# Care Incident Log (Operation Save Grandma)

Private incident tracker for nursing-home residents. Built by a nursing-home resident (works mostly by voice) to log care failures; goal is a downloadable standalone app for every resident's laptop, plus reports for ombudsman / state inspectors.

## Why this matters
This is Andy's mission, not a demo.
- **Who:** Andy is a 43-year-old resident of a North Carolina nursing home. He lives with poor care every day and watches his neighbors get the same.
- **How:** he builds this mostly by voice, with AI and no computer-science degree. A tool like this never existed because nobody had the will or the money. AI now makes it possible for pennies, built by the person it affects. That's the story to tell: this is what AI is for.
- **Goal:** real change in how residents are treated. Build everything as if the state will read it, because it will.
- **Direction (2026-10-24): companion first.** A friendly animated AI companion named Mary (Gemini) that residents talk to as a friend, with speak-up help built in. A pure reporting tool scares residents and makes facilities fight it. Plan: `docs/companion-plan.md`.

- `server.py` — stdlib-only Python server on 127.0.0.1:8765. SQLite at `%APPDATA%\CareIncidentLog\incidents.db` (override with env `TRACKER_DATA`), daily backups in its `backups\`. The old project `data/` folder is copied there once (until the new log has incidents) and left in place. Soft delete only (`deleted_at`). Mutating API calls need header `X-Tracker: 1`.
- `web/` — vanilla HTML/CSS/JS UI, design "C" from `mockups/` (approved 2026-10-23): home = summary sentence + "Just tell me what happened" mic + 9 category tiles; add/saved/list/report/my-info screens; built for residents 65-95 (≥20px text, ≥64px targets). Andy Flow parts show only when the resident has turned on "Connect Andy Flow" in My info (that switch itself shows only when Andy Flow is installed).
- `speech.py` — on-device speech-to-text (faster-whisper base.en, model in `models/`, sounddevice mic). Routes `GET /api/listen`, `POST /api/listen/start|stop`.
- `assist.py` — optional Gemini "smart helper" (resident's own key, off by default; key never sent to the page). `POST /api/tidy` sorts free text: Gemini if on, else offline `guess_incident()`.
- `reports.py` — formal state reports: `GET /report` (printable, attestation + signature lines) and `GET /api/export.xlsx`. CMS F-tag citations verified 2026-10-23 against CMS crosswalk/Appendix PP; F600 (neglect) added only for 3+ of one category in the period.
- Andy Flow inbox: **off by default** (setting `andyflow_enabled`, 2026-10-28, 2eba502). When off, nothing opens `%APPDATA%\Andyflow\history.db` and the MCP Andy Flow tools answer "link is off". A log that already holds `andyflow-*` incidents (Andy's) is switched on once by `init_db`. When on, it reads history.db read-only; dictations/notes starting with "Incident" (or notes in a folder containing "incident") appear for one-click add.
- Run: `Start Incident Tracker.bat`, or preview config `incident-tracker` in `.claude/launch.json`.
- "Update from Andy Flow" button → `POST /api/inbox/import`: logs every new "Incident" dictation/note at once, using `guess_incident()` in `server.py` (category, wait, never-came, severity).
- **Claude access: use the `care-incident-log` MCP (`mcp_server.py`, registered in `.mcp.json`), not screenshots.** Tools: `tracker_summary`, `list_incidents`, `add_incident`, `update_incident`, `remove_incident`, `andy_flow_inbox`, `update_from_andy_flow`, `dismiss_andy_flow_item`, `search_andy_flow` (all dictations/notes, to find care problems not prefixed "Incident"). The MCP is for Claude on Andy's machine only — not part of the resident installer.

## Desktop app (beta)
- `desktop.py` — app entry: starts the server in a thread (port 8765, or any free port if taken) and shows it in its own pywebview/WebView2 window; if WebView2 is missing it opens the default browser instead. Closing the window quits.
- Build: double-click `packaging\build.bat` (makes `packaging\.venv`, installs pinned `packaging\requirements.txt`, runs `packaging\build.py`). Output in `dist\`: `CareIncidentLog-Setup-<ver>.exe` (Inno Setup, per-user, no admin, Start-menu + desktop shortcuts) and `CareIncidentLog-<ver>-portable.zip`. Version = `VERSION` in `build.py`. Bundles `web/`, the voice model (`models\faster-whisper-base.en` → `_internal\models\`, where `speech.py` finds it) and speech libs (installer ~200 MB, ~400 MB installed); never `mcp_server.py`, `.mcp.json` or `mockups/`. Needs Inno Setup 6 for the installer (zip is built without it).
- `packaging\installer.iss` (installer), `packaging\make_icon.py` → `icon.ico`. Uninstall leaves the data folder alone.
- Test a build without touching real data: set env `APPDATA` to a scratch folder and `TRACKER_PORT=8799`, run the exe, use the API, close, rerun. Silent install: `Setup.exe /VERYSILENT /DIR=<folder>`.
- Not yet: code signing (unsigned exe gets a SmartScreen "More info → Run anyway" prompt).

## Mission
Put this app on every eligible resident's laptop, starting with one North Carolina facility, and make serious care lapses impossible to ignore. Residents (65-95) talk naturally; the app turns it into a formal, dated record the state takes seriously. Open source (GPL-3.0): github.com/sketch2626/care-incident-log. Long term: a backend built to medical/enterprise security standards, plan in `docs/backend-plan.md`. It covers passkey sign-in; named or anonymous sending; mood check-ins; de-identified research data for universities (consent, IRB); identity kept apart from data; and showing a facility only with 5+ participating residents, keyed by CMS provider number. Also funded helpers who set up residents' laptops and optional AI keys.

## Status (2026-10-24)
- Pushed to GitHub: v0.2.0. That's talk-to-log, design C, Talk buttons on detail boxes, formal reports, optional Gemini, and the installer build.
- Verified research, not yet committed:
  - `contacts/NC.json`: DHSR complaint line 1-800-624-3004 (no email or online form, printable forms only); state ombudsman (919) 855-3400 (re-check the roster date).
  - `docs/retaliation.md`: F585, F550, F600, F622/F623, NCGS 131E-117(12), 131E-124(c).
- Parked on branch `wip/report-to-state` (commit fddfdbc). It's unreviewed and untested, because helpers were stopped mid-work:
  - Report-to-state backend in `server.py` and `reports.py`: urgency levels via `/api/status`; the send wizard (grievance letter, completeness check, attestation, email/letter/phone from the contacts JSON); the submissions table; the retaliation flag and pattern detection; and quick notes (`/api/quick`). The `web/` screens for `#send` and `#rights` were never started.
  - The floating mic button in `desktop.py` + `web/float.html`, and the installer's "start with Windows" option.
  - `RETALIATION_REGS` in `reports.py` still needs filling from the verified citations above.
- NC Medicaid provides refurbished laptops for a $65 refurbishing fee, waived if the resident can't pay. Andy has one. Other states: check.
- **Mary build (worker "mary-app", 2026-10-25), in progress.** His name is **Sam** (final, Andy). Done:
  - Face component `web/mary/face.js`/`face.css`, with a demo at `/mary/demo.html`: Mary in 11 moods (7785098), and Sam with his square glow (1a35f99).
  - Talk routes: mood tags, `/api/mary/status|talk|talk?stream=1|hello`, and voice settings (685af39).
  - Listening auto-stop: `GET /api/listen/level` (9635709).
  - A "yes" to Mary's offer saves the incident (8e3e346).
  - Mary uses only the saved key (`gemini_key`) and model (`gemini_model`), not the smart-helper switch.
  - Mary screen `/mary.html` (`web/mary/app.js`, `mary.css`): talk loop, emergency, no-key, menu, typing (6eb1b50). Its API is `window.MaryApp`. `startFirstRun()` is a stub for now.
  - First run `web/mary/firstrun.js`, which covers:
    - Choose Mary/Sam, by tap or voice.
    - First hello, where she asks the resident's name.
    - A greeting by time of day.
    - Idle: asleep at 5 min and dimmed at 15 min (`IDLE` config). Any tap, key or talk wakes her.
    - Screen Wake Lock unless `/api/power` says on battery. That route isn't built yet, so for now the screen stays on.
  - **Full entry points, T5 done 2026-10-28** (97aee7c, 89bd43d; 170 tests pass):
    - `power.py`: `plugged_in()` (`GetSystemPowerStatus`; True/False/None, a desktop with no battery is True), `keep_display_on(p)` = `p is not False`, and a `KeepAwake` thread. Every `SetThreadExecutionState` call and the release on stop run on that thread. Plugged in or unknown means the display stays on; on battery, the normal timeout applies. `GET /api/power` → `{plugged_in}`. Tests are in `tests/test_power.py`.
    - `desktop.py --mary` opens `/mary.html` full screen, titled "Mary":
      - `MaryApi.close_window()` makes the menu show Close.
      - The WebView2 autoplay flag is set through the env var. The env var replaces pywebview's own args, so `--disable-features=ElasticOverscroll` is repeated.
      - `private_mode=False` with storage in `DATA\webview`.
      - KeepAwake starts before the window opens and is stopped in a `finally`.
      - Without WebView2, it opens the browser at `/mary.html` with no KeepAwake.
    - `Start Mary.bat` runs `packaging\.venv\Scripts\pythonw.exe desktop.py --mary`, because only that venv has pywebview. Without the venv it uses the system `pythonw`, which falls back to the browser.
    - Home shows "Talk to Sam" when `companion` is "him". My info has the note "Mary uses this key too…"
    - **Not yet seen in a real window:** full screen, Close, autoplay voice and the keep-awake.
  - **Full review done 2026-10-28** (`docs/review-2026-10-28.md`; fix commits 1b6a8e1…47c78f5; 254 tests, no skips). Fixed: the hidden Close on first run (blocker), missed emergency phrases, bad-key message, offers that didn't save, server data integrity, installer bundling. Ranked open items are in the doc. If Mary gets stuck full screen, the hub stops the `pythonw desktop.py --mary` process; `desktop.log` in the data folder has window errors.
  - **Next for a fresh worker, in order:**
    1. **Andy tried Mary as user #1 (2026-10-28).** Paste is fixed (4b16ebc, c1cadca) and his key is saved. His findings are the robot voice, games refused, Talk needed every turn, the captions and too many buttons. All of them are in **`docs/mary-roadmap.md`** (items M1-M8, with order and dependencies). Start one worker per item; worker `mary-fixes` (local_776f5e74) has the context for M1. **Found so far:** no paste in the app window, fixed 4b16ebc + c1cadca (see `docs/review-2026-10-28.md`, "Andy's first try").
    1b. **In flight (2026-10-29, hub = "Main session"):**
       - **M2:** done. Live talk works; Andy liked it (a story, and it stopped instantly when he cut in). His Mary and Sam voice picks are saved. Talk modes: Live (default), Normal, Offline, all as choices.
       - **M9a:** character sheets approved (`docs/characters/`).
       - **M9b:** done (39fd97c). Mary and Sam each have their own brain text plus live facts about their app; 349 tests pass. Not yet tried with his real key.
       - **M13 skills core:** running on the second account in `.worktrees/M13`, branch `other/M13`, peer session `m13-ad`. Andy approved the design (`docs/skills-design.md`) with two changes: internet only through `ctx.fetch` with allowed hosts, and voice on/off both ways (`skills_off` vs `skills_locked`). When its commit says "DONE: M13 skills core", review it, run the tests in the worktree, merge into `main`, then coordinate the `voices.py` `live_token()` hook. Then remove the worktree.
       - **Next after those:** M3 boards (here), then M4 and M5 (tricky, so second account), M12 pictures as a skill, and M7 games as skills.
    2. **Docs:** `docs/companion-plan.md` gets the build status with commit ids and Sam's name. Also bundle `mary/instructions.md` in `packaging/build.py` when the installer is rebuilt (Next step 5).

## Next steps
1. ~~Quiet test suite~~ **Done 2026-10-24** (371bba0, ea5c4c2, 1c0182d): 59 tests, about 2 s. The 5 `guess_incident()` BUG skips were fixed 2026-10-28 (1b6a8e1).
2. **Mary prototype, with Andy as user #1** (`docs/companion-plan.md`). **Brain done 2026-10-25** (ed6ec4e, 5ecb2d2): `mary/instructions.md`, `mary.py` (`reply(text, memory, api_key)`), `tests/test_mary.py`, speed test `tools/mary_speed.py` (needs env `GEMINI_API_KEY`; no key is saved yet, so Gemini speed is unmeasured). Speech fix done (fad93ba, `beam_size=1`): speech-to-text median about 1-1.6 s, p90 under 3 s (was 5.5 s).
   - **Face, in mock-ups:** round 1 (`mockups/mary/face-boards.html`, ade6015) was rejected. A was "scary", C was out, and B's warm glow came closest.
   - **Round 2 direction (Andy, 2026-10-25):** the screen IS her face, with no head outline and a warm light filling the screen. A soft edge glow changes color with her mood (soft pinkish red for an emergency, never scary).
   - **Her look:** fully cartoon with no realism, a mouth, no nose. Very expressive: eyes change shape, she blushes, and the forehead shades softly with no line eyebrows. 11 moods, plus everyday and emergency screens, with captions and buttons on top of her face near the bottom.
   - **Where the boards are:** on a Design canvas, which is private to Andy's first account. Committed copies are in `mockups/mary/round2/`, `round4/` and `round5/`, the source of truth for a fresh hub.
   - Andy approves a face before any build. Round 2 was liked ("so far, so good"). Round 3 fixes: no unibrow, thinner rounded brows instead of "smudges", and rounder eye corners.
   - **Round 4** (3be92ae, `mockups/mary/round4/`): the cuteness pass (Cute 1-3), his male version, **Sam** (final name; residents choose Mary or Sam), "Choose your companion" and "First hello". Andy: "so far so good… this will be what we use". He'll tweak after pilot feedback. Base: **Cute 3** for both faces (Andy, 2026-10-25).
   - **Mary and the computer (Andy, 2026-10-25):**
     - Level 1, her own skills: pictures ("show me a bird"), music, weather, news, reminders.
     - Level 2: she opens apps and sites, with a floating Mary button.
     - Level 3: she operates the computer, only after the pilot and only if residents ask.
     - Two setup modes: "Mary only" and "Mary plus the computer".
     - See "Mary and the computer" in `docs/companion-plan.md`.
   - **New feature (Andy, 2026-10-25): games with Mary.** She suggests a game, scoots aside, and helps the resident play. Word search comes first, then tic-tac-toe and solitaire. See "Games with Mary" in `docs/companion-plan.md`.
   - **New feature (Andy, 2026-10-25): family messages and calls.** "Mary, message my daughter…" or "Mary, put a call through to my son…", all from her screen. Plan and research list: "Family messages and calls" in `docs/companion-plan.md`. Mock-ups: `R2MessageScreen`, `R2CallScreen`.
   - Still to build: her full-screen face, the talk loop (on-device speech-to-text → Gemini → voice), the "Hey Mary" wake word, and memory on the laptop. Test speed first (reply within ~2 s on a cheap laptop), then voice.
3. **Lid to Mary.** Windows PIN, then Mary opens full screen on her own and stays open; a locked-down kiosk needs Windows 11 Pro. Also a one-click setup tool for helpers, and a laptop spec with a price.
4. **Before the pilot:** review, test and merge `wip/report-to-state`; it becomes Mary's speak-up skill. Then add facility-first emails ("Facility first" in `docs/backend-plan.md`).
5. Rebuild the installer. `build.py` must download the voice model when `models/` is missing, because `models/` is gitignored.
6. Finish the pilot/funding plan doc. The protection checklist and AI partner steps are in `private/protection-and-partners.md`, which is gitignored and never committed or quoted publicly. The 5-resident pilot checklist is in `docs/pilot-checklist.md` (revise it for the companion); the pilot needs backend phases 1-2 only.
7. Build the backend phase by phase per `docs/backend-plan.md`. Phase 1 (encrypt the local log, app lock) needs no server and can come early. No real resident data reaches a server piece until its security review passes.

## Roles and working rules (the maintainer's usage budget is tight)
Run the `token-saving` skill at the start of every task (`~/.claude/skills/token-saving`). It's Andy's hub-and-worker setup, copied from Andy Flow's "Next work" session.
- **The conversation with Andy is the hub (Opus).** It plans with him and asks with one-click buttons. It starts ONE worker session at a time (`start_session`: user_asked, fresh, local, `use_worktree` false) and relays the worker's 3-line report. It doesn't write app code (only tiny fixes) and never runs helpers itself.
- **Usage split between accounts (Andy, 2026-10-29):** his own account is running low, so workers started here run on **Sonnet** (`start_session` with `model: "claude-sonnet-5-5"`), and their helpers too. Tricky code written from scratch, and Opus work in general, goes to the **second account** (see below), where Opus 5.5 is fine. Visual boards and Andy's approvals stay here.
- **Worker sessions** (Sonnet on Andy's account; Opus on the second account) read targeted lines and hand code to the helpers in `.claude/agents/`, one at a time. **Sonnet `coder` (40-call budget) is the default for all code** (Andy, 2026-10-29). Haiku `quick-coder` (20) is only for text-only edits: wording, a doc page, or a one-line style change. The hardest new code can go to Opus on the second account (see below). Then they review the diff, test and commit. Name the model whenever you mention one.
- No browser, computer use or screenshots anywhere; use the `care-incident-log` MCP. Scratch data only (`TRACKER_DATA`, in-process server), never the real log.
- **Tests:** `python run_tests.py -q` prints one summary line plus any failures and BUG skips, and exits 1 on failure. Commit only when it passes. `tests/helpers.py` points `APPDATA`/`TRACKER_DATA` at a temp folder before importing `server`, and stops if a path would leave it. Every test file imports `from tests import helpers` first. It runs one in-process server on a free port (`helpers.api(...)`, `reset_db()`, `make_andyflow_db(...)`, `incident(...)`).
- **Quality first.** Never leave out features, polish or expressiveness to save tokens. The hub/worker/helper method is how tokens are saved. Andy has a second account to continue on, so keep handoff state in this file and in committed files.
- When the hub gets long, update Status/Next steps here, and Andy starts a fresh hub with "Continue with the next work."

### Second account: parallel pieces in their own folder (Andy, 2026-10-29)
Andy has a second Claude account (gifted). The terminal version of Claude Code (`C:\Users\Andyb\.local\bin\claude.exe`, on PATH) is logged into it. The desktop app stays on Andy's own account. Andy: anything that "can be done and set aside in a folder for you to then put back together… I trust you."
- **Pick pieces that stand alone:** mostly new files, little overlap with what workers here are changing, and no Design canvas (boards stay on Andy's account, where he sees them).
- **Its own folder and branch:** `git worktree add .worktrees/<item> -b other/<item>` from `main` (`.worktrees/` is gitignored). Then copy `.claude/agents/` into it, because `.claude/` isn't in git and the helpers live there.
- **The brief:** `docs/handoff/<item>.md`, committed to `main` before the worktree is made. It has the same shape as a worker brief (token-saving skill), plus:
  - Commit only on `other/<item>`, and never push, merge or touch `main`.
  - Put the report in the last commit message. Subject "WAITING: …" when Andy must decide something, "DONE: …" when finished.
- **Start it:** the hub runs it in a Terminal panel tab so Andy can watch: `& 'C:\Users\Andyb\.local\bin\claude.exe' --permission-mode acceptEdits --allowedTools "Bash(git:*)" "Bash(python:*)" "Bash(py:*)" "Bash(node:*)" "PowerShell(git:*)" "PowerShell(python:*)" "PowerShell(py:*)" "PowerShell(node:*)"`, with the prompt placed BEFORE the options (`claude "Read docs/handoff/<item>.md and follow it." --model opus …`), because `--allowedTools` swallows the words after it. On Windows the CLI often uses PowerShell, so both shells are listed. Use cwd `.worktrees/<item>`. To continue after Andy answers, find its session with `ListAgents` (it shows as a peer, for example `m13-ad`) and `SendMessage` it Andy's answer. That needs no hands (worked 2026-10-29). Fallback: `claude -c "<Andy's answer>"` in the same folder.
- **Watch it:** a background Bash loop waits for a "WAITING:" or "DONE:" commit on `other/<item>` and exits, which wakes the hub. Never poll in the foreground.
- **Put it back together:** the hub reads the report, runs `python run_tests.py -q` in the worktree, merges into `main` only when it passes and Andy has approved any design, then runs `git worktree remove`.
- **Models on the second account (Andy, 2026-10-29):**
  - Its worker may run the `coder` agent with `model: "opus"` and `effort: "xhigh"` for tricky code written from scratch. Sonnet does ordinary logic and Haiku small edits, and the worker decides which.
  - **Haiku stays under 100,000 tokens of context on both accounts (Andy: its price changes dramatically above that).** Use exact line ranges, at most about 150 lines per read, at most about 8 reads, one or two files, and a brief under about 2k characters. Anything bigger goes to Sonnet. This rule is also in the `token-saving` skill and `.claude/agents/quick-coder.md`.
- **Never at the same time:** a worker here and the other account never change the same files at once. Its memory folder is separate, so its brief must carry the essentials.
