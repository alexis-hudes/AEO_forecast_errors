"""
This script downloads annual historical observations of energy prices
from the State Energy Data System (SEDS) using the EIA API.

API credentials and query parameters are defined in config.py.
"""

import requests
import pandas as pd
import sys, os
from config import API_KEY, sector_seds, fuel_seds


outfile = f"data/raw/SEDS/{sector_seds}_{fuel_seds}.csv"

# Skip download if file already exists
if os.path.exists(outfile):
    print(f"File already exists: {outfile}. Skipping download.")
    sys.exit(0)

session = requests.Session()

url = "https://api.eia.gov/v2/seds/data/"

# defining MSN codes to call SEDS data based on query parameters from config file
consumption_code = fuel_seds + sector_seds + 'B'
price_code = fuel_seds + sector_seds + 'D'
conversion_factor_code = fuel_seds + 'TCK'

params = {
    "api_key": API_KEY,
    "frequency": "annual",
    "data[0]": "value",
    "facets[seriesId][0]": consumption_code, # consumption in Billion Btu
    "facets[seriesId][1]": price_code, # price in Dollars per million Btu
    "facets[seriesId][2]": conversion_factor_code, # million Btu per barrel
    "start": "1990"
}

res = requests.get(url, params=params)
data = res.json()
df = pd.DataFrame(data["response"]["data"])
df["value"] = pd.to_numeric(df["value"], errors="coerce")


print(df.head())

os.makedirs(os.path.dirname(outfile), exist_ok=True)
df.to_csv(outfile, index=False)