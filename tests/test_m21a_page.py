"""M21a: the page's silent starts, tell() and the steps block (pure parts run with Node)."""
import json
import subprocess
import unittest

from tests import helpers  # noqa: F401  (first: points the data folder at a scratch folder)
from tests.test_m4d import APP, NODE, ROOT, between, read


def run(code):
    r = subprocess.run([NODE, "-e", code], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@unittest.skipUnless(NODE, "Node not found")
class PageTests(unittest.TestCase):
    def setUp(self):
        self.src = read(APP)

    def test_tell_with_no_key_shows_the_line_and_calls_no_voice(self):
        code = ("var S={hasKey:false,turn:1,screen:'everyday',phase:'idle'}, lines=[], voice=[], api_calls=0;"
                "function liveOn(){return false;} function greetLive(){return false;} function setCaption(t){lines.push(t);}"
                "function setMood(){} function setPhase(){} function speakModel(){voice.push(1);}"
                "function api(){api_calls++; return Promise.resolve({});} function log(){} function restPhase(){return 'idle';}\n"
                + between(self.src, "function screenLine(", "function showSteps(") +
                "tell('note','Help is on the way.','concerned').then(function(){"
                "console.log(JSON.stringify([lines,voice.length,api_calls]));});")
        self.assertEqual(run(code), [["Help is on the way."], 0, 0])

    def test_a_wake_starts_with_no_words(self):
        wake = between(self.src, "} else if (ev.type === 'wake') {", "wakeDeclined('talk did not start')")
        self.assertIn("startTalk({ mood: 'happy' })", wake)
        self.assertNotIn("say:", wake)

    def test_the_steps_block_is_filled_when_the_screen_opens(self):
        enter = between(self.src, "registerScreen('emergency', {", "leave: function")
        self.assertIn("showSteps('')", enter)
        code = ("var els={steps:{}}; function $(i){return els[i];} var MSG={emergency:'CALL 911'};\n"
                + between(self.src, "function showSteps(", "// ---------------------------------------------------------------- screens") +
                "showSteps(''); var a=els.steps.textContent; showSteps('Press the light'); console.log(JSON.stringify([a, els.steps.textContent]));")
        self.assertEqual(run(code), ["CALL 911", "Press the light"])
        with open(__import__("os").path.join(ROOT, "web", "mary.html"), encoding="utf-8") as fh:
            self.assertIn('id="steps"', fh.read())

    def test_last_words_are_the_last_sentence_or_two(self):
        code = (between(self.src, "function lastSentences(", "function speakModel(") +
                "console.log(JSON.stringify([lastSentences('One. Two! Three?'), lastSentences('')]));")
        self.assertEqual(run(code), ["Two! Three?", ""])


if __name__ == "__main__":
    unittest.main()
