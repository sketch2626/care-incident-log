"""Mary's long memory (M9c): what a resident has told her, dated, in the app's own SQLite log.

Only a small core goes to Gemini every turn (always_sent). The rest stays on the laptop until she looks it up with
recall, which is plain word matching in Python, with no cloud. Like the incident log, nothing is ever hard deleted.
Takes a connect callable (server.connect), and imports neither server nor mary.
"""
import json
import re
from contextlib import closing
from datetime import datetime
from pathlib import Path

MEMORIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    source TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_memories_deleted ON memories (deleted_at);
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
FORGET_THAT_S = 3600  # "forget that" means something just saved, never a memory from months ago


def _now():
    return datetime.now().isoformat(timespec="seconds")


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
    """One new memory from cleaned text. None, and nothing added, when an active memory already says the same."""
    same = text.casefold()
    if any(r[0].casefold() == same for r in conn.execute("SELECT text FROM memories WHERE deleted_at IS NULL")):
        return None
    return conn.execute("INSERT INTO memories (created_at, kind, text, source) VALUES (?, ?, ?, ?)",
                        (_now(), kind if kind in KINDS else guess_kind(text), text,
                         source if source in SOURCES else "talk")).lastrowid


class MemoryStore:
    """Her dated memories. Every call opens and closes its own connection, so it needs no lock of its own."""

    def __init__(self, connect):
        self.connect = connect

    def add(self, text, kind="", source="talk"):
        """The new memory's id, or None if it was empty or is already saved. There is no cap. Something forgotten
        may be saved again if the resident says it again."""
        text = _clean(text)
        if not text:
            return None
        with closing(self.connect()) as conn, conn:
            return _insert(conn, text, kind, source)

    def active(self, limit=None):
        """Memories not forgotten, newest first."""
        with closing(self.connect()) as conn:
            rows = conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM memories WHERE deleted_at IS NULL "
                                "ORDER BY created_at DESC, id DESC LIMIT ?", (-1 if limit is None else limit,)).fetchall()
        out = [dict(zip(_COLUMNS, row)) for row in rows]
        for memory in out:
            memory["date"] = memory["created_at"][:10]
        return out

    def count(self):
        with closing(self.connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM memories WHERE deleted_at IS NULL").fetchone()[0]

    def remove(self, memory_id):
        """Soft delete. True if it was active."""
        try:
            memory_id = int(memory_id)
        except (TypeError, ValueError):
            return False
        if not 0 < memory_id < 2 ** 63:  # SQLite refuses a bigger number
            return False
        with closing(self.connect()) as conn, conn:
            return conn.execute("UPDATE memories SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                                (_now(), memory_id)).rowcount > 0

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

    def forget(self, about=""):
        """Soft deletes and returns the texts removed. Empty about: the single newest memory ("forget that"), if it
        was saved within FORGET_THAT_S. Otherwise every memory holding all the meaningful words of about, exact words
        and stems only, no synonyms."""
        if str(about or "").strip():
            wanted = _meaningful(about)
            rows = [r for r in self.active() if wanted and wanted <= set(_stems(r["text"]))]
        else:
            rows = [r for r in self.active(limit=1) if _just_saved(r)]
        if rows:
            when = _now()
            with closing(self.connect()) as conn, conn:
                conn.executemany("UPDATE memories SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                                 [(when, r["id"]) for r in rows])
        return [r["text"] for r in rows]

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


def migrate_json(path, target):
    """Moves the facts in the old memory.json into memories, once, keeping their order (oldest id first). Settings key
    memories_moved goes in with them, so a removed fact never comes back. The file itself is left as it is.
    target is an open connection (its caller commits) or a MemoryStore. Returns how many facts moved."""
    if isinstance(target, MemoryStore):
        with closing(target.connect()) as conn, conn:
            return migrate_json(path, conn)
    if target.execute("SELECT 1 FROM settings WHERE key = 'memories_moved' AND value = '1'").fetchone():
        return 0
    moved = 0
    for fact in _old_facts(path):
        text = _clean(fact)
        if text and _insert(target, text, "", "talk") is not None:
            moved += 1
    target.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('memories_moved', '1')")
    return moved
