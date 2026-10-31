/* The word search skill, the page half: the theme, the grid, the word list and the big buttons, side by side with Mary.
   All real state lives on the server (skill.py). It sends a "puzzle" effect with everything to draw, then "found",
   "shown", "hint" and "done" as things change, whether the move came by touch or by voice.
   Taps go to POST /api/mary/skills/word_search/event {"event": {"type": "open"|"line"|"hint"|"new"|"close", ...}}.
   Tapping works two ways on one path: tap the first letter and then the last, or tap the letters in a row. The first
   tap only rings the letter. Each later one asks the server about the line from the first letter to this one.
   Hands shake, so a tap is the cell where the finger came down, wherever it lifts, and there is no drag or long press.
   A wrong line clears quietly: no buzz, no red, no "wrong". No timers, scores, sounds or confetti. */
(function () {
  'use strict';
  var D = document;
  var NAME = 'word_search';
  var EVENT_URL = '/api/mary/skills/' + NAME + '/event';
  var VIEW_URL = '/api/mary/skills/' + NAME + '/view';
  var NOTE_START = 'What is on the screen now: ';
  var BOUNCE_MS = 300;      // the same letter again this soon is a shaky hand, not a second tap
  var CLICK_GAP_MS = 700;   // a click this soon after a tap is that tap's own click, already counted
  var SVG_NS = 'http://www.w3.org/2000/svg';

  var root = null;      // the .skill-body while the screen is up
  var data = null;      // the puzzle: the last "puzzle" effect plus what has happened since
  var gridEl = null;    // the grid while it is drawn
  var btns = [];        // btns[row][column]: the letter buttons
  var visit = 0;        // goes up on every enter and leave, so a late reply can't touch a newer visit
  var failed = false;   // no puzzle came back from the server
  var opening = false;  // an "open" is on its way
  var pick = null;      // the letters picked so far: {from, to, cells}
  var sending = false;  // a line is on its way to the server
  var queue = [];       // taps that came in while one was on its way
  var chooser = false;  // the bar shows Bigger letters, Same, More letters during play
  var barBusy = false;  // a button's tap is on its way
  var down = null;      // the finger that is down: {id, r, c}
  var tappedAt = 0;     // when the last pointer tap was taken
  var lastCell = null;  // the last letter tapped, for BOUNCE_MS
  var lastCellAt = 0;

  function log(e) { try { console.log('[word_search]', e); } catch (x) { /* nothing */ } }
  function app() { return window.MaryApp; }

  function make(tag, cls, text) {
    var el = D.createElement(tag);
    if (cls) { el.className = cls; }
    if (text) { el.textContent = text; }
    return el;
  }

  function find(cls) { return root ? root.querySelector('.' + cls) : null; }

  function who() {
    try { return (app() && app().companionName && app().companionName()) || 'Mary'; } catch (e) { log(e); return 'Mary'; }
  }

  function sameCell(a, b) { return !!a && !!b && a[0] === b[0] && a[1] === b[1]; }

  function wordsLeft() { return data.words.length - data.found.length - data.shown.length; }

  // For screen readers: the polite status line.
  function status(text) {
    var s = find('ws-status');
    if (s) { s.textContent = text; }
  }

  // Her line for a move, unless she or the resident is in the middle of something. The screen note still tells her.
  function speak(res) {
    var a = app(), text = res && res.say;
    if (!text || !root || !a || !a.say) { return; }
    try {
      if (a.busy && a.busy()) { return; }
      var p = a.say(text);
      if (p && p.catch) { p.catch(log); }
    } catch (e) { log(e); }
  }

  // Tells the server about a move and applies its effects. Resolves with the reply, or null when it failed.
  function send(event) {
    var mine = visit;
    var init = { method: 'POST', cache: 'no-store', headers: { 'X-Tracker': '1', 'Content-Type': 'application/json' },
      body: JSON.stringify({ event: event }) };
    return fetch(EVENT_URL, init).then(function (r) { return r.json(); }).then(function (res) {
      var effects = (mine === visit && res && res.effects) || [];
      for (var i = 0; i < effects.length; i++) {
        if (window.MarySkills && window.MarySkills.apply) { window.MarySkills.apply(effects[i]); }
      }
      return res;
    }).catch(function (e) { log(e); return null; });
  }

  // The action's own answer: the core may wrap it in "response".
  function answer(res) { return (res && res.response) || res || {}; }

  // After a word found by touch: a silent note for Live, then her line, so the note never lands on top of her words.
  function tellHer(res) {
    fetch(VIEW_URL, { cache: 'no-store', headers: { 'X-Tracker': '1' } }).then(function (r) { return r.json(); }).then(function (v) {
      var a = app();
      if (v && v.text && a && a.screenNote) { a.screenNote(NOTE_START + v.text); }
    }).catch(log).then(function () { speak(res); });
  }

  // ----- picking letters -----

  function lineCells(a, b) {
    var dr = b[0] - a[0], dc = b[1] - a[1], span = Math.max(Math.abs(dr), Math.abs(dc)), out = [];
    var stepR = (dr > 0) - (dr < 0), stepC = (dc > 0) - (dc < 0);
    for (var i = 0; i <= span; i++) { out.push([a[0] + stepR * i, a[1] + stepC * i]); }
    return out;
  }

  function ring(on) {
    if (!pick) { return; }
    pick.cells.forEach(function (cell) {
      var b = btns[cell[0]] && btns[cell[0]][cell[1]];
      if (b) { b.classList.toggle('picked', on); }
    });
  }

  function clearPick() {
    ring(false);
    pick = null;
  }

  function setPick(from, to) {
    ring(false);
    pick = { from: from, to: to, cells: lineCells(from, to) };
    ring(true);
  }

  function sendLine(to) {
    var from = pick.from, mine = visit;
    sending = true;
    send({ type: 'line', from: from, to: to }).then(function (res) {
      sending = false;
      if (mine !== visit) { return; }
      var a = answer(res);
      if (a.found) {
        clearPick();
        tellHer(res);
      } else {
        if (a.partial && pick && pick.from === from) { setPick(from, to); } else { clearPick(); }
        speak(res);
      }
      drainTaps();
    });
  }

  function step(cell) {
    if (!pick) {
      setPick(cell, cell);
      status('Letter ' + String(data.grid[cell[0]][cell[1]]) + ' picked.');
    } else if (pick.cells.some(function (c) { return sameCell(c, cell); })) {
      clearPick();    // the same letter again clears it
      status('Nothing picked.');
    } else {
      sendLine(cell);
    }
  }

  function drainTaps() {
    while (!sending && queue.length && data && !data.finished) { step(queue.shift()); }
  }

  // The one way in for every tap: pointer, keyboard and screen reader.
  function tap(r, c) {
    if (!data || data.finished) { return; }
    var cell = [r, c], now = Date.now();
    if (sameCell(cell, lastCell) && now - lastCellAt < BOUNCE_MS) { return; }
    lastCell = cell;
    lastCellAt = now;
    if (sending) { queue.push(cell); return; }
    step(cell);
  }

  // The nearest letter to where the finger came down. The whole grid is the target, so there are no gaps to miss.
  function cellAt(ev) {
    var box = gridEl.getBoundingClientRect(), n = data.size;
    var r = Math.floor((ev.clientY - box.top) / box.height * n);
    var c = Math.floor((ev.clientX - box.left) / box.width * n);
    return [Math.min(n - 1, Math.max(0, r)), Math.min(n - 1, Math.max(0, c))];
  }

  function listen(grid) {
    grid.addEventListener('pointerdown', function (ev) {
      if (down || !data || (ev.pointerType === 'mouse' && ev.button !== 0)) { return; }
      var cell = cellAt(ev);
      down = { id: ev.pointerId, r: cell[0], c: cell[1] };
      try { grid.setPointerCapture(ev.pointerId); } catch (e) { log(e); }
    });
    grid.addEventListener('pointerup', function (ev) {
      if (!down || ev.pointerId !== down.id) { return; }
      var d = down;
      down = null;
      tappedAt = Date.now();
      tap(d.r, d.c);
    });
    grid.addEventListener('pointercancel', function () { down = null; });
    grid.addEventListener('contextmenu', function (ev) { ev.preventDefault(); });   // a slow press is still a tap
    grid.addEventListener('click', function (ev) {     // keyboards and screen readers click with no pointer first
      if (Date.now() - tappedAt < CLICK_GAP_MS) { return; }
      var b = ev.target && ev.target.closest ? ev.target.closest('.ws-c') : null;
      if (b) { tap(Number(b.getAttribute('data-r')), Number(b.getAttribute('data-c'))); }
    });
  }

  // ----- drawing -----

  // A capsule behind a word's letters. It starts from the left end (the top one when upright), whichever way it reads.
  function addMark(cells, fresh) {
    if (!gridEl) { return; }
    var a = cells[0], b = cells[cells.length - 1];
    if (b[1] < a[1] || (b[1] === a[1] && b[0] < a[0])) { var t = a; a = b; b = t; }
    var dr = b[0] - a[0], dc = b[1] - a[1];
    var way = dr === 0 ? 'h' : (dc === 0 ? 'v' : 'd');
    var mark = make('span', 'ws-mark ' + way + (fresh ? ' fresh' : ''));
    mark.style.setProperty('--r', a[0]);
    mark.style.setProperty('--c', a[1]);
    mark.style.setProperty('--n', cells.length);
    if (way === 'd') { mark.style.setProperty('--a', dr > 0 ? '45deg' : '-45deg'); }
    gridEl.appendChild(mark);
    cells.forEach(function (cell) {
      var letter = btns[cell[0]] && btns[cell[0]][cell[1]];
      if (letter) { letter.classList.add('on'); }
    });
  }

  function crossOff(word, kind) {
    var rows = root ? root.querySelectorAll('.ws-word') : [];
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].getAttribute('data-word') !== word) { continue; }
      rows[i].classList.add('found');
      if (kind === 'shown') { rows[i].classList.add('shown'); }
      rows[i].querySelector('.vh').textContent = kind === 'shown' ? ', shown by ' + who() : ', found';
    }
  }

  // Step 1 is a pale gold band; step 2 adds the solid gold first letter. A slanted word's band is the row it starts in.
  function drawHint() {
    if (!gridEl) { return; }
    var oldBand = gridEl.querySelector('.ws-band');
    if (oldBand) { oldBand.parentNode.removeChild(oldBand); }
    var lit = gridEl.querySelector('.ws-c.lit');
    if (lit) { lit.classList.remove('lit'); }
    var h = data.hint;
    if (!h || !h.line) { return; }
    var band = make('span', 'ws-band');
    if (h.line.kind === 'column') {
      band.classList.add('col');
      band.style.setProperty('--c', h.line.index);
    } else {
      band.style.setProperty('--r', h.line.index);
    }
    gridEl.appendChild(band);
    if (h.step >= 2 && h.cell && btns[h.cell[0]] && btns[h.cell[0]][h.cell[1]]) {
      btns[h.cell[0]][h.cell[1]].classList.add('lit');
    }
  }

  function drawTitle() {
    var t = find('ws-title');
    if (!t) { return; }
    t.textContent = '';
    t.appendChild(make('span', 'ws-theme', data.theme));
    if (data.finished) { t.appendChild(make('span', '', 'That\'s all of them.')); }
    t.classList.toggle('done', !!data.finished);
  }

  function buildGrid() {
    var n = data.size, grid = make('div', 'ws-grid');
    grid.setAttribute('role', 'group');
    grid.setAttribute('aria-label', 'Word search puzzle, ' + n + ' letters by ' + n);
    btns = [];
    for (var r = 0; r < n; r++) {
      var row = [];
      for (var c = 0; c < n; c++) {
        var letter = String(data.grid[r][c] || '');
        var b = make('button', 'ws-c', letter);
        b.type = 'button';
        b.setAttribute('aria-label', 'row ' + (r + 1) + ', column ' + (c + 1) + ', letter ' + letter);
        b.setAttribute('data-r', String(r));
        b.setAttribute('data-c', String(c));
        grid.appendChild(b);
        row.push(b);
      }
      btns.push(row);
    }
    listen(grid);
    return grid;
  }

  function checkMark() {
    var svg = D.createElementNS(SVG_NS, 'svg');
    var attrs = { viewBox: '0 0 24 24', 'aria-hidden': 'true', fill: 'none', stroke: 'currentColor', 'stroke-width': '4',
      'stroke-linecap': 'round', 'stroke-linejoin': 'round' };
    Object.keys(attrs).forEach(function (k) { svg.setAttribute(k, attrs[k]); });
    var path = D.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', 'M4 13l5 5L20 6');
    svg.appendChild(path);
    return svg;
  }

  function buildList() {
    var list = make('ul', 'ws-list');
    list.setAttribute('aria-label', 'Words to find');
    data.words.forEach(function (word) {
      var li = make('li', 'ws-word');
      li.setAttribute('data-word', word);
      li.appendChild(checkMark());
      li.appendChild(make('span', 'ws-w', word));
      li.appendChild(make('span', 'vh'));     // ", found" for screen readers
      list.appendChild(li);
    });
    return list;
  }

  function barButton(cls, text, onTap) {
    var b = make('button', 'ans' + (cls ? ' ' + cls : ''), text);
    b.type = 'button';
    b.addEventListener('click', onTap);
    return b;
  }

  function drawBar() {
    var old = find('ws-bar');
    if (!old) { return; }
    var hadFocus = old.contains(D.activeElement);
    var bar = make('div', 'ws-bar');
    if (data.finished || chooser) {
      bar.classList.add('four');
      bar.appendChild(barButton('', 'Bigger letters', function () { choose('easier'); }));
      bar.appendChild(barButton('yes', 'Same', function () { choose('same'); }));
      bar.appendChild(barButton('', 'More letters', function () { choose('harder'); }));
      if (data.finished) {
        bar.appendChild(barButton('', 'Back to ' + who(), goBack));
      } else {
        bar.appendChild(barButton('', 'Back', function () { chooser = false; drawBar(); }));
      }
    } else {
      bar.appendChild(barButton('yes', 'Give me a hint', askHint));
      bar.appendChild(barButton('', 'New puzzle', function () { chooser = true; drawBar(); }));
      bar.appendChild(barButton('', 'Back to ' + who(), goBack));
    }
    old.parentNode.replaceChild(bar, old);
    if (hadFocus) { bar.firstChild.focus(); }
  }

  function statusLine() {
    var s = make('p', 'vh ws-status');
    s.setAttribute('aria-live', 'polite');
    return s;
  }

  // Before a puzzle is up, and when none could be had: the title row stays, so nothing sits under the Menu button.
  function drawWait() {
    var ws = make('div', 'ws');
    ws.appendChild(make('div', 'ws-title'));
    if (failed) { ws.appendChild(make('p', 'ws-wait', 'The puzzle isn\'t ready yet.')); }
    var bar = make('div', 'ws-bar');
    if (failed) { bar.appendChild(barButton('yes', 'Try again', openPuzzle)); }
    bar.appendChild(barButton('', 'Back to ' + who(), goBack));
    ws.appendChild(bar);
    ws.appendChild(statusLine());
    root.appendChild(ws);
  }

  function draw() {
    if (!root) { return; }
    root.textContent = '';
    gridEl = null;
    btns = [];
    down = null;
    if (!data) { drawWait(); return; }

    var longest = data.words.reduce(function (most, w) { return Math.max(most, w.length); }, 7);
    var ws = make('div', data.size === 8 ? 'ws big' : 'ws');
    ws.style.setProperty('--size', data.size);
    ws.style.setProperty('--rows', Math.max(data.size, data.words.length));
    ws.style.setProperty('--chars', longest);
    ws.appendChild(make('h2', 'ws-title'));
    gridEl = buildGrid();
    ws.appendChild(gridEl);
    ws.appendChild(buildList());
    ws.appendChild(make('div', 'ws-bar'));
    ws.appendChild(statusLine());
    root.appendChild(ws);

    drawTitle();
    drawBar();
    data.found.forEach(function (f) { addMark(f.cells, false); crossOff(f.word, 'found'); });
    data.shown.forEach(function (f) { addMark(f.cells, false); crossOff(f.word, 'shown'); });
    drawHint();
  }

  // ----- the buttons -----

  function askHint() {
    if (barBusy) { return; }
    barBusy = true;
    send({ type: 'hint' }).then(function (res) {
      barBusy = false;
      speak(res);
    });
  }

  // Bigger letters, Same or More letters. A choice always returns to the usual bar; a new puzzle redraws everything anyway.
  function choose(level) {
    if (barBusy) { return; }
    barBusy = true;
    send({ type: 'new', level: level }).then(function (res) {
      barBusy = false;
      if (chooser) {
        chooser = false;
        if (root && data) { drawBar(); }
      }
      speak(res);
    });
  }

  function goBack() {
    if (barBusy) { return; }
    barBusy = true;
    send({ type: 'close' }).then(function () {
      barBusy = false;
      // offline the core refuses this skill's calls; go back to Mary's face anyway
      if (app() && app().currentScreen && app().currentScreen() === NAME) { app().show('everyday'); }
    });
  }

  function openPuzzle() {
    if (opening) { return; }
    opening = true;
    failed = false;
    var mine = visit;
    send({ type: 'open' }).then(function (res) {
      if (mine !== visit) { return; }
      opening = false;
      if (!data) {
        failed = true;
        draw();
      }
      speak(res);
    });
  }

  // ----- what the server sends -----

  function onPuzzle(d) {
    if (!d || !d.grid || !d.grid.length || !d.words) { return; }
    data = { grid: d.grid, words: d.words.map(String), theme: String(d.theme || ''), size: d.grid.length,
      found: (d.found || []).slice(), shown: (d.shown || []).slice(), hint: d.hint || null, finished: !!d.finished };
    pick = null;
    queue = [];
    chooser = false;
    failed = false;
    draw();
    if (root && !data.finished) { status('Word search on ' + data.theme + '. ' + wordsLeft() + ' words to find.'); }
  }

  function onMark(kind, d) {
    if (!data || !d || !d.word || !d.cells || !d.cells.length) { return; }
    var word = String(d.word);
    var known = data.found.concat(data.shown).some(function (f) { return f.word === word; });
    if (known) { return; }
    data[kind].push({ word: word, cells: d.cells });
    addMark(d.cells, true);
    crossOff(word, kind);
    if (data.hint && data.hint.word === word) {   // only the hint on this very word goes
      data.hint = null;
      drawHint();
    }
    status(word + (kind === 'shown' ? ' shown. ' : ' found. ') + wordsLeft() + ' left.');
  }

  function onHint(d) {
    if (!data || !d || !d.line) { return; }
    data.hint = d;
    drawHint();
  }

  function onDone() {
    if (!data) { return; }
    data.finished = true;
    data.hint = null;
    chooser = false;
    queue = [];
    clearPick();
    drawHint();
    drawTitle();
    drawBar();
    status('That\'s all of them.');
  }

  MarySkills.register(NAME, {
    aside: true,
    enter: function (el) {
      root = el;
      visit++;
      failed = false;
      opening = false;
      sending = false;
      barBusy = false;
      pick = null;
      queue = [];
      chooser = false;
      draw();
      // When Mary starts one by voice, her "puzzle" effect comes right behind show_screen, so wait a beat to look.
      var mine = visit;
      setTimeout(function () {
        if (mine === visit && !data) { openPuzzle(); }
      }, 0);
    },
    leave: function (el) {
      visit++;
      el.textContent = '';
      root = null;
      data = null;
      gridEl = null;
      btns = [];
      pick = null;
      queue = [];
      down = null;
    },
    effect: function (kind, d) {
      try {
        if (kind === 'puzzle') { onPuzzle(d); }
        else if (kind === 'found' || kind === 'shown') { onMark(kind, d); }
        else if (kind === 'hint') { onHint(d); }
        else if (kind === 'done') { onDone(); }
      } catch (e) { log(e); }
    }
  });
})();
