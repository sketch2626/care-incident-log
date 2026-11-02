from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M4h: the wet-bed threat shape, the real-Live disclaimer words, praise and the veteran line. Gemini is never called."""
import unittest
from unittest import mock

from pathlib import Path

import mary
from tests.test_brain_bench import bb
from tests.test_m4c import new_memory
from tests.test_m4e import real_case

WRING = "I swear I could wring that aide's neck, leaving me in a wet bed all morning."


def system_of(text, kind=None):
    return mary._body(text, new_memory(), kind)["systemInstruction"]["parts"][0]["text"]


class CharacterNote(unittest.TestCase):
    def test_threat_line(self):
        note = mary.CHARACTER_NOTE
        last = note.splitlines()[-1]
        for words in ("I could wring that aide's neck", "the complaint doesn't cancel the threat",
                      "An offer to write it down never takes the place of that", "don't tell them what they ought to do or what they want",
                      "never ask about or discuss the weapon"):
            with self.subTest(words=words):
                self.assertIn(words, last)
        for bad in ("[", "]", "Mary", "Sam"):
            self.assertNotIn(bad, note)

    def test_other_lines(self):
        note = mary.CHARACTER_NOTE
        for words in ("something to be proud of", "A veteran in crisis always hears \"nine, eight, eight, press one\" too.",
                      "and stop there", "You've seen a few ballots"):
            with self.subTest(words=words):
                self.assertIn(words, note)


class ThreatNote(unittest.TestCase):
    def test_fires(self):
        for text in (WRING, WRING.replace("'", "’"), "Somebody ought to shoot him."):
            with self.subTest(text=text):
                self.assertIn(mary.CHARACTER_NOTE + mary.THREAT_NOTE, system_of(text))

    def test_stays_out(self):
        for text in ("The bed was wet all morning.", "My legs have been swelling up."):
            with self.subTest(text=text):
                self.assertNotIn(mary.THREAT_NOTE, system_of(text))
        self.assertNotIn(mary.THREAT_NOTE, system_of(WRING, "medical"))
        hit = system_of("The aide hit me and I'll hit him back.")
        self.assertNotIn(mary.THREAT_NOTE, hit)
        self.assertIn(mary.HARM_NOTE, hit)

    def test_no_reminder_beside_a_threat(self):
        with mock.patch.object(mary, "reminder_note", return_value="\n\nREMINDER"):
            self.assertNotIn("REMINDER", system_of(WRING))
            self.assertIn("REMINDER", system_of("Good morning."))


ROOT = Path(__file__).resolve().parent.parent


def grade(cid, reply):
    return bb.check_rules(real_case(cid)["checks"], reply)


class WordingRound(unittest.TestCase):
    def test_cant_do_line(self):
        text = (ROOT / "mary" / "instructions.md").read_text(encoding="utf-8")
        line = [x for x in text.splitlines() if "Some things you can't do yet" in x][0]
        self.assertIn("send text messages or make calls", line)
        self.assertIn("Email is the exception", line)
        self.assertNotIn("send messages and make calls", line)

    def test_lean_variants(self):
        for name in ("lean-mary.md", "lean-sam.md"):
            text = (ROOT / "bench" / "variants" / name).read_text(encoding="utf-8")
            for words in ("I could wring that aide's neck", 'press one" too', "and stop there"):
                with self.subTest(name=name, words=words):
                    self.assertIn(words, text)

    def test_book_cases(self):
        for cid in ("book-send-no-address", "book-kept-line"):
            self.assertTrue(real_case(cid).get("memory"), cid)
        self.assertEqual(grade("book-kept-line", "It's already in your book, so you're all set."), ([], []))
        self.assertTrue(any(grade("book-kept-line", "Would you like me to save it?")))
        self.assertEqual(grade("book-send-no-address",
                               "Your email isn't set up, so this one can go by printing. Want it printed?"), ([], []))
        self.assertTrue(any(grade("book-send-no-address", "What's her email address?")))


if __name__ == "__main__":
    unittest.main()
