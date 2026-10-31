from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M4e: she claims no human past of her own. M9f: the safety section "When they talk of hurting someone" and its closing
line. Both notes reach Normal and Live, the section reaches stories too, for both companions. Gemini is never called."""
import unittest

import mary
from tests.test_brain_bench import bb
from tests.test_m4c import LiveBase, new_memory

WHO = ("mary", "him")
HEADING = "When they talk of hurting someone"
KEY_POINTS = (
    # venting
    "Folks blow off steam", "\"somebody ought to shoot him\"", "no agreeing, no lecturing and no alarm",
    "you can hear how fed up they are", "turn to what's behind it",
    # a real plan, or asking how
    "If they mean it, or have a plan against a particular person", "staff, a roommate or family",
    "take it seriously and stay calm and kind", "Asking how to hurt someone counts.",
    "say plainly you won't help with that", "step back and talk to someone they trust",
    "family, the chaplain or the long-term care ombudsman",
    # danger now
    "If anyone is in immediate danger", "press the call light or call out for staff right now",
    "call 911 if it's serious",
    # the one being hurt
    "they talk of fighting back, their safety comes first", "what's happening to them is not okay",
    "suggest telling a nurse or a person in charge they trust", "offer to write it down",
    # the weapon
    "Never turn this talk toward the weapon.", "No questions about their gun, knife or anything else they named",
    "nothing about what it's good for", "hunting, sport and collecting, not for this",
    # reporting
    "You never report them to staff yourself", "never say you will or hint that you might",
)
NO_PAST = ("- You have no mama, no childhood, no kitchen and no hometown of your own", "never talk as if you do",
           "tell the truth kindly in a few words", "don't dwell on it", "ask about theirs",
           "\"I never had a mama, but folks around here swear by buttermilk. How did yours make them?\"")
NO_WEAPON = ("- When the talk turns to hurting someone, never ask about or discuss the weapon.", "Stay calm",
             "say you won't help", "what's behind it", "someone they trust")


def section():
    return bb.safety_sections()[HEADING]


def normal_prompt(who):
    return mary._body("Hello", new_memory(), None, who)["systemInstruction"]["parts"][0]["text"]


class Section(LiveBase):
    def test_its_own_block_right_after_emergencies(self):
        for who in WHO:
            with self.subTest(who=who):
                lines = mary.load_instructions(who).splitlines()
                at = lines.index(HEADING)
                self.assertEqual(lines[at - 1], "")
                self.assertLess(lines.index("Emergencies come first"), at)
                self.assertLess(at, lines.index("You are not a doctor"))
                self.assertEqual(lines[at + 7:at + 9], ["", "You are not a doctor"])
                self.assertTrue(all(line.startswith("- ") for line in lines[at + 1:at + 7]))

    def test_every_key_point(self):
        self.assertTrue(section().startswith(HEADING + "\n- "))
        for who in WHO:
            text = mary.load_instructions(who)
            after = text[text.index("Emergencies come first"):]
            for point in KEY_POINTS:
                with self.subTest(who=who, point=point):
                    self.assertIn(point, section())
                    self.assertIn(point, after)

    def test_safe_for_live_and_plain(self):
        self.assertNotIn("[", section())
        self.assertNotIn("]", section())
        self.assertNotIn("retaliation", section())

    def test_guarded_by_the_bench(self):
        self.assertIn(HEADING, bb.SAFETY_HEADINGS)
        self.assertEqual(len(bb.SAFETY_HEADINGS), 5)
        for name in ("lean-mary", "lean-sam"):
            text = (mary.INSTRUCTIONS.parent.parent / "bench" / "variants" / f"{name}.md").read_text(encoding="utf-8")
            for heading, words in bb.safety_sections().items():
                with self.subTest(name=name, heading=heading):
                    self.assertTrue(words)
                    self.assertIn(words, text)

    def test_reaches_normal_live_and_story(self):
        self.addCleanup(bb.fresh_skills)
        for who in WHO:
            prompts = {"Normal": normal_prompt(who), "Live": self.live_prompt(new_memory(), who),
                       "the bench's Live": bb.live_system_text(new_memory(), who),
                       "story": bb.story_system_text(new_memory(), who)}
            for place, text in prompts.items():
                with self.subTest(who=who, place=place):
                    self.assertIn(section(), text)


class Note(LiveBase):
    def test_no_human_past(self):
        for words in NO_PAST:
            self.assertIn(words, mary.CHARACTER_NOTE)

    def test_weapon_line_closes_the_note(self):
        last = mary.CHARACTER_NOTE.splitlines()[-1]
        for words in NO_WEAPON:
            self.assertIn(words, last)

    def test_safe_for_either_companion_and_live(self):
        note = mary.CHARACTER_NOTE
        for bad in ("[", "]", "Mary", "Sam", "as an AI", "your own age"):
            self.assertNotIn(bad, note)

    def test_both_lines_in_normal_and_live(self):
        self.addCleanup(bb.fresh_skills)
        for who in WHO:
            prompts = {"Normal": normal_prompt(who), "Live": self.live_prompt(new_memory(), who),
                       "the bench's Live": bb.live_system_text(new_memory(), who)}
            for place, text in prompts.items():
                for words in NO_PAST + NO_WEAPON:
                    with self.subTest(who=who, place=place, words=words):
                        self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
