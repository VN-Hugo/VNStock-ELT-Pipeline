from __future__ import annotations


import pandas as pd

# ratio_summary() column -> Bronze column
RATIO_COLUMNS = {
    "pe": "pe_ratio",
    "pb": "pb_ratio",
    "roe": "roe",
    "roa": "roa",
    "after_tax_profit_margin": "net_margin",
    "debt_to_equity": "debt_to_equity",
    "market_cap": "market_cap",
    "number_of_shares_mkt_cap": "shares_outstanding",
}


def fetch_ratios(symbol: str, source: str) -> pd.DataFrame:
    """Quarterly ratios indexed by report_period (e.g. 2026-Q2).

    Finance.ratio() only returns the 4 oldest periods (2018), so it never overlaps the
    income statement periods. Company.ratio_summary() returns the full history.
    """
    from vnstock.api.company import Company

    data = Company(source=source, symbol=symbol).ratio_summary()
    if not isinstance(data, pd.DataFrame) or data.empty or not {"year", "quarter"} <= set(data.columns):
        return pd.DataFrame(columns=list(RATIO_COLUMNS.values()))
    # quarter == 5 is the full-year row
    data = data[data["quarter"].astype(int).between(1, 4)].copy()
    data["report_period"] = data["year"].astype(int).astype(str) + "-Q" + data["quarter"].astype(int).astype(str)
    columns = {source_col: target for source_col, target in RATIO_COLUMNS.items() if source_col in data.columns}
    return data.set_index("report_period")[list(columns)].rename(columns=columns)


def fetch_financial_statements(symbols: list[str], source: str, mock: bool = False) -> pd.DataFrame:
    if mock:
        rows = [
            {"symbol": "FPT", "report_period": "2024-Q4", "revenue": 1200000.0, "profit": 150000.0, "profit_parent": 140000.0, "pe_ratio": 16.2, "pb_ratio": 1.8, "roe": 0.28, "roa": 0.12, "net_margin": 0.125, "debt_to_equity": 0.9, "market_cap": 1.9e14, "shares_outstanding": 1.47e9, "source": source.upper()},
            {"symbol": "HPG", "report_period": "2024-Q4", "revenue": 800000.0, "profit": 95000.0, "profit_parent": 94000.0, "pe_ratio": 12.5, "pb_ratio": 1.1, "roe": 0.11, "roa": 0.06, "net_margin": 0.119, "debt_to_equity": 0.8, "market_cap": 1.7e14, "shares_outstanding": 6.4e9, "source": source.upper()},
        ]
        return pd.DataFrame(rows)

    try:
        from vnstock.api.financial import Finance
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("vnstock package is required for live API extraction.") from exc

    rows = []
    for symbol in symbols:
        data = Finance(source=source, symbol=symbol, period="quarter", get_all=True).income_statement()
        if not isinstance(data, pd.DataFrame) or data.empty:
            print(f"WARN no income statement for {symbol}")
            continue
        metrics = data.set_index("item_id")

        def find_metric(item_ids: tuple[str, ...]):
            # First match wins, so list item_ids in priority order (a set would pick randomly).
            for item_id in item_ids:
                if item_id in metrics.index:
                    return metrics.loc[item_id]
            return None

        revenue = find_metric(("net_sales", "total_operating_income", "sales"))
        profit = find_metric(("net_profit_loss_after_tax",))
        # Profit attributable to parent-company shareholders excludes minority interests; it is
        # the basis for EPS and P/E (FPT's total profit overstates it by ~20% in 2025).
        profit_parent = find_metric(("attributable_to_parent_company",))
        ratios = fetch_ratios(symbol, source)
        periods = [column for column in data.columns if isinstance(column, str) and "-Q" in column]
        for period in periods:
            row = {
                "symbol": symbol.upper(),
                "report_period": period,
                "revenue": revenue.get(period) if revenue is not None else None,
                "profit": profit.get(period) if profit is not None else None,
                "profit_parent": profit_parent.get(period) if profit_parent is not None else None,
            }
            for column in RATIO_COLUMNS.values():
                row[column] = ratios.at[period, column] if period in ratios.index and column in ratios.columns else None
            row["source"] = source.upper()
            rows.append(row)
        missing = [period for period in periods if period not in ratios.index]
        if missing:
            print(f"WARN {symbol}: no ratios for periods {missing}")
    return pd.DataFrame(rows)
