import datetime as dt
import html
import json
import os
import re
import urllib.request
import urllib.error
import time
from collections import Counter
from pathlib import Path

USER = "DefinetlyNotAI"
TOKEN = os.environ["GITHUB_TOKEN"]
HEADERS = {"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-readme"}


def graphql(query, variables=None):
    req = urllib.request.Request("https://api.github.com/graphql", data=json.dumps({"query": query, "variables": variables or {}}).encode(), headers={**HEADERS, "Content-Type": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                payload = json.load(response)
            if payload.get("errors"):
                raise RuntimeError(payload["errors"])
            return payload["data"]
        except urllib.error.HTTPError as error:
            if error.code not in {502, 503, 504} or attempt == 4:
                detail = error.read().decode("utf-8", "replace")
                raise RuntimeError(f"GitHub GraphQL HTTP {error.code}: {detail}") from error
            time.sleep(2 ** attempt)


def profile_data():
    query = """query($login:String!){user(login:$login){createdAt followers{totalCount} repositories(first:100,ownerAffiliations:OWNER,privacy:PUBLIC){totalCount nodes{nameWithOwner stargazerCount defaultBranchRef{name} languages(first:100,orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}}}}}}"""
    return graphql(query, {"login": USER})["user"]


def repo_history(repo, cursor=None):
    owner, name = repo.split("/", 1)
    query = """query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){defaultBranchRef{target{... on Commit{history(first:100,after:$cursor){nodes{oid additions deletions committedDate author{user{login}}} pageInfo{hasNextPage endCursor}}}}}}}"""
    data = graphql(query, {"owner": owner, "name": name, "cursor": cursor})["repository"]
    return data["defaultBranchRef"]["target"]["history"]


def github_commit_days(created):
    """Return GitHub-recognized commit contribution dates, queried one month at a time."""
    today = dt.datetime.now(dt.timezone.utc)
    cursor = created.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days = set()
    query = """query($login:String!,$start:DateTime!,$end:DateTime!){user(login:$login){contributionsCollection(from:$start,to:$end){commitContributionsByRepository(maxRepositories:100){contributions(first:100){nodes{occurredAt commitCount}}}}}}"""
    while cursor <= today:
        if cursor.month == 12:
            next_month = cursor.replace(year=cursor.year + 1, month=1)
        else:
            next_month = cursor.replace(month=cursor.month + 1)
        period_end = min(next_month - dt.timedelta(seconds=1), today)
        data = graphql(query, {
            "login": USER,
            "start": cursor.isoformat(),
            "end": period_end.isoformat(),
        })["user"]["contributionsCollection"]
        for repository in data["commitContributionsByRepository"]:
            for contribution in repository["contributions"]["nodes"]:
                if contribution["commitCount"] > 0:
                    days.add(dt.date.fromisoformat(contribution["occurredAt"][:10]))
        cursor = next_month
    return sorted(days)


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
        history = repo_history(repo["nameWithOwner"])
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
            history = repo_history(repo["nameWithOwner"], history["pageInfo"]["endCursor"])
    created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    delta = dt.datetime.now(dt.timezone.utc) - created
    years, rem = divmod(delta.days, 365)
    months, days = divmod(rem, 30)
    commit_days = github_commit_days(created)
    streak_days, streak_range = streak(commit_days)
    rank, rank_color = rank_data()
    total_lang = sum(languages.values()) or 1
    language_text = ", ".join(f"{name} {size / total_lang:.0%}" for name, size in languages.most_common(5))
    return {
        "joined": created.strftime("%d %b %Y"),
        "uptime": f"{years} years, {months} months, {days} days",
        "repos": user["repositories"]["totalCount"],
        "followers": user["followers"]["totalCount"],
        "stars": stars,
        "commits": commits,
        "additions": additions,
        "deletions": deletions,
        "loc": additions - deletions,
        "churn": additions + deletions,
        "active_days": len(set(commit_days)),
        "languages": language_text,
        "streak_days": streak_days,
        "streak_range": streak_range,
        "rank": rank,
        "rank_color": rank_color,
    }


def wrap_items(value, max_chars=76):
    items = value.split(", ")
    lines, current = [], ""
    for item in items:
        candidate = f"{current}, {item}" if current else item
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = item
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def svg(data, dark):
    if dark:
        bg, terminal, text = "#05080d", "#0a1018", "#d7e0ea"
        muted, border = "#718096", "#263445"
    else:
        bg, terminal, text = "#edf2f7", "#ffffff", "#17212b"
        muted, border = "#66717e", "#bcc8d4"

    green, cyan = "#39d353", "#2f81f7"
    purple, amber = "#a371f7", "#d29922"
    red, teal = "#f85149", "#2bbac5"
    esc = lambda value: html.escape(f"{value:,}" if isinstance(value, int) else str(value))

    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900" viewBox="0 0 1200 900">',
        f'<rect width="1200" height="900" rx="16" fill="{bg}"/>',
        f'<rect x="20" y="20" width="1160" height="860" rx="12" fill="{terminal}" stroke="{border}"/>',
        f'<circle cx="48" cy="47" r="6" fill="{red}"/><circle cx="68" cy="47" r="6" fill="{amber}"/><circle cx="88" cy="47" r="6" fill="{green}"/>',
        f'<style>text{{font-family:ui-monospace,SFMono-Regular,Consolas,Liberation Mono,monospace;font-size:15px}}'
        f'.head{{font-size:18px;font-weight:700}}.dim{{fill:{muted}}}.small{{font-size:13px}}</style>',
        f'<text x="112" y="53" class="small" fill="{muted}">profile-readme-redesign : bash</text>',
        f'<line x1="20" y1="72" x2="1180" y2="72" stroke="{border}"/>',
        f'<text x="48" y="106" fill="{green}">shahm@github</text><text x="166" y="106" fill="{text}">:</text>'
        f'<text x="178" y="106" fill="{cyan}">~</text><text x="192" y="106" fill="{text}">$ ./profile --live --ascii</text>',
        f'<text x="48" y="137" fill="{muted}">[ok] loading public GitHub activity...</text>',
    ]

    ascii_lines = [
        "+---------------------------------------------+",
        "| SHAHM NAJEEB                                |",
        "| @DefinetlyNotAI                             |",
        "+----------------------+----------------------+",
        "| SOFTWARE             | HARDWARE             |",
        "| AI + GAME EXPERIMENTS| ROBOTICS + EMBEDDED  |",
        "| SECURITY TOOLING     | BUILDING SYSTEMS     |",
        "+----------------------+----------------------+",
        "| INPUT  ->  DESIGN  ->  BUILD  ->  SHIP      |",
        "+---------------------------------------------+",
    ]
    for i, line in enumerate(ascii_lines):
        color = green if i in {0, 3, 7, 9} else (cyan if i in {1, 2} else text)
        out.append(f'<text x="48" y="{180 + i*24}" fill="{color}">{html.escape(line)}</text>')

    info = [
        ("joined", data["joined"], amber),
        ("uptime", data["uptime"], green),
        ("ides", "WebStorm, CLion, PyCharm", cyan),
        ("languages.real", "English, Arabic", purple),
        ("focus.software", "AI, games, security tools", teal),
        ("focus.hardware", "Robotics, embedded systems", amber),
        ("scope", "public GitHub repositories", muted),
        ("refresh", "weekly", muted),
    ]
    out.append(f'<text x="650" y="180" class="head" fill="{purple}">profile.info</text>')
    for i, (label, value, color) in enumerate(info):
        y = 216 + i * 31
        dots = "." * max(2, 22 - len(label))
        out.append(f'<text x="650" y="{y}" fill="{muted}">{label} {dots}</text>')
        out.append(f'<text x="872" y="{y}" fill="{color}">{esc(value)}</text>')

    lang_y = 444
    out.append(f'<text x="48" y="{lang_y}" fill="{green}">shahm@github</text><text x="166" y="{lang_y}" fill="{text}">:</text>'
               f'<text x="178" y="{lang_y}" fill="{cyan}">~</text><text x="192" y="{lang_y}" fill="{text}">$ languages --all --by-bytes</text>')
    language_lines = wrap_items(data["languages"])
    for i, line in enumerate(language_lines):
        prefix = "|-- " if i == 0 else "|   "
        out.append(f'<text x="48" y="{lang_y + 30 + i*23}" fill="{cyan}">{prefix}</text>')
        out.append(f'<text x="88" y="{lang_y + 30 + i*23}" fill="{text}">{esc(line)}</text>')

    stats_y = lang_y + 62 + len(language_lines) * 23
    out.append(f'<text x="48" y="{stats_y}" fill="{green}">shahm@github</text><text x="166" y="{stats_y}" fill="{text}">:</text>'
               f'<text x="178" y="{stats_y}" fill="{cyan}">~</text><text x="192" y="{stats_y}" fill="{text}">$ github-stats --verbose</text>')

    left_stats = [
        ("repositories", data["repos"], cyan),
        ("commits", data["commits"], purple),
        ("total_stars", data["stars"], amber),
        ("followers", data["followers"], teal),
        ("active_commit_days", data["active_days"], green),
    ]
    right_stats = [
        ("net_lines", data["loc"], text),
        ("additions", f'+{data["additions"]:,}', green),
        ("deletions", f'-{data["deletions"]:,}', red),
        ("code_churn", data["churn"], cyan),
        ("jordan_rank", data["rank"], data["rank_color"]),
    ]
    for column, values in enumerate((left_stats, right_stats)):
        x = 48 + column * 576
        for i, (label, value, color) in enumerate(values):
            y = stats_y + 34 + i * 28
            dots = "." * max(2, 24 - len(label))
            out.append(f'<text x="{x}" y="{y}" fill="{muted}">|-- {label} {dots}</text>')
            out.append(f'<text x="{x+300}" y="{y}" fill="{color}">{esc(value)}</text>')

    streak_y = stats_y + 192
    out.append(f'<text x="48" y="{streak_y}" fill="{muted}">|-- longest_commit_streak ........</text>')
    out.append(f'<text x="348" y="{streak_y}" fill="{green}">{esc(data["streak_days"])} days</text>')
    out.append(f'<text x="468" y="{streak_y}" fill="{muted}">[{esc(data["streak_range"])}]</text>')
    out.append(f'<text x="48" y="{streak_y+42}" fill="{green}">shahm@github</text><text x="166" y="{streak_y+42}" fill="{text}">:</text>'
               f'<text x="178" y="{streak_y+42}" fill="{cyan}">~</text><text x="192" y="{streak_y+42}" fill="{text}">$ </text>'
               f'<rect x="211" y="{streak_y+29}" width="9" height="17" fill="{text}"/>')
    out.append('</svg>')
    return "".join(out)


if __name__ == "__main__":
    data = collect()
    Path("dark_mode.svg").write_text(svg(data, True), encoding="utf-8")
    Path("light_mode.svg").write_text(svg(data, False), encoding="utf-8")