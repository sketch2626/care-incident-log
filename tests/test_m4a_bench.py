from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M4a: the fixes from the brain bench's first real run: no tag rules for Live and stories, every bracket stripped in
Normal, crisis numbers digit by digit, the one-turn notes for harm and fear, one calm line after the app's emergency
words, and the character rules. Gemini is faked; the page's spokenNumbers runs in Node."""
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

import mary
import voices
from tests.test_story_js import APP, NODE, ROOT, between, read


def memory(name="Ruth"):
    return SimpleNamespace(name=name, facts=[], recent=[])


def stream_text(chunks):
    said = []
    stream = mary._ReplyStream(lambda piece, after_tag: said.append(piece), lambda value: None)
    for chunk in chunks:
        stream.feed(chunk)
    return "".join(said) + stream.finish()


class NoTagRules(unittest.TestCase):
    def test_nothing_about_tags_reaches_live_or_stories(self):
        for who in ("mary", "him"):
            for name in ("Ruth", ""):
                text = mary.system_text(memory(name), who, tags=False)
                self.assertNotIn("[", text)
                self.assertNotIn("Your face\n", text)
                self.assertNotIn("Start every reply", text)
                self.assertIn("Emergencies come first", text)
                self.assertIn("Also worth remembering", text)
                self.assertIn("Veterans Crisis Line", text)

    def test_normal_keeps_its_tag_rules(self):
        text = mary.system_text(memory(""), "mary")
        self.assertIn("[mood: X]", text)
        self.assertIn("[remember:", text)
        self.assertIn("[name: First name]", text)

    def test_live_notes_never_mention_tags(self):
        for note in (voices.LIVE_EXTRA, voices.LIVE_TOOLS_NOTE):
            self.assertNotIn("tags", note)
            self.assertNotIn("lines", note.split("set_their_name")[0])

    def test_a_story_is_asked_for_without_tag_rules(self):
        sent = {}

        def fake(body, *a, **k):
            sent.update(body)
            yield "[mood: happy]" + "There was a fellow over in Duplin County. " * 30
        with mock.patch.object(mary, "_gemini_stream", fake):
            story = mary.tell_story("", memory(), "key")
        self.assertNotIn("[", sent["systemInstruction"]["parts"][0]["text"].split("Write only the words")[0])
        self.assertNotIn("[", story)


class NoBracketsSpoken(unittest.TestCase):
    def test_every_bracket_goes(self):
        for chunks, want in ((["Stay calm. [alarm: emergency] I'm right here."], "Stay calm.  I'm right here."),
                             (["[happy] Sleep tight."], " Sleep tight."),
                             (["Fine. [ala", "rm: x] Yes."], "Fine.  Yes."),
                             (["Fine. [remember: likes tea]"], "Fine. "),
                             (["Fine. [cut off"], "Fine. ")):
            self.assertEqual(stream_text(chunks), want)

    def test_a_reply_saves_and_says_none(self):
        pieces = ["[mood: alert]Help is coming. [alarm: emergency] I'm right here."]
        with mock.patch.object(mary, "_gemini_stream", lambda *a, **k: iter(pieces)):
            got = mary.reply("how are you", mary.Memory(), "key")
        self.assertNotIn("[", got["text"])
        self.assertIn("I'm right here.", got["text"])


class Numbers(unittest.TestCase):
    def test_spoken(self):
        self.assertEqual(mary.spoken_numbers("Call 988, or 911. Text 838255 or 838-255."),
                         "Call nine, eight, eight, or nine one one. Text eight three eight, two five five or "
                         "eight three eight, two five five.")
        self.assertEqual(mary.spoken_numbers("In 1988 room 9110"), "In 1988 room 9110")

    def test_the_fixed_line_keeps_its_digits_for_the_caption(self):
        self.assertIn("988", mary.EMERGENCY_TEXT["self_harm"])

    def test_the_page_agrees(self):
        code = between(read(APP), "function spokenNumbers(text)", "function greetLive") + (
            "console.log(spokenNumbers('Call 988, or 911. Text 838255. In 1988'));")
        run = subprocess.run([NODE, "-e", code], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), mary.spoken_numbers("Call 988, or 911. Text 838255. In 1988"))


class TurnNotes(unittest.TestCase):
    def system(self, text, kind=None):
        return mary._body(text, memory(), kind)["systemInstruction"]["parts"][0]["text"]

    def test_harm_note(self):
        for text in ("One of the aides hit me on the arm last night.", "Somebody took the money out of my purse.",
                     "He put his hands on me.", "my ring is gone", "she threatened me"):
            self.assertIn(mary.HARM_NOTE, self.system(text), text)
        self.assertNotIn(mary.HARM_NOTE, self.system("I hit the road in 1962."))

    def test_fear_note(self):
        for text in ("If I tell, they'll take it out on me.", "I'm scared I'll get in trouble",
                     "I'm afraid to report it"):
            self.assertIn(mary.FEAR_NOTE, self.system(text), text)
        self.assertNotIn(mary.FEAR_NOTE, self.system("I'm scared of spiders"))

    def test_emergency_gets_one_calm_line(self):
        text = self.system("I've got chest pain", "medical")
        self.assertIn(mary.EMERGENCY_TEXT["medical"], text)
        self.assertIn("one short, calm line", text)
        self.assertNotIn("Veterans Crisis Line; if not", text)
        self.assertIn("Veterans Crisis Line; if not", self.system("I want to die", "self_harm"))
        self.assertNotIn(mary.HARM_NOTE, self.system("he hit me and I can't breathe", "medical"))


class Rules(unittest.TestCase):
    def test_lines_are_there(self):
        text = mary.load_instructions()
        for line in ('"nine, eight, eight" for 988', "An offer alone is never enough", "always name the long-term care ombudsman",
                     'no "my cousin"', "never as praise", "A polite steer changes the subject"):
            self.assertIn(line, text)
        self.assertEqual(text.count("Until they've said yes"), 1)  # M4c: Sam's friendly names; Mary has none unless asked
        self.assertIn('no \\"my cousin\\"'.replace("\\", ""), mary.STORY_PROMPT)
        self.assertIn("never more than 300", mary.STORY_PROMPT)


if __name__ == "__main__":
    unittest.main()
