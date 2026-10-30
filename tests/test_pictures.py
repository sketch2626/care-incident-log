from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""The pictures skill (Wikipedia lead image): fake Wikipedia, temp folders, no network."""
import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
import urllib.parse
from pathlib import Path

import server
import skills_core
from skills_core import SkillFetchError

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "pictures"
JPEG = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
MANIFEST = json.loads((SKILL / "manifest.json").read_text(encoding="utf-8"))
CARDINAL = {"index": 1, "title": "Northern cardinal", "pageimage": "Cardinal.jpg",
            "extract": "The northern cardinal is a bird. It is bright red.",
            "thumbnail": {"source": "https://upload.wikimedia.org/thumb/Cardinal.jpg"}}
ARTIST_META = {"Artist": {"value": '<a href="//commons/x">Jane <b>Doe</b></a>'},
               "LicenseShortName": {"value": "CC BY-SA 4.0"}}


class FakeWiki:
    """Routes the skill's fetches like Wikipedia would, and records every one."""

    def __init__(self):
        self.pages = [CARDINAL]
        self.info = {}              # "File:Name.jpg" -> file page
        self.images = []            # titles for the "images" listing
        self.credit_error = None    # raise this on imageinfo calls
        self.image_error = None
        self.image_body = JPEG
        self.calls = []

    def __call__(self, skill_name, url, method="GET", params=None, headers=None, max_bytes=2_000_000, timeout=6):
        self.calls.append({"skill": skill_name, "url": url, "params": params, "max_bytes": max_bytes})
        host = urllib.parse.urlsplit(url).hostname
        if host == "upload.wikimedia.org":
            if self.image_error:
                raise self.image_error
            return {"status": 200, "content_type": "image/jpeg", "body": self.image_body}
        params = params or {}
        if "generator" in params:
            return self._json({"query": {"pages": self.pages}} if self.pages else {"batchcomplete": True})
        if params.get("prop") == "imageinfo":
            if self.credit_error:
                raise self.credit_error
            out = []
            for title in params["titles"].split("|"):
                out.append(self.info.get(title) or {"title": title, "imagerepository": "shared",
                                                    "imageinfo": [{"extmetadata": ARTIST_META}]})
            return self._json({"query": {"pages": out}})
        if params.get("prop") == "images":
            return self._json({"query": {"pages": [{"title": "Northern cardinal",
                                                    "images": [{"title": t} for t in self.images]}]}})
        raise AssertionError("unexpected request " + url)

    @staticmethod
    def _json(data):
        return {"status": 200, "content_type": "application/json", "body": json.dumps(data).encode("utf-8")}

    def searches(self):
        return [c for c in self.calls if "generator" in (c["params"] or {})]

    def images_fetched(self):
        return [c for c in self.calls if urllib.parse.urlsplit(c["url"]).hostname == "upload.wikimedia.org"]


class PicturesCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="pictures-", dir=helpers.TMP))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.skills_dir = self.dir / "skill_code"
        shutil.copytree(SKILL, self.skills_dir / "pictures", ignore=shutil.ignore_patterns("__pycache__"))
        self.wiki = FakeWiki()
        self.online = True
        self.settings = {}
        self.host = self.make_host()
        self.files = self.dir / "skills" / "pictures"

    def make_host(self):
        db = self.dir / "t.db"
        host = skills_core.SkillHost(self.skills_dir, self.dir, lambda: sqlite3.connect(db),
                                     lambda: dict(self.settings), self.settings.update,
                                     online=lambda: self.online, fetcher=self.wiki)
        host.load()
        return host

    @property
    def mod(self):
        return self.host.skills["pictures"].module

    def pic_files(self):
        return sorted(p.name for p in self.files.glob("pic-*")) if self.files.exists() else []

    def show(self, what="cardinal bird"):
        return self.host.call("pictures__show_picture", {"what": what})

    def picture_effect(self, result):
        found = [e for e in result["effects"] if e.get("kind") == "picture"]
        return found[0] if found else None


class ShowPictureTest(PicturesCase):
    def test_found(self):
        r = self.show()
        self.assertTrue(r["say"].startswith("Here's "))
        self.assertIn("Northern cardinal", r["say"])
        kinds = [e["kind"] for e in r["effects"]]
        self.assertEqual(kinds, ["show_screen", "picture"])
        data = self.picture_effect(r)["data"]
        self.assertEqual(data["src"], "/api/mary/skills/pictures/image/pic-1.jpg")
        self.assertEqual(data["title"], "Northern cardinal")
        self.assertIn("Jane Doe", data["credit"])
        self.assertNotIn("<", data["credit"])
        self.assertIn("CC BY-SA 4.0", data["credit"])
        self.assertEqual(self.pic_files(), ["pic-1.jpg"])
        self.assertEqual((self.files / "pic-1.jpg").read_bytes(), JPEG)
        text = self.host.view("pictures")
        self.assertIn("Northern cardinal", text)
        self.assertIn("bright red", text)
        self.assertLessEqual(len(text), 600)

    def test_credit_lookup_fails(self):
        self.wiki.credit_error = SkillFetchError("http_error")
        r = self.show()
        data = self.picture_effect(r)["data"]
        self.assertEqual(data["credit"], "Photo from Wikipedia")
        self.assertEqual(self.pic_files(), ["pic-1.jpg"])

    def test_not_found(self):
        self.wiki.pages = []
        r = self.show("zzzz")
        self.assertEqual(r["say"], self.mod.SAY_NOT_FOUND)
        self.assertIsNone(self.picture_effect(r))
        self.assertEqual(self.pic_files(), [])

    def test_only_disambiguation(self):
        self.wiki.pages = [dict(CARDINAL, pageprops={"disambiguation": ""})]
        r = self.show("cardinal")
        self.assertEqual(r["say"], self.mod.SAY_NOT_FOUND)
        self.assertIsNone(self.picture_effect(r))
        self.assertEqual(self.wiki.images_fetched(), [])

    def test_offline_fetch_error(self):
        self.wiki.pages = None  # unused; fetcher replaced below

        def offline(*a, **k):
            raise SkillFetchError("offline")

        self.host._fetcher = offline
        out = self.mod.show_picture(self.host.context("pictures"), "cardinal")
        self.assertEqual(out["say"], "I need the internet to find pictures.")
        self.assertEqual(self.pic_files(), [])

    def test_offline_host_is_polite(self):
        self.online = False
        r = self.show()
        self.assertTrue(r["say"])
        self.assertEqual(r["response"].get("error"), "needs_internet")
        self.assertEqual(self.wiki.calls, [])
        self.assertIsNone(self.picture_effect(r))

    def test_too_big_image(self):
        self.wiki.image_error = SkillFetchError("too_big")
        r = self.show()
        self.assertIsNone(self.picture_effect(r))
        self.assertTrue(r["say"])
        self.assertEqual(self.pic_files(), [])
        for call in self.wiki.images_fetched():
            self.assertLessEqual(call["max_bytes"], 4_000_000)

    def test_image_max_bytes_on_success(self):
        self.show()
        fetched = self.wiki.images_fetched()
        self.assertEqual(len(fetched), 1)
        self.assertLessEqual(fetched[0]["max_bytes"], 4_000_000)

    def test_not_an_image(self):
        self.wiki.image_body = b"<html>nope</html>"
        r = self.show()
        self.assertIsNone(self.picture_effect(r))
        self.assertEqual(r["say"], self.mod.SAY_NOT_FOUND)
        self.assertEqual(self.pic_files(), [])

    def test_blocked_query_never_fetches(self):
        r = self.show("naked people")
        self.assertEqual(r["say"], self.mod.SAY_BLOCKED)
        self.assertEqual(self.wiki.calls, [])
        self.assertIsNone(self.picture_effect(r))

    def test_blocklist_allows_normal_asks(self):
        for ok in ("deer hunting rifle", "naked mole rat", "breast stroke swimming", "church"):
            self.assertFalse(self.mod.blocked(ok), ok)
        for bad in ("naked people", "porn", "gory accident"):
            self.assertTrue(self.mod.blocked(bad), bad)

    def test_only_search_words_go_out(self):
        self.show("  cardinal   bird ")
        searches = self.wiki.searches()
        self.assertEqual(len(searches), 1)
        self.assertEqual(searches[0]["params"]["gsrsearch"], "cardinal bird")
        self.assertEqual(searches[0]["url"], "https://en.wikipedia.org/w/api.php")
        allowed = set(MANIFEST["needs"]["internet_hosts"])
        for call in self.wiki.calls:
            self.assertIn(urllib.parse.urlsplit(call["url"]).hostname, allowed)
            self.assertEqual(call["skill"], "pictures")
            for value in (call["params"] or {}).values():
                self.assertNotIn("password", str(value).lower())
        for call in self.wiki.images_fetched():
            self.assertEqual(urllib.parse.urlsplit(call["url"]).hostname, "upload.wikimedia.org")
            self.assertIsNone(call["params"])

    def test_image_from_other_host_refused(self):
        self.wiki.pages = [dict(CARDINAL, thumbnail={"source": "https://evil.example.com/a.jpg"})]
        r = self.show()
        self.assertEqual(r["say"], self.mod.SAY_NOT_FOUND)
        self.assertEqual(self.wiki.images_fetched(), [])


class NextAndCloseTest(PicturesCase):
    def test_next_without_picture(self):
        r = self.host.call("pictures__next_picture")
        self.assertEqual(r["say"], self.mod.SAY_NO_PICTURE)
        self.assertEqual(self.wiki.calls, [])

    def test_next_picture_replaces_old_file(self):
        self.show()
        self.wiki.images = ["File:Cardinal.jpg", "File:Red Cardinal 2.jpg", "File:Flag icon.svg"]
        self.wiki.info["File:Red Cardinal 2.jpg"] = {
            "title": "File:Red Cardinal 2.jpg", "imagerepository": "shared",
            "imageinfo": [{"thumburl": "https://upload.wikimedia.org/thumb/Red2.jpg",
                           "extmetadata": {"Artist": {"value": "Bob Smith"}}}]}
        r = self.host.call("pictures__next_picture")
        data = self.picture_effect(r)["data"]
        self.assertEqual(data["src"], "/api/mary/skills/pictures/image/pic-2.jpg")
        self.assertIn("Bob Smith", data["credit"])
        self.assertEqual(self.pic_files(), ["pic-2.jpg"])

    def test_next_with_nothing_new(self):
        self.show()
        self.wiki.images = ["File:Cardinal.jpg", "File:Map of birds.png"]
        r = self.host.call("pictures__next_picture")
        self.assertIn("only picture", r["say"])
        self.assertEqual(self.pic_files(), ["pic-1.jpg"])

    def test_pick_files(self):
        names = ["File:Bird.jpg", "File:Bird icon.png", "File:Logo of club.png", "File:World map.jpg",
                 "File:Drawing.svg", "File:Shown one.jpg", "File:Second.JPEG", "File:Flag of Ohio.png",
                 "File:Photo.gif"]
        got = self.mod.pick_files(names, shown=["Shown_one.jpg"])
        self.assertEqual(got, ["Bird.jpg", "Second.JPEG"])

    def test_close_picture(self):
        self.show()
        r = self.host.call("pictures__close_picture")
        self.assertEqual([e["kind"] for e in r["effects"]], ["leave_screen"])
        self.assertEqual(self.pic_files(), [])
        self.assertEqual(self.host.view("pictures"), "No picture is up.")


class ImageRouteTest(PicturesCase):
    def setUp(self):
        super().setUp()
        helpers.reset_db()
        server.set_skill_host_for_tests(self.host)
        self.addCleanup(server.set_skill_host_for_tests, None)

    def test_saved_image_is_served(self):
        self.show()
        status, body, headers = helpers.api("GET", "/api/mary/skills/pictures/image/pic-1.jpg")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "image/jpeg")
        self.assertEqual(body, JPEG)

    def test_bad_names_are_404(self):
        self.show()
        for path in ("/api/mary/skills/pictures/image/pic-9.jpg", "/api/mary/skills/pictures/image/..%2Fx.jpg",
                     "/api/mary/skills/pictures/image/../x.jpg", "/api/mary/skills/nope/image/pic-1.jpg"):
            status, _, _ = helpers.api("GET", path)
            self.assertEqual(status, 404, path)


class ScreenScriptTest(unittest.TestCase):
    def test_node_check(self):
        node = shutil.which("node")
        if not node and Path(r"C:\Program Files\nodejs\node.exe").exists():
            node = r"C:\Program Files\nodejs\node.exe"
        if not node:
            self.skipTest("node not found")
        done = subprocess.run([node, "--check", str(SKILL / "screen.js")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
