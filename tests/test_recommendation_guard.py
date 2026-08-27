import unittest

from tools.recommendation_guard import enforce_entry_gate


POLICY = {
    "target_new_position_usd": 80,
    "entry_gate": {
        "minimum_confidence": 0.75,
        "minimum_margin_of_safety_pct": 15,
        "minimum_expected_net_upside_pct": 8,
        "require_fundamental_gate": True,
        "require_no_material_sec_risk": True,
        "require_trend_gate": True,
    },
}


def recommendation(**overrides):
    fields = {
        "DECISION": "BUY",
        "SYMBOL": "AAPL",
        "TARGET_AMOUNT_USD": "80",
        "HORIZON_MONTHS": "6",
        "CONFIDENCE": "0.80",
        "ENTRY_GATE": "PASS",
        "FUNDAMENTAL_GATE": "PASS",
        "SEC_RISK_GATE": "PASS",
        "TREND_GATE": "PASS",
        "PRICE_VS_SMA20_PCT": "3.0",
        "FAIR_VALUE_RANGE_USD": "210-240",
        "MARGIN_OF_SAFETY_PCT": "16",
        "EXPECTED_GROSS_UPSIDE_PCT": "12",
        "ROUND_TRIP_COST_PCT": "0",
        "EXPECTED_NET_UPSIDE_PCT": "0",
        "THESIS": "test",
    }
    fields.update(overrides)
    return "\n".join(f"{key}: {value}" for key, value in fields.items()) + "\n<FINISH_SIGNAL>"


class RecommendationGuardTests(unittest.TestCase):
    def test_buy_passes_only_after_deterministic_fee_deduction(self):
        guarded, blockers = enforce_entry_gate(recommendation(), POLICY)
        self.assertEqual(blockers, [])
        self.assertIn("DECISION: BUY", guarded)
        self.assertIn("ROUND_TRIP_COST_PCT: 2.50", guarded)
        self.assertIn("EXPECTED_NET_UPSIDE_PCT: 9.50", guarded)

    def test_buy_below_net_upside_is_downgraded_to_hold(self):
        guarded, blockers = enforce_entry_gate(recommendation(EXPECTED_GROSS_UPSIDE_PCT="10"), POLICY)
        self.assertTrue(blockers)
        self.assertIn("DECISION: HOLD", guarded)
        self.assertIn("SYMBOL: NONE", guarded)
        self.assertIn("TARGET_AMOUNT_USD: 0", guarded)
        self.assertIn("GATE_BLOCKERS:", guarded)

    def test_any_required_gate_failure_blocks_buy(self):
        guarded, blockers = enforce_entry_gate(recommendation(SEC_RISK_GATE="FAIL"), POLICY)
        self.assertIn("SEC_RISK_GATE is not PASS", blockers)
        self.assertIn("DECISION: HOLD", guarded)

    def test_extended_price_blocks_buy_even_when_model_marks_trend_pass(self):
        guarded, blockers = enforce_entry_gate(recommendation(PRICE_VS_SMA20_PCT="8.1"), POLICY)
        self.assertTrue(any("SMA20" in blocker for blocker in blockers))
        self.assertIn("DECISION: HOLD", guarded)

    def test_existing_hold_passes_through(self):
        content = "DECISION: HOLD\nSYMBOL: NONE\nTARGET_AMOUNT_USD: 0"
        guarded, blockers = enforce_entry_gate(content, POLICY)
        self.assertEqual(guarded, content)
        self.assertEqual(blockers, [])


if __name__ == "__main__":
    unittest.main()
