#!/usr/bin/env python3
"""Render the stack card (assets/cards/stack-*.svg). Edit STACK to change what it shows.

Every item is a tile tinted with its brand colour. The tiles fade in column by column, the logos
pop in, and every few seconds a light ripples across all of them.
"""
from cards import PAD, THEMES, card, delay, esc, icon, title, write

# (name, icon in icons/, colour). Colour is one value, a (dark, light) pair, or None for the text colour.
STACK = {
    "Devices": [
        ("Arch Linux", "archlinux", "#1793D1"),
        ("macOS", "apple", None),
    ],
    "Languages": [
        ("TypeScript", "typescript", "#3178C6"),
        ("Rust", "rust", "#F74C00"),
        ("Python", "python", ("#FFD43B", "#3776AB")),
    ],
    "Frameworks": [
        ("Next.js", "nextdotjs", None),
        ("React", "react", ("#58C4DC", "#087EA4")),
        ("Actix Web", "actix", "#F74C00"),
    ],
}
WIDTH = 880
GUTTER = 16  # space between columns
TILE_H, ROW = 44, 54
TOP = 96  # top of the first row of tiles
RIPPLE_SECONDS = 9  # how often the light ripples across the tiles

CSS = f"""
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .6s cubic-bezier(.3,1.6,.5,1) backwards}}
@keyframes pop{{from{{transform:scale(0) rotate(-20deg);opacity:0}}}}
.ripple{{animation:ripple {RIPPLE_SECONDS}s ease-in-out infinite}}
"""


def render(theme):
    t = THEMES[theme]
    column = (WIDTH - 2 * PAD + GUTTER) / len(STACK)
    tile_w = column - GUTTER
    out = [
        f'<g class="in">{title("Stack", t)}</g>',
        f'<linearGradient id="light"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="#fff" stop-opacity="{.12 if theme == "dark" else .6}"/>'
        f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>',
        f'<style>@keyframes ripple{{0%{{transform:translateX(0)}}14%,100%{{transform:translateX({tile_w + 160:.0f}px)}}}}</style>',
    ]

    n = 0
    for i, (group, items) in enumerate(STACK.items()):
        x = PAD + i * column
        out.append(f'<text class="in"{delay(0.1 + i * 0.1)} x="{x:.0f}" y="80" font-size="13" '
                   f'fill="{t["muted"]}">{esc(group)}</text>')
        for j, (name, logo, color) in enumerate(items):
            y = TOP + j * ROW
            if isinstance(color, tuple):
                color = color[0] if theme == "dark" else color[1]
            # Logos without a brand colour use the text colour, and a quieter grey for their tile.
            tint = color or t["muted"]
            color = color or t["text"]
            start = 0.2 + i * 0.12 + j * 0.08
            out += [
                f'<clipPath id="tile{n}"><rect x="{x:.1f}" y="{y}" width="{tile_w:.1f}" height="{TILE_H}" rx="10"/></clipPath>',
                f'<g class="in"{delay(start)}>',
                f'<rect x="{x + .5:.1f}" y="{y + .5}" width="{tile_w - 1:.1f}" height="{TILE_H - 1}" rx="10" '
                f'fill="{tint}" fill-opacity=".07" stroke="{tint}" stroke-opacity=".28"/>',
                # Logo on a tinted badge.
                f'<rect x="{x + 8:.1f}" y="{y + 8}" width="28" height="28" rx="7" fill="{tint}" fill-opacity=".14"/>',
                f'<g class="pop"{delay(start + 0.2)}>{icon(logo, x + 13, y + 13, color, 18)}</g>',
                f'<text x="{x + 48:.1f}" y="{y + 27}" font-size="14" font-weight="500" fill="{t["text"]}">{esc(name)}</text>',
                f'<g clip-path="url(#tile{n})"><rect class="ripple" x="{x - 140:.1f}" y="{y}" width="100" height="{TILE_H}" '
                f'fill="url(#light)" style="animation-delay:{2 + n * 0.18:.2f}s"/></g>',
                "</g>",
            ]
            n += 1

    height = TOP + (max(map(len, STACK.values())) - 1) * ROW + TILE_H + PAD
    label = "; ".join(f"{group}: {', '.join(name for name, _, _ in items)}" for group, items in STACK.items())
    return card(WIDTH, height, theme, out, f"Stack. {label}", CSS)


if __name__ == "__main__":
    write("assets/cards/stack", render)
