"""Pipeline entry point. Each subcommand is one task of the Airflow DAG:

    check-day    -> check_day       (exit code 99 = not a trading day, Airflow marks the run skipped)
    ingest       -> ingest_vnstock  (call the VCI/KBS market data APIs, stage the raw data in a temp folder)
    load-bronze  -> load_bronze     (append staged data to Supabase bronze.*, then delete the folder)
    run          -> ingest + load in one process, for local runs without Airflow
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import shutil
import sys
import uuid

from src.config import VN_TZ, load_settings

SKIP_EXIT_CODE = 99


def _require_database(settings) -> str:
    if not settings.database_url:
        raise SystemExit("No database connection configured: set DATABASE_URL or PGHOST/PGUSER/PGPASSWORD in .env.")
    return settings.database_url


def _ingest(settings, mock: bool, full_refresh: bool):
    from src.bronze_loader import latest_trading_dates
    from src.extract import extract_all, incremental_start_dates

    start_dates = None
    if not mock:
        if not full_refresh:
            start_dates = incremental_start_dates(latest_trading_dates(_require_database(settings)), settings.symbols)
            if start_dates:
                print(f"INCREMENTAL price start dates: {start_dates}")
    return extract_all(settings, mock=mock, start_dates=start_dates)


def cmd_check_day(args, settings) -> int:
    from src.check_day import check_trading_day

    day = date.fromisoformat(args.date) if args.date else datetime.now(VN_TZ).date()
    ok, reason = check_trading_day(day, settings.symbols[0])
    print(("TRADING_DAY " if ok else "SKIP ") + reason)
    return 0 if ok else SKIP_EXIT_CODE


def cmd_ingest(args, settings) -> int:
    from src.extract import write_staging

    frames = _ingest(settings, args.mock, args.full_refresh)
    write_staging(frames, Path(args.staging_dir))
    print(f"STAGED {sum(len(f) for f in frames.values())} rows in {args.staging_dir}")
    return 0


def cmd_load_bronze(args, settings) -> int:
    from src.bronze_loader import load_all
    from src.extract import read_staging

    staging_dir = Path(args.staging_dir)
    load_all(read_staging(staging_dir), _require_database(settings), args.batch_id)
    shutil.rmtree(staging_dir, ignore_errors=True)
    return 0


def cmd_run(args, settings) -> int:
    from src.bronze_loader import load_all

    frames = _ingest(settings, args.mock, args.full_refresh)
    if args.mock:
        print("MOCK run: nothing loaded to Supabase")
        return 0
    load_all(frames, _require_database(settings), args.batch_id)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VNStock ELT pipeline: VCI/KBS market data -> Supabase bronze.")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-day", help="Exit 0 on a trading day with data available, 99 otherwise.")
    check.add_argument("--date", help="YYYY-MM-DD, defaults to today in Vietnam time.")

    for name, helptext in [("ingest", "Extract market data into a staging folder."), ("run", "Extract and load to Supabase in one go.")]:
        cmd = sub.add_parser(name, help=helptext)
        cmd.add_argument("--mock", action="store_true", help="Use fixed sample data, no API or database calls.")
        cmd.add_argument("--full-refresh", action="store_true", help="Ignore Bronze and fetch prices from START_DATE.")
        if name == "ingest":
            cmd.add_argument("--staging-dir", required=True)
        else:
            cmd.add_argument("--batch-id", default=f"manual__{uuid.uuid4().hex[:8]}")

    load = sub.add_parser("load-bronze", help="Load a staging folder into Supabase bronze.")
    load.add_argument("--staging-dir", required=True)
    load.add_argument("--batch-id", required=True, help="Stored in every row for lineage (Airflow run_id).")

    args = parser.parse_args(argv)
    handlers = {"check-day": cmd_check_day, "ingest": cmd_ingest, "load-bronze": cmd_load_bronze, "run": cmd_run}
    return handlers[args.command](args, load_settings())


if __name__ == "__main__":
    sys.exit(main())
