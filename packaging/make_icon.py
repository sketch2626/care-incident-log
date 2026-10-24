"""Draws packaging/icon.ico: a white clipboard with a check mark on the app's blue."""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024  # draw large, then let Pillow scale down to each icon size
ACCENT, WHITE = (28, 92, 171, 255), (255, 255, 255, 255)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((32, 32, S - 32, S - 32), radius=200, fill=ACCENT)
d.rounded_rectangle((250, 210, 774, 860), radius=70, fill=WHITE)            # board
d.rounded_rectangle((380, 150, 644, 280), radius=50, fill=ACCENT)           # clip outline
d.rounded_rectangle((410, 180, 614, 250), radius=30, fill=WHITE)
d.line([(370, 560), (480, 670), (670, 440)], fill=ACCENT, width=80, joint="curve")  # check
for x, y in ((370, 560), (480, 670), (670, 440)):
    d.ellipse((x - 40, y - 40, x + 40, y + 40), fill=ACCENT)

out = Path(__file__).with_name("icon.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"Wrote {out}")
