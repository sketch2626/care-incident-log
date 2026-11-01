from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M17: nothing may leave her asleep for good. Her name is answered after any kind of talk ending and on any screen, a
dead microphone heals itself, a stuck talk or phase lets go, and dictating a note isn't taken for a goodbye. The page's
real code runs in Node on a fake clock; the listener runs on the fake sounddevice from test_wakeword."""
import json
import logging
import os
import subprocess
import threading
import time
import unittest
from unittest import mock

import server
import speech
import wakeword
from tests import test_wakeword as tw
from tests.test_story_js import APP, NODE, ROOT, TALKLIVE, between, read

_LOG = logging.getLogger("care.wakeword")
_saved_log_disabled = _LOG.disabled


def setUpModule():
    _LOG.disabled = True  # these tests break the microphone on purpose


def tearDownModule():
    _LOG.disabled = _saved_log_disabled


STUBS = r"""
var realImmediate = setImmediate;
function flush() { return new Promise(function (r) { realImmediate(r); }); }
var NOW = 1000000; Date.now = function () { return NOW; };
var timers = [], timerId = 0;
setTimeout = function (fn, ms) { timers.push({ id: ++timerId, at: NOW + (ms || 0), fn: fn }); return timerId; };
clearTimeout = function (id) { timers = timers.filter(function (t) { return t.id !== id; }); };
setInterval = function () { return 0; };
clearInterval = function () {};
function tick(ms) {
  var end = NOW + ms;
  for (;;) {
    var due = timers.filter(function (t) { return t.at <= end; }).sort(function (a, b) { return a.at - b.at; })[0];
    if (!due) { break; }
    timers = timers.filter(function (t) { return t !== due; });
    NOW = Math.max(NOW, due.at);
    due.fn();
  }
  NOW = end;
}
var T = { speaking: false, stalled: false, talks: 0, talkOK: true, heard: {}, ui: false, seq: 0 };
var calls = [], holds = [], greets = [], logs = [], stops = [], opts = null;
function count(name) { return calls.filter(function (x) { return x === name; }).length; }
var S = { screen: 'everyday', phase: 'idle', convo: null, firstRun: false, micHeld: false, wakeWord: true, wakeReady: true,
  talkOrder: ['live', 'normal'], volume: 1 };
var W = { polling: true, held: false, holdAt: 0, lastEv: 0, heardTimer: null };
var Sp = { sess: null }, M = { panel: null }, CapS = { owner: '' }, MSG = { emergency: 'call' };
var els = { typing: { hidden: true } };
function $(id) { return els[id]; }
var WAKE_HEARD_MS = 4000, WAKE_HOLD_RENEW_MS = 30000, WAKE_SAY = 'Yes?', WAKE_HELLO = '(hello)';
var CONVO_IDLE_S = 15, STORY_STALL_MS = 15000, LIVE_BYE_QUIET_MS = 1200, LIVE_BYE_MAX_MS = 8000;
var TOOL_REFUSED = { refused: true }, SILENCE_NOISE = /^\W*$/;
var face = { setActivity: function () { calls.push('ears'); } };
var window = { MarySkills: null, MaryLive: {
  start: function (o) { opts = o; return Promise.resolve(); },
  stop: function (why) { stops.push(why); T.speaking = false; },
  stopSpeaking: function () { calls.push('stopSpeaking'); T.speaking = false; },
  greet: function (t) { greets.push(t); return true; },
  setVolume: function () {},
  isSpeaking: function () { return T.speaking; },
  stalled: function () { return T.stalled; }
} };
function log(e) { logs.push(String((e && e.message) || e)); }
function api(method, path, body) {
  if (path === '/api/wake/hold') { holds.push(body); }
  if (path === '/api/mary/heard') { return Promise.resolve(T.heard); }
  return Promise.resolve({});
}
function setPhase(p) { S.phase = p; wakeHoldCheck(); }
function newTurn() { calls.push('newTurn'); }
function spCancel() { calls.push('spCancel'); }
function refreshStatus() { calls.push('refresh'); }
function updateTalkButton() {} function capCut() {} function capListening() {} function capLivePiece() {}
function capLiveAudio() {} function capLiveDone() {} function setCaption() {} function restLine() { return ''; }
function liveFirst() { return true; } function say() { return Promise.resolve(); } function goodbyeLine() { return 'bye'; }
function liveBye() { return '(bye)'; } function menuOpen() { return false; } function closeMenu() {} function closePanel() {}
function faceAct() {} function closeTyping() { els.typing.hidden = true; calls.push('closeTyping'); }
function skillScreen() { return undefined; } function asideSkill() {} function showCaption() {}
function startTalk(o) { T.talks++; return Promise.resolve(T.talkOK); }
function uiOpen() { return T.ui; }
function isGoodbye(t) { return /go to sleep|goodbye/i.test(t); }
function heardTail(track, t) { return t; } function heardFinal(track, t) { return t; } function notEnglish() { return false; }
function liveEmergency() { calls.push('emergency'); } function show(s) { S.screen = s; }
function liveToolGate() { return 'run'; } function storyTake() { return {}; } function storyFromTool(c, r) { return r; }
function refreshName() {} function fixNumbers(t) { return t; } function liveToolCancelled() {} function storyNext() {}
function liveMicLevel() {} function liveFailed() {} function applyMood() {} function liveTurnEnded() {}
function nextMode() { return 'normal'; } function speechModeFor(m) { return m; }
function lockTalkVoice() { return Promise.resolve(); } function sayFallbackOnce() { return Promise.resolve(); }
function convoNext() { calls.push('convoNext'); } function openTyping() {}
"""

HELPERS = r"""
function talk(speaking) {
  var c = { mode: 'live', live: true, open: true, ending: false, paused: false, seq: 1, lastAct: NOW, lastLife: NOW, heard: '',
    heardCheck: null, toolBusy: 0, idleTimer: null, byeTimer: null, byeDone: false, byeAudio: false, story: null, talked: true,
    saidText: '' };
  S.convo = c;
  setPhase(speaking ? 'speaking' : 'listening');
  T.speaking = !!speaking;
  return c;
}
async function openLive() {
  var c = { mode: 'live', seq: 0, lastAct: NOW, toolBusy: 0, story: null, talked: true, saidText: '', ending: false };
  S.convo = c;
  startLive(c, '(hi)');
  await flush();
  greets.length = 0;
  return c;
}
function cut(words) { opts.onCaption(words); opts.onInterrupted(); }
function wake(extra) { onWakeEvent(Object.assign({ type: 'wake', seq: ++T.seq }, extra || {})); }
var END_TALK = { functionCalls: [{ id: 'e1', name: 'end_talk', args: {} }] };
function out(x) { console.log(JSON.stringify(x)); }
"""


def _page():
    app = read(APP)
    consts = ["WAKE_STUCK_MS", "WAKE_READY_RETRY_MS", "LIVE_STUCK_S", "NOTE_BUSY_MS", "LIVE_FALSE_CUT_MS", "LIVE_PICK_UP",
              "END_TALK_HELD"]
    cuts = [
        ("function liveSpeaking() {", "// M15c: the send count's hooks"),
        ("function greetLive(text) {", "// M7a: true means a screen's line"),
        ("function restPhase() {", "// The voice for spoken sentences"),
        ("function closeConvo(c) {", "// --- M6: the wake word"),
        ("// M17: why she can't answer", "setInterval(wakeHoldCheck, 1000);"),
        ("function startLive(c, hello) {", "function liveFailed(c, err) {"),
        ("function liveFallback(c) {", "// M4a: a line of hers goes into the talk history"),
        ("function liveSaid(c) {", "// M4d: Live's audio comes straight"),
        ("function liveByeCap(c, extended) {", "// Every finished thing the resident says"),
        ("function liveHeard(c, text) {", "function liveEmergency(c, j) {"),
        ("// M17: a hand click near", "function liveToolCall(c, tc) {"),
        ("function liveToolCall(c, tc) {", "// Typed words while Live is open"),
    ]
    parts = [STUBS] + [between(app, "var " + n + " ", "\n") for n in consts] + [between(app, a, b) for a, b in cuts]
    parts.append("var App = { onActivity: function () { calls.push('activity'); },\n" + between(app, "keepTalk: function", "\n")
                 + "\n" + between(app, "noteBusy: function", "\n") + "\n};")
    parts.append(HELPERS)
    return "\n".join(parts)


PAGE = _page()


def node(body, code=None):
    code = code or (PAGE + "\n(async function () {\n" + body +
                    "\n})().catch(function (e) { console.error((e && e.stack) || e); process.exit(1); });\n")
    run = subprocess.run([NODE, "-"], input=code, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert run.returncode == 0, run.stderr[-1500:]
    return json.loads(run.stdout)


@unittest.skipUnless(NODE, "Node is not installed")
class WakeAnswersAfterATalk(unittest.TestCase):
    def answers(self, steps):
        got = node(steps + r"""
await flush();
var was = { phase: S.phase, convo: !!S.convo, held: W.held }, before = T.talks;
wake();
await flush();
out({ was: was, answered: T.talks - before });
""")
        self.assertEqual(got["was"], {"phase": "idle", "convo": False, "held": False})
        self.assertEqual(got["answered"], 1)

    def test_live_ended_by_tap_while_she_speaks(self):
        self.answers("var c = talk(true); endConvo(c, 'tap');")

    def test_live_ended_by_idle_while_she_speaks(self):
        self.answers("var c = talk(true); endConvo(c, 'idle'); tick(LIVE_BYE_MAX_MS + 7000);")

    def test_live_ended_by_goodbye_while_she_speaks(self):
        self.answers("var c = talk(true); liveByeNow(c); tick(LIVE_BYE_MAX_MS + 7000);")

    def test_live_line_dropped_while_saying_goodbye(self):
        self.answers("var c = talk(true); c.ending = true; liveDropped(c, 'closed', {});")

    def test_live_line_dropped_then_the_talk_goes_on_and_ends(self):
        self.answers("var c = talk(true); liveDropped(c, 'closed', {}); await flush(); endConvo(c, 'tap');")

    def test_normal_ended_while_she_speaks(self):
        self.answers("var c = talk(true); c.live = false; c.open = false; endConvo(c, 'tap');")

    def test_on_a_skill_or_card_screen(self):
        self.answers("S.screen = 'messages';")

    def test_on_any_other_screen(self):
        self.answers("S.screen = 'nokey';")

    def test_with_the_typing_box_open(self):
        got = node(r"""
els.typing.hidden = false;
wake();
await flush();
out({ talks: T.talks, closed: count('closeTyping'), hidden: els.typing.hidden });
""")
        self.assertEqual(got, {"talks": 1, "closed": 1, "hidden": True})

    def test_stuck_thinking_lets_go_after_90_s(self):
        self.answers(r"""
var c = talk(false);
S.phase = 'thinking';
finishLive(c);
tick(WAKE_STUCK_MS - 1); wakeHoldCheck();
if (S.phase !== 'thinking') { throw new Error('let go too soon'); }
tick(1); wakeHoldCheck();
if (!count('spCancel') || !count('newTurn')) { throw new Error('no clean-up'); }
""")

    def test_a_real_line_or_the_emergency_screen_is_not_stuck(self):
        got = node(r"""
S.phase = 'thinking'; S.screen = 'emergency';
wakeHoldCheck(); tick(WAKE_STUCK_MS * 2); wakeHoldCheck();
var first = S.phase;
S.screen = 'everyday'; Sp.sess = {}; S.phase = 'speaking';
wakeHoldCheck(); tick(WAKE_STUCK_MS * 2); wakeHoldCheck();
out([first, S.phase]);
""")
        self.assertEqual(got, ["thinking", "speaking"])

    def test_a_stopped_poll_looks_at_the_status_once_a_minute(self):
        got = node(r"""
W.polling = false; S.wakeReady = false;
wakeHoldCheck(); tick(1000); wakeHoldCheck();
var one = count('refresh');
tick(WAKE_READY_RETRY_MS); wakeHoldCheck();
out([one, count('refresh')]);
""")
        self.assertEqual(got, [1, 2])


@unittest.skipUnless(NODE, "Node is not installed")
class WakeDeclines(unittest.TestCase):
    def declined(self, setup, why, on):
        got = node(setup + "\nwake(); await flush(); out({ talks: T.talks, hold: holds[holds.length - 1] });")
        self.assertEqual(got, {"talks": 0, "hold": {"on": on, "why": why}})

    def test_only_these_decline_and_each_is_logged(self):
        self.declined("S.screen = 'emergency';", "emergency", False)
        self.declined("S.firstRun = true;", "first run", False)
        self.declined("S.micHeld = true;", "send count", False)
        self.declined("talk(false);", "talk open", True)   # a busy page keeps its hold
        self.declined("S.phase = 'thinking';", "busy thinking", True)

    def test_a_talk_that_would_not_start_releases_the_hold(self):
        got = node("T.talkOK = false; wake(); await flush(); out(holds[holds.length - 1]);")
        self.assertEqual(got, {"on": False, "why": "talk did not start"})

    def test_a_dropped_heard_event_sends_nothing(self):
        got = node("S.firstRun = true; onWakeEvent({ type: 'heard', seq: 5 }); await flush(); out([holds, count('ears')]);")
        self.assertEqual(got, [[], 0])

    def test_a_note_declines_the_bare_name_but_not_a_greeting(self):
        got = node(r"""
App.noteBusy(true);
wake({ greeted: false }); await flush();
var bare = [T.talks, holds[holds.length - 1]];
wake({ greeted: true }); await flush();
var greeted = T.talks;
tick(NOTE_BUSY_MS);
wake({ greeted: false }); await flush();
out({ bare: bare, greeted: greeted, expired: T.talks });
""")
        self.assertEqual(got, {"bare": [0, {"on": False, "why": "note"}], "greeted": 1, "expired": 2})


@unittest.skipUnless(NODE, "Node is not installed")
class FalseCut(unittest.TestCase):
    def test_she_picks_up_once_a_turn_with_balanced_words(self):
        got = node(r"""
var c = await openLive();
cut('Well I was saying');
tick(LIVE_FALSE_CUT_MS - 1);
var early = greets.length;
tick(1);
var first = greets.slice();
cut('Picking it up now');
tick(LIVE_FALSE_CUT_MS);
var second = greets.length;
opts.onHeardDone('right'); await flush();
cut('Again');
tick(LIVE_FALSE_CUT_MS);
out({ early: early, first: first, second: second, third: greets.length });
""")
        self.assertEqual((got["early"], got["second"], got["third"]), (0, 1, 2))
        line = got["first"][0]
        self.assertIn("A noise cut you off", line)
        self.assertEqual(line.count("("), line.count(")"))
        self.assertNotIn("word for word", line)   # the instruction must not be read out

    def test_not_when_their_words_arrive(self):
        got = node("await openLive(); cut('Well I was'); opts.onHeard('no wait'); tick(LIVE_FALSE_CUT_MS); out(greets);")
        self.assertEqual(got, [])

    def test_not_when_nothing_was_said_ending_a_story_emergency_or_closed(self):
        for setup, after in (("", "opts.onInterrupted();"),
                             ("c.ending = true;", "cut('Bye');"),
                             ("c.story = { paused: false };", "cut('Once upon');"),
                             ("S.screen = 'emergency';", "cut('Call');"),
                             ("", "cut('Well'); endConvo(c, 'tap');"),
                             ("", "cut('Well'); T.speaking = true;")):
            with self.subTest(setup=setup, after=after):
                got = node("var c = await openLive();" + setup + after + "tick(LIVE_FALSE_CUT_MS); out(greets);")
                self.assertEqual(got, [])


@unittest.skipUnless(NODE, "Node is not installed")
class StuckTalks(unittest.TestCase):
    def test_keep_talk_moves_last_act_and_never_speaks(self):
        got = node(r"""
var c = talk(false);
tick(14000); App.keepTalk();
var moved = c.lastAct === NOW;
tick(14000); liveIdleCheck(c);
S.convo = null; App.keepTalk();
out({ moved: moved, ending: c.ending, activity: count('activity'), greets: greets });
""")
        self.assertEqual(got, {"moved": True, "ending": False, "activity": 2, "greets": []})

    def test_a_stuck_tool_closes_the_talk_at_180_s(self):
        got = node(r"""
var c = talk(false);
c.toolBusy = 1;
tick(LIVE_STUCK_S * 1000 - 1000); liveIdleCheck(c);
var open = S.convo === c;
tick(1000); liveIdleCheck(c);
out({ open: open, gone: S.convo === null, phase: S.phase, held: W.held, stops: stops });
""")
        self.assertEqual(got, {"open": True, "gone": True, "phase": "idle", "held": False, "stops": ["end"]})

    def test_it_ends_idle_even_from_thinking(self):
        got = node("var c = talk(false); T.ui = true; S.phase = 'thinking'; tick(LIVE_STUCK_S * 1000); liveIdleCheck(c); out(S.phase);")
        self.assertEqual(got, "idle")

    def test_real_events_are_life(self):
        got = node(r"""
var c = await openLive();
c.toolBusy = 1;
tick(170000); opts.onActivity();
tick(170000); opts.onAudioChunk(0, 0, null);
tick(170000); liveIdleCheck(c);
out(S.convo === c);
""")
        self.assertTrue(got)

    def test_a_long_story_she_is_speaking_is_not_stuck(self):
        got = node(r"""
var c = talk(true);
c.story = { paused: false, askedAt: NOW };
for (var i = 0; i < 300; i++) { tick(1000); liveIdleCheck(c); }
out(S.convo === c);
""")
        self.assertTrue(got)

    def test_a_stalled_line_ends_like_a_dropped_one(self):
        got = node(r"""
var c = talk(true);
T.stalled = true;
liveIdleCheck(c);
await flush();
out({ stops: stops, live: c.live, mode: c.mode, next: count('convoNext') });
""")
        self.assertEqual(got, {"stops": ["stalled"], "live": False, "mode": "normal", "next": 1})

    def test_the_emergency_screen_is_never_closed(self):
        got = node(r"""
var c = talk(false);
c.toolBusy = 1; T.stalled = true; S.screen = 'emergency';
tick(LIVE_STUCK_S * 2000); liveIdleCheck(c);
out([S.convo === c, stops]);
""")
        self.assertEqual(got, [True, []])

    def test_stalled_needs_five_seconds_of_a_still_clock(self):
        code = ("(function () {\nvar NOW = 1, resumes = 0, performance = { now: function () { return NOW; } };\n"
                "var S = { talking: true, ended: false, outCtx: { currentTime: 1, resume: function () { resumes++; "
                "return Promise.resolve(); } } };\n" + between(read(TALKLIVE), "var STALL_MS", "function setVolume(v)") + r"""
var r = [stalled()];
NOW = 4000; r.push(stalled());
NOW = 5001; r.push(stalled());
S.outCtx.currentTime = 2; NOW = 6000; r.push(stalled());
S.talking = false; r.push(stalled());
console.log(JSON.stringify([r, resumes]));
})();
""")
        self.assertEqual(node("", code), [[False, False, True, False, False], 1])

    def test_a_lost_mic_track_ends_the_line(self):
        js = read(TALKLIVE)
        self.assertIn("track.addEventListener('ended'", js)
        self.assertIn("endSession(s, 'closed', {note: 'mic lost'})", js)


@unittest.skipUnless(NODE, "Node is not installed")
class NoteBusy(unittest.TestCase):
    def test_a_goodbye_during_a_note_does_not_end_the_talk(self):
        got = node(r"""
var c = talk(true);
App.noteBusy(true);
liveHeardPiece(c, 'go to sleep');
tick(LIVE_BYE_QUIET_MS + 1);
await liveHeard(c, 'go to sleep');
await flush();
var r = await liveToolCall(c, END_TALK);
out({ ending: c.ending, open: S.convo === c, answers: r.functionResponses.length, id: r.functionResponses[0].id,
      hushed: count('stopSpeaking'), mic: stops });
""")
        self.assertEqual(got, {"ending": False, "open": True, "answers": 1, "id": "e1", "hushed": 0, "mic": []})

    def test_a_goodbye_she_has_already_begun_still_ends(self):
        got = node(r"""
var c = talk(false);
c.ending = true; c.byeAudio = true;
App.noteBusy(true);
var r = await liveToolCall(c, END_TALK);
out([S.convo === null, r.functionResponses.length]);
""")
        self.assertEqual(got, [True, 0])

    def test_an_emergency_during_a_note_still_fires(self):
        got = node(r"""
var c = talk(false);
App.noteBusy(true);
T.heard = { emergency: true, say: 'call' };
await liveHeard(c, 'I can not breathe');
await flush();
out(count('emergency'));
""")
        self.assertEqual(got, 1)

    def test_an_expired_note_does_not_block_a_goodbye(self):
        got = node(r"""
var a = talk(false);
App.noteBusy(true);
tick(NOTE_BUSY_MS);
liveHeardPiece(a, 'go to sleep');
tick(LIVE_BYE_QUIET_MS + 1);
var piece = a.ending;
var b = talk(false);
await liveHeard(b, 'goodbye');
await flush();
var heard = b.ending;
var c = talk(false);
var r = await liveToolCall(c, END_TALK);
out({ piece: piece, heard: heard, ended: S.convo === null, answers: r.functionResponses.length });
""")
        self.assertEqual(got, {"piece": True, "heard": True, "ended": True, "answers": 0})

    def test_blur_clears_it(self):
        got = node(r"""
var c = talk(false);
App.noteBusy(true); App.noteBusy(false);
liveHeardPiece(c, 'go to sleep');
tick(LIVE_BYE_QUIET_MS + 1);
out(c.ending);
""")
        self.assertTrue(got)

    def test_a_normal_talk_goodbye_is_gated_too(self):
        self.assertIn("if (isGoodbye(text) && !(S.noteBusy && noteBusyNow())) { return convoBye(c, text); }", read(APP))

    def test_the_drawer_reports_focus_and_redraws(self):
        js = read(os.path.join(ROOT, "tools", "testlist", "drawer.js"))
        self.assertIn("area.addEventListener('focus', function () { noteBusy(true); });", js)
        self.assertIn("if (D.activeElement !== area) { noteBusy(false); }", js)
        self.assertIn("noteBusy(!!again && again.tagName === 'TEXTAREA');", js)
        self.assertIn("W.MaryApp.keepTalk()", js)
        self.assertIn("W.MaryApp.noteBusy(on)", js)
        self.assertIn("ev.stopPropagation();", js)

    def test_nothing_in_mary_listens_for_blur(self):
        for name in ("app.js", "talklive.js", "firstrun.js", "live.js"):
            self.assertNotIn("'blur'", read(os.path.join(ROOT, "web", "mary", name)))


class ConfirmRule(unittest.TestCase):
    def events(self, text):
        rec = tw.FakeRecognizer()
        det = wakeword.Detector(names=("mary",), recognizer_factory=lambda g: rec, confirmer=tw.FakeConfirm(text))
        rec.say(*tw.WAKE)
        found = []
        for _ in tw.WAKE:
            found += det.feed(tw.SILENCE)
        return found

    def test_greeted_says_which_way_it_passed(self):
        self.assertEqual([(e["name"], e["greeted"]) for e in self.events("Hey Mary.")], [("mary", True)])
        self.assertEqual([(e["name"], e["greeted"]) for e in self.events("and hey, Marie")], [("mary", True)])
        self.assertEqual([(e["name"], e["greeted"]) for e in self.events("and and Mary can you")], [("mary", False)])

    def test_the_bare_name_counts_only_in_the_first_four_words(self):
        self.assertEqual(len(self.events("one two three Mary")), 1)
        self.assertEqual(self.events("one two three four Mary"), [])

    def test_only_the_chosen_name_counts(self):
        self.assertEqual(self.events("Sam can you"), [])
        self.assertEqual(self.events("marry me now"), [])

    def test_whisper_gets_one_pass_only(self):
        seen = {}

        class Model:
            def transcribe(self, audio, **kw):
                seen.update(kw)
                return [], None

        with mock.patch.object(speech, "_wait_for_model", return_value=Model()):
            wakeword._whisper_confirm(speech.np.full(1600, 0.5, dtype=speech.np.float32))
        self.assertEqual(seen["temperature"], 0.0)
        self.assertIsInstance(seen["temperature"], float)


class ListenerBase(unittest.TestCase):
    NAMES = ("REOPEN_RETRY_S", "MIC_STALL_S", "MIC_ZERO_S", "CLOSE_WAIT_S", "SLOW_CHECK_S")

    def setUp(self):
        self.sd = tw.FakeSD()
        self.rescans = []
        self.sd._terminate = lambda: self.rescans.append(1)
        self.saved = (speech._sd, speech._sd_loaded, speech._missing_dependency, speech.warm_up, wakeword._listener,
                      [getattr(wakeword, n) for n in self.NAMES])
        speech._sd, speech._sd_loaded = self.sd, True
        speech._missing_dependency = lambda: None
        speech.warm_up = lambda: None
        wakeword.REOPEN_RETRY_S = 0.05
        self.rec = tw.FakeRecognizer()
        self.confirm = tw.FakeConfirm("Hey Mary.")
        self.L = wakeword._Listener(detector_factory=lambda names: wakeword.Detector(
            names=names, recognizer_factory=lambda grammar: self.rec, confirmer=self.confirm))
        wakeword._listener = self.L
        self.heard, self.notes = [], []
        self.release = threading.Event()

    def tearDown(self):
        self.release.set()
        self.L.stop()
        speech._sd, speech._sd_loaded, speech._missing_dependency, speech.warm_up, wakeword._listener, values = self.saved
        for name, value in zip(self.NAMES, values):
            setattr(wakeword, name, value)

    def wait_for(self, check, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = check()
            if value:
                return value
            time.sleep(0.01)
        self.fail("timed out waiting")

    def started(self):
        self.L.start(on_wake=self.heard.append, on_note=self.notes.append)
        return self.wait_for(self.sd.live_wake)

    def fresh(self, old):
        time.sleep(0.1)  # a heal already under way finishes first
        return self.wait_for(lambda: (lambda s: s if s is not None and s is not old else None)(self.sd.live_wake()))

    def wakes(self, stream):
        self.rec.say(*tw.WAKE)
        for _ in tw.WAKE:
            stream.push()
        self.assertIsNotNone(self.L.wait(0, timeout=3))
        self.wait_for(lambda: self.heard)

    def reason(self):
        self.wait_for(lambda: self.notes)
        self.assertEqual(self.notes[0]["type"], "mic")
        return self.notes[0]["reason"]


class ListenerHeals(ListenerBase):
    def test_a_stream_that_stops_giving_blocks_is_reopened_and_she_wakes(self):
        wakeword.MIC_STALL_S = 0.05
        s = self.started()
        self.wait_for(lambda: s.closed)
        wakeword.MIC_STALL_S = 3.0
        self.wakes(self.fresh(s))
        self.assertIn("no audio", self.reason())

    def test_an_inactive_stream_is_reopened_after_a_rescan(self):
        s = self.started()
        s.active = False
        self.wait_for(lambda: s.closed)
        self.wakes(self.fresh(s))
        self.assertEqual(self.reason(), "stream stopped")
        self.assertTrue(self.rescans)

    def test_only_zeros_is_reopened(self):
        wakeword.MIC_ZERO_S = 0.05
        s = self.started()
        end = time.monotonic() + 3
        while not s.closed and time.monotonic() < end:
            s.push()  # blocks keep coming, all of them zeros
            time.sleep(0.01)
        self.assertTrue(s.closed)
        wakeword.MIC_ZERO_S = 10.0
        self.wakes(self.fresh(s))
        self.assertIn("zeros", self.reason())

    def test_a_healthy_quiet_stream_is_left_alone(self):
        wakeword.MIC_STALL_S = wakeword.MIC_ZERO_S = 0.5
        s = self.started()
        loud = b"\x10\x00" * tw.BLOCK
        end = time.monotonic() + 0.7
        while time.monotonic() < end:
            s.push(loud)
            time.sleep(0.01)
        self.assertIs(self.sd.live_wake(), s)
        self.assertEqual(self.notes, [])

    def test_a_failed_reopen_keeps_trying_and_recovers(self):
        s = self.started()
        self.sd.fail_open = True
        s.active = False
        self.wait_for(lambda: self.L.status()["problem"])
        self.sd.fail_open = False
        self.wakes(self.fresh(s))
        self.wait_for(lambda: not self.L.status()["problem"])

    def test_a_hanging_close_does_not_block_and_leaves_portaudio_alone(self):
        wakeword.CLOSE_WAIT_S = 0.05
        s = self.started()
        s.stop = lambda: self.release.wait(10)
        s.active = False
        self.wakes(self.fresh(s))
        self.assertFalse(s.closed)
        self.assertEqual(self.rescans, [])
        self.release.set()
        self.wait_for(lambda: s.closed)

    def test_a_pause_on_a_hanging_close_returns(self):
        wakeword.CLOSE_WAIT_S = 0.05
        s = self.started()
        s.stop = lambda: self.release.wait(10)
        t0 = time.monotonic()
        self.L.pause("test")
        self.assertLess(time.monotonic() - t0, 1.0)
        self.L.resume("test")
        self.wakes(self.fresh(s))

    def test_a_long_check_drops_the_audio_queued_behind_it(self):
        class Slow:
            def __init__(self):
                self.entered, self.gate = threading.Event(), threading.Event()

            def __call__(self, audio):
                self.entered.set()
                self.gate.wait(3)
                return "Hey man"

        wakeword.SLOW_CHECK_S = 0.02
        self.confirm = Slow()
        s = self.started()
        self.rec.say(*tw.WAKE)
        for _ in tw.WAKE:
            s.push()
        self.assertTrue(self.confirm.entered.wait(3))
        for _ in range(5):
            s.push()  # heard while Whisper was busy: stale by the time it is done
        time.sleep(0.1)  # the check really does outlast SLOW_CHECK_S
        self.confirm.gate.set()
        self.wait_for(lambda: self.L._queue.qsize() == 0)
        time.sleep(0.1)
        self.assertEqual(len(self.rec.blocks), len(tw.WAKE))
        self.assertGreaterEqual(self.rec.resets, 3)

    def test_alive_follows_the_worker(self):
        self.assertFalse(wakeword.alive())
        self.started()
        self.assertTrue(wakeword.alive())
        self.L.stop()
        self.assertFalse(wakeword.alive())


class WakeLinkHeals(ListenerBase):
    def link(self):
        link = server.WakeLink()
        link._ensure_watch = lambda: None
        return link

    def test_a_dead_worker_is_restarted(self):
        real, broken = self.L._detector_factory, [True]

        def factory(names):
            if broken:
                broken.clear()
                raise RuntimeError("no model")
            return real(names)

        self.L._detector_factory = factory
        link = self.link()
        link._ensure_started("her")
        self.wait_for(lambda: not wakeword.alive())
        self.assertTrue(link._started)
        link._ensure_started("her")
        self.assertTrue(wakeword.alive())
        self.wait_for(self.sd.live_wake)

    def test_mic_notes_and_declined_wakes_reach_the_log(self):
        link = self.link()
        with mock.patch.object(server, "wake_log") as logged, mock.patch.object(link, "status", return_value={}):
            link._on_note({"type": "mic", "reason": "no audio for 3 s"})
            link.hold(False, why="first run")
            link.hold(False)
        self.assertEqual(logged.call_args_list, [mock.call("mic", reason="no audio for 3 s"),
                                                 mock.call("ignored", why="first run")])

    def test_the_route_passes_why(self):
        self.assertIn('WAKE.hold(on, body.get("why"))', read(os.path.join(ROOT, "server.py")))

    def test_greeted_reaches_the_page(self):
        link = self.link()
        with mock.patch.object(server, "wake_log"):
            link._on_wake({"name": "mary", "greeted": True, "time": 1, "companion": "her"})
            self.assertIs(link._event["greeted"], True)
            link._on_wake({"name": "mary", "time": 2, "companion": "her"})
            self.assertIs(link._event["greeted"], False)
            link._on_note({"type": "heard", "name": "mary"})
        self.assertNotIn("greeted", link._event)

class SecondLookTests(unittest.TestCase):
    """The review's fixes: a dictated "send it" and a muted mic."""

    def test_dictated_words_skip_the_send_gate_but_not_the_emergency_check(self):
        with open("server.py", encoding="utf-8") as f:
            py = f.read()
        self.assertIn('send = {} if body.get("note") else gate_heard(text, kind)', py)
        self.assertLess(py.index('text = str(body.get("text") or "")[:2000]'), py.index('send = {} if body.get("note")'))
        self.assertLess(py.index('kind = mary.is_emergency(text) or ""', py.index('body = self._body()\n            text = str(body')),
                        py.index('send = {} if body.get("note")'))

    def test_a_muted_mic_backs_off(self):
        import wakeword
        self.assertGreater(wakeword.MIC_ZERO_MAX, 1)
        listener = wakeword._Listener(detector_factory=lambda names: None)
        listener._last_audio = time.monotonic()
        listener._last_sound = listener._last_audio - wakeword.MIC_ZERO_S - 1
        self.assertIn("zeros", listener._mic_trouble(object()))
        self.assertEqual(listener._zero_turns, 2)
        self.assertIsNone(listener._mic_trouble(object()))   # now it waits 2 x MIC_ZERO_S


if __name__ == "__main__":
    unittest.main()
