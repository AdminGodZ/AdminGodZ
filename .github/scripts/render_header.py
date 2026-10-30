#!/usr/bin/env python3
"""Render the header card (assets/cards/header-*.svg): avatar, name, languages and links."""
import base64
import json
import os
import urllib.request
from datetime import datetime

from cards import PAD, THEMES, card, esc, icon, text_width, write
from render_stack import STACK

TOKEN = os.environ["GH_TOKEN"]
HOMEPAGE = "https://admingod.ch"
WIDTH, HEIGHT = 880, 200
GLOW = "#a371f7"  # purple to match the avatar


def fetch(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req) as res:
        return res.read(), res.headers.get_content_type()


def pill(x, y, name, label, color, t):
    """Rounded outline with an icon and label; returns (elements, width)."""
    width = 14 + 16 + 6 + text_width(label, 13) + 12
    return [
        f'<rect x="{x:.0f}" y="{y}" width="{width:.0f}" height="30" rx="15" fill="none" stroke="{t["border"]}"/>',
        icon(name, x + 14, y + 8, color),
        f'<text x="{x + 36:.0f}" y="{y + 20}" font-size="13" fill="{color}">{esc(label)}</text>',
    ], width


def render(theme, user, avatar):
    t = THEMES[theme]
    glow = 0.35 if theme == "dark" else 0.18
    cx, cy, r = PAD + 76, HEIGHT / 2, 64
    out = [
        "<defs>",
        f'<radialGradient id="glow"><stop offset="0" stop-color="{GLOW}" stop-opacity="{glow}"/>'
        f'<stop offset="1" stop-color="{GLOW}" stop-opacity="0"/></radialGradient>',
        f'<linearGradient id="name" x1="0" x2="1"><stop offset="0" stop-color="{t["text"]}"/>'
        f'<stop offset="1" stop-color="{GLOW if theme == "dark" else "#8250df"}"/></linearGradient>',
        f'<clipPath id="avatar"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>',
        f'<clipPath id="inside"><rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" rx="11"/></clipPath>',
        "</defs>",
        # Soft purple light behind the avatar, kept inside the card's rounded edge.
        f'<circle cx="{cx}" cy="{cy}" r="{r * 2.2:.0f}" fill="url(#glow)" clip-path="url(#inside)"/>',
        # A fainter one in the far corner to balance the empty right side.
        f'<circle cx="{WIDTH - 40}" cy="{HEIGHT + 40}" r="260" fill="url(#glow)" opacity="0.6" clip-path="url(#inside)"/>',
        f'<image href="{avatar}" x="{cx - r}" y="{cy - r}" width="{2 * r}" height="{2 * r}" clip-path="url(#avatar)"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{GLOW}" stroke-opacity="0.6" stroke-width="2"/>',
    ]

    x = cx + r + 40
    out.append(f'<text x="{x}" y="88" font-size="46" font-weight="700" fill="url(#name)">{esc(user["name"] or user["login"])}</text>')
    languages = " · ".join(name for name, _, _ in STACK["Languages"])
    out.append(f'<text x="{x}" y="118" font-size="16" fill="{t["muted"]}">{esc(languages)}</text>')

    since = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00")).strftime("%b %Y")
    domain = HOMEPAGE.split("://", 1)[1]
    for name, label, color in (("link", domain, t["title"]), ("history", f"On GitHub since {since}", t["muted"])):
        elements, width = pill(x, 136, name, label, color, t)
        out += elements
        x += width + 10

    return card(WIDTH, HEIGHT, theme, out, f"{user['name'] or user['login']} · {domain}")


def main():
    raw, _ = fetch("https://api.github.com/user")
    user = json.loads(raw)
    image, mime = fetch(user["avatar_url"] + "&s=256")
    # Embedded, because SVGs shown through <img> can't load external images.
    avatar = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    write("assets/cards/header", lambda theme: render(theme, user, avatar))


if __name__ == "__main__":
    main()
