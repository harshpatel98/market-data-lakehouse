"""Silver layer: clean, validate, deduplicate, quarantine.

Rules:
  * Standardize and type the data.
  * Bad rows are QUARANTINED with a reason, never silently dropped.
  * Exactly one row per business key (symbol, trade_date); the latest load wins.
"""
import numpy as np
import pandas as pd

REJECT_ORDER = ["null_date", "null_close", "non_positive_close", "high_below_low"]
LINEAGE = ["_source_file", "_row_number", "_run_id", "_ingested_at"]
SILVER_COLUMNS = ["symbol", "trade_date", "open", "high", "low", "close", "volume"]


def standardize_symbol(s: pd.Series) -> pd.Series:
    """Strip whitespace and upper-case: ' spy ' -> 'SPY'."""
    return s.str.strip().str.upper()


def parse_date(s: pd.Series) -> pd.Series:
    """Parse 'YYYY-MM-DD' and 'MM/DD/YYYY' strings to datetime64.

    Empty, missing or unparseable values become NaT (do not raise).
    """
    iso = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    us = pd.to_datetime(s, format="%m/%d/%Y", errors="coerce")
    return iso.fillna(us)


def parse_price(s: pd.Series) -> pd.Series:
    """Turn strings like '$1,234.50', '12.5' or '' into floats (NaN if invalid)."""
    cleaned = s.astype(str).str.replace(r"[$,\s]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce").astype(float)


def split_valid(df: pd.DataFrame):
    """Split a typed frame into (good, bad). Needs columns trade_date, high, low, close.

    `bad` gets a new column `reject_reason`. A row failing several rules gets the FIRST
    matching reason in REJECT_ORDER:
        null_date           trade_date is missing
        null_close          close is missing
        non_positive_close  close <= 0
        high_below_low      high < low
    `good` must not contain the reject_reason column.
    """
    conditions = [
        df["trade_date"].isna(),
        df["close"].isna(),
        df["close"] <= 0,
        df["high"] < df["low"],
    ]
    reason = pd.Series(np.select(conditions, REJECT_ORDER, default=""), index=df.index)
    is_bad = reason != ""
    good = df[~is_bad].copy()
    bad = df[is_bad].copy()
    bad["reject_reason"] = reason[is_bad]
    return good, bad


def dedupe_latest(df: pd.DataFrame, keys: list) -> pd.DataFrame:
    """Keep one row per key combination: the LATEST by (_source_file, _row_number).

    Later file names sort later; within a file, a later row number wins.
    """
    ordered = df.sort_values(["_source_file", "_row_number"], kind="mergesort")
    return ordered.drop_duplicates(subset=keys, keep="last").sort_values(keys).reset_index(drop=True)


def build_silver(bronze: pd.DataFrame):
    """Full silver step. Returns (silver, quarantine).

    silver columns (at least): symbol, trade_date, open, high, low, close, volume
      * symbol standardized, trade_date datetime, prices float, volume numeric
      * exactly one row per (symbol, trade_date), latest load wins
    quarantine: the rejected rows with a reject_reason column
    Order of operations matters: standardize/parse -> split_valid -> dedupe good rows.
    """
    typed = pd.DataFrame({
        "symbol": standardize_symbol(bronze["symbol"]),
        "trade_date": parse_date(bronze["date"]),
        "open": parse_price(bronze["open"]),
        "high": parse_price(bronze["high"]),
        "low": parse_price(bronze["low"]),
        "close": parse_price(bronze["close"]),
        "volume": pd.to_numeric(bronze["volume"], errors="coerce"),
    }, index=bronze.index)
    for col in LINEAGE:
        if col in bronze.columns:
            typed[col] = bronze[col]

    good, bad = split_valid(typed)
    silver = dedupe_latest(good, ["symbol", "trade_date"])
    quarantine = bad.reset_index(drop=True)
    return silver, quarantine
