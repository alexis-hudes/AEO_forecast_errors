"""
AEO data from 2004 to 2010 is not available through the EIA API,
but is presented in consistent formatting on the EIA archive site.


Energy prices by source and sector:
URL pattern: https://www.eia.gov/outlooks/archive/aeo{yr % 100}/supplement/suptab_{table_number}.xls

This script downloads the relevant Excel tables for each vintage and
saves a copy of the raw file
"""
import os
import time
import requests
import pandas as pd

import sys, os
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
sys.path.insert(0, PROJECT_ROOT)
from config import region_abbrv, table_num

# Configuration
AEO_YEARS = range(2004, 2011)
os.makedirs(f"data/raw/aeo_2004_to_2010_{region_abbrv}", exist_ok=True)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (research script)"})

for yr in AEO_YEARS:
    print(f"\nProcessing AEO{yr}...")
    url = f"https://www.eia.gov/outlooks/archive/aeo{yr % 100:02d}/supplement/suptab_{table_num}.xls"

    r = session.get(url, timeout=30)
    r.raise_for_status()

    # Save raw file
    raw_path = os.path.join(f"data/raw/aeo_2004_to_2010_{region_abbrv}", f"aeo{yr}_aeotab_{table_num}.xls")
    with open(raw_path, "wb") as f:
        f.write(r.content)

    time.sleep(1)  # pause before continuing

print('Done')