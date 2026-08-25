import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.company_view_runtime import get_ticker_options, load_company_data

st.set_page_config(page_title="Company View", page_icon="🏢", layout="wide")
st.title("🏢 Company View")
st.caption("Insider activity for a single company, overlaid on its price history.")

ticker_options = get_ticker_options()
if not ticker_options:
    st.error("No tickers available. Check that R2 secrets are set correctly and that the `form4` dataset exists.")
    st.stop()

default_index = ticker_options.index("AAPL") if "AAPL" in ticker_options else 0
ticker = st.selectbox("Ticker", ticker_options, index=default_index)

with st.spinner(f"Loading {ticker}..."):
    prices_df, transactions_df = load_company_data(ticker)

if prices_df.empty and transactions_df.empty:
    st.error(f"No data found for {ticker}.")
    st.stop()

if not transactions_df.empty:
    earliest_filing = transactions_df["filing_date"].min()
    earliest_price = prices_df["date"].min() if not prices_df.empty else None
    if earliest_price is not None and earliest_filing > earliest_price + pd.Timedelta(days=180):
        st.info(
            f"Price history for {ticker} goes back to {earliest_price.date()}, but Form 4 data "
            f"only starts {earliest_filing.date()}. The pipeline processes each ticker's 50 most "
            "recent filings per run, so high-volume filers may not have their full historical "
            "Form 4 record pulled in yet — this isn't necessarily a gap in real insider activity."
        )

show_all_codes = st.checkbox("Show all transaction types on chart (awards, gifts, etc.), not just buys/sells")

st.divider()

# --- Summary metrics -------------------------------------------------------
buys = transactions_df[transactions_df["transaction_code"] == "P"] if not transactions_df.empty else pd.DataFrame()
sells = transactions_df[transactions_df["transaction_code"] == "S"] if not transactions_df.empty else pd.DataFrame()
buy_value = buys["transaction_value"].sum() if not buys.empty else 0
sell_value = sells["transaction_value"].sum() if not sells.empty else 0
n_insiders = transactions_df["reporting_owner_name"].nunique() if not transactions_df.empty else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Buy Value", f"${buy_value:,.0f}")
m2.metric("Total Sell Value", f"${sell_value:,.0f}")
m3.metric("Net (Buy − Sell)", f"${buy_value - sell_value:,.0f}")
m4.metric("Distinct Insiders", n_insiders)

st.divider()

# --- Price chart with buy/sell markers -------------------------------------------------------
st.subheader(f"{ticker} Price with Insider Transactions")

fig = go.Figure()

if not prices_df.empty:
    fig.add_trace(go.Scatter(
        x=prices_df["date"], y=prices_df["adjClose"],
        name="Price", line=dict(width=1.5, color="#7f7f7f"),
    ))

if not transactions_df.empty:
    codes_to_plot = transactions_df["transaction_code"].unique() if show_all_codes else ["P", "S"]
    marker_style = {
        "P": dict(symbol="triangle-up", color="#2ca02c", size=11, name="Buy (P)"),
        "S": dict(symbol="triangle-down", color="#d62728", size=11, name="Sell (S)"),
    }
    default_style = dict(symbol="circle", color="#7f7f7f", size=6, name="Other")

    for code in codes_to_plot:
        subset = transactions_df[transactions_df["transaction_code"] == code]
        if subset.empty:
            continue
        style = marker_style.get(code, {**default_style, "name": f"Other ({code})"})
        fig.add_trace(go.Scatter(
            x=subset["transaction_date"], y=subset["transaction_price_per_share"],
            mode="markers", name=style["name"],
            marker=dict(symbol=style["symbol"], color=style["color"], size=style["size"], line=dict(width=1, color="white")),
            text=subset["reporting_owner_name"],
            hovertemplate="%{text}<br>%{x|%Y-%m-%d}<br>$%{y:.2f}<extra></extra>",
        ))

fig.update_layout(
    height=500, hovermode="closest",
    xaxis_title="Date", yaxis_title="Price ($)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=0, r=0, t=10, b=0),
)
st.plotly_chart(fig, use_container_width=True)
st.caption("Markers are plotted at the reported transaction price, which may differ slightly from that day's closing price.")

st.divider()

# --- Transaction table -------------------------------------------------------
st.subheader("Transaction History")

if transactions_df.empty:
    st.info(f"No Form 4 transactions found for {ticker}.")
else:
    display_cols = {
        "filing_date": "Filing Date",
        "transaction_date": "Transaction Date",
        "reporting_owner_name": "Insider",
        "role": "Role",
        "transaction_code": "Code",
        "transaction_shares": "Shares",
        "transaction_price_per_share": "Price/Share",
        "transaction_value": "Value ($)",
    }
    available_cols = [c for c in display_cols if c in transactions_df.columns]
    table = transactions_df[available_cols].rename(columns=display_cols)

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Filing Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "Transaction Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "Shares": st.column_config.NumberColumn(format="%,.0f"),
            "Price/Share": st.column_config.NumberColumn(format="$%.2f"),
            "Value ($)": st.column_config.NumberColumn(format="$%,.2f"),
        },
    )
