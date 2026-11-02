from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M15c, end to end: the real server routes, a real SkillHost with a real send gate on a fake clock, a real Mailer talking
to a fake loopback TLS SMTP server, and a fake Gemini. No real mail, accounts or keys."""
import address_book
import base64
import json
import shutil
import sqlite3
import ssl
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import mail_core
import mary
import memory_core
import memory_dates
import secret_store
import send_gate
import server
import skills_core
from tests import test_mail_core as tmc
from tests.test_mary_talk import FakeGemini

SKILLS = helpers.ROOT / "skills"
ADDRESS = "mark.hollis@gmail.com"
SPOKEN = "mark dot hollis at gmail dot com"
AMY = "amy.park@example.org"
NO_EFFECTS = "effects"


class CutList(list):
    """The fake SMTP server's messages list: it keeps the message, then the connection drops before the 250."""

    def append(self, item):
        super().append(item)
        raise OSError("cut")


def plain(value):
    """What goes near Gemini or is said aloud: everything except the effects, which only the page sees."""
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items() if key != NO_EFFECTS}
    if isinstance(value, list):
        return [plain(item) for item in value]
    return value


class Flow(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        Path(server.DATA, "mary", "memory.json").unlink(missing_ok=True)
        self.dir = Path(tempfile.mkdtemp(prefix="m15c-send-", dir=helpers.TMP))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.now = 1000.0
        self.fake = tmc.FakeSMTP()
        self.addCleanup(self.fake.close)
        self.log = self.dir / "log" / "mail.log"
        servers = {"gmail": ("127.0.0.1", self.fake.port), "yahoo": ("127.0.0.1", self.fake.port)}
        self.mailer = mail_core.Mailer(secret_store.SecretStore(self.dir / "secrets"), self.log, servers=servers,
                                       tls_context=ssl.create_default_context(cafile=str(tmc.CERT)))
        self.mailer.connect_account("me@example.com", "gmail", tmc.PASSWORD)
        db = self.dir / "skills.db"
        self.settings = {}
        self.host = skills_core.SkillHost(SKILLS, self.dir, lambda: sqlite3.connect(db), lambda: dict(self.settings),
                                          self.settings.update)
        self.host.load(is_blocked=mary.skill_blocked)
        self.assertIn("messages", self.host.skills, self.host.load_errors)
        self.host.mailer = self.mailer.send_for_skill
        self.host.gate = send_gate.SendGate(self.mailer, clock=lambda: self.now)
        self.host.mail_ready = lambda: True
        self.host.book = address_book.AddressBook(self.dir, secret_store.SecretStore(self.dir))
        self.addCleanup(setattr, memory_core, "FORGET_REACH", memory_core.FORGET_REACH)
        memory_core.FORGET_REACH = skills_core.ForgetReach(self.host)
        server.set_skill_host_for_tests(self.host)
        self.addCleanup(server.set_skill_host_for_tests, None)
        self.gemini = FakeGemini()
        self.addCleanup(setattr, mary, "_gemini_stream", mary._gemini_stream)
        mary._gemini_stream = self.gemini
        status, body, _ = helpers.api("PUT", "/api/settings", {"gemini_key": "test-key"})
        self.assertEqual(status, 200, body)
        self.seen = []  # everything that goes near Gemini or is said aloud, without the page's effects
        self.look = None

    # ----- routes -----
    @property
    def ctx(self):
        return self.host.context("messages")

    @property
    def mod(self):
        return self.host.skills["messages"].module

    def post(self, path, body):
        status, out, _ = helpers.api("POST", path, body)
        self.assertEqual(status, 200, out)
        self.seen.append(json.dumps(plain(out)))
        return out

    def call(self, tool, **args):
        """What Gemini does in Live: a tool call."""
        self.last = self.post("/api/mary/skills/call", {"name": "messages__" + tool, "args": args})
        return self.last

    def event(self, **event):
        """What the page does: a tap or a finished piece of work."""
        self.last = self.post("/api/mary/skills/messages/event", {"event": event})
        return self.last

    def heard(self, text):
        """Live's transcript of the resident. Returns the gate's action, or None."""
        self.last = self.post("/api/mary/heard", {"text": text})
        return (self.last.get("send") or {}).get("action")

    def said(self, text):
        self.post("/api/mary/live/said", {"text": text})

    def talk(self, text, chunks=("[mood: calm] Okay.",)):
        """Normal talk, with the fake Gemini."""
        self.gemini.chunks = list(chunks)
        self.last = self.post("/api/mary/talk", {"text": text})
        return self.last

    def effects(self, out=None):
        out = out or self.last
        listed = out.get("effects") or (out.get("send") or {}).get("effects") or []
        return {e["kind"]: e["data"] for e in listed}

    def sent(self):
        return len(self.fake.messages)

    def state(self):
        return self.ctx.send_state()["state"]

    def stored(self):
        store = self.ctx.store
        return json.dumps({key: store.get(key) for key in store.keys()})

    def everywhere(self):
        """The skill's store and the book together: everywhere an address could be kept."""
        return self.stored() + json.dumps(self.host.book.people(include_hidden=True))

    def log_rows(self):
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    # ----- setting up a send -----
    def keep_email(self, person="Mark", address=ADDRESS, relationship=""):
        fields = {"email": address, **({"relationship": relationship} if relationship else {})}
        self.assertIsNotNone(self.ctx.people.keep(person, fields))

    def ready(self, person="Mark", words="Thinking of you.", saved=True, shown=True, line=True, address=SPOKEN):
        """A plain message with the look up, and the look drawn. Returns the send_it say."""
        self.event(type="left")  # an older look from this test is let go
        if saved:
            self.keep_email(person)
        self.call("plain_message", person=person, words=words, signature="Dad")
        out = self.call("send_it")
        if out["response"].get("need_address"):
            self.call("give_address", address=address, person=person)
            out = self.call("address_right", right=True)
        self.look = self.effects(out)["look"]["look"]
        if shown:
            self.event(type="look_up", look=self.look)
        if line:
            self.said(out["say"])
        return out["say"]

    def count(self, words="now send it"):
        self.assertEqual(self.heard(words), "count")

    def done(self):
        return self.event(type="count_done", look=self.look)

    def full_send(self, person="Mark", **kw):
        self.ready(person, **kw)
        self.count()
        self.now += 5.0
        return self.done()

    def card(self):
        self.keep_email()
        self.call("show_fronts", person="Mark")
        self.call("pick_front", choice="1")
        self.call("set_words", words="Happy birthday, son.", signature="Dad")
        out = self.call("send_it")
        self.assertIn("make_mail", self.effects(out))
        draft = self.ctx.state["draft"]
        jpeg = base64.b64encode(b"\xff\xd8\xff\xe0" + bytes(300)).decode("ascii")
        out = self.event(type="picture", id=draft["id"], part="mail", rev=draft["rev"], seq=0, data=jpeg, last=True)
        self.look = self.effects(out)["look"]["look"]
        self.event(type="look_up", look=self.look)
        self.said(out["say"])


class NothingSendsWithoutTheYes(Flow):
    def test_one_look_with_no_yes(self):
        self.ready()
        for _ in range(20):
            self.call("send_it")
        self.assertNotEqual(self.state(), "counting")
        self.talk("Is it nice out?", chunks=("[mood: happy] I sent it for you, it's on its way!",))
        self.done()  # the right look, no yes
        self.now += 6
        self.done()
        self.event(type="tap_send")  # no misses yet
        self.done()
        self.assertEqual((self.sent(), self.state()), (0, "look"))

    def test_a_tap_before_two_misses(self):
        self.ready()
        self.assertIsNone(self.heard("banana split"))  # one miss
        self.event(type="tap_send")
        self.assertEqual(self.state(), "look")
        self.now += 6
        self.done()
        self.assertEqual(self.sent(), 0)


class ChattyWords(Flow):
    PHRASES = ("okay", "sounds good", "yes", "should I send it?", "send it tomorrow", "don't send it", "send it to Tyler")

    def test_live(self):
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                self.ready()
                self.assertNotEqual(self.heard(phrase), "count")
                self.assertEqual(self.state(), "look")
                self.now += 6
                self.done()
        self.assertEqual(self.sent(), 0)

    def test_normal(self):
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                self.ready()
                out = self.talk(phrase)
                self.assertNotIn("count", self.effects(out))
                self.assertEqual(self.state(), "look")
                self.now += 6
                self.done()
        self.assertEqual(self.sent(), 0)


class OrderIsEnforced(Flow):
    def test_look_then_line_then_yes(self):
        line = self.ready(shown=False, line=False)
        self.assertIsNone(self.heard("send it"))  # the page hasn't drawn it
        self.assertEqual(self.state(), "look")
        self.event(type="look_up", look=self.look)
        self.assertEqual(self.heard("send it"), "say_line")  # her line wasn't said yet: scripted, no count
        self.assertIn("five seconds", self.last["send"]["say"])
        self.assertEqual(self.state(), "look")
        self.said(self.last["send"]["say"])
        self.assertEqual(self.heard("send it"), "count")

    def test_wrong_look_id_is_not_shown(self):
        self.ready(shown=False)
        self.assertFalse(self.event(type="look_up", look="not-it")["response"]["ok"])
        self.assertIsNone(self.heard("send it"))


class SmoothPath(Flow):
    def check_message(self, picture):
        self.assertEqual(self.sent(), 1)
        message = tmc.parse(self.fake.messages[0])
        self.assertEqual(message["To"], ADDRESS)
        self.assertEqual(message["Subject"], "A birthday card from Dad" if picture else "A message from Dad")
        body = message.get_body(("plain",)).get_content().splitlines()
        body = "\n".join(body).strip()
        self.assertEqual(body, ("Happy birthday, son." if picture else "Thinking of you.") + "\n\nDad")
        raw = self.fake.messages[0].decode("utf-8", "replace")
        for tag in ("Mary", "Care Incident", "sent with", "Sent from"):
            self.assertNotIn(tag, raw)
        kinds = [part.get_content_type() for part in message.walk() if part.get_content_maintype() == "image"]
        self.assertEqual(kinds, ["image/jpeg"] if picture else [])

    def finish(self):
        self.count()
        self.assertEqual(self.sent(), 0)
        self.now += 5.0
        out = self.done()
        self.assertTrue(out["say"].startswith("Sent to Mark."), out["say"])
        self.assertIn("sent", self.effects(out))
        self.assertEqual(self.effects(out)["sent"]["name"], "Mark")
        return out

    def test_plain_message(self):
        self.ready()
        self.finish()
        self.check_message(False)
        rows = self.log_rows()
        self.assertEqual([(r["to"], r["ok"]) for r in rows], [(mail_core.address_mark(ADDRESS), True)])  # M18
        text = self.log.read_text(encoding="utf-8")
        for secret in ("Thinking of you", "A message from", "Dad"):
            self.assertNotIn(secret, text)

    def test_card_with_its_picture(self):
        self.card()
        self.finish()
        self.check_message(True)

    def test_normal_talk_counts_too(self):
        self.ready()
        out = self.talk("now send it")
        self.assertIn("count", self.effects(out))
        self.assertEqual(len(self.gemini.bodies), 1)  # D1: the count line goes through her, as a turn note only
        self.assertNotIn("tools", self.gemini.bodies[0])
        self.assertIn("The app just did this", self.gemini.bodies[0]["systemInstruction"]["parts"][0]["text"])
        self.now += 5.0
        self.assertTrue(self.done()["say"].startswith("Sent to Mark."))
        self.assertEqual(self.sent(), 1)


class UndoAtAnySecond(Flow):
    def test_tap_undo(self):
        for t in (0, 1, 2, 3, 4, 4.9):
            with self.subTest(t=t):
                self.ready()
                self.count()
                self.now += t
                out = self.event(type="undo")
                self.assertIn("look", self.effects(out))
                self.now += 6
                self.done()
        self.assertEqual(self.sent(), 0)

    def test_spoken_stop_and_undo(self):
        for word in ("stop", "undo"):
            for t in (0, 2, 4.9):
                with self.subTest(word=word, t=t):
                    self.ready()
                    self.count()
                    self.now += t
                    self.assertEqual(self.heard(word), "stopped")
                    self.now += 6
                    self.done()
        self.assertEqual(self.sent(), 0)

    def test_early_and_late_count_done(self):
        self.ready()
        self.count()
        self.now += 4.9
        self.assertTrue(self.done()["response"].get("stale"))
        self.assertEqual(self.sent(), 0)
        self.now += 26.2  # 31.1 s after the yes: too old
        self.assertTrue(self.done()["response"].get("stale"))
        self.assertEqual(self.sent(), 0)

    def test_after_undo_the_next_yes_counts_again(self):
        self.ready()
        self.count()
        self.event(type="undo")
        self.count()
        self.now += 5
        self.done()
        self.assertEqual(self.sent(), 1)


class EmergencyDuringTheCount(Flow):
    WORDS = "I'm having a heart attack"

    def test_live(self):
        self.ready()
        self.count()
        self.now += 2
        self.assertTrue(mary.is_emergency(self.WORDS))
        out = self.post("/api/mary/heard", {"text": self.WORDS})
        self.assertTrue(out["emergency"])
        self.assertTrue(out["steps"])  # the emergency steps come back for the screen
        self.assertNotIn("say", out)
        self.assertEqual(self.state(), "look")
        self.now += 6
        self.done()
        self.assertEqual(self.sent(), 0)

    def test_normal(self):
        self.ready()
        self.count()
        out = self.talk(self.WORDS)
        self.assertTrue(out["emergency"])
        self.assertTrue(out["text"])
        self.assertEqual(self.state(), "look")
        self.now += 6
        self.done()
        self.assertEqual(self.sent(), 0)


class TheTap(Flow):
    def test_two_misses_open_the_tap(self):
        self.ready()
        self.assertIsNone(self.heard("banana split"))
        self.assertEqual(self.heard("mumble jumble"), "tap")
        self.assertIn("tap", self.effects())
        self.assertEqual(self.state(), "look")
        out = self.event(type="tap_send")
        self.assertIn("count", self.effects(out))
        self.assertEqual(self.state(), "counting")
        self.now += 5
        self.done()
        self.assertEqual(self.sent(), 1)

    def test_a_garbled_line_is_a_miss(self):
        self.ready()
        self.post("/api/mary/heard", {"text": "สวัสดี"})
        self.assertEqual(self.heard("こんにちは"), "tap")

    def test_gemini_cannot_open_or_press_it(self):
        self.ready()
        for _ in range(3):
            out = self.call("send_it")
            self.assertNotIn("tap", self.effects(out))
        out = self.call("tap_send")  # not a tool at all
        self.assertNotEqual(out["response"].get("counting"), True)
        self.assertNotIn("count", self.effects(out))
        self.assertEqual(self.state(), "look")
        self.assertEqual(self.event(type="tap_send")["response"].get("ignored"), True)
        self.now += 6
        self.done()
        self.assertEqual(self.sent(), 0)


class TicketsUsedOnce(Flow):
    def test_second_count_done_sends_nothing(self):
        self.full_send()
        self.assertEqual(self.sent(), 1)
        self.assertTrue(self.done()["response"].get("stale"))
        self.now += 10
        self.assertTrue(self.done()["response"].get("stale"))
        self.assertEqual((self.sent(), len(self.mailer._tickets)), (1, 0))

    def test_failed_send_then_a_fresh_yes(self):
        self.fake.mode = "reject"
        out = self.full_send()
        self.assertFalse(out["response"].get("sent"))
        self.assertEqual(self.sent(), 0)
        self.assertEqual(len(self.mailer._tickets), 0)
        self.assertTrue(self.done()["response"].get("stale"))  # the look is used up
        self.fake.mode = "ok"
        self.now += 100
        self.assertIsNone(self.heard("send it"))  # nothing is up, so the words do nothing
        self.assertEqual(self.sent(), 0)
        self.ready(saved=False)  # a fresh look, a fresh yes
        self.count()
        self.now += 5
        self.assertTrue(self.done()["say"].startswith("Sent to Mark."))
        self.assertEqual((self.sent(), len(self.mailer._tickets)), (1, 0))

    def test_skills_cannot_mint(self):
        self.assertIn("mint_ticket", skills_core.FORBIDDEN_NAMES)
        self.assertIn("gate", skills_core.FORBIDDEN_NAMES)


class Unsure(Flow):
    def test_cut_after_data(self):
        self.fake.messages = CutList()
        self.ready()
        self.count()
        self.now += 5
        out = self.done()
        self.assertIn("not sure", out["say"])
        self.assertFalse(out["response"].get("sent"))
        self.assertNotIn("Sent to", out["say"])
        self.assertNotIn(self.state(), ("counting", "sending"))
        self.now += 60
        self.assertEqual(self.heard("send it"), None)  # nothing is up to be sent again
        self.assertTrue(self.done()["response"].get("stale"))
        self.assertEqual(len(self.fake.messages), 1)  # the one that was cut, and no retry
        self.assertEqual(self.log_rows()[-1]["code"], "unsure")


class ChangedContent(Flow):
    def test_words_changed_after_the_look(self):
        self.ready()
        self.call("plain_message", person="Mark", words="Something else entirely.", signature="Dad")
        self.assertEqual(self.state(), "none")
        self.assertIsNone(self.heard("send it"))
        self.now += 6
        self.assertTrue(self.done()["response"].get("stale"))
        self.assertEqual(self.sent(), 0)

    def test_words_changed_during_the_count(self):
        self.ready()
        self.count()
        self.call("plain_message", person="Mark", words="Something else entirely.", signature="Dad")
        self.now += 6
        self.assertTrue(self.done()["response"].get("stale"))
        self.assertEqual(self.sent(), 0)

    def test_leaving_the_screen_disarms(self):
        self.ready()
        self.event(type="left")
        self.assertEqual(self.state(), "none")
        self.assertIsNone(self.heard("send it"))


class KeepOnce(Flow):
    def test_dont_keep_it_holds_for_good(self):
        out = self.full_send(saved=False)
        self.assertIn("Sent to Mark. It's in your book now.", out["say"])
        self.assertNotIn("Keep", out["say"])
        self.call("keep_address", keep=False)
        self.assertNotIn(ADDRESS, self.everywhere())
        self.last_say = self.full_send(saved=False)
        self.assertNotIn("your book", self.last_say["say"])
        self.assertNotIn(ADDRESS, self.everywhere())
        self.assertEqual(self.sent(), 2)
        # and it asks for the address again, since none was kept
        self.call("plain_message", person="Mark", words="Again.", signature="Dad")
        self.assertTrue(self.call("send_it")["response"].get("need_address"))

    def test_kept_on_the_first_send_and_said_once(self):
        out = self.full_send(saved=False)
        self.assertIn("It's in your book now.", out["say"])
        self.assertIn(ADDRESS, self.everywhere())
        self.assertNotIn(ADDRESS, self.stored())
        self.call("plain_message", person="Mark", words="Again.", signature="Dad")
        again = self.call("send_it")
        self.assertFalse(again["response"].get("need_address"))
        self.assertIn("look", self.effects(again))
        self.look = self.effects(again)["look"]["look"]
        self.event(type="look_up", look=self.look)
        self.said(again["say"])
        self.count()
        self.now += 5
        out = self.done()
        self.assertNotIn("your book", out["say"])
        self.assertEqual(self.sent(), 2)

    def test_each_person_is_told_once(self):
        self.full_send("Mark", saved=False)
        out = self.full_send("Amy", saved=False, address="amy dot park at example dot org")
        self.assertIn("Sent to Amy. It's in your book now.", out["say"])


class BookSend(Flow):
    """M19: the look for someone in the book, through the real routes."""

    def test_stopping_the_count_draws_the_look_through_the_book(self):
        self.ready()
        self.count()
        self.heard("stop")
        self.assertEqual(self.effects()["look"]["email"], ADDRESS)
        self.assertNotIn(ADDRESS, json.dumps(self.ctx.state, default=str))
        self.assertNotIn(ADDRESS, "".join(self.seen))


class Forget(Flow):
    def setUp(self):
        super().setUp()
        self.memory = server.mary_memory()
        self.memory.add_fact("Mark is my son and he likes fishing", "person")
        self.memory.add_fact("Mark's birthday is June 3", "person")
        self.memory.add_fact("I like tomato soup", "fact")
        self.memory.save()
        self.full_send("Mark")
        self.keep_email("Amy", AMY)
        self.full_send("Amy", saved=False)
        self.seen.clear()

    def forget(self, about, tool="forget_memory"):
        first = self.post("/api/mary/skills/call", {"name": tool, "args": {"about": about}})
        self.assertTrue(first["response"].get("needs_yes"), first)  # the yes comes first, nothing is removed yet
        return self.post("/api/mary/skills/call", {"name": tool, "args": {"about": about, "confirmed": True}})

    def contact(self, name):
        return next((p for p in self.host.book.people(include_hidden=True) if p["name"] == name), None)

    def facts(self):
        return json.dumps([m["text"] for m in server.mary_memory().store.active(limit=50)])

    def to_list(self):
        marks = {mail_core.address_mark(address): address for address in (ADDRESS, AMY)}  # M18: the log holds marks
        return [marks.get(r["to"], r["to"]) for r in self.log_rows()]

    def test_yes_rule_removes_nothing_first(self):
        first = self.post("/api/mary/skills/call", {"name": "forget_memory", "args": {"about": "Mark"}})
        self.assertTrue(first["response"]["needs_yes"])
        self.assertIsNotNone(self.contact("Mark"))
        self.assertEqual(self.to_list(), [ADDRESS, AMY])

    def test_his_dates_go_too(self):
        store = server.mary_memory().store
        store.learn_date(memory_dates.parse("Mark's birthday is June 3")[0])
        count = "SELECT COUNT(*) FROM dates WHERE who = 'Mark'"
        with closing(store.connect()) as conn:
            self.assertEqual(conn.execute(count).fetchone()[0], 1)
        self.forget("Mark")
        with closing(store.connect()) as conn:
            self.assertEqual(conn.execute(count).fetchone()[0], 0)

    def test_only_his_address(self):
        self.forget("Mark's address")
        self.assertEqual(self.contact("Mark")["email"], "")
        self.assertEqual(self.contact("Mark")["name"], "Mark")
        self.assertIn("Mark is my son", self.facts())
        self.assertEqual(self.to_list(), ["", AMY])

    def test_all_of_mark(self):
        self.forget("Mark")
        self.assertIsNone(self.contact("Mark"))
        self.assertNotIn("Mark", self.facts())
        self.assertIn("tomato soup", self.facts())
        self.assertEqual(self.to_list(), ["", AMY])
        self.assertIsNotNone(self.contact("Amy"))
        self.assertNotIn(ADDRESS, self.everywhere())
        self.assertNotIn(ADDRESS, "".join(self.seen))
        self.assertNotIn(ADDRESS, self.mod.view(self.ctx.state))

    def test_normal_route(self):
        with server._mary_lock:
            memory = server.mary_memory()
            first = mary.memory_tool(memory, "forget_memory", {"about": "Mark"})
            self.assertTrue(first["response"]["needs_yes"])
            done = mary.memory_tool(memory, "forget_memory", {"about": "Mark", "confirmed": True})
            memory.save()
        self.assertGreaterEqual(done["response"]["forgotten"], 1)
        self.assertIsNone(self.contact("Mark"))
        self.assertEqual(self.to_list(), ["", AMY])
        self.assertNotIn(ADDRESS, json.dumps(done))

    def test_forget_name_reaches_an_exact_contact(self):
        self.keep_email("Mark Hollis", "m.hollis@example.net")
        self.keep_email("Mark Jones", "m.jones@example.net")
        with server._mary_lock:
            memory = server.mary_memory()
            memory.name = "Mark Hollis"
            memory.save()
        self.post("/api/mary/skills/call", {"name": "forget_name", "args": {}})
        self.assertIsNone(self.contact("Mark Hollis"))
        self.assertIsNotNone(self.contact("Mark Jones"))

    def test_everything_leaves_the_book_and_clears_mail_log(self):
        out = self.post("/api/mary/skills/call", {"name": "forget_memory", "args": {"about": "everything"}})
        self.assertFalse(out["response"].get("needs_yes", False) and out["response"].get("forgotten"))
        if out["response"].get("needs_yes"):
            self.post("/api/mary/skills/call", {"name": "forget_memory", "args": {"about": "everything", "confirmed": True}})
        self.assertEqual(self.contact("Mark")["email"], ADDRESS)
        self.assertEqual(self.contact("Amy")["email"], AMY)
        self.assertEqual(self.to_list(), ["", ""])

    def test_a_contact_with_no_memory_rows(self):
        self.assertNotIn("Amy", self.facts())  # she has a contact and no memory rows at all
        self.forget("Amy")
        self.assertIsNone(self.contact("Amy"))
        self.assertEqual(self.to_list(), [ADDRESS, ""])

    def test_the_view_never_has_an_address(self):
        self.ready()
        status, view, _ = helpers.api("GET", "/api/mary/skills/messages/view")
        self.assertEqual(status, 200)
        for address in (ADDRESS, AMY):
            self.assertNotIn(address, json.dumps(view))
        self.assertNotIn(ADDRESS, "".join(self.seen))


class Safety(Flow):
    BAD = {"money": "Please send me some money, $200 will do.",
           "password": "What is your password for the bank?",
           "ssn": "My social security number is 123-45-6789."}

    def test_asking_messages_are_paused(self):
        for reason, words in self.BAD.items():
            with self.subTest(reason=reason):
                self.keep_email()
                self.call("plain_message", person="Mark", words=words, signature="Dad")
                out = self.call("send_it")
                self.assertTrue(out["response"].get("paused"), out)
                self.assertIn("I won't send that", out["say"])
                self.assertNotIn("look", self.effects(out))
                self.assertNotIn("count", self.effects(out))
                self.assertEqual(self.state(), "none")
                self.assertIsNone(self.heard("send it"))
                self.assertTrue(self.event(type="count_done", look="x")["response"].get("stale"))
                self.assertFalse(self.event(type="look_up", look="x")["response"]["ok"])
                self.assertTrue(self.event(type="tap_send")["response"].get("ignored"))
        self.assertEqual(self.sent(), 0)

    def test_thanks_for_the_money_is_not_paused(self):
        self.ready(words="Thank you for the money you sent at Christmas.")
        self.assertEqual(self.state(), "look")

    def test_words_changed_to_money_after_the_look(self):
        self.ready()
        self.call("plain_message", person="Mark", words="Wire me some money.", signature="Dad")
        self.assertEqual(self.state(), "none")
        self.now += 6
        self.assertTrue(self.done()["response"].get("stale"))
        self.assertEqual(self.sent(), 0)


class EmailNotSetUp(Flow):
    def test_straight_to_print(self):
        self.host.mail_ready = lambda: False
        self.keep_email()
        self.call("plain_message", person="Mark", words="Hello.", signature="Dad")
        out = self.call("send_it")
        self.assertIn("isn't set up", out["say"])
        self.assertNotIn("look", self.effects(out))
        self.assertEqual(self.state(), "none")
        self.assertEqual(self.heard("send it"), None)
        self.assertEqual(self.sent(), 0)


class SpokenAddress(Flow):
    def test_spoken_address_is_spelled_and_checked(self):
        self.call("plain_message", person="Mark", words="Hello.", signature="Dad")
        out = self.call("send_it")
        self.assertTrue(out["response"]["need_address"])
        out = self.call("give_address", address=SPOKEN, person="Mark")
        self.assertEqual(out["response"]["spelled"], ADDRESS)
        self.assertIn("letter by letter", out["response"]["note"])
        self.assertIn("address_wait", self.effects(out))
        self.assertEqual(self.state(), "none")  # nothing is armed until she's asked if it's right
        out = self.call("address_right", right=False)
        self.assertTrue(out["response"].get("need_address"))
        self.assertEqual(self.state(), "none")
        self.call("give_address", address=SPOKEN, person="Mark")
        out = self.call("address_right", right=True)
        self.assertIn("look", self.effects(out))
        self.assertEqual(self.state(), "look")

    def test_a_bad_spoken_address_is_asked_again(self):
        self.call("plain_message", person="Mark", words="Hello.", signature="Dad")
        out = self.call("give_address", address="mark at", person="Mark")
        self.assertTrue(out["response"].get("need_address"))
        self.assertEqual(self.state(), "none")

    def test_a_typed_address_stays_out_of_the_say_and_the_response(self):
        self.call("plain_message", person="Mark", words="Hello.", signature="Dad")
        self.call("send_it")
        self.seen.clear()
        out = self.event(type="address", address=ADDRESS)
        self.assertIn("look", self.effects(out))  # the page gets it
        self.assertEqual(self.effects(out)["look"]["email"], ADDRESS)
        self.assertNotIn(ADDRESS, json.dumps(plain(out)))
        self.assertNotIn("mark.hollis", out["say"].lower())
        self.assertNotIn(ADDRESS, "".join(self.seen))


class GateFailures(Flow):
    def test_a_raising_gate_does_not_break_talk(self):
        class Boom:
            def __getattr__(self, name):
                raise RuntimeError(name)

        self.host.gate = Boom()
        out = self.talk("good morning", chunks=("[mood: happy] Good morning!",))
        self.assertIn("Good morning", out["text"])
        self.assertFalse(out["error"])
        out = self.post("/api/mary/heard", {"text": "send it"})
        self.assertNotIn("send", out)
        self.post("/api/mary/live/said", {"text": "five seconds"})
        out = self.talk("how are you", chunks=("[mood: happy] Fine.",))
        self.assertIn("Fine", out["text"])


if __name__ == "__main__":
    unittest.main()
