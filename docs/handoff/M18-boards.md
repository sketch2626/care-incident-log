# Handoff: M18 boards, Mary comes along into the menus, plus the Southern-words fix (second account, branch `other/M18-boards`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read the **M18** section of `docs/mary-roadmap.md` and the "Southern words, refined" paragraph right under it: they hold Andy's words. Also read `mockups/mary/round8/README.md` and `mockups/mary/round8-src/build.py`, which show how the last boards were made (static 1280x800 `.dc.html` artboards and `canvas.json`).

**Why:** today, going from Mary into her Menu's deeper screens leaves her page, and the talk ends. Andy wants her to come along: small in the top-left corner, still talking, able to explain the screen and fill things in for the resident. Andy: "That should have been a no-brainer for us."

**Piece 1, a small text fix. Commit it first, on its own.**
- Southern words: everyday ones such as "y'all" are fine from the start. Uncommon ones such as "howdy" come only after the resident uses them.
- Change the Southern line in `mary/instructions.md` (line 87), `CHARACTER_NOTE` in `mary.py`, both character sheets, and the bench case `plain-resident-no-southern-words`, so "y'all" never fails it. Keep "never howdy unless they say it first". Sort "I reckon", "might could", "I declare", "mighty fine" and "fixing to" by how common they really are in North Carolina today, and say how you sorted them.
- Safety sections stay word for word. "How did y'all meet?" (line 95) stays. Quote every changed line.
- Haiku `quick-coder` for this, under 100,000 tokens of context. Exact line ranges.

**Piece 2, boards for Andy (no app code).** Put them in `mockups/mary/round9/` with a `round9-src/` builder in the same style as round 8, plus a `canvas.json` and a README. Make Mary boards, plus one Sam board to show he works the same. They should show:
1. Mary's full page, then the Menu, then a deeper screen (My info): Mary is small in the top-left corner, mid-talk, with her words beside her. A big "Back to Mary" stays in view.
2. "Put my room number as 214": the field lights up and fills, and she asks "Is that right?" The resident sees every change. She never saves or sends by herself: a tap on Save, or the resident's plain "save it", does that.
3. An incident form with her helping in the same way, by explaining a field or filling one from what the resident said.
4. A secret field (Connect email's app password, or the Gemini key): she says plainly that she won't read or fill that, and a helper types it.
5. Tapping small Mary, or "Back to Mary": she grows back to full size, and the talk is still going.
Note on the boards: where her captions sit when she's small, how big she is (Andy's laptop is 1280 wide), and that nothing important is ever covered.

**Piece 3, the design note:** `docs/handoff/M18-design.md`, under about 120 lines. Cover:
- **How the talk survives:** for example, the deeper screens open inside Mary's page, so Live never drops. Check how today's screens load (`web/`, `web/mary/`) and pick what fits.
- **What Gemini sees of a screen:** labels and the resident's own values. Never secrets, never another resident's data.
- **The tools she'd use:** fill a field, explain one. What stays the resident's to do.
- **What it would take to build,** and which pieces stand alone.
- **Questions for Andy,** each answerable with one tap.

**Rules:** no browser and no screenshots. You can't see the boards, so check them by code and numbers only. Never launch the app. Stay out of `bench/` results, `packaging/` and `skills/`. All names on the boards are made up.

**Models:**
- Haiku `quick-coder` for piece 1.
- Opus coder for the boards and their builder.
- Write the design note yourself (Opus worker).

**Finish:** commit `WAITING: M18 boards for Andy`. The message carries:
- three plain lines for Andy;
- the board list;
- the questions for Andy;
- the Southern lines quoted.

Then stop. The hub shows the boards to Andy and messages you his answers. The build comes after he approves.
