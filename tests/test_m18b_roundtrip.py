from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M18b piece 1: the screen tool in Normal talk. The model asks for the screen, the server sends the page a screen_call
down the talk stream, the page does it and POSTs the answer back, and the answer goes to the model only.
A fake Gemini (never the real one), temp data folders and the in-process server."""
import http.client
import json
import threading
import unittest
from pathlib import Path
from unittest import mock

import mary
import server
from tests import test_tool_groups as groups

KEY = "AIzaSyTESTKEY-not-a-real-key-123"
MARKER = "ZEBRA-BOX-CONTENTS-4471"  # stands for what is typed in a box: it may go to the model and nowhere else
OPEN_NOTES = {"action": "open", "name": "notes"}


def use_screen(args=None):
    return groups.call(groups.fc("use_screen", args or OPEN_NOTES))


def sent_back(body):
    """The functionResponse parts the model was sent in this request's last user turn."""
    return [p["functionResponse"] for p in body["contents"][-1]["parts"]]


class PageCalls(groups.Base):
    """mary.reply with a page: the body, the tool loop and what must never happen."""

    def setUp(self):
        super().setUp()
        self.asked = []
        self.answer = {"ok": True, "screen": "notes", "boxes": []}

    def page(self, name, args):
        self.asked.append((name, args))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def talk(self, text, *scripts, use_page=True, store=False, host=None):
        if store:
            self.memory.store = server.memory_store()
        self.fake = mary._gemini_stream = groups.Rounds(*scripts)
        return mary.reply(text, self.memory, groups.KEY, skills=host, on_effect=self.seen.append,
                          page=self.page if use_page else None)

    # (a) the body

    def test_a_normal_body_declares_use_screen_only_with_a_page(self):
        self.memory.store = server.memory_store()
        host = self.build(fakes=[("fake0", 9)])
        plain = mary._body("Hello", self.memory, "", skills=host)
        paged = mary._body("Hello", self.memory, "", skills=host, page_tool=True)
        names = lambda body: [d["name"] for d in body["tools"][0]["functionDeclarations"]]  # noqa: E731
        self.assertNotIn("use_screen", names(plain))
        self.assertLessEqual(len(names(plain)), 12)
        self.assertEqual(len(paged["tools"]), 1)  # the one functionDeclarations list
        self.assertIn("use_screen", names(paged))
        self.assertLessEqual(len(names(paged)), 13)
        self.assertEqual(len(names(paged)), len(names(plain)) + 1)
        declared = next(d for d in paged["tools"][0]["functionDeclarations"] if d["name"] == "use_screen")
        self.assertIs(declared, next(d for d in mary.LIVE_PAGE_TOOLS if d["name"] == "use_screen"))  # one description

    def test_a_page_alone_is_enough_for_the_tool(self):
        body = mary._body("Hello", self.memory, "", page_tool=True)  # no skills, no memory store
        self.assertEqual([d["name"] for d in body["tools"][0]["functionDeclarations"]], ["use_screen"])
        self.assertNotIn("tools", mary._body("Hello", self.memory, ""))

    # (b) a call reaches the page, and its answer comes back

    def test_b_use_screen_reaches_the_page_and_the_answer_is_the_functionResponse(self):
        r = self.talk("Open my notes please", [use_screen()], ["Here are your notes."])
        self.assertEqual(self.asked, [("use_screen", OPEN_NOTES)])
        (back,) = sent_back(self.fake.bodies[1])
        self.assertEqual((back["name"], back["response"]), ("use_screen", self.answer))
        self.assertEqual(r["text"], "Here are your notes.")
        self.assertIn("use_screen", json.dumps(self.fake.bodies[0]["tools"]))  # a page-only setup works

    def test_b_with_skills_and_memory_too(self):
        host = self.build(fakes=[("fake0", 3)])
        self.talk("Open my notes please", [use_screen()], ["Here."], store=True, host=host)
        self.assertEqual(self.asked, [("use_screen", OPEN_NOTES)])
        self.assertEqual(sent_back(self.fake.bodies[1])[0]["response"], self.answer)

    def test_b_a_page_that_fails_answers_not_ok(self):
        for bad in (RuntimeError("page is gone"), "text", ["list"], None):
            self.answer = bad
            self.talk("Open my notes please", [use_screen()], ["It didn't open."])
            self.assertEqual(sent_back(self.fake.bodies[1])[0]["response"], {"ok": False}, bad)

    def test_b_the_tool_rounds_stay_capped(self):
        self.talk("Open my notes please", [use_screen()])  # asks again every round
        self.assertEqual(len(self.fake.bodies), mary.MAX_TOOL_ROUNDS + 1)
        self.assertEqual(len(self.asked), mary.MAX_TOOL_ROUNDS)

    def test_b_without_a_page_nothing_is_declared_and_a_call_goes_nowhere(self):
        self.talk("Open my notes please", [use_screen()], ["I can't."], use_page=False, store=True)
        self.assertNotIn("use_screen", json.dumps(self.fake.bodies[0]["tools"]))
        self.assertEqual(self.asked, [])

    # (c) add a person opens a blank form, in both spellings

    def test_c_add_to_book_opens_the_blank_person_form(self):
        spellings = [("messages__add_to_book", {"name": "Tom"}),
                     ("use_skill", {"action": "add_to_book", "details": "Tom, my brother"})]
        for name, args in spellings:
            self.asked.clear()
            self.talk("Add Tom to my address book", [groups.call(groups.fc(name, args))], ["The form is open."])
            self.assertEqual(self.asked, [("open_screen", {"name": "book-form"})], name)
            (back,) = sent_back(self.fake.bodies[1])
            self.assertEqual((back["name"], back["response"]), (name, self.answer))  # under the name she called

    def test_c_other_use_skill_actions_never_reach_the_page(self):
        self.talk("Start a game", [groups.call(groups.fc("use_skill", {"action": "start"}))], ["No."])
        self.assertEqual(self.asked, [])

    # (d) an emergency gets no page tool

    def test_d_an_emergency_gets_no_page_tool(self):
        host = self.build(fakes=[("fake0", 3)])
        text = "I think I am having a heart attack"
        self.assertTrue(mary.is_emergency(text))
        self.memory.store = server.memory_store()
        self.fake = mary._gemini_stream = groups.Rounds([use_screen()], ["Stay with me."])
        mary.reply(text, self.memory, groups.KEY, skills=host, page=self.page)
        self.assertNotIn("tools", self.fake.bodies[0])
        self.assertEqual(len(self.fake.bodies), 1)  # her tool call isn't run in an emergency
        self.assertEqual(self.asked, [])

    # (h) what the page answered stays with the model

    def test_h_a_page_answer_is_not_remembered(self):
        self.answer = {"ok": True, "boxes": [{"field": "Name", "value": MARKER}]}
        r = self.talk("Open my notes please", [use_screen()], ["It is open."], store=True)
        self.assertIn(MARKER, json.dumps(self.fake.bodies[1]))  # the model got it
        self.assertEqual([t["text"] for t in self.memory.recent], ["Open my notes please", "It is open."])
        self.assertNotIn(MARKER, json.dumps(r))


class StreamCase(unittest.TestCase):
    """The route: a streamed talk with a page, and the page's answer POSTed back."""

    def setUp(self):
        helpers.reset_db()
        self.memory_file = Path(server.DATA) / "mary" / "memory.json"
        self.memory_file.unlink(missing_ok=True)
        self.addCleanup(self.memory_file.unlink, missing_ok=True)
        self._real = mary._gemini_stream
        self.addCleanup(setattr, mary, "_gemini_stream", self._real)
        status, _, _ = helpers.api("PUT", "/api/settings", {"gemini_key": KEY})
        self.assertEqual(status, 200)

    def stream_talk(self, text, answer=None, path="/api/mary/talk?stream=1"):
        """Reads the NDJSON as it comes. Each screen_call is answered by POST /api/mary/screen/result with answer(data)
        (no answer: the page stays quiet). Returns every line."""
        conn = http.client.HTTPConnection("127.0.0.1", helpers.start_server(), timeout=10)
        lines = []
        try:
            conn.request("POST", path, body=json.dumps({"text": text}),
                         headers={"X-Tracker": "1", "Content-Type": "application/json"})
            resp = conn.getresponse()
            while True:
                raw = resp.readline()
                if not raw:
                    break
                got = json.loads(raw)
                lines.append(got)
                effect = got.get("effect") or {}
                if effect.get("kind") == "screen_call" and answer is not None:
                    status, body, _ = helpers.api("POST", "/api/mary/screen/result",
                                                  {"id": effect["data"]["id"], "response": answer(effect["data"])})
                    self.assertEqual(status, 200)
                if "done" in got:
                    break
        finally:
            conn.close()
        return lines

    @staticmethod
    def calls(lines):
        return [x["effect"]["data"] for x in lines if (x.get("effect") or {}).get("kind") == "screen_call"]

    # (e) the round trip

    def test_e_the_stream_asks_the_page_and_the_answer_reaches_the_model(self):
        fake = mary._gemini_stream = groups.Rounds([use_screen({"action": "look"})], ["It's open."])
        lines = self.stream_talk("turn it off", answer=lambda data: {"ok": True, "echo": data["name"]})
        (data,) = self.calls(lines)
        self.assertEqual((data["name"], data["args"]), ("use_screen", {"action": "look"}))
        self.assertEqual(data["order"]["acts"], ["off"])  # D12: the server's ruling on this turn's own words
        self.assertTrue(data["id"])
        self.assertTrue(lines[-1]["done"])
        self.assertEqual(lines[-1]["text"], "It's open.")
        self.assertIn("use_screen", json.dumps(fake.bodies[0]["tools"]))
        self.assertEqual(sent_back(fake.bodies[1])[0]["response"], {"ok": True, "echo": "use_screen"})
        self.assertEqual(server._screen_pending, {})  # nothing is left waiting

    def test_e_an_ordinary_line_has_no_order(self):
        mary._gemini_stream = groups.Rounds([use_screen({"action": "look"})], ["Fine."])
        lines = self.stream_talk("I like it out on the porch", answer=lambda data: {"ok": True})
        self.assertIsNone(self.calls(lines)[0]["order"])

    def test_e_a_plain_talk_without_the_stream_has_no_page(self):
        fake = mary._gemini_stream = groups.Rounds(["Hello there."])
        status, body, _ = helpers.api("POST", "/api/mary/talk", {"text": "Good morning"})
        self.assertEqual(status, 200)
        self.assertNotIn("use_screen", json.dumps(fake.bodies[0].get("tools")))

    def test_e_an_emergency_on_the_stream_asks_the_page_for_nothing(self):
        fake = mary._gemini_stream = groups.Rounds([use_screen()], ["Stay with me."])
        lines = self.stream_talk("I think I am having a heart attack", answer=lambda data: {"ok": True})
        self.assertEqual(self.calls(lines), [])
        self.assertNotIn("tools", fake.bodies[0])
        self.assertTrue(lines[-1]["done"])

    # (f) a page that never answers

    def test_f_a_wait_that_runs_out_answers_not_ok(self):
        fake = mary._gemini_stream = groups.Rounds([use_screen()], ["That didn't open."])
        with mock.patch.object(server, "SCREEN_WAIT_S", 0.2):
            lines = self.stream_talk("open my notes")  # the page says nothing
        self.assertEqual(len(self.calls(lines)), 1)
        self.assertEqual(sent_back(fake.bodies[1])[0]["response"], {"ok": False, "say": "That didn't work just now."})
        self.assertTrue(lines[-1]["done"])
        self.assertEqual(server._screen_pending, {})

    def test_f_a_closed_stream_fails_at_once(self):
        with mock.patch.object(server, "SCREEN_WAIT_S", 5):
            self.assertEqual(server.screen_ask(lambda event: False, "use_screen", {}, None), server.SCREEN_FAILED)
        self.assertEqual(server._screen_pending, {})

    # (g) the result route

    def pending(self, call_id="abc123"):
        entry = {"event": threading.Event(), "response": None}
        server._screen_pending[call_id] = entry
        self.addCleanup(server._screen_pending.pop, call_id, None)
        return entry

    def result(self, call_id, response, **kw):
        return helpers.api("POST", "/api/mary/screen/result", {"id": call_id, "response": response}, **kw)

    def test_g_unknown_and_old_ids_are_ignored(self):
        self.assertEqual(self.result("nope", {"ok": True})[:2], (200, {"ok": False}))
        entry = self.pending()
        self.assertEqual(self.result("abc123", {"ok": True, "n": 1})[1], {"ok": True})
        self.assertEqual(entry["response"], {"ok": True, "n": 1})
        self.assertEqual(self.result("abc123", {"ok": True, "n": 2})[1], {"ok": False})  # already answered
        self.assertEqual(entry["response"], {"ok": True, "n": 1})
        for odd in (None, 5, ["x"], {"a": 1}):
            self.assertEqual(helpers.api("POST", "/api/mary/screen/result", {"id": odd, "response": {}})[1],
                             {"ok": False})

    def test_g_an_oversize_or_odd_answer_becomes_not_ok(self):
        for response in ({"blob": "x" * (server.SCREEN_ANSWER_MAX + 1)}, "text", ["list"], 7, None):
            entry = self.pending()
            self.assertEqual(self.result("abc123", response)[1], {"ok": True})
            self.assertEqual(entry["response"], {"ok": False}, str(response)[:20])
            server._screen_pending.pop("abc123", None)
        entry = self.pending()  # right at the limit still goes through
        small = {"blob": "x" * (server.SCREEN_ANSWER_MAX - 20)}
        self.result("abc123", small)
        self.assertEqual(entry["response"], small)

    def test_g_it_needs_the_tracker_header_and_takes_no_talk_lock(self):
        entry = self.pending()
        status, _, _ = self.result("abc123", {"ok": True}, tracker=False)
        self.assertNotEqual(status, 200)
        self.assertFalse(entry["event"].is_set())
        with server._mary_lock:  # a talk holds this while it waits, so the answer must get in without it
            status, body, _ = self.result("abc123", {"ok": True})
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertTrue(entry["event"].is_set())

    # (h) the answer lives only in the wait

    def test_h_a_page_answer_is_in_no_memory_and_no_file(self):
        mary._gemini_stream = groups.Rounds([use_screen({"action": "look"})], ["Your name box is there."])
        lines = self.stream_talk("look at the screen", answer=lambda data: {"ok": True, "boxes": [{"value": MARKER}]})
        self.assertTrue(lines[-1]["done"])
        self.assertNotIn(MARKER, json.dumps(lines[-1]))  # not even in the reply's own answer
        memory = server.mary_memory()
        self.assertEqual([t["text"] for t in memory.recent], ["look at the screen", "Your name box is there."])
        self.assertEqual(memory.store.active(), [])
        found = []
        for path in Path(server.DATA).rglob("*"):
            try:
                if path.is_file() and MARKER.encode() in path.read_bytes():
                    found.append(str(path))
            except OSError:
                pass
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
