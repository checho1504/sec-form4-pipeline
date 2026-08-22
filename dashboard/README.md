# Follow the Money — Dashboard

Streamlit front end for the insider-trading pipeline. Reads directly from
Cloudflare R2 — no local data needed once secrets are set.

## Setup

1. **Copy your pipeline files into `lib/`** (unmodified):
   - `backtest.py`
   - `portfolio.py`
   - `event_study.py`
   - `price_utils.py`
   - `storage.py`

   These are only *imported* for their pure functions (signal building, trade
   construction, portfolio simulation) — the dashboard's own R2 loader in
   `lib/r2_client.py` handles all actual data fetching, so nothing in these
   files needs to change. If `event_study.py` or `storage.py` run any network
   calls at import time (outside a function), guard them behind
   `if __name__ == "__main__":` so importing the module doesn't try to hit R2
   before secrets are configured.

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up credentials for local dev:**
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   # fill in your real R2 credentials — this file is gitignored
   ```

4. **Run locally:**
   ```bash
   streamlit run Home.py
   ```

## Deploying to Streamlit Community Cloud (free, public URL)

1. Push this repo to GitHub (**do not commit `.streamlit/secrets.toml`** —
   add it to `.gitignore` if it isn't already).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with
   GitHub, and click "New app."
3. Point it at this repo, branch, and `Home.py` as the main file.
4. In **App settings → Secrets**, paste the same key/value pairs from
   `secrets.toml.example` with your real credentials.
5. Deploy. You'll get a public `*.streamlit.app` URL — that's what goes in
   the GitHub README and LinkedIn post.

## Project structure

```
Home.py                          ← landing page
pages/
  1_📈_Backtest_Results.py       ← equity curve, drawdown, trade tables
lib/
  r2_client.py                   ← shared R2 client + cached loaders (dashboard-native)
  backtest_runtime.py            ← wires R2 data into backtest.py/portfolio.py's pure functions
  backtest.py                    ← copy from main pipeline repo
  portfolio.py                   ← copy from main pipeline repo
  event_study.py                 ← copy from main pipeline repo
  price_utils.py                 ← copy from main pipeline repo
  storage.py                     ← copy from main pipeline repo
.streamlit/
  secrets.toml.example           ← template; real secrets.toml is gitignored
```

## Roadmap (dashboard-specific)

- [x] Backtest Results page
- [ ] Signal Leaderboard page (reads `signals`/`insider_panel` datasets — no new backend logic needed)
- [ ] Company View page (single-ticker insider activity + price overlay)
- [ ] Live Feed page (recent filings, filterable)
- [ ] Alerts page (stretch goal)
