from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""Mary's captions (web/mary/captions.js, style A "Coloring-in"): word timing and the caption itself,
checked with Node (tests/js/captions_timing.js). Skipped when Node is not installed."""
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "tests", "js", "captions_timing.js")
CAPTIONS = os.path.join(ROOT, "web", "mary", "captions.js")


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


@unittest.skipUnless(NODE, "Node not found: the caption timing checks were skipped")
class CaptionsJsTests(unittest.TestCase):
    def test_script_parses(self):
        run = subprocess.run([NODE, "--check", CAPTIONS], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr.strip()[-800:])

    def test_timing_and_caption(self):
        """Weights, plan() order and clamps, pauses, the 2.6 words a second estimate and its correction,
        line breaks, Live re-anchoring, and the caption on a small fake page (fill, lines, live region, cut, fade)."""
        run = subprocess.run([NODE, SCRIPT], capture_output=True, text=True, timeout=60, cwd=ROOT)
        out = (run.stdout + run.stderr).strip()
        self.assertEqual(run.returncode, 0, out[-1500:])
        self.assertTrue(run.stdout.strip().startswith("OK "), out[-500:])


class CaptionsPageTests(unittest.TestCase):
    def test_page_loads_captions_before_app(self):
        status, body, _ = helpers.api("GET", "/mary.html")
        self.assertEqual(status, 200)
        html = body.decode("utf-8") if isinstance(body, bytes) else str(body)
        self.assertIn('href="/mary/captions.css"', html)
        cap, app = html.find('src="/mary/captions.js"'), html.find('src="/mary/app.js"')
        self.assertTrue(0 <= cap < app, "captions.js must load before app.js")

    def test_files_are_served(self):
        for path in ("/mary/captions.js", "/mary/captions.css"):
            status, body, _ = helpers.api("GET", path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body, path)


if __name__ == "__main__":
    unittest.main()
