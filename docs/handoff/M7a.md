# Handoff: M7a, word search with Mary (second account, branch `other/M7a`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read only these:
- `docs/companion-plan.md`, "Games with Mary".
- `docs/mary-roadmap.md`: M7, M12 (including the rule every game follows) and M13.
- `docs/skills-design.md`, `docs/how-to-make-a-skill.md`, and `skills/pictures/` as the example of a skill with a screen. Its manifest has a new `vision` field that the docs don't list yet; add it to both docs.
- In `web/mary/`: `skills.js` (`register(name, {aside: true})`, M4b's slide-aside mode) and the round 6 boards with `r6.css` in `mockups/mary/round6/`, for the look.

**Andy's idea (2026-10-25):** Mary suggests a game, scoots aside and helps the resident play. Word search comes first, because so many older people love them. Andy chose the slide-aside layout (Mary big and alive, turned toward the game in 3D, glancing between the game and the person) over shrinking her into a corner. That layout is built now, and pictures use it.

**Step 1: boards first.** Andy approves the look before anything ships.
- Make `mockups/mary/round7/`, using the round 6 style (one HTML file per board plus a shared CSS):
  - (a) Mary aside with a fresh puzzle;
  - (b) the moment a word is found;
  - (c) a hint;
  - (d) the puzzle finished.
- Design rules:
  - Huge letters, high contrast, no timers and no pressure, gentle wins.
  - Found words get a clear mark, plus a crossed-off list beside the grid.
  - Text 20px or larger, targets 64px or larger.
- The hub puts the boards on Andy's design canvas.

**Step 2: build the skill**, so it's ready the moment he approves:
- **`skills/word_search/`:** a puzzle generator with grid sizes about 8x8 to 12x12 (default 10x10).
  - Words go across and down only at first; diagonal and backward are settings.
  - Themes come from the resident's interests (the memory core's `recall`) or a topic they name.
  - Offline word lists cover common themes (fishing, gardening, church, cooking, trucks, birds, North Carolina, holidays). Gemini only adds variety when online.
- **Play:**
  - Tap the first and last letter of a word, or tap letters in a row.
  - By voice: "I found barn", "give me a hint" (first a gentle hint like "it's in the third row", then the first letter lights up, and last "show me where"), "new puzzle", "make it easier" or "harder", and "I'm done".
- **Mary's part:**
  - She enjoys it the way a friend would, never cheers like a children's show, and never narrates the screen (see the mission doc).
  - She never solves it unless asked.
  - Her tools: start, hint, check, show, end.
  - The emergency check still runs first on everything said.
- **Menu:** "Games" stops saying "Coming soon" and lists Word search. Tic-tac-toe, solitaire and the crossword come later, each with its own brief.
- **Rules:** voice first, no key combos, and reduced motion respected.

**Others working now:** M9c (memory core, "truly forget") in `memory_core.py`, `server.py` and `app.js`. Keep your `app.js` changes in blocks marked `M7a`, and stay in `skills/word_search/` as much as you can.

**Tests:**
- The generator: every word is placed, readable and within the grid.
- The skill contract (`tests/test_skills_contract.py`).
- Hint order, plus check and show.
- `node --check` on every script.

**Models:** Opus for the generator, skill and screen (xhigh for the screen's tap-and-voice play); Sonnet for the tests and word lists; Haiku for doc wording.

**Finish:** commit `WAITING: M7a word search boards and build ready for Andy` and stop. The body lists the board files for the hub's canvas. The hub merges only after Andy approves the boards, and any look changes he asks for come back to you.
