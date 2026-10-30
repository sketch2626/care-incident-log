# Mary round 6: captions and the one button (M3)

Boards for `docs/mary-roadmap.md` item M3, made 2026-10-30. Live canvas (private to Andy's first account): https://claude.ai/artifact/Mh4CpUMru2YGNSEycrJnCZ. These files are static copies and the source of truth for a fresh hub or the M4 builder. Faces are Cute 3 from `round4/`.

**Status: awaiting Andy's pick.** Record his choice here and in the roadmap before M4 starts.

## What's here
- `Main.dc.html`: plays by itself, looping all three caption styles on Mary, then on Sam, with the real timing estimate below.
- `WordStates.dc.html`: each word in three steps (not yet said, being said, said), per style.
- `Wrap.dc.html`: long sentences, two lines at most, the top line floats away.
- `A-*`, `B-*`, `C-*`: the three caption styles on Mary and on Sam, full screen.
  - **A · Coloring-in** (Fredoka 600, 66 px): empty white bubble letters with a thin brown edge; her color (Mary berry `#9b2c58`, Sam blue `#1b5a8c`) colors them in; white sticker edge.
  - **B · Bold ink** (Nunito 900, 62 px): dark ink `#2a1d15` with a soft cream halo; her color underlines the word being said.
  - **C · Speech bubble** (Baloo 2 700, 60 px): words in a soft white bubble with a tail up to her mouth.
- `Menu-*`: the one button (top right, "Menu") open: Talk, Things Mary can do, My info, Choose Mary or Sam, Games (coming soon), Close Mary. She scoots aside.
- `Listen-*`, `Think-*`: listening (sky-blue glow that follows your voice, "I'm listening" pill, your words in plain text) and thinking (lavender glow, eyes drift up, three dots color in).
- `SOS-*`: the emergency screen: soft pinkish-red steady glow, the whole sentence already filled, two answer buttons.
- `Contrast.dc.html`: every caption color passes 7:1 (AAA).
- `r6.css`: every class the boards use. Start M4 from it.

## Notes for the builder (M4)
1. **Word timing is estimated.** Gemini TTS, Live and Kokoro give no per-word times (M2, 2026-10-29: Live sent no `startOffset`/`endOffset`).
   - Weight of a word = syllables (vowel groups) + 0.5. Pauses: comma +1.5, end of sentence +3.
   - Start = chunk start + chunk audio length × (weight before it ÷ total weight). It fills over its own share, kept between 180 and 900 ms.
   - Run on the playback clock (AudioContext time of the scheduled audio), not the wall clock.
   - `Main.dc.html`'s script is a working example.
2. **Per talk mode.**
   - Live: her text pieces (`outputTranscription`) arrive next to the audio. Spread each piece's words over the audio that came with it, and re-anchor at every piece. If Live ever sends `startOffset`/`endOffset` (the audition log already records `word_timings`), use those.
   - Normal (Gemini voice) and Offline (Kokoro): make speech a sentence at a time. Plan each sentence's words once its audio length is known; while streaming, start at about 2.6 words a second and correct.
3. **Showing the words.**
   - Lay out the whole two-line chunk first, with later words hidden but holding their place (`.later`), so nothing jumps. Break lines by measured width, never inside a word.
   - The next word shows as an empty outline 150 ms early, then fills left to right (`.on.f1`…`.f9`, then `.done`). The word being said lifts 5 px (A, C) or gets the underline (B).
   - Two lines at most. When a third starts, the top line floats up 40 px and fades over 400 ms while the rest slide up.
   - Fade out 4 s after she stops, or as soon as the resident talks. If she's cut off (Live), stop filling, keep the said words, fade the rest within 300 ms.
4. **Emergency.** Whole sentence at once, already filled; the spoken word still lifts. Steady glow, never flashing. Two answer buttons above the words, the only time more than one button shows.
5. **Sizes and fonts.**
   - Captions 66/62/60 px on a 1280×800 screen; scale with the window, about `clamp(48px, 5.2vw, 88px)`.
   - Menu button 96 px tall, menu rows 88 px, menu text 32 px. Nothing under 64 px to tap or 20 px to read.
   - Fredoka, Nunito and Baloo 2 are SIL Open Font License. The boards load them from Google Fonts; the app must bundle only the chosen one as woff2 in `web/mary/fonts/`, so it works offline.
6. **Listening and thinking.**
   - The blue glow brightens with the mic level (Live: Web Audio analyser on the mic; Normal: `GET /api/listen/level`).
   - "Your words" come from Live's `inputTranscription` or the on-device speech-to-text: plain text, smaller, never bubble letters.
   - Thinking runs from the end of the resident's turn to her first sound; show the dots only after 400 ms.
7. **The one button.**
   - Top right, always there. A tap opens the menu; "Hide menu", a tap on her face, or 20 s idle closes it.
   - Labels follow the companion's name. Talk stays first until wake words (M6) are reliable; Games says "Coming soon" until M7.
8. **Accessibility.**
   - The caption is `aria-hidden` (her voice already speaks); each finished sentence goes to a polite live region once.
   - `prefers-reduced-motion`: no sway, float or lift; words still fill.
   - Color is never the only signal: words lift or underline, and every glow comes with a face change.
