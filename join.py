"""
Market data overlay.

This script joins Form 4 insider transaction data with daily market price data.
It uses adjusted prices to account for stock splits and dividends. It also uses price data for the next available 
trading day to account for days when market is closed. Best for forward-return analysis. 

Output: an event-level dataset for later forward-return analysis.
"""

import pandas as pd
from config import OUTPUT_DIR

TICKER_ALIASES = { 
    "GOOG": ["GOOG", "GOOGL"],
    "BNY": ["BNY", "BK"],
    "BF-B": ["BF-B", "BFA", "BFB", "BFA, BFB"],
}

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
                           left_by="join_ticker",
                           right_by="join_ticker",
                           direction="forward",
                           tolerance=pd.Timedelta("5D"),
    )
    return merged



if __name__ == "__main__":
    from config import CIKS
    from storage import write_parquet, upload_to_r2

    all_joined = []

    for ticker in CIKS:
        form4_path = OUTPUT_DIR / f"form4_{ticker.lower()}.parquet"
        price_path = OUTPUT_DIR / f"prices_{ticker.lower()}.parquet"
        if not form4_path.exists() or not price_path.exists():
            print(f"Skipping {ticker}: missing form4 or price parquet")
            continue

        form4_df = pd.read_parquet(form4_path)
        price_df = pd.read_parquet(price_path)

        # Keep rows where SEC issuer ticker is acceptable for the ticker being processed

        form4_df["issuer_ticker"] = (form4_df["issuer_ticker"]).astype(str).str.upper().str.replace(".","-", regex=False)
        expected_tickers = TICKER_ALIASES.get(ticker, [ticker])
        bad_rows = form4_df[~form4_df["issuer_ticker"].isin(expected_tickers)]

        if not bad_rows.empty:
            print(f"Dropping {len(bad_rows)} not expected for {ticker}")
            print(bad_rows["issuer_ticker"].value_counts())
        form4_df = form4_df[form4_df["issuer_ticker"].isin(expected_tickers)].copy()

        if form4_df.empty:
            print(f"skipping {ticker}: no matching Form 4 rows after filtering")
            continue 

        form4_df["join_ticker"] = ticker
        price_df["join_ticker"] = ticker

        joined_df = join_form4_prices(form4_df=form4_df, price_df=price_df, date_col="filing_date",
                                      )

        #checking for missing price matches

        missing_price_matches = joined_df['adjClose'].isna().sum()
        matched_price_rows = joined_df["adjClose"].notna().sum()
        total_rows = len(joined_df)

        # check if any filings were matched to a future trading date

        joined_df['price_lag_days'] = (joined_df['date'] - joined_df['filing_date']).dt.days
    
        #renaming columns
        joined_df = joined_df.rename(columns={
        "date": "event_price_date",
        "adjClose": "event_adj_close",
        "volume": "event_volume",
    })

        parquet_path = write_parquet(joined_df, ticker, dataset="events")
        upload_to_r2(parquet_path, ticker, dataset="events")

        all_joined.append(joined_df)

    if all_joined:
                combined = pd.concat(all_joined, ignore_index=True)
                print(f"\nTotal joined rows across all tiickers: {len(combined)}")
                print(f"Form 4 rows: {len(combined)}")
                print(f"missing price matches: {combined['event_adj_close'].isna().sum()}")
                print(f"Matched price rows: {combined['event_adj_close'].notna().sum()}/{len(combined)}")   

                missing = combined[combined["event_adj_close"].isna()]
                print(missing["issuer_ticker"].value_counts())
                print(missing[["issuer_ticker", "filing_date"]].sort_values("filing_date"))
    
                print(combined[[
                "issuer_ticker",
                "accession_number",
                "filing_date",
                "transaction_date",
                "reporting_owner_name",
                "transaction_code",
                "transaction_value",
                "event_price_date",
                "event_adj_close",
                "event_volume",
                "price_lag_days",
                ]].head(30))