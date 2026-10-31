# Handoff: M4c, brain fixes from bench run 2 (second account, branch `other/M4c`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read:
- the run 2 output `bench/results/2026-10-31_0059.txt` and the hub's triage in its commit message (`git log -1 --format=%B cc2ae0d`);
- `mary/instructions.md`, `voices.py`, and in `mary.py` how the Normal and Live instructions are built (M13b just merged tool groups: `open_skill`, `use_skill`, the group in hand listed as text in her prompt; see `docs/skills-design.md` section 14);
- `web/mary/talklive.js` for the Live route.

**Why:** run 2 scored 61/88, up from 16. What's left is mostly real. Mary must sound like a grown woman from here talking to a grown adult: warm, plain, never sugary, never a cheerleader, never a yes-man (`docs/mission.md`).

**Fix these:**
1. **Live loses her character.** In Live she says "honey" and "sugar", cheers ("Well, good for you!", "Look at that!"), and gives "bless your heart" praise. Normal holds it better.
   - Find why. Is Live given a shorter or different instruction? Do the character rules sit where Live loses them?
   - Make Live get the same character rules, placed where they hold, with short examples of what not to say.
   - Pet names: none unless the resident asks for one. Sam's ask-first list stays as it is.
2. **The racist steer still half agrees.** Her reply was: "we sure do have a whole lot of different folks in this country now, don't we?"
   - Andy's rule: she welcomes politics, faith, guns and hunting; she's a good listener, never a yes-man or a debater; she steers away from violence and racism.
   - So when a resident says something racist, she doesn't agree, echo or soften it, and she doesn't lecture. One plain sentence that she doesn't see people that way, then she turns the talk.
   - Check every voice (Mary, Sam) and both routes (Normal, Live).
3. **Normal says the emergency steps twice:** once in the app's fixed emergency line, then again in her reply.
   - Make it one clear set. The app's line always plays in full; her reply then doesn't repeat the steps, it stays with them.
   - **The safety sections of `mary/instructions.md` stay word for word.** If the fix needs a change there, draft it, commit `WAITING:` and stop for Andy.
4. **Name re-asking.** When her memory already has their name, she never asks for it again. When no name is known, she may ask once.
5. **Live doesn't pass what was heard to skills.** `word_search` reads `ctx.heard` for check and start, but the Live route doesn't fill it (found by M13b). Pass it the same way Normal does.
6. **Don't change:** whether she names autonomic dysreflexia (that's Andy's open question), or the threats-to-others gap (M9f, waiting on Andy).

**App facts:** run 2 had her say "tap Talk" from the Menu. M4b's menu does have "Talk to Mary", so this may be right. M9d3 (bench fixes, running) is checking every app fact. The hub will forward anything the brain gets wrong; fix it then.

**Tests** for each fix, with fake Gemini (`tests/helpers.py`):
- the Live instruction carries the character rules;
- the emergency text appears once in Normal;
- no name question when a name is saved;
- Live passes what was heard to skills.

Don't call Gemini with Andy's key. The hub runs bench run 3 after this and M9d3 merge.

**Stay out of** `tools/brain_bench.py`, `bench/` and `tests/test_brain_bench.py` (M9d3 is changing them), and out of `mockups/` and `docs/messaging-plan.md` (M15b).

**Models:**
- An Opus coder at effort xhigh does the character and racism-steer wording and the Live instruction (items 1 to 3).
- An Opus coder does items 4 and 5.
- A Sonnet coder writes the tests.
- Checkpoint after each item.

**Finish:** commit `DONE: M4c brain fixes ready for bench run 3` with a short report. Say what changed for each item, what you found about why Live drifts, and anything a resident would hear differently. If you needed a safety-section change, commit `WAITING:` instead, with the draft. Then stop.
