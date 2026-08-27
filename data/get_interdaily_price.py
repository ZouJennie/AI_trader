import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.universe import US_STOCK_UNIVERSE

YFINANCE_CACHE = ROOT / ".yfinance-cache"
YFINANCE_CACHE.mkdir(parents=True, exist_ok=True)
yf.set_tz_cache_location(str(YFINANCE_CACHE))

load_dotenv()
import json

all_nasdaq_100_symbols = [
    "NVDA",
    "MSFT",
    "AAPL",
    "GOOG",
    "GOOGL",
    "AMZN",
    "META",
    "AVGO",
    "TSLA",
    "NFLX",
    "PLTR",
    "COST",
    "ASML",
    "AMD",
    "CSCO",
    "AZN",
    "TMUS",
    "MU",
    "LIN",
    "PEP",
    "SHOP",
    "APP",
    "INTU",
    "AMAT",
    "LRCX",
    "PDD",
    "QCOM",
    "ARM",
    "INTC",
    "BKNG",
    "AMGN",
    "TXN",
    "ISRG",
    "GILD",
    "KLAC",
    "PANW",
    "ADBE",
    "HON",
    "CRWD",
    "CEG",
    "ADI",
    "ADP",
    "DASH",
    "CMCSA",
    "VRTX",
    "MELI",
    "SBUX",
    "CDNS",
    "ORLY",
    "SNPS",
    "MSTR",
    "MDLZ",
    "ABNB",
    "MRVL",
    "CTAS",
    "TRI",
    "MAR",
    "MNST",
    "CSX",
    "ADSK",
    "PYPL",
    "FTNT",
    "AEP",
    "WDAY",
    "REGN",
    "ROP",
    "NXPI",
    "DDOG",
    "AXON",
    "ROST",
    "IDXX",
    "EA",
    "PCAR",
    "FAST",
    "EXC",
    "TTWO",
    "XEL",
    "ZS",
    "PAYX",
    "WBD",
    "BKR",
    "CPRT",
    "CCEP",
    "FANG",
    "TEAM",
    "CHTR",
    "KDP",
    "MCHP",
    "GEHC",
    "VRSK",
    "CTSH",
    "CSGP",
    "KHC",
    "ODFL",
    "DXCM",
    "TTD",
    "ON",
    "BIIB",
    "LULU",
    "CDW",
    "GFS",
]
all_nasdaq_100_symbols = US_STOCK_UNIVERSE


def _frame_for_symbol(dataset: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if dataset is None or dataset.empty:
        return pd.DataFrame()
    if not isinstance(dataset.columns, pd.MultiIndex):
        return dataset.copy()
    level_zero = dataset.columns.get_level_values(0)
    level_one = dataset.columns.get_level_values(1)
    if symbol in level_zero:
        return dataset[symbol].copy()
    if symbol in level_one:
        return dataset.xs(symbol, axis=1, level=1).copy()
    return pd.DataFrame()


def _new_york_date(index_value) -> str:
    stamp = pd.Timestamp(index_value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("America/New_York")
    return stamp.strftime("%Y-%m-%d")


def build_document(symbol: str, daily: pd.DataFrame, intraday: pd.DataFrame, expected_date: str) -> dict | None:
    series = {}
    for index, row in daily.iterrows():
        day = _new_york_date(index)
        if day >= expected_date or pd.isna(row.get("Close")):
            continue
        series[day] = {
            "1. open": str(round(float(row["Open"]), 4)),
            "2. high": str(round(float(row["High"]), 4)),
            "3. low": str(round(float(row["Low"]), 4)),
            "4. close": str(round(float(row["Close"]), 4)),
            "5. volume": str(int(row.get("Volume", 0) or 0)),
        }
    current_rows = [row for index, row in intraday.iterrows() if _new_york_date(index) == expected_date and not pd.isna(row.get("Close"))]
    if not current_rows:
        return None
    # Today's value is deliberately incomplete: merge_jsonl keeps it as a
    # buy price, while trend calculations use completed prior-day closes.
    series[expected_date] = {"1. open": str(round(float(current_rows[-1]["Close"]), 4))}
    return {
        "Meta Data": {
            "1. Information": f"Yahoo daily history plus latest 5-minute price for {symbol}",
            "2. Symbol": symbol,
            "3. Last Refreshed": expected_date,
            "4. Data Source": "Yahoo Finance via yfinance",
            "5. Time Zone": "America/New_York",
        },
        "Time Series (Daily)": series,
    }


def _download(symbols: list[str], *, period: str, interval: str) -> pd.DataFrame:
    return yf.download(
        tickers=symbols,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=False,
        prepost=False,
        threads=True,
        progress=False,
        timeout=30,
    )


def fetch_alpha_fallback(symbol: str, api_key: str) -> dict | None:
    response = requests.get(
        "https://www.alphavantage.co/query",
        params={
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": "60min",
            "outputsize": "compact",
            "extended_hours": "false",
            "apikey": api_key,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("Note") or data.get("Information") or not data.get("Time Series (60min)"):
        return None
    return data


def main() -> int:
    expected_date = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    symbols = all_nasdaq_100_symbols
    daily = _download(symbols, period="1y", interval="1d")
    intraday = _download(symbols, period="1d", interval="5m")
    missing = []
    for symbol in symbols:
        document = build_document(
            symbol,
            _frame_for_symbol(daily, symbol),
            _frame_for_symbol(intraday, symbol),
            expected_date,
        )
        if document is None:
            missing.append(symbol)
            continue
        with open(f"./daily_prices_{symbol}.json", "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
    api_key = os.getenv("ALPHAADVANTAGE_API_KEY", "")
    fallback_limit = int(os.getenv("ALPHA_FALLBACK_LIMIT", "20"))
    recovered = []
    if api_key:
        for symbol in missing[:fallback_limit]:
            try:
                data = fetch_alpha_fallback(symbol, api_key)
                if data:
                    with open(f"./daily_prices_{symbol}.json", "w", encoding="utf-8") as handle:
                        json.dump(data, handle, ensure_ascii=False, indent=2)
                    recovered.append(symbol)
            except (requests.RequestException, ValueError) as exc:
                print(f"Alpha fallback failed for {symbol}: {type(exc).__name__}")
            time.sleep(1.1)

    unresolved = [symbol for symbol in missing if symbol not in recovered]
    print(f"Yahoo snapshot: {len(symbols) - len(missing)}/{len(symbols)}; Alpha recovered: {len(recovered)}")
    if unresolved:
        print(f"Unresolved symbols: {', '.join(unresolved)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
