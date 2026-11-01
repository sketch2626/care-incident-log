"""The address book (M19): who the resident knows, sealed in its own file.

mary/addressbook.db holds one AES-256-GCM blob per person, names included, so the file has no readable list of anyone.
The key is random and lives in secret_store, on this computer only. The book decrypts into memory while the app runs.

Two rules never bend. There's no plain fallback: no key, no library or no safe store means the book is locked. And a
locked book is left exactly as it was: a key is only ever made for a book with nothing in it, and nothing is wiped.

Only this module imports cryptography, and server.py still runs if that import fails.
"""
import base64
import json
import os
import re
import sqlite3
import threading
import unicodedata
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from secrets import token_bytes, token_hex

import secret_store

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_OK = True
except Exception:  # missing, or a broken build's bad DLL: the book stays shut
    AESGCM = None
    CRYPTO_OK = False

KEY_NAME = "address_book_key"
KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12
BOUND_TO = b"addressbook-v1:"
CHECK_ID = "check"  # the meta row. Row ids are 32 hex characters, so it can't be mistaken for a person
CHECK_TEXT = b"address book check"

MAX_PEOPLE = 500
MAX_NAME = 60
MAX_NOTES = 1000
MAX_TEXT = 254

FIELDS = ("name", "relationship", "email", "phone", "cell", "address", "facebook", "birthday", "notes", "kind",
          "asked", "no_keep", "hidden")
TEXT_FIELDS = ("name", "relationship", "email", "phone", "cell", "address", "facebook", "notes")
FLAG_FIELDS = ("asked", "no_keep", "hidden")
LINES_KEPT = ("address", "notes")
KINDS = ("person", "doctor")  # "doctor" is reserved for later: stored, with no logic of its own

WHY_UNAVAILABLE = "unavailable"  # no cryptography library, or no safe place for the key
WHY_KEY = "key"  # the key is missing or doesn't fit
WHY_FILE = "file"  # the file can't be read

CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")  # a line break stays, for the fields that keep them
BIRTHDAY = re.compile(r"(?:([0-9]{4})-)?([0-9]{2})-([0-9]{2})")


class BookError(Exception):
    """Base class. The message is fixed plain text, so it can never carry a name or an address."""
    message = "the address book couldn't do that"

    def __str__(self):
        return self.message


class BookLocked(BookError):
    message = "the address book is locked"


class BookFull(BookError):
    message = "the address book is full"


def _text(value, limit, lines=False):
    text = unicodedata.normalize("NFC", "" if value is None else str(value))
    text = CONTROL.sub(" ", text.encode("utf-8", "ignore").decode("utf-8"))  # a lone surrogate can't be sealed
    return (text if lines else " ".join(text.split())).strip()[:limit].strip()


def _birthday(value):
    """"MM-DD", or "YYYY-MM-DD" when the year is known. Anything else, or a date that can't be, gives ""."""
    text = _text(value, MAX_TEXT)
    found = BIRTHDAY.fullmatch(text)
    if not found:
        return ""
    try:
        date(int(found.group(1) or 2000), int(found.group(2)), int(found.group(3)))  # 2000 was a leap year: 02-29 stands
    except ValueError:
        return ""
    return text


def _clean(fields):
    """Exactly FIELDS, whatever came in."""
    limits = {"name": MAX_NAME, "notes": MAX_NOTES}
    record = {name: _text(fields.get(name), limits.get(name, MAX_TEXT), name in LINES_KEPT) for name in TEXT_FIELDS}
    record["birthday"] = _birthday(fields.get("birthday"))
    record["kind"] = fields.get("kind") if fields.get("kind") in KINDS else "person"
    record.update((name, bool(fields.get(name))) for name in FLAG_FIELDS)
    return {name: record[name] for name in FIELDS}


def _merged(old, fields):
    """Only FIELDS are taken. A blank name or an unusable birthday leaves the one already there."""
    record = _clean({**old, **{name: value for name, value in fields.items() if name in FIELDS}})
    if not record["name"]:
        record["name"] = old["name"]
    if _text(fields.get("birthday"), MAX_TEXT) and not record["birthday"]:
        record["birthday"] = old["birthday"]
    return record


def _norm(name):  # the same as _norm in skills/messages/skill.py
    text = _text(name, MAX_TEXT, True).lower().replace("’", "'").strip()
    return " ".join(re.sub(r"^(?:my|our)\s+", "", text).split())


def _both_named(person, wanted):
    """"My daughter Sarah": the relationship and the first name together. Either one alone never gets here."""
    words, first, relation = wanted.split(), _norm(person["name"]).split()[:1], _norm(person["relationship"])
    return bool(first and relation) and first[0] in words and set(relation.split()) <= set(words)


def _bound(row_id):
    """The row id goes into the seal, so a blob moved to another row won't open."""
    return BOUND_TO + row_id.encode("utf-8")


def _seal(aes, row_id, plain):
    nonce = os.urandom(NONCE_BYTES)
    return nonce, aes.encrypt(nonce, plain, _bound(row_id))


def _unseal(aes, row_id, nonce, sealed):
    """The plain bytes, or None when this blob doesn't open here."""
    try:
        return aes.decrypt(nonce, sealed, _bound(row_id))
    except Exception:
        return None


def _parsed(plain):
    """The record inside an opened blob, or None if it isn't one."""
    try:
        found = json.loads(plain)
    except (TypeError, ValueError):
        return None
    record = _clean(found) if isinstance(found, dict) else None
    return record if record and record["name"] else None


def _gone(path):
    """True when the file no longer exists."""
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


class AddressBook:
    """One resident's book. Every call opens and closes its own connection. secrets is a secret_store.SecretStore."""

    def __init__(self, data_dir, secrets):
        self.path = Path(data_dir) / "mary" / "addressbook.db"
        self.backup_path = self.path.with_name("addressbook_backup.db")
        self._secrets = secrets
        self._lock = threading.RLock()
        self._backup_stale = False  # a fresh rewrite failed and the old copy couldn't be removed either
        self.on_change = None  # called as (kind, person_id, record or None) after a committed add, update, remove or clear
        self._forget()

    def __repr__(self):
        with self._lock:
            return f"<AddressBook people={'?' if self._cache is None else self._shown()}>"

    # What's held in memory

    def _forget(self):
        self._key = self._aes = self._cache = None
        self._damaged = 0
        self._check_ok = False  # True once the meta row is known to open with this key

    def _shown(self):
        return sum(1 for record in self._cache.values() if not record["hidden"])

    # Opening

    def _connect(self):
        """secure_delete: SQLite overwrites what a delete frees. The journal mode stays the default, so no WAL lingers."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute("PRAGMA secure_delete=ON")
        return conn

    @staticmethod
    def _make_tables(conn):
        """No other columns: nothing readable, no timestamps."""
        conn.execute("CREATE TABLE IF NOT EXISTS people(id TEXT PRIMARY KEY, nonce BLOB NOT NULL, sealed BLOB NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, nonce BLOB, sealed BLOB)")

    def _stored_key(self):
        """The key the store holds, or None. A value that isn't a 256-bit key counts as none."""
        value = self._secrets.get(KEY_NAME)
        if value is None:
            return None
        try:
            key = base64.b64decode(value, validate=True)
        except ValueError:
            return None
        return key if len(key) == KEY_BYTES else None

    def _read_file(self):
        """The meta row and every person's row as they stand. Reading never makes the file."""
        if not self.path.exists():
            return None, []
        with closing(self._connect()) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            check = conn.execute("SELECT nonce, sealed FROM meta LIMIT 1").fetchone() if "meta" in tables else None
            rows = conn.execute("SELECT id, nonce, sealed FROM people").fetchall() if "people" in tables else []
        return check, rows

    def _load(self, key, check, rows):
        """Decrypts the rows. False when the key doesn't fit: neither the check value nor any row opens with it.
        A row that won't open under a key that fits is damaged: skipped, counted and left in the file."""
        aes = AESGCM(key)
        cache, damaged = {}, 0
        for row_id, nonce, sealed in rows:
            record = _parsed(_unseal(aes, row_id, nonce, sealed))
            if record is None:
                damaged += 1
            else:
                cache[row_id] = record
        check_ok = check is not None and _unseal(aes, CHECK_ID, *check) == CHECK_TEXT
        if not check_ok and not cache:
            return False
        self._key, self._aes, self._cache, self._damaged, self._check_ok = key, aes, cache, damaged, check_ok
        return True

    def _try_open(self):
        """"" when the book is open, else why not. It reads the key every time, so a key that goes missing locks the
        book at once, and it only ever reads: a locked book stays byte for byte as it was."""
        if not CRYPTO_OK:
            self._forget()
            return WHY_UNAVAILABLE
        try:
            key = self._stored_key()
        except Exception:  # secret_store.NotAvailable, or anything else a backend throws
            self._forget()
            return WHY_UNAVAILABLE
        if key is not None and key == self._key:
            return ""
        self._forget()
        try:
            check, rows = self._read_file()
        except (sqlite3.Error, OSError):
            return WHY_FILE
        if check is None and not rows:  # nothing in it yet. The first write makes what's missing
            self._key, self._aes, self._cache = key, AESGCM(key) if key else None, {}
            return ""
        return "" if key is not None and self._load(key, check, rows) else WHY_KEY

    def _require(self):
        if self._try_open():
            raise BookLocked()

    def state(self):
        """"open" or "locked". Never raises."""
        return "locked" if self.why_locked() else "open"

    def why_locked(self):
        """"" when open, else "unavailable", "key" or "file". Never raises."""
        try:
            with self._lock:
                return self._try_open()
        except Exception:
            return WHY_UNAVAILABLE

    def lock(self):
        """Drops everything decrypted. The file is the truth, and the next call rebuilds from it."""
        with self._lock:
            self._forget()

    # Writing

    def _changed(self, kind, row_id=None, record=None):
        """Tells on_change what was just committed. A fault there never reaches the book's caller."""
        if self.on_change is None:
            return
        try:
            self.on_change(kind, row_id, dict(record) if record else None)
        except Exception:
            pass

    def _sealer(self):
        """The cipher for a write. This is the only place a key is ever made, and _aes is empty only when _try_open has
        just found a book with no rows and no meta. A key the store won't give back is never used."""
        if self._aes is None:
            key = token_bytes(KEY_BYTES)
            try:
                self._secrets.put(KEY_NAME, base64.b64encode(key).decode("ascii"))
                kept = self._stored_key()
            except Exception:
                raise BookLocked() from None
            if kept != key:
                raise BookLocked()
            self._key, self._aes = key, AESGCM(key)
        return self._aes

    def _store(self, row_id, record):
        """Seals one row and writes it. The cache changes only once it's on disk."""
        aes = self._sealer()
        nonce, sealed = _seal(aes, row_id, json.dumps(record, ensure_ascii=False).encode("utf-8"))
        with closing(self._connect()) as conn, conn:
            self._make_tables(conn)
            if not self._check_ok:
                conn.execute("INSERT OR REPLACE INTO meta(key, nonce, sealed) VALUES(?, ?, ?)",
                             (CHECK_ID, *_seal(aes, CHECK_ID, CHECK_TEXT)))
            conn.execute("INSERT OR REPLACE INTO people(id, nonce, sealed) VALUES(?, ?, ?)", (row_id, nonce, sealed))
        self._check_ok = True
        self._cache[row_id] = record

    def add(self, fields):
        """Adds a person and gives back the new id. The id is random, never made from the name."""
        record = _clean(fields)
        if not record["name"]:
            raise ValueError("A name is needed.")
        with self._lock:
            self._require()
            if not record["hidden"] and self._shown() >= MAX_PEOPLE:
                raise BookFull()
            row_id = token_hex(16)
            self._store(row_id, record)
            self._changed("add", row_id, record)
        return row_id

    def update(self, row_id, fields):
        """Merges fields into a person. False when there's no such person."""
        with self._lock:
            self._require()
            old = self._cache.get(row_id)
            if old is None:
                return False
            record = _merged(old, fields)
            if old["hidden"] and not record["hidden"] and self._shown() >= MAX_PEOPLE:
                raise BookFull()
            self._store(row_id, record)
            self._changed("update", row_id, record)
        return True

    def remove(self, row_id):
        """A real delete, and the rolling copy is rewritten at once. False when there's no such person."""
        with self._lock:
            self._require()
            if row_id not in self._cache:
                return False
            with closing(self._connect()) as conn, conn:
                conn.execute("DELETE FROM people WHERE id=?", (row_id,))
            del self._cache[row_id]
            self.backup(fresh=True)
            self._changed("remove", row_id)
        return True

    def clear(self):
        """Removes every row, damaged and hidden ones too, and gives back how many. The key and meta stay."""
        with self._lock:
            self._require()
            if not self.path.exists():
                return 0
            with closing(self._connect()) as conn:
                self._make_tables(conn)
                with conn:
                    removed = conn.execute("DELETE FROM people").rowcount
                conn.execute("VACUUM")
            self._cache, self._damaged = {}, 0
            self.backup(fresh=True)
            self._changed("clear")
        return removed

    # Reading

    def get(self, row_id):
        with self._lock:
            self._require()
            record = self._cache.get(row_id)
            return {"id": row_id, **record} if record is not None else None

    def people(self, include_hidden=False):
        """Sorted by name. A hidden "don't ask" mark is never in the list unless asked for."""
        with self._lock:
            self._require()
            found = [{"id": row_id, **record} for row_id, record in self._cache.items()
                     if include_hidden or not record["hidden"]]
        return sorted(found, key=lambda person: (person["name"].casefold(), person["id"]))

    def find(self, words, include_hidden=False):
        """By exact name, else first name or relationship, else relationship and first name together, without case.
        Hidden marks match only when asked for. More than one back means she asks which."""
        wanted, every = _norm(words), self.people(include_hidden)
        if not wanted:
            return []
        return [p for p in every if _norm(p["name"]) == wanted] or [
            p for p in every if _norm(p["name"]).split()[:1] == [wanted] or _norm(p["relationship"]) == wanted] or [
            p for p in every if _both_named(p, wanted)]

    def count(self):
        """How many people are in the list."""
        with self._lock:
            self._require()
            return self._shown()

    def damaged(self):
        """How many rows won't open with the right key. They stay in the file."""
        with self._lock:
            self._require()
            return self._damaged

    # The rolling copy: sealed like the book, because it's a plain copy of the sealed file

    def _backup_is_today(self):
        try:
            return datetime.fromtimestamp(self.backup_path.stat().st_mtime).date() == datetime.now().date()
        except OSError:
            return False

    def backup(self, fresh=False):
        """One rolling copy, swapped in whole: once a day, and at once after every remove or clear (fresh), so nothing
        removed stays in it. If that rewrite fails the copy is deleted: no copy beats a stale copy. Never raises.
        The daily copy waits while the book is locked, because the copy already there may be the last good one."""
        with self._lock:
            fresh = fresh or self._backup_stale
            tmp = self.backup_path.with_suffix(".tmp")
            try:
                if not fresh and (self._backup_is_today() or self._try_open()):
                    return
                if not self.path.exists():  # connecting would make the file
                    raise FileNotFoundError()
                tmp.unlink(missing_ok=True)
                with closing(self._connect()) as src, closing(sqlite3.connect(tmp)) as dst:
                    dst.execute("PRAGMA secure_delete=ON")
                    src.backup(dst)
                os.replace(tmp, self.backup_path)
                self._backup_stale = False
            except Exception:
                _gone(tmp)
                if fresh:
                    self._backup_stale = not _gone(self.backup_path)
