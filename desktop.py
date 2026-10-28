"""Care Incident Log desktop app: runs the local server and shows it in its own window.

Run:  python desktop.py          (the packaged "Care Incident Log.exe" starts here)
      python desktop.py --mary   (Mary's full-screen window; the display stays on while plugged in)
      python desktop.py --voices (the voice audition page, full screen, set up exactly like --mary)

If the built-in window can't open (no WebView2 on this PC), the log opens in the
default web browser instead and keeps running until the computer restarts. In that
browser fallback Mary has no KeepAwake (we can't tell when a browser tab closes);
the page's own Wake Lock covers it.
"""
import ctypes
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

AUTOPLAY_ARG = "--autoplay-policy=no-user-gesture-required"
# The env var replaces pywebview's own browser arguments, so repeat the one it sets.
PYWEBVIEW_ARG = "--disable-features=ElasticOverscroll"
CF_UNICODETEXT = 13  # Windows clipboard format for text
# Right-click menu: only these editing items stay (no Back, Reload, Save as, Inspect...).
EDIT_MENU_ITEMS = {"undo", "redo", "cut", "copy", "paste", "pasteAndMatchStyle", "selectAll"}


def start_server():
    """Serve on the usual port; if something else holds it, pick any free port."""
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", server.PORT), server.Handler)
    except OSError:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    server.init_db()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_port}"


def log_error(what):
    """pythonw has no console, so note what went wrong in the data folder (desktop.log) for a helper to read."""
    try:
        path = server.DATA / "desktop.log"
        if path.exists() and path.stat().st_size > 200_000:
            path.unlink()  # keep it small; only recent trouble matters
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n{datetime.now():%Y-%m-%d %H:%M:%S}  {what}\n{traceback.format_exc()}")
    except Exception:
        pass


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


def open_window(url, mary=False, voices=False):
    """Show the app in its own window until it is closed. False if no window is possible."""
    keep_awake = power.KeepAwake() if mary else None
    try:
        import webview
        from webview.platforms import winforms
        if winforms.renderer != "edgechromium":
            return False  # pywebview would fall back to Internet Explorer, which can't run the page
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
        window = webview.create_window(opts["title"], url + opts["path"], js_api=api, **opts["kwargs"])
        if mary:
            api._window = window
        if keep_awake:
            keep_awake.start()
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
    url = start_server()
    if not open_window(url, mary, voices):
        webbrowser.open(url + (window_options(mary, voices)["path"]))
        threading.Event().wait()  # keep serving the browser tab


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_error("The app stopped with an error.")
        raise
