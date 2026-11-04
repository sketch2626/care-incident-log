# Handoff: M24 boards, round 11a: Mary as a 3D character on her porch (second account, branch `other/M24-boards`)

Rewritten 2026-11-04 to match Andy's redirect and the critic's review (`docs/handoff/done/M24-critique.md`). The worker received both by message; this file is the record.

Read `docs/handoff/_common.md` first, then `docs/decisions.md` (**D7, D12, D13, D16, D18**), then the **M24** section of `docs/mary-roadmap.md`, which has Andy's words. Then look at:
- how Mary is drawn today: `web/mary/face.js` (the `MaryFace` interface), `face.css` and `mary.css`;
- how round 10 was made: `mockups/mary/round10-src/`, and `mockups/mary/round10/canvas.json`.

Read only what you need.

**Why:** Andy, 2026-11-04: "I want it to be three-dimensional. I want it to be visually appealing. Otherwise, nobody's going to want it… I don't want it to be a woman with normal hands either. And not just like a cartoon woman. It needs to be a character of some sort. It don't need to be a childish little character."

**Round 11a is for Andy to pick a character by eye. At most four boards,** in `mockups/mary/round11/`, with `canvas.json` and a README, made the way round 10 was:
1. **Three character concepts for Mary,** each on the same 3D porch swing on a sunny afternoon, with idle motion (sway, blink, breathe):
   - (a) a Southern animal grown folks respect;
   - (b) an honest AI being, warm and hand-made, never a glowing-eyed machine;
   - (c) a creature of your own invention.
   
   All are grown-up characters, not human women.
2. **Talking and listening** on the strongest one.
3. **A 2D still twin of each character:** the SVG fallback for laptops that can't run 3D.
4. **A strip of stills for each character:** listening and asleep. Asleep must look unmistakably different from being awake at night.

**Later, in round 11b, after Andy picks:** weather and time, Sam as a matching character, and the screen states (menu open, side by side with a skill, and a deeper screen with her in the corner as M18 approved).

**How it's made:**
- **Real-time 3D with three.js.** For the boards, load one pinned version from cdnjs. The app will bundle it offline later and never load the CDN.
- **Everything built from shapes in code.** No downloaded models or textures.
- **Grown-up, hand-made finishes:** Southern carved-wood folk art first (whittled, faceted, matte, milk-paint colors), then matte glazed ceramic or a soft painted diorama.
- **Adult proportions,** with the head about a quarter to a fifth of the body. No gloss, big eyes, sparkle catchlights, blush or bouncing.
- **Light enough for an old laptop:** low poly, one light rig, pixel ratio 1, no shadow maps or post-processing, 30 fps at most. Render only while the board is in view, and draw one still frame for thumbnails.
- **Porch details real porches have:** a swing on chains, a haint-blue ceiling, a screen door, ferns, a glass of tea.
- **Original characters only.** No real people or places, and nothing private about Andy (D16).

**Write `docs/handoff/done/M24-design.md`.** For each concept, cover:
- how it's built: its parts, how it talks and listens, and how it looks asleep;
- a frame-rate and memory budget;
- the fallback rule: WebGL with `failIfMajorPerformanceCaveat`, then the 2D twin;
- that it plugs in behind the existing `MaryFace` interface;
- one line on how its identity line in her brain would read;
- which one you'd pick, and why.

**Rules:**
- Touch nothing outside `mockups/mary/round11/`, `mockups/mary/round11-src/` and that design note.
- No app changes, no Gemini calls.
- You can't see renders. The hub checks every board in its built-in browser and sends you fixes before Andy sees them.
- If your context passes about 200K, commit `WAITING: context full`.

**Models (D14):** you draw the characters yourself, because the look is the judgment. Sonnet `coder` does the canvas plumbing and the 2D twins once a character is drawn. Use one fresh helper per piece.

**Finish:** commit `DONE: M24 boards`. The message carries:
- three plain lines for Andy;
- the list of boards and what each should show;
- your pick and why;
- what isn't shown.

Then stop.
