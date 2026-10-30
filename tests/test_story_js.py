from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M4a: the pure parts of a Live story told by the page (web/mary/app.js), checked with Node.
app.js needs a page to run, so only the helper block and the sentence splitter are cut out of it."""
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "web", "mary", "app.js")

CHECKS = r"""
const assert = require('assert');

// a long story: every piece is 1-2 sentences, at most 40 words, cut at sentence ends, and nothing is lost
const sent = 'The old dog ran down to the river and sat on the bank all day long.';   // 15 words
const story = Array(6).fill(sent).join(' ');
const parts = storyChunks(story);
assert.strictEqual(parts.length, 3);
parts.forEach(function (p) {
  assert.ok(p.split(/\s+/).length <= 40, p);
  assert.ok(/[.!?]$/.test(p), p);
});
assert.strictEqual(parts.join(' '), story);
// more than 40 words in two sentences: they go one at a time
const long = Array(30).fill('word').join(' ') + '.';
assert.deepStrictEqual(storyChunks(long + ' ' + long), [long, long]);
// a title is not a sentence end; markdown and extra spaces go
assert.deepStrictEqual(storyChunks('Mr. Smith  went *home*. He slept.', 40), ['Mr. Smith went home. He slept.']);
assert.deepStrictEqual(storyChunks('   '), []);

// the echo guard
const playing = "Well, the old dog didn't come home that night.";
const before = 'We looked all over the farm.';
assert.strictEqual(storyEcho('the old dog', playing, before), true);
assert.strictEqual(storyEcho('The old DOG, didnt come home!', playing, before), true);
assert.strictEqual(storyEcho("looked all over the farm", playing, before), true);   // the piece before
assert.strictEqual(storyEcho('wait what happened to the dog', playing, before), false);
assert.strictEqual(storyEcho('stop', playing, before), false);                      // a lone real word cuts in
assert.strictEqual(storyEcho('dog', playing, before), true);                        // a lone echoed word doesn't
assert.strictEqual(storyEcho('', playing, before), true);
assert.strictEqual(storyEcho('anything at all', '', ''), false);                    // nothing playing: it's them
// Live's text keeps growing: older echo doesn't count against the words she is saying now
assert.strictEqual(storyEcho('many other words from a piece long gone by now the old dog didnt come home', playing, before), true);

// what Live is told
const text = 'One. Two. Three.', ps = ['One. Two.', 'Three.'];
let a = storyAnswer(text, ps, { ok: true }, 2);
assert.strictEqual(a.told, true);
assert.strictEqual(a.story, text);
assert.ok(/Don't retell/.test(a.note));
a = storyAnswer(text, ps, { ok: true, cut: true }, 1);
assert.strictEqual(a.told, 'partly');
assert.strictEqual(a.said_so_far, 'One. Two.');
a = storyAnswer(text, ps, { ok: true, cut: true }, 0);
assert.strictEqual(a.said_so_far, '');
a = storyAnswer(text, ps, { ok: false, kind: 'failed', at: 0 }, 0);
assert.strictEqual(a.told, undefined);
assert.strictEqual(a.story, text);
assert.ok(/never speed up/.test(a.note));
a = storyAnswer(text, ps, { ok: false, kind: 'failed', at: 1 }, 1);
assert.strictEqual(a.told, 'partly');
assert.strictEqual(a.rest, 'Three.');
assert.ok(/don't repeat/.test(a.note));
console.log('OK story helpers');
"""


def find_node():
    node = shutil.which("node")
    if node:
        return node
    for base in (os.environ.get("ProgramFiles"), r"C:\Program Files"):
        if base:
            p = os.path.join(base, "nodejs", "node.exe")
            if os.path.isfile(p):
                return p
    return None


def between(src, start, end):
    a = src.index(start)
    return src[a:src.index(end, a)]


NODE = find_node()


BYE_CHECKS = r"""
const assert = require('assert');
["Go to sleep", "Okay Mary, you can go to sleep now.", "You can rest now", "That's all for now", "that'll be all for today",
 "Go on to sleep, Mary", "good night", "Goodbye", "Bye now", "Take a nap", "I'm going to sleep"].forEach(function (t) {
  assert.strictEqual(isGoodbye(t), true, t);
});
// a complaint or a question about sleep is not a goodbye, and she keeps listening
["I can't get to sleep", "I can't go to sleep", "I couldn't get to sleep last night", "I need some rest",
 "I want to go to sleep but my chest hurts", "Why did she go to sleep?", "I don't want to say goodbye",
 "That's all I can take", "That's enough", "They told me to go to sleep",
 "she told the kids to go to sleep and then the bear came", "", "hello"].forEach(function (t) {
  assert.strictEqual(isGoodbye(t), false, t);
});
console.log('OK goodbye');
"""


@unittest.skipUnless(NODE, "Node not found: the story checks were skipped")
class StoryJsTests(unittest.TestCase):
    def test_story_helpers(self):
        with open(APP, encoding="utf-8") as f:
            src = f.read()
        code = "\n".join([
            between(src, "function cleanSpeech(", "function estimateMs("),
            between(src, "var ABBR = {", "function addTimer("),
            between(src, "// --- M4a story helpers", "// --- end M4a story helpers"),
            CHECKS,
        ])
        run = subprocess.run([NODE, "-e", code], capture_output=True, text=True, encoding="utf-8",
                             timeout=30, cwd=ROOT)
        out = (run.stdout + run.stderr).strip()
        self.assertEqual(run.returncode, 0, out[-1500:])
        self.assertTrue(run.stdout.strip().startswith("OK "), out[-500:])

    def test_goodbye_phrases(self):
        with open(APP, encoding="utf-8") as f:
            src = f.read()
        code = "\n".join([
            between(src, "var BYE_MAX_WORDS", "var LIVE_BYE_MAX_MS"),
            between(src, "function isGoodbye(", "function liveSupported("),
            BYE_CHECKS,
        ])
        run = subprocess.run([NODE, "-e", code], capture_output=True, text=True, encoding="utf-8",
                             timeout=30, cwd=ROOT)
        out = (run.stdout + run.stderr).strip()
        self.assertEqual(run.returncode, 0, out[-1500:])
        self.assertTrue(run.stdout.strip().startswith("OK "), out[-500:])


if __name__ == "__main__":
    unittest.main()
