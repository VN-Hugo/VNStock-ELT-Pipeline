from __future__ import annotations

import pandas as pd

from src.market_client import MarketClient


def fetch_historical_prices(symbols: list[str], start_date: str, end_date: str | None, source: str, mock: bool = False,
                            start_dates: dict[str, str] | None = None, client: MarketClient | None = None) -> pd.DataFrame:
    """Daily OHLCV per symbol. start_dates overrides start_date per symbol (incremental loads)."""
    if mock:
        rows = []
        for symbol in symbols:
            rows.extend([
                {"symbol": symbol.upper(), "trading_date": start_date, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000, "source": source.upper()},
                {"symbol": symbol.upper(), "trading_date": "2024-01-02", "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.8, "volume": 1200, "source": source.upper()},
            ])
        return pd.DataFrame(rows)

    client = client or MarketClient()
    frames = []
    for symbol in symbols:
        start = (start_dates or {}).get(symbol.upper(), start_date)
        frame = client.daily_prices(symbol, start, end_date)
        if frame.empty:
            print(f"WARN no prices for {symbol} since {start}")
            continue
        frame["symbol"] = symbol.upper()
        frame["source"] = source.upper()
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
