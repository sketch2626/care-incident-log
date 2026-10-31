
const fs = require('fs'), vm = require('vm'), assert = require('assert');
let now = 1e6; Date.now = () => now;
class CL {
  constructor(el) { this.el = el; }
  add(c) { if (!this.el._cls.includes(c)) this.el._cls.push(c); }
  remove(c) { this.el._cls = this.el._cls.filter(x => x !== c); }
  toggle(c, on) { if (on === undefined) on = !this.contains(c); if (on) this.add(c); else this.remove(c); }
  contains(c) { return this.el._cls.includes(c); }
}
class El {
  constructor(tag) { this.tagName = tag; this.children = []; this._attr = {}; this._cls = []; this.listeners = {};
    this.parentNode = null; this._text = ''; this.classList = new CL(this);
    this.style = { props: {}, setProperty(k, v) { this.props[k] = v; } }; }
  set className(v) { this._cls = String(v).split(/\s+/).filter(Boolean); }
  get className() { return this._cls.join(' '); }
  set textContent(v) { this.children.forEach(c => { c.parentNode = null; }); this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  get firstChild() { return this.children[0] || null; }
  setAttribute(k, v) { this._attr[k] = String(v); }
  getAttribute(k) { return k in this._attr ? this._attr[k] : null; }
  appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) { this.children.splice(this.children.indexOf(c), 1); c.parentNode = null; }
  replaceChild(n, o) { this.children[this.children.indexOf(o)] = n; n.parentNode = this; o.parentNode = null; }
  contains(x) { for (; x; x = x.parentNode) { if (x === this) return true; } return false; }
  matches(sel) { return sel.split('.').filter(Boolean).every(c => this._cls.includes(c)); }
  all() { return this.children.reduce((a, c) => a.concat([c], c.all()), []); }
  querySelector(s) { return this.all().find(e => e.matches(s)) || null; }
  querySelectorAll(s) { return this.all().filter(e => e.matches(s)); }
  closest(s) { for (let e = this; e; e = e.parentNode) { if (e.matches(s)) return e; } return null; }
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
  fire(t, ev) { ev = ev || {}; ev.target = ev.target || this; ev.preventDefault = () => {};
    for (let e = this; e; e = e.parentNode) (e.listeners[t] || []).forEach(f => f(ev)); }
  getBoundingClientRect() { return { left: 0, top: 0, width: 540, height: 540 }; }
  setPointerCapture() {}
  focus() { global.document.activeElement = this; }
}
global.document = { activeElement: null, createElement: t => new El(t), createElementNS: (n, t) => new El(t) };
const said = [], notes = [], calls = [];
let isBusy = false, screen = 'word_search', script = () => ({ ok: true }), h = null;
global.fetch = (url, init) => {
  if (url.endsWith('/view')) { calls.push({ view: true }); return Promise.resolve({ json: () => Promise.resolve({ text: 'VIEW' }) }); }
  const ev = JSON.parse(init.body).event; calls.push(ev);
  try { const r = script(ev); return Promise.resolve({ json: () => Promise.resolve(r) }); } catch (e) { return Promise.reject(e); }
};
global.MarySkills = { register(n, x) { h = x; }, apply(e) { h.effect(e.kind, e.data); } };
global.window = { MarySkills: global.MarySkills, MaryApp: { say(t) { said.push(t); return Promise.resolve(); }, busy: () => isBusy,
  screenNote(t) { notes.push(t); }, companionName: () => 'Mary', currentScreen: () => screen, show(s) { screen = s; } } };
const realLog = console.log; console.log = (...a) => { if (a[0] !== '[word_search]') realLog(...a); };
vm.runInThisContext(fs.readFileSync('skills/word_search/screen.js', 'utf8'));

const P = o => Object.assign({ grid: Array(10).fill('ABCDEFGHIJ'), words: ['BASS', 'TROUT'], theme: 'Fishing', size: 10, level: 2,
  diagonal: false, backward: false, found: [], shown: [], hint: null, finished: false }, o);
const flush = () => new Promise(r => setTimeout(r, 3));
const body = new El('div');
const q = s => body.querySelector(s), qa = s => body.querySelectorAll(s);
function tap(r, c, r2, c2) {
  const g = q('.ws-grid'); now += 1000;
  g.fire('pointerdown', { pointerId: 1, pointerType: 'touch', button: 0, clientX: c * 54 + 20, clientY: r * 54 + 20 });
  g.fire('pointerup', { pointerId: 1, clientX: (c2 === undefined ? c : c2) * 54 + 20, clientY: (r2 === undefined ? r : r2) * 54 + 20 });
  g.fire('click', { target: g });
}
const btn = n => qa('.ans').find(b => b.textContent === n);
const names = () => qa('.ans').map(b => b.textContent).join('|');

(async () => {
  script = ev => ev.type === 'open' ? { effects: [{ kind: 'puzzle', data: P() }], say: "Here's one on fishing." } : { ok: true };
  h.enter(body, {}); await flush();
  assert.equal(calls.filter(e => e.type === 'open').length, 1, 'open once');
  assert.equal(qa('.ws-c').length, 100);
  assert.equal(q('.ws-c').getAttribute('aria-label'), 'row 1, column 1, letter A');
  assert.equal(q('.ws-title').textContent, 'Fishing');
  assert.equal(names(), 'Give me a hint|New puzzle|Back to Mary');
  assert.equal(said.pop(), "Here's one on fishing.");

  h.leave(body); calls.length = 0;
  h.enter(body, {}); h.effect('puzzle', P()); await flush();
  assert.equal(calls.length, 0, 'voice: puzzle right behind show_screen, no open');
  h.leave(body); h.effect('puzzle', P({ theme: 'Birds' })); h.enter(body, {}); await flush();
  assert.equal(calls.length, 0, 'voice: puzzle before enter, no open');
  assert.equal(q('.ws-title').textContent, 'Birds');

  for (const wrap of [true, false]) {
    h.leave(body); h.enter(body, {}); h.effect('puzzle', P()); await flush(); calls.length = 0; notes.length = 0;
    const answer = { found: 'BASS', partial: false };
    script = ev => Object.assign({ effects: [{ kind: 'found', data: { word: 'BASS', cells: [[2, 1], [2, 2], [2, 3], [2, 4]] } }], say: 'Good eye.' },
      wrap ? { response: answer } : answer);
    tap(2, 1); assert.ok(q('.ws-c.picked')); assert.equal(calls.length, 0, 'first tap stays local');
    tap(2, 4); await flush();
    assert.deepEqual(calls[0], { type: 'line', from: [2, 1], to: [2, 4] });
    assert.ok(!q('.ws-c.picked')); assert.ok(q('.ws-mark.h.fresh')); assert.equal(qa('.ws-c.on').length, 4);
    assert.ok(qa('.ws-word')[0].classList.contains('found'));
    assert.equal(notes.pop(), 'What is on the screen now: VIEW'); assert.equal(said.pop(), 'Good eye.');
  }

  calls.length = 0; script = () => ({ response: { found: null, partial: true } });
  tap(5, 0); tap(5, 1); await flush(); assert.equal(qa('.ws-c.picked').length, 2, 'partial keeps the ring');
  tap(5, 2); await flush(); assert.deepEqual(calls[1], { type: 'line', from: [5, 0], to: [5, 2] }); assert.equal(qa('.ws-c.picked').length, 3);
  said.length = 0; script = () => ({ response: { found: null, partial: false } });
  tap(5, 5); await flush(); assert.ok(!q('.ws-c.picked'), 'neither clears'); assert.equal(said.length, 0);
  script = () => ({ ignored: true });
  tap(0, 0); tap(3, 5); await flush(); assert.ok(!q('.ws-c.picked'), 'ignored clears');

  tap(7, 7); assert.ok(q('.ws-c.picked')); tap(7, 7); assert.ok(!q('.ws-c.picked'), 'same letter twice clears');
  tap(7, 7); now += 100; const g = q('.ws-grid');
  g.fire('pointerdown', { pointerId: 2, pointerType: 'touch', button: 0, clientX: 7 * 54 + 9, clientY: 7 * 54 + 9 });
  g.fire('pointerup', { pointerId: 2 }); now += 0;
  assert.ok(q('.ws-c.picked'), 'a bounce is not a second tap'); tap(7, 7);

  tap(1, 1, 1, 3); assert.equal(q('.ws-c.picked').getAttribute('data-c'), '1', 'a slide counts where it began'); tap(1, 1);
  now += 1000; q('.ws-grid').fire('click', { target: qa('.ws-c')[33] }); assert.equal(q('.ws-c.picked').getAttribute('data-r'), '3', 'keyboard click'); tap(3, 3);
  now += 1000; g.fire('pointerdown', { pointerId: 3, pointerType: 'touch', button: 0, clientX: -3, clientY: 600 }); g.fire('pointerup', { pointerId: 3 });
  assert.equal(q('.ws-c.picked').getAttribute('data-r'), '9', 'snaps to the nearest'); assert.equal(q('.ws-c.picked').getAttribute('data-c'), '0'); tap(9, 0);

  script = ev => ev.type === 'hint' ? { effects: [{ kind: 'hint', data: { step: 1, word: 'TROUT', line: { kind: 'row', index: 3 } } }], say: 'Third row.' } : { ok: true };
  btn('Give me a hint').fire('click'); await flush();
  assert.equal(q('.ws-band').style.props['--r'], 3); assert.equal(said.pop(), 'Third row.');
  isBusy = true; h.effect('hint', { step: 1, word: 'TROUT', line: { kind: 'row', index: 3 } });
  btn('Give me a hint').fire('click'); await flush(); assert.equal(said.length, 0, 'busy drops the line'); isBusy = false;
  h.effect('found', { word: 'OTHER', cells: [[8, 0], [8, 1], [8, 2]] }); assert.ok(q('.ws-band'), 'another word leaves the hint');
  h.effect('hint', { step: 2, word: 'TROUT', cell: [3, 0], line: { kind: 'column', index: 0 } });
  assert.ok(q('.ws-band.col')); assert.ok(q('.ws-c.lit'));
  h.effect('shown', { word: 'TROUT', cells: [[3, 0], [4, 0], [5, 0], [6, 0], [7, 0]] });
  assert.ok(!q('.ws-band')); assert.ok(!q('.ws-c.lit')); assert.ok(q('.ws-mark.v.fresh')); assert.ok(qa('.ws-word')[1].classList.contains('shown'));

  btn('New puzzle').fire('click'); assert.equal(names(), 'Bigger letters|Same|More letters|Back');
  btn('Back').fire('click'); assert.equal(names(), 'Give me a hint|New puzzle|Back to Mary');
  calls.length = 0; script = () => ({ response: { ok: true, at_end: true }, say: 'This is the easiest one I have.' });
  btn('New puzzle').fire('click'); btn('Bigger letters').fire('click'); await flush();
  assert.deepEqual(calls[0], { type: 'new', level: 'easier' }); assert.equal(names(), 'Give me a hint|New puzzle|Back to Mary'); said.pop();

  h.effect('found', { word: 'DIAG', cells: [[4, 4], [3, 5], [2, 6]] });
  const d = q('.ws-mark.d'); assert.equal(d.style.props['--a'], '-45deg'); assert.equal(d.style.props['--r'], 4); assert.equal(d.style.props['--n'], 3);
  h.effect('found', { word: 'REV', cells: [[0, 5], [0, 4], [0, 3]] });
  assert.equal(qa('.ws-mark.h').pop().style.props['--c'], 3, 'a word read backward starts from its left end');
  h.effect('found', { word: 'ZZZ', cells: [null] });   // a broken effect is caught

  h.effect('done', { found: 1, shown: 1 });
  assert.equal(names(), 'Bigger letters|Same|More letters|Back to Mary'); assert.ok(q('.ws-title').textContent.endsWith("That's all of them."));
  calls.length = 0; tap(1, 1); assert.ok(!q('.ws-c.picked'), 'no picking when finished');
  script = ev => ev.type === 'new' ? { effects: [{ kind: 'puzzle', data: P({ grid: Array(8).fill('ABCDEFGH'), size: 8, level: 1 }) }] } : { ok: true };
  btn('Same').fire('click'); await flush();
  assert.equal(qa('.ws-c').length, 64); assert.ok(q('.ws.big')); assert.equal(names(), 'Give me a hint|New puzzle|Back to Mary');
  assert.equal(qa('.ws-mark').length, 0);

  h.leave(body); script = () => { throw new Error('down'); };
  h.enter(body, {}); await flush();
  assert.ok(q('.ws-wait'), 'a failed open says the plain line'); assert.equal(names(), 'Try again|Back to Mary');
  script = ev => ev.type === 'open' ? { effects: [{ kind: 'puzzle', data: P() }] } : { ok: true };
  btn('Try again').fire('click'); await flush(); assert.equal(qa('.ws-c').length, 100);
  script = () => { throw new Error('down'); };
  tap(1, 1); tap(1, 2); await flush(); assert.ok(!q('.ws-c.picked'), 'a failed line clears quietly'); tap(1, 1); tap(1, 1);
  screen = 'word_search'; btn('Back to Mary').fire('click'); await flush(); assert.equal(screen, 'everyday', 'Back works offline');
  realLog('screen logic OK');

  const clamp = (lo, v, hi) => Math.max(lo, Math.min(v, hi));
  for (const [W, H] of [[1024, 640], [1280, 800], [1920, 1080]]) {
    const boxW = W * .6, padR = Math.min(28, boxW * .03646), padB = Math.min(32, H * .04), bar = clamp(72, H * .11, 110);
    const lf = clamp(20, boxW * .03385, 34), out = [];
    for (const [n, chars, fit, ratio] of [[8, 7, .9778, .6364], [10, 8, 1, .63], [12, 10, 1, .63], [12, 12, 1, .63]]) {
      const lw = Math.max(lf * 7.077, lf * (chars * .6 + 1.25));
      const side = Math.min(boxW - padR - 16 - lw, H - 124 - 16 - bar - padB) * fit, cell = side / n;
      out.push(`${n}x${n}: side ${side.toFixed(0)} cell ${cell.toFixed(1)} letter ${Math.max(24, cell * ratio).toFixed(1)}`);
    }
    realLog(`${W}x${H} bar ${bar.toFixed(0)} list font ${lf.toFixed(1)} | ` + out.join(' | '));
  }
  realLog('OK word search screen');
})().catch(e => { realLog('FAIL', e.message, e.stack.split('\n')[1]); process.exit(1); });
