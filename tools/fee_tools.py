"""Deterministic transaction-cost calculations for eToro-style products.

The defaults are deliberately stored in ``configs/etoro_fees.json`` because
eToro fees vary by account jurisdiction, venue and product.  Calculations use
``Decimal`` so portfolio cash is not corrupted by binary floating-point drift.
"""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEE_CONFIG = PROJECT_ROOT / "configs" / "etoro_fees.json"
MONEY_QUANTUM = Decimal("0.01")
QUANTITY_QUANTUM = Decimal("0.000001")


def as_decimal(value: Any) -> Decimal:
    """Convert user/config values to Decimal without float representation noise."""
    return Decimal(str(value))


def money(value: Any) -> Decimal:
    return as_decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def quantity(value: Any) -> Decimal:
    return as_decimal(value).quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def load_fee_config(path: str | Path | None = None) -> Dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_FEE_CONFIG
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("Fee configuration must be a JSON object")
    return config


def get_product_config(product_type: str, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    fee_config = config or load_fee_config()
    product = fee_config.get(product_type)
    if not isinstance(product, dict):
        raise ValueError(f"Unsupported product type: {product_type}")
    return product


def calculate_commission(
    trade_value_usd: Any,
    side: str,
    product_type: str = "real_stock",
    config: Dict[str, Any] | None = None,
) -> Decimal:
    """Return the opening/closing commission for a positive trade notional."""
    trade_value = money(trade_value_usd)
    if trade_value <= 0:
        raise ValueError("trade_value_usd must be greater than zero")

    normalized_side = side.lower()
    if normalized_side not in {"open", "close"}:
        raise ValueError("side must be 'open' or 'close'")

    product = get_product_config(product_type, config)
    fixed = as_decimal(product.get(f"{normalized_side}_fixed_usd", 0))
    rate = as_decimal(product.get(f"{normalized_side}_rate", 0))
    mode = product.get("commission_mode", "max_fixed_or_rate")
    rate_fee = trade_value * rate

    if mode == "fixed":
        fee = fixed
    elif mode == "rate":
        fee = rate_fee
    elif mode == "fixed_plus_rate":
        fee = fixed + rate_fee
    elif mode == "max_fixed_or_rate":
        fee = max(fixed, rate_fee)
    else:
        raise ValueError(f"Unsupported commission_mode: {mode}")

    return money(fee)


def estimate_round_trip_cost(
    trade_value_usd: Any,
    product_type: str = "real_stock",
    holding_days: int = 0,
    leverage: Any = 1,
    config: Dict[str, Any] | None = None,
) -> Dict[str, Decimal]:
    """Estimate open, close and financing costs for a position.

    Financing is applied only to leveraged exposure above the user's capital.
    The configurable rate is an estimate and must be calibrated against the
    actual cost preview shown by eToro before execution.
    """
    trade_value = money(trade_value_usd)
    leverage_value = as_decimal(leverage)
    if holding_days < 0:
        raise ValueError("holding_days cannot be negative")
    if leverage_value < 1:
        raise ValueError("leverage must be at least 1")

    product = get_product_config(product_type, config)
    open_fee = calculate_commission(trade_value, "open", product_type, config)
    close_fee = calculate_commission(trade_value, "close", product_type, config)
    borrowed_exposure = trade_value * max(Decimal("0"), leverage_value - Decimal("1"))
    annual_rate = as_decimal(product.get("annual_overnight_base_rate", 0)) + as_decimal(
        product.get("annual_benchmark_rate", 0)
    )
    overnight = money(borrowed_exposure * annual_rate * as_decimal(holding_days) / Decimal("365"))
    total = money(open_fee + close_fee + overnight)
    pct = (total / trade_value).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return {
        "open_fee": open_fee,
        "close_fee": close_fee,
        "overnight_fee": overnight,
        "total_cost": total,
        "cost_pct": pct,
    }


def validate_trade_value(
    trade_value_usd: Any,
    product_type: str = "real_stock",
    config: Dict[str, Any] | None = None,
) -> Dict[str, Decimal]:
    """Validate broker minimum and configured round-trip cost threshold."""
    trade_value = money(trade_value_usd)
    product = get_product_config(product_type, config)
    minimum = money(product.get("minimum_trade_usd", 0))
    if trade_value < minimum:
        raise ValueError(f"Trade value ${trade_value} is below the configured minimum ${minimum}")

    estimate = estimate_round_trip_cost(trade_value, product_type, config=config)
    max_pct = as_decimal(product.get("max_estimated_round_trip_cost_pct", 1))
    if estimate["cost_pct"] > max_pct:
        raise ValueError(
            f"Estimated round-trip cost {estimate['cost_pct']:.2%} exceeds the configured limit {max_pct:.2%}"
        )
    return estimate


def fee_summary(product_type: str = "real_stock", config: Dict[str, Any] | None = None) -> str:
    product = get_product_config(product_type, config)
    return (
        f"product={product_type}; open fixed=${money(product.get('open_fixed_usd', 0))}; "
        f"close fixed=${money(product.get('close_fixed_usd', 0))}; "
        f"open rate={as_decimal(product.get('open_rate', 0)):.4%}; "
        f"close rate={as_decimal(product.get('close_rate', 0)):.4%}; "
        f"maximum estimated round-trip cost={as_decimal(product.get('max_estimated_round_trip_cost_pct', 1)):.2%}"
    )
