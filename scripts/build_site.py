#!/usr/bin/env python3
"""Build the static public report from the saved figures and tables."""
from __future__ import annotations

import csv
import html
import math
import os
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
    "change_heatmap_grid.png",
    "change_heatmap_12w.png",
    "grid_age.png",
    "grid_gender.png",
    "grid_region.png",
    "grid_social_grade.png",
    "grid_eu_ref_vote.png",
    "grid_past_vote.png",
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
        cells = "".join(
            f"<td>{_escape(row.get(field, '') or '—')}</td>" for field in fields
        )
        body.append(f"<tr>{cells}</tr>")
    return (
        '<div class="table-scroll">'
        f'<table class="{_escape(class_name)}"><caption>{_escape(caption)}</caption>'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"
        "</div>"
    )


def _image(filename: str, title: str, alt: str, caption: str = "") -> str:
    return (
        '<figure class="chart">'
        f'<a href="assets/figures/{_escape(filename)}" aria-label="Open { _escape(title) } image">'
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
            f'<article class="party-card" style="--party-color:{_escape(color)}">'
            f'<h3>{_escape(label)}</h3>'
            f'<p class="party-value">{_percent(float(row["latest"]) * 100)}</p>'
            f'<p class="party-change">4-week change: {_escape(change)}</p>'
            "</article>"
        )
    return f'<div class="party-grid">{"".join(cards)}</div>'


def _headline_cards(rows: list[dict[str, str]]) -> str:
    cards = []
    for row in rows:
        party = row.get("party", "")
        label = config.PARTY_LABELS.get(party, party)
        color = config.PARTY_COLORS.get(party, "#555555")
        movements = []
        for weeks in (4, 12, 52):
            gain_group = row.get(f"most_gaining_group_{weeks}w", "")
            loss_group = row.get(f"most_losing_group_{weeks}w", "")
            movements.append(
                "<tr>"
                f"<th scope=\"row\">{weeks} weeks</th>"
                f"<td>{_escape(gain_group) or '—'}</td>"
                f"<td>{_escape(_percentage_points(row.get(f'gaining_{weeks}w_pp')))}</td>"
                f"<td>{_escape(loss_group) or '—'}</td>"
                f"<td>{_escape(_percentage_points(row.get(f'losing_{weeks}w_pp')))}</td>"
                "</tr>"
            )
        cards.append(
            f'<article class="headline-card" style="--party-color:{_escape(color)}">'
            f'<h3>{_escape(label)}</h3>'
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


def _category_sections() -> str:
    sections = []
    for slug, title in CATEGORIES:
        filename = f"grid_{slug}.png"
        leaderboard = _read_csv(TABLES_DIR / f"leaderboard_{slug}.csv")
        alt = f"Party voting intention trends across {title.lower()} groups"
        sections.append(
            f'<details class="category-panel" id="{_escape(slug)}">'
            f"<summary>{_escape(title)} <span>View charts and table</span></summary>"
            f'<div class="category-content">{_image(filename, f"Voting intention by {title.lower()}", alt)}'
            f'{_table(leaderboard, f"{title} leaderboard")}'
            "</div></details>"
        )
    return "".join(sections)


def _validate_inputs() -> tuple[list[dict[str, str]], list[Path], list[Path]]:
    missing_figures = [name for name in REQUIRED_FIGURES if not (FIGURES_DIR / name).is_file()]
    missing_tables = [name for name in REQUIRED_TABLES if not (TABLES_DIR / name).is_file()]
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

    figure_files = sorted(FIGURES_DIR.glob("*.png"))
    csv_files = sorted(TABLES_DIR.glob("*.csv"))
    return summary, figure_files, csv_files


def build_site() -> Path:
    summary, figure_files, csv_files = _validate_inputs()
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
    )
    change_grid = _image(
        "change_heatmap_grid.png",
        "Support changes by group",
        "Changes in party support across demographic groups over four, twelve and fifty-two weeks, in percentage points.",
    )
    change_12w = _image(
        "change_heatmap_12w.png",
        "Twelve-week change by group",
        "Twelve-week changes in party support across demographic groups, in percentage points.",
    )

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
        {_national_cards(national_rows)}
        {national_trend}
      </section>

      <section class="report-section" id="demographics">
        <div class="section-heading">
          <p class="eyebrow">Across the electorate</p>
          <h2>Where parties are strongest, and where support is moving</h2>
          <p>These comparisons cover age, gender, region, social grade and EU referendum vote. Past-vote groups are shown separately below.</p>
        </div>
        {_headline_cards(headlines)}
      </section>

      <section class="report-section chart-section" id="groups">
        <div class="section-heading">
          <p class="eyebrow">Explore the breakdowns</p>
          <h2>Support by group</h2>
          <p>Open a category to see its time-series charts and current party leaderboard.</p>
        </div>
        <div class="category-list">{_category_sections()}</div>
      </section>

      <section class="report-section">
        <div class="section-heading">
          <p class="eyebrow">Movement</p>
          <h2>How support is changing</h2>
          <p>Changes are shown in percentage points. Each panel uses its own colour scale.</p>
        </div>
        {change_grid}
        <div class="visual-pair">
          {latest_heatmap}
          {change_12w}
        </div>
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
        <p><a href="https://api-test.yougov.com/public-data/v5/uk/trackers/voting-intention/download/">YouGov tracker download</a> · <a href="https://github.com/data-john/voting-intention-analysis">Analysis code and methodology</a></p>
      </section>
    </div>
  </main>
  <footer class="site-footer">
    <div class="content footer-inner">
      <span>Election Models · UK voting intention tracker</span>
      <a href="#top">Back to top ↑</a>
    </div>
  </footer>
</body>
</html>
"""
    (SITE_DIR / "index.html").write_text(report, encoding="utf-8")
    print(f"Built static report at {SITE_DIR}")
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
