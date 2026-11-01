/* T1: Andy's test list, a drawer down the left edge of Mary's page. Only server.py's injection brings this in.
   It talks to /api/mary/testlist* and nothing else: no mic, no sound, no Gemini, no log, no memories. */
(function () {
  'use strict';

  var API = '/api/mary/testlist';
  var D = document;
  var W = window;
  var scr = D.getElementById('scr');
  if (!scr || D.getElementById('tl-root')) { return; }

  var SHIELDED = ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'touchstart', 'touchend', 'keydown', 'keyup'];

  var list = null;          // what the server sent, with the page's own state on each item
  var open = true;          // opens at start on every load; nothing is stored
  var scale = 1;
  var unfolded = {};        // sections tapped open, by position, until reload
  var held = null;          // the section he last marked in stays open, so the Note box is still there after "Didn't"
  var shownNow = null;      // the highlighted item last brought into view
  var armed = null;         // the Start over timer while it reads "Are you sure?"
  var queue = Promise.resolve();   // saves go out one at a time, in the order they were made

  function make(tag, cls, text) {
    var el = D.createElement(tag);
    if (cls) { el.className = cls; }
    if (text !== undefined) { el.textContent = text; }
    return el;
  }
  function button(cls, text, onTap) {
    var b = make('button', cls, text);
    b.type = 'button';
    b.addEventListener('click', onTap);
    return b;
  }

  var root = make('aside');
  root.id = 'tl-root';
  root.setAttribute('aria-label', 'Test list');
  var tab = button('tl-tab', 'Test list', function () { setOpen(true); });
  var panel = make('div', 'tl-panel');
  var head = make('div', 'tl-head');
  var titleEl = make('h1', 'tl-title', 'Test list');
  var hide = button('tl-hide', 'Hide', function () { setOpen(false); });
  var msg = make('p', 'tl-msg');
  msg.setAttribute('role', 'alert');
  msg.hidden = true;
  var scroller = make('div', 'tl-scroll');
  var body = make('div');
  var over = button('tl-over', 'Start over', startOver);

  head.appendChild(titleEl);
  head.appendChild(hide);
  scroller.appendChild(body);
  scroller.appendChild(over);
  panel.appendChild(head);
  panel.appendChild(msg);
  panel.appendChild(scroller);
  root.appendChild(tab);
  root.appendChild(panel);
  D.body.appendChild(root);

  // Mary's page listens on document in the capture phase: a tap would close her menu (app.js onUiTouch) or wake
  // her with a spoken hello (firstrun.js onAct). Window capture runs first, so those never hear the drawer.
  // Never preventDefault: typing and clicks still have to work.
  function shield(ev) {
    if (ev.target instanceof Node && root.contains(ev.target)) { ev.stopPropagation(); }
  }
  SHIELDED.forEach(function (type) {
    W.addEventListener(type, shield, { capture: true, passive: true });
  });
  root.addEventListener('click', function (ev) { ev.stopPropagation(); });   // live.js listens for clicks on document

  // The face makes room on every screen: all of Mary's page lives in #scr, and her CSS is built on vw, so #scr
  // keeps its size and is scaled as a whole beside the column. Right edge fixed, so Menu stays in its corner.
  function fit() {
    var w = W.innerWidth;
    scale = Math.max(0.1, (w - root.offsetWidth) / w);
    scr.style.transformOrigin = '100% 50%';
    scr.style.transform = 'scale(' + scale + ')';
  }
  W.addEventListener('resize', fit);

  // captions.js:303 measures words with getBoundingClientRect (scaled) and compares them with clientWidth
  // (unscaled, :287), so under scale its lines would run over. Inside .cap only, report the unscaled size.
  var realRect = Element.prototype.getBoundingClientRect;
  Element.prototype.getBoundingClientRect = function () {
    var r = realRect.call(this);
    if (scale === 1 || !this.closest('.cap')) { return r; }
    return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, x: r.x, y: r.y,
             width: r.width / scale, height: r.height / scale };
  };

  function setOpen(on) {
    open = on;
    root.classList.toggle('tl-open', on);
    tab.hidden = on;
    panel.hidden = !on;
    fit();
    if (on) { growAll(); keepInView(); }
  }

  function say(text) {
    msg.textContent = text || '';
    msg.hidden = !text;
  }

  function allItems() {
    var all = [];
    if (list) { list.sections.forEach(function (s) { all = all.concat(s.items); }); }
    return all;
  }

  function firstUnmarked() {
    return allItems().filter(function (i) { return !i.mark; })[0] || null;
  }

  function keepInView() {
    var now = body.querySelector('.tl-now');
    if (now) { now.scrollIntoView({ block: 'nearest' }); }
  }

  // ---- saving
  function post(path, data, keepalive) {
    return fetch(API + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Tracker': '1' },
      body: JSON.stringify(data),
      keepalive: !!keepalive
    }).then(function (r) {
      if (!r.ok) { throw new Error('save failed'); }
      return r.json();
    });
  }

  function payload(item) {
    return { section: item.section, item: item.text, mark: item.mark, note: item.note };
  }

  function cancelTimer(item) {
    clearTimeout(item.timer);
    item.timer = null;
  }

  function save(item, undo) {
    var sent = payload(item);
    cancelTimer(item);
    item.dirty = true;
    queue = queue.then(function () { return post('/mark', sent); }).then(function (saved) {
      say('');
      item.time = saved.time;
      if (item.note === sent.note && item.mark === sent.mark) { item.dirty = false; }
    }, function () {
      say("Couldn't save that. Try again.");
      if (undo) { undo(); }
    });
  }

  function setMark(item, value) {
    var before = item.mark;
    var after = before === value ? null : value;
    item.mark = after;
    held = item.at;
    render();
    save(item, function () {
      if (item.mark === after) { item.mark = before; render(); }
    });
  }

  function grow(area) {   // a long spoken note stays readable; the list keeps its place while the box is measured
    var top = scroller.scrollTop;
    area.style.height = 'auto';
    area.style.height = (area.scrollHeight + 6) + 'px';   // 6: its border, top and bottom
    scroller.scrollTop = top;
  }

  function growAll() {
    body.querySelectorAll('textarea').forEach(function (area) { if (area.value) { grow(area); } });
  }

  W.addEventListener('pagehide', function () {
    allItems().forEach(function (item) {
      if (item.dirty) {
        cancelTimer(item);
        post('/mark', payload(item), true).catch(function () {});
      }
    });
  });

  // ---- drawing
  function drawItem(item, now) {
    var box = make('div', 'tl-item' + (item === now ? ' tl-now' : ''));
    box.appendChild(make('p', 'tl-text', item.text));
    var marks = make('div', 'tl-marks');
    [['worked', 'Worked', 'tl-worked'], ['didnt', "Didn't", 'tl-didnt']].forEach(function (m) {
      var b = button(m[2], m[1], function () { setMark(item, m[0]); });
      b.setAttribute('aria-pressed', item.mark === m[0] ? 'true' : 'false');
      b.setAttribute('data-tl', item.id + '-' + m[0]);
      marks.appendChild(b);
    });
    box.appendChild(marks);
    var label = make('label', 'tl-note', 'Note');
    var area = make('textarea');
    area.rows = 1;
    area.maxLength = 4000;
    area.value = item.note;
    area.setAttribute('data-tl', item.id + '-note');
    area.addEventListener('input', function () {
      item.note = area.value;
      item.dirty = true;
      cancelTimer(item);
      item.timer = setTimeout(function () { save(item); }, 500);
      grow(area);
    });
    area.addEventListener('blur', function () { if (item.dirty) { save(item); } });
    label.appendChild(area);
    box.appendChild(label);
    return box;
  }

  function foldText(section) {
    var marked = section.items.length;
    var bad = section.items.filter(function (i) { return i.mark === 'didnt'; }).length;
    return (section.name || 'List') + ': ' + marked + ' of ' + marked + ' done' +
      (bad ? ', ' + bad + " didn't work" : '');
  }

  function drawSection(section, at, now) {
    var box = make('section', 'tl-section');
    var done = section.items.length > 0 && section.items.every(function (i) { return i.mark; });
    if (done && !unfolded[at] && at !== held) {
      var fold = button('tl-fold', foldText(section), function () { unfolded[at] = true; render(); });
      fold.setAttribute('data-tl', 'fold-' + at);
      box.appendChild(fold);
      return box;
    }
    if (section.name) { box.appendChild(make('h2', 'tl-name', section.name)); }
    section.entries.forEach(function (entry) {
      box.appendChild(entry.type === 'item' ? drawItem(entry, now) : make('p', 'tl-line', entry.text));
    });
    return box;
  }

  function render() {
    var active = root.contains(D.activeElement) ? D.activeElement : null;
    var key = active && active.getAttribute('data-tl');
    var from = active && active.tagName === 'TEXTAREA' ? active.selectionStart : null;
    var now = firstUnmarked();
    body.textContent = '';
    list.sections.forEach(function (section, at) { body.appendChild(drawSection(section, at, now)); });
    growAll();
    var again = key && body.querySelector('[data-tl="' + key + '"]');
    if (again) {
      again.focus({ preventScroll: true });
      if (from !== null) { again.setSelectionRange(from, from); }
    }
    // Only when the highlight moves, so going back to change an earlier mark doesn't jump the list away.
    if (now !== shownNow) {
      shownNow = now;
      keepInView();
    }
  }

  function load() {
    return fetch(API).then(function (r) {
      if (!r.ok) { throw new Error('no list'); }
      return r.json();
    }).then(function (fresh) {
      fresh.sections.forEach(function (s, at) {
        s.items = s.entries.filter(function (e) { return e.type === 'item'; });   // one object per item, marks and all
        s.items.forEach(function (item) { item.section = s.name; item.at = at; });
      });
      list = fresh;
      held = null;
      shownNow = null;
      titleEl.textContent = fresh.title;
      render();
    });
  }

  // ---- Start over: one tap asks, the second clears
  function disarm() {
    clearTimeout(armed);
    armed = null;
    over.textContent = 'Start over';
  }

  function startOver() {
    if (!armed) {
      over.textContent = 'Are you sure?';
      armed = setTimeout(disarm, 6000);
      return;
    }
    disarm();
    allItems().forEach(function (item) { cancelTimer(item); item.dirty = false; });
    queue = queue.then(function () { return post('/reset', {}); }).then(function () {
      say('');
      unfolded = {};
      return load();
    }).catch(function () {
      say("Couldn't save that. Try again.");
    });
  }

  setOpen(true);
  load().catch(function () { say("Couldn't load the list."); });
}());
