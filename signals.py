"""this module aims at converting raw form 4 into research features that could be later used for back testing and dashboards"""

import numpy as np
import pandas as pd
from storage import upload_to_r2, write_parquet 
from event_study import load_events_from_r2, load_prices_from_r2
from price_utils import build_price_index

def add_lag(events_df: pd.DataFrame) -> pd.DataFrame:
    """Calculates the lag(if any) between the transaciton date and the filing date"""
    df = events_df.copy()
    required_cols = ['filing_date', 'transaction_date']
    missing_columns = [col for col in required_cols if col not in df.columns]

    if missing_columns:
        raise ValueError (f'Missing required columns: {missing_columns}')

    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")

    df['filing_lag_days'] = (df["filing_date"] - df["transaction_date"] ).dt.days # calculates the actual lag days

    return df

def add_role_flag(events_df: pd.DataFrame) -> pd.DataFrame:
    """Creates one categorical role column"""
    df = events_df.copy()
    officer_title = (df['officer_title'].fillna("").astype(str).str.upper())

    is_director = df["is_director"].astype("boolean").fillna(False)
    is_officer = df["is_officer"].astype("boolean").fillna(False)
    is_ten_percent_owner = df["is_ten_percent_owner"].astype("boolean").fillna(False)
    is_other = df["is_other"].astype("boolean").fillna(False)

    df["role_flag"] = "Unknown"
    df.loc[is_other, "role_flag"] = "Other"
    df.loc[is_ten_percent_owner, "role_flag"] = "10% Owner"
    df.loc[is_director, "role_flag"] = "Director"
    df.loc[is_officer, "role_flag"] = "Officer"

    has_officer_title = officer_title.str.strip() != ""
    still_unknown = df["role_flag"] == "Unknown"


    df.loc[has_officer_title & still_unknown, "role_flag"] = "Officer"
    df.loc[officer_title.str.contains("CFO|CHIEF FINANCIAL", regex=True), "role_flag"] = "CFO"
    df.loc[officer_title.str.contains("CEO|CHIEF EXECUTIVE|PRESIDENT AND CEO", regex=True), "role_flag"] = "CEO"

    valid_roles = {"CEO", "CFO", "Officer", "Director", "10% Owner", "Other", "Unknown"}
    unexpected = set(df["role_flag"].unique()) - valid_roles
    if unexpected:
        raise ValueError(f"Unexpected role_flag values produced: {unexpected}")

    return df

def add_open_market_flags(events_df: pd.DataFrame) -> pd.DataFrame:
    """P/A: open market purchase. S/D : public market sale"""
    df = events_df.copy()
    required_columns = ["transaction_code", "transaction_acquired_disposed_code", "transaction_price_per_share"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required column for: {missing_columns}")

    code = (df["transaction_code"].fillna("").astype(str).str.upper().str.strip())
    acq_disposed = (df["transaction_acquired_disposed_code"].fillna("").astype(str).str.upper().str.strip())
    price = pd.to_numeric(df["transaction_price_per_share"], errors="coerce")

    # Purchase signal
    df["is_open_market_purchase"] = (code == "P") & (acq_disposed == "A") & (price > 0)

    # Sale signal 
    df["is_open_market_sale"] = (code == "S") & (acq_disposed == "D") & (price > 0)

    # Simply open market
    df["open_market_only"] = df["is_open_market_purchase"] | df["is_open_market_sale"]

    return df

def build_lookback_features(events_df: pd.DataFrame, prices_df: pd.DataFrame, event_date_col: str ="event_price_date", return_window_days: int = 30,
                            high_window_days: int=252, ticker_col: str = "join_ticker",) -> pd.DataFrame:
    """gets trailing returns/volatility and and distance from a 52-week high, measured as of event_date_col"""

    events = events_df.copy()
    events[event_date_col] = pd.to_datetime(events[event_date_col])

    price_index = build_price_index(prices_df) # orginize tickers price history into sorted data arrays

    return_col = f"prior_{return_window_days}d_returns"
    vol_col = f"prior_{return_window_days}d_volatility"
    high_col = "distance_from_52w_high"

    events[return_col] = np.nan
    events[vol_col] = np.nan
    events[high_col] = np.nan

    missing_tickers = set()
    for ticker,  group in events.groupby(ticker_col, sort=False):
        if ticker not in price_index:
            missing_tickers.add(ticker)
            continue

        dates, closes = price_index[ticker]
        n = len(dates)

        event_dates = group[event_date_col].to_numpy()
        nat_mask = pd.isna(group[event_date_col].to_numpy())
        event_idx = np.searchsorted(dates, event_dates, side="left")
        valid = (event_idx < n) & ~nat_mask 

        for row_label, idx, is_valid in zip(group.index, event_idx, valid):
            if not is_valid:
                continue

            current_price = closes[idx]

        # Trailing return + volatility
            start_idx = idx - return_window_days
            if start_idx >= 0:
                window = closes[start_idx: idx + 1]
                if window[0] != 0:
                    events.at[row_label,return_col] = (current_price / window[0]) - 1 
                if len(window) > 1:
                    daily_returns = window[1:]/window[:-1] - 1
                    events.at[row_label, vol_col] = daily_returns.std()

    #distance from 52w high

            high_star_inx = max(0, idx - high_window_days) 
            window_high = closes[high_star_inx: idx + 1].max()
            if window_high != 0:
                events.at[row_label, high_col] = (current_price - window_high) / window_high

    if missing_tickers:
        print(f"No price data found for {len(missing_tickers)} tickers: {sorted(missing_tickers)}")

    return events

#________________________________________________________________________________________________________________________________#

if __name__ == "__main__":
    from event_study import load_events_from_r2, load_prices_from_r2

    events_df = load_events_from_r2()
    prices_df = load_prices_from_r2()

    if events_df.empty:
        print("No events loaded")
        raise SystemExit

    signals_df = add_lag(events_df)
    signals_df = add_role_flag(signals_df)
    signals_df = add_open_market_flags(signals_df)
    signals_df = build_lookback_features(signals_df, prices_df)

    print(signals_df)
    print("\nSample rows:")
    print(signals_df[["issuer_ticker", "reporting_owner_name", "transaction_date","filing_date","filing_lag_days","transaction_code","transaction_value",]].head(20))
    print("\nRole flag distribution:")
    print(signals_df["role_flag"].value_counts(dropna=False))


    OPEN_MARKET_SAMPLE_COLS = [
    "issuer_ticker", "reporting_owner_name", "filing_date", "transaction_date",
    "transaction_code", "transaction_acquired_disposed_code",
    "transaction_price_per_share", "transaction_value"]

    print("\nOpen-market flag counts:")
    print(signals_df[["is_open_market_purchase", "is_open_market_sale", "open_market_only"]].sum())

    print("\nSample open-market rows:")
    print(signals_df.loc[signals_df["open_market_only"], OPEN_MARKET_SAMPLE_COLS].head(20))

    print(signals_df[["prior_30d_returns", "prior_30d_volatility", "distance_from_52w_high"]].isna().sum())
    print("Volatility describe:", signals_df["prior_30d_volatility"].describe())

    print("\nLookback features across all tickers:")
    print(signals_df[["issuer_ticker", "reporting_owner_name", "event_price_date", "event_adj_close",
     "prior_30d_returns", "prior_30d_volatility", "distance_from_52w_high"]].sample(30, random_state=42))