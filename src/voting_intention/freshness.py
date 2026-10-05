"""Evidence of successful source checks, separate from report build times."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import loader


def workbook_receipt(path: Path, source_url: str) -> dict:
    data = loader.load_workbook_long(str(path))
    national = data.loc[data["category"] == "Overall"]
    if national.empty:
        raise ValueError("Source workbook has no national voting-intention data.")
    latest = national["date"].max()
    rows = national.loc[national["date"] == latest]
    if set(rows["party"]) != set(loader.PARTY_ROWS):
        raise ValueError("Latest national poll is missing one or more parties.")
    if not rows["value"].between(0, 1).all():
        raise ValueError("Latest national poll contains invalid vote shares.")
    if latest.date() > datetime.now(timezone.utc).date():
        raise ValueError("Source workbook contains a future poll date.")
    return {
        "schema_version": 1,
        "source_url": source_url,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "latest_poll_date": latest.date().isoformat(),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def matching_receipt(workbook: Path) -> dict | None:
    receipt_path = workbook.with_suffix(".check.json")
    if not receipt_path.exists():
        return None
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["source_sha256"] != hashlib.sha256(workbook.read_bytes()).hexdigest():
        raise ValueError("Workbook has changed since the recorded source check; fetch it again.")
    checked = datetime.fromisoformat(receipt["checked_at"])
    if checked.tzinfo is None or checked > datetime.now(timezone.utc):
        raise ValueError("Source check timestamp is invalid.")
    return receipt


def max_check_age_hours(now: datetime) -> int:
    """Two hours on UK Mondays, seven on other days; allow normal job delays."""
    from zoneinfo import ZoneInfo

    return 2 if now.astimezone(ZoneInfo("Europe/London")).weekday() == 0 else 7
