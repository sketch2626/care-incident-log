from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M15c: the messages skill's contacts and the keep question, run by a real SkillHost with a real send gate on a fake
clock and a fake mailer. Full send flows are in their own tests."""
import base64
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import mary
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

    def contact(self, name):
        return self.ctx.store.get("contact-" + self.mod._contact_slug(name))

    def stored(self):
        store = self.ctx.store
        return json.dumps({key: store.get(key) for key in store.keys()})

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
        self.act("save_contact", name="Mark Hollis", relationship="son")
        for name in ("mark hollis", "MARK", "Son", "my son"):
            r = self.act("find_contact", name=name)
            self.assertEqual((r["known"], r["name"], r["relationship"], r["has_email"]),
                             (True, "Mark Hollis", "son", False), name)
        self.assertEqual(self.act("find_contact", name="Tyler"), {"known": False})

    def test_a_full_name_never_lands_on_someone_else_with_that_first_name(self):
        self.act("save_contact", name="Mark")
        self.assertFalse(self.act("find_contact", name="Mark Jones")["known"])

    def test_two_hits_ask_with_names_only(self):
        self.act("save_contact", name="Mark Hollis", phone="555-0100")
        self.act("save_contact", name="Mark Jones")
        r = self.act("find_contact", name="Mark")
        self.assertEqual(r["which"], ["Mark Hollis", "Mark Jones"])
        self.assertIn("Mark Hollis or Mark Jones", self.last["say"])
        self.assertNotIn("555", self.last["say"])

    def test_two_hits_on_a_send_ask_who(self):
        self.act("save_contact", name="Mark Hollis")
        self.act("save_contact", name="Mark Jones")
        self.letter()
        r = self.act("send_it")
        self.assertTrue(r["need_person"])
        self.assertEqual(self.ctx.send_state()["state"], "none")
        self.assertTrue(self.act("send_it", person="Mark Jones")["need_address"])

    def test_no_name_on_the_draft_asks_who(self):
        self.letter(person="")
        self.assertTrue(self.act("send_it")["need_person"])
        self.assertEqual(self.last["say"], "Who's it for?")

    def test_save_contact_merges_and_keeps_the_address(self):
        self.address_then_send()
        self.act("keep_address", keep=True)
        self.act("save_contact", name="mark", phone="555-0100")
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
        self.act("find_contact", name="Mark")
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
        self.assertNotIn(ADDRESS, self.stored())  # nothing is kept until they say so
        self.assertNotIn(ADDRESS, json.dumps(self.ctx.state.get("draft")))


class KeepTests(Base):
    def test_asked_once_and_a_yes_keeps_it(self):
        self.address_then_send()
        self.assertEqual(self.mailer.sent[0][0], ADDRESS)
        self.assertIn("Sent to Mark. Keep Mark's address for next time?", self.last["say"])
        self.assertTrue(self.contact("Mark")["asked"])
        self.assertEqual(self.contact("Mark")["email"], "")
        self.assertTrue(self.act("keep_address", keep=True)["kept"])
        self.assertNotIn("just_sent", self.ctx.state)
        self.assertEqual(self.contact("Mark")["email"], ADDRESS)
        self.letter()
        self.act("send_it")
        self.send()
        self.assertEqual(self.last["say"], "Sent to Mark. Would you like it printed so it can be mailed?")
        self.assertEqual(len(self.mailer.sent), 2)

    def test_a_no_never_stores_it_and_it_is_not_asked_again(self):
        self.address_then_send()
        self.assertFalse(self.act("keep_address", keep=False)["kept"])
        self.assertTrue(self.contact("Mark")["no_keep"])
        self.assertNotIn(ADDRESS, self.stored())
        self.assertNotIn("just_sent", self.ctx.state)
        self.letter()  # the same words again: the address is needed again, and the question isn't asked
        self.assertTrue(self.act("send_it")["need_address"])
        self.act("give_address", address=SPOKEN)
        self.act("address_right", right=True)
        self.send()
        self.assertNotIn("Keep", self.last["say"])
        self.assertNotIn(ADDRESS, self.stored())

    def test_close_clears_what_was_held(self):
        self.address_then_send()
        self.act("close")
        self.assertNotIn("just_sent", self.ctx.state)
        self.assertNotIn(ADDRESS, self.stored())

    def test_keep_with_nothing_held_keeps_nothing(self):
        self.assertFalse(self.act("keep_address", keep=True)["kept"])


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
        self.act("keep_address", keep=True)

    def test_forget_marks_address_removes_only_the_email(self):
        self.kept()
        self.act("save_contact", name="Mark", phone="555-0100")
        self.assertEqual(self.mod.forget_matches(self.ctx, "Mark's address"), 1)
        out = self.mod.on_forget(self.ctx, "Mark’s email", False)
        self.assertEqual(out, {"addresses": [ADDRESS], "texts": []})
        self.assertEqual((self.contact("Mark")["email"], self.contact("Mark")["phone"]), ("", "555-0100"))
        self.assertEqual(self.mod.forget_matches(self.ctx, "Mark's address"), 0)

    def test_forget_mark_removes_the_whole_contact(self):
        self.kept()
        out = self.mod.on_forget(self.ctx, "Mark", False)
        self.assertEqual((out["addresses"], out["texts"]), ([ADDRESS], ["Mark"]))
        self.assertIsNone(self.contact("Mark"))
        self.assertEqual(self.ctx.store.get("contacts"), [])

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
        self.act("save_contact", name="Mark Hollis")
        self.assertEqual(self.mod.on_forget(self.ctx, "Mark", True), {"addresses": [], "texts": []})
        self.assertEqual(self.mod.on_forget(self.ctx, "Mark Hollis", True)["texts"], ["Mark Hollis"])

    def test_everything(self):
        self.kept()
        self.act("save_contact", name="Ann")
        self.assertEqual(self.mod.forget_matches(self.ctx, "everything"), 2)
        out = self.mod.on_forget(self.ctx, "everything", False)
        self.assertEqual((out["addresses"], out["texts"]), ([ADDRESS], ["Ann", "Mark"]))
        self.assertEqual(self.ctx.store.get("contacts"), [])

    def test_nothing_about_a_stranger(self):
        self.kept()
        self.assertEqual(self.mod.forget_matches(self.ctx, "the fishing trip"), 0)
        self.assertEqual(self.mod.on_forget(self.ctx, "the fishing trip", False), {"addresses": [], "texts": []})
        self.assertEqual(self.contact("Mark")["email"], ADDRESS)


if __name__ == "__main__":
    unittest.main()
