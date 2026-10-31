"""Mary's brain: what she knows about the resident, when to get help, when to offer to write a problem down, and the Gemini talk loop.

Uses the resident's own Gemini key (see assist.py). Safety checks run on this laptop before and
without Gemini. Mary only offers to write things down; she never writes to the incident log.
"""
import base64  # M4a: see_image
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
import memory_core  # M9c

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
INSTRUCTIONS = ROOT / "mary" / "instructions.md"

# M4a: the same three numbers and words in app.js (spokenNumbers), for what her voice says; captions keep the digits
SPOKEN_NUMBERS = ((re.compile(r"\b988\b"), "nine, eight, eight"), (re.compile(r"\b911\b"), "nine one one"),
                  (re.compile(r"\b838[- ]?255\b"), "eight three eight, two five five"))
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
# Phrases that hold an emergency word but mean something else. Cut out before the check, so a real
# "bleeding" or "can't breathe" in the same sentence still counts.
_BENIGN = re.compile("|".join([
    r"\b(?:took|take|taking|taken|drew|draw|drawing|drawn)\s+(?:some\s+(?:of\s+my\s+)?|my\s+)blood\b",  # a blood test
    r"\bblood\s+(?:was\s+|is\s+|got\s+|being\s+)?(?:drawn|taken)\b",
    r"\b(?:died|dead|death)\s+(?:of|from)\s+(?:a\s+|his\s+|her\s+)?heart\s+attack\b",  # someone else, long ago
    r"\bheart\s+attack\s+(?:survivors?|years?\s+ago|(?:in|back\s+in)\s+(?:19|20)\d\d)\b",
    r"\bseizure\s+(?:meds?|medications?|medicine|disorder|history|pads?|precautions?)\b|\b(?:for|from)\s+(?:my|the|his|her)\s+seizures?\b",
    r"\bpass(?:ed|es|ing)?\s+out\s+(?:the|some)\s+(?:meds|medications?|medicine|pills|trays?|snacks?|mail|food|cups?|papers?|menus?|forms?)\b",  # handing things out
    # A standing complaint ("they give me too many pills"); "they gave me too many pills" may be an overdose, so it still alarms.
    r"\b(?:give|gives|giving|have|has|take|takes|taking)\s+(?:me\s+)?too\s+many\s+(?:pills|tablets|meds)\b",
]), _I)
_MEDICAL = re.compile("|".join([
    r"\b(?:can't|cannot|can not|couldn't)\s+(?:\w+\s+)?breathe\b",
    r"\b(?:can't|cannot|can not|couldn't)\s+(?:catch|get)\s+(?:my|a)\s+breath\b",
    r"\b(?:trouble|difficulty|hard)\s+(?:breathing|to\s+breathe)\b",
    r"\bshort\s+of\s+breath\b",
    r"\bchest\s+(?:pains?|pressure|tight\w*|hurts?)\b",
    r"\b(?:fell|fallen)\b(?!\s+asleep)",
    # A person on the floor; a lunch tray or a call light on the floor is not an emergency.
    r"\b(?:i'?m|i\s+am|i\s+was|i'?ve\s+been|i\s+have\s+been|i\s+ended\s+up)\s+(?:(?:lying|laying|stuck|sitting)\s+)?on\s+the\s+floor\b",
    r"\b(?:found|left)\s+me\s+(?:\w+\s+)?on\s+the\s+floor\b|\b(?:lying|laying)\s+on\s+the\s+floor\b",
    r"\b(?:he|she|someone|somebody|roommate|neighbor)(?:'s)?\s+(?:is\s+|was\s+)?(?:lying\s+|laying\s+|stuck\s+)?on\s+the\s+floor\b",
    r"\b(?:bleeding|bled)\b|\bblood\b(?!\s+(?:pressure|sugar|tests?|work|draw|thinners?|count))",
    # Present tense only: many residents mention a stroke years ago.
    r"\bhaving\s+a\s+stroke\b|\b(?:it's|it\s+is|this\s+is)\s+a\s+stroke\b|\bstroke\s+(?:right\s+)?now\b",
    r"\bface\s+(?:is\s+|feels\s+|looks\s+)?(?:drooping|droopy)\b",
    r"\bslurred\s+speech\b|\bspeech\s+(?:is\s+|sounds\s+)?slurred\b",
    # Sudden only: residents with paralysis can't move their legs every day.
    r"\bsudden(?:ly)?\b[^.?!]*\b(?:can't|cannot|can\s+not|couldn't)\s+(?:move|feel|talk|speak|see)\b",
    r"\bside\s+of\s+my\s+(?:face|body)\s+(?:is\s+|feels\s+|went\s+|has\s+gone\s+)?(?:numb|weak|droop\w*)\b",
    r"\bchok(?:ing|ed|e)\b",
    r"\bpounding\s+headache\b|\bhead(?:'s|\s+is|\s+feels)?\s+pounding\b|\bpounding\s+(?:in|inside)\s+(?:my\s+)?head\b|\bdysreflexia\b",
    # A call for help counts only as the whole utterance ("Help!", "please help me now"); "can you help me find my glasses" does not.
    r"^\W*(?:(?:mary|sam)\W+)?(?:please\W+)?(?:help\W*){1,3}(?:me\W*)?(?:(?:please|now|right\s+now|mary|sam)\W*)*$",
    r"(?:^|[.!?;,]\s*|\b(?:oh|hey|please)\s+)(?:some|any)(?:body|one)[\s,]+(?:please\s+)?help\b",
    r"\bi\s+(?:really\s+|desperately\s+)?need\s+help\s+(?:right\s+)?(?:now|away)\b",
    r"\bheart\s+attack\b",
    r"\b(?:pass(?:ed|ing)?|black(?:ed|ing)?)\s+out\b",
    r"\bfaint(?:ed|ing)\b|\b(?:feel|felt|feeling|going\s+to|gonna|about\s+to)\s+(?:(?:very|so|really|a\s+bit|a\s+little|kind\s+of|kinda)\s+)?faint\b",
    r"\bseizures?\b|\bhaving\s+a\s+fit\b",
    r"\boverdos(?:e|ed|ing)\b|\btoo\s+many\s+(?:pills|tablets|meds)\b",
    r"\b(?:hit|bumped|banged|knocked)\s+my\s+head\b",
    r"\b(?:slipped|slid|sliding|slipping)\s+out\s+of\s+(?:my\s+|the\s+)?(?:wheel\s*chair|chair|bed)\b",
    r"\blips\s+(?:(?:are|is|look|looks|turned|turning|went|going|getting|got|have\s+turned)\s+)?(?:blue|bluish|purple)\b|\bblue\s+lips\b",
]), _I)
_SELF_HARM = re.compile("|".join([
    r"\b(?:want|wish)(?:ed)?\s+to\s+die\b|\bwanna\s+die\b",
    r"\bend\s+it\s+all\b",
    r"\bwish\s+(?:i|that\s+i)\s+(?:was|were)\s+dead\b",
    # "I don't want to live here" is about the facility, not about dying.
    r"\b(?:don'?t|do\s+not)\s+(?:even\s+)?want\s+to\s+(?:live|be\s+alive)\b(?!\s+(?:here|there|in|at|with|on|near|alone|by|another)\b)",
    r"\bsuicidal\b|\bcommit(?:ting)?\s+suicide\b",
    r"\bno\s+(?:reason|point)\s+(?:to\s+live|(?:in\s+)?living)\b",
    r"\bkill\s+myself\b",
    r"\bend\s+my\s+life\b",
    r"\bhurt\s+myself\b",
    r"\bwish\s+i\s+(?:just\s+)?(?:wouldn'?t|didn'?t|would\s+not)\s+wake\s+up\b",
    r"\bbetter\s+off\s+dead\b",
]), _I)
_DECLINE = re.compile(
    r"\b(?:don'?t|do\s+not)\s+(?:write|put|note|log|report)(?:\s+(?:that|it|this))?(?:\s+down)?\b"
    r"|\bdon'?t\s+tell\s+anyone\b|\bkeep\s+(?:it|that|this)\s+between\s+us\b", _I)
# Clear signs of a care problem, even when the log has no category for it (guess_incident says "other"):
# someone hurt or threatened them, took their things, care that was never done, broken equipment, a sore.
_LAPSE_CLEAR = "|".join([
    r"\b(?:nurse|aide|cna|staff|worker|orderly|someone|somebody|they|he|she|man|woman|lady|guy|roommate|resident|visitor)\s+(?:\w+\s+)?"
    r"(?:hit|slapped|punched|kicked|pushed|shoved|grabbed|pinched|choked|hurt|threatened)\s+me\b",
    r"\b(?:i\s+(?:was|got)|been|get)\s+(?:hit|slapped|punched|kicked|shoved|pushed|pinched|grabbed)\b",
    r"\bthreaten(?:ed|s|ing)?\b",
    r"\b(?:stole|stolen|steal(?:s|ing)?)\b",
    r"\b(?:they|he|she|someone|somebody|staff|nurse|aide|cna|worker|roommate)\s+(?:\w+\s+){0,2}(?:took|take|takes|taking|taken)\s+(?:away\s+)?(?:my|our)\s+"
    r"(?:phone|cell|tablet|laptop|tv|television|radio|remote|money|wallet|purse|ring|watch|jewelry|glasses|dentures|hearing\s+aids?"
    r"|clothes|things|stuff|belongings|property|wheelchair|walker|cane|blanket|pillow|charger)\b",
    r"\b(?:haven'?t|hasn'?t|wasn'?t|weren'?t|isn'?t|aren'?t)\s+(?:been\s+|being\s+)?"
    r"(?:given|turned|changed|emptied|fed|washed|bathed|cleaned|repositioned|checked|moved)\b",
    r"\b(?:nobody|no\s+one)\s+(?:ever\s+)?(?:\w+\s+)?(?:gave|emptied|changed|turned|fed|washed|bathed|cleaned|repositioned|checked|moved|helped)\b",
    r"\b(?!hearts?\b)\w+(?:'s|\s+(?:is|are|was|were|still|got))\s+(?:\w+\s+)?broken\b",  # not "my heart is broken"
    r"\b(?:bed|pressure)\s*sores?\b|\b(?:a|new|open)\s+sore\b(?!\s+(?:throat|back|neck|arm|leg|knee|shoulder|muscles?|spot))",
])
_LAPSE_CLEAR_RE = re.compile(_LAPSE_CLEAR, _I)
_LAPSE_WORDS = re.compile(
    r"\b(nobody|no one|never|didn'?t|did not|wasn'?t|late|cold|missed|skipped|wait(ed|ing)?|ignored|left me|forgot|rude|yell\w*)\b|"
    + _LAPSE_CLEAR, _I)
# Her own words offering to write it down: "write that down", or "would you like me to write that down" and the like.
_ASKS = re.compile(
    r"write (that|it|this) down|note (that|it|this)|jot"
    r"|\b(?:(?:would|do)\s+you\s+(?:like|want)\s+me\s+to|(?:want|like)\s+me\s+to|shall\s+i|should\s+i|can\s+i|could\s+i|may\s+i|i\s+can|i\s+could)\s+"
    r"(?:write|note|jot|put|record|log)\s+(?:that|it|this|these|those|what|all|down|a\s+note)\b", _I)
# "call me" only counts at the start of a sentence or after "you can" and the like: "the aides call me honey" is not a name.
# M4a: also after "but", "and", "so" or a comma, and "everybody calls me X"; learn_name() lets a "call me" name win.
_NAME = re.compile(
    r"(?:\bmy name is"
    r"|(?:^\s*|[.!?,]\s+|\b(?:you can|you may|please|just|i'd like you to|i like to be|but|and|so)\s+)call me"
    r"|\b(?:everybody|everyone|folks|my friends|my family)\s+calls?\s+me)"
    r"\s+([A-Z][a-z]+)", _I)
# M9c: "don't call me Bob" and "stop calling me that" turn a name down; they never offer one.
_NAME_REFUSED = re.compile(r"\b(?:(?:don'?t|dont|do\s+not|never)\s+(?:(?:you|ever)\s+)*call|(?:stop|quit)\s+calling)"
                           r"\s+me\s+([^\W\d_]+)", _I)
_FORGET_MY_NAME = re.compile(r"(?<!\bi )\bforget my name\b", _I)
_NOT_NAMES = {"back", "when", "if", "later", "please", "crazy", "maybe", "sometime", "tomorrow", "tonight", "today", "again", "not", "a", "an", "the",
              "names", "on", "for", "about", "anything", "whatever", "anytime",
              "at", "in", "to", "by", "after", "before", "now", "soon",
              "honey", "sugar", "sweetie", "sweetheart", "darling", "dear", "hon"}  # M4a: a pet name isn't their name
_TAG = re.compile(r"\[(remember|name):\s*([^\]]+)\]")
_BRACKETS = re.compile(r"\[[^\]]*\]?")  # M4a: any bracketed note, or one cut off at the end
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


def load_instructions(companion=None):  # M9b: one block per companion
    """The system prompt: the text after the first line that is exactly '---'.
    With no companion, all of it (markers included). With one, that companion's block plus the Both block."""
    raw = INSTRUCTIONS.read_text(encoding="utf-8")
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if line == "---":
            text = "\n".join(lines[i + 1:]).strip()
            break
    else:
        text = raw.strip()
    if companion is None:
        return text
    # M9b: split on the marker lines (=== Mary ===, === Sam ===, === Both ===); no markers: the whole text
    markers = {"=== Mary ===": "mary", "=== Sam ===": "sam", "=== Both ===": "both"}
    blocks, current = {}, None
    for line in text.splitlines():
        if line in markers:
            current = markers[line]
            blocks[current] = []
        elif current:
            blocks[current].append(line)
    if len(blocks) < 3:
        return text
    mine = "\n".join(blocks["sam" if companion == "him" else "mary"]).strip()
    return (mine + "\n\n" + "\n".join(blocks["both"]).strip()).strip()


def default_memory_path():
    import server  # lazy: server will import mary
    return Path(server.DATA) / "mary" / "memory.json"


def _forget_waiting(pending):  # M9c
    """pending if it is a forget still waiting for its yes, None when it is odd or older than FORGET_YES_S."""
    try:
        age = (datetime.now() - datetime.fromisoformat(pending["at"])).total_seconds()
        about = str(pending["about"]).strip()
    except (TypeError, ValueError, KeyError):
        return None
    return pending if about and 0 <= age <= memory_core.FORGET_YES_S else None


class Memory:
    """What Mary remembers: the resident's name, a few facts, and the last turns of the conversation."""

    def __init__(self, path=None):
        self.path = Path(path) if path else default_memory_path()
        self.name = ""
        self.name_forgotten = False  # M9c: they asked her not to use a name; only a name they offer clears it
        self.facts = []
        self.recent = []
        self.pending_offer = None
        self.store = None  # M9c: a memory_core.MemoryStore; server sets it. None keeps the old facts list.
        self.pending_forget = None  # M9c: "forget about my son" waiting for its yes: {"about", "at"}
        self.scrubbed = False  # M9c: True once something was truly forgotten through this object
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
            pending_forget = data.get("pending_forget")  # M9c
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            return
        self.name = name if isinstance(name, str) else ""
        self.name_forgotten = data.get("name_forgotten") is True and not self.name  # M9c
        self.facts = facts[-MAX_FACTS:]
        self.recent = recent[-MAX_RECENT:]
        self.pending_offer = offer if isinstance(offer, dict) else None
        self.pending_forget = _forget_waiting(pending_forget)  # M9c

    def add_fact(self, fact, kind="", source="talk"):
        """Returns True if the fact was new."""
        if self.store is not None:  # M9c: kind and source only mean something in the store
            return self.store.add(fact, kind, source) is not None
        fact = " ".join(str(fact).split())[:MAX_FACT_CHARS].rstrip()
        if not fact or fact.lower() in (f.lower() for f in self.facts):
            return False
        self.facts.append(fact)
        self.facts = self.facts[-MAX_FACTS:]
        return True

    def add_turn(self, role, text):
        self.recent.append({"role": role, "text": text[:MAX_TURN_CHARS], "at": datetime.now().isoformat(timespec="seconds")})
        self.recent = self.recent[-MAX_RECENT:]

    def scrub(self, forgotten, about="", name=""):  # M9c
        """Drops every turn that carries what was just forgotten, with her answer right after any such resident turn,
        and a waiting note offer that carries it. An incident already saved in the log stays: that is evidence.
        name: a turn holding this name as a whole word, in any case, goes too."""
        def holds(words):
            return memory_core.carries(words, forgotten, about) or memory_core.says_name(words, name)

        kept = []
        answer_goes = False
        for turn in self.recent:
            if holds(turn["text"]) or (answer_goes and turn["role"] == "model"):
                answer_goes = turn["role"] == "user"
                continue
            answer_goes = False
            kept.append(turn)
        self.recent = kept
        incident = self.pending_offer.get("incident") if isinstance(self.pending_offer, dict) else None
        if isinstance(incident, dict) and holds(" ".join(str(v) for v in incident.values())):
            self.pending_offer = None
        self.scrubbed = True

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.pending_forget = _forget_waiting(self.pending_forget)  # M9c
        data = {"name": self.name, "name_forgotten": self.name_forgotten, "facts": self.facts, "recent": self.recent, "pending_offer": self.pending_offer,
                "pending_forget": self.pending_forget}
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            for attempt in range(5):  # Windows refuses the swap while another thread or a virus scan has the file open
                try:
                    os.replace(tmp, self.path)
                    return
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05)
        finally:  # M9c: a failed save must not leave her talk history lying in a second file
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def _plain(text):
    return text.replace("’", "'").replace("‘", "'").replace("ʼ", "'")


def spoken_numbers(text):  # M4a: a voice left alone can say 988 as "nine eighty-eight"
    """text with the crisis numbers written out digit by digit, for a voice to read."""
    for number, words in SPOKEN_NUMBERS:
        text = number.sub(words, text)
    return text


def is_emergency(text):
    """'medical', 'self_harm' or None."""
    text = _BENIGN.sub(" ", _plain(text))
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


def _guess(text):
    import server  # lazy: server will import mary
    text = _plain(text)
    return server.guess_incident(re.sub(r"\bfell asleep\b", "slept", text, flags=_I), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def _offer(guess):
    return {"incident": guess, "question": OFFER_QUESTION, "at": time.time()}


def lapse_offer(text):
    """None, or {"incident": guess, "question": ..., "at": time} when the resident describes a care lapse."""
    text = _plain(text)
    guess = _guess(text)
    if (guess.get("wait_minutes") is not None or guess.get("never_came") or _LAPSE_CLEAR_RE.search(text)
            or (guess.get("category") != "other"
                and (guess.get("severity") != "minor" or _LAPSE_WORDS.search(text)))):
        return _offer(guess)
    return None


def _asks_to_write(spoken):
    """True when one sentence of her answer is a question that offers to write it down."""
    return any(s.rstrip().endswith("?") and _ASKS.search(s) for s in re.findall(r"[^.!?]+[.!?]*", spoken))


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
    text = _plain(str(text or ""))
    calls = list(re.finditer(r"\bcalls?\s+me\b", text, _I))  # M4a: "Andrew, but call me Andy" is Andy
    if calls:
        nick = name_from(text[calls[-1].end():])
        if nick and nick.lower() not in _NOT_NAMES:
            return nick
    text = _NAME_FILLER.sub(" ", text)
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


def learn_name(memory, text):  # M4a: Normal talk and Live (/api/mary/heard) both learn a name this way
    """Sets memory.name from "my name is X" or "call me X" in what the resident said. A "call me" name wins over
    "my name is" ("my name is Andrew but call me Andy" is Andy). Returns the name, or "" when there was none."""
    found = ""
    said = _plain(str(text or ""))
    refused = list(_NAME_REFUSED.finditer(said))  # M9c: "my name is Bob, but stop calling me Bob" offers no name
    words = {r.group(1).lower() for r in refused}
    that_at = max((r.start() for r in refused if r.group(1).lower() in ("that", "it")), default=-1)
    for m in _NAME.finditer(said):
        word = m.group(1)
        if word.lower() in _NOT_NAMES or word.lower() in words or m.start() < that_at:
            continue
        if not found or "call" in m.group(0)[:m.start(1) - m.start(0)].lower():
            found = word.capitalize()
    if found:
        memory.name = found
        memory.name_forgotten = False  # M9c
    return found


def asks_no_name(text):  # M9c
    """True when they asked her to forget their name or stop calling them it: "don't call me Bob", "forget my name".
    Not "don't call me late", and not "I forget my name sometimes"."""
    said = _plain(str(text or ""))
    return bool(_FORGET_MY_NAME.search(said)) or any(
        r.group(1)[0].isupper() or r.group(1).lower() in ("that", "it") for r in _NAME_REFUSED.finditer(said))


def clean_name(name):  # M4a: Live's set_their_name tool
    """The name Live passed to set_their_name, cleaned like a spoken name, or "" if it isn't a name."""
    name = name_from(str(name or "").strip()[:80])
    return "" if not name or name.lower() in _NOT_NAMES else name


# M9c: said out loud or typed, "remember that..." is the resident's own wish, so it is marked as theirs.
_ASKS_TO_REMEMBER = re.compile(r"\b(?:remember\s+(?:that|this)|please\s+remember|don'?t\s+forget)\b", _I)
# M9c: with no Gemini only these exact phrases reach her memory, so "I forget about my pills" and "don't forget that"
# never do. Nothing but please or her name may stand around them.
_ONLY_LEAD = r"(?:(?:please|mary|sam)[\s,.!]+)*"
_ONLY_TAIL = r"(?:[\s,.!]+(?:please|mary|sam))*[\s.!?]*"
_OFFLINE_RECALL = re.compile(rf"{_ONLY_LEAD}what do you remember about me{_ONLY_TAIL}", _I)
_OFFLINE_FORGET = re.compile(rf"{_ONLY_LEAD}forget (?:that|about my ([^,.!?]+?)){_ONLY_TAIL}", _I)
_OFFLINE_FORGET_NAME = re.compile(  # M9c
    rf"{_ONLY_LEAD}(?:forget my name|(?:don'?t|do not) call me that|stop calling me (?:that|([^\W\d_]+)))"
    rf"(?:\s+any ?more)?{_ONLY_TAIL}", _I)
OFFLINE_SUMMARY_ITEMS = 5
NOTHING_SAVED_TEXT = "I don't have anything saved about you yet."
FORGOT_TEXT = "All right, I've forgotten that."
NAME_FORGOTTEN_TEXT = "All right, I won't use a name."  # M9c
NOTHING_TO_FORGET_TEXT = "I don't have anything saved about that."
OFFER_DROPPED_TEXT = "All right, I won't write that down."
FORGET_ASK_TEXT = "Should I forget everything about your {}?"
FORGET_FAILED_TEXT = "I couldn't do that just now. Please say yes again in a little while."
RECALL_NOTE = "Newer dates win when two disagree. Only say what is here; never make up a memory."
RECALL_EMPTY_NOTE = "Nothing saved about that. Say so; don't guess."
FORGET_EMPTY_NOTE = "Nothing saved matches that. Say so kindly, in one line."
FORGET_OFFER_NOTE = "They meant the note you just offered to write. Nothing was written and nothing was forgotten."
FORGET_ASK_NOTE = ("Ask in one line whether to forget everything about this, and call forget_memory again with confirmed "
                   "true if they say yes.")
FORGOT_NOTE = "Done. Say so in one line, and never bring it up again, even if it came up earlier in this talk."
NAME_FORGOTTEN_NOTE = "Done. Say so in one line. Don't use a name from now on, and don't ask for one."  # M9c
NAME_FORGOTTEN_SYSTEM = "They asked you not to use a name. Don't ask for one."  # M9c
MEMORY_BROKEN_NOTE = "Your memory can't be reached just now. Say so kindly; don't guess."
MEMORY_TOOLS = [  # M9c: her long memory, for Normal talk and Live
    {"name": "recall",
     "description": ("Look up what the resident has told you before. Call this when they mention a person, a place or "
                     "a past talk, before you answer. With no words you get the newest memories."),
     "parameters": {"type": "object", "properties": {
         "words": {"type": "string", "description": "A few words to look for, for example: daughter Ann."},
         "kind": {"type": "string", "enum": list(memory_core.KINDS), "description": "Only this kind of memory."}}}},
    {"name": "forget_memory",
     "description": ("They asked you to forget something. Give what to forget in a few of their words, or in the words "
                     "of the memory you just told them. Give nothing only when they just said 'forget that' about "
                     "something from this talk: it removes the last thing you saved. With words, it removes everything "
                     "about that, but only after they agree: the first call removes nothing and answers needs_yes. Ask "
                     "them in one line, and only if they say yes, call again with the same words and confirmed true."),
     "parameters": {"type": "object", "properties": {
         "about": {"type": "string", "description": "What to forget, for example: my son's job."},
         "confirmed": {"type": "boolean", "description": "True only after they said yes to your question."}}}},
    {"name": "forget_name",  # M9c: no arguments, and no yes first: the words are plain, and they can say it again
     "description": ("They asked you to forget their name or to stop calling them it. It's gone for good at once, with "
                     "no question first. Not for a pet name like honey: just stop using that. Not when they give a new "
                     "name to use instead: use the new name.")},
]
MEMORY_TOOL_NAMES = tuple(tool["name"] for tool in MEMORY_TOOLS)


def fact_source(text, typed=False):  # M9c
    """How a fact reached her: "typed", "said" when the resident asked her to remember it, otherwise "talk"."""
    if typed:
        return "typed"
    return "said" if _ASKS_TO_REMEMBER.search(_plain(str(text or ""))) else "talk"


_FORGET_IT = re.compile(r"\bforget (?:it all|all of it|all of that|all that|it|that|him|her|them|everything)\b", _I)


def _forget_yes(text):  # M9c
    """is_yes, for her question about forgetting. "Yes, forget it" is a yes here, though it is not to a note offer.
    "Forget it" alone may mean never mind, so it isn't one."""
    return is_yes(_FORGET_IT.sub(" ", _plain(str(text or ""))))


def _forget_asked(about):  # M9c
    return {"about": about, "at": datetime.now().isoformat(timespec="seconds")}


def forget_everything(memory, about):  # M9c
    """Really deletes everything about it, then what her talk history holds of it. Returns the texts removed."""
    gone = memory.store.forget(about)
    memory.pending_forget = None
    if gone:
        memory.scrub(gone, about)
    return gone


def forget_name(memory, word=""):  # M9c
    """Really deletes their name: each memory holding it, what her talk history holds of it, and the name itself. She
    then neither uses a name nor asks for one (memory.name_forgotten) until they offer one. word: the name they said in
    "stop calling me <word>", gone too. Returns the texts removed. The caller must save memory."""
    names = [n for n in dict.fromkeys((" ".join(memory.name.split()), " ".join(str(word or "").split()))) if n]
    gone = []
    for name in names:
        gone += memory.store.forget_name(name) if memory.store is not None else []
        memory.facts = [f for f in memory.facts if not memory_core.holds_name(f, name)]
    memory.scrub(gone)  # also marks the turn as one that truly forgot, even with nothing saved
    for name in names:
        memory.scrub(gone, about=name, name=name)
    memory.name = ""
    memory.name_forgotten = True
    return gone


def memory_tool(memory, name, args, offer_waiting=False):  # M9c: recall, forget_memory and forget_name
    """Runs one of her memory tools. The same shape as skills.call ({"response", "effects", "say"}), and never raises.
    Takes no lock: reply already holds server._mary_lock. offer_waiting: a note offer is open, so a bare "forget that"
    means the note, not her newest memory. forget_memory with words deletes only on a second call, confirmed, about the
    same thing, within FORGET_YES_S: Gemini can't skip the resident's yes. The texts removed never go back to Gemini.
    After a real delete memory.scrubbed is True, and the caller must save memory."""
    args = args if isinstance(args, dict) else {}
    say = None
    try:
        if name == "recall":
            found = memory.store.recall(str(args.get("words") or ""), str(args.get("kind") or ""))
            response = ({"memories": found, "total": memory.store.count(), "note": RECALL_NOTE} if found
                        else {"memories": [], "note": RECALL_EMPTY_NOTE})
        elif name == "forget_name":  # M9c: the name itself never goes back to Gemini
            forget_name(memory)
            response = {"done": True, "note": NAME_FORGOTTEN_NOTE}
            say = NAME_FORGOTTEN_TEXT
        else:
            about = " ".join(str(args.get("about") or "").split())
            if about.lower().rstrip(".!") in ("that", "this", "it"):  # she passed "forget that" along word for word
                about = ""
            gone, count = [], 0
            if about:
                waiting = _forget_waiting(memory.pending_forget)
                if args.get("confirmed") is True and waiting and memory_core.same_about(waiting["about"], about):
                    gone = forget_everything(memory, about)
                else:
                    count = len(memory.store.matching(about))
                    memory.pending_forget = _forget_asked(about) if count else None
            elif not offer_waiting:
                gone = memory.store.forget("")
                if gone:
                    memory.scrub(gone)
            if count:
                response = {"needs_yes": True, "count": count, "note": FORGET_ASK_NOTE}
            elif gone:
                response = {"forgotten": len(gone), "note": FORGOT_NOTE}
                say = FORGOT_TEXT  # if her next words never come, the resident still hears it was done
            else:
                response = {"forgotten": 0,
                            "note": FORGET_OFFER_NOTE if offer_waiting and not about else FORGET_EMPTY_NOTE}
    except Exception:
        response = {"error": "memory_not_working", "note": MEMORY_BROKEN_NOTE}
    return {"response": response, "effects": [], "say": say}


def _is_name_word(word, name):  # M9c
    """True when the word in "stop calling me <word>" is a name, not "late" or a pet name."""
    lower = word.lower()
    return lower not in _NOT_NAMES and lower != "anymore" and (word[0].isupper() or lower == name.lower())


def offline_memory(memory, text, offer_waiting=False):  # M9c
    """What she says to an exact memory phrase when Gemini can't be reached, or "" when text isn't one."""
    said = " ".join(_plain(str(text or "")).split())
    try:
        if _OFFLINE_RECALL.fullmatch(said):
            found = memory.store.active(limit=OFFLINE_SUMMARY_ITEMS)
            if not found:
                return NOTHING_SAVED_TEXT
            return "Here's some of what I remember: " + " ".join(m["text"].rstrip(" .") + "." for m in found)
        hit = _OFFLINE_FORGET_NAME.fullmatch(said)
        if hit and (not hit.group(1) or _is_name_word(hit.group(1), memory.name)):
            forget_name(memory, hit.group(1))
            return NAME_FORGOTTEN_TEXT
        hit = _OFFLINE_FORGET.fullmatch(said)
        if not hit:
            return ""
        about = hit.group(1)
        if about:  # the same one-line question as with Gemini; reply takes the yes
            if not memory.store.matching(about):
                return NOTHING_TO_FORGET_TEXT
            memory.pending_forget = _forget_asked(about)
            return FORGET_ASK_TEXT.format(about)
        if offer_waiting:  # "forget that" to "Would you like me to write that down?"
            return OFFER_DROPPED_TEXT
        gone = memory.store.forget("")
        if gone:
            memory.scrub(gone)
        return FORGOT_TEXT if gone else NOTHING_TO_FORGET_TEXT
    except Exception:
        return ""


# M4a: Live's own memory tools, in every Live chat. No "__" in the names, so they never look like a skill's.
LIVE_MEMORY_TOOLS = [
    {"name": "remember_fact",
     "description": ("Save a short fact about the resident's life, in third person, following your Remembering rules "
                     "(never staff names, money or account details, or anything they asked you to forget)."),
     "parameters": {"type": "object", "properties": {
         "fact": {"type": "string",
                  "description": "The fact in third person, for example: Has a daughter named Ann in Raleigh."},
         "kind": {"type": "string", "enum": list(memory_core.KINDS), "description": "What sort of fact it is."}},  # M9c
         "required": ["fact"]}},
    {"name": "set_their_name",
     "description": ("They told you what they like to be called, for example 'call me Andy'. Use the name they go by, "
                     "exactly as they said it, never a longer or formal version."),
     "parameters": {"type": "object", "properties": {"name": {
         "type": "string", "description": "The name they like to be called."}}, "required": ["name"]}},
] + MEMORY_TOOLS  # M9c
# M4a: Live's story tool. Live's own stories came out thin, so a story is written by the same brain as Normal talk.
LIVE_STORY_TOOL = {
    "name": "tell_story",
    "description": ("When they ask for a story, call this with what they asked for; it gives you a well-made story "
                    "to tell."),
    "parameters": {"type": "object", "properties": {"request": {
        "type": "string", "description": ("What they asked for, in a few words, for example: a funny one about "
                                          "fishing on the Outer Banks. Say 'any story' if they didn't say.")}},
        "required": ["request"]}}
# M4a: these two are answered by the page, not the server. No "parameters": they take no arguments, and Gemini
# refuses an OBJECT with empty properties.
LIVE_PAGE_TOOLS = [
    {"name": "story_more",
     "description": "When they want the rest of a story you were telling after they cut in, call this for the next part."},
    {"name": "end_talk",
     "description": ("Call this right after your one short goodbye, when they say goodbye, tell you to go to sleep or "
                     "rest, or say they're done talking.")},
]
LIVE_CORE_TOOLS = LIVE_MEMORY_TOOLS + [LIVE_STORY_TOOL] + LIVE_PAGE_TOOLS  # M4a: every Live chat on her own screen gets these
STORY_DEADLINE_S = 25  # M4a: a whole story, collected before Live tells it
STORY_MIN_WORDS = 100  # M4a: anything shorter isn't a story; she tells her own instead
STORY_RETRY_WITHIN_S = 5  # M4a: a first try failing this fast is a refusal (maybe of thinkingConfig), not a timeout
STORY_PROMPT = (  # M4a: rewritten after Andy's fourth try ("saccharine", "childish")
    "Right now, write one story for this person, for you to tell out loud: a grown man or woman who has seen plenty "
    "of life. Tell it the way a good porch storyteller or Southern humorist would, not a children's book. Make it a "
    "fresh story you make up now, with real people who have names and flaws, a real place (North Carolina flavor "
    "unless they've told you they're from somewhere else), and real stakes: money, pride, a feud, a bad decision, a "
    "lie that got out of hand. Tell it about other people, the way you'd tell any story (\"There was a fellow over in "
    "Duplin County...\"). You and your family are never in it: no \"my cousin\", no \"my granddaddy\", no \"I remember "
    "when\", because you have no family or past of your own. Use concrete grown-up detail, dry humor, and at least one thing nobody saw coming. It "
    "can be a tall tale, a funny one, a bit of North Carolina history with the rough edges left on, or an old folk "
    "tale told your way. End on a good last line: a punchline, a twist, or something left hanging. No moral, no "
    "lesson, nobody learning anything, no tidy feel-good ending, and nobody's kindness saving the day. Keep it clean: "
    "no profanity and nothing crude. If they asked for something in particular, give them that. Don't build it from "
    "your own likes and hobbies; you may lean on what you know they like. About 180 to 280 words and never more than "
    "300, in 3 to 5 short paragraphs with a blank line between them. Write only the words you will say: plain spoken sentences, no title, "
    "no brackets or tags, no lists, no headings, no stage directions. Don't greet them or ask a question first; just "
    "begin the story.")


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
        return _BRACKETS.sub("", held)  # M4a: nothing in brackets is ever spoken, like an [alarm: emergency] of her own


# --- skills hook (M13) ---
MAX_TOOL_ROUNDS = 4  # tool rounds per turn (docs/skills-design.md section 5); M13b: 4, opening a group costs a round
NOT_WORKING_TEXT = "I'm sorry, that's not working right now."
SKILL_DONE_TEXT = "All right."  # an offline skill match whose action gave no line to say


class ToolCall:
    """One functionCall part from Gemini, kept exactly as received (Gemini 3 needs its thoughtSignature back)."""
    __slots__ = ("part",)

    def __init__(self, part):
        self.part = part


def skill_blocked(text):
    """True for words no skill may answer offline or claim as a phrase: emergencies and yes/no words."""
    return bool(is_emergency(text) or is_yes(text) or is_decline(text))
# --- end skills hook ---


def _gemini_stream(body, api_key, model="", deadline_s=None):
    """Yields the text pieces of Gemini's streamed answer. Raises on any network or API problem.
    Stops yielding after GEMINI_DEADLINE_S (or deadline_s, M4a), so a slow trickle ends with what was said.
    A functionCall part is yielded as a ToolCall (skills, M13)."""
    url = assist.ENDPOINT.replace(":generateContent", ":streamGenerateContent").format(model=model or assist.DEFAULT_MODEL) + "?alt=sse"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    deadline = time.monotonic() + (deadline_s or GEMINI_DEADLINE_S)
    with urllib.request.urlopen(req, timeout=min(10, deadline_s or 10)) as resp:  # M4a: a short deadline holds on a dead line too
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
                elif "functionCall" in part:  # --- skills hook (M13) ---
                    yield ToolCall(part)


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


def _no_tag_rules(text):  # M4a: Live and stories have nothing to strip tags, so they never hear of them
    """Her instructions without the "Your face" section or any other line that shows a [tag]."""
    text = re.sub(r"^Your face\n(?:.+\n)*\n?", "", text, flags=re.MULTILINE)
    return "\n".join(line for line in text.split("\n") if "[" not in line)


def system_text(memory, companion="mary", facts=True, tags=True):
    """Her system prompt: her own instructions, the live facts about her app, and what she knows of the resident.
    facts=False keeps only the resident's name (no app facts, no facts list, no ask-for-a-name tag): for a live voice chat.
    tags=False (M4a) leaves out every rule about tags, for text nothing cleans up before it's spoken."""
    system = load_instructions(companion)  # M9b: Sam has his own block now, so no more swapping Mary for Sam
    if not tags:
        system = _no_tag_rules(system)
    if facts:
        system += _app_facts_text(companion)  # M9b
    lines = ([f"Name: {memory.name}"] if memory.name else []) + ([f"- {f}" for f in memory.facts] if facts else [])
    store = getattr(memory, "store", None)  # M9c: the voice tryout's stand-in has no store
    if facts and store is not None:  # M9c: only a small core; the rest is found with recall
        try:
            core = store.always_sent(memory.name)
            lines = [core] if core else []
        except Exception:  # a locked database must never stop her talking
            lines = lines[:1] if memory.name else []
    if lines:
        system += "\n\nWhat you know about the resident:\n" + "\n".join(lines)
    if not memory.name and getattr(memory, "name_forgotten", False):  # M9c: the voice tryout's stand-in has no flag
        system += "\n\n" + NAME_FORGOTTEN_SYSTEM
    elif facts and not memory.name:
        system += "\n\nYou don't know their name yet. If it fits naturally, warmly ask once what they'd like to be called"
        system += ("; when they tell you, add the line [name: First name], using the name they go by, "
                   "exactly as they say it." if tags else ".")  # M4a
    return system


# M9b: set by server.py to a function (companion) -> dict of live facts about her app; None in tools and plain tests.
app_facts = None


def _app_facts_text(companion):  # M9b
    """A short block of true-today facts about her own app (voice, talk mode, speed, volume), or "" when unknown."""
    if app_facts is None:
        return ""
    try:
        f = app_facts(companion)
        me = COMPANIONS["him" if companion == "him" else "mary"]
        other = COMPANIONS["mary" if companion == "him" else "him"]
        out = [f'- You are {me}. The other companion is {other}; "Choose Mary or Sam" in the menu changes to them.']  # M4a
        voice_now, picked, about = f.get("voice_now"), f.get("picked_voice") or "", f.get("picked_about") or ""
        pick = picked + (f" ({about})" if about else "")
        if voice_now == "picked" and picked:
            out.append(f"- Your voice right now is {picked}, the one they picked in the voice tryout.")
        elif voice_now == "builtin":
            out.append("- Your voice right now is this computer's built-in voice, and it can sound like a robot. "
                       "If they mention it, agree kindly and say a nicer voice is being worked on.")
            if picked:
                out.append(f"- In the voice tryout they picked {pick} as your new voice. It isn't built in yet; it's coming soon.")
            else:
                out.append("- No new voice has been picked for you in the voice tryout yet. A nicer voice is coming soon.")
        mode = f.get("talk_mode")
        if mode == "button":
            out.append("- They press the Talk button each time they want to say something, and you answer out loud. "
                       "Talking back and forth without the button, and waking you by saying your name, are coming soon.")
        elif mode == "handsfree":
            # M4a: there is no Talk button any more (M4b); her name wakes her when M6 can run here
            way_in = (f'saying "Hey {me}" or tapping Menu, then "Talk to {me}"' if f.get("wake_word")
                      else f'tapping Menu, then "Talk to {me}"')
            out.append(f"- There is no Talk button. They start a conversation by {way_in}; then you and they talk back "
                       "and forth without pressing anything, until about 15 seconds of quiet or a goodbye such as "
                       '"goodbye" or "go to sleep".')
            if not f.get("wake_word"):
                out.append(f'- Waking you by saying "Hey {me}" is off or not set up on this computer, so never tell '
                           "them to say it; tell them about Menu instead.")
            choice = f.get("talk_choice")  # M4a: the talk mode chosen in My info
            if choice in ("live", "normal", "offline"):
                plain = {"live": "Live, your most natural voice, where they can cut in any time",
                         "normal": "Normal, where this computer turns their words into text and you answer in your voice",
                         "offline": "Offline, where your voice is made on this computer"}[choice]
                out.append(f"- Talk mode in My info: {plain}. If one way isn't working you switch to the next by yourself.")
            if f.get("talk_on_open"):  # M4a
                out.append("- When your screen opens, you start talking by yourself: you say hello and listen, so they "
                           "don't need to tap anything.")  # M4a
        rate, volume = f.get("voice_rate"), f.get("voice_volume")
        if rate is not None and volume is not None:
            speed = "slower than usual" if rate < 0.85 else "faster than usual" if rate > 1.1 else "about normal"
            loud = "soft" if volume < 0.5 else "medium" if volume < 0.85 else "full"
            out.append(f"- Your talking speed is {speed} and your volume is {loud}. "
                       f'They can change these by asking you, or in the menu under "Things {me} can do".')  # M4a
        return "\n\nAbout your app right now (these are true today; trust them over anything else):\n" + "\n".join(out)
    except Exception:
        return ""


def _body(text, memory, kind, companion="mary", skills=None, screen=None):
    system = system_text(memory, companion)
    # --- skills hook (M13) --- an emergency line gets no skills at all
    tools = []
    if skills is not None and not kind:
        extra = skills.instruction_text(screen)
        if extra:
            system += "\n\n" + extra
        tools = skills.gemini_tools()
    # --- end skills hook ---
    system += CHARACTER_NOTE  # M4c: late in the prompt, where it holds; only the turn notes come after it
    if kind:  # M4a: the bench heard the same instruction twice in a row
        system += (f"\n\nThe app has already told them this out loud: {EMERGENCY_TEXT[kind]} They heard it, so don't "
                   "say any of it again, in any words. Add only one short, calm line of your own, to keep them company.")
        if kind == "self_harm":
            system += " If they've told you they're a veteran, that line gives the Veterans Crisis Line; if not, leave it out."
    else:  # M4a: the bench's "an aide hit me" got only the offer to write it down
        if _HARMED.search(_plain(text)):
            system += HARM_NOTE
        if _FEARS_STAFF.search(_plain(text)):
            system += FEAR_NOTE
    if not kind and getattr(memory, "store", None) is not None:  # M9c: one functionDeclarations entry, shared with the skills
        tools = [{"functionDeclarations": [d for t in tools for d in t["functionDeclarations"]] + MEMORY_TOOLS}]
    # M4a: her scripted hello is her turn too, so a talk may start with hers, or follow her last line of the talk before
    contents = []
    for t in memory.recent:
        if contents and contents[-1]["role"] == t["role"]:
            contents[-1]["parts"][0]["text"] += "\n" + t["text"]
        else:
            contents.append({"role": t["role"], "parts": [{"text": t["text"]}]})
    if contents and contents[0]["role"] != "user":
        contents.insert(0, {"role": "user", "parts": [{"text": "(They opened the app.)"}]})
    contents.append({"role": "user", "parts": [{"text": text}]})
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4000}}  # M4a: room for a whole story; the brain keeps chat short
    if tools:  # --- skills hook (M13) ---
        body["tools"] = tools
    return body


# M4a: a nudge on the turn it matters. The words only make the note appear, and it says "if so", so a miss costs nothing.
_HARMED = re.compile(
    r"\b(?:hit|hitting|slapped|punched|kicked|shoved|pinched|grabbed|threatened|threatening|hurt|hurting)\s+me\b"
    r"|\bthreatened\s+to\b|\b(?:put|puts|laid)\s+(?:his|her|their)\s+hands\s+on\s+me\b|\b(?:stole|stolen|stealing|robbed)\b"
    r"|\b(?:took|taken|missing|gone)\b[^.?!]{0,30}\b(?:money|purse|wallet|ring|jewelry)\b"
    r"|\b(?:money|purse|wallet|ring|jewelry)\b[^.?!]{0,30}\b(?:took|taken|missing|gone)\b", _I)
_FEARS_STAFF = re.compile(
    r"\b(?:afraid|scared|fear|frightened|worried|nervous)\b[^.?!]{0,60}"
    r"\b(?:trouble|retaliat\w*|punish\w*|get back at|take it out|mad at me|worse|report\w*|telling|tell)\b"
    r"|\b(?:take it out on|hold it against|get back at) me\b|\bretaliat\w*\b", _I)
HARM_NOTE = ("\n\nThey may have just said someone hurt, hit, threatened or stole from them. If so, say all of this, in "
             "this order: say plainly that it's not okay, suggest telling a nurse or a person in charge they trust, and "
             "only then offer to write it down. Never promise that you will report it yourself.")
FEAR_NOTE = ("\n\nThey may be afraid of staff taking it out on them. If so, tell them that retaliation against residents "
             "is against the law, that nothing is written or sent without their say, and that the long-term care "
             "ombudsman can help them in confidence.")
# M4c: closes Normal's prompt and Live's (voices.LIVE_TOOLS_NOTE), because run 2 showed the manner rules fade mid-prompt.
# For either companion, so no name. No square brackets: Live's prompt must never hold one.
CHARACTER_NOTE = ("\n\nBefore you speak, every time:\n"
                  "- No pet names unless they've asked for one: no \"honey\", no \"sugar\", no \"dear\". Any other "
                  "friendly name only the way your own section above allows.\n"
                  "- Don't cheer or praise ordinary things: no \"Well, good for you!\", no \"Look at that!\", no "
                  "\"That's wonderful!\" Take it the way a neighbor your own age would.\n"
                  "- \"Bless your heart\" only as real sympathy, never as praise.\n"
                  "- No fussing, no \"we\" when you mean \"you\", and no customer-service lines like \"Is there "
                  "anything else I can help you with?\"\n"
                  "- Your warmth is in paying attention, not in sugar.\n"
                  "- When the talk turns racist, don't agree, don't echo it, don't soften it into nicer words, and "
                  "don't lecture. Say one plain line, like \"I don't see people that way,\" and turn to something "
                  "else. Don't ask about it.")


def not_english(text):  # M4a: Live's transcript sometimes comes back in another script
    """True when most of the letters in text are not Latin. No letters at all is False."""
    letters = [c for c in str(text or "") if c.isalpha()]
    return bool(letters) and sum(ord(c) >= 0x250 for c in letters) / len(letters) > 0.5


def _story_memories(memory, ask):  # M9c
    """What she has saved that fits the story asked for, so a story keeps what she knows of them."""
    store = getattr(memory, "store", None)
    if store is None:
        return ""
    try:
        found = store.recall(ask, limit=6)
    except Exception:
        return ""
    return "\n\nThings they've told you that may fit:\n" + "\n".join(f"- {m['text']}" for m in found) if found else ""


def tell_story(request, memory, api_key, model="", companion="mary", report=None):  # M4a: Live's tell_story tool
    """One well-made story for Live to tell aloud, written by the same brain as Normal talk (with her app facts and
    what she knows of them). Returns the story as plain spoken text, or "" on any problem (no key, network, too short).
    report (a dict, if given) gets "path", "words" and any "error", for the log: voices can't be imported here."""
    report = {} if report is None else report
    report.update(path="", words=0)
    if not api_key:
        return ""
    ask = " ".join(str(request or "").split())[:300]
    system = system_text(memory, companion, tags=False) + _story_memories(memory, ask) + "\n\n" + STORY_PROMPT  # M9c
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": "Tell me a story" + (f": {ask}" if ask else ".")}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 6000}}

    def write():
        return "".join(p for p in _gemini_stream(body, api_key, model, deadline_s=STORY_DEADLINE_S)
                       if isinstance(p, str))
    # M4a: thinking tokens count against maxOutputTokens on Gemini 3, and the default HIGH can leave a stub
    plain = body["generationConfig"]
    body["generationConfig"] = {**plain, "thinkingConfig": {"thinkingLevel": "low"}}
    report["path"] = "thinking_low"
    started = time.monotonic()
    try:
        text = write()
    except Exception as e:
        report["error"] = type(e).__name__
        if isinstance(e, TimeoutError) or time.monotonic() - started >= STORY_RETRY_WITHIN_S:
            return ""
        body["generationConfig"] = plain  # some models refuse thinkingConfig with a 400
        report["path"] = "no_thinking"
        try:
            text = write()
        except Exception as e2:
            report["error"] = type(e2).__name__
            return ""
        report.pop("error", None)
    text = _BRACKETS.sub("", text)
    text = re.sub(r"[*#]+", "", text)              # markdown bold and headings are never spoken
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*\n\s*", "\n\n", text).strip()
    end = re.search(r"[.!?…][\"'”’)]*(?=[^.!?…]*$)", text)  # a story cut off by the deadline ends on a whole sentence
    text = text[:end.end()] if end else text
    report["words"] = len(text.split())
    return text if report["words"] >= STORY_MIN_WORDS else ""


# --- M4a: her hello and her eyes: short answers on the resident's own key ---
OPEN_DEADLINE_S = 8
OPEN_TIMES = ("morning", "afternoon", "evening", "night")
OPEN_NUDGE = "(They opened the app.)"
OPEN_PROMPT = (
    "They have just opened your screen{clock}. Say hello in one or two short sentences, as one grown-up to another: "
    "plain and easy, no gushing and no fuss over them. Use their name if you know it and, when it fits, something you "
    "remember about them or from your last talk. Use different words every time. A light \"good morning\", \"good "
    "afternoon\" or \"good evening\" is fine, but never \"good night\", and never comment on the hour or how late it is. "
    "Never ask something they have already answered, and never list what you can do. Just the words you say, with no "
    "tags and no notes in brackets.")
VISION_DEADLINE_S = 8
VISION_BYTES_MAX = 700_000  # a bigger picture isn't sent: a look has to stay quick


def _short_answer(body, api_key, model, deadline_s):
    """One short Gemini answer as text, "" on any problem. Thinking low, as in tell_story, then one retry without
    thinkingConfig after a fast failure (some models refuse it with a 400). Both tries share deadline_s."""
    plain = body["generationConfig"]
    started = time.monotonic()

    def ask(config, left):
        body["generationConfig"] = config
        return "".join(p for p in _gemini_stream(body, api_key, model, deadline_s=left) if isinstance(p, str))
    try:
        return ask({**plain, "thinkingConfig": {"thinkingLevel": "low"}}, deadline_s)
    except Exception as e:
        spent = time.monotonic() - started
        if isinstance(e, TimeoutError) or spent >= STORY_RETRY_WITHIN_S:
            return ""
    try:
        return ask(plain, deadline_s - spent)
    except Exception:
        return ""


def open_line(memory, api_key, model="", companion="mary", when=""):
    """Her hello, from the same brain and history as her talk, with a one-off instruction that is never saved.
    Plain spoken text, or "" on any problem: the page then says a scripted line. Never raises."""
    if not api_key:
        return ""
    try:
        body = _body(OPEN_NUDGE, memory, None, companion)
    except Exception:
        return ""
    clock = f", and it is {when} where they are" if when in OPEN_TIMES else ""
    body["systemInstruction"]["parts"][0]["text"] += "\n\n" + OPEN_PROMPT.format(clock=clock)
    body["generationConfig"] = {"temperature": 0.9, "maxOutputTokens": 1000}
    text = _short_answer(body, api_key, model, OPEN_DEADLINE_S)
    text = " ".join(re.sub(r"[*#]+", "", re.sub(r"\[[^\]]*\]?", "", text)).split())
    end = re.search(r"[.!?…][\"'”’)]*(?=[^.!?…]*$)", text)  # a line cut off by the deadline ends on a whole sentence
    return text[:end.end()] if end else text


def see_image(image_bytes, mime, question, api_key, model=""):
    """What Gemini sees in a picture: the picture and one question, nothing about the resident. Plain text, or "" with
    no key, with a picture over VISION_BYTES_MAX or on any problem. Never raises."""
    try:
        if not api_key or not image_bytes or len(image_bytes) > VISION_BYTES_MAX:
            return ""
        data = base64.b64encode(bytes(image_bytes)).decode("ascii")
    except (TypeError, ValueError):
        return ""
    body = {"contents": [{"role": "user", "parts": [{"inlineData": {"mimeType": str(mime), "data": data}},
                                                    {"text": str(question)}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1000}}
    return _short_answer(body, api_key, model, VISION_DEADLINE_S).strip()
# --- end M4a ---


def reply(text, memory, api_key="", model="", on_text=None, companion="mary", on_mood=None, write=None,
          skills=None, screen=None, on_effect=None, typed=False):
    """Mary's answer to what the resident said.

    typed (M9c): they typed this, so a fact from it is saved with source "typed".
    Returns {text, mood, emergency, gemini_alert, offer, logged, remembered, error, effects, first_words_s, total_s}.
    Skills (M13): skills is a skills_core.SkillHost, screen the skill now on screen. Gemini's tool calls run
    through it (at most MAX_TOOL_ROUNDS rounds); each effect goes to on_effect as it happens and into effects.
    With no Gemini (no key, or it failed) an offline phrase can still run a skill. An emergency gets no skills.
    on_text gets each spoken piece as it is ready. on_mood gets her mood as soon as it is known,
    once (a reply that is only a mood tag, no words, is corrected to "sorry" with a second call).
    Mood tags are never spoken or remembered. An offline emergency always means "alert";
    gemini_alert is True when only Gemini said alert.
    A pending offer lives exactly one turn. When the resident's next words are a clear yes (is_yes) and
    write is given, write(incident) saves it (returns the new id, raises on failure) and Mary says
    SAVED_TEXT without calling Gemini; logged is {id, category}. If saving fails she says SAVE_FAILED_TEXT
    and the offer stays pending for one more try. Otherwise logged is None. Without write nothing is saved.
    A forget waiting for its yes (M9c) is answered by the very next turn. A clear yes deletes and she says FORGOT_TEXT
    without calling Gemini; anything else drops it, so a later "yes" to something else can't delete. An emergency comes
    first, and a note offer's yes goes first; either way it waits. A turn that truly forgot goes in neither talk history
    nor a note offer.
    """
    start = time.monotonic()
    spoken = ""
    first_words_s = None
    mood = None
    gemini_mood_seen = gemini_alert = streamed = False
    if companion not in COMPANIONS:
        companion = "mary"
    store = getattr(memory, "store", None)  # M9c
    # --- skills hook (M13) ---
    effects, says, rounds, gap = [], [], 0, False

    def add_effect(effect):
        effects.append(effect)
        if on_effect:
            on_effect(effect)
    # --- end skills hook ---

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
        nonlocal streamed, gap
        if after_tag and (not spoken or spoken[-1].isspace()):
            piece = piece.lstrip()  # the gap a removed tag leaves
        if piece:
            emit(piece, sep=not streamed or gap)  # gap: a new tool round starts a new sentence (M13)
            streamed, gap = True, False

    prior = memory.pending_offer  # an offer lives exactly one turn
    memory.pending_offer = None
    if not (isinstance(prior, dict) and isinstance(prior.get("incident"), dict) and _offer_fresh(prior)):
        prior = None
    kind = is_emergency(text)
    said_yes = bool(prior) and is_yes(text)
    waiting = _forget_waiting(memory.pending_forget) if store is not None else None  # M9c
    forget_yes = bool(waiting) and not kind and not said_yes and _forget_yes(text)
    if waiting and not kind and is_decline(text):
        memory.pending_forget = None
    if kind:
        set_mood("alert")
        emit(EMERGENCY_TEXT[kind])
        if said_yes:
            memory.pending_offer = prior  # the emergency comes first; the offer waits one more turn
    confirmed = said_yes and not kind and write is not None
    logged = None
    offer = None
    if confirmed or forget_yes or (kind and said_yes):  # M9c: forget_yes
        pass
    elif is_decline(text):
        memory.pending_offer = None
    else:
        offer = None if kind == "self_harm" else lapse_offer(text)
        if offer:
            memory.pending_offer = offer
    learn_name(memory, text)  # M4a: shared with Live's /api/mary/heard

    error = ""
    remembered = []
    name_dropped = False  # M9c: forget_name ran, so a [name:] in the same reply is ignored
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
    elif forget_yes:  # M9c
        try:
            gone = forget_everything(memory, waiting["about"])
        except Exception:
            memory.pending_forget = waiting  # so the next "yes" can try again
            set_mood("sorry")
            emit(FORGET_FAILED_TEXT)
        else:
            set_mood("talking")
            emit(FORGOT_TEXT if gone else NOTHING_TO_FORGET_TEXT)
    elif api_key:
        raw = ""
        stream = _ReplyStream(speak, take_mood)
        body = _body(text, memory, kind, companion, skills, screen)  # --- skills hook (M13) ---
        try:
            while True:  # --- skills hook (M13) --- one pass per tool round
                calls, said = [], ""
                for chunk in _gemini_stream(body, api_key, model):
                    if isinstance(chunk, ToolCall):  # --- skills hook (M13) ---
                        calls.append(chunk.part)
                        continue
                    raw += chunk
                    said += chunk
                    stream.feed(chunk)
                # --- skills hook (M13) --- run her tool calls, then ask again with their answers
                if not calls or (skills is None and store is None) or kind or rounds >= MAX_TOOL_ROUNDS:  # M9c: store too
                    break
                rounds += 1
                answers = []
                for part in calls:
                    call = part.get("functionCall") or {}
                    name_dropped = name_dropped or call.get("name") == "forget_name"  # M9c
                    if store is not None and call.get("name") in MEMORY_TOOL_NAMES:  # M9c
                        result = memory_tool(memory, call.get("name"), call.get("args"), offer_waiting=bool(prior))
                    elif skills is not None:
                        result = skills.call(call.get("name"), call.get("args"), screen=screen)  # M13b: screen
                    else:  # M9c: she has only her memory tools here
                        result = {"response": {"error": "unknown_tool"}, "effects": [], "say": None}
                    for effect in result["effects"]:
                        add_effect(effect)
                    if result["say"]:
                        says.append(result["say"])
                    answer = {"name": call.get("name"), "response": result["response"]}
                    if call.get("id"):
                        answer["id"] = call["id"]
                    answers.append({"functionResponse": answer})
                body = dict(body, contents=body["contents"] + [
                    {"role": "model", "parts": ([{"text": said}] if said else []) + calls},  # parts as received
                    {"role": "user", "parts": answers}])
                tail = stream.finish()
                if tail.strip():
                    speak(tail)
                stream, raw, gap = _ReplyStream(speak, take_mood), raw + "\n", True
                # --- end skills hook ---
        except urllib.error.HTTPError as e:
            error = BAD_KEY if _key_refused(e) else NO_GEMINI
        except Exception:
            error = NO_GEMINI
        for tag, value in _TAG.findall(raw):
            if tag == "remember":
                try:  # M9c: a locked database must never stop her reply
                    # M9c: a [remember] in the very reply that forgot must not save it straight back
                    if not memory.scrubbed and memory.add_fact(value, source=fact_source(text, typed)):
                        remembered.append(" ".join(value.split()))
                except Exception:
                    pass
            elif value.strip() and not name_dropped:
                memory.name = value.strip()[:40]
                memory.name_forgotten = False  # M9c
        tail = stream.finish()
        if tail.strip():
            speak(tail)
        if rounds and not spoken.strip():  # --- skills hook (M13) --- her follow-up failed or had no words
            if says:
                emit(" ".join(says))
            else:
                set_mood("sorry")
                emit(NOT_WORKING_TEXT)
        if not streamed and not error:
            error = NO_GEMINI

    # --- skills hook (M13) --- no Gemini (no key, or it failed): an offline phrase can still run a skill
    if (skills is not None and not spoken.strip() and not kind and not rounds and error in ("", NO_GEMINI)
            and not (prior and (said_yes or is_decline(text)))):
        hit = skills.offline_match(text, is_blocked=skill_blocked)
        if hit:
            for effect in hit["effects"]:
                add_effect(effect)
            gemini_alert = False
            failed = bool(hit["response"].get("error"))
            set_mood("sorry" if failed else "talking")
            emit(hit["say"] or (NOT_WORKING_TEXT if failed else SKILL_DONE_TEXT))
            if not api_key:
                error = NO_KEY
    # --- end skills hook ---

    # M9c: no Gemini: a few exact phrases still reach her memory
    if (store is not None and not spoken.strip() and not kind and not rounds and error in ("", NO_GEMINI)
            and not (prior and (said_yes or is_decline(text)))):
        line = offline_memory(memory, text, offer_waiting=bool(prior))
        if line:
            gemini_alert = False
            set_mood("talking")
            emit(line)
            if not api_key:
                error = NO_KEY

    if not spoken.strip() and not kind:
        gemini_alert = False  # a bare "alert" tag with no words is not something to act on
        set_mood("sorry")
        emit(BAD_KEY_TEXT if error == BAD_KEY else OFFLINE_TEXT)
        if not api_key:
            error = NO_KEY
    elif mood is None:
        set_mood("talking")
    if memory.scrubbed:  # M9c: no note offer keeps the words of a turn that truly forgot
        offer = memory.pending_offer = None
    elif not (offer or said_yes or kind == "self_harm" or is_decline(text)) and _asks_to_write(spoken):
        # Gemini offered on her own for something the word list missed: a "yes" must still save it.
        offer = memory.pending_offer = _offer(_guess(text))
    if offer and not _ASKS.search(spoken):
        emit(offer["question"], sep=True)

    final = spoken.strip()
    if waiting and memory.pending_forget is waiting and not (kind or said_yes or forget_yes):  # M9c
        memory.pending_forget = None  # her question went unanswered, so a later "yes" can't be taken for it
    if not memory.scrubbed:  # M9c: a turn that truly forgot leaves nothing in her talk history
        memory.add_turn("user", text)
        if final:
            memory.add_turn("model", final)
    try:
        memory.save()
    except OSError:
        pass
    return {"text": final, "mood": mood, "emergency": kind, "gemini_alert": gemini_alert, "offer": offer,
            "logged": logged, "remembered": remembered, "error": error, "effects": effects,  # effects: M13
            "first_words_s": first_words_s, "total_s": time.monotonic() - start}
