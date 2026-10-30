/* Mary's spoken replies in Normal (Gemini voice) and Offline (the voice on this computer) talk, as window.MaryVoice.
   The server turns each sentence into raw 16-bit sound with her picked voice (POST /api/mary/say) and streams it;
   we play the pieces back to back, and fetch the next sentence while this one plays so there are no long gaps.
   The streaming player is copied from the voice tryout (voices.js). This file has no screen parts of its own. */
(function () {
  'use strict';

  var HEADERS = {'X-Tracker': '1', 'Content-Type': 'application/json'};
  var ANSWER_MS = 20000;   // give up on a sentence whose sound has not started coming after this long

  var ctx = null;      // one AudioContext for every reply, made the first time she speaks
  var master = null;   // her loudness
  var job = null;      // the speak()/queue() in progress, or null
  var jobId = 0;

  function audio() {
    if (!ctx) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      try {
        ctx = new AC();
        master = ctx.createGain();
        master.connect(ctx.destination);
      } catch (e) {
        ctx = null;
        master = null;
        return null;
      }
    }
    if (ctx.state === 'suspended' && ctx.resume) {
      try {
        var p = ctx.resume();
        if (p && p.catch) p.catch(function () {});
      } catch (e2) { /* it may start on its own */ }
    }
    return ctx;
  }

  function clamp(v, lo, hi, dflt) {
    if (v === null || v === undefined || v === '') return dflt;
    v = Number(v);
    if (isNaN(v)) return dflt;
    return Math.max(lo, Math.min(hi, v));
  }

  function abortItem(it) {
    clearTimeout(it.timer);
    if (it.ctrl) {
      try { it.ctrl.abort(); } catch (e) { /* already done */ }
    }
    if (it.reader) {
      try {
        var p = it.reader.cancel();
        if (p && p.catch) p.catch(function () {});
      } catch (e2) { /* already done */ }
    }
  }

  function stopSources(j) {
    var list = j.sources;
    j.sources = [];
    list.forEach(function (src) {
      src.onended = null;
      try { src.stop(); } catch (e) { /* not started yet */ }
      try { src.disconnect(); } catch (e2) { /* already gone */ }
    });
  }

  function finish(j, result) {
    if (j.dead) return;
    j.dead = true;
    j.timers.forEach(function (t) { clearTimeout(t); });
    j.items.forEach(abortItem);
    if (job === j) job = null;
    j.resolve(result);
  }

  // Done when every sentence is queued (or one failed) and the last sound has been heard.
  function checkEnd(j) {
    if (j.dead || j.sources.length) return;
    if (j.failAt !== null) {
      var r = {ok: false, kind: 'failed', at: j.failAt};
      var why = j.items[j.failAt].why;
      if (why.error) r.error = why.error;
      if (why.no_key) r.no_key = true;
      if (why.bad_key) r.bad_key = true;
      finish(j, r);
    } else if (j.allDone) {
      finish(j, {ok: true});
    }
  }

  // Turns one piece of raw 16-bit sound into a buffer and queues it right after the last piece.
  function schedule(j, it, bytes) {
    if (it.leftover) {
      var joined = new Uint8Array(it.leftover.length + bytes.length);
      joined.set(it.leftover, 0);
      joined.set(bytes, it.leftover.length);
      bytes = joined;
      it.leftover = null;
    }
    var frameBytes = 2 * it.channels;
    var usable = bytes.length - (bytes.length % frameBytes);
    if (usable < bytes.length) it.leftover = new Uint8Array(bytes.subarray(usable));
    if (!usable) return;

    var frames = usable / frameBytes;
    var view = new DataView(bytes.buffer, bytes.byteOffset, usable);
    var buf;
    try {
      buf = ctx.createBuffer(it.channels, frames, it.rate);
    } catch (e) {
      return;   // a sound this computer can't play; the rest still goes on
    }
    for (var ch = 0; ch < it.channels; ch++) {
      var out = buf.getChannelData(ch);
      for (var i = 0; i < frames; i++) {
        out[i] = view.getInt16((i * it.channels + ch) * 2, true) / 32768;
      }
    }

    var src = ctx.createBufferSource();
    src.buffer = buf;
    src.playbackRate.value = 1;   // M4a: the server makes the speed, so the pitch stays natural
    src.connect(master);
    var now = ctx.currentTime;
    var at = Math.max(now + 0.05, j.playhead);
    src.start(at);
    j.playhead = at + buf.duration;
    j.sources.push(src);
    src.onended = function () {
      var at2 = j.sources.indexOf(src);
      if (at2 >= 0) j.sources.splice(at2, 1);
      try { src.disconnect(); } catch (e3) { /* already gone */ }
      checkEnd(j);
    };

    if (!it.scheduled) {
      it.scheduled = true;
      if (j.onSentenceAudio) {   // M4b: the caption plans this sentence's words on the playback clock
        try {
          j.onSentenceAudio(it.i, it.text, at + (ctx.outputLatency || ctx.baseLatency || 0), ctx, it.dur || null);
        } catch (e5) { /* the caller's problem, not the voice's */ }
      }
      if (j.onSentence) {
        var wait = Math.max(0, (at - now + (ctx.outputLatency || ctx.baseLatency || 0)) * 1000);
        j.timers.push(setTimeout(function () {
          if (j.dead) return;
          try { j.onSentence(it.i, it.text); } catch (e4) { /* the caller's problem, not the voice's */ }
        }, wait));
      }
    }
  }

  // At most the sentence playing and the next one are being fetched at once.
  function prefetch(j) {
    var cur = j.items[j.cur];
    if (cur && cur.answered && !cur.failed && j.cur + 1 < j.items.length) fetchItem(j, j.cur + 1);
  }

  // Once nothing more is coming, the job ends a little after its last sound is due, even if the audio clock
  // stalls (a sleeping sound card), so the caller is never left waiting.
  function watchdog(j) {
    var left = Math.max(0, j.playhead - ctx.currentTime) * 1000;
    j.timers.push(setTimeout(function () {
      if (j.dead) return;
      stopSources(j);
      checkEnd(j);
    }, left + 3000));
  }

  // The current sentence has all its sound queued (or failed): move on to the next one.
  function advance(j) {
    while (!j.dead) {
      var it = j.items[j.cur];
      if (it.failed) {
        j.failAt = it.i;
        j.items.forEach(function (x) { if (x.i > it.i) abortItem(x); });
        watchdog(j);
        checkEnd(j);
        return;
      }
      if (!it.streamDone) return;
      j.cur++;
      var next = j.items[j.cur];
      if (!next) {
        if (j.open) return;   // M4a: an open queue waits for more() or end()
        j.allDone = true;
        watchdog(j);
        checkEnd(j);
        return;
      }
      fetchItem(j, j.cur);
      prefetch(j);
      var waiting = next.pending;
      next.pending = [];
      for (var k = 0; k < waiting.length; k++) schedule(j, next, waiting[k]);
    }
  }

  function itemFailed(j, it, body) {
    if (j.dead || it.failed || it.streamDone) return;
    it.failed = true;
    it.why = body || {};
    abortItem(it);
    if (it.i === j.cur) advance(j);
  }

  function gotBytes(j, it, bytes) {
    if (j.dead || it.failed) return;
    it.bytes += bytes.length;
    if (it.i === j.cur) schedule(j, it, bytes);
    else it.pending.push(bytes);
  }

  function streamEnded(j, it) {
    if (j.dead || it.failed || it.streamDone) return;
    if (!it.bytes) {
      itemFailed(j, it, {});
      return;
    }
    it.streamDone = true;
    // M4b: its whole sound is here, so its real length is known (the server makes the speed, playback is 1x)
    it.dur = Math.floor(it.bytes / (2 * it.channels)) / it.rate;
    if (it.scheduled && j.onSentenceLength) {
      try { j.onSentenceLength(it.i, it.dur); } catch (e) { /* the caller's problem, not the voice's */ }
    }
    if (it.i === j.cur) advance(j);
  }

  function pump(j, it) {
    return it.reader.read().then(function (r) {
      if (j.dead || it.failed) return null;
      if (r.done) {
        streamEnded(j, it);
        return null;
      }
      if (r.value && r.value.length) gotBytes(j, it, r.value);
      return pump(j, it);
    });
  }

  function fetchItem(j, i) {
    var it = j.items[i];
    if (!it || it.started || j.dead) return;
    it.started = true;
    it.ctrl = window.AbortController ? new AbortController() : null;
    it.timer = setTimeout(function () {
      if (!it.answered) itemFailed(j, it, {});
    }, ANSWER_MS);
    var init = {method: 'POST', headers: HEADERS, body: JSON.stringify({text: it.text, mode: j.mode, rate: j.rate})};
    if (it.ctrl) init.signal = it.ctrl.signal;
    fetch('/api/mary/say', init)
      .then(function (res) {
        if (j.dead || it.failed) {
          try { if (res.body && res.body.cancel) res.body.cancel().catch(function () {}); } catch (e) { /* nothing to cancel */ }
          return null;
        }
        it.answered = true;
        clearTimeout(it.timer);
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (body) {
            itemFailed(j, it, body || {});
          });
        }
        var rate = Number(res.headers.get('X-Rate'));
        var channels = Number(res.headers.get('X-Channels'));
        it.rate = rate > 0 ? rate : 24000;
        it.channels = channels >= 1 && channels <= 2 ? Math.floor(channels) : 1;
        prefetch(j);
        if (res.body && res.body.getReader) {
          it.reader = res.body.getReader();
          return pump(j, it);
        }
        return res.arrayBuffer().then(function (buf) {
          if (j.dead || it.failed) return;
          gotBytes(j, it, new Uint8Array(buf));
          streamEnded(j, it);
        });
      })
      .catch(function () {
        if (j.dead || it.failed) return;
        clearTimeout(it.timer);
        if (it.bytes) streamEnded(j, it);   // the stream broke after some sound: play what came
        else itemFailed(j, it, {});
      });
  }

  // ------------------------------------------------------------ the page's way in

  // Plays the sentences in order with her picked voice. Resolves {ok:true} when the last sound has been heard,
  // {ok:true, cut:true} after cancel(), or {ok:false, kind:'failed', at:i} when sentence i could not be made
  // (at:0 means no sound at all). opts: mode 'normal'|'offline', rate 0.6-1.4, volume 0-1,
  // onSentence(i, text) when sentence i starts coming out of the speakers.
  // M4b: onSentenceAudio(i, text, at, ctx, dur) when sentence i's first sound is scheduled (at = seconds on
  // ctx.currentTime, dur = its length if already known, else null); onSentenceLength(i, dur) once it is known.
  function queue(sentences, opts) {
    cancel();
    opts = opts || {};
    var list = [];
    (sentences || []).forEach(function (t) {
      t = String(t === null || t === undefined ? '' : t).trim();
      if (t) list.push(t);
    });
    if (!list.length) return Promise.resolve({ok: true});
    if (!audio()) return Promise.resolve({ok: false, kind: 'failed', at: 0});
    var j = {
      id: ++jobId,
      items: list.map(function (text, i) {
        return {i: i, text: text, ctrl: null, reader: null, timer: 0, started: false, answered: false,
          rate: 24000, channels: 1, leftover: null, pending: [], bytes: 0,
          scheduled: false, streamDone: false, failed: false, why: {}};
      }),
      cur: 0,
      sources: [],
      playhead: 0,
      timers: [],
      mode: opts.mode === 'offline' ? 'offline' : 'normal',
      rate: clamp(opts.rate, 0.6, 1.4, 1),
      volume: clamp(opts.volume, 0, 1, 1),
      onSentence: typeof opts.onSentence === 'function' ? opts.onSentence : null,
      onSentenceAudio: typeof opts.onSentenceAudio === 'function' ? opts.onSentenceAudio : null,      // M4b
      onSentenceLength: typeof opts.onSentenceLength === 'function' ? opts.onSentenceLength : null,   // M4b
      failAt: null,
      allDone: false,
      open: !!opts.open,   // M4a: more sentences may follow with more(); end() says none are left
      dead: false,
      resolve: null
    };
    try { master.gain.value = j.volume; } catch (e) { /* keeps the last loudness */ }
    job = j;
    return new Promise(function (resolve) {
      j.resolve = resolve;
      fetchItem(j, 0);
    });
  }

  function speak(text, opts) {
    return queue([text], opts);
  }

  // M4a: adds a sentence to an open queue() (opts.open true) while it is playing, so a streamed reply has no gaps:
  // it is fetched as soon as there is room (the sentence playing and the next one). false if nothing is open.
  function more(text) {
    var j = job;
    text = String(text === null || text === undefined ? '' : text).trim();
    if (!j || j.dead || !j.open || j.failAt !== null || !text) return false;
    var it = {i: j.items.length, text: text, ctrl: null, reader: null, timer: 0, started: false, answered: false,
      rate: 24000, channels: 1, leftover: null, pending: [], bytes: 0,
      scheduled: false, streamDone: false, failed: false, why: {}};
    j.items.push(it);
    if (it.i === j.cur) fetchItem(j, it.i);
    else prefetch(j);
    return true;
  }

  // M4a: no more sentences for the open queue(); it resolves once the last one has been heard.
  function end() {
    var j = job;
    if (!j || j.dead || !j.open) return;
    j.open = false;
    if (j.failAt === null && j.cur >= j.items.length) {
      j.allDone = true;
      watchdog(j);
      checkEnd(j);
    }
  }

  // Stops her voice at once and drops any sentence still being fetched.
  function cancel() {
    var j = job;
    if (!j) return;
    stopSources(j);
    finish(j, {ok: true, cut: true});
  }

  // True from speak()/queue() until it resolves (fetching or playing).
  function isSpeaking() {
    return !!job;
  }

  window.MaryVoice = {
    speak: speak,
    queue: queue,
    more: more,   // M4a
    end: end,     // M4a
    cancel: cancel,
    isSpeaking: isSpeaking
  };
})();
