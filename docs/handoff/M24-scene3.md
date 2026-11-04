# Handoff: M24 scene, round 3: closer, fuller, evening light and the lantern (second account, branch `other/M24-scene`)

You continue the porch scene. Run `git merge main` first, then read:
- `mockups/mary/round12/NOTES.md`: the files, the query switches, the render recipe (a fresh Edge profile for each render), and what's still open;
- `docs/handoff/done/M24-scene2.md`: Andy's layout and his words;
- `mockups/mary/concepts/README.md`, then look at `04-lineup-pairs-sam-picked.webp` for Mary and the lantern.

**Where it stands:** round 2 has Andy's layout, a cartoon face from concept 04, a painted style and film lighting. Andy saw it and said: "I like your recommendations. Let's start pushing in that direction. Let's make it a little bit later in the evening for these initial renders… Where it's not so bright and stuff, and you forgot the lantern. We need the lantern."

**Do, in this order:**
1. **Closer.** She's too small, with too much empty sky above her. Frame her so she fills most of the height: from just above the lantern down to the swing seat, with her face clearly readable from across a room. Keep the radio table on the left and some yard showing through the middle.
2. **Later in the evening.** Late golden hour moving toward dusk: a lower, warmer sun, a softer and less bright sky, and longer, gentler shadows. Keep the film quality, just calmer. The radio's glow and the lantern should start to show against it.
3. **The lantern.** The lantern from concept 04, with its gentle face, hangs from the porch ceiling near the swing, above her and to one side. Keep it in frame and softly lit, with a warm glow that reaches the swing. It will later show when she's listening (brighter, a gentle pulse) and asleep (dim). Give it a `?lantern=listen|asleep|off` switch now, so those can be checked.
4. **Her body: fuller, softer, less mannequin.** Today it's thin stick arms on a stiff torso. Make her body rounder and fuller, like concept 04: soft, rounded enamel forms, sturdier arms with friendly robot joints, and relaxed shoulders. Keep it grown-up, never childish.
5. **The shawl: soft crochet that drapes.** Today it hangs like a stiff cape with a feathery texture, and the pointing arm lifts it into a wing. Make it soft cream crochet resting over her shoulders and upper arms, falling with gravity, so it moves with her instead of standing out.
6. **The yellow cushion:** today it's a flat block that pulls the eye. Remove it, or make it a small, soft, patterned pillow that sits back.
7. **The trees:** lighter and rounder, less dark and lumpy. In evening light they can sit back in soft haze.

After each step, render and look: the main shot, the face close-up, and the radio and point poses. Render the lantern states too. Judge each one as Andy would: is she someone you'd want to sit with?

**Rules:**
- Touch only `mockups/mary/round12/` and `docs/handoff/done/M24-scene.md`.
- No app changes, no Gemini calls, and nothing about her brain (it's parked until the paid model, D26).
- NOTES.md holds facts and task state only, never rules.
- If your context passes about 200K, commit `WAITING: context full`, with NOTES.md updated first.

**Models:** you do all of it yourself, at extra-high effort, with no helpers.

**Finish:** commit `DONE: M24 scene round 3`. The message carries:
- three plain lines for Andy;
- which shots you checked;
- what's still not right.

Then stop.
