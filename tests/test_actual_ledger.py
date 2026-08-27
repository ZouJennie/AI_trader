import unittest

from tools.actual_ledger import portfolio_from_ledger, summarize_ledger


class ActualLedgerTests(unittest.TestCase):
    def test_fractional_trades_and_fees_become_actual_positions(self):
        ledger = {
            "initialCash": 200,
            "trades": [
                {"date": "2026-08-27", "createdAt": "1", "side": "buy", "symbol": "AAPL", "notional": 80, "price": 200, "fee": 1},
                {"date": "2026-08-28", "createdAt": "2", "side": "sell", "symbol": "AAPL", "notional": 20, "price": 250, "fee": 1},
            ],
        }
        positions = portfolio_from_ledger(ledger)
        self.assertAlmostEqual(positions["AAPL"], 0.32)
        self.assertEqual(positions["CASH"], 138.0)

    def test_sell_before_buy_is_rejected(self):
        ledger = {
            "initialCash": 200,
            "trades": [{"date": "2026-08-27", "side": "sell", "symbol": "AAPL", "notional": 20, "price": 200, "fee": 1}],
        }
        with self.assertRaisesRegex(ValueError, "exceeds"):
            portfolio_from_ledger(ledger)

    def test_negative_cash_is_rejected(self):
        ledger = {
            "initialCash": 200,
            "trades": [{"date": "2026-08-27", "side": "buy", "symbol": "AAPL", "notional": 200, "price": 200, "fee": 1}],
        }
        with self.assertRaisesRegex(ValueError, "negative cash"):
            portfolio_from_ledger(ledger)

    def test_summary_includes_fee_adjusted_cost_basis(self):
        ledger = {
            "initialCash": 200,
            "trades": [
                {"date": "2026-08-27", "side": "buy", "symbol": "AAPL", "notional": 80, "price": 200, "fee": 1},
            ],
        }
        summary = summarize_ledger(ledger)
        self.assertEqual(summary["cash"], 119.0)
        self.assertEqual(summary["holdings"]["AAPL"]["shares"], 0.4)
        self.assertEqual(summary["holdings"]["AAPL"]["average_cost_including_buy_fees"], 202.5)
        self.assertEqual(summary["total_fees_paid"], 1.0)


if __name__ == "__main__":
    unittest.main()
