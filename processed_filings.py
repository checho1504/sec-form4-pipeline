from pathlib import Path
import os
from botocore.exceptions import ClientError
from storage import get_r2_client
from dotenv import load_dotenv

#creates the path object pointing at the folder
PROJECT_DIR = Path(__file__).parent 
load_dotenv(PROJECT_DIR / ".env")   
processed= PROJECT_DIR/ "processed_accession.txt"

# This is where the acccesion lives on Cloudflare 

R2_STATE_KEY = "form4/_state/processed_accessions.txt"


def load_processed_accessions():
    """downloads accession log, then reads it and returns the 
    number as a set"""

    client = get_r2_client()
    bucket = os.getenv("R2_BUCKET_NAME")

    try:
        response = client.get_object(Bucket=bucket, Key=R2_STATE_KEY)
        content = response["Body"].read().decode("utf-8")
        processed.write_text(content, encoding="utf-8")
        print(f"Loaded processed accession log from R2: {R2_STATE_KEY}")

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")

        if error_code in ("NoSuchKey", "404"):
            print("No processed accession log found in R2. Starting again")
        else:
            print(f"Could not load processed log from R2: {e}")
            raise
    except Exception as e:
        print((f"Unexpected error while loading processed accession log: {e}"))
        raise
    if not processed.exists():
        return set()
    
    with open(processed, "r", encoding="utf-8") as file:
        return set(line.strip() for line in file if line.strip())
    
    

def mark_accession_processed(accession_number: str):
    """adds an accession number to the processed log"""

    with open(processed, "a", encoding="utf-8") as file:
        file.write(accession_number + "\n")


def save_processed_accessions():
    """uploads local accession log back to r2. Must be called at
    the end of main.py"""

    if not processed.exists():
        print("No local processed accession log to upload")
        return
    
    client = get_r2_client()
    bucket = os.getenv("R2_BUCKET_NAME")

    try:
        client.upload_file(str(processed), bucket, R2_STATE_KEY)
        print(f"saved processed accession log to R2: {R2_STATE_KEY}")
    except Exception as e:
        print(f"Could not save processed accession log to R2: {e}")
        raise
