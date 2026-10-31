"""Mary's long memory (M9c): what a resident has told her, dated, in its own SQLite file, apart from the incident log.

Only a small core goes to Gemini every turn (always_sent). The rest stays on the laptop until she looks it up with
recall, which is plain word matching in Python, with no cloud. The incident log is evidence and keeps soft delete;
this is not: forgetting is a real delete, and what is forgotten is gone from this file and from its one backup.
Takes a connect callable (server.connect_memories), and imports neither server nor mary.
"""
import json
import os
import re
from contextlib import closing
from datetime import date, datetime
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
    what TEXT
);
CREATE TABLE IF NOT EXISTS date_done (
    date_id INTEGER,
    year INTEGER,
    at TEXT,
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


def _clean(text):
    text = " ".join(str(text or "").split())[:MAX_TEXT].rstrip()
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


_DATE_COLUMNS = ("id", "memory_id", "created_at", "month", "day", "who", "relation", "what")  # M15a


def _delete(conn, ids):  # M15a
    """Really deletes these memories, the dates they hold up and those dates' done marks."""
    rows = [(memory_id,) for memory_id in ids]
    conn.executemany("DELETE FROM date_done WHERE date_id IN (SELECT id FROM dates WHERE memory_id = ?)", rows)
    conn.executemany("DELETE FROM dates WHERE memory_id = ?", rows)
    return sum(conn.execute("DELETE FROM memories WHERE id = ?", row).rowcount for row in rows)


def _unstop(conn, about):  # M15a
    """Drops this person's no-reminder row: what is forgotten leaves no trace, not even "don't mention Ruth"."""
    who = " ".join(w for w in _words(about) if w not in STOPWORDS)
    return conn.execute("DELETE FROM no_reminders WHERE who = ?", (who,)).rowcount


def _date_rows(conn):  # M15a
    rows = conn.execute(f"SELECT {', '.join(_DATE_COLUMNS)} FROM dates ORDER BY id").fetchall()
    return [dict(zip(_DATE_COLUMNS, row)) for row in rows]


def _label_memory(conn, label):  # M15a
    """The id of a memory saying just this label, added if none does yet."""
    new_id = _insert(conn, label, "family", "said")
    if new_id is None:
        same = label.casefold()
        new_id = next(r[0] for r in conn.execute("SELECT id, text FROM memories") if r[1].casefold() == same)
    return new_id


def _let_go(conn, row):  # M15a
    """Deletes the memory behind this date, leaving the date, unless another date stands on it too. True if it went."""
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


class MemoryStore:
    """Her dated memories. Every call opens and closes its own connection, so it needs no lock of its own.
    on_change(deleted) runs after every change is saved, so the server can keep her one backup current."""

    def __init__(self, connect, on_change=None):
        self.connect = connect
        self.on_change = on_change

    def _changed(self, deleted):
        if self.on_change:
            self.on_change(deleted)

    def add(self, text, kind="", source="talk"):
        """The new memory's id, or None if it was empty or is already saved. There is no cap. Something forgotten
        may be saved again if the resident says it again."""
        text = _clean(text)
        if not text:
            return None
        with closing(self.connect()) as conn, conn:
            new_id = _insert(conn, text, kind, source)
        if new_id is not None:
            self._changed(False)
        return new_id

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

    def forget(self, about=""):
        """Really deletes and returns the texts removed. Empty about: the single newest memory ("forget that"), if it
        was saved within FORGET_THAT_S. Otherwise everything matching(about) finds."""
        if str(about or "").strip():
            rows = self.matching(about)
        else:
            rows = [r for r in self.active(limit=1) if _just_saved(r)]
        with closing(self.connect()) as conn, conn:  # M15a
            _delete(conn, [r["id"] for r in rows])
            cleared = _unstop(conn, about)
            if is_everything(about):
                for table in ("date_done", "dates", "no_reminders"):
                    cleared += conn.execute(f"DELETE FROM {table}").rowcount
        if rows or cleared:
            self._changed(True)
        return [r["text"] for r in rows]

    def forget_name(self, name):  # M9c
        """Really deletes every memory holding their name and returns the texts removed."""
        rows = [r for r in self.active() if holds_name(r["text"], name)]
        with closing(self.connect()) as conn, conn:  # M15a
            _delete(conn, [r["id"] for r in rows])
            cleared = _unstop(conn, name)
        if rows or cleared:
            self._changed(True)
        return [r["text"] for r in rows]

    def learn_date(self, found, memory_id=None):  # M15a
        """Keeps a date from parse and returns its id. Every date has a memory behind it: memory_id when it came from a
        saved fact, else one of its own whose text is its label (an auto row). The same who and what again is the same
        date, and a different day is a correction."""
        memory_id = _row_id(memory_id)
        label = memory_dates.label(found)
        deleted = False
        with closing(self.connect()) as conn, conn:
            start = conn.total_changes
            if memory_id and not conn.execute("SELECT 1 FROM memories WHERE id = ?", (memory_id,)).fetchone():
                memory_id = None
            key = (found["who"].casefold(), found["what"])
            row = next((r for r in _date_rows(conn) if (r["who"].casefold(), r["what"]) == key), None)
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
        out = [{**{k: row[k] for k in ("id", "who", "relation", "what", "month", "day")}, "on": on,
                "days": (on - today).days, "label": memory_dates.label(row)}
               for row, on in soon if (row["id"], on.year) not in done and not _people(row) & quiet]
        return sorted(out, key=lambda item: (item["days"], item["id"]))[:3]

    def mark_done(self, date_id, year):  # M15a
        """This date was raised this year, so it stays quiet until the next."""
        with closing(self.connect()) as conn, conn:
            conn.execute("INSERT OR IGNORE INTO date_done (date_id, year, at) VALUES (?, ?, ?)",
                         (date_id, year, _now()))
        self._changed(False)

    def said_due(self, text, today=None):  # M15a
        """Marks done each due date her words name, and returns their ids. When in doubt it counts as said, for the same
        "once" promise."""
        said = [row for row in self.due(today) if _named(text, row)]
        for row in said:
            self.mark_done(row["id"], row["on"].year)
        return [row["id"] for row in said]

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

    def last_raised(self):  # M15a
        """Who the newest raised date was about, for "don't remind me about him"; "anniversary" for their own, "" if
        none has been raised."""
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT d.who FROM date_done x JOIN dates d ON d.id = x.date_id "
                               "ORDER BY x.at DESC, x.rowid DESC LIMIT 1").fetchone()
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
