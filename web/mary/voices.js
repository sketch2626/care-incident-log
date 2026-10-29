/* Voice chooser for /mary/voices.html: Mary and Sam each get a voice. */
(function () {
  'use strict';

  var HEADERS = {'X-Tracker': '1', 'Content-Type': 'application/json'};
  var BAD_SOUND = "I couldn't get that voice to play. Please try again.";
  var BAD_SAVE = "I couldn't save that choice. Please try again.";
  var NO_KEY = 'Add your Gemini key in My info first, then try again.';
  var BAD_KEY = "That Gemini key didn't work. Check it in My info.";
  var TABS = {tabGemini: 'secGemini', tabLive: 'secLive', tabOffline: 'secOffline'};

  var face = MaryFace.create(document.getElementById('face'), {companion: 'mary'});

  var data = null;          // loaded from /api/mary/voices
  var current = null;       // the sample being fetched or played: its card, button, audio context, reader and counters
  var playToken = 0;        // bumped on every start or stop; late answers with an old token are ignored
  var selectedLive = null;  // the live voice picked in the Live talk tab

  function byId(id) {
    return document.getElementById(id);
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function setButton(btn, text, disabled) {
    btn.textContent = text;
    btn.disabled = disabled;
  }

  function showError(card, msg) {
    var box = card.querySelector('.errbox');
    box.textContent = msg;
    box.hidden = false;
  }

  // Stops the stream, every scheduled piece of sound and the audio context. Never throws.
  function teardown(run) {
    run.dead = true;
    clearTimeout(run.soundTimer);
    try {
      if (run.reader && run.reader.cancel) {
        var cancelled = run.reader.cancel();
        if (cancelled && cancelled.catch) cancelled.catch(function () {});
      }
    } catch (e) { /* already closed */ }
    var list = run.sources;
    run.sources = [];
    for (var i = 0; i < list.length; i++) {
      list[i].onended = null;
      try { list[i].stop(); } catch (e2) { /* not started yet */ }
      try { list[i].disconnect(); } catch (e3) { /* already gone */ }
    }
    try {
      if (run.ctx && run.ctx.close) {
        var closed = run.ctx.close();
        if (closed && closed.catch) closed.catch(function () {});
      }
    } catch (e4) { /* already closed */ }
  }

  // Tells the server how a sample went, once per sample. It only helps us tune the voices.
  function logPlay(run, ok, error) {
    if (run.logged) return;
    run.logged = true;
    var entry = {
      event: 'played',
      id: run.c.id,
      voice: run.c.voice,
      path: run.c.kind,
      tap_to_sound_ms: run.tapToSound === null ? undefined : run.tapToSound,
      cached: run.cached,
      gaps: run.gaps,
      gap_ms: Math.round(run.gapMs),
      load_ms: run.loadMs,
      ok: ok
    };
    if (error) entry.error = error;
    try {
      fetch('/api/mary/voices/log', {
        method: 'POST',
        headers: HEADERS,
        body: JSON.stringify(entry),
        keepalive: true
      }).catch(function () {});
    } catch (e) { /* the log is only a help */ }
  }

  function stopSound() {
    playToken++;
    if (current) {
      var run = current;
      current = null;
      teardown(run);
      if (run.started) logPlay(run, false, 'stopped');
      setButton(run.btn, '▶ Play', false);
    }
    face.setActivity('resting');
  }

  function statsText(run) {
    var text = 'Started speaking ' + (run.tapToSound / 1000).toFixed(1) + ' s after your tap';
    if (run.cached) text += ' · saved copy';
    if (run.loadMs > 0) {
      text += ' · includes ' + (run.loadMs / 1000).toFixed(1) + ' s getting the offline voice ready';
    }
    if (run.gaps) {
      text += ' · paused ' + run.gaps + (run.gaps === 1 ? ' time' : ' times') + ' waiting for more';
    }
    return text;
  }

  function errorText(j) {
    if (j && j.no_key) return NO_KEY;
    if (j && j.bad_key) return BAD_KEY;
    return (j && typeof j.error === 'string' && j.error) || BAD_SOUND;
  }

  // 'af_heart' -> 'Heart' (offline voices); Gemini names are already plain ('Sulafat').
  function niceName(voice) {
    var n = String(voice || '').replace(/^[a-z]{2}_/, '');
    return n.charAt(0).toUpperCase() + n.slice(1);
  }

  function fail(card, btn, msg) {
    if (current) teardown(current);
    current = null;
    setButton(btn, '▶ Play', false);
    face.setActivity('resting');
    showError(card, msg);
  }

  function showStats(run) {
    var stats = run.card.querySelector('.stats');
    stats.textContent = statsText(run);
    stats.hidden = false;
  }

  // The stream is finished and the last piece of sound has been heard.
  function finishSound(run) {
    teardown(run);
    current = null;
    setButton(run.btn, '▶ Play again', false);
    face.setActivity('resting');
    face.setMood('happy');
    face.bounce();
    showStats(run);
    logPlay(run, !run.streamBroke, run.streamBroke ? 'stream stopped early' : '');
  }

  function checkEnd(run, token) {
    if (run.dead || token !== playToken || !run.streamDone || run.sources.length) return;
    if (run.tapToSound === null) fail(run.card, run.btn, BAD_SOUND);
    else finishSound(run);
  }

  // Turns one piece of raw 16-bit sound into a buffer and queues it right after the last piece.
  function queueBytes(run, token, bytes) {
    if (run.dead) return;
    if (run.leftover) {
      var joined = new Uint8Array(run.leftover.length + bytes.length);
      joined.set(run.leftover, 0);
      joined.set(bytes, run.leftover.length);
      bytes = joined;
      run.leftover = null;
    }
    var frameBytes = 2 * run.channels;
    var usable = bytes.length - (bytes.length % frameBytes);
    if (usable < bytes.length) run.leftover = new Uint8Array(bytes.subarray(usable));
    if (!usable) return;

    var ctx = run.ctx;
    var frames = usable / frameBytes;
    var view = new DataView(bytes.buffer, bytes.byteOffset, usable);
    var buf = ctx.createBuffer(run.channels, frames, run.rate);
    for (var ch = 0; ch < run.channels; ch++) {
      var out = buf.getChannelData(ch);
      for (var i = 0; i < frames; i++) {
        out[i] = view.getInt16((i * run.channels + ch) * 2, true) / 32768;
      }
    }

    var src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    var now = ctx.currentTime;
    var at = Math.max(now + 0.05, run.playhead);
    if (run.scheduled && run.playhead < now) {   // the sound ran dry before this piece came
      run.gaps++;
      run.gapMs += (now - run.playhead) * 1000;
    }
    src.start(at);
    run.playhead = at + buf.duration;
    run.sources.push(src);
    src.onended = function () {
      var at2 = run.sources.indexOf(src);
      if (at2 >= 0) run.sources.splice(at2, 1);
      try { src.disconnect(); } catch (e) { /* already gone */ }
      checkEnd(run, token);
    };

    if (!run.scheduled) {
      run.scheduled = true;
      var wait = (at - now + (ctx.outputLatency || ctx.baseLatency || 0)) * 1000;
      var soundAt = performance.now() + wait;
      run.tapToSound = Math.round(soundAt - run.tapAt);
      showStats(run);
      run.soundTimer = setTimeout(function () {
        if (token !== playToken) return;
        run.started = true;
        face.setActivity('talking');
        setButton(run.btn, 'Playing…', true);
      }, Math.max(0, wait));
    }
  }

  function pump(run, token) {
    return run.reader.read().then(function (r) {
      if (run.dead || token !== playToken) return null;
      if (r.done) {
        run.streamDone = true;
        checkEnd(run, token);
        return null;
      }
      if (r.value && r.value.length) queueBytes(run, token, r.value);
      return pump(run, token);
    });
  }

  function playCandidate(c, card, btn) {
    var tapAt = performance.now();
    stopSound();
    var token = ++playToken;
    var female = c.gender === 'female';

    card.querySelector('.errbox').hidden = true;
    card.querySelector('.stats').hidden = true;
    setButton(btn, 'Getting ' + (female ? 'her' : 'his') + ' voice ready…', true);
    face.setCompanion(female ? 'mary' : 'him');
    face.setActivity('thinking');

    // Made right here, inside the tap, so the browser lets it make sound.
    var ctx = null;
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      ctx = new AC();
    } catch (e) {
      ctx = null;
    }
    if (!ctx) {
      fail(card, btn, BAD_SOUND);
      return;
    }
    try {
      var resumed = ctx.resume();
      if (resumed && resumed.catch) resumed.catch(function () {});
    } catch (e2) { /* it may start on its own */ }

    var run = {
      c: c, card: card, btn: btn, ctx: ctx, tapAt: tapAt,
      reader: null, sources: [], soundTimer: 0, leftover: null,
      rate: 24000, channels: 1, playhead: 0,
      scheduled: false, started: false, streamDone: false, streamBroke: false, dead: false, logged: false,
      tapToSound: null, cached: false, gaps: 0, gapMs: 0, loadMs: 0
    };
    current = run;

    fetch('/api/mary/voices/stream', {
      method: 'POST',
      headers: HEADERS,
      body: JSON.stringify({id: c.id})
    })
      .then(function (res) {
        if (token !== playToken) {
          try { if (res.body && res.body.cancel) res.body.cancel(); } catch (e3) { /* nothing to cancel */ }
          return null;
        }
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (j) {
            if (token === playToken) fail(card, btn, errorText(j));
          });
        }
        var rate = Number(res.headers.get('X-Rate'));
        var channels = Number(res.headers.get('X-Channels'));
        run.rate = rate > 0 ? rate : 24000;
        run.channels = channels >= 1 && channels <= 2 ? Math.floor(channels) : 1;
        run.cached = res.headers.get('X-Cached') === '1';
        run.loadMs = Math.max(0, Number(res.headers.get('X-Load-Ms')) || 0);
        if (res.body && res.body.getReader) {
          run.reader = res.body.getReader();
          return pump(run, token);
        }
        return res.arrayBuffer().then(function (buf) {
          if (run.dead || token !== playToken) return;
          queueBytes(run, token, new Uint8Array(buf));
          run.streamDone = true;
          checkEnd(run, token);
        });
      })
      .catch(function () {
        if (run.dead || token !== playToken) return;
        if (run.tapToSound === null) {
          fail(card, btn, BAD_SOUND);
          return;
        }
        run.streamBroke = true;
        run.streamDone = true;
        checkEnd(run, token);
      });
  }

  function choose(id, gender) {
    var female = gender === 'female';
    var body = female ? {voice_mary: id} : {voice_sam: id};
    return fetch('/api/settings', {
      method: 'PUT',
      headers: HEADERS,
      body: JSON.stringify(body)
    })
      .then(function (res) {
        if (!res.ok) return false;
        data.chosen = data.chosen || {};
        if (female) data.chosen.mary = id;
        else data.chosen.him = id;
        markChosen();
        return true;
      })
      .catch(function () { return false; });
  }

  function markChosen() {
    var chosen = (data && data.chosen) || {};
    var nodes = document.querySelectorAll('[data-id]');
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var female = node.getAttribute('data-gender') === 'female';
      var isChosen = node.getAttribute('data-id') === (female ? chosen.mary : chosen.him);
      node.classList.toggle('chosen', isChosen);
      if (node.classList.contains('card')) {
        var use = node.querySelector('.use');
        if (isChosen) use.textContent = female ? "✓ Mary's voice" : "✓ Sam's voice";
        else use.textContent = female ? 'Use for Mary' : 'Use for Sam';
      }
    }
  }

  function makeCard(c, hasKey) {
    var female = c.gender === 'female';
    var card = el('article', 'card');
    card.setAttribute('data-id', c.id);
    card.setAttribute('data-gender', c.gender);
    card.appendChild(el('h3', 'vname', niceName(c.voice)));
    card.appendChild(el('p', 'about', c.about));

    var play = el('button', 'btn dark play');
    play.type = 'button';
    if (c.kind === 'gemini' && !hasKey) {
      setButton(play, 'Needs the Gemini key (My info)', true);
    } else if (!c.ready) {
      setButton(play, 'Not set up yet', true);
    } else {
      setButton(play, '▶ Play', false);
    }
    play.addEventListener('click', function () { playCandidate(c, card, play); });
    card.appendChild(play);

    var stats = el('p', 'stats');
    stats.hidden = true;
    card.appendChild(stats);

    var err = el('div', 'errbox');
    err.setAttribute('role', 'alert');
    err.hidden = true;
    card.appendChild(err);

    var use = el('button', 'btn light use', female ? 'Use for Mary' : 'Use for Sam');
    use.type = 'button';
    use.addEventListener('click', function () {
      choose(c.id, c.gender).then(function (ok) {
        if (!ok) showError(card, BAD_SAVE);
      });
    });
    card.appendChild(use);

    return card;
  }

  function renderLive() {
    var box = byId('liveVoices');
    var voices = data.live.voices;
    var first = null;
    box.textContent = '';

    voices.forEach(function (v) {
      if (!first && v.gender === 'female') first = v;
    });

    voices.forEach(function (v) {
      var b = el('button', 'btn light livevoice', (v.gender === 'female' ? 'Mary' : 'Sam') + ' · ' + v.voice);
      b.type = 'button';
      b.setAttribute('data-id', v.id);
      b.setAttribute('data-gender', v.gender);
      b.setAttribute('aria-pressed', v === first ? 'true' : 'false');
      b.addEventListener('click', function () {
        selectedLive = v;
        var all = document.querySelectorAll('.livevoice');
        for (var i = 0; i < all.length; i++) {
          all[i].setAttribute('aria-pressed', all[i] === b ? 'true' : 'false');
        }
      });
      box.appendChild(b);
    });

    selectedLive = first;
  }

  function render() {
    var boxes = {
      gemini: {female: byId('geminiMary'), male: byId('geminiSam')},
      kokoro: {female: byId('offlineMary'), male: byId('offlineSam')}
    };
    data.candidates.forEach(function (c) {
      var group = boxes[c.kind];
      if (!group) return;
      group[c.gender === 'female' ? 'female' : 'male'].appendChild(makeCard(c, data.hasKey));
    });
    renderLive();
    markChosen();
  }

  function showTab(tabId) {
    stopSound();
    Object.keys(TABS).forEach(function (id) {
      var on = id === tabId;
      byId(id).setAttribute('aria-pressed', on ? 'true' : 'false');
      byId(TABS[id]).hidden = !on;
    });
  }

  window.Voices = {face: face, stopSound: stopSound, choose: choose, data: data};

  byId('backBtn').addEventListener('click', function () {
    location.href = '/mary.html';
  });

  Object.keys(TABS).forEach(function (tabId) {
    byId(tabId).addEventListener('click', function () { showTab(tabId); });
  });

  byId('liveUse').addEventListener('click', function () {
    if (!selectedLive) return;
    var status = byId('liveStatus');
    choose(selectedLive.id, selectedLive.gender).then(function (ok) {
      status.textContent = ok ? 'Saved.' : BAD_SAVE;
    });
  });

  fetch('/api/mary/voices')
    .then(function (res) {
      if (!res.ok) throw new Error('voices ' + res.status);
      return res.json();
    })
    .then(function (j) {
      data = {
        candidates: j.candidates || [],
        live: j.live || {},
        chosen: j.chosen || {},
        hasKey: j.has_key !== false
      };
      data.live.voices = data.live.voices || [];
      window.Voices.data = data;
      render();
      window.dispatchEvent(new Event('voices-ready'));
    })
    .catch(function () {
      byId('loadError').hidden = false;
    });
})();
