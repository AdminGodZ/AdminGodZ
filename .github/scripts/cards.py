"""Drawing helpers shared by the README cards: themes, icons, text layout and the card frame.

Every card is written twice, as <name>-dark.svg and <name>-light.svg, and shown
through a <picture> element so GitHub picks the one matching the visitor's theme.
"""
import functools
import html
import os
import re

ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
PAD = 24
# Transparent space around every card, so two half-width cards line up with a full-width one.
MARGIN = 6
HALF, FULL = "49.9%", "99.8%"

# GitHub's own language colours, except Rust, which is orange like the rest of the Rust branding.
COLOR_OVERRIDES = {"Rust": "#F74C00"}
OTHER_COLOR = "#8b949e"

THEMES = {
    "dark": {
        "bg": "#161b22", "border": "#30363d", "title": "#58a6ff", "text": "#e6edf3",
        "muted": "#8b949e", "track": "#30363d", "live": "#3fb950", "accent": "#a371f7",
        # Contribution calendar, from no contributions to the most.
        "levels": ["#21262d", "#3a2d63", "#5a3fa0", "#8a63d2", "#c4a5ff"],
    },
    "light": {
        "bg": "#ffffff", "border": "#d0d7de", "title": "#0969da", "text": "#1f2328",
        "muted": "#59636e", "track": "#eaeef2", "live": "#1a7f37", "accent": "#8250df",
        "levels": ["#eff2f5", "#e0d4fb", "#c0a3f3", "#9365e0", "#6639ba"],
    },
}

# Animations shared by every animated card. They play once when the README loads, apart from
# the ambient ones (pulse, glows), and are switched off for visitors who ask for reduced motion.
# Never put an animated class on an element that has its own transform attribute: the CSS
# transform would replace it. Wrap such elements in a <g> instead.
#   in     fade and slide up       grow   grow from the left edge
#   pulse  ripple ring, forever    motion hidden when motion is reduced (for SMIL animations)
ANIMATIONS = """
.in{animation:fade-up .8s cubic-bezier(.2,.7,.2,1) backwards}
@keyframes fade-up{from{opacity:0;transform:translateY(10px)}}
.grow{transform-box:fill-box;transform-origin:left;animation:grow 1.4s cubic-bezier(.2,.8,.2,1) backwards}
@keyframes grow{from{transform:scaleX(0)}}
.pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2s ease-out infinite}
@keyframes pulse{from{transform:scale(1);opacity:.7}to{transform:scale(3.2);opacity:0}}
"""
REDUCED_MOTION = "@media (prefers-reduced-motion:reduce){*{animation:none!important}.motion{display:none}}"

esc = html.escape


def delay(seconds):
    """Attribute that starts an element's animation later, for staggered entrances."""
    return f' style="animation-delay:{seconds:.2f}s"'


def live_dot(cx, cy, r, color):
    """A dot with a ring rippling out of it."""
    return (f'<circle class="pulse" cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="{color}"/>'
            f'<circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="{color}"/>')


def language_color(name, color):
    return COLOR_OVERRIDES.get(name, color or OTHER_COLOR)


@functools.cache
def _icon(name):
    with open(os.path.join(ICON_DIR, f"{name}.svg")) as f:
        svg = f.read()
    view_box = float(re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))
    return view_box, re.search(r' d="([^"]+)"', svg).group(1)


def icon(name, x, y, color, size=14):
    """Octicons (MIT) and Simple Icons (CC0) from the icons/ folder, scaled to size px."""
    view_box, path = _icon(name)
    return f'<path transform="translate({x:g} {y:g}) scale({size / view_box:g})" fill="{color}" d="{path}"/>'


def text_width(text, size):
    """Rough rendered width of text in a sans-serif font, erring on the wide side."""
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
    return width * size * 1.1


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


def ellipsize(text, size, max_width):
    """text, cut short with an ellipsis if it would be wider than max_width."""
    if text_width(text, size) <= max_width:
        return text
    while text and text_width(text + "…", size) > max_width:
        text = text[:-1]
    return text.rstrip(" -_") + "…"


def title(text, t):
    return f'<text x="{PAD}" y="42" font-size="16" font-weight="600" fill="{t["text"]}">{esc(text)}</text>'


def language_bar(langs, x, y, width, t, height=8, start=0.0, sheen=False):
    """Stacked bar of (name, colour, share) tuples on a rounded track, growing in from the left.

    With sheen, a soft highlight sweeps across it every few seconds.
    """
    out = [
        f'<clipPath id="bar{y}"><rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{height / 2:g}"/></clipPath>',
        f'<g clip-path="url(#bar{y})"><rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{t["track"]}"/>',
        f'<g class="grow"{delay(start)}>',
    ]
    left = x
    for _, color, share in langs:
        out.append(f'<rect x="{x:.1f}" y="{y}" width="{share * width + 0.5:.1f}" height="{height}" fill="{color}"/>')
        x += share * width
    out.append("</g>")
    if sheen:
        out.append(
            f'<linearGradient id="sheen{y}"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
            f'<stop offset=".5" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
            f'<style>.sheen{y}{{animation:sheen{y} 4.5s ease-in-out {start + 1.6:.1f}s infinite}}'
            f'@keyframes sheen{y}{{0%{{transform:translateX(0)}}40%,100%{{transform:translateX({width + 200:.0f}px)}}}}</style>'
            f'<rect class="sheen{y}" x="{left - 120}" y="{y}" width="80" height="{height}" fill="url(#sheen{y})"/>'
        )
    out.append("</g>")
    return out


def legend(langs, x, y, t, size=12, start=0.0):
    """Coloured dot, name and share for each language, laid out left to right and fading in one by one."""
    out = []
    for i, (name, color, share) in enumerate(langs):
        percent = f"{share:.0%}" if share >= 0.005 else ""
        out.append(f'<g class="in"{delay(start + i * 0.08)}><circle cx="{x + 4}" cy="{y - 4}" r="4" fill="{color}"/>'
                   f'<text x="{x + 13}" y="{y}" font-size="{size}" fill="{t["text"]}">{esc(name)} '
                   f'<tspan fill="{t["muted"]}">{percent}</tspan></text></g>')
        x += 13 + text_width(f"{name} {percent}", size) + 18
    return out


def card(width, height, theme, body, label, css=None):
    """A rounded card of the given inner size around body, as a complete SVG document.

    Pass css (even empty) to animate the card: it gets the shared ANIMATIONS plus css.
    """
    t = THEMES[theme]
    outer_w, outer_h = width + 2 * MARGIN, height + 2 * MARGIN
    style = [f"<style>{ANIMATIONS}{css}{REDUCED_MOTION}</style>"] if css is not None else []
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{outer_w}" height="{outer_h}" '
        f'viewBox="0 0 {outer_w} {outer_h}" role="img" aria-label="{esc(label)}">',
        f"<title>{esc(label)}</title>",
        *style,
        f'<g transform="translate({MARGIN} {MARGIN})">',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{t["bg"]}" stroke="{t["border"]}"/>',
        f'<g font-family="{FONT}">',
        *body,
        "</g>",
        "</g>",
        "</svg>",
    ]) + "\n"


def write(path, render):
    """Write render(theme) to <path>-dark.svg and <path>-light.svg."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for theme in THEMES:
        with open(f"{path}-{theme}.svg", "w") as f:
            f.write(render(theme))


def picture(path, alt, width, href=None):
    """README markup showing the dark or light card depending on the visitor's theme."""
    tag = (
        f'<picture><source media="(prefers-color-scheme: dark)" srcset="{path}-dark.svg" />'
        f'<img alt="{esc(alt)}" src="{path}-light.svg" width="{width}" /></picture>'
    )
    return f'<a href="{href}">{tag}</a>' if href else tag
