// Care Incident Log - front end. Talks to server.py over /api/*.
'use strict';

/* ---------- Categories (keys and labels match server.py) ---------- */

// tile = what the resident sees on the big buttons; label = the formal name used in the record.
const CATS = [
  { key: 'call_light', color: '#2a78d6', emoji: '\u{1F514}', tile: 'No one answered my call light', label: 'Call light not answered' },
  { key: 'meal', color: '#eb6834', emoji: '\u{1F37D}️', tile: 'My meal was late or missed', label: 'Meal missed or late' },
  { key: 'bathing', color: '#1baf7a', emoji: '\u{1F6C1}', tile: "I didn't get my bath or shower", label: 'Bath or shower missed' },
  { key: 'toileting', color: '#eda100', emoji: '\u{1F6BD}', tile: "I wasn't changed or helped to the toilet", label: 'Toileting / brief change' },
  { key: 'medication', color: '#e87ba4', emoji: '\u{1F48A}', tile: 'Problem with my medicine', label: 'Medication problem' },
  { key: 'repositioning', color: '#008300', emoji: '\u{1F6CF}️', tile: "I wasn't turned or moved", label: 'Not turned or repositioned' },
  { key: 'staff', color: '#6250d6', emoji: '\u{1F5E3}️', tile: 'Staff were rude or rough', label: 'Staff conduct' },
  { key: 'safety', color: '#e34948', emoji: '\u{1FA79}', tile: 'I fell or got hurt', label: 'Fall, injury or safety' },
  { key: 'other', color: '#898781', emoji: '\u{1F4AC}', tile: 'Something else', label: 'Something else' },
];
const CAT = Object.fromEntries(CATS.map(c => [c.key, c]));
const SEV_LABEL = { minor: 'Minor', serious: 'Serious', dangerous: 'Dangerous' };
const WAIT_PRESETS = [15, 30, 60, 120];

/* ---------- Helpers ---------- */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pad = n => String(n).padStart(2, '0');
const isoDate = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseDate = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const daysAgo = n => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - n); return d; };
const nowHM = () => { const d = new Date(); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const minutesOf = t => { const [h, m] = t.split(':').map(Number); return h * 60 + m; };
const fmtDate = (s, long) => parseDate(s).toLocaleDateString(undefined, long ? { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' } : { month: 'short', day: 'numeric' });
const longDate = s => parseDate(s).toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
const fmtTime = t => { const [h, m] = t.split(':').map(Number); return new Date(2000, 0, 1, h, m).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }); };
const fmtStamp = s => `${fmtDate(s.slice(0, 10))}, ${fmtTime(s.slice(11, 16))}`;
const fmtWait = m => m < 60 ? `${m} min` : `${Math.floor(m / 60)} hr${m >= 120 ? 's' : ''}${m % 60 ? ` ${m % 60} min` : ''}`;
const times = n => `${n} ${n === 1 ? 'time' : 'times'}`;
const plainWait = m => {
  if (m < 60) return `${m} ${m === 1 ? 'minute' : 'minutes'}`;
  const h = Math.floor(m / 60), r = m % 60;
  return `${h} ${h === 1 ? 'hour' : 'hours'}${r ? ` ${r} ${r === 1 ? 'minute' : 'minutes'}` : ''}`;
};
const daysBetween = s => Math.round((daysAgo(0) - parseDate(s.slice(0, 10))) / 86400000);

function friendlyDay(s) {
  const n = daysBetween(s);
  if (n === 0) return 'Today';
  if (n === 1) return 'Yesterday';
  if (n > 1 && n < 7) return `${n} days ago`;
  return fmtDate(s, true);
}

// Every request carries the headers the server expects on writes.
async function api(path, opts = {}) {
  const method = opts.method || 'GET';
  const init = { method, headers: { 'Content-Type': 'application/json', 'X-Tracker': '1' } };
  if (method !== 'GET') init.body = opts.body || '{}';
  let res;
  try { res = await fetch(path, init); } catch { throw new Error('Could not reach the tracker. Is it still running?'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || 'Something went wrong. Please try again.'), { status: res.status, code: data.code });
  return data;
}
const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body || {}) });

let toastTimer;
function toast(msg, ms = 4000) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, ms);
}
// Good news fades after 4 seconds; a problem stays up for 8 so it can be read slowly.
const toastError = msg => toast(msg, 8000);

// An "Are you sure?" panel on the page itself (the system box has tiny text). Resolves true for Yes, false for No.
function askConfirm(text) {
  return new Promise(resolve => {
    const box = $('#confirmBox'), yes = $('#confirmYes'), no = $('#confirmNo'), back = document.activeElement;
    $('#confirmText').textContent = text;
    box.hidden = false;
    no.focus(); // the safe answer is the one under the cursor
    const done = answer => {
      box.hidden = true;
      yes.removeEventListener('click', onYes);
      no.removeEventListener('click', onNo);
      box.removeEventListener('click', onBackdrop);
      document.removeEventListener('keydown', onKey, true);
      if (back && back.isConnected) back.focus();
      resolve(answer);
    };
    const onYes = () => done(true);
    const onNo = () => done(false);
    const onBackdrop = e => { if (e.target === box) done(false); };
    const onKey = e => {
      if (e.key === 'Escape') { e.preventDefault(); done(false); }
      else if (e.key === 'Tab') { e.preventDefault(); (document.activeElement === yes ? no : yes).focus(); } // keep focus inside the panel
    };
    yes.addEventListener('click', onYes);
    no.addEventListener('click', onNo);
    box.addEventListener('click', onBackdrop);
    document.addEventListener('keydown', onKey, true);
  });
}

/* ---------- Data ---------- */

let state = { incidents: [], settings: {}, inbox: { available: false, installed: false, enabled: false, items: [] } };
let lastLoad = 0;

async function load() {
  const [incidents, settings, inbox] = await Promise.all([
    api('/api/incidents'),
    api('/api/settings'),
    api('/api/inbox').catch(() => ({ available: false, installed: false, enabled: false, items: [] })),
  ]);
  state = { incidents, settings, inbox: { available: !!inbox.available, installed: !!inbox.installed, enabled: !!inbox.enabled, items: inbox.items || [] } };
  lastLoad = Date.now();
  setBanner('');
}

function setBanner(msg) {
  const b = $('#banner');
  b.hidden = !msg;
  b.textContent = '';
  if (!msg) return;
  const p = document.createElement('span');
  p.textContent = msg + ' ';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'tinybtn';
  btn.textContent = 'Try again';
  btn.addEventListener('click', async () => {
    try { await load(); renderCurrent(); } catch (err) { setBanner(err.message); }
  });
  b.append(p, btn);
}

const recNo = i => `INC-${(i.logged_at || isoDate(new Date())).slice(0, 4)}-${String(i.id).padStart(4, '0')}`;
const monthPrefix = () => isoDate(new Date()).slice(0, 7);
const thisMonth = () => state.incidents.filter(i => (i.occurred_date || '').startsWith(monthPrefix()));
function monthCounts() {
  const counts = {};
  thisMonth().forEach(i => { counts[i.category] = (counts[i.category] || 0) + 1; });
  return counts;
}

function fallbackSummary(i) {
  if (i.summary) return i.summary; // server builds the same sentence the state report uses
  const c = CAT[i.category] || CAT.other;
  const parts = [`Resident reports: ${c.label}.`];
  if (i.never_came) parts.push('No staff member came.');
  else if (i.wait_minutes) parts.push(`Waited ${plainWait(i.wait_minutes)}.`);
  return parts.join(' ');
}

/* ---------- Routing ---------- */

/* ---------- M18: inside Mary's page ---------- */

// Mary opens these screens in a frame on her own page, so going deeper never ends a talk. Her page and this one talk by
// postMessage, to this origin only and checked both ways. A message says what happened, never what was typed.
const IN_MARY = document.documentElement.classList.contains('in-mary');

function toMary(what, more) {
  if (!IN_MARY) return;
  try { window.parent.postMessage({ type: 'mary-deep', what, ...more }, location.origin); } catch { /* she goes on without it */ }
}

// Hands at work on a form aren't quiet: at most one word every 5 s, so her talk doesn't time out.
let maryActAt = 0;
function maryActivity() {
  const now = Date.now();
  if (now - maryActAt < 5000) return;
  maryActAt = now;
  toMary('activity');
}

// The computer has one recorder. While the form holds it she holds the wake word, which lets go of the mic.
let micTold = false;
function micOpen() { return mic.state === 'listening' || mic.state === 'working' || !!field.id || field.busy; }
function tellMaryMic() {
  const on = micOpen();
  if (on === micTold) return;
  micTold = on;
  toMary('mic', { on });
}

// While a talk is open she has the microphone, so the form's Tap and talk buttons step aside.
function maryTalking(on) {
  document.documentElement.classList.toggle('mary-talking', on);
  if (!on || !micOpen()) return;
  teardownMic();
  $('#detailStatus').textContent = '';
  checkMic(); // puts the buttons right for when the talk ends
}

// Her page hid this frame with the mic running: stop the way tapping Stop does, so the words already said stay in the box.
async function micLetGo() {
  for (let n = 0; (mic.state === 'working' || field.busy) && n < 600; n++) await new Promise(r => setTimeout(r, 50));
  if (mic.state === 'listening') await stopTalk();
  else if (field.id) await talkInto(field.id);
}

if (IN_MARY) {
  ['pointerdown', 'input'].forEach(t => document.addEventListener(t, maryActivity, true));
  // Any link to her page closes this frame instead of loading her inside it.
  document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('a[href]');
    if (a && a.pathname === '/mary.html') { e.preventDefault(); toMary('close'); }
  }, true);
  window.addEventListener('message', e => {
    if (e.origin !== location.origin || e.source !== window.parent) return;
    const d = e.data;
    if (!d || d.type !== 'mary-deep') return;
    if (d.what === 'talk') maryTalking(!!d.on);
    else if (d.what === 'hide') micLetGo();
    else if (d.what === 'save') maryAskedSave(); // piece 4
  });
}

// Piece 4: her page asks only on the resident's own plain "save it". This presses Save the way a tap does, with the same
// checks and the same Saved screen. A Save already going answers for itself.
function maryAskedSave() {
  if (cur.screen === 'add') {
    if (add.busy) return;
    const same = !add.inbox && add.cat === add.cleanCat && JSON.stringify(formNow()) === add.clean;
    if (add.saved || same) return toMary('save_none', { why: 'nothing' });
    $('#form').requestSubmit();
  } else if (cur.screen === 'info') {
    if ($('#infoSave').disabled) return;
    if (!infoTouched) return toMary('save_none', { why: 'nothing' });
    $('#infoForm').requestSubmit();
  } else toMary('save_none', { why: 'no_form' });
}

const SCREENS = ['home', 'add', 'saved', 'list', 'inbox', 'report', 'info', 'book-list', 'book-card', 'book-form', 'book-helper'];
let cur = { screen: 'home' };
let pendingInbox = null;
let lastSaved = null;

function showScreen(id) {
  document.documentElement.classList.remove('routing'); // M17
  SCREENS.forEach(s => { $(`#${s}`).hidden = s !== id; });
  $('#infoSaved').hidden = true; // M18
  window.scrollTo(0, 0);
  const h = $('h1', $(`#${id}`));
  if (h) h.focus({ preventScroll: true });
  toMary('screen', { name: id }); // M18
}

function go(name, replace) {
  if (replace) location.replace(`#${name}`); else location.hash = `#${name}`;
}

function route() {
  const [name, arg = ''] = location.hash.replace(/^#/, '').split('/');
  if (cur.screen === 'add') { keepDraft(); teardownMic(); } // M18
  if (bookRoute(name, arg)) return; // M19
  switch (name) {
    case 'add': {
      const opts = arg === 'inbox' && pendingInbox ? { inboxItem: pendingInbox } : CAT[arg] ? { cat: arg } : {};
      cur = { screen: 'add' };
      initAdd(opts);
      showScreen('add');
      return;
    }
    case 'edit': {
      const inc = state.incidents.find(i => i.id === Number(arg));
      if (!inc) return go('list', true);
      cur = { screen: 'add' };
      initAdd({ incident: inc });
      showScreen('add');
      return;
    }
    case 'saved':
      cur = { screen: 'saved', id: Number(arg) };
      if (!renderSaved(cur.id)) return go('home', true);
      return showScreen('saved');
    case 'list':
      cur = { screen: 'list' };
      renderList();
      return showScreen('list');
    case 'inbox':
      if (!state.inbox.available) return go('home', true);
      cur = { screen: 'inbox' };
      renderInbox();
      return showScreen('inbox');
    case 'report':
      cur = { screen: 'report' };
      renderReport(true);
      return showScreen('report');
    case 'info':
      cur = { screen: 'info' };
      if (IN_MARY && infoDirty) { loadSkills(); loadMemories(); loadMail(); } else fillInfo(); // M18: half-typed My info stays
      return showScreen('info');
    default:
      cur = { screen: 'home' };
      if (name && name !== 'home') history.replaceState(null, '', '#home');
      renderHome();
      return showScreen('home');
  }
}

// Re-draw whichever screen shows saved data (never the ones with unsaved input).
function renderCurrent() {
  switch (cur.screen) {
    case 'home': return renderHome();
    case 'list': return renderList();
    case 'saved': return renderSaved(cur.id);
    case 'report': return renderReport(false);
    case 'inbox':
      if (!state.inbox.available) return go('home', true);
      return renderInbox();
  }
}

/* ---------- Home ---------- */

function buildTiles() {
  $('#grid').innerHTML = CATS.map(c => `
    <button type="button" class="tile" id="tile-${c.key}" data-cat="${c.key}" style="--c:${c.color}">
      <span class="trow"><span class="bubble" aria-hidden="true">${c.emoji}</span><span class="num" id="num-${c.key}" aria-hidden="true"></span></span>
      <span class="tlabel">${esc(c.tile)}</span>
      <span class="tcount" id="cnt-${c.key}" aria-hidden="true"></span>
    </button>`).join('');
  $('#groupopts').innerHTML = CATS.map(c => `
    <label class="opt" style="--c:${c.color}"><input type="radio" name="type" value="${c.key}" id="type-${c.key}"><span class="box row"><span class="t"><span aria-hidden="true">${c.emoji}</span> ${esc(c.tile)}</span></span></label>`).join('');
}

function lastNoteWords() {
  const stamps = state.incidents.map(i => i.logged_at).filter(Boolean).sort();
  if (!stamps.length) return '';
  const s = stamps[stamps.length - 1], n = daysBetween(s);
  if (n <= 0) return 'today';
  if (n === 1) return 'yesterday';
  if (n < 14) return `${n} days ago`;
  if (n < 60) return `${Math.floor(n / 7)} weeks ago`;
  return `on ${fmtDate(s.slice(0, 10), true)}`;
}

function renderHome() {
  const first = (state.settings.resident_name || '').trim().split(/\s+/)[0];
  $('#who').textContent = first ? `Hello, ${first}` : '';
  $('#maryName').textContent = state.settings.companion === 'him' ? 'Sam' : 'Mary';
  $('#maryTo').hidden = false; // the link says just "Talk" until we know which friend it is (Mary if settings can't load)

  const month = thisMonth(), counts = monthCounts();
  CATS.forEach(c => {
    const n = counts[c.key] || 0;
    $(`#num-${c.key}`).textContent = n;
    $(`#cnt-${c.key}`).textContent = `${n === 1 ? 'time' : 'times'} this month`;
    $(`#tile-${c.key}`).setAttribute('aria-label', `${c.tile}. ${n === 0 ? 'Not yet this month' : `${times(n)} this month`}.`);
  });

  const total = month.length, never = month.filter(i => i.never_came).length, last = lastNoteWords();
  if (total) {
    const top = CATS.filter(c => counts[c.key]).sort((a, b) => counts[b.key] - counts[a.key])[0];
    $('#sumline').innerHTML = `This month you wrote down <b>${total} ${total === 1 ? 'problem' : 'problems'}</b>. ` +
      (never ? `No one came <b>${times(never)}</b>.` : 'There were no times when no one came.');
    $('#sumsub').innerHTML = `Most often: <b>${esc(top.tile)} (${times(counts[top.key])})</b>.` + (last ? ` Your last note was ${last}.` : '');
  } else {
    $('#sumline').textContent = "You haven't written anything down this month yet.";
    $('#sumsub').textContent = last ? `Your last note was ${last}.` : 'When something goes wrong, tap the big button and tell me about it.';
  }

  // Andy Flow is Andy's own dictation app: residents without it never see any of this.
  const flow = state.inbox.available, waiting = state.inbox.items.length;
  $('#flowrow').hidden = !flow;
  $('#inboxLink').textContent = waiting ? `From Andy Flow (${waiting} waiting)` : 'From Andy Flow';
}

$('#grid').addEventListener('click', e => {
  const t = e.target.closest('[data-cat]');
  if (t) go(`add/${t.dataset.cat}`);
});
$('#auto').addEventListener('click', () => go('add'));

let pulling = false;
$('#pullBtn').addEventListener('click', async () => {
  if (pulling) return;
  pulling = true;
  const btn = $('#pullBtn');
  btn.disabled = true;
  try {
    const r = await post('/api/inbox/import');
    toast(r.added ? `Added ${r.added} from Andy Flow.` : 'Nothing new in Andy Flow.');
    await load();
    renderCurrent();
  } catch (err) { toastError(err.message); } finally { pulling = false; btn.disabled = false; }
});

/* ---------- Add / edit ---------- */

let add = {};
const radioVal = name => { const r = $(`input[name="${name}"]:checked`); return r ? r.value : ''; };
const setRadio = (name, value) => { $$(`input[name="${name}"]`).forEach(r => { r.checked = r.value === value; }); };
const EXTRA_FIELDS = ['staff_involved', 'reported_to', 'outcome', 'witnesses'];

/* ---------- M18: half-typed work ---------- */
// Inside Mary's page a talk can move the resident around, and #add's one form is shared, so going away and coming back
// used to wipe it. A form with changes is kept here by what it was for, in this page's memory only, until Save. Coming
// back to the same category (or to none, by voice) or the same edit puts it back.
const drafts = new Map();
const formNow = () => ({
  words: $('#words').value, when: radioVal('when'), day: $('#day').value, time: $('#time').value,
  wait: radioVal('wait'), sev: radioVal('sev'), extra: EXTRA_FIELDS.map(k => $(`#${k}`).value),
});
const addKey = () => (add.editing ? `edit:${add.editing.id}` : add.inbox ? `inbox:${add.inbox.kind}:${add.inbox.source_id}` : `new:${add.cat || ''}`);

// Piece 5: how many of her fills are in this form right now, so its record can say she helped. Counts, never a value.
// web/mary/screens.js calls this directly (same origin). Each draft and each edit keeps its own count.
let formNo = 0;
var maryHelp = { // a var, so screens.js finds it on this window
  form: () => add.formId,
  step(by, who) {
    add.helpFills = Math.max(0, (add.helpFills || 0) + by);
    if (by > 0) add.helpWho = who;
  },
};
const helpedBy = () => (add.helpFills ? add.helpWho : (add.editing && add.editing.helped_by) || '');

function keepDraft() {
  if (!IN_MARY || add.saved) return;
  const form = formNow();
  if (JSON.stringify(form) === add.clean) return;
  const key = addKey();
  drafts.delete(key); // the newest goes last
  drafts.set(key, { form, cat: add.cat, formal: add.formal, formalFor: add.formalFor, whenTouched: add.whenTouched, customWait: add.customWait, formId: add.formId, helpFills: add.helpFills, helpWho: add.helpWho });
}

function takeDraft(key) {
  const k = key === 'new:' ? [...drafts.keys()].filter(x => x.startsWith('new:')).pop() : key;
  const d = drafts.get(k);
  drafts.delete(k);
  return d;
}

function putDraft(d) {
  const f = d.form;
  Object.assign(add, { formal: d.formal, formalFor: d.formalFor, whenTouched: d.whenTouched, customWait: d.customWait, formId: d.formId, helpFills: d.helpFills, helpWho: d.helpWho });
  $('#words').value = f.words;
  $('#day').value = f.day;
  $('#time').value = f.time;
  setRadio('when', f.when);
  if (d.customWait) setWait(d.customWait);
  setRadio('wait', f.wait);
  setRadio('sev', f.sev);
  EXTRA_FIELDS.forEach((k, i) => { $(`#${k}`).value = f.extra[i]; });
  setType(d.cat);
}

// A save ends her light (web/mary/screens.js puts it on).
function unlit() { $$('.m9-lit').forEach(el => el.classList.remove('m9-lit')); }

function initAdd({ cat = null, incident = null, inboxItem = null } = {}) {
  const g = inboxItem ? inboxItem.guess || {} : null;
  add = { editing: incident, inbox: inboxItem, cat: null, formal: '', formalFor: '', whenTouched: false, busy: false, customWait: 0, formId: ++formNo, helpFills: 0, helpWho: '' };
  $('#form').reset();
  $('#groupopts').hidden = true;
  $('#moreDetails').open = true; // names and who they told are the proof, so keep it in view
  $('#detailStatus').textContent = '';
  $('#formError').hidden = true;
  $('#micNote').hidden = true;
  $('#assistNote').hidden = true;
  $('#waitCustomOpt').hidden = true;
  $('#day').max = isoDate(new Date());
  $('#saveBtn').disabled = false;
  $('#saveBtn').textContent = 'Save';

  if (incident) {
    $('#words').value = incident.description || '';
    add.formal = incident.formal_summary || '';
    add.formalFor = (incident.description || '').trim();
    setRadio('sev', incident.severity);
    setWait(incident.wait_minutes, incident.never_came);
    EXTRA_FIELDS.forEach(k => { $(`#${k}`).value = incident[k] || ''; });
    $('#moreDetails').open = true;
    applyWhen(incident.occurred_date, incident.occurred_time || '', false);
    $('#addtitle').textContent = 'Change what I wrote down';
  } else if (g) {
    $('#words').value = g.description || inboxItem.text || '';
    $('#addtitle').textContent = 'Add from Andy Flow';
    applyGuess(g, $('#words').value, { fromInbox: true });
  } else {
    $('#addtitle').textContent = cat ? CAT[cat].tile : 'Just tell me what happened';
  }
  setType(incident ? incident.category : g && CAT[g.category] ? g.category : cat);
  add.clean = JSON.stringify(formNow()); // M18: what counts as untouched, before anything kept comes back
  add.cleanCat = add.cat; // piece 4: picking another group is a change too
  const kept = takeDraft(addKey());
  if (kept) putDraft(kept);
  updateWhenUI();
  setMic('checking');
  checkMic();
}

function setType(key) {
  add.cat = CAT[key] ? key : null;
  const c = add.cat ? CAT[add.cat] : null;
  $('#add').style.setProperty('--c', c ? c.color : '#898781');
  $('#addicon').textContent = $('#ctIcon').textContent = c ? c.emoji : '\u{1F3A4}';
  $('#ctText').textContent = c ? c.tile : "Not picked yet. Talk first and I'll pick one, or choose it yourself.";
  const n = c ? monthCounts()[add.cat] || 0 : 0;
  $('#ctx').textContent = c
    ? (n === 0 ? 'You have not written this group down yet this month.' : `You have written this group down ${times(n)} this month.`)
    : 'Talk first. I will find the group and tell you how often you have written it down.';
  $$('input[name="type"]').forEach(r => { r.checked = !!c && r.value === add.cat; });
  updateChg();
}

function updateChg() {
  const open = !$('#groupopts').hidden;
  $('#chg').textContent = open ? 'Close the list' : add.cat ? 'Change group' : 'Choose a group';
  $('#chg').setAttribute('aria-expanded', String(open));
}
$('#chg').addEventListener('click', () => { $('#groupopts').hidden = !$('#groupopts').hidden; updateChg(); });
$('#groupopts').addEventListener('change', e => { if (e.target.name === 'type') setType(e.target.value); });

function updateWhenUI() {
  const k = radioVal('when');
  $('#daybox').hidden = k === 'now';
  $('#dayWrap').hidden = k !== 'pick';
}
$('#form').addEventListener('change', e => {
  if (e.target.name === 'when') { add.whenTouched = true; updateWhenUI(); }
});

// Choose the "When" answer that matches a saved date and time.
function applyWhen(date, time, allowNow) {
  if (!date) return;
  const today = isoDate(new Date());
  $('#time').value = time || '';
  if (date === today) {
    if (allowNow && time && Math.abs(minutesOf(time) - minutesOf(nowHM())) <= 3) { setRadio('when', 'now'); $('#time').value = ''; }
    else setRadio('when', 'earlier');
  } else if (date === isoDate(daysAgo(1))) {
    setRadio('when', 'yesterday');
  } else {
    setRadio('when', 'pick');
    $('#day').value = date;
  }
  updateWhenUI();
}

function collectWhen() {
  const k = radioVal('when') || 'now', today = isoDate(new Date());
  if (k === 'now') return { date: today, time: nowHM() };
  const time = $('#time').value || '';
  if (k === 'earlier') return { date: today, time };
  if (k === 'yesterday') return { date: isoDate(daysAgo(1)), time };
  const day = $('#day').value;
  if (!day) throw Object.assign(new Error('Please choose which day it happened.'), { focus: '#day' });
  if (day > today) throw Object.assign(new Error('That day has not happened yet. Please pick today or an earlier day.'), { focus: '#day' });
  return { date: day, time };
}

function setWait(minutes, never) {
  const m = Number(minutes) || 0;
  if (never) return setRadio('wait', 'never');
  if (WAIT_PRESETS.includes(m)) return setRadio('wait', String(m));
  if (m > 0) {
    add.customWait = m;
    $('#waitCustomText').textContent = fmtWait(m);
    $('#waitCustomOpt').hidden = false;
    return setRadio('wait', 'custom');
  }
  setRadio('wait', '');
}

function collectWait() {
  const v = radioVal('wait');
  if (v === 'never') return { never: true, wait: '' };
  if (v === 'custom') return { never: false, wait: add.customWait };
  return { never: false, wait: v ? Number(v) : '' };
}

// Fill in answers from a guess (voice, tidy or Andy Flow) without overwriting what the resident already chose.
function applyGuess(g, fullText, { fromInbox = false, hadText = false } = {}) {
  if (!g) return false;
  let filled = false;
  if (!add.cat && CAT[g.category]) { add.cat = g.category; }
  if (!radioVal('wait') && (g.never_came || Number(g.wait_minutes) > 0)) { setWait(g.wait_minutes, g.never_came); filled = true; }
  if (!radioVal('sev') && SEV_LABEL[g.severity]) { setRadio('sev', g.severity); filled = true; }
  if (fromInbox) {
    applyWhen(g.occurred_date, g.occurred_time || '', false);
  } else if (!add.whenTouched && g.occurred_time) {
    applyWhen(g.occurred_date || isoDate(new Date()), g.occurred_time, true);
  }
  EXTRA_FIELDS.forEach(k => {
    const el = $(`#${k}`);
    if (g[k] && !el.value.trim()) { el.value = g[k]; filled = true; if (k !== 'witnesses') $('#moreDetails').open = true; }
  });
  if (g.formal_summary && !hadText) { add.formal = g.formal_summary; add.formalFor = fullText.trim(); }
  const note = $('#assistNote');
  note.hidden = !g.assist_error;
  note.textContent = g.assist_error || '';
  return filled;
}

$('#clear').addEventListener('click', () => { $('#words').value = ''; $('#words').focus(); });
// Pressing Enter in a one-line box should not save the note by accident.
$('#form').addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') e.preventDefault(); });

/* ---------- Microphone ---------- */

const mic = { state: 'checking', token: 0, timer: null };
const MIC_LABEL = { idle: 'Tap and talk', loading: 'Getting ready…', listening: 'Stop', working: 'Please wait…' };

function setMic(state, msg = '') {
  mic.state = state;
  const b = $('#mic');
  $('#micwrap').hidden = state === 'checking' || state === 'unavailable';
  b.classList.toggle('listening', state === 'listening');
  b.disabled = state === 'loading' || state === 'working';
  $('#miclabel').textContent = MIC_LABEL[state] || '';
  $('.i-mic', b).toggleAttribute('hidden', state === 'listening');
  $('.i-stop', b).toggleAttribute('hidden', state !== 'listening');
  $('#status').textContent = msg;
  syncTalkButtons();
}

async function checkMic(t = ++mic.token) {
  clearTimeout(mic.timer);
  let r;
  try { r = await api('/api/listen'); } catch (err) { r = { available: false, reason: err.message }; }
  if (t !== mic.token) return;
  if (r.loading) {
    setMic('loading', 'The microphone is getting ready. You can start typing if you like.');
    mic.timer = setTimeout(() => checkMic(t), 1500);
    return;
  }
  if (!r.available) {
    setMic('unavailable');
    const n = $('#micNote');
    n.textContent = r.reason || "Talking isn't set up on this computer yet. You can type instead.";
    n.hidden = false;
    return;
  }
  setMic('idle');
}

function teardownMic() {
  mic.token++;
  clearTimeout(mic.timer);
  if (mic.state === 'listening' || field.id) api('/api/listen/stop?raw=1', { method: 'POST' }).catch(() => {});
  field.id = null;
  field.busy = false;
  mic.state = 'checking';
  tellMaryMic(); // M18
}

$('#mic').addEventListener('click', () => {
  if (mic.state === 'idle') startTalk();
  else if (mic.state === 'listening') stopTalk();
});

async function startTalk() {
  const t = mic.token;
  setMic('working', 'Starting…');
  try {
    await post('/api/listen/start');
  } catch (err) {
    if (t === mic.token) setMic('idle', err.message);
    return;
  }
  if (t !== mic.token) { api('/api/listen/stop', { method: 'POST' }).catch(() => {}); return; }
  setMic('listening', "I'm listening. Keep talking.");
}

async function stopTalk() {
  const t = mic.token;
  setMic('working', 'Writing down what you said…');
  let r;
  try { r = await post('/api/listen/stop'); } catch (err) {
    if (t === mic.token) setMic('idle', err.message);
    return;
  }
  if (t !== mic.token) return;
  const text = String(r.text || '').trim();
  if (!text) return setMic('idle', "I didn't hear anything. Tap and try again, or type below.");
  const ta = $('#words'), hadText = !!ta.value.trim(), hadCat = !!add.cat;
  ta.value = hadText ? `${ta.value.replace(/\s+$/, '')} ${text}` : text;
  ta.scrollTop = ta.scrollHeight;
  const filled = applyGuess(r.guess, ta.value, { hadText });
  if (!hadCat && add.cat) setType(add.cat);
  let msg = !hadCat && add.cat ? `I think this is: ${CAT[add.cat].tile}. Is that right? You can change it below.` : 'Got it. You can fix any words by typing.';
  if (filled) msg += ' I filled in some answers below. Please check them.';
  setMic('idle', msg);
}

/* ---------- Talk into a detail box (staff name, who you told, ...) ---------- */

// The computer has one recorder, so only one microphone listens at a time.
const field = { id: null, busy: false };

function syncTalkButtons() {
  const free = mic.state === 'idle' && !field.busy && !field.id;
  $$('[data-talk]').forEach(b => {
    const mine = field.id === b.dataset.talk;
    b.hidden = mic.state === 'checking' || mic.state === 'unavailable';
    b.disabled = field.busy || !(mine || free);
    b.classList.toggle('listening', mine && !field.busy);
    $('.lbl', b).textContent = mine ? (field.busy ? 'Wait…' : 'Stop') : 'Talk';
  });
  if (field.id || field.busy) $('#mic').disabled = true;
  else $('#mic').disabled = mic.state === 'loading' || mic.state === 'working';
  tellMaryMic(); // M18
}

async function talkInto(id) {
  const note = $('#detailStatus');
  if (field.id === id) { // second tap: stop and write it in the box
    field.busy = true;
    syncTalkButtons();
    note.textContent = 'Writing down what you said…';
    let text = '';
    try { text = String((await post('/api/listen/stop?raw=1')).text || '').trim(); } catch (err) { note.textContent = err.message; }
    field.id = null;
    field.busy = false;
    syncTalkButtons();
    if (text) {
      const box = $(`#${id}`);
      box.value = box.value.trim() ? `${box.value.trim()} ${text}` : text;
      note.textContent = 'Got it. You can fix any words by typing.';
    } else if (note.textContent === 'Writing down what you said…') {
      note.textContent = "I didn't hear anything. Tap Talk and try again.";
    }
    return;
  }
  if (field.id || field.busy || mic.state !== 'idle') return;
  field.busy = true;
  syncTalkButtons();
  const t = mic.token; // M18: a talk can open while this starts
  try {
    await post('/api/listen/start');
    if (t !== mic.token) api('/api/listen/stop?raw=1', { method: 'POST' }).catch(() => {}); // nobody is left to stop it
    else {
      field.id = id;
      note.textContent = "I'm listening. Tap Stop when you're done.";
    }
  } catch (err) { note.textContent = err.message; }
  field.busy = false;
  syncTalkButtons();
}

$$('[data-talk]').forEach(b => b.addEventListener('click', () => talkInto(b.dataset.talk)));

// Used by Save: wait out a start or stop in flight, then stop a box that is still listening (the same path as tapping Stop).
async function finishFieldTalk() {
  for (let n = 0; field.busy && n < 600; n++) await new Promise(r => setTimeout(r, 50));
  if (field.id) await talkInto(field.id);
}

/* ---------- Save ---------- */

const FORM_MISSING = { '#words': 'what happened', '#day': 'which day it happened' }; // piece 4: plain labels, never a value
function formFail(message, focusSel, label) {
  const e = $('#formError');
  e.textContent = message;
  e.hidden = false;
  if (focusSel) $(focusSel).focus(); else e.scrollIntoView({ block: 'center' });
  toMary('saved_fail', { label: label || FORM_MISSING[focusSel] || '' }); // piece 4
}

$('#form').addEventListener('submit', async e => {
  e.preventDefault();
  if (add.busy) return;
  $('#formError').hidden = true;
  if (mic.state === 'listening') await stopTalk(); // Save while still listening: finish the recording first
  if (field.id || field.busy) { // same for a detail box's Talk button: let its words land in the box before they are read
    await finishFieldTalk();
    if (add.busy) return; // another tap on Save got there first
  }
  const text = $('#words').value.trim();
  if (!text) return formFail('Please tell me or type what happened first.', '#words');
  let when;
  try { when = collectWhen(); } catch (err) { return formFail(err.message, err.focus); }
  add.busy = true;
  const btn = $('#saveBtn');
  btn.disabled = true;
  btn.textContent = 'Saving…';
  try {
    let cat = add.cat, formal = add.formalFor === text ? add.formal : '', guessed = {};
    if (!cat || !formal) {
      try {
        guessed = await post('/api/tidy', { text });
        if (!cat && CAT[guessed.category]) { cat = guessed.category; setType(cat); }
        if (!formal && guessed.formal_summary) formal = guessed.formal_summary;
      } catch (err) { if (!cat) throw err; }
    }
    if (!cat) throw Object.assign(new Error('Please choose which group this belongs to.'), { label: 'which group this belongs to' });
    // Anything the resident picked wins; otherwise keep what was heard in their words.
    const w = collectWait();
    const pickedWait = w.never || w.wait !== '';
    const payload = {
      occurred_date: when.date, occurred_time: when.time, category: cat, description: text,
      severity: radioVal('sev') || guessed.severity || '',
      wait_minutes: pickedWait ? w.wait : (guessed.wait_minutes ?? ''),
      never_came: pickedWait ? w.never : !!guessed.never_came,
      formal_summary: formal,
      helped_by: helpedBy(), // piece 5
    };
    EXTRA_FIELDS.forEach(k => { payload[k] = $(`#${k}`).value.trim(); });
    const editing = add.editing;
    if (add.inbox) {
      const it = add.inbox;
      Object.assign(payload, { source: `andyflow-${it.kind}`, source_id: String(it.source_id), inbox_kind: it.kind, inbox_id: it.source_id });
    }
    const r = await api(editing ? `/api/incidents/${editing.id}` : '/api/incidents', { method: editing ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    const id = editing ? editing.id : r.id;
    lastSaved = { id, rec: { ...payload, id, logged_at: editing ? editing.logged_at : new Date().toISOString() } };
    pendingInbox = null;
    try { await load(); } catch { /* the saved screen can still show what was just written */ }
    add.busy = false;
    add.saved = true; // M18: nothing here to keep
    unlit();
    toMary('saved'); // M18
    toMary('saved_ok', { form: 'add' }); // piece 4
    go(`saved/${id}`);
  } catch (err) {
    add.busy = false;
    if (err.status === 404 && add.editing) { // this note was already removed: say so, then show the fresh list
      toastError(err.message);
      try { await load(); } catch { /* the list below still opens */ }
      return go('list', true);
    }
    btn.disabled = false;
    btn.textContent = 'Save';
    formFail(err.message, undefined, err.label);
  }
});

/* ---------- Saved ---------- */

function renderSaved(id) {
  let inc = state.incidents.find(i => i.id === id);
  if (!inc && lastSaved && lastSaved.id === id) inc = lastSaved.rec;
  if (!inc) return false;
  const c = CAT[inc.category] || CAT.other;
  $('#saved').style.setProperty('--c', c.color);
  const n = (monthCounts()[inc.category] || 0);
  const isThisMonth = (inc.occurred_date || '').startsWith(monthPrefix());
  $('#savedlead').textContent = isThisMonth && n ? `That makes ${times(n)} this month for this group.` : 'Nothing else to do. Take your time.';
  $('#rNo').textContent = recNo(inc);
  $('#rType').textContent = c.label;
  $('#rWhen').textContent = longDate(inc.occurred_date) + (inc.occurred_time ? `, ${fmtTime(inc.occurred_time)}` : ' (time not noted)');
  $('#rSum').textContent = inc.formal_summary || fallbackSummary(inc);
  $('#rWords').textContent = inc.description ? `“${inc.description}”` : '(No words written)';
  $('#rHelped').textContent = inc.helped_note || ''; // piece 5: apart from their words
  $('#rHelpedL').hidden = $('#rHelped').hidden = !inc.helped_note;
  return true;
}

/* ---------- What I've written down ---------- */

function entryHTML(i) {
  const c = CAT[i.category] || CAT.other, no = recNo(i);
  const meta = [no, `${friendlyDay(i.occurred_date)}${i.occurred_time ? `, ${fmtTime(i.occurred_time)}` : ''}`,
    i.never_came ? 'No one ever came' : i.wait_minutes ? `waited ${plainWait(i.wait_minutes)}` : '',
    SEV_LABEL[i.severity] || ''].filter(Boolean).join(' · ');
  return `<li class="entry" style="--c:${c.color}">
    <b>${esc(c.tile)}</b>
    <span>${esc(meta)}</span>
    ${i.description ? `<span class="quote">“${esc(i.description)}”</span>` : ''}
    ${i.helped_note ? `<span>${esc(i.helped_note)}</span>` : ''}
    <div class="entryacts">
      <button type="button" class="tinybtn" data-edit="${i.id}" aria-label="Edit note ${esc(no)}">Edit</button>
      <button type="button" class="tinybtn danger" data-del="${i.id}" aria-label="Remove note ${esc(no)}">Remove</button>
    </div></li>`;
}

function renderList() {
  $('#entries').innerHTML = state.incidents.map(entryHTML).join('');
  $('#listEmpty').hidden = state.incidents.length > 0;
}

$('#entries').addEventListener('click', async e => {
  const b = e.target.closest('[data-edit],[data-del]');
  if (!b) return;
  if (b.dataset.edit) return go(`edit/${b.dataset.edit}`);
  if (!(await askConfirm('Remove this note? It will disappear from your list.'))) return;
  b.disabled = true;
  try {
    await api(`/api/incidents/${b.dataset.del}`, { method: 'DELETE' });
    toast('Removed.');
    await load();
    renderList();
  } catch (err) {
    b.disabled = false;
    toastError(err.message);
    try { await load(); renderList(); } catch { /* still can't reach it: the list stays as it was */ } // an entry that is already gone drops off the list
  }
});

/* ---------- From Andy Flow ---------- */

function renderInbox() {
  const items = state.inbox.items;
  $('#inboxEmpty').hidden = items.length > 0;
  $('#inboxList').innerHTML = items.map((it, k) => {
    const g = it.guess || {}, c = CAT[g.category] || CAT.other, at = it.at ? fmtStamp(it.at) : '';
    return `<li class="entry" style="--c:${c.color}">
      <b>${esc(c.tile)}</b>
      <span>${it.kind === 'note' ? 'Note' : 'Dictation'}${at ? ` · ${esc(at)}` : ''}</span>
      <span class="quote">“${esc(it.text)}”</span>
      <div class="entryacts">
        <button type="button" class="tinybtn" data-add="${k}" aria-label="Add this ${it.kind === 'note' ? 'note' : 'dictation'} to what I've written down">Add</button>
        <button type="button" class="tinybtn" data-dismiss="${k}" aria-label="Not an incident: leave this ${it.kind === 'note' ? 'note' : 'dictation'} out">Not an incident</button>
      </div></li>`;
  }).join('');
}

$('#inboxList').addEventListener('click', async e => {
  const b = e.target.closest('[data-add],[data-dismiss]');
  if (!b) return;
  if (b.dataset.add !== undefined) {
    pendingInbox = state.inbox.items[Number(b.dataset.add)] || null;
    return go('add/inbox');
  }
  const it = state.inbox.items[Number(b.dataset.dismiss)];
  if (!it) return;
  b.disabled = true;
  try {
    await post('/api/inbox/dismiss', { kind: it.kind, source_id: it.source_id });
    await load();
    renderCurrent();
  } catch (err) { b.disabled = false; toastError(err.message); }
});

/* ---------- Make a report ---------- */

let reportTouched = false;

function renderReport(entering) {
  const from = $('#repFrom'), to = $('#repTo');
  if (entering) reportTouched = false;
  if (!reportTouched || !from.value || !to.value) {
    const dates = state.incidents.map(i => i.occurred_date).filter(Boolean).sort();
    from.value = dates[0] || isoDate(daysAgo(30));
    to.value = isoDate(new Date());
  }
  updateReportLinks();
}

function updateReportLinks() {
  const from = $('#repFrom').value, to = $('#repTo').value;
  const ok = !!from && !!to && from <= to;
  const q = `from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
  const x = $('#xlsxBtn');
  x.href = ok ? `/api/export.xlsx?${q}` : '#report';
  x.setAttribute('aria-disabled', String(!ok));
  $('#printBtn').setAttribute('aria-disabled', String(!ok));
  const err = $('#repErr');
  err.hidden = ok || !from || !to;
  err.textContent = ok ? '' : 'The first day needs to come before the last day.';
  const n = ok ? state.incidents.filter(i => i.occurred_date >= from && i.occurred_date <= to).length : 0;
  $('#repCount').textContent = ok ? (n === 0 ? 'There is nothing written down on these days.' : `${n} ${n === 1 ? 'note' : 'notes'} on these days.`) : '';
}

['#repFrom', '#repTo'].forEach(s => $(s).addEventListener('change', () => { reportTouched = true; updateReportLinks(); }));
$('#printBtn').addEventListener('click', e => {
  if (e.currentTarget.getAttribute('aria-disabled') === 'true') return;
  const url = `/report?from=${encodeURIComponent($('#repFrom').value)}&to=${encodeURIComponent($('#repTo').value)}`;
  if (!window.open(url, '_blank')) location.href = url;
});
$('#xlsxBtn').addEventListener('click', e => {
  if (e.currentTarget.getAttribute('aria-disabled') === 'true') e.preventDefault();
});

/* ---------- My info ---------- */

const INFO_FIELDS = ['resident_name', 'room', 'facility', 'facility_address', 'state', 'gemini_model'];
const FROM_MARY = new URLSearchParams(location.search).get('from') === 'mary'; // Mary sent the resident here
$('#backToMary').addEventListener('click', () => { if (IN_MARY) toMary('close'); else location.href = '/mary.html'; }); // M17: the bar at the top of every screen

let infoDirty = false; // M18: typed into My info since it was last filled, so coming back doesn't write over it
let infoTouched = false; // piece 4: the same, for #infoForm alone: "save it" presses this form's Save, not the other boxes'
$('#info').addEventListener('input', () => { infoDirty = true; });
$('#info').addEventListener('change', () => { infoDirty = true; });

function fillInfo() {
  infoDirty = false;
  infoTouched = false;
  const s = state.settings;
  INFO_FIELDS.forEach(k => { $(`#i-${k}`).value = s[k] || ''; });
  $('#i-gemini_enabled').checked = s.gemini_enabled === '1';
  $('#i-gemini_key').value = '';
  $('#keyState').textContent = s.gemini_key_set ? 'A key is saved. Leave this empty to keep it.' : 'No key is saved yet.';
  $('#infoError').hidden = true;
  updateGemState();
  // The Andy Flow switch only appears on a computer that has Andy Flow; the link starts off.
  $('#flowInfo').hidden = !state.inbox.installed;
  $('#i-andyflow_enabled').checked = s.andyflow_enabled === '1';
  updateFlowState();
  // M4a: talk mode (Live by default) and how long she waits
  const mode = ['live', 'normal', 'offline'].includes(s.talk_mode) ? s.talk_mode : 'live';
  document.querySelector(`input[name="talk_mode"][value="${mode}"]`).checked = true;
  const wait = Number(s.listen_wait) >= 3.5 ? '4' : '2.5';
  document.querySelector(`input[name="listen_wait"][value="${wait}"]`).checked = true;
  $('#i-talk_on_open').checked = s.talk_on_open !== '0'; // M4a: on unless turned off
  $('#i-wake_word').checked = s.wake_word !== '0'; // M6
  loadSkills();
  loadMemories(); // M9c
  loadMail(); // M15d
}

/* ---------- Things Mary can do ---------- */

function skillBtn(text, pressed, disabled, onTap) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'skillbtn';
  b.textContent = text;
  b.setAttribute('aria-pressed', pressed ? 'true' : 'false');
  b.disabled = !!disabled;
  b.addEventListener('click', onTap);
  return b;
}

function renderSkills(list) {
  const rows = $('#skillsList'), locks = $('#skillsLocks');
  rows.textContent = ''; locks.textContent = '';
  $('#skillsMsg').textContent = list.length ? '' : "Mary doesn't have any extra skills yet.";
  $('#skillsLockHead').hidden = !list.length;
  list.forEach(s => {
    const url = `/api/mary/skills/${encodeURIComponent(s.name)}`;
    const row = document.createElement('div');
    row.className = 'skillrow';
    const t = document.createElement('div');
    t.className = 'skilltext';
    const h = document.createElement('b'); h.textContent = s.title || s.name;
    const p = document.createElement('p'); p.className = 'note'; p.textContent = s.summary || '';
    t.append(h, p);
    if (s.tripped) { const w = document.createElement('p'); w.className = 'warn'; w.textContent = 'Not working right now'; t.append(w); }
    row.append(t);
    const label = s.locked ? 'Set by your helper' : (s.on ? 'On' : 'Off');
    row.append(skillBtn(label, s.on, !!s.locked, () => skillChange(url, { on: !s.on })));
    rows.append(row);

    const lr = document.createElement('div');
    lr.className = 'skillrow lockrow';
    const ln = document.createElement('b'); ln.textContent = s.title || s.name;
    const grp = document.createElement('div'); grp.className = 'skillgroup';
    [['Resident chooses', null], ['Always on', 'on'], ['Always off', 'off']].forEach(([text, val]) => {
      grp.append(skillBtn(text, (s.locked || null) === val, false, () => skillChange(url + '/lock', { state: val })));
    });
    lr.append(ln, grp);
    locks.append(lr);
  });
}

async function loadSkills() {
  try { renderSkills((await api('/api/mary/skills')).skills || []); }
  catch (err) { $('#skillsMsg').textContent = "I couldn't get Mary's skills just now. " + err.message; }
}

async function skillChange(path, body) {
  try {
    const r = await api(path, { method: 'PUT', body: JSON.stringify(body) });
    if (r && r.error) throw new Error(r.error === 'locked' ? 'Your helper set this one.' : r.error);
    await loadSkills(); // show what the server now says
  } catch (err) {
    $('#skillsMsg').textContent = "That didn't change. " + err.message;
  }
}

/* ---------- Connect email (M15d) ---------- */

// The app password lives only in its own box until Connect sends it, and the box is then emptied.
const MAIL_NAMES = { gmail: 'Gmail', yahoo: 'Yahoo' };
let mailDraws = 0; // an older /api/mail answer must not undo a newer connect or disconnect
let mailGuessed = null; // what the address last pointed to, so a tile they changed by hand stays changed

function mailPick() {
  const on = document.querySelector('input[name="mail_provider"]:checked');
  return on ? on.value : '';
}

function mailShowSteps() {
  const pick = mailPick();
  $('#mailStepsGmail').hidden = pick !== 'gmail';
  $('#mailStepsYahoo').hidden = pick !== 'yahoo';
}

function mailGuess(address) {
  const a = address.trim().toLowerCase();
  if (/@(gmail|googlemail)\.com$/.test(a)) return 'gmail';
  if (/@yahoo\.[a-z.]*[a-z]$/.test(a)) return 'yahoo';
  return null;
}

function drawMail(st) {
  mailDraws += 1;
  $('#mailMsg').textContent = '';
  $('#mailNone').hidden = !!st.available;
  $('#mailOff').hidden = !st.available || !!st.connected;
  $('#mailOn').hidden = !st.available || !st.connected;
  const name = MAIL_NAMES[st.provider];
  $('#mailLine').textContent = `Connected: ${st.address || ''}` + (name ? ` (${name})` : '');
}

async function loadMail() {
  const draw = mailDraws;
  try {
    const st = await api('/api/mail');
    if (draw === mailDraws) drawMail(st);
  } catch (err) {
    if (draw !== mailDraws) return;
    ['#mailNone', '#mailOff', '#mailOn'].forEach(id => { $(id).hidden = true; });
    $('#mailMsg').textContent = "I couldn't check the email setup just now. " + err.message;
  }
}

function mailError(text) {
  $('#mailError').textContent = text;
  $('#mailError').hidden = false;
}

$('#mailAddress').addEventListener('input', () => {
  const guess = mailGuess($('#mailAddress').value);
  if (guess && guess !== mailGuessed) {
    document.querySelector(`input[name="mail_provider"][value="${guess}"]`).checked = true;
    mailShowSteps();
  }
  mailGuessed = guess;
});
document.querySelectorAll('input[name="mail_provider"]').forEach(r => r.addEventListener('change', mailShowSteps));
$('#mailCard').addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') e.preventDefault(); });

$('#pasteMail').addEventListener('click', async () => {
  const btn = $('#pasteMail'), say = $('#mailPassState');
  btn.disabled = true;
  try {
    const text = await readClipboard();
    if (!text) {
      say.textContent = 'There is nothing to paste yet. Copy the app password first, then tap Paste.';
    } else if (/[\r\n]/.test(text) || text.length > 200) { // spaces are fine: Google shows groups of four
      say.textContent = "That doesn't look like an app password. Copy just the letters, then tap Paste.";
    } else {
      $('#mailPass').value = text;
      say.textContent = 'Password pasted. Tap Connect email.';
    }
  } catch {
    say.textContent = "I couldn't reach what you copied. Right-click the box and choose Paste, then tap Connect email.";
  } finally { btn.disabled = false; }
});

$('#mailConnect').addEventListener('click', async () => {
  const btn = $('#mailConnect'), box = $('#mailPass');
  const address = $('#mailAddress').value.trim(), provider = mailPick();
  $('#mailError').hidden = true;
  $('#mailPassState').textContent = '';
  if (!address) { mailError('Type the email address first.'); return; }
  if (!provider) { mailError('Choose Gmail or Yahoo first.'); return; }
  if (!box.value) { mailError('Paste the app password first.'); return; }
  btn.disabled = true;
  btn.textContent = 'Connecting…';
  try {
    const st = await post('/api/mail/connect', { address, provider, password: box.value });
    box.value = '';
    $('#mailTestMsg').textContent = '';
    drawMail(st);
    if (st.connected) $('#mailTest').focus(); // the button they tapped has just gone
  } catch (err) {
    box.value = '';
    mailError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Connect email';
  }
});

$('#mailTest').addEventListener('click', async () => {
  const btn = $('#mailTest'), off = $('#mailDisconnect'), say = $('#mailTestMsg');
  btn.disabled = true;
  off.disabled = true; // a send can take 12 seconds
  btn.textContent = 'Sending…';
  say.textContent = '';
  try {
    const r = await post('/api/mail/test');
    say.textContent = r.ok ? 'Test sent. Check your inbox.' : (r.message || "That test didn't go out. Please try again.");
  } catch (err) {
    say.textContent = err.message;
  } finally {
    btn.disabled = false;
    off.disabled = false;
    btn.textContent = 'Send a test to myself';
  }
});

$('#mailDisconnect').addEventListener('click', async () => {
  if (!(await askConfirm("Disconnect this email? Mary won't be able to send email until it's connected again."))) return;
  const btn = $('#mailDisconnect'), say = $('#mailTestMsg');
  btn.disabled = true;
  say.textContent = '';
  try {
    const st = await post('/api/mail/disconnect');
    drawMail(st);
    if (!st.connected && st.available) $('#mailAddress').focus(); // the button they tapped has just gone
  } catch (err) {
    say.textContent = err.message;
  } finally { btn.disabled = false; }
});

/* ---------- What Mary remembers (M9c) ---------- */

const MEM_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

// "2026-10-30" read by its parts, so the timezone can't shift the day.
function memDate(s) {
  const p = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || ''));
  const mo = p && MEM_MONTHS[Number(p[2]) - 1];
  return mo ? `${mo} ${Number(p[3])}, ${p[1]}` : '';
}

const memName = () => (state.settings.companion === 'him' ? 'Sam' : 'Mary');

// Memories are untrusted text: textContent only.
function memEmpty(box) {
  const p = document.createElement('p');
  p.className = 'note';
  p.textContent = `Nothing saved yet. As you talk, ${memName()} keeps what matters here.`;
  box.textContent = '';
  box.append(p);
}

function memRow(mem, box) {
  const text = String(mem.text || '');
  const row = document.createElement('div');
  row.className = 'skillrow';
  const t = document.createElement('div');
  t.className = 'skilltext';
  const h = document.createElement('b'); h.textContent = text;
  const p = document.createElement('p'); p.className = 'note'; // M15a: a saved family date reads as the date itself; if it only repeats the memory, one line.
  const sd = String(mem.saved_date || '');
  const norm = (x) => String(x).trim().replace(/\.$/, '').toLowerCase();
  p.textContent = sd ? (norm(sd) === norm(text) ? '' : sd) : memDate(mem.date);
  if (p.textContent) t.append(h, p); else t.append(h);
  const btn = skillBtn('Remove', false, false, async () => {
    btn.disabled = true;
    $('#memMsg').textContent = 'Removing…';
    try {
      await api(`/api/mary/memories/${encodeURIComponent(mem.id)}`, { method: 'DELETE' });
      row.remove();
      $('#memMsg').textContent = `Removed. ${memName()} won't bring that up again.`;
      if (!box.querySelector('.skillrow')) memEmpty(box);
    } catch {
      btn.disabled = false;
      $('#memMsg').textContent = "Sorry, that didn't go through. Please try again.";
    }
  });
  btn.removeAttribute('aria-pressed'); // an action, not an on/off switch
  btn.setAttribute('aria-label', 'Remove: ' + text);
  row.append(t, btn);
  return row;
}

async function loadMemories() {
  const box = $('#memList');
  $('#memTitle').textContent = `What ${memName()} remembers`;
  $('#memMsg').textContent = '';
  try {
    const list = (await api('/api/mary/memories')).memories || [];
    if (!list.length) { memEmpty(box); return; }
    box.textContent = '';
    list.forEach(mem => box.append(memRow(mem, box)));
  } catch (err) {
    $('#memMsg').textContent = "I couldn't get the list just now. " + err.message;
  }
}

// The Paste button reads the clipboard with no key combos: through the app window's
// paste_text (desktop.py), or the browser's clipboard in a plain web browser.
// The key is never shown; it goes into the hidden box and only Save sends it.
async function readClipboard() {
  let app = window.pywebview && window.pywebview.api;
  // M18: in Mary's frame the app's bridge is on her page. The words come straight back here, never through a message.
  if (!app) try { app = window.parent.pywebview && window.parent.pywebview.api; } catch { /* no app window */ }
  if (app && typeof app.paste_text === 'function') return ((await app.paste_text()) || '').trim();
  if (navigator.clipboard && navigator.clipboard.readText) return (await navigator.clipboard.readText()).trim();
  throw new Error('no clipboard');
}

$('#pasteKey').addEventListener('click', async () => {
  const btn = $('#pasteKey');
  btn.disabled = true;
  try {
    const text = await readClipboard();
    if (!text) {
      $('#keyState').textContent = 'There is nothing to paste yet. Copy your key first, then tap Paste.';
    } else if (/\s/.test(text) || text.length > 200) {
      $('#keyState').textContent = "That doesn't look like a key. Copy just the key, then tap Paste.";
    } else {
      $('#i-gemini_key').value = text;
      $('#keyState').textContent = 'Key pasted. Tap Save.';
    }
  } catch {
    $('#keyState').textContent = "I couldn't reach what you copied. Right-click the box and choose Paste, then tap Save.";
  } finally { btn.disabled = false; }
});

function updateGemState() { $('#gemState').textContent = $('#i-gemini_enabled').checked ? 'It is on.' : 'It is off.'; }
$('#i-gemini_enabled').addEventListener('change', updateGemState);
function updateFlowState() { $('#flowState').textContent = $('#i-andyflow_enabled').checked ? 'It is on.' : 'It is off.'; }
$('#i-andyflow_enabled').addEventListener('change', updateFlowState);
$('#infoForm').addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') e.preventDefault(); });

$('#infoForm').addEventListener('input', () => { $('#infoSaved').hidden = true; infoTouched = true; }); // M18: a new change isn't saved yet
$('#infoForm').addEventListener('change', () => { infoTouched = true; });
$('#infoForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('#infoSave');
  $('#infoError').hidden = true;
  $('#infoSaved').hidden = true; // M18
  btn.disabled = true;
  const payload = Object.fromEntries(INFO_FIELDS.map(k => [k, $(`#i-${k}`).value.trim()]));
  payload.gemini_enabled = $('#i-gemini_enabled').checked ? '1' : '0';
  // M4a. M17: written only when the resident changed it here, so saving this form never rewrites their pick
  const modePick = document.querySelector('input[name="talk_mode"]:checked').value;
  if (modePick !== (['live', 'normal', 'offline'].includes(state.settings.talk_mode) ? state.settings.talk_mode : 'live')) payload.talk_mode = modePick;
  payload.talk_on_open = $('#i-talk_on_open').checked ? '1' : '0'; // M4a
  payload.wake_word = $('#i-wake_word').checked ? '1' : '0'; // M6
  const waitNow = Number(state.settings.listen_wait) || 2.5, waitPick = document.querySelector('input[name="listen_wait"]:checked').value;
  if ((waitNow >= 3.5 ? '4' : '2.5') !== waitPick) payload.listen_wait = waitPick; // M4a: keep a voice-set 5 or 6 s
  if (state.inbox.installed) payload.andyflow_enabled = $('#i-andyflow_enabled').checked ? '1' : '0';
  const key = $('#i-gemini_key').value.trim();
  if (key) payload.gemini_key = key; // blank means "keep the saved key"
  try {
    state.settings = await api('/api/settings', { method: 'PUT', body: JSON.stringify(payload) });
    try { await load(); } catch { /* the banner says so */ } // so home shows or hides the Andy Flow parts
    fillInfo();
    unlit(); // M18
    $('#infoSaved').hidden = false; // M18: the plain check beside Save; the toast below only says the way back
    toMary('saved'); // M18: a key saved here reaches her at once
    toMary('saved_ok', { form: 'info' }); // piece 4
    if (IN_MARY) {
      // M18: the way back is her own band, still at the top, and a talk may be going on
      const who = state.settings.companion === 'him' ? 'Sam' : 'Mary';
      toast(`Saved. Tap "Back to ${who}" at the top when you're done.`);
    } else if (FROM_MARY) {
      toast(`Saved. Tap "Back to ${$('#backName').textContent}" at the top to talk again.`);
      $('#backToMary').focus({ preventScroll: true }); // M17: the bar is always in view
    }
  } catch (err) {
    $('#infoError').textContent = err.message;
    $('#infoError').hidden = false;
    toMary('saved_fail', {}); // piece 4
  } finally { btn.disabled = false; }
});

/* ---------- Start up ---------- */

// Refresh when the window comes back into view, but never while something is half-typed.
window.addEventListener('focus', async () => {
  if (cur.screen === 'add' || cur.screen === 'info' || add.busy || Date.now() - lastLoad < 2000) return;
  try { await load(); renderCurrent(); } catch (err) { setBanner(err.message); }
});
window.addEventListener('hashchange', route);

buildTiles();
bookInit(); // M19
(async () => {
  try { await load(); } catch (err) { setBanner(err.message); }
  $('#backName').textContent = state.settings.companion === 'him' ? 'Sam' : 'Mary'; // M17
  try { route(); } finally { document.documentElement.classList.remove('routing'); } // M17: never left blank
})();
