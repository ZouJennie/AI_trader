"""Run scheduled retries during market hours until today's advice exists."""

from __future__ import annotations

import os
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECOMMENDATIONS = (
    ROOT / "data" / "agent_data" / "deepseek-v4-flash" / "recommendations" / "recommendations.jsonl"
)


def has_recommendation_for_date(path: Path, expected_date: str) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if str(record.get("date", "")) == expected_date and str(record.get("content", "")).strip():
                return True
    return False


def should_run(event_name: str, now: datetime, already_generated: bool = False) -> bool:
    if event_name == "workflow_dispatch":
        return True
    if event_name != "schedule":
        return False
    local = now.astimezone(ZoneInfo("America/New_York"))
    # GitHub explicitly treats scheduled workflows as best-effort. Accept
    # delayed hourly retries while the regular session is still open.
    return local.weekday() < 5 and 10 <= local.hour < 16 and not already_generated


if __name__ == "__main__":
    event = os.getenv("GITHUB_EVENT_NAME", "")
    now = datetime.now(ZoneInfo("UTC"))
    local_date = now.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    recommendations = Path(os.getenv("RECOMMENDATIONS_PATH", DEFAULT_RECOMMENDATIONS))
    already_generated = has_recommendation_for_date(recommendations, local_date)
    run = should_run(event, now, already_generated)
    reason = "manual" if event == "workflow_dispatch" else (
        "already_generated" if already_generated else ("retry_window" if run else "outside_window")
    )
    print(f"run={'true' if run else 'false'}")
    print(f"reason={reason}")
