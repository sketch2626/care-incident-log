from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M4d: crisis numbers said right (fix_numbers, the stream, Live captions and retries), the Live emergency line with the
Veterans line, and the prompt wording for items 3-7. Gemini is faked; the page's code runs in Node."""
import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

import mary
import server
from tests.test_m4a_bench import stream_text
from tests.test_m4c import FELL, LiveBase, new_memory
from tests.test_mary import FakeGemini, KEY
from tests.test_story_js import APP, NODE, ROOT, between, read

D988, D911, D838 = "nine, eight, eight", "nine one one", "eight three eight, two five five"
FIXES = ([(f"Call {x} now.", f"Call {D988} now.") for x in (
    "ninety-eight-eight", "Ninety eight eight", "nine eighty-eight", "nine-eighty-eight",
    "nine hundred and eighty-eight", "nine eight eight", "9-8-8", "9 8 8", "9.8.8")]
    + [(f"Call {x} now.", f"Call {D911} now.") for x in (
        "nine-eleven", "nine eleven", "nine hundred eleven", "nine-one-one", "9-1-1", "9 1 1")]
    + [("If it's serious, call nine-eleven.", f"If it's serious, call {D911}."),
       ("I'm having a heart attack, call nine-eleven", f"I'm having a heart attack, call {D911}")]
    + [(f"Text {x}.", f"Text {D838}.") for x in (
        "eight thirty-eight two fifty-five", "eight three eight two five five", "8-3-8-2-5-5")]
    + [("Then press the number one.", "Then press one."), ("Then press number 1.", "Then press one.")])
LEFT = ["nineteen eighty-eight", "1988", "Oldsmobile Ninety-Eight", "ninety-eight", "$9.88", "room 9110", "the 1911",
        "nine eight eight seven", "1-9-8-8", "after nine eleven", "since nine-eleven", "the towers on nine eleven",
        "September nine eleven", "at nine eleven in the morning"]


def node(code):
    run = subprocess.run([NODE, "-e", code], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def numbers_js():
    return between(read(APP), "function spokenNumbers(text)", "function greetLive")


class FixNumbers(unittest.TestCase):
    def test_wrong_forms_fixed(self):
        for text, want in FIXES:
            self.assertEqual(mary.fix_numbers(text), want, text)

    def test_left_alone(self):
        for text in LEFT:
            self.assertEqual(mary.fix_numbers(text), text, text)

    def test_idempotent(self):
        for text in [t for t, _ in FIXES] + LEFT:
            once = mary.fix_numbers(text)
            self.assertEqual(mary.fix_numbers(once), once, text)

    def test_press_one_spoken(self):
        self.assertEqual(mary.spoken_numbers("press 1"), "press one")


class Stream(unittest.TestCase):
    def test_split_chunks(self):
        for chunks in (["call ninety", "-eight", "-eight now."], ["call n", "ine", "-elev", "en."],
                       ["call nine", " eight", " eight now."]):
            got = stream_text(chunks)
            self.assertEqual(got, mary.fix_numbers("".join(chunks)), chunks)
        self.assertEqual(stream_text(["call ninety", "-eight", "-eight now."]), f"call {D988} now.")

    def test_ordinary_flows_at_once(self):
        said = []
        s = mary._ReplyStream(lambda piece, after: said.append(piece), lambda v: None)
        s.feed("Hello there, friend.")
        self.assertEqual("".join(said), "Hello there, friend.")

    def test_finish_returns_held_words_first(self):
        s = mary._ReplyStream(lambda *a: None, lambda v: None)
        s.feed("call ninety-eight [remember: x")
        self.assertTrue(s.finish().startswith("ninety-eight"))

    def test_attacks_stay(self):
        self.assertEqual(stream_text(["since ", "nine-eleven was hard."]), "since nine-eleven was hard.")


class ReplyAndSaving(unittest.TestCase):
    def test_reply_saves_the_fixed_form(self):
        fake = FakeGemini()
        fake.chunks = ["Please call ninety", "-eight", "-eight. I'm with you."]
        mem = new_memory()
        with mock.patch.object(mary, "_gemini_stream", fake):
            r = mary.reply("I feel low today", mem, KEY)
        self.assertIn(D988, r["text"])
        self.assertNotIn("ninety", r["text"])
        self.assertIn(D988, [t["text"] for t in mem.recent if t["role"] == "model"][-1])

    def test_live_said_saves_fixed(self):
        helpers.reset_db()
        status, _, _ = helpers.api("POST", "/api/mary/live/said", {"text": "Call ninety-eight-eight, friend."})
        self.assertEqual(status, 200)
        mem = mary.Memory(server.mary_memory_path()) if hasattr(server, "mary_memory_path") else None
        if mem is None:
            mem = mary.Memory(mary.default_memory_path())
        self.assertIn(f"Call {D988}, friend.", [t["text"] for t in mem.recent])

    def test_character_note(self):
        note = mary.CHARACTER_NOTE
        for want in (D988, "ninety-eight-eight"):
            self.assertIn(want, note)
        for bad in ("[", "Mary", "Sam"):
            self.assertNotIn(bad, note)


@unittest.skipUnless(NODE, "Node not found")
class PageNumbers(unittest.TestCase):
    def test_agrees_with_python(self):
        texts = [t for t, _ in FIXES] + LEFT + ["Call 988, or 911. Text 838255.", "press 1", "press 1-800"]
        code = numbers_js() + f"console.log(JSON.stringify({json.dumps(texts)}.map(function(t){{" \
            "return [fixNumbers(t), spokenNumbers(t)];})));"
        got = node(code)
        for text, (fixed, spoken) in zip(texts, got):
            self.assertEqual(fixed, mary.fix_numbers(text), text)
            self.assertEqual(spoken, mary.spoken_numbers(text), text)

    def test_correction_and_tail(self):
        code = numbers_js() + (
            "console.log(JSON.stringify([numberCorrection('call ninety-eight-eight'),"
            "numberCorrection('ninety-eight-eight or nine-hundred eleven'), numberCorrection('call 9-1-1'),"
            "['call ninety','call ninety-eight-','Call nine-eleven','since nine-eleven','hello there','press the','Call 98']"
            ".map(numberTail)]));")
        a, b, c, tails = node(code)
        self.assertEqual((a, c), (D988, ""))
        self.assertEqual(b.count(" and "), 1)
        self.assertIn(D988, b)
        self.assertIn(D911, b)
        for text, cut in zip(["call ninety", "call ninety-eight-", "Call nine-eleven", "since nine-eleven", "hello there",
                              "press the", "Call 98"], tails):
            self.assertEqual(cut, mary._number_cut(text), text)

    def live_caption(self, pieces, flush=False):
        src = read(APP)
        code = ("var out=[], CapS={numHeld:'',numLead:'',liveDone:false}; var NUM_SENTENCE_UNUSED=0;\n" + numbers_js() +
                between(src, "function capLivePiece(", "function capLiveWords(").replace(
                    "capLiveWords(", "capOut(") +
                "function capOut(t){ out.push(t); }\n" +
                f"{json.dumps(pieces)}.forEach(capLivePiece);" + ("capLiveFlush();" if flush else "") +
                "console.log(JSON.stringify(out));")
        return "".join(node(code))

    def test_live_captions(self):
        self.assertEqual(self.live_caption(["call ninety", "-eight", "-eight now"]), f"call {D988} now")
        self.assertEqual(self.live_caption(["call ninety", "-eight"], flush=True), "call ninety-eight")
        self.assertEqual(self.live_caption(["Hello there, friend."]), "Hello there, friend.")

    def test_live_number_fix(self):
        src = read(APP)
        code = ("var greeted=[]; function greetLive(t){greeted.push(t); return true;}\n" +
                between(src, "function liveNumberFix(", "function liveSafetyMissing(") +
                "var c={}; liveNumberFix(c,'nine, eight, eight'); liveNumberFix(c,'nine one one');"
                "var d={ending:true}; liveNumberFix(d,'x'); var e={story:true}; liveNumberFix(e,'x');"
                "liveNumberFix({},''); console.log(JSON.stringify([greeted,c.numFixed]));")
        greeted, fixed = node(code)
        self.assertEqual(greeted, ["(You said a number wrong. The right number is nine, eight, eight. Say it again, in your own words.)"])
        self.assertTrue(fixed)


class LiveEmergency(LiveBase):
    def test_dysreflexia_line(self):
        helpers.reset_db()
        _, got, _ = helpers.api("POST", "/api/mary/heard", {
            "text": "I'm paralyzed, and I've got a sudden pounding headache and I'm sweating all over."})
        self.assertTrue(got["emergency"])
        self.assertEqual(got["kind"], "medical")
        self.assertIn("911", got["steps"])
        self.assertNotIn("say", got)

    def test_emergency_text_veterans(self):
        plain = mary.EMERGENCY_TEXT["self_harm"]
        self.assertEqual(mary.emergency_text("self_harm", new_memory()), plain)
        self.assertEqual(mary.emergency_text("self_harm", new_memory(), "I'm a veteran"), plain + " " + mary.VETERANS_TEXT)
        for fact in ("served in the Navy", "a Navy vet"):
            self.assertIn(mary.VETERANS_TEXT, mary.emergency_text("self_harm", new_memory(facts=[fact])), fact)
        for no in ("navy blue", "dinner was served in my room", "the vet's office"):
            self.assertEqual(mary.emergency_text("self_harm", new_memory(), no), plain, no)
        self.assertNotIn(mary.VETERANS_TEXT, mary.emergency_text("medical", new_memory(), "I'm a veteran"))

        def boom():
            raise RuntimeError("locked")
        broken = SimpleNamespace(recent=[], facts=[], store=SimpleNamespace(active=boom))
        self.assertEqual(mary.emergency_text("self_harm", broken), plain)

    def test_heard_veteran(self):
        helpers.reset_db()
        _, got, _ = helpers.api("POST", "/api/mary/heard", {"text": "I'm a veteran and I want to kill myself"})
        self.assertIn("press 1", got["steps"])
        self.assertIn("988", got["steps"])

    def reply(self, chunks, key=KEY, **kw):
        fake = self.fake = FakeGemini()
        fake.chunks = chunks
        mem = new_memory(facts=["served in the Navy"], **kw)
        with mock.patch.object(mary, "_gemini_stream", fake):
            return mary.reply("I want to kill myself", mem, key), mem

    def test_veteran_reply(self):
        full = mary.emergency_text("self_harm", new_memory(facts=["served in the Navy"]))
        # D1: the steps go to the screen and into her turn note; her text is only her own words
        r, _ = self.reply(["Call the Veterans Crisis Line, 988 and press 1. I'm here with you."])
        self.assertEqual(r["steps"], full)
        self.assertIn(mary.VETERANS_TEXT, r["steps"])
        self.assertEqual(r["text"], "Call the Veterans Crisis Line, 988 and press 1. I'm here with you.")
        note = self.fake.bodies[0]["systemInstruction"]["parts"][0]["text"]
        self.assertIn(full, note)
        self.assertIn("Include the Veterans Crisis Line", note)
        r, _ = self.reply([], key="")
        self.assertEqual((r["steps"], r["text"]), (full, ""))


SAFETY_JS = ("var greeted=[], said=[], done=[], fixed=[], spoke=[], refuse=false;\n"
             "function greetLive(t){ if (refuse) { return false; } greeted.push(t); return true; }\n"
             "function liveSaid(c){said.push(1);} function liveTurnDone(c){done.push(1);}\n"
             "function liveNumberFix(c,f){fixed.push(f);} function say(w,m){spoke.push([w,m]);}\n"
             "function lastSentences(t){return t;} function screenLine(){} function showSteps(){}\n" +
             between(read(APP), "function liveSafetyText(", "// --- end M4a ---") + "\n")


@unittest.skipUnless(NODE, "Node not found")
class PageSafety(unittest.TestCase):
    def test_said_safety(self):
        cases = [("Help is coming. Call nine one one.", "Call 911 now.", True),
                 ("Call 911, friend.", "Call 911 now.", True),
                 ("Call nine-eleven.", "Call 911 now.", True),
                 ("Press your call light.", "Call 911 now.", False),
                 ("Call 988.", "Call 988 and press 1.", False),
                 ("Call 988 and press 1.", "Call 988 and press 1.", True)]
        code = numbers_js() + f"console.log(JSON.stringify({json.dumps(cases)}.map(function(k){{" \
            "return saidSafety(k[0], k[1]);})));"
        self.assertEqual(node(code), [c[2] for c in cases])

    def run_ended(self, steps):
        src = read(APP)
        code = (SAFETY_JS + numbers_js() +
                between(src, "function liveSafetyMissing(", "function liveByeCap(") + steps +
                "console.log(JSON.stringify({greeted:greeted,said:said.length,done:done.length,fixed:fixed,"
                "spoke:spoke,c:c}));")
        return node(code)

    def test_turn_ended(self):
        line = "Call 911 now."
        got = self.run_ended(f"var c={{saidText:'Hold on, I am here.',safetyWords:{json.dumps(line)}}};"
                             "liveTurnEnded(c,true); c.saidText='Call nine one one now.'; liveTurnEnded(c,true);")
        self.assertEqual(len(got["greeted"]), 1)  # once only: an instruction that carries every number
        self.assertIn("Call nine one one now.", got["greeted"][0])
        self.assertIn("own words", got["greeted"][0])
        self.assertEqual(got["done"], 1)
        self.assertEqual(got["c"]["safetyWords"], "")
        got = self.run_ended(f"var c={{saidText:'  ',safetyWords:{json.dumps(line)}}}; liveTurnEnded(c,true);")
        self.assertEqual((got["greeted"], got["c"]["safetyWords"]), ([], line))
        got = self.run_ended(f"refuse=true; var c={{saidText:'No.',safetyWords:{json.dumps(line)}}}; liveTurnEnded(c,true);")
        self.assertEqual(got["spoke"], [])  # M21a: the steps are on the screen already; she says nothing of her own
        got = self.run_ended(f"var c={{saidText:'No.',safetyWords:{json.dumps(line)}}}; liveTurnEnded(c,false);")
        self.assertEqual((got["greeted"], got["spoke"], got["done"], got["said"]), ([], [], 0, 1))


class PromptText(LiveBase):
    TEXT = mary.INSTRUCTIONS.read_text(encoding="utf-8")

    def test_item3_confused(self):
        for text in (self.TEXT, mary.CHARACTER_NOTE):
            self.assertIn("announce the death", text)
            self.assertIn("You miss him", text)
        for who in ("mary", "him"):
            self.assertIn("You miss him", self.live_prompt(new_memory(), who))

    def test_item4_note_ends_live(self):
        self.assertIn("Well, look at that", mary.CHARACTER_NOTE)
        for who in ("mary", "him"):
            self.assertTrue(self.live_prompt(new_memory(), who).endswith(mary.CHARACTER_NOTE), who)

    def test_item5_fear(self):
        note = mary.FEAR_NOTE
        self.assertNotIn("retaliation against", note)
        for want in ("not allowed to punish", "ombudsman", "stand up for residents"):
            self.assertIn(want, note)
        self.assertIn("punish you for speaking up", self.TEXT)
        self.assertIn("retaliation", self.TEXT)

    def test_item6_offers(self):
        self.assertIn("name that tune", self.TEXT)
        self.assertIn("What you can do", self.TEXT)
        self.assertIn("weather", mary.CHARACTER_NOTE)

    def test_item7_no_stock_hello(self):
        self.assertNotIn("well, hey there", self.TEXT.lower())


if __name__ == "__main__":
    unittest.main()
