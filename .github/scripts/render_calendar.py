#!/usr/bin/env python3
"""Render the contribution calendar card (assets/cards/calendar-*.svg) from the GitHub API.

Last year's contributions as a heatmap in the cards' accent colour, with the current and longest
streak. The cells pop in as a diagonal wave and today's cell glows.
"""
import json
import os
import sys
import urllib.request
from datetime import date

from cards import PAD, THEMES, card, delay, text_width, write

TOKEN = os.environ["GH_TOKEN"]
WIDTH, HEIGHT = 880, 228
GAP = 3
GRID_TOP = 84

LEVELS = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]
QUERY = """{ viewer { contributionsCollection { contributionCalendar { totalContributions
    weeks { contributionDays { date weekday contributionCount contributionLevel } } } } } }"""

CSS = """
.cell{transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.3,1.6,.5,1) backwards}
@keyframes pop{from{transform:scale(0);opacity:0}}
.today{animation:pop .5s cubic-bezier(.3,1.6,.5,1) backwards,breathe 1.6s ease-in-out 2.5s infinite}
@keyframes breathe{50%{opacity:.35}}
.flame{transform-box:fill-box;transform-origin:bottom;animation:flicker .9s ease-in-out infinite alternate}
@keyframes flicker{to{transform:scale(1.08,.9) skewX(4deg)}}
"""
FLAME = "M8 0c1 3 5 5 5 9.5A5 5 0 0 1 3 9.5C3 7 4.5 5.5 5 4c.6 1.8 1.4 2.6 2.4 3C7 4.5 7.3 2 8 0Z"


def fetch_calendar():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    with urllib.request.urlopen(req) as res:
        data = json.load(res)
    if data.get("errors"):
        sys.exit(f"GraphQL error: {data['errors']}")
    return data["data"]["viewer"]["contributionsCollection"]["contributionCalendar"]


def streaks(days):
    """(current, longest) runs of days with contributions. Today without any doesn't break the run yet."""
    longest = run = 0
    for day in days:
        run = run + 1 if day["contributionCount"] else 0
        longest = max(longest, run)
    counts = [day["contributionCount"] for day in days]
    if counts and not counts[-1]:
        counts.pop()
    current = 0
    for count in reversed(counts):
        if not count:
            break
        current += 1
    return current, longest


def render(theme, calendar):
    t = THEMES[theme]
    weeks = calendar["weeks"]
    days = [day for week in weeks for day in week["contributionDays"]]
    total = calendar["totalContributions"]
    current, longest = streaks(days)
    step = (WIDTH - 2 * PAD + GAP) / len(weeks)
    size = step - GAP

    out = [
        f'<text class="in" x="{PAD}" y="42" font-size="16" font-weight="600" fill="{t["text"]}">{total:,} contributions '
        f'<tspan fill="{t["muted"]}" font-weight="400" font-size="14">in the last year</tspan></text>'
    ]
    streak = f"{current}-day streak" if current else "No current streak"
    right = WIDTH - PAD
    out.append(
        f'<g class="in"{delay(0.3)}><text x="{right}" y="42" font-size="13" text-anchor="end" fill="{t["text"]}">{streak} '
        f'<tspan fill="{t["muted"]}">· best {longest}</tspan></text>'
    )
    if current:
        # text_width errs wide by about a tenth; the flame should sit right next to the text.
        flame_x = right - text_width(f"{streak} · best {longest}", 13) / 1.1 - 19
        out.append(f'<g transform="translate({flame_x:.0f} 28) scale(.9)"><path class="flame" fill="#f78166" d="{FLAME}"/></g>')
    out.append("</g>")

    # Month names above the column holding the 1st, unless too close to the edge or the previous name.
    last = -3
    for c, week in enumerate(weeks):
        first = next((day["date"] for day in week["contributionDays"] if day["date"].endswith("-01")), None)
        if first and c - last >= 3 and c < len(weeks) - 2:
            label = date.fromisoformat(first).strftime("%b")
            out.append(f'<text class="in"{delay(0.2 + c * 0.01)} x="{PAD + c * step:.1f}" y="{GRID_TOP - 10}" '
                       f'font-size="11" fill="{t["muted"]}">{label}</text>')
            last = c

    # The cells, popping in as a wave from the top-left corner.
    today = days[-1]["date"]
    for c, week in enumerate(weeks):
        for day in week["contributionDays"]:
            r = day["weekday"]
            level = LEVELS.index(day["contributionLevel"])
            classes = "cell today" if day["date"] == today else "cell"
            fill = t["levels"][max(level, 1) if day["date"] == today else level]
            out.append(
                f'<rect class="{classes}" x="{PAD + c * step:.1f}" y="{GRID_TOP + r * step:.1f}" width="{size:.1f}" height="{size:.1f}" '
                f'rx="2.5" fill="{fill}"{delay((c + r) * 0.02)}/>'
            )

    # Legend, bottom right.
    legend_y = GRID_TOP + 7 * step + 6
    x = right - len(LEVELS) * 15 + GAP
    out.append(f'<text x="{x - 6:.0f}" y="{legend_y + 10:.0f}" font-size="11" text-anchor="end" fill="{t["muted"]}">Less</text>')
    for i, color in enumerate(t["levels"]):
        out.append(f'<rect x="{x + i * 15:.0f}" y="{legend_y:.0f}" width="11" height="11" rx="2.5" fill="{color}"/>')

    label = f"{total:,} contributions in the last year, current streak {current} days, longest {longest}"
    return card(WIDTH, HEIGHT, theme, out, label, CSS)


def main():
    calendar = fetch_calendar()
    write("assets/cards/calendar", lambda theme: render(theme, calendar))
    print(f"{calendar['totalContributions']} contributions over {len(calendar['weeks'])} weeks", file=sys.stderr)


if __name__ == "__main__":
    main()
