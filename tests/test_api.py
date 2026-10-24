"""Server API tests. Scratch data only (see helpers.py)."""
import unittest

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


if __name__ == "__main__":
    unittest.main()
