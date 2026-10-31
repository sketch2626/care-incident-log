#!/usr/bin/env python3
"""Assembles the round 8 boards into ../round8/*.dc.html from one shared shell, so art
changes flow to every board. Stdlib only. Run paint.py first if a scene changed.

To add a board, call board(file, title, who, body, caption_lines). The face SVGs in
face-*.svg are byte-identical copies from the original boards; leave them alone.
New CSS belongs in ../round8/r8.css in the .c8- section."""
import html
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, '..', 'round8'))

FONTS = ('https://fonts.googleapis.com/css2?family=Baloo+2:wght@700&amp;family=Fredoka:wght@600&amp;family=Nunito:wght@900'
         '&amp;family=Pinyon+Script&amp;family=Cinzel:wght@500;700&amp;family=EB+Garamond:ital,wght@0,400;0,500;0,700;1,400'
         '&amp;family=Cedarville+Cursive&amp;family=Kalam&amp;display=swap')
SCRIPT = "'Pinyon Script','Edwardian Script ITC','Segoe Script',cursive"
CAPS = "'Cinzel','Trajan Pro','Times New Roman',serif"

HEAD = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>%(title)s</title>
<script src="./support.js"></script>
<link rel="stylesheet" href="r6.css">
<link rel="stylesheet" href="r8.css">
</head>
<body>
<x-dc>
<helmet>
<link rel="stylesheet" href="%(fonts)s">
<style>body{margin:0}</style>
</helmet>
<div class="scr %(who)s">
<div class="edge"></div>
<div class="m8-fit"><div class="m8-aside">
'''
MENU = ('</div></div>\n<button class="menu-btn" type="button"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" '
        'stroke-width="2.6" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"></path></svg>Menu</button>\n')
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


def read(*path):
    with open(os.path.join(HERE, *path), encoding='utf-8') as f:
        return f.read()


def caption(lines):
    rows = []
    for line in lines:
        words = ''.join('<span class="w done" data-t="%s">%s</span>' % (html.escape(w), html.escape(w, quote=False)) for w in line.split())
        rows.append('<div class="line">%s</div>\n' % words)
    return '<div class="cap capA m8-cap">\n%s</div>\n' % ''.join(rows)


def board(file, title, who='mary', body='', caption_lines=()):
    """Writes one board: the shared shell, the face, the Menu button, the body, the caption."""
    page = (HEAD % {'title': title, 'fonts': FONTS, 'who': who} + read('face-%s.svg' % who) + MENU + body.rstrip('\n') + '\n'
            + caption(caption_lines) + TAIL)
    with open(os.path.join(OUT, file), 'w', encoding='utf-8', newline='\n') as f:
        f.write(page)


def art(name):
    """One card front, ready to sit inside any sized box."""
    return read('art', name + '.svg').strip()


# ---- shared pieces ---------------------------------------------------------------------

def gradient(id_, stops, x1=0, y1=0, x2=1, y2=1, user=False):
    u = ' gradientUnits="userSpaceOnUse"' if user else ''
    s = ''.join('<stop offset="%s" stop-color="%s"></stop>' % st for st in stops)
    return '<linearGradient id="%s" x1="%s" y1="%s" x2="%s" y2="%s"%s>%s</linearGradient>' % (id_, x1, y1, x2, y2, u, s)


def sheet(id_, w, h, light='#f8f1e2', deep='#ece0c8', seed=3, tooth=.3):
    """Heavy cream stock: a soft tone across the sheet with its lit grain over it."""
    return ('<svg class="c8-sheet" viewBox="0 0 %d %d" preserveAspectRatio="none" aria-hidden="true"><defs>'
            '<radialGradient id="%s-g" cx=".42" cy=".36" r=".9"><stop offset="0" stop-color="%s"></stop><stop offset="1" stop-color="%s"></stop></radialGradient>'
            '<filter id="%s-f" filterUnits="userSpaceOnUse" x="0" y="0" width="%d" height="%d" color-interpolation-filters="sRGB">'
            '<feTurbulence type="fractalNoise" baseFrequency="1.05" numOctaves="3" seed="%d" result="t"></feTurbulence>'
            '<feDiffuseLighting in="t" surfaceScale="%s" diffuseConstant="1.155" lighting-color="#ffffff" result="l"><feDistantLight azimuth="225" elevation="60"></feDistantLight></feDiffuseLighting>'
            '<feBlend in="SourceGraphic" in2="l" mode="multiply"></feBlend></filter></defs>'
            '<rect width="%d" height="%d" fill="url(#%s-g)" filter="url(#%s-f)"></rect></svg>'
            % (w, h, id_, light, deep, id_, w, h, seed, tooth, w, h, id_, id_))


GILT = [(0, '#6e4e10'), (.18, '#b08a34'), (.34, '#f2dd98'), (.5, '#94701f'), (.68, '#e4c878'), (.84, '#9e7a26'), (1, '#6a4a0e')]
BRASS = [(0, '#55451a'), (.2, '#967a38'), (.36, '#dcc88a'), (.52, '#7e662a'), (.7, '#ccb577'), (.86, '#8a7032'), (1, '#4f4018')]
SPRIG = ('<path d="M0 0C-8 -7 -20 -8 -33 0C-20 8 -8 7 0 0Z"></path><path d="M0 0C8 -7 20 -8 33 0C20 8 8 7 0 0Z"></path>'
         '<path d="M0 -8C-4 -3 -4 3 0 8C4 3 4 -3 0 -8Z"></path><path d="M-33 0H-92M33 0H92" stroke-width="1.2" stroke="url(#%s)"></path>')


def pine_sprig(foil):
    """Sam's ornament: a short pine bough with its needles."""
    needles = ''
    for i in range(14):
        x = -40 + i * 6.2
        reach = 13 - abs(i - 6.5) * 1.1
        needles += 'M%.1f 0L%.1f %.1fM%.1f 0L%.1f %.1f' % (x, x + 6, -reach, x, x + 6, reach)
    return ('<path d="%s" fill="none" stroke="url(#%s)" stroke-width="1.5" stroke-linecap="round"></path>'
            '<path d="M-48 0H48" fill="none" stroke="url(#%s)" stroke-width="2.2" stroke-linecap="round"></path>'
            '<path d="M-48 0H-98M48 0H98" fill="none" stroke="url(#%s)" stroke-width="1.2"></path>' % (needles, foil, foil, foil))


def rules(who, w=724, h=616):
    foil = 'c8k-foil'
    stops = GILT if who == 'mary' else BRASS
    x0, y0, x1, y1 = 23, 23, w - 23, h - 23
    if who == 'mary':
        q = 16  # scooped corners
        inner = ('M%d %dH%dA%d %d 0 0 0 %d %dV%dA%d %d 0 0 0 %d %dH%dA%d %d 0 0 0 %d %dV%dA%d %d 0 0 0 %d %dZ'
                 % (x0 + q, y0, x1 - q, q, q, x1, y0 + q, y1 - q, q, q, x1 - q, y1, x0 + q, q, q, x0, y1 - q, y0 + q, q, q, x0 + q, y0))
    else:
        q = 15  # square notched corners, a touch more ledger than album
        inner = ('M%d %dH%dV%dH%dV%dH%dV%dH%dV%dH%dV%dH%dZ'
                 % (x0 + q, y0, x1 - q, y0 + q, x1, y1 - q, x1 - q, y1, x0 + q, y1 - q, x0, y0 + q, x0 + q))
    orn = ('<g transform="translate(%d 384)" fill="url(#%s)">%s</g>' % (w // 2, foil, SPRIG % foil)) if who == 'mary' else (
        '<g transform="translate(%d 384)">%s</g>' % (w // 2, pine_sprig(foil)))
    return ('<svg class="c8-rules" viewBox="0 0 %d %d" aria-hidden="true"><defs>%s</defs>'
            '<rect x="1.2" y="1.2" width="%s" height="%s" fill="none" stroke="url(#%s)" stroke-width="2.4"></rect>'
            '<rect x="13" y="13" width="%d" height="%d" fill="none" stroke="url(#%s)" stroke-width="3.2"></rect>'
            '<path d="%s" fill="none" stroke="url(#%s)" stroke-width="1.3"></path>%s</svg>'
            % (w, h, gradient(foil, stops, 0, 0, w, h, True), w - 2.4, h - 2.4, foil, w - 26, h - 26, foil, inner, foil, orn))


def frame(who):
    """A gilt frame with a cream mat, a monogram waiting where his photo will go."""
    foil = 'c8f-foil'
    stops = GILT if who == 'mary' else BRASS
    deep = ('#6d1f35', '#3c0c1a') if who == 'mary' else ('#2c5a3e', '#14301f')
    cx, cy = 108, 128
    defs = (gradient(foil, stops, 0, 0, 216, 256, True) +
            gradient('c8f-bright', [(0, '#a67c22'), (.25, '#f7e6a8'), (.45, '#c49a3c'), (.7, '#fbedb8'), (1, '#a67c22')] if who == 'mary'
                     else [(0, '#8a7030'), (.25, '#efe0a6'), (.45, '#a88c44'), (.7, '#f4e8ba'), (1, '#8a7030')], 30, 60, 186, 200, True) +
            '<radialGradient id="c8f-deep" cx=".44" cy=".38" r=".8"><stop offset="0" stop-color="%s"></stop><stop offset="1" stop-color="%s"></stop></radialGradient>' % deep)
    letter = ('<text x="%d" y="162" text-anchor="middle" font-family="%s" font-size="112" fill="url(#c8f-bright)" stroke="#2a1604" stroke-width=".6" paint-order="stroke">M</text>' % (cx - 2, SCRIPT)
              if who == 'mary' else
              '<text x="%d" y="166" text-anchor="middle" font-family="%s" font-size="84" font-weight="500" fill="url(#c8f-bright)" stroke="#121a0c" stroke-width=".6" paint-order="stroke">M</text>' % (cx, CAPS))
    if who == 'mary':
        shape = ('<ellipse cx="108" cy="128" rx="104" ry="124" fill="url(#%s)"></ellipse>'
                 '<ellipse cx="108" cy="128" rx="104" ry="124" fill="none" stroke="#3e2a08" stroke-width="1" opacity=".7"></ellipse>'
                 '<ellipse cx="108" cy="128" rx="97" ry="117" fill="none" stroke="#fff2c0" stroke-width="2.6" stroke-dasharray=".1 5.4" stroke-linecap="round" opacity=".92"></ellipse>'
                 '<ellipse cx="108" cy="128" rx="91" ry="111" fill="#f4ebd8" stroke="#8a6a26" stroke-width="1.2"></ellipse>'
                 '<ellipse cx="108" cy="128" rx="75" ry="95" fill="url(#c8f-deep)"></ellipse>'
                 '<ellipse cx="108" cy="128" rx="75" ry="95" fill="none" stroke="url(#%s)" stroke-width="2.2"></ellipse>' % (foil, foil))
    else:
        arch = lambda i: 'M%d 252V%dA%d %d 0 0 1 %d %dV252Z' % (4 + i, 108, 104 - i, 104 - i, 212 - i, 108)
        shape = ('<path d="%s" fill="url(#%s)"></path>'
                 '<path d="%s" fill="none" stroke="#2c2206" stroke-width="1" opacity=".7"></path>'
                 '<path d="%s" fill="none" stroke="#efe0a6" stroke-width="2" opacity=".85"></path>'
                 '<path d="%s" fill="#efe7d2" stroke="#6e5a26" stroke-width="1.2"></path>'
                 '<path d="%s" fill="url(#c8f-deep)"></path>'
                 '<path d="%s" fill="none" stroke="url(#%s)" stroke-width="2.2"></path>'
                 % (arch(0), foil, arch(0), arch(7), arch(13), arch(29), arch(29), foil))
    return '<svg class="c8-frame" viewBox="0 0 216 256" role="img" aria-label="A gilt frame with the letter M, ready for his photo"><defs>%s</defs>%s%s</svg>' % (defs, shape, letter)


def foil_name(who):
    """Mark, in the same foil as the cards, deep enough to hold on cream paper."""
    stops = [(0, '#5e4009'), (.2, '#a67a24'), (.38, '#e0c070'), (.54, '#7e5a14'), (.72, '#c9a44e'), (1, '#5e4009')] if who == 'mary' else \
            [(0, '#4a3b12'), (.2, '#8e7230'), (.38, '#cdb574'), (.54, '#685322'), (.72, '#b49a58'), (1, '#463810')]
    return ('<svg class="c8-mark" viewBox="0 0 250 150" role="img" aria-label="Mark"><defs>%s</defs>'
            '<text x="124" y="108" text-anchor="middle" font-family="%s" font-size="124" fill="url(#c8n-foil)" stroke="#2a1a04" stroke-width=".7" paint-order="stroke">Mark</text></svg>'
            % (gradient('c8n-foil', stops, 20, 30, 230, 130, True), SCRIPT))


def keepsake(who):
    return ('<div class="c8-leaf %s">\n%s\n%s\n'
            '<div class="c8-date"><div class="c8-day">Saturday</div><div class="c8-seven">7</div><div class="c8-month">November</div></div>\n'
            '%s\n<div class="m8-note c8-photo-note">His photo goes here later, once Facebook is connected.</div>\n'
            '%s\n<div class="c8-memory"><div class="c8-age">Turning fifty-two</div><div class="c8-lines">Your son. Still fishes every chance he gets.</div></div>\n'
            '</div>' % (who, sheet('c8p', 724, 616, *(('#fbf4e4', '#efe2c6') if who == 'mary' else ('#f6f1e0', '#e6dcbf')), seed=3 if who == 'mary' else 5),
                        rules(who), frame(who), foil_name(who)))


def picker():
    tiles = []
    for i, (name, key) in enumerate([('Lake', 'lake'), ('Buck', 'buck'), ('Lighthouse', 'lighthouse'), ('Magnolia', 'magnolia')]):
        tiles.append('<button class="c8-tile" type="button"><span class="c8-thumb">\n%s\n</span>'
                     '<span class="c8-label"><span class="c8-big">%d</span><span class="c8-name">%s</span></span></button>' % (art(key), i + 1, name))
    return ('<div class="c8-title"><div>Or one made to order.</div><div>Tell me what you\'d like on it.</div></div>\n'
            '<div class="c8-grid">\n%s\n</div>' % '\n'.join(tiles))


VERSE = ('Wishing you a quiet joy,', 'good company and calm water,', 'and years ahead as fine', "as the man you've become.")
HAND = {
    'pen': ('c8-pen', ('Mark, I think about', 'you every day.', 'Hope you catch', 'a big one.')),
    'plain': ('c8-plainhand', ('Mark, I think about you', 'every day. Hope you', 'catch a big one.')),
}


def page_left(id_):
    sprig = ('<svg class="c8-inside-sprig" viewBox="0 0 120 30" aria-hidden="true"><defs>%s</defs><g transform="translate(60 15)" fill="url(#%s-sf)">'
             '<path d="M0 0C-7 -6 -17 -7 -28 0C-17 7 -7 6 0 0Z"></path><path d="M0 0C7 -6 17 -7 28 0C17 7 7 6 0 0Z"></path></g></svg>'
             % (gradient(id_ + '-sf', GILT, 0, 0, 1, 0), id_))
    return '<div class="c8-page l">\n%s\n%s\n<div class="c8-shade"></div></div>' % (sheet(id_, 370, 518, '#f6eedc', '#ecdfc6', 7, .28), sprig)


def page_right(id_, hand):
    cls, lines = HAND[hand]
    verse = ''.join('<div>%s</div>' % html.escape(v, quote=False) for v in VERSE)
    words = ''.join('<div>%s</div>' % html.escape(v, quote=False) for v in lines)
    return ('<div class="c8-page r">\n%s\n<div class="c8-shade"></div>\n<div class="c8-fold"></div>\n'
            '<div class="c8-verse">%s</div><div class="c8-gold"></div>\n'
            '<div class="c8-hand %s">%s<div class="c8-love">Love, Mom</div></div>\n</div>' % (sheet(id_, 370, 518, '#faf3e4', '#f0e4cc', 9, .28), verse, cls, words))


def spread(hand):
    return '<div class="c8-spread">\n<div class="c8-spread-shadow"></div>\n%s\n%s\n</div>' % (page_left('c8l'), page_right('c8r', hand))


def opening():
    return ('<div class="c8-stage">\n<div class="c8-slide">\n<div class="c8-sh-open"></div>\n<div class="c8-sh-closed"></div>\n'
            '%s\n<div class="c8-fall"></div>\n'
            '<div class="c8-cover">\n<div class="c8-face front">\n%s\n<div class="c8-dim"></div></div>\n'
            '<div class="c8-face back">\n%s\n<div class="c8-dim"></div></div>\n</div>\n</div>\n</div>'
            % (page_right('c8r', 'pen'), art('lake'), page_left('c8l')))


def main():
    board('A-Reminder-Mary.dc.html', 'Birthday reminder, Mary', 'mary', keepsake('mary'), ('Want to make', 'him a card?'))
    board('A-Reminder-Sam.dc.html', 'Birthday reminder, Sam', 'sam', keepsake('sam'), ('Want to send', 'him a card?'))
    board('B-Design-Mary.dc.html', 'Pick a picture', 'mary', picker(), ('Tell me what', "you'd like."))
    board('C-Card-Mary.dc.html', 'The card', 'mary', '<div class="c8-closed">\n<div class="c8-stock"></div>\n%s\n</div>' % art('lake'), ('What do you', 'want to say?'))
    board('C2-Inside-Mary.dc.html', 'Inside the card', 'mary', spread('pen'), ('Anything to', 'change?'))
    board('C3-Opens-Mary.dc.html', 'The card opens', 'mary', opening(), ("Here's how", 'it reads.'))
    board('C4-Plain-Mary.dc.html', 'Inside the card, plainer writing', 'mary', spread('plain'), ('Easier to', 'read?'))
    print('built 7 boards')


if __name__ == '__main__':
    main()
