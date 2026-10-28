from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""Home app page checks (static): the in-page confirm panel, longer error toasts, and no flash of the wrong friend's name."""
import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


class HomePageTests(unittest.TestCase):
    def test_remove_uses_in_page_confirm_not_system_box(self):
        js = read("app.js")
        self.assertIsNone(re.search(r"(?<![\w.])confirm\(", js), "native confirm() is back")
        self.assertIn("askConfirm(", js)
        self.assertIn("Escape", js)

    def test_confirm_box_has_both_buttons_and_big_targets(self):
        html, css = read("index.html"), read("styles.css")
        self.assertIn('id="confirmBox"', html)
        self.assertIn('role="alertdialog"', html)
        self.assertIn('aria-modal="true"', html)
        self.assertIn("Yes, remove it", html)
        self.assertIn("No, keep it", html)
        self.assertIn('id="confirmYes"', html)
        self.assertIn('id="confirmNo"', html)
        card = re.search(r"\.confirmcard \.bigbtn\{([^}]*)\}", css)
        self.assertIsNotNone(card)
        self.assertGreaterEqual(int(re.search(r"min-height:(\d+)px", card.group(1)).group(1)), 64)
        text = re.search(r"\.confirmcard p\{([^}]*)\}", css)
        self.assertIsNotNone(text)
        self.assertGreaterEqual(int(re.search(r"font-size:(\d+)px", text.group(1)).group(1)), 24)

    def test_error_toast_stays_eight_seconds(self):
        js = read("app.js")
        self.assertIn("toastError", js)
        self.assertIn("8000", js)
        self.assertIn("ms = 4000", js)
        self.assertNotRegex(js, r"toast\(err\.message\)")

    def test_failed_delete_and_edit_refresh_the_list(self):
        js = read("app.js")
        self.assertIn("err.status === 404", js)
        self.assertIn("status: res.status", js)
        self.assertIn("go('list', true)", js)

    def test_save_waits_for_detail_box_mic(self):
        js = read("app.js")
        self.assertIn("finishFieldTalk", js)
        # it must run before the form is read
        self.assertLess(js.index("await finishFieldTalk();"), js.index("const text = $('#words').value.trim();"))

    def test_home_does_not_show_mary_before_settings_load(self):
        html, js = read("index.html"), read("app.js")
        self.assertIn('id="maryTo" hidden', html)
        self.assertNotIn("Talk to <span", html)
        self.assertIn("$('#maryTo').hidden = false", js)

    def test_andyflow_switch_hidden_until_installed(self):
        html, js = read("index.html"), read("app.js")
        self.assertIn('<div id="flowInfo" hidden>', html)
        self.assertLess(html.index('id="flowInfo"'), html.index('id="i-andyflow_enabled"'))
        self.assertLess(html.index('id="i-andyflow_enabled"'), html.index('<h2 class="smarth">Smart helper'))
        self.assertIn("$('#flowInfo').hidden = !state.inbox.installed", js)

    def test_andyflow_setting_sent_only_when_installed(self):
        js = read("app.js")
        self.assertIn("installed: !!inbox.installed", js)
        self.assertIn("if (state.inbox.installed) payload.andyflow_enabled", js)


if __name__ == "__main__":
    unittest.main()
