"""Is there a real printer on this computer? (M17)

Stdlib only. It asks Windows directly (winspool.drv), so no console window flashes. Skills read the answer through
ctx.has_printer() and never the system. Any error, or a system that isn't Windows, counts as no printer.
"""
import ctypes
import re
import sys
import threading
import time
from ctypes import wintypes

PRINTER_ENUM_LOCAL = 0x2
PRINTER_ENUM_CONNECTIONS = 0x4
PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x400
NOT_PAPER = ("pdf", "xps", "onenote")  # these print to a file, never onto paper; "fax" is matched as a whole word
CACHE_SECONDS = 30

_override = None  # a test hook: when not None, has_printer returns it
_lock = threading.Lock()
_cached = None
_cached_at = 0.0


class _PrinterInfo2(ctypes.Structure):  # PRINTER_INFO_2W
    _fields_ = [("pServerName", wintypes.LPWSTR), ("pPrinterName", wintypes.LPWSTR), ("pShareName", wintypes.LPWSTR),
                ("pPortName", wintypes.LPWSTR), ("pDriverName", wintypes.LPWSTR), ("pComment", wintypes.LPWSTR),
                ("pLocation", wintypes.LPWSTR), ("pDevMode", ctypes.c_void_p), ("pSepFile", wintypes.LPWSTR),
                ("pPrintProcessor", wintypes.LPWSTR), ("pDatatype", wintypes.LPWSTR), ("pParameters", wintypes.LPWSTR),
                ("pSecurityDescriptor", ctypes.c_void_p), ("Attributes", wintypes.DWORD), ("Priority", wintypes.DWORD),
                ("DefaultPriority", wintypes.DWORD), ("StartTime", wintypes.DWORD), ("UntilTime", wintypes.DWORD),
                ("Status", wintypes.DWORD), ("cJobs", wintypes.DWORD), ("AveragePPM", wintypes.DWORD)]


def is_real(name, attributes=0):
    """True for a printer that puts ink on paper now: not a PDF, XPS, OneNote or fax one, and not set to work offline."""
    low = str(name or "").lower()
    if not low or any(word in low for word in NOT_PAPER) or re.search(r"\bfax\b", low):
        return False
    return not attributes & PRINTER_ATTRIBUTE_WORK_OFFLINE


def _listed():
    """(name, attributes) of each printer Windows knows about. It can raise; _look catches that."""
    enum = ctypes.WinDLL("winspool.drv").EnumPrintersW
    enum.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                     ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    enum.restype = wintypes.BOOL
    flags = PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    needed, count = wintypes.DWORD(0), wintypes.DWORD(0)
    enum(flags, None, 2, None, 0, ctypes.byref(needed), ctypes.byref(count))  # this one only asks how much room it needs
    if not needed.value:
        return []
    room = ctypes.create_string_buffer(needed.value)
    if not enum(flags, None, 2, room, needed.value, ctypes.byref(needed), ctypes.byref(count)):
        return []
    rows = ctypes.cast(room, ctypes.POINTER(_PrinterInfo2))
    return [(rows[i].pPrinterName, rows[i].Attributes) for i in range(count.value)]


def _look():
    if sys.platform != "win32":
        return False
    try:
        return any(is_real(name, attributes) for name, attributes in _listed())
    except Exception:  # noqa: BLE001 (a failed look counts as no printer)
        return False


def has_printer():
    """True when this computer has a real printer. Remembered for 30 seconds, and it never raises."""
    global _cached, _cached_at
    if _override is not None:
        return _override
    with _lock:
        now = time.monotonic()
        if _cached is None or now - _cached_at >= CACHE_SECONDS:
            _cached, _cached_at = _look(), now
        return _cached
