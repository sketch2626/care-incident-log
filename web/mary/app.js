/* Mary's screen (web/mary.html): the screen IS her face. Plain script, no libraries.

   Screens (a small state machine; the page element #scr carries data-screen="..."):
     'everyday'   resting face, big Talk button, caption
     'emergency'  alert face, "Get help now" card with two buttons, deep red caption
     'nokey'      sorry face, "Open My info" button
   show(name, opts) switches screen. registerScreen(name, {enter(opts, prev), leave(next)}) adds more
   (the first-run screens). CSS for a new screen goes in mary.css under [data-screen="name"].

   Phases of the talk loop (S.phase): 'idle' | 'listening' | 'thinking' | 'speaking'.
   setPhase(p) also sets the face activity and the Talk button.

   For the first-run and greeting code (task T4b), all on window.MaryApp:
     MaryApp.talkTo(text)        send text through the talk pipeline (shows "You said", streams, speaks); resolves when she is done
     MaryApp.say(text, mood)     show a caption, set the mood, speak it; resolves when she is done (or was interrupted)
     MaryApp.listenOnce()        listen with the Talk button UI; resolves with the heard text ('' = nothing);
                                 MaryApp.state.listenReason is 'quiet' | 'tap' | 'silence' | 'cap'; rejects with Error
                                 (err.stage 'start' | 'stop', err.cancelled true if interrupted)
     MaryApp.setCompanion(c, {noSave})   'mary' | 'him'; saves with PUT /api/settings unless noSave
     MaryApp.show(name, opts), MaryApp.registerScreen(name, handlers), MaryApp.setCaption(text, 'said'|''),
     MaryApp.setMood(m), MaryApp.newTurn() (stop everything in progress), MaryApp.cancelSpeech(),
     MaryApp.openTyping(), MaryApp.refreshStatus(), MaryApp.getFace()
   Replace MaryApp.startFirstRun (called on load when status.first_run) and call MaryApp.enterMain() when done.

   No ?. or ?? here, so the ES2017 syntax checker parses it. */
(function () {
  'use strict';

  var D = document;
  function $(id) { return D.getElementById(id); }
  function noop() {}
  function log(e) { try { console.error(e); } catch (x) { /* nothing */ } }

  var RATE_MIN = 0.6, RATE_MAX = 1.4, VOL_MIN = 0.2, VOL_MAX = 1.0;
  var MIN_LISTEN_MS = 800;       // a second tap this soon after the mic opens is a double tap, not "I'm done"
  var SILENCE_NOISE = /^\W*(?:you|thank you|thanks|thank you for watching|thanks for watching|bye|okay|ok|so|um+|uh+)?\W*$/i;

  var MSG = {
    tapToTalk: "Tap the button and talk to me any time.",
    tapToType: "Tap the button and type to me any time.",
    listening: "I'm listening…",
    silence: "I didn't hear anything. Tap the button and talk whenever you're ready.",
    notCaught: "I didn't quite catch that. Could you say it again?",
    waking: "I'm still waking up my ears. Please try again in a moment.",
    sorry: "I'm sorry, something went wrong. Let's try again.",
    nokey: "I need my key before we can chat. Please paste it in My info, in the Smart helper key box.",
    emergency: "Please press your call light or tell a staff member right now. If it's serious, call 911.",
    light: "Good. Help is on the way. I'll stay right here with you.",
    helpAsk: "Has someone come to help you yet?",
    okNow: "I'm so glad. I'm right here if you need me.",
    better: "Is this better?",
    loading: "I'm getting ready. Just a moment."
  };

  // ---------------------------------------------------------------- state
  var S = {
    companion: 'mary',
    names: { mary: 'Mary', him: 'Sam' },
    hasKey: false,
    firstRun: false,
    name: '',
    rate: 0.92,
    volume: 1,
    statusLoaded: false,
    screen: '',
    phase: 'idle',
    turn: 0,
    ctrl: null,
    typingOnly: false,
    stopNow: null,
    listenAbort: null,
    listenReason: '',
    emSeq: 0,
    lightPressed: false,
    helpAsked: false,
    lightTimer: null,
    chipTimer: null
  };

  var NULLFACE = { setMood: noop, setActivity: noop, setCompanion: noop, bounce: noop, destroy: noop };
  var face = NULLFACE;

  function makeFace(companion) {
    try {
      if (typeof MaryFace !== 'undefined') { return MaryFace.create($('face'), { companion: companion }); }
    } catch (e) { log(e); }
    return NULLFACE;
  }

  function validMood(m) {
    try { return MaryFace.MOODS.indexOf(m) >= 0; } catch (e) { return false; }
  }
  function setMood(m) {
    if (!validMood(m)) { return; }
    try { face.setMood(m); } catch (e) { log(e); }
  }

  function companionName(c) {
    var n = S.names && S.names[c];
    if (n) { return String(n); }
    try { return MaryFace.COMPANIONS[c].name; } catch (e) { /* fall through */ }
    return c === 'him' ? 'Sam' : 'Mary';
  }

  function applyLook(c) {
    var bg = '';
    try { bg = MaryFace.COMPANIONS[c].look.bg || ''; } catch (e) { bg = ''; }
    D.documentElement.style.background = bg;
    D.body.style.background = bg;
    $('scr').style.background = bg;
  }

  // ---------------------------------------------------------------- server calls
  function api(method, url, body, opts) {
    opts = opts || {};
    var init = { method: method, cache: 'no-store', headers: {} };
    if (method !== 'GET') {
      init.headers['X-Tracker'] = '1';
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body || {});
    }
    var timer = null;
    if (opts.signal) {
      init.signal = opts.signal;
    } else if (typeof AbortController === 'function') {
      var c = new AbortController();
      init.signal = c.signal;
      timer = setTimeout(function () { try { c.abort(); } catch (e) { /* nothing */ } }, opts.ms || 20000);
    }
    return fetch(url, init).then(function (r) {
      return r.text().then(function (t) {
        if (timer) { clearTimeout(timer); }
        var j = {};
        try { j = t ? JSON.parse(t) : {}; } catch (e) { j = {}; }
        if (!r.ok) {
          var msg = (j && j.error) ? String(j.error) : '';
          var err = new Error(msg || ('HTTP ' + r.status));
          err.status = r.status;
          err.serverMessage = msg;
          throw err;
        }
        return j;
      });
    }, function (e) {
      if (timer) { clearTimeout(timer); }
      throw e;
    });
  }

  // ---------------------------------------------------------------- caption, chip, button
  function setCaption(text, kind) {
    var c = $('caption');
    text = String(text == null ? '' : text);
    c.className = 'caption' + (kind ? ' ' + kind : '');
    c.textContent = text;
    c.hidden = !text;
    c.scrollTop = c.scrollHeight;
  }

  function showChip() {
    var c = $('chip');
    c.hidden = false;
    clearTimeout(S.chipTimer);
    S.chipTimer = setTimeout(function () { c.hidden = true; }, 5000);
  }

  function reduced() {
    try { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); } catch (e) { return false; }
  }

  function setRing(level) {
    var r = $('ring');
    level = Math.max(0, Math.min(1, Number(level) || 0));
    r.style.opacity = String(0.3 + level * 0.7);
    r.style.transform = reduced() ? '' : 'scale(' + (1 + level * 0.1).toFixed(3) + ')';
  }

  function updateTalkButton() {
    var b = $('talkBtn'), lbl = $('talkLbl'), n = companionName(S.companion);
    var ic = 'mic', text = 'Talk to ' + n, disabled = false;
    if (S.phase === 'listening') { ic = 'done'; text = "I'm done"; }
    else if (S.phase === 'thinking') { ic = 'wait'; text = 'One moment…'; disabled = true; }
    else if (S.typingOnly) { ic = 'type'; text = 'Type to ' + n; }
    b.setAttribute('data-state', S.phase);
    b.setAttribute('data-ic', ic);
    b.setAttribute('aria-busy', S.phase === 'thinking' ? 'true' : 'false');
    lbl.textContent = text;
    b.disabled = disabled;
  }

  function setPhase(p) {
    S.phase = p;
    var a = p === 'listening' ? 'listening' : p === 'thinking' ? 'thinking' : p === 'speaking' ? 'talking' : 'resting';
    try { face.setActivity(a); } catch (e) { log(e); }
    $('scr').setAttribute('data-phase', p);
    updateTalkButton();
    if (p !== 'listening') { setRing(0); }
  }

  function refreshLabels() {
    var n = companionName(S.companion);
    var other = companionName(S.companion === 'mary' ? 'him' : 'mary');
    $('switchBtn').textContent = 'Switch to ' + other;
    $('typeMenuBtn').textContent = 'Type to ' + n;
    $('typeLabel').textContent = 'Type what you would like to say to ' + n;
    D.title = n;
    updateTalkButton();
  }

  // ---------------------------------------------------------------- voice (speechSynthesis)
  var V = {
    ok: (typeof window.speechSynthesis !== 'undefined' && typeof window.SpeechSynthesisUtterance === 'function'),
    voices: [],
    promise: null,
    bad: {},
    refs: [],
    primed: false
  };
  var Sp = { sess: null, cancelAt: 0 };

  var VOICE_NAMES = {
    mary: { nat: ['aria', 'jenny', 'ava', 'emma', 'michelle', 'sonia', 'libby'], cls: ['zira', 'hazel', 'susan', 'catherine'] },
    him: { nat: ['guy', 'andrew', 'brian', 'christopher', 'eric', 'ryan'], cls: ['david', 'mark', 'george'] }
  };
  var WRONG_GENDER = {
    mary: ['david', 'mark', 'george', 'guy', 'andrew', 'brian', 'christopher', 'eric', 'ryan', 'james', 'richard', 'ravi', 'sean', 'roger', 'thomas', 'liam', 'william', 'alfie', 'steffan', 'male'],
    him: ['aria', 'jenny', 'ava', 'emma', 'michelle', 'sonia', 'libby', 'zira', 'hazel', 'susan', 'catherine', 'heera', 'linda', 'mia', 'clara', 'natasha', 'samantha', 'jessa', 'sara', 'allison', 'amy', 'ivy', 'joanna', 'kendra', 'kimberly', 'salli', 'nicole', 'karen', 'kate', 'serena', 'tessa', 'moira', 'fiona', 'victoria', 'female']
  };

  function firstIndex(tokens, list) {
    var best = -1;
    for (var i = 0; i < list.length; i++) {
      if (tokens.indexOf(list[i]) >= 0) { best = i; break; }
    }
    return best;
  }

  function getVoicesSafe() {
    try { return window.speechSynthesis.getVoices() || []; } catch (e) { return []; }
  }

  // Resolves once voices are loaded, or after 1.5 s, whichever comes first.
  function whenVoices() {
    if (V.promise) { return V.promise; }
    V.promise = new Promise(function (resolve) {
      if (!V.ok) { resolve([]); return; }
      var finished = false, t = null;
      function fin() {
        if (finished) { return; }
        finished = true;
        clearTimeout(t);
        try { window.speechSynthesis.removeEventListener('voiceschanged', on); } catch (e) { /* nothing */ }
        V.voices = getVoicesSafe();
        resolve(V.voices);
      }
      function on() { if (getVoicesSafe().length) { fin(); } }
      t = setTimeout(fin, 1500);
      try { window.speechSynthesis.addEventListener('voiceschanged', on); } catch (e) { /* nothing */ }
      on();
    });
    return V.promise;
  }

  function scoreVoice(v, who) {
    var name = String(v.name || '').toLowerCase();
    var lang = String(v.lang || '').toLowerCase().replace('_', '-');
    if (lang.indexOf('en') !== 0) { return -1; }
    var tokens = name.split(/[^a-z]+/);
    var natural = name.indexOf('natural') >= 0;
    var p = VOICE_NAMES[who];
    var ni = firstIndex(tokens, p.nat), ci = firstIndex(tokens, p.cls);
    var s;
    if (natural && ni >= 0) { s = 1000 - ni * 10; }
    else if (ci >= 0) { s = 800 - ci * 10; }
    else if (ni >= 0) { s = 700 - ni * 10; }
    else if (lang === 'en-us') { s = 300; }
    else { s = 200; }
    if (firstIndex(tokens, WRONG_GENDER[who]) >= 0) { s -= 500; }
    if (v.localService) { s += 5; }
    return s;
  }

  function pickVoice(who, localOnly) {
    var best = null, bs = -1;
    var offline = (typeof navigator.onLine === 'boolean') && !navigator.onLine;
    var list = V.voices.length ? V.voices : getVoicesSafe();
    for (var i = 0; i < list.length; i++) {
      var v = list[i];
      if (V.bad[v.name]) { continue; }
      if ((localOnly || offline) && !v.localService) { continue; }
      var sc = scoreVoice(v, who);
      if (sc > bs) { bs = sc; best = v; }
    }
    return best;
  }

  function cleanSpeech(t) {
    return String(t == null ? '' : t).replace(/[*_`#]+/g, '').replace(/\s+/g, ' ').trim();
  }

  function estimateMs(text) {
    return Math.max(800, Math.round(text.length / 14 * 1000 / Math.max(0.6, S.rate)));
  }

  var ABBR = { mr: 1, mrs: 1, ms: 1, dr: 1, st: 1, jr: 1, sr: 1, vs: 1, mt: 1, prof: 1, rev: 1, gen: 1 };

  // Cuts text into sentences. While more text may still come (final false) the last, unfinished piece is held back.
  function splitSentences(buf, final) {
    var out = [], start = 0, n = buf.length, i = 0;
    while (i < n) {
      var ch = buf.charAt(i);
      if (ch !== '.' && ch !== '!' && ch !== '?') { i++; continue; }
      var j = i + 1;
      while (j < n && '.!?"\')”’'.indexOf(buf.charAt(j)) >= 0) { j++; }
      if (j >= n) { break; }
      if (!/\s/.test(buf.charAt(j))) { i = j; continue; }
      if (ch === '.') {
        var k = i - 1;
        while (k >= 0 && /[A-Za-z]/.test(buf.charAt(k))) { k--; }
        var word = buf.slice(k + 1, i).toLowerCase();
        if (ABBR[word] === 1 || word.length === 1) { i = j; continue; }
      }
      var piece = buf.slice(start, j).trim();
      if (piece) { out.push(piece); }
      start = j;
      i = j;
    }
    var rest = buf.slice(start);
    if (final) {
      if (rest.trim()) { out.push(rest.trim()); }
      rest = '';
    } else if (rest.length > 280) {
      var cut = rest.lastIndexOf(' ', 240);
      if (cut < 60) { cut = 240; }
      out.push(rest.slice(0, cut).trim());
      rest = rest.slice(cut);
    }
    return { sentences: out, rest: rest };
  }

  function addTimer(s, fn, ms) {
    var id = setTimeout(fn, ms);
    s.timers.push(id);
    return id;
  }

  function settle(s) {
    var w = s.waiters;
    s.waiters = [];
    for (var i = 0; i < w.length; i++) { try { w[i](); } catch (e) { log(e); } }
  }

  function spCancel() {
    var s = Sp.sess;
    Sp.sess = null;
    if (s) {
      s.finished = true;
      s.queue = [];
      for (var i = 0; i < s.timers.length; i++) { clearTimeout(s.timers[i]); }
      s.timers = [];
      settle(s);
    }
    if (V.ok) {
      try { window.speechSynthesis.cancel(); } catch (e) { /* nothing */ }
      Sp.cancelAt = Date.now();
    }
  }

  function spStart() {
    spCancel();
    var s = { queue: [], busy: false, ended: false, started: false, finished: false, waiters: [], timers: [] };
    Sp.sess = s;
    return s;
  }

  function waitSess(s) {
    return new Promise(function (resolve) {
      if (!s || s.finished) { resolve(); } else { s.waiters.push(resolve); }
    });
  }

  function spAdd(s, text) {
    if (!s || s.finished || Sp.sess !== s) { return; }
    var t = cleanSpeech(text);
    if (!t) { return; }
    s.queue.push(t);
    spPump(s);
  }

  function spEnd(s) {
    if (!s || s.finished || Sp.sess !== s) { return; }
    s.ended = true;
    spPump(s);
  }

  function spFinish(s) {
    if (Sp.sess !== s) { return; }
    Sp.sess = null;
    s.finished = true;
    for (var i = 0; i < s.timers.length; i++) { clearTimeout(s.timers[i]); }
    s.timers = [];
    if (S.phase === 'speaking' || S.phase === 'thinking') { setPhase('idle'); }
    settle(s);
  }

  function spPump(s) {
    if (Sp.sess !== s || s.busy || s.finished) { return; }
    var t = s.queue.shift();
    if (t === undefined) {
      if (s.ended) { spFinish(s); }
      return;
    }
    s.busy = true;
    if (!s.started) {
      s.started = true;
      setPhase('speaking');
    }
    speakOne(s, t, function () { s.busy = false; spPump(s); });
  }

  // Speaks one sentence, then calls cb. Never gets stuck: a timer ends it if the browser never says it is done.
  function speakOne(s, text, cb) {
    var settled = false;
    var est = estimateMs(text);

    function done() {
      if (settled) { return; }
      settled = true;
      cb();
    }
    function captionOnly() {
      // no voice: the mouth moves for about as long as it would take to say it
      addTimer(s, function () { if (Sp.sess === s) { done(); } }, est);
    }

    if (!V.ok) { captionOnly(); return; }

    function utter(voice, isRetry) {
      if (settled || Sp.sess !== s) { return; }
      var u;
      try { u = new window.SpeechSynthesisUtterance(text); } catch (e) { captionOnly(); return; }
      if (voice) { u.voice = voice; u.lang = voice.lang || 'en-US'; } else { u.lang = 'en-US'; }
      u.rate = S.rate;
      u.pitch = S.companion === 'him' ? 0.95 : 1.05;
      u.volume = S.volume;
      V.refs.push(u);                       // keep a reference, or Chromium may drop the end event
      if (V.refs.length > 12) { V.refs.shift(); }
      var failed = false, began = false;

      function fail(why) {
        if (failed || settled || Sp.sess !== s) { return; }
        failed = true;
        if (why === 'canceled' || why === 'interrupted') { done(); return; }
        if (why === 'not-allowed') { captionOnly(); return; }
        try { window.speechSynthesis.cancel(); } catch (e) { /* nothing */ }
        Sp.cancelAt = Date.now();
        if (voice && !voice.localService && !isRetry) {
          V.bad[voice.name] = true;         // an online voice that fails: use the best local one
          var local = pickVoice(S.companion, true);
          if (local) { utter(local, true); return; }
        }
        captionOnly();
      }

      u.onstart = function () { began = true; };
      u.onend = function () { began = true; if (!failed) { done(); } };
      u.onerror = function (ev) { fail(ev && ev.error ? ev.error : 'error'); };
      addTimer(s, function () { fail('timeout'); }, est * 2 + 2000);
      var wait = Math.max(0, Sp.cancelAt + 120 - Date.now());   // Chromium drops a speak() right after cancel()
      addTimer(s, function () {
        if (settled || failed || Sp.sess !== s) { return; }
        try {
          window.speechSynthesis.resume();
          window.speechSynthesis.speak(u);
        } catch (e) { fail('error'); return; }
        if (voice && !voice.localService) {   // an online voice that never starts: don't wait for the long timer
          addTimer(s, function () { if (!began) { fail('timeout'); } }, 2500);
        }
      }, wait);
    }

    whenVoices().then(function () {
      if (settled || Sp.sess !== s) { return; }
      if (!V.primed) {
        V.primed = true;
        try { window.speechSynthesis.cancel(); } catch (e) { /* nothing */ }
        Sp.cancelAt = Date.now();
      }
      if (!V.voices.length) { V.voices = getVoicesSafe(); }   // they may have arrived after the 1.5 s wait
      if (!V.voices.length) { captionOnly(); return; }
      utter(pickVoice(S.companion, false), false);
    });
  }

  // Shows the text as her caption, sets the mood, speaks it. Resolves when she is done (or was interrupted).
  function say(text, mood) {
    text = String(text == null ? '' : text).trim();
    var s = spStart();
    var p = waitSess(s);
    if (mood) { setMood(mood); }
    setCaption(text);
    var parts = splitSentences(text, true).sentences;
    for (var i = 0; i < parts.length; i++) { spAdd(s, parts[i]); }
    spEnd(s);
    return p;
  }

  // ---------------------------------------------------------------- screens
  var screens = {};
  function registerScreen(name, handlers) { screens[name] = handlers || {}; }

  function show(name, opts) {
    var prev = S.screen;
    if (prev && prev !== name && screens[prev] && screens[prev].leave) {
      try { screens[prev].leave(name); } catch (e) { log(e); }
    }
    S.screen = name;
    var root = $('scr');
    root.setAttribute('data-screen', name);
    root.classList.toggle('urgent', name === 'emergency');
    if (screens[name] && screens[name].enter) {
      try { screens[name].enter(opts || {}, prev); } catch (e) { log(e); }
    }
  }

  registerScreen('everyday', {});

  registerScreen('emergency', {
    enter: function () {
      S.emSeq++;
      S.lightPressed = false;
      S.helpAsked = false;
      clearTimeout(S.lightTimer);
      var b = $('lightBtn');
      b.textContent = 'I pressed my call light';
      b.removeAttribute('aria-pressed');
      setMood('alert');
    },
    leave: function () { clearTimeout(S.lightTimer); }
  });

  registerScreen('nokey', {
    enter: function (o) {
      setMood('sorry');
      if (o && o.quiet) { setCaption(MSG.nokey); } else { say(MSG.nokey, 'sorry'); }
    }
  });

  function leaveEmergency() {
    show(S.hasKey ? 'everyday' : 'nokey', { quiet: true });
  }

  // A mood from the server. 'alert' means an emergency; on the emergency screen only worried moods are allowed.
  function applyMood(m) {
    if (!m || !validMood(m)) { return; }
    if (m === 'alert') {
      if (S.screen !== 'emergency') { show('emergency'); }
    } else if (S.screen === 'emergency' && m !== 'concerned' && m !== 'sorry') {
      return;
    }
    setMood(m);
  }

  // ---------------------------------------------------------------- turns
  // Everything in flight (listening, the reply stream, speech) belongs to a turn. Starting a new turn stops the old one.
  function newTurn() {
    S.turn++;
    if (S.ctrl) { try { S.ctrl.abort(); } catch (e) { /* nothing */ } S.ctrl = null; }
    if (S.listenAbort) { try { S.listenAbort(); } catch (e) { log(e); } }
    spCancel();
    if (S.phase !== 'idle') { setPhase('idle'); }
    return S.turn;
  }

  // ---------------------------------------------------------------- listening
  function listenOnce() {
    var my = S.turn;
    return new Promise(function (resolve, reject) {
      var ended = false, started = false, pending = '', t0 = Date.now();
      var timer = null, hard = null, fails = 0, notRec = 0;
      S.listenReason = '';
      setPhase('listening');
      setCaption(MSG.listening);

      function cleanup() {
        ended = true;
        clearTimeout(timer);
        clearTimeout(hard);
        S.stopNow = null;
        S.listenAbort = null;
        setRing(0);
      }
      function finish(reason) {
        if (ended) { return; }
        if (!started) { pending = reason; return; }
        cleanup();
        S.listenReason = reason;
        setPhase('thinking');
        api('POST', '/api/listen/stop?raw=1', {}, { ms: 60000 }).then(function (j) {
          var heard = String((j && j.text) || '').trim();   // whatever was heard counts, even if the level never showed a voice,
          if (reason === 'silence' && SILENCE_NOISE.test(heard)) { heard = ''; }   // except what Whisper invents in a quiet room
          resolve(heard);
        }).catch(function (e) { e.stage = 'stop'; reject(e); });
      }
      function poll() {
        if (ended || my !== S.turn) { return; }
        api('GET', '/api/listen/level', null, { ms: 4000 }).then(function (l) {
          if (ended || my !== S.turn) { return; }
          fails = 0;
          l = l || {};
          setRing(l.level);
          var elapsed = Number(l.elapsed_s) || 0;
          notRec = (l.recording === false) ? notRec + 1 : 0;
          if (l.heard_voice && Number(l.quiet_s) >= 1.4) { finish('quiet'); return; }
          if (!l.heard_voice && elapsed >= 8) { finish('silence'); return; }
          if (elapsed >= 60) { finish('cap'); return; }
          if (notRec >= 3) { finish('quiet'); return; }
          timer = setTimeout(poll, 150);
        }).catch(function () {
          if (ended || my !== S.turn) { return; }
          fails++;
          if (fails >= 5) { finish('tap'); return; }
          timer = setTimeout(poll, 300);
        });
      }

      S.stopNow = function () {
        if (!started || Date.now() - t0 < MIN_LISTEN_MS) { return; }   // double tap while the mic opens
        finish('tap');
      };
      S.listenAbort = function () {
        if (ended) { return; }
        cleanup();
        api('POST', '/api/listen/stop?raw=1', {}, { ms: 60000 }).catch(noop);
        var e = new Error('cancelled');
        e.cancelled = true;
        reject(e);
      };

      api('POST', '/api/listen/start', {}, { ms: 15000 }).then(function () {
        started = true;
        t0 = Date.now();
        if (ended) { api('POST', '/api/listen/stop?raw=1', {}, { ms: 60000 }).catch(noop); return; }
        if (pending) { finish(pending); return; }
        hard = setTimeout(function () { finish('cap'); }, 60000);
        poll();
      }).catch(function (e) {
        if (ended) { return; }
        cleanup();
        e.stage = 'start';
        reject(e);
      });
    });
  }

  function kindMessage(m) {
    m = String(m || '').trim();
    if (!m || m.length > 160 || /traceback|exception|errno|http \d|^something went wrong/i.test(m)) { return "I can't hear you right now."; }
    if (!/[.!?]$/.test(m)) { m += '.'; }
    return m;
  }

  function onTalkTap() {
    App.onActivity();
    if (S.phase === 'thinking') { return; }
    if (S.phase === 'listening') { if (S.stopNow) { S.stopNow(); } return; }
    if (S.typingOnly) { openTyping(); return; }
    beginListening();
  }

  function beginListening() {
    var my = newTurn();
    return listenOnce().then(function (text) {
      if (my !== S.turn) { return undefined; }
      if (!text) { return say(S.listenReason === 'silence' ? MSG.silence : MSG.notCaught, 'talking'); }
      return talkTo(text);
    }).catch(function (e) {
      if ((e && e.cancelled) || my !== S.turn) { return undefined; }
      log(e);
      if (e && (e.stage === 'start' || (e.stage === 'stop' && e.serverMessage))) {
        setPhase('idle');
        openTyping();
        return say("I'm sorry. " + kindMessage(e.serverMessage) + " You can type to me instead.", 'sorry');
      }
      if (e && e.stage === 'stop' && e.name === 'AbortError') {      // the first stop waits for the voice model to load
        setPhase('idle');
        return say(MSG.waking, 'sorry');
      }
      return say(MSG.notCaught, 'talking');
    });
  }

  // ---------------------------------------------------------------- the talk pipeline
  function alive(T) { return T.turn === S.turn && !T.dead; }

  function onPiece(piece, T) {
    T.streamed += piece;
    T.rest += piece;
    setCaption(T.streamed.replace(/^\s+/, ''));
    var r = splitSentences(T.rest, false);
    T.rest = r.rest;
    if (r.sentences.length) {
      if (!T.sess) { T.sess = spStart(); }
      for (var i = 0; i < r.sentences.length; i++) { spAdd(T.sess, r.sentences[i]); }
    }
  }

  // One NDJSON line. Returns the final object when the line is the last one.
  function handleLine(line, T) {
    var o;
    try { o = JSON.parse(line); } catch (e) { return null; }
    if (!o || typeof o !== 'object') { return null; }
    T.gotLine = true;
    if (o.done) { return o; }
    if (o.error) {
      if (T.streamed) { return { done: true, text: T.streamed, mood: T.mood }; }     // she already said part of it: keep that
      return { done: true, error: String(o.error), text: '' };
    }
    if (o.mood) { T.mood = String(o.mood); applyMood(T.mood); }
    if (typeof o.text === 'string' && o.text) { onPiece(o.text, T); }
    return null;
  }

  async function streamReply(text, T, ctrl) {
    var init = {
      method: 'POST',
      cache: 'no-store',
      headers: { 'X-Tracker': '1', 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text })
    };
    if (ctrl) { init.signal = ctrl.signal; }
    var resp = await fetch('/api/mary/talk?stream=1', init);
    T.gotResponse = true;
    if (!alive(T)) { return null; }
    if (!resp.ok) {
      var bad = {};
      try { bad = await resp.json(); } catch (e) { bad = {}; }
      return { done: true, error: (bad && bad.error) ? String(bad.error) : ('HTTP ' + resp.status), text: '' };
    }
    var all = '', d = null;
    if (resp.body && typeof resp.body.getReader === 'function' && typeof TextDecoder === 'function') {
      var reader = resp.body.getReader();
      var dec = new TextDecoder('utf-8');
      var buf = '';
      while (true) {
        var r = await reader.read();
        if (!alive(T)) { try { reader.cancel(); } catch (e) { /* nothing */ } return null; }
        if (r.done) { break; }
        var chunk = dec.decode(r.value, { stream: true });
        all += chunk;
        buf += chunk;
        var idx;
        while ((idx = buf.indexOf('\n')) >= 0) {
          var line = buf.slice(0, idx).trim();
          buf = buf.slice(idx + 1);
          if (line) { d = handleLine(line, T); if (d) { try { reader.cancel(); } catch (e) { /* nothing */ } return d; } }
        }
      }
      buf += dec.decode();
      if (buf.trim()) { d = handleLine(buf.trim(), T); if (d) { return d; } }
    } else {
      all = await resp.text();
      var lines = all.split('\n');
      for (var i = 0; i < lines.length; i++) {
        var ln = lines[i].trim();
        if (ln) { d = handleLine(ln, T); if (d) { return d; } }
      }
    }
    if (!T.gotLine && all.trim()) {            // one plain JSON answer instead of lines
      try { d = JSON.parse(all); } catch (e) { d = null; }
      if (d && typeof d === 'object') { T.gotLine = true; return d; }
    }
    if (T.streamed) { return { done: true, text: T.streamed, mood: T.mood }; }       // the stream stopped early: keep what arrived
    return null;
  }

  async function plainReply(text, ctrl) {
    return await api('POST', '/api/mary/talk', { text: text }, { signal: ctrl ? ctrl.signal : undefined, ms: 30000 });
  }

  async function replyFailed() {
    await say(MSG.sorry, 'sorry');
  }

  async function finishReply(d, T) {
    if (d.mood) { applyMood(String(d.mood)); }
    if (d.emergency && S.screen !== 'emergency') { show('emergency'); }
    if (d.needs_key && !d.emergency) {
      spCancel();
      S.hasKey = false;
      show('nokey');
      return;
    }
    if (d.logged) { showChip(); }

    var full = String(d.text == null ? '' : d.text);
    if (!T.streamed) {
      T.rest = full;
    } else if (full.indexOf(T.streamed) === 0) {
      T.rest += full.slice(T.streamed.length);
    }
    var caption = (full || T.streamed).replace(/^\s+/, '');

    if (!caption.trim()) {
      if (d.emergency) { await say(MSG.emergency, 'alert'); return; }
      await replyFailed();
      return;
    }
    if (d.error && !d.emergency && !d.bad_key && !full.trim()) { await replyFailed(); return; }
    // A key Gemini refused: her own "my key isn't working" line is the caption, not the generic sorry.
    if (d.error && !d.emergency && (d.bad_key || !d.mood)) { setMood('sorry'); }

    setCaption(caption);
    var tail = splitSentences(T.rest, true).sentences;
    if (!T.sess) { T.sess = spStart(); }
    for (var i = 0; i < tail.length; i++) { spAdd(T.sess, tail[i]); }
    spEnd(T.sess);
    await waitSess(T.sess);
  }

  // Sends what the resident said (spoken or typed) to Mary and speaks her answer as it arrives.
  async function talkTo(text) {
    text = String(text == null ? '' : text).trim();
    if (!text) { return; }
    App.onActivity();
    var turn = newTurn();
    closeMenu();
    closeTyping(false);
    setCaption('You said: ' + text, 'said');
    setPhase('thinking');

    var T = { turn: turn, streamed: '', rest: '', mood: '', sess: null, gotLine: false, gotResponse: false, dead: false };
    var ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
    S.ctrl = ctrl;
    var timer = null;
    var timeoutP = new Promise(function (resolve, reject) {
      timer = setTimeout(function () {
        T.dead = true;
        if (ctrl) { try { ctrl.abort(); } catch (e) { /* nothing */ } }
        reject(new Error('timeout'));
      }, 30000);
    });

    try {
      var d = null;
      try {
        d = await Promise.race([streamReply(text, T, ctrl), timeoutP]);
      } catch (e) {
        if (!alive(T)) { throw e; }
        if (T.gotResponse || T.gotLine) { throw e; }
        d = await Promise.race([plainReply(text, ctrl), timeoutP]);      // streaming failed before any answer came
      }
      clearTimeout(timer);
      if (turn !== S.turn) { return; }
      if (!d) { throw new Error('no answer'); }
      await finishReply(d, T);
    } catch (e) {
      clearTimeout(timer);
      T.dead = true;
      if (turn !== S.turn) { return; }
      log(e);
      try { await replyFailed(); } catch (e2) { log(e2); }
    } finally {
      clearTimeout(timer);
      if (turn === S.turn && S.phase === 'thinking') { setPhase('idle'); }
    }
  }

  // ---------------------------------------------------------------- menu and typing
  function openMenu() {
    refreshLabels();
    $('closeBtn').hidden = !(window.pywebview && window.pywebview.api && typeof window.pywebview.api.close_window === 'function');
    $('menu').hidden = false;
    try { $('menu').querySelector('button').focus(); } catch (e) { /* nothing */ }
  }
  function closeMenu() { $('menu').hidden = true; }

  function openTyping() {
    closeMenu();
    newTurn();
    $('typing').hidden = false;
    var t = $('typeText');
    t.value = '';
    setTimeout(function () { try { t.focus(); } catch (e) { /* nothing */ } }, 30);
  }
  function closeTyping(refocus) {
    $('typing').hidden = true;
    if (refocus) { try { $('talkBtn').focus(); } catch (e) { /* nothing */ } }
  }
  function submitTyping() {
    var t = $('typeText');
    var v = t.value.trim();
    if (!v) { try { t.focus(); } catch (e) { /* nothing */ } return; }
    closeTyping(true);
    talkTo(v);
  }

  function adjust(kind, delta) {
    var isRate = kind === 'rate';
    var lo = isRate ? RATE_MIN : VOL_MIN, hi = isRate ? RATE_MAX : VOL_MAX;
    var cur = isRate ? S.rate : S.volume;
    var next = Math.round(Math.max(lo, Math.min(hi, cur + delta)) * 100) / 100;
    newTurn();
    if (next === cur) {
      say(isRate
        ? (delta < 0 ? "I'm already as slow as I can go." : "I'm already as fast as I can go.")
        : (delta < 0 ? "I'm already as quiet as I can be." : "I'm already as loud as I can be. You can turn up the computer's sound too."));
      return;
    }
    if (isRate) { S.rate = next; } else { S.volume = next; }
    var body = {};
    body[isRate ? 'voice_rate' : 'voice_volume'] = next;
    api('PUT', '/api/settings', body).catch(noop);
    say(MSG.better);
  }

  function setCompanion(c, opts) {
    if (c !== 'mary' && c !== 'him') { c = 'mary'; }
    S.companion = c;
    try { face.setCompanion(c); } catch (e) { log(e); }
    applyLook(c);
    refreshLabels();
    if (!(opts && opts.noSave)) { api('PUT', '/api/settings', { companion: c }).catch(noop); }
  }

  function switchCompanion() {
    var c = S.companion === 'mary' ? 'him' : 'mary';
    newTurn();
    setCompanion(c);
    var n = companionName(c);
    say("Hi, I'm " + n + ". It's " + (c === 'mary' ? 'so ' : '') + 'nice to meet you.', 'happy');
    try { face.bounce(); } catch (e) { /* nothing */ }
  }

  function onMenuClick(ev) {
    var t = ev.target;
    if (t === $('menu')) { closeMenu(); return; }
    while (t && t !== $('menu') && !(t.getAttribute && t.getAttribute('data-act'))) { t = t.parentNode; }
    if (!t || t === $('menu')) { return; }
    var act = t.getAttribute('data-act');
    closeMenu();
    if (act === 'slower') { adjust('rate', -0.08); }
    else if (act === 'faster') { adjust('rate', 0.08); }
    else if (act === 'quieter') { adjust('volume', -0.1); }
    else if (act === 'louder') { adjust('volume', 0.1); }
    else if (act === 'switch') { switchCompanion(); }
    else if (act === 'type') { openTyping(); }
    else if (act === 'notes') { window.location.href = '/'; }
    else if (act === 'close') {
      try { window.pywebview.api.close_window(); } catch (e) { log(e); }
    }
  }

  // ---------------------------------------------------------------- emergency buttons
  function onLightPressed() {
    if (S.lightPressed) { return; }
    S.lightPressed = true;
    var b = $('lightBtn');
    b.textContent = '✓ Call light pressed';
    b.setAttribute('aria-pressed', 'true');
    newTurn();
    say(MSG.light, 'concerned');
    clearTimeout(S.lightTimer);
    var seq = S.emSeq;
    function askHelp() {
      if (S.screen !== 'emergency' || S.emSeq !== seq || S.helpAsked) { return; }
      if (S.phase === 'listening' || S.phase === 'thinking') {     // never talk over the resident: ask again shortly
        S.lightTimer = setTimeout(askHelp, 5000);
        return;
      }
      S.helpAsked = true;
      say(MSG.helpAsk, 'concerned');
    }
    S.lightTimer = setTimeout(askHelp, 180000);
  }

  function onOkNow() {
    var seq = S.emSeq;
    clearTimeout(S.lightTimer);
    newTurn();
    say(MSG.okNow, 'happy').then(function () {
      if (S.screen === 'emergency' && S.emSeq === seq) { leaveEmergency(); }
    });
  }

  // ---------------------------------------------------------------- loading
  function clampNum(v, lo, hi, dflt) {
    v = Number(v);
    if (!isFinite(v)) { return dflt; }
    return Math.max(lo, Math.min(hi, v));
  }

  function applyStatus(st) {
    if (!st || typeof st !== 'object') { return; }
    S.statusLoaded = true;
    if (st.companions && typeof st.companions === 'object') {
      if (st.companions.mary) { S.names.mary = String(st.companions.mary); }
      if (st.companions.him) { S.names.him = String(st.companions.him); }
    }
    S.hasKey = !!st.has_key;
    S.firstRun = !!st.first_run;
    S.name = st.name ? String(st.name) : '';
    S.rate = clampNum(st.voice_rate, RATE_MIN, RATE_MAX, S.rate);
    S.volume = clampNum(st.voice_volume, VOL_MIN, VOL_MAX, S.volume);
    var c = st.companion === 'him' ? 'him' : 'mary';
    if (c !== S.companion) { setCompanion(c, { noSave: true }); } else { applyLook(c); refreshLabels(); }
  }

  function refreshStatus() {
    return api('GET', '/api/mary/status').then(function (st) { applyStatus(st); return st; });
  }

  function checkListen() {
    return api('GET', '/api/listen').then(function (l) {
      l = l || {};
      S.typingOnly = (l.available === false && !l.loading);
      updateTalkButton();
      return l;
    }).catch(function () { return null; });
  }

  // The normal start: the no-key screen if she has no key yet, otherwise the everyday screen.
  function enterMain() {
    if (!S.hasKey && S.statusLoaded) {
      show('nokey');
      return;
    }
    show('everyday');
    setCaption(S.typingOnly ? MSG.tapToType : MSG.tapToTalk);
  }

  // ===== T4b: replace this stub with the first-run screens (Choose your companion, First hello).
  // When they are finished, call MaryApp.enterMain(). For now: straight to the everyday screen with Mary.
  function startFirstRun() {
    setCompanion('mary', { noSave: true });
    App.enterMain();
  }
  // ===== end of T4b hook

  function retryStatusLater(tries) {
    if (tries <= 0) { return; }
    setTimeout(function () {
      refreshStatus().then(function () {
        if (S.screen === 'everyday' && S.phase === 'idle') {
          if (S.firstRun) { App.startFirstRun(); } else { App.enterMain(); }
        }
      }).catch(function () { retryStatusLater(tries - 1); });
    }, 5000);
  }

  async function init() {
    face = makeFace('mary');
    applyLook('mary');
    bind();
    setPhase('idle');
    refreshLabels();
    show('everyday');

    var pStatus = refreshStatus().catch(function () { return null; });
    var pListen = checkListen();
    var st = await pStatus;
    if (!st) {
      try { st = await refreshStatus(); } catch (e) { st = null; }
    }
    // The mic check can be slow on a cold laptop: wait 3 s at most, and let a late answer update the button.
    await Promise.race([pListen, new Promise(function (r) { setTimeout(r, 3000); })]);
    pListen.then(function () {
      if (S.typingOnly && S.phase === 'idle' && $('caption').textContent === MSG.tapToTalk) { setCaption(MSG.tapToType); }
    });

    if (!st) {
      show('everyday');
      setCaption(MSG.loading);
      retryStatusLater(6);
      return;
    }
    if (S.firstRun) { App.startFirstRun(); } else { App.enterMain(); }
  }

  function bind() {
    $('talkBtn').addEventListener('click', onTalkTap);
    $('moreBtn').addEventListener('click', openMenu);
    $('menu').addEventListener('click', onMenuClick);
    $('lightBtn').addEventListener('click', onLightPressed);
    $('okBtn').addEventListener('click', onOkNow);
    $('infoBtn').addEventListener('click', function () { window.location.href = '/#info'; });
    $('typeForm').addEventListener('submit', function (ev) { ev.preventDefault(); submitTyping(); });
    $('typeCancel').addEventListener('click', function () { closeTyping(true); });
    $('typeText').addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); submitTyping(); }
    });
    D.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Escape') { return; }
      if (!$('menu').hidden) { closeMenu(); }
      else if (!$('typing').hidden) { closeTyping(true); }
    });
    window.addEventListener('pagehide', function () {
      try { if (S.listenAbort) { S.listenAbort(); } } catch (e) { /* nothing */ }
      spCancel();
    });
    window.addEventListener('unhandledrejection', function (ev) { log(ev && ev.reason); });
    if (V.ok) { whenVoices(); }
  }

  var App = window.MaryApp = {
    state: S,
    show: show,
    registerScreen: registerScreen,
    say: say,
    talkTo: talkTo,
    listenOnce: listenOnce,
    setCompanion: setCompanion,
    setCaption: setCaption,
    setMood: setMood,
    setPhase: setPhase,
    newTurn: newTurn,
    cancelSpeech: spCancel,
    openTyping: openTyping,
    refreshStatus: refreshStatus,
    enterMain: enterMain,
    startFirstRun: startFirstRun,
    onActivity: noop,                        // firstrun.js replaces it: a talk started, wake her if she is sleepy
    companionName: companionName,
    api: api,
    getFace: function () { return face; }
  };

  if (D.readyState === 'loading') {
    D.addEventListener('DOMContentLoaded', function () { init().catch(log); });
  } else {
    init().catch(log);
  }
})();
