"""Mary's long memory (M9c): what a resident has told her, dated, in its own SQLite file, apart from the incident log.

Only a small core goes to Gemini every turn (always_sent). The rest stays on the laptop until she looks it up with
recall, which is plain word matching in Python, with no cloud. The incident log is evidence and keeps soft delete;
this is not: forgetting is a real delete, and what is forgotten is gone from this file and from its one backup.
Takes a connect callable (server.connect_memories), and imports neither server nor mary.
"""
import json
import os
import re
import time  # M15a
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

import memory_dates

MEMORIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id INTEGER NOT NULL,
    created_at TEXT,
    month INTEGER,
    day INTEGER,
    who TEXT,
    relation TEXT,
    what TEXT,
    source TEXT NOT NULL DEFAULT '',
    person_id TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS date_done (
    date_id INTEGER,
    year INTEGER,
    at TEXT,
    PRIMARY KEY (date_id, year)
);
CREATE TABLE IF NOT EXISTS date_sent (
    date_id INTEGER,
    year INTEGER,
    at REAL,
    replies INTEGER DEFAULT 0,
    PRIMARY KEY (date_id, year)
);
CREATE TABLE IF NOT EXISTS no_reminders (
    who TEXT PRIMARY KEY,
    why TEXT,
    at TEXT
);
"""
KINDS = ("person", "family", "likes", "health_care", "history", "preference", "other")
SOURCES = ("talk", "typed", "said")
MAX_TEXT = 200
NOTE_REPLIES = 3  # M15a: her replies a raised date's note may ride along with
TALK_GAP_S = 600  # M15a: a sent note this old by the real clock belongs to a talk that is over
LATELY_ITEMS = 3
SAFETY_LABEL = "Always keep in mind:"
LATELY_LABEL = "Lately they told you:"
MORE_LINE = "More is saved about them; look it up with recall when it could help."
MIN_SAFETY_WORDS = 10  # below this the more line gives way, so the safety text isn't cut to nothing
EXACT_SCORE = 3  # an exact word counts more than a word from the same family
SYNONYM_SCORE = 1

_COLUMNS = ("id", "created_at", "kind", "text", "source")
_GEMINI_KEY = re.compile(r"AIza[0-9A-Za-z_-]{20,}")  # a pasted key is never kept, whatever else the line says
_VOWELS = "aeiouy"
STOPWORDS = frozenset("""
    a about again all also am an and any anything are around as at back be been but by can could did do does doing dont
    didnt else even ever everything for forget from get got had has have he her here hers him his how i if im in into
    is it its ive just knew know me mine more most much my myself no nor not now of on or our out recall remember said
    say she so some something tell than that the their them then there these they thing things this those to told too
    talk talked talking up us very was we were what when where which who whom whose why with would you your yours
""".split())
# Word families for recall only; forget never uses them, so it can't remove more than was asked.
SYNONYMS = (
    ("daughter", "son", "kids", "children", "child", "grandchild", "grandchildren", "family"),
    ("wife", "husband", "married"),
    ("dog", "cat", "pet"),
    ("church", "faith", "pray", "bible"),
    ("job", "work", "worked", "career"),
    ("home", "house", "live", "lived", "moved", "town"),
    ("army", "navy", "marines", "air force", "coast guard", "veteran", "vet", "served", "service"),
    ("doctor", "nurse", "medicine", "meds", "pills"),
    ("fish", "fishing", "hunt", "hunting", "gun", "rifle"),
)
_KIND_WORDS = (  # first hit wins, so "would rather not talk about her son" is a preference
    ("preference", "prefer rather nickname want"),
    ("family", "daughter son kids children child grandchild grandchildren grandson granddaughter family wife husband "
               "married mother father mom dad brother sister nephew niece aunt uncle cousin widow widower"),
    ("history", "born grew raised worked work job career retired served army navy marines airforce coastguard veteran "
                "vet war moved lived school farm"),
    ("health_care", "doctor nurse medicine meds pills insulin diabetes diabetic surgery hospital wheelchair therapy "
                    "allergic allergy pain stroke cancer heart dialysis diet oxygen"),
    ("likes", "like love enjoy favorite hate"),
    ("person", "friend neighbor roommate pastor preacher buddy named"),
)
# A veteran is something she must never lose sight of. "the vet" is the animal doctor.
SAFETY_RE = re.compile(
    r"\b(?:veterans?|(?<!the )vets?|served\s+(?:in|with)\s+(?:the\s+)?(?:united\s+states\s+|u\.?s\.?\s+)?"
    r"(?:army|navy|marines?|marine\s+corps|air\s+force|coast\s+guard))\b", re.I)
_NOT_SAFETY = {"not", "never", "no", "isn't", "wasn't", "didn't", "hasn't", "isnt", "wasnt", "didnt", "hasnt"}
# What to call them goes out every time too, or she would ask again each talk whether "honey" is all right.
_CALL_THEM_RE = re.compile(r"\b(?:pet\s+names?|nicknames?|goes\s+by|(?:likes?|prefers?|wants?)\s+to\s+be\s+called|"
                           r"(?:okay|ok|fine|all\s+right|alright)\s+(?:with\s+being|being|to\s+be)\s+called|"
                           r"call(?:ed|ing)?\s+(?:him|her|them)\b)", re.I)
# M4c: a memory that says what they go by, so she stops asking. It must open the memory: "His son goes by Mike" and
# "Doesn't want to be called Bill" don't count, and neither does being fine with a pet name.
_GOES_BY_RE = re.compile(r"^\s*(?:(?:they|he|she|(?:the\s+)?resident)\s+)?"
                         r"(?:go(?:es)?\s+by|(?:likes?|prefers?|wants?)\s+(?:to\s+be|being)\s+called)\s+(?!by\b)\S", re.I)
FORGET_THAT_S = 3600  # "forget that" means something just saved, never a memory from months ago
FORGET_YES_S = 300  # how long "forget about my son" waits for the resident's yes
FORGET_REACH = None  # M15c: set by the app. count(about) and forget(about, own_name=False) reach a skill's saved people
BOOK_LINK = None  # M19: set by the app. people(), find(words) and set_birthday(person_id, month, day); locked ones raise
BOOK_SOURCE = "book"  # M19: a date from a card, with memory_id 0: no memory is behind it
# Who a memory names, so "forget about my son" takes every memory about him. Only these spots count as a name, never
# every capitalized word: "Raleigh" must not spread.
_RELATIONS = "son daughter wife husband brother sister mother father friend grandson granddaughter"
_NAMED = re.compile(rf"\b(?=(?i:named|called|{'|'.join(_RELATIONS.split())})\s*,?\s+([^\W\d_]+))")  # overlapping: "son named Mike"
_MY_WORD_NAMED = re.compile(r"\b(?i:my|his|her|their)\s+[^\W\d_]+\s+([^\W\d_]+)")  # "my nephew Joe"; for talk history only
_NOT_NAMES = STOPWORDS | frozenset("monday tuesday wednesday thursday friday saturday sunday".split())


def _whole(name):  # M9c
    return r"(?<!\w)" + r"\s+".join(re.escape(w) for w in str(name or "").split()) + r"(?!\w)"


def holds_name(text, name):  # M9c
    """True when a saved memory holds this name: the whole word as written, or in any case after "called" or "goes
    by". "Will" stays out of "will walk"; "Goes by andy" is caught."""
    if not str(name or "").strip():
        return False
    return bool(re.search(_whole(name), text) or re.search(r"\b(?:called|goes\s+by)\s+" + _whole(name), text, re.I))


def says_name(text, name):  # M9c
    """True when a turn of talk holds this name as a whole word, in any case."""
    return bool(str(name or "").strip()) and bool(re.search(_whole(name), text, re.I))


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _today():  # M15a
    """Today, or the day in TRACKER_TODAY (YYYY-MM-DD), so Andy can try a date out without waiting for it."""
    try:
        return date.fromisoformat(os.environ.get("TRACKER_TODAY", ""))
    except ValueError:
        return date.today()


# --- M18: an email address is kept in one place, the messages skill's contacts, and goes through here everywhere else ---
ADDRESS_WORDS = "(an email address)"
_TLD = r"(?:com|net|org|edu|gov|mil|info|biz|us|co|uk|ca)"
_DOT = r"(?:\s*\.(?=[a-z0-9])|\s+\.\s+|[\s,]+(?:dot|period|point)[\s,]+)"  # "home. Us kids" is the end of a sentence
_SPELLED = r"(?:[a-z0-9][\s,.-]+)+[a-z0-9]"  # g m a i l, or a-o-l
_MAIL_HOST = (r"(?:g\s?mail|google\s?mail|ya\s?hoo|y\s?mail|a\s?o\s?l|hot\s?mail|out\s?look|live|msn|i\s?cloud|me|comcast|"
              r"xfinity|verizon|a\s?t\s?t|bell\s?south|charter|spectrum|earth\s?link|wind\s?stream|proton\s?mail|proton|mail)")
# The address-shaped ending: at, a name, a dot, a known ending. A mail company needs nothing more. Any other name needs
# a name in front ("mark at hollisfamily dot com"), so "bought it at walmart dot com" stays plain talk.
_ADDRESS_END = re.compile(
    r"(?P<at>@|(?<![\w.'-])at(?:[\s-]+(?:sign|symbol))?(?![\w'-]))[\s,]*"
    r"(?:(?P<mail>" + _MAIL_HOST + r")(?:" + _DOT + r"|\.\s+|[\s,]+(?=(?:com|net)\b))"
    r"|(?P<host>[a-z0-9][a-z0-9-]*|" + _SPELLED + r")" + _DOT + r")"
    r"(?:[a-z0-9][a-z0-9-]*" + _DOT + r"){0,3}" + _TLD + r"(?:" + _DOT + _TLD + r")?(?![\w-])", re.I)
_WRITTEN = re.compile(r"[\w.+%'-]+@[\w-]+(?:[.,][\w-]+)*|[\w.+%'-]+\s*@\s*[\w-]+(?:\.[\w-]+)+", re.I)  # any ending at all
_WRITTEN_LEFT = re.compile(r"[\w.+%'-]+$")
_PIECE = re.compile(r"under\s+score|[^\s,;:!?()\"<>]+", re.I)
_JOINS = frozenset(("dot", "period", "point", "underscore", "under score", "dash", "hyphen", "minus", "plus"))
_NUMBER_WORDS = frozenset("""zero oh one two three four five six seven eight nine ten eleven twelve thirteen fourteen
    fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred
    thousand""".split())
_NOT_HOSTS = frozenset("the that this those these a an my our your his her their it them".split())
_NOT_NAMES = frozenset("""it its them they that this those these there here he she we you me my mine us our your his her
    their him one ones is are am was were be been being do did does has have had will would can could should may might
    not no yes yeah ok okay sure please thanks and or but so then now also just still only even very really too all any
    some look looks looked looking see saw seen stare stared staring glance glanced shop shops shopped shopping buy buys
    bought order orders ordered sell sells sold sale sales find finds found got get gets go goes going went gone come
    comes came stay stays stayed live lives lived work works worked email e-mail mail address website site page web
    online internet to from for of in on at by with about over under up down out back off say says said tell tells told
    call calls called""".split())
_ONLY_ADDRESS = re.compile(r"(?:(?:[\w'’-]+\s+){0,3}(?:e-?mail|address)\b\s*(?:address\s*)?(?:is|was|:|=)?\s*)?"
                           + re.escape(ADDRESS_WORDS) + r"\W*", re.I)


def _address_start(text, end, after_piece=False):
    """Where the name part of an address starts, going back word by word from end: "mark dot hollis", "m a r k". end
    itself when nothing there can be a name. after_piece: what's at end is a name piece already."""
    pieces = list(_PIECE.finditer(text, max(0, end - 120), end))
    start, can_join = end, not after_piece
    for piece in reversed(pieces):
        word = " ".join(piece.group().lower().split()).replace("’", "'").strip(".!?'\"-")
        if word in _JOINS:
            if can_join:  # two joins together, or nothing yet for it to join
                break
            can_join = True
            continue
        if not can_join or not word or word in _NOT_NAMES or word.endswith("'s"):
            break
        start, can_join = piece.start(), len(word) == 1 or word.isdigit() or word in _NUMBER_WORDS
    return start


def scrub_addresses(text):
    """These words with any email address, written or spoken, as "(an email address)". The caller keeps what it gets
    back. The send gate and give_address see the raw line first, and nothing else needs it."""
    text = str(text or "")
    for found in reversed(list(_ADDRESS_END.finditer(text))):  # from the end, so earlier places stay right
        at = found.start("at")
        if (found.group("host") or "").lower() in _NOT_HOSTS:
            continue
        tight = found.group("at") == "@" and at > 0 and not text[at - 1].isspace()
        left = _WRITTEN_LEFT.search(text, max(0, at - 120), at) if tight else None
        start = _address_start(text, left.start(), True) if left else _address_start(text, at)
        if start == at and found.group("at") != "@" and not found.group("mail"):
            continue
        text = text[:start] + ADDRESS_WORDS + text[found.end():]
    for found in reversed(list(_WRITTEN.finditer(text))):
        text = text[:_address_start(text, found.start(), True)] + ADDRESS_WORDS + text[found.end():]
    return text


def only_address(text):
    """True when scrubbed words say nothing but an address: there's no memory left in them."""
    return bool(_ONLY_ADDRESS.fullmatch(" ".join(str(text or "").split())))
# --- end M18 ---


def _clean(text):
    text = " ".join(scrub_addresses(text).split())[:MAX_TEXT].rstrip()  # M18: scrub first, so a cut can't hide one
    return "" if _GEMINI_KEY.search(text) else text


def _words(text):
    """Lower-case whole words. "Air Force" and "Coast Guard" are one word each, and a possessive 's goes."""
    text = str(text or "").lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"\bcoast\s+guard\b", "coastguard", re.sub(r"\bair\s+force\b", "airforce", text))
    return [w[:-2] if w.endswith("'s") else w.replace("'", "") for w in re.findall(r"[^\W_]+(?:'[^\W_]+)*", text)]


def _stem(word):
    """Light stemming, so "moved", "moves", "moving" and "move" are one word. Short words keep their "e": "care"
    never becomes "car", and "Pete" never becomes "pet"."""
    if len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    if len(word) > 4 and word.endswith("ied"):
        return word[:-3] + "y"
    base = ""
    if len(word) > 5 and word.endswith("ing"):
        base = word[:-3]
    elif len(word) > 4 and word.endswith("ed") and not word.endswith("eed"):
        base = word[:-2]
    if base and any(c in _VOWELS for c in base):  # "spring" and "string" stay whole
        if len(base) > 3 and base[-1] == base[-2] and base[-1] not in "lsz":
            return base[:-1]  # stopped, running
        if len(base) == 3 and base[0] not in _VOWELS and base[1] in _VOWELS and base[2] not in _VOWELS + "wx":
            return base + "e"  # moved, living
        word = base
    return word[:-1] if len(word) > 4 and word.endswith("e") else word


def _stems(text):
    return [_stem(w) for w in _words(text)]


def _meaningful(text):
    return {_stem(w) for w in _words(text) if w not in STOPWORDS}


_RELATION_STEMS = frozenset(_stem(w) for w in _RELATIONS.split())


def is_everything(about):
    """True when they asked her to forget all of it, not one thing."""
    words = str(about or "").lower().replace("’", "'").strip(" .!?")
    return words in ("everything", "all of it", "all that", "everything about me", "all about me", "all of that",
                     "everything you know", "everything you know about me", "everything you remember")


def _names(texts, pattern=_NAMED):
    """The people's names in these texts, as written: the capitalized word in the spots pattern allows."""
    found = set()
    for text in texts:
        for word in pattern.findall(str(text or "").replace("’", "'")):
            if word[0].isupper() and word.lower() not in _NOT_NAMES:
                found.add(word)
    return found


def same_about(one, other):
    """True when two ways of saying what to forget hold the same meaningful words."""
    if is_everything(one) or is_everything(other):
        return is_everything(one) and is_everything(other)
    wanted = _meaningful(one)
    return bool(wanted) and wanted == _meaningful(other)


def carries(turn_text, forgotten_texts, about=""):
    """True when a turn of talk still holds what was just forgotten: all the meaningful words of about, a name from the
    forgotten texts or about, or at least half (never fewer than 2) of the meaningful words of a forgotten fact.
    A turn caught by mistake only costs a line of talk history, so this leans toward catching. "Everything" is every turn."""
    if is_everything(about):
        return True
    have = set(_stems(turn_text))
    wanted = _meaningful(about)
    if wanted and wanted <= have:
        return True
    texts = [*forgotten_texts, about]
    names = _names(texts) | _names(texts, _MY_WORD_NAMED)
    if {name.lower() for name in names} & set(_words(turn_text)):
        return True
    for fact in forgotten_texts:
        stems = _meaningful(fact)
        if len(stems & have) >= max(2, (len(stems) + 1) // 2):
            return True
    return False


_FAMILY_OF = {}
for _group in SYNONYMS:
    _members = {s for word in _group for s in _stems(word)}
    for _member in _members:
        _FAMILY_OF[_member] = _FAMILY_OF.get(_member, frozenset()) | _members
_KIND_STEMS = tuple((kind, frozenset(_stems(words))) for kind, words in _KIND_WORDS)


def guess_kind(text):
    """A keyword guess at what sort of memory this is; "other" when nothing fits."""
    have = set(_stems(text))
    for kind, words in _KIND_STEMS:
        if have & words:
            return kind
    return "other"


def is_safety(text):
    """True for a memory that they served. Clear negatives don't count ("not a veteran", "never served in the Navy")."""
    text = str(text or "").replace("’", "'")
    for hit in SAFETY_RE.finditer(text):
        if not _NOT_SAFETY & set(text[:hit.start()].lower().split()[-3:]):
            return True
    return False


def _always(text):
    """True for a memory that goes out every turn: that they served, or what to call them."""
    return is_safety(text) or bool(_CALL_THEM_RE.search(text))


def _just_saved(memory):
    try:
        return (datetime.now() - datetime.fromisoformat(memory["created_at"])).total_seconds() <= FORGET_THAT_S
    except ValueError:
        return False


def public(memory):
    """A memory as the page and Gemini see it."""
    return {k: memory[k] for k in ("id", "date", "kind", "text")}


def _insert(conn, text, kind, source):
    """One new memory from cleaned text. None, and nothing added, when a memory already says the same."""
    same = text.casefold()
    if any(r[0].casefold() == same for r in conn.execute("SELECT text FROM memories")):
        return None
    return conn.execute("INSERT INTO memories (created_at, kind, text, source) VALUES (?, ?, ?, ?)",
                        (_now(), kind if kind in KINDS else guess_kind(text), text,
                         source if source in SOURCES else "talk")).lastrowid


def _row_id(memory_id):
    """memory_id as a number SQLite can look up, or None."""
    try:
        memory_id = int(memory_id)
    except (TypeError, ValueError):
        return None
    return memory_id if 0 < memory_id < 2 ** 63 else None  # SQLite refuses a bigger number


_DATE_COLUMNS = ("id", "memory_id", "created_at", "month", "day", "who", "relation", "what", "source",  # M15a
                 "person_id")  # M19


def upgrade_dates(conn):  # M19
    """An older file gains the two columns a book birthday needs. Safe at every start."""
    have = {row[1] for row in conn.execute("PRAGMA table_info(dates)")}
    for column in ("source", "person_id"):
        if column not in have:
            conn.execute(f"ALTER TABLE dates ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")


def _delete(conn, ids):  # M15a
    """Really deletes these memories, the dates they hold up and those dates' done marks. A book date has memory_id 0,
    which no memory ever has, so this never reaches one."""
    rows = [(memory_id,) for memory_id in ids if memory_id]
    conn.executemany("DELETE FROM date_done WHERE date_id IN (SELECT id FROM dates WHERE memory_id = ?)", rows)
    conn.executemany("DELETE FROM date_sent WHERE date_id IN (SELECT id FROM dates WHERE memory_id = ?)", rows)
    conn.executemany("DELETE FROM dates WHERE memory_id = ?", rows)
    return sum(conn.execute("DELETE FROM memories WHERE id = ?", row).rowcount for row in rows)


def _unstop(conn, about):  # M15a
    """Drops this person's no-reminder row: what is forgotten leaves no trace, not even "don't mention Ruth"."""
    who = " ".join(w for w in _words(about) if w not in STOPWORDS)
    return conn.execute("DELETE FROM no_reminders WHERE who = ?", (who,)).rowcount


def _date_rows(conn):  # M15a
    rows = conn.execute(f"SELECT {', '.join(_DATE_COLUMNS)} FROM dates ORDER BY id").fetchall()
    return [dict(zip(_DATE_COLUMNS, row)) for row in rows]


def _drop_dates(conn, ids):  # M19
    rows = [(date_id,) for date_id in ids]
    for table in ("date_done", "date_sent"):
        conn.executemany(f"DELETE FROM {table} WHERE date_id = ?", rows)
    conn.executemany("DELETE FROM dates WHERE id = ?", rows)


def _label_memory(conn, label):  # M15a
    """The id of a memory saying just this label, added if none does yet."""
    new_id = _insert(conn, label, "family", "said")
    if new_id is None:
        same = label.casefold()
        new_id = next(r[0] for r in conn.execute("SELECT id, text FROM memories") if r[1].casefold() == same)
    return new_id


def _let_go(conn, row):  # M15a
    """Deletes the memory behind this date, leaving the date, unless another date stands on it too. True if it went."""
    if not row["memory_id"]:  # M19: a book date has no memory behind it
        return False
    if conn.execute("SELECT 1 FROM dates WHERE memory_id = ? AND id != ?", (row["memory_id"], row["id"])).fetchone():
        return False
    return conn.execute("DELETE FROM memories WHERE id = ?", (row["memory_id"],)).rowcount > 0


def _move(conn, row, month, day):  # M15a
    """A corrected date changes in place, so date_done stays and it never comes up twice in a year. The memory behind it
    stops saying the old day: its date words change, or it becomes the label if they can't be found."""
    conn.execute("UPDATE dates SET month = ?, day = ? WHERE id = ?", (month, day, row["id"]))
    saved = conn.execute("SELECT text FROM memories WHERE id = ?", (row["memory_id"],)).fetchone()
    if not saved:
        return
    text = memory_dates.label({**row, "month": month, "day": day})
    for hit in memory_dates.parse(saved[0]):
        if (hit["who"].casefold(), hit["what"]) == (row["who"].casefold(), row["what"]):
            start, end = hit["span"]
            text = saved[0][:start] + memory_dates.when(month, day) + saved[0][end:]
            break
    conn.execute("UPDATE memories SET text = ? WHERE id = ?", (text, row["memory_id"]))


def _who_words(who):  # M15a
    return set(who.lower().split()) - {"and"}


def _people(row):  # M15a
    """The lower-case words that stop this date: each person in it and their relation. A plain anniversary is the
    resident's own, so it goes when either spouse has."""
    if not row["who"]:
        return {"anniversary", "husband", "wife"}
    return _who_words(row["who"]) | ({row["relation"].lower()} - {""})


def _names_of(row):  # M15a
    """The words that name this date in talk: each person in it, or for a bare relation or who "" that relation and
    "anniversary"."""
    who, relation = row["who"].lower(), row["relation"].lower()
    return _who_words(who) if who and who != relation else {relation, "anniversary"} - {""}


def _named(text, row):  # M15a
    return any(says_name(text, name) for name in _names_of(row))


def _same_person(a, b, texts):  # M15a
    """Two date rows (same month, day and what) for one person: a bare relation and that relation with a name, one name
    inside the other ("Mark", "Mark Smith"), or a bare relation and a plain name that a memory ties together ("Mark is
    my son"). Two named people never merge on relation alone."""
    if (a["month"], a["day"], a["what"]) != (b["month"], b["day"], b["what"]):
        return False
    wa, wb = _who_words(a["who"]), _who_words(b["who"])
    if wa and wb and (wa <= wb or wb <= wa):
        return True
    for bare, other in ((a, b), (b, a)):
        rel = bare["relation"].lower()
        if not rel or bare["who"].lower() != rel:
            continue
        if other["relation"].lower() == rel:
            return True
        if not other["relation"] and other["who"]:
            names = _who_words(other["who"])
            for text in texts:
                words = re.findall(r"\w+", text.lower())
                rels = [i for i, w in enumerate(words) if w == rel]
                if any(abs(i - j) <= 3 for i in rels for j, w in enumerate(words) if w in names):
                    return True
    return False


def _touched_last(rows, turns, text):  # M15a
    """The date a correction means: the one named with its birthday or anniversary word, or its day, in the turn nearest
    the newest. Two in that turn: the one the correction names, or None, since a wrong guess spoils a good date."""
    for turn in turns or ():
        said = memory_dates.loose_dates(turn)
        hits = [r for r in rows if _named(turn, r) and (says_name(turn, r["what"]) or (r["month"], r["day"]) in said)]
        if hits:
            hits = [r for r in hits if _named(text, r)] or hits
            return hits[0] if len(hits) == 1 else None
    return None


def _first_word(name):  # M19
    return (str(name or "").lower().split() or [""])[0]


def _relation_word(text):  # M19
    return re.sub(r"^(?:my|our)\s+", "", " ".join(str(text or "").lower().split()))


def _card_day(record):  # M19
    """(month, day) of a card's birthday, "MM-DD" or "YYYY-MM-DD", or (None, None) with none."""
    text = str((record or {}).get("birthday") or "")
    return (int(text[-5:-3]), int(text[-2:])) if len(text) >= 5 else (None, None)


def book_taken(people, person_id=None):  # M19
    """The first names and relationships of everyone in the book but this person, which can't be taken to mean them."""
    taken = set()
    for person in people:
        if person["id"] != person_id:
            taken |= {_first_word(person["name"]), _relation_word(person["relationship"])}
    return taken - {""}


def _is_theirs(row, name, relation, taken):  # M19
    """True when this date's who means this person: their full name, or their first name or relationship when nobody
    else in the book has it (taken). A date saying another relation is someone else's: a brother Mark is not a son Mark."""
    said = row["relation"].lower()
    if said and relation and said != relation:
        return False
    who, whole, first = _who_words(row["who"]), _who_words(name), _first_word(name)
    if not who:
        return False
    if whole <= who <= whole | {relation} or who == {first, relation}:
        return True
    return who <= ({first, relation} - set(taken) - {""})


def _stop_words(name, relation, taken):  # M19
    """The no_reminders keys that mean this person."""
    return ({" ".join(name.lower().split())} | ({_first_word(name), relation} - set(taken))) - {""}


def _book_match(found, rows, hits):  # M19
    """The book date a birthday from talk belongs to, or None. hits: who the book finds by that name. One person is that
    person's date. Several: the one on the same day. None found: the only date with this first name, where one name sits
    inside the other, so "Sarah Beck" can be "Sarah" but never "Sarah Whitfield". A different relation is someone else."""
    relation = _relation_word(found["relation"])

    def fits(other):
        return not relation or not other or other == relation

    saved = {row["person_id"]: row for row in rows}
    hits = [person for person in hits if fits(_relation_word(person["relationship"]))]
    if len(hits) == 1:
        return saved.get(hits[0]["id"])
    if hits:
        same = [saved[p["id"]] for p in hits
                if p["id"] in saved and (saved[p["id"]]["month"], saved[p["id"]]["day"]) == (found["month"], found["day"])]
        return same[0] if len(same) == 1 else None
    said = _who_words(found["who"])
    near = [row for row in rows if fits(row["relation"]) and _first_word(row["who"]) == _first_word(found["who"])
            and (said <= _who_words(row["who"]) or _who_words(row["who"]) <= said)]
    return near[0] if len(near) == 1 else None


def _book_people():  # M19
    """Everyone in the book, hidden marks too, or None with no link or a locked book."""
    try:
        return BOOK_LINK.people() if BOOK_LINK else None
    except Exception:  # noqa: BLE001
        return None


def _card_birthday(person_id, month, day):  # M19
    """The card follows a date corrected in talk. Her side is already saved, so a fault here stays here."""
    try:
        if BOOK_LINK:
            BOOK_LINK.set_birthday(person_id, month, day)
    except Exception:  # noqa: BLE001
        pass


def _reach_gone(about, own_name=False):  # M15c
    """What a forget also took outside her memories (a contact and its address), or [] with no reach or on any error."""
    try:
        return [str(text) for text in FORGET_REACH.forget(about, own_name=own_name)] if FORGET_REACH else []
    except Exception:  # noqa: BLE001 (her own delete already happened; a skill's fault can't undo that)
        return []


class MemoryStore:
    """Her dated memories. Every call opens and closes its own connection, so it needs no lock of its own.
    on_change(deleted) runs after every change is saved, so the server can keep her one backup current."""

    def __init__(self, connect, on_change=None):
        self.connect = connect
        self.on_change = on_change
        self.names_gone = []  # M19: who the last forget took from the book, for what talk history holds of them

    def _changed(self, deleted):
        if self.on_change:
            self.on_change(deleted)

    def add(self, text, kind="", source="talk"):
        """The new memory's id, or None if it was empty or is already saved. There is no cap. Something forgotten
        may be saved again if the resident says it again."""
        text = _clean(text)
        if not text or only_address(text):  # M18
            return None
        with closing(self.connect()) as conn, conn:
            new_id = _insert(conn, text, kind, source)
        if new_id is not None:
            self._changed(False)
        return new_id

    def asks(self, about):  # M19
        """What she must ask before this forget, from a skill's forget_question: {"which": names}, {"field": name} or
        {"person": name, "relationship": word}. None when it's nothing special, with no reach or on any error."""
        try:
            ask = getattr(FORGET_REACH, "ask", None)
            out = ask(about) if callable(ask) else None
        except Exception:  # noqa: BLE001
            return None
        return out if isinstance(out, dict) else None

    def active(self, limit=None):
        """Her memories, newest first."""
        with closing(self.connect()) as conn:
            rows = conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM memories "
                                "ORDER BY created_at DESC, id DESC LIMIT ?", (-1 if limit is None else limit,)).fetchall()
        out = [dict(zip(_COLUMNS, row)) for row in rows]
        for memory in out:
            memory["date"] = memory["created_at"][:10]
        return out

    def count(self):
        with closing(self.connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def text_of(self, memory_id):
        """The words of one memory, or None if it isn't here."""
        memory_id = _row_id(memory_id)
        if memory_id is None:
            return None
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT text FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return row[0] if row else None

    def remove(self, memory_id):
        """A real delete. True if it was here."""
        memory_id = _row_id(memory_id)
        if memory_id is None:
            return False
        with closing(self.connect()) as conn, conn:
            gone = _delete(conn, [memory_id]) > 0  # M15a
        if gone:
            self._changed(True)
        return gone

    def recall(self, words="", kind="", limit=6):
        """The best matches for words, newest first, so a newer fact always comes before an older one. No words: the
        newest of that kind, or of all. Words that are all stopwords, or that match nothing: []."""
        rows = self.active()
        if kind in KINDS:
            rows = [r for r in rows if r["kind"] == kind]
        if not str(words or "").strip():
            return [public(r) for r in rows[:limit]]
        wanted = _meaningful(words)
        scored = []
        for place, row in enumerate(rows):
            have = set(_stems(row["text"]))
            score = sum(EXACT_SCORE if word in have else SYNONYM_SCORE if _FAMILY_OF.get(word, frozenset()) & have else 0
                        for word in wanted)
            if score:
                scored.append((-score, place))
        return [public(rows[place]) for place in sorted(place for _, place in sorted(scored)[:limit])]

    def matching(self, about):
        """Everything saved about this, newest first: every memory holding all the meaningful words of about (exact
        words and stems, no synonyms). When about is just a person ("my son", "Mike"), also every memory with a name
        taken from those; "my son's job" stays with the job. The name must be written the same way, so a son named Will
        doesn't take "will" and a daughter named Faith doesn't take "faith". "Everything" is every memory."""
        rows = self.active()
        if is_everything(about):
            return rows
        wanted = _meaningful(about)
        if not wanted:
            return []
        hits = {r["id"] for r in rows if wanted <= set(_stems(r["text"]))}
        names = _names(r["text"] for r in rows if r["id"] in hits)
        if not (len(wanted) == 1 and (wanted <= _RELATION_STEMS or wanted <= {_stem(n.lower()) for n in names})):
            names = set()
        named = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b") if names else None
        return [r for r in rows if r["id"] in hits or (named and named.search(r["text"]))]

    def others(self, about):  # M15c
        """How many things outside her memories match about (a saved contact). 0 with no reach or on any error."""
        try:
            return int(FORGET_REACH.count(about)) if FORGET_REACH else 0
        except Exception:  # noqa: BLE001
            return 0

    def forget(self, about=""):
        """Really deletes and returns the texts removed. Empty about: the single newest memory ("forget that"), if it
        was saved within FORGET_THAT_S. Otherwise everything matching(about) finds, plus what FORGET_REACH removed
        (M15c: addresses too, so talk history drops them; they never go back to Gemini)."""
        if str(about or "").strip():
            rows = self.matching(about)
        else:
            rows = [r for r in self.active(limit=1) if _just_saved(r)]
        with closing(self.connect()) as conn, conn:  # M15a
            _delete(conn, [r["id"] for r in rows])
            cleared = _unstop(conn, about)
            if is_everything(about):  # M19: the book stays, so its dates and their done marks do too
                talk_date = "date_id NOT IN (SELECT id FROM dates WHERE source = ?)"
                cleared += conn.execute(f"DELETE FROM date_done WHERE {talk_date}", (BOOK_SOURCE,)).rowcount
                cleared += conn.execute(f"DELETE FROM date_sent WHERE {talk_date}", (BOOK_SOURCE,)).rowcount
                cleared += conn.execute("DELETE FROM dates WHERE source != ?", (BOOK_SOURCE,)).rowcount
                cleared += conn.execute("DELETE FROM no_reminders").rowcount
        if rows or cleared:
            self._changed(True)
        gone = [r["text"] for r in rows]
        return gone + self._reach(about) if str(about or "").strip() else gone  # M15c

    def forget_name(self, name):  # M9c
        """Really deletes every memory holding their name and returns the texts removed. M15c: FORGET_REACH takes only a
        contact whose full name is exactly this one."""
        rows = [r for r in self.active() if holds_name(r["text"], name)]
        with closing(self.connect()) as conn, conn:  # M15a
            _delete(conn, [r["id"] for r in rows])
            cleared = _unstop(conn, name)
        if rows or cleared:
            self._changed(True)
        return [r["text"] for r in rows] + self._reach(name, own_name=True)  # M15c

    def _reach(self, about, own_name=False):  # M19
        """_reach_gone, then what each person really removed from the book takes with them."""
        self.names_gone = []
        before = _book_people()
        gone = _reach_gone(about, own_name=own_name)
        after = _book_people() if before else None
        if after is None:
            return gone
        left = {person["id"] for person in after}
        for person in before:
            if person["id"] not in left:
                gone = gone + self._take_person(person, book_taken(after))
        return gone

    def _take_person(self, person, taken):  # M19
        """Someone left the book: every memory holding their full name, their first name unless someone else in the book
        shares it, and what matching finds for their relationship unless someone else has it, then every date and
        no-reminder row of theirs. Returns the memories' texts."""
        name, relation = person["name"], _relation_word(person["relationship"])
        first_free, relation_free = _first_word(name) not in taken, relation and relation not in taken
        rows = {r["id"]: r for r in self.active()
                if says_name(r["text"], name) or (first_free and holds_name(r["text"], name.split()[0]))}
        if relation_free:
            rows.update((r["id"], r) for r in self.matching(relation))
        stops = _stop_words(name, relation, taken)
        with closing(self.connect()) as conn, conn:
            _delete(conn, list(rows))
            dates = [r["id"] for r in _date_rows(conn) if r["person_id"] == person["id"]
                     or (not r["person_id"] and _is_theirs(r, name, relation, taken))]
            _drop_dates(conn, dates)
            stopped = sum(conn.execute("DELETE FROM no_reminders WHERE who = ?", (who,)).rowcount for who in stops)
        if rows or dates or stopped:
            self._changed(True)
        self.names_gone += [name] + [word for word in (name.split()[0] if first_free else "",
                                                       relation if relation_free else "") if word]
        return [r["text"] for r in rows.values()]

    def book_date(self, person_id, record, taken=()):  # M19
        """Keeps one person's birthday row in step with their card. A birthday makes or moves the row, in place, the way
        _move does, so its done marks stay. None, or a card with no birthday, deletes the row with its marks and their
        no-reminder rows. A date from talk that means this person joins the row, so there's never a second reminder. The
        same values again change nothing, so a card update that came from talk can't go round again."""
        month, day = _card_day(record)
        deleted = False
        with closing(self.connect()) as conn, conn:
            start = conn.total_changes
            row = next((r for r in _date_rows(conn) if r["source"] == BOOK_SOURCE and r["person_id"] == person_id), None)
            if month is None:
                if row:
                    _drop_dates(conn, [row["id"]])
                    conn.executemany("DELETE FROM no_reminders WHERE who = ?",
                                     [(who,) for who in _stop_words(row["who"], row["relation"], taken)])
                    deleted = True
            else:
                name, relation = record["name"], _relation_word(record["relationship"])
                if row is None:
                    date_id = conn.execute(
                        "INSERT INTO dates (memory_id, created_at, month, day, who, relation, what, source, person_id) "
                        "VALUES (0, ?, ?, ?, ?, ?, 'birthday', ?, ?)",
                        (_today().isoformat(), month, day, name, relation, BOOK_SOURCE, person_id)).lastrowid
                else:
                    date_id = row["id"]
                    if (row["who"], row["relation"]) != (name, relation):
                        conn.execute("UPDATE dates SET who = ?, relation = ? WHERE id = ?", (name, relation, date_id))
                    if (row["month"], row["day"]) != (month, day):
                        _move(conn, row, month, day)
                for talk in _date_rows(conn):
                    if talk["source"] != BOOK_SOURCE and talk["what"] == "birthday" and _is_theirs(talk, name, relation, taken):
                        if (talk["month"], talk["day"]) != (month, day):
                            _move(conn, talk, month, day)  # its memory stops saying the old day
                        for table in ("date_done", "date_sent"):
                            conn.execute(f"UPDATE OR IGNORE {table} SET date_id = ? WHERE date_id = ?", (date_id, talk["id"]))
                        _drop_dates(conn, [talk["id"]])
            changed = conn.total_changes != start
        if changed:
            self._changed(deleted)

    def clear_book_dates(self):  # M19
        """Every book date goes, with its marks and no-reminder rows. Dates from talk and her memories stay. Returns how many."""
        with closing(self.connect()) as conn, conn:
            rows = [r for r in _date_rows(conn) if r["source"] == BOOK_SOURCE]
            _drop_dates(conn, [r["id"] for r in rows])
            conn.executemany("DELETE FROM no_reminders WHERE who = ?",
                             [(who,) for r in rows for who in _stop_words(r["who"], r["relation"], ())])
        if rows:
            self._changed(True)
        return len(rows)

    def book_people(self):  # M19
        """The ids of everyone with a book date."""
        with closing(self.connect()) as conn:
            return {r["person_id"] for r in _date_rows(conn) if r["source"] == BOOK_SOURCE}

    def _book_row_for(self, found):  # M19
        """The book date this date from talk is, or None: not a birthday, no book date, or a locked book."""
        if found["what"] != "birthday" or not found["who"] or BOOK_LINK is None:
            return None
        with closing(self.connect()) as conn:
            rows = [r for r in _date_rows(conn) if r["source"] == BOOK_SOURCE]
        try:
            return _book_match(found, rows, BOOK_LINK.find(found["who"])) if rows else None
        except Exception:  # noqa: BLE001 (a locked book: it acts as it did before there was a book)
            return None

    def learn_date(self, found, memory_id=None):  # M15a
        """Keeps a date from parse and returns its id. Every date has a memory behind it: memory_id when it came from a
        saved fact, else one of its own whose text is its label (an auto row). The same who and what again is the same
        date, and a different day is a correction. M19: a birthday the book already holds is that row, and a different
        day corrects the card too. The memory that said it stays."""
        book_row = self._book_row_for(found)
        if book_row:
            if (found["month"], found["day"]) != (book_row["month"], book_row["day"]):
                with closing(self.connect()) as conn, conn:
                    _move(conn, book_row, found["month"], found["day"])
                self._changed(False)
                _card_birthday(book_row["person_id"], found["month"], found["day"])  # after the commit: its on_change opens this file
            return book_row["id"]
        memory_id = _row_id(memory_id)
        label = memory_dates.label(found)
        deleted = False
        with closing(self.connect()) as conn, conn:
            start = conn.total_changes
            if memory_id and not conn.execute("SELECT 1 FROM memories WHERE id = ?", (memory_id,)).fetchone():
                memory_id = None
            key = (found["who"].casefold(), found["what"])
            row = next((r for r in _date_rows(conn) if r["source"] != BOOK_SOURCE  # M19
                        and (r["who"].casefold(), r["what"]) == key), None)
            if row is None:
                date_id = conn.execute(
                    "INSERT INTO dates (memory_id, created_at, month, day, who, relation, what) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (memory_id or _label_memory(conn, label), _today().isoformat(), found["month"], found["day"],
                     found["who"], found["relation"], found["what"])).lastrowid
            else:
                date_id = row["id"]
                moved = (found["month"], found["day"]) != (row["month"], row["day"])
                old = conn.execute("SELECT text FROM memories WHERE id = ?", (row["memory_id"],)).fetchone()
                auto = bool(old) and old[0].casefold() == memory_dates.label(row).casefold()
                if memory_id and memory_id != row["memory_id"] and (moved or auto):
                    deleted = _let_go(conn, row)
                    conn.execute("UPDATE dates SET memory_id = ? WHERE id = ?", (memory_id, date_id))
                if moved:
                    _move(conn, row, found["month"], found["day"])
                if found["relation"]:
                    conn.execute("UPDATE dates SET relation = ? WHERE id = ? AND relation = ''",
                                 (found["relation"], date_id))
            changed = conn.total_changes != start
        if changed:
            self._changed(deleted)
        return date_id

    def correct_last(self, text, heard_turns):  # M15a
        """For "no, it's the 9th": fixes the date touched last, keeping its month if only a day was said. heard_turns
        are recent turn texts, newest first. The date's id, or None when nothing fits or the day can't be."""
        if not memory_dates.is_correction(text):
            return None
        if re.match(r"\W*it(?:'|’)?s\b|\W*it\s+is\b", str(text or ""), re.I):
            heard_turns = list(heard_turns or ())[:2]  # a bare "it's the 9th" may answer anything: only right after the date
        said, day = memory_dates.loose_dates(text), memory_dates.loose_day(text)
        if len(said) != 1 and day is None:
            return None
        with closing(self.connect()) as conn, conn:
            row = _touched_last(_date_rows(conn), heard_turns, text)
            if row is None:
                return None
            month, day = next(iter(said)) if len(said) == 1 else (row["month"], day)
            if not memory_dates.valid(month, day):
                return None
            moved = (month, day) != (row["month"], row["day"])
            if moved:
                _move(conn, row, month, day)
        if moved:
            self._changed(False)
            if row["source"] == BOOK_SOURCE:  # M19
                _card_birthday(row["person_id"], month, day)
        return row["id"]

    def date_of(self, memory_id):  # M15a
        """The label of the date this memory holds up, or ""."""
        memory_id = _row_id(memory_id)
        with closing(self.connect()) as conn:
            rows = [r for r in _date_rows(conn) if r["memory_id"] == memory_id]
        return memory_dates.label(rows[0]) if rows else ""

    def active_public(self):  # M15a
        """Her memories for the page, each with saved_date, the label of its date or "". public itself stays as it is,
        since it goes out to Gemini in recall."""
        with closing(self.connect()) as conn:
            saved = {}
            for row in _date_rows(conn):
                saved.setdefault(row["memory_id"], memory_dates.label(row))
        return [{**public(m), "saved_date": saved.get(m["id"], "")} for m in self.active()]

    def due(self, today=None):  # M15a
        """The dates to raise now: 5 to 8 days ahead, nearest first, at most 3. Not one already raised this year, one
        learned today (she was just told, so it isn't news), one they asked to stop, or anyone who has died."""
        today = today or _today()
        with closing(self.connect()) as conn:
            soon = [(row, memory_dates.next_date(row["month"], row["day"], today)) for row in _date_rows(conn)]
            soon = [(row, on) for row, on in soon
                    if 5 <= (on - today).days <= 8 and str(row["created_at"])[:10] != today.isoformat()]
            if not soon:  # most days, and passed below reads every memory
                return []
            done = {tuple(row) for row in conn.execute("SELECT date_id, year FROM date_done")}
            quiet = [row[0] for row in conn.execute("SELECT who FROM no_reminders")]
        quiet += [name for memory in self.active() for name in memory_dates.passed(memory["text"])]
        quiet = {word for name in quiet for word in name.split()}
        texts = [memory["text"] for memory in self.active()]
        groups = []  # one list of (row, on) per person; a twin that is done, stopped or dead silences them all
        for pair in soon:
            for group in groups:
                if any(_same_person(pair[0], other[0], texts) for other in group):
                    group.append(pair)
                    break
            else:
                groups.append([pair])
        out = []
        for group in groups:
            if any((row["id"], on.year) in done or _people(row) & quiet for row, on in group):
                continue
            row, on = min(group, key=lambda p: (p[0]["who"].lower() == p[0]["relation"].lower(), p[0]["id"]))
            out.append({**{k: row[k] for k in ("id", "who", "relation", "what", "month", "day")}, "on": on,
                        "days": (on - today).days, "label": memory_dates.label(row),
                        "also": sorted(r["id"] for r, _ in group if r["id"] != row["id"])})
        return sorted(out, key=lambda item: (item["days"], item["id"]))[:3]

    def mark_done(self, date_id, year):  # M15a
        """This date was raised this year, so it stays quiet until the next."""
        with closing(self.connect()) as conn, conn:
            conn.execute("INSERT OR IGNORE INTO date_done (date_id, year, at) VALUES (?, ?, ?)",
                         (date_id, year, _today().isoformat()))  # M15a: last_raised reads this by _today()
        self._changed(False)

    def said_due(self, text, today=None):  # M15a
        """Marks done each due date her words name, and returns their ids. When in doubt it counts as said, for the same
        "once" promise."""
        said = [row for row in self.due(today) if _named(text, row)]
        for row in said:
            for date_id in [row["id"], *row["also"]]:
                self.mark_done(date_id, row["on"].year)
        return [date_id for row in said for date_id in [row["id"], *row["also"]]]

    def note_sent(self, items):  # M15a
        """These due() items went out in a prompt. A row already there keeps its reply count, and a group goes as one."""
        now = time.time()
        rows = [(date_id, item["on"].year, now) for item in items for date_id in [item["id"], *item["also"]]]
        with closing(self.connect()) as conn, conn:
            conn.executemany("INSERT INTO date_sent (date_id, year, at) VALUES (?, ?, ?) "
                             "ON CONFLICT (date_id, year) DO UPDATE SET at = excluded.at", rows)

    def note_replied(self):  # M15a
        """She answered with a sent note in her prompt. After NOTE_REPLIES of those it is done, even mid-talk."""
        with closing(self.connect()) as conn, conn:
            conn.execute("UPDATE date_sent SET replies = replies + 1")
        return self._close_sent("replies >= ?", (NOTE_REPLIES,))

    def close_talk(self):  # M15a
        """The talk is over, so every sent note is done. Returns how many."""
        return self._close_sent()

    def close_stale(self, gap_s=TALK_GAP_S):  # M15a
        """The safety net for a talk whose end never reached us: real time, so TRACKER_TODAY doesn't move it."""
        return self._close_sent("at < ?", (time.time() - gap_s,))

    def _close_sent(self, where="1", args=()):  # M15a
        today = _today().isoformat()  # last_raised reads this by _today(), as mark_done
        with closing(self.connect()) as conn, conn:
            rows = [tuple(row) for row in conn.execute(f"SELECT date_id, year FROM date_sent WHERE {where}", args)]
            conn.executemany("INSERT OR IGNORE INTO date_done (date_id, year, at) VALUES (?, ?, ?)",
                             [(*row, today) for row in rows])
            conn.executemany("DELETE FROM date_sent WHERE date_id = ? AND year = ?", rows)
        if rows:
            self._changed(False)
        return len(rows)

    def stop_reminders(self, who):  # M15a
        """No more reminders about this person or relation."""
        who = " ".join(str(who or "").lower().split())
        if who:
            with closing(self.connect()) as conn, conn:
                conn.execute("INSERT OR REPLACE INTO no_reminders (who, why, at) VALUES (?, 'asked', ?)", (who, _now()))
            self._changed(False)

    def allow_reminders(self, who):  # M15a
        """Reminders about this person may come again."""
        who = " ".join(str(who or "").lower().split())
        with closing(self.connect()) as conn, conn:
            gone = conn.execute("DELETE FROM no_reminders WHERE who = ?", (who,)).rowcount > 0
        if gone:
            self._changed(True)

    def note_passed(self, names):  # M15a
        """Keeps these people, who have died, on the no-reminder list. A row already there stays."""
        rows = [(" ".join(str(name or "").lower().split()), _now()) for name in names]
        with closing(self.connect()) as conn, conn:
            start = conn.total_changes
            conn.executemany("INSERT OR IGNORE INTO no_reminders (who, why, at) VALUES (?, 'passed', ?)",
                             [row for row in rows if row[0]])
            changed = conn.total_changes != start
        if changed:
            self._changed(False)

    def last_raised(self, within_days=None):  # M15a
        """Who the newest raised date was about, for "don't remind me about him"; "anniversary" for their own, "" if
        none has been raised. within_days: only a date raised that recently counts."""
        since = "" if within_days is None else (_today() - timedelta(days=within_days)).isoformat()
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT d.who FROM date_sent x JOIN dates d ON d.id = x.date_id "  # a talk still open comes first
                               "ORDER BY x.rowid DESC LIMIT 1").fetchone()
            row = row or conn.execute("SELECT d.who FROM date_done x JOIN dates d ON d.id = x.date_id "
                                      "WHERE substr(x.at, 1, 10) >= ? ORDER BY x.rowid DESC LIMIT 1", (since,)).fetchone()
        return (row[0] or "anniversary") if row else ""

    def goes_by(self):  # M4c
        """True when a memory says what they go by."""
        return any(_GOES_BY_RE.search(r["text"]) for r in self.active())

    def always_sent(self, name="", limit_words=120):
        """The small block sent to Gemini every turn: the name, anything safety-related, up to LATELY_ITEMS newest other
        memories, and a line saying more is saved when it is. Never over limit_words words, labels included: the lately
        items go first, then the safety text is shortened. The name is never dropped."""
        rows = self.active()
        safety = [r["text"] for r in rows if _always(r["text"])]
        items = [r["text"] for r in rows if not _always(r["text"])][:LATELY_ITEMS]
        head = [f"Name: {name}"] if name else []

        def block(safe_words, shown, more):
            lines = list(head)
            if safe_words:
                lines.append(" ".join([SAFETY_LABEL, *safe_words]))
            if shown:
                lines += [LATELY_LABEL] + [f"- {t}" for t in shown]
            return lines + [MORE_LINE] if more else lines

        def size(lines):
            return sum(len(line.split()) for line in lines)

        words = "; ".join(safety).split()
        lines = block(words, items, len(rows) > len(safety) + len(items))
        while size(lines) > limit_words and items:
            items = items[:-1]
            lines = block(words, items, len(rows) > len(safety) + len(items))
        if size(lines) > limit_words:  # only the safety text is left to give way
            label = len(SAFETY_LABEL.split())
            room, more = limit_words - size(block([], [], True)) - label, True
            if room < MIN_SAFETY_WORDS:
                room, more = limit_words - size(head) - label, False
            lines = block(words[:max(room, 0)], [], more)
        return "\n".join(lines)


def _old_facts(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        facts = data.get("facts") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return []
    return [f for f in (facts if isinstance(facts, list) else []) if isinstance(f, str)]


def migrate_json(path, store, settings):
    """Moves the facts in the old memory.json into the store, once, keeping their order (oldest id first). Settings key
    memories_moved goes in after them, so a removed fact never comes back. settings is an open connection to the
    incident log, whose caller commits. The server strips the facts from the file. Returns how many facts moved."""
    if settings.execute("SELECT 1 FROM settings WHERE key = 'memories_moved' AND value = '1'").fetchone():
        return 0
    moved = 0
    with closing(store.connect()) as conn, conn:
        for fact in _old_facts(path):
            text = _clean(fact)
            if text and _insert(conn, text, "", "talk") is not None:
                moved += 1
    settings.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('memories_moved', '1')")
    return moved
