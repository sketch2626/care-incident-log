from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M22: Andy's "the phone box on a person's form is locked". A fill asked for on a person's card goes to that person's
form (D12: every voice path that replaces a button must work). Nothing saves (D8), secrets stay out (D9)."""
import unittest

from tests.test_book_screens import screens_node

# A fake frame: openDeep sets the hash and shows the matching section, like the frame's router does.
SETUP = r"""
function world(opts) {
  opts = opts || {};
  const doc = pageOn('none');
  doc.byId['book-card'] = mk('book-card');
  doc.byId['book-form'] = mk('book-form', { hidden: true });
  doc.defaultView.location = { hash: '#book-card/p1' };
  const opened = [];
  const env = envOn(doc, { openDeep(h) {
    opened.push(h);
    if (opts.stuck) { return true; }
    doc.defaultView.location.hash = h;
    const form = h.indexOf('#book-form') === 0;
    doc.byId['book-card'].hidden = form; doc.byId['book-form'].hidden = !form;
    return true;
  }, findPeople() { return Promise.resolve({ state: 'open', people: [{ id: 'p1', name: 'Sarah', relationship: 'daughter' }] }); } });
  return { doc, env, opened };
}
"""


class PersonFormTests(unittest.TestCase):
    def check(self, body):
        rc, _, err = screens_node(SETUP + body)
        self.assertEqual(rc, 0, err)

    def test_d18_with_the_forms_box_focused_she_still_fills_it(self):
        self.check(r"""
          const w = world();
          const o = await run('open_screen', { name: 'book-form', who: 'Sarah' }, w.env);
          assert.strictEqual(o.ok, true);
          w.doc.activeElement = w.doc.byId['bf-phone'];
          const got = await run('fill_field', { field: 'phone', value: '919-555-0142' }, w.env);
          assert.strictEqual(w.doc.byId['bf-phone'].value, '919-555-0142');
          assert.strictEqual(got.ok, true);
          assert.strictEqual(got.saved, false);
        """)

    def test_d12_change_a_persons_phone_reaches_the_form(self):
        self.check(r"""
          let w = world();
          let got = await run('fill_field', { field: 'phone', value: '919-555-0142' }, w.env);
          assert.deepStrictEqual(w.opened, ['#book-form/p1']);
          assert.strictEqual(w.doc.defaultView.location.hash, '#book-form/p1');
          assert.strictEqual(w.doc.byId['bf-phone'].value, '919-555-0142');
          assert.strictEqual(got.ok, true);
          assert.strictEqual(got.saved, false);
          assert.ok(!w.doc.byId['bf-cell'].value);
          // the same through open (book-form + who), then fill
          w = world();
          const o = await run('open_screen', { name: 'book-form', who: 'Sarah' }, w.env);
          assert.strictEqual(o.ok, true);
          got = await run('fill_field', { field: 'phone', value: '919-555-0142' }, w.env);
          assert.strictEqual(w.doc.defaultView.location.hash, '#book-form/p1');
          assert.strictEqual(w.doc.byId['bf-phone'].value, '919-555-0142');
          assert.strictEqual(got.ok, true);
          assert.strictEqual(got.saved, false);
          // no Save was pressed: nothing clicked anywhere
          Object.keys(w.doc.byId).forEach(k => assert.ok(!(w.doc.byId[k].events || []).includes('click'), k));
        """)

    def test_d12_a_card_id_with_who_still_reaches_the_form(self):
        self.check(r"""
          const w = world();
          const got = await run('fill_field', { field: 'bc-phone', who: 'Sarah', value: '919-555-0142' }, w.env);
          assert.strictEqual(got.ok, true);
          assert.strictEqual(w.doc.byId['bf-phone'].value, '919-555-0142');
        """)

    def test_phone_means_home_unless_only_the_cell_is_filled(self):
        self.check(r"""
          let w = world();
          await run('fill_field', { field: 'mobile', value: '919-555-0100' }, w.env);
          assert.strictEqual(w.doc.byId['bf-cell'].value, '919-555-0100');
          assert.ok(!w.doc.byId['bf-phone'].value);
          await run('fill_field', { field: 'phone', value: '919-555-0111' }, w.env);   // cell filled, home empty: the cell
          assert.strictEqual(w.doc.byId['bf-cell'].value, '919-555-0111');
          assert.ok(!w.doc.byId['bf-phone'].value);
          w = world();
          await run('fill_field', { field: 'Home phone', value: '919-555-0122' }, w.env);
          assert.strictEqual(w.doc.byId['bf-phone'].value, '919-555-0122');
        """)

    def test_she_gets_back_what_is_really_in_the_box(self):
        self.check(r"""
          const w = world();
          await run('fill_field', { field: 'Notes', value: 'x' }, w.env);   // lands on the form
          const box = w.doc.byId['bf-phone'];
          let real = '';
          Object.defineProperty(box, 'value', { get() { return real; }, set(v) { real = '(919) ' + String(v).replace(/^919-/, ''); } });
          const got = await run('fill_field', { field: 'phone', value: '919-555-0142' }, w.env);
          assert.strictEqual(got.value, '(919) 555-0142');
          assert.ok(got.next.includes('(919) 555-0142'));
          assert.ok(!got.next.includes('919-555-0142'));
        """)

    def test_a_secret_is_still_refused_and_a_failed_hop_is_the_slow_answer(self):
        self.check(r"""
          let w = world();
          const bad = await run('fill_field', { field: 'Gemini key', value: 'AIza-secret' }, w.env);
          assert.strictEqual(bad.ok, false);
          assert.ok(!JSON.stringify(w.doc.byId).includes('AIza-secret'));
          w = world({ stuck: true });
          const slow = await run('fill_field', { field: 'phone', value: '919-555-0142' }, w.env);
          assert.strictEqual(slow.ok, false);
          assert.ok(!w.doc.byId['bf-phone'].value);
          w = world();
          w.env.openDeep = () => false;
          const no = await run('fill_field', { field: 'phone', value: '919-555-0142' }, w.env);
          assert.strictEqual(no.ok, false);
          assert.strictEqual(no.say, "That didn't open just now.");
        """)

    def test_d12_the_field_id_from_look_reaches_the_form(self):
        self.check(r"""
          const w = world();
          const seen = await run('look_at_screen', {}, w.env);
          const ids = seen.fields.map(f => f.field);
          assert.ok(ids.includes('bc-phone'));
          const got = await run('fill_field', { field: 'bc-phone', value: '919-555-0142' }, w.env);
          assert.strictEqual(w.doc.byId['bf-phone'].value, '919-555-0142');
          assert.strictEqual(got.ok, true);
          assert.strictEqual(got.saved, false);
          for (const id of ids) {   // every id look gave her lands somewhere
            const x = await run('fill_field', { field: id, value: id === 'bc-email' ? 'a@b.com' : 'x' }, world().env);
            assert.notStrictEqual(x.say, "That's not something I can do on this screen.", id);
          }
        """)

    def test_every_label_and_new_word_lands_in_the_right_box(self):
        self.check(r"""
          const cases = [['Name', 'name'], ['Relationship', 'relationship'], ['Email', 'email'], ['Home phone', 'phone'],
            ['Cell phone', 'cell'], ['Mailing address', 'address'], ['Facebook', 'facebook'], ['Birthday', 'birthday'],
            ['Notes', 'notes'], ['telephone number', 'phone'], ['home number', 'phone'], ['home phone number', 'phone'],
            ['landline', 'phone'], ['cell phone', 'cell'], ['cell phone number', 'cell'], ['cell number', 'cell'],
            ['mobile number', 'cell'], ['address', 'address'], ['mailing', 'address'], ['street address', 'address'],
            ['home address', 'address'], ['mail address', 'address'], ['e-mail', 'email'], ['email address', 'email'],
            ['e-mail address', 'email'], ['date of birth', 'birthday'], ['birth date', 'birthday'], ['bday', 'birthday'],
            ['facebook name', 'facebook'], ['note', 'notes'], ["Sarah's phone", 'phone'], ['her cell', 'cell']];
          for (const c of cases) {
            for (const on of ['card', 'form']) {
              const w = world();
              if (on === 'form') { await run('open_screen', { name: 'book-form', who: 'Sarah' }, w.env); }
              const val = c[1] === 'email' ? 'a@b.com' : (c[1] === 'birthday' ? 'May 5' : 'v-' + c[1]);
              const got = await run('fill_field', { field: c[0], value: val }, w.env);
              assert.strictEqual(got.ok, true, c[0] + ' ' + on + ' ' + JSON.stringify(got));
              assert.ok(w.doc.byId['bf-' + c[1]].value, c[0] + ' ' + on);
              assert.strictEqual(got.saved, false);
            }
          }
        """)

    def test_fill_with_who_opens_their_form_from_your_own_screen(self):
        self.check(r"""
          const w = world();
          w.doc.byId['book-card'].hidden = true;
          w.doc.defaultView.location.hash = '';
          const got = await run('fill_field', { field: "Sarah's phone", who: 'Sarah', value: '919-555-0142' }, w.env);
          assert.deepStrictEqual(w.opened, ['#book-form/p1']);
          assert.strictEqual(w.doc.byId['bf-phone'].value, '919-555-0142');
          assert.strictEqual(got.ok, true);
          assert.strictEqual(got.saved, false);
          Object.keys(w.doc.byId).forEach(k => assert.ok(!(w.doc.byId[k].events || []).includes('click'), k));
        """)

    def test_two_people_found_fills_nothing_and_asks_which(self):
        self.check(r"""
          const w = world();
          w.doc.byId['book-card'].hidden = true;
          w.doc.byId['book-list'] = mk('book-list', { hidden: true });
          w.env.findPeople = () => Promise.resolve({ state: 'open', people: [
            { id: 'p1', name: 'Sarah Whitfield', relationship: 'daughter' }, { id: 'p2', name: 'Sarah Cole', relationship: 'friend' }] });
          w.env.openDeep = h => { w.opened.push(h); w.doc.byId['book-list'].hidden = h.indexOf('#book-list') !== 0; return true; };
          const got = await run('fill_field', { field: 'phone', who: 'Sarah', value: '919-555-0142' }, w.env);
          assert.ok(!w.doc.byId['bf-phone'].value);
          assert.ok(JSON.stringify(got).includes('Two Sarahs'), JSON.stringify(got));
        """)

    def test_a_detail_word_with_no_who_on_another_screen_asks_whose(self):
        self.check(r"""
          const w = world();
          w.doc.byId['book-card'].hidden = true;
          for (const word of ['phone', 'cell', 'address', 'birthday']) {
            const got = await run('fill_field', { field: word, value: '1' }, w.env);
            assert.strictEqual(got.ok, false);
            assert.strictEqual(got.say, "Tell me whose it is and I'll open their form.", word);
          }
          const other = await run('fill_field', { field: 'banana', value: '1' }, w.env);
          assert.strictEqual(other.say, "That's not something I can do on this screen.");
        """)


if __name__ == "__main__":
    unittest.main()
