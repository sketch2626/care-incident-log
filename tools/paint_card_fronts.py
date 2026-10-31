#!/usr/bin/env python3
"""Paints the twelve card fronts of the messages skill (M15b). Not bundled: the app only reads what it writes.

Writes skills/messages/assets/fronts/<key>.svg and skills/messages/assets/fronts.json. Stdlib only and seeded, so a
rerun gives the same art. python tools/paint_card_fronts.py paints; add --check to test what is on disk (exits 1 on
any problem). The helpers and the four approved birthday scenes are copied unchanged from
mockups/mary/round8-src/paint.py; the root svg loses its class and the fillable line becomes <!--LINE-->.

Every front is one <svg viewBox="0 0 500 700"> with ids prefixed per card, so several can sit on one page. Lettering
stays at 50 units or more, because a card shows at scale .4 on the picker board and nothing on screen goes under 20px."""
import json
import math
import os
import random
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, 'skills', 'messages', 'assets')
FRONTS_DIR = os.path.join(ASSETS, 'fronts')
LIST_FILE = os.path.join(ASSETS, 'fronts.json')
METRICS = os.path.join(ASSETS, 'metrics.json')
SCRIPT = "'Pinyon Script','Edwardian Script ITC','Palace Script MT','Monotype Corsiva','Segoe Script',cursive"
CAPS = "'Cinzel','Trajan Pro','Times New Roman',serif"
GARAMOND = "'EB Garamond',Garamond,'Times New Roman',serif"


def n(x):
    s = '%.1f' % x
    return s[:-2] if s.endswith('.0') else s


def smooth(pts, closed=False):
    """Catmull-Rom through the points, written as cubic Beziers."""
    c = len(pts)

    def at(i):
        return pts[i % c] if closed else pts[max(0, min(c - 1, i))]

    d = ['M%s %s' % (n(pts[0][0]), n(pts[0][1]))]
    for i in range(c if closed else c - 1):
        a, b, e, g = at(i - 1), at(i), at(i + 1), at(i + 2)
        d.append('C%s %s %s %s %s %s' % (
            n(b[0] + (e[0] - a[0]) / 6), n(b[1] + (e[1] - a[1]) / 6),
            n(e[0] - (g[0] - b[0]) / 6), n(e[1] - (g[1] - b[1]) / 6),
            n(e[0]), n(e[1])))
    if closed:
        d.append('Z')
    return ''.join(d)


def poly(pts):
    return 'M' + 'L'.join('%s %s' % (n(x), n(y)) for x, y in pts) + 'Z'


def lin(id_, stops, x1=0, y1=0, x2=0, y2=1, user=False):
    u = ' gradientUnits="userSpaceOnUse"' if user else ''
    return '<linearGradient id="%s" x1="%s" y1="%s" x2="%s" y2="%s"%s>%s</linearGradient>' % (
        id_, x1, y1, x2, y2, u, stop_list(stops))


def rad(id_, stops, cx=.5, cy=.5, r=.5, user=False, extra=''):
    u = ' gradientUnits="userSpaceOnUse"' if user else ''
    return '<radialGradient id="%s" cx="%s" cy="%s" r="%s"%s%s>%s</radialGradient>' % (
        id_, cx, cy, r, u, extra, stop_list(stops))


def stop_list(stops):
    out = []
    for s in stops:
        a = ' stop-opacity="%s"' % s[2] if len(s) > 2 else ''
        out.append('<stop offset="%s" stop-color="%s"%s></stop>' % (s[0], s[1], a))
    return ''.join(out)


def blur(id_, std):
    return ('<filter id="%s" x="-60%%" y="-60%%" width="220%%" height="220%%" color-interpolation-filters="sRGB">'
            '<feGaussianBlur stdDeviation="%s"></feGaussianBlur></filter>' % (id_, std))


def paper(p, seed, tooth=.42):
    """Over everything: the fine tooth of good card stock, lit from the upper left."""
    return ('<filter id="%s-paper" filterUnits="userSpaceOnUse" x="0" y="0" width="500" height="700" color-interpolation-filters="sRGB">'
            '<feTurbulence type="fractalNoise" baseFrequency=".95" numOctaves="3" seed="%d" result="t"></feTurbulence>'
            '<feDiffuseLighting in="t" surfaceScale="%s" diffuseConstant="1.155" lighting-color="#ffffff" result="l"><feDistantLight azimuth="225" elevation="60"></feDistantLight></feDiffuseLighting>'
            '<feBlend in="SourceGraphic" in2="l" mode="multiply"></feBlend>'
            '</filter>' % (p, seed, tooth))


def wash(p, seed, w=.8):
    """Over the painted part: slow blooms of pigment, multiply, nearly neutral in hue."""
    lift = round(1 - w * .5, 3)
    mid, rest = round(w * .84, 3), round(w * .16, 3)
    return ('<filter id="%s-wash" filterUnits="userSpaceOnUse" x="0" y="0" width="500" height="700" color-interpolation-filters="sRGB">'
            '<feTurbulence type="fractalNoise" baseFrequency=".009 .014" numOctaves="5" seed="%d" result="w"></feTurbulence>'
            '<feColorMatrix in="w" type="matrix" values="%s 0 0 0 %s  %s %s 0 0 %s  %s 0 %s 0 %s  0 0 0 0 1" result="m"></feColorMatrix>'
            '<feBlend in="SourceGraphic" in2="m" mode="multiply"></feBlend>'
            '</filter>' % (p, seed, w, lift, mid, rest, lift, mid, rest, lift))


def rim(id_, dx, dy, rgb, op):
    """Light caught along the upper edges of a dark shape, whatever its parts."""
    return ('<filter id="%s" x="-20%%" y="-20%%" width="140%%" height="140%%" color-interpolation-filters="sRGB">'
            '<feOffset in="SourceAlpha" dx="%s" dy="%s" result="o"></feOffset>'
            '<feComposite in="SourceAlpha" in2="o" operator="out" result="e"></feComposite>'
            '<feGaussianBlur in="e" stdDeviation=".6" result="b"></feGaussianBlur>'
            '<feColorMatrix in="b" type="matrix" values="0 0 0 0 %s  0 0 0 0 %s  0 0 0 0 %s  0 0 0 %s 0" result="c"></feColorMatrix>'
            '<feComposite in="c" in2="SourceAlpha" operator="in" result="r"></feComposite>'
            '<feMerge><feMergeNode in="SourceGraphic"></feMergeNode><feMergeNode in="r"></feMergeNode></feMerge>'
            '</filter>' % (id_, dx, dy, rgb[0], rgb[1], rgb[2], op))


def rock(id_, seed, freq='.016 .058', relief=11):
    """Stone relief, lit from the low sky on the left, multiplied into a crag shape."""
    return ('<filter id="%s" filterUnits="userSpaceOnUse" x="-10" y="-10" width="520" height="730" color-interpolation-filters="sRGB">'
            '<feTurbulence type="fractalNoise" baseFrequency="%s" numOctaves="6" seed="%d" result="t"></feTurbulence>'
            '<feDiffuseLighting in="t" surfaceScale="%s" diffuseConstant="1.6" lighting-color="#ffffff" result="l"><feDistantLight azimuth="196" elevation="38"></feDistantLight></feDiffuseLighting>'
            '<feBlend in="SourceGraphic" in2="l" mode="multiply" result="m"></feBlend>'
            '<feComposite in="m" in2="SourceGraphic" operator="in"></feComposite>'
            '</filter>' % (id_, freq, seed, relief))


def crag(r, pts, rough=.16, depth=4):
    """Midpoint displacement: turns a plain outline into a broken, angular edge."""
    for _ in range(depth):
        out = []
        for i, a in enumerate(pts):
            b = pts[(i + 1) % len(pts)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            k = r.uniform(-rough, rough)
            out += [a, ((a[0] + b[0]) / 2 - dy * k, (a[1] + b[1]) / 2 + dx * k)]
        pts = out
    return pts


def wc(id_, warp=10, freq='.02 .03', fine=2.5, edge=.8, eb=5, tint=(0, 0, 0), seed=1):
    """Watercolor wash edge: wandering outline, rough fringe, pigment pooled at the rim."""
    return ('<filter id="%s" filterUnits="userSpaceOnUse" x="-10" y="-10" width="520" height="720" color-interpolation-filters="sRGB">'
            '<feTurbulence type="fractalNoise" baseFrequency="%s" numOctaves="4" seed="%d"></feTurbulence>'
            '<feColorMatrix type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0 1" result="a"></feColorMatrix>'
            '<feDisplacementMap in="SourceGraphic" in2="a" scale="%s" xChannelSelector="R" yChannelSelector="G" result="b"></feDisplacementMap>'
            '<feTurbulence type="fractalNoise" baseFrequency=".24" numOctaves="2" seed="%d"></feTurbulence>'
            '<feColorMatrix type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0 1" result="c"></feColorMatrix>'
            '<feDisplacementMap in="b" in2="c" scale="%s" xChannelSelector="G" yChannelSelector="R" result="d"></feDisplacementMap>'
            '<feGaussianBlur in="d" stdDeviation="%s" result="e"></feGaussianBlur>'
            '<feColorMatrix in="e" type="matrix" values="0 0 0 0 %s  0 0 0 0 %s  0 0 0 0 %s  0 0 0 -%s %s" result="f"></feColorMatrix>'
            '<feComposite in="f" in2="d" operator="in" result="g"></feComposite>'
            '<feMerge><feMergeNode in="d"></feMergeNode><feMergeNode in="g"></feMergeNode></feMerge>'
            '</filter>' % (id_, freq, seed, warp, seed + 1, fine, eb, tint[0], tint[1], tint[2], edge, edge))


def cloud(id_, freq, gain, cut, seed, soft='1 .6'):
    """Long painted cloud: noise becomes the alpha of whatever gradient fills the rect."""
    return ('<filter id="%s" filterUnits="userSpaceOnUse" x="0" y="0" width="500" height="700" color-interpolation-filters="sRGB">'
            '<feTurbulence type="fractalNoise" baseFrequency="%s" numOctaves="5" seed="%d"></feTurbulence>'
            '<feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  %s 0 0 0 -%s" result="m"></feColorMatrix>'
            '<feComposite in="SourceGraphic" in2="m" operator="in"></feComposite>'
            '<feGaussianBlur stdDeviation="%s"></feGaussianBlur>'
            '</filter>' % (id_, freq, seed, gain, cut, soft))


def ripple(id_, freq, scale, seed):
    return ('<filter id="%s" filterUnits="userSpaceOnUse" x="0" y="0" width="500" height="700" color-interpolation-filters="sRGB">'
            '<feTurbulence type="fractalNoise" baseFrequency="%s" numOctaves="3" seed="%d"></feTurbulence>'
            '<feColorMatrix type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0 1" result="n"></feColorMatrix>'
            '<feDisplacementMap in="SourceGraphic" in2="n" scale="%s" xChannelSelector="R" yChannelSelector="B"></feDisplacementMap>'
            '<feGaussianBlur stdDeviation="1.2 .5"></feGaussianBlur>'
            '</filter>' % (id_, freq, seed, scale))


def foil(p, x1=40, y1=60, x2=460, y2=240):
    return lin(p + '-foil', [(0, '#8c6518'), (.14, '#d2a94e'), (.27, '#fff2bd'), (.4, '#c99b3b'),
                             (.55, '#a67a22'), (.68, '#f8e6a6'), (.82, '#c49a3e'), (1, '#855d14')],
               x1, y1, x2, y2, user=True)


def foil_line(p, text, x, y, size, anchor='middle', family=SCRIPT, edge='#241504', extra=''):
    a = 'x="%s" y="%s" font-family="%s" font-size="%s" text-anchor="%s"%s' % (x, y, family, size, anchor, extra)
    return ('<text %s fill="#000000" fill-opacity=".6" transform="translate(1.4 2.2)" filter="url(#%s-soft)">%s</text>'
            '<text %s fill="url(#%s-foil)" stroke="%s" stroke-width=".8" paint-order="stroke">%s</text>'
            % (a, p, text, a, p, edge, text))


def engraved(p, text, x, y, size=50, anchor='middle', family=CAPS, fill='#ecdcb0', spacing=3, caps=False):
    extra = ' letter-spacing="%s"' % spacing if spacing else ''
    if caps:
        extra += ' font-variant="small-caps"'
    a = 'x="%s" y="%s" font-family="%s" font-size="%s" text-anchor="%s"%s' % (x, y, family, size, anchor, extra)
    return ('<text %s fill="#000000" fill-opacity=".6" transform="translate(1 1.6)" filter="url(#%s-soft)">%s</text>'
            '<text %s fill="%s">%s</text>' % (a, p, text, a, fill, text))


def ridge(r, x0, x1, base, amp, step=12):
    waves = [(r.uniform(.004, .011), r.uniform(0, 6.3), 1), (r.uniform(.013, .024), r.uniform(0, 6.3), .5),
             (r.uniform(.03, .06), r.uniform(0, 6.3), .22), (r.uniform(.08, .15), r.uniform(0, 6.3), .1)]
    pts, x = [], x0
    while x <= x1 + step:
        pts.append((x, base - amp * sum(a * math.sin(fr * x + ph) for fr, ph, a in waves)))
        x += step
    return pts


def land(pts, bottom):
    return smooth(pts) + 'L%s %sL%s %sZ' % (n(pts[-1][0]), n(bottom), n(pts[0][0]), n(bottom))


def pine(r, x, base, h, w):
    """One conifer: a thin spire, then drooping boughs that widen downward."""
    tiers = max(6, int(h / 6.5))
    left, right = [(x, base - h)], []
    for i in range(1, tiers + 1):
        t = i / tiers
        y = base - h + h * t
        half = w / 2 * t ** .92 * r.uniform(.68, 1.14)
        drop = h / tiers * .6
        left += [(x - half, y + drop * r.uniform(.3, 1)), (x - half * .44, y + drop * .1)]
        right += [(x + half * r.uniform(.9, 1.1), y + drop * r.uniform(.3, 1)), (x + half * .44, y + drop * .1)]
    outline = left + [(x - w * .1, base + 4), (x + w * .1, base + 4)]
    for i in range(len(right) - 2, -2, -2):
        outline += [right[i + 1], right[i]] if i >= 0 else []
    return poly(outline)


def blade(x, y, h, lean, w):
    """One blade of grass or reed, tapered to a tip and bent by the wind."""
    return ('M%s %sQ%s %s %s %sQ%s %s %s %sZ' % (
        n(x), n(y), n(x + lean * .25), n(y - h * .62), n(x + lean), n(y - h),
        n(x + lean * .25 + w * .8), n(y - h * .6), n(x + w), n(y)))


def lens(x, y, length, h):
    return 'M%s %sQ%s %s %s %sQ%s %s %s %sZ' % (
        n(x), n(y), n(x + length / 2), n(y - h), n(x + length), n(y), n(x + length / 2), n(y + h), n(x), n(y))


def wrap(name, label, defs, art, lettering):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 700" role="img" aria-label="%s">\n'
            '<defs>\n%s\n</defs>\n%s\n%s\n</svg>\n' % (label, '\n'.join(defs), '\n'.join(art), '\n'.join(lettering)))


# ---- 1. Lake at dawn ---------------------------------------------------------------

def boat_shapes():
    return ('<path d="M-52 -11Q-36 -3.4 -24 -2.4L46 -6.4L48 2.6Q10 8.6 -26 6Q-42 2.6 -52 -11Z"></path>'
            '<path d="M11 -4C9 -13 11 -23 15.4 -28C19.6 -30.4 24.4 -27.4 25.6 -20C26.4 -14 26.8 -9 26.8 -4Z"></path>'
            '<ellipse cx="18.4" cy="-33.2" rx="3.9" ry="4.4"></ellipse><path d="M10.6 -36Q18.4 -38.8 26.4 -35.8Q18.4 -34.8 10.6 -36Z"></path>'
            '<path d="M14.6 -36.6Q15 -41.6 18.6 -41.6Q22 -41.6 22.6 -36.6Z"></path>'
            '<path d="M17.4 -26.4L2.6 -17.6L1.6 -15.4L16.4 -22Z"></path>')


def lake():
    p = 'lk'
    r = random.Random(21)
    X0, Y0, X1, Y1, HZ = 34, 34, 466, 666, 462
    W_, H_ = X1 - X0, Y1 - Y0
    d = [
        lin(p + '-sky', [(0, '#0a1630'), (.3, '#132646'), (.52, '#26395b'), (.68, '#4a5671'), (.79, '#8b7f86'),
                         (.87, '#d3a378'), (.93, '#f4cf92'), (1, '#fdebc2')], 0, Y0, 0, HZ + 2, user=True),
        rad(p + '-glow', [(0, '#ffe2a8', .95), (.3, '#fbc985', .55), (1, '#f4a860', 0)]),
        lin(p + '-cl1', [(0, '#060e20', .95), (.55, '#0f1c38', .8), (1, '#2b3550', 0)], 0, 0, 0, 1),
        lin(p + '-cl2', [(0, '#5f5f7c', 0), (.4, '#8d7184', .7), (.8, '#e2a57f', .95), (1, '#f6cf98', .9)], 0, 0, 0, 1),
        lin(p + '-far', [(0, '#7f8ea8'), (1, '#d6c6b0')]),
        lin(p + '-far2', [(0, '#556886'), (1, '#b6a99f')]),
        lin(p + '-mid', [(0, '#22324e'), (1, '#6a6f7e')]),
        lin(p + '-water', [(0, '#fbe3b2'), (.07, '#e7bd8c'), (.17, '#8f8a96'), (.34, '#4b5c7d'), (.6, '#223552'), (1, '#0d1a31')],
            0, HZ, 0, Y1, user=True),
        rad(p + '-vig', [(.55, '#040a18', 0), (1, '#040a18', .72)], .5, .46, .8),
        lin(p + '-paint', [(0, '#10203a'), (1, '#0a1526')]),
        wc(p + '-wc', 9, '.02 .035', 2, .7, 4, (.02, .05, .12), 3),
        wc(p + '-wcf', 5, '.03 .05', 3, .4, 3, (.1, .13, .2), 9),
        wc(p + '-wcn', 4, '.05', 2.4, .5, 2, (0, .01, .04), 14),
        cloud(p + '-c1', '.0032 .03', 3.4, 1.55, 5, '1.4 .7'),
        cloud(p + '-c2', '.006 .05', 3.6, 1.5, 12, '.9 .5'),
        ripple(p + '-rip', '.01 .22', 13, 4),
        blur(p + '-b06', .6), blur(p + '-b1', 1), blur(p + '-b2', 2.2), blur(p + '-m', 9), blur(p + '-soft', 1.1),
        paper(p, 3), wash(p, 4),
        foil(p, 60, 90, 440, 260),
        '<clipPath id="%s-scene"><rect x="%d" y="%d" width="%d" height="%d"></rect></clipPath>' % (p, X0, Y0, W_, H_),
    ]
    # the far stands of pine; kept as shapes in defs so the water can reflect them
    right = ''.join(pine(r, x, HZ + 2, h, h * .42) for x, h in
                    [(474, 176), (446, 150), (458, 118), (424, 118), (402, 92), (436, 90), (384, 66), (368, 50), (350, 36)])
    left = ''.join(pine(r, x, HZ + 2, h, h * .44) for x, h in
                   [(26, 136), (50, 112), (72, 84), (40, 92), (92, 56), (108, 38), (122, 26)])
    d.append('<path id="%s-right" d="%s"></path><path id="%s-left" d="%s"></path>' % (p, right, p, left))

    midband = ''
    x = X0 - 10
    while x < X1 + 10:
        h = r.uniform(16, 34) * (1.25 - .55 * math.exp(-((x - 205) / 110) ** 2))
        midband += pine(r, x, HZ + 1, h, h * .55)
        x += r.uniform(6, 13)

    art = ['<rect width="500" height="700" fill="#f2e8d3"></rect>']
    s = ['<rect x="%d" y="%d" width="%d" height="%d" fill="url(#%s-sky)"></rect>' % (X0, Y0, W_, HZ - Y0 + 2, p)]
    s.append('<ellipse cx="205" cy="%d" rx="300" ry="120" fill="url(#%s-glow)"></ellipse>' % (HZ - 6, p))
    s.append('<rect x="%d" y="%d" width="%d" height="256" fill="url(#%s-cl1)" filter="url(#%s-c1)"></rect>' % (X0, Y0, W_, p, p))
    s.append('<rect x="%d" y="250" width="%d" height="190" fill="url(#%s-cl2)" filter="url(#%s-c2)"></rect>' % (X0, W_, p, p))
    # hills, each paler and bluer with distance
    s.append('<path d="%s" fill="url(#%s-far)" filter="url(#%s-wcf)" opacity=".9"></path>' % (land(ridge(r, X0 - 12, X1 + 12, 424, 13), HZ + 2), p, p))
    s.append('<ellipse cx="170" cy="438" rx="240" ry="9" fill="#f7dfb6" opacity=".6" filter="url(#%s-m)"></ellipse>' % p)
    s.append('<path d="%s" fill="url(#%s-far2)" filter="url(#%s-wcf)"></path>' % (land(ridge(r, X0 - 12, X1 + 12, 444, 9), HZ + 2), p, p))
    s.append('<path d="%s" fill="url(#%s-mid)" filter="url(#%s-wc)"></path>' % (midband, p, p))
    s.append('<ellipse cx="240" cy="456" rx="260" ry="8" fill="#f3dfbf" opacity=".7" filter="url(#%s-m)"></ellipse>' % p)
    # water, lit near the shore and going to deep navy at our feet
    s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="url(#%s-water)"></rect>' % (X0, HZ, W_, Y1 - HZ, p))
    # reflections of the stands
    refl = ('<g transform="translate(0 %d) scale(1 -1)">'
            '<use href="#%s-right" fill="#101d33"></use><use href="#%s-left" fill="#142440"></use></g>' % (2 * HZ, p, p))
    s.append('<g filter="url(#%s-rip)" opacity=".8">%s<path d="%s" transform="translate(0 %d) scale(1 -.7)" fill="#5a6078" opacity=".5"></path></g>'
             % (p, refl, midband, int(HZ * 1.7) + 1))
    # stands themselves
    s.append('<use href="#%s-right" fill="url(#%s-paint)" filter="url(#%s-wcn)"></use>' % (p, p, p))
    s.append('<use href="#%s-left" fill="#12213b" filter="url(#%s-wcn)"></use>' % (p, p))
    s.append('<ellipse cx="400" cy="460" rx="130" ry="6" fill="#d9cdbc" opacity=".35" filter="url(#%s-b2)"></ellipse>' % p)
    # light on the water, a broken path under the glow, then wind ripples
    glow = ''
    for i in range(34):
        t = (i / 34) ** 1.5
        y = HZ + 4 + (Y1 - HZ - 40) * t
        length = 34 + t * 150 * r.uniform(.5, 1)
        glow += lens(205 - length / 2 + r.uniform(-22, 22) * (1 + t), y, length, .8 + t * 2.1)
    s.append('<path d="%s" fill="#fbdca6" opacity=".62" filter="url(#%s-b1)"></path>' % (glow, p))
    pale, dark = '', ''
    for i in range(110):
        t = r.random() ** 1.5
        y = HZ + 5 + (Y1 - HZ - 5) * t
        length = r.uniform(18, 60) + t * 170
        x = r.uniform(X0 - 40, X1)
        if r.random() < .45:
            pale += lens(x, y, length, .5 + t * 2)
        else:
            dark += lens(x, y, length, .5 + t * 2.6)
    s.append('<path d="%s" fill="#9fb0c8" opacity=".3"></path>' % pale)
    s.append('<path d="%s" fill="#0a1527" opacity=".42"></path>' % dark)
    s.append('<ellipse cx="170" cy="590" rx="210" ry="11" fill="#c9cfdc" opacity=".14" filter="url(#%s-m)"></ellipse>' % p)
    # the boat, its reflection, its ring of still water
    bx, by = 312, 548
    s.append('<g filter="url(#%s-rip)" opacity=".62"><g transform="translate(%d %d) scale(1.16 -1.02)" fill="#070f1e">%s</g></g>' % (p, bx, by + 3, boat_shapes()))
    s.append('<g transform="translate(%d %d) scale(1.16)">'
             '<g fill="#070e1c">%s</g>'
             '<path d="M2 -16.5Q-26 -46 -68 -68" fill="none" stroke="#090f1c" stroke-width="1.2" stroke-linecap="round"></path>'
             '<path d="M-68 -68Q-77 -30 -82 4" fill="none" stroke="#0b1424" stroke-width=".8" opacity=".7"></path>'
             '<path d="M-51 -11Q-36 -4 -24 -3L45 -7" fill="none" stroke="#f0c48a" stroke-width=".9" opacity=".7"></path>'
             '<path d="M11.4 -5C9.6 -14 11.4 -23 15.4 -27.6" fill="none" stroke="#f0c48a" stroke-width=".8" opacity=".55"></path>'
             '</g>' % (bx, by, boat_shapes()))
    s.append('<path d="%s" fill="#c8c6c8" opacity=".3" filter="url(#%s-b1)"></path>' % (lens(bx - 96, by + 8, 150, 1.6) + lens(bx - 112, by + 4, 34, .9), p))
    # reeds close to us, framing the corners
    reeds = ''
    for i in range(38):
        side = r.random() < .62
        x = r.uniform(X0 - 6, 128) if side else r.uniform(392, X1 + 6)
        h = r.uniform(46, 150) * (1 - abs(x - (X0 if side else X1)) / 170)
        reeds += blade(x, Y1 + 6, h + 26, r.uniform(-22, 26), r.uniform(2, 4.4))
    s.append('<path d="%s" fill="#091323" filter="url(#%s-b06)"></path>' % (reeds, p))
    for cx, cy, a in [(70, 546, -6), (102, 582, 7), (438, 586, 9)]:
        s.append('<g transform="translate(%d %d) rotate(%d)"><rect x="-3.6" y="-16" width="7.2" height="33" rx="3.6" fill="#0b1220"></rect><rect x="-.5" y="16" width="1.5" height="90" fill="#060d1b"></rect><path d="M-3 -14L-3 13" stroke="#4d4354" stroke-width="1" opacity=".5"></path></g>' % (cx, cy, a))
    s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="url(#%s-vig)"></rect>' % (X0, Y0, W_, H_, p))
    art.append('<g filter="url(#%s-paper)"><rect width="500" height="700" fill="#f2e8d3"></rect><g clip-path="url(#%s-scene)"><g filter="url(#%s-wash)">%s</g></g></g>' % (p, p, p, '\n'.join(s)))

    rules = ('<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="#1a2438" stroke-width=".9" opacity=".7"></rect>'
             '<rect x="23.5" y="23.5" width="453" height="653" fill="none" stroke="url(#%s-foil)" stroke-width="1.6"></rect>' % (X0, Y0, W_, H_, p))
    words = [rules, foil_line(p, 'Happy', 250, 146, 100), foil_line(p, 'Birthday', 250, 238, 100),
             engraved(p, 'for my son', 250, 306)]
    return wrap('lake', 'Lake at dawn, one small boat', d, art, words)


# ---- 2. Buck at dusk ---------------------------------------------------------------

def tapered(pts, w0, w1):
    """A curve with a width that thins toward its tip, as one filled shape."""
    dense = []
    c = len(pts)
    for i in range(c - 1):
        a, b, e, g = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, c - 1)]
        for t in [j / 6 for j in range(6)]:
            q = []
            for k in (0, 1):
                q.append(.5 * (2 * b[k] + (e[k] - a[k]) * t + (2 * a[k] - 5 * b[k] + 4 * e[k] - g[k]) * t * t
                               + (3 * b[k] - a[k] - 3 * e[k] + g[k]) * t ** 3))
            dense.append(tuple(q))
    dense.append(pts[-1])
    left, right = [], []
    m = len(dense) - 1
    for i, q in enumerate(dense):
        a, b = dense[max(i - 1, 0)], dense[min(i + 1, m)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1
        w = (w0 + (w1 - w0) * i / m) / 2
        left.append((q[0] - dy / length * w, q[1] + dx / length * w))
        right.append((q[0] + dy / length * w, q[1] - dx / length * w))
    return poly(left + right[::-1])


def outline(*runs):
    """One closed shape from smooth runs; where two runs meet the corner stays sharp."""
    d = smooth(runs[0])
    for run in runs[1:]:
        s = smooth(run)
        d += s[s.index('C'):]
    return d + 'Z'


def fur(edge, r, dx, dy, gap=2.4):
    """Short hairs hanging off a drawn edge, one small wedge each."""
    out = ''
    for (ax, ay), (bx, by) in zip(edge, edge[1:]):
        c = max(1, int(math.hypot(bx - ax, by - ay) / gap))
        for j in range(c):
            t = (j + r.random() * .7) / c
            x, y, k = ax + (bx - ax) * t, ay + (by - ay) * t, r.uniform(.55, 1.2)
            out += 'M%s %sL%s %sL%s %sZ' % (n(x - 1.2), n(y - 1.2), n(x + dx * k), n(y + dy * k), n(x + 1.2), n(y - 1.2))
    return out


# A whitetail plotted by hand, facing left. Ground is y=300 and the withers stand at 146,
# so the leg below the chest is about as long as the chest is deep.
BUCK_LIT = [(70, 95), (80, 101), (91, 113), (102, 127), (112, 137), (122, 142), (134, 147), (150, 153), (170, 155),
            (190, 152), (208, 149), (226, 153), (241, 162), (251, 173)]
BUCK_BELLY = [(206, 199), (192, 206), (172, 213), (150, 218), (134, 220), (121, 220)]
BUCK_BRISKET = [(98, 226), (88, 221), (79, 212), (75, 201), (76, 189)]
BUCK_HIDE = [
    # nose, bridge, brow, poll
    [(29, 117), (29.5, 114), (32, 111.5), (39, 108.7), (47, 105), (53, 101.5), (61, 97), (70, 95)],
    # thick rut neck, withers, back, croup, buttock, down the thigh to the point of the hock
    BUCK_LIT + [(256, 186), (256, 200), (253, 214), (249, 227), (249, 235), (254, 242)],
    # back of the hind cannon, fetlock, heel, hoof
    [(254, 242), (251, 250), (249, 262), (248, 276), (248.5, 285), (246, 292), (245, 299)],
    [(245, 299), (235, 300)],
    # front of the hind leg, hock, gaskin, stifle, up into the flank
    [(235, 300), (238, 292), (241, 284), (241, 270), (242, 256), (240, 246), (233, 235), (222, 224), (213, 213), (206, 199)],
    # belly, deep at the girth and tucked at the flank
    BUCK_BELLY,
    # back of the forearm, knee, cannon, heel, hoof
    [(121, 220), (116, 236), (113.5, 246), (112.5, 251), (114, 257), (112, 264), (111, 276), (111, 285), (109, 292), (107.5, 299)],
    [(107.5, 299), (96, 300)],
    # front of the foreleg, knee, forearm, up into the brisket and the point of the breast
    [(96, 300), (99, 292), (102, 284), (103.5, 272), (103.5, 264), (101.5, 257), (102, 251), (103, 245), (102, 236)] + BUCK_BRISKET,
    # swollen throat
    [(76, 189), (72, 177), (67, 162), (62, 146), (58.5, 131)],
    # jaw, chin, lip
    [(58.5, 131), (57, 127), (50, 125), (42, 123), (35, 121.5), (31.5, 120.5), (30, 119), (29, 117)],
]
BUCK_EAR_NEAR = [[(67, 97), (75, 91), (84, 88), (92, 88), (95, 90), (90, 96), (83, 102), (76, 107), (67, 97)]]
BUCK_EAR_FAR = [[(71, 96), (75, 87), (81, 78), (88, 71), (91, 72), (91, 80), (87, 90), (82, 100), (71, 96)]]
BUCK_TAIL = [[(238, 160), (249, 164), (258, 176), (262, 190), (263, 197)], [(263, 197), (257, 193), (251, 184), (244, 174)], [(244, 174), (238, 160)]]
BUCK_LEGS_FAR = [
    # foreleg reaching a little ahead
    [[(114, 212), (106, 232), (99, 246), (96, 254), (93, 264), (89, 278), (86.5, 287), (85, 293), (83.5, 299)],
     [(83.5, 299), (73, 300)],
     [(73, 300), (76.5, 292), (80, 283), (83, 270), (86, 258), (86, 252), (87, 242), (88, 228), (88, 208)],
     [(88, 208), (114, 212)]],
    # hind leg set forward under him
    [[(238, 190), (230, 220), (225, 233), (227, 240), (231, 245)],
     [(231, 245), (227, 254), (222, 268), (218, 282), (216, 289), (213, 295), (212, 299)],
     [(212, 299), (202, 300)],
     [(202, 300), (206, 292), (210, 285), (213, 272), (216, 258), (217, 248), (212, 240), (203, 228), (193, 216), (187, 194)],
     [(187, 194), (238, 190)]],
]
# Eight points: on each side a main beam, a brow tine and two tines rising off the beam. His head
# is turned a touch toward us and we look up from the field, so the far side sits forward and lower.
BUCK_RACK_NEAR = [
    ([(58, 97), (68, 87), (74, 75), (73, 64), (63, 57), (49, 53), (34, 51), (19, 44)], 8.8, 3),
    ([(62, 94), (63, 83), (65, 72)], 5, 1.3),
    ([(73, 65), (73, 48), (69, 25)], 6.6, 1.4),
    ([(52, 55), (50, 39), (45, 24)], 6, 1.4),
]
BUCK_RACK_FAR = [
    ([(54, 98), (58, 89), (56, 79), (46, 72), (32, 68), (18, 66), (5, 59)], 7.2, 2.6),
    ([(55, 96), (49, 88), (47, 78)], 4.2, 1.1),
    ([(46, 73), (41, 56), (34, 39)], 5.2, 1.2),
    ([(22, 68), (18, 54), (12, 41)], 4.8, 1.2),
]


def buck_shape():
    near = [outline(*BUCK_EAR_NEAR), outline(*BUCK_TAIL)]
    far = [outline(*leg) for leg in BUCK_LEGS_FAR] + [outline(*BUCK_EAR_FAR)]
    near += [tapered(*b) for b in BUCK_RACK_NEAR]
    far += [tapered(*b) for b in BUCK_RACK_FAR]
    hair = random.Random(8)
    near += [fur(BUCK_BELLY, hair, 2, 2.8), fur(BUCK_BRISKET, hair, -1.2, 2.8)]
    return outline(*BUCK_HIDE), near, far


def canopy(r, x0, x1, top_at, base, step=15):
    """A broadleaf wood: a bumpy crown line closed down to the base."""
    pts = [(x0, base)]
    x = x0
    while x <= x1:
        y = top_at(x)
        pts.append((x, y - r.uniform(0, 12)))
        pts.append((x + step * .5, y + r.uniform(4, 14)))
        x += step * r.uniform(.7, 1.3)
    pts.append((x1, base))
    return smooth(pts) + 'Z'


def buck():
    p = 'bk'
    r = random.Random(52)
    HZ = 414
    d = [
        lin(p + '-sky', [(0, '#34352b'), (.16, '#4a4939'), (.34, '#736c54'), (.54, '#a49771'), (.72, '#d0bb85'),
                         (.87, '#ecd7a0'), (1, '#f8ebc0')], 0, 0, 0, HZ, user=True),
        rad(p + '-glow', [(0, '#fff0bd', .95), (.45, '#f1d48f', .42), (1, '#d6a964', 0)]),
        lin(p + '-cl1', [(0, '#1c1d15', .9), (.55, '#2f2d21', .62), (1, '#4a4432', 0)]),
        lin(p + '-cl2', [(0, '#5d5540', 0), (.45, '#74674a', .6), (1, '#b98a4e', .6)]),
        lin(p + '-hill', [(0, '#9a9d84'), (1, '#d8cca0')]),
        lin(p + '-band', [(0, '#55654f'), (1, '#928f6c')]),
        lin(p + '-wood', [(0, '#1c2e22'), (.7, '#17261c'), (1, '#2c382b')], 0, 100, 0, 424, user=True),
        lin(p + '-field', [(0, '#d9bd7a'), (.08, '#ab9458'), (.22, '#6c6a3c'), (.42, '#343b24'), (.68, '#171d12'), (1, '#0a0e09')],
            0, HZ, 0, 700, user=True),
        lin(p + '-coat', [(0, '#1a120b'), (.55, '#140e08'), (1, '#0f0a06')], 0, 60, 0, 300, user=True),
        lin(p + '-foot', [(0, '#0a0e09', 0), (.42, '#0a0e09', .74), (1, '#060906', .97)]),
        rad(p + '-vig', [(.52, '#070a06', 0), (1, '#070a06', .74)], .5, .44, .84),
        wc(p + '-wc', 3, '.03 .05', 1.6, .55, 3, (.02, .04, .02), 6),
        wc(p + '-wcf', 5, '.03 .05', 2.4, .4, 3, (.2, .2, .13), 17),
        wc(p + '-wcn', 1.6, '.06', 1.1, .3, 2, (.01, .01, 0), 24),
        cloud(p + '-c1', '.0036 .032', 3.5, 1.78, 8, '1.8 1'),
        cloud(p + '-c2', '.007 .05', 3.6, 1.7, 15, '1 .6'),
        blur(p + '-b1', .7), blur(p + '-b2', 2.4), blur(p + '-b6', 6), blur(p + '-m', 11), blur(p + '-soft', 1.1),
        paper(p, 11), wash(p, 12),
        foil(p, 30, 540, 470, 620),
    ]
    a = []
    a.append('<rect width="500" height="%d" fill="url(#%s-sky)"></rect>' % (HZ + 2, p))
    a.append('<ellipse cx="270" cy="%d" rx="330" ry="170" fill="url(#%s-glow)"></ellipse>' % (HZ - 24, p))
    a.append('<rect width="500" height="210" fill="url(#%s-cl1)" filter="url(#%s-c1)"></rect>' % (p, p))
    a.append('<rect y="170" width="500" height="170" fill="url(#%s-cl2)" filter="url(#%s-c2)"></rect>' % (p, p))
    # far hills and a pale band of trees across the field
    a.append('<path d="%s" fill="url(#%s-hill)" filter="url(#%s-wcf)"></path>' % (land(ridge(r, -12, 512, 384, 11), HZ + 2), p, p))
    a.append('<path d="%s" fill="url(#%s-band)" filter="url(#%s-wcf)"></path>'
             % (canopy(r, -12, 512, lambda x: 398 + 6 * math.sin(x * .016), HZ + 2, 11), p, p))
    a.append('<ellipse cx="320" cy="%d" rx="280" ry="8" fill="#f8e8bc" opacity=".66" filter="url(#%s-m)"></ellipse>' % (HZ - 3, p))
    # the wood: stands of pine, tall on the left and low on the right, open where his head meets the light
    def stand(x0, x1, env, step, wide):
        path, x = '', x0
        while x < x1:
            h = env(x) * r.uniform(.82, 1.12)
            path += pine(r, x, HZ + 6, h, h * wide)
            x += step * r.uniform(.7, 1.3)
        return path
    left = lambda x: 40 + 300 * max(0, 1 - (x + 10) / 214) ** 1.05
    right = lambda x: 44 + 210 * max(0, (x - 424) / 86) ** 1.2
    a.append('<path d="%s" fill="#47584a" opacity=".82" filter="url(#%s-wc)"></path>' % (stand(-6, 222, lambda x: left(x) * .9, 13, .3) + stand(420, 510, lambda x: right(x) * .9, 12, .3), p))
    a.append('<path d="%s" fill="url(#%s-wood)" filter="url(#%s-wc)"></path>' % (stand(-14, 190, left, 19, .34) + stand(436, 514, right, 17, .34), p, p))
    under = canopy(r, -14, 150, lambda x: 372 + x * .24, HZ + 8, 16)
    under2 = canopy(r, 446, 514, lambda x: 392 - (x - 446) * .2, HZ + 8, 14)
    a.append('<path d="%s" fill="#101b13" filter="url(#%s-wc)"></path><path d="%s" fill="#101b13" filter="url(#%s-wc)"></path>' % (under, p, under2, p))
    a.append('<rect y="%d" width="500" height="%d" fill="url(#%s-field)"></rect>' % (HZ, 700 - HZ, p))
    a.append('<ellipse cx="290" cy="%d" rx="300" ry="7" fill="#f7e6b6" opacity=".42" filter="url(#%s-m)"></ellipse>' % (HZ + 2, p))
    # field grasses thickening toward us
    dabs = ['', '', '']
    for i in range(210):
        t = r.random() ** 1.3
        y = HZ + 8 + 96 * t
        k = 0 if t < .3 else (1 if t < .7 else 2)
        dabs[k] += blade(r.uniform(-10, 510), y, 3 + t * 20, r.uniform(-5, 6), .9 + t * 1.7)
    for k, col in enumerate(['#8f7f4b', '#56542f', '#2d3420']):
        a.append('<path d="%s" fill="%s" opacity=".8"></path>' % (dabs[k], col))
    # the buck: near black against the glow, with light only along his back and neck
    hide, near, far = buck_shape()
    bx, by, sc = 184, 202, .96
    d.append('<clipPath id="%s-buck"><path d="%s"></path></clipPath>' % (p, hide))
    a.append('<ellipse cx="%d" cy="%d" rx="136" ry="9" fill="#0d110a" opacity=".6" filter="url(#%s-b6)"></ellipse>' % (bx + sc * 150, by + sc * 300, p))
    a.append('<g filter="url(#%s-wcn)"><g transform="translate(%d %d) scale(%s)">'
             '<g fill="#211810">%s</g><g fill="url(#%s-coat)">%s<path d="%s"></path></g>' % (
                 p, bx, by, sc, ''.join('<path d="%s"></path>' % x for x in far), p,
                 ''.join('<path d="%s"></path>' % x for x in near), hide))
    a.append('<g clip-path="url(#{0}-buck)">'
             '<ellipse cx="102" cy="180" rx="18" ry="34" transform="rotate(14 102 180)" fill="#5c4229" opacity=".18" filter="url(#{0}-b6)"></ellipse>'
             '<ellipse cx="226" cy="190" rx="24" ry="33" transform="rotate(-12 226 190)" fill="#5c4229" opacity=".2" filter="url(#{0}-b6)"></ellipse>'
             '<ellipse cx="92" cy="148" rx="12" ry="30" transform="rotate(-34 92 148)" fill="#523a24" opacity=".14" filter="url(#{0}-b6)"></ellipse>'
             '<ellipse cx="160" cy="178" rx="32" ry="14" fill="#4a3522" opacity=".1" filter="url(#{0}-b6)"></ellipse>'
             '<path d="M122 150Q140 188 120 220" fill="none" stroke="#080503" stroke-width="5" opacity=".3" filter="url(#{0}-b6)"></path>'
             '<path d="M204 152Q190 180 208 204" fill="none" stroke="#080503" stroke-width="5" opacity=".26" filter="url(#{0}-b6)"></path>'
             '<path d="{1}" fill="none" stroke="#f3d391" stroke-width="1.9" opacity=".8" filter="url(#{0}-b1)"></path>'
             '</g></g></g>'.format(p, smooth(BUCK_LIT)))
    # a few blades of his own right at the feet, seeded apart so the field stays as it was
    tuft = random.Random(3)
    tufts = ['', '']
    for fx in (78, 102, 207, 240):
        for i in range(8):
            tufts[i % 2] += blade(bx + sc * fx + tuft.uniform(-12, 12), by + sc * 300 + tuft.uniform(2, 9), tuft.uniform(15, 28), tuft.uniform(-6, 6), 1.4)
    for k, col in enumerate(['#3f4027', '#6b6138']):
        a.append('<path d="%s" fill="%s" filter="url(#%s-b1)"></path>' % (tufts[k], col, p))
    # grass over his feet, then the dark foreground
    near = ['', '', '']
    for i in range(380):
        t = r.random()
        y = 476 + 244 * t
        k = 0 if t < .24 else (1 if t < .55 else 2)
        h = 34 + 76 * t * r.uniform(.6, 1.1)
        near[k] += blade(r.uniform(-14, 514), y, h, r.uniform(-16, 18), 2.3 + 2.6 * t)
    for k, col in enumerate(['#44432a', '#262c1c', '#111710']):
        a.append('<path d="%s" fill="%s" filter="url(#%s-b1)"></path>' % (near[k], col, p))
    lit = ''
    for i in range(46):
        lit += blade(r.uniform(150, 500), r.uniform(478, 512), r.uniform(20, 46), r.uniform(-10, 10), 1.3)
    a.append('<path d="%s" fill="#cdab6b" opacity=".7"></path>' % lit)
    a.append('<rect y="516" width="500" height="184" fill="url(#%s-foot)"></rect>' % p)
    a.append('<rect width="500" height="700" fill="url(#%s-vig)"></rect>' % p)
    art = ['<g filter="url(#%s-paper)"><g filter="url(#%s-wash)">%s</g></g>' % (p, p, '\n'.join(a))]
    words = [foil_line(p, 'Happy Birthday', 250, 604, 82),
             engraved(p, 'to a fine son', 250, 664, 50, family=GARAMOND, caps=True, spacing=2)]
    return wrap('buck', 'A buck at the edge of a field at dusk', d, art, words)


# ---- 3. Lighthouse -----------------------------------------------------------------

def lighthouse():
    p = 'lh'
    r = random.Random(77)
    HZ = 474
    d = [
        lin(p + '-sky', [(0, '#29060f'), (.18, '#3f0d1c'), (.38, '#591b2d'), (.56, '#60303f'), (.72, '#5c4d5d'), (.86, '#64717e'), (1, '#9aa8aa')],
            0, 0, 0, HZ, user=True),
        rad(p + '-glow', [(0, '#ecdac6', .72), (.5, '#b89aa0', .3), (1, '#8a7a8c', 0)]),
        lin(p + '-cl1', [(0, '#1b040b', .9), (.6, '#2e0813', .7), (1, '#44101f', 0)]),
        lin(p + '-cl2', [(0, '#3a2a3c', 0), (.5, '#4a3b4c', .8), (1, '#8d9299', .62)]),
        lin(p + '-sea', [(0, '#97a6aa'), (.08, '#6d7a84'), (.26, '#465060'), (.55, '#2b2e40'), (1, '#120f1a')], 0, HZ, 0, 700, user=True),
        lin(p + '-tower', [(0, '#f6ece0'), (.38, '#ded0c6'), (.72, '#918c98'), (1, '#5a5764')], 0, 0, 1, 0),
        lin(p + '-roof', [(0, '#4e2230'), (1, '#1d0c14')], 0, 0, 1, 0),
        lin(p + '-house', [(0, '#c4b4ae'), (1, '#6d6673')], 0, 0, 1, 0),
        lin(p + '-beam', [(0, '#ffeec8', .24), (.5, '#f7e6c6', .08), (1, '#efdec6', 0)], 1, 0, 0, 0),
        lin(p + '-beam2', [(0, '#ffeec8', .2), (1, '#efdec6', 0)], 0, 0, 1, 0),
        rad(p + '-lamp', [(0, '#fff8df', .95), (.3, '#ffe39a', .55), (1, '#f4c370', 0)]),
        rad(p + '-vig', [(.5, '#0e0408', 0), (1, '#0e0408', .7)], .5, .46, .82),
        wc(p + '-wcb', 1.4, '.06', .7, .3, 2, (.05, .02, .06), 31),
        wc(p + '-wcr', 2, '.05', 1, .55, 3, (.03, .01, .03), 35),
        rock(p + '-r1', 5),
        rock(p + '-r2', 19, '.02 .066', 12),
        rock(p + '-r3', 27, '.014 .05', 14),
        cloud(p + '-c1', '.0034 .03', 3.6, 1.55, 18, '1.6 .8'),
        cloud(p + '-c2', '.006 .045', 3.4, 1.5, 22, '1 .6'),
        ripple(p + '-rip', '.012 .2', 12, 8),
        blur(p + '-b06', .6), blur(p + '-b1', 1), blur(p + '-b2', 2), blur(p + '-b5', 5), blur(p + '-m', 10), blur(p + '-soft', 1.1),
        paper(p, 23), wash(p, 24),
        foil(p, 30, 40, 340, 230),
    ]
    a = []
    a.append('<rect width="500" height="%d" fill="url(#%s-sky)"></rect>' % (HZ + 2, p))
    a.append('<ellipse cx="130" cy="%d" rx="290" ry="120" fill="url(#%s-glow)"></ellipse>' % (HZ - 6, p))
    a.append('<rect width="500" height="290" fill="url(#%s-cl1)" filter="url(#%s-c1)"></rect>' % (p, p))
    a.append('<rect y="270" width="500" height="190" fill="url(#%s-cl2)" filter="url(#%s-c2)"></rect>' % (p, p))
    a.append('<path d="%s" fill="#6f7a86" opacity=".66" filter="url(#%s-wcb)"></path>'
             % (land([(-10, 468), (40, 458), (84, 452), (130, 460), (176, 470), (210, HZ)], HZ + 1), p))
    # sea, swells, then the point's dark reflection
    a.append('<rect y="%d" width="500" height="%d" fill="url(#%s-sea)"></rect>' % (HZ, 700 - HZ, p))
    back = [(172, 512), (200, 494), (232, 476), (272, 462), (306, 444), (344, 430), (392, 424), (432, 414), (470, 402), (512, 392),
            (512, 574), (440, 560), (380, 548), (320, 540), (262, 530), (212, 522)]
    bd = poly(crag(r, back))
    a.append('<g filter="url(#%s-rip)" opacity=".62"><path d="%s" transform="translate(0 1120) scale(1 -1.02)" fill="#120c16"></path>'
             '<path d="M355 430H417L405 250H367Z" transform="translate(0 1110) scale(1 -1)" fill="#a7a4a8" opacity=".5"></path></g>' % (p, bd))
    swell_l, swell_d = '', ''
    for i in range(110):
        t = r.random() ** 1.4
        y = HZ + 3 + 226 * t
        length = r.uniform(20, 56) + t * 190
        x = r.uniform(-40, 480)
        if r.random() < .5:
            swell_l += lens(x, y, length, .5 + t * 2.2)
        else:
            swell_d += lens(x, y, length, .6 + t * 3.2)
    a.append('<g filter="url(#%s-b06)"><path d="%s" fill="#b4c0c3" opacity=".26"></path><path d="%s" fill="#0f0c16" opacity=".46"></path></g>' % (p, swell_l, swell_d))
    glint = ''
    for i in range(28):
        t = (i / 28) ** 1.4
        length = 36 + t * 140 * r.uniform(.5, 1)
        glint += lens(110 - length / 2 + r.uniform(-30, 30) * (1 + t), HZ + 4 + 190 * t, length, .8 + t * 1.6)
    a.append('<path d="%s" fill="#dfe3df" opacity=".4" filter="url(#%s-b1)"></path>' % (glint, p))
    # the point
    a.append('<path d="%s" fill="#5a4852" filter="url(#%s-r1)"></path>' % (bd, p))
    # the keeper's house and the tower, seen against the sky
    tx, base, top = 386, 428, 152
    b0, t0 = 31, 19
    a.append('<g filter="url(#%s-wcb)">' % p)
    a.append('<path d="M304 436L304 406L350 406L350 436Z" fill="url(#%s-house)"></path>'
             '<path d="M298 408L327 386L356 408Z" fill="url(#%s-roof)"></path>'
             '<rect x="338" y="388" width="6" height="13" fill="#2a1420"></rect>' % (p, p))
    a.append('<path d="M%d %dL%d %dL%d %dL%d %dZ" fill="url(#%s-tower)"></path>' % (tx - b0, base + 8, tx - t0, top, tx + t0, top, tx + b0, base + 8, p))
    a.append('<rect x="%d" y="%d" width="%d" height="5" fill="#1d0e15"></rect>' % (tx - 27, top - 5, 54))
    a.append('<rect x="%d" y="%d" width="%d" height="29" fill="#20131a"></rect>' % (tx - 14, top - 34, 28))
    a.append('<rect x="%d" y="%d" width="%d" height="25" fill="#ffe7a8"></rect>' % (tx - 11, top - 32, 22))
    a.append('<path d="M%d %dL%d %dM%d %dL%d %d" stroke="#20131a" stroke-width="1.6"></path>' % (tx - 4, top - 33, tx - 4, top - 6, tx + 4, top - 33, tx + 4, top - 6))
    a.append('<path d="M%d %dQ%d %d %d %dQ%d %d %d %dZ" fill="url(#%s-roof)"></path>' % (tx - 17, top - 34, tx - 8, top - 47, tx, top - 54, tx + 8, top - 47, tx + 17, top - 34, p))
    a.append('<rect x="%d" y="%d" width="2" height="9" fill="#1d0e15"></rect>' % (tx - 1, top - 63))
    for y in (232, 322, 392):
        a.append('<rect x="%d" y="%d" width="6" height="12" fill="#2a1a24"></rect>' % (tx - 8, y))
    a.append('<path d="M%d %dL%d %d" stroke="#201018" stroke-width="1.5"></path>' % (tx - 27, top - 16, tx + 27, top - 16))
    for k in range(-3, 4):
        a.append('<path d="M%d %dL%d %d" stroke="#201018" stroke-width=".9"></path>' % (tx + k * 9, top - 16, tx + k * 9, top - 5))
    a.append('</g>')
    a.append('<path d="M%s %sL%s %s" stroke="#6b6474" stroke-width="5" opacity=".3" filter="url(#%s-b2)"></path>' % (tx + 8, top + 8, tx + 15, base, p))
    # the beam barely there, the house's lit windows
    a.append('<path d="M%d %dL-20 300L-20 372Z" fill="url(#%s-beam)" filter="url(#%s-b5)"></path>' % (tx - 8, top - 19, p, p))
    a.append('<path d="M%d %dL520 104L520 74Z" fill="url(#%s-beam2)" filter="url(#%s-b5)"></path>' % (tx + 8, top - 19, p, p))
    a.append('<ellipse cx="%d" cy="%d" rx="30" ry="30" fill="url(#%s-lamp)"></ellipse>' % (tx, top - 19, p))
    a.append('<rect x="313" y="414" width="7" height="10" fill="#f8cf83"></rect><rect x="331" y="414" width="7" height="10" fill="#f8cf83"></rect>'
             '<ellipse cx="325" cy="419" rx="20" ry="13" fill="url(#%s-lamp)" opacity=".34"></ellipse>' % p)
    # the lower step of the point, in front of the tower's foot
    step = [(206, 532), (240, 510), (288, 490), (330, 462), (372, 452), (436, 446), (512, 424), (512, 596), (440, 578), (370, 566), (300, 554), (244, 544)]
    a.append('<path d="%s" fill="#423340" filter="url(#%s-r2)"></path>' % (poly(crag(r, step)), p))
    surf = ''
    base_line = [(196, 526), (214, 536), (248, 546), (300, 558), (370, 570), (440, 582), (510, 598)]
    for i in range(len(base_line) - 1):
        (x0, y0), (x1, y1) = base_line[i], base_line[i + 1]
        for j in range(5):
            t = r.random()
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            surf += lens(x - 26, y + r.uniform(-3, 6), r.uniform(22, 54), r.uniform(1, 2.1))
    a.append('<path d="%s" fill="#e6e8e2" opacity=".62" filter="url(#%s-b1)"></path>' % (surf, p))
    # a low dark ledge close to us, lower right
    ledge = [(286, 716), (318, 676), (372, 660), (430, 640), (512, 618), (512, 716)]
    a.append('<path d="%s" fill="#2a1e27" filter="url(#%s-r3)"></path>' % (poly(crag(r, ledge, .13)), p))
    a.append('<path d="%s" fill="#dfe2dd" opacity=".4" filter="url(#%s-b1)"></path>' % (lens(290, 678, 54, 1.4) + lens(340, 660, 60, 1.3) + lens(402, 642, 50, 1.1), p))
    a.append('<rect width="500" height="700" fill="url(#%s-vig)"></rect>' % p)
    art = ['<g filter="url(#%s-paper)"><g filter="url(#%s-wash)">%s</g></g>' % (p, p, '\n'.join(a))]
    words = [foil_line(p, 'Happy', 32, 112, 96, anchor='start'), foil_line(p, 'Birthday', 32, 200, 96, anchor='start'),
             engraved(p, 'for my son', 36, 262, 50, anchor='start', family=GARAMOND, caps=True, spacing=2)]
    return wrap('lighthouse', 'A lighthouse on a rocky point at evening', d, art, words)


# ---- 4. Magnolia -------------------------------------------------------------------

def petal(p, i, r, cx, cy, ang, length, width, bruise=False):
    up = [(0, -.04), (.16, -.17), (.38, -.35), (.62, -.48), (.82, -.5), (.95, -.3), (1, -.02)]
    lo = [(.95, .27), (.82, .5), (.62, .48), (.38, .35), (.16, .17), (0, .04)]
    pts = [(x * length + r.uniform(-.012, .012) * length, y * width + r.uniform(-.02, .02) * width) for x, y in up + lo]
    d = smooth(pts, closed=True)
    th = math.radians(ang)
    sn, cs = math.sin(th), math.cos(th)
    # light from the upper left; find which side of the petal faces it
    side = 1 if (-.6 * -sn + -.8 * cs) > 0 else -1
    ox, oy = 3 * cs + 8 * sn, -3 * sn + 8 * cs
    s = ['<g transform="translate(%s %s) rotate(%s)">' % (n(cx), n(cy), ang)]
    s.append('<path d="%s" transform="translate(%s %s)" fill="#40361f" fill-opacity=".36" filter="url(#%s-b7)"></path>' % (d, n(ox), n(oy), p))
    s.append('<clipPath id="%s-p%d"><path d="%s"></path></clipPath><g clip-path="url(#%s-p%d)">' % (p, i, d, p, i))
    s.append('<path d="%s" fill="url(#%s-pet)"></path>' % (d, p))
    s.append('<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="#6f6243" opacity=".5" filter="url(#%s-b7)"></ellipse>'
             % (n(length * .5), n(-side * width * .44), n(length * .62), n(width * .22), p))
    s.append('<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="#ffffff" opacity=".85" filter="url(#%s-b7)"></ellipse>'
             % (n(length * .66), n(side * width * .24), n(length * .3), n(width * .13), p))
    s.append('<ellipse cx="%s" cy="0" rx="%s" ry="%s" fill="#5e5330" opacity=".6" filter="url(#%s-b7)"></ellipse>' % (n(length * .1), n(length * .3), n(width * .32), p))
    # a soft crease down the middle, and the fine veins of a thick petal
    s.append('<path d="M%s 0Q%s %s %s 0" fill="none" stroke="#8b7c56" stroke-width="3" opacity=".3" filter="url(#%s-b2)"></path>'
             % (n(length * .12), n(length * .5), n(side * width * .03), n(length * .92), p))
    veins = ''
    for k in (-4, -3, -2, -1, 1, 2, 3, 4):
        veins += 'M%s %sQ%s %s %s %s' % (n(length * .1), n(k * width * .012), n(length * .5), n(k * width * .1),
                                         n(length * (.94 - abs(k) * .05)), n(k * width * .095))
    s.append('<path d="%s" fill="none" stroke="#a7966c" stroke-width=".7" opacity=".2"></path>' % veins)
    if bruise:
        s.append('<ellipse cx="%s" cy="%s" rx="20" ry="7" fill="#8a5a3a" opacity=".2" filter="url(#%s-b3)"></ellipse>' % (n(length * .97), n(side * -6), p))
    s.append('</g><path d="%s" fill="none" stroke="#6e6144" stroke-width=".8" stroke-opacity=".38"></path></g>' % d)
    return ''.join(s)


def leaf(p, i, r, cx, cy, ang, length, width, bend=10, under=False):
    """A magnolia leaf from above: lit half, shaded half, veins, a wet highlight.
    With under=True it shows the rust-felted underside, the card's burgundy note."""
    k = 14
    top, bot, mid = [], [], []
    for j in range(k + 1):
        t = j / k
        c = bend * math.sin(math.pi * t)
        w = width * .5 * (math.sin(math.pi * t ** .8) ** .78) * (1 + .03 * math.sin(t * 19 + i))
        x = t * length
        mid.append((x, c))
        top.append((x, c - w))
        bot.append((x, c + w))
    th = math.radians(ang)
    sn, cs = math.sin(th), math.cos(th)
    lit_top = (-.6 * sn + -.8 * -cs) > 0  # is the local -y half facing the light?
    upper = smooth(top + mid[::-1], closed=True)
    lower = smooth(mid + bot[::-1], closed=True)
    whole = smooth(top + bot[::-1], closed=True)
    if under:
        a, b, rib = p + '-lua', p + '-lub', '#d9a97a'
    else:
        a, b, rib = p + '-lfa', p + '-lfb', '#c7d0a4'
    if not lit_top:
        a, b = b, a
    s = ['<g transform="translate(%s %s) rotate(%s)">' % (n(cx), n(cy), ang)]
    s.append('<path d="%s" transform="translate(%s %s)" fill="#2c2614" fill-opacity=".34" filter="url(#%s-b5)"></path>'
             % (whole, n(2 * cs + 6 * sn), n(-2 * sn + 6 * cs), p))
    s.append('<clipPath id="%s-l%d"><path d="%s"></path></clipPath><g clip-path="url(#%s-l%d)">' % (p, i, whole, p, i))
    s.append('<path d="%s" fill="url(#%s)"></path><path d="%s" fill="url(#%s)"></path>' % (upper, a, lower, b))
    if under:
        s.append('<path d="%s" fill="#3a1016" opacity=".3" filter="url(#%s-b5)"></path>' % (smooth(mid), p))
    else:
        hi = -1 if lit_top else 1
        s.append('<path d="%s" fill="none" stroke="#b9d8c4" stroke-width="%s" opacity=".5" filter="url(#%s-b3)"></path>'
                 % (smooth([(q[0], q[1] + hi * width * .17 + r.uniform(-1, 1)) for q in mid[2:12]]), n(width * .12), p))
        s.append('<path d="%s" fill="none" stroke="#0c1e13" stroke-width="%s" opacity=".55" filter="url(#%s-b3)"></path>'
                 % (smooth(mid[1:14]), n(width * .05), p))
    veins = ''
    for j in range(1, 11):
        q = mid[int(j * k / 11.5)]
        w = width * .46 * math.sin(math.pi * (j / 11)) ** .7
        for sg in (-1, 1):
            veins += 'M%s %sQ%s %s %s %s' % (n(q[0]), n(q[1]), n(q[0] + 10), n(q[1] + sg * w * .55), n(q[0] + 30), n(q[1] + sg * w))
    s.append('<path d="%s" fill="none" stroke="%s" stroke-width=".8" opacity="%s"></path>' % (veins, rib, '.2' if not under else '.32'))
    s.append('</g>')
    s.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.5" stroke-opacity=".6" stroke-linecap="round"></path>' % (smooth(mid[:13]), rib))
    s.append('</g>')
    return ''.join(s)


def magnolia():
    p = 'mg'
    r = random.Random(9)
    d = [
        lin(p + '-plate', [(0, '#efe3c8'), (.6, '#e9dbbb'), (1, '#dfccA6')]),
        rad(p + '-foxed', [(.45, '#c8ad7c', 0), (1, '#a98954', .42)], .5, .42, .8),
        lin(p + '-pet', [(0, '#7f7344'), (.16, '#b3a472'), (.36, '#e0d4ad'), (.6, '#f6efdb'), (.84, '#fffbef'), (1, '#fffdf6')], 0, 0, 1, 0),
        lin(p + '-lfa', [(0, '#3f7350'), (.5, '#2a5a3b'), (1, '#173a26')], 0, 0, 1, .4),
        lin(p + '-lfb', [(0, '#16321f'), (.6, '#112a1a'), (1, '#0d2015')], 0, 0, 1, .4),
        lin(p + '-lua', [(0, '#a35f3f'), (1, '#7a3628')], 0, 0, 1, .4),
        lin(p + '-lub', [(0, '#6f2a22'), (1, '#50181b')], 0, 0, 1, .4),
        lin(p + '-stem', [(0, '#7a6a55'), (1, '#33281e')], 0, 0, 1, 0),
        lin(p + '-band', [(0, '#5c1729'), (.5, '#4a1020'), (1, '#360a17')]),
        rad(p + '-cone', [(0, '#efe6a8'), (.5, '#c9bd76'), (1, '#8a7c46')], .4, .36, .7),
        lin(p + '-bud', [(0, '#fbf5e4'), (.6, '#e8dcbc'), (1, '#b4a678')], 0, 0, 1, .3),
        wc(p + '-wc', 2.4, '.05', .8, .3, 2.4, (.15, .1, .05), 4),
        blur(p + '-b2', 2), blur(p + '-b3', 3), blur(p + '-b5', 5), blur(p + '-b7', 7.5), blur(p + '-soft', 1.1),
        paper(p, 41), wash(p, 42, .2),
        foil(p, 40, 560, 460, 610),
    ]
    a = ['<rect width="500" height="700" fill="#f4ecd9"></rect>']
    a.append('<rect x="30" y="30" width="440" height="640" fill="url(#%s-plate)"></rect>' % p)
    a.append('<rect x="30" y="30" width="440" height="500" fill="url(#%s-foxed)"></rect>' % p)
    fox = ''
    for i in range(46):
        x, y, rr = r.uniform(34, 466), r.uniform(34, 526), r.uniform(.5, 1.5)
        fox += 'M%s %sa%s %s 0 1 0 .1 0Z' % (n(x), n(y), n(rr), n(rr))
    a.append('<path d="%s" fill="#8a6a3a" opacity=".3"></path>' % fox)
    # stem, side shoot, then the leaves behind the bloom
    cx, cy = 244, 262
    plant = []
    plant.append('<path d="%s" fill="url(#%s-stem)"></path>' % (tapered([(120, 560), (150, 496), (186, 416), (222, 330), (cx, cy + 10)], 15, 9), p))
    plant.append('<path d="%s" fill="url(#%s-stem)"></path>' % (tapered([(184, 420), (262, 392), (330, 300), (378, 196), (392, 136)], 8, 4), p))
    leaves = [
        (cx - 4, cy - 26, -118, 196, 74, 12, False),
        (cx + 8, cy - 18, -62, 178, 72, -10, False),
        (cx - 20, cy + 6, 172, 196, 76, 14, False),
        (cx - 8, cy + 26, 128, 202, 78, -12, True),
        (cx + 16, cy + 22, 66, 216, 78, 12, False),
        (cx + 24, cy + 4, 8, 196, 74, -12, False),
        (cx - 16, cy - 2, -158, 150, 60, 10, True),
    ]
    for i, (lx, ly, ang, ln, wd, bend, under) in enumerate(leaves):
        plant.append(leaf(p, i, r, lx, ly, ang, ln, wd, bend, under))
    # side shoot's own bud and small leaf
    plant.append(leaf(p, 7, r, 344, 270, 24, 112, 42, -7, False))
    plant.append(leaf(p, 8, r, 356, 214, -28, 96, 38, 6, False))
    bud = ('<g transform="translate(392 138) rotate(10)">'
           '<path d="M-17 2C-22 -30 -8 -66 4 -92C16 -62 24 -28 16 2Z" fill="url(#%s-bud)"></path>'
           '<path d="M-3 -88C-16 -56 -16 -26 -8 2C2 -22 4 -60 4 -92Z" fill="#fffbef" opacity=".85"></path>'
           '<path d="M12 -60C18 -38 19 -16 15 2C8 -14 6 -40 7 -78Z" fill="#a89a6c" opacity=".55"></path>'
           '<path d="M-20 10C-24 -6 -19 -24 -9 -34C-10 -18 -6 -4 2 8Z" fill="#5d6d3e"></path>'
           '<path d="M21 10C24 -4 20 -20 11 -30C12 -16 10 -2 0 8Z" fill="#3c5230"></path>'
           '</g>' % p)
    plant.append(bud)
    a.append('<g filter="url(#%s-wc)">%s</g>' % (p, ''.join(plant)))
    # the bloom: back petals, then the front ring, each shading the one under it
    bloom = []
    ring = [(-100, 146, 112, False), (-40, 142, 110, True), (22, 138, 108, False), (82, 130, 104, False), (142, 136, 108, True), (200, 144, 112, False)]
    i = 0
    for ang, ln, wd, br in ring:
        bloom.append(petal(p, i, r, cx, cy, ang, ln, wd, br))
        i += 1
    for ang, ln, wd, br in [(-68, 104, 78, False), (52, 96, 74, False), (172, 102, 76, False)]:
        bloom.append(petal(p, i, r, cx, cy, ang, ln, wd, br))
        i += 1
    # the cone with its stamens
    st = ''
    for k in range(46):
        ang = k / 46 * 2 * math.pi + r.uniform(-.05, .05)
        r0, r1 = r.uniform(18, 22), r.uniform(30, 40)
        x0, y0 = cx + math.cos(ang) * r0, cy + 4 + math.sin(ang) * r0 * .86
        x1, y1 = cx + math.cos(ang) * r1, cy + 4 + math.sin(ang) * r1 * .86
        st += '<path d="M%s %sL%s %s" stroke="%s" stroke-width="%s" stroke-linecap="round"></path>' % (
            n(x0), n(y0), n(x1), n(y1), r.choice(['#7a2436', '#8c3a3e', '#e6d9a8', '#d4c088', '#efe6c0']), n(r.uniform(2, 3.2)))
    bloom.append('<ellipse cx="%d" cy="%d" rx="44" ry="40" fill="#3c2c1a" opacity=".5" filter="url(#%s-b5)"></ellipse>' % (cx, cy + 8, p))
    bloom.append(st)
    bloom.append('<g transform="translate(%d %d) rotate(-14)"><ellipse cx="0" cy="-8" rx="21" ry="30" fill="url(#%s-cone)"></ellipse>' % (cx, cy, p))
    dots = ''
    for row in range(9):
        y = -34 + row * 7.2
        half = 19 * math.sqrt(max(0, 1 - ((y + 8) / 30) ** 2))
        for col in range(-3, 4):
            x = (col + .5 * (row % 2)) * 6.6
            if abs(x) < half - 1:
                dots += '<ellipse cx="%s" cy="%s" rx="2.6" ry="2" fill="#f4edc0" stroke="#7d6f3e" stroke-width=".7"></ellipse>' % (n(x), n(y))
    bloom.append(dots + '</g>')
    a.append('<g filter="url(#%s-wc)">%s</g>' % (p, ''.join(bloom)))
    a.append('<rect x="30" y="530" width="440" height="140" fill="url(#%s-band)"></rect>' % p)
    art = ['<g filter="url(#%s-paper)"><g filter="url(#%s-wash)">%s</g></g>' % (p, p, '\n'.join(a))]
    rules = ('<rect x="30" y="30" width="440" height="640" fill="none" stroke="url(#%s-foil)" stroke-width="1.4"></rect>'
             '<rect x="22.5" y="22.5" width="455" height="655" fill="none" stroke="url(#%s-foil)" stroke-width="1"></rect>'
             '<path d="M30 530H470M30 537H470" fill="none" stroke="url(#%s-foil)" stroke-width="1.2"></path>' % (p, p, p))
    words = [rules, foil_line(p, 'Happy Birthday', 250, 600, 78),
             engraved(p, 'to my son', 250, 655, 50, family=GARAMOND, caps=True, spacing=2)]
    return wrap('magnolia', 'A magnolia branch in the style of a botanical plate', d, art, words)


# ---- What the eight later fronts share ---------------------------------------------

LINE = '<!--LINE-->'


def attrs(f=None, o=None, more=''):
    s = ''
    if f:
        s += ' filter="url(#%s)"' % f
    if o is not None:
        s += ' opacity="%s"' % o
    if more:
        s += ' ' + more
    return s


def fillp(d, fill, f=None, o=None, more=''):
    return '<path d="%s" fill="%s"%s></path>' % (d, fill, attrs(f, o, more))


def strokep(d, stroke, w, f=None, o=None, more=''):
    return '<path d="%s" fill="none" stroke="%s" stroke-width="%s"%s></path>' % (d, stroke, w, attrs(f, o, more))


def oval(cx, cy, rx, ry, fill, f=None, o=None, more=''):
    return '<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="%s"%s></ellipse>' % (n(cx), n(cy), n(rx), n(ry), fill, attrs(f, o, more))


def box(x, y, w, h, fill, f=None, o=None, more=''):
    return '<rect x="%s" y="%s" width="%s" height="%s" fill="%s"%s></rect>' % (n(x), n(y), n(w), n(h), fill, attrs(f, o, more))


def held(id_, d):
    """A long outline kept once, so its shadow, clip, fill and edge can share it."""
    return '<defs><path id="%s" d="%s"></path></defs>' % (id_, d)


def use(id_, fill, f=None, o=None, more=''):
    return '<use href="#%s" fill="%s"%s></use>' % (id_, fill, attrs(f, o, more))


def clip_of(id_, shape):
    return '<clipPath id="%s"><use href="#%s"></use></clipPath>' % (id_, shape)


def segment(a, b):
    return 'M%s %sL%s %s' % (n(a[0]), n(a[1]), n(b[0]), n(b[1]))


def mix(a, b, t):
    """Blend two #rrggbb colors."""
    t = max(0, min(1, t))
    return '#%02x%02x%02x' % tuple(int(int(a[i:i + 2], 16) * (1 - t) + int(b[i:i + 2], 16) * t + .5) for i in (1, 3, 5))


class Cam:
    """A plain perspective camera, so a building or a chair turned at an angle comes out true.
    u runs across the thing, v up from the ground, w away along it; yaw swings w to the right.
    ox, oy is the point straight ahead on the horizon, f the lens, eye the eye height."""

    def __init__(self, ox, oy, f, eye, dist, yaw=0, shift=0):
        self.ox, self.oy, self.f, self.eye, self.dist, self.shift = ox, oy, f, eye, dist, shift
        self.c, self.s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))

    def depth(self, u, w):
        return -u * self.s + w * self.c + self.dist

    def pt(self, u, v, w):
        x = u * self.c + w * self.s + self.shift
        z = self.depth(u, w)
        return (self.ox + self.f * x / z, self.oy + self.f * (self.eye - v) / z)

    def px(self, u, w):
        """Page units per world unit at that spot."""
        return self.f / self.depth(u, w)

    def quad(self, *pts):
        return poly([self.pt(*q) for q in pts])


def dab(r, x, y, rx, ry):
    """One touch of a loaded brush: a lumpy little shape the watercolor filter roughens further."""
    k = r.choice((5, 6, 6, 7))
    a = r.uniform(0, 6.3)
    return poly([(x + rx * r.uniform(.7, 1.2) * math.cos(a + i * 6.283 / k),
                  y + ry * r.uniform(.7, 1.2) * math.sin(a + i * 6.283 / k)) for i in range(k)])


def tree(r, cx, cy, rx, ry, count, size, cols, f, sun=(-.7, -.7)):
    """A leaf mass: one dark body, then dabs sorted by how much each faces the sun. cols runs dark to light."""
    tones = [''] * len(cols)
    for i in range(count):
        a, q = r.uniform(0, 6.283), r.random() ** .55
        x, y = math.cos(a) * q, math.sin(a) * q
        lit = (x * sun[0] + y * sun[1]) * .5 + .5 + r.uniform(-.2, .2)
        k = max(0, min(len(cols) - 1, int(lit * len(cols))))
        s = size * r.uniform(.7, 1.3)
        tones[k] += dab(r, cx + x * rx, cy + y * ry, s * 1.25, s)
    body = [(cx + rx * r.uniform(.76, .96) * math.cos(i * 6.283 / 12), cy + ry * r.uniform(.76, .96) * math.sin(i * 6.283 / 12))
            for i in range(12)]
    return '<g filter="url(#%s)">%s%s</g>' % (f, fillp(smooth(body, True), cols[0]), ''.join(fillp(t, c) for t, c in zip(tones, cols) if t))


def sliver(x, y, ang, length, width):
    """A leaf or a long brush mark from (x, y) at an angle in degrees, fat in the middle."""
    th = math.radians(ang)
    ex, ey = x + math.cos(th) * length, y + math.sin(th) * length
    mx, my = (x + ex) / 2, (y + ey) / 2
    nx, ny = -math.sin(th) * width, math.cos(th) * width
    return 'M%s %sQ%s %s %s %sQ%s %s %s %sZ' % (n(x), n(y), n(mx + nx), n(my + ny), n(ex), n(ey), n(mx - nx), n(my - ny), n(x), n(y))


def sward(r, count, x0, x1, y0, y1, hmin, hmax, lean, wmin, wmax, tones=3):
    """Grass thickening toward us: blades sorted far to near, one path per tone."""
    out = [''] * tones
    for i in range(count):
        t = r.random()
        h = (hmin + (hmax - hmin) * t) * r.uniform(.6, 1.15)
        out[min(tones - 1, int(t * tones))] += blade(r.uniform(x0, x1), y0 + (y1 - y0) * t, h, r.uniform(-lean, lean),
                                                     wmin + (wmax - wmin) * t)
    return out


def stand(r, x0, x1, env, step, wide, base):
    """A row of pines whose heights follow env(x)."""
    path, x = '', x0
    while x < x1:
        h = env(x) * r.uniform(.82, 1.12)
        path += pine(r, x, base, h, h * wide)
        x += step * r.uniform(.7, 1.3)
    return path


def bleed(p, a):
    """A painting that runs to the card's edges, like the buck and the lighthouse."""
    return ['<g filter="url(#%s-paper)"><g filter="url(#%s-wash)">%s</g></g>' % (p, p, '\n'.join(a))]


def inset(p, s):
    """A painting set in a cream mat, the way the lake card is."""
    return ['<rect width="500" height="700" fill="#f2e8d3"></rect>',
            '<g filter="url(#%s-paper)"><rect width="500" height="700" fill="#f2e8d3"></rect><g clip-path="url(#%s-scene)">'
            '<g filter="url(#%s-wash)">%s</g></g></g>' % (p, p, p, '\n'.join(s))]


def scene_clip(p):
    return '<clipPath id="%s-scene"><rect x="34" y="34" width="432" height="632"></rect></clipPath>' % p


def mat_rules(p, ink='#1a2438'):
    return ('<rect x="34" y="34" width="432" height="632" fill="none" stroke="%s" stroke-width=".9" opacity=".7"></rect>'
            '<rect x="23.5" y="23.5" width="453" height="653" fill="none" stroke="url(#%s-foil)" stroke-width="1.6"></rect>' % (ink, p))


def foil_rule(p):
    return '<rect x="22.5" y="22.5" width="455" height="655" fill="none" stroke="url(#%s-foil)" stroke-width="1.2"></rect>' % p



# ---- 5. Tobacco barn ---------------------------------------------------------------

def barn():
    p, r = 'bn', random.Random(63)
    u = lambda k: 'url(#%s-%s)' % (p, k)
    X0, Y0, X1, Y1, HZ, VX = 34, 34, 466, 666, 470, 236
    W_ = X1 - X0
    d = [
        lin(p + '-sky', [(0, '#0f1330'), (.2, '#1b1e40'), (.4, '#322e50'), (.56, '#5a4159'), (.7, '#925855'), (.81, '#cc8352'),
                         (.91, '#efb36c'), (1, '#fde0a4')], 0, Y0, 0, HZ + 2, user=True),
        rad(p + '-glow', [(0, '#ffe6ad', .95), (.3, '#fbc078', .55), (1, '#e98a4e', 0)]),
        lin(p + '-cl1', [(0, '#070a1c', .95), (.55, '#12132c', .8), (1, '#2b2540', 0)]),
        lin(p + '-cl2', [(0, '#5a3f58', 0), (.4, '#8e5560', .72), (.8, '#e08d5a', .95), (1, '#f7c788', .9)]),
        lin(p + '-far', [(0, '#6b6382'), (1, '#d8ac8c')]),
        lin(p + '-far2', [(0, '#3d3a58'), (1, '#a88273')]),
        lin(p + '-field', [(0, '#f3c678'), (.05, '#d9a258'), (.17, '#9a7c3b'), (.38, '#555a2c'), (.66, '#262d1a'), (1, '#0b0f0a')],
            0, HZ, 0, Y1, user=True),
        lin(p + '-front', [(0, '#d8603a'), (.5, '#b04229'), (1, '#82301f')], 0, 0, 1, .3),
        lin(p + '-flank', [(0, '#532227'), (1, '#2c151a')], 0, 0, 1, 0),
        lin(p + '-tin', [(0, '#7b5445'), (.5, '#5c3639'), (1, '#36212d')], 0, 0, 1, .4),
        rad(p + '-vig', [(.55, '#05060f', 0), (1, '#05060f', .72)], .5, .46, .8),
        wc(p + '-wc', 6, '.03 .05', 2.4, .6, 3, (.03, .02, .05), 7),
        wc(p + '-wcf', 5, '.03 .05', 3, .4, 3, (.12, .1, .14), 13),
        wc(p + '-wcn', 2.4, '.05', 1.4, .4, 2, (.04, .05, .02), 15),
        wc(p + '-wcb', 1.3, '.06', .6, .3, 2, (.06, .02, .02), 19),
        rock(p + '-wd', 33, '.16 .008', 1.8),
        rock(p + '-tn', 37, '.05 .05', 4),
        cloud(p + '-c1', '.0032 .03', 3.4, 1.55, 5, '1.4 .7'),
        cloud(p + '-c2', '.006 .05', 3.6, 1.5, 12, '.9 .5'),
        blur(p + '-b06', .6), blur(p + '-b1', 1), blur(p + '-b2', 2.2), blur(p + '-m', 9), blur(p + '-soft', 1.1),
        paper(p, 61), wash(p, 62), foil(p, 60, 80, 440, 250), scene_clip(p),
    ]
    s = [box(X0, Y0, W_, HZ - Y0 + 2, u('sky')), oval(128, HZ - 8, 320, 132, u('glow')),
         box(X0, Y0, W_, 250, u('cl1'), p + '-c1'), box(X0, 322, W_, 130, u('cl2'), p + '-c2')]
    # hills, then a far wood, each lit from the low sun on the left
    s.append(fillp(land(ridge(r, X0 - 12, X1 + 12, 438, 12), HZ + 2), u('far'), p + '-wcf', .92))
    s.append(oval(150, 452, 240, 9, '#fbe2b4', p + '-m', .6))
    s.append(fillp(canopy(r, X0 - 12, X1 + 12, lambda x: 452 + 5 * math.sin(x * .02), HZ + 2, 11), u('far2'), p + '-wcf'))
    s.append(oval(128, 466, 220, 6, '#ffe9bc', p + '-m', .7))
    s.append(box(X0, HZ, W_, Y1 - HZ, u('field')))
    s.append(oval(128, HZ + 3, 280, 7, '#ffe9b8', p + '-m', .5))
    # the crop rows, wedges closing on one point under the barn
    rows = ''
    for i in range(-18, 19):
        bx = VX + i * 74
        rows += poly([(VX + i * 74 * .03, HZ + 6), (bx + 17, HZ + 206), (bx - 17, HZ + 206)])
    s.append(fillp(rows, '#3b4422', p + '-b06', .62))
    # the wood behind the barn on the right, a lone tree out in the light on the left
    dark = ['#14191c', '#22281f', '#3a3a26', '#7c5c32']
    s.append(tree(r, 466, 392, 62, 80, 110, 14, dark, p + '-wc', (-.9, -.35)))
    s.append(tree(r, 404, 424, 72, 50, 90, 13, dark, p + '-wc', (-.9, -.35)))
    s.append(tree(r, 346, 446, 62, 28, 60, 10, ['#1a1f20', '#2b2e24', '#47412a', '#8d6a38'], p + '-wc', (-.9, -.35)))
    s.append(fillp(tapered([(68, 482), (72, 440), (66, 404)], 11, 6), '#161313', p + '-wcn'))
    s.append(tree(r, 72, 396, 54, 56, 90, 12, ['#141518', '#1f2020', '#2e2a22', '#6e4f2c'], p + '-wc', (.5, -.7)))
    # the barn's long shadow, thrown right across the rows
    cam = Cam(250, HZ, 660, 1.6, 30, 42, 1.1)
    HW, L, E, R = 3, 7, 5.8, 8
    s.append(fillp(poly([cam.pt(HW, 0, 0), cam.pt(HW, 0, L), (520, 512), (520, 538)]), '#141014', p + '-b2', .55))
    b = []
    # lean-to shed on the left: open and dark, two posts, its tin edge catching the sun
    b.append(fillp(cam.quad((-HW, 0, 0), (-6.4, 0, 0), (-6.4, 2.5, 0), (-HW, 3.7, 0)), '#190e12'))
    for ux in (-6.3, -4.7):
        top = 3.7 - (-3 - ux) * .353
        b.append(fillp(cam.quad((ux - .12, 0, 0), (ux + .12, 0, 0), (ux + .12, top, 0), (ux - .12, top, 0)), '#6a4a34'))
        b.append(strokep(segment(cam.pt(ux - .12, 0, 0), cam.pt(ux - .12, top, 0)), '#f2c084', 1, o=.8))
    b.append(fillp(cam.quad((-HW, 3.98, -.2), (-6.8, 2.58, -.2), (-6.8, 2.34, -.2), (-HW, 3.72, -.2)), '#4a2c2a'))
    b.append(strokep(segment(cam.pt(-HW, 3.98, -.2), cam.pt(-6.8, 2.58, -.2)), '#f5c489', 1.3, o=.85))
    # the long wall, in its own shade
    b.append(fillp(cam.quad((HW, 0, 0), (HW, 0, L), (HW, E, L), (HW, E, 0)), u('flank'), p + '-wd'))
    seams, w = '', .5
    while w < L:
        seams += segment(cam.pt(HW, 0, w), cam.pt(HW, E, w))
        w += .5
    b.append(strokep(seams, '#150a0e', .8, o=.7))
    b.append(fillp(cam.quad((HW, 3.4, 3), (HW, 3.4, 4), (HW, 4.3, 4), (HW, 4.3, 3)), '#120a0d'))
    # the tin roof, rusted in streaks, with its seams and a ridge vent
    b.append(fillp(cam.quad((0, R + .12, -.3), (HW + .35, E - .25, -.3), (HW + .35, E - .25, L + .3), (0, R + .12, L + .3)), u('tin'), p + '-tn'))
    tin, rust, w = '', '', -.1
    while w < L + .2:
        tin += segment(cam.pt(0, R + .12, w), cam.pt(HW + .35, E - .25, w))
        k = r.uniform(.15, .55)
        rust += poly([cam.pt((HW + .35) * k, R + .12 - (R + .37 - E) * k, w + .12), cam.pt(HW + .35, E - .25, w + .06),
                      cam.pt(HW + .35, E - .25, w + .34), cam.pt((HW + .35) * k, R + .12 - (R + .37 - E) * k, w + .24)])
        w += .62
    b.append(fillp(rust, '#a8623a', o=.3))
    b.append(strokep(tin, '#1f1216', .9, o=.6))
    b.append(fillp(cam.quad((0, R + .42, .8), (0, R + .42, 6.2), (0, R + .1, 6.2), (0, R + .1, .8)), '#2a1a22'))
    # the gable end, with the last of the sun full on it
    b.append(fillp(cam.quad((-HW, 0, 0), (HW, 0, 0), (HW, E, 0), (0, R, 0), (-HW, E, 0)), u('front'), p + '-wd'))
    seams, x = '', -HW + .5
    while x < HW:
        seams += segment(cam.pt(x, 0, 0), cam.pt(x, E + (R - E) * (1 - abs(x) / HW), 0))
        x += .5
    pale, tar = '', ''
    for i in range(16):
        x = -HW + .5 * r.randint(0, 11)
        v0 = r.uniform(0, 3)
        v1 = min(v0 + r.uniform(1, 3), E - .1)
        q = cam.quad((x, v0, 0), (x + .5, v0, 0), (x + .5, v1, 0), (x, v1, 0))
        if i % 3:
            pale += q
        else:
            tar += q
    b.append(fillp(pale, '#edba8e', o=.14))
    b.append(fillp(tar, '#2a0f0c', o=.2))
    b.append(strokep(seams, '#3b120e', 1, o=.62))
    # door with its Z brace, and the dark loft hatch
    b.append(fillp(cam.quad((-1.15, .15, 0), (1.15, .15, 0), (1.15, 2.7, 0), (-1.15, 2.7, 0)), '#7c2b1c', p + '-wd'))
    b.append(strokep(segment(cam.pt(0, .15, 0), cam.pt(0, 2.7, 0)), '#2a0f0c', 1.1, o=.8))
    b.append(strokep(segment(cam.pt(-1.1, .36, 0), cam.pt(1.1, .36, 0)) + segment(cam.pt(-1.1, 2.5, 0), cam.pt(1.1, 2.5, 0))
                     + segment(cam.pt(-1.1, .36, 0), cam.pt(1.1, 2.5, 0)), '#bf6a45', 2.2, o=.9))
    b.append(strokep(poly([cam.pt(-1.15, .15, 0), cam.pt(1.15, .15, 0), cam.pt(1.15, 2.7, 0), cam.pt(-1.15, 2.7, 0)]), '#2a0f0c', 1.3, o=.8))
    b.append(fillp(cam.quad((-.8, 3.9, 0), (.8, 3.9, 0), (.8, 5.1, 0), (-.8, 5.1, 0)), '#190b0b'))
    b.append(strokep(segment(cam.pt(-.8, 3.9, 0), cam.pt(.8, 3.9, 0)), '#f0b582', 1.3, o=.8))
    # verge boards: the left one burning in the light, the near corner in shadow
    b.append(strokep(segment(cam.pt(-HW - .35, E - .25, -.3), cam.pt(0, R + .12, -.3)), '#f7cb8e', 2.2))
    b.append(strokep(segment(cam.pt(0, R + .12, -.3), cam.pt(HW + .35, E - .25, -.3)), '#c98857', 2.2))
    b.append(strokep(segment(cam.pt(HW, 0, 0), cam.pt(HW, E, 0)), '#241014', 1.6))
    s.append('<g filter="url(#%s-wcb)">%s</g>' % (p, ''.join(b)))
    # tobacco in rows in front of the barn: broad leaves, smaller and fewer-leaved with distance
    tones = ['', '', '']
    for q, count in ((.16, 3), (.2, 3), (.25, 4), (.31, 4), (.38, 5), (.47, 5), (.58, 6), (.72, 6)):
        y = HZ + 206 * q
        for i in range(-26, 27):
            x = VX + i * 74 * q + r.uniform(-9, 9) * q
            if x < X0 - 30 or x > X1 + 30 or (180 < x < 414 and y < 512):
                continue
            size = 7 + 44 * q
            for k in range(count):
                ang = -90 + (k - (count - 1) / 2) * (150 / count) + r.uniform(-12, 12)
                length = size * r.uniform(.75, 1.15)
                tone = 2 if ang < -100 and r.random() < .75 else (0 if ang > -70 and r.random() < .7 else 1)
                tones[tone] += sliver(x, y, ang, length, length * .34)
    s.append('<g filter="url(#%s-wcn)">%s</g>' % (p, ''.join(fillp(t, c) for t, c in zip(tones, ['#28311a', '#56612c', '#c2a44f']))))
    # broomsedge close to us, dark, with the sun in a few stems at the left
    near = sward(r, 230, X0 - 10, X1 + 10, 612, Y1 + 10, 30, 96, 18, 2.2, 4.4)
    for k, col in enumerate(['#3b3a20', '#20261a', '#0e130c']):
        s.append(fillp(near[k], col, p + '-b06'))
    lit = ''
    for i in range(34):
        lit += blade(r.uniform(X0 - 4, 190), r.uniform(630, Y1 + 8), r.uniform(40, 104), r.uniform(-14, 10), 1.3)
    s.append(fillp(lit, '#d8b06a', o=.68))
    s.append(box(X0, Y0, W_, Y1 - Y0, u('vig')))
    words = [mat_rules(p, '#1a1a2c'), foil_line(p, 'Happy', 250, 138, 98), foil_line(p, 'Birthday', 250, 226, 98), LINE]
    return wrap('barn', 'An old red tobacco barn in a field at evening', d, inset(p, s), words)



# ---- 6. Porch and rocking chair ------------------------------------------------------

def rocker():
    """A slat-back rocker seen from behind and a little to one side, every part projected.
    The eye is seated, so the horizon falls at the top of the chair's back."""
    chair = Cam(250, 340, 429, 110, 230, -28, 50)

    def bar(a, b, cm):
        A, B = chair.pt(*a), chair.pt(*b)
        return '<path d="%s" fill="none" stroke-width="%s"></path>' % (segment(A, B), n(cm * chair.px(a[0], a[2])))

    def curve(pts, w0, w1):
        return '<path d="%s"></path>' % tapered([chair.pt(*q) for q in pts], w0, w1)

    run = lambda w: 13 * ((w + 2) / 48) ** 2         # height of the rocker's curve above the floor
    lean = lambda v: -21 - (v - 44) / 68 * 15        # how far back the chair's back has gone at height v

    def side(sg):
        x = 23 * sg
        return ''.join([
            curve([(x, run(w), w) for w in range(-52, 49, 14)], 11, 10),
            curve([(x * .96, run(-20), -20), (x * .96, 44, -21), (x * .93, 78, lean(78)), (x * .9, 112, lean(112))], 11, 8),
            bar((x, run(22), 22), (x, 66, 22), 4.6),
            bar((x, 24, -19), (x, 24, 22), 2.8),
            curve([(x * 1.12, 69, 30), (x * 1.08, 68, 10), (x * .98, 67, -27)], 12, 8)])

    parts = [side(1), '<path d="%s"></path>' % chair.quad((-23, 44, -19), (23, 44, -19), (24, 46, 24), (-24, 46, 24))]
    parts.append(bar((-23, 24, -19), (23, 24, -19), 2.8))
    parts.append(side(-1))
    for i in range(6):
        x = -17.5 + i * 7
        parts.append('<path d="%s"></path>' % chair.quad((x - 2.4, 56, lean(56)), (x + 2.4, 56, lean(56)), (x + 2.4, 106, lean(106)), (x - 2.4, 106, lean(106))))
    parts.append(bar((-21, 55, lean(55)), (21, 55, lean(55)), 3.4))
    parts.append(curve([(x, 110 + 5 * (1 - (x / 24) ** 2), lean(112)) for x in range(-24, 25, 8)], 15, 15))
    return ''.join(parts)


def porch():
    p, r = 'pc', random.Random(84)
    u = lambda k: 'url(#%s-%s)' % (p, k)
    RT, FE, HB, HT, VX, VY = 372, 503, 133, 103, 250, 340     # rail top, floor edge, header, vanishing point
    d = [
        lin(p + '-sky', [(0, '#7f93a4'), (.34, '#a7afb0'), (.58, '#cfc6ae'), (.78, '#efd9aa'), (1, '#f9e8c2')], 0, 130, 0, 340, user=True),
        rad(p + '-glow', [(0, '#fff3cf', .95), (.45, '#fbe0a6', .4), (1, '#f0cf96', 0)]),
        lin(p + '-cl2', [(0, '#c7c3b6', 0), (.5, '#e2d3b2', .7), (1, '#f6dfb0', .6)]),
        lin(p + '-r1', [(0, '#9fb0bb'), (1, '#e2d3b8')]),
        lin(p + '-r2', [(0, '#7f96a6'), (1, '#d2c9b4')]),
        lin(p + '-r3', [(0, '#5f7d8c'), (1, '#bcbdab')]),
        lin(p + '-r4', [(0, '#45646e'), (1, '#9fa997')]),
        lin(p + '-r5', [(0, '#2f4c4c'), (1, '#7e8f76')]),
        lin(p + '-past', [(0, '#a8ab68'), (.35, '#7c8a4c'), (1, '#4f6238')]),
        lin(p + '-floor', [(0, '#8a6c4e'), (.2, '#5e4836'), (.5, '#30251e'), (.76, '#17120f'), (1, '#0b0908')], 0, FE, 0, 700, user=True),
        lin(p + '-sun', [(0, '#f8d594', .62), (1, '#f8d594', 0)], 0, FE, 0, 650, user=True),
        lin(p + '-bal', [(0, '#6f6e66'), (1, '#46453f')], 0, 0, 1, 0),
        lin(p + '-rail', [(0, '#7a776c'), (1, '#3f3d37')]),
        lin(p + '-pl', [(0, '#121110'), (.76, '#221e1b'), (.95, '#4e4335'), (1, '#c7a46e')], 0, 0, 1, 0),
        lin(p + '-pr', [(0, '#a98a5c'), (.05, '#3e352c'), (.3, '#1e1b18'), (1, '#100f0e')], 0, 0, 1, 0),
        lin(p + '-ceil', [(0, '#0d181c'), (.7, '#16262b'), (1, '#28403f')]),
        lin(p + '-head', [(0, '#121d1f'), (.7, '#1b2826'), (1, '#2e3a33')]),
        lin(p + '-foot', [(0, '#060505', 0), (1, '#060505', .82)], 0, 590, 0, 668, user=True),
        rad(p + '-vig', [(.58, '#050606', 0), (1, '#050606', .6)], .5, .46, .84),
        wc(p + '-wc', 5, '.03 .05', 2.2, .5, 3, (.08, .1, .1), 7),
        wc(p + '-wcf', 4, '.03 .05', 2.4, .4, 3, (.2, .24, .28), 13),
        wc(p + '-wcn', 1.6, '.06', 1, .3, 2, (.02, .03, .02), 21),
        rim(p + '-rim', -1.5, .8, (.97, .84, .58), .85),
        rim(p + '-rimc', -1.8, 1.2, (.98, .84, .56), .95),
        cloud(p + '-c2', '.005 .04', 3.4, 1.55, 9, '1.2 .6'),
        blur(p + '-b1', 1), blur(p + '-b2', 2.4), blur(p + '-b6', 6), blur(p + '-m', 10), blur(p + '-soft', 1.1),
        paper(p, 71), wash(p, 72, .55), foil(p, 40, 40, 460, 130),
    ]
    a = [box(0, 0, 500, 430, u('sky')), oval(340, 262, 270, 150, u('glow')), box(0, 130, 500, 130, u('cl2'), p + '-c2')]
    # the Blue Ridge, layer on layer, mist lying in each fold
    for k, (base, amp, op) in enumerate([(268, 15, .9), (288, 13, 1), (308, 12, 1), (330, 11, 1), (352, 9, 1)]):
        a.append(fillp(land(ridge(r, -12, 512, base, amp), 400), u('r%d' % (k + 1)), p + '-wcf', op))
        a.append(oval(250 + r.uniform(-90, 90), base + 15, 300, 9, '#f8ecd0', p + '-m', .6))
    a.append(oval(330, 300, 300, 56, '#fff1cc', p + '-m', .3))
    # the near pasture falling away below the rail, a hedgerow, trees at its edge
    a.append(fillp(land(ridge(r, -12, 512, 364, 6), 520), u('past'), p + '-wcn'))
    a.append(oval(300, 372, 240, 10, '#f3e6b4', p + '-m', .55))
    leafy = ['#1f3329', '#2e4632', '#4f6a42', '#aaa86a']
    a.append(tree(r, 96, 366, 64, 24, 70, 9, leafy, p + '-wc', (.75, -.6)))
    a.append(tree(r, 404, 356, 84, 34, 90, 10, leafy, p + '-wc', (.75, -.6)))
    a.append(tree(r, 250, 424, 210, 7, 44, 6, ['#2c4230', '#3e5636', '#6a7a46'], p + '-wc', (.7, -.7)))
    # the floor: boards running out to the rail, closing on the vanishing point
    a.append(box(0, FE, 500, 700 - FE, u('floor')))
    seams, tint = '', ''
    for i in range(-26, 27):
        x0, x1 = VX + i * 12, VX + i * 26.5
        seams += segment((x0, FE), (x1, 700))
        if r.random() < .4:
            tint += poly([(x0, FE), (x0 + 12, FE), (x1 + 26.5, 700), (x1, 700)])
    a.append(fillp(tint, '#000000', o=.14))
    a.append(strokep(seams, '#0c0907', 1, o=.62))
    # morning coming through the rail: stripes of sun laid across the boards toward us
    bars = list(range(48, 456, 25))
    sun = ''
    for x in bars:
        g = x + 16
        sun += poly([(g - 9, FE + 2), (g + 9, FE + 2), (g + 14 - 88, 650), (g - 14 - 88, 650)])
    a.append(fillp(sun, u('sun'), p + '-b1'))
    # the chair's shadow, reaching the same way
    a.append(fillp(poly([(280, 500), (418, 560), (332, 650), (176, 620)]), '#050403', p + '-b6', .55))
    # balusters and rails, dark against the morning, sun on their right edges
    rail = ''.join(box(x, RT + 12, 7, 98, u('bal')) for x in bars)
    a.append('<g filter="url(#%s-rim)">%s%s%s</g>' % (p, rail, box(40, 480, 420, 11, u('rail')), box(40, RT + 4, 420, 11, u('rail'))))
    a.append(box(40, RT, 420, 5, '#f1dcae', o=.85))
    a.append(box(40, 491, 420, 12, '#191512', o=.7))
    a.append(box(0, FE, 500, 2, '#f0d6a2', o=.7))
    # the two posts, then the header and the ceiling: dark, and it frames the bright view
    a.append(box(0, 90, 40, 428, u('pl')))
    a.append(box(460, 90, 40, 428, u('pr')))
    a.append(box(0, 0, 500, HT, u('ceil')))
    boards = ''
    for i in range(-15, 16):
        x = VX + i * 22
        boards += segment((x, HT), (VX + (x - VX) * (VY / (VY - HT)), 0))
    a.append(strokep(boards, '#091215', .9, o=.7))
    a.append(box(0, HT, 500, 30, u('head')))
    a.append(box(40, HB - 2, 420, 2, '#9b8a66', o=.7))
    # a Boston fern hung from the header, backlit, its fronds cut into leaflets by a dashed stroke
    FX, FY = 132, 198
    back, front = ['', '', ''], ['', '', '']
    for i in range(36):
        sp = (i + .5) / 36 * 2 - 1 + r.uniform(-.03, .03)
        k = 1 - abs(sp)
        q = [(FX + sp * 14, FY), (FX + sp * 48, FY - 14 - 20 * k), (FX + sp * 84, FY + r.uniform(-8, 6) - 6 * k), (FX + sp * 104, FY + 44 + r.uniform(-6, 26))]
        back[0], back[1], back[2] = back[0] + smooth(q), back[1] + smooth(q[:3]), back[2] + smooth(q[:2])
    for i in range(16):
        sp = (i + .5) / 16 * 2 - 1 + r.uniform(-.04, .04)
        q = [(FX + sp * 10, FY + 2), (FX + sp * 34, FY + r.uniform(-8, 2)), (FX + sp * 54, FY + 30), (FX + sp * 62, FY + 66 + r.uniform(-8, 20))]
        front[0], front[1], front[2] = front[0] + smooth(q), front[1] + smooth(q[:3]), front[2] + smooth(q[:2])
    dash = 'stroke-dasharray="1.7 1.3"'
    fern = [strokep(segment((FX, HB), (FX - 30, FY - 2)) + segment((FX, HB), (FX + 30, FY - 2)) + segment((FX, HB), (FX, FY - 8)), '#1a1612', 1.1)]
    fern += [strokep(back[k], '#1e2e1d', w, more=dash) for k, w in ((0, 5), (1, 9), (2, 12))]
    fern.append(strokep(back[0], '#7f9148', 1, o=.5))
    fern.append(fillp('M100 196Q104 240 132 244Q160 240 164 196Z', '#241a12'))
    fern.append(strokep('M101 208Q132 226 163 208M105 224Q132 238 159 224M116 201Q118 228 124 242M148 201Q146 228 140 242', '#5a4a38', 1, o=.6))
    fern.append(oval(FX, 197, 34, 7, '#3a4a28'))
    fern += [strokep(front[k], c, w, more=dash) for k, w, c in ((0, 5, '#6f8444'), (1, 9, '#4c6235'), (2, 12, '#34472a'))]
    fern.append(strokep(front[0], '#2a3a20', 1))
    a.append('<g filter="url(#%s-wcn)">%s</g>' % (p, ''.join(fern)))
    # the rocker, nearly black against the hills, the sun on its right-hand edges
    a.append('<g filter="url(#%s-rimc)"><g fill="#241710" stroke="#241710" stroke-linecap="round" stroke-linejoin="round">%s</g></g>' % (p, rocker()))
    a.append(box(0, 590, 500, 110, u('foot')))
    a.append(box(0, 0, 500, 700, u('vig')))
    words = [foil_line(p, 'Get Well Soon', 250, 106, 84), LINE]
    return wrap('porch', 'A rocking chair on a porch looking out on morning hills', d, bleed(p, a), words)



# ---- 7. Dogwood ----------------------------------------------------------------------

def bract(p, i, r, ang, world, length, width, plain=False):
    """One of a dogwood's four white bracts: broad, with the notched, rust-stained tip that names it.
    world is its angle on the page, used to find the side that faces the light.
    plain leaves out the shadow and fine veins, for the soft blooms set back behind the branch."""
    up = [(0, 0), (.2, -.22), (.45, -.43), (.7, -.5), (.88, -.41), (.98, -.22), (1, -.1), (.925, 0)]
    lo = [(.925, 0), (1, .1), (.98, .22), (.88, .41), (.7, .5), (.45, .43), (.2, .22), (0, 0)]

    def jitter(run):
        return [(x * length + r.uniform(-.012, .012) * length, y * width + r.uniform(-.018, .018) * width) for x, y in run]
    top, bot = jitter(up), jitter(lo)
    bot[0], bot[-1] = top[-1], top[0]
    d = outline(top, bot)
    th = math.radians(world)
    sn, cs = math.sin(th), math.cos(th)
    side = 1 if (-.6 * -sn + -.8 * cs) > 0 else -1
    form = '%s-f%d' % (p, i)
    s = ['<g transform="rotate(%s)">' % n(ang), held(form, d)]
    if not plain:
        s.append(use(form, '#050c0a', p + '-b5', .46, 'transform="translate(%s %s)"' % (n(2 * cs + 7 * sn), n(-2 * sn + 7 * cs))))
    s.append(clip_of('%s-q%d' % (p, i), form))
    s.append('<g clip-path="url(#%s-q%d)">' % (p, i))
    s.append(use(form, 'url(#%s-br)' % p))
    s.append(oval(length * .5, -side * width * .4, length * .62, width * .22, '#5f6352', p + '-b7', .5))
    s.append(oval(length * .68, side * width * .22, length * .28, width * .14, '#ffffff', p + '-b7', .85))
    s.append(oval(length * .08, 0, length * .26, width * .3, '#5c6a34', p + '-b7', .6))
    if not plain:
        veins = ''
        for k in (-3, -2, -1, 1, 2, 3):
            veins += 'M%s %sQ%s %s %s %s' % (n(length * .06), n(k * width * .012), n(length * .5), n(k * width * .15), n(length * (.93 - abs(k) * .04)), n(k * width * .09))
        s.append(strokep(veins, '#8f8d6c', .7, o=.32))
        s.append(strokep('M%s 0Q%s %s %s 0' % (n(length * .1), n(length * .5), n(side * width * .03), n(length * .9)), '#8a8a64', 2.4, p + '-b2', .3))
    # the stain at the notch
    s.append(oval(length * .96, 0, length * .13, width * .16, '#7d3f33', p + '-b3', .62))
    s.append(oval(length * .94, 0, length * .05, width * .06, '#54281f', p + '-b2', .8))
    s.append('</g>')
    s.append(use(form, 'none', more='stroke="#5f5a46" stroke-width=".8" stroke-opacity=".42"'))
    s.append('</g>')
    return ''.join(s)


def dog_bloom(p, i, r, cx, cy, tilt, sq, length, spin, plain=False):
    """Four bracts, the nearer pair over the other, around the green button of true flowers."""
    s = ['<g transform="translate(%s %s) rotate(%s) scale(1 %s)">' % (n(cx), n(cy), tilt, sq)]
    for k, ang in enumerate((spin + 180, spin, spin + 90, spin + 270)):
        ln = length * (1 if k < 2 else .93) * r.uniform(.97, 1.03)
        s.append(bract(p, i + k, r, ang, ang + tilt, ln, ln * .94, plain))
    s.append(oval(0, 0, length * .21, length * .2, '#2a3016', p + '-b3', .75))
    knob, tones = length * .024, ['', '', '']
    for k in range(1, 13 if plain else 34):
        rr, a = length * (.058 if plain else .034) * math.sqrt(k), k * 2.39996
        x, y = rr * math.cos(a), rr * math.sin(a)
        lit = .5 + (-.6 * x - .8 * y) / (length * .3) + r.uniform(-.1, .1)
        tones[max(0, min(2, int(lit * 3)))] += 'M%s %sa%s %s 0 1 0 .1 0Z' % (n(x - knob), n(y), n(knob), n(knob))
    for tone, col in zip(tones, ('#6f7a38', '#a4a65a', '#d8d084')):
        if tone:
            s.append(fillp(tone, col, more='stroke="#2a3016" stroke-width=".5"'))
    s.append('</g>')
    return ''.join(s)


def ghost(r, cx, cy, length):
    """A blossom far back in the wood, four soft lobes for the blur to melt."""
    base = r.uniform(0, 90)
    return ''.join(sliver(cx, cy, base + k * 90, length * r.uniform(.9, 1.1), length * .5) for k in range(4))


def dogwood():
    p, r = 'dw', random.Random(147)
    u = lambda k: 'url(#%s-%s)' % (p, k)
    d = [
        rad(p + '-ground', [(0, '#4d6258'), (.42, '#2f443d'), (.78, '#1a2a29'), (1, '#0f1a1b')], .44, .36, .82),
        lin(p + '-br', [(0, '#97a066'), (.14, '#cbcd9e'), (.4, '#f1edd8'), (.8, '#fdfaf0'), (1, '#f3e8d2')], 0, 0, 1, 0),
        lin(p + '-lfa', [(0, '#84a066'), (.5, '#5f8650'), (1, '#3a5f3e')], 0, 0, 1, .4),
        lin(p + '-lfb', [(0, '#3f6340'), (.6, '#2f5236'), (1, '#22402d')], 0, 0, 1, .4),
        lin(p + '-bark', [(0, '#7a6d5e'), (.45, '#54483e'), (1, '#251e1a')]),
        lin(p + '-wsh', [(0, '#7f9486', 0), (.5, '#7f9486', .5), (1, '#5a6f64', 0)]),
        lin(p + '-foot', [(0, '#0b1414', 0), (.5, '#0b1414', .74), (1, '#070e0e', .94)], 0, 500, 0, 640, user=True),
        rad(p + '-vig', [(.6, '#060c0c', 0), (1, '#060c0c', .6)], .5, .44, .84),
        wc(p + '-wc', 2.4, '.05', .8, .3, 2.4, (.08, .1, .06), 5),
        wc(p + '-wcf', 3, '.04', 1.2, .35, 3, (.02, .05, .04), 12),
        rim(p + '-lit', 1.2, 1.6, (.85, .78, .62), .7),
        rock(p + '-bk', 7, '.05 .02', 5),
        cloud(p + '-c1', '.006 .01', 3.4, 1.55, 6, '3 3'),
        blur(p + '-b1', .9), blur(p + '-b2', 2), blur(p + '-b3', 3), blur(p + '-b5', 5), blur(p + '-b7', 7.5), blur(p + '-m', 11), blur(p + '-soft', 1.1),
        paper(p, 51), wash(p, 52, .45), foil(p, 40, 560, 460, 640),
    ]
    a = [box(0, 0, 500, 700, u('ground')), box(0, 0, 500, 620, u('wsh'), p + '-c1')]
    # the far wood: soft pale ghosts of bloom, then blurred dark limbs
    far, nearer = '', ''
    for i in range(9):
        far += ghost(r, r.uniform(30, 470), r.uniform(40, 500), 74)
    for i in range(11):
        nearer += ghost(r, r.uniform(20, 480), r.uniform(50, 510), 46)
    a.append(fillp(far, '#bcc8b8', p + '-m', .16))
    a.append(fillp(tapered([(520, 90), (420, 150), (330, 170), (230, 240)], 12, 3) + tapered([(-20, 150), (70, 210), (150, 214)], 11, 3), '#0c1513', p + '-b3', .6))
    a.append(fillp(nearer, '#d2dacb', p + '-b5', .22))
    # a middle tier of smaller blooms, a little soft, so the front branch stands forward
    mid = []
    for k, (x, y, tilt, sq, ln, spin) in enumerate([(182, 288, 18, .84, 54, 20), (322, 258, -22, .8, 58, 40), (252, 112, 8, .86, 56, 12),
                                                    (52, 262, 30, .82, 50, 30), (456, 276, -14, .84, 48, 16)]):
        mid.append(dog_bloom(p, 100 + k * 4, r, x, y, tilt, sq, ln, spin, True))
    a.append('<g filter="url(#%s-b1)" opacity=".66">%s</g>' % (p, ''.join(mid)))
    # the branch with its twigs, each twig ending at a bloom
    wood = []
    for pts, w0, w1 in [([(-12, 500), (60, 472), (150, 440), (238, 412), (318, 392), (398, 372)], 15, 5),
                        ([(150, 440), (128, 404), (104, 372)], 6, 3),
                        ([(238, 412), (246, 340), (250, 250)], 8, 4),
                        ([(178, 431), (150, 340), (122, 250), (110, 156)], 6, 3),
                        ([(318, 392), (350, 300), (374, 210), (392, 128)], 6, 3)]:
        wood.append(fillp(tapered(pts, w0, w1), u('bark')))
    a.append('<g filter="url(#%s-wc)"><g filter="url(#%s-lit)"><g filter="url(#%s-bk)">%s</g></g></g>' % (p, p, p, ''.join(wood)))
    # new leaves in pairs below each bloom
    leaves = [(246, 338, 170, 96, 40, 8), (246, 338, 12, 100, 42, -8), (128, 222, -165, 82, 34, 7),
              (378, 190, 170, 80, 32, 7), (378, 190, 28, 84, 34, -7), (360, 382, 110, 86, 36, 8),
              (124, 398, 130, 78, 32, 8), (60, 472, -118, 70, 30, 6)]
    a.append('<g filter="url(#%s-wc)">%s</g>' % (p, ''.join(leaf(p, i, r, *q) for i, q in enumerate(leaves))))
    # the five front blooms, largest in the middle, drawn last
    blooms = []
    for k, (x, y, tilt, sq, ln, spin) in enumerate([(392, 128, -16, .82, 82, 24), (110, 156, 14, .86, 86, 38), (104, 372, 24, .8, 78, 14),
                                                    (398, 372, -24, .84, 90, 30), (250, 250, 6, .92, 104, 44)]):
        blooms.append(dog_bloom(p, k * 4, r, x, y, tilt, sq, ln, spin))
    a.append('<g filter="url(#%s-wc)">%s</g>' % (p, ''.join(blooms)))
    a.append(box(0, 500, 500, 200, u('foot')))
    a.append(box(0, 0, 500, 700, u('vig')))
    words = [foil_rule(p), foil_line(p, 'Thinking of You', 250, 598, 68), LINE]
    return wrap('dogwood', 'A dogwood branch in bloom', d, bleed(p, a), words)



# ---- A country church, shared by the chapel and the snow card -------------------------

def arch(cam, f, at, hw, v0, v1, rise):
    """An arched opening on a wall. f(a, b) turns along-the-wall a and height b into a world point."""
    pts = [f(at - hw, v0), f(at + hw, v0), f(at + hw, v1)]
    for k in range(1, 6):
        t = k / 6 * math.pi
        pts.append(f(at + hw * math.cos(t), v1 + rise * math.sin(t)))
    pts.append(f(at - hw, v1))
    return poly([cam.pt(*q) for q in pts])


def church(cam, sd, c, snow=False):
    """A white clapboard church from one front corner: nave, a square tower on the gable end, belfry, spire.
    sd says which long wall we see, 1 or -1 (yaw must have the same sign). c holds the paints.
    Returns the painted parts and where the lit windows fall on the page."""
    HW, L, E, R, T = 4, 13, 5.2, 8.4, 1.9
    TH, BH, SH = 12.4, 15, 21
    B = T * .84
    flank = lambda a, b: (sd * HW, b, a)
    tflank = lambda a, b: (sd * T, b, a)
    tfront = lambda a, b: (a, b, -2 * T)
    bflank = lambda a, b: (sd * B, b, a)
    bfront = lambda a, b: (a, b, -T - B)
    out, lights = [], []

    def laps(f, a0, a1, v0, v1, narrow=None):
        d, v = '', v0 + .44
        while v < v1:
            k = narrow(v) if narrow else 1
            d += segment(cam.pt(*f(a0 * k, v)), cam.pt(*f(a1 * k, v)))
            v += .44
        return strokep(d, c['line'], .6, o=.3)

    def window(f, at, hw, v0, v1, rise, keep=True):
        out.append(fillp(arch(cam, f, at, hw + .15, v0 - .15, v1, rise + .15), c['trim']))
        out.append(fillp(arch(cam, f, at, hw, v0, v1, rise), c['glass']))
        out.append(strokep(segment(cam.pt(*f(at, v0)), cam.pt(*f(at, v1 + rise))) + segment(cam.pt(*f(at - hw, (v0 + v1) / 2)), cam.pt(*f(at + hw, (v0 + v1) / 2))),
                           c['dark'], .8, o=.8))
        if snow:
            out.append(strokep(segment(cam.pt(*f(at - hw - .15, v0 - .12)), cam.pt(*f(at + hw + .15, v0 - .12))), c['snow'], 1.7))
        if keep:
            lights.append(cam.pt(*f(at, (v0 + v1) / 2)))

    # the roof, then the long wall with its windows
    out.append(fillp(cam.quad((0, R + .12, -.3), (sd * (HW + .5), E - .34, -.3), (sd * (HW + .5), E - .34, L + .3), (0, R + .12, L + .3)), c['roof']))
    if not snow:
        seams = ''
        for k in (.2, .4, .6, .8):
            a0 = (sd * (HW + .5) * k, R + .12 - (R + .46 - E) * k, -.3)
            seams += segment(cam.pt(*a0), cam.pt(a0[0], a0[1], L + .3))
        out.append(strokep(seams, c['line'], .7, o=.28))
    out.append(fillp(cam.quad(flank(0, 0), flank(L, 0), flank(L, E), flank(0, E)), c['flank']))
    out.append(laps(flank, 0, L, 0, E))
    out.append(fillp(cam.quad(flank(0, 0), flank(L, 0), flank(L, .5), flank(0, .5)), c['stone']))
    for w in (2.4, 5.2, 8, 10.8):
        window(flank, w, .62, 1.7, 3.4, .68)
    out.append(strokep(segment(cam.pt(*flank(0, E)), cam.pt(*flank(L, E))), c['dark'], 1, o=.5))
    # the gable end
    out.append(fillp(cam.quad((-HW, 0, 0), (HW, 0, 0), (HW, E, 0), (0, R, 0), (-HW, E, 0)), c['front']))
    out.append(laps(lambda a, b: (a, b, 0), -HW, HW, 0, R - .3, lambda v: 1 if v < E else (R - v) / (R - E)))
    out.append(fillp(cam.quad((-HW, 0, 0), (HW, 0, 0), (HW, .5, 0), (-HW, .5, 0)), c['stone']))
    out.append(strokep(segment(cam.pt(-HW - .3, E - .24, 0), cam.pt(0, R + .12, 0)) + segment(cam.pt(0, R + .12, 0), cam.pt(HW + .3, E - .24, 0)), c['trim'], 1.5))
    out.append(strokep(segment(cam.pt(sd * HW, .5, 0), cam.pt(sd * HW, E, 0)), c['trim'], 1.2, o=.8))
    window(lambda a, b: (a, b, 0), sd * 2.95, .42, 1.9, 3.3, .42)
    # the tower: shaded side, then its face with the door and a round window
    out.append(fillp(cam.quad(tflank(-2 * T, 0), tflank(0, 0), tflank(0, TH), tflank(-2 * T, TH)), c['flank']))
    out.append(laps(tflank, -2 * T, 0, 0, TH))
    window(tflank, -T, .46, 5.4, 7, .46)
    out.append(fillp(cam.quad(tfront(-T, 0), tfront(T, 0), tfront(T, TH), tfront(-T, TH)), c['front']))
    out.append(laps(tfront, -T, T, 0, TH))
    out.append(strokep(segment(cam.pt(*tfront(sd * T, 0)), cam.pt(*tfront(sd * T, TH))), c['trim'], 1.2, o=.8))
    out.append(fillp(cam.quad((-1.5, .34, -2 * T), (1.5, .34, -2 * T), (1.7, 0, -2 * T - 1), (-1.7, 0, -2 * T - 1)), c['trim']))
    out.append(fillp(arch(cam, tfront, 0, 1, .34, 2.4, .62), c['trim']))
    out.append(fillp(arch(cam, tfront, 0, .82, .34, 2.4, .46), c['door']))
    out.append(strokep(segment(cam.pt(*tfront(0, .34)), cam.pt(*tfront(0, 2.86))), c['dark'], .8, o=.7))
    ring = [tfront(.72 * math.cos(k * .628), 5.8 + .72 * math.sin(k * .628)) for k in range(10)]
    out.append(fillp(poly([cam.pt(*q) for q in ring]), c['glass']))
    out.append(strokep(poly([cam.pt(*q) for q in ring]), c['trim'], 1.3))
    lights.append(cam.pt(*tfront(0, 5.8)))
    # cornice, belfry with louvers, cornice, spire, cross
    out.append(fillp(cam.quad((sd * (T + .18), TH, -2 * T - .18), (sd * (T + .18), TH, .18), (sd * (T + .18), TH + .4, .18), (sd * (T + .18), TH + .4, -2 * T - .18)), c['trim']))
    out.append(fillp(cam.quad((-T - .18, TH, -2 * T - .18), (T + .18, TH, -2 * T - .18), (T + .18, TH + .4, -2 * T - .18), (-T - .18, TH + .4, -2 * T - .18)), c['trim']))
    out.append(fillp(cam.quad(bflank(-T - B, TH + .4), bflank(-T + B, TH + .4), bflank(-T + B, BH), bflank(-T - B, BH)), c['flank']))
    out.append(fillp(cam.quad(bfront(-B, TH + .4), bfront(B, TH + .4), bfront(B, BH), bfront(-B, BH)), c['front']))
    for f, at in ((bflank, -T), (bfront, 0)):
        out.append(fillp(arch(cam, f, at, B * .6, TH + .9, BH - .9, .5), c['dark']))
        lou, v = '', TH + 1.1
        while v < BH - .5:
            lou += segment(cam.pt(*f(at - B * .6, v)), cam.pt(*f(at + B * .6, v)))
            v += .28
        out.append(strokep(lou, c['trim'], .6, o=.7))
    out.append(fillp(cam.quad((sd * (B + .14), BH, -T - B - .14), (sd * (B + .14), BH, -T + B + .14), (sd * (B + .14), BH + .3, -T + B + .14), (sd * (B + .14), BH + .3, -T - B - .14)), c['trim']))
    out.append(fillp(cam.quad((-B - .14, BH, -T - B - .14), (B + .14, BH, -T - B - .14), (B + .14, BH + .3, -T - B - .14), (-B - .14, BH + .3, -T - B - .14)), c['trim']))
    q = B + .08
    out.append(fillp(cam.quad((sd * q, BH + .3, -T - q), (sd * q, BH + .3, -T + q), (0, SH, -T)), c['spire2']))
    out.append(fillp(cam.quad((-q, BH + .3, -T - q), (q, BH + .3, -T - q), (0, SH, -T)), c['spire']))
    out.append(strokep(segment(cam.pt(0, SH - .1, -T), cam.pt(0, SH + 1.5, -T)) + segment(cam.pt(-.46, SH + 1, -T), cam.pt(.46, SH + 1, -T)), c['cross'], 1.3))
    return ''.join(out), lights


# ---- 8. Chapel -----------------------------------------------------------------------

def chapel():
    p, r = 'cp', random.Random(118)
    u = lambda k: 'url(#%s-%s)' % (p, k)
    X0, Y0, X1, Y1, HZ = 34, 34, 466, 666, 438
    W_ = X1 - X0
    d = [
        lin(p + '-sky', [(0, '#262c49'), (.24, '#3f4566'), (.46, '#6a6a83'), (.64, '#a08f94'), (.8, '#cfae98'), (.92, '#ecd0a6'), (1, '#f6e4bd')],
            0, Y0, 0, HZ + 2, user=True),
        rad(p + '-glow', [(0, '#fdeec6', .9), (.42, '#f1cf9e', .4), (1, '#d3a58a', 0)]),
        lin(p + '-cl1', [(0, '#1a1f38', .8), (.6, '#2a2f4c', .6), (1, '#454864', 0)]),
        lin(p + '-cl2', [(0, '#6e6780', 0), (.5, '#94808a', .6), (1, '#e4bd9c', .7)]),
        lin(p + '-far', [(0, '#7d8299'), (1, '#d6bda6')]),
        lin(p + '-far2', [(0, '#565e76'), (1, '#a9a09c')]),
        lin(p + '-wood', [(0, '#1b282e'), (.7, '#18242a'), (1, '#2c3836')], 0, 120, 0, 446, user=True),
        lin(p + '-field', [(0, '#d6bb8c'), (.05, '#ac9a73'), (.16, '#676855'), (.32, '#333a36'), (.55, '#171e20'), (1, '#0a0e11')], 0, HZ, 0, Y1, user=True),
        lin(p + '-path', [(0, '#e4cfa6', .85), (.55, '#b6a382', .4), (1, '#8d8066', 0)], 0, 456, 0, 572, user=True),
        lin(p + '-front', [(0, '#fbf1df'), (.6, '#efe0cc'), (1, '#d9c5b4')], 0, 0, 1, .2),
        lin(p + '-flank', [(0, '#a9a3ae'), (.6, '#8b8798'), (1, '#6e6c80')], 0, 0, 1, 0),
        lin(p + '-roof', [(0, '#59525c'), (1, '#2f2c3a')], 0, 0, 1, .6),
        lin(p + '-spire', [(0, '#8a7e84'), (1, '#5c5460')], 0, 0, 1, 0),
        lin(p + '-glass', [(0, '#fbe3a6'), (1, '#e3a95c')]),
        rad(p + '-lamp', [(0, '#fff0c0', .6), (.4, '#f8d48e', .25), (1, '#f0bd70', 0)]),
        rad(p + '-vig', [(.55, '#070a12', 0), (1, '#070a12', .62)], .5, .46, .82),
        wc(p + '-wc', 6, '.03 .05', 2.4, .55, 3, (.03, .04, .07), 7),
        wc(p + '-wcf', 5, '.03 .05', 3, .4, 3, (.14, .13, .18), 13),
        wc(p + '-wcn', 3, '.05', 1.6, .4, 2, (.02, .03, .05), 17),
        wc(p + '-wcb', 1.2, '.06', .6, .3, 2, (.05, .04, .08), 23),
        cloud(p + '-c1', '.0034 .03', 3.4, 1.6, 8, '1.6 .8'),
        cloud(p + '-c2', '.006 .05', 3.5, 1.55, 15, '1 .6'),
        blur(p + '-b06', .6), blur(p + '-b1', 1), blur(p + '-b2', 2.2), blur(p + '-m', 10), blur(p + '-soft', 1.1),
        paper(p, 81), wash(p, 82, .6), foil(p, 50, 556, 450, 640), scene_clip(p),
    ]
    s = [box(X0, Y0, W_, HZ - Y0 + 2, u('sky')), oval(226, HZ - 4, 330, 150, u('glow')),
         box(X0, Y0, W_, 200, u('cl1'), p + '-c1'), box(X0, 240, W_, 170, u('cl2'), p + '-c2')]
    s.append(fillp(land(ridge(r, X0 - 12, X1 + 12, 410, 9), HZ + 2), u('far'), p + '-wcf', .9))
    s.append(oval(220, 422, 240, 8, '#f8e6c0', p + '-m', .6))
    s.append(fillp(canopy(r, X0 - 12, X1 + 12, lambda x: 424 + 4 * math.sin(x * .03), HZ + 2, 11), u('far2'), p + '-wcf'))
    # pines on the left, oaks on the right, a gap of evening sky left for the steeple
    envl = lambda x: 70 + 260 * max(0, 1 - (x - 20) / 170) ** 1.1
    s.append(fillp(stand(r, 150, 200, lambda x: 90, 16, .3, HZ + 6) + stand(r, 20, 176, lambda x: envl(x) * .9, 15, .3, HZ + 6), '#4c5a68', p + '-wc', .8))
    s.append(fillp(stand(r, 18, 158, envl, 20, .34, HZ + 6), u('wood'), p + '-wc'))
    oak = ['#162226', '#1f2f2e', '#2f4036', '#5c5a4a']
    s.append(tree(r, 430, 322, 74, 118, 150, 16, oak, p + '-wc', (-.8, -.5)))
    s.append(tree(r, 348, 384, 72, 56, 90, 13, oak, p + '-wc', (-.8, -.5)))
    s.append(box(X0, HZ, W_, Y1 - HZ, u('field')))
    s.append(oval(214, HZ + 6, 230, 8, '#f6e2b8', p + '-m', .55))
    # the worn path up to the door, gone before the words begin
    s.append(fillp(smooth([(202, 458), (192, 474), (166, 500), (150, 530), (170, 574)]) + 'L' + smooth([(280, 574), (226, 534), (212, 502), (222, 474), (214, 458)])[1:] + 'Z', u('path')))
    # the church, front lit by what is left of the sun, one or two lamps on inside
    paints = {'front': u('front'), 'flank': u('flank'), 'roof': u('roof'), 'spire': '#8d8088', 'spire2': '#544e5c', 'trim': '#f4ebdb', 'glass': u('glass'),
              'dark': '#2c2a34', 'line': '#5c5664', 'stone': '#6e6a6c', 'door': '#3a2c2c', 'cross': '#2c2a34'}
    cam = Cam(250, HZ, 660, 1.6, 60, 36, -1.5)
    parts, lights = church(cam, 1, paints)
    s.append('<ellipse cx="270" cy="464" rx="108" ry="7" fill="#101418" opacity=".5" filter="url(#%s-b2)"></ellipse>' % p)
    s.append('<g filter="url(#%s-wcb)">%s</g>' % (p, parts))
    for x, y in lights[:4]:
        s.append(oval(x, y, 15, 15, u('lamp')))
    # grasses at the church's foot, then the dark meadow toward us, kept quiet under the words
    near = sward(r, 220, X0 - 10, X1 + 10, 458, 556, 6, 30, 7, 1, 2.6)
    for k, col in enumerate(['#6b6a52', '#3e4438', '#1f2726']):
        s.append(fillp(near[k], col, o=.85))
    low = sward(r, 150, X0 - 10, X1 + 10, 556, Y1 + 10, 26, 52, 11, 2.2, 3.6, 2)
    for k, col in enumerate(['#141a1c', '#0d1214']):
        s.append(fillp(low[k], col, p + '-b06'))
    # an oak limb close to us across the top left, nearly black
    s.append('<g filter="url(#%s-wcn)">%s%s</g>' % (p, fillp(tapered([(20, 124), (86, 104), (150, 82), (222, 70)], 14, 2.5), '#0d1218'), fillp(tapered([(92, 102), (128, 124), (176, 134)], 5, 1.5), '#0d1218')))
    limb = ''
    for i in range(70):
        t = r.random()
        if i % 3 == 0:
            limb += dab(r, 112 + 68 * t + r.uniform(-14, 14), 126 + 12 * t + r.uniform(-12, 16), r.uniform(5, 9), r.uniform(4, 7))
        else:
            limb += dab(r, 30 + 190 * t + r.uniform(-14, 14), 112 - 44 * t + r.uniform(-20, 18), r.uniform(5, 10), r.uniform(4, 8))
    s.append(fillp(limb, '#0f161c', p + '-wcn'))
    s.append(box(X0, Y0, W_, Y1 - Y0, u('vig')))
    words = [mat_rules(p, '#1c2030'), foil_line(p, 'With Sympathy', 250, 610, 70)]
    return wrap('chapel', 'A small white country church among trees at evening', d, inset(p, s), words)



# ---- 9. Church in snow ---------------------------------------------------------------

def snow_pine(r, x, base, h, w):
    """A pine under snow: the dark tree, and white lenses lying along its boughs."""
    tree_, snow = pine(r, x, base, h, w), ''
    tiers = max(5, int(h / 12))
    for i in range(1, tiers + 1):
        t = i / tiers
        half = w / 2 * t ** .92
        snow += lens(x - half * r.uniform(.55, .95), base - h + h * t + r.uniform(-1, 3), half * r.uniform(1, 1.9), 1.4 + h * .014)
    return tree_, snow


def bare(r, x, y, ang, length, depth, levels):
    """A winter hardwood: each limb forks into thinner ones, one path per thickness."""
    th = math.radians(ang)
    ex, ey = x + math.cos(th) * length, y + math.sin(th) * length
    mx, my = (x + ex) / 2 + r.uniform(-.12, .12) * length, (y + ey) / 2 + r.uniform(-.12, .12) * length
    levels[depth] += 'M%s %sQ%s %s %s %s' % (n(x), n(y), n(mx), n(my), n(ex), n(ey))
    if depth:
        for k in range(2 if depth > 3 or r.random() < .7 else 1):
            bare(r, ex, ey, ang + r.uniform(-34, -12) * (1 if k else -1), length * r.uniform(.68, .8), depth - 1, levels)


def snowchurch():
    p, r = 'sc', random.Random(1225)
    u = lambda k: 'url(#%s-%s)' % (p, k)
    X0, Y0, X1, Y1, HZ = 34, 34, 466, 666, 470
    W_ = X1 - X0
    d = [
        lin(p + '-sky', [(0, '#060b22'), (.22, '#0c1634'), (.44, '#18264c'), (.62, '#2f3b68'), (.76, '#5c5f86'), (.87, '#a78c94'), (.95, '#e3b793'), (1, '#f5d4a4')],
            0, Y0, 0, HZ + 2, user=True),
        rad(p + '-glow', [(0, '#ffdfa8', .85), (.4, '#e8ae8c', .4), (1, '#a98a9c', 0)]),
        lin(p + '-cl1', [(0, '#040820', .9), (.6, '#0a1230', .7), (1, '#1a2448', 0)]),
        lin(p + '-cl2', [(0, '#3c4470', 0), (.5, '#6a6688', .6), (1, '#c79a92', .66)]),
        lin(p + '-far', [(0, '#6c759c'), (.6, '#a7a4bc'), (1, '#dfc6bc')]),
        lin(p + '-far2', [(0, '#2c3760'), (1, '#6c6f96')]),
        lin(p + '-s1', [(0, '#e9dcdc'), (.3, '#b4b6d0'), (1, '#6f7cab')], 0, HZ, 0, 560, user=True),
        lin(p + '-s2', [(0, '#dfe2f2'), (.34, '#a7b0d2'), (.7, '#6a78a8'), (1, '#2e3a68')], 0, 496, 0, 680, user=True),
        lin(p + '-s3', [(0, '#a4aed2'), (.4, '#5c6a9c'), (1, '#1a2450')], 0, 572, 0, 680, user=True),
        lin(p + '-front', [(0, '#d9dced'), (.6, '#bcc3dc'), (1, '#9ca5c6')], 0, 0, 1, .2),
        lin(p + '-flank', [(0, '#6f7aa2'), (.6, '#616c96'), (1, '#515c86')], 0, 0, 1, 0),
        lin(p + '-roof', [(0, '#f1f2f8'), (.6, '#cdd3e6'), (1, '#9aa6c8')], 0, 0, 1, .6),
        lin(p + '-glass', [(0, '#fff2bc'), (.5, '#fcc968'), (1, '#e48c38')]),
        rad(p + '-lamp', [(0, '#ffe6a0', .85), (.35, '#fbbf6c', .4), (1, '#ef9a4a', 0)]),
        rad(p + '-pool', [(0, '#ffc877', .7), (.5, '#f5a95c', .3), (1, '#e68f4c', 0)]),
        rad(p + '-vig', [(.55, '#030618', 0), (1, '#030618', .66)], .5, .46, .82),
        wc(p + '-wc', 5, '.03 .05', 2.2, .5, 3, (.03, .05, .12), 7),
        wc(p + '-wcf', 4, '.03 .05', 2.4, .4, 3, (.3, .32, .46), 13),
        wc(p + '-wcn', 2, '.06', 1.2, .3, 2, (.02, .03, .1), 19),
        wc(p + '-wcb', 1.2, '.06', .6, .3, 2, (.06, .08, .18), 23),
        cloud(p + '-c1', '.0034 .03', 3.4, 1.6, 8, '1.6 .8'),
        cloud(p + '-c2', '.006 .05', 3.5, 1.56, 15, '1 .6'),
        blur(p + '-b06', .5), blur(p + '-b1', 1), blur(p + '-b2', 2.2), blur(p + '-m', 10), blur(p + '-soft', 1.1),
        paper(p, 91), wash(p, 92, .55), foil(p, 60, 70, 440, 230), scene_clip(p),
    ]
    s = [box(X0, Y0, W_, HZ - Y0 + 2, u('sky'))]
    bright, dim = '', ''
    for i in range(46):
        x, y, rr = r.uniform(X0, X1), r.uniform(Y0, 330), r.uniform(.5, 1.1)
        star = 'M%s %sa%s %s 0 1 0 .1 0Z' % (n(x), n(y), n(rr), n(rr))
        if i % 4:
            dim += star
        else:
            bright += star
    s.append(fillp(dim, '#cfd8f0', o=.42))
    s.append(fillp(bright, '#f4f0dc', o=.8))
    s.append(oval(372, HZ - 4, 320, 130, u('glow')))
    s.append(box(X0, Y0, W_, 180, u('cl1'), p + '-c1'))
    s.append(box(X0, 330, W_, 130, u('cl2'), p + '-c2'))
    # far hills white on top, a far wood, then the near pines under snow
    s.append(fillp(land(ridge(r, X0 - 12, X1 + 12, 444, 11), HZ + 2), u('far'), p + '-wcf'))
    s.append(fillp(canopy(r, X0 - 12, X1 + 12, lambda x: 458 + 4 * math.sin(x * .025), HZ + 4, 10), u('far2'), p + '-wcf'))
    s.append(oval(380, 466, 200, 6, '#f6d6ae', p + '-m', .5))
    s.append(fillp(land(ridge(r, X0 - 12, X1 + 12, 478, 5), 570), u('s1'), p + '-wcf'))
    dark, snow = '', ''
    for x, base, h in [(452, 500, 176), (416, 496, 140), (476, 508, 130), (392, 494, 92), (192, 492, 104), (160, 490, 126), (128, 492, 96), (214, 492, 72)]:
        t_, w_ = snow_pine(r, x, base, h, h * .44)
        dark += t_
        snow += w_
    s.append(fillp(dark, '#16233f', p + '-wcn'))
    s.append(fillp(snow, '#d3daee', p + '-wcn', .9))
    # the church, roof deep in snow, every window lit
    paints = {'front': u('front'), 'flank': u('flank'), 'roof': u('roof'), 'spire': '#c6cde2', 'spire2': '#5f6a94', 'trim': '#e6e9f4', 'glass': u('glass'),
              'dark': '#2a2c4a', 'line': '#3c466e', 'stone': '#4a5078', 'door': u('glass'), 'cross': '#20264a', 'snow': '#f4f5fb'}
    cam = Cam(250, HZ, 560, 3, 60, -38, 6.15)
    parts, lights = church(cam, -1, paints, snow=True)
    s.append('<g filter="url(#%s-wcb)">%s</g>' % (p, parts))
    door = cam.pt(0, 1.4, -3.8)
    for x, y in lights:
        s.append(oval(x, y, 24, 24, u('lamp')))
    s.append(oval(door[0], door[1], 30, 34, u('lamp')))
    # the snow in front, which buries the foundation, with lamplight lying on it
    s.append(fillp(land(ridge(r, X0 - 12, X1 + 12, 504, 3), 680), u('s2'), p + '-wcf'))
    for x, y in lights[:4]:
        s.append(oval(x - 8, 514, 34, 9, u('pool')))
    s.append(oval(door[0] - 6, 516, 48, 16, u('pool')))
    # a trodden path from the door down toward us
    walk = [(door[0], 506), (324, 530), (296, 566), (268, 606), (236, 650), (214, 690)]
    s.append(fillp(tapered(walk, 7, 42), '#4f5c8e', p + '-b1', .5))
    s.append(fillp(tapered([(q[0] + 3, q[1] + 1) for q in walk], 2, 8), '#c9d0e6', p + '-b1', .4))
    # the old fence, its top rail carrying a line of snow
    posts = [(50, 640, 70), (118, 612, 52), (176, 592, 40), (226, 578, 31), (264, 569, 25)]
    wood, cap = '', ''
    for (x0, y0, h0), (x1, y1, h1) in zip(posts, posts[1:]):
        for k in (.84, .48):
            wood += poly([(x0, y0 - h0 * k), (x1, y1 - h1 * k), (x1, y1 - h1 * k + 3), (x0, y0 - h0 * k + 4.4)])
        ax, ay, bx, by = x0, y0 - h0 * .84 - 1, x1, y1 - h1 * .84 - 1
        cap += sliver(ax, ay, math.degrees(math.atan2(by - ay, bx - ax)), math.hypot(bx - ax, by - ay), 3.2)
    for x, y, h in posts:
        wood += poly([(x - 3.6, y - h), (x + 3.6, y - h - 1), (x + 3.6, y + 3), (x - 3.6, y + 3)])
        cap += lens(x - 6.4, y - h - 1, 12.8, 5)
    s.append(fillp(wood, '#1d2138', p + '-wcn'))
    s.append(fillp(cap, '#eef0f8', o=.92))
    # a bare oak at the left, close to us, snow along its big limbs
    levels = [''] * 8
    bare(r, 74, 470, -82, 66, 7, levels)
    s.append(fillp(tapered([(66, 560), (70, 520), (74, 470)], 19, 9), '#10152e', p + '-wcn'))
    s.append('<g filter="url(#%s-wcn)" stroke-linecap="round">%s</g>' % (p, ''.join(strokep(levels[k], '#10152e', n(.7 + k * 1.02)) for k in range(8))))
    s.append(strokep(levels[7] + levels[6], '#d7ddef', 1.1, o=.6, more='transform="translate(0 -3)"'))
    # the drift nearest us, its long blue shadow, and a quiet fall of snow
    s.append(fillp(land(ridge(r, X0 - 12, X1 + 12, 618, 12), 680), u('s3'), p + '-wcf'))
    shadow = ''
    for i in range(9):
        shadow += lens(r.uniform(X0 - 40, 300), r.uniform(630, 664), r.uniform(120, 240), r.uniform(1.6, 3.6))
    s.append(fillp(shadow, '#0e1640', p + '-b1', .3))
    flakes, soft = '', ''
    for i in range(84):
        x, y, rr = r.uniform(X0, X1), r.uniform(Y0 + 10, Y1), r.uniform(.8, 1.9)
        flake = 'M%s %sa%s %s 0 1 0 .1 0Z' % (n(x), n(y), n(rr), n(rr))
        if i % 3:
            flakes += flake
        else:
            soft += flake
    s.append(fillp(soft, '#e6ecfa', p + '-b1', .5))
    s.append(fillp(flakes, '#f4f6fc', o=.6))
    s.append(box(X0, Y0, W_, Y1 - Y0, u('vig')))
    words = [mat_rules(p, '#0c1430'), foil_line(p, 'Merry', 250, 122, 96), foil_line(p, 'Christmas', 250, 208, 96), LINE]
    return wrap('snowchurch', 'A country church in the snow on a Christmas evening', d, inset(p, s), words)



# ---- 10. Lilies ----------------------------------------------------------------------

def vadd(a, b, k=1):
    return (a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def vunit(a):
    k = math.sqrt(vdot(a, a)) or 1
    return (a[0] / k, a[1] / k, a[2] / k)


def lily_bloom(p, d, i0, O, A, S, phi0):
    """One open lily, worked out in 3D so the foreshortening is true: six curved ribbons round axis A,
    sorted back to front. O is the throat on the page, S the flower's size. Each tepal adds its own gradient to d."""
    A = vunit(A)
    e1 = vunit(vcross(A, (0, 0, 1)))
    e2 = vcross(A, e1)
    sun = vunit((-.5, -.65, .57))
    ts = [j / 12 for j in range(13)]
    out = []

    def ring(ang):
        c, s = math.cos(ang), math.sin(ang)
        return vadd(vadd((0, 0, 0), e1, c), e2, s), vadd(vadd((0, 0, 0), e1, -s), e2, c)

    items = []
    for k in range(6):
        ur, ut = ring(math.radians(phi0 + k * 60))
        W, reach = (.31, 1) if k % 2 == 0 else (.24, .96)

        def at(t, s, ur=ur, ut=ut, W=W, reach=reach):
            along = math.sin(1.95 * t) / .93 * reach + .16 * s * s * math.sin(math.pi * t)
            out_ = (.06 + .1 * t + .62 * t ** 3) * reach
            w = W * (.16 + .84 * abs(math.sin(math.pi * t ** 1.25)) ** .8) * (1 - t ** 8)
            q = vadd(vadd(vadd((0, 0, 0), A, along), ur, out_), ut, s * w)
            return (O[0] + S * q[0], O[1] + S * q[1], S * q[2])
        items.append((sum(at(t, 0)[2] for t in ts) / len(ts), k, at, ut))
    items.sort(key=lambda q: q[0])

    # the tube behind the flower, running back to the stalk
    rear = (O[0] - A[0] * S * .5, O[1] - A[1] * S * .5)
    out.append(fillp(tapered([rear, ((rear[0] + O[0]) / 2, (rear[1] + O[1]) / 2 + 3), O[:2]], S * .075, S * .19), 'url(#%s-tube)' % p))

    for _, k, at, ut in items:
        i = i0 + k
        left = [at(t, -1)[:2] for t in ts]
        right = [at(t, 1)[:2] for t in ts[::-1]]
        mid = [at(t, 0)[:2] for t in ts]
        shape = outline(left, right)
        # which way this ribbon faces decides how much of the sky it gets
        dt = vadd(at(.6, 0), at(.5, 0), -1)
        ds = vadd(at(.55, .5), at(.55, -.5), -1)
        nrm = vunit(vcross(dt, ds))
        if nrm[2] < 0:
            nrm = (-nrm[0], -nrm[1], -nrm[2])
        tone = .52 + .48 * max(0, vdot(nrm, sun)) ** .8
        d.append(lin('%s-g%d' % (p, i), [(0, '#8d9458'), (.16, '#c5c695'), (.4, mix('#7d7c7e', '#fffcf0', tone * .96)), (.75, mix('#8a898a', '#fffdf4', tone)),
                                         (1, mix('#77767a', '#f8f2dc', tone))], n(mid[0][0]), n(mid[0][1]), n(mid[-1][0]), n(mid[-1][1]), user=True))
        lit = 1 if vdot(ut, sun) > 0 else -1
        along_lit = [at(t, .5 * lit)[:2] for t in ts[2:12]]
        along_dark = [at(t, -.62 * lit)[:2] for t in ts[1:12]]
        form = '%s-f%d' % (p, i)
        out.append(held(form, shape))
        out.append(use(form, '#040306', p + '-b5', .42, 'transform="translate(3 8)"'))
        out.append(clip_of('%s-t%d' % (p, i), form))
        out.append('<g clip-path="url(#%s-t%d)">' % (p, i))
        out.append(use(form, 'url(#%s-g%d)' % (p, i)))
        out.append(strokep(smooth(along_dark), '#55544e', n(S * .05), p + '-b5', .46))
        out.append(strokep(smooth(along_lit), '#ffffff', n(S * .035), p + '-b3', .8))
        out.append(oval(O[0], O[1], S * .2, S * .2, '#39451f', p + '-b7', .62))
        out.append(strokep(smooth(mid[1:11]), '#8a8a58', 3, p + '-b2', .4))
        veins = ''.join(smooth([at(t, q)[:2] for t in ts[1:12:2]]) for q in (-.7, -.45, -.22, .22, .45, .7))
        out.append(strokep(veins, '#a09a70', .7, o=.28))
        out.append('</g>')
        out.append(use(form, 'none', more='stroke="#55524a" stroke-width=".8" stroke-opacity=".4"'))
    # stamens and the pistil, standing out of the throat
    an = ''
    hi = ''
    for k in range(6):
        ur, ut = ring(math.radians(phi0 + 30 + k * 60))
        q = [vadd(vadd((0, 0, 0), A, a_), ur, b_) for a_, b_ in ((.12, .03), (.5, .07), (.86, .16))]
        pts = [(O[0] + S * c[0], O[1] + S * c[1] + j * S * .018) for j, c in enumerate(q)]
        out.append(strokep(smooth(pts), '#e6e5bd', 1.8))
        ang = math.degrees(math.atan2(ut[1], ut[0]))
        x, y = pts[-1]
        th = math.radians(ang)
        length = S * .09
        an += sliver(x - math.cos(th) * length / 2, y - math.sin(th) * length / 2, ang, length, S * .05)
        hi += sliver(x - math.cos(th) * length / 3, y - math.sin(th) * length / 3 - 1, ang, length * .66, S * .018)
    q = [vadd((0, 0, 0), A, a_) for a_ in (.1, .55, .98)]
    pts = [(O[0] + S * c[0], O[1] + S * c[1] + j * S * .012) for j, c in enumerate(q)]
    out.append(strokep(smooth(pts), '#dcdeb4', 3))
    out.append(fillp(an, '#6e3f16'))
    out.append(fillp(hi, '#c99a4a'))
    out.append(oval(pts[-1][0], pts[-1][1], S * .03, S * .028, '#aeb870', more='stroke="#6d7440" stroke-width=".8"'))
    return ''.join(out)


def lily_bud(p, x, y, ang, length):
    up = [(0, 0), (.18, -.1), (.42, -.17), (.68, -.19), (.86, -.13), (1, 0)]
    lo = [(1, 0), (.86, .13), (.68, .19), (.42, .17), (.18, .1), (0, 0)]
    run = lambda q: [(a * length, b * length) for a, b in q]
    shape = outline(run(up), run(lo))
    return ('<g transform="translate(%s %s) rotate(%s)">%s%s%s</g>' % (
        n(x), n(y), ang, fillp(shape, 'url(#%s-bud)' % p),
        strokep('M%s %sQ%s %s %s 0M%s %sQ%s %s %s 0' % (n(length * .1), n(length * .03), n(length * .6), n(-length * .09), n(length * .98),
                                                         n(length * .1), n(-length * .03), n(length * .6), n(length * .1), n(length * .98)), '#8d9458', 1, o=.5),
        oval(length * .56, -length * .08, length * .26, length * .035, '#ffffff', p + '-b3', .6)))


def lance(p, x, y, ang, length, width, bend):
    """A long lily leaf: lit half, shaded half, a pale midrib, two fine veins running with it."""
    k = 10
    top, bot, mid = [], [], []
    for j in range(k + 1):
        t = j / k
        c = bend * math.sin(math.pi * t)
        w = width * .5 * math.sin(math.pi * t ** .7) ** .9
        mid.append((t * length, c))
        top.append((t * length, c - w))
        bot.append((t * length, c + w))
    half = lambda e: outline(e, mid[::-1])
    return ('<g transform="translate(%s %s) rotate(%s)">%s%s%s%s</g>' % (
        n(x), n(y), ang, fillp(half(top), 'url(#%s-lfa)' % p), fillp(outline(mid, bot[::-1]), 'url(#%s-lfb)' % p),
        strokep(smooth(mid[:10]), '#8fa07a', 1.2, o=.5),
        strokep(smooth([(q[0], q[1] - width * .2) for q in mid[1:9]]) + smooth([(q[0], q[1] + width * .2) for q in mid[1:9]]), '#7f9270', .7, o=.24)))


def lily():
    p, r = 'ly', random.Random(203)
    u = lambda k: 'url(#%s-%s)' % (p, k)
    d = [
        rad(p + '-ground', [(0, '#3c3236'), (.4, '#262025'), (.75, '#151117'), (1, '#0b090e')], .46, .34, .84),
        rad(p + '-light', [(0, '#6b5c50', .5), (.5, '#4a3f3c', .2), (1, '#2a2226', 0)]),
        lin(p + '-wsh', [(0, '#544a50', 0), (.5, '#544a50', .4), (1, '#3c343a', 0)]),
        lin(p + '-tube', [(0, '#b9c088'), (.6, '#e2e0bc'), (1, '#f4f1dc')], 0, 0, 1, 0),
        lin(p + '-bud', [(0, '#fbf8e8'), (.5, '#e6e5c6'), (1, '#9aa268')], 0, 0, 0, 1),
        lin(p + '-stalk', [(0, '#8c9a64'), (.5, '#55663f'), (1, '#27331f')], 0, 0, 1, 0),
        lin(p + '-lfa', [(0, '#4f6a48'), (1, '#2c4430')], 0, 0, 1, .3),
        lin(p + '-lfb', [(0, '#1d3022'), (1, '#121f18')], 0, 0, 1, .3),
        lin(p + '-foot', [(0, '#08070a', 0), (.55, '#08070a', .78), (1, '#060508', .95)], 0, 510, 0, 600, user=True),
        rad(p + '-vig', [(.58, '#050407', 0), (1, '#050407', .6)], .5, .44, .84),
        wc(p + '-wc', 2.2, '.05', .8, .3, 2.2, (.1, .09, .06), 5),
        wc(p + '-wcg', 3, '.04', 1.2, .35, 3, (.02, .03, .02), 12),
        cloud(p + '-c1', '.006 .011', 3.4, 1.55, 6, '3 3'),
        blur(p + '-b2', 2), blur(p + '-b3', 3), blur(p + '-b5', 5), blur(p + '-b7', 7.5), blur(p + '-m', 12), blur(p + '-soft', 1.1),
        paper(p, 31), wash(p, 32, .35), foil(p, 40, 570, 460, 640),
    ]
    a = [box(0, 0, 500, 700, u('ground')), oval(214, 250, 300, 300, u('light')), box(0, 0, 500, 640, u('wsh'), p + '-c1')]
    # the stalk, its side stems and leaves, all well back in the dark
    g = [fillp(tapered([(238, 720), (240, 620), (246, 520), (256, 430), (272, 350), (296, 280), (322, 216), (344, 162), (372, 128)], 13, 4.5), u('stalk')),
         fillp(tapered([(258, 420), (272, 388), (287, 358)], 6, 4), u('stalk')),
         fillp(tapered([(248, 476), (224, 432), (206, 388)], 6.5, 4), u('stalk')),
         fillp(tapered([(249, 486), (312, 508), (372, 498)], 6, 3.5), u('stalk'))]
    g.append(lance(p, 242, 575, -158, 122, 25, -12))
    g.append(lance(p, 243, 560, -20, 122, 25, 12))
    g.append(lance(p, 245, 536, -150, 158, 31, -17))
    g.append(lance(p, 247, 516, -27, 160, 32, 15))
    g.append(lance(p, 255, 436, -152, 120, 26, -13))
    g.append(lance(p, 262, 396, -30, 112, 25, 12))
    g.append(lance(p, 300, 270, -150, 90, 21, -9))
    g.append(lance(p, 330, 200, 16, 96, 22, 9))
    a.append('<g filter="url(#%s-wcg)">%s</g>' % (p, ''.join(g)))
    # two buds, still shut
    a.append('<g filter="url(#%s-wc)">%s%s</g>' % (p, lily_bud(p, 372, 128, -20, 96), lily_bud(p, 372, 498, -8, 84)))
    # the three lilies, lowest first so the largest lies over them
    blooms = [lily_bloom(p, d, 20, (170, 394), (-.6, .1, .79), 120, 5),
              lily_bloom(p, d, 10, (321, 368), (.55, .16, .82), 125, 25),
              lily_bloom(p, d, 0, (295, 210), (-.45, .12, .885), 165, 12)]
    a.append('<g filter="url(#%s-wc)">%s</g>' % (p, ''.join(blooms)))
    a.append(box(0, 510, 500, 190, u('foot')))
    a.append(box(0, 0, 500, 700, u('vig')))
    words = [foil_rule(p), foil_line(p, 'In Sympathy', 250, 620, 80)]
    return wrap('lily', 'White lilies on a dark, quiet ground', d, bleed(p, a), words)



# ---- 11. Hydrangea in a crock ---------------------------------------------------------

def floret(p):
    """One four-petaled floret, drawn once with no fill of its own so each use can color it."""
    pet = [(3.6, -1.6), (6.4, -5), (4.4, -8.6), (2.6, -10.8), (-2.6, -10.8), (-4.4, -8.6), (-6.4, -5), (-3.6, -1.6)]

    def turned(pts, deg, k=1):
        th = math.radians(deg)
        c, s = math.cos(th), math.sin(th)
        q = [(k * (x * c - y * s), k * (x * s + y * c)) for x, y in pts]
        return 'M0 0C' + 'C'.join('%s %s %s %s %s %s' % (n(a[0]), n(a[1]), n(b[0]), n(b[1]), n(e[0]), n(e[1])) for a, b, e in (q[:3], q[3:6], (q[6], q[7], (0, 0)))) + 'Z'
    whole = ''.join(turned(pet, a) for a in (0, 90, 180, 270))
    throat = ''.join(turned(pet, a, .52) for a in (0, 90, 180, 270))
    crease = ''.join(segment(turned_pt, end) for turned_pt, end in (((0, -2), (0, -8)), ((2, 0), (8, 0)), ((0, 2), (0, 8)), ((-2, 0), (-8, 0))))
    return ('<g id="%s-fl"><path d="%s" stroke="#0c0a24" stroke-opacity=".3" stroke-width=".5"></path>'
            '<path d="%s" fill="#0c0a24" fill-opacity=".22"></path>'
            '<path d="%s" fill="none" stroke="#ffffff" stroke-opacity=".16" stroke-width=".7"></path>'
            '<circle r="1.5" fill="#eee8c8" stroke="#3a3a2a" stroke-width=".4"></circle></g>' % (p, whole, throat, crease))


def mophead(p, r, cx, cy, R, shadow, mid, light, count=120):
    """A globe of florets laid out evenly on a sphere, each turned to its own part of the curve and
    colored by how much of the window it sees, then painted back to front."""
    sun = (-.5, -.62, .6)
    fl = []
    for i in range(count):
        z = 1 - (i + .5) / count * 1.3
        rho = math.sqrt(max(0, 1 - z * z))
        a = i * 2.39996
        x, y = rho * math.cos(a) + r.uniform(-.03, .03), rho * math.sin(a) + r.uniform(-.03, .03)
        t = (.5 + .5 * (x * sun[0] + y * sun[1] + z * sun[2])) * (.55 + .45 * max(z, 0) ** .5) + r.uniform(-.07, .07)
        col = mix(shadow, mid, t * 2.2) if t < .45 else mix(mid, light, (t - .45) * 2.2)
        fl.append((z, '<use href="#%s-fl" transform="translate(%s %s)rotate(%d)scale(%.2f 1)rotate(%d)scale(%.2f)" fill="%s"></use>' % (
            p, n(cx + R * x), n(cy + R * y), math.degrees(math.atan2(y, x)), max(.34, z), r.randint(0, 89), R * .0175 * r.uniform(.9, 1.1), col)))
    fl.sort(key=lambda q: q[0])
    return oval(cx, cy, R * .96, R * .96, mix('#000000', shadow, .6)) + ''.join(q[1] for q in fl)


def hydrangea():
    p, r = 'hy', random.Random(92)
    u = lambda k: 'url(#%s-%s)' % (p, k)
    body = 'M168 464C158 520 164 592 180 620Q250 638 320 620C336 592 342 520 332 464Q250 482 168 464Z'
    d = [
        rad(p + '-wall', [(0, '#4e4d3c'), (.4, '#33332a'), (.78, '#1e1f1a'), (1, '#121310')], .32, .3, .9),
        lin(p + '-table', [(0, '#5a3f2b'), (.3, '#42301f'), (.7, '#25190f'), (1, '#120b07')]),
        lin(p + '-crock', [(0, '#4f473b'), (.1, '#8c8170'), (.28, '#ded4bd'), (.4, '#f0e8d4'), (.58, '#bfb39b'), (.8, '#7a6e5c'), (1, '#3a3329')], 0, 0, 1, 0),
        lin(p + '-rimg', [(0, '#6e6554'), (.3, '#efe7d2'), (.6, '#c5b9a0'), (1, '#4d4538')], 0, 0, 1, 0),
        lin(p + '-lfa', [(0, '#4c7a52'), (.5, '#2f5e3e'), (1, '#1b3f2a')], 0, 0, 1, .4),
        lin(p + '-lfb', [(0, '#183520'), (.6, '#122a1b'), (1, '#0d2015')], 0, 0, 1, .4),
        rad(p + '-vig', [(.58, '#070706', 0), (1, '#070706', .62)], .5, .46, .84),
        wc(p + '-wc', 2.4, '.05', .9, .35, 2.4, (.03, .05, .03), 5),
        wc(p + '-wcn', 1.2, '.08', .7, .25, 1.6, (.05, .05, .12), 12),
        rock(p + '-gl', 15, '.035 .06', 3),
        rock(p + '-pl', 29, '.012 .02', 9),
        blur(p + '-b1', .9), blur(p + '-b2', 2), blur(p + '-b3', 3), blur(p + '-b5', 5), blur(p + '-m', 14), blur(p + '-soft', 1.1),
        paper(p, 41), wash(p, 42, .5), foil(p, 70, 50, 430, 150),
        floret(p),
    ]
    a = [box(0, 0, 500, 700, u('wall'), p + '-pl')]
    # window light falling on the plaster behind the flowers, the crock's shadow beside it
    a.append(fillp(poly([(306, 60), (480, 28), (510, 240), (344, 300)]), '#8a8468', p + '-m', .16))
    a.append(oval(340, 400, 150, 170, '#070706', p + '-m', .5))
    # the table, its back edge, the grain running along it
    a.append(box(0, 548, 500, 152, u('table')))
    grain_l, grain_d = '', ''
    for i in range(60):
        y = r.uniform(552, 700)
        if i % 2:
            grain_l += lens(r.uniform(-60, 420), y, r.uniform(90, 300), r.uniform(.5, 1.3))
        else:
            grain_d += lens(r.uniform(-60, 420), y, r.uniform(90, 300), r.uniform(.5, 1.6))
    a.append(fillp(grain_l, '#7c5a3c', o=.3))
    a.append(fillp(grain_d, '#0c0705', o=.42))
    a.append(box(0, 546, 500, 3, '#7a5e42', o=.7))
    a.append(fillp(lens(164, 628, 330, 26), '#060403', p + '-b5', .75))
    a.append('<g transform="translate(0 1256) scale(1 -1)" opacity=".14">%s</g>' % fillp(body, u('crock'), p + '-b2'))
    # leaves behind the flowers
    back = [(216, 446, 168, 176, 84, 12), (288, 446, 14, 178, 86, -12), (150, 360, -172, 120, 66, 10), (360, 360, -6, 120, 66, -10),
            (140, 270, -150, 110, 60, 10), (372, 250, -30, 104, 56, -10)]
    a.append('<g filter="url(#%s-wc)">%s</g>' % (p, ''.join(leaf(p, i, r, *q) for i, q in enumerate(back))))
    # the heads back to front, each with its shadow on what lies behind it
    a.append('<g filter="url(#%s-wcn)">%s</g>' % (p, mophead(p, r, 92, 386, 60, '#2f3a2a', '#7c8a5a', '#d6d8a8', 90)))
    a.append(oval(346, 330, 100, 100, '#050505', p + '-b5', .4))
    a.append('<g filter="url(#%s-wcn)">%s</g>' % (p, mophead(p, r, 336, 306, 100, '#2e2340', '#7f6a96', '#d8cbe0')))
    a.append(oval(198, 342, 112, 112, '#050505', p + '-b5', .42))
    a.append('<g filter="url(#%s-wcn)">%s</g>' % (p, mophead(p, r, 186, 318, 112, '#1b2350', '#4c62a0', '#b4c4e6')))
    # the crock: plain salt-glazed stoneware, the window on its shoulder
    c = [fillp(body, u('crock'), p + '-gl')]
    c.append(strokep('M166 500C150 500 148 524 164 526', '#3c3429', 7, more='stroke-linecap="round"'))
    c.append(strokep('M334 500C350 500 352 524 336 526', '#2c261e', 7, more='stroke-linecap="round"'))
    c.append(strokep('M166 492Q250 510 334 492', '#3a3024', 1.2, o=.42))
    c.append(strokep('M166 495Q250 513 334 495', '#ffffff', .9, o=.24))
    c.append(strokep('M174 600Q250 618 326 600', '#3a3024', 1.2, o=.32))
    c.append(fillp('M204 486C198 530 200 580 210 606C216 580 214 530 214 490Z', '#ffffff', p + '-b3', .55))
    c.append(fillp('M178 612Q250 636 322 612L320 622Q250 640 180 622Z', '#14100b', p + '-b3', .5))
    c.append(oval(250, 462, 84, 16, u('rimg')))
    c.append(oval(250, 463, 73, 11.5, '#160f0a'))
    c.append(strokep('M176 458Q250 442 324 458', '#fffaf0', 1.1, p + '-b1', .6))
    a.append('<g filter="url(#%s-wc)">%s</g>' % (p, ''.join(c)))
    # two leaves over the rim, then the low head hanging forward, the nearest thing in the picture
    front = [(256, 452, 128, 120, 64, 10), (262, 452, 60, 100, 54, -8)]
    a.append('<g filter="url(#%s-wc)">%s</g>' % (p, ''.join(leaf(p, i + 6, r, *q) for i, q in enumerate(front))))
    a.append(oval(272, 428, 82, 76, '#050505', p + '-b5', .42))
    a.append('<g filter="url(#%s-wcn)">%s</g>' % (p, mophead(p, r, 262, 412, 78, '#20305a', '#5f7cb0', '#cdd9ee', 110)))
    # a few florets fallen on the boards
    for x, y, col in [(112, 640, '#8fa0cc'), (86, 662, '#6f82b4'), (402, 652, '#a79ac0'), (136, 668, '#7f92c2')]:
        a.append('<use href="#%s-fl" transform="translate(%d %d)scale(1.5 .62)rotate(%d)" fill="%s"></use>' % (p, x, y, r.randint(0, 89), col))
    a.append(box(0, 0, 500, 700, u('vig')))
    words = [foil_rule(p), foil_line(p, 'Thank You', 250, 128, 100), LINE]
    return wrap('hydrangea', 'A hydrangea in a plain crock', d, bleed(p, a), words)



# ---- 12. Harvest ---------------------------------------------------------------------

def shock(r, x, base, h, w, stalks):
    """A corn shock: stalks stood up in a cone, tied two thirds of the way up, the tops flaring out.
    Lit on the left, shaded on the right, with dry leaves hanging from the tie."""
    tie = base - h * .62
    sw = max(.8, h / 110)
    shade, body, lit, tops, pale, dull = '', '', '', '', '', ''
    for i in range(stalks):
        t = r.uniform(-1, 1)
        fx, fy = x + t * w / 2 + r.uniform(-3, 3), base + (1 - abs(t)) * h * .035 * r.uniform(.3, 1)
        mx = x + t * w * .085
        stalk = 'M%s %sQ%s %s %s %s' % (n(fx), n(fy), n(x + t * w * .19), n(base - h * .34), n(mx), n(tie))
        tops += 'M%s %sQ%s %s %s %s' % (n(mx), n(tie), n(mx + t * w * .02), n(tie - h * .2), n(x + t * w * .26 + r.uniform(-.05, .05) * h), n(base - h * r.uniform(.84, 1.04)))
        v = t + r.uniform(-.35, .35)
        if v < -.2:
            lit += stalk
        elif v > .4:
            shade += stalk
        else:
            body += stalk
    for i in range(int(stalks * .3)):
        t = r.uniform(-1, 1)
        leaf_ = sliver(x + t * w * .1, tie + r.uniform(-.06, .1) * h, 90 - t * 62 + r.uniform(-14, 14), h * r.uniform(.2, .36), h * .03)
        if t > .1:
            dull += leaf_
        else:
            pale += leaf_
    for i in range(int(stalks * .2)):
        t = r.uniform(-1, 1)
        leaf_ = sliver(x + t * w * .08, tie - r.uniform(0, .1) * h, -90 + t * 70, h * r.uniform(.16, .3), h * .02)
        if t > .1:
            dull += leaf_
        else:
            pale += leaf_
    core = poly([(x - w / 2, base), (x - w * .07, tie), (x + w * .07, tie), (x + w / 2, base), (x, base + h * .03)])
    return ''.join([fillp(core, '#2a1c0e'), strokep(tops, '#b89858', n(sw * 1.2)), strokep(shade, '#3f2c16', n(sw * 2.2)), strokep(body, '#8a6a36', n(sw * 2)),
                    strokep(lit, '#d6b36e', n(sw * 1.7)), fillp(dull, '#6f5228'), fillp(pale, '#e0c585'),
                    strokep('M%s %sQ%s %s %s %s' % (n(x - w * .1), n(tie), n(x), n(tie + h * .02), n(x + w * .1), n(tie)), '#1c1208', n(sw * 2.4))])


def pumpkin(p, i, cx, cy, R, squash=.8, lean=0):
    """Nine lobes round a stem, outer ones first, each with its own round light, then the whole fruit
    shaded away from the sun with its creases drawn in."""
    shapes, clip = '', ''
    for k in (-4, 4, -3, 3, -2, 2, -1, 1, 0):
        th = k / 4.6 * math.pi / 2
        e = '<ellipse cx="%s" cy="0" rx="%s" ry="%s"' % (n(R * math.sin(th)), n(R * (.16 + .3 * math.cos(th))), n(R * squash * (.74 + .26 * math.cos(th))))
        shapes += e + ' fill="url(#%s-pu)"></ellipse>' % p
        clip += e + '></ellipse>'
    h = R * squash
    s = [oval(cx + R * .34, cy + h * .9, R * 1.4, h * .2, '#0c0603', p + '-b5', .72)]
    s.append('<g transform="translate(%s %s) rotate(%s)">' % (n(cx), n(cy), lean))
    s.append('<clipPath id="%s-k%d">%s</clipPath>' % (p, i, clip))
    s.append(shapes)
    s.append('<g clip-path="url(#%s-k%d)">' % (p, i))
    s.append(oval(0, 0, R * 1.24, h * 1.06, 'url(#%s-pus)' % p))
    s.append(oval(-R * .42, -h * .42, R * .46, h * .3, '#ffd590', p + '-b3', .26))
    creases = ''
    for k in range(-3, 4):
        x = R * math.sin((k + .5 * (1 if k >= 0 else -1)) / 4.6 * math.pi / 2)
        creases += 'M0 %sQ%s 0 0 %s' % (n(-h * .92), n(x * 1.9), n(h * .94))
    s.append(strokep(creases, '#4a1f08', n(max(1, R * .03)), p + '-b1', .5))
    s.append('</g>')
    s.append(oval(0, -h * .86, R * .24, h * .11, '#5a2c0e', p + '-b2', .7))
    s.append(fillp('M%s %sC%s %s %s %s %s %sL%s %sC%s %s %s %s %s %sZ' % (
        n(-R * .1), n(-h * .84), n(-R * .08), n(-h * 1.02), n(-R * .14), n(-h * 1.14), n(-R * .22), n(-h * 1.26),
        n(-R * .04), n(-h * 1.34), n(R * .02), n(-h * 1.14), n(R * .12), n(-h * 1.02), n(R * .13), n(-h * .84)), 'url(#%s-pst)' % p))
    s.append('</g>')
    return ''.join(s)


def harvest():
    p, r = 'hv', random.Random(171)
    u = lambda k: 'url(#%s-%s)' % (p, k)
    HZ, VPX, VPY, RX = 430, 640, 430, 190
    d = [
        lin(p + '-sky', [(0, '#251516'), (.2, '#321c1c'), (.42, '#472320'), (.6, '#743c27'), (.76, '#bc7d3d'), (.89, '#e8b565'), (1, '#f9dd9e')], 0, 0, 0, HZ + 2, user=True),
        rad(p + '-glow', [(0, '#ffe7ae', .95), (.34, '#f7c274', .5), (1, '#d98d48', 0)]),
        lin(p + '-cl1', [(0, '#160c0c', .92), (.55, '#2a1614', .76), (1, '#4a2620', 0)]),
        lin(p + '-cl2', [(0, '#6e3a2c', 0), (.45, '#94533a', .66), (.85, '#e09a56', .9), (1, '#f4c67e', .85)]),
        lin(p + '-far', [(0, '#7c5a52'), (1, '#d8a874')]),
        lin(p + '-field', [(0, '#e9bf74'), (.08, '#c4954f'), (.26, '#8a6532'), (.5, '#54391c'), (.76, '#2a1c0f'), (1, '#120b06')], 0, HZ, 0, 700, user=True),
        rad(p + '-pu', [(0, '#eba24a'), (.4, '#cb6f22'), (.78, '#96471a'), (1, '#5d2b10')], .38, .3, .74),
        rad(p + '-pus', [(.38, '#1c0a04', 0), (1, '#1c0a04', .74)], .36, .3, .84),
        lin(p + '-pst', [(0, '#a8965a'), (.5, '#6c6a34'), (1, '#33331a')], 0, 0, 1, 0),
        rad(p + '-vig', [(.56, '#090504', 0), (1, '#090504', .68)], .5, .46, .84),
        wc(p + '-wc', 5, '.03 .05', 2.2, .5, 3, (.08, .03, .01), 7),
        wc(p + '-wcf', 5, '.03 .05', 3, .4, 3, (.2, .12, .08), 13),
        wc(p + '-wcn', 1.8, '.06', 1.1, .35, 2, (.05, .02, .01), 19),
        rock(p + '-wd', 44, '.01 .14', 2),
        cloud(p + '-c1', '.0034 .03', 3.4, 1.55, 8, '1.6 .8'),
        cloud(p + '-c2', '.006 .05', 3.6, 1.5, 15, '1 .6'),
        blur(p + '-b06', .6), blur(p + '-b1', 1), blur(p + '-b2', 2.2), blur(p + '-b3', 3), blur(p + '-b5', 5), blur(p + '-m', 10), blur(p + '-soft', 1.1),
        paper(p, 13), wash(p, 14), foil(p, 40, 50, 460, 220),
    ]
    a = [box(0, 0, 500, HZ + 2, u('sky')), oval(186, HZ - 6, 320, 150, u('glow')),
         box(0, 0, 500, 250, u('cl1'), p + '-c1'), box(0, 280, 500, 130, u('cl2'), p + '-c2')]
    a.append(fillp(land(ridge(r, -12, 512, 404, 12), HZ + 2), u('far'), p + '-wcf', .92))
    a.append(oval(190, 418, 260, 8, '#fde6b4', p + '-m', .6))
    # a far wood in turning leaf, rust and gold and old green, small dabs on a dark body
    a.append(fillp(canopy(r, -12, 512, lambda x: 408 + 6 * math.sin(x * .02), HZ + 3, 12), '#3e2a20', p + '-wcf'))
    woods = ['', '', '', '', '']
    for i in range(250):
        x, y = r.uniform(-10, 510), r.uniform(398, 428)
        woods[r.choice((0, 0, 1, 1, 1, 2, 2, 3, 4))] += dab(r, x, y, r.uniform(4, 8), r.uniform(3, 6))
    a.append('<g filter="url(#%s-wc)">%s</g>' % (p, ''.join(fillp(t, c) for t, c in zip(woods, ['#4e2a1c', '#8c4524', '#b87432', '#d9a648', '#5d6230']))))
    a.append(box(0, HZ, 500, 700 - HZ, u('field')))
    a.append(oval(186, HZ + 3, 300, 7, '#ffe8b8', p + '-m', .5))
    # the cut field: rows of stubble closing on a point at the horizon, then the short stalks themselves
    rows = ''
    for i in range(-12, 13):
        bx = RX + i * 92
        rows += poly([(RX + i * 92 * .03, HZ + 5), (bx + 20, 704), (bx - 20, 704)])
    a.append(fillp(rows, '#3a2612', p + '-b1', .44))
    stub = ['', '', '']
    for i in range(190):
        t = r.random() ** 1.3
        k = 0 if t < .3 else (1 if t < .65 else 2)
        stub[k] += blade(r.uniform(-10, 510), HZ + 8 + 200 * t, 3 + t * 16, r.uniform(-4, 4), .9 + t * 1.7)
    for k, col in enumerate(['#b08a4c', '#7c5c2c', '#4c3618']):
        a.append(fillp(stub[k], col, o=.82))
    # shocks standing away across the field, each smaller with distance, the fence going off to the right
    far = ''.join(shock(r, x, base, h, h * .62, 20 + int(h * .4)) for x, base, h in [(286, 446, 26), (250, 449, 31), (214, 453, 38), (452, 452, 40), (176, 458, 48), (476, 470, 62)])
    a.append('<g filter="url(#%s-wcn)">%s</g>' % (p, far))
    a.append(fillp(lens(112, 500, 150, 11), '#160c06', p + '-b3', .6))
    a.append('<g filter="url(#%s-wcn)">%s</g>' % (p, shock(r, 110, 500, 140, 94, 110)))
    at = lambda q, h: (VPX - 600 * q, VPY + (190 - 142 * h) * q)
    qs = [1 / (1 + k * .33) for k in range(12)]
    rails, shine, posts, edge = '', '', '', ''
    for q0, q1 in zip([1.14] + qs, qs):
        for h in (.34, .62, .9):
            A, B = at(q0, h), at(q1, h)
            ta, tb, sag = 5 * q0, 5 * q1, r.uniform(-1.5, 1.5)
            rails += poly([(A[0], A[1] - ta), (B[0], B[1] - tb + sag), (B[0], B[1] + tb + sag), (A[0], A[1] + ta)])
            shine += poly([(A[0], A[1] - ta), (B[0], B[1] - tb + sag), (B[0], B[1] - tb * .3 + sag), (A[0], A[1] - ta * .3)])
    for q in qs:
        w, T, F = 8 * q, at(q, 1.02), at(q, -.02)
        posts += poly([(T[0] - w, T[1]), (T[0] + w, T[1] - 1), (F[0] + w, F[1]), (F[0] - w, F[1])])
        edge += poly([(T[0] - w, T[1]), (T[0] - w * .3, T[1]), (F[0] - w * .3, F[1]), (F[0] - w, F[1])])
    a.append('<g filter="url(#%s-wd)">%s%s</g>' % (p, fillp(posts, '#4e3e30'), fillp(rails, '#5c4a38')))
    a.append(fillp(shine + edge, '#dcbc8a', o=.55))
    # the big shock, in front of the fence, its shadow lying right
    a.append(fillp(lens(342, 568, 200, 26), '#120904', p + '-b5', .66))
    a.append('<g filter="url(#%s-wcn)">%s</g>' % (p, shock(r, 342, 566, 262, 170, 170)))
    # grass along the fence, then the pumpkins, back to front
    tuft = sward(r, 100, -10, 510, 596, 660, 16, 40, 10, 1.6, 3, 2)
    for k, col in enumerate(['#5a4522', '#33261a']):
        a.append(fillp(tuft[k], col, p + '-b06'))
    a.append('<g filter="url(#%s-wcn)">%s</g>' % (p, ''.join(pumpkin(p, i, *q) for i, q in enumerate(
        [(404, 606, 26, .82, 4), (170, 622, 60, .8, -3), (330, 640, 30, .78, 6), (90, 650, 46, .8, 5), (262, 654, 42, .76, -4)]))))
    # fallen leaves, and the last grass close to us at the corners
    fall = ['', '', '']
    for i in range(30):
        fall[i % 3] += sliver(r.uniform(10, 490), r.uniform(600, 690), r.uniform(0, 360), r.uniform(9, 18), r.uniform(3, 6))
    for k, col in enumerate(['#a8582a', '#c98e3a', '#6e3a20']):
        a.append(fillp(fall[k], col, o=.9))
    low = sward(r, 70, -10, 170, 660, 712, 24, 64, 12, 1.8, 3.4, 2) + sward(r, 55, 400, 510, 650, 712, 24, 70, 12, 1.8, 3.4, 2)
    for k, col in zip((0, 1, 2, 3), ['#2a2012', '#120d08', '#2a2012', '#120d08']):
        a.append(fillp(low[k], col, p + '-b06'))
    a.append(box(0, 0, 500, 700, u('vig')))
    words = [foil_line(p, 'Happy', 250, 112, 94), foil_line(p, 'Thanksgiving', 250, 200, 86), LINE]
    return wrap('harvest', 'Corn shocks and pumpkins at a fence', d, bleed(p, a), words)



# ---- The list of fronts, the writer and the check -------------------------------------

INK = '#ecdcb0'


def spot(x, y, width, spacing=3, **more):
    """Where the personal line goes. Beyond the plain case: anchor, family (garamond) and caps (small caps)."""
    return dict({'x': x, 'y': y, 'size': 50, 'width': width, 'fill': INK, 'spacing': spacing}, **more)


# fn and prefix stay here; cut is the approved line's words, taken out of the four older fronts.
FRONTS = [
    {'key': 'lake', 'fn': lake, 'prefix': 'lk', 'cut': 'for my son', 'name': 'Lake', 'label': 'Lake at dawn, one small boat',
     'occasions': ['birthday'], 'tags': ['fishing', 'lake', 'boat', 'water', 'outdoors'], 'line': spot(250, 306, 420)},
    {'key': 'buck', 'fn': buck, 'prefix': 'bk', 'cut': 'to a fine son', 'name': 'Buck', 'label': 'A buck at the edge of a field at dusk',
     'occasions': ['birthday'], 'tags': ['hunting', 'deer', 'buck', 'woods', 'outdoors'], 'line': spot(250, 664, 420, 2, family='garamond', caps=True)},
    {'key': 'lighthouse', 'fn': lighthouse, 'prefix': 'lh', 'cut': 'for my son', 'name': 'Lighthouse', 'label': 'A lighthouse on a rocky point at evening',
     'occasions': ['birthday'], 'tags': ['sea', 'ocean', 'coast', 'beach', 'lighthouse', 'boats'],
     'line': spot(36, 262, 310, 2, anchor='start', family='garamond', caps=True)},
    {'key': 'magnolia', 'fn': magnolia, 'prefix': 'mg', 'cut': 'to my son', 'name': 'Magnolia', 'label': 'A magnolia branch in the style of a botanical plate',
     'occasions': ['birthday'], 'tags': ['flowers', 'garden', 'magnolia', 'trees', 'south'], 'line': spot(250, 655, 420, 2, family='garamond', caps=True)},
    {'key': 'barn', 'fn': barn, 'prefix': 'bn', 'name': 'Barn', 'label': 'An old red tobacco barn in a field at evening',
     'occasions': ['birthday'], 'tags': ['farm', 'farming', 'tobacco', 'barn', 'country', 'outdoors'], 'line': spot(250, 292, 400)},
    {'key': 'porch', 'fn': porch, 'prefix': 'pc', 'name': 'Porch', 'label': 'A rocking chair on a porch looking out on morning hills',
     'occasions': ['get_well'], 'tags': ['home', 'porch', 'mountains', 'hills', 'country', 'morning'], 'line': spot(250, 664, 400)},
    {'key': 'dogwood', 'fn': dogwood, 'prefix': 'dw', 'name': 'Dogwood', 'label': 'A dogwood branch in bloom',
     'occasions': ['get_well'], 'tags': ['flowers', 'garden', 'dogwood', 'spring', 'trees', 'carolina'], 'line': spot(250, 656, 400)},
    {'key': 'chapel', 'fn': chapel, 'prefix': 'cp', 'name': 'Chapel', 'label': 'A small white country church among trees at evening',
     'occasions': ['sympathy'], 'tags': ['church', 'faith', 'prayer', 'country', 'trees'], 'line': None},
    {'key': 'lily', 'fn': lily, 'prefix': 'ly', 'name': 'Lilies', 'label': 'White lilies on a dark, quiet ground',
     'occasions': ['sympathy'], 'tags': ['flowers', 'lily', 'lilies', 'faith', 'peace'], 'line': None},
    {'key': 'hydrangea', 'fn': hydrangea, 'prefix': 'hy', 'name': 'Hydrangea', 'label': 'A hydrangea in a plain crock',
     'occasions': ['thank_you'], 'tags': ['flowers', 'garden', 'hydrangea', 'home'], 'line': spot(250, 190, 400)},
    {'key': 'snowchurch', 'fn': snowchurch, 'prefix': 'sc', 'name': 'Snowy Church', 'label': 'A country church in the snow on a Christmas evening',
     'occasions': ['christmas'], 'tags': ['church', 'faith', 'christmas', 'snow', 'winter'], 'line': spot(250, 270, 400)},
    {'key': 'harvest', 'fn': harvest, 'prefix': 'hv', 'name': 'Harvest', 'label': 'Corn shocks and pumpkins at a fence',
     'occasions': ['thanksgiving'], 'tags': ['farm', 'harvest', 'pumpkins', 'corn', 'autumn', 'fall'], 'line': spot(250, 262, 400)},
]
PUBLIC = ('key', 'name', 'label', 'occasions', 'tags', 'line')
OCCASIONS = {'birthday', 'get_well', 'sympathy', 'thank_you', 'christmas', 'thanksgiving', 'anytime'}
BANNED = {'image', 'script', 'foreignObject', 'style'}
MAX_ONE, MAX_ALL = 136 * 1024, int(1.15 * 1024 * 1024)      # "about 130 KB", "about 1.1 MB"


def paint(front):
    """One front as written to disk: the fillable line becomes a comment the skill replaces."""
    svg = front['fn']()
    if front.get('cut'):
        svg, hits = re.subn(r'(<text [^>]*>%s</text>){2}' % re.escape(front['cut']), LINE, svg)
        if hits != 1:
            raise SystemExit('%s: the personal line was not found' % front['key'])
    return svg


def write_all():
    os.makedirs(FRONTS_DIR, exist_ok=True)
    total = 0
    for front in FRONTS:
        svg = paint(front)
        with open(os.path.join(FRONTS_DIR, front['key'] + '.svg'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(svg)
        total += len(svg.encode('utf-8'))
        print('%-11s %5d KB' % (front['key'], len(svg) // 1024))
    with open(LIST_FILE, 'w', encoding='utf-8', newline='\n') as f:
        json.dump([{k: front[k] for k in PUBLIC} for front in FRONTS], f, indent=1, ensure_ascii=False)
        f.write('\n')
    print('total       %5d KB' % (total // 1024))


def title_room(el, widths, bad, key):
    """Foil lettering must fit the card, worked out from the real letter widths."""
    size, x = float(el.get('font-size')), float(el.get('x'))
    wide = sum(widths.get(c, .6) for c in el.text) * size
    room = 500 - x - 40 if el.get('text-anchor') == 'start' else 2 * (min(x, 500 - x) - 40)
    if wide > room:
        bad.append('%s: "%s" is %d wide, room for %d' % (key, el.text, wide, room))


def check_front(front, entry, bad):
    key, prefix = front['key'], front['prefix'] + '-'
    path = os.path.join(FRONTS_DIR, key + '.svg')
    if not os.path.exists(path):
        bad.append('%s: no svg' % key)
        return 0
    with open(path, encoding='utf-8', newline='') as f:
        raw = f.read().replace('\r\n', '\n')       # git on Windows may check these out with CRLF
    size = len(raw.encode('utf-8'))
    if size > MAX_ONE:
        bad.append('%s: %d KB is too big' % (key, size // 1024))
    if raw != paint(front):
        bad.append('%s: the file differs from what the tool paints' % key)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        bad.append('%s: does not parse: %s' % (key, e))
        return size
    if not raw.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 700" role="img" aria-label="'):
        bad.append('%s: wrong root attributes' % key)
    if 'c8-art' in raw or '@import' in raw or 'foreignObject' in raw:
        bad.append('%s: holds something banned' % key)
    ids = []
    with open(METRICS, encoding='utf-8') as f:
        widths = json.load(f)['pinyon']['widths']
    for el in root.iter():
        tag = el.tag.rsplit('}', 1)[-1]
        if tag in BANNED:
            bad.append('%s: banned element %s' % (key, tag))
        if el.get('id'):
            ids.append(el.get('id'))
        if tag == 'text':
            family = el.get('font-family', '')
            if not family.startswith(("'Pinyon Script'", "'Cinzel'", "'EB Garamond'")):
                bad.append('%s: lettering in %s' % (key, family[:24]))
            if float(el.get('font-size')) < 50:
                bad.append('%s: lettering under 50 units' % key)
            if 'foil' in el.get('fill', '') and not front.get('cut'):      # the four approved fronts keep their size
                title_room(el, widths, bad, key)
    if len(ids) != len(set(ids)):
        bad.append('%s: repeated ids' % key)
    strays = [i for i in ids if not i.startswith(prefix)]
    if strays:
        bad.append('%s: ids without its prefix, such as %s' % (key, strays[0]))
    have = set(ids)
    used = set(re.findall(r'url\(#([^)]+)\)', raw)) | set(re.findall(r'href="#([^"]+)"', raw))
    if used - have:
        bad.append('%s: nothing answers %s' % (key, sorted(used - have)[:4]))
    if re.search(r'url\((?!#)', raw) or re.search(r'href="(?!#)', raw):
        bad.append('%s: reaches outside the file' % key)
    if raw.count(LINE) != (1 if entry.get('line') else 0):
        bad.append('%s: the <!--LINE--> comment does not match fronts.json' % key)
    return size


def check():
    bad = []
    try:
        with open(LIST_FILE, encoding='utf-8') as f:
            listed = json.load(f)
    except (OSError, ValueError) as e:
        print('fronts.json: %s' % e)
        return 1
    if [q.get('key') for q in listed] != [q['key'] for q in FRONTS] or len(listed) != 12:
        bad.append('fronts.json does not hold the twelve fronts in order')
    total = 0
    for front, entry in zip(FRONTS, listed):
        total += check_front(front, entry, bad)
        if sorted(entry) != sorted(PUBLIC):
            bad.append('%s: wrong keys in fronts.json' % front['key'])
        if not set(entry.get('occasions', ())) <= OCCASIONS or 'anytime' in entry['occasions'] and not {'birthday', 'thank_you'} & set(entry['occasions']):
            bad.append('%s: bad occasions' % front['key'])
        if any(t != t.lower() for t in entry.get('tags', ())) or not entry.get('tags'):
            bad.append('%s: bad tags' % front['key'])
        spot_ = entry.get('line')
        if spot_ and not all(isinstance(spot_.get(k), int) for k in ('x', 'y', 'size', 'width', 'spacing')):
            bad.append('%s: bad line' % front['key'])
    if total > MAX_ALL:
        bad.append('all fronts: %d KB' % (total // 1024))
    extra = sorted(set(os.listdir(FRONTS_DIR)) - {q['key'] + '.svg' for q in FRONTS})
    if extra:
        bad.append('stray files: %s' % extra)
    for line in bad:
        print(line)
    print('%s: %d fronts, %d KB, %d problems' % ('FAILED' if bad else 'ok', len(listed), total // 1024, len(bad)))
    return 1 if bad else 0


if __name__ == '__main__':
    if '--check' in sys.argv[1:]:
        sys.exit(check())
    write_all()
