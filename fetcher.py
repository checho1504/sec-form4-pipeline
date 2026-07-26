import requests
from pathlib import Path
from config import HEADERS
import time


FORM4_START_DATE = "2022-01-01"

def extract_filings(filings_data: dict) -> list:
    """converts SEC filing data into a standard list of dictionaries """

    filings = [
    {
        "accessionNumber": filings_data["accessionNumber"][i],
        "form": filings_data["form"][i],
        "filingDate": filings_data["filingDate"][i],
        "primaryDocument": filings_data["primaryDocument"][i],
    }
    for i in range(len(filings_data["form"]))
    ]
    return filings

def fetch_form4s(cik: str, start_date: str = FORM4_START_DATE) -> list: #returns a list of form 4 forms
    r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=HEADERS, timeout=30)
    data = r.json()
    all_filings = []
    recent_filings = extract_filings(data["filings"]["recent"])
    all_filings.extend(recent_filings)

    # older paginated filing files

    older_files = data["filings"].get("files", []) 

    for file_info in older_files:
        file_name = file_info["name"]
        older_url = f"https://data.sec.gov/submissions/{file_name}"

        try:
            time.sleep(0.25)

            older_r = requests.get(older_url, headers=HEADERS, timeout=30)
            print(f"Fetched older submissions file {file_name}: {older_r.status_code}")
            if older_r.status_code != 200:
                continue

            older_data = older_r.json()
            older_filings = extract_filings(older_data)
            all_filings.extend(older_filings)
        except requests.exceptions.RequestException as e:
            print(f"could not fetch older submissions file {file_name}: {e}")
            continue

    form4s = [filing for filing in all_filings if filing["form"] == "4" and filing["filingDate"] >= start_date]
    print(f"Found {len(form4s)} Form 4 filings for CIK {cik} since {start_date}")
    return form4s


def build_xml_url(cik: str, accession: str, primary_doc: str) -> str: # this function builds the URL that will be used to download the xml file
    accession_nodash = accession.replace("-", "")
    cik_nozeros      = str(int(cik))
    primary_doc_raw  = primary_doc.split("/")[-1]
    return (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik_nozeros}/{accession_nodash}/{primary_doc_raw}"
    )


def download_xml(filing: dict, cik: str, dest_dir: Path) -> Path | None:
    filing["xml_url"] = build_xml_url(cik, filing["accessionNumber"], filing["primaryDocument"])
    
    #adding a delay between requests
    try:
        time.sleep(0.25)
        xml_r = requests.get(filing["xml_url"], headers=HEADERS, timeout=30)
        print(filing["accessionNumber"], xml_r.status_code)

    except requests.exceptions.RequestException as e:
        print(f"SEC request failed for {filing['accessionNumber']}: {e}")
        return None


    if xml_r.status_code == 200 and "<ownershipDocument>" in xml_r.text:
        file_path = dest_dir / f"{filing['accessionNumber']}.xml"

        with open(file_path, "w", encoding="utf-8") as file:
            file.write(xml_r.text)

        print(f"Saved XML to: {file_path.resolve()}")
        return file_path
        
    else:
        print(f"Skipped: {filing['accessionNumber']}")
        return None