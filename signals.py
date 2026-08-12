"""this module aims at converting raw form 4 into research features that could be later used for back testing and dashboards"""

import numpy as np
import pandas as pd
from storage import upload_to_r2, write_parquet 
from event_study import load_events_from_r2, load_prices_from_r2

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


#________________________________________________________________________________________________________________________________#

if __name__ == "__main__":
    events_df = load_events_from_r2()
    if events_df.empty:
        print("No events loaded")
        raise SystemExit

    signals_df = add_lag(events_df)
    signals_df = add_role_flag(signals_df)
    signals_df = add_open_market_flags(signals_df)

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

 