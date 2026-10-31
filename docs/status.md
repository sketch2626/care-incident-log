# Where things stand (the hub keeps this current)

Read `docs/mission.md` first. This file holds the facts: what's running, what's waiting on Andy, and what's next. The hub updates "Right now" at every milestone, so a compaction or a fresh hub never loses track. Plans: `docs/mary-roadmap.md` (M items), `docs/companion-plan.md`, `docs/backend-plan.md`.

## Right now (2026-10-31, about 00:45)
- **Mary** runs in talk mode **Offline**: the full Gemini brain plus the Kokoro "Heart" voice. Everything through the M9c truly-forget merge is merged and backed up to GitHub `dev`. Andy will restart her for his next try when he's ready (he's resting).
- **Her account's workers resumed at 23:50.** Her weekly limit resets Oct 31 at 5pm, and Andy wants her usage used before then. Check each worker's size with `python tools/worker_context.py`. New jobs go to fresh workers; reuse one only for fixes to its own job while it's under about 200,000 tokens.
  - **M9c truly forget: merged 2026-10-31** (811 tests). It's a real delete: memories live in their own `mary/memories.db` with secure_delete, so incident backups never hold them, and the old table is wiped from every backup. "Forget my name" merged too (822 tests): it clears the saved name, its memories and its talk turns, then she uses no name until one is offered. The page reloads the name after each turn (hub fix). Not run with real Gemini yet. Note: `test_live_skills` failed once while M8 was timing the laptop (a skill guard timeout under load); it passed on rerun.
  - **M7a word search: merged 2026-10-31 (865 tests).** The resident picks 8x8, 10x10 (the first-time default) or 12x12 by voice or tap; it's saved as setting `word_search_size`. The bar reads "Bigger letters", "Same", "More letters", "Back". Not yet seen in a real window, with real touch or in a real Live talk: Andy's first try is the check. Known gaps are in the merge commit.
  - **M13b tool groups** (`other/M13b`, tab "M13b tool groups her acct", brief `docs/handoff/M13b.md`, started 00:40): each skill is one group, at most about 12 tools at once, and one thing beside Mary at a time (a picture sets the game aside, and the game comes back).
  - **M15 cards and messages** (`other/M15`, tab "M15 cards and messages her acct", brief `docs/handoff/M15.md`, started 00:55): research, plan (`docs/messaging-plan.md`) and round 8 boards, no code. Andy decided on email plus Facebook Messenger and other messaging apps, messaging in general ("help me send a message to my grandson"), and image generation on the paid tier. It commits WAITING for Andy.
  - **M8 laptop speed check** (`other/M8`, tab "M8 laptop speed her acct", brief `docs/handoff/M8.md`, started 00:15): on first run it times Kokoro, Whisper and the wake word, picks a "normal" or "light" tier, and lightens settings by itself on a slow laptop. Anything a resident would see or hear differently waits for Andy.
  - **M9d2 bench fixes** (`other/M9d`, tab "M9d2 bench fixes her acct", peer `m9d-4b`): the fixes committed, tests in progress. Then the hub does a second real bench run.
  - **Idle:** M4b (`m4b-32`). Closed: speak-up (243K; its next step S1 is a fresh worker after D2, D3 and D9) and M4a, both merged; M4a's tab is still open because Andy typed in it. Speak-up's next steps wait on decisions D1-D10 in `docs/speakup-plan.md`.
- **Merged today since 20:30:**
  - the speak-up review and plan, plus S0 (legal facts fixed against Appendix PP Rev. 232);
  - M4a's fixes from the bench (no tags in Live, every bracket stripped in Normal, crisis numbers digit by digit, harm before the write-down offer, grown-up stories with no human past);
  - bench run 1 (`bench/results/2026-10-30_2051.*`, 16/88, a mix of real problems and bench flaws).
- **Questions for Andy:**
  - Should Mary name autonomic dysreflexia to the resident? The safety section names it on purpose; the bench judge called it diagnosing.
  - Speak-up decisions D1-D10.
  - "Pal" was added to Sam's pet names that wait until asked; keep it?
- **Merged, waiting on a check:**
  - **M9c memory core** (merged 2026-10-30, 707 tests):
    - Memories are dated entries in the app's database, pulled with a `recall` tool; about 120 words are always sent.
    - "What do you remember about me?", "forget that", and a "What Mary remembers" list in My info.
    - Andy tries it after M4a and M4b land. "Forget" really erases since the 2026-10-31 merge.
  - **M9d brain bench:** the hub's first live run waits until Andy is done with Mary for the day, because it shares his free Gemini allowance. Commands are in the M9d merge commit body:
    - `python tools/brain_bench.py --key-from-app --delay 4` (about 168 requests);
    - add `--raw --variant bench/variants/lean-mary.md --variant bench/variants/lean-sam.md` for the full side-by-side (about 349 requests).
  - **M6 wake word:** "Hey Mary" worked (1.6 s). Andy's TV check is read from `wake.log` in the data folder, then `DONE`.
  - **M12 pictures:** waits for M4a and M4b's fixes, then Andy tries it again.
- **Decisions waiting on Andy:**
  - **Politics:** decided 2026-10-30 (Andy's answer 10). Merged into her instructions and bench (bd7cc85).
  - **M9f, threats against others:** the safety-section gap. A draft is in the roadmap, waiting on Andy.
  - **Paid tier for residents (Andy, 2026-10-31):** "this is going to have to be on a paid tier once it gets into the hands of the other people… for the privacy concerns." The free tier is for Andy's testing only.
  - **wake.log words:** decided 2026-10-31 (Andy: "word count at pilot"). The log keeps Whisper's words around each wake while Andy tunes the wake word. Before the pilot it keeps only a word count, because forget can't reach the log.
  - **"Forget that":** decided 2026-10-30: truly erase (Andy: "forget that means forget that"). Merged 2026-10-31.
  - the main talk mode (Normal/Offline back-and-forth vs. Live; roadmap "Main talk mode, being decided");
  - the "Mary" shortcut name in the installer.
- **Next, in order:**
  1. **M13b, tool groups**, running (see above). Then rebuild the installer once M13b and M8 are merged. Andy decided 2026-10-31: group her tools so she only holds the ones for what you're asking about. Each skill is one group, plus her own tools and a way to open another group, at most about 12 at once. With word search she has about 26 today.
  2. M9e, a leaner brain, after the bench A/B.
  3. M7 games as skills (boards first, on Andy's account).
  4. M15, cards and messages: build after Andy approves the plan and boards.
  5. M14, a better voice: ask Andy for the name of the open-source, ElevenLabs-style voice.
  6. Before the pilot: presentable GitHub, and wake.log keeps a word count instead of the words.
- **Free-tier facts:** Gemini TTS allows 10 requests a day and resets at midnight Pacific. Live is free. The text model's daily limit isn't measured yet.
- **GitHub:** all of `main` is backed up to the `dev` branch (2026-10-30). The public `main` is still v0.2.0 until the cleanup before the pilot.
- **Clean-up done 2026-10-30:** the installer, M12 and M13 worktrees and branches were removed, and the finished briefs moved to `docs/handoff/done/`.

## Build history and notes (moved from `CLAUDE.md` on 2026-10-30)

### Status (from 2026-10-24)
- Pushed to GitHub: v0.2.0. That's talk-to-log, design C, Talk buttons on detail boxes, formal reports, optional Gemini, and the installer build.
- Verified research, not yet committed:
  - `contacts/NC.json`: DHSR complaint line 1-800-624-3004 (no email or online form, printable forms only); state ombudsman (919) 855-3400 (re-check the roster date). Corrected 2026-10-30: DHSR's pages do list an email, unconfirmed for complaints (see `docs/speakup-review.md`).
  - `docs/retaliation.md`: F585, F550, F600, F622/F623, NCGS 131E-117(12), 131E-124(c). Corrected 2026-10-30: F622/F623 are now F627/F628.
- Parked on branch `wip/report-to-state` (commit fddfdbc). It's unreviewed and untested, because helpers were stopped mid-work:
  - Report-to-state backend in `server.py` and `reports.py`: urgency levels via `/api/status`; the send wizard (grievance letter, completeness check, attestation, email/letter/phone from the contacts JSON); the submissions table; the retaliation flag and pattern detection; and quick notes (`/api/quick`). The `web/` screens for `#send` and `#rights` were never started.
  - The floating mic button in `desktop.py` + `web/float.html`, and the installer's "start with Windows" option.
  - `RETALIATION_REGS` in `reports.py` still needs filling from the verified citations above.
- NC Medicaid laptops (Andy, 2026-10-30): the program gives residents laptops. Many are **new donated Lenovos**, like Andy's (AMD Ryzen 5 7520U, integrated Radeon), and some are refurbished, for a $65 refurbishing fee waived if the resident can't pay. Other states: check. Plan for both: tune defaults on the new Lenovo class, and check heavy pieces (voices, wake word) on a weaker refurbished-class machine, or with a CPU limit, so they never stutter there.
- **Mary build (worker "mary-app", 2026-10-25), in progress.** His name is **Sam** (final, Andy). Done:
  - Face component `web/mary/face.js`/`face.css`, with a demo at `/mary/demo.html`: Mary in 11 moods (7785098), and Sam with his square glow (1a35f99).
  - Talk routes: mood tags, `/api/mary/status|talk|talk?stream=1|hello`, and voice settings (685af39).
  - Listening auto-stop: `GET /api/listen/level` (9635709).
  - A "yes" to Mary's offer saves the incident (8e3e346).
  - Mary uses only the saved key (`gemini_key`) and model (`gemini_model`), not the smart-helper switch.
  - Mary screen `/mary.html` (`web/mary/app.js`, `mary.css`): talk loop, emergency, no-key, menu, typing (6eb1b50). Its API is `window.MaryApp`. `startFirstRun()` is a stub for now.
  - First run `web/mary/firstrun.js`, which covers:
    - Choose Mary/Sam, by tap or voice.
    - First hello, where she asks the resident's name.
    - A greeting by time of day.
    - Idle: asleep at 5 min and dimmed at 15 min (`IDLE` config). Any tap, key or talk wakes her.
    - Screen Wake Lock unless `/api/power` says on battery. That route isn't built yet, so for now the screen stays on.
  - **Full entry points, T5 done 2026-10-28** (97aee7c, 89bd43d; 170 tests pass):
    - `power.py`: `plugged_in()` (`GetSystemPowerStatus`; True/False/None, a desktop with no battery is True), `keep_display_on(p)` = `p is not False`, and a `KeepAwake` thread. Every `SetThreadExecutionState` call and the release on stop run on that thread. Plugged in or unknown means the display stays on; on battery, the normal timeout applies. `GET /api/power` → `{plugged_in}`. Tests are in `tests/test_power.py`.
    - `desktop.py --mary` opens `/mary.html` full screen, titled "Mary":
      - `MaryApi.close_window()` makes the menu show Close.
      - The WebView2 autoplay flag is set through the env var. The env var replaces pywebview's own args, so `--disable-features=ElasticOverscroll` is repeated.
      - `private_mode=False` with storage in `DATA\webview`.
      - KeepAwake starts before the window opens and is stopped in a `finally`.
      - Without WebView2, it opens the browser at `/mary.html` with no KeepAwake.
    - `Start Mary.bat` runs `packaging\.venv\Scripts\pythonw.exe desktop.py --mary`, because only that venv has pywebview. Without the venv it uses the system `pythonw`, which falls back to the browser.
    - Home shows "Talk to Sam" when `companion` is "him". My info has the note "Mary uses this key too…"
    - **Not yet seen in a real window:** full screen, Close, autoplay voice and the keep-awake.
  - **Full review done 2026-10-28** (`docs/review-2026-10-28.md`; fix commits 1b6a8e1…47c78f5; 254 tests, no skips). Fixed: the hidden Close on first run (blocker), missed emergency phrases, bad-key message, offers that didn't save, server data integrity, installer bundling. Ranked open items are in the doc. If Mary gets stuck full screen, the hub stops the `pythonw desktop.py --mary` process; `desktop.log` in the data folder has window errors.
  - **Next for a fresh worker, in order:**
    1. **Andy tried Mary as user #1 (2026-10-28).** Paste is fixed (4b16ebc, c1cadca) and his key is saved. His findings are the robot voice, games refused, Talk needed every turn, the captions and too many buttons. All of them are in **`docs/mary-roadmap.md`** (items M1-M8, with order and dependencies). Start one worker per item; worker `mary-fixes` (local_776f5e74) has the context for M1. **Found so far:** no paste in the app window, fixed 4b16ebc + c1cadca (see `docs/review-2026-10-28.md`, "Andy's first try").
    1b. **In flight (2026-10-29, hub = "Main session"):**
       - **M2:** done. Live talk works; Andy liked it (a story, and it stopped instantly when he cut in). His Mary and Sam voice picks are saved. Talk modes: Live (default), Normal, Offline, all as choices.
       - **M9a:** character sheets approved (`docs/characters/`).
       - **M9b:** done (39fd97c). Mary and Sam each have their own brain text plus live facts about their app; 349 tests pass. Not yet tried with his real key.
       - **M13 skills core:** merged into `main` (28c8fe0), built on the second account. 407 tests pass. The first skill is `voice_comfort` (slower, faster, quieter, louder, switch to Sam, by voice and offline). How-to: `docs/how-to-make-a-skill.md`. **Still open:** (1) the one-line Live hook in `voices.py` `live_token()` (`server.mary_live_skill_setup()`) lands with M4; (2) ~~JS syntax~~ checked with Node on 2026-10-30: every script passes, and 407 tests pass with no skips; (3) remove `.worktrees/M13` and branch `other/M13` once its terminal tab is closed.
       - **2026-10-30:**
         - **Andy's second try:** the new brain is great (her NC story "nailed it"), and "slow down"/"speed up" work. She cut him off mid-sentence, so `QUIET_END_S` went from 1.4 to 2.5 s (779728c).
         - **M12 pictures skill:** merged (6962a23), 428 tests pass. Not yet seen in a real window or against live Wikipedia. `.worktrees/M12` stays until its terminal tab closes.
         - **M3 boards** (`mockups/mary/round6/`, canvas https://claude.ai/artifact/Mh4CpUMru2YGNSEycrJnCZ):
           - Approved: caption style A, the emergency screen, and the menu (one Menu button, top right).
           - Being revised: listening = sound-wave arcs off both "ears", with no "I'm listening" pill; thinking = bubbles rising into a thought cloud over her head.
         - **Merged into main (all built on the second account):**
           - M4a, Live voice plus stories, greeting, starting on open, and plain talk;
           - M4b, captions, ear waves, thinking cloud and the one top-right Menu ("looks really good", Andy);
           - M6, "Hey Mary"/"Hey Sam", which woke for him in 1.6 s; log in `wake.log` in the data folder;
           - installer 0.3.0.
         - **Andy's third try** (roadmap M4): runaway pacing in long stories, "go to sleep", there's no Talk button, and a patronizing tone ("infantilizing"). M4a's fixes are on `other/M4a`.
         - **M9d brain bench:** being built (`docs/handoff/M9d.md`). The hub does the first live run, `--key-from-app`.
         - **M14, a better voice:** later. It's the open-source, ElevenLabs-style voice Andy found (it runs locally and can't be shut down); ask him for its name first.
       - **Next:** M7 games as skills (boards first, on Andy's account); rebuild the installer after M4a's latest merge.
    2. **Docs:** `docs/companion-plan.md` gets the build status with commit ids and Sam's name. Also bundle `mary/instructions.md` in `packaging/build.py` when the installer is rebuilt (Next step 5).

### Next steps (older list)
1. ~~Quiet test suite~~ **Done 2026-10-24** (371bba0, ea5c4c2, 1c0182d): 59 tests, about 2 s. The 5 `guess_incident()` BUG skips were fixed 2026-10-28 (1b6a8e1).
2. **Mary prototype, with Andy as user #1** (`docs/companion-plan.md`). **Brain done 2026-10-25** (ed6ec4e, 5ecb2d2): `mary/instructions.md`, `mary.py` (`reply(text, memory, api_key)`), `tests/test_mary.py`, speed test `tools/mary_speed.py` (needs env `GEMINI_API_KEY`; no key is saved yet, so Gemini speed is unmeasured). Speech fix done (fad93ba, `beam_size=1`): speech-to-text median about 1-1.6 s, p90 under 3 s (was 5.5 s).
   - **Face, in mock-ups:** round 1 (`mockups/mary/face-boards.html`, ade6015) was rejected. A was "scary", C was out, and B's warm glow came closest.
   - **Round 2 direction (Andy, 2026-10-25):** the screen IS her face, with no head outline and a warm light filling the screen. A soft edge glow changes color with her mood (soft pinkish red for an emergency, never scary).
   - **Her look:** fully cartoon with no realism, a mouth, no nose. Very expressive: eyes change shape, she blushes, and the forehead shades softly with no line eyebrows. 11 moods, plus everyday and emergency screens, with captions and buttons on top of her face near the bottom.
   - **Where the boards are:** on a Design canvas, which is private to Andy's first account. Committed copies are in `mockups/mary/round2/`, `round4/` and `round5/`, the source of truth for a fresh hub.
   - Andy approves a face before any build. Round 2 was liked ("so far, so good"). Round 3 fixes: no unibrow, thinner rounded brows instead of "smudges", and rounder eye corners.
   - **Round 4** (3be92ae, `mockups/mary/round4/`): the cuteness pass (Cute 1-3), his male version, **Sam** (final name; residents choose Mary or Sam), "Choose your companion" and "First hello". Andy: "so far so good… this will be what we use". He'll tweak after pilot feedback. Base: **Cute 3** for both faces (Andy, 2026-10-25).
   - **Mary and the computer (Andy, 2026-10-25):**
     - Level 1, her own skills: pictures ("show me a bird"), music, weather, news, reminders.
     - Level 2: she opens apps and sites, with a floating Mary button.
     - Level 3: she operates the computer, only after the pilot and only if residents ask.
     - Two setup modes: "Mary only" and "Mary plus the computer".
     - See "Mary and the computer" in `docs/companion-plan.md`.
   - **New feature (Andy, 2026-10-25): games with Mary.** She suggests a game, scoots aside, and helps the resident play. Word search comes first, then tic-tac-toe and solitaire. See "Games with Mary" in `docs/companion-plan.md`.
   - **New feature (Andy, 2026-10-25): family messages and calls.** "Mary, message my daughter…" or "Mary, put a call through to my son…", all from her screen. Plan and research list: "Family messages and calls" in `docs/companion-plan.md`. Mock-ups: `R2MessageScreen`, `R2CallScreen`.
   - Still to build: her full-screen face, the talk loop (on-device speech-to-text → Gemini → voice), the "Hey Mary" wake word, and memory on the laptop. Test speed first (reply within ~2 s on a cheap laptop), then voice.
3. **Lid to Mary.** Windows PIN, then Mary opens full screen on her own and stays open; a locked-down kiosk needs Windows 11 Pro. Also a one-click setup tool for helpers, and a laptop spec with a price.
4. **Before the pilot:** review, test and merge `wip/report-to-state`; it becomes Mary's speak-up skill. Then add facility-first emails ("Facility first" in `docs/backend-plan.md`).
5. ~~Rebuild the installer~~ **Done 2026-10-30** (0.3.0, branch `other/installer`). Models download when missing, and it was smoke-tested in a scratch folder. Rebuild it after each big Mary merge.
6. Finish the pilot/funding plan doc. The protection checklist and AI partner steps are in `private/protection-and-partners.md`, which is gitignored and never committed or quoted publicly. The 5-resident pilot checklist is in `docs/pilot-checklist.md` (revise it for the companion); the pilot needs backend phases 1-2 only.
7. Build the backend phase by phase per `docs/backend-plan.md`. Phase 1 (encrypt the local log, app lock) needs no server and can come early. No real resident data reaches a server piece until its security review passes.
