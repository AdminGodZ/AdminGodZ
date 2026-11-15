#!/usr/bin/env python3
"""Render the header card (assets/cards/header-*.svg): avatar, name, a typed tagline and links.

Animated: the name shimmers, a ring orbits the avatar, the glows drift, stars twinkle and the
tagline types out each line of TAGLINES in turn.
"""
import base64
import json
import os
import urllib.request
from datetime import datetime

from cards import PAD, THEMES, card, delay, esc, icon, live_dot, text_width, write
from render_stack import STACK

TOKEN = os.environ["GH_TOKEN"]
HOMEPAGE = "https://admingod.ch"
WIDTH, HEIGHT = 880, 200
GLOW = "#a371f7"  # purple to match the avatar
SECOND_GLOW = "#58a6ff"

# Lines the tagline types out in turn. The languages from the stack card are always added last,
# and are the only line shown to visitors who prefer reduced motion.
TAGLINES = [
    "Building Aeralyth, a self-hostable cloud",
    "Tuning AetherZ, a C++ chess engine",
]
LINE_SECONDS = 4  # time each line gets: typing, a pause, then deleting
STARS = [(620, 40, 1.2, 0), (700, 70, 1, 1.1), (760, 30, 1.4, .6), (820, 110, 1, 2),
         (660, 140, 1.1, 1.6), (560, 60, .9, 2.4), (840, 50, 1.2, .3), (590, 160, 1, 1.3)]

CSS = """
.drift-a{animation:drift-a 11s ease-in-out infinite alternate}
.drift-b{animation:drift-b 13s ease-in-out infinite alternate}
@keyframes drift-a{to{transform:translate(50px,-24px)}}
@keyframes drift-b{to{transform:translate(-90px,-30px)}}
.orbit{transform-box:fill-box;transform-origin:center;animation:orbit 6s linear infinite}
@keyframes orbit{to{transform:rotate(360deg)}}
.twinkle{animation:twinkle 3s ease-in-out infinite}
@keyframes twinkle{50%{opacity:.1}}
.blink{animation:blink 1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
"""


def fetch(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req) as res:
        return res.read(), res.headers.get_content_type()


def pill(x, y, name, label, color, t, live=False):
    """Rounded outline with an icon (or a live dot) and label; returns (elements, width)."""
    width = 14 + 16 + 6 + text_width(label, 13) + 12
    if live:
        frame = f'<rect x="{x:.0f}" y="{y}" width="{width:.0f}" height="30" rx="15" fill="{color}" fill-opacity=".08" stroke="{color}" stroke-opacity=".4"/>'
        mark = live_dot(x + 18, y + 15, 4, color)
    else:
        frame = f'<rect x="{x:.0f}" y="{y}" width="{width:.0f}" height="30" rx="15" fill="none" stroke="{t["border"]}"/>'
        mark = icon(name, x + 14, y + 8, color)
    return [frame, mark, f'<text x="{x + 36:.0f}" y="{y + 20}" font-size="13" fill="{color}">{esc(label)}</text>'], width


def tagline(lines, x, y, t):
    """Types out each line, pauses, deletes it, then moves on to the next, with a blinking caret.

    Returns (css, defs, elements). The last line stays visible when motion is reduced.
    """
    cycle = LINE_SECONDS * len(lines)
    typed, held, deleted = (100 * s / cycle for s in (1.2, LINE_SECONDS - 0.9, LINE_SECONDS - 0.4))
    css, defs, out = [], [], []
    for i, line in enumerate(lines):
        # A mask slides right one character per step to reveal the line; the caret follows its edge.
        width = text_width(line, 16) / 1.08
        hidden = f"transform:translateX(-{width:.0f}px)"
        caret_end = f"transform:translateX({width:.0f}px)"
        timing = f"{cycle}s steps({len(line)}) {i * LINE_SECONDS}s infinite both"
        css.append(
            f"@keyframes type{i}{{0%{{{hidden}}}{typed:.1f}%,{held:.1f}%{{transform:none}}{deleted:.1f}%,100%{{{hidden}}}}}"
            f"@keyframes caret{i}{{0%{{transform:none;opacity:1}}{typed:.1f}%,{held:.1f}%{{{caret_end}}}"
            f"{deleted:.1f}%{{transform:none;opacity:1}}{deleted + 0.1:.1f}%,100%{{opacity:0}}}}"
            f".type{i}{{animation:type{i} {timing}}}.caret{i}{{animation:caret{i} {timing}}}"
        )
        defs.append(f'<mask id="line{i}" maskUnits="userSpaceOnUse" x="0" y="0" width="{WIDTH}" height="{HEIGHT}">'
                    f'<rect class="type{i}" x="{x}" y="{y - 22}" width="{width + 4:.0f}" height="30" fill="#fff"/></mask>')
        hide = ' class="motion"' if i < len(lines) - 1 else ""
        out.append(f'<g{hide}><text x="{x}" y="{y}" font-size="16" fill="{t["muted"]}" mask="url(#line{i})">{esc(line)}</text>'
                   f'<g class="motion caret{i}"><rect class="blink" x="{x + 1}" y="{y - 14}" width="2" height="18" fill="{t["accent"]}"/></g></g>')
    return "".join(css), defs, out


def render(theme, user, avatar, working_on):
    t = THEMES[theme]
    dark = theme == "dark"
    glow = 0.38 if dark else 0.18
    cx, cy, r = PAD + 76, HEIGHT / 2, 64
    name = user["name"] or user["login"]
    x = cx + r + 40
    name_width = text_width(name, 46)
    languages = " · ".join(name for name, _, _ in STACK["Languages"])
    css, masks, typed = tagline(TAGLINES + [languages], x, 118, t)
    shine = [t["text"], t["accent"], t["title"], t["text"]]

    out = [
        "<defs>",
        f'<radialGradient id="glow"><stop offset="0" stop-color="{GLOW}" stop-opacity="{glow}"/>'
        f'<stop offset="1" stop-color="{GLOW}" stop-opacity="0"/></radialGradient>',
        f'<radialGradient id="glow2"><stop offset="0" stop-color="{SECOND_GLOW}" stop-opacity="{glow * 0.7:.2f}"/>'
        f'<stop offset="1" stop-color="{SECOND_GLOW}" stop-opacity="0"/></radialGradient>',
        # Static gradient for the name, and one that sweeps across it every few seconds.
        f'<linearGradient id="name" x1="0" x2="1"><stop offset="0" stop-color="{t["text"]}"/>'
        f'<stop offset="1" stop-color="{t["accent"]}"/></linearGradient>',
        f'<linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="{x}" x2="{x + name_width * 1.6:.0f}">'
        + "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in zip((0, .45, .6, 1), shine))
        + f'<animateTransform attributeName="gradientTransform" type="translate" '
        f'values="-{name_width * 1.6:.0f} 0;{name_width * 0.6:.0f} 0;-{name_width * 1.6:.0f} 0" dur="7s" repeatCount="indefinite"/></linearGradient>',
        f'<linearGradient id="ring" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="{t["accent"]}"/>'
        f'<stop offset="1" stop-color="{t["title"]}"/></linearGradient>',
        f'<clipPath id="avatar"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>',
        f'<clipPath id="inside"><rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" rx="11"/></clipPath>',
        *masks,
        "</defs>",
        # Soft lights behind the avatar and in the corners, drifting slowly, plus a few twinkling stars.
        '<g clip-path="url(#inside)">',
        f'<circle class="drift-a" cx="{cx}" cy="{cy}" r="{r * 2.3:.0f}" fill="url(#glow)"/>',
        f'<circle class="drift-b" cx="{WIDTH - 60}" cy="{HEIGHT + 30}" r="260" fill="url(#glow)" opacity="0.7"/>',
        f'<circle class="drift-a" cx="{WIDTH - 320}" cy="-40" r="200" fill="url(#glow2)"/>',
        *(f'<circle class="twinkle" cx="{sx}" cy="{sy}" r="{sr}" fill="{"#fff" if dark else t["accent"]}" '
          f'opacity="{.5 if dark else .35}"{delay(sd)}/>' for sx, sy, sr, sd in STARS),
        "</g>",
        f'<image href="{avatar}" x="{cx - r}" y="{cy - r}" width="{2 * r}" height="{2 * r}" clip-path="url(#avatar)"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{r + 6}" fill="none" stroke="{t["border"]}" stroke-width="2"/>',
        f'<circle class="orbit" cx="{cx}" cy="{cy}" r="{r + 6}" fill="none" stroke="url(#ring)" stroke-width="3" '
        f'stroke-linecap="round" stroke-dasharray="90 350"/>',
        f'<g class="in"><text x="{x}" y="84" font-size="46" font-weight="700" fill="url(#name)">{esc(name)}</text>'
        f'<text class="motion" x="{x}" y="84" font-size="46" font-weight="700" fill="url(#shine)">{esc(name)}</text></g>',
        *typed,
    ]

    since = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00")).strftime("%b %Y")
    domain = HOMEPAGE.split("://", 1)[1]
    pills = [("link", domain, t["title"], False)]
    if working_on:
        pills.append((None, f"Working on {working_on}", t["live"], True))
    pills.append(("history", f"On GitHub since {since}", t["muted"], False))
    for i, (icon_name, label, color, live) in enumerate(pills):
        elements, width = pill(x, 140, icon_name, label, color, t, live)
        out += [f'<g class="in"{delay(0.4 + i * 0.12)}>', *elements, "</g>"]
        x += width + 10

    return card(WIDTH, HEIGHT, theme, out, f"{name} · {domain}", CSS + css)


def latest_project(login):
    """Name of your most recently pushed public repo, skipping this profile repo, forks and archives."""
    raw, _ = fetch(f"https://api.github.com/users/{login}/repos?type=owner&sort=pushed&per_page=10")
    for repo in json.loads(raw):
        if repo["name"].lower() != login.lower() and not repo["fork"] and not repo["archived"]:
            return repo["name"]
    return None


def main():
    raw, _ = fetch("https://api.github.com/user")
    user = json.loads(raw)
    image, mime = fetch(user["avatar_url"] + "&s=256")
    # Embedded, because SVGs shown through <img> can't load external images.
    avatar = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    working_on = latest_project(user["login"])
    write("assets/cards/header", lambda theme: render(theme, user, avatar, working_on))


if __name__ == "__main__":
    main()
