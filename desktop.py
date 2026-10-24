"""Care Incident Log desktop app: runs the local server and shows it in its own window.

Run:  python desktop.py   (the packaged "Care Incident Log.exe" starts here)

If the built-in window can't open (no WebView2 on this PC), the log opens in the
default web browser instead and keeps running until the computer restarts.
"""
import threading
import webbrowser
from http.server import ThreadingHTTPServer

import server


def start_server():
    """Serve on the usual port; if something else holds it, pick any free port."""
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", server.PORT), server.Handler)
    except OSError:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    server.init_db()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_port}"


def open_window(url):
    """Show the app in its own window until it is closed. False if no window is possible."""
    try:
        import webview
        from webview.platforms import winforms
        if winforms.renderer != "edgechromium":
            return False  # pywebview would fall back to Internet Explorer, which can't run the page
        webview.settings["ALLOW_DOWNLOADS"] = True  # "Download spreadsheet" shows a Save dialog
        webview.create_window(server.PAGE_TITLE, url, width=1280, height=860,
                              min_size=(720, 540), maximized=True)
        webview.start(gui="edgechromium")
        return True
    except Exception:
        return False


def main():
    url = start_server()
    if not open_window(url):
        webbrowser.open(url)
        threading.Event().wait()  # keep serving the browser tab


if __name__ == "__main__":
    main()
