"""Care Incident Log desktop app: runs the local server and shows it in its own window.

Run:  python desktop.py          (the packaged "Care Incident Log.exe" starts here)
      python desktop.py --mary   (Mary's full-screen window; the display stays on while plugged in)
      python desktop.py --voices (the voice audition page, full screen, set up exactly like --mary)

If the built-in window can't open (no WebView2 on this PC), the log opens in the
default web browser instead and keeps running until the computer restarts. In that
browser fallback Mary has no KeepAwake (we can't tell when a browser tab closes);
the page's own Wake Lock covers it.
"""
import sys  # M8

if "--laptop-check" in sys.argv:  # M8: the speed check's child; it must stop before `import server` below
    import speedcheck
    speedcheck.child_main(sys.argv[sys.argv.index("--laptop-check") + 1])
    sys.exit(0)

import ctypes
import faulthandler
import os
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer

import power
import server
import speedcheck  # M8

AUTOPLAY_ARG = "--autoplay-policy=no-user-gesture-required"
# The env var replaces pywebview's own browser arguments, so repeat the one it sets.
PYWEBVIEW_ARG = "--disable-features=ElasticOverscroll"
CF_UNICODETEXT = 13  # Windows clipboard format for text
# Right-click menu: only these editing items stay (no Back, Reload, Save as, Inspect...).
EDIT_MENU_ITEMS = {"undo", "redo", "cut", "copy", "paste", "pasteAndMatchStyle", "selectAll"}
STARTUP_WAIT_S = 30  # the window and page are up long before this; if not, desktop.log says where it stuck
SW_SHOWMAXIMIZED = 3


def start_server():
    """Serve on the usual port; if something else holds it, pick any free port."""
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", server.PORT), server.Handler)
    except OSError:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    server.init_db()
    server.close_talk()  # M15a: this path never runs server.main()
    server.laptop_check_setup()  # M8
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_port}"


def log_note(what, detail=""):
    """pythonw has no console, so note what happened in the data folder (desktop.log) for a helper to read."""
    path = server.DATA / "desktop.log"
    try:
        if path.exists() and path.stat().st_size > 200_000:
            path.unlink()  # keep it small; only recent trouble matters
    except OSError:
        pass  # the startup watch holds it open; trim it next time
    try:
        detail = server.memory_core.scrub_addresses(str(detail))  # M18
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n{datetime.now():%Y-%m-%d %H:%M:%S}  {what}\n{detail}")
    except Exception:
        pass


def log_error(what):
    log_note(what, traceback.format_exc())


def start_laptop_check():  # M8
    """Called once something is on screen; it can't affect the window."""
    try:
        speedcheck.CHECK.start_after_window()
    except Exception:
        log_error("The laptop speed check couldn't start.")


def thread_stacks():
    """Where every thread is, for desktop.log (code lines only, no values)."""
    names = {t.ident: t.name for t in threading.enumerate()}
    return "".join(f"Thread {names.get(ident, ident)}:\n" + "".join(traceback.format_stack(frame))
                   for ident, frame in sys._current_frames().items())


class Startup:
    """Watches the start, so a start that hangs is never silent. If the window and page aren't showing
    after `wait` seconds, desktop.log gets the last step reached and every thread's stack, and the page
    opens in the web browser so something is on screen. If Python itself is stuck, faulthandler writes
    the stacks a second later instead. A good start leaves one line."""

    def __init__(self, mode, wait=STARTUP_WAIT_S):
        self.mode, self.wait = mode, wait
        self.step = "starting"
        self.page = None  # the page's address, once the server is up
        self.began = time.monotonic()
        self.ready = threading.Event()
        self._dump = None  # desktop.log, held open for faulthandler
        self._browser_tried = False
        self._lock = threading.Lock()

    def at(self, step):
        self.step = step

    def watch(self):
        try:
            server.DATA.mkdir(parents=True, exist_ok=True)
            self._dump = (server.DATA / "desktop.log").open("a", encoding="utf-8")
            faulthandler.dump_traceback_later(self.wait + 1, file=self._dump)
        except Exception:
            self._dump = None
        threading.Thread(target=self._watch, name="startup-watch", daemon=True).start()

    def _watch(self):
        if self.ready.wait(self.wait):
            return
        log_note(f"Startup stuck ({self.mode}): nothing showing after {self.wait} s. Last step: {self.step}.",
                 thread_stacks())
        faulthandler.cancel_dump_traceback_later()  # the stacks are written; it was only the backup
        if self.page:
            self.open_browser()

    def open_browser(self):
        """Show the page in the web browser instead (once). False if that didn't open either."""
        if self._browser_tried:
            return self.ready.is_set()
        self._browser_tried = True
        self.at("opening the web browser")
        try:
            opened = webbrowser.open(self.page)
        except Exception:
            log_error("The web browser couldn't be opened.")
            opened = False
        if opened:
            self.done("opened in the web browser")
        else:
            self.at("the web browser didn't open")
            log_note(f"The web browser didn't open ({self.mode}).")
        return opened

    def done(self, how):
        with self._lock:
            if self.ready.is_set():
                return
            if self._dump:
                faulthandler.cancel_dump_traceback_later()
                self._dump.close()
                self._dump = None
            log_note(f"Started ({self.mode}): {how} after {time.monotonic() - self.began:.1f} s.")
            self.ready.set()


def bring_up(window, user32=None):
    """True once the window is on screen. If the launcher asked Windows for a hidden start (for example
    PowerShell's Start-Process -WindowStyle Hidden), Windows applies that to the window's first show and it
    stays invisible while the app runs. Show it maximized ourselves when that happens."""
    try:
        user32 = user32 or ctypes.windll.user32
        hwnd = window.native.Handle.ToInt64()
        if not user32.IsWindowVisible(hwnd):
            log_note("Windows started the window hidden; showing it.")
            user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
            user32.SetForegroundWindow(hwnd)
        return bool(user32.IsWindowVisible(hwnd))
    except Exception:
        log_error("The window couldn't be checked or shown.")
        return False


def window_options(mary, voices=False):
    """Title, page path and create_window arguments. No GUI needed."""
    if voices:
        return {"title": "Mary voices", "path": "/mary/voices.html", "kwargs": {"fullscreen": True}}
    if mary:
        return {"title": "Mary", "path": "/mary.html", "kwargs": {"fullscreen": True}}
    return {"title": server.PAGE_TITLE, "path": "",
            "kwargs": {"width": 1280, "height": 860, "min_size": (720, 540), "maximized": True}}


def read_clipboard_text(user32=None, kernel32=None, tries=5):
    """Text on the Windows clipboard, trimmed; "" if there is none or it can't be read.
    The text is never logged or stored."""
    if (user32 is None or kernel32 is None) and sys.platform != "win32":
        return ""
    try:
        if user32 is None:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.OpenClipboard.argtypes = [ctypes.c_void_p]
            user32.GetClipboardData.restype = ctypes.c_void_p
            user32.GetClipboardData.argtypes = [ctypes.c_uint]
            user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
        if kernel32 is None:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        opened = False
        for attempt in range(max(1, tries)):
            if user32.OpenClipboard(None):
                opened = True
                break
            if attempt < tries - 1:
                time.sleep(0.05)  # another app may hold the clipboard for a moment
        if not opened:
            return ""
        try:
            if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return ""
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                text = ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
        return text.strip()
    except Exception:
        log_error("The clipboard couldn't be read.")  # never include the text
        return ""


class AppApi:
    """Offered to every app window as window.pywebview.api."""

    def paste_text(self):
        """The text on the clipboard, so a big on-screen Paste button works with no key combos."""
        return read_clipboard_text()


class MaryApi(AppApi):
    """Offered to Mary's page as window.pywebview.api (the page shows Close when close_window exists)."""

    def __init__(self):
        self._window = None  # leading underscore: pywebview exposes public attributes to the page

    def close_window(self):
        if self._window is not None:
            self._window.destroy()


def keep_edit_items(sender, args):
    """ContextMenuRequested handler: keep only the editing items; show no menu if none are left."""
    try:
        items = args.MenuItems
        for i in range(items.Count - 1, -1, -1):
            if items[i].Name not in EDIT_MENU_ITEMS:
                items.RemoveAt(i)
        if items.Count == 0:
            args.Handled = True
    except Exception:
        log_error("The right-click menu couldn't be trimmed.")


def allow_edit_menu(edge_cls):
    """pywebview ties the right-click menu to debug mode (which also opens devtools).
    Turn the menu on after pywebview's setup and trim it to editing items (Paste for a key, etc.)."""
    original = edge_cls.on_webview_ready
    if getattr(original, "_edit_menu", False):
        return

    def on_webview_ready(self, sender, args):
        original(self, sender, args)
        try:
            core = sender.CoreWebView2
            if core is not None:
                core.Settings.AreDefaultContextMenusEnabled = True
                core.ContextMenuRequested += keep_edit_items
        except Exception:
            log_error("The right-click menu couldn't be turned on.")

    on_webview_ready._edit_menu = True
    edge_cls.on_webview_ready = on_webview_ready


def open_window(url, mary=False, voices=False, startup=None):
    """Show the app in its own window until it is closed. False if no window is possible."""
    startup = startup or Startup("voices" if voices else "mary" if mary else "app")
    keep_awake = power.KeepAwake() if mary else None
    try:
        startup.at("loading the window library")
        import webview
        from webview.platforms import winforms
        if winforms.renderer != "edgechromium":
            # pywebview would fall back to Internet Explorer, which can't run the page
            log_note(f"No WebView2 window (pywebview found {winforms.renderer!r}); using the web browser.")
            return False
        from webview.platforms import edgechromium
        allow_edit_menu(edgechromium.EdgeChrome)
        webview.settings["ALLOW_DOWNLOADS"] = True  # "Download spreadsheet" shows a Save dialog
        opts = window_options(mary, voices)
        start_args = {"gui": "edgechromium"}
        api = AppApi()
        if mary:
            current = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
            extra = [a for a in (PYWEBVIEW_ARG, AUTOPLAY_ARG) if a not in current]
            if extra:
                os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = " ".join([current] + extra).strip()
            api = MaryApi()
            storage = server.DATA / "webview"
            storage.mkdir(parents=True, exist_ok=True)
            start_args.update(private_mode=False, storage_path=str(storage))
        startup.at("creating the window")
        window = webview.create_window(opts["title"], url + opts["path"], js_api=api, **opts["kwargs"])
        if mary:
            api._window = window

        def shown():
            startup.at("window shown, page loading")
            bring_up(window)

        def loaded():
            if bring_up(window):
                startup.done("window and page showing")
            else:
                startup.at("page loaded, but the window isn't showing")
            start_laptop_check()  # M8

        window.events.shown += shown
        window.events.loaded += loaded
        if keep_awake:
            keep_awake.start()
        startup.at("starting the window")
        webview.start(**start_args)
        return True
    except Exception:
        log_error("The app window couldn't open; using the web browser instead.")
        return False
    finally:
        if keep_awake:
            keep_awake.stop()


def main():
    voices = "--voices" in sys.argv
    mary = "--mary" in sys.argv or voices
    startup = Startup("voices" if voices else "mary" if mary else "app")
    startup.watch()
    startup.at("starting the server")
    url = start_server()
    startup.page = url + window_options(mary, voices)["path"]
    if not open_window(url, mary, voices, startup):
        startup.open_browser()
        start_laptop_check()  # M8
        threading.Event().wait()  # keep serving the browser tab  # keep serving the browser tab


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_error("The app stopped with an error.")
        raise
