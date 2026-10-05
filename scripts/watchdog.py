#!/usr/bin/env python3
"""Independent check of YouGov, the public report and GitHub; optionally repair gaps.

Run from a scheduler outside GitHub Actions. Uses the existing gh login for dispatch.
It never changes polling data in the repository or substitutes a stale local workbook.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
from voting_intention import downloader, freshness  # noqa: E402

STATE_PATH = REPO_ROOT / "outputs" / "watchdog_state.json"
REPOSITORY = "data-john/voting-intention-analysis"
WORKFLOW = "publish-report.yml"


def gh(*args: str):
    result = subprocess.run(["gh", *args], text=True, capture_output=True, timeout=45, check=True)
    return result.stdout


def repair_reason(public: dict, source: dict, now: datetime) -> str | None:
    if not public.get("checked_at"):
        return "The public report has no verified source-check receipt."
    checked = datetime.fromisoformat(public["checked_at"])
    if checked.tzinfo is None or checked > now:
        raise ValueError("Public source-check timestamp is invalid.")
    if public["latest_poll_date"] > source["latest_poll_date"]:
        raise ValueError("YouGov is returning older data than the published report; refusing a rollback.")
    if public["latest_poll_date"] < source["latest_poll_date"]:
        return f"New YouGov poll {source['latest_poll_date']} is missing from the public report."
    if (now - checked).total_seconds() > freshness.max_check_age_hours(now) * 3600:
        return f"The last published source check is overdue ({public['checked_at']})."
    return None


def check(repair: bool, state: dict) -> dict:
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="yougov-watchdog-") as directory:
        workbook = downloader.download_latest(data_dir=directory, archive=False)
        if workbook is None:
            raise RuntimeError("Independent YouGov download failed.")
        source = freshness.matching_receipt(workbook)
    response = requests.get("https://electionmodels.com/yougov/status.json",
                            params={"check": now.timestamp()}, timeout=30)
    if response.status_code == 404:
        public = {}
    else:
        response.raise_for_status()
        public = response.json()
    reason = repair_reason(public, source, now)
    if not reason:
        return {"result": "healthy", "checked_at": now.isoformat(),
                "latest_poll_date": source["latest_poll_date"]}
    print(reason)
    if not repair:
        return {"result": "overdue", "reason": reason, "checked_at": now.isoformat()}
    runs = json.loads(gh("run", "list", "--repo", REPOSITORY, "--workflow", WORKFLOW,
                         "--limit", "10", "--json", "databaseId,status,createdAt,conclusion,url"))
    active = [run for run in runs if run["status"] != "completed"]
    if active:
        oldest = min(datetime.fromisoformat(run["createdAt"].replace("Z", "+00:00")) for run in active)
        if (now - oldest).total_seconds() > 30 * 60:
            raise RuntimeError(f"Publishing has been stuck for over 30 minutes: {active[0]['url']}")
        return {"result": "pending", "reason": reason, "run_url": active[0]["url"],
                "checked_at": now.isoformat(), "last_dispatch_at": state.get("last_dispatch_at")}
    previous_dispatch = state.get("last_dispatch_at")
    if previous_dispatch:
        elapsed = (now - datetime.fromisoformat(previous_dispatch)).total_seconds()
        if elapsed < 25 * 60:
            return dict(state, result="pending", checked_at=now.isoformat())
        if runs and runs[0]["conclusion"] != "success":
            print(f"Previous publishing attempt failed: {runs[0]['url']}", file=sys.stderr)
            notify(f"The previous polling report update failed. Retrying. {runs[0]['url']}")
    gh("workflow", "run", WORKFLOW, "--repo", REPOSITORY, "--ref", "main")
    print("Dispatched a replacement source check and publication through GitHub Actions.")
    return {"result": "dispatched", "reason": reason, "checked_at": now.isoformat(),
            "last_dispatch_at": now.isoformat(), "latest_poll_date": source["latest_poll_date"]}


def notify(message: str) -> None:
    try:
        subprocess.run(["notify-send", "Voting intention report", message], timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass  # The error is still retained in state and the scheduler journal.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    try:
        result = check(args.repair, state)
        if state.get("result") == "error" and result["result"] == "healthy":
            notify("The report's source checks have recovered.")
        freshness.write_json(STATE_PATH, result)
        print(json.dumps(result))
    except Exception as exc:
        reason = str(exc)
        if state.get("error") != reason:
            notify(f"Source checks need attention: {reason}")
        freshness.write_json(STATE_PATH, dict(state, result="error", error=reason,
                                             checked_at=datetime.now(timezone.utc).isoformat()))
        raise SystemExit(reason) from exc


if __name__ == "__main__":
    main()
