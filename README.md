# Follow the Money: Insider Buying Event Study

A Python data engineering and research project that pulls SEC Form 4 insider trading filings, filters for high-signal open-market purchases, joins them with adjusted stock prices, measures forward returns, compares them against baselines, and tests whether the results are statistically meaningful.

The main question:

> When insiders buy their own company's stock on the open market, does the stock tend to outperform afterward?

Current finding:

> In this dataset, open-market insider purchases show statistically significant short-term abnormal returns, especially around the 20-trading-day horizon. The signal does not appear reliable at 60 to 90 days.

---

## Features

- Downloads Form 4 filings directly from SEC EDGAR
- Parses messy Form 4 XML into structured transaction rows
- Filters for open-market insider purchases
- Stores cleaned Parquet datasets in Cloudflare R2
- Fetches adjusted daily stock prices
- Joins insider events to the next available trading day after filing date
- Computes 1, 5, 20, 60, and 90 trading-day forward returns
- Compares event returns against:
  - SPY benchmark returns
  - Random same-stock trading-day baselines
- Calculates abnormal returns
- Runs significance testing using:
  - one-sample t-test
  - ticker-level block bootstrap
- Outputs summary tables for raw, SPY-adjusted, and random-days-adjusted returns

---

## Why I Built This

I kept seeing headlines like:

> CEO buys $2M of their own stock.

Those headlines are usually treated like obvious good news, but I wanted to test that idea with data.

So I built this project to answer:

- Do stocks go up after insider purchases?
- Do they beat the market?
- Do they beat their own normal/random behavior?
- Is the pattern statistically significant or just noise?

This is a student research project, not investment advice.

---

## Current Dataset

Latest event-study run:

| Metric | Value |
|---|---:|
| Total Form 4 event rows | 44,820 |
| Unique tickers with Form 4 events | 498 |
| Clean open-market purchase events | 842 |
| Tickers with purchase events | 174 |
| Duplicate purchase rows | 0 |

The pipeline is now close to a broad S&P 500-scale universe, though some tickers may still be missing due to unavailable event files, ticker changes, aliases, or data quality issues.

---

## High-Signal Purchase Filter

The main signal currently used is:

```text
transaction_code == "P"
and transaction_acquired_disposed_code == "A"
and transaction_price_per_share > 0
```

This captures open-market purchases where insiders used their own money.

It removes grants, awards, gifts, zero-price transactions, and other non-cash events.

---

## How the Pipeline Works

1. **Fetch filings**

   Pull Form 4 filings from SEC EDGAR using company CIKs.

2. **Parse XML**

   Form 4 filings are XML documents. The parser extracts transaction fields like insider name, issuer, transaction date, filing date, shares, price, transaction code, and ownership details.

3. **Clean and validate**

   The pipeline converts dates and numeric columns, calculates transaction value, validates issuer CIK/ticker fields, and removes rows that do not match the expected issuer.

4. **Store in R2**

   Cleaned Form 4 data is stored as Parquet files in Cloudflare R2.

5. **Fetch market data**

   Daily adjusted OHLCV price data is pulled for each ticker.

6. **Join filings to prices**

   Each filing is matched to the next available trading day after the filing date.

   I use `filing_date`, not `transaction_date`, because the filing date is when the market can actually react to the information.

7. **Compute forward returns**

   For every open-market purchase event, the pipeline calculates returns after:

   - 1 trading day
   - 5 trading days
   - 20 trading days
   - 60 trading days
   - 90 trading days

8. **Compare against baselines**

   Raw returns are not enough because the whole market may have gone up.

   So the event returns are compared against:

   - **SPY baseline:** did the stock beat the broad market?
   - **Random-days baseline:** did the stock beat its own average random-period behavior?

9. **Run significance tests**

   The project tests whether abnormal returns are statistically different from zero using:

   - a one-sample t-test
   - a ticker-level block bootstrap

---

## Event Study Results

### Raw Purchase Returns

| Horizon | Valid Events | Mean Return | Median Return | Win Rate |
|---:|---:|---:|---:|---:|
| 1 day | 836 | +0.87% | +0.87% | 69.62% |
| 5 days | 823 | +1.00% | +0.75% | 56.38% |
| 20 days | 802 | +3.23% | +3.42% | 67.83% |
| 60 days | 609 | +5.32% | +3.36% | 56.81% |
| 90 days | 535 | +6.96% | +3.59% | 59.44% |

Raw returns answer:

> Did the stock go up after the insider purchase?

But raw returns can be misleading because they do not adjust for market conditions.

---

## Baseline-Adjusted Results

### SPY-Adjusted Abnormal Returns

| Horizon | Mean Abnormal Return | Median Abnormal Return | Win Rate vs SPY |
|---:|---:|---:|---:|
| 1 day | +0.87% | +0.79% | 68.14% |
| 5 days | +0.88% | +0.65% | 56.69% |
| 20 days | +2.39% | +2.59% | 61.67% |
| 60 days | -0.56% | -1.68% | 44.13% |
| 90 days | -0.67% | -5.52% | 39.44% |

SPY-adjusted abnormal return means:

```text
stock forward return - SPY forward return
```

This answers:

> Did the stock outperform the broad market after the insider purchase?

---

### Random-Days-Adjusted Abnormal Returns

| Horizon | Mean Abnormal Return | Median Abnormal Return | Win Rate vs Random Days |
|---:|---:|---:|---:|
| 1 day | +0.81% | +0.83% | 67.46% |
| 5 days | +0.76% | +0.43% | 53.95% |
| 20 days | +2.29% | N/A | 65.59% |
| 60 days | +2.98% | +0.88% | 51.89% |
| 90 days | +3.37% | +0.75% | 51.40% |

Random-days abnormal return means:

```text
stock return after insider purchase - average return from random same-stock periods
```

This answers:

> Did the stock perform better after insider purchases than it usually does during random periods in its own history?

---

## Significance Testing

The ticker-level block bootstrap is important because some tickers appear much more often than others.

A normal row-level bootstrap could overweight companies with many events. The block bootstrap resamples by ticker, which asks:

> Does the signal still hold across companies, or is it being carried by a few heavily represented tickers?

### Bootstrap Results

| Horizon | SPY-Adjusted Significant? | Random-Days Significant? | Interpretation |
|---:|---:|---:|---|
| 1 day | Yes | Yes | Strong short-term reaction |
| 5 days | Yes | Yes | Positive but weaker |
| 20 days | Yes | Yes | Strongest result |
| 60 days | No | No | Not statistically reliable |
| 90 days | No | No | Not statistically reliable |

### Confidence Intervals

| Method | Horizon | Events | Bootstrap 95% CI | Significant? |
|---|---:|---:|---:|---|
| SPY-adjusted | 1d | 835 | +0.580% to +1.227% | Yes |
| Random-days-adjusted | 1d | 836 | +0.506% to +1.183% | Yes |
| SPY-adjusted | 5d | 822 | +0.224% to +1.587% | Yes |
| Random-days-adjusted | 5d | 823 | +0.074% to +1.543% | Yes |
| SPY-adjusted | 20d | 801 | +1.049% to +3.717% | Yes |
| Random-days-adjusted | 20d | 802 | +0.596% to +4.171% | Yes |
| SPY-adjusted | 60d | 605 | -3.678% to +3.480% | No |
| Random-days-adjusted | 60d | 609 | -1.243% to +7.977% | No |
| SPY-adjusted | 90d | 535 | -4.882% to +5.004% | No |
| Random-days-adjusted | 90d | 535 | -1.263% to +9.561% | No |

The clearest finding so far:

> Open-market insider purchases are followed by statistically significant short-term abnormal returns, with the strongest evidence around the 20-trading-day horizon.

The longer 60-day and 90-day windows do not hold up after uncertainty testing.

---

## Side-by-Side Comparison

| Horizon | Raw Mean | Raw Win Rate | SPY Win Rate | Random-Days Mean | Random-Days Win Rate |
|---:|---:|---:|---:|---:|---:|
| 1 day | +0.87% | 69.62% | 68.14% | +0.81% | 67.46% |
| 5 days | +1.00% | 56.38% | 56.69% | +0.76% | 53.95% |
| 20 days | +3.23% | 67.83% | 61.67% | +2.29% | 65.59% |
| 60 days | +5.32% | 56.81% | 44.13% | +2.98% | 51.89% |
| 90 days | +6.96% | 59.44% | 39.44% | +3.37% | 51.40% |

---

## Main Takeaway

The raw numbers look strong at longer horizons, but the adjusted results tell a more careful story.

The 1-day, 5-day, and especially 20-day horizons show statistically significant abnormal returns.

The 60-day and 90-day horizons look positive in raw returns, but they do not appear statistically reliable after adjusting for baselines and using ticker-level block bootstrap confidence intervals.

In plain English:

> Insider buying appears to have a real short-term signal in this dataset, but it does not look like a simple long-term buy-and-hold signal.

---

## Limitations

- This is not investment advice.
- This is a research project, not a trading strategy.
- The dataset may still have missing tickers or incomplete coverage.
- Some companies appear more often than others.
- Some results may change as more historical filings are added.
- The current study uses event rows, not fully aggregated signal-level events.
- No beta-adjusted or factor-model abnormal return has been added yet.
- Longer horizons have fewer valid observations because newer events do not have enough future price history.

---

## What's Next

Phase 3 answered the first research question:

> Are open-market insider purchases followed by statistically significant abnormal returns?

The next step is to turn the event-study results into stronger research signals and eventually test whether those signals could support a simple strategy.

---

## Phase 4 — Signal Engineering

Phase 4 turns raw insider transactions into more useful research features.

Planned features:

| Feature | Description |
|---|---|
| `net_insider_buying` | Buy value minus sell value over a rolling window |
| `cluster_buying` | Multiple insiders buying the same stock in the same week |
| `role_flag` | CEO / CFO / Director / 10% owner |
| `open_market_only` | Filter to open-market purchases/sales |
| `transaction_value` | Shares × price per share |
| `transaction_value_vs_market_cap` | Trade size relative to company size |
| `insider_count` | Distinct insiders buying in a rolling window |
| `buy_sell_imbalance` | Buy value ÷ total buy/sell value |
| `distance_from_52w_high` | Distance below 52-week high at filing |
| `prior_30d_return` | Stock momentum before filing |
| `prior_volatility` | Risk environment before filing |
| `filing_lag` | Gap between transaction date and filing date |

Questions Phase 4 should answer:

- Are large purchases more predictive than small purchases?
- Are CEO/CFO purchases stronger than director purchases?
- Does cluster buying matter?
- Does the signal work better after a stock has fallen?
- Does buying near 52-week lows behave differently than buying near highs?

---

## Phase 5 — Backtesting Engine

Phase 5 asks:

> If I traded based on these signals using only information available at the time, would the strategy have worked?

Strategies to test:

- Buy after cluster open-market insider purchases
- Buy after large open-market insider purchases
- Buy when multiple officers/directors buy in the same rolling window
- Hold for 20 / 60 / 90 trading days
- Compare against SPY or sector ETF
- Include estimated transaction costs
- Use `filing_date`, not `transaction_date`, to avoid lookahead bias

Backtest outputs:

| Output | Meaning |
|---|---|
| Cumulative return | Strategy performance over time |
| Benchmark return | SPY or sector ETF return over the same period |
| Win rate | Percentage of winning trades |
| Average / median return | Typical trade outcome |
| Max drawdown | Worst peak-to-trough loss |
| Sharpe ratio | Return adjusted for volatility |
| Trade count | Number of trades |
| Return by holding period | 20d vs 60d vs 90d comparison |

---

## Phase 6 — Dashboard and Alerts

Planned dashboard views:

1. **Live Feed** — recent insider transactions filterable by ticker, role, code, and value
2. **Company View** — single-ticker insider activity with price overlay and buy/sell markers
3. **Signal Leaderboard** — strongest current buying signals and cluster events
4. **Backtest Results** — strategy vs benchmark, return distribution, and holding-period comparison
5. **Alerts** — new open-market purchases, cluster buying, and large transactions relative to company size

---

## Project Structure

```text
main.py                  runs the Form 4 fetch, parse, clean, and store pipeline
fetcher.py               talks to SEC EDGAR and downloads filings
parser.py                parses Form 4 XML into structured rows
transform.py             cleans and types parsed data
storage.py               handles local Parquet files and Cloudflare R2 uploads
market_data.py           fetches daily adjusted stock prices
fetch_spy_prices.py      fetches SPY benchmark prices
join.py                  matches insider transactions to market prices
event_study.py           forward returns, baselines, abnormal returns, and significance testing
config.py                ticker lists and shared settings
sp500_ciks.py            generated ticker-to-CIK lookup
build_sp500_ciks.py      generates the S&P 500 CIK lookup file
processed_filings.py     tracks already-processed filings
inspect_parquet.py       quick script for checking saved Parquet data
requirements.txt         Python dependencies
README.md                project overview and findings
```

Local/generated files that should not be committed:

```text
.env
data/
temp_xml_storage/
processed_accession.txt
__pycache__/
*.parquet
*.csv
```

---

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/checho1504/sec-form4-pipeline.git
cd sec-form4-pipeline
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create a `.env` file

This project uses Cloudflare R2 and Tiingo.

```text
R2_ENDPOINT_URL=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=...
TIINGO_API_KEY=...
```

Do not commit `.env`.

### 4. Run the pipeline

Run scripts in this order:

```bash
python main.py
python market_data.py
python fetch_spy_prices.py
python join.py
python event_study.py
```

---

## Important SEC Note

SEC EDGAR requires a real User-Agent header on every request.

This is configured in `config.py`.

If you fork this project, update the User-Agent with your own name/email or project contact information.

---

## Disclaimer

This project is for research and education only.

It is not financial advice, investment advice, or a recommendation to buy or sell any security.

The results are historical, preliminary, and may change as the dataset expands or the methodology improves.