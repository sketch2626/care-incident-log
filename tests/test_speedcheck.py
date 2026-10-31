"""M8: the first-run laptop speed check. Fakes only: no real child process, models or timing."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tests import helpers

import server
import speedcheck
from speedcheck import Checker

try:
    import numpy  # noqa: F401
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

CPU = "TestCPU"
FAST = {"whisper_rtf": 0.3, "kokoro_rtf": 1.0, "kokoro_first_ms": 3000, "wake_cpu_pct": 3.0,
        "other_busy_pct": 5.0, "plugged_in": True}
SLOW = {"whisper_rtf": 1.0, "kokoro_rtf": 2.0, "kokoro_first_ms": 6000, "wake_cpu_pct": 3.0}


def join_check(timeout=5):
    for t in threading.enumerate():
        if t.name == "laptop-check":
            t.join(timeout)


class FakeStdin:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeProc:
    def __init__(self, command, result, timeout):
        self.command = command
        self.timeout = timeout
        self.killed = False
        self.waits = []
        self.stdin = FakeStdin()
        if result is not None and not timeout:
            with open(command[-1], "w", encoding="utf-8") as f:
                json.dump(result, f)

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.timeout and not self.killed:
            raise subprocess.TimeoutExpired("fake", timeout)
        return 0

    def kill(self):
        self.killed = True


class Rig:
    """A Checker with a dict settings store and a fake spawn."""

    def __init__(self, result=None, timeout=False, times=None, free_gb=lambda: 8.0, sleeper=lambda s: None,
                 settings=None):
        self.settings = {} if settings is None else settings
        self.result = FAST if result is None else result
        self.timeout = timeout
        self.procs = []
        self.sleeps = []
        self.sleeper = sleeper
        self.checker = Checker(lambda: dict(self.settings), self.settings.update, self._sleep,
                               lambda: datetime(2026, 10, 31, 12, 0, 0), self._spawn,
                               times or (lambda handle: None), free_gb)

    def _sleep(self, seconds):
        self.sleeps.append(seconds)
        self.sleeper(seconds)

    def _spawn(self, command):
        proc = FakeProc(command, self.result, self.timeout)
        self.procs.append(proc)
        return proc

    def record(self):
        return json.loads(self.settings[speedcheck.SETTING_KEY])


class Patched(unittest.TestCase):
    def setUp(self):
        for name, value in (("cpu_name", lambda: CPU), ("ram_gb", lambda: 16.0), ("_plugged_in", lambda: True)):
            p = mock.patch.object(speedcheck, name, value)
            p.start()
            self.addCleanup(p.stop)


class PickTierTests(unittest.TestCase):
    def test_all_fast_is_normal(self):
        self.assertEqual(speedcheck.pick_tier(FAST), ("normal", []))

    def test_each_threshold_alone_picks_light(self):
        for key, limit in (("whisper_rtf", speedcheck.LIGHT_WHISPER_RTF),
                           ("kokoro_rtf", speedcheck.LIGHT_KOKORO_RTF),
                           ("kokoro_first_ms", speedcheck.LIGHT_KOKORO_FIRST_MS),
                           ("wake_cpu_pct", speedcheck.LIGHT_WAKE_CPU_PCT)):
            with self.subTest(key=key):
                tier, reasons = speedcheck.pick_tier({**FAST, key: limit + 0.5})
                self.assertEqual(tier, "light")
                self.assertEqual(len(reasons), 1)
                self.assertIn(key, reasons[0])
                self.assertEqual(speedcheck.pick_tier({**FAST, key: limit}), ("normal", []))

    def test_timeout_and_whisper_failure_pick_light(self):
        self.assertEqual(speedcheck.pick_tier({**FAST, "timed_out": True})[0], "light")
        self.assertEqual(speedcheck.pick_tier({**FAST, "whisper_error": "RuntimeError"})[0], "light")

    def test_missing_engines_say_nothing(self):
        for extra in ({"whisper_error": "missing"}, {"whisper_error": "ImportError"},
                      {"kokoro_error": "missing"}):
            with self.subTest(extra=extra):
                self.assertEqual(speedcheck.pick_tier({**FAST, **extra}), ("normal", []))

    def test_nothing_measured(self):
        self.assertEqual(speedcheck.pick_tier({}), ("normal", ["nothing measured"]))


class SettleTests(unittest.TestCase):
    def test_quiet_slow_saves_light(self):
        r = speedcheck.settle({**SLOW, "other_busy_pct": 5, "plugged_in": True}, None, "c", "v")
        self.assertEqual((r["tier"], r["unsure"], r["tries"]), ("light", False, 0))

    def test_busy_slow_counts_tries_then_accepts(self):
        slow = {**SLOW, "other_busy_pct": speedcheck.BUSY_LIMIT_PCT + 10, "plugged_in": True}
        prev = None
        for expected in range(1, speedcheck.MAX_UNSURE_TRIES):
            r = speedcheck.settle(slow, prev, "c", "v")
            self.assertEqual((r["tier"], r["unsure"], r["tries"]), ("normal", True, expected))
            prev = {**r, "cpu_name": "c", "version": "v"}
        r = speedcheck.settle(slow, prev, "c", "v")
        self.assertEqual((r["tier"], r["unsure"], r["tries"]),
                         ("light", False, speedcheck.MAX_UNSURE_TRIES))

    def test_battery_slow_is_unsure_and_keeps_previous_tier(self):
        slow = {**SLOW, "other_busy_pct": 1, "plugged_in": False}
        r = speedcheck.settle(slow, {"tier": "light", "unsure": False}, "c", "v")
        self.assertEqual((r["tier"], r["unsure"], r["tries"]), ("light", True, 1))

    def test_fast_while_busy_is_normal_and_sure(self):
        r = speedcheck.settle({**FAST, "other_busy_pct": 80}, None, "c", "v")
        self.assertEqual((r["tier"], r["unsure"], r["tries"]), ("normal", False, 0))

    def test_changed_cpu_or_version_resets_tries(self):
        slow = {**SLOW, "other_busy_pct": 90}
        prev = {"tier": "normal", "unsure": True, "tries": 2, "cpu_name": "c", "version": "v"}
        self.assertEqual(speedcheck.settle(slow, prev, "other", "v")["tries"], 1)
        self.assertEqual(speedcheck.settle(slow, prev, "c", "w")["tries"], 1)
        self.assertEqual(speedcheck.settle(slow, prev, "c", "v")["tries"], 3)

    def test_nothing_measured_keeps_tier_and_is_unsure(self):
        r = speedcheck.settle({}, {"tier": "light"}, "c", "v")
        self.assertEqual((r["tier"], r["unsure"], r["tries"]), ("light", True, 1))
        self.assertEqual(speedcheck.settle({}, None, "c", "v")["tier"], "normal")


class NeededTests(unittest.TestCase):
    def rec(self, **kw):
        base = {"tier": "normal", "unsure": False, "tries": 0, "cpu_name": "c", "version": "v"}
        return {speedcheck.SETTING_KEY: json.dumps({**base, **kw})}

    def test_needed(self):
        n = Checker.needed
        self.assertTrue(n({}, "c", "v"))
        self.assertTrue(n({speedcheck.SETTING_KEY: "{not json"}, "c", "v"))
        self.assertTrue(n(self.rec(), "other", "v"))
        self.assertTrue(n(self.rec(), "c", "w"))
        self.assertTrue(n(self.rec(unsure=True, tries=speedcheck.MAX_UNSURE_TRIES - 1), "c", "v"))

    def test_not_needed(self):
        n = Checker.needed
        self.assertFalse(n(self.rec(), "c", "v"))
        self.assertFalse(n(self.rec(unsure=True, tries=speedcheck.MAX_UNSURE_TRIES), "c", "v"))


class SavedRecordTests(Patched):
    def test_record_fields_and_tier(self):
        rig = Rig(result=SLOW)
        self.assertTrue(rig.checker.run_now())
        join_check()
        rec = rig.record()
        for key in ("tier", "timings", "reasons", "date", "cpu_name", "cores", "version", "unsure",
                    "tries", "timed_out", "ram_gb"):
            self.assertIn(key, rec)
        self.assertEqual(rec["tier"], "light")
        self.assertEqual(rec["cpu_name"], CPU)
        self.assertEqual(rec["version"], speedcheck.VERSION)
        self.assertEqual(rec["date"], "2026-10-31T12:00:00")
        self.assertEqual(rec["ram_gb"], 16.0)
        self.assertEqual(rec["cores"], os.cpu_count())
        self.assertIs(rec["timed_out"], False)
        self.assertEqual(rec["timings"]["whisper_rtf"], 1.0)
        self.assertEqual(rig.checker.tier, "light")
        again = Checker(rig.checker.load_settings, rig.checker.save_settings)
        again.apply_saved()
        self.assertEqual(again.tier, "light")

    def test_garbage_tier_is_normal(self):
        rig = Rig(settings={speedcheck.SETTING_KEY: json.dumps({"tier": "turbo"})})
        rig.checker.tier = "light"
        rig.checker.apply_saved()
        self.assertEqual(rig.checker.tier, "normal")

    def test_raising_load_does_not_raise(self):
        def boom():
            raise OSError("db locked")
        c = Checker(boom, lambda v: None)
        with self.assertLogs("care.speedcheck", level="ERROR"):
            c.apply_saved()
        self.assertEqual(c.tier, "normal")
        self.assertEqual(c.status(), {"running": False, "tier": "normal", "record": None})


class NeverBlocksTests(Patched):
    def test_start_after_window_returns_at_once(self):
        gate = threading.Event()
        rig = Rig(sleeper=lambda s: gate.wait(10))
        try:
            started = threading.Event()
            t = threading.Thread(target=lambda: (rig.checker.start_after_window(), started.set()))
            t.start()
            self.assertTrue(started.wait(1.0))
            self.assertEqual(rig.procs, [])
            self.assertEqual(rig.sleeps, [speedcheck.START_DELAY_S])
            self.assertTrue(rig.checker._running)
        finally:
            gate.set()
        join_check()
        self.assertEqual(len(rig.procs), 1)
        self.assertIn(speedcheck.SETTING_KEY, rig.settings)
        self.assertFalse(rig.checker._running)

    def test_second_start_does_nothing(self):
        rig = Rig()
        rig.checker.start_after_window()
        join_check()
        rig.settings.clear()
        rig.checker.start_after_window()
        join_check()
        self.assertEqual(len(rig.procs), 1)

    def test_spawn_raising_does_not_raise_out(self):
        rig = Rig()

        def boom(command):
            raise OSError("no exe")
        rig.checker.spawn = boom
        with self.assertLogs("care.speedcheck", level="ERROR"):
            rig.checker.start_after_window()
            join_check()
        self.assertFalse(rig.checker._running)
        self.assertNotIn(speedcheck.SETTING_KEY, rig.settings)

    def test_not_needed_never_spawns(self):
        settings = {speedcheck.SETTING_KEY: json.dumps(
            {"tier": "normal", "unsure": False, "tries": 0, "cpu_name": CPU, "version": speedcheck.VERSION})}
        rig = Rig(settings=settings)
        rig.checker.start_after_window()
        join_check()
        self.assertEqual(rig.procs, [])
        self.assertFalse(rig.checker._running)

    def test_low_free_ram_skips_auto_but_not_run_now(self):
        rig = Rig(free_gb=lambda: speedcheck.MIN_FREE_GB - 0.1)
        rig.checker.start_after_window()
        join_check()
        self.assertEqual(rig.procs, [])
        self.assertNotIn(speedcheck.SETTING_KEY, rig.settings)
        self.assertTrue(rig.checker.run_now())
        join_check()
        self.assertEqual(len(rig.procs), 1)
        self.assertIn(speedcheck.SETTING_KEY, rig.settings)

    def test_free_ram_unknown_runs(self):
        rig = Rig(free_gb=lambda: None)
        rig.checker.start_after_window()
        join_check()
        self.assertEqual(len(rig.procs), 1)

    def test_enough_free_ram_exactly_at_limit_runs(self):
        rig = Rig(free_gb=lambda: speedcheck.MIN_FREE_GB)
        rig.checker.start_after_window()
        join_check()
        self.assertEqual(len(rig.procs), 1)


class RunNowTests(Patched):
    def test_no_delay_and_runs_even_if_not_needed(self):
        settings = {speedcheck.SETTING_KEY: json.dumps(
            {"tier": "normal", "unsure": False, "tries": 0, "cpu_name": CPU, "version": speedcheck.VERSION})}
        rig = Rig(settings=settings)
        self.assertTrue(rig.checker.run_now())
        join_check()
        self.assertEqual(rig.sleeps, [])
        self.assertEqual(len(rig.procs), 1)

    def test_false_while_running(self):
        gate = threading.Event()
        rig = Rig()
        orig = rig.checker.spawn

        def slow_spawn(command):
            gate.wait(10)
            return orig(command)
        rig.checker.spawn = slow_spawn
        try:
            self.assertTrue(rig.checker.run_now())
            self.assertFalse(rig.checker.run_now())
        finally:
            gate.set()
        join_check()
        self.assertEqual(len(rig.procs), 1)
        self.assertTrue(rig.checker.run_now())
        join_check()

    def test_false_when_not_configured(self):
        c = Checker()
        self.assertFalse(c.run_now())
        c.start_after_window()
        self.assertFalse(c._running)


class TimeoutTests(Patched):
    def make_times(self, end):
        readings = iter([(0, 0, 0), end])
        return lambda handle: next(readings, end)

    def test_timeout_kills_and_picks_light_when_quiet(self):
        rig = Rig(timeout=True, times=self.make_times((100, 10, 0)))
        rig.checker.run_now()
        join_check()
        proc = rig.procs[0]
        self.assertTrue(proc.killed)
        self.assertTrue(proc.stdin.closed)
        self.assertEqual(proc.waits, [speedcheck.CHECK_TIMEOUT_S, speedcheck.KILL_WAIT_S])
        rec = rig.record()
        self.assertIs(rec["timed_out"], True)
        self.assertEqual((rec["tier"], rec["unsure"]), ("light", False))
        self.assertEqual(rec["timings"]["other_busy_pct"], 10.0)
        self.assertEqual(rig.checker.tier, "light")

    def test_timeout_while_busy_is_unsure(self):
        rig = Rig(timeout=True, times=self.make_times((100, 60, 0)))
        rig.checker.run_now()
        join_check()
        rec = rig.record()
        self.assertEqual((rec["tier"], rec["unsure"], rec["tries"]), ("normal", True, 1))
        self.assertEqual(rig.checker.tier, "normal")

    def test_child_leaving_nothing_is_unsure(self):
        rig = Rig()
        rig.result = None
        rig.checker.run_now()
        join_check()
        rec = rig.record()
        self.assertEqual((rec["tier"], rec["unsure"], rec["timings"]), ("normal", True, {}))


class RunCheckTests(unittest.TestCase):
    def test_failed_step_leaves_error_and_later_steps_run(self):
        def bad():
            raise ValueError("x")
        out = speedcheck.run_check([("a", bad), ("b", lambda: {"b_ms": 1})], times=lambda: None)
        self.assertEqual(out["a_error"], "ValueError")
        self.assertEqual(out["b_ms"], 1)
        self.assertIsNone(out["other_busy_pct"])

    def test_other_busy_from_times(self):
        readings = iter([(0, 0, 0), (1000, 300, 100)])
        with mock.patch.object(speedcheck, "_plugged_in", lambda: True):
            out = speedcheck.run_check([], times=lambda: next(readings))
        self.assertEqual(out["other_busy_pct"], 20.0)
        self.assertIs(out["plugged_in"], True)

    def test_other_busy_pct(self):
        f = speedcheck.other_busy_pct
        self.assertIsNone(f(None, (1, 1, 1)))
        self.assertIsNone(f((1, 1, 1), None))
        self.assertIsNone(f((5, 0, 0), (5, 1, 0)))  # no time passed
        self.assertEqual(f((0, 0, 0), (1000, 300, 100)), 20.0)
        self.assertEqual(f((0, 0, 0), (1000, 100, 500)), 0.0)  # never below zero


class StepTests(unittest.TestCase):
    def test_kokoro(self):
        engine = mock.Mock()
        engine.create.return_value = ([0.0] * 24000, 24000)  # one second
        voices = mock.Mock()
        voices.kokoro_ready.return_value = True
        voices._load_kokoro.return_value = engine
        ticks = iter([0.0, 1.0, 3.0])
        out = speedcheck.step_kokoro(clock=lambda: next(ticks), voices_mod=voices)
        self.assertEqual(out, {"kokoro_load_ms": 1000.0, "kokoro_first_ms": 2000.0, "kokoro_rtf": 2.0})
        self.assertEqual(engine.create.call_args.args[0], speedcheck.CHECK_SENTENCE)

    def test_kokoro_missing(self):
        voices = mock.Mock()
        voices.kokoro_ready.return_value = False
        self.assertEqual(speedcheck.step_kokoro(voices_mod=voices), {"kokoro_error": "missing"})
        voices._load_kokoro.assert_not_called()

    @unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
    def test_whisper_consumes_lazy_segments_before_done_clock(self):
        state = {"ran": False, "ran_at_done": None, "seen": 0}

        def segments():
            state["ran"] = True
            yield mock.Mock(text=" hello ")
            yield mock.Mock(text="world")

        model = mock.Mock()
        model.transcribe.side_effect = lambda audio, **kw: (segments(), None)
        factory = mock.Mock(return_value=model)
        ticks = iter([0.0, 0.5, 2.5])

        def clock():
            state["seen"] += 1
            if state["seen"] == 3:
                state["ran_at_done"] = state["ran"]
            return next(ticks)

        speech = mock.Mock()
        speech._find_model_dir.return_value = Path("fake-model")
        pcm = b"\x00\x00" * 16000  # one second
        out = speedcheck.step_whisper(pcm, clock=clock, threads=3, speech_mod=speech, model_factory=factory)
        self.assertIs(state["ran_at_done"], True)
        self.assertEqual(out, {"whisper_load_ms": 500.0, "whisper_ms": 2000.0, "whisper_rtf": 2.0,
                               "whisper_text": "hello world", "whisper_threads": 3})
        self.assertEqual(factory.call_args.kwargs["cpu_threads"], 3)

    def test_whisper_missing(self):
        speech = mock.Mock()
        speech._find_model_dir.return_value = None
        self.assertEqual(speedcheck.step_whisper(b"\x00\x00", speech_mod=speech), {"whisper_error": "missing"})
        speech._find_model_dir.return_value = Path("m")
        self.assertEqual(speedcheck.step_whisper(None, speech_mod=speech), {"whisper_error": "missing"})

    def test_wake(self):
        fed = []

        class Detector:
            def __init__(self, names, confirm):
                self.names, self.confirm = names, confirm

            def feed(self, block):
                fed.append(len(block))

        wake = mock.Mock()
        wake.find_model_dir.return_value = Path("m")
        wake.Detector = Detector
        wake._vosk_models = {"x": 1}
        pcm = b"\x00" * 64000  # two seconds: repeated to reach four
        ticks = iter([0.0, 0.25])
        cpu = iter([10.0, 11.0])
        out = speedcheck.step_wake(pcm, clock=lambda: next(ticks), cpu_clock=lambda: next(cpu), wake_mod=wake)
        self.assertEqual(out, {"wake_load_ms": 250.0, "wake_cpu_pct": 25.0})
        self.assertEqual(sum(fed), 128000)
        self.assertEqual(set(fed), {speedcheck.WAKE_BLOCK_BYTES})
        self.assertEqual(wake._vosk_models, {})

    def test_wake_missing(self):
        wake = mock.Mock()
        wake.find_model_dir.return_value = None
        self.assertEqual(speedcheck.step_wake(b"\x00\x00", wake_mod=wake), {"wake_error": "missing"})
        wake.find_model_dir.return_value = Path("m")
        self.assertEqual(speedcheck.step_wake(b"", wake_mod=wake), {"wake_error": "missing"})


class GuardTests(unittest.TestCase):
    def test_closed_pipe_exits(self):
        done = threading.Event()
        calls = []
        speedcheck._start_guards(limit=60, exit_fn=lambda code: (calls.append(code), done.set()),
                                 pipe_open=lambda: False, poll_s=0.001)
        self.assertTrue(done.wait(2))
        self.assertEqual(calls, [0])

    def test_none_stops_watching_without_exit(self):
        calls = []
        polled = []

        def pipe():
            polled.append(1)
            return None
        speedcheck._start_guards(limit=60, exit_fn=calls.append, pipe_open=pipe, poll_s=0.001)
        threading.Event().wait(0.1)
        self.assertEqual(calls, [])
        self.assertEqual(len(polled), 1)

    def test_timer_limit_fires(self):
        done = threading.Event()
        calls = []

        def exit_fn(code):
            calls.append(code)
            done.set()
        speedcheck._start_guards(limit=0.05, exit_fn=exit_fn, pipe_open=lambda: None if done.is_set() else True,
                                 poll_s=0.001)
        self.assertTrue(done.wait(2))
        self.assertEqual(calls, [0])


class ChildMainTests(unittest.TestCase):
    def test_writes_json_and_exits(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "result.json")
            exits, guards = [], []
            with mock.patch.object(speedcheck, "_plugged_in", lambda: True), \
                    mock.patch.object(speedcheck, "machine_times", lambda process=None: None):
                speedcheck.child_main(out, steps=[("a", lambda: {"x": 1})], guards=lambda: guards.append(1),
                                      exit_fn=exits.append)
            with open(out, encoding="utf-8") as f:
                data = json.load(f)
        self.assertEqual(data["x"], 1)
        self.assertIn("other_busy_pct", data)
        self.assertEqual(exits, [0])
        self.assertEqual(guards, [1])

    def test_failed_write_still_exits(self):
        exits = []
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "no-such-folder", "result.json")
            with mock.patch.object(speedcheck, "_plugged_in", lambda: True):
                speedcheck.child_main(out, steps=[], guards=lambda: None, exit_fn=exits.append)
        self.assertEqual(exits, [0])


class ThreadsAndCommandTests(unittest.TestCase):
    def setUp(self):
        self.saved = speedcheck.CHECK.tier
        self.addCleanup(setattr, speedcheck.CHECK, "tier", self.saved)

    def test_whisper_threads(self):
        for cores, normal, light in ((8, 8, 4), (4, 4, 2), (2, 2, 2), (1, 1, 1)):
            for tier, expected in (("normal", normal), ("light", light)):
                with self.subTest(cores=cores, tier=tier), mock.patch("os.cpu_count", return_value=cores):
                    speedcheck.CHECK.tier = tier
                    self.assertEqual(speedcheck.whisper_threads(), expected)
        with mock.patch("os.cpu_count", return_value=None):
            speedcheck.CHECK.tier = "normal"
            self.assertEqual(speedcheck.whisper_threads(), 4)
        with mock.patch("os.cpu_count", return_value=32):
            self.assertEqual(speedcheck.whisper_threads(), 8)

    def test_unknown_tier_counts_as_normal(self):
        speedcheck.CHECK.tier = "turbo"
        with mock.patch("os.cpu_count", return_value=8):
            self.assertEqual(speedcheck.whisper_threads(), 8)

    def test_child_command_dev(self):
        with mock.patch.object(sys, "frozen", False, create=True), mock.patch.object(sys, "executable", "py.exe"):
            cmd = speedcheck.child_command("out.json")
        self.assertEqual(cmd[0], "py.exe")
        self.assertEqual(Path(cmd[1]), Path(speedcheck.__file__).resolve())
        self.assertEqual(cmd[2:], ["--laptop-check", "out.json"])

    def test_child_command_frozen(self):
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", "Mary.exe"):
            cmd = speedcheck.child_command("out.json")
        self.assertEqual(cmd, ["Mary.exe", "--laptop-check", "out.json"])


class RouteTests(Patched):
    ATTRS = ("load_settings", "save_settings", "sleeper", "clock", "spawn", "times", "free_gb", "tier",
             "_running", "_auto_started")

    def setUp(self):
        super().setUp()
        helpers.reset_db()
        c = speedcheck.CHECK
        saved = {a: getattr(c, a) for a in self.ATTRS}
        self.addCleanup(lambda: [setattr(c, a, v) for a, v in saved.items()])
        self.addCleanup(join_check)
        self.rig = Rig()
        c.configure(self.rig.checker.load_settings, self.rig.checker.save_settings)
        c.spawn, c.times, c.clock, c.free_gb = self.rig.checker.spawn, lambda h: None, self.rig.checker.clock, lambda: 8.0
        c.tier, c._running = "normal", False

    def test_get_status(self):
        status, body, _ = helpers.api("GET", "/api/laptop-check")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"running": False, "tier": "normal", "record": None})

    def test_post_needs_tracker_header(self):
        status, _, _ = helpers.api("POST", "/api/laptop-check", {}, tracker=False)
        self.assertEqual(status, 403)
        self.assertEqual(self.rig.procs, [])

    def test_post_starts_then_status_has_record(self):
        status, body, _ = helpers.api("POST", "/api/laptop-check", {})
        self.assertEqual((status, body), (200, {"started": True}))
        join_check()
        self.assertEqual(len(self.rig.procs), 1)
        _, body, _ = helpers.api("GET", "/api/laptop-check")
        self.assertFalse(body["running"])
        self.assertEqual(body["record"]["tier"], "normal")

    def test_post_false_when_running_or_not_configured(self):
        speedcheck.CHECK._running = True
        self.assertEqual(helpers.api("POST", "/api/laptop-check", {})[1], {"started": False})
        speedcheck.CHECK._running = False
        speedcheck.CHECK.configure(None, None)
        self.assertEqual(helpers.api("POST", "/api/laptop-check", {})[1], {"started": False})

    def test_settings_route_ignores_laptop_check(self):
        helpers.api("PUT", "/api/settings", {"laptop_check": "x"})
        self.assertNotIn("laptop_check", server._all_settings())
        self.assertNotIn(speedcheck.SETTING_KEY, helpers.api("GET", "/api/settings")[1])


if __name__ == "__main__":
    unittest.main()
