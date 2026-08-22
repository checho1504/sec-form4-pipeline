import streamlit as st

st.set_page_config(page_title="Follow the Money", page_icon="💰", layout="wide")

st.title("💰 Follow the Money")
st.subheader("Tracking SEC Form 4 insider purchases and testing whether they predict returns")

st.markdown(
    """
Corporate insiders — CEOs, CFOs, board members, major shareholders — have to file a **Form 4**
whenever they buy or sell shares of their own company. That data is public, timely, and
potentially useful as a research signal.

This dashboard is the front end for an end-to-end pipeline:

**SEC EDGAR → parse Form 4 filings → clean & guard against bad data → overlay market prices →
event study → signal engineering → backtest → (you are here)**

### Pages

- **📈 Backtest Results** — did the strategy actually make money? Portfolio equity curve vs. SPY,
  trade-level stats, drawdown.
- More pages coming: Signal Leaderboard, Company View, Live Feed.

---
*Data refreshes hourly from Cloudflare R2. Built by [checho1504](https://github.com/checho1504) —
[GitHub repo](https://github.com/checho1504/sec-form4-pipeline).*
"""
)