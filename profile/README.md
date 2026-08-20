# How the card is built

The profile README is a single `<picture>` pointing at `dark_mode.svg` / `light_mode.svg` in
the repo root. Both are generated — never hand-edit them.

```
photo.jpg --img2ascii.py--> portrait.txt --build.py--> dark_mode.svg + light_mode.svg
                            GitHub GraphQL ---^
```

## Edit the card text

Everything a human changes lives in `card()` at the top of `build.py` (and `BIRTHDAY` /
`THEMES` just above it). Row kinds: `head`, `rule`, `kv`, `kv2`, `raw`, `blank`.

## Swap the photo

The source headshot is deliberately **not** committed — only the generated `portrait.txt`
is. Drop yours at `profile/photo.jpg` (gitignored) and run:

```bash
python profile/img2ascii.py profile/photo.jpg --crop 260,10,880,880
```

`--crop x,y,w,h` is in source pixels and runs before anything else — use it to frame the
close-up. The knobs that matter, in the order worth trying:

| flag | does |
|------|------|
| `--low` | edges weaker than this are blank. Raise it to clean up background speckle |
| `--high` | edges stronger than this get a full line glyph. Lower it for a bolder face |
| `--blur` | pre-blur. Raise it when skin texture or JPEG noise turns into edges |
| `--weak` | glyph for in-between edges; `--weak ''` gives pure outline |
| `--width` / `--lines` | grid size; must stay in step with `ART_*` in `build.py` |

It draws outlines rather than shaded density on purpose: density reads as darkness on the
light card and as glow on the dark one, so one shaded grid can't be right on both.

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
