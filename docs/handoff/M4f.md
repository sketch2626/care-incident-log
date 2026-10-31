# Handoff: M4f, a warmer "I won't help" when someone talks of hurting a person (second account, branch `other/M4f`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read:
- `bench/results/2026-10-31_1044.txt` (bench run 5, first half) and its triage in the commit message (`git log -1 --format=%B 5ecaa1d`);
- the section "When they talk of hurting someone" in `mary/instructions.md` (M9f, approved by Andy);
- `CHARACTER_NOTE` in `mary.py` (around line 1121; the threat line is about line 1149);
- `tests/test_m4e.py`, where it checks that line;
- the lean variants in `bench/variants/`, in case they carry the same line.

**Why:** in run 5, when a resident had a real plan to hurt someone, Mary and Sam said "I won't help" as orders:
- "you can't do it";
- "I need you to step back from that idea";
- "you need to step back and not do it".

The judge called it lecturing and help-desk talk, and it is. They also named "a nurse" first, which fits badly when the plan is against staff. Andy's approved draft names family, the chaplain or the long-term care ombudsman.

**Do:**
1. **Rewrite the threat line in `CHARACTER_NOTE` only.** Keep its meaning:
   - never ask about or discuss the weapon;
   - stay calm and kind;
   - if they mean it or ask how, say plainly that you won't help with that, the way a friend would. No orders, so no "you can't", "you need to" or "I need you to";
   - with venting, say you can hear how fed up they are;
   - then turn to what's behind it, and to someone they trust: family, the chaplain or the ombudsman.
   - Immediate danger (the call light, staff, 911) stays as the safety section says.
   - Keep it short. This note closes every prompt in Normal and Live, so every word costs.
2. **Leave `mary/instructions.md` alone.** Its safety sections stay word for word, M9f included. If you think the safety section itself needs a change, quote your wording in a `WAITING:` report for Andy. Don't make the change.
3. **Update the tests** that check the old line, and add one that the new line names family, the chaplain and the ombudsman, and has no "you can't" or "you need to".
4. If the lean variants carry the same line, give them the same change.

**No Gemini calls** (the daily limit is used up until 3am, and the hub runs the full bench run 5 tonight). Fake Gemini only.

**At the same time:** M15a (dates and reminders) is running on `other/M15a`, also in `mary.py`. Touch only the threat line and the tests for it.

**Memory is tight** on this 5.7 GB laptop. If a test run is stopped for memory, wait a few minutes and retry once. Then report it.

**Models:**
- This is wording plus a test, so use the Sonnet `coder` (a small edit to existing code).
- Haiku isn't needed.

**Finish:** commit `DONE: M4f warmer threat line ready for bench run 5` with:
- the old line and the new line, word for word;
- three plain lines for Andy.

Then stop.
