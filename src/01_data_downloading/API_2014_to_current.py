"""
From 2014 onward, AEO data is available through the EIA API.

This script downloads annual AEO series data across vintages
and combines the results into a single dataframe.

API credentials and query parameters are defined in config.py.
"""

import time
import requests
import pandas as pd

import sys, os
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
sys.path.insert(0, PROJECT_ROOT)
from config import API_KEY, current_year, sector, fuel, region_shorthand, value, region_code, region_abbrv


session = requests.Session()

all_dfs = []

# Download loop
for yr in range(2014, current_year):

    url = f"https://api.eia.gov/v2/aeo/{yr}/data/"

    # Building series ID
    if value == "nom":

        current_series = (
            f"prce_nom_{sector}_NA_{fuel}_NA_{region_shorthand}_ndlrpmbtu"
        )

    elif value == "real":

        if yr == 2014:
            dollar_year = 12
            # old naming convention
            base = f"prce_ene_{sector}_NA_{fuel}_NA_{region_shorthand}"

        else:
            # not sure why they keep this static at 13 from 2015 onward
            dollar_year = 13
            # newer naming convention
            base = f"prce_real_{sector}_NA_{fuel}_NA_{region_shorthand}"

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

outfile = f"data/raw/AEO_{value}_{sector}_{fuel}_{region_abbrv}_2014_current.csv"
final_df.to_csv(outfile, index=False)