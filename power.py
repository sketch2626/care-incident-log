"""Keep Mary's screen awake while the laptop is plugged in.

Rule: plugged in (or power state unknown) -> the display never turns off.
On battery -> normal Windows screen timeout. The hold is released when the
KeepAwake thread stops (Mary's window closes).

Stdlib only. Imports cleanly on non-Windows, where everything is a no-op.
"""
import ctypes
import sys
import threading

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_uint32),
        ("BatteryFullLifeTime", ctypes.c_uint32),
    ]


def plugged_in():
    """True on AC power (or a desktop with no battery), False on battery, None if unknown."""
    try:
        if sys.platform != "win32":
            return None
        status = SYSTEM_POWER_STATUS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return None
        if status.BatteryFlag == 128:  # no system battery: a desktop
            return True
        if status.ACLineStatus == 1:
            return True
        if status.ACLineStatus == 0:
            return False
        return None
    except Exception:
        return None


def keep_display_on(p):
    """Unknown power counts as plugged in."""
    return p is not False


def _default_set_state(flags):
    if sys.platform != "win32":
        return 0
    fn = ctypes.windll.kernel32.SetThreadExecutionState
    fn.restype = ctypes.c_uint32
    fn.argtypes = [ctypes.c_uint32]
    return fn(flags)


class KeepAwake:
    """Daemon thread that holds the display on while plugged in.

    SetThreadExecutionState is per thread, so every set and the final release
    happen on this thread.
    """

    def __init__(self, interval=30, plugged=plugged_in, set_state=None):
        self.interval = interval
        self._plugged = plugged
        self._set_state = set_state or _default_set_state
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="KeepAwake", daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False

    def _apply(self, flags):
        try:
            self._set_state(flags)
        except Exception:
            pass

    def _run(self):
        wanted = None
        while not self._stop.is_set():
            try:
                p = self._plugged()
            except Exception:
                p = None
            flags = (ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED
                     if keep_display_on(p) else ES_CONTINUOUS)
            if flags != wanted:
                self._apply(flags)
                wanted = flags
            self._stop.wait(self.interval)
        self._apply(ES_CONTINUOUS)
