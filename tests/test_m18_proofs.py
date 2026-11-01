from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M18 proofs, gap fillers: walks EVERY screen in web/mary/screens.js's list (deep screens and panels) for proofs 1, 2 and 5.
Proofs 3 (addresses) and 4 (the save gate) are covered whole by test_m18_addresses.py and test_m18_save.py."""
import json
import re
import unittest

from tests.test_m18_frame import PARENT_STUBS, deep_block, read, run_node
from tests.test_m18_screens import node as screens_node
from tests.test_story_js import between

PANEL_END = "// ---------------------------------------------------------------- M18: the deep view"


def listed():
    rc, out, err = run_node("globalThis.window = globalThis;\n" + read("mary/screens.js") +
                            "\nconsole.log(JSON.stringify(MaryScreens.LIST.map(function (s) { return { id: s.id, hash: s.hash || '', panel: s.panel || '' }; })));")
    assert rc == 0, err
    return json.loads(out.strip().splitlines()[-1])


SCREENS = listed()
DEEP = [s for s in SCREENS if not s["panel"]]
PANELS = [s for s in SCREENS if s["panel"]]

PANEL_STUBS = r"""
const assert = require('assert');
var S = { convo: null, phase: 'idle', screen: 'everyday', hasKey: true, firstRun: false, formMic: false };
var M = { panel: null, over: undefined, timer: 0 }, Band = { snap: true }, calls = [], els = {};
var BAND_FADE_MS = 300, PANEL_IDLE_MS = 1;
function $(id) { return els[id] = els[id] || { id: id, hidden: true, scrollTop: 0, classList: { add() {}, remove() {} }, focus() {},
  querySelector() { return { setAttribute() {} }; } }; }
function skillScreen() { return undefined; }
function refreshLabels() {} function fillCan() {} function fillInfo() {} function fillGames() {} function fillChoose() {}
function armIdle() {} function stopSample() {} function bandSync() { calls.push('bandSync'); }
function closeConvo() { calls.push('closeConvo'); } function stopLive() { calls.push('stopLive'); }
function wakeStop() { calls.push('wakeStop'); } function spCancel() { calls.push('spCancel'); }
var window = { addEventListener() { throw new Error('a handler was added'); } };
"""

WAKE_STUBS = r"""
var W = { polling: true, held: false, gen: 0, heardTimer: 0, lastEv: 0, holdAt: 0 }, started = 0;
var WAKE_SAY = 'x', WAKE_HELLO = 'x', WAKE_HEARD_MS = 1;
function noteBusyNow() { return false; } function closeTyping() {} function faceAct() {}
var face = { setActivity() {} };
function startTalk() { started++; return Promise.resolve(true); }
"""


def panel_code():
    return between(read("mary/app.js"), "function openPanel(id) {", PANEL_END)


def wake_chunk():
    src = read("mary/app.js")
    return between(src, "function wakeWhyNot(ev)", "// Busy = a talk is open") + between(src, "function wakeBusy()", "// M17: nothing may leave her asleep")


class Base(unittest.TestCase):
    def go(self, code):
        rc, _, both = run_node(code)
        self.assertEqual(rc, 0, both[-1800:])


# Proof 1: a talk survives opening and closing every deeper screen.
class TalkSurvivesEveryScreen(Base):
    def test_the_list_is_not_a_sample(self):
        self.assertGreaterEqual(len(DEEP), 8)
        self.assertEqual(len(PANELS), 4)

    def test_every_deep_screen_opens_and_closes_around_a_live_talk(self):
        self.go(PARENT_STUBS + r"""
function closeConvo() { calls.push('closeConvo'); } function stopLive() { calls.push('stopLive'); }
function wakeStop() { calls.push('wakeStop'); } function spCancel() { calls.push('spCancel'); }
window.addEventListener = function () { throw new Error('a pagehide or other handler was added'); };
""" + deep_block() + r"""
(async function () {
  const screens = %s;
  var talk = { live: true, ending: false, story: null, lastAct: 1, lastLife: 1 }; S.convo = talk;
  for (const s of screens) {
    calls.length = 0;
    assert.strictEqual(openDeep(s.hash), true, s.id);
    assert.ok(up(), s.id + ' is showing');
    assert.strictEqual(S.convo, talk, s.id + ': same talk');
    closeDeep();
    assert.ok(!up(), s.id + ' is closed');
    await Promise.resolve(); await Promise.resolve();
    assert.strictEqual(S.convo, talk, s.id + ': same talk after');
    assert.strictEqual(S.phase, 'idle');
    assert.ok(talk.live && !talk.ending, s.id + ': Live still open');
    ['closeConvo', 'stopLive', 'wakeStop', 'spCancel'].forEach(function (c) { assert.ok(calls.indexOf(c) < 0, s.id + ' called ' + c); });
  }
})().catch(function (e) { console.error(e); process.exit(1); });
""" % json.dumps(DEEP))

    def test_every_panel_opens_and_closes_around_a_live_talk(self):
        self.go(PANEL_STUBS + panel_code() + r"""
const panels = %s;
var talk = { live: true, ending: false, lastAct: 1 }; S.convo = talk;
for (const s of panels) {
  calls.length = 0;
  openPanel(s.panel);
  assert.strictEqual(M.panel, s.panel, s.id);
  assert.strictEqual(S.convo, talk, s.id);
  closePanel(false);
  assert.strictEqual(M.panel, null, s.id);
  assert.strictEqual(S.convo, talk, s.id + ': same talk after');
  assert.ok(talk.live && !talk.ending);
  ['closeConvo', 'stopLive', 'wakeStop', 'spCancel'].forEach(function (c) { assert.ok(calls.indexOf(c) < 0, s.id + ' called ' + c); });
}
""" % json.dumps(PANELS))

    def test_opening_and_closing_touch_no_talk_or_page_code(self):
        bodies = deep_block() + panel_code()
        for bad in (r"closeConvo", r"stopLive", r"finishLive", r"wakeStop", r"spCancel", r"addEventListener",
                    r"location\.(reload|href|assign)"):
            self.assertIsNone(re.search(bad, bodies), bad)
        self.assertEqual(len(re.findall(r"'pagehide'", read("mary/app.js"))), 1)  # the one real page leaving


# Proof 2: secret fields never reach Gemini or a log.
class SecretsGoNowhere(unittest.TestCase):
    def test_every_password_box_in_the_page_is_a_listed_secret_and_leaks_nowhere(self):
        html = read("index.html")
        ids = re.findall(r'<input\b[^>]*type="password"[^>]*\bid="([^"]+)"', html) + \
            re.findall(r'<input\b[^>]*\bid="([^"]+)"[^>]*type="password"', html)
        self.assertGreaterEqual(len(ids), 2)
        rc, _, err = screens_node(r"""
          const ids = %s;
          const secrets = MaryScreens.LIST.reduce((a, s) => a.concat((s.fields || []).filter(f => f.kind === 'secret')), []);
          assert.deepStrictEqual(secrets.map(f => f.id).sort(), ids.slice().sort());
          for (const id of ids) {
            const page = pageOn('info');
            page.byId[id].value = 'FAKE-' + id + '-VALUE';
            for (const [tool, args] of [['look_at_screen', {}], ['explain_field', { field: id }], ['fill_field', { field: id, value: 'x' }],
                                        ['put_back', {}], ['their_words', {}]]) {
              const r = await run(tool, args, envOn(page, { turns: [{ text: 'my words', bad: false }] }));
              assert(!JSON.stringify(r).includes('FAKE-'), id + ' ' + tool + ' leaked');
            }
            assert.strictEqual(page.byId[id].value, 'FAKE-' + id + '-VALUE', id + ' was touched');
            const card = (await run('look_at_screen', {}, envOn(page))).fields.find(f => f.field === id);
            assert.deepStrictEqual(Object.keys(card).sort(), ['field', 'kind', 'label']);
            assert.strictEqual(card.kind, 'secret');
            const fill = await run('fill_field', { field: id, value: 'x' }, envOn(page));
            assert.strictEqual(fill.ok, false);
          }
        """ % json.dumps(ids))
        self.assertEqual(rc, 0, err)

    def test_nothing_in_screens_js_can_log_send_or_store(self):
        js = read("mary/screens.js")
        for bad in (r"console\.", r"\blog\(", r"\bfetch\(", r"\bapi\(", r"sendBeacon", r"XMLHttpRequest", r"postMessage",
                    r"localStorage", r"sessionStorage", r"indexedDB"):
            self.assertIsNone(re.search(bad, js), bad)

    def test_her_page_never_logs_a_screen_tool_result(self):
        js = read("mary/app.js")
        start = js.index("MaryScreens.run(fc.name")
        block = js[start:start + 900]
        self.assertNotRegex(block, r"\blog\(\s*res|console\.")

    def test_the_forms_paste_posts_no_message(self):
        js = read("app.js")
        paste = js[js.index("async function readClipboard"):js.index("$('#infoForm').addEventListener('keydown'")]
        self.assertNotRegex(paste, r"postMessage|toMary|fetch\(|api\(|console\.")


# Proof 5: the wake word still works on every screen.
class WakeWordOnEveryScreen(Base):
    def test_every_deep_screen_leaves_her_free_to_wake_and_a_wake_starts_a_talk_there(self):
        self.go(PARENT_STUBS + WAKE_STUBS + r"""
els.typing = { hidden: true };
""" + deep_block() + wake_chunk() + r"""
(async function () {
  const screens = %s;
  var seq = 0;
  for (const s of screens) {
    openDeep(s.hash); calls.length = 0; started = 0;
    assert.strictEqual(wakeWhyNot({}), '', s.id);
    assert.strictEqual(wakeBusy(), false, s.id);
    onWakeEvent({ type: 'wake', seq: ++seq });
    await Promise.resolve();
    assert.strictEqual(started, 1, s.id + ': a talk started');
    assert.ok(up(), s.id + ': the deep view is left open');
    assert.ok(calls.indexOf('closePanel') < 0, s.id + ': nothing closed');
    closeDeep();
  }
})().catch(function (e) { console.error(e); process.exit(1); });
""" % json.dumps(DEEP))

    def test_every_panel_leaves_her_free_to_wake_and_a_wake_leaves_it_open(self):
        self.go(PANEL_STUBS + WAKE_STUBS + r"""
els.typing = { hidden: true };
function menuOpen() { return false; } function closeMenu() {} function api() { return Promise.resolve({}); }
""" + panel_code() + wake_chunk() + r"""
(async function () {
  const panels = %s;
  var seq = 0;
  for (const s of panels) {
    openPanel(s.panel); started = 0;
    assert.strictEqual(wakeWhyNot({}), '', s.id);
    onWakeEvent({ type: 'wake', seq: ++seq });
    await Promise.resolve();
    assert.strictEqual(started, 1, s.id + ': a talk started');
    assert.strictEqual(M.panel, s.panel, s.id + ': the panel is left open');
    closePanel(false);
  }
})().catch(function (e) { console.error(e); process.exit(1); });
""" % json.dumps(PANELS))

    def test_the_poll_keeps_running_when_a_talk_ends_with_a_deep_view_open(self):
        self.go(PARENT_STUBS + WAKE_STUBS + r"""
function wakeSchedule() {} function wakeStop() { throw new Error('the poll was stopped'); }
S.wakeWord = true; S.wakeReady = true;
""" + deep_block() + between(read("mary/app.js"), "function wakeWanted()", "function wakeStop()") +
                 between(read("mary/app.js"), "function wakeBusy()", "// M17: nothing may leave her asleep") + r"""
(async function () {
  const screens = %s;
  S.convo = { live: true };
  for (const s of screens) {
    openDeep(s.hash);
    S.convo = null;                 // the talk ends with the deep view open
    assert.strictEqual(wakeBusy(), false, s.id + ': not held by the screen');
    wakeSync();
    assert.strictEqual(W.polling, true, s.id + ': still polling');
    assert.strictEqual(W.gen, 0);
    closeDeep();
    S.convo = { live: true };
  }
})().catch(function (e) { console.error(e); process.exit(1); });
""" % json.dumps(DEEP))

    def test_no_screen_code_stops_the_poll(self):
        self.assertNotRegex(deep_block() + panel_code(), r"wakeStop|W\.polling|W\.gone")


if __name__ == "__main__":
    unittest.main()
