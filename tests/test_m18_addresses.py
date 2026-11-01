from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M18 piece 3b: email addresses. She can take one and fill one, and contacts are the one place one is kept. Everywhere
else words are kept, memory_core.scrub_addresses has been through them first. Made-up addresses only."""
import json
import shutil
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path

import desktop
import mail_core
import mary
import memory_core
import server
import voices
from tests.test_m15c_contacts import ADDRESS, SPOKEN, Base
from tests.test_m18_screens import node

SAYS = memory_core.ADDRESS_WORDS
LINE = "my daughter's email is sarah dot hollis at gmail dot com"


class Scrub(unittest.TestCase):
    def test_written(self):
        for line in ("a@b.co", "mark.hollis@example.com", "Mark.Hollis+care@Example.org", "mark @ example . com",
                     "mark@ example.com", "mark @example.com", "mark@gmail,com", "mark@gmail . com", "x@y.photography",
                     "sarah_h-2@mail.example.co.uk", "mark@example", "mark dot hollis@example.com"):
            self.assertEqual(memory_core.scrub_addresses(line), SAYS, line)

    def test_spoken(self):
        for line in ("mark dot hollis at gmail dot com", "Mark Dot Hollis At Gmail Dot Com", "m a r k at yahoo dot com",
                     "M-A-R-K at gmail dot com", "mark underscore hollis at aol dot com", "mark at sign gmail dot com",
                     "mark at symbol gmail dot com", "m, a, r, k at yahoo dot com", "M. A. R. K. at gmail dot com",
                     "mark, dot, hollis, at, gmail, dot, com", "mark under score hollis at aol dot com",
                     "mark dash hollis at hotmail dot com", "mark seven two at g mail dot com", "mark at gmail.com",
                     "mark at gmail . com", "mark at gmail. com", "mark at gmail com", "mark at hollisfamily dot com",
                     "mark at mail dot example dot org", "mark at example dot co dot uk", "m a r k at y a h o o dot com"):
            self.assertEqual(memory_core.scrub_addresses(line), SAYS, line)

    def test_the_words_around_it_stay(self):
        cases = {"My email is mark@example.com.": "My email is %s." % SAYS,
                 LINE: "my daughter's email is %s" % SAYS,
                 "her address is m a r k at yahoo dot com, and she's fine": "her address is %s, and she's fine" % SAYS,
                 "it's mark at gmail dot com or amy@example.org": "it's %s or %s" % (SAYS, SAYS),
                 "my email's at gmail dot com": "my email's %s" % SAYS}
        for line, want in cases.items():
            self.assertEqual(memory_core.scrub_addresses(line), want)

    def test_plain_talk_stays(self):
        for line in ("I was at church dot dot dot", "she's at home", "look at that dot on the map", "at the store dot com",
                     "we were at the store, dot com stuff I don't know", "I bought it at walmart dot com",
                     "she works at acme dot com", "look at that dot com", "Called my mom at home. Us kids played.",
                     "dinner at five, dot your i's", "the point is at home", "meet @ 3 tomorrow", "she's at sign language class",
                     "walmart dot com has it", "I looked at amazon.com", "Mark's at hollisfamily dot com", ""):
            self.assertEqual(memory_core.scrub_addresses(line), line, line)

    def test_twice_is_the_same_as_once(self):
        once = memory_core.scrub_addresses(LINE + " and mark@example.com")
        self.assertEqual(memory_core.scrub_addresses(once), once)

    def test_only_address(self):
        for fact in ("Her email is sarah@example.com", "sarah@example.com", "My daughter Sarah's email address is a@b.co."):
            self.assertTrue(memory_core.only_address(memory_core.scrub_addresses(fact)), fact)
        for fact in ("Likes tea", "Likes tea and her email is a@b.co", ""):
            self.assertFalse(memory_core.only_address(memory_core.scrub_addresses(fact)), fact)


class Watcher:
    """Stands in for the skill host: what the send gate was given."""

    def __init__(self):
        self.lines, self.her = [], []

    def resident_said(self, text, garbled=False):
        self.lines.append(text)

    def her_words(self, text):
        self.her.append(text)

    def send_emergency(self):
        pass

    def talk_over(self):
        pass


class ThroughTheServer(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        server.init_memories()
        (server.DATA / "mary" / "memory.json").unlink(missing_ok=True)
        with closing(server.connect_memories()) as conn, conn:
            conn.execute("DELETE FROM dates")
            conn.execute("DELETE FROM memories")
        self.gate = Watcher()
        server.set_skill_host_for_tests(self.gate)
        self.addCleanup(server.set_skill_host_for_tests, None)

    def post(self, path, body):
        code, reply, _ = helpers.api("POST", path, body)
        self.assertEqual(code, 200, reply)
        return reply

    def kept(self):
        path = server.DATA / "mary" / "memory.json"
        text = path.read_text("utf-8") if path.exists() else ""
        return text + json.dumps([m["text"] for m in server.memory_store().active()])

    def test_heard_keeps_no_address_and_the_gate_had_the_raw_line(self):
        self.post("/api/mary/heard", {"text": LINE})
        self.assertEqual(self.gate.lines, [LINE])
        kept = self.kept()
        self.assertNotIn("hollis", kept)
        self.assertNotIn("gmail", kept)
        self.assertIn(SAYS, kept)
        self.assertEqual(server.mary_memory().recent[-1]["text"], "my daughter's email is %s" % SAYS)

    def test_said_keeps_no_address_and_the_gate_had_the_raw_line(self):
        said = "That's s a r a h dot hollis at gmail dot com. Is that right?"
        self.post("/api/mary/live/said", {"text": said})
        self.post("/api/mary/live/said", {"text": said})  # the same words twice stay one turn
        self.assertEqual(self.gate.her, [said, said])
        self.assertNotIn("gmail", self.kept())
        self.assertEqual([t["text"] for t in server.mary_memory().recent], ["That's %s. Is that right?" % SAYS])

    def test_remember_fact_with_only_an_address_is_told_it_is_for_contacts(self):
        out = server.mary_live_memory_call("remember_fact", {"fact": "Her daughter's email is sarah.hollis@gmail.com"}, LINE)
        self.assertFalse(out["response"]["ok"])
        self.assertIn("contacts", out["response"]["note"])
        self.assertEqual(server.memory_store().count(), 0)

    def test_remember_fact_keeps_the_rest(self):
        out = server.mary_live_memory_call("remember_fact", {"fact": "Likes tea and her email is sarah.hollis@gmail.com"}, LINE)
        self.assertTrue(out["response"]["ok"])
        self.assertEqual([m["text"] for m in server.memory_store().active()], ["Likes tea and her email is %s" % SAYS])

    def test_every_memory_writer(self):
        memory = server.mary_memory()
        self.assertFalse(memory.add_fact("sarah@example.com"))
        self.assertTrue(memory.add_fact("Daughter Sarah, sarah@example.com, lives in Durham"))
        self.assertIsNone(memory.store.add("mark at gmail dot com"))
        memory.add_turn("user", "x " * 300 + "mark at gmail dot com")  # past the cut
        memory.pending_offer = {"incident": {"description": LINE}, "question": "Write that down?"}
        memory.pending_forget = {"about": "mark at gmail dot com", "at": 1}
        mary.learn_dates(memory, "mark at gmail dot com")
        memory.save()
        kept = self.kept()
        for word in ("sarah@", "gmail", "hollis"):
            self.assertNotIn(word, kept)
        self.assertEqual(memory.pending_offer["incident"]["description"], LINE)  # only what's written down changes

    def test_a_waiting_offer_keeps_their_words_off_the_file(self):
        memory = server.mary_memory()
        memory.pending_offer = {"incident": {"description": LINE}, "question": "Write that down?"}
        memory.save()
        self.assertNotIn("gmail", self.kept())
        again = server.mary_memory()  # she reloads every turn: the incident must still be their own words
        self.assertEqual(again.pending_offer["incident"]["description"], LINE)
        again.pending_offer = None
        again.save()
        self.assertIsNone(server.mary_memory().pending_offer)

    def test_old_talk_in_the_file_comes_back_clean(self):
        path = server.DATA / "mary" / "memory.json"
        path.write_text(json.dumps({"recent": [{"role": "user", "text": LINE, "at": ""}]}), "utf-8")
        self.assertNotIn("gmail", server.mary_memory().recent[0]["text"])

    def test_talk_memory_with_no_store(self):
        memory = mary.Memory(server.DATA / "mary" / "other.json")
        self.addCleanup(memory.path.unlink, missing_ok=True)
        self.assertFalse(memory.add_fact("sarah@example.com"))
        self.assertTrue(memory.add_fact("Her friend is at sarah@example.com"))
        self.assertNotIn("sarah@", json.dumps(memory.facts))


class TextLogs(unittest.TestCase):
    def setUp(self):
        server.DATA.mkdir(parents=True, exist_ok=True)

    def test_wake_log(self):
        path = server.DATA / "wake.log"
        path.unlink(missing_ok=True)
        self.addCleanup(path.unlink, missing_ok=True)
        server.wake_log("almost", name="mary", whisper="hey mary sarah dot hollis at gmail dot com")
        text = path.read_text("utf-8")
        self.assertNotIn("gmail", text)
        self.assertIn("hey mary", text)

    def test_voices_log(self):
        path = server.DATA / "mary" / "audition.log"
        path.unlink(missing_ok=True)
        self.addCleanup(path.unlink, missing_ok=True)
        voices.log({"event": "live", "note": "mark at gmail dot com", "error": "sarah@example.com"}, server.DATA)
        text = path.read_text("utf-8")
        self.assertNotIn("gmail", text)
        self.assertNotIn("sarah@", text)

    def test_desktop_log(self):
        path = server.DATA / "desktop.log"
        path.unlink(missing_ok=True)
        self.addCleanup(path.unlink, missing_ok=True)
        desktop.log_note("trouble", "while sending to sarah@example.com")
        self.assertNotIn("sarah@", path.read_text("utf-8"))


class MailLog(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="maillog-", dir=helpers.TMP))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.log = self.dir / "mail.log"
        self.mailer = mail_core.Mailer(types.SimpleNamespace(get=lambda key: None), self.log)

    def rows(self):
        return [json.loads(line) for line in self.log.read_text("utf-8").splitlines()]

    def test_when_a_mark_and_the_result(self):
        self.mailer._done("messages", "mark.hollis@gmail.com", None)
        self.mailer._done("messages", "Mark.Hollis@Gmail.com", "offline")
        self.mailer._done("messages", "amy@example.org", None)
        text = self.log.read_text("utf-8")
        for word in ("hollis", "gmail", "amy", "@"):
            self.assertNotIn(word.lower(), text.lower())
        rows = self.rows()
        self.assertEqual(rows[0]["to"], rows[1]["to"])  # a helper can tell two sends apart
        self.assertNotEqual(rows[0]["to"], rows[2]["to"])
        self.assertEqual(len(rows[0]["to"]), 10)
        self.assertEqual([r["ok"] for r in rows], [True, False, True])

    def test_forget_still_finds_the_line(self):
        self.mailer._done("messages", "mark.hollis@gmail.com", None)
        self.mailer.scrub_log(["MARK.hollis@gmail.com"])
        self.assertEqual(self.rows()[0]["to"], "")

    def test_lines_from_before_get_a_mark(self):
        self.log.write_text('{"when": "t", "skill": "s", "to": "amy@example.org", "ok": true, "code": ""}\n'
                            '{"when": "t", "skill": "s", "to": "", "ok": false, "code": "offline"}\n'
                            'not json amy@example.org\n', "utf-8")
        self.mailer.hide_old_addresses()
        self.assertNotIn("@", self.log.read_text("utf-8"))
        self.assertEqual([r["to"] for r in self.rows()], [mail_core.address_mark("amy@example.org"), ""])


class Contacts(Base):
    def told(self, person="Sarah", relationship="daughter"):
        self.act("give_address", address=SPOKEN, person=person, relationship=relationship)
        return self.act("address_right", right=True)

    def saved(self):
        self.told()
        self.act("keep_address", keep=True)

    def ask(self, heard, name="Sarah"):
        return self.host.call("messages__contact_address", {"name": name}, heard=heard)["response"]

    def test_told_outside_a_send_is_spelled_back_then_offered(self):
        out = self.act("give_address", address=SPOKEN, person="my daughter", relationship="daughter")
        self.assertEqual(out["spelled"], ADDRESS)
        self.assertIsNone(self.contact("my daughter"))  # nothing is kept before the yes
        out = self.act("address_right", right=True)
        self.assertTrue(out["keep_question"])
        self.assertEqual(self.last["say"], "Keep your daughter's address for next time?")
        self.assertNotIn(ADDRESS, json.dumps(out))
        self.assertTrue(self.act("keep_address", keep=True)["kept"])
        self.assertEqual(self.contact("my daughter")["email"], ADDRESS)
        self.assertNotIn("address_told", self.ctx.state)

    def test_a_no_at_the_spelling_keeps_nothing(self):
        self.act("give_address", address=SPOKEN, person="Sarah")
        self.assertTrue(self.act("address_right", right=False)["need_address"])
        self.assertEqual(self.ctx.state.get("address_wait"), None)
        self.assertNotIn(ADDRESS, self.everywhere())

    def test_a_no_to_keeping_leaves_a_saved_address_alone(self):
        self.saved()
        self.act("give_address", address="other.one@example.org", person="Sarah")
        self.assertTrue(self.act("address_right", right=True)["keep_question"])
        self.assertFalse(self.act("keep_address", keep=False)["kept"])
        self.assertEqual(self.contact("Sarah")["email"], ADDRESS)

    def test_the_same_address_again_asks_nothing(self):
        self.saved()
        out = self.told()
        self.assertTrue(out["kept"])
        self.assertNotIn("address_told", self.ctx.state)

    def test_email_my_daughter_needs_no_address_said(self):
        self.saved()
        for said in ("my daughter", "Sarah", "my daughter Sarah", "daughter"):
            self.seen.clear()
            self.mod._drop_send(self.ctx)
            self.letter(said)
            out = self.act("send_it")
            self.assertTrue(out.get("look_up"), said)
            self.assertEqual(self.effect("look")["email"], ADDRESS)
            self.assertNotIn(ADDRESS, "".join(self.seen))
            self.assertNotIn("hollis", "".join(self.seen).lower())

    def test_both_names_needs_both(self):
        self.saved()
        self.assertFalse(self.act("find_contact", name="my daughter in law")["known"])
        self.assertFalse(self.act("find_contact", name="my granddaughter Sarah Ann")["known"])
        self.assertTrue(self.act("find_contact", name="my daughter Sarah")["known"])

    def test_find_contact_never_gives_the_address(self):
        self.saved()
        out = self.act("find_contact", name="my daughter")
        self.assertEqual(out, {"known": True, "name": "Sarah", "relationship": "daughter", "has_email": True})

    def test_contact_address_refuses_unasked(self):
        self.saved()
        for heard in ("", "how is Sarah doing", "email my daughter", "send an email to Sarah", "send it",
                      "write to my daughter", "tell Sarah happy birthday"):
            out = self.ask(heard)
            self.assertNotIn("address", out, heard)
            self.assertTrue(out["not_asked"], heard)
            self.assertNotIn(ADDRESS, json.dumps(out))

    def test_contact_address_gives_it_when_asked(self):
        self.saved()
        for heard in ("what's Sarah's email address", "read me my daughter's email", "fill in the to box with Sarah",
                      "put her email in that box", "put my daughter in the to box", "what’s her address"):
            self.assertEqual(self.ask(heard).get("address"), ADDRESS, heard)

    def test_contact_address_with_nobody_or_no_address(self):
        self.assertEqual(self.ask("what's Tyler's address", "Tyler"), {"known": False})
        self.act("save_contact", name="Tyler")
        self.assertFalse(self.ask("what's Tyler's address", "Tyler")["has_email"])

    def test_waiting_address_goes_after_the_turn(self):
        self.act("give_address", address=SPOKEN, person="Sarah")
        self.assertIn("address_wait", self.ctx.state)
        self.host.resident_said("hm")
        self.host.resident_said("what was that")
        self.assertIn("address_wait", self.ctx.state)  # room for the yes, whichever way round Live's words arrive
        self.host.resident_said("anyway, tell me a story")
        self.assertNotIn("address_wait", self.ctx.state)
        self.assertEqual(self.ctx.state.get("send_view"), None)

    def test_keep_question_goes_after_the_turn_and_with_the_talk(self):
        self.told()
        for _ in range(self.mod.ADDRESS_LINES):
            self.host.resident_said("hm")
        self.assertNotIn("address_told", self.ctx.state)
        self.act("give_address", address=SPOKEN, person="Sarah")
        self.host.talk_over()
        self.assertNotIn("address_wait", self.ctx.state)

    def test_an_address_checked_for_a_send_stays_with_the_send(self):
        self.letter()
        self.act("send_it")
        self.act("give_address", address=SPOKEN)
        self.act("address_right", right=True)
        for _ in range(5):
            self.mod.on_resident_line(self.ctx)
        self.mod.on_resident_line(self.ctx, True)
        self.assertEqual(self.ctx.state["address_wait"]["address"], ADDRESS)

    def test_a_send_keeps_it_and_says_so(self):
        self.address_then_send()
        self.assertEqual(self.last["say"], "Sent to Mark. It's in your book now. Would you like it printed so it can be mailed?")
        self.assertEqual(self.contact("Mark")["email"], ADDRESS)

    def test_dont_keep_it_after_a_send(self):
        self.address_then_send()
        self.assertFalse(self.act("keep_address", keep=False)["kept"])
        self.assertEqual((self.contact("Mark")["email"], self.contact("Mark")["no_keep"]), ("", True))

    def test_keep_answer_after_a_send_changes_nothing(self):
        self.address_then_send()
        self.assertTrue(self.act("keep_address", keep=True)["kept"])
        self.assertEqual(self.contact("Mark")["email"], ADDRESS)

    def test_forget_reaches_an_address_told(self):
        self.told()
        out = self.mod.on_forget(self.ctx, "Sarah")
        self.assertEqual(out["addresses"], [ADDRESS])
        self.assertNotIn("address_told", self.ctx.state)

    def test_nothing_held_or_logged_beyond_the_contact(self):
        self.saved()
        self.ask("what's Sarah's email address")
        self.host._log("try", note="mail to " + ADDRESS)
        self.assertNotIn(ADDRESS, json.dumps(self.ctx.state))
        log = self.dir / "skills.log"
        self.assertNotIn(ADDRESS, log.read_text("utf-8"))
        self.assertNotIn(ADDRESS, self.stored())
        self.assertIn(ADDRESS, self.everywhere())


class Screens(unittest.TestCase):
    def test_her_look_shows_the_box_and_only_the_box(self):
        rc, _, err = node(r"""
          const page = pageOn('info');
          page.byId['mailAddress'].value = 'mark.hollis@example.com';
          const card = await run('look_at_screen', {}, envOn(page));
          assert.strictEqual(card.fields.find(f => f.field === 'mailAddress').value, 'mark.hollis@example.com');
          assert(!JSON.stringify(card).includes('secret-pass'));
        """)
        self.assertEqual(rc, 0, err)

    def test_a_written_address_fills_and_she_spells_it_back(self):
        rc, _, err = node(r"""
          const page = pageOn('info');
          const r = await run('fill_field', { field: 'mailAddress', value: 'mark.hollis@example.com' }, envOn(page));
          assert.strictEqual(r.ok, true);
          assert.strictEqual(page.byId['mailAddress'].value, 'mark.hollis@example.com');
          assert(r.next.includes('letter by letter'));
        """)
        self.assertEqual(rc, 0, err)

    def test_a_spoken_address_does_not_go_in_the_box(self):
        rc, _, err = node(r"""
          const page = pageOn('info');
          const r = await run('fill_field', { field: 'mailAddress', value: 'mark dot hollis at gmail dot com' }, envOn(page));
          assert.strictEqual(r.ok, false);
          assert.strictEqual(page.byId['mailAddress'].value, '');
        """)
        self.assertEqual(rc, 0, err)


class Words(unittest.TestCase):
    def test_her_lines(self):
        text = (helpers.ROOT / "mary" / "instructions.md").read_text("utf-8")
        part = text[text.index("Working on their screens\n"):text.index("Remembering\n- Below")]
        self.assertIn("Spell it back letter by letter and wait for their yes", part)
        self.assertIn("use the name", part)
        self.assertIn("contact_address", part)

    def test_find_contact_still_says_so(self):
        manifest = json.loads((helpers.ROOT / "skills" / "messages" / "manifest.json").read_text("utf-8"))
        tools = {a["name"]: a["description"] for a in manifest["actions"]}
        self.assertIn("Never the address itself.", tools["find_contact"])
        self.assertIn("only when they ask", tools["contact_address"])


if __name__ == "__main__":
    unittest.main()
