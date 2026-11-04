# How we work (the one home for process)

Every hub, worker and brief follows this file. It holds the process: who runs what, how a job moves from brief to merge, testing, the browser, publishing and boards. **Andy's standing decisions are in `docs/decisions.md`**, each with its guard, and they outrank this file. The spirit behind both is `docs/mission.md`.

**Rules live in two places only: `docs/decisions.md` and this file** (Andy, 2026-11-04). Notes (status, the roadmap, a folder's notes, reports, briefs for finished work and the archive) hold facts, history and context. They never hold an instruction that could override a rule. Where a note needs a rule, it links to it ("see D12"). If a note and a rule disagree, the rule wins, and the note gets fixed. Andy: "any notes that go in are addendums to certain things in the rules… That way the notes don't get read and supersede something."

## Who runs what (D14)
| Who | Where | Model | Does | Never |
|---|---|---|---|---|
| **Hub** | Andy's own account, in the Claude desktop app | Opus | Talks with Andy, plans, asks with one-click buttons, writes briefs, starts one worker at a time, watches, merges, publishes, keeps `docs/status.md` current | Writes app code (only a fix under about 40 lines in a file it already read), runs helpers, starts workers on Andy's account |
| **Worker** | The second account, Claude Code in a terminal, in its own worktree | Opus (`--model opus`) | Reads targeted lines, briefs helpers, reviews each diff, tests, commits on its branch, reports | Explores the whole codebase, writes big code itself, runs helpers in parallel, pushes or merges |
| **Helper** | Inside a worker, from `.claude/agents/` | Sonnet `coder`, or Haiku `quick-coder` | One piece from an exact brief, within its call budget | Anything outside its piece |

- **Andy's account is the hub only.** Every worker runs on the second account. There is one hub, kept for good and compacted by hand (at about 250-300K, after `docs/status.md` is up to date), never replaced for being long.
- **Sonnet `coder` (40 calls) writes all code,** new or changed.
- **Opus `coder`** (`model: "opus"`, default effort) is only for one truly hard piece that the brief names, such as encryption or a tricky concurrency fix, or one that Sonnet tried and failed. The worker says why in its report.
- **Haiku `quick-coder` (20 calls) only edits text:** wording, a doc page or a one-line style change. Haiku stays **under 100,000 tokens of context**, because its price changes sharply above that. Give it exact line ranges, at most about 150 lines a read, at most about 8 reads, one or two files, and a brief under about 2,000 characters. Anything bigger goes to Sonnet.
- **Helpers are small and one at a time.** One piece per helper, and a fresh helper for the next piece. Never resume a helper past about 150,000 tokens of context. Never run two at once unless Andy asks in words.
- **Effort.** Design and graphics work runs at extra-high effort: Andy, 2026-11-04: "We will not skimp on the graphics… We go full bore on stuff like that." A brief may set a worker's effort for judgment-heavy work. What costs is the model and the number of helpers, not the effort level. The 2026-11-01 usage audit found Opus helpers were two thirds of the second account's week. Andy, 2026-11-04: it "wasn't the effort level, it was that everything was being done on Opus… every helper… was all running on Opus, and they were spinning up a bunch of helpers."
- **Name the model** whenever a model is mentioned, in every report.
- **Quality first** (`docs/mission.md`). The method is what saves tokens. Never cut a feature, polish or expressiveness to save them.

## A job, from brief to merge
1. **The item.** Every batch of Andy's findings or ideas becomes a numbered item in `docs/mary-roadmap.md`, with his own words quoted. One worker takes each item.
2. **The brief.** The hub writes `docs/handoff/<item>.md` and commits it to `main` before the worktree is made. The brief says:
   - Andy's approval and its date, and the job in one sentence;
   - the sources, as exact sections or line ranges, and what's *not* part of this job;
   - the decisions it touches (by D number), and anything it must not touch;
   - a suggested split into helper pieces, and the models;
   - how to finish.

   Every brief starts by sending the worker to `docs/handoff/_common.md`, which carries the essentials and points here.
3. **The folder.** `git worktree add .worktrees/<item> -b other/<item>` from `main`, then copy `.claude/agents/` into it (`.claude/` isn't in git, and the helpers live there). `.worktrees/` is gitignored.
4. **The start.** The hub runs the worker in a Terminal panel tab, so Andy can watch, with cwd `.worktrees/<item>`:

   `& 'C:\Users\Andyb\.local\bin\claude.exe' "Read docs/handoff/<item>.md and follow it." --model opus --strict-mcp-config --permission-mode auto`

   The prompt goes before the options. `--permission-mode auto` approves safe steps by itself, so Andy gets no prompts. `--strict-mcp-config` skips the "new MCP server" question, because workers never use the real-log MCP.
5. **The watch.** A background Bash loop waits for a `WAITING:` or `DONE:` commit on `other/<item>` and then exits, which wakes the hub. Never poll in the foreground. A long job is also checked about every 20 minutes, so a worker that stopped at a usage limit never strands.
6. **Questions.** When a worker commits `WAITING:`, the hub asks Andy with buttons, then finds the worker with `ListAgents` (it shows as a peer, for example `m13-ad`) and sends his answer with `SendMessage`. Fallback: `claude -c "<Andy's answer>"` in the same folder.
7. **The merge.** The hub reads the report, runs `python run_tests.py -q` in the worktree, and merges into `main` only when the tests pass and Andy has approved any design. Then it publishes (below), moves the brief to `docs/handoff/done/`, runs `git worktree remove .worktrees/<item>` and deletes the branch.
- **Never two workers on the same files at once.**
- **Worker size.** `python tools/worker_context.py` shows how full each worker is. A new job goes to a fresh worker. A worker is reused only for fixes to its own job, while it's under about 200,000 tokens.
- **Near a usage limit** (about 96-98% of an account's week), the hub wraps up the running worker, updates `docs/status.md`, and prints a paste-ready handoff in chat.

## Inside a worker
- **Start:** run the `token-saving` skill and follow it as a worker. Read `docs/mission.md`, `docs/decisions.md` and this file, then only what the brief names: headings first, then line ranges. Never whole big files.
- **If the job would break a standing decision,** stop and commit `WAITING:` instead of working around it.
- **Brief each helper exactly,** in about 2-4k characters: the project in one line, the piece, the files with the line numbers found, the approach and the rules, the call budget, and "Return a short summary of the diff and the test result." Never tell a helper to "explore".
- **After each helper:** review the diff against the piece (exactly that, nothing else, and no weakened tests), run the tests, and commit only the named paths.
- **Checkpoints** (Andy, 2026-10-30): commit as soon as each piece passes, before starting the next. A usage-limit stop can cut a helper off mid-call, so it should never strand more than one piece.
- **Context:** if the worker's own context passes about 200,000 tokens, commit `WAITING: context full`, saying which steps are done.
- **Reports go in commit messages.** Subject `WAITING: …` when Andy must try or decide something; then stop, and the hub will message. Subject `DONE: …` when finished. The body has three plain lines for Andy, what isn't verified yet, and anything the hub needs to know to merge.

## Testing
- **The suite:** `python run_tests.py -q` prints one summary line plus any failures and BUG skips, and exits 1 on failure. Commit only when it passes.
- **Test setup:** every test file imports `from tests import helpers` first. `tests/helpers.py` points `APPDATA` and `TRACKER_DATA` at a temp folder before `server` is imported, and stops if a path would leave it. It runs one in-process server on a free port (`helpers.api(...)`, `reset_db()`, `make_andyflow_db(...)`, `incident(...)`), and gives secrets an in-memory backend.
- **Page scripts:** check them with `node --check`. Node is at `C:\Program Files\nodejs`, and a shell opened before the install may need that folder added to PATH.
- **Skills** must pass `tests/test_skills_contract.py` (`docs/skills-design.md`, `docs/how-to-make-a-skill.md`).
- **Mary's brain** is tested as D4 and D26 say: whole talks on the real model, and light testing by Andy's ear in Live until the paid model.
- **A standing decision gets a guard test** when a job first touches it (`docs/decisions.md`).

## Data, the browser and the screen (D15)
- **Scratch data only.** Workers never read or write `%APPDATA%\CareIncidentLog`, Andy's real key or Andy Flow's `history.db`. Tests use `TRACKER_DATA` and the in-process server. To try a build, set `APPDATA` to a scratch folder and `TRACKER_PORT=8799` (`CLAUDE.md`, "Desktop app").
- **Nothing on Andy's screen.** Not his Chrome, not computer use, and no desktop screenshots.
- **Workers may render their own pages to a picture** with headless Edge and a throwaway profile, to check a layout or a board.
- **The hub may use its built-in browser pane** without asking.
- **Workers never launch the app or the `.bat` files.** When the hub launches Mary for Andy, it uses `packaging\.venv\Scripts\pythonw.exe desktop.py --mary` (`Start Mary.bat`'s way), because the system Python falls back to Chrome.
- **The hub reads the real log through the `care-incident-log` MCP** (`mcp_server.py`), never through screenshots. The MCP is for Claude on Andy's machine only.
- **Never open File Explorer for Andy:** it puts up an approval card every time.

## Boards: anything visual, Andy sees first
- **Boards first, then the build.** A mock-up worker draws boards; Andy approves them by eye; a build worker matches them exactly.
- **The worker commits the boards** under `mockups/`, with a short README for the round. The committed copies are the source of truth.
- **Still boards go on a Design canvas Artifact on Andy's account,** opened on the right, where he sees them.
- **3D or moving boards show in the hub's built-in browser pane,** because a canvas may not show them (`docs/handoff/done/M24-critique.md`).

## Committing and publishing (D16, D17)
- **Workers** commit only on their own branch `other/<item>`, only named paths, and never push, merge or touch `main`.
- **The hub** merges into `main`, and after each merge that passes the tests, pushes `main` to GitHub (github.com/sketch2626/marys-porch) and backs it up to `dev`. Commits use GitHub's no-reply address.
- **Private facts never go in the repo** (D16). Andy's health and personal plans live in the hub's memory and in `private/`, which is gitignored.

## Keeping track
| What | Where |
|---|---|
| The spirit | `docs/mission.md` |
| Andy's standing decisions, with guards | `docs/decisions.md` |
| How we work | this file |
| What's happening now, what's waiting on Andy, what's next | `docs/status.md`. The hub updates "Right now" at every milestone and before any compaction or account switch. |
| What's ahead, item by item, in Andy's words | `docs/mary-roadmap.md` |
| Plans by topic | `docs/messaging-plan.md`, `docs/speakup-plan.md`, `docs/backend-plan.md`, `docs/pilot-checklist.md` |
| Open briefs | `docs/handoff/`. Finished ones move to `docs/handoff/done/`. |
| Done or dropped | `docs/archive/`. Each file says at its top why it's there. |

If the hub is ever restarted, it starts with "Continue with the next work": it reads `docs/mission.md`, then `docs/status.md`.

## Andy's hands and budget
- Andy works mostly by voice. His hands work but are hard to use: a quick click, opening a file or a short paste is fine; long, multi-step or repeated chores are not, and never key combos.
- He pays for every token. Replies are short and plain, with one question and one-click buttons.
- A box's buttons vanish once the talk moves past them. Never point him at an old button; ask again in a fresh box.
- After sending Andy to approve something in a worker, follow up and tell him it worked.
