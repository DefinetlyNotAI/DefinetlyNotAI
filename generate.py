import datetime as dt
import html
import json
import os
import re
import urllib.request
from collections import Counter
from pathlib import Path

USER = "DefinetlyNotAI"
TOKEN = os.environ["GITHUB_TOKEN"]
HEADERS = {"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-readme"}


def graphql(query, variables=None):
    req = urllib.request.Request("https://api.github.com/graphql", data=json.dumps({"query": query, "variables": variables or {}}).encode(), headers={**HEADERS, "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def profile_data():
    query = """query($login:String!){user(login:$login){createdAt followers{totalCount} repositories(first:100,ownerAffiliations:OWNER,privacy:PUBLIC){totalCount nodes{nameWithOwner stargazerCount defaultBranchRef{target{... on Commit{oid history(first:100){nodes{oid additions deletions committedDate author{user{login}}} pageInfo{hasNextPage endCursor}}}}} languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}}}}}}"""
    return graphql(query, {"login": USER})["user"]


def extra_commits(repo, cursor):
    owner, name = repo.split("/", 1)
    query = """query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){defaultBranchRef{target{... on Commit{history(first:100,after:$cursor){nodes{oid additions deletions committedDate author{user{login}}} pageInfo{hasNextPage endCursor}}}}}}}"""
    return graphql(query, {"owner": owner, "name": name, "cursor": cursor})["repository"]["defaultBranchRef"]["target"]["history"]


def rank_data():
    try:
        req = urllib.request.Request(f"https://user-badge.committers.top/jordan/{USER}.svg", headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=20).read().decode()
        match = re.search(r"(?:rank|#)\s*(\d+)(?:st|nd|rd|th)?", raw, re.I)
        rank = int(match.group(1)) if match else None
    except Exception:
        rank = None
    colors = {1: "#d4af37", 2: "#a7b0b8", 3: "#cd7f32"}
    return (f"#{rank}" if rank else "unavailable"), colors.get(rank, "#58a6ff")


def streak(days):
    active = sorted(set(days))
    if not active:
        return 0, "No public commits"
    best_start = best_end = run_start = previous = active[0]
    for day in active[1:]:
        if (day - previous).days != 1:
            if (previous - run_start).days > (best_end - best_start).days:
                best_start, best_end = run_start, previous
            run_start = day
        previous = day
    if (previous - run_start).days > (best_end - best_start).days:
        best_start, best_end = run_start, previous
    return (best_end - best_start).days + 1, f"{best_start:%d %b %Y} - {best_end:%d %b %Y}"


def collect():
    user = profile_data()
    additions = deletions = commits = stars = 0
    languages = Counter()
    commit_days = []
    for repo in user["repositories"]["nodes"]:
        stars += repo["stargazerCount"]
        for edge in repo["languages"]["edges"]:
            languages[edge["node"]["name"]] += edge["size"]
        branch = repo.get("defaultBranchRef")
        if not branch:
            continue
        history = branch["target"]["history"]
        while True:
            for commit in history["nodes"]:
                author = commit.get("author") or {}
                github_user = (author.get("user") or {}).get("login", "")
                if github_user.lower() == USER.lower():
                    commits += 1
                    additions += commit["additions"]
                    deletions += commit["deletions"]
                    commit_days.append(dt.date.fromisoformat(commit["committedDate"][:10]))
            if not history["pageInfo"]["hasNextPage"]:
                break
            history = extra_commits(repo["nameWithOwner"], history["pageInfo"]["endCursor"])
    created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    delta = dt.datetime.now(dt.timezone.utc) - created
    years, rem = divmod(delta.days, 365)
    months, days = divmod(rem, 30)
    streak_days, streak_range = streak(commit_days)
    rank, rank_color = rank_data()
    total_lang = sum(languages.values()) or 1
    language_text = ", ".join(f"{name} {size / total_lang:.0%}" for name, size in languages.most_common(5))
    return {"uptime": f"{years} years, {months} months, {days} days", "repos": user["repositories"]["totalCount"], "followers": user["followers"]["totalCount"], "stars": stars, "commits": commits, "additions": additions, "deletions": deletions, "loc": additions - deletions, "languages": language_text, "streak_days": streak_days, "streak_range": streak_range, "rank": rank, "rank_color": rank_color}


def svg(data, dark):
    bg, panel, text, muted, accent = ("#0d1117", "#161b22", "#e6edf3", "#8b949e", "#7ee787") if dark else ("#ffffff", "#f6f8fa", "#1f2328", "#656d76", "#1a7f37")
    esc = lambda value: html.escape(f"{value:,}" if isinstance(value, int) else str(value))
    rows = [
        ("Uptime", data["uptime"], accent), ("IDE", "WebStorm, CLion, PyCharm", text),
        ("Languages.Programming", data["languages"], text), ("Languages.Real", "English, Arabic", text),
        ("Hobbies.Software", "AI/Game Experiments, Hacking Tools", text), ("Hobbies.Hardware", "Robotics", text),
    ]
    stats = [("Repositories", data["repos"], text), ("Commits", data["commits"], text), ("Lines of Code", data["loc"], text), ("++ additions", data["additions"], "#3fb950"), ("-- deletions", data["deletions"], "#f85149"), ("Total Stars", data["stars"], text), ("Followers", data["followers"], text), ("Longest Streak", f'{data["streak_days"]} days', accent), ("Streak Range", data["streak_range"], muted), ("Jordan Rank", data["rank"], data["rank_color"])]
    ascii_art = ["      .--------.", "  .---|  01 10 |---.", "  |   '--------'   |", "--+--[ SHAHM.EXE ]-+--", "  |  AI / WEB / HW |", "  '---o--------o---'"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="640" viewBox="0 0 1000 640"><rect width="1000" height="640" rx="18" fill="{bg}"/><style>text{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:15px}}.title{{font-size:25px;font-weight:700}}.label{{fill:{muted}}}</style>', f'<rect x="24" y="24" width="952" height="592" rx="14" fill="{panel}" stroke="{muted}" stroke-opacity=".35"/><text x="55" y="68" class="title" fill="{accent}">Shahm Najeeb</text><text x="55" y="94" fill="{muted}">@{USER} / profile --live</text>']
    for i, line in enumerate(ascii_art): out.append(f'<text x="55" y="{145+i*25}" fill="{accent}">{html.escape(line)}</text>')
    for i, (label, value, color) in enumerate(rows): out.append(f'<text x="355" y="{145+i*34}" class="label">{label}</text><text x="565" y="{145+i*34}" fill="{color}">{esc(value)}</text>')
    out.append(f'<line x1="55" y1="325" x2="945" y2="325" stroke="{muted}" stroke-opacity=".35"/><text x="55" y="365" class="title" fill="{accent}">GitHub Stats</text>')
    for i, (label, value, color) in enumerate(stats):
        x = 55 if i < 5 else 535; y = 405 + (i % 5) * 37
        out.append(f'<text x="{x}" y="{y}" class="label">{label}</text><text x="{x+190}" y="{y}" fill="{color}">{esc(value)}</text>')
    out.append(f'<text x="55" y="602" fill="{muted}">Updated daily by GitHub Actions</text></svg>')
    return "".join(out)


if __name__ == "__main__":
    data = collect()
    Path("dark_mode.svg").write_text(svg(data, True), encoding="utf-8")
    Path("light_mode.svg").write_text(svg(data, False), encoding="utf-8")
