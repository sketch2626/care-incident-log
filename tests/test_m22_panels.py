from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M22 (D12): Mary's own panels (My info lists, Choose Mary or Sam). A fill on a row is the row's own tap, on the
server's ruling of the resident's words only (send_gate.plain_order "set", "on", "off"). Node with a fake page."""
import unittest

import send_gate
from tests.test_book_screens import screens_node

FAKE = r"""
function btn(name, attrs) {
  const a = Object.assign({}, attrs || {});
  return { clicks: 0, textContent: name + ' hint', getAttribute(k) { return k in a ? a[k] : null; },
    setAttr(k, v) { a[k] = v; }, querySelector(s) { return s === '.txt span' ? { textContent: name } : null; },
    click() { this.clicks++; } };
}
function radio(name, on, dis) { return btn(name, { 'aria-checked': on ? 'true' : 'false', 'aria-disabled': dis ? 'true' : null }); }
function box(radios) {
  return { items: radios, lead: null,
    querySelectorAll(s) { return s === '[role="radio"]' ? this.items : []; },
    querySelector(s) { return s === '.lead' && this.lead ? { textContent: this.lead } : null; } };
}
function skillBox(skills) {
  const b = { lead: null, rows: skills.map(function (k) {
      const x = btn('', { 'aria-pressed': k.on ? 'true' : 'false', 'aria-disabled': k.locked ? 'true' : null });
      return { b: x, querySelector(s) { return s === '.txt span' ? { textContent: k.title } : s === 'button' ? x : null; } };
    }),
    querySelectorAll(s) { return s === '.row' ? this.rows : []; },
    querySelector(s) { return s === '.lead' && this.lead ? { textContent: this.lead } : null; } };
  return b;
}
function make() {
  const lists = {
    modeList: box([radio('Live (best)', true), radio('Normal'), radio('Offline')]),
    voiceList: box([radio('Deep and calm', true), radio('Bright'), radio('Soft and slow'), radio('Warm', false, true)]),
    waitList: box([radio('Usual', true), radio('More time')]),
    wakeList: box([radio('On'), radio('Off', true)]),
    skillList: skillBox([{ title: 'Weather', on: true }, { title: 'Jokes', on: false }, { title: 'Reminders', on: true, locked: true }]),
    chooseList: box([radio('Mary', true), radio('Sam')])
  };
  const page = { getElementById(id) { return lists[id] || null; } };
  const st = { panel: null, opened: [] };
  const env = envOn(pageOn('home'), { page() { return page; }, panel() { return st.panel; },
    openPanel(p) { st.opened.push(p); st.panel = p; } });
  return { lists, env, st };
}
const say = (env, words, acts) => { env.order = { acts: acts, words: words }; };
const clicks = (b) => b.items ? b.items.map(x => x.clicks) : b.rows.map(r => r.b.clicks);
"""


class PlainSetOrder(unittest.TestCase):
    def test_a_set_order(self):
        for line in ("use the deep voice", "switch to Sam", "change it to More time", "Mary, pick the bright one", "go with Normal"):
            got = send_gate.plain_order(line)
            self.assertIsNotNone(got, line)
            self.assertEqual(got["acts"], ["set"], line)

    def test_anything_less_is_not(self):
        for line in ("don't use that voice", "what voice is that", "should I switch", "use the deep voice later"):
            self.assertIsNone(send_gate.plain_order(line), line)

    def test_on_and_off_still_win(self):
        self.assertEqual(send_gate.plain_order("switch it on")["acts"], ["on"])
        self.assertEqual(send_gate.plain_order("set the weather off")["acts"], ["off"])
        self.assertEqual(send_gate.plain_order("make it serious")["acts"], ["sev"])


class Panels(unittest.TestCase):
    def check(self, body):
        rc, out, err = screens_node(FAKE + "\n" + body)
        self.assertEqual(rc, 0, err)

    def test_look_lists_the_names_and_never_memories(self):
        self.check("""
          const m = make(); m.st.panel = 'infoPanel';
          const card = await run('look_at_screen', {}, m.env);
          const by = {}; card.rows.forEach(r => { by[r.field] = r; });
          assert.deepStrictEqual(by.voice.choices, ['Deep and calm', 'Bright', 'Soft and slow', 'Warm']);
          assert.strictEqual(by.voice.value, 'Deep and calm');
          assert.deepStrictEqual(by.skills.choices, ['Weather: On', 'Jokes: Off', 'Reminders: Set by your helper']);
          assert.deepStrictEqual(by.wake.choices, ['On', 'Off']);
          assert.strictEqual(by.wait.value, 'Usual');
          assert.ok(!JSON.stringify(card).includes('hint'));
          assert.ok(!JSON.stringify(card).toLowerCase().includes('memor'));
          assert.strictEqual(card.fields, undefined);
        """)

    def test_each_list_clicks_only_the_right_button_with_an_order(self):
        self.check("""
          let m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'use the bright voice', ['set']);
          let r = await run('fill_field', { field: 'voice', value: 'bright' }, m.env);
          assert.strictEqual(r.ok, true); assert.deepStrictEqual(clicks(m.lists.voiceList), [0, 1, 0, 0]);
          m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'change it to more time', ['set']);
          r = await run('fill_field', { field: 'wait', value: 'More time' }, m.env);
          assert.strictEqual(r.ok, true); assert.deepStrictEqual(clicks(m.lists.waitList), [0, 1]);
          m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'switch to normal', ['set']);
          r = await run('fill_field', { field: 'talk_mode', value: 'normal' }, m.env);
          assert.strictEqual(r.ok, true); assert.deepStrictEqual(clicks(m.lists.modeList), [0, 1, 0]);
          m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'turn off hey mary', ['off']);
          r = await run('fill_field', { field: 'wake', value: 'off' }, m.env);
          assert.strictEqual(r.ok, true); assert.strictEqual(r.value, 'Off');   // already off: no click
          assert.deepStrictEqual(clicks(m.lists.wakeList), [0, 0]);
          m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'turn on hey mary', ['on']);
          r = await run('fill_field', { field: 'wake' }, m.env);
          assert.deepStrictEqual(clicks(m.lists.wakeList), [1, 0]);
          m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'turn on the jokes', ['on']);
          r = await run('fill_field', { field: 'skills', value: 'Jokes' }, m.env);
          assert.strictEqual(r.ok, true); assert.deepStrictEqual(clicks(m.lists.skillList), [0, 1, 0]);
          m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'turn off the weather', ['off']);
          await run('fill_field', { field: 'skills', value: 'Weather' }, m.env);
          assert.deepStrictEqual(clicks(m.lists.skillList), [1, 0, 0]);
        """)

    def test_no_order_clicks_nothing_and_does_not_hop(self):
        self.check("""
          const m = make();
          for (const o of [undefined, { acts: [], words: 'bright' }, { acts: ['on'], words: 'use the bright voice' }]) {
            m.env.order = o;
            const r = await run('fill_field', { field: 'voice', value: 'bright' }, m.env);
            assert.strictEqual(r.ok, false);
          }
          assert.deepStrictEqual(m.st.opened, []);
          assert.deepStrictEqual(clicks(m.lists.voiceList), [0, 0, 0, 0]);
        """)

    def test_a_value_not_in_their_line_is_refused(self):
        self.check("""
          const m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'use the bright voice', ['set']);
          let r = await run('fill_field', { field: 'voice', value: 'soft' }, m.env);
          assert.strictEqual(r.ok, false);
          assert.deepStrictEqual(clicks(m.lists.voiceList), [0, 0, 0, 0]);
          say(m.env, 'switch to sam', ['set']);
          r = await run('fill_field', { field: 'companion', value: 'mary' }, m.env);   // Mary is already chosen but not what they said
          assert.strictEqual(r.ok, false);
          say(m.env, 'use the voice', ['set']);   // names nothing
          r = await run('fill_field', { field: 'voice', value: 'calm' }, m.env);
          assert.strictEqual(r.ok, false);
          assert.deepStrictEqual(clicks(m.lists.voiceList), [0, 0, 0, 0]);
        """)

    def test_an_unclear_value_lists_the_choices(self):
        self.check("""
          const m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'use the and voice', ['set']);
          const r = await run('fill_field', { field: 'voice', value: 'and' }, m.env);   // only a stop word
          assert.strictEqual(r.ok, false);
          say(m.env, 'use the o voice', ['set']);
          const r2 = await run('fill_field', { field: 'voice', value: 'xyz' }, m.env);
          assert.strictEqual(r2.ok, false); assert.ok(/Deep and calm/.test(r2.say));
          assert.deepStrictEqual(clicks(m.lists.voiceList), [0, 0, 0, 0]);
        """)

    def test_a_locked_one_is_not_clicked(self):
        self.check("""
          let m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'turn off reminders', ['off']);
          let r = await run('fill_field', { field: 'skills', value: 'Reminders' }, m.env);
          assert.strictEqual(r.ok, false); assert.strictEqual(r.say, 'Your helper set that one.');
          assert.deepStrictEqual(clicks(m.lists.skillList), [0, 0, 0]);
          say(m.env, 'use the warm voice', ['set']);
          r = await run('fill_field', { field: 'voice', value: 'warm' }, m.env);
          assert.strictEqual(r.ok, false);
          assert.deepStrictEqual(clicks(m.lists.voiceList), [0, 0, 0, 0]);
        """)

    def test_already_chosen_is_ok_and_not_clicked(self):
        self.check("""
          const m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'use deep and calm', ['set']);
          const r = await run('fill_field', { field: 'voice', value: 'deep' }, m.env);
          assert.strictEqual(r.ok, true); assert.strictEqual(r.value, 'Deep and calm');
          say(m.env, 'turn on the weather', ['on']);
          const r2 = await run('fill_field', { field: 'skills', value: 'weather' }, m.env);
          assert.strictEqual(r2.ok, true);
          assert.deepStrictEqual(clicks(m.lists.voiceList), [0, 0, 0, 0]);
          assert.deepStrictEqual(clicks(m.lists.skillList), [0, 0, 0]);
        """)

    def test_the_order_is_spent_once(self):
        self.check("""
          const m = make(); m.st.panel = 'infoPanel';
          say(m.env, 'use bright', ['set']);
          await run('fill_field', { field: 'voice', value: 'bright' }, m.env);
          m.lists.voiceList.items[1].setAttr('aria-checked', 'false');
          const r = await run('fill_field', { field: 'voice', value: 'bright' }, m.env);
          assert.strictEqual(r.ok, false);
          assert.deepStrictEqual(clicks(m.lists.voiceList), [0, 1, 0, 0]);
        """)

    def test_a_word_from_another_screen_opens_the_panel_first(self):
        self.check("""
          const m = make();
          say(m.env, 'switch to sam', ['set']);
          const r = await run('fill_field', { field: 'sam' }, m.env);
          assert.strictEqual(r.ok, true);
          assert.deepStrictEqual(m.st.opened, ['choosePanel']);
          assert.deepStrictEqual(clicks(m.lists.chooseList), [0, 1]);
          const n = make();
          say(n.env, 'use the bright voice', ['set']);
          await run('fill_field', { field: 'voice', value: 'bright' }, n.env);
          assert.deepStrictEqual(n.st.opened, ['infoPanel']);
          assert.deepStrictEqual(clicks(n.lists.voiceList), [0, 1, 0, 0]);
        """)

    def test_a_my_info_field_wins_unless_the_panel_is_open(self):
        self.check("""
          const m = make(), seen = [];
          m.env.openDeep = (h) => { seen.push(h); return true; };
          say(m.env, 'turn on hey mary', ['on']);
          await run('fill_field', { field: 'hey mary' }, m.env);   // from home: the My info page, as before
          assert.deepStrictEqual(m.st.opened, []);
          assert.deepStrictEqual(clicks(m.lists.wakeList), [0, 0]);
          const n = make(); n.st.panel = 'infoPanel';
          say(n.env, 'turn on hey mary', ['on']);
          await run('fill_field', { field: 'hey mary' }, n.env);   // panel open: the row
          assert.deepStrictEqual(clicks(n.lists.wakeList), [1, 0]);
        """)

    def test_a_list_still_loading_then_arriving(self):
        self.check("""
          const m = make(); m.st.panel = 'infoPanel';
          const items = m.lists.voiceList.items;
          m.lists.voiceList.items = []; m.lists.voiceList.lead = 'Getting the voices…';
          setTimeout(() => { m.lists.voiceList.items = items; m.lists.voiceList.lead = null; }, 300);
          say(m.env, 'use the bright voice', ['set']);
          const r = await run('fill_field', { field: 'voice', value: 'bright' }, m.env);
          assert.strictEqual(r.ok, true);
          assert.deepStrictEqual(clicks(m.lists.voiceList), [0, 1, 0, 0]);
        """)

    def test_a_list_that_never_arrives_says_so(self):
        self.check("""
          const m = make(); m.st.panel = 'infoPanel';
          m.lists.skillList.rows = []; m.lists.skillList.lead = 'Getting the list…';
          const card = await run('look_at_screen', {}, m.env);
          assert.strictEqual(card.ok, false); assert.strictEqual(card.say, "That didn't open just now.");
          say(m.env, 'turn on jokes', ['on']);
          const r = await run('fill_field', { field: 'skills', value: 'jokes' }, m.env);
          assert.strictEqual(r.ok, false); assert.strictEqual(r.say, "That didn't open just now.");
        """)


if __name__ == "__main__":
    unittest.main()
