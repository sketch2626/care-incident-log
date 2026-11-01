from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M17: every way out of Mary has a big way back, the talk mode survives a restart, and when another mode is forced
she says so (once) without changing the saved pick. Static checks on the served pages, plus Node for the pure logic."""
import re
import subprocess
import unittest
from pathlib import Path

import server
from tests.test_story_js import NODE, between

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


def read(rel):
    return (WEB / rel).read_text(encoding="utf-8")


def css_rule(css, selector):
    m = re.search(r"(?m)(?:^|\{)\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, "no CSS rule for " + selector
    return m.group(1)


def min_height(rule):
    m = re.search(r"min-height:\s*(\d+)px", rule)
    assert m, "no min-height in: " + rule
    return int(m.group(1))


class TalkModeSavedTests(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()

    def test_each_mode_survives_a_restart(self):
        for mode in ("live", "offline", "normal"):
            st, _, _ = helpers.api("PUT", "/api/settings", {"talk_mode": mode})
            self.assertEqual(st, 200)
            self.assertEqual(server.mary_settings()["talk_mode"], mode)
            st, j, _ = helpers.api("GET", "/api/mary/status")
            self.assertEqual(j["talk_mode"], mode)
            # a fresh read straight from the saved settings, as a restart would do
            self.assertEqual(server.mary_status()["talk_mode"], mode)

    def test_no_key_drops_live_from_the_order_but_keeps_the_pick(self):
        helpers.api("PUT", "/api/settings", {"talk_mode": "live"})
        _, j, _ = helpers.api("GET", "/api/mary/status")
        self.assertFalse(j["has_key"])
        self.assertNotIn("live", j["talk_order"])
        self.assertEqual(j["talk_mode"], "live")

    def test_saving_the_log_form_leaves_talk_mode_alone_unless_changed(self):
        js = read("app.js")
        near = js[js.index("const modePick"):][:400]
        self.assertIn("!== (", near)
        self.assertIn("payload.talk_mode = modePick", near)
        self.assertNotRegex(js, r"payload\s*=\s*\{[^}]*talk_mode")


FORCED_STUBS = r"""
var said = [], noteBox = { textContent: '' };
var S = { statusLoaded: true, talkMode: 'live', hasKey: false, talkOrder: ['normal', 'offline'], liveFailed: false,
          typingOnly: false, ttsSpent: false, companion: 'her', forcedSaid: {} };
var LIVE_OK = true;
function liveSupported() { return LIVE_OK; }
function nextMode(order, after) { var i = after ? order.indexOf(after) + 1 : 0; return order[i] || ''; }
function say(t) { said.push(t); return Promise.resolve(); }
function $(id) { return id === 'modeNote' ? noteBox : null; }
"""

FORCED_CHECKS = r"""
const assert = require('assert');
(async function () {
  await sayForcedOnce(); await sayForcedOnce();
  assert.strictEqual(said.length, 1, 'once for no key');
  assert.ok(/Gemini key/.test(said[0]));
  assert.strictEqual(S.talkMode, 'live', 'pick unchanged');
  fillModeNote();
  assert.ok(/Your pick is still saved/.test(noteBox.textContent));
  assert.strictEqual(S.talkMode, 'live');
  S.hasKey = true; LIVE_OK = false; S.talkOrder = ['live', 'normal'];
  await sayForcedOnce(); await sayForcedOnce();
  assert.strictEqual(said.length, 2, 'a new reason, one more line');
  assert.ok(/won't run on this computer/.test(said[1]));
  assert.strictEqual(S.talkMode, 'live');
  LIVE_OK = true; S.forcedSaid = {}; said.length = 0;
  await sayForcedOnce(); fillModeNote();
  assert.strictEqual(said.length, 0);
  assert.strictEqual(noteBox.textContent, '');
  assert.strictEqual(forcedNow(), null);
  console.log('OK forced');
})().catch(function (e) { console.error(e && e.stack || e); process.exit(1); });
"""


@unittest.skipUnless(NODE, "Node not found")
class ForcedModeTests(unittest.TestCase):
    def test_she_says_so_once_and_the_pick_stays(self):
        src = read("mary/app.js")
        code = "\n".join([FORCED_STUBS, between(src, "function modeInUse()", "// --- M4a: her hello"), FORCED_CHECKS])
        run = subprocess.run([NODE, "-"], input=code, capture_output=True, text=True, encoding="utf-8",
                             timeout=30, cwd=str(ROOT))
        out = (run.stdout + run.stderr).strip()
        self.assertEqual(run.returncode, 0, out[-1500:])
        self.assertTrue(run.stdout.startswith("OK "), out[-500:])


EXIT_RE = re.compile(r"""(?:href=["']|location\.href\s*=\s*['"]|location\.assign\(['"]|window\.open\(['"])([^'"]*)""")


class BackFromMaryTests(unittest.TestCase):
    def test_every_way_out_of_mary_goes_to_the_log_with_from_mary(self):
        seen = 0
        for name in ("mary.html", "mary/app.js"):
            for m in EXIT_RE.finditer(read(name)):
                url = m.group(1)
                if url in ("", "/mary.html") or url.startswith(("#", "mailto:", "tel:", "http", "data:")) or ".css" in url:
                    continue
                seen += 1
                self.assertRegex(url, r"^/\?from=mary", name + " leaves Mary without from=mary: " + url)
        self.assertGreaterEqual(seen, 3)

    def test_log_page_has_the_big_button_above_main(self):
        html = read("index.html")
        self.assertEqual(html.count('id="backToMary"'), 1)
        b = html.index('<button class="bigbtn alt" id="backToMary" type="button"')
        self.assertLess(b, html.index("<main"))
        css = read("styles.css")
        bar = css_rule(css, ".marybar").replace(" ", "")
        self.assertIn("position:sticky", bar)
        self.assertIn("top:0", bar)
        self.assertIn("background", bar)
        self.assertGreaterEqual(min_height(css_rule(css, ".bigbtn")), 64)
        self.assertIn("location.href = '/mary.html'", read("app.js"))

    def test_every_sheet_panel_has_back_before_its_content(self):
        page = read("mary.html")
        panels = re.split(r'(?=<div id="\w+Panel" class="overlay sheet")', page)[1:]
        self.assertEqual(len(panels), page.count('class="overlay sheet"'))
        self.assertGreaterEqual(len(panels), 4)
        for p in panels:
            back = p.find('<button class="back"')
            self.assertGreater(back, -1)
            for later in ("<h3", "<h2", '<div class="rows"', '<p class="lead"'):
                if later in p:
                    self.assertLess(back, p.index(later), later)
        css = read("mary/mary.css")
        self.assertGreaterEqual(min_height(css_rule(css, ".back")), 64)
        sticky = css_rule(css, ".sheetcard .back").replace(" ", "")
        self.assertIn("position:sticky", sticky)
        self.assertIn("top:0", sticky)

    def test_skill_screens_put_back_first_and_it_is_sticky(self):
        box = between(read("mary/skills.js"), "function boxFor(name)", "boxes[name] = el")
        self.assertLess(box.index("el.appendChild(back)"), box.index("el.appendChild(body)"))
        rule = css_rule(read("mary/mary.css"), ".skill-screen > .btn").replace(" ", "")
        self.assertIn("position:sticky", rule)
        self.assertIn("top:0", rule)
        self.assertIn("background", rule)
        self.assertGreaterEqual(min_height(rule), 64)

    def test_no_flash_of_the_log_home(self):
        html = read("index.html")
        head = html[:html.index("</head>")]
        self.assertIn("<script>", head)
        self.assertIn("c.add('routing')", head)
        self.assertIn("html.routing .wrap", read("styles.css"))
        self.assertRegex(read("app.js"),
                         r"try \{ route\(\); \} finally \{ document\.documentElement\.classList\.remove\('routing'\)")


class ReportBackTests(unittest.TestCase):
    def test_report_has_a_big_back_button_hidden_in_print(self):
        import reports
        html = reports.build_report_html([], {})
        self.assertIn('id="reportBack"', html)
        self.assertIn("history.back()", html)
        self.assertIn("location.href='/'", html)
        pos = html.index('id="reportBack"')
        self.assertLess(pos, html.index("<h1>"))
        self.assertIn('class="backbar noprint"', html[:pos])
        self.assertIn(".noprint { display: none !important; }", html)
        css = html[html.index("<style>"):html.index("</style>")]
        rule = css_rule(css, ".backbar button")
        self.assertGreaterEqual(min_height(rule), 64)
        self.assertGreaterEqual(int(re.search(r"font:\s*bold\s*(\d+)px", rule).group(1)), 20)


if __name__ == "__main__":
    unittest.main()
