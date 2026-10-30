# Handoff: installer rebuild 0.3.0 (second account, branch `other/installer`)

Read `docs/handoff/_common.md` first. Then read only these:
- `CLAUDE.md`: the "Desktop app (beta)" section and Next step 5.
- `packaging/build.py`, `packaging/build.bat`, `packaging/installer.iss`, `packaging/requirements.txt`.
- `tools/get_voice_model.py`, `tools/get_wake_model.py`.
- How `desktop.py` handles `--mary`.

**Goal:** a fresh resident laptop gets all of today's Mary from one installer: Live talk and the fallbacks, the captions font, the new menu, the skills (voice_comfort, pictures), and the "Hey Mary" wake word.

**Build:**
1. **Models download when missing.** `models/` is gitignored, and your worktree starts without it. `build.py` fetches each model that's missing, with a SHA-256 check, by reusing the `tools/get_*_model.py` code: faster-whisper base.en, kokoro, and the vosk small English model. Then it bundles them where `speech.py`, the Kokoro code and `wakeword.py` look for them.
2. **Bundle everything Mary needs:**
   - `web/`, including `web/mary/fonts/` with `OFL.txt`;
   - `mary/instructions.md`;
   - `skills/` with each skill's files;
   - `wakeword.py`, `power.py`, `voices.py`, `skills_core.py`, and the vosk package with its DLLs.
   - Check the frozen app finds each of these, the same way the existing code finds `models\` under `_internal\`.
   - Never `mcp_server.py`, `.mcp.json`, `mockups/`, `docs/handoff/`, `.worktrees/` or `bench/`.
3. **Shortcuts.**
   - Add a Start-menu and desktop shortcut named **"Mary"** that opens the companion (`--mary`). Keep the "Care Incident Log" shortcut.
   - Say in the report that the name is a guess for Andy to confirm, since residents can pick Sam.
4. **Version:** `VERSION = "0.3.0"`.
5. **Build and smoke test.** This is the one exception to "never launch the app or the .bat files": you may run `packaging\build.bat` (or `build.py` in its venv), and run the **built exe** only as follows:
   - Set env `APPDATA` to a scratch folder and `TRACKER_PORT=8799`.
   - Silent install to a scratch folder: `Setup.exe /VERYSILENT /DIR=<scratch>`.
   - Start the exe, check `/api/mary/status` (`offline_ready` true) and the wake route reports installed, check fonts and skills are served, close it, and uninstall.
   - Never touch the real `%APPDATA%\CareIncidentLog`.
   - Inno Setup 6 is at `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.
6. **Tests:** add a small test that checks the bundle list in `build.py` names each Mary piece above. Run the full suite.

**Don't change** app code outside `packaging/` and `tools/get_*` unless the frozen app can't find a file. In that case make the smallest fix and list it, because M4a is editing `mary.py`, `voices.py` and `web/mary/app.js`.

**Models:** Opus for the model-download code and any frozen-path fix; Sonnet for the build list, shortcuts and tests.

**Finish:** commit `DONE: installer 0.3.0 rebuilt and smoke-tested`. The body gives the installer and zip sizes, what was bundled, and the smoke-test results. `dist\` stays out of git. Use `WAITING:` instead only if something needs Andy.
