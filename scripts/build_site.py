#!/usr/bin/env python3
"""Build the static public report from the saved figures and tables."""
from __future__ import annotations

import csv
import html
import json
import math
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "electionmodels-mpl"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from voting_intention import config  # noqa: E402

FIGURES_DIR = REPO_ROOT / "outputs" / "figures"
TABLES_DIR = REPO_ROOT / "outputs" / "tables"
SITE_DIR = REPO_ROOT / "site"

REQUIRED_FIGURES = [
    "overall_trend.png",
    "latest_heatmap.png",
]
REQUIRED_TABLES = [
    "summary_all_groups.csv",
    "headline_all_breakdowns.csv",
    "headline_demographics_only.csv",
    "vote_retention.csv",
    "leaderboard_age.csv",
    "leaderboard_gender.csv",
    "leaderboard_region.csv",
    "leaderboard_social_grade.csv",
    "leaderboard_eu_ref_vote.csv",
    "leaderboard_past_vote.csv",
]
CATEGORIES = [
    ("age", "Age"),
    ("gender", "Gender"),
    ("region", "Region"),
    ("social_grade", "Social grade"),
    ("eu_ref_vote", "EU referendum vote"),
    ("past_vote", "Past vote"),
]
DOWNLOAD_LABELS = {
    "summary_all_groups.csv": "Full group-by-party summary",
    "headline_all_breakdowns.csv": "Headline findings across all breakdowns",
    "headline_demographics_only.csv": "Headline findings across demographics",
    "vote_retention.csv": "Past-vote retention by party",
    "leaderboard_age.csv": "Age leaderboard",
    "leaderboard_gender.csv": "Gender leaderboard",
    "leaderboard_region.csv": "Region leaderboard",
    "leaderboard_social_grade.csv": "Social-grade leaderboard",
    "leaderboard_eu_ref_vote.csv": "EU referendum-vote leaderboard",
    "leaderboard_past_vote.csv": "Past-vote leaderboard",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _percent(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(number):
        return "—"
    return f"{number:.1f}%"


def _percentage_points(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(number):
        return "—"
    return f"{number:+.1f} pp"


def _change_class(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number) or number == 0:
        return ""
    return "positive" if number > 0 else "negative"


def _change_cell(value: object) -> str:
    tone = _change_class(value)
    class_attribute = f' class="{tone}"' if tone else ""
    return f'<td{class_attribute}>{_escape(_percentage_points(value))}</td>'


def _party_anchor(party: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", party.casefold()).strip("-")


def _pretty_header(value: str) -> str:
    replacements = {
        "party": "Party",
        "latest_date": "Latest poll",
        "retention_%": "Retention",
        "strongest_%": "Support with strongest group",
        "weakest_%": "Support with weakest group",
        "n_polls": "Polls",
    }
    if value in replacements:
        return replacements[value]
    text = value.replace("_", " ").replace("%", "(%)")
    text = text.replace("pp", "pp").strip()
    return text[:1].upper() + text[1:]


def _table(rows: list[dict[str, str]], caption: str, class_name: str = "data-table") -> str:
    if not rows:
        return f'<p class="muted">No rows are available for { _escape(caption.lower()) }.</p>'
    fields = list(rows[0])
    head = "".join(f"<th scope=\"col\">{_escape(_pretty_header(field))}</th>" for field in fields)
    body = []
    for row in rows:
        cells = []
        for field in fields:
            value = row.get(field, "")
            if field.endswith("_pp"):
                cells.append(_change_cell(value))
            else:
                cells.append(f"<td>{_escape(value or '—')}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return (
        '<div class="table-scroll">'
        f'<table class="{_escape(class_name)}"><caption>{_escape(caption)}</caption>'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"
        "</div>"
    )


def _image(filename: str, title: str, alt: str, caption: str = "") -> str:
    return (
        '<figure class="chart">'
        f'<a href="assets/figures/{_escape(filename)}" data-chart-view aria-label="Open { _escape(title) } image">'
        f'<img src="assets/figures/{_escape(filename)}" alt="{_escape(alt)}" loading="lazy">'
        "</a>"
        f"<figcaption><strong>{_escape(title)}</strong>{(' — ' + _escape(caption)) if caption else ''}</figcaption>"
        "</figure>"
    )


def _latest_national(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    national = [
        row for row in rows
        if row.get("category") == "Overall" and row.get("group") == "All adults"
    ]
    if not national:
        raise ValueError("The summary table has no Overall / All adults rows.")
    order = {party: index for index, party in enumerate(config.PARTY_ORDER)}
    national.sort(key=lambda row: order.get(row.get("party", ""), len(order)))
    return national


def _national_cards(rows: list[dict[str, str]]) -> str:
    cards = []
    for row in rows:
        party = row["party"]
        label = config.PARTY_LABELS.get(party, party)
        color = config.PARTY_COLORS.get(party, "#555555")
        change = _percentage_points(float(row["change_4w"]) * 100) if row.get("change_4w") else "—"
        cards.append(
            f'<a class="party-card-link" href="#party-detail-{_escape(_party_anchor(party))}" '
            f'aria-label="View {_escape(label)} strength and movement">'
            f'<article class="party-card" style="--party-color:{_escape(color)}">'
            f'<h3>{_escape(label)}</h3>'
            f'<p class="party-value">{_percent(float(row["latest"]) * 100)}</p>'
            f'<p class="party-change">4-week change: {_escape(change)}</p>'
            '<p class="party-card-hint">See party breakdown ↓</p>'
            "</article></a>"
        )
    return f'<div class="party-grid">{"".join(cards)}</div>'


def _national_movement_card(rows: list[dict[str, str]]) -> str:
    changes = []
    for row in rows:
        try:
            points = float(row.get("change_4w", "")) * 100
        except (TypeError, ValueError):
            continue
        if math.isfinite(points) and round(points, 1) != 0:
            changes.append({**row, "points": points})

    gaining = [row for row in changes if float(row["points"]) > 0]
    losing = [row for row in changes if float(row["points"]) < 0]

    def movement(label: str, row: dict[str, object] | None) -> str:
        if row is None:
            message = "No increase recorded" if label == "Up most" else "No decrease recorded"
            return (
                '<div class="national-move">'
                f'<span>{_escape(label)}</span><strong class="no-movement">{_escape(message)}</strong>'
                '</div>'
            )
        party = str(row["party"])
        party_label = config.PARTY_LABELS.get(party, party)
        party_color = config.PARTY_COLORS.get(party, "#555555")
        points = float(row["points"])
        direction = "positive" if points > 0 else "negative"
        return (
            '<div class="national-move">'
            f'<span>{_escape(label)}</span>'
            '<div>'
            f'<strong style="--party-color:{_escape(party_color)}">{_escape(party_label)}</strong>'
            f'<b class="{direction}">{_escape(_percentage_points(points))}</b>'
            '</div>'
            '</div>'
        )

    up_most = max(gaining, key=lambda row: float(row["points"])) if gaining else None
    down_most = min(losing, key=lambda row: float(row["points"])) if losing else None
    return (
        '<aside class="national-moves" aria-label="Largest national changes over the last four weeks">'
        '<h3>Biggest 4-week moves</h3>'
        f'{movement("Up most", up_most)}'
        f'{movement("Down most", down_most)}'
        '<p>Among all adults</p>'
        '</aside>'
    )


def _change_cards(summary: list[dict[str, str]]) -> str:
    """Show the three largest demographic moves for each recent window.

    A move is paired with the largest opposite-direction party change within
    the same category and group, so the cards give context for where support
    may be shifting.
    """
    category_labels = {
        "Age": "Age",
        "Gender": "Gender",
        "Region": "Region",
        "Social Grade": "Social grade",
        "EU Ref Vote": "EU referendum vote",
        "Past Vote": "Past vote",
    }
    category_order = {category: index for index, category in enumerate(category_labels)}
    party_order = {party: index for index, party in enumerate(config.PARTY_ORDER)}
    by_group: dict[tuple[str, str], list[dict[str, object]]] = {}

    for row in summary:
        category = row.get("category", "")
        if category not in category_labels:
            continue
        by_group.setdefault((category, row.get("group", "")), []).append(row)

    cards = []
    for weeks in (4, 12):
        change_column = f"change_{weeks}w"
        changes_by_group: dict[tuple[str, str], list[dict[str, object]]] = {}
        candidates: list[dict[str, object]] = []
        for group_key, group_rows in by_group.items():
            changes = []
            for row in group_rows:
                try:
                    points = float(row.get(change_column, "")) * 100
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(points) or round(points, 1) == 0:
                    continue
                move = {**row, "points": points}
                changes.append(move)
                candidates.append(move)
            changes_by_group[group_key] = changes

        def movement_rank(row: dict[str, object]) -> tuple[float, int, str, int]:
            return (
                -abs(float(row["points"])),
                category_order.get(str(row["category"]), len(category_order)),
                str(row["group"]).casefold(),
                party_order.get(str(row["party"]), len(party_order)),
            )
        candidates.sort(key=movement_rank)
        selected = candidates[:3]

        entries = []
        for index, move in enumerate(selected, start=1):
            points = float(move["points"])
            party = str(move["party"])
            category = str(move["category"])
            group = str(move["group"])
            opposite_moves = [
                other for other in changes_by_group[(category, group)]
                if other["party"] != party
                and float(other["points"]) * points < 0
            ]
            opposite_moves.sort(
                key=lambda row: (
                    -abs(float(row["points"])),
                    party_order.get(str(row["party"]), len(party_order)),
                )
            )
            counterpart = opposite_moves[0] if opposite_moves else None
            party_label = config.PARTY_LABELS.get(party, party)
            party_color = config.PARTY_COLORS.get(party, "#555555")
            movement_class = "positive" if points > 0 else "negative"
            if counterpart is None:
                opposite_html = '<p class="opposite-move unavailable">No opposite change recorded for this group</p>'
            else:
                other_party = str(counterpart["party"])
                other_label = config.PARTY_LABELS.get(other_party, other_party)
                other_color = config.PARTY_COLORS.get(other_party, "#555555")
                other_points = float(counterpart["points"])
                other_class = "positive" if other_points > 0 else "negative"
                relation = "Gaining most from" if points > 0 else "Losing most to"
                opposite_html = (
                    f'<p class="opposite-move"><span>{_escape(relation)}</span>'
                    f'<strong style="--party-color:{_escape(other_color)}">{_escape(other_label)}</strong>'
                    f'<b class="{other_class}">{_escape(_percentage_points(other_points))}</b></p>'
                )
            entries.append(
                '<li class="change-entry">'
                f'<p class="change-demographic">{_escape(category_labels[category])} · {_escape(group)}</p>'
                '<div class="leading-move">'
                f'<span class="change-rank">{index:02d}</span>'
                f'<strong style="--party-color:{_escape(party_color)}">{_escape(party_label)}</strong>'
                f'<b class="{movement_class}">{_escape(_percentage_points(points))}</b>'
                '</div>'
                f'{opposite_html}'
                '</li>'
            )

        if not entries:
            entries.append('<li class="muted">No demographic changes are available for this period.</li>')
        cards.append(
            '<article class="change-summary-card">'
            f'<h3>Top 3 changes · {weeks} weeks</h3>'
            f'<ol class="change-rankings">{"".join(entries)}</ol>'
            '</article>'
        )
    return f'<div class="change-card-grid">{"".join(cards)}</div>'


def _headline_cards(
    rows: list[dict[str, str]], national_rows: list[dict[str, str]]
) -> str:
    cards = []
    national_by_party = {row["party"]: row for row in national_rows}
    for row in rows:
        party = row.get("party", "")
        label = config.PARTY_LABELS.get(party, party)
        color = config.PARTY_COLORS.get(party, "#555555")
        national = national_by_party.get(party, {})
        latest_support = _percent(float(national["latest"]) * 100) if national.get("latest") else "—"
        movements = []
        for weeks in (4, 12, 52):
            gain_group = row.get(f"most_gaining_group_{weeks}w", "")
            loss_group = row.get(f"most_losing_group_{weeks}w", "")
            gain_value = row.get(f"gaining_{weeks}w_pp")
            loss_value = row.get(f"losing_{weeks}w_pp")
            movements.append(
                "<tr>"
                f"<th scope=\"row\">{weeks} weeks</th>"
                f"<td>{_escape(gain_group) or '—'}</td>"
                f"{_change_cell(gain_value)}"
                f"<td>{_escape(loss_group) or '—'}</td>"
                f"{_change_cell(loss_value)}"
                "</tr>"
            )
        cards.append(
            f'<article class="headline-card" id="party-detail-{_escape(_party_anchor(party))}" '
            f'tabindex="-1" style="--party-color:{_escape(color)}">'
            '<div class="headline-card-header">'
            f'<h3>{_escape(label)}</h3>'
            f'<p class="headline-latest"><span>Latest national support</span><strong>{_escape(latest_support)}</strong></p>'
            '</div>'
            '<div class="strength-grid">'
            f'<p><span>Strongest demographic</span><strong>{_escape(row.get("strongest_group", "—"))}</strong>'
            f'<em>{_escape(_percent(row.get("strongest_%")))}</em></p>'
            f'<p><span>Weakest demographic</span><strong>{_escape(row.get("weakest_group", "—"))}</strong>'
            f'<em>{_escape(_percent(row.get("weakest_%")))}</em></p>'
            "</div>"
            '<div class="table-scroll"><table class="movement-table">'
            '<caption>Largest demographic changes</caption>'
            '<thead><tr><th scope="col">Period</th><th scope="col">Gaining most</th>'
            '<th scope="col">Change</th><th scope="col">Losing most</th><th scope="col">Change</th></tr></thead>'
            f"<tbody>{''.join(movements)}</tbody></table></div>"
            "</article>"
        )
    return f'<div class="headline-grid">{"".join(cards)}</div>'


def _downloads(csv_files: list[Path]) -> str:
    links = []
    for path in sorted(csv_files, key=lambda item: DOWNLOAD_LABELS.get(item.name, item.name)):
        label = DOWNLOAD_LABELS.get(path.name, path.stem.replace("_", " ").title())
        links.append(
            f'<li><a href="downloads/{_escape(path.name)}" download>{_escape(label)}</a>'
            f'<span>{_escape(path.name)}</span></li>'
        )
    return f'<ul class="download-list">{"".join(links)}</ul>'


def _category_sections(group_charts: list[dict[str, str]]) -> str:
    sections = []
    for slug, title in CATEGORIES:
        leaderboard = _read_csv(TABLES_DIR / f"leaderboard_{slug}.csv")
        charts = [chart for chart in group_charts if chart.get("category_slug") == slug]
        chart_cards = []
        for chart in charts:
            group = chart["group"]
            chart_image = _image(
                chart["filename"],
                group,
                f"Voting intention trends for {title.lower()} group {group}",
                "Thin lines show weekly readings; bold lines show a four-poll average.",
            )
            chart_cards.append(
                f'<div class="group-chart-item" data-filter-item data-search-text="{_escape(group.casefold())}">'
                f'{chart_image}'
                '</div>'
            )
        filter_id = f"group-filter-{slug}"
        sections.append(
            f'<details class="category-panel" id="{_escape(slug)}">'
            f"<summary>{_escape(title)} <span>{len(charts)} group charts and leaderboard</span></summary>"
            '<div class="category-content">'
            '<div class="group-filter">'
            f'<label for="{_escape(filter_id)}">Find a group</label>'
            f'<input type="search" id="{_escape(filter_id)}" data-group-filter placeholder="Type a group name" autocomplete="off">'
            f'<span data-filter-status aria-live="polite">{len(charts)} groups</span>'
            '</div>'
            f'<div class="group-chart-grid">{"".join(chart_cards)}</div>'
            '<p class="filter-empty" data-filter-empty hidden>No groups match that search.</p>'
            f'{_table(leaderboard, f"{title} leaderboard")}'
            "</div></details>"
        )
    return "".join(sections)


def _change_window_sections(figure_files: list[Path]) -> str:
    windows = []
    for path in figure_files:
        match = re.fullmatch(r"change_heatmap_(\d+)w\.png", path.name)
        if match:
            windows.append((int(match.group(1)), path.name))
    windows.sort()
    if not windows:
        return '<p class="muted">No change heatmaps are available.</p>'

    preferred = next((index for index, (weeks, _) in enumerate(windows) if weeks == 12), 0)
    sections = []
    for index, (weeks, filename) in enumerate(windows):
        image = _image(
            filename,
            f"Support change over {weeks} weeks",
            f"Change in party support across demographic groups over {weeks} weeks, in percentage points.",
        )
        sections.append(
            f'<details class="change-window"{" open" if index == preferred else ""}>'
            f'<summary>Last {weeks} weeks <span>Open standalone heatmap</span></summary>'
            f'<div class="change-window-content">{image}</div>'
            '</details>'
        )
    return f'<div class="change-window-list">{"".join(sections)}</div>'


def _validate_inputs() -> tuple[list[dict[str, str]], list[Path], list[Path], list[dict[str, str]]]:
    missing_figures = [name for name in REQUIRED_FIGURES if not (FIGURES_DIR / name).is_file()]
    missing_tables = [name for name in REQUIRED_TABLES if not (TABLES_DIR / name).is_file()]
    manifest_path = FIGURES_DIR / "group_charts.json"
    if not manifest_path.is_file():
        missing_figures.append("group_charts.json (run scripts/refresh_outputs.py)")
    change_figures = sorted(FIGURES_DIR.glob("change_heatmap_*w.png"))
    if not change_figures:
        missing_figures.append("change_heatmap_*w.png")
    if missing_figures or missing_tables:
        problems = []
        if missing_figures:
            problems.append("missing figures: " + ", ".join(missing_figures))
        if missing_tables:
            problems.append("missing tables: " + ", ".join(missing_tables))
        raise FileNotFoundError("Cannot build report; " + "; ".join(problems))

    summary = _read_csv(TABLES_DIR / "summary_all_groups.csv")
    if not summary:
        raise ValueError("The summary table contains no data rows.")
    national = _latest_national(summary)
    if not any(row.get("latest_date") for row in national):
        raise ValueError("The national summary rows have no latest poll date.")

    group_charts = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(group_charts, list) or not group_charts:
        raise ValueError("The group chart manifest is empty; rerun scripts/refresh_outputs.py.")
    group_files = []
    for chart in group_charts:
        filename = Path(chart.get("filename", "")).name
        if not filename or not (FIGURES_DIR / filename).is_file():
            raise FileNotFoundError(f"Missing standalone group chart: {filename or '(no filename)'}")
        group_files.append(FIGURES_DIR / filename)
    figure_files = [
        FIGURES_DIR / name for name in REQUIRED_FIGURES
    ] + change_figures + group_files
    # Keep report assets unique if the manifest ever references a shared image.
    figure_files = list(dict.fromkeys(figure_files))
    csv_files = sorted(TABLES_DIR.glob("*.csv"))
    return summary, figure_files, csv_files, group_charts


def build_site() -> Path:
    summary, figure_files, csv_files, group_charts = _validate_inputs()
    national = _latest_national(summary)
    latest_date = max(row["latest_date"] for row in national)
    national_rows = [row for row in national if row.get("latest_date") == latest_date]
    headlines = _read_csv(TABLES_DIR / "headline_demographics_only.csv")
    retention = _read_csv(TABLES_DIR / "vote_retention.csv")
    checked = datetime.now(ZoneInfo("Europe/London"))
    checked_label = f"{checked.day} {checked.strftime('%B %Y at %H:%M %Z')}"

    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    figures_out = SITE_DIR / "assets" / "figures"
    downloads_out = SITE_DIR / "downloads"
    figures_out.mkdir(parents=True)
    downloads_out.mkdir(parents=True)
    for path in figure_files:
        shutil.copy2(path, figures_out / path.name)
    for path in csv_files:
        shutil.copy2(path, downloads_out / path.name)
    shutil.copy2(REPO_ROOT / "web" / "styles.css", SITE_DIR / "assets" / "styles.css")
    shutil.copy2(REPO_ROOT / "web" / "report.js", SITE_DIR / "assets" / "report.js")

    national_trend = _image(
        "overall_trend.png",
        "National voting intention",
        "National voting intention by party over time; thin lines show weekly readings and bold lines show a four-week average.",
        "Thin lines show weekly readings; bold lines show a four-poll average.",
    )
    latest_heatmap = _image(
        "latest_heatmap.png",
        "Latest support by group",
        "Latest voting intention for parties across age, gender, region, social grade and referendum-vote groups.",
        "Cell labels show support; colour shows relative strength within each party.",
    )
    change_windows = _change_window_sections(figure_files)

    report = f"""<!doctype html>
<html lang="en-GB">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Weekly analysis of UK voting intention and demographic trends from YouGov's public tracker.">
  <meta name="theme-color" content="#102c46">
  <title>UK Voting Intention Tracker | Election Models</title>
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
  <a class="skip-link" href="#main">Skip to report</a>
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="#top" aria-label="Election Models home">ELECTION<span>MODELS</span></a>
      <nav aria-label="Report sections">
        <a href="#national">National trend</a>
        <a href="#shifts">Biggest shifts</a>
        <a href="#demographics">Demographics</a>
        <a href="#groups">By group</a>
        <a href="#downloads">Downloads</a>
      </nav>
    </div>
  </header>
  <main id="main">
    <section class="hero" id="top">
      <div class="hero-inner">
        <p class="eyebrow">UK polling tracker</p>
        <h1>Voting intention,<br><span>week by week.</span></h1>
        <p class="hero-copy">A clear view of national voting intention and how party support varies across the UK electorate.</p>
        <div class="update-meta">
          <p><span>Poll data through</span><strong><time datetime="{_escape(latest_date)}">{_escape(_format_date(latest_date))}</time></strong></p>
          <p><span>Last checked</span><strong><time datetime="{_escape(checked.isoformat(timespec='minutes'))}">{_escape(checked_label)}</time></strong></p>
        </div>
      </div>
    </section>

    <div class="content">
      <section class="report-section" id="national">
        <div class="section-heading">
          <p class="eyebrow">The latest</p>
          <h2>National voting intention</h2>
          <p>Latest reported support among all adults, alongside the change over the previous four weeks.</p>
        </div>
        <div class="national-overview">
          {_national_cards(national_rows)}
          {_national_movement_card(national_rows)}
        </div>
        <section class="shift-summary" id="shifts">
          <div class="section-heading">
            <p class="eyebrow">Recent movement</p>
            <h2>The biggest demographic shifts</h2>
            <p>The three largest changes in either direction across age, gender, region, social grade, EU referendum and past-vote groups. Each is paired with the strongest opposite change among parties in the same group.</p>
          </div>
          {_change_cards(summary)}
        </section>
        {national_trend}
      </section>

      <section class="report-section" id="demographics">
        <div class="section-heading">
          <p class="eyebrow">Across the electorate</p>
          <h2>Where parties are strongest, and where support is moving</h2>
          <p>These comparisons cover age, gender, region, social grade and EU referendum vote. Past-vote groups are shown separately below.</p>
        </div>
          {_headline_cards(headlines, national_rows)}
      </section>

      <section class="report-section chart-section" id="groups">
        <div class="section-heading">
          <p class="eyebrow">Explore the breakdowns</p>
          <h2>Support by group</h2>
          <p>Open a category to explore separate group charts and the current party leaderboard. Search for a group, then select a chart to enlarge it.</p>
        </div>
        <div class="category-tools" aria-label="Category chart controls">
          <button type="button" data-category-action="open">Open all categories</button>
          <button type="button" data-category-action="close">Close all categories</button>
        </div>
        <div class="category-list">{_category_sections(group_charts)}</div>
      </section>

      <section class="report-section" id="latest-support">
        <div class="section-heading">
          <p class="eyebrow">Current picture</p>
          <h2>Latest support by group</h2>
          <p>Cell labels show reported support, while colour highlights groups where each party is relatively stronger or weaker.</p>
        </div>
        {latest_heatmap}
      </section>

      <section class="report-section" id="support-changes">
        <div class="section-heading">
          <p class="eyebrow">Movement</p>
          <h2>How support is changing</h2>
          <p>Each heatmap is a standalone chart. Changes are shown in percentage points, with a separate colour scale for each period.</p>
        </div>
        {change_windows}
      </section>

      <section class="report-section retention-section">
        <div class="section-heading">
          <p class="eyebrow">Past vote</p>
          <h2>Party vote retention</h2>
          <p>Among people who recall voting for each party at the last election, the share who currently say they would vote for that party again.</p>
        </div>
        {_table(retention, "Current vote retention and change over time")}
      </section>

      <section class="report-section downloads-section" id="downloads">
        <div class="section-heading">
          <p class="eyebrow">Open data</p>
          <h2>Download the tables</h2>
          <p>CSV files contain the underlying summaries and leaderboards used in this report.</p>
        </div>
        {_downloads(csv_files)}
      </section>

      <section class="method-note" aria-labelledby="method-title">
        <h2 id="method-title">Source and method</h2>
        <p>Data comes from YouGov's public UK voting-intention tracker. This report describes tracker responses and demographic breakdowns; it is not an election forecast or a seat projection. Support changes are percentage-point differences. The analysis avoids comparing across long gaps in the polling series.</p>
        <p>Regional results for SNP are shown for Scotland only, and Plaid Cymru results for Wales only. Their other demographic breakdowns remain UK-wide.</p>
        <p><a href="https://api-test.yougov.com/public-data/v5/uk/trackers/voting-intention/download/">YouGov tracker download</a> · <a href="https://github.com/data-john/voting-intention-analysis">Analysis code and methodology</a></p>
      </section>
    </div>
  </main>
  <dialog class="chart-dialog" aria-label="Expanded chart" data-chart-dialog>
    <div class="dialog-toolbar">
      <p data-dialog-caption></p>
      <div class="zoom-controls" aria-label="Chart zoom controls">
        <button type="button" data-zoom-out aria-label="Zoom out">−</button>
        <button type="button" data-zoom-fit>Fit</button>
        <button type="button" data-zoom-in aria-label="Zoom in">+</button>
        <output data-zoom-level aria-live="polite">Fit</output>
        <span class="pan-hint" data-pan-hint hidden>Drag the chart to pan</span>
      </div>
      <button type="button" data-close-dialog>Close chart</button>
    </div>
    <div class="dialog-image-viewport" data-dialog-viewport>
      <img data-dialog-image alt="" draggable="false">
    </div>
  </dialog>
  <footer class="site-footer">
    <div class="content footer-inner">
      <span>Election Models · UK voting intention tracker</span>
      <a href="#top">Back to top ↑</a>
    </div>
  </footer>
  <script src="assets/report.js" defer></script>
</body>
</html>
    """
    (SITE_DIR / "index.html").write_text(report, encoding="utf-8")
    yougov_dir = SITE_DIR / "yougov"
    yougov_dir.mkdir()
    shutil.copytree(SITE_DIR / "assets", yougov_dir / "assets")
    shutil.copytree(SITE_DIR / "downloads", yougov_dir / "downloads")
    shutil.copy2(SITE_DIR / "index.html", yougov_dir / "index.html")

    print(f"Built static report at {SITE_DIR} and {yougov_dir}")
    print(f"Poll data through {_format_date(latest_date)}; checked {checked_label}.")
    print(f"Copied {len(figure_files)} figures and {len(csv_files)} CSV tables.")
    return SITE_DIR


def _format_date(value: str) -> str:
    try:
        date = datetime.fromisoformat(value)
        return f"{date.day} {date.strftime('%B %Y')}"
    except ValueError:
        return value


if __name__ == "__main__":
    try:
        build_site()
    except (FileNotFoundError, ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
