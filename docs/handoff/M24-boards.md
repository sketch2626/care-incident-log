# Handoff: M24 boards, round 11: Mary and Sam on their porch in 3D (second account, branch `other/M24-boards`)

Rewritten 2026-11-04 after Andy picked the cast from concept lineups. Earlier versions (a cartoon woman, then three test concepts) are retired. The critic's review in `docs/handoff/done/M24-critique.md` still holds where it fits, apart from the points Andy overruled, which are listed below.

**First, merge `main` into your branch** (`git merge main`) to get `mockups/mary/concepts/`, the pictures Andy picked from, and their README. Then read:
- `docs/decisions.md` (**D7, D12, D13, D16, D18**);
- the **M24** and **M25** sections of `docs/mary-roadmap.md`, which have Andy's words;
- `web/mary/face.js` (the `MaryFace` interface).

Your own `round11-src/porch3d.js`, rig and SVG preview pipeline carry over.

**The cast (Andy, 2026-11-04):**
- **Sam:** the second character in `04-lineup-pairs-sam-picked.webp`. A tall 1950s robot in faded, chipped tractor-red enamel over dark steel joints, with a boxy chest, a rectangular head with a kind, weathered face and eyebrows, and an olive feed-store cap. Andy: "that's Sam. Perfect for him."
- **Mary:** the first character in the same picture. A robot from the same factory in robin's-egg blue and cream, with a crocheted shawl. Andy: "that's not bad for Mary… we may make some tweaks later." Build her like the picture. Her face is the most human part, so keep it clearly a robot's face, kind and expressive with eyebrows, because human-like faces turn uncanny fastest in simple 3D. Her voice comes from a soft mouth shape or a glowing grille, never a hinged jaw.
- **Pets:** Mary's gray cat and Sam's old hound, both from the same picture, settled near the swing.
- **The lantern:** the one in `04-…` (its gentle face), hanging from the porch ceiling above the swing. It glows when the companion is listening and dims when they're asleep. Andy: "for indications… and two just because it's cool."
- **The radio:** the wooden radio, far right in `03-lineup-six.webp`, sitting on a small side table on the left. It keeps its friendly face, lit when it plays. No arms or legs needed on the table.

**The scene (Andy's words):** "I want them sitting on a porch swing and I want the porch swing facing us directly. And then the yard and the background and the stuff back behind them and then like a little side table over to the left that has the radio on it and then it all turns in and moves over a little for bringing other things up onto the screen."

**Boards** in `mockups/mary/round11/`, with `canvas.json` and a README saying in words what each board should show. At most five:
1. **Mary on the swing,** facing us, on a sunny afternoon: idle motion (sway, blink, breathe), then talking. The cat, the lantern and the radio table are in place.
2. **Sam the same way,** with the hound.
3. **The weather and time, from the start** (Andy: "this is an old people app, so the weather needs to be included from the get-go"): morning, rain, a thunderstorm, dusk with the lantern lit, and night. Snow too, if there's room.
   - Lightning is a soft glow in the clouds, a few seconds apart, never a strobe (no more than three flashes a second).
   - Thunder stays quiet. The boards have no sound, so just note it.
4. **Listening and asleep:** the lantern's glow, her posture, and how asleep at night differs unmistakably from awake at night.
5. **"It all turns in and moves over":** the scene turns and slides aside as a camera move, with a screen open next to it and "Back to Mary" in view (D13). Note in the README that Andy might later want them to stand up off the porch instead.

**How it's made:**
- three.js r128 from cdnjs for the boards only. The app bundles it later.
- Shapes in code, with no downloaded models or textures.
- Worn enamel over steel for the robots, with the critic's grown-up rules: adult proportions, no gloss, no big shiny eyes, no blush, no bouncing.
- Low poly, one light rig, pixel ratio 1, 30 fps at most. Render only while a board is in view, and draw one still frame for thumbnails.

**Andy overruled two of the critic's points:**
- The laptop's memory is less of a worry, because residents' laptops will be locked down to Mary. So no 2D twins on the boards; the fallback stays in the build plan only.
- The weather is included from the start, with lightning.

**Check your own renders** with your SVG preview pipeline, and look at every board before you finish. The hub then opens each one in its built-in browser and sends fixes before Andy sees them.

**Write `docs/handoff/done/M24-design.md`:**
- how Mary, Sam, the pets, the lantern and the radio are built;
- how talking, listening and asleep work;
- how the weather and time change;
- the frame-rate and memory budget;
- how it plugs in behind `MaryFace`.

**Rules:**
- Touch nothing outside `mockups/mary/round11/`, `mockups/mary/round11-src/` and that design note.
- No app changes, no Gemini calls.
- If your context passes about 200K, commit `WAITING: context full`.

**Models (D14):** you draw Mary and Sam yourself. Sonnet `coder` does the canvas plumbing and repeat work, like the weather versions, with one fresh helper per piece.

**Finish:** commit `DONE: M24 boards`. The message carries:
- three plain lines for Andy;
- the boards and what each should show;
- what you couldn't get right;
- what isn't shown.

Then stop.
