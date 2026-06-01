"""
From 2014 onward, AEO data is available through the EIA API.

This script downloads annual AEO series data across vintages
and combines the results into a single dataframe.

Note: there was no AEO 2024

API credentials and query parameters are defined in config.py.
"""

import time
import requests
import pandas as pd
import os, sys
from config import API_KEY, current_year, sector_aeo, fuel_aeo, region_shorthand, value, region_code, region_abbrv


outfile = f"data/raw/AEO/AEO_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_2014_current.csv"

# Skip download if file already exists
if os.path.exists(outfile):
    print(f"File already exists: {outfile}. Skipping download.")
    sys.exit(0)

session = requests.Session()

all_dfs = []

# Download loop
for yr in range(2014, current_year):

    if yr == 2024:
        continue

    url = f"https://api.eia.gov/v2/aeo/{yr}/data/"

    # Handling quirky name changes
    # 'resd' was 'res' in AEO 2014-2017, 'comm' was 'cmm' for 2014
    sector_for_api = sector_aeo
    if sector_aeo == 'resd' and yr <= 2017:
        sector_for_api = 'res'
    elif sector_aeo == 'comm' and yr == 2014:
        sector_for_api = 'cmm'
    

    # Building series ID
    if value == "nom":

        current_series = (
            f"prce_nom_{sector_for_api}_NA_{fuel_aeo}_NA_{region_shorthand}_ndlrpmbtu"
        )

    elif value == "real":

        if yr == 2014:
            dollar_year = 12
            # old naming convention
            base = f"prce_ene_{sector_for_api}_NA_{fuel_aeo}_NA_{region_shorthand}"

        else:
            # this is static at 13 from 2015 onward
            dollar_year = 13
            # newer naming convention
            base = f"prce_real_{sector_for_api}_NA_{fuel_aeo}_NA_{region_shorthand}"

        current_series = (
            f"{base}_y{dollar_year}dlrpmmbtu"
        )

    print(f"Downloading {yr} | {current_series}")

    params = {
        "api_key": API_KEY,
        "frequency": "annual",
        "data[]": "value",
        "facets[scenario][]": f"ref{yr}",
        "facets[seriesId][]": current_series,
        "facets[regionId][]": region_code,
        "length": 5000
    }

    # Retry logic with exponential backoff
    for attempt in range(3):

        try:
            response = session.get(
                url,
                params=params,
                timeout=30
            )

            response.raise_for_status()

            json_data = response.json()

            if "response" not in json_data:
                print(f"Skipping {yr}: malformed response")
                break

            df = pd.DataFrame(json_data["response"]["data"])

            if df.empty:
                print(f"No data returned for {yr}")
                break

            df["aeo_vintage"] = yr

            all_dfs.append(df)

            print(f"Success: {yr}")

            # Small pause to avoid API throttling
            time.sleep(1)

            break

        except requests.exceptions.RequestException as e:

            wait_time = 2 ** attempt

            print(
                f"Attempt {attempt + 1} failed for {yr}: {e}"
            )

            if attempt < 2:
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"Failed permanently for {yr}")


# Combine results
final_df = pd.concat(all_dfs, ignore_index=True)
print(final_df.head())

os.makedirs(os.path.dirname(outfile), exist_ok=True)
final_df.to_csv(outfile, index=False)