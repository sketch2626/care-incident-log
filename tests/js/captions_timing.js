// Node checks for web/mary/captions.js (run by tests/test_captions_js.py). Prints "OK <n>" or fails with a message.
'use strict';
const assert = require('assert');
const path = require('path');
const C = require(path.join(__dirname, '..', '..', 'web', 'mary', 'captions.js'));

let count = 0;
function check(name, fn) {
  try { fn(); count++; } catch (e) { console.error('FAIL ' + name + ': ' + (e && e.message)); process.exit(1); }
}
const near = (a, b, eps) => Math.abs(a - b) <= (eps == null ? 1e-9 : eps);
const SENT = "Dinner came late again? I'm sorry, that sounds hard. Want me to write it down?";

// ------------------------------------------------------------------ weights
check('syllables are vowel groups, at least 1', () => {
  assert.strictEqual(C.syllables('Dinner'), 2);
  assert.strictEqual(C.syllables('sunshine!'), 3);
  assert.strictEqual(C.syllables('coffee'), 2);
  assert.strictEqual(C.syllables("I'm"), 1);
  assert.strictEqual(C.syllables('rhythm'), 1);
  assert.strictEqual(C.syllables('911'), 1);
});
check('weight = syllables + 0.5', () => {
  assert.strictEqual(C.weight('Dinner'), 2.5);
  assert.strictEqual(C.weight('go'), 1.5);
});
check('pauses: comma 1.5, end of sentence 3', () => {
  assert.strictEqual(C.pause('sorry,'), 1.5);
  assert.strictEqual(C.pause('again?'), 3);
  assert.strictEqual(C.pause('hard.'), 3);
  assert.strictEqual(C.pause('wow!'), 3);
  assert.strictEqual(C.pause('well."'), 3);
  assert.strictEqual(C.pause('that'), 0);
  assert.ok(C.endsSentence('down?') && !C.endsSentence('sorry,'));
});

// ------------------------------------------------------------------ plan()
check('plan: starts in order, first at the chunk start, all inside the chunk', () => {
  const p = C.plan(SENT, 10, 6);
  assert.strictEqual(p.length, 15);
  assert.ok(near(p[0].start, 10));
  for (let i = 1; i < p.length; i++) assert.ok(p[i].start > p[i - 1].start, 'start ' + i + ' not after ' + (i - 1));
  for (const w of p) {
    assert.ok(w.dur >= C.MIN_FILL - 1e-9 && w.dur <= C.MAX_FILL + 1e-9, 'fill out of range: ' + w.dur);
    assert.ok(w.start + w.dur <= 16 + 1e-9, 'past the chunk end: ' + w.t);
  }
  assert.strictEqual(p.map((w) => w.t).join(' '), SENT);
});
check('plan: start = chunk start + length x weight before / total weight', () => {
  const ws = C.words(SENT);
  const total = ws.reduce((a, w) => a + C.weight(w) + C.pause(w), 0);
  let before = 0;
  const p = C.plan(ws, 2, 6);
  ws.forEach((w, i) => {
    assert.ok(near(p[i].start, 2 + 6 * before / total), 'start of ' + w);
    const share = 6 * C.weight(w) / total;
    if (share >= C.MIN_FILL && share <= C.MAX_FILL) assert.ok(near(p[i].dur, share), 'share of ' + w);
    before += C.weight(w) + C.pause(w);
  });
});
check('plan: fills are kept between 180 and 900 ms', () => {
  const slow = C.plan('Hello', 0, 5);
  assert.ok(near(slow[0].dur, 0.9));
  const fast = C.plan('go go go go go go', 0, 0.6);   // 100 ms shares
  for (const w of fast) assert.ok(w.dur >= 0.18 - 1e-9, 'under 180 ms');
  const last = fast[fast.length - 1];
  assert.ok(last.start + last.dur <= 0.6 + 0.18 + 1e-9, 'a too-short chunk overshoots by at most 180 ms');
});
check('plan: comma and sentence-end pauses', () => {
  const p = C.plan('go, go go. go', 0, 6);            // each go weighs 1.5
  const g1 = p[1].start - p[0].start, g2 = p[2].start - p[1].start, g3 = p[3].start - p[2].start;
  assert.ok(near(g1 / g2, 2), 'comma: (1.5 + 1.5) / 1.5');
  assert.ok(near(g3 / g2, 3), 'end: (1.5 + 3) / 1.5');
});
check('streaming estimate: about 2.6 words a second', () => {
  assert.strictEqual(C.RATE, 2.6);
  assert.ok(near(C.estimate(13), 5));
  const ws = C.words(SENT);
  const est = C.plan(ws, 3, null), known = C.plan(ws, 3, ws.length / 2.6);
  est.forEach((w, i) => { assert.ok(near(w.start, known[i].start)); assert.ok(near(w.dur, known[i].dur)); });
  const rate = ws.length / (C.estimate(ws.length));
  assert.ok(near(rate, 2.6, 1e-9));
});
check('correction: the real length re-spreads the words; words never go back', () => {
  const ws = C.words(SENT);
  const est = C.plan(ws, 0, null), real = C.plan(ws, 0, 9);
  const k = 9 / C.estimate(ws.length);
  est.forEach((w, i) => assert.ok(near(real[i].start, w.start * k, 1e-9)));
  const t = 3;
  est.forEach((w, i) => {
    const before = C.level(w, t);
    assert.ok(C.advance(before, real[i], t) >= before, 'word ' + i + ' went back');
  });
  assert.ok(est.some((w, i) => C.level(w, t) > C.level(real[i], t)), 'the slower plan is behind at t=3');
});
check('word levels and classes', () => {
  const w = { start: 1, dur: 0.5 };
  assert.strictEqual(C.level(w, 0.5), C.LATER);
  assert.strictEqual(C.level(w, 0.9), C.NEXT);           // 150 ms early: empty outline
  assert.strictEqual(C.level(w, 1.01), 1);
  assert.strictEqual(C.level(w, 1.25), 5);
  assert.strictEqual(C.level(w, 1.49), 9);
  assert.strictEqual(C.level(w, 1.5), C.DONE);
  assert.strictEqual(C.wordClass(C.LATER), 'w later');
  assert.strictEqual(C.wordClass(C.NEXT), 'w');
  assert.strictEqual(C.wordClass(5), 'w on f5');
  assert.strictEqual(C.wordClass(C.DONE), 'w done');
  assert.strictEqual(C.wordClass(C.DONE, true), 'w done on');
});

// ------------------------------------------------------------------ lines
check('lines break by width, never inside a word, and stay put when words are added', () => {
  assert.deepStrictEqual(C.breakLines([100, 100, 100, 100], 320, 10), [0, 0, 0, 1]);
  assert.deepStrictEqual(C.breakLines([500, 100], 300, 10), [0, 1]);
  assert.deepStrictEqual(C.breakLines([100, 500, 100], 300, 10), [0, 1, 2]);
  const all = C.breakLines([90, 120, 60, 200, 80, 150, 70], 400, 20);
  assert.deepStrictEqual(C.breakLines([90, 120, 60, 200], 400, 20), all.slice(0, 4));
  assert.strictEqual(C.windowTop(0), 0);
  assert.strictEqual(C.windowTop(1), 0);
  assert.strictEqual(C.windowTop(2), 1);
});

// ------------------------------------------------------------------ Live timing
check('Live: text after its audio takes the waiting audio', () => {
  const L = new C.LiveTrack();
  assert.strictEqual(L.audio(0, 0.5), null);
  L.audio(0.5, 0.5);
  const p1 = L.piece(3, 0.1);
  assert.ok(near(p1.at, 0) && near(p1.dur, 1) && !p1.hungry);
  assert.strictEqual(L.audio(1, 0.5), null);              // waits for the next piece
  const p2 = L.piece(2, 0.6);
  assert.ok(near(p2.at, 1) && p2.hungry && near(p2.dur, 2 / 2.6));
  assert.strictEqual(L.audio(1.5, 0.5), p2);              // a hungry piece takes what follows
  assert.ok(near(p2.dur, 1) && !p2.hungry);
});
check('Live: text before its audio re-anchors on its first sound', () => {
  const L = new C.LiveTrack();
  const p = L.piece(4, 2);
  assert.ok(near(p.at, 2) && p.hungry && near(p.dur, 4 / 2.6));
  L.audio(2.3, 0.4);
  assert.ok(near(p.at, 2.3) && p.hungry);
  L.audio(2.7, 0.8);
  assert.ok(near(p.dur, 1.2) && !p.hungry);
});
check('Live: audio that already played is not given to a new piece', () => {
  const L = new C.LiveTrack();
  L.audio(0, 0.5);
  const p = L.piece(2, 5);
  assert.ok(near(p.at, 5));
});

// ------------------------------------------------------------------ the caption object, on a tiny fake page
let T = 0;
const rafQ = [];
let timers = [], clockMs = 0;
global.setTimeout = (f, ms) => { const t = { f, at: clockMs + (ms || 0) }; timers.push(t); return t; };
global.clearTimeout = (t) => { timers = timers.filter((x) => x !== t); };
function runTimers(ms) {
  const end = clockMs + ms;
  for (;;) {
    timers.sort((a, b) => a.at - b.at);
    const t = timers[0];
    if (!t || t.at > end) break;
    timers.shift(); clockMs = t.at; t.f();
  }
  clockMs = end;
}
function frame(t) { T = t; const q = rafQ.splice(0); q.forEach((f) => f()); }

class El {
  constructor(doc) { this.ownerDocument = doc; this.children = []; this.parentNode = null; this.cls = new Set(); this.style = {}; this.attrs = {}; this.text = ''; this.hidden = false; }
  get className() { return [...this.cls].join(' '); }
  set className(v) { this.cls = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get classList() {
    const s = this.cls;
    return {
      add: (...a) => a.forEach((x) => s.add(x)), remove: (...a) => a.forEach((x) => s.delete(x)),
      toggle: (x, f) => { const on = f === undefined ? !s.has(x) : !!f; if (on) s.add(x); else s.delete(x); return on; },
      contains: (x) => s.has(x)
    };
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); this.children.push(c); c.parentNode = this; return c; }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentNode = null; return c; }
  get textContent() { return this.children.length ? this.children.map((c) => c.textContent).join('') : this.text; }
  set textContent(v) { this.children.forEach((c) => { c.parentNode = null; }); this.children = []; this.text = String(v); }
  getBoundingClientRect() { return { width: this.textContent.length * 30 }; }
  get clientWidth() { for (let e = this; e; e = e.parentNode) if (e.cls.has('cap')) return e.cls.has('left') ? 330 : 660; return 660; }
  get offsetHeight() { return 0; }
}
const win = {
  requestAnimationFrame: (f) => { rafQ.push(f); return rafQ.length; },
  cancelAnimationFrame: () => { rafQ.length = 0; },
  getComputedStyle: () => ({ columnGap: '20px' }),
  addEventListener() {}, removeEventListener() {}, innerWidth: 1280
};
const doc = { defaultView: win, createElement: () => new El(doc) };
const host = new El(doc);
const region = new El(doc);
const told = [];   // every write to the live region
Object.defineProperty(region, 'textContent', { get: () => told[told.length - 1] || '', set: (v) => { told.push(String(v)); } });
const clock = () => T;
const capEl = () => host.children[host.children.length - 1];
const track = () => capEl().children[0];
const spans = () => track().children.flatMap((l) => l.children);
const classes = () => spans().map((s) => s.className);

check('Normal: words show, fill and finish on the playback clock; lines and the live region', () => {
  T = 0; told.length = 0;
  const cap = C.create(host, { liveRegion: region, clock });
  const id = cap.sentence(SENT, { at: 1, dur: null });
  assert.ok(id > 0);
  assert.ok(!capEl().classList.contains('hidden'));
  assert.ok(capEl().getAttribute('aria-hidden') === 'true');
  assert.ok(classes().every((c) => c === 'w later'), 'all hidden, holding their place');
  assert.ok(track().children.length >= 3, 'needs 3+ lines for this check');
  frame(0.9);
  assert.strictEqual(classes()[0], 'w', 'first word is an empty outline 150 ms early');
  frame(1.02);
  assert.strictEqual(classes()[0], 'w on f1');
  frame(3);
  const doneAt3 = classes().filter((c) => c === 'w done').length;
  cap.setDuration(id, 30);                                 // much slower than the estimate
  frame(3);
  assert.ok(classes().filter((c) => c === 'w done').length >= doneAt3, 'words never go back');
  cap.setDuration(id, 5);
  frame(10);
  assert.ok(classes().every((c) => c === 'w done'));
  assert.strictEqual(told.join(' '), SENT, 'each finished sentence goes to the live region once');
  assert.ok(track().children[0].classList.contains('gone'), 'the top line floats away when a third starts');
  runTimers(700);
  assert.strictEqual(track().children.length, 2, 'the gone lines are removed; two stay');
  cap.stopped();
  runTimers(10);
  assert.ok(!capEl().classList.contains('hidden'), 'still there right after she finished');
  runTimers(4000);
  assert.ok(capEl().classList.contains('hidden'), 'faded 4 s after she finished');
  runTimers(500);
  assert.strictEqual(track().children.length, 0, 'emptied after the fade');
  assert.strictEqual(rafQ.length, 0, 'no frame loop when nothing shows');
  cap.destroy();
});

check('Live: pieces glue split words, cut keeps what she said, late pieces are dropped', () => {
  T = 0; region.textContent = '';
  const ctx = { get currentTime() { return T; } };
  const cap = C.create(host, { liveRegion: region });
  cap.liveAudio(0, 0.5, ctx);
  cap.livePiece('Good mor');
  cap.livePiece('ning, sunshine! I hope ');
  cap.liveAudio(0.5, 1.5, ctx);
  assert.deepStrictEqual(spans().map((s) => s.getAttribute('data-t')), ['Good', 'morning,', 'sunshine!', 'I', 'hope']);
  frame(0.4);
  frame(0.6);
  assert.ok(classes()[0] === 'w done');
  cap.cut();
  assert.ok(classes().some((c) => c.includes('cut')), 'unsaid words fade');
  assert.ok(!classes().some((c) => / on /.test(' ' + c + ' ')), 'nothing is filling after a cut');
  assert.ok(/^Good/.test(region.textContent), 'what she said is told');
  assert.strictEqual(cap.livePiece(' you slept well.'), 0, 'a late piece of the cut speech is dropped');
  cap.clear();
  runTimers(500);
  assert.strictEqual(track().children.length, 0);
  assert.ok(cap.livePiece('Hello there.') > 0, 'after the resident talks, new pieces show');
  cap.destroy();
});

check('Emergency: the whole text at once, filled, the spoken word lifts', () => {
  T = 0; region.textContent = '';
  const cap = C.create(host, { liveRegion: region, clock });
  const text = 'Please press your call light now, or tell a staff member.';
  cap.whole(text, { at: 0, dur: 4 });
  assert.ok(classes().every((c) => c.startsWith('w done')));
  assert.strictEqual(region.textContent, text);
  frame(0.05);
  assert.strictEqual(classes()[0], 'w done on');
  frame(2);
  assert.strictEqual(classes().filter((c) => c === 'w done on').length, 1);
  frame(5);
  assert.ok(classes().every((c) => c === 'w done'));
  cap.destroy();
});

check('Menu open: lines are laid out again for the narrower caption; plain lines', () => {
  T = 0;
  const cap = C.create(host, { liveRegion: region, clock });
  cap.sentence('Good morning, sunshine! I hope you slept well.', { at: 0, dur: 3 });
  const wide = track().children.length;
  cap.setSide(true);
  assert.ok(capEl().classList.contains('left'));
  assert.ok(track().children.length > wide, 'more lines when narrower');
  assert.strictEqual(spans().map((s) => s.getAttribute('data-t')).join(' '), 'Good morning, sunshine! I hope you slept well.');
  cap.plain('You said: my lunch never came', 'said');
  const pl = capEl().children[2];
  assert.ok(!pl.hidden && pl.classList.contains('said') && pl.textContent === 'You said: my lunch never came');
  assert.strictEqual(region.textContent, 'You said: my lunch never came');
  assert.strictEqual(track().children.length, 0);
  cap.destroy();
});

console.log('OK ' + count);
