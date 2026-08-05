import os
import io
from pathlib import Path
import requests
import pandas as pd
from dotenv import load_dotenv
from config import CIKS, OUTPUT_DIR
from storage import write_parquet, upload_to_r2, get_r2_client


PROJECT_DIR = Path(__file__).parent
load_dotenv(PROJECT_DIR / ".env")


def fetch_daily_prices(ticker: str, start_date: str,end_date: str | None = None) -> pd.DataFrame:
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Token {os.getenv('TIINGO_API_KEY')}",
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

    df = df[
        [
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
        ]
    ]

    return df


def inspect_r2data() -> pd.DataFrame:
    """Check whether price and Form 4 data exists in R2."""

    client = get_r2_client()
    bucket = os.getenv("R2_BUCKET_NAME")

    rows = []

    for ticker in CIKS:
        price_key = f"prices/ticker={ticker}/prices_{ticker.lower()}.parquet"
        form4_key = f"form4/ticker={ticker}/form4_{ticker.lower()}.parquet"

        price_rows = 0
        price_min_date = None
        price_max_date = None

        form4_rows = 0
        form4_min_filing_date = None
        form4_max_filing_date = None
        open_market_purchases = 0

        try:
            price_response = client.get_object(Bucket=bucket, Key=price_key)
            price_bytes = price_response["Body"].read()
            price_df = pd.read_parquet(io.BytesIO(price_bytes))

            price_rows = len(price_df)
            price_min_date = price_df["date"].min()
            price_max_date = price_df["date"].max()

        except Exception as e:
            print(f"No price data for {ticker}: {e}")

        try:
            form4_response = client.get_object(Bucket=bucket, Key=form4_key)
            form4_bytes = form4_response["Body"].read()
            form4_df = pd.read_parquet(io.BytesIO(form4_bytes))

            form4_rows = len(form4_df)
            form4_min_filing_date = form4_df["filing_date"].min()
            form4_max_filing_date = form4_df["filing_date"].max()

            open_market_purchases = len(
                form4_df[
                    (form4_df["transaction_code"] == "P")
                    & (form4_df["transaction_acquired_disposed_code"] == "A")
                    & (form4_df["transaction_price_per_share"] > 0)
                ]
            )

        except Exception as e:
            print(f"No Form 4 data for {ticker}: {e}")

        rows.append(
            {
                "ticker": ticker,
                "price_rows": price_rows,
                "price_min_date": price_min_date,
                "price_max_date": price_max_date,
                "form4_rows": form4_rows,
                "form4_min_filing_date": form4_min_filing_date,
                "form4_max_filing_date": form4_max_filing_date,
                "open_market_purchases": open_market_purchases,
            }
        )

    summary_df = pd.DataFrame(rows)

    print("\nR2 data health check:")
    print(summary_df)

    summary_df.to_csv("r2_data_health_check.csv", index=False)
    print("\nSaved r2_data_health_check.csv")

    return summary_df


if __name__ == "__main__":
    all_dfs = []

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for ticker in CIKS:
        local_price_path = OUTPUT_DIR / f"prices_{ticker.lower()}.parquet"

        if local_price_path.exists():
            print(f"Skipping {ticker}: local price parquet already exists")
            continue

        print(f"Fetching prices for {ticker}...")

        df = fetch_daily_prices(
            ticker=ticker,
            start_date="2022-01-01",
            end_date=None,
        )

        if df.empty:
            print(f"No price data found for {ticker}")
            continue

        parquet_path = write_parquet(df, ticker, dataset="prices")
        upload_to_r2(parquet_path, ticker, dataset="prices")

        all_dfs.append(df)
        print(f"got {len(df)} rows")

    if not all_dfs:
        print("No new price data loaded")
    else:
        combined_prices = pd.concat(all_dfs, ignore_index=True)

        print(f"\nTotal new price rows: {len(combined_prices)}")
        print(combined_prices.head())
        print(combined_prices.tail(20))