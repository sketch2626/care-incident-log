# Handoff: M24 scene, round 2: Andy's fixes and a new face (second account, branch `other/M24-scene`)

You continue the scene a first worker built. Its context filled up, but the work is all committed. First run `git merge main` to get this brief, then read:
- `mockups/mary/round12/NOTES.md`: the files, the query switches, what's been checked, and the steps still to do;
- `docs/handoff/M24-scene.md`: the original brief, Andy's scene in his words, and how to render your own pictures with headless Edge;
- `mockups/mary/concepts/README.md`, then look at `04-lineup-pairs-sam-picked.webp`. **Mary is the first character there.**

**Andy, on seeing the first round (2026-11-04):** "Camera needs to be more in the center, the swing up against the house that's not going to work. Obviously her face needs to be completely overhauled. That doesn't look nothing like the picture. And it's just kind of weird looking. And we need to be able to see off… more in the middle, and you can see a little bit of the yard out that way."

**Andy, correcting that a minute later:** "the chain of the swing is up against the house. So that's not going to work. And maybe we should put the little table in the radio on the left-hand side up against the house. That way her left hand controls the radio and her right hand can point at stuff that's going to be on the screen on the other side. And still, I feel like it needs to be closer in too still." He means the hand on the left of the screen tunes the radio (her own right hand, since she faces us), and the hand on the right of the screen points toward where screens open.

**What works and stays:** the film lighting (sun, fills, GTAO, bloom, the grade), the painted textures, the haint-blue ceiling, the chains, the walnut radio with its glowing dial, and the crochet shawl and brooch.

**Do, in this order:**
1. **The layout.**
   - **Center the camera on the swing,** and move the swing out to the middle of the porch, so no chain comes near the house wall.
   - **Closer in than round 1,** so she fills more of the frame.
   - **Open the middle of the view:** beyond the railing, the yard shows through the center and off to the viewer's right. Show some of it, not a vast landscape.
   - **Keep a slice of the house** at the viewer's left edge, with the radio table up against it.
   - **Her right hand** reaches over to tune the radio, and **her left arm** points loosely toward the viewer's right, where screens will open. Andy: screens open on the same side as always, and the porch scene just takes the face's place.
2. **Her face, fully redone to look like the picture.** Today it's a human mask in a helmet: a sculpted nose, colored lips, and a wide stare. That's the "weird" part. Match concept 04's Mary instead:
   - a smooth, calm, gentle face inside her robin's-egg-blue bob;
   - soft almond eyes with lids, relaxed and warm, never staring;
   - gentle brows;
   - a small, kind closed smile that can open softly to talk;
   - no more than a faint hint of a nose, the way the picture has it.

   She should look like an appealing character from a warm animated film. Render the face close-up after every change, and compare it with the picture until it reads as her.
3. **The motion:** check the talk, radio-reach and point poses and fix them, starting with the hands and the IK, as NOTES.md says.
4. **Then NOTES.md's other steps:** the shawl should wrap her upper arms, the trees should be rounder and irregular, and check the live loop runs smoothly.

**Rules:**
- Touch only `mockups/mary/round12/` and `docs/handoff/done/M24-scene.md`.
- No app changes, no Gemini calls.
- If your context passes about 200K, commit `WAITING: context full`, with NOTES.md updated first.
- NOTES.md holds facts and task state only, never rules (Andy, 2026-11-04).

**Models:** you do all of it yourself, at extra-high effort, with no helpers.

**Finish:** commit `DONE: M24 scene`. The message carries:
- three plain lines for Andy;
- which shots you checked;
- what's still not right.

Then stop.
