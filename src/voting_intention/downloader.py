"""
Download the latest YouGov UK voting-intention tracker workbook directly
from YouGov's public data API, so a new poll wave can be picked up with one
command instead of manually downloading and moving a file into data/.

YouGov's tracker download always returns the *full* current workbook (every
week to date), not just new rows -- so this overwrites a single canonical
file (`data/voting-intention.xlsx` by default) rather than accumulating one
dated file per download. The previous version is copied into
`data/_archive/` first (unless `archive=False`), and that folder is ignored
by the loader (which only looks directly inside `data/`), so archived
snapshots never cause duplicate rows in the analysis.

If the download is byte-identical to what's already there (i.e. no new poll
has been published since you last ran this), nothing is overwritten and no
archive copy is made.
"""
from __future__ import annotations

import hashlib
import shutil
from datetime import date
from pathlib import Path

import requests

# The public download link for YouGov's UK voting-intention tracker. The
# query string on the link YouGov's site gives you (?_gl=...&_ga=...) is
# just Google Analytics tracking and isn't needed for the download itself.
YOUGOV_VOTING_INTENTION_URL = (
    "https://api-test.yougov.com/public-data/v5/uk/trackers/voting-intention/download/"
)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_latest(
    data_dir: str = "data",
    filename: str = "voting-intention.xlsx",
    url: str = YOUGOV_VOTING_INTENTION_URL,
    archive: bool = True,
    timeout: int = 30,
) -> Path | None:
    """Fetch the current tracker workbook and save it to `data_dir/filename`.

    Returns the path written to, or None if the request failed. Prints a
    one-line status either way so it's clear what happened when run from a
    script or notebook cell.
    """
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    target = data_path / filename

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Could not download {url}: {exc}")
        return None

    content = response.content
    if not content:
        print("Download returned no content -- something's wrong upstream; nothing was saved.")
        return None

    if target.exists():
        if _hash_bytes(target.read_bytes()) == _hash_bytes(content):
            print(f"{target} is already up to date -- no new poll since your last download.")
            return target
        if archive:
            archive_dir = data_path / "_archive"
            archive_dir.mkdir(exist_ok=True)
            backup_path = archive_dir / f"{target.stem}_{date.today().isoformat()}{target.suffix}"
            shutil.copy2(target, backup_path)
            print(f"Archived previous version to {backup_path}")

    target.write_bytes(content)
    print(f"Downloaded latest data -> {target}  ({len(content):,} bytes)")
    return target


if __name__ == "__main__":
    download_latest()
