"""Care Incident Log - a private, local incident tracker for nursing-home residents.

Run:  python server.py            (opens http://localhost:8765 in the browser)
      python server.py --no-browser

Everything is stored in %APPDATA%\\CareIncidentLog\\incidents.db (set TRACKER_DATA to
use another folder) and backed up daily to its backups\\ folder. Nothing leaves this computer.
"""
import csv
import io
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import threading
import webbrowser
from contextlib import closing
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import assist
import mary
import power

# In the packaged app, web/ is unpacked next to the program (sys._MEIPASS).
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
WEB = ROOT / "web"
# Per-user data folder, so the log survives app updates and never sits next to the .exe.
DEFAULT_DATA = Path(os.environ.get("APPDATA") or Path.home()) / "CareIncidentLog"
DATA = Path(os.environ.get("TRACKER_DATA") or DEFAULT_DATA)
LEGACY_DATA = ROOT / "data"  # where versions before the desktop app kept the log
DB_PATH = DATA / "incidents.db"
BACKUPS = DATA / "backups"
ANDYFLOW_DB = Path(os.environ.get("APPDATA", "")) / "Andyflow" / "history.db"
PORT = int(os.environ.get("TRACKER_PORT", "8765"))
PAGE_TITLE = "Care Incident Log"
KEEP_BACKUPS = 30
MAX_BODY = 5 * 1024 * 1024  # biggest request body the server will read
BAD_REQUEST = "That request didn't look right."
NOT_FOUND = "That entry wasn't found."

CATEGORIES = {
    "call_light": "Call light not answered",
    "meal": "Meal missed or late",
    "bathing": "Bath or shower missed",
    "toileting": "Toileting / brief change",
    "medication": "Medication problem",
    "repositioning": "Not turned or repositioned",
    "staff": "Staff conduct",
    "safety": "Fall, injury or safety",
    "other": "Something else",
}
SEVERITIES = {"minor", "serious", "dangerous"}
TEXT_FIELDS = ["occurred_date", "occurred_time", "category", "description", "severity",
               "staff_involved", "reported_to", "outcome", "witnesses", "source", "source_id",
               "formal_summary"]
SETTING_KEYS = {"resident_name", "room", "facility", "facility_address", "state",
                "gemini_enabled", "gemini_key", "gemini_model",
                "companion", "voice_rate", "voice_volume", "andyflow_enabled"}
# Mary's voice settings: (lowest, highest, default). Saved values are clamped into range.
VOICE_LIMITS = {"voice_rate": (0.6, 1.4, 0.92), "voice_volume": (0.2, 1.0, 1.0)}
NO_SPEECH = "Talking isn't set up on this computer yet. You can type instead."

# A dictation or note is offered to the inbox when it starts with "Incident" (or "New incident").
INBOX_TRIGGER = re.compile(r"^\W*(new\s+)?incident\b", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_date TEXT NOT NULL,
    occurred_time TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    wait_minutes INTEGER,
    never_came INTEGER NOT NULL DEFAULT 0,
    severity TEXT NOT NULL DEFAULT 'minor',
    staff_involved TEXT NOT NULL DEFAULT '',
    reported_to TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    witnesses TEXT NOT NULL DEFAULT '',
    formal_summary TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    source_id TEXT NOT NULL DEFAULT '',
    logged_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inbox_seen (
    kind TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    at TEXT NOT NULL,
    PRIMARY KEY (kind, source_id)
);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def log_is_empty(path):
    """True if the log at path doesn't exist yet or holds no incidents and no settings.
    Any other trouble reading it counts as "not empty", so a real log is never overwritten."""
    if not path.exists():
        return True
    try:
        with closing(sqlite3.connect(path)) as conn:
            for table in ("incidents", "settings"):
                try:
                    if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None:
                        return False
                except sqlite3.OperationalError as e:
                    if "no such table" not in str(e):
                        return False
        return True
    except sqlite3.Error:
        return False


def migrate_legacy_data():
    """Copy an older data/ folder into the per-user folder until the new log has incidents
    or settings. The old copy is left in place."""
    old_db = LEGACY_DATA / "incidents.db"
    if DATA != DEFAULT_DATA or not old_db.exists() or not log_is_empty(DB_PATH):
        return
    with sqlite3.connect(old_db) as src, sqlite3.connect(DB_PATH) as dst:
        src.backup(dst)
    BACKUPS.mkdir(exist_ok=True)
    for old in (LEGACY_DATA / "backups").glob("incidents_*.db"):
        if not (BACKUPS / old.name).exists():
            shutil.copy2(old, BACKUPS / old.name)


def init_db():
    DATA.mkdir(parents=True, exist_ok=True)
    migrate_legacy_data()
    with connect() as conn:
        conn.executescript(SCHEMA)
        if "formal_summary" not in {r["name"] for r in conn.execute("PRAGMA table_info(incidents)")}:
            conn.execute("ALTER TABLE incidents ADD COLUMN formal_summary TEXT NOT NULL DEFAULT ''")
        # The Andy Flow link is the resident's choice and starts off. A log that already holds entries
        # imported from Andy Flow was connected before this setting existed, so it keeps the link, once.
        if "andyflow_enabled" not in get_settings(conn) and conn.execute(
                "SELECT 1 FROM incidents WHERE source LIKE 'andyflow-%' LIMIT 1").fetchone():
            conn.execute("INSERT INTO settings (key, value) VALUES ('andyflow_enabled', '1')")
    backup_db()


def backup_db():
    """One copy per day, newest KEEP_BACKUPS kept. Evidence should never live in one file.
    Called at start-up and after each save, so a window left open for days still gets one.
    Never raises: a failed backup must not stop the app or a save, and tries again next time."""
    tmp = None
    try:
        BACKUPS.mkdir(exist_ok=True)
        target = BACKUPS / f"incidents_{datetime.now():%Y-%m-%d}.db"
        if not target.exists():
            # Copy to a temporary name first, so a half-written file is never taken for today's backup.
            tmp = target.with_suffix(".tmp")
            tmp.unlink(missing_ok=True)
            with closing(connect()) as src, closing(sqlite3.connect(tmp)) as dst:
                src.backup(dst)
            os.replace(tmp, target)
        for old in sorted(BACKUPS.glob("incidents_*.db"))[:-KEEP_BACKUPS]:
            old.unlink()
    except Exception:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def clean_incident(data):
    """Validate and normalise an incident payload. Raises ValueError with a plain-language message."""
    row = {k: str(data.get(k) or "").strip() for k in TEXT_FIELDS}
    try:  # the shape is checked first; strptime then rejects dates like 2026-02-31
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["occurred_date"]):
            raise ValueError
        datetime.strptime(row["occurred_date"], "%Y-%m-%d")
    except ValueError:
        raise ValueError("Please choose the date it happened.") from None
    try:
        if row["occurred_time"]:
            if not re.fullmatch(r"\d{2}:\d{2}", row["occurred_time"]):
                raise ValueError
            datetime.strptime(row["occurred_time"], "%H:%M")
    except ValueError:
        raise ValueError("The time doesn't look right.") from None
    if row["category"] not in CATEGORIES:
        raise ValueError("Please choose what kind of problem it was.")
    if not row["description"]:
        raise ValueError("Please say what happened.")
    if row["severity"] not in SEVERITIES:
        row["severity"] = "minor"
    row["source"] = row["source"] or "manual"
    try:  # "30", 30, "30.0" and 30.5 all mean 30; anything else is "not known"
        wait = int(float(str(data.get("wait_minutes")).strip()))
    except (ValueError, OverflowError):
        wait = None
    row["wait_minutes"] = wait if wait is not None and 0 <= wait <= 100000 else None
    row["never_came"] = 1 if str(data.get("never_came")).strip().lower() in ("1", "true", "yes") else 0
    return row


def list_incidents(conn, date_from="", date_to=""):
    sql = "SELECT * FROM incidents WHERE deleted_at IS NULL"
    args = []
    if date_from:
        sql += " AND occurred_date >= ?"
        args.append(date_from)
    if date_to:
        sql += " AND occurred_date <= ?"
        args.append(date_to)
    sql += " ORDER BY occurred_date DESC, occurred_time DESC, id DESC"
    return [dict(r) for r in conn.execute(sql, args)]


def get_settings(conn):
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


def andyflow_on(conn):
    """True only when the resident has turned the Andy Flow link on. Off or never set: its file is never opened."""
    return get_settings(conn).get("andyflow_enabled") == "1"


def public_settings(conn):
    """Settings for the page. The Gemini key never leaves the server; the page only learns whether one is set."""
    s = get_settings(conn)
    s["gemini_key_set"] = bool(s.pop("gemini_key", ""))
    return s


def clean_voice_setting(key, value):
    """A voice setting clamped into its range, as text; None if it isn't a usable number."""
    low, high, _ = VOICE_LIMITS[key]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return str(round(min(high, max(low, number)), 2))


# Mary. One talk at a time, so two requests never interleave her memory.
_mary_lock = threading.Lock()
HELLO_NO_NAME = "I'm sorry, I didn't quite catch your name. Could you say it once more?"
TALK_NO_TEXT = "I didn't catch anything. Could you say that again?"


def mary_memory():
    return mary.Memory(DATA / "mary" / "memory.json")


def mary_settings():
    """What Mary needs from the saved settings. Her key is used whenever one is saved; the
    'smart helper' switch only controls the incident helper."""
    with closing(connect()) as conn:
        s = get_settings(conn)
    companion = s.get("companion", "")
    out = {"companion": companion if companion in mary.COMPANIONS else "",
           "key": s.get("gemini_key", "").strip(), "model": s.get("gemini_model", "").strip()}
    for k, (_, _, default) in VOICE_LIMITS.items():
        got = clean_voice_setting(k, s.get(k))
        out[k] = float(got) if got is not None else default
    return out


def mary_status():
    s = mary_settings()
    name = mary_memory().name
    return {"companion": s["companion"], "first_run": not s["companion"],
            "companions": mary.COMPANIONS, "has_key": bool(s["key"]), "name": name,
            "voice_rate": s["voice_rate"], "voice_volume": s["voice_volume"]}


def mary_write_incident(incident):
    """The resident said yes to 'Would you like me to write that down?': log her guess. Returns the new id."""
    with closing(connect()) as conn:
        new_id = insert_incident(conn, clean_incident({**incident, "source": "mary"}))
        conn.commit()
    backup_db()  # Mary's window stays open for days: her first save of a day makes that day's backup
    return new_id


def mary_talk(text, on_text=None, on_mood=None):
    """Mary's answer to text, for the page. Never contains the key."""
    s = mary_settings()
    with _mary_lock:
        r = mary.reply(text, mary_memory(), s["key"], s["model"], on_text=on_text,
                       companion=s["companion"] or "mary", on_mood=on_mood, write=mary_write_incident)
    return {"text": r["text"], "mood": r["mood"],
            "emergency": bool(r["emergency"] or r["gemini_alert"]),
            "emergency_kind": r["emergency"] or ("other" if r["gemini_alert"] else ""),
            "offer": r["offer"], "logged": r["logged"], "error": r["error"], "needs_key": not s["key"],
            "bad_key": r["error"] == mary.BAD_KEY,
            "first_words_s": r["first_words_s"], "total_s": r["total_s"]}


_speech = None


def speech_engine():
    """Local speech-to-text, imported on first use so the app still starts without it."""
    global _speech
    if _speech is None:
        try:
            import speech
            _speech = speech
        except ImportError:
            _speech = False
    return _speech or None


def tidy(conn, text):
    """Sort a free-form report into incident fields: Gemini if the resident switched it on, else the offline guesser."""
    guess = guess_incident(text, now())
    s = get_settings(conn)
    if s.get("gemini_enabled") == "1" and s.get("gemini_key"):
        try:
            ai = assist.structure(text, s["gemini_key"], list(CATEGORIES), s.get("gemini_model", ""))
            for k in ("description", "formal_summary", "category", "severity", "wait_minutes", "never_came",
                      "occurred_time", "staff_involved", "reported_to", "outcome"):
                if ai.get(k) not in (None, ""):
                    guess[k] = ai[k]
            guess["assisted"] = True
        except Exception:
            guess["assist_error"] = "The smart helper couldn't be reached, so the basic sorter was used."
    return guess


def scan_andyflow(conn):
    """Dictations and notes from Andy Flow that start with 'Incident' and haven't been handled yet.
    "enabled" is the resident's switch, "installed" whether Andy Flow's file is on this computer."""
    installed = ANDYFLOW_DB.exists()  # only looks at the file; never opens it
    if not andyflow_on(conn):
        return {"available": False, "enabled": False, "installed": installed, "items": []}
    if not installed:
        return {"available": False, "enabled": True, "installed": False, "items": []}
    seen = {(r["kind"], r["source_id"]) for r in conn.execute("SELECT kind, source_id FROM inbox_seen")}
    items = []
    try:  # read-only; as_uri() escapes a # or % in the path
        af = sqlite3.connect(ANDYFLOW_DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    except Exception:
        return {"available": False, "enabled": True, "installed": True, "items": []}
    try:
        # A missing (NULL) value in Andy Flow's file reads as empty text, and a row with no time is skipped.
        for id_, at, text, window in af.execute(
                "SELECT id, COALESCE(timestamp, ''), COALESCE(text, ''), COALESCE(window_title, '') FROM dictations"):
            if not at:
                continue
            if PAGE_TITLE.lower() in window.lower():
                continue  # dictated straight into this tracker, already logged
            if INBOX_TRIGGER.search(text) and ("dictation", id_) not in seen:
                items.append({"kind": "dictation", "source_id": id_, "at": at, "text": text.strip()})
        for id_, at, title, body, folder in af.execute(
                "SELECT id, COALESCE(created_at, ''), COALESCE(title, ''), COALESCE(body, ''), "
                "COALESCE(folder, '') FROM notes"):
            if not at:
                continue
            text = (body or title).strip()
            in_folder = "incident" in folder.lower()
            if text and (in_folder or INBOX_TRIGGER.search(title) or INBOX_TRIGGER.search(body)) \
                    and ("note", id_) not in seen:
                items.append({"kind": "note", "source_id": id_, "at": at, "text": text})
    except Exception:
        return {"available": False, "enabled": True, "installed": True, "items": []}
    finally:
        af.close()
    items.sort(key=lambda i: i["at"], reverse=True)
    for item in items:
        item["guess"] = guess_incident(item["text"], item["at"])
    return {"available": True, "enabled": True, "installed": True, "items": items}


def mark_seen(conn, kind, source_id, status):
    conn.execute("INSERT OR REPLACE INTO inbox_seen (kind, source_id, status, at) VALUES (?, ?, ?, ?)",
                 (kind, int(source_id), status, now()))


# First match wins, so toileting ("bathroom") is checked before bathing ("bath").
# Someone hurt them: a person must be the one doing it ("it hit me that I miss my wife" is not).
HURT_ME = (r"\b(?:nurse|aide|cna|staff|worker|orderly|someone|somebody|they|he|she|man|woman|lady|guy|roommate|resident|visitor)"
           r"\s+(?:\w+\s+)?(?:hit|slapped|punched|kicked|pushed|shoved|pinched|grabbed|hurt)\s+me\b")
GUESS_CATEGORY = [(k, re.compile(p, re.I)) for k, p in [
    ("call_light", r"call ?light|buzzer|pressed (my|the) (button|light)"),
    ("meal", r"dinner|lunch|breakfast|meal|tray|food|hungry|kitchen|snack|sandwich"),
    ("toileting", r"brief|diaper|toilet|bedpan|urinal|soiled|\bwet\b|bathroom"),
    ("bathing", r"bath|shower|wash(ed)? me"),
    ("medication", r"\bmeds?\b|medication|pill|dose|insulin"),
    ("repositioning", r"turn(ed)? me|reposition|bed ?sore|pressure (sore|ulcer)"),
    ("safety", r"\bfell\b|\bfall\b|injur|bruise|unsafe"),
    ("staff", r"rude|yell|attitude|disrespect|scream|cuss|threaten|" + HURT_ME),
]]
NEVER_CAME = re.compile(r"\b(never|nobody|no one|no-one)\s+(ever\s+)?(came|showed|answered|brought|asked)\b(?!\s+(for|until)\b)", re.I)
_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90}
WORD_NUMS = {"a": 1, "an": 1, **_UNITS, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
             "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
             **_TENS, **{f"{t} {u}": tn + un for t, tn in _TENS.items() for u, un in _UNITS.items()}}
# Longest first, so "twenty five" wins over "twenty"; a space in a key also matches a hyphen ("twenty-five").
_NUM_WORDS = "|".join(k.replace(" ", r"[\s-]+") for k in sorted(WORD_NUMS, key=len, reverse=True))
WAIT = re.compile(r"\b(\d+|" + _NUM_WORDS + r")(\s+and\s+a\s+half)?\s*(hours?|hrs?|minutes?|mins?)(\s+and\s+a\s+half)?\b", re.I)
HALF_HOUR = re.compile(r"\b(?:a\s+)?half\s+(?:an?\s+)?hour\b", re.I)
DANGEROUS = re.compile(r"\bfell\b|\bfall\b|injur|bleed|\bbled\b|chok|fever|unsafe|" + HURT_ME + r"|"
                       r"\b(?:can'?t|can\s*not|couldn'?t|could\s+not)\s+breathe|hard to breathe|trouble breathing|short of breath", re.I)
SERIOUS = re.compile(r"hungry|pain|hurt|soiled|sitting in|cry|skipped|never|nobody|no one|hours?\b", re.I)


def guess_incident(text, at):
    """Best guess at a structured incident from a free-form 'Incident: ...' dictation."""
    body = INBOX_TRIGGER.sub("", text, count=1).lstrip(" :.,-").strip() or text.strip()
    body = re.sub(r"\b(um+|uh+|erm*)\b[,.]?\s*", "", body, flags=re.I).strip() or body  # only pure filler
    body = body[:1].upper() + body[1:]
    category = next((k for k, rx in GUESS_CATEGORY if rx.search(body)), "other")
    wait = None
    m, half = WAIT.search(body), HALF_HOUR.search(body)
    if half and (not m or half.start() <= m.start()):
        wait = 30  # "half an hour", "a half hour"
    elif m:
        word = re.sub(r"[\s-]+", " ", m.group(1).lower())
        n = int(word) if word.isdigit() else WORD_NUMS[word]
        hours = m.group(3).lower().startswith("h")
        wait = n * 60 + (30 if hours and (m.group(2) or m.group(4)) else 0) if hours else n
    plain = body.replace("’", "'")  # dictation often types a curly apostrophe: can’t
    severity = "dangerous" if DANGEROUS.search(plain) else "serious" if SERIOUS.search(plain) else "minor"
    return {"occurred_date": at[:10], "occurred_time": at[11:16], "category": category,
            "description": body, "severity": severity, "wait_minutes": wait,
            "never_came": bool(NEVER_CAME.search(body))}


def insert_incident(conn, row):
    row["logged_at"] = row["updated_at"] = now()
    cur = conn.execute(f"INSERT INTO incidents ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                       list(row.values()))
    return cur.lastrowid


def import_andyflow(conn):
    """The 'Update from Andy Flow' button: log every new 'Incident' dictation or note in one go."""
    # Take the write lock before looking at what was already seen, so two imports (two clicks, or the
    # app and Claude's MCP) can't both add the same items. The caller's `with connect()` commits.
    if not andyflow_on(conn):
        return {"available": False, "enabled": False, "added": 0, "ids": []}
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    inbox = scan_andyflow(conn)
    ids = []
    for item in inbox["items"]:
        row = clean_incident({**item["guess"], "source": f"andyflow-{item['kind']}",
                              "source_id": str(item["source_id"])})
        ids.append(insert_incident(conn, row))
        mark_seen(conn, item["kind"], item["source_id"], "added")
    return {"available": inbox["available"], "enabled": inbox["enabled"], "added": len(ids), "ids": ids}


def export_csv(rows):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date", "Time", "Problem", "Severity", "What happened", "Minutes waited",
                "No one came", "Staff involved", "Reported to", "What happened after",
                "Witnesses", "Logged at"])
    for r in sorted(rows, key=lambda r: (r["occurred_date"], r["occurred_time"])):
        w.writerow([r["occurred_date"], r["occurred_time"], CATEGORIES.get(r["category"], r["category"]),
                    r["severity"].title(), _csv_safe(r["description"]), r["wait_minutes"] or "",
                    "Yes" if r["never_came"] else "", _csv_safe(r["staff_involved"]), _csv_safe(r["reported_to"]),
                    _csv_safe(r["outcome"]), _csv_safe(r["witnesses"]), r["logged_at"]])
    return ("﻿" + out.getvalue()).encode("utf-8")  # BOM so Excel reads it correctly


def _csv_safe(value):
    """Words starting with = + - @ would run as a formula when an inspector opens the file in Excel."""
    value = str(value or "")
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")  # no other website may show the log inside its own page
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        super().end_headers()

    # Only answer this computer, and only our own page (custom header blocks other websites).
    def _allowed(self, mutating=False):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("localhost", "127.0.0.1"):
            self.send_error(403)
            return False
        if mutating and self.headers.get("X-Tracker") != "1":
            self.send_error(403)
            return False
        return True

    def _send(self, body, status=200, ctype="application/json", extra=None):
        conn, self._conn = getattr(self, "_conn", None), None
        if conn is not None and status < 400 and conn.in_transaction:
            conn.commit()  # the page may read the log the moment this reply lands
        if not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)
        return True

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 <= n <= MAX_BODY:
                raise ValueError
            raw = self.rfile.read(n)
            self._read = n
            data = json.loads(raw or b"{}")
        except ValueError:  # includes bad JSON and bad UTF-8
            raise ValueError(BAD_REQUEST) from None
        if not isinstance(data, dict):
            raise ValueError(BAD_REQUEST)
        return data

    def _mary(self, method, path, q):
        """Mary's routes. Returns None for a path that isn't one of hers."""
        if method == "GET" and path == "/api/mary/status":
            return self._send(mary_status())
        if method == "POST" and path in ("/api/mary/talk", "/api/mary/hello"):
            body = self._body()
            text = str(body.get("text") or "").strip() if isinstance(body, dict) else ""
            if path == "/api/mary/hello":
                name = mary.name_from(text)
                if not name:
                    return self._send({"name": "", "text": HELLO_NO_NAME})
                with _mary_lock:
                    memory = mary_memory()
                    memory.name = name
                    try:
                        memory.save()
                    except OSError:
                        pass  # she still greets them; with no saved name she asks again later
                return self._send({"name": name,
                                   "text": f"It's lovely to meet you, {name}! I'm here whenever you'd like to talk."})
            if not text:
                raise ValueError(TALK_NO_TEXT)
            if q("stream") == "1":
                return self._mary_stream(text)
            return self._send(mary_talk(text))
        return None

    def _mary_stream(self, text):
        """Mary's answer as it happens: one JSON line per event (mood, text pieces, then done).
        The connection closing ends the stream (HTTP/1.0); end_headers adds Cache-Control: no-store."""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        gone = False

        def line(event):
            nonlocal gone
            if gone:
                return
            try:
                self.wfile.write(json.dumps(event).encode("utf-8") + b"\n")
                self.wfile.flush()
            except (OSError, ValueError):
                gone = True  # the page went away; Mary still finishes, so the talk is remembered

        try:
            done = mary_talk(text, on_text=lambda piece: line({"text": piece}),
                             on_mood=lambda mood: line({"mood": mood}))
        except Exception:
            line({"error": "Something went wrong. Please try again."})
            return True
        line({"done": True, **done})
        return True

    def _route(self, method):
        parsed = urlparse(self.path)
        path, query = parsed.path.rstrip("/"), parse_qs(parsed.query)
        q = lambda k: (query.get(k) or [""])[0]
        m = re.fullmatch(r"/api/incidents/(\d+)", path)
        if method == "GET" and path == "/api/power":
            return self._send({"plugged_in": power.plugged_in()})
        if path.startswith("/api/mary/"):
            return self._mary(method, path, q)
        with connect() as conn:
            self._conn = conn  # _send commits it first, so a reply never arrives before its save is on disk
            if method == "GET" and path == "/api/incidents":
                import reports  # lazy, like the export routes
                rows = list_incidents(conn, q("from"), q("to"))
                for r in rows:
                    r["summary"] = reports.summary_for(r)  # same sentence the state report prints
                return self._send(rows)
            if method == "GET" and path == "/api/settings":
                return self._send(public_settings(conn))
            if method == "GET" and path == "/api/listen":
                engine = speech_engine()
                if not engine:
                    return self._send({"available": False, "loading": False, "reason": NO_SPEECH})
                engine.warm_up()
                return self._send(engine.is_ready())
            if method == "GET" and path == "/api/listen/level":
                engine = speech_engine()
                if not engine:
                    return self._send({"recording": False, "level": 0, "heard_voice": False,
                                       "quiet_s": 0, "elapsed_s": 0})
                return self._send(engine.level())
            if method == "POST" and path == "/api/listen/start":
                engine = speech_engine()
                if not engine:
                    raise ValueError(NO_SPEECH)
                try:
                    engine.start()
                except RuntimeError as e:
                    raise ValueError(str(e))
                return self._send({"ok": True})
            if method == "POST" and path == "/api/listen/stop":
                engine = speech_engine()
                try:
                    text = engine.stop() if engine else ""
                except RuntimeError as e:
                    raise ValueError(str(e))
                # raw=1: a detail box (staff name etc.) just wants the words, not a sorted incident
                guess = tidy(conn, text) if text and q("raw") != "1" else None
                return self._send({"text": text, "guess": guess})
            if method == "POST" and path == "/api/tidy":
                text = str(self._body().get("text") or "").strip()
                if not text:
                    raise ValueError("Please say or type what happened.")
                return self._send(tidy(conn, text))
            if method == "GET" and path == "/api/inbox":
                return self._send(scan_andyflow(conn))
            if method == "GET" and path == "/api/export.csv":
                name = f"care-incidents-{datetime.now():%Y-%m-%d}.csv"
                return self._send(export_csv(list_incidents(conn, q("from"), q("to"))),
                                  ctype="text/csv; charset=utf-8",
                                  extra={"Content-Disposition": f'attachment; filename="{name}"'})
            if method == "GET" and path == "/api/export.xlsx":
                import reports
                name = f"care-incident-record-{datetime.now():%Y-%m-%d}.xlsx"
                rows = list_incidents(conn, q("from"), q("to"))
                return self._send(reports.build_xlsx(rows, get_settings(conn), q("from"), q("to")),
                                  ctype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  extra={"Content-Disposition": f'attachment; filename="{name}"'})
            if method == "GET" and path == "/report":
                import reports
                rows = list_incidents(conn, q("from"), q("to"))
                page = reports.build_report_html(rows, get_settings(conn), q("from"), q("to"))
                return self._send(page.encode("utf-8"), ctype="text/html; charset=utf-8")
            if method == "POST" and path == "/api/incidents":
                data = self._body()
                new_id = insert_incident(conn, clean_incident(data))
                if data.get("inbox_kind") and data.get("inbox_id"):
                    mark_seen(conn, data["inbox_kind"], data["inbox_id"], "added")
                return self._send({"id": new_id}, 201)
            if method == "PUT" and m:
                row = clean_incident(self._body())
                row.pop("source"), row.pop("source_id")
                row["updated_at"] = now()
                cur = conn.execute(f"UPDATE incidents SET {', '.join(k + ' = ?' for k in row)} "
                                   "WHERE id = ? AND deleted_at IS NULL", [*row.values(), int(m.group(1))])
                if cur.rowcount == 0:
                    return self._send({"error": NOT_FOUND}, 404)
                return self._send({"ok": True})
            if method == "DELETE" and m:
                # Soft delete: the entry disappears from the log but stays recoverable in the file.
                cur = conn.execute("UPDATE incidents SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                                   (now(), int(m.group(1))))
                if cur.rowcount == 0:
                    return self._send({"error": NOT_FOUND}, 404)
                return self._send({"ok": True})
            if method == "PUT" and path == "/api/settings":
                for k, v in self._body().items():
                    if k == "gemini_key" and not str(v).strip():
                        continue  # a blank key box means "keep the saved key"
                    if k == "companion":
                        v = str(v).strip().lower()
                        if v and v not in mary.COMPANIONS:
                            continue  # only Mary, him, or blank
                    if k in VOICE_LIMITS:
                        v = clean_voice_setting(k, v)
                        if v is None:
                            continue
                    if k == "andyflow_enabled":
                        v = "1" if str(v).strip().lower() in ("1", "true", "yes", "on") else "0"
                    if k in SETTING_KEYS:
                        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                                     (k, str(v).strip()))
                return self._send(public_settings(conn))
            if method == "POST" and path == "/api/inbox/import":
                return self._send(import_andyflow(conn))
            if method == "POST" and path == "/api/inbox/dismiss":
                if not andyflow_on(conn):
                    raise ValueError("The Andy Flow link is off.")
                data = self._body()
                kind = str(data.get("kind") or "").strip()
                try:
                    source_id = int(data.get("source_id"))
                except (TypeError, ValueError):
                    source_id = None
                if not kind or source_id is None:
                    raise ValueError(BAD_REQUEST)
                mark_seen(conn, kind, source_id, "dismissed")
                return self._send({"ok": True})
        return None

    def _handle(self, method):
        self._read = 0
        try:
            self._dispatch(method)
        finally:
            self._drain()

    def _drain(self):
        """Read any request body we answered without reading. On Windows, closing a socket with unread
        data resets the connection, and the page can lose the reply (e.g. a 403, or listen/start's '{}')."""
        try:
            left = int(self.headers.get("Content-Length") or 0) - self._read
            if 0 < left <= MAX_BODY:
                self.connection.settimeout(5)
                self.rfile.read(left)
        except (OSError, ValueError):
            pass

    def _dispatch(self, method):
        mutating = method not in ("GET", "HEAD")
        if not self._allowed(mutating):
            return
        if not self.path.startswith("/api/") and urlparse(self.path).path.rstrip("/") != "/report":
            if method == "GET":
                return super().do_GET()
            if method == "HEAD":
                return super().do_HEAD()
            return self.send_error(405)
        if method == "HEAD":
            return self.send_error(405)
        try:
            if self._route(method) is None:
                self._send({"error": "Not found"}, 404)
            elif mutating and not self.path.startswith("/api/mary/"):
                backup_db()  # the first save of a new day makes that day's backup; otherwise a quick no-op
        except ValueError as e:
            self._send({"error": str(e)}, 400)
        except Exception as e:  # keep the server alive; show a readable message
            self._send({"error": f"Something went wrong saving that: {e}"}, 500)

    def do_GET(self):
        self._handle("GET")

    def do_HEAD(self):
        self._handle("HEAD")  # through _allowed() like everything else

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")


def main():
    url = f"http://localhost:{PORT}"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        # Already running - just bring the page up.
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)
        return
    init_db()
    print(f"Care Incident Log running at {url}")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
