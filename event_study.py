"""the goal of this script is to measure what happened to stock prices after the insider transactions took place.
event_price_date is the actual trading day used for the event. """

import os
import io
import pandas as pd
from config import CIKS
from storage import write_parquet, upload_to_r2, get_r2_client
import numpy as np

def load_prices_from_r2(tickers: list[str] | None = None) -> pd.DataFrame:
    """load combined price data from R2"""
    client = get_r2_client()
    bucket = os.getenv("R2_BUCKET_NAME")
    tickers = tickers or list(CIKS.keys())
    all_prices = []

    for ticker in tickers:
        key = f"prices/ticker={ticker}/prices_{ticker.lower()}.parquet"

        try:
            response = client.get_object(Bucket=bucket, Key=key)
            data = response["Body"].read()
            df = pd.read_parquet(io.BytesIO(data))
            all_prices.append(df)
            print(f"loaded prices for {ticker}: {len(df)} rows")

        except Exception as e:
            print(f"could not load prices for {ticker}: {e}")

    if not all_prices:
        print("No price data loaded")
        return pd.DataFrame()

    prices_df = pd.concat(all_prices, ignore_index=True)
    prices_df = prices_df.rename(columns={"ticker": "join_ticker"})  # match events' join key

    return prices_df

def load_events_from_r2(tickers: list[str] | None = None) -> pd.DataFrame:
    """
    Load form4 and price data from R2 and combine them
    """
    client = get_r2_client()
    bucket = os.getenv("R2_BUCKET_NAME")
    tickers = tickers or list(CIKS.keys())
    all_events = []
    for ticker in tickers:
        #file path/address
        key = f"events/ticker={ticker}/events_{ticker.lower()}.parquet"

        try:
            response = client.get_object(Bucket=bucket, Key=key)
            data = response["Body"].read()
            df = pd.read_parquet(io.BytesIO(data)) #wraps raw bytes in object that behaves like file
            df["requested_ticker"] = ticker
            all_events.append(df)
            print(f"loaded {ticker}: {len(df)} rows")

        except Exception as e:
            print(f"could not load events for {ticker}: {e}")

    if not all_events:
        print("No event data loaded")
        return pd.DataFrame()

    events_df = pd.concat(all_events, ignore_index=True)
    events_df["join_ticker"] = events_df["requested_ticker"]  # alias for prices' join key

    return events_df

def get_purchase_events(events_df: pd.DataFrame) -> pd.DataFrame:
    """P = purchase. transaction_price_per:share > 0 removes grants, awards, etc"""

    purchase_events = events_df[(events_df["transaction_code"] == "P") & (events_df["transaction_acquired_disposed_code"] == "A") & (events_df["transaction_price_per_share"] > 0)].copy()
    return purchase_events

def count_duplicate_purchase_rows(purchase_events: pd.DataFrame) -> int:
    dedupe_cols = [
        "issuer_ticker",
        "accession_number",
        "reporting_owner_name",
        "transaction_date",
        "transaction_code",
        "transaction_acquired_disposed_code",
        "transaction_shares",
        "transaction_price_per_share",
        "shares_owned_following_transaction",
        "event_price_date",
        "event_adj_close",
    ]

    duplicate_count = purchase_events.duplicated(subset=dedupe_cols).sum()

    return duplicate_count

def get_forward_return(price_df: pd.DataFrame, event_date, ticker:str, horizon_days: int, ) -> float | None:
    """% change in adjClose from event date to trading day horizon date
    """
    event_date = pd.to_datetime(event_date)

    # no events returns none

    if pd.isna(event_date):
        return None

    ticker_prices = price_df[price_df["join_ticker"] == ticker].copy()

    if ticker_prices.empty:
        return None

    ticker_prices["date"] = pd.to_datetime(ticker_prices["date"])

    # Drop NaT or missing adjclose before sorting

    ticker_prices = ticker_prices.dropna(subset=["date","adjClose"])

    if ticker_prices.empty:
        return None

    ticker_prices = ticker_prices.sort_values("date")
    dates = ticker_prices["date"].to_numpy()
    closes = ticker_prices["adjClose"].to_numpy(dtype="float64")
    event_date_np = np.datetime64(event_date)

    start_idx = np.searchsorted(dates, event_date_np, side="left")
    if start_idx >= len(dates):
        return None # event after price date

    end_idx = start_idx + horizon_days
    if end_idx >= len(dates):
        return None #not enough future trading days yet

    start_price = closes[start_idx]
    end_price = closes[end_idx]

    if start_price == 0:
        return None

    return(end_price / start_price) - 1


def _build_price_index(prices_df: pd.DataFrame) -> dict:
    """Pre-sorts price data per ticker into numpy arrays for fast
    positional lookups.
    """
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


def build_event_returns(events_df: pd.DataFrame, prices_df: pd.DataFrame, horizons: list[int] = [1, 5, 20, 60, 90], event_date_col: str = "event_price_date", 
ticker_col: str = "join_ticker") -> pd.DataFrame:
    """ Vectorized forward-return computation for every event, across every horizon..
    """
    events = events_df.copy()
    events[event_date_col] = pd.to_datetime(events[event_date_col]) 

    price_index = _build_price_index(prices_df)

    for h in horizons:
        events[f"fwd_return_{h}d"] = np.nan

    missing_tickers = set()

    for ticker, group in events.groupby(ticker_col, sort=False):
        if ticker not in price_index:
            missing_tickers.add(ticker)
            continue

        dates, closes = price_index[ticker]
        n = len(dates)

        event_dates = group[event_date_col].to_numpy()
        nat_mask = pd.isna(group[event_date_col]).to_numpy()

        start_idx = np.searchsorted(dates, event_dates, side="left")
        valid_start = (start_idx < n) & ~nat_mask

        start_prices = np.full(len(group), np.nan)
        start_prices[valid_start] = closes[start_idx[valid_start]]

        for h in horizons:
            end_idx = start_idx + h
            valid_end = valid_start & (end_idx < n)

            end_prices = np.full(len(group), np.nan)
            end_prices[valid_end] = closes[end_idx[valid_end]]

            with np.errstate(divide="ignore", invalid="ignore"):
                returns = (end_prices / start_prices) - 1
            returns[start_prices == 0] = np.nan

            events.loc[group.index, f"fwd_return_{h}d"] = returns

    if missing_tickers:
        print(f"No price data found for {len(missing_tickers)} tickers: {sorted(missing_tickers)}")

    return events


        
if __name__ == "__main__":
    events_df = load_events_from_r2()

    if events_df.empty:
        print("No event data found.Run market_data.py & join first.py")
        raise SystemExit # sotps running now. Nothing should execute from here on

    purchase_events = get_purchase_events(events_df)
    duplicate_purchase_rows = count_duplicate_purchase_rows(purchase_events)

    print("\nCombined event dataset:")
    print(f"Rows: {len(events_df)}")
    print(f"Columns: {len(events_df.columns)}")
    print("\nTickers:")
    print(events_df["issuer_ticker"].value_counts())
    print("\nMissing event prices:")
    print("\nPurchase-only signal dataset:")
    print(f"Purchase-only rows: {len(purchase_events)} out of {len(events_df)} total events")
    print(f"Duplicate rows within purchases: {duplicate_purchase_rows} out of {len(purchase_events)}")

    print("\nPurchase-only rows by ticker:")
    print(purchase_events["issuer_ticker"].value_counts())

    print(events_df["event_adj_close"].isna().sum())
    print(events_df[[
        "requested_ticker",
        "issuer_ticker",
        "accession_number",
        "filing_date",
        "transaction_date",
        "transaction_code",
        "transaction_value",
        "event_price_date",
        "event_adj_close",
        "event_volume",
        "price_lag_days",
    ]].tail(30))

  #  Phase 3A: forward returns, full purchase-event dataset ---

    all_purchase_tickers = purchase_events["join_ticker"].unique().tolist()
    print(f"\nLoading price data for {len(all_purchase_tickers)} tickers with purchase events...")

    all_prices_df = load_prices_from_r2(tickers=all_purchase_tickers)

    if all_prices_df.empty:
        print("No price data loaded, cannot compute forward returns")
    else:
        event_returns_df = build_event_returns(
            purchase_events,
            all_prices_df,
            horizons=[1, 5, 20, 60, 90],
        )

        print(f"\nForward returns computed for {len(event_returns_df)} purchase events")

        print("\nNaN counts per horizon (full dataset):")
        for h in [1, 5, 20, 60, 90]:
            col = f"fwd_return_{h}d"
            print(f"{col}: {event_returns_df[col].isna().sum()} / {len(event_returns_df)}")

        return_cols = [f"fwd_return_{h}d" for h in [1, 5, 20, 60, 90]] #horizon periods
        
        print(event_returns_df[return_cols].describe())
        print("\nMedian returns:")
        print("\nWin rates excluding NaN:")
        print(event_returns_df[return_cols].apply(lambda col: (col.dropna() > 0).mean()))
        
        print((event_returns_df[return_cols] > 0).mean())  



        #  Save event returns dataset 
        for ticker, group in event_returns_df.groupby("join_ticker"):
            returns_path = write_parquet(group, ticker, dataset="event_returns")
            upload_to_r2(returns_path, ticker, dataset="event_returns")

        print(f"\nSaved and uploaded event_returns for {event_returns_df['join_ticker'].nunique()} tickers")
        print("\nSample rows:")
        print(event_returns_df[[
            "requested_ticker",
            "reporting_owner_name",
            "event_price_date",
            "fwd_return_1d",
            "fwd_return_5d",
            "fwd_return_20d",
            "fwd_return_60d",
            "fwd_return_90d",
        ]].sample(min(15, len(event_returns_df)), random_state=42))

        



