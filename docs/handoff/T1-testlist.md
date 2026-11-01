# Handoff: T1, Andy's tuck-away test list beside Mary (second account, branch `other/T1-testlist`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read only what you need of `desktop.py` (the `--mary` window), `server.py` (how routes and `X-Tracker: 1` work), `web/mary/` (the page, and where the card and picture panels sit beside Mary's face), and `packaging/build.py` (what gets bundled).

**Why:** Mary's window takes the whole screen. While Andy tests a new build, he has to remember everything he's meant to try. Andy: "a list of things… beside or underneath Mary's face just until I get done testing it, and then we can remove it." This is a tool for Andy's own testing, never for residents.

**Build:**
1. **When it shows.** Only when the app runs from source (not frozen) and the file `private/testing/list.md` exists in the project folder (gitignored; the hub writes it). No file, or the installed app: nothing changes at all, not one extra request or element. Removing it later = the hub deletes the file. Never bundle its script in the installer or zip.
2. **The list file** is plain markdown: `# Title`, `## Section` headers, `- item` lines. Show it as written. Re-read it each time Mary's page loads, so the hub can update it between tries.
3. **Where.** A slim tab on the screen edge reading "Test list" that opens a drawer, and closes back to the tab with one tap. It opens at start. It must not cover Mary's face, her captions or the card/picture panel that opens beside her; if the drawer would, it sits on the other side or the face makes room. Pick what fits the layout and say what you chose.
4. **Each item** has two big buttons, "Worked" and "Didn't", that stay lit once tapped (tap again to change), and a small "Note" box (Windows voice typing works there, so a plain text box is enough). The first unmarked item is highlighted, so he sees where he is. A section with every item marked folds to its header with a count.
5. **Results** save at once to `private/testing/results.json`: per item, the section, the mark, the note and the time. Marks survive a restart. A new list keeps marks for items whose text is unchanged. A "Start over" button at the bottom clears marks, with one "Are you sure?" tap.
6. **Never in the way:** tapping the drawer never takes the mic, starts or stops a talk, makes a sound, or reaches Gemini, the incident log or Mary's memories. Text ≥20px, targets ≥64px (his hands are hard to use), plain words, the page's own colors.

**Tests:**
- The routes answer nothing when the file is missing or the app is frozen.
- Results save, survive a reload, and carry over for unchanged items.
- The results route needs `X-Tracker: 1` and never writes outside `private/testing/`.
- Use a temp folder for the list and results; never the real `private/`.
- `node --check` the page script.

**Stay out of:** `bench/`, `tools/brain_bench.py`, `mockups/`, `mary/instructions.md` and `skills/`.

**Models:** Opus coder for the server routes and the drawer; Sonnet coder for the tests.

**Finish:** commit `DONE: T1 test list ready` with three plain lines for Andy, where the drawer sits and why, and what isn't verified (nobody will have seen it on screen). Then stop.
