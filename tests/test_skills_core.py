from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""Skills core (docs/skills-design.md sections 3-7): store, files, settings, fetch, guard and trip rule,
switches and locks, offline matching, Gemini tools and instruction text. Temp folders only, no network."""
import email.message
import io
import json
import shutil
import sqlite3
import tempfile
import textwrap
import unittest
import urllib.parse
import urllib.request
import urllib.response
from pathlib import Path
from unittest import mock

import mary
import skills_core
from skills_core import SkillError, SkillFetchError

FIXTURES = Path(__file__).resolve().parent / "skill_fixtures"
BASE = {"contract": 1, "version": "0.1.0", "summary": "A test skill.", "instructions": "Use it in tests.",
        "storage": True, "needs": {"internet_hosts": []}, "offline": "works", "default_on": True}

STORE_SOURCE = '''
def save(ctx, text):
    ctx.store.put("k", text)
    return {"saved": True}


def read(ctx):
    return {"value": ctx.store.get("k"), "keys": ctx.store.keys()}
'''


def action(name, props=None, required=None, phrases=None):
    """One action for a test card."""
    out = {"name": name, "description": f"Test action {name}.",
           "inputSchema": {"type": "object", "properties": props or {}}}
    if required:
        out["inputSchema"]["required"] = required
    if phrases:
        out["offline_phrases"] = phrases
    return out


def fake_web(routes):
    """Stands in for the https handler: routes {host: (code, headers, body)}. Returns (patcher, urls asked)."""
    asked = []

    def https_open(handler, req):
        asked.append(req.full_url)
        code, headers, body = routes[urllib.parse.urlsplit(req.full_url).hostname]
        msg = email.message.Message()
        for key, value in headers.items():
            msg[key] = value
        resp = urllib.response.addinfourl(io.BytesIO(body), msg, req.full_url, code)
        resp.msg = "OK"
        return resp

    return mock.patch.object(urllib.request.HTTPSHandler, "https_open", https_open), asked


class SkillsTestCase(unittest.TestCase):
    """A temp skills folder, a temp sqlite file and in-memory settings for each test."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="skills-core-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.skills_dir = self.dir / "skill_code"
        self.skills_dir.mkdir()
        self.settings = {}

    def write_skill(self, name, source, actions=(), **fields):
        folder = self.skills_dir / name
        folder.mkdir()
        manifest = dict(BASE, name=name, title=fields.pop("title", name.replace("_", " ").capitalize()),
                        actions=list(actions), **fields)
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (folder / "skill.py").write_text(textwrap.dedent(source), encoding="utf-8")

    def add_coin(self):
        shutil.copytree(FIXTURES / "coin_flip", self.skills_dir / "coin_flip",
                        ignore=shutil.ignore_patterns("__pycache__"))

    def host(self, **kwargs):
        db = self.dir / "test.db"
        host = skills_core.SkillHost(self.skills_dir, self.dir, lambda: sqlite3.connect(db),
                                     lambda: dict(self.settings), self.settings.update, **kwargs)
        host.load()
        return host

    def log_lines(self):
        log = self.dir / "skills.log"
        return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


class StoreFilesSettingsTest(SkillsTestCase):

    def test_each_skill_sees_only_its_own_store(self):
        for name in ("alpha", "beta"):
            self.write_skill(name, STORE_SOURCE, [action("save", {"text": {"type": "string", "description": "t"}},
                                                         ["text"]), action("read")])
        host = self.host()
        host.call("alpha__save", {"text": "a"})
        host.call("beta__save", {"text": "b"})
        self.assertEqual(host.call("alpha__read")["response"], {"value": "a", "keys": ["k"]})
        host.context("alpha").store.delete("k")
        self.assertEqual(host.call("alpha__read")["response"], {"value": None, "keys": []})
        self.assertEqual(host.call("beta__read")["response"], {"value": "b", "keys": ["k"]})

    def test_store_limits(self):
        self.write_skill("alpha", STORE_SOURCE, [action("read")])
        self.write_skill("nostore", "def go(ctx):\n    return {}\n", [action("go")], storage=False)
        host = self.host()
        store = host.context("alpha").store
        with self.assertRaises(SkillError):
            store.put("big", "x" * (64 * 1024 + 1))
        with self.assertRaises(SkillError):
            store.put("bad", {1, 2})
        with self.assertRaises(SkillError):
            host.context("nostore").store.get("k")

    def test_files_stay_inside_the_skill_folder(self):
        self.add_coin()
        files = self.host().context("coin_flip").files
        files.write_text("notes/a.txt", "hi")
        self.assertEqual(files.read_text("notes/a.txt"), "hi")
        self.assertEqual(files.list(), ["notes/a.txt"])
        self.assertTrue((self.dir / "skills" / "coin_flip" / "notes" / "a.txt").is_file())
        for bad in ("../escape.txt", "notes/../../x.txt", str(self.dir / "x.txt"), ""):
            with self.assertRaises(SkillError):
                files.write_text(bad, "no")

    def test_settings_only_from_the_card(self):
        self.write_skill("talky", "def go(ctx):\n    ctx.settings_put('voice_rate', '1.2')\n    return {}\n",
                         [action("go")], settings=["voice_rate"])
        self.write_skill("greedy", "def go(ctx):\n    return {}\n", [action("go")], settings=["gemini_key"])
        host = self.host()
        self.assertIn("greedy", host.load_errors)
        out = host.call("talky__go")
        self.assertEqual(self.settings["voice_rate"], "1.2")
        self.assertIn({"kind": "settings", "data": {"values": {"voice_rate": "1.2"}}}, out["effects"])
        ctx = host.context("talky")
        self.assertEqual(ctx.settings_get("voice_rate"), "1.2")
        with self.assertRaises(SkillError):
            ctx.settings_get("gemini_key")
        with self.assertRaises(SkillError):
            ctx.settings_put("skills_off", "[]")

    def test_effects(self):
        self.add_coin()
        host = self.host()
        ctx = host.context("coin_flip")
        ctx.effect("show_screen")
        ctx.effect("coin", {"side": "heads"})
        self.assertEqual(ctx.effects, [{"kind": "show_screen", "data": {"screen": "coin_flip"}},
                                       {"skill": "coin_flip", "kind": "coin", "data": {"side": "heads"}}])
        for kind, data in (("show_screen", {"screen": "other"}), ("settings", {}), ("Bad Kind", {}), ("coin", 3)):
            with self.assertRaises(SkillError):
                ctx.effect(kind, data)
        out = host.on_event("coin_flip", {"type": "tap"})
        self.assertIn(out["response"]["side"], ("heads", "tails"))
        self.assertEqual(host.on_event("coin_flip", "tap")["response"]["error"], "bad_input")


class FetchTest(SkillsTestCase):

    def setUp(self):
        super().setUp()
        self.write_skill("pics", "def go(ctx):\n    return {}\n", [action("go")], storage=False,
                         needs={"internet_hosts": ["*.example.org", "api.example.com"]})

    def fetch(self, url, online=True, **kwargs):
        return self.host(online=lambda: online).context("pics").fetch(url, **kwargs)

    def test_only_allowed_hosts(self):
        patch, asked = fake_web({"en.example.org": (200, {"Content-Type": "text/plain"}, b"hello"),
                                 "api.example.com": (200, {}, b"ok"), "evil.com": (200, {}, b"bad")})
        with patch:
            out = self.fetch("https://en.example.org/a")
            self.assertEqual(out, {"status": 200, "content_type": "text/plain", "body": b"hello"})
            self.fetch("https://api.example.com/s?x=1", params={"q": "bird"})
            for bad in ("https://evil.com/", "http://en.example.org/", "https://example.org/",
                        "https://a.b.example.org/", "https://en.example.org:8443/", "https://api.example.com.evil.com/",
                        "https://user:pw@en.example.org/", "file:///c:/x"):
                with self.subTest(url=bad), self.assertRaises(SkillFetchError):
                    self.fetch(bad)
            with self.assertRaises(SkillFetchError):
                self.fetch("https://en.example.org/", method="POST")
        self.assertEqual(len(asked), 2)
        self.assertEqual(urllib.parse.urlsplit(asked[1]).query, "x=1&q=bird")

    def test_redirects_are_checked_again(self):
        patch, asked = fake_web({"en.example.org": (302, {"Location": "https://evil.com/steal"}, b""),
                                 "fr.example.org": (302, {"Location": "http://api.example.com/"}, b""),
                                 "de.example.org": (302, {"Location": "https://api.example.com/x"}, b""),
                                 "api.example.com": (200, {}, b"ok"), "evil.com": (200, {}, b"bad")})
        with patch:
            for url in ("https://en.example.org/", "https://fr.example.org/"):
                with self.subTest(url=url), self.assertRaises(SkillFetchError) as caught:
                    self.fetch(url)
                self.assertEqual(caught.exception.reason, "redirect_not_allowed")
            self.assertEqual(self.fetch("https://de.example.org/")["body"], b"ok")
        self.assertFalse(any("evil.com" in url for url in asked))

    def test_size_cap_is_an_error(self):
        patch, _ = fake_web({"en.example.org": (200, {}, b"x" * 3000),
                             "api.example.com": (200, {"Content-Length": "999999"}, b"small")})
        with patch:
            with self.assertRaises(SkillFetchError) as caught:
                self.fetch("https://en.example.org/", max_bytes=1000)
            self.assertEqual(caught.exception.reason, "too_big")
            with self.assertRaises(SkillFetchError):
                self.fetch("https://api.example.com/", max_bytes=1000)
            self.assertEqual(len(self.fetch("https://en.example.org/", max_bytes=3000)["body"]), 3000)

    def test_timeout_and_cap_have_ceilings(self):
        with mock.patch.object(skills_core, "_open_url", side_effect=OSError("down")) as opened:
            with self.assertRaises(SkillFetchError):
                self.fetch("https://en.example.org/", timeout=60)
        self.assertEqual(opened.call_args[0][1], skills_core.FETCH_TIMEOUT_MAX)

    def test_offline_refuses_at_once(self):
        patch, asked = fake_web({"en.example.org": (200, {}, b"hello")})
        with patch, self.assertRaises(SkillFetchError) as caught:
            self.fetch("https://en.example.org/", online=False)
        self.assertEqual(caught.exception.reason, "offline")
        self.assertEqual(asked, [])

    def test_log_keeps_host_status_bytes_only(self):
        patch, _ = fake_web({"en.example.org": (200, {}, b"hello")})
        with patch:
            self.fetch("https://en.example.org/private/diary?name=Rose%20Smith")
            with self.assertRaises(SkillFetchError):
                self.fetch("https://evil.com/secret/path?who=Rose")
        lines = self.log_lines()
        self.assertIn({"event": "fetch", "skill": "pics", "host": "en.example.org", "status": 200, "bytes": 5},
                      [{k: v for k, v in line.items() if k != "time"} for line in lines])
        text = (self.dir / "skills.log").read_text(encoding="utf-8")
        for secret in ("private", "diary", "Rose", "secret", "path", "?"):
            self.assertNotIn(secret, text)


class GuardTest(SkillsTestCase):

    def test_two_failures_trip_the_skill(self):
        self.write_skill("boom", "def go(ctx):\n    return 1 // 0\n", [action("go")])
        host = self.host()
        first = host.call("boom__go")
        self.assertEqual(first, {"response": {"error": "not_working"}, "effects": [],
                                 "say": skills_core.SAY_NOT_WORKING})
        self.assertTrue(host.enabled("boom"))
        host.call("boom__go")
        self.assertFalse(host.enabled("boom"))
        self.assertTrue(host.list_skills()[0]["tripped"])
        self.assertEqual([d["name"] for d in host.gemini_tools()[0]["functionDeclarations"]], ["set_skill"])
        failure = next(line for line in self.log_lines() if line["event"] == "failure")
        self.assertEqual((failure["error"], failure["where"]), ("ZeroDivisionError", "skill.py:2"))
        self.assertIn("tripped", [line["event"] for line in self.log_lines()])

    def test_failures_far_apart_dont_trip(self):
        self.write_skill("boom", "def go(ctx):\n    return 1 // 0\n", [action("go")])
        now = [0.0]
        host = self.host(clock=lambda: now[0])
        host.call("boom__go")
        now[0] = 601.0
        host.call("boom__go")
        self.assertTrue(host.enabled("boom"))

    def test_timeout_is_a_failure(self):
        self.write_skill("slowpoke", "import time\n\n\ndef go(ctx):\n    time.sleep(0.5)\n    return {}\n",
                         [action("go")])
        host = self.host(timeout=0.1)
        self.assertEqual(host.call("slowpoke__go")["response"], {"error": "not_working"})
        self.assertEqual(self.log_lines()[-1]["error"], "Timeout")

    def test_load_crash_and_unsafe_code_are_not_loaded(self):
        self.write_skill("crash", "raise RuntimeError('no')\n", [])
        self.write_skill("sneaky", "import socket\n\n\ndef go(ctx):\n    return open('x')\n", [action("go")])
        self.write_skill("newer", "", [], contract=2)
        host = self.host()
        self.assertEqual(host.skills, {})
        self.assertIn("crashed on load (RuntimeError", host.load_errors["crash"])
        self.assertIn("imports socket", host.load_errors["sneaky"])
        self.assertIn("uses open", host.load_errors["sneaky"])
        self.assertEqual(host.load_errors["newer"], "unsupported contract")
        self.assertEqual(sum(line["event"] == "load_failed" for line in self.log_lines()), 3)

    def test_page_failures_count(self):
        self.add_coin()
        host = self.host()
        host.broken("coin_flip")
        self.assertEqual(host.broken("coin_flip"), {"ok": True, "tripped": True})
        self.assertEqual(host.call("coin_flip__flip")["response"], {"error": "not_working"})

    def test_bad_arguments_are_an_answer_not_a_crash(self):
        self.add_coin()
        host = self.host()
        for args in ({"coin": "euro"}, {}, {"coin": "dime", "x": 1}, {"coin": 5}):
            with self.subTest(args=args):
                self.assertEqual(host.call("coin_flip__set_coin", args)["response"]["error"], "bad_input")
        self.assertEqual(host.call("coin_flip__nope")["response"], {"error": "unknown_tool"})
        self.assertEqual(skills_core.check_args({"type": "integer", "minimum": 1}, 3.0), (3, None))
        self.assertIsNotNone(skills_core.check_args({"type": "integer", "minimum": 1}, 0)[1])
        self.assertEqual(host.list_skills()[0]["tripped"], False)


class SwitchTest(SkillsTestCase):

    def test_locks_hold_against_voice_both_ways(self):
        self.add_coin()
        host = self.host()
        host.lock("coin_flip", "off")
        self.assertEqual(json.loads(self.settings["skills_locked"]), {"coin_flip": "off"})
        out = host.call("set_skill", {"name": "coin_flip", "on": True})
        self.assertEqual((out["response"]["error"], out["say"]), ("locked", skills_core.SAY_LOCKED))
        self.assertFalse(host.enabled("coin_flip"))
        host.lock("coin_flip", "on")
        self.assertEqual(host.set_skill("coin_flip", False)["error"], "locked")
        self.assertTrue(host.enabled("coin_flip"))
        self.assertTrue(host.set_skill("coin_flip", False, by="helper")["ok"])
        self.assertTrue(host.enabled("coin_flip"))
        host.lock("coin_flip", None)
        self.assertFalse(host.enabled("coin_flip"))
        self.assertEqual(json.loads(self.settings["skills_off"]), ["coin_flip"])
        out = host.call("set_skill", {"name": "coin_flip", "on": True})
        self.assertEqual(out["say"], "Coin flip is on now.")
        self.assertEqual(out["effects"], [{"kind": "settings", "data": {"skills": {"coin_flip": True}}}])
        self.assertTrue(host.enabled("coin_flip"))

    def test_default_off_skill(self):
        self.write_skill("quiet", "def go(ctx):\n    return {}\n", [action("go")], default_on=False)
        host = self.host()
        self.assertFalse(host.enabled("quiet"))
        self.assertEqual(host.call("quiet__go")["response"], {"error": "off"})
        self.assertTrue(host.set_skill("quiet", True)["on"])
        self.assertEqual(json.loads(self.settings["skills_on"]), ["quiet"])
        self.assertFalse(host.set_skill("quiet", False)["on"])

    def test_list_skills(self):
        self.add_coin()
        self.assertEqual(self.host().list_skills(), [{
            "name": "coin_flip", "title": "Coin flip", "summary": "Mary flips a coin and shows it on screen.",
            "menu": {"label": "Flip a coin", "icon": "coin", "full_screen": False}, "on": True, "locked": None,
            "tripped": False, "has_screen": True, "has_css": False}])


class OfflineTest(SkillsTestCase):

    def test_phrases_and_switches(self):
        self.add_coin()
        host = self.host()
        out = host.offline_match("Could you flip a coin please, Mary?")
        self.assertIn(out["response"]["side"], ("heads", "tails"))
        self.assertTrue(out["say"].startswith("It's "))
        self.assertIsNone(host.offline_match("Please don't flip a coin"))
        self.assertIsNone(host.offline_match("flip a coin", is_blocked=lambda text: True))
        self.assertIsNone(host.offline_match("I can't breathe, flip a coin", is_blocked=mary.is_emergency))
        self.assertIsNone(host.offline_match("tell me a story"))
        self.assertEqual(host.offline_match("Turn the coin flip off")["say"], "Coin flip is off now.")
        self.assertIsNone(host.offline_match("flip a coin"))
        host.offline_match("turn coin flip back on")
        self.assertTrue(host.enabled("coin_flip"))
        host.offline_match("stop the coin flip")
        self.assertFalse(host.enabled("coin_flip"))
        host.lock("coin_flip", "off")
        self.assertEqual(host.offline_match("turn on the coin flip")["say"], skills_core.SAY_LOCKED)

    def test_needs_internet_skill_offline(self):
        self.write_skill("news", "def read(ctx):\n    return {}\n", [action("read", phrases=["read the news"])],
                         offline="needs_internet")
        host = self.host(online=lambda: False)
        self.assertIsNone(host.offline_match("read the news"))
        out = host.call("news__read")
        self.assertEqual((out["response"], out["say"]), ({"error": "needs_internet"}, skills_core.SAY_NEEDS_INTERNET))


class GeminiTest(SkillsTestCase):

    def test_tools_shape(self):
        self.add_coin()
        host = self.host()
        tools = host.gemini_tools()
        self.assertEqual(len(tools), 1)
        decls = {d["name"]: d for d in tools[0]["functionDeclarations"]}
        self.assertEqual(sorted(decls), ["coin_flip__flip", "coin_flip__set_coin", "set_skill"])
        self.assertNotIn("parameters", decls["coin_flip__flip"])
        self.assertEqual(decls["coin_flip__set_coin"]["parameters"]["required"], ["coin"])
        self.assertEqual(decls["set_skill"]["parameters"]["properties"]["name"]["enum"], ["coin_flip"])
        text = json.dumps(tools)
        for key in ("annotations", "offline_phrases", "readOnlyHint"):
            self.assertNotIn(key, text)
        host.set_skill("coin_flip", False)
        self.assertEqual([d["name"] for d in host.gemini_tools()[0]["functionDeclarations"]], ["set_skill"])

    def test_no_skills_no_tools(self):
        host = self.host()
        self.assertEqual((host.gemini_tools(), host.instruction_text()), ([], ""))

    def test_gemini_schema_strips_other_keys(self):
        schema = {"type": "object", "$ref": "#/x", "additionalProperties": False,
                  "properties": {"a": {"type": "string", "pattern": "x", "description": "d", "maxLength": 9}}}
        self.assertEqual(skills_core.gemini_schema(schema), {
            "type": "object", "properties": {"a": {"type": "string", "description": "d", "maxLength": 9}}})

    def test_instruction_text(self):
        self.add_coin()
        host = self.host()
        text = host.instruction_text()
        self.assertTrue(text.startswith(skills_core.INSTRUCTIONS_HEAD))
        self.assertIn("- Coin flip: Offer it when", text)
        self.assertIn("not_working", text)
        self.assertIn("locked", text)
        self.assertNotIn("What's on the screen now", text)
        side = host.call("coin_flip__flip")["response"]["side"]
        self.assertIn(f"What's on the screen now (Coin flip): A quarter showing {side}.",
                      host.instruction_text(on_screen="coin_flip"))
        host.set_skill("coin_flip", False)
        self.assertNotIn("- Coin flip", host.instruction_text(on_screen="coin_flip"))


if __name__ == "__main__":
    unittest.main()
