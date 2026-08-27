"""Decide whether a dual-UTC cron invocation is the 10:15 New York run."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo


def should_run(event_name: str, now: datetime) -> bool:
    if event_name == "workflow_dispatch":
        return True
    if event_name != "schedule":
        return False
    local = now.astimezone(ZoneInfo("America/New_York"))
    return local.weekday() < 5 and local.hour == 10


if __name__ == "__main__":
    event = os.getenv("GITHUB_EVENT_NAME", "")
    print(f"run={'true' if should_run(event, datetime.now(ZoneInfo('UTC'))) else 'false'}")
