#!/usr/bin/env python3
"""Render a card for every public repo you own and list them in README.md.

Each card shows the last six months of commits as a sparkline that draws itself in. On the first
FEATURED cards, the most recently pushed repos, a light also sweeps around the border.
"""
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

from cards import (HALF, PAD, THEMES, card, delay, esc, icon, language_bar, language_color, legend, live_dot, picture,
                   text_width, wrap, write)

API = "https://api.github.com/graphql"
TOKEN = os.environ["GH_TOKEN"]
README = os.environ.get("README", "README.md")
CARDS_DIR = "assets/projects"
WIDTH, HEIGHT = 440, 240
WEEKS = 26  # weeks of commit activity in the sparkline
FEATURED = 4  # cards with the border sweep: the top two rows
SPARK_TOP, SPARK_BOTTOM = 118, 150

CSS = """
.draw{animation:draw 2s cubic-bezier(.4,0,.2,1) .4s backwards}
@keyframes draw{from{stroke-dashoffset:1}}
.late{animation:fade 1s 1.6s backwards}
@keyframes fade{from{opacity:0}}
"""

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


def commit_activity(repo):
    """Commits per week over the last WEEKS weeks, or None when GitHub hasn't computed them yet."""
    owner_name = repo["url"].split("github.com/", 1)[1]
    req = urllib.request.Request(f"https://api.github.com/repos/{owner_name}/stats/commit_activity",
                                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"})
    # The stats endpoint answers 202 while GitHub computes them in the background.
    for _ in range(10):
        try:
            with urllib.request.urlopen(req) as res:
                if res.status == 200:
                    return [week["total"] for week in json.load(res)][-WEEKS:]
                if res.status == 204:
                    return [0] * WEEKS
        except urllib.error.HTTPError as error:
            print(f"warning: commit activity for {repo['name']}: {error}", file=sys.stderr)
            return None
        time.sleep(3)
    print(f"warning: commit activity for {repo['name']} still not ready, skipping", file=sys.stderr)
    return None


def smooth_path(points):
    """A curve through points (Catmull-Rom as cubic Béziers), kept inside the sparkline's band."""
    clamp = lambda y: min(SPARK_BOTTOM, max(SPARK_TOP, y))
    path = [f"M{points[0][0]:.1f} {points[0][1]:.1f}"]
    for i in range(len(points) - 1):
        p0, p1, p2 = points[max(i - 1, 0)], points[i], points[i + 1]
        p3 = points[min(i + 2, len(points) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, clamp(p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, clamp(p2[1] - (p3[1] - p1[1]) / 6))
        path.append(f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    return " ".join(path)


def sparkline(weeks, t):
    """Weekly commits as a line that draws itself in over a fading area, ending in a pulsing dot.

    A repo without recent commits gets a quiet dashed baseline instead.
    """
    if not any(weeks):
        return [
            f'<text class="in"{delay(0.2)} x="{WIDTH - PAD}" y="{SPARK_TOP - 10}" font-size="11" text-anchor="end" '
            f'fill="{t["muted"]}">No commits in 6 months</text>',
            f'<line class="in"{delay(0.3)} x1="{PAD}" y1="{SPARK_BOTTOM}" x2="{WIDTH - PAD}" y2="{SPARK_BOTTOM}" '
            f'stroke="{t["border"]}" stroke-width="2" stroke-dasharray="2 5" stroke-linecap="round"/>',
        ]
    peak = max(weeks)
    span = (WIDTH - 2 * PAD) / (len(weeks) - 1)
    points = [(PAD + i * span, SPARK_BOTTOM - count / peak * (SPARK_BOTTOM - SPARK_TOP)) for i, count in enumerate(weeks)]
    line = smooth_path(points)
    end_x, end_y = points[-1]
    total = sum(weeks)
    return [
        f'<linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t["accent"]}" stop-opacity=".3"/>'
        f'<stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/></linearGradient>',
        f'<text class="in"{delay(0.2)} x="{WIDTH - PAD}" y="{SPARK_TOP - 10}" font-size="11" text-anchor="end" fill="{t["muted"]}">'
        f'{total} commit{"s" if total != 1 else ""} in 6 months</text>',
        f'<path class="late" d="{line} L{end_x:.1f} {SPARK_BOTTOM} L{PAD} {SPARK_BOTTOM}Z" fill="url(#area)"/>',
        f'<path class="draw" d="{line}" pathLength="1" stroke-dasharray="1" fill="none" stroke="{t["accent"]}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>',
        f'<g class="late">{live_dot(round(end_x, 1), round(end_y, 1), 3.5, t["accent"])}</g>',
    ]


def border_sweep(t):
    """A highlight that travels around the card's border. Hidden when motion is reduced."""
    return [
        f'<linearGradient id="sweep" x1="0" x2="1"><stop offset=".3" stop-color="{t["accent"]}" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="{t["accent"]}"/><stop offset=".55" stop-color="{t["title"]}"/>'
        f'<stop offset=".75" stop-color="{t["title"]}" stop-opacity="0"/>'
        '<animateTransform attributeName="gradientTransform" type="rotate" values="0 .5 .5;360 .5 .5" dur="5s" '
        'repeatCount="indefinite"/></linearGradient>',
        f'<rect class="motion" x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" rx="11.5" fill="none" '
        'stroke="url(#sweep)" stroke-width="1.5"/>',
    ]


def languages(repo):
    """Top three languages plus an 'Other' bucket, as (name, colour, share)."""
    total = repo["languages"]["totalSize"]
    if not total:
        return []
    parts = [
        (e["node"]["name"], language_color(e["node"]["name"], e["node"]["color"]), e["size"] / total)
        for e in repo["languages"]["edges"]
    ]
    top, rest = parts[:3], sum(share for _, _, share in parts[3:])
    return top + ([("Other", language_color("Other", None), rest)] if rest >= 0.005 else [])


def render(repo, theme, weeks, featured):
    t = THEMES[theme]
    langs = languages(repo)
    out = border_sweep(t) if featured else []

    # Title row, with a "Live" pill when the repo has a homepage.
    out.append(icon("repo", PAD, 29, t["muted"], 16))
    out.append(f'<text x="{PAD + 24}" y="42" font-size="17" font-weight="600" fill="{t["title"]}">{esc(repo["name"])}</text>')
    pill = "Archived" if repo["isArchived"] else "Live" if repo["homepageUrl"] else None
    if pill:
        color = t["muted"] if repo["isArchived"] else t["live"]
        pill_width = text_width(pill, 11) + (26 if pill == "Live" else 16)
        x = WIDTH - PAD - pill_width
        out.append(f'<rect x="{x:.0f}" y="27" width="{pill_width:.0f}" height="20" rx="10" fill="none" stroke="{color}"/>')
        if pill == "Live":
            out.append(live_dot(round(x + 11), 37, 3, color))
        text_x = x + (18 if pill == "Live" else 8)
        out.append(f'<text x="{text_x:.0f}" y="41" font-size="11" font-weight="600" fill="{color}">{pill}</text>')

    # Description, at most two lines.
    if repo["description"]:
        for i, line in enumerate(wrap(repo["description"], 13, WIDTH - 2 * PAD, 2)):
            out.append(f'<text class="in"{delay(0.1)} x="{PAD}" y="{72 + i * 20}" font-size="13" fill="{t["text"]}">{esc(line)}</text>')
    else:
        out.append(f'<text class="in"{delay(0.1)} x="{PAD}" y="72" font-size="13" font-style="italic" fill="{t["muted"]}">No description</text>')

    # Commits per week, when GitHub has them.
    if weeks:
        out += sparkline(weeks, t)

    # Language bar and legend.
    out += language_bar(langs, PAD, 164, WIDTH - 2 * PAD, t, start=0.3)
    if langs:
        out += legend(langs, PAD, 194, t, start=0.8)
    else:
        out.append(f'<text x="{PAD}" y="194" font-size="12" fill="{t["muted"]}">No code yet</text>')

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
    out.append(f'<g class="in"{delay(0.9)}>')
    for name, label in items:
        out.append(icon(name, x, 209, t["muted"]))
        out.append(f'<text x="{x + 19:.0f}" y="220" font-size="12" fill="{t["muted"]}">{esc(label)}</text>')
        x += 19 + text_width(label, 12) + 16
    if repo["homepageUrl"]:
        domain = re.sub(r"^https?://(www\.)?", "", repo["homepageUrl"]).rstrip("/")
        out.append(f'<text x="{WIDTH - PAD}" y="220" font-size="12" text-anchor="end" fill="{t["title"]}">{esc(domain)}</text>')
        out.append(icon("link", WIDTH - PAD - text_width(domain, 12) - 19, 209, t["title"]))
    out.append("</g>")

    return card(WIDTH, HEIGHT, theme, out, repo["name"], CSS)


def main():
    repos = fetch_repos()

    # Start from an empty folder so cards of deleted or now-private repos disappear.
    shutil.rmtree(CARDS_DIR, ignore_errors=True)
    cells = []
    for i, repo in enumerate(repos):
        path = f"{CARDS_DIR}/{repo['name']}"
        weeks = commit_activity(repo)
        write(path, lambda theme: render(repo, theme, weeks, i < FEATURED))
        alt = repo["name"] + (f": {repo['description']}" if repo["description"] else "")
        cells.append(picture(path, alt, HALF, repo["url"]))

    # Two cards per line with no whitespace between them, so they fill the row exactly.
    rows = ["  " + "".join(cells[i:i + 2]) for i in range(0, len(cells), 2)]
    block = "\n".join(["<!-- PROJECTS:START -->", '<p align="center">', *rows, "</p>", "<!-- PROJECTS:END -->"])
    with open(README) as f:
        readme = f.read()
    updated = re.sub(r"<!-- PROJECTS:START -->.*?<!-- PROJECTS:END -->", lambda _: block, readme, flags=re.S)
    with open(README, "w") as f:
        f.write(updated)
    print(f"{len(repos)} project cards: {', '.join(r['name'] for r in repos)}", file=sys.stderr)


if __name__ == "__main__":
    main()
