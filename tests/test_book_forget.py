from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest import mock

import mail_core
import mary
import memory_core
import memory_dates
import server
from tests import test_m15c_send as flow

ADDRESS = flow.ADDRESS
TODAY = date(2027, 3, 8)  # six days before a birthday on the 14th, and never the day a test learned it
BIRTHDAY = "03-14"
ASK_SARAH = "Forget Sarah Beck? Her address, her birthday reminders and what I remember about her all go for good."
ASK_FIELD = "The email or the mailing address?"


def talk_date(who, month, day, what="birthday", relation=""):
    return {"who": who, "relation": relation, "month": month, "day": day, "what": what}


class Book(flow.Flow):
    """The real routes and the real book, with the send flow's host pointed at it."""

    def setUp(self):
        super().setUp()
        self.host.book = server.BOOK
        self.store = server.memory_store()

    def add(self, name, **fields):
        return server.BOOK.add({"name": name, **fields})

    def rows(self, sql, *args):
        with closing(server.connect_memories()) as conn:
            return [tuple(row) for row in conn.execute(sql, args).fetchall()]

    def book_row(self, person_id):
        return self.rows("SELECT id, month, day FROM dates WHERE person_id = ?", person_id)

    def tool(self, about, **args):
        return self.post("/api/mary/skills/call", {"name": "forget_memory", "args": {"about": about, **args}})["response"]

    def forget(self, about):
        first = self.tool(about)
        self.assertTrue(first.get("needs_yes"), first)
        return self.tool(about, confirmed=True)

    def person(self, person_id):
        return server.BOOK.get(person_id)


class Marks(Book):
    def test_a_mark_holds_however_the_person_is_named(self):
        self.add("Mark Hollis", relationship="son", no_keep=True, hidden=True)
        for words in ("Mark Hollis", "Mark", "my son", "son"):
            self.assertEqual(self.ctx.people.marks(words), {"asked": False, "no_keep": True}, words)
        self.assertEqual(self.ctx.people.marks("Nobody"), {"asked": False, "no_keep": False})
        self.assertEqual(self.ctx.people.find("Mark"), [])  # still never a handle
        self.assertEqual(server.BOOK.find("Mark"), [])

    def test_a_forget_by_first_name_takes_the_mark(self):
        self.add("Mark Hollis", relationship="son", no_keep=True, hidden=True)
        self.tool("Mark")
        self.tool("Mark", confirmed=True)
        self.assertEqual(server.BOOK.people(include_hidden=True), [])


class OnChange(Book):
    def test_it_is_told_each_kind_and_a_fault_stays_inside(self):
        seen = []
        original = server.BOOK.on_change
        self.addCleanup(setattr, server.BOOK, "on_change", original)
        server.BOOK.on_change = lambda *args: seen.append(args)
        person = self.add("Ann", birthday=BIRTHDAY)
        server.BOOK.update(person, {"phone": "555"})
        server.BOOK.remove(person)
        self.add("Bob")
        server.BOOK.clear()
        self.assertEqual([args[0] for args in seen], ["add", "update", "remove", "add", "clear"])
        self.assertEqual(seen[0][2]["name"], "Ann")
        self.assertEqual((seen[2][2], seen[4][1], seen[4][2]), (None, None, None))

        def broken(*args):
            raise RuntimeError("no")

        server.BOOK.on_change = broken
        self.assertTrue(self.add("Cal"))


class BookDates(Book):
    def test_a_birthday_makes_the_row(self):
        person = self.add("Sarah Whitfield", relationship="daughter", birthday=BIRTHDAY)
        self.assertEqual(self.rows("SELECT memory_id, month, day, who, relation, what, source, person_id FROM dates"),
                         [(0, 3, 14, "Sarah Whitfield", "daughter", "birthday", "book", person)])

    def test_a_birthday_with_a_year(self):
        person = self.add("Ruth", birthday="1950-03-14")
        self.assertEqual([row[1:] for row in self.book_row(person)], [(3, 14)])

    def test_no_birthday_no_row(self):
        self.add("Ruth")
        self.assertEqual(self.rows("SELECT * FROM dates"), [])

    def test_it_reaches_the_reminder(self):
        self.add("Sarah Whitfield", relationship="daughter", birthday=BIRTHDAY)
        due = self.store.due(TODAY)
        self.assertEqual([(d["who"], d["days"], d["label"]) for d in due],
                         [("Sarah Whitfield", 6, "Sarah Whitfield's birthday, March 14")])

    def test_a_change_moves_it_and_its_marks_stay(self):
        person = self.add("Ruth", birthday=BIRTHDAY)
        date_id = self.book_row(person)[0][0]
        self.store.mark_done(date_id, 2027)
        self.store.note_sent([{"id": date_id, "on": date(2028, 3, 14), "also": []}])
        server.BOOK.update(person, {"birthday": "04-02"})
        self.assertEqual(self.book_row(person), [(date_id, 4, 2)])
        self.assertEqual(self.rows("SELECT date_id FROM date_done"), [(date_id,)])
        self.assertEqual(self.rows("SELECT date_id FROM date_sent"), [(date_id,)])

    def test_a_new_name_and_relationship_follow(self):
        person = self.add("Ruth", birthday=BIRTHDAY)
        server.BOOK.update(person, {"name": "Ruth Ann", "relationship": "Sister"})
        self.assertEqual(self.rows("SELECT who, relation FROM dates"), [("Ruth Ann", "sister")])

    def clears(self, change):
        person = self.add("Ruth Ann", birthday=BIRTHDAY)
        date_id = self.book_row(person)[0][0]
        self.store.mark_done(date_id, 2027)
        self.store.note_sent([{"id": date_id, "on": date(2028, 3, 14), "also": []}])
        self.store.stop_reminders("Ruth Ann")
        change(person)
        for table in ("dates", "date_done", "date_sent", "no_reminders"):
            self.assertEqual(self.rows(f"SELECT * FROM {table}"), [], table)

    def test_clearing_the_birthday_removes_it_all(self):
        self.clears(lambda person: server.BOOK.update(person, {"birthday": ""}))

    def test_removing_the_person_removes_it_all(self):
        self.clears(server.BOOK.remove)

    def test_the_same_day_in_talk_is_one_reminder(self):
        self.add("Sarah Whitfield", relationship="daughter", birthday=BIRTHDAY)
        fact = self.store.add("My daughter Sarah's birthday is March 14")
        self.store.learn_date(talk_date("Sarah", 3, 14, relation="daughter"), fact)
        self.store.learn_date(talk_date("Sarah Whitfield", 3, 14))
        self.assertEqual(len(self.rows("SELECT * FROM dates")), 1)
        self.assertEqual(len(self.store.due(TODAY)), 1)
        self.assertIsNotNone(self.store.text_of(fact))  # the memory still saves

    def test_a_date_said_first_joins_the_card(self):
        fact = self.store.add("Sarah's birthday is June 1")
        date_id = self.store.learn_date(talk_date("Sarah", 6, 1), fact)
        self.store.mark_done(date_id, 2027)
        person = self.add("Sarah Whitfield", birthday=BIRTHDAY)
        self.assertEqual(self.rows("SELECT who, month, day, source FROM dates"), [("Sarah Whitfield", 3, 14, "book")])
        self.assertEqual(self.rows("SELECT date_id FROM date_done"), self.rows("SELECT id FROM dates"))
        self.assertIn("March 14", self.store.text_of(fact))
        self.assertEqual(self.person(person)["birthday"], BIRTHDAY)

    def test_a_day_said_differently_corrects_the_card(self):
        person = self.add("Ruth", birthday="1950-03-14")
        calls = []
        original = server.BOOK.on_change
        self.addCleanup(setattr, server.BOOK, "on_change", original)
        server.BOOK.on_change = lambda *args: (calls.append(args[0]), original(*args))
        fact = self.store.add("Ruth's birthday is April 2")
        date_id = self.book_row(person)[0][0]
        self.assertEqual(self.store.learn_date(talk_date("Ruth", 4, 2), fact), date_id)
        self.assertEqual(self.book_row(person), [(date_id, 4, 2)])
        self.assertEqual(self.person(person)["birthday"], "1950-04-02")  # the year stays
        self.assertEqual(calls, ["update"])  # once: it doesn't go round again
        self.assertEqual(len(self.rows("SELECT * FROM dates")), 1)
        self.assertIsNotNone(self.store.text_of(fact))

    def test_a_correction_in_talk_reaches_the_card(self):
        person = self.add("Ruth", birthday=BIRTHDAY)
        date_id = self.store.correct_last("no, it's the 9th", ["Ruth's birthday is March 14"])
        self.assertEqual(date_id, self.book_row(person)[0][0])
        self.assertEqual(self.person(person)["birthday"], "03-09")

    def test_a_locked_book_acts_as_it_always_did(self):
        person = self.add("Ruth Ann", birthday=BIRTHDAY)
        before = self.book_row(person)

        class Locked:
            @staticmethod
            def find(words):
                raise server.address_book.BookLocked()

        with mock.patch.object(memory_core, "BOOK_LINK", Locked):
            self.store.learn_date(talk_date("Ruth", 4, 2))
        self.assertEqual(self.book_row(person), before)
        self.assertEqual(self.rows("SELECT who, source FROM dates ORDER BY id"), [("Ruth Ann", "book"), ("Ruth", "")])
        self.assertEqual(self.person(person)["birthday"], BIRTHDAY)

    def test_someone_else_by_that_name_is_not_merged(self):
        self.add("Mark Hollis", relationship="son", birthday=BIRTHDAY)
        self.store.learn_date(talk_date("Mark", 6, 1, relation="brother"))
        self.assertEqual(self.rows("SELECT who, month FROM dates ORDER BY id"), [("Mark Hollis", 3), ("Mark", 6)])

    def test_another_surname_is_not_merged(self):
        self.add("Sarah Beck", birthday=BIRTHDAY)
        self.store.learn_date(talk_date("Sarah Whitfield", 6, 1))
        self.assertEqual(len(self.rows("SELECT * FROM dates")), 2)

    def test_two_of_a_first_name_merge_only_on_the_same_day(self):
        self.add("Sarah Beck", birthday=BIRTHDAY)
        self.add("Sarah Whitfield", birthday="06-01")
        self.store.learn_date(talk_date("Sarah", 6, 1))
        self.assertEqual(len(self.rows("SELECT * FROM dates")), 2)
        self.store.learn_date(talk_date("Sarah", 9, 9))
        self.assertEqual(len(self.rows("SELECT * FROM dates")), 3)
        self.assertEqual(self.rows("SELECT month FROM dates WHERE source = 'book' ORDER BY month"), [(3,), (6,)])

    def test_going_quiet_still_applies_and_the_card_stays(self):
        person = self.add("Mark Hollis", relationship="son", birthday=BIRTHDAY)
        said = "Mark died last spring"
        self.assertTrue(memory_dates.passed(said))
        self.store.add(said)
        self.assertEqual(self.store.due(TODAY), [])
        self.assertEqual(self.person(person)["birthday"], BIRTHDAY)
        self.assertEqual(len(self.book_row(person)), 1)

    def test_memory_id_0_is_safe_in_every_reader(self):
        person = self.add("Ruth", birthday=BIRTHDAY)
        fact = self.store.add("I like tomato soup")
        self.store.add("Her dog is Bo")
        date_id = self.book_row(person)[0][0]
        self.assertEqual(self.store.date_of(0), "")
        self.assertEqual(self.store.date_of(fact), "")
        self.assertEqual({m["saved_date"] for m in self.store.active_public()}, {""})
        self.assertIsNone(self.store.text_of(0))
        self.assertFalse(self.store.remove(0))
        self.assertTrue(self.store.remove(fact))
        with closing(server.connect_memories()) as conn, conn:
            row = next(r for r in memory_core._date_rows(conn) if r["id"] == date_id)
            self.assertFalse(memory_core._let_go(conn, row))
            memory_core._move(conn, row, 3, 15)
            memory_core._delete(conn, [0])
        self.assertEqual(self.book_row(person), [(date_id, 3, 15)])
        self.assertEqual(self.store.forget(""), ["Her dog is Bo"])
        self.assertEqual(self.book_row(person), [(date_id, 3, 15)])

    def test_forgetting_a_memory_of_the_day_leaves_the_book_date(self):
        person = self.add("Ruth", birthday=BIRTHDAY)
        fact = self.store.add("Ruth's birthday is March 14")
        self.store.learn_date(talk_date("Ruth", 3, 14), fact)
        self.store.remove(fact)
        self.assertEqual(len(self.book_row(person)), 1)

    def test_an_older_file_gains_the_columns(self):
        with tempfile.TemporaryDirectory(dir=helpers.TMP) as folder:
            with closing(sqlite3.connect(Path(folder) / "old.db")) as conn:
                conn.execute("CREATE TABLE dates (id INTEGER PRIMARY KEY, memory_id INTEGER NOT NULL, created_at TEXT, "
                             "month INTEGER, day INTEGER, who TEXT, relation TEXT, what TEXT)")
                conn.execute("INSERT INTO dates (memory_id, month, day, who, relation, what) "
                             "VALUES (4, 1, 2, 'Ann', '', 'birthday')")
                memory_core.upgrade_dates(conn)
                memory_core.upgrade_dates(conn)  # twice is fine
                self.assertEqual(memory_core._date_rows(conn)[0]["source"], "")
                self.assertEqual(memory_core._date_rows(conn)[0]["person_id"], "")

    def test_each_start_catches_up(self):
        self.addCleanup(setattr, server.BOOK, "on_change", server.BOOK.on_change)
        hooked, server.BOOK.on_change = server.BOOK.on_change, None
        person = self.add("Ruth", birthday=BIRTHDAY)
        server.sync_book_dates()
        self.assertEqual(len(self.book_row(person)), 1)
        server.BOOK.remove(person)
        server.BOOK.on_change = hooked
        server.sync_book_dates()
        self.assertEqual(self.book_row(person), [])


class ClearBook(Book):
    def test_it_clears_book_dates_only(self):
        self.add("Ruth", birthday=BIRTHDAY)
        self.add("Sam", birthday="06-01")
        fact = self.store.add("Tom's birthday is May 2")
        self.store.learn_date(talk_date("Tom", 5, 2), fact)
        self.assertEqual(server.clear_book(), 2)
        self.assertEqual(server.BOOK.count(), 0)
        self.assertEqual(self.rows("SELECT who, source FROM dates"), [("Tom", "")])
        self.assertEqual(self.store.text_of(fact), "Tom's birthday is May 2")


class FullReach(Book):
    def fill(self):
        """Sarah Whitfield, the only Sarah, with something in every place she can be."""
        self.sarah = self.add("Sarah Whitfield", relationship="daughter", email=ADDRESS, birthday=BIRTHDAY,
                              address="12 Oak Street")
        self.other = self.add("Tom Reed", relationship="son", email="tom@example.com", birthday="06-01")
        self.date_id = self.book_row(self.sarah)[0][0]
        self.store.mark_done(self.date_id, 2027)
        self.store.note_sent([{"id": self.date_id, "on": date(2028, 3, 14), "also": []}])
        self.store.stop_reminders("Sarah")
        self.store.stop_reminders("Sarah Whitfield")
        self.store.stop_reminders("daughter")
        self.store.stop_reminders("Tom")
        self.store.add("Sarah loves lilies")
        self.store.add("Sarah Whitfield lives in Durham")
        self.store.add("My daughter plays the piano")
        self.store.add("I like tomato soup")
        self.store.add("Tom Reed fishes on Sundays")
        self.store.learn_date(talk_date("Sarah", 5, 2, what="anniversary"), self.store.add("Sarah got married on May 2"))
        self.store.learn_date(talk_date("daughter", 7, 7, what="graduation", relation="daughter"))
        memory = server.mary_memory()
        memory.add_turn("user", "Sarah phoned me yesterday")
        memory.add_turn("model", "That sounds nice.")
        memory.add_turn("user", "My daughter came by today")
        memory.add_turn("model", "How lovely.")
        memory.add_turn("user", "Is it nice out?")
        memory.save()

    def memories(self):
        return json.dumps([m["text"] for m in self.store.active()])

    def test_every_place_she_was(self):
        self.fill()
        self.full_send("Sarah Whitfield")
        self.ready("Sarah Whitfield", saved=False)  # a waiting look
        self.assertIn("held", self.ctx.state)
        self.assertEqual(self.tool("Sarah Whitfield")["needs_yes"], True)
        self.assertIsNotNone(self.person(self.sarah))  # nothing goes before the yes
        self.assertEqual(self.tool("Sarah Whitfield", confirmed=True)["forgotten"] > 0, True)

        self.assertIsNone(self.person(self.sarah))
        with closing(sqlite3.connect(server.BOOK.backup_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM people").fetchone()[0], 1)
        self.assertEqual(self.rows("SELECT who FROM dates"), [("Tom Reed",)])
        self.assertEqual(self.rows("SELECT * FROM date_done"), [])
        self.assertEqual(self.rows("SELECT * FROM date_sent"), [])
        self.assertEqual(self.rows("SELECT who FROM no_reminders"), [("tom",)])
        for text in ("Sarah", "daughter", "Durham", "piano", "lilies"):
            self.assertNotIn(text, self.memories())
        self.assertIn("tomato soup", self.memories())
        self.assertIn("Tom Reed", self.memories())
        recent = [turn["text"] for turn in server.mary_memory().recent]
        self.assertFalse([text for text in recent if "Sarah" in text or "daughter" in text], recent)
        self.assertIn("Is it nice out?", recent)
        self.assertNotIn(mail_core.address_mark(ADDRESS), [row["to"] for row in self.log_rows()])
        self.assertNotIn("held", self.ctx.state)
        self.assertNotIn(ADDRESS, self.everywhere())

    def test_by_first_name_and_by_relationship(self):
        for about in ("Sarah", "my daughter"):
            with self.subTest(about):
                helpers.reset_db()
                self.fill()
                self.forget(about)
                self.assertIsNone(self.person(self.sarah))
                self.assertNotIn("Sarah", self.memories())
                self.assertIn("Tom Reed", self.memories())

    def test_a_person_with_no_card_details_still_takes_their_memories(self):
        self.add("Sarah Whitfield")
        self.store.add("Sarah loves lilies")
        self.forget("Sarah Whitfield")
        self.assertEqual(self.store.active(), [])

    def test_their_own_name_forget_reaches_too(self):
        person = self.add("Ruth Ann", relationship="sister", birthday=BIRTHDAY)
        self.store.add("Ruth likes tea")
        self.assertTrue(self.store.forget_name("Ruth Ann"))
        self.assertIsNone(self.person(person))
        self.assertEqual(self.store.active(), [])
        self.assertEqual(self.rows("SELECT * FROM dates"), [])

    def test_another_sarah_survives(self):
        whitfield = self.add("Sarah Whitfield", relationship="daughter", birthday=BIRTHDAY)
        beck = self.add("Sarah Beck", relationship="friend", birthday="06-01")
        self.store.add("Sarah Beck bakes pies")
        self.store.add("Sarah loves lilies")  # either one: it stays
        self.store.add("Sarah Whitfield lives in Durham")
        self.store.learn_date(talk_date("Sarah", 9, 9, what="anniversary"))
        self.store.stop_reminders("Sarah")
        self.forget("Sarah Whitfield")
        self.assertIsNone(self.person(whitfield))
        self.assertEqual(self.person(beck)["name"], "Sarah Beck")
        self.assertEqual(len(self.book_row(beck)), 1)
        self.assertEqual(self.rows("SELECT who FROM no_reminders"), [("sarah",)])
        self.assertIn("Sarah Beck bakes pies", self.memories())
        self.assertIn("Sarah loves lilies", self.memories())
        self.assertNotIn("Durham", self.memories())
        self.assertEqual(self.rows("SELECT who, what FROM dates ORDER BY id"),
                         [("Sarah Beck", "birthday"), ("Sarah", "anniversary")])

    def test_a_shared_relationship_is_left_alone(self):
        self.add("Mark Hollis", relationship="son")
        self.add("Tom Reed", relationship="son")
        self.store.add("My son plays guitar")
        self.forget("Mark Hollis")
        self.assertIn("guitar", self.memories())

    def test_incidents_and_saved_cards_stay(self):
        self.fill()
        status, made, _ = helpers.api("POST", "/api/incidents", helpers.incident(description="Sarah Whitfield saw the tray left."))
        self.assertIn(status, (200, 201), made)
        self.ctx.store.put("saved-card1", {"id": "card1", "person": "Sarah Whitfield"})
        self.forget("Sarah Whitfield")
        status, listed, _ = helpers.api("GET", "/api/incidents")
        self.assertIn("Sarah Whitfield saw the tray left.", json.dumps(listed))
        self.assertEqual(self.ctx.store.get("saved-card1")["person"], "Sarah Whitfield")

    def test_forget_everything_leaves_the_book_and_its_reminders(self):
        self.fill()
        self.forget("everything")
        self.assertEqual(self.store.active(), [])
        self.assertEqual(server.BOOK.count(), 2)
        self.assertEqual(self.rows("SELECT source FROM dates"), [("book",), ("book",)])
        self.assertEqual(self.rows("SELECT date_id FROM date_done"), [(self.date_id,)])
        self.assertEqual(self.rows("SELECT * FROM no_reminders"), [])
        self.assertEqual([d["who"] for d in self.store.due(date(2028, 5, 25))], ["Tom Reed"])
        self.assertEqual([d["who"] for d in self.store.due(TODAY)], [])  # raised in 2027 already
        self.assertEqual([d["who"] for d in self.store.due(date(2029, 3, 8))], ["Sarah Whitfield"])


class AddressForms(Book):
    def fill(self):
        return self.add("Mark Hollis", relationship="son", email=ADDRESS, address="12 Oak Street", phone="555")

    def left(self, person):
        return self.person(person)["email"], self.person(person)["address"], self.person(person)["no_keep"]

    def test_email_is_the_email(self):
        for about in ("Mark's email", "Mark's e-mail", "the email for Mark"):
            with self.subTest(about):
                helpers.reset_db()
                person = self.fill()
                self.forget(about)
                self.assertEqual(self.left(person), ("", "12 Oak Street", True))

    def test_the_mailing_words_are_the_mailing_address(self):
        for about in ("Mark's mailing address", "Mark's street address", "Mark's home address"):
            with self.subTest(about):
                helpers.reset_db()
                person = self.fill()
                self.forget(about)
                self.assertEqual(self.left(person), (ADDRESS, "", False))
                self.assertEqual(self.person(person)["phone"], "555")

    def test_the_rolling_copy_loses_it(self):
        person = self.fill()
        server.BOOK.backup(fresh=True)
        before = server.BOOK.backup_path.read_bytes()
        self.forget("Mark's mailing address")
        self.assertNotEqual(server.BOOK.backup_path.read_bytes(), before)
        self.assertEqual(self.left(person)[1], "")

    def test_bare_address_with_both_asks_and_removes_nothing(self):
        person = self.fill()
        out = self.tool("Mark's address")
        self.assertTrue(out["needs_which"])
        self.assertNotIn("needs_yes", out)
        self.assertIn(ASK_FIELD, out["note"])
        self.assertEqual(self.left(person), (ADDRESS, "12 Oak Street", False))
        self.assertEqual(self.ctx.people.forget("Nobody"), {"addresses": [], "texts": []})
        self.assertEqual(self.mod.on_forget(self.ctx, "Mark's address"), {"addresses": [], "texts": []})
        self.assertEqual(self.left(person), (ADDRESS, "12 Oak Street", False))

    def test_a_yes_is_no_answer_to_which_one(self):
        person = self.fill()
        self.tool("Mark's address")
        out = self.tool("Mark's address", confirmed=True)
        self.assertTrue(out["needs_which"])
        self.assertEqual(self.left(person), (ADDRESS, "12 Oak Street", False))

    def test_their_answer_runs_it_in_live(self):
        person = self.fill()
        self.tool("Mark's address")
        self.assertGreater(self.tool("the email")["forgotten"], 0)
        self.assertEqual(self.left(person), ("", "12 Oak Street", True))
        self.assertIsNone(server.mary_memory().pending_forget)

    def test_their_answer_runs_it_in_normal_talk(self):
        person = self.fill()
        self.tool("Mark's address")
        out = self.talk("the mailing address")
        self.assertEqual(self.left(person), (ADDRESS, "", False))
        self.assertEqual(self.gemini.calls if hasattr(self.gemini, "calls") else [], [])
        self.assertIsNone(server.mary_memory().pending_forget, out)

    def test_both_takes_both(self):
        person = self.fill()
        self.tool("Mark's address")
        self.tool("both of them")
        self.assertEqual(self.left(person), ("", "", True))

    def test_a_forget_of_someone_else_doesnt_answer_for_him(self):
        person = self.fill()
        tom = self.add("Tom Reed", email="tom@example.com")
        self.tool("Mark's address")
        self.tool("Tom's email")
        self.assertEqual(self.left(person), (ADDRESS, "12 Oak Street", False))
        self.assertEqual(self.person(tom)["email"], "tom@example.com")

    def test_only_one_filled_takes_that_one(self):
        email = self.add("Mark Hollis", email=ADDRESS)
        mailing = self.add("Tom Reed", address="9 Elm Road")
        self.forget("Mark's address")
        self.forget("Tom's address")
        self.assertEqual(self.left(email), ("", "", True))
        self.assertEqual(self.left(mailing), ("", "", False))

    def test_offline_asks_the_same(self):
        person = self.fill()
        memory = server.mary_memory()
        self.assertEqual(mary.offline_memory(memory, "forget about my son's address"), ASK_FIELD)
        self.assertEqual(memory.pending_forget["field"], "Mark Hollis")
        self.assertEqual(self.left(person), (ADDRESS, "12 Oak Street", False))


class HerAsking(Book):
    def test_her_words(self):
        line = mary.forget_line
        self.assertEqual(line({"person": "Sarah Beck", "relationship": "daughter"}), ASK_SARAH)
        self.assertEqual(line({"person": "Mark Hollis", "relationship": "son"}),
                         "Forget Mark Hollis? His address, his birthday reminders and what I remember about him all go for good.")
        for relationship in ("friend", "", "neighbor", "cousin"):
            self.assertEqual(line({"person": "Pat", "relationship": relationship}),
                             "Forget Pat? Their address, their birthday reminders and what I remember about them all go for good.")

    def test_each_word_settles_it(self):
        for word in "daughter wife mother sister aunt niece granddaughter".split():
            self.assertIn("Her address", mary.forget_line({"person": "Pat", "relationship": word}), word)
        for word in "son husband father brother uncle nephew grandson".split():
            self.assertIn("His address", mary.forget_line({"person": "Pat", "relationship": word}), word)

    def test_the_full_name_from_a_first_name(self):
        self.add("Sarah Beck", relationship="daughter")
        out = self.tool("Sarah")
        self.assertTrue(out["needs_yes"])
        self.assertIn(ASK_SARAH, out["note"])

    def test_something_else_keeps_the_old_question(self):
        self.store.add("My son's job is at the mill")
        self.assertEqual(self.tool("my son's job")["note"], mary.FORGET_ASK_NOTE)

    def test_two_people_she_asks_which_and_nothing_goes(self):
        first = self.add("Sarah Beck", email=ADDRESS)
        second = self.add("Sarah Whitfield", email="other@example.com")
        self.store.add("Sarah loves lilies")
        out = self.tool("Sarah")
        self.assertTrue(out["needs_which"])
        self.assertIn("Sarah Beck or Sarah Whitfield", out["note"])
        self.assertIsNone(server.mary_memory().pending_forget)
        out = self.tool("Sarah", confirmed=True)  # no yes was asked for
        self.assertTrue(out["needs_which"])
        self.assertEqual(self.mod.on_forget(self.ctx, "Sarah"), {"addresses": [], "texts": []})
        self.assertIsNotNone(self.person(first))
        self.assertIsNotNone(self.person(second))
        self.assertEqual(len(self.store.active()), 1)

    def test_offline_says_the_same_line(self):
        self.add("Sarah Beck", relationship="daughter")
        memory = server.mary_memory()
        self.assertEqual(mary.offline_memory(memory, "forget about my daughter"), ASK_SARAH)
        self.assertTrue(memory.pending_forget)


if __name__ == "__main__":
    unittest.main()
