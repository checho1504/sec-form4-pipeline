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

def get_baseline_returns(prices_df: pd.DataFrame, events_df: pd.DataFrame, horizons: list[int] | None = None,
                         method:str = "spy", event_date_col: str = "event_price_date", n_random_draws: int = 100, random_seed: int = 42) -> pd.DataFrame:
    
    """calculates baseline returns for a set of events using the chosen method: 'SPY': SPY return over the same event window" & 
            'random_days': average. same-ticker returns for a random trading days  """
    
    if horizons is None:
        horizons = [1, 5, 20, 60, 90]
    method = method.lower()

    if method == "spy":
        baseline_events = events_df.copy()
        baseline_events["join_ticker"] = "SPY"

        baseline_returns = build_event_returns(baseline_events, prices_df, horizons=horizons, event_date_col=event_date_col)

        rename_map = {f"fwd_return_{h}d": f"baseline_return_{h}d" for h in horizons}
        baseline_returns = baseline_returns.rename(columns=rename_map)

        return baseline_returns[[f"baseline_return_{h}d" for h in horizons]]
    
    elif method == "random_days":
        rng = np.random.default_rng(random_seed)
        price_index = _build_price_index(prices_df) 
        result = pd.DataFrame(index=events_df.index)
        for h in horizons:
            result[f"baseline_return_{h}d"] = np.nan 

        for ticker, group in events_df.groupby("join_ticker"):
            if ticker not in price_index:
                continue

            dates, closes = price_index[ticker]
            n = len(dates)

            for h in horizons:
                max_start_idx = n - h - 1
                if max_start_idx < 0:
                    continue
                # for each event in tiicker group, averga n random_draws, random-day retunrs 

                for idx in group.index:
                    start_idxs = rng.integers(0, max_start_idx + 1, size=n_random_draws)
                    end_idxs = start_idxs + h

                    start_prices = closes[start_idxs]
                    end_prices = closes[end_idxs]

                    with np.errstate(divide="ignore", invalid="ignore"):
                        draws = (end_prices / start_prices) - 1
                    draws = draws[~np.isnan(draws) & (start_prices != 0)]

                    if len(draws) > 0:
                        result.loc[idx, f"baseline_return_{h}d"] = draws.mean()

        return result

    else:
        raise ValueError(f"Unknown method: {method}")

def summarize_abnormal_returns(event_returns_df: pd.DataFrame, abnormal_cols: list[str], label: str) -> None:
    """Print a describe()-style summary and win rates for a set of abnormal-return columns."""

    print(f"\nSummary of {label} abnormal returns")
    summary = event_returns_df[abnormal_cols].describe()
    rows_to_percent = summary.index != "count"
    summary.loc[rows_to_percent] = summary.loc[rows_to_percent] * 100
    print(summary.round(2))

    print(f"\n{label} win rates excluding NaN:")
    win_rates = event_returns_df[abnormal_cols].apply(lambda col: (col.dropna() > 0).mean()) * 100
    print(win_rates.round(2).astype(str) + "%")



def sumarize_returns_by_transaction_code(event_returns_df: pd.DataFrame, horizons: list[int] = [1, 5, 20, 60, 90],) -> pd.DataFrame:
    """summarize by transaction code"""
    summary_rows = []
    for h in horizons:
        col = f"fwd_return_{h}d"

        summary = (event_returns_df.groupby("transaction_code")[col].agg(valid_return_count="count",
                                                                         mean_return="mean",
                                                                         median_return="median",
                                                                         )
                                                                         .reset_index()
                                                                         )
        summary["horizon_days"] = h
        summary["mean_return_pct"] = summary["mean_return"] * 100
        summary["median_return_pct"] = summary["median_return"] * 100

        summary_rows.append(
            summary[
                [
                    "transaction_code",
                    "horizon_days",
                    "valid_return_count",
                    "mean_return_pct",
                    "median_return_pct",
                ]
            ]
        )

    return pd.concat(summary_rows, ignore_index=True)


        
if __name__ == "__main__":
    HORIZONS = [1, 5, 20, 60, 90]
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

  # forward return by transaction code

    all_event_tickers = events_df["join_ticker"].unique().tolist()  
    all_event_prices_df = load_prices_from_r2(tickers=all_event_tickers)
    if all_event_prices_df.empty:
        print("No data loaded. Cannot summarize return by transaction code")
    else:

        all_event_returns_df = build_event_returns(events_df, all_event_prices_df, horizons=[1, 5, 20, 60, 90],)
        transaction_code_summary = sumarize_returns_by_transaction_code(all_event_returns_df, horizons=[1, 5, 20, 60, 90])

        print("\nForward returns by transaction code:")
        print(
            transaction_code_summary
            .sort_values(["transaction_code", "horizon_days"])
            .round(2)
        )

  # forward returns, full purchase-event dataset 

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
        for h in HORIZONS:
            col = f"fwd_return_{h}d"
            print(f"{col}: {event_returns_df[col].isna().sum()} / {len(event_returns_df)}")

        return_cols = [f"fwd_return_{h}d" for h in [1, 5, 20, 60, 90]]

        p_only_summary = pd.DataFrame({
        "horizon_days": HORIZONS,
        "valid_return_count": [event_returns_df[f"fwd_return_{h}d"].count() for h in [1, 5, 20, 60, 90]],
        "mean_return_pct": [event_returns_df[f"fwd_return_{h}d"].mean() * 100 for h in [1, 5, 20, 60, 90]],
        "median_return_pct": [event_returns_df[f"fwd_return_{h}d"].median() * 100 for h in [1, 5, 20, 60, 90]],
        "win_rate_pct": [
            (event_returns_df[f"fwd_return_{h}d"].dropna() > 0).mean() * 100
            for h in HORIZONS
        ],
    })

        print("\nP-only forward return summary:")
        print(p_only_summary.round(2))

        print("\nForward return summary:")
        summary_stats = event_returns_df[return_cols].describe()

        rows_to_percent = summary_stats.index != "count"
        summary_stats.loc[rows_to_percent] = summary_stats.loc[rows_to_percent] * 100

        print(summary_stats.round(2))

        print("\nWin rates excluding NaN:")

        win_rates = event_returns_df[return_cols].apply(
            lambda col: (col.dropna() > 0).mean()
        ) * 100
        print(win_rates.round(2).astype(str) + "%")

        # Benchmark-adjusted returns

        spy_prices_df = load_prices_from_r2(tickers=["SPY"]) #local R2 stored locally
        if spy_prices_df.empty:
            print("No price data found for SPY, cannot calculate benchmark-adjusted returns")
        else:
            baseline_df = get_baseline_returns(spy_prices_df, purchase_events, horizons=[1, 5, 20, 60, 90], method="spy",)


            for h in [1, 5, 20, 60, 90]:
                stock_col = f"fwd_return_{h}d"
                baseline_col = f"baseline_return_{h}d"
                abnormal_col = f"abnormal_return_{h}d"

                event_returns_df[baseline_col] = baseline_df[baseline_col].reindex(event_returns_df.index)
                event_returns_df[abnormal_col] = event_returns_df[stock_col] - event_returns_df[baseline_col]

            abnormal_cols = [f"abnormal_return_{h}d" for h in HORIZONS]  

            summarize_abnormal_returns(event_returns_df, abnormal_cols, "SPY-adjusted")

        # Random-days baseline (method 2)

        random_baseline_df = get_baseline_returns(all_prices_df, purchase_events, horizons=[1, 5, 20, 60, 90],method="random_days",
        )

        for h in HORIZONS:
            event_returns_df[f"random_baseline_return_{h}d"] = random_baseline_df[f"baseline_return_{h}d"].reindex(event_returns_df.index)
            event_returns_df[f"random_abnormal_return_{h}d"] = event_returns_df[f"fwd_return_{h}d"] - event_returns_df[f"random_baseline_return_{h}d"]

        random_abnormal_cols = [f"random_abnormal_return_{h}d" for h in [1, 5, 20, 60, 90]]

        summarize_abnormal_returns(event_returns_df, random_abnormal_cols, "Random-days-adjusted")
         
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

        # event returns vs baselines, per horizon ---

        comparison_rows = []
        for h in HORIZONS:
            comparison_rows.append({
                "horizon_days": h,
                "raw_mean_pct": event_returns_df[f"fwd_return_{h}d"].mean() * 100,
                "raw_win_rate_pct": (event_returns_df[f"fwd_return_{h}d"].dropna() > 0).mean() * 100,
                "spy_abnormal_mean_pct": event_returns_df[f"abnormal_return_{h}d"].mean() * 100,
                "spy_win_rate_pct": (event_returns_df[f"abnormal_return_{h}d"].dropna() > 0).mean() * 100,
                "random_abnormal_mean_pct": event_returns_df[f"random_abnormal_return_{h}d"].mean() * 100,
                "random_win_rate_pct": (event_returns_df[f"random_abnormal_return_{h}d"].dropna() > 0).mean() * 100,
            })

        comparison_df = pd.DataFrame(comparison_rows)

        print("\nSide-by-side comparison: raw vs. SPY-adjusted vs. random-days-adjusted, per horizon")
        print(comparison_df.round(2))

        
        



