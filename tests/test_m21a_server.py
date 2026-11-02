from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M21a (D1, no built-in speech), server side: notice and steps, a told turn, /api/mary/tell, a lapsing question,
and a dictated note that reaches her not at all. Fake Gemini only."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import mary
import server
from tests.test_mary import FakeGemini, KEY

FELL = "I fell and I can't get up"


def new_memory():
    return mary.Memory(Path(tempfile.mkdtemp(prefix="m21a-", dir=helpers.TMP)) / "memory.json")


class ToldTurn(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGemini()
        real = mary._gemini_stream
        mary._gemini_stream = self.fake
        self.addCleanup(setattr, mary, "_gemini_stream", real)
        self.memory = new_memory()
        self.written = []

    def offer(self):
        self.memory.pending_offer = mary._offer(mary._guess("the nurse never came"))

    def turn(self, key=KEY):
        return mary.reply("yes please", self.memory, key, write=lambda inc: self.written.append(inc) or 7)

    def test_save_yes_goes_through_the_model_with_the_note(self):
        self.offer()
        self.fake.chunks = ["All saved for you."]
        r = self.turn()
        self.assertEqual(r["text"], "All saved for you.")
        self.assertEqual(r["notice"], "")
        self.assertEqual(r["logged"]["id"], 7)
        body = self.fake.bodies[-1]
        system = body["systemInstruction"]["parts"][0]["text"]
        self.assertIn("The app just did this", system)
        self.assertIn(mary.SAVED_TEXT, system)
        self.assertLess(system.index(mary.CHARACTER_NOTE), system.index("The app just did this"))
        self.assertNotIn("tools", body)
        self.assertEqual(self.memory.recent[-1]["text"], "All saved for you.")

    def test_failing_model_gives_a_notice_not_speech(self):
        self.offer()
        self.fake.fail = True
        r = self.turn()
        self.assertEqual(r["text"], "")
        self.assertEqual(r["notice"], mary.SAVED_TEXT)
        self.assertEqual(r["error"], "")
        self.assertNotIn(mary.SAVED_TEXT, [t["text"] for t in self.memory.recent])

    def test_no_key_gives_a_notice_and_no_call(self):
        self.offer()
        r = self.turn(key="")
        self.assertEqual((r["text"], r["notice"]), ("", mary.SAVED_TEXT))
        self.assertEqual(self.fake.bodies, [])

    def test_no_key_offline_line_is_a_notice(self):
        r = mary.reply("what is the weather like", self.memory, "")
        self.assertEqual(r["text"], "")
        self.assertEqual(r["notice"], mary.OFFLINE_TEXT)
        self.assertEqual(r["steps"], "")

    def test_quiet_gated_turn_makes_no_call_and_says_nothing(self):
        skills = mock.Mock()
        skills.resident_said.return_value = {"skip_brain": True, "effects": []}
        r = mary.reply("hmm", self.memory, KEY, skills=skills)
        self.assertEqual((r["text"], r["notice"]), ("", ""))
        self.assertEqual(self.fake.bodies, [])

    def test_gated_say_reaches_the_gate_as_a_notice_with_no_key(self):
        skills = mock.Mock()
        skills.resident_said.return_value = {"skip_brain": True, "effects": [], "say": "Sending in five seconds to Sarah."}
        r = mary.reply("send it", self.memory, "", skills=skills)
        self.assertEqual(r["notice"], "Sending in five seconds to Sarah.")
        skills.her_words.assert_called_once_with("Sending in five seconds to Sarah.")


class TellRoute(unittest.TestCase):
    def test_no_key_is_empty(self):
        with mock.patch.object(server, "mary_settings", return_value={"key": "", "model": "", "companion": "mary"}):
            self.assertEqual(server.mary_tell("Saved."), {"text": ""})

    def test_with_key_saves_her_turn_not_the_note(self):
        fake = FakeGemini()
        fake.chunks = ["Welcome, Dorothy."]
        with mock.patch.object(server, "mary_settings", return_value={"key": KEY, "model": "", "companion": "mary"}), \
                mock.patch.object(mary, "_gemini_stream", lambda body, key, model="", **kw: fake(body, key, model)):
            out = server.mary_tell("Their name is saved as Dorothy.")
        self.assertEqual(out, {"text": "Welcome, Dorothy."})
        self.assertIn("Their name is saved as Dorothy.", fake.bodies[-1]["systemInstruction"]["parts"][0]["text"])
        saved = [t["text"] for t in server.mary_memory().recent]
        self.assertEqual(saved[-1], "Welcome, Dorothy.")
        self.assertFalse(any("name is saved" in t for t in saved))

    def test_old_open_route_is_gone(self):
        status, _, _ = helpers.api("POST", "/api/mary/open", {})
        self.assertNotEqual(status, 200)


class Lapse(unittest.TestCase):
    def test_talk_end_clears_waiting_questions(self):
        memory = server.mary_memory()
        memory.pending_forget = {"about": "my son", "at": time.time()}
        memory.pending_offer = mary._offer(mary._guess("the nurse never came"))
        status, _, _ = helpers.api("POST", "/api/mary/talk/end", {})
        self.assertEqual(status, 200)
        memory = server.mary_memory()
        self.assertIsNone(memory.pending_forget)
        self.assertIsNone(memory.pending_offer)

    def test_pending_forget_is_not_saved_across_restarts(self):
        memory = new_memory()
        memory.pending_forget = {"about": "my son", "at": time.time()}
        memory.save()
        again = mary.Memory(memory.path)
        self.assertIsNone(again.pending_forget)


class HeardRoute(unittest.TestCase):
    def test_note_sends_and_saves_nothing_but_she_remembers_it(self):
        memory = server.mary_memory()
        before = list(memory.recent)
        status, body, _ = helpers.api("POST", "/api/mary/heard", {"text": "call me Zelda, I was born May 5", "note": True})
        self.assertEqual(status, 200)
        memory = server.mary_memory()
        # D18: she hears it, so the turn is remembered once (recent is capped, so look at the whole list)
        self.assertFalse(any("Zelda" in str(t) for t in before))
        self.assertEqual(sum("Zelda" in str(t) for t in memory.recent), 1)
        status, body, _ = helpers.api("POST", "/api/mary/heard", {"text": FELL, "note": True})
        self.assertTrue(body["emergency"])
        self.assertEqual(body["steps"], mary.emergency_text(body["kind"], server.mary_memory(), FELL))
        self.assertNotIn("say", body)
        self.assertFalse(any(t["role"] == "model" for t in server.mary_memory().recent[len(before):]))


if __name__ == "__main__":
    unittest.main()
