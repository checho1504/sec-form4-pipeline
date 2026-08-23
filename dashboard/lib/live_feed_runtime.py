"""Loads raw Form 4 transactions from R2 for the Live Feed page.

Unlike backtest_runtime.py / event_study_runtime.py, this page doesn't call
into any pipeline analysis functions (backtest.py, event_study.py) — it just
loads and lightly cleans the raw `form4` dataset for display. No sys.path
trick needed here since nothing imports the pipeline's sibling-import files.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import r2_client

ROLE_FLAG_COLUMNS = ["is_officer", "is_director", "is_ten_percent_owner", "is_other"]


def _to_bool(series: pd.Series) -> pd.Series:
    """Coerce a column that may already be bool, or may be 0/1 or
    'true'/'false' strings (depending on how it was parsed), into a
    proper boolean series."""
    return series.astype(str).str.strip().str.lower().isin(["true", "1", "yes", "y"])


def _derive_role(row: pd.Series) -> str:
    """Simple role label from the is_officer/is_director/... flags,
    roughly matching the CEO/CFO > Officer > Director > 10% Owner > Other
    priority described in the project roadmap's role_flag feature."""
    title = str(row.get("officer_title") or "").lower()

    if row["is_officer"]:
        if "chief executive" in title:
            return "CEO"
        if "chief financial" in title:
            return "CFO"
        return "Officer"
    if row["is_director"]:
        return "Director"
    if row["is_ten_percent_owner"]:
        return "10% Owner"
    if row["is_other"]:
        return "Other"
    return "Unknown"


@st.cache_data(ttl=3600, show_spinner="Loading transactions from R2...")
def load_live_feed() -> pd.DataFrame:
    """Loads and lightly cleans the raw form4 dataset across all tickers,
    sorted most-recent-filing-first."""
    tickers = tuple(r2_client.list_available_tickers("form4"))
    if not tickers:
        return pd.DataFrame()

    df = r2_client.load_dataset("form4", tickers)
    if df.empty:
        return df

    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    df["transaction_value"] = pd.to_numeric(df["transaction_value"], errors="coerce")
    df["transaction_shares"] = pd.to_numeric(df["transaction_shares"], errors="coerce").round().astype("Int64")
    df["transaction_price_per_share"] = pd.to_numeric(df["transaction_price_per_share"], errors="coerce")
    df["transaction_code"] = df["transaction_code"].fillna("").astype(str).str.upper().str.strip()
    df["issuer_ticker"] = df["issuer_ticker"].astype(str).str.upper().str.strip()

    for col in ROLE_FLAG_COLUMNS:
        df[col] = _to_bool(df[col]) if col in df.columns else False

    df["role"] = df.apply(_derive_role, axis=1)

    # Remove only exact duplicate transaction rows.
    # Do not collapse separate lots from the same insider/filing.
    dedupe_cols = [
        "accession_number",
        "issuer_ticker",
        "reporting_owner_name",
        "transaction_code",
        "transaction_date",
        "transaction_shares",
        "transaction_price_per_share",
        "transaction_value",
    ]
    df = df.drop_duplicates(
        subset=[col for col in dedupe_cols if col in df.columns],
        keep="first",
    )

    df = (
        df.dropna(subset=["filing_date"])
        .sort_values("filing_date", ascending=False)
        .reset_index(drop=True)
    )

    return df