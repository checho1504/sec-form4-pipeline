from pathlib import Path

#creates the path object pointing at the folder
PROJECT_DIR = Path(__file__).parent    
processed= PROJECT_DIR/"processed_accession.txt"

def load_processed_accessions():
    """reads numbers already processed and returns a set"""

    if not processed.exists():
        return set()
    
    with open(processed, "r", encoding="utf-8") as file:
        return set(line.strip() for line in file if line.strip())
    
def mark_accession_processed(accession_number: str):
    """adds an accession number to the processed log"""

    with open(processed, "a", encoding="utf-8") as file:
        file.write(accession_number + "\n")