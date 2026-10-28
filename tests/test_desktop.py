from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""Desktop window helpers: clipboard Paste for the on-screen button, and the trimmed right-click menu.
No window, no real clipboard, no pywebview."""
import ctypes
import unittest
from unittest import mock

import desktop


class FakeUser32:
    def __init__(self, open_ok=True, available=True, handle=1234):
        self.open_ok, self.available, self.handle = open_ok, available, handle
        self.open_calls = 0
        self.close_calls = 0

    def OpenClipboard(self, owner):
        self.open_calls += 1
        return 1 if self.open_ok else 0

    def IsClipboardFormatAvailable(self, fmt):
        return 1 if self.available and fmt == desktop.CF_UNICODETEXT else 0

    def GetClipboardData(self, fmt):
        return self.handle

    def CloseClipboard(self):
        self.close_calls += 1
        return 1


class FakeKernel32:
    def __init__(self, ptr):
        self.ptr = ptr
        self.lock_calls = 0
        self.unlock_calls = 0

    def GlobalLock(self, handle):
        self.lock_calls += 1
        return self.ptr

    def GlobalUnlock(self, handle):
        self.unlock_calls += 1
        return 1


class ClipboardTests(unittest.TestCase):
    def test_reads_and_trims_text(self):
        buf = ctypes.create_unicode_buffer("  AIzaFAKE123 \r\n")
        user32, kernel32 = FakeUser32(), FakeKernel32(ctypes.addressof(buf))
        self.assertEqual(desktop.read_clipboard_text(user32, kernel32), "AIzaFAKE123")
        self.assertEqual(user32.close_calls, 1)
        self.assertEqual(kernel32.lock_calls, 1)
        self.assertEqual(kernel32.unlock_calls, 1)

    def test_no_text_format_returns_empty_and_still_closes(self):
        user32, kernel32 = FakeUser32(available=False), FakeKernel32(0)
        self.assertEqual(desktop.read_clipboard_text(user32, kernel32), "")
        self.assertEqual(user32.close_calls, 1)
        self.assertEqual(kernel32.lock_calls, 0)

    def test_null_handle_returns_empty_and_still_closes(self):
        user32, kernel32 = FakeUser32(handle=None), FakeKernel32(0)
        self.assertEqual(desktop.read_clipboard_text(user32, kernel32), "")
        self.assertEqual(user32.close_calls, 1)

    def test_null_pointer_returns_empty_and_still_closes(self):
        user32, kernel32 = FakeUser32(), FakeKernel32(None)
        self.assertEqual(desktop.read_clipboard_text(user32, kernel32), "")
        self.assertEqual(user32.close_calls, 1)
        self.assertEqual(kernel32.unlock_calls, 0)

    def test_clipboard_that_never_opens_returns_empty_without_closing(self):
        user32, kernel32 = FakeUser32(open_ok=False), FakeKernel32(0)
        with mock.patch.object(desktop.time, "sleep"):
            self.assertEqual(desktop.read_clipboard_text(user32, kernel32, tries=3), "")
        self.assertEqual(user32.open_calls, 3)
        self.assertEqual(user32.close_calls, 0)


class ApiTests(unittest.TestCase):
    def test_paste_text_returns_the_clipboard_text(self):
        with mock.patch.object(desktop, "read_clipboard_text", return_value="AIzaFAKE123"):
            self.assertEqual(desktop.AppApi().paste_text(), "AIzaFAKE123")

    def test_normal_window_api_has_no_close_window(self):
        self.assertFalse(hasattr(desktop.AppApi(), "close_window"))

    def test_mary_api_has_both(self):
        api = desktop.MaryApi()
        self.assertTrue(callable(api.paste_text))
        self.assertTrue(callable(api.close_window))


class FakeItem:
    def __init__(self, name):
        self.Name = name


class FakeItems(list):
    """Acts like the .NET IList the menu items come in."""

    @property
    def Count(self):
        return len(self)

    def RemoveAt(self, i):
        del self[i]


class FakeMenuArgs:
    def __init__(self, names):
        self.MenuItems = FakeItems(FakeItem(n) for n in names)
        self.Handled = False


class MenuTests(unittest.TestCase):
    def test_keeps_only_editing_items_in_order(self):
        args = FakeMenuArgs(["back", "reload", "cut", "copy", "separator", "paste",
                             "selectAll", "inspectElement", "saveAs"])
        desktop.keep_edit_items(None, args)
        self.assertEqual([i.Name for i in args.MenuItems], ["cut", "copy", "paste", "selectAll"])
        self.assertFalse(args.Handled)

    def test_no_editing_items_means_no_menu(self):
        args = FakeMenuArgs(["back", "reload", "separator", "inspectElement"])
        desktop.keep_edit_items(None, args)
        self.assertEqual(len(args.MenuItems), 0)
        self.assertTrue(args.Handled)


class FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class FakeSettings:
    def __init__(self):
        self.AreDefaultContextMenusEnabled = False
        self.AreDevToolsEnabled = False


class FakeCore:
    def __init__(self):
        self.Settings = FakeSettings()
        self.ContextMenuRequested = FakeEvent()


class FakeSender:
    def __init__(self, core):
        self.CoreWebView2 = core


class AllowEditMenuTests(unittest.TestCase):
    def make_class(self):
        class FakeEdge:
            calls = []

            def on_webview_ready(self, sender, args):
                FakeEdge.calls.append((self, sender, args))

        return FakeEdge

    def test_turns_menu_on_keeps_devtools_off_and_subscribes_once(self):
        edge = self.make_class()
        desktop.allow_edit_menu(edge)
        core = FakeCore()
        sender, args, obj = FakeSender(core), object(), edge()
        obj.on_webview_ready(sender, args)
        self.assertEqual(edge.calls, [(obj, sender, args)])  # the original still ran, same arguments
        self.assertTrue(core.Settings.AreDefaultContextMenusEnabled)
        self.assertFalse(core.Settings.AreDevToolsEnabled)
        self.assertEqual(core.ContextMenuRequested.handlers, [desktop.keep_edit_items])

    def test_wrapping_twice_does_not_double_wrap(self):
        edge = self.make_class()
        desktop.allow_edit_menu(edge)
        first = edge.on_webview_ready
        desktop.allow_edit_menu(edge)
        self.assertIs(edge.on_webview_ready, first)
        core = FakeCore()
        edge().on_webview_ready(FakeSender(core), object())
        self.assertEqual(len(edge.calls), 1)
        self.assertEqual(len(core.ContextMenuRequested.handlers), 1)

    def test_missing_core_does_not_raise(self):
        edge = self.make_class()
        desktop.allow_edit_menu(edge)
        edge().on_webview_ready(FakeSender(None), object())
        self.assertEqual(len(edge.calls), 1)


if __name__ == "__main__":
    unittest.main()
