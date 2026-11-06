from tests import helpers  # noqa: F401  (first: points the data folder at a scratch place)

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

import mary
import voices

FACTS = {"voice_now": "builtin", "picked_voice": "", "talk_mode": "handsfree", "wake_word": False,
         "talk_choice": "live", "talk_on_open": True, "voice_rate": 0.8, "voice_volume": 0.4, "printer": False}

# sha256 of the full-brain prompts (fixed FACTS, empty memory, hello). Repinned for D12 (Andy, 2026-11-02): one line, switches, How bad and deleting go by their word.
# Repinned for M18b: one app-fact line in "Working on their screens" now reads "You may have one screen tool" (true in Normal too), shorter than before.
# Repinned 2026-11-06: tic-tac-toe is dropped (Andy), so the games line reads "Cards and crosswords are coming soon", shorter than before.
PINNED = {("mary", "normal"): "128e228b81b1ba46f8676383573fc63912930e57becf0bfb8b0869a1ee2c6473",
          ("mary", "live"): "6d32ed630ba05da312c89320e321dcde079fee8064a931e631c0c1fc587aa5e2",
          ("him", "normal"): "8a1b7a85649045218aebf2d2723c9758da8d2143e2913925675fab2a2681ca76",
          ("him", "live"): "699179d764a18670b097fba929163488ed955eee4a545f304c400a5fd8c40850"}


def _memory():
    return mary.Memory(Path(tempfile.mkdtemp(prefix="m21c-", dir=helpers.TMP)) / "memory.json")


def _boom():
    raise RuntimeError("setting broke")


def normal(c, **kw):
    return mary._body("hello", _memory(), None, c, **kw)["systemInstruction"]["parts"][0]["text"]


def live(c, **kw):
    return voices.live_system(c, memory=_memory(), **kw)


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        real = mary.app_facts
        mary.app_facts = lambda companion: dict(FACTS)
        self.addCleanup(setattr, mary, "app_facts", real)
        self.addCleanup(setattr, mary, "brain_setting", mary.brain_setting)
        self.addCleanup(setattr, mary, "LEAN", mary.LEAN)
        self.addCleanup(setattr, mary, "INSTRUCTIONS", mary.INSTRUCTIONS)

    def lean(self):
        mary.brain_setting = lambda: "lean"


class FullUnchanged(Base):
    def test_full_whatever_the_setting(self):
        for setting in (None, lambda: "full", lambda: "nonsense", _boom):
            mary.brain_setting = setting
            for c in ("mary", "him"):
                self.assertEqual(sha(normal(c)), PINNED[(c, "normal")])
                self.assertEqual(sha(live(c)), PINNED[(c, "live")])
            self.assertEqual(mary.current_brain(), "full")
        mary.brain_setting = None
        base = [mary.load_instructions(x) for x in ("mary", "him", None)]
        for setting in (lambda: "full", lambda: "nonsense", _boom):
            mary.brain_setting = setting
            self.assertEqual([mary.load_instructions(x) for x in ("mary", "him", None)], base)

    def test_missing_lean_falls_back(self):
        self.lean()
        mary.LEAN = Path(helpers.TMP) / "no-such-lean.md"
        self.assertEqual(mary.current_brain(), "full")
        self.assertEqual(sha(normal("mary")), PINNED[("mary", "normal")])
        self.assertEqual(sha(live("him")), PINNED[("him", "live")])

    def test_unreadable_safety_falls_back(self):
        self.lean()
        tmp = Path(tempfile.mkdtemp(dir=helpers.TMP)) / "i.md"
        tmp.write_text(mary.INSTRUCTIONS.read_text(encoding="utf-8").replace("You are not a doctor", "x"), encoding="utf-8")
        mary.INSTRUCTIONS = tmp
        self.assertEqual(mary.current_brain(), "full")


class Lean(Base):
    def setUp(self):
        super().setUp()
        self.lean()

    def test_safety_word_for_word(self):
        sections = mary.safety_sections()
        raw = mary.INSTRUCTIONS.read_text(encoding="utf-8")
        for h in mary.SAFETY_HEADINGS:
            self.assertIn(h, sections)
        for part in sections.split("\n\n"):
            self.assertIn(part, raw)
        for c in ("mary", "him"):
            for text in (normal(c), live(c)):
                self.assertIn(sections, text)

    def test_names_differ_and_old_notes_gone(self):
        self.assertEqual(mary.current_brain(), "lean")
        self.assertNotEqual(mary.load_instructions("mary"), mary.load_instructions("him"))
        self.assertNotIn("=== ", mary.load_instructions(None))
        for text in (normal("mary"), normal("him"), live("mary"), live("him")):
            for old in (mary.CHARACTER_NOTE, voices.LIVE_EXTRA, voices.LIVE_TOOLS_NOTE):
                self.assertNotIn(old, text)
        self.assertEqual(mary.character_note(), "")

    def test_changed_instructions_flow_through(self):
        raw = mary.INSTRUCTIONS.read_text(encoding="utf-8")
        lines = raw.splitlines()
        i = lines.index("You are not a doctor")
        lines[i + 1] = "ALTERED SAFETY LINE for the test."
        tmp = Path(tempfile.mkdtemp(dir=helpers.TMP)) / "instructions.md"
        tmp.write_text("\n".join(lines), encoding="utf-8")
        self.assertNotIn("ALTERED SAFETY", normal("mary"))
        mary.INSTRUCTIONS = tmp
        self.assertIn("ALTERED SAFETY LINE for the test.", normal("mary"))
        self.assertIn("ALTERED SAFETY LINE for the test.", live("him"))

    def test_tags(self):
        for c in ("mary", "him"):
            n = normal(c)
            self.assertIn("[mood:", n)
            self.assertIn("[remember:", n)
            brain = [mary._no_tag_rules(mary.load_instructions(c)), voices.live_extra(), voices.live_tools_note()]
            for part in brain:
                self.assertNotIn("[", part)

    def test_no_caching(self):
        state = ["lean"]
        mary.brain_setting = lambda: state[0]
        a = normal("mary")
        state[0] = "full"
        b = normal("mary")
        state[0] = "lean"
        self.assertNotEqual(a, b)
        self.assertEqual(a, normal("mary"))

    def test_memory_history_skills_same_in_both(self):
        class Skills:
            def instruction_text(self, screen):
                return "SKILLS-INSTRUCTION-TEXT"

            def gemini_tools(self):
                return []

        def build():
            m = _memory()
            m.facts = ["Likes fishing on the lake"]
            m.name = "Ruth"
            m.recent = [{"role": "user", "text": "I slept badly"}]
            return m
        for brain in ("lean", "full"):
            mary.brain_setting = lambda b=brain: b
            n = mary._body("hello", build(), None, "mary", skills=Skills())["systemInstruction"]["parts"][0]["text"]
            lv = voices.live_system("mary", memory=build())
            for text in (n, lv):
                self.assertIn("- Likes fishing on the lake", text)
                self.assertIn("Name: Ruth", text)
            self.assertIn("SKILLS-INSTRUCTION-TEXT", n)
            self.assertIn("They: I slept badly", lv)


class BrainSettingTests(unittest.TestCase):
    def setUp(self):
        import server
        self.server = server
        self.saved = mary.brain_setting
        helpers.reset_db()
        mary.brain_setting = lambda: server.mary_settings()["mary_brain"]  # the hook server sets on import

    def tearDown(self):
        helpers.reset_db()
        mary.brain_setting = self.saved

    def test_default_is_full(self):
        self.assertEqual(self.server.mary_settings()["mary_brain"], "full")
        self.assertEqual(mary.current_brain(), "full")

    def test_server_import_sets_the_hook(self):
        self.assertIsNotNone(self.saved)

    def test_lean_saves_and_reads_back(self):
        st, _, _ = helpers.api("PUT", "/api/settings", {"mary_brain": " Lean "})
        self.assertEqual(st, 200)
        self.assertEqual(self.server.mary_settings()["mary_brain"], "lean")
        self.assertEqual(mary.current_brain(), "lean")
        _, j, _ = helpers.api("GET", "/api/settings")
        self.assertEqual(j["mary_brain"], "lean")

    def test_nonsense_is_ignored(self):
        helpers.api("PUT", "/api/settings", {"mary_brain": "lean"})
        helpers.api("PUT", "/api/settings", {"mary_brain": "nonsense"})
        self.assertEqual(mary.current_brain(), "lean")

    def test_page_has_the_two_radios(self):
        html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('name="mary_brain" value="full" checked', html)
        self.assertIn('name="mary_brain" value="lean"', html)
        self.assertIn("How much Mary is told", html)


if __name__ == "__main__":
    unittest.main()
