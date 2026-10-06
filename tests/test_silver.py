import numpy as np
import pandas as pd

from src import bronze, silver


# ---------- unit tests on tiny frames ----------
def test_standardize_symbol():
    out = silver.standardize_symbol(pd.Series([" spy ", "qqq", "Btc", "SPY"]))
    assert list(out) == ["SPY", "QQQ", "BTC", "SPY"]


def test_parse_date_handles_both_formats_and_bad_values():
    out = silver.parse_date(pd.Series(["2024-03-05", "03/05/2024", "", None, "not a date"]))
    assert out.iloc[0] == pd.Timestamp("2024-03-05")
    assert out.iloc[1] == pd.Timestamp("2024-03-05")
    assert out.iloc[2:].isna().all()


def test_parse_price_handles_symbols_and_blanks():
    out = silver.parse_price(pd.Series(["$1,234.50", "12.5", "", "abc", "0"]))
    assert out.iloc[0] == 1234.50
    assert out.iloc[1] == 12.5
    assert np.isnan(out.iloc[2]) and np.isnan(out.iloc[3])
    assert out.iloc[4] == 0.0


def _typed(rows):
    return pd.DataFrame(rows, columns=["symbol", "trade_date", "high", "low", "close"]).assign(
        trade_date=lambda d: pd.to_datetime(d["trade_date"]))


def test_split_valid_reasons_and_precedence():
    df = _typed([
        ("A", "2024-01-01", 10, 9, 9.5),          # good
        ("A", None, 10, 9, 9.5),                  # null_date
        ("A", "2024-01-03", 10, 9, np.nan),       # null_close
        ("A", "2024-01-04", 10, 9, -1.0),         # non_positive_close
        ("A", "2024-01-05", 8, 9, 8.5),           # high_below_low
        ("A", None, 8, 9, -3.0),                  # several problems -> null_date first
    ])
    good, bad = silver.split_valid(df)
    assert len(good) == 1 and "reject_reason" not in good.columns
    assert list(bad["reject_reason"]) == [
        "null_date", "null_close", "non_positive_close", "high_below_low", "null_date"]


def test_dedupe_latest_keeps_last_load():
    df = pd.DataFrame({
        "symbol": ["A", "A", "A", "B"],
        "trade_date": pd.to_datetime(["2024-01-01"] * 4),
        "close": [1.0, 2.0, 3.0, 9.0],
        "_source_file": ["p1.csv", "p3.csv", "p2.csv", "p1.csv"],
        "_row_number": [0, 0, 5, 0],
    })
    out = silver.dedupe_latest(df, ["symbol", "trade_date"])
    assert len(out) == 2
    assert out.loc[out["symbol"] == "A", "close"].iloc[0] == 2.0  # p3 is the latest file


# ---------- integration test on the dirty landing files ----------
def test_build_silver_on_real_landing_files(raw_dir, expected):
    raw = bronze.ingest_raw(raw_dir, run_id="r1")
    good, bad = silver.build_silver(raw)

    assert len(good) == expected["expected_silver_rows"]
    assert len(bad) == expected["expected_quarantine_rows"]
    assert bad["reject_reason"].notna().all()

    assert not good.duplicated(["symbol", "trade_date"]).any()
    assert (good["close"] > 0).all()
    assert (good["high"] >= good["low"]).all()
    assert good["symbol"].isin(["QQQ", "SPY", "BTC"]).all()
    assert pd.api.types.is_datetime64_any_dtype(good["trade_date"])
    assert pd.api.types.is_float_dtype(good["close"])


def test_late_corrections_win(raw_dir, expected):
    raw = bronze.ingest_raw(raw_dir, run_id="r1")
    good, _ = silver.build_silver(raw)
    for fix in expected["late_corrections"]:
        row = good[(good["symbol"] == fix["symbol"]) &
                   (good["trade_date"] == pd.Timestamp(fix["trade_date"]))]
        assert len(row) == 1
        assert abs(row["close"].iloc[0] - fix["close"]) < 0.01
