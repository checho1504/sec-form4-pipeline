import numpy as np
import pandas as pd

MAX_PLAUSIBLE_PRICE_PER_SHARE = 50_000.0
MAX_PLAUSIBLE_SHARES = 1_000_000_000

def clean_dataframe(rows: list) -> pd.DataFrame:
    """Converts raw Form 4 rows into typed columns: parses dates, coerces numeric
    and boolean fields, and computes transaction_value as shares * price. Rows with
    an implausible price-per-share or share count are nulled out before the value
    calculation runs, so a single corrupted field can't silently blow up transaction_value."""

    required_columns = [
        "transaction_date", "period_of_report", "filing_date",
        "transaction_shares", "transaction_price_per_share", "shares_owned_following_transaction",
        "is_director", "is_officer", "is_ten_percent_owner",
        "is_other", "equity_swap_involved", "not_subject_to_section16",
    ]

    df = pd.DataFrame(rows)
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    df["period_of_report"] = pd.to_datetime(df["period_of_report"], errors="coerce")
    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")

    df["transaction_shares"] = pd.to_numeric(df["transaction_shares"], errors="coerce")
    df["transaction_price_per_share"] = pd.to_numeric(
        df["transaction_price_per_share"],
        errors="coerce"
    )
    df["shares_owned_following_transaction"] = pd.to_numeric(
        df["shares_owned_following_transaction"], errors="coerce"
    )

    implausible_price = df["transaction_price_per_share"] > MAX_PLAUSIBLE_PRICE_PER_SHARE
    implausible_shares = df["transaction_shares"].abs() > MAX_PLAUSIBLE_SHARES
    df["implausible_transaction_fields"] = implausible_price | implausible_shares

    if df["implausible_transaction_fields"].any():
        n_bad = int(df["implausible_transaction_fields"].sum())
        print(f"Warning: {n_bad} rows have implausible price/share values and were nulled out before computing transaction_value")

    df.loc[implausible_price, "transaction_price_per_share"] = np.nan
    df.loc[implausible_shares, "transaction_shares"] = np.nan

    bool_columns = [
        "is_director", "is_officer", "is_ten_percent_owner",
        "is_other", "equity_swap_involved", "not_subject_to_section16",
    ]

    bool_map = {"1": True, "0": False, 1: True, 0: False, True: True, False: False}
    for col in bool_columns:
        df[col] = df[col].map(bool_map)

    df["transaction_value"] = (
        df["transaction_shares"] * df["transaction_price_per_share"]
    )

    return df