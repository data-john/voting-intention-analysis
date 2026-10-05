#!/usr/bin/env python3
"""
One-command update: download the latest YouGov tracker workbook into data/,
then regenerate every chart and summary table. This is what you want when a
new poll comes out and you just want everything refreshed.

Usage:
    python scripts/update.py
    python scripts/update.py --weeks 4 12 52
    python scripts/update.py --url https://...   # override the download URL
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from voting_intention import downloader  # noqa: E402
import refresh_outputs  # noqa: E402
import requests  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--weeks", type=int, nargs="+", default=[4, 12, 52],
        help="Trailing windows (in weeks) for the gaining/losing calculations.",
    )
    parser.add_argument(
        "--url", default=downloader.YOUGOV_VOTING_INTENTION_URL,
        help="Override the download URL (defaults to YouGov's voting-intention tracker).",
    )
    parser.add_argument(
        "--filename", default="voting-intention.xlsx",
        help="Filename to save into data/ (default: voting-intention.xlsx).",
    )
    parser.add_argument(
        "--no-archive", action="store_true",
        help="Don't keep a backup copy of the previous version in data/_archive/.",
    )
    parser.add_argument("--published-status-url", help="Reject source dates older than this published status.json.")
    args = parser.parse_args()

    published = None
    if args.published_status_url:
        response = requests.get(args.published_status_url, timeout=30, headers={"Cache-Control": "no-cache"})
        if response.status_code != 404:  # Allow the first deployment of status.json.
            response.raise_for_status()
            published = response.json()

    downloaded = downloader.download_latest(
        data_dir=str(REPO_ROOT / "data"),
        filename=args.filename,
        url=args.url,
        archive=not args.no_archive,
    )
    if downloaded is None:
        raise SystemExit(
            "Could not download the latest YouGov workbook. Outputs were not refreshed. "
            "Check the connection or run scripts/refresh_outputs.py if local data is current."
        )

    receipt = json.loads(downloaded.with_suffix(".check.json").read_text(encoding="utf-8"))
    if published and receipt["latest_poll_date"] < published["latest_poll_date"]:
        raise SystemExit("YouGov returned an older poll than the live report; refusing to publish a regression.")
    refresh_outputs.run(trailing_weeks=args.weeks, source_workbook=downloaded)


if __name__ == "__main__":
    main()
