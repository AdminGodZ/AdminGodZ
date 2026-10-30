#!/usr/bin/env python3
"""Render an SVG card for every public repo you own and list them in README.md.

Each repo gets a dark and a light card under assets/projects/, shown through a
<picture> element so GitHub picks the one matching the visitor's theme.
"""
import html
import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import datetime

API = "https://api.github.com/graphql"
TOKEN = os.environ["GH_TOKEN"]
README = os.environ.get("README", "README.md")
CARDS_DIR = os.environ.get("CARDS_DIR", "assets/projects")

# GitHub's own language colours, except Rust, which matches the orange Rust badge.
COLOR_OVERRIDES = {"Rust": "#F74C00"}
OTHER_COLOR = "#8b949e"

THEMES = {
    "dark": {
        "bg": "#161b22", "border": "#30363d", "title": "#58a6ff", "text": "#c9d1d9",
        "muted": "#8b949e", "track": "#30363d", "live": "#3fb950",
    },
    "light": {
        "bg": "#ffffff", "border": "#d0d7de", "title": "#0969da", "text": "#1f2328",
        "muted": "#59636e", "track": "#eaeef2", "live": "#1a7f37",
    },
}

# Octicons (MIT, github.com/primer/octicons), 16x16.
ICONS = {
    "repo": "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.249.249 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z",
    "star": "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Zm0 2.445L6.615 5.5a.75.75 0 0 1-.564.41l-3.097.45 2.24 2.184a.75.75 0 0 1 .216.664l-.528 3.084 2.769-1.456a.75.75 0 0 1 .698 0l2.77 1.456-.53-3.084a.75.75 0 0 1 .216-.664l2.24-2.183-3.096-.45a.75.75 0 0 1-.564-.41L8 2.694Z",
    "fork": "M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 1 1 1.5 0v.878a2.25 2.25 0 0 1-2.25 2.25h-1.5v2.128a2.251 2.251 0 1 1-1.5 0V8.5h-1.5A2.25 2.25 0 0 1 3.5 6.25v-.878a2.25 2.25 0 1 1 1.5 0ZM5 3.25a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Zm6.75.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm-3 8.75a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z",
    "commit": "M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z",
    "history": "m.427 1.927 1.215 1.215a8.002 8.002 0 1 1-1.6 5.685.75.75 0 1 1 1.493-.154 6.5 6.5 0 1 0 1.18-4.458l1.358 1.358A.25.25 0 0 1 3.896 6H.25A.25.25 0 0 1 0 5.75V2.104a.25.25 0 0 1 .427-.177ZM7.75 4a.75.75 0 0 1 .75.75v2.992l2.028.812a.75.75 0 0 1-.557 1.392l-2.5-1A.751.751 0 0 1 7 8.25v-3.5A.75.75 0 0 1 7.75 4Z",
    "link": "M3.75 2h3.5a.75.75 0 0 1 0 1.5h-3.5a.25.25 0 0 0-.25.25v8.5c0 .138.112.25.25.25h8.5a.25.25 0 0 0 .25-.25v-3.5a.75.75 0 0 1 1.5 0v3.5A1.75 1.75 0 0 1 12.25 14h-8.5A1.75 1.75 0 0 1 2 12.25v-8.5C2 2.784 2.784 2 3.75 2Zm6.854-1h4.146a.25.25 0 0 1 .25.25v4.146a.25.25 0 0 1-.427.177L13.03 4.03 9.28 7.78a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042l3.75-3.75-1.543-1.543A.25.25 0 0 1 10.604 1Z",
}

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
WIDTH, HEIGHT, PAD = 440, 196, 24

QUERY = """query($cursor: String) { viewer { login repositories(first: 100, after: $cursor, privacy: PUBLIC,
    ownerAffiliations: OWNER, isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
    pageInfo { hasNextPage endCursor }
    nodes {
      name description url homepageUrl stargazerCount forkCount pushedAt isArchived
      defaultBranchRef { target { ... on Commit { history { totalCount } } } }
      languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name color } } }
    } } } }"""


def graphql(query, **variables):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    with urllib.request.urlopen(req) as res:
        data = json.load(res)
    if data.get("errors"):
        sys.exit(f"GraphQL error: {data['errors']}")
    return data["data"]


def fetch_repos():
    repos, cursor = [], None
    while True:
        viewer = graphql(QUERY, cursor=cursor)["viewer"]
        page = viewer["repositories"]
        # Skip the profile repo itself.
        repos += [r for r in page["nodes"] if r["name"].lower() != viewer["login"].lower()]
        if not page["pageInfo"]["hasNextPage"]:
            return repos
        cursor = page["pageInfo"]["endCursor"]


def text_width(text, size):
    """Rough rendered width of text in a sans-serif font, good enough for layout."""
    width = 0.0
    for ch in text:
        if ch in "iljtf.,:;'|!() ":
            width += 0.3
        elif ch in "mwMW":
            width += 0.85
        elif ch.isupper() or ch.isdigit():
            width += 0.64
        else:
            width += 0.54
    return width * size


def wrap(text, size, max_width, max_lines):
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if text_width(candidate, size) <= max_width:
            line = candidate
            continue
        lines.append(line)
        line = word
        if len(lines) == max_lines:
            break
    else:
        lines.append(line)
        return [l for l in lines if l]
    # Out of room: trim the last line and mark it as cut off.
    last = lines[-1]
    while last and text_width(last + "…", size) > max_width:
        last = last[:-1]
    lines[-1] = last.rstrip(" ,.;:") + "…"
    return lines


def icon(name, x, y, color, size=14):
    scale = size / 16
    return f'<path transform="translate({x} {y}) scale({scale})" fill="{color}" d="{ICONS[name]}"/>'


def languages(repo):
    """Top three languages plus an 'Other' bucket, as (name, colour, share)."""
    total = repo["languages"]["totalSize"]
    if not total:
        return []
    parts = [
        (e["node"]["name"], COLOR_OVERRIDES.get(e["node"]["name"], e["node"]["color"] or OTHER_COLOR), e["size"] / total)
        for e in repo["languages"]["edges"]
    ]
    top, rest = parts[:3], sum(share for _, _, share in parts[3:])
    return top + ([("Other", OTHER_COLOR, rest)] if rest >= 0.005 else [])


def render(repo, theme):
    t = THEMES[theme]
    esc = html.escape
    langs = languages(repo)
    accent = langs[0][1] if langs else t["border"]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'role="img" aria-label="{esc(repo["name"])}">',
        f"<title>{esc(repo['name'])}</title>",
        f'<defs><clipPath id="card"><rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="12"/></clipPath>'
        f'<clipPath id="bar"><rect x="{PAD}" y="118" width="{WIDTH - 2 * PAD}" height="8" rx="4"/></clipPath></defs>',
        f'<g clip-path="url(#card)">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{t["bg"]}"/>',
        # Thin strip in the main language's colour along the top edge.
        f'<rect width="{WIDTH}" height="4" fill="{accent}"/>',
        "</g>",
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="12" fill="none" stroke="{t["border"]}"/>',
        f'<g font-family="{FONT}">',
    ]

    # Title row, with a "Live" pill when the repo has a homepage.
    out.append(icon("repo", PAD, 29, t["muted"], 16))
    out.append(f'<text x="{PAD + 24}" y="42" font-size="17" font-weight="600" fill="{t["title"]}">{esc(repo["name"])}</text>')
    pill = "Archived" if repo["isArchived"] else "Live" if repo["homepageUrl"] else None
    if pill:
        color = t["muted"] if repo["isArchived"] else t["live"]
        pill_width = text_width(pill, 11) + (26 if pill == "Live" else 16)
        x = WIDTH - PAD - pill_width
        out.append(f'<rect x="{x}" y="27" width="{pill_width:.0f}" height="20" rx="10" fill="none" stroke="{color}"/>')
        if pill == "Live":
            out.append(f'<circle cx="{x + 11}" cy="37" r="3" fill="{color}"/>')
        text_x = x + (18 if pill == "Live" else 8)
        out.append(f'<text x="{text_x:.0f}" y="41" font-size="11" font-weight="600" fill="{color}">{pill}</text>')

    # Description, at most two lines.
    if repo["description"]:
        for i, line in enumerate(wrap(repo["description"], 13, WIDTH - 2 * PAD, 2)):
            out.append(f'<text x="{PAD}" y="{72 + i * 20}" font-size="13" fill="{t["text"]}">{esc(line)}</text>')
    else:
        out.append(f'<text x="{PAD}" y="72" font-size="13" font-style="italic" fill="{t["muted"]}">No description</text>')

    # Language bar and legend.
    out.append(f'<g clip-path="url(#bar)"><rect x="{PAD}" y="118" width="{WIDTH - 2 * PAD}" height="8" fill="{t["track"]}"/>')
    x = PAD
    for _, color, share in langs:
        width = share * (WIDTH - 2 * PAD)
        out.append(f'<rect x="{x:.1f}" y="118" width="{width + 0.5:.1f}" height="8" fill="{color}"/>')
        x += width
    out.append("</g>")
    x = PAD
    for name, color, share in langs:
        label = f"{name} {share:.0%}" if share >= 0.005 else name
        out.append(f'<circle cx="{x + 4}" cy="144" r="4" fill="{color}"/>')
        out.append(f'<text x="{x + 13}" y="148" font-size="12" fill="{t["text"]}">{esc(name)} '
                   f'<tspan fill="{t["muted"]}">{label[len(name):].strip()}</tspan></text>')
        x += 13 + text_width(label, 12) + 16
    if not langs:
        out.append(f'<text x="{PAD}" y="148" font-size="12" fill="{t["muted"]}">No code yet</text>')

    # Footer: stars and forks only when there are any, commits, last update, homepage.
    commits = ((repo["defaultBranchRef"] or {}).get("target") or {}).get("history", {}).get("totalCount", 0)
    updated = datetime.fromisoformat(repo["pushedAt"].replace("Z", "+00:00")).strftime("%b %Y")
    items = []
    if repo["stargazerCount"]:
        items.append(("star", str(repo["stargazerCount"])))
    if repo["forkCount"]:
        items.append(("fork", str(repo["forkCount"])))
    items.append(("commit", f"{commits} commit{'s' if commits != 1 else ''}"))
    items.append(("history", updated))
    x = PAD
    for name, label in items:
        out.append(icon(name, x, 165, t["muted"]))
        out.append(f'<text x="{x + 19}" y="176" font-size="12" fill="{t["muted"]}">{esc(label)}</text>')
        x += 19 + text_width(label, 12) + 16
    if repo["homepageUrl"]:
        domain = re.sub(r"^https?://(www\.)?", "", repo["homepageUrl"]).rstrip("/")
        out.append(f'<text x="{WIDTH - PAD}" y="176" font-size="12" text-anchor="end" fill="{t["title"]}">{esc(domain)}</text>')
        out.append(icon("link", WIDTH - PAD - text_width(domain, 12) - 19, 165, t["title"]))

    out += ["</g>", "</svg>"]
    return "\n".join(out) + "\n"


def card(repo):
    alt = repo["name"] + (f": {repo['description']}" if repo["description"] else "")
    path = f"{CARDS_DIR}/{repo['name']}"
    return (
        f'  <a href="{repo["url"]}"><picture>'
        f'<source media="(prefers-color-scheme: dark)" srcset="{path}-dark.svg" />'
        f'<img alt="{html.escape(alt)}" src="{path}-light.svg" width="49%" />'
        f"</picture></a>"
    )


def main():
    repos = fetch_repos()

    # Start from an empty folder so cards of deleted or now-private repos disappear.
    shutil.rmtree(CARDS_DIR, ignore_errors=True)
    os.makedirs(CARDS_DIR)
    for repo in repos:
        for theme in THEMES:
            with open(f"{CARDS_DIR}/{repo['name']}-{theme}.svg", "w") as f:
                f.write(render(repo, theme))

    block = "\n".join(["<!-- PROJECTS:START -->", '<p align="center">', *map(card, repos), "</p>", "<!-- PROJECTS:END -->"])
    with open(README) as f:
        readme = f.read()
    updated = re.sub(r"<!-- PROJECTS:START -->.*?<!-- PROJECTS:END -->", lambda _: block, readme, flags=re.S)
    with open(README, "w") as f:
        f.write(updated)
    print(f"{len(repos)} project cards: {', '.join(r['name'] for r in repos)}", file=sys.stderr)


if __name__ == "__main__":
    main()
