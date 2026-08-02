"""
Market data overlay.

This script joins Form 4 insider transaction data with daily market price data.
It uses adjusted prices to account for stock splits and dividends. It also uses price data for the next available 
trading day to account for days when market is closed. Best for forward-return analysis. 

Output: an event-level dataset for later forward-return analysis.
"""

import pandas as pd
from pathlib import Path
from config import OUTPUT_DIR

def join_form4_prices(form4_df: pd.DataFrame, price_df: pd.DataFrame, date_col: str = "filing_date") -> pd.DataFrame:
    form4 = form4_df.copy()
    prices = price_df.copy()

    form4[date_col] = pd.to_datetime(form4[date_col])
    prices["date"] = pd.to_datetime(prices["date"])

    #sorting keys

    form4 = form4.sort_values(date_col)
    prices = prices.sort_values("date")

 
    merged = pd.merge_asof(form4,                      #chooses the closest date as opposed to the exact date match
                           prices,                               
                           left_on=date_col,
                           right_on="date",
                           left_by="issuer_ticker",
                           right_by="ticker",
                           direction="forward",
                           tolerance=pd.Timedelta("5D"),
    )
    return merged

if __name__ == "__main__":
    ticker = "AAPL"

    form4_path = OUTPUT_DIR / f"form4_{ticker.lower()}.parquet"
    price_path = OUTPUT_DIR / f"prices_{ticker.lower()}.parquet"

    form4_df = pd.read_parquet(form4_path)
    price_df = pd.read_parquet(price_path)

    joined_df = join_form4_prices(
        form4_df=form4_df,
        price_df=price_df,
        date_col="filing_date",
    )

    print(f"Form 4 rows: {len(form4_df)}")
    print(f"Price rows: {len(price_df)}")
    print(f"Joined rows: {len(joined_df)}")

    print(joined_df[[
        "issuer_ticker",
        "accession_number",
        "filing_date",
        "transaction_date",
        "reporting_owner_name",
        "transaction_code",
        "transaction_value",
        "date",
        "adjClose",
        "volume",
    ]].head(20))