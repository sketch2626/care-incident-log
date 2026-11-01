"""M19 piece 3: the old contacts move into the sealed book once, and leave incidents.db and its dated backups."""
from tests import helpers  # noqa: F401  (first: points the data folder at scratch)

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest import mock

import address_book
import book_move
import secret_store
import server

MARK = {"name": "Mark Hollis", "relationship": "son", "email": "mark.hollis@example.org", "facebook": "Mark H Fishing",
        "phone": "919-555-0100", "asked": True, "no_keep": False}
TOM = {"name": "Tom Reed", "relationship": "", "email": "", "facebook": "", "phone": "", "asked": True, "no_keep": True}
OLD_ONLY = {"name": "Vera Lang", "relationship": "", "email": "vera.lang@example.org", "facebook": "", "phone": "",
            "asked": True, "no_keep": False}
PRIVATE = ("Mark Hollis", "mark.hollis", "example.org", "Mark H Fishing", "919-555-0100", "Tom Reed", "tom-reed")
SKILL_TABLE = ("CREATE TABLE IF NOT EXISTS skill_data (skill TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
               "updated_at TEXT, PRIMARY KEY (skill, key))")
IS_CONTACT = "skill='messages' AND (key='contacts' OR key LIKE 'contact-%')"
OLD_TIME = 1700000000


def slug(person):
    return person["name"].lower().replace(" ", "-")


def put_people(conn, *people):
    conn.execute(SKILL_TABLE)
    conn.execute("INSERT OR REPLACE INTO skill_data VALUES ('messages', 'contacts', ?, 't')",
                 (json.dumps([slug(person) for person in people]),))
    conn.executemany("INSERT OR REPLACE INTO skill_data VALUES ('messages', ?, ?, 't')",
                     [("contact-" + slug(person), json.dumps(person)) for person in people])


def fill(path, *people):
    """A log as the app leaves it: an incident, the other tables and rows, and these contacts."""
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(server.SCHEMA)
        conn.execute(SKILL_TABLE)
        conn.execute("INSERT INTO incidents (occurred_date, category, description, logged_at, updated_at) "
                     "VALUES ('2026-10-01', 'call_light', 'Waited an hour.', '2026-10-01 09:00:00', '2026-10-01 09:00:00')")
        conn.execute("INSERT INTO settings (key, value) VALUES ('resident_name', 'Pat Moore')")
        conn.execute("INSERT INTO inbox_seen VALUES ('note', 7, 'added', '2026-10-01')")
        conn.execute("INSERT INTO skill_data VALUES ('messages', 'draft', ?, 't')",
                     (json.dumps({"id": "c1", "person": "Sue", "words": "Happy birthday."}),))
        conn.execute("INSERT INTO skill_data VALUES ('weather', 'contact-card', '{\"kept\": 1}', 't')")  # not this skill's row
        put_people(conn, *people)
        conn.commit()


def evidence(path):
    """A SHA-256 of the test's own, over every row of every table but skill_data."""
    digest = hashlib.sha256()
    with closing(sqlite3.connect(path)) as conn:
        names = sorted(row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        for name in names:
            if name != "skill_data":
                digest.update(name.encode("utf-8"))
                for row in conn.execute(f"SELECT * FROM {name} ORDER BY rowid"):
                    digest.update(repr(row).encode("utf-8"))
    return digest.hexdigest()


def others(path):
    """Every skill_data row that isn't a contact."""
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(f"SELECT * FROM skill_data WHERE NOT ({IS_CONTACT}) ORDER BY skill, key").fetchall()


def contact_rows(path):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(f"SELECT key FROM skill_data WHERE {IS_CONTACT} ORDER BY key").fetchall()


def setting(path, key=book_move.DONE_KEY):
    with closing(sqlite3.connect(path)) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def holds(path, *words):
    raw = Path(path).read_bytes()
    return [word for word in words if word.encode("utf-8") in raw]


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="book-move-", dir=helpers.TMP))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.db = self.dir / "incidents.db"
        self.backups = self.dir / "backups"
        self.backups.mkdir()
        self.log = self.dir / "book_move.log"
        self.secrets = secret_store.SecretStore(self.dir)
        self.book = address_book.AddressBook(self.dir, self.secrets)
        fill(self.db, MARK, TOM)

    def run_move(self):
        book_move.run(self.db, self.backups, self.book, self.log)

    def in_book(self, name):
        return next((p for p in self.book.people(include_hidden=True) if p["name"] == name), None)

    def backup(self, day, *people):
        path = self.backups / f"incidents_{day}.db"
        fill(path, *people)
        os.utime(path, (OLD_TIME, OLD_TIME))
        return path

    def logged(self):
        return [json.loads(line) for line in self.log.read_text("utf-8").splitlines()]


class Moves(Base):
    def test_rows_move_field_for_field(self):
        self.run_move()
        self.book.lock()  # from the file, not from what's in memory
        mark = self.in_book("Mark Hollis")
        for field, value in MARK.items():
            self.assertEqual(mark[field], value, field)
        self.assertFalse(mark["hidden"])
        self.assertEqual(self.book.count(), 1)

    def test_they_leave_the_file_for_good(self):
        self.assertEqual(sorted(holds(self.db, *PRIVATE)), sorted(PRIVATE))
        self.run_move()
        self.assertEqual(contact_rows(self.db), [])
        self.assertEqual(holds(self.db, *PRIVATE), [])

    def test_nothing_else_changes(self):
        before, rest = evidence(self.db), others(self.db)
        self.run_move()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("DELETE FROM settings WHERE key=?", (book_move.DONE_KEY,))
            conn.commit()
        self.assertEqual(evidence(self.db), before)
        self.assertEqual(others(self.db), rest)
        self.assertEqual(len(rest), 2)

    def test_no_journal_is_left(self):
        self.run_move()
        self.assertEqual([p.name for p in self.dir.glob("incidents.db-*")], [])

    def test_a_no_keep_with_nothing_else_is_a_hidden_mark(self):
        self.run_move()
        tom = self.in_book("Tom Reed")
        self.assertTrue(tom["hidden"])
        self.assertEqual([person["name"] for person in self.book.people()], ["Mark Hollis"])
        self.assertEqual(self.book.find("Tom Reed"), [])

    def test_a_no_keep_with_a_detail_stays_in_the_list(self):
        put = dict(TOM, name="Ann Bell", phone="919-555-0111")
        with closing(sqlite3.connect(self.db)) as conn, conn:
            put_people(conn, MARK, put)
        self.run_move()
        self.assertFalse(self.in_book("Ann Bell")["hidden"])
        self.assertTrue(self.in_book("Ann Bell")["no_keep"])

    def test_asked_and_no_keep_carry_over(self):
        self.run_move()
        self.assertEqual((self.in_book("Tom Reed")["asked"], self.in_book("Tom Reed")["no_keep"]), (True, True))
        self.assertEqual((self.in_book("Mark Hollis")["asked"], self.in_book("Mark Hollis")["no_keep"]), (True, False))

    def test_a_merge_fills_blanks_and_overwrites_nothing(self):
        there = self.book.add({"name": "mark hollis", "phone": "919-555-0199", "notes": "Fishes on Sundays"})
        self.run_move()
        self.assertEqual(self.book.count(), 1)
        person = self.book.get(there)
        self.assertEqual((person["name"], person["phone"], person["notes"]),
                         ("mark hollis", "919-555-0199", "Fishes on Sundays"))
        self.assertEqual((person["email"], person["relationship"], person["facebook"], person["asked"]),
                         (MARK["email"], "son", "Mark H Fishing", True))

    def test_a_dont_keep_already_in_the_book_keeps_the_address_out(self):
        there = self.book.add({"name": "Mark Hollis", "no_keep": True, "hidden": True})
        self.run_move()
        self.assertEqual(self.book.get(there)["email"], "")
        self.assertEqual(self.book.get(there)["phone"], MARK["phone"])

    def test_a_doctor_is_never_merged_into(self):
        doctor = self.book.add({"name": "Mark Hollis", "kind": "doctor", "phone": "919-555-0177"})
        self.run_move()
        self.assertEqual(self.book.get(doctor)["email"], "")
        self.assertEqual(len([p for p in self.book.people() if p["name"] == "Mark Hollis"]), 2)

    def test_malformed_rows_stay_and_are_counted(self):
        bad = [("contact-a", "not json"), ("contact-b", "[1, 2]"), ("contact-c", '{"relationship": "son"}'),
               ("contact-d", '{"name": "Ed", "email": 5}'), ("contact-e", '{"name": "Ed", "asked": "yes"}'),
               ("contact-f", '{"name": ""}'), ("contact-g", json.dumps({"name": "Ed " + "x" * 70}))]
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.executemany("INSERT INTO skill_data VALUES ('messages', ?, ?, 't')", [(k, v) for k, v in bad])
        self.run_move()
        self.assertEqual([row[0] for row in contact_rows(self.db)], [key for key, _ in bad])
        self.assertEqual(self.logged()[-1]["malformed"], len(bad))
        self.assertEqual(self.logged()[-1]["moved"], 2)
        self.assertEqual(setting(self.db), "1")  # they can never move, so they don't hold the move open
        self.assertIsNone(self.in_book("Ed"))

    def test_a_malformed_index_stays_and_the_people_still_move(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE skill_data SET value='oops' WHERE key='contacts'")
        self.run_move()
        self.assertEqual(contact_rows(self.db), [("contacts",)])
        self.assertIsNotNone(self.in_book("Mark Hollis"))

    def test_no_table_at_all_is_fine(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("DROP TABLE skill_data")
            conn.commit()
        self.run_move()
        self.assertEqual(setting(self.db), "1")

    def test_a_read_back_that_differs_deletes_nothing(self):
        real = address_book.AddressBook.get

        def wrong(book, row_id):
            person = real(book, row_id)
            return person and {**person, "email": "changed@example.net"}

        with mock.patch.object(address_book.AddressBook, "get", wrong):
            self.run_move()
        self.assertEqual(len(contact_rows(self.db)), 3)
        self.assertIsNone(setting(self.db))
        self.assertEqual(self.logged()[-1]["stopped"], book_move.STOP_MISMATCH)
        self.run_move()  # and the next start finishes it, with no double
        self.assertEqual(contact_rows(self.db), [])
        self.assertEqual(self.book.count(), 1)

    def test_a_full_book_deletes_nothing(self):
        with mock.patch.object(address_book, "MAX_PEOPLE", 0):
            self.run_move()
        self.assertEqual(len(contact_rows(self.db)), 3)
        self.assertIsNone(setting(self.db))

    def test_a_changed_file_stops_before_the_backups(self):
        path = self.backup("2026-10-01", MARK)
        raw = path.read_bytes()
        with mock.patch.object(book_move, "_fingerprint", side_effect=["one", "two"]):
            self.run_move()
        self.assertEqual(self.logged()[-1]["stopped"], book_move.STOP_CHANGED)
        self.assertEqual(path.read_bytes(), raw)
        self.assertIsNone(setting(self.db))

    def test_the_log_holds_counts_and_no_names(self):
        self.backup("2026-10-01", MARK)
        self.run_move()
        text = self.log.read_text("utf-8")
        self.assertEqual(holds(self.log, *PRIVATE), [])
        row = self.logged()[-1]
        self.assertEqual({key: row[key] for key in ("moved", "malformed", "backups_cleaned", "backups_left", "stopped")},
                         {"moved": 2, "malformed": 0, "backups_cleaned": 1, "backups_left": 0, "stopped": ""})
        self.assertNotIn("Tom", text)

    def test_it_never_raises(self):
        self.db.unlink()
        self.db.mkdir()  # can't be opened as a database
        self.run_move()
        self.assertTrue(self.logged()[-1]["stopped"])


class Backups(Base):
    def test_cleaned_with_the_evidence_and_the_date_kept(self):
        path = self.backup("2026-10-01", MARK, TOM)
        before, rest = evidence(path), others(path)
        self.assertEqual(sorted(holds(path, *PRIVATE)), sorted(PRIVATE))
        self.run_move()
        self.assertEqual(contact_rows(path), [])
        self.assertEqual(holds(path, *PRIVATE), [])
        self.assertEqual(evidence(path), before)
        self.assertEqual(others(path), rest)
        self.assertEqual(path.stat().st_mtime, OLD_TIME)
        with closing(sqlite3.connect(path)) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(), [("ok",)])

    def test_every_dated_backup_is_cleaned(self):
        paths = [self.backup(f"2026-10-{day:02}", MARK) for day in range(1, 6)]
        self.run_move()
        for path in paths:
            self.assertEqual(holds(path, *PRIVATE), [])
        self.assertEqual(self.logged()[-1]["backups_cleaned"], 5)
        self.assertEqual(setting(self.db), "1")

    def test_a_contact_only_in_an_old_backup_does_not_come_back(self):
        path = self.backup("2026-10-01", OLD_ONLY)
        self.run_move()
        self.assertIsNone(self.in_book("Vera Lang"))
        self.assertEqual(holds(path, "Vera Lang", "vera.lang"), [])

    def test_a_backup_with_no_contacts_is_not_touched(self):
        path = self.backup("2026-10-01")
        with closing(sqlite3.connect(path)) as conn:
            conn.execute(f"DELETE FROM skill_data WHERE {IS_CONTACT}")
            conn.commit()
        os.utime(path, (OLD_TIME, OLD_TIME))
        raw = path.read_bytes()
        self.run_move()
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(path.stat().st_mtime, OLD_TIME)

    def tampered(self):
        """The copy's hash comes out different. Everything else hashes as it should."""
        real = book_move._fingerprint

        def fingerprint(conn):
            name = conn.execute("PRAGMA database_list").fetchone()[2]
            return "tampered" if name.endswith(book_move.TEMP) else real(conn)

        return mock.patch.object(book_move, "_fingerprint", fingerprint)

    def test_a_mismatch_leaves_the_backup_byte_identical_and_retries(self):
        path = self.backup("2026-10-01", MARK)
        good = self.backup("2026-10-02", MARK)
        raw = path.read_bytes()
        real = book_move._fingerprint

        def only_the_first(conn):
            name = conn.execute("PRAGMA database_list").fetchone()[2]
            return "tampered" if name.endswith("2026-10-01.db" + book_move.TEMP) else real(conn)

        with mock.patch.object(book_move, "_fingerprint", only_the_first):
            self.run_move()
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(path.stat().st_mtime, OLD_TIME)
        self.assertEqual(holds(good, *PRIVATE), [])
        self.assertEqual([p.name for p in self.backups.iterdir() if ".clean" in p.name], [])
        self.assertIsNone(setting(self.db))
        row = self.logged()[-1]
        self.assertEqual((row["backups_left"], row["backups_cleaned"]), (1, 1))
        self.run_move()  # the next start tries again, and this time it's clean
        self.assertEqual(holds(path, *PRIVATE), [])
        self.assertEqual(setting(self.db), "1")

    def test_a_copy_that_fails_its_check_leaves_the_backup_alone(self):
        path = self.backup("2026-10-01", MARK)
        raw = path.read_bytes()
        with self.tampered():
            self.run_move()
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(self.logged()[-1]["backups_left"], 1)

    def test_a_swap_that_fails_leaves_the_backup_alone(self):
        path = self.backup("2026-10-01", MARK)
        raw = path.read_bytes()
        with mock.patch.object(book_move.os, "replace", side_effect=OSError("in use")):
            self.run_move()
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual([p.name for p in self.backups.iterdir()], [path.name])
        self.assertIsNone(setting(self.db))

    def test_a_broken_backup_is_left_and_counted(self):
        path = self.backups / "incidents_2026-10-01.db"
        path.write_bytes(b"not a database, " * 64)
        raw = path.read_bytes()
        self.run_move()
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(self.logged()[-1]["backups_left"], 1)
        self.assertIsNone(setting(self.db))

    def test_a_temp_file_from_a_start_that_died_goes(self):
        stale = self.backups / ("incidents_2026-10-01.db" + book_move.TEMP)
        stale.write_bytes(b"Mark Hollis")
        self.run_move()
        self.assertFalse(stale.exists())

    def test_the_cheap_check_does_not_open_a_backup(self):
        self.run_move()
        with mock.patch.object(book_move, "_clean_backups") as clean:
            self.run_move()
        clean.assert_not_called()


class Once(Base):
    def lock(self):
        self.book.add({"name": "Someone Else"})
        self.key = self.secrets.get(address_book.KEY_NAME)
        self.book.lock()
        self.secrets.delete(address_book.KEY_NAME)
        self.assertEqual(self.book.state(), "locked")

    def test_a_locked_book_leaves_every_row_and_the_next_start_retries(self):
        path = self.backup("2026-10-01", MARK)
        raw = path.read_bytes()
        self.lock()
        self.run_move()
        self.assertEqual(len(contact_rows(self.db)), 3)
        self.assertEqual(path.read_bytes(), raw)
        self.assertIsNone(setting(self.db))
        self.assertEqual(self.logged()[-1]["stopped"], book_move.STOP_LOCKED)
        self.secrets.put(address_book.KEY_NAME, self.key)
        self.book.lock()
        self.run_move()
        self.assertEqual(contact_rows(self.db), [])
        self.assertIsNotNone(self.in_book("Mark Hollis"))
        self.assertEqual(setting(self.db), "1")

    def test_once_only(self):
        self.run_move()
        lines, stamp = len(self.logged()), self.db.stat().st_mtime_ns
        with mock.patch.object(book_move, "_take_out") as take_out, \
                mock.patch.object(book_move, "_into_book") as into_book:
            self.run_move()
        take_out.assert_not_called()
        into_book.assert_not_called()
        self.assertEqual(len(self.logged()), lines)
        self.assertEqual(self.db.stat().st_mtime_ns, stamp)

    def test_a_forget_since_the_move_stays_forgotten(self):
        self.run_move()
        self.book.remove(self.in_book("Mark Hollis")["id"])
        self.run_move()
        self.assertIsNone(self.in_book("Mark Hollis"))

    def test_new_rows_after_the_move_go_the_same_way(self):
        self.run_move()
        late = dict(MARK, name="Joan Fry", email="joan.fry@example.org")
        with closing(sqlite3.connect(self.db)) as conn, conn:
            put_people(conn, late)
        self.run_move()
        self.assertEqual(self.in_book("Joan Fry")["email"], "joan.fry@example.org")
        self.assertEqual(contact_rows(self.db), [])
        self.assertEqual(holds(self.db, "Joan Fry", "joan.fry"), [])

    def test_only_malformed_rows_after_the_move_do_no_work(self):
        self.run_move()
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("INSERT INTO skill_data VALUES ('messages', 'contact-x', 'not json', 't')")
        lines = len(self.logged())
        self.run_move()
        self.assertEqual(len(self.logged()), lines)
        self.assertEqual(contact_rows(self.db), [("contact-x",)])


class AtStart(unittest.TestCase):
    """Through server.init_db and the page's routes, on the scratch log."""

    def setUp(self):
        helpers.reset_db()
        self.addCleanup(helpers.reset_db)
        self.addCleanup(lambda: (server.DATA / "book_move.log").unlink(missing_ok=True))
        self.today = server.BACKUPS / f"incidents_{datetime.now():%Y-%m-%d}.db"
        self.today.unlink(missing_ok=True)
        with closing(sqlite3.connect(server.DB_PATH)) as conn, conn:
            put_people(conn, MARK, TOM)
        server.init_db()

    def test_the_move_comes_before_todays_backup(self):
        self.assertTrue(self.today.exists())
        self.assertEqual(holds(self.today, *PRIVATE), [])
        self.assertEqual(holds(server.DB_PATH, *PRIVATE), [])
        self.assertEqual(server.BOOK.find("Mark Hollis")[0]["email"], MARK["email"])
        self.assertEqual(setting(server.DB_PATH), "1")

    def test_the_page_never_sees_it_and_cannot_set_it(self):
        status, settings, _ = helpers.api("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertNotIn(book_move.DONE_KEY, settings)
        status, _, _ = helpers.api("PUT", "/api/settings", {book_move.DONE_KEY: "0"})
        self.assertEqual(status, 200)
        self.assertEqual(setting(server.DB_PATH), "1")


if __name__ == "__main__":
    unittest.main()
