"""Fetch the authenticated user's Supabase ledger for the scheduled advisor."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.actual_ledger import portfolio_from_ledger
from tools.price_tools import get_yesterday_date


def supabase_headers(secret_key: str) -> dict[str, str]:
    headers = {"apikey": secret_key}
    # New sb_secret_* keys are not JWTs; legacy service_role keys are.
    if not secret_key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {secret_key}"
    return headers



def fetch_ledger(url: str, secret_key: str, user_id: str) -> dict:
    endpoint = f"{url.rstrip('/')}/rest/v1/user_ledgers"
    response = requests.get(
        endpoint,
        params={"user_id": f"eq.{user_id}", "select": "ledger,updated_at", "limit": "1"},
        headers=supabase_headers(secret_key),
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return {"version": 1, "initialCash": 200, "trades": [], "priceOverrides": {}}
    ledger = rows[0].get("ledger")
    if not isinstance(ledger, dict):
        raise ValueError("Supabase returned an invalid ledger")
    return ledger


def write_actual_snapshot(config_path: Path, analysis_date: str, positions: dict[str, float], ledger: dict) -> Path:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    model = next(model for model in config["models"] if model.get("enabled", True))
    signature = model["signature"]
    log_path = str(config.get("log_config", {}).get("log_path", "./data/agent_data"))
    output = (ROOT / log_path / signature / "position" / "position.jsonl").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot_date = get_yesterday_date(analysis_date)
    record = {
        "date": snapshot_date,
        "id": 0,
        "source": "supabase_actual_ledger",
        "positions": positions,
    }
    output.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    ledger_path = output.parent.parent / "actual_ledger.json"
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "default_config.json")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    url = os.environ.get("SUPABASE_URL", "")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY", "")
    user_id = os.environ.get("SUPABASE_USER_ID", "")
    if not url or not secret_key or not user_id:
        raise SystemExit("SUPABASE_URL, SUPABASE_SECRET_KEY and SUPABASE_USER_ID are required")
    ledger = fetch_ledger(url, secret_key, user_id)
    positions = portfolio_from_ledger(ledger)
    path = write_actual_snapshot(args.config.resolve(), args.date, positions, ledger)
    print(f"Imported actual portfolio with {len(positions) - 1} holdings into {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
