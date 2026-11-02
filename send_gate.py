"""The hard-wired yes for email (M15c).

This guards the one way a message leaves the resident's laptop: a look at the finished message, the words they say, and
five seconds to stop it. Gemini can never start a send. Only three things move a send forward, and all three are checked
here, in core code a skill can't change: the resident's own words, a tap on the page, and the clock. A tool call from
Gemini can show the look and nothing more.

One look at a time, in memory only, under a lock. A restart forgets it, which is safe. There are no timers and no threads
here: nothing can send unless a live page asks at the end of the count. If the window dies mid-count, nothing goes.
Stdlib only.
"""

import re
import secrets
import threading
import time

import mail_core

COUNT_S = 5.0  # the Undo window
COUNT_STALE_S = 30.0  # a count nobody finished by now is dead
LOOK_TTL_S = 600
MISSES_FOR_TAP = 2
MAIL_PICTURES_MAX = 600_000  # bytes in all, from the M15d note: a card that fits any inbox
PLAIN_WORDS_MAX = 12
ORDER_WORDS_MAX = 16  # D12: a plain order to turn a switch on or off
MISS_WORDS_MAX = 3

STOP_WORDS = ("stop", "undo", "wait", "no", "don't", "cancel", "hold", "hang on", "never mind", "oops", "not")

NO_LOOK = {"state": "none", "line_said": False, "tap_open": False, "look": None, "line": ""}

_NOT_PLAIN = STOP_WORDS + ("do not", "never", "later", "tomorrow", "maybe", "should", "if", "when", "did", "why",
                           "whether", "instead", "nope", "nah", "until", "unless", "after", "before", "next", "tonight")
_MADE_OUT = {"ok", "okay", "yes", "yeah", "yep", "yup", "sure", "alright", "right", "fine", "good", "great", "nice",
             "lovely", "perfect", "wonderful", "sounds", "looks", "that", "that's", "thats", "it", "is", "very", "thanks",
             "thank", "you", "no", "nope", "nah", "not", "mm", "mhm", "hmm", "uh", "um", "huh", "oh", "ah", "well", "so",
             "got", "i", "see"}
_TITLES = {"aunt", "uncle", "cousin", "grandma", "grandpa", "granny", "nana", "papa", "brother", "sister", "father",
           "mother", "pastor", "reverend", "rev", "dr", "doctor", "mr", "mrs", "ms", "miss", "mister", "my", "our", "the"}


def _alternatives(words):
    return "|".join(re.escape(word).replace(r"\ ", r"\s+") for word in words)


_STOP_RE = re.compile(rf"\b(?:{_alternatives(STOP_WORDS)}|dont)\b")
_NOT_PLAIN_RE = re.compile(rf"\b(?:{_alternatives(_NOT_PLAIN)})\b|\w+n't\b"
                           r"|\b(?:dont|cant|wont|didnt|shouldnt|wouldnt|couldnt)\b")
_BREAK_RE = re.compile(r"[,.;:!?–—]+|\s-\s")
_BEFORE = (r"(?:mary|sam|please|now|okay|ok|yes|yeah|alright|go ahead and|just|you can|can you|could you|would you"
           r"|will you|then|and)")
_WHAT = r"(?:it|that|this|the card|the message|my card|my message)"
_AFTER = r"now|off|please|on its way|mary|sam|okay|ok|yes|yeah|alright|then"
_SAVE_BEFORE = (r"(?:mary|sam|please|now|okay|ok|yes|yeah|alright|go ahead and|just|you can|can you|could you|would you"
                r"|will you|then|and|let'?s|that'?s (?:good|fine|right)|looks good)")
_SAVE_WHAT = r"(?:it|that|this|my info|my information|the form|this form|my form)"
_SAVE_AFTER = r"now|please|mary|sam|okay|ok|yes|yeah|alright|then|for me|thanks|thank you"

_FIVE_RE = re.compile(r"\b(?:five|5)[\s-]seconds?\b")
_SECOND_RE = re.compile(r"\bseconds?\b")
_EMAIL_RE = re.compile(r"\be-?mail\b")

_ASKS = (
    ("password", re.compile(r"\bpass(?:word|code)s?\b|\bpin numbers?\b|\blog[\s-]?in\b")),
    ("ssn", re.compile(r"\bsocial security\b|\bssn\b|\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")),
    ("money", re.compile(
        r"\bbank accounts?\b|\baccount numbers?\b|\brouting numbers?\b"
        r"|\b(?:credit|debit)(?: or (?:credit|debit))? card numbers?\b"
        r"|\bwire (?:me|you|him|her|them|us|it|money|cash|the money|some money|transfer)\b|\bwired? \$|\bwestern union\b|\bmoney ?grams?\b|\bmoney orders?\b|\bgift cards?\b|\bzelle\b|\bvenmo\b"
        r"|\bcash ?app\b|\bpay ?pal\b|\bbitcoin\b|\bcrypto(?:currency)?\b"
        r"|\b(?:send|give|lend|loan|transfer|mail)(?: (?:me|you|him|her|them|us))?(?: (?:some|the))?"
        r"\s*(?:money\b|cash\b|\$\s*\d|\d[\d,.]*\s*(?:dollars|bucks)\b)")),
)


class GateRefused(Exception):
    """arm said no. reason: money, password, ssn, too_big or bad_message."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _lower(text):
    return str(text or "").lower().replace("’", "'")


def _words(text):
    return re.sub(r"[^\w']+", " ", _lower(text)).split()


def _short_name(person):
    """The name she says: the first name, or the whole name after a title ("Aunt Sue", "Dr. Smith", "my son")."""
    words = str(person or "").split()
    if not words:
        return ""
    return " ".join(words) if len(words) > 1 and words[0].lower().strip(".") in _TITLES else words[0]


def _spoken_names(person):
    """The person's name and short name as plain lower-case words, to match against what the resident said."""
    return [name for name in dict.fromkeys((" ".join(_words(person)), " ".join(_words(_short_name(person))))) if name]


def line_for(person, plain=False):
    """The line she says before any send. Skills and the gate both use this one, so the two can't drift. plain: a message
    with no picture, which gets "Here's what I've got." first."""
    name = _short_name(person)
    if name.lower().startswith("my "):
        name = "your " + name[3:]
    whose = f"{name}'s" if name else "their"
    line = f"When you say send, it goes to {whose} email. You'll have five seconds to stop it."
    return f"Here's what I've got. {line}" if plain else line


def is_plain_send(text, person=""):
    """True when the words are a plain "send it" to this person, and nothing less. Any negative or delay anywhere refuses
    the whole line. The last clause must fully match, so "okay, send it" counts and "send it to Tyler" with Mark on the
    envelope doesn't. A clause of only fillers after it ("send it, please") doesn't hide it."""
    lower = _lower(text)
    if _NOT_PLAIN_RE.search(lower) or len(_words(lower)) > PLAIN_WORDS_MAX:
        return False
    clauses = [" ".join(_words(part)) for part in _BREAK_RE.split(lower)]
    clauses = [clause for clause in clauses if clause]
    if not clauses:
        return False
    names = "|".join(re.escape(name) for name in _spoken_names(person))
    after = f"(?:{_AFTER}|to (?:{names}))" if names else f"(?:{_AFTER})"
    while len(clauses) > 1 and re.fullmatch(rf"{after}(?: {after})*", clauses[-1]):
        clauses.pop()
    return re.fullmatch(rf"(?:{_BEFORE} )*send {_WHAT}(?: {after})*", clauses[-1]) is not None


def is_plain_save(text):
    """True when the words are a plain "save it" for the form on the screen, and nothing less. Built like is_plain_send:
    any negative or delay anywhere refuses the whole line, and the last clause must fully match. A question mark on that
    clause refuses too ("save it?", "save it, okay?"), except a plain ask of her ("Can you save it?"), since Live adds the
    mark by itself. "keep it" never counts: it answers "Is that right?" or "keep it for
    next time?", not the form."""
    lower = _lower(text)
    if _NOT_PLAIN_RE.search(lower) or len(_words(lower)) > PLAIN_WORDS_MAX:
        return False
    clauses = list(zip((" ".join(_words(part)) for part in _BREAK_RE.split(lower)), _BREAK_RE.findall(lower) + [""]))
    clauses = [clause for clause in clauses if clause[0]]
    if not clauses:
        return False
    after = rf"(?:{_SAVE_AFTER})(?: (?:{_SAVE_AFTER}))*"
    while len(clauses) > 1 and "?" not in clauses[-1][1] and re.fullmatch(after, clauses[-1][0]):
        clauses.pop()
    words, mark = clauses[-1]
    asked = re.match(r"(?:can|could|would|will) you ", words) is not None
    return ("?" not in mark or asked) and re.fullmatch(rf"(?:{_SAVE_BEFORE} )*save {_SAVE_WHAT}(?: {after})?", words) is not None


_ORDER_OFF_RE = re.compile(r"\b(?:(?:turn|switch|shut|put|set)\b.*\boff|disable)\b")
_ORDER_ON_RE = re.compile(r"\b(?:(?:turn|switch|put|set)\b.*\bon|enable|connect)\b")
_ORDER_SWITCH_NAME_RE = re.compile(r"\bwhen (?:mary|sam|you|she|he) opens?\b")
_ORDER_ASK_RE = re.compile(r"\b(?:how|what|does)\b")
_ORDER_FILLERS = r"(?:(?:mary|sam|hey|please|okay|ok|yes|yeah|alright|now|then|and|just)[\s,]+)*"


def plain_order(text):  # D12
    """The resident's own plain order to turn a switch on or off, or None. Built like is_plain_save: any negative or delay
    anywhere refuses the whole line, as do how/what/does and a question that is not a plain ask of her ("Can you turn it
    off?"; Live adds the mark by itself). Both directions in one line, or neither, is no order. Returns the acts and the
    lower-case words, so the page can check the line names (or points at) the field. The server changes nothing."""
    lower = _lower(text)
    words = _words(lower)
    plain = _ORDER_SWITCH_NAME_RE.sub("", lower)  # "when Mary opens" is a switch's own name, not a delay
    if not words or _NOT_PLAIN_RE.search(plain) or len(words) > ORDER_WORDS_MAX or _ORDER_ASK_RE.search(lower):
        return None
    if "?" in lower and not re.match(rf"\s*{_ORDER_FILLERS}(?:can|could|would|will) you\b", lower):
        return None
    acts = []
    if _ORDER_OFF_RE.search(lower):
        acts.append("off")
    if _ORDER_ON_RE.search(lower):
        acts.append("on")
    return {"acts": acts, "words": " ".join(words)} if len(acts) == 1 else None


def asks_for(text):
    """"money", "password", "ssn" or None. Narrow, so "thank you for the money you sent at Christmas" passes."""
    words = " ".join(_lower(text).split())
    for reason, pattern in _ASKS:
        if pattern.search(words):
            return reason
    return None


class _Look:
    """One armed message. content is the plain copies from mail_core._freeze. The id is what the page holds."""

    def __init__(self, skill, person, content, armed_at):
        self.id = secrets.token_urlsafe(16)
        self.skill = skill
        self.person = person
        self.content = content
        self.line = line_for(person, plain=not content[3])
        self.armed_at = armed_at
        self.state = "look"  # then counting, then sending
        self.shown = False
        self.line_said = False
        self.scripted = False
        self.misses = 0
        self.tap_open = False
        self.count_from = None


class SendGate:
    """Holds the one look. mailer is the core's own mailer object, which skills never reach; only SkillContext.send_now
    uses it, after take. clock is for tests."""

    def __init__(self, mailer, clock=time.monotonic):
        self.mailer = mailer
        self._clock = clock
        self._lock = threading.Lock()
        self._look = None

    # ----- plumbing (call these with the lock held) -----

    def _current(self, now):
        """The live look, once the clock has had its say. A dead count goes back to the look, because every word during
        a count is kept from the brain, and talk must never stay shut off by a window that died."""
        look = self._look
        if look is None:
            return None
        if look.state == "counting" and now > look.count_from + COUNT_STALE_S:
            self._back_to_look(look)
        if look.state == "look" and now - look.armed_at > LOOK_TTL_S:
            self._look = None
        return self._look

    @staticmethod
    def _back_to_look(look):
        look.state = "look"
        look.count_from = None
        look.misses = 0
        look.tap_open = False

    @staticmethod
    def _start_count(look, now):
        look.state = "counting"
        look.count_from = now

    # ----- the look -----

    @property
    def skill(self):
        """The skill holding the look, or None."""
        with self._lock:
            return self._look.skill if self._look is not None else None

    def arm(self, skill, person, to, subject, body, pictures=()):
        """Freezes the exact content and returns the look id, or raises GateRefused. Replaces any older look. A refused
        arm drops the older one too, because that content is no longer what the resident is looking at."""
        self.disarm(skill)
        content = mail_core._freeze(to, subject, body, pictures)
        if not mail_core._message_ok(*content):
            raise GateRefused("bad_message")
        reason = asks_for(f"{content[1]}\n{content[2]}")
        if reason:
            raise GateRefused(reason)
        if sum(len(data) for _, data in content[3]) > MAIL_PICTURES_MAX:
            raise GateRefused("too_big")
        person = " ".join(str(person or "").split())
        with self._lock:
            self._look = _Look(skill, person, content, self._clock())
            return self._look.id

    def disarm(self, skill):
        """The content changed or the screen left. No look."""
        with self._lock:
            if self._look is not None and self._look.skill == skill:
                self._look = None

    def shown(self, look_id):
        """The page really drew this look. Only the page can say so."""
        with self._lock:
            look = self._current(self._clock())
            if look is None or look.id != look_id:
                return False
            look.shown = True
            return True

    def state(self, skill):
        """{"state", "line_said", "tap_open", "look", "line"}, with no address."""
        with self._lock:
            look = self._current(self._clock())
            if look is None or look.skill != skill:
                return dict(NO_LOOK)
            return {"state": look.state, "line_said": look.line_said, "tap_open": look.tap_open, "look": look.id,
                    "line": look.line}

    # ----- the words -----

    def her_words(self, text):
        """Her finished turn. Marks the line said once it really went out. After a scripted line, "second" alone does, so
        a transcript quirk can't trap them."""
        lower = _lower(text)
        with self._lock:
            look = self._current(self._clock())
            if look is None or look.state != "look" or look.line_said:
                return False
            name = _short_name(look.person).lower()
            named = _EMAIL_RE.search(lower) or (name and re.search(rf"\b{re.escape(name)}\b", lower))
            if (_FIVE_RE.search(lower) and named) or (look.scripted and _SECOND_RE.search(lower)):
                look.line_said = True
            return look.line_said

    def heard(self, text, garbled=False):
        """The resident's finished words. Returns {"action": ...}: None when the gate has nothing to do with them, else
        stopped, quiet, say_line (with "line"), count or tap."""
        with self._lock:
            now = self._clock()
            look = self._current(now)
            if look is None:
                return {"action": None}
            if look.state == "counting":
                if _STOP_RE.search(_lower(text)):
                    self._back_to_look(look)
                    return {"action": "stopped"}
                return {"action": "quiet"}
            if look.state != "look" or not look.shown:
                return {"action": None}
            if not garbled and is_plain_send(text, look.person):
                if look.line_said:
                    self._start_count(look, now)
                    return {"action": "count"}
                look.scripted = True
                return {"action": "say_line", "line": look.line}
            words = _words(text)
            if garbled or (0 < len(words) <= MISS_WORDS_MAX and not all(word in _MADE_OUT for word in words)):
                look.misses += 1
                if look.misses >= MISSES_FOR_TAP:
                    look.tap_open = True
                    return {"action": "tap"}
            return {"action": None}

    def emergency(self):
        """During a count, the same as Undo. A look stays."""
        return self.undo()

    # ----- the page -----

    def tap(self):
        """True, and the count starts, only when two misses opened the tap."""
        with self._lock:
            now = self._clock()
            look = self._current(now)
            if look is None or look.state != "look" or not look.tap_open:
                return False
            self._start_count(look, now)
            return True

    def undo(self):
        """Stops a count. The line stays said; misses and the tap start over."""
        with self._lock:
            look = self._current(self._clock())
            if look is None or look.state != "counting":
                return False
            self._back_to_look(look)
            return True

    def take(self, skill, look_id):
        """The frozen content, once only: a dict for mint_ticket and send_mail, or None. A count must have run its full
        five seconds and be no older than COUNT_STALE_S. The look is then used up, whatever the result."""
        with self._lock:
            now = self._clock()
            look = self._current(now)
            if look is None or look.state != "counting" or look.id != look_id or look.skill != skill:
                return None
            if now < look.count_from + COUNT_S:
                return None
            to, subject, body, pictures = look.content
            look.state, look.content = "sending", None
            if asks_for(f"{subject}\n{body}"):
                self._look = None
                return None
            return {"to": to, "subject": subject, "body": body,
                    "pictures": [{"name": name, "data": data} for name, data in pictures]}

    def finish(self, look_id):
        """The send is over, whatever came of it. Clears the used look, if a new one hasn't replaced it."""
        with self._lock:
            if self._look is not None and self._look.id == look_id and self._look.state == "sending":
                self._look = None
