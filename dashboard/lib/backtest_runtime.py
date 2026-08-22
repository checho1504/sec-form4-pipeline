"""Runs the existing trade-level + portfolio backtest against live R2 data.

This deliberately does NOT call backtest.run_backtest() or
portfolio.run_portfolio_backtest() directly, since those reach into R2
themselves via event_study.load_prices_from_r2 (which expects a local
.env). Instead it pulls data through lib/r2_client.py (Streamlit secrets)
and feeds it into the same pure functions those orchestrators call.

Requires backtest.py, portfolio.py, event_study.py, storage.py, config.py,
price_utils.py, and sp500_ciks.py to be copied unmodified into lib/.
"""
from __future__ import annotations

import sys
from pathlib import Path

# The pipeline files above import each other as bare siblings
# (e.g. `from event_study import ...`, `from config import ...`), which is
# how they're laid out in the main pipeline repo. Inside dashboard/lib/
# they're one directory deeper, so Python can't resolve those bare imports
# unless lib/ itself is on the import path. Adding it here, once, fixes
# every one of those sibling imports without touching the copied files.
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import streamlit as st

from lib import r2_client
from lib.backtest import (
    get_clean_purchase_signals,
    build_insider_purchase_trades,
    add_benchmark_returns,
    summarize_trades,
)
from lib.portfolio import (
    simulate_portfolio,
    summarize_portfolio,
    STARTING_CAPITAL,
    POSITION_SIZE,
    MAX_OPEN_POSITIONS,
    TRANSACTION_COST_RATE,
    MIN_SIGNAL_PURCHASE_VALUE,
)

BENCHMARK_TICKER = "SPY"


@st.cache_data(ttl=3600, show_spinner="Loading events + prices from R2...")
def _load_events_and_prices() -> tuple[pd.DataFrame, pd.DataFrame]:
    tickers = tuple(r2_client.list_available_tickers("events"))
    if not tickers:
        return pd.DataFrame(), pd.DataFrame()

    price_tickers = tuple(sorted(set(tickers) | {BENCHMARK_TICKER}))

    events_df = r2_client.load_dataset("events", tickers)
    prices_df = r2_client.load_dataset("prices", price_tickers)

    return events_df, prices_df


@st.cache_data(ttl=3600, show_spinner="Running trade-level backtest...")
def run_trade_level_backtest() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (trades_df, trade_summary_df)."""
    events_df, prices_df = _load_events_and_prices()
    if events_df.empty or prices_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    signals_df = get_clean_purchase_signals(events_df)
    trades_df = build_insider_purchase_trades(signals_df=signals_df, prices_df=prices_df)
    trades_df = add_benchmark_returns(trades_df=trades_df, prices_df=prices_df, benchmark_ticker=BENCHMARK_TICKER)
    summary_df = summarize_trades(trades_df)

    return trades_df, summary_df


@st.cache_data(ttl=3600, show_spinner="Running portfolio simulation...")
def run_portfolio_simulation() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (daily_equity_df, closed_trades_df, skipped_trades_df, portfolio_summary_df)."""
    trades_df, _ = run_trade_level_backtest()
    _, prices_df = _load_events_and_prices()

    if trades_df.empty or prices_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    daily_equity_df, closed_trades_df, skipped_trades_df = simulate_portfolio(
        trades_df=trades_df,
        prices_df=prices_df,
        starting_capital=STARTING_CAPITAL,
        position_size=POSITION_SIZE,
        max_open_positions=MAX_OPEN_POSITIONS,
        transaction_cost_rate=TRANSACTION_COST_RATE,
        min_signal_purchase_value=MIN_SIGNAL_PURCHASE_VALUE,
        benchmark_ticker=BENCHMARK_TICKER,
    )

    portfolio_summary_df = summarize_portfolio(
        daily_equity_df=daily_equity_df,
        closed_trades_df=closed_trades_df,
        skipped_trades_df=skipped_trades_df,
        starting_capital=STARTING_CAPITAL,
    )

    return daily_equity_df, closed_trades_df, skipped_trades_df, portfolio_summary_df