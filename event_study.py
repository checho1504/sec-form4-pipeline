"""the goal of this script is to measure what happened to stock prices after the insider transactions.
event_price_date is the actual trading day used for the event. """


import os
import io
import pandas as pd
from config import CIKS
from storage import get_r2_client

def load_events_from_r2() -> pd.DataFrame :
    """
    Load form4 and price data from R2 and combine them
    """ 

    client = get_r2_client()
    bucket = os.getenv("R2_BUCKET_NAME")
    all_events = []
    for ticker in CIKS:
        #file path/address
        key = f"events/ticker={ticker}/events_{ticker.lower()}.parquet"

        try:
            response = client.get_object(Bucket=bucket, Key=key)
            data = response["Body"].read()
            df = pd.read_parquet(io.BytesIO(data)) #wraps raw bytes in object that behaves like file
            df["requested_ticker"] = ticker
            all_events.append(df)
            print(f"loaded {ticker}: {len(df)} rows")

        except Exception as e:
            print(f"could not load events for {ticker}: {e}")

    if not all_events:
        print("No event data loaded")
        return pd.DataFrame()

    events_df = pd.concat(all_events, ignore_index=True)

    return events_df

def get_purchase_events(events_df: pd.DataFrame) -> pd.DataFrame:
    """P = purchase. transaction_price_per:share > 0 removes grants, awards, etc"""

    purchase_events = events_df[(events_df["transaction_code"] == "P") & (events_df["transaction_acquired_disposed_code"] == "A") & (events_df["transaction_price_per_share"] > 0)].copy()
    return purchase_events

def count_duplicate_purchase_rows(purchase_events: pd.DataFrame) -> int:
    dedupe_cols = [
        "issuer_ticker",
        "accession_number",
        "reporting_owner_name",
        "transaction_date",
        "transaction_code",
        "transaction_acquired_disposed_code",
        "transaction_shares",
        "transaction_price_per_share",
        "shares_owned_following_transaction",
        "event_price_date",
        "event_adj_close",
    ]

    duplicate_count = purchase_events.duplicated(subset=dedupe_cols).sum()

    return duplicate_count

if __name__ == "__main__":
    events_df = load_events_from_r2()

    if events_df.empty:
        print("No event data found.Run market_data.py & join first.py")
        raise SystemExit # sotps running now. Nothing should execute from here on

    purchase_events = get_purchase_events(events_df)
    duplicate_purchase_rows = count_duplicate_purchase_rows(purchase_events)

    print("\nCombined event dataset:")
    print(f"Rows: {len(events_df)}")
    print(f"Columns: {len(events_df.columns)}")
    print("\nTickers:")
    print(events_df["issuer_ticker"].value_counts())
    print("\nMissing event prices:")
    print("\nPurchase-only signal dataset:")
    print(f"Purchase-only rows: {len(purchase_events)} out of {len(events_df)} total events")
    print(f"Duplicate rows within purchases: {duplicate_purchase_rows} out of {len(purchase_events)}")

    print("\nPurchase-only rows by ticker:")
    print(purchase_events["issuer_ticker"].value_counts())

    print(events_df["event_adj_close"].isna().sum())
    print(events_df[[
        "requested_ticker",
        "issuer_ticker",
        "accession_number",
        "filing_date",
        "transaction_date",
        "transaction_code",
        "transaction_value",
        "event_price_date",
        "event_adj_close",
        "event_volume",
        "price_lag_days",
    ]].tail(30))




