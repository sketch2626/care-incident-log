# Handoff: repo1, the repo becomes "Mary's Porch" (second account, branch `other/repo1`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md` and `docs/decisions.md`). Then read `README.md`, `docs/companion-plan.md`, the top of `docs/mary-roadmap.md` and `docs/status.md` "Right now". Read only what you need of the code, to check what you write.

**Why:** Andy (2026-11-02): "in the repo… there's no mention of Mary at all, or how this app works… the readmes over there are all about the care incident log." The project is now **Mary's Porch**, so it's easy to search for (other products are called "Mary"). A fundraising effort will send people to the repo, so the front page has to tell the truth about what this is, and do it well.

**Do:**
1. **A new `README.md` for Mary's Porch.** It's the front page for people arriving from Hacker News, X and AI companies, and for developers. Include:
   - **What it is, in the first lines** (plain words, good search words):
     - an open-source AI companion for nursing-home residents: Mary (and Sam), friendship first;
     - built in, help speaking up about care problems: the resident talks naturally, and the app makes a formal, dated record for the long-term care ombudsman and state inspectors;
     - it runs on the resident's own Windows laptop.
   - **Who made it and why:** built by voice, with AI, by a paralyzed nursing-home resident in North Carolina. Use `docs/mission.md`'s public framing. "This is what AI is for." No other personal facts.
   - **What she does today**, checked against the code: talk modes (Normal, Live, Offline), voices, the speak-up log and state reports, cards and messages, email, the address book, word search, skills. Say plainly what's beta and what isn't built.
   - **Status:** beta v0.5.0. Her conversation is being rebuilt (M21) after testing found her talking down to people.
   - **Privacy and safety, in plain words:** local first; the resident's own Gemini key; on-device speech; secrets in Windows Credential Manager; the locked address book; what leaves the laptop and when; how safety rules are kept (`docs/decisions.md`).
   - **Install** (the Windows installer and building it), **for developers** (layout, run, tests, skills), the roadmap, contributing, the license.
2. **Index the folders:** short `README.md` files for `docs/`, `bench/`, `mockups/`, `skills/` and `tools/` where missing, saying what's inside and what's current versus history.
3. **Tidy the docs, carefully:**
   - Move superseded docs to `docs/archive/` with a line saying why.
   - Move finished handoff briefs to `docs/handoff/done/`. Leave `_common.md`, `M21a.md` and this brief where they are.
   - Delete only what is clearly dead and unreferenced. When unsure, archive it instead.
   - List every move and deletion in your report.
4. **Fix links:** relative links wherever possible. Where an absolute link is needed, use `https://github.com/sketch2626/marys-porch` (the hub renames the repo before publishing).
5. **A privacy sweep of tracked files.** Look for private facts: Andy's health beyond "paralyzed nursing-home resident", his email, real names of residents or staff, the facility's name, money or benefits. **Report them; don't rewrite git history.** Fix only plain doc text that you can reword safely.
6. **Suggest the GitHub "About" text:** a one-line description (under 350 characters) and 8-12 topics, in your report. The hub sets them.

**Don't touch** (another worker, M21a, is changing code right now):
- any `.py` or `.js` file, `tests/`, `web/`, `skills/` code, `packaging/`;
- `CLAUDE.md`, `docs/decisions.md`, `docs/status.md`, `docs/mary-roadmap.md` (the hub's);
- `private/`.

Instead, list in your report:
- **code cleanup for after M21a merges:** dead files such as `speedcheck.py`, if it is, and any folder moves you'd suggest;
- **every place a product rename would touch** (window titles, installer names, shortcuts "Mary" and "Care Incident Log"). Renaming the app itself is Andy's later call. This job is the repo and its docs.

**Rules:** everything you write must be true today, checked in the code or docs. Don't make up features. Plain words, Andy's spirit (`docs/mission.md`). Scratch data only, no browser.

**Models (D14):** you write the README's outline and its key sentences yourself. Sonnet `coder` drafts sections and the folder indexes, one fresh helper per piece. Haiku `quick-coder` only for small text files, under its limits. Commit after each piece.

**Finish:** commit `DONE: repo1 Mary's Porch front page and tidy`. The message carries:
- three plain lines for Andy;
- the moves and deletions;
- the privacy findings;
- the suggested About text and topics;
- the code-cleanup and product-rename lists;
- anything unverified.

Then stop.
