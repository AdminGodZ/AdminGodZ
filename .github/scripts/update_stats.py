#!/usr/bin/env python3
"""Render the overview card (assets/cards/overview-*.svg) from the GitHub API.

Counts commits, merged PRs, lines added, repos, and the top languages (weighted by
how many lines you added in each repo). Needs a token in GH_TOKEN that can read
your private repos, otherwise only public activity is counted.
"""
import json
import os
import sys
import time
import urllib.request
from collections import Counter

from cards import PAD, THEMES, card, esc, icon, language_bar, language_color, legend, title, write

API = "https://api.github.com"
TOKEN = os.environ["GH_TOKEN"]
WIDTH, HEIGHT = 880, 228

def request(path, body=None):
    req = urllib.request.Request(
        path if path.startswith("http") else API + path,
        data=json.dumps(body).encode() if body else None,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req) as res:
        raw = res.read()
        return res.status, json.loads(raw) if raw else None


def graphql(query, **variables):
    _, data = request("/graphql", {"query": query, "variables": variables})
    if data.get("errors"):
        sys.exit(f"GraphQL error: {data['errors']}")
    return data["data"]


def paginate(query, path, **variables):
    cursor = None
    while True:
        data = graphql(query, cursor=cursor, **variables)
        for key in path:
            data = data[key]
        yield from data["nodes"]
        if not data["pageInfo"]["hasNextPage"]:
            return
        cursor = data["pageInfo"]["endCursor"]


def collect_repos(login):
    """Repos you own, recently contributed to, or merged a PR into (forks skipped to avoid double counting).

    Returns the repo names and GitHub's colour for every language seen in them.
    """
    repos, colors = {}, {}
    fields = "nameWithOwner isFork languages(first: 20) { nodes { name color } }"
    owned = f"""query($cursor: String) {{ viewer {{ repositories(first: 100, after: $cursor, ownerAffiliations: OWNER) {{
        pageInfo {{ hasNextPage endCursor }} nodes {{ {fields} }} }} }} }}"""
    contributed = f"""query($cursor: String) {{ viewer {{ repositoriesContributedTo(first: 100, after: $cursor,
        includeUserRepositories: true, contributionTypes: [COMMIT, PULL_REQUEST]) {{
        pageInfo {{ hasNextPage endCursor }} nodes {{ {fields} }} }} }} }}"""
    merged = f"""query($cursor: String, $q: String!) {{ search(query: $q, type: ISSUE, first: 100, after: $cursor) {{
        pageInfo {{ hasNextPage endCursor }} nodes {{ ... on PullRequest {{ repository {{ {fields} }} }} }} }} }}"""

    def add(repo):
        repos[repo["nameWithOwner"]] = repo["isFork"]
        for language in repo["languages"]["nodes"]:
            colors[language["name"]] = language["color"]

    for node in paginate(owned, ["viewer", "repositories"]):
        add(node)
    for node in paginate(contributed, ["viewer", "repositoriesContributedTo"]):
        add(node)
    for node in paginate(merged, ["search"], q=f"author:{login} is:pr is:merged"):
        add(node["repository"])
    return sorted(name for name, is_fork in repos.items() if not is_fork), colors


def contributor_stats(repo, login):
    """Return (commits, lines added) by login on the repo's default branch."""
    # The stats endpoint answers 202 while GitHub computes it in the background.
    for _ in range(10):
        status, data = request(f"/repos/{repo}/stats/contributors")
        if status == 200:
            for contributor in data or []:
                if (contributor.get("author") or {}).get("login", "").lower() == login.lower():
                    return contributor["total"], sum(week["a"] for week in contributor["weeks"])
            return 0, 0
        if status == 204:
            return 0, 0
        time.sleep(3)
    print(f"warning: stats for {repo} still not ready, skipping", file=sys.stderr)
    return 0, 0


def compact(n):
    for size, suffix in ((1_000_000, "M"), (1_000, "k")):
        if n >= size:
            return f"{n / size:.1f}".rstrip("0").rstrip(".") + suffix
    return str(n)


def render(theme, metrics, langs):
    t = THEMES[theme]
    out = [title("Overview", t)]

    # One column per number: icon and label on top, the value large underneath.
    column = (WIDTH - 2 * PAD) / len(metrics)
    for i, (name, label, value) in enumerate(metrics):
        x = PAD + i * column
        out.append(icon(name, x, 68, t["muted"]))
        out.append(f'<text x="{x + 20:.0f}" y="80" font-size="13" fill="{t["muted"]}">{esc(label)}</text>')
        out.append(f'<text x="{x:.0f}" y="118" font-size="30" font-weight="700" fill="{t["text"]}">{esc(value)}</text>')

    out.append(f'<line x1="{PAD}" y1="142" x2="{WIDTH - PAD}" y2="142" stroke="{t["border"]}"/>')
    out.append(f'<text x="{PAD}" y="170" font-size="13" fill="{t["muted"]}">Top languages</text>')
    out += language_bar(langs, PAD, 182, WIDTH - 2 * PAD, t, height=10)
    out += legend(langs, PAD, 214, t, size=13)

    label = ", ".join(f"{value} {label.lower()}" for _, label, value in metrics)
    return card(WIDTH, HEIGHT, theme, out, f"Overview: {label}")


def main():
    login = graphql("{ viewer { login } }")["viewer"]["login"]
    repos, colors = collect_repos(login)

    merged_prs = graphql(
        "query($q: String!) { search(query: $q, type: ISSUE, first: 1) { issueCount } }",
        q=f"author:{login} is:pr is:merged",
    )["search"]["issueCount"]

    total_commits = 0
    total_lines = 0
    languages = Counter()
    for repo in repos:
        commits, added = contributor_stats(repo, login)
        total_commits += commits
        if not added:
            continue
        total_lines += added
        _, bytes_by_language = request(f"/repos/{repo}/languages")
        repo_total = sum(bytes_by_language.values())
        for language, size in bytes_by_language.items():
            languages[language] += added * size / repo_total
        print(f"{repo}: {commits} commits, +{added}", file=sys.stderr)

    # Top five languages, with the rest grouped into "Other".
    language_total = sum(languages.values()) or 1
    langs = [
        (name, language_color(name, colors.get(name)), weight / language_total)
        for name, weight in languages.most_common(5)
    ]
    rest = 1 - sum(share for _, _, share in langs)
    if rest >= 0.005:
        langs.append(("Other", language_color("Other", None), rest))

    metrics = [
        ("commit", "Commits", compact(total_commits)),
        ("merge", "PRs merged", compact(merged_prs)),
        ("code", "Lines pushed", compact(total_lines)),
        ("repo", "Repositories", str(len(repos))),
    ]
    write("assets/cards/overview", lambda theme: render(theme, metrics, langs))
    print(f"{total_commits} commits, {merged_prs} merged PRs, {total_lines} lines, {len(repos)} repos, "
          f"top: {languages.most_common(5)}", file=sys.stderr)


if __name__ == "__main__":
    main()
