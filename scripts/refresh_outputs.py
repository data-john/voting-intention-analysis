#!/usr/bin/env python3
"""
Regenerate every chart and summary table from whatever workbook(s) are
currently in data/, without needing to open Jupyter.

Usage (from the repo root):
    python scripts/refresh_outputs.py
    python scripts/refresh_outputs.py --weeks 4 12 52   # customise the trailing windows
    python scripts/refresh_outputs.py --fetch           # also download the latest YouGov data first

Run this any time you add a new poll-tracker workbook to data/, or use
`scripts/update.py` to fetch + refresh in one step.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import matplotlib

matplotlib.use("Agg")  # no display needed for a script

from voting_intention import loader, analysis, plotting  # noqa: E402

CATEGORIES = ["Age", "Gender", "Region", "Social Grade", "EU Ref Vote", "Past Vote"]


def run(trailing_weeks: list[int] = (4, 12, 52)) -> None:
    """Reload every workbook in data/ and regenerate all figures/tables."""
    trailing_weeks = list(trailing_weeks)

    data_dir = REPO_ROOT / "data"
    fig_dir = REPO_ROOT / "outputs" / "figures"
    table_dir = REPO_ROOT / "outputs" / "tables"
    fig_dir.mkdir(parents=True, exist_ok=True)
    table_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading workbooks from {data_dir} ...")
    df = loader.load_all(str(data_dir))
    print(f"  {len(df):,} rows | {df['category'].nunique()} categories | "
          f"{df['group'].nunique()} groups | {df['party'].nunique()} parties")
    print(loader.coverage_report(df))
    print(f"Trailing windows: {trailing_weeks} weeks")

    summary = analysis.build_summary(df, trailing_weeks=trailing_weeks)
    summary.to_csv(table_dir / "summary_all_groups.csv", index=False)

    headline_all = analysis.headline_table(summary, trailing_weeks=trailing_weeks)
    headline_all.to_csv(table_dir / "headline_all_breakdowns.csv")

    headline_demo = analysis.headline_table(
        summary, trailing_weeks=trailing_weeks, exclude_categories=("Overall", "Past Vote")
    )
    headline_demo.to_csv(table_dir / "headline_demographics_only.csv")

    retention = analysis.vote_retention_table(summary, trailing_weeks=trailing_weeks)
    retention.to_csv(table_dir / "vote_retention.csv")

    plotting.plot_overall_trend(df, save_path=str(fig_dir / "overall_trend.png"))
    plotting.plot_latest_heatmap(summary, save_path=str(fig_dir / "latest_heatmap.png"))
    plotting.plot_change_heatmap_grid(
        summary, trailing_weeks=trailing_weeks, save_path=str(fig_dir / "change_heatmap_grid.png")
    )
    # Also save a single-window change heatmap for the middle window, for reports
    # that just want one figure.
    mid_window = trailing_weeks[len(trailing_weeks) // 2]
    plotting.plot_change_heatmap(
        summary, trailing_weeks=mid_window, save_path=str(fig_dir / f"change_heatmap_{mid_window}w.png")
    )

    for category in CATEGORIES:
        fname = category.lower().replace(" ", "_")
        plotting.plot_category_grid(df, category, save_path=str(fig_dir / f"grid_{fname}.png"))
        board = analysis.category_leaderboard(summary, category, trailing_weeks=trailing_weeks)
        board.to_csv(table_dir / f"leaderboard_{fname}.csv")

    print(f"Done. Figures -> {fig_dir}, tables -> {table_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--weeks",
        type=int,
        nargs="+",
        default=[4, 12, 52],
        help="Trailing windows (in weeks) for the gaining/losing calculations, e.g. --weeks 4 12 52",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Download the latest YouGov tracker workbook into data/ before refreshing",
    )
    args = parser.parse_args()

    if args.fetch:
        from voting_intention import downloader

        if downloader.download_latest(data_dir=str(REPO_ROOT / "data")) is None:
            raise SystemExit("Could not fetch the latest YouGov workbook; outputs were not refreshed.")

    run(trailing_weeks=args.weeks)


if __name__ == "__main__":
    main()
