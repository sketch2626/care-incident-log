from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""Mary's screen is served: the page, its script and its style load, and the page uses the face script."""
import re
import unittest

api = helpers.api


class MaryPageTests(unittest.TestCase):
    def get(self, path):
        status, body, headers = api("GET", path)
        self.assertEqual(status, 200, path)
        self.assertIsInstance(body, bytes, path)
        return body.decode("utf-8"), headers

    def test_page_loads_and_uses_face_and_app_scripts(self):
        html, headers = self.get("/mary.html")
        ctype = {k.lower(): v for k, v in headers.items()}.get("content-type", "")
        self.assertIn("text/html", ctype)
        self.assertIn("/mary/face.js", html)
        self.assertIn("/mary/face.css", html)
        self.assertIn("/mary/mary.css", html)
        self.assertIn("/mary/app.js", html)
        for needle in ('id="talkBtn"', 'id="caption"', 'id="lightBtn"', 'id="okBtn"', 'id="infoBtn"', 'id="moreBtn"'):
            self.assertIn(needle, html)

    def test_app_script_and_style_load(self):
        js, _ = self.get("/mary/app.js")
        self.assertIn("MaryApp", js)
        self.assertIn("/api/mary/talk", js)
        css, _ = self.get("/mary/mary.css")
        self.assertIn(".talk", css)

    def test_firstrun_script_loads_after_app_script(self):
        js, _ = self.get("/mary/firstrun.js")
        self.assertIn("MaryApp", js)
        self.assertIn("/api/mary/hello", js)
        html, _ = self.get("/mary.html")
        self.assertIn("/mary/firstrun.js", html)
        self.assertGreater(html.index("/mary/firstrun.js"), html.index("/mary/app.js"))

    def test_firstrun_idle_timings_are_in_one_config(self):
        js, _ = self.get("/mary/firstrun.js")
        self.assertRegex(js, r"var IDLE = \{\s*sleepMin:\s*5,\s*dimMin:\s*15\s*\}")
        self.assertIn("/api/power", js)
        self.assertIn("wakeLock", js)

    def test_more_button_stays_on_first_run_screens_and_menu_keeps_a_way_out(self):
        # first run has no other way out of her full-screen window, so More must show on choose and hello,
        # and the menu there must keep Close and Done while hiding the items that would derail the first run
        css, _ = self.get("/mary/mary.css")
        html, _ = self.get("/mary.html")
        self.assertNotRegex(css, r'\[data-screen="(choose|hello)"\]\s*\.more')
        rule = re.search(r'\[data-screen="choose"\] \.menu \.panel > ([^,{]+),\s*\[data-screen="hello"\] \.menu \.panel > ([^{]+)\{display:none\}', css)
        self.assertIsNotNone(rule, "first-run menu rule is missing")
        for selector in rule.groups():
            self.assertIn(":not(#closeBtn)", selector)
            self.assertIn(':not([data-act="done"])', selector)
        self.assertIn('id="closeBtn"', html)
        self.assertIn('data-act="done"', html)

    def test_face_files_still_load(self):
        self.get("/mary/face.js")
        self.get("/mary/face.css")


if __name__ == "__main__":
    unittest.main()
