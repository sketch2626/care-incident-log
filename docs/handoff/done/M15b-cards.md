# Handoff: M15b, making the cards (second account, branch `other/M15b-cards`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read:
- `docs/messaging-plan.md`: "Making a card", "The look", "Voice first" and "A plain message" (section 3), the M15b row of the build list (section 8), and the decisions in section 9;
- the boards Andy approved: `mockups/mary/round8/README.md` (every board, her lines, and the buttons kept and why), then `A-Reminder-Mary`, `B-Design-Mary`, `C-Card-Mary`, `C3-Opens-Mary`, `C2-Inside-Mary`, `C4-Plain-Mary` and `G-Message-Mary`;
- `mockups/mary/round8-src/build.py`, where the painted fronts and the card layout are drawn (reuse that art);
- `docs/how-to-make-a-skill.md` and `docs/skills-design.md`, with `skills/word_search/` as the example of a skill with a screen;
- M15a's reminder hook (`memory_dates.py`, and where the reminder note offers a card when a `messages` skill is installed).

**Why:** this is the heart of cards and messages, which Andy approved (all 12 recommendations, and the round 8 boards: "much better"). A resident says "let's make Mark a birthday card", and Mary makes a real, grown-up card with them by voice.

**Build the `messages` skill (`skills/messages/`):**
1. **Choosing a front (board B).**
   - Three or four painted fronts that suit the person and the occasion, each with a big number and a short name, so they can say "the second one" or "the one with the lake". One big tap on a card also works.
   - Draw 12 fronts in all, in the round 8 painted style: birthdays first, then get-well, sympathy, thank-you (staff included) and a few holidays.
   - Grown up and traditional: heavy cream paper, deep muted colors, classic lettering, painted scenes. No cartoons, balloons, confetti or clip art.
   - Don't offer "made to order" yet. Picture making is M15f.
2. **The words.** They say what they want. She helps only if they ask, in their voice, never hers. She adds no feeling they didn't express, and she reads it back. Changes are made by voice, at any time.
3. **The folded card (boards C, C3, C2, C4).**
   - A front that opens by itself to show the inside (the C3 animation).
   - Inside: a short printed verse in a classic typeface, and under it their own words in handwriting, signed with their name.
   - Two handwriting styles: cursive, and plain for anyone who finds cursive hard to read ("I can write it plainer").
   - Long words and long messages must fit: shrink the type within limits, then wrap. Never cut a word off.
4. **Saved on the laptop.** Every card is saved as pictures in the data folder (under `TRACKER_DATA` in tests): the front, the inside, and one picture of both side by side (Andy approved sending it as one picture). They must work offline, with the fonts embedded in the drawing.
5. **Print.** A printable folded card on one letter page, with a fold line. Marked as needing facility help for the mailing.
6. **A plain message (board G).** "Help me send a message to my grandson" shows their words on cream paper, with no design step.
7. **No sending yet.** Contacts, the five-second Undo and email are M15c and M15d. On "send it" for now, she says plainly that sending isn't set up yet, that the card is saved, and offers to print it.
8. **The reminder (board A).** When M15a's reminder comes up and this skill is installed, she offers a card in her own words, and the keepsake reminder screen from board A can show, with the monogram in the photo frame.
9. **Voice first.** No question-and-answer buttons, no who-gets-it list, no Back or Next. Keep a button only where the round 8 README gives a reason. If the person is unclear ("my grandson", with two grandsons), she asks aloud. Text ≥20px, targets ≥64px.

**Fonts (Andy approved the download, 2026-10-31: "Yes, download them"):**
- Get the five open-license Google Fonts the boards use: Pinyon Script, Cedarville Cursive, Kalam, EB Garamond and Cinzel. Take only the weights the boards use, in latin and latin-ext `.woff2`, and add each family's OFL license text.
- Put them in `web/mary/fonts/` with `fonts.css`, the way M4b bundled Fredoka (commit 6e74f69).
- Download the font files only, from Google Fonts' own servers. Nothing else, and no `pip install`.

**Tests** use fake Gemini and scratch data:
- `tests/test_skills_contract.py` passes;
- the tools flow: pick, words, change, plainer, read back, save, print;
- long words and long messages fit;
- the pictures are saved under the scratch data folder;
- "send it" doesn't send;
- the card offer appears only when the skill is installed.

Run `node --check` on every page script you touch.

**Memory is tight** on this 5.7 GB laptop. If a test run is stopped for memory, wait a few minutes and retry once. Then report it.

**This is a big job.** Keep your own context lean: helpers do the reading and writing, and you review diffs. Commit after each piece. If your context passes about 200K, commit `WAITING: context full` with the pieces done and the pieces left, so the hub can start a fresh worker.

**Stay out of:** `bench/`, `tools/brain_bench.py`, `packaging/` and `mockups/` (read them only). The safety sections of `mary/instructions.md` stay word for word.

**Models:**
- Opus coder, `effort: "xhigh"`: the card drawing, the fitting and the saved pictures.
- Opus coder: the skill's tools and screen.
- Sonnet coder: the tests.

**Finish:** commit `WAITING: M15b cards ready for Andy to try`, because Andy approves the look. Include:
- three plain lines for Andy;
- how he can try it in the app (what to say to Mary);
- what isn't verified;
- anything the hub needs to merge.

Then stop.
