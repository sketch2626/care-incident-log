"""T1: Andy's tuck-away test list beside Mary. For his own testing, never for residents.

server.py loads this file by path, only when running from source, so it can't land in the installer.
It shows only while private/testing/list.md exists; deleting that file turns it off at once.
It touches nothing but list.md (read) and results.json (written), and no path ever comes from the page.
"""
import json
import os
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[2] / "private" / "testing"
HERE = Path(__file__).resolve().parent
MAX_NOTE = 4000
MARKS = ("worked", "didnt", None)
DRAWER_TAGS = (b'<link rel="stylesheet" href="/api/mary/testlist/drawer.css">'
               b'<script src="/api/mary/testlist/drawer.js"></script>\n')
_lock = threading.Lock()


def _list_file():
    return FOLDER / "list.md"


def _results_file():
    return FOLDER / "results.json"


def list_exists():
    return _list_file().is_file()


def with_drawer(page):
    """Mary's page, with the drawer's two tags just before </body>."""
    at = page.rfind(b"</body>")
    return page + DRAWER_TAGS if at < 0 else page[:at] + DRAWER_TAGS + page[at:]


def parse(text):
    """The list file: {title, sections:[{name, entries, items}]}. Anything that isn't a heading or an
    item stays as a plain line, in its place. Items before any ## sit in a section named ""."""
    title = ""
    current = {"name": "", "entries": [], "items": []}
    sections = [current]
    for raw in text.splitlines():
        line = raw.strip()
        heading = re.fullmatch(r"##\s+(.+)", line)
        top = re.fullmatch(r"#\s+(.+)", line)
        item = re.fullmatch(r"-\s+(.+)", line)
        if not line:
            continue
        if top and not title:
            title = top.group(1).strip()
        elif heading:
            current = {"name": heading.group(1).strip(), "entries": [], "items": []}
            sections.append(current)
        elif item:
            entry = {"type": "item", "id": f"{len(sections)}-{len(current['entries'])}",
                     "text": item.group(1).strip(), "mark": None, "note": "", "time": None}
            current["entries"].append(entry)
            current["items"].append(entry)
        else:
            current["entries"].append({"type": "line", "text": line})
    return {"title": title or "Test list", "sections": [s for s in sections if s["name"] or s["entries"]]}


def _read_list():
    return parse(_list_file().read_text(encoding="utf-8-sig", errors="replace"))


def _load():
    """(records, whether the file is unreadable). A corrupt file counts as empty and is never a crash."""
    try:
        raw = _results_file().read_bytes()
    except OSError:
        return [], False
    try:
        records = json.loads(raw.decode("utf-8-sig"))["items"]
        if isinstance(records, list) and all(isinstance(r, dict) and isinstance(r.get("section"), str)
                                             and isinstance(r.get("item"), str) for r in records):
            return records, False
    except (ValueError, KeyError, TypeError):  # bad JSON and bad UTF-8 are both ValueError
        pass
    return [], True


def _save(records, corrupt):
    """Atomic: the old file stays whole until the new one is complete."""
    path = _results_file()
    if corrupt:
        os.replace(path, path.with_name("results.bad.json"))
    fd, tmp = tempfile.mkstemp(dir=FOLDER, prefix="results.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"items": records}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _on_list(listing):
    return {(s["name"], i["text"]) for s in listing["sections"] for i in s["items"]}


def _find(records, section, text, live):
    """Same section and text first. Otherwise an item moved to a new section keeps its mark: a lone record
    with that text whose old place is gone. A record still on the list elsewhere belongs to that place."""
    for r in records:
        if r.get("section") == section and r.get("item") == text:
            return r
    moved = [r for r in records if r.get("item") == text and (r.get("section"), text) not in live]
    return moved[0] if len(moved) == 1 else None


def current():
    """The list as it stands now, with its marks. Reads only; never writes."""
    listing = _read_list()
    records = _load()[0]
    live = _on_list(listing)
    for section in listing["sections"]:
        for item in section["items"]:
            found = _find(records, section["name"], item["text"], live)
            if found:
                item.update(mark=found.get("mark"), note=found.get("note") or "", time=found.get("time"))
    return listing


def mark(data):
    """Save one item's mark and note. Raises ValueError for anything that isn't on the list right now."""
    section, text, value, note = data.get("section"), data.get("item"), data.get("mark"), data.get("note", "")
    if not isinstance(section, str) or not isinstance(text, str) or not isinstance(note, str):
        raise ValueError("That request didn't look right.")
    if value not in MARKS:
        raise ValueError("That mark isn't one I know.")
    if len(note) > MAX_NOTE:
        raise ValueError("That note is too long.")
    live = _on_list(_read_list())
    if (section, text) not in live:
        raise ValueError("That item isn't on the list.")
    with _lock:
        records, corrupt = _load()
        found = _find(records, section, text, live)
        if value is None and not note.strip():  # cleared: nothing left to remember
            if found:
                records.remove(found)
            _save(records, corrupt)
            return {"item": text, "section": section, "mark": None, "note": "", "time": None}
        if not found:
            found = {}
            records.append(found)
        found.update(item=text, section=section, mark=value, note=note,
                     time=datetime.now().astimezone().isoformat(timespec="seconds"))
        _save(records, corrupt)
        return found


def reset():
    with _lock:
        _save([], _load()[1])
    return {"ok": True}


def route(handler, method, path):
    """Every testlist route. Returns None for a path that isn't one, which gives the normal 404."""
    if method == "GET" and path == "/api/mary/testlist":
        return handler._send(current())
    if method == "GET" and path == "/api/mary/testlist/drawer.js":
        return handler._send((HERE / "drawer.js").read_bytes(), ctype="text/javascript; charset=utf-8")
    if method == "GET" and path == "/api/mary/testlist/drawer.css":
        return handler._send((HERE / "drawer.css").read_bytes(), ctype="text/css; charset=utf-8")
    if method == "POST" and path == "/api/mary/testlist/mark":
        return handler._send(mark(handler._body()))
    if method == "POST" and path == "/api/mary/testlist/reset":
        return handler._send(reset())
    return None
