import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from fastmcp import FastMCP


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv()

from tools.sec_tools import SecClient


mcp = FastMCP("SecFilings")


@mcp.tool()
def get_sec_risk_events(symbol: str, as_of_date: str, lookback_days: int = 120) -> Dict[str, Any]:
    """Check official SEC filings for fundamental, guidance, accounting and legal risk signals.

    Results include filing URLs and evidence snippets. Text matches are candidate
    review signals and must be corroborated before an early loss exit.
    """
    try:
        date.fromisoformat(as_of_date[:10])
        if lookback_days < 1 or lookback_days > 730:
            raise ValueError("lookback_days must be between 1 and 730")
        return SecClient().analyze_recent_filings(symbol, as_of_date, lookback_days)
    except Exception as exc:
        return {"error": str(exc), "symbol": symbol, "as_of_date": as_of_date}


if __name__ == "__main__":
    port = int(os.getenv("SEC_HTTP_PORT", "8005"))
    mcp.run(transport="streamable-http", port=port)
