import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from agent_tools import tool_trade


class TradeByAmountTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.position_file = Path(self.temp_dir.name) / "position.jsonl"

    def tearDown(self):
        self.temp_dir.cleanup()

    def read_record(self):
        return json.loads(self.position_file.read_text(encoding="utf-8").strip())

    def test_fractional_buy_preserves_cash_and_records_fee(self):
        with (
            patch.object(tool_trade, "_position_lock", return_value=nullcontext()),
            patch.object(tool_trade, "_position_file_path", return_value=str(self.position_file)),
            patch.object(tool_trade, "get_latest_position", return_value=({"CASH": 250.0, "AAPL": 0.0}, 0)),
            patch.object(tool_trade, "get_open_prices", return_value={"AAPL_price": 25.0}),
        ):
            result = tool_trade.buy_by_amount.fn("AAPL", 100, "test-agent", "2026-01-05")

        self.assertNotIn("error", result)
        self.assertEqual(result["positions"]["AAPL"], 4.0)
        self.assertEqual(result["positions"]["CASH"], 149.0)
        record = self.read_record()
        self.assertEqual(record["costs"]["commission_usd"], 1.0)
        self.assertEqual(record["this_action"]["amount_usd"], 100.0)

    def test_small_trade_is_rejected_before_mutation(self):
        result = tool_trade.buy_by_amount.fn("AAPL", 13, "test-agent", "2026-01-05")
        self.assertIn("error", result)
        self.assertFalse(self.position_file.exists())

    def test_fractional_sell_deducts_close_commission(self):
        with (
            patch.object(tool_trade, "_position_lock", return_value=nullcontext()),
            patch.object(tool_trade, "_position_file_path", return_value=str(self.position_file)),
            patch.object(tool_trade, "get_latest_position", return_value=({"CASH": 50.0, "AAPL": 10.0}, 3)),
            patch.object(tool_trade, "get_open_prices", return_value={"AAPL_price": 25.0}),
        ):
            result = tool_trade.sell_by_amount.fn("AAPL", 100, "test-agent", "2026-01-05")

        self.assertNotIn("error", result)
        self.assertEqual(result["positions"]["AAPL"], 6.0)
        self.assertEqual(result["positions"]["CASH"], 149.0)
        self.assertEqual(self.read_record()["costs"]["commission_usd"], 1.0)

    def test_small_exit_is_not_blocked_by_entry_cost_threshold(self):
        with (
            patch.object(tool_trade, "_position_lock", return_value=nullcontext()),
            patch.object(tool_trade, "_position_file_path", return_value=str(self.position_file)),
            patch.object(tool_trade, "get_latest_position", return_value=({"CASH": 0.0, "AAPL": 1.0}, 0)),
            patch.object(tool_trade, "get_open_prices", return_value={"AAPL_price": 25.0}),
        ):
            result = tool_trade.sell_by_amount.fn("AAPL", 13, "test-agent", "2026-01-05")

        self.assertNotIn("error", result)
        self.assertEqual(result["positions"]["CASH"], 12.0)

    def test_legacy_share_tools_reject_non_positive_amounts(self):
        self.assertIn("error", tool_trade.buy.fn("AAPL", 0))
        self.assertIn("error", tool_trade.sell.fn("AAPL", -1))


if __name__ == "__main__":
    unittest.main()
