"""Failure cases that could otherwise silently publish or accept stale data."""
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from voting_intention import downloader, freshness, loader
import watchdog
import build_site
import verify_publication


def workbook(date="2026-09-28", parties=None):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "All adults"
    sheet.append(["Voting intention", date])
    for party in (loader.PARTY_ROWS if parties is None else parties):
        sheet.append([party, 0.125])
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


class FreshnessTests(unittest.TestCase):
    def test_unchanged_download_records_new_successful_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voting-intention.xlsx"
            content = workbook()
            path.write_bytes(content)
            with patch.object(downloader, "_download_content", return_value=content):
                self.assertEqual(downloader.download_latest(directory), path)
            receipt = freshness.matching_receipt(path)
            self.assertEqual(receipt["latest_poll_date"], "2026-09-28")
            self.assertFalse((Path(directory) / "_archive").exists())

    def test_failed_or_invalid_download_never_updates_receipt_or_workbook(self):
        for content in (None, b"<html>error</html>", workbook(parties=["Lab"])):
            with self.subTest(content_type=type(content).__name__), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "voting-intention.xlsx"
                original = workbook()
                path.write_bytes(original)
                receipt = freshness.workbook_receipt(path, "source")
                freshness.write_json(path.with_suffix(".check.json"), receipt)
                with patch.object(downloader, "_download_content", return_value=content):
                    if content and content.startswith(b"PK"):
                        with self.assertRaises(ValueError):
                            downloader.download_latest(directory)
                    else:
                        self.assertIsNone(downloader.download_latest(directory))
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(freshness.matching_receipt(path), receipt)

    def test_download_regression_preserves_current_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voting-intention.xlsx"
            original = workbook()
            path.write_bytes(original)
            with patch.object(downloader, "_download_content", return_value=workbook("2026-09-21")):
                with self.assertRaisesRegex(ValueError, "older"):
                    downloader.download_latest(directory)
            self.assertEqual(path.read_bytes(), original)

    def test_manually_replaced_workbook_invalidates_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voting-intention.xlsx"
            path.write_bytes(workbook())
            freshness.write_json(path.with_suffix(".check.json"), freshness.workbook_receipt(path, "source"))
            path.write_bytes(workbook("2026-09-21"))
            with self.assertRaisesRegex(ValueError, "changed"):
                freshness.matching_receipt(path)

    def test_watchdog_distinguishes_missing_check_from_no_new_poll(self):
        now = datetime(2026, 10, 5, 15, tzinfo=timezone.utc)
        source = {"latest_poll_date": "2026-09-28"}
        public = dict(source, checked_at="2026-10-05T14:00:00+00:00")
        self.assertIsNone(watchdog.repair_reason(public, source, now))
        public["checked_at"] = "2026-10-05T07:08:00+00:00"
        self.assertIn("overdue", watchdog.repair_reason(public, source, now))
        self.assertIn("New YouGov", watchdog.repair_reason(public, {"latest_poll_date": "2026-10-05"}, now))
        with self.assertRaisesRegex(ValueError, "rollback"):
            watchdog.repair_reason(public, {"latest_poll_date": "2026-09-21"}, now)

    def test_build_cannot_invent_source_check(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = [{"category": "Overall", "group": "All adults", "party": "Lab", "latest_date": "2026-09-28"}]
            with patch.object(build_site, "REPO_ROOT", Path(directory)), \
                 patch.object(build_site, "_validate_inputs", return_value=(summary, [], [], [])), \
                 patch.object(build_site, "_read_csv", return_value=[]):
                with self.assertRaisesRegex(ValueError, "verified source check"):
                    build_site.build_site(require_source_check=True)

    def test_publication_verification_rejects_old_status(self):
        expected = {"checked_at": "2026-10-05T15:00:00+00:00", "latest_poll_date": "2026-09-28"}
        with patch.object(verify_publication.requests, "get") as get:
            get.return_value.json.return_value = dict(expected, checked_at="2026-10-05T07:08:00+00:00")
            with self.assertRaisesRegex(ValueError, "checked_at"):
                verify_publication.verify("https://example.test", expected)

    def test_watchdog_dispatches_missed_check_and_does_not_duplicate_active_run(self):
        source = {"latest_poll_date": "2026-09-28"}
        active_run = {"status": "in_progress", "createdAt": datetime.now(timezone.utc).isoformat(),
                      "url": "https://github.com/example/run/1"}
        for runs, expected in (([], "dispatched"), ([active_run], "pending")):
            with self.subTest(expected=expected), \
                 patch.object(watchdog.downloader, "download_latest", return_value=Path("unused.xlsx")), \
                 patch.object(watchdog.freshness, "matching_receipt", return_value=source), \
                 patch.object(watchdog.requests, "get") as get, \
                 patch.object(watchdog, "gh") as gh:
                get.return_value.status_code = 404
                gh.return_value = json.dumps(runs)
                self.assertEqual(watchdog.check(True, {})["result"], expected)
                dispatched = any(call.args[0] == "workflow" for call in gh.call_args_list)
                self.assertEqual(dispatched, expected == "dispatched")


if __name__ == "__main__":
    unittest.main()
