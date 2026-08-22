import pandas as pd

MAX_PLAUSIBLE_PRICE_PER_SHARE = 100_000.0
MAX_PLAUSIBLE_SHARES = 500_000_000


def build_price_index(prices_df: pd.DataFrame) -> dict:
    """Pre-sorts price data per ticker into numpy arrays for fast
    positional lookups. Shared by event_study.py 
    and signals.py"""
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