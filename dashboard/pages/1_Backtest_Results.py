import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.backtest_runtime import run_trade_level_backtest, run_portfolio_simulation

st.set_page_config(page_title="Backtest Results", page_icon="📈", layout="wide")
# Note: filename intentionally has no emoji (Windows zip extraction can
# mangle emoji in filenames). The 📈 icon above still sets the browser
# tab icon and appears next to the page title here on the page itself.
st.title("📈 Backtest Results")
st.caption("Strategy: buy after a clean open-market insider purchase filing, capital-constrained portfolio simulation vs. SPY buy-and-hold.")

with st.spinner("Loading backtest data..."):
    trades_df, trade_summary_df = run_trade_level_backtest()
    daily_equity_df, closed_trades_df, skipped_trades_df, portfolio_summary_df = run_portfolio_simulation()

if daily_equity_df.empty:
    st.error(
        "No backtest data available. Check that R2 secrets are set correctly and that "
        "the `events` and `prices` datasets exist in your bucket."
    )
    st.stop()

# --- Top-line metrics -------------------------------------------------------
summary = portfolio_summary_df.iloc[0]

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Return", f"{summary['total_return']:.1%}")
col2.metric("CAGR", f"{summary['cagr']:.1%}")
col3.metric("Sharpe", f"{summary['sharpe']:.2f}")
col4.metric("Max Drawdown", f"{summary['max_drawdown']:.1%}")
if "excess_return_vs_benchmark" in summary:
    col5.metric("vs. SPY", f"{summary['excess_return_vs_benchmark']:+.1%}")

col6, col7, col8 = st.columns(3)
col6.metric("Closed Trades", int(summary["closed_trades"]))
col7.metric("Trade Win Rate", f"{summary['trade_win_rate']:.1%}")
col8.metric("Skipped Trades", int(summary["skipped_trades"]))

st.divider()

# --- Equity curve -------------------------------------------------------
st.subheader("Equity Curve: Strategy vs. SPY")

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=daily_equity_df["date"], y=daily_equity_df["equity"],
    name="Insider portfolio", line=dict(width=2),
))
if "benchmark_equity" in daily_equity_df.columns and daily_equity_df["benchmark_equity"].notna().any():
    fig.add_trace(go.Scatter(
        x=daily_equity_df["date"], y=daily_equity_df["benchmark_equity"],
        name="SPY buy-and-hold", line=dict(width=2, dash="dot"),
    ))
fig.update_layout(
    height=450, hovermode="x unified",
    xaxis_title="Date", yaxis_title="Portfolio Value ($)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=0, r=0, t=10, b=0),
)
st.plotly_chart(fig, use_container_width=True)

# --- Drawdown -------------------------------------------------------
st.subheader("Drawdown")

fig_dd = go.Figure()
fig_dd.add_trace(go.Scatter(
    x=daily_equity_df["date"], y=daily_equity_df["drawdown"],
    fill="tozeroy", line=dict(width=1, color="crimson"), name="Drawdown",
))
fig_dd.update_layout(
    height=250, xaxis_title="Date", yaxis_title="Drawdown", yaxis_tickformat=".0%",
    margin=dict(l=0, r=0, t=10, b=0),
)
st.plotly_chart(fig_dd, use_container_width=True)

st.divider()

# --- Trade tables -------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    st.subheader("Closed Trades")
    if closed_trades_df.empty:
        st.info("No closed trades.")
    else:
        display_cols = [c for c in [
            "ticker", "entry_date", "exit_date", "entry_price", "exit_price",
            "pnl", "net_trade_return", "signal_purchase_value",
        ] if c in closed_trades_df.columns]
        st.dataframe(
            closed_trades_df[display_cols].sort_values("exit_date", ascending=False),
            use_container_width=True, hide_index=True,
        )

with right:
    st.subheader("Skipped Trade Reasons")
    if skipped_trades_df.empty:
        st.info("No skipped trades.")
    else:
        reason_counts = skipped_trades_df["reason"].value_counts().reset_index()
        reason_counts.columns = ["reason", "count"]
        st.dataframe(reason_counts, use_container_width=True, hide_index=True)
        st.caption(
            "Trades skipped because a ticker was already held or the portfolio hit "
            "its max open-position limit — a known driver of the gap vs. SPY."
        )

st.divider()

st.subheader("Trade-Level Summary (pre-portfolio-constraints)")
st.caption("Every qualifying signal taken in isolation, before capital/position limits are applied.")
if not trade_summary_df.empty:
    st.dataframe(trade_summary_df, use_container_width=True, hide_index=True)
