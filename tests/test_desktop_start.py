from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""Desktop start-up safety net: the startup watch that leaves a line in desktop.log, bring_up (shows a window
Windows started hidden), and open_window / main wiring. No real window, no real Windows calls, no pywebview."""
import os
import sys
import time
import types
import unittest
from pathlib import Path
from unittest import mock

import desktop
import server


def read_log():
    path = server.DATA / "desktop.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


class LogCase(unittest.TestCase):
    """desktop.log starts empty and is removed afterwards; any startup watch left open is closed first."""

    def setUp(self):
        self.startups = []
        server.DATA.mkdir(parents=True, exist_ok=True)  # log_note stays silent when the folder is missing
        self._clear_log()

    def tearDown(self):
        for s in self.startups:
            if s._dump:
                s._dump.close()
                s._dump = None
        self._clear_log()

    @staticmethod
    def _clear_log():
        try:
            (server.DATA / "desktop.log").unlink()
        except FileNotFoundError:
            pass


class FakeWindowUser32:
    """Stands in for ctypes.windll.user32: remembers calls; can turn visible when ShowWindow is called."""

    def __init__(self, visible, shows_on_show=False):
        self.visible, self.shows_on_show = visible, shows_on_show
        self.calls = []

    def IsWindowVisible(self, hwnd):
        self.calls.append(("IsWindowVisible", hwnd))
        return 1 if self.visible else 0

    def ShowWindow(self, hwnd, cmd):
        self.calls.append(("ShowWindow", hwnd, cmd))
        if self.shows_on_show:
            self.visible = True
        return 1

    def SetForegroundWindow(self, hwnd):
        self.calls.append(("SetForegroundWindow", hwnd))
        return 1


def fake_window(handle=4242):
    window = mock.Mock()
    window.native.Handle.ToInt64.return_value = handle
    return window


class BringUpTests(LogCase):
    def test_already_visible_is_left_alone(self):
        user32 = FakeWindowUser32(visible=True)
        self.assertTrue(desktop.bring_up(fake_window(), user32))
        names = [c[0] for c in user32.calls]
        self.assertNotIn("ShowWindow", names)
        self.assertNotIn("SetForegroundWindow", names)
        self.assertEqual(read_log(), "")

    def test_hidden_window_is_shown_maximized_and_brought_forward(self):
        user32 = FakeWindowUser32(visible=False, shows_on_show=True)
        self.assertTrue(desktop.bring_up(fake_window(4242), user32))
        self.assertIn(("ShowWindow", 4242, 3), user32.calls)
        self.assertIn(("SetForegroundWindow", 4242), user32.calls)
        self.assertIn("started the window hidden", read_log())

    def test_window_that_stays_hidden_is_reported(self):
        user32 = FakeWindowUser32(visible=False, shows_on_show=False)
        self.assertFalse(desktop.bring_up(fake_window(4242), user32))
        self.assertIn(("ShowWindow", 4242, 3), user32.calls)
        self.assertIn(("SetForegroundWindow", 4242), user32.calls)

    def test_window_with_no_native_handle_is_false_and_logged(self):
        window = mock.Mock(native=None)
        self.assertFalse(desktop.bring_up(window, FakeWindowUser32(visible=True)))
        self.assertIn("couldn't be checked", read_log())


class StartupTests(LogCase):
    def test_done_twice_logs_one_line(self):
        startup = desktop.Startup("voices")
        startup.done("window and page showing")
        startup.done("window and page showing")
        self.assertTrue(startup.ready.is_set())
        self.assertEqual(read_log().count("Started (voices): window and page showing after"), 1)

    def test_watch_logs_where_it_stuck_then_done_cancels_the_dump(self):
        with mock.patch.object(desktop.faulthandler, "dump_traceback_later") as dump, \
                mock.patch.object(desktop.faulthandler, "cancel_dump_traceback_later") as cancel:
            startup = desktop.Startup("voices", wait=0.05)
            self.startups.append(startup)
            startup.watch()
            dump.assert_called_once()
            self.assertAlmostEqual(dump.call_args.args[0], 1.05)
            self.assertIsNotNone(dump.call_args.kwargs.get("file"))
            startup.at("creating the window")
            deadline = time.monotonic() + 2
            while not cancel.called and time.monotonic() < deadline:
                time.sleep(0.02)
            log = read_log()
            self.assertIn("Startup stuck (voices)", log)
            self.assertIn("Last step: creating the window", log)
            self.assertIn("Thread startup-watch:", log)  # every thread's stack is written
            cancel.assert_called_once()  # so the faulthandler backup isn't needed
            self.assertFalse(startup.ready.is_set())  # no page address yet, so no browser
            startup.done("window and page showing")
            self.assertEqual(cancel.call_count, 2)
            self.assertIsNone(startup._dump)

    def test_stuck_start_opens_the_page_in_the_browser(self):
        with mock.patch.object(desktop.faulthandler, "dump_traceback_later"), \
                mock.patch.object(desktop.faulthandler, "cancel_dump_traceback_later"), \
                mock.patch.object(desktop.webbrowser, "open", return_value=True) as browser:
            startup = desktop.Startup("voices", wait=0.05)
            self.startups.append(startup)
            startup.page = "http://127.0.0.1:1/mary/voices.html"
            startup.watch()
            self.assertTrue(startup.ready.wait(2))
        browser.assert_called_once_with("http://127.0.0.1:1/mary/voices.html")
        log = read_log()
        self.assertIn("Startup stuck (voices)", log)
        self.assertIn("Started (voices): opened in the web browser after", log)

    def test_browser_that_wont_open_is_logged_and_tried_once(self):
        startup = desktop.Startup("voices")
        startup.page = "http://127.0.0.1:1/mary/voices.html"
        with mock.patch.object(desktop.webbrowser, "open", return_value=False) as browser:
            self.assertFalse(startup.open_browser())
            self.assertFalse(startup.open_browser())
        browser.assert_called_once()
        self.assertFalse(startup.ready.is_set())
        self.assertEqual(startup.step, "the web browser didn't open")
        self.assertIn("The web browser didn't open (voices).", read_log())

    def test_watch_stays_quiet_when_the_start_finishes_in_time(self):
        with mock.patch.object(desktop.faulthandler, "dump_traceback_later"), \
                mock.patch.object(desktop.faulthandler, "cancel_dump_traceback_later"):
            startup = desktop.Startup("voices", wait=0.3)
            self.startups.append(startup)
            startup.watch()
            startup.done("window and page showing")
            time.sleep(0.5)
        log = read_log()
        self.assertNotIn("Startup stuck", log)
        self.assertEqual(log.count("Started (voices)"), 1)


class FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class FakeEvents:
    def __init__(self):
        self.shown, self.loaded = FakeEvent(), FakeEvent()


class FakeWindow:
    def __init__(self):
        self.events = FakeEvents()
        self.native = None


class FakeWebview:
    """A stand-in for the pywebview package: records create_window and start, and fires shown then loaded."""

    def __init__(self, renderer="edgechromium", create_error=None):
        self.created, self.started = [], []
        self.window = FakeWindow()
        self.create_error = create_error

        class EdgeChrome:
            def on_webview_ready(self, sender, args):
                pass

        self.EdgeChrome = EdgeChrome
        webview = types.ModuleType("webview")
        webview.__path__ = []
        webview.settings = {}
        webview.create_window = self.create_window
        webview.start = self.start
        platforms = types.ModuleType("webview.platforms")
        platforms.__path__ = []
        winforms = types.ModuleType("webview.platforms.winforms")
        winforms.renderer = renderer
        edge = types.ModuleType("webview.platforms.edgechromium")
        edge.EdgeChrome = EdgeChrome
        webview.platforms = platforms
        platforms.winforms = winforms
        platforms.edgechromium = edge
        self.webview = webview
        self.modules = {"webview": webview, "webview.platforms": platforms,
                        "webview.platforms.winforms": winforms, "webview.platforms.edgechromium": edge}

    def create_window(self, title, url, js_api=None, **kwargs):
        if self.create_error:
            raise self.create_error
        self.created.append({"title": title, "url": url, "js_api": js_api, "kwargs": kwargs})
        return self.window

    def start(self, **kw):
        self.started.append(kw)
        for handler in list(self.window.events.shown.handlers):
            handler()
        for handler in list(self.window.events.loaded.handlers):
            handler()


class OpenWindowTests(LogCase):
    URL = "http://127.0.0.1:1"

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
        keep_awake = mock.patch.object(desktop.power, "KeepAwake")
        self.keep_awake_cls = keep_awake.start()
        self.addCleanup(keep_awake.stop)

    def fake(self, **kw):
        fake = FakeWebview(**kw)
        modules = mock.patch.dict(sys.modules, fake.modules)
        modules.start()
        self.addCleanup(modules.stop)
        return fake

    def open_voices(self, fake, window_showing):
        startup = desktop.Startup("voices", wait=5)
        with mock.patch.object(desktop, "bring_up", return_value=window_showing):
            result = desktop.open_window(self.URL, mary=True, voices=True, startup=startup)
        return result, startup

    def test_voices_window_is_full_screen_and_ready_once_it_shows(self):
        fake = self.fake()
        result, startup = self.open_voices(fake, True)
        self.assertTrue(result)
        self.assertEqual(len(fake.created), 1)
        made = fake.created[0]
        self.assertEqual(made["title"], "Mary voices")
        self.assertTrue(made["url"].endswith("/mary/voices.html"))
        self.assertTrue(made["url"].startswith(self.URL))
        self.assertIs(made["kwargs"].get("fullscreen"), True)
        self.assertIsInstance(made["js_api"], desktop.MaryApi)
        self.assertIs(made["js_api"]._window, fake.window)
        self.assertEqual(len(fake.started), 1)
        kw = fake.started[0]
        self.assertEqual(kw["gui"], "edgechromium")
        self.assertIs(kw["private_mode"], False)
        self.assertEqual(Path(kw["storage_path"]).name, "webview")
        self.assertEqual(Path(kw["storage_path"]).parent, server.DATA)
        args = os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"]
        self.assertIn("--autoplay-policy=no-user-gesture-required", args)
        self.assertIn(desktop.PYWEBVIEW_ARG, args)
        self.assertTrue(startup.ready.is_set())
        self.assertIn("Started (voices): window and page showing", read_log())
        self.assertIs(fake.webview.settings["ALLOW_DOWNLOADS"], True)
        self.assertTrue(getattr(fake.EdgeChrome.on_webview_ready, "_edit_menu", False))
        keep_awake = self.keep_awake_cls.return_value
        keep_awake.start.assert_called_once()
        keep_awake.stop.assert_called_once()

    def test_page_loaded_but_window_not_showing_is_not_ready(self):
        fake = self.fake()
        result, startup = self.open_voices(fake, False)
        self.assertTrue(result)
        self.assertFalse(startup.ready.is_set())
        self.assertEqual(startup.step, "page loaded, but the window isn't showing")
        self.assertNotIn("Started (voices)", read_log())

    def test_old_browser_engine_means_no_window(self):
        fake = self.fake(renderer="mshtml")
        result, startup = self.open_voices(fake, True)
        self.assertFalse(result)
        self.assertEqual(fake.created, [])
        self.assertEqual(fake.started, [])
        self.assertFalse(startup.ready.is_set())
        self.assertIn("No WebView2 window (pywebview found 'mshtml')", read_log())

    def test_window_that_cant_be_created_is_logged_and_false(self):
        fake = self.fake(create_error=RuntimeError("boom"))
        result, startup = self.open_voices(fake, True)
        self.assertFalse(result)
        self.assertEqual(fake.started, [])
        log = read_log()
        self.assertIn("couldn't open", log)
        self.assertIn("boom", log)
        self.assertFalse(startup.ready.is_set())
        self.keep_awake_cls.return_value.stop.assert_called_once()


class MainTests(LogCase):
    def test_voices_flag_opens_the_voices_window_with_a_voices_startup(self):
        with mock.patch.object(sys, "argv", ["desktop.py", "--voices"]), \
                mock.patch.object(desktop, "start_server", return_value="http://127.0.0.1:1"), \
                mock.patch.object(desktop, "open_window", return_value=True) as open_window, \
                mock.patch.object(desktop.Startup, "watch") as watch:
            desktop.main()
        open_window.assert_called_once()
        args = open_window.call_args.args
        self.assertEqual(args[:3], ("http://127.0.0.1:1", True, True))
        self.assertIsInstance(args[3], desktop.Startup)
        self.assertEqual(args[3].mode, "voices")
        self.assertEqual(args[3].page, "http://127.0.0.1:1/mary/voices.html")
        watch.assert_called_once()

    def test_no_window_falls_back_to_the_browser(self):
        with mock.patch.object(sys, "argv", ["desktop.py", "--voices"]), \
                mock.patch.object(desktop, "start_server", return_value="http://127.0.0.1:1"), \
                mock.patch.object(desktop, "open_window", return_value=False), \
                mock.patch.object(desktop.Startup, "watch"), \
                mock.patch.object(desktop.Startup, "open_browser") as browser, \
                mock.patch.object(desktop.threading, "Event"):  # main waits forever on one
            desktop.main()
        browser.assert_called_once()


if __name__ == "__main__":
    unittest.main()
