"""SEC EDGAR ingestion and conservative event extraction.

Official filings are treated as evidence. Keyword extraction only creates
reviewable candidate events; it does not itself authorize a sell decision.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "sec"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
FULL_SUBMISSION_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{accession_number}.txt"
FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{accession_number}-index.html"
RELEVANT_FORMS = {"8-K", "10-Q", "10-K", "6-K", "20-F"}


EVENT_PATTERNS = [
    ("GUIDANCE_WITHDRAWN", "HIGH", 0.9, r"\b(withdraw(?:s|n|ing)?|suspend(?:s|ed|ing)?)\b.{0,100}\b(guidance|outlook|forecast)\b"),
    ("GUIDANCE_CUT", "HIGH", 0.78, r"\b(lower(?:s|ed|ing)?|reduc(?:e|es|ed|ing)|cut|revis(?:e|es|ed|ing) downward)\b.{0,120}\b(guidance|outlook|forecast)\b"),
    ("GOING_CONCERN", "CRITICAL", 0.95, r"\bsubstantial doubt\b.{0,160}\bgoing concern\b|\bgoing concern\b.{0,160}\bsubstantial doubt\b"),
    ("FINANCIAL_RESTATEMENT", "CRITICAL", 0.92, r"\b(restatement|restate(?:d|ment)?)\b.{0,140}\bfinancial statements?|results?\b"),
    ("NON_RELIANCE", "CRITICAL", 0.95, r"\bshould no longer be relied upon\b|\bnon-reliance\b"),
    ("MATERIAL_WEAKNESS", "HIGH", 0.88, r"\bmaterial weakness(?:es)?\b"),
    ("BANKRUPTCY_RISK", "CRITICAL", 0.9, r"\b(bankruptcy|chapter 11|receivership|insolven(?:t|cy))\b"),
    ("REGULATORY_INVESTIGATION", "HIGH", 0.72, r"\b(SEC|Department of Justice|DOJ|FTC)\b.{0,100}\b(investigation|subpoena|enforcement action)\b"),
    ("MATERIAL_LITIGATION", "MEDIUM", 0.62, r"\b(material litigation|class action lawsuit|legal proceedings?)\b"),
]

ITEM_EVENTS = {
    "1.03": ("BANKRUPTCY_OR_RECEIVERSHIP", "CRITICAL", 0.99),
    "2.04": ("OBLIGATION_TRIGGER_EVENT", "HIGH", 0.95),
    "3.01": ("DELISTING_OR_LISTING_FAILURE", "HIGH", 0.95),
    "4.01": ("AUDITOR_CHANGE", "MEDIUM", 0.95),
    "4.02": ("NON_RELIANCE_ON_FINANCIALS", "CRITICAL", 0.99),
}


def _plain_text(document: str) -> str:
    without_scripts = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", document)
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _snippet(text: str, start: int, end: int, radius: int = 180) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)].strip()


def extract_sec_events(document: str, form: str = "", items: str = "") -> List[Dict[str, Any]]:
    text = _plain_text(document)
    events: List[Dict[str, Any]] = []
    seen = set()

    for item, event_data in ITEM_EVENTS.items():
        if item in (items or ""):
            event_type, severity, confidence = event_data
            seen.add(event_type)
            events.append(
                {
                    "event_type": event_type,
                    "severity": severity,
                    "confidence": confidence,
                    "evidence": f"Form {form} Item {item}",
                    "evidence_kind": "form_item",
                }
            )

    for event_type, severity, confidence, pattern in EVENT_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match or event_type in seen:
            continue
        seen.add(event_type)
        events.append(
            {
                "event_type": event_type,
                "severity": severity,
                "confidence": confidence,
                "evidence": _snippet(text, match.start(), match.end()),
                "evidence_kind": "text_match",
            }
        )
    return events


class SecClient:
    def __init__(
        self,
        user_agent: Optional[str] = None,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        session: Optional[requests.Session] = None,
    ):
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT")
        self.cache_dir = Path(cache_dir)
        self.session = session or requests.Session()

    def _require_user_agent(self) -> str:
        if not self.user_agent or "example.com" in self.user_agent:
            raise ValueError("Set SEC_USER_AGENT to 'Your Name your-email@domain' before accessing SEC EDGAR")
        return self.user_agent

    def _get(self, url: str) -> requests.Response:
        response = self.session.get(
            url,
            headers={
                "User-Agent": self._require_user_agent(),
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=20,
        )
        response.raise_for_status()
        return response

    def _cache_path(self, name: str) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.cache_dir / name

    def _cached_json(self, url: str, name: str, max_age_hours: int) -> Any:
        path = self._cache_path(name)
        if path.exists():
            age = datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if age <= timedelta(hours=max_age_hours):
                return json.loads(path.read_text(encoding="utf-8"))
        data = self._get(url).json()
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        return data

    def get_company_cik(self, symbol: str) -> int:
        ticker_map = self._cached_json(TICKER_MAP_URL, "company_tickers.json", 24)
        wanted = symbol.strip().upper()
        for entry in ticker_map.values():
            if str(entry.get("ticker", "")).upper() == wanted:
                return int(entry["cik_str"])
        raise ValueError(f"No SEC CIK found for {wanted}")

    def get_recent_filings(self, symbol: str) -> List[Dict[str, Any]]:
        cik = self.get_company_cik(symbol)
        payload = self._cached_json(SUBMISSIONS_URL.format(cik=cik), f"submissions_{cik:010d}.json", 1)
        recent = payload.get("filings", {}).get("recent", {})
        keys = [
            "accessionNumber",
            "filingDate",
            "reportDate",
            "acceptanceDateTime",
            "form",
            "primaryDocument",
            "primaryDocDescription",
            "items",
        ]
        length = len(recent.get("accessionNumber", []))
        filings = []
        for index in range(length):
            filing = {}
            for key in keys:
                values = recent.get(key, [])
                filing[key] = (values[index] if index < len(values) else "") or ""
            filing["cik"] = cik
            filings.append(filing)
        return filings

    def get_filing_document(self, filing: Dict[str, Any]) -> tuple[str, str]:
        accession = filing["accessionNumber"].replace("-", "")
        download_url = FULL_SUBMISSION_URL.format(
            cik=int(filing["cik"]),
            accession=accession,
            accession_number=filing["accessionNumber"],
        )
        source_url = FILING_INDEX_URL.format(
            cik=int(filing["cik"]),
            accession=accession,
            accession_number=filing["accessionNumber"],
        )
        # The full submission text includes exhibits such as earnings releases;
        # the primary 8-K document often only points to Exhibit 99.1.
        path = self._cache_path(f"filing_{accession}_full.txt")
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace"), source_url
        text = self._get(download_url).text
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
        return text, source_url

    def analyze_recent_filings(
        self,
        symbol: str,
        as_of_date: str,
        lookback_days: int = 120,
        max_filings: int = 8,
    ) -> Dict[str, Any]:
        cutoff_date = date.fromisoformat(as_of_date[:10])
        earliest = cutoff_date - timedelta(days=lookback_days)
        candidates = [
            filing
            for filing in self.get_recent_filings(symbol)
            if filing["form"] in RELEVANT_FORMS
            and filing["filingDate"]
            and earliest <= date.fromisoformat(filing["filingDate"]) <= cutoff_date
        ][:max_filings]

        events = []
        sources = []
        for filing in candidates:
            document, source_url = self.get_filing_document(filing)
            filing_events = extract_sec_events(document, filing["form"], filing.get("items", ""))
            for event in filing_events:
                events.append(
                    {
                        "symbol": symbol.strip().upper(),
                        "filing_date": filing["filingDate"],
                        "form": filing["form"],
                        "accession_number": filing["accessionNumber"],
                        "source_url": source_url,
                        **event,
                    }
                )
            sources.append(
                {
                    "filing_date": filing["filingDate"],
                    "form": filing["form"],
                    "source_url": source_url,
                }
            )

        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        events.sort(key=lambda event: (severity_order.get(event["severity"], 0), event["filing_date"]), reverse=True)
        return {
            "symbol": symbol.strip().upper(),
            "as_of_date": as_of_date[:10],
            "filings_checked": len(candidates),
            "events": events,
            "sources": sources,
            "warning": "Text matches are review signals, not standalone sell authorization.",
        }
