# Handoff: M4a, the good voice in Mary (second account, branch `other/M4a`)

Read `docs/handoff/_common.md` first. Then read only these:
- In `docs/mary-roadmap.md`: M2 (the Live results and the talk modes), M4, M5, the M9b note about `MARY_VOICE_NOW` / `MARY_TALK_MODE`, and M13's "Still open" item about the Live hook.
- `voices.py` `live_token()` and `tts_stream()` / `kokoro_stream()`.
- `web/mary/live.js`, the Live client from the voice audition, which already works on Andy's laptop.
- How `web/mary/app.js` talks today (grep for `speechSynthesis` and the Talk button).
- `server.py` lines near `MARY_VOICE_NOW` and `mary_live_skill_setup()`.
- `web/mary/skills.js`.

**Andy (2026-10-30):** he loves her brain now (her North Carolina story "nailed it"), but she still has the robot voice: "it just really depends on when we get the good voice in there." In the audition he loved Live: a story, and she stopped instantly when he cut in. His Mary and Sam voice picks are saved in the voice settings.

**Build:**
1. **Live in Mary's own screen.** Live is the default talk mode.
   - One tap on Talk opens her Live session with the picked voice: Mary's for Mary, Sam's for Sam.
   - Reuse `live.js` and `live_token()`. The key never reaches the page.
   - The session stays open hands-free, using Live's own turn-taking and interruptions. It ends after quiet (a config constant; start at about 15 s) or "goodbye", and she says a short goodbye.
   - Use the same brain as Normal: the system text with app facts and the resident's name.
2. **Skills in Live.** Add the M13 hook to `live_token()`: `server.mary_live_skill_setup()["tools"]` goes into `bidiGenerateContentSetup`, and its `"instruction"` goes into the system text.
   - Handle Live `toolCall` messages through the existing skills path, and send the `toolResponse` back.
   - "Slow down", "speak up" and "switch to Sam" must work by voice in Live.
3. **The emergency check in Live (must not be missed).** Her input transcription goes through the same emergency check as Normal.
   - On a match, show the emergency screen as today. An emergency line never triggers tools.
   - Test it.
4. **Talk modes:** Live, Normal and Offline as a setting (Live by default). Show it plainly in My info.
   - **Normal:** on-device speech-to-text → Gemini → the picked Gemini voice (`tts_stream`).
   - **Offline:** Kokoro (`kokoro_stream`).
   - **Fallback:** if Live fails (no internet, token refused), fall back to Normal, then Offline, with one kind spoken line. Never go silent.
5. **Hands-free in every mode, and patient listening (M5 folded in).**
   - **Andy (2026-10-30):** "before I could finish speaking, it was cutting me off". It happened a couple of times. Normal mode ended his turn after 1.4 s of quiet. The hub raised that to 2.5 s (`QUIET_END_S` in `app.js`).
   - **Live:** set `realtimeInputConfig.automaticActivityDetection` to be just as patient, with low end-of-speech sensitivity and about 2.5 s of silence. Check that the field names are the ones Google really accepts.
   - **A voice command in `voice_comfort`,** in every mode: "give me more time" or "you're cutting me off" makes her wait longer (2.5 → 4 s, saved). "You can answer faster" sets it back.
   - **Normal and Offline get the back-and-forth too.** After she finishes speaking, she listens again by herself and never while she's talking. The conversation stays open until about 15 s of quiet or "goodbye", the same as Live. Andy wants wake words plus hands-free talk in every mode, not only Live.
6. **Captions:** for now, show her words from `outputTranscription` in the existing caption area.
   - Keep this in one function, `showCaption(...)`, because M4b replaces it with the bubble letters after Andy approves the boards.
7. **She tells the truth about her voice.** Set `MARY_VOICE_NOW` / `MARY_TALK_MODE` in `server.py`, and update the "What you can do" / "Your screen" text in `mary/instructions.md`.
8. **Leave a hook for the wake word.** Make one function, `startTalk()`, that the wake word (M6, being built in another worktree) will call later.
   - Don't touch `speech.py` or the mic code in Python; M6 is changing them.
   - Live uses the page mic with echo cancellation, as in the audition.

**Other worktrees running now:**
- M12 (pictures) may add a server route.
- M6 (wake word) changes `speech.py`, and later `app.js` and `server.py`.

So keep your changes in clear blocks marked `M4a` to make merging easy.

**Tests:**
- Token setup carries the skills tools and instruction.
- Talk-mode setting and the fallback order.
- The emergency check on Live transcripts.
- A mocked `toolCall` → `toolResponse` round trip.
- App facts say the picked voice.
- `node --check` on every changed script.

**Models:**
- Opus xhigh: the Live session in `app.js`, the fallback chain and the emergency check.
- Opus: the other new code.
- Sonnet: the tests.

**Finish:** Andy has to hear it, so commit with the subject `WAITING: M4a good voice ready for Andy to try`. Then stop; the hub launches Mary for him and messages you his findings. After his fixes, commit `DONE: M4a good voice`.
