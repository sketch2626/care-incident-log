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
        self.assertEqual(carded.replace(mary.REMINDER_CARDS_LINE, "").replace(mary.REMINDER_KEEPSAKE_LINE, ""), self.NOTE)
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
        self.assertTrue(server.mary_live_skill_setup()["cards"])  # M15b: the messages skill is here

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


class Needs(unittest.TestCase):
    """M15a: the whole list of what must hold, through the real functions."""

    def setUp(self):
        helpers.reset_db()
        with closing(server.connect_memories()) as conn, conn:
            for table in ("dates", "date_done", "no_reminders"):
                conn.execute(f"DELETE FROM {table}")
        self.memory = server.mary_memory()
        self.memory.name, self.memory.recent = "", []
        self.store = self.memory.store

    def count(self, table):
        with closing(server.connect_memories()) as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def hear(self, text, day="2026-01-01"):
        with clock(day):
            mary.learn_dates(self.memory, text)

    def due_on(self, day, store=None):
        with clock(day):
            return [d["who"] for d in (store or self.store).due()]

    def stopped(self):
        with closing(server.connect_memories()) as conn:
            return [tuple(r) for r in conn.execute("SELECT who, why FROM no_reminders ORDER BY who")]

    def rows_md(self):
        with closing(server.connect_memories()) as conn:
            return [tuple(r) for r in conn.execute("SELECT month, day FROM dates")]

    def test_once_only_and_next_day(self):
        self.hear("Mark's birthday is November 7")
        with clock("2026-11-01"):
            self.assertIn("Mark", mary.reminder_note(self.memory))
            self.memory.add_turn("model", "Mark's birthday is coming up, so there's time to call.")
            self.assertEqual(mary.reminder_note(self.memory), "")
            self.memory.add_turn("user", "Thanks")
            self.assertEqual(mary.reminder_note(self.memory), "")
        self.assertEqual(self.due_on("2026-11-02"), [])

    def test_across_a_restart(self):
        self.hear("Mark's birthday is November 7")
        self.hear("Lily's birthday is November 6")
        with clock("2026-11-01"):
            self.memory.add_turn("model", "Mark's birthday is coming up.")
        fresh_memory = server.mary_memory()
        fresh = memory_core.MemoryStore(server.connect_memories)
        self.assertEqual(self.due_on("2026-11-01", fresh), ["Lily"])
        self.assertEqual(self.due_on("2026-11-01", fresh_memory.store), ["Lily"])

    def test_a_missed_week(self):
        self.hear("Mark's birthday is November 7")
        self.assertEqual(self.due_on("2026-10-29"), [])  # 9 days out
        self.assertEqual(self.due_on("2026-11-02"), ["Mark"])  # first talk, 5 days out
        self.assertEqual(self.due_on("2026-11-03"), [])  # 4 days out with no talk before: lost this year
        self.assertEqual(self.due_on("2027-10-31"), ["Mark"])  # back next year

    def test_new_year(self):
        self.hear("Mark's birthday is December 30")
        self.hear("Lily's birthday is January 2")
        self.assertEqual(self.due_on("2026-12-23"), ["Mark"])
        with clock("2026-12-26"):
            self.assertEqual([d["who"] for d in self.store.due()], ["Lily"])
            self.memory.add_turn("model", "Lily's birthday is coming up.")
        with closing(server.connect_memories()) as conn:
            self.assertEqual([r[0] for r in conn.execute("SELECT year FROM date_done")], [2027])
        self.assertEqual(self.due_on("2026-12-27"), [])
        self.assertEqual(self.due_on("2027-12-26"), ["Lily"])

    def test_leap_day(self):
        self.hear("Mark's birthday is February 29")
        self.assertEqual(self.due_on("2027-02-19"), [])  # 9 days before Feb 28
        self.assertEqual(self.due_on("2027-02-20"), ["Mark"])  # Feb 28 minus 8: the window opens
        self.assertEqual(self.due_on("2028-02-20"), [])  # 9 days before Feb 29
        self.assertEqual(self.due_on("2028-02-21"), ["Mark"])  # Feb 29 minus 8

    def test_the_dead_get_no_note(self):
        for fact, who in (("my late husband Bob", "Bob"), ("Mark passed in 2019", "Mark"), ("since Ruth died", "Ruth")):
            with self.subTest(fact):
                self.store.add(fact)
                self.hear(f"{who}'s birthday is November 7")
                self.assertEqual(self.due_on("2026-11-01"), [], fact)
        self.hear("My late husband's birthday is June 3")
        self.assertEqual(self.due_on("2026-05-30"), [])

    def test_stopping_and_bringing_back(self):
        self.hear("Mark's birthday is November 7")
        with clock("2026-11-01"):
            self.memory.add_turn("model", "Mark's birthday is coming up.")
        self.hear("Don't remind me about him", "2026-11-01")
        self.assertEqual(self.stopped(), [("mark", "asked")])
        self.hear("Go ahead and remind me about Mark again", "2026-11-02")
        self.assertEqual(self.stopped(), [])
        self.hear("Don't remind me about Mark")
        self.assertEqual(self.stopped(), [("mark", "asked")])
        self.hear("Go ahead and remind me about Mark again")
        self.assertEqual(self.stopped(), [])
        self.hear("Don't remind me about him", "2026-11-10")  # nobody raised lately
        self.assertEqual(self.stopped(), [])

    def test_forgetting_takes_the_date_and_its_mark(self):
        def set_up():
            self.memory.scrubbed = False  # a new turn
            self.hear("Mark's birthday is November 7")
            with clock("2026-11-01"):
                self.store.mark_done(self.store.due()[0]["id"], 2026)
            self.assertEqual((self.count("dates"), self.count("date_done")), (1, 1))

        def empty():
            self.assertEqual((self.count("dates"), self.count("date_done")), (0, 0))
        set_up()
        mary.forget_everything(self.memory, "Mark's birthday")
        empty()
        set_up()
        mary.forget_name(self.memory, "Mark")
        empty()
        set_up()
        mary.forget_everything(self.memory, "everything")
        empty()
        set_up()
        self.store.remove(self.store.active()[0]["id"])  # the Remove button
        empty()
        self.hear("Mark's birthday is November 7")  # said again after a forget: may be raised again
        self.assertEqual(self.due_on("2026-11-01"), ["Mark"])

    def test_forget_by_the_tool(self):
        said = "Mark's birthday is November 7"
        self.memory.add_fact(said, heard=said)
        self.assertEqual(self.count("dates"), 1)
        mary.memory_tool(self.memory, "forget_memory", {"about": "Mark's birthday"})
        mary.memory_tool(self.memory, "forget_memory", {"about": "Mark's birthday", "confirmed": True})
        self.assertEqual((self.count("dates"), self.count("date_done")), (0, 0))

    def test_unreadable_and_invented_dates(self):
        said = "Mark's birthday is sometime in the fall"
        self.hear(said)
        self.assertTrue(self.memory.add_fact(said + ".", heard=said))
        self.assertEqual((len(self.store.active()), self.count("dates")), (1, 0))
        self.assertTrue(self.memory.add_fact("Mark's birthday is November 7", heard="Mark's coming to see me"))
        self.assertEqual((len(self.store.active()), self.count("dates")), (2, 0))

    def test_correction_keeps_one_date(self):
        said = "Mark's birthday is November 7"
        self.hear(said)
        with clock("2026-11-01"):
            self.store.mark_done(self.store.due()[0]["id"], 2026)
        self.memory.add_turn("user", said)
        self.hear("No, it's the 9th")
        self.assertEqual((self.count("dates"), self.count("date_done")), (1, 1))
        self.assertEqual(self.rows_md(), [(11, 9)])
        self.assertEqual([m["text"] for m in self.store.active()], ["Mark's birthday, November 9"])

    def test_small_fixes(self):
        self.hear("Don't forget, Mark's birthday is November 7")
        self.assertEqual(self.count("dates"), 1)
        self.hear("Forget Lily's birthday, March 12")
        self.assertEqual(self.count("dates"), 1)
        # asked about Mark's birthday long ago, a doctor's question last turn: "the 9th" is not a fix
        for who, text in (("user", "When is Mark's birthday?"), ("model", "Mark's is November 7."), ("user", "Thanks"),
                          ("model", "Anything else?"), ("user", "What time is my doctor's visit?"),
                          ("model", "Check with the nurse.")):
            self.memory.add_turn(who, text)
        self.hear("It's the 9th")
        self.assertEqual(self.rows_md(), [(11, 7)])

    def test_one_or_a_few(self):
        self.hear("Mark's birthday is November 7")
        with clock("2026-11-01"):
            note = mary.reminder_note(self.memory)
        self.assertIn("One thing", note)
        self.assertIn("this date", note)
        self.hear("Lily's birthday is November 6")
        with clock("2026-11-01"):
            note = mary.reminder_note(self.memory)
        self.assertIn("A few things", note)
        self.assertIn("these dates", note)

    def test_never_on_a_heavy_turn_and_no_brackets(self):
        self.hear("Mark's birthday is November 7")
        with clock("2026-11-01"):
            note = mary.reminder_note(self.memory)
            self.assertTrue(note)
            self.assertNotIn("[", note)
            self.assertNotIn("]", note)
            for text in ("I can't breathe", "An aide hit me"):
                sent = mary._body(text, self.memory, mary.is_emergency(text))["systemInstruction"]["parts"][0]["text"]
                self.assertNotIn(note, sent, text)
            sent = mary._body("Good morning", self.memory, "")["systemInstruction"]["parts"][0]["text"]
            self.assertIn(note, sent)


    # M15a: one person saved twice gives one reminder
    def due_items(self, day):
        with clock(day):
            return self.store.due()

    def test_twice_saved_person_one_reminder(self):
        self.hear("my son's birthday is November 7")
        self.hear("my son Mark's birthday is November 7")
        items = self.due_items("2026-11-01")
        self.assertEqual(len(items), 1)
        self.assertIn("Mark", items[0]["label"])
        self.assertEqual(len(items[0]["also"]), 1)
        with clock("2026-11-01"):
            ids = self.store.said_due("Mark's birthday is coming up")
        self.assertEqual(len(ids), 2)
        self.assertEqual(self.count("date_done"), 2)
        self.assertEqual(self.due_items("2026-11-02"), [])

    def test_memory_ties_plain_name_to_relation(self):
        self.store.add("Mark is my son")
        self.hear("my son's birthday is November 7")
        self.hear("Mark's birthday is November 7")
        items = self.due_items("2026-11-01")
        self.assertEqual([i["who"] for i in items], ["Mark"])

    def test_done_twin_silences_later_learned_date(self):
        self.hear("my son Mark's birthday is November 7")
        with clock("2026-11-01"):
            self.store.said_due("Mark")
        self.hear("my son's birthday is November 7", day="2026-11-02")
        self.assertEqual(self.due_items("2026-11-02"), [])

    def test_not_the_same_person(self):
        cases = (("my son's birthday is November 7", "my son Mark's birthday is November 9"),
                 ("Mark's birthday is November 7", "Lily's birthday is November 7"),
                 ("my son Mark's birthday is November 7", "my son Luke's birthday is November 7"),
                 ("my son's birthday is November 7", "my daughter's birthday is November 7"))
        for first, second in cases:
            with self.subTest(first=first, second=second):
                with closing(server.connect_memories()) as conn, conn:
                    conn.execute("DELETE FROM dates")
                self.hear(first)
                self.hear(second)
                self.assertEqual(len(self.due_items("2026-11-02" if "9" in second else "2026-11-01")), 2)


class StopMidTalk(unittest.TestCase):
    """M15a: "don't remind me about him" right after "your boy's birthday", with the talk still open."""

    def test_him_means_the_date_just_sent(self):
        helpers.reset_db()
        memory = server.mary_memory()
        memory.name, memory.recent = "", []
        with clock("2026-01-01"):
            mary.learn_dates(memory, "Mark's birthday is November 7")
        with clock("2026-11-01"):
            memory.store.note_sent(memory.store.due())
            self.assertEqual(memory.store.last_raised(within_days=2), "Mark")
            mary.learn_dates(memory, "Don't remind me about him")
        with clock("2027-11-01"):
            self.assertEqual(memory.store.due(), [])


if __name__ == "__main__":
    unittest.main()


class OneTalk(unittest.TestCase):
    """M15a: at most one talk ever carries a date's note, whatever she says or they answer."""

    DAY = "2026-11-01"

    def setUp(self):
        helpers.reset_db()
        self.memory = server.mary_memory()
        self.memory.name, self.memory.recent = "", []
        self.store = self.memory.store
        with clock("2026-01-01"):
            mary.learn_dates(self.memory, "Mark's birthday is November 7")

    def rows(self, table):
        with closing(server.connect_memories()) as conn:
            return [tuple(row) for row in conn.execute(f"SELECT date_id, year FROM {table}")]

    def note(self, day=DAY):
        with clock(day):
            return mary.reminder_note(self.memory)

    def talk(self, text="Good morning", said="Your boy's birthday is coming up.", day=DAY):
        """One turn with a fake Gemini that never says Mark. True when the note was in her prompt."""
        bodies = []

        def stream(body, *args, **kw):
            bodies.append(body)
            if said is None:
                raise OSError("no line")
            yield said

        with clock(day), mock.patch.object(mary, "_gemini_stream", stream):
            mary.reply(text, self.memory, KEY)
        return mary.REMINDER_MARK in bodies[0]["systemInstruction"]["parts"][0]["text"]

    def hello(self):
        """server.mary_tell with a fake Gemini. True when the note was in her prompt."""
        bodies = []

        def answer(body, *args, **kw):
            bodies.append(body)
            return "Good morning to you."

        real = server.mary_settings
        with clock(self.DAY), mock.patch.object(mary, "_short_answer", answer), \
                mock.patch.object(server, "mary_settings", lambda: {**real(), "key": KEY}):
            self.assertTrue(server.mary_tell("The app has opened.")["text"])
        return mary.REMINDER_MARK in bodies[0]["systemInstruction"]["parts"][0]["text"]

    def token(self, **patch):
        real = server.mary_settings
        with clock(self.DAY), mock.patch.object(server, "mary_settings", lambda: {**real(), "key": KEY}), \
                mock.patch.object(voices, "_open", Net(Resp({"name": "auth_tokens/abc"}))):
            if patch:
                with mock.patch.object(voices, "live_token", **patch):
                    return helpers.api("POST", "/api/mary/live/start", {})
            return helpers.api("POST", "/api/mary/live/start", {})

    def test_her_own_words_then_the_talk_ends(self):
        self.assertTrue(self.talk())
        self.assertEqual(len(self.rows("date_sent")), 1)
        with clock(self.DAY):
            status, got, _ = helpers.api("POST", "/api/mary/talk/end", {})
        self.assertEqual((status, got), (200, {"ok": True}))
        self.assertEqual(self.rows("date_sent"), [])
        self.assertEqual(self.note(), "")
        self.assertEqual(self.note("2026-11-02"), "")

    def test_one_reply_then_gone_until_next_year(self):
        self.assertTrue(self.talk())
        with clock(self.DAY):
            helpers.api("POST", "/api/mary/talk/end", {})
        self.assertEqual(self.note("2026-11-03"), "")
        self.assertIn("Mark", self.note("2027-11-01"))

    def test_three_replies_in_one_talk(self):
        self.assertEqual([self.talk() for _ in range(4)], [True, True, True, False])
        self.assertEqual(self.rows("date_sent"), [])

    def test_a_crash_counts_as_sent(self):
        self.assertTrue(self.talk())
        self.assertEqual(memory_core.MemoryStore(server.connect_memories).close_talk(), 1)
        self.assertEqual(self.note(), "")

    def test_a_stale_row_counts_as_sent(self):
        self.assertTrue(self.talk())
        with closing(server.connect_memories()) as conn, conn:
            conn.execute("UPDATE date_sent SET at = at - 60")
        self.assertIn("Mark", self.note())
        with closing(server.connect_memories()) as conn, conn:
            conn.execute("UPDATE date_sent SET at = at - 600")
        self.assertEqual(self.note(), "")
        self.assertEqual(self.rows("date_sent"), [])

    def test_a_group_goes_as_one(self):
        with clock("2026-01-01"):
            mary.learn_dates(self.memory, "My son Mark's birthday is November 7")
            mary.learn_dates(self.memory, "My son's birthday is November 7")
        with clock(self.DAY):
            items = self.store.due()
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["also"])
        self.store.note_sent(items)
        self.assertEqual(len(self.rows("date_sent")), 1 + len(items[0]["also"]))
        self.assertEqual(self.store.close_talk(), 1 + len(items[0]["also"]))
        self.assertEqual(len(self.rows("date_done")), 1 + len(items[0]["also"]))

    def test_a_hello_carries_it_and_counts(self):
        self.assertTrue(self.hello())
        self.assertEqual(len(self.rows("date_sent")), 1)

    def test_a_new_hello_closes_the_old_talk(self):
        self.assertTrue(self.talk())
        server.close_talk()  # M21a: a tell no longer ends the talk; the page's new talk does
        self.assertFalse(self.hello())
        self.assertEqual(self.note(), "")

    def test_emergency_and_harm_send_nothing(self):
        self.assertFalse(self.talk("I can't breathe"))
        self.assertFalse(self.talk("An aide hit me"))
        self.assertEqual(self.rows("date_sent"), [])
        self.assertTrue(self.talk())

    def test_gemini_failing_sends_nothing(self):
        self.assertTrue(self.talk(said=None))
        self.assertEqual(self.rows("date_sent"), [])
        self.assertIn("Mark", self.note())

    def test_live_token_marks_and_three_turns_close(self):
        self.assertEqual(self.token()[0], 200)
        self.assertEqual(len(self.rows("date_sent")), 1)
        with clock(self.DAY), mock.patch.object(server, "_live_forgot_at", None):
            helpers.api("POST", "/api/mary/heard", {"text": "Good morning"})
            for said in ("Good morning to you.", "How did you sleep?"):
                helpers.api("POST", "/api/mary/live/said", {"text": said})
            self.assertEqual(len(self.rows("date_sent")), 1)
            helpers.api("POST", "/api/mary/live/said", {"text": "Your boy's birthday is coming up."})
        self.assertEqual(self.rows("date_sent"), [])
        self.assertEqual(self.note(), "")

    def test_live_token_failing_marks_nothing(self):
        self.assertNotEqual(self.token(side_effect=voices.VoiceError("connect"))[0], 200)
        self.assertEqual(self.rows("date_sent"), [])
        self.assertTrue(self.talk())

    def test_forget_removes_the_rows(self):
        self.assertTrue(self.talk())
        self.store.forget("Mark")
        self.assertEqual(self.rows("date_sent"), [])

    def test_forget_everything_removes_the_rows(self):
        self.assertTrue(self.talk())
        self.store.forget("everything")
        self.assertEqual(self.rows("date_sent"), [])

    def test_the_page_says_when_a_talk_ends(self):
        js = server.Path(server.__file__).parent.joinpath("web", "mary", "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/mary/talk/end", js)
        self.assertIn("(c.talked || forgetAsking) && !c.endSent", js)
