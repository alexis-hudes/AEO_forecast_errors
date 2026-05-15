"""
AEO data from 1998 to 2010 is not available through the EIA API,
but supplementary data files can be downloaded from the EIA archive site.

This script downloads the relevant XLS tables for each year and
saves a copy of the raw file in a folder


Energy prices by source and sector URLs:
1998
https://www.eia.gov/outlooks/archive/aeo98/sup98tables/sup98b.xls

1999
https://www.eia.gov/outlooks/archive/aeo99/supplement/sup99b.xls

2000
https://www.eia.gov/outlooks/archive/aeo00/supplement/sup2kb.xls

2001 - 2010
https://www.eia.gov/outlooks/archive/aeo{yr % 100:02d}/supplement/sup_t2t3.xls

"""
import os
import time
import requests
import pandas as pd

# Configuration
AEO_YEARS = range(1998, 2011)
os.makedirs(f"data/raw/aeo_1998_to_2010", exist_ok=True)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (research script)"})

for yr in AEO_YEARS:
    print(f"\nProcessing AEO{yr}...")
    if yr == 1998:
        url = "https://www.eia.gov/outlooks/archive/aeo98/sup98tables/sup98b.xls"
    elif yr == 1999:
        url = "https://www.eia.gov/outlooks/archive/aeo99/supplement/sup99b.xls"
    elif yr == 2000:
        url = "https://www.eia.gov/outlooks/archive/aeo00/supplement/sup2kb.xls"
    else:
        url = f"https://www.eia.gov/outlooks/archive/aeo{yr % 100:02d}/supplement/sup_t2t3.xls"

    # check if file already exists before downloading
    raw_path = os.path.join(f"data/raw/aeo_1998_to_2010", f"aeo{yr}.xls")
    
    if os.path.exists(raw_path):
        print(f"  Already exists, skipping")
        continue

    # download
    r = session.get(url, timeout=30)

    # check for error
    r.raise_for_status()

    # save file
    with open(raw_path, "wb") as f:
        f.write(r.content)

    time.sleep(1)  # pause before continuing

print('Done')