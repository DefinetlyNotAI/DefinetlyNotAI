import datetime as dt
import hashlib
import html
import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


USER = "DefinetlyNotAI"
TOKEN = os.environ["GITHUB_TOKEN"]

GRAPHQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "profile-readme",
    "X-GitHub-Api-Version": "2022-11-28",
}

LANGUAGE_BAR_WIDTH = 72
LANGUAGE_LABEL_WIDTH = 108

ABOUT_TEXT = """
I’m Shahm Najeeb, a full-stack developer, systems builder, and student
technology organizer focused on turning ambitious ideas into working software.

My portfolio spans production-ready web platforms, developer tooling,
cybersecurity and digital-forensics utilities, NFC infrastructure, embedded
systems, machine learning experiments, browser extensions, simulations, and
interactive ARG experiences. I work mainly with TypeScript, Python, Next.js,
React, PostgreSQL, JavaScript, C, C#, PowerShell, and ESP32 hardware.

Some of my larger projects include an NFC-based conference management
platform, a self-hosted API and WebSocket sandbox, a TypeScript code-quality
analyzer published as a CLI, a Windows forensic data collection system, a
digital banking simulation, and Facility, a multi-part psychological-horror
ARG with custom websites, terminal games, bots, puzzles, and supporting tools
- all of which are open-sourced.

Outside development, I founded Hack Street, a non-profit student organization
supported through Hack Club’s HCB program for 2.5 years. I have helped
organize and lead more than 4 student hackathons while creating the websites,
registration systems, schedules, infrastructure, and interactive experiences
behind them gathering over 300 students/hackers.

I also have over 9 years of structured robotics experience, including
embedded systems, competition programming, Arduino based robotics, and
regional robotics events. I enjoy projects that combine software, hardware,
infrastructure, and creative problem-solving into something people can
actually use.
""".strip()


GITHUB_LANGUAGE_COLORS = {
    "1C Enterprise": "#814CCC",
    "ABAP": "#E8274B",
    "ActionScript": "#882B0F",
    "Ada": "#02F88C",
    "Arduino": "#BD79D1",
    "Assembly": "#6E4C13",
    "Astro": "#FF5A03",
    "Batchfile": "#C1F12E",
    "C": "#555555",
    "C#": "#178600",
    "C++": "#F34B7D",
    "CMake": "#DA3434",
    "COBOL": "#005CA5",
    "CoffeeScript": "#244776",
    "Common Lisp": "#3FB68B",
    "Crystal": "#000100",
    "CSS": "#663399",
    "Cuda": "#3A4E3A",
    "D": "#BA595E",
    "Dart": "#00B4AB",
    "Dockerfile": "#384D54",
    "Elixir": "#6E4A7E",
    "Elm": "#60B5CC",
    "Emacs Lisp": "#C065DB",
    "Erlang": "#B83998",
    "F#": "#B845FC",
    "Fortran": "#4D41B1",
    "GDScript": "#355570",
    "GLSL": "#5686A5",
    "Go": "#00ADD8",
    "Groovy": "#4298B8",
    "HLSL": "#AACE60",
    "HTML": "#E34C26",
    "Haskell": "#5E5086",
    "Java": "#B07219",
    "JavaScript": "#F1E05A",
    "Jinja": "#A52A22",
    "Julia": "#A270BA",
    "Jupyter Notebook": "#DA5B0B",
    "Kotlin": "#A97BFF",
    "Less": "#1D365D",
    "Lua": "#000080",
    "MATLAB": "#E16737",
    "Makefile": "#427819",
    "Markdown": "#083FA1",
    "Nim": "#FFC200",
    "Nix": "#7E7EFF",
    "Objective-C": "#438EFF",
    "Objective-C++": "#6866FB",
    "OCaml": "#EF7A08",
    "Pascal": "#E3F171",
    "Perl": "#0298C3",
    "PHP": "#4F5D95",
    "PowerShell": "#012456",
    "Processing": "#0096D8",
    "Prolog": "#74283C",
    "Pug": "#A86454",
    "Python": "#3572A5",
    "R": "#198CE7",
    "Racket": "#3C5CAA",
    "Ren'Py": "#FF7F7F",
    "Ruby": "#701516",
    "Rust": "#DEA584",
    "Sass": "#A53B70",
    "Scala": "#C22D40",
    "SCSS": "#C6538C",
    "Shell": "#89E051",
    "Solidity": "#AA6746",
    "SQL": "#E38C00",
    "Svelte": "#FF3E00",
    "Swift": "#F05138",
    "TeX": "#3D6117",
    "TypeScript": "#3178C6",
    "VBA": "#867DB1",
    "Vue": "#41B883",
    "WebAssembly": "#04133B",
    "XML": "#0060AC",
    "YAML": "#CB171E",
    "Zig": "#EC915C",
}


def request_json(url, *, method="GET", data=None, headers=None, retries=5):
    request_headers = dict(HEADERS)

    if headers:
        request_headers.update(headers)

    body = None

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    for attempt in range(retries):
        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            retryable = error.code in {429, 500, 502, 503, 504}

            if not retryable or attempt == retries - 1:
                detail = error.read().decode("utf-8", "replace")
                raise RuntimeError(
                    f"GitHub HTTP {error.code} for {url}: {detail}"
                ) from error

            retry_after = error.headers.get("Retry-After")
            delay = int(retry_after) if retry_after else 2 ** attempt
            time.sleep(delay)
        except urllib.error.URLError as error:
            if attempt == retries - 1:
                raise RuntimeError(f"Request failed for {url}: {error}") from error

            time.sleep(2 ** attempt)

    raise RuntimeError(f"Request failed after {retries} attempts: {url}")


def request_bytes(url, *, retries=5):
    for attempt in range(retries):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": HEADERS["User-Agent"],
                "Accept": "image/*",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError) as error:
            if attempt == retries - 1:
                raise RuntimeError(f"Failed to download {url}: {error}") from error

            time.sleep(2 ** attempt)

    raise RuntimeError(f"Failed to download {url}")


def graphql(query, variables=None):
    payload = request_json(
        GRAPHQL_URL,
        method="POST",
        data={
            "query": query,
            "variables": variables or {},
        },
    )

    if payload.get("errors"):
        raise RuntimeError(payload["errors"])

    return payload["data"]


def profile_data():
    query = """
    query($login: String!) {
      user(login: $login) {
        name
        login
        avatarUrl(size: 460)
        createdAt
        followers {
          totalCount
        }
        repositories(
          first: 1
          ownerAffiliations: OWNER
          privacy: PUBLIC
        ) {
          totalCount
        }
      }
    }
    """

    return graphql(query, {"login": USER})["user"]


def rest_paginated(path, params=None):
    params = dict(params or {})
    params["per_page"] = 100

    page = 1
    results = []

    while True:
        params["page"] = page
        query = urllib.parse.urlencode(params)
        url = f"{REST_URL}{path}?{query}"

        response = request_json(url)

        if not response:
            break

        if not isinstance(response, list):
            raise RuntimeError(f"Expected list response from {url}")

        results.extend(response)

        if len(response) < 100:
            break

        page += 1

    return results


def public_repositories():
    return rest_paginated(
        f"/users/{USER}/repos",
        {
            "type": "owner",
            "sort": "full_name",
            "direction": "asc",
        },
    )


def repository_languages(repo):
    return request_json(
        f"{REST_URL}/repos/{repo['owner']['login']}/{repo['name']}/languages"
    )


def repo_history(repo, cursor=None):
    owner, name = repo.split("/", 1)

    query = """
    query(
      $owner: String!
      $name: String!
      $cursor: String
    ) {
      repository(owner: $owner, name: $name) {
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 100, after: $cursor) {
                nodes {
                  oid
                  additions
                  deletions
                  committedDate
                  author {
                    user {
                      login
                    }
                  }
                }
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
          }
        }
      }
    }
    """

    data = graphql(
        query,
        {
            "owner": owner,
            "name": name,
            "cursor": cursor,
        },
    )["repository"]

    branch = data.get("defaultBranchRef")

    if not branch:
        return None

    return branch["target"]["history"]


def github_commit_days(created):
    today = dt.datetime.now(dt.timezone.utc)
    cursor = created.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    days = set()

    query = """
    query(
      $login: String!
      $start: DateTime!
      $end: DateTime!
    ) {
      user(login: $login) {
        contributionsCollection(from: $start, to: $end) {
          commitContributionsByRepository(maxRepositories: 100) {
            contributions(first: 100) {
              nodes {
                occurredAt
                commitCount
              }
            }
          }
        }
      }
    }
    """

    while cursor <= today:
        if cursor.month == 12:
            next_month = cursor.replace(
                year=cursor.year + 1,
                month=1,
            )
        else:
            next_month = cursor.replace(month=cursor.month + 1)

        period_end = min(
            next_month - dt.timedelta(seconds=1),
            today,
        )

        data = graphql(
            query,
            {
                "login": USER,
                "start": cursor.isoformat(),
                "end": period_end.isoformat(),
            },
        )["user"]["contributionsCollection"]

        for repository in data["commitContributionsByRepository"]:
            nodes = repository["contributions"]["nodes"]

            for contribution in nodes:
                if contribution["commitCount"] > 0:
                    days.add(
                        dt.date.fromisoformat(
                            contribution["occurredAt"][:10]
                        )
                    )

        cursor = next_month

    return sorted(days)


def rank_data():
    try:
        request = urllib.request.Request(
            f"https://user-badge.committers.top/jordan/{USER}.svg",
            headers={"User-Agent": "Mozilla/5.0"},
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", "replace")

        match = re.search(
            r"(?:rank|#)\s*(\d+)(?:st|nd|rd|th)?",
            raw,
            re.IGNORECASE,
        )

        rank = int(match.group(1)) if match else None
    except Exception:
        rank = None

    return f"#{rank}" if rank else "unavailable"


def longest_streak(days):
    active = sorted(set(days))

    if not active:
        return 0, "No public commit contributions"

    best_start = active[0]
    best_end = active[0]

    run_start = active[0]
    previous = active[0]

    for day in active[1:]:
        if (day - previous).days != 1:
            current_length = (previous - run_start).days
            best_length = (best_end - best_start).days

            if current_length > best_length:
                best_start = run_start
                best_end = previous

            run_start = day

        previous = day

    current_length = (previous - run_start).days
    best_length = (best_end - best_start).days

    if current_length > best_length:
        best_start = run_start
        best_end = previous

    length = (best_end - best_start).days + 1
    date_range = f"{best_start:%d %b %Y} - {best_end:%d %b %Y}"

    return length, date_range


def collect_repository_activity(repositories):
    additions = 0
    deletions = 0
    commits = 0
    stars = 0

    for repo in repositories:
        stars += repo.get("stargazers_count", 0)

        if not repo.get("default_branch"):
            continue

        history = repo_history(repo["full_name"])

        if history is None:
            continue

        while True:
            for commit in history["nodes"]:
                author = commit.get("author") or {}
                github_user = (author.get("user") or {}).get("login", "")

                if github_user.lower() != USER.lower():
                    continue

                commits += 1
                additions += commit["additions"]
                deletions += commit["deletions"]

            if not history["pageInfo"]["hasNextPage"]:
                break

            history = repo_history(
                repo["full_name"],
                history["pageInfo"]["endCursor"],
            )

            if history is None:
                break

    return {
        "commits": commits,
        "additions": additions,
        "deletions": deletions,
        "stars": stars,
    }


def collect_languages(repositories):
    totals = Counter()

    for repo in repositories:
        languages = repository_languages(repo)

        for language, byte_count in languages.items():
            totals[language] += int(byte_count)

    return totals


def collect():
    user = profile_data()
    repositories = public_repositories()

    language_totals = collect_languages(repositories)
    activity = collect_repository_activity(repositories)

    created = dt.datetime.fromisoformat(
        user["createdAt"].replace("Z", "+00:00")
    )

    now = dt.datetime.now(dt.timezone.utc)
    delta = now - created

    years = delta.days // 365
    remaining_days = delta.days % 365
    months = remaining_days // 30
    days = remaining_days % 30

    commit_days = github_commit_days(created)
    streak_days, streak_range = longest_streak(commit_days)

    additions = activity["additions"]
    deletions = activity["deletions"]

    return {
        "name": user.get("name") or "Shahm Najeeb",
        "username": user["login"],
        "avatar_url": user["avatarUrl"],
        "joined": created.strftime("%d %b %Y"),
        "uptime": f"{years} years, {months} months, {days} days",
        "repos": len(repositories),
        "followers": user["followers"]["totalCount"],
        "stars": activity["stars"],
        "commits": activity["commits"],
        "additions": additions,
        "deletions": deletions,
        "loc": additions - deletions,
        "churn": additions + deletions,
        "active_days": len(commit_days),
        "streak_days": streak_days,
        "streak_range": streak_range,
        "rank": rank_data(),
        "languages": language_totals,
    }


def escape(value):
    if isinstance(value, int):
        return html.escape(f"{value:,}")

    return html.escape(str(value))


def wrap_text(text, max_chars):
    paragraphs = text.splitlines()
    lines = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            lines.append("")
            continue

        words = paragraph.split()
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip()

            if len(candidate) > max_chars and current:
                lines.append(current)
                current = word
            else:
                current = candidate

        if current:
            lines.append(current)

    return lines


def avatar_to_ascii(url, width=46):
    try:
        raw = request_bytes(url)

        with Image.open(io.BytesIO(raw)) as image:
            image = image.convert("L")
            image = ImageOps.fit(
                image,
                (460, 460),
                method=Image.Resampling.LANCZOS,
            )

            image = ImageEnhance.Contrast(image).enhance(1.55)

            aspect_ratio = image.height / image.width
            height = max(1, round(width * aspect_ratio * 0.47))

            image = image.resize(
                (width, height),
                Image.Resampling.LANCZOS,
            )

            characters = "@%#*+=-:. "
            pixels = list(image.getdata())
            lines = []

            for row in range(height):
                line = ""

                for column in range(width):
                    value = pixels[row * width + column]
                    index = round(
                        value / 255 * (len(characters) - 1)
                    )
                    line += characters[index]

                lines.append(line.rstrip())

            return lines
    except Exception:
        return [
            "              .-==============-.",
            "          .-======================-.",
            "       .-============================-.",
            "      ==================================",
            "     ====================================",
            "     ============ SHAHM =================",
            "     ========== @DefinetlyNotAI =========",
            "     ====================================",
            "      ==================================",
            "       '-============================-'",
            "          '-======================-'",
            "              '-==============-'",
        ]


def generated_language_color(language, unavailable_colors):
    digest = hashlib.sha256(language.encode("utf-8")).hexdigest()
    seed = int(digest[:8], 16)

    hue = seed % 360
    saturation = 58 + ((seed >> 8) % 24)
    lightness = 48 + ((seed >> 16) % 15)

    for _ in range(360):
        color = hsl_to_hex(hue, saturation, lightness)

        if color.lower() not in unavailable_colors:
            return color

        hue = (hue + 37) % 360

    return "#8B949E"


def hsl_to_hex(hue, saturation, lightness):
    saturation /= 100
    lightness /= 100

    chroma = (1 - abs(2 * lightness - 1)) * saturation
    section = hue / 60
    x_value = chroma * (1 - abs(section % 2 - 1))
    offset = lightness - chroma / 2

    if 0 <= section < 1:
        red, green, blue = chroma, x_value, 0
    elif 1 <= section < 2:
        red, green, blue = x_value, chroma, 0
    elif 2 <= section < 3:
        red, green, blue = 0, chroma, x_value
    elif 3 <= section < 4:
        red, green, blue = 0, x_value, chroma
    elif 4 <= section < 5:
        red, green, blue = x_value, 0, chroma
    else:
        red, green, blue = chroma, 0, x_value

    red = round((red + offset) * 255)
    green = round((green + offset) * 255)
    blue = round((blue + offset) * 255)

    return f"#{red:02X}{green:02X}{blue:02X}"


def build_language_segments(language_totals, bar_width):
    total_bytes = sum(language_totals.values())

    if total_bytes <= 0:
        return [], [], []

    percentages = [
        {
            "name": language,
            "bytes": byte_count,
            "percent": byte_count / total_bytes * 100,
        }
        for language, byte_count in language_totals.most_common()
    ]

    minimum_percent = 100 / bar_width

    visible = [
        item
        for item in percentages
        if item["percent"] >= minimum_percent
    ]

    others = [
        item
        for item in percentages
        if item["percent"] < minimum_percent
    ]

    if others:
        visible.append(
            {
                "name": "Others",
                "bytes": sum(item["bytes"] for item in others),
                "percent": sum(item["percent"] for item in others),
            }
        )

    raw_allocations = [
        item["percent"] / 100 * bar_width
        for item in visible
    ]

    allocations = [
        max(1, math.floor(value))
        for value in raw_allocations
    ]

    while sum(allocations) > bar_width:
        candidates = [
            index
            for index, allocation in enumerate(allocations)
            if allocation > 1
        ]

        if not candidates:
            break

        remove_index = min(
            candidates,
            key=lambda index: (
                raw_allocations[index] - allocations[index],
                visible[index]["percent"],
            ),
        )

        allocations[remove_index] -= 1

    while sum(allocations) < bar_width:
        add_index = max(
            range(len(allocations)),
            key=lambda index: (
                raw_allocations[index] - allocations[index],
                visible[index]["percent"],
            ),
        )

        allocations[add_index] += 1

    predefined_colors = {
        color.lower()
        for color in GITHUB_LANGUAGE_COLORS.values()
    }

    used_colors = set()
    previous_color = None
    segments = []

    for item, width in zip(visible, allocations):
        language = item["name"]

        if language == "Others":
            color = "#8B949E"
        else:
            color = GITHUB_LANGUAGE_COLORS.get(language)

            if color is None:
                unavailable = predefined_colors | used_colors

                if previous_color:
                    unavailable.add(previous_color.lower())

                color = generated_language_color(
                    language,
                    unavailable,
                )

        if previous_color and color.lower() == previous_color.lower():
            color = generated_language_color(
                f"{language}-alternate",
                predefined_colors | used_colors | {previous_color.lower()},
            )

        used_colors.add(color.lower())
        previous_color = color

        segments.append(
            {
                "name": language,
                "percent": item["percent"],
                "width": width,
                "color": color,
            }
        )

    return segments, visible, others


def language_label_lines(segments, max_chars=LANGUAGE_LABEL_WIDTH):
    labels = [
        f"{segment['name']} {segment['percent']:.2f}%"
        for segment in segments
    ]

    lines = []
    current = ""

    for label in labels:
        decorated = f"| {label} "
        candidate = f"{current}{decorated}"

        if len(candidate) + 1 > max_chars and current:
            lines.append(current + "|")
            current = decorated
        else:
            current = candidate

    if current:
        lines.append(current + "|")

    return lines


def svg_text(
    x,
    y,
    content,
    color,
    *,
    css_class=None,
    anchor=None,
):
    attributes = [
        f'x="{x}"',
        f'y="{y}"',
        f'fill="{color}"',
    ]

    if css_class:
        attributes.append(f'class="{css_class}"')

    if anchor:
        attributes.append(f'text-anchor="{anchor}"')

    return (
        f"<text {' '.join(attributes)}>"
        f"{html.escape(str(content))}"
        f"</text>"
    )


def command_prompt(y, text, colors):
    green = colors["green"]
    cyan = colors["cyan"]
    foreground = colors["text"]

    return [
        svg_text(48, y, "shahm@github", green),
        svg_text(166, y, ":", foreground),
        svg_text(178, y, "~", cyan),
        svg_text(192, y, f"$ {text}", foreground),
    ]


def svg(data, dark):
    if dark:
        colors = {
            "bg": "#05080D",
            "terminal": "#0A1018",
            "text": "#F0F3F6",
            "muted": "#7D8590",
            "border": "#263445",
            "green": "#39D353",
            "cyan": "#58A6FF",
            "amber": "#D29922",
            "red": "#F85149",
        }
    else:
        colors = {
            "bg": "#EDF2F7",
            "terminal": "#FFFFFF",
            "text": "#17212B",
            "muted": "#66717E",
            "border": "#BCC8D4",
            "green": "#1A7F37",
            "cyan": "#0969DA",
            "amber": "#9A6700",
            "red": "#CF222E",
        }

    avatar_lines = avatar_to_ascii(data["avatar_url"])

    segments, _, other_languages = build_language_segments(
        data["languages"],
        LANGUAGE_BAR_WIDTH,
    )

    label_lines = language_label_lines(segments)

    other_names = [
        item["name"]
        for item in other_languages
    ]

    if other_names:
        others_text = ", ".join(other_names)
        others_lines = wrap_text(
            f"Others: {others_text}",
            108,
        )
    else:
        others_lines = ["Others: none"]

    about_lines = wrap_text(
        ABOUT_TEXT,
        116,
    )

    avatar_start_y = 205
    avatar_line_height = 17

    language_command_y = (
        avatar_start_y
        + len(avatar_lines) * avatar_line_height
        + 54
    )

    language_labels_y = language_command_y + 31
    language_bar_y = (
        language_labels_y
        + len(label_lines) * 22
        + 10
    )

    others_y = language_bar_y + 33
    stats_command_y = (
        others_y
        + len(others_lines) * 21
        + 39
    )

    stats_start_y = stats_command_y + 35
    streak_y = stats_start_y + 5 * 29 + 15
    about_command_y = streak_y + 52
    about_start_y = about_command_y + 34

    total_height = (
        about_start_y
        + len(about_lines) * 22
        + 74
    )

    output = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="1200" height="{total_height}" '
            f'viewBox="0 0 1200 {total_height}">'
        ),
        (
            f'<rect width="1200" height="{total_height}" '
            f'rx="16" fill="{colors["bg"]}"/>'
        ),
        (
            f'<rect x="20" y="20" width="1160" '
            f'height="{total_height - 40}" rx="12" '
            f'fill="{colors["terminal"]}" '
            f'stroke="{colors["border"]}"/>'
        ),
        (
            f'<circle cx="48" cy="47" r="6" fill="{colors["red"]}"/>'
            f'<circle cx="68" cy="47" r="6" fill="{colors["amber"]}"/>'
            f'<circle cx="88" cy="47" r="6" fill="{colors["green"]}"/>'
        ),
        (
            "<style>"
            "text{"
            "font-family:ui-monospace,SFMono-Regular,Consolas,"
            "Liberation Mono,monospace;"
            "font-size:15px;"
            "white-space:pre"
            "}"
            ".small{font-size:13px}"
            ".head{font-size:19px;font-weight:700}"
            ".avatar{font-size:14px}"
            ".bar{font-size:18px;font-weight:700}"
            "</style>"
        ),
        svg_text(
            112,
            53,
            "profile-readme : bash",
            colors["muted"],
            css_class="small",
        ),
        (
            f'<line x1="20" y1="72" x2="1180" y2="72" '
            f'stroke="{colors["border"]}"/>'
        ),
    ]

    output.extend(
        command_prompt(
            106,
            "./profile --live --ascii",
            colors,
        )
    )

    output.append(
        svg_text(
            48,
            137,
            "[ok] loading public GitHub activity...",
            colors["muted"],
        )
    )

    output.append(
        svg_text(
            48,
            175,
            data["name"],
            colors["text"],
            css_class="head",
        )
    )

    output.append(
        svg_text(
            255,
            175,
            f"@{data['username']}",
            colors["cyan"],
            css_class="head",
        )
    )

    for index, line in enumerate(avatar_lines):
        output.append(
            svg_text(
                48,
                avatar_start_y + index * avatar_line_height,
                line,
                colors["text"],
                css_class="avatar",
            )
        )

    output.extend(
        command_prompt(
            language_command_y,
            "github-languages --aggregate --by-bytes",
            colors,
        )
    )

    for index, line in enumerate(label_lines):
        output.append(
            svg_text(
                48,
                language_labels_y + index * 22,
                line,
                colors["text"],
            )
        )

    bar_x = 48
    character_width = 9.05

    for segment in segments:
        segment_text = "#" * segment["width"]

        output.append(
            svg_text(
                bar_x,
                language_bar_y,
                segment_text,
                segment["color"],
                css_class="bar",
            )
        )

        bar_x += segment["width"] * character_width

    for index, line in enumerate(others_lines):
        output.append(
            svg_text(
                48,
                others_y + index * 21,
                line,
                colors["muted"],
                css_class="small",
            )
        )

    output.extend(
        command_prompt(
            stats_command_y,
            "github-stats --verbose",
            colors,
        )
    )

    left_stats = [
        ("repositories", data["repos"]),
        ("commits", data["commits"]),
        ("total_stars", data["stars"]),
        ("followers", data["followers"]),
        ("active_commit_days", data["active_days"]),
    ]

    right_stats = [
        ("net_lines", data["loc"]),
        ("additions", f"+{data['additions']:,}"),
        ("deletions", f"-{data['deletions']:,}"),
        ("code_churn", data["churn"]),
        ("jordan_rank", data["rank"]),
    ]

    for column_index, values in enumerate(
        (left_stats, right_stats)
    ):
        base_x = 48 + column_index * 576
        value_x = base_x + 318

        for row_index, (label, value) in enumerate(values):
            y = stats_start_y + row_index * 29

            output.append(
                svg_text(
                    base_x,
                    y,
                    f"|-- {label}",
                    colors["muted"],
                )
            )

            output.append(
                svg_text(
                    value_x,
                    y,
                    escape(value),
                    colors["text"],
                )
            )

    output.append(
        svg_text(
            48,
            streak_y,
            "|-- longest_commit_streak",
            colors["muted"],
        )
    )

    output.append(
        svg_text(
            366,
            streak_y,
            f"{data['streak_days']} days",
            colors["text"],
        )
    )

    output.append(
        svg_text(
            500,
            streak_y,
            f"[{data['streak_range']}]",
            colors["muted"],
        )
    )

    output.extend(
        command_prompt(
            about_command_y,
            "about",
            colors,
        )
    )

    for index, line in enumerate(about_lines):
        y = about_start_y + index * 22

        if not line:
            continue

        output.append(
            svg_text(
                48,
                y,
                line,
                colors["text"],
            )
        )

    cursor_y = about_start_y + len(about_lines) * 22 + 27

    output.extend(
        command_prompt(
            cursor_y,
            "",
            colors,
        )
    )

    output.append(
        (
            f'<rect x="211" y="{cursor_y - 14}" '
            f'width="9" height="17" fill="{colors["text"]}"/>'
        )
    )

    output.append("</svg>")

    return "".join(output)


def main():
    data = collect()

    Path("dark_mode.svg").write_text(
        svg(data, True),
        encoding="utf-8",
    )

    Path("light_mode.svg").write_text(
        svg(data, False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
