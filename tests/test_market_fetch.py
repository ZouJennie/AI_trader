import importlib.util
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "data" / "get_interdaily_price.py"
SPEC = importlib.util.spec_from_file_location("market_fetch", MODULE_PATH)
market_fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(market_fetch)


class MarketFetchTests(unittest.TestCase):
    def test_build_document_uses_latest_intraday_close_and_prior_daily_history(self):
        daily = pd.DataFrame(
            [{"Open": 190, "High": 202, "Low": 189, "Close": 200, "Volume": 1000}],
            index=pd.to_datetime(["2026-08-26"]),
        )
        intraday = pd.DataFrame(
            [
                {"Open": 201, "High": 203, "Low": 200, "Close": 202, "Volume": 10},
                {"Open": 202, "High": 204, "Low": 201, "Close": 203, "Volume": 20},
            ],
            index=pd.to_datetime(["2026-08-27 09:35:00-04:00", "2026-08-27 10:15:00-04:00"]),
        )
        document = market_fetch.build_document("AAPL", daily, intraday, "2026-08-27")
        series = document["Time Series (Daily)"]
        self.assertEqual(series["2026-08-26"]["4. close"], "200.0")
        self.assertEqual(series["2026-08-27"], {"1. open": "203.0"})

    def test_build_document_rejects_symbol_without_current_day_price(self):
        empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        self.assertIsNone(market_fetch.build_document("AAPL", empty, empty, "2026-08-27"))


if __name__ == "__main__":
    unittest.main()
