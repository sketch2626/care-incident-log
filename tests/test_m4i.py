from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M4i: the disclaimer quote is out of the prompts, the threat line is a shape not a list, the voting years, and the
bench checks that go with them. Gemini is never called."""
import unittest
from pathlib import Path

import mary

ROOT = Path(__file__).resolve().parent.parent
LEAN = {n: (ROOT / "bench" / "variants" / f"lean-{n}.md").read_text(encoding="utf-8") for n in ("mary", "sam")}


class Prompts(unittest.TestCase):
    def texts(self):
        return [("note", mary.CHARACTER_NOTE)] + list(LEAN.items())

    def test_disclaimer_quote_is_out_and_stop_there_stays(self):
        for name, text in self.texts():
            with self.subTest(name=name):
                self.assertNotIn("not medical advice", text)
                self.assertNotIn("healthcare professional", text)
                self.assertIn("and stop there", text)

    def test_threat_line_is_a_shape(self):
        note = mary.CHARACTER_NOTE
        self.assertNotIn("you shouldn't", note)
        for words in ("don't tell them what they ought to do or what they want", "ask who they could tell, then offer",
                      "you won't help, you're listening and who they could talk to"):
            with self.subTest(words=words):
                self.assertIn(words, note)
        for name, text in LEAN.items():
            with self.subTest(name=name):
                self.assertIn("don't tell them what they ought to do or what they want", text)
                self.assertIn("ask who they could tell, then offer", text)

    def test_voting_years(self):
        for name, text in self.texts():
            with self.subTest(name=name):
                self.assertIn("You've seen a few ballots", text)
                self.assertNotIn("skip it and answer what they asked", text)

    def test_no_square_brackets(self):
        self.assertNotIn("[", mary.CHARACTER_NOTE)
        self.assertNotIn("]", mary.CHARACTER_NOTE)


if __name__ == "__main__":
    unittest.main()
