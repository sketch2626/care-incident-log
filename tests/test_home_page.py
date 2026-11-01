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

    def test_key_box_has_big_paste_button_no_key_combos(self):
        html, js, css = read("index.html"), read("app.js"), read("styles.css")
        row = html[html.index('<div class="keyrow">'):]
        row = row[:row.index("</div>")]
        self.assertIn('id="i-gemini_key"', row)
        self.assertIn('type="button" class="pastebtn" id="pasteKey">Paste<', row)
        rule = re.search(r"\.pastebtn\{([^}]*)\}", css).group(1)
        self.assertGreaterEqual(int(re.search(r"min-height:(\d+)px", rule).group(1)), 64)
        self.assertGreaterEqual(int(re.search(r"font-size:(\d+)px", rule).group(1)), 20)
        self.assertIn("app.paste_text()", js)  # the app window (desktop.py)
        self.assertIn("navigator.clipboard.readText()", js)  # a plain browser
        self.assertIn("Key pasted. Tap Save.", js)
        self.assertIn("I couldn't reach what you copied.", js)
        paste = js[js.index("async function readClipboard"):js.index("$('#infoForm').addEventListener('keydown'")]
        self.assertNotIn("console.", paste)  # the key is never logged
        self.assertNotIn("api(", paste.replace("window.pywebview.api", ""))  # only Save sends it

    def test_my_info_has_way_back_to_mary(self):
        html, js, mary = read("index.html"), read("app.js"), read("mary/app.js")
        self.assertIn("openDeep('#info')", mary)  # M18: a frame on her own page, so a talk goes on
        self.assertIn('<button class="bigbtn alt" id="backToMary" type="button">', html)  # M17: a real button, top of every screen
        self.assertNotIn('href="/mary.html" hidden', html)
        self.assertIn("get('from') === 'mary'", js)
        self.assertIn("$('#backToMary').addEventListener('click'", js)
        self.assertIn("s.companion === 'him' ? 'Sam' : 'Mary'", js)

    def test_mail_card_stays_out_of_save_and_keeps_the_password_in_its_box(self):
        html, js, css = read("index.html"), read("app.js"), read("styles.css")
        form_end = html.index("</form>", html.index('id="infoForm"'))
        self.assertLess(form_end, html.index('id="mailCard"'))
        self.assertLess(html.index('id="mailCard"'), html.index('id="skillsCard"'))
        self.assertIn('type="password" id="mailPass" autocomplete="new-password" spellcheck="false"', html)
        self.assertRegex(css, r"\[hidden\]\{display:none!important\}")  # hides .bigbtn too
        self.assertIn("loadMail();", js)
        mail = js[js.index("/* ---------- Connect email"):js.index("/* ---------- What Mary remembers")]
        for banned in ("innerHTML", "localStorage", "console.", "state.", "toast("):
            self.assertNotIn(banned, mail)
        self.assertEqual(mail.count("box.value = '';"), 2)  # emptied whether it worked or not
        self.assertNotIn("mail", js[js.index("INFO_FIELDS"):js.index("]", js.index("INFO_FIELDS"))].lower())


if __name__ == "__main__":
    unittest.main()
