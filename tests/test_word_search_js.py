from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M7a: the word search page logic (skills/word_search/screen.js) and the held Live note (web/mary/talklive.js), checked
with Node. The page script runs against a stubbed page in tests/js/word_search_screen.js."""
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREEN_CHECKS = os.path.join(ROOT, "tests", "js", "word_search_screen.js")
TALKLIVE = os.path.join(ROOT, "web", "mary", "talklive.js")

NOTE_CHECKS = r"""
const assert = require('assert');
var S = null;
//NOTE
function mk(open) {
  const sent = [];
  return {sent: sent, s: {ready: true, ended: false, turnOpen: open, pendingNote: '',
                          ws: {readyState: 1, send: function (m) { sent.push(JSON.parse(m)); }}}};
}
let a = mk(false); S = a.s;
assert.strictEqual(note('first'), true);
assert.strictEqual(a.sent.length, 1);                       // she is quiet: it goes now, and it is silent
assert.strictEqual(a.sent[0].clientContent.turnComplete, false);
a = mk(true); S = a.s;
assert.strictEqual(note('one'), true);
assert.strictEqual(note('two'), true);
assert.strictEqual(a.sent.length, 0);                       // she is speaking: nothing is sent
assert.strictEqual(a.s.pendingNote, 'two');                 // only the newest is kept
sendNote(a.s, a.s.pendingNote);
assert.strictEqual(a.sent[0].clientContent.turns[0].parts[0].text, 'two');
S = null; assert.strictEqual(note('x'), false);
console.log('OK note');
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


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


NODE = find_node()


@unittest.skipUnless(NODE, "Node not found: the word search page checks were skipped")
class WordSearchJsTests(unittest.TestCase):
    def run_node(self, code):
        run = subprocess.run([NODE, "-"], input=code, capture_output=True, text=True, encoding="utf-8",
                             timeout=60, cwd=ROOT)
        out = (run.stdout + run.stderr).strip()
        self.assertEqual(run.returncode, 0, out[-1500:])
        self.assertIn("OK ", run.stdout, out[-500:])

    def test_screen_logic(self):
        self.run_node(read(SCREEN_CHECKS))

    def test_note_is_held_while_she_speaks(self):
        src = read(TALKLIVE)
        a = src.index("function note(")
        part = src[a:src.index("// M7a: true while the resident's words", a)]
        self.run_node(NOTE_CHECKS.replace("//NOTE", part))
        # at turnComplete the held note goes out, and a finished session drops it
        self.assertIn("sendNote(s, held)", src)
        self.assertIn("s.pendingNote = '';   // M7a", src)


if __name__ == "__main__":
    unittest.main()
