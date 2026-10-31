#!/usr/bin/env python3
"""Writes skills/messages/assets/metrics.json: how wide each letter is in the card fonts (M15b).

The messages skill has to fit a resident's words on the card on the server, and the app has no font library, so the
widths are read once from the .ttf copies here and kept as JSON. Stdlib only. Not bundled and not run by the app.
Run it only if a card font changes: python tools/card_font_metrics.py <folder of .ttf files, named as in FONTS below>.
Google Fonts serves .ttf when asked with no browser name; only the .woff2 files are kept in web/mary/fonts/."""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "skills" / "messages" / "assets" / "metrics.json"
FONTS = ("pinyon", "cinzel-500", "cinzel-700", "garamond-400", "garamond-500", "garamond-700", "garamond-italic",
         "cedarville", "kalam")
# Latin, Latin Extended A and B, and the curly quotes, dashes and ellipsis that speech-to-text and Gemini write.
CODES = list(range(0x20, 0x7F)) + list(range(0xA0, 0x250)) + [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026]


def tables(data):
    count = struct.unpack(">H", data[4:6])[0]
    out = {}
    for i in range(count):
        tag, _, offset, length = struct.unpack(">4sIII", data[12 + i * 16:28 + i * 16])
        out[tag.decode("latin-1")] = data[offset:offset + length]
    return out


def char_map(cmap):
    """Code point to glyph, from the format 12 or format 4 Unicode subtable."""
    best = None
    for i in range(struct.unpack(">H", cmap[2:4])[0]):
        platform, encoding, offset = struct.unpack(">HHI", cmap[4 + i * 8:12 + i * 8])
        fmt = struct.unpack(">H", cmap[offset:offset + 2])[0]
        if fmt == 12 or (fmt == 4 and best is None) and (platform, encoding) in ((3, 1), (0, 3), (0, 4)):
            best = (fmt, offset)
    fmt, base = best
    found = {}
    if fmt == 12:
        for i in range(struct.unpack(">I", cmap[base + 12:base + 16])[0]):
            start, end, glyph = struct.unpack(">III", cmap[base + 16 + i * 12:base + 28 + i * 12])
            for code in range(start, end + 1):
                found[code] = glyph + code - start
        return found
    segments = struct.unpack(">H", cmap[base + 6:base + 8])[0] // 2
    words = lambda at: struct.unpack(f">{segments}H", cmap[at:at + segments * 2])
    ends, starts = words(base + 14), words(base + 16 + segments * 2)
    deltas, range_at = words(base + 16 + segments * 4), base + 16 + segments * 6
    ranges = words(range_at)
    for i in range(segments):
        for code in range(starts[i], ends[i] + 1):
            if code == 0xFFFF:
                continue
            if ranges[i] == 0:
                glyph = (code + deltas[i]) & 0xFFFF
            else:
                at = range_at + i * 2 + ranges[i] + (code - starts[i]) * 2
                glyph = struct.unpack(">H", cmap[at:at + 2])[0]
                glyph = (glyph + deltas[i]) & 0xFFFF if glyph else 0
            if glyph:
                found[code] = glyph
    return found


def font_metrics(path):
    t = tables(path.read_bytes())
    upm = struct.unpack(">H", t["head"][18:20])[0]
    ascent, descent = struct.unpack(">hh", t["hhea"][4:8])
    long_metrics = struct.unpack(">H", t["hhea"][34:36])[0]
    advance = lambda glyph: struct.unpack(">H", t["hmtx"][min(glyph, long_metrics - 1) * 4:][:2])[0]
    glyphs = char_map(t["cmap"])
    widths = {chr(c): round(advance(glyphs[c]) / upm, 4) for c in CODES if c in glyphs}
    return {"ascent": round(ascent / upm, 4), "descent": round(-descent / upm, 4),
            "average": round(sum(widths.values()) / len(widths), 4), "widths": widths}


def main():
    folder = Path(sys.argv[1])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {name: font_metrics(folder / f"{name}.ttf") for name in FONTS}
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
