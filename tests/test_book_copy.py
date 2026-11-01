from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M19 piece 7, a helper's copy: the file, the six words, the merge, a locked book, the routes and the word list."""
import base64
import hashlib
import json
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import address_book
import secret_store
import server

api = helpers.api
ROOT = Path(__file__).resolve().parent.parent
REFUSED = "That file and those words don't fit together."
SARAH = {"name": "Sarah Whitfield", "relationship": "daughter", "email": "sarah@example.com", "cell": "919-555-0142",
         "birthday": "03-14", "notes": "Works nights.", "address": "12 Oak Lane\nRaleigh"}


def new_book(folder=None):
    folder = folder or tempfile.mkdtemp(dir=helpers.TMP)
    return address_book.AddressBook(folder, secret_store.SecretStore(folder))


def refusal(data, words):
    try:
        address_book.read_copy(data, words)
    except address_book.CopyRefused as e:
        return str(e)
    raise AssertionError("it opened")


class CopyFileTests(unittest.TestCase):
    def setUp(self):
        self.book = new_book()
        self.book.add(SARAH)
        self.book.add({"name": "Dr. Lee", "kind": "doctor", "phone": "919-555-0100"})
        self.book.add({"name": "Mark", "hidden": True, "no_keep": True})
        self.words, self.data = self.book.make_copy()

    def test_six_words_from_the_list_and_a_different_set_each_time(self):
        self.assertEqual(len(self.words), 6)
        self.assertTrue(set(self.words) <= set(address_book.word_list()))
        self.assertNotEqual(self.book.make_copy()[0], self.words)

    def test_round_trip_into_a_fresh_folder_with_its_own_key(self):
        records = address_book.read_copy(self.data, " ".join(self.words))
        other = new_book()
        counts = other.bring_in(records)
        self.assertEqual(counts, {"added": 2, "filled": 0, "full": False})
        self.assertNotEqual(self.book._stored_key(), other._stored_key())
        self.assertEqual(other.find("Sarah Whitfield")[0]["address"], "12 Oak Lane\nRaleigh")
        self.assertEqual(other.find("Dr. Lee")[0]["kind"], "doctor")
        mark = other.find("Mark", include_hidden=True)[0]
        self.assertTrue(mark["hidden"] and mark["no_keep"])
        self.assertEqual(other.count(), 2)

    def test_the_file_never_holds_a_key_or_a_row_id(self):
        plain = json.dumps(address_book.read_copy(self.data, self.words))
        self.assertNotIn(self.book.people()[0]["id"], plain)
        self.assertFalse(self.book._stored_key() in self.data)

    def test_every_bad_try_gets_the_same_words(self):
        good = list(self.words)
        wrong = [w for w in address_book.word_list() if w not in good][:6]
        one_wrong = good[:5] + wrong[:1]
        flipped = bytearray(self.data)
        flipped[-1] ^= 1
        head = bytearray(self.data)
        head[self.data.index(b'"salt"') + 9] ^= 1
        cases = [(self.data, wrong), (self.data, one_wrong), (self.data, good[::-1]), (bytes(flipped), good),
                 (bytes(head), good), (b"", good), (self.data[:-20], good), (self.data, ""), (self.data, None),
                 ("not bytes", good)]
        for data, words in cases:
            self.assertEqual(refusal(data, words), REFUSED)

    def test_the_raw_bytes_hold_nothing_readable(self):
        for part in (b"Sarah", b"Whitfield", b"sarah@example.com", b"555", b"Oak Lane", b"Lee", b"Mark", b"daughter"):
            self.assertNotIn(part, self.data)
        head = json.loads(self.data.split(b"\n", 1)[0])
        self.assertEqual(set(head), {"magic", "version", "salt", "n", "r", "p", "nonce"})
        self.assertEqual((head["magic"], head["version"]), ("CareBook", 1))

    def tampered(self, **changes):
        head, sealed = self.data.split(b"\n", 1)
        return json.dumps({**json.loads(head), **changes}).encode("utf-8") + b"\n" + sealed

    def test_a_bad_header_stops_before_scrypt(self):
        bad = [{"magic": "CareBooK"}, {"version": 2}, {"version": True}, {"n": 2 ** 30}, {"n": 2 ** 15}, {"r": 64},
               {"p": 16}, {"p": True}, {"n": 65536.0}, {"salt": "AAAA"}, {"salt": "!!"}, {"nonce": "AAAA"}, {"extra": 1}]
        with mock.patch.object(hashlib, "scrypt", side_effect=AssertionError("scrypt ran")) as scrypt:
            for changes in bad:
                self.assertEqual(refusal(self.tampered(**changes), self.words), REFUSED)
            self.assertEqual(refusal(b"x" * 600 + b"\n" + b"y", self.words), REFUSED)  # no end to the header
            self.assertEqual(refusal(b"[1,2]\nabc", self.words), REFUSED)
            scrypt.assert_not_called()

    def test_a_file_too_big_stops_before_anything(self):
        with mock.patch.object(hashlib, "scrypt", side_effect=AssertionError("scrypt ran")) as scrypt:
            self.assertEqual(refusal(self.data + b"x" * (5 * 1024 * 1024), self.words), REFUSED)
            scrypt.assert_not_called()

    def test_a_copy_too_big_to_read_back_is_never_made(self):
        with mock.patch.object(address_book, "MAX_COPY", 100):
            with self.assertRaises(address_book.BookError):
                self.book.make_copy()

    def test_odd_spaces_and_capitals_still_work(self):
        typed = "  " + "\t  ".join(w.upper() for w in self.words) + "\n"
        self.assertEqual(len(address_book.read_copy(self.data, typed)), 3)
        self.assertEqual(address_book.normalize_words(typed), " ".join(self.words))

    def test_a_word_off_the_list_or_a_short_count_stops_before_scrypt(self):
        with mock.patch.object(hashlib, "scrypt", side_effect=AssertionError("scrypt ran")) as scrypt:
            self.assertEqual(refusal(self.data, self.words[:5] + ["xyzzyq"]), REFUSED)
            self.assertEqual(refusal(self.data, self.words[:5]), REFUSED)
            self.assertEqual(refusal(self.data, self.words + self.words[:1]), REFUSED)
            scrypt.assert_not_called()

    def test_scrypt_settings(self):
        self.assertEqual((address_book.SCRYPT_N, address_book.SCRYPT_R, address_book.SCRYPT_P), (2 ** 16, 8, 1))


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.book = new_book()

    def bring(self, *records):
        return self.book.bring_in(records)

    def test_a_new_name_adds(self):
        self.assertEqual(self.bring(SARAH), {"added": 1, "filled": 0, "full": False})

    def test_fills_blanks_and_never_overwrites(self):
        self.book.add({"name": "My Sarah Whitfield", "cell": "000", "email": ""})
        self.assertEqual(self.bring(SARAH), {"added": 0, "filled": 1, "full": False})
        person = self.book.people()[0]
        self.assertEqual((person["name"], person["cell"], person["email"]), ("My Sarah Whitfield", "000", SARAH["email"]))

    def test_the_same_copy_twice_changes_nothing(self):
        self.bring(SARAH)
        self.assertEqual(self.bring(SARAH), {"added": 0, "filled": 0, "full": False})
        self.assertEqual(self.book.count(), 1)

    def test_names_match_without_case_or_a_leading_my_or_our(self):
        self.book.add({"name": "OUR STRASSE", "cell": "1"})
        self.assertEqual(self.bring({"name": "my straße", "phone": "2"}), {"added": 0, "filled": 1, "full": False})

    def test_a_no_keep_mark_holds(self):
        self.book.add({"name": "Mark", "hidden": True, "no_keep": True})
        self.bring({"name": "Mark", "email": "mark@example.com"})
        mark = self.book.find("Mark", include_hidden=True)[0]
        self.assertEqual(mark["email"], "")
        self.assertTrue(mark["hidden"] and mark["no_keep"])

    def test_a_no_keep_on_someone_shown_keeps_the_email_out_and_the_rest_fills(self):
        self.book.add({"name": "Mark", "no_keep": True, "cell": "1"})
        self.assertEqual(self.bring({"name": "Mark", "email": "mark@example.com", "phone": "2"})["filled"], 1)
        mark = self.book.people()[0]
        self.assertEqual((mark["email"], mark["phone"]), ("", "2"))

    def test_a_mark_in_the_copy_comes_across_and_hides_no_one(self):
        self.book.add({"name": "Mark", "cell": "1"})
        self.assertEqual(self.bring({"name": "Mark", "hidden": True, "no_keep": True}), {"added": 0, "filled": 0, "full": False})
        mark = self.book.people()[0]
        self.assertTrue(mark["no_keep"])
        self.assertFalse(mark["hidden"])

    def test_a_doctor_and_a_person_stay_apart(self):
        self.book.add({"name": "Pat Lee", "cell": "1"})
        self.assertEqual(self.bring({"name": "Pat Lee", "kind": "doctor", "phone": "2"})["added"], 1)
        self.assertEqual(sorted(p["kind"] for p in self.book.people()), ["doctor", "person"])

    def test_a_full_book_stops_with_what_got_in_counted(self):
        with mock.patch.object(address_book, "MAX_PEOPLE", 2):
            self.book.add({"name": "Ann"})
            counts = self.bring({"name": "Bob"}, {"name": "Cal"}, {"name": "Dee"})
        self.assertEqual(counts, {"added": 1, "filled": 0, "full": True})

    def test_birthdays_flow_through_on_change(self):
        seen = []
        self.book.on_change = lambda kind, row_id, record: seen.append((kind, record["birthday"]))
        self.book.add({"name": "Ann"})
        self.bring({"name": "Ann", "birthday": "05-01"}, SARAH)
        self.assertEqual(seen, [("add", ""), ("update", "05-01"), ("add", "03-14")])


class LockedBookTests(unittest.TestCase):
    def setUp(self):
        source = new_book()
        source.add(SARAH)
        self.words, self.data = source.make_copy()
        self.records = address_book.read_copy(self.data, self.words)
        self.book = new_book()
        self.book.add({"name": "Old Friend", "cell": "1"})
        self.book.backup(fresh=True)
        self.before = (self.book.path.read_bytes(), self.book.backup_path.read_bytes())
        self.old_key = self.book._secrets.get(address_book.KEY_NAME)
        self.book._secrets.delete(address_book.KEY_NAME)
        self.book.lock()
        self.today = time.strftime("%Y-%m-%d")

    def set_aside(self, stem="addressbook", more=""):
        return self.book.path.with_name(f"{stem}.locked-{self.today}{more}.db")

    def test_moves_aside_byte_identical_then_starts_fresh(self):
        self.assertEqual(self.book.why_locked(), "key")
        self.assertEqual(self.book.bring_in(self.records), {"added": 1, "filled": 0, "full": False})
        self.assertEqual(self.set_aside().read_bytes(), self.before[0])
        self.assertEqual(self.set_aside("addressbook_backup").read_bytes(), self.before[1])
        self.assertEqual(self.book.state(), "open")
        self.assertEqual([p["name"] for p in self.book.people()], [SARAH["name"]])
        self.assertNotEqual(self.book._secrets.get(address_book.KEY_NAME), self.old_key)
        self.book.lock()
        self.assertEqual(self.book.count(), 1)  # the new key really is the one kept

    def test_a_second_move_the_same_day_overwrites_nothing(self):
        self.book.bring_in(self.records)
        self.book._secrets.delete(address_book.KEY_NAME)
        self.book.lock()
        self.book.bring_in(self.records)
        self.assertEqual(self.set_aside().read_bytes(), self.before[0])
        self.assertTrue(self.set_aside(more="-2").exists())

    def test_a_key_that_does_not_fit_is_kept_not_written_over(self):
        wrong = base64.b64encode(b"k" * 32).decode("ascii")
        self.book._secrets.put(address_book.KEY_NAME, wrong)
        self.book.lock()
        self.assertEqual(self.book.why_locked(), "key")
        self.book.bring_in(self.records)
        self.assertNotEqual(self.book._secrets.get(address_book.KEY_NAME), wrong)
        kept = f"{address_book.KEY_NAME}_locked_{self.today.replace('-', '')}"
        self.assertEqual(self.book._secrets.get(kept), wrong)

    def test_a_failed_move_puts_everything_back(self):
        real, calls = address_book.os.rename, []

        def second_fails(src, dst):
            calls.append(src)
            if len(calls) == 2:
                raise OSError("held")
            real(src, dst)
        with mock.patch.object(address_book.os, "rename", second_fails):
            with self.assertRaises(address_book.BookLocked):
                self.book.bring_in(self.records)
        self.assertEqual(self.book.path.read_bytes(), self.before[0])
        self.assertEqual(self.book.why_locked(), "key")
        self.assertFalse(self.set_aside().exists())

    def test_an_empty_copy_moves_nothing(self):
        self.book.bring_in([])
        self.assertFalse(self.set_aside().exists())
        self.assertEqual(self.book.path.read_bytes(), self.before[0])

    def test_unavailable_and_file_refuse_and_move_nothing(self):
        for why in (address_book.WHY_UNAVAILABLE, address_book.WHY_FILE):
            with mock.patch.object(self.book, "_try_open", return_value=why):
                with self.assertRaises(address_book.BookLocked):
                    self.book.bring_in(self.records)
            self.assertEqual(self.book.path.read_bytes(), self.before[0])
            self.assertFalse(self.set_aside().exists())


class RouteTests(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        server.BOOK.clear()
        server.BOOK_COPIES.clear()

    def tearDown(self):
        server.BOOK_COPIES.clear()

    def make(self):
        status, body, _ = api("POST", "/api/book/copy", {})
        self.assertEqual(status, 200, body)
        return body

    def bring(self, data, words):
        return api("POST", "/api/book/bring-in", {"file": base64.b64encode(data).decode("ascii"), "words": words})

    def test_every_route_needs_the_host_and_a_post_needs_the_header(self):
        server.BOOK.add(SARAH)
        self.assertEqual(api("POST", "/api/book/copy", {}, tracker=False)[0], 403)
        self.assertEqual(api("POST", "/api/book/bring-in", {}, tracker=False)[0], 403)
        self.assertEqual(api("POST", "/api/book/copy", {}, host="evil.example")[0], 403)
        self.assertEqual(api("POST", "/api/book/bring-in", {}, host="evil.example")[0], 403)
        token = self.make()["token"]
        self.assertEqual(api("GET", f"/api/book/copy/{token}", host="evil.example")[0], 403)
        self.assertEqual(api("GET", f"/api/book/copy/{token}", tracker=False)[0], 200)

    def test_the_token_is_one_time_and_named_like_the_spreadsheet(self):
        server.BOOK.add(SARAH)
        made = self.make()
        self.assertEqual(len(made["words"]), 6)
        self.assertEqual(set(made), {"words", "token"})
        status, data, headers = api("GET", f"/api/book/copy/{made['token']}")
        self.assertEqual(status, 200)
        self.assertRegex(headers["Content-Disposition"], r'attachment; filename="MaryAddressBook-\d{4}-\d\d-\d\d\.carebook"')
        self.assertEqual(len(address_book.read_copy(data, made["words"])), 1)
        self.assertEqual(api("GET", f"/api/book/copy/{made['token']}")[0], 404)
        self.assertEqual(server.BOOK_COPIES, {})

    def test_a_token_lapses_after_ten_minutes(self):
        server.BOOK.add(SARAH)
        token = self.make()["token"]
        self.assertEqual(server.BOOK_COPY_S, 600)
        with mock.patch.object(server.time, "monotonic", return_value=time.monotonic() + 601):
            self.assertEqual(api("GET", f"/api/book/copy/{token}")[0], 404)
        self.assertEqual(server.BOOK_COPIES, {})

    def test_an_empty_book_makes_no_copy_and_a_locked_one_says_so(self):
        status, body, _ = api("POST", "/api/book/copy", {})
        self.assertEqual((status, body["code"]), (409, "empty"))
        with mock.patch.object(server.BOOK, "make_copy", side_effect=address_book.BookLocked()):
            server.BOOK.add(SARAH)
            status, body, _ = api("POST", "/api/book/copy", {})
        self.assertEqual((status, body["code"]), (409, "locked"))

    def test_bring_in_answers_counts_and_refuses_plainly(self):
        source = new_book()
        source.add(SARAH)
        words, data = source.make_copy()
        status, body, _ = self.bring(data, list(reversed(words)))
        self.assertEqual((status, body["error"]), (400, REFUSED))
        self.assertEqual(server.BOOK.count(), 0)
        status, body, _ = self.bring(data, " ".join(words))
        self.assertEqual((status, body), (200, {"added": 1, "filled": 0, "full": False}))
        self.assertEqual(server.BOOK.count(), 1)

    def test_a_bad_body_gets_the_same_refusal(self):
        for body in ({"file": "@@@", "words": "a b"}, {"file": 5, "words": 5}, {}):
            status, got, _ = api("POST", "/api/book/bring-in", body)
            self.assertEqual((status, got["error"]), (400, REFUSED))

    def test_a_file_at_the_limit_fits_through_the_door(self):
        data = b"x" * (5 * 1024 * 1024)
        status, body, _ = self.bring(data, "a b c d e f")
        self.assertEqual((status, body["error"]), (400, REFUSED))

    def test_unavailable_refuses_before_the_file_is_read(self):
        with mock.patch.object(server.BOOK, "why_locked", return_value="unavailable"), \
                mock.patch.object(address_book, "read_copy", side_effect=AssertionError("read")):
            status, body, _ = self.bring(b"x", "a b c d e f")
        self.assertEqual((status, body["code"]), (409, "cant"))
        self.assertEqual(body["error"], server.BOOK_COPY_CANT)

    def test_words_and_file_reach_no_file_on_disk(self):
        server.BOOK.add({"name": "Quentin Zanzibar", "email": "quentin@example.com"})
        made = self.make()
        words = " ".join(made["words"])
        data = api("GET", f"/api/book/copy/{made['token']}")[1]
        server.BOOK.clear()
        self.assertEqual(self.bring(data, words)[1]["added"], 1)
        wanted = (words.encode(), made["token"].encode(), base64.b64encode(data), data[:40])
        for path in helpers.TMP.rglob("*"):
            if path.is_file():
                raw = path.read_bytes()
                self.assertFalse(any(part in raw for part in wanted), path.name)
                self.assertFalse(path.suffix == ".log" and b"quentin" in raw.lower(), path.name)


class PageTests(unittest.TestCase):
    def test_her_screens_list_the_box_as_a_secret_and_never_the_words_shown(self):
        screens = (ROOT / "web" / "mary" / "screens.js").read_text(encoding="utf-8")
        entry = re.search(r"\{ id: 'copyWords'.*?\}", screens, re.S).group(0)
        self.assertIn("kind: 'secret'", entry)
        self.assertIn("fill: false", entry)
        self.assertNotIn("copyShown", screens)

    def test_my_info_holds_the_two_buttons_and_the_plain_lines(self):
        page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        card = re.search(r'<div class="card infocard skillscard" id="copyCard">.*?<!-- end copyCard -->', page, re.S).group(0)
        for line in ("Make a helper's copy", "Bring in a helper's copy", "Save the file", "Bring it in",
                     "Write these six words on paper and keep them with family. Anyone with the file and the words can read this book.",
                     "Forget can't reach a copy on a stick, so throw old copies away."):
            self.assertIn(line, card)
        self.assertNotIn('id="copyWords" type="password"', card)
        self.assertLess(page.index('id="infoForm"'), page.index('id="copyCard"'))
        self.assertLess(page.index("</form>", page.index('id="infoForm"')), page.index('id="copyCard"'))

    def test_book_js_never_tells_mary_anything_about_a_copy(self):
        script = (ROOT / "web" / "book.js").read_text(encoding="utf-8")
        part = script[script.index("/* ---------- A helper's copy"):script.index("/* ---------- What the rest")]
        self.assertNotIn("toMary", part)
        self.assertNotIn("localStorage", part)


class WordListTests(unittest.TestCase):
    def setUp(self):
        self.lines = (ROOT / "book_words.txt").read_text(encoding="ascii").split()

    def test_big_unique_and_the_right_shape(self):
        self.assertGreaterEqual(len(self.lines), 2048)
        self.assertEqual(len(self.lines), len(set(self.lines)))
        for word in self.lines:
            self.assertRegex(word, r"^[a-z]{3,7}$")

    def test_nothing_rude_or_sad(self):
        bad = set("""ass bitch blood bomb bury cancer casket cough coffin crap cripple cry damn dead death die disease
            dumb fag fat fever fool funeral gimp grave grief gun hate hell hurt idiot ill insane jerk kill lame loser moron
            murder nude pain pee penis piss poop rape retard sad scum sex shit sick slave slut stupid suicide tumor ugly
            war whore wound""".split())
        self.assertEqual(sorted(bad & set(self.lines)), [])

    def test_the_usual_sound_alikes_keep_only_one(self):
        pairs = """sea see|two too|four for|one won|eight ate|pear pair|bear bare|deer dear|sun son|blue blew|red read|
            road rode|sail sale|tail tale|wood would|night knight|peace piece|plain plane|steel steal|stair stare|
            week weak|whole hole|wine whine|ant aunt|beach beech|bee be|beet beat|berry bury|board bored|bread bred|
            flower flour|meet meat|hair hare|horse hoarse|hour our|peak peek|pole poll|rose rows|steak stake|tea tee|
            time thyme|toe tow|way weigh|mail male|maze maize|sight site|side sighed|wrap rap|right write""".replace("\n", " ")
        words = set(self.lines)
        for pair in pairs.split("|"):
            self.assertLess(len(set(pair.split()) & words), 2, pair)

    def test_the_build_bundles_it(self):
        self.assertIn("book_words.txt", (ROOT / "packaging" / "build.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
