/* Mary's face, built from the approved boards:
     base      mockups/mary/round4/R4Cute3.dc.html  (geometry, catchlights, blush, sway, hop, blink, glance)
     expressions  mockups/mary/round2/R2*.dc.html   (eye shapes, brows, extras and motion of each mood)
     flow      mockups/mary/round2/R2MoodFlow.dc.html (crossfading faces and glows)

   Plain script, no libraries. It adds one global, MaryFace:

     const face = MaryFace.create(containerEl, {companion: 'mary'});
     face.setMood(m)       one of MaryFace.MOODS (unknown -> 'talking')
     face.setActivity(a)   'resting' | 'listening' | 'thinking' | 'talking'
     face.setCompanion(c)  'mary' | 'him' (a clean cut: new face, new background, new glow)
     face.setLoud(on)      while listening: the resident is talking (bright, fast ear waves and glow)
     face.setMenuOpen(on)  the menu is open: she moves left (translate -105 -30), looks at it, closed smile
     face.setAside(on)     side by side with a skill: she slides into the left 40% of the window and turns toward
                           the right 60%, still big and alive, and glances between it and the person (face.css)
     face.setSmall(on)     M18: she is small in the band; #face moves to the corner by transform and the circle crops her head
     face.setEmergency(on) emergency: the calm concerned face, a little higher (translate 0 -50),
                           a steady rose glow (never flashing). It wins over every mood and activity.
     face.bounce()         one happy hop
     face.destroy()
     face.getState()       { companion, mood, activity, shown, listening, loud, thinking, cloud, menuOpen, aside, small, emergency }
   Options: { companion, cloudDelay }  cloudDelay = ms in thinking before the thought cloud shows (400).

   Which face shows: emergency first, then activity 'listening' or 'thinking', otherwise the mood's face.
   Activity 'talking' (or the mood 'talking') swaps the resting mouth for an open, moving mouth.
   Round 6 boards (mockups/mary/round6/, Listen-*, Think-*-Word, Menu-*, SOS-*):
     listening  ear waves on both sides, sky-blue glow, slight lean (setLoud brightens and speeds them)
     thinking   the face eases 60 px lower (of 800), eyes drift up-left, lavender glow, then after
                cloudDelay a thought cloud up-left with "Thinking…" coloring in, over and over
   The states are classes on the root (face.el) for the page to read:
     mf-listen, mf-loud, mf-think, mf-cloud, mf-menu, mf-aside, mf-sos

   COMPANIONS: each entry has the same shape (COMPANIONS.him is the second example, drawn from
   mockups/mary/round4/R4His*.dc.html; Andy named him Sam):

     COMPANIONS.x = { name, look: {...}, moods: { resting: {...}, ...all 11 MOODS } };

   look     bg, dusk    CSS backgrounds (left out = Mary's warm cream and dusk)
            glowStyle   'round' (Mary: a radial glow) | 'square' (him: an inset box-shadow glow, sized in % of the screen)
            alpha       strength of the square glow (.85)
            cheekY, cheekRy   where the blush sits (Mary 234/15, him 236/14)
   Each mood is a plain object (see M() for the defaults):
     label    spoken in the aria-label ("Mary, happy")
     glow     [r, g, b] of the edge glow         pulse  'edge' 6s | 'fast' 3s | 'slow' 8s | 'steady'
     motion   'float' | 'lean' | 'tilt' | 'bounce' | 'slow'   (whole-face movement, on an HTML wrapper)
     dusk     true = dusky background (sleepy)
     blush    0..1 opacity of the cheeks, or 'pulse' (breathing blush)
     brows, eyes, mouth, talk, extras, behind   SVG markup in the 640x400 drawing (already inside translate(0 -30))
     eyes     two <g class="mf-eye"> groups (use eyePair); blink:true lets them blink; look:'peek' = glances
              at you now and then, 'think' = looks up and to the side all the time; pop:true = pulsing size
     mouth    the resting mouth, talk = the open mouth (it is squashed up and down while she talks)
   Everything is drawn in the same space, so a new companion only needs new shapes. The G.* mappers below
   turn board coordinates into this space; a new face can use them or write final coordinates directly. */
(function (global) {
  'use strict';

  const MOODS = ['resting', 'listening', 'thinking', 'talking', 'happy', 'laughing',
    'concerned', 'sorry', 'surprised', 'sleepy', 'alert'];
  const ACTIVITIES = ['resting', 'listening', 'thinking', 'talking'];

  const INK = '#3a2b22', BROW = '#6b4a32', MOUTH = '#8a3b2e', TONGUE = '#e8897a';
  let uid = 0;

  const r = v => Math.round(v * 100) / 100;

  /* ---------- Mary's geometry: board coordinates (R2) -> Cute 3 ---------- */
  // Rewrites every "x y" pair in a path string with fn(x, y). Only absolute M L Q C Z paths go through here.
  function mapper(fn) {
    return d => d.replace(/(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)/g, (_, x, y) => {
      const p = fn(+x, +y);
      return r(p[0]) + ' ' + r(p[1]);
    });
  }
  const G = {
    // eyes: bigger (x1.19), lower and closer together: R2 centres 248,165 / 392,165 -> 256,182 / 384,182
    eyeL: mapper((x, y) => [256 + 1.19 * (x - 248), 182 + 1.19 * (y - 165)]),
    eyeR: mapper((x, y) => [384 + 1.19 * (x - 392), 182 + 1.19 * (y - 165)]),
    // brows: dropped 18 and pulled in so the talking brows land exactly on Cute 3's
    browL: mapper((x, y) => [228 + 0.9655 * (x - 218), y + 18]),
    browR: mapper((x, y) => [412 - 0.9655 * (422 - x), y + 18]),
    // mouths: centred on x=320, 0.8x smaller, top edge at Cute 3's mouth height
    mouth: mapper((x, y) => [320 + 0.8 * (x - 320), 260 + 0.8 * (y - 244)]),
    // things that ride on the face (twinkles, thought dots, zz) keep their place relative to the eyes
    rise: mapper((x, y) => [x, y + 17])
  };

  /* ---------- small SVG builders ---------- */
  const line = (d, w) => `<path d="${G.mouth(d)}" fill="none" stroke="${INK}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
  const arc = (d, w) => `<path d="${d}" fill="none" stroke="${INK}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;

  function brows(l, rt, lift) {
    const a = `<path d="${G.browL(l)}"/>`, b = `<path d="${G.browR(rt)}"/>`;
    const open = `<g fill="none" stroke="${BROW}" stroke-width="5" stroke-linecap="round">`;
    if (lift === 'both') return `<g class="mf-lift">${open}${a}${b}</g></g>`;
    if (lift === 'right') return `${open}${a}<g class="mf-lift">${b}</g></g>`;
    return `${open}${a}${b}</g>`;
  }

  // Cute 3's four-point sparkle, centred on x,y (k = size)
  function spark(x, y, k) {
    const a = 6 * k, b = k;
    return `M${r(x)} ${r(y - a)} Q${r(x + b)} ${r(y - b)} ${r(x + a)} ${r(y)} Q${r(x + b)} ${r(y + b)} ${r(x)} ${r(y + a)} ` +
      `Q${r(x - b)} ${r(y + b)} ${r(x - a)} ${r(y)} Q${r(x - b)} ${r(y - b)} ${r(x)} ${r(y - a)} Z`;
  }
  // catchlight circle plus twinkling sparkle
  function shine(hx, hy, hr, sx, sy, k) {
    return `<circle cx="${r(hx)}" cy="${r(hy)}" r="${r(hr)}" fill="#fff"/><path class="mf-spark" d="${spark(sx, sy, k)}" fill="#fff"/>`;
  }
  // open round eye; rx2/ry2 are the board's radii (they are scaled x1.19 to Cute 3 size)
  function openEye(cx, rx2, ry2) {
    const rx = Math.round(rx2 * 1.19), ry = Math.round(ry2 * 1.19), k = Math.min(rx / 25, 1.1);
    return `<ellipse cx="${cx}" cy="182" rx="${rx}" ry="${ry}" fill="${INK}"/>` +
      shine(cx + 8 * k, 182 - 12 * k, 8 * k, cx - 8 * k, 182 + 11 * k, k);
  }
  const eyePair = (a, b) => `<g class="mf-eye">${a}</g><g class="mf-eye">${b}</g>`;
  const opens = (rx2, ry2) => eyePair(openEye(256, rx2, ry2), openEye(384, rx2, ry2));
  const arcs = (l, rt, w) => eyePair(arc(G.eyeL(l), w), arc(G.eyeR(rt), w));

  // Sorry's slanted eyes, with the two sharp corners rounded off (Andy's round 3 note: rounder corners)
  const SORRY_L = 'M231.85 158.67 L264.15 151.33 Q270 150 270.33 156 Q272 186 248 188 Q224 186 225.54 166 Q225.8 160 231.85 158.67 Z';
  const SORRY_R = 'M408.15 158.67 L375.85 151.33 Q370 150 369.67 156 Q368 186 392 188 Q416 186 414.46 166 Q414.2 160 408.15 158.67 Z';
  const sorryEyes = () => eyePair(
    `<path d="${G.eyeL(SORRY_L)}" fill="${INK}"/>` + shine(263.14, 183.19, 8, 247.67, 192.71, 1),
    `<path d="${G.eyeR(SORRY_R)}" fill="${INK}"/>` + shine(391.14, 183.19, 8, 375.67, 192.71, 1));

  // open talking mouths, already in final coordinates (tongue = ellipse ex,ey,erx,ery)
  const say = (d, ex, ey, erx, ery) =>
    `<path d="${d}" fill="${MOUTH}"/><ellipse cx="${ex}" cy="${ey}" rx="${erx}" ry="${ery}" fill="${TONGUE}"/>`;
  const dimple = (d) => `<path d="${d}" fill="none" stroke="${INK}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>`;
  // Cute 3's mouth, exactly
  const NEUTRAL = say('M298 262 Q320 268 342 262 Q339 290 320 290 Q301 290 298 262 Z', 320, 284, 12, 5);
  const LAUGH = `<path d="${G.mouth('M274 236 L366 236 Q362 298 320 298 Q278 298 274 236 Z')}" fill="${MOUTH}"/>` +
    `<path d="${G.mouth('M298 286 Q320 270 342 286 Q332 297 320 297 Q308 297 298 286 Z')}" fill="${TONGUE}"/>`;

  const TWINKLE_D = [
    'M196 118 Q198 126 206 128 Q198 130 196 138 Q194 130 186 128 Q194 126 196 118 Z',
    'M444 118 Q446 126 454 128 Q446 130 444 138 Q442 130 434 128 Q442 126 444 118 Z',
    'M470 96 Q471 101 476 102 Q471 103 470 108 Q469 103 464 102 Q469 101 470 96 Z'];
  const TWINKLES = '<g fill="#f0b429">' + TWINKLE_D.map(d => `<path class="mf-twinkle" d="${G.rise(d)}"/>`).join('') + '</g>';
  const LAUGH_LINES = `<g fill="none" stroke="${INK}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="0.6">` +
    `<path d="${G.eyeL('M210 150 L198 142')}"/><path d="${G.eyeL('M208 166 L194 166')}"/>` +
    `<path d="${G.eyeR('M430 150 L442 142')}"/><path d="${G.eyeR('M432 166 L446 166')}"/></g>`;
  const SKY = '<path d="M118 62 A34 34 0 1 0 156 116 A27 27 0 1 1 118 62 Z" fill="#8e8fc7" opacity="0.75"/>' +
    '<g fill="#8e8fc7"><circle class="mf-twinkle" cx="190" cy="60" r="4"/><circle class="mf-twinkle" cx="84" cy="128" r="3"/><circle class="mf-twinkle" cx="214" cy="104" r="3"/></g>';
  const ZZ = '<g fill="#5d5f9e" font-family="Segoe UI, sans-serif" font-weight="700">' +
    '<text class="mf-zz" x="452" y="135" font-size="30">z</text><text class="mf-zz" x="478" y="109" font-size="36">z</text><text class="mf-zz" x="508" y="81" font-size="42">z</text></g>';

  /* ---------- round 6 pieces (mockups/mary/round6/*.dc.html): final coordinates, copied from the boards ---------- */
  // a closed line mouth in the boards' mouth colour, 7 wide
  const mLine = d => `<path d="${d}" fill="none" stroke="${MOUTH}" stroke-width="7" stroke-linecap="round"/>`;
  // two brows in final coordinates; lift = the gentle lift of both (listening)
  const bPair = (l, rt, col, w, lift) => {
    const g = `<g fill="none" stroke="${col}" stroke-width="${w}" stroke-linecap="round"><path d="${l}"/><path d="${rt}"/></g>`;
    return lift ? `<g class="mf-lift">${g}</g>` : g;
  };
  // an eye: its shape plus white catchlights [cx, cy, r, opacity?] (no sparkle)
  const lights = a => a.map(c => `<circle cx="${c[0]}" cy="${c[1]}" r="${c[2]}" fill="#fff"${c[3] ? ` opacity="${c[3]}"` : ''}/>`).join('');
  const oval = (cx, cy, rx, ry, l) => `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="${INK}"/>` + lights(l);
  const box = (x, y, w, h, rx, l) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${INK}"/>` + lights(l);
  // listening: sound waves where the ears would be, three arcs each side, small to large (Listen-Mary / Listen-Sam)
  const EARS = '<g class="mf-ears" aria-hidden="true">' + [
    ['mf-l mf-w1', 'M188.7 183.1 A20 20 0 0 0 188.7 208.9', 4.5], ['mf-l mf-w2', 'M176.4 172.9 A36 36 0 0 0 176.4 219.1', 5.5],
    ['mf-l mf-w3', 'M164.2 162.6 A52 52 0 0 0 164.2 229.4', 6.5], ['mf-r mf-w1', 'M451.3 183.1 A20 20 0 0 1 451.3 208.9', 4.5],
    ['mf-r mf-w2', 'M463.6 172.9 A36 36 0 0 1 463.6 219.1', 5.5], ['mf-r mf-w3', 'M475.8 162.6 A52 52 0 0 1 475.8 229.4', 6.5]
  ].map(w => `<path class="mf-wave ${w[0]}" d="${w[1]}" stroke-width="${w[2]}"/>`).join('') + '</g>';
  // thinking (b): the thought cloud up and to her left, with rising trail bubbles (Think-Mary-Word / Think-Sam-Word).
  // It sits on its own layer in the screen's 640x400 space, so it stays put while her face eases down and leans.
  const PUFFS = '<ellipse cx="172" cy="38" rx="58" ry="21"/><circle cx="124" cy="42" r="16"/><circle cx="142" cy="24" r="18"/>' +
    '<circle cx="172" cy="20" r="18"/><circle cx="202" cy="24" r="18"/><circle cx="222" cy="42" r="16"/>' +
    '<circle cx="198" cy="54" r="12"/><circle cx="170" cy="56" r="12"/><circle cx="144" cy="54" r="12"/>';
  const CLOUD = '<svg class="mf-cloud-svg" viewBox="0 0 640 400" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><g class="mf-puffs">' +
    '<g class="mf-trail"><circle cx="236" cy="103" r="3.5"/><circle cx="226" cy="92" r="5"/><circle cx="214" cy="78" r="7"/></g>' +
    `<g class="mf-ol">${PUFFS}</g><g class="mf-fl">${PUFFS}</g></g></svg>` +
    '<div class="mf-cloudword" aria-hidden="true"><span class="mf-w" data-t="Thinking…">Thinking…</span></div>';

  /* ---------- his pieces (round 4, R4His*.dc.html): already in final coordinates, so no G.* mappers ---------- */
  const H_BROW = '#5a3d28';
  const flip = mapper((x, y) => [640 - x, y]);   // a path on his left side -> the same path on his right side
  const hLine = (d, w) => `<path d="${d}" fill="none" stroke="${MOUTH}" stroke-width="${w || 7}" stroke-linecap="round" stroke-linejoin="round"/>`;
  // straighter brows, 6.5 wide. Give the left brow; the right one is its mirror unless a right one is passed.
  function hBrows(l, lift, rt) {
    const a = `<path d="${l}"/>`, b = `<path d="${rt || flip(l)}"/>`;
    const open = `<g fill="none" stroke="${H_BROW}" stroke-width="6.5" stroke-linecap="round">`;
    if (lift === 'both') return `<g class="mf-lift">${open}${a}${b}</g></g>`;
    if (lift === 'right') return `${open}${a}<g class="mf-lift">${b}</g></g>`;
    return `${open}${a}${b}</g>`;
  }
  // rounded-square eye, w x h, centred on cx,182. hl = how far the catchlight sits above (and the sparkle below) the centre.
  function hEye(cx, w, h, rx, hl, hr) {
    const dx = Math.round(8 + (w - 44) / 8);
    return `<rect x="${r(cx - w / 2)}" y="${r(182 - h / 2)}" width="${w}" height="${h}" rx="${rx}" fill="${INK}"/>` +
      shine(cx + dx, 182 - hl, hr, cx - 8, 182 + hl, 1);
  }
  const hEyes = (w, h, rx, hl, hr) => eyePair(hEye(256, w, h, rx, hl, hr), hEye(384, w, h, rx, hl, hr));
  const hArcs = (l, w) => eyePair(arc(l, w), arc(flip(l), w));

  // sorry's slanted eyes (the board's own paths and catchlights)
  const H_SORRY_L = 'M234 178 C234 170 270 164 278 168 L278 200 C278 206 272 210 256 210 C240 210 234 206 234 200 Z';
  const hSorryEyes = () => eyePair(
    `<path d="${H_SORRY_L}" fill="${INK}"/>` + shine(264, 177, 8, 248, 194, 1),
    `<path d="${flip(H_SORRY_L)}" fill="${INK}"/>` + shine(390, 179, 8, 376, 194, 1));

  // his wide grin (the everyday board's mouth) and the big laugh
  const H_GRIN = say('M280 262 Q320 270 360 262 Q354 288 320 288 Q286 288 280 262 Z', 320, 283, 16, 4.5);
  const H_LAUGH = `<path d="M270 250 L370 250 Q364 300 320 300 Q276 300 270 250 Z" fill="${MOUTH}"/>` +
    `<path d="M298 288 Q320 274 342 288 Q332 298 320 298 Q308 298 298 288 Z" fill="${TONGUE}"/>`;
  // surprised: a soft round-cornered O, like his eyes (it opens a little wider than it rests while he talks)
  const H_O = `<rect x="305" y="262" width="30" height="32" rx="14" fill="${MOUTH}"/>`;

  const H_TWINKLES = '<g fill="#f0b429">' + [
    'M198 128 Q200 138 210 140 Q200 142 198 152 Q196 142 186 140 Q196 138 198 128 Z',
    'M442 128 Q444 138 454 140 Q444 142 442 152 Q440 142 430 140 Q440 138 442 128 Z'
  ].map(d => `<path class="mf-twinkle" d="${d}"/>`).join('') + '</g>';
  const H_LAUGH_LINES = `<g fill="none" stroke="${H_BROW}" stroke-width="4" stroke-linecap="round" opacity="0.6">` +
    '<path d="M222 176 L212 170"/><path d="M220 190 L208 192"/><path d="M418 176 L428 170"/><path d="M420 190 L432 192"/></g>';
  // thought dots, moon and zz: Mary's, in his slightly deeper blues and purples
  const H_SKY = SKY.replace(/#8e8fc7/g, '#7f81bd');
  const H_ZZ = ZZ.replace('#5d5f9e', '#52558f');

  // fills in the defaults for a mood
  const M = o => Object.assign({
    pulse: 'edge', motion: 'float', dusk: false, blush: 0.8,
    blink: false, look: '', pop: false, extras: '', behind: '', dy: -30, cheekY: 0
  }, o);

  /* ---------- companions ---------- */
  const COMPANIONS = {
    mary: {
      name: 'Mary',
      look: { glowStyle: 'round',   // her cream background, dusk, blush, round glow and ink are the CSS defaults
        menuSmile: mLine('M300 260 Q320 280 340 260') },   // Menu-Mary: the closed smile while the menu is open
      moods: {
        resting: M({
          label: 'resting', glow: [242, 183, 102],
          brows: brows('M218 128 C222 106 258 98 276 112', 'M422 128 C418 106 382 98 364 112'),
          eyes: arcs('M226 166 Q248 180 270 166', 'M370 166 Q392 180 414 166', 8),
          mouth: line('M300 252 Q320 266 340 252', 6), talk: NEUTRAL
        }),
        listening: M({   // Listen-Mary (round 6)
          label: 'listening', glow: [110, 185, 220], pulse: 'ear', motion: 'lean', blush: 0.45, blink: true, cheekY: 236,
          brows: bPair('M226 130 C230 106 266 98 284 112', 'M414 130 C410 106 374 98 356 112', BROW, 5, true),
          eyes: eyePair(oval(256, 180, 27, 36, [[265, 166, 9], [247, 193, 4, 0.85]]), oval(384, 180, 27, 36, [[393, 166, 9], [375, 193, 4, 0.85]])),
          mouth: mLine('M304 262 Q320 274 336 262'), talk: NEUTRAL, extras: EARS
        }),
        thinking: M({   // Think-Mary-Word (round 6); the cloud is on its own layer
          label: 'thinking', glow: [176, 156, 222], pulse: 'slow', motion: 'lean', blush: 0.45, blink: true, look: 'ponder',
          brows: bPair('M228 134 C232 110 266 102 284 116', 'M412 142 C406 130 378 126 356 132', BROW, 5),
          eyes: eyePair(oval(256, 182, 25, 33, [[264, 170, 8]]), oval(384, 182, 25, 33, [[392, 170, 8]])),
          mouth: mLine('M306 268 Q322 261 337 270'), talk: NEUTRAL
        }),
        talking: M({
          label: 'talking', glow: [245, 170, 110], blink: true, look: 'peek',
          brows: brows('M218 122 C222 100 258 92 276 106', 'M422 122 C418 100 382 92 364 106'),
          eyes: opens(21, 28),
          mouth: NEUTRAL, talk: NEUTRAL
        }),
        happy: M({
          label: 'happy', glow: [246, 200, 80], blush: 'pulse',
          brows: brows('M218 118 C222 94 258 86 276 102', 'M422 118 C418 94 382 86 364 102'),
          eyes: arcs('M226 172 Q248 148 270 172', 'M370 172 Q392 148 414 172', 9),
          mouth: line('M280 242 Q320 290 360 242', 7) + dimple(G.mouth('M276 236 Q271 243 277 250')) + dimple(G.mouth('M364 236 Q369 243 363 250')),
          talk: say('M290 261 Q320 270 350 261 Q346 294 320 294 Q294 294 290 261 Z', 320, 287, 15, 6) +
            dimple('M285 254 Q280.5 260 286 267') + dimple('M355 254 Q359.5 260 354 267'),
          extras: TWINKLES
        }),
        laughing: M({
          label: 'laughing', glow: [250, 175, 90], motion: 'bounce', blush: 'pulse',
          brows: brows('M216 114 C220 88 258 78 278 96', 'M424 114 C420 88 382 78 362 96'),
          eyes: arcs('M224 170 Q248 140 272 170', 'M368 170 Q392 140 416 170', 10),
          mouth: LAUGH, talk: LAUGH, extras: TWINKLES + LAUGH_LINES
        }),
        concerned: M({
          label: 'concerned', glow: [240, 150, 100], blush: 0.5, blink: true, look: 'peek',
          brows: brows('M220 114 C228 98 260 96 278 112', 'M420 114 C412 98 380 96 362 112'),
          eyes: opens(20, 25),
          mouth: line('M298 260 Q309 254 320 260 Q331 266 342 260', 6),
          talk: say('M302 268 Q320 262 338 268 Q336 288 320 288 Q304 288 302 268 Z', 320, 282, 10, 4)
        }),
        sorry: M({
          label: 'sorry for you', glow: [214, 160, 200], motion: 'tilt', blush: 0.45, blink: true, look: 'peek',
          brows: brows('M218 124 C224 108 256 98 274 96', 'M422 124 C416 108 384 98 366 96'),
          eyes: sorryEyes(),
          mouth: line('M300 264 Q320 252 340 264', 6),
          talk: say('M304 270 Q320 261 336 270 Q334 288 320 288 Q306 288 304 270 Z', 320, 282.5, 9, 3.5)
        }),
        surprised: M({
          label: 'surprised', glow: [130, 205, 185], blush: 0.6, blink: true, look: 'peek', pop: true,
          brows: brows('M216 104 C220 76 260 68 278 86', 'M424 104 C420 76 380 68 362 86', 'both'),
          eyes: opens(25, 33),
          mouth: `<ellipse cx="320" cy="276" rx="12" ry="15.2" fill="${MOUTH}"/>`,
          talk: `<ellipse cx="320" cy="277" rx="12" ry="15" fill="${MOUTH}"/><ellipse cx="320" cy="287" rx="7" ry="4" fill="${TONGUE}"/>`
        }),
        sleepy: M({
          label: 'sleepy', glow: [110, 112, 175], pulse: 'slow', motion: 'slow', dusk: true, blush: 0.6,
          brows: brows('M220 132 C226 116 258 110 274 120', 'M420 132 C414 116 382 110 366 120'),
          eyes: arcs('M230 172 Q248 180 266 172', 'M374 172 Q392 180 410 172', 7),
          mouth: line('M310 258 Q320 263 330 258', 5),
          talk: say('M306 266 Q320 270 334 266 Q332 282 320 282 Q308 282 306 266 Z', 320, 277, 8, 3.5),
          behind: SKY, extras: ZZ
        }),
        alert: M({
          label: 'worried', glow: [232, 110, 120], pulse: 'steady', blush: 0.3, blink: true, look: 'peek',
          brows: brows('M218 120 C224 102 258 94 276 100', 'M422 120 C416 102 382 94 364 100'),
          eyes: opens(21, 28),
          mouth: line('M298 260 Q320 254 342 260', 6),
          talk: say('M303 268 Q320 262 337 268 Q335 289 320 289 Q305 289 303 268 Z', 320, 282.5, 10, 4)
        }),
        // emergency (SOS-Mary, round 6): inner brows raised, no sparkle, face a little higher, steady rose glow
        sos: M({
          label: 'concerned and calm', glow: [232, 110, 120], pulse: 'steady', blush: 0.45, blink: true, dy: -50, smile: false,
          brows: bPair('M230 136 C244 128 266 116 284 110', 'M410 136 C396 128 374 116 356 110', BROW, 5),
          eyes: eyePair(oval(256, 182, 24, 31, [[264, 171, 7]]), oval(384, 182, 24, 31, [[392, 171, 7]])),
          mouth: mLine('M302 270 Q320 262 338 270'),
          talk: say('M302 268 Q320 262 338 268 Q336 288 320 288 Q304 288 302 268 Z', 320, 282, 10, 4)
        })
      }
    },

    /* Him: square glow, straighter brows, rounded-square eyes, wide grin. Same Cute 3 cuteness as Mary.
       Boards: resting, everyday (= talking), happy, laughing, concerned, sorry, alert. Listening, thinking, surprised
       and sleepy have no board of his own; they are Mary's ideas for those moods drawn in his style. */
    him: {
      name: 'Sam',   // Andy named him Sam (2026-10-25). Written here and nowhere else in the face.
      look: {
        glowStyle: 'square', alpha: 0.85,
        bg: 'radial-gradient(ellipse at 50% 42%,#fdf8ee 0%,#f6e8cc 50%,#e9cf9f 100%)',
        dusk: 'radial-gradient(ellipse at 50% 42%,#efe2c8 0%,#d4c3a6 55%,#9b95b9 100%)',
        cheekY: 236, cheekRy: 14,
        ink: '#1b5a8c',   // his "Thinking…" colour (Mary's #9b2c58 is the CSS default)
        menuSmile: mLine('M290 260 Q320 282 350 260')   // Menu-Sam
      },
      moods: {
        resting: M({
          label: 'resting', glow: [214, 140, 50], pulse: 'slow',
          brows: hBrows('M226 144 C238 136 266 134 284 140'),
          eyes: hArcs('M236 186 C242 196 270 196 276 186', 7),
          mouth: hLine('M288 262 Q320 276 352 262'), talk: H_GRIN
        }),
        listening: M({   // Listen-Sam (round 6)
          label: 'listening', glow: [95, 170, 215], pulse: 'ear', motion: 'lean', blush: 0.45, blink: true, cheekY: 238,
          brows: bPair('M226 128 C238 118 266 116 284 122', 'M414 128 C402 118 374 116 356 122', H_BROW, 6.5, true),
          eyes: eyePair(box(232, 151, 48, 58, 19, [[265, 166, 8], [246, 194, 4, 0.85]]), box(360, 151, 48, 58, 19, [[393, 166, 8], [374, 194, 4, 0.85]])),
          mouth: mLine('M296 262 Q320 276 344 262'), talk: H_GRIN, extras: EARS
        }),
        thinking: M({   // Think-Sam-Word (round 6)
          label: 'thinking', glow: [160, 140, 215], pulse: 'slow', motion: 'lean', blush: 0.45, blink: true, look: 'ponder',
          brows: bPair('M226 128 C238 116 266 114 284 120', 'M414 140 C402 134 374 132 356 136', H_BROW, 6.5),
          eyes: eyePair(box(234, 156, 44, 52, 17, [[264, 170, 7]]), box(362, 156, 44, 52, 17, [[392, 170, 7]])),
          mouth: mLine('M302 268 Q322 261 342 270'), talk: H_GRIN
        }),
        talking: M({
          label: 'talking', glow: [214, 140, 50], blink: true, look: 'peek',
          brows: hBrows('M226 138 C238 128 266 126 284 132'),
          eyes: hEyes(44, 52, 17, 12, 7),
          mouth: H_GRIN, talk: H_GRIN
        }),
        happy: M({
          label: 'happy', glow: [226, 170, 40], look: 'peek',
          brows: hBrows('M226 130 C238 120 266 118 284 124'),
          eyes: hArcs('M236 190 C240 170 272 170 276 190', 8),
          mouth: hLine('M274 254 Q320 292 366 254', 8),
          talk: say('M274 256 Q320 266 366 256 Q358 292 320 292 Q282 292 274 256 Z', 320, 287, 18, 5),
          extras: H_TWINKLES
        }),
        laughing: M({
          label: 'laughing', glow: [230, 150, 50], pulse: 'fast', motion: 'bounce', look: 'peek',
          brows: hBrows('M224 124 C236 112 268 110 286 118'),
          eyes: hArcs('M234 188 C238 162 274 162 278 188', 9),
          mouth: H_LAUGH, talk: H_LAUGH, extras: H_LAUGH_LINES
        }),
        concerned: M({
          label: 'concerned', glow: [214, 120, 70], blink: true, look: 'peek',
          brows: hBrows('M226 132 C240 130 266 132 284 140'),
          eyes: hEyes(44, 46, 17, 12, 7),
          mouth: hLine('M296 268 Q308 262 320 268 Q332 274 344 268'),
          talk: say('M296 268 Q308 262 320 268 Q332 274 344 268 Q340 290 320 290 Q300 290 296 268 Z', 320, 284, 10, 3.5)
        }),
        sorry: M({
          label: 'sorry for you', glow: [160, 140, 200], pulse: 'slow', motion: 'tilt', blush: 0.45, blink: true, look: 'peek',
          brows: hBrows('M224 144 C238 138 266 128 284 124'),
          eyes: hSorryEyes(),
          mouth: hLine('M298 272 Q320 260 342 272'),
          talk: say('M298 272 Q320 260 342 272 Q338 292 320 292 Q302 292 298 272 Z', 320, 286, 10, 3.5)
        }),
        surprised: M({
          label: 'surprised', glow: [76, 178, 156], blush: 0.6, blink: true, look: 'peek', pop: true,
          brows: hBrows('M226 116 C238 106 266 102 284 108', 'both'),
          eyes: hEyes(52, 62, 21, 15, 8.5),
          mouth: H_O, talk: H_O + `<ellipse cx="320" cy="287" rx="9" ry="4" fill="${TONGUE}"/>`
        }),
        sleepy: M({
          label: 'sleepy', glow: [88, 92, 160], pulse: 'slow', motion: 'slow', dusk: true, blush: 0.6,
          brows: hBrows('M226 152 C238 142 266 138 284 144'),
          eyes: hArcs('M240 191 C245 198 267 198 272 191', 6),
          mouth: hLine('M304 266 Q320 272 336 266', 6),
          talk: say('M302 268 Q320 274 338 268 Q334 285 320 285 Q306 285 302 268 Z', 320, 280, 8, 3),
          behind: H_SKY, extras: H_ZZ
        }),
        alert: M({
          label: 'worried', glow: [220, 95, 105], pulse: 'steady', blush: 0, blink: true, look: 'peek',
          brows: hBrows('M226 138 C240 128 266 124 284 126'),
          eyes: hEyes(44, 52, 17, 12, 7),
          mouth: hLine('M298 268 Q320 262 342 268'),
          talk: say('M298 268 Q320 262 342 268 Q338 290 320 290 Q302 290 298 268 Z', 320, 284, 10, 3.5)
        }),
        sos: M({   // SOS-Sam (round 6)
          label: 'concerned and calm', glow: [225, 105, 115], pulse: 'steady', blush: 0.45, blink: true, dy: -50, smile: false,
          brows: bPair('M226 136 C240 130 266 120 284 114', 'M414 136 C400 130 374 120 356 114', H_BROW, 6.5),
          eyes: eyePair(box(235, 158, 42, 50, 16, [[264, 171, 6]]), box(363, 158, 42, 50, 16, [[392, 171, 6]])),
          mouth: mLine('M298 270 Q320 262 342 270'),
          talk: say('M296 268 Q308 262 320 268 Q332 274 344 268 Q340 290 320 290 Q300 290 296 268 Z', 320, 284, 10, 3.5)
        })
      }
    }
  };

  /* ---------- one-shot movements (Web Animations, so no class juggling) ---------- */
  const EASE = 'ease-in-out';
  // Cute 3's squash-and-stretch blink
  const BLINK = [
    { transform: 'scale(1,1)', easing: EASE },
    { transform: 'scale(1.14,0.1)', offset: 0.33, easing: EASE },
    { transform: 'scale(0.95,1.07)', offset: 0.67, easing: EASE },
    { transform: 'scale(1.02,0.98)', offset: 0.85, easing: EASE },
    { transform: 'scale(1,1)' }
  ];
  // Cute 3's happy hop. The face wrapper is HTML, so distance is in % of the drawing's height (10 of 400 = 2.5%).
  const HOP = [
    { transform: 'translateY(0%) scale(1,1)', easing: EASE },
    { transform: 'translateY(-2.5%) scale(1,1)', offset: 0.33, easing: EASE },
    { transform: 'translateY(0%) scale(1.02,0.98)', offset: 0.67, easing: EASE },
    { transform: 'translateY(0%) scale(1,1)' }
  ];
  // look aside, then back at you with a tiny pop (Cute 3's peek)
  const glanceFrames = (dx, dy) => [
    { transform: 'translate(0px,0px) scale(1)', easing: EASE },
    { transform: `translate(${dx}px,${r(dy)}px) scale(1)`, offset: 0.16, easing: EASE },
    { transform: `translate(${dx}px,${r(dy)}px) scale(1)`, offset: 0.6, easing: EASE },
    { transform: 'translate(0px,0px) scale(1.03)', offset: 0.82, easing: EASE },
    { transform: 'translate(0px,0px) scale(1)' }
  ];

  /* ---------- markup of one face ---------- */
  function faceHTML(def, id, label, look) {
    look = look || {};
    const cy = def.cheekY || look.cheekY || 234, cry = look.cheekRy || 15;
    let cheeks = '';
    if (def.blush) {
      const pulse = def.blush === 'pulse';
      cheeks = `<g class="mf-cheeks${pulse ? ' mf-blush' : ''}"${pulse ? '' : ` style="opacity:${def.blush}"`}>` +
        `<ellipse cx="246" cy="${cy}" rx="36" ry="${cry}" fill="url(#${id}-bl)"/>` +
        `<ellipse cx="394" cy="${cy}" rx="36" ry="${cry}" fill="url(#${id}-bl)"/></g>`;
    }
    let eyes = def.eyes;
    if (def.pop) eyes = `<g class="mf-pop">${eyes}</g>`;
    if (def.look) eyes = `<g class="${def.look === 'peek' ? 'mf-look' : def.look === 'ponder' ? 'mf-ponder' : 'mf-think'}">${eyes}</g>`;
    eyes = `<g class="mf-eyes">${eyes}</g>`;   // moves toward the menu while it is open
    // the closed smile while the menu is open (not in an emergency)
    const smile = look.menuSmile && def.smile !== false ? `<g class="mf-mouth-menu">${look.menuSmile}</g>` : '';
    return `<div class="mf-motion mf-${def.motion}">` +
      `<svg class="mf-svg" viewBox="0 0 640 400" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${label}">` +
      `<defs><radialGradient id="${id}-bl"><stop offset="0" stop-color="#f48fa6" stop-opacity="0.75"/>` +
      `<stop offset="1" stop-color="#f48fa6" stop-opacity="0"/></radialGradient></defs>` +
      `<g transform="translate(0 ${def.dy})">${def.behind}${def.brows}${cheeks}${eyes}` +
      `<g class="mf-mouth-rest">${def.mouth}</g>${smile}<g class="mf-mouth-say"><g class="mf-mouth-talk">${def.talk}</g></g>` +
      `${def.extras}</g></svg></div>`;
  }

  /* ---------- the face ---------- */
  function create(container, opts) {
    opts = opts || {};
    const id = 'mf' + (++uid);
    const root = document.createElement('div');
    root.className = 'mf-root';
    root.innerHTML = '<div class="mf-bg"></div><div class="mf-bg mf-dusk"></div>' +
      '<div class="mf-glow"><div class="mf-glow-in"></div></div>' +
      '<div class="mf-glow"><div class="mf-glow-in"></div></div>' +
      '<div class="mf-fit"><div class="mf-stage"><div class="mf-sway"><div class="mf-hop"></div></div></div>' +
      '<div class="mf-stage mf-over">' + CLOUD + '</div></div>';
    container.appendChild(root);
    const dusk = root.querySelector('.mf-dusk');
    const glows = root.querySelectorAll('.mf-glow');
    const hop = root.querySelector('.mf-hop');
    const mql = global.matchMedia ? global.matchMedia('(prefers-reduced-motion: reduce)') : null;

    let companion = 'mary', data = COMPANIONS.mary;
    let mood = 'resting', activity = 'resting';
    let loud = false, menuOpen = false, aside = false, small = false, emergency = false, cloud = false, cloudT = 0;
    const cloudDelay = opts.cloudDelay >= 0 ? +opts.cloudDelay : 400;
    let faces = {}, shown = null;
    let glowNow = -1, glowSig = '';
    const glowT = [0, 0];
    let reduced = !!(mql && mql.matches);
    let gone = false;
    let blinkT = 0, glanceT = 0, hopT = 0, snapT = 0;
    const EXTRA = ['sos'];   // faces that are not moods (setEmergency)

    const fadeMs = () => (reduced ? 200 : 780);

    function show(f, instant) {
      clearTimeout(f.hideT);
      f.el.classList.add('mf-show');
      if (!instant) void f.el.offsetWidth;   // let it start from opacity 0
      f.el.classList.add('mf-vis');
    }
    function hide(f) {
      f.el.classList.remove('mf-vis');
      clearTimeout(f.hideT);
      // once faded out, stop drawing it so its animations stop too
      f.hideT = setTimeout(() => f.el.classList.remove('mf-show'), fadeMs());
    }

    function build() {
      Object.keys(faces).forEach(k => clearTimeout(faces[k].hideT));
      hop.innerHTML = '';
      faces = {};
      shown = null;
      MOODS.concat(EXTRA).forEach(key => {
        const def = data.moods[key];
        const el = document.createElement('div');
        el.className = 'mf-mood';
        el.setAttribute('data-mood', key);
        el.innerHTML = faceHTML(def, id + '-' + key, data.name + ', ' + def.label, data.look);
        if (el.querySelector('.mf-mouth-menu')) el.classList.add('mf-has-smile');
        hop.appendChild(el);
        faces[key] = {
          el: el, def: def, hideT: 0,
          svg: el.querySelector('.mf-svg'),
          eyes: def.blink ? Array.prototype.slice.call(el.querySelectorAll('.mf-eye')) : [],
          look: def.look === 'peek' ? el.querySelector('.mf-look') : null
        };
      });
    }

    // the companion's background and glow shape. Mary sets nothing (the CSS defaults are hers), so switching back leaves nothing behind.
    function applyLook() {
      const lk = data.look || {}, st = root.style;
      root.classList.toggle('mf-square', lk.glowStyle === 'square');
      [['--mf-bg', lk.bg], ['--mf-dusk', lk.dusk], ['--mf-ga', lk.alpha], ['--mf-ink', lk.ink]].forEach(p => {
        if (p[1]) st.setProperty(p[0], String(p[1])); else st.removeProperty(p[0]);
      });
    }
    // both glows off, their colours and pulses cleared, so the next setGlow starts fresh
    function resetGlow() {
      for (let i = 0; i < 2; i++) {
        clearTimeout(glowT[i]);
        glowT[i] = 0;
        glows[i].classList.remove('mf-vis');
        glows[i].firstChild.className = 'mf-glow-in';
        glows[i].firstChild.style.removeProperty('--c');
      }
      glowNow = -1;
      glowSig = '';
    }
    // makes a change with no fades (a different companion is a clean cut, not a crossfade between two looks)
    function cut(fn) {
      clearTimeout(snapT);
      root.classList.add('mf-snap');
      fn();
      void root.offsetWidth;
      snapT = setTimeout(() => root.classList.remove('mf-snap'), 80);
    }

    function setGlow(rgb, pulse) {
      const sig = rgb.join(',') + '|' + pulse;
      if (sig === glowSig) return;
      glowSig = sig;
      const old = glowNow;
      glowNow = old < 0 ? 0 : 1 - old;
      const g = glows[glowNow], inner = g.firstChild;
      clearTimeout(glowT[glowNow]);
      // the new colour goes on the hidden glow, then the two swap by crossfading
      inner.style.setProperty('--c', rgb.join(','));
      inner.className = 'mf-glow-in mf-pulse-' + pulse;
      g.classList.add('mf-vis');
      if (old >= 0) {
        glows[old].classList.remove('mf-vis');
        clearTimeout(glowT[old]);
        // after it has faded out, stop its pulse
        glowT[old] = setTimeout(() => { glows[old].firstChild.className = 'mf-glow-in'; }, reduced ? 250 : 1300);
      }
    }

    function render() {
      if (gone) return;
      let key = (activity === 'listening' || activity === 'thinking') ? activity : mood;
      // the neutral talking face only while she speaks; resting's closed eyes never talk
      if (key === 'talking' && activity !== 'talking') key = 'resting';
      if (key === 'resting' && activity === 'talking') key = 'talking';
      // with the menu open she looks at it with open eyes (Menu-Mary / Menu-Sam)
      if (key === 'resting' && menuOpen) key = 'talking';
      if (emergency) key = 'sos';
      const talking = activity === 'talking';
      const f = faces[key];
      if (key !== shown) {
        if (shown) hide(faces[shown]);
        show(f, shown === null);
        shown = key;
      }
      f.el.classList.toggle('mf-talking', talking);
      f.svg.setAttribute('aria-label', data.name + ', ' + f.def.label + (talking && key !== 'talking' ? ', talking' : ''));
      // the alert glow stays on, even while she listens or thinks
      const g = data.moods[mood === 'alert' && !emergency ? 'alert' : key];
      const isLoud = loud && key === 'listening';
      // the resident is talking: a brighter, faster blue (Listen-Mary's .listen.loud)
      if (isLoud && g === data.moods.listening) setGlow(companion === 'him' ? [80, 160, 215] : [90, 175, 220], 'voice');
      else setGlow(g.glow, g.pulse);
      dusk.classList.toggle('mf-vis', !!f.def.dusk);
      root.classList.toggle('mf-listen', key === 'listening');
      root.classList.toggle('mf-loud', isLoud);
      root.classList.toggle('mf-think', key === 'thinking');
      root.classList.toggle('mf-menu', menuOpen);
      root.classList.toggle('mf-aside', aside);
      root.classList.toggle('mf-small', small);
      root.classList.toggle('mf-sos', emergency);
      // the thought cloud comes only after a short wait, so a quick answer never flickers it
      if (key !== 'thinking') {
        clearTimeout(cloudT); cloudT = 0;
        cloud = false;
      } else if (!cloud && !cloudT) {
        cloudT = setTimeout(() => { cloudT = 0; if (!gone && shown === 'thinking') { cloud = true; root.classList.add('mf-cloud'); } }, cloudDelay);
      }
      root.classList.toggle('mf-cloud', cloud);
    }

    /* blinks, glances and the happy hop, on random timers */
    const rand = (a, b) => a + Math.random() * (b - a);

    function blinkNow(ms) {
      const f = faces[shown];
      if (!f) return;
      f.eyes.forEach(el => { if (el.animate) el.animate(BLINK, { duration: ms }); });
    }
    function nextBlink() {
      blinkT = setTimeout(() => {
        blinkNow(480);
        if (Math.random() < 0.25) {   // sometimes a double blink
          blinkT = setTimeout(() => { blinkNow(420); nextBlink(); }, 580);
        } else {
          nextBlink();
        }
      }, rand(2500, 6000));
    }
    function nextGlance() {
      glanceT = setTimeout(() => {
        const f = faces[shown];
        if (f && f.look && f.look.animate) {
          f.look.animate(glanceFrames(Math.random() < 0.5 ? -7 : 7, 2 + Math.random() * 3), { duration: 2600 });
        }
        nextGlance();
      }, rand(7000, 13000));
    }
    function nextHop() {
      hopT = setTimeout(() => { if (shown === 'happy') bounce(); nextHop(); }, rand(7500, 9500));
    }
    function stopSched() {
      clearTimeout(blinkT); clearTimeout(glanceT); clearTimeout(hopT);
    }
    function startSched() {
      stopSched();
      if (gone || reduced || document.hidden) return;
      nextBlink(); nextGlance(); nextHop();
    }

    function bounce() {
      if (gone || reduced || !hop.animate) return;
      hop.animate(HOP, { duration: 720 });
    }

    function setMood(m) {
      if (gone) return;
      mood = MOODS.indexOf(m) >= 0 ? m : 'talking';
      render();
    }
    function setActivity(a) {
      if (gone) return;
      const was = activity;
      activity = ACTIVITIES.indexOf(a) >= 0 ? a : 'resting';
      render();
      if (activity === 'talking' && was !== 'talking') bounce();
    }
    function setLoud(on) {
      if (gone) return;
      loud = !!on;
      render();
    }
    function setMenuOpen(on) {
      if (gone) return;
      menuOpen = !!on;
      render();
    }
    function setAside(on) {
      if (gone) return;
      aside = !!on;
      render();
    }
    // M18: where #face has to go for her head to land on the band's circle, for this window. mary.css does the moving.
    function fitSmall() {
      const box = root.parentNode;
      if (!box || !box.clientWidth || !box.clientHeight) return;
      const b = smallBox(box.clientWidth, box.clientHeight);
      box.style.setProperty('--mf-small-t', 'translate(' + b.x.toFixed(2) + 'px,' + b.y.toFixed(2) + 'px) scale(' + b.scale.toFixed(5) + ')');
      box.style.setProperty('--mf-small-clip', 'circle(' + b.r.toFixed(2) + 'px at ' + b.cx.toFixed(2) + 'px ' + b.cy.toFixed(2) + 'px)');
    }
    function setSmall(on) {
      if (gone) return;
      small = !!on;
      fitSmall();
      render();
    }
    function setEmergency(on) {
      if (gone) return;
      emergency = !!on;
      render();
    }
    function setCompanion(c) {
      if (gone) return;
      companion = c === 'him' && COMPANIONS.him ? 'him' : 'mary';
      root.setAttribute('data-companion', companion);
      const d = COMPANIONS[companion];
      if (d === data) return;
      data = d;
      cut(() => { resetGlow(); applyLook(); build(); render(); });
    }

    function onVisible() {
      if (document.hidden) stopSched(); else startSched();
    }
    function onMotion() {
      reduced = !!mql.matches;
      startSched();
    }
    document.addEventListener('visibilitychange', onVisible);
    if (mql) {
      if (mql.addEventListener) mql.addEventListener('change', onMotion); else mql.addListener(onMotion);
    }

    function destroy() {
      if (gone) return;
      gone = true;
      stopSched();
      clearTimeout(snapT);
      clearTimeout(cloudT);
      Object.keys(faces).forEach(k => clearTimeout(faces[k].hideT));
      glowT.forEach(t => clearTimeout(t));
      document.removeEventListener('visibilitychange', onVisible);
      if (global.removeEventListener) global.removeEventListener('resize', fitSmall);
      if (mql) {
        if (mql.removeEventListener) mql.removeEventListener('change', onMotion); else mql.removeListener(onMotion);
      }
      if (root.parentNode) root.parentNode.removeChild(root);
      faces = {};
    }

    companion = opts.companion === 'him' ? 'him' : 'mary';
    root.setAttribute('data-companion', companion);
    data = COMPANIONS[companion] || COMPANIONS.mary;
    applyLook();
    build();
    render();
    startSched();
    if (global.addEventListener) global.addEventListener('resize', fitSmall);   // M18

    return {
      el: root,
      setMood: setMood,
      setActivity: setActivity,
      setCompanion: setCompanion,
      setLoud: setLoud,
      setMenuOpen: setMenuOpen,
      setAside: setAside,
      setSmall: setSmall,
      setEmergency: setEmergency,
      bounce: bounce,
      destroy: destroy,
      getState: function () {
        return { companion: companion, mood: mood, activity: activity, shown: shown,
          listening: shown === 'listening', loud: loud && shown === 'listening', thinking: shown === 'thinking',
          cloud: cloud, menuOpen: menuOpen, aside: aside, small: small, emergency: emergency };
      }
    };
  }

  // M18: small Mary. Her drawing is 640x400, fitted centered in the window, and the crop is viewBox 180 50 280 280 of it.
  // Returns the scale and move that put that crop on the 132 circle at x 16, y 12, and the same circle in #face's own pixels.
  // At 1280x800: translate(-68.86px,-11.57px) scale(.23571), as board E1 says.
  function smallBox(w, h) {
    const SIZE = 132, X = 16, Y = 12, VX = 180, VY = 50, CROP = 280;
    const sw = Math.min(w, h * 1.6), u = sw / 640, left = (w - sw) / 2, top = (h - sw / 1.6) / 2;
    const scale = SIZE / (CROP * u);
    return { scale: scale, x: X - scale * (left + VX * u), y: Y - scale * (top + VY * u),
      cx: left + (VX + CROP / 2) * u, cy: top + (VY + CROP / 2) * u, r: CROP / 2 * u };
  }

  global.MaryFace = { create: create, smallBox: smallBox, MOODS: MOODS.slice(), ACTIVITIES: ACTIVITIES.slice(), COMPANIONS: COMPANIONS };
})(window);
