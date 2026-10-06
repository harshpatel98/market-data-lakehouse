import os

import pandas as pd
import pytest

from src import contract as c

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def spec():
    return c.load_contract(os.path.join(ROOT, "contracts", "prices_daily.yaml"))


def good_df():
    return pd.DataFrame({
        "symbol": ["A", "A", "B"],
        "trade_date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-02"]),
        "close": [1.0, 2.0, 3.0],
        "volume": [10, None, 30],
    })


def test_contract_file_loads(spec):
    assert spec["dataset"] == "gold.prices_daily"
    assert spec["grain_keys"] == ["symbol", "trade_date"]


def test_good_data_passes(spec):
    assert c.validate(good_df(), spec) == []


def test_missing_column(spec):
    assert c.validate(good_df().drop(columns=["close"]), spec) == ["missing column: close"]


def test_null_in_non_nullable(spec):
    df = good_df()
    df.loc[0, "symbol"] = None
    assert "nulls in: symbol" in c.validate(df, spec)


def test_nullable_column_may_have_nulls(spec):
    assert c.validate(good_df(), spec) == []  # volume has a null


def test_min_exclusive_rule(spec):
    df = good_df()
    df.loc[1, "close"] = 0.0
    assert "rule failed: close > 0" in c.validate(df, spec)


def test_duplicate_keys(spec):
    df = pd.concat([good_df(), good_df().iloc[[0]]], ignore_index=True)
    assert "duplicate keys" in c.validate(df, spec)


def test_wrong_kind(spec):
    df = good_df()
    df["trade_date"] = df["trade_date"].dt.strftime("%Y-%m-%d")  # text instead of dates
    assert "wrong kind: trade_date" in c.validate(df, spec)


def test_freshness(spec):
    df = good_df()  # newest date is 2024-01-02, SLA is 3 days
    assert c.check_freshness(df, spec, today=pd.Timestamp("2024-01-05")) is True
    assert c.check_freshness(df, spec, today=pd.Timestamp("2024-01-06")) is False
