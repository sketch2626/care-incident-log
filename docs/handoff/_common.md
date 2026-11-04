# Handoff essentials for every second-account worker (read this first)

You are a **worker** on Andy's second account, in your own folder (a git worktree on branch `other/<item>`). The hub in Andy's desktop app merges your branch into `main` when you're done. Your memory folder is empty, so this page gives you the essentials and points to the rest.

**Read these in order, then only what your brief names:**
1. `docs/mission.md`, the spirit. Every choice you make should fit it.
2. `docs/decisions.md`, Andy's standing decisions. If your job would break one, stop and commit `WAITING:` instead of working around it.
3. `docs/how-we-work.md`, the process: helpers and models, testing, checkpoints, the browser rule and reports. It's the one home for how work is run; this page only sums it up.

## Who and why
- **Andy** is 43 and paralyzed, and lives in a North Carolina nursing home with poor care. He builds **Mary's Porch** (the code still says Care Incident Log) mostly by voice. Everything a resident does must work by voice or one big tap, **never key combos**. He pays for every token.
- **Mary and Sam** are the app's companions for residents aged 65-95: two 1950s robots on a porch swing, who call themselves robots (D20). Her window opens maximized (D25). Her brain is Gemini today; a paid model is being chosen (roadmap M26). Who they are: `docs/characters/`. What's ahead: `docs/mary-roadmap.md`.
- **Residents are Southern and often conservative.** Guns, hunting, faith, prayer and politics are all welcome. On politics she's a good listener, never a yes-man and never a debater (`docs/mission.md`). Never moralize.

## The job, in short (details in `docs/how-we-work.md`)
- Run the `token-saving` skill first and follow it as a **worker**.
- **Helpers, one at a time** (D14): Sonnet `coder` writes all code; Haiku `quick-coder` only edits text, under 100,000 tokens of context; an Opus `coder` only for a piece your brief names. Name the model in every report.
- **Tests:** `python run_tests.py -q`, and `node --check` for page scripts. Commit as soon as each piece passes, and only named paths.
- **Data and screen** (D15): scratch data only, and nothing on Andy's screen. Never launch the app or the `.bat` files.
- **UI:** text 20px or larger, targets 64px or larger, plain words.
- **Skills:** new abilities are skills (`docs/skills-design.md`, `docs/how-to-make-a-skill.md`, the example `skills/voice_comfort/`). A skill reaches the internet only through `ctx.fetch`, with the hosts listed on its card, and must pass `tests/test_skills_contract.py`.
- **Your branch only:** commit on `other/<item>`. Never push, merge or touch `main`, and never edit files outside your worktree.
- **Reports go in commit messages:** subject `WAITING: …` when Andy must try or decide something, then stop, and the hub will message you. Subject `DONE: …` when you're finished: three plain lines for Andy, what isn't verified yet, and anything the hub needs to know to merge.
