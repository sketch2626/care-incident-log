"""Mary's brain: what she knows about the resident, when to get help, when to offer to write a problem down, and the Gemini talk loop.

Uses the resident's own Gemini key (see assist.py). Safety checks run on this laptop before and
without Gemini. Mary only offers to write things down; she never writes to the incident log.
"""
import json
import os
import re
import sys
import time
import urllib.error
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
SAVED_TEXT = "All right, I've written that down for you, with today's date and time. Is there anything else on your mind?"
SAVE_FAILED_TEXT = "I'm sorry, I couldn't save that just now. Could we try again in a moment?"
NO_KEY = "No Gemini key."
NO_GEMINI = "Mary couldn't reach Gemini."
BAD_KEY = "Gemini didn't accept the key."
BAD_KEY_TEXT = "I'm sorry, my thinking key isn't working. Could someone check it in My info?"
GEMINI_DEADLINE_S = 20  # a whole answer; the socket timeout alone lets a trickling stream run on
OFFER_TTL_S = 600       # a "yes" to "write that down?" counts for ten minutes

# Her face (web/mary/face.js has the same list, in the same order). Gemini starts each reply with [mood: X].
MOODS = ("resting", "listening", "thinking", "talking", "happy", "laughing",
         "concerned", "sorry", "surprised", "sleepy", "alert")
COMPANIONS = {"mary": "Mary", "him": "Sam"}

MAX_FACTS = 40
MAX_RECENT = 12
MAX_TURN_CHARS = 500
MAX_FACT_CHARS = 200

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
# "call me" only counts at the start of a sentence or after "you can" and the like: "the aides call me honey" is not a name.
_NAME = re.compile(
    r"(?:\bmy name is"
    r"|(?:^\s*|[.!?]\s+|\b(?:you can|you may|please|just|i'd like you to|i like to be)\s+)call me)"
    r"\s+([A-Z][a-z]+)", _I)
_NOT_NAMES = {"back", "when", "if", "later", "please", "crazy", "maybe", "sometime", "tomorrow", "tonight", "today", "again", "not", "a", "an", "the",
              "names", "on", "for", "about", "anything", "whatever", "anytime",
              "at", "in", "to", "by", "after", "before", "now", "soon"}
_TAG = re.compile(r"\[(remember|name):\s*([^\]]+)\]")
_MOOD_TAG = re.compile(r"\[\s*mood\s*:\s*([^\[\]]*?)\s*\]", _I)
# A "[" so far that may still turn into a mood tag, so the stream waits for more before deciding.
_MOOD_OPEN = re.compile(r"\[\s*(?:m(?:o(?:o(?:d\s*(?::[^\[\]]{0,30})?)?)?)?)?$", _I)
_NAME_FILLER = re.compile(
    r"\b(?:(?:hi|hello|hey|good\s+(?:morning|afternoon|evening))(?:\s+(?:mary|sam))?"
    r"|um+|uh+|er+|hmm+|well|oh|yes|yeah|okay|ok|just|please|thanks|thank\s+you"
    r"|(?:my\s+)?name(?:\s+is|'s)"
    r"|(?:(?:you\s+)?can\s+|they\s+|people\s+|everyone\s+|everybody\s+)?calls?\s+me"
    r"|(?:it|that|this)(?:\s+is|'s)"
    r"|i(?:\s+am|'m))\b", _I)
# Words that are not a name: a first word like this means "nothing sensible"; later it ends the name.
_NAME_STOP = {"and", "but", "so", "because", "i", "my", "we", "the", "a", "an", "from", "in", "at", "here", "is",
              "was", "who", "what", "no", "nope", "nothing", "none", "nah", "sorry", "pardon", "huh", "why",
              "how", "where", "when", "don't", "dont", "can't", "cant", "not", "you", "me", "do", "does"}


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
            facts, recent = data.get("facts"), data.get("recent")  # null or odd values must not lose the name
            facts = [f for f in (facts if isinstance(facts, list) else []) if isinstance(f, str) and f.strip()]
            recent = [{"role": t["role"], "text": t["text"], "at": str(t.get("at", ""))}
                      for t in (recent if isinstance(recent, list) else [])
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
        fact = " ".join(str(fact).split())[:MAX_FACT_CHARS].rstrip()
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
        for attempt in range(5):  # Windows refuses the swap while another thread or a virus scan has the file open
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)


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


# "Yes" to "Would you like me to write that down?". When unsure this says no: writing to the log is never a guess.
_YES_PHRASE = re.compile(
    r"\b(?:yes|yeah|yea|yah|yep|yup|sure|okay|ok|all right|alright|absolutely|of course|definitely|certainly|please"
    r"|uh huh|mm hmm|mhm|mmhm|um hum|go ahead|do it|do that|write (?:that|it|this) down|put (?:that|it|this) down"
    r"|that(?:'d| would| will)? (?:be|sounds) (?:good|great|nice|fine|lovely|helpful)"
    r"|i(?:'d| would) (?:like|love) that|i would)\b", _I)
_YES_FILLER = re.compile(
    r"\b(?:oh|well|um+|uh+|hmm+|mm+|ah|so|then|now|too|and|do|thanks|thank you|very much|so much"
    r"|mary|sam|dear|honey|darling|friend|that|it|really|just)\b", _I)
_YES_LEAD = re.compile(
    r"^(?:(?:oh|well|um+|uh+|hmm+|mary|sam|thanks|thank you)\b[\s,.!]*)*"
    r"(?:yes|yeah|yea|yah|yep|yup|sure|okay|ok|all right|alright|absolutely|of course|definitely|certainly"
    r"|go ahead|please do|write (?:that|it|this) down|put (?:that|it|this) down)\b", _I)
# Anywhere in a reply: taking it back or putting it off.
_YES_HARD = re.compile(
    r"\b(?:maybe\s+(?:later|not|tomorrow|next)|hold on|never ?mind|forget (?:it|that)|changed my mind|second thought"
    r"|not (?:now|yet|today|tonight|right now|sure))\b", _I)
# Only in the first few words, or after a "but": the rest of a long yes may be the resident's own story.
_YES_WITHDRAW = re.compile(
    r"\b(?:later|wait|no|nope|nah|maybe|perhaps|don'?t|do not|dont|won'?t|stop|cancel|guess|suppose|not really)\b", _I)
_YES_DONT_ACT = re.compile(r"\b(?:don'?t|do not|dont)\s+(?:use|tell|share|send|say|name|mention|give)\b", _I)


def is_yes(text):
    """True for a clear yes: a short reply made only of yes-words ("yes please", "sure", "go ahead",
    "uh-huh", "that would be nice"), or any reply that starts with one ("Yes, and the food was cold too").
    Never for no / not now / maybe later / don't, a question, or a request to leave something out."""
    low = _plain(text).lower().strip()
    if not low or is_decline(low) or _YES_HARD.search(low):
        return False
    norm = " ".join(re.sub(r"[^a-z' ]+", " ", low).split())
    if not norm:
        return False
    if len(norm.split()) <= 8:
        found = []
        rest = _YES_PHRASE.sub(lambda m: found.append(m.group()) or " ", norm)
        rest = _YES_FILLER.sub(" ", rest)
        if found and not re.sub(r"[^a-z]", "", rest):
            return True
    if not _YES_LEAD.match(low) or "?" in low or _YES_DONT_ACT.search(low):
        return False
    head = " ".join(re.split(r"[.!?]", low)[0].replace(",", " ").split()[:4])
    if _YES_WITHDRAW.search(head):
        return False
    after = re.search(r"\b(?:but|except|however|although|though)\b(.*)", low)
    return not (after and _YES_WITHDRAW.search(after.group(1)))


def lapse_offer(text):
    """None, or {"incident": guess, "question": ..., "at": time} when the resident describes a care lapse."""
    import server  # lazy: server will import mary
    text = _plain(text)
    guess = server.guess_incident(re.sub(r"\bfell asleep\b", "slept", text, flags=_I), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if (guess.get("wait_minutes") is not None or guess.get("never_came")
            or (guess.get("category") != "other"
                and (guess.get("severity") != "minor" or _LAPSE_WORDS.search(text)))):
        return {"incident": guess, "question": OFFER_QUESTION, "at": time.time()}
    return None


def _offer_fresh(offer):
    """False for an offer with no usable time or older than OFFER_TTL_S: a 'yes' hours later is about something else."""
    at = offer.get("at")
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        return False
    return 0 <= time.time() - at <= OFFER_TTL_S


def _name_case(word):
    """'dorothy' -> 'Dorothy', "o'brien" -> "O'Brien", 'mary-ann' -> 'Mary-Ann'."""
    def cap(part):
        return part[:1].upper() + part[1:].lower()
    out = []
    for piece in word.split("-"):
        bits = piece.split("'")
        out.append("'".join(cap(b) for b in bits) if len(bits) > 1 and len(bits[0]) == 1 else cap(piece))
    return "-".join(out)


def name_from(text):
    """The name in the resident's answer to 'What would you like me to call you?', or '' if there isn't one."""
    text = _NAME_FILLER.sub(" ", _plain(str(text or "")))
    text = re.sub(r"[^\w'\-]+|[\d_]+", " ", text)
    words = []
    for w in text.split():
        w = re.sub(r"([-'])[-']+", r"\1", w).strip("'-")
        if not w:
            continue
        if w.lower() in _NAME_STOP:
            break
        words.append(w)
    name = " ".join(_name_case(w) for w in words[:3])
    return name if len(name) <= 40 else ""


class _ReplyStream:
    """Sorts Gemini's streamed text into words to speak, mood tags, and held-back tags.

    A [mood: x] tag is handled the moment its "]" arrives and the words after it flow on at once.
    Any other "[" starts a hold: everything from there to the end is kept, so a [remember:] or
    [name:] line is never spoken half-way. speak(piece, after_tag) and mood(value) are callbacks.
    """

    def __init__(self, speak, mood):
        self.speak, self.mood = speak, mood
        self.buf = self.held = ""
        self.after_tag = False

    def _say(self, piece):
        if not piece:
            return
        self.speak(piece, self.after_tag)
        if piece.strip():
            self.after_tag = False

    def feed(self, chunk):
        if self.held:
            self.held += chunk
            return
        self.buf += chunk
        while self.buf:
            cut = self.buf.find("[")
            if cut < 0:
                self._say(self.buf)
                self.buf = ""
                return
            if cut:
                self._say(self.buf[:cut])
                self.buf = self.buf[cut:]
            m = _MOOD_TAG.match(self.buf)
            if m:
                self.mood(m.group(1))
                self.buf = self.buf[m.end():]
                self.after_tag = True
                continue
            if _MOOD_OPEN.match(self.buf):
                return  # might still become a mood tag; wait for more
            self.held, self.buf = self.buf, ""
            return

    def finish(self):
        """The held-back text with every tag removed, and nothing from a half-finished tag."""
        held = _MOOD_TAG.sub(lambda m: self.mood(m.group(1)) or "", _TAG.sub("", self.held))
        self.buf = self.held = ""
        cut = held.rfind("[")
        if cut >= 0 and "]" not in held[cut:]:
            held = held[:cut]
        return held


def _gemini_stream(body, api_key, model=""):
    """Yields the text pieces of Gemini's streamed answer. Raises on any network or API problem.
    Stops yielding after GEMINI_DEADLINE_S, so a slow trickle ends with what was said."""
    url = assist.ENDPOINT.replace(":generateContent", ":streamGenerateContent").format(model=model or assist.DEFAULT_MODEL) + "?alt=sse"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    deadline = time.monotonic() + GEMINI_DEADLINE_S
    with urllib.request.urlopen(req, timeout=10) as resp:
        for line in resp:
            if time.monotonic() > deadline:
                return
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


def _key_refused(err):
    """True when Gemini turned the key down: 401/403, or a 400 whose message is about the API key.
    A 404 (wrong model name) and 5xx are not the key. Never puts the key or the body in a message."""
    if err.code in (401, 403):
        return True
    if err.code != 400:
        return False
    try:
        return "api key" in err.read(2048).decode("utf-8", "replace").lower()
    except Exception:
        return False


def _body(text, memory, kind, companion="mary"):
    system = load_instructions()
    if companion == "him":
        name = COMPANIONS["him"]
        first, newline, rest = system.partition("\n")
        system = (first + " You are a man, a kind and friendly gentleman." + newline + rest).replace("Mary", name)
    lines = ([f"Name: {memory.name}"] if memory.name else []) + [f"- {f}" for f in memory.facts]
    if lines:
        system += "\n\nWhat you know about the resident:\n" + "\n".join(lines)
    if not memory.name:
        system += ("\n\nYou don't know their name yet. If it fits naturally, warmly ask once what they'd like to be called; "
                   "when they tell you, add the line [name: First name].")
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


def reply(text, memory, api_key="", model="", on_text=None, companion="mary", on_mood=None, write=None):
    """Mary's answer to what the resident said.

    Returns {text, mood, emergency, gemini_alert, offer, logged, remembered, error, first_words_s, total_s}.
    on_text gets each spoken piece as it is ready. on_mood gets her mood as soon as it is known,
    once (a reply that is only a mood tag, no words, is corrected to "sorry" with a second call).
    Mood tags are never spoken or remembered. An offline emergency always means "alert";
    gemini_alert is True when only Gemini said alert.
    A pending offer lives exactly one turn. When the resident's next words are a clear yes (is_yes) and
    write is given, write(incident) saves it (returns the new id, raises on failure) and Mary says
    SAVED_TEXT without calling Gemini; logged is {id, category}. If saving fails she says SAVE_FAILED_TEXT
    and the offer stays pending for one more try. Otherwise logged is None. Without write nothing is saved.
    """
    start = time.monotonic()
    spoken = ""
    first_words_s = None
    mood = None
    gemini_mood_seen = gemini_alert = streamed = False
    if companion not in COMPANIONS:
        companion = "mary"

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

    def set_mood(value):
        nonlocal mood
        if value != mood:
            mood = value
            if on_mood:
                on_mood(value)

    def take_mood(value):
        """A mood tag from Gemini. Only the first counts, and never against an offline emergency."""
        nonlocal gemini_mood_seen, gemini_alert
        if gemini_mood_seen or kind:
            return
        gemini_mood_seen = True
        value = re.sub(r"[^a-z]", "", value.lower())
        if value not in MOODS or value in ("listening", "resting"):
            value = "talking"
        gemini_alert = value == "alert"
        set_mood(value)

    def speak(piece, after_tag=False):
        nonlocal streamed
        if after_tag and (not spoken or spoken[-1].isspace()):
            piece = piece.lstrip()  # the gap a removed tag leaves
        if piece:
            emit(piece, sep=not streamed)
            streamed = True

    prior = memory.pending_offer  # an offer lives exactly one turn
    memory.pending_offer = None
    if not (isinstance(prior, dict) and isinstance(prior.get("incident"), dict) and _offer_fresh(prior)):
        prior = None
    kind = is_emergency(text)
    said_yes = bool(prior) and is_yes(text)
    if kind:
        set_mood("alert")
        emit(EMERGENCY_TEXT[kind])
        if said_yes:
            memory.pending_offer = prior  # the emergency comes first; the offer waits one more turn
    confirmed = said_yes and not kind and write is not None
    logged = None
    offer = None
    if confirmed or (kind and said_yes):
        pass
    elif is_decline(text):
        memory.pending_offer = None
    else:
        offer = None if kind == "self_harm" else lapse_offer(text)
        if offer:
            memory.pending_offer = offer
    m = _NAME.search(_plain(text))
    if m and m.group(1).lower() not in _NOT_NAMES:
        memory.name = m.group(1).capitalize()

    error = ""
    remembered = []
    if confirmed:
        try:
            new_id = write(prior["incident"])
        except Exception:
            memory.pending_offer = prior  # so the next "yes" can try again
            set_mood("sorry")
            emit(SAVE_FAILED_TEXT)
        else:
            logged = {"id": new_id, "category": prior["incident"].get("category")}
            set_mood("talking")
            emit(SAVED_TEXT)
    elif api_key:
        raw = ""
        stream = _ReplyStream(speak, take_mood)
        try:
            for chunk in _gemini_stream(_body(text, memory, kind, companion), api_key, model):
                raw += chunk
                stream.feed(chunk)
        except urllib.error.HTTPError as e:
            error = BAD_KEY if _key_refused(e) else NO_GEMINI
        except Exception:
            error = NO_GEMINI
        for tag, value in _TAG.findall(raw):
            if tag == "remember":
                if memory.add_fact(value):
                    remembered.append(" ".join(value.split()))
            elif value.strip():
                memory.name = value.strip()[:40]
        tail = stream.finish()
        if tail.strip():
            speak(tail)
        if not streamed and not error:
            error = NO_GEMINI

    if not spoken.strip() and not kind:
        gemini_alert = False  # a bare "alert" tag with no words is not something to act on
        set_mood("sorry")
        emit(BAD_KEY_TEXT if error == BAD_KEY else OFFLINE_TEXT)
        if not api_key:
            error = NO_KEY
    elif mood is None:
        set_mood("talking")
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
    return {"text": final, "mood": mood, "emergency": kind, "gemini_alert": gemini_alert, "offer": offer,
            "logged": logged, "remembered": remembered, "error": error,
            "first_words_s": first_words_s, "total_s": time.monotonic() - start}
