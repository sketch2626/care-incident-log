"""Care Incident Log desktop app: runs the local server and shows it in its own window.

Run:  python desktop.py          (the packaged "Care Incident Log.exe" starts here)
      python desktop.py --mary   (Mary's full-screen window; the display stays on while plugged in)

If the built-in window can't open (no WebView2 on this PC), the log opens in the
default web browser instead and keeps running until the computer restarts. In that
browser fallback Mary has no KeepAwake (we can't tell when a browser tab closes);
the page's own Wake Lock covers it.
"""
import os
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer

import power
import server

AUTOPLAY_ARG = "--autoplay-policy=no-user-gesture-required"
# The env var replaces pywebview's own browser arguments, so repeat the one it sets.
PYWEBVIEW_ARG = "--disable-features=ElasticOverscroll"


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


def window_options(mary):
    """Title, page path and create_window arguments. No GUI needed."""
    if mary:
        return {"title": "Mary", "path": "/mary.html", "kwargs": {"fullscreen": True}}
    return {"title": server.PAGE_TITLE, "path": "",
            "kwargs": {"width": 1280, "height": 860, "min_size": (720, 540), "maximized": True}}


class MaryApi:
    """Offered to Mary's page as window.pywebview.api (the page shows Close when it exists)."""

    def __init__(self):
        self._window = None  # leading underscore: pywebview exposes public attributes to the page

    def close_window(self):
        if self._window is not None:
            self._window.destroy()


def open_window(url, mary=False):
    """Show the app in its own window until it is closed. False if no window is possible."""
    keep_awake = power.KeepAwake() if mary else None
    try:
        import webview
        from webview.platforms import winforms
        if winforms.renderer != "edgechromium":
            return False  # pywebview would fall back to Internet Explorer, which can't run the page
        webview.settings["ALLOW_DOWNLOADS"] = True  # "Download spreadsheet" shows a Save dialog
        opts = window_options(mary)
        start_args = {"gui": "edgechromium"}
        api = None
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
        if api is not None:
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
    mary = "--mary" in sys.argv
    url = start_server()
    if not open_window(url, mary):
        webbrowser.open(url + (window_options(mary)["path"]))
        threading.Event().wait()  # keep serving the browser tab


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_error("The app stopped with an error.")
        raise
