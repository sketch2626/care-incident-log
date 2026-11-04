# Handoff: M24 boards, Mary on her porch (second account, branch `other/M24-boards`)

Read `docs/handoff/_common.md` first, then `docs/decisions.md` (**D7, D12, D13, D16**), then the **M24** section of `docs/mary-roadmap.md`, which has Andy's words. Then look at:
- how Mary is drawn today: `web/mary/face.js`, `face.css`, `mary.css`, and her moods;
- how round 10 was made: `mockups/mary/round10-src/`, and `mockups/mary/round10/canvas.json`.

Read only what you need.

**Why:** Andy, 2026-11-04: "Let's make this look really cool… she's sitting on a porch swing and the weather in the background… matches the actual weather of the day… she needs more of a body then instead of just floating eyes… some kind of cartoony thing." The app's name is Mary's Porch.

**This round is for Andy to pick a look by eye, so make it few and good.** He judges by looking. How good the drawing is matters far more than how many boards there are.

**Boards** in `mockups/mary/round11/`, with `canvas.json` and a README, made the way round 10 was:
1. **Three styles of one scene,** one board each: Mary on a porch swing, centered, with a sunny afternoon behind her and the porch around her. For example:
   - (a) clean flat shapes with soft shading;
   - (b) a warm storybook look;
   - (c) soft and rounded, almost like clay.

   All three are grown-up, never a kids' show (D7). She's a warm woman who seems 60 to 65, with a whole body, hands, and a face that clearly talks and listens. Not floating eyes.
2. **Weather and time in each style:** a strip under each scene, or a second board per style. Show the same porch in the morning, in rain, at dusk with the porch light on, and at night. Add snow and fall leaves if there's room.
3. **Sam,** in the style you think is strongest, with a spot of his own. That could be a rocking chair on the same porch, or a place of his own, like a truck tailgate by a pond. Show both if they're cheap.
4. **She moves left:** one board with a screen open (round 10's address book). The porch scene sits on the left, and Mary is still alive on her swing. "Back to Mary" stays in view (D13).
5. **Gentle motion** in each board: the swing's slow sway, blinking and breathing, plus a talking mouth on one board. Keep it calm, never flashing.

**Rules for the drawing:**
- **Original art only.** Don't copy any existing character, mascot or brand look.
- **It has to run in the app later:** SVG and CSS, offline, and light enough for an old laptop short on memory. No images from the internet and no heavy libraries.
- **Big and clear for residents 65 to 95:** strong shapes, good contrast, and nothing busy behind her face.
- **The porch details real porches have,** not a theme park: a swing on chains, a haint-blue ceiling, a screen door, ferns, a glass of tea. Plain, not cutesy.
- **No real people or places,** and nothing private about Andy (D16).

**Write `docs/handoff/done/M24-design.md`.** For each style, cover:
- how it would be built: its SVG parts, how she talks and listens, and how the weather changes;
- what it costs to run;
- which one you'd pick, and why.

**Rules:**
- Touch nothing outside `mockups/mary/round11/`, `mockups/mary/round11-src/` and that design note.
- No app changes, no Gemini calls, no browser.
- If your context passes about 200K, commit `WAITING: context full`.

**Models (D14):** you draw the three main scenes yourself, because the look is the judgment. Sonnet `coder` does the canvas plumbing and the repeat work, like the weather versions once a scene is drawn. Use one fresh helper per piece.

**Finish:** commit `DONE: M24 boards`. The message carries:
- three plain lines for Andy;
- the list of boards;
- your pick and why;
- what isn't shown.

Then stop.
