from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""Keep-awake rule: plugged in or unknown keeps the display on; battery lets Windows time out."""
import threading
import unittest

import desktop
import power
import server

api = helpers.api
ON = power.ES_CONTINUOUS | power.ES_DISPLAY_REQUIRED | power.ES_SYSTEM_REQUIRED
OFF = power.ES_CONTINUOUS


class Recorder:
    """Fake set_state: records (flags, thread id) and signals each call."""

    def __init__(self):
        self.calls = []
        self.event = threading.Event()

    def __call__(self, flags):
        self.calls.append((flags, threading.get_ident()))
        self.event.set()

    def wait_for(self, n, timeout=2):
        """Wait until at least n calls were recorded."""
        end = threading.Event()
        for _ in range(int(timeout / 0.005)):
            if len(self.calls) >= n:
                return True
            end.wait(0.005)
        return len(self.calls) >= n


class PowerStateTests(unittest.TestCase):
    def test_plugged_in_returns_known_value(self):
        self.assertIn(power.plugged_in(), (True, False, None))

    def test_keep_display_on_rule(self):
        self.assertIs(power.keep_display_on(True), True)
        self.assertIs(power.keep_display_on(None), True)
        self.assertIs(power.keep_display_on(False), False)


class KeepAwakeTests(unittest.TestCase):
    def test_plugged_holds_then_battery_releases_then_stop_releases(self):
        state = {"plugged": True}
        rec = Recorder()
        ka = power.KeepAwake(interval=0.005, plugged=lambda: state["plugged"], set_state=rec)
        ka.start()
        self.assertTrue(rec.wait_for(1))
        self.assertEqual(rec.calls[0][0], ON)
        state["plugged"] = False
        self.assertTrue(rec.wait_for(2))
        self.assertEqual(rec.calls[1][0], OFF)
        ka.stop()
        self.assertEqual(rec.calls[-1][0], OFF)
        threads = {tid for _, tid in rec.calls}
        self.assertEqual(len(threads), 1)
        self.assertNotIn(threading.get_ident(), threads)
        self.assertFalse(ka._thread.is_alive())

    def test_only_calls_when_state_changes(self):
        rec = Recorder()
        ka = power.KeepAwake(interval=0.002, plugged=lambda: True, set_state=rec)
        ka.start()
        self.assertTrue(rec.wait_for(1))
        threading.Event().wait(0.03)  # many loop passes, no change
        ka.stop()
        self.assertEqual([f for f, _ in rec.calls], [ON, OFF])  # hold once, release on stop

    def test_stop_twice_and_without_start(self):
        power.KeepAwake(set_state=Recorder()).stop()
        rec = Recorder()
        ka = power.KeepAwake(interval=0.005, plugged=lambda: True, set_state=rec).start()
        ka.stop()
        ka.stop()
        self.assertEqual(rec.calls[-1][0], OFF)

    def test_context_manager_releases(self):
        rec = Recorder()
        with power.KeepAwake(interval=0.005, plugged=lambda: True, set_state=rec) as ka:
            self.assertTrue(rec.wait_for(1))
            self.assertEqual(rec.calls[0][0], ON)
        self.assertEqual(rec.calls[-1][0], OFF)
        self.assertFalse(ka._thread.is_alive())

    def test_unknown_power_keeps_display_on_and_loop_survives(self):
        def boom():
            raise RuntimeError("no power info")
        rec = Recorder()
        ka = power.KeepAwake(interval=0.005, plugged=boom, set_state=rec)
        ka.start()
        self.assertTrue(rec.wait_for(1))
        self.assertEqual(rec.calls[0][0], ON)
        self.assertTrue(ka._thread.is_alive())
        ka.stop()
        self.assertEqual(rec.calls[-1][0], OFF)

    def test_set_state_error_does_not_kill_loop(self):
        seen = []

        def flaky(flags):
            seen.append(flags)
            raise OSError("boom")
        state = {"plugged": True}
        ka = power.KeepAwake(interval=0.005, plugged=lambda: state["plugged"], set_state=flaky)
        ka.start()
        end = threading.Event()
        for _ in range(400):
            if seen:
                break
            end.wait(0.005)
        state["plugged"] = False
        for _ in range(400):
            if len(seen) >= 2:
                break
            end.wait(0.005)
        self.assertTrue(ka._thread.is_alive())
        ka.stop()
        self.assertEqual(seen[:2], [ON, OFF])


class PowerRouteTests(unittest.TestCase):
    def test_api_power(self):
        status, body, _ = api("GET", "/api/power")
        self.assertEqual(status, 200)
        self.assertIsInstance(body, dict)
        self.assertIn("plugged_in", body)
        self.assertIn(body["plugged_in"], (True, False, None))


class WindowOptionsTests(unittest.TestCase):
    def test_mary_is_full_screen(self):
        opts = desktop.window_options(True)
        self.assertEqual(opts["title"], "Mary")
        self.assertEqual(opts["path"], "/mary.html")
        self.assertIs(opts["kwargs"]["fullscreen"], True)

    def test_normal_window_is_unchanged(self):
        opts = desktop.window_options(False)
        self.assertEqual(opts["title"], server.PAGE_TITLE)
        self.assertEqual(opts["path"], "")
        self.assertNotIn("fullscreen", opts["kwargs"])
        self.assertTrue(opts["kwargs"]["maximized"])

    def test_window_trouble_is_written_to_desktop_log(self):
        path = server.DATA / "desktop.log"
        path.unlink(missing_ok=True)
        try:
            raise RuntimeError("no WebView2 here")
        except RuntimeError:
            desktop.log_error("window failed")
        text = path.read_text(encoding="utf-8")
        self.assertIn("window failed", text)
        self.assertIn("no WebView2 here", text)
        path.unlink()


if __name__ == "__main__":
    unittest.main()
