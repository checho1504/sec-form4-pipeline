import pandas as pd
import streamlit as st

from lib.live_feed_runtime import load_live_feed

st.set_page_config(page_title="Live Feed", page_icon="📰", layout="wide")
st.title("📰 Live Feed")
st.caption(
    "Recent SEC Form 4 insider transactions, filterable by ticker, role, "
    "transaction code, and value."
)

TRANSACTION_CODE_LABELS = {
    "P": "Open-market purchase",
    "S": "Open-market sale",
    "A": "Award / grant",
    "F": "Tax withholding",
    "G": "Gift",
    "M": "Option exercise",
}

with st.spinner("Loading transactions..."):
    feed_df = load_live_feed()

if feed_df.empty:
    st.error(
        "No transaction data available. Check that R2 secrets are set correctly and that "
        "the `form4` dataset exists in your bucket."
    )
    st.stop()

most_recent_date = feed_df["filing_date"].max()

# --- Filters -------------------------------------------------------------
col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 2])

with col1:
    ticker_options = sorted(feed_df["issuer_ticker"].dropna().unique())
    selected_tickers = st.multiselect("Ticker", ticker_options)

with col2:
    role_options = sorted(feed_df["role"].dropna().unique())
    selected_roles = st.multiselect("Role", role_options)

with col3:
    code_options = sorted(c for c in feed_df["transaction_code"].dropna().unique() if c)
    selected_codes = st.multiselect(
        "Transaction code",
        code_options,
        format_func=lambda c: f"{c} — {TRANSACTION_CODE_LABELS.get(c, 'Other')}",
    )

with col4:
    min_value = st.number_input(
        "Min transaction value ($)",
        min_value=0,
        value=0,
        step=10_000,
    )

with col5:
    data_min_date = feed_df["filing_date"].min()
    max_days_back = max((most_recent_date - data_min_date).days, 1)
    days_back = st.slider(
        "Days back",
        min_value=1,
        max_value=max_days_back,
        value=min(30, max_days_back),
    )

# --- Apply filters ---------------------------------------------------------
filtered = feed_df.copy()

if selected_tickers:
    filtered = filtered[filtered["issuer_ticker"].isin(selected_tickers)]

if selected_roles:
    filtered = filtered[filtered["role"].isin(selected_roles)]

if selected_codes:
    filtered = filtered[filtered["transaction_code"].isin(selected_codes)]

if min_value > 0:
    filtered = filtered[filtered["transaction_value"] >= min_value]

cutoff = most_recent_date - pd.Timedelta(days=days_back)
filtered = filtered[filtered["filing_date"] >= cutoff]

st.caption(
    f"Showing {len(filtered):,} of {len(feed_df):,} total filings "
    f"(most recent filing date in data: {most_recent_date.date()})."
)

st.divider()

# --- Table -------------------------------------------------------------
display_cols = {
    "filing_date": "Filing Date",
    "issuer_ticker": "Ticker",
    "reporting_owner_name": "Insider",
    "role": "Role",
    "transaction_code": "Code",
    "transaction_date": "Transaction Date",
    "transaction_shares": "Shares",
    "transaction_price_per_share": "Price/Share",
    "transaction_value": "Value ($)",
}

available_cols = [c for c in display_cols if c in filtered.columns]
table = filtered[available_cols].rename(columns=display_cols).copy()

# Format dates as clean YYYY-MM-DD strings.
for col in ["Filing Date", "Transaction Date"]:
    if col in table.columns:
        table[col] = pd.to_datetime(table[col], errors="coerce").dt.strftime("%Y-%m-%d")

# Format shares with commas and no decimals.
if "Shares" in table.columns:
    table["Shares"] = table["Shares"].apply(
        lambda x: f"{x:,.0f}" if pd.notna(x) else ""
    )

# Format price per share with dollar sign, commas, and 2 decimals.
if "Price/Share" in table.columns:
    table["Price/Share"] = table["Price/Share"].apply(
        lambda x: f"${x:,.2f}" if pd.notna(x) else ""
    )

# Format total transaction value with dollar sign, commas, and 2 decimals.
if "Value ($)" in table.columns:
    table["Value ($)"] = table["Value ($)"].apply(
        lambda x: f"${x:,.2f}" if pd.notna(x) else ""
    )

st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
)

with st.expander("Transaction code reference"):
    st.table(
        pd.DataFrame(
            [{"Code": k, "Meaning": v} for k, v in TRANSACTION_CODE_LABELS.items()]
        )
    )