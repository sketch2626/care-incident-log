// M13b: "one thing beside Mary at a time": web/mary/skills.js with the real show() from web/mary/app.js, on a stubbed page.
const fs = require('fs'), vm = require('vm'), assert = require('assert');

class El {
  constructor() { this.hidden = false; this.children = []; this.style = {}; this.attrs = {}; this.classList = { toggle() {} }; }
  get firstChild() { return this.children[0] || null; }
  appendChild(c) { this.children.push(c); return c; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener() {}
}
const scr = new El();
global.document = { readyState: 'complete', body: new El(), head: new El(), createElement: () => new El(),
  getElementById: () => scr, addEventListener() {} };

const LIST = [{ name: 'word_search', on: true, menu: { label: 'Word search' } }, { name: 'pictures', on: true, menu: { label: 'Pictures' } }];
const sent = [];
global.fetch = (url, init) => {
  if (url !== '/api/mary/skills') { sent.push(JSON.parse(init.body)); }
  return Promise.resolve({ json: () => Promise.resolve({ skills: LIST, effects: [] }) });
};

const S = { screen: 'everyday' }, screens = { everyday: {}, emergency: {} };
const src = fs.readFileSync('web/mary/app.js', 'utf8');
function fn(sig) {
  const rest = src.slice(src.indexOf(sig)), end = rest.search(/\r?\n  \}\r?\n/);
  assert.ok(src.includes(sig) && end > 0, sig);
  return rest.slice(0, end) + '\n  }\n';
}
const page = { setAttribute() {}, classList: { toggle() {} } };
const show = new Function('S', '$', 'screens', 'face', 'log', fn('function show(name, opts) {') + 'return show;')(
  S, () => page, screens, { setEmergency() {} }, e => { throw e; });

const slides = [], events = [];
global.window = { MaryApp: { show, currentScreen: () => S.screen, registerScreen(n, h) { screens[n] = h; },
  sideBySide(on) { slides.push(!!on); } } };
vm.runInThisContext(fs.readFileSync('web/mary/skills.js', 'utf8'));
const M = window.MarySkills;

function skill(name, extra) {
  M.register(name, Object.assign({ aside: true, enter() { events.push(name + ' enter'); }, leave() { events.push(name + ' leave'); } }, extra));
}
skill('word_search', { setAside: true });
skill('pictures', { backChanged() { events.push('pictures backChanged'); } });

const box = n => scr.children.find(b => b.attrs['data-skill'] === n);
const clear = () => { events.length = 0; slides.length = 0; sent.length = 0; };
function reset() { show('emergency'); show('everyday'); clear(); }
function pictureOverGame() { reset(); show('word_search'); show('pictures'); clear(); }
function gameIsBack() {
  assert.equal(S.screen, 'word_search');
  assert.deepEqual(events, ['pictures leave'], 'the game is not started again');
  assert.equal(box('word_search').hidden, false);
  assert.equal(box('pictures').hidden, true);
  assert.equal(M.comingBack(), null);
  assert.equal(M.backLabel(), null);
  assert.ok(!slides.includes(false), 'Mary stays beside it');
}

(async () => {
  await new Promise(r => setTimeout(r, 1));   // the skills list comes in

  // a picture over the game (a tool call or the menu: both are show('pictures')): the game waits as it was
  show('word_search'); clear();
  show('pictures');
  assert.deepEqual(events, ['pictures enter'], 'the game is not ended');
  assert.equal(S.screen, 'pictures');
  assert.equal(box('word_search').hidden, true);
  assert.equal(box('pictures').hidden, false);
  assert.equal(M.comingBack(), 'word_search');
  assert.equal(M.backLabel(), 'word search');
  assert.ok(!slides.includes(false), 'Mary stays beside it');

  // the picture closed by a tap or a Back button, then the game's own Back really ends it
  clear(); show('everyday'); gameIsBack();
  clear(); show('everyday');
  assert.equal(S.screen, 'everyday');
  assert.deepEqual(events, ['word_search leave']);
  assert.deepEqual(slides, [false]);

  // the picture closed by voice
  pictureOverGame();
  M.apply({ kind: 'leave_screen', data: { screen: 'pictures' } });
  gameIsBack();

  // the game resumed by voice with the picture up
  pictureOverGame();
  M.apply({ kind: 'show_screen', data: { screen: 'word_search' } });
  gameIsBack();

  // an emergency: nothing comes back after it
  pictureOverGame();
  show('emergency');
  assert.deepEqual(events, ['pictures leave', 'word_search leave']);
  assert.equal(M.comingBack(), null);
  assert.equal(box('word_search').hidden, true);
  assert.ok(slides.includes(false));
  show('everyday');
  assert.equal(S.screen, 'everyday');

  // the game ended while hidden: it stays gone and the picture's Back changes
  pictureOverGame();
  M.apply({ kind: 'leave_screen', data: { screen: 'word_search' } });
  assert.deepEqual(events, ['word_search leave', 'pictures backChanged']);
  assert.equal(S.screen, 'pictures');
  assert.equal(M.comingBack(), null);
  clear(); show('everyday');
  assert.equal(S.screen, 'everyday');
  assert.deepEqual(events, ['pictures leave']);
  assert.deepEqual(slides, [false]);

  // a game started over a picture replaces it, and Mary doesn't slide out and back
  reset(); show('pictures'); clear();
  show('word_search');
  assert.deepEqual(events, ['pictures leave', 'word_search enter']);
  assert.equal(M.comingBack(), null);
  assert.ok(!slides.includes(false));

  // every call says what is on screen and what waits; none says it when nothing does
  pictureOverGame();
  await M.call('pictures__next', {});
  assert.equal(sent[0].screen, 'pictures');
  assert.equal(sent[0].aside, 'word_search');
  reset();
  await M.call('pictures__next', {});
  assert.ok(!('aside' in sent[0]) && !('screen' in sent[0]));

  // two games that both wait: B over A, Back from B brings A back, and A's Back reaches everyday (no endless swap)
  skill('game_a', { setAside: true });
  skill('game_b', { setAside: true });
  reset(); show('game_a'); clear();
  show('game_b');
  assert.equal(S.screen, 'game_b');
  assert.equal(M.comingBack(), 'game_a');
  clear(); show('everyday');
  assert.equal(S.screen, 'game_a', 'Back from B returns to A');
  assert.equal(M.comingBack(), null, 'nothing is left waiting');
  assert.equal(box('game_a').hidden, false);
  assert.equal(box('game_b').hidden, true);
  clear(); show('everyday');
  assert.equal(S.screen, 'everyday', "A's Back reaches everyday");
  assert.ok(events.includes('game_a leave'));
  assert.equal(M.comingBack(), null);

  // a game switched off by voice while it is hidden: closing the picture lands on everyday, and the picture heard it
  reset(); show('game_a'); show('pictures'); clear();
  assert.equal(M.comingBack(), 'game_a');
  M.apply({ kind: 'settings', data: { skills: { game_a: false } } });
  assert.ok(events.includes('pictures backChanged'), 'the picture hears where Back goes now');
  assert.equal(M.comingBack(), null);
  assert.equal(S.screen, 'pictures');
  clear(); show('everyday');
  assert.equal(S.screen, 'everyday');
  assert.equal(box('game_a').hidden, true);

  console.log('OK skills aside');
})().catch(e => { console.error(e); process.exit(1); });
