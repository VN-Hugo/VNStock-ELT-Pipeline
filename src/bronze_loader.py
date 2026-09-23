from __future__ import annotations

import pandas as pd
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

BRONZE_SCHEMA = "bronze"
BRONZE_TABLES = ("companies_raw", "historical_prices_raw", "financial_statements_raw", "foreign_trading_raw")


def load_frame(frame: pd.DataFrame, table_name: str, conn_str: str, batch_id: str) -> int:
    """Append a DataFrame to bronze.<table_name>, storing every value as text.

    Bronze is append-only: typing and deduplication happen in the dbt Silver models.
    New columns are added to an existing table (schema evolution); older rows keep NULL.
    """
    if frame is None or frame.empty:
        return 0

    frame = frame.copy()
    frame["batch_id"] = batch_id
    cols = [str(column) for column in frame.columns]
    table = sql.Identifier(BRONZE_SCHEMA, table_name)

    with psycopg2.connect(conn_str) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(BRONZE_SCHEMA)))
            cur.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
                table, sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(c)) for c in cols)
            ))
            for column in cols:
                cur.execute(sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} text").format(table, sql.Identifier(column)))
            values = [
                [None if pd.isna(value) else str(value) for value in row]
                for row in frame.itertuples(index=False, name=None)
            ]
            execute_values(
                cur,
                sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
                    table, sql.SQL(", ").join(sql.Identifier(c) for c in cols)
                ).as_string(cur),
                values,
                page_size=1000,
            )
    return len(frame)


def load_all(frames: dict[str, pd.DataFrame], conn_str: str, batch_id: str) -> dict[str, int]:
    counts = {}
    for table_name, frame in frames.items():
        counts[table_name] = load_frame(frame, table_name, conn_str, batch_id)
        print(f"LOADED {counts[table_name]} rows -> {BRONZE_SCHEMA}.{table_name}")
    return counts


def latest_trading_dates(conn_str: str) -> dict[str, str]:
    """Latest trading_date per symbol already in Bronze; empty on the first run."""
    with psycopg2.connect(conn_str) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('bronze.historical_prices_raw')")
            if cur.fetchone()[0] is None:
                return {}
            cur.execute(
                "SELECT UPPER(symbol), MAX(CAST(trading_date AS DATE))::text "
                "FROM bronze.historical_prices_raw WHERE NULLIF(trading_date, '') IS NOT NULL GROUP BY 1"
            )
            return dict(cur.fetchall())
