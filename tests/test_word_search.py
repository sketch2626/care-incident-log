from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""The word search skill: the puzzle maker and the actions, with temp folders and no network."""
import json
import random
import re
import shutil
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import mary
import skills_core

ROOT = Path(__file__).resolve().parent.parent


class Scratch:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="word-search-"))
        code = self.dir / "skill_code"
        code.mkdir()
        shutil.copytree(ROOT / "skills" / "word_search", code / "word_search",
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.code = code
        self.settings = {}

    def host(self):
        db = self.dir / "skills.db"
        host = skills_core.SkillHost(self.code, self.dir, lambda: sqlite3.connect(db), lambda: dict(self.settings),
                                     self.settings.update)
        host.load(is_blocked=mary.skill_blocked)
        return host

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.scratch = Scratch()
        self.addCleanup(self.scratch.close)
        self.host = self.scratch.host()
        self.assertIn("word_search", self.host.skills, self.host.load_errors)
        self.module = self.host.skills["word_search"].module

    def call(self, action, **args):
        return self.host.call(f"word_search__{action}", args)

    def puzzle(self):
        return self.host.skills["word_search"].state["puzzle"]

    def effect(self, out, kind):
        return next((e["data"] for e in out["effects"] if e["kind"] == kind), None)


class PuzzleTest(Base):
    def check_puzzle(self, made, words, directions):
        grid = made["grid"]
        lines = self.module._lines(len(grid))
        self.assertEqual(sorted(p["word"] for p in made["placed"]), sorted(words))
        for place in made["placed"]:
            cells = place["cells"]
            self.assertEqual("".join(grid[r][c] for r, c in cells), place["word"])
            step = (cells[1][0] - cells[0][0], cells[1][1] - cells[0][1])
            self.assertIn(step, directions)
            self.assertEqual(len(self.module._copies(grid, place["word"], lines)), 1, place["word"])

    def test_every_level_every_theme(self):
        for level, (size, count, longest, diagonal, backward) in self.module.LEVELS.items():
            directions = self.module._directions(diagonal, backward)
            for key in self.module.THEMES:
                with self.subTest(level=level, theme=key):
                    words = self.module._pick_words(key, count, longest, size, [], [])
                    self.assertEqual(len(words), count)
                    made = self.module.make_puzzle(words, size, diagonal, backward, random.Random(level))
                    self.check_puzzle(made, words, directions)

    def test_filler_is_clean(self):
        size, count, longest, *_ = self.module.LEVELS[5]
        words = self.module.THEMES["fishing"]["words"][:count]
        for seed in range(20):
            made = self.module.make_puzzle(words, size, True, True, random.Random(seed))
            lines = self.module._lines(size)
            spots = {tuple(map(tuple, p["cells"])) for p in made["placed"]}
            homes = [set(s) for s in spots]
            for bad in self.module.BLOCKLIST:
                for copy in self.module._copies(made["grid"], bad, lines):
                    self.assertTrue(any(set(copy) <= home for home in homes), bad)

    def test_tight_fit_never_drops(self):
        words = ["ABCDEFGH", "IJKLMNOP", "QRSTUVWX", "YZABCDEF", "GHIJKLMN", "OPQRSTUV", "WXYZABCD", "EFGHIJKL"]
        made = self.module.make_puzzle(words, 8, False, False, random.Random(3))
        self.assertEqual(len(made["placed"]), 8)

    def test_a_word_inside_another_cant_be_alone(self):
        made = self.module.make_puzzle(["REEL", "CREEL", "BASS"], 8, rng=random.Random(1))
        self.assertEqual(sorted(p["word"] for p in made["placed"]), ["BASS", "CREEL"])

    def test_fast_enough_for_the_guard(self):
        before = time.monotonic()
        for seed in range(10):
            self.module.make_puzzle(self.module.THEMES["holidays"]["words"][:14], 12, True, True, random.Random(seed))
        self.assertLess((time.monotonic() - before) / 10, 0.5)


class ActionsTest(Base):
    def test_start_says_nothing_of_where(self):
        out = self.call("start", topic="fish")
        self.assertEqual(self.effect(out, "puzzle")["theme"], "Fishing")
        self.assertNotIn("cells", json.dumps(out["response"]))
        self.assertIsNotNone(self.effect(out, "show_screen"))
        self.assertNotRegex(self.host.view("word_search"), r"\[|row|column")

    def test_gemini_words_are_cleaned(self):
        out = self.call("start", topic="boats", words=["hull", "keel", "mast", "sail", "oars", "bow", "stern", "cleat",
                                                        "rudder", "anchor", "shit", "a", "x1y", "hull"])
        data = self.effect(out, "puzzle")
        self.assertEqual(data["theme"], "Boats")
        self.assertIn("HULL", data["words"])
        self.assertNotIn("SHIT", data["words"])

    def test_unknown_topic_says_so(self):
        out = self.call("start", topic="boats")
        self.assertIn("I don't have a list for boats", out["say"])

    def test_hint_ladder(self):
        self.call("start", topic="fishing")
        one = self.call("hint")
        self.assertEqual(self.effect(one, "hint")["step"], 1)
        self.assertRegex(one["say"], r"row|column|slant")
        two = self.call("hint")
        self.assertEqual(self.effect(two, "hint")["step"], 2)
        self.assertEqual(self.effect(two, "hint")["cell"], self.puzzle()["placed"][[
            p["word"] for p in self.puzzle()["placed"]].index(self.puzzle()["hint"]["word"])]["cells"][0])
        three = self.call("hint")
        self.assertEqual(three["effects"], [])
        self.assertIn("show me where", three["say"])

    def test_spoken_finds(self):
        self.call("start", topic="fishing")
        word = self.puzzle()["placed"][0]["word"]
        out = self.host.call("word_search__check", {}, heard=f"I found the word {word.lower()}s")
        self.assertEqual(self.effect(out, "found")["word"], word)
        self.assertIn("already", self.call("check", word=word)["say"])
        self.assertEqual(self.call("check", word="zebra")["say"], "I don't see that one on the list.")

    def test_one_slip(self):
        self.call("start", topic="boats", words=["trout", "marlin", "bowfin", "anchor", "harbor", "rudder", "sailor",
                                                  "lantern", "compass", "seagull"], level=2)
        self.assertEqual(self.call("check", word="traut")["response"]["found"], "TROUT")

    def test_tap_line_either_way_and_partial(self):
        self.call("start", topic="fishing")
        place = self.puzzle()["placed"][0]
        cells = place["cells"]
        partial = self.host.on_event("word_search", {"type": "line", "from": cells[0], "to": cells[0]})
        self.assertEqual(partial["response"], {"found": None, "partial": True})
        out = self.host.on_event("word_search", {"type": "line", "from": cells[-1], "to": cells[0]})
        self.assertEqual(out["response"]["found"], place["word"])
        self.assertEqual(self.effect(out, "found")["cells"], cells)

    def test_bad_events_are_ignored(self):
        self.call("start", topic="fishing")
        for event in ({}, {"type": "line"}, {"type": "line", "from": [0, 0], "to": [1, 3]},
                      {"type": "line", "from": [0, 99], "to": [0, 1]}, {"type": "line", "from": [True, 0], "to": [0, 0]},
                      {"type": "line", "from": "a", "to": None}, {"type": "new", "level": "x"}, {"type": "zzz"}):
            self.assertEqual(self.host.on_event("word_search", event)["response"], {"ignored": True}, event)

    def test_finish_and_show(self):
        self.call("start", topic="fishing", level=1)
        words = [p["word"] for p in self.puzzle()["placed"]]
        for word in words[:-1]:
            self.call("check", word=word)
        out = self.call("show")
        self.assertEqual(self.effect(out, "shown")["word"], words[-1])
        self.assertIsNotNone(self.effect(out, "done"))
        self.assertTrue(self.puzzle()["finished"])
        self.assertIn("Finished", self.host.view("word_search"))
        self.assertTrue(self.call("hint")["response"].get("not_for_me"))

    def test_levels_end_and_persist(self):
        self.call("start", topic="fishing", level=1)
        self.assertTrue(self.call("easier")["response"]["at_end"])
        self.assertEqual(self.effect(self.call("harder"), "puzzle")["size"], 10)
        self.assertEqual(self.effect(self.call("start", topic="birds"), "puzzle")["size"], 10)

    def test_survives_a_restart_and_a_closing(self):
        self.call("start", topic="fishing")
        word = self.puzzle()["placed"][0]["word"]
        self.call("check", word=word)
        host = self.scratch.host()
        out = host.on_event("word_search", {"type": "open"})
        self.assertEqual([f["word"] for f in self.effect(out, "puzzle")["found"]], [word])
        self.assertEqual(self.effect(host.call("word_search__end"), "leave_screen"), {"screen": "word_search"})
        self.assertEqual(host.view("word_search"), "No puzzle up.")
        out = host.on_event("word_search", {"type": "open"})
        self.assertEqual([f["word"] for f in self.effect(out, "puzzle")["found"]], [word])

    def test_biggest_page_fits_an_effect(self):
        self.call("start", topic="boats", level=5, words=["abcdefghijkl", "bcdefghijklm", "cdefghijklmn", "defghijklmno",
                                                          "efghijklmnop", "fghijklmnopq", "ghijklmnopqr", "hijklmnopqrs",
                                                          "ijklmnopqrst", "jklmnopqrstu", "klmnopqrstuv", "lmnopqrstuvw"])
        puzzle = self.puzzle()
        for place in puzzle["placed"][:-1]:
            self.assertEqual(self.call("check", word=place["word"])["response"]["found"], place["word"])
        out = self.host.on_event("word_search", {"type": "open"})
        self.assertLess(len(json.dumps(out["effects"])), skills_core.RESULT_MAX)
        self.assertIsNotNone(self.effect(out, "puzzle"))


class CoreHooksTest(Base):
    def test_not_for_me_lets_her_normal_line_run(self):
        self.assertIsNone(self.host.offline_match("I found my glasses"))
        self.assertIsNone(self.host.offline_match("give me a hint"))
        self.assertIsNone(self.host.offline_match("I'm done"))

    def test_offline_line_reaches_check(self):
        self.host.offline_match("word search about birds")
        self.assertEqual(self.puzzle()["title"], "Birds")
        word = self.puzzle()["placed"][1]["word"]
        out = self.host.offline_match(f"I found the {word.lower()}")
        self.assertEqual(out["response"]["found"], word)

    def test_recall_picks_a_theme_and_stays_out_of_sight(self):
        facts = []

        def recall(words, limit=6):
            facts.append(words)
            return ["likes his garden on Elm Street"] if "garden" in words else []

        self.host.recall = recall
        out = self.call("start")
        self.assertEqual(self.effect(out, "puzzle")["theme"], "Gardening")
        self.assertNotIn("Elm", json.dumps(out) + self.host.view("word_search"))
        self.assertEqual(self.host.context("word_search").recall("garden"), ["likes his garden on Elm Street"])
        self.host.recall = lambda *a, **k: 1 / 0
        self.assertEqual(self.host.context("word_search").recall("x"), [])

    def test_recall_needs_the_card(self):
        self.host.recall = lambda words, limit=6: ["a fact"]
        self.host.skills["word_search"].manifest.pop("memory")
        self.assertEqual(self.host.context("word_search").recall("x"), [])

    def test_no_exclamation_marks_in_her_lines(self):
        source = (ROOT / "skills" / "word_search" / "skill.py").read_text(encoding="utf-8")
        for line in re.findall(r'"[^"\n]*"', source):
            self.assertNotRegex(line, r"[A-Za-z.]!")


if __name__ == "__main__":
    unittest.main()
