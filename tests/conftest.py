import json
import os

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def raw_dir():
    return os.path.join(ROOT, "data", "raw")


@pytest.fixture(scope="session")
def expected():
    with open(os.path.join(ROOT, "data", "expected_counts.json")) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def clean_silver():
    """Clean base data shaped like a silver table (used by the gold integration tests)."""
    df = pd.read_csv(os.path.join(ROOT, "data", "prices_clean.csv"))
    df["trade_date"] = pd.to_datetime(df["date"])
    return df.drop(columns=["date"])[["symbol", "trade_date", "open", "high", "low", "close", "volume"]]
