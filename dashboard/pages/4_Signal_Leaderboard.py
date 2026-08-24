import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.signal_leaderboard_runtime import load_signal_leaderboard

st.set_page_config(page_title="Signal Leaderboard", page_icon="🏆", layout="wide")
st.title("🏆 Signal Leaderboard")
st.caption(
    "Clean open-market insider purchase signals, ranked by dollar size. "
    "One row per ticker/filing date."
)

with st.spinner("Loading signals..."):
    signals_df = load_signal_leaderboard()

if signals_df.empty:
    st.error(
        "No signal data available. Check that R2 secrets are set correctly and that "
        "the `events` dataset exists in your bucket."
    )
    st.stop()

most_recent_date = signals_df["filing_date"].max()

# --- Filters -------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

with col1:
    ticker_options = sorted(signals_df["join_ticker"].dropna().unique())
    selected_tickers = st.multiselect("Ticker", ticker_options)

with col2:
    min_value = st.number_input(
        "Min signal value ($)",
        min_value=0,
        value=0,
        step=100_000,
    )

with col3:
    cluster_only = st.checkbox("Cluster buying only (3+ insiders)")

with col4:
    data_min_date = signals_df["filing_date"].min()
    max_days_back = max((most_recent_date - data_min_date).days, 1)
    days_back = st.slider(
        "Days back",
        min_value=1,
        max_value=max_days_back,
        value=min(90, max_days_back),
    )

filtered = signals_df.copy()

if selected_tickers:
    filtered = filtered[filtered["join_ticker"].isin(selected_tickers)]

if min_value > 0:
    filtered = filtered[filtered["signal_purchase_value"] >= min_value]

if cluster_only:
    filtered = filtered[filtered["cluster_buying_at_signal"]]

cutoff = most_recent_date - pd.Timedelta(days=days_back)

filtered = (
    filtered[filtered["filing_date"] >= cutoff]
    .sort_values("signal_purchase_value", ascending=False)
)

st.caption(
    f"Showing {len(filtered):,} of {len(signals_df):,} total signals "
    f"(most recent filing date in data: {most_recent_date.date()})."
)

st.divider()

# --- Top-line metrics -------------------------------------------------------
m1, m2, m3, m4 = st.columns(4)

m1.metric("Signals", f"{len(filtered):,}")
m2.metric("Total $ Value", f"${filtered['signal_purchase_value'].sum():,.0f}")
m3.metric(
    "Avg Signal Size",
    f"${filtered['signal_purchase_value'].mean():,.0f}" if len(filtered) else "$0",
)
m4.metric("Cluster Signals", f"{int(filtered['cluster_buying_at_signal'].sum()):,}")

st.divider()

# --- Top 10 chart -------------------------------------------------------
st.subheader("Top 10 Signals by Dollar Value")

top10 = filtered.head(10).sort_values("signal_purchase_value")

if top10.empty:
    st.info("No signals match the current filters.")
else:
    labels = top10["join_ticker"] + " — " + top10["filing_date"].dt.strftime("%Y-%m-%d")

    fig = go.Figure(
        go.Bar(
            x=top10["signal_purchase_value"],
            y=labels,
            orientation="h",
            marker_color=[
                "#d62728" if c else "#1f77b4"
                for c in top10["cluster_buying_at_signal"]
            ],
            text=top10["signal_purchase_value"].apply(lambda x: f"${x:,.0f}"),
            textposition="auto",
        )
    )

    fig.update_layout(
        height=400,
        xaxis_title="Signal Value ($)",
        yaxis_title="",
        margin=dict(l=0, r=0, t=10, b=0),
    )

    fig.update_xaxes(tickprefix="$", separatethousands=True)

    st.plotly_chart(fig, use_container_width=True)
    st.caption("Red bars = cluster buying (3+ distinct insiders on the same filing date).")

st.divider()

# --- Full leaderboard table -------------------------------------------------------
st.subheader("Full Leaderboard")

display_cols = {
    "filing_date": "Filing Date",
    "join_ticker": "Ticker",
    "signal_purchase_value": "Signal Value ($)",
    "max_single_purchase_value": "Largest Single Buy ($)",
    "purchase_transaction_count": "# Transactions",
    "signal_insider_count": "# Insiders",
    "cluster_buying_at_signal": "Cluster?",
    "first_transaction_date": "First Transaction",
}

if "role_flag" in filtered.columns:
    display_cols["role_flag"] = "Role"

available_cols = [c for c in display_cols if c in filtered.columns]
table = filtered[available_cols].rename(columns=display_cols).copy()

# Format dates.
for col in ["Filing Date", "First Transaction"]:
    if col in table.columns:
        table[col] = pd.to_datetime(table[col], errors="coerce").dt.strftime("%Y-%m-%d")

# Format money columns with commas and 2 decimals.
for col in ["Signal Value ($)", "Largest Single Buy ($)"]:
    if col in table.columns:
        table[col] = table[col].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "")

# Format count columns with commas.
for col in ["# Transactions", "# Insiders"]:
    if col in table.columns:
        table[col] = table[col].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "")

st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Cluster?": st.column_config.CheckboxColumn(),
    },
)