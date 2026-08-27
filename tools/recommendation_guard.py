"""Deterministically downgrade BUY recommendations that fail the entry policy."""

from __future__ import annotations

import re
from typing import Any

from tools.fee_tools import estimate_round_trip_cost


FIELD_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*):\s*(.*?)\s*$", re.MULTILINE)


def parse_fields(content: str) -> dict[str, str]:
    return {match.group(1): match.group(2) for match in FIELD_PATTERN.finditer(content or "")}


def parse_number(value: str | None) -> float | None:
    if not value or "DATA_UNAVAILABLE" in value.upper():
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group()) if match else None


def replace_field(content: str, field: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(field)}:\s*.*$", re.MULTILINE)
    replacement = f"{field}: {value}"
    if pattern.search(content):
        return pattern.sub(replacement, content, count=1)
    return f"{replacement}\n{content}"


def enforce_entry_gate(content: str, policy: dict[str, Any]) -> tuple[str, list[str]]:
    """Return guarded content and BUY blockers; non-BUY decisions pass through."""
    fields = parse_fields(content)
    decision = fields.get("DECISION", "").upper()
    if decision and decision != "BUY":
        return content, []

    blockers: list[str] = []
    if decision != "BUY":
        blockers.append("missing or invalid DECISION")

    gate = policy.get("entry_gate", {})
    confidence = parse_number(fields.get("CONFIDENCE"))
    minimum_confidence = float(gate.get("minimum_confidence", 0.75))
    if confidence is None or confidence < minimum_confidence:
        blockers.append(f"confidence below {minimum_confidence:.2f}")

    target_amount = parse_number(fields.get("TARGET_AMOUNT_USD"))
    configured_target = float(policy.get("target_new_position_usd", 80.0))
    if target_amount is None or target_amount <= 0 or target_amount > configured_target:
        blockers.append(f"target amount must be within $0-${configured_target:.2f}")

    margin = parse_number(fields.get("MARGIN_OF_SAFETY_PCT"))
    minimum_margin = float(gate.get("minimum_margin_of_safety_pct", 15.0))
    if margin is None or margin < minimum_margin:
        blockers.append(f"margin of safety below {minimum_margin:.1f}%")

    gross_upside = parse_number(fields.get("EXPECTED_GROSS_UPSIDE_PCT"))
    if target_amount and target_amount > 0:
        actual_cost_pct = float(estimate_round_trip_cost(target_amount)["cost_pct"] * 100)
    else:
        actual_cost_pct = 100.0
    expected_net = None if gross_upside is None else gross_upside - actual_cost_pct
    minimum_net = float(gate.get("minimum_expected_net_upside_pct", 8.0))
    if expected_net is None or expected_net < minimum_net:
        blockers.append(f"expected upside after {actual_cost_pct:.2f}% round-trip cost below {minimum_net:.1f}%")

    required_gates = {
        "ENTRY_GATE": True,
        "FUNDAMENTAL_GATE": bool(gate.get("require_fundamental_gate", True)),
        "SEC_RISK_GATE": bool(gate.get("require_no_material_sec_risk", True)),
        "TREND_GATE": bool(gate.get("require_trend_gate", True)),
    }
    for field, required in required_gates.items():
        if required and fields.get(field, "").upper() != "PASS":
            blockers.append(f"{field} is not PASS")

    price_vs_sma20 = parse_number(fields.get("PRICE_VS_SMA20_PCT"))
    maximum_sma20_premium = float(gate.get("maximum_price_premium_to_sma20_pct", 8.0))
    if price_vs_sma20 is None or price_vs_sma20 > maximum_sma20_premium:
        blockers.append(f"price premium to SMA20 exceeds {maximum_sma20_premium:.1f}% or is unavailable")

    if not blockers:
        guarded = replace_field(content, "ROUND_TRIP_COST_PCT", f"{actual_cost_pct:.2f}")
        guarded = replace_field(guarded, "EXPECTED_NET_UPSIDE_PCT", f"{expected_net:.2f}")
        return guarded, []

    guarded = content
    guarded = replace_field(guarded, "DECISION", "HOLD")
    guarded = replace_field(guarded, "SYMBOL", "NONE")
    guarded = replace_field(guarded, "TARGET_AMOUNT_USD", "0")
    guarded = replace_field(guarded, "ENTRY_GATE", "FAIL")
    guarded = replace_field(guarded, "ROUND_TRIP_COST_PCT", f"{actual_cost_pct:.2f}")
    guarded = replace_field(guarded, "EXPECTED_NET_UPSIDE_PCT", "DATA_UNAVAILABLE" if expected_net is None else f"{expected_net:.2f}")
    blocker_line = "GATE_BLOCKERS: " + "; ".join(blockers)
    finish_signal = "<FINISH_SIGNAL>"
    guarded = guarded.replace(finish_signal, f"{blocker_line}\n{finish_signal}") if finish_signal in guarded else f"{guarded.rstrip()}\n{blocker_line}"
    return guarded, blockers
