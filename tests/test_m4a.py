from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M4a: the Live token body, talk modes, the emergency check on Live, app facts, the listen-wait skill actions,
the pace/speed plumbing and the /api/mary/say checks. No network: voices._open is faked."""
import shutil
import tempfile
import json
import unittest
from pathlib import Path
from unittest import mock

import mary
import server
import voices
from tests.test_voices import KEY, Net, Resp

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
        self.assertIn("speak slowly and clearly", slow)
        normal = self.start(voice_rate="1.0")["systemInstruction"]["parts"][0]["text"]
        self.assertNotIn("unhurried pace", normal)
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
        self.assertEqual(names, {"remember_fact", "set_their_name", "tell_story"})
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
    STORY = ("[mood: happy] " + " ".join(["Once upon a time in Boone there lived a man named Earl."] * 6)
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
        self.assertEqual(body["generationConfig"]["maxOutputTokens"], 1500)
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
        self.assertEqual(body["generationConfig"]["maxOutputTokens"], 1200)


if __name__ == "__main__":
    unittest.main()
