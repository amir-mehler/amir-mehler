#!/usr/bin/env python3
"""
Turn a photo into the ASCII portrait used by the profile card.

    python profile/img2ascii.py profile/photo.jpg --crop 260,10,880,880

Writes profile/portrait.txt (which build.py renders into both SVGs) and prints a
preview.

Two modes, because the two kinds of source want different treatment:

  line     (default) per glyph cell, the dominant edge direction becomes one of
           - / | \\ and featureless cells stay blank. An outline reads the same
           on a dark and a light card, and survives flat studio lighting, which
           gives a density ramp almost nothing to work with.

  recover  the source is a *screenshot of ASCII art*: read the glyphs back out of
           it by matching every cell of its character grid against rendered
           templates. Faithful to the original art, where re-deriving tone from
           the screenshot only smears it. Density reads as darkness on the light
           card and as glow on the dark one, so this mode needs a second
           --invert pass to produce the dark variant.
"""
import argparse
import math
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

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


# sparse -> dense. The ramp the generators that produced the source art use, and
# the alphabet --mode recover is allowed to answer with.
RAMP = " .:-=+*#%@"
FONT = "/System/Library/Fonts/Menlo.ttc"


def recover(path, width, lines, font_path, invert):
    """Read the glyphs back out of a screenshot of ASCII art.

    The screenshot's font, size and grid origin are unknown, so sweep them: score
    each candidate by how well the whole ramp explains a sample of cells, then
    decode every cell with the winner. Confusing two neighbours on the ramp costs
    one shade, so a near-miss on the font is harmless.
    """
    img = Image.open(path).convert("L")
    w, h = img.size
    cw, ch = w / width, h / lines
    tile = (int(round(cw)), int(round(ch)))

    def templates(size, dy):
        font = ImageFont.truetype(font_path, size)
        out = {}
        for ch_ in RAMP:
            im = Image.new("L", tile, 255)
            ImageDraw.Draw(im).text((0, dy), ch_, font=font, fill=0)
            out[ch_] = list(im.getdata())
        return out

    def cell(cx, cy, ox, oy):
        x0, y0 = int(round(cx * cw)) + ox, int(round(cy * ch)) + oy
        return list(img.crop((x0, y0, x0 + tile[0], y0 + tile[1])).getdata())

    def ssd(a, b):
        return sum((p - q) ** 2 for p, q in zip(a, b))

    sample = [(cx, cy) for cy in range(2, lines, 7) for cx in range(2, width, 9)]
    best = None
    for size in range(9, 17):
        for dy in range(-4, 3):
            tpl = templates(size, dy)
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    err = sum(min(ssd(cell(cx, cy, ox, oy), t) for t in tpl.values())
                              for cx, cy in sample)
                    if best is None or err < best[0]:
                        best = (err, size, dy, ox, oy)
    _, size, dy, ox, oy = best
    print(f"grid {width}x{lines}, cell {cw:.2f}x{ch:.2f}, "
          f"font size {size} dy {dy}, origin ({ox},{oy})", file=sys.stderr)

    tpl = templates(size, dy)
    flip = {a: b for a, b in zip(RAMP, reversed(RAMP))}
    rows = []
    for cy in range(lines):
        row = []
        for cx in range(width):
            c = cell(cx, cy, ox, oy)
            g = min(tpl, key=lambda ch_: ssd(c, tpl[ch_]))
            row.append(flip[g] if invert else g)
        rows.append("".join(row).rstrip() if not invert else "".join(row))
    return rows


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
    ap.add_argument("--mode", choices=("line", "recover"), default="line")
    ap.add_argument("--width", type=int, default=76, help="portrait width in characters")
    ap.add_argument("--lines", type=int, default=47, help="portrait height in lines")
    ap.add_argument("--invert", action="store_true",
                    help="recover mode: flip the ramp, for the dark card")
    ap.add_argument("--font", default=FONT, help="recover mode: font to match the art against")
    ap.add_argument("--crop", help='explicit source crop "x,y,w,h", applied before anything else')
    ap.add_argument("--focus", type=float, default=0.05, help="vertical crop bias, 0=top 1=bottom")
    ap.add_argument("--low", type=float, default=22.0, help="edges weaker than this are blank")
    ap.add_argument("--high", type=float, default=30.0, help="edges stronger than this get a line")
    ap.add_argument("--blur", type=float, default=3.0, help="pre-blur; raise it to drop skin texture")
    ap.add_argument("--weak", default=".", help="glyph for in-between edges; empty for none")
    ap.add_argument("--out", default="profile/portrait.txt")
    args = ap.parse_args()

    if args.mode == "recover":
        rows = recover(args.image, args.width, args.lines, args.font, args.invert)
    else:
        rows = to_ascii(args.image, args.width, args.lines, args.crop, args.focus,
                        args.low, args.high, args.blur, args.weak)
    with open(args.out, "w") as f:
        f.write("\n".join(rows) + "\n")
    print("\n".join(rows))
    print(f"\n-> {args.out} ({len(rows)} lines x {args.width} cols)", file=sys.stderr)


if __name__ == "__main__":
    main()
