from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M4b: Mary's caption font (Fredoka 600, SIL OFL) is bundled and served, so captions work offline."""
import unittest

api = helpers.api


class MaryFontTests(unittest.TestCase):
    def test_font_files_are_served_as_woff2(self):
        for name in ("fredoka-600-latin.woff2", "fredoka-600-latin-ext.woff2"):
            status, body, headers = api("GET", "/mary/fonts/" + name)
            self.assertEqual(status, 200, name)
            self.assertEqual(body[:4], b"wOF2", name)
            ctype = {k.lower(): v for k, v in headers.items()}.get("content-type", "")
            self.assertEqual(ctype, "font/woff2", name)

    def test_page_links_the_local_font_and_license_is_bundled(self):
        status, html, _ = api("GET", "/mary.html")
        self.assertEqual(status, 200)
        self.assertIn(b"/mary/fonts/fonts.css", html)
        self.assertNotIn(b"fonts.googleapis.com", html)
        status, css, _ = api("GET", "/mary/fonts/fonts.css")
        self.assertEqual(status, 200)
        self.assertIn(b"fredoka-600-latin.woff2", css)
        status, lic, _ = api("GET", "/mary/fonts/OFL.txt")
        self.assertEqual(status, 200)
        self.assertIn(b"SIL Open Font License", lic)


if __name__ == "__main__":
    unittest.main()
