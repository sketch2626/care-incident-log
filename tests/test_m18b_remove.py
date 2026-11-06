from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M18b piece 5 (D12): removing a saved note or disconnecting email by voice first asks "are you sure?". The order only asks;
only the resident's own plain yes (send_gate.is_plain_yes, ruled by the server on the raw line) removes it. Any other line, a
60 second wait, a screen change or a reset keeps it. A fake Gemini (never the real one) and scratch data only."""
import http.client
import json
import re
import time
import unittest
from pathlib import Path
from unittest import mock

import mary
import send_gate
import server
from tests import test_tool_groups as groups
from tests.test_book_screens import read, screens_node
from tests.test_m22_orders import SETUP

KEY = "AIzaSyTESTKEY-not-a-real-key-123"
SECRET_WORDS = "ZEBRA-NOTE-WORDS-7783"  # a note's own words: they stay on the page, never in what the server tells the model
GONE = {"ok": True, "removed": {"date": "2026-10-05", "category": "No one answered my call light", "words": SECRET_WORDS}}
GONE_TEXT = "The saved note from 2026-10-05 about No one answered my call light was removed."


class PlainYesTests(unittest.TestCase):
    def test_a_plain_yes_is_one(self):
        for line in ("yes", "Yes.", "yes please", "yeah", "yep", "sure", "go ahead", "do it", "yes remove it", "yes Mary",
                     "okay do it", "Yes, remove it.", "yeah go ahead", "yes please remove that", "go ahead and do it",
                     "Mary, yes", "yes, delete it", "yes disconnect it", "yes remove it please"):
            self.assertTrue(send_gate.is_plain_yes(line), line)

    def test_anything_less_is_not(self):
        for line in ("no", "yes but wait", "yes later", "not sure", "yes?", "sure?", "okay", "ok", "alright", "please", "",
                     "remove it", "delete it", "okay remove it", "yes remove that note", "yes, don't", "don't do it",
                     "maybe yes", "yes if you think so", "yes and then no", "yes I think so", "do it later", "wait, yes",
                     "yes, but not that one", "go ahead and do it tomorrow", "never mind, yes", "sure thing",
                     "yes " + " ".join(["please"] * 12)):
            self.assertFalse(send_gate.is_plain_yes(line), line)

    def test_a_plain_remove_order_is_still_an_order_and_not_a_yes(self):
        self.assertEqual(send_gate.plain_order("remove that note")["acts"], ["remove"])
        self.assertFalse(send_gate.is_plain_yes("remove that note"))
        self.assertFalse(send_gate.is_plain_yes("remove it"))


class HeardRouteTests(unittest.TestCase):
    def heard(self, text, **more):
        status, got, _ = helpers.api("POST", "/api/mary/heard", dict({"text": text}, **more))
        self.assertEqual(status, 200)
        return got

    def test_a_plain_yes_is_answered_beside_the_order(self):
        for line in ("yes", "Yes please", "go ahead", "okay do it"):
            self.assertIs(self.heard(line).get("yes"), True, line)
        both = self.heard("yes remove it")
        self.assertIs(both.get("yes"), True)
        self.assertEqual(both["order"]["acts"], ["remove"])  # the page drops this order when it takes the yes

    def test_anything_else_is_not(self):
        for line in ("no", "yes but wait", "remove that note", "save it", "okay", "yes?", "tell me about my day"):
            self.assertNotIn("yes", self.heard(line), line)

    def test_not_for_a_typed_note(self):
        self.assertNotIn("yes", self.heard("yes", note=True))

    def test_not_in_an_emergency(self):
        got = self.heard("I can't breathe")
        self.assertTrue(got["emergency"])
        self.assertNotIn("yes", got)
        self.assertFalse(server.yes_heard("yes", "medical"))

    def test_not_when_garbled(self):
        with mock.patch.object(mary, "not_english", return_value=True):
            got = self.heard("yes")
        self.assertTrue(got["garbled"])
        self.assertNotIn("yes", got)


class OutcomeTests(unittest.TestCase):
    def test_the_outcome_names_what_went_and_never_the_notes_words(self):
        self.assertEqual(server.remove_outcome(GONE), GONE_TEXT)
        self.assertNotIn(SECRET_WORDS, server.remove_outcome(GONE))
        self.assertEqual(server.remove_outcome({"ok": True, "removed": True, "label": "Disconnect"}),
                         "Their email account was disconnected.")

    def test_a_failure_is_the_pages_own_line_or_a_plain_one(self):
        self.assertEqual(server.remove_outcome({"ok": False, "say": "Nothing is waiting for a yes."}),
                         "Nothing is waiting for a yes.")
        for odd in ({"ok": False}, {}, None, "text", {"ok": False, "say": 5}, server.SCREEN_FAILED):
            self.assertEqual(server.remove_outcome(odd), "That didn't work just now.", odd)

    def test_an_odd_date_is_left_out(self):
        got = server.remove_outcome({"ok": True, "removed": {"date": "soon <b>", "category": "Meals"}})
        self.assertEqual(got, "The saved note about Meals was removed.")


class PageTestCase(unittest.TestCase):
    def check(self, body):
        rc, _, err = screens_node(SETUP + r"""
          const ROWS = [{ id: 11, category: 'meal', occurred_date: '2026-10-01', description: 'cold food', severity: 'minor' },
            { id: 12, category: 'call_light', occurred_date: '2026-10-05', description: 'no one came', severity: 'serious' }];
          function notes(order, shown) {
            const w = world(order, shown || 'list'); w.removed = []; w.changed = 0; w.calls = 0;
            w.env.incidents = () => Promise.resolve(ROWS);
            w.env.removeIncident = id => { w.removed.push(id); return Promise.resolve({}); };
            w.page.defaultView.maryActs = { notesChanged() { w.changed++; return Promise.resolve(); },
              disconnectMail() { w.calls++; return Promise.resolve({ connected: false }); } };
            return w;
          }
          const rm = (w, a) => MaryScreens.run('remove_thing', a, w.env);
          const WAIT = 'Nothing is waiting for a yes.';
          """ + body)
        self.assertEqual(rc, 0, err)


class AskFirstTests(PageTestCase):
    def test_an_ordered_note_removal_only_asks_and_their_yes_removes_it_once(self):
        self.check(r"""
          const w = notes(ORDER('remove', 'remove that note'));
          const r = await rm(w, { when: '2026-10-05' });
          assert.strictEqual(r.ok, true, JSON.stringify(r)); assert.strictEqual(r.asked, true);
          assert.deepStrictEqual(r.would_remove, { date: '2026-10-05', category: 'No one answered my call light' });
          assert(/Nothing is removed yet/.test(r.note) && /wait for their yes/.test(r.note), r.note);
          assert(!/"id"|\b12\b|no one came/.test(JSON.stringify(r)), JSON.stringify(r));
          assert.deepStrictEqual(w.removed, []); assert.strictEqual(w.changed, 0);
          assert.strictEqual(MaryScreens.hasPending(w.env), true);
          w.env.order = null;   // the order is spent on the ask: the confirm needs none
          const done = await MaryScreens.confirmPending(w.env);
          assert.strictEqual(done.ok, true, JSON.stringify(done));
          assert.deepStrictEqual(done.removed, { date: '2026-10-05', category: 'No one answered my call light', words: 'no one came' });
          assert.deepStrictEqual(w.removed, [12]); assert.strictEqual(w.changed, 1);
          const twice = await MaryScreens.confirmPending(w.env);
          assert.strictEqual(twice.ok, false); assert.strictEqual(twice.say, WAIT);
          assert.deepStrictEqual(w.removed, [12]);
          assert.strictEqual(MaryScreens.hasPending(w.env), false);
        """)

    def test_the_old_answers_stand_and_nothing_waits_after_them(self):
        self.check(r"""
          for (const [args, say] of [[{ when: '2026-11' }, "There's nothing saved for that."],
                                     [{ category: 'meal' }, null], [{}, 'Tell me which note: the day or the kind of problem.']]) {
            const w = notes(ORDER('remove', 'delete the note'));
            const r = await rm(w, args);
            if (args.category) { assert.strictEqual(r.ok, true); assert.strictEqual(r.asked, true); }   // one meal note: it asks
            else { assert.strictEqual(r.ok, false); assert.strictEqual(r.say, say); assert.strictEqual(MaryScreens.hasPending(w.env), false); }
            assert.deepStrictEqual(w.removed, []);
            MaryScreens.cancelPending();
          }
          const none = notes(null);
          const r = await rm(none, { when: '2026-10-05' });
          assert.strictEqual(r.ok, false); assert(r.say.startsWith('Tell me plainly what to remove'), r.say);
          assert.strictEqual((await MaryScreens.confirmPending(none.env)).say, WAIT);
          assert.deepStrictEqual(none.removed, []);
        """)

    def test_a_line_asks_once(self):
        self.check(r"""
          const w = notes(ORDER('remove', 'remove that note'));
          assert.strictEqual((await rm(w, { when: '2026-10-05' })).asked, true);
          const again = await rm(w, { when: '2026-10-01' });   // the same line is spent: no second ask
          assert.strictEqual(again.ok, false);
          assert.strictEqual((await MaryScreens.confirmPending(w.env)).ok, true);   // the first ask still stands
          assert.deepStrictEqual(w.removed, [12]);
        """)

    def test_email_disconnect_asks_and_their_yes_disconnects(self):
        self.check(r"""
          const w = notes(ORDER('remove', 'disconnect my email'), 'info');
          const r = await rm(w, { field: 'mailDisconnect' });
          assert.strictEqual(r.ok, true, JSON.stringify(r)); assert.strictEqual(r.asked, true);
          assert.deepStrictEqual(r.would_remove, { what: 'email account' });
          assert.strictEqual(w.calls, 0); assert(!r.removed);
          const done = await MaryScreens.confirmPending(w.env);
          assert.strictEqual(done.ok, true, JSON.stringify(done)); assert.strictEqual(done.removed, true);
          assert(/disconnected/.test(done.note)); assert.strictEqual(w.calls, 1);
          assert.strictEqual((await MaryScreens.confirmPending(w.env)).say, WAIT); assert.strictEqual(w.calls, 1);
          const f = notes(ORDER('remove', 'disconnect my email'), 'info');   // a fill of the button asks too
          assert.strictEqual((await fill(f, 'mailDisconnect', 'x')).asked, true); assert.strictEqual(f.calls, 0);
          const bad = notes(ORDER('remove', 'disconnect my email'), 'info');
          bad.page.defaultView.maryActs.disconnectMail = () => Promise.resolve({ connected: true });
          await rm(bad, { field: 'mailDisconnect' });
          const no = await MaryScreens.confirmPending(bad.env);
          assert.strictEqual(no.ok, false); assert.strictEqual(no.say, "That didn't work just now.");
        """)

    def test_a_failed_note_removal_says_so(self):
        self.check(r"""
          const w = notes(ORDER('remove', 'remove that note'));
          w.env.removeIncident = () => Promise.reject(new Error('down'));
          await rm(w, { when: '2026-10-05' });
          const r = await MaryScreens.confirmPending(w.env);
          assert.strictEqual(r.ok, false); assert.strictEqual(r.say, "That didn't work just now.");
          assert.strictEqual(w.changed, 0);
        """)


class KeepTests(PageTestCase):
    def asked(self, extra=""):
        return r"""
          const w = notes(ORDER('remove', 'remove that note'));
          assert.strictEqual((await rm(w, { when: '2026-10-05' })).asked, true);
          """ + extra + r"""
          const r = await MaryScreens.confirmPending(w.env);
          assert.strictEqual(r.ok, false, JSON.stringify(r)); assert.strictEqual(r.say, WAIT);
          assert.deepStrictEqual(w.removed, []);
        """

    def test_a_no_or_any_other_line_keeps_it(self):
        self.check(self.asked("MaryScreens.cancelPending();"))

    def test_sixty_seconds_keeps_it(self):
        self.check(r"""
          const real = Date.now, base = real();
          try {
            Date.now = () => base;
            const w = notes(ORDER('remove', 'remove that note'));
            assert.strictEqual((await rm(w, { when: '2026-10-05' })).asked, true);
            Date.now = () => base + 59000;
            assert.strictEqual(MaryScreens.hasPending(w.env), true);
            Date.now = () => base + 60001;
            assert.strictEqual(MaryScreens.hasPending(w.env), false);
            const r = await MaryScreens.confirmPending(w.env);
            assert.strictEqual(r.ok, false); assert.strictEqual(r.say, WAIT);
            assert.deepStrictEqual(w.removed, []);
            Date.now = () => base;   // and one inside the minute does remove
            const v = notes(ORDER('remove', 'remove that note'));
            await rm(v, { when: '2026-10-05' });
            Date.now = () => base + 30000;
            assert.strictEqual((await MaryScreens.confirmPending(v.env)).ok, true);
            assert.deepStrictEqual(v.removed, [12]);
          } finally { Date.now = real; }
        """)

    def test_a_reset_keeps_it(self):
        self.check(self.asked("MaryScreens.reset();"))

    def test_a_screen_change_keeps_it(self):
        self.check(self.asked("w.page.byId.list.hidden = true; w.page.byId.add.hidden = false;"))   # a tap moved them
        self.check(self.asked("assert.strictEqual((await MaryScreens.run('go_back', {}, w.env)).ok, true);"))
        self.check(self.asked("assert.strictEqual((await MaryScreens.run('open_screen', { name: 'info_panel' }, w.env)).ok, true);"))  # a panel: the page itself never moved

    def test_a_new_ask_replaces_the_old_one(self):
        self.check(r"""
          const w = notes(ORDER('remove', 'remove that note'));
          await rm(w, { when: '2026-10-05' });
          w.env.order = ORDER('remove', 'remove that note');   // a new line, a new order
          assert.strictEqual((await rm(w, { when: '2026-10-01' })).asked, true);
          assert.strictEqual((await MaryScreens.confirmPending(w.env)).ok, true);
          assert.deepStrictEqual(w.removed, [11]);
          assert.strictEqual((await MaryScreens.confirmPending(w.env)).say, WAIT);
        """)


class NotReachableByTheModelTests(PageTestCase):
    def test_confirm_is_not_a_use_screen_action(self):
        self.check(r"""
          assert(!('confirm' in MaryScreens.ACTIONS) && !('confirm_pending' in MaryScreens.ACTIONS));
          assert(!Object.values(MaryScreens.ACTIONS).some(v => /confirm|pending/i.test(v)));
          const w = notes(ORDER('remove', 'remove that note'));
          assert.strictEqual((await rm(w, { when: '2026-10-05' })).asked, true);
          for (const action of ['confirm', 'confirm_pending', 'yes', 'cancel']) {
            const r = await MaryScreens.run('use_screen', { action }, w.env);
            assert.strictEqual(r.ok, false, action); assert.strictEqual(r.say, "That's not something I can do on this screen.");
          }
          for (const name of ['confirm', 'confirm_pending', 'confirmPending']) {
            assert.strictEqual((await MaryScreens.run(name, {}, w.env)).ok, false, name);
          }
          assert.deepStrictEqual(w.removed, []);
          assert.strictEqual(MaryScreens.hasPending(w.env), true);   // and none of it touched the ask
        """)

    def test_a_remove_through_use_screen_asks_too(self):
        self.check(r"""
          const w = notes(ORDER('remove', 'remove that note'));
          const r = await MaryScreens.run('use_screen', { action: 'remove', when: '2026-10-05' }, w.env);
          assert.strictEqual(r.asked, true, JSON.stringify(r)); assert.deepStrictEqual(w.removed, []);
        """)

    def test_clearing_a_box_is_still_immediate(self):
        self.check(r"""
          const w = world(ORDER('remove', 'clear my room number'));
          const box = w.page.byId['i-room']; box.value = '214';
          const r = await MaryScreens.run('remove_thing', { field: 'i-room' }, w.env);
          assert.strictEqual(r.ok, true, JSON.stringify(r)); assert.strictEqual(r.removed, true); assert(!r.asked);
          assert.strictEqual(box.value, '');
          assert.strictEqual(MaryScreens.hasPending(w.env), false);
          assert.strictEqual((await MaryScreens.run('put_back', { field: 'i-room' }, w.env)).ok, true);
          assert.strictEqual(box.value, '214');
        """)


class PageWiringTests(unittest.TestCase):
    """app.js acts only on the server's yes. Static checks on the page script."""

    def test_live_confirms_only_on_the_servers_yes_and_any_other_line_cancels(self):
        app = read("mary/app.js")
        body = app[app.index("function liveRemoveAnswer"):app.index("function liveEmergency")]
        self.assertEqual(len(re.findall(r"confirmPending\(", body)), 1)
        self.assertRegex(body, r"if \(j && j\.yes && !j\.emergency && !j\.garbled && S\.screen !== 'emergency'")
        self.assertIn("M.cancelPending();", body)
        self.assertIn("j.order = null;", body)
        self.assertEqual(app.count("confirmPending("), 2)  # Live's and Normal's screenConfirm: no other caller
        heard = app[app.index("function liveHeard"):app.index("function liveRemoveAnswer")]
        self.assertLess(heard.index("liveRemoveAnswer(c, j)"), heard.index("if (j && j.emergency)"))
        self.assertIn("Say plainly what went, in a few words.", body)

    def test_normal_confirms_and_cancels_on_the_servers_effects_and_always_answers(self):
        app = read("mary/app.js")
        apply = app[app.index("function applyEffect"):app.index("function skillScreen")]
        self.assertIn("'screen_confirm'", apply)
        self.assertIn("'screen_cancel'", apply)
        self.assertLess(apply.index("'screen_confirm'"), apply.index("if (T) {"))  # neither counts as a skill effect
        self.assertLess(apply.index("'screen_cancel'"), apply.index("if (T) {"))
        confirm = app[app.index("function screenConfirm"):app.index("// M18b: their_words needs")]
        self.assertIn("/api/mary/screen/result", confirm)
        self.assertIn("S.screen === 'emergency'", confirm)
        self.assertIn("answer({ ok: false })", confirm)

    def test_the_tool_text_says_a_remove_asks_first(self):
        text = [d for d in mary.LIVE_PAGE_TOOLS if d["name"] == "use_screen"][0]["description"]
        self.assertIn("are you sure?", text)
        self.assertIn("only their yes removes it", text)


class StreamCase(unittest.TestCase):
    """The route: a removal asked in Normal talk, then the next line. The page's answers are POSTed back."""

    def setUp(self):
        helpers.reset_db()
        self.memory_file = Path(server.DATA) / "mary" / "memory.json"
        self.memory_file.unlink(missing_ok=True)
        self.addCleanup(self.memory_file.unlink, missing_ok=True)
        self._real = mary._gemini_stream
        self.addCleanup(setattr, mary, "_gemini_stream", self._real)
        self.addCleanup(server.remove_drop)
        server.remove_drop()
        self.set_key(KEY)

    def set_key(self, key):
        status, _, _ = helpers.api("PUT", "/api/settings", {"gemini_key": key})
        self.assertEqual(status, 200)

    def stream_talk(self, text, answer):
        """Every NDJSON line. A screen_call or screen_confirm is answered with answer(kind, data)."""
        conn = http.client.HTTPConnection("127.0.0.1", helpers.start_server(), timeout=10)
        lines = []
        try:
            conn.request("POST", "/api/mary/talk?stream=1", body=json.dumps({"text": text}),
                         headers={"X-Tracker": "1", "Content-Type": "application/json"})
            resp = conn.getresponse()
            while True:
                raw = resp.readline()
                if not raw:
                    break
                got = json.loads(raw)
                lines.append(got)
                effect = got.get("effect") or {}
                if effect.get("kind") in ("screen_call", "screen_confirm"):
                    status, _, _ = helpers.api("POST", "/api/mary/screen/result",
                                               {"id": effect["data"]["id"], "response": answer(effect["kind"], effect["data"])})
                    self.assertEqual(status, 200)
                if "done" in got:
                    break
        finally:
            conn.close()
        return lines

    @staticmethod
    def kinds(lines):
        return [x["effect"]["kind"] for x in lines if "effect" in x]

    def answer(self, kind, data):
        if kind == "screen_confirm":
            self.confirmed.append(data)
            return GONE
        return {"ok": True, "asked": True, "would_remove": {"date": "2026-10-05", "category": "No one answered my call light"}}

    def setUpAsked(self):
        self.confirmed = []
        server.remove_drop()
        fake = mary._gemini_stream = groups.Rounds([groups.call(groups.fc("use_screen", {"action": "remove", "when": "2026-10-05"}))],
                                                   ["Are you sure you want to remove it?"])
        lines = self.stream_talk("remove that note", self.answer)
        self.assertEqual(lines[-1]["text"], "Are you sure you want to remove it?")
        return fake

    def test_an_asked_answer_starts_the_wait(self):
        self.assertFalse(server.remove_waiting())
        self.setUpAsked()
        self.assertTrue(server.remove_waiting())
        self.assertEqual(self.confirmed, [])  # asking removes nothing

    def test_an_answer_that_did_not_ask_starts_no_wait(self):
        self.confirmed = []
        mary._gemini_stream = groups.Rounds([groups.call(groups.fc("use_screen", {"action": "look"}))], ["Here."])
        self.stream_talk("turn it off", lambda kind, data: {"ok": True, "screen": "x", "asked": "yes"})  # not a real True
        self.assertFalse(server.remove_waiting())

    def test_a_plain_yes_confirms_and_the_outcome_reaches_the_model(self):
        self.setUpAsked()
        fake = mary._gemini_stream = groups.Rounds(["It's gone."])
        lines = self.stream_talk("yes", self.answer)
        self.assertEqual(self.kinds(lines), ["screen_confirm"])
        self.assertEqual(len(self.confirmed), 1)
        self.assertEqual(set(self.confirmed[0]), {"id"})
        self.assertEqual(lines[-1]["text"], "It's gone.")
        sent = json.dumps(fake.bodies[0])
        self.assertIn(GONE_TEXT, sent)
        self.assertNotIn(SECRET_WORDS, sent)
        self.assertNotIn("tools", fake.bodies[0])  # a told turn has no tool rounds
        self.assertFalse(server.remove_waiting())
        self.assertEqual(lines[-1]["mood"], "talking")

    def test_a_yes_with_no_key_shows_the_outcome_as_a_screen_notice(self):
        self.setUpAsked()
        real = server.mary_settings
        with mock.patch.object(server, "mary_settings", lambda: dict(real(), key="")):
            lines = self.stream_talk("yes", self.answer)
        self.assertEqual(self.kinds(lines), ["screen_confirm"])
        done = lines[-1]
        self.assertEqual(done["text"], "")
        self.assertIn(GONE_TEXT, done["notice"])
        self.assertEqual(done["mood"], "talking")

    def test_a_failed_removal_is_told_in_the_pages_words(self):
        self.setUpAsked()
        fake = mary._gemini_stream = groups.Rounds(["That didn't go."])
        self.stream_talk("go ahead", lambda kind, data: {"ok": False, "say": "That didn't work just now."})
        self.assertIn("That didn't work just now.", json.dumps(fake.bodies[0]))

    def test_any_other_line_cancels_and_removes_nothing(self):
        for line in ("no thanks", "wait", "tell me about my day", "yes but not that one", "remove that note"):
            self.setUpAsked()
            fake = mary._gemini_stream = groups.Rounds(["All right."])
            lines = self.stream_talk(line, self.answer)
            self.assertEqual(self.kinds(lines).count("screen_cancel"), 1, line)
            self.assertNotIn("screen_confirm", self.kinds(lines), line)
            self.assertEqual(self.confirmed, [], line)
            self.assertFalse(server.remove_waiting(), line)
            self.assertNotIn(GONE_TEXT, json.dumps(fake.bodies[0]), line)
            # a yes after that finds nothing to confirm
            mary._gemini_stream = groups.Rounds(["Okay."])
            self.assertNotIn("screen_confirm", self.kinds(self.stream_talk("yes", self.answer)), line)

    def test_a_stale_wait_does_nothing(self):
        self.setUpAsked()
        server._remove_asked = time.monotonic() - server.REMOVE_ASK_S - 1
        for line in ("yes", "no thanks"):
            mary._gemini_stream = groups.Rounds(["Okay."])
            lines = self.stream_talk(line, self.answer)
            self.assertEqual([k for k in self.kinds(lines) if k.startswith("screen_c")], [], line)
        self.assertEqual(self.confirmed, [])

    def test_an_emergency_line_never_confirms_and_the_wait_is_not_used(self):
        self.setUpAsked()
        mary._gemini_stream = groups.Rounds(["I'm here."])
        lines = self.stream_talk("I can't breathe", self.answer)
        self.assertEqual([k for k in self.kinds(lines) if k.startswith("screen_c")], [], lines)
        self.assertEqual(self.confirmed, [])
        self.assertTrue(lines[-1]["emergency"])
        self.assertFalse(server.yes_heard("yes", mary.is_emergency("I can't breathe") or ""))

    def test_a_yes_never_runs_a_second_removal_by_its_own_order(self):
        self.setUpAsked()
        seen = []
        fake = mary._gemini_stream = groups.Rounds(["Done."])
        self.stream_talk("yes remove it", lambda kind, data: seen.append((kind, data.get("order"))) or GONE)
        self.assertEqual([k for k, _ in seen], ["screen_confirm"])
        self.assertIn(GONE_TEXT, json.dumps(fake.bodies[0]))

    def test_a_yes_on_a_screen_the_page_cannot_confirm_is_told_plainly(self):
        self.setUpAsked()
        fake = mary._gemini_stream = groups.Rounds(["Nothing was waiting."])
        self.stream_talk("yes", lambda kind, data: {"ok": False, "say": "Nothing is waiting for a yes."})
        self.assertIn("Nothing is waiting for a yes.", json.dumps(fake.bodies[0]))


class ReplyTests(groups.Base):
    """mary.reply with app_told: the app's outcome goes through the model like any other (D1)."""

    def test_the_outcome_goes_to_the_model_and_a_yes_for_an_offer_does_not_also_save(self):
        saved = []
        self.memory.pending_offer = {"incident": {"category": "meal", "description": "cold food"}, "at": time.time()}
        fake = mary._gemini_stream = groups.Rounds(["It's gone."])
        r = mary.reply("yes", self.memory, groups.KEY, write=lambda inc: saved.append(inc) or 1, app_told=GONE_TEXT)
        self.assertEqual(r["text"], "It's gone.")
        self.assertIn(GONE_TEXT, json.dumps(fake.bodies[0]))
        self.assertEqual(saved, [])  # the yes went to the removal
        self.assertEqual(r["mood"], "talking")

    def test_no_key_is_a_notice_and_never_speech(self):
        r = mary.reply("yes", self.memory, "", app_told=GONE_TEXT)
        self.assertEqual((r["text"], r["notice"], r["mood"]), ("", GONE_TEXT, "talking"))

    def test_an_emergency_ignores_it(self):
        mary._gemini_stream = groups.Rounds(["I'm here."])
        r = mary.reply("I can't breathe", self.memory, groups.KEY, app_told=GONE_TEXT)
        self.assertTrue(r["emergency"])
        self.assertNotIn(GONE_TEXT, json.dumps(mary._gemini_stream.bodies[0]))
        self.assertEqual(r["mood"], "alert")


if __name__ == "__main__":
    unittest.main()
