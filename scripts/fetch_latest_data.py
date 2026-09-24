#!/usr/bin/env python3
"""
Download the latest YouGov UK voting-intention tracker workbook into data/,
without regenerating charts/tables. Use `scripts/update.py` if you want both
in one step.

Usage:
    python scripts/fetch_latest_data.py
    python scripts/fetch_latest_data.py --url https://...   # override the download URL
    python scripts/fetch_latest_data.py --no-archive        # overwrite without keeping a backup copy
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from voting_intention import downloader  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=downloader.YOUGOV_VOTING_INTENTION_URL,
        help="Override the download URL (defaults to YouGov's voting-intention tracker).",
    )
    parser.add_argument(
        "--filename",
        default="voting-intention.xlsx",
        help="Filename to save into data/ (default: voting-intention.xlsx).",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Don't keep a backup copy of the previous version in data/_archive/.",
    )
    args = parser.parse_args()

    downloader.download_latest(
        data_dir=str(REPO_ROOT / "data"),
        filename=args.filename,
        url=args.url,
        archive=not args.no_archive,
    )


if __name__ == "__main__":
    main()
