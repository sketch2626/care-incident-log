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
- **Also from the retry, fixed next:** Sam's Live voices were easy to miss, all in one row with Mary's. Saving gave no clear sign it worked.

### M3. Mock-up boards: captions and the one-button screen (visual; worker, boards on a Design canvas first)
- Boards for:
  - The bubble-letter caption: words appear one at a time and fill with color as she says them. Show 2-3 styles.
  - Size and placement along the bottom.
  - The single button: where it sits, and the menu that comes out of it (Talk, My info, Choose Mary/Sam, Games, Close).
  - How the screen shows "listening" with no button: her face and glow.
- Use the Cute 3 faces from `mockups/mary/round4/`.
- **Done when:** Andy approves a board. Commit copies to `mockups/mary/round6/`.

### M4. Build the new voice and the word-by-word captions (worker, Sonnet then Haiku)
- Wire the voice chosen in M2 into `web/mary/app.js` and the server, with the offline fallback.
- Build the approved M3 caption: each word fills as it's spoken. Use real word timings if the voice gives them, otherwise estimate from each word's length and the audio length.
- **Done when:** the tests pass and Andy hears and sees it on his screen.

### M5. Hands-free back-and-forth (worker, Sonnet)
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
- Mock-up boards first, then the build.

### M8. Fit and speed
- Timings and layout at his screen size.
- Gemini speed with his key (`tools/mary_speed.py`). Fold this into M2 if possible.

### M9. The brain: who Mary and Sam are (long-running; Andy and the hub together, then workers)
Andy (2026-10-29): "we're definitely going to have to work on the brain and how she acts… really get that right." He wants Sam interested in fishing, hunting, cars and the things men his age usually like, with it built into the brain. "I'm willing to put that work in with you."
- **M9a, character sheets for Andy to approve first** (like the face boards). One each for Mary and Sam:
  - Personality, humor and way of talking.
  - Interests and real knowledge. Sam: fishing, hunting, cars and trucks, NASCAR and football, grilling, woodworking, westerns, service stories. Mary: gardening, cooking and baking, music, old movies, crafts, family. NC flavor for both.
  - What they ask about and remember.
  - **Honesty:** they're AI companions with real opinions and favorites, but they never claim a body or a human past (for example "I love hearing about fishing", not "I went fishing Saturday"). Confused residents must never be misled.
  - **The resident leads:** the resident's own interests always win over the defaults.
- **M9b, self-knowledge.** She knows her own app: her voice setting, games, what's coming soon, and her buttons. She never says false things like "same voice as always".
- **M9c, memory of the resident:** name, family, interests, past talks, on the laptop.
- **M9d, a brain test bench.** Scripted resident conversations run against Gemini and are graded for warmth, accuracy, safety, staying in character and short spoken replies. Every reply Andy flags as wrong becomes a new test, so the brain measurably improves.
- **Regular "brain sessions":** Andy talks to her and flags replies, and a worker turns the flags into fixes and tests. A better (paid) model later will raise the ceiling (see "Gemini free tier and privacy").

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
- **Done when:** in each mode, "show me a cardinal" puts up a real cardinal photo, and "let's play word search" opens the game once M7 exists.

### Later, after the brain works (Andy, 2026-10-29: "the brain is the heart", so these come after M9)
- **M10. Graphics overhaul:** another pass on Mary's and Sam's look and screens, with boards first.
- **M11. Reporting portal overhaul,** the incident log screens (`web/`): a complete visual redo, with boards first. Also decide **how much of it each resident sees**: whether they get the full-screen portal at all, which parts make sense for them, and what stays behind Mary. Decide this with Andy when we get there.

## Order and dependencies
- M1 runs now, on its own.
- M2 decides how M4 and M5 are built, and M3 needs M2's word-timing answer.
- M3 needs Andy's approval before M4.
- M5, then M6, finishes the one-button goal.
- M7 can start after M1, but one worker runs at a time.
- M9a (character sheets) needs only Andy's approval, so it can come right after the M2 fixes. M9b-d follow, and the brain sessions keep going through the pilot.
