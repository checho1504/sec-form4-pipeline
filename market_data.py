import os
import requests
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from config import CIKS

PROJECT_DIR = Path(__file__).parent
load_dotenv(PROJECT_DIR / ".env")

def fetch_daily_prices(ticker: str, start_date: str, end_date: str | None = None):

    headers = {
    'Content-Type': 'application/json',
    'Authorization': f"Token {os.getenv('TIINGO_API_KEY')}"
}

    tickers = list(CIKS.keys())

    for t in tickers:
        url = f"https://api.tiingo.com/tiingo/daily/{t}/prices"
        print(f"Fetching for {t}")

    params = {
        "startDate": "2024-01-01", #change later?
    
    }
    if end_date:
        params["endDate"] = end_date
    
    print(f"Fetching for {ticker}")

    response = requests.get(url, headers=headers, params=params, timeout=30)
    print(ticker, response.status_code)

    if response.status_code != 200:
        print(response.text)
        return pd.DataFrame()
    data = response.json()

    if not data:
        print("No data found for {ticker}")
        return pd.DataFrame()
    
    df = pd.DataFrame(data)

# raw JSON to Dataframe
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

if __name__ == "__main":
    all_dfss = []

    for t in CIKS:
        print(f" Fetching prices for{t}..")

        df = fetch_daily_prices(ticker=t, start_date="2024-01-01", end_date="2024-01-31",)

        if df.empty:
            print(f"No price data found for {t}")
            continue

        all_dfss.append(df)
        print(f"Got {len(df)} rows")

        #Stacking everything into a single DataFrame

        combined_prices = pd.concat(all_dfss, ignore_index=True)
        print(f"\nTotal price rows: {len(combined_prices)}")
        print(combined_prices.head())