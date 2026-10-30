# Mary round 6: captions and the one button (M3)

Boards for `docs/mary-roadmap.md` item M3, made 2026-10-30. Live canvas (private to Andy's first account): https://claude.ai/artifact/Mh4CpUMru2YGNSEycrJnCZ. These files are static copies and the source of truth for a fresh hub or the M4 builder. Faces are Cute 3 from `round4/`.

**Andy's picks (2026-10-30):**
- Caption style: **A · Coloring-in**. B and C stay on the canvas and here, marked not chosen.
- Listening: **sound waves where her ears would be**, three arcs each side, small to large. No "I'm listening" bar, no words.
- Thinking: **a thought cloud** rising off the top of her head, not dots at the bottom. Still to pick: (a) three dots coloring in, or (b) the word "Thinking…".
- Emergency: approved as is ("that'll work for now"). The Menu button stays top right.

## What's here
- `Main.dc.html`: plays by itself: the resident talks (ear waves), she thinks (cloud, dots then the word), then answers in style A, using the real timing estimate below. Mary twice, then Sam twice. Built as one face with mood classes, the way M4 should do it.
- `WordStates.dc.html`: each word in three steps (not yet said, being said, said), style A, Mary and Sam.
- `Wrap.dc.html`: long sentences, two lines at most, the top line floats away.
- `A-*`: the chosen caption style on Mary and on Sam, full screen. **A · Coloring-in** (Fredoka 600, 66 px): empty white bubble letters with a thin brown edge; her color (Mary berry `#9b2c58`, Sam blue `#1b5a8c`, emergency rose `#8a1f2e`) colors them in; white sticker edge.
- `B-*`, `C-*` (not chosen): B · Bold ink (Nunito 900, dark ink, her color underlines the spoken word); C · Speech bubble (Baloo 2 700, words in a white bubble).
- `Menu-*`: the one button (top right, "Menu") open: Talk, Things Mary can do, My info, Choose Mary or Sam, Games (coming soon), Close Mary. She scoots aside.
- `Listen-*`: listening: sky-blue glow, she leans in, and three sound-wave arcs pulse outward on each side where her ears would be. Mary's board shows the resident talking (bright, fast); Sam's shows waiting (soft, slow).
- `Think-*`: thinking: lavender glow, little bubbles rise off the top of her head into a thought cloud up and to her left, and her eyes look up at it. `Think-Mary`/`Think-Sam` = (a) dots coloring in; `Think-*-Word` = (b) "Thinking…" coloring in.
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
   - The next word shows as an empty outline 150 ms early, then fills left to right (`.on.f1`…`.f9`, then `.done`). The word being said lifts 5 px.
   - Two lines at most. When a third starts, the top line floats up 40 px and fades over 400 ms while the rest slide up.
   - Fade out 4 s after she stops, or as soon as the resident talks. If she's cut off (Live), stop filling, keep the said words, fade the rest within 300 ms.
4. **Emergency.** Whole sentence at once, already filled; the spoken word still lifts. Steady glow, never flashing. Two answer buttons above the words, the only time more than one button shows.
5. **Sizes and fonts.**
   - Captions 66 px on a 1280×800 screen; scale with the window, about `clamp(48px, 5.2vw, 88px)`.
   - Menu button 96 px tall, menu rows 88 px, menu text 32 px. Nothing under 64 px to tap or 20 px to read.
   - Fredoka 600 is SIL Open Font License. The boards load it from Google Fonts; the app must bundle it as woff2 in `web/mary/fonts/`, so it works offline.
6. **Listening and thinking.**
   - Build one face with mood classes on the screen element: `.listen`, `.listen.loud`, `.think.dots` or `.think.word` (see `Main.dc.html` and the "One face" block in `r6.css`).
   - Listening: the ear waves (`.ears`, `.wave`) and the blue glow brighten with the mic level (Live: Web Audio analyser on the mic; Normal: `GET /api/listen/level`). No words on screen.
   - Thinking runs from the end of the resident's turn to her first sound; show it only after 400 ms. The cloud sits up and to her left; her face eases 60 px lower (`.think .facepos`) so it fits, and back up when she talks. Her eyes drift up-left toward it.
7. **The one button.**
   - Top right, always there. A tap opens the menu; "Hide menu", a tap on her face, or 20 s idle closes it.
   - Labels follow the companion's name. Talk stays first until wake words (M6) are reliable; Games says "Coming soon" until M7.
8. **Accessibility.**
   - The caption is `aria-hidden` (her voice already speaks); each finished sentence goes to a polite live region once.
   - `prefers-reduced-motion`: no sway, float or lift; words still fill.
   - Color is never the only signal: words lift or underline, and every glow comes with a face change.
