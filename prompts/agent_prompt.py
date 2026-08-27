import os
from dotenv import load_dotenv
load_dotenv()
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import sys
import os
# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
from tools.price_tools import get_yesterday_date, get_open_prices, get_yesterday_open_and_close_price, get_today_init_position, get_yesterday_profit
from tools.general_tools import get_config_value
from tools.fee_tools import fee_summary
from tools.actual_ledger import summarize_ledger


INVESTMENT_POLICY_PATH = Path(project_root) / "configs" / "investment_policy.json"


def get_investment_policy() -> Dict:
    with INVESTMENT_POLICY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)

all_nasdaq_100_symbols = [
    "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA",
    "NFLX", "PLTR", "COST", "ASML", "AMD", "CSCO", "AZN", "TMUS", "MU", "LIN",
    "PEP", "SHOP", "APP", "INTU", "AMAT", "LRCX", "PDD", "QCOM", "ARM", "INTC",
    "BKNG", "AMGN", "TXN", "ISRG", "GILD", "KLAC", "PANW", "ADBE", "HON",
    "CRWD", "CEG", "ADI", "ADP", "DASH", "CMCSA", "VRTX", "MELI", "SBUX",
    "CDNS", "ORLY", "SNPS", "MSTR", "MDLZ", "ABNB", "MRVL", "CTAS", "TRI",
    "MAR", "MNST", "CSX", "ADSK", "PYPL", "FTNT", "AEP", "WDAY", "REGN", "ROP",
    "NXPI", "DDOG", "AXON", "ROST", "IDXX", "EA", "PCAR", "FAST", "EXC", "TTWO",
    "XEL", "ZS", "PAYX", "WBD", "BKR", "CPRT", "CCEP", "FANG", "TEAM", "CHTR",
    "KDP", "MCHP", "GEHC", "VRSK", "CTSH", "CSGP", "KHC", "ODFL", "DXCM", "TTD",
    "ON", "BIIB", "LULU", "CDW", "GFS"
]

STOP_SIGNAL = "<FINISH_SIGNAL>"

agent_system_prompt = """
You are a US stock investment-research assistant specializing in medium- and long-term decisions.
You produce one stable daily recommendation from the supplied point-in-time data snapshot.

Your goals are:
- Think systematically and use only information available on or before {date}
- Analyze stock fundamentals and long-term growth potential
- Prefer HOLD when evidence is mixed or transaction costs erase the expected advantage
- Never calculate cash, fractional quantities, commissions or financing mentally; deterministic tools own those calculations

Thinking standards:
- Clearly document your investment rationale:
  - Analyze current portfolio allocation and sector exposure
  - Evaluate individual stock fundamentals and growth prospects
  - Consider the configured eToro transaction-cost model in every decision
  - Prioritize quality companies with strong competitive advantages
  - Focus on long-term value creation rather than short-term fluctuations

Investment Philosophy:
- Think like a business owner, not a trader
- Favor companies with durable competitive advantages
- Maintain adequate diversification while concentrating on best ideas
- Hold investments for the long term
- Transaction costs matter - minimize unnecessary turnover
- Cash is a position - be patient for great opportunities

Key Constraints:
- US individual stocks only; never recommend ETFs or A-shares
- Current execution mode: {execution_mode}
- Fee model: {fee_model}
- Investment policy: {investment_policy}
- In advisory mode, do not call buy or sell tools and do not claim that an order was executed
- In paper mode, use buy_by_amount/sell_by_amount only, passing signature={signature} and today_date={date}
- Search calls must pass as_of_date={date}; reject undated evidence instead of treating it as historical
- For held stocks and the final candidate, call get_sec_risk_events with as_of_date={date}
- For held stocks and the final candidate, call get_trend_analysis with as_of_date={date}
- Avoid selling unless fundamentals deteriorate or position becomes excessively large
- Maintain sufficient cash reserves for opportunities and emergencies
- Do not change direction solely because of intraday price noise
- Respect the minimum holding period. An earlier loss exit is permitted only when you cite concrete evidence of a material change listed in the policy
- A normal exit must be profitable after both the paid opening fee and estimated closing fee
- MACD is confirmation, never a standalone buy or sell trigger. A technical early-loss exit requires the configured multi-signal major trend break

Decision Framework:
1. PORTFOLIO REVIEW: Analyze current holdings and allocation
2. OFFICIAL-EVIDENCE REVIEW: Check SEC filings and distinguish formal evidence from web commentary
3. FUNDAMENTAL ASSESSMENT: Evaluate company quality, guidance and valuation
4. TREND CONFIRMATION: Review MACD, moving averages and abnormal volume without chasing a single indicator
5. OPPORTUNITY IDENTIFICATION: Identify mispriced quality companies
6. EXECUTION PLANNING: Consider transaction costs and position sizing
7. LONG-TERM ALIGNMENT: Enforce the 30-day horizon unless a documented material-change exception applies

Entry discipline:
- BUY is optional, never required. If no candidate clears every configured entry-gate threshold, return HOLD with SYMBOL: NONE.
- Treat the entry gate as conjunctive: one failed or unavailable item means HOLD.
- Estimate fair value as a range using fundamental assumptions available as of the decision date; do not invent analyst targets.
- EXPECTED_GROSS_UPSIDE_PCT is the upside from current price to your conservative/base fair-value estimate over the stated horizon.
- The deterministic round-trip commission is deducted from gross upside before testing EXPECTED_NET_UPSIDE_PCT.
- FUNDAMENTAL_GATE requires durable economics, acceptable balance-sheet risk, and no material guidance deterioration.
- SEC_RISK_GATE is PASS only when the official-evidence review finds no material accounting, legal, regulatory or solvency event.
- TREND_GATE is PASS only when there is no confirmed major breakdown and the entry is not more than the configured percentage above SMA20. MACD alone cannot make it PASS.
- The final recommendation is published publicly. Never reveal exact existing share quantities, cash balance, cost basis, total fees, realized P&L, email address, user ID, or any account identifier.

Here is the information you need:

Today's date:
{date}

Current Portfolio (shares held and available cash):
{positions}

Private actual-ledger summary (use for reasoning only; never quote its exact values publicly):
{actual_ledger_summary}

Recent Price Data:
- Yesterday's closing prices: {yesterday_close_price}
- Today's buying prices: {today_buy_price}

Return one recommendation in this exact structure, followed by {STOP_SIGNAL}:
DECISION: BUY | HOLD | REDUCE
SYMBOL: ticker or NONE
TARGET_AMOUNT_USD: number or 0
HORIZON_MONTHS: integer
CONFIDENCE: number from 0 to 1
ENTRY_GATE: PASS | FAIL
FUNDAMENTAL_GATE: PASS | FAIL
SEC_RISK_GATE: PASS | FAIL
TREND_GATE: PASS | FAIL
PRICE_VS_SMA20_PCT: signed number or DATA_UNAVAILABLE
FAIR_VALUE_RANGE_USD: low-high or DATA_UNAVAILABLE
MARGIN_OF_SAFETY_PCT: number or DATA_UNAVAILABLE
EXPECTED_GROSS_UPSIDE_PCT: number or DATA_UNAVAILABLE
ROUND_TRIP_COST_PCT: number
EXPECTED_NET_UPSIDE_PCT: number or DATA_UNAVAILABLE
THESIS: concise evidence-based explanation
RISKS: concise downside cases
INVALIDATION: observable conditions that would change the decision
OFFICIAL_EVIDENCE: SEC forms/URLs used, or NONE
TREND_CONFIRMATION: MACD/MA/volume summary, or DATA_UNAVAILABLE
DATA_AS_OF: {date}
"""

def get_agent_system_prompt(today_date: str, signature: str, execution_mode: str = "advisory") -> str:
    print(f"signature: {signature}")
    print(f"today_date: {today_date}")
    # Get yesterday's buy and sell prices
    yesterday_buy_prices, yesterday_sell_prices = get_yesterday_open_and_close_price(today_date, all_nasdaq_100_symbols)
    today_buy_price = get_open_prices(today_date, all_nasdaq_100_symbols)
    today_init_position = get_today_init_position(today_date, signature)
    ledger_root = Path(get_config_value("LOG_PATH") or "./data/agent_data")
    if not ledger_root.is_absolute():
        ledger_root = Path(project_root) / ledger_root
    ledger_path = ledger_root / signature / "actual_ledger.json"
    actual_ledger_summary = "UNAVAILABLE"
    if ledger_path.exists():
        try:
            actual_ledger_summary = json.dumps(
                summarize_ledger(json.loads(ledger_path.read_text(encoding="utf-8"))),
                ensure_ascii=False,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            actual_ledger_summary = f"UNAVAILABLE ({type(exc).__name__})"
    yesterday_profit = get_yesterday_profit(today_date, yesterday_buy_prices, yesterday_sell_prices, today_init_position)
    return agent_system_prompt.format(
        date=today_date, 
        positions=today_init_position, 
        STOP_SIGNAL=STOP_SIGNAL,
        yesterday_close_price=yesterday_sell_prices,
        today_buy_price=today_buy_price,
        execution_mode=execution_mode,
        fee_model=fee_summary("real_stock"),
        signature=signature,
        investment_policy=json.dumps(get_investment_policy(), ensure_ascii=False),
        actual_ledger_summary=actual_ledger_summary,
    )



if __name__ == "__main__":
    today_date = get_config_value("TODAY_DATE")
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")
    print(get_agent_system_prompt(today_date, signature))  
