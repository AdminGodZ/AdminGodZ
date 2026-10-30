#!/usr/bin/env python3
"""Regenerate the stats block in README.md from the GitHub API.

Counts commits, merged PRs, lines added, and the top languages (weighted by how many
lines you added in each repo). Needs a token in GH_TOKEN that can read your
private repos, otherwise only public activity is counted.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter

API = "https://api.github.com"
TOKEN = os.environ["GH_TOKEN"]
README = os.environ.get("README", "README.md")

# shields.io colour + simple-icons slug per language; anything else falls back to grey.
LANGUAGES = {
    "TypeScript": ("3178C6", "typescript"),
    "JavaScript": ("F7DF1E", "javascript"),
    "Rust": ("000000", "rust"),
    "Python": ("3670A0", "python"),
    "C++": ("00599C", "cplusplus"),
    "Java": ("ED8B00", "openjdk"),
    "CSS": ("1572B6", "css3"),
    "HTML": ("E34F26", "html5"),
    "PLpgSQL": ("4169E1", "postgresql"),
    "Shell": ("4EAA25", "gnubash"),
    "PowerShell": ("5391FE", "powershell"),
    "Astro": ("BC52EE", "astro"),
}


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
    """Repos you own, recently contributed to, or merged a PR into (forks skipped to avoid double counting)."""
    repos = {}
    owned = """query($cursor: String) { viewer { repositories(first: 100, after: $cursor, ownerAffiliations: OWNER) {
        pageInfo { hasNextPage endCursor } nodes { nameWithOwner isFork } } } }"""
    contributed = """query($cursor: String) { viewer { repositoriesContributedTo(first: 100, after: $cursor,
        includeUserRepositories: true, contributionTypes: [COMMIT, PULL_REQUEST]) {
        pageInfo { hasNextPage endCursor } nodes { nameWithOwner isFork } } } }"""
    merged = """query($cursor: String, $q: String!) { search(query: $q, type: ISSUE, first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor } nodes { ... on PullRequest { repository { nameWithOwner isFork } } } } }"""

    for node in paginate(owned, ["viewer", "repositories"]):
        repos[node["nameWithOwner"]] = node["isFork"]
    for node in paginate(contributed, ["viewer", "repositoriesContributedTo"]):
        repos[node["nameWithOwner"]] = node["isFork"]
    for node in paginate(merged, ["search"], q=f"author:{login} is:pr is:merged"):
        repo = node["repository"]
        repos[repo["nameWithOwner"]] = repo["isFork"]
    return sorted(name for name, is_fork in repos.items() if not is_fork)


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


def badge(label, message, color, logo):
    def escape(text):
        return urllib.parse.quote(text.replace("-", "--").replace("_", "__").replace(" ", "_"))

    url = f"https://img.shields.io/badge/{escape(label)}-{escape(message)}-{color}?style=for-the-badge&logo={logo}&logoColor=white"
    return f'<img alt="{label}: {message}" src="{url}" />'


def main():
    login = graphql("{ viewer { login } }")["viewer"]["login"]
    repos = collect_repos(login)

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

    language_total = sum(languages.values()) or 1
    top = [
        badge(language, f"{weight / language_total:.0%}", *LANGUAGES.get(language, ("555555", "")))
        for language, weight in languages.most_common(3)
    ]

    block = "\n".join([
        "<!-- STATS:START -->",
        '<p align="center">',
        "  " + badge("Commits", compact(total_commits), "F05032", "git"),
        "  " + badge("PRs merged", str(merged_prs), "8957E5", "github"),
        "  " + badge("Lines pushed", compact(total_lines), "2EA44F", "github"),
        "</p>",
        '<p align="center">',
        *("  " + b for b in top),
        "</p>",
        "<!-- STATS:END -->",
    ])

    with open(README) as f:
        readme = f.read()
    updated = re.sub(r"<!-- STATS:START -->.*?<!-- STATS:END -->", lambda _: block, readme, flags=re.S)
    with open(README, "w") as f:
        f.write(updated)
    print(f"{total_commits} commits, {merged_prs} merged PRs, {total_lines} lines, top: {languages.most_common(3)}", file=sys.stderr)


if __name__ == "__main__":
    main()
