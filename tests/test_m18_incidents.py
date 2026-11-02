from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

"""M18 piece 5: she reads back saved incidents when they ask, and a record she helped fill in says so."""
import html
import io
import json
import shutil
import sqlite3
import subprocess
import unittest
from contextlib import closing
from pathlib import Path

import openpyxl

import reports
import server
from tests.test_m18_screens import HARNESS

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"


def read(rel):
    return (ROOT / rel).read_text("utf-8")


def slice_js(js, start, end):
    i = js.index(start)
    return js[i:js.index(end, i)]


def node(body):
    code = HARNESS + read("web/mary/screens.js") + "\n" + body
    done = subprocess.run([NODE], input=code, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if done.returncode:
        raise AssertionError(done.stderr[-1500:])
    return json.loads(done.stdout.strip().splitlines()[-1])


def rows():
    return helpers.api("GET", "/api/incidents")[1]


class Column(unittest.TestCase):
    def setUp(self):
        helpers.reset_db()

    def test_it_migrates_on_an_old_table_and_keeps_the_row(self):
        helpers.api("POST", "/api/incidents", helpers.incident())
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            conn.execute("ALTER TABLE incidents DROP COLUMN helped_by")
            conn.commit()
        server.init_db()
        with closing(sqlite3.connect(server.DB_PATH)) as conn:
            cols = {r[1]: r for r in conn.execute("PRAGMA table_info(incidents)")}
        self.assertEqual((cols["helped_by"][2], cols["helped_by"][3]), ("TEXT", 1))
        got = rows()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["helped_by"], "")
        self.assertEqual(got[0]["description"], helpers.incident()["description"])

    def test_only_mary_or_sam_get_in(self):
        for value, kept in (("mary", "mary"), ("sam", "sam"), ("", ""), ("gemini", ""), ("Mary", ""), ("mary ; drop", "")):
            helpers.reset_db()
            helpers.api("POST", "/api/incidents", helpers.incident(helped_by=value))
            self.assertEqual(rows()[0]["helped_by"], kept)

    def test_an_edit_keeps_it_or_changes_it(self):
        _, made, _ = helpers.api("POST", "/api/incidents", helpers.incident(helped_by="mary"))
        path = f"/api/incidents/{made['id']}"
        helpers.api("PUT", path, helpers.incident(description="Changed."))   # says nothing about help
        self.assertEqual(rows()[0]["helped_by"], "mary")
        helpers.api("PUT", path, helpers.incident(helped_by="mary"))         # the form sends what it kept
        self.assertEqual(rows()[0]["helped_by"], "mary")
        helpers.api("PUT", path, helpers.incident(helped_by="sam"))          # a later edit he helped with
        self.assertEqual(rows()[0]["helped_by"], "sam")

    def test_what_she_wrote_herself_says_so_and_nobody_can_say_otherwise(self):
        server.mary_write_incident(helpers.incident(helped_by="sam"))  # Mary is the companion: the caller has no say
        self.assertEqual(rows()[0]["helped_by"], "mary")

    def test_no_other_path_can_set_it(self):
        mcp = read("mcp_server.py")
        self.assertIn('"source": "claude", "helped_by": ""', mcp)
        self.assertIn('**args, "helped_by": current["helped_by"]', mcp)
        js = read("web/app.js")
        self.assertEqual(js.count("helped_by:"), 1)
        self.assertIn("helped_by: helpedBy(),", js)
        self.assertNotIn("guessed.helped_by", js)


class TheNote(unittest.TestCase):
    WORDS = 'I said "where is my tray" and she walked off.'

    def setUp(self):
        helpers.reset_db()
        helpers.api("POST", "/api/incidents", helpers.incident(description=self.WORDS, helped_by="mary", occurred_date="2026-10-20"))
        helpers.api("POST", "/api/incidents", helpers.incident(description="Sam's one.", helped_by="sam", occurred_date="2026-10-19"))
        helpers.api("POST", "/api/incidents", helpers.incident(description="All mine.", occurred_date="2026-10-18"))

    def test_the_one_wording(self):
        self.assertEqual(reports.helped_note({"helped_by": "mary"}), "Filled in with Mary's help")
        self.assertEqual(reports.helped_note({"helped_by": "sam"}), "Filled in with Sam's help")
        for empty in ({}, {"helped_by": ""}, {"helped_by": None}, {"helped_by": "gemini"}):
            self.assertEqual(reports.helped_note(empty), "")

    def test_in_the_list(self):
        self.assertEqual([r["helped_note"] for r in rows()],
                         ["Filled in with Mary's help", "Filled in with Sam's help", ""])
        js = read("web/app.js")
        self.assertIn("esc(i.helped_note)", slice_js(js, "function entryHTML(i)", "function renderList()"))
        self.assertIn("inc.helped_note", slice_js(js, "function renderSaved(id)", "/* ---------- What I've written down"))
        self.assertNotIn("Filled in with", js)   # one helper, in reports.py

    def test_in_the_printable_report_and_apart_from_the_statement(self):
        page = html.unescape(helpers.api("GET", "/report")[1].decode("utf-8"))
        self.assertIn("<td>Filled in with Mary's help</td>", page)
        self.assertIn("<td>Filled in with Sam's help</td>", page)
        self.assertIn(f'<td class="stmt">“{self.WORDS}”</td>', page)
        self.assertIn('<td class="stmt">“All mine.”</td>', page)

    def test_in_the_spreadsheet_at_the_end_of_the_record_sheet(self):
        data = helpers.api("GET", "/api/export.xlsx")[1]
        ws = openpyxl.load_workbook(io.BytesIO(data))["Incident Record"]
        head = [c.value for c in ws[7]]
        self.assertEqual(head[:14], [name for name, _ in reports.COLUMNS[:14]])
        self.assertEqual(len(head), 15)
        table = [[c.value for c in ws[n]] for n in range(8, 11)]
        self.assertEqual(sorted(str(r[14]) for r in table),
                         ["Filled in with Mary's help", "Filled in with Sam's help", "None"])
        mary = [r for r in table if r[14] == "Filled in with Mary's help"][0]
        self.assertEqual(mary[5], f"“{self.WORDS}”")

    def test_the_summary_and_tags_take_no_notice(self):
        one = helpers.incident(id=1, description="x", logged_at="2026-10-20T10:00:00")
        self.assertEqual(reports.summary_for({**one, "helped_by": "mary"}), reports.summary_for(one))


class HerMemory(unittest.TestCase):
    def test_reading_a_name_aloud_is_a_turn_and_not_a_stored_fact(self):
        helpers.reset_db()
        memory = server.mary_memory()
        before = list(memory.facts)
        said = "It says Nurse Hollis walked off with your tray."
        self.assertEqual(helpers.api("POST", "/api/mary/live/said", {"text": said})[0], 200)
        memory = server.mary_memory()
        self.assertEqual(memory.recent[-1]["text"], said)
        self.assertEqual(memory.facts, before)
        if memory.store is not None:
            self.assertFalse([m for m in memory.store.active() if "Hollis" in str(m["text"])])


WORLD = r"""
const M = MaryScreens;
const said = (...lines) => lines.map(text => ({ text, bad: false }));
function row(n, o) {
  return Object.assign({ id: n, source: 'andyflow-note', source_id: 'S' + n, inbox_id: 77, occurred_date: '2026-10-' + ('0' + (28 - n)).slice(-2),
    occurred_time: '09:00', category: 'meal', severity: 'serious', description: 'words ' + n, staff_involved: 'Nurse Hollis',
    reported_to: 'charge nurse', outcome: 'nothing', witnesses: 'roommate', helped_by: 'mary', helped_note: "Filled in with Mary's help",
    formal_summary: 'tidy ' + n, summary: 'tidy ' + n, logged_at: 'x', deleted_at: null, wait_minutes: 5 }, o || {});
}
function reader(list, turns) {
  const env = { calls: 0, doc: () => null, panel: () => null, turns,
    incidents() { env.calls++; return Promise.resolve(list); } };
  return env;
}
const READ = (env, a) => M.run('use_screen', Object.assign({ action: 'read_incidents' }, a || {}), env);
function form(frame, companion) {
  const doc = pageOn(frame || 'add');
  doc.defaultView.maryHelp = window.maryHelp;
  return { doc, doc_: () => doc, env: { doc: () => doc, panel: () => null, turns: said('The tray never came.', 'put that in'),
    companion: () => companion || 'mary' } };
}
const U = (f, args) => M.run('use_screen', args, f.env);
"""

FORM = "let add = { formId: 1, helpFills: 0, helpWho: '', editing: null };\n"


class Reading(unittest.TestCase):
    def go(self, body):
        return node(WORLD + "(async function () {\n" + body + "\n})().catch(function (e) { console.error(e); process.exit(1); });")

    def test_it_refuses_when_they_did_not_ask(self):
        got = self.go(r"""
          const heard = ['Nice weather today', 'Are you ready', 'I listen to the radio', 'yes'];
          const out = [];
          for (const h of heard) { const e = reader([row(1)], said(h)); out.push([await READ(e), e.calls]); }
          const none = reader([row(1)], []);
          out.push([await READ(none), none.calls]);
          console.log(JSON.stringify(out));
        """)
        for res, calls in got:
            self.assertFalse(res["ok"])
            self.assertEqual(res["say"], "I only read your notes when you ask me to.")
            self.assertEqual(calls, 0)

    def test_the_ask_words_and_any_screen(self):
        got = self.go(r"""
          const out = [];
          for (const h of ['Read me what I saved', 'what did I write', 'Tell me my notes', 'the last one', 'what happened with my incidents']) {
            out.push((await READ(reader([row(1)], said(h)))).ok);
          }
          console.log(JSON.stringify(out));
        """)
        self.assertEqual(got, [True] * 5)

    def test_what_comes_back_and_what_never_does(self):
        got = self.go(r"""
          const r = await READ(reader([row(1), row(2, { deleted_at: '2026-10-25' }), row(3, { helped_note: '', helped_by: '', category: 'staff' })],
                                      said('read me my notes')));
          console.log(JSON.stringify(r));
        """)
        self.assertEqual(got["count"], 2)
        self.assertNotIn("more", got)
        first = got["incidents"][0]
        self.assertEqual(set(first), {"date", "time", "category", "severity", "words", "staff", "reported_to", "outcome",
                                      "witnesses", "helped"})
        self.assertEqual(first["words"], "words 1")
        self.assertEqual(first["category"], "My meal was late or missed")
        self.assertEqual(first["severity"], "Serious")
        self.assertEqual(first["helped"], "Filled in with Mary's help")
        self.assertEqual(got["incidents"][1]["helped"], "")
        text = json.dumps(got)
        for hidden in ("andyflow", "S1", "source", "\"id\"", "inbox", "tidy", "words 2", "logged_at"):
            self.assertNotIn(hidden, text)

    def test_ten_at_most_with_the_count_and_the_month_offer(self):
        got = self.go(r"""
          const list = []; for (let n = 1; n <= 23; n++) { list.push(row(n, n > 15 ? { occurred_date: '2026-09-01' } : {})); }
          const r = await READ(reader(list, said('read me all of them')));
          console.log(JSON.stringify(r));
        """)
        self.assertEqual(got["count"], 23)
        self.assertEqual(len(got["incidents"]), 10)
        self.assertEqual(got["incidents"][0]["words"], "words 1")
        self.assertIn("23", got["more"])
        self.assertIn("by month", got["more"])
        self.assertEqual(got["by_month"], [{"month": "2026-10", "count": 15}, {"month": "2026-09", "count": 8}])

    def test_the_turn_answering_her_month_offer_counts_and_the_one_after_does_not(self):
        got = self.go(r"""
          const list = []; for (let n = 1; n <= 12; n++) { list.push(row(n)); }
          const t = said('read me all of them');
          const e = reader(list, t);
          await READ(e);
          e.turns = t.concat(said('October'));
          const yes = await READ(e, { when: '2026-10' });
          e.turns = t.concat(said('October', 'Are you ready'));
          const no = await READ(e);
          console.log(JSON.stringify([yes.ok, no.ok]));
        """)
        self.assertEqual(got, [True, False])

    def test_when_and_category(self):
        got = self.go(r"""
          const list = [row(1, { occurred_date: '2026-10-20' }), row(2, { occurred_date: '2026-10-05', category: 'staff' }), row(3, { occurred_date: '2026-09-30' })];
          const e = reader(list, said('read my notes'));
          const out = [];
          for (const a of [{ when: 'latest' }, { when: '2026-10' }, { when: '2026-10-05' }, { category: 'staff' }, { category: 'write_meal' },
                           { when: 'latest', category: 'staff' }, { when: '2026-01' }]) {
            const r = await READ(e, a); out.push(r.incidents.map(i => i.date));
          }
          const bad = [await READ(e, { when: 'last Tuesday' }), await READ(e, { category: 'gardening' })];
          const none = await READ(e, { when: '2026-01' });
          console.log(JSON.stringify({ out, bad, none }));
        """)
        self.assertEqual(got["out"], [["2026-10-20"], ["2026-10-20", "2026-10-05"], ["2026-10-05"], ["2026-10-05"],
                                      ["2026-10-20", "2026-09-30"], ["2026-10-05"], []])
        self.assertTrue(all(b["ok"] is False for b in got["bad"]))
        self.assertTrue(got["none"]["ok"])
        self.assertEqual(got["none"]["say"], "There's nothing saved for that.")

    def test_a_failed_read_is_a_plain_line(self):
        got = self.go(r"""
          const e = reader([], said('read my notes'));
          e.incidents = () => Promise.reject(new Error('Nurse Hollis'));
          console.log(JSON.stringify(await READ(e)));
        """)
        self.assertEqual(got, {"ok": False, "say": "I couldn't get to your notes just now."})

    def test_an_emergency_turn_stops_it_at_the_gate(self):
        js = read("web/mary/app.js")
        got = self.go(r"""
          const S = { screen: 'everyday' }, TOOL_REFUSED = { ok: false, refused: true }, END_TALK_HELD = {};
          const ENV = reader([row(1)], said('read my notes'));
          function screenEnv() { return ENV; } function storyTake() { return {}; } function storyFromTool(c, r) { return r; }
          function liveEndTalk() {} function noteBusyNow() { return false; } function dictating() { return false; } function refreshName() {} function log() {}
        """ + slice_js(js, "function liveToolGate(heardResult", "// A short goodbye turn")
            + slice_js(js, "function liveToolCall(c, tc) {", "// Typed words while Live is open") + r"""
          const call = { functionCalls: [{ id: 1, name: 'use_screen', args: { action: 'read_incidents' } }] };
          const a = await liveToolCall({ toolBusy: 0, heardCheck: Promise.resolve({ emergency: 'fall' }) }, call);
          S.screen = 'emergency';
          const b = await liveToolCall({ toolBusy: 0, heardCheck: Promise.resolve({}) }, call);
          const calls = ENV.calls;
          S.screen = 'everyday';
          const c = await liveToolCall({ toolBusy: 0, heardCheck: Promise.resolve({}) }, call);
          console.log(JSON.stringify([a.functionResponses[0].response, b.functionResponses[0].response, calls, ENV.calls, c.functionResponses[0].response.ok]));
        """)
        self.assertEqual(got, [{"ok": False, "refused": True}, {"ok": False, "refused": True}, 0, 1, True])

    def test_declared_and_told_only_when_they_ask(self):
        import mary
        tool = [d for d in mary.LIVE_PAGE_TOOLS if d["name"] == "use_screen"][0]
        self.assertIn("read_incidents = read back what they saved, only when they ask", tool["description"].replace('"', ""))
        text = read("mary/instructions.md")
        part = text[text.index("Working on their screens\n"):text.index("Remembering\n- Below")]
        self.assertIn("They can ask you to read back what they saved. Do it only when they ask", part)
        self.assertIn("don't comment beyond it", part)
        self.assertEqual(len([d for d in mary.LIVE_PAGE_TOOLS if d["name"] not in ("story_more", "end_talk")]), 1)   # no new tool


class Helped(unittest.TestCase):
    def go(self, body):
        block = slice_js(read("web/app.js"), "// Piece 5: how many of her fills", "function keepDraft() {")
        return node(FORM + block + WORLD + "(async function () {\n" + body + "\n})().catch(function (e) { console.error(e); process.exit(1); });")

    def test_only_explaining_leaves_none(self):
        got = self.go(r"""
          const f = form();
          await U(f, { action: 'look' });
          await U(f, { action: 'explain', field: 'staff_involved' });
          console.log(JSON.stringify([helpedBy(), add.helpFills]));
        """)
        self.assertEqual(got, ["", 0])

    def test_a_refused_fill_leaves_none(self):
        got = self.go(r"""
          const f = form();
          const a = await U(f, { action: 'fill', field: 'day', value: 'tomorrow' });
          const b = await U(f, { action: 'fill', field: 'words', value: 'I fell' });
          const c = await U(f, { action: 'fill', field: 'sev', value: 'Serious' });
          console.log(JSON.stringify([a.ok, b.ok, c.ok, helpedBy()]));
        """)
        self.assertEqual(got, [False, False, False, ""])

    def test_a_real_fill_sets_it_and_putting_all_back_clears_it(self):
        got = self.go(r"""
          const f = form('add', 'sam');
          await U(f, { action: 'fill', field: 'staff_involved', value: 'Tom' });
          const one = helpedBy();
          await U(f, { action: 'fill', field: 'wait', value: '30 min' });
          await U(f, { action: 'put_back', field: 'staff_involved' });
          const two = helpedBy();
          await U(f, { action: 'put_back', field: 'wait' });
          console.log(JSON.stringify([one, two, helpedBy(), f.doc.byId.staff_involved.value]));
        """)
        self.assertEqual(got, ["sam", "sam", "", ""])

    def test_their_words_sets_it_too(self):
        got = self.go(r"""
          const f = form();
          const r = await U(f, { action: 'their_words', turns_back: '1' });
          const on = helpedBy();
          await U(f, { action: 'put_back', field: 'words' });
          console.log(JSON.stringify([r.ok, on, helpedBy(), f.doc.byId.words.value]));
        """)
        self.assertEqual(got, [True, "mary", "", ""])

    def test_a_fill_that_changes_nothing_is_no_help(self):
        got = self.go(r"""
          const f = form();
          f.doc.byId.staff_involved.value = 'Tom';
          await U(f, { action: 'fill', field: 'staff_involved', value: 'Tom' });
          const a = helpedBy();
          await U(f, { action: 'fill', field: 'outcome', value: 'Nothing' });
          await U(f, { action: 'put_back', field: 'staff_involved' });
          console.log(JSON.stringify([a, helpedBy()]));
        """)
        self.assertEqual(got, ["", "mary"])

    def test_old_help_stays_on_an_edit_and_a_later_edit_can_change_it(self):
        got = self.go(r"""
          const f = form('add', 'sam');
          add.editing = { helped_by: 'mary' };
          const a = helpedBy();
          await U(f, { action: 'explain', field: 'outcome' });
          const b = helpedBy();
          await U(f, { action: 'fill', field: 'outcome', value: 'Nothing' });
          const c = helpedBy();
          await U(f, { action: 'put_back', field: 'outcome' });
          add.editing = { helped_by: '' };
          console.log(JSON.stringify([a, b, c, helpedBy()]));
        """)
        self.assertEqual(got, ["mary", "mary", "sam", ""])

    def test_each_form_keeps_its_own_count(self):
        got = self.go(r"""
          const f = form();
          await U(f, { action: 'fill', field: 'outcome', value: 'Nothing' });
          const first = { formId: add.formId, helpFills: add.helpFills, helpWho: add.helpWho };
          Object.assign(add, { formId: 2, helpFills: 0, helpWho: '' });        // another draft
          await U(f, { action: 'fill', field: 'staff_involved', value: 'Tom' });
          await U(f, { action: 'put_back', field: 'outcome' });              // that fill was the first form's
          const second = helpedBy();
          Object.assign(add, { formId: 3, helpFills: 0, helpWho: '' });        // a clean form
          console.log(JSON.stringify([second, helpedBy(), first.helpFills]));
        """)
        self.assertEqual(got, ["mary", "", 1])

    def test_other_screens_do_not_count(self):
        got = self.go(r"""
          const f = form('info');
          const r = await U(f, { action: 'fill', field: 'i-room', value: '214' });
          console.log(JSON.stringify([r.ok, helpedBy()]));
        """)
        self.assertEqual(got, [True, ""])

    def test_a_tool_cannot_set_it(self):
        got = self.go(r"""
          const f = form();
          const out = [await U(f, { action: 'fill', field: 'helped_by', value: 'mary' }), await U(f, { action: 'help' }),
                       await U(f, { action: 'helped', helped_by: 'mary' })];
          console.log(JSON.stringify([out.map(r => r.ok), helpedBy()]));
        """)
        self.assertEqual(got, [[False, False, False], ""])

    def test_drafts_carry_the_count(self):
        js = read("web/app.js")
        for name in ("keepDraft() {", "function putDraft(d)"):
            part = slice_js(js, name, "}\n\n")
            self.assertIn("helpFills", part)
            self.assertIn("formId", part)


if __name__ == "__main__":
    unittest.main()
