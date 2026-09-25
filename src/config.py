from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    source: str
    symbols: list[str]
    start_date: str
    end_date: str | None
    slack_webhook_url: str | None


def _read_database_url() -> str | None:
    """DATABASE_URL wins; otherwise build a Postgres URI from the PG* variables dbt also uses."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host, user, password = os.getenv("PGHOST"), os.getenv("PGUSER"), os.getenv("PGPASSWORD")
    if not (host and user and password):
        return None
    port = os.getenv("PGPORT", "5432")
    database = os.getenv("PGDATABASE", "postgres")
    return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}?sslmode=require"


def load_settings() -> Settings:
    # Values already in the environment (Docker/Airflow) take precedence over .env
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    symbols = [item.strip().upper() for item in os.getenv("STOCK_SYMBOLS", "VCB,FPT,HPG,VNM").split(",") if item.strip()]
    return Settings(
        database_url=_read_database_url(),
        source=os.getenv("VNSTOCK_SOURCE", "VCI"),
        symbols=symbols,
        start_date=os.getenv("START_DATE", "2024-01-01"),
        end_date=os.getenv("END_DATE") or None,
        slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL") or None,
    )
