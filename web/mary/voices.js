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
  var audio = null;         // the sample playing now
  var audioUrl = null;      // object URL for that sample
  var current = null;       // {card, btn} of the sample being fetched or played
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

  function freeUrl() {
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      audioUrl = null;
    }
  }

  function stopSound() {
    playToken++;
    if (audio) {
      audio.pause();
      audio = null;
    }
    freeUrl();
    if (current) {
      setButton(current.btn, '▶ Play', false);
      current = null;
    }
    face.setActivity('resting');
  }

  function fmtSecs(raw) {
    if (raw === null || raw === '') return '?';
    var ms = Number(raw);
    return isFinite(ms) ? (ms / 1000).toFixed(1) : '?';
  }

  function statsText(c, h) {
    var text = 'First sound in ' + fmtSecs(h.get('X-First-Sound-Ms')) +
      ' s · whole line ' + fmtSecs(h.get('X-Total-Ms')) + ' s';
    if (h.get('X-Cached') === '1') text += ' · saved copy';
    var rtf = Number(h.get('X-Rtf'));
    if (c.kind === 'kokoro' && rtf > 0) text += ' · speed ×' + (1 / rtf).toFixed(1);
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
    current = null;
    setButton(btn, '▶ Play', false);
    face.setActivity('resting');
    showError(card, msg);
  }

  function startSound(c, card, btn, blob, h, token) {
    freeUrl();
    audioUrl = URL.createObjectURL(blob);
    audio = new Audio(audioUrl);

    var stats = card.querySelector('.stats');
    stats.textContent = statsText(c, h);
    stats.hidden = false;
    setButton(btn, 'Playing…', true);

    audio.onplaying = function () {
      if (token === playToken) face.setActivity('talking');
    };
    audio.onended = function () {
      if (token !== playToken) return;
      current = null;
      setButton(btn, '▶ Play again', false);
      face.setActivity('resting');
      face.setMood('happy');
      face.bounce();
    };
    audio.onerror = function () {
      if (token === playToken) fail(card, btn, BAD_SOUND);
    };

    var started = audio.play();
    if (started && started.catch) {
      started.catch(function () {
        if (token === playToken) fail(card, btn, BAD_SOUND);
      });
    }
  }

  function playCandidate(c, card, btn) {
    stopSound();
    var token = ++playToken;
    current = {card: card, btn: btn};
    var female = c.gender === 'female';

    card.querySelector('.errbox').hidden = true;
    card.querySelector('.stats').hidden = true;
    setButton(btn, 'Getting ' + (female ? 'her' : 'his') + ' voice ready…', true);
    face.setCompanion(female ? 'mary' : 'him');
    face.setActivity('thinking');

    fetch('/api/mary/voices/sample', {
      method: 'POST',
      headers: HEADERS,
      body: JSON.stringify({id: c.id})
    })
      .then(function (res) {
        if (res.ok) {
          return res.blob().then(function (blob) {
            if (token === playToken) startSound(c, card, btn, blob, res.headers, token);
          });
        }
        return res.json().catch(function () { return {}; }).then(function (j) {
          if (token === playToken) fail(card, btn, errorText(j));
        });
      })
      .catch(function () {
        if (token === playToken) fail(card, btn, BAD_SOUND);
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
