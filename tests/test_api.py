"""Server API tests. Scratch data only (see helpers.py)."""
import shutil
import sqlite3
import threading
import time
import unittest
from contextlib import closing
from datetime import datetime
from unittest import mock

from tests import helpers
from tests.helpers import api, db_rows, incident, make_andyflow_db, reset_db


class IncidentTests(unittest.TestCase):
    def setUp(self):
        reset_db()

    def add(self, **overrides):
        status, body, _ = api("POST", "/api/incidents", incident(**overrides))
        self.assertEqual(status, 201, body)
        return body["id"]

    def test_create_returns_201_and_id(self):
        status, body, _ = api("POST", "/api/incidents", incident())
        self.assertEqual(status, 201)
        self.assertIsInstance(body["id"], int)

    def test_list_includes_summary(self):
        new_id = self.add()
        status, rows, _ = api("GET", "/api/incidents")
        self.assertEqual(status, 200)
        self.assertEqual([r["id"] for r in rows], [new_id])
        self.assertTrue(rows[0]["summary"])
        self.assertEqual(rows[0]["category"], "meal")

    def test_from_to_filtering(self):
        self.add(occurred_date="2026-10-01")
        mid = self.add(occurred_date="2026-10-10")
        self.add(occurred_date="2026-10-20")
        _, rows, _ = api("GET", "/api/incidents?from=2026-10-05&to=2026-10-15")
        self.assertEqual([r["id"] for r in rows], [mid])
        _, rows, _ = api("GET", "/api/incidents?from=2026-10-10")
        self.assertEqual(len(rows), 2)
        _, rows, _ = api("GET", "/api/incidents?to=2026-10-01")
        self.assertEqual(len(rows), 1)

    def test_bad_date_rejected(self):
        status, body, _ = api("POST", "/api/incidents", incident(occurred_date="10/20/2026"))
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_unknown_category_rejected(self):
        status, body, _ = api("POST", "/api/incidents", incident(category="made_up"))
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_empty_description_rejected(self):
        status, body, _ = api("POST", "/api/incidents", incident(description="   "))
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        self.assertEqual(db_rows("SELECT id FROM incidents"), [])

    def test_update_changes_fields(self):
        new_id = self.add()
        status, _, _ = api("PUT", f"/api/incidents/{new_id}",
                           incident(description="Changed words.", category="call_light", severity="dangerous"))
        self.assertEqual(status, 200)
        _, rows, _ = api("GET", "/api/incidents")
        self.assertEqual(rows[0]["description"], "Changed words.")
        self.assertEqual(rows[0]["category"], "call_light")
        self.assertEqual(rows[0]["severity"], "dangerous")

    def test_delete_is_soft(self):
        new_id = self.add()
        status, _, _ = api("DELETE", f"/api/incidents/{new_id}")
        self.assertEqual(status, 200)
        _, rows, _ = api("GET", "/api/incidents")
        self.assertEqual(rows, [])
        stored = db_rows("SELECT id, deleted_at FROM incidents WHERE id = ?", (new_id,))
        self.assertEqual(len(stored), 1)
        self.assertTrue(stored[0]["deleted_at"])


class SecurityTests(unittest.TestCase):
    def setUp(self):
        reset_db()

    def test_mutations_need_tracker_header(self):
        new_id = api("POST", "/api/incidents", incident())[1]["id"]
        status, _, _ = api("POST", "/api/incidents", incident(), tracker=False)
        self.assertEqual(status, 403)
        status, _, _ = api("PUT", f"/api/incidents/{new_id}", incident(description="Hacked."), tracker=False)
        self.assertEqual(status, 403)
        status, _, _ = api("DELETE", f"/api/incidents/{new_id}", tracker=False)
        self.assertEqual(status, 403)
        status, _, _ = api("PUT", "/api/settings", {"resident_name": "Hacker"}, tracker=False)
        self.assertEqual(status, 403)
        rows = db_rows("SELECT description, deleted_at FROM incidents")
        self.assertEqual(len(rows), 1)  # the extra POST added nothing
        self.assertEqual(rows[0]["description"], incident()["description"])
        self.assertIsNone(rows[0]["deleted_at"])
        self.assertEqual(db_rows("SELECT * FROM settings"), [])

    def test_foreign_host_refused(self):
        status, _, _ = api("GET", "/api/incidents", host="evil.example")
        self.assertEqual(status, 403)
        status, _, _ = api("POST", "/api/incidents", incident(), host="evil.example")
        self.assertEqual(status, 403)
        self.assertEqual(db_rows("SELECT id FROM incidents"), [])

    def test_localhost_host_allowed(self):
        status, _, _ = api("GET", "/api/incidents", host="localhost:8765")
        self.assertEqual(status, 200)


class HardeningTests(unittest.TestCase):
    def setUp(self):
        reset_db()

    def test_csv_cells_cannot_run_as_formulas(self):
        api("POST", "/api/incidents", incident(description='=HYPERLINK("http://x","click")', witnesses="+1+1"))
        status, body, _ = api("GET", "/api/export.csv")
        self.assertEqual(status, 200)
        text = body.decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", text)
        self.assertIn("'+1+1", text)

    def test_pages_cannot_be_framed_by_other_sites(self):
        _, _, headers = api("GET", "/api/settings")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        _, _, headers = api("GET", "/index.html")
        self.assertIn("frame-ancestors 'none'", headers.get("Content-Security-Policy", ""))

    def test_head_checks_the_host_too(self):
        status, _, _ = api("HEAD", "/index.html", host="evil.example")
        self.assertEqual(status, 403)
        status, _, _ = api("HEAD", "/index.html")
        self.assertEqual(status, 200)
        status, _, _ = api("HEAD", "/api/settings")
        self.assertEqual(status, 405)

    def test_mcp_survives_odd_arguments(self):
        import mcp_server
        for args in ([1], {"limit": "abc"}, {"limit": -5}):
            with self.subTest(args=args):
                out = mcp_server.handle({"method": "tools/call", "params": {"name": "list_incidents", "arguments": args}})
                self.assertIn("content", out)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        reset_db()

    def test_get_settings_starts_without_key(self):
        status, body, _ = api("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertFalse(body["gemini_key_set"])
        self.assertNotIn("gemini_key", body)

    def test_put_saves_name_and_hides_key(self):
        status, body, _ = api("PUT", "/api/settings",
                              {"resident_name": "Test Resident", "gemini_key": "fake-key-123"})
        self.assertEqual(status, 200)
        self.assertEqual(body["resident_name"], "Test Resident")
        self.assertTrue(body["gemini_key_set"])
        self.assertNotIn("gemini_key", body)
        _, again, _ = api("GET", "/api/settings")
        self.assertEqual(again["resident_name"], "Test Resident")
        self.assertTrue(again["gemini_key_set"])
        self.assertNotIn("gemini_key", again)
        self.assertNotIn("fake-key-123", str(again))

    def test_blank_key_keeps_saved_key(self):
        api("PUT", "/api/settings", {"gemini_key": "fake-key-123"})
        status, body, _ = api("PUT", "/api/settings", {"gemini_key": "  ", "resident_name": "Pat"})
        self.assertEqual(status, 200)
        self.assertTrue(body["gemini_key_set"])
        self.assertEqual(body["resident_name"], "Pat")
        self.assertEqual(db_rows("SELECT value FROM settings WHERE key = 'gemini_key'")[0]["value"], "fake-key-123")

    def test_unknown_setting_ignored(self):
        _, body, _ = api("PUT", "/api/settings", {"not_a_setting": "x"})
        self.assertNotIn("not_a_setting", body)


class TidyAndMiscTests(unittest.TestCase):
    def setUp(self):
        reset_db()

    def test_tidy_offline_guess(self):
        status, body, _ = api("POST", "/api/tidy",
                              {"text": "Incident: I pressed my call light and nobody came for two hours"})
        self.assertEqual(status, 200)
        self.assertEqual(body["category"], "call_light")
        self.assertEqual(body["wait_minutes"], 120)
        self.assertNotIn("assisted", body)

    def test_tidy_empty_text_rejected(self):
        status, body, _ = api("POST", "/api/tidy", {"text": "   "})
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        status, body, _ = api("POST", "/api/tidy", {})
        self.assertEqual(status, 400)

    def test_listen_unavailable_without_speech(self):
        status, body, _ = api("GET", "/api/listen")
        self.assertEqual(status, 200)
        self.assertIs(body["available"], False)

    def test_unknown_api_path_is_404(self):
        status, body, _ = api("GET", "/api/nope")
        self.assertEqual(status, 404)
        self.assertIn("error", body)


class AndyFlowInboxTests(unittest.TestCase):
    DICTATIONS = [
        (1, "2026-10-20 14:30:00", "Incident: nobody brought my lunch tray", "Notepad"),
        (2, "2026-10-20 15:00:00", "Remind me to call my sister", "Notepad"),
        (3, "2026-10-20 16:00:00", "Incident: this was typed in the tracker itself", "Care Incident Log - Google Chrome"),
    ]
    NOTES = [
        (1, "2026-10-21 09:00:00", "Shower", "They skipped my shower again today", "Incidents"),
        (2, "2026-10-21 10:00:00", "Groceries", "Buy stamps", "Errands"),
    ]

    def setUp(self):
        reset_db()

    def texts(self, body):
        return {(i["kind"], i["source_id"]) for i in body["items"]}

    def test_no_andyflow_db(self):
        status, body, _ = api("GET", "/api/inbox")
        self.assertEqual(status, 200)
        self.assertIs(body["available"], False)
        self.assertEqual(body["items"], [])

    def test_inbox_lists_only_incident_items(self):
        make_andyflow_db(self.DICTATIONS, self.NOTES)
        status, body, _ = api("GET", "/api/inbox")
        self.assertEqual(status, 200)
        self.assertIs(body["available"], True)
        self.assertEqual(self.texts(body), {("dictation", 1), ("note", 1)})
        self.assertTrue(all(i["guess"]["category"] for i in body["items"]))

    def test_import_adds_then_adds_nothing(self):
        make_andyflow_db(self.DICTATIONS, self.NOTES)
        status, body, _ = api("POST", "/api/inbox/import")
        self.assertEqual(status, 200)
        self.assertEqual(body["added"], 2)
        _, rows, _ = api("GET", "/api/incidents")
        self.assertEqual({r["source"] for r in rows}, {"andyflow-dictation", "andyflow-note"})
        self.assertEqual(self.texts(api("GET", "/api/inbox")[1]), set())
        _, again, _ = api("POST", "/api/inbox/import")
        self.assertEqual(again["added"], 0)
        self.assertEqual(len(api("GET", "/api/incidents")[1]), 2)

    def test_dismiss_hides_item(self):
        make_andyflow_db(self.DICTATIONS, self.NOTES)
        status, _, _ = api("POST", "/api/inbox/dismiss", {"kind": "dictation", "source_id": 1})
        self.assertEqual(status, 200)
        self.assertEqual(self.texts(api("GET", "/api/inbox")[1]), {("note", 1)})
        _, body, _ = api("POST", "/api/inbox/import")
        self.assertEqual(body["added"], 1)  # the dismissed one is not imported

    def test_inbox_needs_no_tracker_header_but_import_does(self):
        make_andyflow_db(self.DICTATIONS, self.NOTES)
        self.assertEqual(api("GET", "/api/inbox", tracker=False)[0], 200)
        self.assertEqual(api("POST", "/api/inbox/import", tracker=False)[0], 403)
        self.assertEqual(api("POST", "/api/inbox/dismiss", {"kind": "note", "source_id": 1}, tracker=False)[0], 403)
        self.assertEqual(len(self.texts(api("GET", "/api/inbox")[1])), 2)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        reset_db()

    def post(self, **overrides):
        return api("POST", "/api/incidents", incident(**overrides))

    def test_impossible_dates_rejected(self):
        for bad in ("2026-02-31", "2026-13-45", "2026-00-10", "2026-04-31", "2025-02-29", "0000-01-01"):
            status, body, _ = self.post(occurred_date=bad)
            self.assertEqual(status, 400, bad)
            self.assertIn("date", body["error"])
        self.assertEqual(db_rows("SELECT id FROM incidents"), [])
        self.assertEqual(self.post(occurred_date="2028-02-29")[0], 201)  # a real leap day

    def test_impossible_times_rejected(self):
        for bad in ("99:99", "24:00", "12:60", "7:30"):
            status, body, _ = self.post(occurred_time=bad)
            self.assertEqual(status, 400, bad)
            self.assertIn("time", body["error"])
        self.assertEqual(db_rows("SELECT id FROM incidents"), [])
        for good in ("00:00", "23:59", ""):
            self.assertEqual(self.post(occurred_time=good)[0], 201, good)

    def test_wait_minutes_parsing(self):
        cases = [(30, 30), ("30", 30), ("30.0", 30), (30.0, 30), (30.9, 30), (" 45 ", 45), (0, 0),
                 (100000, 100000), (-5, None), ("-5", None), (100001, None), (10 ** 30, None),
                 (float("inf"), None), ("nan", None), ("abc", None), ("", None), (None, None), (True, None)]
        for sent, expected in cases:
            status, body, _ = self.post(wait_minutes=sent)
            self.assertEqual(status, 201, (sent, body))
            stored = db_rows("SELECT wait_minutes FROM incidents WHERE id = ?", (body["id"],))[0]
            self.assertEqual(stored["wait_minutes"], expected, sent)

    def test_never_came_parsing(self):
        cases = [(True, 1), (1, 1), ("1", 1), ("true", 1), ("TRUE", 1), ("yes", 1),
                 (False, 0), (0, 0), ("0", 0), ("false", 0), ("no", 0), ("", 0), (None, 0)]
        for sent, expected in cases:
            status, body, _ = self.post(never_came=sent)
            self.assertEqual(status, 201, (sent, body))
            stored = db_rows("SELECT never_came FROM incidents WHERE id = ?", (body["id"],))[0]
            self.assertEqual(stored["never_came"], expected, sent)


class MissingEntryTests(unittest.TestCase):
    def setUp(self):
        reset_db()

    def add(self):
        status, body, _ = api("POST", "/api/incidents", incident())
        self.assertEqual(status, 201, body)
        return body["id"]

    def test_put_and_delete_on_missing_id_are_404(self):
        status, body, _ = api("PUT", "/api/incidents/9999", incident())
        self.assertEqual((status, body), (404, {"error": "That entry wasn't found."}))
        status, body, _ = api("DELETE", "/api/incidents/9999")
        self.assertEqual((status, body), (404, {"error": "That entry wasn't found."}))

    def test_put_on_deleted_entry_is_404_and_changes_nothing(self):
        new_id = self.add()
        self.assertEqual(api("DELETE", f"/api/incidents/{new_id}")[0], 200)
        status, body, _ = api("PUT", f"/api/incidents/{new_id}", incident(description="Sneaky edit."))
        self.assertEqual(status, 404, body)
        row = db_rows("SELECT description FROM incidents WHERE id = ?", (new_id,))[0]
        self.assertEqual(row["description"], "Lunch tray never arrived.")

    def test_second_delete_keeps_the_first_deleted_at(self):
        new_id = self.add()
        self.assertEqual(api("DELETE", f"/api/incidents/{new_id}")[0], 200)
        with closing(sqlite3.connect(helpers.server.DB_PATH)) as conn:
            conn.execute("UPDATE incidents SET deleted_at = '2020-01-01 00:00:00' WHERE id = ?", (new_id,))
            conn.commit()
        self.assertEqual(api("DELETE", f"/api/incidents/{new_id}")[0], 404)
        row = db_rows("SELECT deleted_at FROM incidents WHERE id = ?", (new_id,))[0]
        self.assertEqual(row["deleted_at"], "2020-01-01 00:00:00")


class BadBodyTests(unittest.TestCase):
    def setUp(self):
        reset_db()

    def test_dismiss_needs_kind_and_id(self):
        for body in ({}, {"source_id": 1}, {"kind": "note"}, {"kind": "note", "source_id": "abc"}):
            status, resp, _ = api("POST", "/api/inbox/dismiss", body)
            self.assertEqual(status, 400, body)
            self.assertEqual(resp["error"], "That request didn't look right.")
        self.assertEqual(db_rows("SELECT * FROM inbox_seen"), [])

    def test_body_that_is_not_an_object_is_400(self):
        for method, path in (("POST", "/api/inbox/dismiss"), ("POST", "/api/incidents"),
                             ("POST", "/api/tidy"), ("PUT", "/api/settings")):
            status, resp, _ = api(method, path, [1, 2, 3])
            self.assertEqual(status, 400, path)
            self.assertEqual(resp["error"], "That request didn't look right.")

    def test_negative_or_huge_content_length_is_400(self):
        for length in ("-1", str(5 * 1024 * 1024 + 1), "abc"):
            status, resp, _ = api("POST", "/api/inbox/dismiss", headers={"Content-Length": length})
            self.assertEqual(status, 400, length)
            self.assertEqual(resp["error"], "That request didn't look right.")


class AndyFlowRobustnessTests(unittest.TestCase):
    def setUp(self):
        reset_db()

    def keys(self, body):
        return {(i["kind"], i["source_id"]) for i in body["items"]}

    def test_concurrent_imports_add_each_item_once(self):
        make_andyflow_db([(i, f"2026-10-20 1{i}:00:00", f"Incident: nobody answered my call light {i}", "Notepad")
                          for i in range(1, 9)])
        barrier, results = threading.Barrier(4), []

        def go():
            barrier.wait()
            results.append(api("POST", "/api/inbox/import", {}))

        threads = [threading.Thread(target=go) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 4)
        self.assertTrue(all(status == 200 for status, _, _ in results), results)
        self.assertEqual(sum(body["added"] for _, body, _ in results), 8)
        self.assertEqual(len(db_rows("SELECT id FROM incidents")), 8)
        self.assertEqual(len(db_rows("SELECT DISTINCT source_id FROM incidents")), 8)

    def test_null_values_in_andyflow_do_not_break_the_inbox(self):
        make_andyflow_db(
            [(1, "2026-10-20 14:30:00", "Incident: lunch never came", None),
             (2, "2026-10-20 15:00:00", None, "Notepad"),
             (3, None, "Incident: no time on this one", "Notepad")],
            [(1, "2026-10-21 09:00:00", "Incident: dry bed", None, None),
             (2, "2026-10-21 10:00:00", None, "They skipped my shower", "Incidents"),
             (3, "2026-10-21 11:00:00", None, None, None),
             (4, None, "Incident: note with no time", "text", "Incidents")])
        status, body, _ = api("GET", "/api/inbox")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["available"])
        self.assertEqual(self.keys(body), {("dictation", 1), ("note", 1), ("note", 2)})
        self.assertEqual(api("POST", "/api/inbox/import", {})[1]["added"], 3)

    def test_andyflow_path_with_hash_and_percent(self):
        folder = helpers.TMP / "af#1%20x" / "Andyflow"
        self.addCleanup(shutil.rmtree, folder.parent, True)
        with mock.patch.object(helpers.server, "ANDYFLOW_DB", folder / "history.db"):
            make_andyflow_db([(1, "2026-10-20 14:30:00", "Incident: lunch never came", "Notepad")])
            status, body, _ = api("GET", "/api/inbox")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["available"])
        self.assertEqual(self.keys(body), {("dictation", 1)})

    def test_andyflow_file_that_is_not_a_database(self):
        helpers.server.ANDYFLOW_DB.parent.mkdir(parents=True, exist_ok=True)
        helpers.server.ANDYFLOW_DB.write_bytes(b"this is not a database" * 50)
        status, body, _ = api("GET", "/api/inbox")
        self.assertEqual((status, body), (200, {"available": False, "items": []}))


class BackupTests(unittest.TestCase):
    def setUp(self):
        reset_db()
        self.today = helpers.server.BACKUPS / f"incidents_{datetime.now():%Y-%m-%d}.db"
        self.today.unlink(missing_ok=True)
        self.today.with_suffix(".tmp").unlink(missing_ok=True)

    def count_in(self, path):
        with closing(sqlite3.connect(path)) as conn:
            return conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]

    def test_failed_backup_does_not_raise_or_leave_a_file(self):
        class Failing:  # starts writing the copy, then dies
            def backup(self, dst):
                dst.execute("CREATE TABLE partial (x)")
                dst.commit()
                raise sqlite3.OperationalError("disk full")

            def close(self):
                pass

        with mock.patch.object(helpers.server, "connect", Failing):
            helpers.server.backup_db()
        self.assertFalse(self.today.exists())
        self.assertFalse(self.today.with_suffix(".tmp").exists())
        helpers.server.backup_db()  # the next try works
        self.assertEqual(self.count_in(self.today), 0)

    def test_leftover_partial_file_is_replaced(self):
        self.today.with_suffix(".tmp").write_bytes(b"half a backup")
        helpers.server.backup_db()
        self.assertEqual(self.count_in(self.today), 0)
        self.assertFalse(self.today.with_suffix(".tmp").exists())

    def test_unusable_backup_folder_does_not_raise(self):
        not_a_folder = helpers.TMP / "backups-are-a-file"
        not_a_folder.write_bytes(b"x")
        with mock.patch.object(helpers.server, "BACKUPS", not_a_folder):
            helpers.server.backup_db()

    def test_a_save_makes_the_days_backup(self):
        status, body, _ = api("POST", "/api/incidents", incident())
        self.assertEqual(status, 201, body)
        for _ in range(60):  # the backup runs just after the answer is sent
            if self.today.exists():
                break
            time.sleep(0.05)
        self.assertTrue(self.today.exists())
        self.assertEqual(self.count_in(self.today), 1)


class LegacyMigrationTests(unittest.TestCase):
    def make_db(self, path, incidents=0, settings=0):
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript(helpers.server.SCHEMA)
            for i in range(incidents):
                conn.execute("INSERT INTO incidents (occurred_date, category, description, logged_at, updated_at) "
                             "VALUES ('2026-10-01', 'meal', 'x', 'now', 'now')")
            for i in range(settings):
                conn.execute("INSERT INTO settings (key, value) VALUES (?, 'v')", (f"k{i}",))
            conn.commit()

    def test_log_is_empty(self):
        base = helpers.TMP / "migrate-check"
        self.addCleanup(shutil.rmtree, base, True)
        self.make_db(base / "schema_only.db")
        self.make_db(base / "has_incident.db", incidents=1)
        self.make_db(base / "has_setting.db", settings=1)
        (base / "zero_bytes.db").write_bytes(b"")
        (base / "garbage.db").write_bytes(b"this is not a database" * 50)
        empty = helpers.server.log_is_empty
        self.assertTrue(empty(base / "missing.db"))
        self.assertTrue(empty(base / "schema_only.db"))
        self.assertTrue(empty(base / "zero_bytes.db"))
        self.assertFalse(empty(base / "has_incident.db"))
        self.assertFalse(empty(base / "has_setting.db"))
        self.assertFalse(empty(base / "garbage.db"))

    def migrate(self, name, new_settings):
        data, old = helpers.TMP / name / "new", helpers.TMP / name / "old"
        self.addCleanup(shutil.rmtree, helpers.TMP / name, True)
        self.make_db(old / "incidents.db", incidents=2)
        if new_settings is not None:
            self.make_db(data / "incidents.db", settings=new_settings)
        data.mkdir(parents=True, exist_ok=True)
        with mock.patch.multiple(helpers.server, DATA=data, DEFAULT_DATA=data, LEGACY_DATA=old,
                                 DB_PATH=data / "incidents.db", BACKUPS=data / "backups"):
            helpers.server.migrate_legacy_data()
        with closing(sqlite3.connect(data / "incidents.db")) as conn:
            return (conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0],
                    conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0])

    def test_old_log_is_copied_into_a_new_one(self):
        self.assertEqual(self.migrate("mig-fresh", None), (2, 0))

    def test_new_log_with_only_settings_is_not_overwritten(self):
        self.assertEqual(self.migrate("mig-settings", 1), (0, 1))


if __name__ == "__main__":
    unittest.main()
