import os
import requests
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from config import CIKS
from storage import write_parquet, upload_to_r2

PROJECT_DIR = Path(__file__).parent
load_dotenv(PROJECT_DIR / ".env")


def fetch_daily_prices(ticker: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Token {os.getenv('TIINGO_API_KEY')}"
    }

    url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
    print(f"Fetching for {ticker}")

    params = {"startDate": start_date}
    if end_date:
        params["endDate"] = end_date

    response = requests.get(url, headers=headers, params=params, timeout=30)
    print(ticker, response.status_code)

    if response.status_code != 200:
        print(response.text)
        return pd.DataFrame()

    data = response.json()

    if not data:
        print(f"No data found for {ticker}")
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ticker"] = ticker
    df = df[[
        "ticker",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adjOpen",
        "adjHigh",
        "adjLow",
        "adjClose",
        "adjVolume",
        "divCash",
        "splitFactor",
    ]]

    return df


if __name__ == "__main__":
    all_dfs = []

    for t in CIKS:
        print(f"Fetching prices for {t}...")

        df = fetch_daily_prices(ticker=t, start_date="2022-01-01", end_date=None)

        if df.empty:
            print(f"No price data found for {t}")
            continue

       # saving prices as parquet

        parquet_path = write_parquet(df, t, dataset="prices")

        upload_to_r2(parquet_path, t, dataset="prices")

        all_dfs.append(df)
        print(f"got {len(df)} rows")

    if not all_dfs:
        print("No price data loaded")
    else:
        combined_prices = pd.concat(all_dfs, ignore_index=True)
        print(f"\nTotal price rows: {len(combined_prices)}")
        print(combined_prices.head())
        print(combined_prices.tail(20))

