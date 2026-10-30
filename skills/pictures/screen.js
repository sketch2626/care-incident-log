/* The pictures skill, the page half: one big picture with its title and credit, "Another picture" and "Back to Mary".
   The server finds the picture (skill.py) and sends a "picture" effect {src, title, credit}; all real state lives there.
   Taps go to POST /api/mary/skills/pictures/event {"event": {"type": "next"|"close"}}.
   While this screen is up, screen.css moves Mary's face (#face) small into the top-left corner so she keeps talking. */
(function () {
  'use strict';
  var D = document;
  var EVENT_URL = '/api/mary/skills/pictures/event';
  var last = null;     // the last picture effect's data, so enter() can draw it again
  var fresh = false;   // true when `last` came in while this screen was up (not left over from an earlier visit)
  var root = null;     // the .skill-body while the screen is up
  var busy = false;    // a tap is on its way to the server

  function log(e) { try { console.log('[pictures]', e); } catch (x) { /* nothing */ } }
  function app() { return window.MaryApp; }

  function make(tag, cls, text) {
    var el = D.createElement(tag);
    if (cls) { el.className = cls; }
    if (text) { el.textContent = text; }
    return el;
  }

  function bigButton(cls, text, onTap) {
    var b = make('button', 'btn big ' + cls, text);
    b.type = 'button';
    b.addEventListener('click', onTap);
    return b;
  }

  function find(cls) { return root ? root.querySelector('.' + cls) : null; }

  function setStatus(text) {
    var s = find('pic-status');
    if (!s) { return; }
    s.textContent = text || '';
    s.hidden = !text;
  }

  // Tells the server about a tap; applies its effects and lets Mary say its line. Resolves with the reply or null.
  function send(type) {
    var init = { method: 'POST', cache: 'no-store', headers: { 'X-Tracker': '1', 'Content-Type': 'application/json' },
      body: JSON.stringify({ event: { type: type } }) };
    return fetch(EVENT_URL, init).then(function (r) { return r.json(); }).then(function (res) {
      var effects = (res && res.effects) || [];
      for (var i = 0; i < effects.length; i++) {
        if (window.MarySkills && window.MarySkills.apply) { window.MarySkills.apply(effects[i]); }
      }
      if (res && res.say && app() && app().say) {
        try { app().say(res.say); } catch (e) { log(e); }
      }
      return res;
    }).catch(function (e) { log(e); return null; });
  }

  function goBack() {
    if (busy) { return; }
    busy = true;
    send('close').then(function () {
      busy = false;
      // offline the core refuses this skill's calls; go back to Mary's face anyway
      if (app() && app().currentScreen && app().currentScreen() === 'pictures') { app().show('everyday'); }
    });
  }

  function another() {
    if (busy) { return; }
    busy = true;
    var b = find('pic-next');
    if (b) { b.disabled = true; }
    setStatus('Finding your picture…');
    var before = last;
    send('next').then(function (res) {
      busy = false;
      if (last !== before) { return; }   // a new picture came in and was drawn already
      var nb = find('pic-next');
      if (nb) { nb.disabled = false; }
      var img = find('pic-img');
      if (img && img.complete && img.naturalWidth) { setStatus(''); }
      if (!res || res.error) { setStatus('I couldn’t get another picture.'); }
    });
  }

  // Shown when there is no picture: what to say to get one.
  function drawEmpty() {
    var who = 'Mary';
    try { who = (app() && app().companionName && app().companionName()) || 'Mary'; } catch (e) { log(e); }
    var bar = make('div', 'pic-bar');
    bar.appendChild(bigButton('pic-back', 'Back to ' + who, goBack));
    root.appendChild(bar);
    var stage = make('div', 'pic-stage');
    var s = make('p', 'pic-status', 'Ask ' + who + ' for a picture of anything you like.');
    s.setAttribute('aria-live', 'polite');
    stage.appendChild(s);
    root.appendChild(stage);
  }

  function draw() {
    if (!root) { return; }
    root.innerHTML = '';
    if (!last || !last.src) { drawEmpty(); return; }
    var who = 'Mary';
    try { who = (app() && app().companionName && app().companionName()) || 'Mary'; } catch (e) { log(e); }
    var data = last;

    var bar = make('div', 'pic-bar');
    bar.appendChild(bigButton('pic-back', 'Back to ' + who, goBack));
    bar.appendChild(bigButton('pic-next yes', 'Another picture', another));
    root.appendChild(bar);

    var stage = make('div', 'pic-stage');
    var status = make('p', 'pic-status', 'Finding your picture…');
    status.setAttribute('aria-live', 'polite');
    var img = make('img', 'pic-img');
    img.alt = data.title || 'A picture';
    img.hidden = true;
    img.addEventListener('load', function () {
      if (last !== data) { return; }
      img.hidden = false;
      setStatus('');
    });
    img.addEventListener('error', function () {
      if (last !== data) { return; }
      if (!fresh) { last = null; draw(); return; }   // left over from an earlier visit: the server put it away
      img.hidden = true;
      var nb = find('pic-next');
      if (nb) { nb.hidden = true; }
      setStatus('That picture didn’t load.');
    });
    stage.appendChild(img);
    stage.appendChild(status);
    var title = make('h2', 'pic-title', data.title || '');
    title.setAttribute('aria-live', 'polite');
    title.hidden = !data.title;
    stage.appendChild(title);
    root.appendChild(stage);

    var credit = make('p', 'pic-credit', data.credit || '');
    credit.hidden = !data.credit;
    root.appendChild(credit);

    img.src = data.src;   // set last, so a cached picture's load event still finds the page drawn
  }

  MarySkills.register('pictures', {
    enter: function (el) {
      root = el;
      busy = false;
      draw();
    },
    leave: function (el) {
      el.innerHTML = '';
      root = null;
      fresh = false;
    },
    effect: function (kind, data) {
      if (kind !== 'picture' || !data || !data.src) { return; }
      last = { src: String(data.src), title: String(data.title || ''), credit: String(data.credit || '') };
      fresh = true;
      draw();
    }
  });
})();
