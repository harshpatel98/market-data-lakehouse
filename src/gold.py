"""Gold layer: consumer-ready tables (BI tables and a point-in-time ML feature table).

Input `silver` has columns: symbol, trade_date (datetime), open, high, low, close, volume.
"""
import pandas as pd


def _sorted(silver: pd.DataFrame) -> pd.DataFrame:
    return silver.sort_values(["symbol", "trade_date"]).reset_index(drop=True)


def daily_prices(silver: pd.DataFrame) -> pd.DataFrame:
    """BI table. Columns: symbol, trade_date, close, volume, return_1d.

    return_1d = close / previous close - 1, computed per symbol in date order.
    The first row of each symbol has NaN. Sorted by symbol, trade_date.
    """
    df = _sorted(silver)
    prev = df.groupby("symbol")["close"].shift(1)
    df["return_1d"] = df["close"] / prev - 1
    return df[["symbol", "trade_date", "close", "volume", "return_1d"]]


def monthly_summary(silver: pd.DataFrame) -> pd.DataFrame:
    """BI table, one row per symbol and month.

    Columns: symbol, month ('YYYY-MM'), first_close, last_close, month_return,
             total_volume, trading_days
    month_return = last_close / first_close - 1 (first/last by date within the month).
    """
    df = _sorted(silver)
    df["month"] = df["trade_date"].dt.strftime("%Y-%m")
    out = df.groupby(["symbol", "month"], as_index=False).agg(
        first_close=("close", "first"),
        last_close=("close", "last"),
        total_volume=("volume", "sum"),
        trading_days=("close", "size"),
    )
    out["month_return"] = out["last_close"] / out["first_close"] - 1
    return out[["symbol", "month", "first_close", "last_close", "month_return",
                "total_volume", "trading_days"]]


def price_features(silver: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    """ML feature table, one row per symbol and as_of_date.

    Columns: symbol, as_of_date, ret_5d, vol_20d, ma_20, label
      ret_5d  = close / close 5 rows earlier - 1
      vol_20d = standard deviation of the last 20 one-day returns (pandas default ddof)
      ma_20   = mean of the last 20 closes (including today)
      label   = 1 if the close `horizon` rows LATER is higher than today's close, else 0

    Features only use data up to and including as_of_date (no look-ahead).
    Drop rows where any feature or the label cannot be computed.
    Sorted by symbol, as_of_date.
    """
    df = _sorted(silver)
    close = df.groupby("symbol")["close"]

    # Features: shift(+n) and trailing rolling windows only look backwards.
    ret_1d = df["close"] / close.shift(1) - 1
    df["ret_5d"] = df["close"] / close.shift(5) - 1
    df["vol_20d"] = ret_1d.groupby(df["symbol"]).transform(lambda r: r.rolling(20).std())
    df["ma_20"] = close.transform(lambda c: c.rolling(20).mean())

    # Label: the only forward-looking column, kept apart from the features.
    future = close.shift(-horizon)
    df["label"] = (future > df["close"]).astype(int)

    keep = df[["ret_5d", "vol_20d", "ma_20"]].notna().all(axis=1) & future.notna()
    out = df.loc[keep, ["symbol", "trade_date", "ret_5d", "vol_20d", "ma_20", "label"]]
    return out.rename(columns={"trade_date": "as_of_date"}).reset_index(drop=True)
