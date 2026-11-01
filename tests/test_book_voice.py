from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M19 piece 6b, Mary on the address book's screens in a Live talk: opening, look, filling, saving, forgetting, "Put that on
Mark's card?" and clearing the book. Python for what the server decides, Node with a fake page for the rules in the page code."""
import json
import re
import unittest
from pathlib import Path

import mary
import send_gate
import server
from tests.test_m18_band import slice_js
from tests.test_m18_frame import read, run_node
from tests.test_m18_screens import HARNESS

ROOT = Path(__file__).resolve().parent.parent
EMAIL, PHONE = "sarah.whitfield@example.com", "919-555-0142"

BOOK_PAGE = r"""
function bookDoc(frame, book) {
  const doc = pageOn(frame);
  ['book-list', 'book-card', 'book-form', 'book-helper'].forEach(f => { doc.byId[f] = mk(f, { hidden: f !== frame }); });
  doc.defaultView.maryBook = Object.assign({ narrowed: [], filledKeys: [], now: 1,
    listNow() { return { state: 'open', count: 0, people: [] }; },
    narrow(w) { this.narrowed.push(w); },
    cardNow() { return { name: 'Sarah Whitfield', relationship: 'daughter', email: 'sarah.whitfield@example.com' }; },
    form() { return this.now; },
    filled(k) { this.filledKeys.push(k); } }, book || {});
  return doc;
}
function bookEnv(doc, found, more) {
  const opened = [];
  return envOn(doc, Object.assign({ opened, findPeople: async () => found,
    openDeep(hash) {
      opened.push(hash);
      const to = hash.slice(1).split('/')[0];
      ['home', 'book-list', 'book-card', 'book-form', 'book-helper'].forEach(f => { doc.byId[f].hidden = f !== to; });
      return true;
    } }, more || {}));
}
const use = (a, env) => run('use_screen', a, env);
const SARAH = { id: '7', name: 'Sarah Whitfield', relationship: 'daughter' };
const BECK = { id: '9', name: 'Sarah Beck', relationship: 'friend from church' };
"""

# web/book.js on a fake page: only what its functions touch.
BOOK_JS = r"""
globalThis.window = globalThis;
const assert = require('assert');
const els = {};
function el(id) {
  if (!els[id]) {
    els[id] = { id, value: '', hidden: false, textContent: '', disabled: false, listeners: {},
      classList: { toggle() {}, add() {}, remove() {} }, addEventListener(t, f) { this.listeners[t] = f; }, append() {}, focus() {},
      after(x) { els[x.id] = x; }, replaceChildren() {}, requestSubmit() { this.listeners.submit({ preventDefault() {} }); } };
  }
  return els[id];
}
globalThis.$ = s => el(s.replace('#', ''));
globalThis.document = { createElement: () => el('new' + Object.keys(els).length) };
globalThis.location = { hash: '' };
globalThis.addEventListener = () => {};
globalThis.isoDate = () => '2026-11-01';
globalThis.innerHeight = 800;
globalThis.unlit = () => {};
globalThis.showScreen = () => {};
globalThis.cur = { screen: 'book-form' };
const told = [], gone = [];
let saves = 0, refuse = null, person = null;
globalThis.toMary = (what, more) => told.push({ what, ...more });
globalThis.go = hash => gone.push(hash);
globalThis.api = async (path, o) => {
  if (o && o.method) {
    saves++;
    if (refuse) { const e = new Error(refuse.message); e.code = refuse.code; throw e; }
    const sent = JSON.parse(o.body);
    return { ...sent, id: '7', birthday_words: sent.birthday, them: 'her', state: 'open' };
  }
  return person ? { ...person, state: 'open' } : { state: 'open' };
};
const later = () => new Promise(r => setTimeout(r, 5));
const last = () => told[told.length - 1];
"""


def node(body):
    code = (HARNESS + BOOK_PAGE + read("mary/screens.js") + "\n(async function () {\n" + body +
            "\nconsole.log('ok');\n})().catch(function (e) { console.error(e); process.exit(1); });")
    return run_node(code)


def node_book(body):
    code = (BOOK_JS + read("book.js") + "\n(async function () {\nbookInit();\n" + body +
            "\nconsole.log('ok');\n})().catch(function (e) { console.error(e); process.exit(1); });")
    return run_node(code)


def tool(name, args, heard=""):
    return helpers.api("POST", "/api/mary/skills/call", {"name": name, "args": args, "heard": heard})[1]


def heard(text):
    return helpers.api("POST", "/api/mary/heard", {"text": text})[1]


def she_said(text):
    return helpers.api("POST", "/api/mary/live/said", {"text": text})


class Book(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        server.BOOK.clear()
        server._birthday_ask = {}
        server.book_keep()  # a forget left waiting by the test before
        server.set_skill_host_for_tests(None)
        self.addCleanup(server.set_skill_host_for_tests, None)
        self.host = server.skill_host()

    def person(self, name, **fields):
        return server.BOOK.add({"name": name, **fields})

    def memories(self):
        return server.memory_store().count()

    def remember(self, text):
        with server._mary_lock:
            memory = server.mary_memory()
            memory.add_fact(text, "", "said")
            memory.save()


class OpeningByName(Book):
    def find(self, words):
        return helpers.api("POST", "/api/mary/book/find", {"words": words})[1]

    def test_one_match_gives_an_id_and_no_detail(self):
        person = self.person("Sarah Whitfield", relationship="daughter", email=EMAIL, phone=PHONE, notes="Takes her coffee black")
        got = self.find("Sarah")
        self.assertEqual(got, {"state": "open", "people": [{"id": person, "name": "Sarah Whitfield", "relationship": "daughter"}]})
        self.assertEqual([p["id"] for p in self.find("my daughter")["people"]], [person])

    def test_two_matches_and_none(self):
        self.person("Sarah Whitfield", relationship="daughter")
        self.person("Sarah Beck", relationship="friend from church")
        self.assertEqual(len(self.find("Sarah")["people"]), 2)
        self.assertEqual(self.find("Bartholomew")["people"], [])

    def test_a_doctor_stays_out_of_it(self):
        self.person("Dr. Helen Lee", kind="doctor", relationship="heart doctor")
        self.assertEqual(self.find("Dr. Helen Lee")["people"], [])

    def test_a_tool_alone_adds_nobody(self):
        out = self.host.call("messages__add_to_book", {}, heard="add Tom to my book")["response"]
        self.assertFalse(out["saved"])
        self.assertEqual(server.BOOK.count(), 0)


class OpeningOnThePage(unittest.TestCase):
    def check(self, body):
        rc, _, err = node(body)
        self.assertEqual(rc, 0, err)

    def test_one_match_opens_that_card_at_once(self):
        self.check(r"""
          const env = bookEnv(bookDoc('home'), { state: 'open', people: [SARAH] });
          const out = await use({ action: 'open', name: 'book-card', who: 'Sarah' }, env);
          assert.deepEqual(env.opened, ['#book-card/7']);
          assert.equal(out.ok, true);
          assert.match(out.note, /Here's Sarah\./);
          assert.equal(out.name, 'Sarah Whitfield');
        """)

    def test_two_matches_narrow_the_list_and_she_asks_by_relationship(self):
        self.check(r"""
          const doc = bookDoc('home'), env = bookEnv(doc, { state: 'open', people: [SARAH, BECK] });
          const out = await use({ action: 'open', name: 'book-list', who: 'Sarah' }, env);
          assert.deepEqual(env.opened, ['#book-list']);
          assert.deepEqual(doc.defaultView.maryBook.narrowed, ['Sarah']);
          assert.match(out.note, /"Two Sarahs\. Your daughter, or Sarah Beck from church\?"/);
        """)

    def test_none_says_so_and_opens_nothing(self):
        self.check(r"""
          const env = bookEnv(bookDoc('home'), { state: 'open', people: [] });
          const out = await use({ action: 'open', name: 'book-card', who: 'my nephew' }, env);
          assert.deepEqual(env.opened, []);
          assert.equal(out.ok, false);
          assert.equal(out.say, "I don't see your nephew in your address book.");
        """)

    def test_the_book_opens_and_she_asks_who(self):
        self.check(r"""
          for (const name of ['book-list', 'book-card']) {
            const env = bookEnv(bookDoc('home'), { state: 'open', people: [] });
            const out = await use({ action: 'open', name }, env);
            assert.deepEqual(env.opened, ['#book-list']);
            assert.match(out.note, /"Who are you after\?"/);
          }
        """)
        self.assertNotIn("Tell me who, and I'll find them.", read("mary/screens.js"))

    def test_a_change_opens_their_form_and_an_add_a_blank_one(self):
        self.check(r"""
          let env = bookEnv(bookDoc('home'), { state: 'open', people: [SARAH] });
          let out = await use({ action: 'open', name: 'book-form', who: 'Sarah' }, env);
          assert.deepEqual(env.opened, ['#book-form/7']);
          assert.equal(out.ok, true);
          env = bookEnv(bookDoc('home'), { state: 'open', people: [] });
          out = await use({ action: 'open', name: 'book-form' }, env);
          assert.deepEqual(env.opened, ['#book-form']);
          out = await use({ action: 'open', name: 'book-helper' }, env);
          assert.deepEqual(env.opened, ['#book-form', '#book-helper']);
          assert.match(out.note, /Ask if you need me\./);
        """)

    def test_a_locked_book_says_so(self):
        self.check(r"""
          const env = bookEnv(bookDoc('home'), { state: 'locked', people: [] });
          const out = await use({ action: 'open', name: 'book-card', who: 'Sarah' }, env);
          assert.equal(out.ok, false);
          assert.match(out.say, /locked/);
        """)

    def test_add_to_book_in_live_opens_the_blank_form(self):
        text = read("mary/app.js")
        self.assertIn("page.push({ id: fc.id, name: 'open_screen', args: { name: 'book-form' }, asked: fc.name });", text)
        self.assertIn("own.push({ id: fc.id, name: fc.asked || fc.name, response: res });", text)


class LookAndFill(unittest.TestCase):
    def check(self, body):
        rc, _, err = node(body)
        self.assertEqual(rc, 0, err)

    def test_a_card_says_whose_it_is_and_no_value(self):
        self.check(r"""
          const doc = bookDoc('book-card');
          doc.byId['bc-email'].textContent = 'sarah.whitfield@example.com';
          const out = await use({ action: 'look' }, bookEnv(doc));
          assert.deepEqual(out.person, { name: 'Sarah Whitfield', relationship: 'daughter' });
          assert.equal(out.fields.filter(f => f.filled).map(f => f.label).join(), 'Email');
          assert.ok(!JSON.stringify(out).includes('example.com'));
          assert.ok(out.fields.every(f => f.can_fill === false));
        """)

    def test_she_fills_a_form_and_never_a_card(self):
        self.check(r"""
          let doc = bookDoc('book-card'), out = await use({ action: 'fill', field: 'Email', value: 'a@b.co' }, bookEnv(doc));
          assert.equal(out.ok, false);
          for (const frame of ['book-form', 'book-helper']) {
            doc = bookDoc(frame);
            for (const label of ['Name', 'Relationship', 'Home phone', 'Cell phone', 'Mailing address', 'Facebook', 'Birthday', 'Notes']) {
              out = await use({ action: 'fill', field: label, value: 'June 3' }, bookEnv(doc));
              assert.equal(out.ok, true, label);
              assert.equal(out.saved, false);
              assert.match(out.next, /Is that right\?/);
            }
          }
        """)

    def test_the_email_keeps_m18s_rules(self):
        self.check(r"""
          const doc = bookDoc('book-form');
          let out = await use({ action: 'fill', field: 'Email', value: 'sarah at example dot com' }, bookEnv(doc));
          assert.equal(out.ok, false);
          assert.match(out.say, /Spell it back to them first/);
          assert.equal(doc.byId['bf-email'].value, '');
          out = await use({ action: 'fill', field: 'Email', value: 'sarah@example.com' }, bookEnv(doc));
          assert.match(out.next, /letter by letter/);
          assert.equal(doc.byId['bf-email'].value, 'sarah@example.com');
        """)

    def test_a_fill_never_gives_back_the_old_value(self):
        self.check(r"""
          const doc = bookDoc('book-form'), env = bookEnv(doc);
          doc.byId['bf-cell'].value = '919-555-0142';
          doc.byId['bf-phone'].value = '919-555-0100';
          let out = await use({ action: 'fill', field: 'Cell phone', value: '919-555-0188' }, env);
          assert.ok(!JSON.stringify(out).includes('0142'));
          assert.equal(doc.byId['bf-cell'].value, '919-555-0188');
          assert.deepEqual(doc.defaultView.maryBook.filledKeys, ['cell']);
          const look = await use({ action: 'look' }, env);
          assert.ok(!JSON.stringify(look).includes('0142'));
          assert.ok(!JSON.stringify(look).includes('0100'));
          assert.equal(look.fields.filter(f => 'value' in f).map(f => f.value).join(), '919-555-0188');
          out = await use({ action: 'put_back', field: 'Cell phone' }, env);
          assert.ok(!JSON.stringify(out).includes('0142'));
          assert.equal(doc.byId['bf-cell'].value, '919-555-0142');
        """)

    def test_another_persons_old_value_stays_out(self):
        self.check(r"""
          const doc = bookDoc('book-form'), env = bookEnv(doc);
          doc.byId['bf-cell'].value = '919-555-0142';
          await use({ action: 'fill', field: 'Cell phone', value: '919-555-0188' }, env);
          doc.defaultView.maryBook.now = 2;
          const out = await use({ action: 'put_back', field: 'Cell phone' }, env);
          assert.equal(out.ok, false);
          assert.equal(doc.byId['bf-cell'].value, '919-555-0188');
        """)


class TheFormPage(unittest.TestCase):
    def check(self, body):
        rc, _, err = node_book(body)
        self.assertEqual(rc, 0, err)

    def test_said_save_saves_once_and_tells_no_value(self):
        self.check(r"""
          await bookShowForm('', false);
          bookAskedSave();
          assert.deepEqual(last(), { what: 'save_none', why: 'nothing' });
          $('#bf-name').value = 'Tom Reed';
          $('#bf-birthday').value = 'March 3';
          bookAskedSave();
          bookAskedSave();
          await later();
          assert.equal(saves, 1);
          assert.deepEqual(last(), { what: 'saved_ok', form: 'book', birthday: true });
          assert.ok(!JSON.stringify(told).includes('Tom') && !JSON.stringify(told).includes('March'));
        """)

    def test_a_tap_saves_the_same_way(self):
        self.check(r"""
          await bookShowForm('', false);
          $('#bf-name').value = 'Tom Reed';
          $('#bookForm').listeners.submit({ preventDefault() {} });
          await later();
          assert.equal(saves, 1);
          assert.deepEqual(last(), { what: 'saved_ok', form: 'book', birthday: false });
        """)

    def test_a_refusal_stays_on_the_form(self):
        self.check(r"""
          await bookShowForm('', false);
          $('#bf-name').value = 'Tom Reed';
          refuse = { message: 'That name is already in your address book.', code: 'same_name' };
          bookAskedSave();
          await later();
          assert.deepEqual(last(), { what: 'saved_fail', why: 'same_name' });
          assert.equal($('#bf-name').value, 'Tom Reed');
          assert.equal(gone.length, 0);
          refuse = { message: "I can't read that birthday.", code: 'birthday' };
          bookAskedSave();
          await later();
          assert.deepEqual(last(), { what: 'saved_fail', why: 'birthday' });
        """)

    def test_the_was_line_shows_only_after_her_fill_on_a_saved_value(self):
        self.check(r"""
          person = { id: '7', name: 'Sarah', cell: '919-555-0142', birthday_words: '' };
          await bookShowForm('7', false);
          $('#bf-cell').value = '919-555-0188';
          $('#bookForm').listeners.input();
          assert.equal($('#bw-cell').hidden, true);   // their own typing
          maryBook.filled('cell');
          assert.equal($('#bw-cell').textContent, 'Was: 919-555-0142');
          assert.equal($('#bw-cell').hidden, false);
          $('#bf-cell').value = '919-555-0142';
          $('#bookForm').listeners.input();
          assert.equal($('#bw-cell').hidden, true);   // put back
          $('#bf-name').value = 'Ruth';
          maryBook.filled('name');
          assert.equal($('#bw-name').textContent, 'Was: Sarah');
          $('#bf-phone').value = '919-555-0100';
          maryBook.filled('phone');
          assert.equal($('#bw-phone').hidden, true);   // nothing was there before
        """)

    def test_a_card_tells_look_only_who(self):
        self.check(r"""
          person = { id: '7', name: 'Sarah', relationship: 'daughter', email: 'a@b.co', birthday_words: '', them: 'her' };
          await bookShowCard('7');
          assert.deepEqual(maryBook.cardNow(), { name: 'Sarah', relationship: 'daughter' });
        """)

    def test_the_stop_closes_to_the_list_and_tells_her(self):
        self.check(r"""
          maryBook.forgetAsk('7');
          assert.equal(maryBook.asking(), true);
          $('#bookStop').listeners.click();
          assert.equal(maryBook.asking(), false);
          assert.equal(gone[gone.length - 1], 'book-list');
          assert.deepEqual(last(), { what: 'book_keep' });
        """)

    def test_the_form_number_moves_with_each_person_and_save(self):
        self.check(r"""
          const first = maryBook.form();
          person = { id: '7', name: 'Sarah', birthday_words: '' };
          await bookShowForm('7', false);
          const second = maryBook.form();
          assert.notEqual(first, second);
          $('#bf-name').value = 'Ruth';
          bookAskedSave();
          await later();
          assert.notEqual(maryBook.form(), second);
        """)


class Saving(Book):
    def test_only_their_plain_save_counts(self):
        for line in ("yes", "that's right", "keep it", "Yes, that's right", "yes keep it"):
            self.assertFalse(send_gate.is_plain_save(line), line)
            self.assertNotIn("save", heard(line), line)
        self.assertTrue(send_gate.is_plain_save("save it"))
        self.assertTrue(heard("save it")["save"])

    def test_no_tool_can_press_save(self):
        rc, out, err = run_node(HARNESS + read("mary/screens.js") + "\nconsole.log(JSON.stringify(Object.keys(MaryScreens.ACTIONS)));")
        self.assertEqual(rc, 0, err)
        self.assertEqual(sorted(json.loads(out)), sorted(["look", "explain", "fill", "put_back", "open", "go_back", "their_words", "read_incidents"]))
        text = read("mary/screens.js")
        for word in ("bookSave", "bookAskedSave", "requestSubmit", "/api/book"):
            self.assertNotIn(word, text)

    def test_said_save_reaches_the_book_form_by_one_path(self):
        frame = read("app.js")
        self.assertIn("(cur.screen === 'book-form' || cur.screen === 'book-helper') bookAskedSave();", frame)
        self.assertIn("Deep.screen === 'book-form' || Deep.screen === 'book-helper'", read("mary/app.js"))
        hits = [line for line in read("mary/app.js").splitlines() if "deepPost({ what: 'save' })" in line]
        self.assertEqual(len(hits), 1)

    def test_her_saved_line_and_the_refusals(self):
        text = read("mary/app.js")
        self.assertIn("Saved. I'll mention the birthday when it's close.", text)
        self.assertIn("d.birthday ? SAVE_SAID.birthday : SAVE_SAID.ok", text)
        block = slice_js(text, "var BOOK_SAVE_NO = {", "};")
        for why in ("same_name", "birthday", "name"):
            self.assertIn(why + ": bookSaveNo(", block)


class Forgetting(Book):
    def ask(self, name):
        return tool("forget_memory", {"about": name}, heard=f"forget {name}")

    def yes(self, name, line="yes"):
        return tool("forget_memory", {"about": name, "confirmed": True}, heard=line)

    def setUp(self):
        super().setUp()
        self.sarah = self.person("Sarah Beck", relationship="friend from church")

    def test_the_ask_puts_up_the_card_and_nothing_goes(self):
        out = self.ask("Sarah Beck")
        self.assertTrue(out["response"]["needs_yes"])
        self.assertEqual(out["effects"], [{"kind": "book_ask", "data": {"id": self.sarah}}])
        self.assertEqual(server.BOOK.count(), 1)

    def test_with_no_yes_nothing_goes(self):
        self.ask("Sarah Beck")
        out = self.yes("Sarah Beck", "tell me about her instead")
        self.assertTrue(out["response"]["needs_yes"])
        self.assertEqual(server.BOOK.count(), 1)

    def test_a_yes_takes_them_out_and_says_so(self):
        self.ask("Sarah Beck")
        out = self.yes("Sarah Beck")
        self.assertEqual(server.BOOK.count(), 0)
        self.assertEqual(out["say"], "Done. Sarah Beck is out of your address book.")
        self.assertIn("Done. Sarah Beck is out of your address book.", out["response"]["note"])
        self.assertEqual(out["effects"], [{"kind": "book_out", "data": {}}])

    def test_the_stop_button_cancels(self):
        self.ask("Sarah Beck")
        status, got, _ = helpers.api("POST", "/api/mary/book/keep", {})
        self.assertEqual((status, got), (200, {"ok": True}))
        self.assertIsNone(server.mary_memory().pending_forget)
        self.yes("Sarah Beck")
        self.assertEqual(server.BOOK.count(), 1)

    def test_a_spoken_no_cancels(self):
        self.ask("Sarah Beck")
        self.assertTrue(heard("No, keep her")["forget_kept"])
        self.assertIsNone(server.mary_memory().pending_forget)
        self.yes("Sarah Beck")
        self.assertEqual(server.BOOK.count(), 1)

    def test_a_no_with_nothing_waiting_is_just_a_no(self):
        self.assertNotIn("forget_kept", heard("No thanks"))

    def test_the_page_follows(self):
        text = read("mary/app.js")
        self.assertIn("else if (d.what === 'book_keep') { bookKept(false); }", text)
        self.assertIn("if (j && j.forget_kept) { bookKept(true); }", text)
        self.assertIn("(They kept them. Say so in a few words.)", text)
        self.assertIn("b.forgetAsk(id);", text)
        self.assertIn("book.afterForget();", text)
        self.assertIn("if (a && a.bookEffect) { a.bookEffect(kind, data); }", read("mary/skills.js"))

    def test_her_lines_never_say_gone(self):
        for line in (mary.FORGET_OUT_TEXT, mary.FORGET_CLEARED_TEXT, mary.FORGET_BOOK_TEXT):
            self.assertNotIn("gone", line.lower())


class ClearingTheBook(Book):
    def setUp(self):
        super().setUp()
        self.person("Sarah Beck")
        self.person("Mark Hollis")
        self.remember("They like sweet tea")
        self.before = self.memories()

    def ask(self):
        return tool("forget_memory", {"about": "my address book"}, heard="clear my address book")

    def yes(self, line="yes"):
        return tool("forget_memory", {"about": "my address book", "confirmed": True}, heard=line)

    def test_what_counts(self):
        for words in ("my address book", "address book", "clear my address book", "take everyone out of my book",
                      "Take everyone out of my address book.", "empty my whole address book", "everyone in my book"):
            self.assertTrue(mary.whole_book(words), words)
        for words in ("everything", "my book", "the book I was reading", "my library book", "Sarah", "my address", ""):
            self.assertFalse(mary.whole_book(words), words)

    def test_it_asks_and_nothing_goes(self):
        out = self.ask()
        self.assertTrue(out["response"]["needs_yes"])
        self.assertIn("Clear your whole address book? Everyone in it comes out for good. Your memories stay.", out["response"]["note"])
        self.assertEqual(server.BOOK.count(), 2)

    def test_a_no_leaves_it(self):
        self.ask()
        heard("no")
        self.yes()
        self.assertEqual(server.BOOK.count(), 2)

    def test_it_takes_their_own_yes(self):
        self.ask()
        self.yes("clear my address book")
        self.assertEqual(server.BOOK.count(), 2)

    def test_a_yes_empties_it_says_how_many_and_keeps_her_memories(self):
        self.ask()
        out = self.yes()
        self.assertEqual(server.BOOK.count(), 0)
        self.assertEqual(self.memories(), self.before)
        self.assertEqual(out["say"], "Done. 2 people came out of your address book.")

    def test_forget_everything_never_reaches_it(self):
        tool("forget_memory", {"about": "everything"}, heard="forget everything")
        tool("forget_memory", {"about": "everything", "confirmed": True}, heard="yes")
        self.assertEqual(server.BOOK.count(), 2)

    def test_an_empty_book_has_nothing_to_ask(self):
        server.BOOK.clear()
        self.assertNotIn("needs_yes", self.ask()["response"])


class PutThatOnTheCard(Book):
    LINE = "Mark's birthday is March 3rd."

    def setUp(self):
        super().setUp()
        self.mark = self.person("Mark Hollis", relationship="son")

    def asked(self):
        return "book_note" in heard(self.LINE)

    def test_a_birthday_for_a_bare_card_starts_the_question(self):
        got = heard(self.LINE)
        self.assertIn("Put that on Mark's card?", got["book_note"])
        self.assertNotIn("asked_birthday", {k for k, v in server.BOOK.get(self.mark).items() if v})

    def test_a_yes_before_she_asked_opens_nothing(self):
        self.assertTrue(self.asked())
        self.assertNotIn("book_open", heard("yes"))

    def test_a_yes_opens_the_form_by_id_and_saves_nothing(self):
        self.assertTrue(self.asked())
        she_said("Put that on Mark's card?")
        got = heard("yes")["book_open"]
        self.assertEqual(got["id"], self.mark)
        self.assertNotIn("March", json.dumps(got))
        self.assertEqual(server.BOOK.get(self.mark)["birthday"], "")

    def test_once_per_person(self):
        self.assertTrue(self.asked())
        she_said("Put that on Mark's card?")
        self.assertTrue(server.BOOK.get(self.mark)["asked_birthday"])
        heard("yes")
        self.assertFalse(self.asked())

    def test_a_no_sets_the_mark_and_nothing_else(self):
        self.assertTrue(self.asked())
        she_said("Put that on Mark's card?")
        self.assertNotIn("book_open", heard("no"))
        person = server.BOOK.get(self.mark)
        self.assertTrue(person["asked_birthday"])
        self.assertEqual(person["birthday"], "")
        self.assertFalse(self.asked())

    def test_never_for_someone_who_has_passed(self):
        heard("My son Mark passed away last spring.")
        self.assertFalse(self.asked())

    def test_never_with_a_birthday_on_the_card(self):
        server.BOOK.update(self.mark, {"birthday": "03-03"})
        self.assertFalse(self.asked())

    def test_nobody_in_the_book(self):
        self.assertNotIn("book_note", heard("Lily's birthday is March 12."))

    def test_the_question_goes_with_the_talk(self):
        self.assertTrue(self.asked())
        she_said("Put that on Mark's card?")
        server.close_talk()
        self.assertNotIn("book_open", heard("yes"))

    def test_the_page_follows(self):
        text = read("mary/app.js")
        self.assertIn("if (j && j.book_note) { screenNote(String(j.book_note)); }", text)
        self.assertIn("if (j && j.book_open) { bookBirthday(j.book_open); }", text)


class ReadDetailIsTighter(Book):
    def read_one(self, heard_words, field):
        return self.host.call("messages__read_detail", {"person": "Sarah", "field": field}, heard=heard_words)["response"]

    def test_the_four_lines_are_refused(self):
        self.person("Sarah Whitfield", relationship="daughter", email=EMAIL, facebook="sarah.hollis.99")
        for words, field in (("Write to Sarah's email", "email"), ("use her Facebook", "facebook"),
                             ("I got Sarah's email yesterday", "email"), ("put Sarah's card on the table", "email")):
            out = self.read_one(words, field)
            self.assertTrue(out.get("not_asked"), words)
            self.assertNotIn("value", out, words)

    def test_a_real_ask_still_passes(self):
        self.person("Sarah Whitfield", relationship="daughter", email=EMAIL)
        for words in ("what's Sarah's email address", "put my daughter in the to box", "write her email in the box",
                      "have you got Sarah's email", "I need Sarah's email"):
            self.assertEqual(self.read_one(words, "email").get("value"), EMAIL, words)


class TheInstructions(unittest.TestCase):
    def test_the_block_is_the_same_in_all_three_and_the_old_line_left(self):
        full = mary.INSTRUCTIONS.read_text(encoding="utf-8")
        block = slice_js(full, '- Open the address book only when they ask', '- If they tell you someone\'s email address')
        for line in ('"Who are you after?"', "unless they ask for it", "leave Save to them", "There's no Add button"):
            self.assertIn(line, block)
        self.assertNotIn("in Address book, in the Menu", full)
        for name in ("lean-mary", "lean-sam"):
            text = (mary.INSTRUCTIONS.parent.parent / "bench" / "variants" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn(block, text, name)


class SamToo(unittest.TestCase):
    def test_his_page_uses_the_same_paths(self):
        text = read("mary/app.js")
        block = slice_js(text, "// M19 piece 6b: what her forget and her birthday question", "// ---------------------------------------------------------------- end M18")
        self.assertNotRegex(block, r"S\.companion|'sam'|'him'|'mary'")
        self.assertNotRegex(read("book.js"), r"S\.companion|companion\(")

    def test_his_lines_are_the_same_on_the_page(self):
        rc, _, err = node(r"""
          const env = bookEnv(bookDoc('home'), { state: 'open', people: [SARAH] }, { companion() { return 'sam'; } });
          const out = await use({ action: 'open', name: 'book-card', who: 'Sarah' }, env);
          assert.match(out.note, /Here's Sarah\./);
        """)
        self.assertEqual(rc, 0, err)

    def test_no_line_of_hers_names_her(self):
        for text in (read("mary/screens.js"), read("book.js")):
            self.assertIsNone(re.search(r"['\"][^'\"]*\bMary\b[^'\"]*Who are you after", text))


if __name__ == "__main__":
    unittest.main()
