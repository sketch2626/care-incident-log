from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""Mary's screen is served: the page, its script and its style load, and the page uses the face script."""
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

    def test_face_files_still_load(self):
        self.get("/mary/face.js")
        self.get("/mary/face.css")


if __name__ == "__main__":
    unittest.main()
