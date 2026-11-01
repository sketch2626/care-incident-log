"""T1: the developer-only test list (tools/testlist). Scratch folders only; the real private/ is never used."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import helpers

server = helpers.server
ROOT = helpers.ROOT
A = helpers.api
TOOL_DIR = ROOT / "tools" / "testlist"
BASE = "/api/mary/testlist"

LIST_TEXT = ("\ufeff# Try these\nIntro line\n- loose\n\n## Talk\n- hello\n- same\nread me: <b>x</b>\n"
             "## Games\n- same\n- cards\n")


def tree(path):
    path = Path(path)
    out = []
    for p in sorted(path.rglob("*")):
        out.append((str(p.relative_to(path)), p.stat().st_size if p.is_file() else -1))
    return out


helpers.start_server()
server.testlist_tool()  # loads the module (reads only whether list.md exists)
TOOL = server._testlist


class Base(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(TOOL, "tool.py did not load")
        self.real_folder = TOOL.FOLDER
        self.container = Path(tempfile.mkdtemp(prefix="tl-", dir=helpers.TMP))
        self.folder = self.container / "testing"
        self.folder.mkdir()
        TOOL.FOLDER = self.folder
        self.addCleanup(self._restore)
        self.assertTrue(helpers._inside_tmp(TOOL.FOLDER))
        self.list = self.folder / "list.md"
        self.res = self.folder / "results.json"

    def _restore(self):
        TOOL.FOLDER = self.real_folder
        if hasattr(sys, "frozen"):
            del sys.frozen
        shutil.rmtree(self.container, ignore_errors=True)

    def write_list(self, text=LIST_TEXT):
        self.list.write_text(text, encoding="utf-8")

    def mark(self, section, item, mark="worked", note="", **kw):
        return A("POST", BASE + "/mark", {"section": section, "item": item, "mark": mark, "note": note}, **kw)

    def records(self):
        return json.loads(self.res.read_text(encoding="utf-8"))["items"]

    def get(self):
        s, d, _ = A("GET", BASE)
        self.assertEqual(s, 200)
        return d

    def item(self, d, section, text):
        for s in d["sections"]:
            if s["name"] == section:
                for i in s["items"]:
                    if i["text"] == text:
                        return i
        self.fail(f"{section}/{text} not found")

    def assert_all_off(self):
        for method, path in (("GET", BASE), ("GET", BASE + "/drawer.js"), ("GET", BASE + "/drawer.css")):
            self.assertEqual(A(method, path)[0], 404, path)
        self.assertEqual(self.mark("Talk", "hello")[0], 404)
        self.assertEqual(A("POST", BASE + "/reset", {})[0], 404)
        s, b, _ = A("GET", "/mary.html")
        self.assertEqual(s, 200)
        self.assertNotIn(b"testlist", b)
        self.assertEqual(b, (ROOT / "web" / "mary.html").read_bytes())
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), sorted(
            p.name for p in self.folder.iterdir() if p.name == "list.md"))


class TestOffStates(Base):
    def test_no_list(self):
        self.assert_all_off()
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_frozen(self):
        self.write_list()
        sys.frozen = True
        self.assert_all_off()
        self.assertEqual([p.name for p in self.folder.iterdir()], ["list.md"])

    def test_deleting_list_turns_off(self):
        self.write_list()
        self.assertEqual(A("GET", BASE)[0], 200)
        self.list.unlink()
        self.assert_all_off()


class TestOn(Base):
    def test_page_and_assets(self):
        plain = (ROOT / "web" / "mary.html").read_bytes()
        self.write_list()
        s, b, _ = A("GET", "/mary.html")
        self.assertEqual(s, 200)
        self.assertEqual(b.count(b"/api/mary/testlist/drawer"), 2)
        self.assertEqual(b.replace(TOOL.DRAWER_TAGS, b""), plain)
        at = plain.rfind(b"</body>")
        self.assertEqual(b, plain[:at] + TOOL.DRAWER_TAGS + plain[at:])
        s, b, h = A("GET", BASE + "/drawer.js")
        self.assertEqual(s, 200)
        self.assertEqual(b, (TOOL_DIR / "drawer.js").read_bytes())
        self.assertIn("javascript", h.get("Content-Type", ""))
        s, b, h = A("GET", BASE + "/drawer.css")
        self.assertEqual(s, 200)
        self.assertEqual(b, (TOOL_DIR / "drawer.css").read_bytes())
        self.assertIn("text/css", h.get("Content-Type", ""))


class TestParse(unittest.TestCase):
    def test_parse(self):
        d = TOOL.parse(LIST_TEXT.lstrip("\ufeff"))
        self.assertEqual(d["title"], "Try these")
        self.assertEqual([s["name"] for s in d["sections"]], ["", "Talk", "Games"])
        first = d["sections"][0]
        self.assertEqual(first["entries"][0], {"type": "line", "text": "Intro line"})
        self.assertEqual([i["text"] for i in first["items"]], ["loose"])
        talk = d["sections"][1]
        self.assertEqual([i["text"] for i in talk["items"]], ["hello", "same"])
        self.assertEqual(talk["entries"][2], {"type": "line", "text": "read me: <b>x</b>"})
        self.assertEqual([i["text"] for i in d["sections"][2]["items"]], ["same", "cards"])
        self.assertEqual(TOOL.parse("")["title"], "Test list")
        self.assertEqual(TOOL.parse("")["sections"], [])

    def test_bom_via_file(self):
        with tempfile.TemporaryDirectory(dir=helpers.TMP) as t:
            old = TOOL.FOLDER
            TOOL.FOLDER = Path(t)
            try:
                self.assertTrue(helpers._inside_tmp(TOOL.FOLDER))
                (Path(t) / "list.md").write_bytes(b"\xef\xbb\xbf# Title\n- a\n")
                d = TOOL.current()
                self.assertEqual(d["title"], "Title")
                self.assertEqual(d["sections"][0]["items"][0]["text"], "a")
            finally:
                TOOL.FOLDER = old


class TestMarks(Base):
    def test_saved_and_survives_restart(self):
        self.write_list()
        s, r, _ = self.mark("Talk", "same", "didnt", "broke")
        self.assertEqual(s, 200)
        rec = self.records()
        self.assertEqual(len(rec), 1)
        for k, v in (("item", "same"), ("section", "Talk"), ("mark", "didnt"), ("note", "broke")):
            self.assertEqual(rec[0][k], v)
        self.assertIn("T", rec[0]["time"])
        got = self.item(self.get(), "Talk", "same")
        self.assertEqual((got["mark"], got["note"]), ("didnt", "broke"))
        spec = importlib.util.spec_from_file_location("testlist_tool_fresh", TOOL_DIR / "tool.py")
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        fresh.FOLDER = self.folder
        self.assertTrue(helpers._inside_tmp(fresh.FOLDER))
        again = [i for s in fresh.current()["sections"] for i in s["items"]
                 if i["text"] == "same" and s["name"] == "Talk"][0]
        self.assertEqual((again["mark"], again["note"]), ("didnt", "broke"))

    def test_same_text_two_sections(self):
        self.write_list()
        self.mark("Talk", "same", "didnt", "broke")
        d = self.get()
        self.assertIsNone(self.item(d, "Games", "same")["mark"])
        self.mark("Games", "same", "worked")
        self.assertEqual(len(self.records()), 2)

    def test_carry_over(self):
        self.write_list()
        self.mark("Talk", "hello", "worked", "fine")
        self.mark("Games", "cards", "didnt", "bad")
        self.mark("Talk", "same", "worked")
        self.list.write_text("# T\n## Talk\n- hello\n- same\n## New\n- cards\n- brand new\n", encoding="utf-8")
        d = self.get()
        h = self.item(d, "Talk", "hello")
        self.assertEqual((h["mark"], h["note"]), ("worked", "fine"))
        c = self.item(d, "New", "cards")  # moved to another section
        self.assertEqual((c["mark"], c["note"]), ("didnt", "bad"))
        self.assertIsNone(self.item(d, "New", "brand new")["mark"])
        # changed text comes back unmarked
        self.list.write_text("# T\n## Talk\n- hello there\n- same\n", encoding="utf-8")
        d = self.get()
        self.assertIsNone(self.item(d, "Talk", "hello there")["mark"])
        self.assertEqual(self.item(d, "Talk", "same")["mark"], "worked")
        # dropped item's record stays in the file
        self.list.write_text("# T\n## Talk\n- other\n", encoding="utf-8")
        self.mark("Talk", "other", "worked")
        texts = sorted(r["item"] for r in self.records())
        self.assertEqual(texts, ["cards", "hello", "other", "same"])

    def test_needs_header(self):
        self.write_list()
        self.assertEqual(self.mark("Talk", "hello", tracker=False)[0], 403)
        self.assertEqual(A("POST", BASE + "/reset", {}, tracker=False)[0], 403)
        self.assertEqual([p.name for p in self.folder.iterdir()], ["list.md"])

    def test_bad_input(self):
        self.write_list()
        bad = ({"section": "Talk", "item": "nope", "mark": "worked"},
               {"section": "Talk", "item": "hello", "mark": "maybe"},
               {"section": "Talk", "item": "hello", "mark": None, "note": "x" * 4001},
               {"section": 1, "item": "hello", "mark": "worked"},
               {"section": "Talk", "item": 5, "mark": "worked"},
               {"section": "Talk", "item": "hello", "mark": "worked", "note": 7},
               {"section": "Talk", "item": ["hello"], "mark": "worked"},
               {})
        for body in bad:
            s, _, _ = A("POST", BASE + "/mark", body)
            self.assertEqual(s, 400, body)
        self.assertEqual(self.mark("Talk", "hello", None, "x" * 4000)[0], 200)
        self.assertEqual([p.name for p in self.folder.iterdir() if p.name != "list.md"], ["results.json"])

    def test_never_outside_folder(self):
        self.write_list()
        before = tree(self.container)
        parent_before = sorted(p.name for p in self.container.parent.iterdir())
        for sec, item in (("../../evil", "hello"), ("Talk", "../../evil"), ("C:\\evil", "hello"),
                          ("/etc/evil", "hello"), ("Talk", "C:\\Windows\\x"), ("..\\..\\evil", "..\\x")):
            self.assertEqual(self.mark(sec, item)[0], 400, (sec, item))
        self.assertEqual(tree(self.container), before)
        self.assertEqual(sorted(p.name for p in self.container.parent.iterdir()), parent_before)
        for path in (BASE + "/../../server.py", BASE + "/tool.py", BASE + "/..%2Ftool.py",
                     BASE + "/..%2F..%2Fserver.py", BASE + "/list.md", BASE + "/results.json"):
            self.assertEqual(A("GET", path)[0], 404, path)

    def test_corrupt_results(self):
        self.write_list()
        self.res.write_text("{not json", encoding="utf-8")
        d = self.get()
        self.assertIsNone(self.item(d, "Talk", "same")["mark"])
        self.assertEqual(self.res.read_text(encoding="utf-8"), "{not json")
        self.assertFalse((self.folder / "results.bad.json").exists())
        self.assertEqual(self.mark("Talk", "same")[0], 200)
        self.assertEqual((self.folder / "results.bad.json").read_text(encoding="utf-8"), "{not json")
        self.assertEqual(len(self.records()), 1)

    def test_reset_and_get_never_creates(self):
        self.write_list()
        self.get()
        self.assertFalse(self.res.exists())
        self.mark("Talk", "hello")
        self.mark("Games", "cards", "didnt")
        s, _, _ = A("POST", BASE + "/reset", {})
        self.assertEqual(s, 200)
        self.assertEqual(self.records(), [])
        self.assertIsNone(self.item(self.get(), "Talk", "hello")["mark"])
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["list.md", "results.json"])

    def test_log_untouched(self):
        helpers.reset_db()
        self.write_list()
        helpers.db_rows("SELECT 1")
        count = lambda: helpers.db_rows("SELECT COUNT(*) AS n FROM incidents")[0]["n"]
        backups = lambda: sorted(p.name for p in server.BACKUPS.glob("*")) if server.BACKUPS.exists() else []
        n0, b0 = count(), backups()
        self.mark("Talk", "hello")
        self.mark("Talk", "hello", None, "note")
        A("POST", BASE + "/reset", {})
        self.assertEqual(count(), n0)
        self.assertEqual(backups(), b0)


class TestPackaging(unittest.TestCase):
    def test_nothing_in_web_or_build(self):
        for name in ("drawer.js", "drawer.css", "tool.py"):
            self.assertEqual(list((ROOT / "web").rglob(name)), [], name)
        self.assertNotIn("testlist", (ROOT / "web" / "mary.html").read_text(encoding="utf-8").lower())
        src = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*(import testlist|from testlist\b|from tools)", src, re.M))
        build = (ROOT / "packaging" / "build.py").read_text(encoding="utf-8")
        self.assertNotIn("testlist", build.lower())
        for line in build.splitlines():  # tools/ may run helper scripts, but never ship as data
            if re.search(r"add-data|datas|collect_data", line):
                self.assertNotRegex(line, "tools")


class TestDrawerScript(unittest.TestCase):
    def test_node_check(self):
        node = shutil.which("node")
        if not node and Path(r"C:\Program Files\nodejs\node.exe").is_file():
            node = r"C:\Program Files\nodejs\node.exe"
        if not node:
            self.skipTest("node not found; drawer.js was not syntax-checked")
        r = subprocess.run([node, "--check", str(TOOL_DIR / "drawer.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])

    def test_script_limits(self):
        js = (TOOL_DIR / "drawer.js").read_text(encoding="utf-8")
        for bad in ("getUserMedia", "Audio(", "/api/mary/talk"):
            self.assertNotIn(bad, js)
        for m in re.finditer(r"fetch\(\s*([^,)]+)", js):
            self.assertTrue(m.group(1).strip().startswith("API"), m.group(0))  # API is the testlist path
        self.assertIn("var API = '/api/mary/testlist';", js)
        strings = re.findall(r"""["'`](/api/[^"'`]*)["'`]""", js)
        self.assertTrue(strings)
        for s in strings:
            self.assertTrue(s.startswith("/api/mary/testlist"), s)


if __name__ == "__main__":
    unittest.main()
