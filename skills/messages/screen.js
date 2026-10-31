/* Cards and messages, the page half (M15b). Beside Mary, boards in mockups/mary/round8: the numbered fronts (B), the
   closed card (C), the card opening once (C3), the open spread (C2, C4), the plain message (G) and the keepsake (A).
   This is done by voice: the only thing to tap is a front on the picker. Everything shown is a saved picture.
   After a card is saved a small queued job turns it into jpegs for sending later. An event is 4 KB at most, so each
   jpeg goes in pieces. If that fails the svgs still stand, so it's only logged. */
(function () {
  'use strict';
  var NAME = 'messages';
  var EVENT_URL = '/api/mary/skills/' + NAME + '/event';
  var IMAGE_URL = '/api/mary/skills/' + NAME + '/image/';
  var PICTURES = { front: [740, 1036], inside: [740, 1036], both: [1480, 1036] };
  var JPEG_QUALITY = 0.92;
  var PIECE = 3000;          // base64 characters in one event; a multiple of 4
  var PICTURE_WAIT = 3000;   // after the last change, so a run of changes makes one job
  var PIECE_GAP = 15;        // so speech and the screen stay first
  var PRINT_WAIT = 15000;
  var PRINT_KEEP = 60000;

  var root = null;
  var visit = 0;
  var shown = false;
  var tapped = false;
  var spread = null;         // the open card on screen: {id, front, inside, left}
  var stamp = Date.now();    // each picture name gets a new ?v=
  var waiting = null;        // the newest card waiting for its jpegs
  var waitTimer = null;
  var running = false;

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
  function move(event) {
    var mine = visit;
    return post(event).then(function (res) {
      var effects = (mine === visit && res && res.effects) || [];
      for (var i = 0; i < effects.length; i++) { window.MarySkills.apply(effects[i]); }
      if (mine === visit) { speak(res); }
    }).catch(log);
  }

  // Her line after a tap, unless she or the resident is in the middle of something. The screen note still tells her.
  function speak(res) {
    var a = window.MaryApp, text = res && res.say;
    if (!text || !a || !a.say) { return; }
    try {
      if (a.busy && a.busy()) { return; }
      var p = a.say(text);
      if (p && p.catch) { p.catch(log); }
    } catch (e) { log(e); }
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
        canvas.toBlob(function (blob) {
          if (blob) { done(blob); } else { fail(new Error('no jpeg ' + which)); }
        }, 'image/jpeg', JPEG_QUALITY);
      };
      img.src = url(d[which]) + '?v=' + d.rev;
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
      if (last || !res || res.stale || res.error) { return undefined; }
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
    Object.keys(PICTURES).forEach(function (which) {
      chain = chain.then(function () { return waiting ? undefined : sendPicture(d, which); });
    });
    chain.catch(log).then(function () {
      running = false;
      if (waiting) { waitTimer = setTimeout(runPictures, PICTURE_WAIT); }
    });
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

  MarySkills.register(NAME, {
    aside: true,
    enter: function (el) {
      if (root === el && el.firstChild) { return; }   // show_screen while it's already up: leave it as it is
      root = el;
      visit++;
      shown = false;
      // When Mary starts one by voice her own effect comes right behind show_screen, so wait a beat to look.
      var mine = visit;
      setTimeout(function () {
        if (mine === visit && !shown) { move({ type: 'open' }); }
      }, 0);
    },
    leave: function (el) {
      visit++;
      el.textContent = '';
      root = null;
      spread = null;
    },
    effect: function (kind, d) {
      try {
        if (kind === 'print') { onPrint(d); return; }
        if (!root) { return; }
        shown = true;
        if (kind === 'fronts') { onFronts(d); }
        else if (kind === 'card') { onCard(d); }
        else if (kind === 'letter' || kind === 'keepsake') { onSheet(d); }
      } catch (e) { log(e); }
    }
  });
})();
