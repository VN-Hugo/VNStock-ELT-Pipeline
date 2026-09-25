"""Minimal client for the public market-data endpoints the pipeline needs.

Replaces the vnstock/vnai packages, which PyPI quarantined on 2026-09-24. These are the
same unofficial JSON endpoints that power the Vietcap (VCI) and KB Securities (KBS) web
apps; they are undocumented and may change, so every parser checks the fields it relies on
and fails loudly instead of loading silently wrong data.

Prices are returned in thousand VND to stay consistent with the history already in Bronze.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import time

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

VCI_CHART_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
VCI_IQ_URL = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company"
KBS_BOARD_URL = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stock/iss"

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
_VCI_HEADERS = {"Referer": "https://trading.vietcap.com.vn/", "Origin": "https://trading.vietcap.com.vn"}
_KBS_HEADERS = {"Referer": "https://kbbuddywts.kbsec.com.vn/", "Origin": "https://kbbuddywts.kbsec.com.vn", "x-lang": "vi"}

# Income statement field codes (VCI IQ). Banks report total operating income instead of net sales.
FIELD_NET_SALES = "isa3"
FIELD_BANK_TOTAL_OPERATING_INCOME = "isb38"
FIELD_PROFIT_AFTER_TAX = "isa20"
FIELD_PROFIT_PARENT = "isa22"

# Pause between requests: these are free public endpoints, keep the load polite.
REQUEST_INTERVAL_SECONDS = 0.5


class MarketDataError(RuntimeError):
    pass


class MarketClient:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": _USER_AGENT, "Accept": "application/json", "Content-Type": "application/json"})
        retry = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET", "POST"))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self._last_request = 0.0

    def _request(self, method: str, url: str, headers: dict, **kwargs):
        wait = REQUEST_INTERVAL_SECONDS - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        response = self.session.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
        self._last_request = time.monotonic()
        if response.status_code != 200:
            raise MarketDataError(f"{method} {url} -> HTTP {response.status_code}: {response.text[:200]}")
        return response.json()

    def _iq(self, path: str, **params):
        body = self._request("GET", f"{VCI_IQ_URL}/{path}", _VCI_HEADERS, params=params or None)
        if not body.get("successful", True) or "data" not in body:
            raise MarketDataError(f"VCI IQ {path}: unexpected response {str(body)[:200]}")
        return body["data"]

    # ---- Prices ---------------------------------------------------------------------------

    def daily_prices(self, symbol: str, start: str, end: str | None = None) -> pd.DataFrame:
        """Daily OHLCV (adjusted, thousand VND) between start and end inclusive."""
        start_day = date.fromisoformat(start)
        end_day = date.fromisoformat(end) if end else date.today()
        # The endpoint counts bars back from `to`; business days is an upper bound on sessions.
        count_back = len(pd.bdate_range(start_day, end_day)) + 5
        to = int(datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())
        body = self._request("POST", VCI_CHART_URL, _VCI_HEADERS,
                             json={"timeFrame": "ONE_DAY", "symbols": [symbol.upper()], "to": to, "countBack": count_back})
        if not body:
            return pd.DataFrame(columns=["trading_date", "open", "high", "low", "close", "volume"])
        bars = body[0]
        missing = {"t", "o", "h", "l", "c", "v"} - set(bars)
        if missing:
            raise MarketDataError(f"price response for {symbol} lacks {missing}")
        frame = pd.DataFrame({
            # Bars are stamped at 00:00 UTC of the session date
            "trading_date": pd.to_datetime(pd.to_numeric(pd.Series(bars["t"])), unit="s", utc=True).dt.date,
            "open": pd.to_numeric(bars["o"]) / 1000,
            "high": pd.to_numeric(bars["h"]) / 1000,
            "low": pd.to_numeric(bars["l"]) / 1000,
            "close": pd.to_numeric(bars["c"]) / 1000,
            "volume": pd.to_numeric(bars["v"]),
        })
        frame = frame[(frame["trading_date"] >= start_day) & (frame["trading_date"] <= end_day)]
        frame["trading_date"] = frame["trading_date"].astype(str)
        return frame.reset_index(drop=True)

    # ---- Fundamentals ---------------------------------------------------------------------

    def income_statement(self, symbol: str) -> pd.DataFrame:
        """One row per quarter with revenue, profit after tax, profit attributable to the
        parent company and the real publication date (full history, not capped)."""
        data = self._iq(f"{symbol.upper()}/financial-statement", section="INCOME_STATEMENT")
        quarters = data.get("quarters") or []
        rows = []
        for q in quarters:
            if int(q.get("lengthReport", 0)) not in (1, 2, 3, 4):
                continue
            revenue = q.get(FIELD_NET_SALES)
            if revenue in (None, 0):
                revenue = q.get(FIELD_BANK_TOTAL_OPERATING_INCOME)
            rows.append({
                "report_period": f"{int(q['yearReport'])}-Q{int(q['lengthReport'])}",
                "public_date": (q.get("publicDate") or "")[:10] or None,
                "revenue": revenue,
                "profit": q.get(FIELD_PROFIT_AFTER_TAX),
                "profit_parent": q.get(FIELD_PROFIT_PARENT),
            })
        frame = pd.DataFrame(rows)
        if not frame.empty and frame["profit"].isna().all():
            raise MarketDataError(f"income statement for {symbol}: field {FIELD_PROFIT_AFTER_TAX} missing, the API layout may have changed")
        return frame

    def ratios(self, symbol: str) -> pd.DataFrame:
        """Quarterly ratio history (camelCase columns as returned, quarter 5 = full year)."""
        return pd.DataFrame(self._iq(f"{symbol.upper()}/statistics-financial"))

    def company(self, symbol: str) -> dict:
        return self._iq("details", ticker=symbol.upper())

    # ---- Price board ----------------------------------------------------------------------

    def price_board(self, symbols: list[str]) -> pd.DataFrame:
        """Current session snapshot from KBS: exchange and foreign buy/sell/room."""
        body = self._request("POST", KBS_BOARD_URL, _KBS_HEADERS, json={"code": ",".join(s.upper() for s in symbols)})
        frame = pd.DataFrame(body)
        if frame.empty:
            return frame
        missing = {"SB", "FB", "FS", "FR", "TD", "EX"} - set(frame.columns)
        if missing:
            raise MarketDataError(f"KBS price board lacks {missing}, the API layout may have changed")
        return pd.DataFrame({
            "symbol": frame["SB"].str.upper(),
            "exchange": frame["EX"],
            # TD is the session date (dd/mm/yyyy), valid on weekends too
            "trading_date": pd.to_datetime(frame["TD"], format="%d/%m/%Y").dt.date.astype(str),
            "snapshot_at": pd.to_datetime(pd.to_numeric(frame.get("t"), errors="coerce"), unit="ms", utc=True),
            "foreign_buy_vol": pd.to_numeric(frame["FB"], errors="coerce"),
            "foreign_sell_vol": pd.to_numeric(frame["FS"], errors="coerce"),
            "foreign_room": pd.to_numeric(frame["FR"], errors="coerce"),
        })
