import numpy as np
import pandas as pd

from src import gold


def _silver(rows):
    df = pd.DataFrame(rows, columns=["symbol", "trade_date", "close", "volume"])
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["open"] = df["high"] = df["low"] = df["close"]
    return df


def test_daily_prices_returns_per_symbol():
    s = _silver([
        ("A", "2024-01-01", 100.0, 1), ("A", "2024-01-02", 110.0, 1), ("A", "2024-01-03", 99.0, 1),
        ("B", "2024-01-01", 50.0, 1), ("B", "2024-01-02", 55.0, 1),
    ]).sample(frac=1, random_state=1)  # shuffled input: the function must sort
    out = gold.daily_prices(s)
    assert list(out.columns) == ["symbol", "trade_date", "close", "volume", "return_1d"]
    a = out[out["symbol"] == "A"]["return_1d"].tolist()
    b = out[out["symbol"] == "B"]["return_1d"].tolist()
    assert np.isnan(a[0]) and np.isnan(b[0])
    assert abs(a[1] - 0.10) < 1e-9 and abs(a[2] - (-0.10)) < 1e-9
    assert abs(b[1] - 0.10) < 1e-9
    assert out["trade_date"].is_monotonic_increasing or out.groupby("symbol")["trade_date"].apply(
        lambda x: x.is_monotonic_increasing).all()


def test_monthly_summary():
    s = _silver([
        ("A", "2024-01-02", 100.0, 1), ("A", "2024-01-10", 110.0, 2), ("A", "2024-01-31", 120.0, 3),
        ("A", "2024-02-01", 130.0, 4), ("A", "2024-02-28", 125.0, 5),
    ])
    out = gold.monthly_summary(s).sort_values("month").reset_index(drop=True)
    assert list(out.columns) == ["symbol", "month", "first_close", "last_close",
                                 "month_return", "total_volume", "trading_days"]
    jan, feb = out.iloc[0], out.iloc[1]
    assert jan["month"] == "2024-01" and jan["first_close"] == 100.0 and jan["last_close"] == 120.0
    assert abs(jan["month_return"] - 0.2) < 1e-9 and jan["total_volume"] == 6 and jan["trading_days"] == 3
    assert abs(feb["month_return"] - (125 / 130 - 1)) < 1e-9 and feb["trading_days"] == 2


def _trend(n=40, up=True):
    closes = [100 + i if up else 200 - i for i in range(n)]
    dates = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({"symbol": "A", "trade_date": dates, "open": closes, "high": closes,
                         "low": closes, "close": [float(c) for c in closes], "volume": 1})


def test_features_shape_values_and_labels():
    out = gold.price_features(_trend(40, up=True), horizon=5)
    assert list(out.columns) == ["symbol", "as_of_date", "ret_5d", "vol_20d", "ma_20", "label"]
    assert len(out) == 15  # rows 20..34 have 20 returns of history and 5 rows of future
    assert (out["label"] == 1).all()
    row = out[out["as_of_date"] == pd.bdate_range("2024-01-01", periods=40)[25]].iloc[0]
    assert abs(row["ma_20"] - 115.5) < 1e-9
    assert abs(row["ret_5d"] - (125 / 120 - 1)) < 1e-9
    down = gold.price_features(_trend(40, up=False), horizon=5)
    assert (down["label"] == 0).all()


def test_features_have_no_lookahead(clean_silver):
    full = gold.price_features(clean_silver, horizon=5)
    cutoff = pd.Timestamp("2024-12-31")
    trunc = gold.price_features(clean_silver[clean_silver["trade_date"] <= cutoff], horizon=5)
    m = full.merge(trunc, on=["symbol", "as_of_date"], suffixes=("_full", "_trunc"))
    assert len(m) > 100
    for col in ["ret_5d", "vol_20d", "ma_20"]:
        assert np.allclose(m[f"{col}_full"], m[f"{col}_trunc"]), f"{col} changed when future data was removed"


def test_features_on_real_data_are_clean(clean_silver):
    out = gold.price_features(clean_silver, horizon=5)
    assert out[["ret_5d", "vol_20d", "ma_20", "label"]].notna().all().all()
    assert set(out["label"].unique()) <= {0, 1}
    assert set(out["symbol"]) == {"QQQ", "SPY", "BTC"}
