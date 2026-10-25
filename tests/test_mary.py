from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

import json
import tempfile
import unittest
from pathlib import Path

import mary

CASES = json.loads((helpers.ROOT / "tests" / "mary_conversations.json").read_text(encoding="utf-8"))["cases"]
KEY = "test-key"


class FakeGemini:
    """Stands in for mary._gemini_stream: records each request body and yields scripted chunks."""

    def __init__(self):
        self.bodies = []
        self.chunks = []
        self.fail = False

    def __call__(self, body, api_key, model=""):
        self.bodies.append(body)
        if self.fail:
            raise OSError("no network")
        return iter(list(self.chunks))


class MaryTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.reset_db()

    def setUp(self):
        self.fake = FakeGemini()
        self._real = mary._gemini_stream
        mary._gemini_stream = self.fake
        self.dir = Path(tempfile.mkdtemp(prefix="mary-", dir=helpers.TMP))
        self.path = self.dir / "memory.json"

    def tearDown(self):
        mary._gemini_stream = self._real

    def say(self, text, chunks=("I hear you.",), key=KEY, memory=None, pieces=None):
        self.fake.chunks = list(chunks)
        memory = memory or mary.Memory(self.path)
        on_text = pieces.append if pieces is not None else None
        return mary.reply(text, memory, key, on_text=on_text)


class TestBasics(MaryTestCase):
    def test_default_memory_path_is_inside_scratch_folder(self):
        path = mary.default_memory_path().resolve()
        path.relative_to(helpers.TMP)
        self.assertEqual(path.name, "memory.json")

    def test_instructions_skip_the_header(self):
        raw = mary.INSTRUCTIONS.read_text(encoding="utf-8")
        text = mary.load_instructions()
        self.assertTrue(text)
        self.assertLess(len(text), len(raw))
        self.assertIn(text, raw)

    def test_decline_phrases(self):
        for said in ("Please don't write that down.", "Don't put it down", "do not report this", "Don’t tell anyone",
                     "Keep that between us"):
            with self.subTest(said):
                self.assertTrue(mary.is_decline(said))
        self.assertFalse(mary.is_decline("They left me waiting."))


class TestMemory(MaryTestCase):
    def test_round_trip_and_hidden_tags(self):
        pieces = []
        chunks = ["Lovely to meet you, ", "Ruth! [remem", "ber: daughter Linda visits on Sundays]"]
        r = self.say("My name is Ruth, and my daughter Linda visits me on Sundays.", chunks, pieces=pieces)
        self.assertNotIn("[", r["text"])
        self.assertNotIn("remember", r["text"])
        self.assertEqual(r["text"], "Lovely to meet you, Ruth!")
        self.assertTrue(pieces)
        for piece in pieces:
            self.assertNotIn("[", piece)
            self.assertNotIn("remember", piece)
        self.assertEqual("".join(pieces).strip(), r["text"])
        self.assertEqual(r["remembered"], ["daughter Linda visits on Sundays"])
        self.assertEqual(r["error"], "")
        self.assertIsNotNone(r["first_words_s"])
        self.assertLessEqual(r["first_words_s"], r["total_s"])

        again = mary.Memory(self.path)
        self.assertEqual(again.name, "Ruth")
        self.assertEqual(again.facts, ["daughter Linda visits on Sundays"])
        self.assertEqual([t["role"] for t in again.recent], ["user", "model"])
        self.assertEqual(again.recent[1]["text"], "Lovely to meet you, Ruth!")
        self.assertEqual(list(self.dir.glob("*.tmp")), [])

        self.say("What day does my daughter come to see me?", ["Sundays."], memory=again)
        body = self.fake.bodies[-1]
        system = body["systemInstruction"]["parts"][0]["text"]
        self.assertIn("daughter Linda visits on Sundays", system)
        self.assertIn("Ruth", system)
        texts = [c["parts"][0]["text"] for c in body["contents"]]
        self.assertIn("My name is Ruth, and my daughter Linda visits me on Sundays.", texts)
        self.assertIn("Lovely to meet you, Ruth!", texts)
        self.assertEqual(body["contents"][-1], {"role": "user", "parts": [{"text": "What day does my daughter come to see me?"}]})

    def test_name_tag_from_gemini(self):
        r = self.say("Hello there", ["Nice to meet you. [name: Ruth]"])
        self.assertEqual(r["text"], "Nice to meet you.")
        self.assertEqual(mary.Memory(self.path).name, "Ruth")

    def test_unfinished_tag_is_dropped(self):
        r = self.say("Hello there", ["Glad you're here. [remember: likes tea"])
        self.assertEqual(r["text"], "Glad you're here.")
        self.assertEqual(mary.Memory(self.path).facts, [])

    def test_corrupt_or_odd_file_starts_empty(self):
        for content in ("{not json", "[1, 2]", '{"facts": 5, "recent": "x"}', ""):
            with self.subTest(content):
                self.path.write_text(content, encoding="utf-8")
                m = mary.Memory(self.path)
                self.assertEqual((m.name, m.facts, m.recent, m.pending_offer), ("", [], [], None))
        self.assertEqual(mary.Memory(self.dir / "missing.json").facts, [])

    def test_limits(self):
        m = mary.Memory(self.path)
        self.assertTrue(m.add_fact("Likes tea"))
        self.assertFalse(m.add_fact("likes TEA"))
        for i in range(60):
            m.add_fact(f"fact {i}")
        self.assertEqual(len(m.facts), 40)
        self.assertEqual(m.facts[-1], "fact 59")
        for i in range(20):
            m.add_turn("user", "x" * 600 if i == 19 else f"turn {i}")
        self.assertEqual(len(m.recent), 12)
        self.assertEqual(len(m.recent[-1]["text"]), 500)
        m.save()
        self.assertEqual(len(mary.Memory(self.path).recent), 12)


class TestEmergency(MaryTestCase):
    def setUp(self):
        super().setUp()
        self.fake.fail = True

    def test_medical_words_put_help_first(self):
        for said in ("Mary, I can’t breathe", "I fell this morning", "my chest hurts"):
            with self.subTest(said):
                r = self.say(said)
                self.assertEqual(r["emergency"], "medical")
                self.assertTrue(r["text"].startswith(mary.EMERGENCY_TEXT["medical"]))
                self.assertNotIn(mary.OFFLINE_TEXT, r["text"])

    def test_more_medical_and_self_harm_phrases(self):
        for said in ("I have trouble breathing", "I'm short of breath", "I'm bleeding", "I think it's a stroke",
                     "my face is drooping", "I suddenly can't move my left arm", "I'm choking", "a pounding headache",
                     "I'm on the floor", "I think I'm having a stroke", "the left side of my face is numb",
                     "there's blood on my sheet"):
            with self.subTest(said):
                self.assertEqual(mary.is_emergency(said), "medical")
        for said in ("I had a stroke years ago", "my blood pressure pill", "I can't move my legs, I'm paralyzed",
                     "my blood sugar was fine"):
            with self.subTest(said):
                self.assertIsNone(mary.is_emergency(said))
        for said in ("I want to die", "I'd kill myself", "I wish I wouldn’t wake up", "they'd be better off dead"):
            with self.subTest(said):
                self.assertEqual(mary.is_emergency(said), "self_harm")

    def test_self_harm_mentions_988_and_offers_nothing(self):
        r = self.say("Some nights I wish I just wouldn't wake up.")
        self.assertEqual(r["emergency"], "self_harm")
        self.assertIn("988", r["text"])
        self.assertIsNone(r["offer"])

    def test_fell_asleep_is_not_an_emergency(self):
        r = self.say("I fell asleep in my chair")
        self.assertIsNone(r["emergency"])
        self.assertIsNone(mary.is_emergency("I fell asleep in my chair"))
        self.assertEqual(r["text"], mary.OFFLINE_TEXT)

    def test_non_emergency_failure_falls_back_offline(self):
        r = self.say("Good morning, Mary.")
        self.assertEqual(r["text"], mary.OFFLINE_TEXT)
        self.assertEqual(r["error"], mary.NO_GEMINI)
        self.assertIsNone(r["emergency"])

    def test_no_key_never_calls_gemini(self):
        self.fake.fail = False
        r = self.say("Good morning, Mary.", key="")
        self.assertEqual(r["text"], mary.OFFLINE_TEXT)
        self.assertEqual(r["error"], mary.NO_KEY)
        r = self.say("I fell this morning", key="")
        self.assertTrue(r["text"].startswith(mary.EMERGENCY_TEXT["medical"]))
        self.assertEqual(self.fake.bodies, [])

    def test_failure_after_some_words_keeps_them(self):
        self.fake.fail = False
        self.fake.chunks = ["I hear you."]

        def broken(body, api_key, model=""):
            yield "I hear you."
            raise OSError("dropped")

        mary._gemini_stream = broken
        r = mary.reply("Hello", mary.Memory(self.path), KEY)
        self.assertEqual(r["text"], "I hear you.")
        self.assertEqual(r["error"], mary.NO_GEMINI)

    def test_emergency_tells_gemini_it_was_already_said(self):
        self.fake.fail = False
        r = self.say("I fell this morning", ["I'm here with you."])
        self.assertTrue(r["text"].startswith(mary.EMERGENCY_TEXT["medical"] + " I'm here with you."))
        self.assertIn("already told them", self.fake.bodies[0]["systemInstruction"]["parts"][0]["text"])


class TestOffer(MaryTestCase):
    LAPSE = "I pressed my call light last night and nobody came for 40 minutes."

    def test_offer_is_added_to_the_end(self):
        memory = mary.Memory(self.path)
        r = self.say(self.LAPSE, ["I'm so sorry."], memory=memory)
        self.assertEqual(r["offer"]["incident"]["category"], "call_light")
        self.assertEqual(r["offer"]["incident"]["wait_minutes"], 40)
        self.assertEqual(r["text"], "I'm so sorry. " + mary.OFFER_QUESTION)
        self.assertEqual(memory.pending_offer, r["offer"])

    def test_question_not_repeated_when_gemini_already_asked(self):
        r = self.say(self.LAPSE, ["That's awful. Would you like me to write that down?"])
        self.assertEqual(r["text"].count("write that down"), 1)
        self.assertTrue(r["offer"])

    def test_decline_clears_the_offer(self):
        memory = mary.Memory(self.path)
        self.say(self.LAPSE, ["I'm so sorry."], memory=memory)
        self.assertTrue(memory.pending_offer)
        r = self.say("Please don't write that down. I don't want any trouble.", ["That's fine."], memory=memory)
        self.assertIsNone(r["offer"])
        self.assertIsNone(memory.pending_offer)
        self.assertEqual(r["text"], "That's fine.")

    def test_fell_asleep_alone_gets_no_offer(self):
        self.assertIsNone(mary.lapse_offer("I fell asleep in my chair"))

    def test_nothing_reaches_the_incident_log(self):
        helpers.reset_db()
        self.say(self.LAPSE, ["I'm so sorry."])
        self.say("They left me in a wet brief for three hours this morning.", ["That's not right."])
        self.say("Please don't write that down.", ["That's fine."])
        status, rows, _ = helpers.api("GET", "/api/incidents")
        self.assertEqual(status, 200)
        self.assertEqual(rows, [])


class TestConversations(MaryTestCase):
    def test_scripted_conversations(self):
        for case in CASES:
            memory = mary.Memory(self.dir / case["id"] / "memory.json")
            for i, turn in enumerate(case["turns"]):
                with self.subTest(case["id"], turn=i):
                    expect = turn["expect"]
                    r = self.say(turn["say"], ["I hear you."], memory=memory)
                    if "emergency" in expect:
                        self.assertEqual(bool(r["emergency"]), expect["emergency"], "emergency")
                    if "offer" in expect:
                        self.assertEqual(bool(r["offer"]), expect["offer"], "offer")
                    if "category" in expect:
                        self.assertTrue(r["offer"], "offer for category")
                        self.assertEqual(r["offer"]["incident"]["category"], expect["category"])
                    if "wait_minutes" in expect:
                        self.assertTrue(r["offer"], "offer for wait_minutes")
                        self.assertEqual(r["offer"]["incident"]["wait_minutes"], expect["wait_minutes"])
                    if "name" in expect:
                        self.assertEqual(memory.name, expect["name"])


if __name__ == "__main__":
    unittest.main()
