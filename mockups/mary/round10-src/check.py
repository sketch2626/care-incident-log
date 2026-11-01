#!/usr/bin/env python3
"""Checks the round 10 boards by calculation, since the pages can't be opened here.
Prints one line per check group and FAIL lines; exits 1 on any failure. Stdlib only."""
import filecmp
import json
import math
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import build  # noqa: E402

ROUND10 = os.path.normpath(os.path.join(HERE, '..', 'round10'))
ROUND9 = os.path.normpath(os.path.join(HERE, '..', 'round9'))
SRC9 = os.path.normpath(os.path.join(HERE, '..', 'round9-src'))
BANNED = re.compile(r"\b(?:hello|hi there|howdy|welcome|good to see|where were we|let's begin|let's start|start over|great job|good job|well done|nice job|great|wonderful|"
                    r"awesome|perfect|amazing|excellent|fantastic|lovely|proud|sweetie|honey|darling|dearie|yay|oops|yahoo)\b", re.I)
ROWS1 = ['Anna Reyes Your niece', 'Dale Greene Your pastor', 'Ellen Pruitt Your sister', 'June Tate Your friend', 'Katie Whitfield Your granddaughter']
ROWS3 = ['Katie Whitfield Your granddaughter', 'Mark Hollis Your son', 'Sarah Whitfield Your daughter', 'Tom Hollis Your nephew']
LISTBOT = ['My doctors', 'Up', 'Down', 'Add someone']
FORM = ['All people', 'Save']
HELP = ['Save and add another', 'Done']
BUTTONS = {
    'A1-List-Mary': ['Back to Mary'] + ROWS1 + LISTBOT,
    'A2-Find-Mary': ['Back to Mary', 'Sarah Whitfield Your daughter', 'Sarah Beck Friend from church', 'My doctors', 'Show everyone', 'Add someone'],
    'B1-Card-Mary': ['Back to Mary', 'All people', 'Change', 'Email Sarah', 'Make a card'],
    'H1-Doctor-Mary': ['Back to Mary', 'All doctors', 'Change'],
    'C1-AddFill-Mary': ['Back to Mary'] + FORM, 'C2-AddSpell-Mary': ['Back to Mary'] + FORM, 'C3-AddFix-Mary': ['Back to Mary'] + FORM,
    'C4-AddSaved-Mary': ['Back to Mary'] + FORM, 'S1-AddSpell-Sam': ['Back to Sam'] + FORM,
    'D1-Email-Mary': ['Menu'], 'D2-Look-Mary': ['Back to Mary', 'Send', 'Not yet'], 'D3-Card-Mary': ['Menu'],
    'G1-KeepAsk-Mary': ['Menu'], 'G2-KeptSay-Mary': ['Menu'],
    'E1-Change-Mary': ['Back to Mary', 'Save', 'Put it back', 'Forget Sarah'],
    'E2-ForgetAsk-Mary': ['Back to Mary', 'Yes, forget her', 'No, keep her'],
    'E3-Forgotten-Mary': ['Back to Mary'] + ROWS3 + LISTBOT,
    'F1-Helper-Mary': ['Back to Mary'] + HELP, 'F2-HelperVoice-Mary': ['Back to Mary'] + HELP,
    'N-Notes': [],
}
SMALL = [name for name in BUTTONS if 'Back to Mary' in BUTTONS[name] or 'Back to Sam' in BUTTONS[name]]
LIT = ['A2-Find-Mary', 'C1-AddFill-Mary', 'C2-AddSpell-Mary', 'C3-AddFix-Mary', 'S1-AddSpell-Sam', 'E1-Change-Mary', 'F2-HelperVoice-Mary']
THEY_SAID = ['Show me Sarah', 'My daughter Sarah', 'her email is', 'No, W-H-I-T', 'save it', 'Email my daughter', 'Make Sarah a birthday card', 'new number is',
             'Forget Sarah Beck.', 'His birthday is', 'Show me my heart']
# every capitalized word the boards may use: the made-up names, then plain words. Any other is taken for a stray name.
NAMES = {'Anna', 'Reyes', 'Dale', 'Greene', 'Ellen', 'Pruitt', 'June', 'Tate', 'Katie', 'Whitfield', 'Mark', 'Hollis', 'Sarah', 'Beck', 'Tom', 'Ruth', 'Mary', 'Sam', 'Dr', 'Helen', 'Lee'}
WORDS = set('''A Add Address All Anytown Ask At Back Best Birthday But Cell Change Choose Close Demo Done Down Email Example Facebook Find Forget Friend
Friend From Games Her Here His Home I If Is It Just Keep Kept Lane Mailing Make Message Mom Mailing Menu March Name Names NC No Nobody Not Notes On One Option Or Pick
Put Relationship Road Sample Save Saved Say Send Sent She Show Sits Street Takes That The Then They Things To Typed Up Was What When Where Who Works Yes You Your July
Two Sarahs Daughter My With Son Never An Its Practice Office Fax Patient Specialty Cardiology Heart Clinic Avenue Checkups'''.split())
SITES = {'portal.example.com'}
EMAILS = {'sarah.whitfield@example.com', 'sarah.whitfeld@example.com', 'sarah.beck@example.com', 'mark.hollis@example.com'}
VOID = {'meta', 'link', 'br', 'hr', 'img', 'input'}
fails = []


def fail(msg):
    fails.append(msg)
    print('FAIL', msg)


class Walk(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.ids, self.refs, self.texts = [], [], [], []

    def note(self, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        for v in a.values():
            if v:
                self.refs += re.findall(r'url\(#([^)]+)\)', v)
        if (a.get('href') or '').startswith('#'):
            self.refs.append(a['href'][1:])

    def handle_starttag(self, tag, attrs):
        self.note(attrs)
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.note(attrs)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            fail('stray </%s> with %s open at line %d' % (tag, self.stack[-3:], self.getpos()[0]))
            return
        self.stack.pop()

    def handle_data(self, data):
        if self.stack and self.stack[-1] in ('script', 'style', 'title'):
            return
        if data.strip():
            self.texts.append(data.strip())


def captions(src):
    """Each caption block: (style, [lines])."""
    found = []
    for chunk in src.split('<div class="cap capA ')[1:]:
        style = 'words' if chunk.startswith('m9-words') else 'full'
        block = chunk[:chunk.index('\n</div>') if '\n</div>' in chunk else None]
        lines = [' '.join(re.findall(r'data-t="([^"]*)"', x)).replace('&#x27;', "'") for x in re.findall(r'<div class="line">(.*?)</div>', block)]
        found.append((style, lines))
    return found


def check_data(name, words):
    """Only the made-up data: emails, phones and names from the brief; the plain-words rules for this round."""
    for mail in re.findall(r'[\w.+-]+@[\w.-]+', words):
        if not mail.endswith('@example.com') or mail not in EMAILS:
            fail('%s: email %s' % (name, mail))
    for site in re.findall(r'(?<![@\w.-])[\w-]+(?:\.[\w-]+)*\.(?:com|org|net)\b', words):
        if site not in SITES:
            fail('%s: web address %s' % (name, site))
    for phone in re.findall(r'\(?\d{3}\)?[ -]\d{3}-\d{4}', words):
        if not re.search(r'555-01\d\d$', phone):
            fail('%s: phone %s' % (name, phone))
    for token in re.findall(r"\b[A-Z][a-z]+\b", words):
        if token not in NAMES and token not in WORDS:
            fail('%s: unknown capitalized word %s' % (name, token))
    if re.search(r'\bgone\b', words, re.I):
        fail("%s: the word 'gone'" % name)
    if re.search(r'\bSaved\b', words) and name != 'C4-AddSaved-Mary':
        fail("%s: 'Saved' shows on a board other than C4" % name)


def check_boards(boards):
    for b in boards:
        name = b['stem']
        path = os.path.join(ROUND10, name + '.dc.html')
        src = open(path, encoding='utf-8').read()
        if src != b['html']:
            fail('%s: file on disk is stale, run build.py' % name)
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
        for tag_size in re.findall(r'font-size[:=]"?\s*([\d.]+)', src):
            if float(tag_size) < 20:
                fail('%s: inline font-size %s' % (name, tag_size))
        joined = ' '.join(w.texts)
        labels = ' '.join(re.findall(r'aria-label="([^"]*)"', src))
        hit_word = BANNED.search(joined + ' ' + labels + ' ' + b['aloud'])
        if hit_word:
            fail('%s: banned words: %s' % (name, hit_word.group(0)))
        if '!' in joined + b['aloud']:
            fail('%s: exclamation mark' % name)
        if re.search('[\U0001F300-\U0001FAFF☀-➿⭐]', joined + b['aloud']):
            fail('%s: emoji or star in the text' % name)
        check_data(name, joined + ' ' + b['aloud'] + ' ' + ' '.join(' '.join(x) for _, x in captions(src)))
        pressed = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'<svg.*?</svg>', '', x, flags=re.S))).strip() for x in re.findall(r'<button[^>]*>(.*?)</button>', src, re.S)]
        if sorted(pressed) != sorted(BUTTONS[name]):
            fail('%s: buttons %s' % (name, pressed))
        caps = captions(src)
        all_lines = []
        for style, lines in caps:
            all_lines += lines
            if not 1 <= len(lines) <= 2:
                fail('%s: caption has %d lines' % (name, len(lines)))
            for line in lines:
                if len(line) > build.LIMIT[style]:
                    fail('%s: caption line over %d: %s' % (name, build.LIMIT[style], line))
                for said in THEY_SAID:
                    if said.lower() in line.lower():
                        fail('%s: their own words as a caption' % name)
        if all_lines != list(b['lines']):
            fail('%s: captions on the page differ from the board data: %s' % (name, all_lines))
        if name != 'N-Notes' and not caps:
            fail('%s: no caption' % name)
        print('%-20s %3d KB  %2d buttons  %s' % (name, len(src) // 1024, len(pressed), ' / '.join(all_lines) or '(no caption)'))


def hit(a, b):
    return a['x'] < b['x'] + b['w'] and b['x'] < a['x'] + a['w'] and a['y'] < b['y'] + b['h'] and b['y'] < a['y'] + a['h']


def inside(a, b):
    return b['x'] <= a['x'] and b['y'] <= a['y'] and a['x'] + a['w'] <= b['x'] + b['w'] and a['y'] + a['h'] <= b['y'] + b['h']


def rect(t, label=''):
    return {'label': label, 'x': t[0], 'y': t[1], 'w': t[2], 'h': t[3]}


def grow(r, by):
    return {'label': r['label'], 'x': r['x'] - by, 'y': r['y'] - by, 'w': r['w'] + 2 * by, 'h': r['h'] + 2 * by}


def check_layout(boards):
    band = {k: rect(v, k) for k, v in build.BAND.items()}
    page, row = rect(build.PAGE, 'page'), rect(build.ROW, 'row')
    parts = [band['small'], band['words'], band['back']]
    for i, a in enumerate(parts):
        if not inside(a, band['band']):
            fail('layout: %s leaves the band' % a['label'])
        for z in parts[i + 1:]:
            if hit(a, z):
                fail('layout: %s touches %s' % (a['label'], z['label']))
    for pair in ((band['band'], page), (page, row), (band['band'], row)):
        if hit(*pair):
            fail('layout: %s overlaps %s' % (pair[0]['label'], pair[1]['label']))
    if band['band']['h'] != page['y'] or page['y'] + page['h'] != row['y'] or row['y'] + row['h'] != build.H:
        fail('layout: band, page and row do not stack exactly to y 800')
    count, smallest = 0, 999
    for b in boards:
        name = b['stem']
        if (name in SMALL) != ('class="m9-small"' in b['html']):
            fail('%s: small Mary on the wrong kind of board' % name)
        if b['kind'] != 'deep':
            continue
        rs = b['rects']
        count += len(rs)
        placed = len(re.findall(r'style="left:\d+px;top:\d+px;width:\d+px;height:\d+px"', b['html']))
        if placed != len(rs):
            fail('%s: %d boxes placed, %d measured' % (name, placed, len(rs)))
        for r in rs:
            home = row if r['y'] >= row['y'] else page
            room = grow(r, 3) if r['lit'] else r
            if r['x'] < 0 or r['y'] < 0 or r['x'] + r['w'] > build.W or r['y'] + r['h'] > build.H:
                fail('%s: %s leaves the screen' % (name, r['label']))
            if r['y'] < 156:
                fail('%s: %s is in the band' % (name, r['label']))
            if not inside(room, home):
                fail('%s: %s leaves its area (%s)' % (name, r['label'], home['label']))
            if r['kind'] == 'target':
                smallest = min(smallest, r['w'], r['h'])
                if r['w'] < 64 or r['h'] < 64:
                    fail('%s: target %s is %dx%d' % (name, r['label'], r['w'], r['h']))
            if r['kind'] == 'field' and r['h'] < 64:
                fail('%s: field %s is %d tall' % (name, r['label'], r['h']))
        for i, a in enumerate(rs):
            for z in rs[i + 1:]:
                aa, zz = (grow(a, 3) if a['lit'] else a), (grow(z, 3) if z['lit'] else z)
                if hit(aa, zz) and not (inside(aa, zz) or inside(zz, aa)):
                    fail('%s: %s touches %s' % (name, a['label'], z['label']))
        rows = [r for r in rs if r['label'].startswith('row ')]
        if len(rows) != b['html'].count('class="m10-row') or any(r['tag'] != 'button' or r['kind'] != 'target' for r in rows):
            fail('%s: a list row is not a measured button' % name)
        for r in rows:
            if r['w'] < 64 or r['h'] < 64:
                fail('%s: list row %s is %dx%d' % (name, r['label'], r['w'], r['h']))
        if (name in LIT) != ('m9-lit' in b['html']):
            fail('%s: lit state is wrong' % name)
    for box in (build.MENU_BTN, build.BAND['back'], build.BAND['small']):
        smallest = min(smallest, box[2], box[3])
        if box[2] < 64 or box[3] < 64:
            fail('target too small: %s' % (box,))
    n = 0
    screen = rect((0, 0, build.W, build.H), 'screen')
    for b in boards:
        if b['kind'] != 'full':
            continue
        for r in b['rects']:
            n += 1
            if not inside(r, screen):
                fail('%s: note leaves the screen' % b['stem'])
            for zone, label in ((build.FACE_ZONE, 'her face'), (build.CAP_ZONE, 'the caption'), (build.MENU_BTN, 'Menu')):
                if hit(r, rect(zone)):
                    fail('%s: note touches %s' % (b['stem'], label))
    print('layout: band parts and page areas clear of each other; %d boxes on deeper boards measured; smallest target %dpx; %d full-page notes clear of her face, caption and Menu' % (count, smallest, n))


def check_fit(boards):
    worst, n, tight = 1, 0, ''
    rows = []
    for b in boards:
        rows += [(b['stem'], *r['fit']) for r in b['rects'] if r.get('fit')]
        rows += [(b['stem'], *f) for f in b['fits']]
        for style, lines in captions(b['html']):
            px, room = (32, build.BAND['words'][2]) if style == 'words' else (44, 1168)
            rows += [(b['stem'], 'caption ' + line, len(line) * .56 * px, room) for line in lines]
    rows.append(('band', 'Back to Mary with its arrow', 12 * .58 * 34 + 44 + 14, 368 - 8 - 40))
    for name, label, need, room in rows:
        n += 1
        if 1 - need / room < worst:
            worst, tight = 1 - need / room, '%s %s' % (name, label)
        if need > room:
            fail('fit: %s %s needs %.0f of %d' % (name, label, need, room))
    print('fit: %d lines at conservative widths, tightest has %.1f%% to spare (%s)' % (n, worst * 100, tight))
    line = 28 * 1.2
    for label, bottom, limit in [('Card two-line box', 2 * line + 6, 104), ('Form two-line box', 2 * line + 6, 98), ('To box, two lines', 2 * line + 6, 104),
                                 ('Message, three lines at 30px', 18 * 2 + 3 * 40.5 + 6, 200), ('Tight note, three lines', 3 * 23 + 4 + 6, 84),
                                 ('Full-page note, four lines', 4 * 26 + 12 + 6, 122), ('N section', 48 + 10 + 2 * 40.5, 232), ('N last section', 80 + 232 * 2 + 48 + 10 + 2 * 40.5, 800)]:
        if bottom > limit:
            fail('height: %s ends %d past %d' % (label, bottom, limit))
    print('heights: every block ends inside its area')


def lum(c):
    v = [int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    v = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in v]
    return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]


def ratio(a, b):
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + .05) / (lo + .05)


CONTRAST = [('Value on lit field', '#1f1b16', '#fff1c7', 7), ('Value on white field', '#1f1b16', '#ffffff', 7), ('Labels on the page', '#1f1b16', '#fbf7ef', 7),
            ('Find someone on white', '#544739', '#ffffff', 7), ('Was line on lit field', '#544739', '#fff1c7', 7), ('Save-style buttons', '#ffffff', '#0f5560', 7),
            ('White bottom-row buttons, lock line', '#1f1b16', '#ffffff', 7), ('Notes', '#1f1b16', '#fffdf8', 7),
            ('Her words, Mary ink on the white edge', '#9b2c58', '#ffffff', 7), ('Her words, Sam ink on the white edge', '#1b5a8c', '#ffffff', 7),
            ('Back to Mary', '#2b1f17', '#fffdf8', 7), ('Notes board on her glow, darkest spot', '#1f1b16', '#f6af74', 7), ('Gold ring against pale gold edge', '#2b1f17', '#f2b632', 3)]


def check_contrast():
    for label, fg, bg, need in CONTRAST:
        r = ratio(fg, bg)
        print('contrast: %-40s %s on %s %5.1f:1' % (label, fg, bg, r))
        if r < need:
            fail('contrast: %s %.1f under %d' % (label, r, need))


def font_sizes(sheet):
    sizes = [float(x) for x in re.findall(r'font-size:\s*([\d.]+)px', sheet)]
    for decl in re.findall(r'[{;]font:([^;}]*)', sheet):
        m = re.search(r'([\d.]+)px', decl)
        if m:
            sizes.append(float(m.group(1)))
    return sizes


def check_css(boards):
    css = open(os.path.join(ROUND10, 'r10.css'), encoding='utf-8').read()
    r9 = open(os.path.join(ROUND10, 'r9.css'), encoding='utf-8').read()
    r6 = open(os.path.join(ROUND10, 'r6.css'), encoding='utf-8').read()
    used = set()
    for b in boards:
        for names in re.findall(r'class="([^"]*)"', b['html']):
            used.update(names.split())
    idle = sorted(set(re.findall(r'\.(m10-[\w-]+)', css)) - used)
    if idle:
        fail('r10.css: classes no board uses: %s' % idle[:8])
    if sorted(c for c in re.findall(r'\.([\w-]+)', re.sub(r'/\*.*?\*/', '', re.sub(r'\{[^}]*\}', '{}', css), flags=re.S)) if not c.startswith('m10-') and c != 'm9-lit' and c != 'm9-v'):
        fail('r10.css: a class that is not .m10-')
    blocks = re.findall(r'@keyframes [\w-]+\{.*?\}\}', css + r9, re.S)
    for block in blocks:
        extra = set(re.findall(r'[{;]([a-z-]+):', block)) - {'transform', 'opacity', 'animation-timing-function'}
        if extra:
            fail('keyframes animate %s' % sorted(extra))
    if re.search(r'transition', css):
        fail('r10.css: transitions are not checked; use keyframes')
    if '@keyframes' in css:
        fail('r10.css: new motion needs a reduced-motion rule')
    sizes = font_sizes(css) + font_sizes(r9) + font_sizes(r6)
    low = [s for s in sizes if s < 20]
    if low:
        fail('font-size under 20px: %s' % low)
    print('css: %d font sizes, smallest %.0fpx; %d keyframes, transform and opacity only; r10.css adds no motion' % (len(sizes), min(sizes), len(blocks)))
    # C1: the email fills in on round 9's stacked opacity, and rests on the whole address
    src = next(b['html'] for b in boards if b['stem'] == 'C1-AddFill-Mary')
    stages = re.findall(r'<span class="m9-v (a|b|c)">([^<]*)</span>', src)
    if [s[0] for s in stages] != ['a', 'b', 'c'] or tuple(s[1] for s in stages) != build.STAGES:
        fail('C1: the stacked email is %s' % stages)
    elif not (stages[1][1].startswith(stages[0][1]) and stages[2][1].startswith(stages[1][1])):
        fail('C1: each stage must grow from the one before')
    if not re.search(r'class="m9-field m9-lit"[^>]*><span class="m9-fill m10-wide">', src):
        fail('C1: the stacked email is not in the lit field')
    if sum('m9-fill' in b['html'] for b in boards) != 1:
        fail('only C1 has a filling value')
    if '.m9-v.c{opacity:1}' not in r9 or '.m9-v.a,.m9-v.b,.m9-v.c{animation:none}' not in r9[r9.index('@media (prefers-reduced-motion'):]:
        fail('reduced motion must rest on the whole address')
    print('C1 stacked email: %s; rests on the last, reduced motion too' % ' / '.join(s[1] for s in stages))
    return css


def check_face():
    x, y, w, h = build.FACE_BOX
    cx, cy, rr = x + w / 2, y + h / 2, w / 2
    far = 0
    # the widest points of both faces (brow ends, cheek edges, mouth corners), under her sway and lean
    points = [(226, 136), (414, 136), (228, 138), (412, 138), (210, 234), (430, 234), (210, 236), (430, 236), (290, 260), (350, 260), (320, 275), (240, 108), (400, 108)]
    for px, py in points:
        for deg in (-4, 4):
            t = math.radians(deg)
            qx = 320 + (px - 320) * math.cos(t) - (py - 330) * math.sin(t)
            qy = 330 + (px - 320) * math.sin(t) + (py - 330) * math.cos(t) - 4
            far = max(far, math.hypot(qx - cx, qy - cy))
    ring = 5 * w / build.BAND['small'][2]  # her 5px ring, in face units
    if far > rr - ring:
        fail('face: reaches %.0f, the inside of the ring is %.0f' % (far, rr - ring))
    print('face: viewBox %d %d %d %d, widest point %.0f of %.0f units inside the ring' % (x, y, w, h, far, rr - ring))


def check_files(boards):
    for a, b in ((os.path.join(ROUND9, 'r6.css'), os.path.join(ROUND10, 'r6.css')), (os.path.join(ROUND9, 'r9.css'), os.path.join(ROUND10, 'r9.css')),
                 (os.path.join(SRC9, 'face-mary.svg'), os.path.join(HERE, 'face-mary.svg')), (os.path.join(SRC9, 'face-sam.svg'), os.path.join(HERE, 'face-sam.svg'))):
        if not filecmp.cmp(a, b, shallow=False):
            fail('%s is not a byte-identical copy' % os.path.basename(b))
    names = {f[:-len('.dc.html')] for f in os.listdir(ROUND10) if f.endswith('.dc.html')}
    want = {b['stem'] for b in boards}
    if names != want or want != set(BUTTONS):
        fail('boards differ: %s' % sorted((names ^ want) | (want ^ set(BUTTONS))))
    canvas = json.load(open(os.path.join(ROUND10, 'canvas.json'), encoding='utf-8'))
    for file in canvas['boards']:
        if not os.path.exists(os.path.join(ROUND10, file)):
            fail('canvas: %s is missing' % file)
    if {f[:-len('.dc.html')] for f in canvas['boards']} != want or sorted(canvas['order']) != sorted(canvas['boards']):
        fail('canvas.json boards differ from the list')
    if canvas['title'] != 'Mary round 10: a secure address book':
        fail('canvas title')
    for c in canvas['boards'].values():
        if (c['w'], c['h']) != (1280, 800) or c['x'] % 1360:
            fail('canvas: board size or spacing')
    print('files: r6.css, r9.css and faces identical; canvas: %d boards, %d rows, every file exists' % (len(canvas['boards']), len(canvas['notes'])))
    readme = os.path.join(ROUND10, 'README.md')
    if os.path.exists(readme):
        text = open(readme, encoding='utf-8').read()
        for b in boards:
            if b['aloud'] and b['aloud'] not in text:
                fail('README: missing the full line of %s' % b['stem'])
            if b['stem'] not in text:
                fail('README: missing %s' % b['stem'])
        if 'no real names or data' not in text.lower():
            fail('README: must state no real names or data are used')
    else:
        fail('README.md is missing')


if __name__ == '__main__':
    built = build.make_boards()
    check_boards(built)
    check_layout(built)
    check_fit(built)
    check_contrast()
    check_css(built)
    check_face()
    check_files(built)
    print('OK' if not fails else '%d FAILED' % len(fails))
    sys.exit(1 if fails else 0)
