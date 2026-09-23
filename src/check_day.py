from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def check_trading_day(day: date, probe_symbol: str, source: str) -> tuple[bool, str]:
    """Is `day` a trading session whose data is already published?

    Weekends are rejected without calling the API. For weekdays the probe symbol's daily
    bar must exist, which also covers public holidays (Tet, 30/4, 2/9...) without a
    hard-coded holiday calendar.
    """
    if day.weekday() >= 5:
        return False, f"{day} is a weekend"

    from vnstock.api.quote import Quote

    history = Quote(source=source, symbol=probe_symbol).history(
        start=(day - timedelta(days=7)).isoformat(), end=day.isoformat()
    )
    if history is None or history.empty:
        return False, f"no {probe_symbol} data in the week up to {day}"
    latest = pd.to_datetime(history["time"]).dt.date.max()
    if latest < day:
        return False, f"no {probe_symbol} bar for {day} (latest {latest}): holiday or data not published yet"
    return True, f"{day} is a trading day and {probe_symbol} data is available"
