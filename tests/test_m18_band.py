from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M18 piece 2, small Mary and the band: static CSS numbers from mockups/mary/round9/README.md, plus Node for the gates
(a panel no longer ends a talk, her full screens beat the band and the deep view comes back)."""
import re
import unittest
from pathlib import Path

from tests.test_m18_frame import PARENT_STUBS, deep_block, read, run_node

ROOT = Path(__file__).resolve().parent.parent


def slice_js(js, start, end):
    i = js.index(start)
    return js[i:js.index(end, i)]


def rule(css, selector):
    m = re.search(r"(?m)^" + re.escape(selector) + r"\{([^}]*)\}", css)
    return m.group(1).replace("\n", "") if m else ""


class SizesTests(unittest.TestCase):
    def test_the_band(self):
        css = read("mary/mary.css")
        band = rule(css, ".deep-band")
        self.assertIn("height:156px", band)
        self.assertIn("radial-gradient(ellipse at 50% 42%,#fffaf0 0%,#fff0d2 50%,#fadcaa 100%)", band)  # her warm background
        self.assertIn("inset 0 -3px 0 rgba(43,31,23,.18)", band)
        self.assertIn("#fdf8ee 0%,#f6e8cc 50%,#e9cf9f 100%", css)  # and Sam's

    def test_small_mary_is_a_132_circle_and_not_a_button(self):
        css = read("mary/mary.css")
        small = rule(css, ".m9-small")
        for bit in ("left:16px", "top:12px", "width:132px", "height:132px", "border-radius:50%", "cursor:pointer",
                    "touch-action:manipulation", "pointer-events:none"):
            self.assertIn(bit, small)
        self.assertIn("radial-gradient(circle at 50% 42%,#fffdf8 0%,#fff6e4 70%,#ffedcf 100%)", css)
        self.assertIn("#scr[data-small] .m9-small{visibility:visible;opacity:1;pointer-events:auto", css)
        page = read("mary.html")
        self.assertIn('<div id="smallMary" class="m9-small"', page)
        self.assertNotIn('<button id="smallMary"', page)

    def test_the_ring_uses_the_same_classes_as_her_edge_glow(self):
        css = read("mary/mary.css")
        ring = rule(css, ".m9-ring")
        self.assertIn("inset 0 0 0 5px var(--glow)", ring)
        self.assertIn("0 0 10px 3px var(--glow)", ring)
        self.assertIn(".mf-root.mf-listen) .m9-ring{--glow:rgb(95,170,215);animation-duration:3s}", css)
        self.assertIn(".mf-root.mf-think) .m9-ring{--glow:rgb(160,140,215);animation-duration:8s}", css)
        self.assertIn('.mf-root[data-companion="him"]) .m9-ring{--glow:rgb(214,140,50)}', css)
        self.assertIn("@media (prefers-reduced-motion:reduce){.m9-ring{animation:none}}", css)

    def test_her_words_sit_beside_her(self):
        css = read("mary/captions.css")
        words = rule(css, "#scr .cap.m9-words")
        for bit in ("left:164px", "right:416px", "font-size:32px", "height:2.4em", "top:calc(78px - 1.2em)"):
            self.assertIn(bit, words)  # 1280 - 416 = 864; (156 - 2.4em) / 2 from the top
        self.assertIn("#scr .cap.m9-words .w{-webkit-text-stroke:9px #ffffff}", css)
        self.assertIn("#scr .cap.m9-words .w::before{-webkit-text-stroke:2px #4a3426}", css)
        self.assertIn("#scr .cap.m9-words .w::after{-webkit-text-stroke:2px var(--ink,#9b2c58)}", css)
        self.assertLess(css.index("#scr[data-aside] .cap{"), css.index("#scr .cap.m9-words{"))  # same weight, so it must come later

    def test_back_to_mary(self):
        css = read("mary/mary.css")
        self.assertIn("width:368px", rule(css, ".menu-btn.m9-back"))
        menu = rule(css, ".menu-btn")
        for bit in ("top:28px", "right:28px", "height:96px", "font:700 34px/1"):
            self.assertIn(bit, menu)  # x 884-1252, y 28-124
        page = read("mary.html")
        self.assertIn('id="deepBack" class="menu-btn m9-back"', page)
        self.assertIn('class="backLbl"', page[page.index('id="deepBack"'):])

    def test_the_menu_button_stays_off_the_band(self):
        css = read("mary/mary.css")
        self.assertIn("#scr[data-small] #menuBtn,#scr.band-move #menuBtn", css)
        self.assertIn("#scr[data-small] .sheetcard .back{display:none}", css)

    def test_stacking_inside_her_page(self):
        css = read("mary/mary.css")
        self.assertIn("z-index:6", rule(css, ".deep"))
        self.assertIn("#scr[data-small] #face{z-index:7;", css)
        self.assertIn("z-index:8", rule(css, ".m9-small"))
        self.assertIn("z-index:50", rule(css, ".overlay"))  # the typing box is above the band
        self.assertIn("z-index:5", read("mary/skills.js"))  # a skill screen is under it

    def test_panels_are_a_plain_page_under_the_band(self):
        sheet = rule(read("mary/mary.css"), ".overlay.sheet")
        self.assertIn("top:156px", sheet)
        self.assertIn("background:#fbf7ef", sheet)
        self.assertNotIn("rgba", sheet)

    def test_only_transform_and_opacity_move(self):
        css = read("mary/mary.css") + read("mary/face.css")
        self.assertIn("#face{transform-origin:0 0;transition:transform .5s", css)
        self.assertNotRegex(css, r"transition:[^;}]*clip-path")

    def test_the_bottom_row(self):
        css = read("styles.css")
        row = rule(css, ".m9-row")
        for bit in ("position:fixed", "bottom:0", "height:88px", "background:#ffffff", "inset 0 3px 0 #d9cbb8"):
            self.assertIn(bit, row)
        save = rule(css, ".m9-row .save,.m9-row .primary")
        for bit in ("width:300px", "height:72px", "background:#0f5560", "color:#ffffff", "font:700 32px/1"):
            self.assertIn(bit, save)
        self.assertIn("#add,#info{padding-bottom:104px}", css)   # the scroll ends above the row
        self.assertIn("html{scroll-padding-bottom:104px}", css)  # and a focused field clears it

    def test_save_stays_inside_each_form(self):
        html = read("index.html")
        form = html[html.index('<form id="form"'):html.index("</form>")]
        self.assertRegex(form, r'<div class="m9-row"><button type="submit" class="save" id="saveBtn">Save</button></div>')
        info = html[html.index('<form id="infoForm"'):]
        info = info[:info.index("</form>")]
        self.assertRegex(info, r'class="m9-row">.*id="infoSaved".*id="infoSave"')

    def test_saved_check_is_shown_after_a_save_and_cleared_by_a_change(self):
        js = read("app.js")
        self.assertIn("$('#infoSaved').hidden = false;", js)
        self.assertIn("$('#infoForm').addEventListener('input', () => { $('#infoSaved').hidden = true; });", js)
        self.assertNotIn("toast('Saved.')", js)


class HandlerTests(unittest.TestCase):
    def test_tap_and_back_are_the_same_way_home(self):
        js = read("mary/app.js")
        self.assertIn("$('deepBack').addEventListener('click', bandBack);", js)
        self.assertIn("$('smallMary').addEventListener('click', bandBack);", js)

    def test_the_wake_word_leaves_a_panel_open_and_still_closes_the_menu(self):
        js = read("mary/app.js")
        wake = slice_js(js, "} else if (ev.type === 'wake') {", "startTalk({ say: WAKE_SAY")
        self.assertNotIn("closePanel", wake)
        self.assertIn("closeMenu(false)", wake)
        self.assertIn("closeTyping(false)", wake)

    def test_a_panel_holds_no_live_talk_open(self):
        js = read("mary/app.js")
        idle = slice_js(js, "function liveIdleCheck(c)", "if (c.story && !c.story.paused)")
        self.assertNotIn("uiOpen", idle)
        self.assertIn("menuOpen()", idle)  # the menu keeps today's behaviour

    def test_the_stand_ins_know_the_new_calls(self):
        js = read("mary/app.js")
        self.assertIn("setSmall: noop", js)
        self.assertIn("setBand: noop", js)


class GeometryTests(unittest.TestCase):
    def node(self, body):
        face = read("mary/face.js")
        fn = slice_js(face, "function smallBox(w, h) {", "global.MaryFace =")
        code, out, both = run_node("const assert = require('assert');\n" + fn + body)
        self.assertEqual(code, 0, both)

    def test_board_e1_at_1280x800(self):
        self.node(r"""
var b = smallBox(1280, 800);
assert.ok(Math.abs(b.scale - 0.23571) < 1e-4);
assert.ok(Math.abs(b.x + 68.86) < 0.01, b.x);
assert.ok(Math.abs(b.y + 11.57) < 0.01, b.y);
assert.deepStrictEqual([b.cx, b.cy, b.r], [640, 380, 280]);
""")

    def test_her_head_lands_on_the_circle_at_any_window(self):
        self.node(r"""
[[1366, 768], [1920, 1080], [1024, 768], [800, 600], [2560, 1080]].forEach(function (s) {
  var b = smallBox(s[0], s[1]);
  assert.ok(Math.abs(b.x + b.scale * b.cx - 82) < 1e-6, 'x ' + s);    // 16 + 132 / 2
  assert.ok(Math.abs(b.y + b.scale * b.cy - 78) < 1e-6, 'y ' + s);    // 12 + 132 / 2
  assert.ok(Math.abs(b.scale * b.r - 66) < 1e-6, 'r ' + s);
});
""")


class CaptionTests(unittest.TestCase):
    def test_a_band_line_stops_at_32_characters(self):
        code, _, both = run_node(r"""
const assert = require('assert');
const C = require('./web/mary/captions.js');
const ws = 'Tell me what to change, or ask about anything here.'.split(' ');
const w = ws.map(function () { return 10; }), c = ws.map(function (t) { return t.length; });
const ln = C.breakLines(w, 700, 5, c, C.BAND_CHARS);
assert.strictEqual(C.BAND_CHARS, 32);
const lines = {};
ws.forEach(function (t, i) { (lines[ln[i]] = lines[ln[i]] || []).push(t); });
Object.keys(lines).forEach(function (k) { assert.ok(lines[k].join(' ').length <= 32, lines[k].join(' ')); });
assert.ok(Object.keys(lines).length === 2);
assert.deepStrictEqual(C.breakLines(w, 700, 5), ws.map(function () { return 0; }), 'no cap outside the band');
""")
        self.assertEqual(code, 0, both)

    def test_set_band_measures_again(self):
        js = read("mary/captions.js")
        band = slice_js(js, "setBand: function (on) {", "// A plain line for things")
        self.assertIn("cap.classList.toggle('m9-words', on)", band)
        self.assertIn("layout(true)", band)


BAND_STUBS = r"""
var attrs = {}, rootC = {}, sets = [], words = [], timers = [];
function list(store) { return { contains: function (c) { return !!store[c]; }, toggle: function (c, on) { store[c] = on; },
  add: function (c) { store[c] = true; }, remove: function (c) { store[c] = false; } }; }
els.scr = { classList: list(rootC), toggleAttribute: function (a, on) { attrs[a] = on; } };
var D = { activeElement: null, body: {} };
var face = { setSmall: function (on) { sets.push(on); } };
var cap = { setBand: function (on) { words.push(on); } };
function capCall(fn) { return fn(); }
setTimeout = function (fn, ms) { timers.push([fn, ms]); return timers.length; };
clearTimeout = function (t) { if (t) { timers[t - 1] = [function () {}, 0]; } };
function flush(ms) { timers.splice(0).filter(function (t) { return t[1] <= ms; }).forEach(function (t) { t[0](); }); }
"""


def band_node(body, stubs=""):
    code = (PARENT_STUBS + stubs + deep_block() + BAND_STUBS + "\n(async function () {\n" + body +
            "\n})().catch(function (e) { console.error(e); process.exit(1); });")
    return run_node(code)


class DeepGateTests(unittest.TestCase):
    def go(self, body):
        code, _, both = band_node(body)
        self.assertEqual(code, 0, both)

    def test_she_goes_small_with_the_deep_view_and_grows_back(self):
        self.go(r"""
openDeep('#info');
assert.strictEqual(attrs['data-small'], true);
assert.deepStrictEqual(sets, [true]);
assert.deepStrictEqual(words, [true], 'her words go to the band at once');
closeDeep();
assert.strictEqual(attrs['data-small'], false);
assert.deepStrictEqual(sets, [true, false]);
assert.deepStrictEqual(words, [true], 'her words wait for the page to go');
assert.strictEqual(rootC['band-move'], true);
flush(BAND_WORDS_MS);
assert.deepStrictEqual(words, [true, false]);
""")

    def test_tapping_twice_only_closes_once(self):
        self.go(r"""
openDeep('#info');
calls.length = 0;
bandBack(); bandBack();
assert.strictEqual(calls.filter(function (c) { return c === 'status'; }).length, 1);
""")

    def test_the_frame_waits_for_its_first_screen(self):
        self.go(r"""
openDeep('#info');
assert.ok(!classes.ready, 'not before it is ready');
msg({ type: 'mary-deep', what: 'screen', name: 'info' });
assert.strictEqual(classes.ready, true);
frameLoc.hash = '#info';
openDeep('#info');
assert.strictEqual(classes.ready, true, 'the same screen: no wait, no word would come');
openDeep('#list');
assert.ok(!classes.ready, 'a new screen waits');
msg({ type: 'mary-deep', what: 'screen', name: 'list' });
assert.strictEqual(classes.ready, true);
""")

    def test_the_timer_is_the_way_out_of_a_frame_that_never_answers(self):
        self.go(r"""
openDeep('#info');
assert.ok(timers.some(function (t) { return t[1] === DEEP_READY_MS; }));
flush(DEEP_READY_MS);
assert.strictEqual(classes.ready, true);
""")

    def test_a_skill_screen_she_opens_hides_it_and_it_comes_back(self):
        self.go(r"""
openDeep('#add');
msg({ type: 'mary-deep', what: 'screen', name: 'add' });
posts.length = 0;
S.skill = 'word_search'; S.screen = 'word_search'; deepSync();
assert.strictEqual(deepUp(), false);
assert.ok(!up(), 'she comes up full with that screen');
assert.strictEqual(attrs['data-small'], false);
assert.deepStrictEqual(posts.map(function (p) { return p[0].what; }), ['hide'], 'a running mic stops and keeps its words');
S.skill = undefined; show('everyday');
assert.ok(up(), 'the deep view comes back as it was');
assert.strictEqual(attrs['data-small'], true);
assert.strictEqual(srcs.length, 1, 'never reloaded');
""")

    def test_opened_from_a_skill_screen_it_shows_over_that_screen(self):
        self.go(r"""
S.skill = 'word_search'; S.screen = 'word_search';
openDeep('#info');
assert.ok(up());
S.skill = 'crossword'; S.screen = 'crossword'; deepSync();
assert.ok(!up(), 'a different screen she opens still beats it');
""")

    def test_emergency_beats_the_band_with_no_move(self):
        self.go(r"""
openDeep('#info');
flush(BAND_MOVE_MS);
S.screen = 'emergency'; deepSync();
assert.ok(!up());
assert.strictEqual(rootC['band-snap'], true);
assert.strictEqual(rootC['band-move'], false);
assert.deepStrictEqual(words, [true, false], 'her words go at once');
""")

    def test_a_panel_gets_the_band_without_the_frame(self):
        code, _, both = band_node(r"""
panel = true; bandSync();
assert.ok(up());
assert.strictEqual(classes.noframe, true);
assert.strictEqual(attrs['data-small'], true);
bandBack();
assert.strictEqual(panel, false, 'Back and small Mary close the panel');
assert.ok(!up());
openDeep('#info'); panel = true; bandSync();
assert.strictEqual(classes.noframe, false, 'over the deep view the frame stays under it');
bandBack();
assert.ok(up(), 'closing it goes back to the deep view');
""", stubs=r"""
var panel = false;
panelOpen = function () { return panel; };
closePanel = function () { panel = false; bandSync(); };
""")
        self.assertEqual(code, 0, both)

    def test_a_removed_key_goes_to_nokey_unless_a_talk_is_open(self):
        self.go(r"""
S.statusLoaded = true; S.hasKey = false;
openDeep('#info'); calls.length = 0;
S.convo = { lastAct: 1 };
closeDeep(); await Promise.resolve(); await Promise.resolve();
assert.strictEqual(S.screen, 'everyday', 'a talk stays on her face');
S.convo = null; openDeep('#info');
closeDeep(); await Promise.resolve(); await Promise.resolve();
assert.strictEqual(S.screen, 'nokey');
""")


def talk_node(body):
    js = read("mary/app.js")
    convo = slice_js(js, "function convoNext(c) {", "// A short goodbye in Normal/Offline")
    idle = slice_js(js, "function armIdle(ms) {", "function menuItems()")
    return run_node(r"""
const assert = require('assert');
var CONVO_IDLE_S = 15, PANEL_IDLE_MS = 120000;
var S = { convo: null, phase: 'idle', screen: 'everyday' }, Sp = { sess: null }, M = { panel: null, timer: 0 };
var typingHidden = true, menu = false, band = false, closed = 0, listens = 0, panelsClosed = 0, menusClosed = 0, pending = [];
function $() { return { hidden: typingHidden }; }
function skillScreen() { return undefined; }
function menuOpen() { return menu; }
function bandUp() { return band; }
function closeConvo() { closed++; }
function convoListen() { listens++; }
function setPhase() {} function updateTalkButton() {}
function closePanel() { panelsClosed++; M.panel = null; }
function closeMenu() { menusClosed++; }
setTimeout = function (fn) { pending.push(fn); return pending.length; };
clearTimeout = function () {};
""" + convo + idle + body)


class PanelTalkTests(unittest.TestCase):
    def go(self, body):
        code, _, both = talk_node(body)
        self.assertEqual(code, 0, both)

    def test_a_panel_does_not_end_a_normal_talk(self):
        self.go(r"""
M.panel = 'infoPanel';
var c = { lastAct: Date.now() }; S.convo = c;
convoNext(c);
assert.strictEqual(closed, 0);
assert.strictEqual(listens, 1);
""")

    def test_the_menu_still_ends_it(self):
        self.go(r"""
menu = true; var c = { lastAct: Date.now() }; S.convo = c;
convoNext(c);
assert.strictEqual(closed, 1);
""")

    def test_the_typing_box_over_the_band_holds_the_talk_a_while(self):
        self.go(r"""
typingHidden = false; band = true;
var c = { lastAct: Date.now() }; S.convo = c;
convoNext(c);
assert.strictEqual(closed, 0); assert.strictEqual(listens, 0); assert.strictEqual(pending.length, 1);
typingHidden = true; pending.pop()();
assert.strictEqual(listens, 1, 'she listens again when it closes');
typingHidden = false; c.lastAct = 0;
convoNext(c);
assert.strictEqual(closed, 1, 'not for ever');
""")

    def test_the_typing_box_on_her_face_still_ends_it(self):
        self.go(r"""
typingHidden = false; var c = { lastAct: Date.now() }; S.convo = c;
convoNext(c);
assert.strictEqual(closed, 1);
""")

    def test_the_idle_close_waits_for_the_talk_to_end(self):
        self.go(r"""
M.panel = 'canPanel'; S.convo = { lastAct: 1 };
armIdle(PANEL_IDLE_MS);
pending.shift()();
assert.strictEqual(panelsClosed, 0);
assert.strictEqual(pending.length, 1, 'it looks again later');
S.convo = null;
pending.shift()();
assert.strictEqual(panelsClosed, 1);
""")

    def test_the_menu_idle_close_is_unchanged(self):
        self.go(r"""
menu = true; S.convo = { lastAct: 1 };
armIdle(20000);
pending.shift()();
assert.strictEqual(menusClosed, 1);
""")


if __name__ == "__main__":
    unittest.main()
