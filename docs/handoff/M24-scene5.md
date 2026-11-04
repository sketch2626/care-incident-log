# Handoff: M24 scene, round 5: no glare on her face, a darker mood, and a calmer day (second account, branch `other/M24-scene`)

You continue the porch scene. Run `git merge main` first, then read:
- `mockups/mary/round12/NOTES.md`: the files, the switches, the render recipe, and what's still open;
- `docs/handoff/done/M24-scene4.md`: the last round.

**Andy, on round 4 (2026-11-04):** "you're definitely right about the night shot. And when I pictured this in my head the whole time, for some reason, I always seen it kind of being dark around the background and stuff… We're going to have to obviously do daytime… can still be less bright. But yeah, I like this. I think that the point of light, that's right on her eye, might be a little too much. It's extremely reflective right there. I mean, I know that… the light has to have a point on her head somewhere, but it's kind of off-putting a little bit."

**The night shot is the look Andy likes. Keep it, and build the rest toward it.**

**Do, in this order:**
1. **No glare on her face.** The hard, bright highlight near her eye is off-putting and reads as plastic. Make her face plate matte (higher roughness, little or no clearcoat), so light rolls across it softly. Keep a gentle sheen on her helmet and enamel, away from her eyes. Check the night face, the evening face and the main shots. No hot spot should sit on or beside her eyes.
2. **A darker mood around her.** The background stays deep and quiet in every time of day, so she and the lantern are the brightest, warmest things in the frame. A soft vignette is fine.
3. **A calmer day, `?time=day`.** A daytime version that isn't bright: soft, overcast or late-afternoon light, muted greens, a gentle sky, and the porch in shade. It should feel as calm as the night shot. Keep the evening view as it is now.
4. **The leftovers from round 4:**
   - the house siding shows faintly through the lantern glass;
   - asleep, her head should tip down a little more;
   - the stars could be a touch brighter;
   - the lantern's face should be readable at a glance;
   - re-check the radio and point poses with the lantern in its new place.

**Memory:** the laptop ran low last round. Render one shot at a time with a fresh Edge profile, delete each profile after its shot, and keep no more than one server running.

**Rules:**
- Touch only `mockups/mary/round12/` and `docs/handoff/done/M24-scene.md`.
- No app changes, no Gemini calls, and nothing about her brain (D26).
- NOTES.md holds facts and task state only, never rules.
- If your context passes about 200K, commit `WAITING: context full`, with NOTES.md updated first.

**Models:** you do all of it yourself, at extra-high effort, with no helpers.

**Finish:** commit `DONE: M24 scene round 5`. The message carries:
- three plain lines for Andy;
- which shots you checked;
- what's still not right.

Then stop.
