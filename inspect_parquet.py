import io
import os
from pathlib import Path
from config import CIKS
import boto3
import pandas as pd
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).parent
load_dotenv(PROJECT_DIR / ".env")

R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")

s3 = boto3.client("s3", endpoint_url=R2_ENDPOINT_URL, aws_access_key_id=R2_ACCESS_KEY_ID, aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    region_name="auto")

#loads each ticker's parquet file from R2
all_dfs = []
for ticker in CIKS:
    object_key = f"form4/ticker={ticker}/form4_{ticker.lower()}.parquet"

    try:
        response = s3.get_object(Bucket=os.getenv("R2_BUCKET_NAME"), Key=object_key)
        parquet_bytes = response["Body"].read()
        df = pd.read_parquet(io.BytesIO(parquet_bytes))
        print(f"Loaded {len(df)} rows for {ticker}")
        all_dfs.append(df)
    
    except Exception as e:
        print(f"Could not load ticke: {e}")


# combining into a single df

if not all_dfs:
    print("No data loaded")
else:
    combined = pd.concat(all_dfs, ignore_index=True)

    print(f"\nTotal rows: {len(combined)}")
    print(f"Tickers: {combined['issuer_ticker'].unique().tolist()}")

    print(combined[[
        "source_file",
        "issuer_ticker",
        "reporting_owner_name",
        "transaction_date",
        "transaction_code",
        "transaction_shares",
        "transaction_price_per_share",
        "transaction_value",
    ]].head(100))

    combined.info()