"""this module aims at converting raw form 4 into research features that could be later used for back testing and dashboards"""

import numpy as np
import pandas as pd
from storage import upload_to_r2, write_parquet 
from event_study import load_events_from_r2, load_prices_from_r2
from price_utils import MAX_PLAUSIBLE_SHARES, MAX_PLAUSIBLE_PRICE_PER_SHARE, build_price_index

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

def build_insider_activity_panel(
    events_df: pd.DataFrame,
    window_days: int = 30,
    ticker_col: str = "join_ticker",
    date_col: str = "transaction_date",
    value_col: str = "transaction_value",
    owner_col: str = "reporting_owner_name",
    code_col: str = "transaction_code",
    acq_disposed_col: str = "transaction_acquired_disposed_code",
    price_col: str = "transaction_price_per_share",
    cluster_threshold: int = 3,
) -> pd.DataFrame:
    """
    Build rolling insider activity features by ticker and date.For each ticker/date, looks back `window_days` and summarizes net buying,
    number of distinct insiders, whether cluster buying happened, and the buy/sell imbalance. Rows with an implausible price or share count are excluded before
    they get aggregated
    """
    required_columns = [
        ticker_col,
        date_col,
        value_col,
        owner_col,
        code_col,
        acq_disposed_col,
        price_col,
    ]

    missing_columns = [col for col in required_columns if col not in events_df.columns]

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    df = events_df.copy()

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce").fillna(0.0)

    code = df[code_col].fillna("").astype(str).str.upper().str.strip()
    acq_disposed = df[acq_disposed_col].fillna("").astype(str).str.upper().str.strip()
    price = pd.to_numeric(df[price_col], errors="coerce")

    # Keep corrupted price fields out of panel signals.
    sane_price = price.between(0, MAX_PLAUSIBLE_PRICE_PER_SHARE, inclusive="neither")
    bad_price_count = int((price > MAX_PLAUSIBLE_PRICE_PER_SHARE).sum())

    if bad_price_count:
        print(f"Warning: excluding {bad_price_count} implausible transaction prices from panel")

    # Keep corrupted share-count fields out of panel signals too.
    shares = pd.to_numeric(df.get("transaction_shares"), errors="coerce")
    sane_shares = shares.between(0, MAX_PLAUSIBLE_SHARES, inclusive="neither")

    bad_shares_count = int((shares > MAX_PLAUSIBLE_SHARES).sum())
    if bad_shares_count:
        print(f"Warning: excluding {bad_shares_count} implausible share counts from panel")

    # Collapse rows where the same trade was filed under multiple affiliated
    # owners (e.g. an executive and their holding LLC/trust) so it isn't
    # double-counted in net_insider_buying.
    dedup_keys = [ticker_col, date_col, code_col, acq_disposed_col, price_col, "transaction_shares"]

    before = len(df)
    df = df.drop_duplicates(subset=dedup_keys, keep="first")
    after = len(df)

    if before != after:
        print(
            f"Warning: collapsed {before - after} duplicate joint-filer rows "
            f"(same transaction reported by multiple affiliated owners)"
        )

    df["is_buy"] = (
        (code == "P") & (acq_disposed == "A") & sane_price & sane_shares & (df[value_col] > 0)
    )
    df["is_sell"] = (
        (code == "S") & (acq_disposed == "D") & sane_price & sane_shares & (df[value_col] > 0)
    )

    df["buy_value"] = np.where(df["is_buy"], df[value_col], 0.0)
    df["sell_value"] = np.where(df["is_sell"], df[value_col], 0.0)

    df = df.dropna(subset=[date_col, ticker_col])

    panel_rows = []

    for ticker, group in df.groupby(ticker_col, sort=False):
        group = group.sort_values(date_col)

        dates = group[date_col].to_numpy()
        buy_values = group["buy_value"].to_numpy()
        sell_values = group["sell_value"].to_numpy()
        is_buy = group["is_buy"].to_numpy()
        owners = group[owner_col].fillna("Unknown").astype(str).to_numpy()

        # One summary row per ticker/date.
        panel_dates = np.unique(dates)

        # Find rolling window boundaries.
        window_start = panel_dates - np.timedelta64(window_days, "D")
        start_idx = np.searchsorted(dates, window_start, side="left")
        end_idx = np.searchsorted(dates, panel_dates, side="right")

        for panel_date, lo, hi in zip(panel_dates, start_idx, end_idx):
            window_buy = buy_values[lo:hi].sum()
            window_sell = sell_values[lo:hi].sum()
            window_owners = owners[lo:hi]
            window_is_buy = is_buy[lo:hi]

            net_insider_buying = window_buy - window_sell
            insider_count = len(np.unique(window_owners))

            buying_insiders = np.unique(window_owners[window_is_buy])
            cluster_buying = len(buying_insiders) >= cluster_threshold

            denom = window_buy + window_sell

            buy_sell_imbalance = (
                (window_buy - window_sell) / denom
                if denom != 0
                else np.nan
            )

            panel_rows.append(
                {
                    ticker_col: ticker,
                    "panel_date": panel_date,
                    "net_insider_buying": net_insider_buying,
                    "gross_buy_value": window_buy,
                    "insider_count": insider_count,
                    "cluster_buying": cluster_buying,
                    "buy_sell_imbalance": buy_sell_imbalance,
                }
            )
    panel_df = pd.DataFrame(
        panel_rows,
        columns=[
            ticker_col,
            "panel_date",
            "net_insider_buying",
            "gross_buy_value",
            "insider_count",
            "cluster_buying",
            "buy_sell_imbalance",
        ],
    )
    return panel_df  

#________________________________________________________________________________________________________________________________#

if __name__ == "__main__":
    from event_study import load_events_from_r2, load_prices_from_r2

    events_df = load_events_from_r2()
    prices_df = load_prices_from_r2()

    if events_df.empty:
        print("No events loaded")
        raise SystemExit

    if prices_df.empty:
        print("No prices loaded")
        raise SystemExit

    # ------------------------------------------------------------
    # Build event-level signal features
    # ------------------------------------------------------------

    signals_df = add_lag(events_df)
    signals_df = add_role_flag(signals_df)
    signals_df = add_open_market_flags(signals_df)
    signals_df = build_lookback_features(signals_df, prices_df)

    print("\nSignals dataset:")
    print(f"Rows: {len(signals_df)}")
    print(f"Columns: {len(signals_df.columns)}")

    print("\nSample rows:")
    print(
        signals_df[
            [
                "issuer_ticker",
                "reporting_owner_name",
                "transaction_date",
                "filing_date",
                "filing_lag_days",
                "transaction_code",
                "transaction_value",
            ]
        ].head(20)
    )

    print("\nRole flag distribution:")
    print(signals_df["role_flag"].value_counts(dropna=False))

    print("\nOpen-market flag counts:")
    print(
        signals_df[
            [
                "is_open_market_purchase",
                "is_open_market_sale",
                "open_market_only",
            ]
        ].sum()
    )

    open_market_sample_cols = [
        "issuer_ticker",
        "reporting_owner_name",
        "filing_date",
        "transaction_date",
        "transaction_code",
        "transaction_acquired_disposed_code",
        "transaction_price_per_share",
        "transaction_value",
    ]

    print("\nSample open-market rows:")
    print(
        signals_df.loc[
            signals_df["open_market_only"],
            open_market_sample_cols,
        ].head(20)
    )

    lookback_cols = [
        "prior_30d_returns",
        "prior_30d_volatility",
        "distance_from_52w_high",
    ]

    print("\nLookback feature missing values:")
    print(signals_df[lookback_cols].isna().sum())

    print("\nVolatility describe:")
    print(signals_df["prior_30d_volatility"].describe())

    print("\nLookback features across all tickers:")
    print(
        signals_df[
            [
                "issuer_ticker",
                "reporting_owner_name",
                "event_price_date",
                "event_adj_close",
                "prior_30d_returns",
                "prior_30d_volatility",
                "distance_from_52w_high",
            ]
        ].sample(30, random_state=42)
    )

    # ------------------------------------------------------------
    # Build panel-level insider activity features
    # ------------------------------------------------------------

    insider_panel_df = build_insider_activity_panel(signals_df)

    if insider_panel_df.empty:
        print("No insider activity data available")
        raise SystemExit
    
    pd.set_option("display.float_format", lambda x: f"{x:,.2f}")

    print("\nInsider activity panel sample:")
    print(insider_panel_df.head(20))

    print("\nCluster buying counts:")
    print(insider_panel_df["cluster_buying"].value_counts(dropna=False))

    print("\nInsider activity panel summary stats:")
    print(
        insider_panel_df[
            [
                "net_insider_buying",
                "insider_count",
                "buy_sell_imbalance",
            ]
        ].describe()
    )

    print("\nLargest absolute net insider buying panel rows after sanity filter:")
    largest_abs_panel_rows = (
        insider_panel_df
        .assign(abs_net_insider_buying=insider_panel_df["net_insider_buying"].abs())
        .sort_values("abs_net_insider_buying", ascending=False)
        .head(10)
    )

    print(largest_abs_panel_rows[["join_ticker","panel_date","net_insider_buying","insider_count","cluster_buying","buy_sell_imbalance",]])

    print("\nTop insider purchase activity (gross buy value, purchases only):")
    top_purchases = (
        insider_panel_df[insider_panel_df["gross_buy_value"] > 0]
        .sort_values("gross_buy_value", ascending=False)
        .head(10)
    )
    print(
        top_purchases[
            [
                "join_ticker",
                "panel_date",
                "gross_buy_value",
                "insider_count",
                "cluster_buying",
            ]
        ]
    )

    print("\nCluster buying rows (3+ distinct insiders buying in the window):")
    cluster_rows = insider_panel_df[insider_panel_df["cluster_buying"]]
    print(
        cluster_rows[
            [
                "join_ticker",
                "panel_date",
                "gross_buy_value",
                "net_insider_buying",
                "insider_count",
            ]
        ]
    )

    # ------------------------------------------------------------
    # Save signals + insider activity panel to R2, one file per ticker
    # ------------------------------------------------------------

    print("\nSaving signals and insider activity panel to R2...")
    for ticker, group in signals_df.groupby("join_ticker", sort=False):
         parquet_path = write_parquet(group, ticker, dataset="signals")
         upload_to_r2(parquet_path, ticker, dataset="signals")

    for ticker, group in insider_panel_df.groupby("join_ticker", sort=False):
         parquet_path = write_parquet(group, ticker, dataset="insider_panel")
         upload_to_r2(parquet_path, ticker, dataset="insider_panel")

    print(f"Saved {signals_df['join_ticker'].nunique()} tickers to signals/, "
    f"{insider_panel_df['join_ticker'].nunique()} tickers to insider_panel/")
  

    