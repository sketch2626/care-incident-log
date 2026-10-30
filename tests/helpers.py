"""Shared test helpers. Import this module BEFORE anything imports server.

Everything runs against a scratch folder. The real log (%APPDATA%\\CareIncidentLog) and the real
Andy Flow history (%APPDATA%\\Andyflow) are never opened, written or copied.
"""
import atexit
import gc
import http.client
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The server reads its paths from the environment at import time, so set them first.
TMP = Path(tempfile.mkdtemp(prefix="cil-tests-")).resolve()
os.environ["APPDATA"] = str(TMP)
os.environ["TRACKER_DATA"] = str(TMP / "CareIncidentLog-test")
os.environ["TRACKER_PORT"] = "0"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402

server._speech = False  # speech_engine() returns None; never loads the mic or the model


def _inside_tmp(path):
    try:
        Path(path).resolve().relative_to(TMP)
        return True
    except ValueError:
        return False


if not (_inside_tmp(server.DB_PATH) and _inside_tmp(server.ANDYFLOW_DB)):
    shutil.rmtree(TMP, ignore_errors=True)
    raise SystemExit(
        "SAFETY STOP: the tests would touch files outside their scratch folder "
        f"({server.DB_PATH} / {server.ANDYFLOW_DB}). Nothing was run.")

_httpd = None
_port = None


def _cleanup():
    if _httpd is not None:
        try:
            _httpd.shutdown()
            _httpd.server_close()
        except Exception:
            pass
    # The server leaves its sqlite connections to the garbage collector; Windows can't delete
    # the db file until they are closed.
    gc.collect()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def start_server():
    """Start the one shared in-process server (127.0.0.1, free port, scratch data). Returns the port."""
    global _httpd, _port
    if _httpd is None:
        server.init_db()
        _httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        _port = _httpd.server_address[1]
        threading.Thread(target=_httpd.serve_forever, daemon=True).start()
    return _port


def api(method, path, body=None, headers=None, tracker=True, host=None):
    """Call the test server. Returns (status, parsed JSON or raw bytes, response headers)."""
    port = start_server()
    hdrs = dict(headers or {})
    if tracker:
        hdrs["X-Tracker"] = "1"
    if host is not None:
        hdrs["Host"] = host
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        status, resp_headers = resp.status, dict(resp.getheaders())
    finally:
        conn.close()
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        parsed = raw
    return status, parsed, resp_headers


def db_rows(sql, args=()):
    """Read straight from the scratch incidents db (for checking what the API really stored)."""
    with closing(sqlite3.connect(server.DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, args)]


def reset_db():
    """Empty the scratch db and remove the fixture Andy Flow db."""
    start_server()
    with closing(sqlite3.connect(server.DB_PATH)) as conn:
        for table in ("incidents", "settings", "inbox_seen", "memories"):  # M9c: memories
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('incidents', 'memories')")
        conn.commit()
    try:
        server.ANDYFLOW_DB.unlink()
    except FileNotFoundError:
        pass


def enable_andyflow(on=True):
    """Turn the Andy Flow link on (or off) in the scratch settings. It starts off; reset_db clears it."""
    start_server()
    with closing(sqlite3.connect(server.DB_PATH)) as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('andyflow_enabled', ?)",
                     ("1" if on else "0",))
        conn.commit()


def make_andyflow_db(dictations=(), notes=()):
    """Create a fixture Andy Flow db at server.ANDYFLOW_DB (inside the scratch folder).

    dictations: (id, timestamp, text, window_title) tuples
    notes:      (id, created_at, title, body, folder) tuples
    """
    server.ANDYFLOW_DB.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(server.ANDYFLOW_DB)) as conn:
        conn.execute("CREATE TABLE dictations (id INTEGER PRIMARY KEY, timestamp TEXT, text TEXT, window_title TEXT)")
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, created_at TEXT, title TEXT, body TEXT, folder TEXT)")
        conn.executemany("INSERT INTO dictations VALUES (?, ?, ?, ?)", list(dictations))
        conn.executemany("INSERT INTO notes VALUES (?, ?, ?, ?, ?)", list(notes))
        conn.commit()


def incident(**overrides):
    """A valid incident payload; override any field."""
    data = {
        "occurred_date": "2026-10-20",
        "occurred_time": "14:30",
        "category": "meal",
        "description": "Lunch tray never arrived.",
        "severity": "serious",
    }
    data.update(overrides)
    return data
