/* Mary's captions, style A "Coloring-in" (round 6, approved by Andy 2026-10-30).
   Boards: mockups/mary/round6/A-Mary, A-Sam, WordStates, Wrap, SOS-Mary and the live Main board,
   whose script (turns(), renderVals()) is the timing example ported here. Look: captions.css.

   Her voice gives no word times, so they are estimated (round 6 README, "Notes for the builder" 1-3):
   - weight of a word = syllables (vowel groups) + 0.5; a comma adds 1.5 after it, the end of a sentence 3;
   - start = chunk start + chunk length x (weight before it / total weight); a word fills over its own
     share, kept between 180 and 900 ms;
   - while a sentence's length is not known yet, about 2.6 words a second, corrected when it is.
   Times run on the playback clock (AudioContext.currentTime of the scheduled audio), or on
   performance.now() when there is no audio (computer voice, caption only).

   Use:
     const cap = MaryCaptions.create(document.getElementById('scr'), {liveRegion: el, clock: audioCtx});
     const id = cap.sentence('Dinner came late again?', {at: ctx time, dur: null, ctx});  // Normal, Offline
     cap.setDuration(id, seconds);                         // once that sentence's audio length is known
     cap.liveAudio(at, dur, ctx);  cap.livePiece(text);    // Live: every audio chunk, every text piece
     cap.whole(text, {at, dur, ctx});                      // emergency: all of it at once
     cap.cut();  cap.stopped();  cap.clear();  cap.setSide(true);  cap.plain('You said: ...', 'said');
   The caption is aria-hidden (her voice speaks it); each finished sentence goes to liveRegion once. */
(function (root) {
  'use strict';

  const MIN_FILL = 0.18;      // seconds: the quickest a word fills
  const MAX_FILL = 0.9;       // seconds: the slowest a word fills
  const RATE = 2.6;           // words a second, until the real length is known
  const LEAD = 0.15;          // seconds: the next word shows as an empty outline this early
  const COMMA = 1.5;          // extra weight after a comma
  const END = 3;              // extra weight after the end of a sentence
  const HUNGRY = 0.75;        // Live: a piece takes the audio that follows it until it has this much of its estimate
  const FADE_AFTER_MS = 4000; // she finished: fade this long after
  const GONE_MS = 600;        // a line that floated away is removed after this (its fade takes 400 ms)
  const FADE_MS = 450;        // the caption's own fade (400 ms in captions.css), then it is emptied
  const LATER = -1, NEXT = 0, DONE = 10;   // word levels; 1-9 = being said (.on.f1-.f9)

  // ------------------------------------------------------------------ pure parts (tested with Node)
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

  function words(text) {
    return String(text == null ? '' : text).split(/\s+/).filter(Boolean);
  }

  function syllables(word) {
    const m = String(word).toLowerCase().match(/[aeiouyàáâäèéêëìíîïòóôöùúûü]+/g);
    return Math.max(1, m ? m.length : 0);
  }

  function weight(word) { return syllables(word) + 0.5; }

  // Extra weight after a word: the end of a sentence 3, a comma 1.5, else 0. Closing quotes don't hide it.
  function pause(word) {
    const t = String(word).replace(/["'”’)\]]+$/, '');
    if (/[.?!…]$/.test(t)) return END;
    if (/[,;:—–]$/.test(t)) return COMMA;
    return 0;
  }

  function endsSentence(word) { return pause(word) === END; }

  // Seconds a run of n words takes at the streaming rate.
  function estimate(n) { return Math.max(0, n) / RATE; }

  // Each word's {t, start, dur} (seconds) when the words are spoken over [start, start + dur].
  // dur missing or 0 = not known yet: the streaming estimate.
  function plan(ws, start, dur) {
    if (!Array.isArray(ws)) ws = words(ws);
    start = Number(start) || 0;
    const n = ws.length;
    if (!(dur > 0)) dur = estimate(n);
    const wt = [], ps = [];
    let total = 0;
    for (let i = 0; i < n; i++) { wt[i] = weight(ws[i]); ps[i] = pause(ws[i]); total += wt[i] + ps[i]; }
    const end = start + dur, out = [];
    let before = 0;
    for (let i = 0; i < n; i++) {
      const s = start + dur * before / total;
      const share = dur * wt[i] / total;
      // its own share, 180-900 ms, and never past the end of the chunk unless the chunk is too short to fill in
      const d = Math.min(clamp(share, MIN_FILL, MAX_FILL), Math.max(MIN_FILL, end - s));
      out.push({ t: ws[i], start: s, dur: d });
      before += wt[i] + ps[i];
    }
    return out;
  }

  // A word's level at time t: LATER (hidden, holds its place), NEXT (empty outline), 1-9 (filling), DONE.
  function level(w, t) {
    if (t >= w.start + w.dur) return DONE;
    if (t >= w.start) return clamp(Math.ceil(10 * (t - w.start) / w.dur), 1, 9);
    if (t >= w.start - LEAD) return NEXT;
    return LATER;
  }

  // A word never goes back (a corrected length only slows what is still to come).
  function advance(prev, w, t) { return Math.max(prev, level(w, t)); }

  function wordClass(lv, on) {
    let c;
    if (lv === LATER) c = 'w later';
    else if (lv === NEXT) c = 'w';
    else if (lv >= DONE) c = 'w done';
    else c = 'w on f' + lv;
    return on && lv >= DONE ? c + ' on' : c;
  }

  // Greedy line breaks by measured width, never inside a word: the line number of each word.
  // Adding words at the end never moves the earlier ones.
  function breakLines(widths, avail, gap) {
    const out = [];
    let line = 0, used = 0, count = 0;
    for (let i = 0; i < widths.length; i++) {
      const w = Number(widths[i]) || 0;
      const n = count ? used + gap + w : w;
      if (count && n > avail) { line++; used = w; count = 1; } else { used = n; count++; }
      out.push(line);
    }
    return out;
  }

  // Two lines show: the one before the line being said and that line (lines 0 and 1 at first).
  function windowTop(cur) { return Math.max(0, cur - 1); }

  // Live: text pieces (outputTranscription) arrive apart from the audio. Each piece is spread over
  // the audio that came with it: audio not yet claimed when it arrives, or, if there is none yet,
  // the audio that follows until it has about its estimate. Every piece re-anchors on the audio.
  function LiveTrack() { this.reset(); }
  LiveTrack.prototype.reset = function () {
    this.end = null;       // end of all audio heard of
    this.claimed = null;   // audio up to here belongs to a piece
    this.u0 = null;        // start of the audio no piece has taken yet
    this.last = null;      // the latest piece
  };
  // An audio chunk was scheduled at `at` for `dur` seconds. Returns the piece whose timing changed, or null.
  LiveTrack.prototype.audio = function (at, dur) {
    at = Number(at) || 0;
    const e = at + Math.max(0, Number(dur) || 0);
    this.end = this.end == null ? e : Math.max(this.end, e);
    const p = this.last;
    if (p && p.hungry) {
      if (!p.audio) p.at = at;                  // its first sound: re-anchor on it
      p.audio = Math.max(0, e - p.at);
      this.claimed = Math.max(this.claimed == null ? e : this.claimed, e);
      if (p.audio >= p.need * HUNGRY) p.hungry = false;
      p.dur = LiveTrack.dur(p);
      return p;
    }
    if (this.u0 == null) this.u0 = at;
    return null;
  };
  // A text piece of n words arrived at playback time `now`. Returns its {at, dur, need, audio, hungry}.
  LiveTrack.prototype.piece = function (n, now) {
    now = Number(now) || 0;
    const prev = this.last;
    if (prev && prev.hungry) { prev.hungry = false; prev.dur = LiveTrack.dur(prev); }
    const p = { at: now, audio: 0, need: estimate(n), hungry: false, dur: 0 };
    if (this.u0 != null && this.end > now) {    // audio is waiting for words: this piece's
      p.at = this.u0;
      p.audio = this.end - this.u0;
      this.claimed = this.end;
    } else {                                    // its audio is still to come (old leftovers are dropped)
      let floor = this.claimed == null ? now : Math.max(this.claimed, now);
      if (prev && !prev.audio) floor = Math.max(floor, prev.at + prev.dur);
      p.at = floor;
    }
    this.u0 = null;
    p.hungry = p.audio < p.need * HUNGRY;
    p.dur = LiveTrack.dur(p);
    this.last = p;
    return p;
  };
  LiveTrack.dur = function (p) { return p.hungry ? Math.max(p.audio, p.need) : (p.audio || p.need); };

  // ------------------------------------------------------------------ clocks
  function wall() {
    const pf = root.performance;
    return (pf && pf.now ? pf.now() : Date.now()) / 1000;
  }
  // c: an AudioContext (anything with currentTime), a function returning one or seconds, or nothing.
  function readClock(c) {
    let v = c;
    try { if (typeof v === 'function') v = v(); } catch (e) { v = null; }
    if (v && typeof v.currentTime === 'number') return v.currentTime;
    return typeof v === 'number' && isFinite(v) ? v : NaN;
  }
  // A segment's clock: the given one while it answers, else the wall clock (and `at` becomes "now").
  function makeClock(c) {
    const first = readClock(c);
    if (!isFinite(first)) return { now: wall, audio: false };
    let lastT = first;
    return {
      now: function () { const v = readClock(c); if (isFinite(v)) lastT = v; return lastT; },
      audio: true
    };
  }

  // ------------------------------------------------------------------ the caption on screen
  function create(host, opts) {
    opts = opts || {};
    const doc = host.ownerDocument || root.document;
    const win = doc.defaultView || root;
    const rAF = win.requestAnimationFrame ? win.requestAnimationFrame.bind(win) : function (f) { return setTimeout(f, 16); };
    const cAF = win.cancelAnimationFrame ? win.cancelAnimationFrame.bind(win) : clearTimeout;

    function div(cls) { const d = doc.createElement('div'); d.className = cls; return d; }
    const cap = div('cap capA hidden');
    cap.setAttribute('aria-hidden', 'true');
    const track = div('cap-track');
    const meas = div('line cap-measure');
    const plainEl = div('cap-plain');
    plainEl.hidden = true;
    cap.appendChild(track);
    cap.appendChild(meas);
    cap.appendChild(plainEl);
    host.appendChild(cap);

    let liveRegion = opts.liveRegion || null;
    let defaultClock = opts.clock || null;
    let W = [];              // words on screen: {t, el, seg, start, dur, lv, line, width, told}
    let segs = {};           // id -> {id, kind, words, at, dur, est, clock}
    let nextId = 1;
    let lineEls = [];        // line elements, index = line number
    let top = 0;             // first line of the two shown
    let whole = false;       // emergency: everything at once
    let onWord = null;       // emergency: the word being said
    let frozen = false;      // after cut(): nothing fills any more
    let ignoreLive = false;  // after cut(): late pieces of the cut-off speech are dropped
    let state = 'empty';     // 'empty' | 'showing' | 'ending' | 'fading'
    let raf = 0, finishT = 0, fadeT = 0, emptyT = 0, pruneT = 0;
    let firstUntold = 0, tellBuf = [];
    let liveTail = true;     // the last Live piece ended with a space
    const live = new LiveTrack();
    let liveClock = null;    // the context Live audio is scheduled on

    function timers() {
      clearTimeout(finishT); clearTimeout(fadeT); clearTimeout(emptyT); clearTimeout(pruneT);
      finishT = fadeT = emptyT = pruneT = 0;
    }
    function stopLoop() { if (raf) { cAF(raf); raf = 0; } }

    function empty() {
      timers(); stopLoop();
      track.textContent = ''; meas.textContent = '';
      track.style.transform = '';
      W = []; segs = {}; lineEls = []; top = 0; whole = false; onWord = null; frozen = false;
      firstUntold = 0; tellBuf = []; liveTail = true;
      plainEl.hidden = true; plainEl.textContent = '';
      cap.classList.remove('plain', 'whole');
    }

    // New words: a fresh caption after a fade, a cut, a finish or a plain line; else they join the one showing.
    function begin() {
      if (state !== 'showing' || frozen || whole || !plainEl.hidden) empty();
      clearTimeout(fadeT); clearTimeout(emptyT); clearTimeout(finishT);
      state = 'showing';
      cap.classList.remove('hidden');
    }

    function newSeg(kind, o) {
      const clock = makeClock(o.ctx || o.clock || defaultClock);
      const seg = { id: nextId++, kind: kind, words: [], at: 0, dur: 0, est: true, clock: clock };
      seg.at = clock.audio && typeof o.at === 'number' && isFinite(o.at) ? o.at : clock.now();
      seg.est = !(o.dur > 0);
      segs[seg.id] = seg;
      return seg;
    }

    function addWords(seg, toks) {
      for (const t of toks) {
        const el = doc.createElement('span');
        el.className = 'w later';
        el.setAttribute('data-t', t);
        el.textContent = t;
        const w = { t: t, el: el, seg: seg, start: 0, dur: MIN_FILL, lv: LATER, line: 0, width: null, told: false };
        seg.words.push(w);
        W.push(w);
      }
    }

    function replan(seg) {
      const p = plan(seg.words.map(function (w) { return w.t; }), seg.at, seg.est ? 0 : seg.dur);
      if (seg.est) seg.dur = estimate(seg.words.length);
      seg.words.forEach(function (w, i) { w.start = p[i].start; w.dur = p[i].dur; });
    }

    // ---- layout: measure the words, break lines by width, keep two lines in view
    function avail() {
      const a = track.clientWidth || cap.clientWidth;
      return a > 50 ? a : Math.max(200, (win.innerWidth || 1280) - 112);
    }
    function gapPx() {
      let g = NaN;
      try { g = parseFloat(win.getComputedStyle(meas).columnGap); } catch (e) { g = NaN; }
      return isFinite(g) ? g : 0;
    }
    function lineEl(i) {
      while (lineEls.length <= i) { const l = div('line'); lineEls.push(l); track.appendChild(l); }
      return lineEls[i];
    }
    function layout(remeasure) {
      if (!W.length) return;
      const fresh = W.filter(function (w) { return remeasure || w.width == null; });
      fresh.forEach(function (w) { if (!w.el.parentNode) meas.appendChild(w.el); });
      fresh.forEach(function (w) { w.width = w.el.getBoundingClientRect().width; });
      const ln = breakLines(W.map(function (w) { return w.width; }), avail(), gapPx());
      let moved = false;
      W.forEach(function (w, i) { if (w.el.parentNode !== meas && w.line !== ln[i]) moved = true; });
      if (moved) {              // the width changed (menu, window, font): lay every line out again
        lineEls.forEach(function (l) { if (l.parentNode) l.parentNode.removeChild(l); });
        lineEls = [];
      }
      W.forEach(function (w, i) {
        w.line = ln[i];
        const l = lineEl(ln[i]);
        if (w.el.parentNode !== l) l.appendChild(w.el);
      });
      while (lineEls.length > ln[ln.length - 1] + 1) { const l = lineEls.pop(); if (l.parentNode) l.parentNode.removeChild(l); }
      place(true);
    }

    function curLine() {
      let cur = 0;
      for (const w of W) if (w.lv >= NEXT) cur = w.line;
      if (onWord) cur = onWord.line;
      return cur;
    }

    // Show lines top and top+1 at the bottom; earlier lines float up and fade (.gone).
    function place(force) {
      if (whole) {
        lineEls.forEach(function (l) { l.classList.remove('gone'); });
        track.style.transform = '';
        return;
      }
      const t = windowTop(curLine());
      if (t === top && !force) return;
      top = t;
      lineEls.forEach(function (l, i) { l.classList.toggle('gone', i < top); });
      const last = lineEls.length - 1;
      const shown = Math.max(1, Math.min(2, last - top + 1));
      const shift = top - (2 - shown);         // one line only: it sits on the bottom row
      track.style.transform = shift ? 'translateY(' + (-1.2 * shift).toFixed(2) + 'em)' : '';
      if (top > 0 && !pruneT) pruneT = setTimeout(prune, GONE_MS);
    }

    // Lines that floated away leave the page; the rest stay exactly where they are.
    function prune() {
      pruneT = 0;
      const k = top;
      if (k <= 0) return;
      const dropped = W.filter(function (w) { return w.line < k; });
      // they were said long ago: make sure they count as said and were told, then let them go
      // (their sentence keeps them in seg.words, so a later retime still spreads it the same way)
      dropped.forEach(function (w) { if (w.lv < DONE) { w.lv = DONE; w.el.className = wordClass(DONE, false); } });
      if (!whole) tell(false);
      track.style.transition = 'none';
      for (let i = 0; i < k; i++) { const l = lineEls[i]; if (l && l.parentNode) l.parentNode.removeChild(l); }
      lineEls = lineEls.slice(k);
      W = W.filter(function (w) { return w.line >= k; });
      W.forEach(function (w) { w.line -= k; });
      firstUntold = Math.max(0, firstUntold - dropped.length);
      top = 0;
      place(true);
      void track.offsetHeight;                   // apply the jump-free position before the slide comes back
      track.style.transition = '';
    }

    // ---- the polite live region: each finished sentence once
    function announce(text) {
      text = String(text || '').trim();
      if (!text || !liveRegion) return;
      try { liveRegion.textContent = text; } catch (e) { /* nothing */ }
    }
    function tell(flush) {
      const out = [];
      while (firstUntold < W.length && W[firstUntold].lv >= DONE) {
        const w = W[firstUntold++];
        w.told = true;
        tellBuf.push(w.t);
        if (endsSentence(w.t)) { out.push(tellBuf.join(' ')); tellBuf = []; }
      }
      if (flush && tellBuf.length) { out.push(tellBuf.join(' ')); tellBuf = []; }
      if (out.length) announce(out.join(' '));
    }

    // ---- the frame loop: runs only while words are still to fill
    function frame() {
      raf = 0;
      if (frozen) return;
      let busy = false;
      const now = {};
      function tAt(seg) { if (!(seg.id in now)) now[seg.id] = seg.clock.now(); return now[seg.id]; }
      for (const w of W) {
        if (w.lv >= DONE) continue;
        const lv = advance(w.lv, w, tAt(w.seg));
        if (lv !== w.lv) { w.lv = lv; w.el.className = wordClass(lv, false); }
        if (lv < DONE) busy = true;
      }
      if (whole) {
        let on = null;
        for (const w of W) {
          const t = tAt(w.seg);
          if (t >= w.start && t < w.start + Math.max(w.dur, nextStart(w) - w.start)) { on = w; break; }
          if (t < w.start) { busy = true; break; }
        }
        if (on) busy = true;
        if (on !== onWord) {
          if (onWord) onWord.el.className = wordClass(DONE, false);
          onWord = on;
          if (on) on.el.className = wordClass(DONE, true);
        }
      } else {
        tell(false);
      }
      place(false);
      if (busy) raf = rAF(frame);
    }
    function nextStart(w) {
      const ws = w.seg.words, i = ws.indexOf(w);
      return i >= 0 && i + 1 < ws.length ? ws[i + 1].start : w.start + w.dur;
    }
    function kick() { if (!raf && !frozen) raf = rAF(frame); }

    // ---- fades
    function fadeOut() {
      timers(); stopLoop();
      if (state === 'empty') return;
      state = 'fading';
      cap.classList.add('hidden');
      emptyT = setTimeout(function () { empty(); state = 'empty'; }, FADE_MS);
    }
    function finishAll() {
      stopLoop();
      for (const w of W) if (w.lv < DONE) { w.lv = DONE; w.el.className = wordClass(DONE, false); }
      if (onWord) { onWord.el.className = wordClass(DONE, false); onWord = null; }
      if (!whole) tell(true);
      place(false);
    }

    // ------------------------------------------------------------------ the API
    const api = {
      el: cap,

      // Normal / Offline: one sentence whose audio starts at playback time `at` (seconds on ctx) and lasts
      // `dur` seconds; dur null = not known yet (about 2.6 words a second until setDuration). Returns its id.
      sentence: function (text, o) {
        o = o || {};
        const toks = words(text);
        if (!toks.length) return 0;
        begin();
        ignoreLive = false;
        const seg = newSeg('sentence', o);
        if (!seg.est) seg.dur = Number(o.dur);
        addWords(seg, toks);
        replan(seg);
        layout(false);
        kick();
        return seg.id;
      },

      // The real length (seconds) of a sentence's audio, once its stream has ended.
      setDuration: function (id, dur) { api.retime(id, { dur: dur }); },

      // Move a sentence or piece: {at} its start on its clock, {dur} its length. Words never go back.
      retime: function (id, o) {
        const seg = segs[id];
        if (!seg || !o) return;
        if (typeof o.at === 'number' && isFinite(o.at) && seg.clock.audio) seg.at = o.at;
        if (o.dur > 0) { seg.dur = Number(o.dur); seg.est = false; }
        replan(seg);
        kick();
      },

      // Live: an audio chunk scheduled at ctx time `at` for `dur` seconds (talklive playChunk()).
      liveAudio: function (at, dur, ctx) {
        if (ctx) liveClock = ctx;
        const p = live.audio(at, dur);
        if (p && p.segId && segs[p.segId] && !frozen) {
          const seg = segs[p.segId];
          if (seg.clock.audio) seg.at = p.at;
          seg.dur = p.dur; seg.est = false;
          replan(seg);
          kick();
        }
      },

      // Live: a piece of her words (outputTranscription). Spread over the audio that came with it
      // (liveAudio), re-anchored at every piece. {at, dur, ctx} set its timing by hand instead.
      livePiece: function (text, o) {
        o = o || {};
        text = String(text == null ? '' : text);
        if (ignoreLive) return 0;
        let toks = words(text);
        const tail = /\s$/.test(text);
        const glue = toks.length && !/^\s/.test(text) && !liveTail && state === 'showing' && !frozen && !whole && W.length;
        if (glue) {                              // the piece starts inside her last word
          const w = W[W.length - 1];
          w.t += toks[0];
          w.el.setAttribute('data-t', w.t);
          w.el.textContent = w.t;
          w.width = null;
          toks = toks.slice(1);
          if (!toks.length) { liveTail = tail; replan(w.seg); layout(false); kick(); return w.seg.id; }
        }
        if (!toks.length) { if (text) liveTail = true; return 0; }
        begin();
        liveTail = tail;
        const seg = newSeg('live', { ctx: o.ctx || liveClock, at: o.at, dur: o.dur });
        if (o.dur > 0) {
          seg.dur = Number(o.dur);
          live.claimed = Math.max(live.claimed == null ? 0 : live.claimed, seg.at + seg.dur);
        } else {
          const prev = live.last;
          const p = live.piece(toks.length, seg.clock.now());
          p.segId = seg.id;
          const ps = prev && prev.segId && segs[prev.segId];
          if (ps && ps.dur !== prev.dur) { ps.dur = prev.dur; replan(ps); }   // the piece before is now closed
          if (seg.clock.audio) seg.at = p.at;
          seg.dur = p.dur; seg.est = false;
        }
        addWords(seg, toks);
        replan(seg);
        layout(false);
        kick();
        return seg.id;
      },

      // Emergency: the whole text at once, already filled; with audio ({at, dur, ctx}) the word being
      // said lifts (.on) as she says it. Written to the live region at once.
      whole: function (text, o) {
        o = o || {};
        const toks = words(text);
        empty();
        timers();
        ignoreLive = false;
        if (!toks.length) { fadeOut(); return 0; }
        state = 'showing';
        whole = true;
        cap.classList.add('whole');
        cap.classList.remove('hidden');
        const seg = newSeg('whole', o);
        if (!seg.est) seg.dur = Number(o.dur);
        addWords(seg, toks);
        replan(seg);
        for (const w of W) { w.lv = DONE; w.told = true; w.el.className = wordClass(DONE, false); }
        firstUntold = W.length;
        layout(false);
        announce(toks.join(' '));
        if (seg.clock.audio || typeof o.at === 'number' || o.dur > 0) kick();
        return seg.id;
      },

      // She was cut off: stop filling, keep the words she said, fade the rest (300 ms); gone in 4 s.
      cut: function () {
        if (state === 'empty' || state === 'fading') return;
        stopLoop();
        frozen = true;
        ignoreLive = true;
        live.reset();
        for (const w of W) {
          if (w.lv >= 1 && w.lv < DONE) { w.lv = DONE; w.el.className = wordClass(DONE, false); }
          else if (w.lv < 1) w.el.classList.add('cut');
        }
        if (onWord) { onWord.el.className = wordClass(DONE, false); onWord = null; }
        if (!whole) {
          while (firstUntold < W.length && W[firstUntold].lv >= DONE) { tellBuf.push(W[firstUntold].t); W[firstUntold++].told = true; }
          if (tellBuf.length) { announce(tellBuf.join(' ') + '…'); tellBuf = []; }
        }
        state = 'ending';
        clearTimeout(fadeT);
        fadeT = setTimeout(fadeOut, FADE_AFTER_MS);
      },

      // She finished (call it when her audio has played): the last words finish, then fade 4 s later.
      stopped: function () {
        if (state === 'empty' || state === 'fading') return;
        live.reset();
        clearTimeout(finishT); clearTimeout(fadeT);
        let wait = 0;
        if (!frozen) {
          for (const w of W) if (w.lv < DONE || whole) wait = Math.max(wait, w.start + w.dur - w.seg.clock.now());
        }
        wait = clamp(wait, 0, 30);
        state = 'ending';
        finishT = setTimeout(function () {
          finishT = 0;
          if (!frozen) finishAll();
          fadeT = setTimeout(fadeOut, FADE_AFTER_MS);
        }, wait * 1000);
      },

      // The resident is talking: fade now.
      clear: function () {
        ignoreLive = false;
        live.reset();
        fadeOut();
      },

      // While the menu is open the caption keeps to the left (.cap.left) and its lines are laid out again.
      setSide: function (left) {
        left = !!left;
        if (cap.classList.contains('left') === left) return;
        cap.classList.toggle('left', left);
        layout(false);
      },

      // A plain line for things that are not her voice, e.g. plain('You said: ...', 'said').
      plain: function (text, kind) {
        text = String(text == null ? '' : text).trim();
        empty();
        ignoreLive = false;
        if (!text) { fadeOut(); return; }
        state = 'showing';
        plainEl.className = 'cap-plain' + (kind ? ' ' + String(kind).replace(/[^\w-]/g, '') : '');
        plainEl.textContent = text;
        plainEl.hidden = false;
        cap.classList.add('plain');
        cap.classList.remove('hidden');
        announce(text);
      },

      setLiveRegion: function (el) { liveRegion = el || null; },
      setClock: function (c) { defaultClock = c || null; },
      showing: function () { return state === 'showing' || state === 'ending'; },

      destroy: function () {
        empty();
        state = 'empty';
        win.removeEventListener('resize', onResize);
        if (cap.parentNode) cap.parentNode.removeChild(cap);
      }
    };

    // The window or the font changed: measure again.
    let resizeRaf = 0;
    function onResize() {
      if (resizeRaf) return;
      resizeRaf = rAF(function () { resizeRaf = 0; layout(true); });
    }
    win.addEventListener('resize', onResize);
    try {
      if (doc.fonts) {
        doc.fonts.ready.then(function () { layout(true); });
        doc.fonts.addEventListener('loadingdone', function () { layout(true); });
      }
    } catch (e) { /* nothing */ }

    return api;
  }

  const MaryCaptions = {
    create: create,
    // pure parts
    words: words, syllables: syllables, weight: weight, pause: pause, endsSentence: endsSentence,
    estimate: estimate, plan: plan, level: level, advance: advance, wordClass: wordClass,
    breakLines: breakLines, windowTop: windowTop, LiveTrack: LiveTrack,
    MIN_FILL: MIN_FILL, MAX_FILL: MAX_FILL, RATE: RATE, LEAD: LEAD, COMMA: COMMA, END: END,
    LATER: LATER, NEXT: NEXT, DONE: DONE
  };

  root.MaryCaptions = MaryCaptions;
  if (typeof module !== 'undefined' && module.exports) module.exports = MaryCaptions;
})(typeof window !== 'undefined' ? window : globalThis);
