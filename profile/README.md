# How the card is built

The profile README is a single `<picture>` pointing at `dark_mode.svg` / `light_mode.svg` in
the repo root. Both are generated — never hand-edit them.

```
source art --img2ascii.py--> portrait.txt      --build.py--> light_mode.svg
                             portrait_dark.txt --build.py--> dark_mode.svg
                             GitHub GraphQL ------^
```

Two portraits, not one, because glyph density reads as **darkness** on the light card and as
**glow** on the dark one — one shaded grid can't be right on both. Which file each theme
uses is the `portrait` key in `THEMES` in `build.py`.

## Edit the card text

Everything a human changes lives in `card()` at the top of `build.py` (and `BIRTHDAY` /
`THEMES` just above it). Row kinds: `head`, `rule`, `kv`, `kv2`, `raw`, `blank`.

## Swap the portrait

Sources are deliberately **not** committed — only the generated `portrait*.txt`.
`img2ascii.py` has a mode per kind of source.

**Already ASCII art** (a screenshot from one of the online converters — this is how the
current portrait was made). It reads the glyphs back out of the image by matching every cell
of its character grid against rendered templates, which is faithful where re-deriving tone
from the screenshot only smears it. Pass the art's real grid size:

```bash
python profile/img2ascii.py art.png --mode recover --width 112 --lines 55 \
    --out profile/portrait.txt
python profile/img2ascii.py art.png --mode recover --width 112 --lines 55 --invert \
    --out profile/portrait_dark.txt
```

`--invert` flips the ramp for the dark card. Grid size is countable off the image (its
width in pixels ÷ the cell width) and must stay in step with `ART_*` in `build.py` — leave
`ART_FONT_SIZE` at 11 so a card cell matches the ~7x12 cell the art was authored at;
smaller and neighbouring shades of the ramp stop being distinguishable.

**A photo.** Drop it at `profile/photo.jpg` (gitignored) and run the default `line` mode,
which turns the dominant edge direction in each cell into one of `- / | \`:

```bash
python profile/img2ascii.py profile/photo.jpg --crop 260,10,880,880
```

An outline reads the same on both cards, so `line` needs no inverted twin — point both
themes at the one file. `--crop x,y,w,h` is in source pixels and runs first; use it to frame
the close-up. Then, in the order worth trying:

| flag | does |
|------|------|
| `--low` | edges weaker than this are blank. Raise it to clean up background speckle |
| `--high` | edges stronger than this get a full line glyph. Lower it for a bolder face |
| `--blur` | pre-blur. Raise it when skin texture or JPEG noise turns into edges |
| `--weak` | glyph for in-between edges; `--weak ''` gives pure outline |
| `--width` / `--lines` | grid size; must stay in step with `ART_*` in `build.py` |

## Render locally

```bash
ACCESS_TOKEN=$(gh auth token) python profile/build.py
rsvg-convert -z 2 dark_mode.svg -o /tmp/card.png && open /tmp/card.png
```

## Auto-refresh

`.github/workflows/build.yaml` re-renders on push to `main` and daily at 04:17 UTC, and
commits the SVGs only if they changed. `cache/loc.json` keeps per-repo line counts so only
repos with new commits are re-walked.

Add a PAT with `read:user` + `repo` as the `ACCESS_TOKEN` secret so private contributions
count toward the "Last 12mo" row. Without it the workflow still passes on `GITHUB_TOKEN`,
but that token can't see restricted contributions and the number reads near zero.

Only repos you *own* are read for stars, commits and LOC. Org and collaborator repos
contribute a bare count and nothing else, so no private work code or per-repo work data
ends up on a public card.
