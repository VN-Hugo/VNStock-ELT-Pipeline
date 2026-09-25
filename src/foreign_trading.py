from __future__ import annotations

import pandas as pd

from src.market_client import MarketClient


def fetch_foreign_trading(symbols: list[str], mock: bool = False, client: MarketClient | None = None) -> pd.DataFrame:
    """Snapshot of the current session's foreign buy/sell volumes from the KBS price board.

    No free source offers historical foreign flows, so the pipeline stores one snapshot per
    run and builds the history day by day. Run it after the market closes (after 15:00 VN
    time) to capture the full session.
    """
    if mock:
        return pd.DataFrame([
            {"symbol": symbol.upper(), "trading_date": "2024-01-02", "snapshot_at": "2024-01-02T08:30:00+00:00", "foreign_buy_vol": 140, "foreign_sell_vol": 100, "foreign_room": 1000000, "source": "KBS"}
            for symbol in symbols
        ])

    board = (client or MarketClient()).price_board(symbols)
    if board.empty:
        return board
    board["snapshot_at"] = board["snapshot_at"].fillna(pd.Timestamp.now(tz="UTC")).map(lambda value: value.isoformat())
    board["source"] = "KBS"
    return board[["symbol", "trading_date", "snapshot_at", "foreign_buy_vol", "foreign_sell_vol", "foreign_room", "source"]]
