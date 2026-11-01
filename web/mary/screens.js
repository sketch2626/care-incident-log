/* M18 piece 3a: what Gemini sees of a screen, and the tools to open, explain and fill, as window.MaryScreens.
   LIST is written by hand, one entry per screen. This page never scans a screen, so a field nobody listed doesn't exist
   for her, and a new field stays invisible until someone decides. Deeper screens are web/index.html in #deepFrame, same
   origin, so the page reaches its fields directly. The rules below are code, not manners: she can't be talked round them.
     MaryScreens.isTool(name)            is this one of the screen tools
     MaryScreens.run(name, args, env)    runs it; resolves with what Live gets back
     MaryScreens.nameHere(env)           the plain name of the screen in front of them
     MaryScreens.noContent(text)         a turn with nothing to paste ("yes", "um")
     MaryScreens.pickHeard(turns, back)  the turn their_words pastes
     MaryScreens.reset()                 the frame loaded a new page
   env is the page's: doc() the log's document when it's in view, else null; panel() the open panel's id, else null;
   openDeep(hash); openPanel(id); back(); turns, the turns heard in this talk; incidents() the saved log; companion() 'mary'
   or 'sam'.
   No value here is ever logged or sent to the server. A tool's answer goes to Live and nowhere else. */
(function () {
  'use strict';

  // Her plain answers when she can't do something. D1 is the board's own line.
  var SECRET_NO = "I won't read or fill that one. It's a password, so it stays out of my hands. A helper can type it in.";
  var SWITCH_NO = "That switch is yours to turn on or off. I can tell you what it does.";
  var WORDS_NO = "Your words stay what you said. I can copy in what I heard you say, but I don't write them for you.";
  var SEVERITY_NO = "That one's your call. I can tell you what each one means, and you pick.";
  var REMOVE_NO = "Deleting or removing anything is yours to do by hand. I won't touch it.";
  var UNLISTED_NO = "That's not something I can do on this screen.";
  var NOT_THERE_NO = "There's nothing for me to fill on this screen.";
  var HIDDEN_NO = "That box isn't showing right now.";
  var EMPTY_NO = "I didn't get what to put there. Say it once more.";
  var DATE_NO = "That isn't a date I can use. Tell me the month, the day and the year.";
  var FUTURE_NO = "That day hasn't come yet.";
  var TIME_NO = "That isn't a time I can use. Tell me the hour and the minutes.";
  var NO_UNDO = "I haven't changed that one, so there's nothing to put back.";
  var NO_TURN = "I don't have that. I only keep the last few things you said.";
  var WRONG_SCREEN = "Your words go on the write something down screen.";
  var NOT_OPEN_NO = "I can't open that one.";
  var SAVED_NO = "That one shows by itself after you save.";
  var OFF_NO = "That one isn't switched on here.";
  var SLOW_NO = "That didn't open just now.";
  var READ_UNASKED = "I only read your notes when you ask me to.";
  var READ_WHEN_NO = "I can look by a day or by a month. Tell me which.";
  var READ_GROUP_NO = "I don't know that group. Tell me what kind of problem it was.";
  var READ_FAIL_NO = "I couldn't get to your notes just now.";
  var READ_NONE = "There's nothing saved for that.";

  var GROUPS = [
    { key: 'call_light', label: 'No one answered my call light' },
    { key: 'meal', label: 'My meal was late or missed' },
    { key: 'bathing', label: "I didn't get my bath or shower" },
    { key: 'toileting', label: "I wasn't changed or helped to the toilet" },
    { key: 'medication', label: 'Problem with my medicine' },
    { key: 'repositioning', label: "I wasn't turned or moved" },
    { key: 'staff', label: 'Staff were rude or rough' },
    { key: 'safety', label: 'I fell or got hurt' },
    { key: 'other', label: 'Something else' }
  ];

  var TALK = { id: 'talk', name: 'Your own screen', explain: 'Your face, with nothing else open.', fields: [] };

  var LIST = [
    { id: 'notes', frame: 'home', hash: '#home', name: 'My notes',
      explain: 'The front page of their notes: a line about this month, the big talk button, and the nine groups.',
      labels: ['Just tell me what happened', "What I've written down", 'Make a report', 'My info'],
      groups: true, fields: [] },
    { id: 'write', frame: 'add', hash: '#add', name: 'Write something down',
      explain: 'The form for one care problem. Nothing is kept for good until they save it.',
      groups: true,
      fields: [
        { id: 'words', label: 'Your words', kind: 'words', fill: false,
          explain: 'What happened, in the words they said themselves. It stays theirs; you can only copy in what you heard them say.' },
        { id: 'when', radio: 'when', label: 'When did it happen?', kind: 'choice', fill: true,
          choices: [{ value: 'now', label: 'Just now' }, { value: 'earlier', label: 'Earlier today' },
            { value: 'yesterday', label: 'Yesterday' }, { value: 'pick', label: 'Pick a day' }],
          explain: 'When it happened. Pick a day opens a box for the date.' },
        { id: 'day', label: 'Which day?', kind: 'date', fill: true, past: true,
          hiddenNo: 'That box shows after you pick "Pick a day".',
          explain: 'The day it happened, when it was not today or yesterday.' },
        { id: 'time', label: 'About what time?', kind: 'time', fill: true,
          hiddenNo: 'That box shows after you pick when it happened.',
          explain: 'About what time it happened. A best guess is fine.' },
        { id: 'wait', radio: 'wait', label: 'How long did you wait?', kind: 'choice', fill: true,
          choices: [{ value: '15', label: '15 min' }, { value: '30', label: '30 min' }, { value: '60', label: '1 hour' },
            { value: '120', label: '2+ hours' }, { value: 'never', label: 'No one ever came' }],
          explain: 'How long they waited for someone to come.' },
        { id: 'sev', radio: 'sev', label: 'How bad was it?', kind: 'choice', fill: false, no: SEVERITY_NO,
          choices: [{ value: 'minor', label: 'Minor' }, { value: 'serious', label: 'Serious' }, { value: 'dangerous', label: 'Dangerous' }],
          explain: 'Their own judgment. Minor means it bothered them but they are okay. Serious means it hurt them or really upset them. Dangerous means they could have been badly hurt.' },
        { id: 'staff_involved', label: 'Which staff member was involved?', kind: 'text', fill: true,
          explain: 'A name, or what the person looked like and which shift it was.' },
        { id: 'reported_to', label: 'Who did you tell?', kind: 'text', fill: true,
          explain: 'Who they told about it, like the charge nurse. Inspectors look for this.' },
        { id: 'outcome', label: 'What happened after?', kind: 'text', fill: true,
          explain: 'What came of it afterward.' },
        { id: 'witnesses', label: 'Did anyone else see it? Who?', kind: 'text', fill: true,
          explain: 'Anyone else who saw it, like a roommate or family.' }
      ] },
    { id: 'saved', frame: 'saved', hash: null, name: 'Saved',
      explain: 'Shows the note just saved, the way it will look in the record.', fields: [] },
    { id: 'list', frame: 'list', hash: '#list', name: "What I've written down",
      explain: 'Their saved notes, newest first.', labels: ['Newest first'], fields: [] },
    { id: 'inbox', frame: 'inbox', hash: '#inbox', name: 'From Andy Flow',
      explain: 'Things they dictated in Andy Flow that start with the word Incident.', fields: [] },
    { id: 'report', frame: 'report', hash: '#report', name: 'Make a report',
      explain: 'Makes a report of the days they pick, to print or to save as a spreadsheet.',
      labels: ['Open printable report', 'Download spreadsheet'],
      fields: [
        { id: 'repFrom', label: 'From', kind: 'date', fill: true, explain: 'The first day the report covers.' },
        { id: 'repTo', label: 'To', kind: 'date', fill: true, explain: 'The last day the report covers.' }
      ] },
    { id: 'info', frame: 'info', hash: '#info', name: 'My info', also: 'email',
      explain: 'What goes at the top of their reports, plus how the app is set up. It stays on this computer.',
      fields: [
        { id: 'i-resident_name', label: 'Your name', kind: 'text', fill: true, explain: 'Their name, as it goes on reports.' },
        { id: 'i-room', label: 'Your room number', kind: 'text', fill: true, explain: 'Their room number, as it goes on reports.' },
        { id: 'i-facility', label: 'Name of the care home', kind: 'text', fill: true, explain: 'The name of the home they live in.' },
        { id: 'i-facility_address', label: 'Address of the care home', kind: 'text', fill: true, explain: 'The address of the home they live in.' },
        { id: 'i-state', label: 'State', kind: 'text', fill: true, explain: 'The state the home is in.' },
        { id: 'i-andyflow_enabled', label: 'Connect Andy Flow', kind: 'switch', fill: false,
          explain: 'Lets notes from Andy Flow that start with Incident show up here. Nothing leaves the computer.' },
        { id: 'i-talk_on_open', label: 'Start talking when you open', kind: 'switch', fill: false,
          explain: 'When it is on, you say hello and listen as soon as your screen opens.' },
        { id: 'i-wake_word', label: 'Listen for your name', kind: 'switch', fill: false,
          explain: 'When it is on, saying hey and your name starts a talk. Nothing leaves the laptop until you hear it.' },
        { id: 'i-gemini_enabled', label: 'Use the smart helper', kind: 'switch', fill: false,
          explain: 'When it is on, what they say is sent to Google to tidy it up. Off keeps everything on this computer.' },
        { id: 'i-gemini_key', label: 'Smart helper key', kind: 'secret', fill: false,
          explain: 'A key from Google that lets the smart helper and you work. A helper types or pastes it in.' }
      ] },
    { id: 'email', frame: 'info', hash: '#info', scroll: 'mailCard', name: 'Connect email',
      explain: 'Lets a card or message go out from their own email, only after they say to send it.',
      fields: [
        { id: 'mailAddress', label: 'Email address', kind: 'text', fill: true, address: true, explain: 'Their own email address.' },
        { id: 'mail_provider', radio: 'mail_provider', label: 'Which email is it?', kind: 'choice', fill: true,
          choices: [{ value: 'gmail', label: 'Gmail' }, { value: 'yahoo', label: 'Yahoo' }],
          explain: 'Which company their email is with.' },
        { id: 'mailPass', label: 'App password', kind: 'secret', fill: false,
          explain: 'A special password the email company makes for this app. A helper types or pastes it in.' },
        { id: 'mailConnect', label: 'Connect email', kind: 'switch', fill: false,
          explain: 'Connects their email once the boxes above are filled. The tap is theirs.' }
      ] },
    { id: 'things', panel: 'canPanel', name: 'Things I can do',
      explain: 'Things they can say to you, or tap: slow down, speed up, quieter, louder, more time, typing to you, and My notes.',
      fields: [] },
    { id: 'games', panel: 'gamesPanel', name: 'Games',
      explain: 'The games that are switched on. They can say one or tap it.', fields: [] },
    { id: 'choose', panel: 'choosePanel', name: 'Choose Mary or Sam',
      explain: 'Where they pick which of you they talk with.', fields: [] },
    { id: 'info_panel', panel: 'infoPanel', name: 'My info panel',
      explain: 'How you talk, your voice, how long you wait, your name word, things you can do, and what you remember.',
      labels: ['How you talk', 'Your voice', 'How long you wait', 'Things you can do', 'What you remember', 'More settings'],
      fields: [] }
  ];

  var TOOL_NAMES = ['look_at_screen', 'explain_field', 'fill_field', 'put_back', 'open_screen', 'go_back', 'their_words'];
  var TYPE_MS = 110, TYPE_MIN_MS = 25, TYPE_TOTAL_MS = 1800;   // 2, 21, 214; a long address never drags
  var ROOM_PX = 24;                                            // clear space around a lit field
  var ARRIVE_MS = 4000, ARRIVE_POLL_MS = 60;                   // DEEP_READY_MS in app.js
  var KEEP_TURNS = 5, KEEP_FILLS = 5;
  var READ_MOST = 10;                                          // piece 5: notes read in one go
  var ASK_WORDS = /\b(?:read|reading|hear|tell|what did|saved|wrote|write|written|incidents?|notes?|last|lists?|happened)\b/i;

  var Lit = { el: null };
  var Typing = { finish: null };
  var Undo = {};   // per field, what was there before each of her fills. Held here only, never logged
  var Months = { after: null };   // piece 5: the heard turn behind her offer to go by month

  function no(say) { return { ok: false, say: say }; }

  function byId(id) {
    for (var i = 0; i < LIST.length; i++) { if (LIST[i].id === id) { return LIST[i]; } }
    return null;
  }
  // Every field of a screen. My info and Connect email are one page, so they're one set of fields.
  function fieldsOf(s) {
    var more = s.also ? byId(s.also) : null;
    return (s.fields || []).concat(more ? more.fields : []);
  }
  function here(env) {
    var p = env.panel(), doc = env.doc(), i;
    if (p) { for (i = 0; i < LIST.length; i++) { if (LIST[i].panel === p) { return LIST[i]; } } }
    if (doc) {
      for (i = 0; i < LIST.length; i++) {
        var f = LIST[i].frame, sec = f ? doc.getElementById(f) : null;
        if (sec && !sec.hidden) { return LIST[i]; }
      }
    }
    return TALK;
  }
  function findField(s, want) {
    var w = String(want == null ? '' : want).trim().toLowerCase(), all = fieldsOf(s);
    for (var i = 0; i < all.length; i++) {
      if (all[i].id.toLowerCase() === w || all[i].label.toLowerCase() === w) { return all[i]; }
    }
    return null;
  }
  function radios(doc, f) { return Array.prototype.slice.call(doc.querySelectorAll('input[name="' + f.radio + '"]')); }
  function fieldEl(doc, f) {
    if (!doc) { return null; }
    return f.radio ? (radios(doc, f)[0] || null) : doc.getElementById(f.id);
  }
  // The wall. It holds even if an entry above is wrong: any password box is a secret.
  function isSecret(f, el) { return f.kind === 'secret' || !!(el && el.type === 'password'); }
  function shown(el) {
    for (var n = el; n; n = n.parentElement) { if (n.hidden) { return false; } }
    return !!el;
  }
  function closest(el, sel) { return (el && el.closest) ? el.closest(sel) : null; }

  // The one place a value is read. A secret never gets past the first line.
  function valueOf(doc, f, el) {
    if (isSecret(f, el) || !el) { return undefined; }
    if (f.radio) {
      var on = radios(doc, f).filter(function (r) { return r.checked; })[0];
      if (!on) { return ''; }
      var ch = (f.choices || []).filter(function (c) { return c.value === on.value; })[0];
      return ch ? ch.label : on.value;
    }
    if (f.kind === 'switch') { return el.type === 'checkbox' ? (el.checked ? 'on' : 'off') : undefined; }
    return el.value;
  }
  function cardField(doc, f) {
    var el = fieldEl(doc, f);
    if (isSecret(f, el)) { return { field: f.id, label: f.label, kind: 'secret' }; }   // label and kind, and nothing that could hint
    if (!shown(el)) { return null; }
    var out = { field: f.id, label: f.label, kind: f.kind, explain: f.explain, can_fill: !!f.fill };
    if (f.choices) { out.choices = f.choices.map(function (c) { return c.label; }); }
    var v = valueOf(doc, f, el);
    if (v !== undefined) { out.value = v; }
    return out;
  }
  function isoDay(d) {
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }
  function look(env) {
    var s = here(env), doc = env.doc(), card = { screen: s.name, about: s.explain };
    if (s.labels) { card.labels = s.labels; }
    if (s.groups) { card.groups = GROUPS.map(function (g) { return g.label; }); }
    if (doc && !s.panel) {
      var fields = fieldsOf(s).map(function (f) { return cardField(doc, f); }).filter(Boolean);
      if (fields.length) { card.fields = fields; }
      if (fields.some(function (f) { return f.kind === 'date'; })) { card.today = isoDay(new Date()); }
    }
    return card;
  }

  function fire(win, el, type) {
    var E = win.Event;
    el.dispatchEvent(new E(type, { bubbles: true }));
  }
  function setVal(win, el, v) {
    var C = el.tagName === 'TEXTAREA' ? win.HTMLTextAreaElement : win.HTMLInputElement;
    var d = C && C.prototype ? Object.getOwnPropertyDescriptor(C.prototype, 'value') : null;
    if (d && d.set) { d.set.call(el, v); } else { el.value = v; }
  }
  function still(win) {
    try { return !!(win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches); } catch (e) { return false; }
  }
  // Clear of the fixed Save row, and of the band, which sits above the frame. No focus is ever moved.
  function scrollClear(doc, el) {
    var win = doc.defaultView, r = el.getBoundingClientRect();
    var row = doc.querySelector('.screen:not([hidden]) .m9-row');
    var rowTop = row ? row.getBoundingClientRect().top : 0;
    var bottom = (rowTop > 0 ? rowTop : win.innerHeight) - ROOM_PX, dy = 0;
    if (r.top < ROOM_PX || r.bottom - r.top > bottom - ROOM_PX) { dy = r.top - ROOM_PX; }
    else if (r.bottom > bottom) { dy = r.bottom - bottom; }
    if (dy) { win.scrollBy({ top: dy, behavior: still(win) ? 'auto' : 'smooth' }); }
  }
  function unlight() {
    if (Lit.el) { Lit.el.classList.remove('m9-lit'); }
    Lit.el = null;
  }
  // The light stays until the next field or a save (web/app.js clears it on Save).
  function light(doc, f, el) {
    var t = (f.radio ? closest(el, 'fieldset') : f.kind === 'switch' ? closest(el, '.opt') : null) || el;
    var d = closest(el, 'details');
    if (d && !d.open) { d.open = true; }
    unlight();
    t.classList.add('m9-lit');
    Lit.el = t;
    scrollClear(doc, t);
  }
  function finishTyping() { if (Typing.finish) { Typing.finish(); } }
  // 2, 21, 214. Reduced motion: it appears at once.
  function typeIn(win, el, text) {
    finishTyping();
    return new Promise(function (resolve) {
      var chars = Array.from(text), i = 0, timer = 0;
      var step = Math.max(TYPE_MIN_MS, Math.min(TYPE_MS, Math.floor(TYPE_TOTAL_MS / (chars.length || 1))));
      function end() {
        clearTimeout(timer);
        Typing.finish = null;
        try {
          setVal(win, el, text);
          fire(win, el, 'input');
          fire(win, el, 'change');
        } catch (e) { /* the page went away: Live must still get its answer */ }
        resolve();
      }
      function next() {
        i++;
        if (i >= chars.length) { end(); return; }
        setVal(win, el, chars.slice(0, i).join(''));
        fire(win, el, 'input');
        timer = setTimeout(next, step);
      }
      if (still(win) || chars.length < 2) { end(); return; }
      Typing.finish = end;
      setVal(win, el, '');
      fire(win, el, 'input');
      timer = setTimeout(next, step);
    });
  }
  function setChoice(doc, f, value) {
    var win = doc.defaultView, all = radios(doc, f), on = all[0];
    all.forEach(function (r) { r.checked = r.value === value; if (r.checked) { on = r; } });
    if (on) { fire(win, on, 'input'); fire(win, on, 'change'); }
  }
  // Piece 5: the log's form keeps count of her fills, so its record can say she helped. Only that form: not My info.
  function formHelp(env) {
    var doc = env.doc(), win = doc && here(env).id === 'write' ? doc.defaultView : null;
    return (win && win.maryHelp) || null;
  }
  // changed: this fill really put something new in. form: which form it counted in, as the box may be another form's by then.
  function remember(f, old, changed, env) {
    var list = Undo[f.id] = Undo[f.id] || [], help = formHelp(env);
    list.push({ old: old, form: help ? help.form() : 0, counted: !!(help && changed) });
    if (help && changed) { help.step(1, env.companion ? env.companion() : 'mary'); }
    if (list.length > KEEP_FILLS) { list.shift(); }
  }
  function refusal(f, el) {
    if (isSecret(f, el)) { return SECRET_NO; }
    if (f.kind === 'switch') { return SWITCH_NO; }
    if (f.kind === 'words') { return WORDS_NO; }
    return f.fill ? '' : (f.no || UNLISTED_NO);
  }
  function unlistedNo(want) {
    var w = String(want == null ? '' : want);
    if (/pass|secret|\bkey\b/i.test(w)) { return SECRET_NO; }
    if (/delete|remove|disconnect/i.test(w)) { return REMOVE_NO; }
    return UNLISTED_NO;
  }
  function cleanDate(f, raw) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
    if (!m) { return { no: DATE_NO }; }
    var d = new Date(+m[1], +m[2] - 1, +m[3]);
    if (d.getFullYear() !== +m[1] || d.getMonth() !== +m[2] - 1 || d.getDate() !== +m[3]) { return { no: DATE_NO }; }
    if (f.past && raw > isoDay(new Date())) { return { no: FUTURE_NO }; }
    return { v: raw, show: raw };
  }
  function cleanTime(raw) {
    var m = /^(\d{1,2}):(\d{2})(?:\s*([ap])\.?m\.?)?$/i.exec(raw);
    if (!m) { return { no: TIME_NO }; }
    var h = +m[1], min = +m[2], ap = (m[3] || '').toLowerCase();
    if (ap && (h < 1 || h > 12)) { return { no: TIME_NO }; }
    if (ap === 'p' && h < 12) { h += 12; }
    if (ap === 'a' && h === 12) { h = 0; }
    if (h > 23 || min > 59) { return { no: TIME_NO }; }
    var hm = ('0' + h).slice(-2) + ':' + ('0' + min).slice(-2);
    return { v: hm, show: hm };
  }
  function cleanValue(f, value) {
    var raw = String(value == null ? '' : value).trim();
    if (!raw) { return { no: EMPTY_NO }; }
    if (f.kind === 'date') { return cleanDate(f, raw); }
    if (f.kind === 'time') { return cleanTime(raw); }
    if (f.kind === 'choice') {
      var low = raw.toLowerCase();
      var ch = f.choices.filter(function (c) { return c.value === low || c.label.toLowerCase() === low; })[0];
      if (ch) { return { v: ch.value, show: ch.label }; }
      return { no: "That isn't one of the choices. They are: " + f.choices.map(function (c) { return c.label; }).join(', ') + '.' };
    }
    if (f.address && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(raw)) {   // M18: what goes in the box is the written address
      return { no: 'That box needs it written out, like name@gmail.com. Spell it back to them first, then fill it.' };
    }
    return { v: raw, show: raw };
  }

  function explainField(args, env) {
    var s = here(env), doc = env.doc(), f = findField(s, args.field);
    if (!doc) { return no(NOT_THERE_NO); }
    if (!f) { return no(unlistedNo(args.field)); }
    var el = fieldEl(doc, f);
    if (!el) { return no(UNLISTED_NO); }
    if (!shown(el)) { return no(f.hiddenNo || HIDDEN_NO); }
    light(doc, f, el);
    if (isSecret(f, el)) { return { ok: true, label: f.label, kind: 'secret', explain: f.explain || '', say_plainly: SECRET_NO }; }
    var out = { ok: true, label: f.label, kind: f.kind, explain: f.explain, note: 'Lit on their screen. Explain it in your own words.' };
    if (f.choices) { out.choices = f.choices.map(function (c) { return c.label; }); }
    return out;
  }
  function fillField(args, env) {
    var s = here(env), doc = env.doc(), f = findField(s, args.field);
    if (!f) { return no(unlistedNo(args.field)); }
    if (!doc) { return no(NOT_THERE_NO); }
    var el = fieldEl(doc, f), why = refusal(f, el);
    if (why) { return no(why); }
    if (!el) { return no(UNLISTED_NO); }
    if (!shown(el)) { return no(f.hiddenNo || HIDDEN_NO); }
    var c = cleanValue(f, args.value);
    if (c.no) { return no(c.no); }
    finishTyping();
    var win = doc.defaultView, done = function () {
      return { ok: true, label: f.label, value: c.show, saved: false,
        next: f.address ? 'Spell it back letter by letter and ask "Is that right?" Nothing is saved.'
          : 'Say the value back and ask "Is that right?" Nothing is saved.' };
    };
    light(doc, f, el);
    if (f.radio) {
      var was = radios(doc, f).filter(function (r) { return r.checked; })[0];
      remember(f, was ? was.value : '', (was ? was.value : '') !== c.v, env);
      setChoice(doc, f, c.v);
      return done();
    }
    remember(f, el.value, el.value !== c.v, env);
    if (f.kind !== 'text') {   // a date or a time box only holds a whole value
      setVal(win, el, c.v);
      fire(win, el, 'input');
      fire(win, el, 'change');
      return done();
    }
    return typeIn(win, el, c.v).then(done);
  }
  function putBack(args, env) {
    var s = here(env), doc = env.doc(), f = findField(s, args.field);
    if (!f) { return no(unlistedNo(args.field)); }
    if (!doc) { return no(NOT_THERE_NO); }
    var el = fieldEl(doc, f);
    if (isSecret(f, el)) { return no(SECRET_NO); }
    var list = Undo[f.id];
    if (!el || !list || !list.length) { return no(NO_UNDO); }
    finishTyping();
    var help = formHelp(env);
    if (help && list[list.length - 1].form && list[list.length - 1].form !== help.form()) { return no(NO_UNDO); }   // another form's old value stays out of this one
    var last = list.pop(), old = last.old, win = doc.defaultView;
    if (help && last.counted) { help.step(-1); }
    light(doc, f, el);
    if (f.radio) { setChoice(doc, f, old); }
    else {
      setVal(win, el, old);
      fire(win, el, 'input');
      fire(win, el, 'change');
    }
    return { ok: true, label: f.label, done: 'It is back the way it was. Nothing is saved.' };
  }
  function goBack(args, env) {
    env.back();
    return { ok: true, screen: here(env).name };
  }
  function findOpen(want) {
    var w = String(want == null ? '' : want).trim().toLowerCase(), i;
    for (i = 0; i < LIST.length; i++) {
      if (LIST[i].id === w || LIST[i].name.toLowerCase() === w) { return { s: LIST[i], group: '' }; }
    }
    var key = w.replace(/^write_/, '');
    for (i = 0; i < GROUPS.length; i++) {
      if (GROUPS[i].key === key || GROUPS[i].label.toLowerCase() === w) { return { s: byId('write'), group: GROUPS[i].key }; }
    }
    return null;
  }
  // The frame's own router has the last word: #inbox goes home unless the Andy Flow link is on. So she only says a screen
  // opened once it's the one really showing.
  function arrive(env, s) {
    var want = byId(s.id), began = Date.now();
    return new Promise(function (resolve) {
      function check() {
        if (here(env).frame === want.frame) { resolve(true); return; }
        if (Date.now() - began >= ARRIVE_MS) { resolve(false); return; }
        setTimeout(check, ARRIVE_POLL_MS);
      }
      setTimeout(check, ARRIVE_POLL_MS);   // a hash change lands a moment after it's set
    });
  }
  function openScreen(args, env) {
    var hit = findOpen(args.name), s = hit && hit.s;
    if (!s) { return no(NOT_OPEN_NO); }
    if (s.id === 'saved') { return no(SAVED_NO); }
    if (s.panel) {
      env.openPanel(s.panel);
      return { ok: true, screen: s.name };
    }
    if (!env.openDeep(s.hash + (hit.group ? '/' + hit.group : ''))) { return no(SLOW_NO); }
    return arrive(env, s).then(function (came) {
      if (!came) { return no(s.id === 'inbox' ? OFF_NO : SLOW_NO); }
      var doc = env.doc(), to = s.scroll && doc ? doc.getElementById(s.scroll) : null;
      if (to) { scrollClear(doc, to); }
      return { ok: true, screen: s.name };
    });
  }

  // Turns with nothing in them to keep, even if heard clearly: never offered to their_words.
  var NO_CONTENT = /^\W*(?:(?:you|thank you|thanks|thank you for watching|thanks for watching|bye|okay|ok|so|um+|uh+|yes|yeah|yep|yup|no|nope|right|that's right|correct|sure|please|uh-?huh|mm+-?hm*|hm+)\W*)*$/i;
  function noContent(text) { return NO_CONTENT.test(String(text == null ? '' : text)); }
  // turns: the talk's heard turns, oldest first, each { text, bad }. Only the last five worth offering count.
  // back 1 is what they said before the turn that asked, 2 the one before that, 0 the asking turn itself. When the asking
  // turn is only "yes", it doesn't count, so 1 is still the last thing they really said.
  function pickHeard(turns, back) {
    var list = turns || [], last = list[list.length - 1];
    var good = list.filter(function (t) { return t && !t.bad && String(t.text || '').trim(); }).slice(-KEEP_TURNS).reverse();
    var n = parseInt(back, 10);
    if (!(n >= 0)) { n = 1; }
    var turn = good[(last && !last.bad) ? n : Math.max(n - 1, 0)];
    return turn ? turn.text : null;
  }
  // Only turns_back is read. She has no way to hand it text: what goes in the box is the transcript the page kept.
  function theirWords(args, env) {
    var doc = env.doc(), f = findField(byId('write'), 'words');
    if (!doc || here(env).id !== 'write') { return no(WRONG_SCREEN); }
    var text = pickHeard(env.turns, args.turns_back);
    if (text === null) { return no(NO_TURN); }
    var el = fieldEl(doc, f), now = el.value, win = doc.defaultView;
    light(doc, f, el);
    if (now.trim() && now.trim().slice(-text.length) === text) {
      return { ok: true, done: 'Those words are already in the box.', saved: false };
    }
    remember(f, now, true, env);
    setVal(win, el, now.trim() ? now.replace(/\s+$/, '') + '\n' + text : text);
    fire(win, el, 'input');
    fire(win, el, 'change');
    return { ok: true, done: 'Their own words are in the box, just as they said them. Nothing is saved.', saved: false };
  }

  // Piece 5. The latest thing heard must hold an ask word, or it must answer her offer to go by month.
  function askedToRead(env) {
    var t = env.turns || [], last = t[t.length - 1];
    if (!last) { return false; }
    return ASK_WORDS.test(String(last.text || '')) || (!!Months.after && t[t.length - 2] === Months.after);
  }
  function findGroup(want) {
    var w = String(want).trim().toLowerCase().replace(/^write_/, '');
    return GROUPS.filter(function (g) { return g.key === w || g.label.toLowerCase() === w; })[0] || null;
  }
  function readRow(r) {   // a list of what goes out, so a source, an id or anything added later never does
    var g = findGroup(r.category), sev = String(r.severity || '');
    return { date: r.occurred_date || '', time: r.occurred_time || '', category: (g || GROUPS[8]).label,
      severity: sev.charAt(0).toUpperCase() + sev.slice(1), words: r.description || '', staff: r.staff_involved || '',
      reported_to: r.reported_to || '', outcome: r.outcome || '', witnesses: r.witnesses || '', helped: r.helped_note || '' };
  }
  function countMonths(rows) {
    var seen = {}, out = [];
    rows.forEach(function (r) {
      var m = String(r.occurred_date || '').slice(0, 7);
      if (!seen[m]) { seen[m] = { month: m, count: 0 }; out.push(seen[m]); }
      seen[m].count++;
    });
    return out.slice(0, 12);
  }
  // The rows come newest first from the server. What she gets goes to Live and nowhere else.
  function readIncidents(args, env) {
    if (!askedToRead(env)) { return no(READ_UNASKED); }
    var t = env.turns, heard = t[t.length - 1];
    var when = String(args.when == null ? '' : args.when).trim().toLowerCase();
    var cat = String(args.category == null ? '' : args.category).trim();
    var group = cat ? findGroup(cat) : null;
    if (cat && !group) { return no(READ_GROUP_NO); }
    if (when && when !== 'latest' && !/^\d{4}-\d{2}(?:-\d{2})?$/.test(when)) { return no(READ_WHEN_NO); }
    Months.after = null;
    return Promise.resolve().then(env.incidents).then(function (rows) {
      var hit = (Array.isArray(rows) ? rows : []).filter(function (r) {
        if (r.deleted_at || (group && r.category !== group.key)) { return false; }
        return !when || when === 'latest' || String(r.occurred_date || '').indexOf(when) === 0;
      });
      if (when === 'latest') { hit = hit.slice(0, 1); }
      if (!hit.length) { return { ok: true, count: 0, incidents: [], say: READ_NONE }; }
      var out = { ok: true, count: hit.length, incidents: hit.slice(0, READ_MOST).map(readRow),
        note: "Read what's there and add nothing to it. It stays out of your memories." };
      if (hit.length > READ_MOST) {
        out.by_month = countMonths(hit);
        out.more = 'There are ' + hit.length + ' in all, and these are the newest ' + READ_MOST + '. Say how many, and offer to go by month.';
        Months.after = heard;
      }
      return out;
    }, function () { return no(READ_FAIL_NO); });
  }

  var TOOLS = {
    look_at_screen: function (args, env) { return look(env); },
    explain_field: explainField,
    fill_field: fillField,
    put_back: putBack,
    open_screen: openScreen,
    go_back: goBack,
    their_words: theirWords,
    read_incidents: readIncidents
  };

  // M18: Live gets ONE declared tool, use_screen, with an action. It goes to the same functions, in order.
  var USE_NAME = 'use_screen';
  var ACTIONS = { look: 'look_at_screen', explain: 'explain_field', fill: 'fill_field', put_back: 'put_back',
                  open: 'open_screen', go_back: 'go_back', their_words: 'their_words', read_incidents: 'read_incidents' };
  function useScreen(args, env) {
    var a = args || {}, tool = ACTIONS.hasOwnProperty(String(a.action)) ? ACTIONS[a.action] : null;
    if (!tool) { return no(UNLISTED_NO); }
    var inner = { field: a.field, value: a.value, name: a.name, when: a.when, category: a.category };
    if (tool === 'their_words') {
      var t = typeof a.turns_back === 'string' ? a.turns_back.trim() : a.turns_back;
      if (!/^[0-4]$/.test(String(t))) { return no("I couldn't tell which of your words you meant."); }
      inner = { turns_back: Number(t) };
    }
    return TOOLS[tool](inner, env);
  }

  window.MaryScreens = {
    USE_NAME: USE_NAME,
    ACTIONS: ACTIONS,
    LIST: LIST,
    GROUPS: GROUPS,
    TALK_NAME: TALK.name,
    TOOL_NAMES: TOOL_NAMES,
    isTool: function (name) { return name === USE_NAME || TOOL_NAMES.indexOf(name) >= 0; },
    run: function (name, args, env) {
      if (name !== USE_NAME && TOOL_NAMES.indexOf(name) < 0) { return Promise.resolve(no(UNLISTED_NO)); }
      return new Promise(function (resolve) { resolve(name === USE_NAME ? useScreen(args, env) : TOOLS[name](args || {}, env)); }).catch(function () {
        return no("That didn't work just now.");   // never the error: it could hold a value
      });
    },
    nameHere: function (env) { return here(env).name; },
    noContent: noContent,
    pickHeard: pickHeard,
    finishTyping: finishTyping,   // piece 4: a plain "save it" lets her fill land first
    reset: function () {
      finishTyping();
      Undo = {};
      Months.after = null;
      Lit.el = null;
    }
  };
})();
