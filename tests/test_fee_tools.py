import unittest
from decimal import Decimal

from tools.fee_tools import calculate_commission, estimate_round_trip_cost, validate_trade_value


class FeeToolsTests(unittest.TestCase):
    def test_fixed_stock_commission_is_applied_on_both_sides(self):
        estimate = estimate_round_trip_cost(100, "real_stock")
        self.assertEqual(estimate["open_fee"], Decimal("1.00"))
        self.assertEqual(estimate["close_fee"], Decimal("1.00"))
        self.assertEqual(estimate["total_cost"], Decimal("2.00"))
        self.assertEqual(estimate["cost_pct"], Decimal("0.020000"))

    def test_small_stock_trade_is_rejected_by_cost_limit(self):
        with self.assertRaisesRegex(ValueError, "exceeds the configured limit"):
            validate_trade_value(13, "real_stock")

    def test_confirmed_80_dollar_position_meets_cost_limit(self):
        estimate = validate_trade_value(80, "real_stock")
        self.assertEqual(estimate["cost_pct"], Decimal("0.025000"))

    def test_etf_has_zero_configured_commission(self):
        self.assertEqual(calculate_commission(25, "open", "etf"), Decimal("0.00"))

    def test_non_positive_value_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_commission(0, "open")


if __name__ == "__main__":
    unittest.main()
