import pandas as pd

from src import bronze


def test_ingest_reads_every_file_and_row(raw_dir, expected):
    df = bronze.ingest_raw(raw_dir, run_id="r1")
    assert len(df) == expected["raw_rows"]


def test_files_are_read_in_sorted_order(raw_dir):
    df = bronze.ingest_raw(raw_dir, run_id="r1")
    files = list(dict.fromkeys(df["_source_file"]))
    assert files == sorted(files)
    assert len(files) == 3


def test_original_columns_kept_as_text(raw_dir):
    df = bronze.ingest_raw(raw_dir, run_id="r1")
    for col in ["symbol", "date", "open", "high", "low", "close", "volume"]:
        assert col in df.columns
        assert not pd.api.types.is_numeric_dtype(df[col]), f"{col} must stay text in bronze"


def test_raw_values_are_not_cleaned(raw_dir):
    df = bronze.ingest_raw(raw_dir, run_id="r1")
    assert df["close"].astype(str).str.startswith("$").any(), "dollar strings must survive"
    messy = df["symbol"].astype(str)
    assert (messy != messy.str.strip().str.upper()).any(), "messy symbols must survive"
    assert (df["date"].astype(str).str.contains("/")).any(), "US-style dates must survive"


def test_metadata_columns(raw_dir):
    df = bronze.ingest_raw(raw_dir, run_id="run-42")
    assert (df["_run_id"] == "run-42").all()
    assert df["_ingested_at"].notna().all()
    first = df[df["_source_file"] == df["_source_file"].iloc[0]]
    assert list(first["_row_number"].head(3)) == [0, 1, 2]
    per_file_max = df.groupby("_source_file")["_row_number"].max()
    counts = df.groupby("_source_file").size()
    assert (per_file_max == counts - 1).all()


def test_write_bronze_is_append_only(raw_dir, tmp_path):
    db = str(tmp_path / "lake.db")
    df = bronze.ingest_raw(raw_dir, run_id="r1")
    n1 = bronze.write_bronze(df, db)
    n2 = bronze.write_bronze(df, db)
    assert n1 == n2 == len(df)
    assert len(bronze.read_bronze(db)) == 2 * len(df)
