"""Run the pipeline end to end: bronze -> silver -> gold, then check the gold contract.

Usage:
    python -m src.pipeline                       # defaults below
    python -m src.pipeline --db out/lake.db --run-id manual-1

Bronze is append-only: every run adds its rows to bronze_prices_raw, tagged with its run id.
Silver and gold are rebuilt from this run's bronze load and replace the previous tables, so rerunning
with the same input gives the same silver and gold tables.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

import pandas as pd

from src import bronze, contract, gold, silver

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_table(df: pd.DataFrame, db_path: str, table: str) -> None:
    with sqlite3.connect(db_path) as con:
        df.to_sql(table, con, if_exists="replace", index=False)


def run(raw_dir: str, db_path: str, contract_path: str, run_id: str) -> int:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    raw = bronze.ingest_raw(raw_dir, run_id=run_id)
    bronze.write_bronze(raw, db_path)
    print(f"bronze     {len(raw):>6} rows appended to bronze_prices_raw (run {run_id})")

    good, quarantine = silver.build_silver(raw)
    write_table(good, db_path, "silver_prices")
    write_table(quarantine, db_path, "silver_quarantine")
    print(f"silver     {len(good):>6} rows in silver_prices")
    reasons = quarantine["reject_reason"].value_counts().to_dict()
    print(f"quarantine {len(quarantine):>6} rows in silver_quarantine {reasons}")

    daily = gold.daily_prices(good)
    monthly = gold.monthly_summary(good)
    features = gold.price_features(good)
    write_table(daily, db_path, "gold_prices_daily")
    write_table(monthly, db_path, "gold_monthly_summary")
    write_table(features, db_path, "gold_price_features")
    print(f"gold       {len(daily):>6} rows in gold_prices_daily")
    print(f"gold       {len(monthly):>6} rows in gold_monthly_summary")
    print(f"gold       {len(features):>6} rows in gold_price_features")

    spec = contract.load_contract(contract_path)
    problems = contract.validate(daily, spec)
    fresh = contract.check_freshness(daily, spec, today=pd.Timestamp.now().normalize())
    print(f"contract   {spec['dataset']}: {'pass' if not problems else '; '.join(problems)}")
    print(f"freshness  newest trade_date {daily['trade_date'].max():%Y-%m-%d}: "
          f"{'fresh' if fresh else 'stale'} (max age {spec['freshness']['max_age_days']} days; "
          "the bundled synthetic data is historical, so it reports stale)")
    return 1 if problems else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--raw-dir", default=os.path.join(ROOT, "data", "raw"))
    p.add_argument("--db", default=os.path.join(ROOT, "output", "lakehouse.db"))
    p.add_argument("--contract", default=os.path.join(ROOT, "contracts", "prices_daily.yaml"))
    p.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ"))
    a = p.parse_args(argv)
    return run(a.raw_dir, a.db, a.contract, a.run_id)


if __name__ == "__main__":
    sys.exit(main())
