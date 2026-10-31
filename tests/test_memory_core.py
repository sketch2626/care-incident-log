from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)

"""M9c: Mary's long memory (memory_core.py): the table and move, the store, the core sent every turn, recall, forget,
the offline phrases, Normal talk with a fake Gemini, Live's tool route and the page routes. No network."""
import json
import os
import sqlite3
import unittest
import uuid
from contextlib import closing
from pathlib import Path

import mary
import memory_core
import server

KEY = "AIzaSyTESTKEY-not-a-real-key-123"
EMERGENCY = "I can't breathe"


def store():
    return server.memory_store()


def rows(sql="SELECT * FROM memories ORDER BY id"):
    """Her memories, read from memories.db (the settings are in the incident log: see settings())."""
    with closing(server.connect_memories()) as conn:
        return [dict(r) for r in conn.execute(sql)]


def settings(key):
    return [r["value"] for r in helpers.db_rows("SELECT value FROM settings WHERE key=?", (key,))]


def migrate(path, target):
    with closing(server.connect()) as conn, conn:
        return memory_core.migrate_json(path, target, conn)


class Case(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()
        self.file = Path(server.DATA) / "mary" / "memory.json"
        self.file.unlink(missing_ok=True)
        self.store = store()
        self.addCleanup(self.file.unlink, missing_ok=True)

    def age(self, memory_id, days):
        from datetime import datetime, timedelta
        old = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with closing(server.connect_memories()) as conn:
            conn.execute("UPDATE memories SET created_at = ? WHERE id = ?", (old, memory_id))
            conn.commit()


class TestTableAndMove(Case):
    def test_init_creates_table(self):
        self.assertTrue(rows("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"))
        self.assertFalse(helpers.db_rows("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"))

    def test_move_once_in_order_file_loses_facts_only(self):
        src = Path(helpers.TMP) / "old-memory.json"
        recent = [{"role": "user", "text": "Hello", "at": "2026-10-01T10:00:00"}]
        src.write_text(json.dumps({"name": "Ruth", "facts": ["First fact", "Second fact", "Third fact"],
                                   "recent": recent}), encoding="utf-8")
        self.assertEqual(migrate(src, self.store), 3)
        self.assertEqual([m["text"] for m in reversed(self.store.active())], ["First fact", "Second fact", "Third fact"])
        # migrate_json itself leaves the file alone (its docstring: "The server strips the facts"); init_db does that,
        # see TestTrulyForget.test_old_facts_stripped_by_init_db.
        kept = json.loads(src.read_text(encoding="utf-8"))
        self.assertEqual(kept["name"], "Ruth")
        self.assertEqual([t["text"] for t in kept["recent"]], ["Hello"])
        self.assertEqual(settings("memories_moved"), ["1"])
        self.store.remove(self.store.active()[-1]["id"])
        self.assertEqual(migrate(src, self.store), 0)
        self.assertEqual(self.store.count(), 2)
        self.assertEqual(len(json.loads(src.read_text(encoding="utf-8"))["facts"]), 3)

    def test_bad_or_missing_json_does_not_raise(self):
        bad = Path(helpers.TMP) / "bad-memory.json"
        cases = [None, "{not json", "[1, 2]", '{"facts": "nope"}', '{"facts": [1, null, ["x"]]}', ""]
        for content in cases:
            helpers.reset_db()
            if content is None:
                bad.unlink(missing_ok=True)
            else:
                bad.write_text(content, encoding="utf-8")
            self.assertEqual(migrate(bad, self.store), 0, content)
        helpers.reset_db()
        bad.write_text('{"facts": [1, "ok fact", null]}', encoding="utf-8")
        self.assertEqual(migrate(bad, self.store), 1)


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

    def test_real_delete_and_save_again(self):
        mid = self.store.add("Likes tea")
        self.assertTrue(self.store.remove(mid))
        self.assertFalse(self.store.remove(mid))
        self.assertEqual(rows(f"SELECT * FROM memories WHERE id={mid}"), [])
        self.assertNotIn("deleted_at", rows("SELECT * FROM memories LIMIT 1") or [{}])
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
        self.assertEqual(rows(f"SELECT * FROM memories WHERE id={mid}"), [])

    def test_old_newest_not_removed(self):
        mid = self.store.add("Newest fact")
        self.age(mid, 2)
        self.assertEqual(self.store.forget(""), [])
        self.assertEqual(self.store.count(), 1)

    def test_about_no_synonyms_and_real_delete(self):
        did = self.store.add("My daughter Ann lives in Raleigh")
        self.assertEqual(self.store.forget("kids"), [])
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.store.forget("daughter Ann"), ["My daughter Ann lives in Raleigh"])
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(rows(f"SELECT * FROM memories WHERE id={did}"), [])

    def test_that_and_it_via_memory_tool_are_bare(self):
        memory = server.mary_memory()
        self.store.add("Fresh fact")
        got = mary.memory_tool(memory, "forget_memory", {"about": "that"})
        self.assertEqual(got["response"]["forgotten"], 1)
        self.assertNotIn("Fresh fact", json.dumps(got))
        self.assertEqual(self.store.count(), 0)
        self.store.add("Another fresh fact")
        got = mary.memory_tool(memory, "forget_memory", {"about": "It."})
        self.assertEqual(got["response"]["forgotten"], 1)
        self.assertEqual(self.store.count(), 0)

    def test_offer_waiting_bare_removes_nothing(self):
        memory = server.mary_memory()
        self.store.add("Fresh fact")
        for about in ({}, {"about": ""}, {"about": "that"}):
            got = mary.memory_tool(memory, "forget_memory", about, offer_waiting=True)
            self.assertEqual(got["response"]["forgotten"], 0)
        self.assertEqual(self.store.count(), 1)


class TestOfflinePhrases(Case):
    def test_fires(self):
        memory = server.mary_memory()
        self.store.add("Likes tea")
        self.assertIn("Likes tea", mary.offline_memory(memory, "what do you remember about me"))
        self.assertEqual(mary.offline_memory(memory, "Mary, forget that"), mary.FORGOT_TEXT)
        self.store.add("Son's job is at the mill")
        self.assertEqual(self.store.count(), 1)  # "forget that" took Likes tea; the new fact is still here
        self.assertEqual(mary.offline_memory(memory, "please forget about my son's job"),
                         mary.FORGET_ASK_TEXT.format("son's job"))  # asks first
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(memory.pending_forget["about"], "son's job")
        out = mary.reply("yes", memory, "")
        self.assertEqual(out["text"], mary.FORGOT_TEXT)
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
        self.assertEqual(set(got["memories"][0]), {"id", "date", "kind", "text", "saved_date"})  # saved_date: M15a
        self.assertEqual(helpers.api("DELETE", f"/api/mary/memories/{a}")[0], 200)
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(rows(f"SELECT * FROM memories WHERE id={a}"), [])

    def test_unknown_id_404(self):
        self.assertEqual(helpers.api("DELETE", "/api/mary/memories/99999")[0], 404)

    def test_delete_without_header_refused(self):
        a = self.store.add("Likes tea")
        status, _, _ = helpers.api("DELETE", f"/api/mary/memories/{a}", tracker=False)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.store.count(), 1)

    def test_key_never_leaks(self):
        helpers.api("PUT", "/api/settings", {"gemini_key": KEY})
        self.assertEqual(server.SECRETS.get("gemini_key"), KEY)  # M15d: kept in the store
        self.assertEqual(settings("gemini_key"), [])  # and never in the table
        self.store.add("Likes tea")
        _, listed, _ = helpers.api("GET", "/api/mary/memories")
        _, called, _ = helpers.api("POST", "/api/mary/skills/call", {"name": "recall", "args": {"words": "tea"}})
        self.assertNotIn(KEY, json.dumps(listed))
        self.assertNotIn(KEY, json.dumps(called))
        self.assertNotIn(KEY, mary.system_text(server.mary_memory()))


def walk_hits(marker):
    """Every file under the data folder whose raw bytes hold marker, as ASCII or as UTF-16LE. Relative paths."""
    needles = (marker.encode("ascii"), marker.encode("utf-16-le"))
    found = []
    for root, _, files in os.walk(server.DATA):
        for name in files:
            path = Path(root) / name
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if any(n in data for n in needles):
                found.append(str(path.relative_to(server.DATA)).replace("\\", "/"))
    return sorted(found)


class TestTrulyForget(Case):
    """After a forget the words are nowhere in the data folder: not in memories.db, its backup, memory.json or the
    incident log's backups."""

    def setUp(self):
        super().setUp()
        self.marker = "Zeb" + uuid.uuid4().hex[:8]
        self.addCleanup(server.MEMORIES_BACKUP.unlink, missing_ok=True)

    def seed(self, other_first=True):
        """The marker in a memory, in memory.json's talk history, and (after this) in the memories backup."""
        if other_first:
            self.store.add("Likes strong coffee")
        self.mid = self.store.add(f"Has a cat named {self.marker}")
        memory = server.mary_memory()
        memory.name = "Ruth"
        memory.add_turn("user", f"My cat {self.marker} is old")
        memory.add_turn("model", f"{self.marker} sounds dear to you.")
        memory.save()
        server.backup_memories(fresh=True)
        server.backup_db()
        hits = walk_hits(self.marker)  # proves the walk works
        for want in ("mary/memories.db", "mary/memories_backup.db", "mary/memory.json"):
            self.assertIn(want, hits)
        self.assertEqual([h for h in hits if h.startswith("backups/")], [])  # incident backups never had it
        return server.mary_memory()

    def assertNowhere(self):
        self.assertEqual(walk_hits(self.marker), [])
        self.assertTrue(server.MEMORIES_BACKUP.exists())  # the rolling copy was rewritten, not just dropped

    def test_tool_forget_confirmed(self):
        memory = self.seed()
        first = mary.memory_tool(memory, "forget_memory", {"about": "cat"})
        self.assertTrue(first["response"]["needs_yes"])
        self.assertIn(self.marker, json.dumps(rows()))  # nothing deleted by the first call
        got = mary.memory_tool(memory, "forget_memory", {"about": "cat", "confirmed": True})
        self.assertEqual(got["response"]["forgotten"], 1)
        memory.save()
        self.assertNowhere()

    def test_bare_forget_within_the_hour(self):
        memory = self.seed()
        got = mary.memory_tool(memory, "forget_memory", {"about": ""})
        self.assertEqual(got["response"]["forgotten"], 1)
        memory.save()
        self.assertNowhere()
        self.assertEqual([m["text"] for m in self.store.active()], ["Likes strong coffee"])

    def test_delete_route(self):
        self.seed()
        self.assertEqual(helpers.api("DELETE", f"/api/mary/memories/{self.mid}")[0], 200)
        self.assertNowhere()

    def test_live_route(self):
        self.seed()
        _, first, _ = helpers.api("POST", "/api/mary/skills/call", {"name": "forget_memory", "args": {"about": "cat"}})
        self.assertTrue(first["response"]["needs_yes"])
        self.assertIn(self.marker, json.dumps(rows()))
        _, got, _ = helpers.api("POST", "/api/mary/skills/call",
                                {"name": "forget_memory", "args": {"about": "cat", "confirmed": True}})
        self.assertEqual(got["response"]["forgotten"], 1)
        self.assertNotIn(self.marker, json.dumps(got))
        self.assertNowhere()

    def test_offline_ask_then_yes(self):
        memory = self.seed()
        asked = mary.reply("forget about my cat", memory, "")
        self.assertIn("forget everything about your cat", asked["text"])
        self.assertIn(self.marker, json.dumps(rows()))
        done = mary.reply("yes", memory, "")
        self.assertEqual(done["text"], mary.FORGOT_TEXT)
        self.assertNowhere()

    def test_split_from_an_older_install(self):
        helpers.api("POST", "/api/incidents", helpers.incident(description="Tray never came."))
        server.backup_db()
        old = Path(server.BACKUPS) / "incidents_2020-01-01.db"
        with closing(server.connect()) as conn, conn:
            conn.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, "
                         "kind TEXT NOT NULL DEFAULT 'other', text TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'talk', "
                         "deleted_at TEXT)")
            conn.execute("INSERT INTO memories (created_at, text) VALUES ('2026-10-01T10:00:00', 'Likes pie')")
            conn.execute("INSERT INTO memories (created_at, text, deleted_at) VALUES ('2026-10-01T10:00:00', ?, "
                         "'2026-10-02T10:00:00')", (f"Has a cat named {self.marker}",))
            conn.execute("DELETE FROM settings WHERE key = 'memories_split'")
        old.unlink(missing_ok=True)
        with closing(server.connect()) as src, closing(sqlite3.connect(old)) as dst:
            src.backup(dst)
        self.assertIn(f"backups/{old.name}", walk_hits(self.marker))  # the old backup really holds it
        self.assertIn("incidents.db", walk_hits(self.marker))
        server.init_db()
        self.assertEqual([m["text"] for m in self.store.active()], ["Likes pie"])
        self.assertEqual(walk_hits(self.marker), [])
        self.assertEqual(settings("memories_split"), ["1"])
        for path in [Path(server.DB_PATH), old]:
            with closing(sqlite3.connect(path)) as conn:
                self.assertEqual(conn.execute("SELECT description FROM incidents").fetchall(),
                                 [("Tray never came.",)], path.name)
                self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='memories'").fetchone())
        old.unlink()

    def test_old_facts_stripped_by_init_db(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps({"name": "Ruth", "facts": [f"Has a cat named {self.marker}"],
                                         "recent": [{"role": "user", "text": "Hello", "at": "2026-10-01T10:00:00"}]}),
                             encoding="utf-8")
        with closing(server.connect()) as conn, conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('memories_moved', '1')")
        self.assertEqual(walk_hits(self.marker), ["mary/memory.json"])
        server.init_db()
        self.assertEqual(walk_hits(self.marker), [])
        kept = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual((kept["name"], kept["facts"], kept["recent"][0]["text"]), ("Ruth", [], "Hello"))
        self.assertEqual(self.store.count(), 0)

    def test_incident_stays_after_forget(self):
        memory = self.seed()
        _, made, _ = helpers.api("POST", "/api/incidents", helpers.incident(description=f"{self.marker} was ignored"))
        iid = made["id"]
        mary.memory_tool(memory, "forget_memory", {"about": "cat"})
        mary.memory_tool(memory, "forget_memory", {"about": "cat", "confirmed": True})
        memory.save()
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(walk_hits(self.marker), ["incidents.db"])  # evidence is kept, nothing else
        self.assertIn(self.marker, helpers.db_rows("SELECT description FROM incidents WHERE id=?", (iid,))[0]["description"])
        self.assertEqual(helpers.api("DELETE", f"/api/incidents/{iid}")[0], 200)  # soft delete still works
        row = helpers.db_rows("SELECT deleted_at FROM incidents WHERE id=?", (iid,))
        self.assertEqual(len(row), 1)
        self.assertTrue(row[0]["deleted_at"])


class TestForgetRules(Case):
    def setUp(self):
        super().setUp()
        self.memory = server.mary_memory()
        self._real = mary._gemini_stream
        self.addCleanup(setattr, mary, "_gemini_stream", self._real)

    def tool(self, about, **extra):
        return mary.memory_tool(self.memory, "forget_memory", {"about": about, **extra})

    def texts(self):
        return {m["text"] for m in self.store.active()}

    def test_two_step_confirmation(self):
        self.store.add("Has a son named Mike")
        self.store.add("Likes tea")
        got = self.tool("my son")
        self.assertTrue(got["response"]["needs_yes"])
        self.assertEqual(got["response"]["count"], 1)
        self.assertEqual(self.store.count(), 2)
        # confirmed with nothing waiting (a new talk) deletes nothing and asks instead
        fresh = server.mary_memory()
        got = mary.memory_tool(fresh, "forget_memory", {"about": "my son", "confirmed": True})
        self.assertTrue(got["response"].get("needs_yes"))
        self.assertEqual(self.store.count(), 2)
        # confirmed about something other than what was asked deletes nothing
        self.tool("tea", confirmed=True)
        self.assertEqual(self.store.count(), 2)
        self.tool("my son")
        got = self.tool("my son", confirmed=True)
        self.assertEqual(got["response"]["forgotten"], 1)
        self.assertEqual(self.texts(), {"Likes tea"})

    def test_normal_talk_drops_unanswered_forget(self):
        self.store.add("Has a son named Mike")
        self.tool("my son")
        self.assertIsNotNone(self.memory.pending_forget)
        mary._gemini_stream = Fake(["Sure, a joke."], ["All right."])
        mary.reply("Tell me a joke", self.memory, "k")
        self.assertIsNone(self.memory.pending_forget)
        mary.reply("yes", self.memory, "k")  # a late yes can't be taken for the old question
        self.assertEqual(self.store.count(), 1)

    def test_no_clears_pending(self):
        self.store.add("Has a son named Mike")
        self.tool("my son")
        mary._gemini_stream = Fake(["Okay, I'll keep it."])
        mary.reply("no", self.memory, "k")
        self.assertIsNone(self.memory.pending_forget)
        self.assertEqual(self.store.count(), 1)

    def test_yes_in_normal_talk_deletes(self):
        self.store.add("Has a son named Mike")
        self.tool("my son")
        mary._gemini_stream = Fake(["unused"])
        out = mary.reply("yes", self.memory, "k")
        self.assertEqual(out["text"], mary.FORGOT_TEXT)
        self.assertEqual(self.store.count(), 0)

    def test_emergency_never_forgets(self):
        self.store.add("Has a son named Mike")
        self.tool("my son")
        mary._gemini_stream = Fake(["I'm here."])
        mary.reply(EMERGENCY + ", yes forget it", self.memory, "k")
        self.assertEqual(self.store.count(), 1)

    def test_son_takes_the_named_son_only(self):
        for t in ("Has a son named Mike", "Mike likes fishing", "Mike lives in Raleigh",
                  "Raleigh has a lovely park", "Likes tea"):
            self.store.add(t)
        self.assertEqual(set(self.store.forget("my son")),
                         {"Has a son named Mike", "Mike likes fishing", "Mike lives in Raleigh"})
        self.assertEqual(self.texts(), {"Raleigh has a lovely park", "Likes tea"})  # Raleigh doesn't spread

    def test_sons_job_takes_only_both_words(self):
        for t in ("Has a son named Mike", "Mike likes fishing", "Son's job is at the mill", "Mike's job is hard"):
            self.store.add(t)
        self.assertEqual(self.store.forget("my son's job"), ["Son's job is at the mill"])
        self.assertEqual(self.texts(), {"Has a son named Mike", "Mike likes fishing", "Mike's job is hard"})

    def test_everything(self):
        for t in ("Has a son named Mike", "Likes tea", "Has a dog"):
            self.store.add(t)
        self.memory.add_turn("user", "Anything at all")
        self.memory.add_turn("model", "Of course.")
        got = self.tool("everything")
        self.assertEqual((got["response"]["needs_yes"], got["response"]["count"]), (True, 3))
        self.assertEqual(self.store.count(), 3)
        got = self.tool("everything", confirmed=True)
        self.assertEqual(got["response"]["forgotten"], 3)
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(self.memory.recent, [])

    def test_bare_forget_that_on_old_memory(self):
        mid = self.store.add("Has a dog")
        self.age(mid, 2)
        got = self.tool("that")
        self.assertEqual(got["response"]["forgotten"], 0)
        self.assertEqual(self.store.count(), 1)

    def test_response_never_holds_the_text(self):
        self.store.add("Has a son named Zorbaxx")
        for args in ({"about": "my son"}, {"about": "my son", "confirmed": True}, {"about": "that"}):
            got = mary.memory_tool(self.memory, "forget_memory", args)
            self.assertNotIn("Zorbaxx", json.dumps(got))


if __name__ == "__main__":
    unittest.main()


class TestForgetName(Case):
    """M9c: "forget my name" really deletes the name, the memories and talk turns that hold it, and she stops asking."""

    def setUp(self):
        super().setUp()
        self.marker = "Zeb" + uuid.uuid4().hex[:8].translate(str.maketrans("0123456789", "ghijklmnop"))
        self.addCleanup(server.MEMORIES_BACKUP.unlink, missing_ok=True)
        self._real = mary._gemini_stream
        self.addCleanup(setattr, mary, "_gemini_stream", self._real)

    def seed(self):
        self.store.add(f"Likes to be called {self.marker}")
        self.store.add("Likes strong coffee")
        memory = server.mary_memory()
        memory.name = self.marker
        memory.add_turn("user", f"Everyone calls me {self.marker}")
        memory.add_turn("model", f"Nice to meet you, {self.marker}.")
        memory.add_turn("user", "The weather is nice today.")
        memory.add_turn("model", "It sure is.")
        memory.save()
        server.backup_memories(fresh=True)
        hits = walk_hits(self.marker)
        for want in ("mary/memories.db", "mary/memories_backup.db", "mary/memory.json"):
            self.assertIn(want, hits)
        return server.mary_memory()

    def assertForgotten(self, got=None):
        memory = server.mary_memory()
        self.assertEqual(memory.name, "")
        self.assertTrue(memory.name_forgotten)
        self.assertEqual([m["text"] for m in self.store.active()], ["Likes strong coffee"])
        self.assertEqual([t["text"] for t in memory.recent], ["The weather is nice today.", "It sure is."])
        self.assertEqual(walk_hits(self.marker), [])
        if got is not None:
            self.assertNotIn(self.marker, json.dumps(got))

    def test_normal_tool(self):
        memory = self.seed()
        call = {"functionCall": {"name": "forget_name", "args": {}}}
        mary._gemini_stream = fake = Fake([mary.ToolCall(call)], ["All right."])
        out = mary.reply("forget my name", memory, "k")
        part = fake.bodies[1]["contents"][-1]["parts"][0]["functionResponse"]
        self.assertEqual(part["name"], "forget_name")
        self.assertNotIn(self.marker, json.dumps(part))
        self.assertForgotten(out)

    def test_live_route(self):
        self.seed()
        _, got, _ = helpers.api("POST", "/api/mary/skills/call", {"name": "forget_name", "args": {}})
        self.assertForgotten(got)

    def test_live_emergency_changes_nothing(self):
        self.seed()
        _, got, _ = helpers.api("POST", "/api/mary/skills/call",
                                {"name": "forget_name", "args": {}, "heard": EMERGENCY})
        self.assertTrue(got.get("emergency"))
        memory = server.mary_memory()
        self.assertEqual(memory.name, self.marker)
        self.assertFalse(memory.name_forgotten)
        self.assertEqual(self.store.count(), 2)
        self.assertEqual(len(memory.recent), 4)

    def test_offline_phrases_clear(self):
        for phrase in ("forget my name", "don't call me that anymore", f"stop calling me {self.marker}"):
            with self.subTest(phrase):
                helpers.reset_db()
                memory = self.seed()
                out = mary.reply(phrase, memory, "")
                self.assertEqual(memory.name, "")
                self.assertTrue(memory.name_forgotten)
                self.assertNotIn(self.marker, json.dumps(out))
                memory.save()
                self.assertEqual(walk_hits(self.marker), [])

    def test_offline_lookalikes_change_nothing(self):
        for phrase in ("I forget my name sometimes", "don't call me late", "stop calling me honey"):
            with self.subTest(phrase):
                memory = self.seed()
                mary.reply(phrase, memory, "")
                self.assertEqual(memory.name, self.marker)
                self.assertFalse(memory.name_forgotten)
                self.assertEqual(self.store.count(), 2)

    def test_after_forgetting(self):
        memory = self.seed()
        before = mary.system_text(memory)
        self.assertIn("what they'd like to be called", mary.system_text(self.fresh_memory()))
        self.assertIn(self.marker, before)
        mary.reply("forget my name", memory, "")
        memory.save()
        text = mary.system_text(memory)
        self.assertNotIn(self.marker, text)
        self.assertNotIn("what they'd like to be called", text)
        self.assertIn(mary.NAME_FORGOTTEN_SYSTEM, text)
        _, status, _ = helpers.api("GET", "/api/mary/status")
        self.assertEqual(status["name"], "")
        self.assertIs(status["name_forgotten"], True)
        self.assertIs(json.loads(self.file.read_text(encoding="utf-8"))["name_forgotten"], True)
        again = server.mary_memory()
        self.assertEqual((again.name, again.name_forgotten), ("", True))
        self.assertIn(mary.NAME_FORGOTTEN_SYSTEM, mary.system_text(again))

    def fresh_memory(self):
        helpers.reset_db()
        self.file.unlink(missing_ok=True)
        return server.mary_memory()

    def forgotten_memory(self):
        memory = self.seed()
        mary.reply("forget my name", memory, "")
        memory.save()
        self.assertTrue(server.mary_memory().name_forgotten)
        return server.mary_memory()

    def test_offering_a_name_clears_the_flag(self):
        memory = self.forgotten_memory()
        mary.reply("my name is Ann", memory, "")
        self.assertEqual((memory.name, memory.name_forgotten), ("Ann", False))
        self.fresh_memory()
        self.forgotten_memory()
        helpers.api("POST", "/api/mary/skills/call", {"name": "set_their_name", "args": {"name": "Ann"}})
        memory = server.mary_memory()
        self.assertEqual((memory.name, memory.name_forgotten), ("Ann", False))
        self.fresh_memory()
        self.forgotten_memory()
        helpers.api("POST", "/api/mary/hello", {"text": "Ann"})
        memory = server.mary_memory()
        self.assertEqual((memory.name, memory.name_forgotten), ("Ann", False))

    def test_learn_name_refusals(self):
        memory = server.mary_memory()
        mary.learn_name(memory, "stop calling me Bob")
        self.assertEqual(memory.name, "")
        mary.learn_name(memory, "don't call me that, call me Andy")
        self.assertEqual(memory.name, "Andy")

    def test_name_tag_in_the_forgetting_reply_ignored(self):
        memory = self.seed()
        call = {"functionCall": {"name": "forget_name", "args": {}}}
        mary._gemini_stream = Fake([mary.ToolCall(call)], [f"All right. [name: {self.marker}]"])
        mary.reply("forget my name", memory, "k")
        self.assertEqual((memory.name, memory.name_forgotten), ("", True))
        memory.save()
        self.assertEqual(walk_hits(self.marker), [])
        mary._gemini_stream = Fake(["Nice to meet you. [name: Ann]"])
        mary.reply("hello there", memory, "k")
        self.assertEqual((memory.name, memory.name_forgotten), ("Ann", False))

    def test_resident_name_setting_untouched(self):
        helpers.api("PUT", "/api/settings", {"resident_name": "Ruth Smith"})
        before = settings("resident_name")
        self.assertEqual(before, ["Ruth Smith"])
        memory = self.seed()
        mary.reply("forget my name", memory, "")
        self.assertEqual(settings("resident_name"), before)

    def test_offline_with_a_note_offer_waiting(self):
        memory = self.seed()
        memory.pending_offer = mary._offer(mary._guess("The tray never came"))
        mary.reply("don't call me that", memory, "")
        self.assertEqual(memory.name, "")
        self.assertTrue(memory.name_forgotten)
