/* The pictures skill, the page half: one big picture with its title and credit, "Another picture" and "Back to Mary".
   The server finds the picture (skill.py) and sends a "picture" effect {src, title, credit}; all real state lives there.
   Taps go to POST /api/mary/skills/pictures/event {"event": {"type": "next"|"close"}}.
   aside:true stands this screen side by side with Mary: she slides left and turns toward the picture.
   Nothing ever sits over the picture: the title is above it, the credit under it, and status words show in the card
   only while no picture is up, otherwise in their own line under it.
   M13b: with a game set aside for the picture, the Back button names the game, and the game comes back (web/mary/skills.js). */
(function () {
  'use strict';
  var D = document;
  var EVENT_URL = '/api/mary/skills/pictures/event';
  var CREDIT_MAX = 140;   // characters of credit we draw, then "…"
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

  // Titles and credits can arrive with HTML in them. This makes them plain text: tags go, spaces collapse, and a long
  // one is cut short with "…". They are always drawn with textContent, never innerHTML.
  function plainText(s, max) {
    var t = String(s == null ? '' : s);
    try {
      var body = new DOMParser().parseFromString(t, 'text/html').body;
      var junk = body.querySelectorAll('script,style');
      for (var i = 0; i < junk.length; i++) { junk[i].parentNode.removeChild(junk[i]); }
      t = body.textContent || '';
    } catch (e) { log(e); }
    t = t.replace(/\s+/g, ' ').trim();
    if (max && t.length > max) { t = t.slice(0, max - 1).replace(/\s+$/, '') + '…'; }
    return t;
  }

  // The words go in the card only while no picture shows; with a picture up they get their own line under it.
  function setStatus(text) {
    var s = find('pic-status');
    if (!s) { return; }
    s.textContent = text || '';
    s.hidden = !text;
    var stage = find('pic-stage'), img = find('pic-img');
    if (!stage) { return; }
    if (img && !img.hidden) { stage.parentNode.insertBefore(s, stage.nextSibling); } else { stage.appendChild(s); }
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
      if (res && res.say && app() && app().tell) {
        try { app().tell('The app just did this: ' + res.say, res.say); } catch (e) { log(e); }
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

  // M13b: where Back goes: the game set aside for this picture when there is one, otherwise Mary.
  function backWords() {
    var who = 'Mary', label = null;
    try {
      who = (app() && app().companionName && app().companionName()) || 'Mary';
      label = window.MarySkills && window.MarySkills.backLabel && window.MarySkills.backLabel();
    } catch (e) { log(e); }
    return 'Back to ' + (label || who);
  }

  // Shown when there is no picture: what to say to get one.
  function drawEmpty() {
    var who = 'Mary';
    try { who = (app() && app().companionName && app().companionName()) || 'Mary'; } catch (e) { log(e); }
    root.appendChild(make('div', 'pic-title'));   // empty: it keeps the card clear of the Menu button
    var stage = make('div', 'pic-stage');
    var s = make('p', 'pic-status', 'Ask ' + who + ' for a picture of anything you like.');
    s.setAttribute('aria-live', 'polite');
    stage.appendChild(s);
    root.appendChild(stage);
    var bar = make('div', 'pic-bar');
    bar.appendChild(bigButton('pic-back', backWords(), goBack));   // M13b
    root.appendChild(bar);
  }

  function draw() {
    if (!root) { return; }
    root.innerHTML = '';
    if (!last || !last.src) { drawEmpty(); return; }
    var data = last;

    var title = make(data.title ? 'h2' : 'div', 'pic-title', data.title);   // the row stays when there is no title
    title.setAttribute('aria-live', 'polite');
    root.appendChild(title);

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
    root.appendChild(stage);

    var credit = make('p', 'pic-credit', data.credit || '');
    credit.hidden = !data.credit;
    root.appendChild(credit);

    var bar = make('div', 'pic-bar');
    bar.appendChild(bigButton('pic-back', backWords(), goBack));   // M13b
    bar.appendChild(bigButton('pic-next yes', 'Another picture', another));
    root.appendChild(bar);

    img.src = data.src;   // set last, so a cached picture's load event still finds the page drawn
  }

  MarySkills.register('pictures', {
    aside: true,
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
    backChanged: function () {   // M13b: the game behind the picture was ended, so Back goes to Mary now
      var b = find('pic-back');
      if (b) { b.textContent = backWords(); }
    },
    effect: function (kind, data) {
      if (kind !== 'picture' || !data || !data.src) { return; }
      last = { src: String(data.src), title: plainText(data.title), credit: plainText(data.credit, CREDIT_MAX) };
      fresh = true;
      draw();
    }
  });
})();
