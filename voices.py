"""Voice audition for Mary: candidate voices, one spoken sample each, and a Live chat token.

Server side only. The audition page (web/mary/voices.html) plays the samples and records what the
resident prefers. Nothing here ever puts the Gemini key, a URL with the key, or a response body into
a message or a log. Stdlib only.
"""
import base64
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from array import array
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import mary

TTS_MODEL = "gemini-3.8-flash-tts"
LIVE_MODEL = "gemini-3.8-live"
API = "https://generativelanguage.googleapis.com/v1beta"
LIVE_WS = ("wss://generativelanguage.googleapis.com/ws/"
           "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained")

LINE = ("Hello there! It's so good to see you today. "
        "I'm right here whenever you'd like to talk, or just to keep you company.")
STYLE = "warm, gentle and unhurried, like a kind friend"

# (name, gender, Google's one-word description). Gemini ids are "gemini:<Name>", Live ids "live:<Name>".
GEMINI_VOICES = [
    ("Sulafat", "female", "Warm"), ("Vindemiatrix", "female", "Gentle"), ("Achernar", "female", "Soft"),
    ("Achird", "male", "Friendly"), ("Algieba", "male", "Smooth"), ("Umbriel", "male", "Easy-going"),
]
# Offline candidates ("kokoro:<voice>"): (name, gender, about). Names starting with "b" are British.
KOKORO_VOICES = [
    ("af_heart", "female", "Warm, American"), ("af_bella", "female", "Bright, American"),
    ("bf_emma", "female", "Gentle, British"),
    ("am_michael", "male", "Calm, American"), ("am_fenrir", "male", "Deep, American"),
    ("bm_george", "male", "Kind, British"),
]
KOKORO_MODEL = "kokoro-v1.0.int8.onnx"   # fetched by tools/get_voice_model.py into models/kokoro/
KOKORO_VOICE_FILE = "voices-v1.0.bin"
KOKORO_PAUSE_S = 0.15                     # quiet gap put between the sentences of one sample
_HERE = Path(__file__).resolve().parent

SOCKET_TIMEOUT = 15  # seconds to wait on any one read
DEADLINE = 30        # seconds for a whole sample
SAMPLE_RATE = 24000  # Gemini's default streamed audio: 16-bit little-endian PCM, mono
LIVE_EXTRA = ("You are talking out loud in a live voice conversation. Never say anything in square brackets. "
              "Keep each answer to one to three short sentences, warm and natural. "
              "That includes the mood, name and remember tags described above: don't use them here.")
TIMING_WORDS = ("timestamp", "offset", "word_info", "alignment", "timing")
LOG_MAX = 200_000


class VoiceError(Exception):
    """kind is "bad_key" (Google turned the key down), "no_gemini" (couldn't get an answer), "no_offline"
    (the offline voice isn't installed or failed) or "unknown_voice".
    The message is only the kind, so no key, URL or response text can leak through it."""

    def __init__(self, kind, detail=""):
        super().__init__(kind)
        self.kind = kind
        self.detail = detail  # for audition.log only, already scrubbed; never sent to the page


def _open(req, timeout):
    """The one network seam (tests replace it)."""
    return urllib.request.urlopen(req, timeout=timeout)


def _scrub(text, api_key):
    """Short and safe for the log: no key, no key= parameter, one line, 120 characters."""
    text = str(text)
    if api_key:
        text = text.replace(api_key, "[key]")
    text = re.sub(r"(key|token)=[^&\s\"']+", r"\1=[hidden]", text, flags=re.I)
    return " ".join(text.split())[:120]


def _http_failure(err, api_key, where):
    """(key_refused, detail) for an HTTPError, reading its body once. Same rule as mary._key_refused:
    401/403, or a 400 about the API key. detail is Google's status and reason, scrubbed, for the log."""
    try:
        body = err.read(4096).decode("utf-8", "replace")
    except Exception:
        body = ""
    refused = err.code in (401, 403) or (err.code == 400 and "api key" in body.lower())
    reason = ""
    try:
        e = json.loads(body).get("error") or {}
        reason = f"{e.get('status', '')}: {e.get('message', '')}"
    except (ValueError, AttributeError):
        pass
    return refused, _scrub(f"{where} {err.code} {reason}", api_key)


def _other_failure(exc, where):
    return f"{where} {type(exc).__name__}"


def candidates():
    out = [{"id": f"gemini:{n}", "kind": "gemini", "voice": n, "gender": g, "about": a, "ready": True}
           for n, g, a in GEMINI_VOICES]
    ready = kokoro_ready()
    out += [{"id": f"kokoro:{n}", "kind": "kokoro", "voice": n, "gender": g, "about": a, "ready": ready}
            for n, g, a in KOKORO_VOICES]
    return out


def live_choices():
    return [{"id": f"live:{n}", "voice": n, "gender": g, "about": a} for n, g, a in GEMINI_VOICES]


def valid_choice(v):
    """True for a known candidate id: gemini:<Name>, live:<Name> or kokoro:<voice>."""
    if not isinstance(v, str) or ":" not in v:
        return False
    kind, _, name = v.partition(":")
    names = {"gemini": [n for n, _, _ in GEMINI_VOICES], "live": [n for n, _, _ in GEMINI_VOICES],
             "kokoro": [n for n, _, _ in KOKORO_VOICES]}
    return name in names.get(kind, [])


def _voice_name(voice, kind):
    """The bare voice name from 'Sulafat' or 'gemini:Sulafat'; VoiceError if it isn't one of ours."""
    voice = str(voice or "").strip()
    name = voice.split(":", 1)[1] if voice.startswith((kind + ":",)) else voice
    known = KOKORO_VOICES if kind == "kokoro" else GEMINI_VOICES
    if name not in [n for n, _, _ in known]:
        raise VoiceError("unknown_voice")
    return name


def _data(data):
    if data is not None:
        return data
    import server  # lazy: server imports this module
    return server.DATA


# ---------------------------------------------------------------- log

_LOG_NUMBERS = ("first_sound_ms", "total_ms", "audio_s", "reply_gap_ms", "first_audio_ms",
                "turns", "interruptions", "seconds", "close_code", "rtf", "load_ms")
_LOG_BOOLS = ("word_timings", "ok")
_LOG_STRINGS = ("event", "id", "voice", "model", "path", "error")


def log(event, data=None):
    """Append one JSON line to mary/audition.log. Only whitelisted keys are kept; numbers are coerced and
    strings capped, so a page can't write anything else. Never raises."""
    try:
        line = {"ts": datetime.now().isoformat(timespec="seconds")}
        for k in _LOG_STRINGS:
            if k in event:
                line[k] = str(event[k])[:60]
        if "note" in event:
            line["note"] = str(event["note"])[:120]
        for k in _LOG_BOOLS:
            if k in event:
                line[k] = bool(event[k])
        for k in _LOG_NUMBERS:
            v = event.get(k)
            if isinstance(v, bool) or v is None:
                continue
            try:
                n = float(v)
            except (TypeError, ValueError):
                continue
            if math.isfinite(n):
                line[k] = int(n) if n == int(n) else round(n, 2)
        path = _data(data) / "mary" / "audition.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > LOG_MAX:
            path.unlink()  # keep it small; only recent trials matter
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- sample

def _post(url, payload, api_key):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    return _open(req, SOCKET_TIMEOUT)


def _walk(node, audio, flags):
    """Collect every dict that is {type: "audio", data: str}; note any timing-looking key."""
    if isinstance(node, dict):
        for k in node:
            if any(w in str(k).lower() for w in TIMING_WORDS):
                flags["timing"] = True
        if node.get("type") == "audio" and isinstance(node.get("data"), str):
            audio.append(node)
        for v in node.values():
            _walk(v, audio, flags)
    elif isinstance(node, list):
        for v in node:
            _walk(v, audio, flags)


def _decode(node):
    """(pcm bytes, rate, channels) from one audio chunk. A WAV chunk loses its RIFF header."""
    raw = base64.b64decode(node["data"])
    mime = str(node.get("mime_type") or node.get("mimeType") or "").lower()
    rate = int(node.get("sample_rate") or 0) or _rate_of(mime)
    channels = int(node.get("channels") or 1)
    if "wav" in mime or raw[:4] == b"RIFF":
        with wave.open(io.BytesIO(raw), "rb") as w:
            return w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()
    return raw, rate or SAMPLE_RATE, channels


def _rate_of(mime):
    m = re.search(r"rate=(\d+)", mime or "")
    return int(m.group(1)) if m else 0


def _wav(pcm, rate, channels=1):
    pcm = pcm[: len(pcm) - len(pcm) % (2 * channels)]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _from_interactions(resp, started):
    """Read the streamed answer. SSE ("data: {...}" lines) or a plain JSON body (dict or list) both work.
    Returns (chunks, first_sound_ms, timing_seen)."""
    audio, flags, plain, first = [], {"timing": False}, [], None
    for raw in resp:
        if time.monotonic() - started > DEADLINE:
            raise VoiceError("no_gemini")
        line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else str(raw).strip()
        if not line or line.startswith((":", "event:", "id:", "retry:")):
            continue
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload and payload != "[DONE]":
                try:
                    node = json.loads(payload)
                except ValueError:
                    continue
                before = len(audio)
                _walk(node, audio, flags)
                if first is None and len(audio) > before:
                    first = int((time.monotonic() - started) * 1000)
        else:
            plain.append(line)
    if not audio and plain:
        nodes = []
        try:
            nodes = [json.loads("\n".join(plain))]
        except ValueError:
            for p in plain:  # one JSON object per line
                try:
                    nodes.append(json.loads(p))
                except ValueError:
                    pass
        for node in nodes:
            _walk(node, audio, flags)
        if audio:
            first = int((time.monotonic() - started) * 1000)
    return audio, first, flags["timing"]


def _interactions(voice, api_key, started):
    body = {"model": TTS_MODEL,
            "input": [{"type": "user_input", "content": [
                {"type": "text", "text": LINE,
                 "annotations": [{"type": "speech_metadata", "style": STYLE}]}]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]},
            "stream": True}
    with _post(f"{API}/interactions", body, api_key) as resp:
        audio, first, timing = _from_interactions(resp, started)
    if not audio:
        return None
    pcm, rate, channels = b"", 0, 1
    for node in audio:
        chunk, r, c = _decode(node)
        pcm += chunk
        if not rate:
            rate, channels = r, c  # the first chunk sets the format
    return pcm, rate or SAMPLE_RATE, channels, first, timing


def _generate_content(voice, api_key, started):
    body = {"contents": [{"parts": [{"text": LINE}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    with _post(f"{API}/models/{TTS_MODEL}:generateContent", body, api_key) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    flags = {"timing": False}
    _walk(data, [], flags)
    pcm, rate = b"", 0
    for cand in (data.get("candidates") or [])[:1]:
        for part in (cand.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and isinstance(inline.get("data"), str):
                node = {"data": inline["data"], "mime_type": inline.get("mimeType") or inline.get("mime_type") or ""}
                chunk, r, _ = _decode(node)
                pcm += chunk
                rate = rate or r
    if not pcm:
        raise VoiceError("no_gemini")
    total = int((time.monotonic() - started) * 1000)
    return pcm, rate or SAMPLE_RATE, 1, total, flags["timing"]


def _cache_files(voice_id, voice, data):
    key = hashlib.sha256(f"{TTS_MODEL}|{LINE}|{STYLE}|{voice}".encode("utf-8")).hexdigest()[:8]
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", voice_id)
    wav = _data(data) / "mary" / "voices" / f"{safe}-{key}.wav"
    return wav, wav.with_suffix(".json")


def tts_sample(voice, api_key, data=None):
    """One spoken sample of LINE. Returns {wav, first_sound_ms, total_ms, audio_s, path, word_timings, cached}.
    A saved copy is used when there is one (no network). Raises VoiceError. Every call is logged."""
    voice_id = str(voice or "").strip()
    event = {"event": "tts", "id": voice_id, "model": TTS_MODEL}
    try:
        name = _voice_name(voice_id, "gemini")
        voice_id = f"gemini:{name}"
        event.update(id=voice_id, voice=name)
        wav_file, meta_file = _cache_files(voice_id, name, data)
        try:
            wav = wav_file.read_bytes()
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            with wave.open(io.BytesIO(wav), "rb") as w:
                audio_s = round(w.getnframes() / w.getframerate(), 2)
            out = {"wav": wav, "first_sound_ms": int(meta.get("first_sound_ms", 0)),
                   "total_ms": int(meta.get("total_ms", 0)), "audio_s": audio_s,
                   "path": str(meta.get("path") or "cache"), "word_timings": bool(meta.get("word_timings")),
                   "cached": True}
            log({**event, "ok": True, "note": "saved copy", **{k: out[k] for k in ("audio_s", "path")}}, data)
            return out
        except (OSError, EOFError, wave.Error, ZeroDivisionError, ValueError, TypeError):
            pass  # no usable saved copy; ask Google
        started = time.monotonic()
        path, fell_back = "interactions", ""
        try:
            got = _interactions(name, api_key, started)
            if got is None:
                fell_back = "interactions gave no audio"
        except urllib.error.HTTPError as e:
            refused, detail = _http_failure(e, api_key, "interactions")
            if refused:
                raise VoiceError("bad_key", detail) from None
            if e.code not in (400, 404):
                raise VoiceError("no_gemini", detail) from None
            got, fell_back = None, detail
        except VoiceError:
            raise
        except Exception as e:  # no network, timeout, bad stream
            raise VoiceError("no_gemini", _other_failure(e, "interactions")) from None
        if got is None:
            path = "generateContent"
            try:
                got = _generate_content(name, api_key, started)
            except urllib.error.HTTPError as e:
                refused, detail = _http_failure(e, api_key, "generateContent")
                raise VoiceError("bad_key" if refused else "no_gemini", _scrub(f"{fell_back} | {detail}", api_key)) from None
            except VoiceError as e:
                raise VoiceError(e.kind, _scrub(f"{fell_back} | generateContent gave no audio", api_key)) from None
            except Exception as e:
                raise VoiceError("no_gemini", _scrub(f"{fell_back} | {_other_failure(e, 'generateContent')}", api_key)) from None
        pcm, rate, channels, first, timing = got
        wav = _wav(pcm, rate, channels)
        total = int((time.monotonic() - started) * 1000)
        out = {"wav": wav, "first_sound_ms": first if first is not None else total, "total_ms": total,
               "audio_s": round(len(pcm) / (2 * channels * rate), 2), "path": path,
               "word_timings": bool(timing), "cached": False}
        try:
            wav_file.parent.mkdir(parents=True, exist_ok=True)
            wav_file.write_bytes(wav)
            meta_file.write_text(json.dumps({k: out[k] for k in ("first_sound_ms", "total_ms", "path", "word_timings")}),
                                 encoding="utf-8")
        except OSError:
            pass  # not saving a copy only costs a second call later
        log({**event, "ok": True, **({"note": fell_back} if fell_back else {}),
             **{k: out[k] for k in ("first_sound_ms", "total_ms", "audio_s", "path", "word_timings")}}, data)
        return out
    except VoiceError as e:
        log({**event, "ok": False, "error": e.kind, **({"note": e.detail} if e.detail else {})}, data)
        raise


# ---------------------------------------------------------------- offline voice (Kokoro)

_kokoro = None                      # the loaded engine, kept for the life of the server
_kokoro_lock = threading.Lock()     # one load and one synthesis at a time


def _kokoro_files():
    """(model, voices) paths: the app's models/kokoro folder, then the one in %APPDATA%\\CareIncidentLog\\models."""
    dirs = [_HERE / "models" / "kokoro"]
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(Path(appdata) / "CareIncidentLog" / "models" / "kokoro")
    for d in dirs:
        if (d / KOKORO_MODEL).is_file() and (d / KOKORO_VOICE_FILE).is_file():
            return d / KOKORO_MODEL, d / KOKORO_VOICE_FILE
    return None


def kokoro_ready():
    """True when both model files are on disk and the kokoro_onnx package is installed (nothing is imported)."""
    try:
        return _kokoro_files() is not None and importlib.util.find_spec("kokoro_onnx") is not None
    except (ImportError, ValueError):
        return False


def _load_kokoro():
    """Build the engine (tests replace this). Slow: reads the ~90 MB model."""
    files = _kokoro_files()
    if files is None:
        raise FileNotFoundError("kokoro model files")
    from kokoro_onnx import Kokoro
    return Kokoro(str(files[0]), str(files[1]))


def _sentences(text):
    return [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]


def _pcm16(samples):
    """Little-endian 16-bit PCM bytes from float samples in -1..1 (clipped)."""
    try:
        import numpy as np
        return np.clip(np.asarray(samples, dtype=np.float32) * 32767.0, -32768, 32767).astype("<i2").tobytes()
    except ImportError:
        out = array("h", (max(-32768, min(32767, int(x * 32767.0))) for x in samples))
        if sys.byteorder == "big":
            out.byteswap()
        return out.tobytes()


def kokoro_sample(voice, data=None):
    """One spoken sample of LINE made on this computer. Same result shape as tts_sample, plus rtf (seconds of
    synthesis per second of speech) and load_ms (model load, only on the first call). Never cached, so every
    play measures the speed again. Raises VoiceError("no_offline"). Every call is logged."""
    voice_id = str(voice or "").strip()
    event = {"event": "tts", "id": voice_id, "model": KOKORO_MODEL.rsplit(".", 1)[0]}
    try:
        name = _voice_name(voice_id, "kokoro")
        voice_id = f"kokoro:{name}"
        event.update(id=voice_id, voice=name)
        if not kokoro_ready():
            raise VoiceError("no_offline", "model files or kokoro_onnx missing")
        lang = "en-gb" if name.startswith("b") else "en-us"
        global _kokoro
        try:
            with _kokoro_lock:
                load_ms = 0
                if _kokoro is None:
                    t = time.monotonic()
                    _kokoro = _load_kokoro()
                    load_ms = int((time.monotonic() - t) * 1000)
                pieces, rate, synth, first_ms = [], 0, 0.0, 0
                for sentence in _sentences(LINE):
                    t = time.monotonic()
                    samples, r = _kokoro.create(sentence, voice=name, speed=1.0, lang=lang)
                    took = time.monotonic() - t
                    synth += took
                    if not pieces:
                        first_ms = int(took * 1000) + load_ms
                    rate = rate or int(r)
                    pieces.append(_pcm16(samples))
        except Exception as e:  # missing file, bad model, out of memory
            raise VoiceError("no_offline", _other_failure(e, "kokoro")) from None
        if not rate or not any(pieces):
            raise VoiceError("no_offline", "kokoro gave no audio")
        speech_s = sum(len(p) for p in pieces) / (2 * rate)
        gap = b"\x00\x00" * int(rate * KOKORO_PAUSE_S)
        pcm = gap.join(pieces)
        wav = _wav(pcm, rate)
        out = {"wav": wav, "first_sound_ms": first_ms, "total_ms": load_ms + int(synth * 1000),
               "audio_s": round(len(pcm) / (2 * rate), 2), "path": "kokoro", "word_timings": False,
               "cached": False, "rtf": round(synth / speech_s, 3), "load_ms": load_ms}
        log({**event, "ok": True, **{k: out[k] for k in ("first_sound_ms", "total_ms", "audio_s", "path",
                                                          "word_timings", "rtf", "load_ms")}}, data)
        return out
    except VoiceError as e:
        log({**event, "ok": False, "error": e.kind, **({"note": e.detail} if e.detail else {})}, data)
        raise


# ---------------------------------------------------------------- Live chat token

def live_token(voice, api_key, companion="mary", memory_name="", data=None):
    """A one-use token the page uses to open a Live voice chat straight to Google (the key stays here).
    Returns {token, model, ws, voice}. Raises VoiceError. Logged."""
    event = {"event": "token", "id": str(voice or ""), "model": LIVE_MODEL}
    try:
        name = _voice_name(voice, "live")
        event.update(id=f"live:{name}", voice=name)
        system = mary.system_text(SimpleNamespace(name=memory_name or "", facts=[], recent=[]), companion, facts=False)
        system += "\n\n" + LIVE_EXTRA
        now = datetime.now(timezone.utc)
        stamp = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
        body = {"uses": 1,
                "expireTime": stamp(now + timedelta(minutes=30)),
                "newSessionExpireTime": stamp(now + timedelta(minutes=1)),
                "liveConnectConstraints": {
                    "model": f"models/{LIVE_MODEL}",
                    "config": {"responseModalities": ["AUDIO"],
                               "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": name}}},
                               "systemInstruction": {"parts": [{"text": system}]},
                               "inputAudioTranscription": {}, "outputAudioTranscription": {}}}}
        try:
            with _post(f"{API}/auth_tokens", body, api_key) as resp:
                token = json.loads(resp.read().decode("utf-8", "replace")).get("name")
        except urllib.error.HTTPError as e:
            refused, detail = _http_failure(e, api_key, "auth_tokens")
            raise VoiceError("bad_key" if refused else "no_gemini", detail) from None
        except Exception as e:
            raise VoiceError("no_gemini", _other_failure(e, "auth_tokens")) from None
        if not isinstance(token, str) or not token:
            raise VoiceError("no_gemini", "auth_tokens gave no name")
        log({**event, "ok": True}, data)
        return {"token": token, "model": f"models/{LIVE_MODEL}", "ws": LIVE_WS, "voice": name}
    except VoiceError as e:
        log({**event, "ok": False, "error": e.kind, **({"note": e.detail} if e.detail else {})}, data)
        raise
