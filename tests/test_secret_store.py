"""M15d: the secret store, and the Gemini key's move out of the settings table. Scratch data and a memory backend only."""
from tests import helpers  # first: scratch folders and an in-memory backend, before anything loads server

import ctypes
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import sys
import unittest
import urllib.request
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest import mock

import secret_store
import server
from secret_store import MemoryBackend, NotAvailable, SecretStore, SecretStoreError, TooLong, UnavailableBackend
from tests import test_skills_core as tsc

KEY = "AIzaSyFAKE-test-key-0123456789abcdefghij"


def blobs_for(backend, store, name):
    prefix = store._target(name)
    return {k: v for k, v in backend.data.items() if k == prefix or k.startswith(prefix + "#")}


class MemoryStoreTest(unittest.TestCase):

    def setUp(self):
        self.backend = MemoryBackend()
        secret_store.set_backend(self.backend)
        self.addCleanup(secret_store.set_backend, helpers.SECRETS)
        self.store = SecretStore(helpers.TMP / "store-a")

    def test_round_trip_delete_and_missing(self):
        self.assertIsNone(self.store.get("thing"))
        self.store.put("thing", "hello")
        self.assertEqual(self.store.get("thing"), "hello")
        self.store.put("thing", "änother — ✓")
        self.assertEqual(self.store.get("thing"), "änother — ✓")
        self.store.delete("thing")
        self.assertIsNone(self.store.get("thing"))
        self.store.delete("thing")  # deleting what isn't there is fine
        self.assertEqual(self.backend.data, {})

    def test_long_values_split_into_parts(self):
        for size in (1, 2, 2553, 2554, 2560, 2561, 5000, 20000):
            value = ("0123456789abcdef" * 2000)[:size]
            self.store.put("big", value)
            self.assertEqual(self.store.get("big"), value, size)
            held = blobs_for(self.backend, self.store, "big")
            self.assertTrue(all(len(b) <= 2560 for b in held.values()), (size, [len(b) for b in held.values()]))
            self.store.delete("big")
            self.assertEqual(blobs_for(self.backend, self.store, "big"), {})

    def test_too_long(self):
        self.store.put("big", "short")
        with self.assertRaises(TooLong):
            self.store.put("big", "x" * 20001)
        self.assertEqual(self.store.get("big"), "short")  # the refused save changed nothing

    def test_short_overwrite_leaves_no_part_behind(self):
        self.store.put("big", "y" * 20000)
        self.assertGreater(len(blobs_for(self.backend, self.store, "big")), 3)
        self.store.put("big", "tiny")
        self.assertEqual(self.store.get("big"), "tiny")
        self.assertEqual(len(blobs_for(self.backend, self.store, "big")), 1)

    def test_missing_part_gives_none(self):
        self.store.put("big", "z" * 6000)
        target = self.store._target("big")
        del self.backend.data[target + "#1"]
        self.assertIsNone(self.store.get("big"))

    def test_old_head_with_new_parts_gives_none(self):
        """A save cut off after the parts but before the head."""
        target = self.store._target("big")
        self.store.put("big", "a" * 6000)
        old_head = self.backend.data[target]
        self.store.put("big", "b" * 6000)
        self.backend.data[target] = old_head
        self.assertIsNone(self.store.get("big"))

    def test_bad_names(self):
        for bad in ("", "A", "1a", "a b", "a/b", "a#1", "x" * 42, None, 5, b"abc"):
            for call in (lambda: self.store.get(bad), lambda: self.store.put(bad, "v"), lambda: self.store.delete(bad)):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    call()
        self.store.put("x" * 41, "ok")  # the longest allowed
        self.assertEqual(self.store.get("x" * 41), "ok")

    def test_lone_surrogate_value(self):
        secret = "pass\ud800word-SECRET"
        with self.assertRaises(SecretStoreError) as caught:
            self.store.put("thing", secret)
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertNotIn("SECRET", repr(caught.exception.args))
        self.assertIsNone(self.store.get("thing"))


class UnavailableTest(unittest.TestCase):

    def test_unavailable_backend(self):
        self.addCleanup(secret_store.set_backend, helpers.SECRETS)
        secret_store.set_backend(UnavailableBackend())
        store = SecretStore(helpers.TMP / "store-u")
        self.assertFalse(store.available())
        for call in (lambda: store.get("a"), lambda: store.put("a", "v"), lambda: store.delete("a")):
            with self.assertRaises(NotAvailable):
                call()
        secret_store.set_backend(MemoryBackend())
        self.assertTrue(store.available())

    def test_reset_db_puts_the_memory_backend_back(self):
        self.addCleanup(secret_store.set_backend, helpers.SECRETS)
        secret_store.set_backend(UnavailableBackend())
        helpers.reset_db()
        self.assertTrue(server.SECRETS.available())


class ScratchRuleTest(unittest.TestCase):

    def setUp(self):
        self.backend = MemoryBackend()
        secret_store.set_backend(self.backend)
        self.addCleanup(secret_store.set_backend, helpers.SECRETS)

    def test_two_folders_never_see_each_other(self):
        a, b = SecretStore(helpers.TMP / "folder-a"), SecretStore(helpers.TMP / "folder-b")
        a.put("thing", "from-a")
        self.assertIsNone(b.get("thing"))
        b.put("thing", "from-b")
        self.assertEqual(a.get("thing"), "from-a")
        a.delete("thing")
        self.assertEqual(b.get("thing"), "from-b")

    @unittest.skipUnless(sys.platform == "win32", "Windows paths ignore case and trailing separators")
    def test_case_and_trailing_separator_match_on_windows(self):
        folder = str(helpers.TMP / "Folder-Mixed")
        SecretStore(folder).put("thing", "same")
        for variant in (folder.upper(), folder.lower(), folder + os.sep, folder.replace("\\", "/")):
            self.assertEqual(SecretStore(variant).get("thing"), "same", variant)

    def test_target_name_holds_neither_folder_nor_secret(self):
        folder = helpers.TMP / "Secret-Folder-Name"
        SecretStore(folder).put("thing", "THE-SECRET-VALUE")
        self.assertTrue(self.backend.data)
        for target in self.backend.data:
            self.assertNotIn("secret-folder-name", target.lower())
            self.assertNotIn(str(folder).lower(), target.lower())
            self.assertNotIn("THE-SECRET-VALUE", target)


class FakeDll:
    """Stands in for advapi32. Never reaches Credential Manager."""

    def __init__(self, read_error=1168, found=None, write_ok=1, delete_error=1168):
        self.read_error, self.found, self.write_ok, self.delete_error = read_error, found, write_ok, delete_error
        self.freed, self.written, self.keep = [], [], []

        def read(target, kind, flags, out):
            if self.found is None:
                ctypes.set_last_error(self.read_error)
                return 0
            blob = (ctypes.c_ubyte * len(self.found)).from_buffer_copy(self.found) if self.found else None
            cred = secret_store.CREDENTIALW()
            cred.CredentialBlobSize = len(self.found)
            if blob is not None:
                cred.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
            self.keep.extend([blob, cred])
            out._obj.contents = cred
            return 1

        def write(cred, flags):
            c = cred._obj
            self.written.append((c.TargetName, c.Type, c.Persist, c.UserName,
                                 ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)))
            if not self.write_ok:
                ctypes.set_last_error(5)
            return self.write_ok

        def delete(target, kind, flags):
            ctypes.set_last_error(self.delete_error)
            return 0 if self.delete_error else 1

        self.CredReadW, self.CredWriteW, self.CredDeleteW = read, write, delete
        self.CredFree = lambda pointer: self.freed.append(pointer)


class WindowsBackendFakeTest(unittest.TestCase):

    def test_struct_size_on_64_bit(self):
        if sys.maxsize <= 2 ** 32:
            self.skipTest("32-bit Python")
        self.assertEqual(ctypes.sizeof(secret_store.CREDENTIALW), 80)

    def test_not_found_reads_none_and_deletes_fine(self):
        backend = secret_store.WindowsBackend(dll=FakeDll(read_error=1168, delete_error=1168))
        self.assertIsNone(backend.read("t"))
        backend.delete("t")

    def test_other_errors_give_not_available(self):
        backend = secret_store.WindowsBackend(dll=FakeDll(read_error=5, delete_error=5))
        with self.assertRaises(NotAvailable):
            backend.read("t")
        with self.assertRaises(NotAvailable):
            backend.delete("t")
        with self.assertRaises(NotAvailable):
            secret_store.WindowsBackend(dll=FakeDll(write_ok=0)).write("t", b"data")

    def test_write_sends_a_local_machine_generic_entry(self):
        dll = FakeDll()
        secret_store.WindowsBackend(dll=dll).write("target-x", b"abc")
        target, kind, persist, user, blob = dll.written[0]
        self.assertEqual((target, kind, persist, blob), ("target-x", 1, 2, b"abc"))
        self.assertEqual(user, "CareIncidentLog")

    def test_cred_free_is_called_after_every_read_that_found_something(self):
        for found in (b"hello", b""):
            dll = FakeDll(found=found)
            self.assertEqual(secret_store.WindowsBackend(dll=dll).read("t"), found)
            self.assertEqual(len(dll.freed), 1, found)

    def test_cred_free_is_called_even_when_reading_the_blob_fails(self):
        dll = FakeDll(found=b"hello")
        backend = secret_store.WindowsBackend(dll=dll)
        with mock.patch.object(secret_store.ctypes, "string_at", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                backend.read("t")
        self.assertEqual(len(dll.freed), 1)


@unittest.skipUnless(os.environ.get("CARELOG_TEST_REAL_CREDMAN") == "1" and sys.platform == "win32",
                     "opt-in: set CARELOG_TEST_REAL_CREDMAN=1 on Windows to use the real Credential Manager")
class RealCredentialManagerTest(unittest.TestCase):
    """Touches only one entry it names itself, and removes it."""

    def test_round_trip(self):
        backend = secret_store.WindowsBackend()
        target = "CareIncidentLog-test-" + secrets.token_hex(8)
        try:
            self.assertIsNone(backend.read(target))
            backend.write(target, b"first value")
            self.assertEqual(backend.read(target), b"first value")
            backend.write(target, b"second, longer value")
            self.assertEqual(backend.read(target), b"second, longer value")
            backend.write(target, b"x" * secret_store.MAX_BLOB)  # the most one entry can hold
            self.assertEqual(backend.read(target), b"x" * secret_store.MAX_BLOB)
        finally:
            backend.delete(target)
        self.assertIsNone(backend.read(target))


# ---------------------------------------------------------------- the Gemini key move

def db_bytes():
    out = server.DB_PATH.read_bytes()
    wal = Path(str(server.DB_PATH) + "-wal")
    return out + (wal.read_bytes() if wal.exists() else b"")


def put_row(value=KEY, name="gemini_key"):
    with closing(server.connect()) as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (name, value))
        conn.commit()


def rows():
    with closing(server.connect()) as conn:
        return {r[0]: r[1] for r in conn.execute("SELECT key, value FROM settings")}


def clear_backups():
    assert helpers._inside_tmp(server.BACKUPS)
    if server.BACKUPS.exists():
        for f in server.BACKUPS.iterdir():
            f.unlink()


class GeminiKeyMoveTest(unittest.TestCase):

    def setUp(self):
        helpers.reset_db()
        self.addCleanup(secret_store.set_backend, helpers.SECRETS)
        clear_backups()
        for name in ("mail.log", "skills.log", "secret_move.log"):
            (server.DATA / name).unlink(missing_ok=True)

    def test_the_move(self):
        put_row()
        self.assertIn(KEY.encode(), db_bytes())  # the test has teeth: the bytes are there before the move
        server.move_gemini_key()
        self.assertEqual(server.SECRETS.get("gemini_key"), KEY)
        self.assertNotIn("gemini_key", rows())
        self.assertNotIn(KEY.encode(), db_bytes())
        today = server.BACKUPS / f"incidents_{datetime.now():%Y-%m-%d}.db"
        today.unlink(missing_ok=True)
        server.backup_db()
        self.assertTrue(today.exists())
        self.assertNotIn(KEY.encode(), today.read_bytes())
        with closing(server.connect()) as conn:
            self.assertEqual(server.gemini_key(conn), KEY)

    def test_before_the_move_a_new_backup_would_carry_the_key(self):
        put_row()
        today = server.BACKUPS / f"incidents_{datetime.now():%Y-%m-%d}.db"
        today.unlink(missing_ok=True)
        server.backup_db()
        self.assertIn(KEY.encode(), today.read_bytes())

    def test_store_wins_over_the_row(self):
        server.SECRETS.put("gemini_key", "AIza-newer-key-in-store")
        put_row("AIza-older-key-in-row")
        server.move_gemini_key()
        self.assertEqual(server.SECRETS.get("gemini_key"), "AIza-newer-key-in-store")
        self.assertNotIn("gemini_key", rows())
        self.assertNotIn(b"AIza-older-key-in-row", db_bytes())

    def test_blank_row_is_removed(self):
        put_row("   ")
        server.move_gemini_key()
        self.assertNotIn("gemini_key", rows())
        self.assertIsNone(server.SECRETS.get("gemini_key"))

    def test_store_not_available_keeps_the_row_until_a_later_start(self):
        put_row()
        secret_store.set_backend(UnavailableBackend())
        server.move_gemini_key()  # must not raise
        self.assertEqual(rows().get("gemini_key"), KEY)
        with closing(server.connect()) as conn:
            self.assertEqual(server.gemini_key(conn), KEY)
        secret_store.set_backend(helpers.SECRETS)
        server.move_gemini_key()
        self.assertEqual(server.SECRETS.get("gemini_key"), KEY)
        self.assertNotIn("gemini_key", rows())

    def test_read_back_mismatch_keeps_the_row_and_clears_the_store(self):
        put_row()
        real_get, calls = server.SECRETS.get, []

        def get(name):
            calls.append(name)
            return None if len(calls) == 1 else "something-else-entirely"

        with mock.patch.object(server.SECRETS, "get", side_effect=get):
            server.move_gemini_key()
        self.assertEqual(rows().get("gemini_key"), KEY)
        self.assertIsNone(real_get("gemini_key"))
        self.assertEqual(helpers.SECRETS.data, {})

    def test_move_log_counts_old_backups_and_changes_none(self):
        put_row()
        server.BACKUPS.mkdir(exist_ok=True)
        old, clean = server.BACKUPS / "incidents_2020-01-01.db", server.BACKUPS / "incidents_2020-01-02.db"
        shutil.copy(server.DB_PATH, old)
        self.assertIn(KEY.encode(), old.read_bytes())
        with closing(sqlite3.connect(clean)) as c:
            c.execute("CREATE TABLE t (x)")
            c.commit()
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (old, clean)}
        server.move_gemini_key()
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (old, clean)}
        self.assertEqual(before, after)
        text = (server.DATA / "secret_move.log").read_text(encoding="utf-8")
        self.assertNotIn(KEY, text)
        entry = json.loads(text.splitlines()[-1])
        self.assertEqual((entry["backups_total"], entry["backups_holding_key"]), (2, 1))

    def test_the_key_never_shows_anywhere_else(self):
        put_row()
        server.move_gemini_key()
        put_row(KEY)  # worst case: a leftover row as well as the store entry
        code, reply, _ = helpers.api("GET", "/api/settings")
        self.assertEqual(code, 200)
        self.assertNotIn(KEY, json.dumps(reply))
        self.assertTrue(reply["gemini_key_set"])
        self.assertNotIn("gemini_key", reply)
        with closing(server.connect()) as conn:
            self.assertNotIn(KEY, json.dumps(server.public_settings(conn)))
        # a skill can't read it with settings_get
        case = tsc.SkillsTestCase("setUp")
        case.setUp()
        self.addCleanup(shutil.rmtree, case.dir, True)
        source = "def go(ctx):\n    return {'got': ctx.settings_get('gemini_key')}\n"
        case.write_skill("peek", source, [tsc.action("go")])
        case.write_skill("greedy", source, [tsc.action("go")], settings=["gemini_key"])
        with closing(server.connect()) as conn:
            case.settings.update(server.get_settings(conn))
        host = case.host()
        for name in ("peek__go", "greedy__go"):
            self.assertNotIn(KEY, json.dumps(host.call(name), default=str), name)
        for log in (case.dir / "skills.log", server.DATA / "skills.log", server.DATA / "mail.log",
                    server.DATA / "secret_move.log"):
            if log.exists():
                self.assertNotIn(KEY, log.read_text(encoding="utf-8"), log.name)

    def test_saving_a_key_goes_to_the_store_not_the_table(self):
        code, reply, _ = helpers.api("PUT", "/api/settings", {"gemini_key": KEY, "gemini_enabled": "1"})
        self.assertEqual(code, 200)
        self.assertEqual(server.SECRETS.get("gemini_key"), KEY)
        self.assertNotIn("gemini_key", rows())
        self.assertNotIn(KEY.encode(), db_bytes())
        self.assertNotIn(KEY, json.dumps(reply))
        self.assertEqual(rows().get("gemini_enabled"), "1")

    def test_saving_a_key_when_the_store_is_unavailable(self):
        secret_store.set_backend(UnavailableBackend())
        code, reply, _ = helpers.api("PUT", "/api/settings", {"gemini_key": KEY})
        self.assertEqual(code, 400)
        self.assertNotIn(KEY, json.dumps(reply))
        self.assertTrue(reply.get("error"))
        self.assertNotIn("Traceback", reply["error"])
        self.assertNotIn("gemini_key", rows())
        self.assertNotIn(KEY.encode(), db_bytes())

    def test_the_request_to_gemini_carries_the_key_only_in_the_header(self):
        server.SECRETS.put("gemini_key", KEY)
        put_row("1", "gemini_enabled")
        seen = []

        class Reply:
            def __init__(self, data):
                self.data = data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, *a):
                return self.data

        answer = {"candidates": [{"content": {"parts": [{"text": json.dumps(
            {"description": "d", "formal_summary": "f", "category": "other", "severity": "minor",
             "never_came": False})}]}}]}

        def fake_open(req, timeout=None):
            seen.append(req)
            return Reply(json.dumps(answer).encode())

        with mock.patch.object(urllib.request, "urlopen", fake_open):
            code, reply, _ = helpers.api("POST", "/api/tidy", {"text": "Nobody came when I rang the bell."})
        self.assertEqual(code, 200)
        self.assertEqual(len(seen), 1, "Gemini wasn't asked")
        req = seen[0]
        headers = {k.lower(): v for k, v in req.header_items()}
        self.assertEqual(headers.get("x-goog-api-key"), KEY)
        self.assertNotIn(KEY, req.full_url)
        self.assertNotIn("key=", req.full_url)
        self.assertNotIn(KEY.encode(), req.data)
        self.assertNotIn(KEY, json.dumps(reply))

    def test_another_folders_store_cannot_read_it(self):
        server.SECRETS.put("gemini_key", KEY)
        self.assertIsNone(SecretStore(helpers.TMP / "some-other-folder").get("gemini_key"))
        self.assertEqual(SecretStore(server.DATA).get("gemini_key"), KEY)


if __name__ == "__main__":
    unittest.main()
