from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M21a: "go to sleep" gets one goodnight and a quiet close, and her own voice never wakes
her. The page's real code runs in Node on a fake clock (the same page as test_m17_wake); the server rule runs directly."""
import json
import subprocess
import unittest
from unittest import mock

import server
import wakeword
from tests.test_m17_wake import PAGE
from tests.test_story_js import APP, NODE, ROOT, between, read

CONVO = between(read(APP), "function convoListen(c, tapped) {", "// After her answer")
EMERGENCY = between(read(APP), "function liveEmergency(c, j) {", "// --- M4a: in Live, Live speaks everything")
EXTRA = r"""
var talked = [];
function listenOnce() { return Promise.resolve('hello there'); }
function talkTo(t) { talked.push(t); return Promise.resolve(); }
function convoBye() { return Promise.resolve(); } function micMissGoesOn() { return false; }
function liveSafetyText(w) { return w; } function showSteps() {}
"""


def run(body):
    code = (PAGE + "\n" + EXTRA + "\n" + CONVO + "\n" + EMERGENCY + "\n(async function () {\n" + body +
            "\n})().catch(function (e) { console.error((e && e.stack) || e); process.exit(1); });\n")
    out = subprocess.run([NODE, "-"], input=code, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "Node is not installed")
class OneGoodnight(unittest.TestCase):
    def test_a_goodbye_sends_no_greet_and_goes_deaf(self):
        got = run("var c = talk(false); liveByeNow(c); out({ greets: greets.length, deaf: T.deaf, ending: c.ending, stop: count('stopSpeaking') });")
        self.assertEqual(got, {"greets": 0, "deaf": True, "ending": True, "stop": 0})

    def test_already_speaking_closes_when_her_turn_completes(self):
        got = run("var c = talk(true); liveByeNow(c); T.speaking = false; liveTurnDone(c); out({ open: !!S.convo, stops: stops });")
        self.assertEqual(got, {"open": False, "stops": ["end"]})

    def test_end_talk_closes_the_same_way(self):
        got = run("var c = talk(true); liveEndTalk(c); T.speaking = false; liveTurnDone(c); out({ open: !!S.convo, greets: greets.length });")
        self.assertEqual(got, {"open": False, "greets": 0})

    def test_end_talk_after_her_audio_turn_already_finished_closes_now(self):
        got = run("var c = talk(false); c.sawAudio = true; liveTurnDone(c); liveEndTalk(c); out({ open: !!S.convo });")
        self.assertEqual(got, {"open": False})

    def test_no_reply_closes_at_the_cap_in_silence(self):
        got = run("var c = talk(false); liveByeNow(c); var early = !!S.convo; tick(LIVE_BYE_MAX_MS + 1); out({ early: early, open: !!S.convo, greets: greets.length });")
        self.assertEqual(got, {"early": True, "open": False, "greets": 0})

    def test_word_check_and_end_talk_together_are_one_goodbye(self):
        got = run("var c = talk(true); liveByeNow(c); liveEndTalk(c); T.speaking = false; liveTurnDone(c); "
                  "tick(LIVE_BYE_MAX_MS + 1); out({ open: !!S.convo, greets: greets.length, stops: stops });")
        self.assertEqual(got, {"open": False, "greets": 0, "stops": ["end"]})

    def test_an_emergency_while_ending_hears_again(self):
        got = run("var c = talk(false); liveByeNow(c); liveEmergency(c, { steps: 'call' }); out({ deaf: T.deaf, ending: c.ending });")
        self.assertEqual(got, {"deaf": False, "ending": False})


@unittest.skipUnless(NODE, "Node is not installed")
class AwakeSheHearsEveryBox(unittest.TestCase):
    def test_the_emergency_screen_is_never_a_note(self):
        got = run("var c = talk(false); App.noteBusy(true); S.screen = 'emergency'; out({ d: dictating() });")
        self.assertEqual(got, {"d": False})

    def test_the_note_flag_reaches_heard(self):
        got = run("var c = talk(false); App.noteBusy(true); liveHeard(c, 'hello'); await flush(); out({ note: T.lastHeard.note });")
        self.assertEqual(got, {"note": True})

    def test_a_normal_line_heard_during_a_note_reaches_her(self):
        got = run(r"""
var c = talk(false); c.live = false; c.open = false; c.misses = 0; S.listenReason = '';
App.noteBusy(true); convoListen(c); await flush();
out({ talked: talked });
""")
        self.assertEqual(got, {"talked": ["hello there"]})

    def test_a_wake_in_a_talk_changes_nothing(self):
        got = run(r"""
var c = talk(false); App.noteBusy(true);
wake({ greeted: true }); await flush();
out({ deaf: !!T.deaf, noteBusy: !!S.noteBusy, greets: greets.length, talks: T.talks, busy: wakeBusy() });
""")
        self.assertEqual(got, {"deaf": False, "noteBusy": True, "greets": 0, "talks": 0, "busy": True})

    def test_d18_a_focused_box_on_a_deeper_screen_never_stops_her_hearing(self):
        got = run(r"""
var c = talk(false);
var box = { tagName: 'INPUT', id: 'bf-phone' };
els.deepFrame = { contentDocument: { activeElement: box } };
document.activeElement = box;
document.hasFocus = function () { return false; };
wakeHoldCheck();
await liveHeard(c, 'her cell is 919 555 0142'); await flush();
var live = { deaf: !!T.deaf, note: T.lastHeard.note, open: S.convo === c, ending: !!c.ending };
var n = talk(false); n.live = false; n.open = false; n.misses = 0; S.listenReason = '';
convoListen(n, false); await flush();
out({ live: live, talked: talked });
""")
        self.assertEqual(got, {"live": {"deaf": False, "note": False, "open": True, "ending": False},
                               "talked": ["hello there"]})
        app = read(APP)
        for gone in ("focusin", "hasFocus", "startedAway", "activeElement.blur", "END_TALK_HELD"):
            self.assertNotIn(gone, app, gone)


@unittest.skipUnless(NODE, "Node is not installed")
class HerOwnVoiceNeverWakesHer(unittest.TestCase):
    def test_the_hold_stays_on_for_two_and_a_half_seconds_after_she_stops(self):
        got = run(r"""
var c = talk(true); wakeHoldCheck(); var on = holds.length ? holds[holds.length - 1].on : null;
S.convo = null; T.speaking = false; setPhase('idle'); tick(1000); wakeHoldCheck();
var mid = { held: W.held, last: holds[holds.length - 1].on };
tick(1600); wakeHoldCheck();
out({ on: on, mid: mid, end: { held: W.held, last: holds[holds.length - 1].on }, tail: WAKE_TAIL_MS });
""")
        self.assertEqual(got, {"on": True, "mid": {"held": True, "last": True}, "end": {"held": False, "last": False},
                               "tail": 2500})

    def tearDown(self):
        server._her_said = ("", 0.0)

    def test_her_last_words_are_matched_inside_twelve_seconds(self):
        server.note_her_words("Goodnight, Andy. Sleep well, and I'll be right here.")
        self.assertTrue(server.is_her_own_voice("sleep well and I'll be right here"))
        self.assertFalse(server.is_her_own_voice("hey mary"))
        server.note_her_words("Hey Mary is what you say to wake me.")
        self.assertTrue(server.is_her_own_voice("Hey Mary"))
        with mock.patch.object(server.time, "monotonic", return_value=server._her_said[1] + 13):
            self.assertFalse(server.is_her_own_voice("Hey Mary"))

    def test_a_wake_made_of_her_own_words_is_dropped_and_the_residents_passes(self):
        link = server.WAKE
        server.note_her_words("Goodnight, sleep well")
        with mock.patch.object(server, "wake_log") as logged, mock.patch.object(link, "hold") as hold, \
                mock.patch.object(link, "_publish") as pub, mock.patch.object(wakeword, "pause") as pause:
            link._on_wake({"name": "mary", "confirm_text": "sleep well", "time": 1})
            logged.assert_called_once_with("ignored", why="her own voice")
            hold.assert_called_once_with(False)
            pub.assert_not_called()
            pause.assert_not_called()
            with mock.patch.object(link, "_ensure_watch"):
                link._on_wake({"name": "mary", "confirm_text": "hey mary", "time": 2, "greeted": True})
            pub.assert_called_once()
            pause.assert_called_once()
        with link._cond:
            link._woke_until = 0.0


if __name__ == "__main__":
    unittest.main()
