"""Cards and messages (M15b): draws each card, letter and keepsake as one self-contained SVG and saves them.
Everything is in this one file because a skill can't load a second one. Mary's tools are at the bottom.

Every draw_ function that fits text takes ctx, because the letter widths and the fonts come through it. Sizes are in
SVG units: a card page is 500x700 units and shows at 370x518 on screen, so 27 units is the 20px floor."""
import base64
import datetime
import functools
import html
import json
import math
import random
import re
import threading
import unicodedata

SVG_NS = "http://www.w3.org/2000/svg"
K = 500 / 370  # the board's 370x518 page, stored here at 500x700
SAFETY = 1.04  # every fit keeps this spare: kerning is ignored and script fonts swash past their advance

SCRIPT = "'Pinyon Script','Edwardian Script ITC','Palace Script MT','Monotype Corsiva','Segoe Script',cursive"
CAPS = "'Cinzel','Trajan Pro','Times New Roman',serif"
GARAMOND = "'EB Garamond',Garamond,'Times New Roman',serif"
CEDARVILLE = "'Cedarville Cursive','Segoe Script',cursive"
KALAM = "'Kalam','Segoe Print',cursive"
SEGOE = "'Segoe UI',Arial,sans-serif"
ESTIMATED = {"segoe": ("garamond-500", 1.08), "segoe-600": ("garamond-700", 1.08)}  # a system face has no metrics here

LATIN = ("U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, "
         "U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD")
LATIN_EXT = ("U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, "
             "U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF")
FACES = {  # first font-family name: (file stem, weights, style, has an -ext file)
    "Pinyon Script": ("pinyon", "400", "normal", True),
    "Cinzel": ("cinzel", "400 900", "normal", True),
    "EB Garamond": ("garamond", "400 800", "normal", True),
    "EB Garamond italic": ("garamond-italic", "400", "italic", True),
    "Cedarville Cursive": ("cedarville", "400", "normal", False),
    "Kalam": ("kalam", "400", "normal", True),
}

FRONT_FLOOR = 30
FRONT_LEAD = 1.2
FRONT_TOP, FRONT_BOTTOM = 40, 670

WORDS_FLOOR = 27  # 20 board px
VERSE_FLOOR = 27
VERSE_SIZE, VERSE_LEAD, VERSE_W = 26 * K, 35 / 26, 322 * K
HAND_X, HAND_W, SIGN_INDENT = 30 * K, 322 * K, 150 * K
RULE_ABOVE, RULE_H, RULE_BELOW = 18 * K, 2 * K, 16 * K
SIGN_GAP, SIGN_LEAD = 6 * K, 48 / 34
PAGE_TOP, PAGE_BOTTOM = 36, 660
PAGE_LIFT = .4  # of the page's spare height goes above the block, as on the board
SNUG_LEAD = 1.3  # the hand's lines set closer, the last try before "doesn't fit"
HANDS = {
    "cursive": {"font": "cedarville", "family": CEDARVILLE, "size": 30 * K, "lead": 43 / 30, "sign": 34 / 30},
    "plain": {"font": "kalam", "family": KALAM, "size": 28 * K, "lead": 40 / 28, "sign": 34 / 28},
}

LETTER_W, LETTER_PAD, LETTER_MIN_H = 544, 48, 440
LETTER_TOP, LETTER_FLOOR, LETTER_LEAD, LETTER_GAP = 32, 24, 1.3, 12

NAME_CENTER, NAME_W, NAME_ROOM, NAME_LEAD = 158, 274, 176, 1.05
MEMORY_X, MEMORY_W, MEMORY_TOP, MEMORY_ROOM = 304, 378, 424, 154

GILT = [(0, "#6e4e10"), (.18, "#b08a34"), (.34, "#f2dd98"), (.5, "#94701f"), (.68, "#e4c878"), (.84, "#9e7a26"), (1, "#6a4a0e")]
BRASS = [(0, "#55451a"), (.2, "#967a38"), (.36, "#dcc88a"), (.52, "#7e662a"), (.7, "#ccb577"), (.86, "#8a7032"), (1, "#4f4018")]
SPRIG = ('<path d="M0 0C-8 -7 -20 -8 -33 0C-20 8 -8 7 0 0Z"/><path d="M0 0C8 -7 20 -8 33 0C20 8 8 7 0 0Z"/>'
         '<path d="M0 -8C-4 -3 -4 3 0 8C4 3 4 -3 0 -8Z"/><path d="M-33 0H-92M33 0H92" stroke-width="1.2" stroke="url(#%s)"/>')
KEEPSAKE = {
    "mary": {"deep": "#5e1a2e", "ink": "#2c1c18", "paper": ("#fbf4e4", "#efe2c6", 3), "foil": GILT,
             "mat": ("#6d1f35", "#3c0c1a"),
             "bright": [(0, "#a67c22"), (.25, "#f7e6a8"), (.45, "#c49a3c"), (.7, "#fbedb8"), (1, "#a67c22")],
             "name": [(0, "#5e4009"), (.2, "#a67a24"), (.38, "#e0c070"), (.54, "#7e5a14"), (.72, "#c9a44e"), (1, "#5e4009")]},
    "sam": {"deep": "#1f3d2b", "ink": "#1e2a1f", "paper": ("#f6f1e0", "#e6dcbf", 5), "foil": BRASS,
            "mat": ("#2c5a3e", "#14301f"),
            "bright": [(0, "#8a7030"), (.25, "#efe0a6"), (.45, "#a88c44"), (.7, "#f4e8ba"), (1, "#8a7030")],
            "name": [(0, "#4a3b12"), (.2, "#8e7230"), (.38, "#cdb574"), (.54, "#685322"), (.72, "#b49a58"), (1, "#463810")]},
}

# Printed verses. "assumes" names what a verse takes for granted, so a card only gets one that's true of the person:
# man or woman (who it's for), water (they like the water), faith (they'd welcome a prayer).
VERSES = {
    "birthday": [
        {"lines": ["Wishing you a quiet joy,", "good company and calm water,", "and years ahead as fine",
                   "as the man you've become."], "assumes": ["man", "water"]},
        {"lines": ["May this day bring you peace,", "old friends and good news,", "and a year as well spent",
                   "as the ones gone before."], "assumes": []},
        {"lines": ["To a woman who has given", "more than she ever asked,", "may this day and all to follow",
                   "give some of it back."], "assumes": ["woman"]},
    ],
    "get_well": [
        {"lines": ["Thinking of you today,", "and hoping each new morning", "brings back a little strength",
                   "and a little more ease."], "assumes": []},
        {"lines": ["May rest come easy to you,", "and strength return in time.", "You are in my thoughts today",
                   "and in my prayers tonight."], "assumes": ["faith"]},
        {"lines": ["Take your time and mend well.", "Many are pulling for you,", "and the days ahead will wait",
                   "until you are ready."], "assumes": []},
    ],
    "sympathy": [
        {"lines": ["May God hold you close", "in this hard and quiet time,", "and may the love you shared",
                   "be your comfort and peace."], "assumes": ["faith"]},
        {"lines": ["There are no right words", "for a loss like this one.", "Please know you are held",
                   "in my heart and my thoughts."], "assumes": []},
        {"lines": ["The Lord is close", "to the brokenhearted.", "May He give you rest",
                   "and peace in the days to come."], "assumes": ["faith"]},
    ],
    "thank_you": [
        {"lines": ["Your kindness was noticed,", "and it meant a great deal.", "Please accept my thanks,",
                   "from a grateful heart."], "assumes": []},
        {"lines": ["A simple word of thanks", "for all that you have done.", "Good deeds are not forgotten",
                   "by the ones they were done for."], "assumes": []},
        {"lines": ["Some debts can't be repaid,", "only gratefully remembered.", "Yours is one of those.",
                   "Thank you, from the heart."], "assumes": []},
    ],
    "christmas": [
        {"lines": ["May the peace of this night", "rest upon you and your home,", "and the love of our Savior",
                   "stay with you all the year."], "assumes": ["faith"]},
        {"lines": ["A quiet Christmas to you,", "a warm house, good company,", "and every good thing",
                   "in the year to come."], "assumes": []},
        {"lines": ["Glory to God in the highest,", "and on earth peace, good will.", "May that old promise find you",
                   "well this Christmas and always."], "assumes": ["faith"]},
    ],
    "thanksgiving": [
        {"lines": ["For the harvest and the table,", "for the faces gathered near,", "for all that we've been given,",
                   "we give thanks again this year."], "assumes": []},
        {"lines": ["Counting my blessings today,", "and you are among the first.", "May your table be full",
                   "and your heart at peace."], "assumes": []},
        {"lines": ["Give thanks to the Lord,", "for He is good.", "May His mercy and His peace",
                   "be with you and yours today."], "assumes": ["faith"]},
    ],
}

ID_RE = re.compile(r"[a-z0-9_-]{1,40}")
BROKEN_LINE_RE = re.compile(r"\r\n?|[\x0b\x0c\x85  ]")
CONTROL_RE = re.compile("[\x00-\x09\x0b-\x1f\x7f-\x9f\ud800-\udfff￾￿]")
OPEN_RE = re.compile(r"\s*<svg\b[^>]*>")
STYLE_RE = re.compile(r"<style>(.*?)</style>", re.S)
FACE_RE = re.compile(r"@font-face\{[^}]*\}")
TEXT_RE = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)
FAMILY_RE = re.compile(r'font-family="([^"]*)"')
VIEW_RE = re.compile(r'viewBox="([^"]+)"')
TAG_RE = re.compile(r"<[^>]+>")
REF_RE = re.compile(r'\bid="|url\(#|href="#')  # each is followed by the name of something in the same picture
SOFT_RE = re.compile(r'<filter id="([^"]+-soft)"')

_metric_cache = {}
_front_cache = {}


# Fitting

def clean(text):
    """The person's text, safe to draw: control characters go, line breaks stay, every letter stays."""
    text = unicodedata.normalize("NFC", str(text or ""))
    text = BROKEN_LINE_RE.sub("\n", text).replace("\t", " ")
    return "\n".join(line.strip() for line in CONTROL_RE.sub("", text).split("\n")).strip()


def _metrics(ctx):
    if not _metric_cache:
        _metric_cache.update(json.loads(ctx.asset("metrics.json")))
    return _metric_cache


def width(ctx, font, text, size, spacing=0):
    """Estimated width of text in units. font is a name in metrics.json, "segoe" or "segoe-600"; "-caps" on the end
    measures small capitals, each lowercase letter drawn as a capital about .8 as wide."""
    if font.endswith("-caps"):
        small = "".join(c.upper() for c in text if c.islower())
        return width(ctx, font[:-5], text.upper(), size, spacing) - .2 * width(ctx, font[:-5], small, size)
    font, scale = ESTIMATED.get(font, (font, 1))
    face = _metrics(ctx)[font]
    missing = face["average"] * 1.2
    return sum(face["widths"].get(c, missing) for c in text) * size * scale + spacing * len(text)


def _fits(ctx, font, text, size, box, track=0):
    """track is letter spacing in em, so it shrinks along with the text."""
    return width(ctx, font, text, size, track * size) * SAFETY <= box


def _break_word(ctx, font, word, size, box, track):
    """A word too wide for any line, in hyphenated pieces. Every letter is kept."""
    pieces, piece = [], ""
    for letter in word:
        if piece and not _fits(ctx, font, piece + letter + "-", size, box, track):
            pieces.append(piece + "-")
            piece = ""
        piece += letter
    return pieces + [piece]


def _wrap(ctx, font, text, size, box, track=0, hyphen=False):
    """Greedy on spaces, keeping the person's own line breaks. None when a word is wider than the box and hyphen is off."""
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            trial = line + " " + word if line else word
            if _fits(ctx, font, trial, size, box, track):
                line = trial
                continue
            if line:
                lines.append(line)
                line = ""
            if _fits(ctx, font, word, size, box, track):
                line = word
            elif not hyphen:
                return None
            else:
                *whole, line = _break_word(ctx, font, word, size, box, track)
                lines += whole
        lines.append(line)
    return lines


def _sizes(top, floor):
    """top, one less each step, ending exactly on floor."""
    sizes = [top]
    while sizes[-1] > floor:
        sizes.append(max(floor, sizes[-1] - 1))
    return sizes


def _fit(ctx, font, text, top, floor, box, room=math.inf, lead=1.3, track=0, most=0):
    """The largest size at which text wraps inside box and room, as (lines, size), or (None, floor).
    Words are broken only at the floor. most limits the number of lines."""
    for size in _sizes(top, floor):
        lines = _wrap(ctx, font, text, size, box, track, hyphen=size <= floor)
        if lines and len(lines) * size * lead <= room and (not most or len(lines) <= most):
            return lines, size
    return None, floor


def _fit_all(ctx, font, text, top, floor, box, room, lead, track=0):
    """_fit for a picture that has no way to say it didn't fit: past the floor it keeps shrinking, so no letter is lost."""
    lines, size = _fit(ctx, font, text, top, floor, box, room, lead, track)
    while lines is None:
        size *= .92
        lines = _wrap(ctx, font, text, size, box, track, hyphen=True)
        lines = lines if len(lines) * size * lead <= room else None
    return lines, size


def _baseline(ctx, font, size, line_height):
    """From the top of a line box down to where the letters sit, as a browser sets it."""
    face = _metrics(ctx)[font]
    return (line_height - (face["ascent"] + face["descent"]) * size) / 2 + face["ascent"] * size


# Pieces of SVG

def _n(value):
    return ("%.2f" % value).rstrip("0").rstrip(".")


def _esc(text):
    return html.escape(str(text), quote=True)


def _text(x, y, size, family, fill, body, more=""):
    return ('<text x="%s" y="%s" font-family="%s" font-size="%s" fill="%s"%s>%s</text>'
            % (_n(x), _n(y), family, _n(size), fill, more, _esc(body)))


def _root(w, h, label, body):
    return ('<svg xmlns="%s" viewBox="0 0 %s %s" role="img" aria-label="%s">%s</svg>'
            % (SVG_NS, _n(w), _n(h), _esc(label), body))


def _gradient(id_, stops, x1=0, y1=0, x2=1, y2=1, user=False):
    units = ' gradientUnits="userSpaceOnUse"' if user else ""
    body = "".join('<stop offset="%s" stop-color="%s"/>' % stop for stop in stops)
    return '<linearGradient id="%s" x1="%s" y1="%s" x2="%s" y2="%s"%s>%s</linearGradient>' % (id_, x1, y1, x2, y2, units, body)


def _sheet(id_, w, h, light, deep, seed, tooth=.3, out_w=None, out_h=None):
    """Heavy cream stock, with its grain worked at the board's own scale whatever size it's shown."""
    return ('<svg width="%s" height="%s" viewBox="0 0 %d %d" preserveAspectRatio="none" aria-hidden="true"><defs>'
            '<radialGradient id="%s-g" cx=".42" cy=".36" r=".9"><stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></radialGradient>'
            '<filter id="%s-f" filterUnits="userSpaceOnUse" x="0" y="0" width="%d" height="%d" color-interpolation-filters="sRGB">'
            '<feTurbulence type="fractalNoise" baseFrequency="1.05" numOctaves="3" seed="%d" result="t"/>'
            '<feDiffuseLighting in="t" surfaceScale="%s" diffuseConstant="1.155" lighting-color="#ffffff" result="l"><feDistantLight azimuth="225" elevation="60"/></feDiffuseLighting>'
            '<feBlend in="SourceGraphic" in2="l" mode="multiply"/></filter></defs>'
            '<rect width="%d" height="%d" fill="url(#%s-g)" filter="url(#%s-f)"/></svg>'
            % (out_w or w, out_h or h, w, h, id_, light, deep, id_, w, h, seed, tooth, w, h, id_, id_))


def _shade(id_, x1, x2, stops):
    """The page darkening toward the fold, as the board's CSS gradient."""
    body = "".join('<stop offset="%s" stop-color="%s" stop-opacity="%s"/>' % stop for stop in stops)
    return ('<defs><linearGradient id="%s" x1="%s" y1="0" x2="%s" y2="0">%s</linearGradient></defs>'
            '<rect width="500" height="700" fill="url(#%s)"/>' % (id_, x1, x2, body, id_))


def _sprig(id_, x, y, scale):
    return ('<g transform="translate(%s %s) scale(%s)" opacity=".85"><defs>%s</defs><g fill="url(#%s)">'
            '<path d="M0 0C-7 -6 -17 -7 -28 0C-17 7 -7 6 0 0Z"/><path d="M0 0C7 -6 17 -7 28 0C17 7 7 6 0 0Z"/></g></g>'
            % (_n(x), _n(y), _n(scale), _gradient(id_, GILT, 0, 0, 1, 0), id_))


# Fonts, embedded so a picture needs nothing from outside itself

def _face_rule(ctx, family, stem, weight, style, ranges):
    try:
        data = base64.b64encode(ctx.font(stem + ".woff2")).decode("ascii")
    except Exception:  # a missing font falls back to the next family in the picture's list, and the card still draws
        return ""
    return ("@font-face{font-family:'%s';font-style:%s;font-weight:%s;src:url(data:font/woff2;base64,%s) format('woff2');unicode-range:%s}"
            % (family, style, weight, data, ranges))


def _wanted_faces(svg):
    """{face: needs its -ext file} for every embeddable family this picture draws text in."""
    wanted = {}
    for attrs, body in TEXT_RE.findall(svg):
        found = FAMILY_RE.search(attrs)
        if not found:
            continue
        face = found.group(1).split(",")[0].strip(" '\"")
        face = face + " italic" if 'font-style="italic"' in attrs else face
        if face in FACES:
            wanted[face] = wanted.get(face, False) or any(ord(c) > 0xFF for c in html.unescape(body))
    return wanted


def _font_rules(ctx, svg):
    rules = []
    for face, extended in _wanted_faces(svg).items():
        stem, weight, style, has_ext = FACES[face]
        family = face.replace(" italic", "")
        if extended and has_ext:
            rules.append(_face_rule(ctx, family, stem + "-ext", weight, style, LATIN_EXT))
        rules.append(_face_rule(ctx, family, stem, weight, style, LATIN))
    return rules


def _with_fonts(ctx, svg):
    rules = _font_rules(ctx, svg)
    if not rules:
        return svg
    head = OPEN_RE.match(svg).end()
    return svg[:head] + "<style>" + "".join(rules) + "</style>" + svg[head:]


def _nest(svg, prefix, x, y, w, h):
    """svg's drawing, placed in a box and fitted without stretching. Its ids get prefix, so two pictures can't clash;
    its fonts stay behind for _joined."""
    opening = OPEN_RE.match(svg).group(0)
    body = STYLE_RE.sub("", svg[len(opening):svg.rfind("</svg>")], count=1)
    body = TAG_RE.sub(lambda tag: REF_RE.sub(lambda ref: ref.group(0) + prefix, tag.group(0)), body)
    return ('<svg x="%s" y="%s" width="%s" height="%s" viewBox="%s">%s</svg>'
            % (_n(x), _n(y), _n(w), _n(h), VIEW_RE.search(opening).group(1), body))


def _joined(w, h, label, body, sources):
    """One picture made of others, carrying each font once."""
    rules = {}
    for svg in sources:
        for style in STYLE_RE.findall(svg)[:1]:
            rules.update(dict.fromkeys(FACE_RE.findall(style)))
    return _root(w, h, label, ("<style>%s</style>" % "".join(rules) if rules else "") + body)


# The card

def fronts(ctx):
    """Every front in fronts.json, as {key: entry}."""
    if not _front_cache:
        _front_cache.update((entry["key"], entry) for entry in json.loads(ctx.asset("fronts.json")))
    return _front_cache


def _front_font(spec):
    font = "garamond-400" if spec.get("family") == "garamond" else "cinzel-500"
    return font + "-caps" if spec.get("caps") else font


def _fit_front_line(ctx, spec, text):
    """One line shrinking to about 30, then as many lines at 30 as it takes."""
    font, top, box = _front_font(spec), spec["size"], spec["width"]
    track = spec.get("spacing", 0) / top
    lines, size = _fit(ctx, font, text, top, FRONT_FLOOR, box, lead=FRONT_LEAD, track=track, most=1)
    if lines:
        return lines, size
    room = spec["y"] - FRONT_TOP if spec["y"] > 350 else FRONT_BOTTOM - spec["y"]
    return _fit_all(ctx, font, text, FRONT_FLOOR, FRONT_FLOOR, box, room, FRONT_LEAD, track)


def _engraved(soft, spec, line, y, size):
    """A soft shadow and the line over it, as paint_card_fronts.engraved() draws the fronts' own words."""
    family = GARAMOND if spec.get("family") == "garamond" else CAPS
    more = ' text-anchor="%s"' % spec.get("anchor", "middle")
    if spec.get("spacing"):
        more += ' letter-spacing="%s"' % _n(spec["spacing"] * size / spec["size"])
    if spec.get("caps"):
        more += ' font-variant="small-caps"'
    shadow = more + ' fill-opacity=".6" transform="translate(1 1.6)" filter="url(#%s)"' % soft
    return (_text(spec["x"], y, size, family, "#000000", line, shadow) +
            _text(spec["x"], y, size, family, spec["fill"], line, more))


def _front_line(ctx, art, spec, text):
    lines, size = _fit_front_line(ctx, spec, text)
    step = size * FRONT_LEAD
    first = spec["y"] - (len(lines) - 1) * step if spec["y"] > 350 else spec["y"]  # low on the card it grows upward
    soft = SOFT_RE.search(art).group(1)
    return "".join(_engraved(soft, spec, line, first + i * step, size) for i, line in enumerate(lines) if line)


def draw_front(ctx, key, line=""):
    """The front picture with the personal line drawn in. A front with no line in fronts.json ignores it."""
    entry = fronts(ctx)[key]
    art = ctx.asset("fronts/%s.svg" % entry["key"]).decode("utf-8")
    text, spec = clean(line), entry["line"]
    drawn = _front_line(ctx, art, spec, text) if spec and text else ""
    return _with_fonts(ctx, art.replace("<!--LINE-->", drawn))


def _verse_top(ctx, verse):
    """The largest size at which every verse line crosses the page, or None."""
    for size in _sizes(VERSE_SIZE, VERSE_FLOOR):
        if all(_fits(ctx, "garamond-400", line, size, VERSE_W) for line in verse):
            return size
    return None


def _fit_signature(ctx, hand, text, size):
    """Larger than the words as on the board, in two lines at most until the floor forces more."""
    lines, sign = _fit(ctx, hand["font"], text, size * hand["sign"], WORDS_FLOOR, HAND_W, most=2)
    return (lines, sign) if lines else _fit(ctx, hand["font"], text, WORDS_FLOOR, WORDS_FLOOR, HAND_W)


def _plan_inside(ctx, verse, verse_size, words, signature, hand, size, lead):
    """One layout try: the lines and sizes and the block's height, or None when it won't go."""
    lines = _wrap(ctx, hand["font"], words, size, HAND_W, hyphen=size <= WORDS_FLOOR) if words else []
    if lines is None:
        return None
    sign, sign_size = _fit_signature(ctx, hand, signature, size) if signature else ([], size)
    hand_h = len(lines) * size * lead + (SIGN_GAP if lines and sign else 0) + len(sign) * sign_size * SIGN_LEAD
    verse_h = len(verse) * verse_size * VERSE_LEAD + (RULE_ABOVE + RULE_H + RULE_BELOW if verse else 0)
    if verse_h + hand_h > PAGE_BOTTOM - PAGE_TOP:
        return None
    return {"verse": verse, "verse_size": verse_size, "lines": lines, "size": size, "lead": lead,
            "sign": sign, "sign_size": sign_size, "height": verse_h + hand_h, "hand_h": hand_h}


def _fit_inside(ctx, verse, words, signature, hand):
    """Tries in order: the words shrink, then the verse shrinks, then the verse is left out, then the hand's lines
    close up. None if nothing fits."""
    top = _verse_top(ctx, verse) if verse else None
    lead = hand["lead"]
    tries = []
    if top:
        tries += [(verse, top, size, lead) for size in _sizes(hand["size"], WORDS_FLOOR)]
        tries += [(verse, size, WORDS_FLOOR, lead) for size in _sizes(top, VERSE_FLOOR)[1:]]
    tries += [([], 0, size, lead) for size in _sizes(hand["size"], WORDS_FLOOR)]
    tries.append(([], 0, WORDS_FLOOR, SNUG_LEAD))
    for kept, verse_size, size, line_lead in tries:
        plan = _plan_inside(ctx, kept, verse_size, words, signature, hand, size, line_lead)
        if plan:
            return plan
    return None


def _verse_block(ctx, plan, y):
    """The verse and the gold rule from y down."""
    size, step = plan["verse_size"], plan["verse_size"] * VERSE_LEAD
    drop = _baseline(ctx, "garamond-400", size, step)
    parts = [_text(250, y + i * step + drop, size, GARAMOND, "#2b2320", line, ' text-anchor="middle"')
             for i, line in enumerate(plan["verse"])]
    y += len(plan["verse"]) * step + RULE_ABOVE
    parts.append('<rect x="%s" y="%s" width="%s" height="%s" fill="url(#ci-rule)"/>' % (_n(125 * K), _n(y), _n(120 * K), _n(RULE_H)))
    return "".join(parts), y + RULE_H + RULE_BELOW


def _hand_block(ctx, plan, hand, y):
    """Their words and the signature from y down, on the board's slight tilt."""
    font, family, ink = hand["font"], hand["family"], "#1c2a4a"
    size, step = plan["size"], plan["size"] * plan["lead"]
    drop = _baseline(ctx, font, size, step)
    parts = [_text(HAND_X, y + i * step + drop, size, family, ink, line) for i, line in enumerate(plan["lines"]) if line]
    top = y + len(plan["lines"]) * step + (SIGN_GAP if plan["lines"] else 0)
    sign, step = plan["sign_size"], plan["sign_size"] * SIGN_LEAD
    widest = max([width(ctx, font, line, sign) * SAFETY for line in plan["sign"]] or [0])
    x = min(HAND_X + SIGN_INDENT, HAND_X + HAND_W - widest)
    drop = _baseline(ctx, font, sign, step)
    parts += [_text(x, top + i * step + drop, sign, family, ink, line) for i, line in enumerate(plan["sign"]) if line]
    return '<g transform="rotate(-.6 %s %s)">%s</g>' % (_n(HAND_X), _n(y + plan["hand_h"] / 2), "".join(parts))


INSIDE_DEFS = ('<defs><linearGradient id="ci-rule"><stop offset="0" stop-color="#a67c22" stop-opacity="0"/>'
               '<stop offset=".2" stop-color="#b08a34"/><stop offset=".5" stop-color="#ecd690"/><stop offset=".8" stop-color="#b08a34"/>'
               '<stop offset="1" stop-color="#a67c22" stop-opacity="0"/></linearGradient>'
               '<linearGradient id="ci-fold"><stop offset="0" stop-color="#382414" stop-opacity=".42"/>'
               '<stop offset="1" stop-color="#fffaeb" stop-opacity=".5"/></linearGradient></defs>')


def _inside_svg(ctx, plan, hand):
    y = max(PAGE_TOP, (700 - plan["height"]) * PAGE_LIFT)
    verse = ""
    if plan["verse"]:
        verse, y = _verse_block(ctx, plan, y)
    body = (INSIDE_DEFS + _sheet("ci", 370, 518, "#faf3e4", "#f0e4cc", 9, .28, 500, 700) +
            _shade("ci-sh", 1, 0, [(.74, "#5a4228", 0), (.91, "#5a4228", .06), (1, "#382414", .22)]) +
            '<rect width="%s" height="700" fill="url(#ci-fold)"/>' % _n(2 * K) + verse + _hand_block(ctx, plan, hand, y))
    return _with_fonts(ctx, _root(500, 700, "Inside of the card", body))


def draw_inside(ctx, verse_lines, words, signature, hand="cursive"):
    """The right-hand page: printed verse, gold rule, then their words and signature in hand ("cursive" or "plain").
    Returns {"svg", "fits", "verse_left_out", "size"}; size is the words' size in units, never under 27 (20 board px).
    When the words can't fit even with the verse out, fits is False and svg is "": they are never drawn cut."""
    verse = [" ".join(clean(line).split()) for line in verse_lines or []]
    verse = [line for line in verse if line]
    style = HANDS.get(hand, HANDS["cursive"])
    plan = _fit_inside(ctx, verse, clean(words), clean(signature), style)
    if plan is None:
        return {"svg": "", "fits": False, "verse_left_out": bool(verse), "size": WORDS_FLOOR}
    return {"svg": _inside_svg(ctx, plan, style), "fits": True,
            "verse_left_out": bool(verse) and not plan["verse"], "size": round(plan["size"], 2)}


def draw_left():
    """The blank left page with its gilt sprig, for the card opening."""
    body = (_sheet("cl", 370, 518, "#f6eedc", "#ecdfc6", 7, .28, 500, 700) + _sprig("cl-sf", 185 * K, 451 * K, K) +
            _shade("cl-sh", 0, 1, [(.6, "#5a4228", 0), (.84, "#5a4228", .07), (1, "#382414", .24)]))
    return _root(500, 700, "Left page of the card", body)


def draw_both(front_svg, inside_svg):
    """Front and inside side by side in one 1000x700 picture."""
    body = _nest(front_svg, "f-", 0, 0, 500, 700) + _nest(inside_svg, "i-", 500, 0, 500, 700)
    return _joined(1000, 700, "The card, front and inside", body, [front_svg, inside_svg])


def draw_print_sheet(front_svg, inside_svg):
    """A quarter-fold card on one letter sheet. Fold the top half back behind, printed side out, then fold left to
    right so the bottom panels meet: the front ends up outside with the inside words opposite."""
    folds = ('<path d="M12 396H600M306 12V780" fill="none" stroke="#b5b5b5" stroke-width=".5" stroke-dasharray="4 4"/>')
    note = _text(153, 766, 9, "Georgia,'Times New Roman',serif", "#9a9a9a", "Fold along the lines", ' text-anchor="middle"')
    body = ('<rect width="612" height="792" fill="#ffffff"/>'
            '<g transform="rotate(180 153 198)">%s</g><g transform="rotate(180 459 198)">%s</g>%s%s%s%s'
            % (_nest(front_svg, "f-", 18, 18, 270, 360), _sprig("ps-back", 459, 331, .5), _sprig("ps-left", 153, 727, .7),
               _nest(inside_svg, "i-", 324, 414, 270, 360), folds, note))
    return _joined(612, 792, "The card laid out to print and fold", body, [front_svg, inside_svg])


# The plain letter

def _letter_blocks(ctx, paragraphs, signature, size):
    """[(lines, weight)] at one size, or None while a word is still wider than the page."""
    hyphen = size <= LETTER_FLOOR
    blocks = [(_wrap(ctx, "segoe", p, size, LETTER_W, hyphen=hyphen), "400") for p in paragraphs]
    if signature:
        blocks.append((_wrap(ctx, "segoe-600", signature, size, LETTER_W, hyphen=hyphen), "600"))
    return None if any(lines is None for lines, _ in blocks) else blocks


def _letter_height(blocks, size):
    return sum(len(lines) * size * LETTER_LEAD for lines, _ in blocks) + LETTER_GAP * max(0, len(blocks) - 1)


def _fit_letter(ctx, paragraphs, signature):
    """The largest size that keeps the paper at its usual height; at the floor the paper grows instead."""
    for size in _sizes(LETTER_TOP, LETTER_FLOOR):
        blocks = _letter_blocks(ctx, paragraphs, signature, size)
        if blocks is None:
            continue
        height = _letter_height(blocks, size)
        if size <= LETTER_FLOOR or height + 2 * LETTER_PAD <= LETTER_MIN_H:
            return blocks, size, height


def draw_letter(ctx, words, signature):
    """Cream paper 640 wide with their words in a plain face. The paper grows from 440 so it always fits."""
    paragraphs = [p for p in clean(words).split("\n") if p]
    blocks, size, height = _fit_letter(ctx, paragraphs, clean(signature))
    paper = max(LETTER_MIN_H, math.ceil(height + 2 * LETTER_PAD))
    y, step, parts = (paper - height) / 2, size * LETTER_LEAD, []
    for lines, weight in blocks:
        for line in lines:
            more = ' font-weight="600"' if weight == "600" else ""
            parts.append(_text(LETTER_PAD, y + size * 1.06, size, SEGOE, "#1f1b16", line, more))
            y += step
        y += LETTER_GAP
    return _root(640, paper, "A letter", _sheet("lt", 640, paper, "#fbf6ea", "#f3e9d6", 13, .22) + "".join(parts))


# The keepsake page (board A)

def _keep_rules(who, w=724, h=616):
    foil, stops = "kp-foil", KEEPSAKE[who]["foil"]
    x0, y0, x1, y1 = 23, 23, w - 23, h - 23
    if who == "mary":
        q = 16  # scooped corners
        inner = ("M%d %dH%dA%d %d 0 0 0 %d %dV%dA%d %d 0 0 0 %d %dH%dA%d %d 0 0 0 %d %dV%dA%d %d 0 0 0 %d %dZ"
                 % (x0 + q, y0, x1 - q, q, q, x1, y0 + q, y1 - q, q, q, x1 - q, y1, x0 + q, q, q, x0, y1 - q, y0 + q, q, q, x0 + q, y0))
        ornament = '<g transform="translate(%d 384)" fill="url(#%s)">%s</g>' % (w // 2, foil, SPRIG % foil)
    else:
        q = 15  # square notched corners, a touch more ledger than album
        inner = ("M%d %dH%dV%dH%dV%dH%dV%dH%dV%dH%dV%dH%dZ"
                 % (x0 + q, y0, x1 - q, y0 + q, x1, y1 - q, x1 - q, y1, x0 + q, y1 - q, x0, y0 + q, x0 + q))
        ornament = '<g transform="translate(%d 384)">%s</g>' % (w // 2, _pine_sprig(foil))
    return ('<defs>%s</defs><rect x="1.2" y="1.2" width="%s" height="%s" fill="none" stroke="url(#%s)" stroke-width="2.4"/>'
            '<rect x="13" y="13" width="%d" height="%d" fill="none" stroke="url(#%s)" stroke-width="3.2"/>'
            '<path d="%s" fill="none" stroke="url(#%s)" stroke-width="1.3"/>%s'
            % (_gradient(foil, stops, 0, 0, w, h, True), w - 2.4, h - 2.4, foil, w - 26, h - 26, foil, inner, foil, ornament))


def _pine_sprig(foil):
    """Sam's ornament: a short pine bough with its needles."""
    needles = ""
    for i in range(14):
        x = -40 + i * 6.2
        reach = 13 - abs(i - 6.5) * 1.1
        needles += "M%.1f 0L%.1f %.1fM%.1f 0L%.1f %.1f" % (x, x + 6, -reach, x, x + 6, reach)
    return ('<path d="%s" fill="none" stroke="url(#%s)" stroke-width="1.5" stroke-linecap="round"/>'
            '<path d="M-48 0H48" fill="none" stroke="url(#%s)" stroke-width="2.2" stroke-linecap="round"/>'
            '<path d="M-48 0H-98M48 0H98" fill="none" stroke="url(#%s)" stroke-width="1.2"/>' % (needles, foil, foil, foil))


def _oval_frame(foil):
    return ('<ellipse cx="108" cy="128" rx="104" ry="124" fill="url(#%s)"/>'
            '<ellipse cx="108" cy="128" rx="104" ry="124" fill="none" stroke="#3e2a08" stroke-width="1" opacity=".7"/>'
            '<ellipse cx="108" cy="128" rx="97" ry="117" fill="none" stroke="#fff2c0" stroke-width="2.6" stroke-dasharray=".1 5.4" stroke-linecap="round" opacity=".92"/>'
            '<ellipse cx="108" cy="128" rx="91" ry="111" fill="#f4ebd8" stroke="#8a6a26" stroke-width="1.2"/>'
            '<ellipse cx="108" cy="128" rx="75" ry="95" fill="url(#kf-deep)"/>'
            '<ellipse cx="108" cy="128" rx="75" ry="95" fill="none" stroke="url(#%s)" stroke-width="2.2"/>' % (foil, foil))


def _arch_frame(foil):
    def arch(i):
        return "M%d 252V%dA%d %d 0 0 1 %d %dV252Z" % (4 + i, 108, 104 - i, 104 - i, 212 - i, 108)
    return ('<path d="%s" fill="url(#%s)"/><path d="%s" fill="none" stroke="#2c2206" stroke-width="1" opacity=".7"/>'
            '<path d="%s" fill="none" stroke="#efe0a6" stroke-width="2" opacity=".85"/>'
            '<path d="%s" fill="#efe7d2" stroke="#6e5a26" stroke-width="1.2"/><path d="%s" fill="url(#kf-deep)"/>'
            '<path d="%s" fill="none" stroke="url(#%s)" stroke-width="2.2"/>'
            % (arch(0), foil, arch(0), arch(7), arch(13), arch(29), arch(29), foil))


def _monogram(ctx, who, letter):
    """Their first initial where a photo will go later, narrowed to stay inside the mat."""
    font, top, x, y = ("pinyon", 112, 106, 162) if who == "mary" else ("cinzel-500", 84, 108, 166)
    size = min(top, top * 140 / max(1, width(ctx, font, letter, top) * SAFETY))
    family, more = (SCRIPT, "") if who == "mary" else (CAPS, ' font-weight="500"')
    stroke = "#2a1604" if who == "mary" else "#121a0c"
    return _text(x, y, size, family, "url(#kf-bright)", letter,
                 ' text-anchor="middle" stroke="%s" stroke-width=".6" paint-order="stroke"%s' % (stroke, more))


def _frame(ctx, who, letter):
    """A gilt frame with a cream mat, the monogram waiting where the photo will go."""
    look = KEEPSAKE[who]
    defs = (_gradient("kf-foil", look["foil"], 0, 0, 216, 256, True) + _gradient("kf-bright", look["bright"], 30, 60, 186, 200, True) +
            '<radialGradient id="kf-deep" cx=".44" cy=".38" r=".8"><stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></radialGradient>' % look["mat"] +
            '<filter id="kf-shadow" x="-10%" y="-10%" width="125%" height="125%"><feDropShadow dx="1" dy="3" stdDeviation="3" flood-color="#321e0a" flood-opacity=".45"/></filter>')
    shape = _oval_frame("kf-foil") if who == "mary" else _arch_frame("kf-foil")
    label = "A gilt frame with the letter %s, ready for a photo" % letter
    return ('<g filter="url(#kf-shadow)"><svg x="412" y="30" width="216" height="256" viewBox="0 0 216 256" role="img" aria-label="%s"><defs>%s</defs>%s%s</svg></g>'
            % (_esc(label), defs, shape, _monogram(ctx, who, letter)))


def _fit_name(ctx, name):
    """Big on one line if it can be, then two lines, then smaller still: a long name is never cut."""
    for most, floor in ((1, 60), (2, 44)):
        lines, size = _fit(ctx, "pinyon", name, 124, floor, NAME_W, NAME_ROOM, NAME_LEAD, most=most)
        if lines:
            return lines, size
    return _fit_all(ctx, "pinyon", name, 44, 44, NAME_W, NAME_ROOM, NAME_LEAD)


def _foil_name(ctx, who, name):
    """The name in the same foil as the cards, deep enough to hold on cream paper."""
    lines, size = _fit_name(ctx, name)
    step = size * NAME_LEAD
    first = 514 - (len(lines) - 1) * step
    more = ' text-anchor="middle" stroke="#2a1a04" stroke-width=".7" paint-order="stroke"'
    texts = "".join(_text(NAME_CENTER, first + i * step, size, SCRIPT, "url(#kn-foil)", line, more)
                    for i, line in enumerate(lines))
    return "<defs>%s</defs>%s" % (_gradient("kn-foil", KEEPSAKE[who]["name"], 50, 436, 260, 536, True), texts)


def _embossed(x, y, size, family, fill, body, more="", dark=False):
    """The board's text-shadow: a line of light under the letters, and a thin dark one over them on the big numeral."""
    light = _text(x, y, size, family, "#ffffff", body, more + ' fill-opacity=".75" transform="translate(0 1)"')
    shade = _text(x, y, size, family, "#281010", body, more + ' fill-opacity=".25" transform="translate(0 -1)"') if dark else ""
    return light + shade + _text(x, y, size, family, fill, body, more)


def _date_line(ctx, text, top, deep):
    """A weekday or month: Cinzel 700, 30/40, spaced .16em, narrowing if it must."""
    lines, size = _fit_all(ctx, "cinzel-700", text, 30, 20, 300, 41, 40 / 30, track=.16)
    drop = _baseline(ctx, "cinzel-700", size, 40)
    more = ' text-anchor="middle" font-weight="700" letter-spacing="%s"' % _n(size * .16)
    return "".join(_embossed(194, top + i * 40 + drop, size, CAPS, deep, line, more) for i, line in enumerate(lines))


def _date_block(ctx, who, weekday, day, month):
    deep = KEEPSAKE[who]["deep"]
    lines, size = _fit_all(ctx, "garamond-500", day, 200, 80, 300, 189, 188 / 200)
    more = ' text-anchor="middle" font-weight="500" style="font-variant-numeric:lining-nums"'
    numeral = _embossed(194, 96 + _baseline(ctx, "garamond-500", size, 188), size, GARAMOND, deep, " ".join(lines), more, dark=True)
    return _date_line(ctx, weekday, 56, deep) + numeral + _date_line(ctx, month, 284, deep)


def _memory_block(ctx, who, age_line, memory_line):
    """The age and the memory lines, in the room left under the rule."""
    look, parts, y = KEEPSAKE[who], [], MEMORY_TOP
    if age_line:
        lines, size = _fit_all(ctx, "garamond-500", age_line, 34, 24, MEMORY_W, 89, 44 / 34)
        step = size * 44 / 34
        for line in lines:
            parts.append(_text(MEMORY_X, y + _baseline(ctx, "garamond-500", size, step), size, GARAMOND, look["deep"], line, ' font-weight="500"'))
            y += step
    if memory_line:
        y += 8
        lines, size = _fit_all(ctx, "garamond-400", memory_line, 28, 22, MEMORY_W, MEMORY_TOP + MEMORY_ROOM - y, 36 / 28)
        step = size * 36 / 28
        for line in lines:
            parts.append(_text(MEMORY_X, y + _baseline(ctx, "garamond-400", size, step), size, GARAMOND, look["ink"], line))
            y += step
    return "".join(parts)


def draw_keepsake(ctx, who, name, weekday, day, month, age_line="", memory_line=""):
    """Board A at 724x616 for who ("mary" or "sam"): the date, a framed monogram, the name in foil, age and memory."""
    who = "sam" if who == "sam" else "mary"
    name, weekday, day, month = clean(name), clean(weekday), clean(day), clean(month)
    letter = next((c.upper() for c in name if c.isalpha()), "")
    light, deep, seed = KEEPSAKE[who]["paper"]
    body = (_sheet("kp", 724, 616, light, deep, seed) + _keep_rules(who) + _date_block(ctx, who, weekday, day, month) +
            _frame(ctx, who, letter[:1]) + _foil_name(ctx, who, name) + _memory_block(ctx, who, clean(age_line), clean(memory_line)))
    label = "A keepsake page for %s, %s %s %s" % (name, weekday, day, month)
    return _with_fonts(ctx, _root(724, 616, label, body))


# Saving

def _file_id(value):
    text = str(value)
    if not ID_RE.fullmatch(text):
        raise ValueError("a card id is 1 to 40 lowercase letters, digits, - or _")
    return text


def save_card(ctx, card):
    """Writes a card's pictures flat in ctx.files, over any earlier ones. card holds id, front, line, verse (a list of
    lines), words, signature and hand. Returns {"files": {part: name}, "fits", "verse_left_out", "size"}.
    When the words can't fit nothing is written and files is empty."""
    card_id = _file_id(card["id"])
    inside = draw_inside(ctx, card.get("verse"), card.get("words"), card.get("signature"), card.get("hand", "cursive"))
    result = {"files": {}, "fits": inside["fits"], "verse_left_out": inside["verse_left_out"], "size": inside["size"]}
    if not inside["fits"]:
        return result
    front = draw_front(ctx, card["front"], card.get("line"))
    pictures = {"front": front, "inside": inside["svg"], "both": draw_both(front, inside["svg"]), "left": draw_left(),
                "print": draw_print_sheet(front, inside["svg"])}
    for part, svg in pictures.items():
        name = "card-%s-%s.svg" % (card_id, part)
        ctx.files.write_text(name, svg)
        result["files"][part] = name
    return result


def save_letter(ctx, letter):
    """Writes letter-<id>.svg in ctx.files, over any earlier one, and returns {"files": {"letter": name}}."""
    name = "letter-%s.svg" % _file_id(letter["id"])
    ctx.files.write_text(name, draw_letter(ctx, letter.get("words"), letter.get("signature")))
    return {"files": {"letter": name}}


# Mary's tools. Every "say" is something she could say aloud as it stands, and "note" carries the same words because
# Live never sees "say". The facts are in the other fields. A draft lives in ctx.store, so a restart keeps it.

SHOWN_MAX = 4
WORDS_MAX = 1200
LINE_MAX = 40
NAME_MAX = 60
LIKES_MAX = 200
AGE_MAX = 60
MEMORY_MAX = 110
INDEX_MAX = 400
READ_MAX = 3000
PICTURE_MAX = 3_000_000  # one saved jpeg; each piece of it comes in its own event, because an event is 4 KB at most
PICTURE_PARTS = ("front", "inside", "both", "mail")
JPEG_MAGIC = b"\xff\xd8\xff"
WATER_TAGS = {"water", "lake", "sea", "ocean", "river", "boat", "boats", "fishing"}
FAITH_TAGS = {"church", "faith"}
FAITH_WORDS = {"faith", "church", "god", "lord", "jesus", "prayer", "prayers", "pray", "praying", "bible", "hymn", "hymns"}
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
          "december")
PICK_NUMBERS = {"first": 1, "1st": 1, "1": 1, "second": 2, "2nd": 2, "2": 2, "two": 2, "third": 3, "3rd": 3, "3": 3,
                "three": 3, "fourth": 4, "4th": 4, "4": 4, "four": 4}
PICK_SKIP = {"the", "a", "an", "one", "with", "that", "this", "at", "of", "and", "in", "on", "it", "i", "like", "want",
             "please", "number", "card", "picture", "small"}
SAY_NO_CARD = "We haven't started a card yet."
SAY_PICK_FIRST = "Which picture do you like for the front of the card?"  # M20, Andy's wording
SAY_NEEDS_WORDS = "There's nothing saved yet. It needs your words first."
SAY_TOO_LONG = "That's too long for a card. We can shorten it, or I can make it a plain message."
SAY_NOTHING_READY = "Nothing's ready to send yet."
SAY_NO_EMAIL = "Your email isn't set up, so this one can go by printing. Want it printed?"
SAY_CANT_SEND = "I can't send that one as it is. Want it printed?"
SAY_BOOK_LOCKED = "Your address book is locked right now, so I can't look them up. A helper can open it."  # M19
SAY_BOOK_LOCKED_SAVE = "Your address book is locked right now, so I can't change it. A helper can open it."  # M19
SAY_NO_PICTURE = "The picture wouldn't make. I can send the words as a plain message, or print it."
SAY_PRINT_OFFER = "Would you like it printed so it can be mailed?"
# M17: with no printer she offers nothing and says it's saved. %s is card, message or page (_what).
SAY_SAVED_LATER = "The %s is saved, and a helper can print it for you later."
SAY_NO_EMAIL_LATER = "Your email isn't set up. " + SAY_SAVED_LATER
SAY_CANT_SEND_LATER = "I can't send that one as it is. " + SAY_SAVED_LATER
SAY_NO_PICTURE_PLAIN = "The picture wouldn't make. I can send the words as a plain message."
SAY_NO_PRINTER = "It's saved. There's no printer on this computer, so a helper can print it for you later."
SAY_WHO = "Who's it for?"
SAY_NEXT = "When they're happy with it, call send_it."
ASKS_WORDS = {"money": "money", "password": "a password", "ssn": "a Social Security number"}
OCCASION_WORDS = {"birthday": "birthday", "get_well": "get well", "sympathy": "sympathy", "thank_you": "thank-you",
                  "christmas": "Christmas", "thanksgiving": "Thanksgiving"}
CONTENT_FIELDS = ("kind", "id", "person", "occasion", "line", "front", "words", "signature", "verse", "verse_off",
                  "left_out", "hand")  # a change to any of these means the look no longer shows what would go
DETAIL_MAX = 120
ADDRESS_MAX = 254
ADDRESS_LINES = 3  # M18: how many lines of theirs an address waits for a yes or a keep answer before it's let go
ASKS_ADDRESS_RE = re.compile(r"\baddress\b|(?:'s|\b(?:her|his|their|my|the|that|whose))\s+e-?mail\b")  # M18: not "an email"
ASKS_HEAR_RE = re.compile(r"\b(?:what|what's|read|tell|say|spell|give|repeat|remind|hear|know|have|got|need|find|look)\b")
ASKS_FILL_RE = re.compile(r"\b(?:fill|put|type|enter|paste|copy|write|use|add)\b")
ASKS_BOX_RE = re.compile(r"\b(?:fill|put|type|enter|paste|copy)\b")
ADDRESS_RE = re.compile(r"[a-z0-9_%+'-]+(?:\.[a-z0-9_%+'-]+)*@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}")
SPOKEN_DIGITS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
                 "eight": "8", "nine": "9"}
SPOKEN_ADDRESS = ((r"\b(?:capital|cap|upper case|uppercase|lower case|lowercase)\s+", ""),
                  (r"(?:\s+at\b)+(?:\s+sign)?\s+", "@"),
                  (r"\s*\b(?:dot|period|point)\b\s*", "."),
                  (r"\s*\bunderscore\b\s*", "_"),
                  (r"\s*\b(?:dash|hyphen)\b\s*", "-"),
                  (r"\s*\bplus\b\s*", "+"))
_FORGET_FIELD = r"(?P<field>e-?mail(?:\s+address)?|(?:mailing|street|home)\s+address|address)"  # M19
FORGET_ADDRESS_RES = (re.compile(r"(?:the\s+)?(?P<who>.+?)\s+" + _FORGET_FIELD),
                      re.compile(r"(?:the\s+|my\s+)?" + _FORGET_FIELD + r"\s+(?:for|of)\s+(?P<who>.+)"))
FORGET_ASK = "ask"  # M19: a bare "address" with both filled, so she asks which
SAY_FOLD = ("It prints on one sheet of paper. Fold the top half back behind, printed side out, then fold it left to "
            "right. Mailing it needs some help from the facility.")
SAY_SHEET = "It prints on one sheet of paper. Mailing it needs some help from the facility."

_LOCK = threading.RLock()  # a tap, a picture and a spoken line may land together


def _locked(fn):
    @functools.wraps(fn)
    def run(*args, **kwargs):
        with _LOCK:
            return fn(*args, **kwargs)
    return run


def _reply(say, **facts):
    for key, value in facts.items():  # a result is 4 KB at most, and letters outside plain English count six times over
        if isinstance(value, str) and len(json.dumps(value)) > READ_MAX:
            facts[key] = value[:READ_MAX // 6]
    return dict(facts, note=say, say=say)


def _said(value, limit):
    return clean(value if isinstance(value, str) else "")[:limit].strip()


def _word_set(text):
    return set(re.findall(r"[a-z0-9']+", clean(text or "").lower()))


def _today():
    return datetime.date.today()


def _slug(text, limit):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-")


def _new_id(person):
    return "%s-%s-%04x" % (_slug(person, 16) or "card", _today().strftime("%Y%m%d"), random.randrange(16 ** 4))


def _draft(ctx):
    if "draft" not in ctx.state:
        ctx.state["draft"] = ctx.store.get("draft")
    return ctx.state["draft"]


def _what(ctx):  # M17
    """The plain word for what's up: a keepsake page, a message or a card."""
    if ctx.state.get("keepsake"):
        return "page"
    draft = _draft(ctx)
    return "message" if draft and draft.get("kind") == "letter" else "card"


def _saved_later(ctx):  # M17
    """The no-printer line, or "" when nothing is saved to print."""
    saved = ctx.state.get("keepsake") or (_draft(ctx) or {}).get("rev")
    return SAY_SAVED_LATER % _what(ctx) if saved else ""


def _then_print(ctx, lead=""):  # M17
    """What follows a send: the print offer when there's a printer, the saved line when there isn't."""
    return ("%s %s" % (lead, SAY_PRINT_OFFER if ctx.has_printer() else _saved_later(ctx))).strip()


def _no_picture(ctx):  # M17
    return SAY_NO_PICTURE if ctx.has_printer() else ("%s %s" % (SAY_NO_PICTURE_PLAIN, _saved_later(ctx))).strip()


def _cant_go(ctx, offer, without_printer):  # M17
    can_print = ctx.has_printer()
    return _reply(offer if can_print else without_printer % _what(ctx), sent=False, saved=True, can_print=can_print)


def _keep(ctx, draft):
    before = _draft(ctx) or {}
    if any(before.get(field) != draft.get(field) for field in CONTENT_FIELDS):  # the look must show exactly what goes
        ctx.disarm_send()
        _no_look(ctx)
        ctx.state.pop("last_sent", None)
        draft.pop("look_wanted", None)
    ctx.state["draft"] = draft
    ctx.state.pop("keepsake", None)
    ctx.store.put("draft", draft)


def _file_away(ctx, draft):
    """Keeps a saved card or letter for open_saved: its whole record, and a small list to find it by."""
    draft["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    ctx.store.put("saved-" + draft["id"], draft)
    index = [entry for entry in ctx.store.get("index", []) if entry["id"] != draft["id"]]
    index.append({"id": draft["id"], "person": draft.get("person", ""), "updated": draft["updated"]})
    ctx.store.put("index", index[-INDEX_MAX:])


def _is_card(draft):
    return bool(draft) and draft.get("kind") == "card"


def _tags(ctx, draft):
    entry = fronts(ctx).get(draft.get("front")) or {}
    return {tag.lower() for tag in entry.get("tags", [])}


def _verse_true(ctx, draft, assumed):
    if assumed in ("man", "woman"):
        return draft.get("person_is") == assumed
    if assumed == "water":
        return bool(_tags(ctx, draft) & WATER_TAGS)
    if assumed == "faith":
        return bool(_tags(ctx, draft) & FAITH_TAGS) or draft.get("occasion") in ("sympathy", "christmas") \
            or bool(_word_set(draft.get("likes")) & FAITH_WORDS)
    return False


def _verses(ctx, draft):
    """The verses that are true of this person and this front, the most particular first."""
    fitting = [v for v in VERSES.get(draft.get("occasion"), []) if all(_verse_true(ctx, draft, a) for a in v["assumes"])]
    return [v["lines"] for v in sorted(fitting, key=lambda v: -len(v["assumes"]))]


def _reading(draft):
    verse = [] if draft.get("left_out") else (draft.get("verse") or [])
    return " ".join(verse + [draft.get("words") or "", draft.get("signature") or ""]).strip()


def _when(day):
    return "%s, %s %d" % (day.strftime("%A"), day.strftime("%B"), day.day)


def _save_card(ctx, trial):
    """Saves a trial copy of the draft and makes it the draft. False, with nothing changed, when it won't fit."""
    saved = save_card(ctx, trial)
    if not saved["fits"]:
        return False
    for part in PICTURE_PARTS:  # a picture of the old words must not outlive them
        ctx.files.delete("card-%s-%s.jpg" % (trial["id"], part))
    trial.update(rev=trial.get("rev", 0) + 1, left_out=saved["verse_left_out"], saved=True, step="open")
    _file_away(ctx, trial)
    _keep(ctx, trial)
    return True


def _front_file(key):
    return "card-draft-%s.svg" % key


def _show_card(ctx, draft, opening=False):
    data = {"id": draft["id"], "rev": draft.get("rev", 0), "stage": draft["step"], "opening": opening}
    if draft["step"] == "closed":
        data["front"] = _front_file(draft["front"])
    else:
        data.update({part: "card-%s-%s.svg" % (draft["id"], part) for part in ("front", "left", "inside", "both")})
        data["pictures"] = not all(ctx.files.exists("card-%s-%s.jpg" % (draft["id"], part)) for part in PICTURE_PARTS)
    ctx.effect("card", data)


def _show_fronts(ctx, draft):
    every = fronts(ctx)
    ctx.effect("fronts", {"cards": [{"number": number, "name": every[key]["name"], "key": key, "file": _front_file(key)}
                                    for number, key in enumerate(draft["shown"], 1)]})


def _show_letter(ctx, draft):
    ctx.effect("letter", {"file": "letter-%s.svg" % draft["id"], "rev": draft.get("rev", 0)})


def _show(ctx, draft, opening=False):
    if draft["step"] == "fronts":
        _show_fronts(ctx, draft)
    elif draft["step"] == "letter":
        _show_letter(ctx, draft)
    else:
        _show_card(ctx, draft, opening)


def _offer(ctx, draft):
    """The picker: the occasion's fronts, those nearest what they love first, each drawn with the personal line."""
    every, likes = fronts(ctx), _word_set(draft.get("likes"))

    def match(entry):
        tags = [tag.lower() for tag in entry["tags"]]
        return sum(any(w == t or w.rstrip("s") == t or (len(w) >= 4 and t.startswith(w)) for t in tags) for w in likes)

    chosen = sorted((e for e in every.values() if draft["occasion"] in e["occasions"]), key=lambda e: -match(e))[:SHOWN_MAX]
    for entry in chosen:
        ctx.files.write_text(_front_file(entry["key"]), draw_front(ctx, entry["key"], draft.get("line")))
    draft.update(shown=[entry["key"] for entry in chosen], step="fronts")
    _keep(ctx, draft)
    ctx.effect("show_screen")
    _show_fronts(ctx, draft)
    return [{"number": number, "name": entry["name"]} for number, entry in enumerate(chosen, 1)]


@_locked
def show_fronts(ctx, person="", occasion="birthday", likes="", line="", person_is="unknown"):
    draft = {"kind": "card", "id": _new_id(_said(person, NAME_MAX)), "person": _said(person, NAME_MAX),
             "person_is": person_is if person_is in ("man", "woman") else "unknown",
             "occasion": occasion if occasion in VERSES else "birthday", "likes": _said(likes, LIKES_MAX),
             "line": _said(line, LINE_MAX), "hand": ctx.store.get("hand", "cursive"), "rev": 0}
    shown = _offer(ctx, draft)
    if ctx.heard:
        return _reply("Here are some fronts. Writing the words takes the internet, so we can finish it when I'm back on.",
                      fronts=shown)
    return _reply("These are up. Which one do you like?", fronts=shown, person=draft["person"])


def _match_front(ctx, choice, draft):
    """A number, a name or a word from a front's tags, among those shown. None when it isn't clear which."""
    shown, every = draft.get("shown", []), fronts(ctx)
    words = re.findall(r"[a-z0-9']+", clean(str(choice)).lower())
    wanted = set(words) - PICK_SKIP
    scores = {}
    for key in shown:
        entry = every[key]
        own = {key} | _word_set(entry["name"]) | _word_set(entry.get("label")) | {tag.lower() for tag in entry["tags"]}
        scores[key] = len(wanted & own)
    best = max(scores.values(), default=0)
    hits = [key for key, score in scores.items() if score == best]
    if best and len(hits) == 1:
        return hits[0]
    if best:
        return None
    number = next((PICK_NUMBERS[w] for w in words if w in PICK_NUMBERS), None)
    if "last" in words:
        number = len(shown)
    if number is None and "one" in words and len(words) <= 2 and "the" not in words:
        number = 1
    return shown[number - 1] if number and number <= len(shown) else None


@_locked
def pick_front(ctx, choice):
    draft = _draft(ctx)
    if not _is_card(draft) or not draft.get("shown"):
        return _reply(SAY_NO_CARD, picked=None)
    key = _match_front(ctx, choice, draft)
    if key is None:
        return _reply("I'm not sure which one you mean.", picked=None)
    trial = dict(draft, front=key)
    fitting = _verses(ctx, trial)
    if not trial.get("verse_off") and (not trial.get("verse_chosen") or trial.get("verse") not in fitting):
        trial["verse"] = fitting[0] if fitting else []
    name = fronts(ctx)[key]["name"]
    ctx.effect("show_screen")
    if trial.get("saved") and (_save_card(ctx, trial) or _save_card(ctx, dict(trial, verse=[]))):
        _show(ctx, _draft(ctx))
        return _reply("That's on the card now.", picked=name, read_back=_reading(_draft(ctx)))
    trial["step"] = "closed"
    _keep(ctx, trial)
    _show(ctx, trial)
    return _reply("What do you want to say?", picked=name)


@_locked
def set_words(ctx, words, signature=""):
    draft = _draft(ctx)
    if not _is_card(draft):
        return _reply(SAY_NO_CARD)
    words, signature = clean(words if isinstance(words, str) else "").strip(), _said(signature, NAME_MAX)
    if len(words) > WORDS_MAX:
        return _reply(SAY_TOO_LONG, too_long=True, saved=False)
    words, signature = words or draft.get("words", ""), signature or draft.get("signature", "")
    if not draft.get("front"):
        _keep(ctx, dict(draft, words=words, signature=signature))
        return _reply(SAY_PICK_FIRST, saved=False)
    if not words:
        return _reply("What do you want to say?", saved=False)
    if not signature:
        _keep(ctx, dict(draft, words=words))
        return _reply("How do you want to sign it?", saved=False, words_kept=True, need="signature")
    first = not draft.get("saved")
    trial = dict(draft, words=words, signature=signature)
    if not _save_card(ctx, trial):
        return _reply(SAY_TOO_LONG, too_long=True, saved=False)
    _show(ctx, trial, opening=first)
    facts = {"saved": True, "read_back": _reading(trial), "next": SAY_NEXT}
    say = "Here's how it reads."
    if trial["left_out"]:
        facts["verse_left_out"] = True
        say = "The verse won't fit with your words, so I left it out. Here's how it reads."
    if first and trial["hand"] == "cursive" and not trial.get("mentioned"):
        facts["mention"] = "Say once: I can write it plainer if cursive's hard to read."
        trial["mentioned"] = True
        _keep(ctx, trial)
    return _reply(say, **facts)


@_locked
def set_hand(ctx, hand=""):
    draft = _draft(ctx)
    if ctx.heard:  # the only phrase here is "write it plainer"
        if not _is_card(draft):
            return {"not_for_me": True}
        hand = "plain"
    current = draft.get("hand") if _is_card(draft) else ctx.store.get("hand", "cursive")
    hand = hand if hand in ("plain", "cursive") else ("cursive" if current == "plain" else "plain")
    if _is_card(draft) and draft.get("saved"):
        trial = dict(draft, hand=hand)
        if not _save_card(ctx, trial):
            return _reply("It won't fit on the card that way.", hand=current, too_long=True)
        _show(ctx, trial)
    elif _is_card(draft):
        _keep(ctx, dict(draft, hand=hand))
    ctx.store.put("hand", hand)
    return _reply("Written plainer now." if hand == "plain" else "Back in cursive.", hand=hand)


@_locked
def change_verse(ctx, which="next"):
    draft = _draft(ctx)
    if not _is_card(draft) or not draft.get("front"):
        return _reply(SAY_PICK_FIRST if _is_card(draft) else SAY_NO_CARD)
    if which == "none":
        trial = dict(draft, verse=[], verse_off=True)
    else:
        fitting = _verses(ctx, draft)
        if not fitting or fitting == [draft.get("verse")]:
            return _reply("That's the only verse that suits this card.", verse=draft.get("verse") or [])
        current = fitting.index(draft["verse"]) if draft.get("verse") in fitting else -1
        trial = dict(draft, verse=fitting[(current + 1) % len(fitting)], verse_off=False, verse_chosen=True)
    if draft.get("saved"):
        if not _save_card(ctx, trial):
            return _reply("That verse won't fit with your words, so I left the card as it was.", changed=False)
        _show(ctx, trial)
    else:
        _keep(ctx, trial)
    if trial.get("left_out"):
        return _reply("That verse won't fit with your words, so I left it out.", verse_left_out=True, verse=[])
    return _reply("The verse is gone." if which == "none" else "Here's the verse now.", verse=trial["verse"])


@_locked
def change_front(ctx):
    draft = _draft(ctx)
    if not _is_card(draft):
        return _reply(SAY_NO_CARD)
    return _reply("Here are the fronts again. Your words are kept.", fronts=_offer(ctx, dict(draft)))


@_locked
def read_back(ctx):
    draft = _draft(ctx)
    if not draft:
        return _reply(SAY_NO_CARD)
    verse = [] if draft.get("left_out") else (draft.get("verse") or [])
    return _reply("Here's how it reads.", verse=verse, words=draft.get("words", ""), signature=draft.get("signature", ""))


@_locked
def save_card_now(ctx):
    draft = _draft(ctx)
    if not draft or not draft.get("rev"):
        return _reply(SAY_NEEDS_WORDS, saved=False)
    return _reply("It's saved on your laptop, as of %s." % _when(_today()), saved=True)


def _print_file(ctx, draft):
    keepsake = ctx.state.get("keepsake")
    if keepsake:
        return keepsake["file"]
    if not draft or not draft.get("rev"):
        return None
    return "letter-%s.svg" % draft["id"] if draft["kind"] == "letter" else "card-%s-print.svg" % draft["id"]


@_locked
def print_card(ctx):
    file = _print_file(ctx, _draft(ctx))
    if file is None:
        return {"not_for_me": True} if ctx.heard else _reply(SAY_NEEDS_WORDS, printing=False)
    ctx.state.pop("print_failed", None)
    if not ctx.has_printer():  # M17
        return _reply(SAY_NO_PRINTER, printing=False, saved=True)
    ctx.effect("print", {"file": file})
    return _reply(SAY_FOLD if file.endswith("-print.svg") else SAY_SHEET, printing=True)


# Contacts live in the sealed address book, through ctx.people. An address leaves there only in a page effect, never
# in a result, a say or view.

def _norm(name):
    text = clean(str(name or "")).lower().replace("\u2019", "'").strip()
    return " ".join(re.sub(r"^(?:my|our)\s+", "", text).split())


def _said_relation(name):
    """"My son", for someone new: how they said it is the relationship too."""
    plain = re.sub(r"^my\s+", "", name, flags=re.I)
    return {"relationship": plain} if plain != name else {}


def _cant_keep(ctx):
    return SAY_BOOK_LOCKED_SAVE if ctx.people.locked() else "I can't keep any more people."


def _nobody(ctx):
    """No one by that name. A locked book says so: it must never sound as if they're gone."""
    return _reply(SAY_BOOK_LOCKED, known=False, book_locked=True) if ctx.people.locked() else {"known": False}


def _which(hits, **facts):
    names = [c["name"] for c in hits]
    return _reply("Which one, %s or %s?" % (", ".join(names[:-1]), names[-1]), which=names, **facts)


def _whose(name):
    """Mark's, or your son's, by name only, so it stays right for anyone."""
    return re.sub(r"^my\s+", "your ", name, flags=re.I) + "'s"


def _short_from(line):
    """The name in the gate's own line, so what she says next can't drift from it."""
    found = re.search(r"goes to (.+)'s email", line or "")
    return found.group(1) if found else "them"


def _spoken_address(text):
    """"mark dot hollis at gmail dot com" as an address, or None when it doesn't make one."""
    text = str(text if isinstance(text, str) else "")[:ADDRESS_MAX * 4].strip().lower().replace("\u2019", "'")
    if re.search(r"\s", text):  # only speech has spaces: a typed "seven@aol.com" stays as it is
        text = re.sub(r"\b(%s)\b" % "|".join(SPOKEN_DIGITS), lambda m: SPOKEN_DIGITS[m.group(1)], text)
        for pattern, part in SPOKEN_ADDRESS:
            text = re.sub(pattern, part, text)
    text = re.sub(r"\s+", "", text).strip(".,;:!?<>\"")
    return text if len(text) <= ADDRESS_MAX and ADDRESS_RE.fullmatch(text) else None


# Sending. The skill can show a look and no more: a yes, a tap and the clock are checked in core code.

def _no_look(ctx):
    for key in ("held", "send_view"):
        ctx.state.pop(key, None)


def _no_picture_wanted(ctx):
    draft = _draft(ctx)
    if draft and draft.get("look_wanted"):
        _keep(ctx, {key: value for key, value in draft.items() if key != "look_wanted"})


def _drop_send(ctx):
    """The screen left, or the card was put away: no look, and no picture still on its way to one."""
    ctx.disarm_send()
    _no_look(ctx)
    _no_picture_wanted(ctx)


def _email(draft):
    """The subject and body of what would go. No tag and no footer: it's only theirs."""
    signature, words = draft.get("signature", ""), draft.get("words", "")
    if draft["kind"] == "letter":
        subject = "A message from %s" % signature
    elif draft.get("occasion") in OCCASION_WORDS:
        subject = "A %s card from %s" % (OCCASION_WORDS[draft["occasion"]], signature)
    else:
        subject = "A card from %s" % signature
    return subject, "%s\n\n%s" % (words, signature)


def _paused(reason):
    return _reply("This asks for %s. I won't send that. If someone's asked you for it, talk it over with someone you "
                  "trust first." % ASKS_WORDS[reason], paused=True, sent=False)


def _ask_address(ctx, name, bad=False, locked=False):
    ctx.state.pop("address_wait", None)
    ctx.state["send_view"] = {"kind": "need_address", "name": name}
    ctx.effect("show_screen")
    ctx.effect("need_address", {"name": name, "bad": bad})
    say = "That doesn't look like an address. " if bad else SAY_BOOK_LOCKED + " " if locked else ""
    return _reply(say + "What's %s email address? You can say it, or a helper can type it." % _whose(name),
                  need_address=True, sent=False)


def _waiting_address(ctx, name, contact):
    """An address they checked just now, for this person, held in memory only."""
    wait = ctx.state.get("address_wait")
    if wait and wait.get("right") and _norm(wait["person"]) in (_norm(name), _norm(contact and contact["name"])):
        return wait["address"]
    return None


def _picture_current(ctx, draft):
    return draft.get("mail_rev") == draft.get("rev") and ctx.files.exists("card-%s-mail.jpg" % draft["id"])


def _show_look(ctx, held):
    """The look on the page. For someone in the book the core adds the address on its way out, so it's never held here."""
    if held.get("handle"):
        ctx.people.show_address(held["handle"], "look", held["effect"])
    else:
        ctx.effect("look", held.get("effect", {}))


def _arm(ctx, draft, who, address, contact):
    """Arms the gate. With an address just told and checked it goes as it is, in memory only; otherwise to contact in the book."""
    subject, body = _email(draft)
    pictures = []
    if draft["kind"] == "card":
        name = "card-%s-mail.jpg" % draft["id"]
        pictures = [{"name": name, "data": ctx.files.read_bytes(name)}]
    if address:
        armed = ctx.arm_send(who, address, subject, body, pictures)
    else:
        armed = ctx.people.send_to(contact, subject, body, pictures)
    if not armed["ok"]:
        reason = armed.get("reason")
        if reason in ASKS_WORDS:
            return _paused(reason)
        if reason == "too_big":
            return _reply(_no_picture(ctx), picture_failed=True, sent=False)
        if reason == "no_email":
            return _cant_go(ctx, SAY_NO_EMAIL, SAY_NO_EMAIL_LATER)
        return _cant_go(ctx, SAY_CANT_SEND, SAY_CANT_SEND_LATER)
    line = ctx.send_state()["line"]
    data = {"look": armed["look"], "name": who, "kind": draft["kind"], "rev": draft.get("rev", 0)}
    if address:
        data["email"] = address
    if draft["kind"] == "card":
        data["front"] = "card-%s-front.svg" % draft["id"]
    else:
        data["file"] = "letter-%s.svg" % draft["id"]
    short = _short_from(line)
    held = {"look": armed["look"], "person": who, "short": short, "effect": data}
    held.update({"address": address} if address else {"handle": contact})
    ctx.state["held"] = held
    ctx.state["send_view"] = {"kind": "look", "name": short}
    ctx.effect("show_screen")
    _show_look(ctx, held)
    return _reply(line, look_up=True, sent=False)


def _send_flow(ctx):
    """Every send starts here, and it runs again after an address or a picture lands, so no step can be skipped."""
    draft = _draft(ctx)
    if not draft or not draft.get("rev") or ctx.state.get("keepsake"):
        return _reply(SAY_NOTHING_READY, sent=False, saved=False)
    reason = ctx.asks_for("%s\n%s" % _email(draft))
    if reason:
        return _paused(reason)
    if not ctx.mail_ready():
        return _cant_go(ctx, SAY_NO_EMAIL, SAY_NO_EMAIL_LATER)
    name = draft.get("person", "")
    if not name:
        return _reply(SAY_WHO, need_person=True, sent=False)
    hits = ctx.people.find(name)
    if len(hits) > 1:
        return _which(hits, need_person=True, sent=False)
    contact = hits[0] if hits else None
    address = _waiting_address(ctx, name, contact)
    if not address and not (contact and contact["has_email"]):
        return _ask_address(ctx, name, locked=ctx.people.locked())
    state = ctx.send_state()
    if state["state"] in ("counting", "sending"):
        return {"counting": True}
    if state["state"] == "look":
        return {"look_up": True} if state["line_said"] else _reply(state["line"], look_up=True, sent=False)
    if draft["kind"] == "card" and not _picture_current(ctx, draft):
        _keep(ctx, dict(draft, look_wanted=True))
        ctx.effect("make_mail", {"id": draft["id"], "rev": draft.get("rev", 0)})
        return _reply("One moment.", sent=False)
    return _arm(ctx, draft, contact["name"] if contact else name, address, contact)


def _with_the_send(ctx):  # M18
    """Whether the address just checked is for the card or message that's ready to go."""
    draft = _draft(ctx)
    if not draft or not draft.get("rev") or ctx.state.get("keepsake"):
        return False
    name, hits = draft.get("person", ""), ctx.people.find(draft.get("person", ""))
    return bool(_waiting_address(ctx, name, hits[0] if len(hits) == 1 else None))


def _offer_keep(ctx, wait):  # M18
    """An address they told her with nothing being sent, checked with them. It stays only if they say so, in the book."""
    ctx.state.pop("address_wait", None)
    ctx.effect("leave_screen")
    hits = ctx.people.find(wait["person"])
    if len(hits) == 1 and ctx.people.detail(hits[0], "email").lower() == wait["address"]:
        return _reply("I've already got that one.", kept=True)
    ctx.state["address_told"] = {key: wait.get(key, "") for key in ("person", "address", "relationship")}
    return _reply("Keep %s address for next time?" % _whose(wait["person"]), keep_question=True)


def _keep_told(ctx, told, keep):  # M18
    """Their answer about an address told outside a send. A no changes nothing, so an address already saved stays."""
    if keep is not True:
        return _reply("All right.", kept=False)
    hits = ctx.people.find(told["person"])
    fields = {} if len(hits) == 1 else _said_relation(told["person"])
    fields.update(email=told["address"], asked=True, no_keep=False)
    if told.get("relationship"):
        fields["relationship"] = told["relationship"]
    kept = bool(ctx.people.keep(hits[0]["name"] if len(hits) == 1 else told["person"], fields))
    return _reply("Kept." if kept else _cant_keep(ctx), kept=kept)


def _asked_address(heard, contact):  # M18
    """Whether their own words ask to hear this address or put it in a box. Sending needs neither."""
    words = clean(heard or "").lower().replace("\u2019", "'")
    if ASKS_ADDRESS_RE.search(words) and (ASKS_HEAR_RE.search(words) or ASKS_FILL_RE.search(words)):
        return True
    names = _norm(contact["name"]).split()[:1] + [_norm(contact.get("relationship"))]
    return bool(ASKS_BOX_RE.search(words)) and any(name and re.search(r"\b%s\b" % re.escape(name), words) for name in names)


@_locked
def send_it(ctx, person=""):
    draft, person = _draft(ctx), _said(person, NAME_MAX)
    ready = bool(draft and draft.get("rev")) and not ctx.state.get("keepsake")
    if ctx.heard and not ready:
        return {"not_for_me": True}
    if ready and person and _norm(person) != _norm(draft.get("person")):
        draft = dict(draft, person=person)
        _keep(ctx, draft)
        _file_away(ctx, draft)
    return _send_flow(ctx)


@_locked
def give_address(ctx, address, person="", relationship=""):  # M18: relationship
    draft, person = _draft(ctx), _said(person, NAME_MAX)
    if draft and person and not draft.get("person"):
        draft = dict(draft, person=person)
        _keep(ctx, draft)
        if draft.get("rev"):
            _file_away(ctx, draft)
    name = person or (draft or {}).get("person", "")
    if not name:
        return _reply(SAY_WHO, need_person=True)
    spoken = _spoken_address(address)
    if spoken is None:
        return _ask_address(ctx, name, bad=True)
    ctx.state["address_wait"] = {"person": name, "address": spoken, "right": False,
                                 "relationship": _said(relationship, DETAIL_MAX)}
    ctx.state["send_view"] = {"kind": "address_wait", "name": name}
    ctx.effect("show_screen")
    ctx.effect("address_wait", {"name": name, "address": spoken})
    return {"spelled": spoken, "note": "Read it letter by letter, then ask if that's right."}


@_locked
def address_right(ctx, right):
    wait = ctx.state.get("address_wait")
    if not wait:
        return _reply("What's the address?", need_address=True)
    if right is not True:
        return _ask_address(ctx, wait["person"])
    wait["right"] = True
    ctx.state.pop("send_view", None)
    if not _with_the_send(ctx):  # M18
        return _offer_keep(ctx, wait)
    return _send_flow(ctx)


@_locked
def keep_address(ctx, keep):
    told = ctx.state.pop("address_told", None)  # M18: told outside a send
    if told:
        return _keep_told(ctx, told, keep)
    sent = ctx.state.get("just_sent")  # M19: a send already kept it, so all that's left to say is "don't keep it"
    if not sent:
        return _reply(_then_print(ctx) or "All right.", kept=False)
    if keep is True:
        return _reply("Kept.", kept=True)
    if not ctx.people.unkeep(sent["person"]):
        return _reply(SAY_BOOK_LOCKED_SAVE, kept=True)
    ctx.state.pop("just_sent", None)
    return _reply("All right.", kept=False)


@_locked
def save_contact(ctx, name, relationship="", facebook="", phone=""):
    name = _said(name, NAME_MAX)
    if not name:
        return _reply("Who should I remember?", saved=False)
    fields = _said_relation(name)
    for field, value in (("relationship", relationship), ("facebook", facebook), ("phone", phone)):
        value = _said(value, DETAIL_MAX)
        if value:
            fields[field] = value
    if not ctx.people.keep(name, fields):
        return _reply(_cant_keep(ctx), saved=False)
    return _reply("I've got %s." % name, saved=True)


@_locked
def find_contact(ctx, name):
    hits = ctx.people.find(_said(name, NAME_MAX))
    if len(hits) > 1:
        return _which(hits, known=True)
    if not hits:
        return _nobody(ctx)
    return {"known": True, "name": hits[0]["name"], "relationship": hits[0]["relationship"],
            "has_email": hits[0]["has_email"]}


@_locked
def contact_address(ctx, name):  # M18
    """A saved address for her to read out or put in a box, and only when their own words just asked for it."""
    hits = ctx.people.find(_said(name, NAME_MAX))
    if len(hits) > 1:
        return _which(hits, known=True)
    if not hits:
        return _nobody(ctx)
    found = {"known": True, "name": hits[0]["name"], "has_email": hits[0]["has_email"]}
    if not found["has_email"]:
        return found
    if not _asked_address(ctx.heard, hits[0]):
        return dict(found, not_asked=True, note="They didn't ask for the address. Use the name: a send needs no address.")
    return dict(found, address=ctx.people.detail(hits[0], "email"),
                note="For what they asked, this once. Spell it, or put it in the box.")


def _exactly(ctx, words, exact=True):
    """This exact name: someone in the list, else a "don't keep" mark, which has no handle and goes by its name.
    exact False: a mark counts however it's named."""
    found = [hit for hit in ctx.people.find(words) if _norm(hit["name"]) == _norm(words)]
    marks = ctx.people.marks(words, exact)
    return found or ([{"name": words}] if marks["asked"] or marks["no_keep"] else [])


def _address_hits(hits, field):  # M19
    """Who holds what they named, and which field: the one named, else the only one filled, else FORGET_ASK."""
    if field:
        return [hit for hit in hits if hit["has_" + field]], field
    hits = [hit for hit in hits if hit["has_email"] or hit["has_address"]]
    if any(hit["has_email"] and hit["has_address"] for hit in hits):
        return hits, FORGET_ASK
    return hits, "email" if any(hit["has_email"] for hit in hits) else "address"


def _forget_hits(ctx, about, own_name):
    """The people about means, what it takes of them (False for all of it, "email", "address" for the mailing address,
    or FORGET_ASK), and the name it came to."""
    words = str(about or "").strip(" .!?").replace("\u2019", "'")
    if own_name:
        return _exactly(ctx, words), False, words
    for pattern in FORGET_ADDRESS_RES:
        found = pattern.fullmatch(words.lower())
        if found:
            raw, said = found.group("who"), found.group("field")
            field = "email" if said.startswith("e") else "" if said == "address" else "address"  # M19
            for name in (re.sub(r"'s$|'$", "", raw), raw, raw[:-1] if raw.endswith("s") else raw):
                hits = ctx.people.find(name)
                if hits:
                    return (*_address_hits(hits, field), name)
            return [], field or "email", re.sub(r"'s$|'$", "", raw)
    return ctx.people.find(words) or _exactly(ctx, words, exact=False), False, words


def _holding(ctx, hits, wanted, own_name):
    """What's in memory for this person: the keys of ctx.state that hold their address."""
    names = {_norm(wanted)} | {_norm(c["name"]) for c in hits} | {_norm(c.get("relationship")) for c in hits}
    names.discard("")

    def theirs(person):
        return _norm(person) in names or (not own_name and _norm(person).split()[:1] == [_norm(wanted)])

    return [key for key in ("address_wait", "address_told", "just_sent", "held")  # M18: address_told
            if key in ctx.state and theirs(ctx.state[key]["person"])]


def _everything(about):
    return str(about or "").strip().lower() == "everything"


def _several(hits):  # M19
    """More than one person by different names: she asks which, and nothing goes until she knows."""
    return len({_norm(hit["name"]) for hit in hits}) > 1


@_locked
def on_forget(ctx, about, own_name=False):
    """A real forget. Their addresses and names come back so the core can drop them from talk history and mail.log.
    "Everything" leaves the address book alone: only what's held in memory goes."""
    if _everything(about):
        hits, only_address = [], False
        keys = [key for key in ("address_wait", "address_told", "just_sent", "held") if key in ctx.state]  # M18: address_told
    else:
        hits, only_address, wanted = _forget_hits(ctx, about, own_name)
        if only_address == FORGET_ASK or (_several(hits) and not own_name):  # M19
            return {"addresses": [], "texts": []}
        keys = [] if only_address == "address" else _holding(ctx, hits, wanted, own_name)
    addresses = [ctx.state[key]["address"] for key in keys if ctx.state[key].get("address")]
    texts = []
    for hit in hits:
        gone = ctx.people.forget(hit if "id" in hit else hit["name"], only_address)
        addresses += gone["addresses"]
        texts += gone["texts"]
    for key in keys:
        ctx.state.pop(key, None)
    if "held" in keys:
        _no_look(ctx)
    if keys or (hits and only_address != "address"):
        ctx.state.pop("last_sent", None)
    return {"addresses": sorted(set(addresses)), "texts": sorted(set(texts))}


@_locked
def forget_question(ctx, about):  # M19
    """What she must ask before this forget, or None: {"which": names} when it could be several people, {"field": name}
    for a bare "address" with both filled, or {"person": name, "relationship": word} for the whole person."""
    if _everything(about):
        return None
    hits, only_address, _ = _forget_hits(ctx, about, False)
    people = [hit for hit in hits if "id" in hit]
    if _several(people):
        return {"which": sorted({hit["name"] for hit in people})}
    if not people or (only_address and only_address != FORGET_ASK):
        return None
    if only_address:
        return {"field": people[0]["name"]}
    return {"person": people[0]["name"], "relationship": people[0]["relationship"]}


@_locked
def forget_matches(ctx, about):
    """How many people a forget of about would touch: only the count, no names and no addresses."""
    if _everything(about):
        return 0
    hits, _, wanted = _forget_hits(ctx, about, False)
    return max(len(hits), 1 if _holding(ctx, hits, wanted, False) else 0)


def _gate_turn(ctx, action):
    """What she says and the page does for one step of the gate. Never an address, except the look back on the page."""
    state = ctx.send_state()
    short, held = _short_from(state["line"]), ctx.state.get("held") or {}
    if action == "count":
        ctx.state["send_view"] = {"kind": "counting", "name": short}
        ctx.effect("count", {"look": state["look"], "name": short, "kind": held.get("effect", {}).get("kind")})
        return _reply("Going to %s." % ("their email" if short == "them" else short + "'s email"), counting=True)
    if action == "stopped":
        ctx.state["send_view"] = {"kind": "look", "name": short}
        _show_look(ctx, held)
        return _reply("Stopped. It hasn't gone.", stopped=True)
    if action == "say_line":
        return _reply(state["line"])
    if action == "tap":
        ctx.effect("tap", {"look": state["look"]})
        return _reply("I didn't catch that. Say it again, or tap here.")
    return {}  # quiet: the count runs on


@_locked
def on_gate(ctx, action):
    """Core has already moved the gate. This only says so."""
    return _gate_turn(ctx, action)


@_locked
def plain_message(ctx, person, words, signature=""):
    person, signature = _said(person, NAME_MAX), _said(signature, NAME_MAX)
    words = clean(words if isinstance(words, str) else "").strip()
    if len(words) > WORDS_MAX:
        return _reply("That's a lot for one message. Can we shorten it?", too_long=True, saved=False)
    draft = _draft(ctx)
    same = bool(draft) and draft.get("kind") == "letter" and (not person or person.lower() == draft["person"].lower())
    if same:
        trial = dict(draft)
    else:
        trial = {"kind": "letter", "id": _new_id(person), "person": person, "rev": 0, "step": "letter"}
    words, signature = words or trial.get("words", ""), signature or trial.get("signature", "")
    trial.update(words=words, signature=signature)
    if not words:
        return _reply("What do you want to say?", saved=False)
    if not signature:
        _keep(ctx, trial)
        return _reply("How do you want to sign it?", saved=False, words_kept=True, need="signature")
    save_letter(ctx, trial)
    trial["rev"] += 1
    _file_away(ctx, trial)
    _keep(ctx, trial)
    ctx.effect("show_screen")
    _show(ctx, trial)
    return _reply("Here's how it reads.", saved=True, read_back=_reading(trial), next=SAY_NEXT)  # the line opens with G's words


def _month_number(month):
    text = clean(str(month)).strip().lower()
    if text.isdigit():
        return int(text) if 1 <= int(text) <= 12 else None
    found = [number for number, name in enumerate(MONTHS, 1) if len(text) >= 3 and name.startswith(text)]
    return found[0] if len(found) == 1 else None


def _next_date(month, day):
    today = _today()
    for year in range(today.year, today.year + 9):  # far enough for the next 29 February
        try:
            date = datetime.date(year, month, day)
        except ValueError:
            continue
        if date >= today:
            return date
    return None


@_locked
def show_keepsake(ctx, name, month, day, age_line="", memory_line="", who=""):
    name = _said(name, NAME_MAX)
    number = _month_number(month)
    date = _next_date(number, day) if number else None
    if date is None:
        return _reply("I don't have that date right.", shown=False)
    if who not in ("mary", "sam"):
        who = "sam" if ctx.settings_get("companion") == "him" else "mary"
    file = "keepsake-%s-%02d%02d.svg" % (_slug(name, 30) or "date", date.month, date.day)
    weekday = date.strftime("%A")
    ctx.files.write_text(file, draw_keepsake(ctx, who, name, weekday, date.day, date.strftime("%B"),
                                             _said(age_line, AGE_MAX), _said(memory_line, MEMORY_MAX)))
    ctx.state["keepsake"] = {"file": file, "name": name, "when": _when(date)}
    ctx.effect("show_screen")
    ctx.effect("keepsake", {"file": file})
    return _reply("It's up.", shown=True, weekday=weekday, date=_when(date))


@_locked
def open_saved(ctx, person=""):
    wanted = _said(person, NAME_MAX).lower()
    index = ctx.store.get("index", [])
    for entry in reversed(index):
        held = entry["person"].lower()
        if wanted and not (held and (wanted in held or held in wanted)):
            continue
        record = ctx.store.get("saved-" + entry["id"])
        if record:
            _keep(ctx, record)
            ctx.effect("show_screen")
            _show(ctx, record)
            return _reply("Here it is.", found=True, kind=record["kind"], person=record.get("person", ""),
                          read_back=_reading(record))
    return _reply("I don't have one saved for %s." % _said(person, NAME_MAX) if wanted else "There's nothing saved yet.",
                  found=False)


@_locked
def close(ctx):
    """Puts the card away. It stays saved. Anything held for a send goes with it."""
    _drop_send(ctx)
    for key in ("just_sent", "address_wait", "address_told", "last_sent"):  # M18: address_told
        ctx.state.pop(key, None)
    ctx.effect("leave_screen")
    return _reply("All put away. It stays saved.")


def _picture(ctx, event):
    """One piece of a jpeg of the saved card, for sending later. Anything out of step is dropped; the svg stays."""
    draft, part, seq = _draft(ctx), event.get("part"), event.get("seq")
    key = [event.get("id"), part, event.get("rev")]
    if not _is_card(draft) or part not in PICTURE_PARTS or key[0] != draft["id"] or key[2] != draft.get("rev"):
        return {"ignored": True, "stale": True}
    if seq == 0:
        ctx.state["picture"] = {"key": key, "next": 0, "data": bytearray()}
    job = ctx.state.get("picture")
    if not job or job["key"] != key or job["next"] != seq:
        return {"ignored": True, "stale": True}
    try:
        job["data"] += base64.b64decode(event.get("data"), validate=True)
    except (TypeError, ValueError):
        ctx.state.pop("picture", None)
        return {"ignored": True, "stale": True}
    job["next"] += 1
    if len(job["data"]) > PICTURE_MAX:
        ctx.state.pop("picture", None)
        return {"ignored": True, "stale": True}
    if not event.get("last"):
        return {"ok": True}
    ctx.state.pop("picture", None)
    if not job["data"].startswith(JPEG_MAGIC):
        return {"ignored": True, "stale": True}
    ctx.files.write_bytes("card-%s-%s.jpg" % (draft["id"], part), bytes(job["data"]))
    if part != "mail":
        return {"ok": True, "saved": True}
    trial = dict(draft, mail_rev=draft.get("rev"))
    wanted = trial.pop("look_wanted", False)
    _keep(ctx, trial)
    return dict(_send_flow(ctx), ok=True, saved=True) if wanted else {"ok": True, "saved": True}


def _when_sent(moment):
    """As on board F: "Today at 2:14", then "in the afternoon"."""
    part = "in the morning" if moment.hour < 12 else "in the afternoon" if moment.hour < 17 else \
        "in the evening" if moment.hour < 21 else "at night"
    return "Today at %d:%02d" % (moment.hour % 12 or 12, moment.minute), part


def _sent(ctx, held):
    """It went. A new address goes in the book and she says so, and "don't keep it" takes it back. Only no_keep stops it."""
    short, person, address = held["short"], held["person"], held.get("address")
    time, part = _when_sent(datetime.datetime.now())
    ctx.state.pop("address_wait", None)
    ctx.state.pop("just_sent", None)  # "don't keep it" only ever means the latest send
    ctx.state["last_sent"] = {"name": short, "time": time, "part": part, "date": _today().isoformat()}
    ctx.effect("sent", {"name": short, "time": time, "part": part})
    has_email = any(hit["has_email"] for hit in ctx.people.find(person))
    if address and not has_email and not ctx.people.marks(person)["no_keep"]:
        if ctx.people.keep(person, dict(_said_relation(person), email=address, asked=True)):
            ctx.state["just_sent"] = {"person": person, "address": address}
            return _reply(_then_print(ctx, "Sent to %s. It's in your book now." % short), kept=True, sent=True)
    return _reply(_then_print(ctx, "Sent to %s." % short), sent=True)


def _not_sent(ctx, held, result):
    draft = _draft(ctx)
    if draft:
        _show(ctx, draft)
    if result.get("code") == "unsure":  # never retried: nobody can know it didn't go
        return _reply("I'm not sure that went. Ask %s if it came before we send it again." % held["short"],
                      sent=False, unsure=True)
    return _reply(_then_print(ctx, str(result.get("message") or "That didn't go.")), sent=False,
                  can_print=ctx.has_printer())


def _stale(ctx, held):
    """The gate said no at the end of the count: back to the look if there is one, else the card."""
    if held and ctx.send_state()["state"] == "look":
        ctx.state["send_view"] = {"kind": "look", "name": held["short"]}
        _show_look(ctx, held)
    else:
        _no_look(ctx)
        draft = _draft(ctx)
        if draft:
            _show(ctx, draft)
    return {"stale": True}


def _count_done(ctx, event):
    """The end of the count. A send can take 12 s, so _LOCK is let go around it and a tap never waits on it."""
    look = event.get("look")
    with _LOCK:
        held = ctx.state.get("held")
        if not held or held["look"] != look:
            return _stale(ctx, held)
    result = ctx.send_now(look)
    with _LOCK:
        if result is None:
            return _stale(ctx, held)
        _no_look(ctx)
        return _sent(ctx, held) if result.get("ok") else _not_sent(ctx, held, result)


def _typed_address(ctx, event):
    """An address a helper typed. It never goes near Gemini, so nothing about it is in a say or a result."""
    name = (_draft(ctx) or {}).get("person", "")
    if not name:
        return _reply(SAY_WHO, need_person=True)
    typed = _spoken_address(event.get("address"))
    if typed is None:
        return _ask_address(ctx, name, bad=True)
    ctx.state["address_wait"] = {"person": name, "address": typed, "right": True}
    ctx.state.pop("send_view", None)
    return _send_flow(ctx)


def on_resident_line(ctx, over=False):  # M18
    """One more line from them, or the talk's end. An address still waiting on a yes or a keep answer is let go, so it
    never sits in memory past the question. One they've checked for a send stays with that send."""
    with _LOCK:
        for key in ("address_wait", "address_told"):
            wait = ctx.state.get(key)
            if not wait or wait.get("right"):
                continue
            wait["lines"] = wait.get("lines", 0) + 1
            if over or wait["lines"] >= ADDRESS_LINES:
                ctx.state.pop(key, None)
                if (ctx.state.get("send_view") or {}).get("kind") == "address_wait":
                    ctx.state.pop("send_view", None)


def on_event(ctx, event):
    if event.get("type") == "count_done":
        return _count_done(ctx, event)
    with _LOCK:
        return _page_event(ctx, event)


def _page_event(ctx, event):
    kind = event.get("type")
    if kind == "open":  # from the menu, or after a restart
        keepsake, draft = ctx.state.get("keepsake"), _draft(ctx)
        if keepsake:
            ctx.effect("keepsake", {"file": keepsake["file"]})
        elif draft:
            _show(ctx, draft)
        else:
            show_fronts(ctx)
        return {"ok": True}
    if kind == "pick":
        draft = _draft(ctx)
        if _is_card(draft) and event.get("key") in draft.get("shown", []):
            return pick_front(ctx, event["key"])  # its say comes back, so a tap gets her line as a spoken pick does
        return {"ignored": True}
    if kind == "picture":
        return _picture(ctx, event)
    if kind == "print_failed":
        ctx.state["print_failed"] = True
        return _reply("The print didn't work.")
    if kind == "look_up":
        return {"ok": ctx.send_shown(event.get("look"))}
    if kind == "tap_send":
        return _gate_turn(ctx, "count") if ctx.send_tap() else {"ignored": True}
    if kind == "undo":
        return _gate_turn(ctx, "stopped") if ctx.send_undo() else {"ignored": True}
    if kind == "address":
        return _typed_address(ctx, event)
    if kind == "left":
        _drop_send(ctx)
        return {"ok": True}
    if kind == "picture_failed":
        _no_picture_wanted(ctx)
        return _reply(_no_picture(ctx), picture_failed=True)
    return {"ignored": True}


def _send_seen(state):
    """Where a send has got to, in plain words and with no address, so she knows what's on screen."""
    seen, sent = state.get("send_view") or {}, state.get("last_sent")
    name = seen.get("name", "")
    if seen.get("kind") == "counting":
        return "The five-second count is running for %s. Stay silent. " % name
    if seen.get("kind") == "look":
        return "The last look is up for %s, waiting for them to say send. " % name
    if seen.get("kind") == "need_address":
        return "Waiting for %s email address. " % _whose(name)
    if seen.get("kind") == "address_wait":
        return "Checking the address for %s with them. " % name
    if state.get("address_told"):  # M18
        return "Waiting to hear whether to keep %s address. " % _whose(state["address_told"]["person"])
    if sent and sent["date"] == _today().isoformat():
        ask = "The address is in their book now. If they say not to keep it, use keep_address. " if state.get("just_sent") else ""
        return "Sent to %s, %s %s. %s" % (sent["name"], sent["time"].lower(), sent["part"], ask)
    return ""


def view(state):
    """What Mary sees: the step, the person and the words so far, so she never has to describe the screen."""
    failed = ("The print didn't work. " if state.get("print_failed") else "") + _send_seen(state)
    keepsake = state.get("keepsake")
    if keepsake:
        return (failed + "A keepsake page for %s, %s." % (keepsake["name"], keepsake["when"]))[:590]
    draft = state.get("draft")
    if not draft:
        return failed + "No card up."
    person = draft.get("person") or "someone not named yet"
    words = (draft.get("words") or "")[:300]
    if draft.get("kind") == "letter":
        text = "A plain message to %s. Words so far: %s" % (person, words or "none")
    elif draft.get("step") == "fronts":
        text = "Fronts up for %s, not picked yet." % person
    elif draft.get("step") == "closed":
        text = "The %s card for %s is up, no words yet. Ask what they want to say." % (draft.get("front"), person)
    else:
        text = "The %s card for %s is open, in %s. Words so far: %s" % (draft.get("front"), person, draft.get("hand"), words)
    return (failed + text)[:590]
