# cleanup1: proposed changes outside the repo (for the hub to apply with Andy)

These files live outside the repo, so the cleanup worker didn't change them. Line numbers are from the copies in `private/audit-inputs/` (2026-11-04). Each change is a plain before and after. The aim is the same as the cleanup's: one home for each rule. The shared files keep only the general method. This project's specifics now live in `docs/how-we-work.md` (process) and `docs/decisions.md` (Andy's decisions), so the shared files point there instead of repeating them.

## 1. Andy's global instructions (`~/.claude/CLAUDE.md`, every project)
This file covers every project, including Andy Flow. **Andy decides** whether the new browser wording goes here or only into each project's own file.

**Line 7, the browser rule** (stale for this project; D15 as fixed):
- Before: `- No browser, computer use or screenshots unless Andy asks; use the project's MCP or API.`
- After: `- Nothing on Andy's screen unless he asks: not his Chrome, not computer use, and no desktop screenshots. Use the project's MCP or API. A worker may render its own pages to a picture with headless Edge and a throwaway profile, and the hub may use its built-in browser pane. A project's own rule file can say more (Save Grandma: D15 in docs/decisions.md).`

**Line 3, add one pointer** (so a project's process file wins over the shared skill for that project):
- Before: `` - Run the `token-saving` skill (`~/.claude/skills/token-saving`) at the start of every task. It's the hub-and-worker setup from Andy Flow's "Next work" session: ``
- After: `` - Run the `token-saving` skill (`~/.claude/skills/token-saving`) at the start of every task. It's the hub-and-worker setup from Andy Flow's "Next work" session. Where a project has its own how-we-work file (Save Grandma: docs/how-we-work.md), that file says where workers run and which models they use: ``

## 2. The token-saving skill (`~/.claude/skills/token-saving/SKILL.md`, shared with Andy Flow)
Keep it general. Each line below either goes general or points to the project's own file.

**Line 15, the helper row** (contradicts line 26 and this project's rule):
- Before: `` | **Helper**: a subagent inside a worker | `coder` (Sonnet) for tricky logic, `quick-coder` (Haiku) for routine edits | One task from an exact brief, within a tool-call budget | Anything outside its task | ``
- After: `` | **Helper**: a subagent inside a worker | `coder` (Sonnet) for all code; `quick-coder` (Haiku) only for text-only edits (wording, a doc page, a one-line style change) | One task from an exact brief, within a tool-call budget | Anything outside its task | ``

**Line 26, the usage-audit reading** (D14: it was many Opus helpers, not the effort level):
- Before: `` - **Sonnet writes the code on both accounts (Andy, 2026-11-01).** A usage audit found Opus helpers at `xhigh` were two thirds of his second account's week. On that account the worker itself is Opus, but it hands code to Sonnet `coder`. An Opus `coder` (default effort, never `xhigh`) is only for one truly hard piece the brief names, or one Sonnet tried and failed. One piece per helper; never resume a helper past about 150K context. Name the model in reports. ``
- After: `` - **Sonnet writes the code on both accounts (Andy, 2026-11-01).** A usage audit found Opus helpers were two thirds of the second account's week. Andy, 2026-11-04: it "wasn't the effort level, it was that everything was being done on Opus… every helper." So the worker may be Opus, but it hands code to Sonnet `coder`. An Opus `coder` is only for one truly hard piece the brief names, or one Sonnet tried and failed. Design and graphics work runs at extra-high effort. One piece per helper; never resume a helper past about 150K context. Name the model in reports. ``

**Line 28, the browser rule** (D15):
- Before: `- **No browser, no computer use, no desktop screenshots, anywhere.** Use the project's own MCP or API: in Andy Flow, the andyflow tools, with one page screenshot per check; in Save Grandma, the care-incident-log MCP.`
- After: `- **Nothing on Andy's screen:** not his Chrome, not computer use, and no desktop screenshots. Use the project's own MCP or API: in Andy Flow, the andyflow tools, with one page screenshot per check; in Save Grandma, the care-incident-log MCP. A worker may render its own pages to a picture with headless Edge and a throwaway profile, and the hub may use its built-in browser pane.`

**Line 14, where workers run** (in Save Grandma they're terminal sessions on the second account):
- Before: `| **Worker**: a session the hub starts | Opus (inherits the hub's model) | …`
- After: `| **Worker**: a session the hub starts (where and how: the project's how-we-work file, if it has one) | Opus | …` (the rest of the row unchanged)

**Line 30, how the hub hears back:**
- Before: `- **Never poll in the foreground.** The app wakes the hub when a local worker ends a turn.`
- After: `- **Never poll in the foreground.** The app wakes the hub when a local worker ends a turn. For a terminal worker, a background git loop waits for its WAITING: or DONE: commit (Save Grandma: docs/how-we-work.md).`

**Line 35, where the next item is read** (this project keeps it in `docs/status.md`):
- Before: ``    - Read the next item in the project's `CLAUDE.md` (Next work or Next steps), and say in 1-2 lines what it is. ``
- After: ``    - Read the next item where the project keeps it (its `CLAUDE.md` says where; Save Grandma: "Next" in docs/status.md), and say in 1-2 lines what it is. ``

**Line 38, how a worker starts:**
- Before: ``    - `start_session` with `initiation` "user_asked", `context` "fresh", `target` "local", `use_worktree` false, and a short `name`. ``
- After: ``    - Start it the way the project says (Save Grandma: a terminal worker on the second account, in its own worktree, docs/how-we-work.md). Otherwise `start_session` with `initiation` "user_asked", `context` "fresh", `target` "local", `use_worktree` false, and a short `name`. ``

**Line 44, answering a worker:**
- Before: `` 4. **If the worker asks something,** answer with `SendMessage` to its `local_…` id, or ask Andy with buttons. ``
- After: `` 4. **If the worker asks something,** answer with `SendMessage` (a terminal worker shows up in `ListAgents` as a peer), or ask Andy with buttons. ``

**Line 46, a fresh hub** (contradicts the hub's memory: one hub, compacted by hand):
- Before: `` 6. **When the hub itself grows long,** update the project's `CLAUDE.md` (status and next work). Then Andy starts a fresh hub with "Continue with the next work." ``
- After: `6. **When the hub itself grows long,** update the project's status file first, then compact by hand (at about 250-300K). There's one hub for good; a fresh hub is only for a restart, and it opens with "Continue with the next work."`

**Line 51, the brief's helper line** (matches line 15):
- Before: `` 2. "Start by running the `token-saving` skill and follow it the whole way. You orchestrate and read targeted line ranges only. Delegate routine edits to `quick-coder` (20-call budget) and trickier ones to `coder` (40), one task per call. Read CLAUDE.md first." ``
- After: `` 2. "Start by running the `token-saving` skill and follow it the whole way. You orchestrate and read targeted line ranges only. Hand all code to `coder` (Sonnet, 40-call budget) and text-only edits to `quick-coder` (Haiku, 20), one task per call. Read CLAUDE.md first." ``

## 3. The hub's memory (`~/.claude/projects/C--Users-Andyb-Operation-Save-Grandma/memory/`)
The hub can see these files; the worker saw only their index lines.
- **`feedback-working-method.md` and its `MEMORY.md` line.** The line now reads "thin hub, Sonnet workers here and Opus on her account, tight helper briefs, name the model, no browser or screenshots". Proposed: "thin hub on Andy's account; every worker on her account (Opus worker, Sonnet `coder`, Haiku text only); the process is docs/how-we-work.md". Retire "workers run Sonnet" here, "never `xhigh`" and "no browser… unless he asks".
- **`feedback-hub-only-account.md`.** "For the next few days" and "ask Andy before going back to running workers here" become permanent (D14). Desktop-app workers are retired.
- **`feedback-boards-on-canvas.md`** (audit call 9). Still boards go on a Design canvas Artifact on Andy's account, opened on the right. 3D or moving boards show in the hub's built-in browser pane. The worker commits the boards in `mockups/`, and the hub shows them (docs/how-we-work.md, "Boards").
- **`feedback-notes-never-rules.md`** is already there. It matches `docs/how-we-work.md`'s first section.
- **Facts the hub may want to record:**
  - D21-D27 are new;
  - companion-plan is archived;
  - the roadmap's brain item is M26;
  - Speak-up's own decisions are now SD1-SD10.
