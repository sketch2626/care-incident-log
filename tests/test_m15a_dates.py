from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M15a piece 1: the offline date parser and the store of family dates. Nothing here reaches Gemini."""
import os
import unittest
from contextlib import closing
from datetime import date
from unittest import mock

import mary
import memory_core
import memory_dates as md
import server
import voices
from tests.test_voices import KEY, Net, Resp


def one(text, **kw):
    found = md.parse(text, **kw)
    assert len(found) == 1, (text, found)
    return found[0]


class Parse(unittest.TestCase):
    def test_reads(self):
        cases = [  # text, month, day, who, relation, what
            ("Mark's birthday is November 7th", 11, 7, "Mark", "", "birthday"),
            ("my anniversary is June 3rd", 6, 3, "", "", "anniversary"),
            ("my granddaughter Lily turns ten on the 12th of March", 3, 12, "Lily", "granddaughter", "birthday"),
            ("Mark's birthday is November seventh", 11, 7, "Mark", "", "birthday"),
            ("Mark's birthday is November the seventh", 11, 7, "Mark", "", "birthday"),
            ("Mark's birthday is the 7th of November", 11, 7, "Mark", "", "birthday"),
            ("Mark's birthday is the seventh of November", 11, 7, "Mark", "", "birthday"),
            ("Mark's birthday is Nov. 7", 11, 7, "Mark", "", "birthday"),
            ("Mark's birthday is 11/7", 11, 7, "Mark", "", "birthday"),
            ("Mark's birthday is 11/7/1950", 11, 7, "Mark", "", "birthday"),
            ("Mark's birthday is 11-7", 11, 7, "Mark", "", "birthday"),
            ("Mark's birthday is June twenty-first", 6, 21, "Mark", "", "birthday"),
            ("Mark's birthday is June twenty first", 6, 21, "Mark", "", "birthday"),
            ("Mark's birthday is March thirty first", 3, 31, "Mark", "", "birthday"),
            ("Mark's birthday is November 7th, 1952", 11, 7, "Mark", "", "birthday"),
            ("November 7 is Mark's birthday", 11, 7, "Mark", "", "birthday"),
            ("November 7, 1952 is Mark's birthday", 11, 7, "Mark", "", "birthday"),
            ("Mark was born on March 3rd", 3, 3, "Mark", "", "birthday"),
            ("my son Mark's birthday is November 7", 11, 7, "Mark", "son", "birthday"),
            ("my son's birthday is November 7", 11, 7, "son", "son", "birthday"),
            ("Mark and Sue's anniversary is June 3", 6, 3, "Mark and Sue", "", "anniversary"),
            ("our wedding anniversary is June 3", 6, 3, "", "", "anniversary"),
            ("mark's birthday is november 7th", 11, 7, "Mark", "", "birthday"),
            ("His son Mark's birthday is November 7", 11, 7, "Mark", "son", "birthday"),
            ("Mark’s birthday is November 7", 11, 7, "Mark", "", "birthday"),
            ("Mark's birthday is February 29", 2, 29, "Mark", "", "birthday"),
            ("Mary Ann's birthday is May 2", 5, 2, "Mary Ann", "", "birthday"),
            ("my son in law's birthday is May 2", 5, 2, "son-in-law", "son-in-law", "birthday"),
            ("Remember Mark's birthday is May 2", 5, 2, "Mark", "", "birthday"),
            ("Don't forget, it's Mark's birthday on May 2", 5, 2, "Mark", "", "birthday"),
            ("november seven is mark's birthday", 11, 7, "Mark", "", "birthday"),
            ("Bob, and Sue's anniversary is June 3", 6, 3, "Sue", "", "anniversary"),
        ]
        for text, month, day, who, relation, what in cases:
            with self.subTest(text):
                hit = one(text)
                self.assertEqual((hit["month"], hit["day"], hit["who"], hit["relation"], hit["what"]),
                                 (month, day, who, relation, what))

    def test_two_in_a_line(self):
        for text in ("Mark's birthday is November 7 and Lily's is March 12",
                     "Mark's birthday is November 7 and Lily's birthday is March 12",
                     "November 7 is Mark's birthday and March 12 is Lily's birthday",
                     "November 7 is Mark's birthday, March 12 is Lily's",
                     "Mark's birthday is November 7. Lily's is March 12."):
            with self.subTest(text):
                self.assertEqual([(f["who"], f["month"], f["day"]) for f in md.parse(text)],
                                 [("Mark", 11, 7), ("Lily", 3, 12)])

    def test_span_fits_the_words(self):
        text = "Mark’s birthday is the 7th of November, 1952"
        start, end = one(text)["span"]
        self.assertEqual(text[start:end], "the 7th of November")

    def test_nothing(self):
        for text in ("Mark's birthday is November 31", "Mark's birthday is Feb 30", "Mark's birthday is the 12th",
                     "Mark's birthday is next Tuesday", "Mark's birthday is today", "Mark's birthday is next week",
                     "Is Mark's birthday November 7?", "Mark's birthday is November 7, right?",
                     "Mark's birthday is November 7. Right?",
                     "I don't remember if Mark's birthday is November 7", "Mark's birthday isn't November 7",
                     "I'm not sure, Mark's birthday is November 7", "Mark's birthday, is it November 7",
                     "Maybe Mark's birthday is November 7", "I can't recall, Mark's birthday is November 7",
                     "I forgot, Mark's birthday is November 7", "my birthday is November 7",
                     "her birthday is November 7",
                     "his birthday is November 7", "their birthday is November 7", "was born on March 3rd",
                     "I was born on March 3rd", "He was born on March 3rd", "the church's anniversary is June 3",
                     "the company's anniversary is June 3", "the store's anniversary is June 3",
                     "our church's anniversary is June 3", "the anniversary of the war is June 3",
                     "June 3 is the anniversary of the war", "3/4", "Mark's birthday party is November 7",
                     "Mark was born in November 1952",
                     "Mark was born in November nineteen fifty two", "Mark's birthday is November 7-9",
                     "Mark's birthday is not November 7", "Bob's death anniversary is June 3"):
            with self.subTest(text):
                self.assertEqual(md.parse(text), [])

    def test_self_name(self):
        for name in ("Andy", "andy", "ANDY", "Andy Smith"):
            self.assertEqual(md.parse("Andy's birthday is June 3", self_name=name), [])
        self.assertEqual(one("Andy's birthday is June 3", self_name="Mark")["who"], "Andy")
        self.assertEqual(one("my son Andy's birthday is June 3", self_name="Andy")["who"], "Andy")

    def test_loose_dates(self):
        self.assertEqual(md.loose_dates("the seventh of November and Nov. 8, also June twenty first"),
                         {(11, 7), (11, 8), (6, 21)})
        self.assertEqual(md.loose_dates("3/4 of a cup"), set())
        self.assertEqual(md.loose_dates("his birthday is 3/4"), {(3, 4)})
        self.assertEqual(md.loose_dates("November 31"), set())

    def test_loose_day_and_correction(self):
        for text, day in (("no, it's the 9th", 9), ("actually the ninth", 9), ("no the twenty first", 21),
                          ("no, the 9th, not the 7th", 9), ("no, not the 7th, the 9th", 9), ("it's 9", 9),
                          ("no one came", None), ("no, 9 o'clock", None), ("no, the first one", None),
                          ("no, 9:30", None), ("is it the 9th?", None), ("maybe the 9th", None), ("11/9", None)):
            with self.subTest(text):
                self.assertEqual(md.loose_day(text), day)
        for text in ("no, it's the 9th", "Nope", "actually the ninth", "wait", "sorry, the 9th", "I mean the 9th",
                     "it's the 9th", "that's wrong"):
            self.assertTrue(md.is_correction(text), text)
        self.assertFalse(md.is_correction("Mark came by"))
        self.assertFalse(md.is_correction("no " + "word " * 10))

    def test_passed(self):
        for text, names in (("my late husband", ["husband"]), ("my late husband Bob", ["husband", "bob"]),
                            ("Mark passed in 2019", ["mark"]), ("Mark passed away", ["mark"]),
                            ("since Ruth died", ["ruth"]), ("my son died", ["son"]), ("we lost Ruth", ["ruth"]),
                            ("lost my wife", ["wife"]), ("Ruth is in heaven", ["ruth"]), ("Ruth's in heaven", ["ruth"]),
                            ("buried my husband", ["husband"]), ("Bob went to be with the Lord", ["bob"]),
                            ("I am a widow", ["husband"]), ("he is a widower", ["wife"]),
                            ("she was widowed young", ["husband", "wife"]), ("Mark's wife died", ["wife"]),
                            ("lost Mark's wife", ["wife"]), ("my son Mark passed away", ["son", "mark"]),
                            ("Beth died", ["beth"]), ("Ruth's with the Lord now", ["ruth"]), ("he passed away", []),
                            ("Mark passed his test", []), ("Mark passed the salt", []), ("I almost died", []),
                            ("Mark nearly died", []), ("Mark didn't die", []), ("Mark could have died", []),
                            ("the battery died", []), ("I lost my keys", []), ("I was late", [])):
            with self.subTest(text):
                self.assertEqual(md.passed(text), names)

    def test_stop_request(self):
        for text, want in (("don't remind me about him", ("stop", "")),
                           ("don't remind me about Mark", ("stop", "Mark")),
                           ("stop reminding me about my sister", ("stop", "sister")),
                           ("don't bring up Mark's birthday again", ("stop", "Mark")),
                           ("no more reminders about Ruth", ("stop", "Ruth")),
                           ("go ahead and remind me about Mark again", ("remind", "Mark")),
                           ("you can remind me about Mark", ("remind", "Mark")),
                           ("please stop reminding me about my anniversary", ("stop", "anniversary")),
                           ("don't remind me to take my pills", None), ("Mark came by", None),
                           ("don't mention it", None), ("don't bring up the rent", None)):
            with self.subTest(text):
                self.assertEqual(md.stop_request(text), want)

    def test_label(self):
        when = {"month": 11, "day": 7, "what": "birthday"}
        self.assertEqual(md.label({**when, "who": "Mark", "relation": ""}), "Mark's birthday, November 7")
        self.assertEqual(md.label({**when, "who": "son", "relation": "son"}), "Your son's birthday, November 7")
        self.assertEqual(md.label({"month": 6, "day": 3, "what": "anniversary", "who": "", "relation": ""}),
                         "Your anniversary, June 3")
        self.assertEqual(md.label({"month": 6, "day": 3, "what": "anniversary", "who": "Mark and Sue", "relation": ""}),
                         "Mark and Sue's anniversary, June 3")

    def test_next_date(self):
        self.assertEqual(md.next_date(11, 7, date(2026, 11, 7)), date(2026, 11, 7))
        self.assertEqual(md.next_date(11, 7, date(2026, 11, 8)), date(2027, 11, 7))
        self.assertEqual(md.next_date(2, 29, date(2027, 1, 1)), date(2027, 2, 28))
        self.assertEqual(md.next_date(2, 29, date(2028, 1, 1)), date(2028, 2, 29))


class Store(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        with closing(server.connect_memories()) as conn, conn:
            for table in ("dates", "date_done", "no_reminders"):
                conn.execute(f"DELETE FROM {table}")
        self.changes = []
        self.store = memory_core.MemoryStore(server.connect_memories, on_change=self.changes.append)
        self.day = date(2026, 10, 31)
        learned = mock.patch.object(memory_core, "_today", return_value=date(2026, 1, 1))  # so nothing was told "today"
        learned.start()
        self.addCleanup(learned.stop)

    def rows(self, sql):
        with closing(server.connect_memories()) as conn:
            return [tuple(row) for row in conn.execute(sql).fetchall()]

    def learn(self, text, memory_id=None):
        return self.store.learn_date(one(text), memory_id)

    def test_auto_row_and_remove(self):
        date_id = self.learn("Mark's birthday is November 7")
        memory = self.rows("SELECT id, text, kind, source FROM memories")
        self.assertEqual(memory[0][1:], ("Mark's birthday, November 7", "family", "said"))
        self.assertEqual(self.store.date_of(memory[0][0]), "Mark's birthday, November 7")
        self.store.mark_done(date_id, 2026)
        self.assertTrue(self.store.remove(memory[0][0]))
        self.assertEqual(self.rows("SELECT * FROM dates") + self.rows("SELECT * FROM date_done"), [])

    def test_public_stays_plain(self):
        self.learn("Mark's birthday is November 7")
        self.store.add("Likes fishing")
        by_text = {m["text"]: m for m in self.store.active_public()}
        self.assertEqual(by_text["Mark's birthday, November 7"]["saved_date"], "Mark's birthday, November 7")
        self.assertEqual(by_text["Likes fishing"]["saved_date"], "")
        self.assertNotIn("saved_date", self.store.recall("fishing")[0])

    def test_same_date_takes_over_an_auto_row(self):
        date_id = self.learn("Mark's birthday is November 7")
        fact = self.store.add("His son Mark's birthday is November 7")
        self.assertEqual(self.learn("His son Mark's birthday is November 7", fact), date_id)
        self.assertEqual(self.rows("SELECT text FROM memories"), [("His son Mark's birthday is November 7",)])
        self.assertEqual(self.rows("SELECT memory_id, relation FROM dates"), [(fact, "son")])

    def test_same_date_leaves_a_real_memory(self):
        first = self.store.add("Mark's birthday is November 7")
        date_id = self.learn("Mark's birthday is November 7", first)
        second = self.store.add("Mark was born November 7")
        self.assertEqual(self.learn("Mark was born November 7", second), date_id)
        self.assertEqual(self.rows("SELECT memory_id FROM dates"), [(first,)])
        self.assertEqual(self.store.count(), 2)

    def test_correction_keeps_done_and_drops_the_old_memory(self):
        first = self.store.add("Mark's birthday is November 7")
        date_id = self.learn("Mark's birthday is November 7", first)
        self.store.mark_done(date_id, 2026)
        fact = self.store.add("Mark's birthday is November 9")
        self.assertEqual(self.learn("Mark's birthday is November 9", fact), date_id)
        self.assertEqual(self.rows("SELECT text FROM memories"), [("Mark's birthday is November 9",)])
        self.assertEqual(self.rows("SELECT memory_id, month, day FROM dates"), [(fact, 11, 9)])
        self.assertEqual(len(self.rows("SELECT * FROM date_done")), 1)
        self.assertIn(True, self.changes)

    def test_correction_rewrites_when_no_new_memory(self):
        fact = self.store.add("His son Mark's birthday is the 7th of November, 1952, a Friday")
        self.learn("His son Mark's birthday is the 7th of November", fact)
        self.learn("Mark's birthday is November 9")
        self.assertEqual(self.store.text_of(fact), "His son Mark's birthday is November 9, 1952, a Friday")

    def test_two_dates_on_one_memory_stay_standing(self):
        fact = self.store.add("Mark's birthday is November 7 and Lily's is March 12")
        for found in md.parse(self.store.text_of(fact)):
            self.store.learn_date(found, fact)
        newer = self.store.add("Mark's birthday is November 9")
        self.learn("Mark's birthday is November 9", newer)
        self.assertEqual(self.store.text_of(fact), "Mark's birthday is November 9 and Lily's is March 12")
        self.assertEqual(sorted(self.rows("SELECT memory_id FROM dates")), [(fact,), (newer,)])

    def test_correct_last(self):
        date_id = self.learn("Mark's birthday is November 7")
        heard = ["Mark's birthday is November 7"]
        self.assertIsNone(self.store.correct_last("no, it's the 9th", ["I saw Mark", "Lily is here"]))
        self.assertIsNone(self.store.correct_last("no, it's the 31st", heard))
        self.assertIsNone(self.store.correct_last("Mark came on the 9th", heard))
        self.assertEqual(self.store.correct_last("no, it's the 9th", ["Hello", *heard]), date_id)
        self.assertEqual(self.rows("SELECT month, day FROM dates"), [(11, 9)])
        self.assertEqual(self.rows("SELECT text FROM memories"), [("Mark's birthday, November 9",)])
        heard = ["Mark's birthday is November 9"]
        self.assertEqual(self.store.correct_last("actually it's December 2", heard), date_id)
        self.assertEqual(self.rows("SELECT month, day FROM dates"), [(12, 2)])

    def test_correct_last_never_guesses_between_two(self):
        mark = self.learn("Mark's birthday is November 7")
        self.learn("Lily's birthday is March 12")
        heard = ["Mark's birthday is November 7 and Lily's is March 12"]
        self.assertIsNone(self.store.correct_last("no, it's the 9th", heard))
        self.assertEqual(self.store.correct_last("no, Mark's is the 9th", heard), mark)

    def test_due_window_and_order(self):
        self.learn("Mark's birthday is November 5")   # 5 days ahead
        self.learn("Lily's birthday is November 8")   # 8 days ahead
        self.learn("Sue's birthday is November 4")    # 4: too soon
        self.learn("Bob's birthday is November 9")    # 9: too far
        self.learn("Ann's birthday is November 6")
        self.learn("Tom's birthday is November 7")
        got = self.store.due(self.day)
        self.assertEqual([(d["who"], d["days"]) for d in got], [("Mark", 5), ("Ann", 6), ("Tom", 7)])
        self.assertEqual(got[0]["on"], date(2026, 11, 5))
        self.assertEqual(got[0]["label"], "Mark's birthday, November 5")

    def test_due_skips_done_and_todays(self):
        with mock.patch.object(memory_core, "_today", return_value=self.day):
            date_id = self.learn("Mark's birthday is November 7")
            self.assertEqual(self.store.due(), [])  # told today, so it isn't news
        later = date(2026, 11, 1)
        self.assertEqual(len(self.store.due(later)), 1)
        self.store.mark_done(date_id, 2026)
        self.assertEqual(self.store.due(later), [])
        self.assertEqual(self.store.due(date(2027, 11, 1))[0]["id"], date_id)  # back next year

    def test_due_skips_the_stopped_and_the_dead(self):
        self.learn("my son Mark's birthday is November 7")
        self.learn("Lily's birthday is November 6")
        self.learn("Tom and Sue's anniversary is November 5")
        self.assertEqual(len(self.store.due(self.day)), 3)
        self.store.stop_reminders("Sue")
        self.store.stop_reminders("son")
        self.assertEqual([d["who"] for d in self.store.due(self.day)], ["Lily"])
        self.store.allow_reminders("SON")
        self.assertEqual(len(self.store.due(self.day)), 2)
        self.store.add("Lily passed away in 2019")
        self.assertEqual([d["who"] for d in self.store.due(self.day)], ["Mark"])

    def test_widow_stops_her_anniversary(self):
        self.learn("my anniversary is November 7")
        self.assertEqual(len(self.store.due(self.day)), 1)
        self.store.add("She is a widow")
        self.assertEqual(self.store.due(self.day), [])

    def test_said_due(self):
        mark = self.learn("Mark's birthday is November 7")
        pair = self.learn("Tom and Sue's anniversary is November 6")
        own = self.learn("my anniversary is November 5")
        self.assertEqual(self.store.said_due("How are the grandkids?", self.day), [])
        self.assertEqual(sorted(self.store.said_due("mark's birthday is near, and sue's day too", self.day)),
                         sorted([mark, pair]))
        self.assertEqual(self.store.said_due("Your anniversary is close", self.day), [own])
        self.assertEqual(self.store.due(self.day), [])

    def test_last_raised_and_note_passed(self):
        self.assertEqual(self.store.last_raised(), "")
        self.store.mark_done(self.learn("Mark's birthday is November 7"), 2026)
        self.assertEqual(self.store.last_raised(), "Mark")
        self.store.stop_reminders("Ruth")
        self.store.note_passed(["Ruth", "Bob", ""])
        self.assertEqual(self.rows("SELECT who, why FROM no_reminders ORDER BY who"),
                         [("bob", "passed"), ("ruth", "asked")])

    def test_forget(self):
        self.learn("Mark's birthday is November 7")
        self.store.stop_reminders("Mark")
        self.store.stop_reminders("Ruth")
        self.assertEqual(self.store.forget("Mark"), ["Mark's birthday, November 7"])
        self.assertEqual(self.rows("SELECT * FROM dates"), [])
        self.assertEqual(self.rows("SELECT who FROM no_reminders"), [("ruth",)])
        self.store.forget_name("Ruth")
        self.assertEqual(self.rows("SELECT who FROM no_reminders"), [])
        self.store.mark_done(self.learn("Lily's birthday is November 7"), 2026)
        self.store.stop_reminders("Bob")
        self.store.forget("everything")
        for table in ("memories", "dates", "date_done", "no_reminders"):
            self.assertEqual(self.rows(f"SELECT * FROM {table}"), [], table)


class Today(unittest.TestCase):
    def test_today_from_the_setting(self):
        with mock.patch.dict("os.environ", {"TRACKER_TODAY": "2026-11-01"}):
            self.assertEqual(memory_core._today(), date(2026, 11, 1))
        with mock.patch.dict("os.environ", {"TRACKER_TODAY": "soon"}):
            self.assertEqual(memory_core._today(), date.today())



def clock(day):
    return mock.patch.dict(os.environ, {"TRACKER_TODAY": day})


class Wiring(unittest.TestCase):
    """What joins the parser and the store to her talk."""

    NOTE = ("\n\nOne thing to bring up once in this talk, in your own words, at a natural moment soon: their son's "
            "birthday, Saturday November 7, a week from today. They told you this date themselves. Say the name and the "
            "occasion plainly so they know who you mean, and say there's still time to call or write. Keep it to a "
            "sentence or two, then go back to what you were talking about, and leave it alone whatever they say. It's "
            "your own memory: never mention a reminder, a note or the app. If they've just said something heavy, wait "
            "for a better moment.")

    def setUp(self):
        helpers.reset_db()
        self.memory = server.mary_memory()
        self.memory.name, self.memory.recent = "", []
        self.store = self.memory.store

    def rows(self, sql="SELECT who, what, month, day FROM dates ORDER BY id"):
        with closing(server.connect_memories()) as conn:
            return [tuple(row) for row in conn.execute(sql).fetchall()]

    def stopped(self):
        return self.rows("SELECT who, why FROM no_reminders ORDER BY who")

    def son_due(self):
        with clock("2026-01-01"):
            mary.learn_dates(self.memory, "My son's birthday is November 7")

    def system(self, text, kind=""):
        return mary._body(text, self.memory, kind)["systemInstruction"]["parts"][0]["text"]

    def test_third_person(self):
        found = md.parse("Their wedding anniversary is June 3.", third_person=True)
        self.assertEqual([(f["who"], f["what"], f["month"], f["day"]) for f in found], [("", "anniversary", 6, 3)])
        self.assertEqual(md.parse("June 3 is her anniversary.", third_person=True)[0]["who"], "")
        self.assertEqual(md.parse("Their wedding anniversary is June 3."), [])
        self.assertEqual(md.parse("His birthday is June 3.", third_person=True), [])

    def test_last_raised_within_days(self):
        with clock("2026-11-01"):
            self.store.mark_done(self.store.learn_date(one("Mark's birthday is November 7")), 2026)
        with clock("2026-11-03"):
            self.assertEqual(self.store.last_raised(within_days=2), "Mark")
        with clock("2026-11-04"):
            self.assertEqual(self.store.last_raised(within_days=2), "")
            self.assertEqual(self.store.last_raised(), "Mark")

    def test_fact_keeps_a_date_they_said(self):
        self.assertTrue(self.memory.add_fact("Her son Mark's birthday is November 7.",
                                             heard="My son Mark's birthday is November 7"))
        self.assertEqual(self.rows(), [("Mark", "birthday", 11, 7)])

    def test_fact_keeps_a_date_from_a_recent_turn(self):
        self.memory.add_turn("user", "June 3, I think of it every year.")
        self.memory.add_fact("Their anniversary is June 3.", heard="That's right")
        self.assertEqual(self.rows(), [("", "anniversary", 6, 3)])

    def test_fact_keeps_a_correction(self):
        self.memory.add_fact("Mark's birthday is November 9.", heard="No, it's the 9th")
        self.assertEqual(self.rows(), [("Mark", "birthday", 11, 9)])

    def test_fact_drops_a_date_they_never_said(self):
        self.assertTrue(self.memory.add_fact("Her son Mark's birthday is November 7.", heard="Mark's birthday is soon"))
        self.assertEqual((self.rows(), len(self.store.active())), ([], 1))

    def test_date_trouble_never_loses_the_memory(self):
        said = "Mark's birthday is November 7"
        with mock.patch.object(self.store, "learn_date", side_effect=OSError("locked")):
            self.assertTrue(self.memory.add_fact(said + ".", heard=said))
            mary.learn_dates(self.memory, said)
        self.assertEqual(len(self.store.active()), 1)

    def test_forget_never_saves(self):
        mary.learn_dates(self.memory, "Forget Mark's birthday, November 7")
        self.memory.scrubbed = True
        mary.learn_dates(self.memory, "Mark's birthday is November 7")
        self.assertEqual(self.rows(), [])

    def test_the_late_are_noted(self):
        mary.learn_dates(self.memory, "My late husband's birthday is June 3")
        self.assertEqual(self.stopped(), [("husband", "passed")])

    def test_stop_and_allow(self):
        mary.learn_dates(self.memory, "Don't remind me about him")
        self.assertEqual(self.stopped(), [])
        mary.learn_dates(self.memory, "Don't remind me about Mark")
        self.assertEqual(self.stopped(), [("mark", "asked")])
        mary.learn_dates(self.memory, "You can remind me about Mark")
        self.assertEqual(self.stopped(), [])

    def test_stop_a_pronoun_after_she_raised_it(self):
        with clock("2026-11-01"):
            self.store.mark_done(self.store.learn_date(one("Mark's birthday is November 7")), 2026)
            mary.learn_dates(self.memory, "Don't remind me about him")
        self.assertEqual(self.stopped(), [("mark", "asked")])

    def test_correction_then_a_new_date(self):
        said = "Mark's birthday is November 7"
        mary.learn_dates(self.memory, said)
        self.memory.add_turn("user", said)
        mary.learn_dates(self.memory, "No, it's the 9th")
        self.assertEqual(self.rows(), [("Mark", "birthday", 11, 9)])
        mary.learn_dates(self.memory, "It's Lily's birthday, March 12")  # starts like a correction, and isn't one
        self.assertEqual(self.rows(), [("Mark", "birthday", 11, 9), ("Lily", "birthday", 3, 12)])

    def test_tool(self):
        got = mary.memory_tool(self.memory, "stop_reminders", {"who": "my son"})
        self.assertEqual(got["response"], {"done": True, "note": mary.REMINDERS_STOPPED_NOTE})
        self.assertEqual(got["say"], mary.REMINDERS_STOPPED_TEXT)
        self.assertEqual(self.stopped(), [("son", "asked")])
        got = mary.memory_tool(self.memory, "stop_reminders", {"who": "him"})
        self.assertEqual(got["response"], {"done": False, "note": mary.REMINDERS_WHO_NOTE})
        self.assertEqual(mary.memory_tool(self.memory, "stop_reminders", {})["response"]["note"], mary.REMINDERS_WHO_NOTE)
        self.assertEqual(self.stopped(), [("son", "asked")])

    def test_tool_in_live(self):
        names = [tool["name"] for tool in mary.LIVE_MEMORY_TOOLS]
        self.assertIn("stop_reminders", names)
        _, got, _ = helpers.api("POST", "/api/mary/skills/call", {"name": "stop_reminders", "args": {"who": "Mark"}})
        self.assertTrue(got["response"]["done"])
        self.assertEqual(self.stopped(), [("mark", "asked")])

    def test_offline(self):
        self.assertEqual(mary.offline_memory(self.memory, "Don't remind me about him"), "")
        self.assertEqual(self.stopped(), [])
        self.assertEqual(mary.offline_memory(self.memory, "Don't remind me about Mark"), mary.REMINDERS_STOPPED_TEXT)
        self.assertEqual(self.stopped(), [("mark", "asked")])

    def test_note_as_built(self):
        self.son_due()
        with clock("2026-10-31"):
            self.assertEqual(mary.reminder_note(self.memory), self.NOTE)
            self.assertNotIn("[", self.NOTE)
            carded = mary.reminder_note(self.memory, cards=True)
        self.assertEqual(carded.replace(mary.REMINDER_CARDS_LINE, ""), self.NOTE)
        self.assertNotEqual(carded, self.NOTE)
        with clock("2026-11-01"):
            self.assertIn("6 days from today", mary.reminder_note(self.memory))
        with clock("2026-09-01"):
            self.assertEqual(mary.reminder_note(self.memory), "")

    def test_note_in_the_prompt_only_when_fit(self):
        self.son_due()
        emergency = "I can't breathe"
        with clock("2026-10-31"):
            sent = self.system("Good morning")
            self.assertGreater(sent.index(self.NOTE), sent.index(mary.CHARACTER_NOTE))
            self.assertNotIn(self.NOTE, self.system("An aide hit me"))
            self.assertNotIn(self.NOTE, self.system(emergency, mary.is_emergency(emergency)))

    def test_note_in_live(self):
        self.son_due()
        net = Net(Resp({"name": "auth_tokens/abc"}))
        with clock("2026-10-31"), mock.patch.object(voices, "_open", net):
            voices.live_token("live:Achird", KEY, "mary", "", server.DATA, memory=self.memory)
        sent = net.body()["bidiGenerateContentSetup"]["systemInstruction"]["parts"][0]["text"]
        self.assertGreater(sent.index(self.NOTE), sent.index(voices.LIVE_TOOLS_NOTE))
        self.assertFalse(server.mary_live_skill_setup()["cards"])  # no messages skill yet; M15b flips this

    def test_once_she_says_it(self):
        self.son_due()
        with clock("2026-10-31"):
            self.memory.add_turn("model", "How did you sleep?")
            self.assertTrue(self.store.due())
            self.memory.add_turn("model", "Your son's birthday is a week off, so there's still time to call.")
            self.assertEqual(self.store.due(), [])
            self.assertEqual(self.store.last_raised(within_days=2), "son")

    def test_reply_with_no_gemini(self):
        mary.reply("Mark's birthday is November 7", self.memory)
        self.assertEqual(self.rows(), [("Mark", "birthday", 11, 7)])
        emergency = "I can't breathe and Lily's birthday is March 12"
        self.assertTrue(mary.is_emergency(emergency))
        mary.reply(emergency, self.memory)
        self.assertEqual(self.rows(), [("Mark", "birthday", 11, 7)])

    def test_heard_and_the_page_list(self):
        helpers.api("POST", "/api/mary/heard", {"text": "Mark's birthday is November 7"})
        helpers.api("POST", "/api/mary/heard", {"text": "I can't breathe and Lily's birthday is March 12"})
        self.assertEqual(self.rows(), [("Mark", "birthday", 11, 7)])
        _, got, _ = helpers.api("GET", "/api/mary/memories")
        self.assertEqual(got["memories"][0]["saved_date"], "Mark's birthday, November 7")


if __name__ == "__main__":
    unittest.main()
