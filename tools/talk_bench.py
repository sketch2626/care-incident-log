"""Talk bench: whole scripted talks, counted. Piece 1: load the talks and count what Mary or Sam said.

A talk is one file in bench/talks: ten to fifteen things a resident says in a row, for one companion. The counts below
look at her replies only, never the resident's lines: how often she uses the name, praise, pet names, repeated
sentences, the same opening words, stock comfort lines and "I was thinking of you" lines she can't mean.
Each list is a constant at the top, so it is easy to grow. Counts that are zero are left out of the lists.
"""
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import brain_bench as bb  # noqa: E402  (sets up the scratch folders, so it comes before anything of Mary's)

TALKS_DIR = ROOT / "bench" / "talks"
MIN_TURNS, MAX_TURNS = 10, 15

PRAISE = [
    "wonderful", "amazing", "fantastic", "impressive", "incredible", "awesome", "marvelous", "terrific", "remarkable",
    "great job", "good job", "nice job", "good for you", "well done", "way to go", "proud of you", "so proud",
    "that's great", "thats great", "that's so great", "how nice", "how lovely", "how sweet", "so thoughtful",
    "very thoughtful", "so sweet", "so kind of you", "what a thoughtful", "you did it", "you should be proud",
    "that's quite an accomplishment", "quite an accomplishment", "that's really something",
]
PET_NAMES = [
    "honey", "hon", "hun", "sweetie", "sweetheart", "sweet pea", "sugar", "dear", "dearie", "darling", "darlin",
    "darlin'", "baby", "babe", "kiddo", "young man", "young lady", "love",
]
PET_OPENERS = ["my", "oh", "well", "hey", "hi", "now", "there", "thanks"]  # A pet name may follow these directly
STOCK = [
    "i'm here for you", "here for you", "i'm here", "i'm listening", "whatever you want to talk about",
    "whatever you'd like to talk about", "i'll be right here", "right here whenever", "ready whenever you're ready",
    "whenever you're ready", "whenever you need", "anything else", "how can i help", "what can i do for you",
    "what's on your mind", "what would you like to talk about", "tell me more", "that's a good question",
    "that's a great question", "that must be so hard", "that must be hard", "i hear you", "i understand",
]
MADE_UP = [
    "i was just thinking", "i was thinking about", "i've been thinking about", "i have been thinking about",
    "been thinking about you", "thinking of you", "thought of you", "i keep thinking about", "i was remembering",
    "i've been wondering", "i was wondering how you", "you've been on my mind", "you were on my mind", "i missed you",
    "i've missed you", "reminded me of you", "i was just remembering", "been looking forward to",
]
SAME_SENTENCE = 0.85  # How alike two long sentences must be to count as the same
LONG_SENTENCE = 5  # Words a sentence needs before "nearly the same" can apply
PUNCT = ',.!?;:"-–—…()'


def load_talks(folder=None):
    """Every talk in the folder, sorted by file name. Raises BenchError naming the file when one is wrong."""
    folder = Path(folder) if folder else TALKS_DIR
    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    if not files:
        raise bb.BenchError(f"{folder}: no talk files (*.json) found.")
    talks, seen = [], set()
    for path in files:
        talk = _load_one(path)
        if talk["id"] in seen:
            raise bb.BenchError(f"{path.name}: the id {talk['id']} is used by another talk.")
        seen.add(talk["id"])
        talks.append(talk)
    return talks


def _load_one(path):
    """One talk file, checked."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise bb.BenchError(f"{path.name}: can't read this file as JSON ({e}).")
    if not isinstance(raw, dict):
        raise bb.BenchError(f"{path.name}: a talk must be an object.")
    if "mode" in raw:
        raise bb.BenchError(f"{path.name}: a talk has no mode key.")
    if raw.get("companion") not in ("mary", "sam"):
        raise bb.BenchError(f"{path.name}: companion must be mary or sam.")
    title, also = raw.pop("title", None), raw.pop("also_called", [])
    if not isinstance(title, str) or not title.strip():
        raise bb.BenchError(f"{path.name}: a talk needs a title.")
    if not isinstance(also, list) or not all(isinstance(a, str) and a.strip() for a in also):
        raise bb.BenchError(f"{path.name}: also_called must be a list of words.")
    case = bb.validate_case(raw, path.name)
    if not MIN_TURNS <= len(case["turns"]) <= MAX_TURNS:
        raise bb.BenchError(f"{path.name}: a talk needs {MIN_TURNS} to {MAX_TURNS} turns, not {len(case['turns'])}.")
    case["title"], case["also_called"] = title, also
    return case


def _plain(text):
    """Lowercase with curly quotes made straight."""
    text = str(text).lower()
    for curly in ("’", "‘", "ʼ"):
        text = text.replace(curly, "'")
    return text


def _words(text):
    """The words of a text, normalized, without punctuation."""
    return re.findall(r"[a-z0-9']+", bb.normalize(text))


def _phrase_counts(replies, phrases):
    """{phrase: uses}, whole words only. A longer phrase that holds a shorter one counts once, as the longer."""
    found = {}
    for reply in replies:
        text, taken = _plain(reply), []
        for phrase in sorted(phrases, key=len, reverse=True):
            for m in re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text):
                if any(m.start() < b and a < m.end() for a, b in taken):
                    continue
                taken.append((m.start(), m.end()))
                found[phrase] = found.get(phrase, 0) + 1
    return found


def _name_counts(replies, names):
    """(uses, replies holding one) of the name or its other names; a possessive counts."""
    names = sorted((_plain(n).strip() for n in names if n and n.strip()), key=len, reverse=True)
    if not names:
        return 0, 0
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in names) + r")(?:'s)?(?!\w)")
    per_reply = [len(pattern.findall(_plain(r))) for r in replies]
    return sum(per_reply), sum(1 for n in per_reply if n)


def _pet_ok(word, before, after):
    """True when this use of the word is addressing the person."""
    before, after = before.rstrip(), after.lstrip()
    last = re.search(r"(\w+)$", before)
    if last and last.group(1) in PET_OPENERS:
        if word == "dear" and last.group(1) == "oh":
            return False  # "oh dear" is worry, not a pet name
        return True
    if word == "love":
        return False if not before.endswith(",") else (not after or after[0] in ".!?")
    stands_before = not before or before[-1] in PUNCT
    stands_after = not after or after[0] in PUNCT
    return stands_before and stands_after


def _pet_counts(replies):
    """{pet name: uses} where the word is used to address the person."""
    found = {}
    for reply in replies:
        text = _plain(reply)
        for word in PET_NAMES:
            tail = r"(?![\w'])" if word == "darlin" else r"(?!\w)"
            for m in re.finditer(r"(?<![\w'])" + re.escape(word) + tail, text):
                if _pet_ok(word, text[:m.start()], text[m.end():]):
                    found[word] = found.get(word, 0) + 1
    return found


def _sentences(reply):
    """The sentences of a reply, as (shown text, words), three words or more."""
    out = []
    for part in re.split(r"(?<=[.!?])\s+", reply.strip()):
        words = _words(part)
        if len(words) >= 3:
            out.append((part.strip(), words))
    return out


def _same_sentence(a, b):
    """True when two word lists are the same sentence, or nearly so when both are long."""
    if a == b:
        return True
    if len(a) >= LONG_SENTENCE and len(b) >= LONG_SENTENCE:
        return difflib.SequenceMatcher(None, " ".join(a), " ".join(b)).ratio() >= SAME_SENTENCE
    return False


def _repeats(replies):
    """[{"sentence", "times"}] for each sentence said twice or more across the talk."""
    groups = []  # [shown, words, times]
    for reply in replies:
        for shown, words in _sentences(reply):
            for g in groups:
                if _same_sentence(g[1], words):
                    g[2] += 1
                    break
            else:
                groups.append([shown, words, 1])
    return [{"sentence": g[0], "times": g[2]} for g in groups if g[2] >= 2]


def _openers(replies, names):
    """[{"opener", "times"}] where two or more replies start with the same three words (a leading name dropped)."""
    name_words = [_words(n) for n in names if n and n.strip()]
    groups = {}
    for reply in replies:
        words = _words(reply)
        for nw in sorted(name_words, key=len, reverse=True):
            if nw and words[:len(nw)] == nw:
                words = words[len(nw):]
                break
        if len(words) >= 3:
            groups.setdefault(" ".join(words[:3]), 0)
            groups[" ".join(words[:3])] += 1
    return [{"opener": k, "times": n} for k, n in groups.items() if n >= 2]


def count_talk(replies, name="", also_called=()):
    """The counts for one talk, from her replies only (a list of strings, blanks allowed)."""
    replies = [r if isinstance(r, str) else "" for r in replies]
    names = [name, *also_called]
    spoken = [r for r in replies if r.strip()]
    uses, in_replies = _name_counts(replies, names)
    praise, stock = _phrase_counts(replies, PRAISE), _phrase_counts(replies, STOCK)
    made_up, pets = _phrase_counts(replies, MADE_UP), _pet_counts(replies)
    repeats, openers = _repeats(replies), _openers(spoken, names)
    asked = [bb.question_count(r) for r in spoken]
    sizes = [len(r.split()) for r in spoken]
    return {
        "replies": len(replies), "blank": len(replies) - len(spoken),
        "name_uses": uses, "name_replies": in_replies,
        "praise": praise, "praise_total": sum(praise.values()),
        "pet_names": pets, "pet_total": sum(pets.values()),
        "repeats": repeats, "repeat_total": sum(r["times"] - 1 for r in repeats),
        "openers": openers, "opener_total": sum(o["times"] - 1 for o in openers),
        "stock": stock, "stock_total": sum(stock.values()),
        "made_up": made_up, "made_up_total": sum(made_up.values()),
        "questions_avg": round(sum(asked) / len(asked), 1) if asked else 0.0,
        "questions_max": max(asked, default=0),
        "ended_on_question": sum(1 for r in spoken if r.rstrip().endswith("?")),
        "words_avg": round(sum(sizes) / len(sizes)) if sizes else 0,
        "words_max": max(sizes, default=0),
    }
