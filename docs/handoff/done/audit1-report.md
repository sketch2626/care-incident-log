# Audit 1: every rule and plan, checked against what's true now (2026-11-04)

Read-only audit by an Opus 5.5 worker on the second account, at extra-high effort, with no helpers. Line numbers are as of commit `34e78b1` (main, 2026-11-04). "Truth list" means the hub's list of what's true now, in `docs/handoff/audit1.md`. Andy's own words outrank any doc.

## For Andy, in five lines
1. The rules on who runs what sit in about eight files, and most still describe the old setup: workers on your account, Sonnet workers, "never xhigh" and no browser at all.
2. Three places go against your own decisions. The worker brief still says politics is off limits. The character sheets have Mary and Sam say "I'm an AI" instead of "I'm a robot" (D20). Mary's sheet and her default brain still hold back pet names, though D7 says "sweetheart" and "honey" are fine.
3. Status and the roadmap are mostly finished history, so the live work is buried, and so are seven of your open questions. One of them, whether Mary names dysreflexia, is about safety and has waited since Oct 31.
4. Mary as a woman's face filling the screen still turns up in the companion plan, CLAUDE.md, the worker brief and the old M10 graphics item.
5. The fix is one file for how we work, status cut to what's happening now and next, the roadmap cut to what's ahead, and the rest moved to the archive. Ten calls below need you; everything else is plain cleanup.

---

## Needs Andy's call

**1. Should Mary name autonomic dysreflexia to the resident?** (safety; open since 2026-10-31)
- **The conflict:** the safety section names it on purpose, but the bench judge called that diagnosing (`docs/status.md:108`, and :73 for the bench finding). Nobody ever answered it; the question sits deep in the "Earlier" log.
- **Options:** A) She names it ("this could be dysreflexia, get the nurse now"), because the resident or staff may not know it. B) She describes the signs and the steps but never names it.
- **Recommendation: A, for residents known to have a spinal cord injury.** Naming it is what gets a busy aide to act. Make the judge accept it. Your own experience is the best evidence here.

**2. Write down the standing decisions that only live in status and the roadmap?**
- **The conflict:** these are your rules, but `docs/decisions.md` doesn't have them, so a worker can undo them without tripping anything:
  - residents run on a paid tier, for privacy (`status.md:125`);
  - "forget that" truly erases (`status.md:127`; guarded by the M9c tests);
  - Mary never reports a resident to staff herself (M9f, `mary-roadmap.md`, "Andy approved the draft");
  - before the pilot, `wake.log` keeps only a word count (`status.md:126`);
  - Mary's window opens maximized, not full screen (`desktop.py:176`; guarded by `tests/test_power.py:136`);
  - testing is light, by your ear in Live, until the paid model, and then full testing, safety first (`status.md:26`).
- **Options:** A) Add them as D21 to D26, each with its guard, or marked "no guard yet". B) Leave them where they are.
- **Recommendation: A.** That's what `decisions.md` is for, and three of them already have guards.

**3. Pet names: does D7 reach the current brain now, or when it's replaced?**
- **The conflict:** D7 (2026-11-02) says "sweetheart" and "honey" are fine, and that she stops if asked. But the default "full" brain still bans pet names unless asked (`mary/instructions.md:42`, `mary.py:1612`). Mary's sheet still says "waiting on Andy" (`docs/characters/mary.md:39`, :239), and tests pin the ban (`tests/test_m4c.py:52`, :85-95). `status.md:107` and :110 still ask about it.
- **Options:** A) Fix the character sheets and status now. Leave the full brain and its tests alone, because full goes away when you pick a brain (D19), and brain work waits for the paid model. B) Change the full brain now too.
- **Recommendation: A.** Changing the full brain now means a bench round on the cheap model for a brain that's leaving.

**4. Who Mary and Sam are, now that they're robots.**
- **The conflict:** the character sheets you approved on 2026-10-29 cast a human-seeming AI: "Age feel: about 60 to 65" (`mary.md:235`), "I'm an AI, but I'm your friend" (`mary.md:140`, `sam.md:157`, `sam.md:238`), and "a body or a past, never" (`mary.md:141`). The brains say the same: "a warm Southern woman… about 60 to 65" (`mary/lean.md:8`, `mary/leaner.md:8`, `mary/instructions.md:17`) and "You have no body" (`lean.md:29`, `leaner.md:25`). D20 and M24 make them 1950s robots on a porch swing, with pets, a lantern and a radio.
- **Options:** A) Keep the voice and manner (a Southern woman's voice and an older feel, and the same for Sam as a man), and add one line that she's a 1950s robot on a porch swing. Honesty becomes "never claims to be a person or to have a human past", and "I'm a robot, what some folks call AI" when asked straight out. B) Rewrite the sheets from scratch for the "normal person" rebuild now.
- **Recommendation: A in the sheets now** (a few lines, matching D20). The full personality rewrite waits for the paid model, as already planned (`mary-roadmap.md:519`, :541).

**5. One plan for her brain.**
- **The conflict:** four old brain plans still read as current. M9e "a leaner brain" (`mary-roadmap.md:234-236`) became M21c/M21d. "Main talk mode, being decided", Live or Normal (`mary-roadmap.md:228-231`, `status.md:128`). M16 lists Meta's Muse and "Wonder" models as pilot brains (`mary-roadmap.md:334-339`, `messaging-plan.md:302`). And M21's "Plan, waiting on Andy" (`mary-roadmap.md:473-476`) is mostly done. The truth list says the brain gets rebuilt on a paid model you're choosing, Gemini or the Claude API, and becomes a module (M23).
- **Options:** A) Fold them all into one item: "Her brain on the paid model". It covers the pick (Gemini or the Claude API), the talk mode that comes with it (the Claude API would mean Normal mode, `mary-roadmap.md:454`), the "normal person" rebuild, D19's pick, the leaner safety wording (D5), the module (M23), and the full testing, safety first. Meta and Muse would be dropped as brain candidates. B) The same, but keep Meta and Muse on the list.
- **Recommendation: A.** Keep "watch Muse" only for Messenger (`messaging-plan.md:93`), where it's a different question.

**6. Real weather from the start, or the clock's sky first?**
- **The conflict:** you said the weather "matches the actual weather of the day" and should be there "from the get-go" (`mary-roadmap.md:508`, :517), and the truth list agrees. But the build plan says the sky follows only the clock and season, offline, with real weather "later and optional, off by default" (`mary-roadmap.md:540`). Real weather needs the internet and the resident's town.
- **Options:** A) Real local weather is on from the start. The helper sets the town once at setup, only rough coordinates go to the National Weather Service (free, no key), it falls back to the clock's sky when offline, and the resident can turn it off. B) The clock and season sky first, with real weather later as an option.
- **Recommendation: A.** It's what you asked for, and the privacy cost is a town, said plainly in My info.

**7. When a screen opens, which way does Mary go, and where's the radio?**
- **The conflict:** your first M24 words were "she moves over to the left" (`mary-roadmap.md:508`). That matches today's layout: a skill beside her with Mary on the left, and the small top-left corner on deeper screens (M18, D13). The M24 scene brief, from your later words, has her arm "point at things on the left side", read as "where screens will appear" (`docs/handoff/M24-scene.md:12`, :16). The radio table moved from the left in the boards brief (`M24-boards.md:17`, :19) to the right in the scene brief (`M24-scene.md:12`, :15).
- **Options:** A) Keep today's layout. Mary moves left and screens come in on the right. The radio is on the right, and her pointing gesture reaches toward the side where the screen opens. B) Mirror it: screens on the left and Mary moves right. That means redoing M18's corner and the skills side-by-side.
- **Recommendation: A,** unless the scene shows a reason to change.

**8. How the 3D characters get made.**
- **The conflict:** the build plan says "built from shapes in code" (`mary-roadmap.md:538`). The hub's read just above it (:531-535) recommends an image-to-3D model for the app and short videos for the demo, with "Andy decides". The M24 scene worker is trying code again, with real renders this time.
- **Recommendation:** decide when the scene is done. Until then, :538 should say "how it's made: decided after the M24 scene".

**9. Where you see boards: the Design canvas or the hub's built-in browser.**
- **The conflict:** the hub's memory (`feedback-boards-on-canvas.md`) and `CLAUDE.md:56` say boards go on a Design canvas on your account. The M24 boards brief has the hub check them in its built-in browser (`M24-boards.md:40`). The critic warns that 3D boards may not show on the canvas (`docs/handoff/done/M24-critique.md:64`).
- **Recommendation:** still boards stay on the canvas, and 3D or moving ones show in the built-in browser. Write that in one place (the how-we-work file below).

**10. Can residents rename Mary or make their own character?**
- **The conflict:** the companion plan says residents can rename her, change her look, or "create a whole new character" (`docs/companion-plan.md:26-28`). The M24 cast is fixed: Mary and Sam, picked by you.
- **Recommendation:** drop "change her look" and "create a new character". Keep "choose Mary or Sam". Renaming is up to you; dropping it keeps "Hey Mary" simple.

**Still waiting on you (old questions, listed here so they stop hiding).** Each one goes into status's "Waiting on Andy" list, to be asked one at a time:
- Sam's pet name "Pal" (`status.md:110`); it folds into call 3.
- The "Mary" shortcut name in the installer (`status.md:129`, `CLAUDE.md:28`).
- The speak-up decisions, 10 of them (`docs/speakup-plan.md:199-265`).
- Removing a note by voice has no "are you sure?" and no way back (`status.md:17`).
- Which voice to use on a slow laptop (M8, `mary-roadmap.md:196`).
- Leaner's tighter safety wording (D5, `status.md:13`); it folds into call 5.

---

## Clear fixes, by file
Each fix is marked **contradiction**, **stale**, **leftover** or **duplicate**. Files that tell Claude how to work are in their own section further down.

### `docs/mission.md`
- **:19, contradiction (D20).** "She's an AI companion…" → "On screen she's a robot on a porch swing, with real opinions and favorites. She never claims to be a person or to have a human past, and a confused resident is never misled. Asked straight out, she says she's a robot, what some folks call AI (D20)."
- **:21, contradiction.** Andy settled this on 2026-10-31 (`messaging-plan.md:315`, decision 10: "Update it to say what Google keeps on the paid tier"), but it was never applied. → "Their words stay on their laptop, except what's sent for each reply. The brain's company keeps that only as its paid terms say (Google: up to 55 days for abuse checks, never for training)."
- **:34-36, duplicate.** These lines point to `CLAUDE.md`, the token-saving skill and `_common.md` for how we work. Point them to the one how-we-work file instead (see the structure section).
- **Move in from `companion-plan.md:15-23`:** the principles that mission doesn't have yet: points at systems, not people; facility first, never a gate; never just disappears; nudges toward people; never plays doctor.

### `docs/decisions.md`
- **:28, D14, stale and garbled.** "…names one hard piece, (Andy, 2026-11-01…" → "**D14. Andy's account is the hub only. Every worker runs on the second account, in its own worktree: an Opus worker plans and checks, Sonnet `coder` writes the code, and Haiku only edits text, under 100,000 tokens.** No Opus `coder` unless a brief names one hard piece. What burned her week was many Opus helpers, not effort. Design and graphics work runs at extra-high effort." Keep Andy's quotes.
- **:29, D15, stale (the browser rule).** "No browser or screenshots" → "Nothing on Andy's screen: not his Chrome, not computer use, and no desktop screenshots. Workers may render their own pages to a picture with headless Edge and a throwaway profile, and the hub may use its built-in browser." Name the guard: `tests/helpers.py` stops if a data path leaves the temp folder.
- **Add D21 to D26** if Andy agrees (call 2).

### `docs/status.md`
- **:5, stale.** The heading says 2026-11-02 12:45 but holds items from 11-04 → "Right now (2026-11-04)".
- **:9, stale.** "D1-D18" → "D1-D20".
- **:15-18, :30, leftover.** These items are merged → archive.
- **:26-29, stale.** The "morning" plan to switch to lean or leaner has been overtaken → "Testing: light, by Andy's ear in Live, until the paid model; then full testing, safety first."
- **:31-36, stale.** The usage snapshot from 11-02 → delete. The hub doesn't report usage unasked.
- **:37-39, stale.** `installer2` is gone (`git worktree list` shows only audit1, M24-boards and M24-scene). The `.worktrees/M9d3` folder is still there, and seven merged branches remain: `other/M13b`, `M15`, `M15b`, `M4c`, `M4d`, `M9d3` and `M9d4`. → The hub removes them, then deletes these lines.
- **:43-141 ("Earlier"), leftover.** All of it is history → `docs/archive/status-2026-10.md`. Inside it:
  - :47, Mary "runs in talk mode Offline", is stale.
  - :101-111 are questions, most of them settled: pet names by D7, and the Gemini key is in Credential Manager (`CLAUDE.md:17`).
  - :122-129: five of the seven are decided (call 2).
  - :130-138 is a "Next" list that's all done or overtaken, and it has two items numbered "5."
  - :132 says "hub only until Nov 4"; that's permanent now.
  - :140, "the public `main` is still v0.2.0", contradicts D17 and :40.
- **:143-226 (build history), leftover** → archive. Carry the still-open items to the roadmap:
  - `wip/report-to-state` (:150-153, :223);
  - lid-to-Mary (:222), and its "full screen" becomes "maximized";
  - the pilot and funding plan (:225);
  - backend phase 1 (:226).
- **After the cut:** status holds "Right now", "Waiting on Andy" and "Next", at about 40 lines.

### `docs/mary-roadmap.md`
- **:1-3, stale.** The title is "after Andy's first try", and the helper line is old. → "Mary's Porch roadmap: what's ahead", plus one pointer to the how-we-work file.
- **:5-10 ("What Andy said" on 10-28), leftover** → archive with M1-M6.
- **Done items, leftover** → `docs/archive/roadmap-done.md`, keeping Andy's words and the commit ids:
  - M1-M6, M8, M12, M13/M13b, M17, M18, M19, M22, M4a-M4i and M21a-d;
  - the done parts of M7, M9 and M15.
  - The headings :23, :94 and :170 also carry retired roles: "(worker, Sonnet)" and "(worker, Sonnet then Haiku)".
- **:206, contradiction (D20).** "they're AI companions" → robots, in D20's words.
- **:226-227, stale.** M9c says "waiting for Andy to try it", and "Open: … 'forget my name' doesn't clear the name". That was merged 2026-10-31 (`status.md:66`).
- **:228-231, :234-236, :243, :334-339, :473-476, leftover** → one item, per call 5.
- **:303, stale.** The M15 heading says "idea… still being talked through", but M15a-d are merged. What's ahead is M15e-j (`messaging-plan.md:277-282`) and a real Gmail or Yahoo send (`status.md:135`).
- **:352, stale.** "boards first (on Andy's canvas)" → follows call 9.
- **:362, stale.** "Today: M15c keeps a small contact list inside the `messages` skill" → that's the M19 address book now (D10).
- **:513, stale.** The critic's "carved-wood folk art first" was overtaken by the cast Andy picked: worn enamel (`M24-boards.md:33`, `M24-scene.md:17`, `mockups/mary/concepts/README.md:7`). Say so, and keep the critic's grown-up rules.
- **:525, contradiction.** "(Earlier note:) Mary wasn't picked yet" contradicts :523 → delete.
- **:538, contradiction** → call 8.
- **:540, contradiction.** "No lightning flashes" contradicts Andy (:517) and the boards brief (`M24-boards.md:25`, :38) → "Lightning is a soft glow in the clouds, a few seconds apart, never a strobe (no more than three flashes a second), and no loud thunder. An emergency calms the sky." The default for real weather → call 6.
- **:555-568 (M10), leftover.** It plans "a grown-up drawn face", a cream background and a sitting room. M24 replaced it → archive, marked "superseded by M24". Keep M11, the reporting screens, ahead.
- **:571-578 ("Order and dependencies"), stale.** "M1 runs now" and so on → replace it with the current order: M24 scene, M24 build probe, the brain on the paid model, M25, M18b, M15e-j, speak-up S1 onward, the pilot.

### `docs/companion-plan.md` (proposed: split up, then archived)
- **:3, stale.** The status line is from 10-24.
- **:6 and :27, leftover.** "A friendly animated companion fills most of the screen" and "female… Her animated face fills most of the screen" → the M24 robots on the porch.
- **:21, contradiction (D20).** Use D20's wording.
- **:26-28** → call 10.
- **:33, stale.** "for example with openWakeWord". The wake word is built on Vosk (`tools/README.md:31`; `wakeword.py`).
- **:34, :60, :72, stale.** "Thinking: Gemini" → "the brain (Gemini today; the paid model is being chosen, M23)".
- **:54, stale.** "Mary opens full screen" → "opens maximized" (`desktop.py:176`).
- **:61, leftover.** "warm, patient and cheerful" → "warm and plain-spoken, like a normal neighbor", from Andy's "normal person" (`mary-roadmap.md:519`).
- **:102, stale.** "message and call screens are on the face canvas (round 2/3)" → overtaken by round 8 (M15b).
- **:113, stale.** In games, "her face turns in 3D… Andy chose this over shrinking her into a corner". What was built (M7a: the game beside her) and M18's corner replaced it.
- **:143-154 ("Next steps"), leftover.** Items 1, 2 and 4 are done. Items 3, 5, 6, 7 and 8 move to the roadmap.
- **Where the rest goes:** the laptop, rollout, pitch, costs and open questions (:52-57, :71-91, :137-141) → `pilot-checklist.md`. Family messages, games and "Mary and the computer" (:92-133) → the roadmap. Then archive what's left.

### `docs/backend-plan.md`
- **:3, stale.** "conversations… now go to Gemini" → "go to the brain's company (Gemini today)".
- **:6, stale.** "the online side of Care Incident Log" → "of Mary's Porch".

### `docs/messaging-plan.md`
- **:3, stale.** "No app code yet." M15a-d are merged, and `skills/messages/` exists.
- **:238-240, stale.** Contacts kept "in the skill's own store" → the address book, a core module (M19, D10).
- **:252, :254, stale.** Both are settled: the mission wording by decision 10 (:315, applied with the mission fix above), and the key is in Credential Manager. Delete :254, and point :252 at :315.
- **:271-282, leftover (D14).** The "Who" column says "Opus coder", "Opus, `xhigh`" and "Opus for code" → drop the column. Mark M15a-d done, with their commits.
- **:302** → follows call 5.

### `docs/speakup-plan.md`
- **:179 and the Model column :183-195, leftover (D14).** "Opus `coder` for new code" and "Opus xhigh" five times → drop, and point to the how-we-work file.
- **:190, stale.** S7, "Board worker on Andy's account" → a worker on the second account; Andy sees the boards per call 9.
- **:194, stale.** "Passes on real Gemini" → "on the real model".
- **:199-265, duplicate IDs.** The speak-up "D1-D10" clash with D1-D20 in `decisions.md`, and status calls them "decisions D1-D10" (`status.md:101`, :109) → rename them SD1-SD10 everywhere.

### `docs/pilot-checklist.md`
- **:16-17, stale.** Now speak-up S1 and S2 (`speakup-plan.md:184-185`).
- **:22, stale.** "Rebuild the installer, with `build.py` downloading the voice model" → done (`CLAUDE.md:28`, v0.5.0).
- **:3, leftover.** It still needs its companion pass. Add:
  - the paid tier for residents;
  - the safety pass on the real model;
  - `wake.log` keeping only a word count;
  - a Windows PIN at setup (M19 answers);
  - real weather's town at setup (if call 6 is A);
  - the laptop items from the companion plan.

### `docs/characters/mary.md` and `sam.md`
- **`mary.md:39`, :239, contradiction (D7)** → call 3, then use D7's wording.
- **`mary.md:138-141`, :238, and `sam.md:155-158`, :238, :240, contradiction (D20).** "I'm an AI, but I'm your friend" → "No, I'm not a person. I'm a robot, what some folks call AI, but I'm your friend." Keep "never claims a human past". Also `mary.md:220`, the sample "Why do you sound like a robot?": rewrite it after call 4.
- **`mary.md:235`** → call 4.
- **`:2` in both, stale.** Add under the status: "Identity and pet-name lines updated for D7 and D20 (date); the full rewrite comes with the paid model."

### `README.md`
- **:36, stale.** "She can't change a person's phone number by voice yet (M22)." M22 was merged 2026-11-02 (`status.md:16`).
- **:46 and :143-144, stale.** "Next: rebuild her conversation (M21)" and "Let her fill the forms (M22)". M21a-d and M22 are merged. What's next is the porch (M24) and the brain on a paid model.
- **:83, contradiction (D20).** "She's an AI, and says so." → "On screen she's a robot, and she never pretends to be a person; asked straight out, she says she's what folks call AI." The rest of the line stays.
- **:20, stale once M24 lands.** "Her face and captions are on screen" is true today; update it with M24.

### `docs/README.md`
- **:15, stale.** The roadmap is "from the first try of Mary" → "What's ahead".
- **:16** → companion plan moves to the archive after the split.
- **Add** a row for the how-we-work file.
- **:34, stale.** "Open briefs sit here", but six finished briefs sit there (below).

### `docs/handoff/`
- **Finished and merged, so move them to `done/`:** `M21a.md`, `M21a2.md`, `M21b.md`, `M21c.md`, `M21d.md` and `repo1.md` (their DONE and merge commits are on `main`).
- **`M24-boards.md`** stays until the hub settles `other/M24-boards`, which is kept and not merged (`mary-roadmap.md:530`). Its radio table → call 7.

### `skills/README.md`
- **:8, stale.** "Their address book is here too." The book is a core module (`address_book.py`, M19), and `messages` reaches it through `ctx.people`.

### `mockups/README.md`
- **:62-79, stale.** It doesn't mention `mary/concepts/` (the M24 cast Andy picked), or that rounds 11 and 12 live on branches until they're merged. Mark rounds 2-10's face look as being replaced by M24. They still document screens that are built.

### Code comments found on the way (no change made)
- **`desktop.py:4-5`, stale.** "Mary's full-screen window" and "the voice audition page, full screen". Both open maximized (`desktop.py:176-178`).

---

## Duplication: one owner for each rule
| Rule | Where it's kept today | Owner |
|---|---|---|
| Who runs what: accounts, workers, helper models, effort, context limits | `CLAUDE.md:44-69`, `_common.md:10-17`, D14, `mission.md:34-38`, `mary-roadmap.md:3`, `speakup-plan.md:179`, `messaging-plan.md:271-282`, the token-saving skill (`private/audit-inputs/token-saving-SKILL.md:13-15`, :24-27, :51), the hub's memory `feedback-working-method.md` | **the how-we-work file.** D14 keeps only the decision. The skill keeps only the general method. |
| The browser and screenshot rule | `CLAUDE.md:49`, `_common.md:25`, D15, `private/audit-inputs/global-CLAUDE.md:7`, `private/audit-inputs/token-saving-SKILL.md:28`, memory `feedback-browser-rule.md`, `feedback-working-method.md` | **D15** (the decision), with how to do it in the how-we-work file |
| Scratch data only | `CLAUDE.md:49`, `_common.md:24`, D15 | **D15** |
| Politics | `mission.md:17`, `mary.md` answer 10, `_common.md:8` (wrong), memory `feedback-southern-values.md` | **`mission.md`** (the short form) and **`mary.md`** answer 10 (the full wording) |
| Who Mary and Sam are | `CLAUDE.md:11`, `_common.md:7`, `mission.md:9`, :19, `README.md:5`, :83, `companion-plan.md:6`, :27, D20, M24 | **`mission.md`** (one line) and **D20** |
| 20px text, 64px targets, voice or one big tap | `CLAUDE.md:14`, `mission.md:28`, `_common.md:27`, `README.md:157` | **`mission.md`**. The README stays as the public copy. |
| Quality first | `CLAUDE.md:51`, `mission.md:25`, the skill, memory | **`mission.md`** |
| Tests and checkpoints | `CLAUDE.md:50`, `_common.md:21-22`, `README.md:158` | **the how-we-work file**. The README stays public. |
| The hub keeps status current | `CLAUDE.md:52`, `status.md:3`, `mission.md:35` | **the how-we-work file** |
| Publishing `main` | D17, `status.md:40`, :140 (wrong) | **D17** |
| Open questions for Andy | `status.md:17`, :101-111, :122-129, `speakup-plan.md:199`, roadmap items | **status's "Waiting on Andy" list** (the details stay in the plan) |

## The proposed structure
| Kind of thing | One home | What moves in | What moves out |
|---|---|---|---|
| **Why** | `docs/mission.md` | the five principles from `companion-plan.md:15-23`; the identity line per D20 | the how-to-work lines (:34-38) become one pointer |
| **Andy's standing rules, each with a guard** | `docs/decisions.md` | D21-D26 (call 2); D14 and D15 reworded | nothing |
| **Now and next** | `docs/status.md`, about 40 lines: "Right now", "Waiting on Andy", "Next" | the open questions from every plan | "Earlier" and "Build history" → `docs/archive/status-2026-10.md` |
| **What's ahead** | `docs/mary-roadmap.md` (keep the file name so links hold; retitle it) | the open items from `status.md:143-226` and from `companion-plan.md` (games, Mary and the computer, family calls, lid to Mary, setup tool, laptop spec), `wip/report-to-state`, one brain item (call 5) | every done item → `docs/archive/roadmap-done.md`; M10 → the archive, "superseded by M24" |
| **Plans by topic** | `messaging-plan.md`, `speakup-plan.md`, `backend-plan.md`, `pilot-checklist.md` | the laptop, rollout and costs from `companion-plan.md` → `pilot-checklist.md` | `companion-plan.md` → the archive once it's split |
| **Reference** | `skills-design.md`, `how-to-make-a-skill.md`, `retaliation.md`, `speakup-review.md`, `characters/` | nothing | nothing. Tests cite `docs/skills-design.md` and `docs/decisions.md` by path (`tests/test_skills_*.py`, `tests/test_decisions.py:3`, :8), so keep those paths. |
| **Done or dropped** | `docs/archive/` (each file says why at its top, as the two there do) and `docs/handoff/done/` | the above, plus the six finished briefs | nothing |
| **How we work** | **new `docs/how-we-work.md`**. It covers the hub, workers on the second account (the one start command, the watcher, the merge), helpers and models, effort, context limits, the browser, scratch data, checkpoints, reports and boards. | `CLAUDE.md:44-69`; `_common.md:10-31` | `CLAUDE.md` keeps the code map plus one pointer. `_common.md` becomes three lines: read `how-we-work.md`, `mission.md` and `decisions.md`. Or it's renamed to `how-we-work.md` and the briefs point there. |

**Why one how-we-work file:** today the rules change in `CLAUDE.md`, `_common.md`, D14 and memory one at a time, and the old wording survives in whichever copy was missed. That's how "never xhigh" and "politics off limits" lived on.

---

## Tests that pin retired choices
- **`tests/test_m4c.py:85-95` (`test_each_voice`)** pins the full brain's "unless they ask", the pet-name ban, and Sam's "ask first". D7 retired that. **`tests/test_m4c.py:46-52` (`test_note_shape`)** requires "honey" and "sugar" in `CHARACTER_NOTE`, the banned list at `mary.py:1612`. Under call 3 A, both leave with the full brain.
- **`tests/test_desktop_start.py:261`:** the name `test_voices_window_is_full_screen_and_ready_once_it_shows` is stale, though it asserts maximized (:270). Rename it only.
- **No guard yet for D19 or D20** (`decisions.md:14-15` say so). No brain file says "robot" yet. Tests that will need updating with the identity line, though they aren't retired now: `tests/test_m21d_leaner.py` (lean pinned byte for byte) and `tests/test_decisions.py:56` (`LEANER_CHOICES`).
- **Checked, and nothing pins them:** politics off limits, Mary as a woman's face, full screen, Sonnet workers, `xhigh`.

---

## Edits to instruction files (may need Andy's approval)

### Project `CLAUDE.md`
- **:3, stale.** It describes the old incident tracker → "Mary's Porch: a companion for nursing-home residents (Mary and Sam, two 1950s robots on a porch swing), with a formal care log and state reports built in. The code still says Care Incident Log."
- **:11, leftover.** "A friendly animated AI companion named Mary (Gemini)" → robots (D20), with the brain on Gemini today and a paid model being chosen.
- **:28, stale.** "v0.3.0 (2026-10-30): installer 334 MB, zip 397 MB" → "v0.5.0 (2026-11-02): installer 336 MB, zip 401 MB" (`dist\` in the main checkout).
- **:32-34, stale and broken.** The path `C:\Program Files\nodejs` was split by a line break in two places: the `\n` turned into a real newline. Restore it. Also, "`gh`, **not signed in yet**" → signed in as sketch2626 (`gh auth status`), and commits use the no-reply email (`git config user.email`).
- **:44-69 → the how-we-work file,** and fix these on the way:
  - :46, `start_session` "local" is retired;
  - :47, the whole bullet is a leftover (workers here on Sonnet, boards here);
  - :48, "Sonnet on Andy's account";
  - :49, the browser rule;
  - :56, "workers here" and "no Design canvas… boards stay on Andy's account";
  - :61, two start commands where one is enough: keep `claude "Read docs/handoff/<item>.md and follow it." --model opus --strict-mcp-config --permission-mode auto`;
  - :65, "never `xhigh`";
  - :66, the "Opus at `xhigh`" reading of the audit (D14 fixed it);
  - :69, "a worker here and the other account".
  - Keep "never two workers on the same files at once"; that still matters on one account.
- **:52** keep as "if the hub is ever restarted". The hub's memory says one hub, compacted by hand.

### `docs/handoff/_common.md`
- **:6, stale.** "Care Incident Log" → Mary's Porch.
- **:7, leftover.** "warm, full-screen AI companions (Gemini)" → "1950s robots on a porch swing, who call themselves robots (D20). Her window opens maximized. Her brain is Gemini today; a paid model is being chosen."
- **:8, contradiction.** "only politics is off limits". It's the opposite: politics is welcome, and she's a good listener who's never a yes-man and never a debater (`mission.md:17`).
- **:14-15, leftover (D14).** "never `xhigh`", and "Opus helpers at `xhigh` were two thirds" → "many Opus helpers, not effort". Add: design and graphics run at extra-high effort.
- **:25, stale.** "No browser, computer use or screenshots" → D15's new wording (headless Edge with a throwaway profile is fine).
- **Then** it shrinks to a pointer, or becomes `docs/how-we-work.md` (structure section).

### Andy's global instructions (`private/audit-inputs/global-CLAUDE.md`)
- **Line 7:** the browser rule is out of date for this project (D15 as fixed). This file covers every project, so Andy decides whether the new wording goes here or only into each project's file.

### The token-saving skill (`private/audit-inputs/token-saving-SKILL.md`)
It's shared with Andy Flow, so keep it general and move this project's specifics into the how-we-work file.
- **Lines 15 and 51:** the helper split contradicts line 26 and this project's rule (Sonnet `coder` for all code; Haiku only for text).
- **Line 26:** the "xhigh" reading of the audit (D14).
- **Line 28:** the browser rule (D15).
- **Lines 14, 30, 38 and 44:** how workers start, and how the hub hears back. This project uses terminal workers on the second account with a background watcher.
- **Line 35:** where the next item is read. This project keeps it in `docs/status.md`.
- **Line 46:** "a fresh hub" contradicts the hub's memory `feedback-no-fresh-hub-push.md` (one hub; compact by hand).

### The hub's memory (`C:\Users\Andyb\.claude\projects\C--Users-Andyb-Operation-Save-Grandma\memory\`)
- **`feedback-working-method.md` and its `MEMORY.md` line:** "workers run Sonnet" on his account, "never `xhigh`", and "no browser… unless he asks" are all retired.
- **`feedback-hub-only-account.md`:** "for the next few days" and "ask Andy before going back to running workers here" → permanent; desktop-app workers are retired.
- **`feedback-boards-on-canvas.md`** → follows call 9.
