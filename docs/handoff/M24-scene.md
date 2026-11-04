# Handoff: M24 scene, Mary on her porch swing, made beautiful (second account, branch `other/M24-scene`)

Read `docs/handoff/_common.md` first, then:
- `docs/decisions.md` (**D7, D13, D16, D20**);
- the **M24** section of `docs/mary-roadmap.md`;
- `mockups/mary/concepts/README.md`. Look at the pictures it names: **Mary is the first character in `04-lineup-pairs-sam-picked.webp`**, and the radio is the far-right one in `03-lineup-six.webp`.

To learn from round 11, which looked too plain, read its code and commit messages: `git show other/M24-boards:mockups/mary/round11/porch3d.js` and `git log other/M24-boards`. The bar here is far higher.

**Why:** Andy, on round 11: "It is so far away from what I'm imagining. And it's super low poly. Like, it needs to be smooth." This scene is what will show people the project is real, to raise money for it. Andy: "we go full bore on stuff like that."

**Andy's scene, in his words (2026-11-04):** "a robot character sitting on a porch swing the swinging gently, kind of zoomed in on her a little bit, with a little table off to the right and the radio sitting on it, and you might be able to see a little part of the house there on the left, and you see the chains hanging from the porch swing, and the roof over top, and then the yard in the background over to the back and to the right of it, until it smooths off into… and the only motions is her head will tilt some, rock back and forth, move back and forth. Her hands might come up and move a little bit, and her hand will reach over and adjust the radio and then her other arm will point at things on the left side. Vaguely point at them."

**Build one scene, Mary only:** `mockups/mary/round12/mary-porch.html`, plus its script if it's a separate file.
- **The shot:** framed a little close on Mary on the swing. The chains hang down, the porch roof is overhead (with a haint-blue ceiling), and a slice of the house shows on the left. A small table on the right holds the radio, its face softly lit. The yard runs behind her and off to the right, fading softly into hazy distance.
- **The motion,** one loop: idle (the swing's sway, her head tilting and rocking), then talking (her hands come up a little, and her mouth moves), then one hand reaching over to adjust the radio's dial, then the other arm pointing loosely to the left, where screens will appear, then back to idle.
- **Smooth and beautiful, not low poly.** Mary is built from smooth, rounded forms: high segment counts, lathe and tube shapes, and rounded edges. Her materials are physically based: worn robin's-egg-blue enamel with subtle wear, cream accents and brass details. Her crocheted shawl drapes over her shoulders and upper arms; round 11 made it a stiff bib, which is wrong.
- **Lit like a film still:** warm, low afternoon sun, a sky fill, a rim light, soft shadows (shadow maps are fine) and tone mapping. Add gentle bloom or haze if it helps. Residents' laptops will be locked down to Mary, so quality comes first, but it should stay smooth (30 to 60 fps) on an ordinary laptop.
- **Her face:** kind, expressive and clearly a robot's (D20). Eyes with lids that blink, eyebrows, and a soft mouth that moves when she talks. No doll face and no hinged jaw.
- **Grown-up, never childish (D7),** and original art.

**Seeing your work.** Render the page to a picture with Windows' Edge running in the background. It uses its own throwaway profile in a temp folder, never Andy's browser or his screen. The hub tested this, and it renders three.js with full lighting:

```
& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --headless=new --user-data-dir="<temp>\edgeprofile" --use-angle=swiftshader --enable-unsafe-swiftshader --window-size=1280,800 --hide-scrollbars --virtual-time-budget=5000 --screenshot="<temp>\shot.png" "<url of your page>"
```

Then read the PNG.
- Add a query like `?t=12` or `?pose=radio` that freezes one moment, so you can check each part of the loop.
- If you use ES modules, serve the folder with `python -m http.server` and point Edge at `http://127.0.0.1:<port>/`, because module files don't load from `file://`.
- Make, look, fix, and do it many times. Judge each shot the way Andy will: would someone stop scrolling?

**three.js:** use one pinned version. For example `three@0.160.0` with its `examples/jsm` add-ons from `cdn.jsdelivr.net/npm/`, or r128 from cdnjs. The app bundles it offline later.

**Rules:**
- Touch only `mockups/mary/round12/` and `docs/handoff/done/M24-scene.md`.
- No app changes, no Gemini calls.
- If your context passes about 200K, commit `WAITING: context full`, with where things stand.

**Models (Andy, 2026-11-04):** you do all of it yourself, at extra-high effort, with no helpers. The look is the whole job.

**Finish:** commit `DONE: M24 scene`. The message carries:
- three plain lines for Andy;
- what's in the scene;
- which shots you checked;
- what you'd do next.

Then stop.
