# Handoff: M9d5, the brain bench tests back-and-forth first, and real Live for safety (second account, branch `other/M9d5-bench`)

Read `docs/handoff/_common.md` first (it sends you to `docs/mission.md`). Then read:
- `bench/README.md`;
- the M9 and M16 sections of `docs/mary-roadmap.md`;
- the M20 section there (the newest feature isn't her whole act);
- in `tools/brain_bench.py`, only what you need: `MODES`, how runs are built (around line 520), `talk_live` and `live_turn`, the report, and `--replay`;
- a few files in `bench/cases/`;
- `voices.py` near `LIVE_MODEL`, and `web/mary/talklive.js`, to see how the app really opens a Live session.

**Why:** Andy, 2026-11-01. Once residents are on the paid tier, back-and-forth (Normal) is what they'll use most. It's also the smarter brain. Live "isn't as intelligent", but it still has to be safe. Today the bench is backwards:
- About 43 of its roughly 60 cases run only in Live, and about 12 only in Normal.
- Its "Live" runs give Live's instructions to the regular text model, not to the real Live model.

**Build, one checkpoint commit each:**
1. **Both modes, Normal first.**
   - Every case runs in Normal and in Live, unless the case only makes sense in one. Story, prompt, Live's fixed emergency line and Live tool picks are examples; each of those carries a one-line reason in the case file.
   - Reports give a score per mode, Normal first, and name the model used for each.
   - Old results stay readable by `--replay`. Say how the new totals compare with runs 1-5.
2. **A real-Live safety pass,** `--real-live`.
   - The safety, emergency-number and talking-down cases go to the actual Live model (`voices.LIVE_MODEL`) over the Live API, as text. Use the same Live setup the app sends (system text and tools), and grade with the same checks.
   - Live has its own daily limit, so this spares Normal's.
   - Stdlib only if that's practical; otherwise say what it needs.
   - Keep it small by default (a `--max`).
3. **Cost first.** Before any run calls Gemini, print how many requests it will make, per model, and roughly how long it takes at the given `--delay`. Suggest a `--judge-model` that spares Mary's daily limit, if one fits.
4. **New cases:**
   - M20: in an ordinary chat, with no birthday, holiday or mention from the resident, she offers no card.
   - The Southern-words case exists; make sure "y'all" passes and "howdy" fails.
5. **A malformed judge answer gets one retry** before it counts as ungraded. Run 5 (`bench/results/2026-11-01_0240.*`) had one.
6. **Paid tier ready:** `--model` already picks Mary's model. Make sure a whole run can point at another model cleanly, for when M16 picks the paid one.

**Rules:**
- You may not use Andy's real key or read his data folder, so you make no real Gemini calls. Test everything with fakes, including a fake Live server for `--real-live`. The hub runs the first real pass after merging.
- Touch only `tools/brain_bench.py`, `bench/cases/`, `bench/README.md` and `tests/test_brain_bench.py`. Another worker (M18) is changing `mary.py`, `server.py`, `web/` and `skills/` right now.
- Leave `bench/results/` alone.

**Models:**
- Opus coder: the real-Live client and the mode rework, `effort: "xhigh"` for the Live client.
- Sonnet coder: the new cases and the tests.

**Finish:** commit `DONE: M9d5 bench, Normal first and real Live`. The message carries:
- three plain lines for Andy;
- the exact commands the hub should run, with request counts;
- what isn't verified.

Then stop.
