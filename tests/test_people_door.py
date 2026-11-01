"""M19 piece 2: ctx.people, the one door skills have to the sealed address book."""
from tests import helpers  # noqa: F401  (first: points the data folder at scratch)

import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import address_book
import mary
import secret_store
import send_gate
import server
import skills_core

ADDRESS = "sarah.lee@example.org"
DOCTOR = "dr.jones@example.org"
HANDLE_KEYS = {"id", "name", "relationship", "kind", "has_email", "has_phone", "has_cell", "has_address", "has_facebook",
               "has_birthday", "has_notes"}
SKILL_PY = "JOB = None\n\n\ndef go(ctx):\n    return JOB(ctx)\n"


def card(name, needs, slow=False):
    manifest = {"contract": min(skills_core.SUPPORTED_CONTRACTS), "name": name, "version": "0.1.0", "title": "Door",
                "summary": "A door test.", "instructions": "A door test.", "storage": False, "offline": "works",
                "default_on": True, "needs": needs,
                "actions": [{"name": "go", "description": "Go.", "inputSchema": {"type": "object", "properties": {}}}]}
    if slow:
        manifest["slow"] = True
    return manifest


class FakeGate:
    def __init__(self):
        self.armed = []

    def arm(self, skill, person, to, subject, body, pictures):
        self.armed.append({"skill": skill, "person": person, "to": to, "subject": subject, "body": body})
        return "look1"

    def disarm(self, skill):
        pass

    def state(self, skill):
        return dict(send_gate.NO_LOOK)


class Broken:
    """A book that fails at every touch, with data in the error."""

    def __getattr__(self, name):
        def boom(*args, **kw):
            raise RuntimeError(ADDRESS)
        return boom


class Door(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="people-", dir=helpers.TMP))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.book = address_book.AddressBook(self.dir, secret_store.SecretStore(self.dir))
        self.sarah = self.book.add({"name": "Sarah Lee", "relationship": "daughter", "email": ADDRESS, "phone": "555-0100",
                                    "birthday": "03-14", "notes": "Likes lilies"})
        self.mark = self.book.add({"name": "Mark", "relationship": "brother"})
        self.hidden = self.book.add({"name": "Tom", "email": "", "asked": True, "no_keep": True, "hidden": True})
        self.doctor = self.book.add({"name": "Dr Jones", "kind": "doctor", "email": DOCTOR})

    def host(self, needs, name="door", slow=False, book="own"):
        folder = self.dir / f"skills-{name}-{len(list(self.dir.iterdir()))}"
        (folder / name).mkdir(parents=True)
        (folder / name / "manifest.json").write_text(json.dumps(card(name, needs, slow)), encoding="utf-8")
        (folder / name / "skill.py").write_text(SKILL_PY, encoding="utf-8")
        settings = {}
        db = self.dir / "s.db"
        host = skills_core.SkillHost(folder, self.dir, lambda: sqlite3.connect(db), lambda: dict(settings), settings.update)
        host.book = self.book if book == "own" else book
        host.load(is_blocked=mary.skill_blocked)
        self.assertIn(name, host.skills, host.load_errors)
        return host

    def ask(self, host, job, name="door"):
        """Runs job(ctx) inside the skill. Gives back (job's answer, the finished result)."""
        seen = {}

        def run(ctx):
            seen["answer"] = job(ctx)

        host.skills[name].module.JOB = run
        result = host.call(f"{name}__go")
        self.assertNotIn("error", result["response"], seen)
        return seen.get("answer"), result

    def plain(self, needs=None, **kw):
        return self.host({"contacts": True} if needs is None else needs, **kw)

    def full(self, **kw):
        return self.host({"contacts_full": True}, name="messages", **kw)

    def answers(self, people):
        return (people.find("Sarah"), people.everyone(), people.count(), people.locked(),
                people.detail({"id": self.sarah}, "email"), people.marks("Tom"), people.keep("New", {"email": "a@b.c"}),
                people.unkeep("Mark"))


class NoPermission(Door):
    NOTHING = ([], [], 0, False, "", {"asked": False, "no_keep": False}, None, False)

    def test_a_card_without_it_gets_nothing_not_even_a_count(self):
        answer, _ = self.ask(self.host({}), lambda ctx: self.answers(ctx.people))
        self.assertEqual(answer, self.NOTHING)
        self.assertEqual(self.book.count(), 3)  # nothing changed either

    def test_sending_and_showing_are_refused_the_same_way(self):
        host = self.host({"send_mail": True}, slow=True)
        host.gate = FakeGate()

        def job(ctx):
            ctx.people.show_address({"id": self.sarah}, "look", {"a": 1})
            return ctx.people.send_to({"id": self.sarah}, "Hi", "Hello")

        answer, result = self.ask(host, job)
        self.assertEqual(answer, {"ok": False, "reason": "no_contacts"})
        self.assertEqual(result["effects"], [])
        self.assertEqual(host.gate.armed, [])

    def test_a_plain_card_gets_no_full_answers(self):
        def job(ctx):
            return (ctx.people.detail({"id": self.sarah}, "email"), ctx.people.keep("New", {}), ctx.people.unkeep("Mark"),
                    ctx.people.marks("Tom"))

        answer, _ = self.ask(self.plain(), job)
        self.assertEqual(answer, ("", None, False, {"asked": False, "no_keep": False}))
        self.assertEqual(self.book.find("New"), [])

    def test_a_forged_mark_is_dropped(self):
        host = self.host({})

        def job(ctx):
            ctx.effect("look", {"a": 1})
            ctx.effects[-1][skills_core._SHOW_AT] = self.sarah

        _, result = self.ask(host, job)
        self.assertEqual(result["effects"], [])
        self.assertNotIn(ADDRESS, json.dumps(result))

    def test_a_mark_inside_data_does_nothing(self):
        _, result = self.ask(self.host({}), lambda ctx: ctx.effect("look", {skills_core._SHOW_AT: self.sarah}))
        self.assertNotIn(ADDRESS, json.dumps(result))


class Handles(Door):
    def test_find_gives_a_handle_with_no_values(self):
        handles, _ = self.ask(self.plain(), lambda ctx: ctx.people.find("my daughter"))
        self.assertEqual(len(handles), 1)
        handle = handles[0]
        self.assertEqual(set(handle), HANDLE_KEYS)
        self.assertEqual((handle["id"], handle["name"], handle["relationship"]), (self.sarah, "Sarah Lee", "daughter"))
        self.assertEqual([handle["has_email"], handle["has_phone"], handle["has_cell"], handle["has_birthday"]],
                         [True, True, False, True])
        for value in (ADDRESS, "555-0100", "03-14", "lilies"):
            self.assertNotIn(value, json.dumps(handle))

    def test_everyone_is_sorted_with_no_doctor_or_hidden_row(self):
        (handles, count), _ = self.ask(self.plain(), lambda ctx: (ctx.people.everyone(), ctx.people.count()))
        self.assertEqual([h["name"] for h in handles], ["Mark", "Sarah Lee"])
        self.assertEqual(count, 2)

    def test_doctors_and_hidden_rows_are_never_found(self):
        answer, _ = self.ask(self.plain(), lambda ctx: (ctx.people.find("Dr Jones"), ctx.people.find("Tom")))
        self.assertEqual(answer, ([], []))

    def test_a_full_card_still_never_sees_a_doctor(self):
        host = self.full()

        def job(ctx):
            return (ctx.people.everyone(), ctx.people.find("Dr Jones"), ctx.people.detail({"id": self.doctor}, "email"),
                    ctx.people.marks("Dr Jones"))

        answer, _ = self.ask(host, job, "messages")
        self.assertEqual([h["name"] for h in answer[0]], ["Mark", "Sarah Lee"])
        self.assertEqual(answer[1:], ([], "", {"asked": False, "no_keep": False}))

    def test_contacts_full_alone_opens_the_plain_door(self):
        count, _ = self.ask(self.full(), lambda ctx: ctx.people.count(), "messages")
        self.assertEqual(count, 2)


class SendTo(Door):
    NEEDS = {"contacts": True, "send_mail": True}

    def test_arms_the_gate_while_the_skill_holds_no_address(self):
        host = self.host(self.NEEDS, slow=True)
        host.gate = FakeGate()

        def job(ctx):
            sent = ctx.people.send_to(ctx.people.find("Sarah")[0], "Hello", "Thinking of you.")
            return sent, ctx.send_state(), list(ctx.effects)

        (sent, state, effects), result = self.ask(host, job)
        self.assertEqual(sent, {"ok": True, "look": "look1"})
        self.assertEqual(host.gate.armed[0]["to"], ADDRESS)
        self.assertEqual(host.gate.armed[0]["person"], "Sarah Lee")
        self.assertNotIn(ADDRESS, json.dumps([sent, state, effects, result]))

    def test_the_real_gate_holds_it_and_its_state_does_not_show_it(self):
        host = self.host(self.NEEDS, slow=True)
        host.gate = send_gate.SendGate(object())

        def job(ctx):
            return ctx.people.send_to({"id": self.sarah}, "Hello", "Thinking of you."), ctx.send_state()

        (sent, state), _ = self.ask(host, job)
        self.assertTrue(sent["ok"], sent)
        self.assertEqual(state["state"], "look")
        self.assertNotIn(ADDRESS, json.dumps([sent, state]))

    def test_a_replaced_arm_send_never_gets_the_address(self):
        host = self.host(self.NEEDS, slow=True)
        host.gate = FakeGate()
        stolen = []

        def job(ctx):
            ctx.arm_send = lambda *args: stolen.append(args)
            ctx.people.send_to({"id": self.sarah}, "Hello", "Thinking of you.")

        self.ask(host, job)
        self.assertEqual(stolen, [])
        self.assertEqual(host.gate.armed[0]["to"], ADDRESS)

    def test_no_address_no_person_and_made_up_handles(self):
        host = self.host(self.NEEDS, slow=True)
        host.gate = FakeGate()
        wanted = [{"id": self.mark}, {"id": "nobody"}, {"id": self.doctor}, {"id": self.hidden}, {}, "Sarah", None]

        answer, _ = self.ask(host, lambda ctx: [ctx.people.send_to(h, "Hello", "Hi") for h in wanted])
        self.assertEqual(answer, [{"ok": False, "reason": "no_address"}] * len(wanted))
        self.assertEqual(host.gate.armed, [])

    def test_a_card_without_send_mail_never_arms(self):
        host = self.plain()
        host.gate = FakeGate()
        answer, _ = self.ask(host, lambda ctx: ctx.people.send_to({"id": self.sarah}, "Hello", "Hi"))
        self.assertEqual(answer, {"ok": False, "reason": "no_email"})
        self.assertEqual(host.gate.armed, [])

    def test_a_refused_message_keeps_the_gate_reason(self):
        host = self.host(self.NEEDS, slow=True)
        host.gate = send_gate.SendGate(object())
        answer, _ = self.ask(host, lambda ctx: ctx.people.send_to({"id": self.sarah}, "Hi", "x" * 100, [("a", "b")] * 999))
        self.assertFalse(answer["ok"])
        self.assertIn(answer["reason"], ("bad_message", "too_big"))


class ShowAddress(Door):
    def test_the_address_arrives_only_in_the_finished_result(self):
        host = self.plain()

        def job(ctx):
            ctx.people.show_address({"id": self.sarah}, "look", {"line": "For Sarah"})
            return json.dumps(ctx.effects)

        seen, result = self.ask(host, job)
        self.assertNotIn(ADDRESS, seen)
        self.assertEqual(result["effects"], [{"skill": "door", "kind": "look",
                                              "data": {"line": "For Sarah", "email": ADDRESS}}])

    def test_the_skills_own_objects_never_get_it(self):
        host = self.plain()
        kept = {"line": "x"}
        held = {}

        def job(ctx):
            held["ctx"] = ctx
            ctx.people.show_address({"id": self.sarah}, "look", kept)

        self.ask(host, job)
        self.assertEqual(kept, {"line": "x"})
        self.assertNotIn(ADDRESS, json.dumps(held["ctx"].effects))

    def test_dropped_when_the_person_or_address_is_gone(self):
        host = self.plain()

        def job(ctx):
            for person_id in (self.mark, "nobody", self.doctor, self.hidden):
                ctx.people.show_address({"id": person_id}, "look", {})

        _, result = self.ask(host, job)
        self.assertEqual(result["effects"], [])

    def test_a_person_removed_during_the_call_is_dropped(self):
        def job(ctx):
            ctx.people.show_address({"id": self.sarah}, "look", {})
            self.book.remove(self.sarah)

        _, result = self.ask(self.plain(), job)
        self.assertEqual(result["effects"], [])

    def test_other_effects_pass_untouched(self):
        def job(ctx):
            ctx.effect("hello", {"a": 1})
            ctx.people.show_address({"id": self.mark}, "look", {})

        _, result = self.ask(self.plain(), job)
        self.assertEqual(result["effects"], [{"skill": "door", "kind": "hello", "data": {"a": 1}}])

    def test_a_core_kind_is_ignored(self):
        _, result = self.ask(self.plain(), lambda ctx: ctx.people.show_address({"id": self.sarah}, "show_screen", {}))
        self.assertEqual(result["effects"], [])

    def test_a_failed_call_leaves_nothing(self):
        host = self.plain()

        def job(ctx):
            ctx.people.show_address({"id": self.sarah}, "look", {})
            raise ValueError("no")

        host.skills["door"].module.JOB = job
        result = host.call("door__go")
        self.assertEqual(result["response"], {"error": "not_working"})
        self.assertEqual(result["effects"], [])

    def test_on_event_fills_it_too(self):
        host = self.plain()
        source = "def on_event(ctx, event):\n    ctx.people.show_address({'id': event['id']}, 'look', {})\n"
        host.skills["door"].module.on_event = _compiled(source)["on_event"]
        result = host.on_event("door", {"id": self.sarah})
        self.assertEqual(result["effects"][0]["data"]["email"], ADDRESS)


def _compiled(source):
    found = {}
    exec(compile(source, "skill.py", "exec"), found)  # noqa: S102 (a fixed line in this test)
    return found


class Locked(Door):
    def locked_book(self):
        book = address_book.AddressBook(self.dir, secret_store.SecretStore(self.dir))
        book.state()
        helpers.SECRETS.clear()
        book.lock()
        self.assertEqual(book.state(), "locked")
        return book

    def check_empty(self, host, name="door"):
        host.gate = FakeGate()
        answer, result = self.ask(host, lambda ctx: self.answers(ctx.people) + (
            ctx.people.send_to({"id": self.sarah}, "Hi", "Hello"),
            ctx.people.show_address({"id": self.sarah}, "look", {})), name)
        self.assertEqual(answer, ([], [], 0, True, "", {"asked": False, "no_keep": False}, None, False,
                                  {"ok": False, "reason": "no_contacts"}, None))
        self.assertEqual(result["effects"], [])

    def test_a_locked_book_gives_empty_answers(self):
        self.check_empty(self.host({"contacts_full": True, "send_mail": True}, name="messages", slow=True,
                                   book=self.locked_book()), "messages")

    def test_a_failing_book_gives_the_same_and_no_data(self):
        self.check_empty(self.host({"contacts_full": True, "send_mail": True}, name="messages", slow=True,
                                   book=Broken()), "messages")

    def test_no_book_at_all(self):
        host = self.host({"contacts_full": True, "send_mail": True}, name="messages", slow=True, book=None)
        host.gate = FakeGate()
        self.check_empty(host, "messages")

    def test_a_locked_book_stays_locked_to_a_card_without_permission(self):
        answer, _ = self.ask(self.host({}, book=self.locked_book()), lambda ctx: ctx.people.locked())
        self.assertIs(answer, False)


class Full(Door):
    def go(self, job):
        return self.ask(self.full(), job, "messages")[0]  # every test here runs as the messages card

    def test_detail_gives_the_one_value(self):
        self.assertEqual(self.go(lambda ctx: ctx.people.detail({"id": self.sarah}, "email")), ADDRESS)
        self.assertEqual(self.go(lambda ctx: ctx.people.detail({"id": self.sarah}, "cell")), "")
        self.assertEqual(self.go(lambda ctx: ctx.people.detail({"id": self.sarah}, "asked")), "")
        self.assertEqual(self.go(lambda ctx: ctx.people.detail({"id": "nobody"}, "email")), "")

    def test_marks_reach_hidden_rows(self):
        self.assertEqual(self.go(lambda ctx: ctx.people.marks("tom")), {"asked": True, "no_keep": True})
        self.assertEqual(self.go(lambda ctx: ctx.people.marks("Nobody")), {"asked": False, "no_keep": False})

    def test_keep_adds_then_updates_by_exact_name(self):
        handle = self.go(lambda ctx: ctx.people.keep("Ann", {"email": "ann@example.org", "relationship": "friend"}))
        self.assertTrue(handle["has_email"])
        self.assertNotIn("ann@example.org", json.dumps(handle))
        again = self.go(lambda ctx: ctx.people.keep("my ANN", {"phone": "555-0111"}))
        self.assertEqual(again["id"], handle["id"])
        row = self.book.get(handle["id"])
        self.assertEqual((row["email"], row["phone"], row["relationship"]), ("ann@example.org", "555-0111", "friend"))

    def test_keep_takes_only_its_fields(self):
        handle = self.go(lambda ctx: ctx.people.keep("Ann", {"email": "a@example.org", "kind": "doctor", "hidden": True}))
        row = self.book.get(handle["id"])
        self.assertEqual((row["kind"], row["hidden"]), ("person", False))

    def test_keep_hides_a_bare_no_keep_and_shows_a_row_with_detail(self):
        hidden = self.go(lambda ctx: ctx.people.keep("Ann", {"no_keep": True}))
        self.assertTrue(self.book.get(hidden["id"])["hidden"])
        shown = self.go(lambda ctx: ctx.people.keep("Ann", {"email": "ann@example.org"}))
        self.assertEqual(shown["id"], hidden["id"])
        self.assertFalse(self.book.get(hidden["id"])["hidden"])
        row = self.book.get(self.hidden)
        self.go(lambda ctx: ctx.people.keep("Tom", {"phone": "555-0122"}))
        self.assertTrue(row["hidden"])
        self.assertFalse(self.book.get(self.hidden)["hidden"])

    def test_a_birthday_that_cant_be_kept_does_not_count_as_a_detail(self):
        handle = self.go(lambda ctx: ctx.people.keep("Ann", {"no_keep": True, "birthday": "soon"}))
        self.assertTrue(self.book.get(handle["id"])["hidden"])

    def test_keep_gives_none_when_full(self):
        real, address_book.MAX_PEOPLE = address_book.MAX_PEOPLE, 2
        self.addCleanup(setattr, address_book, "MAX_PEOPLE", real)
        self.assertIsNone(self.go(lambda ctx: ctx.people.keep("Ann", {"email": "ann@example.org"})))

    def test_keep_with_no_name_or_bad_fields_gives_none(self):
        self.assertIsNone(self.go(lambda ctx: ctx.people.keep("  ", {"email": "a@example.org"})))
        self.assertIsNone(self.go(lambda ctx: ctx.people.keep("Ann", "email")))

    def test_unkeep_blanks_the_email_and_marks_the_row(self):
        self.assertTrue(self.go(lambda ctx: ctx.people.unkeep("my sarah lee")))
        row = self.book.get(self.sarah)
        self.assertEqual((row["email"], row["no_keep"], row["hidden"]), ("", True, False))  # the phone is still there
        self.assertEqual(row["phone"], "555-0100")

    def test_unkeep_hides_a_row_with_nothing_left(self):
        self.assertTrue(self.go(lambda ctx: ctx.people.unkeep("Mark")))
        self.assertTrue(self.book.get(self.mark)["hidden"])

    def test_unkeep_of_nobody_adds_a_hidden_mark(self):
        self.assertTrue(self.go(lambda ctx: ctx.people.unkeep("Ruth")))
        rows = [p for p in self.book.people(include_hidden=True) if p["name"] == "Ruth"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["no_keep"], rows[0]["hidden"]), (True, True))
        self.assertEqual(self.go(lambda ctx: ctx.people.marks("ruth")), {"asked": False, "no_keep": True})


class Contract(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="people-card-", dir=helpers.TMP))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def source(self, text):
        path = self.dir / "skill.py"
        path.write_text(text, encoding="utf-8")
        return skills_core.source_problems(path)

    def test_contacts_full_on_any_other_card_is_a_problem(self):
        for value in (True, False):
            problems = skills_core.manifest_problems(card("door", {"contacts_full": value}), "door")
            self.assertIn("needs.contacts_full is only for the messages skill", problems)
        self.assertEqual(skills_core.manifest_problems(card("messages", {"contacts_full": True}), "messages"), [])

    def test_contacts_is_open_to_any_card_and_must_be_a_boolean(self):
        self.assertEqual(skills_core.manifest_problems(card("door", {"contacts": True}), "door"), [])
        self.assertIn("needs.contacts must be true or false",
                      skills_core.manifest_problems(card("door", {"contacts": "yes"}), "door"))
        self.assertIn("needs.contacts_full must be true or false",
                      skills_core.manifest_problems(card("messages", {"contacts_full": 1}), "messages"))

    def test_the_book_and_its_lock_cant_be_imported(self):
        self.assertIn("imports address_book", self.source("import address_book\n"))
        self.assertIn("imports cryptography", self.source("from cryptography.fernet import Fernet\n"))

    def test_the_insides_of_the_door_cant_be_named(self):
        for name in ("__closure__", "__wrapped__", "__code__", "effects"):
            self.assertIn(f"uses {name}", self.source(f"def go(ctx):\n    return ctx.people.{name}\n"))

    def test_a_built_up_name_cant_walk_past_the_checks(self):
        for call in ('getattr(ctx, "_ho" + "st")', 'getattr(ctx, "_host")', 'getattr(ctx, "effects")', "getattr(ctx, name)",
                     'setattr(ctx, "_h" + "ost", 1)', 'delattr(ctx, "_host")'):
            self.assertTrue([p for p in self.source(f"def go(ctx, name):\n    return {call}\n") if "can't check" in p], call)
        self.assertEqual(self.source('def go(err):\n    return getattr(err, "reason", "failed")\n'), [])

    def test_shipped_skills_still_pass(self):
        folder = Path(skills_core.__file__).parent / "skills"
        for path in folder.glob("*/skill.py"):
            self.assertEqual(skills_core.source_problems(path), [], path.parent.name)


class TheApp(unittest.TestCase):
    def test_the_host_gets_the_one_book(self):
        helpers.start_server()
        self.assertIs(server.skill_host().book, server.BOOK)

    def test_reset_leaves_an_empty_open_book(self):
        helpers.start_server()
        helpers.reset_db()
        server.BOOK.add({"name": "Ann"})
        helpers.reset_db()
        self.assertEqual(server.BOOK.state(), "open")
        self.assertEqual(server.BOOK.count(), 0)


class Forgetting(Door):
    NOTHING = {"addresses": [], "texts": []}

    def forget(self, *args, **kw):
        return self.ask(self.full(), lambda ctx: ctx.people.forget(*args, **kw), "messages")[0]

    def rolling_ids(self):
        with closing(sqlite3.connect(self.book.backup_path)) as conn:
            return [row[0] for row in conn.execute("SELECT id FROM people")]

    def test_by_name_is_a_real_delete_and_the_rolling_copy_goes_at_once(self):
        self.book.backup(fresh=True)
        self.assertIn(self.sarah, self.rolling_ids())
        self.assertEqual(self.forget("sarah lee"),
                         {"addresses": [ADDRESS], "texts": sorted(["Sarah Lee", "555-0100", "Likes lilies"])})
        self.assertIsNone(self.book.get(self.sarah))
        self.assertNotIn(self.sarah, self.rolling_ids())

    def test_a_hidden_mark_goes_and_none_is_left(self):
        self.assertEqual(self.forget("Tom"), {"addresses": [], "texts": ["Tom"]})
        self.assertIsNone(self.book.get(self.hidden))

    def test_a_handle_takes_that_person_and_their_mark_and_no_one_else_by_name(self):
        mark = self.book.add({"name": "Sarah Lee", "no_keep": True, "hidden": True})
        other = self.book.add({"name": "Sarah Lee", "email": "other@example.org"})
        self.assertEqual(self.forget({"id": self.sarah})["addresses"], [ADDRESS])
        self.assertIsNone(self.book.get(self.sarah))
        self.assertIsNone(self.book.get(mark))
        self.assertIsNotNone(self.book.get(other))

    def test_only_the_address_is_the_unkeep_rule(self):
        self.book.backup(fresh=True)
        before = self.book.backup_path.read_bytes()
        self.assertEqual(self.forget("Sarah Lee", only_address=True), {"addresses": [ADDRESS], "texts": []})
        person = self.book.get(self.sarah)
        self.assertEqual((person["email"], person["phone"], person["no_keep"], person["hidden"]),
                         ("", "555-0100", True, False))
        self.assertNotEqual(self.book.backup_path.read_bytes(), before)

    def test_only_the_address_with_nothing_else_leaves_a_hidden_mark(self):
        amy = self.book.add({"name": "Amy", "email": "amy@example.org"})
        self.forget("Amy", only_address=True)
        self.assertEqual((self.book.get(amy)["email"], self.book.get(amy)["hidden"]), ("", True))

    def test_only_the_address_with_no_address_changes_nothing(self):
        self.assertEqual(self.forget("Mark", only_address=True), self.NOTHING)
        self.assertFalse(self.book.get(self.mark)["no_keep"])

    def test_a_doctor_is_out_of_reach(self):
        self.assertEqual(self.forget("Dr Jones"), self.NOTHING)
        self.assertEqual(self.forget({"id": self.doctor}), self.NOTHING)
        self.assertIsNotNone(self.book.get(self.doctor))

    def test_a_made_up_handle_or_a_stranger_takes_nothing(self):
        for who in ({"id": "nobody"}, {}, None, "Nobody"):
            self.assertEqual(self.forget(who), self.NOTHING)
        self.assertEqual(self.book.count(), 3)

    def test_it_needs_the_full_door(self):
        self.assertEqual(self.ask(self.plain(), lambda ctx: ctx.people.forget("Sarah Lee"))[0], self.NOTHING)
        self.assertIsNotNone(self.book.get(self.sarah))

    def test_a_broken_book_forgets_nothing_and_raises_nothing(self):
        host = self.full(book=Broken())
        self.assertEqual(self.ask(host, lambda ctx: ctx.people.forget("Sarah Lee"), "messages")[0], self.NOTHING)


if __name__ == "__main__":
    unittest.main()
