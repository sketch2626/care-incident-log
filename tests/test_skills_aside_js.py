from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M13b: a game set aside for a picture (web/mary/skills.js and show() in web/mary/app.js), checked with Node. The page
scripts run against a stubbed page in tests/js/skills_aside.js."""
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKS = os.path.join(ROOT, "tests", "js", "skills_aside.js")


def find_node():
    node = shutil.which("node")
    if node:
        return node
    for base in (os.environ.get("ProgramFiles"), r"C:\Program Files"):
        if base:
            p = os.path.join(base, "nodejs", "node.exe")
            if os.path.isfile(p):
                return p
    return None


NODE = find_node()


@unittest.skipUnless(NODE, "Node not found: the set-aside page checks were skipped")
class SkillsAsideJsTests(unittest.TestCase):
    def test_a_game_waits_behind_a_picture(self):
        done = subprocess.run([NODE, CHECKS], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        self.assertIn("OK skills aside", done.stdout)


if __name__ == "__main__":
    unittest.main()
