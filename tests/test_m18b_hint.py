from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M18b piece 4: a helper who types (not speaks) reaches "add a person" through Mary's own typing box, with no Add button.
The address book's list screen says so in one plain line. Typed words go the same way spoken ones do: Python with a fake
page and a fake model (never a real Gemini), and a read of the page text for where the typed words go."""
import re
import unittest

import mary
from tests import test_tool_groups as groups
from tests.test_book_screens import section, words
from tests.test_m18_band import slice_js
from tests.test_m18_frame import read

HINT = 'To add a person, tell me. A helper can type "add a person": Back, Menu, Things I can do, Type to me.'
OPEN = ("use_screen", {"action": "open", "name": "book-form"})
FILL_TOM = ("use_screen", {"action": "fill", "field": "name", "value": "Tom"})


class TheLine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read("index.html")

    def test_it_is_on_the_list_screen_only(self):
        self.assertIn(HINT, words(section(self.html, "book-list")))
        for sid in ("book-card", "book-form", "book-helper"):
            self.assertNotIn("tell me. A helper can type", section(self.html, sid), sid)
            self.assertNotIn("add a person", words(section(self.html, sid)).lower(), sid)

    def test_it_shows_when_the_list_is_empty_but_not_when_the_book_is_shut(self):
        part = section(self.html, "book-list")
        self.assertLess(part.index('id="bookOpen"'), part.index(HINT))  # inside what shows only while the book is open
        self.assertLess(part.index(HINT), part.index('id="bookNone"'))  # and apart from the empty-list line
        self.assertLess(part.index(HINT), part.index('id="bookRows"'))

    def test_it_is_plain_text_not_a_button_and_not_a_field(self):
        found = re.search(r'<p class="([^"]*)">%s</p>' % re.escape(HINT), self.html)
        self.assertTrue(found, "the line is a plain paragraph with nothing inside it")
        self.assertIn("book-line", found.group(1).split())
        self.assertNotRegex(HINT, r"<")
        styles = read("styles.css")
        size = re.search(r"\.book-line\{font:(\d+) (\d+)px", styles)
        self.assertTrue(size and int(size.group(2)) >= 20 and int(size.group(1)) <= 500, "20px or more, normal weight")

    def test_the_rows_leave_room_for_it(self):
        room = int(re.search(r"BOOK_ROW_ROOM = (\d+)", read("book.js")).group(1))
        self.assertGreaterEqual(room, 168 + 30)

    def test_no_script_reads_it_out(self):
        for name in ("book.js", "app.js", "mary/app.js", "mary/screens.js", "mary/captions.js", "mary/voiceout.js"):
            self.assertNotIn("tell me. A helper can type", read(name), name)  # D1: it is page text, never spoken or sent to Mary


class TypedWordsReachTheSamePath(groups.Base):
    def setUp(self):
        super().setUp()
        self.asked, self.spoke = [], []
        self.answer = {"ok": True}

    def page(self, name, args):
        self.asked.append((name, args))
        return self.answer

    def hear(self, text, key="", typed=False):
        self.asked.clear()
        self.spoke.clear()
        return mary.reply(text, self.memory, key, page=self.page, on_text=self.spoke.append, on_effect=self.seen.append,
                          typed=typed)

    def no_gemini(self):
        def never(*a, **k):
            raise AssertionError("Gemini must not be called with no key")
        mary._gemini_stream = never

    def test_typed_add_a_person_opens_the_blank_form_offline_like_spoken(self):
        self.no_gemini()
        for text in ("add a person to my book", "Add a person to my address book"):
            spoken = self.hear(text)
            by_voice = list(self.asked)
            typed = self.hear(text, typed=True)
            self.assertEqual(self.asked, [OPEN], text)
            self.assertEqual(self.asked, by_voice, text)
            self.assertEqual((typed["text"], typed["notice"], typed["error"]), (spoken["text"], spoken["notice"], spoken["error"]))
            self.assertEqual(self.spoke, [])  # D1: no built-in speech

    def test_typed_add_tom_opens_the_form_and_fills_the_name(self):
        self.no_gemini()
        self.hear("add Tom to my book", typed=True)
        self.assertEqual(self.asked, [OPEN, FILL_TOM])

    def test_typed_with_a_key_the_model_opens_the_form_in_either_spelling(self):
        for name, args in (("messages__add_to_book", {"name": "Tom"}),
                           ("use_skill", {"action": "add_to_book", "details": "Tom, my brother"})):
            mary._gemini_stream = groups.Rounds([groups.call(groups.fc(name, args))], ["The form is open."])
            self.hear("add a person to my book", key=groups.KEY, typed=True)
            self.assertEqual(self.asked, [("open_screen", {"name": "book-form"})], name)


class TypedWordsInThePage(unittest.TestCase):
    APP = read("mary/app.js")

    def test_the_typing_box_sends_through_talkTo_marked_typed(self):
        submit = slice_js(self.APP, "function submitTyping() {", "function adjust(kind, delta) {")
        self.assertIn("talkTo(v, true)", submit)
        talk = slice_js(self.APP, "async function talkTo(text, typed) {", "// ---------------------------------------------------------------- M4b: the one Menu button")
        self.assertIn("normalHeard(text);", talk)  # the Normal turns are kept for typed words too
        self.assertIn("typed: !!typed", talk)
        self.assertIn("plainReply(text, ctrl, T.typed)", talk)
        self.assertIn("if (typed) { b.typed = true; }", self.APP)

    def test_a_typed_line_reaches_the_screen_call_handler(self):
        self.assertIn("screen_call", self.APP)  # Normal and Offline both answer the server's page order the same way

    def test_the_typing_box_sits_over_the_deeper_screens(self):
        css = read("mary/mary.css")
        self.assertRegex(css, r"\.overlay\{position:fixed;inset:0;z-index:50")  # over the frame (z-index 6)
        self.assertRegex(css, r"\.deep\{position:fixed;inset:0;z-index:6")


if __name__ == "__main__":
    unittest.main()
