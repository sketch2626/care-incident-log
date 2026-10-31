from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M15c: the send count in skills/messages/screen.js, checked with Node, plus the hooks it needs in web/mary/app.js. The
logic runs without a page in tests/js/m15c_screen.js."""
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKS = os.path.join(ROOT, "tests", "js", "m15c_screen.js")


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


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(NODE, "Node not found: the send count page checks were skipped")
class SendCountJsTests(unittest.TestCase):
    def test_the_count_keeps_its_order_and_a_stop_never_sends(self):
        done = subprocess.run([NODE, CHECKS], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr + done.stdout)
        self.assertIn("OK m15c screen", done.stdout)


class SendCountPageTests(unittest.TestCase):
    def test_app_has_the_hooks_the_skill_uses(self):
        app = read("web", "mary", "app.js")
        screen = read("skills", "messages", "screen.js")
        for hook in ("isLive", "speaking", "hushLive", "heardEmergency", "watchHeard", "countMic"):
            self.assertRegex(app, r"\b%s: " % hook)
            self.assertRegex(screen, r"\ba\.%s\b" % hook)
        self.assertIn("window.MarySkills.apply(acts[ai])", app)   # Live's gate effects
        self.assertIn("S.heardWatch(tail)", app)
        self.assertIn("if (S.micHeld)", app)
        self.assertIn("!d.error && !d.mood", app)                 # a quiet turn isn't a failure

    def test_nothing_on_the_new_screens_is_under_20px(self):
        css = read("skills", "messages", "screen.css").split("M15c:", 1)[1]
        for size in re.findall(r"font:\s*\d+\s+([^/;]+?)/", css) + re.findall(r"font-size:\s*([^;}]+)", css):
            floor = re.match(r"max\((\d+)px,", size)
            self.assertTrue(floor, size)
            self.assertGreaterEqual(int(floor.group(1)), 20, size)

    def test_every_target_is_at_least_64px(self):
        css = read("skills", "messages", "screen.css")
        for name in ("mc-undo", "mc-quiet", "mc-use"):
            self.assertRegex(css, r"\.%s\b[^{]*\{[^}]*min-height:64px" % name)
        self.assertRegex(css, r"\.mc-field\{[^}]*height:max\(64px,")

    def test_the_address_box_can_take_voice_typing(self):
        screen = read("skills", "messages", "screen.js")
        self.assertIn("field.type = 'text'", screen)
        self.assertIn("field.focus()", screen)
        self.assertNotIn("readOnly", screen)


if __name__ == "__main__":
    unittest.main()
