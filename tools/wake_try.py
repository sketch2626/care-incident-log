"""Try "Hey Mary" / "Hey Sam" on the real microphone, hands-free (no keys to press).

Two timed parts, shown in big letters with a countdown every 15 seconds:
  1. QUIET TEST: TV on, talk normally, but do not say the wake words. Every wake is a false wake.
  2. Say "Hey Mary" or "Hey Sam" from across the room, about 10 times.
Each wake prints a big HEARD YOU banner and rings the terminal bell. Near misses (Vosk heard it,
Whisper said no) are shown too. The summary is printed big and saved to %TEMP%\\wake_try_results.txt.
Ctrl+C stops it safely. Nothing goes to the network.

Run: python tools/wake_try.py  [--minutes 3]   (minutes for each part)
"""
import argparse
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TRACKER_DATA", str(Path(tempfile.gettempdir()) / "wake_try_data"))

import wakeword  # noqa: E402

RESULTS = Path(tempfile.gettempdir()) / "wake_try_results.txt"
TICK_S = 15
WIDTH = 64

_lock = threading.Lock()
_phase = {"n": 0, "t0": 0.0}
_log = {1: [], 2: []}        # phase -> list of wake events
_misses = {1: [], 2: []}     # phase -> list of (stage1, whisper) near misses


def banner(lines, ch="#"):
    out = [ch * WIDTH]
    for line in lines:
        out.append(f"{ch}{ch}  {line}".ljust(WIDTH - 2) + ch * 2)
    out.append(ch * WIDTH)
    print("\n" + "\n".join(out) + "\n", flush=True)


def on_wake(e):
    now = time.time()
    with _lock:
        n = _phase["n"]
        if n not in _log:
            return
        _log[n].append({"t": now, "event": e})
    name = (e.get("name") or "mary").upper()
    what = "FALSE WAKE (quiet test)" if n == 1 else "HEARD YOU"
    banner([f"{what} - HEY {name}", time.strftime("%H:%M:%S"),
            f"Whisper heard: {e.get('confirm_text')!r}", f"check took {e.get('confirm_ms')} ms"])
    print("\a", end="", flush=True)


def on_reject(stage1, whisper):
    with _lock:
        n = _phase["n"]
        if n in _misses:
            _misses[n].append((stage1, whisper))
    print(f"   (almost: Whisper heard {whisper!r})", flush=True)


def run_phase(n, seconds, title_lines):
    banner(title_lines, "=")
    with _lock:
        _phase["n"], _phase["t0"] = n, time.time()
    end = time.time() + seconds
    next_tick = time.time() + TICK_S
    while True:
        left = end - time.time()
        if left <= 0:
            break
        if time.time() >= next_tick:
            m, s = divmod(int(left + 0.5), 60)
            with _lock:
                count = len(_log[n])
            print(f"   ... {m}:{s:02d} left   (wakes so far: {count})", flush=True)
            next_tick += TICK_S
        time.sleep(min(0.25, left))
    with _lock:
        _phase["n"] = 0


def summary(cpu_pct, stopped_early):
    p1, p2 = len(_log[1]), len(_log[2])
    st = wakeword.status()
    ms = [w["event"].get("confirm_ms") for n in (1, 2) for w in _log[n] if w["event"].get("confirm_ms")]
    # after Vosk hears the name: up to CONFIRM_WAIT_S of waiting for the phrase to end, then Whisper's check
    delay = (f"about {wakeword.CONFIRM_WAIT_S + sum(ms) / len(ms) / 1000:.1f} s after the name "
             f"(Whisper check {sum(ms) / len(ms):.0f} ms)") if ms else "-"
    lines = [
        "WAKE WORD TRY - RESULTS" + ("  (stopped early)" if stopped_early else ""),
        "",
        f"Part 1 quiet test: {p1} false wake(s)",
        f"Part 2 wake test:  {p2} wake(s) (asked for about 10)",
        f"Near misses: part 1 {len(_misses[1])}, part 2 {len(_misses[2])}",
        f"Avg wake delay: {delay}",
        f"CPU while listening: {cpu_pct:.1f}% of one core",
    ]
    if st.get("problem"):
        lines.append(f"Problem: {st['problem']}")
    detail = []
    for n in (1, 2):
        for w in _log[n]:
            e = w["event"]
            detail.append(f"part {n} wake {time.strftime('%H:%M:%S', time.localtime(w['t']))} "
                          f"{e.get('name')}: {e.get('confirm_text')!r} ({e.get('confirm_ms')} ms)")
        for s1, wh in _misses[n]:
            detail.append(f"part {n} near miss: Vosk {s1!r}, Whisper {wh!r}")
    banner(lines)
    text = "\n".join(lines + ["", "Details:"] + (detail or ["(none)"])) + "\n"
    RESULTS.write_text(text, encoding="utf-8")
    print("\n".join(detail))
    print(f"\nSaved to {RESULTS}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=3.0, help="minutes for each part (default 3)")
    a = ap.parse_args()
    ok, why = wakeword.available()
    if not ok:
        banner(["CANNOT START", why])
        return 1
    seconds = max(5.0, a.minutes * 60)
    wakeword.on_reject = on_reject
    stopped_early = False
    c0 = w0 = None
    try:
        banner(["Getting ready... the microphone is opening."], "=")
        wakeword.start(on_wake)
        time.sleep(3.0)
        st = wakeword.status()
        if st.get("problem"):
            banner(["MICROPHONE PROBLEM", st["problem"]])
        c0, w0 = time.process_time(), time.time()
        run_phase(1, seconds, [
            "PART 1: QUIET TEST",
            "Leave your TV on and talk normally,",
            "but do NOT say Hey Mary or Hey Sam.",
            f"This part lasts {seconds / 60:g} minutes.",
        ])
        run_phase(2, seconds, [
            "PART 2: NOW SAY 'HEY MARY' OR 'HEY SAM'",
            "From across the room, about 10 times.",
            "Wait for HEARD YOU each time.",
            f"This part lasts {seconds / 60:g} minutes.",
        ])
    except KeyboardInterrupt:
        stopped_early = True
    finally:
        wakeword.stop()
        wakeword.on_reject = None
    cpu = 100.0 * (time.process_time() - c0) / max(0.1, time.time() - w0) if c0 is not None else 0.0
    summary(cpu, stopped_early)
    return 0


if __name__ == "__main__":
    sys.exit(main())
