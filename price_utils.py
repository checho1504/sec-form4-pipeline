import numpy as np
import pandas as pd


def build_price_index(prices_df: pd.DataFrame) -> dict:
    """Pre-sorts price data per ticker into numpy arrays for fast
    positional lookups. Shared by event_study.py (forward returns)
    and signals.py (lookback features)."""
    prices = prices_df.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.dropna(subset=["date", "adjClose"])

    price_index = {}
    for ticker, grp in prices.sort_values("date").groupby("join_ticker", sort=False):
        price_index[ticker] = (
            grp["date"].to_numpy(),
            grp["adjClose"].to_numpy(dtype="float64"),
        )
    return price_index

