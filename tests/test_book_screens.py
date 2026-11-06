from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M19 piece 5, the address book's screens: the routes, Andy's rule that what you can ask Mary needs no button, the text
and target sizes by the CSS, and Node with a fake page for web/book.js and the detail kind in web/mary/screens.js."""
import json
import re
import unittest
from pathlib import Path

import address_book
import server
from tests.test_m18_frame import read, run_node
from tests.test_m18_screens import HARNESS

api = helpers.api
ROOT = Path(__file__).resolve().parent.parent
PEOPLE_BODY = {"name": "Sarah Whitfield", "relationship": "daughter", "email": "sarah@example.com", "cell": "919-555-0142",
               "birthday": "March 14", "notes": "Works nights."}


def section(html, sid):
    """One <section>, without its comments."""
    found = re.search(r'<section id="%s".*?</section>' % sid, html, re.S)
    return re.sub(r"<!--.*?-->", "", found.group(0), flags=re.S)


def words(markup):
    return " ".join(re.sub(r"<svg.*?</svg>|<[^>]+>", " ", markup, flags=re.S).split())


class BookRouteTests(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()

    def add(self, **more):
        status, body, _ = api("POST", "/api/book", {**PEOPLE_BODY, **more})
        self.assertEqual(status, 201, body)
        return body

    def test_writes_need_x_tracker_and_every_route_a_good_host(self):
        self.assertEqual(api("POST", "/api/book", {"name": "Ann"}, tracker=False)[0], 403)
        self.assertEqual(api("PUT", "/api/book/" + "a" * 32, {"name": "Ann"}, tracker=False)[0], 403)
        self.assertEqual(api("GET", "/api/book", host="evil.example")[0], 403)
        self.assertEqual(api("GET", "/api/book/" + "a" * 32, host="evil.example")[0], 403)
        self.assertEqual(api("POST", "/api/book", {"name": "Ann"}, host="evil.example")[0], 403)
        self.assertEqual(server.BOOK.count(), 0)

    def test_there_is_no_delete_route(self):
        card = self.add()
        status, _, _ = api("DELETE", "/api/book/" + card["id"])
        self.assertEqual(status, 404)
        self.assertEqual(server.BOOK.count(), 1)

    def test_list_has_no_details_and_leaves_out_hidden_and_doctors(self):
        card = self.add()
        server.BOOK.add({"name": "Dr. Helen Lee", "kind": "doctor", "email": "lee@example.com"})
        server.BOOK.add({"name": "Tom", "hidden": True, "no_keep": True})
        status, got, _ = api("GET", "/api/book")
        self.assertEqual(status, 200)
        self.assertEqual(got, {"state": "open", "why": "", "count": 1,
                               "people": [{"id": card["id"], "name": "Sarah Whitfield", "relationship": "daughter"}]})

    def test_card_has_the_fields_and_none_of_the_marks(self):
        card = self.add()
        status, got, _ = api("GET", "/api/book/" + card["id"])
        self.assertEqual(status, 200)
        self.assertEqual(got["email"], "sarah@example.com")
        self.assertEqual(got["cell"], "919-555-0142")
        self.assertEqual(got["birthday"], "03-14")
        self.assertEqual(got["birthday_words"], "March 14")
        self.assertEqual(got["them"], "her")
        for mark in ("kind", "asked", "no_keep", "hidden"):
            self.assertNotIn(mark, got)

    def test_a_hidden_mark_or_a_doctor_has_no_card(self):
        for fields in ({"name": "Tom", "hidden": True}, {"name": "Dr. Lee", "kind": "doctor"}):
            row = server.BOOK.add(fields)
            self.assertEqual(api("GET", "/api/book/" + row)[0], 404)
            self.assertEqual(api("PUT", "/api/book/" + row, {"notes": "x"})[0], 404)

    def test_the_page_cant_set_the_marks(self):
        card = self.add(hidden=True, kind="doctor", no_keep=True)
        person = server.BOOK.get(card["id"])
        self.assertEqual((person["hidden"], person["kind"], person["no_keep"]), (False, "person", False))
        api("PUT", "/api/book/" + card["id"], {"hidden": True, "asked": True})
        self.assertFalse(server.BOOK.get(card["id"])["hidden"])

    def test_change_keeps_what_it_wasnt_given(self):
        card = self.add()
        status, got, _ = api("PUT", "/api/book/" + card["id"], {"cell": "919-555-0188"})
        self.assertEqual(status, 200)
        self.assertEqual((got["cell"], got["email"]), ("919-555-0188", "sarah@example.com"))

    def test_locked_answers_locked_and_refuses_writes_and_wipes_nothing(self):
        card = self.add()
        before = server.BOOK.path.read_bytes()
        server.BOOK.lock()
        server.SECRETS.delete(address_book.KEY_NAME)
        status, got, _ = api("GET", "/api/book")
        self.assertEqual(status, 200)
        self.assertEqual((got["state"], got["why"], got["people"], got["count"]), ("locked", "key", [], 0))
        self.assertEqual(api("GET", "/api/book/" + card["id"])[1]["state"], "locked")
        for method, path in (("POST", "/api/book"), ("PUT", "/api/book/" + card["id"])):
            status, got, _ = api(method, path, {"name": "Ann"})
            self.assertEqual(status, 409)
            self.assertEqual(got["code"], "locked")
            self.assertEqual(got["error"], "Your address book is locked. A helper's copy can open it.")
        self.assertEqual(server.BOOK.path.read_bytes(), before)

    def test_same_exact_name_is_refused_and_not_added(self):
        self.add()
        status, got, _ = api("POST", "/api/book", {"name": "sarah  whitfield"})
        self.assertEqual((status, got["code"]), (409, "same_name"))
        self.assertEqual(server.BOOK.count(), 1)

    def test_changing_to_someone_elses_name_is_refused_but_ones_own_stands(self):
        card = self.add()
        other = server.BOOK.add({"name": "Sarah Beck"})
        self.assertEqual(api("PUT", "/api/book/" + other, {"name": "Sarah Whitfield"})[1]["code"], "same_name")
        self.assertEqual(api("PUT", "/api/book/" + card["id"], {"name": "Sarah Whitfield", "notes": "x"})[0], 200)

    def test_a_hidden_mark_doesnt_take_a_name(self):
        server.BOOK.add({"name": "Tom", "hidden": True})
        self.assertEqual(api("POST", "/api/book", {"name": "Tom"})[0], 201)

    def test_full_is_a_plain_line(self):
        real, address_book.MAX_PEOPLE = address_book.MAX_PEOPLE, 1
        self.addCleanup(setattr, address_book, "MAX_PEOPLE", real)
        self.add()
        status, got, _ = api("POST", "/api/book", {"name": "Ann"})
        self.assertEqual((status, got["code"], got["error"]), (409, "full", "Your address book is full."))

    def test_a_name_is_needed(self):
        self.assertEqual(api("POST", "/api/book", {"name": "   "})[1]["code"], "name")
        card = self.add()
        self.assertEqual(api("PUT", "/api/book/" + card["id"], {"name": ""})[1]["code"], "name")
        self.assertEqual(server.BOOK.get(card["id"])["name"], "Sarah Whitfield")

    def test_a_bad_birthday_gets_a_plain_message_and_nothing_vanishes(self):
        for bad in ("soon", "13/45", "February 30", "March"):
            status, got, _ = api("POST", "/api/book", {"name": "Ann", "birthday": bad})
            self.assertEqual((status, got["code"]), (400, "birthday"), bad)
            self.assertIn("March 14", got["error"])
        self.assertEqual(server.BOOK.count(), 0)
        card = self.add()
        self.assertEqual(api("PUT", "/api/book/" + card["id"], {"birthday": "soon", "notes": "new"})[1]["code"], "birthday")
        person = server.BOOK.get(card["id"])
        self.assertEqual((person["birthday"], person["notes"]), ("03-14", "Works nights."))

    def test_plain_birthdays_store_month_and_day(self):
        for typed, stored in (("March 14", "03-14"), ("3/14", "03-14"), ("03-14", "03-14"), ("mar 14th", "03-14"),
                              ("June 3", "06-03"), ("2/29", "02-29")):
            self.assertEqual(server.book_birthday(typed), stored, typed)

    def test_the_same_day_keeps_a_known_year_and_blank_clears(self):
        self.assertEqual(server.book_birthday("March 14", "1950-03-14"), "1950-03-14")
        self.assertEqual(server.book_birthday("March 15", "1950-03-14"), "03-15")
        self.assertEqual(server.book_birthday("  ", "03-14"), "")

    def test_the_stop_word_follows_the_relationship(self):
        for rel, word in (("daughter", "her"), ("Your son", "him"), ("Friend from church", "them"), ("pastor", "them"),
                          ("", "them"), ("sister-in-law", "her"), ("son's wife", "them")):
            self.assertEqual(server.book_them(rel), word, rel)

    def test_the_book_holds_no_log_connection_and_details_stay_out_of_the_log(self):
        self.add()
        self.assertNotIn(b"sarah@example.com", server.DB_PATH.read_bytes())
        self.assertNotIn(b"sarah@example.com", server.BOOK.path.read_bytes())


class BuiltPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read("index.html")
        cls.list = section(cls.html, "book-list")
        cls.card = section(cls.html, "book-card")
        cls.form = section(cls.html, "book-form")
        cls.script = re.sub(r"(?m)^\s*//.*$|\s//\s.*$", "", read("book.js"))
        cls.strings = " ".join(re.findall(r"""'[^'\n]*'|"[^"\n]*"|`[^`\n]*`""", cls.script))
        cls.everything = cls.list + cls.card + cls.form + section(cls.html, "book-helper") + cls.strings

    def test_the_four_screens_are_in_the_frames_list(self):
        for sid in ("book-list", "book-card", "book-form", "book-helper"):
            self.assertIn('<section id="%s" class="screen book"' % sid, self.html)
            self.assertIn("'%s'" % sid, read("app.js"))

    def test_what_she_can_be_asked_has_no_button(self):
        for gone in ("Add someone", "Change", "Email ", "Make a card", "Forget", "Put it back", "Not yet", "My doctors",
                     "Yes,"):
            self.assertNotIn(gone, self.everything, gone)
        self.assertNotIn("All people", self.card)
        self.assertNotIn("All doctors", self.everything)

    def test_the_form_has_all_people_save_and_the_helpers_two(self):
        self.assertIn(">All people<", self.form)
        self.assertIn(">Save<", self.form)
        self.assertIn(">Done<", self.form)
        self.assertIn("Save and add another", self.script)
        self.assertIn("added today", self.script)

    def test_the_card_has_no_button_but_the_stop_button(self):
        self.assertEqual(re.findall(r'id="(\w+)"[^>]*></button>|<button[^>]*id="(\w+)"', self.card), [("", "bookStop")])

    def test_the_extra_line_is_there(self):
        self.assertIn("If you need to scroll down, let me know.", words(self.list))

    def test_the_list_keeps_up_and_down_and_the_lock_line(self):
        self.assertIn(">Up<", self.list)
        self.assertIn(">Down<", self.list)
        self.assertIn("Kept only on this laptop, locked.", self.list)
        self.assertIn("Show everyone", self.list)

    def test_nothing_says_gone(self):
        self.assertNotRegex(words(self.list + self.card + self.form), r"(?i)\bgone\b")
        self.assertNotRegex(self.strings, r"(?i)\bgone\b")

    def test_the_menu_opens_the_list(self):
        page = read("mary.html")
        self.assertRegex(page, r'id="miBook"[^>]*data-act="book".*?Address book</button>')
        self.assertIn("act === 'book'", read("mary/app.js"))
        self.assertIn("openDeep('#book-list')", read("mary/app.js"))

    def test_the_look_before_sending_has_no_not_yet_and_keeps_undo(self):
        skill = (ROOT / "skills" / "messages" / "screen.js").read_text(encoding="utf-8")
        self.assertNotIn("Not yet", skill)
        self.assertIn("'Send it'", skill)
        self.assertIn("'Undo'", skill)

    def test_text_is_20px_or_larger_and_targets_64px_or_larger(self):
        css = read("styles.css")
        block = css[css.index("/* M19 piece 5"):css.index("/* /M19 piece 5 */")]
        sizes = [int(n) for n in re.findall(r"font:\d*\s*(\d+)px", block)] + [int(n) for n in re.findall(r"font-size:(\d+)px", block)]
        self.assertGreater(len(sizes), 15)
        self.assertGreaterEqual(min(sizes), 20)
        for rule in re.findall(r"(\.book-(?:rowbtn|btn|find)|\.book-in)\{([^}]*)\}", block):
            self.assertGreaterEqual(int(re.search(r"(?:^|;)height:(\d+)px", rule[1]).group(1)), 64, rule[0])
        self.assertIn("height:84px", re.search(r"\.book-rowbtn\{[^}]*\}", block).group(0))
        self.assertIn("min-height:72px", re.search(r"\.book-btn\{[^}]*\}", block).group(0))


# A fake page: $ makes any element it's asked for, and every one remembers what was done to it.
BOOK_HARNESS = r"""
globalThis.window = globalThis;
const assert = require('assert');
window.innerHeight = 682;   // M18b piece 4: 644 plus the 38px the way-in line takes, so a page is still 5 rows
window.addEventListener = function () {};
const els = {};
function el(sel) {
  return { sel, hidden: false, disabled: false, value: '', textContent: '', kids: [], on: {}, className: '',
    classList: { toggle() {} }, append(...k) { this.kids.push(...k); },
    replaceChildren(...k) { this.kids = k; }, addEventListener(t, f) { this.on[t] = f; }, focus() {} };
}
const $ = s => (els[s] = els[s] || el(s));
const document = { createElement: () => el('new') };
let hash = '';
const location = { get hash() { return hash; } };
const replies = {};
const api = async (path, o) => {
  const r = replies[(o && o.method || 'GET') + ' ' + path];
  if (r instanceof Error) { throw r; }
  return r;
};
const go = n => { hash = '#' + n; };
const told = [];
const toMary = w => told.push(w);
const unlit = () => {};
let cur = {};
const shown = [];
const showScreen = n => shown.push(n);
const isoDate = () => '2026-11-01';
const PEOPLE = n => Array.from({ length: n }, (_, i) => ({ id: 'p' + i, name: 'Person ' + i, relationship: 'friend', email: 'x@example.com' }));
"""


def book_node(body):
    code = BOOK_HARNESS + read("book.js") + "\n(async function () {\nbookInit();\n" + body + "\nconsole.log('ok');\n})().catch(function (e) { console.error(e); process.exit(1); });"
    return run_node(code)


class BookScriptTests(unittest.TestCase):
    def check(self, body):
        rc, _, err = book_node(body)
        self.assertEqual(rc, 0, err)

    def test_locked_shows_the_one_line_and_nothing_else(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'locked', why: 'key', people: [], count: 0 };
          await bookShowList();
          assert.strictEqual($('#bookShut').hidden, false);
          assert.strictEqual($('#bookShut').textContent, "Your address book is locked. A helper's copy can open it.");
          assert.strictEqual($('#bookOpen').hidden, true);
          assert.strictEqual($('#bookListBar').hidden, true);   // so no lock line
        """)

    def test_a_failed_load_says_so_and_shows_no_list(self):
        self.check(r"""
          replies['GET /api/book'] = new Error('no');
          await bookShowList();
          assert.strictEqual($('#bookShut').textContent, "Your address book didn't open just now.");
          assert.strictEqual($('#bookOpen').hidden, true);
          assert.strictEqual($('#bookListBar').hidden, true);
        """)

    def test_open_shows_the_lock_line_the_count_and_a_page_of_rows(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'open', people: PEOPLE(9), count: 9 };
          await bookShowList();
          assert.strictEqual($('#bookListBar').hidden, false);
          assert.strictEqual($('#bookCount').textContent, '9 people');
          assert.strictEqual($('#bookRows').kids.length, 5);
          assert.strictEqual($('#bookUp').disabled, true);
          assert.strictEqual($('#bookDown').disabled, false);
          assert.strictEqual($('#bookEveryone').hidden, true);
          $('#bookDown').on.click();
          assert.strictEqual($('#bookRows').kids[0].kids[0].textContent, 'Person 4');   // the last full page
          assert.strictEqual($('#bookRows').kids.length, 5);
          assert.strictEqual($('#bookDown').disabled, true);
          $('#bookUp').on.click();
          assert.strictEqual($('#bookRows').kids[0].kids[0].textContent, 'Person 0');
          $('#bookRows').kids[1].on.click();
          assert.strictEqual(hash, '#book-card/p1');
        """)

    def test_an_empty_book_says_so_kindly_and_stays_open(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'open', people: [], count: 0 };
          await bookShowList();
          assert.strictEqual($('#bookNone').textContent, 'No one in your address book yet.');
          assert.strictEqual($('#bookListBar').hidden, false);
        """)

    def test_find_narrows_and_show_everyone_comes_back(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'open', count: 3, people: [
            { id: 'a', name: 'Sarah Whitfield', relationship: 'daughter' }, { id: 'b', name: 'Tom', relationship: 'son' },
            { id: 'c', name: 'Sarah Beck', relationship: 'friend' }] };
          await bookShowList();
          $('#bookFind').value = 'sar';
          $('#bookFind').on.input();
          assert.strictEqual($('#bookRows').kids.length, 2);
          assert.strictEqual($('#bookCount').textContent, '2 of 3');
          assert.strictEqual($('#bookEveryone').hidden, false);
          assert.strictEqual($('#bookRows').kids[0].className, 'book-rowbtn lit');
          $('#bookFind').value = 'daughter';
          $('#bookFind').on.input();
          assert.strictEqual($('#bookRows').kids.length, 1);
          $('#bookEveryone').on.click();
          assert.strictEqual($('#bookFind').value, '');
          assert.strictEqual($('#bookRows').kids.length, 3);
          assert.strictEqual($('#bookEveryone').hidden, true);
        """)

    def test_list_now_gives_names_and_relationships_only(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'open', people: PEOPLE(2), count: 2 };
          await bookShowList();
          const now = window.maryBook.listNow();
          assert.deepStrictEqual(now, { state: 'open', count: 2, people: [
            { name: 'Person 0', relationship: 'friend' }, { name: 'Person 1', relationship: 'friend' }] });
        """)

    def test_the_form_modes_show_the_right_buttons(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'open', people: [], count: 0 };
          replies['GET /api/book/p1'] = { state: 'open', id: 'p1', name: 'Sarah', birthday: '03-14', birthday_words: 'March 14' };
          await bookShowForm('', false);
          assert.strictEqual($('#bookAll').hidden, false);
          assert.strictEqual($('#bookDone').hidden, true);
          assert.strictEqual($('#bookSave').textContent, 'Save');
          await bookShowForm('p1', false);
          assert.strictEqual($('#bookAll').hidden, true);        // E1: the form on that person with Save
          assert.strictEqual($('#bf-name').value, 'Sarah');
          assert.strictEqual($('#bf-birthday').value, 'March 14');
          await bookShowForm('', true);
          assert.strictEqual($('#bookAll').hidden, true);
          assert.strictEqual($('#bookDone').hidden, false);
          assert.strictEqual($('#bookSave').textContent, 'Save and add another');
          assert.strictEqual($('#bf-name').value, '');
        """)

    def test_saved_shows_beside_save_and_a_second_save_changes_not_adds(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'open', people: [], count: 0 };
          replies['POST /api/book'] = { state: 'open', id: 'p1', name: 'Sarah', birthday: '03-14', birthday_words: 'March 14' };
          replies['PUT /api/book/p1'] = { state: 'open', id: 'p1', name: 'Sarah' };
          await bookShowForm('', false);
          $('#bf-name').value = 'Sarah';
          $('#bf-birthday').value = '3/14';
          assert.strictEqual(await bookSave(), true);
          assert.strictEqual($('#bookSaved').hidden, false);
          assert.strictEqual($('#bf-birthday').value, 'March 14');
          replies['POST /api/book'] = new Error('would add twice');
          assert.strictEqual(await bookSave(), true);
        """)

    def test_a_refusal_stays_on_the_form_and_nothing_typed_is_lost(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'open', people: [], count: 0 };
          replies['POST /api/book'] = Object.assign(new Error("I can't read that birthday. Try March 14 or 3/14."), { code: 'birthday', status: 400 });
          await bookShowForm('', false);
          $('#bf-name').value = 'Sarah';
          $('#bf-birthday').value = 'soon';
          assert.strictEqual(await bookSave(), false);
          assert.strictEqual($('#bookMsg').textContent, "I can't read that birthday. Try March 14 or 3/14.");
          assert.strictEqual($('#bookMsg').hidden, false);
          assert.strictEqual($('#bookSaved').hidden, true);
          assert.strictEqual($('#bf-name').value, 'Sarah');
          assert.strictEqual($('#bf-birthday').value, 'soon');
        """)

    def test_a_locked_form_shows_only_the_line(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'locked', people: [], count: 0 };
          await bookShowForm('', false);
          assert.strictEqual($('#bookFormShut').textContent, "Your address book is locked. A helper's copy can open it.");
          assert.strictEqual($('#bookFormBody').hidden, true);
          assert.strictEqual($('#bookFormBar').hidden, true);
        """)

    def test_helper_counts_and_clears_and_done_goes_to_the_list(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'open', people: [], count: 0 };
          replies['POST /api/book'] = { state: 'open', id: 'p1' };
          await bookShowForm('', true);
          assert.strictEqual($('#bookAdded').hidden, true);
          for (const n of ['A', 'B', 'C']) { $('#bf-name').value = n; await bookSave(); }
          assert.strictEqual($('#bookAdded').textContent, '3 added today');
          assert.strictEqual($('#bf-name').value, '');
          await $('#bookDone').on.click();
          assert.strictEqual(hash, '#book-list');
        """)

    def test_done_with_a_person_half_typed_saves_or_stays(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'open', people: [], count: 0 };
          replies['POST /api/book'] = Object.assign(new Error('A name is needed.'), { code: 'name', status: 400 });
          await bookShowForm('', true);
          $('#bf-notes').value = 'half';
          await $('#bookDone').on.click();
          assert.strictEqual(hash, '');
          assert.strictEqual($('#bookMsg').textContent, 'A name is needed.');
          assert.strictEqual($('#bf-notes').value, 'half');
        """)

    def test_half_typed_add_comes_back(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'open', people: [], count: 0 };
          await bookShowForm('', false);
          $('#bf-name').value = 'Sarah';
          await bookShowList();
          await bookShowForm('', false);
          assert.strictEqual($('#bf-name').value, 'Sarah');
        """)

    def test_forget_ask_shows_the_card_with_its_one_stop_button(self):
        self.check(r"""
          replies['GET /api/book/p1'] = { state: 'open', id: 'p1', name: 'Sarah Beck', relationship: 'Friend from church', them: 'them', birthday_words: '' };
          await bookShowCard('p1');
          assert.strictEqual($('#bookStopBar').hidden, true);     // a plain card has no buttons at all
          hash = '#book-card/p1';
          await window.maryBook.forgetAsk('p1');
          assert.strictEqual($('#bookStopBar').hidden, false);
          assert.strictEqual($('#bookStop').textContent, 'No, keep them');
          $('#bookStop').on.click();
          assert.strictEqual($('#bookStopBar').hidden, true);
          assert.deepStrictEqual(told, ['book_keep']);
        """)

    def test_forget_ask_by_route_keeps_the_stop_button_and_leaving_drops_it(self):
        self.check(r"""
          replies['GET /api/book/p1'] = { state: 'open', id: 'p1', name: 'Tom', them: 'him', birthday_words: '' };
          replies['GET /api/book'] = { state: 'open', people: [], count: 0 };
          window.maryBook.forgetAsk('p1');
          assert.strictEqual(hash, '#book-card/p1');
          assert.strictEqual(bookRoute('book-card', 'p1'), true);
          await new Promise(r => setTimeout(r, 5));
          assert.strictEqual($('#bookStop').textContent, 'No, keep him');
          assert.strictEqual($('#bookStopBar').hidden, false);
          bookRoute('book-list', '');
          bookRoute('book-card', 'p1');
          await new Promise(r => setTimeout(r, 5));
          assert.strictEqual($('#bookStopBar').hidden, true);
          assert.strictEqual(bookRoute('home', ''), false);
        """)

    def test_after_forget_shows_the_list_at_its_end(self):
        self.check(r"""
          replies['GET /api/book'] = { state: 'open', people: PEOPLE(8), count: 8 };
          hash = '#book-list';
          await window.maryBook.afterForget();
          assert.strictEqual($('#bookCount').textContent, '8 people');
          assert.strictEqual($('#bookRows').kids[0].kids[0].textContent, 'Person 3');
          assert.strictEqual($('#bookDown').disabled, true);
        """)


def screens_node(body):
    code = HARNESS + read("mary/screens.js") + "\n(async function () {\n" + body + "\nconsole.log('ok');\n})().catch(function (e) { console.error(e); process.exit(1); });"
    return run_node(code)


SECRET_VALUE = "sarah.secret@example.com"


class DetailKindTests(unittest.TestCase):
    def check(self, body):
        rc, _, err = screens_node(body)
        self.assertEqual(rc, 0, err)

    def test_every_book_field_is_a_detail_and_only_a_form_can_be_filled(self):
        rc, out, err = run_node(HARNESS + read("mary/screens.js") + "\nconsole.log(JSON.stringify(MaryScreens.LIST));")
        self.assertEqual(rc, 0, err)
        screens = {s["id"]: s for s in json.loads(out)}
        for sid in ("book-card", "book-form", "book-helper"):
            fields = screens[sid]["fields"]
            self.assertEqual([f["id"].split("-")[1] for f in fields], ["name", "relationship", "email", "phone", "cell", "address",
                                                                      "facebook", "birthday", "notes"])
            for f in fields:
                self.assertEqual((f["kind"], f["fill"]), ("detail", sid != "book-card"), f["id"])  # M19 piece 6b
                self.assertTrue(f["label"] and f["explain"])
        self.assertEqual(screens["book-list"]["fields"], [])
        self.assertEqual(screens["book-form"]["fields"], screens["book-helper"]["fields"])

    def test_the_form_sends_no_value_through_look(self):
        self.check(r"""
          const doc = pageOn('none');
          doc.byId['book-form'] = mk('book-form');
          doc.byId['bf-email'].value = '%s';
          doc.byId['bf-name'].value = 'Sarah Whitfield';
          const got = await run('look_at_screen', {}, envOn(doc));
          assert.strictEqual(got.screen, 'Address book form');
          assert.strictEqual(got.fields.length, 9);
          assert.ok(!JSON.stringify(got).includes('sarah'));
          assert.ok(!JSON.stringify(got).includes('Whitfield'));
          got.fields.forEach(f => { assert.strictEqual(f.kind, 'detail'); assert.ok(!('value' in f)); assert.ok(!('filled' in f)); });
        """ % SECRET_VALUE)

    def test_the_card_says_only_which_fields_are_filled(self):
        self.check(r"""
          const doc = pageOn('none');
          doc.byId['book-card'] = mk('book-card');
          doc.byId['bc-email'].textContent = '%s';
          const got = await run('look_at_screen', {}, envOn(doc));
          assert.ok(!JSON.stringify(got).includes('secret'));
          const filled = got.fields.filter(f => f.filled).map(f => f.label);
          assert.deepStrictEqual(filled, ['Email']);
          got.fields.forEach(f => assert.ok(!('value' in f)));
        """ % SECRET_VALUE)

    def test_the_list_gives_names_and_relationships_only(self):
        self.check(r"""
          const doc = pageOn('none');
          doc.byId['book-list'] = mk('book-list');
          doc.defaultView.maryBook = { listNow() { return { state: 'open', count: 1, people: [
            { name: 'Sarah', relationship: 'daughter', email: '%s', id: 'x' }] }; } };
          const got = await run('look_at_screen', {}, envOn(doc));
          assert.deepStrictEqual(got.people, [{ name: 'Sarah', relationship: 'daughter' }]);
          assert.strictEqual(got.count, 1);
          assert.ok(!('fields' in got));
        """ % SECRET_VALUE)

    def test_a_locked_list_gives_no_people(self):
        self.check(r"""
          const doc = pageOn('none');
          doc.byId['book-list'] = mk('book-list');
          doc.defaultView.maryBook = { listNow() { return { state: 'locked' }; } };
          const got = await run('look_at_screen', {}, envOn(doc));
          assert.strictEqual(got.book, 'locked');
          assert.ok(!('people' in got));
        """)

    def test_what_she_fills_comes_back_in_look_and_nothing_else(self):
        self.check(r"""
          const doc = pageOn('none');
          doc.byId['book-form'] = mk('book-form');
          const yes = await run('fill_field', { field: 'Email', value: 'a@example.com' }, envOn(doc));
          assert.strictEqual(yes.ok, true);
          doc.byId['bf-cell'].value = '919-555-0142';
          let got = await run('look_at_screen', {}, envOn(doc));
          const by = l => got.fields.filter(x => x.label === l)[0];
          assert.strictEqual(by('Email').value, 'a@example.com');
          assert.ok(!('value' in by('Cell phone')));
          doc.byId['bf-email'].value = 'typed.over@example.com';
          got = await run('look_at_screen', {}, envOn(doc));
          assert.ok(!JSON.stringify(got).includes('typed.over'));
          MaryScreens.reset();
          doc.byId['bf-email'].value = 'a@example.com';
          got = await run('look_at_screen', {}, envOn(doc));
          assert.ok(!('value' in by('Email')));
        """)

    def test_a_card_cant_be_opened_without_who(self):
        self.check(r"""
          const got = await run('open_screen', { name: 'book-card' }, envOn(pageOn('none')));
          assert.strictEqual(got.ok, false);
          const opened = [];
          const yes = await run('open_screen', { name: 'book-helper' }, envOn(pageOn('none'), { openDeep(h) { opened.push(h); return false; } }));
          assert.deepStrictEqual(opened, ['#book-helper']);
          assert.strictEqual(yes.ok, false);
        """)


if __name__ == "__main__":
    unittest.main()
