/* M15c: the count's logic in skills/messages/screen.js, with no page: the order of things, and that a stop can never reach
   count_done. Run by tests/test_m15c_screen_js.py. */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.join(__dirname, '..', '..');
global.window = global;
global.MarySkills = { register() {} };
vm.runInThisContext(fs.readFileSync(path.join(ROOT, 'skills', 'messages', 'screen.js'), 'utf8'));
const C = global.MaryMessagesCount;

const later = () => new Promise((done) => setImmediate(done));
async function settle() { for (let i = 0; i < 30; i++) { await later(); } }

// Everything the count does to the world goes in log. listen() hands out one answer at a time from opts.heard.
function world(opts) {
  opts = Object.assign({ live: false, heard: [], check: () => Promise.resolve({ send: { action: 'quiet' } }) }, opts);
  const log = [];
  const io = {
    live: opts.live,
    lead: () => { log.push('lead'); return Promise.resolve(); },
    wait: (ms) => {
      log.push('wait ' + ms);
      return ms === C.WORDS_MS && opts.wordsLate ? opts.wordsLate : later();
    },
    blocked: () => !!(opts.blocked && opts.blocked()),
    digit: (n) => { log.push('digit ' + n); if (opts.onDigit) { opts.onDigit(n, core); } },
    hush: () => log.push('hush'),
    listen: () => {
      log.push('listen');
      const next = opts.heard.shift();
      if (next === undefined) { return new Promise(() => {}); }   // open until the end of the count
      return typeof next === 'function' ? next() : Promise.resolve(next);
    },
    endListen: () => log.push('endListen'),
    dropListen: () => log.push('dropListen'),
    check: (text) => { log.push('check ' + text); return opts.check(text); },
    emergency: () => log.push('emergency'),
    acted: (send) => log.push('acted ' + send.action),
    stoppedHere: () => log.push('stoppedHere'),
    undo: () => { log.push('undo'); return opts.undo ? opts.undo() : Promise.resolve(); },
    done: () => { log.push('done'); return Promise.resolve(); }
  };
  const core = C.makeCount(io);
  return { core, log };
}

const count = (log, what) => log.filter((x) => x === what).length;

(async () => {
  // ---- the stop words: the same list as send_gate.py
  const gate = fs.readFileSync(path.join(ROOT, 'send_gate.py'), 'utf8');
  const stopWords = /^STOP_WORDS = \(([^)]*)\)/m.exec(gate)[1].match(/"[^"]+"/g).map((w) => w.slice(1, -1));
  assert.ok(stopWords.length >= 11);
  stopWords.forEach((w) => assert.ok(C.stopHeard(w), 'not heard as a stop: ' + w));
  const js = fs.readFileSync(path.join(ROOT, 'skills', 'messages', 'screen.js'), 'utf8');
  const listed = /var STOP_RE = \/\\b\(\?:(.*)\)\\b\/;/.exec(js)[1].split('|').map((w) => w.replace(/\\s\+/g, ' '));
  assert.deepStrictEqual(listed.filter((w) => w !== 'dont').sort(), stopWords.slice().sort());
  ['Stop!', 'no no no', 'NO', 'Don’t send it', "don't", 'dont', 'hang  on', 'never   mind', 'oh wait', 'not yet'].forEach((t) => assert.ok(C.stopHeard(t), t));
  ['send it', 'know', 'nothing', 'notes', 'stopped', 'okay', 'thank you', '', null].forEach((t) => assert.ok(!C.stopHeard(t), String(t)));

  // ---- her line: Normal
  assert.ok(!C.leadOver(0, false));
  assert.ok(!C.leadOver(C.LEAD_MIN - 1, false));
  assert.ok(C.leadOver(C.LEAD_MIN, false));
  assert.ok(!C.leadOver(C.LEAD_MAX - 1, true));
  assert.ok(C.leadOver(C.LEAD_MAX, true));

  // ---- Live: 5 to 1, a second each, then count_done; no mic of its own
  {
    const { core, log } = world({ live: true });
    await core.start();
    assert.deepStrictEqual(log.filter((x) => /^digit/.test(x)), ['digit 5', 'digit 4', 'digit 3', 'digit 2', 'digit 1', 'digit 0']);
    assert.strictEqual(log.filter((x) => x === 'wait ' + C.DIGIT_MS).length, 5);
    assert.strictEqual(C.DIGIT_MS, 1000);
    assert.strictEqual(log[0], 'lead');
    assert.strictEqual(count(log, 'done'), 1);
    assert.strictEqual(log[log.length - 1], 'done');
    assert.strictEqual(count(log, 'listen'), 0);
    assert.strictEqual(count(log, 'hush'), 4);     // never on the first digit, so her "Going to" line isn't cut
  }

  // ---- Live: a stop word in the growing words posts undo at once, once
  {
    const { core, log } = world({ live: true, onDigit: (n, c) => { if (n === 3) { c.piece('send it'); c.piece('oh no'); c.piece('oh no wait'); } } });
    await core.start();
    await settle();
    assert.strictEqual(count(log, 'undo'), 1);
    assert.strictEqual(count(log, 'done'), 0);
    assert.ok(!log.includes('digit 2'));
  }

  // ---- Normal: the words are checked before count_done
  {
    let release;
    const words = new Promise((done) => { release = done; });
    const { core, log } = world({ heard: [() => words], onDigit: (n) => { if (n === 0) { release('oh that looks lovely'); } } });
    await core.start();
    assert.ok(log.indexOf('listen') > log.indexOf('digit 5'));
    assert.ok(log.indexOf('endListen') > log.indexOf('digit 0'));
    assert.ok(log.indexOf('check oh that looks lovely') > log.indexOf('endListen'));
    assert.ok(log.indexOf('done') > log.indexOf('acted quiet'));
    assert.strictEqual(count(log, 'done'), 1);
  }

  // ---- Normal: a slow check still comes before count_done
  {
    let answer;
    const { core, log } = world({
      heard: ['hello'],
      check: () => new Promise((done) => { answer = done; })
    });
    const run = core.start();
    await settle();
    assert.strictEqual(count(log, 'done'), 0);
    answer({ send: { action: 'quiet' } });
    await run;
    assert.strictEqual(count(log, 'done'), 1);
  }

  // ---- Normal: a stop in the words: never count_done, even when the digits were done
  {
    const { core, log } = world({ heard: ['wait a minute'], check: () => Promise.resolve({ send: { action: 'stopped', say: 'Stopped.' } }) });
    await core.start();
    await settle();
    assert.strictEqual(count(log, 'done'), 0);
    assert.strictEqual(count(log, 'acted stopped'), 1);
    assert.strictEqual(count(log, 'stoppedHere'), 0);
  }

  // ---- Normal: a stop word the server didn't act on still stops, here
  {
    const { core, log } = world({ heard: ['stop'], check: () => Promise.resolve({}) });
    await core.start();
    await settle();
    assert.strictEqual(count(log, 'done'), 0);
    assert.strictEqual(count(log, 'stoppedHere'), 1);
  }

  // ---- Normal: the gate stopped on words the page's list missed
  {
    const { core, log } = world({ heard: ['hmm'], check: () => Promise.resolve({ send: { action: 'stopped' } }) });
    await core.start();
    await settle();
    assert.strictEqual(count(log, 'done'), 0);
  }

  // ---- Normal: an emergency stops it, and the page acts on it
  {
    const { core, log } = world({ heard: ['I fell'], check: () => Promise.resolve({ emergency: true, say: 'x' }) });
    await core.start();
    await settle();
    assert.strictEqual(count(log, 'emergency'), 1);
    assert.strictEqual(count(log, 'done'), 0);
  }

  // ---- Normal: words nobody could check never go through
  {
    const { core, log } = world({ heard: ['hello'], check: () => Promise.reject(new Error('down')) });
    await core.start();
    await settle();
    assert.strictEqual(count(log, 'done'), 0);
    assert.strictEqual(count(log, 'stoppedHere'), 1);
  }

  // ---- Normal: no words at all in 6 s: it goes, as the design says, and words after that still get the emergency check
  {
    let release;
    const words = new Promise((done) => { release = done; });
    const { core, log } = world({
      heard: [() => words],
      wordsLate: Promise.resolve(),
      check: () => Promise.resolve({ emergency: true, say: 'x' })
    });
    await core.start();
    assert.strictEqual(count(log, 'done'), 1);
    assert.ok(log.includes('wait ' + C.WORDS_MS));
    assert.strictEqual(C.WORDS_MS, 6000);
    release('I fell');
    await settle();
    assert.strictEqual(count(log, 'emergency'), 1);
    assert.strictEqual(count(log, 'stoppedHere'), 0);
  }

  // ---- Normal: a mic that won't open: Undo is still there and the count goes on
  {
    const { core, log } = world({ heard: [() => Promise.reject(new Error('no mic'))] });
    await core.start();
    assert.strictEqual(count(log, 'listen'), 1);
    assert.strictEqual(count(log, 'done'), 1);
  }

  // ---- Normal: words early in the count that aren't a stop: the mic opens again for the rest
  {
    const { core, log } = world({ heard: ['thats nice'] });
    await core.start();
    assert.strictEqual(count(log, 'listen'), 2);
    assert.strictEqual(count(log, 'done'), 1);
  }

  // ---- Undo: never count_done, at any moment, and a failed post stays stopped
  for (const at of [5, 3, 1, 0]) {
    const { core, log } = world({ onDigit: (n, c) => { if (n === at) { c.stop(); } } });
    await core.start();
    await settle();
    assert.strictEqual(count(log, 'undo'), 1, 'undo at ' + at);
    assert.strictEqual(count(log, 'dropListen'), 1);
    assert.strictEqual(count(log, 'done'), 0, 'undo at ' + at);
  }
  {
    const { core, log } = world({ undo: () => Promise.reject(new Error('down')), onDigit: (n, c) => { if (n === 2) { c.stop(); } } });
    await core.start();
    await settle();
    assert.strictEqual(count(log, 'done'), 0);
    assert.strictEqual(count(log, 'stoppedHere'), 1);
  }
  {   // before the digits start: Undo is live at once
    const { core, log } = world({});
    const run = core.start();
    core.stop();
    await run;
    await settle();
    assert.strictEqual(count(log, 'undo'), 1);
    assert.ok(!log.includes('digit 5'));
    assert.strictEqual(count(log, 'done'), 0);
  }
  {   // while the words are awaited, Undo is still live
    let release;
    const words = new Promise((done) => { release = done; });
    const { core, log } = world({ heard: [() => words], wordsLate: new Promise(() => {}) });   // the 6 s hasn't run out
    const run = core.start();
    await settle();
    assert.ok(log.includes('endListen'));
    assert.strictEqual(count(log, 'done'), 0);
    core.stop();
    release('');
    await run;
    await settle();
    assert.strictEqual(count(log, 'undo'), 1);
    assert.strictEqual(count(log, 'done'), 0);
  }

  // ---- the emergency screen: the count stops, wherever it was
  {
    let on = false;
    const { core, log } = world({ live: true, blocked: () => on, onDigit: (n) => { if (n === 2) { on = true; } } });
    await core.start();
    assert.strictEqual(count(log, 'done'), 0);
    assert.ok(!log.includes('digit 1'));
  }
  {   // and in the last moment before count_done
    let on = false;
    const { core, log } = world({ blocked: () => on, onDigit: (n) => { if (n === 0) { on = true; } } });
    await core.start();
    await settle();
    assert.strictEqual(count(log, 'done'), 0);
  }

  // ---- leaving: nothing goes after the screen has gone
  {
    const { core, log } = world({ live: true, onDigit: (n, c) => { if (n === 4) { c.drop(); } } });
    await core.start();
    assert.strictEqual(count(log, 'done'), 0);
    assert.strictEqual(count(log, 'undo'), 0);
  }

  // ---- count_done goes once, and Undo after it does nothing
  {
    const { core, log } = world({ live: true });
    await core.start();
    await core.stop();
    await core.piece('stop');
    assert.strictEqual(count(log, 'done'), 1);
    assert.strictEqual(count(log, 'undo'), 0);
  }

  // ---- the mail picture: the first quality that fits, or a failure
  {
    const tried = [];
    const blob = await C.fitQuality((q) => { tried.push(q); return Promise.resolve({ size: q > 0.65 ? C.MAIL_MAX + 1 : C.MAIL_MAX }); }, C.MAIL_QUALITIES, C.MAIL_MAX);
    assert.deepStrictEqual(tried, [0.8, 0.7, 0.6]);
    assert.strictEqual(blob.size, C.MAIL_MAX);
    assert.strictEqual(C.MAIL_MAX, 590000);
    let failed = false;
    await C.fitQuality(() => Promise.resolve(null), C.MAIL_QUALITIES, C.MAIL_MAX).catch(() => { failed = true; });
    assert.ok(failed);
  }

  console.log('OK m15c screen');
})().catch((e) => { console.error(e); process.exit(1); });
