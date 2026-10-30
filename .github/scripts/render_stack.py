#!/usr/bin/env python3
"""Render the stack card (assets/cards/stack-*.svg). Edit STACK to change what it shows."""
from cards import PAD, THEMES, card, esc, icon, title, write

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
ROW = 32


def render(theme):
    t = THEMES[theme]
    out = [title("Stack", t)]
    column = (WIDTH - 2 * PAD) / len(STACK)
    for i, (group, items) in enumerate(STACK.items()):
        x = PAD + i * column
        out.append(f'<text x="{x:.0f}" y="80" font-size="13" fill="{t["muted"]}">{esc(group)}</text>')
        for j, (name, logo, color) in enumerate(items):
            y = 112 + j * ROW
            if isinstance(color, tuple):
                color = color[0] if theme == "dark" else color[1]
            out.append(icon(logo, x, y - 15, color or t["text"], 20))
            out.append(f'<text x="{x + 32:.0f}" y="{y}" font-size="15" font-weight="500" fill="{t["text"]}">{esc(name)}</text>')
    height = 112 + (max(map(len, STACK.values())) - 1) * ROW + 30
    label = "; ".join(f"{group}: {', '.join(name for name, _, _ in items)}" for group, items in STACK.items())
    return card(WIDTH, height, theme, out, f"Stack. {label}")


if __name__ == "__main__":
    write("assets/cards/stack", render)
