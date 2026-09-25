from __future__ import annotations

import pandas as pd

from src.market_client import MarketClient

# statistics-financial field -> Bronze column
RATIO_COLUMNS = {
    "pe": "pe_ratio",
    "pb": "pb_ratio",
    "roe": "roe",
    "roa": "roa",
    "afterTaxProfitMargin": "net_margin",
    "debtToEquity": "debt_to_equity",
    "marketCap": "market_cap",
    "numberOfSharesMktCap": "shares_outstanding",
    # Bank KPIs (0 / NULL for non-banks)
    "netInterestMargin": "nim",
    "npl": "npl",
    "casaRatio": "casa_ratio",
}


def fetch_ratios(symbol: str, client: MarketClient) -> pd.DataFrame:
    """Quarterly ratios indexed by report_period (e.g. 2026-Q2)."""
    data = client.ratios(symbol)
    if data.empty or not {"year", "quarter"} <= set(data.columns):
        return pd.DataFrame(columns=list(RATIO_COLUMNS.values()))
    # quarter == 5 is the full-year row
    data = data[data["quarter"].astype(int).between(1, 4)].copy()
    data["report_period"] = data["year"].astype(int).astype(str) + "-Q" + data["quarter"].astype(int).astype(str)
    columns = {source_col: target for source_col, target in RATIO_COLUMNS.items() if source_col in data.columns}
    return data.set_index("report_period")[list(columns)].rename(columns=columns)


def fetch_financial_statements(symbols: list[str], source: str, mock: bool = False, client: MarketClient | None = None) -> pd.DataFrame:
    """One row per symbol and quarter: income statement lines, real publication date and ratios."""
    if mock:
        rows = [
            {"symbol": "FPT", "report_period": "2024-Q4", "public_date": "2025-01-20", "revenue": 1200000.0, "profit": 150000.0, "profit_parent": 140000.0, "pe_ratio": 16.2, "pb_ratio": 1.8, "roe": 0.28, "roa": 0.12, "net_margin": 0.125, "debt_to_equity": 0.9, "market_cap": 1.9e14, "shares_outstanding": 1.47e9, "nim": 0.0, "npl": 0.0, "casa_ratio": None, "source": source.upper()},
            {"symbol": "HPG", "report_period": "2024-Q4", "public_date": "2025-01-25", "revenue": 800000.0, "profit": 95000.0, "profit_parent": 94000.0, "pe_ratio": 12.5, "pb_ratio": 1.1, "roe": 0.11, "roa": 0.06, "net_margin": 0.119, "debt_to_equity": 0.8, "market_cap": 1.7e14, "shares_outstanding": 6.4e9, "nim": 0.0, "npl": 0.0, "casa_ratio": None, "source": source.upper()},
        ]
        return pd.DataFrame(rows)

    client = client or MarketClient()
    frames = []
    for symbol in symbols:
        income = client.income_statement(symbol)
        if income.empty:
            print(f"WARN no income statement for {symbol}")
            continue
        ratios = fetch_ratios(symbol, client)
        frame = income.merge(ratios, how="left", left_on="report_period", right_index=True)
        missing = sorted(set(income["report_period"]) - set(ratios.index))
        if missing:
            print(f"WARN {symbol}: no ratios for periods {missing}")
        frame.insert(0, "symbol", symbol.upper())
        frame["source"] = source.upper()
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
