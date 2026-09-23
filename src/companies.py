from __future__ import annotations


import pandas as pd


def _shares_outstanding(record: dict) -> float | None:
    market_cap, price = record.get("market_cap"), record.get("current_price")
    if pd.notna(market_cap) and pd.notna(price) and price:
        return round(float(market_cap) / float(price))
    return None


def fetch_companies(symbols: list[str], source: str, mock: bool = False) -> pd.DataFrame:
    if mock:
        return pd.DataFrame([
            {"symbol": "FPT", "company_name": "FPT Corporation", "exchange": "HOSE", "industry": "Technology", "company_type": "CT", "is_bank": False, "shares_outstanding": 1.47e9, "foreign_ownership_pct": 0.45, "foreign_ownership_limit_pct": 0.49, "source": source.upper()},
            {"symbol": "HPG", "company_name": "Hoa Phat Group", "exchange": "HOSE", "industry": "Materials", "company_type": "CT", "is_bank": False, "shares_outstanding": 6.4e9, "foreign_ownership_pct": 0.22, "foreign_ownership_limit_pct": 1.0, "source": source.upper()},
        ])

    try:
        from vnstock.api.company import Company
        from vnstock.api.trading import Trading
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("vnstock package is required for live API extraction.") from exc

    rows = []
    for symbol in symbols:
        data = Company(source=source, symbol=symbol).overview()
        if isinstance(data, pd.DataFrame) and not data.empty:
            record = data.iloc[0].to_dict()
            board = Trading(source=source, symbol=symbol).price_board([symbol])
            exchange = None
            if isinstance(board, pd.DataFrame) and not board.empty:
                try:
                    exchange = board.iloc[0][("listing", "exchange")]
                except (KeyError, IndexError):
                    exchange = None
            exchange = {"HSX": "HOSE", "HNX": "HNX", "UPCOM": "UPCOM"}.get(str(exchange).upper(), exchange)
            rows.append({
                "symbol": symbol.upper(),
                "company_name": record.get("organ_name") or record.get("organ_short_name") or symbol.upper(),
                "exchange": exchange if pd.notna(exchange) else "UNKNOWN",
                "industry": record.get("industry") or record.get("sector") or "UNKNOWN",
                # com_type_code: CT = corporate, NH = bank, CK = securities, BH = insurance
                "company_type": record.get("com_type_code"),
                "is_bank": record.get("is_bank"),
                "shares_outstanding": _shares_outstanding(record),
                # Current snapshot only; used as the fallback foreign metric for all history
                "foreign_ownership_pct": record.get("foreigner_percentage"),
                "foreign_ownership_limit_pct": record.get("maximum_foreign_percentage"),
                "source": source.upper(),
            })
    return pd.DataFrame(rows)
