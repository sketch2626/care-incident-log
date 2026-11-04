# M24 critique: a hard look at the 3D porch plan (2026-11-04, Opus 5.5, no helpers)

## For Andy, in five lines
1. The idea is right. A real setting and a character with a body is what Mary's look needs. But a clay or vinyl-toy talking animal is the most kid-like choice you could make, the very thing you're trying to leave behind.
2. The biggest risk is the laptop. 3D needs the graphics chip and more memory. Your machine had about 0.4 GB free, and on some old laptops 3D won't start at all. So she needs a 2D twin that looks just as grown-up, and we measure on your laptop before we build.
3. The worker is drawing 3D blind. Primitive shapes drawn blind tend to look crude, and crude won't win helpers. Either let the worker look at its own renders (your new browser rule may already allow it), or pick a style that forgives it (carved-wood folk art).
4. The committed boards brief still says "SVG, a woman 60 to 65 with hands," which contradicts what you asked for. Fix the file now. Also, the "slides left" board clashes with your approved corner Mary (M18).
5. A body changes her brain too. "You have no body" and "a warm Southern woman" have to be reworded for the character you pick. So pick the character before the paid model's bench runs, or you'll bench twice.

---

## The problems, most important first

### 1. "Clay / vinyl-toy" plus a talking animal reads as a children's product (D7, mission "grown adults, always")
- **What breaks:** Andy's own reason for M10 and M24 was that the look "might take" as childlike. Vinyl toys, clay finishes and talking animals on swings are exactly the language of kids' TV and collectible toys. Residents 65 to 95, their families, the facility and a state inspector will judge the product by Mary's look in the first second. A toy-like mascot also undercuts "build everything as if the state will read it": the reporting side shares the app.
- **Why it happens:** "not childish" was layered on after "cartoony" and "character", and the redirect picked the finish that is the easiest to make appealing (round, shiny, cute). Appealing to whom matters: cute appeals to children and to developers browsing GitHub, not to an 80-year-old veteran.
- **Do instead:**
  - Name a grown-up finish in the brief. The one I'd board first is **Southern carved-wood folk art**: whittled, faceted, matte, painted with milk-paint colors. It's native to porches, it's for adults (it's what hangs in the craft barn, not the toy aisle), and flat-shaded low-poly primitives *are* that look. Roughness reads as hand-carved, not broken. It also has an easy 2D twin (problem 2).
  - Two other grown-up finishes worth one board each: matte glazed ceramic, or a soft painted diorama (muted colors, no gloss).
  - Ban for the boards: gloss, big round head-to-body ratios (no "chibi"), huge eyes, sparkle catchlights, blush, bouncing. Proportions closer to adult figures: a head about a quarter to a fifth of the body, not a half.
  - For the animal concept, pick an animal adults respect and joke about, not a cuddly one, and give it adult posture and clothes that suit a porch, not a costume.

### 2. The laptop: memory, the graphics chip, and no fallback
- **What breaks:**
  - **Memory.** The test machine had about 0.4 GB free while running faster-whisper, Kokoro, Vosk and WebView2. WebGL starts a GPU process in WebView2 and adds its buffers. Expect very roughly 80 to 200 MB more, depending on the driver and the window size. On a machine at 0.4 GB free, that tips Windows into paging. Paging slows speech-to-text and the voice, so **she answers slower**, which hurts more than any look helps.
  - **CPU and audio.** On integrated graphics, rendering shares the CPU and memory bandwidth with Kokoro and Whisper. A 60 fps scene can make her voice stutter or her replies lag.
  - **No GPU, or a blocklisted driver.** Older refurbished Lenovos often have drivers that Chromium (WebView2) blocklists. Chromium has been phasing out the automatic software fallback for WebGL, so on those machines `getContext('webgl')` can simply fail. The screen would be empty, with no Mary. Even where software WebGL runs, it eats the CPU.
  - **Context loss.** WebGL contexts get dropped on sleep, driver resets and low memory. Without handling, Mary vanishes mid-talk.
- **Why it matters:** Mary being on screen and listening is the product. "She disappeared" or "she got slow" on a resident's laptop is worse than an old face.
- **Do instead:**
  - **A probe before any build (small, Sonnet `coder`):** one tiny three.js scene inside the real Mary window. Log free memory, the app's memory, CPU and frame time with it on and off, while she talks in Offline (Kokoro) and Live. Run it on Andy's laptop. The hub launches it, so there are no hands steps. Set the budget from that number, for example "no more than 60 MB and 10% CPU while she talks." If it can't meet the budget, the 3D plan stops there.
  - **Render on demand, not 60 fps forever:** cap at 30 fps, drop to about 10 while idle, stop when the window is hidden or minimized, keep the pixel ratio at 1, use no shadows maps or post-processing, and use one light rig.
  - **A real 2D twin, chosen by the code, not the resident:** start WebGL with `failIfMajorPerformanceCaveat: true`. If it fails, the context is lost twice, or the frame time stays bad, fall back to an SVG version of the *same* character. That's why the style matters: folk-art flat shapes translate to SVG, while glossy vinyl doesn't. The fallback must not be today's "Cute 3" face, which is the look Andy wants gone.
  - Keep the 2D twin in the design from round 11 on, as one board, so Andy approves both.

### 3. The committed brief contradicts the redirect, and board 4 contradicts M18
- **What breaks:**
  - `docs/handoff/M24-boards.md` still says "a warm woman who seems 60 to 65, with a whole body, hands", "SVG and CSS, offline… no heavy libraries". The roadmap's "For the build, later" still says "It must run offline as SVG and CSS". The redirect exists only as a chat message. If the boards worker compacts, hits its context limit, or a new worker picks it up, it follows the file and draws the woman Andy rejected. The same goes for any future build worker reading the roadmap.
  - **Board 4, "the scene moves left when a screen opens",** collides with the approved M18 design. Every deeper screen shows Mary small in the **top-left corner** (`face.setSmall`), and `setAside` (the left 40%) is for skills shown side by side. A porch taking the left 40% of the address book squeezes a 20px-text form into 60% of an old laptop's screen, and the 3D scene keeps rendering behind a form the resident is trying to fill.
- **Do instead:**
  - Rewrite the brief file and the roadmap's build lines to match the redirect before the worker goes further. Commit both on `main`.
  - Draw board 4 as three cases using today's names: **menu open** (`setMenuOpen`, a small move left), **side by side with a skill** (`setAside`, the porch on the left 40%), and **a deeper screen** (`setSmall`, her head in the corner circle with the porch gone and the 3D paused or down to a few fps). Ask Andy if he meant the porch-left to replace the corner. My read of his words ("same setup… she moves over to the left") is that he meant the main-screen move, not the forms.

### 4. Her brain says she's a Southern woman with no body; the screen will say otherwise (mission "honest", D2, D3, D4, D5, D19)
- **What breaks:**
  - `mary/leaner.md` line 1: "talks like a warm Southern woman… You seem 60 to 65". Line 25: "You have no body". `lean.md` goes further: "You're a warm Southern woman". Put that brain in a wooden heron or a lantern-being and three things go wrong. A resident asks "what are you?" and she gives an answer that doesn't match what they see. A confused resident gets two stories, which is the exact thing the honesty rule guards against. And "no body" is plainly false-looking on screen.
  - Changing those lines is a brain change. That means D3 (remove before you add), D4 (judged on whole talks, Andy's read), and, for leaner's safety-adjacent line, D5 approval. That line was reworded with Andy's yes only two days ago, to stop a made-up human past.
  - **The name.** "Mary" works on a non-human character (people name mules, boats and hound dogs Mary), so the name can stay. But "Mary" plus a woman's voice plus an animal body is three signals. They have to agree, or the character feels like a costume.
  - **The voice picker.** The resident can pick any voice, men's included (`voices.py`). A character drawn as a she, speaking in a picked man's voice, is the "weird mismatch" Andy warned about in "one mind, one voice".
- **Do instead:**
  - Treat the character pick as a brain decision too. When Andy picks, the hub writes the one-line identity change for each brain. For example: "You're Mary, an AI friend; on screen you look like [X] on a porch swing. That's a picture, not a body. You talk like a warm Southern woman from North Carolina." Swap it for the old line at no net growth (D3), and bench it.
  - **Do it before the paid model's bench, not after.** The brain is waiting on the Gemini-or-Claude choice. If the identity line changes after that bench, the bench is wasted (D4).
  - The "honest AI being" concept fits the honesty rule best: no false body, no false species. Board it with real care, and keep it warm and hand-made, never a glowing-eyed machine. In a nursing home, a robot face can read as a camera watching residents, and that's the fastest way to get a facility to object.
  - Decide whether the voice list narrows to voices that fit the character, or the character follows the voice (Mary's voice for Mary, Sam's for Sam). Andy decides.

### 5. Drawing 3D blind will likely look crude, and crude defeats the point (process)
- **What breaks:** Andy's reason for 3D is "visually appealing… otherwise nobody's going to want it". A worker composing a character from spheres and cylinders, with no picture of the result, gets proportions, silhouettes, faces and the camera framing wrong. Faces are the hardest part, and the face is where talking and listening happen. Earlier rounds worked because SVG coordinates can be reasoned about on paper. Lit 3D with a camera can't: an arm in front of the body or a head clipped by the swing is invisible until rendered. Andy then spends rounds and budget on fixes he has to describe by voice.
- **Do instead (pick one, Andy decides):**
  - **(a) Let it look (my pick):** the worker renders its *own* boards to still PNGs and looks at them before Andy sees anything. A few small images cost far less than a wasted round. Andy's newest rule (hub memory, 2026-11-04) says "no browser" means his Chrome and computer use, and the built-in browser pane is fine. So the hub may be able to allow this already. D15's wording ("no browser or screenshots") should be updated to match, so a worker doesn't refuse.
  - **(b) A forgiving style:** faceted carved-wood (problem 1) hides small errors. Glossy vinyl shows every one.
  - **(c) Both.**
  - Without (a), expect two or three rounds before a character is good enough to recruit helpers with.

### 6. WebGL boards on the Design canvas may not show (process)
- **What breaks:** the canvas shows many boards at once (round 10 had more than ten). Each 3D board is its own WebGL context. Browsers cap live WebGL contexts (Chrome about 16) and drop the oldest, so boards go blank as Andy scrolls. Each one also loads three.js from cdnjs inside the canvas's frame, which may be sandboxed. Thumbnails may capture a blank canvas. Andy may open the board and see nothing, and the worker can't tell.
- **Do instead:**
  - **Board zero:** one tiny spinning-cube board, published first. The hub opens it and asks Andy one button: "Do you see a cube?" That costs a few cents and saves the round.
  - Keep round 11 to **four boards or fewer**. Use one renderer per board that draws stills plus one live view. Start the render only when the board is in view, and draw one still frame for thumbnails (`preserveDrawingBuffer` on the first frame).
  - Have the README say what each board should show, in words, so Andy can tell "broken" from "ugly".

### 7. Round 11 asks for too much at once (cost on a tight budget)
- **What breaks:** three characters, a 3D porch, five weathers, four times of day, Sam, a moved-left board and motion, all in hand-written 3D, done blind. That's an M18/M19-sized job (each took 20-25% of a week), on an account that's already tight. The weather and Sam work is wasted on the two concepts Andy doesn't pick.
- **Do instead:** split it.
  - **11a:** board zero, then the three characters on the same swing, one sunny afternoon, idle motion, plus talking and listening on the strongest one. Add the 2D twin of each as a still. That's it.
  - **11b, after Andy picks:** weather and time, Sam, and the three screen states (problem 3).

### 8. Real weather: internet, a town, and an offline, private app (mission "private and local first", D12, D1)
- **What breaks:**
  - The resident's town, sent with their IP to a weather service, tells that service where a resident lives. That's minor, but it's an outside call from an app that promises nothing leaves. It has to be a skill, with `ctx.fetch` and its hosts listed on the card.
  - The town has to come from somewhere. Typing it is a manual step. Saying it means she stores a location.
  - When the sky shows rain and it's sunny outside the window, residents who can see out will say "it's broken".
  - If she *talks* about the weather, the forecast has to be in her context, which grows the prompt (D3). And she must never announce it on her own (D1).
  - "Tell her to change it" makes the scene something on screen she changes (D12). That means a voice path, which is fine, but Live already carries 13 tools, one over Andy's limit of about 12.
- **Do instead:**
  - **Default: the sky follows the laptop's clock and the season, fully offline.** That covers morning, dusk, night, fall leaves and snow in winter. With the swing, it delivers most of the charm.
  - **Real weather later, as an optional skill, off by default,** like the Gemini helper. Only the town goes out. Use the US National Weather Service API (`api.weather.gov`): free, no key, run by the government. Turn the town into coordinates offline, from a small bundled town list, so no geocoding service sees it. Andy decides if it ever ships.
  - "Make it rain" goes through the existing screen-action tool, not a new one.
  - **No lightning flashes, ever** (photosensitivity, and the "calm, never flashing" rule). Show a storm as dark sky and rain only.

### 9. Her states must stay unmistakable in every weather (D18, emergency, captions)
- **What breaks:**
  - **Asleep versus night.** At night with the porch light low, "she's asleep and only hears her wake word" has to look completely different from "she's awake in the dark". D18 depends on residents knowing whether she hears them.
  - **Listening.** Today it's ear waves and a sky-blue glow. A 3D body needs an equally obvious cue, readable on a small screen with weak eyes.
  - **Emergency.** Today: a calm, concerned face, a steady rose glow, and big letters. A thunderstorm porch behind the 911 steps is wrong.
  - **Captions** ("only her words on screen") over rain, night or a busy porch lose contrast.
  - **Live sends no mood tags.** leaner.md leaves the "[mood]" tags out of Live, so in Live (Andy's main mode) the 3D character shows only resting, listening, thinking and talking. Eleven moods of 3D expression would be mostly unseen there.
- **Do instead:**
  - An emergency **freezes the weather to a plain, calm sky**. Asleep gets its own unmistakable look (eyes shut, head down, the porch light dims). Listening uses a cue that doesn't depend on color alone.
  - Captions keep their solid backing, whatever the scene.
  - Put the effort into the four activities first. Moods are a bonus for Normal and Offline.
  - Keep the current reduced-motion handling (`prefers-reduced-motion`): no sway, no rain motion, stills only.

### 10. Fit with the code: keep the MaryFace interface, or this becomes a rewrite (M17, M18, D13, M23)
- **What breaks:** `web/mary/app.js` drives the face through a small interface: `setMood`, `setActivity`, `setLoud`, `setMenuOpen`, `setAside`, `setSmall`, `setEmergency`, `setCompanion`, `bounce`, and `getState` with its `mf-*` classes (13 calls in `app.js`, plus tests). A 3D build that changes this touches the sleep loop, the corner band, "Back to Mary" and the emergency path. Those were each hard-won (M17, M18, M21a).
- **Do instead:**
  - The 3D character is a **drop-in** `MaryFace.create()` with the same methods and the same `mf-*` classes. `face.js` is already split into drawing and behavior, so this is the seam. The 2D twin is a second drop-in behind the same interface. Choosing between them is the code's job (problem 2), never the resident's.
  - "Back to Mary", the captions and the emergency letters stay as HTML over the canvas, never drawn inside the 3D scene (D13, accessibility). The canvas keeps the `aria-label` that `face.js` gives today ("Mary, happy").
  - **M23:** the mouth must follow whatever audio level the page already has, whether that's Live's stream or Kokoro's output. Then a Claude module that speaks through Kokoro drives the same mouth with no change to the graphics. Don't tie the mouth to Gemini Live.
  - `bounce()` (the happy hop) should go or turn into something adult, like a chuckle or a lean back. It's one of the kid conventions M10 listed.

### 11. Small things that are fine but need doing right
- **License:** three.js is MIT, which is compatible with GPL-3.0. Keep its license file next to the bundled copy, and credit it in the notices. Fonts and any textures must be OFL, CC0 or made in code.
- **Installer size:** a pinned, minified three.js is under 1 MB against a 334 MB installer, so size is a non-issue. Bundle it in `web/` at build time. The app must never load it from cdnjs, because it runs offline. Only the boards use the CDN.
- **Sam:** if Mary becomes a carved heron, Sam can't be a realistic man, or the pair looks mismatched. Design them as a pair in 11b. `setCompanion` stays a clean cut.
- **Facilities:** a grown-up, hand-made porch look *helps* acceptance (it looks like a gift, not a surveillance device). A toy look gets dismissed, and a robot look gets feared. Both are arguments for problem 1's direction.

---

## What I'd change in the boards brief right now
1. **Rewrite `docs/handoff/M24-boards.md` to match the redirect.** Three.js, three character concepts, not a woman, and offline bundling later. Remove "SVG and CSS… no heavy libraries" and "a warm woman… 60 to 65… hands". Fix the roadmap's "It must run offline as SVG and CSS" the same way.
2. **Replace "clay or vinyl-toy finish"** with "grown-up, hand-made finishes: carved-wood folk art first, then matte ceramic or a painted diorama; no gloss, adult proportions, no big eyes, no sparkles, blush or hops".
3. **Add board zero** (the cube test, Andy says yes or no) before any real board.
4. **Cut round 11 to 11a:** three characters on the swing, one sunny afternoon, idle, talking and listening on the strongest, and a 2D still twin of each. At most four boards. Move weather, Sam and the screen states to 11b.
5. **Add for each concept:** how it looks asleep, listening and in an emergency (even as a still), and one line on how its identity line in the brain would read.
6. **Ask Andy two things by button:** may the worker look at its own renders (the new browser rule may already cover it; update D15 to match), and did "she moves left" mean the main-screen move only, keeping the corner for forms (M18)?
7. **Add to the design note:** frame-rate and memory budget, the fallback rule, and that it plugs in behind the `MaryFace` interface.

## What's good and should stay
- **A real place.** The porch, with a swing on chains, a haint-blue ceiling, a screen door, ferns and tea, gives Mary a world and fits the app's name. It's the single biggest improvement over a face on cream.
- **Not a human woman.** A non-human character fits the honesty rule better than a drawn woman ever could. A confused resident is less likely to think a real person is there.
- **Light that follows the real clock and season.** It's warm, offline, private and free.
- **"Tell her to change it"** fits D12 exactly.
- **Gentle motion only,** never flashing, plus the swing's slow sway. It's calming and adult.
- **Primitives in code, no downloaded models.** It's small, GPL-clean, offline, and editable by helpers in plain text, which is what an open-source project needs.
- **Keeping "her in the middle, moves to the left".** It keeps the M17/M18 behavior people already learned.
- **Boards first, Andy picks by eye.** It's the method that has worked for ten rounds.

## Order of work I'd recommend
1. Fix the brief and roadmap (the hub, tiny).
2. Board zero, plus the laptop probe (Sonnet `coder`, small). If either fails, rethink before spending more.
3. Round 11a, then Andy picks a character and a finish.
4. The identity line for the picked character goes into the brain *with* the paid-model bench (D4, D19, M23), not after it.
5. Round 11b (weather and time, Sam, the screen states), then the build: behind `MaryFace`, with the 2D twin and the fallback, budgeted from the probe.
6. Real weather as an optional skill, only if Andy wants it.
