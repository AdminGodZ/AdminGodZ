"""Project tiers by lines of code: the tier list, counting a repo's lines and drawing tier emblems.

Each tier adds one effect to its project cards on top of the ones below it:
  Bronze    medal emblem
  Silver    a glint sweeps across the emblem
  Gold      gold-tinted border
  Platinum  a light sweeps around the border in the tier colour
  Diamond   sparkles around the emblem
  Ruby      full-width card with a slowly breathing glow
"""
import json
import math
import subprocess
import tempfile

# (name, fewest lines of code, (light, main, dark) colours, emblem shape), biggest first.
TIERS = [
    ("Ruby", 100_000, ("#ff9bb0", "#ff4d6d", "#b3123a"), "gem"),
    ("Diamond", 20_000, ("#d6ecff", "#79c0ff", "#2f81f7"), "gem"),
    ("Platinum", 10_000, ("#c4fff7", "#56d4c8", "#1b8f86"), "crest"),
    ("Gold", 2_500, ("#fff1b3", "#e3b341", "#9e6a03"), "medal"),
    ("Silver", 1_000, ("#f4f7fa", "#b4c0cc", "#6e7b88"), "medal"),
    ("Bronze", 1, ("#f2c29b", "#cd8a55", "#8a4b20"), "medal"),
]
RUBY, DIAMOND, PLATINUM, GOLD, SILVER, BRONZE = range(len(TIERS))

# Left out of the count: dependencies, build output and data or prose rather than code.
EXCLUDE_DIRS = "node_modules,vendor,dist,build,.next,target"
EXCLUDE_LANGS = "JSON,YAML,Markdown,SVG,XML,CSV,Text,TOML,INI,diff"

SHAPES = {
    "gem": ('<path d="M6 3h12l4 6-10 13L2 9z" fill="url(#{g})"/>',
            '<path d="M2 9h20M6 3l3 6 3-6 3 6 3-6M9 9l3 13 3-13" {line}/>'),
    "crest": ('<path d="M12 2l9 5v10l-9 5-9-5V7z" fill="url(#{g})"/>',
              '<path d="M12 6l5.5 3v6L12 18l-5.5-3V9z" {line}/>'),
    "medal": ('<circle cx="12" cy="12" r="9.5" fill="url(#{g})"/>',
              '<circle cx="12" cy="12" r="6.5" {line}/><path d="M12 8.2l1.1 2.4 2.5.2-1.9 1.7.6 2.5L12 13.7 9.7 15l.6-2.5-1.9-1.7 2.5-.2z" '
              'fill="#fff" fill-opacity=".75"/>'),
}
OUTLINES = {"gem": '<path transform="{t}" d="M6 3h12l4 6-10 13L2 9z"/>', "crest": '<path transform="{t}" d="M12 2l9 5v10l-9 5-9-5V7z"/>',
            "medal": '<circle transform="{t}" cx="12" cy="12" r="9.5"/>'}


def tier_of(lines):
    """Index into TIERS for a repo with this many lines of code, or None without any code."""
    return next((i for i, tier in enumerate(TIERS) if lines >= tier[1]), None)


def progress(tier, lines):
    """How far through its tier a repo is (0 to 1, on a log scale) and what's next, e.g. '4.2k to Diamond'."""
    if tier == RUBY:
        return 1.0, "Top tier"
    low, high = TIERS[tier][1], TIERS[tier - 1][1]
    share = math.log(max(lines, low) / low) / math.log(high / low)
    return share, f"{compact(high - lines)} to {TIERS[tier - 1][0]}"


def compact(n):
    return f"{n / 1000:.1f}".rstrip("0").rstrip(".") + "k" if n >= 1000 else str(n)


def range_label(tier):
    low = TIERS[tier][1]
    if tier == RUBY:
        return f"{compact(low)}+ lines"
    return f"{compact(low)}–{compact(TIERS[tier - 1][1])} lines"


def text_color(tier, theme):
    """The tier's colour for text: its main colour on dark, the darker one on light backgrounds."""
    light, main, dark = TIERS[tier][2]
    return main if theme == "dark" else dark


def count_lines(clone_url):
    """Lines of code in the repo's default branch, counted with cloc on a shallow clone."""
    with tempfile.TemporaryDirectory() as folder:
        subprocess.run(["git", "clone", "--quiet", "--depth", "1", clone_url, folder], check=True)
        result = subprocess.run(
            ["cloc", "--vcs=git", "--quiet", "--json", f"--exclude-dir={EXCLUDE_DIRS}", f"--exclude-lang={EXCLUDE_LANGS}", "."],
            cwd=folder, capture_output=True, text=True, check=True,
        )
    return json.loads(result.stdout).get("SUM", {}).get("code", 0) if result.stdout.strip() else 0


def emblem(tier, x, y, size, uid):
    """The tier's emblem with its top-left corner at x, y. uid keeps its gradient id unique in the SVG."""
    light, main, dark = TIERS[tier][2]
    shape = TIERS[tier][3]
    g = f"emblem{uid}"
    line = 'stroke="#fff" stroke-opacity=".5" stroke-width=".8" fill="none" stroke-linejoin="round"'
    fill, detail = SHAPES[shape]
    return (
        f'<linearGradient id="{g}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{light}"/>'
        f'<stop offset=".55" stop-color="{main}"/><stop offset="1" stop-color="{dark}"/></linearGradient>'
        f'<g transform="translate({x:g} {y:g}) scale({size / 24:g})">{fill.format(g=g)}{detail.format(line=line)}</g>'
    )


def emblem_outline(tier, x, y, size):
    """The emblem's outer shape, for clipping a glint to it (clip paths can't hold groups)."""
    return OUTLINES[TIERS[tier][3]].format(t=f"translate({x:g} {y:g}) scale({size / 24:g})")
