from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M18 piece 3a, what Gemini sees of a screen and the tools to open, explain and fill: static checks on the hand-written
list against web/index.html, plus Node with a fake page for the rules that must hold in code (web/mary/screens.js)."""
import json
import re
import unittest
from pathlib import Path

import mary
from tests.test_m18_band import slice_js
from tests.test_m18_frame import read, run_node

ROOT = Path(__file__).resolve().parent.parent

# Loads screens.js, and builds a fake page with every listed field on it.
HARNESS = r"""
globalThis.window = globalThis;
const assert = require('assert');
const STILL = { on: true };
function mk(id, o) {
  return Object.assign({ id: id, type: 'text', tagName: 'INPUT', value: '', hidden: false, parentElement: null, checked: false,
    events: [], seen: [],
    classList: { s: {}, add(c) { this.s[c] = 1; }, remove(c) { delete this.s[c]; }, has(c) { return !!this.s[c]; } },
    getBoundingClientRect() { return { top: 100, bottom: 140 }; },
    dispatchEvent(ev) { this.events.push(ev.type); if (ev.type === 'input') { this.seen.push(this.value); } return true; }
  }, o || {});
}
function pageOn(frame) {
  const byId = {}, groups = {};
  ['home', 'add', 'saved', 'list', 'inbox', 'report', 'info'].forEach(f => { byId[f] = mk(f, { hidden: f !== frame }); });
  MaryScreens.LIST.forEach(s => (s.fields || []).forEach(f => {
    if (f.radio) { groups[f.radio] = f.choices.map(c => mk('', { type: 'radio', value: c.value })); return; }
    byId[f.id] = mk(f.id, { type: { secret: 'password', 'switch': 'checkbox', date: 'date', time: 'time' }[f.kind] || 'text',
      tagName: f.kind === 'words' ? 'TEXTAREA' : 'INPUT' });
  }));
  const win = { Event: function (t) { this.type = t; }, innerHeight: 800, scrolled: [], scrollBy(o) { this.scrolled.push(o); },
    matchMedia() { return { matches: STILL.on }; } };
  return { defaultView: win, byId, groups,
    getElementById(id) { return byId[id] || null; },
    querySelector() { return null; },
    querySelectorAll(sel) { const m = /name="([^"]+)"/.exec(sel); return m ? (groups[m[1]] || []) : []; } };
}
function envOn(doc, more) {
  return Object.assign({ doc() { return doc; }, panel() { return null; }, openDeep() { return true; }, openPanel() {}, back() {}, turns: [] }, more || {});
}
const run = (name, args, env) => MaryScreens.run(name, args, env);
"""


def node(body):
    code = HARNESS + read("mary/screens.js") + "\n(async function () {\n" + body + "\nconsole.log('ok');\n})().catch(function (e) { console.error(e); process.exit(1); });"
    rc, out, err = run_node(code)
    return rc, out, err


class Listed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rc, out, err = run_node(HARNESS + read("mary/screens.js") + "\nconsole.log(JSON.stringify({l: MaryScreens.LIST, g: MaryScreens.GROUPS, t: MaryScreens.TOOL_NAMES}));")
        assert rc == 0, err
        got = json.loads(out)
        cls.list, cls.groups, cls.tools = got["l"], got["g"], got["t"]
        cls.fields = [f for s in cls.list for f in s["fields"]]
        cls.html = read("index.html")

    def test_every_listed_id_exists_in_the_page(self):
        for f in self.fields:
            if "radio" in f:
                self.assertIn('name="%s"' % f["radio"], self.html, f["id"])
                for c in f["choices"]:
                    self.assertIn('name="%s" value="%s"' % (f["radio"], c["value"]), self.html, c)
            else:
                self.assertIn('id="%s"' % f["id"], self.html, f["id"])
        for s in self.list:
            if s.get("frame"):
                self.assertIn('id="%s" class="screen' % s["frame"], self.html)
            if s.get("scroll"):
                self.assertIn('id="%s"' % s["scroll"], self.html)

    def test_every_section_and_panel_is_a_listed_screen(self):
        for sec in re.findall(r'<section id="(\w+)" class="screen', self.html):
            self.assertIn(sec, [s.get("frame") for s in self.list])
        page = read("mary.html")
        for panel in re.findall(r'<div id="(\w+Panel)" class="overlay', page):
            self.assertIn(panel, [s.get("panel") for s in self.list])

    def test_a_password_box_is_never_fillable_and_has_no_value_path(self):
        boxes = re.findall(r'<input\b[^>]*type="password"[^>]*>', self.html)
        self.assertEqual(len(boxes), 2)
        for box in boxes:
            bid = re.search(r'id="([^"]+)"', box).group(1)
            hits = [f for f in self.fields if f["id"] == bid]
            for f in hits:
                self.assertEqual(f["kind"], "secret")
                self.assertFalse(f["fill"])
        self.assertTrue(all(not f["fill"] for f in self.fields if f["kind"] == "secret"))
        self.assertEqual({f["id"] for f in self.fields if f["kind"] == "secret"}, {"i-gemini_key", "copyWords", "mailPass"})

    def test_fields_nobody_decided_on_stay_out(self):
        ids = [f["id"] for f in self.fields]
        self.assertNotIn("i-gemini_model", ids)
        for f in self.fields:
            self.assertNotRegex(f["id"], r"(?i)delete|remove|disconnect|clear")

    def test_only_what_the_brief_allows_can_be_filled(self):
        self.assertEqual({f["id"] for f in self.fields if f["fill"]}, {
            "when", "day", "time", "wait", "staff_involved", "reported_to", "outcome", "witnesses", "repFrom", "repTo",
            "i-resident_name", "i-room", "i-facility", "i-facility_address", "i-state", "mailAddress", "mail_provider",
            *("bf-" + name for name in ("name", "relationship", "email", "phone", "cell", "address", "facebook", "birthday", "notes"))})  # M19 piece 6b
        self.assertEqual({f["id"] for f in self.fields if f["kind"] == "switch"}, {
            "i-gemini_enabled", "i-andyflow_enabled", "i-wake_word", "i-talk_on_open", "mailConnect"})

    def test_list_and_report_and_inbox_show_no_records(self):
        for sid in ("list", "inbox"):
            self.assertEqual([s for s in self.list if s["id"] == sid][0]["fields"], [])

    def test_the_nine_groups_match_the_log(self):
        app = read("app.js")
        got = re.findall(r"\{ key: '(\w+)', color: '[^']+', emoji: '[^']+', tile: (?:'([^']+)'|\"([^\"]+)\")", app)
        self.assertEqual([(k, a or b) for k, a, b in got], [(g["key"], g["label"]) for g in self.groups])

    def test_open_screen_names_match_the_list(self):
        names = [s["id"] for s in self.list if s.get("hash") or s.get("panel")] + ["write_" + g["key"] for g in self.groups]
        self.assertEqual(sorted(mary.LIVE_SCREEN_NAMES), sorted(names))

    def test_the_tools_declared_are_the_tools_answered(self):
        declared = {d["name"]: d for d in mary.LIVE_PAGE_TOOLS}
        self.assertEqual(set(declared) - {"story_more", "end_talk"}, {"use_screen"})   # one screen tool, not seven
        props = declared["use_screen"]["parameters"]["properties"]
        self.assertEqual(set(props), {"action", "name", "who", "field", "value", "turns_back", "when", "category"})   # piece 5: when, category; M19 piece 6b: who
        self.assertTrue(all(p["type"] == "string" for p in props.values()))
        for name in self.tools:   # every action named in the description reaches one of the seven functions
            self.assertIn(name, self.tools)
        for action in ("look", "open", "explain", "fill", "put_back", "their_words", "go_back"):
            self.assertIn(action, declared["use_screen"]["description"])
        for n in mary.LIVE_SCREEN_NAMES:
            self.assertIn(n, props["name"]["description"])
        self.assertFalse([n for n in declared if "save" in n or "send" in n or "delete" in n])
        self.assertNotIn("text", declared["use_screen"]["parameters"]["properties"])   # no text, ever
        self.assertEqual(declared["use_screen"]["parameters"]["required"], ["action"])

    def test_it_loads_before_her_page_code(self):
        page = read("mary.html")
        self.assertLess(page.index("/mary/screens.js"), page.index("/mary/app.js"))

    def test_nothing_is_logged_or_sent(self):
        js = read("mary/screens.js")
        for bad in (r"console\.", r"\blog\(", r"\bfetch\(", r"\bapi\(", r"XMLHttpRequest", r"postMessage", r"localStorage"):
            self.assertIsNone(re.search(bad, js), bad)
        self.assertNotIn(".focus(", js)   # a tool never takes focus away from where they're typing

    def test_the_light_matches_the_board(self):
        self.assertIn(".m9-lit{background:#fff1c7!important;box-shadow:inset 0 0 0 5px #f2b632,0 0 0 3px #2b1f17!important}",
                      read("styles.css"))


class Card(unittest.TestCase):
    def test_a_secret_shows_label_and_kind_and_nothing_else(self):
        rc, _, err = node(r"""
          const filled = pageOn('info'), empty = pageOn('info');
          filled.byId['i-gemini_key'].value = 'AIzaHUNTER2';
          filled.byId['mailPass'].value = 'hunter2hunter2';
          filled.byId['i-room'].value = '214';
          const a = await run('look_at_screen', {}, envOn(filled)), b = await run('look_at_screen', {}, envOn(empty));
          const text = JSON.stringify(a);
          assert(!text.includes('HUNTER2') && !text.includes('hunter2'));
          assert.deepStrictEqual(a.fields.filter(f => f.kind === 'secret'), b.fields.filter(f => f.kind === 'secret'));
          assert.deepStrictEqual(a.fields.filter(f => f.kind === 'secret'), [
            { field: 'i-gemini_key', label: 'Smart helper key', kind: 'secret' }, { field: 'copyWords', label: 'The six words', kind: 'secret' }, { field: 'mailPass', label: 'App password', kind: 'secret' }]);
          assert.strictEqual(a.screen, 'My info');
          assert.strictEqual(a.fields.find(f => f.field === 'i-room').value, '214');
        """)
        self.assertEqual(rc, 0, err)

    def test_a_wrong_list_entry_changes_nothing(self):
        rc, _, err = node(r"""
          const f = MaryScreens.LIST.find(s => s.id === 'info').fields.find(x => x.id === 'i-gemini_key');
          f.kind = 'text'; f.fill = true;   // someone got the list wrong
          const page = pageOn('info');
          const el = page.byId['i-gemini_key'];
          el.type = 'password'; el.value = 'AIzaHUNTER2';
          const env = envOn(page), card = await run('look_at_screen', {}, env);
          assert(!JSON.stringify(card).includes('HUNTER2'));
          assert.deepStrictEqual(card.fields.find(x => x.field === 'i-gemini_key'), { field: 'i-gemini_key', label: 'Smart helper key', kind: 'secret' });
          const r = await run('fill_field', { field: 'i-gemini_key', value: 'x' }, env);
          assert.strictEqual(r.ok, false);
          assert(r.say.startsWith("I won't read or fill that one."));
          assert.strictEqual(el.value, 'AIzaHUNTER2');
          assert.strictEqual((await run('put_back', { field: 'i-gemini_key' }, env)).ok, false);
        """)
        self.assertEqual(rc, 0, err)

    def test_a_box_not_showing_stays_out_and_a_secret_stays_the_same(self):
        rc, _, err = node(r"""
          const page = pageOn('info');
          page.byId['mailAddress'].parentElement = { hidden: true };   // email is already connected
          page.byId['mailPass'].parentElement = { hidden: true };
          const card = await run('look_at_screen', {}, envOn(page));
          assert(!card.fields.find(f => f.field === 'mailAddress'));
          assert(card.fields.find(f => f.field === 'mailPass'));
          assert.strictEqual((await run('fill_field', { field: 'mailAddress', value: 'a@b.c' }, envOn(page))).ok, false);
        """)
        self.assertEqual(rc, 0, err)

    def test_nothing_on_her_own_screen_or_a_panel(self):
        rc, _, err = node(r"""
          assert.deepStrictEqual(Object.keys(await run('look_at_screen', {}, envOn(null))).sort(), ['about', 'screen']);
          const page = pageOn('info');
          const card = await run('look_at_screen', {}, envOn(page, { panel() { return 'gamesPanel'; } }));
          assert.strictEqual(card.screen, 'Games');
          assert(!card.fields);
        """)
        self.assertEqual(rc, 0, err)

    def test_inbox_and_list_are_labels_only(self):
        rc, _, err = node(r"""
          for (const frame of ['inbox', 'list']) {
            const page = pageOn(frame);
            page.byId['inboxList'] = mk('inboxList', { value: 'SECRET ITEM', textContent: 'SECRET ITEM' });
            const text = JSON.stringify(await run('look_at_screen', {}, envOn(page)));
            assert(!text.includes('SECRET ITEM'));
            assert(!text.includes('"fields"'));
          }
        """)
        self.assertEqual(rc, 0, err)


class Fill(unittest.TestCase):
    def test_what_she_cannot_fill(self):
        rc, _, err = node(r"""
          const add = pageOn('add'), info = pageOn('info');
          const cases = [
            [add, 'sev', 'serious', "That one's your call"], [add, 'words', 'she said', 'Your words stay'],
            [info, 'i-gemini_key', 'x', "I won't read or fill that one."], [info, 'mailPass', 'x', "I won't read or fill that one."],
            [info, 'App password', 'x', "I won't read or fill that one."], [info, 'i-gemini_enabled', 'on', 'That switch is yours'],
            [info, 'mailConnect', 'on', 'That switch is yours'], [info, 'i-wake_word', 'off', 'That switch is yours'],
            [info, 'memory remove', 'x', 'Deleting or removing'], [info, 'mailDisconnect', 'x', 'Deleting or removing'],
            [info, 'i-gemini_model', 'x', "That's not something"]];
          for (const [page, field, value, start] of cases) {
            const r = await run('fill_field', { field, value }, envOn(page));
            assert.strictEqual(r.ok, false, field);
            assert(r.say.startsWith(start), field + ': ' + r.say);
          }
          assert.strictEqual(add.groups.sev.filter(r => r.checked).length, 0);
          assert.strictEqual(add.byId.words.value, '');
          assert.strictEqual(info.byId['i-gemini_enabled'].checked, false);
        """)
        self.assertEqual(rc, 0, err)

    def test_only_the_screen_in_front_of_them(self):
        rc, _, err = node(r"""
          assert.strictEqual((await run('fill_field', { field: 'i-room', value: '214' }, envOn(pageOn('add')))).ok, false);
          assert.strictEqual((await run('fill_field', { field: 'i-room', value: '214' }, envOn(null))).ok, false);
        """)
        self.assertEqual(rc, 0, err)

    def test_a_value_arrives_a_letter_at_a_time(self):
        rc, _, err = node(r"""
          STILL.on = false;
          const page = pageOn('info'), el = page.byId['i-room'], env = envOn(page);
          const r = await run('fill_field', { field: 'i-room', value: '214' }, env);
          assert.deepStrictEqual(el.seen.filter(Boolean).slice(0, 3), ['2', '21', '214']);
          assert.strictEqual(el.value, '214');
          assert.strictEqual(el.events.filter(e => e === 'change').length, 1);
          assert(el.classList.has('m9-lit'));
          assert(/Is that right\?/.test(r.next) && /Nothing is saved/.test(r.next) && r.saved === false);
        """)
        self.assertEqual(rc, 0, err)

    def test_reduced_motion_is_at_once_and_the_light_moves(self):
        rc, _, err = node(r"""
          const page = pageOn('info'), env = envOn(page);
          await run('fill_field', { field: 'i-room', value: '214' }, env);
          assert.deepStrictEqual(page.byId['i-room'].seen, ['214']);
          await run('explain_field', { field: 'i-state' }, env);
          assert(!page.byId['i-room'].classList.has('m9-lit'));
          assert(page.byId['i-state'].classList.has('m9-lit'));
        """)
        self.assertEqual(rc, 0, err)

    def test_a_choice_is_picked_by_label_or_value_and_a_bad_one_refused(self):
        rc, _, err = node(r"""
          const page = pageOn('add'), env = envOn(page), wait = page.groups.wait;
          const r = await run('fill_field', { field: 'wait', value: '2+ hours' }, env);
          assert.strictEqual(r.value, '2+ hours');
          assert.strictEqual(wait.find(x => x.checked).value, '120');
          assert(wait.find(x => x.checked).events.includes('change'));
          await run('fill_field', { field: 'wait', value: 'never' }, env);
          assert.strictEqual(wait.find(x => x.checked).value, 'never');
          const bad = await run('fill_field', { field: 'wait', value: 'a fortnight' }, env);
          assert.strictEqual(bad.ok, false);
          assert(/15 min/.test(bad.say));
          assert.strictEqual(wait.find(x => x.checked).value, 'never');
        """)
        self.assertEqual(rc, 0, err)

    def test_bad_dates_and_times_are_refused_plainly(self):
        rc, _, err = node(r"""
          const page = pageOn('add'), env = envOn(page);
          for (const value of ['last Tuesday', '2026-13-01', '2026-02-30', '']) {
            assert.strictEqual((await run('fill_field', { field: 'day', value }, env)).ok, false, value);
          }
          assert(/hasn't come yet/.test((await run('fill_field', { field: 'day', value: '2999-01-01' }, env)).say));
          assert.strictEqual(page.byId.day.value, '');
          assert.strictEqual((await run('fill_field', { field: 'day', value: '2026-10-03' }, env)).ok, true);
          assert.strictEqual(page.byId.day.value, '2026-10-03');
          assert.strictEqual((await run('fill_field', { field: 'time', value: 'noonish' }, env)).ok, false);
          await run('fill_field', { field: 'time', value: '7:30 PM' }, env);
          assert.strictEqual(page.byId.time.value, '19:30');
        """)
        self.assertEqual(rc, 0, err)

    def test_put_back_restores_each_fill(self):
        rc, _, err = node(r"""
          const page = pageOn('info'), env = envOn(page), el = page.byId['i-room'];
          el.value = '101';
          assert.strictEqual((await run('put_back', { field: 'i-room' }, env)).ok, false);
          await run('fill_field', { field: 'i-room', value: '214' }, env);
          await run('fill_field', { field: 'i-room', value: '215' }, env);
          assert.strictEqual((await run('put_back', { field: 'i-room' }, env)).ok, true);
          assert.strictEqual(el.value, '214');
          await run('put_back', { field: 'i-room' }, env);
          assert.strictEqual(el.value, '101');
          assert.strictEqual((await run('put_back', { field: 'i-room' }, env)).ok, false);
          const add = pageOn('add'), e2 = envOn(add);
          await run('fill_field', { field: 'wait', value: '1 hour' }, e2);
          await run('put_back', { field: 'wait' }, e2);
          assert.strictEqual(add.groups.wait.filter(r => r.checked).length, 0);
        """)
        self.assertEqual(rc, 0, err)

    def test_explain_lights_without_touching_and_a_secret_is_named_plainly(self):
        rc, _, err = node(r"""
          const page = pageOn('add'), env = envOn(page);
          const r = await run('explain_field', { field: 'sev' }, env);
          assert(/Dangerous/.test(r.explain));
          assert.strictEqual(page.groups.sev.filter(x => x.checked).length, 0);
          const info = pageOn('info'), el = info.byId.mailPass;
          el.value = 'hunter2';
          const s = await run('explain_field', { field: 'mailPass' }, envOn(info));
          assert.strictEqual(s.kind, 'secret');
          assert(s.say_plainly.startsWith("I won't read or fill that one."));
          assert(!JSON.stringify(s).includes('hunter2'));
        """)
        self.assertEqual(rc, 0, err)


class OpenAndBack(unittest.TestCase):
    def test_only_listed_screens_open(self):
        rc, _, err = node(r"""
          const page = pageOn('home'), hashes = [], panels = [];
          const env = envOn(page, { openDeep(h) { hashes.push(h); page.byId.home.hidden = true; page.byId[h.slice(1).split('/')[0]].hidden = false; return true; },
            openPanel(p) { panels.push(p); } });
          assert.strictEqual((await run('open_screen', { name: 'system settings' }, env)).ok, false);
          assert.strictEqual((await run('open_screen', { name: 'saved' }, env)).ok, false);
          assert.deepStrictEqual(hashes, []);
          assert.strictEqual((await run('open_screen', { name: 'report' }, env)).screen, 'Make a report');
          page.byId.report.hidden = true; page.byId.home.hidden = false;
          assert.strictEqual((await run('open_screen', { name: 'write_meal' }, env)).screen, 'Write something down');
          assert.strictEqual((await run('open_screen', { name: 'games' }, env)).screen, 'Games');
          assert.deepStrictEqual(hashes, ['#report', '#add/meal']);
          assert.deepStrictEqual(panels, ['gamesPanel']);
        """)
        self.assertEqual(rc, 0, err)

    def test_connect_email_scrolls_to_the_mail_card(self):
        rc, _, err = node(r"""
          const page = pageOn('info');
          page.byId.mailCard = mk('mailCard', { getBoundingClientRect() { return { top: 1200, bottom: 1600 }; } });
          const r = await run('open_screen', { name: 'email' }, envOn(page));
          assert.strictEqual(r.screen, 'Connect email');
          assert.strictEqual(page.defaultView.scrolled.length, 1);
        """)
        self.assertEqual(rc, 0, err)

    def test_the_inbox_opens_only_when_the_router_lets_it(self):
        rc, _, err = node(r"""
          const page = pageOn('home');   // the link is off: the log's router stays home
          const orig = Date.now, realTimeout = setTimeout;
          let t = orig();
          Date.now = () => (t += 5000);
          const r = await run('open_screen', { name: 'inbox' }, envOn(page));
          Date.now = orig;
          assert.strictEqual(r.ok, false);
          assert(/isn't switched on/.test(r.say));
        """)
        self.assertEqual(rc, 0, err)

    def test_the_one_tool_reaches_each_action(self):
        rc, _, err = node(r"""
          let backs = 0;
          const page = pageOn('add'), env = envOn(page, { back() { backs++; }, turns: [{ text: 'Nobody came.', bad: false }, { text: 'Put it in.', bad: false }] });
          const U = (args, e) => run('use_screen', args, e || env);
          assert(MaryScreens.isTool('use_screen'));
          assert.strictEqual((await U({ action: 'look' })).screen, 'Write something down');
          assert.strictEqual((await U({ action: 'fill', field: 'staff_involved', value: '214' })).ok, true);
          assert.strictEqual(page.byId['staff_involved'].value, '214');
          assert.strictEqual((await U({ action: 'explain', field: 'reported_to' })).ok, true);
          assert(page.byId['reported_to'].classList.has('m9-lit'));
          assert.strictEqual((await U({ action: 'put_back', field: 'staff_involved' })).ok, true);
          assert.strictEqual(page.byId['staff_involved'].value, '');
          assert.strictEqual((await U({ action: 'their_words', turns_back: '1' })).ok, true);
          assert.strictEqual(page.byId.words.value, 'Nobody came.');
          assert.strictEqual((await U({ action: 'their_words', turns_back: 'lots' })).ok, false);
          assert.strictEqual((await U({ action: 'their_words', turns_back: '9' })).ok, false);
          const home = pageOn('home');
          const env2 = envOn(home, { openDeep(h) { home.byId.home.hidden = true; home.byId[h.slice(1).split('/')[0]].hidden = false; return true; } });
          assert.strictEqual((await U({ action: 'open', name: 'report' }, env2)).screen, 'Make a report');
          assert.strictEqual((await U({ action: 'go_back' }, envOn(null, { back() { backs++; } }))).screen, MaryScreens.TALK_NAME);
          assert.strictEqual(backs, 1);
          assert.strictEqual((await U({ action: 'save' })).ok, false);
          assert.strictEqual((await U({})).ok, false);
          assert.strictEqual((await U({ action: 'constructor' })).ok, false);
        """)
        self.assertEqual(rc, 0, err)

    def test_go_back_is_tapping_her(self):
        rc, _, err = node(r"""
          let backs = 0;
          const r = await run('go_back', {}, envOn(null, { back() { backs++; } }));
          assert.strictEqual(backs, 1);
          assert.strictEqual(r.screen, MaryScreens.TALK_NAME);
        """)
        self.assertEqual(rc, 0, err)


class TheirWords(unittest.TestCase):
    def test_their_own_words_go_in_verbatim_and_she_gives_no_text(self):
        rc, _, err = node(r"""
          const said = "the aide said, quote, you can wait—I waited two hours  and nobody came";
          const page = pageOn('add'), el = page.byId.words;
          const turns = [{ text: said, bad: false }, { text: 'Put that in my words.', bad: false }];
          const env = envOn(page, { turns });
          const r = await run('their_words', { turns_back: 1, text: 'She waited a long time.', value: 'rewritten', field: 'x' }, env);
          assert.strictEqual(r.ok, true);
          assert.strictEqual(el.value, said);
          assert(el.events.includes('input') && el.events.includes('change'));
          assert(!JSON.stringify(r).includes('waited'));   // nothing of it comes back through Gemini
          turns.push({ text: 'And my roommate saw it.', bad: false }, { text: 'Add that too.', bad: false });
          await run('their_words', { turns_back: 1 }, env);
          assert.strictEqual(el.value, said + '\nAnd my roommate saw it.');
          await run('put_back', { field: 'words' }, env);
          assert.strictEqual(el.value, said);
        """)
        self.assertEqual(rc, 0, err)

    def test_the_same_words_are_not_pasted_twice(self):
        rc, _, err = node(r"""
          const page = pageOn('add'), env = envOn(page, { turns: [{ text: 'Nobody came.', bad: false }, { text: 'Put it in.', bad: false }] });
          await run('their_words', { turns_back: 1 }, env);
          await run('their_words', { turns_back: 1 }, env);
          assert.strictEqual(page.byId.words.value, 'Nobody came.');
        """)
        self.assertEqual(rc, 0, err)

    def test_garbled_and_empty_turns_are_not_offered(self):
        rc, _, err = node(r"""
          const T = (text, bad) => ({ text, bad: !!bad });
          const turns = [T('The aide never came.'), T('我不知道', true), T('Yes.', true)];
          assert.strictEqual(MaryScreens.pickHeard(turns, 1), 'The aide never came.');   // a plain yes asked for it
          assert.strictEqual(MaryScreens.pickHeard(turns, 0), 'The aide never came.');
          assert.strictEqual(MaryScreens.pickHeard(turns, 2), null);
          assert.strictEqual(MaryScreens.pickHeard([], 1), null);
          const five = ['one', 'two', 'three', 'four', 'five', 'six', 'ask'].map(t => T(t));
          assert.strictEqual(MaryScreens.pickHeard(five, 0), 'ask');
          assert.strictEqual(MaryScreens.pickHeard(five, 1), 'six');
          assert.strictEqual(MaryScreens.pickHeard(five, 4), 'three');
          assert.strictEqual(MaryScreens.pickHeard(five, 5), null);   // only the last five
          for (const t of ['', 'um', 'Yes.', "Yes, that's right.", 'okay okay', 'Thank you.']) { assert(MaryScreens.noContent(t), t); }
          for (const t of ['No one came.', 'Yes she hit me', 'Put that in']) { assert(!MaryScreens.noContent(t), t); }
        """)
        self.assertEqual(rc, 0, err)

    def test_only_on_the_form(self):
        rc, _, err = node(r"""
          const env = envOn(pageOn('info'), { turns: [{ text: 'Nobody came.', bad: false }, { text: 'Put it in.', bad: false }] });
          assert.strictEqual((await run('their_words', { turns_back: 1 }, env)).ok, false);
        """)
        self.assertEqual(rc, 0, err)

    def test_her_page_keeps_the_turns_and_marks_a_garbled_one(self):
        js = read("mary/app.js")
        body = slice_js(js, "function liveHeard(c, text) {", "function liveEmergency(c, j)")
        self.assertIn("c.turns = (c.turns || []).concat([turn]).slice(-12);", body)
        self.assertLess(body.index("if (j && j.garbled) { turn.bad = true; }"), body.index("if (j && j.emergency)"))


class EmergencyGate(unittest.TestCase):
    def test_an_emergency_turn_refuses_every_screen_tool(self):
        js = read("mary/app.js")
        code = "globalThis.window = globalThis;\nconst assert = require('assert');\n" + r"""
          var S = { screen: 'everyday' }, TOOL_REFUSED = { error: 'emergency' }, ENV = {}, runs = [];
          function log() {} function noteBusyNow() { return false; } function dictating() { return false; } function liveEndTalk() {} function storyTake() { return {}; }
          function storyFromTool(c, r) { return r; } function refreshName() {} function screenEnv() { return ENV; }
          window.MaryScreens = { isTool(n) { return n !== 'recall'; }, run(n, a, e) { runs.push([n, a, e]); return Promise.resolve({ ok: true, n }); } };
          window.MarySkills = { handleLiveToolCall() { return Promise.resolve({ functionResponses: [{ id: 9, name: 'recall', response: {} }] }); } };
        """ + slice_js(js, "function liveToolGate(heardResult", "// A short goodbye turn") \
            + slice_js(js, "function liveToolCall(c, tc) {", "// Typed words while Live is open") + r"""
          (async function () {
            const names = ['look', 'explain', 'fill', 'put_back', 'open', 'go_back', 'their_words'];
            const calls = names.map((action, id) => ({ id, name: 'use_screen', args: { action, field: 'i-room', value: '214' } }));
            let c = { toolBusy: 0, heardCheck: Promise.resolve({ emergency: 'fall' }) };
            let r = await liveToolCall(c, { functionCalls: calls });
            assert.strictEqual(r.functionResponses.length, 7);
            r.functionResponses.forEach(x => assert.strictEqual(x.response, TOOL_REFUSED));
            assert.strictEqual(runs.length, 0);
            S.screen = 'emergency';
            c = { toolBusy: 0, heardCheck: Promise.resolve({}) };
            r = await liveToolCall(c, { functionCalls: calls });
            r.functionResponses.forEach(x => assert.strictEqual(x.response, TOOL_REFUSED));
            assert.strictEqual(runs.length, 0);
            S.screen = 'everyday';
            r = await liveToolCall(c, { functionCalls: calls.concat([{ id: 7, name: 'recall', args: {} }]) });
            assert.deepStrictEqual(runs.map(x => x[1].action), names);   // in order
            assert.strictEqual(runs[2][2], ENV);
            assert.strictEqual(r.functionResponses.length, 8);
            assert.strictEqual(c.toolBusy, 0);
            console.log('ok');
          })().catch(function (e) { console.error(e); process.exit(1); });
        """
        rc, _, err = run_node(code)
        self.assertEqual(rc, 0, err)

    def test_the_screen_name_is_silent_and_held_back_in_a_story_or_emergency(self):
        js = read("mary/app.js")
        code = "globalThis.window = globalThis;\nconst assert = require('assert');\n" + r"""
          var S = { screen: 'everyday', convo: null }, notes = [], NAME = 'My info';
          function screenNote(t) { notes.push(t); } function screenEnv() { return {}; }
          window.MaryScreens = { TALK_NAME: 'Your own screen', nameHere() { return NAME; } };
        """ + slice_js(js, "function screenTell() {", "// ---------------------------------------------------------------- end M18") + r"""
          screenTell(); assert.strictEqual(notes.length, 0);
          S.convo = { live: true, story: {} }; screenTell(); assert.strictEqual(notes.length, 0);
          S.convo = { live: true }; S.screen = 'emergency'; screenTell(); assert.strictEqual(notes.length, 0);
          S.screen = 'everyday'; screenTell(); screenTell();
          assert.deepStrictEqual(notes, ['Screen: My info']);   // the name only, once
          console.log('ok');
        """
        rc, _, err = run_node(code)
        self.assertEqual(rc, 0, err)


class HalfTyped(unittest.TestCase):
    def test_a_dirty_form_survives_a_hash_trip(self):
        app = read("app.js")
        code = r"""
          const assert = require('assert');
          const store = {};
          const $ = s => store[s] || (store[s] = { value: '', hidden: false, open: true, disabled: false, textContent: '' });
          const $$ = () => [];
          const R = { when: 'now', wait: '', sev: '' };
          const BOXES = ['#words', '#day', '#time', '#staff_involved', '#reported_to', '#outcome', '#witnesses'];
          store['#form'] = { reset() { BOXES.forEach(k => { $(k).value = ''; }); R.when = 'now'; R.wait = ''; R.sev = ''; } };
          const radioVal = n => R[n], setRadio = (n, v) => { R[n] = v; };
          const EXTRA_FIELDS = ['staff_involved', 'reported_to', 'outcome', 'witnesses'];
          const CAT = { meal: { tile: 'Meal' }, staff: { tile: 'Staff' } };
          const IN_MARY = true;
          let add = {};
          function isoDate() { return '2026-11-01'; } function setType(k) { add.cat = CAT[k] ? k : null; } function setWait(m) { add.customWait = m; }
          function updateWhenUI() {} function setMic() {} function checkMic() {} function applyGuess() {} function applyWhen() {}
        """ + slice_js(app, "/* ---------- M18: half-typed work", "function initAdd(") \
            + slice_js(app, "function initAdd(", "function setType(key)") + r"""
          initAdd({ cat: 'meal' });
          $('#words').value = 'half typed'; $('#staff_involved').value = 'Dana'; R.wait = '120'; R.sev = 'serious';
          keepDraft();                     // leaving for #info
          initAdd({ cat: 'staff' });       // another group opens clean
          assert.strictEqual($('#words').value, '');
          keepDraft();                     // nothing typed, nothing kept
          initAdd({});                     // back by voice, no category
          assert.strictEqual($('#words').value, 'half typed');
          assert.strictEqual($('#staff_involved').value, 'Dana');
          assert.strictEqual(R.wait, '120');
          assert.strictEqual(R.sev, 'serious');
          assert.strictEqual(add.cat, 'meal');
          keepDraft();                     // still dirty after coming back
          initAdd({ cat: 'meal' });        // the same category
          assert.strictEqual($('#words').value, 'half typed');
          keepDraft();
          const inc = { id: 5, description: 'old words', category: 'meal', severity: 'minor', formal_summary: '', occurred_date: '2026-10-01' };
          initAdd({ incident: inc });      // editing is its own draft
          assert.strictEqual($('#words').value, 'old words');
          $('#words').value = 'new words';
          keepDraft();
          initAdd({ cat: 'meal' });
          assert.strictEqual($('#words').value, 'half typed');
          add.saved = true;                // Save clears it
          keepDraft();
          initAdd({ cat: 'meal' });
          assert.strictEqual($('#words').value, '');
          keepDraft();
          initAdd({ incident: inc });      // leaving edit mode lost nothing
          assert.strictEqual($('#words').value, 'new words');
          console.log('ok');
        """
        rc, _, err = run_node(code)
        self.assertEqual(rc, 0, err)

    def test_the_plain_log_is_as_it_was(self):
        app = read("app.js")
        body = slice_js(app, "function keepDraft() {", "function takeDraft(key)")
        self.assertIn("if (!IN_MARY || add.saved) return;", body)
        self.assertIn("if (IN_MARY && infoDirty) {", slice_js(app, "function route() {", "function renderCurrent()"))

    def test_every_route_keeps_it_first_and_my_info_is_not_written_over(self):
        app = read("app.js")
        route = slice_js(app, "function route() {", "function renderCurrent()")
        self.assertLess(route.index("keepDraft();"), route.index("switch (name)"))
        self.assertIn("infoDirty = false;", slice_js(app, "function fillInfo() {", "const mode ="))
        self.assertIn("if (cur.screen === 'add' || cur.screen === 'info' || add.busy", app)   # the focus listener still skips

    def test_a_save_ends_the_light(self):
        app = read("app.js")
        self.assertEqual(app.count("unlit();"), 2)
        self.assertIn("add.saved = true;", app)


class Instructions(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "mary" / "instructions.md").read_text(encoding="utf-8")
        self.part = slice_js(self.text, "Working on their screens\n", "Remembering\n- Below")

    def test_it_sits_apart_from_the_safety_sections(self):
        self.assertLess(self.text.index("Your screen\n- Your face"), self.text.index("Working on their screens\n"))
        self.assertLess(self.text.index("On their side, and toward people"), self.text.index("Working on their screens\n"))

    def test_what_it_says(self):
        for bit in ('"Is that right?"', "only when they ask", "Never narrate", "Never say anything is saved",
                    "I won't read or fill that one. A helper can type it in."):
            self.assertIn(bit, self.part)

    def test_no_tags_in_it(self):
        self.assertNotIn("[", self.part)   # a line with a tag is left out of Live


class Bench(unittest.TestCase):
    def test_the_three_cases_are_there(self):
        cases = json.loads((ROOT / "bench" / "cases" / "app_truth.json").read_text(encoding="utf-8"))["cases"]
        ids = [c["id"] for c in cases]
        for want in ("screen-refuses-the-secret", "screen-not-saved-early", "screen-no-narrating"):
            self.assertIn(want, ids)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
