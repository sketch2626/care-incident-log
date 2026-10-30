"""The voice_comfort skill (skills/voice_comfort): steps, limits, offline phrases and Gemini tools."""
from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import server
import skills_core

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "voice_comfort"


class VoiceComfortTest(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="voice-comfort-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        code = self.dir / "skill_code"
        code.mkdir()
        shutil.copytree(SKILL, code / "voice_comfort", ignore=shutil.ignore_patterns("__pycache__"))
        self.settings = {}
        db = self.dir / "t.db"
        self.host = skills_core.SkillHost(code, self.dir, lambda: sqlite3.connect(db),
                                          lambda: dict(self.settings), self.settings.update)
        self.host.load()

    def call(self, action):
        return self.host.call(f"voice_comfort__{action}", {})

    def test_loads(self):
        self.assertIn("voice_comfort", self.host.skills)

    def test_slower_and_faster_step_by_008(self):
        r = self.call("slower")
        self.assertEqual(self.settings["voice_rate"], "0.84")
        self.assertEqual(r["say"], "Is this better?")
        self.assertEqual(r["effects"], [{"kind": "settings", "data": {"values": {"voice_rate": "0.84"}}}])
        self.call("faster")
        self.call("faster")
        self.assertEqual(self.settings["voice_rate"], "1.0")

    def test_rate_clamps(self):
        self.settings["voice_rate"] = "0.62"
        self.call("slower")
        self.assertEqual(self.settings["voice_rate"], "0.6")
        r = self.call("slower")
        self.assertEqual(r["say"], "I'm already as slow as I can go.")
        self.assertEqual(r["effects"], [])
        self.settings["voice_rate"] = "1.4"
        self.assertEqual(self.call("faster")["say"], "I'm already as fast as I can go.")

    def test_volume_steps_and_clamps(self):
        r = self.call("louder")
        self.assertIn("already as loud", r["say"])
        self.assertIn("computer's sound", r["say"])
        self.call("quieter")
        self.assertEqual(self.settings["voice_volume"], "0.9")
        self.settings["voice_volume"] = "0.25"
        self.call("quieter")
        self.assertEqual(self.settings["voice_volume"], "0.2")
        self.assertEqual(self.call("quieter")["say"], "I'm already as quiet as I can be.")

    def test_switch_companion(self):
        r = self.call("switch_companion")
        self.assertEqual(self.settings["companion"], "him")
        self.assertEqual(r["say"], "Hi, I'm Sam. It's nice to meet you.")
        r = self.call("switch_companion")
        self.assertEqual(self.settings["companion"], "mary")
        self.assertEqual(r["say"], "Hi, I'm Mary. It's so nice to meet you.")

    def test_view(self):
        self.assertEqual(self.host.view("voice_comfort"),
                         "Speaking speed 0.92 (0.6-1.4), volume 1.0, companion Mary, waits 2.5 s before answering.")

    def test_offline_phrases(self):
        r = self.host.offline_match("could you speak up")
        self.assertIsNotNone(r)
        self.assertIn("voice_volume", r["response"])

    def test_stop_and_start_wake(self):  # M6
        r = self.call("stop_wake")
        self.assertEqual(self.settings["wake_word"], "0")
        self.assertEqual(r["effects"], [{"kind": "settings", "data": {"values": {"wake_word": "0"}}}])
        self.assertIn("won't listen", self.call("stop_wake")["say"])
        self.settings["companion"] = "him"
        r = self.call("start_wake")
        self.assertEqual(self.settings["wake_word"], "1")
        self.assertIn("Hey Sam", r["say"])

    def test_wake_offline_phrases(self):  # M6
        r = self.host.offline_match("please stop listening for your name")
        self.assertIsNotNone(r)
        self.assertEqual(self.settings["wake_word"], "0")
        self.assertIsNotNone(self.host.offline_match("listen for hey mary"))
        self.assertEqual(self.settings["wake_word"], "1")

    def test_skill_wake_change_reaches_listener(self):  # M6
        from unittest import mock
        helpers.reset_db()
        with mock.patch.object(server.WAKE, "settings_changed") as m:
            server._put_settings({"wake_word": "0"})
            server._put_settings({"voice_rate": "1.0"})
            self.assertEqual(m.call_count, 1)
        with mock.patch.object(server.WAKE, "settings_changed", side_effect=RuntimeError("x")):
            server._put_settings({"companion": "him"})  # must not raise
        server._put_settings({"companion": "mary", "wake_word": "1"})

    def test_wake_model_and_vosk_packaged(self):  # M6
        build = (ROOT / "packaging" / "build.py").read_text(encoding="utf8")
        self.assertIn("vosk-model-small-en-us-0.15", build)
        self.assertIn("get_wake_model.py", build)
        self.assertIn("wakeword", build)
        self.assertIn("vosk==", (ROOT / "packaging" / "requirements.txt").read_text())

    def test_gemini_tools(self):
        text = repr(self.host.gemini_tools())
        for name in ("slower", "faster", "quieter", "louder", "switch_companion"):
            self.assertIn(f"voice_comfort__{name}", text)

    def test_constants_match_server(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("vc_skill", SKILL / "skill.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual((mod.RATE_MIN, mod.RATE_MAX, mod.RATE_DEFAULT), server.VOICE_LIMITS["voice_rate"])
        self.assertEqual((mod.VOLUME_MIN, mod.VOLUME_MAX, mod.VOLUME_DEFAULT), server.VOICE_LIMITS["voice_volume"])
        self.assertEqual((mod.WAIT_MIN, mod.WAIT_MAX, mod.WAIT_DEFAULT), server.VOICE_LIMITS["listen_wait"])  # M4a


if __name__ == "__main__":
    unittest.main()
