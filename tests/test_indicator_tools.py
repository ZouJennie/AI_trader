import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from tools.indicator_tools import calculate_trend_snapshot, get_trend_snapshot


def make_bars(count=260):
    start = date(2025, 1, 1)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "close": 100 + index * 0.2,
            "volume": 1000,
        }
        for index in range(count)
    ]


class IndicatorToolsTests(unittest.TestCase):
    def test_macd_and_moving_averages_are_returned(self):
        snapshot = calculate_trend_snapshot(make_bars())
        self.assertEqual(snapshot["macd_state"], "bullish")
        self.assertIsNotNone(snapshot["sma200"])
        self.assertFalse(snapshot["confirmed_major_trend_break"])

    def test_major_break_requires_price_macd_and_abnormal_volume_confirmation(self):
        bars = make_bars()
        bars[-2]["close"] = 80
        bars[-2]["volume"] = 5000
        bars[-1]["close"] = 75
        bars[-1]["volume"] = 6000
        snapshot = calculate_trend_snapshot(bars)
        self.assertEqual(snapshot["macd_state"], "bearish")
        self.assertTrue(snapshot["abnormal_volume"])
        self.assertGreaterEqual(snapshot["consecutive_closes_below_sma50"], 2)
        self.assertTrue(snapshot["confirmed_major_trend_break"])

    def test_incomplete_current_bar_is_excluded(self):
        completed = {}
        start = date(2025, 1, 1)
        for index in range(80):
            day = (start + timedelta(days=index)).isoformat()
            completed[day] = {"4. sell price": str(100 + index), "5. volume": "1000"}
        incomplete_date = (start + timedelta(days=80)).isoformat()
        completed[incomplete_date] = {"1. buy price": "200"}
        document = {"Meta Data": {"2. Symbol": "TEST"}, "Time Series (Daily)": completed}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.jsonl"
            path.write_text(json.dumps(document) + "\n", encoding="utf-8")
            snapshot = get_trend_snapshot("TEST", incomplete_date, path)

        self.assertNotEqual(snapshot["data_through"], incomplete_date)


if __name__ == "__main__":
    unittest.main()
