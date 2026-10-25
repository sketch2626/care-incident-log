"""Mary speed test: can she start answering within about 2 seconds on this laptop?

How to run (from the project folder):

    set GEMINI_API_KEY=your-key-here
    python tools/mary_speed.py            # add -v for one line per turn

It speaks each scripted "speed" turn from tests/mary_conversations.json with Windows' built-in
voice, runs the on-device speech-to-text on it, then sends the same scripted words to Mary
(Gemini) and times the first text and the full reply. The target is judged on the median of
(speech-to-text time + Gemini first-text time). Without GEMINI_API_KEY the Gemini part is skipped.
GEMINI_MODEL picks the model (otherwise Mary's default). Flags: --no-speech, --no-gemini,
--keep (keep the scratch folder), -v.

Safe by design: everything runs in a scratch folder (TRACKER_DATA and APPDATA point there), so
the real incident log, Andy Flow data and Mary's real memory are never touched.
"""
import atexit
import os
import shutil
import sys
import tempfile

_ORIG_ENV = dict(os.environ)  # the Windows voice subprocess gets the real environment
SCRATCH = tempfile.mkdtemp(prefix="mary-speed-")
os.environ["TRACKER_DATA"] = os.path.join(SCRATCH, "data")
os.environ["APPDATA"] = SCRATCH
_KEEP = False


def _cleanup():
    if _KEEP:
        print(f"Scratch folder kept: {SCRATCH}")
    else:
        shutil.rmtree(SCRATCH, ignore_errors=True)


atexit.register(_cleanup)

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import platform  # noqa: E402
import re  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TARGET_S = 2.0

PS_SCRIPT = r"""param([string]$JsonPath)
Add-Type -AssemblyName System.Speech
$items = Get-Content -Raw -Encoding UTF8 -Path $JsonPath | ConvertFrom-Json
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    foreach ($it in $items) {
        $synth.SetOutputToWaveFile($it.path)
        $synth.Speak($it.text)
    }
} finally {
    $synth.SetOutputToNull()
    $synth.Dispose()
}
"""


def median(vals):
    return statistics.median(vals) if vals else None


def p90(vals):
    if not vals:
        return None
    s = sorted(vals)
    return s[max(0, math.ceil(0.9 * len(s)) - 1)]


def stats(vals):
    m, p = median(vals), p90(vals)
    return (f"median {m:.2f}s, p90 {p:.2f}s" if vals else "median n/a, p90 n/a")


def words(text):
    text = text.lower().replace("’", "").replace("'", "")
    return re.findall(r"[a-z0-9]+", text)


def norm(text):
    return text.replace("’", "'").lower()


def load_turns():
    data = json.loads((ROOT / "tests" / "mary_conversations.json").read_text(encoding="utf-8"))
    turns = []
    for case in data["cases"]:
        if not case.get("speed"):
            continue
        for i, t in enumerate(case["turns"], 1):
            turns.append({"case": case["id"], "label": f"{case['id']}#{i}", "say": t["say"],
                          "expect": t.get("expect", {})})
    return turns


def make_wavs(turns):
    """Speak every turn with Windows' built-in voice. Returns an error string, or None if all is well."""
    wavdir = Path(SCRATCH) / "wav"
    wavdir.mkdir(parents=True, exist_ok=True)
    items = []
    for i, t in enumerate(turns):
        t["wav"] = wavdir / f"{i:02d}.wav"
        items.append({"path": str(t["wav"]), "text": t["say"]})
    jpath = Path(SCRATCH) / "say.json"
    jpath.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    ps1 = Path(SCRATCH) / "say.ps1"
    ps1.write_text(PS_SCRIPT, encoding="ascii")
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1), str(jpath)],
            env=_ORIG_ENV, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Windows voice could not run ({e})"
    if done.returncode != 0:
        return "Windows voice failed: " + (done.stderr or done.stdout).strip()[:200]
    missing = [t["label"] for t in turns if not t["wav"].is_file() or t["wav"].stat().st_size < 1000]
    return f"Windows voice made no audio for {', '.join(missing)}" if missing else None


def run_speech(turns, verbose):
    """Fills t['stt_s'] and t['heard']. Returns (load_s, error). error is set when the part was skipped."""
    import speech
    reason = speech._missing_dependency()
    if reason:
        return None, reason
    err = make_wavs(turns)
    if err:
        return None, err
    t0 = time.perf_counter()
    try:
        speech._wait_for_model()
    except Exception as e:
        return None, f"speech model did not load ({e})"
    load_s = time.perf_counter() - t0
    for t in turns:
        t0 = time.perf_counter()
        try:
            t["heard"] = speech.transcribe_file(t["wav"])
            t["stt_s"] = time.perf_counter() - t0
        except Exception as e:
            t["heard"], t["stt_s"] = "", None
            t["stt_error"] = str(e)[:120]
            continue
        scripted = words(t["say"])
        heard = set(words(t["heard"]))
        t["words_total"] = len(scripted)
        t["words_found"] = sum(1 for w in scripted if w in heard)
        if verbose:
            pct = 100 * t["words_found"] / max(1, t["words_total"])
            print(f"  {t['label']}: speech-to-text {t['stt_s']:.2f}s, words {pct:.0f}%")
    return load_s, None


def run_gemini(turns, api_key, model, verbose):
    """Fills t['first_s'], t['full_s'], t['error'], t['reply'], t['ok'] for every turn."""
    import mary
    probe = {"first": None}
    original = mary._gemini_stream

    def timed(body, key, mdl=""):
        t0 = time.monotonic()
        for chunk in original(body, key, mdl):
            if probe["first"] is None:
                probe["first"] = time.monotonic() - t0
            yield chunk

    mary._gemini_stream = timed
    memories = {}
    memdir = Path(SCRATCH) / "mem"
    memdir.mkdir(parents=True, exist_ok=True)
    try:
        for t in turns:
            memory = memories.get(t["case"])
            if memory is None:
                memory = memories[t["case"]] = mary.Memory(memdir / f"{t['case']}.json")
            probe["first"] = None
            try:
                r = mary.reply(t["say"], memory, api_key, model)
            except Exception as e:
                r = {"text": "", "error": f"{type(e).__name__}: {e}", "total_s": None}
            t["first_s"] = probe["first"]
            t["full_s"] = r.get("total_s")
            t["error"] = r.get("error") or ""
            t["reply"] = r.get("text") or ""
            text = norm(t["reply"])
            expect = t["expect"]
            any_of = expect.get("reply_any") or []
            t["ok"] = (not t["error"]
                       and (not any_of or any(norm(a) in text for a in any_of))
                       and not any(norm(n) in text for n in expect.get("reply_none") or []))
            if verbose:
                first = f"{t['first_s']:.2f}s" if t["first_s"] is not None else "n/a"
                full = f"{t['full_s']:.2f}s" if t["full_s"] is not None else "n/a"
                print(f"  {t['label']}: Gemini first {first}, full {full}, "
                      f"{'ok' if t['ok'] else 'FAILED'}")
    finally:
        mary._gemini_stream = original


def main():
    global _KEEP
    ap = argparse.ArgumentParser(description="Time Mary's speech-to-text and Gemini reply.")
    ap.add_argument("--no-speech", action="store_true", help="skip the speech-to-text part")
    ap.add_argument("--no-gemini", action="store_true", help="skip the Gemini part")
    ap.add_argument("--keep", action="store_true", help="keep the scratch folder")
    ap.add_argument("-v", "--verbose", action="store_true", help="one line per turn")
    args = ap.parse_args()
    _KEEP = args.keep

    import assist
    turns = load_turns()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("GEMINI_MODEL", "").strip()
    use_gemini = bool(api_key) and not args.no_gemini
    gemini_skip = "--no-gemini given" if args.no_gemini else "no GEMINI_API_KEY set"

    load_s, speech_skip = None, None
    if args.no_speech:
        speech_skip = "--no-speech given"
    else:
        load_s, speech_skip = run_speech(turns, args.verbose)
    if use_gemini:
        run_gemini(turns, api_key, model, args.verbose)

    gemini_name = model or assist.DEFAULT_MODEL
    import speech
    print(f"Mary speed test on {platform.processor() or platform.machine()}, {os.cpu_count()} threads, "
          f"model {gemini_name if use_gemini else speech.MODEL_NAME}")

    stt = [t["stt_s"] for t in turns if t.get("stt_s") is not None]
    if speech_skip:
        print(f"Speech part skipped: {speech_skip}.")
    else:
        found = sum(t.get("words_found", 0) for t in turns)
        total = sum(t.get("words_total", 0) for t in turns)
        pct = f"{100 * found / total:.0f}%" if total else "n/a"
        print(f"Speech model load (once at startup): {load_s:.2f}s")
        print(f"Speech-to-text per turn: {stats(stt)} (n={len(stt)}), words matched {pct}")

    if not use_gemini:
        print(f"Gemini part skipped: {gemini_skip}.")
        return 0

    firsts = [t["first_s"] for t in turns if t.get("first_s") is not None]
    fulls = [t["full_s"] for t in turns if t.get("full_s") is not None]
    print(f"Gemini first text: {stats(firsts)}")
    print(f"Gemini full reply: {stats(fulls)}")
    combined = [t["stt_s"] + t["first_s"] for t in turns
                if t.get("stt_s") is not None and t.get("first_s") is not None]
    if combined:
        verdict = "MET" if median(combined) <= TARGET_S else "MISSED"
        print(f"Heard -> Mary starts talking (speech-to-text + Gemini first text): {stats(combined)} "
              f"-> target {TARGET_S:.1f}s: {verdict}")
    else:
        print("Heard -> Mary starts talking (speech-to-text + Gemini first text): n/a "
              "(needs both speech and Gemini measured)")
    passed = [t for t in turns if t["ok"]]
    failed = [t for t in turns if not t["ok"]]
    line = f"Behavior checks: {len(passed)}/{len(turns)} passed."
    if failed:
        bits = [f'{t["case"]}: "{(t["error"] or t["reply"])[:120]}"' for t in failed]
        line += " Failed: " + "; ".join(bits)
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
