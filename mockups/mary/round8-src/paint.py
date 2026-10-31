#!/usr/bin/env python3
"""Paints the four card fronts into art/*.svg. Stdlib only and seeded, so a rerun
gives the same art. Run it after changing a scene, then run build.py.

Every front is one <svg viewBox="0 0 500 700"> partial with ids prefixed per card,
so several can sit on one board. Lettering stays at 50 units or more, because a
card shows at scale .4 on the picker board and nothing on screen goes under 20px."""
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
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
    return ('<svg class="c8-art" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 700" role="img" aria-label="%s">\n'
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


BUCK_BODY = [
    # chest, back, rump, belly: a heavy-bodied buck in his prime
    [(60, 130), (66, 112), (84, 99), (104, 98), (128, 106), (150, 110), (172, 105), (192, 106), (208, 120), (212, 140),
     (204, 160), (180, 162), (152, 156), (126, 164), (100, 174), (78, 170), (64, 152)],
    # neck, thick for the rut
    [(62, 84), (74, 78), (86, 88), (100, 98), (122, 112), (106, 160), (76, 162), (62, 134), (58, 110), (56, 94)],
    # head
    [(25, 103), (25, 99), (31, 95), (41, 88), (53, 81), (66, 76), (74, 84), (70, 96), (60, 102), (47, 106), (35, 109), (28, 108)],
    # ears
    [(70, 78), (82, 66), (100, 60), (98, 68), (86, 82), (74, 86)],
    [(62, 76), (68, 62), (77, 55), (77, 63), (71, 76)],
    # tail
    [(202, 118), (217, 128), (220, 142), (212, 148), (204, 138)],
    # near hind leg
    [(172, 134), (208, 132), (209, 160), (205, 174), (211, 188), (204, 199), (200, 216), (202, 226), (189, 226), (189, 208), (187, 192), (177, 178), (158, 164)],
    # far hind leg, stepping
    [(148, 150), (176, 152), (170, 178), (174, 192), (164, 212), (166, 226), (153, 226), (155, 208), (158, 192), (147, 172)],
    # near foreleg
    [(74, 150), (102, 150), (99, 178), (96, 192), (95, 212), (98, 226), (85, 226), (86, 210), (85, 192), (80, 174)],
    # far foreleg
    [(100, 152), (120, 154), (120, 178), (118, 192), (122, 212), (126, 226), (113, 226), (111, 208), (108, 192), (106, 172)],
]


def buck_shape():
    parts = [smooth(b, closed=True) for b in BUCK_BODY]
    parts.append(tapered([(64, 80), (76, 54), (78, 28), (60, 8), (34, 4), (13, 15)], 7.4, 1.6))
    for tine, w in [([(73, 60), (60, 50), (50, 33)], 4.8), ([(78, 36), (76, 14), (66, -12)], 5),
                    ([(62, 10), (56, -8), (46, -26)], 4.4), ([(40, 5), (34, -10), (26, -20)], 3.4)]:
        parts.append(tapered(tine, w, 1))
    far = [tapered([(58, 80), (62, 52), (56, 30), (38, 14), (16, 14), (0, 26)], 6, 1.4)]
    for tine, w in [([(59, 58), (48, 50), (38, 38)], 3.6), ([(58, 34), (54, 14), (46, -2)], 4),
                    ([(42, 18), (36, 2), (28, -12)], 3.4)]:
        far.append(tapered(tine, w, 1))
    return parts, far


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
        lin(p + '-coat', [(0, '#2e2216'), (.5, '#1c150e'), (1, '#110d08')], 240, 300, 480, 400, user=True),
        lin(p + '-foot', [(0, '#0a0e09', 0), (.42, '#0a0e09', .74), (1, '#060906', .97)]),
        rad(p + '-vig', [(.52, '#070a06', 0), (1, '#070a06', .74)], .5, .44, .84),
        wc(p + '-wc', 3, '.03 .05', 1.6, .55, 3, (.02, .04, .02), 6),
        wc(p + '-wcf', 5, '.03 .05', 2.4, .4, 3, (.2, .2, .13), 17),
        wc(p + '-wcn', 1.6, '.06', 1.1, .3, 2, (.01, .01, 0), 24),
        rim(p + '-rim', 1.1, 1.4, (.97, .85, .58), .62),
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
    # the buck
    parts, far = buck_shape()
    bx, by, sc = 190, 241, 1.12
    d.append('<clipPath id="%s-buck">%s</clipPath>' % (p, ''.join('<path d="%s"></path>' % x for x in parts)))
    a.append('<ellipse cx="%d" cy="%d" rx="150" ry="10" fill="#0d110a" opacity=".6" filter="url(#%s-b6)"></ellipse>' % (bx + 130, by + sc * 226, p))
    a.append('<g transform="translate(%d %d) scale(%s)" filter="url(#%s-rim)">'
             '<g fill="#3a2d1c">%s</g><g fill="url(#%s-coat)">%s</g>' % (
                 bx, by, sc, p, ''.join('<path d="%s"></path>' % x for x in far), p, ''.join('<path d="%s"></path>' % x for x in parts)))
    a.append('<g clip-path="url(#%s-buck)">'
             '<ellipse cx="112" cy="128" rx="28" ry="24" fill="#6e5030" opacity=".22" filter="url(#%s-b6)"></ellipse>'
             '<ellipse cx="188" cy="136" rx="22" ry="26" fill="#6e5030" opacity=".2" filter="url(#%s-b6)"></ellipse>'
             '<ellipse cx="84" cy="116" rx="14" ry="30" transform="rotate(-34 84 116)" fill="#5e432a" opacity=".22" filter="url(#%s-b6)"></ellipse>'
             '<path d="M30 110Q42 113 58 106" fill="none" stroke="#b6a586" stroke-width="3" opacity=".26" filter="url(#%s-b1)"></path>'
             '</g></g>' % (p, p, p, p, p))
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


def main():
    out = os.path.join(HERE, 'art')
    os.makedirs(out, exist_ok=True)
    for name, fn in [('lake', lake), ('buck', buck), ('lighthouse', lighthouse), ('magnolia', magnolia)]:
        svg = fn()
        with open(os.path.join(out, name + '.svg'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(svg)
        print('%-11s %5d KB' % (name, len(svg) // 1024))


if __name__ == '__main__':
    main()
