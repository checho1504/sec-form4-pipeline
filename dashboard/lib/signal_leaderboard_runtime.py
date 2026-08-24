"""Loads and ranks current insider purchase signals from R2.

Reuses the same get_clean_purchase_signals() used by the backtest and event
study pages, so "what counts as a signal" stays consistent across the whole
dashboard. Only needs the `events` dataset — no price data required.
"""
from __future__ import annotations

import sys
from pathlib import Path

# See backtest_runtime.py for why this is needed: backtest.py imports its
# siblings (event_study, storage) as bare top-level imports.
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import streamlit as st

from lib import r2_client
from lib.backtest import get_clean_purchase_signals

CLUSTER_THRESHOLD = 3


@st.cache_data(ttl=3600, show_spinner="Loading signals from R2...")
def load_signal_leaderboard() -> pd.DataFrame:
    """Returns one row per ticker/filing-date clean purchase signal,
    ranked by nothing yet — sorting happens on the page."""
    tickers = tuple(r2_client.list_available_tickers("events"))
    if not tickers:
        return pd.DataFrame()

    events_df = r2_client.load_dataset("events", tickers)
    if events_df.empty:
        return pd.DataFrame()

    return get_clean_purchase_signals(events_df, cluster_threshold=CLUSTER_THRESHOLD)
