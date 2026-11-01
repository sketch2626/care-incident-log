from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M13b: tool groups. Gemini gets only open_skill, use_skill and set_skill however many skills there are; a group opens
by name, the picture sets a game aside and it comes back, emergencies get no tools, offline phrases still work.
Temp folders, a fake Gemini and (for the route) the in-process server. Never the real Gemini."""
import copy
import json
import shutil
import sqlite3
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import mary
import server
import skills_core

REAL = Path(__file__).resolve().parent.parent / "skills"
KEY = "test-key"
GAME_WORDS = '{"words": ["CAT", "DOG", "BIRD", "FISH"], "level": 1}'
BASE = {"contract": 1, "version": "0.1.0", "instructions": "Use it in tests.", "storage": True,
        "needs": {"internet_hosts": []}, "offline": "works", "default_on": True}
STAND_IN_PICTURES = '''
def show_picture(ctx, what=""):
    ctx.effect("show_screen", {})
    ctx.effect("picture", {"title": what})
    return {"title": what, "say": "Here."}


def close_picture(ctx):
    ctx.effect("leave_screen", {})
    return {"closed": True}
'''
ECHO = '''
def say_it(ctx, text=""):
    return {"got": text}


def ping(ctx):
    return {"ok": True}
'''


def act(name, props=None):
    return {"name": name, "description": f"Test action {name}.",
            "inputSchema": {"type": "object", "properties": props or {}}}


def text_prop(key="text"):
    return {key: {"type": "string", "description": "The words."}}


def write_skill(root, name, actions, source, **fields):
    folder = Path(root) / name
    folder.mkdir(parents=True)
    manifest = dict(BASE, name=name, title=fields.pop("title", name.replace("_", " ").capitalize()),
                    summary=fields.pop("summary", f"The {name} group."), actions=actions, **fields)
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "skill.py").write_text(textwrap.dedent(source), encoding="utf-8")


def call(part):
    return mary.ToolCall(json.loads(json.dumps(part)))


class Rounds:
    """Stands in for mary._gemini_stream: request n gets script n (the last one repeats)."""

    def __init__(self, *scripts):
        self.scripts = list(scripts)
        self.bodies = []

    def __call__(self, body, api_key, model=""):
        self.bodies.append(json.loads(json.dumps(body)))
        script = self.scripts[min(len(self.bodies), len(self.scripts)) - 1]
        return iter([call(c.part) if isinstance(c, mary.ToolCall) else c for c in script])


def fc(name, args=None, sig=None):
    part = {"functionCall": {"name": name, "args": args or {}}}
    if sig:
        part["thoughtSignature"] = sig
    return part


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tool-groups-", dir=helpers.TMP))
        self.settings = {}
        self.memory = mary.Memory(self.dir / "memory.json")
        self.seen = []
        self._real = mary._gemini_stream
        self.addCleanup(setattr, mary, "_gemini_stream", self._real)

    def build(self, real=(), fakes=(), stand_in_pictures=False, echo=False):
        """A SkillHost over copies of real skills plus fake ones."""
        folder = self.dir / f"skills{len(list(self.dir.glob('skills*')))}"
        folder.mkdir()
        for name in real:
            shutil.copytree(REAL / name, folder / name, ignore=shutil.ignore_patterns("__pycache__"))
        for name, count in fakes:
            acts = [act(f"a{i}") for i in range(1, count + 1)]
            write_skill(folder, name, acts, "\n".join(f"def a{i}(ctx):\n    return {{'ok': True}}\n"
                                                      for i in range(1, count + 1)))
        if stand_in_pictures:
            write_skill(folder, "pictures", [act("show_picture", text_prop("what")), act("close_picture")],
                        STAND_IN_PICTURES, title="Pictures", summary="Shows a picture of anything.")
        if echo:
            write_skill(folder, "echo", [act("say_it", text_prop()), act("ping")], ECHO, title="Echo")
        db = self.dir / f"s{id(folder)}.db"
        host = skills_core.SkillHost(folder, self.dir, lambda: sqlite3.connect(db), lambda: dict(self.settings),
                                     self.settings.update)
        host.load(is_blocked=mary.skill_blocked)
        self.assertEqual(host.load_errors, {})
        return host

    def say(self, text, *scripts, key=KEY, host=None, screen=None):
        self.fake = mary._gemini_stream = Rounds(*(scripts or (["I hear you."],)))
        return mary.reply(text, self.memory, key, skills=host, screen=screen, on_effect=self.seen.append)

    @staticmethod
    def names(host):
        return [d["name"] for t in host.gemini_tools() for d in t["functionDeclarations"]]

    def start_game(self, host):
        host.call("open_skill", {"name": "word_search"})
        out = host.call("use_skill", {"action": "start", "details": GAME_WORDS})
        self.assertNotIn("error", out["response"], out)
        return out


class Ceiling(Base):
    def test_tool_count_is_the_same_with_one_skill_or_ten(self):
        self.memory.store = server.memory_store()  # her three memory tools ride along in Normal talk
        counts = {}
        for n in (1, 10):
            host = self.build(fakes=[(f"fake{i}", 9) for i in range(n)])
            body = mary._body("Hello", self.memory, None, skills=host)
            normal = len(body["tools"][0]["functionDeclarations"])
            live = len(host.gemini_tools()[0]["functionDeclarations"]) + len(mary.LIVE_CORE_TOOLS)
            counts[n] = (normal, live)
            self.assertLessEqual(normal, 12)
            self.assertLessEqual(live, 13)   # M18: Live's one screen tool; normal stays 12
            names = [d["name"] for d in body["tools"][0]["functionDeclarations"]]
            self.assertFalse([x for x in names if "__" in x], names)
        self.assertEqual(counts[1], counts[10])


class PicturesHiddenBehindTheGame(Base):
    def test_word_search_hides_picture_actions(self):
        host = self.build(real=["word_search", "pictures", "voice_comfort"])
        self.assertNotIn("show_picture", self.names(host))
        text = host.instruction_text("word_search")
        self.assertNotIn("show_picture", text)
        self.assertIn("check", text)
        self.assertIn("- Pictures: ", text)  # pictures is in the one-line menu
        out = host.call("use_skill", {"action": "show_picture", "details": "a cardinal"}, screen="word_search")
        self.assertEqual(out["response"]["error"], "not_open")
        self.assertEqual(out["response"]["open"], "pictures")
        self.assertEqual(out["effects"], [])
        self.assertEqual(host.skills["pictures"].state, {})  # no picture was fetched or shown
        self.assertIsNone(host.opened)


class SwitchingInOneTurn(Base):
    def test_open_then_use_then_words(self):
        host = self.build(real=["word_search"], stand_in_pictures=True)
        open_part = fc("open_skill", {"name": "pictures"}, "sig-open-1")
        use_part = fc("use_skill", {"action": "show_picture", "details": "a cardinal"}, "sig-use-2")
        r = self.say("Show me a cardinal", [call(open_part)], [call(use_part)], ["[mood: happy] There it is!"],
                     host=host, screen="word_search")
        self.assertEqual(len(self.fake.bodies), 3)
        kinds = [e["kind"] for e in r["effects"]]
        self.assertEqual(kinds, ["show_screen", "picture"])
        self.assertEqual([e["kind"] for e in self.seen], kinds)  # on_effect heard them too
        self.assertEqual(host.opened, "pictures")
        self.assertIn("There it is!", r["text"])
        # every thoughtSignature comes back unchanged
        third = self.fake.bodies[2]["contents"]
        self.assertEqual(third[-4], {"role": "model", "parts": [open_part]})
        self.assertEqual(third[-2], {"role": "model", "parts": [use_part]})
        second_model = self.fake.bodies[1]["contents"][-2]
        self.assertEqual(second_model["parts"][0]["thoughtSignature"], "sig-open-1")
        self.assertEqual(third[-1]["parts"][0]["functionResponse"]["name"], "use_skill")

    def test_open_alone_gives_no_effects(self):
        host = self.build(real=["word_search"], stand_in_pictures=True)
        r = self.say("Hmm", [call(fc("open_skill", {"name": "pictures"}, "s"))], ["Okay."], host=host,
                     screen="word_search")
        self.assertEqual((r["effects"], self.seen), ([], []))
        answer = self.fake.bodies[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]
        self.assertEqual(answer["opened"], "Pictures")


class AsideAndBack(Base):
    def test_picture_sets_the_game_aside_and_it_comes_back_unchanged(self):
        host = self.build(real=["word_search", "pictures"])
        self.start_game(host)
        host.call("use_skill", {"action": "check", "details": "cat"}, screen="word_search")
        state = host.skills["word_search"].state
        before = copy.deepcopy(state["puzzle"])
        self.assertIn("CAT", before["found"])
        seen_before = host.view("word_search")
        host.set_aside("word_search")
        out = host.call("use_skill", {"action": "close_picture"}, screen="pictures")
        res = out["response"]
        self.assertEqual(res["came_back"], "Word search")
        self.assertIn("is back on the screen", res["note"])
        self.assertEqual(host.opened, "word_search")
        self.assertEqual(host.skills["word_search"].state["puzzle"], before)
        self.assertEqual(host.view("word_search"), seen_before)
        again = host.call("use_skill", {"action": "start"}, screen="word_search")["response"]
        self.assertTrue(again["resumed"])
        self.assertIn("CAT", host.skills["word_search"].state["puzzle"]["found"])

    def test_set_aside_line_only_when_something_is_aside(self):
        host = self.build(real=["word_search", "pictures"])
        self.start_game(host)
        host.set_aside("word_search")
        self.assertIn("Set aside for now", host.instruction_text("pictures"))
        host.set_aside(None)
        self.assertNotIn("Set aside for now", host.instruction_text("pictures"))
        host.set_aside("nonsense")
        self.assertIsNone(host.aside)


class LiveRoute(Base):
    def setUp(self):
        super().setUp()
        helpers.reset_db()
        folder = self.dir / "live-skills"
        folder.mkdir()
        for name in ("word_search", "pictures", "voice_comfort"):
            shutil.copytree(REAL / name, folder / name, ignore=shutil.ignore_patterns("__pycache__"))
        p = mock.patch.object(server, "SKILLS_DIR", folder)
        p.start()
        self.addCleanup(p.stop)
        server.set_skill_host_for_tests(None)
        self.addCleanup(server.set_skill_host_for_tests, None)
        self.host = server.skill_host()

    def post(self, name, args=None, **extra):
        return helpers.api("POST", "/api/mary/skills/call", dict({"name": name, "args": args or {}}, **extra))[1]

    def test_open_skill_answer(self):
        got = self.post("open_skill", {"name": "word_search"})
        res = got["response"]
        self.assertIn("how", res)
        self.assertIn("start", [a["name"] for a in res["actions"]])
        start = next(a for a in res["actions"] if a["name"] == "start")
        self.assertIn("words", start["needs"])
        self.assertEqual(got["effects"], [])

    def test_use_skill_plain_words_and_json(self):
        self.post("open_skill", {"name": "word_search"})
        got = self.post("use_skill", {"action": "start", "details": GAME_WORDS})  # a JSON object
        self.assertNotIn("error", got["response"], got)
        got = self.post("use_skill", {"action": "check", "details": "cat"})  # plain words
        self.assertEqual(got["response"].get("found"), "CAT", got)

    def test_screen_in_the_body_needs_no_opening(self):
        self.post("open_skill", {"name": "word_search"})
        self.post("use_skill", {"action": "start", "details": GAME_WORDS})
        self.host.opened = None
        got = self.post("use_skill", {"action": "check", "details": "dog"}, screen="word_search")
        self.assertEqual(got["response"].get("found"), "DOG", got)
        got = self.post("use_skill", {"action": "check", "details": "bird"})
        self.assertEqual(got["response"]["error"], "not_open")

    def test_aside_round_trip(self):
        self.post("open_skill", {"name": "word_search"})
        self.post("use_skill", {"action": "start", "details": GAME_WORDS})
        got = self.post("use_skill", {"action": "close_picture"}, screen="pictures", aside="word_search")
        self.assertEqual(got["response"].get("came_back"), "Word search", got)
        self.assertEqual(self.host.opened, "word_search")

    def test_emergency_refuses_both_tools(self):
        self.post("open_skill", {"name": "voice_comfort"})
        for name, args in (("open_skill", {"name": "word_search"}),
                           ("use_skill", {"action": "louder"})):
            got = self.post(name, args, heard="I think I'm having a heart attack")
            self.assertTrue(got["emergency"])
            self.assertEqual(got["response"], {"error": "emergency"})
            self.assertEqual(self.host.opened, "voice_comfort")


class OpenToolAnswers(Base):
    def test_every_real_skill_opens_without_touching_the_screen(self):
        host = self.build(real=["word_search", "pictures", "voice_comfort"])
        for name, skill in host.skills.items():
            out = host.call("open_skill", {"name": name})
            self.assertEqual(out["effects"], [], name)
            self.assertNotIn("error", out["response"], name)
            listed = [a["name"] for a in out["response"]["actions"]]
            self.assertEqual(listed, [a["name"] for a in skill.manifest["actions"]], name)
            self.assertEqual(out["response"]["how"], skill.manifest["instructions"])
            again = host.call("open_skill", {"name": name})  # twice is harmless
            self.assertEqual(again["response"], out["response"])
            self.assertEqual(host.opened, name)

    def test_off_unknown_and_tripped(self):
        host = self.build(real=["word_search", "voice_comfort"])
        self.assertEqual(host.call("open_skill", {"name": "nothing_here"})["response"], {"error": "unknown_skill"})
        host.set_skill("word_search", False, by="voice")
        self.assertEqual(host.call("open_skill", {"name": "word_search"})["response"], {"error": "off"})
        self.assertNotIn("word_search", host.instruction_text().split("\n", 3)[1])
        host.skills["voice_comfort"].tripped = True
        self.assertEqual(host.call("open_skill", {"name": "voice_comfort"})["response"], {"error": "not_working"})
        self.assertEqual(host.call("use_skill", {"action": "louder"})["response"], {"error": "not_working"})
        self.assertEqual(host.call("use_skill", {"action": "more_time"})["response"], {"error": "not_working"})


class AlwaysOnHand(Base):
    def test_louder_runs_unopened_and_more_time_does_not(self):
        host = self.build(real=["word_search", "voice_comfort"])
        host.call("open_skill", {"name": "word_search"})
        out = host.call("use_skill", {"action": "louder"})
        self.assertNotIn("error", out["response"], out)
        self.assertEqual(host.opened, "word_search")  # it did not move the open group
        out = host.call("use_skill", {"action": "more_time"})
        self.assertEqual(out["response"]["error"], "not_open")
        self.assertEqual(out["response"]["open"], "voice_comfort")
        self.assertEqual(host.opened, "word_search")


class Safety(Base):
    HEART = "I think I'm having a heart attack"

    def test_emergency_body_has_no_tools_and_no_skill_text(self):
        host = self.build(real=["word_search"])
        self.memory.store = server.memory_store()
        self.assertEqual(mary.is_emergency(self.HEART), "medical")
        body = mary._body(self.HEART, self.memory, "medical", skills=host)
        self.assertNotIn("tools", body)
        self.assertNotIn(skills_core.INSTRUCTIONS_HEAD, body["systemInstruction"]["parts"][0]["text"])

    def test_gemini_open_skill_on_an_emergency_line_runs_nothing(self):
        host = self.build(real=["word_search"])
        r = self.say(self.HEART, [call(fc("open_skill", {"name": "word_search"}, "s1"))], ["Stay calm."], host=host)
        self.assertEqual(r["emergency"], "medical")
        self.assertEqual((r["effects"], host.opened), ([], None))
        self.assertEqual(len(self.fake.bodies), 1)
        self.assertNotIn("tools", self.fake.bodies[0])

    def test_emergency_words_come_out_with_no_skills_or_a_broken_host(self):
        class Broken:
            def gemini_tools(self):
                raise RuntimeError("boom")

            instruction_text = offline_match = call = gemini_tools

        for skills in (None, Broken()):
            self.memory = mary.Memory(self.dir / f"m{id(skills)}.json")
            r = self.say(self.HEART, ["I'm here."], host=skills)
            self.assertEqual(r["emergency"], "medical")
            self.assertIn(mary.EMERGENCY_TEXT["medical"], r["text"])
        offline = mary.reply(self.HEART, mary.Memory(self.dir / "o.json"), "", skills=Broken())
        self.assertIn(mary.EMERGENCY_TEXT["medical"], offline["text"])


class OfflineNoGemini(Base):
    def setUp(self):
        super().setUp()

        def never(*a, **k):
            raise AssertionError("Gemini must not be called with no key")
        mary._gemini_stream = never
        self.host = self.build(real=["word_search", "voice_comfort"])

    def hear(self, text):
        return mary.reply(text, self.memory, "", skills=self.host, on_effect=self.seen.append)

    def test_phrases_run_with_no_group_open(self):
        helpers.api("PUT", "/api/settings", {"voice_volume": "0.5"})
        r = self.hear("louder")
        self.assertNotEqual(r["text"], mary.OFFLINE_TEXT, r)
        r = self.hear("word search")
        self.assertIn("show_screen", [e["kind"] for e in r["effects"]], r)
        r = self.hear("give me a hint")
        self.assertNotEqual(r["text"], mary.OFFLINE_TEXT, r)
        self.assertIn("hint", [e["kind"] for e in r["effects"]], r)

    def test_turn_off_and_on_by_words(self):
        for off in ("turn word search off", "stop word search"):
            r = self.hear(off)
            self.assertEqual(self.host.enabled("word_search"), False, off)
            self.assertEqual([e["kind"] for e in r["effects"]], ["settings"])
            self.hear("turn word search on")
            self.assertTrue(self.host.enabled("word_search"), off)

    def test_set_skill_through_the_fake_gemini(self):
        part = fc("set_skill", {"name": "word_search", "on": False}, "sig-set")
        r = self.say("Please stop the word search", [call(part)], ["Done."], host=self.host)
        self.assertFalse(self.host.enabled("word_search"))
        self.assertEqual([e["kind"] for e in r["effects"]], ["settings"])
        self.assertEqual(self.fake.bodies[1]["contents"][-2]["parts"], [part])


class BadInput(Base):
    def test_use_skill_without_an_action(self):
        host = self.build(echo=True)
        self.assertEqual(host.call("use_skill", {})["response"]["error"], "bad_input")
        self.assertEqual(host.call("use_skill", {"details": "x"})["response"]["error"], "bad_input")

    def test_details_on_a_no_args_action_are_ignored(self):
        host = self.build(echo=True)
        host.call("open_skill", {"name": "echo"})
        out = host.call("use_skill", {"action": "ping", "details": "some words {nope"})
        self.assertEqual(out["response"], {"ok": True})

    def test_garbage_json_goes_to_the_text_field(self):
        host = self.build(echo=True)
        host.call("open_skill", {"name": "echo"})
        out = host.call("use_skill", {"action": "say_it", "details": "{oops"})
        self.assertEqual(out["response"], {"got": "{oops"})
        out = host.call("use_skill", {"action": "say_it", "details": '{"text": "hi"}'})
        self.assertEqual(out["response"], {"got": "hi"})
        out = host.call("use_skill", {"action": "no_such"})
        self.assertEqual(out["response"]["error"], "no_such_action")


if __name__ == "__main__":
    unittest.main()
