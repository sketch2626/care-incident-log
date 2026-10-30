"""Offline benchmark for the "Hey Mary" / "Hey Sam" wake word (wakeword.py).

Makes spoken test clips with the Windows voices (SAPI David and Zira) and Mary's offline voices
(Kokoro), cached in %TEMP%\\wake_bench_cache. Each clip is played to a fresh wakeword.Detector in three
conditions (clean, across the room, TV on), Vosk only and Vosk + Whisper, and it reports hit rate,
false wakes, wake delay, Whisper time and CPU. Then a ~10 minute TV-on stream of everyday speech checks
false wakes per hour, and CPU/RAM are measured (openWakeWord "hey_jarvis" for comparison only).
Nothing goes to the network; the real microphone is used only with --live.

Run: python tools/wake_bench.py  [--quick] [--live 60] [--stream-min 10] [--out results.json]
Needs numpy, vosk, faster-whisper, kokoro_onnx (optional: scipy, openwakeword).
"""
import argparse
import ctypes
import ctypes.wintypes
import hashlib
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TRACKER_DATA", str(Path(tempfile.gettempdir()) / "wake_bench_data"))

import numpy as np  # noqa: E402

SR = 16000
BLOCK = 1600                       # 0.1 s, as the microphone delivers it
PAD_S = 1.5                        # background before and after each phrase
CACHE = Path(tempfile.gettempdir()) / "wake_bench_cache"
OUT = Path(tempfile.gettempdir()) / "wake_bench_results.json"

POSITIVES = [
    "Hey Mary", "Hey Sam", "Hey Mary, are you there?", "Hey Sam, I need you", "Hey, Mary",
    "Hey Mary, what's the weather",
]
NEGATIVES = [
    "I'm going to marry her next spring", "Merry Christmas to all of you", "Mary had a little lamb",
    "Hey man, how is it going", "Hey Larry, pass the salt", "I saw Sam at the store yesterday",
    "Hey ma'am, your tray is here", "Hey Barry", "Hey, buddy", "Ave Maria", "Sam's Club has a sale",
    "Hail Mary, full of grace", "They got married in May", "Hey Sandy",
    # everyday TV, news and commercials
    "Good evening, here is tonight's top story from the capitol.",
    "Call now and get a second one absolutely free, just pay shipping.",
    "Tomorrow expect scattered showers with a high of seventy two.",
    "The Panthers take the lead with two minutes left in the fourth quarter.",
    "Ask your doctor if this medication is right for you.",
    "Come on down, you're the next contestant on the show.",
    "Stocks closed higher today after a strong jobs report.",
    "Stay tuned, we'll be right back after these messages.",
    "This episode is brought to you by our friends at the furniture store.",
    "Police say the suspect was last seen heading north on the highway.",
    "Mix two cups of flour with a pinch of salt and stir.",
    "Is that your final answer?",
    "In other news, the county fair opens this weekend.",
    "Side effects may include dizziness, nausea and dry mouth.",
    "Grandma, did you take your pills this morning?",
]
SAPI = [("david", "Microsoft David Desktop"), ("zira", "Microsoft Zira Desktop")]
KOKORO = ["af_heart", "af_bella", "bf_emma", "am_michael", "am_fenrir", "bm_george"]
CONDITIONS = ("clean", "room", "tv")


# --------------------------------------------------------------------------- samples

def _key(*parts):
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def voices_for(quick):
    if quick:
        return [("sapi", "david", 0), ("sapi", "zira", 0), ("kokoro", "af_heart", 1.0), ("kokoro", "am_michael", 1.0)]
    out = [("sapi", v, r) for v, _ in SAPI for r in (-2, 0, 2)]
    return out + [("kokoro", v, s) for v in KOKORO for s in (0.85, 1.0)]


def wav_read(path):
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
        rate, ch = w.getframerate(), w.getnchannels()
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return resample(x, rate)


def wav_write(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(to_int16(x))


def to_int16(x):
    return np.clip(np.asarray(x) * 32767.0, -32768, 32767).astype("<i2").tobytes()


def resample(x, rate):
    if rate == SR:
        return x.astype(np.float32)
    try:
        from math import gcd

        from scipy.signal import resample_poly
        g = gcd(SR, rate)
        return resample_poly(x, SR // g, rate // g).astype(np.float32)
    except ImportError:
        t = np.arange(int(len(x) * SR / rate)) * (rate / SR)
        return np.interp(t, np.arange(len(x)), x).astype(np.float32)


def trim(x, thresh=0.01):
    idx = np.nonzero(np.abs(x) > thresh)[0]
    if len(idx) == 0:
        return x
    return x[max(0, idx[0] - 800): idx[-1] + 800]


def make_samples(voices):
    """Return {(engine, voice, rate, text): path}; makes missing clips."""
    CACHE.mkdir(parents=True, exist_ok=True)
    texts = POSITIVES + NEGATIVES
    paths, sapi_jobs, kokoro_jobs = {}, [], []
    for eng, voice, rate in voices:
        for t in texts:
            p = CACHE / f"{eng}_{voice}_{rate}_{_key(eng, voice, rate, t)}.wav"
            paths[(eng, voice, rate, t)] = p
            if not p.is_file():
                (sapi_jobs if eng == "sapi" else kokoro_jobs).append((voice, rate, t, p))
    if sapi_jobs:
        full = dict(SAPI)
        jobs = [{"voice": full[v], "rate": r, "text": t, "path": str(p) + ".raw.wav"} for v, r, t, p in sapi_jobs]
        jf = CACHE / "sapi_jobs.json"
        jf.write_text(json.dumps(jobs), encoding="utf-8")
        ps = (
            "Add-Type -AssemblyName System.Speech; "
            f"$jobs = Get-Content -Raw -Encoding UTF8 '{jf}' | ConvertFrom-Json; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
            "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono); "
            "foreach ($j in $jobs) { $s.SelectVoice($j.voice); $s.Rate = [int]$j.rate; "
            "$s.SetOutputToWaveFile($j.path, $fmt); $s.Speak($j.text); $s.SetOutputToNull() }; $s.Dispose()"
        )
        print(f"making {len(jobs)} SAPI clips...", flush=True)
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], check=True)
        for _v, _r, _t, p in sapi_jobs:
            raw = Path(str(p) + ".raw.wav")
            wav_write(p, trim(wav_read(raw)))
            raw.unlink(missing_ok=True)
    if kokoro_jobs:
        print(f"making {len(kokoro_jobs)} Kokoro clips...", flush=True)
        jobs = [{"voice": v, "speed": float(r), "text": t, "path": str(p)} for v, r, t, p in kokoro_jobs]
        try:
            import kokoro_onnx  # noqa: F401
            kokoro_make(jobs)
        except ImportError:  # kokoro_onnx lives in the app's build venv: make the clips there
            py = kokoro_python()
            if py is None:
                raise SystemExit("kokoro_onnx not found (set WAKE_BENCH_KOKORO_PY to a python that has it)")
            jf = CACHE / "kokoro_jobs.json"
            jf.write_text(json.dumps(jobs), encoding="utf-8")
            subprocess.run([str(py), __file__, "--kokoro-make", str(jf)], check=True)
    return paths


def kokoro_python():
    if os.environ.get("WAKE_BENCH_KOKORO_PY"):
        return Path(os.environ["WAKE_BENCH_KOKORO_PY"])
    for base in (ROOT, ROOT.parent.parent):  # this folder, or the main checkout of a worktree
        py = base / "packaging" / ".venv" / "Scripts" / "python.exe"
        if py.is_file():
            return py
    return None


def kokoro_make(jobs):
    import voices as vmod
    k = vmod._load_kokoro()
    for j in jobs:
        samples, rate = k.create(j["text"], voice=j["voice"], speed=j["speed"], lang="en-us")
        wav_write(j["path"], trim(resample(np.asarray(samples, dtype=np.float32), rate)))


# --------------------------------------------------------------------------- acoustics

RNG = np.random.default_rng(1234)


def db(x):
    return 10 ** (x / 20.0)


def rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def room_ir(rt60=0.4):
    n = int(rt60 * SR)
    t = np.arange(n) / SR
    tail = RNG.standard_normal(n) * np.exp(-6.91 * t / rt60) * 0.25
    tail[: int(0.01 * SR)] = 0.0              # early gap before reflections
    ir = tail
    ir[0] = 1.0
    return (ir / np.sqrt(np.sum(ir ** 2))).astype(np.float32)


IR = room_ir()


def across_room(x):
    from numpy.fft import irfft, rfft
    n = len(x) + len(IR) - 1
    size = 1 << (n - 1).bit_length()
    y = irfft(rfft(x, size) * rfft(IR, size), size)[: len(x)]   # reverb tail cut at the clip end
    return (y * db(-18)).astype(np.float32)


def pink(n):
    w = RNG.standard_normal(n)
    f = np.fft.rfft(w)
    scale = 1.0 / np.sqrt(np.maximum(np.arange(len(f)), 1))
    p = np.fft.irfft(f * scale, n)
    return (p / (rms(p) or 1.0)).astype(np.float32)


def babble_track(n, pool):
    """Three overlapping talkers from the negative clips, plus nothing else; unit RMS."""
    out = np.zeros(n, dtype=np.float32)
    for _ in range(3):
        pos = int(RNG.integers(0, SR))
        while pos < n:
            c = pool[int(RNG.integers(0, len(pool)))]
            end = min(n, pos + len(c))
            out[pos:end] += c[: end - pos]
            pos = end + int(RNG.integers(0, int(0.3 * SR)))
    return out / (rms(out) or 1.0)


def noise_bed(n, speech_rms, pool):
    """TV: babble + pink noise together at 5 dB below the speech."""
    bed = babble_track(n, pool) + 0.5 * pink(n)
    bed = bed / (rms(bed) or 1.0)
    return (bed * speech_rms * db(-5)).astype(np.float32)


def floor(n, level=db(-70)):
    return (RNG.standard_normal(n) * level).astype(np.float32)


def condition(x, cond, pool):
    """Return (signal, phrase_end_s) with PAD_S of matching background before and after."""
    pad = int(PAD_S * SR)
    s = x if cond == "clean" else across_room(x)
    total = np.concatenate([np.zeros(pad, np.float32), s, np.zeros(pad, np.float32)])
    if cond == "tv":
        total = total + noise_bed(len(total), rms(trim(s, 0.001)), pool)
    else:
        total = total + floor(len(total))
    return np.clip(total, -1, 1), PAD_S + len(x) / SR


# --------------------------------------------------------------------------- running

def run_detector(det, x):
    raw = to_int16(x)
    events = []
    t0 = time.process_time()
    for i in range(0, len(raw), BLOCK * 2):
        events += det.feed(raw[i: i + BLOCK * 2])
    return events, time.process_time() - t0


def mem():
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.wintypes.DWORD), ("PageFaultCount", ctypes.wintypes.DWORD)] + [
            (f, ctypes.c_size_t) for f in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    c = PMC()
    c.cb = ctypes.sizeof(c)
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(PMC), ctypes.wintypes.DWORD]
    psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return {"working_mb": round(c.WorkingSetSize / 2**20, 1), "peak_mb": round(c.PeakWorkingSetSize / 2**20, 1)}


def pct(cpu_s, audio_s):
    one = 100.0 * cpu_s / audio_s if audio_s else 0.0
    return {"one_core_pct": round(one, 2), "whole_cpu_pct": round(one / (os.cpu_count() or 1), 2)}


def p90(v):
    return round(float(np.percentile(v, 90)), 1) if v else None


def bench_clips(paths, voices, pool):
    import wakeword
    rows, details = [], []
    pos_set = set(POSITIVES)
    for cond in CONDITIONS:
        for confirm in (False, True):
            hits = npos = fw = nneg = 0
            lat, cms, cpu, aud = [], [], 0.0, 0.0
            t_start = time.time()
            for eng, voice, rate in voices:
                for text in POSITIVES + NEGATIVES:
                    x = wav_read(paths[(eng, voice, rate, text)])
                    sig, end_s = condition(x, cond, pool)
                    det = wakeword.Detector(confirm=confirm)
                    ev, c = run_detector(det, sig)
                    if not confirm:
                        cpu += c
                        aud += len(sig) / SR
                    cms += det.confirm_ms
                    is_pos = text in pos_set
                    if is_pos:
                        npos += 1
                        if ev:
                            hits += 1
                            lat.append(ev[0]["audio_t"] - end_s)
                    else:
                        nneg += 1
                        fw += 1 if ev else 0
                    if ev or (is_pos and not ev):
                        details.append({"cond": cond, "confirm": confirm, "voice": f"{eng}:{voice}:{rate}",
                                        "text": text, "woke": bool(ev),
                                        "events": [{k: e[k] for k in ("name", "stage1_text", "confirm_text", "audio_t")} for e in ev]})
            row = {
                "condition": cond, "mode": "vosk+whisper" if confirm else "vosk only",
                "hits": hits, "positives": npos, "hit_rate_pct": round(100 * hits / npos, 1) if npos else None,
                "false_wakes": fw, "negatives": nneg,
                "latency_mean_s": round(statistics.mean(lat), 2) if lat else None,
                "latency_p90_s": round(float(np.percentile(lat, 90)), 2) if lat else None,
                "whisper_calls": len(cms) if confirm else 0,
                "whisper_mean_ms": round(statistics.mean(cms), 1) if confirm and cms else None,
                "whisper_p90_ms": p90(cms) if confirm else None,
                "wall_s": round(time.time() - t_start, 1),
            }
            if not confirm:
                row.update({"vosk_" + k: v for k, v in pct(cpu, aud).items()})
            rows.append(row)
            print(f"  {cond:5} {row['mode']:12} hit {hits}/{npos}  false {fw}/{nneg}  ({row['wall_s']} s)", flush=True)
    return rows, details


def long_stream(paths, voices, minutes):
    """~minutes of shuffled negatives, across the room with TV noise; one Detector per mode."""
    import wakeword
    neg = [across_room(wav_read(paths[(e, v, r, t)])) for e, v, r in voices for t in NEGATIVES]
    rnd = random.Random(7)
    target = int(minutes * 60 * SR)
    parts, n = [], 0
    while n < target:
        c = neg[rnd.randrange(len(neg))]
        gap = np.zeros(int(rnd.uniform(0.3, 1.5) * SR), np.float32)
        parts += [c, gap]
        n += len(c) + len(gap)
    speech_s = np.concatenate(parts)[:target]
    sig = np.clip(speech_s + noise_bed(target, rms(trim(speech_s, 0.001)), neg), -1, 1)
    hours = target / SR / 3600
    out = {"minutes": round(target / SR / 60, 1)}
    for confirm in (False, True):
        det = wakeword.Detector(confirm=confirm)
        ev, c = run_detector(det, sig)
        key = "vosk+whisper" if confirm else "vosk only"
        out[key] = {"false_wakes": len(ev), "per_hour": round(len(ev) / hours, 1),
                    "candidates": det.candidates, "rejected": det.rejected,
                    "texts": [e["confirm_text"] or e["stage1_text"] for e in ev][:20], **pct(c, target / SR)}
        print(f"  stream {key:12} false wakes {len(ev)} ({out[key]['per_hour']}/h)", flush=True)
    return out, sig


def oww_cpu(sig):
    try:
        import openwakeword
        from openwakeword.model import Model
    except Exception as e:
        return {"error": f"openwakeword not usable: {e}"}
    mdir = Path(openwakeword.__file__).parent / "resources" / "models"
    try:
        m = Model(wakeword_models=[str(mdir / "hey_jarvis_v0.1.onnx")], inference_framework="onnx")
    except Exception as e:
        return {"error": f"openwakeword load failed: {e}"}
    pcm = np.frombuffer(to_int16(sig), dtype=np.int16)
    t0 = time.process_time()
    over = 0
    for i in range(0, len(pcm) - 1280, 1280):
        scores = m.predict(pcm[i: i + 1280])
        over += any(v > 0.5 for v in scores.values())
    c = time.process_time() - t0
    return {"frames_over_0.5": over, **pct(c, len(pcm) / SR)}


# --------------------------------------------------------------------------- subprocess probes

def ram_probe():
    import speech
    import wakeword
    base = mem()
    det = wakeword.Detector(confirm=False)
    det.feed(b"\0\0" * BLOCK)
    after_vosk = mem()
    speech._wait_for_model()
    after_whisper = mem()
    print(json.dumps({"baseline": base, "after_vosk": after_vosk, "after_vosk_and_whisper": after_whisper}))


def live_probe(seconds):
    import wakeword
    ok, why = wakeword.available()
    if not ok:
        print(json.dumps({"error": why}))
        return
    wakes = []
    wakeword.start(lambda e: wakes.append({k: e.get(k) for k in ("name", "confirm_text", "confirm_ms")}))
    try:
        time.sleep(3.0)   # let the mic open and the models load
        st0, c0, w0 = wakeword.status(), time.process_time(), time.time()
        time.sleep(seconds)
        c1, w1, st1 = time.process_time(), time.time(), wakeword.status()
        m = mem()
    finally:
        wakeword.stop()
    print(json.dumps({"seconds": round(w1 - w0, 1), **pct(c1 - c0, w1 - w0), **m,
                      "listening": st1.get("listening"), "problem": st1.get("problem") or st0.get("problem"),
                      "wakes": wakes}))


def probe(args):
    r = subprocess.run([sys.executable, __file__] + args, capture_output=True, text=True)
    for line in reversed(r.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {"error": (r.stderr or r.stdout).strip()[-500:]}


# --------------------------------------------------------------------------- report

def table(rows):
    head = f"{'condition':9} {'mode':12} {'hits':>7} {'hit%':>6} {'false':>7} {'lat s':>6} {'p90':>5} {'wh n':>5} {'wh ms':>6} {'wh p90':>6} {'vosk %1c':>8}"
    print(head)
    print("-" * len(head))
    for r in rows:
        print(f"{r['condition']:9} {r['mode']:12} {r['hits']:>3}/{r['positives']:<3} {r['hit_rate_pct'] or 0:>6} "
              f"{r['false_wakes']:>3}/{r['negatives']:<3} {r['latency_mean_s'] if r['latency_mean_s'] is not None else '-':>6} "
              f"{r['latency_p90_s'] if r['latency_p90_s'] is not None else '-':>5} {r['whisper_calls']:>5} "
              f"{r['whisper_mean_ms'] or '-':>6} {r['whisper_p90_ms'] or '-':>6} {r.get('vosk_one_core_pct', '-'):>8}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="4 voices instead of 18")
    ap.add_argument("--live", type=float, default=0, metavar="SECONDS", help="also listen on the real mic")
    ap.add_argument("--stream-min", type=float, default=10.0)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--kokoro-make", default="", help=argparse.SUPPRESS)
    ap.add_argument("--ram-probe", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--live-probe", type=float, default=0, help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.kokoro_make:
        return kokoro_make(json.loads(Path(a.kokoro_make).read_text(encoding="utf-8")))
    if a.ram_probe:
        return ram_probe()
    if a.live_probe:
        return live_probe(a.live_probe)

    import speech
    import wakeword
    ok, why = wakeword.available()
    if not ok:
        print("wake word not available:", why)
        return 1
    voices = voices_for(a.quick)
    paths = make_samples(voices)
    print("RAM probe...", flush=True)
    ram = probe(["--ram-probe"])
    speech._wait_for_model()                     # load Whisper before timing anything
    pool = [across_room(wav_read(paths[(e, v, r, t)])) for e, v, r in voices for t in NEGATIVES]
    print(f"clips: {len(voices)} voices x {len(POSITIVES)} positives + {len(NEGATIVES)} negatives", flush=True)
    rows, details = bench_clips(paths, voices, pool)
    print(f"long stream ({a.stream_min} min)...", flush=True)
    stream, sig = long_stream(paths, voices, a.stream_min)
    oww = oww_cpu(sig[: 120 * SR])
    live = probe(["--live-probe", str(a.live)]) if a.live else None

    print("\n=== per-clip results (" + ("quick" if a.quick else "full") + f", {len(voices)} voices) ===")
    table(rows)
    print(f"\n=== long TV-on stream, {stream['minutes']} min of everyday speech ===")
    for k in ("vosk only", "vosk+whisper"):
        s = stream[k]
        print(f"{k:12} false wakes {s['false_wakes']:>3}  = {s['per_hour']:>6}/hour  "
              f"(candidates {s['candidates']}, Whisper rejected {s['rejected']}; CPU {s['one_core_pct']}% of one core)")
        if s["texts"]:
            print("             heard:", "; ".join(map(str, s["texts"][:8])))
    print(f"\n=== CPU (cpu_count {os.cpu_count()}) ===")
    vs = stream["vosk only"]
    print(f"Vosk only:                 {vs['one_core_pct']}% of one core, {vs['whole_cpu_pct']}% of whole CPU")
    if "error" in oww:
        print("openWakeWord hey_jarvis:  ", oww["error"])
    else:
        print(f"openWakeWord hey_jarvis:   {oww['one_core_pct']}% of one core, {oww['whole_cpu_pct']}% of whole CPU "
              f"(frames over 0.5 on TV stream: {oww['frames_over_0.5']})")
    print("\n=== RAM (separate process) ===")
    for k, v in ram.items():
        print(f"{k:24} {v}")
    if live is not None:
        print(f"\n=== live mic, idle listening ===\n{live}")
    out = {"voices": [":".join(map(str, v)) for v in voices], "rows": rows, "stream": stream, "oww": oww,
           "ram": ram, "live": live, "cpu_count": os.cpu_count(), "details": details}
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nresults: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
