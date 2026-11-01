#!/usr/bin/env python3
"""Checks the round 9 boards by calculation, since the pages can't be opened here.
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

ROUND9 = os.path.normpath(os.path.join(HERE, '..', 'round9'))
ROUND8 = os.path.normpath(os.path.join(HERE, '..', 'round8'))
SRC8 = os.path.normpath(os.path.join(HERE, '..', 'round8-src'))
BANNED = re.compile(r"\b(?:hello|hi there|howdy|welcome|good to see|where were we|let's begin|let's start|start over|great job|good job|well done|nice job|great|wonderful|"
                    r"awesome|perfect|amazing|excellent|fantastic|lovely|proud|sweetie|honey|darling|dearie|yay|oops|yahoo|facebook)\b", re.I)
FORM = ['Save']
WAIT = ['15 min', '30 min', '1 hour', '2+ hours', 'No one ever came']
BAD = ['Minor', 'Serious It hurt me or really upset me.', 'Dangerous I could have been badly hurt.']
MENU_NAMES = ['Stop talking', 'Things Mary can do', 'My info', 'Choose Mary or Sam', 'Games', 'Close Mary']
# every button named per board; A and E2 boards also have Menu, which is listed
BUTTONS = {
    'A1-Full-Mary': ['Menu'], 'A2-Menu-Mary': ['Hide menu'] + MENU_NAMES,
    'A3-MyInfo-Mary': ['Back to Mary'] + FORM, 'B1-Fill-Mary': ['Back to Mary'] + FORM, 'B2-Saved-Mary': ['Back to Mary'] + FORM,
    'S1-Fill-Sam': ['Back to Sam'] + FORM,
    'C1-Explain-Mary': ['Back to Mary'] + WAIT + BAD + FORM, 'C2-FillForm-Mary': ['Back to Mary'] + WAIT + BAD + FORM,
    'D1-Secret-Mary': ['Back to Mary', 'Gmail', 'Paste', 'Connect email'],
    'E1-Grow-Mary': FORM + ['Back to Mary'], 'E2-Back-Mary': ['Menu'], 'N-Notes': [],
}
SMALL = ['A3-MyInfo-Mary', 'B1-Fill-Mary', 'B2-Saved-Mary', 'S1-Fill-Sam', 'C1-Explain-Mary', 'C2-FillForm-Mary', 'D1-Secret-Mary']
THEY_SAID = ['Put my room number', 'pressed my call light', 'save it']
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
    """Each caption block: (style, [lines]). Two blocks only on E1."""
    found = []
    for chunk in src.split('<div class="cap capA ')[1:]:
        style = 'words' if chunk.startswith('m9-words') else 'full'
        block = chunk[:chunk.index('\n</div>') if '\n</div>' in chunk else None]
        lines = [' '.join(re.findall(r'data-t="([^"]*)"', x)).replace('&#x27;', "'") for x in re.findall(r'<div class="line">(.*?)</div>', block)]
        found.append((style, lines))
    return found


def check_boards(boards):
    for b in boards:
        name = b['stem']
        path = os.path.join(ROUND9, name + '.dc.html')
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
        hit = BANNED.search(joined + ' ' + labels + ' ' + b['aloud'])
        if hit:
            fail('%s: banned words: %s' % (name, hit.group(0)))
        if '!' in joined + b['aloud']:
            fail('%s: exclamation mark' % name)
        if re.search('[\U0001F300-\U0001FAFF☀-➿⭐]', joined + b['aloud']):
            fail('%s: emoji or star in the text' % name)
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
        print('%-18s %3d KB  %2d buttons  %s' % (name, len(src) // 1024, len(pressed), ' / '.join(all_lines) or '(no caption)'))


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
        if b['kind'] != 'deep':
            continue
        name = b['stem']
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
    for box in [build.MENU_BTN] + build.MENU_ITEMS + [build.BAND['back'], build.BAND['small']]:
        smallest = min(smallest, box[2], box[3])
        if box[2] < 64 or box[3] < 64:
            fail('target too small: %s' % (box,))
    last = build.MENU_ITEMS[-1]
    if last[1] + last[3] + 20 > build.H:
        fail('menu leaves the screen')
    if not any('m9-lit' in re.sub(r'<svg.*?</svg>', '', b['html'], flags=re.S) for b in boards if b['stem'] == 'B1-Fill-Mary'):
        fail('B1: no lit field')
    if 'm9-lit' in next(b['html'] for b in boards if b['stem'] == 'B2-Saved-Mary'):
        fail('B2: a field is still lit')
    print('layout: band parts and page areas clear of each other; %d boxes on deeper boards measured; smallest target %dpx' % (count, smallest))


def check_fit(boards):
    worst, n = 1, 0
    rows = []
    for b in boards:
        rows += [(b['stem'], *r['fit']) for r in b['rects'] if r.get('fit')]
        for style, lines in captions(b['html']):
            px, room = (32, build.BAND['words'][2]) if style == 'words' else (44, 624 if 'm9-full left' in b['html'] else 1168)
            rows += [(b['stem'], 'caption ' + line, len(line) * .56 * px, room) for line in lines]
    rows.append(('band', 'Back to Mary with its arrow', 12 * .58 * 34 + 44 + 14, 368 - 8 - 40))
    rows += [('A2', 'menu item ' + name, len(name) * .56 * 32 + 46 + 22, 520 - 58) for name in MENU_NAMES]
    rows += [('C', 'Dangerous in its 150 column', 9 * .58 * 26, 150)]
    for name, label, need, room in rows:
        n += 1
        worst = min(worst, 1 - need / room)
        if need > room:
            fail('fit: %s %s needs %.0f of %d' % (name, label, need, room))
    print('fit: %d lines at conservative widths, tightest has %.1f%% to spare' % (n, worst * 100))
    for label, bottom, limit in [('C words, 4 lines at 30px', 18 + 4 * 40.5 + 18, 300), ('N section', 48 + 10 + 2 * 40.5, 232), ('N last section', 80 + 232 * 2 + 48 + 10 + 2 * 40.5, 800)]:
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
            ('Hints on white', '#544739', '#ffffff', 7), ('Save, Paste, chosen option', '#ffffff', '#0f5560', 7), ('Notes', '#1f1b16', '#fffdf8', 7),
            ('Her words, Mary ink on the white edge', '#9b2c58', '#ffffff', 7), ('Her words, Sam ink on the white edge', '#1b5a8c', '#ffffff', 7),
            ('Back to Mary', '#2b1f17', '#fffdf8', 7), ('Notes board on her glow, darkest spot', '#1f1b16', '#f6af74', 7), ('Gold ring against pale gold edge', '#2b1f17', '#f2b632', 3)]


def check_contrast():
    for label, fg, bg, need in CONTRAST:
        r = ratio(fg, bg)
        print('contrast: %-40s %s on %s %5.1f:1' % (label, fg, bg, r))
        if r < need:
            fail('contrast: %s %.1f under %d' % (label, r, need))


def check_css(boards):
    css = open(os.path.join(ROUND9, 'r9.css'), encoding='utf-8').read()
    used = set()
    for b in boards:
        for names in re.findall(r'class="([^"]*)"', b['html']):
            used.update(names.split())
    idle = sorted(set(re.findall(r'\.(m9-[\w-]+)', css)) - used)
    if idle:
        fail('r9.css: classes no board uses: %s' % idle[:8])
    reduced = css[css.index('@media (prefers-reduced-motion'):]
    for cls in ('.m9-v.a', '.m9-v.b', '.m9-v.c', '.m9-grow', '.m9-gone', '.m9-capin', '.m9-ring', '.mouth-talk'):
        if cls not in reduced:
            fail('reduced motion leaves %s moving' % cls)
    if '.m9-v.c{opacity:1}' not in css or '.m9-gone{opacity:0;' not in css:
        fail('reduced motion must rest on 214 and on the page gone')
    if '.m9-grow{' in css and 'transform:' in css[css.index('.m9-grow{'):css.index('@keyframes m9-grow')].split('}')[0]:
        fail('E1 must rest at full size')
    blocks = re.findall(r'@keyframes [\w-]+\{.*?\}\}', css, re.S)
    for block in blocks:
        extra = set(re.findall(r'[{;]([a-z-]+):', block)) - {'transform', 'opacity', 'animation-timing-function'}
        if extra:
            fail('keyframes animate %s' % sorted(extra))
    if re.search(r'transition', css):
        fail('r9.css: transitions are not checked; use keyframes')
    sizes = [float(x) for x in re.findall(r'font-size:\s*([\d.]+)px', css)]
    for decl in re.findall(r'[{;]font:([^;}]*)', css):
        m = re.search(r'([\d.]+)px', decl)
        if m:
            sizes.append(float(m.group(1)))
    r6 = open(os.path.join(ROUND9, 'r6.css'), encoding='utf-8').read()
    for sheet in (r6,):
        sizes += [float(x) for x in re.findall(r'font-size:\s*([\d.]+)px', sheet)]
        for decl in re.findall(r'[{;]font:([^;}]*)', sheet):
            m = re.search(r'([\d.]+)px', decl)
            if m:
                sizes.append(float(m.group(1)))
    low = [s for s in sizes if s < 20]
    if low:
        fail('font-size under 20px: %s' % low)
    print('css: %d font sizes, smallest %.0fpx; %d keyframes in r9.css, transform and opacity only' % (len(sizes), min(sizes), len(blocks)))
    # E1 timing: the page has gone before the bottom caption starts
    gone = int(re.search(r'm9-fade\{0%,10%\{opacity:1\}(\d+)%', css).group(1))
    cap = int(re.search(r'm9-capin\{0%,(\d+)%', css).group(1))
    if gone > cap:
        fail('E1: bottom caption starts at %d%% before the page has gone at %d%%' % (cap, gone))
    print('E1 timing: page gone at %d%%, bottom caption starts at %d%%; nothing sits over the page' % (gone, cap))
    return css


def check_face(css):
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
    s = build.BAND['small'][2] / w / 2
    tx, ty = 82 - s * 640, 78 - s * 380
    m = re.search(r'translate\((-?[\d.]+)px,(-?[\d.]+)px\) scale\(([\d.]+)\)', css)
    if abs(float(m.group(1)) - tx) > .05 or abs(float(m.group(2)) - ty) > .05 or abs(float(m.group(3)) - s) > .0001:
        fail('E1: grow start is %s, her head in the corner needs %.2f %.2f %.5f' % (m.groups(), tx, ty, s))
    print('E1 start: translate %.2f, %.2f scale %.5f puts her head on the small circle' % (tx, ty, s))


def check_files(boards):
    for a, b in ((os.path.join(ROUND8, 'r6.css'), os.path.join(ROUND9, 'r6.css')), (os.path.join(SRC8, 'face-mary.svg'), os.path.join(HERE, 'face-mary.svg')),
                 (os.path.join(SRC8, 'face-sam.svg'), os.path.join(HERE, 'face-sam.svg'))):
        if not filecmp.cmp(a, b, shallow=False):
            fail('%s is not a byte-identical copy' % os.path.basename(b))
    names = {f[:-len('.dc.html')] for f in os.listdir(ROUND9) if f.endswith('.dc.html')}
    want = {b['stem'] for b in boards}
    if names != want or want != set(BUTTONS):
        fail('boards differ: %s' % sorted((names ^ want) | (want ^ set(BUTTONS))))
    canvas = json.load(open(os.path.join(ROUND9, 'canvas.json'), encoding='utf-8'))
    for file in canvas['boards']:
        if not os.path.exists(os.path.join(ROUND9, file)):
            fail('canvas: %s is missing' % file)
    if {f[:-len('.dc.html')] for f in canvas['boards']} != want or sorted(canvas['order']) != sorted(canvas['boards']):
        fail('canvas.json boards differ from the list')
    if canvas['title'] != 'Mary round 9: she comes along':
        fail('canvas title')
    for c in canvas['boards'].values():
        if (c['w'], c['h']) != (1280, 800) or c['x'] % 1360:
            fail('canvas: board size or spacing')
    print('files: r6.css and faces identical; canvas: %d boards, %d rows, every file exists' % (len(canvas['boards']), len(canvas['notes'])))
    readme = os.path.join(ROUND9, 'README.md')
    if os.path.exists(readme):
        text = open(readme, encoding='utf-8').read()
        for b in boards:
            if b['aloud'] and b['aloud'] not in text:
                fail('README: missing the full line of %s' % b['stem'])
            if b['stem'] not in text:
                fail('README: missing %s' % b['stem'])
    else:
        fail('README.md is missing')


if __name__ == '__main__':
    built = build.make_boards()
    check_boards(built)
    check_layout(built)
    check_fit(built)
    check_contrast()
    sheet = check_css(built)
    check_face(sheet)
    check_files(built)
    print('OK' if not fails else '%d FAILED' % len(fails))
    sys.exit(1 if fails else 0)
