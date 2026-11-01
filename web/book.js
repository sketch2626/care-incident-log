// M19 piece 5: the address book's screens, in Mary's frame with her small in the corner. Loaded before app.js, which gives
// this page $, api, post, go and toMary. If you can just ask Mary, it needs no button: there is no Add someone, no forget
// button and no yes button. Every value goes to this page only. What Mary may see of them is listNow() and web/mary/screens.js.
'use strict';

const BOOK_FORM_FIELDS = ['name', 'relationship', 'cell', 'phone', 'email', 'birthday', 'address', 'facebook', 'notes'];
const BOOK_SHUT = {
  locked: "Your address book is locked. A helper's copy can open it.",
  failed: "Your address book didn't open just now.",
};
const BOOK_ROW = 92, BOOK_ROW_ROOM = 168, BOOK_ROWS_LEAST = 3;   // 84 tall and 8 between; the room above and below them

// state: '' while loading, 'open', 'locked' or 'failed'. mode: 'add', 'change' or 'helper'.
const Bk = { state: '', people: [], count: 0, top: 0, end: false, ticket: 0, forget: '', mode: 'add', id: '', clean: '', busy: false,
             helperDay: '', helperCount: 0, card: null, form: 0, was: new Set() };

function bookMatches(people, words) {
  const w = String(words ?? '').trim().toLowerCase();
  return w ? people.filter(p => `${p.name} ${p.relationship}`.toLowerCase().includes(w)) : people;
}
function bookPeople(n) { return `${n} ${n === 1 ? 'person' : 'people'}`; }
// "daughter" reads "Your daughter"; anything longer stays as it was given, with a capital.
function bookRelation(rel) {
  const r = String(rel ?? '').trim();
  if (!r) return '';
  return /\s/.test(r) ? r[0].toUpperCase() + r.slice(1) : `Your ${r[0].toLowerCase()}${r.slice(1)}`;
}
function bookRowsAPage() { return Math.max(BOOK_ROWS_LEAST, Math.floor((window.innerHeight - BOOK_ROW_ROOM) / BOOK_ROW)); }

/* ---------- The list ---------- */

function bookDrawList() {
  const open = Bk.state === 'open', loading = Bk.state === '';
  $('#bookShut').hidden = open || loading;
  $('#bookShut').textContent = BOOK_SHUT[Bk.state] || '';
  $('#bookOpen').hidden = !open;
  $('#bookListBar').hidden = !open;   // the lock line lives here, so it shows only while the book is really open
  if (!open) return;
  const words = $('#bookFind').value.trim(), hits = bookMatches(Bk.people, words), size = bookRowsAPage(), last = Math.max(hits.length - size, 0);
  Bk.top = Bk.end ? last : Math.min(Math.max(Bk.top, 0), last);
  Bk.end = false;
  $('#bookCount').textContent = words ? `${hits.length} of ${Bk.count}` : bookPeople(Bk.count);
  const rows = $('#bookRows');
  rows.replaceChildren(...hits.slice(Bk.top, Bk.top + size).map(p => {
    const b = document.createElement('button'), n = document.createElement('span'), r = document.createElement('span');
    b.type = 'button';
    b.className = words ? 'book-rowbtn lit' : 'book-rowbtn';   // board A2: the rows she narrowed to are lit
    n.className = 'book-nm';
    n.textContent = p.name;
    r.className = 'book-rel';
    r.textContent = bookRelation(p.relationship);
    b.append(n, r);
    b.addEventListener('click', () => go(`book-card/${p.id}`));
    return b;
  }));
  $('#bookNone').hidden = hits.length > 0;
  $('#bookNone').textContent = words ? 'No one by that name.' : 'No one in your address book yet.';
  $('#bookUp').disabled = Bk.top === 0;
  $('#bookDown').disabled = Bk.top >= last;
  $('#bookEveryone').hidden = !words;
}

async function bookShowList() {
  const mine = ++Bk.ticket;
  Bk.state = '';
  bookDrawList();
  try {
    const got = await api('/api/book');
    if (mine !== Bk.ticket) return;
    Bk.state = got.state === 'open' ? 'open' : 'locked';
    Bk.people = got.people || [];
    Bk.count = got.count || 0;
  } catch {
    if (mine !== Bk.ticket) return;
    Bk.state = 'failed';
  }
  bookDrawList();
}

function bookMove(rows) {
  Bk.top += rows;
  bookDrawList();
}
function bookNarrow(words) {
  $('#bookFind').value = words;
  Bk.top = 0;
  bookDrawList();
}

/* ---------- The card ---------- */

function bookCardShut(words) {
  $('#bookCardShut').textContent = words;
  $('#bookCardShut').hidden = !words;
}

async function bookShowCard(id) {
  const mine = ++Bk.ticket;
  Bk.card = null;
  $('#bookCardBody').hidden = true;
  $('#bookStopBar').hidden = true;
  bookCardShut('');
  try {
    const c = await api(`/api/book/${encodeURIComponent(id)}`);
    if (mine !== Bk.ticket) return;
    if (c.state !== 'open') return bookCardShut(BOOK_SHUT.locked);
    BOOK_FORM_FIELDS.forEach(f => { $(`#bc-${f}`).textContent = f === 'birthday' ? c.birthday_words : c[f]; });
    $('#bc-relationship').textContent = bookRelation(c.relationship);
    Bk.card = { name: c.name, relationship: c.relationship };   // all look_at_screen may tell of whose card this is
    $('#bookStop').textContent = `No, keep ${c.them}`;   // never a yes button: she asks, and a spoken yes does it
    $('#bookStopBar').hidden = Bk.forget !== id;
    $('#bookCardBody').hidden = false;
  } catch (err) {
    if (mine !== Bk.ticket) return;
    if (err.status === 404) return go('book-list', true);
    bookCardShut(BOOK_SHUT.failed);
  }
}

/* ---------- The form ---------- */

function bookValues() { return Object.fromEntries(BOOK_FORM_FIELDS.map(f => [f, $(`#bf-${f}`).value])); }
function bookDirty() { return JSON.stringify(bookValues()) !== Bk.clean; }
// E1: her fill on someone who already has a value. The old one shows beside it, for their eyes: no tool reads this line.
function bookWasDraw() {
  const saved = JSON.parse(Bk.clean || '{}');
  BOOK_FORM_FIELDS.forEach(f => {
    const line = $(`#bw-${f}`);
    if (!line) return;
    const old = saved[f] || '', show = !!Bk.id && Bk.was.has(f) && !!old.trim() && $(`#bf-${f}`).value !== old;
    line.textContent = show ? `Was: ${old}` : '';
    line.hidden = !show;
  });
}
function bookFill(values) {
  BOOK_FORM_FIELDS.forEach(f => { $(`#bf-${f}`).value = values[f] ?? ''; });
  Bk.clean = JSON.stringify(bookValues());
  Bk.form++;   // what she filled before this can't be put back into it
  Bk.was.clear();
  bookWasDraw();
}
function bookSay(words, saved) {
  $('#bookMsg').textContent = words;
  $('#bookMsg').hidden = !words;
  $('#bookSaved').hidden = !saved;
}
function bookFormShut(words) {
  $('#bookFormShut').textContent = words;
  $('#bookFormShut').hidden = !words;
  $('#bookFormBody').hidden = !!words;
  $('#bookFormBar').hidden = !!words;
}
function bookHelperCount() {
  const today = isoDate(new Date());
  if (Bk.helperDay !== today) { Bk.helperDay = today; Bk.helperCount = 0; }
  $('#bookAdded').textContent = `${Bk.helperCount} added today`;
  $('#bookAdded').hidden = Bk.helperCount === 0;
}
// One form, with one set of ids: the helper's screen is the same form moved into its own section.
function bookFormMode(mode, id) {
  const helper = mode === 'helper';
  Bk.mode = mode;
  Bk.id = id;
  $(helper ? '#book-helper' : '#book-form').append($('#bookForm'));
  $('#bookAll').hidden = mode !== 'add';
  $('#bookDone').hidden = !helper;
  $('#bookSave').textContent = helper ? 'Save and add another' : 'Save';
  $('#bookSave').classList.toggle('book-wide', helper);
  bookHelperCount();
  if (!helper) $('#bookAdded').hidden = true;
}

async function bookShowForm(id, helper) {
  const mine = ++Bk.ticket, mode = helper ? 'helper' : id ? 'change' : 'add';
  // Half-typed work stays: only another person, or the same form with nothing typed, starts the boxes over.
  const keep = !id && Bk.mode !== 'change' && bookDirty();
  bookFormMode(mode, keep ? Bk.id : id);
  bookSay('', false);
  if (!keep) bookFill({});
  bookFormShut('');
  $('#bookFormBody').hidden = true;
  $('#bookFormBar').hidden = true;
  try {
    const got = await api(id ? `/api/book/${encodeURIComponent(id)}` : '/api/book');
    if (mine !== Bk.ticket) return;
    if (got.state !== 'open') return bookFormShut(BOOK_SHUT.locked);
    if (id) bookFill({ ...got, birthday: got.birthday_words });
    bookFormShut('');
  } catch (err) {
    if (mine !== Bk.ticket) return;
    if (err.status === 404) return go('book-list', true);
    bookFormShut(BOOK_SHUT.failed);
  }
}

// Saves the boxes. True when it went in; a refusal stays on the form in plain words and nothing typed is lost.
async function bookSave() {
  if (Bk.busy) return false;
  Bk.busy = true;
  $('#bookSave').disabled = true;
  bookSay('', false);
  const said = bookValues().birthday.trim(), birthday = !!said && said !== JSON.parse(Bk.clean || '{}').birthday;
  try {
    const body = JSON.stringify(bookValues());
    const c = Bk.id ? await api(`/api/book/${encodeURIComponent(Bk.id)}`, { method: 'PUT', body })
      : await api('/api/book', { method: 'POST', body });
    if (Bk.mode === 'helper') {
      Bk.helperCount++;
      Bk.id = '';
      bookFill({});
      bookHelperCount();
      $('#bf-name').focus();
      unlit();
      toMary('saved_ok', { form: 'book', birthday });   // piece 6b: no field values, only that it went in
      return true;
    }
    Bk.id = c.id;   // another Save changes this person, and never adds them twice
    bookFill({ ...c, birthday: c.birthday_words });
    bookSay('', true);
    unlit();
    toMary('saved_ok', { form: 'book', birthday });
    return true;
  } catch (err) {
    bookSay(err.message, false);
    toMary('saved_fail', { why: err.code || '' });   // piece 6b: which refusal, and nothing typed
    if (err.code === 'birthday') $('#bf-birthday').focus();
    if (err.code === 'name' || err.code === 'same_name') $('#bf-name').focus();
    return false;
  } finally {
    Bk.busy = false;
    $('#bookSave').disabled = false;
  }
}

// Piece 6b: her page asks only on their own plain "save it". This presses Save the way a tap does, and no tool reaches it.
function bookAskedSave() {
  if (Bk.busy) return;
  if (!bookDirty()) return toMary('save_none', { why: 'nothing' });
  $('#bookForm').requestSubmit();
}

// Piece 6b: the stop under her forget question, or a spoken no: the ask closes back to the list.
function bookKeep() {
  Bk.forget = '';
  $('#bookStopBar').hidden = true;
  go('book-list');
}

/* ---------- What the rest of the page calls ---------- */

function bookInit() {
  bookFill({});
  $('#bookFind').addEventListener('input', () => { Bk.top = 0; bookDrawList(); });
  $('#bookUp').addEventListener('click', () => bookMove(-bookRowsAPage()));
  $('#bookDown').addEventListener('click', () => bookMove(bookRowsAPage()));
  $('#bookEveryone').addEventListener('click', () => bookNarrow(''));
  $('#bookForm').addEventListener('submit', e => { e.preventDefault(); bookSave(); });
  $('#bookForm').addEventListener('input', () => { bookSay('', false); bookWasDraw(); });
  $('#bookAll').addEventListener('click', () => go('book-list'));
  $('#bookDone').addEventListener('click', async () => {   // what's typed is saved first, and a refusal stays on the form
    if (!bookDirty() || await bookSave()) go('book-list');
  });
  $('#bookStop').addEventListener('click', () => {
    bookKeep();
    toMary('book_keep');   // says only that they stopped it
  });
  window.addEventListener('resize', () => { if (cur.screen === 'book-list') bookDrawList(); });
}

// route() in app.js hands the book's hashes here. True when the name was one of them.
function bookRoute(name, arg) {
  if (name !== 'book-card' || arg !== Bk.forget) Bk.forget = '';
  if (name === 'book-list') { cur = { screen: name }; bookShowList(); }
  else if (name === 'book-card') { cur = { screen: name, id: arg }; bookShowCard(arg); }
  else if (name === 'book-form') { cur = { screen: name, id: arg }; bookShowForm(arg, false); }
  else if (name === 'book-helper') { cur = { screen: name }; bookShowForm('', true); }
  else return false;
  showScreen(name);
  return true;
}

// Piece 6 calls these from her page, as MaryScreens reads window.maryHelp. listNow is all look_at_screen gets of the list.
window.maryBook = {
  listNow() {
    if (Bk.state !== 'open') return { state: Bk.state || 'loading' };
    const people = bookMatches(Bk.people, $('#bookFind').value);
    return { state: 'open', count: Bk.count, people: people.map(p => ({ name: p.name, relationship: p.relationship })) };
  },
  narrow: bookNarrow,
  cardNow() { return Bk.card ? { ...Bk.card } : null; },   // piece 6b: whose card, so she knows whose a tapped row opened
  form() { return Bk.form; },                              // piece 6b: changes with each person and each save
  filled(field) { Bk.was.add(field); bookWasDraw(); },     // piece 6b: E1's "was" line; the old value stays on this page
  asking() { return !!Bk.forget; },                        // piece 6b
  keep: bookKeep,                                          // piece 6b
  // E2: the person's card with its one stop button.
  forgetAsk(id) {
    Bk.forget = String(id);
    if (location.hash === `#book-card/${id}`) return bookShowCard(Bk.forget);
    go(`book-card/${id}`);
  },
  // E3: the list at its end, with them out of it. Her caption says so, and never says "gone".
  afterForget() {
    Bk.forget = '';
    Bk.end = true;
    if (location.hash === '#book-list') return bookShowList();
    go('book-list');
  },
};
