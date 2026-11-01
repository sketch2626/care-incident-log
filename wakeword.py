"""Offline wake word ("Hey Mary" / "Hey Sam") for the Care Incident Log.

Nothing here ever touches the network. Both speech models are read from disk and
audio never leaves the computer.

Two stages (measured on a Ryzen 5 7520U laptop):

1. Vosk (small English model, a three-phrase grammar) listens all the time. It is
   cheap, about 2.5% of one core, but on its own it also "hears" Hey Mary in
   "Hey man" and "Hey Larry", so what it finds is only a candidate.
2. faster-whisper (the same base.en model voice typing uses) then reads the last
   ~2.5 s of audio and must hear the greeting and the name anywhere, or the bare name
   among the clip's first 4 words (Vosk already heard it). It tells "Mary" from "man",
   "Larry", "marry" and "merry". It costs about 1 s, and only on candidates.

Public interface (all functions are thread-safe):

    available()              -> (ok, reason)   can wake-word listening run on this computer?
    start(on_wake=None, on_note=None) -> None   begin listening (RuntimeError with a plain message if
                                        it cannot); on_note gets "heard" and "almost" notes (below)
    stop()                   -> None   stop listening and let go of the microphone
    pause(reason)            -> None   let go of the microphone now, until resume(reason)
    resume(reason)           -> None   listening restarts once no pause reason is left
    set_companion(companion) -> None   "him" -> Sam, anything else -> Mary (only that name wakes)
    alive()                  -> bool   is the worker thread running?
    status()                 -> dict   {"enabled", "running", "listening", "paused_by", "wakes",
                                        "last", "problem"}
    wait(after_seq, timeout) -> dict | None   long-poll: newest wake event with seq > after_seq

`Detector` is the microphone-free part; tests and the bench tool feed it audio directly.
The bench listens for both NAMES; the app's listener builds its Detector for the chosen
companion's name only, and set_companion() has the worker thread build a fresh one.

Notes (on_note, called on the worker thread with no lock held; errors in it are ignored):
    {"type": "heard",  "name", "stage1_text", "audio_t", "companion", "time"}
        Vosk heard the name; Whisper is checking it now (a wake event follows if it agrees).
    {"type": "almost", "name", "stage1_text", "confirm_text", "confirm_ms", "companion", "time"}
        Whisper turned the candidate down (a near miss).
    {"type": "mic", "reason", "companion", "time"}
        The open microphone died and is being reopened; reason says how.

Lock order: speech._rec_lock first, then _Listener._lock (wait()'s Condition shares that
lock). Nothing takes speech._rec_lock while holding _Listener._lock. The audio callback
takes no lock except queue.Queue's own, on_wake runs with no lock held, and the Whisper
check takes speech._transcribe_lock on the worker thread with no wake-word lock held.

Messages that may be shown to a resident are plain language; "{name}" in them becomes
Mary or Sam.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import queue
import re
import threading
import time
from pathlib import Path

try:  # numpy is installed with faster-whisper; keep available() working without it
    import numpy as np
except Exception:  # pragma: no cover
    np = None

log = logging.getLogger("care.wakeword")

VOSK_MODEL_NAME = "vosk-model-small-en-us-0.15"
SAMPLE_RATE = 16000          # both models listen at 16 kHz mono
BLOCK_SECONDS = 0.1          # one microphone block (1600 samples at 16 kHz)
NAMES = ("mary", "sam")      # the bench listens for both; the app only for the chosen companion's name
GRAMMAR = ["hey mary", "hey sam", "[unk]"]  # the bench grammar ("[unk]" = anything else)
NAME_SPELLINGS = {"mary": ("mary", "marie"), "sam": ("sam",)}  # how Whisper may write each name
GREETINGS = ("hey", "hi", "hay", "okay", "ok")  # words Whisper may write before the name
BARE_NAME_WORDS = 4          # or Whisper may write the bare name among the clip's first this many words
RING_SECONDS = 3.0           # audio kept for the Whisper check
CONFIRM_WAIT_S = 0.5         # after a candidate, wait for this much more audio (or the end of the phrase)
CONFIRM_SECONDS = 2.5        # ...then Whisper reads the last 2.5 s
REFRACTORY_S = 2.0           # after a wake, the name is ignored for 2 s of audio
CONFIRM_MS_KEPT = 50         # how many Whisper timings Detector.stats() keeps
QUEUE_BLOCKS = 50            # audio waiting for the worker (5 s); the oldest block is dropped when full
QUEUE_POLL_S = 0.2           # the worker checks at least this often whether to open or close the mic
REOPEN_RETRY_S = 5.0         # a microphone that would not open is tried again this often
JOIN_TIMEOUT_S = 5.0         # stop() waits at most this long for the worker thread
MIC_STALL_S = 3.0            # an open microphone with no block for this long has died: reopen it
MIC_ZERO_S = 10.0            # nothing but exact zeros for this long has died too (real silence is never all zeros)
MIC_ZERO_MAX = 12            # ...and with only zeros each reopen waits twice as long, up to this many times MIC_ZERO_S
MIC_NOTE_S = 60.0            # the same "mic" note goes out at most this often (a muted mic gives only zeros)
CLOSE_WAIT_S = 2.0           # a close gets this long: PortAudio can hang on a vanished device
SLOW_CHECK_S = 3.0           # a Whisper check longer than this makes the audio queued behind it stale

MSG_NOT_INSTALLED = 'Listening for "Hey {name}" is not installed on this computer. You can still tap Talk.'
MSG_MODEL_MISSING = (
    'Listening for "Hey {name}" is not set up on this computer because its speech files are '
    "missing. You can still tap Talk."
)
MSG_START_FAILED = 'Listening for "Hey {name}" could not start on this computer. You can still tap Talk.'
MSG_NO_MIC = (
    'No microphone found, so "Hey {name}" cannot be heard. Please plug in a microphone. '
    "Listening starts again by itself."
)
MSG_MIC_FAILED = (
    'The microphone could not be used, so "Hey {name}" cannot be heard. Please check that it is '
    "plugged in and that microphone access is turned on in Windows Settings."
)
MSG_CONFIRM_FAILED = '"Hey {name}" could not be checked just now. You can still tap Talk.'

# Optional test hook (tools/wake_try.py): on_reject(stage1_text, confirm_text) is called for
# each Vosk candidate that Whisper turns down. None in the app. Errors in it are ignored.
on_reject = None

_HERE = Path(__file__).resolve().parent
_RING_BYTES = int(RING_SECONDS * SAMPLE_RATE) * 2
_CONFIRM_WAIT = int(CONFIRM_WAIT_S * SAMPLE_RATE)
_REFRACTORY = int(REFRACTORY_S * SAMPLE_RATE)


def _speech():
    """speech.py, imported on first use so importing this module stays cheap."""
    import speech

    return speech


def _fmt(message: str, name: str) -> str:
    try:
        return message.format(name=name)
    except Exception:
        return message


def _say(message: str) -> str:
    """A message with the companion's name filled in."""
    return _fmt(message, _listener._primary.capitalize())


def _grammar(names) -> list[str]:
    return [f"hey {n}" for n in names] + ["[unk]"]


def _candidate_re(names):
    return re.compile(r"\bhey (" + "|".join(map(re.escape, names)) + r")\b")


def _confirm_re(names):
    """Group 1: a greeting and the name, anywhere. Group 2: otherwise the bare name among the first BARE_NAME_WORDS
    words, because Vosk already heard it and messy audio garbles the rest. \\b keeps "marry" and "maryland" out."""
    spellings = "|".join(map(re.escape, [s for n in names for s in NAME_SPELLINGS.get(n, (n,))]))
    return re.compile(
        r"^.*?\b(?:" + "|".join(GREETINGS) + r")\b[\s,.!]*(" + spellings + r")\b"
        r"|^\W*(?:[\w'-]+\W+){0," + str(BARE_NAME_WORDS - 1) + r"}(" + spellings + r")\b",
        re.DOTALL,
    )


CONFIRM_RE = _confirm_re(NAMES)  # Whisper's text must match this (lower-cased) for a wake


def _json_text(raw, key: str) -> str:
    try:
        return str(json.loads(raw).get(key, "") or "")
    except Exception:
        return ""


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

def _vosk_model_dirs() -> list[Path]:
    dirs = [_HERE / "models" / VOSK_MODEL_NAME]
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(Path(appdata) / "CareIncidentLog" / "models" / VOSK_MODEL_NAME)
    return dirs


def find_model_dir() -> Path | None:
    """The Vosk model folder, or None if it is not on this computer."""
    for d in _vosk_model_dirs():
        if (d / "am" / "final.mdl").is_file():
            return d
    return None


def _vosk_installed() -> bool:
    try:
        return importlib.util.find_spec("vosk") is not None
    except Exception:
        return False


def available() -> tuple[bool, str]:
    """(True, "") if wake-word listening can run here, else (False, plain reason)."""
    if np is None or not _vosk_installed():
        return False, _say(MSG_NOT_INSTALLED)
    if find_model_dir() is None:
        return False, _say(MSG_MODEL_MISSING)
    sp = _speech()
    if sp._missing_dependency():
        return False, _say(MSG_NOT_INSTALLED)
    if sp._find_model_dir() is None:
        return False, _say(MSG_MODEL_MISSING)
    return True, ""


_vosk_lock = threading.Lock()  # guards _vosk_models
_vosk_models: dict = {}        # model folder -> loaded vosk.Model (loaded once per process)


def _vosk_recognizer_factory(model_dir):
    import vosk

    try:
        vosk.SetLogLevel(-1)  # keep Kaldi's console chatter out of the log
    except Exception:
        pass
    key = str(model_dir)
    with _vosk_lock:
        model = _vosk_models.get(key)
        if model is None:
            model = vosk.Model(key)
            _vosk_models[key] = model

    def make(grammar_json: str):
        return vosk.KaldiRecognizer(model, SAMPLE_RATE, grammar_json)

    return make


def _whisper_confirm(audio) -> str:
    """Default second stage: faster-whisper reads the clip (16 kHz mono float32). No
    vocabulary prompt here, so "marry" or "man" are not nudged towards "Mary"."""
    sp = _speech()
    model = sp._wait_for_model()
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if sp.SILENT_PEAK <= peak < 0.3:  # quiet laptop microphones: lift the level, as voice typing does
        audio = np.clip(audio * min(0.5 / peak, 20.0), -1.0, 1.0).astype(np.float32)
    with sp._transcribe_lock:
        segments, _info = model.transcribe(
            audio,
            language="en",
            beam_size=1,
            temperature=0.0,  # one pass: on messy clips the fallback ladder took 12 s
            condition_on_previous_text=False,
            vad_filter=False,
        )
        return " ".join(seg.text.strip() for seg in segments)


# --------------------------------------------------------------------------
# Detector (no microphone)
# --------------------------------------------------------------------------

class Detector:
    """Two-stage wake-word detector for 16 kHz mono int16 audio. Knows nothing about
    microphones. Not thread-safe: one thread feeds it.

    feed() returns a list of wake events:
        {"name", "stage1_text", "confirm_text", "audio_t", "confirm_ms", "greeted"}
    audio_t is the seconds of audio fed so far when the wake fired. With confirm=False
    every Vosk candidate is a wake (stage 1 only, for the bench comparison). greeted:
    Whisper heard a greeting before the name, not only the bare name.
    """

    def __init__(self, model_dir=None, names=NAMES, confirm=True, recognizer_factory=None, confirmer=None):
        self.names = tuple(n.lower() for n in names)
        self.grammar = _grammar(self.names)
        self.confirm = confirm
        if recognizer_factory is None:
            model_dir = Path(model_dir) if model_dir else find_model_dir()
            if model_dir is None:
                raise RuntimeError(_say(MSG_MODEL_MISSING))
            recognizer_factory = _vosk_recognizer_factory(model_dir)
        self._rec = recognizer_factory(json.dumps(self.grammar))
        self._confirmer = confirmer or _whisper_confirm
        self._candidate_re = _candidate_re(self.names)
        self._confirm_re = _confirm_re(self.names)
        self._spelling = {s: n for n in self.names for s in NAME_SPELLINGS.get(n, (n,))}
        self._ring = bytearray()   # the last RING_SECONDS of audio
        self._pending = None       # a candidate waiting for its Whisper check
        self._quiet_until = 0      # sample count before which the name is ignored (after a wake)
        self.fed = 0               # samples fed so far
        self.candidates = 0
        self.confirmed = 0
        self.rejected = 0
        self.errors = 0
        self.confirm_ms: list[float] = []
        self.problem: str | None = None  # plain message while the Whisper check cannot run
        # Optional hooks, called inside feed() with errors ignored: on_candidate(info) the moment
        # Vosk hears the name (before Whisper checks it), on_rejected(info) when Whisper says no.
        self.on_candidate = None
        self.on_rejected = None

    def feed(self, data) -> list[dict]:
        data = bytes(data)
        if len(data) % 2:
            data = data[:-1]
        if not data:
            return []
        self._ring += data
        if len(self._ring) > _RING_BYTES:
            del self._ring[: len(self._ring) - _RING_BYTES]
        self.fed += len(data) // 2
        ended = bool(self._rec.AcceptWaveform(data))
        if ended:
            text = _json_text(self._rec.Result(), "text")
        else:
            text = _json_text(self._rec.PartialResult(), "partial")
        name = self._candidate(text)
        if self._pending is None and name:
            if self.fed < self._quiet_until:
                self._rec.Reset()  # the name again within 2 s of a wake: drop it
                return []
            self.candidates += 1
            self._pending = {"name": name, "stage1_text": text, "due": self.fed + _CONFIRM_WAIT}
            self._hook(self.on_candidate, {"name": name, "stage1_text": text,
                                           "audio_t": round(self.fed / SAMPLE_RATE, 3)})
            if not self.confirm:
                return self._finish(self._event(self._pending, None, None))
        elif self._pending is not None and name:
            self._pending["stage1_text"] = text
        if self._pending is not None and (ended or self.fed >= self._pending["due"]):
            return self._finish(self._check(self._pending))
        return []

    def clip(self, seconds: float = CONFIRM_SECONDS):
        """The last `seconds` of audio as 16 kHz mono float32."""
        n = int(seconds * SAMPLE_RATE) * 2
        raw = bytes(self._ring[-n:])
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    def reset(self) -> None:
        """Forget half-heard words and buffered audio (after a pause or a new stream)."""
        self._rec.Reset()
        self._ring.clear()
        self._pending = None

    def stats(self) -> dict:
        return {
            "candidates": self.candidates,
            "confirmed": self.confirmed,
            "rejected": self.rejected,
            "errors": self.errors,
            "confirm_ms": list(self.confirm_ms),
            "audio_s": round(self.fed / SAMPLE_RATE, 2),
        }

    def _candidate(self, text: str) -> str | None:
        m = self._candidate_re.search(text.lower()) if text else None
        return m.group(1) if m else None

    def _check(self, pending: dict) -> dict | None:
        clip = self.clip()
        t0 = time.perf_counter()
        try:
            text = str(self._confirmer(clip) or "")
        except Exception:
            log.exception("The wake-word check could not run")
            self.errors += 1
            self.rejected += 1
            self.problem = _say(MSG_CONFIRM_FAILED)
            return None
        ms = round((time.perf_counter() - t0) * 1000.0, 1)
        self.problem = None
        self.confirm_ms.append(ms)
        del self.confirm_ms[:-CONFIRM_MS_KEPT]
        m = self._confirm_re.search(text.lower())
        if m is None:
            self.rejected += 1
            log.debug("Wake-word candidate rejected after %.0f ms", ms)  # no transcript in the log
            hook = on_reject
            if hook is not None:
                try:
                    hook(pending["stage1_text"], text.strip())
                except Exception:
                    pass
            self._hook(self.on_rejected, {"name": pending["name"], "stage1_text": pending["stage1_text"],
                                          "confirm_text": text.strip(), "confirm_ms": ms})
            return None
        self.confirmed += 1
        heard = m.group(1) or m.group(2)
        return self._event(pending, text.strip(), ms, self._spelling.get(heard, pending["name"]), m.group(1) is not None)

    @staticmethod
    def _hook(fn, info: dict) -> None:
        if fn is not None:
            try:
                fn(info)
            except Exception:
                pass

    def _event(self, pending: dict, confirm_text, ms, name=None, greeted=False) -> dict:
        return {
            "name": name or pending["name"],
            "stage1_text": pending["stage1_text"],
            "confirm_text": confirm_text,
            "audio_t": round(self.fed / SAMPLE_RATE, 3),
            "confirm_ms": ms,
            "greeted": greeted,
        }

    def _finish(self, event: dict | None) -> list[dict]:
        self._pending = None
        self._rec.Reset()
        if event is None:
            return []
        self._quiet_until = self.fed + _REFRACTORY
        return [event]


# --------------------------------------------------------------------------
# Listener (the always-on microphone)
# --------------------------------------------------------------------------

def _close(stream):
    """Stop and close a stream. PortAudio can hang on a vanished device, and callers hold speech._rec_lock (and the
    server's _cond), so this runs on a daemon thread that gets CLOSE_WAIT_S. Returns that thread if it is still stuck."""
    def shut():
        for step in (stream.stop, stream.close):
            try:
                step()
            except Exception:
                pass

    thread = threading.Thread(target=shut, name="care-wakeword-close", daemon=True)
    thread.start()
    thread.join(CLOSE_WAIT_S)
    if thread.is_alive():
        log.warning("The microphone did not close within %s s; carrying on", CLOSE_WAIT_S)
        return thread
    return None


def _drain(q) -> None:
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            return


def _to_16k(data: bytes, rate: int) -> bytes:
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    out = _speech()._resample(audio, rate)
    return (np.clip(out, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()


class _Listener:
    """The always-on microphone behind start()/stop()/pause()/... (one per process).

    One daemon worker thread owns the Detector and is the only one that opens the
    microphone; anyone may close it (pause/stop). Open, close and device queries happen
    only under speech._rec_lock.
    """

    def __init__(self, detector_factory=None):
        self._detector_factory = detector_factory     # None = real Vosk + Whisper
        self._lock = threading.Lock()                 # guards everything below
        self._cond = threading.Condition(self._lock)  # wait() sleeps on this
        self._enabled = False
        self._paused: set[str] = set()
        self._primary = "mary"
        self._on_wake = None
        self._on_note = None      # gets "heard" / "almost" notes (see the module docstring)
        self._feed_gen = None     # worker thread only: the stream generation of the audio being fed
        self._run = None          # token of the current worker run (a fresh object per start())
        self._thread: threading.Thread | None = None
        self._queue: queue.Queue = queue.Queue(maxsize=QUEUE_BLOCKS)
        self._detector: Detector | None = None
        self._stream = None
        self._gen = 0             # bumped whenever the stream opens or closes; older audio is ignored
        self._next_open = 0.0     # monotonic time of the next try to open the microphone
        self._last_audio = 0.0    # monotonic time of the last block from the open stream
        self._last_sound = 0.0    # ...and of the last block that wasn't all zeros
        self._zero_turns = 1      # a muted mic reopens less and less often: MIC_ZERO_S times this, up to MIC_ZERO_MAX
        self._mic_lost = False    # a stream died: re-scan the devices before opening again
        self._stuck_close = None  # a close thread that hasn't come back
        self._mic_note = (None, 0.0)  # the last "mic" note's reason and time
        self._problem: str | None = None
        self._dropped = 0         # audio blocks dropped because the worker fell behind
        self._seq = 0
        self._wakes = 0
        self._last: dict | None = None

    # ---- public -----------------------------------------------------------

    def start(self, on_wake=None, on_note=None) -> None:
        real = self._detector_factory is None
        if real:
            ok, reason = available()
            if not ok:
                raise RuntimeError(reason)
        _register_speech_hook()
        sp = _speech()
        recording = sp._rec is not None  # voice typing already has the microphone
        with self._lock:
            if on_wake is not None:
                self._on_wake = on_wake
            if on_note is not None:
                self._on_note = on_note
            if recording:
                self._paused.add("listen")
            self._enabled = True
            if self._run is not None and self._thread is not None and self._thread.is_alive():
                return
            run = self._run = object()
            self._queue = queue.Queue(maxsize=QUEUE_BLOCKS)
            self._problem = None
            self._next_open = 0.0
            thread = self._thread = threading.Thread(
                target=self._work, args=(run,), name="care-wakeword", daemon=True
            )
        thread.start()
        if real:
            sp.warm_up()  # Whisper is the second stage: load it now, not on the first "Hey Mary"

    def stop(self) -> None:
        with self._cond:
            self._enabled = False
            self._run = None
            self._detector = None
            self._problem = None
            thread, self._thread = self._thread, None
            self._cond.notify_all()
        self._sync(None)  # closes the microphone now
        self._poke()
        if thread is not None and thread is not threading.current_thread():
            thread.join(JOIN_TIMEOUT_S)
            if thread.is_alive():
                log.warning("The wake-word worker did not stop within %s s", JOIN_TIMEOUT_S)

    def pause(self, reason) -> None:
        with self._lock:
            self._paused.add(str(reason))
        self._sync(None)  # the microphone is closed before this returns

    def resume(self, reason) -> None:
        with self._lock:
            self._paused.discard(str(reason))
            if not self._paused:
                self._next_open = 0.0  # try at once, not after the retry wait
        self._poke()

    def set_companion(self, companion) -> None:
        with self._lock:
            self._primary = "sam" if str(companion or "").strip().lower() == "him" else "mary"
        self._poke()  # the worker builds a Detector for the new name at once

    def status(self) -> dict:
        with self._lock:
            thread, detector = self._thread, self._detector
            problem = self._problem or (detector.problem if detector is not None else None)
            out = {
                "enabled": self._enabled,
                "running": bool(
                    self._run is not None and thread is not None and thread.is_alive() and detector is not None
                ),
                "listening": self._stream is not None,
                "paused_by": sorted(self._paused),
                "wakes": self._wakes,
                "last": dict(self._last) if self._last else None,
                "problem": None,
            }
            name = self._primary.capitalize()
        if problem:
            out["problem"] = _fmt(problem, name)
        return out

    def alive(self) -> bool:
        """Is the worker thread running? It stops for good if its Detector can't be built."""
        with self._lock:
            thread = self._thread
        return thread is not None and thread.is_alive()

    def wait(self, after_seq=0, timeout: float = 25.0) -> dict | None:
        """The newest wake event with seq > after_seq, or None after `timeout` seconds
        (or at once when listening is not on, or as soon as stop() is called)."""
        after_seq = int(after_seq or 0)
        deadline = time.monotonic() + max(0.0, float(timeout))
        with self._cond:
            while True:
                if self._last is not None and self._last["seq"] > after_seq:
                    return dict(self._last)
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self._enabled:
                    return None
                self._cond.wait(remaining)

    # ---- worker -----------------------------------------------------------

    def _wanted(self) -> bool:
        """Should the microphone be open? (caller holds self._lock)"""
        return self._enabled and not self._paused and self._detector is not None and self._run is not None

    def _poke(self) -> None:
        try:
            self._queue.put_nowait(None)  # wake the worker so it opens or closes the mic now
        except queue.Full:
            pass  # it is busy with audio and will look again in a moment

    def _make_detector(self, run, names):
        """A Detector for `names` with its hooks wired to this run, or None (problem set)."""
        try:
            detector = self._detector_factory(names) if self._detector_factory else Detector(names=names)
        except Exception:
            log.exception("Wake-word listening could not start")
            with self._lock:
                if self._run is run:
                    self._problem = MSG_START_FAILED
            return None
        detector.on_candidate = lambda info: self._note(run, "heard", info)
        detector.on_rejected = lambda info: self._note(run, "almost", info)
        return detector

    def _work(self, run) -> None:
        with self._lock:
            names = (self._primary,)
        detector = self._make_detector(run, names)
        if detector is None:
            return
        with self._lock:
            if self._run is not run:
                return
            self._detector = detector
            q = self._queue
        last_gen = None
        while True:
            with self._lock:
                if self._run is not run:
                    break
                rebuild = (self._primary,) != names
                if rebuild:
                    names = (self._primary,)
                needs_sync = self._wanted() != (self._stream is not None)
            try:
                if rebuild:  # the companion changed: only the new name may wake her
                    fresh = self._make_detector(run, names)
                    if fresh is not None:
                        with self._lock:
                            if self._run is not run:
                                break
                            self._detector = detector = fresh
                            if self._problem == MSG_START_FAILED:
                                self._problem = None
                        last_gen = None
                if needs_sync:
                    self._sync(run)
                self._heal(run)
                try:
                    item = q.get(timeout=QUEUE_POLL_S)
                except queue.Empty:
                    continue
                if item is None:
                    continue
                gen, rate, data = item
                if gen != self._gen:
                    continue  # audio from a stream that has closed since
                if gen != last_gen:
                    detector.reset()  # a fresh stream: forget half-heard words
                    last_gen = gen
                if rate != SAMPLE_RATE:
                    data = _to_16k(data, rate)
                self._feed_gen = gen
                began = time.monotonic()
                events = detector.feed(data)
                slow = time.monotonic() - began > SLOW_CHECK_S
                for event in events:
                    self._publish(run, gen, event)
                if slow:  # what queued up behind a long Whisper check is stale: it must not be judged
                    _drain(q)
                    detector.reset()
            except Exception:
                log.exception("Wake-word listening hit a problem; carrying on")
                time.sleep(0.5)

    def _publish(self, run, gen: int, event: dict) -> None:
        with self._cond:
            if self._run is not run or gen != self._gen:
                return  # heard before a pause or stop: too late to act on
            self._seq += 1
            self._wakes += 1
            event = dict(event, seq=self._seq, companion=self._primary, time=round(time.time(), 3))
            self._last = event
            self._cond.notify_all()
            callback = self._on_wake
        log.info("Wake word heard (%s)", event["name"])
        if callback is not None:
            try:
                callback(dict(event))
            except Exception:
                log.exception("The wake-word callback failed")

    def _note(self, run, kind: str, info: dict) -> None:
        """A Detector hook, or the worker's own "mic" note: pass it to on_note (worker thread)."""
        with self._lock:
            if self._run is not run or (kind != "mic" and self._feed_gen != self._gen):
                return  # heard before a pause or stop: too late to act on
            callback = self._on_note
            note = dict(info, type=kind, companion=self._primary, time=round(time.time(), 3))
        if callback is not None:
            try:
                callback(note)
            except Exception:
                log.exception("The wake-word note callback failed")

    def _callback_for(self, gen: int, rate: int, q):
        def callback(indata, frames, time_info, status):
            # PortAudio's thread: only queue the bytes. Never block, raise or close the stream here.
            try:
                if gen == self._gen:  # a stream whose close hung may still call back: only the open one counts
                    now = time.monotonic()
                    self._last_audio = now
                    if indata.any():
                        self._last_sound = now
                        self._zero_turns = 1
                item = (gen, rate, indata.tobytes())
                for _ in range(3):
                    try:
                        q.put_nowait(item)
                        return
                    except queue.Full:
                        try:
                            q.get_nowait()  # the worker fell behind: drop the oldest block
                            self._dropped += 1
                        except queue.Empty:
                            pass
            except Exception:
                pass

        return callback

    def _sync(self, run) -> None:
        """Open or close the microphone to match what is wanted. Only the worker (run is
        its token) opens it; anyone may close it. Lock order: speech._rec_lock, then
        self._lock."""
        sp = _speech()
        with sp._rec_lock:
            with self._lock:
                want = self._wanted()
                stream, q = self._stream, self._queue
                if stream is not None and not want:
                    self._stream = None
                    self._gen += 1
                elif (
                    stream is None and want and run is not None and run is self._run
                    and time.monotonic() >= self._next_open
                ):
                    self._gen += 1
                    gen = self._gen
                else:
                    return
            if stream is not None:
                self._note_stuck(_close(stream))
                _drain(q)
                log.info("Wake-word microphone closed")
                return
            try:
                self._rescan_if_lost(sp)
                stream = self._open(sp, gen, q)
            except Exception as exc:
                message = str(exc) if isinstance(exc, RuntimeError) and str(exc) else MSG_MIC_FAILED
                with self._lock:
                    if self._problem != message:
                        log.warning("Wake-word microphone not open: %s", _fmt(message, "Mary"))
                    self._problem = message
                    self._next_open = time.monotonic() + REOPEN_RETRY_S
                return
            with self._lock:
                keep = self._wanted() and run is self._run and self._gen == gen
                if keep:
                    self._stream = stream
                    self._problem = None
                    self._mic_lost = False
                    self._last_audio = self._last_sound = time.monotonic()
            if not keep:
                _close(stream)

    def _note_stuck(self, stuck) -> None:
        """A close that hung: the device list may be out of date, and nothing re-scans until that close comes back."""
        if stuck is not None:
            self._stuck_close, self._mic_lost = stuck, True

    def _rescan_if_lost(self, sp) -> None:
        """A stream died: PortAudio only lists devices when it starts, so look again before reopening and a changed
        default device is found. Not while voice typing records, or while a hung close may still be inside PortAudio.
        (caller holds speech._rec_lock)"""
        stuck = self._stuck_close
        if not self._mic_lost or sp._rec is not None or (stuck is not None and stuck.is_alive()):
            return
        sd = sp._get_sd()
        if sd is not None:
            sp._last_rescan = time.monotonic()
            sp._rescan_devices(sd)

    def _mic_trouble(self, stream) -> str | None:
        """Why the open stream looks dead, or None. A stream that has gone may raise when asked."""
        try:
            active = getattr(stream, "active", True)
        except Exception:
            active = False
        if not active:
            return "stream stopped"
        now = time.monotonic()
        if now - self._last_audio >= MIC_STALL_S:
            return f"no audio for {MIC_STALL_S:g} s"
        if now - self._last_sound >= MIC_ZERO_S * self._zero_turns:
            self._zero_turns = min(self._zero_turns * 2, MIC_ZERO_MAX)
            return f"only zeros for {MIC_ZERO_S:g} s"
        return None

    def _heal(self, run) -> None:
        """Worker thread: a dead microphone is closed and opened again at once, so she is never deaf for good. A reopen
        that fails goes on through _sync's retry."""
        with self._lock:
            stream = self._stream
        reason = self._mic_trouble(stream) if stream is not None else None
        if reason is None:
            return
        sp = _speech()
        with sp._rec_lock:
            with self._lock:
                if self._run is not run or self._stream is not stream:
                    return  # a pause or stop got there first
                self._stream = None
                self._gen += 1
                self._next_open = 0.0
                self._mic_lost = True
                q = self._queue
            self._note_stuck(_close(stream))
            _drain(q)
        now = time.monotonic()
        last_reason, last_at = self._mic_note
        if reason != last_reason or now - last_at >= MIC_NOTE_S:
            self._mic_note = (reason, now)
            log.warning("Wake-word microphone died (%s); reopening", reason)
            self._note(run, "mic", {"reason": reason})
        self._sync(run)

    def _open(self, sp, gen: int, q):
        """Open the default microphone (caller holds speech._rec_lock)."""
        sd = sp._get_sd()
        if sd is None:
            raise RuntimeError(MSG_NOT_INSTALLED)
        info = sp._default_input_info(sd)
        if info is None and sp._rec is None:
            # PortAudio only lists devices when it starts: re-scan so a newly plugged-in mic is seen
            sp._last_rescan = time.monotonic()
            sp._rescan_devices(sd)
            info = sp._default_input_info(sd)
        if info is None:
            raise RuntimeError(MSG_NO_MIC)
        rates = [SAMPLE_RATE]
        native = int(info.get("default_samplerate") or 0)
        if native and native != SAMPLE_RATE:
            rates.append(native)  # some microphones refuse 16 kHz: use their own rate and resample
        last_error = None
        for rate in rates:
            stream = None
            try:
                stream = sd.InputStream(
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                    blocksize=int(rate * BLOCK_SECONDS),
                    callback=self._callback_for(gen, rate, q),
                )
                stream.start()
                log.info("Wake-word microphone open at %d Hz", rate)
                return stream
            except Exception as exc:
                last_error = exc
                if stream is not None:
                    _close(stream)
        log.warning("Could not open the microphone for the wake word: %s", last_error)
        raise RuntimeError(MSG_MIC_FAILED) from last_error


# --------------------------------------------------------------------------
# Public interface
# --------------------------------------------------------------------------

_listener = _Listener()
_hook_lock = threading.Lock()  # guards _hook_registered
_hook_registered = False


def _on_speech_mic(busy: bool) -> None:
    """Voice typing takes the microphone (busy=True) or gives it back (False)."""
    if busy:
        pause("listen")
    else:
        resume("listen")


def _register_speech_hook() -> None:
    global _hook_registered
    with _hook_lock:
        if not _hook_registered:
            _speech().add_mic_hook(_on_speech_mic)
            _hook_registered = True


def start(on_wake=None, on_note=None) -> None:
    """Begin listening for "Hey Mary" or "Hey Sam" (the chosen companion's name only).
    on_wake(event) is called (on the worker thread) for each wake and on_note(note) for each
    "heard" / "almost" note; None keeps the previous callback. Raises RuntimeError with a
    plain message if wake-word listening is not set up on this computer."""
    _listener.start(on_wake, on_note)


def stop() -> None:
    """Stop listening, let go of the microphone and end the worker thread."""
    _listener.stop()


def pause(reason) -> None:
    """Let go of the microphone (before returning) until resume(reason). Reasons stack."""
    _listener.pause(reason)


def resume(reason) -> None:
    """Drop one pause reason; listening starts again once none is left."""
    _listener.resume(reason)


def set_companion(companion) -> None:
    """"him" makes Sam the wake name, anything else Mary. Only that name wakes; the worker
    thread builds a fresh Detector for it."""
    _listener.set_companion(companion)


def status() -> dict:
    return _listener.status()


def alive() -> bool:
    """Is the worker thread running? WakeLink starts it again if not."""
    return _listener.alive()


def wait(after_seq=0, timeout: float = 25.0) -> dict | None:
    return _listener.wait(after_seq, timeout)
