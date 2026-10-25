"""Mary's brain: what she knows about the resident, when to get help, when to offer to write a problem down, and the Gemini talk loop.

Uses the resident's own Gemini key (see assist.py). Safety checks run on this laptop before and
without Gemini. Mary only offers to write things down; she never writes to the incident log.
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import assist

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
INSTRUCTIONS = ROOT / "mary" / "instructions.md"

EMERGENCY_TEXT = {
    "medical": "Please press your call light or call out for staff right now. If it's serious, call 911.",
    "self_harm": "I'm really glad you told me. Please press your call light and tell a nurse how you're feeling, "
                 "or call or text 988 any time, day or night.",
}
OFFLINE_TEXT = "I'm sorry, I'm having trouble thinking right now, but I'm still right here with you."
OFFER_QUESTION = "Would you like me to write that down?"
NO_KEY = "No Gemini key."
NO_GEMINI = "Mary couldn't reach Gemini."

MAX_FACTS = 40
MAX_RECENT = 12
MAX_TURN_CHARS = 500

_I = re.IGNORECASE
_MEDICAL = re.compile("|".join([
    r"\b(?:can't|cannot|can not|couldn't)\s+(?:\w+\s+)?breathe\b",
    r"\b(?:trouble|difficulty|hard)\s+(?:breathing|to\s+breathe)\b",
    r"\bshort\s+of\s+breath\b",
    r"\bchest\s+(?:pains?|pressure|tight\w*|hurts?)\b",
    r"\b(?:fell|fallen)\b(?!\s+asleep)",
    r"\bon\s+the\s+floor\b",
    r"\b(?:bleeding|bled)\b|\bblood\b(?!\s+(?:pressure|sugar|tests?|work|draw|thinners?|count))",
    # Present tense only: many residents mention a stroke years ago.
    r"\bhaving\s+a\s+stroke\b|\b(?:it's|it\s+is|this\s+is)\s+a\s+stroke\b|\bstroke\s+(?:right\s+)?now\b",
    r"\bface\s+(?:is\s+|feels\s+|looks\s+)?(?:drooping|droopy)\b",
    r"\bslurred\s+speech\b|\bspeech\s+(?:is\s+|sounds\s+)?slurred\b",
    # Sudden only: residents with paralysis can't move their legs every day.
    r"\bsudden(?:ly)?\b[^.?!]*\b(?:can't|cannot|can\s+not|couldn't)\s+(?:move|feel|talk|speak|see)\b",
    r"\bside\s+of\s+my\s+(?:face|body)\s+(?:is\s+|feels\s+|went\s+|has\s+gone\s+)?(?:numb|weak|droop\w*)\b",
    r"\bchok(?:ing|ed|e)\b",
    r"\bpounding\s+headache\b",
]), _I)
_SELF_HARM = re.compile("|".join([
    r"\b(?:want|wish)(?:ed)?\s+to\s+die\b",
    r"\bkill\s+myself\b",
    r"\bend\s+my\s+life\b",
    r"\bhurt\s+myself\b",
    r"\bwish\s+i\s+(?:just\s+)?(?:wouldn'?t|didn'?t|would\s+not)\s+wake\s+up\b",
    r"\bbetter\s+off\s+dead\b",
]), _I)
_DECLINE = re.compile(
    r"\b(?:don'?t|do\s+not)\s+(?:write|put|note|log|report)(?:\s+(?:that|it|this))?(?:\s+down)?\b"
    r"|\bdon'?t\s+tell\s+anyone\b|\bkeep\s+(?:it|that|this)\s+between\s+us\b", _I)
_LAPSE_WORDS = re.compile(
    r"\b(nobody|no one|never|didn'?t|did not|wasn'?t|late|cold|missed|skipped|wait(ed|ing)?|ignored|left me|forgot|rude|yell\w*)\b", _I)
_ASKS = re.compile(r"write (that|it|this) down|note (that|it|this)|jot", _I)
_NAME = re.compile(r"\b(?:my name is|call me)\s+([A-Z][a-z]+)", _I)
_NOT_NAMES = {"back", "when", "if", "later", "please", "crazy", "maybe", "sometime", "tomorrow", "tonight", "today", "again", "not", "a", "an", "the"}
_TAG = re.compile(r"\[(remember|name):\s*([^\]]+)\]")


def load_instructions():
    """Mary's system prompt: the text after the first line that is exactly '---'."""
    raw = INSTRUCTIONS.read_text(encoding="utf-8")
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if line == "---":
            return "\n".join(lines[i + 1:]).strip()
    return raw.strip()


def default_memory_path():
    import server  # lazy: server will import mary
    return Path(server.DATA) / "mary" / "memory.json"


class Memory:
    """What Mary remembers: the resident's name, a few facts, and the last turns of the conversation."""

    def __init__(self, path=None):
        self.path = Path(path) if path else default_memory_path()
        self.name = ""
        self.facts = []
        self.recent = []
        self.pending_offer = None
        self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            name = data.get("name")
            facts = [f for f in data.get("facts", []) if isinstance(f, str) and f.strip()]
            recent = [{"role": t["role"], "text": t["text"], "at": str(t.get("at", ""))}
                      for t in data.get("recent", [])
                      if isinstance(t, dict) and t.get("role") in ("user", "model") and isinstance(t.get("text"), str)]
            offer = data.get("pending_offer")
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            return
        self.name = name if isinstance(name, str) else ""
        self.facts = facts[-MAX_FACTS:]
        self.recent = recent[-MAX_RECENT:]
        self.pending_offer = offer if isinstance(offer, dict) else None

    def add_fact(self, fact):
        """Returns True if the fact was new."""
        fact = " ".join(str(fact).split())
        if not fact or fact.lower() in (f.lower() for f in self.facts):
            return False
        self.facts.append(fact)
        self.facts = self.facts[-MAX_FACTS:]
        return True

    def add_turn(self, role, text):
        self.recent.append({"role": role, "text": text[:MAX_TURN_CHARS], "at": datetime.now().isoformat(timespec="seconds")})
        self.recent = self.recent[-MAX_RECENT:]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"name": self.name, "facts": self.facts, "recent": self.recent, "pending_offer": self.pending_offer}
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)


def _plain(text):
    return text.replace("’", "'").replace("‘", "'").replace("ʼ", "'")


def is_emergency(text):
    """'medical', 'self_harm' or None."""
    text = _plain(text)
    if _SELF_HARM.search(text):
        return "self_harm"
    if _MEDICAL.search(text):
        return "medical"
    return None


def is_decline(text):
    return bool(_DECLINE.search(_plain(text)))


def lapse_offer(text):
    """None, or {"incident": guess, "question": ...} when the resident describes a care lapse."""
    import server  # lazy: server will import mary
    text = _plain(text)
    guess = server.guess_incident(re.sub(r"\bfell asleep\b", "slept", text, flags=_I), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if (guess.get("wait_minutes") is not None or guess.get("never_came")
            or (guess.get("category") != "other"
                and (guess.get("severity") != "minor" or _LAPSE_WORDS.search(text)))):
        return {"incident": guess, "question": OFFER_QUESTION}
    return None


def _gemini_stream(body, api_key, model=""):
    """Yields the text pieces of Gemini's streamed answer. Raises on any network or API problem."""
    url = assist.ENDPOINT.replace(":generateContent", ":streamGenerateContent").format(model=model or assist.DEFAULT_MODEL) + "?alt=sse"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    with urllib.request.urlopen(req, timeout=20) as resp:
        for line in resp:
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                data = json.loads(line[5:].strip())
            except ValueError:
                continue
            for part in (data.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
                if part.get("text"):
                    yield part["text"]


def _body(text, memory, kind):
    system = load_instructions()
    lines = ([f"Name: {memory.name}"] if memory.name else []) + [f"- {f}" for f in memory.facts]
    if lines:
        system += "\n\nWhat you know about the resident:\n" + "\n".join(lines)
    if kind:
        system += (f"\n\nThe app has already told them: {EMERGENCY_TEXT[kind]} "
                   "Don't repeat it word for word; follow on calmly and kindly.")
    turns = list(memory.recent)
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    contents = [{"role": t["role"], "parts": [{"text": t["text"]}]} for t in turns]
    contents.append({"role": "user", "parts": [{"text": text}]})
    return {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 256}}


def reply(text, memory, api_key="", model="", on_text=None):
    """Mary's answer to what the resident said.

    Returns {text, emergency, offer, remembered, error, first_words_s, total_s}. on_text gets each
    spoken piece as it is ready. Nothing is written to the incident log.
    """
    start = time.monotonic()
    spoken = ""
    first_words_s = None

    def emit(piece, sep=False):
        nonlocal spoken, first_words_s
        if not piece:
            return
        if sep and spoken and not spoken[-1].isspace() and not piece[0].isspace():
            piece = " " + piece
        spoken += piece
        if first_words_s is None:
            first_words_s = time.monotonic() - start
        if on_text:
            on_text(piece)

    kind = is_emergency(text)
    if kind:
        emit(EMERGENCY_TEXT[kind])
    offer = None
    if is_decline(text):
        memory.pending_offer = None
    else:
        offer = None if kind == "self_harm" else lapse_offer(text)
        if offer:
            memory.pending_offer = offer
    m = _NAME.search(text)
    if m and m.group(1).lower() not in _NOT_NAMES:
        memory.name = m.group(1).capitalize()

    error = ""
    remembered = []
    if api_key:
        raw = held = ""
        streamed = False
        try:
            for chunk in _gemini_stream(_body(text, memory, kind), api_key, model):
                raw += chunk
                if held:
                    held += chunk
                    continue
                cut = chunk.find("[")
                safe = chunk if cut < 0 else chunk[:cut]
                if cut >= 0:
                    held = chunk[cut:]
                if safe:
                    emit(safe, sep=not streamed)
                    streamed = True
        except Exception:
            error = NO_GEMINI
        for tag, value in _TAG.findall(raw):
            if tag == "remember":
                if memory.add_fact(value):
                    remembered.append(" ".join(value.split()))
            elif value.strip():
                memory.name = value.strip()[:40]
        held = _TAG.sub("", held)
        cut = held.rfind("[")
        if cut >= 0 and "]" not in held[cut:]:
            held = held[:cut]
        if held.strip():
            emit(held, sep=not streamed)
            streamed = True
        if not streamed and not error:
            error = NO_GEMINI

    if not spoken.strip() and not kind:
        emit(OFFLINE_TEXT)
        if not api_key:
            error = NO_KEY
    if offer and not _ASKS.search(spoken):
        emit(offer["question"], sep=True)

    final = spoken.strip()
    memory.add_turn("user", text)
    if final:
        memory.add_turn("model", final)
    try:
        memory.save()
    except OSError:
        pass
    return {"text": final, "emergency": kind, "offer": offer, "remembered": remembered, "error": error,
            "first_words_s": first_words_s, "total_s": time.monotonic() - start}
