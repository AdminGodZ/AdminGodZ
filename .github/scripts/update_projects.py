#!/usr/bin/env python3
"""Render a card for every public repo you own and list them in README.md."""
import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import datetime

from cards import HALF, PAD, THEMES, card, esc, icon, language_bar, language_color, legend, picture, text_width, wrap, write

API = "https://api.github.com/graphql"
TOKEN = os.environ["GH_TOKEN"]
README = os.environ.get("README", "README.md")
CARDS_DIR = "assets/projects"
WIDTH, HEIGHT = 440, 196

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


def render(repo, theme):
    t = THEMES[theme]
    langs = languages(repo)
    out = []

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
            out.append(f'<circle cx="{x + 11:.0f}" cy="37" r="3" fill="{color}"/>')
        text_x = x + (18 if pill == "Live" else 8)
        out.append(f'<text x="{text_x:.0f}" y="41" font-size="11" font-weight="600" fill="{color}">{pill}</text>')

    # Description, at most two lines.
    if repo["description"]:
        for i, line in enumerate(wrap(repo["description"], 13, WIDTH - 2 * PAD, 2)):
            out.append(f'<text x="{PAD}" y="{72 + i * 20}" font-size="13" fill="{t["text"]}">{esc(line)}</text>')
    else:
        out.append(f'<text x="{PAD}" y="72" font-size="13" font-style="italic" fill="{t["muted"]}">No description</text>')

    # Language bar and legend.
    out += language_bar(langs, PAD, 118, WIDTH - 2 * PAD, t)
    if langs:
        out += legend(langs, PAD, 148, t)
    else:
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
        out.append(f'<text x="{x + 19:.0f}" y="176" font-size="12" fill="{t["muted"]}">{esc(label)}</text>')
        x += 19 + text_width(label, 12) + 16
    if repo["homepageUrl"]:
        domain = re.sub(r"^https?://(www\.)?", "", repo["homepageUrl"]).rstrip("/")
        out.append(f'<text x="{WIDTH - PAD}" y="176" font-size="12" text-anchor="end" fill="{t["title"]}">{esc(domain)}</text>')
        out.append(icon("link", WIDTH - PAD - text_width(domain, 12) - 19, 165, t["title"]))

    return card(WIDTH, HEIGHT, theme, out, repo["name"])


def main():
    repos = fetch_repos()

    # Start from an empty folder so cards of deleted or now-private repos disappear.
    shutil.rmtree(CARDS_DIR, ignore_errors=True)
    cells = []
    for repo in repos:
        path = f"{CARDS_DIR}/{repo['name']}"
        write(path, lambda theme: render(repo, theme))
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
