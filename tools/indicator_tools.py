"""Deterministic technical indicators calculated from completed daily bars."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import fmean
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRICE_FILE = PROJECT_ROOT / "data" / "merged.jsonl"


def _float(value: Any) -> Optional[float]:
    try:
        result = float(value)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def ema(values: Iterable[float], period: int) -> List[float]:
    values_list = list(values)
    if period <= 0:
        raise ValueError("period must be positive")
    if not values_list:
        return []
    multiplier = 2.0 / (period + 1)
    output = [values_list[0]]
    for value in values_list[1:]:
        output.append((value - output[-1]) * multiplier + output[-1])
    return output


def rolling_sma(values: List[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")
    output: List[Optional[float]] = []
    running_sum = 0.0
    for index, value in enumerate(values):
        running_sum += value
        if index >= period:
            running_sum -= values[index - period]
        output.append(running_sum / period if index + 1 >= period else None)
    return output


def load_completed_daily_bars(
    symbol: str,
    as_of_date: str,
    price_file: str | Path | None = None,
) -> List[Dict[str, Any]]:
    """Load completed daily bars, excluding rows without close or volume."""
    path = Path(price_file) if price_file else DEFAULT_PRICE_FILE
    if not path.exists():
        raise FileNotFoundError(f"Price file not found: {path}")
    wanted_symbol = symbol.strip().upper()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            document = json.loads(line)
            if document.get("Meta Data", {}).get("2. Symbol") != wanted_symbol:
                continue
            series = document.get("Time Series (Daily)", {})
            bars = []
            for date, raw_bar in series.items():
                if date > as_of_date:
                    continue
                close = _float(raw_bar.get("4. sell price"))
                volume = _float(raw_bar.get("5. volume"))
                if close is None or volume is None:
                    continue
                bars.append(
                    {
                        "date": date,
                        "open": _float(raw_bar.get("1. buy price")),
                        "high": _float(raw_bar.get("2. high")),
                        "low": _float(raw_bar.get("3. low")),
                        "close": close,
                        "volume": volume,
                    }
                )
            return sorted(bars, key=lambda item: item["date"])
    raise ValueError(f"Symbol {wanted_symbol} not found in {path}")


def calculate_trend_snapshot(
    bars: List[Dict[str, Any]],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    abnormal_volume_ratio: float = 1.5,
    break_sma_period: int = 50,
    confirmation_closes: int = 2,
) -> Dict[str, Any]:
    minimum = max(slow_period + signal_period, break_sma_period, 20)
    if len(bars) < minimum:
        raise ValueError(f"At least {minimum} completed daily bars are required")

    closes = [float(bar["close"]) for bar in bars]
    volumes = [float(bar["volume"]) for bar in bars]
    fast = ema(closes, fast_period)
    slow = ema(closes, slow_period)
    macd_values = [fast_value - slow_value for fast_value, slow_value in zip(fast, slow)]
    signal_values = ema(macd_values, signal_period)
    histogram = [macd - signal for macd, signal in zip(macd_values, signal_values)]

    sma20 = rolling_sma(closes, 20)
    sma50 = rolling_sma(closes, 50)
    sma200 = rolling_sma(closes, 200)
    volume_window = volumes[-21:-1] if len(volumes) >= 21 else volumes[:-1]
    average_volume = fmean(volume_window) if volume_window else volumes[-1]
    volume_ratio = volumes[-1] / average_volume if average_volume else 0.0

    break_sma = rolling_sma(closes, break_sma_period)
    consecutive_below = 0
    for close, average in zip(reversed(closes), reversed(break_sma)):
        if average is not None and close < average:
            consecutive_below += 1
        else:
            break

    macd_state = "bullish" if macd_values[-1] > signal_values[-1] else "bearish"
    histogram_direction = "improving" if histogram[-1] > histogram[-2] else "weakening"
    confirmed_break = (
        consecutive_below >= confirmation_closes
        and macd_state == "bearish"
        and volume_ratio >= abnormal_volume_ratio
    )

    return {
        "data_through": bars[-1]["date"],
        "completed_bars": len(bars),
        "close": round(closes[-1], 6),
        "sma20": round(sma20[-1], 6) if sma20[-1] is not None else None,
        "sma50": round(sma50[-1], 6) if sma50[-1] is not None else None,
        "sma200": round(sma200[-1], 6) if sma200[-1] is not None else None,
        "macd": round(macd_values[-1], 6),
        "macd_signal": round(signal_values[-1], 6),
        "macd_histogram": round(histogram[-1], 6),
        "macd_state": macd_state,
        "macd_histogram_direction": histogram_direction,
        "volume": round(volumes[-1], 2),
        "average_volume_20": round(average_volume, 2),
        "volume_ratio_20": round(volume_ratio, 4),
        "consecutive_closes_below_sma50": consecutive_below if break_sma_period == 50 else None,
        "abnormal_volume": volume_ratio >= abnormal_volume_ratio,
        "confirmed_major_trend_break": confirmed_break,
    }


def get_trend_snapshot(symbol: str, as_of_date: str, price_file: str | Path | None = None) -> Dict[str, Any]:
    bars = load_completed_daily_bars(symbol, as_of_date, price_file)
    snapshot = calculate_trend_snapshot(bars)
    return {"symbol": symbol.strip().upper(), "as_of_date": as_of_date, **snapshot}
