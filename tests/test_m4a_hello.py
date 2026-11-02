from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M4a: everything she says is in the talk history. The brain-made hello (mary.open_line, POST /api/mary/open), the
/api/mary/live/said dedupe and mary.see_image, with Gemini faked; the page side (say, openingLine, startTalk) with Node."""
import copy
import subprocess
import unittest
from unittest import mock

import mary
import server
from tests.test_story_js import APP, NODE, ROOT, between, read

KEY = "test-key"
HELLO = "Good morning, Andy. How's that knee today?"
ANSWER = "It's better, thanks."


class BrainCase(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        self.path = server.DATA / "mary" / "memory.json"
        self.path.unlink(missing_ok=True)
        self.addCleanup(self.path.unlink, True)
        self.bodies, self.deadlines, self.answers = [], [], []
        real = server.mary_settings
        for target, name, value in ((server, "mary_settings", lambda: dict(real(), key=KEY, model="m")),
                                    (mary, "_gemini_stream", self.stream)):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)

    def stream(self, body, api_key, model="", deadline_s=None):
        self.bodies.append(copy.deepcopy(body))
        self.deadlines.append(deadline_s)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        yield from answer

    def memory(self):
        return mary.Memory(self.path)

    def seed(self, *turns):
        memory = self.memory()
        for role, text in turns:
            memory.add_turn(role, text)
        memory.save()

    def turns(self):
        return [(t["role"], t["text"]) for t in self.memory().recent]

    @staticmethod
    def contents(body):
        return [(c["role"], c["parts"][0]["text"]) for c in body["contents"]]

    @staticmethod
    def system(body):
        return body["systemInstruction"]["parts"][0]["text"]


NOTE = "The note is saved."


class HelloInHistoryTest(BrainCase):
    """M21a: the app's note goes in as a one-off turn note; only her answer is saved, as her turn."""

    def hello_then_answer(self):
        self.answers = [[HELLO], ["Glad to hear it."]]
        status, got = helpers.api("POST", "/api/mary/tell", {"note": NOTE})[:2]
        self.assertEqual((status, got), (200, {"text": HELLO}))
        self.assertEqual(helpers.api("POST", "/api/mary/talk", {"text": ANSWER})[0], 200)
        return self.contents(self.bodies[1])

    def test_blank_history(self):
        self.assertEqual(self.hello_then_answer(),
                         [("user", mary.OPEN_NUDGE), ("model", HELLO), ("user", ANSWER)])  # the talk body's placeholder

    def test_history_ending_on_her_turn_merges(self):
        self.seed(("user", "Tell me about the ducks."), ("model", "They were lovely."))
        self.assertEqual(self.hello_then_answer(),
                         [("user", "Tell me about the ducks."), ("model", "They were lovely.\n" + HELLO), ("user", ANSWER)])

    def test_history_ending_on_their_turn(self):
        self.seed(("user", "I have to go now."))
        self.assertEqual(self.hello_then_answer(),
                         [("user", "I have to go now."), ("model", HELLO), ("user", ANSWER)])

    def test_history_starting_on_her_turn(self):
        self.seed(("model", "Hello there."))
        self.assertEqual(self.hello_then_answer(),
                         [("user", mary.OPEN_NUDGE), ("model", "Hello there.\n" + HELLO), ("user", ANSWER)])

    def test_saved_once_and_the_note_never(self):
        self.answers = [[HELLO]]
        helpers.api("POST", "/api/mary/tell", {"note": NOTE})
        self.assertEqual(self.turns(), [("model", HELLO)])  # her answer, as her turn; the note is not saved
        self.answers = [["Glad to hear it."]]
        helpers.api("POST", "/api/mary/talk", {"text": ANSWER})
        self.assertIn(NOTE, self.system(self.bodies[0]))
        self.assertNotIn(NOTE, self.system(self.bodies[1]))
        self.assertNotIn(mary.TELL_NUDGE, [t[1] for t in self.turns()])
        self.assertNotIn(NOTE, " ".join(t[1] for t in self.turns()))


class TellLineTest(BrainCase):
    def test_same_brain_and_history(self):
        memory = self.memory()
        memory.name = "Andy"
        memory.add_fact("Andy's knee has been sore")
        memory.add_turn("user", "My knee hurts.")
        memory.add_turn("model", "I'm sorry to hear that.")
        memory.save()
        self.answers = [[HELLO]]
        self.assertEqual(mary.tell_line(self.memory(), KEY, "m", "mary", NOTE), HELLO)
        body = self.bodies[0]
        self.assertEqual(self.contents(body), [("user", "My knee hurts."), ("model", "I'm sorry to hear that."),
                                               ("user", mary.TELL_NUDGE)])
        system = self.system(body)
        self.assertTrue(system.startswith(mary.system_text(self.memory(), "mary", facts=True)))
        self.assertIn("Name: Andy", system)
        self.assertIn("Andy's knee has been sore", system)
        self.assertIn(NOTE, system)
        self.assertIn("in your own words", system)
        self.assertNotIn("tools", body)
        self.assertEqual(body["generationConfig"]["thinkingConfig"], {"thinkingLevel": "low"})
        self.assertEqual(self.deadlines, [mary.OPEN_DEADLINE_S])

    def test_tags_and_markdown_are_stripped(self):
        self.answers = [["[mood: happy] **Good morning.** [remember: likes ducks] How's it going? [name: An"]]
        self.assertEqual(mary.tell_line(self.memory(), KEY, note=NOTE), "Good morning. How's it going?")

    def test_a_line_cut_off_ends_on_a_whole_sentence(self):
        self.answers = [["Good morning, Andy. How did the doc"]]
        self.assertEqual(mary.tell_line(self.memory(), KEY, note=NOTE), "Good morning, Andy.")

    def test_retries_without_thinking_after_a_fast_failure(self):
        self.answers = [RuntimeError("400"), [HELLO]]
        self.assertEqual(mary.tell_line(self.memory(), KEY, note=NOTE), HELLO)
        self.assertIn("thinkingConfig", self.bodies[0]["generationConfig"])
        self.assertNotIn("thinkingConfig", self.bodies[1]["generationConfig"])
        self.assertLess(self.deadlines[1], mary.OPEN_DEADLINE_S + 0.01)

    def test_a_timeout_is_not_retried(self):
        self.answers = [TimeoutError()]
        self.assertEqual(mary.tell_line(self.memory(), KEY, note=NOTE), "")
        self.assertEqual(len(self.bodies), 1)

    def test_any_failure_is_empty_and_saves_nothing(self):
        self.answers = [RuntimeError("down"), RuntimeError("down")]
        status, got, _ = helpers.api("POST", "/api/mary/tell", {"note": NOTE})
        self.assertEqual((status, got), (200, {"text": ""}))
        self.assertEqual(self.turns(), [])

    def test_nothing_said_is_empty(self):
        self.answers = [[]]
        self.assertEqual(mary.tell_line(self.memory(), KEY, note=NOTE), "")

    def test_no_key_or_no_note_never_asks(self):
        self.assertEqual(mary.tell_line(self.memory(), "", note=NOTE), "")
        self.assertEqual(mary.tell_line(self.memory(), KEY, note="  "), "")
        self.assertEqual(self.bodies, [])

    def test_a_long_note_is_cut(self):
        self.answers = [[HELLO]]
        mary.tell_line(self.memory(), KEY, note="x" * (mary.TELL_NOTE_MAX + 200))
        self.assertNotIn("x" * (mary.TELL_NOTE_MAX + 1), self.system(self.bodies[0]))


class SaidDedupeTest(BrainCase):
    def said(self, text):
        self.assertEqual(helpers.api("POST", "/api/mary/live/said", {"text": text})[0], 200)

    def test_emergency_words_are_not_doubled(self):
        _, got, _ = helpers.api("POST", "/api/mary/heard", {"text": "I can't breathe"})
        self.assertTrue(got["emergency"])
        self.assertIn("steps", got)
        self.assertNotIn("say", got)
        self.assertEqual(self.turns(), [("user", "I can't breathe")])  # D1: the steps are not her turn; her own words are
        self.said("I'm here, press your call light.")
        self.assertEqual(self.turns(), [("user", "I can't breathe"), ("model", "I'm here, press your call light.")])

    def test_the_same_line_twice_in_a_row_is_one_turn(self):
        self.said("I didn't catch that.")
        self.said("  I didn't   catch that. ")
        self.assertEqual(self.turns(), [("model", "I didn't catch that.")])

    def test_a_long_line_matches_where_it_was_cut(self):
        long_line = "word " * 300
        self.said(long_line)
        self.said(long_line)
        self.assertEqual(len(self.turns()), 1)

    def test_a_different_line_is_saved(self):
        self.said("One thing.")
        self.said("Another thing.")
        self.assertEqual(len(self.turns()), 2)

    def test_the_same_line_after_their_turn_is_saved(self):
        self.seed(("model", "How are you?"), ("user", "Fine."))
        self.said("How are you?")
        self.assertEqual(self.turns()[-1], ("model", "How are you?"))
        self.assertEqual(len(self.turns()), 3)

    def test_not_english_guard_stays(self):
        self.said("这是一段中文文字")
        self.assertEqual(self.turns(), [])


class SeeImageTest(BrainCase):
    def see(self, data=b"abc", key=KEY):
        return mary.see_image(data, "image/jpeg", "What is it?", key, "m")

    def test_one_small_ask(self):
        self.answers = [["YES\nA red bird.  "]]
        self.assertEqual(self.see(), "YES\nA red bird.")
        body = self.bodies[0]
        parts = body["contents"][0]["parts"]
        self.assertEqual(parts[0], {"inlineData": {"mimeType": "image/jpeg", "data": "YWJj"}})
        self.assertEqual(parts[1], {"text": "What is it?"})
        self.assertNotIn("systemInstruction", body)
        self.assertEqual(body["generationConfig"]["thinkingConfig"], {"thinkingLevel": "low"})
        self.assertEqual(self.deadlines, [mary.VISION_DEADLINE_S])

    def test_retries_without_thinking_after_a_fast_failure(self):
        self.answers = [RuntimeError("400"), ["NO\nA logo."]]
        self.assertEqual(self.see(), "NO\nA logo.")
        self.assertNotIn("thinkingConfig", self.bodies[1]["generationConfig"])

    def test_a_big_picture_is_not_sent(self):
        self.assertEqual(self.see(b"x" * (mary.VISION_BYTES_MAX + 1)), "")
        self.assertEqual(self.bodies, [])

    def test_never_raises(self):
        self.assertEqual(self.see(key=""), "")
        self.assertEqual(self.see(b""), "")
        self.assertEqual(self.see(12345), "")
        self.answers = [RuntimeError("down"), RuntimeError("down")]
        self.assertEqual(self.see(), "")

    def test_the_key_stays_with_the_server(self):
        with mock.patch.object(mary, "see_image", return_value="YES") as see:
            self.assertEqual(server.mary_see_image(b"x", "image/png", "q"), "YES")
        see.assert_called_once_with(b"x", "image/png", "q", KEY, "m")

    def test_the_host_is_wired(self):
        server.set_skill_host_for_tests(None)
        self.addCleanup(server.set_skill_host_for_tests, None)
        self.assertIs(server.skill_host().vision, server.mary_see_image)


STUBS = r"""
var posted = [], events = [];
var S = { screen: 'everyday', hasKey: true, phase: 'idle', talkOrder: [] }, CapS = {};
var Live = { open: false, takes: true }, Net = { open: '' }, Mode = { v: 'normal' };
var LIVE_SAY = '(';
var window = { MaryLive: { stopSpeaking: function () {} } };
var App = { onActivity: function () {} };
function log() {}
function sayForcedOnce() { return Promise.resolve(); }
function api(method, url, body) {
  posted.push(url + ' ' + (body.text || body.when || ''));
  if (url !== '/api/mary/open') { return Promise.resolve({}); }
  return Net.open instanceof Error ? Promise.reject(Net.open) : Promise.resolve({ text: Net.open });
}
function liveOn() { return Live.open; }
function greetLive() { return Live.takes; }
function spStart() { events.push('speak'); S.phase = 'speaking'; return {}; }
function waitSess() { S.phase = 'idle'; return Promise.resolve(); }
function setMood() {}
function showCaption() {}
function capLiveEmergency() {}
function quietWhole() {}
function splitSentences() { return { sentences: [] }; }
function spAdd() {}
function spEnd() {}
function setPhase(p) { S.phase = p; }
function timeWord() { return 'morning'; }
function nextMode() { return Mode.v; }
function liveSupported() { return true; }
function speechModeFor() { return ''; }
function updateTalkButton() {}
function wakeHoldCheck() {}
function lockTalkVoice() { return Promise.resolve(); }
function liveHello() { return 'live hello'; }
function startLive(c, hello) { events.push('live:' + hello); }
function convoListen() { events.push('listen'); }
function openTyping() { events.push('typing'); }
function eq(a, b, what) {
  if (JSON.stringify(a) !== JSON.stringify(b)) { throw new Error(what + ': ' + JSON.stringify(a)); }
}
function tick() { return new Promise(function (r) { setTimeout(r, 5); }); }
"""

CHECKS = r"""
var SAID = '/api/mary/live/said ', OPEN = '/api/mary/open morning';
(async function () {
  await say('Hello there.', 'happy');
  eq(posted, [SAID + 'Hello there.'], 'say posts once');
  posted.length = 0;
  await say('Saved already.', 'happy', undefined, true);
  await say('   ');
  eq(posted, [], 'a saved or empty line posts nothing');
  Live.open = true;
  await say('Through Live.');
  eq(posted, [], 'Live saves its own');
  Live.takes = false;
  await say('Live refused.');
  eq(posted, [SAID + 'Live refused.'], 'a line Live refused goes the usual way');
  Live.open = false; Live.takes = true; posted.length = 0;

  Net.open = 'Hi, Andy.';
  var waiting = openingLine('Scripted.');
  eq(S.phase, 'thinking', 'thinking while it comes');
  eq(await waiting, { text: 'Hi, Andy.', saved: true }, 'the brain hello');
  eq(posted, [OPEN], 'asked with the time of day');
  Net.open = new Error('down');
  eq(await openingLine('Scripted.'), { text: 'Scripted.', saved: false }, 'a failure uses the script');
  Net.open = '';
  eq(await openingLine('Scripted.'), { text: 'Scripted.', saved: false }, 'an empty answer uses the script');
  S.hasKey = false; posted.length = 0; S.phase = 'idle';
  eq(await openingLine('Scripted.'), { text: 'Scripted.', saved: false }, 'no key');
  eq(posted, [], 'no key, no call');
  eq(S.phase, 'idle', 'no key, no thinking');
  S.hasKey = true;
  Net.open = 'Hi.';
  waiting = openingLine('Scripted.');
  S.screen = 'emergency'; S.phase = 'speaking';
  eq(await waiting, { text: '', saved: false }, 'an emergency while it comes: she says nothing');
  S.screen = 'pictures'; S.phase = 'idle';
  waiting = openingLine('Scripted.');
  eq(await waiting, { text: '', saved: false }, 'another screen too');
  eq(S.phase, 'idle', 'and she does not stay thinking');
  S.screen = 'everyday';

  async function talk(opts) {
    posted.length = 0; events.length = 0; S.convo = null; S.phase = 'idle';
    await startTalk(opts);
    await tick();
    return posted.slice();
  }
  eq(await talk({ say: 'Tell me about yourself.' }), [SAID + 'Tell me about yourself.'], 'a plain line is saved once');
  eq(events, ['speak', 'listen'], 'said, then she listens');
  Net.open = 'Morning, Andy.';
  eq(await talk({ say: 'Scripted.', brainHello: true }), [OPEN], 'the brain hello is not saved again');
  eq(events, ['speak', 'listen'], 'the brain hello, then she listens');
  Net.open = new Error('down');
  eq(await talk({ say: 'Scripted.', brainHello: true }), [OPEN, SAID + 'Scripted.'], 'the fallback is saved');
  Mode.v = 'live';
  eq(await talk({ say: 'Scripted.', brainHello: true }), [], 'Live keeps its own hello');
  eq(events, ['live:live hello'], 'liveHello');
  Mode.v = 'normal'; S.typingOnly = true; Net.open = 'Morning.';
  eq(await talk({ say: 'Scripted.', brainHello: true }), [OPEN], 'no mic: the brain hello too');
  eq(events, ['speak'], 'no mic: only said');
  eq(await talk({ say: 'Scripted.' }), [SAID + 'Scripted.'], 'no mic, plain line');
  console.log('OK hello');
})().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
"""


@unittest.skipUnless(NODE, "Node not found: the page checks were skipped")
class PageTest(unittest.TestCase):
    def test_say_open_and_start(self):
        src = read(APP)
        code = "\n".join([
            STUBS,
            between(src, "function say(text, mood, voice, saved)", "// ---------------------------------------------------------------- screens"),
            between(src, "function rememberSaid(", "// M4a: her finished Live turn"),
            between(src, "function openingLine(", "// --- end M4a ---"),
            between(src, "function startTalk(opts)", "// M4a: decides c.voice"),
            CHECKS,
        ])
        run = subprocess.run([NODE, "-"], input=code, capture_output=True, text=True, encoding="utf-8",
                             timeout=30, cwd=ROOT)
        out = (run.stdout + run.stderr).strip()
        self.assertEqual(run.returncode, 0, out[-1500:])
        self.assertTrue(run.stdout.strip().startswith("OK "), out[-500:])

    def test_firstrun_has_no_saving_of_its_own(self):
        src = read(APP.replace("app.js", "firstrun.js"))
        self.assertNotIn("rememberSaid", src)
        self.assertIn("brainHello: true", between(src, "function talkOnOpen()", "// M4a: after the first hello"))
        self.assertIn("A.openingLine(", between(src, "function greet()", 'function talkOnOpen()'))
        self.assertNotIn("brainHello", between(src, "await askName();", "// ====="))


if __name__ == "__main__":
    unittest.main()
