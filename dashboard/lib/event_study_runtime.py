"""Runs the event study against live R2 data.

Mirrors backtest_runtime.py's approach: pulls data through lib/r2_client.py
(Streamlit secrets) and calls the pure functions in event_study.py directly,
rather than event_study.py's own R2-loading functions (which expect a local
.env file).

Requires event_study.py (and its dependencies: config.py, storage.py,
price_utils.py, sp500_ciks.py) to already be in lib/.
"""
from __future__ import annotations

import sys
from pathlib import Path

# See backtest_runtime.py for why this is needed: event_study.py imports
# its siblings (config, storage, price_utils) as bare top-level imports.
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import streamlit as st

from lib import r2_client
from lib.event_study import (
    get_purchase_events,
    build_event_returns,
    get_baseline_returns,
    run_significance_test,
)

BENCHMARK_TICKER = "SPY"
HORIZONS = [1, 5, 20, 60, 90]


@st.cache_data(ttl=3600, show_spinner="Loading events + prices from R2...")
def _load_events_and_prices() -> tuple[pd.DataFrame, pd.DataFrame]:
    tickers = tuple(r2_client.list_available_tickers("events"))
    if not tickers:
        return pd.DataFrame(), pd.DataFrame()

    price_tickers = tuple(sorted(set(tickers) | {BENCHMARK_TICKER}))

    events_df = r2_client.load_dataset("events", tickers)
    prices_df = r2_client.load_dataset("prices", price_tickers)

    if not events_df.empty and "join_ticker" not in events_df.columns:
        events_df["join_ticker"] = events_df["issuer_ticker"].astype(str).str.upper().str.strip()

    if not prices_df.empty and "join_ticker" not in prices_df.columns and "ticker" in prices_df.columns:
        prices_df = prices_df.rename(columns={"ticker": "join_ticker"})

    return events_df, prices_df


@st.cache_data(ttl=3600, show_spinner="Running event study (forward returns + significance tests)...")
def run_event_study() -> dict:
    """Returns a dict with event_returns_df, comparison_df, significance_df,
    n_events, n_tickers. Empty dict if no data is available."""
    events_df, prices_df = _load_events_and_prices()
    if events_df.empty or prices_df.empty:
        return {}

    purchase_events = get_purchase_events(events_df)
    if purchase_events.empty:
        return {}

    event_returns_df = build_event_returns(purchase_events, prices_df, horizons=HORIZONS)

    # SPY-adjusted baseline (abnormal return vs. buying the market instead)
    spy_baseline_df = get_baseline_returns(prices_df, purchase_events, horizons=HORIZONS, method="spy")
    for h in HORIZONS:
        event_returns_df[f"baseline_return_{h}d"] = spy_baseline_df[f"baseline_return_{h}d"].reindex(event_returns_df.index)
        event_returns_df[f"abnormal_return_{h}d"] = event_returns_df[f"fwd_return_{h}d"] - event_returns_df[f"baseline_return_{h}d"]

    # Random-trading-day baseline (abnormal return vs. buying the same stock on a random day)
    random_baseline_df = get_baseline_returns(prices_df, purchase_events, horizons=HORIZONS, method="random_days")
    for h in HORIZONS:
        event_returns_df[f"random_baseline_return_{h}d"] = random_baseline_df[f"baseline_return_{h}d"].reindex(event_returns_df.index)
        event_returns_df[f"random_abnormal_return_{h}d"] = event_returns_df[f"fwd_return_{h}d"] - event_returns_df[f"random_baseline_return_{h}d"]

    # Comparison table: raw vs SPY-adjusted vs random-adjusted, per horizon
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

    # Significance testing per horizon, both baseline methods
    significance_rows = []
    for h in HORIZONS:
        spy_result = run_significance_test(event_returns_df, return_col=f"abnormal_return_{h}d")
        spy_result["horizon_days"] = h
        spy_result["method"] = "SPY-adjusted"
        significance_rows.append(spy_result)

        random_result = run_significance_test(event_returns_df, return_col=f"random_abnormal_return_{h}d")
        random_result["horizon_days"] = h
        random_result["method"] = "Random-days-adjusted"
        significance_rows.append(random_result)

    significance_df = pd.DataFrame(significance_rows).rename(columns={"p_value": "t_test_p_value"})

    return {
        "event_returns_df": event_returns_df,
        "comparison_df": comparison_df,
        "significance_df": significance_df,
        "n_events": len(purchase_events),
        "n_tickers": purchase_events["join_ticker"].nunique(),
    }