from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M9c: Mary's long memory (memory_core.py): the table and move, the store, the core sent every turn, recall, forget,
the offline phrases, Normal talk with a fake Gemini, Live's tool route and the page routes. No network."""
import json
import unittest
from pathlib import Path

import mary
import memory_core
import server

KEY = "AIzaSyTESTKEY-not-a-real-key-123"
EMERGENCY = "I can't breathe"


def store():
    return memory_core.MemoryStore(server.connect)


def rows(sql="SELECT * FROM memories ORDER BY id"):
    return helpers.db_rows(sql)


class Case(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        self.file = Path(server.DATA) / "mary" / "memory.json"
        self.file.unlink(missing_ok=True)
        self.store = store()
        self.addCleanup(self.file.unlink, missing_ok=True)

    def age(self, memory_id, days):
        import sqlite3
        from contextlib import closing
        from datetime import datetime, timedelta
        old = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            conn.execute("UPDATE memories SET created_at = ? WHERE id = ?", (old, memory_id))
            conn.commit()


class TestTableAndMove(Case):
    def test_init_creates_table(self):
        self.assertTrue(rows("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"))

    def test_move_once_in_order_file_untouched(self):
        src = Path(helpers.TMP) / "old-memory.json"
        src.write_text(json.dumps({"name": "Ruth", "facts": ["First fact", "Second fact", "Third fact"]}), encoding="utf-8")
        before = src.read_bytes()
        self.assertEqual(memory_core.migrate_json(src, self.store), 3)
        self.assertEqual([m["text"] for m in reversed(self.store.active())], ["First fact", "Second fact", "Third fact"])
        self.assertEqual(src.read_bytes(), before)
        self.assertEqual(rows("SELECT value FROM settings WHERE key='memories_moved'")[0]["value"], "1")
        self.store.remove(self.store.active()[-1]["id"])
        self.assertEqual(memory_core.migrate_json(src, self.store), 0)
        self.assertEqual(self.store.count(), 2)
        self.assertEqual(src.read_bytes(), before)

    def test_bad_or_missing_json_does_not_raise(self):
        bad = Path(helpers.TMP) / "bad-memory.json"
        cases = [None, "{not json", "[1, 2]", '{"facts": "nope"}', '{"facts": [1, null, ["x"]]}', ""]
        for content in cases:
            helpers.reset_db()
            if content is None:
                bad.unlink(missing_ok=True)
            else:
                bad.write_text(content, encoding="utf-8")
            self.assertEqual(memory_core.migrate_json(bad, self.store), 0, content)
        helpers.reset_db()
        bad.write_text('{"facts": [1, "ok fact", null]}', encoding="utf-8")
        self.assertEqual(memory_core.migrate_json(bad, self.store), 1)


class TestStore(Case):
    def test_no_cap(self):
        for i in range(100):
            self.assertIsNotNone(self.store.add(f"Fact number {i} about something"))
        self.assertEqual(self.store.count(), 100)
        self.assertEqual(len(self.store.active()), 100)

    def test_duplicates_case_insensitive(self):
        self.assertIsNotNone(self.store.add("Likes tea"))
        self.assertIsNone(self.store.add("likes TEA"))
        self.assertIsNone(self.store.add("  Likes   tea "))
        self.assertEqual(self.store.count(), 1)

    def test_soft_delete_and_save_again(self):
        mid = self.store.add("Likes tea")
        self.assertTrue(self.store.remove(mid))
        self.assertFalse(self.store.remove(mid))
        row = rows(f"SELECT * FROM memories WHERE id={mid}")
        self.assertEqual(len(row), 1)
        self.assertTrue(row[0]["deleted_at"])
        self.assertEqual(self.store.active(), [])
        self.assertEqual(self.store.recall("tea"), [])
        self.assertEqual(self.store.always_sent(), "")
        self.assertIsNotNone(self.store.add("Likes tea"))
        self.assertEqual(self.store.count(), 1)

    def test_remove_bad_ids(self):
        for bad in ("x", None, 0, -3, 2 ** 70):
            self.assertFalse(self.store.remove(bad))

    def test_key_shape_refused(self):
        self.assertIsNone(self.store.add("My key is AIza" + "a" * 30))
        self.assertIsNone(self.store.add("AIza" + "b" * 30))
        self.assertEqual(self.store.count(), 0)


class TestAlwaysSent(Case):
    def words(self, text):
        return len(text.split())

    def test_cap_with_long_memories(self):
        for i in range(30):
            self.store.add(f"Story {i} " + " ".join(f"word{j}" for j in range(30)))
        out = self.store.always_sent("Ruth")
        self.assertLessEqual(self.words(out), 120)
        self.assertTrue(out.startswith("Name: Ruth"))

    def test_cap_with_long_veteran_memories(self):
        for i in range(30):
            self.store.add(f"Veteran number {i} served with pride " + " ".join(f"item{j}" for j in range(25)))
        for i in range(5):
            self.store.add("Ordinary memory about gardening " + " ".join(f"leaf{j}" for j in range(25)))
        out = self.store.always_sent("Ruth")
        self.assertLessEqual(self.words(out), 120)
        self.assertTrue(out.startswith("Name: Ruth"))
        self.assertIn(memory_core.SAFETY_LABEL, out)

    def test_veteran_always_included_even_oldest_of_50(self):
        self.store.add("Is a veteran of the Army")
        for i in range(49):
            self.store.add(f"Plain note {i} about the garden")
        out = self.store.always_sent("Ruth")
        self.assertIn("veteran of the Army", out)
        self.assertLessEqual(self.words(out), 120)

    def test_not_safety_lookalikes(self):
        self.assertFalse(memory_core.is_safety("Not a veteran"))
        self.assertFalse(memory_core.is_safety("Took the dog to the vet"))
        self.assertTrue(memory_core.is_safety("Is a veteran"))
        self.store.add("Not a veteran")
        self.store.add("Took the dog to the vet last week")
        out = self.store.always_sent()
        self.assertNotIn(memory_core.SAFETY_LABEL, out)

    def test_nickname_always_included(self):
        self.store.add("Likes to be called Sugar")
        for i in range(10):
            self.store.add(f"Plain note {i} about the garden")
        out = self.store.always_sent("Ruth")
        self.assertIn("Likes to be called Sugar", out)
        self.assertIn(memory_core.SAFETY_LABEL, out)

    def test_more_line_only_when_more_exist(self):
        self.store.add("Likes tea")
        self.assertNotIn(memory_core.MORE_LINE, self.store.always_sent("Ruth"))
        for i in range(3):
            self.store.add(f"Plain note {i} about the garden")
        self.assertIn(memory_core.MORE_LINE, self.store.always_sent("Ruth"))

    def test_empty(self):
        self.assertEqual(self.store.always_sent("Ruth"), "Name: Ruth")
        self.assertEqual(self.store.always_sent(), "")


class TestSystemText(Case):
    def test_core_not_old_memory(self):
        memory = server.mary_memory()
        for i in range(6):
            memory.add_fact(f"Gardening memory number {i}")
        text = mary.system_text(memory)
        for i in (3, 4, 5):
            self.assertIn(f"Gardening memory number {i}", text)
        for i in (0, 1, 2):
            self.assertNotIn(f"Gardening memory number {i}", text)
        self.assertIn(memory_core.MORE_LINE, text)

    def test_plain_memory_lists_facts(self):
        memory = mary.Memory(self.file)
        memory.facts = ["Likes tea", "Has a dog"]
        text = mary.system_text(memory)
        self.assertIn("- Likes tea", text)
        self.assertIn("- Has a dog", text)

    def test_empty_store_equals_plain_no_facts(self):
        self.assertEqual(mary.system_text(server.mary_memory()), mary.system_text(mary.Memory(self.file)))


class TestRecall(Case):
    def test_exact_and_synonym(self):
        self.store.add("My daughter Ann lives in Raleigh")
        self.assertEqual(len(self.store.recall("Raleigh")), 1)
        self.assertEqual(len(self.store.recall("kids")), 1)

    def test_whole_words_only(self):
        self.store.add("Met a nice person at church")
        self.store.add("Went to the Annual picnic")
        self.assertEqual(self.store.recall("son"), [])
        self.assertEqual(self.store.recall("Ann"), [])

    def test_stopwords_and_no_hits(self):
        self.store.add("Likes tea")
        self.assertEqual(self.store.recall("what do you remember about that"), [])
        self.assertEqual(self.store.recall("submarine"), [])

    def test_kind_filter(self):
        self.store.add("Likes tea", kind="likes")
        self.store.add("Tea with the pastor", kind="person")
        got = self.store.recall("tea", kind="person")
        self.assertEqual([m["text"] for m in got], ["Tea with the pastor"])

    def test_deleted_never_returned(self):
        mid = self.store.add("Likes tea")
        self.store.remove(mid)
        self.assertEqual(self.store.recall("tea"), [])
        self.assertEqual(self.store.recall(""), [])

    def test_newer_before_older(self):
        self.store.add("My daughter lives in Raleigh")
        self.store.add("My daughter moved to Durham")
        got = self.store.recall("where does my daughter live")
        self.assertEqual([m["text"] for m in got], ["My daughter moved to Durham", "My daughter lives in Raleigh"])

    def test_result_keys(self):
        self.store.add("Likes tea")
        self.assertEqual(set(self.store.recall("tea")[0]), {"id", "date", "kind", "text"})
        self.assertEqual(set(self.store.recall("")[0]), {"id", "date", "kind", "text"})


class TestForget(Case):
    def test_bare_removes_newest_only_if_recent(self):
        self.store.add("Older fact")
        mid = self.store.add("Newest fact")
        self.assertEqual(self.store.forget(""), ["Newest fact"])
        self.assertEqual(self.store.count(), 1)
        self.assertTrue(rows(f"SELECT deleted_at FROM memories WHERE id={mid}")[0]["deleted_at"])

    def test_old_newest_not_removed(self):
        mid = self.store.add("Newest fact")
        self.age(mid, 2)
        self.assertEqual(self.store.forget(""), [])
        self.assertEqual(self.store.count(), 1)

    def test_about_no_synonyms_and_soft(self):
        did = self.store.add("My daughter Ann lives in Raleigh")
        self.assertEqual(self.store.forget("kids"), [])
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.store.forget("daughter Ann"), ["My daughter Ann lives in Raleigh"])
        self.assertEqual(self.store.count(), 0)
        self.assertTrue(rows(f"SELECT deleted_at FROM memories WHERE id={did}")[0]["deleted_at"])

    def test_that_and_it_via_memory_tool_are_bare(self):
        memory = server.mary_memory()
        self.store.add("Fresh fact")
        got = mary.memory_tool(memory, "forget_memory", {"about": "that"})
        self.assertEqual(got["response"]["forgotten"], ["Fresh fact"])
        self.store.add("Another fresh fact")
        got = mary.memory_tool(memory, "forget_memory", {"about": "It."})
        self.assertEqual(got["response"]["forgotten"], ["Another fresh fact"])

    def test_offer_waiting_bare_removes_nothing(self):
        memory = server.mary_memory()
        self.store.add("Fresh fact")
        for about in ({}, {"about": ""}, {"about": "that"}):
            got = mary.memory_tool(memory, "forget_memory", about, offer_waiting=True)
            self.assertEqual(got["response"]["forgotten"], [])
        self.assertEqual(self.store.count(), 1)


class TestOfflinePhrases(Case):
    def test_fires(self):
        memory = server.mary_memory()
        self.store.add("Likes tea")
        self.assertIn("Likes tea", mary.offline_memory(memory, "what do you remember about me"))
        self.assertEqual(mary.offline_memory(memory, "Mary, forget that"), mary.FORGOT_TEXT)
        self.store.add("Son's job is at the mill")
        self.assertEqual(mary.offline_memory(memory, "please forget about my son's job"), mary.FORGOT_TEXT)
        self.assertEqual(self.store.count(), 0)

    def test_does_not_fire(self):
        memory = server.mary_memory()
        self.store.add("Likes tea")
        for text in ("I forget about my pills", "don't forget that", "forget it"):
            self.assertEqual(mary.offline_memory(memory, text), "", text)
        self.assertEqual(self.store.count(), 1)


class Fake:
    """mary._gemini_stream stand-in: one list of chunks per request, in order."""

    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.bodies = []

    def __call__(self, body, api_key, model="", deadline_s=None):
        self.bodies.append(body)
        return iter(self.rounds.pop(0) if self.rounds else [])


class TestNormalTalk(Case):
    def setUp(self):
        super().setUp()
        self._real = mary._gemini_stream
        self.addCleanup(setattr, mary, "_gemini_stream", self._real)

    def test_recall_call_answered(self):
        self.store.add("My daughter Ann lives in Raleigh")
        call = {"functionCall": {"name": "recall", "args": {"words": "daughter"}}}
        mary._gemini_stream = fake = Fake([mary.ToolCall(call)], ["Her name is Ann."])
        out = mary.reply("Where does my daughter live?", server.mary_memory(), "k")
        self.assertEqual(len(fake.bodies), 2)
        names = [d["name"] for d in fake.bodies[0]["tools"][0]["functionDeclarations"]]
        for want in mary.MEMORY_TOOL_NAMES:
            self.assertIn(want, names)
        part = fake.bodies[1]["contents"][-1]["parts"][0]["functionResponse"]
        self.assertEqual(part["name"], "recall")
        self.assertEqual(part["response"]["memories"][0]["text"], "My daughter Ann lives in Raleigh")
        self.assertIn("Ann", out["text"])

    def test_emergency_no_tools_no_run(self):
        self.assertTrue(mary.is_emergency(EMERGENCY))
        self.store.add("Likes tea")
        call = {"functionCall": {"name": "forget_memory", "args": {"about": "tea"}}}
        mary._gemini_stream = fake = Fake([mary.ToolCall(call)], ["I'm here."])
        mary.reply(EMERGENCY, server.mary_memory(), "k")
        self.assertNotIn("tools", fake.bodies[0])
        self.assertEqual(len(fake.bodies), 1)
        self.assertEqual([m["text"] for m in self.store.active()], ["Likes tea"])


class TestLiveRoute(Case):
    def call(self, name, args, heard=None):
        body = {"name": name, "args": args}
        if heard is not None:
            body["heard"] = heard
        return helpers.api("POST", "/api/mary/skills/call", body)[1]

    def test_recall_emergency(self):
        self.store.add("Likes tea")
        got = self.call("recall", {"words": "tea"}, heard=EMERGENCY)
        self.assertTrue(got.get("emergency"))
        self.assertNotIn("Likes tea", json.dumps(got))

    def test_forget_emergency(self):
        self.store.add("Likes tea")
        got = self.call("forget_memory", {"about": "tea"}, heard=EMERGENCY)
        self.assertTrue(got.get("emergency"))
        self.assertEqual(self.store.count(), 1)

    def test_recall_plain(self):
        self.store.add("Likes tea")
        got = self.call("recall", {"words": "tea"}, heard="what do I like")
        self.assertEqual(got["response"]["memories"][0]["text"], "Likes tea")

    def test_remember_fact_said(self):
        got = self.call("remember_fact", {"fact": "Likes tea."}, heard="please remember that I like tea")
        self.assertTrue(got["response"]["ok"])
        found = rows("SELECT * FROM memories")
        self.assertEqual([(r["text"], r["source"]) for r in found], [("Likes tea.", "said")])


class TestRoutes(Case):
    def test_list_and_delete(self):
        a = self.store.add("Likes tea")
        b = self.store.add("Has a dog")
        status, got, _ = helpers.api("GET", "/api/mary/memories")
        self.assertEqual(status, 200)
        self.assertEqual(got["count"], 2)
        self.assertEqual({m["id"] for m in got["memories"]}, {a, b})
        self.assertEqual(set(got["memories"][0]), {"id", "date", "kind", "text"})
        self.assertEqual(helpers.api("DELETE", f"/api/mary/memories/{a}")[0], 200)
        self.assertEqual(self.store.count(), 1)
        self.assertTrue(rows(f"SELECT deleted_at FROM memories WHERE id={a}")[0]["deleted_at"])

    def test_unknown_id_404(self):
        self.assertEqual(helpers.api("DELETE", "/api/mary/memories/99999")[0], 404)

    def test_delete_without_header_refused(self):
        a = self.store.add("Likes tea")
        status, _, _ = helpers.api("DELETE", f"/api/mary/memories/{a}", tracker=False)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.store.count(), 1)

    def test_key_never_leaks(self):
        helpers.api("PUT", "/api/settings", {"gemini_key": KEY})
        self.assertEqual(rows("SELECT value FROM settings WHERE key='gemini_key'")[0]["value"], KEY)
        self.store.add("Likes tea")
        _, listed, _ = helpers.api("GET", "/api/mary/memories")
        _, called, _ = helpers.api("POST", "/api/mary/skills/call", {"name": "recall", "args": {"words": "tea"}})
        self.assertNotIn(KEY, json.dumps(listed))
        self.assertNotIn(KEY, json.dumps(called))
        self.assertNotIn(KEY, mary.system_text(server.mary_memory()))


if __name__ == "__main__":
    unittest.main()
