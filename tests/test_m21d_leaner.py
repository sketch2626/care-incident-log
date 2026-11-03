from tests import helpers  # noqa: F401  (first: points the data folder at a scratch place)

import hashlib
import tempfile
import unittest
from pathlib import Path

import mary
import voices
from tests.test_m21c_lean import FACTS, PINNED, _memory, live, normal, sha

# sha256 of mary/lean.md with \r\n turned into \n (Windows may check the file out with CRLF; the bytes in git are LF).
# Repinned for D12 (Andy, 2026-11-02): one line reworded. The lean-v1 tag stays as the old revert point.
LEAN_FILE_PREFIX = "346133d795ef65e2"
# sha256 of the lean-brain prompts before M21d (fixed FACTS, empty memory, hello).
LEAN_PINNED = {("mary", "normal"): "b5030699fe96612ba16663b616ef7acd3cbedc2d7206c0ed760c22c968c2f9bf",
               ("mary", "live"): "f3e78d7851c35672865485dcd68921224966b7fcdd014ad294fab5469569152b",
               ("him", "normal"): "15ff0d79ff73098c08a3ed08b501a36525615db24bc4dc5cbfac200beec3cb52",
               ("him", "live"): "ebb7579b5d318c3f9c352bf61dc350dcf55f7a4f3b5412bc5f196ce23d6fd5af"}


class Base(unittest.TestCase):
    def setUp(self):
        real = mary.app_facts
        mary.app_facts = lambda companion: dict(FACTS)
        self.addCleanup(setattr, mary, "app_facts", real)
        self.addCleanup(setattr, mary, "brain_setting", mary.brain_setting)
        self.addCleanup(setattr, mary, "LEAN", mary.LEAN)
        self.addCleanup(setattr, mary, "LEANER", mary.LEANER)

    def brain(self, name):
        mary.brain_setting = lambda: name


class Pins(Base):
    def test_full_pinned_when_leaner_file_missing_or_setting_junk(self):
        self.brain("leaner")
        mary.LEANER = Path(helpers.TMP) / "no-such-leaner.md"
        self.assertEqual(mary.current_brain(), "full")
        for c in ("mary", "him"):
            self.assertEqual(sha(normal(c)), PINNED[(c, "normal")])
            self.assertEqual(sha(live(c)), PINNED[(c, "live")])
        self.brain("junk")
        self.assertEqual(mary.current_brain(), "full")
        for c in ("mary", "him"):
            self.assertEqual(sha(normal(c)), PINNED[(c, "normal")])
            self.assertEqual(sha(live(c)), PINNED[(c, "live")])

    def test_lean_file_and_prompts_unchanged(self):
        data = Path(mary.LEAN).read_bytes().replace(b"\r\n", b"\n")
        self.assertTrue(hashlib.sha256(data).hexdigest().startswith(LEAN_FILE_PREFIX))
        self.brain("lean")
        for c in ("mary", "him"):
            self.assertEqual(sha(normal(c)), LEAN_PINNED[(c, "normal")])
            self.assertEqual(sha(live(c)), LEAN_PINNED[(c, "live")])


class Assembly(Base):
    def test_all_three_brains(self):
        out = {}
        for b in ("full", "lean", "leaner"):
            self.brain(b)
            self.assertEqual(mary.current_brain(), b)
            for c, who in (("mary", "You are Mary"), ("him", "You are Sam")):
                for kind, text in (("normal", normal(c)), ("live", live(c))):
                    self.assertTrue(text.strip())
                    self.assertIn(who, text)
                    self.assertNotIn("=== ", text)
                    self.assertNotIn("{{safety}}", text)
                    out[(b, c, kind)] = text
                self.assertIn("[mood:", out[(b, c, "normal")])
                self.assertIn("[remember:", out[(b, c, "normal")])
        for c in ("mary", "him"):
            for kind in ("normal", "live"):
                a, b, d = (out[(x, c, kind)] for x in ("full", "lean", "leaner"))
                self.assertEqual(len({a, b, d}), 3)
        self.brain("leaner")
        for c in ("mary", "him"):
            for part in (mary._no_tag_rules(mary.load_instructions(c)), voices.live_extra(), voices.live_tools_note()):
                self.assertNotIn("[", part)
        self.assertEqual(mary.character_note(), "")

    def test_no_caching(self):
        state = ["lean"]
        mary.brain_setting = lambda: state[0]
        seen = []
        for s in ("lean", "leaner", "full", "leaner", "lean"):
            state[0] = s
            seen.append(normal("mary"))
        self.assertEqual(len({seen[0], seen[1], seen[2]}), 3)
        self.assertEqual(seen[0], seen[4])
        self.assertEqual(seen[1], seen[3])

    def test_no_tag_rules_keeps_remembering(self):
        self.brain("leaner")
        raw = mary.load_instructions("mary")
        self.assertIn("Your face", raw)
        stripped = mary._no_tag_rules(raw)
        self.assertNotIn("Your face", stripped)
        self.assertIn("Remembering", stripped)
        self.assertIn("Never remember staff names", stripped)

    def test_broken_leaner_file_falls_back(self):
        self.brain("leaner")
        bad = Path(tempfile.mkdtemp(dir=helpers.TMP)) / "leaner.md"
        bad.write_text("---\n=== Mary ===\nx\n", encoding="utf-8")
        mary.LEANER = bad
        self.assertEqual(mary.current_brain(), "full")


class SettingTests(unittest.TestCase):
    def setUp(self):
        import server
        self.server = server
        self.saved = mary.brain_setting
        helpers.reset_db()
        mary.brain_setting = lambda: server.mary_settings()["mary_brain"]

    def tearDown(self):
        helpers.reset_db()
        mary.brain_setting = self.saved

    def test_leaner_saves_and_reads_back(self):
        st, _, _ = helpers.api("PUT", "/api/settings", {"mary_brain": "leaner"})
        self.assertEqual(st, 200)
        self.assertEqual(self.server.mary_settings()["mary_brain"], "leaner")
        self.assertEqual(mary.current_brain(), "leaner")
        _, j, _ = helpers.api("GET", "/api/settings")
        self.assertEqual(j["mary_brain"], "leaner")

    def test_nonsense_is_ignored(self):
        helpers.api("PUT", "/api/settings", {"mary_brain": "leaner"})
        helpers.api("PUT", "/api/settings", {"mary_brain": "nonsense"})
        self.assertEqual(mary.current_brain(), "leaner")

    def test_page_has_the_radio(self):
        root = Path(__file__).resolve().parent.parent / "web"
        html = (root / "index.html").read_text(encoding="utf-8")
        self.assertIn('name="mary_brain" value="leaner"', html)
        self.assertIn("Leaner instructions", html)
        self.assertIn("leaner", (root / "app.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
