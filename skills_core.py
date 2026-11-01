"""Mary's skills core (M13, docs/skills-design.md): finds the skill folders, checks them and runs them safely.

Each skill is a folder in skills/ with a manifest.json card, a skill.py server half and an optional screen.js
page half. A skill reaches the rest of the app only through its ctx: its own store, its own state, its own
files folder, the settings keys its card lists, effects for the page, and an allow-listed ctx.fetch.
Every call into skill code runs in a guard, so a bug or a hang becomes {"error": "not_working"}, never a crash.
This is not a security sandbox: skills run in this process, so only reviewed skills shipped in this repo load.
Nothing here imports the server; the host gets its database, settings and online check from the caller.
"""
import ast
import contextlib
import importlib.util
import itertools
import json
import keyword
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import mail_core  # M15d: only for its plain words; skills may not import it
import memory_core  # M15c: what counts as "everything"; memory_core never imports this file
import printers  # M17: skills ask ctx.has_printer() and may not import it
import send_gate  # M15c: the hard-wired yes; skills may not import it

SUPPORTED_CONTRACTS = {1}

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")          # skill (folder) names
ACTION_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")        # action names; each is a def in skill.py
FUNCTION_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")        # Gemini function names
KIND_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")          # a skill's own effect kinds
SETTING_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
FONT_RE = re.compile(r"[a-z0-9-]+\.woff2")                # a bundled font, for ctx.font
_PROTECTED_SETTING = re.compile(r"key|token|secret|password|^skills_|^andyflow")
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

REQUIRED_FIELDS = ("contract", "name", "version", "title", "summary", "instructions", "actions",
                   "storage", "needs", "offline", "default_on")
OPTIONAL_FIELDS = ("screen", "sees", "settings", "slow", "vision", "memory")  # M4a: vision, M7a: memory
ACTION_KEYS = {"name", "description", "inputSchema", "annotations", "offline_phrases", "always"}  # M13b: always
MCP_ONLY_KEYS = {"annotations", "offline_phrases", "always"}  # M13b: always
SCREEN_KEYS = {"menu_label", "menu_icon", "full_screen"}
NEEDS_KEYS = {"internet_hosts", "mic", "modes", "send_mail"}  # M15d: send_mail
MODES = {"live", "normal", "offline"}
RESERVED_ACTIONS = {"view", "on_event", "set_skill", "open_skill", "use_skill"}  # M13b: open_skill, use_skill

SCHEMA_TYPES = {"object", "string", "integer", "number", "boolean", "array"}
SCHEMA_KEYS = {"type", "properties", "items", "enum", "required", "description", "maxLength", "minimum", "maximum"}

CORE_EFFECT_KINDS = {"show_screen", "leave_screen", "settings"}
FORBIDDEN_IMPORTS = {"server", "sqlite3", "mary", "assist", "subprocess", "ctypes", "multiprocessing", "importlib",
                     "urllib", "http", "requests", "httpx", "aiohttp", "socket", "ssl", "ftplib", "smtplib",
                     "websocket", "websockets", "skills_core",
                     "mail_core", "secret_store", "sys", "builtins", "gc", "inspect",  # M15d
                     "send_gate",  # M15c: it holds mail_core, and a skill must not reach that through it
                     "printers"}  # M17: ctx.has_printer() is the way in
FORBIDDEN_NAMES = {"open", "exec", "eval", "__import__", "__builtins__",
                   "mint_ticket", "vars", "__dict__", "__self__", "__globals__", "__getattribute__",  # M15d: from these on
                   "_host", "gate", "from_page"}  # M15c: a skill can't move a send, or say a move came from the page

TITLE_MAX = 40
SUMMARY_MAX = 200
INSTRUCTIONS_MAX = 400
DESCRIPTION_MAX = 200
TOTAL_INSTRUCTIONS_MAX = 4000
ALWAYS_SKILL_MAX = 4  # M13b: "always" actions on one skill's card
ALWAYS_MAX = 6  # M13b: across the host; only the first ones count
VIEW_MAX = 600
RESULT_MAX = 4096
SAY_MAX = 300
PHRASE_MAX = 60
STORE_VALUE_MAX = 64 * 1024
FILE_MAX = 5_000_000
GUARD_TIMEOUT = 2.0
GUARD_SLOW_TIMEOUT = 18.0  # M4a: was 8; a slow skill may now wait on an 8 s look at a picture (ctx.look)
TRIP_FAILURES = 2
TRIP_WINDOW_S = 600
FETCH_TIMEOUT_MAX = 8.0
FETCH_BYTES_MAX = 5_000_000
FETCH_AGENT = "CareIncidentLog-Mary/1"

SAY_NOT_WORKING = "That's not working right now."
SAY_NEEDS_INTERNET = "I need the internet for that."
GATE_SKIPS_BRAIN = {"count", "stopped", "quiet", "say_line", "tap"}  # M15c: the send gate's turns, which Gemini stays out of
SAY_LOCKED = "The person who set up your laptop chose that."

INSTRUCTIONS_HEAD = "Things you can do, in groups (never mention tools or groups):"  # M13b
GROUPS_LINE = ("To use a group, call open_skill with its name, and then use_skill with one of the actions it gives "  # M13b
               "you. Do it the moment the talk turns to that group, in the same turn: don't ask first, and don't say "
               "anything about it. Opening a group changes nothing on the screen.")
SWITCH_LINE = ("- Turning these on or off: when they ask (\"stop the crossword\", \"turn it back on\"), "
               "use set_skill for them.")
ERRORS_LINE = ("If a tool answers not_working, say kindly that that's not working right now, and carry on. "
               "If set_skill answers locked, say kindly that the person who set up your laptop chose that. "
               "If use_skill answers not_open, open that group and try again, without a word about it.")  # M13b
ASIDE_LINE = ("Set aside for now: {title}, just as they left it. When they want it back, or they're done with what's "  # M13b
              "on the screen, put what's on the screen away and it comes back. You may mention that once, in one line.")
OPEN_NOTE = ("Nothing changed on the screen. Now use use_skill for what they asked, in this same turn. "  # M13b
             "Say nothing about this.")
NOT_OPEN_NOTE = "Open that group first, then try again."  # M13b
CAME_BACK_NOTE = "{title} is back on the screen, just as they left it. You may say so once, in one line."  # M13b
OPEN_SKILL_DESCRIPTION = ("Open one group of things you can do. It answers with how to use that group and its actions, "  # M13b
                          "for use_skill. It changes nothing on the screen.")
USE_SKILL_DESCRIPTION = "Do one action from a group you have open, or one you can do any time."  # M13b
DETAILS_DESCRIPTION = ("What the action needs. Just the word or words when it needs one thing; a small JSON object when "  # M13b
                       "it needs several. Leave it out when it needs nothing.")

SET_SKILL_DESCRIPTION = ("Turn one of your skills on or off when the resident asks, "
                         "for example 'stop the crossword' or 'turn the crossword back on'.")

_NEGATION = re.compile(r"\b(?:don't|dont|do not|not|never|no)\b")
_FAILED = object()
_module_ids = itertools.count(1)


class SkillError(Exception):
    """A rule a skill broke, written by the core (so its message never holds resident text)."""


class SkillLoadError(SkillError):
    """A skill folder that can't be loaded."""


class SkillFetchError(SkillError):
    """ctx.fetch refused or failed. reason is a short code; status is the HTTP status when there was one."""

    def __init__(self, reason, status=None):
        super().__init__(reason)
        self.reason = reason
        self.status = status


# ---------- contract versions ----------

def adapt_v1(manifest):
    """Contract 1 is the current shape: nothing to change."""
    return manifest


ADAPTERS = {1: adapt_v1}


def adapt(manifest):
    """Brings a manifest of a supported contract to the current shape. Raises SkillLoadError for any other."""
    version = manifest.get("contract") if isinstance(manifest, dict) else None
    if isinstance(version, bool) or version not in SUPPORTED_CONTRACTS or version not in ADAPTERS:
        raise SkillLoadError("unsupported contract")
    return ADAPTERS[version](dict(manifest))


# ---------- checks that need no running code ----------

def read_manifest(folder):
    """The parsed manifest.json of a skill folder. Raises SkillLoadError when it's missing or not a JSON object."""
    try:
        data = json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SkillLoadError("no manifest.json") from None
    except (OSError, ValueError):
        raise SkillLoadError("manifest.json doesn't parse") from None
    if not isinstance(data, dict):
        raise SkillLoadError("manifest.json is not an object")
    return data


def host_pattern_ok(pattern):
    """True for a host name, or one with a single leading wildcard label ("*.wikipedia.org"). No IPs, no ports."""
    if not isinstance(pattern, str) or pattern != pattern.lower():
        return False
    labels = pattern.split(".")
    if labels[0] == "*":
        labels = labels[1:]
    if len(labels) < 2 or labels[-1].isdigit():
        return False
    return all(_HOST_LABEL.match(label) for label in labels)


def host_allowed(host, patterns):
    """True when host matches one pattern exactly, or a "*." pattern with exactly one more label in front."""
    host = (host or "").lower().rstrip(".")
    if not host:
        return False
    for pattern in patterns or []:
        if pattern.startswith("*."):
            head, _, rest = host.partition(".")
            if head and rest == pattern[2:]:
                return True
        elif host == pattern:
            return True
    return False


def _text_ok(value, limit):
    return isinstance(value, str) and value.strip() != "" and len(value) <= limit


def _bool_ok(value):
    return isinstance(value, bool)


def _plain(text):
    """Lower case, curly quotes made straight, only letters, digits, apostrophes and single spaces."""
    text = str(text).lower().replace("’", "'")
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", text).split())


def schema_problems(schema, where="inputSchema", top=True, needs_description=False):
    """Problems with an inputSchema: only the Gemini-safe subset, and every property described."""
    if not isinstance(schema, dict):
        return [f"{where} is not an object"]
    problems = []
    extra = set(schema) - SCHEMA_KEYS
    if extra:
        problems.append(f"{where} uses {', '.join(sorted(extra))}, outside the Gemini subset")
    kind = schema.get("type")
    if kind not in SCHEMA_TYPES:
        return problems + [f"{where} has a bad type"]
    if top and kind != "object":
        problems.append(f"{where} must be an object")
    if "description" in schema or needs_description:
        if not _text_ok(schema.get("description"), DESCRIPTION_MAX):
            problems.append(f"{where} needs a description of at most {DESCRIPTION_MAX} characters")
    if kind == "object":
        props = schema.get("properties", {})
        if not isinstance(props, dict):
            return problems + [f"{where}.properties is not an object"]
        for key, sub in props.items():
            if not (isinstance(key, str) and key.isidentifier() and not keyword.iskeyword(key)
                    and key != "ctx" and not key.startswith("_")):
                problems.append(f"{where} has a bad property name")
                continue
            problems += schema_problems(sub, f"{where}.{key}", top=False, needs_description=True)
        required = schema.get("required", [])
        if not isinstance(required, list) or any(r not in props for r in required):
            problems.append(f"{where}.required names a property that isn't there")
    elif "properties" in schema or "required" in schema:
        problems.append(f"{where} has properties but isn't an object")
    if kind == "array":
        if "items" not in schema:
            problems.append(f"{where} is an array with no items")
        else:
            problems += schema_problems(schema["items"], f"{where}[]", top=False)
    elif "items" in schema:
        problems.append(f"{where} has items but isn't an array")
    if "maxLength" in schema and (kind != "string" or not isinstance(schema["maxLength"], int)
                                  or isinstance(schema["maxLength"], bool) or schema["maxLength"] < 0):
        problems.append(f"{where}.maxLength is only for strings, as a whole number")
    for bound in ("minimum", "maximum"):
        if bound in schema and (kind not in ("integer", "number") or isinstance(schema[bound], bool)
                                or not isinstance(schema[bound], (int, float))):
            problems.append(f"{where}.{bound} is only for numbers")
    if "enum" in schema:
        enum = schema["enum"]
        fits = {"string": lambda v: isinstance(v, str),
                "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
                "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)}.get(kind)
        if fits is None or not isinstance(enum, list) or not enum or not all(fits(v) for v in enum):
            problems.append(f"{where}.enum must be a list of {kind} values")
    return problems


def gemini_schema(schema):
    """A copy of a schema with only the keys Gemini accepts (MCP-only and unknown keys dropped)."""
    if not isinstance(schema, dict):
        return {}
    out = {}
    for key, value in schema.items():
        if key not in SCHEMA_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            value = {name: gemini_schema(sub) for name, sub in value.items()}
        elif key == "items":
            value = gemini_schema(value)
        elif isinstance(value, list):
            value = list(value)
        out[key] = value
    return out


def check_args(schema, value, where="args"):
    """Checks a call's arguments against its schema. Returns (clean value, None) or (None, short problem).
    The problem names the field, never its value. Whole-number floats like 3.0 become 3 for integers."""
    kind = schema.get("type", "object")
    if kind == "object":
        if not isinstance(value, dict):
            return None, f"{where} must be an object"
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                return None, f"{where}.{key} is missing"
        out = {}
        for key, item in value.items():
            if key not in props:
                return None, f"{where} has an unknown field {str(key)[:40]}"
            out[key], problem = check_args(props[key], item, f"{where}.{key}")
            if problem:
                return None, problem
        return out, None
    if kind == "string":
        if not isinstance(value, str):
            return None, f"{where} must be text"
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return None, f"{where} is longer than {schema['maxLength']}"
    elif kind == "integer":
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if not isinstance(value, int) or isinstance(value, bool):
            return None, f"{where} must be a whole number"
    elif kind == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None, f"{where} must be a number"
    elif kind == "boolean":
        if not isinstance(value, bool):
            return None, f"{where} must be true or false"
    elif kind == "array":
        if not isinstance(value, list):
            return None, f"{where} must be a list"
        out = []
        for i, item in enumerate(value):
            item, problem = check_args(schema.get("items", {}), item, f"{where}[{i}]")
            if problem:
                return None, problem
            out.append(item)
        value = out
    if kind in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            return None, f"{where} is below {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return None, f"{where} is above {schema['maximum']}"
    if "enum" in schema and value not in schema["enum"]:
        return None, f"{where} is not one of the choices"
    return value, None


def manifest_problems(manifest, folder_name):
    """Contract checks 1-4 and 9 (in one card) plus the host patterns: a list of short problems, empty when fine."""
    if not isinstance(manifest, dict):
        return ["manifest is not an object"]
    problems = [f"missing {key}" for key in REQUIRED_FIELDS if key not in manifest]
    problems += [f"unknown field {key}" for key in manifest if key not in REQUIRED_FIELDS + OPTIONAL_FIELDS]
    if problems:
        return problems
    name = manifest["name"]
    if not isinstance(name, str) or not NAME_RE.match(name) or "__" in name:
        problems.append("bad name")
    elif name != folder_name:
        problems.append("name must match the folder name")
    contract = manifest["contract"]
    if isinstance(contract, bool) or contract not in SUPPORTED_CONTRACTS:
        problems.append("unsupported contract")
    if not isinstance(manifest["version"], str) or not VERSION_RE.match(manifest["version"]):
        problems.append("version must look like 0.1.0")
    for key, limit in (("title", TITLE_MAX), ("summary", SUMMARY_MAX), ("instructions", INSTRUCTIONS_MAX)):
        if not _text_ok(manifest[key], limit):
            problems.append(f"{key} must be text of at most {limit} characters")
    for key in ("storage", "default_on", "sees", "slow", "vision", "memory"):  # M4a: vision, M7a: memory
        if key in manifest and not _bool_ok(manifest[key]):
            problems.append(f"{key} must be true or false")
    if manifest["offline"] not in ("works", "needs_internet"):
        problems.append("offline must be works or needs_internet")
    problems += _needs_problems(manifest["needs"])
    if isinstance(manifest["needs"], dict) and manifest["needs"].get("send_mail") is True and manifest.get("slow") is not True:
        problems.append("a skill with needs.send_mail must also have \"slow\": true")  # M15d: or a send outlives its guard
    problems += _screen_problems(manifest.get("screen"))
    settings = manifest.get("settings", [])
    if not isinstance(settings, list) or not all(
            isinstance(s, str) and SETTING_RE.match(s) and not _PROTECTED_SETTING.search(s) for s in settings):
        problems.append("settings must list plain setting names (never keys or skills_ ones)")
    actions = manifest["actions"]
    if not isinstance(actions, list):
        return problems + ["actions must be a list"]
    seen = set()
    for i, action in enumerate(actions):
        problems += _action_problems(action, i, name, seen)
    if sum(1 for a in actions if isinstance(a, dict) and a.get("always") is True) > ALWAYS_SKILL_MAX:  # M13b
        problems.append(f"at most {ALWAYS_SKILL_MAX} actions can be always")
    return problems


def _needs_problems(needs):
    if not isinstance(needs, dict):
        return ["needs must be an object"]
    problems = [f"unknown needs field {key}" for key in needs if key not in NEEDS_KEYS]
    hosts = needs.get("internet_hosts", [])
    if not isinstance(hosts, list) or not all(host_pattern_ok(h) for h in hosts):
        problems.append("needs.internet_hosts must be host names like api.example.org or *.example.org")
    if "mic" in needs and not _bool_ok(needs["mic"]):
        problems.append("needs.mic must be true or false")
    if "send_mail" in needs and not _bool_ok(needs["send_mail"]):  # M15d
        problems.append("needs.send_mail must be true or false")
    modes = needs.get("modes", list(MODES))
    if not isinstance(modes, list) or not set(modes) <= MODES:
        problems.append("needs.modes must list live, normal or offline")
    return problems


def _screen_problems(screen):
    if screen is None:
        return []
    if not isinstance(screen, dict):
        return ["screen must be an object"]
    problems = [f"unknown screen field {key}" for key in screen if key not in SCREEN_KEYS]
    if not _text_ok(screen.get("menu_label"), TITLE_MAX):
        problems.append(f"screen.menu_label must be text of at most {TITLE_MAX} characters")
    if "menu_icon" in screen and not _text_ok(screen["menu_icon"], 30):
        problems.append("screen.menu_icon must be a short word")
    if "full_screen" in screen and not _bool_ok(screen["full_screen"]):
        problems.append("screen.full_screen must be true or false")
    return problems


def _action_problems(action, i, skill_name, seen):
    if not isinstance(action, dict):
        return [f"action {i} is not an object"]
    problems = [f"action {i} has unknown field {key}" for key in action if key not in ACTION_KEYS]
    act = action.get("name")
    if not isinstance(act, str) or not ACTION_RE.match(act) or "__" in act or act in RESERVED_ACTIONS:
        return problems + [f"action {i} has a bad name"]
    if act in seen:
        problems.append(f"action {act} is declared twice")
    seen.add(act)
    function = f"{skill_name}__{act}"
    if not FUNCTION_RE.match(function):
        problems.append(f"function name {function[:70]} is longer than 64 characters")
    if not _text_ok(action.get("description"), DESCRIPTION_MAX):
        problems.append(f"action {act} needs a description of at most {DESCRIPTION_MAX} characters")
    schema = action.get("inputSchema", {"type": "object"})
    problems += schema_problems(schema, f"{act}.inputSchema")
    if "annotations" in action and not isinstance(action["annotations"], dict):
        problems.append(f"action {act} annotations must be an object")
    if "always" in action and not _bool_ok(action["always"]):  # M13b
        problems.append(f"action {act} always must be true or false")
    phrases = action.get("offline_phrases", [])
    if not isinstance(phrases, list) or not all(isinstance(p, str) and _plain(p) and len(p) <= PHRASE_MAX
                                                for p in phrases):
        problems.append(f"action {act} offline_phrases must be short phrases")
    elif phrases and isinstance(schema, dict) and schema.get("required"):
        problems.append(f"action {act} has offline_phrases but needs inputs")
    return problems


def source_problems(path):
    """Static safety check (contract check 6) of a skill.py, from its source with ast, before it's imported."""
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename="skill.py")
    except SyntaxError as err:
        return [f"skill.py has a syntax error on line {err.lineno}"]
    except (OSError, ValueError):
        return ["skill.py can't be read"]
    problems = []
    for node in ast.walk(tree):
        roots = []
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots = [node.module.split(".")[0]]
        for root in roots:
            if root in FORBIDDEN_IMPORTS:
                problems.append(f"imports {root}")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            problems.append(f"uses {node.id}")
        elif isinstance(node, ast.Attribute) and (node.attr in FORBIDDEN_NAMES or node.attr == "_host"):  # M15d: _host
            problems.append(f"uses {node.attr}")
    return sorted(set(problems))


def _where(exc, folder):
    """'skill.py:12': the last line of the skill's own code in a traceback (never a full path)."""
    folder = os.path.normcase(os.path.abspath(folder))
    spot, tb = None, exc.__traceback__
    while tb is not None:
        fname = tb.tb_frame.f_code.co_filename
        if os.path.normcase(os.path.dirname(os.path.abspath(fname))) == folder:
            spot = f"{os.path.basename(fname)}:{tb.tb_lineno}"
        tb = tb.tb_next
    return spot


def _run_limited(fn, limit, name):
    """Runs fn on a worker thread for at most limit seconds. Returns ("ok", value), ("error", exc) or ("timeout", None).
    A thread that times out can't be stopped; it's a daemon, so it never holds the app open."""
    box = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 (any failure in skill code is the skill's)
            box["error"] = exc

    worker = threading.Thread(target=run, name=name, daemon=True)
    worker.start()
    worker.join(limit)
    if worker.is_alive():
        return "timeout", None
    if "error" in box:
        return "error", box["error"]
    return "ok", box.get("value")


class _AllowListRedirect(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to https on an allowed host; anything else stops the fetch."""

    def __init__(self, patterns):
        super().__init__()
        self.patterns = patterns

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urllib.parse.urlsplit(newurl)
        try:
            port = parts.port
        except ValueError:
            port = -1
        if parts.scheme != "https" or port not in (None, 443) or not host_allowed(parts.hostname, self.patterns):
            raise SkillFetchError("redirect_not_allowed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_url(request, timeout, patterns):
    """Opens one request with the allow-list redirect check. Tests replace the https handler, never this rule."""
    return urllib.request.build_opener(_AllowListRedirect(patterns)).open(request, timeout=timeout)


# ---------- what a skill gets ----------

class _NoStore:
    """The store of a skill whose card says "storage": false."""

    def _refuse(self, *args, **kwargs):
        raise SkillError("this skill has no storage")

    get = put = delete = keys = _refuse


class SkillStore:
    """A skill's private key-value store in the skill_data table, bound to its own name. Values are JSON, 64 KB at most."""

    def __init__(self, host, skill_name):
        self._host = host
        self._skill = skill_name

    @staticmethod
    def _key(key):
        if not isinstance(key, str) or not 0 < len(key) <= 200:
            raise SkillError("store keys are text of 1 to 200 characters")
        return key

    def get(self, key, default=None):
        with self._host._db() as conn:
            row = conn.execute("SELECT value FROM skill_data WHERE skill=? AND key=?",
                               (self._skill, self._key(key))).fetchone()
        return default if row is None else json.loads(row[0])

    def put(self, key, value):
        try:
            text = json.dumps(value)
        except (TypeError, ValueError):
            raise SkillError("store values must be JSON") from None
        if len(text.encode("utf-8")) > STORE_VALUE_MAX:
            raise SkillError("store value is over 64 KB")
        with self._host._db() as conn:
            conn.execute("INSERT OR REPLACE INTO skill_data (skill, key, value, updated_at) VALUES (?, ?, ?, ?)",
                         (self._skill, self._key(key), text, datetime.now().isoformat(timespec="seconds")))

    def delete(self, key):
        with self._host._db() as conn:
            conn.execute("DELETE FROM skill_data WHERE skill=? AND key=?", (self._skill, self._key(key)))

    def keys(self):
        with self._host._db() as conn:
            rows = conn.execute("SELECT key FROM skill_data WHERE skill=? ORDER BY key", (self._skill,)).fetchall()
        return [row[0] for row in rows]


class SkillFiles:
    """The skill's own folder, DATA\\skills\\<name>\\. Every name is checked to stay inside it."""

    def __init__(self, root):
        self._root = Path(root)

    def _path(self, name):
        if not isinstance(name, str) or not name or Path(name).is_absolute() or Path(name).drive:
            raise SkillError("bad file name")
        self._root.mkdir(parents=True, exist_ok=True)
        root = self._root.resolve()
        full = (root / name).resolve()
        if full == root or not full.is_relative_to(root):
            raise SkillError("that file is outside the skill's folder")
        return full

    def read_bytes(self, name):
        return self._path(name).read_bytes()

    def write_bytes(self, name, data):
        if not isinstance(data, (bytes, bytearray)) or len(data) > FILE_MAX:
            raise SkillError("files are bytes, 5 MB at most")
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(data))

    def read_text(self, name):
        return self.read_bytes(name).decode("utf-8")

    def write_text(self, name, text):
        self.write_bytes(name, str(text).encode("utf-8"))

    def exists(self, name):
        return self._path(name).is_file()

    def delete(self, name):
        path = self._path(name)
        if path.is_file():
            path.unlink()

    def list(self):
        if not self._root.is_dir():
            return []
        root = self._root.resolve()
        return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _card_gate(host, skill):  # M15c
    """The core's send gate for a card with needs.send_mail, else None. Out here so no ctx attribute hands a skill the gate."""
    return host.gate if skill.manifest.get("needs", {}).get("send_mail") else None


def _page_gate(ctx):  # M15c
    """The same, only for a move on the page, and only while the look is this skill's."""
    gate = _card_gate(ctx._host, ctx._skill)
    return gate if gate is not None and ctx.from_page and gate.skill == ctx.name else None


class SkillContext:
    """What one call into a skill gets: store, state, files, effect(), settings_get/put, fetch(), look() (M4a),
    send_mail() (M15d), asset() and font() (M15b), the send gate's arm_send() and the rest (M15c), and
    has_printer() (M17)."""

    def __init__(self, host, skill):
        self._host = host
        self._skill = skill
        self.name = skill.name
        self.store = SkillStore(host, skill.name) if skill.manifest["storage"] else _NoStore()
        self.state = skill.state
        self.files = SkillFiles(Path(host.data_dir) / "skills" / skill.name)
        self.effects = []
        self.heard = ""  # M7a: the resident's offline line, when offline mode made this call
        self.from_page = False  # M15c: True only inside SkillHost.on_event

    def effect(self, kind, data=None):
        """Asks the page to do something: show_screen / leave_screen (its own screen) or one of its own kinds."""
        data = {} if data is None else data
        if not isinstance(data, dict):
            raise SkillError("effect data must be an object")
        if kind == "settings":
            raise SkillError("settings change through ctx.settings_put")
        if kind in ("show_screen", "leave_screen"):
            if data.get("screen", self.name) != self.name:
                raise SkillError("a skill shows only its own screen")
            effect = {"kind": kind, "data": dict(data, screen=self.name)}
        elif isinstance(kind, str) and KIND_RE.match(kind):
            effect = {"skill": self.name, "kind": kind, "data": data}
        else:
            raise SkillError("bad effect kind")
        try:
            size = len(json.dumps(effect))
        except (TypeError, ValueError):
            raise SkillError("effect data must be JSON") from None
        if size > RESULT_MAX:
            raise SkillError("effect data is over 4 KB")
        self.effects.append(effect)

    def _setting(self, key):
        if key not in self._skill.manifest.get("settings", []):
            raise SkillError("that setting isn't in the skill's card")
        return key

    def settings_get(self, key, default=None):
        return self._host.get_settings().get(self._setting(key), default)

    def settings_put(self, key, value):
        """Saves one of its card's settings and tells the page (a core "settings" effect)."""
        text = value if isinstance(value, str) else json.dumps(value)
        self._host.put_settings({self._setting(key): text})
        self.effects.append({"kind": "settings", "data": {"values": {key: text}}})

    def asset(self, name):  # M15b
        """Read-only bytes of a file the skill ships in its own assets folder. Subfolders are fine; outside it isn't."""
        if not isinstance(name, str) or not name:
            raise SkillError("bad file name")
        root = (Path(self._skill.folder) / "assets").resolve()
        full = (root / name).resolve()
        if full == root or not full.is_relative_to(root):
            raise SkillError("that file is outside the skill's assets")
        try:
            return full.read_bytes()
        except OSError:
            raise SkillError("no such asset") from None

    def font(self, file):  # M15b
        """Read-only bytes of a font bundled with Mary (web/mary/fonts), by bare file name."""
        if not isinstance(file, str) or not FONT_RE.fullmatch(file):
            raise SkillError("bad font name")
        try:
            return (Path(self._host.skills_dir).parent / "web" / "mary" / "fonts" / file).read_bytes()
        except OSError:
            raise SkillError("no such font") from None

    def fetch(self, url, method="GET", params=None, headers=None, max_bytes=2_000_000, timeout=6):
        """The only way to the internet: https GET to the card's internet_hosts. Returns {status, content_type, body}."""
        return self._host._fetch(self._skill, url, method, params, headers, max_bytes, timeout)

    def send_mail(self, ticket, to, subject, body, pictures=()):  # M15d
        """Sends from her own email account through the host, so a skill never sees the password. The card needs
        needs.send_mail true and "slow": true, and each email needs a one-time ticket only the core can mint.
        Returns {"ok": True} or {"ok": False, "code": ..., "message": ...}, and never raises."""
        return self._host._send_mail(self._skill, ticket, to, subject, body, pictures)

    # ----- the hard-wired yes (M15c): all of it needs needs.send_mail on the card -----

    def arm_send(self, person, to, subject, body, pictures=()):
        """Holds this exact content for the resident's yes. Any tool call may do this, and it shows the look, no more.
        {"ok": True, "look": id}, or {"ok": False, "reason": ...}: money, password, ssn, too_big, bad_message or no_email.
        Never raises. An arm that's refused leaves no look."""
        gate = _card_gate(self._host, self._skill)
        if gate is None:
            return {"ok": False, "reason": "no_email"}
        try:
            return {"ok": True, "look": gate.arm(self.name, person, to, subject, body, pictures)}
        except send_gate.GateRefused as err:
            return {"ok": False, "reason": err.reason}
        except Exception:  # noqa: BLE001 (a look that can't be held is a bad message, never the skill's crash)
            return {"ok": False, "reason": "bad_message"}

    def disarm_send(self):
        """The content changed or the screen left. No look."""
        gate = _card_gate(self._host, self._skill)
        if gate is not None:
            gate.disarm(self.name)

    def send_state(self):
        """{"state", "line_said", "tap_open", "look", "line"}: none, look, counting or sending, and never an address."""
        gate = _card_gate(self._host, self._skill)
        return gate.state(self.name) if gate is not None else dict(send_gate.NO_LOOK)

    def mail_ready(self):
        """True when her email is connected. With no gate, email isn't set up."""
        check = self._host.mail_ready
        if _card_gate(self._host, self._skill) is None or check is None:
            return False
        try:
            return bool(check())
        except Exception:  # noqa: BLE001 (a check that fails counts as not ready)
            return False

    def asks_for(self, text):
        """"money", "password", "ssn" or None, by the same words the gate refuses."""
        return send_gate.asks_for(text)

    def send_shown(self, look):
        """Page only: the page really drew this look."""
        gate = _page_gate(self)
        return gate.shown(look) if gate is not None else False

    def send_tap(self):
        """Page only: their tap on the quiet Send it. True when the count started."""
        gate = _page_gate(self)
        return gate.tap() if gate is not None else False

    def send_undo(self):
        """Page only: their tap on Undo. True when a count stopped."""
        gate = _page_gate(self)
        return gate.undo() if gate is not None else False

    def send_now(self, look):
        """Page only, at the end of the count. The gate hands over the frozen content once, the ticket is minted here for
        this one try, and send_mail goes last, so the skill never holds a ticket. Returns send_mail's result, or None when
        the gate said no."""
        gate = _page_gate(self)
        if gate is None:
            return None
        content = gate.take(self.name, look)
        if content is None:
            return None
        try:
            ticket = gate.mailer.mint_ticket(self.name, content["to"], content["subject"], content["body"],
                                             content["pictures"])
            return self.send_mail(ticket, content["to"], content["subject"], content["body"], content["pictures"])
        except Exception:  # noqa: BLE001 (nothing went: send_mail itself never raises)
            return {"ok": False, "code": "refused", "message": mail_core.MESSAGES["refused"]}
        finally:
            gate.finish(look)

    def has_printer(self):  # M17
        """True when this computer has a real printer. Skills ask here and never the system."""
        return printers.has_printer()

    def look(self, image_bytes, mime, question):  # M4a
        """Asks what a picture shows, through the host, so a skill never holds the key. Text, or "" when the card has no
        "vision": true, the host has no vision, or anything went wrong."""
        vision = self._host.vision
        if vision is None or not self._skill.manifest.get("vision"):
            return ""
        try:
            return str(vision(image_bytes, mime, question) or "")
        except Exception:  # noqa: BLE001 (a look that fails is no answer, never the skill's fault)
            return ""

    def recall(self, words, limit=6):  # M7a
        """Read-only: plain fact texts from her memory that match words. [] when the card has no "memory": true,
        the host has no recall, or anything went wrong."""
        recall = self._host.recall
        if recall is None or not self._skill.manifest.get("memory"):
            return []
        try:
            return [str(text) for text in recall(words, limit=limit)]
        except Exception:  # noqa: BLE001 (a recall that fails is no facts, never the skill's fault)
            return []


class Skill:
    """One loaded skill: its card, its code, its in-memory state and its failure record."""

    def __init__(self, name, folder, manifest, module):
        self.name = name
        self.folder = folder
        self.manifest = manifest
        self.module = module
        self.state = {}
        self.failures = []
        self.tripped = False
        self.actions = {a["name"]: a for a in manifest["actions"]}

    @property
    def title(self):
        return self.manifest["title"]

    def phrases(self):
        """(phrase in plain words, action name) for every offline phrase."""
        return [(_plain(p), a["name"]) for a in self.manifest["actions"] for p in a.get("offline_phrases", [])]


# ---------- the host ----------

class ForgetReach:  # M15c
    """What memory_core.FORGET_REACH holds: a forget's way to the skills, from a SkillHost."""

    def __init__(self, host):
        self.count = host.forget_count
        self.forget = host.forget_reach


class SkillHost:
    """Loads the skills in skills_dir and runs them. Backends come from the caller, so tests need no server:
    connect() -> sqlite3 connection, get_settings() -> {str: str}, put_settings({str: str}), online() -> bool.
    timeout / slow_timeout bound every call into skill code; clock is for tests of the trip rule;
    fetcher(skill_name, url, **kw), when given, replaces every skill's ctx.fetch (contract tests).
    mailer, set by the app, is the only way a skill's email leaves (M15d); it checks the one-time ticket."""

    def __init__(self, skills_dir, data_dir, connect, get_settings, put_settings, online=lambda: True,
                 log_path=None, timeout=GUARD_TIMEOUT, slow_timeout=GUARD_SLOW_TIMEOUT, clock=time.monotonic,
                 fetcher=None):
        self.skills_dir = Path(skills_dir)
        self.data_dir = Path(data_dir)
        self._connect = connect
        self.get_settings = get_settings
        self.put_settings = put_settings
        self.online = online
        self.log_path = Path(log_path) if log_path else self.data_dir / "skills.log"
        self.timeout = timeout
        self.slow_timeout = slow_timeout
        self._clock = clock
        self._fetcher = fetcher
        self.vision = None  # M4a: set by the app: vision(image_bytes, mime, question) -> text or ""
        self.mailer = None  # M15d: set by the app: mailer(skill_name, ticket, to, subject, body, pictures) -> result
        self.gate = None  # M15c: set by the app: the send_gate.SendGate. With none, email isn't set up
        self.mail_ready = None  # M15c: set by the app: mail_ready() -> True when her email is connected
        self.recall = None  # M7a: set by the app: recall(words, limit=6) -> list of fact texts
        self.opened = None  # M13b: the group she opened last (memory only)
        self.aside = None  # M13b: the skill the page has set aside (memory only)
        self._table_ready = False
        self._log_lock = threading.Lock()
        self._settings_lock = threading.Lock()
        self._fail_lock = threading.Lock()
        self.skills = {}
        self.load_errors = {}

    # ----- plumbing -----

    @contextlib.contextmanager
    def _db(self):
        conn = self._connect()
        try:
            if not self._table_ready:
                conn.execute("CREATE TABLE IF NOT EXISTS skill_data (skill TEXT NOT NULL, key TEXT NOT NULL, "
                             "value TEXT NOT NULL, updated_at TEXT, PRIMARY KEY (skill, key))")
                self._table_ready = True
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _log(self, event, **fields):
        """One JSON line in skills.log. Callers pass only names, codes and numbers: never resident text, keys or URLs."""
        fields = {key: memory_core.scrub_addresses(value) if isinstance(value, str) else value  # M18: the wall behind that
                  for key, value in fields.items()}
        line = json.dumps(dict({"time": datetime.now().isoformat(timespec="seconds"), "event": event}, **fields))
        with self._log_lock:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass

    def _json_setting(self, key, kind):
        try:
            value = json.loads(self.get_settings().get(key) or "null")
        except ValueError:
            value = None
        return value if isinstance(value, kind) else kind()

    def _locks(self):
        return {k: v for k, v in self._json_setting("skills_locked", dict).items() if v in ("on", "off")}

    def _limit(self, skill):
        return self.slow_timeout if skill.manifest.get("slow") else self.timeout

    def _sorted(self):
        return [self.skills[name] for name in sorted(self.skills)]

    # ----- loading -----

    def load(self, is_blocked=None):
        """Scans skills_dir and loads every folder that passes the checks. A folder that fails is left out,
        with a line in skills.log and its reason in load_errors. is_blocked(phrase) refuses offline phrases
        that are emergency or yes/no words (the caller passes the app's word lists)."""
        self.skills, self.load_errors = {}, {}
        if not self.skills_dir.is_dir():
            return
        taken, budget = {}, 0
        for folder in sorted(p for p in self.skills_dir.iterdir() if p.is_dir()):
            if folder.name.startswith((".", "_")):
                continue
            try:
                skill = self._load_one(folder, taken, budget, is_blocked)
            except SkillLoadError as err:
                self.load_errors[folder.name] = str(err)
                self._log("load_failed", skill=folder.name[:40], reason=str(err))
                continue
            self.skills[skill.name] = skill
            budget += len(skill.manifest["summary"])  # M13b: only the one-line menu is always in her prompt
            for phrase, _ in skill.phrases():
                taken[phrase] = skill.name

    def _load_one(self, folder, taken, budget, is_blocked):
        manifest = adapt(read_manifest(folder))
        problems = manifest_problems(manifest, folder.name)
        if problems:
            raise SkillLoadError("; ".join(problems[:3]))
        name = manifest["name"]
        if budget + len(manifest["summary"]) > TOTAL_INSTRUCTIONS_MAX:  # M13b
            raise SkillLoadError("instruction budget is full")
        skill = Skill(name, folder, manifest, None)
        for phrase, _ in skill.phrases():
            if phrase in taken:
                raise SkillLoadError(f"offline phrase clashes with {taken[phrase]}")
            if is_blocked and is_blocked(phrase):
                raise SkillLoadError("offline phrase clashes with emergency or yes/no words")
        source = folder / "skill.py"
        if not source.is_file():
            if manifest["actions"] or manifest.get("sees"):
                raise SkillLoadError("no skill.py")
            return skill
        problems = source_problems(source)
        if problems:
            raise SkillLoadError("unsafe: " + ", ".join(problems[:3]))
        skill.module = self._import(name, source, folder)
        missing = [a for a in skill.actions if not callable(getattr(skill.module, a, None))]
        if missing:
            raise SkillLoadError(f"no handler for {missing[0]}")
        if manifest.get("sees") and not callable(getattr(skill.module, "view", None)):
            raise SkillLoadError("sees is true but there's no view()")
        return skill

    def _import(self, name, source, folder):
        module_name = f"mary_skill_{name}_{next(_module_ids)}"
        spec = importlib.util.spec_from_file_location(module_name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        outcome, value = _run_limited(lambda: spec.loader.exec_module(module), self.slow_timeout, f"skill-load-{name}")
        if outcome == "ok":
            return module
        sys.modules.pop(module_name, None)
        if outcome == "timeout":
            raise SkillLoadError("timed out on load")
        where = _where(value, folder)
        raise SkillLoadError(f"crashed on load ({type(value).__name__}{' at ' + where if where else ''})")

    # ----- switches -----

    def enabled(self, name):
        """Loaded, not tripped, not locked off, and (locked on, or the resident's choice / the card's default)."""
        skill = self.skills.get(name)
        if skill is None or skill.tripped:
            return False
        lock = self._locks().get(name)
        if lock:
            return lock == "on"
        if name in self._json_setting("skills_off", list):
            return False
        return bool(skill.manifest["default_on"]) or name in self._json_setting("skills_on", list)

    def set_skill(self, name, on, by="voice"):
        """The resident's own on/off choice. By voice, a skill the helper locked answers {"error": "locked"}.
        Kept in settings: skills_off (JSON list), and skills_on (JSON list) for skills whose card is default_on false."""
        skill = self.skills.get(name)
        if skill is None:
            return {"error": "unknown_skill"}
        lock = self._locks().get(name)
        if lock and by != "helper":
            return {"error": "locked", "locked": lock}
        with self._settings_lock:
            off = [n for n in self._json_setting("skills_off", list) if n != name]
            turned_on = [n for n in self._json_setting("skills_on", list) if n != name]
            if not on:
                off.append(name)
            elif not skill.manifest["default_on"]:
                turned_on.append(name)
            self.put_settings({"skills_off": json.dumps(sorted(off)), "skills_on": json.dumps(sorted(turned_on))})
        self._log("switch", skill=name, on=bool(on), by=by)
        if on and skill.tripped:
            return {"error": "not_working"}
        return {"ok": True, "name": name, "on": self.enabled(name)}

    def lock(self, name, state):
        """The helper's lock: "off", "on", or None to unlock. Kept in settings as skills_locked {name: state}."""
        if not isinstance(name, str) or not NAME_RE.match(name) or state not in ("on", "off", None):
            raise ValueError("lock(name, 'on' | 'off' | None)")
        with self._settings_lock:
            locks = self._locks()
            if state is None:
                locks.pop(name, None)
            else:
                locks[name] = state
            self.put_settings({"skills_locked": json.dumps(locks, sort_keys=True)})
        self._log("lock", skill=name, state=state)
        return locks

    def list_skills(self):
        """Every loaded skill for the page and My info: name, title, summary, menu, on, locked, tripped, has_screen."""
        locks = self._locks()
        out = []
        for skill in self._sorted():
            screen = skill.manifest.get("screen")
            out.append({
                "name": skill.name, "title": skill.title, "summary": skill.manifest["summary"],
                "menu": ({"label": screen["menu_label"], "icon": screen.get("menu_icon", ""),
                          "full_screen": bool(screen.get("full_screen"))} if screen else None),
                "on": self.enabled(skill.name), "locked": locks.get(skill.name), "tripped": skill.tripped,
                "has_screen": bool(screen) and (skill.folder / "screen.js").is_file(),
                "has_css": (skill.folder / "screen.css").is_file(),
            })
        return out

    # ----- what Gemini sees -----

    def set_aside(self, name):  # M13b
        """The page's word on which skill it has set aside: a loaded skill's name, anything else for none."""
        self.aside = name if isinstance(name, str) and name in self.skills else None

    def _in_hand(self, screen=None):  # M13b
        """The groups she holds with no opening: the skill on screen, then the one she opened last, if they're on."""
        return [self.skills[name] for name in dict.fromkeys((screen, self.opened)) if self.enabled(name)]

    def _always(self):  # M13b
        """(skill, action) she can use with no opening, from the skills that are on; only the first ALWAYS_MAX count."""
        found = [(skill, action) for skill in self._sorted() if self.enabled(skill.name)
                 for action in skill.manifest["actions"] if action.get("always")]
        return found[:ALWAYS_MAX]

    @staticmethod
    def _action_line(action):  # M13b
        """One action for her system prompt: "name (param, param): description"."""
        params = action.get("inputSchema", {}).get("properties")
        head = f"{action['name']} ({', '.join(params)})" if params else action["name"]
        return f"{head}: {action['description']}"

    def _open_skill_declaration(self):  # M13b
        return {"name": "open_skill", "description": OPEN_SKILL_DESCRIPTION, "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "enum": sorted(self.skills), "description": "Which group"}},
            "required": ["name"]}}

    def _use_skill_declaration(self):  # M13b: details is text because Gemini refuses an OBJECT with empty properties
        return {"name": "use_skill", "description": USE_SKILL_DESCRIPTION, "parameters": {
            "type": "object",
            "properties": {"action": {"type": "string", "description": "The action's name"},
                           "details": {"type": "string", "description": DETAILS_DESCRIPTION}},
            "required": ["action"]}}

    def _set_skill_declaration(self):
        return {"name": "set_skill", "description": SET_SKILL_DESCRIPTION, "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "enum": sorted(self.skills), "description": "Which skill"},
                           "on": {"type": "boolean", "description": "true turns it on, false turns it off"}},
            "required": ["name", "on"]}}

    def gemini_tools(self):
        """[{"functionDeclarations": [...]}]: M13b: open_skill and use_skill while any skill is on, so the count stays
        the same however many skills exist, plus the core set_skill; [] when no skill is loaded."""
        if not self.skills:
            return []
        decls = [self._set_skill_declaration()]
        if any(self.enabled(skill.name) for skill in self._sorted()):
            decls = [self._open_skill_declaration(), self._use_skill_declaration()] + decls
        return [{"functionDeclarations": decls}]

    def instruction_text(self, on_screen=None):
        """The "Things you can do" text for her system prompt: M13b: one line per group, the how-to and actions of the
        groups in hand and the any-time actions; then "What's on the screen now" for the skill on screen, and what's
        set aside. Empty when no skill is loaded."""
        if not self.skills:
            return ""
        on = [s for s in self._sorted() if self.enabled(s.name)]
        lines = [INSTRUCTIONS_HEAD] + [f"- {s.title}: {s.manifest['summary']}" for s in on]  # M13b: summary
        if on:  # M13b
            lines.append(GROUPS_LINE)
        for skill in self._in_hand(on_screen):  # M13b
            lines.append(f"Open now ({skill.title}): {skill.manifest['instructions']}")
            lines.append("Its actions: " + "; ".join(self._action_line(a) for a in skill.manifest["actions"]))
        always = self._always()  # M13b
        if always:
            lines.append("Any time, with use_skill and no opening: " + "; ".join(self._action_line(a) for _, a in always))
        lines += [SWITCH_LINE, ERRORS_LINE]
        if on_screen in self.skills and self.enabled(on_screen):
            seen = self.view(on_screen)
            if seen:
                lines.append(f"What's on the screen now ({self.skills[on_screen].title}): {seen}")
        if self.aside != on_screen and self.enabled(self.aside):  # M13b
            lines.append(ASIDE_LINE.format(title=self.skills[self.aside].title))
        return "\n".join(lines)

    # ----- running skill code -----

    def context(self, name):
        """A fresh ctx for a loaded skill (each call gets its own, so effects never mix)."""
        return SkillContext(self, self.skills[name])

    def _fail(self, skill, what, error, where=None, message=None):
        """Records one failure in skills.log and applies the trip rule (2 within 10 minutes = off until restart)."""
        fields = {"skill": skill.name, "action": what, "error": error}
        if where:
            fields["where"] = where
        if message:
            fields["message"] = message[:120]
        self._log("failure", **fields)
        with self._fail_lock:
            now = self._clock()
            skill.failures = [t for t in skill.failures if now - t < TRIP_WINDOW_S] + [now]
            if len(skill.failures) >= TRIP_FAILURES and not skill.tripped:
                skill.tripped = True
                self._log("tripped", skill=skill.name)

    def _guard(self, skill, what, fn):
        """Runs skill code with the time limit. Returns its value, or _FAILED after recording the failure."""
        limit = self._limit(skill)
        outcome, value = _run_limited(fn, limit, f"skill-{skill.name}")
        if outcome == "ok":
            return value
        if outcome == "timeout":
            self._fail(skill, what, "Timeout", message=f"took longer than {limit} s")
        else:
            message = str(value) if isinstance(value, SkillError) else None
            self._fail(skill, what, type(value).__name__, _where(value, skill.folder), message)
        return _FAILED

    @staticmethod
    def _result(response, effects=(), say=None):
        return {"response": response, "effects": list(effects), "say": say}

    def _finish(self, skill, what, ctx, outcome):
        """Turns a handler's return value into {response, effects, say}, checking size and effects."""
        if outcome is _FAILED:
            return self._result({"error": "not_working"}, say=SAY_NOT_WORKING)
        response = dict(outcome) if isinstance(outcome, dict) else ({"ok": True} if outcome is None
                                                                    else {"result": outcome})
        say = response.pop("say", None)
        say = say[:SAY_MAX] if isinstance(say, str) and say.strip() else None
        try:
            size = len(json.dumps(response).encode("utf-8"))
        except (TypeError, ValueError):
            size = None
        bad_effect = any(e.get("kind") not in CORE_EFFECT_KINDS and e.get("skill") != skill.name for e in ctx.effects)
        if size is None or size > RESULT_MAX or bad_effect:
            self._fail(skill, what, "BadResult", message="result not JSON, over 4 KB, or a foreign effect")
            return self._result({"error": "not_working"}, say=SAY_NOT_WORKING)
        return self._result(response, ctx.effects, say)

    def call(self, fn_name, args=None, heard="", screen=None):  # M7a: heard  # M13b: screen
        """Runs one tool call from Gemini, the page or offline mode: "<skill>__<action>", "set_skill", or (M13b)
        "open_skill" / "use_skill"; screen is the skill on screen, which use_skill needs no opening for.
        Returns {"response": {...}, "effects": [...], "say": str | None}; never raises for a skill's fault."""
        args = {} if args is None else args
        if fn_name == "set_skill":
            return self._call_set_skill(args)
        if fn_name == "open_skill":  # M13b
            return self._call_open(args)
        if fn_name == "use_skill":  # M13b
            return self._call_use(args, heard, screen)
        name, sep, action = str(fn_name).partition("__")
        skill = self.skills.get(name)
        if not sep or skill is None or action not in skill.actions:
            return self._result({"error": "unknown_tool"})
        if skill.tripped:
            return self._result({"error": "not_working"}, say=SAY_NOT_WORKING)
        if not self.enabled(name):
            return self._result({"error": "off"})
        if skill.manifest["offline"] == "needs_internet" and not self.online():
            return self._result({"error": "needs_internet"}, say=SAY_NEEDS_INTERNET)
        clean, problem = check_args(skill.actions[action].get("inputSchema", {"type": "object"}), args)
        if problem:
            return self._result({"error": "bad_input", "detail": problem})
        ctx = self.context(name)
        ctx.heard = str(heard or "")  # M7a
        handler = getattr(skill.module, action)
        result = self._finish(skill, action, ctx, self._guard(skill, action, lambda: handler(ctx, **clean)))  # M13b
        back = self._track(skill, result)  # M13b
        if back:
            result["response"].update(came_back=back, note=CAME_BACK_NOTE.format(title=back))
        return result

    def _call_set_skill(self, args):
        clean, problem = check_args(self._set_skill_declaration()["parameters"], args)
        if problem:
            return self._result({"error": "bad_input", "detail": problem})
        response = self.set_skill(clean["name"], clean["on"], by="voice")
        error = response.get("error")
        if error == "locked":
            return self._result(response, say=SAY_LOCKED)
        if error == "not_working":
            return self._result(response, say=SAY_NOT_WORKING)
        if error:
            return self._result(response)
        title = self.skills[clean["name"]].title
        effects = [{"kind": "settings", "data": {"skills": {clean["name"]: response["on"]}}}]
        return self._result(response, effects, f"{title} is {'on' if response['on'] else 'off'} now.")

    def _call_open(self, args):  # M13b
        """open_skill: the how-to and actions of one group. Opening changes nothing on the screen."""
        name = args.get("name") if isinstance(args, dict) else None
        if isinstance(name, str) and name not in self.skills:  # before check_args, whose enum would say bad_input
            return self._result({"error": "unknown_skill"})
        clean, problem = check_args(self._open_skill_declaration()["parameters"], args)
        if problem:
            return self._result({"error": "bad_input", "detail": problem})
        skill = self.skills[clean["name"]]
        if skill.tripped:
            return self._result({"error": "not_working"}, say=SAY_NOT_WORKING)
        if not self.enabled(skill.name):
            return self._result({"error": "off"})
        self.opened = skill.name
        actions = []
        for action in skill.manifest["actions"]:
            item = {"name": action["name"], "does": action["description"]}
            params = action.get("inputSchema", {}).get("properties")
            if params:
                item["needs"] = {key: prop.get("description") or prop.get("type", "") for key, prop in params.items()}
            actions.append(item)
        return self._result({"opened": skill.title, "how": skill.manifest["instructions"], "actions": actions,
                             "note": OPEN_NOTE})

    def _call_use(self, args, heard, screen):  # M13b
        """use_skill: one action of a group in hand or an "always" one, by its name or as "skill__action"."""
        clean, problem = check_args(self._use_skill_declaration()["parameters"], args)
        if problem:
            return self._result({"error": "bad_input", "detail": problem})
        first, sep, rest = clean["action"].partition("__")
        group, act = (first, rest) if sep else (None, first)
        hand, always = self._in_hand(screen), self._always()
        skill = next((s for s in hand if act in s.actions and group in (None, s.name)), None)
        if skill is None:
            skill = next((s for s, a in always if a["name"] == act and group in (None, s.name)), None)
        if skill is None:
            for other in self._sorted():
                if act in other.actions and group in (None, other.name):
                    if other.tripped:  # so she gets not_working and its kind line
                        return self._result({"error": "not_working"}, say=SAY_NOT_WORKING)
                    if self.enabled(other.name):
                        return self._result({"error": "not_open", "open": other.name, "note": NOT_OPEN_NOTE})
            names = [n for s in hand for n in s.actions] + [a["name"] for _, a in always]
            return self._result({"error": "no_such_action", "actions": list(dict.fromkeys(names))})
        schema = skill.actions[act].get("inputSchema", {"type": "object"})
        return self.call(f"{skill.name}__{act}", self._details_args(schema, clean.get("details")), heard=heard)

    @staticmethod
    def _details_args(schema, details):  # M13b
        """use_skill's details text as an action's args: a JSON object if it is one, else the first text field gets it.
        With no text field the args stay empty, and check_args or the handler reports what's missing."""
        props = schema.get("properties")
        text = (details or "").strip()
        if not text or not props:
            return {}
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
        first = next((key for key, prop in props.items() if prop.get("type") == "string"), None)
        return {first: text} if first else {}

    def _track(self, skill, result):  # M13b
        """Keeps opened and aside in step with a skill's own screen (core stamps every show_screen / leave_screen with
        the skill's own name, so the kind is enough). Returns the title of a set-aside skill that's now back, or None."""
        try:
            kinds = {effect.get("kind") for effect in result["effects"]}
            if "show_screen" in kinds:
                self.opened = skill.name
            if "leave_screen" not in kinds:
                return None
            back = self.aside if self.aside and self.aside != skill.name else None
            self.opened = back
            if self.aside == skill.name:
                self.aside = None
            return self.skills[back].title if back and self.enabled(back) else None
        except Exception:
            return None

    def view(self, name):
        """The live "what Mary sees" text of a skill on screen (view(state), at most 600 characters), or None."""
        skill = self.skills.get(name)
        if skill is None or not skill.manifest.get("sees") or not self.enabled(name):
            return None
        out = self._guard(skill, "view", lambda: skill.module.view(skill.state))
        if out is _FAILED:
            return None
        if not isinstance(out, str):
            self._fail(skill, "view", "BadView", message="view() must return text")
            return None
        return out[:VIEW_MAX]

    def on_event(self, name, event):
        """A resident's move on a skill's screen: runs skill.py's on_event(ctx, event) in the guard."""
        skill = self.skills.get(name)
        if skill is None:
            return self._result({"error": "unknown_skill"})
        if skill.tripped or not self.enabled(name):
            return self._result({"error": "not_working" if skill.tripped else "off"})
        handler = getattr(skill.module, "on_event", None)
        if not callable(handler):
            return self._result({"error": "no_events"})
        try:
            ok = isinstance(event, dict) and len(json.dumps(event)) <= RESULT_MAX
        except (TypeError, ValueError):
            ok = False
        if not ok:
            return self._result({"error": "bad_input", "detail": "event must be a small object"})
        ctx = self.context(name)
        ctx.from_page = True  # M15c: the one place this is set
        result = self._finish(skill, "on_event", ctx, self._guard(skill, "on_event", lambda: handler(ctx, event)))  # M13b
        self._track(skill, result)  # M13b
        return result

    def broken(self, name):
        """The page half failed (screen.js threw): counts as one failure toward the trip rule."""
        skill = self.skills.get(name)
        if skill is None:
            return {"error": "unknown_skill"}
        self._fail(skill, "page", "PageError")
        return {"ok": True, "tripped": skill.tripped}

    # ----- offline mode -----

    def offline_match(self, text, is_blocked=None):
        """Offline mode: a skill's offline phrase or "turn <title> on/off" in what the resident said, run as a call.
        Returns the call result (with its say line) or None. Never matches a line is_blocked(text) flags
        (the emergency check), or one with a "don't" or "not" in it."""
        if not text or (is_blocked and is_blocked(text)):
            return None
        plain = _plain(text)
        if not plain or _NEGATION.search(plain):
            return None
        padded = f" {plain} "
        for skill in sorted(self.skills.values(), key=lambda s: -len(s.title)):
            title = re.escape(_plain(skill.title))
            the = r"(?:the |my )?"
            if re.search(rf"\b(?:turn|switch|put) {the}{title} (?:back )?on\b"
                         rf"|\b(?:turn|switch) (?:back )?on {the}{title}\b", plain):
                return self.call("set_skill", {"name": skill.name, "on": True})
            if re.search(rf"\b(?:turn|switch) {the}{title} off\b|\b(?:turn|switch) off {the}{title}\b"
                         rf"|\bstop {the}{title}\b", plain):
                return self.call("set_skill", {"name": skill.name, "on": False})
        best = None
        for skill in self._sorted():
            if skill.manifest["offline"] != "works" or not self.enabled(skill.name):
                continue
            for phrase, action in skill.phrases():
                if f" {phrase} " in padded and (best is None or len(phrase) > len(best[0])):
                    best = (phrase, f"{skill.name}__{action}")
        if not best:
            return None
        out = self.call(best[1], {}, heard=text)  # M7a
        return None if out["response"].get("not_for_me") else out  # M7a: her normal offline line runs instead

    # ----- email (M15d) -----

    def _send_mail(self, skill, ticket, to, subject, body, pictures):
        """ctx.send_mail. This checks the card and the mailer checks the ticket. Logs no address and no content."""
        if not skill.manifest.get("needs", {}).get("send_mail"):
            self._log("mail_refused", skill=skill.name, reason="not_on_card")
            return {"ok": False, "code": "not_on_card", "message": "This skill isn't allowed to send email."}
        if self.mailer is None:
            result = {"ok": False, "code": "no_email", "message": mail_core.MESSAGES["no_email"]}
        else:
            try:
                result = self.mailer(skill.name, ticket, to, subject, body, pictures)
            except Exception:  # noqa: BLE001 (a send that fails is a refusal, never the skill's crash)
                result = {"ok": False, "code": "refused", "message": mail_core.MESSAGES["refused"]}
        self._log("mail", skill=skill.name, ok=result["ok"], code=result.get("code", ""))
        return result

    # ----- the send gate (M15c) -----

    def _resident_line(self, over=False):  # M18
        """Tells each skill with an on_resident_line about one more line of theirs, or the end of the talk. Never raises."""
        for name, skill in list(self.skills.items()):
            handler = getattr(skill.module, "on_resident_line", None)
            if callable(handler) and not skill.tripped:
                try:
                    ctx = self.context(name)
                    self._guard(skill, "on_resident_line", lambda: handler(ctx, over))
                except Exception:  # noqa: BLE001
                    pass

    def talk_over(self):  # M18
        self._resident_line(over=True)

    def resident_said(self, text, garbled=False):
        """The resident's finished words at the gate. None when it has nothing to do with them, else {"action", "say",
        "effects", "skip_brain"}, after the skill's optional on_gate(ctx, action) in the guard. A failure in the gate or
        the skill acts as if there were no gate: nothing sends, she answers normally. Never raises."""
        self._resident_line()  # M18
        gate = self.gate
        if gate is None:
            return None
        try:
            heard = gate.heard(text, garbled=garbled)
            action = heard.get("action")
            if not action:
                return None
            name = gate.skill
            skill = self.skills.get(name)
            if skill is None or skill.tripped or not self.enabled(name):
                gate.disarm(name)  # nothing can finish this send
                return None
            say, effects = heard.get("line"), []
            handler = getattr(skill.module, "on_gate", None)
            if callable(handler):
                ctx = self.context(name)
                result = self._finish(skill, "on_gate", ctx, self._guard(skill, "on_gate", lambda: handler(ctx, action)))
                self._track(skill, result)
                if result["response"].get("error") == "not_working":
                    gate.undo()
                    return None
                say, effects = result["say"] or say, result["effects"]
            return {"action": action, "say": say, "effects": effects, "skip_brain": action in GATE_SKIPS_BRAIN}
        except Exception as err:  # noqa: BLE001
            self._log("gate_failed", error=type(err).__name__)
            try:
                gate.undo()
            except Exception:  # noqa: BLE001
                pass
            return None

    def her_words(self, text):
        """Her finished turn, so the gate knows the line really went out. Never raises."""
        try:
            if self.gate is not None:
                self.gate.her_words(text)
        except Exception as err:  # noqa: BLE001
            self._log("gate_failed", error=type(err).__name__)

    def send_emergency(self):
        """An emergency stops a count. It runs no skill code, so it can't delay the emergency line. Never raises."""
        try:
            if self.gate is not None:
                self.gate.emergency()
        except Exception as err:  # noqa: BLE001
            self._log("gate_failed", error=type(err).__name__)

    def _optional(self, skill, what, *args):
        """A skill's optional module function, in the guard: its value, or None when it has none or it failed."""
        handler = getattr(skill.module, what, None)
        if not callable(handler):
            return None
        ctx = self.context(skill.name)
        out = self._guard(skill, what, lambda: handler(ctx, *args))
        return None if out is _FAILED else out

    def forget_count(self, about):
        """How many contacts match about, across each skill's optional forget_matches(ctx, about)."""
        counts = [self._optional(skill, "forget_matches", about) for skill in list(self.skills.values())]
        return sum(count for count in counts if type(count) is int and count > 0)

    def forget_reach(self, about, own_name=False):
        """A real forget reaches what skills hold, on or off, through each one's optional on_forget(ctx, about, own_name),
        which returns {"addresses": [...], "texts": [...]}. "Everything" comes through as that one word and clears every
        address from mail.log. A skill that removed something loses its look. Returns the addresses and texts, in one list."""
        everything = memory_core.is_everything(about)
        about = "everything" if everything else about
        addresses, texts = [], []
        removed = []
        for skill in list(self.skills.values()):
            out = self._optional(skill, "on_forget", about, own_name)
            if isinstance(out, dict):
                mail = [text for text in out.get("addresses") or [] if isinstance(text, str) and text]
                words = [text for text in out.get("texts") or [] if isinstance(text, str) and text]
                addresses += mail
                texts += words
                if mail or words:
                    removed.append(skill.name)
        self._gate_forgets(removed, None if everything else addresses, everything)
        return addresses + texts

    def _gate_forgets(self, removed, addresses, everything):
        gate = self.gate
        if gate is None:
            return
        try:
            for name in removed:
                gate.disarm(name)
            if everything:
                gate.disarm(gate.skill)
            scrub = getattr(gate.mailer, "scrub_log", None)
            if callable(scrub) and (everything or addresses):
                scrub(addresses)
        except Exception as err:  # noqa: BLE001 (her memories are already gone; this can't undo that)
            self._log("gate_failed", error=type(err).__name__)

    # ----- the internet -----

    def _fetch(self, skill, url, method, params, headers, max_bytes, timeout):
        if self._fetcher is not None:
            return self._fetcher(skill.name, url, method=method, params=params, headers=headers,
                                 max_bytes=max_bytes, timeout=timeout)
        host = ""
        try:
            parts = urllib.parse.urlsplit(str(url))
            host = (parts.hostname or "").lower()
            port = parts.port
        except ValueError:
            parts, port = None, -1
        try:
            result = self._fetch_checked(skill, url, parts, host, port, method, params, headers, max_bytes, timeout)
        except SkillFetchError as err:
            fields = {"status": err.status} if err.status else {}
            self._log("fetch_refused", skill=skill.name, host=host[:100], reason=err.reason, **fields)
            raise
        except urllib.error.HTTPError as err:
            self._log("fetch_failed", skill=skill.name, host=host[:100], status=err.code)
            raise SkillFetchError("http_error", status=err.code) from None
        except Exception as err:  # noqa: BLE001 (any network failure is a refusal for the skill)
            self._log("fetch_failed", skill=skill.name, host=host[:100], error=type(err).__name__)
            raise SkillFetchError("failed") from None
        self._log("fetch", skill=skill.name, host=host[:100], status=result["status"], bytes=len(result["body"]))
        return result

    def _fetch_checked(self, skill, url, parts, host, port, method, params, headers, max_bytes, timeout):
        if not self.online():
            raise SkillFetchError("offline")
        if str(method).upper() != "GET":
            raise SkillFetchError("not_get")
        if parts is None or parts.scheme != "https" or port not in (None, 443) or parts.username or parts.password:
            raise SkillFetchError("not_https" if parts is not None and parts.scheme != "https" else "bad_url")
        if not host_allowed(host, skill.manifest["needs"].get("internet_hosts", [])):
            raise SkillFetchError("host_not_allowed")
        try:
            timeout = max(0.5, min(float(timeout), FETCH_TIMEOUT_MAX))
            max_bytes = min(int(max_bytes), FETCH_BYTES_MAX)
        except (TypeError, ValueError):
            raise SkillFetchError("bad_limits") from None
        if max_bytes <= 0:
            raise SkillFetchError("bad_limits")
        if params:
            query = urllib.parse.urlencode(params, doseq=True)
            url = urllib.parse.urlunsplit(parts._replace(query=f"{parts.query}&{query}" if parts.query else query))
        sent = {"User-Agent": FETCH_AGENT}
        for key, value in (headers or {}).items():
            if str(key).lower() not in ("host", "cookie", "authorization", "content-length", "transfer-encoding"):
                sent[str(key)] = str(value)
        request = urllib.request.Request(str(url), headers=sent, method="GET")
        with _open_url(request, timeout, skill.manifest["needs"].get("internet_hosts", [])) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            length = resp.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > max_bytes:
                raise SkillFetchError("too_big", status=status)
            chunks, total = [], 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise SkillFetchError("too_big", status=status)
                chunks.append(chunk)
            return {"status": status, "content_type": resp.headers.get("Content-Type", ""), "body": b"".join(chunks)}
