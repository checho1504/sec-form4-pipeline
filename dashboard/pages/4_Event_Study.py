import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.event_study_runtime import run_event_study, HORIZONS

st.set_page_config(page_title="Event Study", page_icon="🔬", layout="wide")
st.title("🔬 Event Study")
st.caption(
    "Does an insider's open-market purchase predict what happens next? Event date = filing date "
    "(not transaction date), so this only uses information that was actually public at the time."
)

with st.spinner("Running event study..."):
    results = run_event_study()

if not results:
    st.error(
        "No event study data available. Check that R2 secrets are set correctly and that "
        "the `events` and `prices` datasets exist in your bucket."
    )
    st.stop()

comparison_df = results["comparison_df"]
significance_df = results["significance_df"]

st.metric("Purchase Events Analyzed", f"{results['n_events']:,}", help=f"Across {results['n_tickers']} tickers")

st.divider()

# --- Headline finding, computed live from the significance results ---------
spy_sig = significance_df[significance_df["method"] == "SPY-adjusted"].sort_values("horizon_days")
significant_horizons = spy_sig.loc[spy_sig["bootstrap_significant"], "horizon_days"].tolist()

if significant_horizons:
    lo, hi = min(significant_horizons), max(significant_horizons)
    span = f"the {lo}-day horizon" if lo == hi else f"{lo}-{hi} trading days"
    st.success(
        f"**Finding:** insider purchases show a statistically significant abnormal return "
        f"(vs. SPY, 95% bootstrap CI excludes zero) at {span}."
    )
else:
    st.info("**Finding:** no horizon showed a statistically significant abnormal return vs. SPY in this sample.")

# --- Main chart: SPY-adjusted abnormal return per horizon, with 95% CI -----
st.subheader("Abnormal Return vs. SPY, by Holding Period")

fig = go.Figure()
fig.add_trace(go.Bar(
    x=[f"{h}d" for h in spy_sig["horizon_days"]],
    y=spy_sig["mean_return_pct"],
    error_y=dict(
        type="data",
        symmetric=False,
        array=spy_sig["bootstrap_ci_high_pct"] - spy_sig["mean_return_pct"],
        arrayminus=spy_sig["mean_return_pct"] - spy_sig["bootstrap_ci_low_pct"],
    ),
    marker_color=["#2ca02c" if sig else "#7f7f7f" for sig in spy_sig["bootstrap_significant"]],
    name="Mean abnormal return",
))
fig.add_hline(y=0, line_dash="dot", line_color="gray")
fig.update_layout(
    height=380, xaxis_title="Holding period", yaxis_title="Mean abnormal return (%)",
    showlegend=False, margin=dict(l=0, r=0, t=10, b=0),
)
st.plotly_chart(fig, use_container_width=True)
st.caption("Green bars = statistically significant (95% bootstrap CI excludes zero). Error bars = 95% CI from a block bootstrap by ticker.")

st.divider()

# --- Raw vs. SPY-adjusted vs. random-days-adjusted, per horizon ------------
st.subheader("Raw vs. Benchmark-Adjusted Returns")

display_comparison = comparison_df.rename(columns={
    "horizon_days": "Horizon (days)",
    "raw_mean_pct": "Raw mean return (%)",
    "raw_win_rate_pct": "Raw win rate (%)",
    "spy_abnormal_mean_pct": "SPY-adjusted mean (%)",
    "spy_win_rate_pct": "SPY-adjusted win rate (%)",
    "random_abnormal_mean_pct": "Random-day-adjusted mean (%)",
    "random_win_rate_pct": "Random-day-adjusted win rate (%)",
}).round(2)
st.dataframe(display_comparison, use_container_width=True, hide_index=True)
st.caption(
    "Raw = the stock's own forward return. SPY-adjusted = raw minus what SPY did over the same window. "
    "Random-day-adjusted = raw minus the same stock's average return starting on 100 random days, "
    "a control for the stock's own typical volatility rather than the market's."
)

st.divider()

# --- Full significance test results -----------------------------------
st.subheader("Statistical Significance Tests")
display_significance = significance_df[[
    "method", "horizon_days", "n_events", "n_tickers", "mean_return_pct",
    "t_test_p_value", "bootstrap_ci_low_pct", "bootstrap_ci_high_pct", "bootstrap_significant",
]].rename(columns={
    "method": "Baseline",
    "horizon_days": "Horizon (days)",
    "n_events": "N events",
    "n_tickers": "N tickers",
    "mean_return_pct": "Mean abnormal return (%)",
    "t_test_p_value": "t-test p-value",
    "bootstrap_ci_low_pct": "95% CI low (%)",
    "bootstrap_ci_high_pct": "95% CI high (%)",
    "bootstrap_significant": "Significant?",
}).sort_values(["Baseline", "Horizon (days)"]).round(3)
st.dataframe(display_significance, use_container_width=True, hide_index=True)
st.caption(
    "Significance tested two ways: a one-sample t-test, and a block bootstrap resampled by ticker "
    "(5,000 draws) so a single ticker's events don't get treated as independent evidence."
)
