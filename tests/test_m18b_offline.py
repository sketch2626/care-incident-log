from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M18b piece 3: with no model answer (no key, or the model failed) a few plain phrases still open and fill screens through
the page, and add a person. Python for what the server side decides (a fake page, never a real Gemini), Node with a fake page
for the one new rule in the page code: offline she fills only plain text and phone boxes."""
import subprocess
import unittest
from pathlib import Path

import mary
import server
from tests import test_tool_groups as groups
from tests.test_book_voice import BOOK_PAGE
from tests.test_m18_frame import NODE, read, run_node
from tests.test_m18_screens import HARNESS

ROOT = Path(__file__).resolve().parent.parent
KEY = "AIzaSyTESTKEY-not-a-real-key-123"
MARKER = "ZEBRA-BOX-CONTENTS-4471"  # what is typed in a box: it may go to the page and never into a notice
ASKED_OPEN = "use_screen"


def opens(name):
    return (ASKED_OPEN, {"action": "open", "name": name})


class OfflineScreens(groups.Base):
    def setUp(self):
        super().setUp()
        self.asked, self.spoke, self.answer = [], [], {"ok": True}

        def never(*a, **k):
            raise AssertionError("Gemini must not be called with no key")
        mary._gemini_stream = never

    def page(self, name, args):
        self.asked.append((name, args))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer(name, args) if callable(self.answer) else self.answer

    def hear(self, text, key="", host=None):
        return mary.reply(text, self.memory, key, skills=host, page=self.page, on_text=self.spoke.append,
                          on_effect=self.seen.append)

    def hear_model_failing(self, text):
        def down(*a, **k):
            raise OSError("down")
        mary._gemini_stream = down
        return self.hear(text, KEY)

    def both_ways(self, text):
        """The same line with no key, and with a key whose model fails: (reply, what the page was asked) each time."""
        out = []
        for run in (lambda: self.hear(text), lambda: self.hear_model_failing(text)):
            self.asked.clear()
            got = run()
            out.append((got, list(self.asked)))
        return out

    def check(self, got, no_key):
        self.assertEqual(got["text"], "", got)  # D1: no built-in speech
        self.assertEqual(self.spoke, [])
        self.assertTrue(got["notice"], got)
        self.assertEqual(got["mood"], "talking", got)  # keeps the no-key screen from replacing the notice
        self.assertEqual(got["error"], mary.NO_KEY if no_key else mary.NO_GEMINI, got)

    # (a) open

    def test_each_open_phrase_goes_to_its_screen(self):
        table = {
            "open the address book": "book-list", "Show me my notes": "notes", "go to my info": "info",
            "take me to my information": "info", "open saved notes": "list", "show my saved notes": "list",
            "open what I've written down": "list", "open write something down": "write", "show a new note": "write",
            "show my report": "report", "open email": "email", "open my email settings": "email",
            "open the games please": "games", "Please show me the contacts": "book-list",
            "open things I can do": "things", "open Andy Flow": "inbox", "open Mary or Sam": "choose",
            "Mary, can you open the address book?": "book-list", "Hey Sam, could you show my notes": "notes",
            "Open the address book screen.": "book-list", "go to the games": "games",
        }
        for text, name in table.items():
            for no_key, (got, asked) in zip((True, False), self.both_ways(text)):
                self.spoke.clear()
                self.assertEqual(asked, [opens(name)], (text, asked))
                self.check(got, no_key)
                self.assertNotIn(mary.OFFLINE_TEXT, got["notice"])
                self.assertTrue(got["notice"].startswith("Opened "), got["notice"])

    def test_every_name_is_one_the_page_knows(self):
        names = {name for name, _, _ in mary._OFFLINE_SCREEN_WORDS}
        self.assertTrue(names <= set(mary.LIVE_SCREEN_NAMES), names - set(mary.LIVE_SCREEN_NAMES))
        js = read("mary/screens.js")
        for name in names:
            self.assertIn(f"id: '{name}'", js, name)

    def test_the_notice_names_the_screen_the_page_opened(self):
        self.answer = {"ok": True, "screen": "Address book"}
        self.assertEqual(self.hear("open the address book")["notice"], "Opened Address book.")

    def test_go_back(self):
        for text in ("go back", "Go back to you.", "back to you", "please go back", "Mary, go back to Mary"):
            for no_key, (got, asked) in zip((True, False), self.both_ways(text)):
                self.spoke.clear()
                self.assertEqual(asked, [(ASKED_OPEN, {"action": "go_back"})], text)
                self.check(got, no_key)
                self.assertEqual(got["notice"], mary.SCREEN_BACK_TEXT)

    # (b) add a person

    def test_add_a_person_opens_a_blank_form(self):
        for text in ("add a person", "Add someone to my book", "please add a new person to my address book",
                     "add a contact"):
            for no_key, (got, asked) in zip((True, False), self.both_ways(text)):
                self.spoke.clear()
                self.assertEqual(asked, [opens("book-form")], text)
                self.check(got, no_key)

    def test_add_a_person_by_name_fills_the_name_box_only(self):
        for text, name in (("add Tom to my address book", "Tom"), ("Add Mary Ann to my book", "Mary Ann"),
                           ("Mary, please add Sarah Whitfield to the address book.", "Sarah Whitfield"),
                           ("add tom to my book", "tom")):
            for no_key, (got, asked) in zip((True, False), self.both_ways(text)):
                self.spoke.clear()
                self.assertEqual(asked, [opens("book-form"), (ASKED_OPEN, {"action": "fill", "field": "name", "value": name})],
                                 text)
                self.check(got, no_key)
                self.assertTrue(got["notice"].startswith("Opened "), got["notice"])
                self.assertNotIn(name, got["notice"])

    def test_a_relationship_or_two_people_is_not_a_name(self):
        for text in ("add my daughter to my book", "add Tom and Jane to my address book", "add the nurse to my book"):
            self.asked.clear()
            self.hear(text)
            self.assertEqual(self.asked, [opens("book-form")], text)  # the blank form, nothing guessed into it

    def test_if_the_form_will_not_open_nothing_is_filled(self):
        self.answer = {"ok": False, "say": "That didn't open just now."}
        got = self.hear("add Tom to my address book")
        self.assertEqual(self.asked, [opens("book-form")])
        self.assertEqual(got["notice"], "That didn't open just now.")

    # (c) fill

    def test_the_one_safe_fill_pattern(self):
        table = {
            "put Tom in her name": ("name", "Tom"), "type 919-555-0100 in the home phone": ("home phone", "919-555-0100"),
            "enter Nurse Kim into my staff involved": ("staff involved", "Nurse Kim"),
            "Put Tom in the name box": ("name", "Tom"), "write Smith, Tom in their name field": ("name", "Smith, Tom"),
            "put the milk in the fridge in my notes": ("notes", "the milk in the fridge"),
            "Mary, please put Tom in her name please": ("name", "Tom"),
        }
        for text, (field, value) in table.items():
            for no_key, (got, asked) in zip((True, False), self.both_ways(text)):
                self.spoke.clear()
                self.assertEqual(asked, [(ASKED_OPEN, {"action": "fill", "field": field, "value": value, "offline": True})], text)
                self.check(got, no_key)

    def test_the_notice_never_holds_what_was_typed(self):
        self.answer = {"ok": True, "label": "Name", "value": MARKER, "saved": False, "next": f'Say "{MARKER}" back.'}
        got = self.hear(f"put {MARKER} in her name")
        self.assertEqual(self.asked[0][1]["value"], MARKER)  # the page is given it, as said
        self.assertEqual(got["notice"], 'Typed it into "Name". Nothing is saved yet.')
        self.assertNotIn(MARKER, repr(got))
        self.answer = {"ok": True}  # no label from the page: the box words, never the value
        got = self.hear(f"type {MARKER} into the name box")
        self.assertNotIn(MARKER, repr(got))
        self.assertEqual(got["notice"], 'Typed it into "name". Nothing is saved yet.')

    def test_a_refusal_is_the_pages_own_line(self):
        line = "I can't do that one here without my model. You can tap it yourself."
        self.answer = {"ok": False, "say": line}
        got = self.hear("put 2026-01-02 in my day")
        self.assertEqual(got["notice"], line)
        self.assertEqual(self.spoke, [])
        self.assertEqual(got["text"], "")

    def test_a_page_with_no_line_gets_the_plain_not_working_notice(self):
        for answer in ({"ok": False}, {"ok": False, "say": "  "}, "nonsense", None, RuntimeError("x")):
            self.answer = answer
            got = self.hear("open the address book")
            self.assertEqual(got["notice"], mary.NOT_WORKING_TEXT, answer)
            self.assertEqual(got["text"], "")

    # what must not change

    def test_ordinary_talk_is_exactly_as_it_was(self):
        for text in ("I had a good day", "open the pod bay doors", "add milk to my list", "add to my book", "put the kettle on",
                     "show me a picture of a cat", "open", "go to sleep", "add Tom to my phone", "put it in",
                     "what's the weather", "write me a poem", "back"):
            self.asked.clear()
            self.assertIsNone(mary.offline_screen(text, self.page), text)
            got = self.hear(text)
            self.assertEqual(self.asked, [], text)
            self.assertEqual(got["notice"], mary.OFFLINE_TEXT, text)
            self.assertEqual(got["error"], mary.NO_KEY, text)
            self.assertEqual(got["mood"], "sorry", text)

    def test_without_a_page_nothing_changes(self):
        got = mary.reply("open the address book", self.memory, "", on_effect=self.seen.append)
        self.assertEqual(got["notice"], mary.OFFLINE_TEXT)
        self.assertIsNone(mary.offline_screen("open the address book", None))

    def test_a_model_that_answers_is_not_second_guessed(self):
        mary._gemini_stream = groups.Rounds(["Of course, here we go."])
        got = self.hear("open the address book", KEY)
        self.assertEqual(self.asked, [])
        self.assertIn("Of course", got["text"])

    def test_skill_and_memory_phrases_still_win(self):
        host = self.build(real=["word_search", "voice_comfort"])
        helpers.api("PUT", "/api/settings", {"voice_volume": "0.5"})
        got = self.hear("louder", host=host)
        self.assertEqual(self.asked, [])
        self.assertNotEqual(got["notice"], mary.OFFLINE_TEXT)
        self.assertNotIn("Opened", got["notice"])
        self.memory.store = server.memory_store()
        got = self.hear("what do you remember about me")
        self.assertEqual(self.asked, [])
        self.assertEqual(got["notice"], mary.NOTHING_SAVED_TEXT)

    def test_an_emergency_gets_no_page_call(self):
        for text in ("put I can't breathe in my notes", "write I am having chest pain in my notes"):
            got = self.hear(text)
            self.assertEqual(self.asked, [], text)
            self.assertTrue(got["emergency"], got)
            self.assertNotIn("Typed it", got["notice"])
        got = self.hear_model_failing("put I fell and hit my head in the notes")
        self.assertEqual(self.asked, [])
        self.assertTrue(got["emergency"], got)

    def test_the_page_scripts_still_parse(self):
        for rel in ("mary/screens.js", "mary/app.js"):
            run = subprocess.run([NODE, "--check", str(ROOT / "web" / rel)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


def node(body):
    code = (HARNESS + BOOK_PAGE + read("mary/screens.js") + "\n(async function () {\n" + body +
            "\nconsole.log('ok');\n})().catch(function (e) { console.error(e); process.exit(1); });")
    return run_node(code)


class OfflineFillOnThePage(unittest.TestCase):
    """screens.js: offline (the server says there is no model answer) she fills plain text and phone boxes and nothing else."""

    def check(self, body):
        rc, _, err = node(body)
        self.assertEqual(rc, 0, err)

    def test_a_text_or_phone_box_fills(self):
        self.check(r"""
          const off = (f, v) => ({ action: 'fill', field: f, value: v, offline: true });
          let doc = pageOn('add'), out = await use(off('staff_involved', 'Nurse Kim'), envOn(doc));
          assert.equal(out.ok, true);
          assert.equal(doc.byId['staff_involved'].value, 'Nurse Kim');
          doc = bookDoc('book-form');
          for (const [label, key, v] of [['Home phone', 'phone', '919-555-0100'], ['Cell phone', 'cell', '919-555-0188'],
                                         ['Name', 'name', 'Tom'], ['Notes', 'notes', 'Likes fishing']]) {
            out = await use(off(label, v), bookEnv(doc));
            assert.equal(out.ok, true, label);
            assert.equal(doc.byId['bf-' + key].value, v, label);
          }
          doc = pageOn('info');
          out = await use(off('Your room number', '214'), envOn(doc));
          assert.equal(out.ok, true);
          assert.equal(doc.byId['i-room'].value, '214');
        """)

    def test_a_date_time_choice_severity_or_words_box_is_refused(self):
        self.check(r"""
          const SAY = /without my model/;
          const off = (f, v) => ({ action: 'fill', field: f, value: v, offline: true });
          const doc = pageOn('add');
          // an order from the server must not get a severity past it either
          const env = envOn(doc, { order: { acts: ['sev'], sev: 'dangerous' } });
          for (const [label, id, v] of [['Which day?', 'day', '2026-01-02'], ['About what time?', 'time', '09:30'],
                                        ['Your words', 'words', 'my own words']]) {
            const out = await use(off(label, v), env);
            assert.equal(out.ok, false, label);
            assert.match(out.say, SAY, label);
            assert.equal(doc.byId[id].value, '', label);
            assert.deepEqual(doc.byId[id].events, [], label);
          }
          for (const [label, group, v] of [['When did it happen?', 'when', 'Yesterday'], ['How long did you wait?', 'wait', '30 min'],
                                           ['How bad was it?', 'sev', 'dangerous']]) {
            const out = await use(off(label, v), env);
            assert.equal(out.ok, false, label);
            assert.match(out.say, SAY, label);
            assert.ok(doc.groups[group].every(r => !r.checked), label);
          }
          const book = bookDoc('book-form');
          const out = await use(off('Birthday', 'June 3'), bookEnv(book));
          assert.equal(out.ok, false);
          assert.match(out.say, SAY);
          assert.equal(book.byId['bf-birthday'].value, '');
          const info = pageOn('info');
          const pick = await use(off('How Mary talks', 'Offline'), envOn(info));
          assert.equal(pick.ok, false);
          assert.match(pick.say, SAY);
          assert.ok(info.groups.talk_mode.every(r => !r.checked));
        """)

    def test_a_switch_is_refused_even_on_an_order(self):
        self.check(r"""
          const doc = pageOn('info');
          const env = envOn(doc, { order: { acts: ['on'], boxes: ['andy flow'] } });
          const out = await use({ action: 'fill', field: 'Connect Andy Flow', value: 'on', offline: true }, env);
          assert.equal(out.ok, false);
          assert.match(out.say, /without my model/);
          assert.equal(doc.byId['i-andyflow_enabled'].checked, false);
          assert.deepEqual(doc.byId['i-andyflow_enabled'].events, []);
          const remove = await use({ action: 'fill', field: 'Disconnect', value: 'x', offline: true }, envOn(pageOn('info')));
          assert.equal(remove.ok, false);
        """)

    def test_a_secret_keeps_its_own_wall_first(self):
        self.check(r"""
          const doc = pageOn('info');
          for (const [label, id] of [['Smart helper key', 'i-gemini_key'], ['The six words', 'copyWords']]) {
            const out = await use({ action: 'fill', field: label, value: 'hunter2', offline: true }, envOn(doc));
            assert.equal(out.ok, false, label);
            assert.match(out.say, /password/, label);
            assert.doesNotMatch(out.say, /without my model/, label);
            assert.equal(doc.byId[id].value, '', label);
            assert.deepEqual(doc.byId[id].events, [], label);
          }
        """)

    def test_the_same_fills_work_when_there_is_a_model(self):
        self.check(r"""
          const doc = pageOn('add'), env = envOn(doc);
          let out = await use({ action: 'fill', field: 'Which day?', value: '2026-01-02' }, env);
          assert.equal(out.ok, true);
          assert.equal(doc.byId['day'].value, '2026-01-02');
          out = await use({ action: 'fill', field: 'When did it happen?', value: 'Yesterday' }, env);
          assert.equal(out.ok, true);
          assert.ok(doc.groups.when.some(r => r.checked));
          out = await use({ action: 'fill', field: 'About what time?', value: '09:30', offline: false }, env);
          assert.equal(out.ok, true);
          assert.equal(doc.byId['time'].value, '09:30');
          // only a real true narrows her; a model's odd value does not make a switch work either
          out = await use({ action: 'fill', field: 'Smart helper key', value: 'x', offline: 'true' }, envOn(pageOn('info')));
          assert.equal(out.ok, false);
        """)


if __name__ == "__main__":
    unittest.main()
