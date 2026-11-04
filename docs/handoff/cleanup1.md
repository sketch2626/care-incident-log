# Handoff: cleanup1, apply the audit: one home for each kind of thing (second account, branch `other/cleanup1`)

**Why:** Andy, 2026-11-04: "pull out any contradictions, and anything that we've moved on from or decided against that still lurking around in there. We need to get rid of all of that stuff. We need to make this look professional." The audit, `docs/handoff/done/audit1-report.md`, found it all, file by file and line by line. **Andy has answered all ten of its calls.** They're at the end of that report, under "Andy's answers".

Read `docs/handoff/_common.md`, then the whole audit report, with Andy's answers last. Read the files it names as you fix them.

**Andy's rule for this cleanup** (from his answers): rules live only in rule files. `docs/decisions.md` holds his standing decisions, and one how-we-work file holds the process. Notes (status, the roadmap, folder NOTES, reports, the archive) hold facts, history and context. They never hold an instruction that could override a rule. Where a note needs a rule, it links to it ("see D12").

**Do:**
1. **Create `docs/how-we-work.md`,** the one home for process: who runs what (Andy's account is the hub only; workers run on the second account as an Opus worker with Sonnet `coder` and Haiku for text only; design and graphics at extra-high effort; D14 as fixed), the worktree and brief flow, the browser rule, testing, committing and publishing (D17), and how boards are shown (call 9). Pull these from the eight places the audit found, and replace each old copy with a one-line link.
2. **`docs/decisions.md`:**
   - add the six standing decisions from call 2, as D21 to D26, each with its guard or "no guard yet";
   - apply calls 1 (dysreflexia is named when the talk is about it) and 3 (pet names);
   - keep each decision to its rule, its source and its guard.
3. **`docs/status.md`:** cut it to now, next, and a short "Waiting on Andy" list. The audit lists the old open questions; add each one, one line apiece. Move the history to `docs/archive/` as it is, under a dated name.
4. **`docs/mary-roadmap.md`:** keep only what's ahead. Done and dropped items move to the archive, with one line left behind ("M9e, done as M21c/d; see archive").
   - Fold the brain plans into one item, per call 5.
   - Apply calls 6 (real weather from the start), 7 (screens open on the same side as always; the porch scene takes the face's place) and 8 (how the 3D is made gets decided after the M24 scene).
   - Andy's words stay with their items.
5. **The other plans:** bring `docs/companion-plan.md`, `messaging-plan.md`, `backend-plan.md` and the speak-up plan up to date, or move them to the archive with a pointer, per the audit.
   - Mary is no longer a woman's face. She's the robot on the porch (M24, D20), and she can be renamed (call 10).
   - Rename the speak-up plan's own "D1-D10" so they don't clash with Andy's D numbers.
6. **The character sheets** (`docs/characters/`), per calls 3 and 4: they're robots on a porch swing, never claim to be a person, and say "I'm a robot, what some folks call AI" when asked straight out (D20). Pet names are fine (D7). The full personality rewrite waits for the paid model.
7. **`docs/handoff/_common.md`:** cut it to task essentials plus a link to how-we-work. Fix the stale lines the audit found, such as politics being "off limits", which is wrong.
8. **The project `CLAUDE.md`:** rewrite it to be short and current (what the app is, where things live, and links to mission, decisions, how-we-work and status), fixing every stale line the audit lists. If editing CLAUDE.md is blocked, write the full proposed text to `docs/handoff/done/CLAUDE-proposed.md` and leave the hub to apply it.
9. **Tests:** fix any test that pins a retired choice the audit lists and that this cleanup changes. Leave the full brain and its tests alone (call 3). Run `python run_tests.py -q`; it must pass.
10. **Andy's global instructions and the token-saving skill** live outside the repo. Copies are in `private/audit-inputs/` if you need to refer to them. Write the proposed changes to `docs/handoff/done/cleanup1-global-proposals.md` as plain before-and-after lines, and the hub will apply them with Andy.

**Rules:**
- Change docs, briefs, character sheets and the tests above. No app code.
- Don't touch `mockups/mary/round12/` or `docs/handoff/M24-scene*.md`, because the scene worker is working there.
- Nothing private goes into the repo (D16).
- Commit after each numbered step, so a full context loses nothing.
- If your context passes about 200K, commit `WAITING: context full`, saying which steps are done.

**Models:** you do the judgment and the writing yourself, at extra-high effort. A Sonnet `coder` may do the mechanical moves (copying sections to the archive, fixing links), one fresh helper per piece. Never Opus helpers.

**Finish:** commit `DONE: cleanup1`. The message carries:
- three plain lines for Andy;
- each file and what changed;
- the tests' result;
- what's left for the hub (the global proposals, and CLAUDE.md if it was blocked).

Then stop.
