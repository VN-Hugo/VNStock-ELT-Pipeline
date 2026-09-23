from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def fetch_historical_prices(symbols: list[str], start_date: str, end_date: str | None, source: str, mock: bool = False, start_dates: dict[str, str] | None = None) -> pd.DataFrame:
    """Daily OHLCV per symbol. start_dates overrides start_date per symbol (incremental loads)."""
    if mock:
        rows = []
        for symbol in symbols:
            rows.extend([
                {"symbol": symbol.upper(), "trading_date": start_date, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000, "source": source.upper()},
                {"symbol": symbol.upper(), "trading_date": "2024-01-02", "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.8, "volume": 1200, "source": source.upper()},
            ])
        return pd.DataFrame(rows)

    try:
        from vnstock.api.quote import Quote
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("vnstock package is required for live API extraction.") from exc

    rows = []
    for symbol in symbols:
        start = (start_dates or {}).get(symbol.upper(), start_date)
        data = Quote(source=source, symbol=symbol).history(start=start, end=end_date or datetime.now(timezone.utc).date().isoformat())
        if hasattr(data, "copy"):
            frame = data.copy()
        else:
            frame = pd.DataFrame(data)
        if frame.empty:
            continue
        frame = frame.rename(columns={"time": "trading_date", "date": "trading_date", "ticker": "symbol"})
        frame["trading_date"] = pd.to_datetime(frame["trading_date"]).dt.strftime("%Y-%m-%d")
        if "symbol" not in frame.columns:
            frame["symbol"] = symbol.upper()
        if "source" not in frame.columns:
            frame["source"] = source.upper()
        rows.append(frame)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
