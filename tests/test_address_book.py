"""The address book (M19): sealed on disk, locked rather than wiped, never plain."""
from tests import helpers

import base64
import importlib.util
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import address_book
import secret_store
from address_book import AddressBook, BookFull, BookLocked

SARAH = {"name": "Sarah Jenkins", "relationship": "daughter", "email": "sarah.j@example.org", "phone": "919-555-0142",
         "notes": "Plays the dulcimer on Sundays"}
PRIVATE = ["Sarah", "Jenkins", "daughter", "sarah.j@example.org", "example.org", "919-555-0142", "dulcimer"]


def raw_forms(word):
    return [word.encode("utf-8"), word.encode("utf-16-le"), word.encode("utf-16-be"),
            word.lower().encode("utf-8"), word.upper().encode("utf-8")]


class Base(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=helpers.TMP))
        self.secrets = secret_store.SecretStore(self.folder)
        self.book = AddressBook(self.folder, self.secrets)

    def key(self):
        try:
            return self.secrets.get(address_book.KEY_NAME)
        except secret_store.NotAvailable:
            return None

    def reopened(self):
        return AddressBook(self.folder, self.secrets)

    def rows(self):
        with closing(sqlite3.connect(self.book.path)) as conn:
            return conn.execute("SELECT id, nonce, sealed FROM people").fetchall()

    def poke(self, sql, *args):
        with closing(sqlite3.connect(self.book.path)) as conn, conn:
            conn.execute(sql, args)

    def assert_locked(self, book, why):
        before = self.book.path.read_bytes() if self.book.path.exists() else None
        key = self.key()
        self.assertEqual(book.state(), "locked")
        self.assertEqual(book.why_locked(), why)
        some_id = "0" * 32
        for call in (book.people, book.count, book.damaged, book.clear, lambda: book.find("Sarah"),
                     lambda: book.get(some_id), lambda: book.add({"name": "Nora"}),
                     lambda: book.update(some_id, {"name": "Nora"}), lambda: book.remove(some_id)):
            with self.assertRaises(BookLocked):
                call()
        self.assertEqual(self.key(), key)
        self.assertEqual(self.book.path.read_bytes() if self.book.path.exists() else None, before)


class Sealed(Base):
    def test_nothing_readable_in_either_file(self):
        self.book.add(SARAH)
        self.book.backup(fresh=True)
        self.assertTrue(self.book.backup_path.exists())
        for path in self.book.path.parent.iterdir():
            data = path.read_bytes()
            for word in PRIVATE:
                for form in raw_forms(word):
                    self.assertNotIn(form, data, f"{word} in {path.name}")

    def test_only_the_columns_the_design_allows(self):
        self.book.add(SARAH)
        with closing(sqlite3.connect(self.book.path)) as conn:
            self.assertEqual([c[1] for c in conn.execute("PRAGMA table_info(people)")], ["id", "nonce", "sealed"])
            self.assertEqual([c[1] for c in conn.execute("PRAGMA table_info(meta)")], ["key", "nonce", "sealed"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        with closing(self.book._connect()) as conn:
            self.assertEqual(conn.execute("PRAGMA secure_delete").fetchone()[0], 1)

    def test_id_is_random_not_from_the_name(self):
        first, second = self.book.add(SARAH), self.book.add(SARAH)
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{32}$")

    def test_every_write_gets_a_new_nonce(self):
        person = self.book.add(SARAH)
        nonce = self.rows()[0][1]
        self.book.update(person, {"phone": "919-555-0199"})
        self.assertEqual(len(self.rows()[0][1]), address_book.NONCE_BYTES)
        self.assertNotEqual(self.rows()[0][1], nonce)

    def test_blobs_swapped_between_rows_do_not_open(self):
        first, second = self.book.add(SARAH), self.book.add({"name": "Nora Pike"})
        rows = {row[0]: row for row in self.rows()}
        self.poke("UPDATE people SET nonce=?, sealed=? WHERE id=?", rows[second][1], rows[second][2], first)
        self.poke("UPDATE people SET nonce=?, sealed=? WHERE id=?", rows[first][1], rows[first][2], second)
        self.book.lock()
        self.assertEqual(self.book.state(), "open")
        self.assertEqual(self.book.people(), [])
        self.assertEqual(self.book.damaged(), 2)
        self.assertEqual(len(self.rows()), 2)

    def test_repr_and_errors_carry_no_details(self):
        self.assertEqual(repr(self.book), "<AddressBook people=?>")
        self.book.add(SARAH)
        self.assertEqual(repr(self.book), "<AddressBook people=1>")
        self.assertEqual(str(BookLocked("Sarah")), "the address book is locked")
        self.assertEqual(str(BookFull("Sarah")), "the address book is full")


class Locked(Base):
    def test_a_fresh_book_makes_nothing_until_the_first_write(self):
        self.assertEqual(self.book.state(), "open")
        self.assertEqual(self.book.people(), [])
        self.assertEqual(self.book.find("Sarah"), [])
        self.assertEqual(self.book.clear(), 0)
        self.assertFalse(self.book.remove("0" * 32))
        self.assertIsNone(self.key())
        self.assertFalse(self.book.path.parent.exists())
        self.book.add(SARAH)
        self.assertEqual(len(base64.b64decode(self.key(), validate=True)), 32)

    def test_missing_key_locks_and_no_new_key_is_made(self):
        self.book.add(SARAH)
        self.secrets.delete(address_book.KEY_NAME)
        self.assert_locked(self.reopened(), "key")
        self.assert_locked(self.book, "key")  # the same instance, already open
        self.assertIsNone(self.key())

    def test_wrong_key_locks_and_stays_the_wrong_key(self):
        self.book.add(SARAH)
        wrong = base64.b64encode(os.urandom(32)).decode("ascii")
        self.secrets.put(address_book.KEY_NAME, wrong)
        self.assert_locked(self.reopened(), "key")
        self.assertEqual(self.key(), wrong)

    def test_a_stored_value_that_is_not_a_key_locks(self):
        self.book.add(SARAH)
        for junk in ("not base64 !", base64.b64encode(b"short").decode("ascii")):
            self.secrets.put(address_book.KEY_NAME, junk)
            self.assert_locked(self.reopened(), "key")
            self.assertEqual(self.key(), junk)

    def test_meta_alone_still_locks_without_the_key(self):
        person = self.book.add(SARAH)
        self.book.remove(person)
        self.secrets.delete(address_book.KEY_NAME)
        self.assert_locked(self.reopened(), "key")
        self.assertIsNone(self.key())

    def test_rows_without_meta_are_checked_by_the_rows(self):
        person = self.book.add(SARAH)
        self.poke("DELETE FROM meta")
        self.assertEqual(self.reopened().get(person)["name"], "Sarah Jenkins")
        self.secrets.put(address_book.KEY_NAME, base64.b64encode(os.urandom(32)).decode("ascii"))
        self.assert_locked(self.reopened(), "key")

    def test_a_damaged_check_value_does_not_lock_a_good_key_out(self):
        person = self.book.add(SARAH)
        self.poke("UPDATE meta SET sealed=?", b"\x00" * 40)
        book = self.reopened()
        self.assertEqual(book.state(), "open")
        book.update(person, {"phone": "919-555-0199"})  # a write puts a good one back
        book.remove(person)
        self.assertEqual(self.reopened().state(), "open")

    def test_no_safe_store_and_no_book_makes_nothing(self):
        self.addCleanup(secret_store.set_backend, helpers.SECRETS)
        secret_store.set_backend(secret_store.UnavailableBackend())
        self.assertFalse(self.secrets.available())
        self.assert_locked(self.book, "unavailable")
        self.book.backup(fresh=True)
        self.assertFalse(self.book.path.parent.exists())
        secret_store.set_backend(helpers.SECRETS)
        self.assertIsNone(self.key())

    def test_no_safe_store_with_rows_locks_and_comes_back(self):
        person = self.book.add(SARAH)
        self.addCleanup(secret_store.set_backend, helpers.SECRETS)
        secret_store.set_backend(secret_store.UnavailableBackend())
        before = self.book.path.read_bytes()
        self.assertEqual(self.book.state(), "locked")
        with self.assertRaises(BookLocked):
            self.book.people()
        self.assertEqual(self.book.path.read_bytes(), before)
        secret_store.set_backend(helpers.SECRETS)
        self.assertEqual(self.book.get(person)["name"], "Sarah Jenkins")

    def test_a_store_that_will_not_keep_the_key_stops_the_first_write(self):
        with mock.patch.object(self.secrets, "put", side_effect=secret_store.NotAvailable()):
            with self.assertRaises(BookLocked):
                self.book.add(SARAH)
        with mock.patch.object(self.secrets, "put"):  # says it kept it, but didn't
            with self.assertRaises(BookLocked):
                self.book.add(SARAH)
        self.assertFalse(self.book.path.exists())

    def test_restored_key_opens_it_all_again(self):
        person = self.book.add(SARAH)
        key = self.key()
        self.secrets.delete(address_book.KEY_NAME)
        self.assertEqual(self.book.state(), "locked")
        self.secrets.put(address_book.KEY_NAME, key)
        self.assertEqual(self.book.state(), "open")
        self.assertEqual(self.book.get(person)["email"], "sarah.j@example.org")
        self.assertEqual(self.reopened().get(person)["email"], "sarah.j@example.org")

    def test_a_file_that_is_not_a_database_locks_and_stays(self):
        self.book.path.parent.mkdir(parents=True)
        self.book.path.write_bytes(b"this is not a database, and nothing may overwrite it" * 40)
        self.assert_locked(self.book, "file")
        self.assertIsNone(self.key())

    def test_library_missing_gives_locked_not_plain(self):
        person = self.book.add(SARAH)
        with mock.patch.object(address_book, "CRYPTO_OK", False):
            self.assert_locked(self.book, "unavailable")
            fresh = Path(tempfile.mkdtemp(dir=helpers.TMP))
            empty = AddressBook(fresh, secret_store.SecretStore(fresh))
            self.assertEqual(empty.state(), "locked")
            with self.assertRaises(BookLocked):
                empty.add(SARAH)
            self.assertFalse((fresh / "mary").exists())
        self.assertEqual(self.book.get(person)["name"], "Sarah Jenkins")

    def test_a_failed_import_still_loads_the_module_and_stays_locked(self):
        spec = importlib.util.spec_from_file_location("address_book_no_crypto", address_book.__file__)
        module = importlib.util.module_from_spec(spec)
        blocked = {"cryptography": None, "cryptography.hazmat.primitives.ciphers.aead": None}
        with mock.patch.dict(sys.modules, blocked):
            spec.loader.exec_module(module)
        self.assertFalse(module.CRYPTO_OK)
        book = module.AddressBook(self.folder, self.secrets)
        self.assertEqual(book.state(), "locked")
        with self.assertRaises(module.BookLocked):
            book.add(SARAH)
        self.assertFalse(book.path.exists())
        self.assertIsNone(self.key())

    def test_state_never_raises(self):
        with mock.patch.object(self.book, "_try_open", side_effect=RuntimeError("boom")):
            self.assertEqual(self.book.state(), "locked")


class Damage(Base):
    def test_a_damaged_row_is_skipped_counted_and_kept(self):
        good, bad = self.book.add({"name": "Nora Pike"}), self.book.add(SARAH)
        sealed = bytearray(next(row[2] for row in self.rows() if row[0] == bad))
        sealed[5] ^= 0xFF
        self.poke("UPDATE people SET sealed=? WHERE id=?", bytes(sealed), bad)
        self.book.lock()
        self.assertEqual([p["id"] for p in self.book.people()], [good])
        self.assertIsNone(self.book.get(bad))
        self.assertFalse(self.book.remove(bad))
        self.assertEqual(self.book.damaged(), 1)
        self.assertEqual(self.book.count(), 1)
        self.assertIn(bad, [row[0] for row in self.rows()])
        self.assertIn(bytes(sealed), [row[2] for row in self.rows()])

    def test_rows_of_junk_do_not_stop_the_book(self):
        good = self.book.add(SARAH)
        self.poke("INSERT INTO people(id, nonce, sealed) VALUES(?, ?, ?)", "f" * 32, b"", b"")
        self.poke("INSERT INTO people(id, nonce, sealed) VALUES(?, ?, ?)", "e" * 32, "text", "text")
        self.book.lock()
        self.assertEqual([p["id"] for p in self.book.people()], [good])
        self.assertEqual(self.book.damaged(), 2)

    def test_clear_takes_damaged_rows_too(self):
        self.book.add(SARAH)
        self.poke("UPDATE people SET sealed=?", b"\x00" * 40)
        self.book.lock()
        self.assertEqual(self.book.damaged(), 1)
        self.assertEqual(self.book.clear(), 1)
        self.assertEqual(self.book.damaged(), 0)


class Records(Base):
    def test_always_the_exact_field_set(self):
        person = self.book.add({"name": "Nora", "shoe_size": "9", "id": "x"})
        record = self.book.get(person)
        self.assertEqual(set(record), {"id", *address_book.FIELDS})
        self.assertEqual(record["id"], person)
        self.assertEqual(record["kind"], "person")
        self.assertIs(record["asked"], False)
        self.assertEqual(record["relationship"], "")

    def test_a_blank_name_is_refused(self):
        for name in ("", "   ", None):
            with self.assertRaises(ValueError):
                self.book.add({"name": name, "email": "a@example.org"})
        self.assertFalse(self.book.path.exists())

    def test_text_is_cut_to_its_limit_and_tidied(self):
        person = self.book.add({"name": "N" * 100, "notes": "n" * 2000, "email": "e" * 300, "phone": "919\x00 555\n0142",
                                "address": "12 Oak St\nRaleigh", "cell": "\ud800 919"})
        record = self.book.get(person)
        self.assertEqual(len(record["name"]), 60)
        self.assertEqual(len(record["notes"]), 1000)
        self.assertEqual(len(record["email"]), 254)
        self.assertEqual(record["phone"], "919 555 0142")
        self.assertEqual(record["address"], "12 Oak St\nRaleigh")
        self.assertEqual(record["cell"], "919")

    def test_birthday_forms(self):
        for given, kept in (("03-14", "03-14"), ("1951-03-14", "1951-03-14"), ("02-29", "02-29"), ("1952-02-29", "1952-02-29"),
                            ("1951-02-29", ""), ("13-01", ""), ("March 14", ""), ("", ""), (None, "")):
            self.assertEqual(self.book.get(self.book.add({"name": "Nora", "birthday": given}))["birthday"], kept, given)

    def test_kind_and_flags(self):
        doctor = self.book.add({"name": "Dr Lane", "kind": "doctor", "asked": True, "no_keep": True})
        self.assertEqual(self.book.get(doctor)["kind"], "doctor")
        self.assertIs(self.book.get(doctor)["asked"], True)
        self.assertIs(self.book.get(doctor)["no_keep"], True)
        self.assertEqual(self.book.get(self.book.add({"name": "Nora", "kind": "cat"}))["kind"], "person")

    def test_update_merges_only_fields(self):
        person = self.book.add(SARAH)
        self.assertTrue(self.book.update(person, {"phone": "919-555-0199", "shoe_size": "9", "id": "x"}))
        record = self.reopened().get(person)
        self.assertEqual(record["phone"], "919-555-0199")
        self.assertEqual(record["email"], SARAH["email"])
        self.assertEqual(record["id"], person)
        self.assertNotIn("shoe_size", record)
        self.assertFalse(self.book.update("0" * 32, {"phone": "1"}))

    def test_a_name_cannot_go_blank_and_a_bad_birthday_changes_nothing(self):
        person = self.book.add({**SARAH, "birthday": "03-14"})
        self.assertTrue(self.book.update(person, {"name": "  ", "birthday": "someday", "phone": "1"}))
        record = self.book.get(person)
        self.assertEqual((record["name"], record["birthday"], record["phone"]), ("Sarah Jenkins", "03-14", "1"))
        self.book.update(person, {"birthday": ""})
        self.assertEqual(self.book.get(person)["birthday"], "")

    def test_what_comes_back_cannot_change_the_book(self):
        person = self.book.add(SARAH)
        self.book.get(person)["name"] = "Changed"
        self.book.people()[0]["name"] = "Changed"
        self.assertEqual(self.book.get(person)["name"], "Sarah Jenkins")

    def test_people_sorted_without_case_and_hidden_left_out(self):
        for name in ("bob", "Alice", "Carl"):
            self.book.add({"name": name})
        self.book.add({"name": "Dan", "no_keep": True, "hidden": True})
        self.assertEqual([p["name"] for p in self.book.people()], ["Alice", "bob", "Carl"])
        self.assertEqual(self.book.count(), 3)
        self.assertEqual([p["name"] for p in self.book.people(include_hidden=True)], ["Alice", "bob", "Carl", "Dan"])

    def test_the_cap(self):
        self.assertEqual(address_book.MAX_PEOPLE, 500)
        with mock.patch.object(address_book, "MAX_PEOPLE", 2):
            self.book.add({"name": "One"})
            self.book.add({"name": "Two"})
            hidden = self.book.add({"name": "Dan", "no_keep": True, "hidden": True})  # hidden rows don't count
            with self.assertRaises(BookFull):
                self.book.add({"name": "Three"})
            with self.assertRaises(BookFull):
                self.book.update(hidden, {"hidden": False})
        self.assertEqual(self.book.count(), 2)

    def test_a_full_book_makes_no_key_for_nothing(self):
        with mock.patch.object(address_book, "MAX_PEOPLE", 0):
            with self.assertRaises(BookFull):
                self.book.add(SARAH)
        self.assertIsNone(self.key())

    def test_memory_rebuilds_from_the_file(self):
        person = self.book.add(SARAH)
        self.book.lock()
        self.assertIsNone(self.book._cache)
        self.assertEqual(self.book.get(person)["name"], "Sarah Jenkins")
        self.assertEqual(self.reopened().count(), 1)


class Find(Base):
    def setUp(self):
        super().setUp()
        self.jenkins = self.book.add({"name": "Sarah Jenkins", "relationship": "daughter"})
        self.miller = self.book.add({"name": "Sarah Miller", "relationship": "neighbor"})
        self.tom = self.book.add({"name": "Tom O’Brien", "relationship": "my son"})
        self.jake = self.book.add({"name": "Jake", "relationship": "step daughter"})
        self.book.add({"name": "Hank Lowe", "relationship": "brother", "no_keep": True, "hidden": True})

    def found(self, words):
        return [person["id"] for person in self.book.find(words)]

    def test_exact_name_comes_first(self):
        only = self.book.add({"name": "Sarah"})
        self.assertEqual(self.found("sarah"), [only])
        self.assertEqual(self.found("SARAH JENKINS"), [self.jenkins])

    def test_first_name_or_relationship_next(self):
        self.assertEqual(self.found("Sarah"), [self.jenkins, self.miller])
        self.assertEqual(self.found("neighbor"), [self.miller])
        self.assertEqual(self.found("My Daughter"), [self.jenkins])
        self.assertEqual(self.found("our neighbor"), [self.miller])
        self.assertEqual(self.found("son"), [self.tom])

    def test_relationship_and_first_name_last(self):
        self.assertEqual(self.found("my daughter Sarah"), [self.jenkins])
        self.assertEqual(self.found("Sarah my daughter"), [self.jenkins])
        self.assertEqual(self.found("my step daughter jake"), [self.jake])
        self.assertEqual(self.found("my sister Sarah"), [])

    def test_a_curly_apostrophe_and_a_straight_one_match(self):
        self.assertEqual(self.found("tom o'brien"), [self.tom])

    def test_hidden_marks_never_match_and_blank_finds_nothing(self):
        self.assertEqual(self.found("Hank Lowe"), [])
        self.assertEqual(self.found("brother"), [])
        self.assertEqual(self.found(""), [])
        self.assertEqual(self.found(None), [])
        self.assertEqual(self.found("my"), [])

    def test_the_same_answers_the_messages_skill_gave(self):
        """Its own search went in M19 piece 3. This is that search as it was, so the book can't drift from it."""
        from skills.messages import skill
        norm = skill._norm

        def both_named(contact, wanted):
            words, first, relation = wanted.split(), norm(contact["name"]).split()[:1], norm(contact.get("relationship"))
            return bool(first and relation) and first[0] in words and set(relation.split()) <= set(words)

        def old_find(every, name):
            wanted = norm(name)
            if not wanted:
                return []
            return [c for c in every if norm(c["name"]) == wanted] or [
                c for c in every if norm(c["name"]).split()[:1] == [wanted] or norm(c.get("relationship")) == wanted] or [
                c for c in every if both_named(c, wanted)]

        contacts = [{"name": p["name"], "relationship": p["relationship"]} for p in self.book.people()]
        for words in ("Sarah", "sarah miller", "my daughter", "my daughter Sarah", "son", "tom", "nobody", ""):
            self.assertEqual([p["name"] for p in self.book.find(words)],
                             [c["name"] for c in old_find(contacts, words)], words)


class Removing(Base):
    def test_remove_is_gone_from_both_files_at_once(self):
        first, second = self.book.add(SARAH), self.book.add({"name": "Nora Pike"})
        self.book.backup(fresh=True)
        gone = next(row[2] for row in self.rows() if row[0] == first)
        kept = next(row[2] for row in self.rows() if row[0] == second)
        self.assertIn(gone, self.book.path.read_bytes())
        self.assertIn(gone, self.book.backup_path.read_bytes())
        self.assertTrue(self.book.remove(first))
        self.assertNotIn(gone, self.book.path.read_bytes())
        self.assertNotIn(gone, self.book.backup_path.read_bytes())
        self.assertNotIn(first.encode("ascii"), self.book.path.read_bytes())
        self.assertIn(kept, self.book.backup_path.read_bytes())
        self.assertIsNone(self.reopened().get(first))
        self.assertFalse(self.book.remove(first))
        self.assertFalse(self.book.backup_path.with_suffix(".tmp").exists())

    def test_clear_keeps_key_and_meta_and_leaves_no_blob(self):
        self.book.add(SARAH)
        self.book.add({"name": "Dan", "hidden": True})
        self.book.backup(fresh=True)
        blobs = [row[2] for row in self.rows()]
        key = self.key()
        self.assertEqual(self.book.clear(), 2)
        self.assertEqual(self.book.people(include_hidden=True), [])
        self.assertEqual(self.key(), key)
        for path in (self.book.path, self.book.backup_path):
            data = path.read_bytes()
            for blob in blobs:
                self.assertNotIn(blob, data)
        with closing(sqlite3.connect(self.book.path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0], 1)
        person = self.book.add({"name": "Nora"})
        self.assertEqual(self.reopened().get(person)["name"], "Nora")

    def test_a_failed_fresh_copy_deletes_the_copy(self):
        person = self.book.add(SARAH)
        self.book.backup(fresh=True)
        with mock.patch.object(address_book.os, "replace", side_effect=OSError("disk")):
            self.assertTrue(self.book.remove(person))
        self.assertFalse(self.book.backup_path.exists())
        self.assertFalse(self.book.backup_path.with_suffix(".tmp").exists())
        self.assertFalse(self.book._backup_stale)

    def test_a_failed_delete_of_the_copy_retries(self):
        person = self.book.add(SARAH)
        self.book.add({"name": "Nora Pike"})
        self.book.backup(fresh=True)
        gone = next(row[2] for row in self.rows() if row[0] == person)
        with mock.patch.object(address_book.os, "replace", side_effect=OSError("disk")), \
                mock.patch.object(address_book, "_gone", return_value=False):
            self.book.remove(person)
        self.assertTrue(self.book._backup_stale)
        self.assertIn(gone, self.book.backup_path.read_bytes())
        self.book.backup()  # dated today, but it's stale, so it's redone
        self.assertFalse(self.book._backup_stale)
        self.assertNotIn(gone, self.book.backup_path.read_bytes())


class RollingCopy(Base):
    def test_once_a_day_and_other_writes_do_not_force_it(self):
        person = self.book.add(SARAH)
        self.book.backup()
        before = self.book.backup_path.read_bytes()
        self.book.update(person, {"phone": "1"})
        self.book.add({"name": "Nora Pike"})
        self.book.backup()
        self.assertEqual(self.book.backup_path.read_bytes(), before)
        yesterday = time.time() - 2 * 86400
        os.utime(self.book.backup_path, (yesterday, yesterday))
        self.book.backup()
        self.assertNotEqual(self.book.backup_path.read_bytes(), before)

    def test_the_copy_opens_with_the_same_key(self):
        person = self.book.add(SARAH)
        self.book.backup()
        os.replace(self.book.backup_path, self.book.path)
        self.assertEqual(self.reopened().get(person)["name"], "Sarah Jenkins")

    def test_the_copy_is_made_with_secure_delete(self):
        self.book.add(SARAH)
        real, seen = sqlite3.connect, []

        def spy(path, *args, **kwargs):
            conn = real(path, *args, **kwargs)
            if str(path).endswith(".tmp"):
                conn.set_trace_callback(seen.append)
            return conn

        with mock.patch.object(address_book.sqlite3, "connect", side_effect=spy):
            self.book.backup(fresh=True)
        self.assertIn("PRAGMA secure_delete=ON", seen)
        self.assertTrue(self.book.backup_path.exists())

    def test_a_locked_book_leaves_its_daily_copy_alone(self):
        self.book.add(SARAH)
        self.book.backup()
        before = self.book.backup_path.read_bytes()
        yesterday = time.time() - 2 * 86400
        os.utime(self.book.backup_path, (yesterday, yesterday))
        self.secrets.delete(address_book.KEY_NAME)
        self.poke("INSERT INTO meta(key, nonce, sealed) VALUES('other', x'00', x'00')")
        self.book.backup()
        self.assertEqual(self.book.backup_path.read_bytes(), before)

    def test_a_failed_daily_copy_leaves_the_old_one(self):
        self.book.add(SARAH)
        self.book.backup()
        before = self.book.backup_path.read_bytes()
        yesterday = time.time() - 2 * 86400
        os.utime(self.book.backup_path, (yesterday, yesterday))
        with mock.patch.object(address_book.os, "replace", side_effect=OSError("disk")):
            self.book.backup()
        self.assertEqual(self.book.backup_path.read_bytes(), before)

    def test_it_never_makes_the_book(self):
        self.book.backup()
        self.book.backup(fresh=True)
        self.assertFalse(self.book.path.exists())
        self.assertFalse(self.book.backup_path.exists())


class Plainly(unittest.TestCase):
    def test_only_this_module_imports_cryptography(self):
        for path in helpers.ROOT.glob("*.py"):
            if path.name != "address_book.py":
                self.assertNotRegex(path.read_text(encoding="utf-8"), r"(?m)^\s*(?:import|from)\s+cryptography", path.name)

    def test_nothing_is_logged(self):
        source = Path(address_book.__file__).read_text(encoding="utf-8")
        self.assertNotIn("print(", source)
        self.assertNotIn("logging", source)


if __name__ == "__main__":
    unittest.main()
