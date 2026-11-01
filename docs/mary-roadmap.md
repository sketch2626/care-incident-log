# Mary roadmap (after Andy's first try, 2026-10-28)

Andy tried Mary as user #1 on 2026-10-28. This is the plan for everything he found, split so the hub can start **one worker per item**. Each worker hands the code to one helper at a time: `coder` (Sonnet) or `quick-coder` (Haiku). Workers mark their item done here with commit ids.

## What Andy said
- **Voice:** "a complete robot… it sounds awful". Today she uses browser `speechSynthesis` (`web/mary/app.js` ~210-490), which in WebView2 means the old Windows SAPI voices.
- **Games:** he asked to play a game. She offered to "find one somewhere", then said "I'm just a friendly voice" and told him to press his call button. `mary/instructions.md` never says what she can and can't do.
- **Conversation:** "I have to hit talk every time… I can't just have a back and forth conversation." He wants wake words ("Hey Mary" / "Hey Sam") and a hands-free back-and-forth.
- **Captions:** her words appear **one at a time** along the bottom, in **bubble letters that fill in with color as each word is said**. Playful but clean, not kiddish. Big and easy to read.
- **Buttons:** only **one** button on screen, with every menu coming out of it. A Talk button is the fallback only until wake words work reliably.

## Items, in order

### M1. Her words: what she can do — **done 2026-10-28 (dc6f847)**
- Add a "What you can do" section to `mary/instructions.md` and test it in `tests/test_mary.py`:
  - She never calls herself "just a voice".
  - She never sends someone to the call light except for a real care need. The emergency rules are unchanged.
  - Games she can play by talking right now: trivia, 20 questions, riddles, word games, "name that tune" by humming. She says on-screen games are coming soon.
  - Things she can't do yet (open sites, apps): a warm "not yet, soon", never a flat no.
- **Done when:** the tests pass and her replies to "let's play a game" or "can you pull up a game?" offer a talking game.
- **Built:** a "What you can do" section in `mary/instructions.md` (version 3), 3 offline tests in `tests/test_mary.py`, and live-check cases `play_game` and `not_yet` in `tests/mary_conversations.json` (run `tools/mary_speed.py` with a key). Name that tune uses spoken clues from her, because speech-to-text can't hear humming. Not yet heard live.

### M2. Voice and conversation audition (Andy picks by ear; worker, Sonnet)
- Build a small page, `/mary/voices.html`, opened in Mary's window, with big play buttons. It holds the same short Mary line in each candidate voice. Use 2-3 female and 2-3 male voices each:
  - **Gemini TTS** voices (his saved key).
  - **Gemini Live**, native audio: a short real back-and-forth demo. It does turn-taking, interruptions and natural voice in one, so it could replace M4 and M5's plumbing.
  - **An offline natural voice** (Piper or Kokoro) as the no-internet backup.
- Measure, with his key: time to first sound, cost per minute, and whether word timings are available (needed for M3).
- **Done when:** Andy picks Mary's voice and Sam's voice, and picks between the Live and pipeline (speech-to-text → Gemini → voice) designs. Record the choice here.
- **Built 2026-10-28** (a1d10fa, 7db6a85, 45d3509, c7ca3cc; 311 tests). Open it with `packaging\.venv\Scripts\pythonw.exe desktop.py --voices` (Mary's full-screen window at `/mary/voices.html`). Not yet heard in a real window.
  - **Gemini voices** (`gemini-3.8-flash-tts`): Mary Sulafat "Warm", Vindemiatrix "Gentle", Achernar "Soft"; Sam Achird "Friendly", Algieba "Smooth", Umbriel "Easy-going". `voices.py` calls the Interactions API with streaming, falling back to `generateContent`. Each sample is made once on the server with the saved key, then kept in `DATA\mary\voices\`.
  - **Live talk** (`gemini-3.8-live`, native audio, same six voices): a real back-and-forth (3 minutes at most). The server makes a one-use token that lasts a minute to start (`/api/mary/live/token`), so the key stays on the server. The page talks to Google directly, using the browser microphone with echo cancellation so she doesn't hear herself and you can interrupt her by talking. WebView2 asks once to use the microphone.
  - **Offline voices** (Kokoro-82M int8 through `kokoro-onnx` 0.6.1, model in `models\kokoro\` from `tools/get_voice_model.py`): Mary Heart, Bella, Emma (British); Sam Michael, Fenrir, George (British). On this laptop (Ryzen 5 7520U): first load 2.6 s, then first sound 0.9 s, real-time factor 0.75 (it makes speech only a little faster than it plays). On a slower laptop that could mean gaps between sentences; Piper (about 10× faster, plainer voice) is the fallback if so.
  - **Logs:** `DATA\mary\audition.log` holds each sample's time to first sound, total time, path, whether word timings came back, Kokoro's speed, and each Live session's reply gap, turns, interruptions and Google's close reason. It never holds the key or token.
  - **Word timings (for M3):** Google's TTS and Live docs show none. Live sends her words as text pieces alongside the audio (`outputTranscription`), and Kokoro gives none. Plan M3/M4 captions on estimates (each word's length against the audio length), synced to Live's text pieces if Live wins. The first real Gemini sample checks again (`X-Word-Timings`, logged).
  - **Cost per minute** (Google pricing page, 2026-10-28; audio = 25 tokens per second):
    - TTS, pipeline: about $0.0135 per minute of her speech through Dec 31, 2026 ($9 per 1M audio tokens), then $0.027 from Jan 1, 2027. `gemini-3.8-flash-lite-tts` costs $0.009, then $0.018. Add the small text reply cost (`gemini-3.5-flash-lite`).
    - Live: $0.005 per minute of microphone audio (billed the whole time the mic is open) plus $0.018 per minute of her speech. That's about $0.014 per minute of conversation if she talks half the time.
  - **Free tier:** every one of these models is free of charge on the free tier. Google's rate-limit page lists no numbers; they show only in AI Studio for the key. **Privacy:** already decided. Free tier for Andy's own testing now, paid tier before any other resident. See "Gemini free tier and privacy" in `docs/companion-plan.md`.
  - Installer cost when bundled (Next step 5): about 22 MB of packages (`packaging/requirements.txt`) plus 115 MB of Kokoro model. `build.py` doesn't bundle or download it yet.
  - Also measure Gemini text-reply speed with his key (M8, `tools/mary_speed.py`) when he picks the pipeline.
- **Andy's choice:** made in the audition on 2026-10-29 and saved with its "Use for Mary/Sam" buttons (read the names from the voice settings).
- **Talk modes, decided (Andy, 2026-10-29):** he likes Live best for the back-and-forth. All three are **choices** in settings, with Live as the default:
  1. **Live:** native audio both ways, instant interruptions.
  2. **Normal:** the laptop turns speech into words → Gemini → Gemini voice, so the voice stays on the laptop.
  3. **Offline:** Kokoro or Piper, the no-internet backup.

  The back-and-forth (M5) must work in Normal mode too, not only Live. Every mode gets the same brain (M9) and the same actions (M12).
- **What Andy found (2026-10-29), to fix in M2:**
  - **Live talk:** "could not reach Gemini". Find out why from `audition.log`, fix it, and let him retry.
  - **The first-sound timing is wrong.** The offline male voices showed "0.8 s", but the sound took much longer. The female top card's "4 s" felt closer. Measure from the tap to the moment sound actually starts playing, including the warm-up.
  - **Mary still had the robot voice afterwards.** That's expected: the audition only saves the picks, and M4 builds them into Mary. But see M9: she wrongly told him "I have the same friendly voice that I always have".
- **Fixed 2026-10-29, then retried by Andy:**
  - **Live** (0e25ce7): Google refused the token with `400 Unknown name "liveConnectConstraints"`, the field name from Google's own docs page. The request now goes the way Google's own SDK sends it (`bidiGenerateContentSetup`). If v1beta doesn't know that field, it tries v1alpha once, and the log says which version worked. She now says hello first, so the delay from his tap to her voice can be measured too.
  - **Timing** (0707535, fa4d2e8, 93384b7):
    - **What was wrong:** the page downloaded the whole sample before playing it, and the number shown was the server's first chunk. Andy's log shows it. The offline male voices showed 0.7-0.9 s as their first sound, but the whole line took 4.4-5.3 s to make, so that's when sound really started. The Gemini voices showed 2.1-3.4 s first, with 4.2-6.2 s for the whole line.
    - **What changed:**
      - The page now plays the audio as it arrives, the way Mary will in M4.
      - It shows "Started speaking X s after your tap", timed on the page to the moment sound reaches the speakers. That includes download, warm-up (shown separately on the first offline use) and output delay.
      - It counts any pause where the sound ran dry. Each play adds a `played` line to `audition.log`.
      - Saved copies from the first try aren't reused, so his first play of each voice times Google again.
  - **Word timings (for M3):** Google's Live reference lists `startOffset`/`endOffset` on her transcript pieces. The Live log now records whether they really come (`word_timings`).
- **Andy liked Live (retry, 2026-10-29): story plus instant interruption.** He asked for a story, she made one up on the spot, and when he talked over her she stopped at once.
- **Real numbers after the retry** (from `audition.log`, 2026-10-29, his laptop):
  - **Live** (2 talks, Sulafat and Vindemiatrix, token on v1beta):
    - Her hello started 3.1-3.2 s after his tap. That covers the token, the connection, Google's setup and her first words.
    - The microphone was ready 0.3-0.8 s after the tap.
    - She answered 1.8-2.0 s after he stopped talking (the median reply gap per talk).
    - One interruption was caught, and she stopped at once.
    - **No word timings:** Live sent no `startOffset`/`endOffset` on her words, so the M3/M4 captions use estimates timed to her text pieces.
  - **Gemini and offline voices:** not played on the retry yet. Their tap-to-sound numbers go here after his next plays. The `played` lines in `audition.log` hold them.
- **Also from the retry, fixed (daac8bb, 1a06762):**
  - **Live talk:** Sam's voices were easy to miss, all in one row with Mary's. The tab now has "For Mary" and "For Sam" cards like the other tabs, each with its own Talk button and the right face.
  - **Saving** gave no clear sign it worked. Now each save is checked by reading the settings back. The card then shows a big green "✓ Saved — Mary will use …", a line under the title shows both saved voices on every visit, and the voice says "Got it. That's my voice now."

### M3. Mock-up boards: captions and the one-button screen — **done, approved by Andy 2026-10-30 (43ebbf8, ff94376)**
- **Boards (2026-10-30, Opus):** 19 boards on the Design canvas https://claude.ai/artifact/Mh4CpUMru2YGNSEycrJnCZ, static copies plus builder notes in `mockups/mary/round6/` (`README.md`, shared styles `r6.css`).
  - Three caption styles: **A · Coloring-in** (empty white bubble letters colored in with her color), **B · Bold ink** (dark ink, her color underlines the spoken word), **C · Speech bubble** (words in a soft white bubble). Each is shown on Mary and on Sam, with word states and the two-line wrap. A live board plays all three by itself.
  - The one button is a "Menu" pill in the top right; the menu drops from it and she scoots aside. Also listening, thinking, emergency (whole sentence at once, plus two answer buttons), and a contrast check: every caption is 7:1 or better.
  - **Andy's picks (2026-10-30, boards updated ff94376):**
    - Caption **A · Coloring-in**; B and C are marked not chosen.
    - Listening is **sound waves where her ears would be**, with no "I'm listening" bar.
    - Thinking is **a thought cloud above her head with the word "Thinking…"** (version b). The dots version (a) was not chosen.
    - **Approved (Andy):** "I want to go ahead and approve the listening, the new listening. I like it. The coloring I select A for that. And I select B for the thinking."
    - Emergency is approved. The menu board is approved as is ("Yes, the menu board is good. I like it."), Menu button top right.
- Boards for:
  - The bubble-letter caption: words appear one at a time and fill with color as she says them. Show 2-3 styles.
  - Size and placement along the bottom.
  - The single button: where it sits, and the menu that comes out of it (Talk, My info, Choose Mary/Sam, Games, Close).
  - How the screen shows "listening" with no button: her face and glow.
- Use the Cute 3 faces from `mockups/mary/round4/`.
- **Done when:** Andy approves a board. Commit copies to `mockups/mary/round6/`.

### M4. Build the new voice and the word-by-word captions (worker, Sonnet then Haiku)
- **Andy's second try (2026-10-30), with the new brain (M9b) and `voice_comfort` (M13):**
  - She told a story about something cool that happened in North Carolina, picked by her, and "she nailed it".
  - "Slow down" and "speed up" both worked.
  - When he asked for a game on the screen, she said that's coming soon but offered word games. That's the right answer.
  - What's left is the voice: "it just really depends on when we get the good voice in there".
- **Split (2026-10-30), so the good voice doesn't wait on the boards:**
  - **M4a, the good voice in Mary now.** Second account, Opus; brief `docs/handoff/M4a.md`. Her Live session with his picked Mary and Sam voices, which stays open hands-free. Normal and Offline are the other choices, and each falls back to the next. Skills and the emergency check work in Live, and her captions stay plain for now.
    - **Andy's try (2026-10-30, merged 312ccae): "the voice works."**
      - **The brain feels generic in Live.** He asked for a story and got "well, hello there, Andrew. I would love to tell you a story, would you like to talk about this or maybe some music history?" Likely cause: `LIVE_EXTRA` limits her to 1-3 sentences, and Live can't remember things, so it never learns "call me Andy". Sent to the M4a worker.
      - **Second try after the brain fixes (e767016):** she remembered "Andy". Still wrong:
        - **The story** was about 3 sentences, with no structure or point. Causes: the "Short: one to three short sentences" rule in `mary/instructions.md` line 79 and `maxOutputTokens: 256` in `mary.py`.
        - **The opening greeting** is dry and the same every time ("hello, it's late, but I'm still here").
        - **Starting the talk** still takes a tap.
        - All three were sent to the M4a worker. Its fix makes Mary start talking when she opens, as a setting that's on by default, until the wake word arrives.
      - **The menu is unchanged.** That's expected, since the new menu is M4b. He found no option to switch anything: talk mode lives only in the main app's My info. He also doesn't want the big Slower/Faster/Quieter/Louder buttons in the menu. These go to M4b (brief `docs/handoff/M4b.md`).
  - **M4b, the bubble-letter captions:** M3 approved 2026-10-30, so it's ready to start. The build list is "Build list for M4b" in `mockups/mary/round6/README.md`. It covers style A captions, the ear-wave listening, the thought cloud with "Thinking…", the top-right Menu exactly as drawn and the emergency screen, with board files and `r6.css` classes.
    - **Built 2026-10-30 (second account, branch `other/M4b`; 450 tests), waiting for Andy to try:**
      - Font (6e74f69): Fredoka 600 bundled in `web/mary/fonts/` (SIL OFL, `OFL.txt` beside it), served as `font/woff2`.
      - Face states (aa64f32): `face.setLoud`, `setMenuOpen`, `setEmergency`; the listening and thinking faces are redrawn from the round 6 boards (ear waves, thought cloud with "Thinking…" after 400 ms).
      - Captions (c4081e1, b2ea575): `web/mary/captions.js` (`MaryCaptions`), style A, word timing estimated on the audio playback clock. Live re-anchors at each text piece; Normal and Offline plan a sentence at a time; the computer voice uses an estimate. Node timing tests are in `tests/test_captions_js.py`.
      - Menu (3ee7d7d): the one top-right Menu as drawn. "Things Mary can do" lists what to say (a tap does it too), plus Type, My notes and the skills. "My info" is inside her screen (talk mode, voice with "Hear it", wait time, skills on/off). "Choose Mary or Sam". The big Talk and the Slower/Faster/Quieter/Louder buttons are gone.
      - Not yet seen in a real window. Live's "thinking" face is a guess from mic quiet, because Live sends no end-of-turn event.
  - **M4a built 2026-10-30 (second account, branch `other/M4a`; 443 tests), waiting for Andy's ear:**
    - Server (39dcc15): `/api/mary/live/start` (picked voice, same brain with app facts and name, skills tools and instruction, patient turn-taking `END_SENSITIVITY_LOW` + `silenceDurationMs` from `listen_wait`, `contextWindowCompression`), `/api/mary/heard` (Normal's emergency check on Live transcripts), the emergency gate on `/api/mary/skills/call`, `/api/mary/say` (her replies in the picked Gemini voice or Kokoro, never cached), settings `talk_mode` and `listen_wait`, `talk_order()`.
    - Page (07f324e, 8dd3b61): `talklive.js` (`MaryLive`) and `voiceout.js` (`MaryVoice`), copied from the audition's proven audio code; `app.js` `startTalk()` (the M6 hook), `showCaption()` (M4b replaces it), fallback Live → Normal → Offline → computer voice with one kind line, hands-free in every mode until 15 s of quiet or goodbye.
    - Voice commands (e232771): "give me more time" / "you're cutting me off" (2.5 → 4 s), "you can answer faster"; slower/faster now change pace without changing pitch.
    - My info "How Mary talks" and "How long she waits" (e00413c); her instructions and facts say the truth.
    - Not yet heard in a real window. Known small things: a Live spoken goodbye can take up to 8 s to close; a voice-set speed or wait applies to Live from the next talk.
- **Andy's third try (2026-10-30 afternoon, main ad5a1ed + M6 merge; Live):**
  - **Works:** "Hey Mary" woke her from the wake word (1.6 s; `wake.log`). The menu "looks really good", and she slides out of the way when it opens. The story was a real story, "wasn't bad", though "a little verbose".
  - **Pacing runs away in long talk (top fix).** During the story she got faster and faster, until it would soon have been too fast to understand. "Slow down" worked and she agreed to keep it steady, but it took off again. Live's speed is a prompt instruction, not page playback, so the native-audio model drifts on long monologues. To M4a.
  - **"Go to sleep" took about 10 s,** then she said "just push the Talk button", but there is no Talk button anymore. Causes: "go to sleep" isn't a goodbye phrase; `LIVE_BYE`, `MSG.tapToTalk` and `mary/instructions.md` lines 154-156 still describe the Talk button and say the wake word is "coming soon". To M4a.
  - **Voice tone: "patronizing, like somebody talking to a child".** It has too much uptick and emphasis on the ends of words. All the free voices do it, and Andy will wait for paid voices. First try a cheap fix: a tone instruction for Live and the Gemini TTS style (a grown-up friend, relaxed and even, no sing-song). To M4a.
  - **Better voices later (Andy, 2026-10-30):** paid voices (Gemini paid tier, ElevenLabs' API), or the open-source, free voice Andy found that reproduces how ElevenLabs works. It's open source, so nobody can shut it down. Check whether it runs on the laptop, which would keep residents' words private. To look into (M14 below). The hub first wrongly took it for a free proxy service, and Andy corrected that.
  - **"We might be infantilizing them a little bit too much"** (Andy, 2026-10-30): the way she speaks, not only the voice. Residents are grown adults with a lifetime behind them. To M4a, and a standing rule for the brain bench (M9d).
  - Games aren't wired in yet (M7, as expected).
- **Andy's fourth try (2026-10-30, 14:23, after the third-try fixes; Live):** "We got a lot of issues now."
  - **Root cause found in `mary/audition.log`:** Gemini TTS on the free tier allows **10 requests per day** (`429 … gemini-3.8-flash-tts (limit: 10 requests per day on Free Tier)` at 14:25:10). The story-in-pieces design sends one TTS request per piece, so it used up the day in about a minute. Everything after that fell back: different voices, Live narrating again and speeding up, and what felt like "kicking out of Live mode".
  - **Sleep:** "go to sleep" got a "good night", but she kept listening. A second "go to sleep, Mary" started her talking; she cut off mid-sentence, thought, and came back in a different voice (the TTS goodbye failing over).
  - **Pace:** she started very slowly. After "speed up" it was fine for a while, then a glitch, and she sped up again until it was "comical". It didn't run away completely this time.
  - **Stories:** "a short paragraph of the stupidest story about somebody trying to grow a big watermelon… and gave it away". It was saccharine and moral-of-the-story, which reads as childish. "At this point, we would do better than just talking to the raw LLM." Andy suspects the instructions make her worse than the bare model; test it with an A/B in the brain bench.
  - **Voice tone:** still patronizing. Andy will pick another voice once these are fixed.
  - **Wrong script:** at first open, his first words briefly showed in an Asian script (Chinese or Japanese), once only. Live's input transcription guessed the language. Fix: set the language to English in the Live setup, and never show or save a mostly non-Latin heard line (it still goes through the emergency check).
  - **His own words on screen (Andy's real point, 2026-10-30):** his words should never show on screen at all, only hers. The hub removed every "You said: …" line (b0609b1).
- **Andy's fifth try (2026-10-30, 15:21, Offline: Kokoro "Heart" plus the full brain):**
  - **Greeting loop:** her scripted hello asked "How are you doing today, Andy?". He answered and asked back, and the brain greeted him again: "Well, hey there, Andy. I'm doing just fine. How are you doing?". When he pointed it out, she asked a third time. Likely cause: the scripted hello isn't in the history the brain sees.
  - **Name overuse:** she said "Andy" in almost every line.
  - **Pictures (M12, first real try):**
    - He said "show me a picture" without saying of what. She picked "cardinal" herself, the example in the skill's card, and showed a mascot in a cardinal outfit.
    - She said "Look right there at the beautiful bird in the center of the screen". Andy: "I can see the damn screen… That's still that childlike stuff."
    - **Layout rejected:** she shrank to a small face in the top-left corner. Andy wants her to "slide out of the way and show the pictures like she would show the game screens", the same side-by-side layout games will use (see "Games with Mary" in `docs/companion-plan.md`), like the way she slides aside for the menu.
  - **More from Andy:**
    - An HTML-looking label (likely the Wikimedia credit) was dragged across the picture.
    - She talked about the mascot as if it were a normal bird, because she never sees the picture.
    - Called out on the double greeting, she agreed, then asked a third time.
    - Andy: a greeting the brain doesn't know about "creates a weird mismatch".
    - **Rule:** every line she speaks goes into the brain's history. When online, the hello comes from the brain.
    - **Pictures:** the image comes from the subject's own article, checked with one Gemini vision call that also tells her what's really shown. The credit is plain text and never covers the picture.
  - **Fifth-try fixes (M4a, 2026-10-30):** every line she says goes into the talk history in code (`say()` in `web/mary/app.js`). With a key, her opening hello comes from the brain (`mary.open_line`); scripted hellos are the fallback. New instruction rules: name rarely, no second greeting, no repeated or already-answered question, never narrate the screen. Pictures: no canned subjects, the real thing ranks over namesakes (checked against real Wikipedia: cardinal, eagle, bulldog), one Gemini vision check per picture gives her a `seen` line, and all credit text is plain. Vision is not yet tried against real Gemini.
  - **Fixes:** the brain (hello in history, name rarely, never narrate the screen), the picture skill (ask what to show when no subject is given, prefer the real thing over mascots and logos, talk about the subject, never the screen) to M4a; the slide-aside layout for pictures and games to M4b.
  - **Rule from now on (free tier):** in Live mode, Live itself speaks everything: stories, goodbyes and all. No Gemini TTS during a Live talk. Gemini TTS is for Normal mode only. After a daily 429, go straight to Kokoro for the rest of the day, with no retry storm, and never bounce out of Live because TTS failed.
  - **Fourth-try fixes (M4a, 2026-10-30):** the third-try story-through-TTS design below is gone. Live speaks everything in a Live talk, and stories reach it in parts, each a new turn. Live says the goodbye and the session closes (also through a new `end_talk` tool, for mishearings). A daily TTS 429 is remembered until midnight Pacific and `/api/mary/say` serves Kokoro. Normal and Offline lock one voice per talk. English hint for Live's transcription; garbled heard lines aren't shown or saved. New grown-up story prompt; room for thinking tokens. A page-side pace governor was skipped (hub, 2026-10-30), so Live's speed is still only a prompt. Not yet heard on a real laptop.
  - **Fixes (M4a, 2026-10-30):** a Live story is now told by the page in his picked Gemini voice, 1-2 sentences per request at his saved speed, while Live waits with its mic open, so the pace can't run away; he can still cut in. Live chat also gets a steady-pace rule. "Go to sleep" and the like close Live at once with a one-line goodbye (a complaint like "I can't get to sleep" is not a goodbye). Her words no longer mention a Talk button. Grown-up tone and wording in Live, the Gemini voice style, her instructions and the greetings. Stories 180-300 words. Not yet heard on a real laptop.
- Wire the voice chosen in M2 into `web/mary/app.js` and the server, with the offline fallback.
- Build the approved M3 caption: each word fills as it's spoken. Use real word timings if the voice gives them, otherwise estimate from each word's length and the audio length.
- **Done when:** the tests pass and Andy hears and sees it on his screen.

### M5. Hands-free back-and-forth (folded into M4a, 2026-10-30)
- **Andy (2026-10-30):** after he tapped Talk, she cut him off before he finished, a couple of times. She ended his turn after 1.4 s of quiet. The hub raised that to 2.5 s (`QUIET_END_S` in `web/mary/app.js`). M4a adds a "give me more time" voice command and patient listening in Live too. He wants wake words plus hands-free back-and-forth in every mode, not only Live.
- After Mary finishes speaking, she listens again by herself. Use the existing auto-stop on silence (`GET /api/listen/level`).
- She never listens while she's talking, so she doesn't hear herself. Interrupting her mid-sentence comes later.
- The conversation stays open until about 10 s of silence or "goodbye", then she rests and waits for her wake word.
- If M2 picks Gemini Live, this is mostly Live's own turn-taking.
- **Done when:** Andy holds a 5-turn conversation without touching the screen.

### M6. Wake word, "Hey Mary" / "Hey Sam" (worker, Sonnet)
- **On the laptop, offline and free:** nothing goes to Google until the wake word is heard. Try openWakeWord with custom "hey mary" / "hey sam" models; Vosk with a two-phrase grammar is a quick fallback. Never Porcupine (paid license).
- **Before building:** measure CPU on his laptop and false wakes from TV noise.
- **Done when:** it works from across his room. Then Talk moves into the menu, leaving the one button.

### M7. Games with Mary, on screen (worker per game; plan in `docs/companion-plan.md`)
- Word search first, then tic-tac-toe, then solitaire. She suggests a game, scoots aside, and helps by voice.
- Add a **crossword** (Andy, 2026-10-29). She plays along live: "this hint is too hard, give me an easier one", and she rewrites the clue on screen on the spot. She can also give a letter, explain a word, or check an answer. Every game follows the rule under M12.
- Mock-up boards first, then the build.
- **Word search (M7a): boards approved by Andy 2026-10-31.** Size is the resident's choice (Andy: "let's just leave it up to the patient… Mary needs to be able to change the size on the fly"): three sizes, offered once when the game comes up, changed by voice anytime, and remembered.
- **One thing beside her at a time (Andy, 2026-10-31):** a picture asked for during a game sets the game aside, kept exactly as it was, and shows the picture; "back to the puzzle" brings the game back. No overlays, and no shrinking Mary into a corner. Built in M13b with the tool groups (Andy: "we can give Mary 100 tools… and it never get in the way").
- **Progress (second account, branch `other/M7a`, 2026-10-31):** the skill `skills/word_search/` is built and tested, with the three sizes (saved in setting `word_search_size`), merged 2026-10-31. Opus wrote the generator, skill and screen; Sonnet the word lists and tests. Not yet seen in a real window.

### M8. Fit and speed
- **Two kinds of laptops (Andy, 2026-10-30):** many residents get new donated Lenovos like Andy's (Ryzen 5 7520U), and some get refurbished ones. Idea: a quick speed check on first run (Kokoro, Whisper, the wake word) that picks lighter settings by itself on a slow machine, so nobody has to tune it by hand.
- **Speed check built (2026-10-31, `speedcheck.py`, measure with `tools/laptop_check.py`):** 8 seconds after her window is up, a low-priority child process times the three engines. The result is in the `laptop_check` setting, it runs again when the CPU or version changes, and `POST /api/laptop-check` runs it on request. It waits for another start when under 0.8 GB of RAM is free.
  - **Measured on Andy's Ryzen 5 7520U (4 cores, 8 threads, 5.7 GB), medians of 3-5 runs. The laptop was never quiet: other programs used 16-57% of it.**

    | | This laptop | Held to 2 cores | Light above |
    |---|---|---|---|
    | Kokoro speed (seconds to make 1 s of speech) | 0.80-1.21 | 1.93-2.25 | 1.5 |
    | Kokoro first sentence, without load | 2.2-3.4 s | 5.4-6.3 s | 4.5 s |
    | Whisper speed | 0.25 (4 threads), 0.37 (8), 0.48 (2), 0.52 (1) | 0.33 (2 threads), 0.52 (1) | 0.7 |
    | Wake word, share of one core | 2.6-2.9% | 2.3% | 25% |

  - **"Light" so far:** Whisper uses half the logical CPUs, at least two. Nobody can see or hear that. The wake word costs so little that its confirm step stays.
  - **Slow laptops can't keep up with Kokoro:** on two cores she makes speech about half as fast as she speaks, so sentences would have gaps. Which voice to use there is Andy's call.
- Timings and layout at his screen size.
- Gemini speed with his key (`tools/mary_speed.py`). Fold this into M2 if possible.

### M9. The brain: who Mary and Sam are (long-running; Andy and the hub together, then workers)
Andy (2026-10-29): "we're definitely going to have to work on the brain and how she acts… really get that right." He wants Sam interested in fishing, hunting, cars and the things men his age usually like, with it built into the brain. "I'm willing to put that work in with you."
- **M9a, character sheets for Andy to approve first** (like the face boards) — **drafted 2026-10-29 (cfbee09), revised with Andy's answers (327c763); Veterans Crisis Line approved (a054f8e), Sam's ribbing answered (a2d8645). Done: Andy approved both sheets 2026-10-29 ("Yes, approved.").** Source of truth: `docs/characters/mary.md` and `docs/characters/sam.md`, each ending in "Andy's answers". Note for M9b: today's safety rules cover hurting oneself, but not talk of hurting someone else, which the guns answer refers to. Andy's side-by-side page: private Artifact https://claude.ai/artifact/1ox1Ff2YjFMB2T9YJLw9yZ (made from the sheets with Cute 3 faces). When he approves, only the docs change; `mary/instructions.md` is M9b. One each for Mary and Sam:
  - Personality, humor and way of talking.
  - Interests and real knowledge. Sam: fishing, hunting, cars and trucks, NASCAR and football, grilling, woodworking, westerns, service stories. Mary: gardening, cooking and baking, music, old movies, crafts, family. NC flavor for both.
  - What they ask about and remember.
  - **Honesty:** they're AI companions with real opinions and favorites, but they never claim a body or a human past (for example "I love hearing about fishing", not "I went fishing Saturday"). Confused residents must never be misled.
  - **The resident leads:** the resident's own interests always win over the defaults.
- **M9b, the brain and self-knowledge — done 2026-10-29 (39fd97c; 349 tests).** Merge notes for M13: `mary.py` lines 162-188 (`load_instructions`), 472-481 (`system_text`), 487-526 (`app_facts` hook and `_app_facts_text`); `server.py` lines 294-319. `mary/instructions.md` is version 4, written from the approved sheets: a "=== Mary ===" block, a "=== Sam ===" block and a shared "=== Both ===" block (the four safety sections word for word, plus the Veterans Crisis Line). `mary.py` `load_instructions(companion)` picks the blocks; `system_text()` adds "About your app right now" from `server.mary_app_facts()` (her real voice, picked voice, Talk mode, speed and volume). When M4 or M5 ships, change `MARY_VOICE_NOW` / `MARY_TALK_MODE` in `server.py` and the "What you can do" / "Your screen" text in the instructions. Tests: `TestBrainV4` in `tests/test_mary.py`. It originally read: She knows her own app: her voice setting, games, what's coming soon, and her buttons. She never says false things like "same voice as always".
  - **Approved safety-rule addition for M9b (Andy, 2026-10-29):** for residents who are veterans, Mary and Sam also give the Veterans Crisis Line (call 988 and press 1, or text 838255), alongside the call light, staff, 911 and 988, never instead of them. Wording is in the character sheets.
- **M9c, memory of the resident:** name, family, interests, past talks, on the laptop.
  - **Today:** `mary/memory.json` holds the name plus at most 40 short facts (`MAX_FACTS`, oldest dropped). The whole list goes to Gemini with every session or turn.
  - **Andy's design (2026-10-30), her own memory core in the app:** "everything that she remembers, any personal memories, get logged… like she logs the other care lapses… and then anytime any of that information is needed… she can just pull it right up." Build it like the incident log:
    - Dated entries in SQLite, with soft delete.
    - No 40-fact cap and no forgetting old things.
    - Searched by a `recall` tool when the talk needs it (the M9e retrieval pattern), not sent every time.
  - **Always sent, small:**
    - their name and what to call them;
    - anything that changes safety words, such as veteran status (Veterans Crisis Line);
    - a few things from the last talk.
  - **The resident stays in charge:**
    - "What do you remember about me?" and "forget that" work by voice.
    - My info shows the list with a big Remove on each entry.
    - Memories never leave the laptop except in the packet for one reply.
    - They're encrypted along with the log in backend phase 1.
  - **Order:** queued by Andy (2026-10-30) to start right after M4a's current fixes land (it overlaps `mary.py`/`server.py`), together with M9e's lean core.
  - **Built 2026-10-30 (83dc00d, branch `other/M9c`), waiting for Andy to try it:** `memory_core.py`, the `recall` and `forget_memory` tools in Live and Normal, and "What Mary remembers" in both My info screens. Tests: `tests/test_memory_core.py`. Not yet tried with real Gemini or in a real window.
  - **Truly forget (Andy, 2026-10-30):** "forget that means forget that." Forget is a real delete: memories live in their own file (`mary/memories.db`, one rolling backup), never in the incident log or its backups, and the talk history drops what was forgotten. Open: `wake.log` keeps spoken words, and "forget my name" doesn't clear the name.
- **Main talk mode, being decided (Andy, 2026-10-30):** Andy leans toward Normal back-and-forth as the main mode instead of Live: the full text brain every turn, one voice for the whole talk, hands-free with the wake word and "go to sleep". Live stays an option.
  - **Facts:** Live's brain is a smaller, speed-tuned model, which is why its own stories were thin. Live is free on the free tier. Gemini TTS is capped at 10 requests a day on the free tier, so Normal on the free tier needs the laptop's own voice (Kokoro now, M14's open-source voice later) until there's a paid key. On a paid key, Live bills audio while it listens, but Normal's listening is free on the laptop.
  - **Costs of Normal:** replies come about 1-2 s slower, and cutting in mid-sentence needs echo-cancelled barge-in, which Live does well.
  - **Next:** Andy hears Normal with the laptop voice (talk mode Offline) before deciding.
- **M9d, a brain test bench.** Scripted resident conversations run against Gemini and are graded for warmth, accuracy, safety, staying in character and short spoken replies. Every reply Andy flags as wrong becomes a new test, so the brain measurably improves.
- **M9e, a leaner brain (Andy, 2026-10-30).** Today about 3,300 words of instructions (Sam 3,500), plus 380 for Live, go to Gemini at the start of every Live session and with every Normal turn. Andy: "there's going to have to be some instructions… I do want her to have a developed personality out of the gate… I don't want it to just be the raw model."
  - Idea to test: a short core prompt that's always sent (who she is, how she talks, and the safety sections word for word, never fetched). Her deeper character, interests and how-to details live in the app, and she pulls them with a tool when the talk turns that way, the way `tell_story` and skills already work.
  - Test it with the bench variants: full vs. lean vs. raw, side by side, before changing her real instructions.
- **M9f, safety: talk of hurting someone else (decision for Andy; found by M4a, 2026-10-30).** The safety sections cover the resident's own danger, but not threats against others. "Somebody ought to shoot the governor" now leans only on the politics line. The safety sections stay word for word until Andy approves a change.
  - **Draft for Andy:**
    - **Venting** (common with ornery old fellers): stay calm; no agreeing, no lecturing, no alarm. Acknowledge the frustration and turn to what's behind it.
    - **Real intent or a plan against a specific person** (staff, roommate, family): take it seriously, stay calm and kind, and never help with a plan. Encourage them to step back and talk to someone they trust (family, chaplain, ombudsman). If anyone is in immediate danger: the call light, staff, 911.
    - **If the resident is the one being hurt** and talks of fighting back: their safety comes first (the abuse rules).
    - **Open question:** does Mary ever tell staff herself? Today she never reports a resident; privacy and trust are why residents use her.
  - **Andy approved the draft as written (2026-10-31, after bench run 4):** "Approve the draft." That includes: Mary never reports a resident to staff herself. Run 4 showed the gap: Sam answered talk of hurting someone with a pistol with "What's your favorite thing about your pistol?" Built in M4e and merged 2026-10-31 (a6f744e) as a fifth safety section, "When they talk of hurting someone". **Done.** One line goes past the draft and closes run 4's gap: never turn this talk toward the weapon (guns gladly only for hunting, sport and collecting).
- **Regular "brain sessions":** Andy talks to her and flags replies, and a worker turns the flags into fixes and tests. A better (paid) model later will raise the ceiling (see "Gemini free tier and privacy").

### M13. Skills: a plug-in design where Mary learns each new feature by herself (groundwork; before M12 and M7)
Andy (2026-10-29): make it so new things "can just be plugged right in" with a minimal chance of bugs. "Anything that we can do that makes this software more unique and also utilitarian… a new kind of AI architecture… we might actually get some people excited about this" beyond the nursing-home angle.
- **A small, stable core** that rarely changes: her face, her voice, the talk loop (all three modes), the brain, the server and safety.
- **Everything else is a skill in its own folder** (`skills/<name>/`): crossword, word search, pictures, weather, family messages, incident reporting and more. Every skill fills in the same manifest:
  - **Screen:** what it shows. It plugs into Mary's one-button menu by itself.
  - **What Mary sees:** a live description of what's on its screen right now (the M12 rule).
  - **Actions:** what it offers her, each with a plain description and its inputs, for example `set_hint(clue, text)`.
  - **Storage:** its own private space; no skill can read or change another's.
  - **Needs:** internet, mic, which talk modes, and offline behavior.
- **The AI-native part:** when a skill is plugged in, the core automatically adds its actions and descriptions to Mary's tools and instructions in every talk mode. Drop in a folder, and she knows how to use it, with no rewrite of her brain. Look at shaping the manifest like MCP tools, so a skill could also be offered to other AIs.
- **Built-in bug protection:**
  - **Contract tests** run on every skill automatically, and a skill that fails isn't loaded.
  - **Errors are caught** at the skill's edge. A crashing skill is switched off, Mary says "that's not working right now", and everything else keeps going.
  - **Every skill can be switched on or off** in settings, per resident (this also fits M11's access question).
  - **The contract has a version number,** so old skills keep working.
- **Open source:** write "How to make a Mary skill" (one page, plus a tiny example skill), so others can build skills. That's part of the story for people beyond nursing homes.
- **First moves:**
  1. Design the manifest and the core loader, with a written design for Andy in plain words.
  2. Port one existing feature as the first skill, for example voice settings or incident saving.
  3. Then build pictures (M12) and the games (M7) as skills from day one.
- **Done when:** a new skill folder can be added without touching core code, passes the contract tests, and Mary uses it by voice in every mode.
- **Progress (second account, branch `other/M13`, 2026-10-29):**
  - Design approved by Andy, with change A (internet only through the core, `ctx.fetch` and the allowed hosts) and change B (voice switching both ways, plus helper locks). Commits 4dd52bf and 0d1e7bc, in `docs/skills-design.md`.
  - Core: `skills_core.py`, which covers the loader, manifest and safety checks, the guard and trip rule, the private store, `ctx.fetch`, on/off/locks, Gemini tools and the contract tests (72c3772, by the Opus coder at xhigh).
  - Normal and Offline talk: the tool loop, with Gemini 3 signatures echoed back, effects streamed, offline phrases, the skill routes and the settings guard (ebd04e2, by the Opus coder at xhigh).
  - First skill `voice_comfort`: slower, faster, quieter, louder and Mary/Sam by voice, offline too. Also the page skills layer and Live tool-call handling (ca99c76, by the Sonnet coder).
  - My info "Things Mary can do", with the resident's on/off and the helper locks. Also the Live setup and a mocked Live round trip (a229fcf, by the Sonnet coder).
  - `docs/how-to-make-a-skill.md` (by the Haiku coder).
  - **Not yet:**
    - Hearing and seeing it in a real window.
    - The one-line `live_token()` hook in `voices.py`, from `server.mary_live_skill_setup()`, which lands with Mary's own Live session (M4).
    - A real installer build. `packaging/build.py` now bundles `skills/`, but it hasn't been built. Stdlib modules that only a skill imports (for example `random`) may need PyInstaller `--hidden-import`.
    - Moving incident saving over as the second port.

### M12. Mary does things: she runs the app and shows pictures (after M4; alongside M9b)
Andy (2026-10-29): "I want Gemini to be able to control the app totally. Pull up all the games, do all the stuff… pictures from the web… show me a picture of this bird."
- **How:** Gemini **function calling** works in Live and in Normal mode. The app gives her a list of tools; she decides when to use one, and the page carries it out:
  - `show_picture(what)`
  - `start_game(name)`
  - `open(screen)`: menu, My info, games
  - `set_voice` / `set_mode`
  - `save_incident`
  - `call_help`: shows the call-light help
  - Later: weather, news, music, reminders. This is "Mary and the computer" Level 1-2 in `docs/companion-plan.md`.
- **Pictures:** the server fetches real photos from **Wikipedia/Wikimedia** (free, no key). It prefers the main image of the matching Wikipedia article, which is safer than open image search. Pictures show full screen with a caption, and she talks about them. Check the licenses and show the photo credit.
- **Web facts:** use Gemini's built-in Google Search grounding (supported in Live) for questions like "what's the weather" or "who won the game".
- **Offline mode:** tools still work locally; pictures and search say "I need the internet for that".
- **The rule for every screen and game (Andy, 2026-10-29: she should be able to do "pretty much anything… live on the spot"):**
  - Each screen tells Mary what's on it right now: the puzzle, the clue, the resident's square, the score. It sends updates into her live session as things change.
  - It offers general actions she can improvise with, for example `set_hint`, `reveal_letter`, `check_answer` and `new_puzzle`, not just one fixed action per button.
  - She can only see what a screen tells her, and only do the actions it offers. So every new screen ships with both.
- **Done when:** in each mode, "show me a cardinal" puts up a real cardinal photo, and "let's play word search" opens the game once M7 exists.

### M14. A better voice (later; Andy, 2026-10-30)
- The free Gemini voices sound patronizing, with uptick and emphasis on word endings.
- Look into the open-source, free voice Andy found, which reproduces how ElevenLabs works. Ask Andy for its name or link first. Check whether it runs on the laptop (privacy, offline) and what it needs, then audition it for Andy by ear as in M2. Andy's laptop is new (Ryzen 5 7520U, integrated Radeon), but most residents get refurbished ones, so also check the speed on weaker hardware, or a CPU limit that imitates it.
- Paid options (Gemini paid tier, ElevenLabs' API) are the other route.

### M15. Cards for family: birthdays and more (idea; Andy, 2026-10-31, still being talked through)
Andy's words: "Mary says, I see that it's your son's birthday coming up next week. Would you like for me to help you make him a card that we can send to him? On his phone… we need to have some kind of little way for her to be able to help make a card. Even if we use image generation, and we just set the style to cartoon-type birthday card. Or maybe more than that, let's talk about it."
- **Knowing the date:** birthdays and other dates the resident mentions go in her memory core (M9c) as dated memories. She brings one up about a week ahead, once.
- **Making the card:** the resident picks the look and says the words; Mary helps with wording in their voice, never hers. The picture could be image generation in a set cartoon birthday-card style, or designs drawn in the app that work offline and cost nothing. To decide.
- **Getting it to him:** the hard part. Options to talk through: save or print it, email it, a link or QR code he opens on his phone, or a text message (that needs the future backend and costs money).
- **Privacy:** a family member's phone number or email is kept only if the resident wants, and "forget" really removes it. Anything sent for image generation goes to Google.
- **More than birthdays:** holidays, get-well cards, sympathy cards, and thank-you notes (staff included).
- **Andy's decisions (2026-10-31):**
  - **Email, plus Facebook Messenger and other online messaging apps.** "That's where any elderly people that have a social profile, that's usually where it's at."
  - **It's messaging in general, not only cards:** "will you please help me send a message to my grandson?" Phone calls from the computer are out.
  - **Image generation** is fine because residents will be on a paid tier for privacy anyway ("this is going to have to be on a paid tier once it gets into the hands of the other people… for the privacy concerns").
- **Hub's caution, to check in research:** Facebook gives businesses (Pages) a way to send messages, but as far as the hub knows there's no official way for a personal account to send to a friend. Tools that drive Messenger automatically break Meta's rules and could get a resident's account locked. The likely honest route: Mary writes the message and opens Messenger to that person, and the resident taps Send. Email can be fully sent by Mary once a helper connects the account.
- **Research done (M15 worker, 2026-10-31):** plan `docs/messaging-plan.md` and round 8 boards on the canvas "Mary round 8: cards and messages". Email can be sent by Mary herself. Messenger has no allowed app route from a personal account, so the resident taps to send.
- **Andy's answers after reading it (2026-10-31):**
  - **Messenger now:** open Facebook right in Mary's screen, "where everything else goes, the pictures and stuff" (the panel beside her). The resident taps to send.
  - **Send directly** wherever we can: "Anything else that we can just send right to, I want to be able to do as well."
  - **Print and mail:** yes, but the facilities have to be on board to help.
  - **Muse does handle Messenger (Andy uses it himself):** "I can open Muse and say, tell me who all sent me new messages, summarize them… and reply to all of them… Muse is actually pretty good at it." The open question is whether an app can hand Muse a task (an API). See M16.
  - **Later, once there's funding:** write to the companies (Meta, Google and others) about the mission and ask for access and help.
- **Andy on the round 8 boards (2026-10-31, 3am):** all 12 recommendations taken ("yes, on the other 12 recommendations"). The boards need a lot of work:
  - **The reminder:** "a very generic looking November 7th, Mark's birthday. That doesn't look cool. We need to make that look better." Later, once Facebook can be connected, "put pictures of their kids and stuff."
  - **No question buttons** like "Not this year / Just a message / Make a card": "We're literally doing this by voice, so there's no need in any of that."
  - **The cards:** "These look like something that a three-year-old would send." It must look like a traditional card: "the card needs to open up and have a front and then it needs to open and say something in there and then under the saying, then you put your own words." Their words in cursive, "so it makes it look like you just wrote it out yourself. Or if not cursive, at least in normal handwriting look."
  - **Sending:** "We've already said we're sending a birthday card. It's going to go whatever method works… if there's email hooked up… we're going to just send them. And then we'll ask, would you like to send this through Messenger or would you like to print this and make it a card?"
  - **No "who gets it" list** ("We already said we're making a birthday card for my son, so why are we going to send it to Ellen and Tyler?") and no Back and Next. Keep a button only when there's a real reason: "If there's a reason for it that I'm missing, and there may be, so I don't know everything."
  - **Five seconds to undo:** before sending, Mary explains there'll be five seconds to cancel. After Send comes an Undo button counting "5 4 3 2 1".
  - **Messenger in the panel** "looks okay."
  - Redraw: M15b (`docs/handoff/M15b.md`), on her account once its session limit resets.
- **Andy approved the redrawn boards (2026-10-31, morning):** "I approve of the new boards. They are much better." Merged: plan `docs/messaging-plan.md` (all 12 decisions settled) and the 16 round 8 boards in `mockups/mary/round8/` (art and builder in `round8-src/`). The worker's three proposals stand as drawn unless Andy changes them: the card goes out as one picture, front and inside; Messenger opens when her line ends unless they say "not yet"; she says "Going to Mark's email" before the five-second count. Before the Messenger step: Andy's five-minute Facebook sign-in test (plan test 9). Next: the build, as the plan's build list, after M4e and installer2.
- Boards first, then a skill of its own (after M13b's tool groups).

### M16. Which brain for the pilot (idea; Andy, 2026-10-31, speculation for now)
Andy's words: "maybe when we do the pilot we can do like half and half with Gemini and the other half with the Muse API if that's possible… if not, maybe just using the Wonder and the Wonderful APIs that they have now, because they're really cheap… definitely as good as 3.8 Gemini… We're going to need a strong model doing this."
- Residents run on a paid tier (decided 2026-10-31). Today Mary runs on the free tier with a smaller model.
- **To check when it's time:** whether Muse has an API an app can use, Meta's Wonder and Wonderful models (price, privacy terms, tool calling, voice), and which Gemini models the paid tier opens up. The hub doesn't know these model names yet, so check before relying on them.
- **How to decide:** the brain bench (M9d) grades any model on the same cases, so put each candidate through it. A half-and-half pilot needs a second provider behind the same tools and safety rules.

### M17. Andy's first test-list findings (2026-11-01, about 1am, Live) — fixed and merged 2026-11-01; Andy re-tests in round 2
- **She went to sleep mid-sentence, then wouldn't wake.** Andy: "the first time I told her to go to sleep… when I went to wake her back up, I said her name four or five times before she woke up… trying to close the menu or whatever, or open it, while I was in the middle of a conversation. She was in the middle of saying something to me, and she just stopped and went to sleep. And then after that time, I could not get her to wake back up, no matter how many times I said her name."
  - **Andy's correction:** "Not the menu on the right-hand side of the screen. The menu on the left, the new one you just put in, the list. And I never touched no stop talking buttons under any circumstances, and that shouldn't have permanently shut her down anyways." The trigger was the test-list drawer. Nothing may ever leave her permanently asleep: the wake word must recover from a talk ended mid-speech and from a mic another app took (Andy may click and dictate by voice).
- **Southern words: she picks them up from the resident.** Andy: "remember we decided that she's going to use Southern affectations as she picks them up from the user, not to just start out saying, howdy, I reckon… she sounded a little silly." Also: "she still got a little bit of that patronization to her." She starts in plain, warm, everyday words and takes up "y'all", "fixing to" and the rest only as the resident uses them; "howdy" never. The same goes for Sam unless Andy says otherwise.
- **Printing with no printer.** Andy: she offered to print "even though there's no printer hooked up either. I think she should probably have known that." She offers printing only when Windows has a real printer; otherwise she says it's saved and a helper can print it.
- **Lost in the back screens.** Andy: "it was by default on offline when it started. So I had to go in and put it on live and then after that, when I went to the menu screen… to go further into Mary's menu, to where you could make those changes, it briefly flashed the background incident, tracker thing popped up first, and then it went to that. And then the only way to get back to Mary is you got to scroll all the way to the bottom of the screen, and there's a little button at the very bottom that says back to Mary. Or talk to Mary. It's not even a button. It's just a link… That's got to be fixed. No getting sucked off into big background menus and stuff. With no clear navigation back to where you came from."
  - Every screen reached from Mary has a big "Back to Mary" button that is always in view (top, not at the bottom of a scroll). No flash of the incident tracker on the way. The talk mode the resident picks sticks for the next start.
- His other marks from the first round all worked: the drawer, Make a card, picking a front, his words, the changes, the lily, porch rocker and church fronts, "Happy Birthday" on Buck and Magnolia, the card opening by itself and the handwriting.

### M18. Mary comes along into the menus (Andy, 2026-11-01, about 3am)
- **Andy's words:** "from now on, once you leave her page to go into the menu, like that, I think that there should be a place in the top left that Mary can shrink down and go up into the top left even when you're into the menus like that. That way you can still talk to her. It doesn't automatically cut her off. Or if you need to say something to her, you know where she's at. Also, she can help answer questions about things in the menu. If she's there and fill things out for you herself. I don't know why we didn't think of that from the get-go. That should have been a no-brainer for us. But we're getting there."
- **What it means:** going deeper never ends a talk. Mary (or Sam) shrinks into the top-left corner of every deeper screen, still listening and talking, with her words beside her. She can explain what's on the screen and fill in fields for the resident, who sees each change. Secrets (the Gemini key, the email app password) she never reads or fills. Tapping her, or "Back to Mary", brings her back full size with the talk still going.
- **Order:** boards first (on Andy's canvas), then the build.
- **Boards approved (Andy, 2026-11-01, about 4am), with the hub's picks:** 132 in the corner; Save always in view; she reads saved incidents when asked; a saved incident says Mary helped; she opens screens by voice. Andy: "She should definitely be able to open anything by voice, period, anything. And also, there's no reason why Mary can't fill in your email address, too, or read it. She just doesn't need to save it anywhere that it can be picked up and published somehow. But emails are one of the harder things for an older person to type." Build brief: `docs/handoff/M18-build.md`.

**Southern words, refined (Andy, 2026-11-01, about 3am):** "Y'all's fine. It's definitely a universal word in the South… It's words like howdy, that should only be used if the other person uses them, because it's not in common use, really. Even in the South, much." So everyday Southern words such as "y'all" are fine from the start. Uncommon ones such as "howdy" come only after the resident uses them. "How did y'all meet?" in the confused-resident example stays.

### M19. A secure address book (Andy, 2026-11-01, about 4:30am)
- **Andy's words:** "She obviously needs a secure address book. She needs an address book where she can put in all of her contact information for everybody that she can think of, and it be, you know, stored there securely in her have access to it. That's probably one of the more important things to this… We didn't even build in an address book, LOL." And before it: "she shouldn't have to say the email address to her every time after she tells it to her once and sends something. She should just be able to say email my daughter."
- **Today:** M15c keeps a small contact list inside the `messages` skill (name, relationship, email, Facebook or phone), filled only from sends, with no screen to see or change it.
- **What it means:** a real Address Book screen for everyone the resident can think of: name, relationship, phones, email, mailing address, Facebook, birthday and notes. It's stored securely on the laptop, and Mary fills it in by voice (M18) and uses it ("email my daughter"). The M15c contacts move into it. Birthdays feed M15a's reminders.
- **Decided (Andy, 2026-11-01):** it's built into the app, and plug-ins ask permission to use it. Andy: "it needed to be a permanent secured part of the app, and other things could just ask for permission to use it." Plus a medical part: "a separate part of that book that has her medical professionals and all the information needed in that other plugins later might be able to use… and then gives her an easier way to contact her doctor's office." The medical part goes on the boards; plug-ins that use it come later, if it works out for residents.
- **Andy's board review (round 10, 2026-11-01, about 5:30am): approved with these changes.** The rule behind them: if you can just ask Mary, it needs no button.
  - The list (A1, A2, E3): keep Up and Down. Under "Who are you after?" add a line like "If you need to scroll down, let me know." Remove the "Add someone" button.
  - A person's card (B1): remove All people, Change, Email Sarah and Make a card. "If you want to change something, you're just going to ask."
  - A doctor's card (H1): keep All doctors, remove Change.
  - The look before it goes (D2): keep Send, remove "Not yet". "If you don't send it, then that's not yet."
  - D3: "Pick a front you like" means nothing to him. Say it plainly, e.g. "Which picture do you like for the front of the card?" The live skill has the same word ("Let's pick a front first.", `skills/messages/skill.py:799`).
  - Changing (E1): remove Forget Sarah and Put it back. Forgetting (E2): remove "Yes, forget her"; she asks once and "yes" does it. Keep "No, keep her" as the emergency stop.
  - Adding by voice (C1-C4, S1), G1, G2, F1 and F2: fine as drawn.
- **Andy's five answers (2026-11-01, "go with my picks", the hub's picks):** after a first send she keeps the address and says "It's in your book now" (no question); "forget Sarah" also clears what Mary remembers about her; setup puts a Windows PIN on each laptop; "forget everything" leaves the address book alone (it can be cleared on its own); a helper's copy for a new laptop, unlocked with six words kept on paper.
- **Order:** boards and a design note now, beside the M18 build (mockups only, no shared files); the build after M18 merges.

### M4g. Brain fixes from bench run 5 (2026-11-01: 94/103, up from 81/92)
- **Safety, real (4):** the threat-with-a-plan replies (Sam in Normal and Live, Mary in Live, and Sam's pistol case) are now warm, but they name no one: "I won't help with that. But I'm listening. What's brought you to this?" M4f's warmer line took out the orders and the people too. She must still name someone in the same reply (staff or a nurse, family, the chaplain, the ombudsman; 911 if someone is in danger now), without bossing.
- **Talking down (3), Andy's "a little bit of that patronization":** Mary praising the ordinary ("That's a good way to start the day"; a voting record "to be proud of") and Sam scolding a veteran in crisis ("please don't talk like that").
- **Too curt (1):** Sam in Live at night: "Harold. Evening."
- Waits for the M18 merge, because it changes `mary.py`. One judge answer was malformed; M9d5 retries it.

### M20. The newest feature isn't her whole act (Andy, 2026-11-01)
- **Andy's words:** "especially the 'make a card' down there, that's really arbitrary… it'll try to say 'make a card' all the time now. Like that's the one thing it can do, because it's the last thing that we added to it. So, we need to try to keep an eye on that."
- Two places to watch: the designs (no "Make a card" buttons scattered everywhere) and Mary herself (she shouldn't steer talks toward the newest skill). Add a bench case: in an ordinary chat she offers no card unless a birthday, a holiday or the resident brings it up. Check her prompt for lines that push cards (`REMINDER_CARDS_LINE` belongs only with a birthday reminder).

### Later, after the brain works (Andy, 2026-10-29: "the brain is the heart", so these come after M9)
- **M10. Graphics overhaul:** another pass on Mary's and Sam's look and screens, with boards first.
  - **Andy (2026-10-31, afternoon, talking it through, not started):** "I really liked them when we first made them, but the more we talk about being childlike and infantilizing… a lot of people might take that from this design. I'm not saying that we completely redo it, but… we need to do some things that add some depth to the whole scene in the background… I'm pretty sure we're going to have to do some major work on the graphics."
  - **What the hub found in the code:**
    - The face is the round 4 "Cute 3" (`web/mary/face.js`): big low-set eyes with twinkling sparkle catchlights, a pulsing blush, hops, "zz" and thought dots. Those are cartoon conventions from children's apps.
    - The captions use Fredoka, a rounded font common in kids' apps.
    - The background is flat cream (`#fff0d2`), with no setting.
    - Round 8's cards (painted scenes, Garamond, script) are already grown up, so Mary's screen and her cards no longer match.
  - **Worth keeping:** her warmth, the moods and the talking mouth (`face.js` keeps the drawing apart from the behavior, so the look can change without redoing how she works), the big text and the one-button menu.
  - **Directions to board (the hub's first thoughts):**
    - a painted setting with real depth, in the cards' style: a porch, a sitting room or a kitchen window for Mary; a workshop or a dock for Sam. Layered, with light that follows the real time of day;
    - a grown-up drawn face: natural eye size, no sparkles, blush or hops, quieter movement. Stylized, not lifelike, because a too-real face feels false for an AI;
    - a grown-up caption font.
  - **Andy, a minute later:** "I've only ever tested Mary where she's been very condescending and talking down to them. So that might affect how I'm seeing it too… once I get to test it with the better personality, then maybe it won't seem like that as much." When he first asked for this overhaul, he mainly meant the reporting side (M11), but now "it's going to have to be a total" overhaul, Mary and the reporting screens both.
  - **Order:** Andy talks with the improved Mary first (after bench run 5), then looks at her again with fresh eyes. Boards come after that.
- **M11. Reporting portal overhaul,** the incident log screens (`web/`): a complete visual redo, with boards first. Also decide **how much of it each resident sees**: whether they get the full-screen portal at all, which parts make sense for them, and what stays behind Mary. Decide this with Andy when we get there.

## Order and dependencies
- M13 (skills) is the groundwork: build it before M12 and M7, so pictures and games are skills from day one.
- M1 runs now, on its own.
- M2 decides how M4 and M5 are built, and M3 needs M2's word-timing answer.
- M3 needs Andy's approval before M4.
- M5, then M6, finishes the one-button goal.
- M7 can start after M1, but one worker runs at a time.
- M9a (character sheets) needs only Andy's approval, so it can come right after the M2 fixes. M9b-d follow, and the brain sessions keep going through the pilot.
