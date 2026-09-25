from __future__ import annotations

import pandas as pd

from src.market_client import MarketClient

EXCHANGE_NAMES = {"HSX": "HOSE", "HOSE": "HOSE", "HNX": "HNX", "UPCOM": "UPCOM"}


def fetch_companies(symbols: list[str], source: str, mock: bool = False, client: MarketClient | None = None) -> pd.DataFrame:
    if mock:
        return pd.DataFrame([
            {"symbol": "FPT", "company_name": "FPT Corporation", "exchange": "HOSE", "industry": "Technology", "company_type": "CT", "is_bank": False, "shares_outstanding": 1.47e9, "foreign_ownership_pct": 0.45, "foreign_ownership_limit_pct": 0.49, "source": source.upper()},
            {"symbol": "HPG", "company_name": "Hoa Phat Group", "exchange": "HOSE", "industry": "Materials", "company_type": "CT", "is_bank": False, "shares_outstanding": 6.4e9, "foreign_ownership_pct": 0.22, "foreign_ownership_limit_pct": 1.0, "source": source.upper()},
        ])

    client = client or MarketClient()
    # One board call gives the exchange for every symbol
    board = client.price_board(symbols)
    exchange_of = dict(zip(board["symbol"], board["exchange"])) if not board.empty else {}

    rows = []
    for symbol in symbols:
        record = client.company(symbol)
        exchange = exchange_of.get(symbol.upper())
        rows.append({
            "symbol": symbol.upper(),
            "company_name": record.get("viOrganName") or record.get("enOrganName") or symbol.upper(),
            "exchange": EXCHANGE_NAMES.get(str(exchange).upper(), "UNKNOWN") if exchange else "UNKNOWN",
            "industry": record.get("sector") or "UNKNOWN",
            # comTypeCode: CT = corporate, NH = bank, CK = securities, BH = insurance
            "company_type": record.get("comTypeCode"),
            "is_bank": record.get("isBank"),
            "shares_outstanding": record.get("numberOfSharesMktCap"),
            # Current snapshot only; used as the fallback foreign metric for all history
            "foreign_ownership_pct": record.get("foreignerPercentage"),
            "foreign_ownership_limit_pct": record.get("maximumForeignPercentage"),
            "source": source.upper(),
        })
    return pd.DataFrame(rows)
