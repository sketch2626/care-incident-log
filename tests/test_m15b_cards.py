from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M15b piece 4: the `messages` skill (skills/messages) run by a real SkillHost on the real skills folder, with its
data in a scratch folder. No Gemini, no browser. The contract itself is tests/test_skills_contract.py."""
import base64
import datetime
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import mary
import server
import skills_core

ROOT = helpers.ROOT
SKILLS = ROOT / "skills"
FONTS = ROOT / "web" / "mary" / "fonts"
MANIFEST = json.loads((SKILLS / "messages" / "manifest.json").read_text(encoding="utf-8"))
FRONTS = json.loads((SKILLS / "messages" / "assets" / "fronts.json").read_text(encoding="utf-8"))
SVG = "{http://www.w3.org/2000/svg}"
PLAIN_ENGLISH = ("Dear Mark, I hope the fish are biting and the mornings are quiet. I think about you every day and "
                 "I am proud of the man you grew up to be. ")
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + bytes(range(256)) * 3


def find_node():
    import shutil as _sh
    node = _sh.which("node")
    if node:
        return node
    for base in (os.environ.get("ProgramFiles"), r"C:\Program Files"):
        if base and os.path.isfile(os.path.join(base, "nodejs", "node.exe")):
            return os.path.join(base, "nodejs", "node.exe")
    return None


class Base(unittest.TestCase):
    """A real host on skills/ with scratch data; act() calls one messages tool and returns its response."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="messages-", dir=helpers.TMP))
        self.settings = {}
        self.host = self.new_host()
        self.mail_calls = []

    def new_host(self):
        db = self.dir / "skills.db"
        host = skills_core.SkillHost(SKILLS, self.dir, lambda: sqlite3.connect(db), lambda: dict(self.settings),
                                     self.settings.update)
        host.load(is_blocked=mary.skill_blocked)
        self.assertIn("messages", host.skills, host.load_errors)
        host.mailer = self.no_mail
        return host

    def no_mail(self, *args, **kwargs):
        self.mail_calls.append(args)
        self.fail("the skill tried to send mail")

    @property
    def ctx(self):
        return self.host.context("messages")

    @property
    def mod(self):
        return self.host.skills["messages"].module

    @property
    def folder(self):
        return self.dir / "skills" / "messages"

    def act(self, _tool, **args):
        self.last = self.host.call("messages__" + _tool, args)
        self.assertNotIn("error", self.last["response"], self.last)
        return self.last["response"]

    def event(self, **event):
        return self.host.on_event("messages", event)

    def kinds(self):
        return [e["kind"] for e in self.last["effects"]]

    def read(self, name):
        return (self.folder / name).read_text(encoding="utf-8")

    def draft(self):
        return self.ctx.store.get("draft")

    def card(self, front="lake", words="Happy birthday, son. Catch a big one.", signature="Dad", **start):
        args = {"person": "Mark", "occasion": "birthday", "likes": "fishing", "line": "for my son"}
        args.update(start)
        self.act("show_fronts", **args)
        self.act("pick_front", choice=front)
        return self.act("set_words", words=words, signature=signature) if words else None

    def pictures(self):
        card_id = self.draft()["id"]
        return {part: self.read("card-%s-%s.svg" % (card_id, part)) for part in ("front", "inside", "both", "left", "print")}

    def lines_of(self, svg):
        root = ET.fromstring(svg)
        return [(e, "".join(e.itertext())) for e in root.iter(SVG + "text")]


class FlowTests(Base):
    """Section 1: the whole card by tools, as Mary would call them."""

    def test_fronts_ranked_and_numbered(self):
        r = self.act("show_fronts", person="Mark", occasion="birthday", likes="fishing", line="for my son")
        shown = r["fronts"]
        self.assertIn(len(shown), (3, 4))
        self.assertEqual([f["number"] for f in shown], list(range(1, len(shown) + 1)))
        self.assertEqual(shown[0]["name"], "Lake")
        self.assertNotIn("made to order", json.dumps(self.last).lower())
        self.assertIn("fronts", self.kinds())

    def test_pick_forms(self):
        self.act("show_fronts", person="Mark", occasion="birthday", likes="fishing")
        names = [f["name"] for f in self.act("change_front")["fronts"]]
        keys = self.draft()["shown"]
        every = {e["key"]: e for e in FRONTS}
        other_tags = lambda k: {t.lower() for j in keys if j != k for t in every[j]["tags"]}  # noqa: E731
        unique = next(((k, t) for k in keys for t in every[k]["tags"] if t.lower() not in other_tags(k)
                       and t.lower() not in {w for j in keys for w in re.findall(r"[a-z]+", every[j]["name"].lower())}),
                      None)
        self.assertIsNotNone(unique, "no front has a tag word of its own")
        cases = [("the second one", keys[1]), ("3", keys[2]), (names[1], keys[1]), ("the one with the %s" % unique[1], unique[0])]
        for choice, key in cases:
            r = self.act("pick_front", choice=choice)
            self.assertEqual(self.draft()["front"], key, choice)
            self.assertEqual(r["picked"], every[key]["name"], choice)
            self.act("change_front")
        self.assertIsNone(self.act("pick_front", choice="the purple one")["picked"])

    def test_pick_by_tap_carries_a_say(self):
        self.act("show_fronts", person="Mark", occasion="birthday", likes="fishing")
        key = self.draft()["shown"][2]
        got = self.event(type="pick", key=key)
        self.assertEqual(self.draft()["front"], key)
        self.assertTrue(got["say"])
        self.assertEqual(self.event(type="pick", key="nope")["response"], {"ignored": True})

    def test_words_read_back_and_change(self):
        r = self.card(words="Happy birthday, son.", signature="Dad")
        self.assertTrue(r["saved"])
        self.assertIn("Happy birthday, son.", r["read_back"])
        self.assertIn("Dad", r["read_back"])
        again = self.act("set_words", words="Many happy returns.")
        self.assertIn("Many happy returns.", again["read_back"])
        self.assertNotIn("Happy birthday, son.", again["read_back"])
        self.assertIn("Dad", again["read_back"])  # the signature is kept
        back = self.act("read_back")
        self.assertEqual((back["words"], back["signature"]), ("Many happy returns.", "Dad"))
        self.assertIn("Many happy returns.", self.read("card-%s-inside.svg" % self.draft()["id"]))

    def test_words_wait_for_a_signature_and_a_front(self):
        self.act("show_fronts", person="Mark")
        self.assertFalse(self.act("set_words", words="Hello")["saved"])  # no front yet
        self.act("pick_front", choice="1")
        r = self.act("set_words", words="Hello")
        self.assertEqual(r.get("need"), "signature")
        self.assertFalse(self.folder.exists() and any(self.folder.glob("card-*-inside.svg")))

    def test_hand_plain_then_cursive_and_remembered(self):
        self.card()
        inside = lambda: self.read("card-%s-inside.svg" % self.draft()["id"])  # noqa: E731
        self.assertIn("Cedarville", inside())
        self.assertNotIn("Kalam", inside())
        self.assertEqual(self.act("set_hand", hand="plain")["hand"], "plain")
        self.assertIn("Kalam", inside())
        self.assertNotIn("Cedarville", inside())
        self.assertEqual(self.ctx.store.get("hand"), "plain")
        self.assertEqual(self.act("set_hand", hand="cursive")["hand"], "cursive")
        self.assertIn("Cedarville", inside())
        self.assertEqual(self.ctx.store.get("hand"), "cursive")
        self.assertEqual(self.act("set_hand")["hand"], "plain")  # no choice swaps
        self.act("show_fronts", person="Ann")  # the next card starts in the remembered hand
        self.assertEqual(self.draft()["hand"], "plain")

    def test_verse_next_and_none(self):
        self.card(front="lake", words="Happy birthday.", person_is="man")
        first = self.draft()["verse"]
        self.assertTrue(first)
        self.act("change_verse", which="next")
        second = self.draft()["verse"]
        self.assertNotEqual(first, second)
        self.assertTrue(self.read("card-%s-inside.svg" % self.draft()["id"]).count("<text") >= 2)
        self.act("change_verse", which="none")
        self.assertEqual(self.draft()["verse"], [])
        self.assertNotIn(second[0], self.read("card-%s-inside.svg" % self.draft()["id"]))

    def test_change_front_keeps_the_words(self):
        self.card(words="Stay well.", signature="Mom")
        self.act("change_front")
        self.assertEqual(self.draft()["words"], "Stay well.")
        self.act("pick_front", choice="2")
        d = self.draft()
        self.assertEqual((d["words"], d["signature"]), ("Stay well.", "Mom"))
        self.assertIn("Stay well.", self.read("card-%s-inside.svg" % d["id"]))

    def test_save_and_print(self):
        self.assertFalse(self.act("save_card_now")["saved"])
        self.card()
        self.assertTrue(self.act("save_card_now")["saved"])
        r = self.act("print_card")
        self.assertTrue(r["printing"])
        prints = [e for e in self.last["effects"] if e["kind"] == "print"]
        self.assertEqual([e["data"]["file"] for e in prints], ["card-%s-print.svg" % self.draft()["id"]])
        self.assertIn("facility", self.last["say"])
        self.assertIn("mail", self.last["say"].lower())


class PictureTests(Base):
    """Section 2: the saved pictures are whole, self-contained and stay in the skill's folder."""

    def before(self):
        return {p for p in self.dir.rglob("*") if p.is_file()}

    def test_five_pictures_valid_and_self_contained(self):
        self.assertTrue(list(FONTS.glob("*.woff2")), "the real web/mary/fonts folder must hold the fonts")
        for name in ("cedarville.woff2", "kalam.woff2", "garamond.woff2", "cinzel.woff2"):
            self.assertGreater((FONTS / name).stat().st_size, 1000, name)
        known = self.before()
        self.card()
        card_id = self.draft()["id"]
        made = {p for p in self.before() - known}
        for p in made:
            self.assertTrue(p == self.dir / "skills.log" or p == self.dir / "skills.db" or
                            p.is_relative_to(self.folder), "wrote outside the skill folder: %s" % p)
        pics = self.pictures()
        for part, svg in pics.items():
            self.assertTrue((self.folder / ("card-%s-%s.svg" % (card_id, part))).is_file(), part)
            root = ET.fromstring(svg)
            self.assertEqual(root.tag, SVG + "svg", part)
            if part != "left":
                self.assertIn("data:font/woff2;base64,", svg, part)
            self.assertNotRegex(svg, r"url\(\s*['\"]?https?:", part)
            for m in re.finditer(r"https?://[^\s\"'<>)]*", svg):
                self.assertTrue(m.group(0).startswith("http://www.w3.org/"), "%s: %s" % (part, m.group(0)))
            tags = {e.tag.replace(SVG, "") for e in root.iter()}
            self.assertFalse(tags & {"script", "foreignObject"}, part)
            for e in root.iter(SVG + "image"):
                href = e.get("href") or e.get("{http://www.w3.org/1999/xlink}href") or ""
                self.assertTrue(href.startswith("data:"), "%s: image with %s" % (part, href[:40]))
        self.assertEqual(ET.fromstring(pics["print"]).get("viewBox"), "0 0 612 792")

    def test_embedded_fonts_are_real(self):
        self.card()
        for part, svg in self.pictures().items():
            for m in re.finditer(r"data:font/woff2;base64,([A-Za-z0-9+/=]+)", svg):
                data = base64.b64decode(m.group(1))
                self.assertEqual(data[:4], b"wOF2", part)
                self.assertGreater(len(data), 1000, part)

    def test_plain_hand_embeds_kalam(self):
        self.card()
        self.act("set_hand", hand="plain")
        self.assertIn("kalam", {w for w in re.findall(r"font-family:\s*'?([A-Za-z]+)", self.pictures()["inside"].lower())}
                      | {"kalam"} if "Kalam" in self.pictures()["inside"] else set())

    def test_letter_and_keepsake_pictures_are_self_contained(self):
        self.act("plain_message", person="Ann", words="Thinking of you.", signature="Bo")
        self.act("show_keepsake", name="Mark", month="December", day=25)
        for p in self.folder.glob("*.svg"):
            if p.name.startswith(("letter-", "keepsake-")):
                svg = p.read_text(encoding="utf-8")
                root = ET.fromstring(svg)
                self.assertFalse({e.tag.replace(SVG, "") for e in root.iter()} & {"script", "foreignObject"}, p.name)
                self.assertNotRegex(svg, r"https?://(?!www\.w3\.org)", p.name)  # a letter's Segoe is the system's own


class FitTests(Base):
    """Section 3: words fit, shrink, spill or are refused, and are never cut."""

    def draw(self, words, signature="Dad", verse=None, hand="cursive"):
        verse = self.mod.VERSES["birthday"][1]["lines"] if verse is None else verse
        return self.mod.draw_inside(self.ctx, verse, words, signature, hand)

    def drawn(self, out):
        return [t for _, t in self.lines_of(out["svg"])]

    def test_short_words_full_size(self):
        out = self.draw("Happy birthday.")
        self.assertTrue(out["fits"])
        self.assertEqual(out["size"], round(self.mod.HANDS["cursive"]["size"], 2))
        self.assertFalse(out["verse_left_out"])

    def test_300_characters_smaller_and_whole(self):
        words = (PLAIN_ENGLISH * 3)[:300].rsplit(" ", 1)[0]
        out = self.draw(words)
        self.assertTrue(out["fits"])
        self.assertLess(out["size"], self.draw("Hi")["size"])
        self.assertGreaterEqual(out["size"], self.mod.WORDS_FLOOR)
        self.assertEqual(" ".join(" ".join(self.drawn(out)).split()).count(words.split()[-1]) >= 1, True)

    def test_450_characters_leaves_the_verse_out(self):
        words = (PLAIN_ENGLISH * 5)[:450].rsplit(" ", 1)[0]
        out = self.draw(words)
        self.assertTrue(out["fits"])
        self.assertTrue(out["verse_left_out"])
        for w in words.split():
            self.assertIn(w, " ".join(self.drawn(out)))

    def test_40_letter_word_is_kept_whole(self):
        word = "WMWMWMWMWMWMWMWMWMWMWMWMWMWMWMWMWMWMWMWM"
        for hand in ("cursive", "plain"):
            out = self.draw("Dear " + word + " love", signature="Dad", verse=[], hand=hand)
            self.assertTrue(out["fits"], hand)
            lines = [t for t in self.drawn(out) if t.strip()]
            self.assertIn(word, "".join(lines).replace("-", "").replace(" ", ""), hand)
            self.assertGreater(len([t for t in lines if "W" in t or "M" in t]), 1, hand)  # broken across lines

    def test_far_too_long_is_refused_and_changes_nothing(self):
        self.card(words="Short and sweet.", signature="Dad")
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        draft = json.dumps(self.draft(), sort_keys=True)
        too_long = ("wonderful " * 120)[:1190]
        r = self.act("set_words", words=too_long)
        self.assertTrue(r["too_long"])
        self.assertFalse(r["saved"])
        self.assertEqual(self.last["say"], self.mod.SAY_TOO_LONG)
        self.assertEqual(json.dumps(self.draft(), sort_keys=True), draft)
        self.assertEqual({p.name: p.read_bytes() for p in self.folder.iterdir()}, before)
        self.assertEqual(self.act("read_back")["words"], "Short and sweet.")
        over = self.host.call("messages__set_words", {"words": "x " * 700})  # past the 1200 limit: the host refuses
        self.assertEqual(over["response"]["error"], "bad_input")
        self.assertEqual(self.draft()["words"], "Short and sweet.")
        self.assertEqual({p.name: p.read_bytes() for p in self.folder.iterdir()}, before)

    def test_every_line_stays_on_the_page(self):
        samples = ["Happy birthday.", (PLAIN_ENGLISH * 3)[:300], "WMWMWMWMWMWMWMWMWMWMWMWMWMWMWMWMWMWMWMWM"]
        for hand, font in (("cursive", "cedarville"), ("plain", "kalam")):
            for words in samples:
                out = self.draw(words, hand=hand)
                self.assertTrue(out["fits"], (hand, words[:20]))
                root = ET.fromstring(out["svg"])
                self.assertEqual(root.get("viewBox"), "0 0 500 700")
                for e, text in self.lines_of(out["svg"]):
                    if not text.strip() or "serif" in (e.get("font-family") or "").lower() and font not in (e.get("font-family") or "").lower():
                        continue
                    if font not in (e.get("font-family") or "").lower():
                        continue
                    size = float(e.get("font-size"))
                    self.assertLess(self.mod.width(self.ctx, font, text, size), 500, (hand, text))

    def test_letters_and_quotes_come_through(self):
        out = self.draw("Café for Łukasz \u201cmy friend\u201d and \u2018his\u2019 wife", verse=[])
        text = " ".join(self.drawn(out))
        for ch in "éŁ\u201c\u201d\u2018\u2019":
            self.assertIn(ch, text)

    def test_markup_in_words_is_escaped(self):
        self.card(words="<script>alert(1)</script> Tom & Jerry", signature="<b>Dad</b>")
        for part, svg in self.pictures().items():
            root = ET.fromstring(svg)
            self.assertFalse([e for e in root.iter() if e.tag.endswith("script")], part)
        self.assertIn("Tom & Jerry", " ".join(t for _, t in self.lines_of(self.pictures()["inside"])))
        self.assertNotIn("<script", self.pictures()["inside"])

    def test_front_line_fits_or_takes_two_lines(self):
        long_line = "for my dearest son, the best fisherman I know anywhere"
        for entry in FRONTS:
            spec = entry["line"]
            if not spec:
                continue
            lines, size = self.mod._fit_front_line(self.ctx, spec, long_line)
            self.assertEqual(" ".join(lines).replace("- ", ""), long_line, entry["key"])
            font = self.mod._front_font(spec)
            for line in lines:
                self.assertLessEqual(self.mod.width(self.ctx, font, line, size, spec.get("spacing", 0) / spec["size"] * size),
                                     spec["width"] * 1.02, (entry["key"], line))
            svg = self.mod.draw_front(self.ctx, entry["key"], long_line)
            ET.fromstring(svg)
            for line in lines:
                self.assertIn(line.replace("&", "&amp;"), svg, entry["key"])


class FrontTests(Base):
    """Section 4: the twelve fronts and the verses."""

    def test_all_twelve_draw(self):
        self.assertEqual(len(FRONTS), 12)
        for entry in FRONTS:
            svg = self.mod.draw_front(self.ctx, entry["key"], "for my son")
            self.assertEqual(ET.fromstring(svg).tag, SVG + "svg", entry["key"])

    def test_every_occasion_has_fronts_listed_with_number_and_name(self):
        occasions = set(MANIFEST["actions"][0]["inputSchema"]["properties"]["occasion"]["enum"])
        self.assertEqual({o for e in FRONTS for o in e["occasions"]}, occasions)
        for occasion in sorted(occasions):
            shown = self.act("show_fronts", person="Ann", occasion=occasion)["fronts"]
            self.assertTrue(shown, occasion)
            for i, f in enumerate(shown, 1):
                self.assertEqual(f["number"], i)
                self.assertTrue(f["name"])
            for key in self.draft()["shown"]:
                self.assertIn(occasion, next(e for e in FRONTS if e["key"] == key)["occasions"])

    def test_sympathy_uses_no_birthday_verse(self):
        self.card(front="1", words="I am so sorry for your loss.", signature="Ann", occasion="sympathy", likes="")
        birthday = [v["lines"] for v in self.mod.VERSES["birthday"]]
        self.assertNotIn(self.draft()["verse"], birthday)
        inside = self.pictures()["inside"]
        for lines in birthday:
            self.assertNotIn(lines[0], inside)

    def test_a_woman_never_gets_a_man_verse(self):
        man_verses = [v["lines"] for verses in self.mod.VERSES.values() for v in verses if "man" in v["assumes"]]
        self.assertTrue(man_verses)
        for occasion in self.mod.VERSES:
            for likes in ("", "fishing lake boat", "church faith"):
                self.act("show_fronts", person="Ann", occasion=occasion, likes=likes, person_is="woman")
                for key in self.draft()["shown"]:
                    draft = dict(self.draft(), front=key)
                    for verse in self.mod._verses(self.ctx, draft):
                        self.assertNotIn(verse, man_verses, (occasion, likes, key))


class SendTests(Base):
    """Section 5: "send it" never sends, never touches the card, and offers to print."""

    def test_manifest_asks_for_no_mail(self):
        self.assertNotIn("send_mail", json.dumps(MANIFEST))
        self.assertEqual(MANIFEST["needs"]["internet_hosts"], [])
        self.assertNotIn("send_mail(", (SKILLS / "messages" / "skill.py").read_text(encoding="utf-8"))

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.folder.glob("*")} if self.folder.exists() else {}

    def test_send_a_card(self):
        self.card()
        before = self.snapshot()
        r = self.act("send_it")
        self.assertEqual((r["sent"], r["saved"], r["can_print"]), (False, True, True))
        self.assertIn("isn't set up", self.last["say"])
        self.assertIn("print", self.last["say"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.mail_calls, [])

    def test_send_a_plain_message(self):
        self.act("plain_message", person="Ann", words="Thinking of you.", signature="Bo")
        before = self.snapshot()
        r = self.act("send_it")
        self.assertEqual((r["sent"], r["saved"], r["can_print"]), (False, True, True))
        self.assertIn("isn't set up", self.last["say"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.mail_calls, [])

    def test_send_with_nothing_made(self):
        r = self.act("send_it")
        self.assertEqual((r["sent"], r["saved"]), (False, False))


class LetterTests(Base):
    """Section 6: a plain message is a letter, not a card."""

    def test_plain_message_saves_a_letter_only(self):
        r = self.act("plain_message", person="Ann", words="Thinking of you.", signature="Bo")
        self.assertTrue(r["saved"])
        d = self.draft()
        self.assertEqual(d["kind"], "letter")
        self.assertTrue((self.folder / ("letter-%s.svg" % d["id"])).is_file())
        self.assertEqual(self.kinds().count("letter"), 1)
        self.assertNotIn("fronts", self.kinds())
        self.assertFalse(list(self.folder.glob("card-*")))
        self.assertIsNone(self.act("pick_front", choice="1")["picked"])  # no card, so nothing to pick
        self.assertEqual(self.act("print_card")["printing"], True)
        self.assertEqual([e["data"]["file"] for e in self.last["effects"] if e["kind"] == "print"], ["letter-%s.svg" % d["id"]])

    def test_a_change_replaces_it(self):
        self.act("plain_message", person="Ann", words="Thinking of you.", signature="Bo")
        first = self.draft()["id"]
        self.act("plain_message", person="Ann", words="Missing you instead.")
        self.assertEqual(self.draft()["id"], first)
        files = list(self.folder.glob("letter-*.svg"))
        self.assertEqual(len(files), 1)
        svg = files[0].read_text(encoding="utf-8")
        self.assertIn("Missing you instead.", " ".join(t for _, t in self.lines_of(svg)))
        self.assertNotIn("Thinking of you.", svg)

    def test_a_signature_is_asked_for(self):
        r = self.act("plain_message", person="Ann", words="Hello there")
        self.assertEqual((r["saved"], r.get("need")), (False, "signature"))
        self.assertFalse(list(self.folder.glob("letter-*"))) if self.folder.exists() else None


class KeepsakeTests(Base):
    """Section 7: the keepsake page for someone's date."""

    def test_keepsake_page(self):
        today = datetime.date.today()
        date = datetime.date(today.year, 12, 25)
        if date < today:
            date = datetime.date(today.year + 1, 12, 25)
        r = self.act("show_keepsake", name="Mark", month="December", day=25, age_line="Fifty-two this year",
                     memory_line="Loves the lake.", who="mary")
        self.assertEqual(r["weekday"], date.strftime("%A"))
        self.assertTrue(r["shown"])
        files = list(self.folder.glob("keepsake-*.svg"))
        self.assertEqual(len(files), 1)
        svg = files[0].read_text(encoding="utf-8")
        text = " ".join(t for _, t in self.lines_of(svg)).lower()
        self.assertIn("mark", text)
        self.assertIn(date.strftime("%A").lower(), text)
        self.assertIn("25", text)
        self.assertRegex(text, r"\bm\b")  # the initial, set in its own frame
        for wording in ("his photo", "her photo", "your photo"):
            self.assertNotIn(wording, svg.lower())
        self.assertIn("keepsake", self.kinds())

    def test_sam_looks_different(self):
        self.act("show_keepsake", name="Mark", month="December", day=25, who="mary")
        mary_svg = next(self.folder.glob("keepsake-*.svg")).read_text(encoding="utf-8")
        self.act("show_keepsake", name="Mark", month="December", day=25, who="sam")
        sam_svg = next(self.folder.glob("keepsake-*.svg")).read_text(encoding="utf-8")
        self.assertNotEqual(sam_svg, mary_svg)
        ET.fromstring(sam_svg)
        self.settings["companion"] = "him"  # with who left out, Sam's setting picks Sam's look
        self.act("show_keepsake", name="Mark", month="December", day=25)
        self.assertEqual(next(self.folder.glob("keepsake-*.svg")).read_text(encoding="utf-8"), sam_svg)

    def test_bad_date(self):
        self.assertFalse(self.act("show_keepsake", name="Mark", month="Smarch", day=3)["shown"])
        self.assertFalse(self.act("show_keepsake", name="Mark", month="February", day=31)["shown"])

    def test_print_a_keepsake(self):
        self.act("show_keepsake", name="Mark", month="December", day=25)
        self.act("print_card")
        self.assertEqual([e["data"]["file"] for e in self.last["effects"] if e["kind"] == "print"],
                         [next(self.folder.glob("keepsake-*.svg")).name])


class ReminderTests(Base):
    """Section 8: Mary offers a card only when the skill is on."""

    def test_can_make_cards_follows_the_switch(self):
        self.assertTrue(mary.can_make_cards(self.host))
        self.host.set_skill("messages", False)
        self.assertFalse(mary.can_make_cards(self.host))
        self.host.set_skill("messages", True)
        self.assertTrue(mary.can_make_cards(self.host))

    def test_host_without_the_skill(self):
        empty = skills_core.SkillHost(self.dir / "nothing", self.dir, lambda: sqlite3.connect(self.dir / "x.db"), dict,
                                      lambda v: None)
        empty.load()
        self.assertFalse(mary.can_make_cards(empty))
        self.assertFalse(mary.can_make_cards(None))

    def test_note_mentions_a_card_only_when_asked(self):
        helpers.reset_db()
        memory = server.mary_memory()
        memory.name, memory.recent = "", []
        with unittest_env("TRACKER_TODAY", "2026-01-01"):
            mary.learn_dates(memory, "My son's birthday is November 7")
        with unittest_env("TRACKER_TODAY", "2026-10-31"):
            with_cards = mary.reminder_note(memory, cards=mary.can_make_cards(self.host))
            self.host.set_skill("messages", False)
            without = mary.reminder_note(memory, cards=mary.can_make_cards(self.host))
        self.assertIn("make a card", with_cards)
        self.assertIn("show_keepsake", with_cards)
        self.assertTrue(without)
        self.assertNotIn("card", without.lower())


class unittest_env:
    """Sets one environment variable for a with-block."""

    def __init__(self, name, value):
        self.name, self.value = name, value

    def __enter__(self):
        self.old = os.environ.get(self.name)
        os.environ[self.name] = self.value

    def __exit__(self, *exc):
        if self.old is None:
            os.environ.pop(self.name, None)
        else:
            os.environ[self.name] = self.old


class RestartTests(Base):
    """Section 9: a restart keeps the draft and the saved card."""

    def test_draft_and_saved_card_survive(self):
        self.card(words="Many happy returns.", signature="Dad")
        card_id = self.draft()["id"]
        files = sorted(p.name for p in self.folder.iterdir())
        self.host = self.new_host()  # fresh host and fresh skill memory, same data folder
        self.assertEqual(self.draft()["id"], card_id)
        self.assertEqual(self.act("read_back")["words"], "Many happy returns.")
        r = self.act("open_saved", person="mark")
        self.assertTrue(r["found"])
        self.assertEqual(r["kind"], "card")
        self.assertIn("Many happy returns.", r["read_back"])
        self.assertIn("card", self.kinds())
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), files)

    def test_open_after_restart_shows_the_draft(self):
        self.card()
        self.host = self.new_host()
        self.event(type="open")
        self.assertIn("card", [e["kind"] for e in self.host.on_event("messages", {"type": "open"})["effects"]])

    def test_nothing_saved(self):
        r = self.act("open_saved")
        self.assertFalse(r["found"])
        r = self.act("open_saved", person="nobody")
        self.assertFalse(r["found"])


class PictureEventTests(Base):
    """Section 10: pieces of a jpeg of the saved card, glued back together."""

    def piece(self, chunk, seq, last, **over):
        d = self.draft()
        event = {"type": "picture", "id": d["id"], "part": "both", "rev": d["rev"], "seq": seq,
                 "data": base64.b64encode(chunk).decode(), "last": last}
        event.update(over)
        return self.event(**event)["response"]

    def jpgs(self):
        return list(self.folder.glob("*.jpg"))

    def test_pieces_reassemble(self):
        self.card()
        cut = [JPEG[:300], JPEG[300:600], JPEG[600:]]
        for i, chunk in enumerate(cut):
            r = self.piece(chunk, i, i == len(cut) - 1)
        self.assertTrue(r.get("saved"))
        self.assertEqual((self.folder / ("card-%s-both.jpg" % self.draft()["id"])).read_bytes(), JPEG)

    def test_refusals_write_nothing(self):
        self.card()
        self.assertTrue(self.piece(b"not a jpeg at all", 0, True).get("stale"))
        self.assertEqual(self.jpgs(), [])
        self.assertTrue(self.piece(JPEG, 1, True).get("stale"))  # a piece out of order, no job begun
        self.assertTrue(self.piece(JPEG, 0, True, rev=self.draft()["rev"] + 5).get("stale"))  # a stale rev
        self.assertEqual(self.jpgs(), [])
        self.assertTrue(self.piece(JPEG, 0, True, id="somebody-else").get("stale"))
        self.assertTrue(self.piece(JPEG, 0, True, part="left").get("stale"))
        self.assertEqual(self.jpgs(), [])
        self.assertTrue(self.piece(b"x", 0, False, data="@@@").get("stale"))
        self.assertEqual(self.jpgs(), [])

    def test_oversized_total_is_refused(self):
        self.card()
        chunk = JPEG[:3] + b"\x00" * (self.mod.PICTURE_MAX // 2)
        self.assertNotIn("stale", self.piece(chunk, 0, False))
        self.assertNotIn("stale", self.piece(b"\x00" * (self.mod.PICTURE_MAX // 2), 1, False))
        self.assertTrue(self.piece(b"\x00" * 10, 2, True).get("stale"))
        self.assertEqual(self.jpgs(), [])

    def test_new_words_drop_old_pictures(self):
        self.card()
        self.piece(JPEG, 0, True)
        self.assertEqual(len(self.jpgs()), 1)
        self.act("set_words", words="Something new.")
        self.assertEqual(self.jpgs(), [])


@unittest.skipUnless(find_node(), "Node not found: the screen checks were skipped")
class ScreenTests(unittest.TestCase):
    """Section 11: the screen's script parses and its words and sizes follow the resident rules."""

    SCREEN = SKILLS / "messages"

    def test_screen_js_parses(self):
        done = subprocess.run([find_node(), "--check", str(self.SCREEN / "screen.js")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[:500])

    def test_css_text_and_targets(self):
        css = (self.SCREEN / "screen.css").read_text(encoding="utf-8")
        sizes = [float(n) for decl in re.findall(r"font(?:-size)?:[^;}]*", css) for n in re.findall(r"(\d+(?:\.\d+)?)px", decl)]
        self.assertTrue(sizes)
        self.assertGreaterEqual(min(sizes), 20, sizes)
        heights = [float(n) for n in re.findall(r"min-height:\s*(\d+(?:\.\d+)?)px", css)]
        self.assertTrue(heights)
        self.assertGreaterEqual(min(heights), 64, heights)
        for n in re.findall(r"(?<![\w-])height:\s*(\d+(?:\.\d+)?)px", css):
            self.assertGreaterEqual(float(n), 64, "a fixed height under 64px")

    def test_no_back_next_or_made_to_order(self):
        js = (self.SCREEN / "screen.js").read_text(encoding="utf-8")
        for bad in ("'Back'", '"Back"', "'Next'", '"Next"', "made to order", "Made to order"):
            self.assertNotIn(bad, js)
        self.assertNotIn("made to order", (self.SCREEN / "screen.css").read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
