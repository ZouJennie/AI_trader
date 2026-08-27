"""Run the US advisory workflow at a fixed New York market time.

This process schedules analysis only.  The configured market-data ingestion
command must finish before 10:15 ET; the next iteration will wire the selected
intraday provider into that ingestion step.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "default_config.json"


def load_schedule(config_path: Path) -> tuple[ZoneInfo, int, int]:
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    schedule = config.get("schedule", {})
    timezone = ZoneInfo(schedule.get("timezone", "America/New_York"))
    hour_text, minute_text = schedule.get("analysis_time", "10:15").split(":", 1)
    return timezone, int(hour_text), int(minute_text)


def next_run(now: datetime, hour: int, minute: int) -> datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def run_once(config_path: Path, analysis_date: str | None = None) -> int:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    run_date = analysis_date or datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    # A scheduled advisory run must analyze one point-in-time snapshot only.
    # Without this override a fresh account would replay every date from the
    # static config's init_date, creating many costly and stale model calls.
    env["INIT_DATE"] = run_date
    env["END_DATE"] = run_date
    command = [sys.executable, str(PROJECT_ROOT / "main.py"), str(config_path)]
    return subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Schedule the US investment advisor at 10:15 ET")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--once", action="store_true", help="Run immediately instead of waiting")
    args = parser.parse_args()

    config_path = args.config.resolve()
    timezone, hour, minute = load_schedule(config_path)
    if args.once:
        return run_once(config_path)

    while True:
        now = datetime.now(timezone)
        scheduled = next_run(now, hour, minute)
        wait_seconds = max(0, (scheduled - now).total_seconds())
        print(f"Next advisory run: {scheduled.isoformat()}", flush=True)
        while wait_seconds > 0:
            time.sleep(min(wait_seconds, 60))
            wait_seconds = max(0, (scheduled - datetime.now(timezone)).total_seconds())
        exit_code = run_once(config_path, scheduled.strftime("%Y-%m-%d"))
        if exit_code != 0:
            print(f"Advisor exited with code {exit_code}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
