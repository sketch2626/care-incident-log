from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

import io
import json
import os
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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

    MEDICAL_SAID = (
        "Help!", "help me", "please help me", "Please help me now", "Mary, help me!", "Help me, please.", "help help",
        "Somebody help", "someone help me!", "Anybody help!", "Hey, anyone help me", "Mary, somebody please help",
        "I need help now", "I need help right now", "I really need help right away",
        "I think I'm having a heart attack", "heart attack", "I can't catch my breath", "I can't get my breath",
        "I passed out", "I'm passing out", "I blacked out", "she fainted", "I'm fainting", "I feel faint",
        "I felt faint", "I'm feeling faint", "I'm going to faint", "I'm gonna faint", "I feel a little faint",
        "I'm having a seizure", "he's having a fit", "I took too many pills", "too many pills", "the nurse gave me too many pills and I feel dizzy", "I think it was an overdose",
        "I hit my head", "I slipped out of my chair", "I slipped out of bed", "I slipped out of my wheelchair",
        "my lips are blue", "her lips look blue", "his lips turned blue", "my lips went blue",
        "my head is pounding", "head is pounding", "there's a pounding in my head", "I think it's dysreflexia",
        "I'm on the floor", "I am lying on the floor", "I was on the floor", "I've been on the floor",
        "I ended up on the floor", "I ended up stuck on the floor", "they found me on the floor",
        "they left me on the floor", "I'm laying on the floor", "my roommate is on the floor",
        "they took my blood and now it's bleeding")
    SELF_HARM_SAID = (
        "I wanna die", "I want to end it all", "end it all", "I wish I was dead", "I wish I were dead",
        "I don't want to live anymore", "I do not want to live", "I don't want to be alive", "I'm suicidal",
        "there's no reason to live", "no point living", "no point in living", "I want to commit suicide",
        "I don't want to live like this")
    NO_ALARM_SAID = (
        "can you help me find my glasses", "help me remember my daughter's birthday", "the help here is slow",
        "I need help with my tablet", "can someone help me with the TV", "Helpful people here",
        "a faint smell of smoke", "I heard a faint noise", "my lunch tray was on the floor",
        "my call light was on the floor", "they took my blood this morning", "my blood was drawn today",
        "the aide passed out the meds", "they give me too many pills", "my husband died of a heart attack",
        "I take pills for my seizures", "I don't want to live here", "I don't want to live alone")

    def test_help_and_other_emergency_phrases(self):
        for table, kind in ((self.MEDICAL_SAID, "medical"), (self.SELF_HARM_SAID, "self_harm")):
            for said in table:
                for variant in (said, said.replace("'", "’")):  # a curly apostrophe, as speech-to-text types it
                    with self.subTest(variant):
                        self.assertEqual(mary.is_emergency(variant), kind)

    def test_ordinary_sentences_with_these_words_are_not_emergencies(self):
        for said in self.NO_ALARM_SAID:
            for variant in (said, said.replace("'", "’")):
                with self.subTest(variant):
                    self.assertIsNone(mary.is_emergency(variant))

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

    def test_more_ways_to_describe_a_problem_get_an_offer(self):
        for said in ("a nurse hit me", "they keep stealing my things", "I haven't been given my pain medicine",
                     "my catheter bag was full and nobody emptied it", "I wasn't turned all night and now I have a sore",
                     "my call light is broken", "they took my phone", "I haven’t been given my pain medicine",
                     "somebody stole my ring", "she threatened me", "my wheelchair is broken"):
            with self.subTest(said):
                self.assertIsNotNone(mary.lapse_offer(said))

    def test_everyday_talk_gets_no_offer(self):
        for said in ("I had a lovely visit with my daughter", "I never liked broccoli", "my heart is broken since my wife died",
                     "I have a sore throat", "my daughter took my phone to charge it", "it hit me that I miss my wife",
                     "the weather is cold today", "the food here is bland"):
            with self.subTest(said):
                self.assertIsNone(mary.lapse_offer(said))

    def test_gemini_asking_on_her_own_makes_an_offer(self):
        asks = ("That sounds awful. Would you like me to write that down?", "Shall I write that down for you?",
                "Do you want me to write it down?", "Would you like me to note that?",
                "Would you like me to jot that down?", "Want me to put that down for you?")
        for i, spoken in enumerate(asks):
            with self.subTest(spoken):
                memory = mary.Memory(self.dir / f"m{i}.json")
                r = self.say("the food here is bland", [spoken], memory=memory)
                self.assertEqual(r["offer"]["incident"]["category"], "meal")
                self.assertEqual(memory.pending_offer, r["offer"])
                self.assertEqual(r["text"], spoken)  # her own question stands; no second one

    def test_gemini_not_asking_makes_no_offer(self):
        for spoken in ("Please note that I'm an AI. Do you want to hear a joke?", "I'll note that.",
                       "Would you like me to write you a poem?", "That sounds hard."):
            with self.subTest(spoken):
                memory = mary.Memory(self.dir / "none.json")
                r = self.say("the food here is bland", [spoken], memory=memory)
                self.assertIsNone(r["offer"])
                self.assertIsNone(memory.pending_offer)

    def test_gemini_asking_after_a_decline_or_in_self_harm_makes_no_offer(self):
        ask = ["Would you like me to write that down?"]
        r = self.say("Please don't write that down, the food is bland", ask, memory=mary.Memory(self.dir / "a.json"))
        self.assertIsNone(r["offer"])
        r = self.say("I want to die", ask, memory=mary.Memory(self.dir / "b.json"))
        self.assertEqual(r["emergency"], "self_harm")
        self.assertIsNone(r["offer"])

    def test_nothing_reaches_the_incident_log(self):
        helpers.reset_db()
        self.say(self.LAPSE, ["I'm so sorry."])
        self.say("They left me in a wet brief for three hours this morning.", ["That's not right."])
        self.say("Please don't write that down.", ["That's fine."])
        status, rows, _ = helpers.api("GET", "/api/incidents")
        self.assertEqual(status, 200)
        self.assertEqual(rows, [])


class TestYesSavesIt(MaryTestCase):
    """The resident says yes to 'Would you like me to write that down?'. write is a fake that records."""
    LAPSE = TestOffer.LAPSE

    def setUp(self):
        super().setUp()
        self.written = []
        self.fail_next = False
        self.memory = mary.Memory(self.path)

    def write(self, incident):
        if self.fail_next:
            self.fail_next = False
            raise OSError("database is locked")
        self.written.append(incident)
        return 100 + len(self.written)

    def turn(self, text, chunks=("I hear you.",), write=True):
        self.fake.chunks = list(chunks)
        return mary.reply(text, self.memory, KEY, write=self.write if write is True else write)

    def offered(self):
        r = self.turn(self.LAPSE, ["I'm so sorry."])
        self.assertTrue(r["offer"])
        return r["offer"]

    def test_yes_please_writes_the_guess_once(self):
        offer = self.offered()
        asked = len(self.fake.bodies)
        r = self.turn("Yes please", ["should never be said"])
        self.assertEqual(self.written, [offer["incident"]])
        self.assertEqual(self.written[0]["description"], self.LAPSE)
        self.assertEqual(r["text"], mary.SAVED_TEXT)
        self.assertEqual(r["mood"], "talking")
        self.assertEqual(r["logged"], {"id": 101, "category": "call_light"})
        self.assertIsNone(r["offer"])
        self.assertIsNone(self.memory.pending_offer)
        self.assertEqual(len(self.fake.bodies), asked)  # Gemini was not asked
        self.assertEqual(self.memory.recent[-1]["text"], mary.SAVED_TEXT)
        r = self.turn("Yes please")  # the offer is used up
        self.assertEqual(len(self.written), 1)
        self.assertIsNone(r["logged"])

    def test_yes_to_gemini_own_offer_writes_exactly_once(self):
        r = self.turn("the food here is bland", ["That sounds awful. Would you like me to write that down?"])
        self.assertTrue(r["offer"])  # no lapse word, so only Gemini's own question made this offer
        self.assertEqual(self.memory.pending_offer, r["offer"])
        r = self.turn("Yes please", ["should never be said"])
        self.assertEqual(len(self.written), 1)
        self.assertEqual(self.written[0]["description"], "The food here is bland")
        self.assertEqual(r["logged"], {"id": 101, "category": "meal"})
        self.turn("Yes please")
        self.assertEqual(len(self.written), 1)

    def test_every_result_has_logged(self):
        self.assertIsNone(self.turn("Good morning")["logged"])
        self.assertIsNone(self.turn(self.LAPSE)["logged"])

    def test_yes_with_nothing_pending_is_a_normal_reply(self):
        r = self.turn("Yes", ["Hello there."])
        self.assertEqual(self.written, [])
        self.assertEqual(r["text"], "Hello there.")
        self.assertIsNone(r["logged"])
        self.assertEqual(len(self.fake.bodies), 1)

    def test_the_offer_lives_one_turn(self):
        self.offered()
        self.turn("It is a sunny day today.")
        self.assertIsNone(self.memory.pending_offer)
        r = self.turn("Yes")
        self.assertEqual(self.written, [])
        self.assertIsNone(r["logged"])
        self.assertNotEqual(r["text"], mary.SAVED_TEXT)

    def test_no_and_not_now_write_nothing(self):
        for said in ("No thanks", "No", "Nah", "Don't write that down", "Please don't write that down",
                     "maybe later", "Maybe", "Not now", "not right now", "I don’t want any trouble",
                     "Yes, but not now", "Yes, but don't use my name", "Yes, maybe later"):
            with self.subTest(said):
                self.memory = mary.Memory(self.path)
                self.offered()
                r = self.turn(said)
                self.assertEqual(self.written, [], said)
                self.assertIsNone(r["logged"])
                self.assertIsNone(self.memory.pending_offer)

    def test_yes_words(self):
        for said in ("yes", "Yeah.", "Yep!", "Yes, please.", "Sure", "Please", "Please do", "Okay", "OK", "All right",
                     "Go ahead", "Do it", "Write it down", "Put that down", "That would be good", "That would be nice.",
                     "I’d like that", "I'd like that", "I would", "Uh-huh", "Mm-hmm.", "Sure, I'd like that.",
                     "Oh yes please, thank you Mary", "Yes, and the food was cold too",
                     "Yes, and they never came back", "Yes. They never even apologized."):
            with self.subTest(said):
                self.assertTrue(mary.is_yes(said), said)

    def test_not_yes_words(self):
        for said in ("", "No", "No thanks", "No, thank you", "Nah", "Nope", "Maybe", "Maybe later", "Not now",
                     "Don't write that down", "Never mind", "Please help me", "I would like some water",
                     "I need a nurse", "That's not right", "I don't think so", "Okay, I guess",
                     "Yes, what would you write?", "Yes, hold on", "Hello"):
            with self.subTest(said):
                self.assertFalse(mary.is_yes(said), said)

    def test_a_yes_with_more_words_still_saves(self):
        self.offered()
        r = self.turn("Yes, and the food was cold too")
        self.assertEqual(len(self.written), 1)
        self.assertEqual(r["text"], mary.SAVED_TEXT)

    def test_failed_save_says_sorry_and_the_next_yes_retries(self):
        offer = self.offered()
        self.fail_next = True
        r = self.turn("Yes")
        self.assertEqual(self.written, [])
        self.assertEqual(r["text"], mary.SAVE_FAILED_TEXT)
        self.assertEqual(r["mood"], "sorry")
        self.assertIsNone(r["logged"])
        self.assertEqual(self.memory.pending_offer, offer)
        r = self.turn("Yes please")
        self.assertEqual(self.written, [offer["incident"]])
        self.assertEqual(r["text"], mary.SAVED_TEXT)
        self.assertEqual(r["logged"]["id"], 101)

    def test_emergency_comes_first_and_nothing_is_saved(self):
        offer = self.offered()
        r = self.turn("Yes, and I fell out of my bed", ["Press your call light."])
        self.assertEqual(r["emergency"], "medical")
        self.assertEqual(r["mood"], "alert")
        self.assertEqual(self.written, [])
        self.assertIsNone(r["logged"])
        self.assertEqual(self.memory.pending_offer, offer)  # kept for one more turn
        r = self.turn("Yes")
        self.assertEqual(self.written, [offer["incident"]])
        self.assertEqual(r["text"], mary.SAVED_TEXT)

    def test_without_a_write_callable_it_is_a_normal_reply(self):
        self.offered()
        r = self.turn("Yes please", ["Of course."], write=None)
        self.assertEqual(r["text"], "Of course.")
        self.assertIsNone(r["logged"])
        self.assertEqual(self.written, [])

    def test_an_old_offer_is_not_saved(self):
        self.offered()
        self.memory.pending_offer["at"] -= mary.OFFER_TTL_S + 1
        r = self.turn("Yes", ["Hello there."])
        self.assertEqual(self.written, [])
        self.assertIsNone(r["logged"])
        self.assertEqual(r["text"], "Hello there.")
        self.assertIsNone(self.memory.pending_offer)

    def test_an_offer_with_no_time_is_not_saved(self):
        for bad in ("missing", None, "yesterday", True, float("nan")):
            with self.subTest(bad=bad):
                self.memory = mary.Memory(self.path)
                self.offered()
                if bad == "missing":
                    del self.memory.pending_offer["at"]
                else:
                    self.memory.pending_offer["at"] = bad
                self.turn("Yes", ["Hello there."])
                self.assertEqual(self.written, [])

    def test_a_recent_offer_still_saves_after_a_restart(self):
        self.offered()
        self.memory.pending_offer["at"] -= mary.OFFER_TTL_S - 30
        self.memory.save()
        self.memory = mary.Memory(self.path)  # the app was closed and reopened
        r = self.turn("Yes please")
        self.assertEqual(len(self.written), 1)
        self.assertEqual(r["text"], mary.SAVED_TEXT)


def http_error(code, body=b""):
    return urllib.error.HTTPError("https://example.invalid/", code, "x", {}, io.BytesIO(body))


class TestGeminiFailures(MaryTestCase):
    BAD_KEY_BODY = b'{"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}}'

    def failing_with(self, error):
        def raiser(body, api_key, model=""):
            raise error
        mary._gemini_stream = raiser

    def test_a_key_gemini_refuses_is_not_called_offline(self):
        for error in (http_error(400, self.BAD_KEY_BODY), http_error(401), http_error(403, b'{"error": {}}')):
            with self.subTest(code=error.code):
                self.failing_with(error)
                r = self.say("Hello", memory=mary.Memory(self.dir / f"{error.code}.json"))
                self.assertEqual(r["error"], mary.BAD_KEY)
                self.assertEqual(r["text"], mary.BAD_KEY_TEXT)
                self.assertEqual(r["mood"], "sorry")
                self.assertNotIn(KEY, r["text"])
                self.assertNotIn(KEY, r["error"])

    def test_other_failures_still_sound_offline(self):
        for error in (http_error(400, b'{"error": {"message": "Invalid JSON payload"}}'), http_error(400),
                      http_error(404, b"models/nope is not found"), http_error(429), http_error(503),
                      urllib.error.URLError("no route"), OSError("dropped")):
            with self.subTest(error=repr(error)):
                self.failing_with(error)
                r = self.say("Hello", memory=mary.Memory(self.dir / "other.json"))
                self.assertEqual(r["error"], mary.NO_GEMINI)
                self.assertEqual(r["text"], mary.OFFLINE_TEXT)

    def test_an_unreadable_400_body_is_just_offline(self):
        class Broken(io.BytesIO):
            def read(self, *args):
                raise OSError("reset")
        self.failing_with(urllib.error.HTTPError("https://example.invalid/", 400, "x", {}, Broken()))
        r = self.say("Hello")
        self.assertEqual((r["error"], r["text"]), (mary.NO_GEMINI, mary.OFFLINE_TEXT))

    def test_a_bad_key_in_an_emergency_still_gives_the_emergency_words(self):
        self.failing_with(http_error(403))
        r = self.say("I fell this morning")
        self.assertTrue(r["text"].startswith(mary.EMERGENCY_TEXT["medical"]))
        self.assertNotIn(mary.BAD_KEY_TEXT, r["text"])
        self.assertEqual((r["emergency"], r["mood"], r["error"]), ("medical", "alert", mary.BAD_KEY))

    def test_a_slow_trickle_stops_at_the_deadline_with_what_was_said(self):
        clock = [1000.0]

        def sse(text):
            return b"data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode("utf-8")

        def lines():
            yield sse("I hear you. ")
            clock[0] += mary.GEMINI_DEADLINE_S + 1
            yield sse("This comes too late.")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                return lines()

        fake_time = SimpleNamespace(monotonic=lambda: clock[0], time=time.time, sleep=time.sleep)
        with mock.patch("urllib.request.urlopen", return_value=Response()) as urlopen, \
                mock.patch.object(mary, "time", fake_time):
            got = list(self._real({"contents": []}, KEY))
        self.assertEqual(got, ["I hear you. "])
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)
        self.assertEqual(urlopen.call_args.args[0].get_header("X-goog-api-key"), KEY)


class TestRobustMemory(MaryTestCase):
    def test_save_retries_when_windows_has_the_file_open(self):
        real = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(src)
            if len(calls) <= 2:
                raise PermissionError(13, "The process cannot access the file")
            return real(src, dst)

        m = mary.Memory(self.path)
        m.name = "Ruth"
        with mock.patch.object(mary.os, "replace", flaky):
            m.save()
        self.assertEqual(len(calls), 3)
        self.assertEqual(mary.Memory(self.path).name, "Ruth")
        self.assertEqual(list(self.dir.glob("*.tmp")), [])

    def test_save_gives_up_after_five_tries_and_reply_still_answers(self):
        calls = []

        def locked(src, dst):
            calls.append(src)
            raise PermissionError(13, "locked")

        m = mary.Memory(self.path)
        with mock.patch.object(mary.os, "replace", locked):
            with self.assertRaises(PermissionError):
                m.save()
            self.assertEqual(len(calls), 5)
            r = self.say("Hello", memory=m)  # reply swallows the failed save
        self.assertEqual(r["text"], "I hear you.")

    def test_call_me_is_a_name_only_at_the_start_of_a_sentence(self):
        for said in ("The aides call me honey and I hate it.", "They call me names.", "Call me at five, would you?",
                     "Please call me at five.", "Call me later.", "They always call me when I'm busy.",
                     "my name is not important", "Call me anything you like.", "Whatever, call me whatever."):
            with self.subTest(said):
                memory = mary.Memory(self.dir / "none.json")
                self.say(said, memory=memory)
                self.assertEqual(memory.name, "")

    def test_names_people_really_give(self):
        for said in ("call me Dorothy", "Call me dorothy.", "My name is Dorothy", "Hello Mary, my name is Dorothy.",
                     "You can call me Dorothy", "Please call me Dorothy", "Just call me Dorothy",
                     "Good morning. Call me Dorothy.", "I’d like you to call me Dorothy", "Hi! Call me Dorothy"):
            with self.subTest(said):
                memory = mary.Memory(self.dir / "dorothy.json")
                self.say(said, memory=memory)
                self.assertEqual(memory.name, "Dorothy")

    def test_a_good_name_is_not_overwritten_by_a_false_match(self):
        memory = mary.Memory(self.path)
        self.say("My name is Dorothy", memory=memory)
        self.say("The aides call me honey and I hate it", memory=memory)
        self.assertEqual(memory.name, "Dorothy")

    def test_a_null_or_odd_list_keeps_the_name(self):
        for content in ('{"name": "Ruth", "facts": null, "recent": null}',
                        '{"name": "Ruth", "facts": 5, "recent": "x"}',
                        '{"name": "Ruth", "facts": {"a": 1}, "recent": {"role": "user"}}'):
            with self.subTest(content):
                self.path.write_text(content, encoding="utf-8")
                m = mary.Memory(self.path)
                self.assertEqual((m.name, m.facts, m.recent), ("Ruth", [], []))

    def test_a_fact_is_capped(self):
        m = mary.Memory(self.path)
        self.assertTrue(m.add_fact("likes tea " * 60))
        self.assertLessEqual(len(m.facts[0]), mary.MAX_FACT_CHARS)
        self.assertEqual(m.facts[0], m.facts[0].strip())

    def test_she_is_told_to_ask_the_name_only_while_it_is_unknown(self):
        memory = mary.Memory(self.path)
        self.say("Good morning", memory=memory)
        asked = self.fake.bodies[-1]["systemInstruction"]["parts"][0]["text"]
        self.assertIn("You don't know their name yet.", asked)
        self.assertIn("[name: First name]", asked)
        memory.name = "Ruth"
        self.say("Good morning", memory=memory)
        self.assertNotIn("don't know their name", self.fake.bodies[-1]["systemInstruction"]["parts"][0]["text"])


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
