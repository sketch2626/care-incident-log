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


def wiki_page(index, title, image, extract=""):  # M4a
    return {"index": index, "title": title, "pageimage": image, "extract": extract,
            "thumbnail": {"source": "https://upload.wikimedia.org/thumb/" + image.replace(" ", "_")}}


class FakeWiki:
    """Routes the skill's fetches like Wikipedia would, and records every one."""

    def __init__(self):
        self.pages = [CARDINAL]
        self.by_query = {}          # M4a: search words -> their own results, instead of self.pages
        self.search_errors = {}     # M4a: search words -> raise this
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
            if url == getattr(self, "bad_url", None):  # M4a
                raise SkillFetchError("too_big")
            return {"status": 200, "content_type": "image/jpeg", "body": self.image_body}
        params = params or {}
        if "generator" in params:
            words = params["gsrsearch"]
            if words in self.search_errors:
                raise self.search_errors[words]
            pages = self.by_query.get(words, self.pages)  # M4a
            return self._json({"query": {"pages": pages}} if pages else {"batchcomplete": True})
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

    def see(self, *answers):  # M4a: Mary's eyes: each look takes the next answer, and the last one repeats
        self.looks = []
        queue = list(answers)

        def vision(data, mime, question):
            self.looks.append({"data": data, "mime": mime, "question": question})
            answer = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(answer, Exception):
                raise answer
            return answer
        self.host.vision = vision

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
        self.see("YES\nA red bird in the snow.")  # M4a: a file from the article shows only when she sees what it is
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


class RankingTest(PicturesCase):  # M4a: test words may name things; the skill itself never does
    MASCOT = wiki_page(1, "Cardinal Bird", "LouisvilleMascot.jpg", "The Cardinal Bird cheers for a college.")

    def rank(self, page, query):
        return self.mod._rank(page, query)

    def test_mascot_under_the_exact_title_loses_to_the_species(self):
        self.wiki.pages = [self.MASCOT, dict(CARDINAL, index=2)]
        r = self.show("cardinal bird")
        self.assertEqual(self.picture_effect(r)["data"]["title"], "Northern cardinal")
        self.assertEqual(len(self.wiki.searches()), 1)

    def test_mascot_seen_in_title_extract_or_image(self):
        for page in (wiki_page(1, "Duke", "Dog.jpg", "Duke is the mascot of a school."),
                     wiki_page(1, "Duke", "Duke costume.jpg", "Duke was a friendly fellow."),
                     wiki_page(1, "Duke", "DukeLogo.png", "Duke was a friendly fellow.")):
            self.assertEqual(self.rank(page, "duke"), self.mod.RANK_LAST, page["pageimage"])

    def test_asking_for_a_mascot_still_finds_one(self):
        self.assertEqual(self.rank(wiki_page(1, "School mascot", "Mascot.jpg"), "school mascot"), 0)

    def test_exact_title_still_wins(self):
        eagle = wiki_page(1, "Eagle", "Golden Eagle.jpg", "Eagle is the common name for a large bird of prey.")
        self.assertEqual(self.rank(eagle, "eagle"), 0)
        self.assertEqual(self.rank(eagle, "an eagle"), 0)
        self.assertEqual(self.rank(wiki_page(1, "Grand Canyon", "Canyon.jpg"), "the Grand Canyon"), 0)

    def test_living_thing_needs_one_asked_word_and_its_own_text(self):
        self.assertEqual(self.rank(CARDINAL, "cardinal bird"), 1)
        self.assertEqual(self.rank(CARDINAL, "cardinal"), 1)
        self.assertEqual(self.rank(wiki_page(1, "Cardinal Richelieu", "Bird feeder.jpg", "A statesman."), "cardinal"), 2)
        self.assertEqual(self.rank(wiki_page(1, "The Ladder", "Bird.jpg", "A bird on one."), "the rope"), 2)

    def test_namesake_stays_below_the_rest(self):
        self.assertEqual(self.rank(wiki_page(1, "Cardinal stadium", "TeamLogo.png"), "cardinal"), 3)

    def test_drawing_only_when_nothing_else_exists(self):
        drawing = wiki_page(1, "Cardinal (church)", "Galero.svg", "A church official.")
        self.assertEqual(self.rank(drawing, "cardinal (church)"), self.mod.RANK_LAST)
        self.wiki.pages = [drawing, wiki_page(2, "Cardinal direction", "Compass.jpg", "North and south.")]
        self.assertEqual(self.picture_effect(self.show("cardinal"))["data"]["title"], "Cardinal direction")
        self.wiki.pages = [drawing]
        self.assertEqual(self.picture_effect(self.show("cardinal"))["data"]["title"], "Cardinal (church)")

    def test_second_search_finds_the_species(self):
        self.wiki.by_query = {
            "cardinal": [wiki_page(1, "Cardinal (Catholic Church)", "Galero.svg", "A church official."),
                         wiki_page(2, "Cardinal Richelieu", "Richelieu.jpg", "A French statesman."),
                         wiki_page(3, "Cardinal direction", "Compass.jpg", "North and south.")],
            "cardinal species": [CARDINAL]}
        r = self.show("cardinal")
        self.assertEqual(self.picture_effect(r)["data"]["title"], "Northern cardinal")
        self.assertEqual([c["params"]["gsrsearch"] for c in self.wiki.searches()], ["cardinal", "cardinal species"])

    def test_a_disambiguation_page_does_not_stop_the_second_search(self):
        self.wiki.by_query = {"cardinal": [dict(CARDINAL, title="Cardinal", pageprops={"disambiguation": ""})],
                              "cardinal species": [CARDINAL]}
        self.assertEqual(self.picture_effect(self.show("cardinal"))["data"]["title"], "Northern cardinal")

    def test_never_more_than_two_searches(self):
        self.wiki.by_query = {"old truck": [wiki_page(1, "Pickup history", "Truck.jpg", "Trucks.")],
                              "old truck species": [wiki_page(1, "Truck stop", "Stop.jpg", "A place.")]}
        r = self.show("old truck")
        self.assertEqual(self.picture_effect(r)["data"]["title"], "Pickup history")
        self.assertEqual(len(self.wiki.searches()), 2)

    def test_first_results_stand_if_the_second_search_fails(self):
        self.wiki.pages = [wiki_page(1, "Pickup history", "Truck.jpg", "Trucks.")]
        self.wiki.search_errors = {"old truck species": SkillFetchError("http_error")}
        self.assertEqual(self.picture_effect(self.show("old truck"))["data"]["title"], "Pickup history")

    def test_no_canned_subject(self):
        card = (SKILL / "manifest.json").read_text(encoding="utf-8").lower()
        for word in ("bird", "cardinal", "eagle", "robin"):
            self.assertNotIn(word, card)
        self.assertNotIn("bird", self.mod.SAY_BLOCKED)


class VisionTest(PicturesCase):  # M4a: she sees what's really shown
    RED = wiki_page(1, "Northern cardinal", "Red.jpg", "A red bird.")
    GREY = wiki_page(2, "Cardinal tetra", "Grey.jpg", "A small fish.")
    BLUE = wiki_page(3, "Cardinal beetle", "Blue.jpg", "An insect, not a bird.")

    def next_ready(self):
        self.show()
        self.wiki.images = ["File:Cardinal.jpg", "File:One.jpg", "File:Two.jpg", "File:Three.jpg"]
        for name in ("One", "Two", "Three"):
            self.wiki.info[f"File:{name}.jpg"] = {
                "title": f"File:{name}.jpg", "imagerepository": "shared",
                "imageinfo": [{"thumburl": f"https://upload.wikimedia.org/thumb/{name}.jpg",
                               "extmetadata": {"Artist": {"value": name}}}]}

    def test_yes_keeps_what_she_saw(self):
        self.see("YES\nA red bird on a snowy branch.")
        r = self.show()
        self.assertEqual(r["response"]["seen"], "A red bird on a snowy branch.")
        view = self.host.view("pictures")
        self.assertIn("Seen: A red bird on a snowy branch.", view)
        self.assertEqual([(x["data"], x["mime"]) for x in self.looks], [(JPEG, "image/jpeg")])

    def test_seen_stays_in_a_full_view(self):
        self.wiki.pages = [dict(CARDINAL, extract="A bird. " * 200)]
        self.see("YES\nA red bird.")
        self.show()
        view = self.host.view("pictures")
        self.assertIn("Seen: A red bird.", view)
        self.assertLessEqual(len(view), 600)

    def test_question_names_the_article_when_it_differs(self):
        self.see("YES\nA red bird.")
        self.show("cardinal")
        question = self.looks[0]["question"]
        self.assertIn('real cardinal (the article "Northern cardinal"), as a photo or painting', question)
        self.assertIn("Answer YES or NO on the first line", question)
        self.wiki.pages = [wiki_page(1, "Eagle", "Eagle.jpg", "A large bird.")]
        self.show("eagle")
        self.assertIn("a real eagle, as a photo", self.looks[1]["question"])

    def test_no_goes_to_the_next_candidate(self):
        self.wiki.pages = [self.RED, self.GREY]
        self.see("NO\nA person in a bird costume.", "YES\nA small silver fish.")
        r = self.show("cardinal")
        self.assertEqual(self.picture_effect(r)["data"]["title"], "Cardinal tetra")
        self.assertEqual(r["response"]["seen"], "A small silver fish.")
        self.assertEqual(len(self.looks), 2)

    def test_two_noes_and_she_stops(self):
        self.wiki.pages = [self.RED, self.GREY, self.BLUE]
        self.see("NO\nA cartoon.")
        r = self.show("cardinal")
        self.assertIsNone(self.picture_effect(r))
        self.assertEqual(r["say"], self.mod.SAY_NOT_FOUND)
        self.assertEqual((len(self.looks), len(self.wiki.images_fetched())), (2, 2))
        self.assertEqual(self.pic_files(), [])

    def test_a_picture_that_wont_load_costs_no_look(self):
        self.wiki.pages = [self.RED, self.GREY]
        self.wiki.bad_url = self.RED["thumbnail"]["source"]
        self.see("YES\nA small silver fish.")
        r = self.show("cardinal")
        self.assertEqual(self.picture_effect(r)["data"]["title"], "Cardinal tetra")
        self.assertEqual(len(self.looks), 1)

    def test_no_answer_falls_back_to_the_lead_image(self):
        for answer in ("", "   ", "Maybe, it's hard to say.", "Nothing to see", RuntimeError("boom")):
            self.wiki.pages = [self.RED, self.GREY]
            self.see(answer)
            r = self.show("cardinal")
            self.assertEqual(self.picture_effect(r)["data"]["title"], "Northern cardinal", repr(answer))
            self.assertNotIn("seen", r["response"], repr(answer))
            self.assertNotIn("Seen:", self.host.view("pictures"))
            self.assertEqual(len(self.looks), 1)

    def test_a_no_then_no_answer_shows_the_next_one_unchecked(self):
        self.wiki.pages = [self.RED, self.GREY]
        self.see("NO\nA logo.", "")
        r = self.show("cardinal")
        self.assertEqual(self.picture_effect(r)["data"]["title"], "Cardinal tetra")
        self.assertNotIn("seen", r["response"])

    def test_no_vision_at_all_shows_the_lead_image(self):
        r = self.show()
        self.assertEqual(self.picture_effect(r)["data"]["title"], "Northern cardinal")
        self.assertNotIn("seen", r["response"])

    def test_a_new_picture_forgets_the_old_seen(self):
        self.see("YES\nA red bird.", "")
        self.show()
        self.show()
        self.assertNotIn("Seen:", self.host.view("pictures"))

    def test_no_look_without_the_time_for_it(self):
        self.mod.TIME_BUDGET_S = 3.0
        self.see("NO\nA logo.")
        r = self.show()
        self.assertEqual(self.picture_effect(r)["data"]["title"], "Northern cardinal")
        self.assertEqual(self.looks, [])

    def test_next_with_no_vision_shows_nothing(self):
        self.next_ready()
        for answer in (None, ""):
            if answer is not None:
                self.see(answer)
            r = self.host.call("pictures__next_picture")
            self.assertIsNone(self.picture_effect(r))
            self.assertIn("only picture", r["say"])
            self.assertEqual(self.pic_files(), ["pic-1.jpg"])

    def test_next_comes_back_once_vision_does(self):
        self.next_ready()
        self.host.call("pictures__next_picture")
        self.see("YES\nA red bird on a fence.")
        r = self.host.call("pictures__next_picture")
        self.assertIn("One", self.picture_effect(r)["data"]["credit"])
        self.assertEqual(r["response"]["seen"], "A red bird on a fence.")
        self.assertIn("Seen: A red bird on a fence.", self.host.view("pictures"))

    def test_next_skips_a_no(self):
        self.next_ready()
        self.see("NO\nA range map.", "YES\nA red bird.")
        r = self.host.call("pictures__next_picture")
        self.assertIn("Two", self.picture_effect(r)["data"]["credit"])
        self.assertEqual(self.pic_files(), ["pic-2.jpg"])

    def test_next_looks_at_most_twice(self):
        self.next_ready()
        self.see("NO\nA range map.")
        r = self.host.call("pictures__next_picture")
        self.assertIsNone(self.picture_effect(r))
        self.assertEqual(len(self.looks), 2)
        self.assertEqual(self.pic_files(), ["pic-1.jpg"])

    def test_no_look_on_close_or_a_blocked_ask(self):
        self.show()
        self.see("YES\nA red bird.")
        self.host.call("pictures__close_picture")
        self.host.call("pictures__show_picture", {"what": "naked people"})
        self.assertEqual(self.looks, [])

    def test_look_needs_the_card_field(self):
        self.see("YES\nA red bird.")
        ctx = self.host.context("pictures")
        self.assertEqual(ctx.look(JPEG, "image/jpeg", "What is it?"), "YES\nA red bird.")
        self.host.skills["pictures"].manifest.pop("vision")
        self.assertEqual(ctx.look(JPEG, "image/jpeg", "What is it?"), "")
        self.assertEqual(len(self.looks), 1)

    def test_look_with_no_host_vision_or_a_failure_is_empty(self):
        ctx = self.host.context("pictures")
        self.assertEqual(ctx.look(JPEG, "image/jpeg", "What is it?"), "")
        self.see(RuntimeError("boom"))
        self.assertEqual(ctx.look(JPEG, "image/jpeg", "What is it?"), "")

    def test_card_field_must_be_true_or_false(self):
        self.assertEqual(skills_core.manifest_problems(MANIFEST, "pictures"), [])
        self.assertIn("vision must be true or false",
                      skills_core.manifest_problems(dict(MANIFEST, vision="yes"), "pictures"))

    def test_verdict(self):
        for answer, want in (("YES\nA bird.", (True, "A bird.")), ("no. A logo.", (False, "A logo.")),
                             ("**Yes** - a bird", (True, "a bird")), ("YES", (True, "")),
                             ("Not really", (None, "")), ("", (None, "")), (None, (None, ""))):
            self.assertEqual(self.mod.verdict(answer), want, repr(answer))


class PlainTextTest(PicturesCase):  # M4a
    def artist(self, value):
        return self.mod.credit_text({"Artist": {"value": value}})

    def test_credit_never_holds_html(self):
        for value in ('<a href="https://commons.wikimedia.org/wiki/User:Jane">Jane Doe</a>',
                      '&lt;a href=&quot;//commons/x&quot;&gt;Jane Doe&lt;/a&gt;',
                      'Jane Doe <a href="https://commons.wikimedia.org/wiki/User:Ja',
                      'Jane Doe &lt;a href=&quot;https://commons.wikimedia.org/wiki/Us',
                      '&amp;lt;b&amp;gt;Jane Doe&amp;lt;/b&amp;gt;',
                      'Jane Doe&bogus;', 'Jane Doe &quo'):
            self.assertEqual(self.artist(value), "Photo: Jane Doe · Wikimedia Commons", value)

    def test_a_credit_that_is_only_a_cut_off_tag_is_no_credit(self):
        self.assertEqual(self.artist('<a href="https://commons.wikimedia.org/wiki/Us'), "Photo from Wikimedia Commons")

    def test_ordinary_text_stands(self):
        for text in ("AT&T", "R&B records", "5 < 7", "Fish & chips"):
            self.assertEqual(self.mod.plain_text(text, 100), text)

    def test_title_summary_and_say_are_plain(self):
        self.wiki.pages = [dict(CARDINAL, title="Northern <i>cardinal</i>", extract='A <b>bird</b> &lt;a href=&quot;x')]
        r = self.show()
        self.assertEqual(r["say"], "Here's Northern cardinal.")
        self.assertEqual(r["response"]["summary"], "A bird")
        self.assertEqual(self.picture_effect(r)["data"]["title"], "Northern cardinal")

    def test_seen_is_plain(self):
        self.see('YES\nA red bird <a href="x">here</a> &lt;b')
        self.assertEqual(self.show()["response"]["seen"], "A red bird here")


class ScreenScriptTest(unittest.TestCase):
    def test_text_never_goes_in_as_html(self):  # M4a
        self.assertNotRegex((SKILL / "screen.js").read_text(encoding="utf-8"), r"innerHTML\s*=\s*[^'\s]")

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
