/* Mary's face, built from the approved boards:
     base      mockups/mary/round4/R4Cute3.dc.html  (geometry, catchlights, blush, sway, hop, blink, glance)
     expressions  mockups/mary/round2/R2*.dc.html   (eye shapes, brows, extras and motion of each mood)
     flow      mockups/mary/round2/R2MoodFlow.dc.html (crossfading faces and glows)

   Plain script, no libraries. It adds one global, MaryFace:

     const face = MaryFace.create(containerEl, {companion: 'mary'});
     face.setMood(m)       one of MaryFace.MOODS (unknown -> 'talking')
     face.setActivity(a)   'resting' | 'listening' | 'thinking' | 'talking'
     face.setCompanion(c)  'mary' | 'him' (until his data exists, 'him' shows Mary)
     face.bounce()         one happy hop
     face.destroy()

   Which face shows: activity 'listening' or 'thinking' shows that face, otherwise the mood's face.
   Activity 'talking' (or the mood 'talking') swaps the resting mouth for an open, moving mouth.

   ADDING A COMPANION (his face): add an entry to COMPANIONS in the same shape as COMPANIONS.mary:

     COMPANIONS.him = { name: 'Him', moods: { resting: {...}, ...all 11 MOODS } };

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
  const DOTS = '<g fill="#8b76c6"><circle class="mf-dot" cx="468" cy="109" r="8"/><circle class="mf-dot" cx="494" cy="89" r="9"/><circle class="mf-dot" cx="522" cy="71" r="10"/></g>';
  const SKY = '<path d="M118 62 A34 34 0 1 0 156 116 A27 27 0 1 1 118 62 Z" fill="#8e8fc7" opacity="0.75"/>' +
    '<g fill="#8e8fc7"><circle class="mf-twinkle" cx="190" cy="60" r="4"/><circle class="mf-twinkle" cx="84" cy="128" r="3"/><circle class="mf-twinkle" cx="214" cy="104" r="3"/></g>';
  const ZZ = '<g fill="#5d5f9e" font-family="Segoe UI, sans-serif" font-weight="700">' +
    '<text class="mf-zz" x="452" y="135" font-size="30">z</text><text class="mf-zz" x="478" y="109" font-size="36">z</text><text class="mf-zz" x="508" y="81" font-size="42">z</text></g>';

  // fills in the defaults for a mood
  const M = o => Object.assign({
    pulse: 'edge', motion: 'float', dusk: false, blush: 0.8,
    blink: false, look: '', pop: false, extras: '', behind: ''
  }, o);

  /* ---------- companions ---------- */
  const COMPANIONS = {
    mary: {
      name: 'Mary',
      moods: {
        resting: M({
          label: 'resting', glow: [242, 183, 102],
          brows: brows('M218 128 C222 106 258 98 276 112', 'M422 128 C418 106 382 98 364 112'),
          eyes: arcs('M226 166 Q248 180 270 166', 'M370 166 Q392 180 414 166', 8),
          mouth: line('M300 252 Q320 266 340 252', 6), talk: NEUTRAL
        }),
        listening: M({
          label: 'listening', glow: [120, 190, 220], pulse: 'fast', motion: 'lean', blink: true, look: 'peek',
          brows: brows('M218 112 C222 90 258 82 276 96', 'M422 112 C418 90 382 82 364 96', 'both'),
          eyes: opens(22, 30),
          mouth: line('M304 254 Q320 262 336 254', 6), talk: NEUTRAL
        }),
        thinking: M({
          label: 'thinking', glow: [176, 156, 222], blush: 0.6, blink: true, look: 'think',
          brows: brows('M218 122 C222 100 258 92 276 106', 'M422 108 C418 86 382 78 364 92', 'right'),
          eyes: opens(21, 28),
          mouth: line('M302 258 Q318 252 338 260', 6), talk: NEUTRAL, extras: DOTS
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
        })
      }
    }
    // him: { name: '...', moods: { ...the same 11 moods... } }   (a later task)
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
  function faceHTML(def, id, label) {
    let cheeks = '';
    if (def.blush) {
      const pulse = def.blush === 'pulse';
      cheeks = `<g class="mf-cheeks${pulse ? ' mf-blush' : ''}"${pulse ? '' : ` style="opacity:${def.blush}"`}>` +
        `<ellipse cx="246" cy="234" rx="36" ry="15" fill="url(#${id}-bl)"/>` +
        `<ellipse cx="394" cy="234" rx="36" ry="15" fill="url(#${id}-bl)"/></g>`;
    }
    let eyes = def.eyes;
    if (def.pop) eyes = `<g class="mf-pop">${eyes}</g>`;
    if (def.look) eyes = `<g class="${def.look === 'peek' ? 'mf-look' : 'mf-think'}">${eyes}</g>`;
    return `<div class="mf-motion mf-${def.motion}">` +
      `<svg class="mf-svg" viewBox="0 0 640 400" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${label}">` +
      `<defs><radialGradient id="${id}-bl"><stop offset="0" stop-color="#f48fa6" stop-opacity="0.75"/>` +
      `<stop offset="1" stop-color="#f48fa6" stop-opacity="0"/></radialGradient></defs>` +
      `<g transform="translate(0 -30)">${def.behind}${def.brows}${cheeks}${eyes}` +
      `<g class="mf-mouth-rest">${def.mouth}</g><g class="mf-mouth-say"><g class="mf-mouth-talk">${def.talk}</g></g>` +
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
      '<div class="mf-fit"><div class="mf-stage"><div class="mf-sway"><div class="mf-hop"></div></div></div></div>';
    container.appendChild(root);
    const dusk = root.querySelector('.mf-dusk');
    const glows = root.querySelectorAll('.mf-glow');
    const hop = root.querySelector('.mf-hop');
    const mql = global.matchMedia ? global.matchMedia('(prefers-reduced-motion: reduce)') : null;

    let companion = 'mary', data = COMPANIONS.mary;
    let mood = 'resting', activity = 'resting';
    let faces = {}, shown = null;
    let glowNow = -1, glowSig = '';
    const glowT = [0, 0];
    let reduced = !!(mql && mql.matches);
    let gone = false;
    let blinkT = 0, glanceT = 0, hopT = 0;

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
      MOODS.forEach(key => {
        const def = data.moods[key];
        const el = document.createElement('div');
        el.className = 'mf-mood';
        el.setAttribute('data-mood', key);
        el.innerHTML = faceHTML(def, id + '-' + key, data.name + ', ' + def.label);
        hop.appendChild(el);
        faces[key] = {
          el: el, def: def, hideT: 0,
          svg: el.querySelector('.mf-svg'),
          eyes: def.blink ? Array.prototype.slice.call(el.querySelectorAll('.mf-eye')) : [],
          look: def.look === 'peek' ? el.querySelector('.mf-look') : null
        };
      });
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
      const g = data.moods[mood === 'alert' ? 'alert' : key];
      setGlow(g.glow, g.pulse);
      dusk.classList.toggle('mf-vis', !!f.def.dusk);
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
    function setCompanion(c) {
      if (gone) return;
      companion = c === 'him' ? 'him' : 'mary';
      root.setAttribute('data-companion', companion);
      const d = COMPANIONS[companion] || COMPANIONS.mary;   // until his data exists he shows Mary
      if (d === data) return;
      data = d;
      build();
      render();
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
      Object.keys(faces).forEach(k => clearTimeout(faces[k].hideT));
      glowT.forEach(t => clearTimeout(t));
      document.removeEventListener('visibilitychange', onVisible);
      if (mql) {
        if (mql.removeEventListener) mql.removeEventListener('change', onMotion); else mql.removeListener(onMotion);
      }
      if (root.parentNode) root.parentNode.removeChild(root);
      faces = {};
    }

    companion = opts.companion === 'him' ? 'him' : 'mary';
    root.setAttribute('data-companion', companion);
    data = COMPANIONS[companion] || COMPANIONS.mary;
    build();
    render();
    startSched();

    return {
      el: root,
      setMood: setMood,
      setActivity: setActivity,
      setCompanion: setCompanion,
      bounce: bounce,
      destroy: destroy,
      getState: function () { return { companion: companion, mood: mood, activity: activity, shown: shown }; }
    };
  }

  global.MaryFace = { create: create, MOODS: MOODS.slice(), ACTIVITIES: ACTIVITIES.slice(), COMPANIONS: COMPANIONS };
})(window);
