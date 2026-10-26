"""Offline, on-device speech-to-text for the Care Incident Log.

Nothing here ever touches the network. The speech model (faster-whisper
"base.en", CPU, int8) is read from disk, and audio never leaves the computer.

Public interface (all functions are thread-safe):

    is_ready()            -> {"available": bool, "loading": bool, "reason": str}
    warm_up()             -> None   start loading the model in the background
    start()               -> None   begin recording from the default microphone
    stop()                -> str    stop recording and return the transcript
    level()               -> dict   live loudness / voice-activity reading while recording
    transcribe_file(path) -> str    transcribe an existing audio file

Error messages raised to callers are written in plain language so they can be
shown to a resident as they are.
"""

from __future__ import annotations

import importlib.util
import logging
import math
import os
import threading
import time
from pathlib import Path

try:  # numpy is installed with faster-whisper; keep is_ready() working without it
    import numpy as np
except Exception:  # pragma: no cover
    np = None

log = logging.getLogger("care.speech")

MODEL_NAME = "faster-whisper-base.en"
SAMPLE_RATE = 16000          # Whisper's native rate
MAX_RECORD_SECONDS = 5 * 60  # recording stops itself after 5 minutes
MIN_AUDIO_SECONDS = 0.3      # anything shorter is treated as "nothing said"
SILENT_PEAK = 0.001          # a recording quieter than this is treated as silence
RELOAD_RETRY_SECONDS = 30    # warm_up() will not retry a failed load more often than this

# Live voice-activity meter (runs per audio chunk, so the page can stop listening by itself).
# RMS values are on the -1..1 float scale; a laptop mic at normal distance gives speech
# around 0.01-0.05 and a quiet room around 0.0005-0.003.
VOICE_MIN_RMS = 0.003        # never call anything quieter than this "voice" (faint speech still passes)
VOICE_RATIO = 3.0            # voice = louder than 3x the background (about +9.5 dB)
FLOOR_START_CAP = 0.015      # first chunk may be a click or the first word: cap the starting floor
FLOOR_FALL_S = 0.1           # background estimate drops quickly when it gets quieter
FLOOR_RISE_S = 1.5           # ...and follows a rising background (TV, fan) within a couple of seconds
FLOOR_RISE_VOICED_S = 10.0   # ...but creeps up slowly under voice-like sound, so speech is not absorbed
LEVEL_FULL_RMS = 0.05        # loudness (above the background) that fills the page's meter
LEVEL_ATTACK_S = 0.05        # meter rises quickly...
LEVEL_RELEASE_S = 0.25       # ...and falls smoothly
HEARD_VOICE_S = 0.35         # this much voiced audio in total counts as "heard someone speak"


def _clock() -> float:
    """Monotonic seconds (module-level so tests can swap in a fake clock)."""
    return time.monotonic()

INITIAL_PROMPT = (
    "call light, CNA, aide, nurse, brief, shower, bed bath, medication, meds, "
    "reposition, charge nurse, DON, administrator, ombudsman"
)

MSG_NO_MIC = "No microphone found. Please plug in a microphone and try again."
MSG_MIC_FAILED = (
    "The microphone could not be used. Please check that it is plugged in and "
    "that microphone access is turned on in Windows Settings."
)
MSG_NOT_INSTALLED = "Voice typing is not installed on this computer. Please type your report instead."
MSG_MODEL_MISSING = (
    "Voice typing is not set up on this computer because its speech files are missing. "
    "Please type your report instead."
)
MSG_LOAD_FAILED = "Voice typing could not start on this computer. Please type your report instead."
MSG_STILL_LOADING = "Voice typing is still getting ready. Please try again in a moment."

_HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Model location and loading
# --------------------------------------------------------------------------

_state_lock = threading.Lock()       # guards _model, _load_thread, _load_error, _load_failed_at
_model = None
_load_thread: threading.Thread | None = None
_load_error: str | None = None
_load_failed_at = 0.0
_transcribe_lock = threading.Lock()  # one transcription at a time


def _model_dirs() -> list[Path]:
    dirs = [_HERE / "models" / MODEL_NAME]
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(Path(appdata) / "CareIncidentLog" / "models" / MODEL_NAME)
    return dirs


def _find_model_dir() -> Path | None:
    for d in _model_dirs():
        if (d / "model.bin").is_file() and (d / "config.json").is_file():
            return d
    return None


def _missing_dependency() -> str | None:
    if np is None or importlib.util.find_spec("faster_whisper") is None:
        return MSG_NOT_INSTALLED
    return None


def _load_model_worker() -> None:
    global _model, _load_error, _load_failed_at
    model = None
    error = None
    try:
        model_dir = _find_model_dir()
        if model_dir is None:
            error = MSG_MODEL_MISSING
        else:
            from faster_whisper import WhisperModel

            threads = max(1, min(8, os.cpu_count() or 4))
            model = WhisperModel(
                str(model_dir),
                device="cpu",
                compute_type="int8",
                cpu_threads=threads,
                local_files_only=True,
            )
    except Exception:
        log.exception("Could not load the speech model")
        error = MSG_LOAD_FAILED
    with _state_lock:
        _model = model
        _load_error = error
        _load_failed_at = time.monotonic() if error else 0.0


def _start_loading(force: bool = False) -> None:
    """Start the loader thread unless the model is loaded or already loading."""
    global _load_thread, _load_error
    with _state_lock:
        if _model is not None:
            return
        if _load_thread is not None and _load_thread.is_alive():
            return
        if (
            not force
            and _load_error is not None
            and time.monotonic() - _load_failed_at < RELOAD_RETRY_SECONDS
        ):
            return
        _load_error = None
        _load_thread = threading.Thread(target=_load_model_worker, name="speech-model-loader", daemon=True)
        _load_thread.start()


def warm_up() -> None:
    """Begin loading the model in the background. Returns at once; safe to call repeatedly."""
    if _missing_dependency() is not None:
        return
    _start_loading()


def _wait_for_model(timeout: float = 600.0):
    _start_loading(force=True)
    with _state_lock:
        thread = _load_thread
    if thread is not None:
        thread.join(timeout)
    with _state_lock:
        if _model is not None:
            return _model
        error = _load_error
    raise RuntimeError(error or MSG_STILL_LOADING)


# --------------------------------------------------------------------------
# Microphone access
# --------------------------------------------------------------------------

_rec_lock = threading.RLock()  # guards _rec and all PortAudio device queries / re-scans
_rec: "_Recording | None" = None
_sd = None
_sd_loaded = False
_last_rescan = 0.0


def _get_sd():
    """Return the sounddevice module, or None if it (or PortAudio) is unavailable."""
    global _sd, _sd_loaded
    if not _sd_loaded:
        try:
            import sounddevice

            _sd = sounddevice
        except Exception:
            log.exception("sounddevice is not available")
            _sd = None
        _sd_loaded = True
    return _sd


def _default_input_info(sd):
    """Info dict for the default input device, or None if there is none."""
    try:
        info = sd.query_devices(kind="input")
    except Exception:
        return None
    if not info or info.get("max_input_channels", 0) < 1:
        return None
    return info


def _rescan_devices(sd) -> None:
    """PortAudio only lists devices when it starts; restart it so newly plugged-in
    microphones are seen. Only called while nothing is recording."""
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        log.exception("Could not re-scan audio devices")


def _mic_problem() -> str | None:
    """Plain-language reason there is no usable microphone, or None if there is one."""
    global _last_rescan
    with _rec_lock:
        if _rec is not None:
            return None  # already recording, so the microphone clearly works
        sd = _get_sd()
        if sd is None:
            return MSG_NOT_INSTALLED
        if _default_input_info(sd) is not None:
            return None
        now = time.monotonic()
        if now - _last_rescan > 2.0:  # throttle: is_ready() may be polled often
            _last_rescan = now
            _rescan_devices(sd)
            if _default_input_info(sd) is not None:
                return None
        return MSG_NO_MIC


def _resample(audio, rate: int):
    """Convert mono float32 audio from `rate` to 16 kHz (only used if the
    microphone refuses to open at 16 kHz directly)."""
    if rate == SAMPLE_RATE:
        return audio
    if rate % SAMPLE_RATE == 0:
        k = rate // SAMPLE_RATE
        n = len(audio) // k * k
        return audio[:n].reshape(-1, k).mean(axis=1).astype(np.float32)
    width = max(1, int(round(rate / SAMPLE_RATE)))
    if width > 1:
        audio = np.convolve(audio, np.ones(width, dtype=np.float32) / width, mode="same")
    n_out = int(len(audio) * SAMPLE_RATE / rate)
    positions = np.arange(n_out) * (rate / SAMPLE_RATE)
    return np.interp(positions, np.arange(len(audio)), audio).astype(np.float32)


class _Recording:
    """One microphone recording. The audio callback only appends to a list."""

    def __init__(self, sd):
        self._sd = sd
        self.rate = SAMPLE_RATE
        self.limit = SAMPLE_RATE * MAX_RECORD_SECONDS
        self.chunks: list = []
        self.frames = 0
        self.stream = None
        self._reset_meter()

    def _reset_meter(self) -> None:
        """Live voice-activity state, written by the audio thread and read by reading()."""
        self.started_t = _clock()
        self.level = 0.0           # smoothed loudness 0..1 for the page's listening animation
        self.noise_floor = None    # RMS of the quiet background (set from the first chunk)
        self.voice_s = 0.0         # total seconds of audio clearly louder than the background
        self.last_voice_t = None   # clock time of the last voiced chunk

    def open(self, rate: int) -> None:
        self.rate = rate
        self.limit = rate * MAX_RECORD_SECONDS
        self.chunks = []
        self.frames = 0
        self._reset_meter()
        stream = self._sd.InputStream(
            samplerate=rate, channels=1, dtype="float32", callback=self._callback
        )
        try:
            stream.start()
        except Exception:
            try:
                stream.close()
            except Exception:
                pass
            raise
        self.stream = stream

    def _callback(self, indata, frames, time_info, status):
        if self.frames >= self.limit:
            raise self._sd.CallbackStop  # 5-minute cap reached; stop() still returns the text
        chunk = indata[:, 0].copy()
        self.chunks.append(chunk)
        self.frames += frames
        self._meter(chunk)

    def _meter(self, chunk) -> None:
        """Update level / noise floor / voice time from one chunk. Cheap, lock-free, never raises
        (an exception in the audio callback would kill the stream)."""
        try:
            n = len(chunk)
            if n == 0:
                return
            now = _clock()
            dt = n / self.rate
            rms = math.sqrt(max(float(np.dot(chunk, chunk)) / n, 0.0))
            floor = self.noise_floor
            if floor is None:
                floor = min(rms, FLOOR_START_CAP)
            voiced = rms > max(floor * VOICE_RATIO, VOICE_MIN_RMS)
            if voiced:
                self.voice_s += dt
                self.last_voice_t = now
            # loudness for the page's animation: above the background, compressed so soft speech shows
            raw = min(1.0, math.sqrt(max(rms - floor, 0.0) / LEVEL_FULL_RMS))
            tau = LEVEL_ATTACK_S if raw > self.level else LEVEL_RELEASE_S
            self.level = min(1.0, max(0.0, self.level + (raw - self.level) * (1.0 - math.exp(-dt / tau))))
            # background estimate: falls fast, rises slowly (slower still under voice-like sound)
            tau = FLOOR_FALL_S if rms < floor else (FLOOR_RISE_VOICED_S if voiced else FLOOR_RISE_S)
            self.noise_floor = floor + (rms - floor) * (1.0 - math.exp(-dt / tau))
        except Exception:
            pass

    def reading(self, now: float | None = None) -> dict:
        """The live reading the page polls (see level())."""
        if now is None:
            now = _clock()
        since = self.last_voice_t if self.last_voice_t is not None else self.started_t
        return {
            "recording": True,
            "level": round(min(1.0, max(0.0, float(self.level))), 3),
            "heard_voice": self.voice_s >= HEARD_VOICE_S,
            "quiet_s": round(max(0.0, now - since), 2),
            "elapsed_s": round(max(0.0, now - self.started_t), 2),
        }

    def abort(self) -> None:
        stream, self.stream = self.stream, None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    def finish(self):
        """Close the stream and return all audio as 16 kHz mono float32."""
        self.abort()
        if not self.chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self.chunks)
        self.chunks = []
        return _resample(audio, self.rate)


def _open_recording(sd) -> _Recording:
    info = _default_input_info(sd)
    if info is None:
        raise RuntimeError(MSG_NO_MIC)
    rates = [SAMPLE_RATE]
    native = int(info.get("default_samplerate") or 0)
    if native and native != SAMPLE_RATE:
        rates.append(native)
    last_error = None
    for rate in rates:
        rec = _Recording(sd)
        try:
            rec.open(rate)
            return rec
        except Exception as exc:
            last_error = exc
    log.error("Could not open the microphone: %s", last_error)
    raise RuntimeError(MSG_MIC_FAILED) from last_error


# --------------------------------------------------------------------------
# Transcription
# --------------------------------------------------------------------------

def _normalise(text: str) -> str:
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in text).split())


def _clean(text: str) -> str:
    text = " ".join(text.split())
    # With no real speech Whisper sometimes just repeats its vocabulary prompt back.
    if text and _normalise(text) in _normalise(INITIAL_PROMPT):
        return ""
    return text


def _transcribe(source) -> str:
    model = _wait_for_model()
    with _transcribe_lock:
        segments, _info = model.transcribe(
            source,
            language="en",
            beam_size=1,  # greedy: beam search with the prompt sometimes ran 5x longer, same text
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            initial_prompt=INITIAL_PROMPT,
            condition_on_previous_text=False,
        )
        text = " ".join(seg.text.strip() for seg in segments)
    return _clean(text)


# --------------------------------------------------------------------------
# Public interface
# --------------------------------------------------------------------------

def is_ready() -> dict:
    """Can voice typing be used right now?

    available -- True if recording can be started (the model may still be
                 loading; stop() will wait for it).
    loading   -- True while the speech model is being loaded.
    reason    -- plain-language explanation when available is False, else "".
    """
    with _state_lock:
        loading = _load_thread is not None and _load_thread.is_alive() and _model is None
        have_model = _model is not None
        load_error = _load_error

    def result(available: bool, reason: str = "") -> dict:
        return {"available": available, "loading": loading, "reason": reason}

    problem = _missing_dependency()
    if problem:
        return result(False, problem)
    if not have_model and not loading:
        if _find_model_dir() is None:
            return result(False, MSG_MODEL_MISSING)
        if load_error:
            return result(False, load_error)
    problem = _mic_problem()
    if problem:
        return result(False, problem)
    return result(True)


def start() -> None:
    """Begin recording from the default microphone. Returns immediately.

    Raises RuntimeError (plain-language message) if there is no usable microphone.
    A recording already in progress is discarded and a fresh one begins.
    """
    global _rec, _last_rescan
    problem = _missing_dependency()
    if problem:
        raise RuntimeError(problem)
    with _rec_lock:
        if _rec is not None:
            old, _rec = _rec, None
            old.abort()
        sd = _get_sd()
        if sd is None:
            raise RuntimeError(MSG_NOT_INSTALLED)
        try:
            rec = _open_recording(sd)
        except RuntimeError:
            # The device list may be stale (microphone plugged in or changed since
            # PortAudio started): re-scan once and try again.
            _last_rescan = time.monotonic()
            _rescan_devices(sd)
            rec = _open_recording(sd)
        _rec = rec
    warm_up()  # load the model while the person is speaking


def stop() -> str:
    """Stop recording, transcribe, and return the text ("" if nothing was said).

    Waits for the model if it is still loading. Raises RuntimeError with a
    plain-language message if the speech model cannot be loaded.
    """
    global _rec
    with _rec_lock:
        rec, _rec = _rec, None
    if rec is None:
        return ""
    audio = rec.finish()
    if len(audio) < MIN_AUDIO_SECONDS * SAMPLE_RATE:
        return ""
    peak = float(np.max(np.abs(audio)))
    if peak < SILENT_PEAK:
        return ""
    if peak < 0.3:  # quiet laptop microphones: lift the level so speech detection works
        audio = np.clip(audio * min(0.5 / peak, 20.0), -1.0, 1.0).astype(np.float32)
    return _transcribe(audio)


def level() -> dict:
    """Live reading while recording, cheap enough to poll every ~150 ms. Never raises.

    {"recording", "level" (0..1), "heard_voice", "quiet_s" (seconds since the last
    voiced chunk, or since the start if none yet), "elapsed_s"}. All zeros/False
    when nothing is recording.
    """
    idle = {"recording": False, "level": 0.0, "heard_voice": False, "quiet_s": 0.0, "elapsed_s": 0.0}
    try:
        with _rec_lock:
            rec = _rec
        return rec.reading() if rec is not None else idle
    except Exception:
        return idle


def transcribe_file(path) -> str:
    """Transcribe an existing audio file (wav, mp3, m4a, ...) and return the text."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError("That recording could not be found.")
    return _transcribe(str(p))


if __name__ == "__main__":  # quick manual check: python speech.py [audiofile]
    import sys

    logging.basicConfig(level=logging.WARNING)
    print(is_ready())
    if len(sys.argv) > 1:
        started = time.perf_counter()
        print(transcribe_file(sys.argv[1]))
        print("%.1f seconds" % (time.perf_counter() - started))
