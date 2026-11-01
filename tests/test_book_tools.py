from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M19 piece 6a: her tools for finding people and reading details, and details staying out of what she keeps. Gemini
sees names and which details exist. A value reaches her only when the resident's own words ask. Made-up people only."""
import json
import re
import subprocess
import unittest
from unittest import mock

import address_book
import mary
import memory_core
import secret_store
import server
import skills_core
import tests.test_m15c_send as send_tests
from tests.test_m15c_contacts import ADDRESS, Base

SAYS = memory_core.DETAIL_WORDS
PHONE, CELL, STREET = "919-555-0142", "919-555-0188", "12 Maple Street"
FACEBOOK, BIRTHDAY, NOTES = "sarah.hollis.99", "1960-03-14", "Takes her coffee black"
LOCKED_LINE = "Your address book is locked right now, so I can't look them up. A helper can open it."

ASKS = {"email": ("what's Sarah's email address", "read me her email", "put her email in the box",
                  "fill in the to box with Sarah", "read me my daughter's email"),
        "phone": ("What's Sarah's phone number", "what's her number", "read me my daughter's phone number",
                  "put her phone number in the box", "do you have Sarah's number"),
        "cell": ("what's Sarah's cell", "read me her cell number", "what's her mobile number",
                 "put her cell phone in the box"),
        "address": ("read me her address", "what's Sarah's address", "put her address in the box",
                    "what's her mailing address"),
        "facebook": ("what's Sarah's Facebook", "tell me her Facebook name", "put her Facebook in the box"),
        "birthday": ("when's Mark's birthday", "when is Sarah's birthday", "what's her birthday", "tell me his birthday",
                     "put her birthday in the box"),
        "notes": ("what did I put in the notes for Tom", "read me the notes on Sarah", "what's in Sarah's notes",
                  "read me her notes")}
NOT_ASKS = ("", "call my daughter", "email my daughter", "how is Sarah doing", "send it", "write to my daughter",
            "tell Sarah happy birthday", "add Sarah to my book", "who's in my book")
NOT_THIS_ONE = {"email": ("send an email to Sarah", "what's Sarah's phone number", "read me her birthday"),
                "phone": ("call Sarah's phone", "I need to phone Sarah", "what's her email", "what's her room number",
                          "what's Sarah's address"),
                "cell": ("call her cell", "what's her email"),
                "address": ("what's her email address", "what's her e-mail address", "send it to her address"),
                "facebook": ("message Sarah on Facebook", "is Sarah on Facebook", "what's her email"),
                "birthday": ("make a card for Sarah's birthday", "write a card for Sarah's birthday",
                             "I need a card for Mark's birthday", "what's her phone number"),
                "notes": ("write a note to Tom", "put a note on the card", "read me my notes")}

PHONES = ("919-555-0142", "(919) 555-0142", "919.555.0142", "919 555 0142", "1-919-555-0142", "+1 919 555 0142",
          "9195550142", "19195550142", "555-0142", "555 0142", "nine one nine five five five zero one four two")
STREETS = ("12 Maple Street", "12 Maple St", "12 Maple St.", "450 North Main Avenue", "450 N Main Ave", "9 Oak Road",
           "9 Oak Rd", "77 Elm Lane", "1200 Old Mill Drive", "1200 Old Mill Dr", "8 Pine Court", "500 Glenwood Blvd",
           "1200 Highway 64", "1200 US Hwy 70", "PO Box 123", "P.O. Box 123", "post office box 44", "12 maple street",
           "12 Maple Street, Apt 4")
SAFE = ("I was born in 1942", "Room 214", "room 214 since 2019", "she's 87", "3 kids", "I raised 3 kids on Maple Street",
        "I lived on Maple Street for years", "March 14, 1950", "3/14/1950", "03-14-1950", "1950-03-14", "03141950",
        "the bus comes at 10:30", "at 2:45 pm", "Sarah's birthday is March 14", "It's a 3 hour drive", "a 30 minute drive",
        "In 1942 Main Street was dirt", "I lived off Highway 64", "Mass at St Mary's at 9", "he paid $1000000",
        "1,000,000 dollars", "1942-1945", "at 5 see Dr Smith", "my daughter Sarah", "I'm 87 and I have 3 grandkids", "")


class Book(Base):
    def setUp(self):
        super().setUp()
        self.person(name="Sarah", relationship="daughter", email=ADDRESS, phone=PHONE, cell=CELL, address=STREET,
                    facebook=FACEBOOK, birthday=BIRTHDAY, notes=NOTES)

    def values(self):
        row = self.contact("Sarah")
        return {field: row[field] for field in skills_core.PERSON_DETAILS}

    def call(self, tool, heard="", **args):
        self.last = self.host.call("messages__" + tool, args, heard=heard)
        return self.last["response"]

    def read(self, field, heard, person="Sarah"):
        return self.call("read_detail", heard=heard, person=person, field=field)

    def lock_book(self):
        self.host.book.lock()
        secret_store.SecretStore(self.dir).delete(address_book.KEY_NAME)
        self.assertEqual(self.host.book.state(), "locked")


class FindPerson(Book):
    def test_one_match_says_who_and_what_exists(self):
        self.assertEqual(self.call("find_person", name="my daughter"),
                         {"known": True, "name": "Sarah", "relationship": "daughter", "has_email": True, "has_phone": True,
                          "has_cell": True, "has_address": True, "has_facebook": True, "has_birthday": True,
                          "has_notes": True})

    def test_what_isnt_saved_says_so(self):
        self.person(name="Tom")
        out = self.call("find_person", name="Tom")
        self.assertEqual({key: out[key] for key in ("has_email", "has_phone", "has_notes")},
                         {"has_email": False, "has_phone": False, "has_notes": False})

    def test_two_matches_ask_which(self):
        self.person(name="Mark Hollis")
        self.person(name="Mark Jones")
        out = self.call("find_person", name="Mark")
        self.assertEqual(out["which"], ["Mark Hollis", "Mark Jones"])
        self.assertTrue(out["known"])
        self.assertIn("Which one", self.last["say"])

    def test_nobody(self):
        self.assertEqual(self.call("find_person", name="Tyler"), {"known": False})

    def test_a_doctor_never_appears(self):
        self.host.book.add({"name": "Patel", "kind": "doctor", "phone": CELL})
        self.assertEqual(self.call("find_person", name="Patel"), {"known": False})
        self.assertEqual(self.read("phone", "what's Patel's phone number", "Patel"), {"known": False})
        self.assertEqual([p["name"] for p in self.call("list_people", heard="who's in my book")["people"]], ["Sarah"])

    def test_a_locked_book_says_so(self):
        self.lock_book()
        for out in (self.call("find_person", name="Sarah"), self.read("phone", "what's Sarah's phone number"),
                    self.call("list_people", heard="who's in my book")):
            self.assertTrue(out["book_locked"])
            self.assertEqual(out["note"], LOCKED_LINE)
            self.assertEqual(self.last["say"], LOCKED_LINE)


class ReadDetail(Book):
    def test_each_ask_gets_its_field(self):
        values = self.values()
        for field, lines in ASKS.items():
            for heard in lines:
                out = self.read(field, heard)
                self.assertEqual(out.get("value"), values[field], (field, heard))
                self.assertEqual(out["note"], "For what they asked, this once.")
                self.assertEqual("spell" in out, field == "email", (field, heard))

    def test_the_curly_quote_counts(self):
        self.assertEqual(self.read("phone", "what’s Sarah’s phone number")["value"], PHONE)

    def test_words_that_dont_ask_get_nothing(self):
        values = self.values()
        for field in ASKS:
            for heard in NOT_ASKS + NOT_THIS_ONE[field]:
                out = self.read(field, heard)
                self.assertTrue(out.get("not_asked"), (field, heard))
                self.assertEqual(out["note"], "They didn't ask for that. Use the name.")
                self.assertNotIn("value", out)
                self.assertNotIn(values[field], json.dumps(out), (field, heard))

    def test_nobody_or_nothing_saved(self):
        self.assertEqual(self.read("phone", "what's Tyler's phone number", "Tyler"), {"known": False})
        self.person(name="Tyler")
        self.assertEqual(self.read("phone", "what's Tyler's phone number", "Tyler"),
                         {"known": True, "name": "Tyler", "field": "phone", "has": False})

    def test_two_matches_ask_which_and_give_nothing(self):
        self.person(name="Mark Hollis", phone=PHONE)
        self.person(name="Mark Jones", phone=CELL)
        out = self.read("phone", "what's Mark's phone number", "Mark")
        self.assertEqual(len(out["which"]), 2)
        self.assertNotIn("value", out)

    def test_a_field_she_makes_up_goes_nowhere(self):
        self.assertIn("error", self.read("password", "what's Sarah's password"))

    def test_a_result_holds_a_value_only_with_the_ask(self):
        values = list(self.values().values())
        results = [self.call("find_person", name="Sarah"), self.call("list_people", heard="who's in my book")]
        results += [self.read(field, "email my daughter") for field in ASKS]
        results += [self.host.call("use_skill", {"action": "find_person", "details": "Sarah"})["response"]]
        for out in results:
            for value in values:
                self.assertNotIn(value, json.dumps(out))


class GroupsAndTheCeiling(Book):
    def test_the_live_ceiling_stands(self):
        tools = self.host.gemini_tools()[0]["functionDeclarations"]
        self.assertLessEqual(len(tools) + len(mary.LIVE_CORE_TOOLS), 13)
        self.assertFalse({d["name"] for d in tools} & {"find_person", "read_detail", "list_people"})
        always = [action["name"] for _, action in self.host._always()]
        self.assertLessEqual(len(always), skills_core.ALWAYS_MAX)
        for name in ("find_person", "read_detail", "slower", "faster", "quieter", "louder"):
            self.assertIn(name, always)

    def test_both_work_with_no_group_open(self):
        self.assertIsNone(self.host.opened)
        out = self.host.call("use_skill", {"action": "find_person", "details": "my daughter"})["response"]
        self.assertEqual(out["name"], "Sarah")
        details = json.dumps({"person": "my daughter", "field": "phone"})
        out = self.host.call("use_skill", {"action": "read_detail", "details": details},
                             heard="what's my daughter's phone number")["response"]
        self.assertEqual(out["value"], PHONE)
        out = self.host.call("use_skill", {"action": "read_detail", "details": details}, heard="call my daughter")["response"]
        self.assertTrue(out["not_asked"])

    def test_the_old_tools_are_gone(self):
        actions = self.host.skills["messages"].actions
        for name in ("save_contact", "find_contact", "contact_address"):
            self.assertNotIn(name, actions)
        for name in ("find_person", "read_detail", "list_people", "add_to_book"):
            self.assertIn(name, actions)


class ListAndAdd(Book):
    def test_who_gives_names_and_relationships(self):
        self.person(name="Tom", relationship="neighbor")
        out = self.call("list_people", heard="who's in my book")
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["people"], [{"name": "Sarah", "relationship": "daughter"},
                                         {"name": "Tom", "relationship": "neighbor"}])
        self.assertEqual(self.last["say"], "You have 2 people in your book: Sarah, Tom.")

    def test_how_many_says_the_number(self):
        self.person(name="Tom")
        self.call("list_people", heard="how many people have I got")
        self.assertEqual(self.last["say"], "You have 2 people in your book.")

    def test_at_most_forty_with_the_full_count(self):
        for number in range(45):
            self.person(name="Person %02d" % number)
        out = self.call("list_people", heard="who's in my book")
        self.assertEqual(len(out["people"]), 40)
        self.assertEqual(out["count"], 46)
        self.assertEqual(self.last["say"], "You have 46 people in your book.")

    def test_an_empty_book(self):
        self.ctx.people.forget("Sarah")
        self.assertEqual(self.call("list_people", heard="how many people have I got")["count"], 0)
        self.assertEqual(self.last["say"], "Your book is empty.")

    def test_offline_it_answers_and_adds_nothing(self):
        self.assertEqual(self.host.offline_match("who's in my book")["say"], "You have 1 person in your book: Sarah.")
        self.assertEqual(self.host.offline_match("how many people have I got")["say"], "You have 1 person in your book.")
        for line in ("add Tom to my book", "put Tom in my address book please, add him to my address book"):
            out = self.host.offline_match(line)
            self.assertIn("Menu", out["say"])
            self.assertFalse(out["response"]["saved"])
        self.assertEqual(self.call("list_people")["count"], 1)

    def test_add_points_to_the_menu_and_saves_nothing(self):
        out = self.call("add_to_book", heard="add Tom to my book")
        self.assertEqual(self.last["say"], "That's done in Address book. Tap Menu, then Address book.")
        self.assertFalse(out["saved"])
        self.assertIsNone(self.contact("Tom"))


class ScrubDetails(unittest.TestCase):
    def test_phone_forms(self):
        for line in PHONES:
            self.assertEqual(memory_core.scrub_details(line), SAYS, line)

    def test_street_forms(self):
        for line in STREETS:
            self.assertEqual(memory_core.scrub_details(line), SAYS, line)

    def test_email_as_today(self):
        for line in ("mark.hollis@example.com", "mark dot hollis at gmail dot com"):
            self.assertEqual(memory_core.scrub_details(line), memory_core.ADDRESS_WORDS)
        self.assertEqual(memory_core.scrub_addresses("call 919-555-0142"), "call 919-555-0142")  # that one's unchanged

    def test_the_words_around_it_stay(self):
        cases = {"Call me at 919-555-0142 after lunch.": "Call me at %s after lunch." % SAYS,
                 "I live at 12 Maple Street in Raleigh": "I live at %s in Raleigh" % SAYS,
                 "3 kids at 12 Maple Street": "3 kids at %s" % SAYS,
                 "it's 555-0142 or 919-555-0188": "it's %s or %s" % (SAYS, SAYS)}
        for line, want in cases.items():
            self.assertEqual(memory_core.scrub_details(line), want)

    def test_good_memories_stay(self):
        for line in SAFE:
            self.assertEqual(memory_core.scrub_details(line), line, line)
            self.assertFalse(memory_core.only_address(memory_core.scrub_details(line)), line)

    def test_twice_is_the_same_as_once(self):
        for line in PHONES + STREETS + SAFE:
            once = memory_core.scrub_details(line)
            self.assertEqual(memory_core.scrub_details(once), once, line)

    def test_only_a_detail_is_no_memory(self):
        for line in ("919-555-0142", STREET, "Sarah's number is 919-555-0142", "Her cell: 919-555-0142",
                     "Her phone number is 919-555-0142", "Her address is 12 Maple Street", "Sarah lives at 12 Maple Street"):
            self.assertTrue(memory_core.only_address(memory_core.scrub_details(line)), line)

    def test_a_memory_with_more_in_it_keeps_the_rest(self):
        line = memory_core.scrub_details("Sarah's number is 919-555-0142 and she picks up at noon")
        self.assertFalse(memory_core.only_address(line))
        self.assertEqual(line, "Sarah's number is %s and she picks up at noon" % SAYS)


class Saved(unittest.TestCase):
    """With the server's own book, through the hook it sets."""

    def setUp(self):
        helpers.reset_db()
        server.BOOK.clear()
        self.addCleanup(server.BOOK.clear)
        self.id = server.BOOK.add({"name": "Sarah Hollis", "relationship": "daughter", "phone": "919 555 0142",
                                   "cell": "(919) 555-0188", "email": ADDRESS, "address": "Rural Route 2 Box 40",
                                   "facebook": "Sarah.Hollis.99", "birthday": "03-14", "notes": "Takes her coffee black"})
        self.memory = server.mary_memory()
        self.addCleanup(self.memory.recent.clear)

    def test_the_book_is_matched_without_case_and_phones_by_digits(self):
        cases = {"mail it to rural route 2 box 40 please": "mail it to %s please" % SAYS,
                 "she's SARAH.HOLLIS.99 on there": "she's %s on there" % SAYS,
                 "ring 91 95 55 01 42 now": "ring %s now" % SAYS,
                 "her cell's 919 555 0188": "her cell's %s" % SAYS}
        for line, want in cases.items():
            self.assertEqual(memory_core.scrub_details(line), want)

    def test_names_relationships_birthdays_and_notes_stay(self):
        for line in ("Sarah Hollis is my daughter", "my daughter", "Sarah's birthday is March 14", "03-14",
                     "Takes her coffee black"):
            self.assertEqual(memory_core.scrub_details(line), line)

    def test_a_facebook_name_that_is_a_name_stays(self):
        for facebook in ("Sarah Hollis", "Grandma"):
            server.BOOK.update(self.id, {"facebook": facebook})
            self.assertEqual(memory_core.scrub_details("Sarah Hollis and Grandma came by"), "Sarah Hollis and Grandma came by")

    def test_a_town_alone_stays(self):
        server.BOOK.update(self.id, {"address": "Raleigh"})
        self.assertEqual(memory_core.scrub_details("she moved to Raleigh"), "she moved to Raleigh")

    def test_a_multi_line_address_goes_line_by_line(self):
        server.BOOK.update(self.id, {"address": "Rural Route 2 Box 40\nCary NC"})
        self.assertEqual(memory_core.scrub_details("it's Rural Route 2 Box 40"), "it's %s" % SAYS)

    def test_a_locked_book_is_skipped(self):
        with mock.patch.object(server.BOOK, "state", return_value="locked"):
            self.assertEqual(server._book_details(), [])
            self.assertEqual(memory_core.scrub_details("rural route 2 box 40"), "rural route 2 box 40")

    def test_a_failing_book_stops_nothing(self):
        with mock.patch.object(memory_core, "BOOK_DETAILS", side_effect=OSError("no")):
            self.assertEqual(memory_core.scrub_details("call 555-0142"), "call %s" % SAYS)

    def test_a_forgotten_value_stops_counting(self):
        server.BOOK.update(self.id, {"address": ""})
        self.assertEqual(memory_core.scrub_details("rural route 2 box 40"), "rural route 2 box 40")

    def test_memory_refuses_each_form(self):
        store = server.memory_store()
        for fact in ("919-555-0142", STREET, "Her address is 12 Maple Street", "mark.hollis@example.com",
                     "Rural Route 2 Box 40", "Sarah's number is 91 95 55 01 42"):
            self.assertIsNone(store.add(fact), fact)
            self.assertFalse(self.memory.add_fact(fact), fact)

    def test_the_tool_answers_like_the_address_one(self):
        for fact, note in (("919-555-0142", server.DETAIL_NOT_A_MEMORY), (STREET, server.DETAIL_NOT_A_MEMORY),
                           ("Rural Route 2 Box 40", server.DETAIL_NOT_A_MEMORY),
                           ("mark.hollis@example.com", server.ADDRESS_NOT_A_MEMORY)):
            out = server.mary_live_memory_call("remember_fact", {"fact": fact})
            self.assertEqual(out["response"], {"ok": False, "note": note})
        self.assertIn("never goes in your memories", server.DETAIL_NOT_A_MEMORY)

    def test_a_memory_with_a_detail_in_it_keeps_the_placeholder(self):
        line = "Sarah's number is 919-555-0142 and she picks up at noon"
        self.assertEqual(memory_core._clean(line), "Sarah's number is %s and she picks up at noon" % SAYS)
        self.assertIsNotNone(server.memory_store().add(line))

    def test_good_memories_are_saved(self):
        for line in ("I was born in 1942", "Room 214", "she's 87", "I have 3 kids", "I lived on Maple Street for years",
                     "Sarah's birthday is March 14"):
            self.assertIsNotNone(server.memory_store().add(line), line)

    def test_talk_history_holds_none_of_them(self):
        for text in ("my number's 919-555-0142", "I'm at 12 Maple Street", "it's mark.hollis@example.com",
                     "rural route 2 box 40"):
            self.memory.add_turn("user", text)
            self.memory.add_turn("model", "You said " + text)
        kept = json.dumps(self.memory.recent)
        for piece in ("919", "Maple", "hollis", "rural"):
            self.assertNotIn(piece, kept)
        self.assertIn(SAYS, kept)

    def test_old_talk_history_is_cleaned_on_load(self):
        self.memory.recent.append({"role": "user", "text": "my number's 919-555-0142", "at": ""})
        self.memory.save()
        self.memory._load()
        self.assertNotIn("919", json.dumps(self.memory.recent))


class Reports(unittest.TestCase):
    def test_the_report_and_spreadsheet_never_open_the_book(self):
        helpers.reset_db()
        helpers.incident(what="She waited an hour for help")
        used = []

        class Trap:
            def __getattr__(self, name):
                used.append(name)
                raise AssertionError("the book was opened: " + name)

        with mock.patch.object(server, "BOOK", Trap()):
            for path in ("/report", "/api/export.xlsx"):
                self.assertEqual(helpers.api("GET", path)[0], 200, path)
        self.assertEqual(used, [])

    def test_reports_py_has_no_way_to_it(self):
        source = (helpers.ROOT / "reports.py").read_text("utf-8")
        for word in ("BOOK", "address_book", "addressbook", "ctx.people"):
            self.assertNotIn(word, source)


class Logs(send_tests.Flow):
    def test_no_name_or_detail_after_a_send_and_a_read(self):
        wake = server.DATA / "wake.log"
        before = wake.read_text("utf-8") if wake.exists() else ""
        self.full_send("Mark")
        heard = "what's Mark's email address"
        args = {"action": "read_detail", "details": json.dumps({"person": "Mark", "field": "email"})}
        out = self.post("/api/mary/skills/call", {"name": "use_skill", "args": args, "heard": heard})
        self.assertEqual(out["response"]["value"], send_tests.ADDRESS)
        self.assertTrue(self.log.exists())
        for path in (self.log, self.host.log_path):
            text = path.read_text("utf-8") if path.exists() else ""
            self.assertNotIn(send_tests.ADDRESS.lower(), text.lower(), path.name)
            self.assertIsNone(re.search(r"\bmark\b|hollis", text, re.I), path.name)
        self.assertEqual(wake.read_text("utf-8") if wake.exists() else "", before)

    def test_a_log_line_with_a_detail_in_it_is_scrubbed(self):
        server.wake_log("book_tools_test", text="call 919-555-0142 at 12 Maple Street")
        line = (server.DATA / "wake.log").read_text("utf-8").splitlines()[-1]
        self.assertIn("book_tools_test", line)
        self.assertNotIn("919", line)
        self.assertNotIn("Maple", line)
        self.host._log("book_tools_test", detail="919-555-0142")
        self.assertNotIn("919", self.host.log_path.read_text("utf-8"))


class Words(unittest.TestCase):
    START, END = "- A saved person is a name to you.", "- They can ask you to read back what they saved."

    def lines(self):
        return (helpers.ROOT / "mary" / "instructions.md").read_text("utf-8")

    def test_only_her_book_lines_changed(self):
        head = subprocess.run(["git", "show", "HEAD:mary/instructions.md"], cwd=helpers.ROOT, capture_output=True)
        if head.returncode:
            self.skipTest("no git history here")
        old, new = head.stdout.decode("utf-8").replace("\r\n", "\n"), self.lines()
        self.assertEqual(new[:new.index(self.START)], old[:old.index(self.START)])
        self.assertEqual(new[new.index(self.END):], old[old.index(self.END):])

    def test_her_lines(self):
        text = self.lines()
        part = text[text.index(self.START):text.index(self.END)]
        for words in ('"Email my daughter" needs no address, so use the name.', "by name or relationship",
                      "only when their own words ask for that detail", "It never goes in your memories.",
                      "Don't recite the book or offer it on your own", '"It\'s in your book now."',
                      "If they say don't keep it, that's done.", "ask once. A yes does it.",
                      'Never say "gone" about a person.', "There's no Add button."):
            self.assertIn(words, part)
        self.assertNotIn("contact_address", text)
        self.assertNotIn("find_contact", text)

    def test_the_privacy_words(self):
        page = (helpers.ROOT / "web" / "index.html").read_text("utf-8")
        plan = (helpers.ROOT / "docs" / "messaging-plan.md").read_text("utf-8")
        table = plan[plan.index("## 6. Privacy"):plan.index("## 7. Costs")]
        for text in (page, table):
            self.assertIn("55 days on the paid tier", text)
            self.assertIn("aloud", text)
            self.assertIn("Address book", text)


if __name__ == "__main__":
    unittest.main()
