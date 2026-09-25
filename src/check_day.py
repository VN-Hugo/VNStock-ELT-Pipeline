from __future__ import annotations

from datetime import date, timedelta

from src.market_client import MarketClient


def check_trading_day(day: date, probe_symbol: str, client: MarketClient | None = None) -> tuple[bool, str]:
    """Is `day` a trading session whose data is already published?

    Weekends are rejected without calling the API. For weekdays the probe symbol's daily
    bar must exist, which also covers public holidays (Tet, 30/4, 2/9...) without a
    hard-coded holiday calendar.
    """
    if day.weekday() >= 5:
        return False, f"{day} is a weekend"

    history = (client or MarketClient()).daily_prices(probe_symbol, (day - timedelta(days=7)).isoformat(), day.isoformat())
    if history.empty:
        return False, f"no {probe_symbol} data in the week up to {day}"
    # Test membership, not max(): a source may return bars after `end` depending on the
    # machine's timezone (a UTC container once got 2026-09-03 for end=2026-09-02, a holiday).
    if day.isoformat() not in set(history["trading_date"]):
        return False, f"no {probe_symbol} bar for {day}: holiday or data not published yet"
    return True, f"{day} is a trading day and {probe_symbol} data is available"
