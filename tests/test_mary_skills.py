from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""Skills wired into Mary's talk and the server (M13, docs/skills-design.md sections 5-7 and 11):
tools in the Gemini body, the tool loop with thoughtSignature echoed back, effects as NDJSON, the 3-round cap,
a failing skill, emergencies, offline phrases, and the skill routes. Temp folders and a fake Gemini only."""
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mary
import server
import skills_core

FIXTURE = Path(__file__).resolve().parent / "skill_fixtures" / "coin_flip"
KEY = "test-key"
FLIP = {"functionCall": {"name": "coin_flip__flip", "args": {}}, "thoughtSignature": "sig-abc-123"}
OOPS_MANIFEST = {"contract": 1, "name": "oops", "version": "0.1.0", "title": "Oops", "summary": "Always fails.",
                 "instructions": "Use it in tests.", "storage": True, "needs": {"internet_hosts": []},
                 "offline": "works", "default_on": True,
                 "actions": [{"name": "go", "description": "Always fails.",
                              "inputSchema": {"type": "object", "properties": {}}}]}


def call(part):
    return mary.ToolCall(json.loads(json.dumps(part)))


class Rounds:
    """Stands in for mary._gemini_stream: request n gets script n (the last one repeats); "fail" raises."""

    def __init__(self, *scripts):
        self.scripts = list(scripts)
        self.bodies = []

    def __call__(self, body, api_key, model=""):
        self.bodies.append(json.loads(json.dumps(body)))  # a snapshot, and proof it is plain JSON
        script = self.scripts[min(len(self.bodies), len(self.scripts)) - 1]
        if script == "fail":
            raise OSError("no network")
        return iter([call(c.part) if isinstance(c, mary.ToolCall) else c for c in script])


def skills_folder(root, oops=False):
    folder = root / "skills"
    shutil.copytree(FIXTURE, folder / "coin_flip")
    if oops:
        (folder / "oops").mkdir()
        (folder / "oops" / "manifest.json").write_text(json.dumps(OOPS_MANIFEST), encoding="utf-8")
        (folder / "oops" / "skill.py").write_text("def go(ctx):\n    raise RuntimeError('boom')\n", encoding="utf-8")
    return folder


class MaryCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mary-skills-", dir=helpers.TMP))
        self.settings = {}
        db = self.dir / "skills.db"
        self.host = skills_core.SkillHost(skills_folder(self.dir, oops=True), self.dir, lambda: sqlite3.connect(db),
                                          lambda: dict(self.settings), self.settings.update)
        self.host.load(is_blocked=mary.skill_blocked)
        self.assertEqual(sorted(self.host.skills), ["coin_flip", "oops"], self.host.load_errors)
        self.memory = mary.Memory(self.dir / "memory.json")
        self.seen = []
        self._real = mary._gemini_stream

    def tearDown(self):
        mary._gemini_stream = self._real

    def say(self, text, *scripts, key=KEY, skills=True, screen=None):
        self.fake = mary._gemini_stream = Rounds(*(scripts or (["I hear you."],)))
        return mary.reply(text, self.memory, key, skills=self.host if skills else None, screen=screen,
                          on_effect=self.seen.append)

    def test_body_has_tools_and_instruction_text(self):
        self.say("Hello there", ["Hello!"], screen="coin_flip")
        body = self.fake.bodies[0]
        names = [d["name"] for d in body["tools"][0]["functionDeclarations"]]
        self.assertIn("open_skill", names)  # M13b
        self.assertIn("use_skill", names)  # M13b
        self.assertNotIn("coin_flip__flip", names)  # M13b
        self.assertIn("set_skill", names)
        system = body["systemInstruction"]["parts"][0]["text"]
        self.assertIn(skills_core.INSTRUCTIONS_HEAD, system)
        self.assertIn("Open now (Coin flip): ", system)  # M13b
        self.assertIn("What's on the screen now (Coin flip): A coin, not flipped yet.", system)

    def test_without_skills_the_body_is_as_before(self):
        r = self.say("Hello there", ["Hello!"], skills=False)
        body = self.fake.bodies[0]
        self.assertNotIn("tools", body)
        self.assertNotIn(skills_core.INSTRUCTIONS_HEAD, body["systemInstruction"]["parts"][0]["text"])
        self.assertEqual(body, json.loads(json.dumps(mary._body("Hello there", mary.Memory(self.dir / "x.json"),
                                                                None))))
        self.assertEqual((r["text"], r["effects"]), ("Hello!", []))

    def test_function_call_round_trip_echoes_the_signature(self):
        r = self.say("Could you flip a coin?", ["Let me see.", call(FLIP)], ["[mood: happy] It came up nicely!"])
        self.assertEqual(len(self.fake.bodies), 2)
        model_turn, answer_turn = self.fake.bodies[1]["contents"][-2:]
        self.assertEqual(model_turn, {"role": "model", "parts": [{"text": "Let me see."}, FLIP]})
        response = answer_turn["parts"][0]["functionResponse"]
        self.assertEqual((answer_turn["role"], response["name"]), ("user", "coin_flip__flip"))
        self.assertIn(response["response"]["side"], ("heads", "tails"))
        self.assertNotIn("say", response["response"])
        self.assertIn("tools", self.fake.bodies[1])
        self.assertEqual([e["kind"] for e in r["effects"]], ["show_screen", "coin"])
        self.assertEqual(self.seen, r["effects"])
        self.assertEqual((r["text"], r["mood"]), ("Let me see. It came up nicely!", "happy"))

    def test_use_skill_gets_the_screen(self):  # M13b: what's on screen needs no opening
        use = {"functionCall": {"name": "use_skill", "args": {"action": "flip"}}}
        r = self.say("Flip a coin", [call(use)], screen="coin_flip")
        self.assertIn("coin", [e["kind"] for e in r["effects"]])

    def test_three_round_cap(self):
        r = self.say("Flip a coin", [call(FLIP)])  # she keeps asking for another flip
        self.assertEqual(len(self.fake.bodies), mary.MAX_TOOL_ROUNDS + 1)
        self.assertEqual(len(r["effects"]), 2 * mary.MAX_TOOL_ROUNDS)
        self.assertEqual(r["text"], "")  # she said nothing
        self.assertTrue(r["notice"].startswith("It's "))  # the skill's own lines, on screen only

    def test_not_working_skill(self):
        oops = {"functionCall": {"name": "oops__go", "args": {}}}
        r = self.say("Do the thing", [call(oops)], ["Oh dear, that didn't work."])
        answer = self.fake.bodies[1]["contents"][-1]["parts"][0]["functionResponse"]
        self.assertEqual(answer["response"], {"error": "not_working"})
        self.assertEqual(r["text"], "Oh dear, that didn't work.")
        r = self.say("Do the thing", [call(oops)], "fail")  # the follow-up fails too: the core's line
        self.assertEqual((r["text"], r["notice"]), ("", skills_core.SAY_NOT_WORKING))
        bad = {"functionCall": {"name": "set_skill", "args": {"name": "nope"}}}
        r = self.say("Hm", [call(bad)], "fail")  # no line from the skill at all
        self.assertEqual((r["text"], r["notice"], r["mood"]), ("", mary.NOT_WORKING_TEXT, "sorry"))

    def test_emergency_gets_no_tools_and_runs_nothing(self):
        r = self.say("I can't breathe", [call(FLIP)], ["More."])
        self.assertEqual(len(self.fake.bodies), 1)
        self.assertNotIn("tools", self.fake.bodies[0])
        self.assertNotIn(skills_core.INSTRUCTIONS_HEAD, self.fake.bodies[0]["systemInstruction"]["parts"][0]["text"])
        self.assertEqual((r["effects"], self.seen), ([], []))
        self.assertTrue(r["emergency"])
        r = self.say("I can't breathe, flip a coin", key="")
        self.assertEqual(r["effects"], [])

    def test_offline_phrase_without_a_key(self):
        r = self.say("flip a coin", key="")
        self.assertEqual(self.fake.bodies, [])
        self.assertIn(r["notice"], ("It's heads.", "It's tails."))  # no model: screen only
        self.assertEqual(r["text"], "")
        self.assertEqual([e["kind"] for e in self.seen], ["show_screen", "coin"])
        self.assertEqual((r["error"], r["mood"]), (mary.NO_KEY, "talking"))
        r = self.say("please flip a coin", "fail")  # Gemini failed: the phrase still works
        self.assertIn(r["notice"], ("It's heads.", "It's tails."))
        self.assertEqual(r["error"], mary.NO_GEMINI)
        r = self.say("turn the coin flip off", key="")
        self.assertEqual((r["text"], r["notice"]), ("", "Coin flip is off now."))
        self.assertFalse(self.host.enabled("coin_flip"))
        r = self.say("what a lovely day", key="")
        self.assertEqual((r["text"], r["notice"], r["effects"]), ("", mary.OFFLINE_TEXT, []))


class ServerCase(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        self.dir = Path(tempfile.mkdtemp(prefix="server-skills-", dir=helpers.TMP))
        patcher = mock.patch.object(server, "SKILLS_DIR", skills_folder(self.dir))
        patcher.start()
        self.addCleanup(patcher.stop)
        server.set_skill_host_for_tests(None)
        self.addCleanup(server.set_skill_host_for_tests, None)
        self._real = mary._gemini_stream
        self.addCleanup(setattr, mary, "_gemini_stream", self._real)

    def put(self, path, body):
        return helpers.api("PUT", path, body)

    def test_stream_writes_effect_lines(self):
        self.put("/api/settings", {"gemini_key": KEY})
        fake = mary._gemini_stream = Rounds([call(FLIP)], ["It came up nicely!"])
        status, raw, _ = helpers.api("POST", "/api/mary/talk?stream=1",
                                     {"text": "Could you flip a coin?", "screen": "coin_flip"})
        self.assertEqual(status, 200)
        lines = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
        kinds = [x["effect"]["kind"] for x in lines if "effect" in x]
        self.assertEqual(kinds, ["show_screen", "coin"])
        self.assertTrue(lines[-1]["done"])
        self.assertEqual(len(lines[-1]["effects"]), 2)
        self.assertEqual(lines[-1]["text"], "It came up nicely!")
        self.assertIn("What's on the screen now", fake.bodies[0]["systemInstruction"]["parts"][0]["text"])
        self.assertEqual(fake.bodies[1]["contents"][-2]["parts"], [FLIP])

    def test_list_and_static_files(self):
        status, body, _ = helpers.api("GET", "/api/mary/skills")
        self.assertEqual(status, 200)
        (skill,) = body["skills"]
        self.assertEqual((skill["name"], skill["on"], skill["script"], skill["style"]),
                         ("coin_flip", True, "/skills/coin_flip/screen.js", None))
        status, raw, headers = helpers.api("GET", "/skills/coin_flip/screen.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        self.assertEqual(raw, (FIXTURE / "screen.js").read_bytes())
        for bad in ("/skills/coin_flip/skill.py", "/skills/coin_flip/manifest.json", "/skills/coin_flip/screen.css",
                    "/skills/coin_flip/../../server.py", "/skills/coin_flip/..%2f..%2fserver.py",
                    "/skills/nope/screen.js", "/skills/../server.py"):
            status, body, _ = helpers.api("GET", bad)
            self.assertEqual(status, 404, bad)
            self.assertNotIn(b"import", body if isinstance(body, bytes) else b"")

    def test_call_event_view_and_broken(self):
        status, body, _ = helpers.api("POST", "/api/mary/skills/call", {"name": "coin_flip__flip", "args": {}})
        self.assertEqual(status, 200)
        self.assertIn(body["response"]["side"], ("heads", "tails"))
        self.assertEqual(body["say"], f"It's {body['response']['side']}.")
        self.assertEqual(helpers.api("POST", "/api/mary/skills/call", {"name": "coin_flip__flip"}, tracker=False)[0],
                         403)
        status, body, _ = helpers.api("GET", "/api/mary/skills/coin_flip/view")
        self.assertTrue(body["text"].startswith("A quarter showing "))
        status, body, _ = helpers.api("POST", "/api/mary/skills/coin_flip/event", {"event": {"type": "tap"}})
        self.assertIn(body["response"]["side"], ("heads", "tails"))
        self.assertEqual(helpers.api("POST", "/api/mary/skills/coin_flip/broken", {})[1]["ok"], True)
        status, body, _ = helpers.api("GET", "/api/mary/skills/nope/view")
        self.assertEqual((status, body["error"]), (404, server.SKILL_UNKNOWN))

    def test_switch_and_helper_lock(self):
        status, body, _ = self.put("/api/mary/skills/coin_flip", {"on": False})
        self.assertEqual((status, body["on"]), (200, False))
        self.assertEqual(helpers.api("GET", "/api/settings")[1]["skills_off"], '["coin_flip"]')
        body = self.put("/api/mary/skills/coin_flip/lock", {"state": "on"})[1]
        self.assertEqual((body["locked"], body["on"]), ("on", True))
        self.assertEqual(self.put("/api/mary/skills/coin_flip", {"on": False})[1]["error"], "locked")
        body = self.put("/api/mary/skills/coin_flip/lock", {"state": None})[1]
        self.assertEqual((body["locked"], body["on"]), (None, False))
        self.assertEqual(self.put("/api/mary/skills/coin_flip", {"on": "yes"})[0], 400)
        self.assertEqual(self.put("/api/mary/skills/coin_flip/lock", {"state": "maybe"})[0], 400)
        self.assertEqual(self.put("/api/mary/skills/nope", {"on": True})[0], 404)

    def test_settings_route_cannot_write_skill_lists(self):
        status, body, _ = self.put("/api/settings", {"skills_off": '["coin_flip"]', "skills_on": "[]",
                                                     "skills_locked": '{"coin_flip": "off"}', "room": "12"})
        self.assertEqual(status, 200)
        self.assertEqual(body["room"], "12")
        for key in ("skills_off", "skills_on", "skills_locked"):
            self.assertNotIn(key, body)
        self.assertTrue(server.skill_host().enabled("coin_flip"))


if __name__ == "__main__":
    unittest.main()
