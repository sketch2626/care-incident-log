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
import time
import webbrowser
from contextlib import closing
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import assist
import mary
import memory_core  # M9c
import power
import skills_core  # --- skills hook (M13) ---
import voices
import wakeword  # M6: "Hey Mary" (opens nothing until a Mary page asks)

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
                "companion", "voice_rate", "voice_volume", "andyflow_enabled",
                "voice_mary", "voice_sam"}  # the last two: the voice the resident picked in the audition
# Mary's voice settings: (lowest, highest, default). Saved values are clamped into range.
VOICE_LIMITS = {"voice_rate": (0.6, 1.4, 0.92), "voice_volume": (0.2, 1.0, 1.0)}
# M4a: how Mary's own screen talks (Live, Normal or Offline), and how many seconds of quiet end the resident's turn.
TALK_MODES = ("live", "normal", "offline")
VOICE_LIMITS["listen_wait"] = (1.5, 6.0, 2.5)  # M4a: clamped like the other voice settings
SETTING_KEYS |= {"talk_mode", "listen_wait"}  # M4a
SETTING_KEYS |= {"talk_on_open"}  # M4a: '1' (default) = she says hello and listens when her screen opens; '0' = she waits
SETTING_KEYS |= {"wake_word"}  # M6: '1' (default) = "Hey Mary" / "Hey Sam" wakes her while her screen is open; '0' = off
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
        conn.executescript(memory_core.MEMORIES_SCHEMA)  # M9c
        if "formal_summary" not in {r["name"] for r in conn.execute("PRAGMA table_info(incidents)")}:
            conn.execute("ALTER TABLE incidents ADD COLUMN formal_summary TEXT NOT NULL DEFAULT ''")
        # The Andy Flow link is the resident's choice and starts off. A log that already holds entries
        # imported from Andy Flow was connected before this setting existed, so it keeps the link, once.
        if "andyflow_enabled" not in get_settings(conn) and conn.execute(
                "SELECT 1 FROM incidents WHERE source LIKE 'andyflow-%' LIMIT 1").fetchone():
            conn.execute("INSERT INTO settings (key, value) VALUES ('andyflow_enabled', '1')")
        memory_core.migrate_json(DATA / "mary" / "memory.json", conn)  # M9c: once only, by settings key memories_moved
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
    memory = mary.Memory(DATA / "mary" / "memory.json")
    memory.store = memory_core.MemoryStore(connect)  # M9c
    return memory


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
    mode = str(s.get("talk_mode") or "").strip().lower()  # M4a: the saved talk mode, Live when none is saved
    out["talk_mode"] = mode if mode in TALK_MODES else "live"
    out["talk_on_open"] = str(s.get("talk_on_open", "1")).strip() != "0"  # M4a: on unless turned off
    out["wake_word"] = str(s.get("wake_word", "1")).strip() != "0"  # M6: on unless turned off
    return out


def mary_status():
    s = mary_settings()
    name = mary_memory().name
    offline_ready = voices.kokoro_ready()  # M4a
    return {"companion": s["companion"], "first_run": not s["companion"],
            "companions": mary.COMPANIONS, "has_key": bool(s["key"]), "name": name,
            "voice_rate": s["voice_rate"], "voice_volume": s["voice_volume"],
            # M4a: talk modes, the order the page tries them in, and the voice for each
            "talk_mode": s["talk_mode"], "listen_wait": s["listen_wait"], "talk_on_open": s["talk_on_open"],
            "talk_order": talk_order(s["talk_mode"], bool(s["key"]), offline_ready), "offline_ready": offline_ready,
            "voices": companion_voices(s["companion"] or "mary"),
            "tts_spent": voices.tts_spent(DATA),  # M4a: for information; /api/mary/say swaps to Kokoro by itself
            "wake_word": s["wake_word"], "wake_ready": wakeword.available()[0]}  # M6


# --- M4a: talk modes and the voices for each ---
def talk_order(mode, has_key, offline_ready):
    """The talk modes Mary's screen tries, best first. Live and Normal need the Gemini key; Offline needs the
    Kokoro voice installed. The page's last resort is always the computer's built-in voice, so [] is allowed."""
    order = {"normal": ["normal", "offline"], "offline": ["offline"]}.get(mode, ["live", "normal", "offline"])
    return [m for m in order if (offline_ready if m == "offline" else has_key)]


def _first_voice(table, companion):
    """The first voice of the companion's gender in GEMINI_VOICES or KOKORO_VOICES (Mary female, Sam male)."""
    gender = "male" if companion == "him" else "female"
    return next(n for n, g, _ in table if g == gender)


def companion_voices(companion, saved=None):
    """The voices Mary (or Sam) uses: {"live": <Live voice name>, "tts": "gemini:<name>", "offline": "kokoro:<name>"
    or "" when the offline voice isn't installed}. A live:/gemini: pick sets live and tts; a kokoro: pick sets the
    offline voice; anything not picked uses the companion's default."""
    if saved is None:
        saved = _all_settings()
    picked = str(saved.get("voice_sam" if companion == "him" else "voice_mary") or "").strip()
    kind, _, name = picked.partition(":")
    gemini, kokoro = _first_voice(voices.GEMINI_VOICES, companion), _first_voice(voices.KOKORO_VOICES, companion)
    if voices.valid_choice(picked):
        if kind in ("live", "gemini"):
            gemini = name
        elif kind == "kokoro":
            kokoro = name
    return {"live": gemini, "tts": f"gemini:{gemini}",
            "offline": f"kokoro:{kokoro}" if voices.kokoro_ready() else ""}
# --- end M4a ---


# M9b: what Mary and Sam are told about their own app, so they never guess about their voice or the Talk button.
MARY_VOICE_NOW = "picked"  # M4a: her screen speaks with the voice picked in the tryout (Live, Normal or Offline)
MARY_TALK_MODE = "handsfree"  # M4a: she and the resident talk back and forth without pressing Talk


def mary_app_facts(companion):
    """Live facts about her app for her system prompt: the voice, talk mode, and the voice the resident picked."""
    s = mary_settings()
    with closing(connect()) as conn:
        saved = get_settings(conn)
    picked = str(saved.get("voice_sam" if companion == "him" else "voice_mary") or "").strip()
    voice = about = ""
    if voices.valid_choice(picked):  # M4a: the voice she really uses in the saved talk mode (facts only reach
        cv = companion_voices(companion, saved)  # Gemini, so a key is there); nothing picked: say nothing
        order = talk_order(s["talk_mode"], True, bool(cv["offline"]))
        if order and order[0] == "offline":
            name = cv["offline"].partition(":")[2]
            for n, _g, a in voices.KOKORO_VOICES:
                if n == name:
                    voice, about = "the offline voice", a
        elif order:
            for n, _g, a in voices.GEMINI_VOICES:
                if n == cv["live"]:
                    voice, about = n, a
    return {"voice_now": MARY_VOICE_NOW, "talk_mode": MARY_TALK_MODE, "picked_voice": voice, "picked_about": about,
            "voice_rate": s["voice_rate"], "voice_volume": s["voice_volume"],
            "talk_choice": s["talk_mode"],  # M4a: Live, Normal or Offline, as saved
            "talk_on_open": s["talk_on_open"],  # M4a: she starts talking when her screen opens
            "wake_word": s["wake_word"] and wakeword.available()[0]}  # M6; M4a: only when it can really run here


mary.app_facts = mary_app_facts  # M9b: Mary's live facts about her own app


# The voice audition page (/mary/voices.html).
VOICE_ERRORS = {  # kind -> (plain sentence, HTTP status)
    "no_key": ("Mary needs her Gemini key first. You can add it in My info.", 400),
    "bad_key": ("Google didn't accept the Gemini key. Please check it in My info.", 400),
    "no_gemini": ("I couldn't reach Gemini just now. Please try again in a moment.", 502),
    "unknown_voice": ("I don't know that voice.", 400),
    "no_offline": ("The offline voice isn't installed on this computer yet.", 503),
    "busy": ("Gemini's free limit is used up for now. Please try again in a few minutes.", 503),
    "tts_spent": ("The Gemini voice has used up its free turns for today. It will be back tomorrow.", 503),  # M4a
}


def voice_failure(kind):
    """(JSON body, status) for a failed voice call. No key, URL or Google reply text is ever included."""
    text, status = VOICE_ERRORS.get(kind, VOICE_ERRORS["no_gemini"])
    return {"error": text, "bad_key": kind == "bad_key", "no_key": kind == "no_key"}, status


def mary_voices():
    s = mary_settings()
    with closing(connect()) as conn:
        saved = get_settings(conn)
    return {"line": voices.LINE, "tts_model": voices.TTS_MODEL, "candidates": voices.candidates(),
            "live": {"model": voices.LIVE_MODEL, "voices": voices.live_choices()},
            "chosen": {"mary": saved.get("voice_mary", ""), "him": saved.get("voice_sam", "")},
            "has_key": bool(s["key"])}


def mary_write_incident(incident):
    """The resident said yes to 'Would you like me to write that down?': log her guess. Returns the new id."""
    with closing(connect()) as conn:
        new_id = insert_incident(conn, clean_incident({**incident, "source": "mary"}))
        conn.commit()
    backup_db()  # Mary's window stays open for days: her first save of a day makes that day's backup
    return new_id


# --- skills hook (M13) --- Mary's skills (docs/skills-design.md), loaded once on first use.
SKILLS_DIR = Path(os.environ.get("TRACKER_SKILLS") or ROOT / "skills")  # a missing folder means no skills
SKILL_UNKNOWN = "Mary doesn't know that skill."
SKILL_SETTINGS = {"skills_off", "skills_on", "skills_locked"}  # only the skill routes change these
_skill_host = None
_skill_host_lock = threading.Lock()


def _all_settings():
    with closing(connect()) as conn:
        return get_settings(conn)


def _put_settings(values):
    with closing(connect()) as conn:
        conn.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                         [(k, str(v)) for k, v in values.items()])
        conn.commit()
    if "wake_word" in values or "companion" in values:  # M6: a skill turned listening for the name on/off
        try:
            WAKE.settings_changed()
        except Exception as e:  # never let this fail a skill
            wake_log("error", where="_put_settings", msg=str(e)[:120])


def skill_host():
    """The one SkillHost, loaded on first use. Offline phrases may not be emergency or yes/no words."""
    global _skill_host
    with _skill_host_lock:
        if _skill_host is None:
            host = skills_core.SkillHost(SKILLS_DIR, DATA, connect, _all_settings, _put_settings, online=lambda: True)
            host.load(is_blocked=mary.skill_blocked)
            _skill_host = host
        return _skill_host


def set_skill_host_for_tests(host):
    """Tests swap in their own host (None: load SKILLS_DIR again on next use)."""
    global _skill_host
    with _skill_host_lock:
        _skill_host = host


def mary_live_skill_setup(screen=None):
    """What live_token() adds to bidiGenerateContentSetup (tools) and to the system text; wired when Mary's own
    Live session is built (M4)."""
    return {"tools": skill_host().gemini_tools(), "instruction": skill_host().instruction_text(screen)}
# --- end skills hook ---


def mary_live_memory_call(name, args, heard=""):  # M4a: Live's remember_fact and set_their_name tools; M9c: recall too
    """Saves what one of Live's memory tools asked for, or runs recall or forget_memory (M9c). The same shape as a skill
    call's result. heard is what Live heard, which says whether they asked her to remember (M9c)."""
    args = args if isinstance(args, dict) else {}
    if name in mary.MEMORY_TOOL_NAMES:  # M9c
        with _mary_lock:
            return mary.memory_tool(mary_memory(), name, args)
    if name == "set_their_name":
        value = mary.clean_name(args.get("name"))
        error = "" if value else "That isn't a name. If it's a pet name they like, save it with remember_fact."
    else:
        value = " ".join(str(args.get("fact") or "").split())
        error = "" if value else "There was no fact to save."
    if error:
        return {"response": {"ok": False, "error": error}, "effects": [], "say": None}
    with _mary_lock:
        memory = mary_memory()
        try:
            if name == "set_their_name":
                memory.name = value
            else:
                memory.add_fact(value, str(args.get("kind") or ""), mary.fact_source(heard))  # M9c
            memory.save()
        except (OSError, sqlite3.Error):  # M9c: the store writes to the database
            return {"response": {"ok": False, "error": "It could not be saved just now."}, "effects": [], "say": None}
    return {"response": {"ok": True}, "effects": [], "say": None}


STORY_FAILED = {"error": "no_story",  # M4a
                "note": "Tell a short story yourself instead, with a beginning, middle and end."}


def mary_live_story_call(args):  # M4a: Live's tell_story tool
    """A well-made story from the same brain as Normal talk, for Live to tell aloud. The lock is held only while
    her memory is read, never while Gemini writes."""
    args = args if isinstance(args, dict) else {}
    s = mary_settings()
    with _mary_lock:
        memory = mary_memory()
    info = {}
    story = mary.tell_story(args.get("request"), memory, s["key"], s["model"], s["companion"] or "mary", report=info)
    voices.log({"event": "story", "ok": bool(story), **info}, DATA)  # here: voices imports mary, not the reverse
    return {"response": {"story": story} if story else dict(STORY_FAILED), "effects": [], "say": None}


def mary_talk(text, on_text=None, on_mood=None, screen=None, on_effect=None, typed=False):  # M9c: typed
    """Mary's answer to text, for the page. Never contains the key."""
    s = mary_settings()
    skills = skill_host()  # --- skills hook (M13) ---
    with _mary_lock:
        r = mary.reply(text, mary_memory(), s["key"], s["model"], on_text=on_text,
                       companion=s["companion"] or "mary", on_mood=on_mood, write=mary_write_incident,
                       skills=skills, screen=screen, on_effect=on_effect, typed=typed)  # --- skills hook (M13) --- M9c: typed
    return {"text": r["text"], "mood": r["mood"], "effects": r["effects"],  # effects: M13
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


# --- M6: "Hey Mary" / "Hey Sam" wake word -------------------------------------------------------------
# The microphone is only used while a Mary page is open: the page long-polls GET /api/wake/wait, the first poll
# starts the listener, and a watchdog lets go of the microphone when no poll has come for WAKE_LEASE_S.
WAKE_WAIT_S = 20.0         # one long-poll of GET /api/wake/wait
WAKE_LEASE_S = 45.0        # no poll for this long: the page is gone, so the microphone is let go
WAKE_HOLD_S = 90.0         # a page hold ends by itself unless renewed (the page renews it every 30 s)
WAKE_WOKE_S = 10.0         # after a wake she is not listening for her name (so her own greeting cannot wake her)
WAKE_TICK_S = 0.5          # how often the watchdog looks
WAKE_LOG_MAX = 512 * 1024  # wake.log becomes wake.log.1 (the one old copy) when bigger than this
_wake_log_lock = threading.Lock()


def wake_log(kind, **fields):
    """One line in DATA/wake.log: time, kind, then the fields given (text quoted). Never audio; never raises."""
    try:
        parts = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), kind]
        for k, v in fields.items():
            if v is not None and v != "":
                parts.append(f"{k}={json.dumps(v, ensure_ascii=False) if isinstance(v, str) else v}")
        line = "  ".join(parts) + "\n"
        path = DATA / "wake.log"
        with _wake_log_lock:
            try:
                if path.stat().st_size > WAKE_LOG_MAX:
                    os.replace(path, DATA / "wake.log.1")
            except OSError:
                pass
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


class WakeLink:
    """Runs the wake word for the Mary page: the poll lease, the page hold, the pause after a wake and the
    event stream the page reads ("heard" the moment Vosk hears the name, "wake" once Whisper agrees).

    Locks: _ctl (one start/stop at a time) is never taken by a wakeword callback. _cond may be held while calling
    wakeword.pause()/resume() (they never call back into here), but never around wakeword.start()/stop(): stop()
    joins the worker thread, and the worker's callbacks take _cond."""

    def __init__(self):
        self._cond = threading.Condition()
        self._ctl = threading.Lock()
        self._seq = 1              # every event for the page gets the next number (from 1: a page never sends 0 twice)
        self._event = None         # the newest event
        self._polled = 0.0         # monotonic time a poll last started or ended
        self._waiting = 0          # polls waiting right now (a waiting page is still there)
        self._started = False      # this server started the listener
        self._off = False          # the setting was turned off: waiting polls answer at once
        self._hold_until = 0.0     # the page hold ("page" pause) ends then; 0 = no hold
        self._woke_until = 0.0     # the pause after a wake ("woke") ends then; 0 = none
        self._watch = None         # the watchdog thread while there is something to watch
        self._problem = None       # the last problem written to wake.log

    # ---- routes ----
    def wait(self, after):
        """GET /api/wake/wait?after=<seq>: the newest event with seq > after, or none after WAKE_WAIT_S.
        after 0 (or a number this server never gave out) means "from now"."""
        s = mary_settings()
        if not s["wake_word"]:
            self.stop("setting off", off=True)
            return self._reply(None, s)
        if not wakeword.available()[0]:
            return self._reply(None, s)  # nothing to listen with: status.ready is false, the page stops asking
        with self._cond:
            self._off = False
            self._waiting += 1
            self._polled = time.monotonic()
        try:
            self._ensure_started(s["companion"])
            deadline = time.monotonic() + WAKE_WAIT_S
            with self._cond:
                if after <= 0 or after > self._seq:
                    after = self._seq
                while self._seq <= after and not self._off:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._cond.wait(remaining)
                event = dict(self._event) if self._event and self._event["seq"] > after else None
        finally:
            with self._cond:
                self._waiting -= 1
                self._polled = time.monotonic()
        return self._reply(event, s)

    def hold(self, on):
        """POST /api/wake/hold {"on": true|false}: hold the wake word while she talks, listens or thinks, or while
        a Live session uses the browser's microphone. Either way the pause after a wake ends now."""
        with self._cond:
            self._hold_until = time.monotonic() + WAKE_HOLD_S if on else 0.0
            (wakeword.pause if on else wakeword.resume)("page")
            if self._woke_until:
                self._woke_until = 0.0
                wakeword.resume("woke")
        if on:
            self._ensure_watch()
        return {"ok": True, "held": bool(on), "hold_s": WAKE_HOLD_S if on else 0, "status": self.status()}

    def status(self, s=None):
        """GET /api/wake/status: wakeword.status() plus the setting, whether it can run here, and this link."""
        s = s or mary_settings()
        ready, reason = wakeword.available()
        out = wakeword.status()
        with self._cond:
            out.update({"wake_word": s["wake_word"], "ready": ready, "reason": reason,
                        "phrase": "Hey Sam" if s["companion"] == "him" else "Hey Mary",
                        "page": self._started, "held": bool(self._hold_until), "woke": bool(self._woke_until)})
        return out

    def settings_changed(self):
        """PUT /api/settings changed wake_word or companion."""
        s = mary_settings()
        if not s["wake_word"]:
            self.stop("setting off", off=True)
        else:
            wakeword.set_companion(s["companion"])  # only the chosen companion's name wakes

    def stop(self, why, off=False, lease=False):
        """Stop listening and let go of the microphone. lease=True: only if still no poll came (watchdog)."""
        with self._ctl:
            with self._cond:
                if lease and not self._lease_over():
                    return
                was, self._started = self._started, False
                if off:
                    self._off = True
                self._cond.notify_all()
            if was:
                wakeword.stop()
                wake_log("stop", why=why)
            with self._cond:
                if self._hold_until or self._woke_until or was:
                    self._hold_until = self._woke_until = 0.0
                    wakeword.resume("page")
                    wakeword.resume("woke")

    # ---- inside ----
    def _reply(self, event, s):
        with self._cond:
            seq, off = self._seq, self._off or not s["wake_word"]
        return {"seq": seq, "event": event, "off": off, "status": self.status(s)}

    def _lease_over(self):
        return self._started and self._waiting == 0 and time.monotonic() - self._polled > WAKE_LEASE_S

    def _ensure_started(self, companion):
        wakeword.set_companion(companion)
        with self._ctl:
            if self._started:
                return
            try:
                wakeword.start(on_wake=self._on_wake, on_note=self._on_note)
            except Exception as e:  # not set up here: a plain message for status and the log
                self._log_problem(str(e) if isinstance(e, RuntimeError) else "could not start")
                return
            with self._cond:
                self._started = True
                self._problem = None
            wake_log("start", name="sam" if companion == "him" else "mary")
        self._ensure_watch()

    def _publish(self, kind, ev):
        """Caller holds _cond."""
        self._seq += 1
        self._event = {"type": kind, "name": ev.get("name"), "seq": self._seq, "time": ev.get("time"),
                       "companion": ev.get("companion")}
        self._cond.notify_all()

    def _on_wake(self, ev):  # wakeword's worker thread, no wakeword lock held
        with self._cond:
            self._woke_until = time.monotonic() + WAKE_WOKE_S
            wakeword.pause("woke")  # she must not wake on her own greeting
            self._publish("wake", ev)
        wake_log("wake", name=ev.get("name"), vosk=ev.get("stage1_text"), whisper=ev.get("confirm_text"),
                 ms=ev.get("confirm_ms"))
        self._ensure_watch()

    def _on_note(self, note):  # wakeword's worker thread, no wakeword lock held
        if note.get("type") == "heard":
            with self._cond:
                self._publish("heard", note)
        elif note.get("type") == "almost":
            wake_log("almost", name=note.get("name"), vosk=note.get("stage1_text"),
                     whisper=note.get("confirm_text"), ms=note.get("confirm_ms"))

    def _log_problem(self, problem):
        with self._cond:
            if problem == self._problem:
                return
            self._problem = problem
        if problem:
            wake_log("problem", text=problem)

    def _ensure_watch(self):
        with self._cond:
            if self._watch is None:
                self._watch = threading.Thread(target=self._watchdog, name="care-wake-watch", daemon=True)
                self._watch.start()

    def _watchdog(self):
        while True:
            time.sleep(WAKE_TICK_S)
            try:
                now = time.monotonic()
                with self._cond:
                    if self._hold_until and now >= self._hold_until:  # a page that stopped renewing its hold
                        self._hold_until = 0.0
                        wakeword.resume("page")
                    if self._woke_until and now >= self._woke_until:
                        self._woke_until = 0.0
                        wakeword.resume("woke")
                    lease_over, started = self._lease_over(), self._started
                    if not (started or self._hold_until or self._woke_until):
                        self._watch = None  # nothing left to watch; the next poll or hold starts a new one
                        return
                if lease_over:
                    self.stop(f"no Mary page for {WAKE_LEASE_S:g} s", lease=True)
                elif started:
                    self._log_problem(wakeword.status().get("problem"))
            except Exception:
                time.sleep(WAKE_TICK_S)  # keep watching; never take the server down


WAKE = WakeLink()


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".woff2": "font/woff2"}  # M4b: Mary's caption font

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
            screen = body.get("screen") if isinstance(body.get("screen"), str) else None  # --- skills hook (M13) ---
            typed = body.get("typed") is True  # M9c
            if q("stream") == "1":
                return self._mary_stream(text, screen, typed)
            return self._send(mary_talk(text, screen=screen, typed=typed))
        if method == "GET" and path == "/api/mary/voices":
            return self._send(mary_voices())
        if method == "POST" and path in ("/api/mary/voices/sample", "/api/mary/live/token"):
            body = self._body()
            key = mary_settings()["key"]
            offline = path.endswith("/sample") and str(body.get("id") or "").strip().startswith("kokoro:")
            if not key and not offline:  # the offline voice needs no Gemini key
                return self._send(*voice_failure("no_key"))
            try:
                if offline:
                    got = voices.kokoro_sample(str(body.get("id") or ""), DATA)
                elif path.endswith("/sample"):
                    got = voices.tts_sample(str(body.get("id") or ""), key, DATA)
                else:
                    companion = str(body.get("companion") or "")  # try a voice as Mary or as Sam
                    if companion not in mary.COMPANIONS:
                        companion = mary_settings()["companion"] or "mary"
                    got = voices.live_token(str(body.get("voice") or ""), key, companion, mary_memory().name, DATA)
            except voices.VoiceError as e:
                return self._send(*voice_failure(e.kind))
            if not path.endswith("/sample"):
                return self._send(got)
            headers = {
                "X-First-Sound-Ms": str(got["first_sound_ms"]), "X-Total-Ms": str(got["total_ms"]),
                "X-Audio-S": str(got["audio_s"]), "X-Cached": "1" if got["cached"] else "0",
                "X-Word-Timings": "1" if got["word_timings"] else "0", "X-Voice-Path": got["path"]}
            if "rtf" in got:
                headers["X-Rtf"] = str(got["rtf"])
            return self._send(got["wav"], 200, "audio/wav", headers)
        if method == "POST" and path == "/api/mary/voices/stream":
            body = self._body()
            voice_id = str(body.get("id") or "")
            text = voices.LINES.get(str(body.get("line") or ""), voices.LINE)  # only our own lines, never page text
            offline = voice_id.strip().startswith("kokoro:")
            key = mary_settings()["key"]
            if not key and not offline:  # the offline voice needs no Gemini key
                return self._send(*voice_failure("no_key"))
            return self._voice_stream(voice_id, key, offline, text)
        if method == "POST" and path == "/api/mary/voices/log":
            body = self._body()  # the page's numbers; only whitelisted keys are kept
            voices.log({**body, "event": "played" if body.get("event") == "played" else "live"}, DATA)
            return self._send({"ok": True})
        # --- M4a: Mary's own screen: a Live chat, the emergency check on what Live heard, and speaking her replies ---
        if method == "POST" and path == "/api/mary/live/start":
            body = self._body()
            s = mary_settings()
            if not s["key"]:
                return self._send(*voice_failure("no_key"))
            companion = s["companion"] or "mary"
            screen = body.get("screen") if isinstance(body.get("screen"), str) else None
            try:
                skills = mary_live_skill_setup(screen)
            except Exception:
                skills = None  # a skills failure never stops Live
            with _mary_lock:
                memory = mary_memory()
            try:
                got = voices.live_token(companion_voices(companion)["live"], s["key"], companion, memory.name, DATA,
                                        skills=skills, silence_ms=round(s["listen_wait"] * 1000), memory=memory,
                                        rate=s["voice_rate"], plain=bool(body.get("plain")))  # M4a: rate, plain
            except voices.VoiceError as e:
                return self._send(*voice_failure(e.kind))
            return self._send({**got, "companion": companion})
        if method == "POST" and path == "/api/mary/heard":
            # The same emergency check as Normal talk, on Live's transcript of what the resident said.
            text = str(self._body().get("text") or "")[:2000]
            kind = mary.is_emergency(text) or ""
            say = mary.EMERGENCY_TEXT.get(kind, "") if kind else ""
            if not kind and mary.not_english(text):  # M4a: a garbled transcript teaches her nothing; an emergency stands
                return self._send({"emergency": False, "kind": "", "say": "", "garbled": True})
            if kind or text.strip():  # M4a: every resident turn is remembered (once), as in Normal talk
                with _mary_lock:  # as in Normal talk: the emergency cancels a waiting offer and is remembered
                    memory = mary_memory()
                    if kind:
                        memory.pending_offer = None
                    else:
                        mary.learn_name(memory, text)  # M4a: "call me Andy" works even if Live skips the tool
                    memory.add_turn("user", text.strip())
                    if say:
                        memory.add_turn("model", say)
                    try:
                        memory.save()
                    except OSError:
                        pass
            return self._send({"emergency": bool(kind), "kind": kind, "say": say})
        if method == "POST" and path == "/api/mary/live/said":  # M4a: her finished Live turn, remembered
            text = " ".join(str(self._body().get("text") or "").split())[:2000]
            if text and not mary.not_english(text):  # M4a: her turn in a foreign script is noise too
                with _mary_lock:
                    memory = mary_memory()
                    memory.add_turn("model", text)
                    try:
                        memory.save()
                    except OSError:
                        pass
            return self._send({"ok": True})
        if method == "POST" and path == "/api/mary/say":
            # Mary's reply spoken in Normal (Gemini voice) or Offline (Kokoro) mode, streamed like the tryout.
            body = self._body()
            text = str(body.get("text") or "").strip()[:2000]
            if not text:
                raise ValueError(TALK_NO_TEXT)
            mode = body.get("mode")
            if mode not in ("normal", "offline"):
                raise ValueError(BAD_REQUEST)
            s = mary_settings()
            lo, hi, _ = VOICE_LIMITS["voice_rate"]  # M4a: real speed without a pitch change
            try:
                rate = min(hi, max(lo, float(body["rate"]))) if body.get("rate") is not None else s["voice_rate"]
            except (TypeError, ValueError):
                rate = s["voice_rate"]
            companion = s["companion"] or "mary"
            cv = companion_voices(companion)
            offline_voice = cv["offline"] or f"kokoro:{_first_voice(voices.KOKORO_VOICES, companion)}"
            if mode == "offline":
                return self._voice_stream(offline_voice, "", True, text, speed=rate)
            if not s["key"]:
                return self._send(*voice_failure("no_key"))
            if voices.tts_spent(DATA):  # M4a: the Gemini voice's daily limit is used up
                return self._kokoro_for_spent(offline_voice, text, rate)
            return self._voice_stream(cv["tts"], s["key"], False, text, cache=False, pace=rate,  # replies never pile up on disk
                                      spent_voice=offline_voice)  # M4a: the request that hits the limit swaps too
        # --- end M4a ---
        if method == "GET" and path == "/api/mary/memories":  # M9c: the page's list; no lock, each store call stands alone
            found = memory_core.MemoryStore(connect).active()
            return self._send({"memories": [memory_core.public(m) for m in found], "count": len(found)})
        m = re.fullmatch(r"/api/mary/memories/(\d+)", path)  # M9c
        if m and method == "DELETE":
            if not memory_core.MemoryStore(connect).remove(m.group(1)):
                return self._send({"error": "That memory isn't here."}, 404)
            return self._send({"ok": True})
        if path == "/api/mary/skills" or path.startswith("/api/mary/skills/"):  # --- skills hook (M13) ---
            return self._skills(method, path)
        return None

    # --- skills hook (M13) ---
    def _skills(self, method, path):
        """Mary's skill routes. An unknown skill is a 404 with a plain sentence."""
        host = skill_host()
        if method == "GET" and path == "/api/mary/skills":
            out = host.list_skills()
            for s in out:
                folder = host.skills[s["name"]].folder
                s["script"], s["style"] = ((f"/skills/{s['name']}/{f}" if (folder / f).is_file() else None)
                                           for f in ("screen.js", "screen.css"))
            return self._send({"skills": out})
        if method == "POST" and path == "/api/mary/skills/call":  # Live mode's tool calls
            body = self._body()
            heard = body.get("heard")  # M4a: what Live heard; an emergency line never runs a tool
            if isinstance(heard, str) and mary.is_emergency(heard[:2000]):
                return self._send({"response": {"error": "emergency"}, "effects": [], "say": "",
                                   "ok": False, "emergency": True})
            name = str(body.get("name") or "")
            if name in ("remember_fact", "set_their_name") + mary.MEMORY_TOOL_NAMES:  # M4a: Live's own memory tools, not a skill
                return self._send(mary_live_memory_call(name, body.get("args"),  # M9c: recall stays below the emergency gate
                                                        heard[:2000] if isinstance(heard, str) else ""))
            if name in ("story_more", "end_talk"):  # M4a: the page answers these two; they should never reach here
                return self._send({"response": {"error": "not_here"}, "effects": [], "say": None})
            if name == "tell_story":  # M4a: Live's story tool, after the emergency gate above
                return self._send(mary_live_story_call(body.get("args")))
            return self._send(host.call(name, body.get("args")))
        m = re.fullmatch(r"/api/mary/skills/([^/]+)/image/([a-z0-9_-]{1,40}\.(jpg|png|gif|webp))", path)
        if m and method == "GET":  # an image a skill saved in its own ctx.files (any skill, images only)
            try:
                data = (skills_core.SkillFiles(Path(host.data_dir) / "skills" / m.group(1)).read_bytes(m.group(2))
                        if m.group(1) in host.skills else None)
            except (OSError, skills_core.SkillError):
                data = None
            if data is None:
                return self._send({"error": "That picture isn't here."}, 404)
            ctype = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}[m.group(3)]
            return self._send(data, 200, ctype, {"X-Content-Type-Options": "nosniff"})  # end_headers adds no-store
        m = re.fullmatch(r"/api/mary/skills/([^/]+)(/event|/broken|/view|/lock)?", path)
        if not m:
            return None
        name, action = m.group(1), m.group(2) or ""
        if name not in host.skills:
            return self._send({"error": SKILL_UNKNOWN}, 404)
        if method == "POST" and action == "/event":
            return self._send(host.on_event(name, self._body().get("event")))
        if method == "POST" and action == "/broken":
            return self._send(host.broken(name))
        if method == "GET" and action == "/view":
            return self._send({"text": host.view(name) or ""})
        if method == "PUT" and action == "":
            on = self._body().get("on")
            if not isinstance(on, bool):
                raise ValueError(BAD_REQUEST)
            return self._send(host.set_skill(name, on, by="resident"))
        if method == "PUT" and action == "/lock":  # the helper's lock, from My info
            state = self._body().get("state")
            if state not in ("on", "off", None):
                raise ValueError(BAD_REQUEST)
            return self._send({"ok": True, "locked": host.lock(name, state).get(name), "on": host.enabled(name)})
        return None

    def _skill_file(self, method):
        """GET /skills/<name>/screen.js|screen.css: only a loaded skill's two page files, nothing else."""
        if method != "GET":
            return self.send_error(405)
        m = re.fullmatch(r"/skills/([a-z][a-z0-9_]{1,30})/(screen\.js|screen\.css)", urlparse(self.path).path)
        try:
            host = skill_host()
            path = host.skills[m.group(1)].folder / m.group(2) if m and m.group(1) in host.skills else None
            data = path.read_bytes() if path is not None and path.is_file() else None
        except OSError:
            data = None
        if data is None:
            return self._send({"error": SKILL_UNKNOWN}, 404)
        ctype = "text/javascript; charset=utf-8" if m.group(2).endswith(".js") else "text/css; charset=utf-8"
        return self._send(data, 200, ctype)
    # --- end skills hook ---

    def _kokoro_for_spent(self, voice_id, text, speed):  # M4a
        """Speak in Kokoro because the Gemini voice is spent for today. If Kokoro isn't here this is the usual
        failure, and the page falls on to the computer's voice."""
        voices.log({"event": "say", "id": voice_id, "note": "Gemini voice spent for today, using Kokoro"}, DATA)
        return self._voice_stream(voice_id, "", True, text, speed=speed)

    def _voice_stream(self, voice_id, key, offline, text=voices.LINE, cache=True, speed=1.0, pace=None,
                      spent_voice=None):  # M4a: speed, pace, spent_voice
        """One voice sample as raw 16-bit PCM, sent as it is made so the page can play it at once. Nothing is
        sent until the first audio is ready, so a failure is still a plain JSON answer. No Content-Length: the
        connection closing ends it (HTTP/1.0). cache=False (M4a): a Gemini reply is never saved or reused.
        spent_voice (M4a): the Kokoro voice to swap to if this is the request that finds the daily limit used up."""
        gen = (voices.kokoro_stream(voice_id, DATA, text=text, speed=speed) if offline
               else voices.tts_stream(voice_id, key, DATA, text=text, cache=cache, pace=pace))  # cache: M4a
        try:
            first = next(gen)
        except voices.VoiceError as e:
            if e.kind == "tts_spent" and spent_voice:  # M4a: nothing has been sent yet, so the page never knows
                return self._kokoro_for_spent(spent_voice, text, pace or speed)
            return self._send(*voice_failure(e.kind))
        except StopIteration:
            return self._send(*voice_failure("no_offline" if offline else "no_gemini"))
        self.send_response(200)
        self.send_header("Content-Type", "audio/L16")
        self.send_header("X-Rate", str(first["rate"]))
        self.send_header("X-Channels", str(first["channels"]))
        self.send_header("X-Cached", "1" if first.get("cached") else "0")
        self.send_header("X-Voice-Path", str(first.get("path", "")))
        self.send_header("X-Mary-Voice", "offline" if offline else "normal")  # M4a: the page learns of a Kokoro swap
        if "load_ms" in first:
            self.send_header("X-Load-Ms", str(first["load_ms"]))
        self.end_headers()
        try:
            self.wfile.write(first["pcm"])
            self.wfile.flush()
            for chunk in gen:
                self.wfile.write(chunk["pcm"])
                self.wfile.flush()
        except (OSError, ValueError):
            pass  # the page went away
        except voices.VoiceError:
            pass  # failed part-way: it is logged, and the page keeps the short audio it has
        finally:
            gen.close()  # a stopped sample is logged and never saved
        return True

    def _mary_stream(self, text, screen=None, typed=False):  # M9c: typed
        """Mary's answer as it happens: one JSON line per event (mood, text pieces, skill effects, then done).
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
                             on_mood=lambda mood: line({"mood": mood}),
                             screen=screen, on_effect=lambda effect: line({"effect": effect}),  # skills hook (M13)
                             typed=typed)  # M9c
        except Exception:
            line({"error": "Something went wrong. Please try again."})
            return True
        line({"done": True, **done})
        return True

    def _wake(self, method, path, q):
        """M6: the wake word routes (see WakeLink)."""
        if method == "GET" and path == "/api/wake/wait":
            try:
                after = int(q("after") or 0)
            except ValueError:
                after = 0
            return self._send(WAKE.wait(after))
        if method == "GET" and path == "/api/wake/status":
            return self._send(WAKE.status())
        if method == "POST" and path == "/api/wake/hold":
            on = str(self._body().get("on")).strip().lower() in ("1", "true", "yes", "on")
            return self._send(WAKE.hold(on))
        return None

    def _route(self, method):
        parsed = urlparse(self.path)
        path, query = parsed.path.rstrip("/"), parse_qs(parsed.query)
        q = lambda k: (query.get(k) or [""])[0]
        m = re.fullmatch(r"/api/incidents/(\d+)", path)
        if method == "GET" and path == "/api/power":
            return self._send({"plugged_in": power.plugged_in()})
        if path.startswith("/api/mary/"):
            return self._mary(method, path, q)
        if path.startswith("/api/wake/"):  # M6
            return self._wake(method, path, q)
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
                body = self._body()
                for k, v in body.items():
                    if k in SKILL_SETTINGS:
                        continue  # --- skills hook (M13) --- only the skill routes change these
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
                    if k in ("voice_mary", "voice_sam"):
                        v = str(v).strip()
                        if v and not voices.valid_choice(v):
                            continue  # a known voice id, or blank to clear
                    if k == "talk_mode":  # M4a: live, normal or offline; anything else is ignored
                        v = str(v).strip().lower()
                        if v not in TALK_MODES:
                            continue
                    if k in ("talk_on_open", "wake_word"):  # M4a, M6: '1' or '0'; anything else is ignored
                        v = str(v).strip().lower()
                        v = "1" if v in ("1", "true", "yes", "on") else "0" if v in ("0", "false", "no", "off") else None
                        if v is None:
                            continue
                    if k == "andyflow_enabled":
                        v = "1" if str(v).strip().lower() in ("1", "true", "yes", "on") else "0"
                    if k in SETTING_KEYS:
                        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                                     (k, str(v).strip()))
                if "wake_word" in body or "companion" in body:  # M6: turned off, or a new name to listen for
                    conn.commit()
                    WAKE.settings_changed()
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
        if self.path.startswith("/skills/"):  # --- skills hook (M13) --- a skill's page files
            return self._skill_file(method)
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
            elif mutating and not self.path.startswith(("/api/mary/", "/api/wake/")):
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
