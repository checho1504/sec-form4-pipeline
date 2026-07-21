import requests
from pathlib import Path
from config import HEADERS
import time

def fetch_form4s(cik: str) -> list: #returns a list of form 4 forms
    r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=HEADERS, timeout=30)
    data = r.json()
    recent = data["filings"]["recent"]

    filings = [
        {
            "accessionNumber": recent["accessionNumber"][i],
            "form"           : recent["form"][i],
            "filingDate"     : recent["filingDate"][i],
            "primaryDocument": recent["primaryDocument"][i],
        }
        for i in range(len(recent["form"]))
    ]

    form4s = [f for f in filings if f["form"] == "4"]
    print(f"Found {len(form4s)} Form 4 filings for CIK {cik}")
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