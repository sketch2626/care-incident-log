#!/usr/bin/env python3
"""Checks the boards made by build.py by calculation, since the page can't be opened here.
Prints one line per check group and FAIL lines; exits 1 on any failure. Stdlib only."""
import math
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
ROUND8 = os.path.normpath(os.path.join(HERE, '..', 'round8'))
BUILT = ['A-Reminder-Mary', 'A-Reminder-Sam', 'B-Design-Mary', 'C-Card-Mary', 'C2-Inside-Mary', 'C3-Opens-Mary', 'C4-Plain-Mary']
ART_SCALE = {'B-Design-Mary': .4, 'C-Card-Mary': .874, 'C3-Opens-Mary': .74}  # on-screen scale of a card front
VOID = {'meta', 'link', 'br', 'hr', 'img', 'input'}
fails = []


def fail(msg):
    fails.append(msg)
    print('FAIL', msg)


class Walk(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.ids, self.refs, self.texts, self.fonts = [], [], [], [], []
        self.art = 0

    def note(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        for v in a.values():
            if v:
                self.refs += re.findall(r'url\(#([^)]+)\)', v)
        if (a.get('href') or '').startswith('#'):
            self.refs.append(a['href'][1:])
        if tag == 'text':
            self.fonts.append((float(a.get('font-size', 0)), bool(self.art)))
        return a

    def handle_starttag(self, tag, attrs):
        a = self.note(tag, attrs)
        if tag in VOID:
            return
        self.stack.append(tag)
        if tag == 'svg' and 'c8-art' in (a.get('class') or ''):
            self.art = len(self.stack)

    def handle_startendtag(self, tag, attrs):
        self.note(tag, attrs)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            fail('stray </%s> with %s open at line %d' % (tag, self.stack[-3:], self.getpos()[0]))
            if tag in self.stack:
                while self.stack.pop() != tag:
                    pass
            return
        if self.art and len(self.stack) == self.art:
            self.art = 0
        self.stack.pop()

    def handle_data(self, data):
        if self.stack and self.stack[-1] in ('script', 'style'):
            return
        if data.strip():
            self.texts.append(data.strip())


def check_boards():
    for name in BUILT:
        src = open(os.path.join(ROUND8, name + '.dc.html'), encoding='utf-8').read()
        w = Walk()
        w.feed(src)
        if w.stack:
            fail('%s: left open %s' % (name, w.stack[-4:]))
        dup = sorted({i for i in w.ids if w.ids.count(i) > 1})
        if dup:
            fail('%s: duplicate ids %s' % (name, dup[:6]))
        missing = sorted(set(w.refs) - set(w.ids))
        if missing:
            fail('%s: dangling references %s' % (name, missing[:6]))
        scale = ART_SCALE.get(name, 1)
        shown = [s * (scale if a else 1) for s, a in w.fonts]
        for px in shown:
            if px < 20:
                fail('%s: SVG text shows at %.1fpx' % (name, px))
        joined = ' '.join(w.texts)
        if '!' in joined:
            fail('%s: exclamation mark in the text' % name)
        if re.search('[\U0001F300-\U0001FAFF☀-➿]', joined):
            fail('%s: emoji in the text' % name)
        said = [' '.join(re.findall(r'data-t="([^"]*)"', x)).replace('&#x27;', "'") for x in re.findall(r'<div class="line">(.*?)</div>', src)]
        if not 1 <= len(said) <= 2 or any(len(x) > 13 for x in said):
            fail('%s: caption %s' % (name, said))
        print('%-16s %5d KB  %3d ids  smallest svg text %5.1fpx  caption: %s' % (name, len(src) // 1024, len(w.ids), min(shown or [0]), ' / '.join(said)))


def check_css():
    css = open(os.path.join(ROUND8, 'r8.css'), encoding='utf-8').read()
    css = css[css.index('M15b: the card art boards'):]
    sizes = [float(x) for x in re.findall(r'font-size:\s*([\d.]+)px', css)]
    for decl in re.findall(r'[{;]font:([^;}]*)', css):
        m = re.search(r'([\d.]+)px', decl)
        if m:
            sizes.append(float(m.group(1)))
    low = [s for s in sizes if s < 20]
    if low:
        fail('r8.css: font-size under 20px: %s' % low)
    blocks = re.findall(r'@keyframes [\w-]+\{.*?\}\}', css, re.S)
    for block in blocks:
        extra = set(re.findall(r'[{;]([a-z-]+):', block)) - {'transform', 'opacity', 'animation-timing-function'}
        if extra:
            fail('keyframes animate %s' % sorted(extra))
    print('css: %d font sizes, smallest %.0fpx; %d keyframes, transform and opacity only' % (len(sizes), min(sizes), len(blocks)))


FIT = [
    # label, characters, em per char, px, room
    ('A  SATURDAY, Cinzel with .16em tracking', 8, .88, 30, 300),
    ('A  NOVEMBER, Cinzel with .16em tracking', 8, .88, 30, 300),
    ('A  Mark, Pinyon', 4, .40, 124, 250),
    ('A  Turning fifty-two, EB Garamond', 17, .44, 34, 378),
    ('A  Your son. Still fishes every, EB Garamond', 28, .44, 28, 378),
    ('A  note line, Segoe UI 600', 27, .56, 20, 306),
    ('B  Lighthouse, serif bold', 10, .50, 28, 142),
    ('B  title line 2, EB Garamond', 30, .44, 28, 450),
    ('card  Happy Birthday, Pinyon, Buck', 14, .40, 82, 460),
    ('card  Happy Birthday, Pinyon, Magnolia', 14, .40, 78, 440),
    ('card  Birthday, Pinyon, Lake', 8, .40, 100, 432),
    ('card  for my son, Cinzel, Lake', 10, .72, 50, 432),
    ('card  for my son, Cinzel with 3 tracking, Lake', 10, .78, 50, 432),
    ('card  Birthday, Pinyon, Lighthouse, clear of the tower', 8, .40, 96, 330),
    ('C2 longest verse line, EB Garamond', 28, .44, 26, 322),
    ('C2 longest pen line, Cedarville', 19, .56, 30, 322),
    ('C2 Love, Mom, Cedarville, after 150 inset', 9, .56, 34, 172),
    ('C4 longest line, Kalam', 23, .50, 28, 322),
    ('C4 Love, Mom, Kalam, after 150 inset', 9, .50, 34, 172),
]


def check_fit():
    worst = 1
    for label, chars, em, px, room in FIT:
        need = chars * em * px
        worst = min(worst, 1 - need / room)
        if need > room:
            fail('fit: %s needs %.0f of %d' % (label, need, room))
    print('fit: %d lines at conservative widths, tightest has %.1f%% to spare' % (len(FIT), worst * 100))
    for label, bottom, limit in [('A date block', 56 + 40 + 188 + 40, 366), ('A photo note', 296 + 52 + 12 + 6, 372), ('A memory', 424 + 44 + 8 + 72, 590),
                                 ('B grid', 154 + 280 * 2 + 40, 768), ('C card', 148 + 612, 768), ('C2 pen page', 222 + 43 * 4 + 6 + 48, 518),
                                 ('C4 plain page', 222 + 40 * 3 + 6 + 48, 518)]:
        if bottom > limit:
            fail('height: %s ends %d past %d' % (label, bottom, limit))
    print('heights: every block ends inside its area')


def ease(x, a=.45, b=.05, c=.55, d=.95):
    lo, hi = 0, 1
    for _ in range(40):
        t = (lo + hi) / 2
        if 3 * (1 - t) ** 2 * t * a + 3 * (1 - t) * t * t * c + t ** 3 < x:
            lo = t
        else:
            hi = t
    t = (lo + hi) / 2
    return 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * d + t ** 3


def check_swing():
    """The cover's free edge through the whole swing, with the real easing and slide."""
    d, ox, oy, half = 2600, 882, 454, 259
    box = [9999, 9999, -9999, -9999]
    mid = None
    for i in range(481):
        e = ease(i / 480)
        th = e * math.pi
        fold = 882 - 185 * (1 - e)
        x = fold + 370 * math.cos(th)
        s = d / (d - (370 * math.sin(th) + 1))
        X = ox + (x - ox) * s
        top, bot = oy - half * s, oy + half * s
        box = [min(box[0], X, fold), min(box[1], top), max(box[2], X, fold), max(box[3], bot)]
        if mid is None and th >= math.pi / 2:
            mid = (s, X, top, bot, fold)
    print('swing at 90deg: scale %.3f, free edge x %.0f, y %.0f to %.0f, fold at x %.0f' % mid)
    print('swing whole path: x %.0f to %.0f, y %.0f to %.0f' % (box[0], box[2], box[1], box[3]))
    if box[0] < 492 or box[2] > 1252 or box[1] < 0 or box[3] > 800:
        fail('swing leaves the area: %s' % box)
    if box[1] < 130 and box[2] > 1029:
        fail('swing touches the Menu button')
    print('swing: clear of the caption (ends x 488) and the Menu button (x 1029 on, y to 130)')


if __name__ == '__main__':
    check_boards()
    check_css()
    check_fit()
    check_swing()
    print('OK' if not fails else '%d FAILED' % len(fails))
    sys.exit(1 if fails else 0)
