"""Validate a browser ledger and derive the actual fractional-share portfolio."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from tools.fee_tools import money, quantity


def _positive_decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"Invalid {field}") from exc
    if result <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return result


def portfolio_from_ledger(ledger: dict[str, Any]) -> dict[str, float]:
    if not isinstance(ledger, dict) or not isinstance(ledger.get("trades", []), list):
        raise ValueError("Ledger must be an object containing a trades array")
    cash = money(ledger.get("initialCash", 200))
    if cash < 0:
        raise ValueError("Initial cash cannot be negative")
    holdings: dict[str, Decimal] = {}
    trades = sorted(
        ledger.get("trades", []),
        key=lambda item: (str(item.get("date", "")), str(item.get("createdAt", item.get("id", "")))),
    )
    for trade in trades:
        if not isinstance(trade, dict):
            raise ValueError("Each trade must be an object")
        symbol = str(trade.get("symbol", "")).strip().upper()
        if not symbol or len(symbol) > 10:
            raise ValueError("Invalid trade symbol")
        side = str(trade.get("side", "")).lower()
        if side not in {"buy", "sell"}:
            raise ValueError("Trade side must be buy or sell")
        notional = _positive_decimal(trade.get("notional"), "notional")
        price = _positive_decimal(trade.get("price"), "price")
        fee = money(trade.get("fee", 0))
        if fee < 0:
            raise ValueError("Trade fee cannot be negative")
        shares = quantity(notional / price)
        current = holdings.get(symbol, Decimal("0"))
        if side == "buy":
            holdings[symbol] = quantity(current + shares)
            cash = money(cash - notional - fee)
        else:
            if shares > current + Decimal("0.000001"):
                raise ValueError(f"Sell quantity exceeds actual holding for {symbol}")
            holdings[symbol] = quantity(max(Decimal("0"), current - shares))
            cash = money(cash + notional - fee)
    if cash < Decimal("-0.01"):
        raise ValueError("Ledger produces a negative cash balance")
    result = {symbol: float(shares) for symbol, shares in holdings.items() if shares > 0}
    result["CASH"] = float(cash)
    return result


def summarize_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    """Return cost-basis context for the model without exposing the raw ledger."""
    positions = portfolio_from_ledger(ledger)
    lots: dict[str, dict[str, Decimal]] = {}
    total_fees = Decimal("0")
    realized = Decimal("0")
    trades = sorted(
        ledger.get("trades", []),
        key=lambda item: (str(item.get("date", "")), str(item.get("createdAt", item.get("id", "")))),
    )
    for trade in trades:
        symbol = str(trade["symbol"]).strip().upper()
        side = str(trade["side"]).lower()
        notional = _positive_decimal(trade.get("notional"), "notional")
        price = _positive_decimal(trade.get("price"), "price")
        fee = money(trade.get("fee", 0))
        shares = quantity(notional / price)
        lot = lots.setdefault(symbol, {"shares": Decimal("0"), "cost": Decimal("0")})
        total_fees = money(total_fees + fee)
        if side == "buy":
            lot["shares"] = quantity(lot["shares"] + shares)
            lot["cost"] = money(lot["cost"] + notional + fee)
        else:
            average_cost = lot["cost"] / lot["shares"] if lot["shares"] else Decimal("0")
            removed_cost = money(average_cost * shares)
            override = trade.get("pnlOverride")
            trade_realized = (
                Decimal(str(override))
                if override not in (None, "")
                else money(notional - fee - removed_cost)
            )
            realized = money(realized + trade_realized)
            lot["shares"] = quantity(max(Decimal("0"), lot["shares"] - shares))
            lot["cost"] = money(max(Decimal("0"), lot["cost"] - removed_cost))

    holdings = {}
    for symbol, lot in lots.items():
        if lot["shares"] > 0:
            holdings[symbol] = {
                "shares": float(lot["shares"]),
                "average_cost_including_buy_fees": float(money(lot["cost"] / lot["shares"])),
            }
    return {
        "cash": positions["CASH"],
        "holdings": holdings,
        "total_fees_paid": float(total_fees),
        "realized_pnl": float(realized),
        "trade_count": len(trades),
    }
