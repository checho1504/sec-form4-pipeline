# fetch SPY price data for further analysis on event_study

from market_data import fetch_daily_prices
from storage import write_parquet, upload_to_r2

if __name__ == "__main__":
    ticker = "SPY"

    spy_df = fetch_daily_prices(ticker=ticker, start_date="2022-01-01", end_date=None) 

    if spy_df.empty:
        print("No SPY data loaded")
        raise SystemExit

parquet_path = write_parquet(spy_df, ticker, dataset="prices")
upload_to_r2(parquet_path, ticker, dataset="prices")
print(f"Saved SPY benchmark prices: {len(spy_df)} rows")


