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


if __name__ == "__main__":
    unittest.main()
