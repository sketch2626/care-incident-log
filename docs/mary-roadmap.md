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
  - **Free tier:** every one of these models is free of charge on the free tier. Google's rate-limit page lists no numbers; they show only in AI Studio for the key. **Privacy:** on the free tier, content "Used to improve our products" is Yes (No on paid). That matters for residents' talks and has to go into the backend and consent plans before a pilot.
  - Installer cost when bundled (Next step 5): about 22 MB of packages (`packaging/requirements.txt`) plus 115 MB of Kokoro model. `build.py` doesn't bundle or download it yet.
  - Also measure Gemini text-reply speed with his key (M8, `tools/mary_speed.py`) when he picks the pipeline.
- **Andy's choice:** 

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

## Order and dependencies
- M1 runs now, on its own.
- M2 decides how M4 and M5 are built, and M3 needs M2's word-timing answer.
- M3 needs Andy's approval before M4.
- M5, then M6, finishes the one-button goal.
- M7 can start after M1, but one worker runs at a time.
