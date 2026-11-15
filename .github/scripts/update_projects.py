#!/usr/bin/env python3
"""Render a card for every public repo you own and list them in README.md, grouped into tiers.

Each repo is ranked into a tier by its lines of code (see tiers.py): Ruby, Diamond, Platinum and
Gold are listed openly, Silver, Bronze and repos without code sit in a collapsed section. Every card
shows its tier, its lines of code with progress towards the next tier, and the last six months of
commits as a sparkline that draws itself in. Needs cloc installed to count lines.
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

from cards import (ANIMATIONS, FONT, FULL, HALF, MARGIN, PAD, REDUCED_MOTION, THEMES, card, delay, ellipsize, esc, icon,
                   language_bar, language_color, legend, live_dot, picture, text_width, wrap, write)
from tiers import (DIAMOND, GOLD, PLATINUM, RUBY, SILVER, TIERS, count_lines, emblem, emblem_outline, progress,
                   range_label, text_color, tier_of)

API = "https://api.github.com/graphql"
TOKEN = os.environ["GH_TOKEN"]
README = os.environ.get("README", "README.md")
CARDS_DIR = "assets/projects"
HALF_WIDTH, FULL_WIDTH, HEIGHT = 440, 880, 280
WEEKS = 26  # weeks of commit activity in the sparkline
SPARK_TOP, SPARK_BOTTOM = 168, 196
OPEN_TIERS = (RUBY, DIAMOND, PLATINUM, GOLD)  # listed openly; the rest go in a collapsed section
EMBLEM = (PAD, 26, 22)  # x, y and size of the emblem in the title row

CSS = """
.draw{animation:draw 2s cubic-bezier(.4,0,.2,1) .4s backwards}
@keyframes draw{from{stroke-dashoffset:1}}
.late{animation:fade 1s 1.6s backwards}
@keyframes fade{from{opacity:0}}
.pop{transform-box:fill-box;transform-origin:center;animation:pop .6s cubic-bezier(.3,1.6,.5,1) .15s backwards}
@keyframes pop{from{transform:scale(0) rotate(-25deg);opacity:0}}
.glint{animation:glint 3.5s ease-in-out 1.2s infinite}
@keyframes glint{0%{transform:translateX(0)}35%,100%{transform:translateX(40px)}}
.sparkle{transform-box:fill-box;transform-origin:center;animation:sparkle 2.4s ease-in-out infinite}
@keyframes sparkle{0%,100%{opacity:0;transform:scale(.3)}50%{opacity:1;transform:scale(1)}}
.breathe{animation:breathe 4s ease-in-out infinite}
@keyframes breathe{50%{opacity:.45}}
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


def sparkline(weeks, width, t):
    """Weekly commits as a line that draws itself in over a fading area, ending in a pulsing dot.

    A repo without recent commits gets a quiet dashed baseline instead.
    """
    right = width - PAD
    if not any(weeks):
        return [
            f'<text class="in"{delay(0.2)} x="{right}" y="{SPARK_TOP - 10}" font-size="11" text-anchor="end" '
            f'fill="{t["muted"]}">No commits in 6 months</text>',
            f'<line class="in"{delay(0.3)} x1="{PAD}" y1="{SPARK_BOTTOM}" x2="{right}" y2="{SPARK_BOTTOM}" '
            f'stroke="{t["border"]}" stroke-width="2" stroke-dasharray="2 5" stroke-linecap="round"/>',
        ]
    peak = max(weeks)
    span = (width - 2 * PAD) / (len(weeks) - 1)
    points = [(PAD + i * span, SPARK_BOTTOM - count / peak * (SPARK_BOTTOM - SPARK_TOP)) for i, count in enumerate(weeks)]
    line = smooth_path(points)
    end_x, end_y = points[-1]
    total = sum(weeks)
    return [
        f'<linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t["accent"]}" stop-opacity=".3"/>'
        f'<stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/></linearGradient>',
        f'<text class="in"{delay(0.2)} x="{right}" y="{SPARK_TOP - 10}" font-size="11" text-anchor="end" fill="{t["muted"]}">'
        f'{total} commit{"s" if total != 1 else ""} in 6 months</text>',
        f'<path class="late" d="{line} L{end_x:.1f} {SPARK_BOTTOM} L{PAD} {SPARK_BOTTOM}Z" fill="url(#area)"/>',
        f'<path class="draw" d="{line}" pathLength="1" stroke-dasharray="1" fill="none" stroke="{t["accent"]}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>',
        f'<g class="late">{live_dot(round(end_x, 1), round(end_y, 1), 3.5, t["accent"])}</g>',
    ]


def tier_effects(tier, width, t):
    """Everything a tier adds around the card and its emblem, cumulative from Bronze up."""
    light, main, dark = TIERS[tier][2]
    x, y, size = EMBLEM
    out = []
    if tier <= RUBY:
        # A soft glow from the top-left corner that slowly breathes.
        out.append(f'<radialGradient id="glow" cx="0" cy="0" r="1" gradientTransform="scale({width} {HEIGHT * 1.4:.0f})" '
                   f'gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="{main}" stop-opacity=".2"/>'
                   f'<stop offset=".6" stop-color="{main}" stop-opacity="0"/></radialGradient>')
        out.append(f'<rect class="breathe" x="1" y="1" width="{width - 2}" height="{HEIGHT - 2}" rx="11" fill="url(#glow)"/>')
    if tier <= GOLD:
        # Border tinted with the tier colour, fading out from the top-left corner.
        out.append(f'<linearGradient id="tint" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{main}" stop-opacity=".9"/>'
                   f'<stop offset=".5" stop-color="{main}" stop-opacity="0"/></linearGradient>')
        out.append(f'<rect x=".5" y=".5" width="{width - 1}" height="{HEIGHT - 1}" rx="12" fill="none" stroke="url(#tint)"/>')
    if tier <= PLATINUM:
        # A light in the tier's colours travelling around the border (hidden when motion is reduced).
        out.append(f'<linearGradient id="sweep" x1="0" x2="1"><stop offset=".3" stop-color="{dark}" stop-opacity="0"/>'
                   f'<stop offset=".5" stop-color="{main}"/><stop offset=".55" stop-color="{light}"/>'
                   f'<stop offset=".75" stop-color="{main}" stop-opacity="0"/>'
                   '<animateTransform attributeName="gradientTransform" type="rotate" values="0 .5 .5;360 .5 .5" dur="5s" '
                   'repeatCount="indefinite"/></linearGradient>')
        out.append(f'<rect class="motion" x="1" y="1" width="{width - 2}" height="{HEIGHT - 2}" rx="11.5" fill="none" '
                   'stroke="url(#sweep)" stroke-width="1.5"/>')
    if tier <= SILVER:
        # A glint crossing the emblem every few seconds.
        band = f"{x - 16},{y + size} {x - 9},{y} {x - 4},{y} {x - 11},{y + size}"
        out.append(f'<clipPath id="emblem-shape">{emblem_outline(tier, x, y, size)}</clipPath>')
        out.append(f'<g clip-path="url(#emblem-shape)"><polygon class="glint" points="{band}" fill="#fff" fill-opacity=".75"/></g>')
    if tier <= DIAMOND:
        # Sparkles twinkling around the emblem.
        star = "M0 -4L1 -1 4 0 1 1 0 4-1 1-4 0-1-1Z"
        for sx, sy, scale, wait in ((x + size + 2, y - 1, 1, 0), (x - 3, y + size + 1, .7, .8), (x + 4, y - 4, .55, 1.6)):
            out.append(f'<g transform="translate({sx} {sy}) scale({scale})"><path class="sparkle" d="{star}" fill="{light}"'
                       f'{delay(wait)}/></g>')
    return out


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


def render(repo, theme, weeks, lines, wide):
    t = THEMES[theme]
    width = FULL_WIDTH if wide else HALF_WIDTH
    right = width - PAD
    tier = tier_of(lines)
    langs = languages(repo)
    out = tier_effects(tier, width, t) if tier is not None else []

    # Title row: emblem (or the repo icon without a tier), name, tier badge and a Live pill.
    x, y, size = EMBLEM
    if tier is None:
        out.append(icon("repo", PAD, 29, t["muted"], 16))
    else:
        out.append(f'<g class="pop">{emblem(tier, x, y, size, 0)}</g>')
    pill = "Archived" if repo["isArchived"] else "Live" if repo["homepageUrl"] else None
    pill_width = text_width(pill, 11) + (26 if pill == "Live" else 16) if pill else 0
    badge = TIERS[tier][0] if tier is not None else None
    badge_width = text_width(badge, 11) + 14 if badge else 0
    name_x = PAD + size + 8
    name = ellipsize(repo["name"], 17, right - name_x - (badge_width + 10 if badge else 0) - (pill_width + 10 if pill else 0))
    out.append(f'<text x="{name_x}" y="43" font-size="17" font-weight="600" fill="{t["title"]}">{esc(name)}</text>')
    if badge:
        color = text_color(tier, theme)
        bx = name_x + text_width(name, 17) / 1.1 + 8  # text_width errs wide by about a tenth
        out.append(f'<g class="in"{delay(0.3)}><rect x="{bx:.0f}" y="28" width="{badge_width:.0f}" height="20" rx="10" '
                   f'fill="{color}" fill-opacity=".1" stroke="{color}" stroke-opacity=".5"/>'
                   f'<text x="{bx + 7:.0f}" y="42" font-size="11" font-weight="600" fill="{color}">{badge}</text></g>')
    if pill:
        color = t["muted"] if repo["isArchived"] else t["live"]
        px = right - pill_width
        out.append(f'<rect x="{px:.0f}" y="28" width="{pill_width:.0f}" height="20" rx="10" fill="none" stroke="{color}"/>')
        if pill == "Live":
            out.append(live_dot(round(px + 11), 38, 3, color))
        out.append(f'<text x="{px + (18 if pill == "Live" else 8):.0f}" y="42" font-size="11" font-weight="600" fill="{color}">{pill}</text>')

    # Description, at most two lines (one is plenty on a wide card).
    if repo["description"]:
        for i, line in enumerate(wrap(repo["description"], 13, width - 2 * PAD, 1 if wide else 2)):
            out.append(f'<text class="in"{delay(0.1)} x="{PAD}" y="{74 + i * 20}" font-size="13" fill="{t["text"]}">{esc(line)}</text>')
    else:
        out.append(f'<text class="in"{delay(0.1)} x="{PAD}" y="74" font-size="13" font-style="italic" fill="{t["muted"]}">No description</text>')

    # Lines of code, and progress through the tier towards the next one.
    if tier is None:
        out.append(f'<text class="in"{delay(0.2)} x="{PAD}" y="126" font-size="13" fill="{t["muted"]}">No code yet</text>')
    else:
        light, main, dark = TIERS[tier][2]
        share, next_step = progress(tier, lines)
        out.append(f'<g class="in"{delay(0.2)}><text x="{PAD}" y="126" font-size="18" font-weight="700" fill="{t["text"]}">{lines:,} '
                   f'<tspan font-size="12" font-weight="400" fill="{t["muted"]}">lines</tspan></text>'
                   f'<text x="{right}" y="126" font-size="11" text-anchor="end" fill="{t["muted"]}">{next_step}</text></g>')
        out.append(f'<linearGradient id="progress"><stop offset="0" stop-color="{dark}"/><stop offset=".6" stop-color="{main}"/>'
                   f'<stop offset="1" stop-color="{light}"/></linearGradient>'
                   f'<rect x="{PAD}" y="134" width="{width - 2 * PAD}" height="4" rx="2" fill="{t["track"]}"/>'
                   f'<rect class="grow"{delay(0.4)} x="{PAD}" y="134" width="{max(share, 0.02) * (width - 2 * PAD):.1f}" height="4" '
                   f'rx="2" fill="url(#progress)"/>')

    # Commits per week, when GitHub has them.
    if weeks:
        out += sparkline(weeks, width, t)

    # Language bar and legend.
    out += language_bar(langs, PAD, 210, width - 2 * PAD, t, start=0.3)
    if langs:
        out += legend(langs, PAD, 238, t, start=0.8)

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
        out.append(icon(name, x, 251, t["muted"]))
        out.append(f'<text x="{x + 19:.0f}" y="262" font-size="12" fill="{t["muted"]}">{esc(label)}</text>')
        x += 19 + text_width(label, 12) + 16
    if repo["homepageUrl"]:
        domain = re.sub(r"^https?://(www\.)?", "", repo["homepageUrl"]).rstrip("/")
        out.append(f'<text x="{right}" y="262" font-size="12" text-anchor="end" fill="{t["title"]}">{esc(domain)}</text>')
        out.append(icon("link", right - text_width(domain, 12) - 19, 251, t["title"]))
    out.append("</g>")

    label = repo["name"] + (f", {TIERS[tier][0]} tier, {lines:,} lines of code" if tier is not None else "")
    return card(width, HEIGHT, theme, out, label, CSS)


def heading(theme, tier, count):
    """Full-width title above a tier's cards: emblem, name, line range and a line fading out to the right."""
    t = THEMES[theme]
    width, height = FULL_WIDTH + 2 * MARGIN, 46
    if tier is None:
        name, detail, color, mark, x = "No code yet", "", t["muted"], "", MARGIN + 4
    else:
        name, detail, color = TIERS[tier][0], f"{range_label(tier)} · ", text_color(tier, theme)
        mark, x = f'<g class="pop">{emblem(tier, MARGIN + 4, 12, 22, 0)}</g>', MARGIN + 36
    detail += f"{count} project{'s' if count != 1 else ''}"
    line_x = x + (text_width(name, 17) + 4 + text_width(detail, 13)) / 1.1 + 18  # text_width errs wide
    label = f"{name}: {detail}"
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{esc(label)}"><title>{esc(label)}</title>',
        f"<style>{ANIMATIONS}{CSS}{REDUCED_MOTION}</style>",
        f'<linearGradient id="fade" x1="0" x2="1"><stop offset="0" stop-color="{color}" stop-opacity=".6"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient>',
        f'<g font-family="{FONT}">',
        mark,
        f'<text class="in" x="{x}" y="30" font-size="17" font-weight="600" fill="{color}">{esc(name)} '
        f'<tspan dx="4" font-size="13" font-weight="400" fill="{t["muted"]}">{esc(detail)}</tspan></text>',
        f'<rect class="grow"{delay(0.3)} x="{line_x:.0f}" y="23" width="{width - MARGIN - line_x:.0f}" height="1" fill="url(#fade)"/>',
        "</g></svg>",
    ]) + "\n"


def write_heading(tier, count):
    path = f"{CARDS_DIR}/tiers/{TIERS[tier][0].lower() if tier is not None else 'no-code'}"
    write(path, lambda theme: heading(theme, tier, count))
    name = TIERS[tier][0] if tier is not None else "No code yet"
    return picture(path, f"{name} tier" if tier is not None else name, FULL)


def main():
    if not shutil.which("cloc"):
        sys.exit("cloc is needed to count lines of code: install it with `apt install cloc` or `brew install cloc`")
    repos = fetch_repos()
    for repo in repos:
        repo["lines"] = count_lines(repo["url"] + ".git") if repo["languages"]["totalSize"] else 0
        print(f"{repo['name']}: {repo['lines']:,} lines", file=sys.stderr)

    # Group by tier, biggest first within each. Repos without code form their own group at the end.
    groups = {}
    for repo in sorted(repos, key=lambda repo: -repo["lines"]):
        groups.setdefault(tier_of(repo["lines"]), []).append(repo)
    order = [tier for tier in range(len(TIERS)) if tier in groups] + ([None] if None in groups else [])

    # Start from an empty folder so cards of deleted or now-private repos disappear.
    shutil.rmtree(CARDS_DIR, ignore_errors=True)
    shown, hidden = [], []
    for tier in order:
        members = groups[tier]
        # A tier's only project, and every Ruby project, gets a full-width card.
        wide = tier == RUBY or len(members) == 1
        cells = []
        for repo in members:
            path = f"{CARDS_DIR}/{repo['name']}"
            weeks = commit_activity(repo)
            write(path, lambda theme: render(repo, theme, weeks, repo["lines"], wide))
            alt = repo["name"] + (f": {repo['description']}" if repo["description"] else "")
            cells.append(picture(path, alt, FULL if wide else HALF, repo["url"]))
        # Two half-width cards per line with no whitespace between them, so they fill the row exactly.
        step = 1 if wide else 2
        rows = ["  " + write_heading(tier, len(members))] + ["  " + "".join(cells[i:i + step]) for i in range(0, len(cells), step)]
        (shown if tier in OPEN_TIERS else hidden).extend(rows)

    block = ["<!-- PROJECTS:START -->"]
    if shown:
        block += ['<p align="center">', *shown, "</p>"]
    if hidden:
        tiers = [TIERS[tier][0] for tier in order if tier is not None and tier not in OPEN_TIERS]
        ranked = sum(len(groups[tier]) for tier in order if tier is not None and tier not in OPEN_TIERS)
        summary = f"<b>{' &amp; '.join(tiers)}</b> · {ranked} smaller project{'s' if ranked != 1 else ''}" if tiers else "<b>More projects</b>"
        if None in groups:
            summary += f", plus {len(groups[None])} without code"
        block += ["<details>", f"<summary>{summary}</summary>", "", '<p align="center">', *hidden, "</p>", "</details>"]
    block.append("<!-- PROJECTS:END -->")

    with open(README) as f:
        readme = f.read()
    updated = re.sub(r"<!-- PROJECTS:START -->.*?<!-- PROJECTS:END -->", lambda _: "\n".join(block), readme, flags=re.S)
    with open(README, "w") as f:
        f.write(updated)
    print(" / ".join(f"{TIERS[tier][0] if tier is not None else 'No code'}: {', '.join(r['name'] for r in groups[tier])}"
                     for tier in order), file=sys.stderr)


if __name__ == "__main__":
    main()
