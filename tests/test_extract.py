from datetime import date

import pandas as pd
import pytest

from src.config import Settings
from src.extract import extract_all, incremental_start_dates, read_staging, write_staging

SETTINGS = Settings(
    database_url=None, source="VCI", symbols=["FPT", "HPG"],
    start_date="2024-01-01", end_date="2024-01-02", slack_webhook_url=None,
)


def test_extract_all_mock_returns_bronze_tables():
    frames = extract_all(SETTINGS, mock=True)

    assert set(frames) == {"companies_raw", "historical_prices_raw", "financial_statements_raw", "foreign_trading_raw"}
    for frame in frames.values():
        assert not frame.empty
        assert {"ingestion_date", "extracted_at"} <= set(frame.columns)
    assert {"is_bank", "shares_outstanding", "foreign_ownership_pct"} <= set(frames["companies_raw"].columns)
    assert frames["foreign_trading_raw"][["foreign_buy_vol", "foreign_sell_vol"]].notna().all().all()
    assert frames["financial_statements_raw"][["pe_ratio", "pb_ratio", "profit_parent"]].notna().all().all()


def test_staging_round_trip(tmp_path):
    frames = extract_all(SETTINGS, mock=True)
    write_staging(frames, tmp_path / "run")
    loaded = read_staging(tmp_path / "run")
    assert set(loaded) == set(frames)
    pd.testing.assert_frame_equal(loaded["historical_prices_raw"], frames["historical_prices_raw"])


def test_read_staging_fails_when_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_staging(tmp_path)


def test_incremental_start_dates_overlap_and_first_load():
    starts = incremental_start_dates({"FPT": "2026-09-23"}, ["FPT", "HPG"])
    # 5-day overlap for loaded symbols; HPG has no history yet so it falls back to START_DATE
    assert starts == {"FPT": "2026-09-18"}


def test_check_day_skips_weekend_without_api_call():
    from src.check_day import check_trading_day

    ok, reason = check_trading_day(date(2026, 9, 26), "FPT", client=object())  # Saturday, client never called
    assert not ok and "weekend" in reason


def test_fetch_ratios_aligns_quarters_with_income_periods():
    from src import financial_statements

    class FakeClient:
        def ratios(self, symbol):
            return pd.DataFrame({
                "year": [2025, 2025, 2026], "quarter": [4, 5, 1],
                "pe": [14.2, 13.9, 13.7], "pb": [2.2, 2.19, 2.1], "netInterestMargin": [0.03, 0.03, 0.028],
            })

    ratios = financial_statements.fetch_ratios("VCB", FakeClient())
    # quarter 5 (full year) is dropped; quarters map to the income statement's "YYYY-Qn" labels
    assert list(ratios.index) == ["2025-Q4", "2026-Q1"]
    assert ratios.loc["2026-Q1", "pe_ratio"] == 13.7
    assert ratios.loc["2025-Q4", "pb_ratio"] == 2.2
    assert ratios.loc["2026-Q1", "nim"] == 0.028


def test_check_day_skips_holiday_even_if_api_returns_later_bars():
    from src.check_day import check_trading_day

    class FakeClient:
        def daily_prices(self, symbol, start, end):
            # A UTC container once got the 3/9 bar for end=2026-09-02 (National Day)
            return pd.DataFrame({"trading_date": ["2026-08-27", "2026-08-28", "2026-09-03"]})

    ok, reason = check_trading_day(date(2026, 9, 2), "VCB", FakeClient())
    assert not ok and "holiday" in reason
    assert check_trading_day(date(2026, 9, 3), "VCB", FakeClient())[0]


def test_income_statement_parses_fields_and_bank_revenue(monkeypatch):
    from src.market_client import MarketClient

    client = MarketClient()
    monkeypatch.setattr(client, "_iq", lambda path, **params: {"quarters": [
        {"yearReport": 2026, "lengthReport": 2, "publicDate": "2026-08-19T00:00:00", "isb38": 26.0, "isa20": 14.5, "isa22": 14.4},
        {"yearReport": 2025, "lengthReport": 5, "publicDate": "2026-03-01T00:00:00", "isa3": 99.0, "isa20": 1.0, "isa22": 1.0},
    ]})
    frame = client.income_statement("VCB")
    # the full-year row (lengthReport 5) is dropped; banks fall back to total operating income
    assert frame.to_dict("records") == [{"report_period": "2026-Q2", "public_date": "2026-08-19", "revenue": 26.0, "profit": 14.5, "profit_parent": 14.4}]
