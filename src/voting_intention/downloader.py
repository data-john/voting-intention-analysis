"""
Download the latest YouGov UK voting-intention tracker workbook directly
from YouGov's public data API, so a new poll wave can be picked up with one
command instead of manually downloading and moving a file into data/.

YouGov's tracker download always returns the full current workbook (every
week to date), not just new rows. This overwrites a single canonical file
(data/voting-intention.xlsx by default) rather than accumulating one dated
file per download. The previous version is copied into data/_archive/ first
(unless archive=False), and that folder is ignored by the loader.

If the download is byte-identical to what's already there, nothing is
overwritten and no archive copy is made.
"""
from __future__ import annotations

import hashlib
import io
import shutil
import time
import zipfile
from datetime import date
from pathlib import Path

import requests

from . import freshness

# The public download link for YouGov's UK voting-intention tracker.
YOUGOV_VOTING_INTENTION_URL = (
    "https://api-test.yougov.com/public-data/v5/uk/trackers/voting-intention/download/"
)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_valid_xlsx(content: bytes) -> bool:
    """Reject HTML error pages and truncated/non-Excel responses."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as workbook:
            return "xl/workbook.xml" in workbook.namelist()
    except zipfile.BadZipFile:
        return False


def _download_content(url: str, timeout: int, max_attempts: int) -> bytes | None:
    """Retry transient network/server failures with a short exponential backoff."""
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            status = (
                exc.response.status_code
                if isinstance(exc, requests.HTTPError) and exc.response is not None
                else None
            )
            retryable = status is None or status in (408, 429) or (status is not None and status >= 500)
            if not retryable or attempt == max_attempts:
                print(f"Could not download {url} after {attempt} attempt(s): {exc}")
                return None

            delay = 2 ** (attempt - 1)
            if exc.response is not None:
                try:
                    retry_after = int(exc.response.headers.get("Retry-After", "0"))
                    delay = max(delay, min(retry_after, 30))
                except ValueError:
                    pass
            print(f"Download attempt {attempt} failed ({exc}); retrying in {delay}s.")
            time.sleep(delay)

    return None


def download_latest(
    data_dir: str = "data",
    filename: str = "voting-intention.xlsx",
    url: str = YOUGOV_VOTING_INTENTION_URL,
    archive: bool = True,
    timeout: int = 30,
    max_attempts: int = 4,
) -> Path | None:
    """Fetch the current tracker workbook and save it to data_dir/filename.

    Returns the path written to, or None if the request failed. A response is
    validated before the existing workbook is archived or replaced.
    """
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    target = data_path / filename

    content = _download_content(url, timeout=timeout, max_attempts=max_attempts)
    if not content:
        print("Download returned no content; nothing was saved.")
        return None
    if not _is_valid_xlsx(content):
        print("Download was not a valid Excel workbook; nothing was saved.")
        return None

    content_hash = _hash_bytes(content)
    temporary = target.with_name(f".{target.name}.download")
    try:
        temporary.write_bytes(content)
        receipt = freshness.workbook_receipt(temporary, url)
        if target.exists():
            previous = freshness.workbook_receipt(target, url)
            if receipt["latest_poll_date"] < previous["latest_poll_date"]:
                raise ValueError("Downloaded poll date is older than the existing workbook.")
            if _hash_bytes(target.read_bytes()) == content_hash:
                freshness.write_json(target.with_suffix(".check.json"), receipt)
                print(f"Source checked successfully; latest poll {receipt['latest_poll_date']}. Workbook unchanged.")
                return target
        if target.exists() and archive:
            archive_dir = data_path / "_archive"
            archive_dir.mkdir(exist_ok=True)
            backup_path = archive_dir / f"{target.stem}_{date.today().isoformat()}{target.suffix}"
            shutil.copy2(target, backup_path)
            print(f"Archived previous version to {backup_path}")

        temporary.replace(target)
        freshness.write_json(target.with_suffix(".check.json"), receipt)
    finally:
        temporary.unlink(missing_ok=True)

    print(f"Downloaded latest data -> {target}  ({len(content):,} bytes)")
    return target


if __name__ == "__main__":
    download_latest()
