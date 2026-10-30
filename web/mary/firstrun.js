/* Mary's first meeting, her daily greeting, and her sleepiness (task T4b). Plain script, loaded after app.js.
   It only uses what app.js hands out on window.MaryApp, and it replaces two of its hooks:

     MaryApp.startFirstRun   Choose your companion (board mockups/mary/round4/R4Choose.dc.html), then the
                             First hello (R4FirstHello.dc.html: waking up, hello, getting to know you).
     MaryApp.enterMain       the normal start; now it also greets the resident by name and time of day.
     MaryApp.onActivity      called by app.js when a talk starts; wakes her if she was sleepy.

   Idle (see IDLE below): after sleepMin minutes of nothing she gently falls asleep (sleepy face, nothing spoken); after
   dimMin minutes her background and glow dim softly. A tap, key or talk wakes her: the light fades back, surprised, then
   happy with a bounce, "Oh! Hello again." Power only decides the keep-awake: plugged in or unknown (GET /api/power ->
   {plugged_in: true|false|null}; a 404 or an error counts as plugged in) holds a Screen Wake Lock so the screen never
   goes black; on battery it lets go so Windows can dim as usual.

   No ?. or ?? here, so the ES2017 syntax checker parses it. */
(function () {
  'use strict';

  // Idle timings, in minutes with no talk, tap or key. She falls asleep at sleepMin (on any power); her light dims at dimMin.
  var IDLE = { sleepMin: 5, dimMin: 15 };

  var A = window.MaryApp;
  if (!A || !A.state) { return; }
  var S = A.state;
  var D = document;
  function $(id) { return D.getElementById(id); }
  function noop() {}
  function log(e) { try { console.error(e); } catch (x) { /* nothing */ } }

  var origEnterMain = A.enterMain;
  var flow = 0;                 // bumps whenever a new chain of steps starts, so an old chain can tell it is stale
  var skipOn = false;           // a tap on the screen skips ahead (first hello, steps 1-2)
  var waiter = null;            // the pause that a tap can end early

  // M4a: the big Talk button is gone (M4b): A.restLine() names only ways in that work (her name, or Menu)
  function sleepyCaption() { return S.typingOnly ? A.restLine(true) : A.restLine(false).replace(' any time you want to talk.', ' whenever you need me.'); }

  function restCaption() { return A.restLine(!!S.typingOnly); }   // M4a

  // A pause that a tap on the screen can end early.
  function wait(ms) {
    return new Promise(function (resolve) {
      var t = setTimeout(done, ms);
      function done() {
        clearTimeout(t);
        if (waiter && waiter.done === done) { waiter = null; }
        resolve();
      }
      waiter = { done: done };
    });
  }

  function skipAhead() {
    A.newTurn();                // stops her voice; the line being said counts as done
    if (waiter) { waiter.done(); }
  }

  // ================================================================ Choose your companion
  var CH = null;                // { root, faces: {mary, him}, picked, timer }
  var SAM_FALLBACK = 'Sam';

  var MARY_WORDS = ['mary', 'marie', 'mari', 'merry'];                // names count anywhere in what was said
  var SAM_WORDS = ['sam', 'sammy'];
  var MARY_HINTS = ['her', 'she', 'woman', 'lady', 'girl', 'you'];    // pronouns and descriptors count only in a short answer,
  var SAM_HINTS = ['him', 'he', 'man', 'gentleman', 'guy', 'boy'];    // so "what do you mean?" or TV chatter picks no one
  var HINT_MAX_WORDS = 5;
  var YOU_MAX_WORDS = 3;                                              // "You!" or "I'll take you" picks Mary; "what do you mean?" doesn't

  // What the resident said -> 'mary' | 'him' | '' (unclear, or both named)
  function parseChoice(text) {
    var words = String(text || '').toLowerCase().replace(/[^a-z\s]/g, ' ').split(/\s+/).filter(Boolean);
    var himName = String(A.companionName('him') || SAM_FALLBACK).toLowerCase();
    var maryName = String(A.companionName('mary') || 'Mary').toLowerCase();
    var hints = words.length <= HINT_MAX_WORDS;
    var m = false, s = false;
    for (var i = 0; i < words.length; i++) {
      var w = words[i];
      if (w === 'you' && words.length > YOU_MAX_WORDS) { continue; }
      if (w === maryName || MARY_WORDS.indexOf(w) >= 0 || (hints && MARY_HINTS.indexOf(w) >= 0)) { m = true; }
      if (w === himName || SAM_WORDS.indexOf(w) >= 0 || (hints && SAM_HINTS.indexOf(w) >= 0)) { s = true; }
    }
    if (m && !s) { return 'mary'; }
    if (s && !m) { return 'him'; }
    return '';
  }

  function makeSmallFace(box, c) {
    try {
      if (typeof MaryFace !== 'undefined') { return MaryFace.create(box, { companion: c }); }
    } catch (e) { log(e); }
    return null;
  }

  function buildCard(c) {
    var name = A.companionName(c);
    var b = D.createElement('button');
    b.type = 'button';
    b.className = 'pick';
    b.setAttribute('data-c', c);
    b.setAttribute('aria-label', 'Choose ' + name);
    var box = D.createElement('div');
    box.className = 'pickface';
    var lbl = D.createElement('span');
    lbl.className = 'pickname';
    lbl.textContent = name;
    b.appendChild(box);
    b.appendChild(lbl);
    b.addEventListener('click', function () { pick(c); });
    return { card: b, box: box };
  }

  A.registerScreen('choose', {
    enter: function () {
      var root = D.createElement('div');
      root.id = 'choose';
      root.className = 'choose';
      var edge = D.createElement('div');
      edge.className = 'edge';
      edge.setAttribute('aria-hidden', 'true');
      var row = D.createElement('div');
      row.className = 'pickrow';
      var m = buildCard('mary'), h = buildCard('him');
      row.appendChild(m.card);
      row.appendChild(h.card);
      root.appendChild(edge);
      root.appendChild(row);
      $('scr').appendChild(root);
      CH = { root: root, cards: { mary: m.card, him: h.card }, faces: {}, picked: '', timer: null };
      CH.faces.mary = makeSmallFace(m.box, 'mary');
      CH.faces.him = makeSmallFace(h.box, 'him');
    },
    leave: function () {
      var ch = CH;
      CH = null;
      if (!ch) { return; }
      ch.root.classList.add('leaving');          // fades out over the sleepy face; the small faces live until it is gone
      ch.timer = setTimeout(function () {
        ['mary', 'him'].forEach(function (k) {
          var f = ch.faces[k];
          if (f) { try { f.destroy(); } catch (e) { log(e); } }
        });
        if (ch.root.parentNode) { ch.root.parentNode.removeChild(ch.root); }
      }, 700);
    }
  });

  // Mary says it on her card: her face talks while the voice speaks.
  function sayOnCard(text) {
    var f = CH && CH.faces.mary;
    if (f) { f.setActivity('talking'); }
    return A.say(text, 'happy').then(function () {
      if (f && CH && !CH.picked) { f.setActivity('resting'); }
    });
  }

  // Listen once with Mary's card showing the listening face. Resolves { text, failed, cancelled }.
  function hearChoice() {
    var f = CH && CH.faces.mary;
    if (f) { f.setActivity('listening'); }
    function end() {
      if (CH && !CH.picked) {                    // a tap may have chosen already; then her mouth must not stop mid-sentence
        A.setPhase('idle');
        if (f) { f.setActivity('resting'); }
      }
    }
    return A.listenOnce().then(function (t) {
      end();
      return { text: String(t || '').trim() };
    }, function (e) {
      if (e && e.cancelled) { return { cancelled: true }; }
      end();
      log(e);
      return { failed: true };
    });
  }

  async function chooseByVoice(tok) {
    var sam = A.companionName('him') || SAM_FALLBACK;
    var ask = 'Would you like to talk with me, or with ' + sam + '?';
    await sayOnCard(ask);
    if (tok !== flow || !CH || CH.picked) { return; }
    if (S.typingOnly) { return; }                  // no speech here: just wait for a tap
    for (var tries = 0; tries < 2; tries++) {
      var r = await hearChoice();
      if (tok !== flow || !CH || CH.picked || r.cancelled) { return; }
      var c = r.failed ? '' : parseChoice(r.text);
      if (c) { pick(c); return; }
      if (r.failed) { break; }
      if (tries === 0) {
        await sayOnCard("I'm sorry, I didn't catch that. Would you like to talk with me, or with " + sam + '?');
        if (tok !== flow || !CH || CH.picked) { return; }
      }
    }
    A.setCaption('Just tap the one you would like to talk with.');
  }

  function pick(c) {
    if (!CH || CH.picked) { return; }
    var ch = CH;
    ch.picked = c;
    var tok = ++flow;                              // ends the voice-choose chain
    A.newTurn();
    A.setCompanion(c);                             // saves the choice and switches her look and voice
    A.setMood('sleepy');                           // behind the cards, ready for the hello
    var other = c === 'mary' ? 'him' : 'mary';
    var f = ch.faces[c];
    if (f) { try { f.setActivity('resting'); f.setMood('happy'); f.bounce(); } catch (e) { log(e); } }
    ch.cards[c].classList.add('chosen');
    ch.cards[other].classList.add('gone');
    setTimeout(function () {
      if (tok !== flow) { return; }
      hello(c, tok).catch(log);
    }, 1000);
  }

  function startFirstRun() {
    if (S.screen === 'choose' || S.screen === 'hello') { return; }
    S.firstRun = true;
    var tok = ++flow;
    A.setCompanion('mary', { noSave: true });
    A.setCaption('');
    A.show('choose');
    chooseByVoice(tok).catch(log);
  }

  // ================================================================ First hello
  A.registerScreen('hello', {
    enter: function () { A.setCaption(''); },
    leave: function () { skipOn = false; closeNameBox(); }
  });

  function ensureNameBox() {
    var ov = $('nameBox');
    if (ov) { return ov; }
    ov = D.createElement('div');
    ov.id = 'nameBox';
    ov.className = 'overlay';
    ov.hidden = true;
    var form = D.createElement('form');
    form.id = 'nameForm';
    form.className = 'panel typing';
    form.setAttribute('autocomplete', 'off');
    var lbl = D.createElement('label');
    lbl.setAttribute('for', 'nameText');
    lbl.textContent = 'Type your name';
    var inp = D.createElement('input');
    inp.type = 'text';
    inp.id = 'nameText';
    inp.maxLength = 60;
    inp.setAttribute('autocomplete', 'off');
    var btns = D.createElement('div');
    btns.className = 'btns';
    var ok = D.createElement('button');
    ok.type = 'submit';
    ok.className = 'btn yes';
    ok.textContent = 'OK';
    var skip = D.createElement('button');
    skip.type = 'button';
    skip.id = 'nameSkip';
    skip.className = 'btn';
    skip.textContent = 'Not now';
    btns.appendChild(ok);
    btns.appendChild(skip);
    form.appendChild(lbl);
    form.appendChild(inp);
    form.appendChild(btns);
    ov.appendChild(form);
    $('scr').appendChild(ov);
    return ov;
  }

  function closeNameBox() {
    var ov = $('nameBox');
    if (ov) { ov.hidden = true; }
  }

  // Typing instead of speaking. Resolves { text } or { skipped: true }.
  function typeName() {
    return new Promise(function (resolve) {
      var ov = ensureNameBox();
      var form = $('nameForm'), inp = $('nameText'), skip = $('nameSkip');
      inp.value = '';
      ov.hidden = false;
      setTimeout(function () { try { inp.focus(); } catch (e) { /* nothing */ } }, 30);
      function end(v) {
        form.onsubmit = null;
        skip.onclick = null;
        ov.hidden = true;
        resolve(v);
      }
      form.onsubmit = function (ev) {
        ev.preventDefault();
        var v = inp.value.trim();
        if (!v) { try { inp.focus(); } catch (e) { /* nothing */ } return; }
        end({ text: v });
      };
      skip.onclick = function () { end({ skipped: true }); };
    });
  }

  // What she hears (or what is typed). Resolves { text } or { skipped: true }.
  function getAnswer(question) {
    if (S.typingOnly) { return typeName(); }
    return A.listenOnce().then(function (t) {
      A.setPhase('idle');
      return { text: String(t || '').trim() };
    }, function (e) {
      A.setPhase('idle');
      if (e && e.cancelled) { return { text: '' }; }
      log(e);
      A.setCaption(question);                     // the caption would still say "I'm listening…" over the typing box
      return typeName();
    });
  }

  async function askName() {
    var asks = ['What would you like me to call you?', "I didn't quite catch that. What should I call you?"];
    for (var i = 0; i < asks.length; i++) {
      await A.say(asks[i], 'happy');
      var ans = await getAnswer(asks[i]);
      if (ans.skipped) { break; }
      if (!ans.text) { continue; }
      A.setPhase('thinking');
      var r = null;
      try { r = await A.api('POST', '/api/mary/hello', { text: ans.text }, { ms: 20000 }); } catch (e) { log(e); }
      A.setPhase('idle');
      var name = (r && r.name) ? String(r.name).trim() : '';
      if (name) {
        S.name = name;
        try { A.getFace().bounce(); } catch (e2) { /* nothing */ }
        await A.say(String((r && r.text) || ('It is lovely to meet you, ' + name + '.')), 'happy');
        return true;
      }
    }
    await A.say("That's all right. You can tell me any time.", 'happy');
    return false;
  }

  async function hello(c, tok) {
    A.show('hello');
    var n = A.companionName(c);
    A.setMood('sleepy');                           // step 1: eyes closed, dusk
    skipOn = true;
    await wait(1800);
    if (tok !== flow) { return; }
    A.setMood('surprised');                        // she wakes
    await A.say('Oh! Hello there.', 'surprised');
    if (tok !== flow) { return; }
    await wait(250);
    if (tok !== flow) { return; }
    try { A.getFace().bounce(); } catch (e) { /* nothing */ }
    await A.say("I'm " + n + ". It's so nice to meet you.", 'happy');   // step 2
    skipOn = false;
    if (tok !== flow) { return; }
    await wait(300);
    await askName();                               // step 3: getting to know you
    if (tok !== flow) { return; }
    if (S.talkOnOpen && S.hasKey) {                // M4a: she carries on talking, no tap needed
      S.firstRun = false;
      enterMainQuiet();
      if (S.screen === 'everyday') { A.startTalk({ say: FIRST_TALK, hello: FIRST_TALK_LIVE }).catch(log); }
      return;
    }
    await A.say(A.restLine(false), 'happy');   // M4a: no Talk button any more
    if (tok !== flow) { return; }
    S.firstRun = false;
    enterMainQuiet();
  }

  // ================================================================ greeting on later opens
  // M4a: warm and varied, like a friend glad to see them; the night lines never remark on the hour.
  // Grown-up and plain (Andy: no talking down): no "rise and shine", no "how are you feeling", few exclamation marks.
  var GREET = {
    morning: [
      "Good morning{n}. It's good to see you.",
      "Well, good morning{n}. Did you sleep all right?",
      "Morning{n}. What's going on today?",
      "Hey there{n}, good morning. What's new with you?",
      "Good morning{n}. How's the day starting out?",
      "Morning{n}. Good to see you. Got anything on your mind?"
    ],
    afternoon: [
      "Good afternoon{n}. How's your day treating you?",
      "Well, hey there{n}. Good to see you this afternoon.",
      "Afternoon{n}. It's real good to see you.",
      "Hi{n}. How's your afternoon going?",
      "Good afternoon{n}. What's been going on?",
      "Hey{n}. Tell me how your day's going."
    ],
    evening: [
      "Good evening{n}. It's good to see you.",
      "Well, hey there{n}. How was your day?",
      "Evening{n}. Glad to have the company.",
      "Hi{n}. How was supper tonight?",
      "Good evening{n}. Sit a spell and tell me about your day.",
      "Hey{n}, good evening. Good to see you."
    ],
    night: [
      "Well, hey there{n}. Can't sleep? I'm glad for the company.",
      "Hi{n}. It's a nice quiet night. Want to talk a little while?",
      "Hey{n}. It's good to see you. Want some company for a bit?",
      "Hello{n}. Nice and quiet tonight. Good time for a talk.",
      "Hey there{n}. Want to talk a while? I'd like that.",
      "Hi{n}. A little company is nice on a quiet night."
    ]
  };

  function slotFor(h) {
    if (h >= 22 || h < 5) { return 'night'; }   // M4a: was 'late'
    if (h < 12) { return 'morning'; }
    if (h < 17) { return 'afternoon'; }
    return 'evening';
  }

  function greetingText() {
    var slot = slotFor(new Date().getHours());
    var list = GREET[slot];
    var last = -1;
    try { last = Number(localStorage.getItem('maryGreet.' + slot)); } catch (e) { last = -1; }
    var i = Math.floor(Math.random() * list.length);
    if (list.length > 1 && i === last) { i = (i + 1) % list.length; }
    try { localStorage.setItem('maryGreet.' + slot, String(i)); } catch (e2) { /* nothing */ }
    var nm = S.name ? ', ' + S.name : '';
    return { text: list[i].replace('{n}', nm), slot: slot };
  }

  function greet() {
    var g = greetingText();
    if (g.slot !== 'night') {
      try { A.getFace().bounce(); } catch (e) { /* nothing */ }
    }
    // if the webview blocks her voice before a first tap, say() still leaves the caption up and does not retry
    A.openingLine(g.text).then(function (line) {   // M4a: her own words, with the scripted line behind them
      if (line.text) { return A.say(line.text, g.slot === 'night' ? 'talking' : 'happy', undefined, line.saved); }
    }).catch(log);
  }

  // M4a: "Start talking when Mary opens" (talk_on_open). She starts the talk herself: Live says its own hello
  // (with the time of day); Normal and Offline say the brain's hello, or a scripted greeting if that fails, then
  // listen. 15 s of quiet and she rests.
  function talkOnOpen() {
    var g = greetingText();
    if (g.slot !== 'night') {
      try { A.getFace().bounce(); } catch (e) { /* nothing */ }
    }
    A.startTalk({ say: g.text, brainHello: true, mood: g.slot === 'night' ? 'talking' : 'happy' }).catch(log);   // M4a
  }
  // M4a: after the first hello she carries on talking; she has just greeted them, so no second hello
  var FIRST_TALK = "Now, tell me a little about yourself. I'd love to get to know you.";
  var FIRST_TALK_LIVE = "(You just met them on this screen a moment ago, so don't greet them again. In one short, " +
    "warm sentence, ask them one easy question about themselves, then listen.)";

  function enterMainQuiet() {
    origEnterMain();
    lastAct = Date.now();
    asleep = false;
    setDim(false);
  }

  A.enterMain = function () {
    enterMainQuiet();
    if (S.screen !== 'everyday' || !S.hasKey) { return; }   // never on the emergency or no-key screens
    if (S.talkOnOpen) { talkOnOpen(); } else { greet(); }   // M4a
  };

  A.startFirstRun = startFirstRun;

  // ================================================================ keep the screen on (power)
  // Power only decides the keep-awake, never the sleep. Plugged in, unknown, a 404 or an error: hold a Screen Wake Lock
  // so the screen never goes black. On battery (plugged_in === false): let go, so Windows can dim as usual.
  var onBattery = false;
  var wl = { sentinel: null, pending: false };

  function keepScreenOn() {
    try {
      if (wl.sentinel || wl.pending || onBattery) { return; }
      if (!navigator.wakeLock || typeof navigator.wakeLock.request !== 'function') { return; }
      if (D.visibilityState && D.visibilityState !== 'visible') { return; }
      wl.pending = true;
      navigator.wakeLock.request('screen').then(function (lock) {
        wl.pending = false;
        if (onBattery) { try { lock.release(); } catch (e) { /* nothing */ } return; }
        wl.sentinel = lock;
        try {
          lock.addEventListener('release', function () { if (wl.sentinel === lock) { wl.sentinel = null; } });
        } catch (e2) { /* nothing */ }
      }, function () { wl.pending = false; });
    } catch (e3) { wl.pending = false; }
  }

  function releaseScreen() {
    var lock = wl.sentinel;
    wl.sentinel = null;
    if (lock) { try { lock.release(); } catch (e) { /* nothing */ } }
  }

  // p is the /api/power answer, or null when it could not be read (404, error): that counts as plugged in.
  function updatePower(p) {
    onBattery = !!(p && p.plugged_in === false);
    if (onBattery) { releaseScreen(); } else { keepScreenOn(); }
  }

  function pollPower() {
    A.api('GET', '/api/power', null, { ms: 5000 }).then(updatePower, function () { updatePower(null); });
  }

  // ================================================================ idle: sleepy, then dim
  var lastAct = Date.now();
  var asleep = false;
  var dimmed = false;
  var dimEl = null;
  var wakeTimer = null;

  function overlaysClosed() {
    var m = $('menu'), t = $('typing'), nb = $('nameBox');
    var panel = D.querySelector('.overlay.sheet:not([hidden])');   // M4b: Things Mary can do, My info, Choose
    return (!m || m.hidden) && (!t || t.hidden) && (!nb || nb.hidden) && !panel;
  }

  // The dim layer sits inside her face, between the glow layers and the face (.mf-root > .mf-dim before .mf-fit),
  // so the background and glow dim more than her face. Without a face it is a full-screen layer below the dock.
  function dimLayer() {
    if (dimEl && dimEl.parentNode) { return dimEl; }
    dimEl = null;
    try {
      var root = A.getFace().el;
      var d = D.createElement('div');
      d.className = 'mf-dim';
      d.setAttribute('aria-hidden', 'true');
      if (root && root.insertBefore) {
        var fit = root.querySelector('.mf-fit');
        if (fit) { root.insertBefore(d, fit); } else { root.appendChild(d); }
      } else {
        d.style.zIndex = '1';
        $('scr').appendChild(d);
      }
      void d.offsetWidth;                         // so the first fade starts from 0
      dimEl = d;
    } catch (e) { log(e); dimEl = null; }
    return dimEl;
  }

  function setDim(on) {
    dimmed = !!on;
    var d = on ? dimLayer() : dimEl;
    if (d) { d.classList.toggle('on', !!on); }
  }

  function sleep() {
    asleep = true;
    A.setMood('sleepy');                          // the face only; nothing is spoken
    A.setCaption(sleepyCaption());   // M4a
  }

  // quiet = true (a button, or a talk that is starting): the light comes back and she is just resting.
  // Otherwise: surprised, then happy with a bounce and "Oh! Hello again."
  function wake(quiet) {
    if (!asleep) { return; }
    asleep = false;
    lastAct = Date.now();
    clearTimeout(wakeTimer);
    setDim(false);
    if (S.screen !== 'everyday') { return; }
    if (quiet) {
      A.setMood('resting');
      A.setCaption(restCaption());
      return;
    }
    var t0 = S.turn;
    A.setMood('surprised');
    wakeTimer = setTimeout(function () {
      if (S.screen !== 'everyday') { return; }
      if (S.turn !== t0 || S.phase !== 'idle') { A.setMood('happy'); return; }   // a talk began meanwhile
      try { A.getFace().bounce(); } catch (e) { /* nothing */ }
      A.say('Oh! Hello again.', 'happy').catch(log);
    }, 600);
  }

  function tick() {
    var now = Date.now();
    if (S.screen !== 'everyday' || S.phase !== 'idle' || !overlaysClosed()) {
      if (asleep && S.screen !== 'everyday') { asleep = false; clearTimeout(wakeTimer); setDim(false); }
      lastAct = now;
      return;
    }
    var idle = now - lastAct;
    if (!asleep) {
      if (idle >= IDLE.sleepMin * 60000) { sleep(); }
      return;
    }
    if (!dimmed && idle >= IDLE.dimMin * 60000) { setDim(true); }
  }

  function onAct(ev) {
    lastAct = Date.now();
    if (skipOn && S.screen === 'hello' && ev && ev.type === 'pointerdown') {
      var onUi = false;
      try { onUi = !!(ev.target && ev.target.closest && ev.target.closest('button, .overlay')); } catch (e) { onUi = false; }
      if (!onUi) {                                // a tap on More, Done or Close is not "skip": only a tap on her face is
        skipAhead();
        return;
      }
    }
    if (!asleep) { return; }
    var t = ev && ev.target;
    var onControl = false;
    try { onControl = !!(t && t.closest && t.closest('button, .overlay')); } catch (e) { onControl = false; }
    wake(onControl);                              // a tap on her face or a key press gets "Oh! Hello again."; a button wakes her quietly
  }

  A.onActivity = function () {
    lastAct = Date.now();
    if (asleep) { wake(true); }
  };

  D.addEventListener('pointerdown', onAct, true);
  D.addEventListener('keydown', onAct, true);
  var idleTimer = setInterval(tick, 5000);
  var powerTimer = setInterval(pollPower, 60000);

  D.addEventListener('visibilitychange', function () {
    if (D.visibilityState === 'visible') { keepScreenOn(); }
  });
  window.addEventListener('pagehide', function () {
    releaseScreen();
    clearInterval(idleTimer);
    clearInterval(powerTimer);
    clearTimeout(wakeTimer);
  });

  keepScreenOn();                                 // unknown power counts as plugged in
  pollPower();
})();
