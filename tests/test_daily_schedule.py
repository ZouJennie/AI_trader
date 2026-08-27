import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.run_daily_advisor import next_run
from agent.base_agent.base_agent import BaseAgent


class DailyScheduleTests(unittest.TestCase):
    def test_advisory_mode_does_not_expose_trade_service(self):
        agent = BaseAgent(signature="test", basemodel="test", execution_mode="advisory")
        self.assertNotIn("trade", agent.mcp_config)

    def test_paper_mode_exposes_trade_service(self):
        agent = BaseAgent(signature="test", basemodel="test", execution_mode="paper")
        self.assertIn("trade", agent.mcp_config)

    def test_schedules_1015_new_york_same_weekday(self):
        tz = ZoneInfo("America/New_York")
        now = datetime(2026, 8, 27, 9, 0, tzinfo=tz)
        self.assertEqual(next_run(now, 10, 15), datetime(2026, 8, 27, 10, 15, tzinfo=tz))

    def test_skips_weekend(self):
        tz = ZoneInfo("America/New_York")
        friday_after_run = datetime(2026, 8, 28, 11, 0, tzinfo=tz)
        self.assertEqual(next_run(friday_after_run, 10, 15), datetime(2026, 8, 31, 10, 15, tzinfo=tz))


if __name__ == "__main__":
    unittest.main()
