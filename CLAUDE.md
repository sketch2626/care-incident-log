# Care Incident Log (Operation Save Grandma)

Private incident tracker for nursing-home residents. Built by a nursing-home resident (works mostly by voice) to log care failures; goal is a downloadable standalone app for every resident's laptop, plus reports for ombudsman / state inspectors.

## Why this matters
This is Andy's mission, not a demo.
- **Who:** Andy is a 43-year-old resident of a North Carolina nursing home. He lives with poor care every day and watches his neighbors get the same.
- **How:** he builds this mostly by voice, with AI and no computer-science degree. A tool like this never existed because nobody had the will or the money. AI now makes it possible for pennies, built by the person it affects. That's the story to tell: this is what AI is for.
- **Goal:** real change in how residents are treated. Build everything as if the state will read it, because it will.
- **Direction (2026-10-24): companion first.** A friendly animated AI companion named Mary (Gemini) that residents talk to as a friend, with speak-up help built in. A pure reporting tool scares residents and makes facilities fight it. Plan: `docs/companion-plan.md`.

- `server.py` — stdlib-only Python server on 127.0.0.1:8765. SQLite at `%APPDATA%\CareIncidentLog\incidents.db` (override with env `TRACKER_DATA`), daily backups in its `backups\`. The old project `data/` folder is copied there once (until the new log has incidents) and left in place. Soft delete only (`deleted_at`). Mutating API calls need header `X-Tracker: 1`.
- `web/` — vanilla HTML/CSS/JS UI, design "C" from `mockups/` (approved 2026-10-23): home = summary sentence + "Just tell me what happened" mic + 9 category tiles; add/saved/list/report/my-info screens; built for residents 65-95 (≥20px text, ≥64px targets). Andy Flow parts show only when Andy Flow is installed.
- `speech.py` — on-device speech-to-text (faster-whisper base.en, model in `models/`, sounddevice mic). Routes `GET /api/listen`, `POST /api/listen/start|stop`.
- `assist.py` — optional Gemini "smart helper" (resident's own key, off by default; key never sent to the page). `POST /api/tidy` sorts free text: Gemini if on, else offline `guess_incident()`.
- `reports.py` — formal state reports: `GET /report` (printable, attestation + signature lines) and `GET /api/export.xlsx`. CMS F-tag citations verified 2026-10-23 against CMS crosswalk/Appendix PP; F600 (neglect) added only for 3+ of one category in the period.
- Andy Flow inbox: reads `%APPDATA%\Andyflow\history.db` read-only; dictations/notes starting with "Incident" (or notes in a folder containing "incident") appear for one-click add.
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
  - Minimal entry points (wrap-up, 2026-10-26):
    - `Start Mary.bat` starts `server.py --no-browser` and opens `/mary.html` in the default browser.
    - The home screen's first "More" link is "Talk to Mary".
    - Nothing is uncommitted. Everything is syntax-checked and API-tested only: **nobody has seen it run in a window yet.**
  - **Next for a fresh worker, in order:**
    1. **T5 (Sonnet `coder`), the full entry points:**
       - `power.py`: `plugged_in()` via `GetSystemPowerStatus`, `keep_display_on(p)` = `p is not False`, and a `KeepAwake` thread that calls `SetThreadExecutionState(ES_CONTINUOUS|ES_DISPLAY_REQUIRED|ES_SYSTEM_REQUIRED)` and releases it on stop.
       - `GET /api/power` → `{plugged_in}`. The page already polls it, and a 404 counts as plugged in.
       - `desktop.py --mary`: opens `/mary.html` full screen, titled "Mary". It has a `js_api.close_window()` (the page menu shows Close when that exists), sets `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--autoplay-policy=no-user-gesture-required`, and runs KeepAwake start/stop.
       - Point `Start Mary.bat` at `pythonw desktop.py --mary`.
       - The home link says "Talk to Sam" when `companion` is "him".
       - My info gets the note "Mary uses this key too. A free key comes from Google AI Studio."
       - Tests in `tests/test_power.py`.
    2. **Andy tries Mary as user #1.** Fix what he finds: voice choice, timings and layout at his screen size. Then measure Gemini speed with his key (`tools/mary_speed.py`).
    3. **Docs:** `docs/companion-plan.md` gets the build status with commit ids and Sam's name. Also bundle `mary/instructions.md` in `packaging/build.py` when the installer is rebuilt (Next step 5).

## Next steps
1. ~~Quiet test suite~~ **Done 2026-10-24** (371bba0, ea5c4c2, 1c0182d): 59 tests, about 2 s. 5 BUG skips in `tests/test_guess.py` that `guess_incident()` gets wrong. It marks "bled", "couldn't breathe" and "can’t breathe" (curly apostrophe) as minor. It reads "twenty five minutes" as 5 and "half an hour" as 60. Fix them in a small worker, then remove the skips.
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
- **Worker sessions** (inherit Opus) read targeted lines and hand code to the helpers in `.claude/agents/`: `coder` (Sonnet, 40-call budget) or `quick-coder` (Haiku, 20), one at a time. Then they review the diff, test and commit. Name the model whenever you mention one.
- No browser, computer use or screenshots anywhere; use the `care-incident-log` MCP. Scratch data only (`TRACKER_DATA`, in-process server), never the real log.
- **Tests:** `python run_tests.py -q` prints one summary line plus any failures and BUG skips, and exits 1 on failure. Commit only when it passes. `tests/helpers.py` points `APPDATA`/`TRACKER_DATA` at a temp folder before importing `server`, and stops if a path would leave it. Every test file imports `from tests import helpers` first. It runs one in-process server on a free port (`helpers.api(...)`, `reset_db()`, `make_andyflow_db(...)`, `incident(...)`).
- **Quality first.** Never leave out features, polish or expressiveness to save tokens. The hub/worker/helper method is how tokens are saved. Andy has a second account to continue on, so keep handoff state in this file and in committed files.
- When the hub gets long, update Status/Next steps here, and Andy starts a fresh hub with "Continue with the next work."
