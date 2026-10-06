"""Bronze layer: land raw data untouched, with lineage metadata.

Rules:
  * Keep every raw value exactly as received (as text). No cleaning here.
  * Add metadata so every row can be traced and replayed.
  * Append-only: loading twice adds rows, it never overwrites history.
"""
import glob
import os
import sqlite3

import pandas as pd


def ingest_raw(raw_dir: str, run_id: str) -> pd.DataFrame:
    """Read every *.csv in raw_dir (sorted by file name) into one DataFrame.

    Contract:
      * all original columns are kept, every value kept as text (no type guessing)
      * extra columns added:
          _source_file   base name of the file the row came from
          _ingested_at   UTC timestamp string for this load
          _run_id        the run_id argument, same on every row
          _row_number    0-based row position within its source file
      * files are read in sorted file-name order, rows keep their file order
    """
    ingested_at = pd.Timestamp.now(tz="UTC").isoformat()
    frames = []
    for path in sorted(glob.glob(os.path.join(raw_dir, "*.csv"))):
        # dtype=str and keep_default_na=False keep every value exactly as received, blanks included
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        df["_source_file"] = os.path.basename(path)
        df["_ingested_at"] = ingested_at
        df["_run_id"] = run_id
        df["_row_number"] = range(len(df))
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"no CSV files found in {raw_dir}")
    return pd.concat(frames, ignore_index=True)


def write_bronze(df: pd.DataFrame, db_path: str, table: str = "bronze_prices_raw") -> int:
    """Append df to a SQLite table and return the number of rows written.

    Calling it twice with the same data must double the table (append-only).
    """
    with sqlite3.connect(db_path) as con:
        df.to_sql(table, con, if_exists="append", index=False)
    return len(df)


def read_bronze(db_path: str, table: str = "bronze_prices_raw") -> pd.DataFrame:
    """Read the whole bronze table back."""
    with sqlite3.connect(db_path) as con:
        return pd.read_sql_query(f"SELECT * FROM {table}", con)
