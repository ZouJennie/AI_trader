import tempfile
import unittest
from unittest.mock import patch

from tools.sec_tools import SecClient, extract_sec_events


class SecToolsTests(unittest.TestCase):
    def test_extracts_guidance_cut_and_material_weakness(self):
        document = """
        <html><body>The company lowered its full-year revenue guidance.
        Management also identified a material weakness in internal control.</body></html>
        """
        events = extract_sec_events(document, "8-K", "2.02")
        event_types = {event["event_type"] for event in events}
        self.assertIn("GUIDANCE_CUT", event_types)
        self.assertIn("MATERIAL_WEAKNESS", event_types)

    def test_form_item_creates_high_confidence_event(self):
        events = extract_sec_events("No details supplied", "8-K", "4.02")
        self.assertEqual(events[0]["event_type"], "NON_RELIANCE_ON_FINANCIALS")
        self.assertEqual(events[0]["confidence"], 0.99)

    def test_future_filings_are_excluded_by_as_of_date(self):
        filings = [
            {
                "cik": 1,
                "accessionNumber": "0000000001-26-000001",
                "filingDate": "2026-08-20",
                "reportDate": "",
                "acceptanceDateTime": "",
                "form": "8-K",
                "primaryDocument": "current.htm",
                "primaryDocDescription": "",
                "items": "2.02",
            },
            {
                "cik": 1,
                "accessionNumber": "0000000001-26-000002",
                "filingDate": "2026-09-01",
                "reportDate": "",
                "acceptanceDateTime": "",
                "form": "8-K",
                "primaryDocument": "future.htm",
                "primaryDocDescription": "",
                "items": "2.02",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            client = SecClient("AI Trader test@example.org", directory)
            with (
                patch.object(client, "get_recent_filings", return_value=filings),
                patch.object(client, "get_filing_document", return_value=("lowered its annual guidance", "https://sec.test/filing")),
            ):
                result = client.analyze_recent_filings("TEST", "2026-08-27")

        self.assertEqual(result["filings_checked"], 1)
        self.assertTrue(all(event["filing_date"] <= "2026-08-27" for event in result["events"]))


if __name__ == "__main__":
    unittest.main()
