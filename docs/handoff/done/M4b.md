# Handoff: M4b, bubble captions and the one-button screen (second account, branch `other/M4b`)

Read `docs/handoff/_common.md` first. Then read only these:
- **"Build list for M4b"** and **"Notes for the builder (M4)"** in `mockups/mary/round6/README.md`. This is your spec, approved by Andy on 2026-10-30.
- The board files it names in `mockups/mary/round6/`, plus `r6.css`.
- In `web/mary/`: `app.js` (`showCaption()`, which M4a left for you, and the menu code), `mary.html`, `mary.css`, `face.js`, `face.css` and `skills.js` (`addMenuButton`).
- In `docs/mary-roadmap.md`: M3, M4a and M4b.

**Andy approved (2026-10-30):**
- Caption style A, the coloring-in bubble letters.
- Listening: the ear waves, with no "I'm listening" bar and no words.
- Thinking: the thought cloud with "Thinking…", version (b).
- The top-right Menu, exactly as drawn.
- The emergency screen.

**Andy's findings to fix here (2026-10-30), after trying M4a:**
- **"The menu hasn't been changed."** Build the approved menu: Talk to Mary, Things Mary can do, My info, Choose Mary or Sam, Games (Coming soon), Close Mary. The names follow the companion.
- **Remove the big Slower / Faster / Quieter / Louder buttons from the menu** (Andy: "they don't need to be in the menu"), and the skills' menu buttons too.
  - They work by voice.
  - List them under **"Things Mary can do"** as things to say ("Say: slow down"), with a tap there doing the same thing.
- **"There was no options for me to switch anything."** "My info" in Mary's menu must open the settings from inside her screen, with a big "Back to Mary": "How Mary talks" (Live, Normal or Offline), her voice, her wait time, and switching skills on and off. It can be a simple panel in her screen, or the main app's My info screen with a return button. Use your judgment, but no tiny controls.
- **Nothing is dropped.** "Type to Mary" and "My notes" move into "Things Mary can do" (or My info). "Switch to Sam" becomes "Choose Mary or Sam".

**How:**
- Replace `showCaption()` with the style A captions. Use the timing rules in the builder notes: playback clock, Live text pieces re-anchored, Normal and Offline a sentence at a time.
- Add the listening, thinking, menu-open and emergency states to the existing face (`face.js`/`face.css`) as mood classes on the screen. Don't make a second face.
- The ear waves turn `.loud` while the mic level is up: in Live, from the page mic level; in Normal, from `/api/listen/level`.
- Bundle the Fredoka 600 font locally so it works offline. Check its license (OFL) and note it.
- Text ≥20px, targets ≥64px, plain words. Respect reduced motion.

**Other worktrees:**
- M4a (`other/M4a`) is fixing Live's brain in `voices.py`, `mary/instructions.md` and maybe the memory parts of `server.py`/`app.js`.
- M6 (wake word, Stage 2 later) will hook `startTalk()` and use your listening state.

Stay out of their files where you can, and keep your `app.js` changes in blocks marked `M4b`.

**Tests:**
- Server tests for any route you add.
- `node --check` on every changed script.
- A small page-logic test of the word-timing estimate, if you can run it with Node.

**Models:**
- Opus xhigh: the caption timing and word fill, and the state wiring in `app.js`.
- Opus: the menu, My info panel and face states.
- Sonnet: the tests.
- Haiku: text-only edits.

**Finish:** Andy has to see it, so commit `WAITING: M4b captions and menu ready for Andy to try` and stop. The hub merges and opens Mary for him. After his fixes, commit `DONE: M4b captions and menu`.
