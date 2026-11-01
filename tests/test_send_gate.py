from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

import json
import shutil
import smtplib
import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import mail_core
import mary
import memory_core
import send_gate
import server
import skills_core

PICTURE = {"name": "card.jpg", "data": b"\xff\xd8\xff" + b"x" * 100}
PERSON = "Mark Hollis"
TO = "mark@example.org"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeMailer:
    def __init__(self):
        self.minted = []
        self.scrubbed = []

    def mint_ticket(self, skill, to, subject, body, pictures=()):
        self.minted.append((skill, to, subject, body, pictures))
        return f"ticket-{len(self.minted)}"

    def scrub_log(self, addresses=None):
        self.scrubbed.append(addresses)


class GateCase(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.mailer = FakeMailer()
        self.gate = send_gate.SendGate(self.mailer, clock=self.clock)

    def arm(self, shown=True, said=True, person=PERSON, pictures=(PICTURE,)):
        look = self.gate.arm("messages", person, TO, "A card from Andy", "Happy birthday", list(pictures))
        if shown:
            self.gate.shown(look)
        if said:
            self.gate.her_words(send_gate.line_for(person))
        return look

    def counting(self):
        look = self.arm()
        self.assertEqual(self.gate.heard("send it")["action"], "count")
        return look

    def state(self):
        return self.gate.state("messages")


class PlainSend(unittest.TestCase):
    def test_yes(self):
        for line in ("send it", "Send it.", "now send it", "okay, send it", "that looks good. send it",
                     "go ahead and send it", "send it to Mark", "send it to mark hollis", "Send it, please",
                     "please send the card", "Mary, send my message now", "can you send it?", "yes send it off",
                     "send it on its way", "you can send that now please", "send it, Mary"):
            self.assertTrue(send_gate.is_plain_send(line, PERSON), line)

    def test_no(self):
        for line in ("Send it to Tyler", "send it to Tyler, please", "okay", "sounds good", "should I send it?",
                     "send it tomorrow", "don't send it", "do not send it", "no, send it", "not yet, send it",
                     "send it later", "maybe send it", "did you send it", "wait, send it", "send it if you can",
                     "why send it", "send", "I sent it", "shouldn't we send it", "send it when he's home", "", None,
                     "well I was thinking that it looks pretty good to me, so nice, send it"):
            self.assertFalse(send_gate.is_plain_send(line, PERSON), line)

    def test_no_person_has_no_to(self):
        self.assertTrue(send_gate.is_plain_send("send it", ""))
        self.assertFalse(send_gate.is_plain_send("send it to Mark", ""))


class PlainSave(unittest.TestCase):
    def test_plain_words_count(self):
        for line in ("save it", "Save it.", "save that", "save this", "go ahead and save it", "okay save it",
                     "yes save it", "Yes, save it.", "save it please", "Save it, please.", "save it now", "save my info",
                     "save the form", "that's good save it", "That's good, save it.", "that’s good save it",
                     "Mary, save it.", "Save it, Mary.", "please save it", "just save it", "okay Mary save it please",
                     "let's save it", "save it for me", "save that for me", "save it, thanks", "looks good save it",
                     "can you save it", "Can you save it?", "could you save that?", "could you save that please", "would you save it", "will you save it",
                     "Okay? Save it.", "The soup was cold. Save it."):
            self.assertTrue(send_gate.is_plain_save(line), line)

    def test_anything_less_refuses(self):
        for line in ("Save it? I don't know yet", "save it?", "Save it?!", "save it, please?", "Save it, okay?",
                     "Save it? Hmm.", "Save it. I guess.", "don't save it",
                     "do not save it", "dont save it", "not yet", "save it later", "should I save it", "save me a seat",
                     "yes", "okay", "ok", "that's right", "Yes, that's right.", "save money", "save it for later",
                     "save it for tomorrow", "save the rest for tomorrow", "I saved it", "we saved it", "did you save it",
                     "did it save", "is it saved", "wait, save it", "no, save it", "stop", "maybe save it",
                     "save it if you want", "save it when you can", "save it after lunch", "never mind", "hold on",
                     "keep it", "yes keep it", "keep that", "save", "save room for pie", "save it to my notes",
                     "send it", "okay send it", "", "   ", "...", None,
                     "well I told my daughter that we might go ahead and save it"):
            self.assertFalse(send_gate.is_plain_save(line), line)

    def test_save_and_send_never_cross(self):
        self.assertFalse(send_gate.is_plain_send("save it"))
        self.assertFalse(send_gate.is_plain_save("send it"))


class Words(GateCase):
    def test_chatty_okay_is_neither_a_yes_nor_a_miss(self):
        self.arm()
        for line in ("Okay", "sounds good", "yes", "no", "okay", "sounds good", "That's fine"):
            self.assertIsNone(self.gate.heard(line)["action"], line)
        self.assertFalse(self.state()["tap_open"])
        self.assertEqual(self.state()["state"], "look")

    def test_long_talk_is_not_a_miss(self):
        self.arm()
        for _ in range(3):
            self.assertIsNone(self.gate.heard("I wonder how the weather is out there today")["action"])
        self.assertFalse(self.state()["tap_open"])

    def test_two_misses_open_the_tap(self):
        look = self.arm()
        self.assertFalse(self.gate.tap())
        self.assertIsNone(self.gate.heard("send ti")["action"])
        self.assertFalse(self.gate.tap())
        self.assertEqual(self.gate.heard("sent it")["action"], "tap")
        self.assertTrue(self.state()["tap_open"])
        self.assertTrue(self.gate.tap())
        self.assertEqual(self.state()["state"], "counting")
        self.clock.advance(5)
        self.assertIsNotNone(self.gate.take("messages", look))

    def test_garbled_counts_as_a_miss_and_never_as_a_yes(self):
        self.arm()
        self.assertIsNone(self.gate.heard("send it", garbled=True)["action"])
        self.assertEqual(self.gate.heard("okay", garbled=True)["action"], "tap")

    def test_line_must_be_said(self):
        self.arm(said=False)
        out = self.gate.heard("send it")
        self.assertEqual(out["action"], "say_line")
        self.assertEqual(out["line"], send_gate.line_for(PERSON))
        self.assertEqual(self.state()["state"], "look")
        self.assertEqual(self.gate.heard("send it")["action"], "say_line")
        self.gate.her_words("It'll go in a second.")  # after a scripted line, "second" alone does
        self.assertTrue(self.state()["line_said"])
        self.assertEqual(self.gate.heard("send it")["action"], "count")

    def test_what_counts_as_the_line(self):
        for words, said in (("All set.", False), ("You'll have five seconds.", False), ("In a second, Mark.", False),
                            ("Going to Mark in five seconds.", True), ("5 seconds and it's off by email.", True),
                            ("Five second wait, then Mark gets it", True), (send_gate.line_for(PERSON), True)):
            self.arm(said=False)
            self.gate.her_words(words)
            self.assertEqual(self.state()["line_said"], said, words)

    def test_look_must_be_shown(self):
        look = self.arm(shown=False)
        self.assertIsNone(self.gate.heard("send it")["action"])
        self.assertFalse(self.gate.shown("another look"))
        self.assertTrue(self.gate.shown(look))
        self.assertEqual(self.gate.heard("send it")["action"], "count")

    def test_no_look_hears_nothing(self):
        self.assertIsNone(self.gate.heard("send it")["action"])
        self.assertFalse(self.gate.her_words(send_gate.line_for(PERSON)))
        self.assertFalse(self.gate.undo())
        self.assertFalse(self.gate.tap())
        self.assertIsNone(self.gate.take("messages", "nothing"))
        self.assertEqual(self.state(), send_gate.NO_LOOK)


class Count(GateCase):
    def test_undo_at_each_second(self):
        for second in range(5):
            look = self.counting()
            self.clock.advance(second)
            self.assertTrue(self.gate.undo(), second)
            state = self.state()
            self.assertEqual((state["state"], state["line_said"], state["tap_open"]), ("look", True, False))
            self.clock.advance(5)
            self.assertIsNone(self.gate.take("messages", look), second)

    def test_undo_resets_misses(self):
        self.arm()
        self.gate.heard("send ti")
        self.gate.heard("sent it")
        self.gate.tap()
        self.gate.undo()
        self.assertFalse(self.state()["tap_open"])
        self.assertIsNone(self.gate.heard("send ti")["action"])

    def test_stop_words_and_the_quiet(self):
        for line in ("stop", "Undo!", "wait", "no", "don't", "cancel it", "hold on", "hang on", "never mind", "oops",
                     "not yet", "No no no"):
            self.counting()
            self.assertEqual(self.gate.heard(line)["action"], "stopped", line)
            self.assertEqual(self.state()["state"], "look")
        self.counting()
        for line in ("thank you", "send it", "okay"):
            self.assertEqual(self.gate.heard(line)["action"], "quiet", line)
        self.assertEqual(self.state()["state"], "counting")

    def test_emergency_stops_the_count_and_keeps_the_look(self):
        look = self.counting()
        self.assertTrue(self.gate.emergency())
        self.assertEqual(self.state()["look"], look)
        self.assertEqual(self.state()["state"], "look")
        self.clock.advance(5)
        self.assertIsNone(self.gate.take("messages", look))

    def test_take_refused_before_five_seconds(self):
        look = self.counting()
        self.clock.advance(4.9)
        self.assertIsNone(self.gate.take("messages", look))
        self.clock.advance(0.1)
        got = self.gate.take("messages", look)
        self.assertEqual((got["to"], got["subject"], got["body"]), (TO, "A card from Andy", "Happy birthday"))
        self.assertEqual(got["pictures"], [PICTURE])

    def test_take_refused_after_thirty_seconds(self):
        look = self.counting()
        self.clock.advance(30.1)
        self.assertIsNone(self.gate.take("messages", look))
        self.assertEqual(self.state()["state"], "look")
        self.assertNotEqual(self.gate.heard("thank you")["action"], "quiet")  # a dead window can't keep her silent

    def test_take_at_thirty_seconds_still_goes(self):
        look = self.counting()
        self.clock.advance(30)
        self.assertIsNotNone(self.gate.take("messages", look))

    def test_a_used_look_cannot_be_taken_twice(self):
        look = self.counting()
        self.clock.advance(5)
        self.assertIsNotNone(self.gate.take("messages", look))
        self.assertEqual(self.state()["state"], "sending")
        self.assertIsNone(self.gate.take("messages", look))
        self.gate.finish(look)
        self.assertIsNone(self.gate.take("messages", look))
        self.assertEqual(self.state(), send_gate.NO_LOOK)

    def test_take_checks_id_and_skill(self):
        look = self.counting()
        self.clock.advance(5)
        self.assertIsNone(self.gate.take("messages", "another"))
        self.assertIsNone(self.gate.take("other", look))
        self.assertIsNotNone(self.gate.take("messages", look))

    def test_take_refused_when_it_asks_for_money_after_all(self):
        look = self.counting()
        self.clock.advance(5)
        with mock.patch.object(send_gate, "asks_for", return_value="money"):
            self.assertIsNone(self.gate.take("messages", look))
        self.assertIsNone(self.gate.take("messages", look))

    def test_old_look_is_dropped_first(self):
        self.arm()
        self.clock.advance(send_gate.LOOK_TTL_S + 1)
        self.assertIsNone(self.gate.heard("send it")["action"])
        self.assertEqual(self.state()["state"], "none")

    def test_a_new_look_replaces_the_old_one(self):
        old = self.arm()
        new = self.arm()
        self.assertNotEqual(old, new)
        self.gate.heard("send it")
        self.clock.advance(5)
        self.assertIsNone(self.gate.take("messages", old))
        self.assertIsNotNone(self.gate.take("messages", new))

    def test_disarm(self):
        self.arm()
        self.gate.disarm("other")
        self.assertEqual(self.state()["state"], "look")
        self.gate.disarm("messages")
        self.assertEqual(self.state()["state"], "none")


class Arm(GateCase):
    def test_refusals(self):
        for reason, args in (("money", (TO, "Hi", "Please wire me the money")),
                             ("password", (TO, "What's your password?", "Hi")),
                             ("ssn", (TO, "Hi", "It's 123-45-6789")),
                             ("bad_message", ("not an address", "Hi", "Hello")),
                             ("bad_message", (TO, None, "Hello"))):
            with self.assertRaises(send_gate.GateRefused) as made:
                self.gate.arm("messages", PERSON, *args)
            self.assertEqual(made.exception.reason, reason)

    def test_too_big(self):
        big = {"name": "card.jpg", "data": b"\xff\xd8\xff" + b"x" * send_gate.MAIL_PICTURES_MAX}
        with self.assertRaises(send_gate.GateRefused) as made:
            self.gate.arm("messages", PERSON, TO, "Hi", "Hello", [big])
        self.assertEqual(made.exception.reason, "too_big")

    def test_a_refused_arm_leaves_no_look(self):
        self.arm()
        with self.assertRaises(send_gate.GateRefused):
            self.gate.arm("messages", PERSON, TO, "Hi", "Send me money")
        self.assertEqual(self.state()["state"], "none")

    def test_content_is_frozen(self):
        pictures = [{"name": "card.jpg", "data": bytearray(PICTURE["data"])}]
        look = self.gate.arm("messages", PERSON, TO, "Hi", "Hello", pictures)
        pictures[0]["data"][3:6] = b"yyy"
        self.gate.shown(look)
        self.gate.her_words(send_gate.line_for(PERSON))
        self.gate.heard("send it")
        self.clock.advance(5)
        self.assertEqual(self.gate.take("messages", look)["pictures"][0]["data"], PICTURE["data"])

    def test_state_has_no_address(self):
        self.arm()
        self.assertNotIn("example", json.dumps(self.state()))


class AsksFor(unittest.TestCase):
    def test_money(self):
        for text in ("Please wire it to me", "Western Union is fine", "a MoneyGram would do", "get a money order",
                     "buy two gift cards", "a gift card", "Zelle me", "I'm on Venmo", "my Cash App", "PayPal",
                     "bitcoin", "crypto", "send me money", "Send money", "give him the cash", "lend me some money",
                     "loan us some cash", "transfer the money", "mail me $50", "send $100", "send me 100 dollars",
                     "my bank account", "the account number", "your routing number", "credit card number",
                     "debit card number", "credit or debit card number"):
            self.assertEqual(send_gate.asks_for(text), "money", text)

    def test_password(self):
        for text in ("my password", "the passcode", "your PIN number", "log in", "your login"):
            self.assertEqual(send_gate.asks_for(text), "password", text)

    def test_ssn(self):
        for text in ("your social security", "SSN", "it's 123-45-6789", "it's 123456789"):
            self.assertEqual(send_gate.asks_for(text), "ssn", text)

    def test_clear(self):
        for text in ("thank you for the money you sent at Christmas", "Happy birthday, Mark!", "I paid $50 for it",
                     "Call me on 555-123-4567", "We're keeping the garden going", "", None,
                     "Thanks for the cash you gave me", "Sent with love, room 1234"):
            self.assertIsNone(send_gate.asks_for(text), text)


class LineFor(unittest.TestCase):
    def test_lines(self):
        self.assertEqual(send_gate.line_for("Mark"),
                         "When you say send, it goes to Mark's email. You'll have five seconds to stop it.")
        self.assertIn("Mark's email", send_gate.line_for(PERSON))
        self.assertIn("Aunt Sue's email", send_gate.line_for("Aunt Sue"))
        self.assertIn("your son's email", send_gate.line_for("my son"))
        self.assertIn("their email", send_gate.line_for(""))
        self.assertTrue(send_gate.line_for("Mark", plain=True).startswith("Here's what I've got. When you say send"))


def module(**functions):
    return types.SimpleNamespace(**functions)


class HostCase(GateCase):
    def setUp(self):
        super().setUp()
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.host = skills_core.SkillHost(self.dir, self.dir, lambda: None, dict, lambda values: None)
        self.host.gate = self.gate
        self.host.mail_ready = lambda: True
        self.sent = []
        self.host.mailer = lambda *args: self.sent.append(args) or {"ok": True}
        self.host.enabled = lambda name: name in self.host.skills
        self.add("messages", module())

    def add(self, name, code, send_mail=True):
        manifest = {"title": name, "storage": False, "actions": [], "slow": True, "needs": {"send_mail": send_mail}}
        self.host.skills[name] = skills_core.Skill(name, self.dir, manifest, code)
        return self.host.skills[name]

    def ctx(self, name="messages"):
        return self.host.context(name)


class Context(HostCase):
    def test_arm_send_answers_and_never_raises(self):
        out = self.ctx().arm_send(PERSON, TO, "Hi", "Hello", [PICTURE])
        self.assertTrue(out["ok"])
        self.assertEqual(self.ctx().send_state()["look"], out["look"])
        self.assertEqual(self.ctx().arm_send(PERSON, TO, "Hi", "Send me money"), {"ok": False, "reason": "money"})

    def test_a_card_without_send_mail_gets_nothing(self):
        self.add("other", module(), send_mail=False)
        ctx = self.ctx("other")
        ctx.from_page = True
        self.assertEqual(ctx.arm_send(PERSON, TO, "Hi", "Hello")["reason"], "no_email")
        self.assertFalse(ctx.mail_ready())
        self.assertEqual(ctx.send_state(), send_gate.NO_LOOK)
        self.assertFalse(ctx.send_tap())
        self.assertIsNone(ctx.send_now("x"))

    def test_no_gate_means_email_isnt_set_up(self):
        self.host.gate = None
        ctx = self.ctx()
        self.assertFalse(ctx.mail_ready())
        self.assertEqual(ctx.arm_send(PERSON, TO, "Hi", "Hello")["reason"], "no_email")
        self.assertEqual(ctx.send_state()["state"], "none")

    def test_mail_ready_failure_is_false(self):
        self.host.mail_ready = lambda: 1 / 0
        self.assertFalse(self.ctx().mail_ready())

    def test_a_tool_call_cannot_move_a_send(self):
        look = self.arm()
        ctx = self.ctx()
        self.assertFalse(ctx.from_page)
        self.assertFalse(ctx.send_shown(look))
        self.gate.heard("send ti")
        self.gate.heard("sent it")
        self.assertFalse(ctx.send_tap())
        self.gate.tap()
        self.assertFalse(ctx.send_undo())
        self.clock.advance(5)
        self.assertIsNone(ctx.send_now(look))
        self.assertEqual(self.sent, [])

    def test_only_on_event_sets_from_page(self):
        seen = []
        self.add("messages", module(on_event=lambda ctx, event: seen.append(ctx.from_page),
                                    on_gate=lambda ctx, action: seen.append(ctx.from_page)))
        self.host.on_event("messages", {})
        self.arm()
        self.host.resident_said("send it")
        self.assertEqual(seen, [True, False])

    def test_the_page_sends_after_the_count(self):
        self.add("messages", module(on_event=lambda ctx, event: {"sent": ctx.send_now(event["look"])}))
        look = self.counting()
        self.assertIsNone(self.host.on_event("messages", {"look": look})["response"]["sent"])  # too early
        self.clock.advance(5)
        self.assertEqual(self.host.on_event("messages", {"look": look})["response"]["sent"], {"ok": True})
        self.assertEqual(len(self.sent), 1)
        skill, ticket, to, subject, body, pictures = self.sent[0]
        self.assertEqual((skill, ticket, to, subject, body), ("messages", "ticket-1", TO, "A card from Andy", "Happy birthday"))
        self.assertEqual(pictures, [PICTURE])
        self.assertEqual(self.mailer.minted[0][1], TO)
        self.assertEqual(self.ctx().send_state(), send_gate.NO_LOOK)
        self.assertIsNone(self.host.on_event("messages", {"look": look})["response"]["sent"])
        self.assertEqual(len(self.sent), 1)

    def test_a_failed_mint_leaves_no_look_and_no_mail(self):
        self.add("messages", module(on_event=lambda ctx, event: {"sent": ctx.send_now(event["look"])}))
        look = self.counting()
        self.clock.advance(5)
        with mock.patch.object(self.mailer, "mint_ticket", side_effect=RuntimeError):
            out = self.host.on_event("messages", {"look": look})["response"]["sent"]
        self.assertEqual(out["code"], "refused")
        self.assertEqual(self.sent, [])
        self.assertEqual(self.ctx().send_state()["state"], "none")

    def test_skills_may_not_reach_the_gate(self):
        self.assertLessEqual({"_host", "gate", "from_page", "mint_ticket"}, skills_core.FORBIDDEN_NAMES)
        self.assertIn("send_gate", skills_core.FORBIDDEN_IMPORTS)


class ResidentSaid(HostCase):
    def test_no_gate_is_none(self):
        self.host.gate = None
        self.assertIsNone(self.host.resident_said("send it"))
        self.host.her_words("anything")
        self.host.send_emergency()

    def test_nothing_to_do_is_none(self):
        self.arm()
        self.assertIsNone(self.host.resident_said("okay"))

    def test_on_gate_gives_the_say_and_effects(self):
        def on_gate(ctx, action):
            ctx.effect("count", {"name": "Mark"})
            return {"say": f"did {action}"}

        self.add("messages", module(on_gate=on_gate))
        self.arm()
        out = self.host.resident_said("send it")
        self.assertEqual((out["action"], out["say"], out["skip_brain"]), ("count", "did count", True))
        self.assertEqual(out["effects"][0]["kind"], "count")

    def test_a_skill_without_on_gate_is_skipped(self):
        self.arm(said=False)
        out = self.host.resident_said("send it")
        self.assertEqual((out["action"], out["say"], out["effects"]), ("say_line", send_gate.line_for(PERSON), []))
        self.host.her_words(send_gate.line_for(PERSON))
        self.assertEqual(self.host.resident_said("send it")["action"], "count")
        self.assertEqual(self.host.resident_said("thanks"), {"action": "quiet", "say": None, "effects": [],
                                                             "skip_brain": True})

    def test_every_action_skips_the_brain(self):
        self.assertEqual(skills_core.GATE_SKIPS_BRAIN, {"count", "stopped", "quiet", "say_line", "tap"})

    def test_a_failing_on_gate_acts_as_no_gate(self):
        self.add("messages", module(on_gate=lambda ctx, action: 1 / 0))
        self.arm()
        self.assertIsNone(self.host.resident_said("send it"))
        self.assertEqual(self.gate.state("messages")["state"], "look")

    def test_a_broken_gate_acts_as_no_gate(self):
        class Broken:
            mailer = None

            def __getattr__(self, name):
                raise RuntimeError(name)

        self.host.gate = Broken()
        self.assertIsNone(self.host.resident_said("send it"))
        self.host.her_words("words")
        self.host.send_emergency()
        self.assertEqual(self.host.forget_reach("Mark"), [])

    def test_a_look_nobody_can_finish_is_dropped(self):
        self.arm()
        del self.host.skills["messages"]
        self.assertIsNone(self.host.resident_said("send it"))
        self.assertEqual(self.gate.skill, None)

    def test_her_words_and_emergency(self):
        self.arm(said=False)
        self.host.her_words(send_gate.line_for(PERSON))
        self.assertTrue(self.gate.state("messages")["line_said"])
        self.gate.heard("send it")
        self.host.send_emergency()
        self.assertEqual(self.gate.state("messages")["state"], "look")


class Reach(HostCase):
    def test_on_forget_and_count(self):
        calls = []

        def on_forget(ctx, about, own_name):
            calls.append((about, own_name))
            return {"addresses": [TO], "texts": ["Mark, my son"]}

        self.add("messages", module(on_forget=on_forget, forget_matches=lambda ctx, about: 2))
        self.add("plain", module())
        self.arm()
        self.assertEqual(self.host.forget_count("Mark"), 2)
        self.assertEqual(self.host.forget_reach("Mark", own_name=True), [TO, "Mark, my son"])
        self.assertEqual(calls, [("Mark", True)])
        self.assertEqual(self.gate.state("messages")["state"], "none")
        self.assertEqual(self.mailer.scrubbed, [[TO]])

    def test_nothing_removed_keeps_the_look_and_the_log(self):
        self.add("messages", module(on_forget=lambda ctx, about, own_name: {"addresses": [], "texts": []}))
        self.arm()
        self.assertEqual(self.host.forget_reach("Mark"), [])
        self.assertEqual(self.gate.state("messages")["state"], "look")
        self.assertEqual(self.mailer.scrubbed, [])

    def test_everything_clears_the_log_and_the_look(self):
        calls = []
        self.add("messages", module(on_forget=lambda ctx, about, own_name: calls.append(about)))
        self.arm()
        self.assertEqual(self.host.forget_reach("All of it."), [])
        self.assertEqual(calls, ["everything"])
        self.assertEqual(self.mailer.scrubbed, [None])
        self.assertEqual(self.gate.state("messages")["state"], "none")

    def test_a_failing_skill_is_skipped(self):
        self.add("messages", module(on_forget=lambda ctx, about, own_name: 1 / 0,
                                    forget_matches=lambda ctx, about: 1 / 0))
        self.assertEqual(self.host.forget_reach("Mark"), [])
        self.assertEqual(self.host.forget_count("Mark"), 0)


class MemoryForget(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(setattr, memory_core, "FORGET_REACH", memory_core.FORGET_REACH)
        db = self.dir / "memories.db"

        def connect():
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            return conn

        first = connect()
        first.executescript(memory_core.MEMORIES_SCHEMA)
        first.close()
        self.store = memory_core.MemoryStore(connect)
        self.calls = []
        test = self

        class Fake:
            def count(self, about):
                return 1

            def forget(self, about, own_name=False):
                test.calls.append((about, own_name))
                return [TO, "Mark, my son"]

        self.fake = Fake()

    def test_no_reach(self):
        memory_core.FORGET_REACH = None
        self.assertEqual(self.store.others("Mark"), 0)
        self.assertEqual(self.store.forget("Mark"), [])

    def test_others_and_forget(self):
        memory_core.FORGET_REACH = self.fake
        self.assertEqual(self.store.others("Mark"), 1)
        self.assertEqual(self.store.forget("Mark"), [TO, "Mark, my son"])
        self.assertEqual(self.store.forget_name("Mark Hollis"), [TO, "Mark, my son"])
        self.assertEqual(self.calls, [("Mark", False), ("Mark Hollis", True)])

    def test_forget_that_never_reaches(self):
        memory_core.FORGET_REACH = self.fake
        self.assertEqual(self.store.forget(""), [])
        self.assertEqual(self.calls, [])

    def test_errors_are_nothing(self):
        memory_core.FORGET_REACH = types.SimpleNamespace(count=lambda about: 1 / 0, forget=lambda about, own_name=False: 1 / 0)
        self.assertEqual(self.store.others("Mark"), 0)
        self.assertEqual(self.store.forget("Mark"), [])

    def test_forget_mark_with_no_memory_still_asks_first(self):
        memory_core.FORGET_REACH = self.fake
        memory = types.SimpleNamespace(store=self.store, pending_forget=None, scrub=lambda *a, **k: None)
        out = mary.memory_tool(memory, "forget_memory", {"about": "Mark"})
        self.assertTrue(out["response"]["needs_yes"])
        self.assertEqual(self.calls, [])
        out = mary.memory_tool(memory, "forget_memory", {"about": "Mark", "confirmed": True})
        self.assertEqual(out["response"]["forgotten"], 2)
        self.assertEqual(self.calls, [("Mark", False)])
        self.assertNotIn(TO, json.dumps(out))


class Skills:
    """A fake host with the gate methods. out: what resident_said gives, or an exception to raise."""

    def __init__(self, out):
        self.out = out
        self.words = []
        self.emergencies = 0

    def resident_said(self, text, garbled=False):
        if isinstance(self.out, Exception):
            raise self.out
        return self.out

    def her_words(self, text):
        self.words.append(text)

    def send_emergency(self):
        self.emergencies += 1

    def offline_match(self, text, is_blocked=None):
        return None


class Reply(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        self.memory = server.mary_memory()

    def test_the_gate_takes_the_turn(self):
        skills = Skills({"action": "count", "say": "Going to Mark's email.", "skip_brain": True,
                         "effects": [{"skill": "messages", "kind": "count", "data": {}}]})
        seen = []
        out = mary.reply("send it", self.memory, skills=skills, on_effect=seen.append)
        self.assertEqual(out["text"], "Going to Mark's email.")
        self.assertEqual(len(seen), 1)
        self.assertEqual(out["effects"], seen)
        self.assertEqual(skills.words, ["Going to Mark's email."])
        self.assertEqual([turn["role"] for turn in self.memory.recent[-2:]], ["user", "model"])

    def test_a_quiet_turn_stays_silent(self):
        skills = Skills({"action": "quiet", "say": None, "effects": [], "skip_brain": True})
        out = mary.reply("thank you", self.memory, skills=skills)
        self.assertEqual((out["text"], out["mood"], out["offer"]), ("", None, None))
        self.assertEqual(skills.words, [])

    def test_a_gate_turn_makes_no_offer(self):
        skills = Skills({"action": "stopped", "say": "Stopped. It hasn't gone.", "skip_brain": True, "effects": []})
        text = "no, nobody answered my call light for two hours"
        self.assertFalse(mary.is_emergency(text))
        self.assertTrue(mary.lapse_offer(text))
        self.assertIsNone(mary.reply(text, self.memory, skills=skills)["offer"])

    def test_old_fakes_and_a_broken_gate_are_no_gate(self):
        plain = types.SimpleNamespace(offline_match=lambda text, is_blocked=None: None)
        self.assertTrue(mary.reply("hello there", self.memory, skills=plain)["text"])
        self.assertTrue(mary.reply("hello there", self.memory, skills=Skills(RuntimeError("no")))["text"])
        self.assertTrue(mary.reply("hello there", self.memory, skills=Skills({"action": "x", "skip_brain": False}))["text"])

    def test_the_emergency_comes_first(self):
        skills = Skills({"action": "quiet", "say": None, "effects": [], "skip_brain": True})
        text = "I can't breathe"
        self.assertTrue(mary.is_emergency(text))
        out = mary.reply(text, self.memory, skills=skills)
        self.assertTrue(out["emergency"])
        self.assertTrue(out["text"])
        self.assertEqual(skills.emergencies, 1)


class Routes(unittest.TestCase):
    def setUp(self):
        self.addCleanup(server.set_skill_host_for_tests, server._skill_host)

    def test_heard_gives_the_send_block(self):
        out = {"action": "count", "say": "Going.", "effects": [], "skip_brain": True}
        server.set_skill_host_for_tests(Skills(out))
        self.assertEqual(server.gate_heard("send it", ""), {"send": {"say": "Going.", "effects": [], "action": "count"}})

    def test_nothing_to_add(self):
        server.set_skill_host_for_tests(Skills(None))
        self.assertEqual(server.gate_heard("okay", ""), {})

    def test_a_broken_gate_is_no_gate(self):
        server.set_skill_host_for_tests(Skills(RuntimeError("no")))
        self.assertEqual(server.gate_heard("send it", ""), {})
        server.set_skill_host_for_tests(types.SimpleNamespace())
        self.assertEqual(server.gate_heard("send it", ""), {})
        self.assertEqual(server.gate_heard("help", "other"), {})
        server.gate_her_words("words")

    def test_the_emergency_calls_the_gate(self):
        skills = Skills(None)
        server.set_skill_host_for_tests(skills)
        self.assertEqual(server.gate_heard("help", "other"), {})
        self.assertEqual(skills.emergencies, 1)


class SMTP:
    """Stands in for smtplib.SMTP_SSL. login_error and send_error are raised at those steps."""
    login_error = None
    send_error = None

    def __init__(self, *args, **kwargs):
        self.sock = types.SimpleNamespace(settimeout=lambda seconds: None)

    def login(self, *args):
        if SMTP.login_error:
            raise SMTP.login_error

    def send_message(self, *args, **kwargs):
        if SMTP.send_error:
            raise SMTP.send_error

    def quit(self):
        pass

    def close(self):
        pass


class Mail(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(setattr, SMTP, "login_error", None)
        self.addCleanup(setattr, SMTP, "send_error", None)
        account = json.dumps({"address": "me@example.com", "provider": "gmail", "password": "abcdefghijklmnop"})
        self.log = self.dir / "mail.log"
        self.mailer = mail_core.Mailer(types.SimpleNamespace(get=lambda key: account), self.log)

    def send(self):
        ticket = self.mailer.mint_ticket("messages", TO, "Hi", "Hello")
        with mock.patch.object(mail_core.smtplib, "SMTP_SSL", SMTP):
            return self.mailer.send_for_skill("messages", ticket, TO, "Hi", "Hello")

    def test_a_clean_send(self):
        self.assertEqual(self.send(), {"ok": True})

    def test_unsure_once_it_started_going(self):
        for error in (TimeoutError(), ConnectionResetError(), OSError(), smtplib.SMTPServerDisconnected(),
                      smtplib.SMTPException(), RuntimeError()):
            SMTP.send_error = error
            out = self.send()
            self.assertEqual((out["ok"], out["code"]), (False, "unsure"), repr(error))
            self.assertEqual(out["message"], "I'm not sure that went.")

    def test_a_clear_refusal_is_refused(self):
        for error in (smtplib.SMTPDataError(554, b"no"), smtplib.SMTPSenderRefused(550, b"no", "me"),
                      smtplib.SMTPRecipientsRefused({}), smtplib.SMTPResponseException(452, b"no")):
            SMTP.send_error = error
            self.assertEqual(self.send()["code"], "refused", repr(error))

    def test_failing_before_it_goes_stays_offline(self):
        SMTP.login_error = TimeoutError()
        self.assertEqual(self.send()["code"], "offline")
        SMTP.login_error = smtplib.SMTPServerDisconnected()
        self.assertEqual(self.send()["code"], "offline")

    def lines(self):
        return [json.loads(line) for line in self.log.read_text("utf-8").splitlines()]

    def test_scrub_log(self):
        self.mailer._done("messages", "Mark@Example.org", None)
        self.mailer._done("messages", "amy@example.org", "offline")
        self.mailer.scrub_log(["MARK@example.ORG"])
        rows = self.lines()
        self.assertEqual([row["to"] for row in rows], ["", mail_core.address_mark("amy@example.org")])  # M18
        self.assertEqual([(row["ok"], row["code"]) for row in rows], [(True, ""), (False, "offline")])
        self.assertTrue(rows[0]["when"])
        self.mailer.scrub_log([])
        self.assertEqual(self.lines()[1]["to"], mail_core.address_mark("amy@example.org"))  # M18
        self.mailer.scrub_log(None)
        self.assertEqual([row["to"] for row in self.lines()], ["", ""])
        self.assertEqual([path.name for path in self.dir.iterdir()], ["mail.log"])

    def test_scrub_log_with_no_file_and_a_bad_line(self):
        self.mailer.scrub_log(None)
        self.assertFalse(self.log.exists())
        self.log.write_text('not json mark@example.org\nnot json either\n', "utf-8")
        self.mailer.scrub_log([TO])
        self.assertEqual(self.log.read_text("utf-8"), "not json either\n")

    def test_scrub_log_never_raises(self):
        self.mailer.scrub_log(5)
        with mock.patch.object(Path, "read_text", side_effect=OSError):
            self.mailer.scrub_log(None)


if __name__ == "__main__":
    unittest.main()
