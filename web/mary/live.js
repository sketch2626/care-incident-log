/* Live talk demo on /mary/voices.html: a real spoken back-and-forth with Gemini Live (native audio).
   The page connects straight to Google with a one-use token from this computer, so the key never reaches the page.
   The resident can talk over her at any time; Live tells us ("interrupted") and we stop her voice at once. */
(function () {
  'use strict';

  var HEADERS = {'X-Tracker': '1', 'Content-Type': 'application/json'};
  var IN_RATE = 16000;          // what Live wants from the microphone
  var OUT_RATE = 24000;         // what Live sends back
  var CHUNK_SAMPLES = 800;      // 50 ms of microphone audio per message
  var VOICE_LEVEL = 0.02;       // microphone loudness that counts as the resident talking
  var MAX_MS = 3 * 60 * 1000;   // the practice chat ends by itself after 3 minutes
  var CONNECT_MS = 20000;       // give up if Google does not answer
  var GAP_WINDOW_MS = 10000;    // only time her reply if the resident spoke in the last 10 seconds

  var MSG_READY = 'Getting ready… If the computer asks to use the microphone, tap Allow.';
  var MSG_LISTEN = "I'm listening. Go ahead and talk.";
  var MSG_MIC = 'I need to hear you. Tap the Talk button again and choose Allow.';
  var MSG_NO_MIC = "I can't find a microphone on this computer.";
  var MSG_MIC_OTHER = "I couldn't use the microphone. Tap a Talk button to try again.";
  var MSG_NO_AUDIO = "This computer can't do a voice chat here.";
  var MSG_TOKEN = "I couldn't get ready. Please try again.";
  var MSG_CONNECT = "I couldn't connect. Tap a Talk button to try again.";
  var MSG_LOST = 'I lost the connection. Tap a Talk button to try again.';
  var MSG_END = "That's the end of the practice chat. Tap a Talk button to talk again.";
  var MSG_STOPPED = 'Stopped. Tap a Talk button to talk again.';

  // Sent once when the line is ready, so she speaks first (and we can time how long her hello takes).
  var GREET = '(The resident just opened this talk. Say a short, warm hello and ask how they are, in one or two sentences.)';

  // Runs in the audio thread: hands the microphone to the page in blocks of 1024 samples.
  var WORKLET_SRC =
    "class MicTap extends AudioWorkletProcessor {" +
    " constructor() { super(); this.buf = new Float32Array(1024); this.n = 0; }" +
    " process(inputs) {" +
    "  var c = inputs[0] && inputs[0][0];" +
    "  if (!c) return true;" +
    "  for (var i = 0; i < c.length; i++) {" +
    "   this.buf[this.n++] = c[i];" +
    "   if (this.n === 1024) { this.port.postMessage(this.buf); this.n = 0; }" +
    "  }" +
    "  return true;" +
    " }" +
    "}" +
    "registerProcessor('mic-tap', MicTap);";

  var activeBtn = null;   // the card's talk button that started the session in progress
  var statusEl = document.getElementById('liveStatus');
  var captionEl = document.getElementById('liveCaption');
  var statsEl = document.getElementById('liveStats');
  if (!statusEl || !captionEl || !statsEl) return;
  statsEl.style.whiteSpace = 'pre-line';

  var sessionId = 0;   // bumped on every start; events from an old session are ignored
  var S = null;        // the session in progress, or null

  // ------------------------------------------------------------ small helpers

  function face() {
    return window.Voices && window.Voices.face;
  }

  function act(activity) {
    var f = face();
    if (f) f.setActivity(activity);
  }

  function setStatus(text) {
    statusEl.textContent = text;
  }

  // Changes the words on the button that started the talk ("Start talking" puts its own words back).
  function setStart(text, disabled) {
    if (!activeBtn) return;
    activeBtn.textContent = text === 'Start talking' ? activeBtn.getAttribute('data-label') : text;
    activeBtn.disabled = disabled;
  }

  // While a talk runs, the other talk buttons are off. A button with no key stays off.
  function lockVoices(locked) {
    var all = document.querySelectorAll('.livetalk');
    for (var i = 0; i < all.length; i++) {
      if (all[i] === activeBtn) continue;
      all[i].disabled = locked || all[i].hasAttribute('data-nokey');
    }
  }

  function alive(s) {
    return S === s && !s.ended;
  }

  function median(list) {
    var a = list.slice().sort(function (x, y) { return x - y; });
    var mid = a.length >> 1;
    return a.length % 2 ? a[mid] : (a[mid - 1] + a[mid]) / 2;
  }

  function toBase64(bytes) {
    var out = '';
    for (var i = 0; i < bytes.length; i += 0x8000) {
      out += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(out);
  }

  function stopTracks(stream) {
    if (!stream) return;
    stream.getTracks().forEach(function (t) {
      try { t.stop(); } catch (e) { /* already stopped */ }
    });
  }

  function closeContext(ctx) {
    if (!ctx) return;
    try {
      var p = ctx.close();
      if (p && p.catch) p.catch(function () {});
    } catch (e) { /* already closed */ }
  }

  // ------------------------------------------------------------ what the page shows

  function statsLine(s) {
    var bits = [];
    if (s.greetMs !== null) {
      bits.push(s.pron + ' said hello in ' + (s.greetMs / 1000).toFixed(1) + ' s' +
        (s.greetFrom === 'mic' ? ' after the microphone was ready' : ' after you tapped'));
    }
    if (s.gaps.length) {
      bits.push(s.pron + ' answered in about ' + (median(s.gaps) / 1000).toFixed(1) + ' s');
    }
    if (s.turns || s.interruptions) {
      bits.push(s.turns + (s.turns === 1 ? ' turn' : ' turns'));
      bits.push(s.interruptions + (s.interruptions === 1 ? ' interruption' : ' interruptions'));
    }
    return bits.join(' · ');
  }

  function showStats(s) {
    var lines = [];
    if (s.youText) lines.push('You: ' + s.youText);
    if (s.turns || s.interruptions || s.greetMs !== null) lines.push(statsLine(s));
    statsEl.textContent = lines.join('\n');
  }

  function showCaption(s) {
    captionEl.textContent = s.caption;
  }

  // ------------------------------------------------------------ the microphone side

  function makeDownsampler(inRate) {
    var ratio = inRate / IN_RATE;
    var sum = 0;
    var count = 0;
    var seen = 0;
    var next = ratio;
    return function (f32, out) {
      for (var i = 0; i < f32.length; i++) {
        sum += f32[i];
        count++;
        seen++;
        if (seen >= next) {
          out.push(sum / count);
          sum = 0;
          count = 0;
          next += ratio;
        }
      }
    };
  }

  function sendPcm(s) {
    var n = s.pcm.length;
    if (!n || !s.ws || s.ws.readyState !== 1) {
      s.pcm = [];
      return;
    }
    var buf = new ArrayBuffer(n * 2);
    var view = new DataView(buf);
    for (var i = 0; i < n; i++) {
      var v = Math.max(-1, Math.min(1, s.pcm[i]));
      view.setInt16(i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
    }
    s.pcm = [];
    try {
      s.ws.send(JSON.stringify({realtimeInput: {audio: {
        data: toBase64(new Uint8Array(buf)),
        mimeType: 'audio/pcm;rate=16000'
      }}}));
    } catch (e) { /* the close event will tell us */ }
  }

  function onFrames(s, f32) {
    if (!alive(s)) return;
    var sum = 0;
    for (var i = 0; i < f32.length; i++) sum += f32[i] * f32[i];
    if (Math.sqrt(sum / f32.length) > VOICE_LEVEL) {
      s.lastVoiceAt = performance.now();
      s.voiceSince = true;
    }
    if (!s.ready) return;
    s.downsample(f32, s.pcm);
    if (s.pcm.length >= CHUNK_SAMPLES) sendPcm(s);
  }

  function useScriptProcessor(s) {
    var proc = s.inCtx.createScriptProcessor(2048, 1, 1);
    proc.onaudioprocess = function (ev) {
      onFrames(s, new Float32Array(ev.inputBuffer.getChannelData(0)));
    };
    s.source.connect(proc);
    proc.connect(s.sink);
    s.node = proc;
  }

  function openCapture(s) {
    var ctx = s.inCtx;
    s.downsample = makeDownsampler(ctx.sampleRate);
    s.source = ctx.createMediaStreamSource(s.stream);
    s.sink = ctx.createGain();
    s.sink.gain.value = 0;
    s.sink.connect(ctx.destination);
    var canWorklet = ctx.audioWorklet && window.AudioWorkletNode && window.Blob && URL.createObjectURL;
    if (!canWorklet) {
      useScriptProcessor(s);
      return Promise.resolve();
    }
    var url = URL.createObjectURL(new Blob([WORKLET_SRC], {type: 'application/javascript'}));
    return ctx.audioWorklet.addModule(url).then(function () {
      URL.revokeObjectURL(url);
      if (!alive(s)) return;
      var node = new AudioWorkletNode(ctx, 'mic-tap', {numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1]});
      node.port.onmessage = function (ev) { onFrames(s, ev.data); };
      s.source.connect(node);
      node.connect(s.sink);
      s.node = node;
    }).catch(function () {
      URL.revokeObjectURL(url);
      if (!alive(s)) return;
      useScriptProcessor(s);
    });
  }

  // ------------------------------------------------------------ her voice

  function stopPlayback(s) {
    var list = s.sources;
    s.sources = [];
    list.forEach(function (src) {
      src.onended = null;
      try { src.stop(); } catch (e) { /* not started yet */ }
      try { src.disconnect(); } catch (e2) { /* already gone */ }
    });
    s.playhead = 0;
    s.talking = false;
    clearTimeout(s.drainTimer);
  }

  function onDrained(s) {
    if (!alive(s) || s.sources.length) return;
    s.talking = false;
    act('listening');
    setStatus(MSG_LISTEN);
  }

  function playChunk(s, b64) {
    var bin = atob(b64);
    var n = bin.length >> 1;
    if (!n) return;
    var buf = s.outCtx.createBuffer(1, n, OUT_RATE);
    var ch = buf.getChannelData(0);
    for (var i = 0; i < n; i++) {
      var v = (bin.charCodeAt(i * 2 + 1) << 8) | bin.charCodeAt(i * 2);
      if (v & 0x8000) v -= 0x10000;
      ch[i] = v / 32768;
    }
    var src = s.outCtx.createBufferSource();
    src.buffer = buf;
    src.connect(s.outCtx.destination);
    var at = Math.max(s.outCtx.currentTime + 0.05, s.playhead);
    src.start(at);
    s.playhead = at + buf.duration;
    var ctx = s.outCtx;
    // The moment this sound will really come out of the speakers.
    var soundAt = performance.now() + (at - ctx.currentTime + (ctx.outputLatency || ctx.baseLatency || 0)) * 1000;
    if (s.greetMs === null) {
      var fromMic = s.micMs > 1000;   // the Allow question took time, so count from when the microphone was ready
      s.greetFrom = fromMic ? 'mic' : 'tap';
      s.greetMs = Math.max(0, Math.round(soundAt - (fromMic ? s.micAt : s.tapAt)));
      showStats(s);
    }
    s.sources.push(src);
    src.onended = function () {
      var at2 = s.sources.indexOf(src);
      if (at2 >= 0) s.sources.splice(at2, 1);
      try { src.disconnect(); } catch (e) { /* already gone */ }
      if (!s.sources.length) {
        clearTimeout(s.drainTimer);
        s.drainTimer = setTimeout(function () { onDrained(s); }, 350);
      }
    };
    clearTimeout(s.drainTimer);
    if (!s.talking) {
      s.talking = true;
      act('talking');
      setStatus(s.name + ' is talking. Talk over ' + s.her + ' any time to interrupt.');
    }
    return soundAt;
  }

  // ------------------------------------------------------------ what Live tells us

  function startOfTurn(s, now, isAudio) {
    // A new turn of hers starts with her first sound (or words that clearly come after the last turn ended).
    if (!s.newTurn) return;
    if (!isAudio && now - s.turnEndedAt < 800) return;
    s.newTurn = false;
    s.caption = '';
    showCaption(s);
  }

  function onAudio(s, b64) {
    var now = performance.now();
    var soundAt = playChunk(s, b64) || now;   // when her voice will really reach the speakers
    if (!s.turnOpen) {
      s.turnOpen = true;
      if (s.firstAudioMs === null) s.firstAudioMs = Math.round(now - s.readyAt);
      if (s.voiceSince && now - s.lastVoiceAt <= GAP_WINDOW_MS) {
        s.gaps.push(Math.max(0, Math.round(soundAt - s.lastVoiceAt)));
        s.voiceSince = false;
      }
    }
    startOfTurn(s, now, true);
  }

  function onInterrupted(s) {
    var now = performance.now();
    stopPlayback(s);
    s.interruptions++;
    s.turnOpen = false;
    s.newTurn = true;
    s.turnEndedAt = now;
    act('listening');
    setStatus('You talked, so ' + s.she + ' stopped to listen.');
    showStats(s);
  }

  function onServerContent(s, sc) {
    var now = performance.now();
    if (sc.interrupted) onInterrupted(s);

    var parts = sc.modelTurn && sc.modelTurn.parts;
    if (parts) {
      for (var i = 0; i < parts.length; i++) {
        var inline = parts[i] && parts[i].inlineData;
        if (inline && inline.data) {
          try { onAudio(s, inline.data); } catch (e) { s.error = 'audio problem'; }
        }
      }
    }

    var ot = sc.outputTranscription;
    if (ot && (ot.startOffset !== undefined || ot.endOffset !== undefined)) s.offsets = true;   // word timings really do come
    if (sc.outputTranscription && sc.outputTranscription.text) {
      startOfTurn(s, now, false);
      s.caption += sc.outputTranscription.text;
      showCaption(s);
    }

    if (sc.inputTranscription && sc.inputTranscription.text) {
      if (s.inputDone) {
        s.youText = '';
        s.inputDone = false;
      }
      s.youText += sc.inputTranscription.text;
      showStats(s);
    }

    if (sc.turnComplete) {
      s.turns++;
      s.turnOpen = false;
      s.newTurn = true;
      s.turnEndedAt = now;
      s.inputDone = true;
      showStats(s);
    }
  }

  function onReady(s) {
    clearTimeout(s.connectTimer);
    s.ready = true;
    s.readyAt = performance.now();
    s.downsample = makeDownsampler(s.inCtx.sampleRate);
    s.pcm = [];
    s.limitTimer = setTimeout(function () { endSession(s, 'timeout', MSG_END); }, MAX_MS);
    act('listening');
    setStatus(MSG_LISTEN);
    setStart('■ Stop talking', false);
    try {
      s.ws.send(JSON.stringify({clientContent: {turns: [{role: 'user', parts: [{text: GREET}]}], turnComplete: true}}));
    } catch (e) { /* she will simply wait for the resident to speak */ }
  }

  function handleText(s, text) {
    var msg;
    try { msg = JSON.parse(text); } catch (e) { return; }
    if (!msg) return;
    if (msg.setupComplete !== undefined) {
      if (!s.ready) onReady(s);
      return;
    }
    if (msg.error && !s.serverNote) {
      s.serverNote = String(msg.error.message || msg.error.status || 'server error');
    }
    if (msg.serverContent && s.ready) onServerContent(s, msg.serverContent);
  }

  function onMessage(s, ev) {
    if (!alive(s)) return;
    var d = ev.data;
    if (typeof d === 'string') {
      handleText(s, d);
    } else if (d instanceof ArrayBuffer) {
      handleText(s, new TextDecoder('utf-8').decode(d));
    }
  }

  function onClose(s, ev) {
    if (!alive(s)) return;
    s.closeCode = ev.code;
    s.closeReason = ev.reason || '';
    if (s.ready) {
      s.error = 'connection lost';
      endSession(s, 'lost', MSG_LOST);
    } else {
      s.error = 'could not connect';
      endSession(s, 'fail', MSG_CONNECT);
    }
  }

  // ------------------------------------------------------------ starting and stopping

  function newSession(voiceId, companion) {
    var male = companion === 'him';
    return {
      sid: ++sessionId,
      voiceId: voiceId,
      companion: companion,
      name: male ? 'Sam' : 'Mary',
      pron: male ? 'He' : 'She',
      she: male ? 'he' : 'she',
      her: male ? 'him' : 'her',
      ended: false,
      ready: false,
      model: '',
      wsUrl: '',
      token: '',
      ws: null,
      stream: null,
      inCtx: null,
      outCtx: null,
      source: null,
      sink: null,
      node: null,
      downsample: null,
      pcm: [],
      sources: [],
      playhead: 0,
      talking: false,
      turnOpen: false,
      newTurn: true,
      turnEndedAt: 0,
      inputDone: false,
      caption: '',
      youText: '',
      lastVoiceAt: 0,
      voiceSince: false,
      readyAt: 0,
      firstAudioMs: null,
      gaps: [],
      turns: 0,
      interruptions: 0,
      closeCode: null,
      closeReason: '',
      serverNote: '',
      error: '',
      limitTimer: 0,
      connectTimer: 0,
      drainTimer: 0,
      tapAt: performance.now(),
      micAt: null,
      micMs: null,
      greetMs: null,
      greetFrom: 'tap',
      offsets: false
    };
  }

  function writeLog(s, why) {
    var seconds = s.ready ? Math.round((performance.now() - s.readyAt) / 1000) : 0;
    var entry = {
      id: s.voiceId,
      voice: s.voiceId.replace(/^live:/, ''),
      model: s.model,
      first_audio_ms: s.firstAudioMs === null ? undefined : s.firstAudioMs,
      greet_ms: s.greetMs === null ? undefined : s.greetMs,
      mic_ms: s.micMs === null ? undefined : s.micMs,
      word_timings: s.offsets,
      reply_gap_ms: s.gaps.length ? Math.round(median(s.gaps)) : undefined,
      turns: s.turns,
      interruptions: s.interruptions,
      seconds: seconds,
      close_code: s.closeCode === null ? (why === 'user' || why === 'timeout' ? 1000 : undefined) : s.closeCode,
      ok: s.ready && (why === 'user' || why === 'timeout') && !s.error,
      error: s.error,
      note: (s.closeReason || s.serverNote || '').slice(0, 120)
    };
    try {
      fetch('/api/mary/voices/log', {
        method: 'POST',
        headers: HEADERS,
        body: JSON.stringify(entry),
        keepalive: true
      }).catch(function () {});
    } catch (e) { /* the log is only a help */ }
  }

  function endSession(s, why, text) {
    if (!s || s.ended) return;
    s.ended = true;
    if (S === s) S = null;
    clearTimeout(s.limitTimer);
    clearTimeout(s.connectTimer);
    stopPlayback(s);

    var ws = s.ws;
    if (ws) {
      ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
      try {
        if (ws.readyState === 1 && s.ready) ws.send(JSON.stringify({realtimeInput: {audioStreamEnd: true}}));
      } catch (e) { /* closing anyway */ }
      try { ws.close(1000, 'done'); } catch (e2) { /* already closed */ }
    }
    if (s.node) {
      try { s.node.onaudioprocess = null; } catch (e3) { /* worklet node */ }
      try { if (s.node.port) s.node.port.onmessage = null; } catch (e4) { /* none */ }
      try { s.node.disconnect(); } catch (e5) { /* already gone */ }
    }
    try { if (s.source) s.source.disconnect(); } catch (e6) { /* already gone */ }
    try { if (s.sink) s.sink.disconnect(); } catch (e7) { /* already gone */ }
    stopTracks(s.stream);
    closeContext(s.inCtx);
    closeContext(s.outCtx);
    s.token = '';

    var f = face();
    if (f) {
      f.setActivity('resting');
      f.setMood('happy');
    }
    setStatus(text || MSG_STOPPED);
    setStart('Start talking', false);
    lockVoices(false);
    activeBtn = null;
    if (window.Voices) window.Voices.liveBusy = false;
    showStats(s);
    if (s.model) writeLog(s, why);
  }

  function fail(s, text, label) {
    if (!alive(s)) return;
    s.error = label;
    endSession(s, 'fail', text);
  }

  function micProblem(err) {
    var name = err && err.name;
    if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError') {
      return {text: MSG_MIC, label: 'mic denied'};
    }
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError' || name === 'OverconstrainedError') {
      return {text: MSG_NO_MIC, label: 'no microphone'};
    }
    return {text: MSG_MIC_OTHER, label: 'mic problem'};
  }

  function openSocket(s) {
    var url = s.wsUrl + (s.wsUrl.indexOf('?') < 0 ? '?' : '&') + 'access_token=' + encodeURIComponent(s.token);
    s.token = '';
    var ws;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      fail(s, MSG_CONNECT, 'could not connect');
      return;
    }
    ws.binaryType = 'arraybuffer';
    s.ws = ws;
    s.connectTimer = setTimeout(function () {
      fail(s, MSG_CONNECT, 'connect timeout');
    }, CONNECT_MS);
    ws.onopen = function () {
      if (!alive(s)) return;
      ws.send(JSON.stringify({setup: {model: s.model}}));
    };
    ws.onmessage = function (ev) { onMessage(s, ev); };
    ws.onerror = function () { /* the close event follows with the reason */ };
    ws.onclose = function (ev) { onClose(s, ev); };
  }

  function getToken(s) {
    return fetch('/api/mary/live/token', {
      method: 'POST',
      headers: HEADERS,
      body: JSON.stringify({voice: s.voiceId, companion: s.companion})
    }).then(function (res) {
      return res.json().catch(function () { return {}; });
    }).then(function (j) {
      if (!alive(s)) return;
      if (!j || !j.token || !j.ws) {
        fail(s, (j && j.error) || MSG_TOKEN, 'no token');
        return;
      }
      s.token = j.token;
      s.model = j.model || '';
      s.wsUrl = j.ws;
      openSocket(s);
    });
  }

  function startSession(btn) {
    var voiceId = btn.getAttribute('data-id');
    var companion = btn.getAttribute('data-gender') === 'male' ? 'him' : 'mary';
    var s = newSession(voiceId, companion);
    S = s;
    activeBtn = btn;

    if (window.Voices) {
      window.Voices.stopSound();
      window.Voices.liveBusy = true;
    }
    var f = face();
    if (f) f.setCompanion(companion);
    act('thinking');
    setStart('Start talking', true);
    lockVoices(true);
    setStatus(MSG_READY);
    try {
      statusEl.scrollIntoView({block: 'nearest'});
    } catch (e0) { /* the page just stays where it is */ }
    captionEl.textContent = '';
    statsEl.textContent = '';

    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      fail(s, MSG_NO_AUDIO, 'no audio support');
      return;
    }
    // Made here, while the tap is fresh, so the browser lets them play and record.
    try {
      s.inCtx = new AC();
      try {
        s.outCtx = new AC({sampleRate: OUT_RATE});
      } catch (e) {
        s.outCtx = new AC();
      }
      if (s.inCtx.resume) s.inCtx.resume().catch(function () {});
      if (s.outCtx.resume) s.outCtx.resume().catch(function () {});
    } catch (e2) {
      fail(s, MSG_NO_AUDIO, 'no audio support');
      return;
    }

    // The microphone comes first: its Allow prompt can take a while, and the Google token only lasts a minute.
    navigator.mediaDevices.getUserMedia({audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1
    }}).then(function (stream) {
      if (!alive(s)) {
        stopTracks(stream);
        return null;
      }
      s.stream = stream;
      s.micAt = performance.now();
      s.micMs = Math.round(s.micAt - s.tapAt);
      if (s.inCtx.resume) s.inCtx.resume().catch(function () {});
      return openCapture(s).then(function () {
        if (alive(s)) return getToken(s);
        return null;
      });
    }, function (err) {
      var p = micProblem(err);
      fail(s, p.text, p.label);
    }).catch(function () {
      fail(s, MSG_TOKEN, 'start failed');
    });
  }

  // One listener for every card's talk button (they are made by voices.js).
  document.addEventListener('click', function (ev) {
    var t = ev.target;
    var btn = t && t.closest ? t.closest('.livetalk') : null;
    if (!btn || btn.disabled) return;
    if (S) {
      if (S.ready && btn === activeBtn) endSession(S, 'user', MSG_STOPPED);
      return;
    }
    startSession(btn);
  });

  function stopNow() {
    if (S) endSession(S, 'user', MSG_STOPPED);
  }

  ['tabGemini', 'tabOffline', 'backBtn'].forEach(function (id) {
    var b = document.getElementById(id);
    if (b) b.addEventListener('click', stopNow);
  });
  window.addEventListener('pagehide', stopNow);
})();
