/* Mary's Live talk on her own screen (/mary.html), as window.MaryLive: a real spoken back-and-forth with
   Gemini Live (native audio). The audio code is copied from the voice tryout (live.js), which stays as it is.
   The page connects straight to Google with a one-use token from this computer, so the key never reaches the page.
   The resident can talk over her at any time; Live tells us ("interrupted") and we stop her voice at once.
   This file has no screen parts of its own: app.js passes callbacks to start() and shows what happens. */
(function () {
  'use strict';

  var HEADERS = {'X-Tracker': '1', 'Content-Type': 'application/json'};
  var IN_RATE = 16000;          // what Live wants from the microphone
  var OUT_RATE = 24000;         // what Live sends back
  var CHUNK_SAMPLES = 800;      // 50 ms of microphone audio per message
  var VOICE_LEVEL = 0.02;       // microphone loudness that counts as the resident talking
  var CONNECT_MS = 20000;       // give up if Google does not answer
  var GAP_WINDOW_MS = 10000;    // only time her reply if the resident spoke in the last 10 seconds
  var DRAIN_MS = 350;           // her voice counts as finished after this much quiet
  var HEARD_SETTLE_MS = 400;    // the last words of what the resident said can come just after her reply starts
  var ACTIVITY_MS = 500;        // at most one onActivity() per this many ms from the microphone
  var MUTE_MAX_MS = 1200;       // after stopSpeaking() + greet(), her new words play by this time at the latest
  var MIC_MS = 45000;           // M4a: an Allow question nobody answers ends the start, so the Talk button comes back

  // Plain words for a failed start (err.message). The server's own sentence is used when it sends one.
  var MESSAGES = {
    token: "I couldn't get ready. Please try again.",
    no_key: 'I need my Gemini key first. You can add it in My info.',
    bad_key: "Google didn't accept the Gemini key. Please check it in My info.",
    busy: "Gemini's free limit is used up for now. Please try again in a few minutes.",
    mic_denied: 'I need to hear you. Please allow the microphone.',
    no_mic: "I can't find a microphone on this computer.",
    connect: "I couldn't connect. Please try again.",
    audio: "This computer can't do a voice chat here.",
    stopped: 'Stopped.'
  };

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

  var sessionId = 0;   // bumped on every start; events from an old session are ignored
  var S = null;        // the session in progress (starting or open), or null
  var volume = 1;      // her loudness, 0..1 (setVolume)

  // ------------------------------------------------------------ small helpers

  function alive(s) {
    return S === s && !s.ended;
  }

  // Calls one of app.js's callbacks. A callback that throws never breaks the talk.
  // Nothing but onEnd is called once the session has ended.
  function emit(s, name) {
    if (s.ended && name !== 'onEnd') return undefined;
    var fn = s.opts[name];
    if (typeof fn !== 'function') return undefined;
    var args = Array.prototype.slice.call(arguments, 2);
    try {
      return fn.apply(null, args);
    } catch (e) {
      return undefined;
    }
  }

  function makeError(kind, message) {
    var err = new Error(message || MESSAGES[kind] || kind);
    err.kind = kind;
    return err;
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
    if (!n || s.deaf || !s.ws || s.ws.readyState !== 1) {   // M21a: deaf = the mic is not sent
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
    var rms = f32.length ? Math.sqrt(sum / f32.length) : 0;   // M4b
    emit(s, 'onMicLevel', rms, rms > VOICE_LEVEL);            // M4b: the ear waves on her face (app.js)
    if (rms > VOICE_LEVEL) {
      var now = performance.now();
      s.lastVoiceAt = now;
      s.voiceSince = true;
      if (s.ready && now - s.activityAt >= ACTIVITY_MS) {
        s.activityAt = now;
        emit(s, 'onActivity');
      }
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

  function setSpeaking(s, on) {
    if (s.talking === on) return;
    s.talking = on;
    emit(s, 'onSpeaking', on);
  }

  function stopPlayback(s) {
    var list = s.sources;
    s.sources = [];
    list.forEach(function (src) {
      src.onended = null;
      try { src.stop(); } catch (e) { /* not started yet */ }
      try { src.disconnect(); } catch (e2) { /* already gone */ }
    });
    s.playhead = 0;
    clearTimeout(s.drainTimer);
    setSpeaking(s, false);
  }

  function onDrained(s) {
    if (!alive(s) || s.sources.length) return;
    setSpeaking(s, false);
    if (s.newTurn) emit(s, 'onAudioDone');   // M4b: her turn is over and all of it was heard
    if (s.goAway) endSession(s, 'closed', {goAway: true, code: s.closeCode, note: s.serverNote});
  }

  function playChunk(s, b64) {
    var bin = atob(b64);
    var n = bin.length >> 1;
    if (!n) return 0;
    var buf = s.outCtx.createBuffer(1, n, OUT_RATE);
    var ch = buf.getChannelData(0);
    for (var i = 0; i < n; i++) {
      var v = (bin.charCodeAt(i * 2 + 1) << 8) | bin.charCodeAt(i * 2);
      if (v & 0x8000) v -= 0x10000;
      ch[i] = v / 32768;
    }
    var src = s.outCtx.createBufferSource();
    src.buffer = buf;
    src.connect(s.gain);
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
    }
    s.sources.push(src);
    emit(s, 'onAudioChunk', at + (ctx.outputLatency || ctx.baseLatency || 0), buf.duration, ctx);   // M4b: caption timing
    src.onended = function () {
      var at2 = s.sources.indexOf(src);
      if (at2 >= 0) s.sources.splice(at2, 1);
      try { src.disconnect(); } catch (e) { /* already gone */ }
      if (!s.sources.length) {
        clearTimeout(s.drainTimer);
        s.drainTimer = setTimeout(function () { onDrained(s); }, DRAIN_MS);
      }
    };
    clearTimeout(s.drainTimer);
    setSpeaking(s, true);
    return soundAt;
  }

  function clearMute(s) {
    s.mute = false;
    clearTimeout(s.muteTimer);
  }

  // ------------------------------------------------------------ what the resident said

  // Her reply has started, so what the resident said is nearly final; late words get a moment to arrive.
  function replyStarts(s) {
    if (s.heardState !== 'open') return;
    s.heardState = 'settling';
    clearTimeout(s.heardTimer);
    s.heardTimer = setTimeout(function () { fireHeard(s); }, HEARD_SETTLE_MS);
  }

  function fireHeard(s) {
    clearTimeout(s.heardTimer);
    if (!alive(s) || (s.heardState !== 'open' && s.heardState !== 'settling')) return;
    var text = s.heard.trim();
    s.heardState = text ? 'done' : 'idle';
    if (text) emit(s, 'onHeardDone', text);
  }

  function onInput(s, text) {
    if (s.heardState !== 'open' && s.heardState !== 'settling') {
      s.heard = '';   // a new turn of the resident's
      s.heardState = 'open';
    }
    s.heard += text;
    emit(s, 'onActivity');
    emit(s, 'onHeard', s.heard);
  }

  // ------------------------------------------------------------ what Live tells us

  function startOfTurn(s, now, isAudio) {
    // A new turn of hers starts with her first sound (or words that clearly come after the last turn ended).
    if (!s.newTurn) return;
    if (!isAudio && now - s.turnEndedAt < 800) return;
    s.newTurn = false;
    s.caption = '';
  }

  function onAudio(s, b64) {
    if (s.mute) return;   // stopSpeaking(): the rest of this turn of hers stays quiet
    var now = performance.now();
    replyStarts(s);
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
    emit(s, 'onCut');   // M4b: before stopPlayback(), so the caption is cut, not finished
    stopPlayback(s);
    s.interruptions++;
    s.turnOpen = false;
    s.newTurn = true;
    s.turnEndedAt = performance.now();
    clearMute(s);
    emit(s, 'onInterrupted');
  }

  function onServerContent(s, sc) {
    // A callback may stop the talk part way through one message, so each part checks it is still on.
    var now = performance.now();
    if (sc.interrupted) onInterrupted(s);

    var parts = sc.modelTurn && sc.modelTurn.parts;
    if (parts) {
      for (var i = 0; i < parts.length && alive(s); i++) {
        var inline = parts[i] && parts[i].inlineData;
        if (inline && inline.data) {
          try { onAudio(s, inline.data); } catch (e) { s.error = 'audio problem'; }
        }
      }
    }

    var ot = sc.outputTranscription;
    if (ot && (ot.startOffset !== undefined || ot.endOffset !== undefined)) s.offsets = true;   // word timings really do come
    if (ot && ot.text && !s.mute && alive(s)) {
      replyStarts(s);
      startOfTurn(s, now, false);
      s.caption += ot.text;
      emit(s, 'onActivity');
      emit(s, 'onCaption', s.caption);
      emit(s, 'onCaptionPiece', ot.text);   // M4b: just the new piece (captions.js livePiece)
    }

    var it = sc.inputTranscription;
    if (it && it.text && alive(s)) onInput(s, it.text);

    if (sc.turnComplete && alive(s)) {
      s.turns++;
      s.turnOpen = false;
      s.newTurn = true;
      s.turnEndedAt = now;
      clearMute(s);
      fireHeard(s);
      emit(s, 'onTurnComplete');
      if (!s.sources.length) emit(s, 'onAudioDone');   // M4b: her sound had already finished
      if (s.pendingNote) { var held = s.pendingNote; s.pendingNote = ''; sendNote(s, held); }   // M7a: the note held while she spoke
    }
  }

  // She wants to use a skill. app.js answers; with no answer (or a failed one) she hears that it did not work,
  // so she never waits forever.
  function onToolCall(s, toolCall) {
    fireHeard(s);   // the resident's words are final once she acts on them
    var calls = (toolCall && toolCall.functionCalls) || [];
    var answer = emit(s, 'onToolCall', toolCall);
    Promise.resolve(answer).then(function (result) {
      if (!result || !result.functionResponses) throw new Error('no answer');
      return result;
    }).catch(function () {
      return {functionResponses: calls.map(function (c) {
        return {id: c.id, name: c.name, response: {error: 'That did not work.'}};
      })};
    }).then(function (result) {
      if (!alive(s) || !s.ws || s.ws.readyState !== 1) return;
      // M4a: a call Live took back (toolCallCancellation) gets no answer
      var left = result.functionResponses.filter(function (r) { return !(s.toolGone && s.toolGone[r.id]); });
      if (!left.length) return;
      try {
        s.ws.send(JSON.stringify({toolResponse: {functionResponses: left}}));
      } catch (e) { /* the close event will tell us */ }
    });
  }

  // M4a: Live took a tool call back (usually the resident talked over it). app.js holds a story that came from it.
  function onToolCancel(s, ids) {
    ids = ids || [];
    s.toolGone = s.toolGone || {};
    for (var i = 0; i < ids.length; i++) s.toolGone[ids[i]] = true;
    emit(s, 'onToolCancel', ids);
  }

  // Google will close this talk soon: let her finish what she is saying, then end it.
  function onGoAway(s) {
    s.goAway = true;
    if (!s.sources.length) endSession(s, 'closed', {goAway: true, code: s.closeCode, note: s.serverNote});
  }

  function onReady(s) {
    clearTimeout(s.connectTimer);
    s.ready = true;
    s.readyAt = performance.now();
    s.downsample = makeDownsampler(s.inCtx.sampleRate);
    s.pcm = [];
    if (!s.settled) {
      s.settled = true;
      s.resolve({model: s.model, voice: s.voice, companion: s.companion});
    }
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
    if (!s.ready) return;
    if (msg.serverContent) onServerContent(s, msg.serverContent);
    if (msg.toolCall && alive(s)) onToolCall(s, msg.toolCall);
    if (msg.toolCallCancellation && alive(s)) onToolCancel(s, msg.toolCallCancellation.ids);   // M4a
    if (msg.goAway && alive(s)) onGoAway(s);
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
    if (!s.ready) {
      failStart(s, 'connect');
      return;
    }
    var bad = !s.goAway && (!!s.serverNote || ev.code === 1007 || ev.code === 1008 || ev.code === 1011);
    if (!s.goAway && ev.code !== 1000) s.error = bad ? 'server error' : 'connection lost';
    endSession(s, bad ? 'error' : 'closed',
      {goAway: s.goAway, code: ev.code, note: (s.closeReason || s.serverNote || '').slice(0, 120)});
  }

  // ------------------------------------------------------------ starting and stopping

  function newSession(opts) {
    return {
      sid: ++sessionId,
      opts: opts,
      ended: false,
      ready: false,
      settled: false,
      resolve: null,
      reject: null,
      model: '',
      voice: '',
      companion: '',
      wsUrl: '',
      token: '',
      ws: null,
      stream: null,
      inCtx: null,
      outCtx: null,
      gain: null,
      source: null,
      sink: null,
      node: null,
      downsample: null,
      pcm: [],
      sources: [],
      playhead: 0,
      talking: false,
      mute: false,
      muteTimer: 0,
      goAway: false,
      turnOpen: false,
      pendingNote: '',   // M7a: newest silent note held while she speaks
      newTurn: true,
      turnEndedAt: 0,
      caption: '',
      heard: '',
      heardState: 'idle',   // idle | open (words coming) | settling (her reply started) | done (onHeardDone sent)
      heardTimer: 0,
      activityAt: 0,
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
    var voice = String(s.voice || '').replace(/^live:/, '');
    var entry = {
      event: 'live',
      id: 'live:' + voice,
      voice: voice,
      model: s.model,
      first_audio_ms: s.firstAudioMs === null ? undefined : s.firstAudioMs,
      greet_ms: s.greetMs === null ? undefined : s.greetMs,
      mic_ms: s.micMs === null ? undefined : s.micMs,
      word_timings: s.offsets,
      reply_gap_ms: s.gaps.length ? Math.round(median(s.gaps)) : undefined,
      turns: s.turns,
      interruptions: s.interruptions,
      seconds: seconds,
      close_code: s.closeCode === null ? (why === 'stop' ? 1000 : undefined) : s.closeCode,
      ok: s.ready && !s.error && (why === 'stop' || s.goAway),
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

  // Ends a session for good. why: 'stop' (stop() or a new start), 'fail' (start failed), 'closed', 'error'.
  // A start still waiting is rejected (startError, or kind 'stopped'); an open talk that ends by itself gets onEnd.
  function endSession(s, why, detail, startError) {
    if (!s || s.ended) return;
    // M4a: words the resident said before the talk ended (a drop, a stop, a restart) still get their emergency check
    if (s.ready && (s.heardState === 'open' || s.heardState === 'settling')) {
      var said = s.heard.trim();
      s.heardState = said ? 'done' : 'idle';
      if (said) emit(s, 'onHeardDone', said);
    }
    s.ended = true;
    s.pendingNote = '';   // M7a
    if (S === s) S = null;
    clearTimeout(s.connectTimer);
    clearTimeout(s.heardTimer);
    clearTimeout(s.muteTimer);
    stopPlayback(s);
    s.talking = false;

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
    if (s.model) writeLog(s, why);

    if (!s.settled) {
      s.settled = true;
      if (s.reject) s.reject(startError || makeError('stopped'));
    } else if (why === 'closed' || why === 'error') {
      emit(s, 'onEnd', why, detail || {});
    }
  }

  function failStart(s, kind, message) {
    if (!alive(s)) return;
    s.error = kind;
    endSession(s, 'fail', null, makeError(kind, message));
  }

  function micKind(err) {
    var name = err && err.name;
    if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError') return 'mic_denied';
    return 'no_mic';   // not found, or in use / broken: either way there is no microphone to use
  }

  function openSocket(s) {
    var url = s.wsUrl + (s.wsUrl.indexOf('?') < 0 ? '?' : '&') + 'access_token=' + encodeURIComponent(s.token);
    s.token = '';
    var ws;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      failStart(s, 'connect');
      return;
    }
    ws.binaryType = 'arraybuffer';
    s.ws = ws;
    s.connectTimer = setTimeout(function () {
      failStart(s, 'connect');
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
    return fetch('/api/mary/live/start', {
      method: 'POST',
      headers: HEADERS,
      // M4a: plain = no language hint on what Live hears, after a start that failed with it
      // M13b: aside goes along when there is one
      body: JSON.stringify(Object.assign(s.opts.plain ? {screen: s.opts.screen || null, plain: true} : {screen: s.opts.screen || null},
        s.opts.aside ? {aside: s.opts.aside} : {}))
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (j) {
        return {ok: res.ok, status: res.status, j: j || {}};
      });
    }).then(function (r) {
      if (!alive(s)) return;
      var j = r.j;
      if (!r.ok || !j.token || !j.ws) {
        var kind = j.no_key ? 'no_key' : j.bad_key ? 'bad_key' : r.status === 503 ? 'busy' : 'token';
        failStart(s, kind, j.error ? String(j.error) : '');
        return;
      }
      s.token = j.token;
      s.model = j.model || '';
      s.wsUrl = j.ws;
      s.voice = j.voice || '';
      s.companion = j.companion || '';
      openSocket(s);
    });
  }

  // M17: a microphone that goes away ends the line at once, so the page falls back instead of talking to nobody.
  function watchMic(s, stream) {
    try {
      stream.getTracks().forEach(function (track) {
        if (!track.addEventListener) return;
        track.addEventListener('ended', function () {
          if (alive(s)) endSession(s, 'closed', {note: 'mic lost'});
        });
      });
    } catch (e) { /* nothing to watch */ }
  }

  // Opens the microphone first (its Allow question can take a while, and Google's token only lasts a minute),
  // then gets the token and opens the line. Call it from a tap so the browser lets it play and record.
  function begin(s) {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.WebSocket) {
      failStart(s, 'audio');
      return;
    }
    try {
      s.inCtx = new AC();
      try {
        s.outCtx = new AC({sampleRate: OUT_RATE});
      } catch (e) {
        s.outCtx = new AC();
      }
      if (s.inCtx.resume) s.inCtx.resume().catch(function () {});
      if (s.outCtx.resume) s.outCtx.resume().catch(function () {});
      s.gain = s.outCtx.createGain();
      s.gain.gain.value = volume;
      s.gain.connect(s.outCtx.destination);
    } catch (e2) {
      failStart(s, 'audio');
      return;
    }

    s.connectTimer = setTimeout(function () { failStart(s, 'mic_denied'); }, MIC_MS);   // M4a
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
      clearTimeout(s.connectTimer);   // M4a: the microphone answered; openSocket() sets the connect timer
      s.stream = stream;
      watchMic(s, stream);   // M17
      s.micAt = performance.now();
      s.micMs = Math.round(s.micAt - s.tapAt);
      if (s.inCtx.resume) s.inCtx.resume().catch(function () {});
      return openCapture(s).then(function () {
        if (alive(s)) return getToken(s);
        return null;
      });
    }, function (err) {
      failStart(s, micKind(err));
    }).catch(function () {
      failStart(s, 'token');
    });
  }

  // ------------------------------------------------------------ the page's way in

  function supported() {
    return !!((window.AudioContext || window.webkitAudioContext) &&
      navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.WebSocket);
  }

  function start(opts) {
    if (S) endSession(S, 'stop');
    var s = newSession(opts || {});
    S = s;
    return new Promise(function (resolve, reject) {
      s.resolve = resolve;
      s.reject = reject;
      begin(s);
    });
  }

  // Asks her to say something (hello, goodbye, the emergency words). false if the line is not open.
  function greet(text) {
    var s = S;
    if (!s || !s.ready || s.ended || !s.ws || s.ws.readyState !== 1 || !text) return false;
    if (s.mute) {
      // stopSpeaking() hushed her last turn; her answer to this must be heard even if Live never ends that turn.
      clearTimeout(s.muteTimer);
      s.muteTimer = setTimeout(function () { s.mute = false; }, MUTE_MAX_MS);
    }
    try {
      s.ws.send(JSON.stringify({clientContent: {turns: [{role: 'user', parts: [{text: String(text)}]}], turnComplete: true}}));
      return true;
    } catch (e) {
      return false;
    }
  }

  // M7a: a silent note about what changed on a screen. turnComplete is false, so it goes in the talk and she doesn't
  // answer it. Unlike greet it leaves the mute alone: nothing here is meant to be heard. false if the line is not open.
  // While she is speaking (turnOpen) a note would cut her off, so only the newest one is held and sent at turnComplete.
  function note(text) {
    var s = S;
    if (!s || !s.ready || s.ended || !s.ws || s.ws.readyState !== 1 || !text) return false;
    if (s.turnOpen) { s.pendingNote = String(text); return true; }   // M7a
    return sendNote(s, text);
  }

  function sendNote(s, text) {
    if (!s || s.ended || !s.ws || s.ws.readyState !== 1) return false;
    try {
      s.ws.send(JSON.stringify({clientContent: {turns: [{role: 'user', parts: [{text: String(text)}]}], turnComplete: false}}));
      return true;
    } catch (e) {
      return false;
    }
  }

  // M21a: deaf = the mic is not sent (a goodbye). Turning it on ends the audio stream once, so
  // her reply to what was already said comes at once. A new session starts hearing again (s.deaf is per session).
  function setDeaf(on) {
    var s = S;
    if (!s || s.ended) return;
    on = !!on;
    if (on === !!s.deaf) return;
    s.deaf = on;
    if (!on) return;
    s.pcm = [];
    try {
      if (s.ws && s.ws.readyState === 1 && s.ready) s.ws.send(JSON.stringify({realtimeInput: {audioStreamEnd: true}}));
    } catch (e) { /* the close event will tell us */ }
  }

  // M7a: true while the resident's words are coming in.
  function isHearing() {
    return !!(S && !S.ended && S.heardState === 'open');
  }

  function stop(reason) {
    if (!S) return;
    S.stopReason = String(reason || '');
    endSession(S, 'stop');
  }

  // Hushes her now (the emergency screen) without closing the line; the rest of this turn of hers is dropped.
  function stopSpeaking() {
    var s = S;
    if (!s || s.ended) return;
    // M4a: only a turn still coming is hushed; after turnComplete the next audio is a new turn and must be heard
    if (s.turnOpen) s.mute = true;
    stopPlayback(s);
  }

  function isOpen() {
    return !!(S && S.ready && !S.ended && S.ws && S.ws.readyState === 1);
  }

  function isSpeaking() {
    return !!(S && !S.ended && S.talking);
  }

  // M17: true when she should be sounding but her clock has stood still this long (a dead audio device). The page checks
  // every second. resume() gets one try first.
  var STALL_MS = 5000;
  function stalled() {
    var s = S;
    if (!s || s.ended || !s.talking || !s.outCtx) {
      if (s) s.stallAt = 0;
      return false;
    }
    var clock = s.outCtx.currentTime, now = performance.now();
    if (!s.stallAt || clock !== s.stallClock) {
      s.stallClock = clock;
      s.stallAt = now;
      s.stallResumed = false;
      return false;
    }
    if (!s.stallResumed) {
      s.stallResumed = true;
      try { if (s.outCtx.resume) s.outCtx.resume().catch(function () {}); } catch (e) { /* closing */ }
    }
    return now - s.stallAt >= STALL_MS;
  }

  function setVolume(v) {
    v = Number(v);
    if (isNaN(v)) return;
    volume = Math.max(0, Math.min(1, v));
    if (S && S.gain) {
      try { S.gain.gain.value = volume; } catch (e) { /* the talk is closing */ }
    }
  }

  window.addEventListener('pagehide', function () {
    if (S) endSession(S, 'stop');
  });

  window.MaryLive = {
    supported: supported,
    start: start,
    greet: greet,
    note: note,                // M7a
    setDeaf: setDeaf,          // M21a
    isHearing: isHearing,      // M7a
    stop: stop,
    stopSpeaking: stopSpeaking,
    isOpen: isOpen,
    isSpeaking: isSpeaking,
    stalled: stalled,          // M17
    setVolume: setVolume
  };
})();
