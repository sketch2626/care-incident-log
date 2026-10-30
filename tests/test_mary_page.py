from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""Mary's screen is served: the page, its script and its style load, and the page uses the face script."""
import re
import unittest
from pathlib import Path

api = helpers.api


class MaryPageTests(unittest.TestCase):
    def get(self, path):
        status, body, headers = api("GET", path)
        self.assertEqual(status, 200, path)
        self.assertIsInstance(body, bytes, path)
        return body.decode("utf-8"), headers

    def test_page_loads_and_uses_face_and_app_scripts(self):
        html, headers = self.get("/mary.html")
        ctype = {k.lower(): v for k, v in headers.items()}.get("content-type", "")
        self.assertIn("text/html", ctype)
        self.assertIn("/mary/face.js", html)
        self.assertIn("/mary/face.css", html)
        self.assertIn("/mary/mary.css", html)
        self.assertIn("/mary/app.js", html)
        self.assertIn("/mary/captions.js", html)   # M4b: style A captions; capLive is their polite live region
        # M4b: the one Menu button (round 6 boards); Talk is a menu row, and there is no big Talk button any more
        for needle in ('id="menuBtn"', 'id="menu"', 'id="miTalk"', 'id="miCan"', 'id="miInfo"', 'id="miChoose"',
                       'id="miGames"', 'id="closeBtn"', 'id="canPanel"', 'id="infoPanel"', 'id="choosePanel"',
                       'id="capLive"', 'id="lightBtn"', 'id="okBtn"', 'id="infoBtn"', 'id="typing"'):
            self.assertIn(needle, html)
        for gone in ('id="talkBtn"', 'id="moreBtn"', 'data-act="slower"', 'data-act="louder"'):
            self.assertNotIn(gone, html)
        self.assertIn('role="menu"', html)
        self.assertEqual(html.count('role="menuitem"'), 6)
        self.assertIn('aria-disabled="true" data-act="games"', html)
        self.assertEqual(html.count('role="dialog"'), 3)

    def test_app_script_and_style_load(self):
        js, _ = self.get("/mary/app.js")
        self.assertIn("MaryApp", js)
        self.assertIn("/api/mary/talk", js)
        css, _ = self.get("/mary/mary.css")
        self.assertIn(".talk", css)

    def test_firstrun_script_loads_after_app_script(self):
        js, _ = self.get("/mary/firstrun.js")
        self.assertIn("MaryApp", js)
        self.assertIn("/api/mary/hello", js)
        html, _ = self.get("/mary.html")
        self.assertIn("/mary/firstrun.js", html)
        self.assertGreater(html.index("/mary/firstrun.js"), html.index("/mary/app.js"))

    def test_firstrun_idle_timings_are_in_one_config(self):
        js, _ = self.get("/mary/firstrun.js")
        self.assertRegex(js, r"var IDLE = \{\s*sleepMin:\s*5,\s*dimMin:\s*15\s*\}")
        self.assertIn("/api/power", js)
        self.assertIn("wakeLock", js)

    def test_menu_button_stays_on_first_run_screens_and_menu_keeps_a_way_out(self):
        # first run has no other way out of her full-screen window, so the Menu button must show on choose and hello,
        # and the menu there must keep Close Mary while hiding the items that would derail the first run
        css, _ = self.get("/mary/mary.css")
        html, _ = self.get("/mary.html")
        self.assertNotRegex(css, r'\[data-screen="(choose|hello)"\]\s*\.menu-btn')
        rule = re.search(r'\[data-screen="choose"\] \.menu > ([^,{]+),\s*\[data-screen="hello"\] \.menu > ([^{]+)\{display:none\}', css)
        self.assertIsNotNone(rule, "first-run menu rule is missing")
        for selector in rule.groups():
            self.assertIn(":not(#closeBtn)", selector)
        self.assertIn('id="closeBtn"', html)

    def test_menu_closes_on_idle_and_skills_list_into_things_she_can_do(self):
        js, _ = self.get("/mary/app.js")
        self.assertRegex(js, r"var MENU_IDLE_MS = 20000;")
        self.assertIn("'Stop talking'", js)
        self.assertIn("'Hide menu'", js)
        skills, _ = self.get("/mary/skills.js")
        self.assertIn("addThing", skills)
        self.assertNotIn("typeMenuBtn", skills)

    def test_listening_guards_double_tap_and_slow_first_stop(self):
        # a tremor double tap must not end the recording at once, and the first stop (which waits for the
        # voice model to load on a slow laptop) gets 60 s, with a kind line instead of "didn't catch that"
        js, _ = self.get("/mary/app.js")
        self.assertRegex(js, r"var MIN_LISTEN_MS = 800;")
        self.assertRegex(js, r"Date\.now\(\) - t0 < MIN_LISTEN_MS")
        self.assertEqual(js.count("/api/listen/stop?raw=1', {}, { ms: 60000 }"), 3)
        self.assertNotIn("/api/listen/stop?raw=1', {}, { ms: 30000 }", js)
        self.assertIn("I'm still waking up my ears", js)

    def test_wake_word_poll_hold_and_setting(self):
        # M6: one long-poll loop on /api/wake/wait, a hold while she is busy (renewed), "heard" shows only her
        # ear waves, "wake" starts a short talk, and My info has an On/Off choice for listening for her name
        js, _ = self.get("/mary/app.js")
        self.assertIn("'/api/wake/wait?after='", js)
        self.assertIn("'/api/wake/hold', { on: busy }", js)
        self.assertIn("if (W.inFlight) { wakeSchedule(500); return; }", js)
        self.assertIn("var WAKE_HOLD_RENEW_MS = 30000;", js)
        self.assertIn("setInterval(wakeHoldCheck, 1000);", js)
        self.assertIn("return !!S.convo || S.phase !== 'idle';", js)
        self.assertEqual(js.count("wakeHoldCheck();   // M6"), 3)   # setPhase, startTalk, closeConvo
        self.assertIn("face.setActivity('listening')", js)
        self.assertIn("var WAKE_HEARD_MS = 4000;", js)
        self.assertIn("startTalk({ say: WAKE_SAY, mood: 'happy', hello: WAKE_HELLO })", js)
        self.assertIn("S.screen === 'everyday' && !S.firstRun && !S.convo", js)
        self.assertIn("wake_word: it.v ? '1' : '0'", js)
        self.assertIn("st.wake_ready", js)
        self.assertIn("wakeState:", js)
        self.assertIn("set('wakeTitle', 'Listen for “Hey ' + n + '”')", js)
        html, _ = self.get("/mary.html")
        self.assertIn('id="wakeTitle"', html)
        self.assertIn('id="wakeList" class="rows" role="radiogroup" aria-labelledby="wakeTitle"', html)

    def test_face_files_still_load(self):
        self.get("/mary/face.js")
        self.get("/mary/face.css")

    def test_skills_stand_side_by_side_with_mary(self):
        app, _ = self.get("/mary/app.js")
        for needle in ("function sideBySide(on)", "sideBySide: sideBySide", "data-aside", "face.setAside(on)",
                       "cap.setAside(on)"):
            self.assertIn(needle, app)
        self.assertEqual(app.count("setAside: noop"), 2)   # the stand-in face and the stand-in caption
        skills, _ = self.get("/mary/skills.js")
        for needle in ("handlers[name].aside", "sideBySide(true)", "sideBySide(false)"):
            self.assertIn(needle, skills)
        face, _ = self.get("/mary/face.js")
        for needle in ("setAside: setAside", "aside: aside", "toggle('mf-aside', aside)"):
            self.assertIn(needle, face)
        css, _ = self.get("/mary/face.css")
        for needle in (".mf-aside .mf-stage", ".mf-aside.mf-think .mf-stage", ".mf-aside .mf-over",
                       ".mf-aside.mf-menu .mf-eyes", "@keyframes mf-glance"):
            self.assertIn(needle, css)
        caption, _ = self.get("/mary/captions.css")
        self.assertIn("#scr[data-aside] .cap", caption)
        page, _ = self.get("/mary/mary.css")
        self.assertIn(".skill-screen.aside", page)

    def test_pictures_stand_aside_and_nothing_covers_the_picture(self):
        folder = Path(__file__).resolve().parent.parent / "skills" / "pictures"
        css = (folder / "screen.css").read_text(encoding="utf-8")
        js = (folder / "screen.js").read_text(encoding="utf-8")
        self.assertNotIn("#face", css)
        self.assertNotIn("position:absolute;top:16px", css)   # the status pill that sat over the picture
        self.assertNotIn("~ .pic-status", css)
        self.assertIn("aside: true", js)
        self.assertNotIn("stage.appendChild(title)", js)
        self.assertNotIn("stage.appendChild(credit)", js)
        self.assertIn("parseFromString(t, 'text/html')", js)
        self.assertIn("plainText(data.credit, CREDIT_MAX)", js)
        self.assertNotIn("innerHTML = data", js)

    def test_voices_page_and_files_load(self):
        html, _ = self.get("/mary/voices.html")
        for needle in ('id="tabGemini"', 'id="tabLive"', 'id="tabOffline"', 'id="backBtn"',
                       'id="liveMary"', 'id="liveSam"', 'id="savedNow"',
                       "/mary/face.js", "/mary/voices.js", "/mary/live.js", "/mary/voices.css"):
            self.assertIn(needle, html)
        for gone in ('id="liveStart"', 'id="liveUse"', 'id="liveVoices"'):
            self.assertNotIn(gone, html)
        for path in ("/mary/voices.html", "/mary/voices.js", "/mary/live.js", "/mary/voices.css"):
            text, _ = self.get(path)
            self.assertNotRegex(text, r"key(down|up|press)", path)
        live, _ = self.get("/mary/live.js")
        for needle in ("echoCancellation", "interrupted", "/api/mary/live/token", "/api/mary/voices/log",
                       "audioStreamEnd"):
            self.assertIn(needle, live)
        self.assertNotIn("gemini_key", live)
        self.assertNotIn("keydown", live)
        for needle in ("clientContent", "greet_ms", "mic_ms", "outputLatency", "startOffset"):
            self.assertIn(needle, live)
        voices, _ = self.get("/mary/voices.js")
        for needle in ("/api/mary/voices/stream", "getReader", "tapAt", "'played'", "outputLatency",
                       "line: 'saved'", "Saving…", "/api/settings", "Saved — "):
            self.assertIn(needle, voices)
        for needle in ("liveVoices", "liveUse", "selectedLive"):
            self.assertNotIn(needle, voices)
        for needle in ("livetalk", "activeBtn"):
            self.assertIn(needle, live)
        self.assertNotIn("liveStart", live)
        for needle in ("X-First-Sound-Ms", "new Audio("):
            self.assertNotIn(needle, voices)


if __name__ == "__main__":
    unittest.main()
