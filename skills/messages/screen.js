/* Cards and messages, the page half (M15b). Beside Mary, boards in mockups/mary/round8: the numbered fronts (B), the
   closed card (C), the card opening once (C3), the open spread (C2, C4), the plain message (G) and the keepsake (A).
   This is done by voice: the things to tap are a front on the picker, and from M15c the big Undo, the one quiet Send it
   and the address box. Every card and message shown is a saved picture.
   After a card is saved a small queued job turns it into jpegs for sending later. An event is 4 KB at most, so each
   jpeg goes in pieces. If that fails the svgs still stand, so it's only logged. */
(function () {
  'use strict';
  var NAME = 'messages';
  var EVENT_URL = '/api/mary/skills/' + NAME + '/event';
  var IMAGE_URL = '/api/mary/skills/' + NAME + '/image/';
  var PICTURES = { front: [740, 1036], inside: [740, 1036], both: [1480, 1036], mail: [1240, 868] };
  var JPEG_QUALITY = 0.92;
  var PIECE = 3000;          // base64 characters in one event; a multiple of 4
  var PICTURE_WAIT = 3000;   // after the last change, so a run of changes makes one job
  var PIECE_GAP = 15;        // so speech and the screen stay first
  var PRINT_WAIT = 15000;
  var PRINT_KEEP = 60000;
  var MAIL_QUALITIES = [0.8, 0.7, 0.6, 0.5];   // M15c: tried in turn until the mail picture is small enough
  var MAIL_MAX = 590000;     // bytes; the gate takes 600 KB
  var DIGITS = [5, 4, 3, 2, 1];
  var DIGIT_MS = 1000;
  var LIVE_LEAD = 2200;      // Live has no promise for her "Going to" line, so the digits give it this long
  var LEAD_MIN = 400;        // Normal: the count comes just ahead of her line, so it gets this long to start
  var LEAD_MAX = 4000;       // the digits start by this time either way
  var LEAD_STEP = 100;
  var WORDS_MS = 6000;       // Normal: how long the words get after the last digit
  var SENT_HOLD = 3000;      // "Sent to Mark." where Undo was, as on board D3, before board F
  var SURE_WAIT = 6000;      // a line they must hear waits this long for a gap, then goes anyway
  var SURE_STEP = 150;
  var SAY_STOPPED = "Stopped. It hasn't gone.";   // only when the server can't be reached to say it
  var SAY_UNSURE = "I'm not sure that went.";
  var ENVELOPE = '<svg class="mc-envsheet" viewBox="0 0 532 372" preserveAspectRatio="none" aria-hidden="true"><defs>' +
    '<radialGradient id="c8e-g" cx=".42" cy=".36" r=".9"><stop offset="0" stop-color="#fbf3e2"></stop><stop offset="1" stop-color="#efe2c9"></stop></radialGradient>' +
    '<filter id="c8e-f" filterUnits="userSpaceOnUse" x="0" y="0" width="532" height="372" color-interpolation-filters="sRGB">' +
    '<feTurbulence type="fractalNoise" baseFrequency="1.05" numOctaves="3" seed="11" result="t"></feTurbulence>' +
    '<feDiffuseLighting in="t" surfaceScale="0.3" diffuseConstant="1.155" lighting-color="#ffffff" result="l"><feDistantLight azimuth="225" elevation="60"></feDistantLight></feDiffuseLighting>' +
    '<feBlend in="SourceGraphic" in2="l" mode="multiply"></feBlend></filter></defs>' +
    '<rect width="532" height="372" fill="url(#c8e-g)" filter="url(#c8e-f)"></rect></svg>' +
    '<svg class="mc-envrules" viewBox="0 0 532 372" aria-hidden="true"><defs>' +
    '<linearGradient id="c8e-foil" x1="-90" y1="0" x2="90" y2="0" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#6e4e10"></stop><stop offset="0.18" stop-color="#b08a34"></stop>' +
    '<stop offset="0.34" stop-color="#f2dd98"></stop><stop offset="0.5" stop-color="#94701f"></stop><stop offset="0.68" stop-color="#e4c878"></stop><stop offset="0.84" stop-color="#9e7a26"></stop>' +
    '<stop offset="1" stop-color="#6a4a0e"></stop></linearGradient>' +
    '<linearGradient id="c8e-wine" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7a2540"></stop><stop offset="1" stop-color="#4a1020"></stop></linearGradient></defs>' +
    '<path d="M2 3 266 196 530 3M2 369 214 152M530 369 318 152" fill="none" stroke="#7a5c34" stroke-width="1.4" opacity=".12"></path>' +
    '<rect x="1.5" y="1.5" width="529" height="369" fill="none" stroke="#fffaf0" stroke-width="1.6" opacity=".85"></rect>' +
    '<path d="M1 371H531V1" fill="none" stroke="#8a6e46" stroke-width="1.6" opacity=".55"></path>' +
    '<rect x="441" y="28" width="70" height="88" fill="#5a4020" opacity=".22"></rect>' +
    '<rect x="438" y="24" width="70" height="88" fill="#fffaf0" stroke="#fffaf0" stroke-width="7" stroke-dasharray=".1 9" stroke-linecap="round"></rect>' +
    '<rect x="443" y="29" width="60" height="78" fill="url(#c8e-wine)"></rect>' +
    '<rect x="447" y="33" width="52" height="70" fill="none" stroke="url(#c8e-foil)" stroke-width="1"></rect>' +
    '<g transform="translate(473 68) scale(.3)" fill="url(#c8e-foil)"><path d="M0 0C-8 -7 -20 -8 -33 0C-20 8 -8 7 0 0Z"></path><path d="M0 0C8 -7 20 -8 33 0C20 8 8 7 0 0Z"></path>' +
    '<path d="M0 -8C-4 -3 -4 3 0 8C4 3 4 -3 0 -8Z"></path><path d="M-33 0H-92M33 0H92" stroke-width="1.2" stroke="url(#c8e-foil)"></path></g></svg>';
  var CHECK = '<svg class="mc-done" viewBox="0 0 110 110" aria-hidden="true"><circle cx="55" cy="55" r="55" fill="#0f5560"></circle>' +
    '<path d="M28 58l19 19 36-42" fill="none" stroke="#ffffff" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"></path></svg>';

  var root = null;
  var visit = 0;
  var shown = false;
  var tapped = false;
  var spread = null;         // the open card on screen: {id, front, inside, left}
  var stamp = Date.now();    // each picture name gets a new ?v=
  var waiting = null;        // the newest card waiting for its jpegs
  var waitTimer = null;
  var running = false;
  var lookData = null;       // M15c: the look last drawn, which the count and board F reuse
  var drawn = null;          // what's on screen for it: {look, box, main, title, letter, src, extra}
  var count = null;          // the count that's running: {look, box, core, going, undo, digits, line, timer}
  var countEnded = false;    // count_done went this visit, so leaving needs no "left"
  var sentTimer = null;
  var typed = '';            // what was typed for an address, there again after a bad one

  function log(e) { try { console.log('[messages]', e); } catch (x) { /* nothing */ } }
  function pause(ms) { return new Promise(function (done) { setTimeout(done, ms); }); }

  function post(event) {
    return fetch(EVENT_URL, {
      method: 'POST', cache: 'no-store',
      headers: { 'X-Tracker': '1', 'Content-Type': 'application/json' },
      body: JSON.stringify({ event: event })
    }).then(function (r) { return r.json(); });
  }

  // A move on the screen: its effects are for this visit only.
  function move(event, sure) {
    var mine = visit;
    return post(event).then(function (res) {
      var effects = (mine === visit && res && res.effects) || [];
      for (var i = 0; i < effects.length; i++) { window.MarySkills.apply(effects[i]); }
      return mine === visit ? speak(res, sure) : undefined;
    }).catch(log);
  }

  // The answer to a gate move: its effects whatever visit this is, because a look or "Sent to Mark" still stands. The
  // skill's screen drops what it can't show.
  function land(res) {
    var effects = (res && res.effects) || [];
    for (var i = 0; i < effects.length; i++) { window.MarySkills.apply(effects[i]); }
    return speak(res, true);
  }

  // M15c: waits for a gap in the talk, for at most SURE_WAIT.
  function gap(a) {
    var began = Date.now();
    return new Promise(function (done) {
      (function look() {
        if (!a.busy || !a.busy() || Date.now() - began >= SURE_WAIT) { done(); return; }
        setTimeout(look, SURE_STEP);
      })();
    });
  }

  // Her line after a tap, unless she or the resident is in the middle of something. The screen note still tells her.
  // M15c: sure is a line they must hear ("Sent to Mark", "Stopped"): it's never dropped, it waits for a gap and then goes.
  function speak(res, sure) {
    var a = window.MaryApp, text = res && res.say;
    if (!text || !a || !a.say) { return Promise.resolve(); }
    return (sure ? gap(a) : Promise.resolve()).then(function () {
      if (!sure && a.busy && a.busy()) { return undefined; }
      return a.say(text);
    }).catch(log);
  }

  // ---------- the count's logic, with no page in it, so tests/js/m15c_screen.js can drive it ----------

  // STOP_WORDS in send_gate.py, the same list; that test compares them.
  var STOP_RE = /\b(?:stop|undo|wait|no|don't|dont|cancel|hold|hang\s+on|never\s+mind|oops|not)\b/;
  function stopHeard(text) {
    return STOP_RE.test(String(text == null ? '' : text).toLowerCase().replace(/’/g, "'"));
  }

  // Normal: true once her "Going to" line has had its chance.
  function leadOver(waited, speaking) {
    return waited >= LEAD_MAX || (waited >= LEAD_MIN && !speaking);
  }

  // The best quality that's small enough. make(quality) resolves with a blob.
  function fitQuality(make, qualities, max) {
    var i = 0;
    return (function next() {
      if (i >= qualities.length) { return Promise.reject(new Error('the mail picture is too big')); }
      return make(qualities[i++]).then(function (blob) { return (blob && blob.size <= max) ? blob : next(); });
    })();
  }

  // One count. io is everything it does to the outside world. It only ever moves forward by the clock, and nothing but
  // the end of send() can ask for the send: once stopped is true, that can't happen. A word that couldn't be checked
  // stops it too. Words that come in after the last 6 s still get the emergency check.
  function makeCount(io) {
    var stopped = false;   // it can never send now
    var gone = false;      // count_done went
    var closing = false;   // the last digit is done; Normal is waiting for the words
    var words = null;      // Normal: the listen that's open
    var checking = null;   // Normal: words on their way to /api/mary/heard

    function check(text) {
      if (!gone && stopHeard(text)) { stopped = true; }   // first, so the clock can't get ahead of the post
      return io.check(text).then(function (j) {
        if (j && j.emergency) { stopped = true; io.emergency(j); return; }
        var acted = j && j.send;
        if (acted && acted.action === 'stopped') { stopped = true; }
        if (acted) { io.acted(acted); }
        if (stopped && !gone && !(acted && acted.action === 'stopped')) { io.stoppedHere(); }
      }, function (e) {
        if (gone) { return; }
        stopped = true;
        io.stoppedHere(e);
      });
    }

    function listen() {
      if (stopped || closing) { return; }
      words = io.listen().then(function (text) {
        words = null;
        checking = (text ? check(text) : Promise.resolve()).then(function () {
          checking = null;
          listen();
        });
      }, function () { words = null; });   // no mic, or something else took it: Undo is still up
    }

    function send() {
      if (io.blocked()) { stopped = true; }
      if (stopped || gone) { return undefined; }
      gone = true;
      return io.done();
    }

    function finish() {
      io.digit(0);
      if (io.live) { return send(); }
      closing = true;
      io.endListen();
      return Promise.race([words || Promise.resolve(), io.wait(WORDS_MS)]).then(function () {
        return checking;
      }).then(send);
    }

    function tick(i) {
      if (io.blocked()) { stopped = true; }
      if (stopped) { return undefined; }
      if (i === DIGITS.length) { return finish(); }
      io.digit(DIGITS[i]);
      if (i === 0 && !io.live) { listen(); }
      if (i > 0) { io.hush(); }             // the first digit leaves room for the end of her "Going to" line
      return io.wait(DIGIT_MS).then(function () { return tick(i + 1); });
    }

    function stop() {
      if (stopped || gone) { return Promise.resolve(); }
      stopped = true;
      io.dropListen();
      return io.undo().then(undefined, function (e) { io.stoppedHere(e); });   // a failed post stays stopped
    }

    return {
      start: function () { return io.lead().then(function () { return tick(0); }); },
      stop: stop,
      piece: function (text) { return stopHeard(text) ? stop() : Promise.resolve(); },
      drop: function () { stopped = true; }
    };
  }

  function url(file) { return IMAGE_URL + encodeURIComponent(file); }
  function fresh(file) { stamp++; return url(file) + '?v=' + stamp; }

  function part(tag, cls, parent) {
    var el = document.createElement(tag);
    if (cls) { el.className = cls; }
    if (parent) { parent.appendChild(el); }
    return el;
  }

  function image(cls, parent) {
    var img = part('img', cls, parent);
    img.alt = '';
    img.draggable = false;
    return img;
  }

  // Resolves when the picture is in, or when it failed: a missing picture shouldn't hold up the card.
  function load(img, src) {
    return new Promise(function (done) {
      img.onload = img.onerror = function () { done(); };
      img.src = src;
    });
  }

  // Swaps a picture in place with no blank moment: the new one is fetched first.
  function swap(img, src) {
    var next = new Image();
    return load(next, src).then(function () { img.src = src; });
  }

  function clear() {
    root.textContent = '';
    spread = null;
    drawn = null;
    clearTimeout(sentTimer);
    return part('div', 'mc', root);
  }

  // ---------- the picker (B) ----------

  function onFronts(d) {
    var box = clear();
    var cards = d.cards || [];
    tapped = false;
    var grid = part('div', 'mc-grid' + (cards.length < 3 ? ' few' : ''), box);
    cards.forEach(function (card) {
      var tile = part('button', 'mc-tile', grid);
      tile.type = 'button';
      var thumb = part('span', 'mc-thumb', tile);
      image('', thumb).src = fresh(card.file);
      var label = part('span', 'mc-label', tile);
      part('span', 'mc-big', label).textContent = String(card.number);
      part('span', 'mc-name', label).textContent = card.name;
      tile.addEventListener('click', function () {
        if (tapped) { return; }
        tapped = true;
        move({ type: 'pick', key: card.key });
      });
    });
  }

  // ---------- the card (C, C3, C2, C4) ----------

  function onClosed(d) {
    var box = clear();
    var card = part('div', 'mc-closed', box);
    image('', card).src = fresh(d.front);
    part('div', 'mc-stock', card);
  }

  function still() {
    try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; }
  }

  function page(side, parent, shade) {
    var el = part('div', 'mc-page ' + side, parent);
    var img = image('', el);
    if (shade) { part('div', 'mc-shade', el); }
    return { el: el, img: img };
  }

  function drawSpread(d, opening) {
    var box = clear();
    var stage = part('div', 'mc-stage', box);
    var slide = part('div', 'mc-slide', stage);
    part('div', 'mc-sh-open', slide);
    part('div', 'mc-sh-closed', slide);
    var right = page('r', slide, true);
    part('div', 'mc-fold', right.el);
    part('div', 'mc-fall', slide);
    var cover = part('div', 'mc-cover', slide);
    var front = part('div', 'mc-face front', cover);
    var frontImg = image('', front);
    part('div', 'mc-dim', front);
    var back = part('div', 'mc-face back', cover);
    var left = page('l', back, true);
    part('div', 'mc-dim', back);
    spread = { id: d.id, stage: stage, front: frontImg, left: left.img, inside: right.img };
    var mine = spread;
    Promise.all([load(frontImg, fresh(d.front)), load(left.img, fresh(d.left)), load(right.img, fresh(d.inside))]).then(function () {
      if (spread !== mine) { return; }
      if (opening && !still()) {
        cover.addEventListener('animationend', function () { stage.classList.add('mc-open'); stage.classList.remove('mc-opening'); });
        stage.classList.add('mc-opening');
      } else {
        stage.classList.add('mc-open');
      }
    });
  }

  function onCard(d) {
    if (d.stage === 'closed') { onClosed(d); return; }
    if (spread && spread.id === d.id && !d.opening) {
      swap(spread.front, fresh(d.front));
      swap(spread.inside, fresh(d.inside));
    } else {
      drawSpread(d, !!d.opening);
    }
    if (d.pictures) { queuePictures(d); }
  }

  // ---------- the plain message (G) and the keepsake (A) ----------

  function onSheet(d) {
    var img = root.querySelector('.mc-sheet');
    if (img) { swap(img, fresh(d.file)); return; }
    image('mc-sheet', clear()).src = fresh(d.file);
  }

  // ---------- the last look (D2, D2b, G), the count (D3, G2), sent (F) and the address (no board) ----------

  function spoken(name) { return String(name == null ? '' : name).replace(/^my\s+/i, 'your '); }
  function whose(name) { return spoken(name) + "'s"; }

  function title(box, text) {
    var head = part('h1', 'mc-title', box);
    head.textContent = text;
    return head;
  }

  function button(cls, text, parent, tap) {
    var b = part('button', cls, parent);
    b.type = 'button';
    b.textContent = text;
    b.addEventListener('click', tap);
    return b;
  }

  // True when the picture is really in: that's what "it was shown" means to the gate.
  function arrived(img, src) {
    return new Promise(function (done) {
      img.onload = function () { done(true); };
      img.onerror = function () { done(false); };
      img.src = src;
    });
  }

  function envelope(parent, name, email) {
    var env = part('div', 'mc-env', parent);
    env.innerHTML = ENVELOPE;
    var addr = part('div', 'mc-addr', env);
    part('div', 'mc-addr-name', addr).textContent = name || '';
    if (email) { part('div', 'mc-addr-mail', addr).textContent = email; }
  }

  function lookTitle(d) { return d.kind === 'letter' ? 'Message to ' + spoken(d.name) : 'Before it goes'; }

  function drawLook(d) {
    var box = clear();
    var letter = d.kind === 'letter';
    var head = title(box, lookTitle(d));
    var main = part('div', letter ? 'mc-letter' : 'mc-look', box);
    if (!letter) { envelope(main, d.name, d.email); }
    var holder = letter ? main : part('div', 'mc-lookcard', main);
    var img = image('', holder);
    if (!letter) { part('div', 'mc-stock', holder); }
    var src = fresh(letter ? d.file : d.front);
    drawn = { look: d.look, box: box, main: main, title: head, letter: letter, src: src, extra: [] };
    return { img: img, src: src, mine: drawn };
  }

  function onLook(d) {
    if (!d || !d.look) { return; }
    endCount();
    lookData = d;
    countEnded = false;
    if (drawn && drawn.look === d.look) {     // back from a stopped count: the same picture stays up
      drawn.main.classList.remove('small');
      drawn.title.textContent = lookTitle(d);
      drawn.extra.forEach(function (el) { el.remove(); });
      drawn.extra = [];
      post({ type: 'look_up', look: d.look }).catch(log);
      return;
    }
    var now = drawLook(d);
    arrived(now.img, now.src).then(function (ok) {
      if (!ok) { log('no picture for the look'); return; }
      if (drawn !== now.mine) { return; }
      // A long message makes a tall sheet: it gets the height a keepsake gets, so its words stay full size.
      if (now.mine.letter && now.img.naturalWidth && now.img.naturalHeight / now.img.naturalWidth > 0.7) { now.mine.main.classList.add('tall'); }
      post({ type: 'look_up', look: d.look }).catch(log);
    });
  }

  function onTap(d) {
    if (!drawn || drawn.look !== d.look || count || drawn.extra.length) { return; }
    var bar = part('div', 'mc-bar', drawn.box);
    drawn.extra.push(bar);
    var once = false;
    button('mc-quiet', 'Send it', bar, function () {
      if (once) { return; }
      once = true;
      move({ type: 'tap_send' }, true);
    });
  }

  function endCount() {
    var run = count, a = window.MaryApp;
    if (!run) { return; }
    count = null;
    run.core.drop();
    clearTimeout(run.timer);
    if (a && a.watchHeard) { a.watchHeard(null); }
    if (a && a.countMic) { a.countMic.free(); }
  }

  function showDigit(run, n) {
    Object.keys(run.digits).forEach(function (key) { run.digits[key].classList.toggle('on', Number(key) === n); });
  }

  // Normal: until her "Going to" line is done, for at most LEAD_MAX.
  function herLine(a) {
    var began = Date.now();
    return new Promise(function (done) {
      (function look() {
        if (leadOver(Date.now() - began, !!(a.speaking && a.speaking()))) { done(); return; }
        setTimeout(look, LEAD_STEP);
      })();
    });
  }

  // Stopped, and nothing came back from the server to show it: the look comes back from here, and it's true, because
  // only this page can ever ask for the send.
  function stoppedHere(run, said) {
    if (count !== run) { return; }
    var d = lookData;
    endCount();
    if (d) { onLook(d); }
    if (!said) { speak({ say: SAY_STOPPED }, true); }
  }

  function sendNow(run) {
    countEnded = true;
    run.undo.remove();
    run.digits = {};
    run.line = part('div', 'mc-sentline', run.box);
    run.line.textContent = 'Sending now.';
    if (drawn) { drawn.extra.push(run.line); }
    return post({ type: 'count_done', look: run.look }).then(land, function (e) {
      log(e);
      return speak({ say: SAY_UNSURE }, true);        // nobody can know, and nothing tries again
    }).then(function () {
      if (count !== run) { return undefined; }
      endCount();                                     // nothing came back to draw
      return root ? move({ type: 'open' }) : undefined;
    });
  }

  function onCount(d) {
    if (count && count.look === d.look) { return; }
    endCount();
    countEnded = false;
    if (lookData && lookData.look === d.look && (!drawn || drawn.look !== d.look)) {
      var now = drawLook(lookData);
      now.img.src = now.src;
    }
    var box = drawn ? drawn.box : clear();
    if (drawn) {
      drawn.main.classList.add('small');
      drawn.title.textContent = drawn.letter ? lookTitle(lookData) : 'Sending';
      drawn.extra.forEach(function (el) { el.remove(); });
      drawn.extra = [];
    }
    var run = { look: d.look, box: box, core: null, digits: {}, line: null, timer: null };
    run.going = part('div', 'mc-going', box);
    run.going.textContent = 'Going to ' + whose(d.name || (lookData && lookData.name)) + ' email';
    run.undo = part('button', 'mc-undo', box);
    run.undo.type = 'button';
    part('span', '', run.undo).textContent = 'Undo';
    var stack = part('span', 'mc-count', run.undo);
    stack.setAttribute('aria-hidden', 'true');
    DIGITS.forEach(function (n) {
      var digit = part('span', 'mc-d', stack);
      digit.textContent = String(n);
      run.digits[n] = digit;
    });
    showDigit(run, DIGITS[0]);
    if (drawn) { drawn.extra.push(run.going, run.undo); }

    var a = window.MaryApp || {};
    var live = !!(a.isLive && a.isLive());
    var mic = live ? null : a.countMic;
    if (mic) { mic.hold(); }
    function wait(ms) { return new Promise(function (done) { run.timer = setTimeout(done, ms); }); }
    run.core = makeCount({
      live: live,
      lead: function () { return live ? wait(LIVE_LEAD) : herLine(a); },
      wait: wait,
      blocked: function () { return !!(a.currentScreen && a.currentScreen() === 'emergency'); },
      digit: function (n) { showDigit(run, n); },
      hush: function () { if (live && a.hushLive) { a.hushLive(); } },
      listen: function () { return mic ? mic.listen() : Promise.reject(new Error('no mic')); },
      endListen: function () { if (mic) { mic.stop(); } },
      dropListen: function () { if (mic) { mic.drop(); } },
      check: function (text) { return a.api('POST', '/api/mary/heard', { text: text }, { ms: 8000 }); },
      emergency: function (j) {
        if (a.heardEmergency) { a.heardEmergency(j); }
        endCount();
      },
      acted: land,
      stoppedHere: function (e) {
        if (e) { log(e); }
        stoppedHere(run, false);
      },
      undo: function () {
        return post({ type: 'undo' }).then(function (res) {
          var done = land(res);
          stoppedHere(run, !!(res && res.say));       // the look normally came back in land
          return done;
        });
      },
      done: function () { return sendNow(run); }
    });
    run.undo.addEventListener('click', function () { run.core.stop(); });
    count = run;
    if (live && a.watchHeard) { a.watchHeard(function (tail) { run.core.piece(tail); }); }
    run.core.start().catch(log);
  }

  function drawSent(d, src) {
    var letter = !!(lookData && lookData.kind === 'letter');
    var box = clear();
    title(box, 'Sent');
    var main = part('div', letter ? 'mc-letter small' : 'mc-look', box);
    if (src) {
      var holder = letter ? main : part('div', 'mc-lookcard', main);
      image('', holder).src = src;
      if (!letter) { part('div', 'mc-stock', holder); }
    }
    var note = part('div', 'mc-sentnote' + (letter ? ' under' : ''), letter ? box : main);
    note.insertAdjacentHTML('beforeend', CHECK);
    part('div', 'mc-sentname', note).textContent = 'Sent to ' + spoken(d.name);
    var when = part('div', 'mc-senttime', note);
    part('div', '', when).textContent = d.time || '';
    part('div', '', when).textContent = d.part || '';
  }

  function onSent(d) {
    var run = count, line = run && run.line, src = drawn && drawn.src;
    endCount();
    countEnded = true;
    if (!line) { drawSent(d, src); return; }
    run.going.remove();
    line.textContent = 'Sent to ' + spoken(d.name) + '.';
    sentTimer = setTimeout(function () { drawSent(d, src); }, SENT_HOLD);
  }

  // No board: the only way to type one. A plain text box, focused, so Windows voice typing lands in it.
  function onNeedAddress(d) {
    var box = clear();
    title(box, whose(d.name) + ' email');
    envelope(part('div', 'mc-look small alone', box), d.name, '');
    part('div', 'mc-going ask', box).textContent = d.bad ? "That didn't look right. Try again." : 'Type the email address here.';
    var field = part('input', 'mc-field', box);
    field.type = 'text';
    field.value = d.bad ? typed : '';
    field.autocomplete = 'off';
    field.spellcheck = false;
    field.maxLength = 254;
    field.setAttribute('autocapitalize', 'off');
    field.setAttribute('inputmode', 'email');
    field.setAttribute('aria-label', whose(d.name) + ' email address');
    var once = false;
    function use() {
      var address = field.value.trim();
      if (!address) { field.focus(); return; }
      if (once) { return; }
      once = true;
      typed = address;
      move({ type: 'address', address: address }, true);
    }
    field.addEventListener('keydown', function (e) {
      e.stopPropagation();
      if (e.key === 'Enter' && !e.isComposing) { use(); }
    });
    button('mc-use', 'Use this', part('div', 'mc-bar', box), use);
    try { field.focus(); } catch (e) { log(e); }
  }

  function onAddressWait(d) {
    var box = clear();
    title(box, 'Is this right?');
    part('div', 'mc-bigaddr', box).textContent = d.address || '';
    part('div', 'mc-going', box).textContent = whose(d.name) + ' email';
  }

  // ---------- jpegs for sending later ----------

  function queuePictures(d) {
    waiting = d;
    clearTimeout(waitTimer);
    waitTimer = setTimeout(runPictures, PICTURE_WAIT);
  }

  function makeJpeg(d, which) {
    return new Promise(function (done, fail) {
      var img = new Image();
      img.onerror = function () { fail(new Error('no picture ' + which)); };
      img.onload = function () {
        var size = PICTURES[which];
        var canvas = document.createElement('canvas');
        canvas.width = size[0];
        canvas.height = size[1];
        canvas.getContext('2d').drawImage(img, 0, 0, size[0], size[1]);
        function grab(quality) { return new Promise(function (got) { canvas.toBlob(got, 'image/jpeg', quality); }); }
        if (which === 'mail') { fitQuality(grab, MAIL_QUALITIES, MAIL_MAX).then(done, fail); return; }
        grab(JPEG_QUALITY).then(function (blob) {
          if (blob) { done(blob); } else { fail(new Error('no jpeg ' + which)); }
        });
      };
      img.src = url(d[which] || d.both) + '?v=' + d.rev;   // M15c: the mail picture is drawn from both
    });
  }

  function base64(blob) {
    return new Promise(function (done, fail) {
      var reader = new FileReader();
      reader.onerror = fail;
      reader.onload = function () { done(String(reader.result).split(',')[1] || ''); };
      reader.readAsDataURL(blob);
    });
  }

  function sendPieces(d, which, text, seq) {
    if (waiting) { return Promise.resolve(); }   // a newer card is waiting, so this one is out of date
    var at = seq * PIECE;
    var last = at + PIECE >= text.length;
    return post({ type: 'picture', id: d.id, rev: d.rev, part: which, seq: seq, last: last, data: text.slice(at, at + PIECE) }).then(function (res) {
      if (last) { land(res); }     // M15c: the mail picture's last piece can bring the look and her line
      if (last || !res || res.stale || res.error) { return res; }
      return pause(PIECE_GAP).then(function () { return sendPieces(d, which, text, seq + 1); });
    });
  }

  function sendPicture(d, which) {
    return makeJpeg(d, which).then(base64).then(function (text) { return sendPieces(d, which, text, 0); });
  }

  function runPictures() {
    if (running || !waiting) { return; }
    var d = waiting;
    waiting = null;
    running = true;
    var chain = Promise.resolve();
    (d.only ? [d.only] : Object.keys(PICTURES)).forEach(function (which) {
      chain = chain.then(function () { return waiting ? undefined : sendPicture(d, which); });
    });
    chain.then(function (res) {
      if (d.wanted && !waiting && (!res || res.stale || res.error)) { throw new Error('the mail picture never landed'); }
    }).catch(function (e) {
      log(e);
      if (d.wanted) { move({ type: 'picture_failed' }, true); }   // M15c: she said "One moment", so she has to answer
    }).then(function () {
      running = false;
      if (waiting) { waitTimer = setTimeout(runPictures, waiting.wanted ? 0 : PICTURE_WAIT); }
    });
  }

  // M15c: the skill is holding a send for this one picture, so it goes now.
  function onMakeMail(d) {
    waiting = { id: d.id, rev: d.rev, both: 'card-' + d.id + '-both.svg', only: 'mail', wanted: true };
    clearTimeout(waitTimer);
    runPictures();
  }

  // ---------- printing ----------

  function printFailed(e) {
    log(e);
    post({ type: 'print_failed' }).then(speak).catch(log);
  }

  function printSheet(svg) {
    return new Promise(function (done, fail) {
      var frame = document.createElement('iframe');
      frame.setAttribute('aria-hidden', 'true');
      frame.tabIndex = -1;
      frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:8.5in;height:11in;border:0;visibility:hidden';
      var timer = setTimeout(function () { frame.remove(); fail(new Error('the page never loaded')); }, PRINT_WAIT);
      frame.onload = function () {
        clearTimeout(timer);
        var win = frame.contentWindow;
        var fonts = (win.document.fonts && win.document.fonts.ready) || Promise.resolve();
        fonts.then(function () {
          win.focus();
          win.print();
          setTimeout(function () { frame.remove(); }, PRINT_KEEP);
          done();
        }).catch(fail);
      };
      frame.srcdoc = '<!doctype html><html><head><meta charset="utf-8"><style>@page{size:letter portrait;margin:0}' +
        'html,body{margin:0;padding:0;background:#fff}svg{display:block;width:8.5in;height:11in}</style></head><body>' +
        svg + '</body></html>';
      document.body.appendChild(frame);
    });
  }

  function onPrint(d) {
    fetch(url(d.file), { cache: 'no-store' }).then(function (r) {
      if (!r.ok) { throw new Error('no print sheet'); }
      return r.text();
    }).then(printSheet).catch(printFailed);
  }

  // For tests/js/m15c_screen.js: the page never uses this.
  window.MaryMessagesCount = {
    makeCount: makeCount, stopHeard: stopHeard, leadOver: leadOver, fitQuality: fitQuality, DIGITS: DIGITS, DIGIT_MS: DIGIT_MS,
    WORDS_MS: WORDS_MS, LEAD_MIN: LEAD_MIN, LEAD_MAX: LEAD_MAX, MAIL_QUALITIES: MAIL_QUALITIES, MAIL_MAX: MAIL_MAX
  };

  MarySkills.register(NAME, {
    aside: true,
    enter: function (el) {
      if (root === el && el.firstChild) { return; }   // show_screen while it's already up: leave it as it is
      root = el;
      visit++;
      shown = false;
      countEnded = false;
      // When Mary starts one by voice her own effect comes right behind show_screen, so wait a beat to look.
      var mine = visit;
      setTimeout(function () {
        if (mine === visit && !shown) { move({ type: 'open' }); }
      }, 0);
    },
    leave: function (el) {
      var ended = countEnded;
      endCount();
      clearTimeout(sentTimer);
      visit++;
      el.textContent = '';
      root = null;
      spread = null;
      drawn = null;
      lookData = null;
      countEnded = false;
      if (!ended) { post({ type: 'left' }).catch(log); }   // M15c: no look stays armed behind a screen that's gone
    },
    effect: function (kind, d) {
      try {
        if (kind === 'print') { onPrint(d); return; }
        if (kind === 'make_mail') { onMakeMail(d); return; }
        if (!root) { return; }
        shown = true;
        if (kind === 'look') { onLook(d); return; }
        if (kind === 'tap') { onTap(d); return; }
        if (kind === 'count') { onCount(d); return; }
        if (kind === 'sent') { onSent(d); return; }
        endCount();   // M15c: a failed send comes back as a card or a letter, and nothing else runs under a count
        if (kind === 'need_address') { onNeedAddress(d); }
        else if (kind === 'address_wait') { onAddressWait(d); }
        else if (kind === 'fronts') { onFronts(d); }
        else if (kind === 'card') { onCard(d); }
        else if (kind === 'letter' || kind === 'keepsake') { onSheet(d); }
      } catch (e) { log(e); }
    }
  });
})();
