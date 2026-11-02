from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M18 piece 4, the save gate: only a tap on Save or the resident's own plain "save it" saves. The server rules on the
words, the page acts on that alone, and no tool call or line of hers can get there. Node runs the page's own code."""
import json
import re
import shutil
import subprocess
import types
import unittest
from pathlib import Path
from unittest import mock

import mary
import send_gate
import server

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
PIECE = "  // Piece 4: the save gate."
END = "  // ---------------------------------------------------------------- end M18"


def read(rel):
    return (ROOT / "web" / rel).read_text(encoding="utf-8")


def slice_js(js, start, end):
    i = js.index(start)
    return js[i:js.index(end, i)]


def node(script):
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60)
    if done.returncode:
        raise AssertionError(done.stderr[-1500:])
    return json.loads(done.stdout.strip().splitlines()[-1])


WORLD = r"""
var BLOCK = __BLOCK__;
function world(over) {
  over = over || {};
  var timers = [], posted = [], told = [], notes = [], said = [], caps = [];
  var live = over.live !== false, up = over.up !== false, panel = !!over.panel, onLog = over.onLog !== false;
  var skill = over.skill || null;
  var S = { screen: over.screen || 'everyday', convo: null, phase: 'idle' }, Sp = { sess: null };
  var Deep = { open: true, screen: over.frame || 'add', saveAt: 0, asked: false, saveDone: null, tellT: 0, waitT: 0, capT: 0 };
  var window = { MaryScreens: { finishTyping: function () { posted.push('fill done'); } } };
  var setTimeout = function (f, ms) { var t = { f: f, ms: ms }; timers.push(t); return t; };
  var clearTimeout = function (t) { if (t) { t.dead = true; } };
  var cap = { plain: function (t) { caps.push(t); } };
  function capCall(f) { return f(); }
  function deepUp() { return up; }
  function panelOpen() { return panel; }
  function deepOnLog() { return onLog; }
  function skillScreen() { return skill; }
  function liveOn() { return live; }
  function liveSpeaking() { return false; }
  function bandUp() { return true; }
  function greetLive(t) { told.push(t); return live; }
  function say(t) { said.push(t); return Promise.resolve(); }
  function tell(n, shown) { said.push(shown); return Promise.resolve(); } function lastSentences(t){return t;} function screenLine(){} function showSteps(){} 
  function screenNote(t) { notes.push(t); }
  function deepPost(m) { posted.push(m.what); }
  eval(BLOCK);
  return {
    posted: posted, told: told, notes: notes, said: said, caps: caps, S: S,
    heard: deepSaveHeard,
    ok: function () { deepSaved(SAVE_SAID.ok, true); },
    fail: function (label) { deepSaved(label ? saveMissing(label) : SAVE_SAID.fail, false); },
    none: function (why) { deepSaved(SAVE_SAID[why], false); },
    flush: function () { timers.splice(0).forEach(function (t) { if (!t.dead && t.ms <= 1000) { t.f(); } }); }
  };
}
"""

FRAME = r"""
var CODE = __CODE__;
function frame(o) {
  var sub = [], tell = [];
  var cur = { screen: o.screen }, add = o.add || {}, infoTouched = !!o.touched, button = { disabled: !!o.disabled };
  function $(sel) {
    if (sel === '#infoSave') { return button; }
    return { requestSubmit: function () { sub.push(sel); } };
  }
  function formNow() { return { a: 1 }; }
  function toMary(what, more) { tell.push([what, (more && more.why) || '']); }
  eval(CODE);
  maryAskedSave();
  return { sub: sub, tell: tell };
}
var SAME = JSON.stringify({ a: 1 });
"""


class Page(unittest.TestCase):
    """The page's own code, with its neighbours stubbed."""

    @classmethod
    def setUpClass(cls):
        block = slice_js(read("mary/app.js"), PIECE, END)
        cls.world = WORLD.replace("__BLOCK__", json.dumps(block))

    def run_js(self, body):
        return node(self.world + "var out = {};\n" + body + "\nconsole.log(JSON.stringify(out));")

    def test_one_line_saves_once(self):
        got = self.run_js("var w = world(); w.heard(); w.heard(); w.heard(); out.posted = w.posted;")
        self.assertEqual(got["posted"].count("save"), 1)

    def test_a_save_that_failed_can_be_said_again(self):
        got = self.run_js("""var w = world(); w.heard(); w.fail('what happened'); w.flush(); w.heard();
                             out.posted = w.posted; out.told = w.told;""")
        self.assertEqual(got["posted"].count("save"), 2)
        self.assertIn("Still needed: what happened", got["told"][0])

    def test_only_with_a_form_up(self):
        for setup in ("{ up: false }", "{ panel: true }", "{ onLog: false }", "{ frame: 'list' }", "{ frame: 'saved' }",
                      "{ frame: 'home' }"):
            got = self.run_js("var w = world(%s); w.heard(); out.posted = w.posted; out.told = w.told;" % setup)
            self.assertEqual(got["posted"], [], setup)
            self.assertIn("No form is open", got["told"][0], setup)

    def test_add_and_info_both_take_it(self):
        for name in ("add", "info"):
            got = self.run_js("var w = world({ frame: '%s' }); w.heard(); out.posted = w.posted;" % name)
            self.assertIn("save", got["posted"])

    def test_a_skill_screen_keeps_its_own_save_it(self):
        got = self.run_js("""var w = world({ up: false, skill: 'messages' }); w.heard();
                             out.all = w.posted.concat(w.told, w.said);""")
        self.assertEqual(got["all"], [])

    def test_never_on_the_emergency_screen(self):
        got = self.run_js("""var w = world({ screen: 'emergency' }); w.heard(); out.all = w.posted.concat(w.told, w.said);
                             var v = world(); v.heard(); v.S.screen = 'emergency'; v.ok(); v.flush();
                             out.late = v.told.concat(v.said);""")
        self.assertEqual(got["all"], [])
        self.assertEqual(got["late"], [])

    def test_her_fill_lands_before_the_save(self):
        got = self.run_js("var w = world(); w.heard(); out.posted = w.posted;")
        self.assertEqual(got["posted"], ["fill done", "save"])

    def test_the_word_gets_an_answer_she_can_say(self):
        got = self.run_js("var w = world(); w.heard(); w.ok(); w.flush(); out.told = w.told; out.notes = w.notes;")
        self.assertEqual(got["told"], ["(The form was saved. Say 'Saved.' and nothing more.)"])
        self.assertEqual(got["notes"], [])

    def test_a_tap_only_tells_her(self):
        got = self.run_js("""var w = world(); w.ok(); w.flush();
                             out.told = w.told; out.notes = w.notes; out.caps = w.caps; out.said = w.said;""")
        self.assertEqual(got["told"], [])
        self.assertEqual(got["said"], [])
        self.assertEqual(got["notes"], ["(The form was saved.)"])
        self.assertEqual(got["caps"], ["Saved."])

    def test_a_failed_tap_says_what_is_missing_quietly(self):
        got = self.run_js("var w = world(); w.fail('which day it happened'); w.flush(); out.notes = w.notes;")
        self.assertEqual(got["notes"], ["(The form did not save. Still needed: which day it happened.)"])

    def test_nothing_changed_is_told(self):
        got = self.run_js("var w = world(); w.heard(); w.none('nothing'); w.flush(); out.told = w.told;")
        self.assertIn("Nothing on this form has changed", got["told"][0])

    def test_normal_talk_says_it_in_her_voice(self):
        got = self.run_js("var w = world({ live: false }); w.heard(); w.ok(); w.flush(); out.said = w.said;")
        self.assertEqual(got["said"], ["Saved."])


class Frame(unittest.TestCase):
    """The frame's side: the same submit a tap runs, and only when there is something to save."""

    @classmethod
    def setUpClass(cls):
        code = slice_js(read("app.js"), "function maryAskedSave() {", "const SCREENS = [")
        cls.frame = FRAME.replace("__CODE__", json.dumps(code))

    def ask(self, spec):
        return node(self.frame + "console.log(JSON.stringify(frame(%s)));" % spec)

    def test_changes_on_add_press_save(self):
        got = self.ask("{ screen: 'add', add: { clean: '{}', cat: 'food', cleanCat: 'food' } }")
        self.assertEqual(got, {"sub": ["#form"], "tell": []})

    def test_another_group_is_a_change(self):
        got = self.ask("{ screen: 'add', add: { clean: SAME, cat: 'food', cleanCat: 'call' } }")
        self.assertEqual(got["sub"], ["#form"])

    def test_an_inbox_item_counts_as_new(self):
        got = self.ask("{ screen: 'add', add: { clean: SAME, inbox: {} } }")
        self.assertEqual(got["sub"], ["#form"])

    def test_untouched_add_presses_nothing(self):
        got = self.ask("{ screen: 'add', add: { clean: SAME } }")
        self.assertEqual(got, {"sub": [], "tell": [["save_none", "nothing"]]})

    def test_a_save_already_going_is_not_pressed_twice(self):
        got = self.ask("{ screen: 'add', add: { clean: '{}', busy: true } }")
        self.assertEqual(got, {"sub": [], "tell": []})
        got = self.ask("{ screen: 'info', touched: true, disabled: true }")
        self.assertEqual(got, {"sub": [], "tell": []})

    def test_a_saved_form_is_not_saved_again(self):
        got = self.ask("{ screen: 'add', add: { clean: '{}', saved: true } }")
        self.assertEqual(got["sub"], [])

    def test_info(self):
        self.assertEqual(self.ask("{ screen: 'info', touched: true }")["sub"], ["#infoForm"])
        got = self.ask("{ screen: 'info' }")
        self.assertEqual(got, {"sub": [], "tell": [["save_none", "nothing"]]})

    def test_any_other_screen(self):
        self.assertEqual(self.ask("{ screen: 'list' }"), {"sub": [], "tell": [["save_none", "no_form"]]})


class Wiring(unittest.TestCase):
    def setUp(self):
        self.js = read("mary/app.js")

    def test_only_the_servers_word_reaches_the_save(self):
        rest = self.js.replace(slice_js(self.js, PIECE, END), "")
        self.assertEqual(rest.count("deepSaveHeard("), 2)  # liveHeard and Normal's reply, both behind save: true
        self.assertIn("if (j && j.save && !j.send) { deepSaveHeard(); }", rest)
        self.assertIn("if (d.save && !d.emergency) { await deepSaveHeard(); }", rest)
        self.assertNotIn("what: 'save'", rest)
        self.assertEqual(self.js.count("deepPost({ what: 'save' })"), 1)

    def test_a_tool_call_cannot_reach_it(self):
        tool = slice_js(self.js, "function liveToolCall(c, tc) {", "// Typed words while Live is open")
        self.assertNotIn("deepSave", tool)
        self.assertNotIn("requestSubmit", self.js)

    def test_the_emergency_comes_first_in_a_live_line(self):
        heard = slice_js(self.js, "function liveHeard(c, text) {", "function liveEmergency(c, j) {")
        self.assertLess(heard.index("j.emergency"), heard.index("j.save"))

    def test_typed_words_take_the_same_road(self):
        self.assertIn("liveHeard(c, text)", slice_js(self.js, "function liveTyped(c, text) {", "liveRestartAfter"))

    def test_a_result_never_presses_anything(self):
        message = slice_js(self.js, "function onDeepMessage(ev) {", "// Piece 3: what the screen tools")
        for word in ("saved_ok", "saved_fail", "save_none"):
            self.assertIn(word, message)
        self.assertNotIn("deepPost", message)
        self.assertNotIn("deepSaveHeard", message)

    def test_screens_have_no_save(self):
        js = read("mary/screens.js")
        for word in ("requestSubmit", ".submit(", "saveBtn", "infoSave", "'save'"):
            self.assertNotIn(word, js)

    def test_the_frame_presses_save_in_one_place(self):
        js = read("app.js")
        self.assertEqual(js.count("requestSubmit"), 2)
        self.assertIn("requestSubmit", slice_js(js, "function maryAskedSave() {", "const SCREENS = ["))
        self.assertEqual(js.count("d.what === 'save'"), 1)

    def test_no_values_in_the_frames_answer(self):
        seen = 0
        for line in read("app.js").splitlines():
            if re.search(r"toMary\('(?:saved_ok|saved_fail|save_none)'", line):
                seen += 1
                self.assertNotRegex(line.split("//")[0], r"\.value|\bmessage\b|\btext\b|err\.")
        self.assertGreaterEqual(seen, 6)


class Tools(unittest.TestCase):
    def test_use_screen_has_no_save_and_refuses_one(self):
        script = r"""
        var fs = require('fs'), vm = require('vm');
        global.window = {}; global.document = {};
        vm.runInThisContext(fs.readFileSync(%s, 'utf8'));
        var M = window.MaryScreens;
        var env = { doc: function () { return null; }, panel: function () { return null; }, turns: [] };
        Promise.all([
          M.run('use_screen', { action: 'save' }, env), M.run('use_screen', { action: 'submit' }, env),
          M.run('save_form', {}, env), M.run('save', {}, env)
        ]).then(function (r) {
          console.log(JSON.stringify({ r: r, actions: Object.keys(M.ACTIONS), tools: M.TOOL_NAMES }));
        });
        """ % json.dumps(str(ROOT / "web" / "mary" / "screens.js"))
        got = node(script)
        self.assertTrue(all(res.get("ok") is False for res in got["r"]))
        self.assertFalse([word for word in got["actions"] + got["tools"] if "save" in word or "submit" in word])


REPLY = {"text": "Okay.", "notice": "", "steps": "", "mood": "talking", "effects": [], "emergency": "", "gemini_alert": False, "offer": None,
         "logged": False, "error": None, "first_words_s": 0, "total_s": 0}


class Server(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        self.addCleanup(server.set_skill_host_for_tests, server._skill_host)

    def heard(self, text, **more):
        status, got, _ = helpers.api("POST", "/api/mary/heard", {"text": text, **more})
        self.assertEqual(status, 200)
        return got

    def test_a_plain_save_it_is_answered(self):
        self.assertIs(self.heard("Okay, save it.").get("save"), True)

    def test_chatty_words_are_not(self):
        for line in ("okay", "yes", "that's right", "sounds good", "Is that right?", "Save it? I don't know yet"):
            self.assertNotIn("save", self.heard(line), line)

    def test_not_when_garbled(self):
        with mock.patch.object(mary, "not_english", return_value=True):
            got = self.heard("save it")
        self.assertTrue(got["garbled"])
        self.assertNotIn("save", got)

    def test_not_in_an_emergency(self):
        with mock.patch.object(mary, "is_emergency", return_value="medical"), \
                mock.patch.object(mary, "emergency_text", return_value="Call 911."):
            got = self.heard("save it")
        self.assertTrue(got["emergency"])
        self.assertNotIn("save", got)

    def test_not_from_a_note_being_dictated(self):
        self.assertNotIn("save", self.heard("save it", note=True))

    def test_the_gates_answer_wins(self):
        out = {"action": "tap", "say": "Tap it.", "effects": [], "skip_brain": True}
        server.set_skill_host_for_tests(types.SimpleNamespace(resident_said=lambda text, garbled=False: out, gate=None))
        got = self.heard("save it")
        self.assertEqual(got["send"]["action"], "tap")
        self.assertNotIn("save", got)

    def test_a_broken_check_saves_nothing(self):
        with mock.patch.object(send_gate, "is_plain_save", side_effect=RuntimeError("no")):
            self.assertFalse(server.save_heard("save it", ""))

    def test_her_own_line_is_no_word_of_theirs(self):
        status, got, _ = helpers.api("POST", "/api/mary/live/said", {"text": "Save it. Saved."})
        self.assertEqual(status, 200)
        self.assertNotIn("save", got)

    def test_normal_talk(self):
        with mock.patch.object(mary, "reply", return_value=dict(REPLY)):
            self.assertTrue(server.mary_talk("save it")["save"])
            self.assertFalse(server.mary_talk("yes")["save"])
        with mock.patch.object(mary, "reply", return_value={**REPLY, "emergency": "medical"}):
            self.assertFalse(server.mary_talk("save it")["save"])
        with mock.patch.object(mary, "reply", return_value={**REPLY, "gemini_alert": True}):
            self.assertFalse(server.mary_talk("save it")["save"])


if __name__ == "__main__":
    unittest.main()
