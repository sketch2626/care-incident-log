from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""Guards for the standing decisions in docs/decisions.md.

D1  no built-in speech: every word she says is the model answering the resident.
D2/D3  her prompt is capped at its size before M21a; a fix removes before it adds.

A failure message says which decision broke. Read docs/decisions.md before "fixing" a test here.
"""
import inspect
import re
import tempfile
import unittest
from pathlib import Path

import mary
import voices
from tests.test_mary import FakeGemini, KEY

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "mary"

# ---------------------------------------------------------------- D2/D3: the prompt caps
# Sizes in characters at commit 9940dee, before M21a, measured with empty memory, no history, no skills and the FACTS below.
# Lowering a cap is fine. Raising one needs Andy's approval (D3). M21c lowers them when the lean brain lands.
#                       before (9940dee)   now (M21a piece 5)
#   Normal prompt          34,864            34,840
#   Live prompt            37,285            37,261
#   mary/instructions.md   28,600            28,600   (what the two prompts are mostly made of)
#   CHARACTER_NOTE          4,641             4,641
#   LIVE_EXTRA              1,050             1,050
NORMAL_CAP = 34864
LIVE_CAP = 37285
INSTRUCTIONS_CAP = 28600
CHARACTER_NOTE_CAP = 4641
LIVE_EXTRA_CAP = 1050
# M21c: the lean brain (mary/lean.md), Sam's size, the larger, with these same FACTS. Mary is 11,588 and 12,040. The full
# caps above stay until Andy approves lean as the default.
# Raised by 338 on 2026-11-02 with Andy's approval (D3): the North Carolina absentee-ballot line and the scam line.
LEAN_NORMAL_CAP = 12036
LEAN_LIVE_CAP = 12488
# M21d: the leaner brain (mary/leaner.md), Sam's size, the larger, with these same FACTS. Mary is 7,123 and 7,585.
LEANER_NORMAL_CAP = 7228
LEANER_LIVE_CAP = 7690
# M21d: what leaner's own safety text must keep, every rule's key words and every number (D5).
LEANER_SAFETY = ("press the call light", "call out for staff", "call 911", "drooping face", "weak arm", "slurred speech",
                 "sudden confusion", "spinal cord injury", "autonomic dysreflexia", "call or text 988",
                 "any time, day or night", "Veterans Crisis Line", "call 988 and press 1", "text 838255", "never instead",
                 "take it seriously", "getting in trouble", "it's not okay", "only then offer to write it down", "long-term care ombudsman", '"retaliation"',
                 "They're not allowed to punish you for speaking up. It's against the law.", "You never report them",
                 "you won't help with that", "the chaplain", "toward the weapon", "Never diagnose", "medicines or doses",
                 "their nurse or doctor", "once per problem", "Never say you have written anything",
                 "Don't name or blame staff", "Their usual first step", "the state or the ombudsman", "legal right",
                 "not the facility", "You never replace them", "push them to report")
# M21d: Andy's choices the brief says leaner keeps.
LEANER_CHOICES = ("Guns, hunting, faith, prayer", "never moralize", "\"y'all\"", '"howdy"', '"sweetheart"', "absentee ballot",
                  "county board of elections", "sounds like a scam", "a paralyzed man in a North Carolina nursing home",
                  "Use their name rarely.", "You weren't thinking while they were away", "Keep praise for what truly earns it.")


# The app's own facts block is machine-dependent (printer, wake word), so the caps are measured with these fixed facts,
# a long case: every line of the block shows.
FACTS = {"voice_now": "builtin", "picked_voice": "", "talk_mode": "handsfree", "wake_word": False,
         "talk_choice": "live", "talk_on_open": True, "voice_rate": 0.8, "voice_volume": 0.4, "printer": False}


def _empty_memory():
    return mary.Memory(Path(tempfile.mkdtemp(prefix="d2-", dir=helpers.TMP)) / "memory.json")


def _too_big(what, size, cap):
    return (f"D2/D3 broke: {what} is {size} characters, over its cap of {cap}. A fix removes before it adds: reword or "
            f"delete something first. Raising a cap needs Andy's approval. Read docs/decisions.md.")


class PromptCap(unittest.TestCase):
    def setUp(self):
        real = mary.app_facts
        mary.app_facts = lambda companion: dict(FACTS)
        self.addCleanup(setattr, mary, "app_facts", real)

    def test_d2_prompt_cap_normal(self):
        body = mary._body("hello", _empty_memory(), None, "mary")
        size = len(body["systemInstruction"]["parts"][0]["text"])
        self.assertLessEqual(size, NORMAL_CAP, _too_big("her Normal-talk prompt", size, NORMAL_CAP))
        n = len(mary.CHARACTER_NOTE)
        self.assertLessEqual(n, CHARACTER_NOTE_CAP, _too_big("CHARACTER_NOTE", n, CHARACTER_NOTE_CAP))
        n = len(mary.load_instructions("mary"))
        self.assertLessEqual(n, INSTRUCTIONS_CAP, _too_big("mary/instructions.md", n, INSTRUCTIONS_CAP))

    def test_d2_prompt_cap_live(self):
        size = len(voices.live_system(memory=_empty_memory()))
        self.assertLessEqual(size, LIVE_CAP, _too_big("her Live prompt", size, LIVE_CAP))
        n = len(voices.LIVE_EXTRA)
        self.assertLessEqual(n, LIVE_EXTRA_CAP, _too_big("LIVE_EXTRA", n, LIVE_EXTRA_CAP))

    def test_d2_lean_prompt_cap(self):  # M21c: the lean brain's own caps, for both companions, safety sections included
        self.addCleanup(setattr, mary, "brain_setting", mary.brain_setting)
        mary.brain_setting = lambda: "lean"
        for who in ("mary", "him"):
            body = mary._body("hello", _empty_memory(), None, who)
            size = len(body["systemInstruction"]["parts"][0]["text"])
            self.assertLessEqual(size, LEAN_NORMAL_CAP, _too_big(f"the lean Normal prompt ({who})", size, LEAN_NORMAL_CAP))
            size = len(voices.live_system(who, memory=_empty_memory()))
            self.assertLessEqual(size, LEAN_LIVE_CAP, _too_big(f"the lean Live prompt ({who})", size, LEAN_LIVE_CAP))

    def test_d2_leaner_prompt_cap(self):  # M21d
        self.addCleanup(setattr, mary, "brain_setting", mary.brain_setting)
        mary.brain_setting = lambda: "leaner"
        for who in ("mary", "him"):
            body = mary._body("hello", _empty_memory(), None, who)
            size = len(body["systemInstruction"]["parts"][0]["text"])
            self.assertLessEqual(size, LEANER_NORMAL_CAP, _too_big(f"the leaner Normal prompt ({who})", size, LEANER_NORMAL_CAP))
            size = len(voices.live_system(who, memory=_empty_memory()))
            self.assertLessEqual(size, LEANER_LIVE_CAP, _too_big(f"the leaner Live prompt ({who})", size, LEANER_LIVE_CAP))

    def test_d5_leaner_keeps_every_safety_rule_and_number(self):  # M21d: in the safety text, and in what is really sent
        self.addCleanup(setattr, mary, "brain_setting", mary.brain_setting)
        mary.brain_setting = lambda: "leaner"
        both = mary._brain_blocks("leaner")["both"]
        safety = both[both.index("Emergencies come first"):]
        for who in ("mary", "him"):
            normal = mary._body("hello", _empty_memory(), None, who)["systemInstruction"]["parts"][0]["text"]
            live = voices.live_system(who, memory=_empty_memory())
            for words in LEANER_SAFETY:
                for text, where in ((safety, "its safety text"), (normal, "Normal"), (live, "Live")):
                    self.assertIn(words, text, f"D5 broke: the leaner brain lost {words!r} in {where} ({who}).")

    def test_leaner_keeps_andys_choices(self):  # M21d
        self.addCleanup(setattr, mary, "brain_setting", mary.brain_setting)
        mary.brain_setting = lambda: "leaner"
        for who in ("mary", "him"):
            for text in (mary.load_instructions(who), voices.live_system(who, memory=_empty_memory())):
                for words in LEANER_CHOICES:
                    self.assertIn(words, text, f"The leaner brain lost Andy's choice {words!r} ({who}).")


# ---------------------------------------------------------------- D1: the page
# Named exception, for Andy to rule on: web/mary/voices.js (the voice tryout page) plays a fixed sample so the
# resident can pick a voice. It is not scanned here. Same page, same exception: web/mary/live.js (the Live demo on
# voices.html) opens with GREET, an instruction asking the model for a short hello. The model writes the words, but
# it is a hello on open, so Andy should rule on it too. Not scanned.
TRYOUT_PAGE = {"voices.js", "live.js"}
#
# What she reads word for word today (tool results the model reads out, allowed by the M21a brief), all in
# web/mary/screens.js:
#   line 178  'Say "Ask if you need me." and nothing more.'            (the book opened)
#   line 498  'Spell "<value>" letter by letter ... ask "Is that right?"'  (reading a detail back)
#   line 499  'Say "<value>" back and ask "Is that right?"'
#   line 598  'Ask in exactly these words: "<which person?>" Then wait.'
#   line 614  'Say "Here's <first name>." and nothing more.'            (a person's card opened)
# and the story lines: storyNextLine() in app.js carries model-written story text.

SCANNED = ["app.js", "firstrun.js", "screens.js", "skills.js"]
# Variables that hold model words, as they are today. Anything new here is a decision for Andy (D1).
SPEAK_MODEL_OK = {"text", "S.lastWords"}
SP_ADD_OK = {"parts[i]", "r.sentences[i]", "tail[i]"}  # second argument: the sentence; the first is the session
GREET_LIVE_OK = {"hello", "text", "said.live", "LIVE_PICK_UP", "String(open.note || '')"}
GREET_LIVE_CALLS_OK = ("liveSafetyText(", "storyNextLine(")  # an instruction wrapper, and model-written story text


def _strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(^|[\s;,{}()])//[^\n]*", r"\1", src)  # not the // in a URL: it follows a colon


def _page_files(all_js=False):
    if all_js:
        files = sorted(p for p in WEB.glob("*.js") if p.name not in TRYOUT_PAGE)
    else:
        files = [WEB / n for n in SCANNED] + sorted((ROOT / "skills").glob("*/screen.js"))
    return [(p, _strip_comments(p.read_text(encoding="utf-8"))) for p in files]


def _args(src, open_idx):
    """The top-level arguments of the call whose '(' is at open_idx."""
    depth, quote, cur, out, i = 0, None, [], [], open_idx
    while i < len(src):
        ch = src[i]
        if quote:
            cur.append(ch)
            if ch == "\\":
                cur.append(src[i + 1])
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
            cur.append(ch)
        elif ch in "([{":
            depth += 1
            if depth > 1:
                cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                out.append("".join(cur).strip())
                return out
            cur.append(ch)
        elif ch == "," and depth == 1:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    return out


def _calls(name):
    """(file, args) for each call of name( in the scanned page code, not its function declaration."""
    found = []
    for path, src in _page_files():
        for m in re.finditer(r"(?<![\w$.])" + re.escape(name) + r"\(", src):
            if src[max(0, m.start() - 9):m.start()] == "function ":
                continue
            found.append((path.name, _args(src, m.end() - 1)))
    return found


def _broke(what):
    return f"D1 broke (no built-in speech): {what} Every word she says must come from the model. Read docs/decisions.md."


class PageSpeaksOnlyModelWords(unittest.TestCase):
    def test_d1_no_say_function_and_no_live_say(self):
        bad = re.compile(r"LIVE_SAY|(?<![\w$.])say\(|\b(?:A|App|a|MaryApp)\.say\(|\bapp\(\)\.say\(")
        for path, src in _page_files():
            m = bad.search(src)
            self.assertIsNone(m, _broke(f"{path.name} has `{m and m.group(0)}`, a way to say a fixed line."))

    def test_d1_speak_model_takes_only_model_words(self):
        calls = _calls("speakModel")
        self.assertTrue(calls, "D1 guard is blind: no speakModel( call found. Update the guard, not the decision.")
        for name, args in calls:
            first = args[0] if args else ""
            self.assertFalse(first[:1] in "'\"`" or first.startswith("MSG."),
                             _broke(f"{name} calls speakModel({first}...), a fixed line."))
            self.assertIn(first, SPEAK_MODEL_OK,
                          _broke(f"{name} calls speakModel({first}...); only {sorted(SPEAK_MODEL_OK)} hold model words."))

    def test_d1_sp_add_takes_only_model_words(self):
        calls = _calls("spAdd")
        self.assertTrue(calls, "D1 guard is blind: no spAdd( call found. Update the guard, not the decision.")
        for name, args in calls:
            second = args[1] if len(args) > 1 else ""
            self.assertFalse(second[:1] in "'\"`" or second.startswith("MSG."),
                             _broke(f"{name} calls spAdd(..., {second}), a fixed line."))
            self.assertIn(second, SP_ADD_OK,
                          _broke(f"{name} calls spAdd(..., {second}); only {sorted(SP_ADD_OK)} hold model words."))

    def test_d1_greet_live_gets_instructions_not_lines(self):
        calls = _calls("greetLive")
        self.assertTrue(calls, "D1 guard is blind: no greetLive( call found. Update the guard, not the decision.")
        for name, args in calls:
            first = args[0] if args else ""
            if first[:1] in "'\"`":
                self.assertTrue(first[1:2] == "(",
                                _broke(f"{name} calls greetLive({first[:40]}...): a literal must be an instruction in ( )."))
                continue
            ok = first in GREET_LIVE_OK or first.startswith(GREET_LIVE_CALLS_OK)
            self.assertTrue(ok, _broke(f"{name} calls greetLive({first[:40]}...): not a known instruction or model-written line."))
        for name in ("app.js", "firstrun.js"):
            src = _strip_comments((WEB / name).read_text(encoding="utf-8"))
            for phrase in ("word for word", "exactly these words"):
                self.assertNotIn(phrase, src, _broke(f"{name} tells her to say something {phrase!r}."))

    def test_d1_no_hello_on_open_or_wake_and_no_goodbye(self):
        names = re.compile(r"\b(?:WAKE_SAY|LIVE_HELLO|OPEN_WAYS|GREET|goodbyeLine)\b|\bliveBye\(")
        for path, src in _page_files(all_js=True):
            m = names.search(src)
            self.assertIsNone(m, _broke(f"{path.name} has `{m and m.group(0)}`, a canned hello or goodbye."))

    def test_d1_mary_say_route_has_one_caller(self):
        callers = [p.name for p, src in _page_files(all_js=True) if "/api/mary/say" in src]
        self.assertEqual(callers, ["voiceout.js"], _broke(f"/api/mary/say is reached from {callers}; only speakOne may."))
        voiceout = _strip_comments((WEB / "voiceout.js").read_text(encoding="utf-8"))
        self.assertEqual(voiceout.count("fetch('/api/mary/say'"), 1,
                         _broke("voiceout.js should reach /api/mary/say from one place only (the one-sentence fetch)."))


# ---------------------------------------------------------------- D1: the server
LINES = {
    "an ordinary line": "what is the weather like",
    "an emergency": "I fell and I can't get up",
    "a yes to an offer": "yes please",
    "forget that": "forget that",
}


class ServerSaysNothingOfItsOwn(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGemini()
        real = mary._gemini_stream
        mary._gemini_stream = self.fake
        self.addCleanup(setattr, mary, "_gemini_stream", real)

    def _ask(self, line, key):
        memory = _empty_memory()
        if line == "yes please":
            memory.pending_offer = mary._offer(mary._guess("the nurse never came"))
        return mary.reply(line, memory, key, write=lambda inc: 7)

    def test_d1_no_key_means_no_speech(self):
        for what, line in LINES.items():
            r = self._ask(line, "")
            self.assertEqual(r["text"], "", _broke(f"with no key, {what} got spoken text: {r['text'][:60]!r}."))

    def test_d1_failing_model_means_no_speech(self):
        self.fake.fail = True
        for what, line in LINES.items():
            r = self._ask(line, KEY)
            self.assertEqual(r["text"], "", _broke(f"with a failing model, {what} got spoken text: {r['text'][:60]!r}."))

    def test_d1_reply_emits_only_through_the_speak_path(self):
        src = inspect.getsource(mary.reply)
        calls = [m for m in re.finditer(r"(?<!def )\bemit\(([^\n]*)", src)]
        self.assertEqual(len(calls), 1, _broke(f"reply() calls emit( {len(calls)} times; only speak() may."))
        arg = calls[0].group(1)
        self.assertNotRegex(arg, r"_TEXT|['\"]", _broke(f"reply() emits a fixed line: emit({arg[:50]}."))
        before = src[:calls[0].start()]
        self.assertTrue(before.rfind("def speak(") > before.rfind("def show("),
                        _broke("reply() calls emit( outside speak()."))

    def test_d1_heard_has_no_say_and_open_is_gone(self):
        status, body, _ = helpers.api("POST", "/api/mary/heard", {"text": "Good morning"})
        self.assertEqual(status, 200)
        self.assertNotIn("say", body, _broke("/api/mary/heard answers with a `say` key."))
        status, _, _ = helpers.api("POST", "/api/mary/open", {})
        self.assertNotEqual(status, 200, _broke("/api/mary/open (a hello on open) is back."))


if __name__ == "__main__":
    unittest.main()
