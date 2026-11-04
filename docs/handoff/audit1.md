# Handoff: audit1, a read-only audit of every rule and plan (second account, branch `other/audit1`)

**Why:** Andy, 2026-11-04: "I want to go through all of our planning and everything too. And pull out any contradictions, and anything that we've moved on from or decided against that still lurking around in there. We need to get rid of all of that stuff. We need to make this look professional." Rules have been added for weeks without the old lines they replaced being removed. Workers then follow stale text, and Andy's decisions quietly get undone.

**You only read.** Write one report and change nothing else. Andy rules on the hard calls, and then a later worker applies the fixes.

Read `docs/handoff/_common.md` first. Then read, in a targeted way (headings first, then the sections that matter; the roadmap and status files are long):
- the project's `CLAUDE.md`;
- copies of Andy's global instructions and the hub's `token-saving` skill, in `private/audit-inputs/` (gitignored: read them, but never commit or quote them at length);
- `docs/mission.md`, `docs/decisions.md`, `docs/status.md`, `docs/mary-roadmap.md`, `docs/companion-plan.md`, `docs/backend-plan.md`, `docs/messaging-plan.md` and any other plan in `docs/` (not `docs/archive/` or `docs/handoff/done/`, except to see what's already archived);
- `docs/handoff/_common.md` itself, `README.md`, and the READMEs in folders;
- the critic's report, `docs/handoff/done/M24-critique.md`, for M24;
- tests that pin a choice that was later dropped. Search; don't read every test.

**What's true now (2026-11-04, from the hub).** Andy's own words outrank any doc. Where a doc disagrees with this list, the doc is stale:
- **Who runs what:**
  - Andy's account is the hub only.
  - Every worker runs on the second account as a terminal session in its own worktree: an Opus worker, with Sonnet `coder` for code and Haiku only for text edits.
  - Design and graphics work runs at extra-high effort.
  - What burned her week was many Opus helpers, not the effort level (D14 as fixed today).
  - Workers started from the desktop app on Andy's account are retired.
- **The browser rule:** "no browser" means Andy's own Chrome and computer use on his screen. The hub's built-in browser is fine. Workers may render their own pages to a picture with headless Edge and a throwaway profile.
- **The project** is Mary's Porch (github.com/sketch2626/marys-porch). `gh` is signed in as sketch2626, `main` is published after every merge (D17), and commits use GitHub's no-reply email.
- **Mary and Sam** are 1950s robots on a 3D porch swing (M24): Mary is robin's-egg blue with a shawl, and Sam is tractor red with a feed-store cap. They aren't a woman's animated face. They call themselves robots, not AI (D20). They have pets (a cat and a hound), a lantern that shows listening and asleep, and a porch radio for music (M25). The weather is there from the start.
- **Her brain:**
  - Three brains sit behind a setting that's only for Andy's testing (D19); the default is still "full".
  - The personality gets rebuilt on a paid model that Andy is choosing (Gemini or the Claude API), aiming at "a normal person", not the way staff talk.
  - Testing is light, by Andy's ear in Live, until the new model arrives. Then the full testing comes, safety first.
  - Brains become modules later (M23).
- **Mary's window** opens maximized, not full screen. D12, D18 and the other decisions stand as written in `decisions.md`.

**Look for, in every file:**
1. **Contradictions:** two places that say different things about the same thing.
2. **Stale facts:** versions, sizes, sign-ins, file paths, who runs what, things that are "not yet" but are done, or "done" but were undone.
3. **Leftovers:** a plan or rule from something Andy moved on from or decided against that still reads as current. For example, Mary as a woman's face, "workers here on Sonnet", "never xhigh", and old brain plans.
4. **Duplication:** the same rule kept in several places that can drift apart. Say which one place should own it.
5. **Structure:** propose one home for each kind of thing:
   - the mission (why);
   - decisions (Andy's standing rules, each with a guard);
   - status (only what's happening now and next);
   - the roadmap (only what's ahead);
   - an archive (what's done or dropped);
   - how-to-work rules (one file that CLAUDE.md and the brief both point to).

   Say what moves where.

**Write `docs/handoff/done/audit1-report.md`:**
- **For Andy, in five lines at most:** what you found, in plain words.
- **Needs Andy's call:** numbered. For each: the conflict, the options, and your recommendation. Keep these to real decisions, not wording.
- **Clear fixes:** grouped by file, with line numbers. For each: what's wrong (contradiction, stale, leftover or duplicate) and the fix (new wording, delete, or move to the archive).
- **The proposed structure,** and what moves where.
- **Tests** that pin retired choices.
- **Edits to instruction files** (both CLAUDE.md files, `_common.md`, the token-saving skill) listed separately. Changing them may need Andy's approval.

**Rules:**
- Read only; your one write is the report.
- No app changes, no Gemini calls, no browser.
- Never put anything from `private/` into the report except a file name and a line number.
- If your context passes about 200K, commit what you have as `WAITING: context full`, with the report so far.

**Models:** this is judgment work, so do it yourself at extra-high effort, with no helpers.

**Finish:** commit `DONE: audit1 report`, with the five lines for Andy in the message. Then stop.
