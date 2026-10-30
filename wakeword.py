"""Offline wake word ("Hey Mary" / "Hey Sam") for the Care Incident Log.

Nothing here ever touches the network. Both speech models are read from disk and
audio never leaves the computer.

Two stages (measured on a Ryzen 5 7520U laptop):

1. Vosk (small English model, a three-phrase grammar) listens all the time. It is
   cheap, about 2.5% of one core, but on its own it also "hears" Hey Mary in
   "Hey man" and "Hey Larry", so what it finds is only a candidate.
2. faster-whisper (the same base.en model voice typing uses) then reads the last
   ~2.5 s of audio and must hear "hey mary" / "hey sam" too. It tells "Mary" from
   "man", "Larry", "marry" and "merry". It costs about 1 s, and only on candidates.

Public interface (all functions are thread-safe):

    available()              -> (ok, reason)   can wake-word listening run on this computer?
    start(on_wake=None)      -> None   begin listening (RuntimeError with a plain message if it cannot)
    stop()                   -> None   stop listening and let go of the microphone
    pause(reason)            -> None   let go of the microphone now, until resume(reason)
    resume(reason)           -> None   listening restarts once no pause reason is left
    set_companion(companion) -> None   "him" -> Sam, anything else -> Mary (both names always work)
    status()                 -> dict   {"enabled", "running", "listening", "paused_by", "wakes",
                                        "last", "problem"}
    wait(after_seq, timeout) -> dict | None   long-poll: newest wake event with seq > after_seq

`Detector` is the microphone-free part; tests and the bench tool feed it audio directly.

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
NAMES = ("mary", "sam")      # both names always wake; the event says which one was heard
GRAMMAR = ["hey mary", "hey sam", "[unk]"]  # all Vosk may hear ("[unk]" = anything else)
NAME_SPELLINGS = {"mary": ("mary", "marie"), "sam": ("sam",)}  # how Whisper may write each name
GREETINGS = ("hey", "hi", "hay", "okay", "ok")  # words Whisper may write before the name
RING_SECONDS = 3.0           # audio kept for the Whisper check
CONFIRM_WAIT_S = 0.5         # after a candidate, wait for this much more audio (or the end of the phrase)
CONFIRM_SECONDS = 2.5        # ...then Whisper reads the last 2.5 s
REFRACTORY_S = 2.0           # after a wake, the name is ignored for 2 s of audio
CONFIRM_MS_KEPT = 50         # how many Whisper timings Detector.stats() keeps
QUEUE_BLOCKS = 50            # audio waiting for the worker (5 s); the oldest block is dropped when full
QUEUE_POLL_S = 0.2           # the worker checks at least this often whether to open or close the mic
REOPEN_RETRY_S = 5.0         # a microphone that would not open is tried again this often
JOIN_TIMEOUT_S = 5.0         # stop() waits at most this long for the worker thread

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
    spellings = [s for n in names for s in NAME_SPELLINGS.get(n, (n,))]
    return re.compile(
        r"\b(" + "|".join(GREETINGS) + r")\b[\s,.!]*(" + "|".join(map(re.escape, spellings)) + r")\b"
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
        {"name", "stage1_text", "confirm_text", "audio_t", "confirm_ms"}
    audio_t is the seconds of audio fed so far when the wake fired. With confirm=False
    every Vosk candidate is a wake (stage 1 only, for the bench comparison).
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
            return None
        self.confirmed += 1
        return self._event(pending, text.strip(), ms, self._spelling.get(m.group(2), pending["name"]))

    def _event(self, pending: dict, confirm_text, ms, name=None) -> dict:
        return {
            "name": name or pending["name"],
            "stage1_text": pending["stage1_text"],
            "confirm_text": confirm_text,
            "audio_t": round(self.fed / SAMPLE_RATE, 3),
            "confirm_ms": ms,
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

def _close(stream) -> None:
    for step in (stream.stop, stream.close):
        try:
            step()
        except Exception:
            pass


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
        self._run = None          # token of the current worker run (a fresh object per start())
        self._thread: threading.Thread | None = None
        self._queue: queue.Queue = queue.Queue(maxsize=QUEUE_BLOCKS)
        self._detector: Detector | None = None
        self._stream = None
        self._gen = 0             # bumped whenever the stream opens or closes; older audio is ignored
        self._next_open = 0.0     # monotonic time of the next try to open the microphone
        self._problem: str | None = None
        self._dropped = 0         # audio blocks dropped because the worker fell behind
        self._seq = 0
        self._wakes = 0
        self._last: dict | None = None

    # ---- public -----------------------------------------------------------

    def start(self, on_wake=None) -> None:
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

    def _work(self, run) -> None:
        try:
            detector = self._detector_factory() if self._detector_factory else Detector()
        except Exception:
            log.exception("Wake-word listening could not start")
            with self._lock:
                if self._run is run:
                    self._problem = MSG_START_FAILED
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
                needs_sync = self._wanted() != (self._stream is not None)
            try:
                if needs_sync:
                    self._sync(run)
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
                for event in detector.feed(data):
                    self._publish(run, gen, event)
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

    def _callback_for(self, gen: int, rate: int, q):
        def callback(indata, frames, time_info, status):
            # PortAudio's thread: only queue the bytes. Never block, raise or close the stream here.
            try:
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
                _close(stream)
                _drain(q)
                log.info("Wake-word microphone closed")
                return
            try:
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
            if not keep:
                _close(stream)

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


def start(on_wake=None) -> None:
    """Begin listening for "Hey Mary" / "Hey Sam". on_wake(event) is called (on the
    worker thread) for each wake; None keeps the previous callback. Raises RuntimeError
    with a plain message if wake-word listening is not set up on this computer."""
    _listener.start(on_wake)


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
    """"him" makes Sam the main name, anything else Mary. Both names always wake."""
    _listener.set_companion(companion)


def status() -> dict:
    return _listener.status()


def wait(after_seq=0, timeout: float = 25.0) -> dict | None:
    return _listener.wait(after_seq, timeout)
