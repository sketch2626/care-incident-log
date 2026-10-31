"""First-run laptop speed check (M8): after Mary's window is up, time Kokoro, Whisper and the
wake word in a low-priority child process and pick a tier, so a slow laptop gets lighter
settings with no human tuning. It must never delay her first hello.

The timing runs in a child so it can't hold voices._kokoro_lock or speech._transcribe_lock,
can't crash Mary if an old CPU hits an illegal instruction, can be killed, and frees its RAM.

desktop.py reaches the child path first thing, so nothing heavy is imported at the top of
this module (no numpy, no server, no voices). A tier change applies at the next model load,
which means the next app start. Thresholds and the light table come from real measurements
(tools/laptop_check.py, numbers in docs/mary-roadmap.md under M8).
"""
import ctypes
import gc
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

from version import VERSION

log = logging.getLogger("care.speedcheck")

SETTING_KEY = "laptop_check"
CHECK_SENTENCE = "It's a pretty day out, and I'm glad you stopped by."  # one sentence: Mary speaks one at a time
CLIP_PATH = Path(__file__).parent / "mary" / "laptop_check_clip.wav"  # 16 kHz mono 16-bit, Kokoro's voice
CLIP_RATE = 16000
WAKE_BLOCK_BYTES = 3200      # 0.1 s, wakeword.BLOCK_SECONDS
WAKE_MIN_AUDIO_S = 4         # the clip is repeated until at least this much is fed

START_DELAY_S = 8            # long enough for her hello to go first
CHECK_TIMEOUT_S = 90         # the check takes 10-15 s here; the parent kills it after this and calls it slow
CHILD_LIMIT_S = 120          # the child's own backstop; past CHECK_TIMEOUT_S so the parent decides first
KILL_WAIT_S = 5
PARENT_POLL_S = 1            # how often the child looks for its parent's pipe closing
STD_INPUT_HANDLE = -10
ERROR_BROKEN_PIPE = 109

# Going over any of these picks "light". Measured 2026-10-31, Ryzen 5 7520U, then held to two cores:
LIGHT_WHISPER_RTF = 0.7      # 0.25-0.37, and 0.33 on two cores: only a truly slow chip gets here
LIGHT_KOKORO_RTF = 1.5       # 0.80-1.21, and 1.93-2.25 on two cores: the number that tells them apart
LIGHT_KOKORO_FIRST_MS = 4500 # 2200-3400, and 5400-6300 on two cores
LIGHT_WAKE_CPU_PCT = 25      # 2.3-3.5 either way; percent of one core
BUSY_LIMIT_PCT = 25          # other programs' share of the machine above which a slow result is unsure
MAX_UNSURE_TRIES = 3
MIN_FREE_GB = 0.8            # with less free RAM the automatic check waits for another app start

NOT_INSTALLED = ("missing", "ImportError", "ModuleNotFoundError")  # says nothing about speed

# whisper_share: the part of the logical CPUs Whisper uses. Half means one thread per real core on
# most laptops, which leaves the other half for her voice and face. Nobody can see or hear this.
SETTINGS_BY_TIER = {
    "normal": {"whisper_share": 1},
    "light": {"whisper_share": 0.5},
}


def tier_setting(name):
    """One setting for the tier in force."""
    return SETTINGS_BY_TIER[_valid_tier(CHECK.tier)][name]


def whisper_threads():
    normal = max(1, min(8, os.cpu_count() or 4))
    return max(min(2, normal), int(normal * tier_setting("whisper_share")))  # two threads beat one (0.33 v 0.52)


def _valid_tier(tier):
    return tier if tier in SETTINGS_BY_TIER else "normal"


def _ms(seconds):
    return round(seconds * 1000, 1)


# ---------------------------------------------------------------- about this laptop

def cpu_name():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except Exception:
        return (platform.processor() or "").strip()


class _MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                *((name, ctypes.c_uint64) for name in (
                    "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
                    "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual"))]


def ram_gb():
    try:
        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return round(status.ullTotalPhys / 2 ** 30, 1)
    except Exception:
        return None


def ram_free_gb():
    try:
        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return round(status.ullAvailPhys / 2 ** 30, 1)
    except Exception:
        return None


def _plugged_in():
    try:
        import power
        return power.plugged_in()
    except Exception:
        return None


def machine_times(process=None):
    """(all CPU time, busy CPU time, CPU time of one process, by default this one) in ticks.
    None on failure or off Windows."""
    if sys.platform != "win32":
        return None
    try:
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32")  # its own copy: argtypes here don't reach ctypes.windll
        filetime = ctypes.POINTER(wintypes.FILETIME)
        kernel32.GetSystemTimes.argtypes = [filetime] * 3
        kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [filetime] * 4
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        made, ended, own_kernel, own_user = (wintypes.FILETIME() for _ in range(4))
        if not kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        if not kernel32.GetProcessTimes(kernel32.GetCurrentProcess() if process is None else process,
                                        ctypes.byref(made), ctypes.byref(ended),
                                        ctypes.byref(own_kernel), ctypes.byref(own_user)):
            return None

        def ticks(t):
            return (t.dwHighDateTime << 32) | t.dwLowDateTime

        total = ticks(kernel) + ticks(user)  # kernel time includes idle time
        return total, total - ticks(idle), ticks(own_kernel) + ticks(own_user)
    except Exception:
        return None


def other_busy_pct(start, end):
    """Share of the whole machine's CPU used by anything but the process, between two machine_times()."""
    if start is None or end is None or end[0] <= start[0]:
        return None
    other = (end[1] - start[1]) - (end[2] - start[2])
    return round(max(0.0, other / (end[0] - start[0]) * 100), 1)


# ---------------------------------------------------------------- the timing steps (child and tool)

def load_clip(path=None):
    """The clip's PCM16 bytes, or None if it can't be read."""
    try:
        with wave.open(str(path or CLIP_PATH), "rb") as clip:
            return clip.readframes(clip.getnframes()) or None
    except (OSError, EOFError, wave.Error):
        return None


def step_kokoro(clock=time.perf_counter, voices_mod=None):
    if voices_mod is None:
        import voices as voices_mod
    if not voices_mod.kokoro_ready():
        return {"kokoro_error": "missing"}
    start = clock()
    engine = voices_mod._load_kokoro()
    loaded = clock()
    samples, rate = engine.create(CHECK_SENTENCE, voice="af_heart", speed=1.0, lang="en-us")
    done = clock()
    return {"kokoro_load_ms": _ms(loaded - start), "kokoro_first_ms": _ms(done - loaded),
            "kokoro_rtf": round((done - loaded) / (len(samples) / rate), 3)}


def step_whisper(pcm, clock=time.perf_counter, threads=None, speech_mod=None, model_factory=None):
    if speech_mod is None:
        import speech as speech_mod
    model_dir = speech_mod._find_model_dir()
    if not pcm or model_dir is None:  # a lost clip says nothing about speed either
        return {"whisper_error": "missing"}
    import numpy as np
    threads = whisper_threads() if threads is None else threads
    audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    start = clock()
    if model_factory is None:
        from faster_whisper import WhisperModel as model_factory
    model = model_factory(str(model_dir), device="cpu", compute_type="int8", cpu_threads=threads,
                          local_files_only=True)
    loaded = clock()
    segments, _info = model.transcribe(audio, language="en", beam_size=1,  # as wakeword._whisper_confirm
                                       condition_on_previous_text=False, vad_filter=False)
    text = " ".join(seg.text.strip() for seg in segments)  # segments are lazy: the real work is here
    done = clock()
    return {"whisper_load_ms": _ms(loaded - start), "whisper_ms": _ms(done - loaded),
            "whisper_rtf": round((done - loaded) / (len(audio) / CLIP_RATE), 3),
            "whisper_text": text, "whisper_threads": threads}


def step_wake(pcm, clock=time.perf_counter, cpu_clock=time.thread_time, wake_mod=None):
    if wake_mod is None:
        import wakeword as wake_mod
    if not pcm or wake_mod.find_model_dir() is None:
        return {"wake_error": "missing"}
    start = clock()
    detector = wake_mod.Detector(names=("mary",), confirm=False)
    loaded = clock()
    need, fed = WAKE_MIN_AUDIO_S * CLIP_RATE * 2, 0
    cpu_start = cpu_clock()
    while fed < need:  # as fast as it will go: only the CPU it took matters
        for at in range(0, len(pcm), WAKE_BLOCK_BYTES):
            block = pcm[at:at + WAKE_BLOCK_BYTES]
            detector.feed(block)
            fed += len(block)
    cpu_s = cpu_clock() - cpu_start
    del detector
    getattr(wake_mod, "_vosk_models", {}).clear()  # wakeword keeps the model for life otherwise
    return {"wake_load_ms": _ms(loaded - start),
            "wake_cpu_pct": round(cpu_s / (fed / 2 / CLIP_RATE) * 100, 1)}


def default_steps(threads=None):
    """[(step name, step)]. threads overrides Whisper's (the tool's --whisper-threads)."""
    pcm = load_clip()
    return [("kokoro", step_kokoro),
            ("whisper", lambda: step_whisper(pcm, threads=threads)),
            ("wake", lambda: step_wake(pcm))]


def run_check(steps=None, times=machine_times):
    """Every step in order, one engine in memory at a time; a failed step leaves
    "<step>_error" and the next one still runs."""
    start = times()
    timings = {}
    for name, step in (default_steps() if steps is None else steps):
        try:
            timings.update(step())
        except Exception as e:
            timings[f"{name}_error"] = type(e).__name__
        gc.collect()
    timings["other_busy_pct"] = other_busy_pct(start, times())
    timings["plugged_in"] = _plugged_in()
    return timings


# ---------------------------------------------------------------- the child (never prints)

def write_result(out_path, timings):
    tmp = f"{out_path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(timings, f)
    os.replace(tmp, out_path)


def _stdin_open():
    """Does the parent still hold its end of the stdin pipe? None when that can't be told."""
    try:
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.PeekNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                           wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID]
        if kernel32.PeekNamedPipe(kernel32.GetStdHandle(STD_INPUT_HANDLE), None, 0, None, None, None):
            return True
        return False if ctypes.get_last_error() == ERROR_BROKEN_PIPE else None
    except Exception:
        return None


def _start_guards(limit=None, exit_fn=os._exit, pipe_open=_stdin_open, poll_s=PARENT_POLL_S):
    """The child never outlives Mary: her end of the stdin pipe closing means she died, and the
    timer is the backstop. The pipe is peeked, never read: with a thread blocked in
    sys.stdin.read() the child couldn't exit at all on Windows, even with os._exit."""
    def wait_for_parent():
        while True:
            state = pipe_open()
            if state is None:  # no pipe to watch; the timer alone ends it
                return
            if not state:
                exit_fn(0)
                return
            time.sleep(poll_s)

    timer = threading.Timer(CHILD_LIMIT_S if limit is None else limit, exit_fn, args=(0,))
    timer.daemon = True
    timer.start()
    threading.Thread(target=wait_for_parent, name="parent-watch", daemon=True).start()


def child_main(out_path, steps=None, guards=_start_guards, exit_fn=os._exit):
    guards()
    try:
        write_result(out_path, run_check(steps))
    except Exception:
        pass  # nowhere to report it; no result file tells the parent enough
    finally:
        exit_fn(0)  # straight out: nothing's left to save, and engine teardown can only go wrong


# ---------------------------------------------------------------- choosing a tier

def pick_tier(timings):
    """(tier, reasons). A missing engine is skipped: it's no evidence of anything."""
    reasons = []
    for key, limit in (("whisper_rtf", LIGHT_WHISPER_RTF), ("kokoro_rtf", LIGHT_KOKORO_RTF),
                       ("kokoro_first_ms", LIGHT_KOKORO_FIRST_MS), ("wake_cpu_pct", LIGHT_WAKE_CPU_PCT)):
        value = timings.get(key)
        if isinstance(value, (int, float)) and value > limit:
            reasons.append(f"{key} {value:g} is over {limit:g}")
    if timings.get("timed_out"):
        reasons.append("timed out")
    error = timings.get("whisper_error")
    if error and error not in NOT_INSTALLED:
        reasons.append(f"whisper failed: {error}")
    if reasons:
        return "light", reasons
    return "normal", [] if _measured(timings) else ["nothing measured"]


def _measured(timings):
    return any(isinstance(timings.get(key), (int, float))
               for key in ("whisper_rtf", "kokoro_rtf", "kokoro_first_ms", "wake_cpu_pct"))


def _tries(record):
    tries = record.get("tries")
    return tries if isinstance(tries, int) else 0


def settle(timings, previous=None, cpu=None, version=None):
    """What to save, given this result and the last record: {"tier", "reasons", "unsure", "tries"}."""
    tier, reasons = pick_tier(timings)
    kept, tries = "normal", 0
    if previous:
        kept = _valid_tier(previous.get("tier"))
        if previous.get("unsure") and previous.get("cpu_name") == cpu and previous.get("version") == version:
            tries = _tries(previous)  # a new CPU or version starts counting again
    if tier == "normal" and not _measured(timings):
        return {"tier": kept, "reasons": reasons, "unsure": True, "tries": tries + 1}
    # A slow result only counts when the laptop was quiet: Windows Update, or a battery saver,
    # can slow a good laptop, and "light" would stick. Fast while busy is still fast, so "normal"
    # always stands. After MAX_UNSURE_TRIES "light" is believed anyway, or a laptop that's never
    # quiet would never get the help.
    busy = timings.get("other_busy_pct")
    if tier == "light" and ((busy is not None and busy > BUSY_LIMIT_PCT) or timings.get("plugged_in") is False):
        tries += 1
        if tries < MAX_UNSURE_TRIES:
            return {"tier": kept, "reasons": reasons, "unsure": True, "tries": tries}
        return {"tier": tier, "reasons": reasons, "unsure": False, "tries": tries}
    return {"tier": tier, "reasons": reasons, "unsure": False, "tries": 0}


def saved_record(settings):
    """The saved record, or None if there isn't a readable one."""
    try:
        record = json.loads((settings or {}).get(SETTING_KEY) or "null")
    except (TypeError, ValueError):
        return None
    return record if isinstance(record, dict) else None


# ---------------------------------------------------------------- the parent

def child_command(out_path):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--laptop-check", out_path]
    return [sys.executable, str(Path(__file__).resolve()), "--laptop-check", out_path]


def _popen(command):
    flags = (getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
             | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=flags)


def _read_result(path):
    try:
        with open(path, encoding="utf-8") as f:
            result = json.load(f)
    except (OSError, ValueError):
        return None
    return result if isinstance(result, dict) else None


class Checker:
    """One check at a time, on its own daemon thread. Nothing here raises into the caller."""

    def __init__(self, load_settings=None, save_settings=None, sleeper=time.sleep, clock=datetime.now,
                 spawn=_popen, times=machine_times, free_gb=ram_free_gb):
        self.load_settings = load_settings
        self.save_settings = save_settings
        self.sleeper = sleeper
        self.clock = clock  # now(), for the record's date
        self.spawn = spawn
        self.times = times
        self.free_gb = free_gb
        self.tier = "normal"
        self._lock = threading.Lock()
        self._running = False
        self._auto_started = False

    def configure(self, load, save):
        self.load_settings, self.save_settings = load, save

    def apply_saved(self):
        try:
            record = saved_record(self.load_settings())
            self.tier = _valid_tier(record.get("tier")) if record else "normal"
        except Exception:
            log.exception("Could not read the saved laptop check")

    @staticmethod
    def needed(settings, cpu_name, version):
        record = saved_record(settings)
        if record is None or record.get("cpu_name") != cpu_name or record.get("version") != version:
            return True
        return bool(record.get("unsure")) and _tries(record) < MAX_UNSURE_TRIES

    def start_after_window(self):
        """Returns at once. Only the first call counts: every page navigation fires the window's
        loaded event, and an unsure laptop's tries are meant to be spread over app starts."""
        try:
            with self._lock:
                if self._auto_started:
                    return
                self._auto_started = True
            self._begin(START_DELAY_S, force=False)
        except Exception:
            log.exception("Could not start the laptop check")

    def run_now(self):
        """For the API: no delay, needed or not. False if one is already running."""
        try:
            return self._begin(0, force=True)
        except Exception:
            log.exception("Could not start the laptop check")
            return False

    def status(self):
        try:
            record = saved_record(self.load_settings())
        except Exception:
            record = None
        return {"running": self._running, "tier": self.tier, "record": record}

    def _begin(self, delay, force):
        if self.load_settings is None or self.save_settings is None:
            return False  # nowhere to keep the result
        with self._lock:
            if self._running:
                return False
            self._running = True
        try:
            threading.Thread(target=self._run, args=(delay, force), name="laptop-check", daemon=True).start()
        except Exception:
            self._running = False
            raise
        return True

    def _run(self, delay, force):
        try:
            if delay:
                self.sleeper(delay)
            settings = self.load_settings()
            cpu = cpu_name()
            if force or self.needed(settings, cpu, VERSION):
                free = self.free_gb()
                if force or free is None or free >= MIN_FREE_GB:  # its models would push Mary's out of RAM
                    self._check(saved_record(settings), cpu)
        except Exception:
            log.exception("The laptop check failed")
        finally:
            self._running = False

    def _check(self, previous, cpu):
        timings, timed_out = self._run_child()
        record = settle({**timings, "timed_out": timed_out}, previous, cpu, VERSION)
        record.update(timings=timings, date=self.clock().isoformat(timespec="seconds"), cpu_name=cpu,
                      cores=os.cpu_count(), ram_gb=ram_gb(), version=VERSION, timed_out=timed_out)
        self.save_settings({SETTING_KEY: json.dumps(record)})
        self.tier = record["tier"]

    def _run_child(self):
        """(timings, timed_out). Empty timings: the child died early, or left nothing to read."""
        folder = tempfile.mkdtemp(prefix="laptop-check-")
        out_path = os.path.join(folder, "result.json")
        proc = None
        try:
            proc = self.spawn(child_command(out_path))
            handle = getattr(proc, "_handle", None)
            start = self.times(handle)
            try:
                proc.wait(timeout=CHECK_TIMEOUT_S)  # stdin stays open: its EOF tells the child Mary died
            except subprocess.TimeoutExpired:
                # A killed child leaves no numbers, and the quiet rule still needs these two.
                timings = {"other_busy_pct": other_busy_pct(start, self.times(handle)),
                           "plugged_in": _plugged_in()}
                proc.kill()
                proc.wait(timeout=KILL_WAIT_S)
                return timings, True
            return _read_result(out_path) or {}, False
        finally:
            stdin = getattr(proc, "stdin", None)
            if stdin is not None:
                try:
                    stdin.close()
                except OSError:
                    pass
            shutil.rmtree(folder, ignore_errors=True)


CHECK = Checker()


if __name__ == "__main__":
    child_main(sys.argv[sys.argv.index("--laptop-check") + 1])
