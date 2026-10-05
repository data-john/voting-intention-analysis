#!/usr/bin/env python3
"""Confirm the public report serves the exact source check that was just deployed."""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests


def verify(base_url: str, expected: dict) -> None:
    for prefix in ("", "yougov/"):
        url = f"{base_url.rstrip('/')}/{prefix}"
        response = requests.get(url + "status.json", params={"check": time.time_ns()},
                                headers={"Cache-Control": "no-cache"}, timeout=20)
        response.raise_for_status()
        actual = response.json()
        for field in ("checked_at", "source_sha256", "latest_poll_date", "run_id", "commit_sha"):
            if actual.get(field) != expected.get(field):
                raise ValueError(f"{url} has not published the expected {field}.")
        response = requests.get(url, params={"check": time.time_ns()}, timeout=20)
        response.raise_for_status()
        timestamps = re.findall(r'<time[^>]*datetime="([^"]+)"', response.text)
        if expected["latest_poll_date"] not in timestamps:
            raise ValueError(f"{url} HTML has the wrong poll date.")
        if not any(datetime.fromisoformat(t) == datetime.fromisoformat(expected["checked_at"])
                   for t in timestamps if "T" in t):
            raise ValueError(f"{url} HTML has the wrong source-check timestamp.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://electionmodels.com")
    parser.add_argument("--status", type=Path, default=Path("site/status.json"))
    parser.add_argument("--attempts", type=int, default=12)
    args = parser.parse_args()
    expected = json.loads(args.status.read_text(encoding="utf-8"))
    if not expected.get("checked_at"):
        raise SystemExit("Cannot verify publication without a successful source check.")
    for attempt in range(args.attempts):
        try:
            verify(args.base_url, expected)
            print(f"Verified root and /yougov/: poll {expected['latest_poll_date']}, check {expected['checked_at']}.")
            return
        except (requests.RequestException, ValueError) as exc:
            if attempt == args.attempts - 1:
                raise SystemExit(f"Public report verification failed: {exc}") from exc
            print(f"Waiting for public deployment ({exc}).")
            time.sleep(10)


if __name__ == "__main__":
    main()
