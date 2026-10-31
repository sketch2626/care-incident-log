"""Secrets kept out of the log (M15d): the resident's Gemini key today, more later.

On Windows they sit in Credential Manager, on this computer only. Every entry's name carries a hash of the data
folder, so a scratch install can never see the real resident's secrets. Stdlib only.
"""
import ctypes
import hashlib
import os
import re
import sys
import threading
from ctypes import wintypes

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2  # this computer only, never enterprise or roaming
ERROR_NOT_FOUND = 1168
USER_NAME = "CareIncidentLog"

MAX_BLOB = 2560  # CRED_MAX_CREDENTIAL_BLOB_SIZE: the most one entry can hold
MAX_VALUE = 20000
HEAD_ROOM = MAX_BLOB - len(b"v1:99:01234567:")  # the head entry also carries "v1:<n>:<check>:"
MAX_PARTS = 2 + (MAX_VALUE - HEAD_ROOM) // MAX_BLOB  # the most entries one value can take, head included
NAME = re.compile(r"[a-z][a-z0-9_]{0,40}")
HEAD = re.compile(rb"v1:([1-9][0-9]*):([0-9a-f]{8}):")


class SecretStoreError(Exception):
    """Base class. The message is fixed plain text, so it can never carry a secret."""
    message = "couldn't keep this safe"

    def __str__(self):
        return self.message


class NotAvailable(SecretStoreError):
    message = "not available on this computer"


class TooLong(SecretStoreError):
    message = "too long to keep"


def _check(data):
    """Tells a whole value from an old head joined to new parts, when a save was cut off partway."""
    return hashlib.sha256(data).hexdigest()[:8].encode("ascii")


class CREDENTIALW(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR)]


class MemoryBackend:
    """Keeps everything in this process. For tests."""

    def __init__(self):
        self.data = {}
        self._lock = threading.Lock()

    def read(self, target):
        with self._lock:
            return self.data.get(target)

    def write(self, target, data):
        with self._lock:
            self.data[target] = bytes(data)

    def delete(self, target):
        with self._lock:
            self.data.pop(target, None)

    def clear(self):
        with self._lock:
            self.data.clear()


class WindowsBackend:
    """Windows Credential Manager. dll stands in for advapi32 in tests, so they never reach the real store."""

    def __init__(self, dll=None):
        dll = dll or ctypes.WinDLL("advapi32", use_last_error=True)
        pointer = ctypes.POINTER(CREDENTIALW)
        self._write = dll.CredWriteW
        self._write.argtypes = [pointer, wintypes.DWORD]
        self._write.restype = wintypes.BOOL
        self._read = dll.CredReadW
        self._read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(pointer)]
        self._read.restype = wintypes.BOOL
        self._delete = dll.CredDeleteW
        self._delete.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._delete.restype = wintypes.BOOL
        self._free = dll.CredFree
        self._free.argtypes = [ctypes.c_void_p]
        self._free.restype = None

    def read(self, target):
        found = ctypes.POINTER(CREDENTIALW)()
        if not self._read(target, CRED_TYPE_GENERIC, 0, ctypes.byref(found)):
            if ctypes.get_last_error() == ERROR_NOT_FOUND:
                return None
            raise NotAvailable()
        try:
            cred = found.contents
            size = cred.CredentialBlobSize
            return ctypes.string_at(cred.CredentialBlob, size) if size else b""
        finally:
            self._free(found)

    def write(self, target, data):
        blob = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        cred = CREDENTIALW()
        cred.Type = CRED_TYPE_GENERIC
        cred.TargetName = target
        cred.CredentialBlobSize = len(data)
        cred.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        cred.Persist = CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = USER_NAME
        if not self._write(ctypes.byref(cred), 0):
            raise NotAvailable()

    def delete(self, target):
        if not self._delete(target, CRED_TYPE_GENERIC, 0) and ctypes.get_last_error() != ERROR_NOT_FOUND:
            raise NotAvailable()


class UnavailableBackend:
    """A computer with nowhere safe to keep secrets."""

    def read(self, target):
        raise NotAvailable()

    def write(self, target, data):
        raise NotAvailable()

    def delete(self, target):
        raise NotAvailable()


def default_backend():
    if sys.platform != "win32":
        return UnavailableBackend()
    try:
        return WindowsBackend()
    except (OSError, AttributeError):
        return UnavailableBackend()


_backend = None


def set_backend(backend):
    global _backend
    _backend = backend


def _current_backend():
    global _backend
    if _backend is None:
        _backend = default_backend()
    return _backend


class SecretStore:
    """Named secrets for one data folder. The backend is looked up at each call, so tests can swap it."""

    def __init__(self, data_dir):
        folder = os.path.normcase(os.path.abspath(str(data_dir)))
        self._prefix = "CareIncidentLog/" + hashlib.sha256(folder.encode("utf-8", "surrogatepass")).hexdigest()[:16]

    def _target(self, name):
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError("That isn't a usable secret name.")
        return f"{self._prefix}/{name}"

    def get(self, name):
        """The value, or None if there's none. A missing, damaged or mismatched piece also gives None, never half a secret."""
        target = self._target(name)
        backend = _current_backend()
        head = backend.read(target)
        found = HEAD.match(head) if head is not None else None
        if found is None:
            return None
        chunks = [head[found.end():]]
        for i in range(1, int(found.group(1))):
            part = backend.read(f"{target}#{i}")
            if part is None:
                return None
            chunks.append(part)
        data = b"".join(chunks)
        if _check(data) != found.group(2):
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def put(self, name, value):
        """Parts first and the head last, then whatever an older, longer value left behind."""
        target = self._target(name)
        try:
            data = value.encode("utf-8")
        except UnicodeEncodeError:  # its error object would carry the whole value
            raise SecretStoreError() from None
        if len(data) > MAX_VALUE:
            raise TooLong()
        chunks = [data[:HEAD_ROOM]] + [data[i:i + MAX_BLOB] for i in range(HEAD_ROOM, len(data), MAX_BLOB)]
        backend = _current_backend()
        for i, chunk in enumerate(chunks[1:], 1):
            backend.write(f"{target}#{i}", chunk)
        backend.write(target, b"v1:%d:%s:" % (len(chunks), _check(data)) + chunks[0])
        for i in range(len(chunks), MAX_PARTS):
            backend.delete(f"{target}#{i}")

    def delete(self, name):
        """The head goes first, so stopping partway leaves nothing readable."""
        target = self._target(name)
        backend = _current_backend()
        backend.delete(target)
        for i in range(1, MAX_PARTS):
            backend.delete(f"{target}#{i}")

    def available(self):
        try:
            _current_backend().read(self._target("available_check"))
            return True
        except SecretStoreError:
            return False
