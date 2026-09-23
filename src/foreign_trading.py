from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _session_date(timestamp: pd.Timestamp) -> str:
    """Trading session a snapshot belongs to: VN local date, rolled back from weekends to Friday.

    Public holidays are not handled; a snapshot taken on a holiday repeats the previous session.
    """
    local = timestamp.tz_convert(VN_TZ).normalize()
    if local.weekday() >= 5:
        local -= pd.Timedelta(days=local.weekday() - 4)
    return local.date().isoformat()


def fetch_foreign_trading(symbols: list[str], mock: bool = False) -> pd.DataFrame:
    """Snapshot of today's foreign buy/sell volumes from the KBS price board.

    vnstock (community) has no historical foreign-flow endpoint: Quote.history() only
    returns OHLCV. The price board carries the current session's foreign volumes, so the
    pipeline stores one snapshot per run and builds the history day by day. Run it after
    the market closes (after 15:00 VN time) to capture the full session.
    """
    if mock:
        return pd.DataFrame([
            {"symbol": symbol.upper(), "trading_date": "2024-01-02", "snapshot_at": "2024-01-02T08:30:00+00:00", "foreign_buy_vol": 140, "foreign_sell_vol": 100, "foreign_room": 1000000, "source": "KBS"}
            for symbol in symbols
        ])

    try:
        from vnstock.api.trading import Trading
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("vnstock package is required for live API extraction.") from exc

    board = Trading(source="KBS", symbol=symbols[0]).price_board([symbol.upper() for symbol in symbols])
    if not isinstance(board, pd.DataFrame) or board.empty:
        return pd.DataFrame()

    now = pd.Timestamp.now(tz="UTC")
    if "time" in board.columns:
        # "time" is the last-update epoch in milliseconds, so it also gives the session date on weekends.
        snapshot_at = pd.to_datetime(pd.to_numeric(board["time"], errors="coerce"), unit="ms", utc=True).fillna(now)
    else:
        # The board sometimes omits "time"; fall back to now.
        snapshot_at = pd.Series(now, index=board.index)
    return pd.DataFrame({
        "symbol": board["symbol"].str.upper(),
        "trading_date": snapshot_at.map(_session_date),
        "snapshot_at": snapshot_at.map(lambda value: value.isoformat()),
        "foreign_buy_vol": board.get("foreign_buy_volume"),
        "foreign_sell_vol": board.get("foreign_sell_volume"),
        "foreign_room": board.get("foreign_room"),
        "source": "KBS",
    })
