# Care Incident Log (Operation Save Grandma)

Private incident tracker for nursing-home residents. Built by a nursing-home resident (works hands-free by voice) to log care failures; goal is a downloadable standalone app for every resident's laptop, plus reports for ombudsman / state inspectors.

## Why this matters
This is Andy's mission, not a demo.
- **Who:** Andy is a 43-year-old resident of a North Carolina nursing home. He lives with poor care every day and watches his neighbors get the same.
- **How:** he builds this hands-free by voice, with AI and no computer-science degree. A tool like this never existed because nobody had the will or the money. AI now makes it possible for pennies, built by the person it affects. That's the story to tell: this is what AI is for.
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

## Next steps
1. ~~Quiet test suite~~ **Done 2026-10-24** (371bba0, ea5c4c2, 1c0182d): 59 tests, about 2 s. 5 BUG skips in `tests/test_guess.py` that `guess_incident()` gets wrong. It marks "bled", "couldn't breathe" and "can’t breathe" (curly apostrophe) as minor. It reads "twenty five minutes" as 5 and "half an hour" as 60. Fix them in a small worker, then remove the skips.
2. **Mary prototype, with Andy as user #1** (`docs/companion-plan.md`). **Brain done 2026-10-25** (ed6ec4e, 5ecb2d2): `mary/instructions.md`, `mary.py` (`reply(text, memory, api_key)`), `tests/test_mary.py`, speed test `tools/mary_speed.py` (needs env `GEMINI_API_KEY`; no key is saved yet, so Gemini speed is unmeasured). Speech-to-text median 1.1 s, p90 5.5 s. Small fix first: `beam_size=1` in `speech.py` `_transcribe` (the probe showed every turn about 1 s). Still to build: her full-screen face, the talk loop (on-device speech-to-text → Gemini → voice), the "Hey Mary" wake word, and memory on the laptop. Test speed first (reply within ~2 s on a cheap laptop), then voice.
3. **Lid to Mary.** Windows PIN, then Mary opens full screen on her own and stays open; a locked-down kiosk needs Windows 11 Pro. Also a one-click setup tool for helpers, and a laptop spec with a price.
4. **Before the pilot:** review, test and merge `wip/report-to-state`; it becomes Mary's speak-up skill. Then add facility-first emails ("Facility first" in `docs/backend-plan.md`).
5. Rebuild the installer. `build.py` must download the voice model when `models/` is missing, because `models/` is gitignored.
6. Finish the pilot/funding plan doc. The 5-resident pilot checklist is in `docs/pilot-checklist.md` (revise it for the companion); the pilot needs backend phases 1-2 only.
7. Build the backend phase by phase per `docs/backend-plan.md`. Phase 1 (encrypt the local log, app lock) needs no server and can come early. No real resident data reaches a server piece until its security review passes.

## Roles and working rules (the maintainer's usage budget is tight)
Run the `token-saving` skill at the start of every task (`~/.claude/skills/token-saving`). It's Andy's hub-and-worker setup, copied from Andy Flow's "Next work" session.
- **The conversation with Andy is the hub (Opus).** It plans with him and asks with one-click buttons. It starts ONE worker session at a time (`start_session`: user_asked, fresh, local, `use_worktree` false) and relays the worker's 3-line report. It doesn't write app code (only tiny fixes) and never runs helpers itself.
- **Worker sessions** (inherit Opus) read targeted lines and hand code to the helpers in `.claude/agents/`: `coder` (Sonnet, 40-call budget) or `quick-coder` (Haiku, 20), one at a time. Then they review the diff, test and commit. Name the model whenever you mention one.
- No browser, computer use or screenshots anywhere; use the `care-incident-log` MCP. Scratch data only (`TRACKER_DATA`, in-process server), never the real log.
- **Tests:** `python run_tests.py -q` prints one summary line plus any failures and BUG skips, and exits 1 on failure. Commit only when it passes. `tests/helpers.py` points `APPDATA`/`TRACKER_DATA` at a temp folder before importing `server`, and stops if a path would leave it. Every test file imports `from tests import helpers` first. It runs one in-process server on a free port (`helpers.api(...)`, `reset_db()`, `make_andyflow_db(...)`, `incident(...)`).
- When the hub gets long, update Status/Next steps here, and Andy starts a fresh hub with "Continue with the next work."
