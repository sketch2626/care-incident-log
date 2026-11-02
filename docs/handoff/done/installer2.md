# Handoff: installer2, rebuild and check the frozen app (second account, branch `other/installer2`)

Read `docs/handoff/_common.md` first. Then read the "Desktop app (beta)" part of `CLAUDE.md`, plus `packaging/build.py`, `packaging/installer.iss`, `version.py`, `desktop.py` and `docs/status.md` "Right now".

**Why:** a lot has merged since the last build (v0.3.0, 2026-10-30):
- M9c, a memory store in its own `mary/memories.db`;
- M7a, word search;
- M8, a laptop speed check;
- M13b, tool groups;
- M4c and M4d, brain fixes.

M8's frozen build was never checked. Before the pilot, the installed app has to work the way the dev one does.

**Do this:**
1. **No downloads.** Your worktree has no `models/` (it's gitignored).
   - Copy the three models from the main checkout: `<main checkout>\models\` (a local copy, not a download).
   - Use the main checkout's existing build venv: `<main checkout>\packaging\.venv\Scripts\python.exe`. Run `packaging\build.py` with it from your worktree.
   - If anything would need downloading or a `pip install`, stop and commit `WAITING:` with what and why.
2. **Bump the version** in `version.py` to the next minor (0.4.0), and build. Note the installer, zip and installed sizes.
3. **Check the frozen app without touching real data.**
   - Set `APPDATA` to a scratch folder and `TRACKER_PORT=8799`. Install it silently (`Setup.exe /VERYSILENT /DIR=<scratch>`), run the exe, and use the API.
   - Check:
     - it starts;
     - `/api/mary/status` answers;
     - the speed check runs and saves its tier;
     - the skills load (pictures, voice comfort, word search) and `open_skill` works;
     - a word search starts;
     - a memory can be saved and forgotten (`mary/memories.db` lands in the scratch data folder);
     - the incident log and report still work.
   - Close it, rerun it, and check that everything persisted.
   - No Gemini calls with Andy's key, and no real `%APPDATA%\CareIncidentLog`.
4. **Fix what's broken in the frozen build only** (hidden imports, bundled files), in `packaging/`. If a fix needs app code, describe it and stop with `WAITING:`.
5. **Run `python run_tests.py -q`**, and run `node --check` on any script you touch.

**Stay out of** `mary.py`, `mary/`, `tools/brain_bench.py`, `bench/` and `mockups/` (M4e is changing the brain and the bench).

**Models:**
- Opus coder: packaging fixes.
- Sonnet coder: the scripted API checks.
- Checkpoint after the build and after the checks.

**Finish:** commit `DONE: installer2 v0.4.0 built and checked` with a short report: sizes, each check passed or failed, fixes made, and where the installer is (`dist\` in your worktree). Use `WAITING:` instead if something needs Andy. Then stop. Don't push or publish anything.
