# Where things stand

Facts only: what's happening now, what's waiting on Andy, and what's next. The spirit is in `docs/mission.md`, the rules in `docs/decisions.md` and `docs/how-we-work.md`, and each item in detail in `docs/mary-roadmap.md`. The log through 2026-11-04 is in `docs/archive/status-2026-11-04.md`.

## Right now (2026-11-04)
- **Mary today:** v0.5.0 (installer 336 MB, zip 401 MB), on the free Gemini tier for Andy's own testing (D21). Three brains sit behind the `mary_brain` test switch: full (the default), lean (`mary/lean.md`, tag `lean-v1`) and leaner (`mary/leaner.md`). Andy picks one with the paid model (D19).
- **Her brain waits on the paid model,** Gemini's paid tier or the Claude API, which Andy is choosing. Personality work on today's cheap model stopped on 2026-11-04. Testing until then follows D26.
- **M24, the porch scene:** round 5 is done on `other/M24-scene` (not merged; brief `docs/handoff/M24-scene5.md`). It has Andy's layout, a cartoon face, a matte finish with no glare, a darker mood, evening, night (`?time=night`, Andy's favorite) and a calm day (`?time=day`), a real old lantern Mary turns up or down (`?lamp=`, `?pose=lamp`), and a soft radio glow. Still open: the turned-down lantern glass stays a bit pale, the day sky reads a little gloomy, and her posture and shawl. How she's shown in the app: a live Mary in front of painted background plates (roadmap M24). Next round waits on her account (it resets Saturday at 4pm).
- **`other/M24-boards`** (round 11 in code) is kept and not merged. The hub settles it after the scene.
- **cleanup1 is merged and published** (2579 tests OK): rules live only in `docs/decisions.md` (D1-D27) and `docs/how-we-work.md`. The hub's memory matches. The proposed changes to Andy's global instructions and the token-saving skill wait on his OK (`docs/handoff/done/cleanup1-global-proposals.md`).
- **Repo:** Mary's Porch (github.com/sketch2626/marys-porch); `main` is published after every merge (D17).
- **Fundraising** is handed to Claude Cowork (`private/fundraising/handoff.md`).
- **Loose ends for the hub:** the merged branches are pruned. The leftover plain folder `.worktrees/M9d3` remains (a safety check blocks deleting it). `wip/report-to-state` stays (roadmap M27).

## Waiting on Andy (asked one at a time)
1. **Her brain:** Gemini's paid tier or the Claude API (roadmap M26).
2. **Leaner's tighter safety wording** (D5), which comes with the brain pick. The old-to-new map is in the M21d merge commit.
3. **Sam's pet name "Pal":** D7 makes pet names fine. Keep "Pal" among Sam's (`docs/characters/sam.md`)?
4. **The "Mary" shortcut name** in the installer (the second shortcut is "Care Incident Log").
5. **The speak-up decisions SD1-SD10** (`docs/speakup-plan.md`, "Decisions for Andy").
6. **Removing a note by voice** has no "are you sure?" (the tap has one) and no voice way to bring it back. Also, after "which one?", the answer must carry the verb ("remove the one from Tuesday"). Keep it that way?
7. **The voice on a slow laptop:** keep Kokoro with gaps between sentences, use the Windows voice there, or add the lighter Piper voice (plainer, a bigger installer)? (Roadmap M8.)
8. **The open-source voice** Andy found that works like ElevenLabs: its name or link (roadmap M14).
9. **The five-minute Facebook sign-in test** (`docs/messaging-plan.md`, test 9), before the Messenger step.
10. **The global-file changes:** apply `docs/handoff/done/cleanup1-global-proposals.md` to Andy's global instructions and the token-saving skill?

## Next, in order
1. **M24:** finish the porch scene, then build the loop studio and the player into the app.
2. **M26, her brain on the paid model:** the pick, the rebuild, the module, and full testing, safety first (D26).
3. **M25,** the porch radio.
4. **M18b:** opening and filling screens by voice in Normal and Offline.
5. **Messages:** M15e-j, and a first real Gmail or Yahoo send with a helper.
6. **M27, speaking up:** speak-up S1 onward, after SD1-SD10.
7. **The pilot:** `docs/pilot-checklist.md`, with M28 (lid to Mary and setup).
