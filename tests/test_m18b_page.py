from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M18b piece 2, the page's side of a screen opened by voice in a Normal talk. The server sends {"effect": {"kind":
"screen_call", "data": {id, name, args, order}}} down the stream and waits for the page to POST {id, response} to
/api/mary/screen/result. Node runs the real functions cut out of web/mary/app.js (applyEffect, screenCall, screenEnv and the
Normal turns) against the real screens.js on a fake page. Python reads the text of app.js for where each piece sits."""
import subprocess
import unittest
from pathlib import Path

from tests.test_m18_band import slice_js
from tests.test_m18_frame import read, run_node
from tests.test_m18_screens import HARNESS
from tests.test_story_js import NODE

ROOT = Path(__file__).resolve().parent.parent
APP = read("mary/app.js")

# The real app.js functions, with every outside name they touch given a stub. Each build() is a fresh page and a fresh state.
FRAME = r"""
const fs = require('fs');
const src = fs.readFileSync('web/mary/app.js', 'utf8');
function cut(a, b) {
  const i = src.indexOf(a), j = src.indexOf(b, i);
  assert(i >= 0 && j > i, a);
  return src.slice(i, j);
}
const CODE = cut('function applyEffect(effect, T) {', 'function applySettings(values) {') +
             cut('function screenEnv(c) {', '// On moving screens Live hears');
const REAL = window.MaryScreens;
const settle = () => new Promise(r => setTimeout(r, 30));
function build(over, rows) {
  const S = Object.assign({ screen: 'everyday', convo: null, normalTurns: [], companion: 'mary' }, over || {});
  const posts = [], kept = [], logs = [], removed = [], keep = window.MaryScreens;
  window.MaryScreens = REAL;   // the fake page lists its fields from the real list, whatever a test has put in the slot
  const page = pageOn('add');
  window.MaryScreens = keep;
  const state = { fail: false };
  const api = (method, url, body) => {
    posts.push({ method, url, body: body === undefined ? undefined : JSON.parse(JSON.stringify(body)) });
    if (method === 'GET') { return Promise.resolve(rows || []); }
    if (method === 'DELETE') { removed.push(url); return Promise.resolve({ ok: true }); }
    return state.fail ? Promise.reject(new Error('down')) : Promise.resolve({ ok: true });
  };
  const App = { keepTalk() { kept.push(1); } };
  const names = ['S', 'App', 'api', 'log', 'notEnglish', 'openDeep', 'bandBack', 'deepUp', 'deepOnLog', 'panelOpen', 'menuOpen',
                 'closeMenu', 'openPanel', 'D', 'M', '$'];
  const fn = new Function(...names, CODE + '\nreturn { applyEffect, screenCall, normalHeard, normalTurnsNow, screenEnv };');
  const app = fn(S, App, api, e => logs.push(String((e && e.message) || e)), t => /[^\x00-\x7f]/.test(t), () => true, () => {},
                 () => true, () => true, () => false, () => false, () => {}, () => {}, {}, {},
                 id => (id === 'deepFrame' ? { contentDocument: page } : null));
  return Object.assign(app, { S, posts, kept, logs, removed, page, state,
    results: () => posts.filter(p => p.url === '/api/mary/screen/result') });
}
const fakeScreens = (run) => ({ seen: [], run(name, args, env) { this.seen.push({ name, args, order: env.order, turns: env.turns }); return run(name, args, env); },
  noContent: t => /^\W*(yes|um)?\W*$/i.test(t) });
const ORDER = { acts: ['remove'], words: 'remove that note' };
const CALL = (data) => ({ kind: 'screen_call', data });
"""


def node(body):
    code = HARNESS + read("mary/screens.js") + FRAME + "\n(async function () {\n" + body + \
        "\nconsole.log('ok');\n})().catch(function (e) { console.error(e); process.exit(1); });"
    return run_node(code)


class ScreenCall(unittest.TestCase):
    def test_it_runs_the_screen_with_the_servers_order_and_posts_the_answer(self):
        rc, _, err = node(r"""
          const fake = fakeScreens(() => Promise.resolve({ ok: true, screen: 'Notes' }));
          window.MaryScreens = fake;
          const convo = { live: false, formAt: 0 }, a = build({ convo }), T = {};
          a.applyEffect(CALL({ id: 'c1', name: 'use_screen', args: { action: 'open', name: 'notes' }, order: ORDER }), T);
          assert.strictEqual(T.effects, undefined);   // a screen is not a skill: finishReply must not think one ran
          await settle();
          assert.strictEqual(fake.seen.length, 1);
          assert.strictEqual(fake.seen[0].name, 'use_screen');
          assert.deepStrictEqual(fake.seen[0].args, { action: 'open', name: 'notes' });
          assert.deepStrictEqual(fake.seen[0].order, ORDER);
          const r = a.results();
          assert.strictEqual(r.length, 1);
          assert.strictEqual(r[0].method, 'POST');
          assert.deepStrictEqual(r[0].body, { id: 'c1', response: { ok: true, screen: 'Notes' } });
          assert(convo.formAt > 0 && a.kept.length >= 1);   // the talk is held open, as a form's hands at work are
          a.applyEffect({ kind: 'set_value', data: {} }, T);   // a real skill effect is still counted
          assert.strictEqual(T.effects, 1);
          window.MaryScreens = REAL;
        """)
        self.assertEqual(rc, 0, err)

    def test_the_order_is_the_servers_and_never_the_models(self):
        rc, _, err = node(r"""
          const fake = fakeScreens(() => Promise.resolve({ ok: true }));
          window.MaryScreens = fake;
          const a = build();
          const sly = { action: 'remove', when: 'latest', order: ORDER, acts: ['remove'], words: 'remove that note' };
          await a.screenCall({ id: 'c2', name: 'use_screen', args: sly });
          assert.strictEqual(fake.seen[0].order, null);   // no order from the server, so none
          await a.screenCall({ id: 'c3', name: 'use_screen', args: sly, order: { acts: [], words: 'hello' } });
          assert.deepStrictEqual(fake.seen[1].order, { acts: [], words: 'hello' });   // only what the server sent
          // and through the real screens.js: her args can't buy a removal
          window.MaryScreens = REAL;
          const rows = [{ id: 5, occurred_date: '2026-11-01', category: 'meals', description: 'Cold dinner.' }];
          const b = build({}, rows);
          await b.screenCall({ id: 'c4', name: 'use_screen', args: sly });
          assert.deepStrictEqual(b.removed, []);
          assert.strictEqual(b.results()[0].body.response.ok, false);
        """)
        self.assertEqual(rc, 0, err)

    def test_a_run_that_fails_still_answers(self):
        rc, _, err = node(r"""
          window.MaryScreens = fakeScreens(() => Promise.reject(new Error('the box held 919-555-0142')));
          const a = build();
          a.applyEffect(CALL({ id: 'c5', name: 'use_screen', args: { action: 'look' }, order: null }), {});
          await settle();
          assert.deepStrictEqual(a.results().map(p => p.body), [{ id: 'c5', response: { ok: false } }]);
          assert(!JSON.stringify(a.posts).includes('919-555'));   // the error text never goes anywhere
          window.MaryScreens = fakeScreens(() => { throw new Error('sync'); });   // a throw on the way in too
          const b = build();
          await b.screenCall({ id: 'c6', name: 'use_screen', args: {} });
          assert.deepStrictEqual(b.results().map(p => p.body), [{ id: 'c6', response: { ok: false } }]);
          window.MaryScreens = fakeScreens(() => Promise.resolve('not an object'));   // an answer that isn't one
          const c = build();
          await c.screenCall({ id: 'c7', name: 'use_screen', args: {} });
          assert.deepStrictEqual(c.results().map(p => p.body), [{ id: 'c7', response: { ok: false } }]);
          window.MaryScreens = undefined;   // screens.js missing
          const d = build();
          await d.screenCall({ id: 'c8', name: 'use_screen', args: {} });
          assert.deepStrictEqual(d.results().map(p => p.body), [{ id: 'c8', response: { ok: false } }]);
          window.MaryScreens = fakeScreens(() => Promise.resolve({ ok: true }));
          const e = build();
          e.state.fail = true;   // the answer can't be posted: nothing is thrown, the talk goes on
          await e.screenCall({ id: 'c9', name: 'use_screen', args: {} });
          assert.strictEqual(e.logs.length, 1);
          await e.screenCall({ id: '', name: 'use_screen', args: {} });   // no id: nobody is waiting
          await e.screenCall(null);
          assert.strictEqual(e.results().length, 1);
          window.MaryScreens = REAL;
        """)
        self.assertEqual(rc, 0, err)

    def test_nothing_runs_over_an_emergency(self):
        rc, _, err = node(r"""
          const fake = fakeScreens(() => Promise.resolve({ ok: true }));
          window.MaryScreens = fake;
          const convo = { live: false, formAt: 0 }, a = build({ screen: 'emergency', convo });
          a.applyEffect(CALL({ id: 'c10', name: 'use_screen', args: { action: 'open', name: 'notes' }, order: ORDER }), {});
          await settle();
          assert.strictEqual(fake.seen.length, 0);
          assert.deepStrictEqual(a.results().map(p => p.body), [{ id: 'c10', response: { ok: false } }]);
          assert.strictEqual(convo.formAt, 0);
          assert.strictEqual(a.kept.length, 0);
          window.MaryScreens = REAL;
        """)
        self.assertEqual(rc, 0, err)


class NormalTurns(unittest.TestCase):
    def test_their_words_reads_what_normal_heard(self):
        rc, _, err = node(r"""
          window.MaryScreens = REAL;
          const a = build();
          a.normalHeard('The aide said you can wait, and I waited two hours.');
          a.normalHeard('Put that in the box.');
          assert.deepStrictEqual(a.S.normalTurns.map(t => t.bad), [false, false]);
          let r = await REAL.run('use_screen', { action: 'their_words', turns_back: 0 }, a.screenEnv(null));
          assert.strictEqual(r.ok, true);   // 0: the line just said
          assert.strictEqual(a.page.byId.words.value, 'Put that in the box.');
          a.page.byId.words.value = '';
          a.applyEffect(CALL({ id: 'c11', name: 'use_screen', args: { action: 'their_words', turns_back: 1 }, order: null }), {});
          await settle();
          assert.strictEqual(a.page.byId.words.value, 'The aide said you can wait, and I waited two hours.');
          assert.strictEqual(a.results()[0].body.response.ok, true);
          // a bare "yes" or a foreign line is never offered, and is not the turn that asks
          const b = build();
          b.normalHeard('Nobody came when I rang.');
          b.normalHeard('我不知道');
          b.normalHeard('Yes.');
          assert.deepStrictEqual(b.S.normalTurns.map(t => t.bad), [false, true, true]);
          await REAL.run('use_screen', { action: 'their_words', turns_back: 1 }, b.screenEnv(null));
          assert.strictEqual(b.page.byId.words.value, 'Nobody came when I rang.');
        """)
        self.assertEqual(rc, 0, err)

    def test_the_list_is_capped_old_lines_drop_out_and_live_keeps_its_own(self):
        rc, _, err = node(r"""
          window.MaryScreens = REAL;
          const a = build();
          for (let i = 0; i < 15; i++) { a.normalHeard('line number ' + i); }
          assert.strictEqual(a.S.normalTurns.length, 12);
          assert.strictEqual(a.S.normalTurns[11].text, 'line number 14');
          assert.strictEqual(a.S.normalTurns[0].text, 'line number 3');
          a.S.normalTurns[0].at -= 11 * 60 * 1000;   // a typed ask from a while ago, with no talk to end
          assert.strictEqual(a.normalTurnsNow().length, 11);
          assert.strictEqual(a.normalTurnsNow()[0].text, 'line number 4');
          assert.strictEqual(a.screenEnv(null).turns.length, 11);
          assert.strictEqual(a.screenEnv({ live: false }).turns.length, 11);
          const live = [{ text: 'Live line.', bad: false }];
          assert.strictEqual(a.screenEnv({ live: true, turns: live }).turns, live);   // Live's own c.turns, as before
          assert.deepStrictEqual(a.screenEnv({ live: true }).turns, []);
        """)
        self.assertEqual(rc, 0, err)


class WhereItSits(unittest.TestCase):
    def test_the_screen_call_is_handled_before_a_skill_effect_is_counted(self):
        body = slice_js(APP, "function applyEffect(effect, T) {", "function skillScreen() {")
        self.assertIn("effect.kind === 'screen_call'", body)
        self.assertLess(body.index("effect.kind === 'screen_call'"), body.index("T.effects = (T.effects || 0) + 1;"))
        self.assertLess(body.index("return;"), body.index("MarySkills.apply"))

    def test_the_answer_goes_back_by_the_pages_own_api_helper(self):
        body = slice_js(APP, "function screenCall(data) {", "var NORMAL_TURNS_MS")
        self.assertIn("api('POST', '/api/mary/screen/result'", body)
        self.assertIn("env.order = data.order || null;", body)
        self.assertNotIn("args.order", body)
        self.assertIn("S.screen === 'emergency'", body)
        self.assertIn("c.formAt = Date.now()", body)
        self.assertIn("App.keepTalk()", body)
        for banned in ("show(", "screenLine(", "tell(", "setCaption", "showCaption", "spAdd", "localStorage", "console."):
            self.assertNotIn(banned, body, banned)   # what a box holds goes to the model only

    def test_normal_turns_are_kept_before_the_request_and_cleared_when_the_talk_ends(self):
        talk = slice_js(APP, "async function talkTo(text, typed) {", "// ---------------------------------------------------------------- M4b: the one Menu button")
        self.assertLess(talk.index("normalHeard(text);"), talk.index("streamReply(text, T, ctrl)"))
        close = slice_js(APP, "function closeConvo(c) {", "// Ends the conversation.")
        self.assertIn("S.normalTurns = [];", close)
        turn = slice_js(APP, "function normalHeard(text) {", "function normalTurnsNow()")
        self.assertIn("notEnglish(text) || !!(window.MaryScreens && window.MaryScreens.noContent(text))", turn)
        self.assertIn(".slice(-12)", turn)
        env = slice_js(APP, "function screenEnv(c) {", "// On moving screens Live hears")
        self.assertIn("turns: (c && c.live) ? (c.turns || []) : normalTurnsNow()", env)

    @unittest.skipUnless(NODE, "Node not found")
    def test_app_js_still_parses(self):
        run = subprocess.run([NODE, "--check", str(ROOT / "web" / "mary" / "app.js")], capture_output=True, text=True,
                             encoding="utf-8", timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
