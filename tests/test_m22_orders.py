from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M22 (D12): Mary turns a switch on or off when the resident tells her to, on the server's ruling of the raw line only
(send_gate.plain_order, through /api/mary/heard), the save gate's way (D8). Secrets stay locked (D9)."""
import unittest
from unittest import mock

import mary
import send_gate
from tests.test_book_screens import screens_node


class PlainOrderTests(unittest.TestCase):
    def test_a_plain_order_is_one(self):
        for line, act in (("turn it off", "off"), ("Mary, turn off the smart helper please", "off"),
                          ("can you turn the wake word off?", "off"), ("shut that off", "off"), ("disable it", "off"),
                          ("turn on the smart helper", "on"), ("please enable the wake word", "on"),
                          ("connect my email", "on"), ("switch it on", "on")):
            got = send_gate.plain_order(line)
            self.assertIsNotNone(got, line)
            self.assertEqual(got["acts"], [act], line)

    def test_words_come_back_lower_case(self):
        self.assertEqual(send_gate.plain_order("Mary, Turn it OFF")["words"], "mary turn it off")

    def test_anything_less_is_not(self):
        for line in ("don't turn it off", "don’t turn it off", "should I turn it off", "what happens if I turn it off",
                     "how do I turn it on?", "turn it off later", "yes", "okay", "", "disconnect my email",
                     "turn it on and then off", "turn it off?", "turn it off’s later", "does turning it off help", "turn it off, I think?",
                     "wait, turn it off"):
            self.assertIsNone(send_gate.plain_order(line), line)

    def test_the_word_cap(self):
        ok = "turn off the smart helper " + " ".join(["please"] * 11)  # 16 words
        self.assertEqual(len(ok.split()), 16)
        self.assertIsNotNone(send_gate.plain_order(ok))
        self.assertIsNone(send_gate.plain_order(ok + " please"))
        self.assertEqual(send_gate.PLAIN_WORDS_MAX, 12)


class HeardRouteTests(unittest.TestCase):
    def heard(self, text, **more):
        status, got, _ = helpers.api("POST", "/api/mary/heard", dict({"text": text}, **more))
        self.assertEqual(status, 200)
        return got

    def test_an_order_is_answered(self):
        got = self.heard("turn off the smart helper")
        self.assertEqual(got["order"]["acts"], ["off"])
        self.assertIn("smart helper", got["order"]["words"])

    def test_chatty_words_are_not(self):
        self.assertNotIn("order", self.heard("okay"))

    def test_not_for_a_typed_note(self):
        self.assertNotIn("order", self.heard("turn off the smart helper", note=True))

    def test_not_in_an_emergency(self):
        got = self.heard("I can't breathe, turn off the smart helper")
        self.assertTrue(got["emergency"])
        self.assertNotIn("order", got)

    def test_not_when_garbled(self):
        with mock.patch.object(mary, "not_english", return_value=True):
            got = self.heard("turn off the smart helper")
        self.assertTrue(got["garbled"])
        self.assertNotIn("order", got)


# A page with My info showing, and the email button as a real button that counts its clicks.
SETUP = r"""
function world(order, shown) {
  const page = pageOn(shown || 'info');
  page.byId.mailConnect.type = 'button';
  page.byId.mailConnect.clicks = 0;
  page.byId.mailConnect.click = function () { this.clicks++; };
  page.byId.mailPass.value = 'typed by a helper';
  const env = envOn(page);
  env.order = order || null;
  return { page, env };
}
const fill = (w, field, value) => MaryScreens.run('fill_field', { field, value }, w.env);
const ORDER = (act, words) => ({ acts: [act], words });
"""


class SwitchScreenTests(unittest.TestCase):
    def check(self, body):
        rc, _, err = screens_node(SETUP + body)
        self.assertEqual(rc, 0, err)

    def test_the_ruling_flips_that_switch_and_only_it(self):
        self.check(r"""
          const w = world(ORDER('on', 'turn on the smart helper please'));
          const r = await fill(w, 'i-gemini_enabled', 'off');   // her value is ignored
          assert.strictEqual(r.ok, true); assert.strictEqual(r.value, 'on'); assert.strictEqual(r.saved, false);
          assert.strictEqual(w.page.byId['i-gemini_enabled'].checked, true);
          assert.deepStrictEqual(w.page.byId['i-gemini_enabled'].events, ['input', 'change']);
          for (const id of ['i-wake_word', 'i-talk_on_open', 'i-andyflow_enabled']) { assert.strictEqual(w.page.byId[id].checked, false, id); }
          assert.strictEqual(w.page.byId.mailConnect.clicks, 0);
        """)

    def test_without_a_ruling_nothing_moves(self):
        self.check(r"""
          const w = world(null);
          for (const v of ['off', 'on']) {
            const r = await fill(w, 'i-gemini_enabled', v);
            assert.strictEqual(r.ok, false); assert(r.say.startsWith('Tell me plainly'), r.say);
          }
          assert.strictEqual(w.page.byId['i-gemini_enabled'].checked, false);
          w.page.byId['i-wake_word'].checked = true;
          assert.strictEqual((await fill(w, 'i-wake_word', 'off')).ok, false);
          assert.strictEqual(w.page.byId['i-wake_word'].checked, true);
          assert.deepStrictEqual(w.page.byId['i-wake_word'].events, []);
        """)

    def test_an_order_for_another_switch_is_refused(self):
        self.check(r"""
          const w = world(ORDER('on', 'turn on the wake word'));
          const r = await fill(w, 'i-gemini_enabled', 'on');
          assert.strictEqual(r.ok, false);
          assert.strictEqual(w.page.byId['i-gemini_enabled'].checked, false);
          assert.strictEqual((await fill(w, 'i-wake_word', 'on')).ok, true);
        """)

    def test_a_wrong_direction_is_refused(self):
        self.check(r"""
          const w = world(ORDER('off', 'turn off the smart helper'));
          w.page.byId['i-gemini_enabled'].checked = true;
          const r = await fill(w, 'i-gemini_enabled', 'on');   // the model says on; the resident said off
          assert.strictEqual(r.ok, true); assert.strictEqual(r.value, 'off');
          assert.strictEqual(w.page.byId['i-gemini_enabled'].checked, false);
        """)

    def test_turn_it_off_needs_the_field_lit_first(self):
        self.check(r"""
          const w = world(ORDER('off', 'turn it off'));
          w.page.byId['i-wake_word'].checked = true;
          assert.strictEqual((await fill(w, 'i-wake_word', 'off')).ok, false);   // nothing lit yet
          assert.strictEqual(w.page.byId['i-wake_word'].checked, true);
          assert.strictEqual((await MaryScreens.run('explain_field', { field: 'i-wake_word' }, w.env)).ok, true);
          assert.strictEqual((await fill(w, 'i-gemini_enabled', 'off')).ok, false);   // lit one is a different switch
          assert.strictEqual((await fill(w, 'i-wake_word', 'off')).ok, true);
          assert.strictEqual(w.page.byId['i-wake_word'].checked, false);
        """)

    def test_one_line_acts_once_per_switch(self):
        self.check(r"""
          const w = world(ORDER('on', 'turn on the smart helper'));
          assert.strictEqual((await fill(w, 'i-gemini_enabled', 'on')).ok, true);
          w.page.byId['i-gemini_enabled'].checked = false;   // the resident turned it back off by hand
          assert.strictEqual((await fill(w, 'i-gemini_enabled', 'on')).ok, false);
          assert.strictEqual(w.page.byId['i-gemini_enabled'].checked, false);
          w.env.order = ORDER('on', 'turn on the smart helper');   // a new line is a new ruling
          assert.strictEqual((await fill(w, 'i-gemini_enabled', 'on')).ok, true);
        """)

    def test_put_back_restores_the_switch(self):
        self.check(r"""
          const w = world(ORDER('off', 'turn off the wake word'));
          const el = w.page.byId['i-wake_word'];
          el.checked = true;
          await fill(w, 'i-wake_word', 'off');
          assert.strictEqual(el.checked, false);
          const r = await MaryScreens.run('put_back', { field: 'i-wake_word' }, w.env);
          assert.strictEqual(r.ok, true); assert.strictEqual(el.checked, true);
        """)

    def test_the_email_button_only_goes_on_and_only_on_the_order(self):
        self.check(r"""
          let w = world(ORDER('off', 'turn off the email'));
          assert.strictEqual((await fill(w, 'mailConnect', 'on')).ok, false);
          w = world(null);
          assert.strictEqual((await fill(w, 'mailConnect', 'on')).ok, false);
          assert.strictEqual(w.page.byId.mailConnect.clicks, 0);
          w = world(ORDER('on', 'connect my email'));
          const r = await fill(w, 'mailConnect', 'off');
          assert.strictEqual(r.ok, true); assert.strictEqual(r.saved, false);
          assert(r.next.startsWith('Connecting now'), r.next);
          assert.strictEqual(w.page.byId.mailConnect.clicks, 1);
          assert.strictEqual(w.page.byId.mailPass.value, 'typed by a helper');   // she never touches it
          assert(!JSON.stringify(r).includes('typed by a helper'));
        """)

    def test_save_is_never_pressed(self):
        self.check(r"""
          const w = world(ORDER('on', 'turn on the smart helper'));
          w.page.byId.infoSave = { id: 'infoSave', clicks: 0, click() { this.clicks++; } };
          await fill(w, 'i-gemini_enabled', 'on');
          assert.strictEqual(w.page.byId.infoSave.clicks, 0);
          assert.strictEqual(MaryScreens.TOOL_NAMES.filter(n => /save/i.test(n)).length, 0);
        """)

    def test_a_secret_stays_locked_with_an_order_present(self):
        self.check(r"""
          const w = world(ORDER('on', 'turn on the smart helper key please'));
          for (const field of ['i-gemini_key', 'mailPass', 'App password', 'copyWords']) {
            const r = await fill(w, field, 'x');
            assert.strictEqual(r.ok, false, field);
            assert(r.say.startsWith("I won't read or fill that one."), field + ': ' + r.say);
          }
          assert.strictEqual(w.page.byId.mailPass.value, 'typed by a helper');
        """)

    def test_from_another_screen_the_switch_hops_to_my_info(self):
        self.check(r"""
          const w = world(ORDER('off', 'turn off the smart helper'), 'add');
          w.page.byId['i-gemini_enabled'].checked = true;
          w.env.openDeep = function (h) {
            ['add', 'info'].forEach(f => { w.page.byId[f].hidden = ('#' + f) !== h; });
            return true;
          };
          const r = await fill(w, 'smart helper', 'off');
          assert.strictEqual(r.ok, true, JSON.stringify(r));
          assert.strictEqual(w.page.byId.info.hidden, false);
          assert.strictEqual(w.page.byId['i-gemini_enabled'].checked, false);
          // and with no ruling, it opens My info and still refuses
          const w2 = world(null, 'add');
          w2.env.openDeep = function (h) { ['add', 'info'].forEach(f => { w2.page.byId[f].hidden = ('#' + f) !== h; }); return true; };
          w2.page.byId['i-gemini_enabled'].checked = true;
          assert.strictEqual((await fill(w2, 'smart helper', 'off')).ok, false);
          assert.strictEqual(w2.page.byId['i-gemini_enabled'].checked, true);
        """)

    def test_a_secret_does_not_hop(self):
        self.check(r"""
          const w = world(ORDER('on', 'turn it on'), 'add');
          let opened = 0;
          w.env.openDeep = function () { opened++; return true; };
          const r = await fill(w, 'i-gemini_key', 'x');
          assert.strictEqual(r.ok, false);
          assert.strictEqual(opened, 0);
          assert(!r.say.startsWith('Tell me plainly'));
        """)


class PlainChoiceTests(unittest.TestCase):
    def check(self, body):
        rc, _, err = screens_node(SETUP + body)
        self.assertEqual(rc, 0, err)

    def test_choices_fill_without_an_order_and_save_waits(self):
        self.check(r"""
          const w = world(null);
          const on = name => w.page.groups[name].filter(r => r.checked).map(r => r.value)[0];
          let r = await fill(w, 'talk_mode', 'live');
          assert.strictEqual(r.ok, true, JSON.stringify(r)); assert.strictEqual(r.value, 'Live (best)'); assert.strictEqual(on('talk_mode'), 'live');
          assert.strictEqual((await fill(w, 'listen_wait', 'More time')).ok, true); assert.strictEqual(on('listen_wait'), '4');
          assert.strictEqual((await fill(w, 'How much Mary is told', 'lean')).ok, true); assert.strictEqual(on('mary_brain'), 'lean');
          assert.strictEqual((await fill(w, 'mary_brain', 'leaner')).ok, true); assert.strictEqual(on('mary_brain'), 'leaner');
          r = await fill(w, 'talk_mode', 'sideways');
          assert.strictEqual(r.ok, false); assert(r.say.includes('Live (best)'), r.say);
          assert.strictEqual(r.saved, undefined);
        """)

    def test_a_word_in_two_labels_is_not_a_pick(self):
        self.check(r"""
          const w = world(null);
          const r = await fill(w, 'mary_brain', 'instructions');
          assert.strictEqual(r.ok, false);
          assert.strictEqual(w.page.groups.mary_brain.filter(x => x.checked).length, 0);
        """)

    def test_the_model_box_is_a_plain_text_fill(self):
        self.check(r"""
          const w = world(null);
          const r = await fill(w, 'i-gemini_model', 'gemini-x');
          assert.strictEqual(r.ok, true, JSON.stringify(r));
          assert.strictEqual(w.page.byId['i-gemini_model'].value, 'gemini-x');
        """)


class SwitchNameTests(unittest.TestCase):
    def test_a_switchs_own_name_is_not_a_delay(self):
        import send_gate
        self.assertEqual(send_gate.plain_order("turn off talking when Mary opens")["acts"], ["off"])
        self.assertIsNone(send_gate.plain_order("turn it off when I go to bed"))


if __name__ == "__main__":
    unittest.main()
