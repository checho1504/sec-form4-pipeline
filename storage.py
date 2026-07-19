from pathlib import Path
from config import OUTPUT_DIR
import boto3
from dotenv import load_dotenv
from os import environ as env

# this loads  the credentials from the .env file

load_dotenv(Path(__file__).parent / ".env")

def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=env.get("R2_ENDPOINT_URL"),
        aws_access_key_id=env.get("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=env.get("R2_SECRET_ACCESS_KEY"),
    )

#this function saves the dataframe in parque format
def write_parquet(df, ticker: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"form4_{ticker.lower()}.parquet"
    df.to_parquet(output_path, index=False)
    print(f"Parquet saved to: {output_path.resolve()}")
    return output_path


def upload_to_r2(local_path: Path, ticker: str):
    bucket = env.get("R2_BUCKET_NAME")
    r2_key = f"form4/ticker={ticker}/{local_path.name}"
    client = get_r2_client()
    client.upload_file(str(local_path), bucket, r2_key)
    print(f"Uploaded to R2: {r2_key}")

    




