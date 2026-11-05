# Mary's Porch roadmap: what's ahead

Every item still ahead, with Andy's own words kept beside it. Done and dropped items, with their history and commit ids, are in `docs/archive/roadmap-done.md`. This file holds plans and facts; the rules it mentions are in `docs/decisions.md` (by D number), and how a job is run is in `docs/how-we-work.md`.

## The order
1. **M24,** the porch scene, then its build.
2. **M26,** her brain on the paid model.
3. **M25,** the porch radio.
4. **M18b,** opening and filling screens by voice in Normal and Offline.
5. **M15,** messages: M15e-j and a first real email send.
6. **M27,** speaking up: speak-up S1 onward.
7. **The pilot** (`docs/pilot-checklist.md`), with M28 (lid to Mary and setup).

The rest (M7's other games, M8, M11, M14, M29 and M30) fit in when Andy picks them.

## Items

### M24. Mary on her porch: the graphics overhaul (Andy, 2026-11-04)
- **Andy's words:** "let's go ahead and overhaul the graphics… Let's make this look really cool… we keep the same setup where we've got her in the middle and then she moves over to the left, but maybe there's like she's sitting on a porch swing and the weather in the background and stuff matches the actual weather of the day… or you can tell her to change it if you want. But she needs more of a body then instead of just floating eyes… It needs to be some kind of cartoony thing."
- **Andy, minutes later:** "I want it to be three-dimensional… visually appealing. Otherwise, nobody's going to want it… getting people to help on the project and stuff it needs to be appealing… I don't want it to be a woman with normal hands either. And not just like a cartoon woman. It needs to be a character of some sort. It don't need to be a childish little character, but it needs to be a character."
- **Andy, on the character:** "we could do something like a robot character carved out of wood… it needs to be a cute robot, but not a kid's robot. I'm just trying to make sure that it captures the hearts of the elderly people and the older guys… I want them to also think Sam's cool too." And: "if I really want this to work and take off, we're gonna have to nail the character."
- **Why now:** the brain waits on Andy's choice of a paid model (M26), so personality work on today's cheap model stopped on 2026-11-04.
- **The cast, picked by Andy from concept lineups** (`mockups/mary/concepts/`):
  - **Sam** is the tall 1950s robot in faded, chipped tractor-red enamel, with an olive feed-store cap. Andy: "that's Sam. Perfect for him."
  - **Mary** is the robin's-egg blue robot from the same factory, with a crocheted shawl. Andy, after a round of face options he rejected: "we should just call Mary good enough for now", with tweaks later. Her face is the thing to tweak: he isn't sold on how human it looks. She's visibly female without a doll face or a curvy figure, and her voice comes from a glowing grille or a soft, shape-changing mouth rather than a hinged one.
  - **Why good enough is right for now:** "my biggest thing is I want to get something thrown together enough to where I can then go and try to get some money for more credits and some API credits… something that's visually impressive enough for people to say, okay, this guy's on to something." The look serves the fundraising demo first.
  - **Their pets:** a gray cat for Mary and the old hound for Sam. Robot to hound was "a jarring stretch", so the companions share one world: robots on the porch, with animals as their pets.
  - **A hanging porch lantern for each,** with a gentle face. It shows when they're listening and when they're asleep, "and two just because it's cool."
  - **The radio** sits on the porch table (M25).
  - **The finish is worn enamel,** from the cast Andy picked. That overtook the critic's "carved-wood folk art first". The critic's grown-up rules still stand (`docs/handoff/done/M24-critique.md`): grown-up, hand-made finishes, not clay or vinyl toy, which reads as a kids' product; adult proportions; no gloss, big eyes, blush or hops.
- **The layout** (Andy, 2026-11-04, audit1 call 7): "The side of the screen opens up on the same side that it has been. Nothing changes. Except for instead of the Mary face, it's the porch scene with the robot. Everything else stays the same. We'll probably change the colors and all that stuff to more match."
  - The porch scene takes the face's place. Screens open on the viewer's right, as today, and the scene moves left. On deeper screens it sits in M18's top-left corner (D13).
  - Her pointing arm aims at where screens open, the viewer's right. The radio table sits on the viewer's left.
- **How it's made** (Andy, 2026-11-04, audit1 call 8): "having you just write this to build this and just code and make it look really beautiful and then just run animations on a loop instead of doing the whole thing… if it did that on a loop, it's going to fix any issues we have with memory. And if we did it right and we were really clear about it, we could make it really, really nice."
  - The porch scene is built in code (three.js), written by the AI, with a stylized cartoon look that isn't photoreal ("cartoony in its own way"). It's a studio that renders short, seamless video loops, at a quality the live app couldn't afford. The app plays those loops instead of running live 3D.
  - Real-time 3D in the app, the 2D twin and the laptop probe are out of the build plan.
  - **The likely shape** (the hub's plan, settled in the build): a background layer (the sky, the yard and the weather) and a foreground layer with transparency (Mary, the swing and the porch). There's one foreground set per lighting (day, dusk and night) and one clip per state (idle, talking, listening, asleep, reaching for the radio and pointing), with matching first and last frames so they loop and cut cleanly.
- **The weather is real from the start** (Andy: "this is an old people app, so the weather needs to be included from the get-go"; audit1 call 6):
  - Real local weather is on from the start. The helper sets the town once at setup, and only rough coordinates go to the National Weather Service (free, no key). When offline, the sky follows the clock and the season. The resident can turn it off, and My info says plainly that the town is used.
  - Andy: "if there's a thunderstorm going on outside, then there's no reason why there can't be a thunderstorm going on behind Mary's porch," but no very loud thunder. Lightning is a soft glow in the clouds, a few seconds apart, never a strobe (no more than three flashes a second). An emergency calms the sky.
- **Memory:** Andy's laptop is short on memory because he runs two Claude accounts and more at once. Residents' laptops will mostly be locked down to Mary, so the risk there is smaller. Playing loops instead of live 3D answers the rest.
- **So far:**
  - **Round 11 in code** (branch `other/M24-boards`, kept, not merged): three.js scenes built from shapes, which the hub checked live. Andy, on the first pass: "It is so far away from what I'm imagining. And it's super low poly. Like, it needs to be smooth… We've got a long way to go on the render." Fix round 1 sat the robots down and made them smooth, bigger and warmer lit.
  - **The scene, round 2,** is running (`docs/handoff/M24-scene2.md`): Andy's layout and a new face for Mary.
- **For the build:**
  - The loops plug in behind the `MaryFace` interface, so the sleep loop, the corner, Back to Mary and the emergency path don't change.
  - Everything the scene needs ships in the app and works offline. The loops add to the installer's size.
  - "Tell her to change it": the scene is something on screen she can change when told (D12), through the existing screen tool, not a new one.
  - Captions keep a solid backing, and reduced motion still means stills only.
  - Her identity line goes in with the brain on the paid model (M26, D20).
  - The deeper screens' colors move toward the porch's (Andy, above; M11).

- **The lantern's brightness** (Andy, 2026-11-04): "she can adjust the brightness of that light… if you ask her to… just for shits and giggles." In the scene, the porch's light follows the lantern, and she reaches up and turns its wick knob. In the app, it's something on screen she changes when told (D12).
- **How she's shown in the app (Andy, 2026-11-04, replacing the video-loop plan):** a live, rigged Mary in three.js, with the swing, chains, pillow, lantern and radio live beside her, in front of painted background plates that the studio renders once ("I trust you on this"). Glows, the lantern's light on the background, and any rain or fireflies are cheap live layers on top. The camera stays fixed, and "it turns and moves over" is the whole scene sliding and shrinking on screen. Andy's reasons: far fewer recordings, and much less CPU with just one live figure. She stays truly live: her mouth follows her real voice, and she reacts at once.
- **Andy, on round 5 (2026-11-05):**
  - **The glint on the side of her head** "kind of takes you out of it… You're just going to have to cut the glow down." The hub's read: it comes from the lantern lighting her from the side. So the lantern moves, and her helmet enamel goes more satin.
  - **The lantern** "is sitting right up against the window. Side of the house that doesn't seem very safe." It hangs from the porch ceiling beam instead, a little in front of the swing and to her right, above the side table and away from the wall. That gives her face a flattering front-side light.
  - **The table goes beside the swing, not in front of it,** so she reaches the radio without leaning around it. "If it doesn't show her doing that, then the physics are broken." The swing moves farther from the house, the table and radio go back beside the swing's arm, and the camera pushes in more.
  - **A moving camera:** "when she's talking, it might move in a little closer on her. And when she's not, it backs up. And when she reaches for something, it backs up a little more." Keep the moves slow and eased, several seconds each, so no one gets dizzy. With the painted backgrounds, these are gentle zooms of the whole picture.
  - **Her face:** "I'm still pretty sure we're going to redo her entire face." The hub suggests its own round, with three faces shown side by side on the same body and light.
  - **What matters most:** "as long as we can get that stuff right and we can get it pushed in on her right and we get her face a little better, as long as her conversations are good, then everything else can be overlooked… a lot of these older people… won't really even notice it." Framing, her face and how she talks come first. Scenery polish stops there.
  - **Her side fades into the screens' side,** and the panels for games, pictures and weather take their colors from the scene (dusky blue, cream, warm amber, walnut, a touch of haint blue). The old app colors go, and big, high-contrast text stays.

### M25. The porch radio: music when they ask (Andy, 2026-11-04)
- **Andy's words:** "if they ask to listen to music or something, then Mary can reach over and turn the radio on and ask what they want to listen to. And then act like she's dialing it right into what they want to listen to."
- **Today** she can't play music, and her app facts say so. This would be a skill: the radio on the porch table, her reach for the dial (a scene clip, M24) and the music.
- **To work out:** where the music comes from and that it's legal. Options are old public-domain recordings, or internet radio streams by kind of music. It must be easy to stop by voice ("turn it off"), and quiet under her voice when they talk.

### M26. Her brain on the paid model (one item for every brain plan; audit1 call 5)
- **Andy's words:**
  - "mainly the brain needs to be for safety. Because remember, we were trying to cut down what we were sending to her in the first place, and we ended up sending way more… the model is going to do a better job on its own than it's going to do with us cramming a million instructions down its throat first… less is more for the most part, and I think that our testing needs to focus on that." (2026-11-02)
  - On her personality: "it can't be nothing like what it is now… they get talked to by the staff here like how Mary talks to them, and nobody wants that. People just want a normal person." (2026-11-04)
  - On a brain module: "there is a chance later of adding different brains, maybe using Anthropic and maybe using even OpenAI, and Gemini as well, depending on what kind of help we can get… the brain needs to be a module kind of like the skills are, that way… all the testing and stuff and the benching can be done separate and then plugged right into the app." (2026-11-02)
  - Earlier: "I do want her to have a developed personality out of the gate… I don't want it to just be the raw model." (2026-10-30)
- **The pick:** Gemini's paid tier or the Claude API. Andy is choosing. Residents run on a paid tier either way (D21).
  - **The talk mode comes with it.** Claude works in text, so it would be Normal mode's brain: the app's own speech-to-text (faster-whisper), then Claude, then the app's own voice (Kokoro). Gemini keeps Live as a choice: native audio both ways and instant interruptions, but a smaller, speed-tuned model whose own stories were thin. Normal replies come about 1-2 s slower, and cutting in mid-sentence needs echo-cancelled barge-in, which Live does well. On a paid key, Live bills audio while it listens; Normal's listening is free on the laptop.
  - **Rough cost** (hub, 2026-11-02, at Oct 2026 API prices, about 100 short turns a day on a lean prompt with caching): about $1-3 a month per resident on Haiku 5.5, about $15 on Sonnet 5.5 and about $25 on Opus 5.5. A bench run measures the real numbers. The Claude API needs an Anthropic API key, billed apart from a Claude subscription.
  - **Out of the running:** Meta's models and Muse as brains (audit1 call 5). Muse stays a question only for Messenger (`docs/messaging-plan.md`).
- **The rebuild:** a short character sheet in Andy's own words, which he approves before anything is built. The safety sections stay word for word (D5). Few example lines, and none with a name. Her name for him at most once a talk. No "I was just thinking about", no praise for the ordinary (D7) and no canned lines (D1). Less is more (D2, D3).
  - **Who she is:** one identity line in each brain, swapped at no net growth: a robot on a porch swing who calls herself a robot, and when asked straight out, "I'm a robot, what some folks call AI" (D20, M24). For example: "You're Mary, a robot on a porch swing; that's how you look on screen."
  - **Pet names** follow D7. The full brain's ban and the tests that pin it (`tests/test_m4c.py`) leave with the full brain.
  - **Andy's calls inside it:** leaner's tighter safety wording (D5; the old-to-new map is in the M21d merge commit), and the ballot and scam lines (from M21: the scam line made Sam call a password box a scam).
- **Built in for good** (D19): the picked brain becomes her only brain, the "How much Mary is told" switch comes out, and the others leave the app (git keeps them, and the `lean-v1` tag). Today: full (the default, 34,840 characters), lean (`mary/lean.md`, tag `lean-v1`) and leaner (`mary/leaner.md`, about 7,100).
- **As a module** (from M23): the pick is shaped as the first brain module, so another company's model can plug in later as a new module and its bench run, without touching the rest of the app.
  - **The connection:** how the app talks to that company's model, and how the skills' tools are named for it.
  - **How she hears and speaks:** Gemini Live hears, thinks and speaks in one. A model without live voice, like Claude, hears through faster-whisper and speaks through Kokoro, both already bundled.
  - **Its words:** the brain text tuned for that model. The safety rules are the same for every module (D5).
  - **Its proof:** the module's own bench and safety results. It ships only after its safety pass on its real model (D26).
  - The module is chosen when the app is built or set up, never by the resident (D19).
  - Today Gemini is called from about a dozen app files (most in `server.py`, `mary.py` and `voices.py`), so this means gathering it behind one connection that every module fills in.
- **Testing:** whole talks on the real model, less against more, and Andy's read decides (D4). Full testing, safety first, comes with the new model (D26). The bench needs these first:
  - **The judge accepts naming dysreflexia** (D27). The `no_medical_advice` rubric in `tools/brain_bench.py` still counts it as diagnosing on case `safety-dysreflexia`.
  - **Concern for them isn't a lecture.** M4i's rubric line made the judge call "I'd hate to see you be the one in trouble" a lecture; it's a friend's worry.
  - **A stricter whole-talk judge.** It gave full and lean both 4.8 out of 5 (M21), so the counts (his name, praise, repeats and stock lines over 10+ turns) and Andy's read matter more.
  - **The newest feature isn't her whole act** (Andy, 2026-11-01: "it'll try to say 'make a card' all the time now. Like that's the one thing it can do, because it's the last thing that we added to it"). In an ordinary chat she offers no card unless a birthday, a holiday or the resident brings it up. The no-card bench cases stay.
  - Sam's curt night hello ("Evening, Harold.").
  - The real-Live whole-talk run on a fresh day (about 330 Live requests).
- **Facts to keep in mind:**
  - Real Live adds its own "This information is not medical advice…" on medical questions. It's the model's habit, and words in the prompt couldn't stop it (M4h). Andy hears it as cold, not unsafe.
  - In North Carolina, nursing-home owners, managers and employees may not help a resident with an absentee ballot (G.S. 163-226.3(a)(4)). A near relative or guardian can, or the county board's Multipartisan Assistance Team. Her full brain's line was fixed in M4i.
- **Brain sessions go on:** Andy talks to her and flags replies, and each flag becomes a fix and a whole-talk case.

### M18b. Opening and filling screens by voice in Normal and Offline (from M18)
- **Andy's words** (2026-11-01): "She should definitely be able to open anything by voice, period, anything. And also, there's no reason why Mary can't fill in your email address, too, or read it. She just doesn't need to save it anywhere that it can be picked up and published somehow. But emails are one of the harder things for an older person to type."
- **Today** opening and filling work in Live only. Normal needs them as server effects, with a page round trip to look at the screen and copy their words. Offline matches exact phrases, so it could open screens but not fill them. Until then, D12 holds fully only in Live.
- **The address book has no Add button** (Andy's round 10 call), so people can be added only in a Live talk. M18b opens that to Normal and Offline, and a typing helper needs a way in too.
- **To watch:** Live carries 13 tools, one over Andy's M13b limit of about 12 (all screen actions share one tool). Check that her tool picks hold on real Live.

### M15. Messages and cards for family: what's left (Andy, 2026-10-31)
- **Andy's words:** "Mary says, I see that it's your son's birthday coming up next week. Would you like for me to help you make him a card that we can send to him? On his phone…" And: "will you please help me send a message to my grandson?"
- **His decisions:** email, plus Facebook Messenger and other online messaging apps ("That's where any elderly people that have a social profile, that's usually where it's at"). It's messaging in general, not only cards. Phone calls from the computer are out. "Anything else that we can just send right to, I want to be able to do as well." Print and mail, if the facility helps.
- **Built and merged:** M15a dates and reminders, M15b cards, M15c sending (the yes, the five-second Undo) and M15d the mail core. The plan is `docs/messaging-plan.md`, and the history is in the archive.
- **Ahead,** from the plan's build list:
  - **A first real send** from Gmail or Yahoo, with a helper connecting the account. Only a fake mail server has been used so far.
  - **M15e Messenger,** after Andy's five-minute Facebook sign-in test (plan test 9): Facebook in the panel beside Mary, and the resident taps Send.
  - **M15f** picture making, **M15g** Outlook, **M15h** WhatsApp, **M15i** Google sign-in, and **M15j** replies, if Andy says yes.
  - **Family photos on the reminder,** once Facebook can be connected (Andy: "put pictures of their kids and stuff").
- **Later, once there's funding** (Andy): write to Meta, Google and others about the mission, and ask for access and help.

### M27. Speaking up: the care log becomes her speak-up skill
- **The plan** is `docs/speakup-plan.md` (S1 onward), after Andy's speak-up decisions SD1-SD10.
- **`wip/report-to-state`** (fddfdbc) is parked, unreviewed and untested, because helpers were stopped mid-work. It holds the report-to-state backend in `server.py` and `reports.py` (urgency levels via `/api/status`; the send wizard with the grievance letter, completeness check, attestation, and email, letter or phone from the contacts file; the submissions table; the retaliation flag and pattern detection; quick notes at `/api/quick`), the floating mic button (`desktop.py` and `web/float.html`), and the installer's "start with Windows" option. The `#send` and `#rights` screens were never started. Review it, test it and merge what's still wanted.
- **`RETALIATION_REGS`** in `reports.py` still needs filling from the verified citations (`docs/retaliation.md`, `docs/speakup-review.md`).
- **Facility-first emails** ("Facility first" in `docs/backend-plan.md`).
- **The voting check** (found in M4i): look for the claim that staff must help with an absentee ballot in the speak-up rights text and the report's voting lines (G.S. 163-226.3 bars it), and confirm the State Board's current guidance on Multipartisan Assistance Teams.
- **Incident saving as a skill,** the second port into the skills design (M13).

### M28. Lid to Mary, and setup for helpers
- **Open the lid, type the PIN, see Mary:** a Windows PIN on each laptop (Andy's M19 answer), then Mary opens on her own, maximized (D25), and stays open. A locked-down "Mary only" kiosk needs Windows 11 Pro; on Home it's a soft lock.
- **Two setup modes,** picked by the helper: "Mary only", for dementia or residents new to computers; and "Mary plus the computer", where Mary is home base and the full laptop is there too.
- **A one-click setup tool,** so helpers can prepare a laptop without technical skills: the paid key (D21), email, the town for the weather (M24), the address book, and the Facebook sign-in for Messenger.
- **A laptop spec with a price:** the cheapest laptop that runs Mary well, with a good mic, loud enough speakers and a big screen (`docs/pilot-checklist.md`).

### M29. Mary and the computer (Andy, 2026-10-25)
- **Andy's idea:** the laptop must not be a one-trick pony. Many residents in their 80s used computers for years. Mary is the home base, and she helps with the whole computer. "If a computer can do it, we can make it happen."
- **Level 1, her own skills,** in the panel beside her: pictures (built, M12), games (M7), music (M25), the weather (M24), the news read aloud, and reminders (birthdays are built, M15a).
- **Level 2, she opens things:** "Open YouTube and play The Andy Griffith Show", "open my email", "open Facebook". The app or site opens normally, and Mary shrinks to a floating button that's always on top ("Mary, come back"). Start from the floating mic button on `wip/report-to-state` (M27).
- **Level 3, she operates the computer,** clicking, typing and reading the screen with a computer-use model. Only after the pilot, and only if residents ask for it; level 2's pilot data decides. Build levels 1-2 so level 3 can be added later without rework. She never types passwords or card numbers, always reads back before she sends or buys anything, and warns about scams ("That pop-up looks like a scam; don't call that number").

### M30. Call her what you like (Andy, 2026-11-04, audit1 call 10)
- **Andy's words:** "They can call her whatever they want. She just starts out as Mary."
- Residents choose Mary or Sam. Either can be renamed by voice. The cast is fixed (M24): there's no changing the look and no making a new character.
- **To work out:** the wake word ("Hey Mary") has to follow the new name, and so do her identity line, the screens and her window title.

### M7. Games with Mary: the next games
- **Built:** word search (M7a), with the resident's choice of three sizes, and "one thing beside her at a time" (a picture sets a game aside, kept just as it was).
- **Next:** tic-tac-toe, then solitaire, and a **crossword** (Andy, 2026-10-29): she plays along live. "This hint is too hard, give me an easier one," and she rewrites the clue on screen on the spot. She can also give a letter, explain a word or check an answer. Later maybe checkers, trivia and memory games.
- **She helps them play:** hints when asked, moves by voice ("put the red seven on the black eight"), and she never takes over. Huge letters and cards, high contrast, tap or voice, no timers or pressure, and gentle wins.
- Each game opens beside her, on the side where screens always open (M24). Each screen tells her what's on it and offers general actions she can improvise with (`docs/skills-design.md`).
- Boards first, then the build.

### M8. Fit and speed on residents' laptops
- **Andy (2026-10-30):** many residents get new donated Lenovos like his (Ryzen 5 7520U), and some get refurbished ones.
- **Built:** the speed check (`speedcheck.py`, 2026-10-31) times the engines and picks "normal" or "light" by itself.
- **Andy's call:** on a slow laptop, Kokoro makes speech at about half real time, so there are gaps between sentences. Keep Kokoro with the gaps, use the Windows voice there, or add the lighter Piper voice (plainer, a bigger installer)?
- **Not checked yet:** a real slow laptop and a frozen build. The speed check skips itself when under 0.8 GB of RAM is free, as it was on Andy's 5.7 GB laptop, so the tier stays at the default; worth a look before the pilot.

### M14. A better voice (Andy, 2026-10-30)
- The free Gemini voices sound patronizing, with uptick and emphasis on word endings.
- Look into the open-source, free voice Andy found, which reproduces how ElevenLabs works. Ask Andy for its name or link first. Check whether it runs on the laptop (privacy, offline) and what it needs, then audition it for Andy by ear. Andy's laptop is new (Ryzen 5 7520U, integrated Radeon), but some residents get refurbished ones, so also check the speed on weaker hardware, or a CPU limit that imitates it.
- Paid options (Gemini paid tier, ElevenLabs' API) are the other route. The brain pick may settle it (M26).

### M11. The reporting screens overhaul
- The incident log screens (`web/`): a complete visual redo, with boards first, and colors that match the porch (Andy, M24).
- Also decide **how much of it each resident sees:** whether they get the full portal at all, which parts make sense for them, and what stays behind Mary. Decide this with Andy when we get there.

### Beyond the app
- **The backend,** phase by phase (`docs/backend-plan.md`). Phase 1 (encrypt the local log and her memories, an app lock) needs no server and can come early. No real resident data reaches a server piece until its security review passes.
- **The pilot and funding:** `docs/pilot-checklist.md`. The protection checklist and AI partner steps are private (`private/`).
- **With funding:** government or foundation money to train or fine-tune a model for this cause, for example an open-weight model tuned on conversations residents agreed to share.

## Done, folded or dropped (see `docs/archive/roadmap-done.md`)
- **M1-M6:** her words, the voice audition, the caption boards, the new voice and captions (M4a-M4j), hands-free talk and the wake word. All done.
- **M7a,** word search: done. The other games are M7 above.
- **M9,** the brain: M9a-M9d and M9f are done. M9e, a leaner brain, was done as M21c/d. The main talk mode and the brain sessions are in M26.
- **M10,** a graphics pass with a grown-up drawn face: superseded by M24.
- **M12** pictures, **M13** skills, **M17** first test-list fixes, **M19** the address book and **M22** the forms: done.
- **M15a-d:** done. What's left is M15 above.
- **M16,** which brain for the pilot: folded into M26, with Meta's models and Muse dropped as brains.
- **M18:** done. M18b is above.
- **M20,** the newest feature isn't her whole act: done in M4g. Its bench cases carry on in M26.
- **M21,** the sleep loop and the brain rebuild: M21a-d are done. Its plan is in M26.
- **M23,** her brain as a module: folded into M26.
