#!/usr/bin/env python3
"""
Render dark_mode.svg / light_mode.svg -- the neofetch-style card shown on
github.com/amir-mehler.

    ACCESS_TOKEN=$(gh auth token) python profile/build.py

Everything a human edits lives in the CARD section below. Stats come from the
GitHub GraphQL API; per-repo line counts are cached in cache/loc.json so only
repos with new commits are re-walked.
"""
import datetime
import json
import os
import sys
from xml.sax.saxutils import escape

import requests

USER = os.environ.get("USER_NAME", "amir-mehler")
TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
API = "https://api.github.com/graphql"

# Repos owned by USER count toward stars/LOC. The wider set (org + collab) only
# ever contributes a repo *count* -- no private work code is read or reported.
OWNED = ["OWNER"]
ALL_AFFILIATIONS = ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"]

# Date the "Uptime" row counts from: the start of the career, not the GitHub join
# date. None falls back to the join date.
BIRTHDAY = datetime.date(2006, 1, 1)

# ---------------------------------------------------------------- layout ----
PAD, GAP, CW, LH, FONT_SIZE = 15, 20, 9.6, 20, 16
RIGHT_COLS = 64  # width of the info column, in characters

# The portrait gets its own, smaller type: same area, ~3x the glyph cells, which
# is the difference between a legible face and a smudge. 0.6 * size is the
# advance width of the mono fallbacks (DejaVu, Liberation, Menlo). 12px gives a
# 7.2 x 12 cell, which is the cell the art was authored at -- shrink it and
# neighbouring shades of the ramp stop being distinguishable. It also happens to
# make 55 rows of art exactly as tall as the info column.
ART_FONT_SIZE, ART_LH = 12, 12
ART_CW = ART_FONT_SIZE * 0.6

THEMES = {
    "dark_mode.svg": {
        # Glyph density reads as glow on a dark background, so the dark card gets
        # the inverted portrait -- see profile/README.md.
        "portrait": "profile/portrait_dark.txt",
        "bg": "#161b22", "fg": "#c9d1d9", "key": "#ffa657", "value": "#a5d6ff",
        "dots": "#4d5866", "add": "#3fb950", "del": "#f85149", "rule": "#8b949e",
    },
    "light_mode.svg": {
        "portrait": "profile/portrait.txt",
        "bg": "#ffffff", "fg": "#24292f", "key": "#953800", "value": "#0550ae",
        "dots": "#afb8c1", "add": "#1a7f37", "del": "#cf222e", "rule": "#57606a",
    },
}


def card(stats):
    """The content of the right-hand column, top to bottom.

    ('head', text)          -> "amir@mehler ------------------------------"
    ('rule', text)          -> "- Section ---------------------------------"
    ('kv', key, value)      -> ". Key: ............................. value"
    ('kv2', k, v, k, v)     -> two dotted pairs sharing one line
    ('raw', [(cls, text)])  -> escape hatch (used for the ++/-- line)
    ('blank',)
    """
    return [
        ("head", "amir@mehler.co.il"),
        ("kv", "OS", "macOS · Linux · Kubernetes"),
        ("kv", "Uptime", stats["uptime"]),
        ("kv", "Host", "PhaseV — Head of DevOps"),
        ("kv", "Experience", "+15 years as SRE / DevOps manager"),
        ("kv", "Shell", "zsh + Claude Code"),
        ("kv", "Editor", "VIM · Cursor · Claude"),
        ("blank",),
        ("rule", "Stack"),
        ("kv", "Infra as Code", "Terraform · Helm · ArgoCD"),
        ("kv", "Cloud", "AWS · GCP · Azure"),
        ("kv", "Observability", "FTW"),
        ("blank",),
        ("rule", "Languages"),
        ("kv", "Code", "Bash · Go · Python · JS"),
        ("kv", "Human", "Hebrew · English"),
        ("blank",),
        ("rule", "Music"),
        ("kv", "Rock", "Classic · Psychedelic · Progressive · Grunge · Metal"),
        ("kv", "Roots", "Blues · Jazz · Funk"),
        ("kv", "Beats", "Hip-Hop · Electronic · DJs"),
        ("kv", "Heroes", "Hendrix · Zeppelin · Beatles · Bowie · Dylan"),
        ("blank",),
        ("rule", "Contact"),
        ("kv", "LinkedIn", "linkedin.com/in/amirmehler"),
        ("kv", "Location", "Tel Aviv, Israel"),
        ("blank",),
        ("rule", "GitHub Stats"),
        ("kv2", "Repos", stats["repos"], "Stars", stats["stars"]),
        ("kv2", "Commits", stats["commits"], "Followers", stats["followers"]),
        ("kv2", "Contributed to", stats["contributed"], "Last 12mo", stats["contributions"]),
        (
            "raw",
            [
                ("dots", ". "), ("key", "Lines of Code"), (None, ":"),
                ("dots", "DOTS"), ("value", stats["loc"]),
                (None, " ( "), ("add", stats["loc_add"] + "++"),
                (None, ", "), ("del", stats["loc_del"] + "--"), (None, " )"),
            ],
        ),
    ]


# ------------------------------------------------------------------ api -----
def gql(query, **variables):
    if not TOKEN:
        sys.exit("set ACCESS_TOKEN (e.g. ACCESS_TOKEN=$(gh auth token))")
    r = requests.post(
        API,
        json={"query": query, "variables": variables},
        headers={"Authorization": f"bearer {TOKEN}"},
        timeout=60,
    )
    if r.status_code != 200:
        sys.exit(f"GitHub API {r.status_code}: {r.text[:400]}")
    body = r.json()
    if "errors" in body:
        sys.exit(f"GitHub API errors: {json.dumps(body['errors'])[:400]}")
    return body["data"]


def account():
    data = gql(
        """query($login: String!) {
            user(login: $login) { id createdAt followers { totalCount } }
        }""",
        login=USER,
    )["user"]
    return data["id"], data["createdAt"], data["followers"]["totalCount"]


def contributions(days=365):
    """Contributions in the last `days`.

    With a token that can see them, this includes private work -- which is where
    most of the commits actually are.
    """
    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - datetime.timedelta(days=days)
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    return gql(
        """query($login: String!, $from: DateTime!, $to: DateTime!) {
            user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                    contributionCalendar { totalContributions }
                }
            }
        }""",
        login=USER,
        **{"from": start.strftime(stamp), "to": end.strftime(stamp)},
    )["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]


def repo_count(affiliations):
    return gql(
        """query($login: String!, $aff: [RepositoryAffiliation]) {
            user(login: $login) { repositories(ownerAffiliations: $aff) { totalCount } }
        }""",
        login=USER,
        aff=affiliations,
    )["user"]["repositories"]["totalCount"]


def owned_repos():
    """Every non-fork repo USER owns, with its stars and commit count."""
    query = """query($login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 50, after: $cursor, ownerAffiliations: [OWNER], isFork: false) {
                nodes {
                    nameWithOwner
                    isEmpty
                    stargazerCount
                    defaultBranchRef { target { ... on Commit { history { totalCount } } } }
                }
                pageInfo { endCursor hasNextPage }
            }
        }
    }"""
    nodes, cursor = [], None
    while True:
        page = gql(query, login=USER, cursor=cursor)["user"]["repositories"]
        nodes += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return nodes
        cursor = page["pageInfo"]["endCursor"]


def walk_commits(owner, name, user_id, max_pages=60):
    """Sum additions/deletions over commits authored by USER on the default branch."""
    query = """query($owner: String!, $name: String!, $cursor: String) {
        repository(owner: $owner, name: $name) {
            defaultBranchRef { target { ... on Commit {
                history(first: 100, after: $cursor) {
                    nodes { additions deletions author { user { id } } }
                    pageInfo { endCursor hasNextPage }
                }
            } } }
        }
    }"""
    mine = add = dele = 0
    cursor = None
    for _ in range(max_pages):
        ref = gql(query, owner=owner, name=name, cursor=cursor)["repository"]["defaultBranchRef"]
        if not ref:
            break
        history = ref["target"]["history"]
        for node in history["nodes"]:
            if (node["author"].get("user") or {}).get("id") == user_id:
                mine += 1
                add += node["additions"]
                dele += node["deletions"]
        if not history["pageInfo"]["hasNextPage"]:
            break
        cursor = history["pageInfo"]["endCursor"]
    return mine, add, dele


def loc_and_commits(repos, user_id, cache_path="cache/loc.json"):
    """Per-repo commit/LOC totals, re-walking only repos whose history grew."""
    try:
        with open(cache_path) as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}

    fresh = {}
    for repo in repos:
        if repo["isEmpty"] or not repo["defaultBranchRef"]:
            continue
        key = repo["nameWithOwner"]
        total = repo["defaultBranchRef"]["target"]["history"]["totalCount"]
        hit = cache.get(key)
        if hit and hit["total"] == total:
            fresh[key] = hit
            continue
        owner, name = key.split("/")
        mine, add, dele = walk_commits(owner, name, user_id)
        print(f"   walked {key}: {mine} commits, +{add}/-{dele}")
        fresh[key] = {"total": total, "mine": mine, "add": add, "del": dele}

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(fresh, f, indent=1, sort_keys=True)
    return (
        sum(v["mine"] for v in fresh.values()),
        sum(v["add"] for v in fresh.values()),
        sum(v["del"] for v in fresh.values()),
    )



def uptime(since):
    """'X years, Y months, Z days' -- no dateutil, so no extra dependency."""
    now = datetime.date.today()
    years = now.year - since.year
    months = now.month - since.month
    days = now.day - since.day
    if days < 0:
        months -= 1
        prev = (now.replace(day=1) - datetime.timedelta(days=1)).day
        days += prev
    if months < 0:
        years -= 1
        months += 12
    plural = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"
    cake = " 🎂" if (months, days) == (0, 0) else ""
    return f"{plural(years, 'year')}, {plural(months, 'month')}, {plural(days, 'day')}{cake}"


# --------------------------------------------------------------- render -----
def dots(n):
    """A dotted leader that keeps one space of air on each side."""
    if n <= 0:
        return ""
    if n == 1:
        return " "
    if n == 2:
        return ". "
    return " " + "." * (n - 2) + " "


def segments(row):
    """Expand one card row into [(css_class, text)], padded to RIGHT_COLS."""
    kind = row[0]
    if kind == "blank":
        return []
    if kind in ("head", "rule"):
        label = row[1] if kind == "head" else f"- {row[1]} "
        cls = "hd" if kind == "head" else "key"
        fill = max(0, RIGHT_COLS - len(label) - 1)
        return [(cls, label), ("rule", "-" + "—" * fill)]
    if kind == "raw":
        parts = list(row[1])
        used = sum(len(t) for _, t in parts if t != "DOTS")
        return [(c, dots(RIGHT_COLS - used) if t == "DOTS" else t) for c, t in parts]
    if kind == "kv":
        head = f". {row[1]}:"
        value = str(row[2])
        return [
            ("dots", ". "), ("key", row[1]), (None, ":"),
            ("dots", dots(RIGHT_COLS - len(head) - len(value))), ("value", value),
        ]
    if kind == "kv2":
        # Two pairs on one line: the first is padded to the halfway mark.
        half = RIGHT_COLS // 2 - 2
        head1, v1 = f". {row[1]}:", str(row[2])
        head2, v2 = f"{row[3]}:", str(row[4])
        return [
            ("dots", ". "), ("key", row[1]), (None, ":"),
            ("dots", dots(half - len(head1) - len(v1))), ("value", v1),
            (None, " | "), ("key", row[3]), (None, ":"),
            ("dots", dots(RIGHT_COLS - half - 3 - len(head2) - len(v2))), ("value", v2),
        ]
    raise ValueError(f"unknown row kind: {kind}")


def render(theme_file, portrait, rows):
    theme = THEMES[theme_file]
    art_cols = max((len(line) for line in portrait), default=0)
    x_info = PAD + round(art_cols * ART_CW) + GAP
    width = x_info + round(RIGHT_COLS * CW) + PAD
    height = PAD * 2 + max(len(portrait) * ART_LH, len(rows) * LH)

    out = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,monospace"'
        f' width="{width}px" height="{height}px" font-size="{FONT_SIZE}px">',
        "<style>",
        "@font-face { src: local('Consolas'); font-family: 'ConsolasFallback';"
        " font-display: swap; size-adjust: 109%; }",
        f".key {{fill: {theme['key']};}} .value {{fill: {theme['value']};}}",
        f".dots {{fill: {theme['dots']};}} .rule {{fill: {theme['rule']};}}",
        f".hd {{fill: {theme['value']}; font-weight: bold;}}",
        f".add {{fill: {theme['add']};}} .del {{fill: {theme['del']};}}",
        "text, tspan {white-space: pre;}",
        "</style>",
        f'<rect width="{width}px" height="{height}px" fill="{theme["bg"]}" rx="15"/>',
        # xml:space, as well as the CSS above: browsers honour white-space:pre,
        # but librsvg (handy for local previews) only honours xml:space.
        f'<text x="{PAD}" y="{PAD + ART_LH}" fill="{theme["fg"]}" xml:space="preserve"'
        f' font-size="{ART_FONT_SIZE}px">',
    ]
    for i, line in enumerate(portrait):
        out.append(f'<tspan x="{PAD}" y="{PAD + (i + 1) * ART_LH}">{escape(line)}</tspan>')
    out.append("</text>")
    out.append(f'<text x="{x_info}" y="{PAD + LH}" fill="{theme["fg"]}" xml:space="preserve">')
    for i, row in enumerate(rows):
        y = PAD + (i + 1) * LH
        body = "".join(
            escape(text) if cls is None else f'<tspan class="{cls}">{escape(text)}</tspan>'
            for cls, text in segments(row)
        )
        out.append(f'<tspan x="{x_info}" y="{y}">{body}</tspan>')
    out += ["</text>", "</svg>", ""]

    with open(theme_file, "w") as f:
        f.write("\n".join(out))
    print(f"   wrote {theme_file} ({width}x{height})")


def main():
    user_id, created_at, followers = account()
    repos = owned_repos()
    commits, loc_add, loc_del = loc_and_commits(repos, user_id)
    joined = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").date()
    comma = "{:,}".format

    stats = {
        "uptime": uptime(BIRTHDAY or joined) + ("" if BIRTHDAY else " (on GitHub)"),
        "repos": comma(repo_count(OWNED)),
        "stars": comma(sum(r["stargazerCount"] for r in repos)),
        "commits": comma(commits),
        "followers": comma(followers),
        "contributed": comma(repo_count(ALL_AFFILIATIONS)),
        "contributions": comma(contributions()),
        "loc": comma(loc_add - loc_del),
        "loc_add": comma(loc_add),
        "loc_del": comma(loc_del),
    }

    rows = card(stats)
    for theme_file, theme in THEMES.items():
        with open(theme["portrait"]) as f:
            render(theme_file, [line.rstrip("\n") for line in f], rows)


if __name__ == "__main__":
    main()
