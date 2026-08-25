import streamlit as st

st.set_page_config(page_title="Follow the Money", page_icon="💰", layout="wide")

st.title("💰 Follow the Money")
st.subheader("Tracking SEC Form 4 insider purchases and testing whether they predict returns")

st.markdown(
    """
Corporate insiders such as  CEOs, CFOs, board members, major shareholders, etc. have to file a **Form 4**
whenever they buy or sell shares of their own company. That data is public, timely, and
potentially useful as a research signal.

This dashboard is the front end for an end-to-end pipeline:

**SEC EDGAR → parse Form 4 filings → clean & guard against bad data → overlay market prices →
event study → signal engineering → backtest → (you are here)**

### Pages

- **📰 Live Feed** — the raw stream of recent insider trades. Filter by ticker, role, buy/sell code, or dollar amount.
- **🏆 Signal Leaderboard** — who's buying the most right now, ranked by dollar size. Flags when 3+ insiders are buying the same stock at once (that's a cluster).
- **🏢 Company View** — pick one company and see its price chart with every insider buy/sell plotted right on top.
- **🔬 Event Study** — the actual research question: does insider buying predict the stock going up afterward? Tested with real stats (t-tests + bootstrap), not just vibes.
- **📈 Backtest Results** — if I'd actually traded on this signal with real money and real limits (starting cash, max positions, fees), would I have beaten just buying SPY?

---
*Data refreshes hourly from Cloudflare R2. Built by [checho1504](https://github.com/checho1504) —
[GitHub repo](https://github.com/checho1504/sec-form4-pipeline).*
"""
)