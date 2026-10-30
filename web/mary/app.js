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

   M4a: MaryApp.startTalk() opens a hands-free conversation in the first working talk mode (Live, Normal, Offline,
   then the computer's own voice); MaryApp.endTalk(), MaryApp.inTalk(). listenReason can also be 'idle'.

   No ?. or ?? here, so the ES2017 syntax checker parses it. */
(function () {
  'use strict';

  var D = document;
  function $(id) { return D.getElementById(id); }
  function noop() {}
  function log(e) { try { console.error(e); } catch (x) { /* nothing */ } }

  var RATE_MIN = 0.6, RATE_MAX = 1.4, VOL_MIN = 0.2, VOL_MAX = 1.0;
  var MIN_LISTEN_MS = 800;       // a second tap this soon after the mic opens is a double tap, not "I'm done"
  var QUIET_END_S = 2.5;         // quiet after speech that ends a turn; 1.4 s cut Andy off mid-thought (2026-10-30)
  var SILENCE_NOISE = /^\W*(?:you|thank you|thanks|thank you for watching|thanks for watching|bye|okay|ok|so|um+|uh+)?\W*$/i;

  // --- M4a: hands-free conversations and talk modes (Live, Normal, Offline; the computer's own voice last) ---
  // QUIET_END_S above follows the saved listen_wait (status and settings effects).
  var CONVO_IDLE_S = 15;         // a conversation ends after this much quiet: nobody talking, she isn't speaking
  var BYE_MAX_WORDS = 6;         // a goodbye is a short turn; a long story that says "goodbye" is not one
  var BYE_RE = /\b(?:good[\s-]?bye|bye now|bye[\s-]bye|that['’]?s all for now|talk to you later|good[\s-]?night|see you later)\b/i;
  var LIVE_BYE_MAX_MS = 8000;    // after the goodbye is asked for, Live closes once her turn ends, or after this
  var LIVE_HELLO = '(The resident just tapped Talk. Say a short, warm hello in one sentence, using their name if you know it.)';
  var LIVE_BYE = '(The conversation is ending now. Say a short, warm goodbye in one sentence and remind them they can tap Talk any time.)';
  var LIVE_SWITCHED = '(The resident just switched to you. Say a short, warm hello in one sentence, using their name if you know it.)';
  var LIVE_SAFETY = '(Safety first. The resident may be in an emergency. Say this to them right now, warmly and plainly, then stay with them: ';
  // --- end M4a ---

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
    loading: "I'm getting ready. Just a moment.",
    fallback: "My best voice isn't working right now, so I'll keep talking with you the usual way.",   // M4a
    goodbye: "It was so nice talking with you. Tap Talk any time you want to chat again."              // M4a
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
    chipTimer: null,
    // M4a: talk modes and the open conversation
    talkMode: 'live',            // the saved choice
    talkOrder: [],               // the modes the server says will work, best first ([] = the computer's own voice)
    voiceMode: '',               // the voice for spoken sentences now: 'normal' | 'offline' | '' (speechSynthesis)
    fallbackSaid: false,         // the "my best voice isn't working" line, once per conversation
    convo: null                  // the open conversation (startTalk), or null
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

  // M4a: her own words (Live captions, her replies, say()). M4b replaces this with bubble letters.
  function showCaption(text) { setCaption(text); }

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
    else if (S.convo && !S.convo.paused) { ic = 'done'; text = "I'm done"; }   // M4a: a tap ends the conversation
    else if (S.typingOnly && !liveFirst()) { ic = 'type'; text = 'Type to ' + n; }   // M4a: Live has its own mic
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
    try { if (window.MaryVoice) { window.MaryVoice.cancel(); } } catch (e) { log(e); }   // M4a: her picked voice too
    if (V.ok) {
      try { window.speechSynthesis.cancel(); } catch (e) { /* nothing */ }
      Sp.cancelAt = Date.now();
    }
  }

  function spStart() {
    spCancel();
    var s = { queue: [], busy: false, ended: false, started: false, finished: false, waiters: [], timers: [],
      voice: speechVoice(), mvJob: null, mvSent: [], mvEnded: false };   // M4a: her picked voice, when it works
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
    if (S.phase === 'speaking' || S.phase === 'thinking') { setPhase(restPhase()); }   // M4a: Live goes back to listening
    settle(s);
  }

  // --- M4a: her picked voice (voiceout.js) for Normal and Offline; speechSynthesis stays the last resort ---
  function speechVoice() {
    var m = S.voiceMode;
    var ok = window.MaryVoice && typeof window.MaryVoice.more === 'function';
    return (ok && (m === 'normal' || m === 'offline')) ? m : '';
  }
  // The voice after `from` in the talk order (Live is never a voice for sentences); '' = the computer's own voice.
  function nextVoice(from) {
    var m = nextMode(S.talkOrder, from);
    while (m === 'live') { m = nextMode(S.talkOrder, m); }
    return (m === 'normal' || m === 'offline') ? m : '';
  }
  // One open MaryVoice job per session: each sentence is fetched as soon as it is added, so there are no gaps.
  function mvPump(s) {
    if (s.queue.length) {
      var batch = s.queue.splice(0, s.queue.length);
      if (!s.started) { s.started = true; setPhase('speaking'); }
      if (!s.mvJob) {
        var job = {}, p;
        s.mvJob = job;
        s.mvSent = batch.slice();
        s.mvEnded = false;
        try {
          p = window.MaryVoice.queue(batch, { mode: s.voice, rate: S.rate, volume: S.volume, open: true });
        } catch (e) { log(e); p = null; }
        Promise.resolve(p || { ok: false, kind: 'failed', at: 0 }).then(function (r) { mvDone(s, job, r); },
          function (e) { log(e); mvDone(s, job, { ok: false, kind: 'failed', at: 0 }); });
      } else {
        for (var i = 0; i < batch.length; i++) {
          s.mvSent.push(batch[i]);
          try { window.MaryVoice.more(batch[i]); } catch (e) { log(e); }
        }
      }
    }
    if (s.ended && !s.mvEnded) {
      if (!s.mvJob) { spFinish(s); return; }
      s.mvEnded = true;
      try { window.MaryVoice.end(); } catch (e) { log(e); }
    }
  }
  // The job is over. On a failure, what was not said goes to the next voice (offline, then the computer's own),
  // with one kind line per conversation; at 0 (no sound at all) that voice is dropped for the rest of the talk.
  function mvDone(s, job, r) {
    if (Sp.sess !== s || s.finished || s.mvJob !== job) { return; }
    s.mvJob = null;
    r = r || {};
    if (r.ok) { spFinish(s); return; }
    var at = Math.max(0, Math.floor(Number(r.at) || 0));
    var rest = s.mvSent.slice(at);
    var from = s.voice;
    log(new Error('Her voice (' + from + ') failed at sentence ' + at + (r.bad_key ? ', bad key' : r.no_key ? ', no key' : '')));
    s.voice = nextVoice(from);
    if (at === 0 && S.voiceMode === from) { S.voiceMode = s.voice; }
    if (!S.fallbackSaid) { S.fallbackSaid = true; rest.unshift(MSG.fallback); }
    s.mvSent = [];
    s.mvEnded = false;
    s.queue = rest.concat(s.queue);
    spPump(s);
  }
  // --- end M4a ---

  function spPump(s) {
    if (Sp.sess !== s || s.busy || s.finished) { return; }
    if (s.voice) { mvPump(s); return; }   // M4a
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
    if (liveOn()) { try { window.MaryLive.stopSpeaking(); } catch (e) { log(e); } }   // M4a: never two voices at once
    var s = spStart();
    var p = waitSess(s);
    if (mood) { setMood(mood); }
    showCaption(text);   // M4a
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
    leave: function () {
      clearTimeout(S.lightTimer);
      setTimeout(convoAfterEmergency, 0);   // M4a: the paused conversation goes on
    }
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
    var rest = restPhase();   // M4a: an open Live talk rests in listening
    if (S.phase !== rest) { setPhase(rest); }
    return S.turn;
  }

  // ---------------------------------------------------------------- listening
  // M4a: listenOnce({convo: true}) is a conversation's listen: no voice for CONVO_IDLE_S finishes it as 'idle'.
  function listenOnce(opts) {
    var convo = !!(opts && opts.convo);   // M4a
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
          if ((reason === 'silence' || reason === 'idle') && SILENCE_NOISE.test(heard)) { heard = ''; }   // except what Whisper invents in a quiet room (M4a: idle too)
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
          if (l.heard_voice && Number(l.quiet_s) >= QUIET_END_S) { finish('quiet'); return; }
          if (!l.heard_voice && elapsed >= (convo ? CONVO_IDLE_S : 8)) { finish(convo ? 'idle' : 'silence'); return; }   // M4a
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
    var c = S.convo;   // M4a: one tap starts a conversation; in one, a tap while listening is "I'm done" (Normal/Offline)
    if (c) {
      if (c.paused) { c.paused = false; convoListen(c); return; }
      if (!c.live && S.phase === 'listening') { if (S.stopNow) { S.stopNow(); } return; }
      if (c.ending) { if (c.live) { finishLive(c); } return; }
      endConvo(c, 'tap');
      return;
    }
    if (S.phase === 'listening') { if (S.stopNow) { S.stopNow(); } return; }
    startTalk();
  }

  // ---------------------------------------------------------------- M4a: conversations and talk modes
  // A conversation starts with one tap (or the wake word, M6, through MaryApp.startTalk) and stays open until about
  // CONVO_IDLE_S of quiet, a short goodbye, or a tap. Live = Gemini Live (talklive.js). Normal/Offline = the on-device
  // mic, /api/mary/talk, and her picked voice (voiceout.js). '' = the computer's own voice, the last resort.

  // The talk mode after `current` in the server's order ('' = the computer's own voice); no current = the first. Pure.
  function nextMode(order, current) {
    var list = [];
    if (order && order.length) { for (var i = 0; i < order.length; i++) { if (order[i]) { list.push(String(order[i])); } } }
    if (!current) { return list.length ? list[0] : ''; }
    var at = list.indexOf(current);
    if (at >= 0) { return at + 1 < list.length ? list[at + 1] : ''; }
    var rank = ['live', 'normal', 'offline'], r = rank.indexOf(current);
    for (var k = 0; k < list.length; k++) { if (rank.indexOf(list[k]) > r) { return list[k]; } }
    return '';
  }

  // What to do with Live's skill call, given the emergency check of what the resident just said. Pure.
  function liveToolGate(heardResult) {
    return (heardResult && heardResult.emergency) ? 'refuse' : 'run';
  }

  // A short goodbye turn ("bye now", "that's all for now"). Pure.
  function isGoodbye(text) {
    text = String(text == null ? '' : text).trim();
    if (!text) { return false; }
    return text.split(/\s+/).length <= BYE_MAX_WORDS && BYE_RE.test(text);
  }

  function liveSupported() {
    try { return !!(window.MaryLive && window.MaryLive.supported()); } catch (e) { return false; }
  }
  function liveFirst() { return S.talkOrder[0] === 'live' && liveSupported(); }
  function liveOn() {
    var c = S.convo;
    try { return !!(c && c.live && window.MaryLive.isOpen()); } catch (e) { return false; }
  }
  function liveSpeaking() {
    try { return !!(window.MaryLive && window.MaryLive.isSpeaking()); } catch (e) { return false; }
  }
  function greetLive(text) {
    try { return !!window.MaryLive.greet(text); } catch (e) { log(e); return false; }
  }
  function restPhase() {
    var c = S.convo;
    return (c && c.live && c.open && !c.ending) ? 'listening' : 'idle';
  }
  // The voice for spoken sentences in a mode: Live's lines outside a Live talk use Normal's (the same Gemini voice).
  function speechModeFor(m) {
    if (m === 'live') { m = nextMode(S.talkOrder, 'live'); }
    return (m === 'normal' || m === 'offline') ? m : '';
  }
  function sayFallbackOnce() {
    if (S.fallbackSaid) { return Promise.resolve(); }
    S.fallbackSaid = true;
    return say(MSG.fallback);
  }

  // The one way to start talking. Call it straight from a tap (Live opens the mic and sound there).
  // opts.hello: what Live is asked to say first. Resolves true when a conversation started.
  function startTalk(opts) {
    opts = opts || {};
    App.onActivity();
    if (S.convo || S.phase === 'thinking' || S.phase === 'listening') { return Promise.resolve(false); }
    var mode = nextMode(S.talkOrder, null);
    if (mode === 'live' && !liveSupported()) { mode = nextMode(S.talkOrder, 'live'); }
    if (mode !== 'live' && S.typingOnly) { openTyping(); return Promise.resolve(false); }
    var c = { mode: mode, live: false, open: false, ending: false, paused: false, seq: 0, lastAct: Date.now(),
      heard: '', heardCheck: null, toolBusy: 0, idleTimer: null, byeTimer: null, byeDone: false };
    S.convo = c;
    S.fallbackSaid = false;
    S.voiceMode = speechModeFor(mode);
    updateTalkButton();
    if (mode === 'live') { startLive(c, opts.hello || LIVE_HELLO); } else { convoListen(c); }
    return Promise.resolve(true);
  }

  function closeConvo(c) {
    if (!c) { return; }
    clearInterval(c.idleTimer);
    clearTimeout(c.byeTimer);
    c.ending = true;
    if (S.convo === c) { S.convo = null; }
    if (c.live) {
      c.live = false;
      c.open = false;
      try { window.MaryLive.stop('end'); } catch (e) { log(e); }
      if (!Sp.sess && (S.phase === 'listening' || S.phase === 'speaking')) { setPhase('idle'); }
    }
    updateTalkButton();
  }

  // Ends the conversation. why: 'tap' (at once, quietly), 'idle' or 'bye' (with a short goodbye).
  function endConvo(c, why) {
    if (!c || S.convo !== c || c.ending) { return; }
    if (why === 'tap') {
      closeConvo(c);
      newTurn();
      setPhase('idle');
      setCaption(S.typingOnly && !liveFirst() ? MSG.tapToType : MSG.tapToTalk);
      return;
    }
    if (c.live && c.open) {
      c.ending = true;
      c.byeDone = false;
      clearInterval(c.idleTimer);
      // to a spoken goodbye she is already answering with one; on quiet she is asked for one
      if (why === 'idle' && !greetLive(LIVE_BYE)) { finishLive(c); return; }
      c.byeTimer = setTimeout(function () { liveByeCap(c, false); }, LIVE_BYE_MAX_MS);
      return;
    }
    closeConvo(c);
    newTurn();
    say(MSG.goodbye, 'happy');
  }

  // --- Live ---
  function startLive(c, hello) {
    var seq = ++c.seq;
    c.live = true;
    c.open = false;
    try { if (window.MaryVoice) { window.MaryVoice.cancel(); } } catch (e) { log(e); }
    newTurn();
    setPhase('thinking');
    function mine() { return S.convo === c && c.seq === seq && c.live; }
    var p;
    try {
      p = window.MaryLive.start({
        screen: skillScreen(),
        onCaption: function (t) { if (mine()) { c.lastAct = Date.now(); showCaption(t); } },
        onHeard: function (t) { if (mine()) { c.lastAct = Date.now(); setCaption('You said: ' + t, 'said'); } },
        onHeardDone: function (t) { if (mine()) { liveHeard(c, t); } },
        onSpeaking: function (on) { if (mine()) { liveSpeakingChanged(c, on); } },
        onInterrupted: function () { if (mine()) { c.lastAct = Date.now(); } },
        onTurnComplete: function () { if (mine()) { liveTurnDone(c); } },
        onToolCall: function (tc) { return liveToolCall(c, tc); },
        onActivity: function () { if (mine()) { c.lastAct = Date.now(); } },
        onEnd: function (why, detail) { if (mine()) { liveDropped(c, why, detail); } }
      });
    } catch (e) { p = Promise.reject(e); }
    Promise.resolve(p).then(function () {
      if (!mine()) { return; }          // ended or restarted while it was opening
      c.open = true;
      c.lastAct = Date.now();
      try { window.MaryLive.setVolume(S.volume); } catch (e) { log(e); }
      setPhase('listening');
      setCaption(MSG.listening);
      greetLive(hello);
      clearInterval(c.idleTimer);
      c.idleTimer = setInterval(function () { liveIdleCheck(c); }, 1000);
    }, function (err) {
      if (mine()) { liveFailed(c, err); }
    });
  }

  function liveFailed(c, err) {
    var kind = (err && err.kind) || '';
    c.live = false;
    c.open = false;
    if (kind === 'stopped') { closeConvo(c); setPhase('idle'); return; }
    if (kind === 'mic_denied' || kind === 'no_mic') {   // no other mode would hear them either: say so, offer typing
      closeConvo(c);
      setPhase('idle');
      openTyping();
      say("I'm sorry. " + kindMessage(err && err.message) + ' You can type to me instead.', 'sorry');
      return;
    }
    log(err);
    liveFallback(c);
  }

  // Live would not start or dropped: the next mode in the order, with one kind line, and the talk goes on.
  function liveFallback(c) {
    c.live = false;
    c.open = false;
    clearInterval(c.idleTimer);
    clearTimeout(c.byeTimer);
    c.mode = nextMode(S.talkOrder, 'live');
    S.voiceMode = speechModeFor(c.mode);
    newTurn();
    setPhase('idle');
    if (c.ending) { closeConvo(c); return; }
    sayFallbackOnce().then(function () {
      if (S.convo !== c) { return; }
      if (S.typingOnly) { closeConvo(c); openTyping(); return; }
      convoNext(c);
    });
  }

  function liveDropped(c, why, detail) {
    log(new Error('Live ended: ' + why + (detail && detail.note ? ' (' + detail.note + ')' : '')));
    if (c.ending) { finishLive(c); return; }
    liveFallback(c);
  }

  function liveSpeakingChanged(c, on) {
    c.lastAct = Date.now();
    if (on) {
      setPhase('speaking');
      applyMood('talking');
      return;
    }
    if (S.phase === 'speaking' && !Sp.sess) { setPhase(restPhase()); }
    if (c.ending && c.byeDone) { finishLive(c); }
  }

  function liveTurnDone(c) {
    c.lastAct = Date.now();
    if (!c.ending) { return; }
    c.byeDone = true;                       // her goodbye turn is complete: close once it has been heard
    if (!liveSpeaking()) { finishLive(c); }
  }

  function liveByeCap(c, extended) {
    if (S.convo !== c) { return; }
    if (!extended && liveSpeaking()) { c.byeTimer = setTimeout(function () { liveByeCap(c, true); }, 6000); return; }
    finishLive(c);
  }

  function finishLive(c) {
    if (S.convo !== c) { return; }
    closeConvo(c);
    if (!Sp.sess && S.phase !== 'thinking') { setPhase('idle'); }
  }

  function liveIdleCheck(c) {
    if (S.convo !== c || !c.live) { clearInterval(c.idleTimer); return; }
    if (c.ending || !c.open) { return; }
    var now = Date.now();
    if (S.screen === 'emergency' || liveSpeaking() || Sp.sess || c.toolBusy > 0 || !$('menu').hidden) { c.lastAct = now; return; }
    if (now - c.lastAct >= CONVO_IDLE_S * 1000) { endConvo(c, 'idle'); }
  }

  // Every finished thing the resident says in Live gets the same emergency check as Normal talk (never missed),
  // then the goodbye check. The promise is kept: skills wait for it.
  function liveHeard(c, text) {
    text = String(text == null ? '' : text).trim();
    c.heard = text;
    c.lastAct = Date.now();
    var p = api('POST', '/api/mary/heard', { text: text }, { ms: 8000 }).then(function (j) {
      return j || {};
    }, function (e) {
      log(e);                               // tools still run; the server's skills gate checks again
      return null;
    });
    c.heardCheck = p;
    p.then(function (j) {
      if (j && j.emergency) {
        if (S.convo === c && c.live) { liveEmergency(c, j); return; }
        newTurn();                                                // Live closed meanwhile: never miss it anyway
        if (S.screen !== 'emergency') { show('emergency'); }
        say((j && j.say) ? String(j.say) : MSG.emergency, 'alert');
        return;
      }
      if (S.convo !== c || !c.live) { return; }
      if (isGoodbye(text)) { endConvo(c, 'bye'); }
    });
    return p;
  }

  function liveEmergency(c, j) {
    try { window.MaryLive.stopSpeaking(); } catch (e) { log(e); }
    var words = (j && j.say) ? String(j.say) : MSG.emergency;
    if (c.ending) {                         // no goodbye now: she stays with them
      c.ending = false;
      clearTimeout(c.byeTimer);
      clearInterval(c.idleTimer);
      c.idleTimer = setInterval(function () { liveIdleCheck(c); }, 1000);
    }
    c.lastAct = Date.now();
    if (S.screen !== 'emergency') { show('emergency'); }
    showCaption(words);
    if (!greetLive(LIVE_SAFETY + words + ')')) { say(words, 'alert'); }
  }

  function liveToolCall(c, tc) {
    var calls = (tc && tc.functionCalls) || [];
    var heard = c.heard || '';
    c.toolBusy++;
    return Promise.resolve(c.heardCheck).then(function (j) {
      if (liveToolGate(j) === 'refuse') {
        return { functionResponses: calls.map(function (fc) { return { id: fc.id, name: fc.name, response: { error: 'emergency' } }; }) };
      }
      if (!window.MarySkills) { throw new Error('skills are not loaded'); }
      return window.MarySkills.handleLiveToolCall(tc, heard);
    }).then(function (r) {
      c.toolBusy--;
      c.lastAct = Date.now();
      return r;
    }, function (e) {
      c.toolBusy--;
      c.lastAct = Date.now();
      log(e);
      throw e;
    });
  }

  // Typed words while Live is open go into the same talk, after the emergency check.
  function liveTyped(c, text) {
    setCaption('You said: ' + text, 'said');
    c.lastAct = Date.now();
    liveHeard(c, text).then(function (j) {
      if (S.convo !== c || (j && j.emergency)) { return; }
      if (!greetLive(text)) { closeConvo(c); talkTo(text); }   // the line closed: answer the usual way
    });
  }

  // A companion switch while Live is open: Live starts again in the new companion's own voice, once it is saved.
  function liveRestartAfter(saved) {
    var c = S.convo;
    if (!c || !c.live) { return; }
    Promise.resolve(saved).then(function () {
      setTimeout(function () {
        if (S.convo === c && c.live && !c.ending) { startLive(c, LIVE_SWITCHED); }
      }, 300);
    });
  }

  // --- Normal / Offline: listen, answer, listen again (never while she speaks) ---
  function convoListen(c) {
    if (S.convo !== c || c.ending || c.live) { return; }
    if (S.screen === 'emergency') { c.paused = true; setPhase('idle'); updateTalkButton(); return; }
    c.paused = false;
    var my = newTurn();
    listenOnce({ convo: true }).then(function (text) {
      if (S.convo !== c || my !== S.turn) { return undefined; }
      if (!text) {
        if (S.listenReason === 'idle') { endConvo(c, 'idle'); return undefined; }
        return say(MSG.notCaught, 'talking').then(function () { convoNext(c); });
      }
      if (isGoodbye(text)) { return convoBye(c, text); }
      return talkTo(text).then(function () { convoNext(c); });
    }).catch(function (e) {
      if (S.convo !== c) { return undefined; }
      if (e && e.cancelled) { convoNext(c); return undefined; }   // something else took the turn: go on after it
      closeConvo(c);
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

  // After her answer (or anything else that took the turn): listen again once she is quiet.
  function convoNext(c) {
    if (S.convo !== c || c.ending || c.live) { return; }
    if (S.screen === 'emergency') { c.paused = true; setPhase('idle'); updateTalkButton(); return; }   // no auto-listen there
    if ((S.screen !== 'everyday' && !skillScreen()) || !$('menu').hidden || !$('typing').hidden) { closeConvo(c); return; }
    if (S.phase !== 'idle' || Sp.sess) { setTimeout(function () { convoNext(c); }, 300); return; }
    convoListen(c);
  }

  // A short goodbye in Normal/Offline: the emergency check first (never missed), then her fixed goodbye.
  function convoBye(c, text) {
    setPhase('thinking');
    return api('POST', '/api/mary/heard', { text: text }, { ms: 8000 }).then(function (j) {
      return j || {};
    }, function (e) { log(e); return null; }).then(function (j) {
      if (S.convo !== c) { return undefined; }
      closeConvo(c);
      if (!j || j.emergency) { return talkTo(text); }   // the full talk path: the emergency screen and her words
      setPhase('idle');
      return say(MSG.goodbye, 'happy');
    });
  }

  function convoAfterEmergency() {
    var c = S.convo;
    if (!c || S.screen === 'emergency') { return; }
    c.lastAct = Date.now();
    if (c.paused && !c.live) { c.paused = false; convoNext(c); }
  }
  // ---------------------------------------------------------------- end M4a conversations

  // ---------------------------------------------------------------- the talk pipeline
  function alive(T) { return T.turn === S.turn && !T.dead; }

  function onPiece(piece, T) {
    T.streamed += piece;
    T.rest += piece;
    showCaption(T.streamed.replace(/^\s+/, ''));   // M4a
    var r = splitSentences(T.rest, false);
    T.rest = r.rest;
    if (r.sentences.length) {
      if (!T.sess) { T.sess = spStart(); }
      for (var i = 0; i < r.sentences.length; i++) { spAdd(T.sess, r.sentences[i]); }
    }
  }

  // --- skills hook (M13) --- effects from a skill go to skills.js; T.effects counts those already applied
  function applyEffect(effect, T) {
    if (T) { T.effects = (T.effects || 0) + 1; }
    try { if (window.MarySkills) { window.MarySkills.apply(effect); } } catch (e) { log(e); }
  }
  function skillScreen() {
    try { return (window.MarySkills && window.MarySkills.isSkillScreen(S.screen)) ? S.screen : undefined; } catch (e) { return undefined; }
  }
  function applySettings(values) {
    values = values || {};
    if (values.voice_rate != null) { S.rate = clampNum(values.voice_rate, RATE_MIN, RATE_MAX, S.rate); }
    if (values.voice_volume != null) { S.volume = clampNum(values.voice_volume, VOL_MIN, VOL_MAX, S.volume); }
    if (values.companion === 'mary' || values.companion === 'him') {
      if (values.companion !== S.companion) {
        setCompanion(values.companion, { noSave: true });   // M4a: an open Live talk starts again in the new voice
        try { face.bounce(); } catch (e) { /* nothing */ }
      }
    }
    // M4a: the quiet that ends a turn (Live uses it from the next talk), the talk mode, and Live's loudness
    if (values.listen_wait != null) { QUIET_END_S = clampNum(values.listen_wait, 1.5, 6, QUIET_END_S); }
    if (values.talk_mode != null || values.listen_wait != null) { refreshStatus().catch(log); }
    if (values.voice_volume != null && liveOn()) { try { window.MaryLive.setVolume(S.volume); } catch (e) { log(e); } }
  }
  // Runs a menu action through the voice_comfort skill; resolves true when the skill answered, false to fall back.
  async function skillMenu(action, mood) {
    try {
      if (!window.MarySkills) { return false; }
      var r = await window.MarySkills.call('voice_comfort__' + action, {});
      if (!r || !r.response || r.response.error || !r.say) { return false; }
      newTurn();
      if (action === 'switch_companion' && S.convo && S.convo.live) { return true; }   // M4a: Live restarts and greets
      say(r.say, mood);
      return true;
    } catch (e) { log(e); return false; }
  }
  // --- end skills hook ---

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
    if (o.effect) { applyEffect(o.effect, T); }   // --- skills hook (M13) ---
    if (o.mood) { T.mood = String(o.mood); applyMood(T.mood); }
    if (typeof o.text === 'string' && o.text) { onPiece(o.text, T); }
    return null;
  }

  async function streamReply(text, T, ctrl) {
    var init = {
      method: 'POST',
      cache: 'no-store',
      headers: { 'X-Tracker': '1', 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, screen: skillScreen() })   // skills hook (M13)
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
    return await api('POST', '/api/mary/talk', { text: text, screen: skillScreen() }, { signal: ctrl ? ctrl.signal : undefined, ms: 30000 });
  }

  async function replyFailed() {
    await say(MSG.sorry, 'sorry');
  }

  async function finishReply(d, T) {
    if (d.mood) { applyMood(String(d.mood)); }
    if (d.emergency && S.screen !== 'emergency') { show('emergency'); }
    // --- skills hook (M13) --- a skill's effects (when not already streamed to us)
    if (!T.effects && d.effects && d.effects.length) {
      for (var ei = 0; ei < d.effects.length; ei++) { applyEffect(d.effects[ei], T); }
    }
    // With no key, an offline voice phrase that ran a skill still gets spoken (no key screen). The server
    // sets mood "talking" for that and "sorry" for its own no-key line.
    var skillRan = !!T.effects || (String(d.text || '').trim() && d.mood === 'talking');
    // --- end skills hook ---
    if (d.needs_key && !d.emergency && !skillRan) {
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

    showCaption(caption);   // M4a
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
    var c = S.convo;   // M4a: Live stays open (typed words go into it); a Normal/Offline talk ends here
    if (c && c.live) { c.lastAct = Date.now(); } else { if (c) { closeConvo(c); } newTurn(); }
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
    if (S.convo && S.convo.live && liveOn()) { liveTyped(S.convo, v); return; }   // M4a
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
    var changed = c !== S.companion;   // M4a
    S.companion = c;
    try { face.setCompanion(c); } catch (e) { log(e); }
    applyLook(c);
    refreshLabels();
    var saved = null;
    if (!(opts && opts.noSave)) { saved = api('PUT', '/api/settings', { companion: c }).catch(noop); }
    if (changed) { liveRestartAfter(saved); }   // M4a: Live talks in the new companion's voice once it is saved
  }

  function switchCompanion() {
    var c = S.companion === 'mary' ? 'him' : 'mary';
    newTurn();
    setCompanion(c);
    if (S.convo && S.convo.live) { try { face.bounce(); } catch (e) { /* nothing */ } return; }   // M4a: Live greets
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
    // --- skills hook (M13) --- voice_comfort does these; the old code is the fallback
    if (act === 'slower') { skillMenu('slower').then(function (ok) { if (!ok) { adjust('rate', -0.08); } }); }
    else if (act === 'faster') { skillMenu('faster').then(function (ok) { if (!ok) { adjust('rate', 0.08); } }); }
    else if (act === 'quieter') { skillMenu('quieter').then(function (ok) { if (!ok) { adjust('volume', -0.1); } }); }
    else if (act === 'louder') { skillMenu('louder').then(function (ok) { if (!ok) { adjust('volume', 0.1); } }); }
    else if (act === 'switch') { skillMenu('switch_companion', 'happy').then(function (ok) { if (!ok) { switchCompanion(); } }); }
    // --- end skills hook ---
    else if (act === 'type') { openTyping(); }
    else if (act === 'notes') { window.location.href = '/?from=mary'; }
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
    // M4a: the talk modes the server says will work, best first, and the quiet that ends a turn
    if (st.talk_mode) { S.talkMode = String(st.talk_mode); }
    if (Array.isArray(st.talk_order)) {
      S.talkOrder = st.talk_order.filter(function (m) { return m === 'live' || m === 'normal' || m === 'offline'; });
    }
    if (st.listen_wait != null) { QUIET_END_S = clampNum(st.listen_wait, 1.5, 6, QUIET_END_S); }
    if (!S.convo) { S.voiceMode = speechModeFor(nextMode(S.talkOrder, null)); }
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
    setCaption(S.typingOnly && !liveFirst() ? MSG.tapToType : MSG.tapToTalk);   // M4a: Live has its own mic
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
    $('infoBtn').addEventListener('click', function () { window.location.href = '/?from=mary#info'; });
    $('typeForm').addEventListener('submit', function (ev) { ev.preventDefault(); submitTyping(); });
    $('typeCancel').addEventListener('click', function () { closeTyping(true); });
    $('typeText').addEventListener('keydown', function (ev) {
      if (S.convo) { S.convo.lastAct = Date.now(); }   // M4a: typing is not quiet
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
    applySettings: applySettings,            // skills hook (M13)
    currentScreen: function () { return S.screen; },
    api: api,
    getFace: function () { return face; },
    // M4a: conversations and talk modes
    startTalk: startTalk,                    // the one way in: Talk tap, and the wake word (M6)
    endTalk: function (why) { if (S.convo) { endConvo(S.convo, why || 'tap'); } },
    inTalk: function () { return !!S.convo; },
    showCaption: showCaption,                // her words; M4b replaces it with bubble letters
    nextMode: nextMode,                      // pure, for tests
    liveToolGate: liveToolGate,              // pure, for tests
    isGoodbye: isGoodbye                     // pure, for tests
  };

  if (D.readyState === 'loading') {
    D.addEventListener('DOMContentLoaded', function () { init().catch(log); });
  } else {
    init().catch(log);
  }
})();
