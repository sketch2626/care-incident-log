from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M4a: the Live token body, talk modes, the emergency check on Live, app facts, the listen-wait skill actions,
the pace/speed plumbing and the /api/mary/say checks. No network: voices._open is faked."""
import shutil
import tempfile
import time
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import mary
import server
import voices
from tests.test_voices import KEY, PCM, Net, Resp, http_error

REAL = Path(__file__).resolve().parent.parent / "skills"


class M4aCase(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        (server.DATA / "mary" / "memory.json").unlink(missing_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="m4a-skills-", dir=helpers.TMP)) / "skills"
        shutil.copytree(REAL / "voice_comfort", folder / "voice_comfort",
                        ignore=shutil.ignore_patterns("__pycache__"))
        p = mock.patch.object(server, "SKILLS_DIR", folder)
        p.start()
        self.addCleanup(p.stop)
        server.set_skill_host_for_tests(None)
        self.addCleanup(server.set_skill_host_for_tests, None)

    def put(self, **kw):
        return helpers.api("PUT", "/api/settings", kw)

    def settings(self):
        return server.mary_settings()

    def net(self, *queue):
        net = Net(*queue)
        p = mock.patch.object(voices, "_open", net)
        p.start()
        self.addCleanup(p.stop)
        return net


class LiveStartBody(M4aCase):
    def start(self, **settings):
        self.put(gemini_key=KEY, **settings)
        net = self.net(Resp({"name": "auth_tokens/abc"}))
        status, got, _ = helpers.api("POST", "/api/mary/live/start", {})
        self.assertEqual(status, 200, got)
        return net.body()["bidiGenerateContentSetup"]

    def test_body_has_tools_detection_compression_voice_and_memory(self):
        memory = server.mary_memory()
        memory.name = "Ruth"
        memory.save()
        setup = self.start(companion="him", voice_sam="live:Achird", listen_wait="4")
        self.assertTrue(setup["tools"])
        text = setup["systemInstruction"]["parts"][0]["text"]
        self.assertIn("Voice comfort", text)
        self.assertIn("Ruth", text)
        vad = setup["realtimeInputConfig"]["automaticActivityDetection"]
        self.assertEqual(vad["endOfSpeechSensitivity"], "END_SENSITIVITY_LOW")
        self.assertEqual(vad["silenceDurationMs"], 4000)
        self.assertIn("contextWindowCompression", setup)
        voice = setup["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]
        self.assertEqual(voice, "Achird")

    def test_slow_pace_sentence_only_when_slow(self):
        slow = self.start(voice_rate="0.7")["systemInstruction"]["parts"][0]["text"]
        self.assertIn("somewhat slower pace", slow)
        normal = self.start(voice_rate="1.0")["systemInstruction"]["parts"][0]["text"]
        self.assertNotIn("somewhat slower pace", normal)
        fast = self.start(voice_rate="1.3")["systemInstruction"]["parts"][0]["text"]
        self.assertIn("brisker pace", fast)


class TalkModes(M4aCase):
    def test_default_save_and_junk(self):
        self.assertEqual(self.settings()["talk_mode"], "live")
        self.put(talk_mode="normal")
        self.assertEqual(self.settings()["talk_mode"], "normal")
        self.put(talk_mode="offline")
        self.assertEqual(self.settings()["talk_mode"], "offline")
        self.put(talk_mode="banana")
        self.assertEqual(self.settings()["talk_mode"], "offline")

    def test_talk_order(self):
        self.assertEqual(server.talk_order("live", True, True), ["live", "normal", "offline"])
        self.assertEqual(server.talk_order("live", False, True), ["offline"])
        self.assertEqual(server.talk_order("live", True, False), ["live", "normal"])
        self.assertEqual(server.talk_order("live", False, False), [])
        self.assertEqual(server.talk_order("offline", True, True), ["offline"])
        self.assertEqual(server.talk_order("normal", True, True), ["normal", "offline"])


class Heard(M4aCase):
    def test_emergency_and_ordinary(self):
        _, got, _ = helpers.api("POST", "/api/mary/heard", {"text": "I fell and I can't get up"})
        self.assertTrue(got["emergency"])
        self.assertTrue(got["say"])
        _, got, _ = helpers.api("POST", "/api/mary/heard", {"text": "tell me a story"})
        self.assertFalse(got["emergency"])

    def test_tool_call_blocked_on_emergency_and_runs_otherwise(self):
        self.put(voice_volume="0.5")
        _, got, _ = helpers.api("POST", "/api/mary/skills/call", {
            "name": "voice_comfort__louder", "args": {}, "heard": "I fell and I can't get up"})
        self.assertTrue(got.get("emergency"))
        self.assertEqual(self.settings()["voice_volume"], 0.5)
        _, got, _ = helpers.api("POST", "/api/mary/skills/call", {
            "name": "voice_comfort__louder", "args": {}, "heard": "speak up please"})
        self.assertNotIn("error", got["response"])
        self.assertAlmostEqual(self.settings()["voice_volume"], 0.6)


class AppFacts(M4aCase):
    def text(self, companion="mary"):
        return mary._app_facts_text(companion)

    def test_picked_voice_named(self):
        self.put(voice_mary="live:Sulafat")
        text = self.text()
        self.assertIn("Your voice right now is Sulafat", text)

    def test_talk_choice_reflects_setting(self):
        self.assertEqual(server.mary_app_facts("mary")["talk_choice"], "live")
        self.put(talk_mode="normal")
        self.assertEqual(server.mary_app_facts("mary")["talk_choice"], "normal")
        self.assertEqual(server.MARY_VOICE_NOW, "picked")

    def test_offline_voice_wording(self):
        self.put(voice_mary="kokoro:af_heart", talk_mode="offline")
        with mock.patch.object(voices, "kokoro_ready", return_value=True):
            text = self.text()
        self.assertIn("the offline voice", text)


class VoiceComfortTime(M4aCase):
    def call(self, name):
        return helpers.api("POST", "/api/mary/skills/call", {"name": f"voice_comfort__{name}", "args": {}})[1]

    def test_more_and_less_time_by_call(self):
        got = self.call("more_time")
        self.assertEqual(self.settings()["listen_wait"], 4.0)
        self.assertIn("more time", got["say"])
        self.call("more_time")
        self.assertEqual(self.settings()["listen_wait"], 5.0)
        self.call("more_time")
        self.call("more_time")
        self.assertEqual(self.settings()["listen_wait"], 6.0)
        self.assertIn("as long as I can", self.call("more_time")["say"])
        self.call("less_time")
        self.assertEqual(self.settings()["listen_wait"], 2.5)

    def test_slower_faster_notes(self):
        self.assertIn("slower", self.call("slower")["response"]["note"])
        self.assertIn("faster", self.call("faster")["response"]["note"])

    def test_offline_phrases(self):
        host = server.skill_host()
        host.offline_match("you keep cutting me off")
        self.assertEqual(self.settings()["listen_wait"], 4.0)
        rate = self.settings()["voice_rate"]
        host.offline_match("hey you can answer faster")
        self.assertEqual(self.settings()["listen_wait"], 2.5)
        self.assertEqual(self.settings()["voice_rate"], rate)  # "answer faster" is not "talk faster"


class SayChecks(M4aCase):
    def test_bad_input(self):
        self.assertEqual(helpers.api("POST", "/api/mary/say", {"text": "  ", "mode": "normal"})[0], 400)
        self.assertEqual(helpers.api("POST", "/api/mary/say", {"text": "hi", "mode": "weird"})[0], 400)

    def test_no_key_normal(self):
        net = self.net()
        status, got, _ = helpers.api("POST", "/api/mary/say", {"text": "hi", "mode": "normal", "rate": 0.8})
        self.assertEqual(status, 400)
        self.assertTrue(got["no_key"])
        self.assertEqual(net.requests, [])

    def test_pace_words_and_speed_plumbing(self):
        self.assertEqual(voices.pace_style(1.0), voices.STYLE)
        self.assertIn("slowly and clearly", voices.pace_style(0.9))
        self.assertIn("very slowly", voices.pace_style(0.7))
        self.assertIn("brisk", voices.pace_style(1.2))
        self.put(gemini_key=KEY)
        net = self.net(Resp(b""), Resp({"candidates": []}))
        helpers.api("POST", "/api/mary/say", {"text": "hi", "mode": "normal", "rate": 0.7})
        self.assertIn("very slowly", json.dumps(net.body(0)))


# --- M4a: Live's brain (talks like a friend, remembers the talk, learns the name they go by) ---
FELL = "I fell and I can't get up"


class LiveBrain(M4aCase):
    def memory(self):
        return mary.Memory(server.DATA / "mary" / "memory.json")

    def token_setup(self, memory, skills=None):
        net = self.net(Resp({"name": "auth_tokens/abc"}))
        voices.live_token("live:Achird", KEY, "mary", "", server.DATA, skills=skills, memory=memory)
        return net.body()["bidiGenerateContentSetup"]

    def call(self, name, args, heard=None):
        body = {"name": name, "args": args}
        if heard is not None:
            body["heard"] = heard
        return helpers.api("POST", "/api/mary/skills/call", body)[1]

    def test_live_extra_is_no_short_cap_and_never_a_menu(self):
        self.assertNotIn("one to three short sentences", voices.LIVE_EXTRA)
        self.assertIn("menu of options", voices.LIVE_EXTRA)
        self.assertIn("North Carolina", voices.LIVE_EXTRA)
        self.assertIn("Greet them only once", voices.LIVE_EXTRA)

    def test_memory_tools_even_with_no_skills(self):
        setup = self.token_setup(self.memory())
        names = {d["name"] for t in setup["tools"] for d in t.get("functionDeclarations", [])}
        self.assertEqual(names, {"remember_fact", "set_their_name", "tell_story", "story_more", "end_talk"})
        self.assertFalse(any("__" in n for n in names))
        self.assertIn(voices.LIVE_TOOLS_NOTE, setup["systemInstruction"]["parts"][0]["text"])

    def test_memory_tools_join_the_skills_tools(self):
        self.put(gemini_key=KEY)
        net = self.net(Resp({"name": "auth_tokens/abc"}))
        helpers.api("POST", "/api/mary/live/start", {})
        tools = net.body()["bidiGenerateContentSetup"]["tools"]
        self.assertEqual(len(tools), 1)
        names = [d["name"] for d in tools[0]["functionDeclarations"]]
        for want in ("voice_comfort__louder", "set_skill", "remember_fact", "set_their_name"):
            self.assertIn(want, names)

    def test_system_text_has_the_last_talk(self):
        memory = self.memory()
        memory.add_turn("user", "Tell me about Mount Airy.")
        memory.add_turn("model", "Oh,  Mayberry itself!")
        text = self.token_setup(memory)["systemInstruction"]["parts"][0]["text"]
        self.assertIn("Your last talk together (most recent last):\nThey: Tell me about Mount Airy.\n"
                      "You: Oh, Mayberry itself!", text)
        fresh = self.token_setup(self.memory())["systemInstruction"]["parts"][0]["text"]
        self.assertNotIn("Your last talk together", fresh)

    def test_set_their_name_and_remember_fact(self):
        self.assertEqual(self.call("set_their_name", {"name": "Andy"})["response"], {"ok": True})
        self.assertEqual(self.memory().name, "Andy")
        self.assertTrue(self.call("remember_fact", {"fact": "Grew up near Boone."})["response"]["ok"])
        self.assertIn("Grew up near Boone.", self.memory().facts)
        self.assertFalse(self.call("set_their_name", {"name": "honey"})["response"]["ok"])  # a pet name
        self.assertFalse(self.call("set_their_name", {"name": "  "})["response"]["ok"])
        self.assertFalse(self.call("remember_fact", {"fact": " "})["response"]["ok"])
        self.assertEqual(self.memory().name, "Andy")

    def test_emergency_heard_refuses_memory_tools(self):
        self.assertTrue(self.call("set_their_name", {"name": "Andy"}, heard=FELL).get("emergency"))
        self.assertTrue(self.call("remember_fact", {"fact": "Likes tea."}, heard=FELL).get("emergency"))
        self.assertEqual((self.memory().name, self.memory().facts), ("", []))

    def test_heard_remembers_their_turn_and_learns_call_me(self):
        helpers.api("POST", "/api/mary/heard", {"text": "My name is Andrew, but call me Andy."})
        m = self.memory()
        self.assertEqual(m.name, "Andy")
        self.assertEqual([(t["role"], t["text"]) for t in m.recent], [("user", "My name is Andrew, but call me Andy.")])

    def test_emergency_heard_saves_each_turn_once(self):
        _, got, _ = helpers.api("POST", "/api/mary/heard", {"text": FELL})
        self.assertEqual([(t["role"], t["text"]) for t in self.memory().recent], [("user", FELL), ("model", got["say"])])

    def test_live_said_records_her_turn(self):
        status, got, _ = helpers.api("POST", "/api/mary/live/said", {"text": "Well hey there,  Andy!"})
        self.assertEqual((status, got), (200, {"ok": True}))
        helpers.api("POST", "/api/mary/live/said", {"text": "   "})
        self.assertEqual([(t["role"], t["text"]) for t in self.memory().recent], [("model", "Well hey there, Andy!")])


class NameCases(unittest.TestCase):
    def test_learn_name_call_me_wins(self):
        from types import SimpleNamespace
        cases = {
            "call me Andy": "Andy",
            "I'm Andy, call me Andy.": "Andy",
            "My name is Andrew but call me Andy": "Andy",
            "My name is Andrew, but everybody calls me Andy.": "Andy",
            "Everybody calls me andy": "Andy",
            "You can call me Andy, my name is Andrew": "Andy",
            "my name is Andrew": "Andrew",
            "I'm Andy": "",                # "I'm" is too loose for a pattern; Gemini's tag or tool takes it
            "the aides call me honey": "",
            "call me back later": "",
            "everybody calls me honey": "",
        }
        for said, want in cases.items():
            with self.subTest(said=said):
                memory = SimpleNamespace(name="")
                self.assertEqual(mary.learn_name(memory, said), want)
                self.assertEqual(memory.name, want)

    def test_name_from_and_clean_name(self):
        for said in ("I'm Andy", "call me Andy", "My name is Andrew but call me Andy",
                     "Andrew, but everybody calls me Andy", "Andy", "andy"):
            with self.subTest(said=said):
                self.assertEqual(mary.name_from(said), "Andy")
                self.assertEqual(mary.clean_name(said), "Andy")
        for bad in ("honey", "", None, "   "):
            with self.subTest(bad=bad):
                self.assertEqual(mary.clean_name(bad), "")


class StoryAndTalkOnOpen(M4aCase):  # M4a: Live's tell_story tool, "Start talking when Mary opens", Normal's room
    STORY = ("[mood: happy] " + " ".join(["Once upon a time in Boone there lived a man named Earl."] * 12)
             + " [remember: Likes stories.]")
    FELL = "I fell and I can't get up"

    def call(self, args, heard=None):
        body = {"name": "tell_story", "args": args}
        if heard is not None:
            body["heard"] = heard
        return helpers.api("POST", "/api/mary/skills/call", body)[1]

    def fake(self, pieces=(), error=None):
        seen = []

        def stream(body, api_key, model="", deadline_s=None):
            seen.append((body, api_key, deadline_s))
            if error:
                raise error
            yield from pieces
        p = mock.patch.object(mary, "_gemini_stream", stream)
        p.start()
        self.addCleanup(p.stop)
        return seen

    def test_tell_story_in_token_tools_and_note(self):
        net = self.net(Resp({"name": "auth_tokens/abc"}))
        voices.live_token("live:Achird", KEY, "mary", "", server.DATA,
                          memory=mary.Memory(server.DATA / "mary" / "memory.json"))
        setup = net.body()["bidiGenerateContentSetup"]
        names = [d["name"] for t in setup["tools"] for d in t.get("functionDeclarations", [])]
        self.assertIn("tell_story", names)
        self.assertIn("call tell_story", voices.LIVE_TOOLS_NOTE)

    def test_story_comes_back_without_tags(self):
        self.put(gemini_key=KEY)
        seen = self.fake([self.STORY[:30], self.STORY[30:]])
        got = self.call({"request": "a funny one about Boone"}, heard="tell me a story about Boone")
        story = got["response"]["story"]
        self.assertIn("a man named Earl.", story)
        for bad in ("[", "]", "mood", "remember"):
            self.assertNotIn(bad, story)
        body, key, deadline = seen[0]
        self.assertEqual((key, deadline), (KEY, mary.STORY_DEADLINE_S))
        self.assertEqual(body["generationConfig"]["maxOutputTokens"], 6000)
        self.assertIn(mary.STORY_PROMPT, body["systemInstruction"]["parts"][0]["text"])
        self.assertIn("a funny one about Boone", body["contents"][0]["parts"][0]["text"])
        self.fake([self.STORY, " And then he went down to the"])  # cut off by the deadline mid-sentence
        self.assertTrue(self.call({"request": "any story"})["response"]["story"].endswith("named Earl."))

    def test_emergency_heard_refuses_story(self):
        self.put(gemini_key=KEY)
        seen = self.fake([self.STORY])
        self.assertTrue(self.call({"request": "any story"}, heard=self.FELL).get("emergency"))
        self.assertEqual(seen, [])

    def test_gemini_failure_or_no_key_gives_no_story(self):
        seen = self.fake([self.STORY])
        self.assertEqual(self.call({"request": "any story"})["response"]["error"], "no_story")  # no key saved
        self.assertEqual(seen, [])
        self.put(gemini_key=KEY)
        self.fake(error=OSError("down"))
        got = self.call({"request": "any story"})["response"]
        self.assertEqual(got["error"], "no_story")
        self.assertIn("beginning, middle and end", got["note"])
        self.fake(["Once there was a man. The end."])  # too short to be a story
        self.assertEqual(self.call({"request": "any story"})["response"]["error"], "no_story")

    def test_talk_on_open_setting(self):
        self.assertTrue(self.settings()["talk_on_open"])
        self.assertIs(helpers.api("GET", "/api/mary/status")[1]["talk_on_open"], True)
        self.put(talk_on_open="0")
        self.assertFalse(self.settings()["talk_on_open"])
        self.assertIs(helpers.api("GET", "/api/mary/status")[1]["talk_on_open"], False)
        self.put(talk_on_open="maybe")  # not '1' or '0': ignored
        self.assertFalse(self.settings()["talk_on_open"])
        self.put(talk_on_open="1")
        self.assertTrue(self.settings()["talk_on_open"])

    def test_facts_mention_talk_on_open(self):
        self.assertIn("When your screen opens, you start talking", mary._app_facts_text("mary"))
        self.put(talk_on_open="0")
        self.assertNotIn("When your screen opens", mary._app_facts_text("mary"))

    def test_normal_has_room_for_a_story(self):
        body = mary._body("tell me a story", mary.Memory(server.DATA / "mary" / "memory.json"), None)
        self.assertEqual(body["generationConfig"]["maxOutputTokens"], 4000)


# --- M4a: the Gemini voice's daily limit, story writing, Live's language hint, garbled lines ---
DAILY = json.dumps({"error": {"status": "RESOURCE_EXHAUSTED", "message": (
    "You exceeded your current quota. " + "More words Google sends first. " * 5
    + "gemini-3.8-flash-tts (limit: 10 requests per day on Free Tier)")}}).encode()  # past the 120-character detail
MINUTE = b'{"error":{"status":"RESOURCE_EXHAUSTED","message":"limit: 3 requests per minute on Free Tier"}}'
KOKORO_PCM = b"\x01\x00" * 4


def clear_spent():
    voices._spent_until, voices._spent_path = 0.0, None
    (server.DATA / "mary" / "tts_spent.json").unlink(missing_ok=True)


def restart():
    """What a restart does: the module forgets, the file stays."""
    voices._spent_until, voices._spent_path = 0.0, None


class DailyVoiceLimit(M4aCase):
    def setUp(self):
        super().setUp()
        clear_spent()
        self.addCleanup(clear_spent)
        self.file = server.DATA / "mary" / "tts_spent.json"

    def spend(self):
        self.net(http_error(429, DAILY))
        with self.assertRaises(voices.VoiceError):
            voices.tts_sample("gemini:Sulafat", KEY, server.DATA)

    def kokoro(self):
        seen = []

        def stream(voice, data=None, summary=None, text="", speed=1.0):
            seen.append((voice, text, speed))
            yield {"pcm": KOKORO_PCM, "rate": 24000, "channels": 1, "cached": False, "path": "kokoro"}
        p = mock.patch.object(voices, "kokoro_stream", stream)
        p.start()
        self.addCleanup(p.stop)
        return seen

    def say(self):
        return helpers.api("POST", "/api/mary/say", {"text": "Hello there.", "mode": "normal", "rate": 0.8})

    def test_daily_429_sets_spent_and_file_with_no_second_request(self):
        for body in (DAILY, b'{"error":{"details":[{"quotaId":"GenerateRequestsPerDayPerProject-FreeTier"}]}}'):
            clear_spent()
            net = self.net(http_error(429, body))
            with self.assertRaises(voices.VoiceError) as cm:
                voices.tts_sample("gemini:Sulafat", KEY, server.DATA)
            self.assertEqual(cm.exception.kind, "tts_spent")
            self.assertEqual(len(net.requests), 1)
            self.assertTrue(voices.tts_spent(server.DATA))
            until = json.loads(self.file.read_text(encoding="utf-8"))["until"]
            self.assertAlmostEqual(until, voices.next_midnight_pacific(), delta=2)

    def test_daily_429_on_the_fallback_path_too(self):
        net = self.net(http_error(404), http_error(429, DAILY))
        with self.assertRaises(voices.VoiceError) as cm:
            voices.tts_sample("gemini:Sulafat", KEY, server.DATA)
        self.assertEqual(cm.exception.kind, "tts_spent")
        self.assertEqual(len(net.requests), 2)
        self.assertTrue(self.file.exists())

    def test_next_call_raises_before_network_even_after_a_restart(self):
        self.spend()
        for _ in (1, 2):
            net = self.net()
            with self.assertRaises(voices.VoiceError) as cm:
                voices.tts_sample("gemini:Sulafat", KEY, server.DATA)
            self.assertEqual(cm.exception.kind, "tts_spent")
            self.assertEqual(net.requests, [])
            restart()

    def test_per_minute_429_is_not_remembered(self):
        net = self.net(http_error(429, MINUTE))
        with self.assertRaises(voices.VoiceError) as cm:
            voices.tts_sample("gemini:Sulafat", KEY, server.DATA)
        self.assertEqual(cm.exception.kind, "no_gemini")
        self.assertEqual(len(net.requests), 1)
        self.assertFalse(voices.tts_spent(server.DATA))
        self.assertFalse(self.file.exists())

    def test_saved_copy_still_plays_while_spent(self):
        wav, meta = voices._cache_files("gemini:Sulafat", "Sulafat", server.DATA, voices.LINE)
        wav.parent.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(voices._wav(PCM, 24000))
        self.addCleanup(wav.unlink, missing_ok=True)
        voices._spent_until, voices._spent_path = voices.next_midnight_pacific(), self.file
        net = self.net()
        self.assertTrue(voices.tts_sample("gemini:Sulafat", KEY, server.DATA)["cached"])
        self.assertEqual(net.requests, [])

    def test_spent_expires(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps({"until": time.time() - 5}), encoding="utf-8")
        restart()
        self.assertFalse(voices.tts_spent(server.DATA))
        voices._spent_until = time.time() + 60
        self.assertTrue(voices.tts_spent(server.DATA))
        voices._spent_until = time.time() - 1
        self.assertFalse(voices.tts_spent(server.DATA))

    def test_corrupt_or_silly_file_is_not_spent(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        for text in ("not json", "[]", "{}", '{"until": "soon"}', '{"until": true}', '{"until": 1e300}',
                     '{"until": Infinity}'):
            self.file.write_text(text, encoding="utf-8")
            restart()
            self.assertFalse(voices.tts_spent(server.DATA), text)

    def test_next_midnight_pacific(self):
        def utc(*a):
            return datetime(*a, tzinfo=timezone.utc).timestamp()
        self.assertEqual(voices.next_midnight_pacific(utc(2026, 7, 1, 15, 0)), utc(2026, 7, 2, 8, 0))
        self.assertEqual(voices.next_midnight_pacific(utc(2026, 1, 1, 7, 59, 59)), utc(2026, 1, 1, 8, 0))
        self.assertEqual(voices.next_midnight_pacific(utc(2026, 1, 1, 8, 0)), utc(2026, 1, 2, 8, 0))
        self.assertEqual(voices.next_midnight_pacific(utc(2026, 12, 31, 9, 0)), utc(2027, 1, 1, 8, 0))

    def test_say_swaps_to_kokoro_on_the_first_429_and_after(self):
        self.put(gemini_key=KEY)
        seen = self.kokoro()
        net = self.net(http_error(429, DAILY))
        status, raw, headers = self.say()
        self.assertEqual((status, raw), (200, KOKORO_PCM))
        self.assertEqual(headers["Content-Type"], "audio/L16")
        self.assertEqual(headers["X-Rate"], "24000")
        self.assertEqual(headers["X-Mary-Voice"], "offline")  # M4a: the page learns of the swap
        self.assertEqual(len(net.requests), 1)
        voice, text, speed = seen[0]
        self.assertTrue(voice.startswith("kokoro:"), voice)
        self.assertEqual((text, speed), ("Hello there.", 0.8))
        net = self.net()
        status, raw, _ = self.say()
        self.assertEqual((status, raw), (200, KOKORO_PCM))
        self.assertEqual(net.requests, [])
        self.assertEqual(len(seen), 2)
        self.assertIn("using Kokoro", (server.DATA / "mary" / "audition.log").read_text(encoding="utf-8"))
        self.assertIs(helpers.api("GET", "/api/mary/status")[1]["tts_spent"], True)

    def test_say_with_no_kokoro_is_a_plain_failure(self):
        self.put(gemini_key=KEY)
        with mock.patch.object(voices, "kokoro_ready", lambda: False):
            self.net(http_error(429, DAILY))
            status, got, _ = self.say()
            self.assertEqual(status, 503)
            self.assertTrue(got["error"])
            net = self.net()
            self.assertEqual(self.say()[0], 503)
            self.assertEqual(net.requests, [])

    def test_per_minute_429_on_say_does_not_swap(self):
        self.put(gemini_key=KEY)
        seen = self.kokoro()
        self.net(http_error(429, MINUTE))
        self.assertEqual(self.say()[0], 502)
        self.assertEqual(seen, [])
        self.assertIs(helpers.api("GET", "/api/mary/status")[1]["tts_spent"], False)

    def test_tryout_gets_a_plain_sentence(self):
        body, status = server.voice_failure("tts_spent")
        self.assertEqual(status, 503)
        self.assertIn("tomorrow", body["error"])
        self.assertNotIn("429", body["error"])


class StoryWriting(M4aCase):
    PARA = " ".join(["Earl took his boat out past Ocracoke one morning in May."] * 10)

    def setUp(self):
        super().setUp()
        self.memory = mary.Memory(server.DATA / "mary" / "memory.json")
        self.now = [100.0]
        p = mock.patch.object(mary, "time", SimpleNamespace(monotonic=lambda: self.now[0]))
        p.start()
        self.addCleanup(p.stop)

    def fake(self, *steps):
        """Each step is an exception to raise, or the story to give; each call takes the next step."""
        seen, steps = [], list(steps)

        def stream(body, api_key, model="", deadline_s=None):
            seen.append(dict(body["generationConfig"]))
            step = steps.pop(0)
            if isinstance(step, Exception):
                self.now[0] += getattr(step, "took", 0)
                raise step
            yield step
        p = mock.patch.object(mary, "_gemini_stream", stream)
        p.start()
        self.addCleanup(p.stop)
        return seen

    def test_first_try_asks_for_low_thinking_and_room(self):
        seen = self.fake(self.PARA)
        info = {}
        self.assertTrue(mary.tell_story("any", self.memory, KEY, report=info))
        self.assertEqual(seen[0]["maxOutputTokens"], 6000)
        self.assertEqual(seen[0]["thinkingConfig"], {"thinkingLevel": "low"})
        self.assertEqual(len(seen), 1)
        self.assertEqual(info, {"path": "thinking_low", "words": 110})

    def test_fast_failure_retries_without_thinking(self):
        seen = self.fake(OSError("400"), self.PARA)
        info = {}
        self.assertTrue(mary.tell_story("any", self.memory, KEY, report=info))
        self.assertEqual(len(seen), 2)
        self.assertIn("thinkingConfig", seen[0])
        self.assertNotIn("thinkingConfig", seen[1])
        self.assertEqual(seen[1]["maxOutputTokens"], 6000)
        self.assertEqual(info["path"], "no_thinking")
        self.assertNotIn("error", info)

    def test_slow_failure_or_timeout_never_retries(self):
        slow = OSError("late")
        slow.took = 5
        for err in (slow, TimeoutError("timed out")):
            seen = self.fake(err, self.PARA)
            info = {}
            self.assertEqual(mary.tell_story("any", self.memory, KEY, report=info), "")
            self.assertEqual(len(seen), 1)
            self.assertEqual(info["path"], "thinking_low")
            self.assertTrue(info["error"])

    def test_only_one_retry(self):
        seen = self.fake(OSError("400"), OSError("400 again"), self.PARA)
        self.assertEqual(mary.tell_story("any", self.memory, KEY), "")
        self.assertEqual(len(seen), 2)

    def test_min_words_and_paragraphs(self):
        word_story = " ".join(["word"] * (mary.STORY_MIN_WORDS - 1)) + "."
        self.assertEqual(mary.STORY_MIN_WORDS, 100)
        self.fake(word_story)
        self.assertEqual(mary.tell_story("any", self.memory, KEY), "")
        self.fake(self.PARA + " \n \n" + self.PARA)
        story = mary.tell_story("any", self.memory, KEY)
        self.assertEqual(story.split("\n\n"), [self.PARA, self.PARA])

    def test_every_story_is_logged(self):
        self.put(gemini_key=KEY)
        log = server.DATA / "mary" / "audition.log"
        log.unlink(missing_ok=True)
        self.fake(self.PARA + " " + self.PARA, TimeoutError("x"))
        call = {"name": "tell_story", "args": {"request": "any"}}
        self.assertIn("story", helpers.api("POST", "/api/mary/skills/call", call)[1]["response"])
        self.assertEqual(helpers.api("POST", "/api/mary/skills/call", call)[1]["response"]["error"], "no_story")
        lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
        stories = [x for x in lines if x.get("event") == "story"]
        self.assertEqual([(x["ok"], x["words"], x["path"]) for x in stories],
                         [(True, 220, "thinking_low"), (False, 0, "thinking_low")])
        self.assertEqual(stories[1]["error"], "TimeoutError")


class LiveLanguageHint(M4aCase):
    BAD = b'{"error":{"status":"INVALID_ARGUMENT","message":"Invalid value at languageCodes"}}'

    def start(self, *queue, **body):
        self.put(gemini_key=KEY)
        net = self.net(*queue)
        return net, helpers.api("POST", "/api/mary/live/start", body)

    def heard(self, net, i=0):
        return net.body(i)["bidiGenerateContentSetup"]["inputAudioTranscription"]

    def test_hint_sent_and_plain_drops_it(self):
        net, (status, _, _) = self.start(Resp({"name": "auth_tokens/abc"}))
        self.assertEqual(status, 200)
        self.assertEqual(self.heard(net), {"languageCodes": ["en-US"]})
        setup = net.body()["bidiGenerateContentSetup"]
        self.assertNotIn("languageCode", setup["generationConfig"]["speechConfig"])
        self.assertEqual(setup["outputAudioTranscription"], {})
        net, (status, _, _) = self.start(Resp({"name": "auth_tokens/abc"}), plain=True)
        self.assertEqual(status, 200)
        self.assertEqual(self.heard(net), {})

    def test_400_retries_once_plain(self):
        net, (status, got, _) = self.start(http_error(400, self.BAD), Resp({"name": "auth_tokens/abc"}))
        self.assertEqual(status, 200, got)
        self.assertEqual(self.heard(net, 0), {"languageCodes": ["en-US"]})
        self.assertEqual(self.heard(net, 1), {})
        self.assertEqual(len(net.requests), 2)

    def test_second_400_or_plain_400_gives_up(self):
        net, (status, _, _) = self.start(http_error(400, self.BAD), http_error(400, self.BAD))
        self.assertEqual((status, len(net.requests)), (502, 2))
        net, (status, _, _) = self.start(http_error(400, self.BAD), plain=True)
        self.assertEqual((status, len(net.requests)), (502, 1))

    def test_key_refusal_never_retries(self):
        bad_key = b'{"error":{"message":"API key not valid."}}'
        net, (status, got, _) = self.start(http_error(400, bad_key))
        self.assertEqual((status, len(net.requests)), (400, 1))
        self.assertTrue(got["bad_key"])

    def test_unknown_name_tries_every_version_before_going_plain(self):
        unknown = b'{"error":{"message":"Unknown name languageCodes"}}'
        net, (status, got, _) = self.start(http_error(400, unknown), http_error(400, unknown),
                                           Resp({"name": "auth_tokens/abc"}))
        self.assertEqual(status, 200, got)
        self.assertEqual([self.heard(net, i) for i in range(3)],
                         [{"languageCodes": ["en-US"]}, {"languageCodes": ["en-US"]}, {}])

    def test_unknown_name_still_tries_the_next_api_version(self):
        unknown = b'{"error":{"message":"Unknown name liveConnectConstraints"}}'
        net, (status, got, _) = self.start(http_error(400, unknown), Resp({"name": "auth_tokens/abc"}), plain=True)
        self.assertEqual(status, 200, got)
        self.assertIn(voices.TOKEN_VERSIONS[1], net.requests[1].full_url)


class PageTools(M4aCase):
    def test_answered_by_the_page_not_the_server(self):
        for name in ("story_more", "end_talk"):
            got = helpers.api("POST", "/api/mary/skills/call", {"name": name, "args": {}})[1]
            self.assertEqual(got, {"response": {"error": "not_here"}, "effects": [], "say": None})

    def test_no_empty_parameters(self):
        for decl in mary.LIVE_PAGE_TOOLS:
            self.assertNotIn("parameters", decl)  # Gemini refuses an OBJECT with empty properties


class GarbledLines(M4aCase):
    CHINESE = "\u6211\u4e0d\u77e5\u9053\u4f60\u5728\u8bf4\u4ec0\u4e48"

    def turns(self):
        return [t["text"] for t in server.mary_memory().recent]

    def test_not_english(self):
        for text in ("", None, "123 !?", "hello there", "caf\u00e9 se\u00f1or", "hello \u4f60\u597d", "ab\u4f60\u597d",
                     "\U0001F600\U0001F600 ok"):
            self.assertFalse(mary.not_english(text), text)
        for text in (self.CHINESE, "\u041f\u0440\u0438\u0432\u0435\u0442", "hi \u4f60\u597d\u5417",
                     "\u0645\u0631\u062d\u0628\u0627"):
            self.assertTrue(mary.not_english(text), text)

    def test_heard_garbled_is_not_saved_or_learned(self):
        before = server.mary_memory().name
        status, got, _ = helpers.api("POST", "/api/mary/heard", {"text": "my name is " + self.CHINESE})
        self.assertEqual(status, 200)
        self.assertEqual(got, {"emergency": False, "kind": "", "say": "", "garbled": True})
        self.assertEqual(self.turns(), [])
        self.assertEqual(server.mary_memory().name, before)

    def test_emergency_in_a_garbled_line_still_fires(self):
        text = "chest pain " + self.CHINESE * 2
        self.assertTrue(mary.not_english(text))
        _, got, _ = helpers.api("POST", "/api/mary/heard", {"text": text})
        self.assertTrue(got["emergency"])
        self.assertTrue(got["say"])
        self.assertNotIn("garbled", got)
        self.assertEqual(self.turns(), [text, got["say"]])

    def test_ordinary_line_has_no_garbled_field(self):
        _, got, _ = helpers.api("POST", "/api/mary/heard", {"text": "tell me about Boone"})
        self.assertNotIn("garbled", got)
        self.assertEqual(self.turns(), ["tell me about Boone"])

    def test_her_garbled_turn_is_not_saved(self):
        self.assertEqual(helpers.api("POST", "/api/mary/live/said", {"text": self.CHINESE})[0], 200)
        self.assertEqual(self.turns(), [])
        helpers.api("POST", "/api/mary/live/said", {"text": "Well now, that's a fine story."})
        self.assertEqual(self.turns(), ["Well now, that's a fine story."])


if __name__ == "__main__":
    unittest.main()
