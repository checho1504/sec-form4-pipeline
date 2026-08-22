from pathlib import Path
from sp500_ciks import CIKS_SP500_ALL

HEADERS = {
    "User-Agent": "FollowTheMoney velasus99@gmail.com",
    "Accept": "application/json"
}

# initial CIK (SEC identifier numbers) list
CIKS_CORE = {
    # Mega-Cap Tech
    "NVDA": "0001045810",
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "AMZN": "0001018724",
    "META": "0001326801",
    "GOOGL": "0001652044",
    "TSLA": "0001318605",

    # Financials
    "JPM": "0000019617",
    "BAC": "0000070858",
    "GS": "0000886982",
    "MS": "0000895421",
    "V": "0001403161",
    "MA": "0001141391",
    "PYPL": "0001633917",
    "COIN": "0001679788",

    # Healthcare
    "LLY": "0000059478",
    "UNH": "0000731766",
    "JNJ": "0000200406",
    "PFE": "0000078003",
    "MRK": "0000310158",

    # Consumer
    "WMT": "0000104169",
    "COST": "0000909832",
    "HD": "0000354950",
    "NKE": "0000320187",
    "MCD": "0000063908",

    # Energy / Industrials
    "XOM": "0000034088",
    "CVX": "0000093410",
    "CAT": "0000018230",
    "BA": "0000012927",
    "GE": "0000040545",
}
# Everything we ever want in the dataset

CIKS_ALL = {**CIKS_CORE, **CIKS_SP500_ALL}

CIKS = CIKS_ALL


PROJECT_DIR = Path(__file__).parent
TEMP_DIR = PROJECT_DIR / "temp_xml_storage"
OUTPUT_DIR = PROJECT_DIR / "data" / "parquet"

