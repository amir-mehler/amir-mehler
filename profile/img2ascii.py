#!/usr/bin/env python3
"""
Turn a photo into the ASCII portrait used by the profile card.

    python profile/img2ascii.py profile/photo.jpg --crop 260,10,880,880

Writes profile/portrait.txt (which build.py renders into both SVGs) and prints a
preview.

It draws *lines*, not shading: per glyph cell, the dominant edge direction
becomes one of - / | \\ , and cells with no edge stay blank. Density-based ASCII
art can't work here -- glyph density reads as darkness on the light card and as
glow on the dark one, so the same grid would look like a face on one and a
hollow mask on the other. An outline reads the same on both.

Flat studio lighting also gives a density ramp almost nothing to work with,
while edges survive it.
"""
import argparse
import math
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageOps

# The portrait is drawn at font-size 11 with a matching 11px line-height, so a
# glyph cell is ~6.6 x 11 px. Keep in step with ART_* in build.py.
CHAR_ASPECT = 6.6 / 11

SOBEL_X = ImageFilter.Kernel((3, 3), [-1, 0, 1, -2, 0, 2, -1, 0, 1], scale=1, offset=128)
SOBEL_Y = ImageFilter.Kernel((3, 3), [-1, -2, -1, 0, 0, 0, 1, 2, 1], scale=1, offset=128)


def crop_rect(img, spec):
    """Explicit crop in source pixels: "x,y,w,h"."""
    x, y, w, h = (int(v) for v in spec.split(","))
    return img.crop((x, y, x + w, y + h))


def crop_to_grid(img, width, lines, focus):
    """Center-crop so the image aspect matches a `width` x `lines` glyph grid.

    `focus` (0=top, 1=bottom) biases the vertical crop -- faces sit high, so the
    default keeps the head and drops the chest.
    """
    target = width / (lines / CHAR_ASPECT)
    w, h = img.size
    if w / h > target:  # too wide -> trim the sides
        new_w = round(h * target)
        left = (w - new_w) // 2
        return img.crop((left, 0, left + new_w, h))
    new_h = round(w / target)  # too tall -> trim top/bottom
    top = round((h - new_h) * focus)
    return img.crop((0, top, w, top + new_h))


def structure(gray, width, lines):
    """Per cell: (edge magnitude, dominant gradient angle).

    Averaging the structure tensor rather than the raw gradients matters: a brow
    is dark-above-light on one side and the reverse on the other, so signed
    gradients cancel and the feature disappears.
    """
    w, h = gray.size

    def sobel(kernel):
        out = gray.filter(kernel)
        # PIL leaves the 1px frame unfiltered, which reads as one huge fake edge.
        ImageDraw.Draw(out).rectangle([0, 0, w - 1, h - 1], outline=128, width=1)
        return out.load()

    gx, gy = sobel(SOBEL_X), sobel(SOBEL_Y)
    cells = []
    for cy in range(lines):
        y0, y1 = h * cy // lines, h * (cy + 1) // lines
        row = []
        for cx in range(width):
            x0, x1 = w * cx // width, w * (cx + 1) // width
            sxx = syy = sxy = 0.0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    dx, dy = gx[x, y] - 128, gy[x, y] - 128
                    sxx += dx * dx
                    syy += dy * dy
                    sxy += dx * dy
            n = max(1, (y1 - y0) * (x1 - x0))
            sxx, syy, sxy = sxx / n, syy / n, sxy / n
            row.append((math.sqrt(sxx + syy), 0.5 * math.atan2(2 * sxy, sxx - syy)))
        cells.append(row)
    return cells


def glyph(angle):
    """The line the edge runs along -- perpendicular to the gradient."""
    edge = (math.degrees(angle) + 90) % 180
    if edge < 22.5 or edge >= 157.5:
        return "-"
    if edge < 67.5:
        return "\\"  # screen y grows downward, so this is the "up-left" diagonal
    if edge < 112.5:
        return "|"
    return "/"


def to_ascii(path, width, lines, crop, focus, low, high, blur, weak):
    img = Image.open(path).convert("L")
    if crop:
        img = crop_rect(img, crop)
    img = crop_to_grid(img, width, lines, focus)
    img = ImageOps.autocontrast(img, cutoff=1)
    if blur:
        # Skin texture and JPEG noise are edges too; blur past them.
        img = img.filter(ImageFilter.GaussianBlur(blur))

    rows = []
    for row in structure(img, width, lines):
        out = []
        for mag, angle in row:
            if mag < low:
                out.append(" ")
            elif mag < high:
                out.append(weak or " ")
            else:
                out.append(glyph(angle))
        rows.append("".join(out).rstrip())
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image")
    ap.add_argument("--width", type=int, default=76, help="portrait width in characters")
    ap.add_argument("--lines", type=int, default=47, help="portrait height in lines")
    ap.add_argument("--crop", help='explicit source crop "x,y,w,h", applied before anything else')
    ap.add_argument("--focus", type=float, default=0.05, help="vertical crop bias, 0=top 1=bottom")
    ap.add_argument("--low", type=float, default=22.0, help="edges weaker than this are blank")
    ap.add_argument("--high", type=float, default=30.0, help="edges stronger than this get a line")
    ap.add_argument("--blur", type=float, default=3.0, help="pre-blur; raise it to drop skin texture")
    ap.add_argument("--weak", default=".", help="glyph for in-between edges; empty for none")
    ap.add_argument("--out", default="profile/portrait.txt")
    args = ap.parse_args()

    rows = to_ascii(args.image, args.width, args.lines, args.crop, args.focus,
                    args.low, args.high, args.blur, args.weak)
    with open(args.out, "w") as f:
        f.write("\n".join(rows) + "\n")
    print("\n".join(rows))
    print(f"\n-> {args.out} ({len(rows)} lines x {args.width} cols)", file=sys.stderr)


if __name__ == "__main__":
    main()
