from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from src.companies import fetch_companies
from src.config import Settings
from src.financial_statements import fetch_financial_statements
from src.foreign_trading import fetch_foreign_trading
from src.historical_prices import fetch_historical_prices
from src.market_client import MarketClient

# Re-fetch a few days before the latest loaded date so late corrections from the source are picked up.
INCREMENTAL_OVERLAP_DAYS = 5


def incremental_start_dates(latest_dates: dict[str, str], symbols: list[str]) -> dict[str, str]:
    """Per-symbol start date: latest loaded date minus the overlap; symbols not yet loaded use START_DATE."""
    starts = {}
    for symbol in symbols:
        latest = latest_dates.get(symbol.upper())
        if latest:
            starts[symbol.upper()] = (date.fromisoformat(latest) - timedelta(days=INCREMENTAL_OVERLAP_DAYS)).isoformat()
    return starts


def _stamp(frame: pd.DataFrame, extracted_at: datetime) -> pd.DataFrame:
    frame = frame.copy()
    frame.insert(0, "ingestion_date", extracted_at.date().isoformat())
    frame["extracted_at"] = extracted_at.isoformat()
    return frame


def extract_all(settings: Settings, mock: bool = False, start_dates: dict[str, str] | None = None) -> dict[str, pd.DataFrame]:
    """Call the market data sources for every dataset. Keys are the Bronze table names."""
    extracted_at = datetime.now(timezone.utc)
    symbols, source = settings.symbols, settings.source
    client = None if mock else MarketClient()
    frames = {
        "companies_raw": fetch_companies(symbols, source, mock=mock, client=client),
        "historical_prices_raw": fetch_historical_prices(symbols, settings.start_date, settings.end_date, source, mock=mock, start_dates=start_dates, client=client),
        "financial_statements_raw": fetch_financial_statements(symbols, source, mock=mock, client=client),
        "foreign_trading_raw": fetch_foreign_trading(symbols, mock=mock, client=client),
    }
    for name, frame in frames.items():
        frames[name] = _stamp(frame, extracted_at)
        print(f"EXTRACTED {len(frame)} rows for {name}")
    return frames


# Airflow hands data from ingest_vnstock to load_bronze through a temporary staging folder
# (outside the repo, deleted after loading). Pickle keeps dtypes and needs no extra dependency.
def write_staging(frames: dict[str, pd.DataFrame], staging_dir: Path) -> None:
    staging_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.to_pickle(staging_dir / f"{name}.pkl")


def read_staging(staging_dir: Path) -> dict[str, pd.DataFrame]:
    files = sorted(staging_dir.glob("*.pkl"))
    if not files:
        raise FileNotFoundError(f"No staged data in {staging_dir}; did ingest_vnstock run?")
    return {file.stem: pd.read_pickle(file) for file in files}
