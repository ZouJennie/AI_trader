"""Fail a scheduled run before AI analysis when the market snapshot is stale."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prompts.agent_prompt import all_nasdaq_100_symbols




def current_symbols(merged_path: Path, expected_date: str) -> set[str]:
    found: set[str] = set()
    if not merged_path.exists():
        return found
    with merged_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                document = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            symbol = str(document.get("Meta Data", {}).get("2. Symbol", "")).upper()
            series = next((value for key, value in document.items() if key.startswith("Time Series") and isinstance(value, dict)), {})
            if symbol and any(str(timestamp).startswith(expected_date) for timestamp in series):
                found.add(symbol)
    return found


def validate(merged_path: Path, expected_date: str, minimum_coverage: float) -> tuple[bool, int, int]:
    expected = set(all_nasdaq_100_symbols)
    found = current_symbols(merged_path, expected_date) & expected
    return len(found) / len(expected) >= minimum_coverage, len(found), len(expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged", type=Path, default=ROOT / "data" / "merged.jsonl")
    parser.add_argument("--date", default=datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d"))
    parser.add_argument("--minimum-coverage", type=float, default=0.90)
    args = parser.parse_args()
    ok, found, expected = validate(args.merged.resolve(), args.date, args.minimum_coverage)
    print(f"Market snapshot coverage for {args.date}: {found}/{expected}")
    if not ok:
        print("Snapshot rejected: current-day market data coverage is below the required threshold.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
