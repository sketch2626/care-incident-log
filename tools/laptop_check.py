"""Time Kokoro, Whisper and the wake word on this laptop, with the same step code as the
first-run check (speedcheck.py), and show the tier those numbers pick. Nothing else does
real timing. It runs in this process, not the app's below-normal child.

Run it with the build venv, which has the engines:
  packaging\\.venv\\Scripts\\python.exe tools\\laptop_check.py
  ... --cores 2 --burn     imitate an older chip: two separate cores, each at about half speed
  ... --whisper-threads 2  override Whisper's threads
  ... --make-clip          write mary\\laptop_check_clip.wav (spoken by Kokoro, not a recording of anyone)

It never reads the real %APPDATA%: APPDATA and TRACKER_DATA point at a scratch folder, unless
--appdata DIR is given. Models come from <project>\\models, then <APPDATA>\\CareIncidentLog\\models.
To use models elsewhere, copy them to <DIR>\\CareIncidentLog\\models\\ and pass --appdata DIR.
"""
import argparse
import ctypes
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import wave
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIP_TEXT = "Hey Mary, what a pretty morning. I'd like to sit and talk a while, and then I'd like a cup of coffee."
CLIP_PEAK = 0.8
BURN_LIMIT_S = 1800  # a burner ends by itself if this tool is killed
BURNER = f"import time\nend = time.monotonic() + {BURN_LIMIT_S}\nwhile time.monotonic() < end:\n    pass\n"
ROWS = ("kokoro_load_ms", "kokoro_first_ms", "kokoro_rtf", "whisper_load_ms", "whisper_ms", "whisper_rtf",
        "whisper_threads", "wake_load_ms", "wake_cpu_pct", "other_busy_pct", "plugged_in")


def parse_args():
    p = argparse.ArgumentParser(description="Time Mary's voice engines on this laptop.")
    p.add_argument("--make-clip", action="store_true", help="write the test clip and stop")
    p.add_argument("--cores", type=int, help="use N logical CPUs, every second one, and N Whisper threads")
    p.add_argument("--burn", action="store_true", help="a busy process on each of those CPUs (needs --cores)")
    p.add_argument("--whisper-threads", type=int, help="Whisper threads, overriding --cores")
    p.add_argument("--repeat", type=int, default=3, help="runs; each number printed is the median")
    p.add_argument("--json", action="store_true", help="print JSON instead of the table")
    p.add_argument("--appdata", help="use this folder as APPDATA instead of a scratch one")
    args = p.parse_args()
    if args.burn and not args.cores:
        p.error("--burn needs --cores")
    return args


def kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    return k


def pick_cpus(n):
    """n logical CPUs, every second one first so they sit on separate physical cores."""
    logical = os.cpu_count() or 1
    return (list(range(0, logical, 2)) + list(range(1, logical, 2)))[:n]


def pin(handle, cpus):
    if not kernel32().SetProcessAffinityMask(handle, sum(1 << cpu for cpu in cpus)):
        raise ctypes.WinError(ctypes.get_last_error())


def start_burners(cpus):
    burners = []
    for cpu in cpus:
        proc = subprocess.Popen([sys.executable, "-I", "-c", BURNER], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        burners.append(proc)
        pin(proc._handle, [cpu])
    return burners


def stop_burners(burners):
    for proc in burners:
        proc.kill()
        proc.wait()


def make_clip(speedcheck):
    import numpy as np
    import speech
    import voices
    if not voices.kokoro_ready():
        sys.exit("Kokoro isn't here: use the build venv, and --appdata if the models live elsewhere.")
    samples, rate = voices._load_kokoro().create(CLIP_TEXT, voice="af_heart", speed=1.0, lang="en-us")
    audio = speech._resample(np.asarray(samples, dtype=np.float32), rate)
    audio = audio * (CLIP_PEAK / float(np.max(np.abs(audio))))
    with wave.open(str(speedcheck.CLIP_PATH), "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(speedcheck.CLIP_RATE)
        clip.writeframes(voices._pcm16(audio))
    print(f"{speedcheck.CLIP_PATH}: {len(audio) / speedcheck.CLIP_RATE:.1f} s")


def medians(runs):
    """The last run, with every number replaced by its median over the runs."""
    out = dict(runs[-1])
    for key in {k for run in runs for k in run}:
        values = [run[key] for run in runs
                  if isinstance(run.get(key), (int, float)) and not isinstance(run.get(key), bool)]
        if values:
            out[key] = round(statistics.median(values), 3)
    return out


def show(result, tier, reasons, runs):
    print(f"median of {runs} run(s)")
    for key in ROWS + tuple(k for k in result if k.endswith("_error")):
        if key in result:
            print(f"  {key:<18}{result[key]}")
    if "whisper_text" in result:
        print(f"  heard: {result['whisper_text']}")
    print(f"tier: {tier}" + (f" ({'; '.join(reasons)})" if reasons else ""))


def timed_runs(speedcheck, args):
    cpus = pick_cpus(args.cores) if args.cores else []
    if cpus:
        pin(kernel32().GetCurrentProcess(), cpus)
    burners = []
    try:
        if args.burn:
            burners = start_burners(cpus)
        threads = args.whisper_threads or args.cores
        return [speedcheck.run_check(speedcheck.default_steps(threads)) for _ in range(max(1, args.repeat))]
    finally:
        stop_burners(burners)


def main():
    args = parse_args()
    scratch = tempfile.mkdtemp(prefix="laptop-check-tool-")
    os.environ["APPDATA"] = args.appdata or scratch  # before any app module is imported
    os.environ["TRACKER_DATA"] = scratch
    sys.path.insert(0, str(ROOT))
    import speedcheck
    try:
        if args.make_clip:
            return make_clip(speedcheck)
        runs = timed_runs(speedcheck, args)
        result = medians(runs)
        tier, reasons = speedcheck.pick_tier(result)
        if args.json:
            print(json.dumps({"median": result, "tier": tier, "reasons": reasons, "runs": runs}))
        else:
            show(result, tier, reasons, len(runs))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
