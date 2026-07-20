# main.py
# runs the whole pipeline

import pandas as pd
from processed_filings import load_processed_accessions, mark_accession_processed, save_processed_accessions
from config import CIKS, TEMP_DIR
from fetcher import fetch_form4s, download_xml
from parser import parse_form4
from transform import clean_dataframe
from storage import write_parquet, upload_to_r2

# Make sure the temp folder exists before saving XML files.
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def delete_downloaded_xml(downloaded_filings):
    # Clean up temporary XML files 
    for xml_file, accession, filing_date in downloaded_filings:
        if xml_file.exists():
            xml_file.unlink()
            print(f"Deleted local XML: {xml_file.name}")


def run_pipeline(ticker: str, cik: str):
    # Load the filings already processedavoiding duplicates

    processed_accessions = load_processed_accessions()
    print(f"\n-Running pipeline for {ticker}")

    filings = fetch_form4s(cik)

    downloaded_filings = []
    for f in filings[:50]: 
        accession = f["accessionNumber"]

        if accession in processed_accessions:
            print(f"Skipping already processed filing: {accession}")
            continue

        path = download_xml(f, cik, TEMP_DIR)

        if path:
            downloaded_filings.append((path, accession, f["filingDate"]))

    # Parse downloaded XML files into transaction rows.
    rows = []
    for xml_file, accession, filing_date in downloaded_filings:
        parsed_rows = parse_form4(xml_file)

        for row in parsed_rows:
            row["accession_number"] = accession
            row["filing_date"] = filing_date

        rows.extend(parsed_rows)

        if parsed_rows:
            mark_accession_processed(accession)

    if not rows:
        print("No new transaction rows found")
        delete_downloaded_xml(downloaded_filings)
        return

    # Convert rows into a DataFrame
    df = clean_dataframe(rows)
    print(f"DataFrame ready: {len(df)} rows, {len(df.columns)} columns")

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)

    print(df[[
    "source_file",
    "accession_number",
    "filing_date",
    "issuer_ticker",
    "reporting_owner_name",
    "transaction_code",
    "transaction_date",
    "transaction_shares",
    "transaction_price_per_share",
    "transaction_value",
]])

    # Save the clean dataset locally and upload it to R2.
    parquet_path = write_parquet(df, ticker)
    upload_to_r2(parquet_path, ticker)

    delete_downloaded_xml(downloaded_filings)


if __name__ == "__main__":
    # Run the pipeline for every ticker in the config file.
    for ticker, cik in CIKS.items():
        run_pipeline(ticker, cik)

    save_processed_accessions() #uploads back to R2 after all tickers finish
