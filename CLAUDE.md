# Care Incident Log (Operation Save Grandma)

Private incident tracker for nursing-home residents. Built by a nursing-home resident (works hands-free by voice) to log care failures; goal is a downloadable standalone app for every resident's laptop, plus reports for ombudsman / state inspectors.

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
