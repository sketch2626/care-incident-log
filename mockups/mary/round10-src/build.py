#!/usr/bin/env python3
"""Assembles the round 10 boards (M19, a secure address book) into ../round10/*.dc.html. Stdlib only.

make_boards() builds everything in memory and returns one dict per board, with the rectangles of
every placed box; check.py imports it and measures them. main() writes the files and canvas.json.
The face SVGs are byte-identical copies from round 9; the crop and talking mouth are applied here,
at build time. r6.css and r9.css are unchanged copies; new CSS belongs in ../round10/r10.css, .m10- classes only.
All names, numbers and addresses are made up."""
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, '..', 'round10'))

FONTS = 'https://fonts.googleapis.com/css2?family=Fredoka:wght@600&amp;display=swap'

# ---- the exact layout, as data; check.py measures these ----
W, H = 1280, 800
BAND = {'band': (0, 0, 1280, 156), 'small': (16, 12, 132, 132), 'words': (164, 12, 700, 132), 'back': (884, 28, 368, 96)}
PAGE = (0, 156, 1280, 556)    # the page on deeper screens
ROW = (0, 712, 1280, 88)      # the bottom row, always in view
FACE_BOX = (180, 50, 280, 280)  # viewBox of the small face, her head centered at 320,190 in the 640x400 face
FACE_VIEW = 'viewBox="%d %d %d %d"' % FACE_BOX
MENU_BTN = (1029, 28, 223, 96)
FACE_ZONE = (390, 190, 500, 400)   # the big face on the full page, with her sway
CAP_ZONE = (440, 640, 400, 150)    # the two caption lines at the bottom of the full page
FULL_NOTE = (36, 300, 340)         # x, y, w of the board note on a full-page board, left of her face
LIMIT = {'words': 32, 'full': 13}  # characters a caption line
LEFT, RIGHT, COL = 56, 658, 566    # the two columns of the card and the form

HEAD = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>%(title)s</title>
<script src="./support.js"></script>
<link rel="stylesheet" href="r6.css">
<link rel="stylesheet" href="r9.css">
<link rel="stylesheet" href="r10.css">
</head>
<body>
<x-dc>
<helmet>
<link rel="stylesheet" href="%(fonts)s">
<style>body{margin:0}</style>
</helmet>
<div class="scr %(who)s">
'''
TAIL = '''</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{"$preview":{"width":1280,"height":800}}'>
class Component extends DCLogic {
renderVals() {
return {};
}
}
</script>
</body>
</html>
'''
MENU = ('<button class="menu-btn" type="button"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" '
        'stroke-width="2.6" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"></path></svg>Menu</button>\n')
ARROW = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" '
         'stroke-linejoin="round"><path d="M20 12H4M11 5l-7 7 7 7"></path></svg>')
CHECK = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" '
         'stroke-linejoin="round"><path d="M4 13l5 5L20 6"></path></svg>')
LOCK = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
        'stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2"></rect><path d="M8 11V8a4 4 0 0 1 8 0v3"></path></svg>')
SEARCH = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round">'
          '<circle cx="11" cy="11" r="7"></circle><path d="M16.5 16.5L21 21"></path></svg>')
UP = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" '
      'stroke-linejoin="round"><path d="M5 15l7-7 7 7"></path></svg>')
DOWN = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" '
        'stroke-linejoin="round"><path d="M5 9l7 7 7-7"></path></svg>')

# ---- made-up people; no real names or data ----
PEOPLE = [('Anna Reyes', 'Your niece'), ('Dale Greene', 'Your pastor'), ('Ellen Pruitt', 'Your sister'), ('June Tate', 'Your friend'),
          ('Katie Whitfield', 'Your granddaughter'), ('Mark Hollis', 'Your son'), ('Sarah Beck', 'Friend from church'),
          ('Sarah Whitfield', 'Your daughter'), ('Tom Hollis', 'Your nephew')]
TOWN = 'Anytown, NC 27000'
WHITFIELD = {'Cell phone': '(919) 555-0142', 'Home phone': '(919) 555-0117', 'Email': 'sarah.whitfield@example.com', 'Birthday': 'March 14',
             'Mailing address': ('12 Example Lane,', TOWN), 'Facebook': 'Sarah Whitfield', 'Notes': 'Works nights. Best to call after 4.'}
BECK = {'Cell phone': '(919) 555-0163', 'Email': 'sarah.beck@example.com', 'Birthday': 'July 9',
        'Mailing address': ('40 Sample Street,', TOWN), 'Notes': 'Sits by me at church.'}
MARK = {'Name': 'Mark Hollis', 'Relationship': 'Son', 'Cell phone': '(919) 555-0129', 'Email': 'mark.hollis@example.com',
        'Mailing address': ('7 Demo Road,', TOWN)}
DAUGHTER = {'Name': 'Sarah Whitfield', 'Relationship': 'Daughter'}
WRONG, RIGHT_EMAIL = 'sarah.whitfeld@example.com', 'sarah.whitfield@example.com'  # the slip is deliberate: she hears it wrong and they catch it
STAGES = ('sarah', 'sarah.whitfeld', WRONG)
FILLING = '<span class="m9-fill m10-wide"><span class="m9-v a">%s</span><span class="m9-v b">%s</span><span class="m9-v c">%s</span></span>' % STAGES
LOCK_WORDS = 'Kept only on this laptop, locked.'
LEE = {'Practice': 'Anytown Heart Clinic', 'Office phone': '(919) 555-0171', 'Fax': '(919) 555-0172', 'Patient portal': 'portal.example.com',
       'Office address': ('200 Sample Avenue,', TOWN), 'Specialty': 'Cardiology', 'Notes': 'Dr. Lee sees me for my heart. Checkups in March.'}


def read(*path):
    with open(os.path.join(HERE, *path), encoding='utf-8') as f:
        return f.read()


def esc(s):
    return html.escape(s, quote=False)


def face(who, small=False):
    """Her real face, unchanged but for the crop and the talking mouth."""
    svg = read('face-%s.svg' % who).replace('stroke="#8a3b2e"', 'class="mouth-talk" stroke="#8a3b2e"')
    return svg.replace('viewBox="0 0 640 400"', FACE_VIEW) if small else svg


def caption(lines, cls):
    rows = []
    for line in lines:
        words = ''.join('<span class="w done" data-t="%s">%s</span>' % (html.escape(w), esc(w)) for w in line.split())
        rows.append('<div class="line">%s</div>\n' % words)
    return '<div class="cap capA %s">\n%s</div>\n' % (cls, ''.join(rows))


class Deep:
    """One deeper screen: every box is placed by absolute board coordinates and noted in .rects."""

    def __init__(self):
        self.rects, self.page, self.row, self.fits = [], [], [], []

    def _put(self, into, top, label, x, y, w, h, inner, cls, kind, tag, text, px, em, lines, pad, lit, attrs):
        need = None
        if text is not None:
            need = (label, len(text) * em * px, (w - pad) * lines)
        self.rects.append({'label': label, 'kind': kind, 'tag': tag, 'x': x, 'y': y, 'w': w, 'h': h, 'lit': lit, 'fit': need})
        extra = ' type="button"' if tag == 'button' else ''
        into.append('<%s class="%s"%s%s style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">%s</%s>\n' % (tag, cls, extra, attrs, x, y - top, w, h, inner, tag))

    def put(self, label, x, y, w, h, inner='', cls='', kind='box', tag='div', text=None, px=24, em=.56, lines=1, pad=0, lit=False, attrs=''):
        self._put(self.page, PAGE[1], label, x, y, w, h, inner if inner else esc(text or ''), cls, kind, tag, text, px, em, lines, pad, lit, attrs)

    def inrow(self, label, x, y, w, h, inner='', cls='', kind='box', tag='div', text=None, px=24, em=.56, lines=1, pad=0):
        self._put(self.row, ROW[1], label, x, y, w, h, inner if inner else esc(text or ''), cls, kind, tag, text, px, em, lines, pad, False, '')

    def fit(self, label, text, px, em, room):
        self.fits.append((label, len(text) * em * px, room))

    def note(self, text, x, y, w, lines=1):
        self.put('note', x, y, w, 26 * lines + 18, cls='m9-note', kind='note', text=text, px=20, lines=lines, pad=34)

    def rownote(self, text, w, lines=1):
        """A note in the left of the bottom row. Three lines need the tighter note to fit in the row's 88."""
        if lines == 3:
            self.inrow('note', 24, 714, w, 84, cls='m9-note m10-tight', kind='note', text=text, px=20, lines=3, pad=30)
        else:
            h = 26 * lines + 18
            self.inrow('note', 24, 756 - h // 2, w, h, cls='m9-note', kind='note', text=text, px=20, lines=lines, pad=34)

    def save(self, label, x, w):
        self.inrow(label, x, 720, w, 72, cls='m9-save', kind='target', tag='button', text=label, px=32, em=.58, pad=24)

    def plain(self, label, x, w, icon=''):
        self.inrow(label, x, 720, w, 72, inner=icon + esc(label), cls='m10-plain', kind='target', tag='button', text=label, px=32, em=.58, pad=70 if icon else 24)

    def lock(self):
        self.inrow('lock line', 416, 720, 480, 72, inner=LOCK + '<span>%s</span>' % esc(LOCK_WORDS), cls='m10-lock', kind='text', text=LOCK_WORDS, px=22, pad=42)


def listing(d, people, count, find='', lit=False):
    """The list: heading, plain count, the typed Find box, then big rows that are buttons."""
    d.put('heading', 56, 168, 300, 60, cls='m9-head', kind='text', text='Address book', px=36, em=.58)
    d.put('count', 370, 168, 256, 60, cls='m9-plainline', kind='text', text=count, px=26)
    words = find or 'Find someone'
    d.put('field Find', 640, 164, 308, 68, inner=SEARCH + ('<span>%s</span>' % esc(find) if find else '<span class="m10-ph">%s</span>' % esc(words)),
          cls='m9-field', kind='field', text=words, px=28, pad=114)
    d.put('My doctors', 964, 160, 260, 72, cls='m10-plain', kind='target', tag='button', text='My doctors', px=32, em=.58, pad=24)
    step = 100 if lit else 92
    for i, (name, rel) in enumerate(people):
        y = 244 + step * i
        d.put('row ' + name, LEFT, y, 1168, 84, inner='<span class="m10-nm">%s</span><span class="m10-rel">%s</span>' % (esc(name), esc(rel)),
              cls='m10-row' + (' m9-lit' if lit else ''), kind='target', tag='button', lit=lit)
        d.fit('row name ' + name, name, 32, .58, 620)
        d.fit('row relationship ' + rel, rel, 28, .56, 486)


def list_bottom(d):
    d.plain('Up', 28, 180, UP)
    d.plain('Down', 220, 180, DOWN)
    d.lock()
    d.save('Add someone', 912, 340)


def box(d, label, x, y, value, lab_h, gap, h, lit=False, inner=None, labcls='m10-lab'):
    """One label above one value box. An address is a pair of lines; an empty value is an empty box."""
    d.put('label ' + label, x, y, COL, lab_h, cls=labcls, kind='text', text=label, px=24)
    lines = 1
    if isinstance(value, tuple):
        inner, value = '<span>%s<br>%s</span>' % (esc(value[0]), esc(value[1])), max(value, key=len)
    elif h > 80:
        lines = 2
    d.put('field ' + label, x, y + lab_h + gap, COL, h, inner=inner, cls='m9-field' + (' m9-lit' if lit else ''), kind='field', text=value or '', px=28, lines=lines, pad=58, lit=lit)


CARD = (('Cell phone', 'Home phone', 'Email', 'Birthday'), ('Mailing address', 'Facebook', 'Notes'))
DOCTOR = (('Practice', 'Office phone', 'Fax', 'Patient portal'), ('Office address', 'Specialty', 'Notes'))


def card(d, name, rel, vals, labels=CARD):
    """One person's card: the name, then two columns, label above value, no scrolling."""
    d.put('name', LEFT, 164, 380, 56, cls='m10-name', kind='text', text=name, px=40, em=.58)
    d.put('relationship', 450, 164, 400, 56, cls='m10-relhead', kind='text', text=rel, px=28)
    for i, label in enumerate(labels[0]):
        box(d, label, LEFT, 228 + 116 * i, vals.get(label, ''), 32, 4, 68)
    for label, y, h in zip(labels[1], (228, 402, 540), (104, 68, 104)):
        box(d, label, RIGHT, y, vals.get(label, ''), 32, 4, h)


def form(d, vals, lit=None, inner=None):
    """Add or change someone: the card's grid with Name and Relationship on top, nine fields, y 164-702."""
    inner = inner or {}

    def one(label, x, y, h=64):
        box(d, label, x, y, vals.get(label, ''), 30, 4, h, lit=label == lit, inner=inner.get(label))

    for i, label in enumerate(('Name', 'Cell phone', 'Home phone', 'Email', 'Birthday')):
        one(label, LEFT, 164 + 110 * i)
    one('Relationship', RIGHT, 164)
    one('Mailing address', RIGHT, 274, 98)
    one('Facebook', RIGHT, 439)
    one('Notes', RIGHT, 570, 98)


def form_bottom(d):
    d.plain('All people', 816, 224)
    d.save('Save', 1052, 200)


def helper_bottom(d, note):
    d.rownote(note, 450, 3)
    d.inrow('added today', 484, 720, 196, 72, cls='m9-plainline', kind='text', text='3 added today', px=26)
    d.save('Save and add another', 688, 400)
    d.save('Done', 1100, 152)


def band(who, lines):
    name = who.capitalize()
    return ('<div class="m9-band">\n<div class="m9-small" role="button" tabindex="0" aria-label="Back to %s">\n<div class="m9-ring"></div>\n%s</div>\n%s'
            '<button class="menu-btn m9-back" type="button">%sBack to %s</button>\n</div>\n') % (name, face(who, True), caption(lines, 'm9-words'), ARROW, name)


def deep_html(d, who, lines):
    return band(who, lines) + '<div class="m9-page">\n%s</div>\n<div class="m9-row">\n%s</div>\n' % (''.join(d.page), ''.join(d.row))


def full(who, cap, note):
    """The full page, with a board note left of her face, clear of her and of the caption."""
    x, y, w = FULL_NOTE
    h = 26 * 4 + 18
    rect = {'label': 'note', 'kind': 'note', 'tag': 'div', 'x': x, 'y': y, 'w': w, 'h': h, 'lit': False, 'fit': ('note', len(note) * .56 * 20, (w - 34) * 4)}
    box_html = '<div class="m9-note" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">%s</div>\n' % (x, y, w, h, esc(note))
    return '<div class="edge"></div>\n' + face(who) + MENU + box_html + caption(cap, 'm9-full'), rect


def make_boards():
    out = []

    def add(row, stem, title, who, kind, aloud, lines, body, rects=(), fits=()):
        page = HEAD % {'title': esc(title), 'fonts': FONTS, 'who': who} + body + TAIL
        out.append({'row': row, 'stem': stem, 'title': title, 'who': who, 'kind': kind, 'aloud': aloud, 'lines': lines, 'html': page, 'rects': list(rects), 'fits': list(fits)})

    def deep(row, stem, title, who, aloud, lines, d):
        add(row, stem, title, who, 'deep', aloud, lines, deep_html(d, who, lines), d.rects, d.fits)

    def page(row, stem, title, aloud, lines, note):
        body, rect = full('mary', lines, note)
        add(row, stem, title, 'mary', 'full', aloud, lines, body, [rect])

    r = 'The address book'
    d = Deep()
    listing(d, PEOPLE[:5], '9 people')
    list_bottom(d)
    deep(r, 'A1-List-Mary', '(a1) The list', 'mary', 'Who are you after?', ('Who are you after?',), d)

    d = Deep()
    listing(d, [PEOPLE[7], PEOPLE[6]], '2 of 9 people', 'Sarah', True)
    d.note('They said: "Show me Sarah." One match opens the card straight away.', LEFT, 470, 1168)
    d.plain('Show everyone', 28, 372)
    d.lock()
    d.save('Add someone', 912, 340)
    deep(r, 'A2-Find-Mary', '(a2) Two Sarahs', 'mary', 'Two Sarahs. Your daughter, or Sarah Beck from church?', ('Your daughter, or', 'Sarah Beck from church?'), d)

    d = Deep()
    card(d, 'Sarah Whitfield', 'Your daughter', WHITFIELD)
    d.plain('All people', 28, 280)
    d.plain('Change', 324, 260)
    d.save('Email Sarah', 600, 316)
    d.save('Make a card', 932, 320)
    deep(r, 'B1-Card-Mary', "(b1) One person's card", 'mary', "Here's Sarah.", ("Here's Sarah.",), d)

    r = 'My doctors'
    d = Deep()
    card(d, 'Dr. Helen Lee', 'Heart doctor', LEE, DOCTOR)
    d.rownote('They said: "Show me my heart doctor." The portal\'s web address is kept here. Its password never is, and Mary won\'t read or fill one.', 744, 3)
    d.plain('All doctors', 780, 260)
    d.plain('Change', 1052, 200)
    deep(r, 'H1-Doctor-Mary', "(h1) A doctor's card", 'mary', "Here's Dr. Lee.", ("Here's Dr. Lee.",), d)

    r = 'Adding someone by voice'
    d = Deep()
    form(d, dict(DAUGHTER, Email=WRONG), 'Email', {'Email': FILLING})
    d.fits += [('stage ' + s, len(s) * .56 * 28, 500) for s in STAGES]
    d.rownote('They said: "My daughter Sarah Whitfield, her email is..."', 776)
    form_bottom(d)
    deep(r, 'C1-AddFill-Mary', '(c1) She fills it in as they talk, moving', 'mary', 'Sarah Whitfield, your daughter.', ('Sarah Whitfield,', 'your daughter.'), d)

    d = Deep()
    form(d, dict(DAUGHTER, Email=WRONG), 'Email')
    form_bottom(d)
    deep(r, 'C2-AddSpell-Mary', '(c2) She spells it back', 'mary', 'S, A, R, A, H, dot, W, H, I, T, F, E, L, D, at example dot com. Is that right?', (WRONG, 'Is that right?'), d)

    def fixed(who):
        d = Deep()
        form(d, dict(DAUGHTER, Email=RIGHT_EMAIL), 'Email')
        d.rownote('They said: "No, W-H-I-T-F-I-E-L-D."', 776)
        form_bottom(d)
        return d

    fix_aloud = 'W, H, I, T, F, I, E, L, D. At example dot com. Is that right?'
    fix_lines = (RIGHT_EMAIL, 'Is that right?')
    deep(r, 'C3-AddFix-Mary', '(c3) They catch a mistake', 'mary', fix_aloud, fix_lines, fixed('mary'))

    d = Deep()
    form(d, dict(DAUGHTER, Email=RIGHT_EMAIL, Birthday='March 14'))
    d.rownote('She never saves by herself. A tap on Save, or their plain "save it", does that.', 580, 2)
    d.inrow('Saved', 618, 724, 186, 64, inner=CHECK + 'Saved', cls='m9-saved', kind='text', text='Saved', px=32, em=.58, pad=58)
    form_bottom(d)
    deep(r, 'C4-AddSaved-Mary', '(c4) Saved, on their word', 'mary', "Saved. I'll mention her birthday when it's close.", ("Saved. I'll mention her", "birthday when it's close."), d)
    deep(r, 'S1-AddSpell-Sam', '(s1) Sam works the same', 'sam', fix_aloud, fix_lines, fixed('sam'))

    r = 'Using it'
    page(r, 'D1-Email-Mary', '(d1) "Email my daughter"', 'To Sarah. What do you want to say?', ('What do you', 'want to say?'),
         'They said: "Email my daughter." She found Sarah. Nobody said the address.')

    d = Deep()
    d.put('label To', LEFT, 172, 76, 104, cls='m9-lab', kind='text', text='To', px=26)
    who_line = 'Sarah Whitfield, your daughter'
    d.put('field To', 140, 172, 1084, 104, inner='<span><span class="m10-strong">%s</span><br>%s</span>' % (esc(who_line), esc(RIGHT_EMAIL)), cls='m9-field', kind='field', text=who_line, px=28, em=.6, pad=58)
    d.put('label Message', LEFT, 292, 1168, 40, cls='m9-lab', kind='text', text='Message', px=26)
    d.put('field Message', LEFT, 336, 1168, 200, inner="<span>I'll be thinking of you at the recital.<br><br>Mom</span>", cls='m9-field big', kind='field',
          text="I'll be thinking of you at the recital.", px=30, pad=54)
    d.note("The same send step as today. The address shows here for their eyes; she doesn't say it.", LEFT, 556, 1168)
    d.plain('Not yet', 696, 240)
    d.save('Send', 952, 300)
    deep(r, 'D2-Look-Mary', '(d2) The look before it goes', 'mary', "When you say send, it goes to Sarah's email. You'll have five seconds to stop it.", ('When you say send, it goes', "to Sarah's email."), d)

    page(r, 'D3-Card-Mary', '(d3) "Make Sarah a birthday card"', "March 14 is Sarah's birthday. Pick a front you like.", ('Pick a front', 'you like.'),
         'They said: "Make Sarah a birthday card." She knew who and when.')

    r = 'A new address on a first send: two ways'
    page(r, 'G1-KeepAsk-Mary', '(g1) Ask once (the pick)', "Sent to Tom. Keep Tom's address for next time?", ("Keep Tom's", 'address?'),
         'Option A, the pick. She asks once per person. Then "Email Tom" just works.')
    page(r, 'G2-KeptSay-Mary', '(g2) Keep it and say so', "Sent to Tom. His address is in your book now. Say so if you'd rather I didn't keep it.", ("It's in your", 'book now.'),
         'Option B. No question, but she keeps it without being told to.')

    r = 'Changing and removing'
    new_cell, was = '(919) 555-0188', 'Was (919) 555-0142'
    d = Deep()
    form(d, dict(DAUGHTER, **dict(WHITFIELD, **{'Cell phone': new_cell})), 'Cell phone', {'Cell phone': '<span>%s</span><span class="m10-was">%s</span>' % (new_cell, was)})
    d.fits.append(('was line', len(new_cell) * .56 * 28 + len(was) * .56 * 22, COL - 58))
    d.rownote('They said: "Sarah\'s new number is 919-555-0188." With no cell on file, or two numbers, she asks which.', 490, 3)
    d.plain('Forget Sarah', 528, 260)
    d.plain('Put it back', 800, 240)
    d.save('Save', 1052, 200)
    deep(r, 'E1-Change-Mary', '(e1) A new number', 'mary', 'Her cell, 919-555-0188. Is that right?', ('Her cell, 919-555-0188.', 'Is that right?'), d)

    d = Deep()
    card(d, 'Sarah Beck', 'Friend from church', BECK)
    d.rownote('They said: "Forget Sarah Beck." Just "Forget Sarah" would first ask which one.', 610, 2)
    d.plain('Yes, forget her', 646, 310)
    d.save('No, keep her', 972, 280)
    deep(r, 'E2-ForgetAsk-Mary', '(e2) She asks once', 'mary', 'Forget Sarah Beck? Her address, her birthday reminders and what I remember about her all go for good.',
         ('Forget Sarah Beck?', 'All of it goes for good.'), d)

    d = Deep()
    listing(d, [PEOPLE[4], PEOPLE[5], PEOPLE[7], PEOPLE[8]], '8 people')
    list_bottom(d)
    deep(r, 'E3-Forgotten-Mary', '(e3) Really removed', 'mary', 'Done. Sarah Beck is out of your address book.', ('Done. Sarah Beck is out', 'of your address book.'), d)

    r = 'A helper adding several people'
    d = Deep()
    form(d, MARK)
    helper_bottom(d, 'Typed words stay on the laptop. Mary sees them only if someone asks her about them.')
    deep(r, 'F1-Helper-Mary', '(f1) A helper types', 'mary', "That's three in. Ask if you need me.", ("That's three in.", 'Ask if you need me.'), d)

    d = Deep()
    form(d, dict(MARK, Birthday='June 3'), 'Birthday')
    helper_bottom(d, 'The helper types. Ruth said: "His birthday is June 3." Mary filled that one.')
    deep(r, 'F2-HelperVoice-Mary', '(f2) The resident pitches in', 'mary', 'June 3. Is that right?', ('June 3.', 'Is that right?'), d)

    # Notes
    secs = [("Where it's kept", 'On this laptop only, locked, apart from the care log. Never in a report.'),
            ('What Mary sees', 'Names and relationships. An address or number only when your task needs it, or you ask her to read it.'),
            ('What forget does', 'Takes the person out for real: address, birthday reminders and what she remembers.')]
    body = '<div class="edge"></div>\n<div class="m9-notes">\n' + ''.join(
        '<section class="m9-sec" style="top:%dpx"><h2>%s</h2><p>%s</p></section>\n' % (80 + 232 * i, esc(h), esc(p)) for i, (h, p) in enumerate(secs)) + '</div>\n'
    add('Notes', 'N-Notes', '(n) Notes', 'mary', 'notes', '', (), body)
    return out


CANVAS_TITLE = 'Mary round 10: a secure address book'


def write_canvas(boards):
    canvas = {'v': 3, 'createdOnFiles': {'v': 1, 'at': '2026-11-01T12:00:00Z'}, 'title': CANVAS_TITLE, 'launch': {'view': 'canvas'},
              'pages': [], 'boards': {}, 'order': [], 'notes': {}, 'designSystems': []}
    rows = []
    for b in boards:
        if b['row'] not in rows:
            rows.append(b['row'])
    for r, heading in enumerate(rows):
        y = r * 1220
        canvas['notes']['t%d' % r] = {'x': 0, 'y': y - 300, 'text': heading, 'kind': 'title1', 'maxW': 2640}
        for c, b in enumerate(x for x in boards if x['row'] == heading):
            file = b['stem'] + '.dc.html'
            canvas['boards'][file] = {'x': c * 1360, 'y': y, 'w': 1280, 'h': 800, 'title': b['title']}
            canvas['order'].append(file)
    with open(os.path.join(OUT, 'canvas.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(canvas, f, ensure_ascii=False, indent=0)
        f.write('\n')


def main():
    boards = make_boards()
    for b in boards:
        with open(os.path.join(OUT, b['stem'] + '.dc.html'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(b['html'])
    write_canvas(boards)
    print('built %d boards' % len(boards))


if __name__ == '__main__':
    main()
