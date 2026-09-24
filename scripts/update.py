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
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from voting_intention import downloader  # noqa: E402
import refresh_outputs  # noqa: E402


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
    args = parser.parse_args()

    downloaded = downloader.download_latest(
        data_dir=str(REPO_ROOT / "data"),
        filename=args.filename,
        url=args.url,
        archive=not args.no_archive,
    )
    if downloaded is None:
        print("Skipping refresh: download failed. Check your internet connection and try again, "
              "or run scripts/refresh_outputs.py directly if data/ is already up to date.")
        return

    refresh_outputs.run(trailing_weeks=args.weeks)


if __name__ == "__main__":
    main()
