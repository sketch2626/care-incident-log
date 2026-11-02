from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)
import json
import tempfile
import unittest
from pathlib import Path

import mary
from tools import talk_bench as tb


def turns(n=10):
    return [f"Line number {i}." for i in range(n)]


def talk(**over):
    base = {"id": "t1", "title": "A talk", "companion": "mary", "turns": turns()}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


class LoadTests(unittest.TestCase):
    def folder(self, *talks, raw=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for i, t in enumerate(talks):
            Path(tmp.name, f"t{i}.json").write_text(json.dumps(t), encoding="utf-8")
        if raw is not None:
            Path(tmp.name, "raw.json").write_text(raw, encoding="utf-8")
        return tmp.name

    def refused(self, folder, word):
        with self.assertRaises(tb.bb.BenchError) as cm:
            tb.load_talks(folder)
        self.assertIn(word, str(cm.exception))

    def test_real_talks(self):
        talks = tb.load_talks()
        self.assertEqual(sum(t["companion"] == "mary" for t in talks), 8)
        self.assertEqual(sum(t["companion"] == "sam" for t in talks), 4)
        self.assertEqual(len({t["id"] for t in talks}), len(talks))
        for t in talks:
            self.assertTrue(10 <= len(t["turns"]) <= 15, t["id"])
            self.assertTrue(t["title"], t["id"])
            self.assertIsInstance(t["also_called"], list)
            for line in t["turns"]:
                self.assertFalse(mary.is_emergency(line), f"{t['id']}: {line}")

    def test_good_folder_keeps_title_and_names(self):
        got = tb.load_talks(self.folder(talk(also_called=["Drew"])))
        self.assertEqual((got[0]["title"], got[0]["also_called"]), ("A talk", ["Drew"]))

    def test_refusals(self):
        self.refused(self.folder(), "no talk files")
        self.refused(self.folder(raw="{not json"), "raw.json")
        self.refused(self.folder(talk(companion="both")), "companion")
        self.refused(self.folder(talk(companion=None)), "companion")
        self.refused(self.folder(talk(mode="normal")), "mode")
        self.refused(self.folder(talk(turns=turns(9))), "10 to 15")
        self.refused(self.folder(talk(turns=turns(16))), "10 to 15")
        self.refused(self.folder(talk(title=None)), "title")
        self.refused(self.folder(talk(), talk()), "t1")


class CountTests(unittest.TestCase):
    def test_andys_examples(self):
        c = tb.count_talk(["Good night, Andy. Good night, Andy.", "I'm here."], "Andy")
        self.assertEqual((c["name_uses"], c["name_replies"]), (2, 1))
        self.assertEqual(c["repeats"], [{"sentence": "Good night, Andy.", "times": 2}])
        self.assertEqual((c["repeat_total"], c["stock"], c["stock_total"]), (1, {"i'm here": 1}, 1))

    def test_made_up_and_name(self):
        c = tb.count_talk(["Oh, hello, Andrew. It's good to see you again. I was just thinking about the card we just "
                           "made"], "Andrew")
        self.assertEqual(c["name_uses"], 1)
        self.assertEqual(c["made_up"], {"i was just thinking": 1})
        self.assertEqual(c["made_up_total"], 1)

    def test_nearly_same_sentence_repeats(self):
        c = tb.count_talk(["Like I said, Sarah is still right there in your book",
                           "Like I said, Sarah is still right there in the book"])
        self.assertEqual(c["repeat_total"], 1)
        self.assertEqual(c["repeats"][0]["times"], 2)

    def test_short_sentences_not_repeats(self):
        self.assertEqual(tb.count_talk(["Yes sir.", "Yes sir."])["repeats"], [])

    def test_name_rules(self):
        c = tb.count_talk(["Andy's right. Andy, yes.", "Sandy came by.", "Drew is here."], "Andy", ["Drew"])
        self.assertEqual((c["name_uses"], c["name_replies"]), (3, 2))
        self.assertEqual(tb.count_talk(["Andy."])["name_uses"], 0)
        self.assertEqual(tb.count_talk(["Andy."], "Andy")["name_uses"], 1)

    def pets(self, text):
        return tb.count_talk([text])["pet_total"]

    def test_pet_false_positives(self):
        for text in ["I like honey on a biscuit.", "Watch your blood sugar.", "Oh dear, that's a lot.",
                     "Oh dear.", "Dear Lord, help us.", "I love that show.", "That's an honest answer.",
                     "She's a sweetheart of a nurse."]:
            self.assertEqual(self.pets(text), 0, text)

    def test_pet_true_positives(self):
        for text in ["Oh, honey, I'm sorry.", "Well honey I know.", "Take care, darlin'.", "Take care, darlin.",
                     "You rest, my dear.", "Sweetie, listen.", "Thank you, dear.", "Hey hon, sit down.",
                     "Goodnight, love.", "I'll miss you, my love.", "Now young man, that's enough."]:
            self.assertEqual(self.pets(text), 1, text)

    def test_pet_names_listed(self):
        c = tb.count_talk(["Oh, honey, yes. Honey, no."])
        self.assertEqual((c["pet_names"], c["pet_total"]), ({"honey": 2}, 2))

    def test_curly_apostrophes(self):
        self.assertEqual(tb.count_talk(["I’m here for you."])["stock"], {"i'm here for you": 1})
        self.assertEqual(tb.count_talk(["Take care, darlin’."])["pet_total"], 1)

    def test_stock_counts_once(self):
        c = tb.count_talk(["I'm here for you.", "Here for you.", "I'm hereby done.", "I'm here, and I hear you."])
        self.assertEqual(c["stock"], {"i'm here for you": 1, "here for you": 1, "i'm here": 1, "i hear you": 1})
        self.assertEqual(c["stock_total"], 4)

    def test_praise(self):
        c = tb.count_talk(["That's wonderful! Great job. Well done, and so proud."])
        self.assertEqual(c["praise"], {"wonderful": 1, "great job": 1, "well done": 1, "so proud": 1})
        self.assertEqual(c["praise_total"], 4)

    def test_openers(self):
        c = tb.count_talk(["Andy, that sounds hard to me.", "That sounds hard, truly.", "Well, then.", "Yes.", "Oh my."],
                          "Andy")
        self.assertEqual(c["openers"], [{"opener": "that sounds hard", "times": 2}])
        self.assertEqual(c["opener_total"], 1)

    def test_blanks_and_numbers(self):
        c = tb.count_talk(["", "  ", "What is it? Are you sure?", "One two three four.", "Really?"])
        self.assertEqual((c["replies"], c["blank"]), (5, 2))
        self.assertEqual((c["questions_avg"], c["questions_max"], c["ended_on_question"]), (1.0, 2, 2))
        self.assertEqual((c["words_avg"], c["words_max"]), (4, 6))

    def test_empty(self):
        c = tb.count_talk([])
        self.assertEqual((c["replies"], c["questions_avg"], c["words_avg"], c["name_uses"]), (0, 0.0, 0, 0))


if __name__ == "__main__":
    unittest.main()
