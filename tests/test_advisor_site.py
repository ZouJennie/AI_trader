import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.daily_run_gate import should_run
from scripts.export_advisor_site import extract_prices, latest_recommendations
from scripts.validate_market_snapshot import current_symbols, rejection_reason


class AdvisorSiteTests(unittest.TestCase):
    def test_recommendations_are_deduplicated_by_date(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recommendations.jsonl"
            records = [
                {"date": "2026-08-26", "content": "old", "signature": "deepseek-v4-flash"},
                {"date": "2026-08-26", "content": "corrected", "signature": "deepseek-v4-flash"},
                {"date": "2026-08-27", "content": "latest", "signature": "deepseek-v4-flash"},
            ]
            path.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
            result = latest_recommendations(path)
        self.assertEqual([item["date"] for item in result], ["2026-08-26", "2026-08-27"])
        self.assertEqual(result[0]["content"], "corrected")

    def test_recommendation_export_removes_finish_signal_and_marks_advisory_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recommendations.jsonl"
            path.write_text(
                json.dumps({"date": "2026-08-28", "content": "DECISION: BUY\n<FINISH_SIGNAL>", "execution_mode": "advisory"}),
                encoding="utf-8",
            )
            result = latest_recommendations(path)
        self.assertEqual(result[0]["content"], "DECISION: BUY")
        self.assertEqual(result[0]["execution_status"], "not_executed")

    def test_latest_market_price_prefers_sell_price(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "merged.jsonl"
            document = {
                "Meta Data": {"2. Symbol": "AAPL"},
                "Time Series (60min)": {
                    "2026-08-27 09:00:00": {"4. sell price": "200"},
                    "2026-08-27 10:00:00": {"1. buy price": "201", "4. sell price": "202"},
                },
            }
            path.write_text(json.dumps(document), encoding="utf-8")
            result = extract_prices(path)
        self.assertEqual(result["AAPL"], {"price": 202.0, "timestamp": "2026-08-27 10:00:00"})

    def test_schedule_gate_handles_new_york_daylight_time(self):
        summer = datetime(2026, 8, 27, 14, 15, tzinfo=ZoneInfo("UTC"))
        winter = datetime(2026, 1, 5, 15, 15, tzinfo=ZoneInfo("UTC"))
        wrong_winter_slot = datetime(2026, 1, 5, 14, 15, tzinfo=ZoneInfo("UTC"))
        self.assertTrue(should_run("schedule", summer))
        self.assertTrue(should_run("schedule", winter))
        self.assertFalse(should_run("schedule", wrong_winter_slot))
        self.assertTrue(should_run("workflow_dispatch", wrong_winter_slot))

    def test_market_snapshot_ignores_stale_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "merged.jsonl"
            documents = [
                {"Meta Data": {"2. Symbol": "AAPL"}, "Time Series (60min)": {"2026-08-27 10:00:00": {}}},
                {"Meta Data": {"2. Symbol": "MSFT"}, "Time Series (60min)": {"2026-08-26 15:00:00": {}}},
            ]
            path.write_text("\n".join(json.dumps(item) for item in documents), encoding="utf-8")
            result = current_symbols(path, "2026-08-27")
            self.assertEqual(result, {"AAPL"})

    def test_market_snapshot_explains_premarket_rejection(self):
        before_open = datetime(2026, 8, 28, 7, 43, tzinfo=ZoneInfo("UTC"))
        reason = rejection_reason("2026-08-28", before_open)
        self.assertIn("09:35", reason)
        self.assertIn("03:43", reason)


if __name__ == "__main__":
    unittest.main()
