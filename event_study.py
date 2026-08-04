"""the goal of this scrip is to measure what  happened to stock prices after the insider transactions.
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

if __name__ == "__main__":
    events_df = load_events_from_r2()

    print("\nCombined event dataset:")
    print(f"Rows: {len(events_df)}")
    print(f"Columns: {len(events_df.columns)}")
    print("\nTickers:")
    print(events_df["issuer_ticker"].value_counts())
    print("\nMissing event prices:")
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




def get_forward_price():
    """find the adjusted close price horizon_days trading days after the event price date"""
    return