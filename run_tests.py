"""Quiet test runner.

    python run_tests.py       verbose (one line per test)
    python run_tests.py -q    prints only failures/errors, then one summary line

Always runs on scratch data (see tests/helpers.py). Exit code 0 = all passed, 1 = something failed.
"""
import sys
import time
import unittest
from pathlib import Path

for _s in (sys.stdout, sys.stderr):   # a non-cp1252 character must not crash the printing
    try:
        _s.reconfigure(errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import tests.helpers  # noqa: E402,F401  (sets up scratch data BEFORE server is imported)


def main(argv):
    quiet = "-q" in argv
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    if quiet:
        runner = unittest.TextTestRunner(stream=_Sink(), verbosity=0)
    else:
        runner = unittest.TextTestRunner(stream=sys.stderr, verbosity=2)
    start = time.time()
    result = runner.run(suite)
    secs = time.time() - start

    if quiet:
        for _, tb in result.failures + result.errors:
            print(tb.rstrip())
            print()
    for test, reason in result.skipped:
        if reason.startswith("BUG:"):
            print(f"{reason} ({test.id()})")

    total = result.testsRun
    if result.wasSuccessful():
        skipped = f", {len(result.skipped)} skipped" if result.skipped else ""
        print(f"OK: {total} tests{skipped}, {secs:.1f}s")
        return 0
    print(f"FAILED: {len(result.failures)} failures, {len(result.errors)} errors of {total} tests, {secs:.1f}s")
    return 1


class _Sink:
    """Swallows the runner's own output so -q prints only what main() chooses to."""

    def write(self, _):
        pass

    def flush(self):
        pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
