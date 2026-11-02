from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

import http.client
import io
import json
import re
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import mary
import server

KEY = "AIzaSyTESTKEY-not-a-real-key-123"


class FakeGemini:
    """Stands in for mary._gemini_stream. chunks may hold functions: each runs when the stream reaches it."""

    def __init__(self):
        self.bodies = []
        self.keys = []
        self.models = []
        self.chunks = []
        self.fail = False

    def __call__(self, body, api_key, model=""):
        self.bodies.append(body)
        self.keys.append(api_key)
        self.models.append(model)
        if self.fail:
            raise OSError("no network")
        return self._pieces(list(self.chunks))

    @staticmethod
    def _pieces(chunks):
        for chunk in chunks:
            piece = chunk() if callable(chunk) else chunk
            if piece:
                yield piece

    def system(self):
        return self.bodies[-1]["systemInstruction"]["parts"][0]["text"]


class TalkCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.reset_db()

    def setUp(self):
        helpers.reset_db()  # also clears the saved settings (key, companion, voice)
        self.memory_file = Path(server.DATA) / "mary" / "memory.json"
        self.memory_file.unlink(missing_ok=True)
        self.fake = FakeGemini()
        self._real = mary._gemini_stream
        mary._gemini_stream = self.fake

    def tearDown(self):
        mary._gemini_stream = self._real
        self.memory_file.unlink(missing_ok=True)


class TestMoodTags(TalkCase):
    def say(self, text="Good morning", chunks=("[mood: happy] Hello.",), key="test-key", companion="mary"):
        """Runs mary.reply with scripted chunks. Returns (result, spoken pieces, events)."""
        self.fake.chunks = list(chunks)
        memory = mary.Memory(Path(tempfile.mkdtemp(prefix="mary-talk-", dir=helpers.TMP)) / "memory.json")
        pieces, events = [], []
        self.pieces = pieces
        result = mary.reply(
            text, memory, key, companion=companion,
            on_text=lambda p: (pieces.append(p), events.append(("text", p))),
            on_mood=lambda m: events.append(("mood", m)))
        self.memory = memory
        return result, pieces, events

    def moods(self, events):
        return [value for kind, value in events if kind == "mood"]

    def test_tag_is_parsed_and_stripped(self):
        result, pieces, events = self.say(chunks=["[mood: happy] Hello there."])
        self.assertEqual(result["text"], "Hello there.")
        self.assertEqual(result["mood"], "happy")
        self.assertEqual("".join(pieces), "Hello there.")
        self.assertEqual(self.moods(events), ["happy"])
        self.assertEqual(events[0], ("mood", "happy"))
        self.assertFalse(result["gemini_alert"])

    def test_tag_split_across_chunks(self):
        result, pieces, events = self.say(chunks=["[mo", "od: happy] Hi", " there."])
        self.assertEqual(result["text"], "Hi there.")
        self.assertEqual("".join(pieces), "Hi there.")
        self.assertEqual(self.moods(events), ["happy"])

    def test_tag_split_right_at_the_bracket(self):
        result, pieces, events = self.say(chunks=["[", "mood: sorry", "] I'm sorry to hear that."])
        self.assertEqual(result["text"], "I'm sorry to hear that.")
        self.assertEqual(self.moods(events), ["sorry"])

    def test_tag_does_not_hold_the_reply(self):
        seen = []
        result, pieces, events = self.say(chunks=[
            "[mood: happy] First bit. ", lambda: seen.append(list(self.pieces)), "Last bit."])
        self.assertEqual(seen, [["First bit. "]])  # spoken before the last chunk arrived
        self.assertEqual(result["text"], "First bit. Last bit.")

    def test_extra_spaces_and_capitals(self):
        result, pieces, events = self.say(chunks=["[ MOOD :   Laughing  ] Ha ha, that's funny."])
        self.assertEqual(result["mood"], "laughing")
        self.assertEqual(result["text"], "Ha ha, that's funny.")

    def test_tag_later_in_the_text_is_stripped(self):
        result, pieces, events = self.say(chunks=["Hello ", "there [mood: concerned] friend."])
        self.assertEqual(result["text"], "Hello there friend.")
        self.assertEqual(result["mood"], "concerned")
        self.assertEqual(self.moods(events), ["concerned"])

    def test_only_the_first_tag_counts(self):
        result, pieces, events = self.say(chunks=["[mood: happy] Hi [mood: sorry] there."])
        self.assertEqual(result["text"], "Hi there.")
        self.assertEqual(result["mood"], "happy")
        self.assertEqual(self.moods(events), ["happy"])

    def test_no_tag_means_talking(self):
        result, pieces, events = self.say(chunks=["Just a plain reply."])
        self.assertEqual(result["mood"], "talking")
        self.assertEqual(self.moods(events), ["talking"])
        self.assertEqual(result["text"], "Just a plain reply.")

    def test_unknown_listening_and_resting_tags_mean_talking(self):
        for tag in ("sparkly", "listening", "resting", "", "very happy"):
            with self.subTest(tag=tag):
                result, pieces, events = self.say(chunks=[f"[mood: {tag}] Okay then."])
                self.assertEqual(result["mood"], "talking")
                self.assertEqual(self.moods(events), ["talking"])
                self.assertEqual(result["text"], "Okay then.")
                self.assertFalse(result["gemini_alert"])

    def test_every_face_mood_is_accepted_except_the_ones_that_are_not_replies(self):
        for mood in mary.MOODS:
            if mood in ("listening", "resting"):
                continue
            with self.subTest(mood=mood):
                result, _, _ = self.say(chunks=[f"[mood: {mood}] Okay."])
                self.assertEqual(result["mood"], mood)

    def test_tag_never_reaches_text_pieces_or_memory(self):
        result, pieces, events = self.say(chunks=["[mood: happy] Lovely to meet you.\n[name: Dorothy]\n[remember: She likes tea]"])
        self.assertEqual(result["text"], "Lovely to meet you.")
        self.assertNotIn("[", "".join(pieces))
        self.assertEqual(self.memory.name, "Dorothy")
        self.assertEqual(self.memory.facts, ["She likes tea"])
        self.assertNotIn("mood", json.dumps(self.memory.recent).lower())

    def test_mood_tag_after_a_remember_tag_is_stripped_too(self):
        result, pieces, events = self.say(chunks=["Hello.\n[remember: She likes tea]\n[mood: happy]"])
        self.assertEqual(result["text"], "Hello.")
        self.assertEqual(result["mood"], "happy")
        self.assertEqual(self.memory.facts, ["She likes tea"])

    def test_unfinished_tag_at_the_end_is_dropped(self):
        result, pieces, events = self.say(chunks=["Hi there. [mood: ha"])
        self.assertEqual(result["text"], "Hi there.")
        self.assertEqual(result["mood"], "talking")

    def test_tag_with_no_words_is_not_a_reply(self):
        result, pieces, events = self.say(chunks=["[mood: alert]"])
        self.assertEqual((result["text"], result["notice"]), ("", mary.OFFLINE_TEXT))
        self.assertEqual(result["mood"], "sorry")
        self.assertFalse(result["gemini_alert"])
        self.assertEqual(self.moods(events)[-1], "sorry")

    def test_offline_emergency_beats_a_happy_tag(self):
        result, pieces, events = self.say(text="I can't breathe", chunks=["[mood: happy] Okay, I'm here."])
        self.assertEqual(result["emergency"], "medical")
        self.assertEqual(result["mood"], "alert")
        self.assertFalse(result["gemini_alert"])
        self.assertEqual(self.moods(events), ["alert"])
        self.assertEqual(events[0], ("mood", "alert"))  # before any words
        self.assertTrue(result["steps"].startswith(mary.EMERGENCY_TEXT["medical"]))  # D1: steps for the screen
        self.assertEqual(result["text"], "Okay, I'm here.")  # only the model's words, no fixed text
        self.assertNotIn("mood", result["text"])

    def test_offline_emergency_without_a_key_is_alert(self):
        result, pieces, events = self.say(text="I want to die", chunks=[], key="")
        self.assertEqual(result["emergency"], "self_harm")
        self.assertEqual(result["mood"], "alert")
        self.assertEqual(self.fake.bodies, [])

    def test_gemini_alert_tag_is_kept_and_flagged(self):
        result, pieces, events = self.say(text="Something feels strange today",
                                          chunks=["[mood: alert] Please tell a nurse right now."])
        self.assertIsNone(result["emergency"])
        self.assertEqual(result["mood"], "alert")
        self.assertIs(result["gemini_alert"], True)
        self.assertEqual(self.moods(events), ["alert"])

    def test_no_key_is_sorry_and_gemini_is_never_called(self):
        result, pieces, events = self.say(chunks=["[mood: happy] Hi."], key="")
        self.assertEqual(self.fake.bodies, [])
        self.assertEqual(result["mood"], "sorry")
        self.assertEqual(result["error"], mary.NO_KEY)
        self.assertEqual((result["text"], result["notice"]), ("", mary.OFFLINE_TEXT))
        self.assertEqual(self.moods(events), ["sorry"])

    def test_gemini_failure_is_sorry(self):
        self.fake.fail = True
        result, pieces, events = self.say(chunks=[])
        self.assertEqual(result["mood"], "sorry")
        self.assertEqual(result["error"], mary.NO_GEMINI)
        self.assertEqual((result["text"], result["notice"]), ("", mary.OFFLINE_TEXT))

    def test_mood_rule_is_in_the_prompt(self):
        self.say()
        system = self.fake.system()
        self.assertIn("[mood: X]", system)
        self.assertIn("You are Mary", system)
        self.assertNotIn("You are Sam", system)  # M9b: the app facts name Sam for the switch button

    def test_him_is_sam_in_the_prompt(self):
        self.say(companion="him")
        system = self.fake.system()
        self.assertIn("Sam", system)
        self.assertNotIn("You are Mary", system)  # M9b: Sam's app facts name Mary for the switch button
        self.assertIn("You are a man", system)
        self.assertIn("[mood: X]", system)

    def test_unknown_companion_is_mary(self):
        self.say(companion="bob")
        self.assertIn("You are Mary", self.fake.system())

    def test_moods_match_the_face(self):
        src = (helpers.ROOT / "web" / "mary" / "face.js").read_text(encoding="utf-8")
        block = re.search(r"const MOODS = \[(.*?)\];", src, re.S).group(1)
        self.assertEqual(tuple(re.findall(r"'([a-z]+)'", block)), mary.MOODS)


class TestNameFrom(unittest.TestCase):
    def test_names(self):
        cases = {
            "my name is dorothy": "Dorothy",
            "call me mister bill": "Mister Bill",
            "You can call me Bill, please.": "Bill",
            "Hi Mary, I'm Dorothy.": "Dorothy",
            "hello, it's dorothy": "Dorothy",
            "my name’s bob": "Bob",
            "Dorothy Jones": "Dorothy Jones",
            "o'brien": "O'Brien",
            "it's o'brien": "O'Brien",
            "mary-ann": "Mary-Ann",
            "Mary": "Mary",
            "My name is Dorothy and I live in room five": "Dorothy",
            "one two three four five": "One Two Three",
            "just Bill": "Bill",
        }
        for said, name in cases.items():
            with self.subTest(said=said):
                self.assertEqual(mary.name_from(said), name)

    def test_nothing_sensible(self):
        for said in ("", "   ", "um", "Um, uh.", "hello", "Hello Mary", "no", "I don't know", "what?", "123", None,
                     "a" * 45, "Abcdefghijklmnopqrstuvwxyz Abcdefghijklmnopqrstuvwxyz"):
            with self.subTest(said=said):
                self.assertEqual(mary.name_from(said), "")


class TestRoutes(TalkCase):
    def save(self, **settings):
        status, body, _ = helpers.api("PUT", "/api/settings", settings)
        self.assertEqual(status, 200)
        return body

    def talk(self, text="Good morning", chunks=("[mood: happy] Good morning!",), key=KEY, **settings):
        if key:
            self.save(gemini_key=key)
        if settings:
            self.save(**settings)
        self.fake.chunks = list(chunks)
        return helpers.api("POST", "/api/mary/talk", {"text": text})

    def stream(self, text="Good morning", chunks=("[mood: happy] Good morning!",), key=KEY):
        if key:
            self.save(gemini_key=key)
        self.fake.chunks = list(chunks)
        status, raw, headers = helpers.api("POST", "/api/mary/talk?stream=1", {"text": text})
        return status, raw, headers

    @staticmethod
    def lines(raw):
        return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]

    # status and settings

    def test_status_before_anything_is_set(self):
        import voices
        import wakeword
        status, body, _ = helpers.api("GET", "/api/mary/status")
        self.assertEqual(status, 200)
        ready = voices.kokoro_ready()  # M4a: the offline voice may or may not be installed on this computer
        self.assertEqual(body, {"companion": "", "first_run": True, "companions": {"mary": "Mary", "him": "Sam"},
                                "has_key": False, "name": "", "name_forgotten": False,  # M9c
                                "voice_rate": 0.92, "voice_volume": 1.0,
                                "talk_mode": "live", "listen_wait": 2.5, "talk_on_open": True,  # M4a
                                "talk_order": ["offline"] if ready else [],
                                "offline_ready": ready,
                                "voices": {"live": "Sulafat", "tts": "gemini:Sulafat",
                                           "offline": "kokoro:af_heart" if ready else ""},
                                "tts_spent": False,  # M4a
                                "wake_word": True, "wake_ready": wakeword.available()[0]})  # M6

    def test_status_after_setup(self):
        self.save(companion="him", gemini_key=KEY, voice_rate="1.1", voice_volume="0.5")
        status, body, _ = helpers.api("GET", "/api/mary/status")
        self.assertEqual((body["companion"], body["has_key"], body["voice_rate"], body["voice_volume"]),
                         ("him", True, 1.1, 0.5))
        self.assertFalse(body["first_run"])  # a companion is chosen; a missing name is learned later
        helpers.api("POST", "/api/mary/hello", {"text": "my name is dorothy"})
        _, body, _ = helpers.api("GET", "/api/mary/status")
        self.assertEqual(body["name"], "Dorothy")

    def test_settings_reject_a_bad_companion(self):
        self.save(companion="him")
        settings = self.save(companion="bob")
        self.assertEqual(settings["companion"], "him")
        self.assertEqual(self.save(companion="MARY")["companion"], "mary")
        self.assertEqual(self.save(companion="")["companion"], "")

    def test_settings_clamp_the_voice(self):
        self.assertEqual(self.save(voice_rate=5)["voice_rate"], "1.4")
        self.assertEqual(self.save(voice_rate="0.1")["voice_rate"], "0.6")
        self.assertEqual(self.save(voice_rate=1.0)["voice_rate"], "1.0")
        self.assertEqual(self.save(voice_volume=9)["voice_volume"], "1.0")
        self.assertEqual(self.save(voice_volume=0.01)["voice_volume"], "0.2")
        settings = self.save(voice_rate="fast", voice_volume="nan")  # not numbers: ignored
        self.assertEqual((settings["voice_rate"], settings["voice_volume"]), ("1.0", "0.2"))
        _, body, _ = helpers.api("GET", "/api/mary/status")
        self.assertEqual((body["voice_rate"], body["voice_volume"]), (1.0, 0.2))

    # talk

    def test_talk_needs_the_tracker_header(self):
        status, _, _ = helpers.api("POST", "/api/mary/talk", {"text": "hi"}, tracker=False)
        self.assertEqual(status, 403)
        status, _, _ = helpers.api("POST", "/api/mary/hello", {"text": "dorothy"}, tracker=False)
        self.assertEqual(status, 403)
        self.assertEqual(self.fake.bodies, [])

    def test_empty_text_is_a_kind_400(self):
        for path in ("/api/mary/talk", "/api/mary/talk?stream=1"):
            with self.subTest(path=path):
                status, body, _ = helpers.api("POST", path, {"text": "   "})
                self.assertEqual(status, 400)
                self.assertTrue(body["error"])
        self.assertEqual(self.fake.bodies, [])

    def test_talk_answers(self):
        status, body, _ = self.talk()
        self.assertEqual(status, 200)
        self.assertEqual((body["text"], body["mood"], body["emergency"], body["emergency_kind"]),
                         ("Good morning!", "happy", False, ""))
        self.assertEqual((body["error"], body["needs_key"], body["offer"]), ("", False, None))
        self.assertIsNotNone(body["first_words_s"])
        self.assertIsNotNone(body["total_s"])
        self.assertEqual(self.fake.keys, [KEY])

    def test_talk_works_without_the_smart_helper_switch(self):
        self.talk()  # only the key is saved, gemini_enabled never set
        self.assertEqual(len(self.fake.bodies), 1)

    def test_talk_uses_the_saved_model(self):
        self.talk(gemini_model="my-test-model")
        self.assertEqual(self.fake.models, ["my-test-model"])
        self.talk()
        self.assertEqual(self.fake.models[-1], "my-test-model")
        self.save(gemini_model="")
        self.talk()
        self.assertEqual(self.fake.models[-1], "")  # empty: _gemini_stream falls back to assist.DEFAULT_MODEL

    def test_talk_without_a_key(self):
        status, body, _ = self.talk(key="")
        self.assertEqual(status, 200)
        self.assertTrue(body["needs_key"])
        self.assertEqual(body["mood"], "sorry")
        self.assertEqual((body["text"], body["notice"]), ("", mary.OFFLINE_TEXT))
        self.assertFalse(body["emergency"])
        self.assertEqual(self.fake.bodies, [])

    def refuse(self, code, body=b""):
        def raiser(*args, **kwargs):  # a new error each time: its body can be read only once
            raise urllib.error.HTTPError("https://example.invalid/", code, "x", {}, io.BytesIO(body))
        mary._gemini_stream = raiser  # TalkCase.tearDown puts the real one back

    def test_a_key_gemini_refuses_says_so(self):
        self.refuse(400, b'{"error": {"message": "API key not valid. Please pass a valid API key."}}')
        status, body, _ = self.talk()
        self.assertEqual(status, 200)
        self.assertTrue(body["bad_key"])
        self.assertFalse(body["needs_key"])
        self.assertEqual((body["error"], body["text"], body["notice"], body["mood"]),
                         (mary.BAD_KEY, "", mary.BAD_KEY_TEXT, "sorry"))
        self.assertFalse(body["emergency"])
        self.assertNotIn(KEY, json.dumps(body))
        status, raw, _ = self.stream()
        done = self.lines(raw)[-1]
        self.assertTrue(done["bad_key"])
        self.assertEqual((done["text"], done["notice"]), ("", mary.BAD_KEY_TEXT))
        self.assertNotIn(KEY, raw.decode("utf-8"))

    def test_other_failures_are_not_a_bad_key(self):
        self.refuse(503)
        status, body, _ = self.talk()
        self.assertFalse(body["bad_key"])
        self.assertEqual((body["error"], body["text"], body["notice"]), (mary.NO_GEMINI, "", mary.OFFLINE_TEXT))
        mary._gemini_stream = self.fake
        self.assertFalse(self.talk()[1]["bad_key"])

    def test_offline_emergency_without_a_key_still_answers(self):
        status, body, _ = self.talk(text="I can't breathe", key="")
        self.assertTrue(body["emergency"])
        self.assertEqual((body["emergency_kind"], body["mood"]), ("medical", "alert"))
        self.assertTrue(body["needs_key"])
        self.assertTrue(body["steps"].startswith(mary.EMERGENCY_TEXT["medical"]))
        self.assertEqual(body["text"], "")

    def test_offline_emergency_overrides_the_tag(self):
        status, body, _ = self.talk(text="I fell and I'm on the floor", chunks=["[mood: happy] I'm here."])
        self.assertTrue(body["emergency"])
        self.assertEqual((body["emergency_kind"], body["mood"]), ("medical", "alert"))

    def test_gemini_alert_counts_as_an_emergency(self):
        status, body, _ = self.talk(text="Something feels strange today",
                                    chunks=["[mood: alert] Please tell a nurse right now."])
        self.assertTrue(body["emergency"])
        self.assertEqual((body["emergency_kind"], body["mood"]), ("other", "alert"))

    def test_the_companion_setting_reaches_gemini(self):
        self.talk(companion="him")
        self.assertIn("Sam", self.fake.system())
        self.assertNotIn("You are Mary", self.fake.system())
        self.talk(companion="mary")
        self.assertIn("You are Mary", self.fake.system())

    def test_talk_remembers_without_mood_tags(self):
        self.talk(text="I like tea", chunks=["[mood: happy] Tea is lovely.\n[remember: She likes tea]"])
        saved = json.loads(self.memory_file.read_text(encoding="utf-8"))
        self.assertEqual([m["text"] for m in server.mary_memory().store.active()], ["She likes tea"])  # M9c: in the store
        self.assertEqual([t["text"] for t in saved["recent"]], ["I like tea", "Tea is lovely."])
        self.assertNotIn("mood", self.memory_file.read_text(encoding="utf-8"))

    def test_two_talks_never_interleave(self):
        events = []

        def slow():
            events.append("in")
            time.sleep(0.15)
            events.append("out")

        self.save(gemini_key=KEY)
        self.fake.chunks = ["Hello. ", slow]
        threads = [threading.Thread(target=helpers.api, args=("POST", "/api/mary/talk", {"text": "Hi"}))
                   for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(events, ["in", "out", "in", "out"])

    # yes to "Would you like me to write that down?"

    SAID = "The nurse never came when I pressed my call light for 45 minutes."

    def test_yes_to_the_offer_logs_the_incident(self):
        status, body, _ = self.talk(self.SAID, chunks=["I'm so sorry."])
        self.assertEqual(status, 200)
        self.assertEqual((body["text"], body["notice"]), ("I'm so sorry.", mary.OFFER_QUESTION))
        self.assertTrue(body["offer"])
        self.assertIsNone(body["logged"])
        self.assertEqual(helpers.db_rows("SELECT * FROM incidents"), [])  # asking does not save
        status, body, _ = self.talk("Yes please", chunks=["It is written down."])
        self.assertEqual(status, 200)
        self.assertEqual(body["text"], "It is written down.")  # her words; the app's outcome went in her turn note
        self.assertIn(mary.SAVED_TEXT, self.fake.system())
        self.assertEqual(body["mood"], "talking")
        rows = helpers.db_rows("SELECT * FROM incidents")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["source"], row["description"]), ("mary", self.SAID))
        self.assertEqual(body["logged"], {"id": row["id"], "category": row["category"]})
        self.assertEqual(row["category"], "call_light")
        self.assertEqual(row["wait_minutes"], 45)
        self.assertEqual(row["never_came"], 1)
        self.assertEqual(row["occurred_date"], row["logged_at"][:10])
        self.assertEqual(len(self.fake.bodies), 2)  # the offer turn and the saved-note turn
        status, rows_api, _ = helpers.api("GET", "/api/incidents")
        self.assertEqual([r["id"] for r in rows_api], [row["id"]])
        status, body, _ = self.talk("Yes", chunks=["Hello."])  # used up: nothing more is written
        self.assertIsNone(body["logged"])
        self.assertEqual(len(helpers.db_rows("SELECT * FROM incidents")), 1)

    def test_no_to_the_offer_logs_nothing(self):
        self.talk(self.SAID, chunks=["I'm so sorry."])
        status, body, _ = self.talk("No thanks", chunks=["That's all right."])
        self.assertIsNone(body["logged"])
        self.talk("Yes", chunks=["Hello."])
        self.assertEqual(helpers.db_rows("SELECT * FROM incidents"), [])

    def test_stream_yes_to_the_offer_logs_the_incident(self):
        self.stream(self.SAID, chunks=["I'm so sorry."])
        status, raw, _ = self.stream("Yes please", chunks=["It is written down."])
        self.assertEqual(status, 200)
        lines = self.lines(raw)
        done = lines[-1]
        rows = helpers.db_rows("SELECT * FROM incidents")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "mary")
        self.assertEqual(done["logged"], {"id": rows[0]["id"], "category": "call_light"})
        self.assertEqual((done["text"], done["mood"]), ("It is written down.", "talking"))
        self.assertIn({"mood": "talking"}, lines)
        self.assertEqual("".join(x["text"] for x in lines if "text" in x and "done" not in x), "It is written down.")
        self.assertIn(mary.SAVED_TEXT, self.fake.system())

    # streaming

    def test_stream_lines(self):
        status, raw, headers = self.stream(chunks=["[mo", "od: happy] Good ", "morning, ", "friend!"])
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/x-ndjson")
        self.assertNotIn("Content-Length", headers)
        self.assertEqual(headers["Cache-Control"], "no-store")
        lines = self.lines(raw)
        self.assertEqual(lines[0], {"mood": "happy"})
        texts = [x["text"] for x in lines if "text" in x and "done" not in x]
        self.assertEqual(texts, ["Good ", "morning, ", "friend!"])
        first_text = next(i for i, x in enumerate(lines) if "text" in x)
        self.assertLess(0, first_text)  # the mood line came first
        done = lines[-1]
        self.assertIs(done["done"], True)
        self.assertEqual((done["text"], done["mood"], done["emergency"], done["needs_key"]),
                         ("Good morning, friend!", "happy", False, False))
        self.assertEqual(sum(1 for x in lines if "done" in x), 1)

    def test_stream_emergency(self):
        status, raw, _ = self.stream(text="I can't breathe", chunks=["[mood: happy] I'm right here."])
        lines = self.lines(raw)
        self.assertEqual(lines[0], {"mood": "alert"})
        self.assertIn("text", lines[1])
        self.assertTrue(lines[-1]["emergency"])
        self.assertEqual(lines[-1]["emergency_kind"], "medical")

    def test_stream_without_a_key(self):
        status, raw, _ = self.stream(key="")
        lines = self.lines(raw)
        self.assertEqual(lines[0], {"mood": "sorry"})
        self.assertTrue(lines[-1]["needs_key"])
        self.assertEqual((lines[-1]["text"], lines[-1]["notice"]), ("", mary.OFFLINE_TEXT))

    def test_stream_finishes_when_the_page_goes_away(self):
        self.save(gemini_key=KEY)
        gate = threading.Event()
        self.fake.chunks = ["[mood: happy] First bit. ", lambda: gate.wait(5) and "Second bit."]
        conn = http.client.HTTPConnection("127.0.0.1", helpers.start_server(), timeout=10)
        try:
            conn.request("POST", "/api/mary/talk?stream=1", body=json.dumps({"text": "Hi"}),
                         headers={"X-Tracker": "1", "Content-Type": "application/json"})
            resp = conn.getresponse()
            self.assertEqual(json.loads(resp.readline()), {"mood": "happy"})
        finally:
            conn.close()  # the page is gone before the rest of her answer
        gate.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.memory_file.exists() and "Second bit." in self.memory_file.read_text(encoding="utf-8"):
                break
            time.sleep(0.05)
        saved = json.loads(self.memory_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["recent"][-1]["text"], "First bit. Second bit.")

    # hello

    def test_hello_saves_the_name(self):
        status, body, _ = helpers.api("POST", "/api/mary/hello", {"text": "my name is dorothy"})
        self.assertEqual(status, 200)
        self.assertEqual(body, {"name": "Dorothy"})  # M21a: the page asks her to say the welcome (tell)
        self.assertEqual(json.loads(self.memory_file.read_text(encoding="utf-8"))["name"], "Dorothy")
        status, body, _ = helpers.api("POST", "/api/mary/hello", {"text": "call me mister bill"})
        self.assertEqual(body["name"], "Mister Bill")
        self.assertEqual(self.fake.bodies, [])  # no key, no Gemini

    def test_hello_still_greets_when_the_memory_file_is_locked(self):
        with mock.patch.object(mary.Memory, "save", side_effect=PermissionError(13, "locked")):
            status, body, _ = helpers.api("POST", "/api/mary/hello", {"text": "my name is dorothy"})
        self.assertEqual(status, 200)
        self.assertEqual(body, {"name": "Dorothy"})  # M21a: the page asks her to say the welcome (tell)

    def test_hello_without_a_name_changes_nothing(self):
        helpers.api("POST", "/api/mary/hello", {"text": "dorothy"})
        for said in ("", "um"):
            with self.subTest(said=said):
                status, body, _ = helpers.api("POST", "/api/mary/hello", {"text": said})
                self.assertEqual(status, 200)
                self.assertEqual(body, {"name": ""})
        self.assertEqual(json.loads(self.memory_file.read_text(encoding="utf-8"))["name"], "Dorothy")

    # the key stays on this computer

    def test_the_key_never_appears_in_a_response(self):
        self.save(gemini_key=KEY, companion="him")
        bodies = [json.dumps(self.save(gemini_key=KEY))]
        bodies.append(json.dumps(helpers.api("GET", "/api/settings")[1]))
        bodies.append(json.dumps(helpers.api("GET", "/api/mary/status")[1]))
        bodies.append(json.dumps(helpers.api("POST", "/api/mary/hello", {"text": "dorothy"})[1]))
        bodies.append(json.dumps(helpers.api("POST", "/api/mary/talk", {"text": ""})[1]))
        self.fake.chunks = ["[mood: happy] Good morning!"]
        bodies.append(json.dumps(helpers.api("POST", "/api/mary/talk", {"text": "Hi"})[1]))
        self.fake.fail = True
        bodies.append(json.dumps(helpers.api("POST", "/api/mary/talk", {"text": "Hi"})[1]))
        self.fake.fail = False
        status, raw, headers = helpers.api("POST", "/api/mary/talk?stream=1", {"text": "Hi"})
        bodies.append(raw.decode("utf-8") + json.dumps(headers))
        self.assertEqual(len(bodies), 8)
        for body in bodies:
            self.assertNotIn(KEY, body)
        self.assertTrue(any("has_key" in b for b in bodies))


if __name__ == "__main__":
    unittest.main()
