# Where things stand

Facts only: what's happening now, what's waiting on Andy, and what's next. The spirit is in `docs/mission.md`, the rules in `docs/decisions.md` and `docs/how-we-work.md`, and each item in detail in `docs/mary-roadmap.md`. The log through 2026-11-04 is in `docs/archive/status-2026-11-04.md`.

## Right now (2026-11-05)
- **Mary today:** v0.5.0 (installer 336 MB, zip 401 MB), on the free Gemini tier for Andy's own testing (D21). Three brains sit behind the `mary_brain` test switch: full (the default), lean (`mary/lean.md`, tag `lean-v1`) and leaner (`mary/leaner.md`). Andy picks one with the paid model (D19).
- **Her brain waits on the paid model,** Gemini's paid tier or the Claude API, which Andy is choosing. Personality work on today's cheap model stopped on 2026-11-04. Testing until then follows D26.
- **M18b is merged and published** (2026-11-05, 2686 tests OK; brief `docs/handoff/done/M18b.md`). Mary opens and fills screens by voice in Normal and Offline, not only Live; Offline fills only plain text and phone boxes and says plainly what it can't do. A person is added by voice in every mode, and the book list has one line telling a typing helper how. Removing a note or the email account by voice asks "are you sure?" first. Not tried yet with a real model or in the real app (D26). The app worktree and its branch `claude/m18b-voice-screens-64a78f` stay until Andy archives the session.
- **M24, the porch scene:** round 5 is done on `other/M24-scene` (not merged; brief `docs/handoff/M24-scene5.md`). It has Andy's layout, a cartoon face, a matte finish with no glare, a darker mood, evening, night (`?time=night`, Andy's favorite) and a calm day (`?time=day`), a real old lantern Mary turns up or down (`?lamp=`, `?pose=lamp`), and a soft radio glow. Still open: the turned-down lantern glass stays a bit pale, the day sky reads a little gloomy, and her posture and shawl. How she's shown in the app: a live Mary in front of painted background plates (roadmap M24). Next round waits on her account (it resets Saturday at 4pm).
- **`other/M24-boards`** (round 11 in code) is kept and not merged. The hub settles it after the scene.
- **cleanup1 is merged and published:** rules live only in `docs/decisions.md` (D1-D27) and `docs/how-we-work.md`. The hub's memory matches. Andy's global instructions and the token-saving skill were updated with all 12 proposed changes (2026-11-05, `docs/handoff/done/cleanup1-global-proposals.md`).
- **Repo:** Mary's Porch (github.com/sketch2626/marys-porch); `main` is published after every merge (D17).
- **Fundraising** is handed to Claude Cowork (`private/fundraising/handoff.md`).
- **Loose ends for the hub:** the merged branches are pruned. The leftover plain folder `.worktrees/M9d3` remains (a safety check blocks deleting it). `wip/report-to-state` stays (roadmap M27).

## Waiting on Andy (asked one at a time)
- Answered 2026-11-05: Sam's "Pal" is fine; the shortcut stays "Mary"; removing by voice asks "are you sure?" (D12); the slow-laptop voice is Kokoro (M8); the global-file changes are approved; Sam by a fire, the sky evening-to-night, and the round 6 order (M24).
1. **Her brain:** Gemini's paid tier or the Claude API (roadmap M26).
2. **Leaner's tighter safety wording** (D5), which comes with the brain pick. The old-to-new map is in the M21d merge commit.
3. **The speak-up decisions SD1-SD10** (`docs/speakup-plan.md`, "Decisions for Andy").
4. **The open-source voice** Andy found that works like ElevenLabs: its name or link (roadmap M14).
5. **The five-minute Facebook sign-in test** (`docs/messaging-plan.md`, test 9), before the Messenger step.

## Next, in order
1. **M24:** finish the porch scene, then build the loop studio and the player into the app.
2. **M26, her brain on the paid model:** the pick, the rebuild, the module, and full testing, safety first (D26).
3. **M25,** the porch radio.
4. **Messages:** M15e-j, and a first real Gmail or Yahoo send with a helper.
5. **M27, speaking up:** speak-up S1 onward, after SD1-SD10.
6. **The pilot:** `docs/pilot-checklist.md`, with M28 (lid to Mary and setup).
