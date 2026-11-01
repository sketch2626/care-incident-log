from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M15c: the messages skill's contacts and keeping an address, run by a real SkillHost with a real send gate and a real
address book (M19) on a fake clock and a fake mailer. Full send flows are in their own tests."""
import base64
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import address_book
import mary
import secret_store
import send_gate
import skills_core

SKILLS = helpers.ROOT / "skills"
ADDRESS = "mark.hollis@gmail.com"
SPOKEN = "Mark dot Hollis at gmail dot com"


class FakeMailer:
    def __init__(self):
        self.sent = []

    def mint_ticket(self, *args):
        return "ticket"

    def __call__(self, skill, ticket, to, subject, body, pictures=()):
        self.sent.append((to, subject, body))
        return {"ok": True}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="contacts-", dir=helpers.TMP))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.settings = {}
        self.now = 1000.0
        self.mailer = FakeMailer()
        db = self.dir / "skills.db"
        self.host = skills_core.SkillHost(SKILLS, self.dir, lambda: sqlite3.connect(db), lambda: dict(self.settings),
                                          self.settings.update)
        self.host.load(is_blocked=mary.skill_blocked)
        self.assertIn("messages", self.host.skills, self.host.load_errors)
        self.host.gate = send_gate.SendGate(self.mailer, clock=lambda: self.now)
        self.host.mail_ready = lambda: True
        self.host.mailer = self.mailer
        self.host.book = address_book.AddressBook(self.dir, secret_store.SecretStore(self.dir))
        self.seen = []  # everything that goes near Gemini, or is said aloud

    @property
    def ctx(self):
        return self.host.context("messages")

    @property
    def mod(self):
        return self.host.skills["messages"].module

    def act(self, _tool, **args):
        self.last = self.host.call("messages__" + _tool, args)
        self.seen.append(json.dumps([self.last["response"], self.last["say"]]))
        return self.last["response"]

    def event(self, **event):
        self.last = self.host.on_event("messages", event)
        self.seen.append(json.dumps([self.last["response"], self.last["say"]]))
        return self.last["response"]

    def effect(self, kind):
        return next(e["data"] for e in self.last["effects"] if e["kind"] == kind)

    def letter(self, person="Mark"):
        self.act("plain_message", person=person, words="Thinking of you.", signature="Dad")

    def person(self, name, **fields):
        """Someone already in the book, as the Address book form leaves them."""
        self.assertTrue(self.ctx.people.keep(name, fields))

    def contact(self, name):
        """Their row in the book, by this exact name, hidden marks too."""
        return next((p for p in self.host.book.people(include_hidden=True) if p["name"] == name), None)

    def stored(self):
        store = self.ctx.store
        return json.dumps({key: store.get(key) for key in store.keys()})

    def everywhere(self):
        """The skill's store and the book together: everywhere an address could be kept."""
        return self.stored() + json.dumps(self.host.book.people(include_hidden=True))

    def send(self):
        """A plain message, from the look to the end of the count."""
        look = self.effect("look")["look"]
        self.event(type="look_up", look=look)
        self.host.her_words("When you say send, it goes to Mark's email. You'll have five seconds to stop it.")
        self.assertEqual(self.host.resident_said("send it")["action"], "count")
        self.now += 5.1
        self.event(type="count_done", look=look)

    def address_then_send(self, person="Mark"):
        self.letter(person)
        self.act("send_it")
        self.act("give_address", address=SPOKEN)
        self.act("address_right", right=True)
        self.send()


class FindTests(Base):
    def test_by_name_first_name_and_relationship_without_case(self):
        self.person(name="Mark Hollis", relationship="son")
        for name in ("mark hollis", "MARK", "Son", "my son"):
            r = self.act("find_person", name=name)
            self.assertEqual((r["known"], r["name"], r["relationship"], r["has_email"]),
                             (True, "Mark Hollis", "son", False), name)
        self.assertEqual(self.act("find_person", name="Tyler"), {"known": False})

    def test_a_full_name_never_lands_on_someone_else_with_that_first_name(self):
        self.person(name="Mark")
        self.assertFalse(self.act("find_person", name="Mark Jones")["known"])

    def test_two_hits_ask_with_names_only(self):
        self.person(name="Mark Hollis", phone="555-0100")
        self.person(name="Mark Jones")
        r = self.act("find_person", name="Mark")
        self.assertEqual(r["which"], ["Mark Hollis", "Mark Jones"])
        self.assertIn("Mark Hollis or Mark Jones", self.last["say"])
        self.assertNotIn("555", self.last["say"])

    def test_two_hits_on_a_send_ask_who(self):
        self.person(name="Mark Hollis")
        self.person(name="Mark Jones")
        self.letter()
        r = self.act("send_it")
        self.assertTrue(r["need_person"])
        self.assertEqual(self.ctx.send_state()["state"], "none")
        self.assertTrue(self.act("send_it", person="Mark Jones")["need_address"])

    def test_no_name_on_the_draft_asks_who(self):
        self.letter(person="")
        self.assertTrue(self.act("send_it")["need_person"])
        self.assertEqual(self.last["say"], "Who's it for?")

    def test_a_later_detail_merges_and_keeps_the_address(self):
        self.address_then_send()
        self.act("keep_address", keep=True)
        self.person(name="mark", phone="555-0100")
        self.assertEqual((self.contact("Mark")["email"], self.contact("Mark")["phone"]), (ADDRESS, "555-0100"))


class AddressTests(Base):
    def test_speech_makes_an_address(self):
        for said, made in ((SPOKEN, ADDRESS), ("MARK.Hollis@Gmail.com.", ADDRESS), ("m a r k at aol dot com", "mark@aol.com"),
                           ("capital Mark underscore one at yahoo dot com", "mark_1@yahoo.com"),
                           ("seven@aol.com", "seven@aol.com"), ("mark at at aol dot com", "mark@aol.com")):
            self.assertEqual(self.mod._spoken_address(said), made, said)
        for said in ("", "mark", "mark at gmail", "mark at gmail at aol dot com", None):
            self.assertIsNone(self.mod._spoken_address(said), said)

    def test_a_bad_address_is_asked_again_and_never_echoed(self):
        self.letter()
        r = self.act("give_address", address="mark at gmail")
        self.assertTrue(r["need_address"])
        self.assertNotIn("gmail", json.dumps(r))
        self.assertNotIn("address_wait", self.ctx.state)

    def test_only_give_address_spells_it(self):
        self.letter()
        r = self.act("send_it")
        self.assertIn("What's Mark's email address?", self.last["say"])
        self.assertTrue(r["need_address"])
        r = self.act("give_address", address=SPOKEN)
        self.assertEqual(r["spelled"], ADDRESS)
        self.assertIsNone(self.last["say"])
        self.assertEqual(self.effect("address_wait")["address"], ADDRESS)
        self.seen.clear()
        self.act("address_right", right=True)
        self.assertEqual(self.effect("look")["email"], ADDRESS)
        self.assertIn(ADDRESS, json.dumps(self.ctx.state["held"]))
        self.send()
        self.act("keep_address", keep=True)
        self.assertNotIn(ADDRESS, " ".join(self.seen))
        self.assertEqual(self.host.view("messages").count("gmail"), 0)
        self.act("find_person", name="Mark")
        self.assertNotIn(ADDRESS, " ".join(self.seen))
        self.assertTrue(self.last["response"]["has_email"])

    def test_no_means_ask_again(self):
        self.letter()
        self.act("give_address", address=SPOKEN)
        self.assertTrue(self.act("address_right", right=False)["need_address"])
        self.assertNotIn("address_wait", self.ctx.state)

    def test_a_typed_address_never_shows_in_a_result(self):
        self.letter()
        self.act("send_it")
        self.event(type="address", address=ADDRESS)
        self.assertEqual(self.ctx.send_state()["state"], "look")
        self.assertEqual(self.effect("look")["email"], ADDRESS)
        self.assertNotIn(ADDRESS, " ".join(self.seen))
        self.assertNotIn("spelled", self.last["response"])

    def test_view_says_where_a_send_is_with_no_address(self):
        self.letter()
        self.event(type="address", address=ADDRESS)
        self.assertIn("say send", self.host.view("messages"))
        self.assertNotIn("gmail", self.host.view("messages"))

    def test_a_saved_draft_never_holds_an_address(self):
        self.address_then_send()
        self.assertNotIn(ADDRESS, self.stored())  # the book is the one place it's kept
        self.assertNotIn(ADDRESS, json.dumps(self.ctx.state.get("draft")))


class KeepTests(Base):
    def test_a_first_send_keeps_it_and_says_so_with_no_question(self):
        self.address_then_send()
        self.assertEqual(self.mailer.sent[0][0], ADDRESS)
        self.assertEqual(self.last["say"], "Sent to Mark. It's in your book now. Would you like it printed so it can be mailed?")
        self.assertTrue(self.last["response"]["kept"])
        self.assertNotIn("keep_question", self.last["response"])
        self.assertEqual(self.contact("Mark")["email"], ADDRESS)
        self.assertTrue(self.contact("Mark")["asked"])
        self.assertEqual(self.ctx.state["just_sent"]["person"], "Mark")
        self.letter()
        self.act("send_it")
        self.send()
        self.assertEqual(self.last["say"], "Sent to Mark. Would you like it printed so it can be mailed?")
        self.assertEqual(len(self.mailer.sent), 2)

    def test_dont_keep_it_takes_it_back_and_it_is_not_kept_again(self):
        self.address_then_send()
        self.assertFalse(self.act("keep_address", keep=False)["kept"])
        self.assertEqual(self.last["say"], "All right.")
        self.assertTrue(self.contact("Mark")["no_keep"])
        self.assertNotIn(ADDRESS, self.everywhere())
        self.assertNotIn("just_sent", self.ctx.state)
        self.letter()  # the same words again: the address is needed again, and it isn't kept
        self.assertTrue(self.act("send_it")["need_address"])
        self.act("give_address", address=SPOKEN)
        self.act("address_right", right=True)
        self.send()
        self.assertEqual(self.last["say"], "Sent to Mark. Would you like it printed so it can be mailed?")
        self.assertNotIn(ADDRESS, self.everywhere())

    def test_a_no_keep_from_before_is_respected(self):
        self.assertTrue(self.ctx.people.unkeep("Mark"))
        self.address_then_send()
        self.assertEqual(self.mailer.sent[0][0], ADDRESS)
        self.assertEqual(self.last["say"], "Sent to Mark. Would you like it printed so it can be mailed?")
        self.assertNotIn(ADDRESS, self.everywhere())
        self.assertNotIn("just_sent", self.ctx.state)

    def test_a_stale_asked_flag_no_longer_stops_a_keep(self):
        self.assertIsNotNone(self.ctx.people.keep("Mark", {"asked": True}))
        self.address_then_send()
        self.assertEqual(self.contact("Mark")["email"], ADDRESS)

    def test_keep_true_after_a_send_is_harmless_and_dont_keep_it_still_works(self):
        self.address_then_send()
        self.assertTrue(self.act("keep_address", keep=True)["kept"])
        self.assertEqual(self.contact("Mark")["email"], ADDRESS)
        self.assertFalse(self.act("keep_address", keep=False)["kept"])
        self.assertEqual(self.contact("Mark")["email"], "")

    def test_dont_keep_it_means_only_the_latest_send(self):
        self.address_then_send()
        self.assertIsNotNone(self.ctx.people.keep("Amy", {"email": "amy.park@example.org"}))
        self.letter("Amy")
        self.act("send_it")
        look = self.effect("look")["look"]
        self.event(type="look_up", look=look)
        self.host.her_words(self.ctx.send_state()["line"])
        self.assertEqual(self.host.resident_said("send it")["action"], "count")
        self.now += 5.1
        self.event(type="count_done", look=look)
        self.assertNotIn("just_sent", self.ctx.state)
        self.act("keep_address", keep=False)
        self.assertEqual(self.contact("Mark")["email"], ADDRESS)
        self.assertEqual(self.contact("Amy")["email"], "amy.park@example.org")

    def test_close_clears_what_was_held(self):
        self.address_then_send()
        self.act("close")
        self.assertNotIn("just_sent", self.ctx.state)
        self.assertNotIn(ADDRESS, self.stored())
        self.assertNotIn(ADDRESS, json.dumps(self.ctx.state, default=str))

    def test_keep_with_nothing_held_keeps_nothing(self):
        self.assertFalse(self.act("keep_address", keep=True)["kept"])


class BookTests(Base):
    """M19: someone in the book. The address reaches the gate and the page from the core, and the skill never holds it."""

    def saved(self):
        self.assertIsNotNone(self.ctx.people.keep("Mark", {"email": ADDRESS}))

    def lock_book(self):
        self.host.book.lock()
        secret_store.SecretStore(self.dir).delete(address_book.KEY_NAME)
        self.assertEqual(self.host.book.state(), "locked")

    def test_the_look_carries_the_address_and_the_state_holds_none(self):
        self.saved()
        self.letter()
        self.assertTrue(self.act("send_it")["look_up"])
        self.assertEqual(self.effect("look")["email"], ADDRESS)
        self.assertNotIn(ADDRESS, json.dumps(self.ctx.state, default=str))
        self.assertNotIn("address", self.ctx.state["held"])
        self.assertNotIn(ADDRESS, " ".join(self.seen))
        self.send()
        self.assertEqual(self.mailer.sent[0][0], ADDRESS)
        self.assertEqual(self.last["say"], "Sent to Mark. Would you like it printed so it can be mailed?")
        self.assertNotIn(ADDRESS, json.dumps(self.ctx.state, default=str))

    def test_a_locked_book_says_so_and_claims_nothing(self):
        self.saved()
        self.lock_book()
        self.letter()
        self.assertTrue(self.act("send_it")["need_address"])
        self.assertEqual(self.last["say"], "Your address book is locked right now, so I can't look them up. A helper can "
                                           "open it. What's Mark's email address? You can say it, or a helper can type it.")
        self.act("give_address", address=SPOKEN)
        self.act("address_right", right=True)
        self.send()
        self.assertEqual(self.mailer.sent[0][0], ADDRESS)
        self.assertEqual(self.last["say"], "Sent to Mark. Would you like it printed so it can be mailed?")
        self.assertNotIn("kept", self.last["response"])
        self.assertNotIn("just_sent", self.ctx.state)

    def test_a_locked_book_never_sounds_as_if_they_are_gone(self):
        self.saved()
        self.lock_book()
        for tool, args in (("find_person", {"name": "Mark"}), ("read_detail", {"person": "Mark", "field": "email"})):
            out = self.act(tool, **args)
            self.assertTrue(out["book_locked"], tool)
            self.assertEqual(self.last["say"], "Your address book is locked right now, so I can't look them up. A helper "
                                               "can open it.")

    def test_a_locked_book_keeps_nothing_and_says_so(self):
        self.saved()
        self.lock_book()
        self.act("give_address", address=SPOKEN, person="Tyler")
        self.act("address_right", right=True)
        self.assertFalse(self.act("keep_address", keep=True)["kept"])
        self.assertIn("locked", self.last["say"])


class HeldSendTests(Base):
    """The picture, and what takes a look away. The whole send has its own tests."""

    def card(self):
        self.act("show_fronts", person="Mark")
        self.act("pick_front", choice="1")
        self.act("set_words", words="Happy birthday, son.", signature="Dad")
        self.event(type="address", address=ADDRESS)
        self.assertIn("make_mail", [e["kind"] for e in self.last["effects"]])
        self.assertTrue(self.ctx.state["draft"]["look_wanted"])
        self.assertEqual(self.ctx.send_state()["state"], "none")

    def picture(self):
        draft = self.ctx.state["draft"]
        data = base64.b64encode(b"\xff\xd8\xff\xe0" + bytes(200)).decode("ascii")
        self.event(type="picture", id=draft["id"], part="mail", rev=draft["rev"], seq=0, data=data, last=True)

    def test_the_picture_landing_brings_the_look(self):
        self.card()
        self.picture()
        self.assertEqual(self.ctx.send_state()["state"], "look")
        self.assertEqual(self.effect("look")["front"], "card-%s-front.svg" % self.ctx.state["draft"]["id"])
        self.assertEqual(self.last["say"], self.ctx.send_state()["line"])
        self.assertNotIn("look_wanted", self.ctx.state["draft"])
        self.assertEqual(self.ctx.state["draft"]["mail_rev"], self.ctx.state["draft"]["rev"])

    def test_new_words_take_the_look_and_the_wait_away(self):
        self.card()
        self.act("set_words", words="Happy birthday, Mark.", signature="Dad")
        self.assertNotIn("look_wanted", self.ctx.state["draft"])
        self.picture()
        self.assertEqual(self.ctx.send_state()["state"], "none")  # an old picture brings nothing up
        self.letter()
        self.act("send_it")
        self.assertEqual(self.ctx.send_state()["state"], "look")
        self.act("plain_message", person="Mark", words="Changed my mind.", signature="Dad")
        self.assertEqual(self.ctx.send_state()["state"], "none")
        self.assertNotIn("held", self.ctx.state)

    def test_close_takes_the_look_away(self):
        self.letter()
        self.event(type="address", address=ADDRESS)
        self.act("close")
        self.assertEqual(self.ctx.send_state()["state"], "none")

    def test_it_asks_for_money_so_it_pauses(self):
        self.act("plain_message", person="Mark", words="Please send me money by Western Union.", signature="Dad")
        r = self.act("send_it")
        self.assertTrue(r["paused"])
        self.assertIn("This asks for money. I won't send that.", self.last["say"])
        self.assertEqual(self.ctx.send_state()["state"], "none")

    def test_the_plain_line_is_said_once(self):
        self.act("plain_message", person="Mark", words="Hello.", signature="Dad")
        self.assertNotIn("what I've got", self.last["say"])
        self.event(type="address", address=ADDRESS)
        self.assertTrue(self.last["say"].startswith("Here's what I've got. When you say send"))


class ForgetTests(Base):
    def kept(self):
        self.address_then_send()

    def test_forget_marks_address_removes_only_the_email(self):
        self.kept()
        self.person(name="Mark", phone="555-0100")
        self.assertEqual(self.mod.forget_matches(self.ctx, "Mark's address"), 1)
        out = self.mod.on_forget(self.ctx, "Mark’s email", False)
        self.assertEqual(out, {"addresses": [ADDRESS], "texts": []})
        self.assertEqual((self.contact("Mark")["email"], self.contact("Mark")["phone"]), ("", "555-0100"))
        self.assertTrue(self.contact("Mark")["no_keep"])  # so a later send doesn't bring it back
        self.assertEqual(self.mod.forget_matches(self.ctx, "Mark's address"), 0)

    def test_forget_mark_removes_the_whole_contact(self):
        self.kept()
        out = self.mod.on_forget(self.ctx, "Mark", False)
        self.assertEqual((out["addresses"], out["texts"]), ([ADDRESS], ["Mark"]))
        self.assertIsNone(self.contact("Mark"))
        self.assertEqual(self.host.book.people(include_hidden=True), [])

    def test_forget_reaches_a_no_keep_record(self):
        self.address_then_send()
        self.act("keep_address", keep=False)
        self.assertEqual(self.mod.forget_matches(self.ctx, "Mark"), 1)
        self.assertEqual(self.mod.on_forget(self.ctx, "mark", False), {"addresses": [], "texts": ["Mark"]})
        self.assertIsNone(self.contact("Mark"))

    def test_forget_clears_an_address_held_in_memory(self):
        self.address_then_send()
        self.assertEqual(self.mod.on_forget(self.ctx, "Mark", False)["addresses"], [ADDRESS])
        self.assertNotIn("just_sent", self.ctx.state)

    def test_own_name_needs_the_full_name(self):
        self.person(name="Mark Hollis")
        self.assertEqual(self.mod.on_forget(self.ctx, "Mark", True), {"addresses": [], "texts": []})
        self.assertEqual(self.mod.on_forget(self.ctx, "Mark Hollis", True)["texts"], ["Mark Hollis"])

    def test_everything_leaves_the_book_and_clears_what_is_held(self):
        self.kept()
        self.person(name="Ann")
        self.assertEqual(self.mod.forget_matches(self.ctx, "everything"), 0)
        out = self.mod.on_forget(self.ctx, "everything", False)
        self.assertEqual(out, {"addresses": [ADDRESS], "texts": []})  # the one held in memory, so mail.log still clears
        self.assertNotIn("just_sent", self.ctx.state)
        self.assertEqual(self.contact("Mark")["email"], ADDRESS)
        self.assertIsNotNone(self.contact("Ann"))

    def test_nothing_about_a_stranger(self):
        self.kept()
        self.assertEqual(self.mod.forget_matches(self.ctx, "the fishing trip"), 0)
        self.assertEqual(self.mod.on_forget(self.ctx, "the fishing trip", False), {"addresses": [], "texts": []})
        self.assertEqual(self.contact("Mark")["email"], ADDRESS)


if __name__ == "__main__":
    unittest.main()
