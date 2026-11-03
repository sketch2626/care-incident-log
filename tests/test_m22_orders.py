from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M22 (D12): Mary turns a switch on or off when the resident tells her to, on the server's ruling of the raw line only
(send_gate.plain_order, through /api/mary/heard), the save gate's way (D8). Secrets stay locked (D9)."""
import sqlite3
import unittest
from contextlib import closing
from unittest import mock

import mary
import send_gate
from tests.test_book_screens import screens_node
from tests.test_m22_person_form import SETUP as PERSON_SETUP


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
                     "how do I turn it on?", "turn it off later", "yes", "okay", "",
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


class RemoveAndSeverityOrderTests(unittest.TestCase):
    def test_remove_orders(self):
        for line in ("remove it", "delete that note", "erase the smart helper model", "clear my room number", "wipe it",
                     "get rid of that", "cross out the last one", "disconnect my email", "take it off", "take that out",
                     "please clear the staff name"):
            got = send_gate.plain_order(line)
            self.assertIsNotNone(got, line)
            self.assertEqual(got["acts"], ["remove"], line)

    def test_take_it_off_is_remove_and_connect_is_not_disconnect(self):
        self.assertEqual(send_gate.plain_order("take it off")["acts"], ["remove"])
        self.assertEqual(send_gate.plain_order("connect my email")["acts"], ["on"])
        self.assertEqual(send_gate.plain_order("disconnect my email")["acts"], ["remove"])

    def test_remove_is_as_strict_as_on_and_off(self):
        for line in ("don't delete it", "should I remove it", "delete it later", "how do I clear it", "remove it?",
                     "remove it and turn it off", "wait, erase that", "delete it when I'm back"):
            self.assertIsNone(send_gate.plain_order(line), line)

    def test_how_bad_is_the_residents_word(self):
        for line, sev in (("serious", "serious"), ("It was serious when he dropped me", "serious"), ("I'd say dangerous", "dangerous"),
                          ("Minor, I guess", "minor"), ("it was dangerous", "dangerous")):
            got = send_gate.plain_order(line)
            self.assertIsNotNone(got, line)
            self.assertEqual((got["acts"], got["sev"]), (["sev"], sev), line)

    def test_how_bad_is_refused_on_a_negative_a_question_or_two_words(self):
        for line in ("not serious", "it wasn't dangerous", "serious or dangerous", "serious?", "never serious", "seriously",
                     "no, minor", "I don't think it was serious", "yes", "it was bad"):
            self.assertIsNone(send_gate.plain_order(line), line)
        self.assertIsNone(send_gate.plain_order("serious " + " ".join(["really"] * 16)))  # over the word cap

    def test_a_strict_order_wins_over_how_bad(self):
        self.assertEqual(send_gate.plain_order("turn it off, it was serious")["acts"], ["off"])
        self.assertIsNone(send_gate.plain_order("delete it, don't mark it serious"))


class SeverityScreenTests(unittest.TestCase):
    def check(self, body):
        rc, _, err = screens_node(SETUP + body)
        self.assertEqual(rc, 0, err)

    def test_d11_only_the_residents_word_sets_it(self):
        self.check(r"""
          const w = world({ acts: ['sev'], sev: 'serious', words: 'it was serious' }, 'add');
          const r = await fill(w, 'sev', 'minor');   // her own pick is ignored
          assert.strictEqual(r.ok, true, JSON.stringify(r)); assert.strictEqual(r.value, 'Serious'); assert.strictEqual(r.saved, false);
          assert.deepStrictEqual(w.page.groups.sev.filter(x => x.checked).map(x => x.value), ['serious']);
          const again = await fill(w, 'sev', 'dangerous');   // one line, one mark
          assert.strictEqual(again.ok, false);
          assert.deepStrictEqual(w.page.groups.sev.filter(x => x.checked).map(x => x.value), ['serious']);
        """)

    def test_d11_a_model_value_alone_does_nothing(self):
        self.check(r"""
          for (const order of [null, { acts: ['on'], words: 'turn it on' }]) {
            const w = world(order, 'add');
            w.env.turns = [{ text: 'yes' }];
            for (const v of ['serious', 'Dangerous', 'yes']) {
              const r = await fill(w, 'sev', v);
              assert.strictEqual(r.ok, false);
              assert(r.say.startsWith('Tell me which it was, Minor, Serious or Dangerous'), r.say);
            }
            assert.strictEqual(w.page.groups.sev.filter(x => x.checked).length, 0);
          }
          const e = await MaryScreens.run('explain_field', { field: 'sev' }, world(null, 'add').env);
          assert(/only to the word they say/.test(e.explain), e.explain);
        """)


class RemoveBoxTests(unittest.TestCase):
    def check(self, body):
        rc, _, err = screens_node(SETUP + body)
        self.assertEqual(rc, 0, err)

    def test_a_box_clears_on_the_order_and_put_back_restores_it(self):
        self.check(r"""
          const w = world(ORDER('remove', 'clear my room number'));
          const box = w.page.byId['i-room']; box.value = '214';
          const r = await MaryScreens.run('remove_thing', { field: 'i-room' }, w.env);
          assert.strictEqual(r.ok, true, JSON.stringify(r)); assert.strictEqual(r.removed, true); assert.strictEqual(r.saved, false);
          assert.strictEqual(box.value, ''); assert.deepStrictEqual(box.events.slice(-2), ['input', 'change']);
          assert(!JSON.stringify(r).includes('214'));
          assert.strictEqual((await MaryScreens.run('put_back', { field: 'i-room' }, w.env)).ok, true);
          assert.strictEqual(box.value, '214');
        """)

    def test_it_points_at_the_lit_box(self):
        self.check(r"""
          const w = world(ORDER('remove', 'clear it'), 'add');
          w.page.byId.staff_involved.value = 'Dana';
          await MaryScreens.run('explain_field', { field: 'staff_involved' }, w.env);
          assert.strictEqual((await MaryScreens.run('remove_thing', { field: 'staff_involved' }, w.env)).ok, true);
          assert.strictEqual(w.page.byId.staff_involved.value, '');
        """)

    def test_no_order_no_clearing(self):
        self.check(r"""
          for (const order of [null, ORDER('off', 'turn it off'), ORDER('remove', 'clear my name')]) {
            const w = world(order);
            w.page.byId['i-room'].value = '214';
            const a = await MaryScreens.run('remove_thing', { field: 'i-room' }, w.env);
            assert.strictEqual(a.ok, false); assert(a.say.startsWith('Tell me plainly what to remove'), a.say);
            assert.strictEqual(w.page.byId['i-room'].value, '214');
          }
        """)

    def test_a_choice_clears_and_a_switch_refuses_and_a_secret_stays(self):
        self.check(r"""
          const w = world(ORDER('remove', 'clear how mary talks'));
          w.page.groups.talk_mode[1].checked = true;
          const r = await MaryScreens.run('remove_thing', { field: 'talk_mode' }, w.env);
          assert.strictEqual(r.ok, true, JSON.stringify(r)); assert.strictEqual(r.removed, true);
          assert.strictEqual(w.page.groups.talk_mode.filter(x => x.checked).length, 0);
          assert.strictEqual((await MaryScreens.run('put_back', { field: 'talk_mode' }, w.env)).ok, true);
          assert.strictEqual(w.page.groups.talk_mode[1].checked, true);
          const w2 = world(ORDER('remove', 'remove the wake word'));
          w2.page.byId['i-wake_word'].checked = true;
          const sw = await MaryScreens.run('remove_thing', { field: 'i-wake_word' }, w2.env);
          assert.strictEqual(sw.ok, false); assert(sw.say.startsWith("A switch isn't removed"), sw.say);
          assert.strictEqual(w2.page.byId['i-wake_word'].checked, true);
          const w3 = world(ORDER('remove', 'clear the app password'));
          const sec = await MaryScreens.run('remove_thing', { field: 'mailPass' }, w3.env);
          assert.strictEqual(sec.ok, false); assert(sec.say.startsWith("I won't read or fill that one."), sec.say);
          assert.strictEqual(w3.page.byId.mailPass.value, 'typed by a helper');
        """)

    def test_a_detail_goes_from_the_card_to_the_form_and_its_value_stays_out(self):
        rc, _, err = screens_node(PERSON_SETUP + r"""
          const w = world();
          w.env.order = { acts: ['remove'], words: 'clear her phone' };
          const filled = [];
          w.doc.defaultView.maryBook = { filled(k) { filled.push(k); } };
          w.doc.byId['bf-phone'].value = '919-555-0142';
          const r = await run('remove_thing', { field: 'phone' }, w.env);
          assert.strictEqual(r.ok, true, JSON.stringify(r));
          assert.deepStrictEqual(w.opened, ['#book-form/p1']);
          assert.strictEqual(w.doc.byId['bf-phone'].value, '');
          assert.deepStrictEqual(filled, ['phone']);
          assert(!JSON.stringify(r).includes('919'));
        """)
        self.assertEqual(rc, 0, err)

    def test_the_email_disconnect_button(self):
        self.check(r"""
          const mk2 = (order, st) => { const w = world(order); w.calls = 0;
            w.page.defaultView.maryActs = { disconnectMail() { w.calls++; return Promise.resolve(st || { connected: false }); } }; return w; };
          const a = mk2(ORDER('remove', 'disconnect my email'));
          const r = await MaryScreens.run('remove_thing', { field: 'mailDisconnect' }, a.env);
          assert.strictEqual(r.ok, true, JSON.stringify(r)); assert.strictEqual(r.removed, true); assert.strictEqual(a.calls, 1);
          assert(/disconnected/.test(r.note));
          const f = mk2(ORDER('remove', 'disconnect my email'));   // a fill of the button is the same path
          assert.strictEqual((await fill(f, 'mailDisconnect', 'x')).ok, true); assert.strictEqual(f.calls, 1);
          const n = mk2(null);
          const none = await fill(n, 'mailDisconnect', 'x');
          assert.strictEqual(none.ok, false); assert(none.say.startsWith('Tell me plainly what to remove'), none.say); assert.strictEqual(n.calls, 0);
          const h = mk2(ORDER('remove', 'disconnect my email'));
          h.page.byId.mailDisconnect.hidden = true;
          const hid = await MaryScreens.run('remove_thing', { field: 'mailDisconnect' }, h.env);
          assert.strictEqual(hid.ok, false); assert.strictEqual(hid.say, "That isn't connected."); assert.strictEqual(h.calls, 0);
        """)


class RemoveNoteTests(unittest.TestCase):
    def check(self, body):
        rc, _, err = screens_node(SETUP + r"""
          const ROWS = [{ id: 11, category: 'meal', occurred_date: '2026-10-01', description: 'cold food', severity: 'minor' },
            { id: 12, category: 'call_light', occurred_date: '2026-10-05', description: 'no one came', severity: 'serious' },
            { id: 13, category: 'meal', occurred_date: '2026-10-09', description: 'late tray', severity: 'minor' }];
          function notes(order, shown) {
            const w = world(order, shown || 'list'); w.removed = []; w.edited = []; w.changed = 0;
            w.env.incidents = () => Promise.resolve(ROWS);
            w.env.removeIncident = id => { w.removed.push(id); return Promise.resolve({}); };
            w.page.defaultView.maryActs = { notesChanged() { w.changed++; return Promise.resolve(); },
              editNote(id) { w.edited.push(id); w.page.byId.list.hidden = true; w.page.byId.add.hidden = false; return true; } };
            return w;
          }
          const rm = (w, a) => MaryScreens.run('remove_thing', a, w.env);
          """ + body)
        self.assertEqual(rc, 0, err)

    def test_one_match_goes_and_the_answer_holds_no_id(self):
        self.check(r"""
          const w = notes(ORDER('remove', 'remove that note'));
          const r = await rm(w, { when: '2026-10-05' });
          assert.strictEqual(r.ok, true, JSON.stringify(r));
          assert.deepStrictEqual(w.removed, [12]); assert.strictEqual(w.changed, 1);
          assert.deepStrictEqual(r.removed, { date: '2026-10-05', category: 'No one answered my call light', words: 'no one came' });
          assert(!/"id"|\b12\b/.test(JSON.stringify(r)), JSON.stringify(r));
          const again = await rm(w, { when: '2026-10-01' });   // the same line is spent
          assert.strictEqual(again.ok, false); assert.deepStrictEqual(w.removed, [12]);
        """)

    def test_none_many_and_not_enough(self):
        self.check(r"""
          let w = notes(ORDER('remove', 'delete the note'));
          let r = await rm(w, { when: '2026-11' });
          assert.strictEqual(r.ok, false); assert.strictEqual(r.say, "There's nothing saved for that.");
          w = notes(ORDER('remove', 'delete the note'));
          r = await rm(w, { category: 'meal' });
          assert.strictEqual(r.ok, false); assert.strictEqual(r.say, 'There are 2 for that. Tell me the day or the kind of problem.');
          w = notes(ORDER('remove', 'delete the note'));
          r = await rm(w, {});
          assert.strictEqual(r.ok, false); assert.strictEqual(r.say, 'Tell me which note: the day or the kind of problem.');
          r = await rm(w, { when: 'last tuesday' });
          assert.strictEqual(r.ok, false);
          assert.deepStrictEqual(w.removed, []);
        """)

    def test_no_order_no_removal(self):
        self.check(r"""
          for (const order of [null, ORDER('off', 'turn it off'), ORDER('remove', 'delete the smart helper model'), { acts: ['sev'], sev: 'minor', words: 'minor' }]) {
            const w = notes(order);
            const r = await rm(w, { when: '2026-10-05' });
            assert.strictEqual(r.ok, false); assert(r.say.startsWith('Tell me plainly what to remove'), r.say);
            assert.deepStrictEqual(w.removed, []);
          }
        """)

    def test_reading_still_needs_an_ask(self):
        self.check(r"""
          const w = notes(ORDER('remove', 'remove that note'));
          const r = await MaryScreens.run('use_screen', { action: 'read_incidents', when: '2026-10-05' }, w.env);
          assert.strictEqual(r.ok, false);
          w.env.turns = [{ text: 'read my notes' }];
          assert.strictEqual((await MaryScreens.run('use_screen', { action: 'read_incidents', when: '2026-10-05' }, w.env)).count, 1);
        """)

    def test_a_saved_note_opens_to_change(self):
        self.check(r"""
          const w = notes(null);   // opening needs no order
          const r = await MaryScreens.run('open_screen', { name: 'write', when: '2026-10-05' }, w.env);
          assert.strictEqual(r.ok, true, JSON.stringify(r)); assert.strictEqual(r.screen, 'Write something down');
          assert.deepStrictEqual(w.edited, [12]);
          assert(/Nothing changes until they say save it/.test(r.note));
          assert(!JSON.stringify(r).includes('12'));
          const m = notes(null);
          const many = await MaryScreens.run('open_screen', { name: 'write', category: 'meal' }, m.env);
          assert.strictEqual(many.ok, false); assert.strictEqual(many.say, 'There are 2 for that. Tell me the day or the kind of problem.');
          assert.deepStrictEqual(m.edited, []);
          // a write_ name is still the new-note path
          const n = notes(null); let asked = 0;
          n.env.incidents = () => { asked++; return Promise.resolve(ROWS); };
          n.env.openDeep = () => { n.page.byId.list.hidden = true; n.page.byId.add.hidden = false; return true; };
          const nw = await MaryScreens.run('open_screen', { name: 'write_meal', category: 'meal' }, n.env);
          assert.strictEqual(nw.ok, true); assert.strictEqual(asked, 0); assert.deepStrictEqual(n.edited, []);
        """)


class RemoveRouteTests(unittest.TestCase):
    def test_the_same_delete_a_tap_makes_is_a_soft_delete(self):
        helpers.reset_db()
        status, made, _ = helpers.api("POST", "/api/incidents", helpers.incident())
        self.assertIn(status, (200, 201))
        new_id = made["id"]
        self.assertEqual(helpers.api("DELETE", f"/api/incidents/{new_id}", {})[0], 200)
        _, rows, _ = helpers.api("GET", "/api/incidents")
        self.assertNotIn(new_id, [r["id"] for r in rows])
        import server
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            self.assertIsNotNone(conn.execute("SELECT deleted_at FROM incidents WHERE id = ?", (new_id,)).fetchone()[0])


class ToolTextTests(unittest.TestCase):
    def test_remove_is_a_listed_action(self):
        text = [d for d in mary.LIVE_PAGE_TOOLS if d["name"] == "use_screen"][0]
        self.assertIn("remove", text["description"])
        self.assertIn("remove", text["parameters"]["properties"]["action"]["description"])


if __name__ == "__main__":
    unittest.main()
