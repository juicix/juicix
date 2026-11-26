"""Render a GitHub commit calendar using only public repository counts."""

import calendar
import json
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      commitContributionsByRepository(maxRepositories: 100) {
        repository { visibility }
        contributions(first: 100) {
          pageInfo { hasNextPage }
          nodes { occurredAt commitCount }
        }
      }
    }
  }
}
"""
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "commit-lights.svg"
COLORS = ("#2b4140", "#4d8d76", "#79ba9c", "#abd9bd", "#e0f3d5")
LABELS = ("0", "1", "2–3", "4–7", "8+")


def load_counts(login, start, end):
    counts = Counter()
    while start <= end:
        last = min(start + timedelta(days=89), end)
        response = subprocess.run(
            [
                "gh", "api", "graphql",
                "-f", f"query={QUERY}",
                "-f", f"login={login}",
                "-f", f"from={start}T00:00:00Z",
                "-f", f"to={last}T23:59:59Z",
            ],
            check=True, text=True, encoding="utf-8", stdout=subprocess.PIPE,
        )
        result = json.loads(response.stdout)
        if result.get("errors"):
            raise RuntimeError("GitHub returned GraphQL errors for commit counts.")
        repositories = result["data"]["user"]["contributionsCollection"]["commitContributionsByRepository"]
        if len(repositories) >= 100:
            raise RuntimeError("The GitHub repository limit was reached.")
        for repository in repositories:
            if repository["repository"]["visibility"] != "PUBLIC":
                continue
            contributions = repository["contributions"]
            if contributions["pageInfo"]["hasNextPage"]:
                raise RuntimeError("The GitHub contribution page limit was reached.")
            for row in contributions["nodes"]:
                day = date.fromisoformat(row["occurredAt"][:10])
                if start <= day <= last:
                    counts[day] += row["commitCount"]
        start = last + timedelta(days=1)
    return counts


def brightness(count):
    return sum(count >= threshold for threshold in (1, 2, 4, 8))


def render(counts, start, end):
    monday = start - timedelta(days=start.weekday())
    total = sum(counts.values())
    days_active = sum(count > 0 for count in counts.values())
    period = f"{calendar.month_abbr[start.month]} {start.day}, {start.year} – {calendar.month_abbr[end.month]} {end.day}, {end.year}"
    stats = f"{total:,} public commits across {days_active} active days"
    svg = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="255" viewBox="0 0 800 255" role="img" aria-labelledby="title desc">
<title id="title">Commit lights</title>
<desc id="desc">{stats}. {period}.</desc>
<rect width="800" height="255" rx="14" fill="#112525"/>
<path d="M27 70h746M27 211h746" stroke="#3e5957"/>
<text x="27" y="41" fill="#fff0d2" font-family="Georgia,serif" font-size="30">Commit lights</text>
<text x="772" y="33" text-anchor="end" fill="#eff9f2" font-family="Arial,sans-serif" font-size="16">{stats}</text>
<text x="772" y="54" text-anchor="end" fill="#bbd0c8" font-family="Arial,sans-serif" font-size="12">{period}</text>
<g fill="#bbd0c8" font-family="Arial,sans-serif" font-size="12">''']
    for weekday, label in ((0, "Mon"), (2, "Wed"), (4, "Fri"), (6, "Sun")):
        svg.append(f'<text x="26" y="{107 + weekday * 14}">{label}</text>')
    last_label_column = -5
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        if (offset or start.day > 24) and day.day != 1:
            continue
        column = (day - monday).days // 7
        if column - last_label_column >= 3 and column < 51:
            x = 63 + column * 13.4
            svg.append(f'<text x="{x:.1f}" y="90">{calendar.month_abbr[day.month]}</text>')
            last_label_column = column
    svg.append("</g>")
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        column, row = divmod((day - monday).days, 7)
        count = counts[day]
        color = COLORS[brightness(count)]
        label = escape(f"{day.isoformat()}: {count} commits")
        svg.append(
            f'<rect x="{63 + column * 13.4:.1f}" y="{98 + row * 14}" width="10.4" height="10.4" rx="2" fill="{color}">'
            f'<title>{label}</title></rect>'
        )
    svg.append('<text x="27" y="237" fill="#bbd0c8" font-family="Arial,sans-serif" font-size="12">PUBLIC COMMITS PER DAY</text>')
    for index, (color, label) in enumerate(zip(COLORS, LABELS)):
        x = 493 + index * 58
        svg.append(f'<rect x="{x}" y="225" width="13" height="13" rx="2" fill="{color}"/>')
        svg.append(f'<text x="{x + 19}" y="236" fill="#eff9f2" font-family="Arial,sans-serif" font-size="12">{label}</text>')
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def main():
    login = sys.argv[1]
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=364)
    counts = load_counts(login, start, end)
    OUTPUT.write_text(render(counts, start, end), encoding="utf-8", newline="\n")
    print(f"Rendered {sum(counts.values())} public commits over {sum(count > 0 for count in counts.values())} days.")


if __name__ == "__main__":
    main()
