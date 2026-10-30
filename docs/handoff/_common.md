# Handoff essentials for every second-account worker (read this first)

You are a **worker** on Andy's second account, in your own folder (a git worktree on branch `other/<item>`). The hub in Andy's desktop app merges your branch into `main` when you're done. Your memory folder is empty, so these are the essentials. **Read `docs/mission.md` first:** it's the spirit of the project, and every choice you make should fit it.

## Who and why
- **Andy** is 43 and paralyzed, and lives in a North Carolina nursing home with poor care. He builds this Care Incident Log mostly by voice. Everything a resident does must work by voice or one big tap, **never key combos**. He pays for every token.
- **Mary and Sam** are the app's warm, full-screen AI companions (Gemini) for residents aged 65-95. Their personalities are in `docs/characters/`, and the plan is in `docs/mary-roadmap.md`.
- **Residents are Southern and often conservative.** Guns, hunting, faith and prayer are welcome topics; only politics is off limits. Never moralize.

## How to work
- Run the `token-saving` skill first and follow it as a **worker**. Read `CLAUDE.md`, then only the sections your brief names. Use targeted line ranges, never whole big files.
- **Helpers, one at a time, from `.claude/agents/` (Andy, 2026-10-30: on this account, Opus writes the new code):**
  - **All new code:** run `coder` with `model: "opus"`; add `effort: "xhigh"` for the tricky parts.
  - Sonnet `coder` (the default model) only for small edits to existing code or extra tests.
  - Haiku `quick-coder` only for text-only edits (wording, doc pages), **under 100,000 tokens of context**: exact line ranges, at most about 150 lines per read, at most about 8 reads.
  - Name the model in every report.
- **Skills:** new abilities are built as **skills** (`docs/skills-design.md`, `docs/how-to-make-a-skill.md`, the example `skills/voice_comfort/`).
  - A skill reaches the internet only through `ctx.fetch`, with the hosts listed on its card.
  - It must pass `tests/test_skills_contract.py`.
- **Tests:** `python run_tests.py -q`. Check page scripts with `node --check` (Node is at `C:\Program Files\nodejs`). Commit only when they pass, and only named paths.
- **Checkpoints (Andy, 2026-10-30):** commit on your branch as soon as each helper's piece passes the tests, before starting the next one. A usage-limit stop can cut off a helper mid-call with no graceful stopping point, so it should never strand more than one piece.
- **Rules:**
  - Scratch data only. Never read or write `%APPDATA%\CareIncidentLog`, his real key, or Andy Flow's `history.db`.
  - No browser, computer use or screenshots.
  - Never launch the app or the .bat files.
  - UI: text ≥20px, targets ≥64px, plain words.
- **Your branch only:** commit on `other/<item>`. Never push, merge or touch `main`, and never edit files outside your worktree.
- **Reports go in commit messages:**
  - Subject `WAITING: …` when Andy must try or decide something. Then stop; the hub will message you.
  - Subject `DONE: …` when you're finished. The body is 3 plain lines for Andy, what isn't verified yet, and anything the hub needs to know to merge.
