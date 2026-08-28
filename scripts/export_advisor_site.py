"""Export private runtime output into the small public GitHub Pages payload."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
FINISH_SIGNAL = "<FINISH_SIGNAL>"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
    return records


def latest_recommendations(path: Path, limit: int = 90) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(path):
        date = str(record.get("date", "")).strip()
        content = str(record.get("content", "")).replace(FINISH_SIGNAL, "").strip()
        if date and content:
            by_date[date] = {
                "date": date,
                "content": content,
                "model": record.get("signature"),
                "execution_mode": record.get("execution_mode", "advisory"),
                "execution_status": "not_executed" if record.get("execution_mode", "advisory") == "advisory" else "paper_mode",
            }
    return [by_date[key] for key in sorted(by_date)[-limit:]]


def extract_prices(merged_path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for document in read_jsonl(merged_path):
        symbol = str(document.get("Meta Data", {}).get("2. Symbol", "")).upper()
        series = next((value for key, value in document.items() if key.startswith("Time Series") and isinstance(value, dict)), None)
        if not symbol or not series:
            continue
        timestamp = max(series)
        bar = series.get(timestamp, {})
        raw_price = bar.get("4. sell price") or bar.get("4. close") or bar.get("1. buy price") or bar.get("1. open")
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            continue
        if price > 0:
            result[symbol] = {"price": price, "timestamp": timestamp}
    return result


def export(config_path: Path, output_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    model = next(model for model in config["models"] if model.get("enabled", True))
    signature = model["signature"]
    log_path = str(config.get("log_config", {}).get("log_path", "./data/agent_data"))
    runtime_root = (ROOT / log_path).resolve()
    recommendations_path = runtime_root / signature / "recommendations" / "recommendations.jsonl"
    history = latest_recommendations(recommendations_path)
    payload = {
        "generated_at": datetime.now(ZoneInfo("America/New_York")).isoformat(),
        "model": model["basemodel"],
        "initial_cash": float(config.get("agent_config", {}).get("initial_cash", 200)),
        "latest": history[-1] if history else None,
        "history": history,
        "prices": extract_prices(ROOT / "data" / "merged.jsonl"),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "default_config.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "data" / "advice.json")
    args = parser.parse_args()
    payload = export(args.config.resolve(), args.output.resolve())
    print(f"Exported {len(payload['history'])} recommendations and {len(payload['prices'])} prices")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
