# Handoff: M24 scene, round 4: a real lantern, a softer radio, and full night (second account, branch `other/M24-scene`)

You continue the porch scene. Run `git merge main` first, then read:
- `mockups/mary/round12/NOTES.md`: the files, the switches, the render recipe (a fresh Edge profile for each render), and what's still open;
- `docs/handoff/done/M24-scene3.md`: the last round.

Look at the lantern in `mockups/mary/concepts/04-lineup-pairs-sam-picked.webp` (hanging above the row).

**Andy, on round 3 (2026-11-04):** "the lantern looks like a lemon drop head on the inside of a frame. So that doesn't work. We also need to cut down the amount of brightness inside the radio. The radio dial area is extremely bright. We also need to see what it looks like when it's dark completely. Outside, and then, you know, illuminated by the lamp. And we will go from there."

**Do, in this order:**
1. **A real lantern.** Today it's a glowing, lemon-shaped head with a face, set in a frame. Make it read first as an old porch lantern: a metal cap and bail, a glass globe or chimney inside a wire guard, and a warm flame or glow inside the glass. Keep a gentle face, as in concept 04, but make it part of the lantern: soft features in the glass or on the glow, not a separate head inside it. Keep its `?lantern=listen|asleep|off` switch working.
2. **The radio's glow, much softer.** The dial area is far too bright. Turn it down to a warm, low glow that reads as an old radio at night, not a lamp. No bloom blowing out its face.
3. **Full night: a new `?time=night` view.**
   - The yard is dark: a deep night sky, maybe a moon, and the trees as soft dark shapes.
   - The porch is lit mainly by the lantern: a warm pool of light on Mary and the swing, falling off into shadow, with the radio's small glow as a second warm spot.
   - It has to look cozy and safe, not spooky. Her face stays readable in the lantern light.
   - Render the night main shot and the night face close-up, and both lantern states at night.
4. **Asleep means Mary too.** In round 3, the asleep switch dimmed only the lantern, and Mary's eyes stayed open. When she's asleep, her eyes close, her head tips down a little, and the radio's glow fades. Make the asleep lantern clearly dimmer, so it reads from across a room. Check it in the evening and at night.

Render and look after each step. Judge each shot the way Andy would.

**Rules:**
- Touch only `mockups/mary/round12/` and `docs/handoff/done/M24-scene.md`.
- No app changes, no Gemini calls, and nothing about her brain (D26).
- NOTES.md holds facts and task state only, never rules.
- If your context passes about 200K, commit `WAITING: context full`, with NOTES.md updated first.

**Models:** you do all of it yourself, at extra-high effort, with no helpers.

**Finish:** commit `DONE: M24 scene round 4`. The message carries:
- three plain lines for Andy;
- which shots you checked;
- what's still not right.

Then stop.
