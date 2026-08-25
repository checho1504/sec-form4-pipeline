"""Loads price history + Form 4 transactions for a single selected ticker.

Deliberately scoped to one ticker at a time — unlike Live Feed/Signal
Leaderboard, which load the full universe, this page only ever needs one
company's data, so it fetches just that ticker's two parquet files.

Reuses the role-deriving helpers from live_feed_runtime.py rather than
duplicating that logic.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import r2_client
from lib.live_feed_runtime import _to_bool, _derive_role, ROLE_FLAG_COLUMNS


@st.cache_data(ttl=3600, show_spinner=False)
def get_ticker_options() -> list[str]:
    return r2_client.list_available_tickers("form4")


@st.cache_data(ttl=3600, show_spinner="Loading company data...")
def load_company_data(ticker: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (prices_df, transactions_df) for a single ticker."""
    ticker = ticker.upper().strip()

    prices_df = r2_client.load_parquet(f"prices/ticker={ticker}/prices_{ticker.lower()}.parquet")
    transactions_df = r2_client.load_parquet(f"form4/ticker={ticker}/form4_{ticker.lower()}.parquet")

    if not prices_df.empty:
        prices_df["date"] = pd.to_datetime(prices_df["date"], errors="coerce")
        prices_df["adjClose"] = pd.to_numeric(prices_df["adjClose"], errors="coerce")
        prices_df = prices_df.dropna(subset=["date", "adjClose"]).sort_values("date")

    if not transactions_df.empty:
        transactions_df["filing_date"] = pd.to_datetime(transactions_df["filing_date"], errors="coerce")
        transactions_df["transaction_date"] = pd.to_datetime(transactions_df["transaction_date"], errors="coerce")
        transactions_df["transaction_shares"] = pd.to_numeric(transactions_df["transaction_shares"], errors="coerce").round().astype("Int64")
        transactions_df["transaction_price_per_share"] = pd.to_numeric(transactions_df["transaction_price_per_share"], errors="coerce")
        transactions_df["transaction_value"] = pd.to_numeric(transactions_df["transaction_value"], errors="coerce")
        transactions_df["transaction_code"] = transactions_df["transaction_code"].fillna("").astype(str).str.upper().str.strip()

        for col in ROLE_FLAG_COLUMNS:
            transactions_df[col] = _to_bool(transactions_df[col]) if col in transactions_df.columns else False
        transactions_df["role"] = transactions_df.apply(_derive_role, axis=1)

        transactions_df = (
            transactions_df.dropna(subset=["transaction_date"])
            .sort_values("transaction_date", ascending=False)
            .reset_index(drop=True)
        )

    return prices_df, transactions_df
