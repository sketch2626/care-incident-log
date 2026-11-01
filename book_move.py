"""M19: the old contacts move into the sealed address book, once, and leave incidents.db and its dated backups.

The log is evidence, so every step is checked and a doubt deletes nothing:
- The book is written, then read back from its file, before a single row is removed.
- Only contact rows are removed, in one transaction, and a SHA-256 over everything else has to match afterwards.
- A dated backup is only ever replaced by a cleaned copy that matches it in everything but the contacts, and it keeps
  its date. Any doubt leaves that backup exactly as it was, and the next start tries again.
- A contact found only in an old backup is never brought back: the resident may already have forgotten them.

book_move.log holds counts. No name and no address ever go in it.
"""
import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import address_book

DONE_KEY = "book_moved"  # a setting: '1' once nothing is left to do
CONTACT_ROW = "skill='messages' AND (key='contacts' OR key LIKE 'contact-%')"
ROW_TEXT = ("name", "relationship", "email", "facebook", "phone")  # every field a contact row has
ROW_FLAGS = ("asked", "no_keep")
DETAILS = ("email", "phone", "cell", "address", "facebook", "birthday", "notes")  # the same as skills_core.PERSON_DETAILS
TEMP = ".clean"  # on a backup's copy, so backup_db's incidents_*.db never takes it for a backup
WHOLE = 100000  # past any stored value: _text with this cuts nothing, so a value the book would cut shows up
STOP_LOCKED = "locked"
STOP_MISMATCH = "mismatch"
STOP_CHANGED = "changed"
STOP_JOURNAL = "journal"


def _person(value):
    """One contact row's fields, cleaned, or None when it's malformed: not what the skill wrote, or more than fits whole."""
    try:
        row = json.loads(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(row, dict) or not isinstance(row.get("name"), str):
        return None
    if not all(isinstance(row.get(field, ""), str) for field in ROW_TEXT):
        return None
    if not all(isinstance(row.get(field, False), bool) for field in ROW_FLAGS):
        return None
    record = address_book._clean(row)
    whole = all(record[field] == address_book._text(row.get(field), WHOLE) for field in ROW_TEXT)
    return {field: record[field] for field in address_book.FIELDS} if record["name"] and whole else None


def _is_index(value):
    try:
        slugs = json.loads(value)
    except (TypeError, ValueError):
        return False
    return isinstance(slugs, list) and all(isinstance(slug, str) for slug in slugs)


def _contact_rows(conn):
    """(the people, the keys that may go, how many rows are malformed). The table may not exist yet."""
    try:
        rows = conn.execute("SELECT key, value FROM skill_data WHERE " + CONTACT_ROW).fetchall()
    except sqlite3.OperationalError as err:
        if "no such table" in str(err):
            return [], [], 0
        raise
    people, keys, malformed = [], [], 0
    for key, value in rows:
        person = None if key == "contacts" else _person(value)
        if person is None and not (key == "contacts" and _is_index(value)):
            malformed += 1
            continue
        keys.append(key)
        if person is not None:
            people.append(person)
    return people, keys, malformed


def _mark_only(record):
    return record["no_keep"] and not any(record[field] for field in DETAILS)


def _in_book(book, name):
    """Who's already there by this name, hidden marks too, shown rows first. A doctor is never merged."""
    wanted = address_book._norm(name).casefold()
    found = [person for person in book.people(include_hidden=True)
             if person["kind"] != "doctor" and address_book._norm(person["name"]).casefold() == wanted]
    return sorted(found, key=lambda person: person["hidden"])[0] if found else None


def _wanted(row, there):
    """What the book should say. With someone already there their values stand and only blanks fill, and a "don't keep"
    they've said since still keeps the address out."""
    if there is None:
        return {**row, "hidden": _mark_only(row)}
    record = {field: there[field] for field in address_book.FIELDS}
    for field in ROW_TEXT:
        if not record[field] and not (field == "email" and there["no_keep"]):
            record[field] = row[field]
    for field in ROW_FLAGS:
        record[field] = record[field] or row[field]
    record["hidden"] = there["hidden"] and _mark_only(record)
    return record


def _into_book(book, people):
    """Writes each one and gives back {row id: what it should say}. A locked or full book raises, and nothing's deleted."""
    written = {}
    for row in people:
        there = _in_book(book, row["name"])
        record = _wanted(row, there)
        if there is None:
            written[book.add(record)] = record
            continue
        if record != {field: there[field] for field in address_book.FIELDS}:
            book.update(there["id"], record)
        written[there["id"]] = record
    return written


def _read_back(book, written):
    """From the file, not from memory: lock() drops what's decrypted, and the next read rebuilds from the file."""
    book.lock()
    for row_id, record in written.items():
        got = book.get(row_id)
        if got is None or any(got[field] != record[field] for field in address_book.FIELDS):
            return False
    return True


def _rows(conn, table):
    name = '"%s"' % table.replace('"', '""')
    try:
        return conn.execute(f"SELECT * FROM {name} ORDER BY rowid")
    except sqlite3.OperationalError:  # a table without rowids is read in key order anyway
        return conn.execute(f"SELECT * FROM {name}")


def _fingerprint(conn):
    """A SHA-256 over the schema, every row of every table but skill_data, and every skill_data row but the contacts.
    Rowids aren't in it: VACUUM may renumber a table that has no INTEGER PRIMARY KEY, and it keeps their order."""
    digest = hashlib.sha256()

    def take(rows):
        for row in rows:
            digest.update(repr(tuple(row)).encode("utf-8", "backslashreplace"))

    take(conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE tbl_name != 'skill_data' "
                      "ORDER BY type, name"))
    for table in sorted(row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")):
        digest.update(table.encode("utf-8"))
        take(conn.execute(f"SELECT * FROM skill_data WHERE NOT ({CONTACT_ROW}) ORDER BY skill, key")
             if table == "skill_data" else _rows(conn, table))
    return digest.hexdigest()


def _take_out(db_path, keys):
    """Removes exactly these rows, and VACUUMs so freed text doesn't stay in the file. A free page with nothing to delete
    is a VACUUM that failed last time. False when anything else in the file came out different."""
    with closing(sqlite3.connect(db_path, timeout=5, isolation_level=None)) as conn:
        conn.execute("PRAGMA secure_delete=ON").fetchall()
        if not keys and not conn.execute("PRAGMA freelist_count").fetchone()[0]:
            return True
        before = _fingerprint(conn)
        if keys:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.executemany("DELETE FROM skill_data WHERE skill='messages' AND key=?", [(key,) for key in keys])
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        conn.execute("VACUUM")
        return _fingerprint(conn) == before


def _read_only(path):
    """immutable: SQLite makes no journal or lock file beside it, so an evidence file can't change by being read."""
    return sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)


def _holds_contacts(path):
    with closing(_read_only(path)) as conn:
        try:
            return conn.execute(f"SELECT 1 FROM skill_data WHERE {CONTACT_ROW} LIMIT 1").fetchone() is not None
        except sqlite3.OperationalError as err:
            if "no such table" in str(err):
                return False
            raise


def _drop_temp(temp):
    for ending in ("", "-journal", "-wal", "-shm"):
        try:
            Path(str(temp) + ending).unlink(missing_ok=True)
        except OSError:
            pass


def _clean_one(path):
    """Cleans a copy and swaps it in only on a full match. Whatever happens the temp file goes. False leaves path as it was."""
    temp = path.with_name(path.name + TEMP)
    try:
        shutil.copy2(path, temp)
        with closing(_read_only(path)) as original:
            wanted = _fingerprint(original)
        with closing(sqlite3.connect(temp, isolation_level=None)) as copy:
            copy.execute("PRAGMA secure_delete=ON").fetchall()
            copy.execute("DELETE FROM skill_data WHERE " + CONTACT_ROW)
            copy.execute("VACUUM")
            sound = copy.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            same = _fingerprint(copy) == wanted
            gone = copy.execute(f"SELECT 1 FROM skill_data WHERE {CONTACT_ROW} LIMIT 1").fetchone() is None
        if not (sound and same and gone):
            return False
        times = path.stat()
        os.utime(temp, ns=(times.st_atime_ns, times.st_mtime_ns))
        os.replace(temp, path)
        return True
    finally:
        _drop_temp(temp)


def _clean_backups(backups, counts):
    for stale in backups.glob(f"incidents_*.db{TEMP}*"):  # a start that died half way
        _drop_temp(stale)
    for path in sorted(backups.glob("incidents_*.db")):
        try:
            if not _holds_contacts(path):
                continue
            counts["backups_cleaned" if _clean_one(path) else "backups_left"] += 1
        except Exception:  # noqa: BLE001 (an unreadable backup is left alone, and counted)
            counts["backups_left"] += 1


def _run(db_path, backups, book, counts):
    """The move. Gives back why it stopped short, or "" when it went through."""
    with closing(sqlite3.connect(db_path, timeout=5)) as conn:
        done = conn.execute("SELECT 1 FROM settings WHERE key=?", (DONE_KEY,)).fetchone() is not None
        people, keys, malformed = _contact_rows(conn)
    if done and not keys:
        return ""
    counts["malformed"] = malformed
    if book.state() != "open":
        return STOP_LOCKED
    if people and not _read_back(book, _into_book(book, people)):
        return STOP_MISMATCH
    counts["moved"] = len(people)
    if not _take_out(db_path, keys):
        return STOP_CHANGED
    _clean_backups(backups, counts)
    if any(Path(str(db_path) + ending).exists() for ending in ("-journal", "-wal")):
        return STOP_JOURNAL
    if not counts["backups_left"]:
        with closing(sqlite3.connect(db_path, timeout=5)) as conn, conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, '1')", (DONE_KEY,))
    return ""


def _log(path, stopped, counts):
    try:
        with open(path, "a", encoding="utf-8") as out:
            out.write(json.dumps({"when": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "stopped": stopped, **counts}) + "\n")
    except OSError:
        pass


def run(db_path, backups, book, log_path):
    """Moves what's left to move. Never raises: a move that stops leaves the rest where it was, and the next start retries."""
    counts = {"moved": 0, "malformed": 0, "backups_cleaned": 0, "backups_left": 0}
    try:
        stopped = _run(Path(db_path), Path(backups), book, counts)
    except Exception as err:  # noqa: BLE001 (its type only: a message could hold a name)
        stopped = type(err).__name__
    if stopped or any(counts.values()):
        _log(log_path, stopped, counts)
