#!/usr/bin/env python3
"""Assembles the round 9 boards (M18, she comes along) into ../round9/*.dc.html. Stdlib only.

make_boards() builds everything in memory and returns one dict per board, with the rectangles of
every placed box; check.py imports it and measures them. main() writes the files and canvas.json.
The face SVGs are byte-identical copies from round 8; the crop and talking mouth are applied here,
at build time. New CSS belongs in ../round9/r9.css, .m9- classes only."""
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, '..', 'round9'))

FONTS = 'https://fonts.googleapis.com/css2?family=Fredoka:wght@600&amp;display=swap'

# ---- the exact layout, as data; check.py measures these ----
W, H = 1280, 800
BAND = {'band': (0, 0, 1280, 156), 'small': (16, 12, 132, 132), 'words': (164, 12, 700, 132), 'back': (884, 28, 368, 96)}
PAGE = (0, 156, 1280, 556)    # the scrolling page on form screens
ROW = (0, 712, 1280, 88)      # the bottom row, a proposal
FACE_BOX = (180, 50, 280, 280)  # viewBox of the small face, her head centered at 320,190 in the 640x400 face
FACE_VIEW = 'viewBox="%d %d %d %d"' % FACE_BOX
MENU_BTN = (1029, 28, 223, 96)
MENU_ITEMS = [(692 + 20, 166 + 98 * i + (6 if i == 5 else 0), 520, 88) for i in range(6)]  # r6.css .menu and .mi
LIMIT = {'words': 32, 'full': 13}  # characters a caption line

HEAD = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>%(title)s</title>
<script src="./support.js"></script>
<link rel="stylesheet" href="r6.css">
<link rel="stylesheet" href="r9.css">
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
MENU_OPEN = ('<button class="menu-btn open" type="button" aria-expanded="true"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" '
             'stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 15l6-6 6 6"></path></svg>Hide menu</button>\n')
ARROW = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" '
         'stroke-linejoin="round"><path d="M20 12H4M11 5l-7 7 7 7"></path></svg>')
CHECK = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" '
         'stroke-linejoin="round"><path d="M4 13l5 5L20 6"></path></svg>')
LOCK = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
        'stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2"></rect><path d="M8 11V8a4 4 0 0 1 8 0v3"></path></svg>')

# the menu items, icons copied from web/mary.html lines 24-29
ITEMS = [
    ('mi talk', 'Stop talking', '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3"></rect><path d="M5 11a7 7 0 0 0 14 0M12 18v3"></path></svg>'),
    ('mi', 'Things Mary can do', '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 3l1.9 5.1L18 10l-5.1 1.9L11 17l-1.9-5.1L4 10l5.1-1.9z"></path><path d="M18.5 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"></path></svg>'),
    ('mi', 'My info', '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="8" r="4"></circle><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"></path></svg>'),
    ('mi', 'Choose Mary or Sam', '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="7" cy="12" r="5"></circle><rect x="12.5" y="7" width="10" height="10" rx="3"></rect><path d="M5.3 11.2h.01M8.7 11.2h.01M15.6 11.2h.01M19.4 11.2h.01" stroke-width="2.4"></path></svg>'),
    ('mi', 'Games', '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><rect x="4" y="4" width="16" height="16" rx="4"></rect><path d="M9 9h.01M15 9h.01M12 12h.01M9 15h.01M15 15h.01" stroke-width="3"></path></svg>'),
    ('mi quit', 'Close Mary', '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 3v8"></path><path d="M6.3 6.8a8 8 0 1 0 11.4 0"></path></svg>'),
]

# made-up resident
FIELDS = [('Your name', 'Ruth Hollis'), ('Your room number', '108'), ('Name of the care home', 'Pine Hollow Care Center'),
          ('Address of the care home', '100 Example Road'), ('State', 'NC')]
THEIR_WORDS = 'I pressed my call light at seven and no one came for more than two hours.'
PROPOSAL = 'Proposal: this bottom row stays in view.'


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
        self.rects, self.page, self.row = [], [], []

    def _put(self, into, top, label, x, y, w, h, inner, cls, kind, tag, text, px, em, lines, pad, lit, attrs):
        need = None
        if text is not None:
            need = (label, len(text) * em * px, (w - pad) * lines)
        self.rects.append({'label': label, 'kind': kind, 'x': x, 'y': y, 'w': w, 'h': h, 'lit': lit, 'fit': need})
        extra = ' type="button"' if tag == 'button' else ''
        into.append('<%s class="%s"%s%s style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">%s</%s>\n' % (tag, cls, extra, attrs, x, y - top, w, h, inner, tag))

    def put(self, label, x, y, w, h, inner='', cls='', kind='box', tag='div', text=None, px=24, em=.56, lines=1, pad=0, lit=False, attrs=''):
        self._put(self.page, PAGE[1], label, x, y, w, h, inner if inner else esc(text or ''), cls, kind, tag, text, px, em, lines, pad, lit, attrs)

    def inrow(self, label, x, y, w, h, inner='', cls='', kind='box', tag='div', text=None, px=24, em=.56, lines=1, pad=0):
        self._put(self.row, ROW[1], label, x, y, w, h, inner if inner else esc(text or ''), cls, kind, tag, text, px, em, lines, pad, False, '')

    def heading(self, text):
        self.put('heading', 56, 168, 350, 60, cls='m9-head', kind='text', text=text, px=36, em=.58)

    def note(self, text, x=420, y=172, w=804, h=48, lines=1):
        self.put('note', x, y, w, h, cls='m9-note', kind='note', text=text, px=20, lines=lines, pad=34)

    def proposal(self):
        self.inrow('proposal note', 24, 734, 500, 44, cls='m9-note', kind='note', text=PROPOSAL, px=20, pad=34)

    def save(self):
        self.inrow('Save', 952, 720, 300, 72, cls='m9-save', kind='target', tag='button', text='Save', px=32, em=.58, pad=24)


def myinfo(d, room=None, lit=False):
    """The My info page: label beside field, five rows, all in view at once."""
    d.heading('My info')
    for i, (label, value) in enumerate(FIELDS):
        y = 240 + 90 * i
        d.put('label ' + label, 56, y, 356, 72, cls='m9-lab', kind='text', text=label, px=26)
        here = i == 1
        d.put('field ' + label, 420, y, 804, 72, inner=(room if here and room else esc(value)), cls='m9-field' + (' m9-lit' if here and lit else ''),
              kind='field', text=value, px=28, pad=58, lit=here and lit)


FILLING = '<span class="m9-fill"><span class="m9-v a">2</span><span class="m9-v b">21</span><span class="m9-v c">214</span></span>'


def incident(d, lit):
    """The incident form: their words left, the two questions right. lit is 'wait' or 'bad'."""
    d.put('heading', 32, 168, 556, 56, cls='m9-head', kind='text', text='1. What happened', px=36, em=.58)
    d.put('label Your words', 32, 232, 556, 36, cls='m9-lab', kind='text', text='Your words', px=26)
    d.put('field Your words', 32, 272, 556, 300, cls='m9-field big', kind='field', text=THEIR_WORDS, px=30, lines=4, pad=54)
    wait, bad = lit == 'wait', lit == 'bad'
    d.put('group wait', 620, 162, 628, 196, cls='m9-group' + (' m9-lit' if wait else ''), kind='group', lit=wait)
    d.put('legend wait', 638, 170, 592, 40, cls='m9-legend', kind='text', text='How long did you wait?', px=28, em=.58)
    for i, label in enumerate(('15 min', '30 min', '1 hour', '2+ hours')):
        on = wait and label == '2+ hours'
        d.put(label, 634 + 153 * i, 214, 141, 64, cls='m9-opt' + (' on' if on else ''), kind='target', tag='button', text=label, px=24, em=.58, pad=22,
              attrs=' aria-pressed="%s"' % ('true' if on else 'false'))
    d.put('No one ever came', 634, 286, 600, 64, cls='m9-opt', kind='target', tag='button', text='No one ever came', px=24, em=.58, pad=22, attrs=' aria-pressed="false"')
    d.put('group bad', 620, 372, 628, 296, cls='m9-group' + (' m9-lit' if bad else ''), kind='group', lit=bad)
    d.put('legend bad', 638, 380, 592, 40, cls='m9-legend', kind='text', text='How bad was it?', px=28, em=.58)
    for i, (word, hint) in enumerate((('Minor', ''), ('Serious', 'It hurt me or really upset me.'), ('Dangerous', 'I could have been badly hurt.'))):
        inner = '<span class="m9-word">%s</span>' % word + ('<span class="m9-hint">%s</span>' % esc(hint) if hint else '')
        # the word sits in a fixed 150 column and the hint follows, so the fit is measured on the hint's room
        d.put(word, 634, 424 + 80 * i, 600, 72, inner=inner, cls='m9-opt hinted', kind='target', tag='button', text=hint or word, px=22 if hint else 26, pad=46 + 166 if hint else 46,
              attrs=' aria-pressed="false"')


def band(who, lines, cls=''):
    name = who.capitalize()
    return ('<div class="m9-band%s">\n<div class="m9-small" role="button" tabindex="0" aria-label="Back to %s">\n<div class="m9-ring"></div>\n%s</div>\n%s'
            '<button class="menu-btn m9-back" type="button">%sBack to %s</button>\n</div>\n') % (cls, name, face(who, True) if not cls else '', caption(lines, 'm9-words'), ARROW, name)


def deep_html(d, who, lines):
    return band(who, lines) + '<div class="m9-page">\n%s</div>\n<div class="m9-row">\n%s</div>\n' % (''.join(d.page), ''.join(d.row))


def full(who, cap, menu=MENU, extra='', left=False):
    return '<div class="edge"></div>\n' + face(who) + extra + menu + caption(cap, 'm9-full left' if left else 'm9-full')


def menu_html():
    rows = ''.join('<button class="%s" type="button" role="menuitem">%s%s</button>\n' % (cls, svg, esc(label)) for cls, label, svg in ITEMS)
    return '<div class="menu" role="menu">\n%s</div>\n' % rows


def fill_board(who):
    d = Deep()
    myinfo(d, FILLING, True)
    d.note('They said: "Put my room number as 214."')
    d.save()
    d.proposal()
    return d


def make_boards():
    out = []

    def add(stem, title, who, kind, aloud, lines, body, rects=(), fits=()):
        page = HEAD % {'title': title, 'fonts': FONTS, 'who': who} + body + TAIL
        out.append({'stem': stem, 'title': title, 'who': who, 'kind': kind, 'aloud': aloud, 'lines': lines, 'html': page, 'rects': list(rects)})

    def deep(stem, title, who, aloud, lines, d):
        add(stem, title, who, 'deep', aloud, lines, deep_html(d, who, lines), d.rects)

    # Mary comes along
    add('A1-Full-Mary', 'Mary, full page', 'mary', 'full', "That's in My info. Open the Menu and I'll come along.", ('That\'s in', 'My info.'), full('mary', ("That's in", 'My info.')))
    add('A2-Menu-Mary', 'Mary, Menu open', 'mary', 'full', 'Tap My info.', ('Tap My info.',), full('mary', ('Tap My info.',), MENU_OPEN, menu_html(), True))
    d = Deep()
    myinfo(d)
    d.save()
    d.proposal()
    deep('A3-MyInfo-Mary', 'My info, Mary comes along', 'mary', 'Here it is. Tell me what to change, or ask about anything on here.',
         ('Tell me what to change,', 'or ask about anything here.'), d)

    # She fills it in, you say when
    deep('B1-Fill-Mary', 'She fills in the room number', 'mary', 'Room 214. Is that right?', ('Room 214.', 'Is that right?'), fill_board('mary'))
    d = Deep()
    myinfo(d, '214')
    d.note('She never saves or sends by herself. A tap on Save, or their plain "save it", does that.', y=162, h=74, lines=2)
    d.save()
    d.proposal()
    d.inrow('Saved', 700, 724, 232, 64, inner=CHECK + 'Saved', cls='m9-saved', kind='text', text='Saved', px=32, em=.58, pad=58)
    deep('B2-Saved-Mary', 'Saved', 'mary', 'Saved.', ('Saved.',), d)
    deep('S1-Fill-Sam', 'Sam fills in the room number', 'sam', 'Room 214. Is that right?', ('Room 214.', 'Is that right?'), fill_board('sam'))

    # On an incident form
    d = Deep()
    incident(d, 'bad')
    d.note('They asked what the words mean. She explains. The choice stays theirs.', x=32, y=588, w=556, h=110, lines=2)
    d.save()
    d.proposal()
    deep('C1-Explain-Mary', 'Incident form, she explains', 'mary',
         "That one's your call. Serious means it hurt you or really upset you. Dangerous means you could have been badly hurt.",
         ('Serious means it hurt you', 'or really upset you.'), d)
    d = Deep()
    incident(d, 'wait')
    d.note('Their words stay their own. She fills answers from what they said and never rewrites them.', x=32, y=588, w=556, h=110, lines=3)
    d.save()
    d.proposal()
    deep('C2-FillForm-Mary', 'Incident form, she fills it in', 'mary', 'More than two hours. Is that right?', ('More than two hours.', 'Is that right?'), d)

    # Secrets
    d = Deep()
    d.heading('Connect email')
    d.note('Same for the Gemini key.')
    d.put('label Email address', 56, 240, 356, 72, cls='m9-lab', kind='text', text='Email address', px=26)
    d.put('field Email address', 420, 240, 804, 72, cls='m9-field', kind='field', text='ruth.hollis@example.com', px=28, pad=58)
    d.put('label Email service', 56, 330, 356, 72, cls='m9-lab', kind='text', text='Email service', px=26)
    d.put('Gmail', 420, 330, 248, 72, cls='m9-opt on', kind='target', tag='button', text='Gmail', px=24, em=.58, pad=22, attrs=' aria-pressed="true"')
    d.put('label App password', 56, 420, 356, 72, cls='m9-lab', kind='text', text='App password', px=26)
    d.put('field App password', 420, 420, 540, 72, inner=LOCK, cls='m9-field', kind='field')
    d.put('Paste', 976, 420, 248, 72, cls='m9-paste', kind='target', tag='button', text='Paste', px=28, em=.58, pad=24)
    d.put('line under the box', 420, 500, 804, 44, cls='m9-plainline', kind='text', text="Mary can't see this box.", px=26)
    d.inrow('Connect email', 872, 720, 380, 72, cls='m9-save', kind='target', tag='button', text='Connect email', px=32, em=.58, pad=24)
    d.proposal()
    deep('D1-Secret-Mary', 'Connect email, she keeps out', 'mary', "I won't read or fill that one. It's a password, so it stays out of my hands. A helper can type it in.",
         ("I won't read or fill that one.", 'A helper can type it in.'), d)

    # Back to her. E1 starts as the My info page; the page, band and row fade, and her face, outside them, grows.
    aloud = "That's done. Now, the coast. Go on."
    d = Deep()
    myinfo(d, '214')
    d.save()
    gone = ('<div class="edge"></div>\n<div class="m9-gone">\n' + '<div class="m9-page">\n%s</div>\n<div class="m9-row">\n%s</div>\n' % (''.join(d.page), ''.join(d.row))
            + band('mary', ("That's done.",), ' clear') + '</div>\n<div class="m9-grow">\n' + face('mary') + '</div>\n' + caption(('Now, the', 'coast. Go on.'), 'm9-full m9-capin'))
    add('E1-Grow-Mary', 'She grows back', 'mary', 'deep', aloud, ("That's done.", 'Now, the', 'coast. Go on.'), gone, d.rects)
    add('E2-Back-Mary', 'Back to her, still talking', 'mary', 'full', aloud, ('Now, the', 'coast. Go on.'), full('mary', ('Now, the', 'coast. Go on.')))

    # Notes
    secs = [('Where her words sit', 'Beside her in the top band, never over the page.'),
            ('How big she is', '132 by 132 on a 1280-wide screen, about a tenth of the width. Big enough to see her moods and tap.'),
            ('Nothing is covered', 'The page starts under the band. When she fills a field she scrolls it into view, under the band.')]
    body = '<div class="edge"></div>\n<div class="m9-notes">\n' + ''.join(
        '<section class="m9-sec" style="top:%dpx"><h2>%s</h2><p>%s</p></section>\n' % (80 + 232 * i, esc(h), esc(p)) for i, (h, p) in enumerate(secs)) + '</div>\n'
    add('N-Notes', 'Notes', 'mary', 'notes', '', (), body)
    return out


# file, board title on the canvas; one row per stretch of the journey, each under a title note
ROWS = [
    ('Mary comes along', [
        ('A1-Full-Mary.dc.html', '(a1) Full page, mid-talk'),
        ('A2-Menu-Mary.dc.html', '(a2) Menu open'),
        ('A3-MyInfo-Mary.dc.html', '(a3) My info, she comes along')]),
    ('She fills it in, you say when', [
        ('B1-Fill-Mary.dc.html', '(b1) She fills in the room, moving'),
        ('B2-Saved-Mary.dc.html', '(b2) Saved'),
        ('S1-Fill-Sam.dc.html', '(s1) Sam works the same, moving')]),
    ('On an incident form', [
        ('C1-Explain-Mary.dc.html', '(c1) She explains a choice'),
        ('C2-FillForm-Mary.dc.html', '(c2) She fills from their words')]),
    ('Secrets', [
        ('D1-Secret-Mary.dc.html', '(d1) She keeps out of the password')]),
    ('Back to her', [
        ('E1-Grow-Mary.dc.html', '(e1) She grows back, moving'),
        ('E2-Back-Mary.dc.html', '(e2) Full page, talk still going')]),
    ('Notes', [
        ('N-Notes.dc.html', '(n) Notes')]),
]


def write_canvas():
    canvas = {'v': 3, 'createdOnFiles': {'v': 1, 'at': '2026-11-01T12:00:00Z'}, 'title': 'Mary round 9: she comes along', 'launch': {'view': 'canvas'},
              'pages': [], 'boards': {}, 'order': [], 'notes': {}, 'designSystems': []}
    for r, (heading, boards) in enumerate(ROWS):
        y = r * 1220
        canvas['notes']['t%d' % r] = {'x': 0, 'y': y - 300, 'text': heading, 'kind': 'title1', 'maxW': 2640}
        for c, (file, name) in enumerate(boards):
            canvas['boards'][file] = {'x': c * 1360, 'y': y, 'w': 1280, 'h': 800, 'title': name}
            canvas['order'].append(file)
    with open(os.path.join(OUT, 'canvas.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(canvas, f, ensure_ascii=False, indent=0)
        f.write('\n')


def main():
    boards = make_boards()
    for b in boards:
        with open(os.path.join(OUT, b['stem'] + '.dc.html'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(b['html'])
    write_canvas()
    print('built %d boards' % len(boards))


if __name__ == '__main__':
    main()
