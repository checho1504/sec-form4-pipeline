# Follow the Money: Insider Buying Event Study & Backtest

A Python project that pulls SEC Form 4 insider trading filings, filters for open market purchases, joins them with stock prices, runs an event study, builds trading signals, and backtests a portfolio strategy. Results are shown on a live dashboard.

Main question: when insiders buy their own company's stock on the open market, does the stock tend to do better afterward? And can that actually be turned into a strategy?

What I found: open market insider purchases show a statistically significant short term return, strongest around the 20 trading day mark. That signal fades by 60 to 90 days. When I turned it into an actual portfolio strategy with position limits and transaction costs, it underperformed SPY on total return but had a much smoother ride (Sharpe 1.16, max drawdown 7.75% vs SPY's deeper drops).

Live dashboard: https://sec-form4-pipeline-zrth7rzakv5pdgkhximw6y.streamlit.app/

---

## What it does

- Downloads Form 4 filings from SEC EDGAR for the S&P 500
- Parses the XML into clean transaction rows
- Filters down to open market purchases only (code P, insider used their own money)
- Checks for bad values before they can throw off calculations
- Stores everything as Parquet in Cloudflare R2
- Pulls daily adjusted stock prices and lines each filing up with the next trading day
- Runs an event study: forward returns at 1, 5, 20, 60, and 90 days, compared to SPY and to random days, tested for significance
- Builds signal features like cluster buying, insider role, and momentum
- Backtests the strategy two ways, a simple trade level test and a capital constrained portfolio simulation
- Runs on a schedule through GitHub Actions
- Feeds a live Streamlit dashboard

## Why I built it

I kept seeing headlines like "CEO buys $2M of their own stock" treated as automatically good news. I wanted to actually test that instead of just assuming it. So I set out to answer:

- Do stocks go up after insider purchases?
- Do they beat the market?
- Is it a real pattern or just noise?
- If it's real, can you actually trade it and make money after costs?

This is a student project. Not investment advice.

## How the pipeline works

```
SEC EDGAR
  Download Form 4 XML filings
  Parse into transaction rows
  Clean data, check for bad values, compute transaction value
  Save to Parquet, upload to Cloudflare R2
  Pull market data, join filings to next trading day
  Event study (forward returns, baselines, significance tests)
  Signal engineering (cluster buying, role flags, momentum)
  Backtesting (trade level and portfolio level)
  Streamlit dashboard, connected live to R2
  Whole thing runs on GitHub Actions
```

Storage layout in R2:

```
r2://follow the money/
  form4/ticker=AAPL/form4_aapl.parquet
  prices/ticker=AAPL/prices_aapl.parquet
  events/ticker=AAPL/events_aapl.parquet
  signals/ticker=AAPL/signals_aapl.parquet
  insider_panel/ticker=AAPL/insider_panel_aapl.parquet
  metadata/processed_accession.txt
```

## The purchase filter

```
transaction_code == "P"
transaction_acquired_disposed_code == "A"
transaction_price_per_share > 0
```

This keeps open market purchases where the insider used their own money, and drops grants, awards, gifts, and anything with no real price attached.

One rule runs through the whole pipeline: the event date is the filing date, not the transaction date. That's when the market actually learns about the trade, so it's the date you have to use if you want to avoid lookahead bias.

## Event study results

Dataset: 44,820 total Form 4 rows across 498 tickers, narrowed down to 842 clean open market purchase events across 174 tickers, 2022 to present.

Raw returns:

| Horizon | Events | Mean Return | Median Return | Win Rate |
|---|---|---|---|---|
| 1 day | 836 | 0.87% | 0.87% | 69.62% |
| 5 days | 823 | 1.00% | 0.75% | 56.38% |
| 20 days | 802 | 3.23% | 3.42% | 67.83% |
| 60 days | 609 | 5.32% | 3.36% | 56.81% |
| 90 days | 535 | 6.96% | 3.59% | 59.44% |

Raw returns just tell you if the stock went up. They don't account for the market moving too.

SPY adjusted returns:

| Horizon | Mean Abnormal Return | Median Abnormal Return | Win Rate vs SPY |
|---|---|---|---|
| 1 day | 0.87% | 0.79% | 68.14% |
| 5 days | 0.88% | 0.65% | 56.69% |
| 20 days | 2.39% | 2.59% | 61.67% |
| 60 days | -0.56% | -1.68% | 44.13% |
| 90 days | -0.67% | -5.52% | 39.44% |

Random days adjusted returns:

| Horizon | Mean Abnormal Return | Median Abnormal Return | Win Rate vs Random Days |
|---|---|---|---|
| 1 day | 0.81% | 0.83% | 67.46% |
| 5 days | 0.76% | 0.43% | 53.95% |
| 20 days | 2.29% | N/A | 65.59% |
| 60 days | 2.98% | 0.88% | 51.89% |
| 90 days | 3.37% | 0.75% | 51.40% |

To test if any of this is real and not just a few big movers, I ran a ticker level block bootstrap along with a one sample t test. A normal bootstrap can get skewed by companies that show up a lot, so the block bootstrap resamples by ticker to check if the pattern holds across companies.

| Horizon | SPY Adjusted Significant | Random Days Significant | Interpretation |
|---|---|---|---|
| 1 day | Yes | Yes | Strong short term reaction |
| 5 days | Yes | Yes | Positive but weaker |
| 20 days | Yes | Yes | Strongest result |
| 60 days | No | No | Not reliable |
| 90 days | No | No | Not reliable |

Bottom line: insider buying looks like a real short term signal here, strongest around 20 trading days. It doesn't look like a good long term buy and hold signal.

## Signal engineering

Turned the raw transactions into usable features:

| Feature | What it is |
|---|---|
| net_insider_buying | Buy value minus sell value in a rolling window |
| gross_buy_value | Buy value only, not offset by sells |
| cluster_buying | Multiple insiders buying the same stock in the same week |
| role_flag | CEO, CFO, Director, or 10% owner |
| open_market_only | Filters to open market buys and sells |
| transaction_value | Shares times price |
| insider_count | Distinct insiders active in the window |
| buy_sell_imbalance | Buy value over total buy plus sell value |
| distance_from_52w_high | How far below the 52 week high at filing time |
| prior_30d_return | Momentum going into the filing |
| prior_30d_volatility | How volatile the stock was before the filing |
| filing_lag_days | Gap between the trade and when it was filed |

Every feature checks for implausible values before it gets aggregated, and duplicate filings from affiliated owners get collapsed so the same trade doesn't get counted twice.

## Backtest results

**Trade level (backtest.py):** enter the next trading day after a clean purchase signal is filed, hold for 20 trading days, compare to SPY over the same window. Filing lag capped at 5 days, one signal per ticker per filing date, joint filers deduped.

**Portfolio level (portfolio.py):** a more realistic version on top of those trades. $100,000 starting capital, $5,000 per position, max 20 open positions at once, transaction costs at 0.10% on both entry and exit. When signals collide, the bigger purchase wins, and the same ticker gets skipped if it's already held.

| Metric | Strategy | SPY Buy and Hold |
|---|---|---|
| Total return | 16.4% | 36.9% |
| CAGR | 8.1% | |
| Sharpe ratio | 1.16 | |
| Max drawdown | 7.75% | deeper |
| Excess return vs benchmark | 20.5pp behind | |

The strategy trails SPY on raw return, but it gets there with a much smoother path. A few reasons why, based on digging into it:

- About 41% of signals got skipped because of the position cap or because that ticker was already held
- The $5,000 position size doesn't scale up as the account grows
- There were stretches with idle cash when not enough signals came through

That's the finding as it stands. I looked into these but didn't chase them further given the scope of the project.

## Two real bugs I found and fixed

**Bug 1, ticker and CIK mix up.** Pulling data for JPM was also pulling in filings where JPM showed up as a shareholder in some other company, not as the actual filer. Big banks hold stakes all over the place, and the code wasn't checking that the issuer CIK in the filing actually matched the CIK I was collecting for. I fixed it in parser.py and main.py so mismatched rows get dropped before they're ever saved, instead of filtering them out later in join.py. Tested it live: JPM dropped one leaked row, BAC dropped 37 (mostly closed end funds), TSLA correctly dropped zero.

**Bug 2, bad values and double counted trades.** PSX had a wildly wrong transaction value in the signals panel. Digging into it turned up two more issues at the same time. NRG and ROL had billion dollar net insider buying numbers that looked wrong but turned out to be real trades counted twice. FANG had a huge number too but that one checked out as a real block sale.

Three separate causes:

1. PSX: a decimal point got dropped in a filed price, an as filed SEC typo, not something my code did.
2. NRG and ROL: the same trade gets filed twice under SEC rules, once by the individual and once by their holding company or trust, so the dollar value was getting summed twice.
3. FANG: confirmed real, a $2.15B block sale filed correctly once. Left alone.

Fix: transform.py now nulls out implausible prices and share counts before transaction value gets calculated, so one bad field can't blow up an aggregate later. Raw values are kept in separate columns for auditing. price_utils.py holds a single shared set of plausibility thresholds instead of two copies that could drift apart. signals.py adds the same guard for share counts and dedupes trades filed by more than one affiliated owner. main.py and join.py can now rebuild a single ticker without reprocessing all 500+.

Still open: WRB and TSLA show a similar pattern to NRG and ROL in the gross buy value view. Haven't root caused it yet, worth checking before trusting those numbers for position sizing.

## Dashboard

Built in Streamlit, connected live to R2, refreshes hourly.

1. Backtest Results, strategy vs benchmark, drawdown chart, skipped trade breakdown
2. Event Study, forward returns, abnormal returns, significance tests by horizon
3. Live Feed, recent Form 4 transactions, filterable by ticker, role, code, value, and date
4. Signal Leaderboard, strongest current buying signals and cluster events
5. Company View, single ticker insider activity with price overlay

One thing worth noting from the build: the pipeline files assumed they'd all sit in one folder and import each other directly. Once I copied them into dashboard/lib, those imports broke. Fixed it by adding lib's own path to sys.path in the adapter files instead of touching the original pipeline code. Small lesson about how file location and imports end up tied together.

## Project structure

```
main.py                 runs the pipeline, supports single ticker rebuilds
config.py                CIK list, paths, constants
fetcher.py                talks to SEC EDGAR, downloads XML
parser.py                parses XML into transaction rows
transform.py              cleans data, checks for bad values
price_utils.py            shared price index and plausibility thresholds
join.py                   joins Form 4 data to prices
event_study.py            forward returns, baselines, significance tests
signals.py                signal engineering
backtest.py                trade level backtest
portfolio.py               portfolio level backtest
storage.py                writes Parquet, uploads to R2
processed_filings.py       tracks processed filings
inspect_parquet.py         checks saved data
build_sp500_ciks.py        builds the S&P 500 ticker to CIK list
sp500_ciks.py              generated ticker to CIK lookup
dashboard/                 Streamlit app
requirements.txt
README.md
.env                      local credentials, not committed
```

## Getting started

Clone it:

```
git clone https://github.com/checho1504/sec form4 pipeline.git
cd sec form4 pipeline
```

Install requirements:

```
pip install -r requirements.txt
```

Make a .env file with your Cloudflare R2 and Tiingo credentials:

```
R2_ENDPOINT_URL=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
TIINGO_API_KEY=
```

Run the pipeline in order:

```
python main.py
python market_data.py
python fetch_spy_prices.py
python join.py
python event_study.py
python signals.py
python backtest.py
python portfolio.py
```

You can rebuild just one ticker without touching the rest:

```
python main.py PSX
python join.py PSX
```

Run the dashboard locally:

```
cd dashboard
streamlit run Home.py
```

More setup details in dashboard/README.md.

## SEC note

SEC EDGAR requires a real User Agent header on every request, set in config.py. If you fork this, swap in your own contact info.

## Limitations

This is a research project, not a trading strategy, and not investment advice. Fills are assumed at the daily close with no slippage. No adjustment for liquidity or trading volume when sizing positions. Not sure if the price data includes delisted tickers, so there may be some survivorship bias. No out of sample testing was done. The WRB and TSLA pattern mentioned above still needs to be looked into. Numbers may shift as more filings get added over time.


## Disclaimer

This project is for research and education. It is not financial advice or a recommendation to buy or sell anything. The results are historical and may change as the dataset grows or the methodology improves.
