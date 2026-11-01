#!/usr/bin/env python3
"""Generate the profile streak and activity SVGs from one GitHub calendar."""

from __future__ import annotations

import html
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


USERNAME = os.environ.get("GITHUB_USERNAME", "Jay-2522")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "assets"))
GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""

BG = "#1B1B2F"
TEXT = "#E6EDF3"
MUTED = "#9BA3B4"
BLUE = "#70A5FD"
PURPLE = "#C084FC"
TEAL = "#2DD4BF"
LEVELS = ("#292943", "#234E70", "#256A8A", "#298A9A", "#2DD4BF")


def fetch_calendar(token: str, start: date, end: date) -> dict:
    variables = {
        "login": USERNAME,
        "from": f"{start.isoformat()}T00:00:00Z",
        "to": f"{end.isoformat()}T23:59:59Z",
    }
    body = json.dumps({"query": QUERY, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "profile-contribution-widgets",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub GraphQL request failed (HTTP {exc.code}).") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not retrieve the GitHub contribution calendar: {exc.__class__.__name__}.") from None

    if payload.get("errors"):
        # Avoid echoing response bodies or request headers into Actions logs.
        raise RuntimeError("GitHub GraphQL returned an error; no widget files were updated.")
    user = (payload.get("data") or {}).get("user")
    collection = (user or {}).get("contributionsCollection")
    calendar = (collection or {}).get("contributionCalendar")
    if not calendar or calendar.get("totalContributions") is None:
        raise RuntimeError("GitHub returned no contribution calendar; no widget files were updated.")
    return {"calendar": calendar, "restricted": collection.get("restrictedContributionsCount")}


def normalize_days(calendar: dict, start: date, end: date) -> list[tuple[date, int]]:
    values: dict[date, int] = {}
    for week in calendar.get("weeks", []):
        for item in week.get("contributionDays", []):
            try:
                day = date.fromisoformat(item["date"])
                count = int(item["contributionCount"])
            except (KeyError, TypeError, ValueError):
                raise RuntimeError("GitHub returned an invalid contribution day; no widget files were updated.") from None
            if count < 0 or day in values:
                raise RuntimeError("GitHub returned duplicate or invalid contribution days; no widget files were updated.")
            values[day] = count

    expected_count = (end - start).days + 1
    days = [(start + timedelta(days=i), values[start + timedelta(days=i)])
            for i in range(expected_count) if start + timedelta(days=i) in values]
    if len(days) != expected_count:
        raise RuntimeError("GitHub returned an incomplete date range; no widget files were updated.")
    return days


def streaks(days: list[tuple[date, int]]) -> tuple[int, int, date | None, date | None, date | None, date | None]:
    if not days:
        return 0, 0, None, None, None, None
    counts = dict(days)
    day_dates = [day for day, _ in days]
    latest = day_dates[-1]
    # The calendar dates are UTC dates. Today may still be in progress; when it
    # has no contribution yet, use yesterday as GitHub's current-streak anchor.
    anchor = latest if counts[latest] > 0 else latest - timedelta(days=1)
    current = 0
    cursor = anchor
    while cursor in counts and counts[cursor] > 0:
        current += 1
        cursor -= timedelta(days=1)
    current_end = anchor if current else None
    current_start = anchor - timedelta(days=current - 1) if current else None

    longest = 0
    best_start = best_end = None
    run = 0
    run_start = None
    for day, count in days:
        if count:
            if not run:
                run_start = day
            run += 1
            if run > longest:
                longest, best_start, best_end = run, run_start, day
        else:
            run = 0
            run_start = None
    return current, longest, current_start, current_end, best_start, best_end


def fmt_day(value: date | None) -> str:
    return value.strftime("%b %-d") if value else "—"


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_streak(total: int, days: list[tuple[date, int]], start: date, end: date) -> str:
    current, longest, current_start, current_end, best_start, best_end = streaks(days)
    year_label = f"{start:%b %-d, %Y} – {end:%b %-d, %Y} UTC"
    current_range = f"{fmt_day(current_start)} – {fmt_day(current_end)}" if current else "No active streak"
    longest_range = f"{fmt_day(best_start)} – {fmt_day(best_end)}" if longest else "—"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="250" viewBox="0 0 640 250" role="img" aria-labelledby="title desc">
  <title id="title">GitHub contribution streak for {escape(USERNAME)}</title>
  <desc id="desc">{total} contributions from {escape(year_label)}; current streak {current} days; longest streak {longest} days.</desc>
  <rect width="640" height="250" rx="14" fill="{BG}"/>
  <text x="100" y="96" text-anchor="middle" fill="{BLUE}" font-family="Arial,sans-serif" font-size="34" font-weight="700">{total}</text>
  <text x="100" y="135" text-anchor="middle" fill="{TEXT}" font-family="Arial,sans-serif" font-size="16">Total Contributions</text>
  <text x="100" y="170" text-anchor="middle" fill="{TEAL}" font-family="Arial,sans-serif" font-size="12">{escape(year_label)}</text>
  <line x1="250" y1="50" x2="250" y2="200" stroke="#D1D5DB" stroke-opacity=".55" stroke-width="2"/>
  <circle cx="320" cy="90" r="48" stroke="{BLUE}" stroke-width="7" fill="none"/><circle cx="320" cy="42" r="8" fill="{BG}" stroke="{BLUE}" stroke-width="5"/>
  <text x="320" y="98" text-anchor="middle" dominant-baseline="middle" fill="{PURPLE}" font-family="Arial,sans-serif" font-size="34" font-weight="700">{current}</text>
  <text x="320" y="165" text-anchor="middle" fill="{PURPLE}" font-family="Arial,sans-serif" font-size="16" font-weight="700">Current Streak</text>
  <text x="320" y="195" text-anchor="middle" fill="{TEAL}" font-family="Arial,sans-serif" font-size="13">{escape(current_range)}</text>
  <line x1="410" y1="50" x2="410" y2="200" stroke="#D1D5DB" stroke-opacity=".55" stroke-width="2"/>
  <text x="505" y="96" text-anchor="middle" fill="{BLUE}" font-family="Arial,sans-serif" font-size="34" font-weight="700">{longest}</text>
  <text x="505" y="135" text-anchor="middle" fill="{TEXT}" font-family="Arial,sans-serif" font-size="16">Longest Streak</text>
  <text x="505" y="170" text-anchor="middle" fill="{TEAL}" font-family="Arial,sans-serif" font-size="13">{escape(longest_range)}</text>
</svg>
'''


def level(count: int) -> int:
    if count == 0:
        return 0
    if count == 1:
        return 1
    if count <= 4:
        return 2
    if count <= 9:
        return 3
    return 4


def render_activity(days: list[tuple[date, int]], start: date, end: date, total: int) -> str:
    cell, gap, step = 11, 3, 14
    first_sunday = start - timedelta(days=(start.weekday() + 1) % 7)
    columns = ((end - first_sunday).days // 7) + 1
    left, top, width, height = 42, 42, 820, 166
    counts = dict(days)
    pieces = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">GitHub activity for {escape(USERNAME)}</title>
  <desc id="desc">Daily GitHub contributions from {start.isoformat()} through {end.isoformat()} UTC; {total} total contributions.</desc>
  <rect width="{width}" height="{height}" rx="14" fill="{BG}"/>
  <text x="{left}" y="23" fill="{TEXT}" font-family="Arial,sans-serif" font-size="14" font-weight="700">Contribution activity</text>
  <text x="{left+176}" y="23" fill="{MUTED}" font-family="Arial,sans-serif" font-size="10">{start.isoformat()} – {end.isoformat()} UTC</text>''']
    for label, row in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
        y = top + row * step + cell - 1
        pieces.append(f'<text x="{left-9}" y="{y}" text-anchor="end" fill="{MUTED}" font-family="Arial,sans-serif" font-size="9">{label}</text>')
    month_columns: dict[tuple[int, int], int] = {(start.year, start.month): 0}
    for day, _ in days:
        if day.day == 1:
            month_columns[(day.year, day.month)] = (day - first_sunday).days // 7
    for (year, month), col in month_columns.items():
        x = left + col * step
        pieces.append(f'<text x="{x}" y="{top-8}" fill="{MUTED}" font-family="Arial,sans-serif" font-size="9">{date(year, month, 1).strftime("%b")}</text>')
    for day, count in days:
        col = (day - first_sunday).days // 7
        row = (day.weekday() + 1) % 7
        x, y = left + col * step, top + row * step
        title = f"{day.isoformat()}: {count} contribution{'s' if count != 1 else ''}"
        pieces.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{LEVELS[level(count)]}"><title>{escape(title)}</title></rect>')
    legend_x, legend_y = width - 154, height - 19
    pieces.append(f'<text x="{legend_x-31}" y="{legend_y+9}" fill="{MUTED}" font-family="Arial,sans-serif" font-size="9">Less</text>')
    for i, color in enumerate(LEVELS):
        pieces.append(f'<rect x="{legend_x + i*(cell+gap)}" y="{legend_y}" width="{cell}" height="{cell}" rx="2" fill="{color}"/>')
    pieces.append(f'<text x="{legend_x + len(LEVELS)*(cell+gap) + 2}" y="{legend_y+9}" fill="{MUTED}" font-family="Arial,sans-serif" font-size="9">More</text>')
    pieces.append("</svg>")
    return "\n".join(pieces) + "\n"


def generate(now: datetime | None = None, token: str | None = None) -> tuple[str, str, dict]:
    now = now or datetime.now(timezone.utc)
    end = now.astimezone(timezone.utc).date()
    start = end - timedelta(days=364)
    token = token or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN is not set; no widget files were updated.")
    result = fetch_calendar(token, start, end)
    calendar = result["calendar"]
    days = normalize_days(calendar, start, end)
    daily_total = sum(count for _, count in days)
    calendar_total = int(calendar["totalContributions"])
    # totalContributions is GitHub's canonical total for this exact collection.
    # restrictedContributionsCount describes contributions whose details are
    # restricted; it is diagnostic metadata and must not be added again.
    diagnostics = {"start": start.isoformat(), "end": end.isoformat(), "daily_total": daily_total,
                   "calendar_total": calendar_total, "restricted_count": result.get("restricted")}
    return render_streak(calendar_total, days, start, end), render_activity(days, start, end, calendar_total), diagnostics


def main() -> None:
    try:
        streak_svg, activity_svg, diagnostics = generate()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "github-streak.svg").write_text(streak_svg, encoding="utf-8")
        (OUTPUT_DIR / "github-activity.svg").write_text(activity_svg, encoding="utf-8")
        print(f"Generated contribution widgets for {diagnostics['start']} through {diagnostics['end']} UTC.")
        print(f"Calendar total: {diagnostics['calendar_total']}; sum of in-range daily counts: {diagnostics['daily_total']}.")
        print("GraphQL restrictedContributionsCount was queried for diagnostics and was not added to the calendar total.")
        if diagnostics["calendar_total"] != diagnostics["daily_total"]:
            print("::warning:: Calendar total differs from the in-range daily sum; SVGs use GitHub's collection total and the returned daily values.")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
