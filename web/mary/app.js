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
     MaryApp.talkTo(text)        send text through the talk pipeline (never shows his words; streams, speaks); resolves when she is done
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
  var BYE_RE = /\b(?:good[\s-]?bye|bye now|bye[\s-]bye|that['’]?s all for now|talk to you later|good[\s-]?night|see you later|(?:go|going|get) (?:on )?(?:back )?to sleep|(?:go|get|take) (?:some |a )?(?:rest|nap)|(?:you can|go on and|time to) (?:rest|sleep)|rest now|that['’]?(?:s| will| ?ll) (?:be )?(?:all|enough) for (?:now|today|tonight))\b/i;   // M4a: and "go to sleep"
  // M4a: "I can't get to sleep", "my chest hurts, I need rest", "why did she go to sleep?" are about something else: she must keep listening
  var BYE_NOT = /\?|\b(?:can['’]?t|cannot|couldn['’]?t|could not|won['’]?t|wouldn['’]?t|didn['’]?t|don['’]?t|doesn['’]?t|not|never|trouble|hard|help|how|why|when|where|what|wish|want|wanted|need|needed|tried|try|trying|if|because|after|before|until|he|she|they|we|her|him|his|their)\b/i;
  // M4a: words that don't count toward a goodbye's length: "Okay Mary, you can go to sleep now" is still short
  var BYE_FILLER = /^(?:ok(?:ay)?|alright|all|right|well|now|so|oh|honey|dear|darling|mary|sam|then|please|thanks|thank|you)$/i;
  var LIVE_BYE_MAX_MS = 6000;    // after the goodbye is asked for, Live closes once her turn ends, or after this
  // M4a: {when} is the local time of day (morning, afternoon, evening or night), filled in by liveHello()
  var LIVE_HELLO = '(The resident is ready to talk with you, and it is {when} where they are. Greet them in one or ' +
    'two short, warm sentences, like a friend who is glad to see them: use their name if you know it and, when it ' +
    'fits, something you remember about them or from your last talk. Talk as one grown-up to another: plain and ' +
    'easy, no gushing and no fuss over them. Use different words every time. A light ' +
    '"good morning", "good afternoon" or "good evening" is fine, but never "good night", never comment on the hour ' +
    'or how late it is, and never say you are still here or waiting for them. Never list what you can do.)';
  function timeWord() {   // M4a: the same slots as the scripted greetings in firstrun.js
    var h = new Date().getHours();
    return (h >= 22 || h < 5) ? 'night' : h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening';
  }
  function goodbyeLine() { return MSG.goodbye + ' ' + restLine(false); }   // M4a
  function liveHello() { return LIVE_HELLO.replace('{when}', timeWord()); }   // M4a
  // M4a: the big Talk button is gone (M4b). The way back in is her name (M6), when it can run here, or Menu.
  function wakeOn() { return !!S.wakeWord && !!S.wakeReady; }
  function restLine(typing) {   // the resting caption and the end of her goodbye: only ways that really work now
    var n = companionName(S.companion);
    if (typing) { return 'Tap Menu, then “Type to ' + n + '”, any time.'; }
    return wakeOn() ? 'Say “Hey ' + n + '” any time you want to talk.'
      : 'Tap Menu, then “Talk to ' + n + '”, any time you want to talk.';
  }
  function liveBye() {
    var n = companionName(S.companion);
    return '(The conversation is ending now. Say a short, warm goodbye in one sentence and remind them ' +
      (wakeOn() ? 'they can say "Hey ' + n + '" any time to talk again.)'
        : 'they can tap Menu, then "Talk to ' + n + '", any time to talk again.)');
  }
  var LIVE_SWITCHED = '(The resident just switched to you. Say a short, warm hello in one sentence, using their name if you know it.)';
  var LIVE_SAY = '(Say this out loud, word for word, and nothing else: ';   // M4a: say() while Live is open
  var LIVE_SAFETY = '(Safety first. The resident may be in an emergency. Say this to them right now, warmly and plainly, then stay with them: ';
  // --- end M4a ---

  var MSG = {
    listening: "I'm listening…",
    silence: "I didn't hear anything. I'm here whenever you're ready.",   // M4a: no Talk button any more
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
    goodbye: "It was so nice talking with you."   // M4a: goodbyeLine() adds the way back in
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
    ttsSpent: false,             // M4a: the Gemini voice has used up its free turns for today (status, or a swap)
    convo: null                  // the open conversation (startTalk), or null
  };

  var NULLFACE = { setMood: noop, setActivity: noop, setCompanion: noop, bounce: noop, destroy: noop,
    setLoud: noop, setMenuOpen: noop, setAside: noop, setEmergency: noop };   // M4b
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
    $('scr').setAttribute('data-companion', c === 'him' ? 'him' : 'mary');   // M4b: her caption ink (captions.css)
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
  // M4b: lines that are not her voice ("You said: ...", tips) as a plain caption line (captions.js plain()).
  function setCaption(text, kind) {
    text = String(text == null ? '' : text);
    CapS.plain = text;
    capCall(function () { if (text) { cap.plain(text, kind); } else { cap.clear(); } });
  }

  // M4a: her own words (Live captions, her replies, say()). M4b: those now show word by word as she says them
  // (capSay in the speech paths, capLivePiece in Live, whole() on the emergency screen), so this does nothing.
  function showCaption(text) { /* M4b */ }

  // --- M4b: her words as style A captions (captions.js) on the playback clock, and the face's listening and
  // thinking states (mockups/mary/round6/README.md, "Notes for the builder" 1-4, 6, 8) ---
  var NULLCAP = { sentence: function () { return 0; }, setDuration: noop, retime: noop, liveAudio: noop,
    livePiece: function () { return 0; }, whole: function () { return 0; }, cut: noop, stopped: noop, clear: noop,
    setSide: noop, setAside: noop, plain: noop, setLiveRegion: noop, showing: function () { return false; } };
  var cap = NULLCAP;
  // plain: the plain line showing; owner: whose words are up (a speech session or 'live');
  // liveWhole / liveTimed / emTurn: Live on the emergency screen; liveDone: her Live turn was heard to the end
  // liveCut: Live cut her off; her next turn's first sound starts a fresh caption (captions.js drops pieces after cut())
  var CapS = { plain: '', owner: null, liveWhole: '', liveTimed: false, emTurn: '', liveDone: false, liveCut: false };
  var LOUD_HOLD_MS = 500;          // the resident counts as talking until this long after their last voice
  var SPOKE_MS = 350;              // Live: this much voice is a real turn of theirs, not a cough (speech.py HEARD_VOICE_S)
  var LIVE_THINK_AFTER_MS = 700;   // Live: this much quiet after they spoke = their turn is over, she is thinking
  var LIVE_THINK_MAX_MS = 8000;    // ...and back to listening if she has not answered by then
  var LV = { loud: false, voiceAt: 0, loudSince: 0, spoke: false, thinking: false, thinkTimer: null };

  function makeCaptions() {
    try {
      if (typeof MaryCaptions !== 'undefined') { return MaryCaptions.create($('scr'), { liveRegion: $('capLive') }); }
    } catch (e) { log(e); }
    return NULLCAP;
  }
  function capCall(fn) { try { return fn(); } catch (e) { log(e); return 0; } }
  function announceLive(text) { try { $('capLive').textContent = String(text || '').trim(); } catch (e) { /* nothing */ } }
  // New words from someone else (another speech session, or Live after one): never join the caption showing.
  // (clear, not cut: cut() would also drop the Live pieces that follow until the resident talks)
  function capOwn(owner) {
    if (CapS.owner === owner) { return; }
    CapS.owner = owner;
    if (cap.showing()) { capCall(function () { cap.clear(); }); }
  }
  // Emergency: all of it at once, already filled (whole). `say` goes to the live region; a re-show stays quiet.
  function quietWhole(text, o, say) {
    capCall(function () { cap.setLiveRegion(null); cap.whole(text, o || {}); });
    capCall(function () { cap.setLiveRegion($('capLive')); });
    if (say) { announceLive(say); }
  }
  function wholeTiming(text, o) {
    var t = { dur: estimateMs(text) / 1000 };
    if (o && o.ctx) { t.at = o.at; t.ctx = o.ctx; }
    return t;
  }
  // One sentence of hers (her picked voice, the computer's voice, caption only), at its first sound. Returns its id.
  function capSay(s, text, o) {
    if (!s || Sp.sess !== s || s.finished) { return 0; }
    if (!s.sounded) { s.sounded = true; faceAct(); }   // her first sound: thinking ends, talking starts
    CapS.plain = '';
    capOwn(s);
    if (S.screen !== 'emergency') { return capCall(function () { return cap.sentence(text, o); }); }
    if (s.capPre) {                       // say() put the words up already: now the spoken word lifts with her voice
      if (!s.capTimed) { s.capTimed = true; quietWhole(s.capPre, wholeTiming(s.capPre, o), ''); }
      return 0;
    }
    var first = !s.capWhole;
    s.capWhole = first ? text : s.capWhole + ' ' + text;
    quietWhole(s.capWhole, first ? wholeTiming(text, o) : {}, text);
    return 0;
  }
  function capStopped() { if (S.screen !== 'emergency') { capCall(function () { cap.stopped(); }); } }   // the emergency words stay up
  function capCut() {
    if (S.screen === 'emergency') { return; }
    if (CapS.owner === 'live') { CapS.liveCut = true; }   // her next Live sound starts a fresh caption
    capCall(function () { cap.cut(); });
  }
  // No words while listening (round 6): a plain tip goes now; her own words fade 4 s after her or when they talk.
  function capListening() { if (CapS.plain) { CapS.plain = ''; capCall(function () { cap.clear(); }); } }
  // Live: each piece of her words (talklive onCaptionPiece), each audio chunk, her turn heard to the end.
  function capLivePiece(piece) {
    CapS.plain = '';
    if (S.screen !== 'emergency') {
      capOwn('live');
      capCall(function () { return cap.livePiece(piece); });
      if (CapS.liveDone) { capCall(function () { cap.stopped(); }); }   // a late piece after her sound ended still fades
      return;
    }
    if (CapS.liveWhole) { return; }       // her safety words are up already, whole
    CapS.emTurn += piece;
    quietWhole(CapS.emTurn.trim(), {}, '');
  }
  function capLiveAudio(at, dur, ctx) {
    CapS.liveDone = false;
    if (CapS.liveCut) { CapS.liveCut = false; if (S.screen !== 'emergency') { capCall(function () { cap.clear(); }); } }
    if (S.screen !== 'emergency') { capCall(function () { cap.liveAudio(at, dur, ctx); }); return; }
    if (CapS.liveWhole && !CapS.liveTimed) {
      CapS.liveTimed = true;
      quietWhole(CapS.liveWhole, wholeTiming(CapS.liveWhole, { at: at, ctx: ctx }), '');
    }
  }
  function capLiveDone() {
    CapS.liveDone = true;
    if (S.screen !== 'emergency') { capCall(function () { cap.stopped(); }); return; }
    if (CapS.emTurn.trim()) { announceLive(CapS.emTurn); }
    CapS.emTurn = '';
    if (CapS.liveTimed) { CapS.liveWhole = ''; }
  }
  function capLiveEmergency(words) {
    CapS.liveWhole = words;
    CapS.liveTimed = false;
    CapS.emTurn = '';
    CapS.owner = 'live';
    quietWhole(words, {}, words);
  }
  function capLeaveEmergency() {
    CapS.liveWhole = '';
    CapS.liveTimed = false;
    CapS.emTurn = '';
    capCall(function () { cap.stopped(); });   // her last emergency words fade gently
  }

  // The face's activity follows the phase, except that thinking runs on to her first sound (round 6 note 6),
  // and in Live the open mic shows thinking between the end of their turn and her answer (face.js: cloud at 400 ms).
  function faceActivity() {
    var p = S.phase, sess = (typeof Sp !== 'undefined' && Sp) ? Sp.sess : null;
    if (p === 'speaking') { return (sess && !sess.sounded && !liveSpeaking()) ? 'thinking' : 'talking'; }
    if (p === 'listening') { return LV.thinking ? 'thinking' : 'listening'; }
    return p === 'thinking' ? 'thinking' : 'resting';
  }
  function faceAct() { try { face.setActivity(faceActivity()); } catch (e) { log(e); } }
  // The resident is talking (a voice on the mic now): bright, fast ear waves, and her caption fades.
  function setLoudNow(on) {
    on = !!on;
    if (LV.loud === on) { return; }
    LV.loud = on;
    if (on) { LV.loudSince = Date.now(); }
    try { face.setLoud(on); } catch (e) { log(e); }
    if (on && S.screen !== 'emergency') { CapS.plain = ''; capCall(function () { cap.clear(); }); }
  }
  function liveThinkStop() { LV.thinking = false; LV.spoke = false; clearTimeout(LV.thinkTimer); }
  function liveThink() {
    liveThinkStop();
    LV.thinking = true;
    LV.thinkTimer = setTimeout(function () { liveThinkStop(); faceAct(); }, LIVE_THINK_MAX_MS);
    faceAct();
  }
  // Live: the page's own mic level (talklive onMicLevel); voice = above talklive's talking level (VOICE_LEVEL).
  function liveMicLevel(voice) {
    if (S.phase !== 'listening') { return; }   // she is talking: her own voice may reach the mic
    var now = Date.now();
    if (voice) {
      LV.voiceAt = now;
      if (LV.thinking) { liveThinkStop(); faceAct(); }   // they went on talking
      setLoudNow(true);
      if (now - LV.loudSince >= SPOKE_MS) { LV.spoke = true; }
    } else if (LV.loud && now - LV.voiceAt > LOUD_HOLD_MS) {
      setLoudNow(false);
    }
    if (LV.spoke && !LV.loud && !LV.thinking && now - LV.voiceAt >= LIVE_THINK_AFTER_MS) { liveThink(); }
  }
  // --- end M4b ---

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
    if (!r) { return; }   // M4b: the big Talk button (and its ring) is gone
    level = Math.max(0, Math.min(1, Number(level) || 0));
    r.style.opacity = String(0.3 + level * 0.7);
    r.style.transform = reduced() ? '' : 'scale(' + (1 + level * 0.1).toFixed(3) + ')';
  }

  // M4b: the menu's Talk row stands in for the big Talk button (gone): "Stop talking" while she is in a talk
  function updateTalkButton() {
    var b = $('miTalk'), lbl = $('miTalkLbl');
    if (!b || !lbl) { return; }
    var n = companionName(S.companion), text = 'Talk to ' + n, busy = false;
    if (S.convo) { text = 'Stop talking'; }
    else if (S.phase === 'listening') { text = "I'm done"; }
    else if (S.phase === 'thinking') { text = 'One moment…'; busy = true; }
    else if (S.typingOnly && !liveFirst()) { text = 'Type to ' + n; }   // M4a: Live has its own mic
    lbl.textContent = text;
    if (busy) { b.setAttribute('aria-disabled', 'true'); } else { b.removeAttribute('aria-disabled'); }
    b.setAttribute('aria-busy', busy ? 'true' : 'false');
  }

  function setPhase(p) {
    S.phase = p;
    if (p !== 'listening') { setLoudNow(false); liveThinkStop(); }   // M4b
    faceAct();   // M4b: the phase's activity, but thinking runs on to her first sound (faceActivity)
    $('scr').setAttribute('data-phase', p);
    updateTalkButton();
    if (p !== 'listening') { setRing(0); }
    wakeHoldCheck();   // M6: the wake word pauses while she is busy
  }

  function refreshLabels() {   // M4b: the menu and panel words follow the companion's name
    var n = companionName(S.companion);
    var both = companionName('mary') + ' or ' + companionName('him');
    function set(id, t) { var el = $(id); if (el) { el.textContent = t; } }
    set('miCanLbl', 'Things ' + n + ' can do');
    set('miChooseLbl', 'Choose ' + both);
    set('closeLbl', 'Close ' + n);
    set('canTitle', 'Things ' + n + ' can do');
    set('canLead', 'You can say these to ' + n + ', or tap one.');
    set('modeTitle', 'How ' + n + ' talks');
    set('voiceTitle', n + "'s voice");
    set('waitTitle', 'How long ' + n + ' waits');
    set('wakeTitle', 'Listen for “Hey ' + n + '”');   // M6
    set('skillTitle', 'Things ' + n + ' can do');
    set('memTitle', 'What ' + n + ' remembers');   // M9c
    set('chooseTitle', 'Choose ' + both);
    try { $('menu').setAttribute('aria-label', n + "'s menu"); } catch (e) { /* nothing */ }
    var backs = D.querySelectorAll('.backLbl');
    for (var i = 0; i < backs.length; i++) { backs[i].textContent = 'Back to ' + n; }
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
    var wasSaying = !!(s && !s.finished && s.sounded);   // M4b
    Sp.sess = null;
    if (s) {
      s.finished = true;
      s.queue = [];
      for (var i = 0; i < s.timers.length; i++) { clearTimeout(s.timers[i]); }
      s.timers = [];
      settle(s);
    }
    if (wasSaying) { capCut(); }   // M4b: she was cut off: keep the words she said, fade the rest
    try { if (window.MaryVoice) { window.MaryVoice.cancel(); } } catch (e) { log(e); }   // M4a: her picked voice too
    if (V.ok) {
      try { window.speechSynthesis.cancel(); } catch (e) { /* nothing */ }
      Sp.cancelAt = Date.now();
    }
  }

  function spStart(voice) {   // M4a: voice: a line that ends a talk, in that talk's voice
    spCancel();
    var s = { queue: [], busy: false, ended: false, started: false, finished: false, waiters: [], timers: [],
      voice: voice == null ? speechVoice() : voiceFor(voice), mvJob: null, mvSent: [], mvEnded: false };   // M4a: her picked voice, when it works
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
    if (s.sounded) { capStopped(); }   // M4b: all of it was heard: the last words finish, then fade
    if (S.phase === 'speaking' || S.phase === 'thinking') { setPhase(restPhase()); }   // M4a: Live goes back to listening
    settle(s);
  }

  // --- M4a: her picked voice (voiceout.js) for Normal and Offline; speechSynthesis stays the last resort ---
  function voiceFor(m) {
    var ok = window.MaryVoice && typeof window.MaryVoice.more === 'function';
    return (ok && (m === 'normal' || m === 'offline')) ? m : '';
  }
  // M4a: Gemini TTS is only for Normal. A Normal or Offline talk has its one locked voice (c.voice); with Live chosen,
  // a line outside any Live talk is Kokoro, or the computer's own voice. Live's own lines never come through here.
  function speechVoice() {
    var c = S.convo, m = S.voiceMode;
    if (c && !c.live && c.voice != null) { m = c.voice; }
    else if ((!c || c.live) && S.talkMode === 'live') { m = talkVoice('live', false, S.talkOrder); }
    return voiceFor(m);
  }
  // The voice after `from` in the talk order (Live is never a voice for sentences); '' = the computer's own voice.
  function nextVoice(from) { return voiceAfter(S.talkOrder, from); }
  // One open MaryVoice job per session: each sentence is fetched as soon as it is added, so there are no gaps.
  function mvPump(s) {
    if (s.queue.length) {
      var batch = s.queue.splice(0, s.queue.length);
      if (!s.started) { s.started = true; setPhase('speaking'); }
      if (!s.mvJob) {
        var job = { capIds: {} }, p;   // M4b: capIds = sentence index -> caption id
        s.mvJob = job;
        s.mvSent = batch.slice();
        s.mvEnded = false;
        try {
          p = window.MaryVoice.queue(batch, { mode: s.voice, rate: S.rate, volume: S.volume, open: true,
            onVoice: function (v) { voiceSwapped(s, v); },   // M4a: the server swapped to Kokoro for this line
            // M4b: each sentence's caption on the playback clock, corrected once its real length is known
            onSentenceAudio: function (i, text, at, ctx, dur) { job.capIds[i] = capSay(s, text, { at: at, ctx: ctx, dur: dur }); },
            onSentenceLength: function (i, dur) {
              if (Sp.sess === s && job.capIds[i]) { capCall(function () { cap.setDuration(job.capIds[i], dur); }); }
            } });
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
  // M4a: the server made this line in Kokoro because Gemini's daily limit is used up. Nothing failed, so there is no
  // fallback line; the page only has to learn it, so the talk stays on Kokoro and never flips back.
  function voiceSwapped(s, to) {
    S.ttsSpent = true;
    var c = S.convo;
    if (s.voice === 'normal') { s.voice = to; }
    if (c && !c.live && c.voice === 'normal') { c.voice = to; }
    if (S.voiceMode === 'normal') { S.voiceMode = to; }
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
    var c = S.convo;   // M4a: a talk moves once and stays there, never back, whatever sound came first
    if (c && !c.live && c.voice === from) { c.voice = s.voice; S.voiceMode = s.voice; }
    else if (at === 0 && S.voiceMode === from) { S.voiceMode = s.voice; }
    if (!S.fallbackSaid) { S.fallbackSaid = true; rest.unshift(MSG.fallback); rememberSaid(MSG.fallback); }   // M4a: this line skips say()
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
    var shown = false;   // M4b
    function capOnce() { if (!shown) { shown = true; capSay(s, text, { dur: est / 1000 }); } }   // M4b: performance clock

    function done() {
      if (settled) { return; }
      settled = true;
      cb();
    }
    function captionOnly() {
      // no voice: the mouth moves for about as long as it would take to say it
      capOnce();   // M4b
      addTimer(s, function () { if (Sp.sess === s) { done(); } }, est);
    }

    if (!V.ok) { captionOnly(); return; }

    function utter(voice, isRetry) {
      if (settled || Sp.sess !== s) { return; }
      var u;
      try { u = new window.SpeechSynthesisUtterance(spokenNumbers(text)); } catch (e) { captionOnly(); return; }
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

      u.onstart = function () { began = true; capOnce(); };   // M4b: her first sound
      u.onend = function () { began = true; if (!failed) { capOnce(); done(); } };   // M4b: capOnce if it never said it started
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
  // M4a: voice: this line's voice when the talk it ends has just closed; saved: the history has this line already
  function say(text, mood, voice, saved) {
    text = String(text == null ? '' : text).trim();
    if (liveOn()) {
      try { window.MaryLive.stopSpeaking(); } catch (e) { log(e); }   // M4a: never two voices at once
      // M4a: in Live, Live speaks everything. If the line won't take it, the usual path below still says it.
      if (text && greetLive(LIVE_SAY + text + ')')) {
        if (mood) { setMood(mood); }
        showCaption(text);
        if (S.screen === 'emergency') { capLiveEmergency(text); }
        return Promise.resolve();
      }
    }
    // M4a: every line she speaks goes into the talk history, here and only here. A line Live says is saved from Live's
    // own transcript (liveSaid) and never gets this far; brain replies never come through say(): mary.reply saves them.
    if (text && !saved) { rememberSaid(text); }
    var s = spStart(voice);
    var p = waitSess(s);
    if (mood) { setMood(mood); }
    showCaption(text);   // M4a
    if (S.screen === 'emergency') {   // M4b: the emergency words all at once, before her voice starts
      s.capPre = text;
      if (CapS.liveWhole !== text) { quietWhole(text, {}, text); }
      CapS.liveWhole = '';
      CapS.owner = s;
    }
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
    try { face.setEmergency(name === 'emergency'); } catch (e) { log(e); }   // M4b: the calm concerned face, steady glow
    if (screens[name] && screens[name].enter) {
      try { screens[name].enter(opts || {}, prev); } catch (e) { log(e); }
    }
  }

  registerScreen('everyday', {});

  registerScreen('emergency', {
    enter: function () {
      S.emSeq++;
      closePanel(false); closeMenu(false);   // M4b: nothing covers the answers
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
      capLeaveEmergency();   // M4b
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
      capListening();   // M4b: no words while listening (round 6)

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
          // M4b: the ear waves brighten while the server hears a voice now (its own voice test, held LOUD_HOLD_MS)
          setLoudNow(Number(l.elapsed_s) - Number(l.quiet_s) > 0.05 && Number(l.quiet_s) * 1000 < LOUD_HOLD_MS);
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
      if (c.paused) { c.paused = false; convoListen(c, true); return; }
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
  // M4a: also refused while the emergency screen is up, so a skill call that beat the transcript can't cover it.
  function liveToolGate(heardResult, onEmergencyScreen) {
    return ((heardResult && heardResult.emergency) || onEmergencyScreen) ? 'refuse' : 'run';
  }

  // A short goodbye turn ("bye now", "that's all for now"). Pure.
  function isGoodbye(text) {
    text = String(text == null ? '' : text).trim();
    if (!text) { return false; }
    var words = text.split(/\s+/).filter(function (w) { return !BYE_FILLER.test(w.replace(/[^\w']/g, '')); });   // M4a
    return words.length <= BYE_MAX_WORDS && BYE_RE.test(text) && !BYE_NOT.test(text);
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
  // M4a: the crisis numbers digit by digit for her voice; mary.py has the same list. Captions keep the digits.
  function spokenNumbers(text) {
    return String(text).replace(/\b988\b/g, 'nine, eight, eight').replace(/\b911\b/g, 'nine one one')
      .replace(/\b838[- ]?255\b/g, 'eight three eight, two five five');
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

  // --- M4a: her hello, in her own words from the same brain as her talk. Thinking while it comes. On any failure, or
  // with no key, the scripted line (say() saves that one). saved: the server has already put it in the history.
  // Empty text: something else started meanwhile, such as an emergency, so she says nothing.
  function openingLine(fallback) {
    if (!S.hasKey) { return Promise.resolve({ text: fallback, saved: false }); }
    setPhase('thinking');
    function done(text, saved) {
      if (S.screen !== 'everyday' && S.phase === 'thinking') { setPhase('idle'); }
      if (S.screen !== 'everyday' || S.phase !== 'thinking') { return { text: '', saved: false }; }
      return { text: text, saved: saved };
    }
    return api('POST', '/api/mary/open', { when: timeWord() }, { ms: 9000 }).then(function (j) {
      var text = String((j && j.text) || '').trim();
      return text ? done(text, true) : done(fallback, false);
    }, function (e) { log(e); return done(fallback, false); });
  }
  function firstLine(opts) {   // what a talk opens with: opts.say as it stands, or the brain's hello with opts.say behind it
    return opts.brainHello ? openingLine(opts.say) : Promise.resolve({ text: opts.say, saved: false });
  }
  // --- end M4a ---

  // The one way to start talking. Call it straight from a tap (Live opens the mic and sound there).
  // opts.hello: what Live is asked to say first. Resolves true when a conversation started.
  // M4a: opts.say (with opts.mood): when she starts by herself, the words Normal and Offline say before listening;
  // with no mic it is only said, and the typing box is not opened. opts.brainHello: opts.say is a hello, so the brain
  // makes it and opts.say is only the fallback.
  function startTalk(opts) {
    opts = opts || {};
    App.onActivity();
    if (S.convo || S.phase === 'thinking' || S.phase === 'listening') { return Promise.resolve(false); }
    var mode = nextMode(S.talkOrder, null);
    if (mode === 'live' && !liveSupported()) { mode = nextMode(S.talkOrder, 'live'); }
    if (mode !== 'live' && S.typingOnly && opts.say) {   // M4a
      firstLine(opts).then(function (l) {
        if (l.text) { return say(l.text, opts.mood || 'happy', undefined, l.saved); }
      }).catch(log);
      return Promise.resolve(false);
    }
    if (mode !== 'live' && S.typingOnly) { openTyping(); return Promise.resolve(false); }
    var c = { mode: mode, live: false, open: false, ending: false, paused: false, seq: 0, lastAct: Date.now(),
      heard: '', heardCheck: null, toolBusy: 0, idleTimer: null, byeTimer: null, byeDone: false, misses: 0,
      byeAudio: false, story: null, voice: null };   // M4a: voice = this talk's one voice, locked by lockTalkVoice()
    S.convo = c;
    S.fallbackSaid = false;
    S.voiceMode = speechModeFor(mode);
    updateTalkButton();
    wakeHoldCheck();   // M6
    if (mode === 'live') {
      startLive(c, opts.hello || liveHello());   // M4a: with the time of day
    } else {
      lockTalkVoice(c).then(function () {   // M4a: from a fresh status, so a spent voice is never tried
        if (S.convo !== c || c.ending) { return; }
        if (!opts.say) { convoListen(c, true); return; }
        firstLine(opts).then(function (l) {   // M4a: her hello first, then she listens
          if (S.convo !== c || c.ending) {
            if (S.phase === 'thinking') { setPhase('idle'); }
            return;
          }
          if (!l.text) {                      // something else started; the emergency screen goes on with the talk itself
            if (S.screen !== 'emergency') { convoListen(c, true); }
            return;
          }
          say(l.text, opts.mood || 'happy', undefined, l.saved).then(function () { convoListen(c, true); },
            function (e) { log(e); convoListen(c, true); });
        }, log);
      });
    }
    return Promise.resolve(true);
  }

  // M4a: decides c.voice, the one voice for the whole of a Normal or Offline talk. A slow status uses what is known.
  function lockTalkVoice(c) {
    return api('GET', '/api/mary/status', null, { ms: STATUS_LOCK_MS }).then(applyStatus, log).then(function () {
      c.voice = talkVoice(c.mode, S.ttsSpent, S.talkOrder);
      if (S.convo === c) { S.voiceMode = c.voice; }
    }, log);
  }

  function closeConvo(c) {
    if (!c) { return; }
    clearInterval(c.idleTimer);
    clearTimeout(c.byeTimer);
    clearTimeout(c.byeWait);   // M4a
    c.ending = true;
    if (S.convo === c) { S.convo = null; }
    c.story = null;   // M4a: a story never outlives the talk
    if (c.live) {
      c.live = false;
      c.open = false;
      try { window.MaryLive.stop('end'); } catch (e) { log(e); }
      if (CapS.owner === 'live') { capCut(); }   // M4b: her voice stops with the talk
      if (!Sp.sess && (S.phase === 'listening' || S.phase === 'speaking')) { setPhase('idle'); }
    }
    updateTalkButton();
    wakeHoldCheck();   // M6
  }

  // Ends the conversation. why: 'tap' (at once, quietly), 'idle' or 'bye' (with a short goodbye).
  function endConvo(c, why) {
    if (!c || S.convo !== c || c.ending) { return; }
    if (why === 'tap') {
      closeConvo(c);
      newTurn();
      setPhase('idle');
      setCaption(restLine(S.typingOnly && !liveFirst()));
      return;
    }
    if (c.live && c.open) {
      if (why === 'bye') { liveByeNow(c); return; }   // M4a: Live says the goodbye, then the session closes
      c.ending = true;
      c.byeDone = false;
      c.byeAudio = false;   // M4a
      clearInterval(c.idleTimer);
      // on quiet she is asked for a goodbye
      if (why === 'idle' && !greetLive(liveBye())) { finishLive(c); return; }
      c.byeTimer = setTimeout(function () { liveByeCap(c, false); }, LIVE_BYE_MAX_MS);
      return;
    }
    var voice = c.voice;   // M4a: her goodbye in the voice of this talk
    closeConvo(c);
    newTurn();
    say(goodbyeLine(), 'happy', voice);
  }

  // --- M6: the wake word ("Hey Mary" / "Hey Sam"), heard on this computer by the server ---
  // The server listens only while this page polls /api/wake/wait (its lease), so one poll loop runs all the time
  // her screen is open, talks included. While she is busy the page holds the listener (/api/wake/hold), so she
  // never wakes herself. "heard" = the name was heard (ear waves only); "wake" = it was confirmed: she answers.
  var WAKE_HEARD_MS = 4000;      // no "wake" this soon after "heard": back to her resting look
  var WAKE_ERR_MS = 5000;        // a failed poll waits this long before the next one
  var WAKE_OFF_MS = 30000;       // the setting is off on the server: ask again this rarely
  var WAKE_POLL_MAX_MS = 30000;  // the server answers within 20 s; give up on a poll after this
  var WAKE_HOLD_RENEW_MS = 30000;  // the server lets a hold go after 90 s
  var WAKE_SAY = "Yes? I'm here.";
  var WAKE_HELLO = "(They just called your name to get your attention. Answer in a few warm words, like 'Yes? I'm here.', then listen.)";
  var W = { polling: false, inFlight: false, seq: 0, lastEv: 0, timer: null, abort: null, heardTimer: null,
    held: false, holdAt: 0, gone: false, gen: 0 };

  function wakeWanted() { return !W.gone && !!S.wakeWord && !!S.wakeReady; }
  function wakeSync() {   // start or stop the one poll loop to match the setting and the server
    if (wakeWanted()) {
      if (!W.polling) { W.polling = true; W.seq = 0; W.lastEv = 0; wakeSchedule(0); }
    } else if (W.polling) {
      wakeStop();
    }
  }
  function wakeStop() {
    W.polling = false;
    W.gen++;   // an answer to an older poll is ignored
    clearTimeout(W.timer);
    clearTimeout(W.heardTimer);
    if (W.abort) { try { W.abort(); } catch (e) { /* nothing */ } }
  }
  function wakeSchedule(ms) {
    clearTimeout(W.timer);
    W.timer = setTimeout(wakePoll, ms);
  }
  function wakePoll() {
    if (!W.polling) { return; }
    if (W.inFlight) { wakeSchedule(500); return; }   // never two polls at once (an old one is still ending)
    W.inFlight = true;
    var gen = W.gen;
    var ctl = (typeof AbortController === 'function') ? new AbortController() : null;
    var guard = ctl ? setTimeout(function () { try { ctl.abort(); } catch (e) { /* nothing */ } }, WAKE_POLL_MAX_MS) : null;
    W.abort = ctl ? function () { ctl.abort(); } : null;
    var opts = ctl ? { signal: ctl.signal } : { ms: WAKE_POLL_MAX_MS };
    api('GET', '/api/wake/wait?after=' + encodeURIComponent(W.seq), null, opts).then(function (j) {
      W.inFlight = false; W.abort = null; clearTimeout(guard);
      if (!W.polling || gen !== W.gen) { return; }
      j = j || {};
      if (j.seq != null && isFinite(Number(j.seq))) { W.seq = Number(j.seq); }
      var st = j.status || {};
      if (st.ready === false) {   // not installed or broken: stop until the status says it is ready again
        S.wakeReady = false;
        if (st.reason) { S.wakeReason = String(st.reason); }
        wakeStop();
        return;
      }
      if (j.event) { onWakeEvent(j.event); }
      wakeSchedule(j.off ? WAKE_OFF_MS : 0);
    }, function (e) {
      W.inFlight = false; W.abort = null; clearTimeout(guard);
      if (!W.polling || gen !== W.gen) { return; }
      log(e);
      wakeSchedule(WAKE_ERR_MS);
    });
  }

  // She may answer her name only on the everyday screen, resting, with no talk, no typing box and no first run.
  function wakeCanAnswer() {
    return S.screen === 'everyday' && !S.firstRun && !S.convo && S.phase === 'idle' && $('typing').hidden;
  }
  function onWakeEvent(ev) {
    var n = Number(ev && ev.seq) || 0;
    if (n && n <= W.lastEv) { return; }
    if (n) { W.lastEv = n; }
    if (W.held || !wakeCanAnswer()) { return; }
    if (ev.type === 'heard') {
      try { face.setActivity('listening'); } catch (e) { log(e); }   // M4b's ear waves: "I hear you", no words
      clearTimeout(W.heardTimer);
      W.heardTimer = setTimeout(function () {
        if (!S.convo && S.phase === 'idle') { faceAct(); }   // back to resting
      }, WAKE_HEARD_MS);
    } else if (ev.type === 'wake') {
      clearTimeout(W.heardTimer);
      if (menuOpen()) { closeMenu(false); }
      if (M.panel) { closePanel(false); }
      startTalk({ say: WAKE_SAY, mood: 'happy', hello: WAKE_HELLO }).then(function (ok) {
        if (!ok && !S.convo && S.phase === 'idle') { faceAct(); }
      }, log);
    }
  }

  // Busy = a talk is open (Live included) or she is speaking, listening or thinking.
  function wakeBusy() { return !!S.convo || S.phase !== 'idle'; }
  function wakeHoldCheck() {
    if (typeof W === 'undefined' || !W) { return; }
    var busy = wakeBusy(), now = Date.now();
    if (!W.polling && !W.held) { return; }
    if (busy === W.held && !(busy && now - W.holdAt >= WAKE_HOLD_RENEW_MS)) { return; }
    W.held = busy;
    W.holdAt = now;
    if (busy) { clearTimeout(W.heardTimer); }
    api('POST', '/api/wake/hold', { on: busy }).catch(log);
  }
  setInterval(wakeHoldCheck, 1000);   // the safety check, and the hold's renewal
  // --- end M6 ---

  // --- Live ---
  function startLive(c, hello) {
    var seq = ++c.seq;
    c.live = true;
    c.open = false;
    c.hello = hello;      // M4a: for the plain retry
    c.story = null;       // M4a: a restart ends the story with its old session
    c.heardTrack = null;  // M4a
    clearTimeout(c.byeWait);   // M4a
    try { if (window.MaryVoice) { window.MaryVoice.cancel(); } } catch (e) { log(e); }
    newTurn();
    setPhase('thinking');
    function mine() { return S.convo === c && c.seq === seq && c.live; }
    var p;
    try {
      p = window.MaryLive.start({
        screen: skillScreen(),
        plain: !!c.plain,   // M4a: no language hint, after a start that failed with it
        onCaption: function (t) { c.saidText = String(t || ''); if (mine()) { c.lastAct = Date.now(); showCaption(t); } },
        // M4a: liveHeardPiece: the story's cut-in, the early goodbye, and garbled lines (true = don't show it)
        // Andy (2026-10-30): his own words are never shown; only her words go on screen
        onHeard: function (t) { if (mine()) { c.lastAct = Date.now(); liveHeardPiece(c, t); } },
        onHeardDone: function (t) { liveHeard(c, t); },   // M4a: even after the talk ended or restarted (never missed)
        onToolCancel: function (ids) { if (mine()) { liveToolCancelled(c, ids); } },   // M4a
        onSpeaking: function (on) { if (mine()) { liveSpeakingChanged(c, on); } },
        onInterrupted: function () {   // M4a: liveSaid; a cut-in holds the story until they ask for the rest
          liveSaid(c);
          if (mine()) { c.lastAct = Date.now(); if (c.story) { c.story.paused = true; } }
        },
        onTurnComplete: function () { liveSaid(c); if (mine()) { liveTurnDone(c); } },   // M4a: liveSaid
        onToolCall: function (tc) { return liveToolCall(c, tc); },
        onActivity: function () { if (mine()) { c.lastAct = Date.now(); } },
        // M4b: her words on her playback clock, the ear waves, and thinking until her first sound
        onCaptionPiece: function (t) { if (mine()) { capLivePiece(t); } },
        onAudioChunk: function (at, dur, ctx) { if (mine()) { if (c.story) { c.story.sounded = true; } capLiveAudio(at, dur, ctx); } },
        onAudioDone: function () { if (mine()) { capLiveDone(); storyNext(c); } },   // M4a: storyNext, once a turn is fully heard
        onCut: function () { if (mine()) { capCut(); } },
        onMicLevel: function (rms, voice) { if (mine()) { liveMicLevel(voice); } },
        onEnd: function (why, detail) { if (mine()) { liveDropped(c, why, detail); } }
      });
    } catch (e) { p = Promise.reject(e); }
    Promise.resolve(p).then(function () {
      if (!mine()) { return; }          // ended or restarted while it was opening
      c.open = true;
      c.lastAct = Date.now();
      try { window.MaryLive.setVolume(S.volume); } catch (e) { log(e); }
      setPhase('listening');
      capListening();   // M4b: no words while listening (round 6)
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
    // M4a: the line closed before it was ready. Google may be refusing the language hint: once more without it.
    if (kind === 'connect' && !c.plainTried) {
      c.plainTried = true;
      c.plain = true;
      startLive(c, c.hello);
      return;
    }
    liveFallback(c);
  }

  // Live would not start or dropped: the next mode in the order, with one kind line, and the talk goes on.
  function liveFallback(c) {
    c.live = false;
    c.open = false;
    clearInterval(c.idleTimer);
    clearTimeout(c.byeTimer);
    clearTimeout(c.byeWait);   // M4a
    c.story = null;            // M4a: only Live can go on with it
    c.mode = nextMode(S.talkOrder, 'live');
    S.voiceMode = speechModeFor(c.mode);
    newTurn();
    setPhase('idle');
    if (c.ending) { closeConvo(c); return; }
    lockTalkVoice(c).then(function () {   // M4a: the talk goes on in one voice from here
      if (S.convo !== c) { return undefined; }
      return sayFallbackOnce().then(function () {
        if (S.convo !== c) { return; }
        if (S.typingOnly) { closeConvo(c); openTyping(); return; }
        convoNext(c);
      });
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
      if (c.ending) { c.byeAudio = true; }   // M4a: her goodbye has started to come through
      setPhase('speaking');
      applyMood('talking');
      return;
    }
    if (S.phase === 'speaking' && !Sp.sess) { setPhase(restPhase()); }
    if (c.ending && c.byeDone) { finishLive(c); }
  }

  function liveTurnDone(c) {
    c.lastAct = Date.now();
    if (!c.ending || !c.byeAudio) { return; }   // M4a: only a turn of hers that came after the goodbye was asked for
    c.byeDone = true;                       // her goodbye turn is complete: close once it has been heard
    if (!liveSpeaking()) { finishLive(c); }
  }

  // M4a: a line of hers goes into the talk history, so the brain knows she said it (say() is the one caller)
  function rememberSaid(text) {
    api('POST', '/api/mary/live/said', { text: String(text || '') }, { ms: 8000 }).catch(log);
  }

  // M4a: her finished Live turn is remembered like Normal talk's, after the resident's own line and never twice.
  function liveSaid(c) {
    var text = String(c.saidText || '').trim();
    c.saidText = '';
    if (!text) { return; }
    if (c.saidSkip) { c.saidSkip = false; return; }   // the emergency words: /api/mary/heard already saved them
    Promise.resolve(c.heardCheck).then(function () {
      return api('POST', '/api/mary/live/said', { text: text }, { ms: 8000 });
    }).catch(log);
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
    if (S.screen === 'emergency' || liveSpeaking() || Sp.sess || c.toolBusy > 0 || uiOpen()) { c.lastAct = now; return; }   // M4b: or a panel
    if (c.story && !c.story.paused) {       // M4a: a story between parts is busy, unless its next part never came
      if (now - c.story.askedAt < STORY_STALL_MS) { c.lastAct = now; return; }
      c.story.paused = true;
    }
    if (now - c.lastAct >= CONVO_IDLE_S * 1000) { endConvo(c, 'idle'); }
  }

  // Every finished thing the resident says in Live gets the same emergency check as Normal talk (never missed),
  // then the goodbye check. The promise is kept: skills wait for it.
  function liveHeard(c, text) {
    text = String(text == null ? '' : text).trim();
    c.heard = text;
    c.lastAct = Date.now();
    var tail = heardFinal(c.heardTrack, text);   // M4a: their last words, not what built up before a pause
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
      if ((j && j.garbled) || notEnglish(tail)) { return; }   // M4a: a garbled line is never a goodbye
      if (isGoodbye(tail)) { endConvo(c, 'bye'); }
    });
    return p;
  }

  function liveEmergency(c, j) {
    c.story = null;   // M4a: the emergency words, never a story over them
    clearTimeout(c.byeWait);   // M4a
    try { window.MaryLive.stopSpeaking(); } catch (e) { log(e); }
    var words = (j && j.say) ? String(j.say) : MSG.emergency;
    if (c.ending) {                         // no goodbye now: she stays with them
      c.ending = false;
      c.byeDone = false;    // M4a
      c.byeAudio = false;   // M4a
      clearTimeout(c.byeTimer);
      clearInterval(c.idleTimer);
      c.idleTimer = setInterval(function () { liveIdleCheck(c); }, 1000);
    }
    c.lastAct = Date.now();
    if (S.screen !== 'emergency') { show('emergency'); }
    showCaption(words);
    capLiveEmergency(words);   // M4b: all of it at once (whole), before her voice
    c.saidText = '';                        // M4a: /api/mary/heard saved the emergency words; not saved twice
    c.saidSkip = true;
    if (!greetLive(LIVE_SAFETY + spokenNumbers(words) + ')')) { c.saidSkip = false; say(words, 'alert'); }
  }

  // --- M4a: in Live, Live speaks everything. A story comes from the server whole; the page hands it to her in parts,
  // each its own turn, so she starts each part fresh. A tool call is answered at once, with the first part. ---
  var TOOL_REFUSED = { error: 'emergency', note: 'Not done. Stay with them about their safety and do not mention this.' };
  var LIVE_BYE_QUIET_MS = 700;     // a goodbye counts once this long has gone by with no new words
  var STORY_STALL_MS = 15000;      // a next part that hasn't started after this long stops counting as busy
  var STATUS_LOCK_MS = 2500;       // a talk's voice is locked from a fresh status, waiting at most this long

  // --- M4a story helpers (pure; tests/test_story_js.py runs this block with Node) ---
  var STORY_PART_EVERY = 70;       // with no paragraphs to go by, cut at the sentence end nearest this many words
  var STORY_PART_LONG = 90;        // a paragraph over this many words is cut the same way
  var STORY_PART_TINY = 20;        // a part under this many words joins the next one
  var STORY_PARTS_MAX = 6;
  var STORY_PART_NOTE = 'Say this part out loud exactly as written, every word, at the speed of ordinary conversation. Add nothing after it. The next part comes by itself.';
  var STORY_END_NOTE = 'That was the end of the story.';
  var LIVE_HEARD_GAP_MS = 1200;    // this long with no new words, and what comes next is a new thing they're saying
  function storyWordCount(t) { return t.split(/\s+/).filter(Boolean).length; }
  function storyRuns(text) {       // sentences gathered into runs of about STORY_PART_EVERY words
    var list = splitSentences(text, true).sentences, out = [], cur = '', words = 0;
    for (var i = 0; i < list.length; i++) {
      var w = storyWordCount(list[i]);
      if (cur && Math.abs(words + w - STORY_PART_EVERY) > Math.abs(words - STORY_PART_EVERY)) {
        out.push(cur);
        cur = '';
        words = 0;
      }
      cur = cur ? cur + ' ' + list[i] : list[i];
      words += w;
    }
    if (cur) { out.push(cur); }
    return out;
  }
  // A story cut into parts for her to say one at a time. Paragraphs first, because cleanSpeech flattens the newlines.
  function storyParts(text) {
    var paras = String(text == null ? '' : text).split(/\n\s*\n/).map(cleanSpeech).filter(Boolean);
    var parts = [];
    paras.forEach(function (p) {
      if (paras.length === 1 || storyWordCount(p) > STORY_PART_LONG) { parts = parts.concat(storyRuns(p)); }
      else { parts.push(p); }
    });
    for (var i = 0; i < parts.length && parts.length > 1;) {   // a tiny part joins the next; the last joins the one before
      if (storyWordCount(parts[i]) >= STORY_PART_TINY) { i++; continue; }
      if (i + 1 < parts.length) { parts.splice(i, 2, parts[i] + ' ' + parts[i + 1]); }
      else { parts.splice(i - 1, 2, parts[i - 1] + ' ' + parts[i]); i--; }
    }
    while (parts.length > STORY_PARTS_MAX) {                   // the two shortest neighbors join, so no part gets huge
      var at = 0, best = Infinity;
      for (var k = 0; k + 1 < parts.length; k++) {
        var both = storyWordCount(parts[k]) + storyWordCount(parts[k + 1]);
        if (both < best) { best = both; at = k; }
      }
      parts.splice(at, 2, parts[at] + ' ' + parts[at + 1]);
    }
    return parts;
  }
  // The next part as Live's answer; moves the story on. No more parts: it says so.
  function storyStep(st) {
    if (!st || st.next >= st.parts.length) { return { done: true, note: STORY_END_NOTE }; }
    var part = st.parts[st.next];
    st.next++;
    st.paused = false;
    return { part: part, more: st.next < st.parts.length, note: STORY_PART_NOTE };
  }
  function storyNextLine(part, last) {
    return '(Go on with the story. Say this next part out loud exactly as written, every word, at the same speed, ' +
      'and add nothing after it' + (last ? '. It is the end of the story, so stop after its last line' : '') + ': ' + part + ')';
  }
  // Live's heard text keeps growing and can hold earlier words. This is what they've said since their last pause.
  // st ({text, mark, at}) is kept between pieces.
  function heardTail(st, text, now) {
    if (text.indexOf(st.text) !== 0) { st.mark = 0; }          // not the same text growing: a new turn of theirs
    else if (text.length > st.text.length && now - st.at > LIVE_HEARD_GAP_MS) { st.mark = st.text.length; }
    if (text !== st.text) { st.at = now; }
    st.text = text;
    return text.slice(st.mark).trim();
  }
  // The same for a finished line (or a typed one, which never came in pieces).
  function heardFinal(st, text) {
    return (st && st.text.trim() === text) ? st.text.slice(st.mark).trim() : text;
  }
  // Live's transcript sometimes comes back in another script. The same rule as mary.not_english: most of the letters
  // are at code point 0x250 or above. Spaces, digits, punctuation, symbols and emoji aren't letters.
  var LATIN_LETTER = /[A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u024F]/;
  var HIGH_NOT_LETTER = /[\u02B0-\u036F\u2000-\u2BFF\u3000-\u303F\uD800-\uF8FF\uFE00-\uFE6F\uFF00-\uFF20\uFF3B-\uFF40\uFF5B-\uFF65\uFFE0-\uFFFF]/;
  function notEnglish(t) {
    var letters = 0, high = 0;
    Array.from(String(t == null ? '' : t)).forEach(function (ch) {
      var cp = ch.codePointAt(0);
      if (cp < 0x250) { if (LATIN_LETTER.test(ch)) { letters++; } return; }
      if (cp > 0xFFFF || HIGH_NOT_LETTER.test(ch)) { return; }
      letters++;
      high++;
    });
    return letters > 0 && high / letters > 0.5;
  }
  // The one voice for a talk. Normal is Gemini TTS unless its day is spent. Kokoro is for Offline, and for lines
  // with Live chosen and no Live open. '' is the computer's own voice: only when Kokoro isn't here.
  function micMissGoesOn(misses) { return !(misses >= 1); }   // the second miss in a row ends the talk, as in convoListen
  function talkVoice(mode, ttsSpent, order) {
    var kokoro = (order || []).indexOf('offline') >= 0 ? 'offline' : '';
    if (mode === 'normal') { return ttsSpent ? kokoro : 'normal'; }
    return (mode === 'offline' || mode === 'live') ? kokoro : '';
  }
  // The voice after `from` in the talk order (Live is never a voice for sentences); '' = the computer's own voice.
  function voiceAfter(order, from) {
    var m = nextMode(order, from);
    while (m === 'live') { m = nextMode(order, m); }
    return (m === 'normal' || m === 'offline') ? m : '';
  }
  // --- end M4a story helpers ---

  function storyTake(c) {   // the next part as Live's answer; the story ends with its last part
    var st = c.story, a = storyStep(st);
    if (st) {
      st.sounded = false;
      st.askedAt = Date.now();
      if (st.next >= st.parts.length) { c.story = null; }
    }
    return a;
  }

  // Live's tell_story came back with a story: Live gets its first part now, and the page brings the rest.
  function storyFromTool(c, r) {
    var list = (r && r.functionResponses) || [], fr = null;
    for (var i = 0; i < list.length; i++) {
      if (list[i] && list[i].name === 'tell_story' && list[i].response && list[i].response.story) { fr = list[i]; }
    }
    if (!fr) { return r; }
    if (S.convo !== c || !c.live || (c.toolGone && c.toolGone[fr.id])) { return r; }
    if (c.ending) { r.functionResponses = list.filter(function (x) { return x !== fr; }); return r; }   // no story now
    if (S.screen === 'emergency') { fr.response = TOOL_REFUSED; return r; }
    var parts = storyParts(fr.response.story);
    if (!parts.length) { return r; }
    c.story = { id: fr.id, parts: parts, next: 0, paused: false, sounded: false, askedAt: 0 };
    fr.response = storyTake(c);
    return r;
  }

  // Her turn has been fully heard: the next part, as a new turn of hers. sounded: never on the back of her lead-in,
  // which can still be finishing when the first part goes out.
  function storyNext(c) {
    var st = c.story;
    if (!st || st.paused || !st.sounded || c.ending || S.screen === 'emergency') { return; }
    var a = storyTake(c);
    if (!a.part) { return; }
    if (!greetLive(storyNextLine(a.part, !a.more))) { c.story = null; }
  }

  // Live says a tool call is off (they talked over it): nothing is answered for it (talklive.js drops the answer).
  function liveToolCancelled(c, ids) {
    c.toolGone = c.toolGone || {};
    for (var i = 0; i < (ids || []).length; i++) { c.toolGone[ids[i]] = true; }
    if (c.story && c.toolGone[c.story.id]) { c.story.paused = true; }
  }

  // Every growing piece of what the resident is saying (Live's onHeard). True = a garbled line: not shown, never a
  // goodbye or a cut-in. Real words while she is quiet between parts hold the story; a goodbye that then stays quiet
  // ends the talk, and later pieces only cancel it if what they've said stops being a goodbye.
  function liveHeardPiece(c, t) {
    c.heardTrack = c.heardTrack || { text: '', mark: 0, at: 0 };
    t = String(t == null ? '' : t);
    var tail = heardTail(c.heardTrack, t, Date.now());
    if (notEnglish(t) || notEnglish(tail)) { return true; }
    var bye = !c.ending && S.screen !== 'emergency' && isGoodbye(tail);
    var st = c.story;
    if (st && !st.paused && (bye || (!liveSpeaking() && !SILENCE_NOISE.test(tail)))) { st.paused = true; }
    clearTimeout(c.byeWait);
    if (bye) { c.byeWait = setTimeout(function () { liveByeNow(c); }, LIVE_BYE_QUIET_MS); }
    return false;
  }

  // A spoken goodbye: Live says it in her own voice, then the session closes. Never a second voice. Their words still
  // go through liveHeard once; if that finds an emergency, liveEmergency takes the talk back.
  function liveByeNow(c) {
    clearTimeout(c.byeWait);
    if (S.convo !== c || c.ending || !c.live || S.screen === 'emergency') { return; }
    c.ending = true;
    c.byeAudio = false;
    c.byeDone = false;
    c.story = null;
    clearInterval(c.idleTimer);
    try { window.MaryLive.stopSpeaking(); } catch (e) { log(e); }
    if (!greetLive(liveBye())) { finishLive(c); return; }
    c.byeTimer = setTimeout(function () { liveByeCap(c, false); }, LIVE_BYE_MAX_MS);
  }

  // Live understood a goodbye itself (this catches a mishearing the page's word check can't). It has said its goodbye,
  // so the call is never answered and she says nothing more: the talk closes once her sound has drained.
  function liveEndTalk(c) {
    if (S.convo !== c || !c.live) { return; }
    clearTimeout(c.byeWait);
    c.story = null;
    var waiting = c.ending && !c.byeAudio;   // the page's goodbye was asked for and hasn't started: let it come
    c.ending = true;
    clearInterval(c.idleTimer);
    if (waiting) { return; }                 // its cap (c.byeTimer) stands
    c.byeDone = true;
    if (!liveSpeaking()) { finishLive(c); return; }
    clearTimeout(c.byeTimer);
    c.byeTimer = setTimeout(function () { liveByeCap(c, false); }, LIVE_BYE_MAX_MS);
  }
  // --- end M4a ---

  function liveToolCall(c, tc) {
    var calls = (tc && tc.functionCalls) || [];
    var heard = c.heard || '';
    c.toolBusy++;
    return Promise.resolve(c.heardCheck).then(function (j) {
      if (liveToolGate(j, S.screen === 'emergency') === 'refuse') {
        return { functionResponses: calls.map(function (fc) { return { id: fc.id, name: fc.name, response: TOOL_REFUSED }; }) };
      }
      // M4a: story_more and end_talk are the page's own; end_talk is never answered, so she says nothing more
      var own = [], rest = [];
      calls.forEach(function (fc) {
        if (fc.name === 'end_talk') { liveEndTalk(c); }
        else if (fc.name === 'story_more') { own.push({ id: fc.id, name: fc.name, response: storyTake(c) }); }
        else { rest.push(fc); }
      });
      if (!rest.length) { return { functionResponses: own }; }
      if (!window.MarySkills) { throw new Error('skills are not loaded'); }
      return window.MarySkills.handleLiveToolCall({ functionCalls: rest }, heard).then(function (r) {
        r.functionResponses = own.concat(r.functionResponses);
        return r;
      });
    }).then(function (r) {
      return storyFromTool(c, r);   // M4a: the first part of a story, answered at once
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
    if (c.story) { c.story.paused = true; }   // M4a: typing is a cut-in too
    setCaption('');   // Andy (2026-10-30): his own words are never shown
    c.lastAct = Date.now();
    liveHeard(c, text).then(function (j) {
      if (S.convo !== c || c.ending || (j && j.emergency)) { return; }   // M4a: c.ending: a typed goodbye
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
  // tapped: the resident asked (Talk tap, wake word), so it listens even on the emergency screen (M4a)
  function convoListen(c, tapped) {
    if (S.convo !== c || c.ending || c.live) { return; }
    if (S.screen === 'emergency' && !tapped) { c.paused = true; setPhase('idle'); updateTalkButton(); return; }
    c.paused = false;
    var my = newTurn();
    listenOnce({ convo: true }).then(function (text) {
      if (S.convo !== c || my !== S.turn) { return undefined; }
      if (!text) {
        // M4a: a second miss in a row (a mic that isn't recording, a noisy room) ends the talk instead of nagging
        if (S.listenReason === 'idle' || c.misses >= 1) { endConvo(c, 'idle'); return undefined; }
        c.misses++;
        return say(MSG.notCaught, 'talking').then(function () { convoNext(c); });
      }
      c.misses = 0;
      if (isGoodbye(text)) { return convoBye(c, text); }
      return talkTo(text).then(function () { convoNext(c); });
    }).catch(function (e) {
      if (S.convo !== c) { return undefined; }
      if (e && e.cancelled) { convoNext(c); return undefined; }   // something else took the turn: go on after it
      log(e);
      if (micMissGoesOn(c.misses)) {   // M4a: one failed listen is a miss, like hearing nothing: the talk goes on
        c.misses++;
        var waking = e && e.stage === 'stop' && e.name === 'AbortError';   // the first stop waits for the voice model
        return say(waking ? MSG.waking : MSG.notCaught, waking ? 'sorry' : 'talking').then(function () { convoNext(c); });
      }
      closeConvo(c);
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
    if ((S.screen !== 'everyday' && !skillScreen()) || uiOpen() || !$('typing').hidden) { closeConvo(c); return; }   // M4b: or a panel
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
      var voice = c.voice;   // M4a: her goodbye in the voice of this talk
      closeConvo(c);
      if (!j || j.emergency) { return talkTo(text); }   // the full talk path: the emergency screen and her words
      setPhase('idle');
      return say(goodbyeLine(), 'happy', voice);
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

  // M9c: typed marks words typed in the box in Normal/Offline, so the server can tell them from speech
  function talkBody(text, typed) {
    var b = { text: text, screen: skillScreen() };   // skills hook (M13)
    if (typed) { b.typed = true; }
    return b;
  }

  async function streamReply(text, T, ctrl) {
    var init = {
      method: 'POST',
      cache: 'no-store',
      headers: { 'X-Tracker': '1', 'Content-Type': 'application/json' },
      body: JSON.stringify(talkBody(text, T.typed))   // skills hook (M13); M9c
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

  async function plainReply(text, ctrl, typed) {   // M9c: typed
    return await api('POST', '/api/mary/talk', talkBody(text, typed), { signal: ctrl ? ctrl.signal : undefined, ms: 30000 });
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
  async function talkTo(text, typed) {   // M9c: typed = from the typing box
    text = String(text == null ? '' : text).trim();
    if (!text) { return; }
    App.onActivity();
    var turn = newTurn();
    closeMenu();
    closeTyping(false);
    setCaption('');   // Andy (2026-10-30): his own words are never shown
    setPhase('thinking');

    var T = { turn: turn, typed: !!typed, streamed: '', rest: '', mood: '', sess: null, gotLine: false, gotResponse: false, dead: false };   // M9c: typed
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
        d = await Promise.race([plainReply(text, ctrl, T.typed), timeoutP]);      // streaming failed before any answer came
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

  // ---------------------------------------------------------------- M4b: the one Menu button, its menu and three panels
  var MENU_IDLE_MS = 20000;      // M4b: the menu closes after 20 s with nothing done in it
  var PANEL_IDLE_MS = 120000;    // M4b: a panel left alone goes back to her face after 2 minutes
  var PANELS = ['canPanel', 'infoPanel', 'choosePanel'];
  var M = { timer: null, panel: null, extra: [] };   // M4b: extra = the skills' rows for "Things Mary can do"

  function hasWindow() {
    return !!(window.pywebview && window.pywebview.api && typeof window.pywebview.api.close_window === 'function');
  }
  function menuOpen() { return !$('menu').hidden; }
  function uiOpen() { return menuOpen() || !!M.panel; }   // M4b: the menu or a panel is over her face
  function armIdle(ms) {
    clearTimeout(M.timer);
    M.timer = setTimeout(function () { if (M.panel) { closePanel(false); } else if (menuOpen()) { closeMenu(false); } }, ms);
  }
  function menuItems() {
    return [].filter.call($('menu').querySelectorAll('.mi'), function (b) { return !b.hidden && b.offsetParent !== null; });
  }

  function openMenu() {
    if (M.panel) { closePanel(false); }
    refreshLabels();
    $('closeBtn').hidden = !hasWindow();
    if ((S.screen === 'choose' || S.screen === 'hello') && !hasWindow()) { return; }   // first run in a browser: nothing to offer
    $('menu').hidden = false;
    var b = $('menuBtn');
    b.classList.add('open');
    b.setAttribute('aria-expanded', 'true');
    $('menuBtnLbl').textContent = 'Hide menu';
    try { face.setMenuOpen(true); } catch (e) { log(e); }   // M4b: she moves aside and looks at it
    capCall(function () { cap.setSide(true); });            // M4b: her words keep clear of it
    armIdle(MENU_IDLE_MS);
    var items = menuItems();
    try { if (items.length) { items[0].focus(); } } catch (e) { /* nothing */ }
  }
  function closeMenu(refocus) {
    var was = menuOpen();
    $('menu').hidden = true;
    if (!M.panel) { clearTimeout(M.timer); }
    var b = $('menuBtn');
    b.classList.remove('open');
    b.setAttribute('aria-expanded', 'false');
    $('menuBtnLbl').textContent = 'Menu';
    try { face.setMenuOpen(false); } catch (e) { log(e); }   // M4b
    capCall(function () { cap.setSide(false); });            // M4b
    if (refocus && was) { try { b.focus(); } catch (e) { /* nothing */ } }
  }
  // M4b: side by side with a skill: her face slides into the left 40% and turns toward the right 60%, her words under her.
  // The one call a screen needs. data-aside comes first, because the caption measures its words in its new size.
  function sideBySide(on) {
    on = !!on;
    var root = $('scr');
    if (on) { root.setAttribute('data-aside', '1'); } else { root.removeAttribute('data-aside'); }
    try { face.setAside(on); } catch (e) { log(e); }
    capCall(function () { cap.setAside(on); });
  }
  function onMenuKey(ev) {   // M4b: arrow keys move through the menu
    var items = menuItems(), i = items.indexOf(D.activeElement), j = -1;
    if (ev.key === 'ArrowDown') { j = (i + 1) % items.length; }
    else if (ev.key === 'ArrowUp') { j = (i - 1 + items.length) % items.length; }
    else if (ev.key === 'Home') { j = 0; }
    else if (ev.key === 'End') { j = items.length - 1; }
    if (j < 0 || !items.length) { return; }
    ev.preventDefault();
    try { items[j].focus(); } catch (e) { /* nothing */ }
  }
  // Any tap or key while the menu or a panel is open keeps it open; a tap on her face (off the menu) closes the menu.
  function onUiTouch(ev) {
    if (!uiOpen()) { return; }
    armIdle(M.panel ? PANEL_IDLE_MS : MENU_IDLE_MS);
    if (ev.type !== 'pointerdown' || M.panel) { return; }
    var t = ev.target;
    if (t && t.closest && (t.closest('#menu') || t.closest('#menuBtn'))) { return; }
    closeMenu(false);
  }
  function trapTab(ev) {   // M4b: Tab stays inside an open panel (it is a dialog)
    var card = $(M.panel).querySelector('.sheetcard');
    var f = [].filter.call(card.querySelectorAll('button, a[href]'), function (el) { return el.offsetParent !== null; });
    if (!f.length) { return; }
    var first = f[0], last = f[f.length - 1];
    if (ev.shiftKey && (D.activeElement === first || !card.contains(D.activeElement))) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && (D.activeElement === last || !card.contains(D.activeElement))) { ev.preventDefault(); first.focus(); }
  }

  function openPanel(id) {
    if (M.panel && M.panel !== id) { $(M.panel).hidden = true; }
    M.panel = id;
    refreshLabels();
    if (id === 'canPanel') { fillCan(); } else if (id === 'infoPanel') { fillInfo(); } else { fillChoose(); }
    $(id).hidden = false;
    $(id).scrollTop = 0;
    armIdle(PANEL_IDLE_MS);
    setTimeout(function () { try { $(id).querySelector('.back').focus(); } catch (e) { /* nothing */ } }, 30);
  }
  function closePanel(refocus) {
    if (!M.panel) { return; }
    $(M.panel).hidden = true;
    M.panel = null;
    clearTimeout(M.timer);
    stopSample();
    if (refocus) { try { $('menuBtn').focus(); } catch (e) { /* nothing */ } }
  }

  // A big row: its words, an optional second line, and what a tap does.
  function rowBtn(text, sub, onTap, attrs) {
    var b = D.createElement('button');
    b.type = 'button';
    b.className = 'row';
    var t = D.createElement('span');
    t.className = 'txt';
    var m = D.createElement('span');
    m.textContent = text;
    t.appendChild(m);
    if (sub) { var s2 = D.createElement('span'); s2.className = 'say'; s2.textContent = sub; t.appendChild(s2); }
    b.appendChild(t);
    if (attrs) { for (var k in attrs) { if (attrs.hasOwnProperty(k)) { b.setAttribute(k, attrs[k]); } } }
    if (onTap) { b.addEventListener('click', onTap); }
    return b;
  }
  function sayLine(words) { return 'Say: “' + words + '”'; }

  // --- Things Mary can do: things to say; a tap does the same thing
  var CAN = [
    { act: 'slower', text: 'Slow down', say: 'slow down' },
    { act: 'faster', text: 'Speed up', say: 'speed up' },
    { act: 'quieter', text: 'Talk quieter', say: 'quieter' },
    { act: 'louder', text: 'Talk louder', say: 'speak up' },
    { act: 'more_time', text: 'Give me more time', say: 'give me more time' },
    { act: 'type', text: 'Type to {n}' },
    { act: 'notes', text: 'My notes' }
  ];
  function fillCan() {
    var box = $('canList'), n = companionName(S.companion);
    box.textContent = '';
    CAN.forEach(function (it) {
      box.appendChild(rowBtn(it.text.replace('{n}', n), it.say ? sayLine(it.say) : '', function () { closePanel(true); doThing(it.act); }));
    });
    M.extra.forEach(function (x) {   // the switched-on skills that have a screen (skills.js)
      box.appendChild(rowBtn(x.label, x.say ? sayLine(x.say) : '', function () {
        closePanel(true);
        try { x.open(); } catch (e) { log(e); }
      }));
    });
  }
  function addThing(x) {   // M4b: skills.js lists a skill's screen here (the old menu buttons are gone)
    if (!x || !x.name || !x.label || typeof x.open !== 'function') { return; }
    M.extra = M.extra.filter(function (o) { return o.name !== x.name; });
    M.extra.push({ name: String(x.name), label: String(x.label), say: x.say ? String(x.say) : '', open: x.open });
    if (M.panel === 'canPanel') { fillCan(); }
  }
  function doThing(act) {
    // --- skills hook (M13) --- voice_comfort does these; the old code is the fallback
    if (act === 'slower') { skillMenu('slower').then(function (ok) { if (!ok) { adjust('rate', -0.08); } }); }
    else if (act === 'faster') { skillMenu('faster').then(function (ok) { if (!ok) { adjust('rate', 0.08); } }); }
    else if (act === 'quieter') { skillMenu('quieter').then(function (ok) { if (!ok) { adjust('volume', -0.1); } }); }
    else if (act === 'louder') { skillMenu('louder').then(function (ok) { if (!ok) { adjust('volume', 0.1); } }); }
    else if (act === 'more_time') {
      skillMenu('more_time').then(function (ok) {
        if (!ok) {
          newTurn();
          api('PUT', '/api/settings', { listen_wait: 4 }).then(function () { return refreshStatus(); }).catch(noop);
          say("I'll wait longer for you.");
          return;
        }
        refreshStatus().catch(noop);   // the longer wait applies from the next turn
      });
    }
    else if (act === 'switch') { skillMenu('switch_companion', 'happy').then(function (ok) { if (!ok) { switchCompanion(); } }); }
    // --- end skills hook ---
    else if (act === 'type') { openTyping(); }
    else if (act === 'notes') { window.location.href = '/?from=mary'; }
  }

  // --- Choose Mary or Sam
  function fillChoose() {
    var box = $('chooseList');
    box.textContent = '';
    box.setAttribute('role', 'radiogroup');
    box.setAttribute('aria-labelledby', 'chooseTitle');
    ['mary', 'him'].forEach(function (c) {
      var now = c === S.companion;
      box.appendChild(rowBtn(companionName(c), now ? 'Talking with you now' : '', function () {
        closePanel(true);
        if (c !== S.companion) { doThing('switch'); }
      }, { role: 'radio', 'aria-checked': now ? 'true' : 'false' }));
    });
  }

  // --- My info: how she talks, her voice, how long she waits, skills on or off, and a link to the rest
  function infoNote(t) { $('infoSaved').textContent = t || ''; }
  function savedNote() { return 'Saved. ' + companionName(S.companion) + ' will use this the next time you talk.'; }
  function saveSetting(body, after) {
    infoNote('Saving…');
    return api('PUT', '/api/settings', body).then(function () {
      return refreshStatus().catch(noop);   // the new setting applies from the next talk
    }).then(function () {
      infoNote(savedNote());
      if (after) { after(); }
    }, function (e) {
      log(e);
      infoNote("Sorry, that didn't save. Please try again.");
    });
  }
  function radioRows(box, items, isOn, onPick) {
    box.textContent = '';
    items.forEach(function (it) {
      var attrs = { role: 'radio', 'aria-checked': isOn(it) ? 'true' : 'false' };
      var b = rowBtn(it.t, it.h, null, attrs);
      b.addEventListener('click', function () {
        if (b.getAttribute('aria-checked') === 'true') { return; }
        [].forEach.call(box.querySelectorAll('[role="radio"]'), function (o) { o.setAttribute('aria-checked', o === b ? 'true' : 'false'); });
        onPick(it);
      });
      box.appendChild(b);
    });
  }
  function fillInfo() {
    infoNote('');
    var him = S.companion === 'him', Her = him ? 'His' : 'Her', she = him ? 'he' : 'she';
    radioRows($('modeList'), [
      { v: 'live', t: 'Live (best)', h: Her + ' natural voice. Talk back and forth, and cut in any time. Needs the internet.' },
      { v: 'normal', t: 'Normal', h: 'This computer turns your words into text, then ' + she + ' answers in ' + Her.toLowerCase() + ' voice. Needs the internet.' },
      { v: 'offline', t: 'Offline', h: Her + ' voice is made on this computer.' + (S.offlineReady === false ? ' Not set up on this computer yet.' : '') }
    ], function (it) { return (S.talkMode || 'live') === it.v; }, function (it) {
      saveSetting({ talk_mode: it.v }, fillVoices);   // the voice list follows the talk mode
    });
    radioRows($('waitList'), [
      { v: 2.5, t: 'Usual', h: 'About 2 and a half seconds of quiet.' },
      { v: 4, t: 'More time', h: 'About 4 seconds. You can also say “give me more time”.' }
    ], function (it) { return (QUIET_END_S >= 3.5) === (it.v >= 3.5); }, function (it) {
      saveSetting({ listen_wait: it.v });
    });
    fillWake();   // M6
    fillVoices();
    fillSkills();
    fillMemories();   // M9c
  }
  // M6: listen for her name, On or Off; one plain line when it cannot run on this computer
  function fillWake() {
    var box = $('wakeList');
    if (!box) { return; }
    if (!S.wakeReady) {
      infoLead(box, S.wakeReason || ('Listening for ' + (S.companion === 'him' ? 'his' : 'her') + " name isn't installed on this computer."));
      return;
    }
    var n = companionName(S.companion);
    radioRows(box, [
      { v: true, t: 'On', h: 'Say “Hey ' + n + '” and ' + (S.companion === 'him' ? 'he' : 'she') + ' answers, while this screen is open.' },
      { v: false, t: 'Off', h: 'Tap the menu to talk instead.' }
    ], function (it) { return !!S.wakeWord === it.v; }, function (it) {
      saveSetting({ wake_word: it.v ? '1' : '0' }, wakeSync);   // refreshStatus has set S.wakeWord; start or stop the loop
    });
  }
  function infoLead(box, t) {
    box.textContent = '';
    var p = D.createElement('p');
    p.className = 'lead';
    p.textContent = t;
    box.appendChild(p);
  }
  function fillVoices() {
    var box = $('voiceList'), c = S.companion;
    infoLead(box, 'Getting the voices…');
    api('GET', '/api/mary/voices').then(function (v) {
      if (M.panel !== 'infoPanel') { return; }
      var offline = S.talkMode === 'offline', kind = offline ? 'kokoro' : 'gemini';
      var gender = c === 'him' ? 'male' : 'female';
      var chosen = String((v && v.chosen && v.chosen[c]) || ''), parts = chosen.split(':');
      var chosenKind = parts[0] || '', chosenName = parts[1] || '';
      var mine = chosenKind === 'kokoro' ? offline : !offline && !!chosenName;   // a pick for this kind of voice
      var list = ((v && v.candidates) || []).filter(function (x) { return x.kind === kind && x.gender === gender; });
      if (!list.length || (offline && !list.some(function (x) { return x.ready; }))) {
        infoLead(box, 'The offline voices are not set up on this computer yet.');
        return;
      }
      box.textContent = '';
      list.forEach(function (x, i) {
        var on = mine ? x.voice === chosenName : i === 0;   // nothing picked: the first one is the one in use
        var row = D.createElement('div');
        row.className = 'row';
        var pick = rowBtn(x.about || x.voice, '', null, { role: 'radio', 'aria-checked': on ? 'true' : 'false' });
        pick.className = 'main';
        if (!x.ready) { pick.setAttribute('aria-disabled', 'true'); }
        pick.addEventListener('click', function () {
          if (pick.getAttribute('aria-disabled') === 'true' || pick.getAttribute('aria-checked') === 'true') { return; }
          [].forEach.call(box.querySelectorAll('[role="radio"]'), function (o) { o.setAttribute('aria-checked', o === pick ? 'true' : 'false'); });
          var body = {};
          body[c === 'him' ? 'voice_sam' : 'voice_mary'] = x.id;
          saveSetting(body);
        });
        var hear = D.createElement('button');
        hear.type = 'button';
        hear.className = 'side';
        hear.textContent = 'Hear it';
        hear.setAttribute('aria-label', 'Hear the ' + (x.about || x.voice) + ' voice');
        hear.addEventListener('click', function () { playSample(x.id, hear); });
        row.appendChild(pick);
        if (x.ready) { row.appendChild(hear); }
        box.appendChild(row);
      });
    }, function (e) { log(e); infoLead(box, "Sorry, I couldn't get the voices just now."); });
  }
  var SMP = { audio: null, url: '' };
  function stopSample() {
    if (SMP.audio) { try { SMP.audio.pause(); } catch (e) { /* nothing */ } SMP.audio = null; }
    if (SMP.url) { try { URL.revokeObjectURL(SMP.url); } catch (e) { /* nothing */ } SMP.url = ''; }
  }
  function playSample(id, btn) {
    if (btn.getAttribute('aria-disabled') === 'true') { return; }
    stopSample();
    btn.textContent = 'Getting it…';
    btn.setAttribute('aria-disabled', 'true');
    function fin() { btn.textContent = 'Hear it'; btn.removeAttribute('aria-disabled'); }
    fetch('/api/mary/voices/sample', { method: 'POST', cache: 'no-store',
      headers: { 'X-Tracker': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ id: id }) })
      .then(function (r) { if (!r.ok) { throw new Error('HTTP ' + r.status); } return r.blob(); })
      .then(function (blob) {
        if (M.panel !== 'infoPanel') { return; }
        SMP.url = URL.createObjectURL(blob);
        var a = new Audio(SMP.url);
        a.volume = Math.max(0, Math.min(1, Number(S.volume) || 1));
        SMP.audio = a;
        a.addEventListener('ended', function () { if (SMP.audio === a) { stopSample(); } });
        return a.play();
      })
      .then(fin, function (e) { log(e); fin(); infoNote("Sorry, I couldn't play that voice just now."); });
  }
  function fillSkills() {
    var box = $('skillList');
    infoLead(box, 'Getting the list…');
    api('GET', '/api/mary/skills').then(function (r) {
      if (M.panel !== 'infoPanel') { return; }
      var list = (r && r.skills) || [];
      if (!list.length) { infoLead(box, 'Nothing here yet.'); return; }
      box.textContent = '';
      list.forEach(function (sk) {
        var row = D.createElement('div');
        row.className = 'row';
        var t = D.createElement('span');
        t.className = 'txt';
        var m = D.createElement('span');
        m.textContent = sk.title || sk.name;
        t.appendChild(m);
        if (sk.summary) { var s2 = D.createElement('span'); s2.className = 'say'; s2.textContent = sk.summary; t.appendChild(s2); }
        var b = D.createElement('button');
        b.type = 'button';
        b.className = 'side';
        if (sk.locked) {
          b.textContent = 'Set by your helper';
          b.setAttribute('aria-disabled', 'true');
        } else {
          b.textContent = sk.on ? 'On' : 'Off';
          b.setAttribute('aria-pressed', sk.on ? 'true' : 'false');
        }
        b.setAttribute('aria-label', (sk.title || sk.name) + ': ' + b.textContent);
        b.addEventListener('click', function () {
          if (sk.locked) { infoNote('Your helper set this one.'); return; }
          infoNote('Saving…');
          api('PUT', '/api/mary/skills/' + encodeURIComponent(sk.name), { on: !sk.on }).then(function () {
            sk.on = !sk.on;
            b.textContent = sk.on ? 'On' : 'Off';
            b.setAttribute('aria-pressed', sk.on ? 'true' : 'false');
            b.setAttribute('aria-label', (sk.title || sk.name) + ': ' + b.textContent);
            infoNote(savedNote());
          }, function (e) {
            log(e);
            infoNote(/locked/.test(String(e && e.message)) ? 'Your helper set this one.' : "Sorry, that didn't save. Please try again.");
          });
        });
        row.appendChild(t);
        row.appendChild(b);
        box.appendChild(row);
      });
    }, function (e) { log(e); infoLead(box, "Sorry, I couldn't get the list just now."); });
  }

  // M9c: what she remembers. Memories are untrusted text: createElement and textContent only, never innerHTML.
  var MEM_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  function memDate(s) {   // "2026-10-30" read by its parts, so the timezone can't shift the day
    var p = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || '')), mo = p && MEM_MONTHS[Number(p[2]) - 1];
    return mo ? mo + ' ' + Number(p[3]) + ', ' + p[1] : '';
  }
  function memRow(mem, box, empty) {
    var text = String(mem.text || '');
    var row = D.createElement('div');
    row.className = 'row';
    var t = D.createElement('span');
    t.className = 'txt';
    var m = D.createElement('span');
    m.textContent = text;
    t.appendChild(m);
    var when = memDate(mem.date);
    if (when) { var s2 = D.createElement('span'); s2.className = 'say'; s2.textContent = when; t.appendChild(s2); }
    var b = D.createElement('button');
    b.type = 'button';
    b.className = 'side';
    b.textContent = 'Remove';
    b.setAttribute('aria-label', 'Remove: ' + text);
    b.addEventListener('click', function () {
      if (b.getAttribute('aria-disabled') === 'true') { return; }   // a second tap while the first is on its way
      b.setAttribute('aria-disabled', 'true');
      infoNote('Removing…');
      api('DELETE', '/api/mary/memories/' + encodeURIComponent(mem.id)).then(function () {
        if (row.parentNode) { row.parentNode.removeChild(row); }
        infoNote('Removed. ' + companionName(S.companion) + " won't bring that up again.");
        if (!box.querySelector('.row')) { infoLead(box, empty); }
      }, function (e) {
        log(e);
        b.removeAttribute('aria-disabled');
        infoNote("Sorry, that didn't go through. Please try again.");
      });
    });
    row.appendChild(t);
    row.appendChild(b);
    return row;
  }
  function fillMemories() {
    var box = $('memList');
    if (!box) { return; }
    var empty = 'Nothing saved yet. As you talk, ' + companionName(S.companion) + ' keeps what matters here.';
    infoLead(box, 'Getting the list…');
    api('GET', '/api/mary/memories').then(function (r) {
      if (M.panel !== 'infoPanel') { return; }
      var list = (r && r.memories) || [];
      if (!list.length) { infoLead(box, empty); return; }
      box.textContent = '';
      list.forEach(function (mem) { box.appendChild(memRow(mem, box, empty)); });
    }, function (e) { log(e); infoLead(box, "Sorry, I couldn't get the list just now."); });
  }

  // The menu's Talk row: start a talk, or "Stop talking" while she is in one (the same end path as before)
  function onTalkRow() {
    var c = S.convo;
    if (c) {
      if (c.ending) { if (c.live) { finishLive(c); } }
      else { endConvo(c, 'tap'); }
      return;
    }
    onTalkTap();
  }

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
    if (refocus) { try { $('menuBtn').focus(); } catch (e) { /* nothing */ } }   // M4b
  }
  function submitTyping() {
    var t = $('typeText');
    var v = t.value.trim();
    if (!v) { try { t.focus(); } catch (e) { /* nothing */ } return; }
    closeTyping(true);
    if (S.convo && S.convo.live && liveOn()) { liveTyped(S.convo, v); return; }   // M4a
    talkTo(v, true);   // M9c
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

  function onMenuClick(ev) {   // M4b: the approved six items
    var t = ev.target && ev.target.closest ? ev.target.closest('[data-act]') : null;
    if (!t || !$('menu').contains(t)) { return; }
    var act = t.getAttribute('data-act');
    App.onActivity();
    if (act === 'talk') {
      if (t.getAttribute('aria-disabled') === 'true') { return; }
      closeMenu(true);
      onTalkRow();
    }
    else if (act === 'can') { closeMenu(false); openPanel('canPanel'); }
    else if (act === 'info') { closeMenu(false); openPanel('infoPanel'); }
    else if (act === 'choose') { closeMenu(false); openPanel('choosePanel'); }
    else if (act === 'games') {   // Coming soon (M7): she says so, unless she is in a talk
      closeMenu(true);
      if (!S.convo && S.phase === 'idle' && S.screen === 'everyday') {
        newTurn();
        say("Games are coming soon. I can't wait to play with you.", 'happy');
      }
    }
    else if (act === 'close') {
      closeMenu(false);
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
    if (st.tts_spent != null) { S.ttsSpent = !!st.tts_spent; }   // M4a: a talk's voice is locked from this
    if (st.offline_ready != null) { S.offlineReady = !!st.offline_ready; }   // M4b: for My info
    if (Array.isArray(st.talk_order)) {
      S.talkOrder = st.talk_order.filter(function (m) { return m === 'live' || m === 'normal' || m === 'offline'; });
    }
    if (st.listen_wait != null) { QUIET_END_S = clampNum(st.listen_wait, 1.5, 6, QUIET_END_S); }
    S.talkOnOpen = st.talk_on_open !== false;   // M4a: she says hello and listens when her screen opens
    if (!S.convo) { S.voiceMode = speechModeFor(nextMode(S.talkOrder, null)); }
    // M6: the wake word setting and whether it can run here; the poll loop follows them
    if (st.wake_word != null) { S.wakeWord = !!st.wake_word; }
    if (st.wake_ready != null) { S.wakeReady = !!st.wake_ready; }
    wakeSync();
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
    setCaption(restLine(S.typingOnly && !liveFirst()));   // M4a: Live has its own mic
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
    cap = makeCaptions();   // M4b
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
      if (S.typingOnly && S.phase === 'idle' && CapS.plain === restLine(false)) { setCaption(restLine(true)); }   // M4a
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
    // M4b: the one Menu button, its menu and the three panels (the big Talk button is gone; Talk is in the menu)
    $('menuBtn').addEventListener('click', function () { App.onActivity(); if (menuOpen()) { closeMenu(true); } else { openMenu(); } });
    $('menu').addEventListener('click', onMenuClick);
    $('menu').addEventListener('keydown', onMenuKey);
    PANELS.forEach(function (id) {
      $(id).addEventListener('click', function (ev) {
        var t = ev.target;
        if (t === $(id) || (t && t.closest && t.closest('[data-back]'))) { closePanel(true); }   // Back, or a tap off the card
      });
    });
    D.addEventListener('pointerdown', onUiTouch, true);
    D.addEventListener('keydown', onUiTouch, true);
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
      if (ev.key === 'Tab' && M.panel) { trapTab(ev); return; }   // M4b
      if (ev.key !== 'Escape') { return; }
      if (M.panel) { closePanel(true); }                         // M4b
      else if (menuOpen()) { closeMenu(true); }                  // M4b
      else if (!$('typing').hidden) { closeTyping(true); }
    });
    window.addEventListener('pagehide', function () {
      try { if (S.listenAbort) { S.listenAbort(); } } catch (e) { /* nothing */ }
      spCancel();
      W.gone = true;   // M6: the poll loop stops with the page
      wakeStop();
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
    addThing: addThing,                      // M4b: skills.js lists a skill's screen in "Things Mary can do"
    openMenu: openMenu,                      // M4b
    closeMenu: closeMenu,                    // M4b
    sideBySide: sideBySide,                  // M4b: a skill's screen beside her face (skills.js does this for aside:true)
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
    wakeState: function () { return { polling: W.polling, seq: W.seq, held: W.held }; },   // M6: for tests and checks
    showCaption: showCaption,                // her words; M4b replaces it with bubble letters
    nextMode: nextMode,                      // pure, for tests
    liveToolGate: liveToolGate,              // pure, for tests
    openingLine: openingLine,                // M4a: firstrun.js, for her hello
    restLine: restLine,                      // M4a: the resting caption (firstrun.js); typing = true for Type
    isGoodbye: isGoodbye,                    // pure, for tests
    storyParts: storyParts,                  // M4a: pure, for tests
    notEnglish: notEnglish,                  // M4a: pure, for tests
    talkVoice: talkVoice                     // M4a: pure, for tests
  };

  if (D.readyState === 'loading') {
    D.addEventListener('DOMContentLoaded', function () { init().catch(log); });
  } else {
    init().catch(log);
  }
})();
