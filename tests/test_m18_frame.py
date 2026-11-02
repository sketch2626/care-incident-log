from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M18 piece 1, the talk survives: deeper screens open in a frame on Mary's page, so her page never unloads. Static checks
on the served pages, plus Node for the logic on both sides of the frame."""
import re
import subprocess
import unittest
from pathlib import Path

from tests.test_story_js import NODE, between

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


def read(rel):
    return (WEB / rel).read_text(encoding="utf-8")


def deep_block():
    return between(read("mary/app.js"), "// ---------------------------------------------------------------- M18: the deep view",
                   "// ---------------------------------------------------------------- end M18")


def frame_block():
    return between(read("app.js"), "/* ---------- M18: inside Mary's page", "const SCREENS")


def run_node(code):
    run = subprocess.run([NODE, "-"], input=code, capture_output=True, text=True, encoding="utf-8",
                         timeout=30, cwd=str(ROOT))
    return run.returncode, run.stdout, (run.stdout + run.stderr).strip()


class HeaderTests(unittest.TestCase):
    def test_her_own_page_may_frame_it_and_no_outside_site_may(self):
        for path in ("/index.html", "/mary.html", "/api/settings"):
            _, _, headers = helpers.api("GET", path)
            self.assertEqual(headers.get("X-Frame-Options"), "SAMEORIGIN", path)
            csp = headers.get("Content-Security-Policy", "")
            self.assertIn("frame-ancestors 'self'", csp, path)
            self.assertNotIn("*", csp, path)


class ExitTests(unittest.TestCase):
    def test_the_deep_view_is_on_her_page(self):
        page = read("mary.html")
        for bit in ('id="deep"', '<iframe id="deepFrame"', 'allow="clipboard-read; clipboard-write"', 'id="deepBack"'):
            self.assertIn(bit, page)
        self.assertRegex(page, r'<iframe id="deepFrame" title="[^"]+"')
        self.assertNotIn(" src=", page[page.index('<iframe id="deepFrame"'):page.index("</iframe>")])  # only when first opened
        # M18 piece 2: it moved inside #scr (was after </main>), so small Mary can sit above the band and the frame under it
        self.assertLess(page.index('id="face"'), page.index('id="deep"'))
        self.assertLess(page.index('id="deep"'), page.index("</main>"))

    def test_the_way_back_says_the_companions_name_and_is_big(self):
        page = read("mary.html")
        back = page[page.index('id="deepBack"'):page.index("</button>", page.index('id="deepBack"'))]
        self.assertIn('class="backLbl"', back)  # refreshLabels sets every .backLbl: Back to Mary, Back to Sam
        self.assertIn("'Back to ' + n", read("mary/app.js"))
        css = read("mary/mary.css")
        rule = re.search(r"(?m)^\.back\{([^}]*)\}", css).group(1)
        self.assertGreaterEqual(int(re.search(r"min-height:(\d+)px", rule).group(1)), 64)
        self.assertGreaterEqual(int(re.search(r"font:700 (\d+)px", rule).group(1)), 20)

    def test_band_stays_and_frame_scrolls_on_its_own(self):
        css = read("mary/mary.css")
        self.assertIn("top:0;left:0;right:0;height:156px", css)
        self.assertIn("top:156px", css)
        self.assertIn(".menu-btn.m9-back{", css)  # M18 piece 2: was .deep-band .back; it now has the Menu button's shape and place
        self.assertIn("height:calc(100% - 156px)", css)

    def test_closed_it_stays_laid_out_and_cannot_be_touched(self):
        css = read("mary/mary.css")
        rule = re.search(r"(?m)^\.deep\{([^}]*)\}", css).group(1)
        self.assertIn("visibility:hidden", rule)
        self.assertIn("pointer-events:none", rule)
        self.assertNotIn("display:none", rule)
        self.assertIn(".deep.up{visibility:visible;pointer-events:auto}", css)

    def test_every_exit_goes_through_opendeep(self):
        js = read("mary/app.js")
        self.assertIn("if (!openDeep('')) { window.location.href = '/?from=mary'; }", js)
        self.assertIn("if (!openDeep('#info')) { window.location.href = '/?from=mary#info'; }", js)
        self.assertIn("$('moreSettings').addEventListener('click', function (ev) { if (openDeep('#info')) { ev.preventDefault(); } });", js)
        self.assertIn('id="moreSettings" class="row link" href="/?from=mary#info"', read("mary.html"))  # the fallback
        leaves = re.findall(r"[^\n]*location\.(?:href|assign|replace)[^\n]*", js)
        self.assertEqual(len(leaves), 3, leaves)
        for line in leaves:
            self.assertIn("if (!openDeep(", line)

    def test_she_loads_the_log_in_mary_mode(self):
        self.assertIn("var DEEP_URL = '/?from=mary&in=mary';", deep_block())
        self.assertIn("f.src = DEEP_URL + hash;", deep_block())

    def test_opendeep_and_closedeep_are_on_maryapp(self):
        js = read("mary/app.js")
        self.assertIn("openDeep: openDeep,", js)
        self.assertIn("closeDeep: closeDeep,", js)

    def test_the_deep_view_leaves_the_talk_and_the_page_alone(self):
        block = deep_block()
        for word in ("closeConvo", "endConvo", "newTurn", "location.href", "location.reload", "pagehide", "S.convo =",
                     "S.convo=", "wakeStop", "spCancel", "armIdle", "PANEL_IDLE_MS", ".src = ''", 'src = ""', "removeAttribute"):
            self.assertNotIn(word, block)

    def test_the_deep_view_is_no_part_of_uiopen(self):
        js = read("mary/app.js")
        self.assertIn("function uiOpen() { return menuOpen() || !!M.panel; }", js)
        self.assertNotIn("Deep", between(js, "function armIdle(ms)", "function menuItems()"))
        wake = between(js, "} else if (ev.type === 'wake') {", "startTalk({ mood: 'happy' })")
        self.assertNotRegex(wake, r"[Dd]eep")
        self.assertNotRegex(between(js, "function startTalk(opts)", "var c = { mode: mode"), r"[Dd]eep")

    def test_she_does_not_doze_off_behind_a_form(self):
        self.assertIn("!panel && !deep", read("mary/firstrun.js"))
        self.assertIn("D.querySelector('.deep.up')", read("mary/firstrun.js"))

    def test_a_status_refresh_mid_talk_leaves_her_voice_alone(self):
        apply = between(read("mary/app.js"), "function applyStatus(st)", "function refreshStatus()")
        self.assertIn("if (!S.convo) { S.voiceMode", apply)
        self.assertNotIn("c.voice", apply)


class InMaryPageTests(unittest.TestCase):
    def test_early_script_and_css(self):
        html = read("index.html")
        head = html[:html.index("</head>")]
        self.assertIn("c.add('in-mary')", head)
        self.assertIn("/[?&]in=mary(&|$)/", head)
        self.assertIn("window.parent!==window", head)  # alone in a window, the bar stays: it's the only way back
        css = read("styles.css")
        self.assertIn("html.in-mary .marybar{display:none}", css)
        self.assertLess(css.index("html.from-mary .marybar{display:block}"), css.index("html.in-mary .marybar{display:none}"))
        self.assertIn("html.mary-talking #micwrap,html.mary-talking [data-talk]{display:none!important}", css)

    def test_saving_never_touches_the_hidden_button_and_the_toast_is_true(self):
        js = read("app.js")
        # M18 piece 2: the end marker was the plain toast('Saved.'), gone now that a check shows beside Save
        save = between(js, "toMary('saved'); // M18: a key saved here", "$('#infoError').textContent = err.message")
        self.assertLess(save.index("if (IN_MARY)"), save.index("else if (FROM_MARY)"))
        frame = between(save, "if (IN_MARY)", "else if (FROM_MARY)")
        self.assertNotIn("focus(", frame)
        self.assertNotIn("to talk again", frame)  # a talk may still be going on
        self.assertIn("state.settings.companion === 'him' ? 'Sam' : 'Mary'", frame)
        self.assertIn('Back to ${who}', frame)

    def test_every_link_to_her_page_closes_the_frame(self):
        html = read("index.html")
        self.assertEqual(re.findall(r'href="(/mary\.html)"', html), ["/mary.html"])  # #maryLink: the delegated click covers it
        block = frame_block()
        self.assertIn("a.pathname === '/mary.html'", block)
        self.assertIn("e.preventDefault(); toMary('close');", block)
        self.assertIn("if (IN_MARY) toMary('close'); else location.href = '/mary.html';", read("app.js"))

    def test_messages_are_targeted_and_never_carry_values(self):
        js, block, mary = read("app.js"), frame_block(), deep_block()
        self.assertNotIn("'*'", block + mary)
        self.assertEqual(js.count("postMessage("), 1)
        self.assertIn("window.parent.postMessage({ type: 'mary-deep', what, ...more }, location.origin)", js)
        self.assertEqual(mary.count("postMessage("), 1)
        self.assertIn("postMessage(msg, window.location.origin)", mary)
        self.assertIn("e.origin !== location.origin || e.source !== window.parent", block)
        self.assertIn("ev.origin !== window.location.origin || !f || ev.source !== f.contentWindow", mary)
        shape = r"(?:, \{ ?(?:on|name: id|why: '\w+'|form: '\w+'|label: label \|\| FORM_MISSING\[focusSel\] \|\| '')? ?\})?"  # piece 4: fixed words, never a value
        told = set(re.findall(r"toMary\('(\w+)'" + shape + r"\)", js))
        self.assertEqual(told, {"activity", "close", "mic", "saved", "screen", "saved_ok", "saved_fail", "save_none"})
        self.assertEqual(len(re.findall(r"toMary\('", js)), len(re.findall(r"toMary\('\w+'" + shape + r"\)", js)))
        self.assertEqual(set(re.findall(r"deepPost\(\{ what: '(\w+)'", mary)), {"talk", "hide", "save"})

    def test_paste_uses_the_apps_bridge_on_her_page_and_no_message(self):
        js = read("app.js")
        paste = js[js.index("async function readClipboard"):js.index("$('#infoForm').addEventListener('keydown'")]
        self.assertIn("window.parent.pywebview && window.parent.pywebview.api", paste)
        self.assertIn("try {", paste[:paste.index("app.paste_text")])
        self.assertNotIn("postMessage", paste)
        self.assertNotIn("toMary", paste)

    def test_a_field_mic_that_starts_after_a_stop_lets_go(self):
        talk = between(read("app.js"), "async function talkInto(id)", "$$('[data-talk]').forEach")
        self.assertIn("if (t !== mic.token) api('/api/listen/stop?raw=1'", talk)

    def test_print_and_download_cannot_strand_the_frame(self):
        js = read("mary/app.js")
        self.assertIn("return l.pathname === '/' && /[?&]in=mary(&|$)/.test(l.search);", js)  # off the log page, it reloads
        self.assertIn("location.href = url", read("app.js"))
        import reports
        self.assertIn('id="reportBack"', reports.build_report_html([], {}))  # the frame's own way back from there


PARENT_STUBS = r"""
const assert = require('assert');
var S = { convo: null, phase: 'idle', screen: 'everyday', hasKey: true, firstRun: false, formMic: false };
var calls = [], posts = [], srcs = [], holds = 0, frameLoc = { pathname: 'blank', search: '', hash: '' };
var frameWin = { location: frameLoc, postMessage: function (m, o) { posts.push([JSON.parse(JSON.stringify(m)), o]); } };
var classes = {}, frame = { contentWindow: frameWin };
Object.defineProperty(frame, 'src', { set: function (v) {
  srcs.push(v); var u = v.split('#');
  frameLoc.pathname = '/'; frameLoc.search = u[0].slice(1); frameLoc.hash = u[1] ? '#' + u[1] : '';
} });
var els = { deepFrame: frame, deepBack: { focus: function () {} }, menuBtn: { focus: function () {} },
  deep: { setAttribute: function () {}, classList: {
    contains: function (c) { return !!classes[c]; }, toggle: function (c, on) { classes[c] = on; } } } };
var window = { location: { origin: 'http://127.0.0.1:1' } };
function $(id) { return els[id] || null; }
function log(e) { throw e; }
function menuOpen() { return false; }
function closeMenu() { calls.push('closeMenu'); }
function closePanel() { calls.push('closePanel'); }
function panelOpen() { return false; }
function panelBeaten() {}
function skillScreen() { return S.skill; }
function wakeHoldCheck() { holds++; }
function refreshStatus() { calls.push('status'); return Promise.resolve(); }
function show(n) { S.screen = n; calls.push('show ' + n); deepSync(); }
function api(m, u) { calls.push(m + ' ' + u); return Promise.resolve({}); }
var App = { enterMain: function () { calls.push('enterMain'); }, startFirstRun: function () { calls.push('firstRun'); },
  keepTalk: function () { if (S.convo) { S.convo.lastAct = S.convo.lastLife = Date.now(); } } };
function msg(d, origin, source) {
  onDeepMessage({ origin: origin === undefined ? window.location.origin : origin,
    source: source === undefined ? frameWin : source, data: d });
}
function kind(what) { return { type: 'mary-deep', what: what }; }
var up = function () { return !!classes.up; };
"""

PARENT_CHECKS = r"""
(async function () {
  // first open loads it, a later open only moves the hash
  assert.strictEqual(openDeep('#info'), true);
  assert.deepStrictEqual(srcs, ['/?from=mary&in=mary#info']);
  assert.ok(up());
  assert.ok(calls.indexOf('closePanel') >= 0, 'its panel closes');
  frameLoc.hash = '#add';
  openDeep('');
  assert.strictEqual(frameLoc.hash, '#add', 'half-typed work stays put');
  openDeep('#list');
  assert.strictEqual(frameLoc.hash, '#list');
  assert.strictEqual(srcs.length, 1, 'never reloaded');

  // closing hides, keeps the page, leaves the talk, and re-reads what changed
  var talk = { lastAct: 1, lastLife: 1 };
  S.convo = talk; calls.length = 0;
  closeDeep();
  assert.ok(!up());
  assert.strictEqual(S.convo, talk);
  assert.strictEqual(srcs.length, 1);
  assert.ok(calls.indexOf('status') >= 0);
  assert.ok(posts.some(function (p) { return p[0].what === 'hide'; }));
  await deepCameBack();
  assert.ok(calls.indexOf('enterMain') < 0, 'not on the no-key screen');

  // off the log page (the report with no new window), the next open goes back to it
  frameLoc.pathname = '/report'; frameLoc.search = '?from=2026-01-01';
  openDeep('');
  assert.strictEqual(srcs.length, 2);
  assert.strictEqual(srcs[1], '/?from=mary&in=mary');

  // the emergency screen: hidden, not unloaded, and back as it was
  frameLoc.hash = '#add';
  show('emergency');
  assert.ok(!up(), 'nothing covers the buttons');
  assert.strictEqual(Deep.open, true);
  show('everyday');
  assert.ok(up());
  assert.strictEqual(frameLoc.hash, '#add');
  assert.strictEqual(srcs.length, 2);

  // only this origin, only this frame, only our kind of message
  S.convo = null; calls.length = 0;
  msg(kind('close'), 'http://evil.example');
  msg(kind('close'), undefined, { other: true });
  msg(kind('close'), 'null');
  msg({ what: 'close' });
  msg(null);
  msg('close');
  assert.ok(up());
  assert.strictEqual(calls.length, 0);
  msg(kind('saved'));
  assert.ok(calls.indexOf('status') >= 0);
  msg({ type: 'mary-deep', what: 'screen', name: 'add' });
  assert.strictEqual(Deep.screen, 'add');

  // filling a form is not being quiet
  S.convo = { lastAct: 1, lastLife: 1 };
  msg(kind('activity'));
  assert.ok(S.convo.lastAct > 1 && S.convo.lastLife > 1 && S.convo.formAt > 1);
  S.convo = null;

  // the form's mic holds the wake word, and always lets go
  holds = 0;
  msg({ type: 'mary-deep', what: 'mic', on: true });
  assert.strictEqual(S.formMic, true);
  assert.strictEqual(holds, 1);
  msg({ type: 'mary-deep', what: 'mic', on: false });
  assert.strictEqual(S.formMic, false);
  msg({ type: 'mary-deep', what: 'mic', on: true });
  closeDeep();
  assert.strictEqual(S.formMic, false, 'closed: not stuck');
  msg({ type: 'mary-deep', what: 'mic', on: true });
  assert.strictEqual(S.formMic, false, 'a late word from a closed view can not hold it');
  openDeep('');
  msg({ type: 'mary-deep', what: 'mic', on: true });
  show('emergency');
  assert.strictEqual(S.formMic, false, 'emergency: not stuck');
  show('everyday');
  msg({ type: 'mary-deep', what: 'mic', on: true });
  calls.length = 0;
  onDeepLoad();
  assert.strictEqual(S.formMic, false, 'reloaded: not stuck');
  assert.ok(calls.indexOf('POST /api/listen/stop?raw=1') >= 0, 'the recorder is let go too');

  // a frame hears the talk when it changes, once, and again whenever a page loads
  S.convo = null; S.phase = 'idle'; posts.length = 0;
  onDeepLoad();
  deepTalkSync(); deepTalkSync();
  assert.deepStrictEqual(posts.map(function (p) { return p[0]; }), [{ what: 'talk', on: false, type: 'mary-deep' }]);
  assert.strictEqual(posts[0][1], 'http://127.0.0.1:1');
  S.convo = {};
  deepTalkSync(); deepTalkSync();
  assert.strictEqual(posts.length, 2);
  assert.strictEqual(posts[1][0].on, true);
  onDeepLoad();
  assert.strictEqual(posts.length, 3);
  assert.strictEqual(posts[2][0].on, true);
  S.convo = null;

  // a key saved in the frame takes her off the no-key screen the way starting up does
  S.screen = 'nokey'; S.hasKey = false; calls.length = 0;
  await deepCameBack();
  assert.ok(calls.indexOf('enterMain') < 0, 'no key yet');
  S.hasKey = true;
  await deepCameBack();
  assert.ok(calls.indexOf('enterMain') >= 0);
  S.firstRun = true; calls.length = 0;
  await deepCameBack();
  assert.ok(calls.indexOf('firstRun') >= 0);
  S.firstRun = false; S.convo = {}; calls.length = 0;
  await deepCameBack();
  assert.deepStrictEqual(calls.filter(function (c) { return c !== 'status'; }), ['show everyday']);
  console.log('OK parent');
  process.exit(0);
})().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
"""

WAKE_CHECKS = r"""
const assert = require('assert');
var S = { screen: 'everyday', firstRun: false, micHeld: false, convo: null, phase: 'idle', noteBusy: 0, formMic: false };
function noteBusyNow() { return false; } function dictating() { return false; }
assert.strictEqual(wakeWhyNot({}), '');
assert.strictEqual(wakeBusy(), false);
S.formMic = true;
assert.strictEqual(wakeWhyNot({}), 'form mic');
assert.strictEqual(wakeBusy(), true);
S.formMic = false;
assert.strictEqual(wakeWhyNot({}), '', 'the mic let go: her name wakes her again');
assert.strictEqual(wakeBusy(), false);
console.log('OK wake');
"""

FRAME_STUBS = r"""
const assert = require('assert');
var classes = { 'in-mary': true }, listeners = {}, sent = [], calls = [];
var document = { documentElement: { classList: {
    contains: function (c) { return !!classes[c]; }, toggle: function (c, on) { classes[c] = on; } } },
  addEventListener: function (t, f) { (listeners[t] = listeners[t] || []).push(f); } };
var parentWin = { postMessage: function (m, o) { sent.push([m, o]); } };
var window = { parent: parentWin, addEventListener: function (t, f) { (listeners['win ' + t] = listeners['win ' + t] || []).push(f); } };
var location = { origin: 'http://127.0.0.1:1' };
var detail = { textContent: 'listening' };
function $(s) { return s === '#detailStatus' ? detail : null; }
var mic = { state: 'idle' }, field = { id: null, busy: false };
function teardownMic() { calls.push('teardown'); mic.state = 'checking'; field.id = null; field.busy = false; tellMaryMic(); }
function checkMic() { calls.push('check'); }
function stopTalk() { calls.push('stop'); mic.state = 'idle'; tellMaryMic(); return Promise.resolve(); }
function talkInto(id) { calls.push('field ' + id); field.id = null; tellMaryMic(); return Promise.resolve(); }
function hear(d, origin, source) {
  listeners['win message'][0]({ origin: origin === undefined ? location.origin : origin,
    source: source === undefined ? parentWin : source, data: d });
}
function talk(on) { hear({ type: 'mary-deep', what: 'talk', on: on }); }
function hide() { hear({ type: 'mary-deep', what: 'hide' }); }
function whats() { return sent.map(function (s) { return s[0].what; }); }
"""

FRAME_CHECKS = r"""
(async function () {
  // messages go to her page, on this origin
  toMary('screen', { name: 'add' });
  assert.deepStrictEqual(sent[0], [{ type: 'mary-deep', what: 'screen', name: 'add' }, 'http://127.0.0.1:1']);
  sent.length = 0;

  // activity: pointerdown and input, at most once in 5 s
  assert.strictEqual(listeners.pointerdown.length, 1);
  assert.strictEqual(listeners.input.length, 1);
  var now = 100000, real = Date.now;
  Date.now = function () { return now; };
  listeners.pointerdown[0]({}); listeners.input[0]({});
  now += 4999; listeners.input[0]({});
  assert.deepStrictEqual(whats(), ['activity']);
  now += 1; listeners.pointerdown[0]({});
  assert.deepStrictEqual(whats(), ['activity', 'activity']);
  Date.now = real;
  sent.length = 0;

  // the mic is told once per change, and carries only on/off
  mic.state = 'listening'; tellMaryMic(); tellMaryMic();
  assert.deepStrictEqual(sent.map(function (s) { return s[0]; }), [{ type: 'mary-deep', what: 'mic', on: true }]);
  mic.state = 'idle'; tellMaryMic();
  assert.strictEqual(sent.length, 2);
  assert.strictEqual(sent[1][0].on, false);
  sent.length = 0;

  // only her page may speak
  hear({ type: 'mary-deep', what: 'talk', on: true }, 'http://evil.example');
  hear({ type: 'mary-deep', what: 'talk', on: true }, undefined, { other: true });
  hear({ what: 'talk', on: true });
  hear(null);
  assert.ok(!classes['mary-talking']);

  // a talk opens: the buttons go and a running mic stops the way teardownMic does
  talk(true);
  assert.strictEqual(classes['mary-talking'], true);
  assert.deepStrictEqual(calls, [], 'no mic running, nothing to stop');
  talk(false);
  mic.state = 'listening'; tellMaryMic(); sent.length = 0;
  talk(true);
  assert.deepStrictEqual(calls, ['teardown', 'check']);
  assert.strictEqual(detail.textContent, '');
  assert.deepStrictEqual(whats(), ['mic']);
  assert.strictEqual(sent[0][0].on, false, 'the wake word is let go');
  talk(false);
  assert.strictEqual(classes['mary-talking'], false);

  // hidden with the mic running: stopped the way a tap on Stop does, so the words stay in the box
  calls.length = 0; mic.state = 'listening'; tellMaryMic();
  hide();
  await new Promise(function (r) { setTimeout(r, 0); });
  assert.deepStrictEqual(calls, ['stop']);
  calls.length = 0; mic.state = 'idle'; field.id = 'staff'; tellMaryMic();
  hide();
  await new Promise(function (r) { setTimeout(r, 0); });
  assert.deepStrictEqual(calls, ['field staff']);
  calls.length = 0; mic.state = 'working'; tellMaryMic();
  hide();                                      // a start still on its way: wait, then stop
  setTimeout(function () { mic.state = 'listening'; }, 10);
  await new Promise(function (r) { setTimeout(r, 120); });
  assert.deepStrictEqual(calls, ['stop']);

  // a link to her page closes the frame instead of loading her in it
  sent.length = 0;
  var stopped = 0, a = { pathname: '/mary.html' };
  var ev = { target: { closest: function () { return a; } }, preventDefault: function () { stopped++; } };
  listeners.click[0](ev);
  assert.strictEqual(stopped, 1);
  assert.deepStrictEqual(whats(), ['close']);
  a = { pathname: '/report' };
  listeners.click[0](ev);
  assert.strictEqual(stopped, 1, 'other links are left alone');
  assert.strictEqual(sent.length, 1);

  // alone in a window it stays silent
  sent.length = 0;
  console.log('OK frame');
})().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
"""

NOT_IN_FRAME = r"""
const assert = require('assert');
var listeners = 0, sent = 0;
var document = { documentElement: { classList: { contains: function () { return false; } } },
  addEventListener: function () { listeners++; } };
var window = { parent: { postMessage: function () { sent++; } }, addEventListener: function () { listeners++; } };
var location = { origin: 'http://127.0.0.1:1' };
"""

NOT_IN_FRAME_CHECKS = r"""
toMary('close');
assert.strictEqual(sent, 0);
assert.strictEqual(listeners, 0);
console.log('OK alone');
"""


@unittest.skipUnless(NODE, "Node not found")
class NodeTests(unittest.TestCase):
    def check(self, code, word):
        rc, out, both = run_node(code)
        self.assertEqual(rc, 0, both[-1800:])
        self.assertTrue(out.startswith("OK " + word), both[-500:])

    def test_her_side_of_the_frame(self):
        self.check("\n".join([PARENT_STUBS, deep_block(), PARENT_CHECKS]), "parent")

    def test_the_forms_mic_holds_the_wake_word(self):
        src = read("mary/app.js")
        code = "\n".join([between(src, "function wakeWhyNot(ev)", "// M17: a wake nobody answered"),
                          between(src, "function wakeBusy()", "// M17: nothing may leave her asleep"), WAKE_CHECKS])
        self.check(code, "wake")

    def test_the_forms_side_of_the_frame(self):
        self.check("\n".join([FRAME_STUBS, frame_block(), FRAME_CHECKS]), "frame")

    def test_the_log_alone_in_a_window_sends_nothing(self):
        self.check("\n".join([NOT_IN_FRAME, frame_block(), NOT_IN_FRAME_CHECKS]), "alone")


if __name__ == "__main__":
    unittest.main()
