"""
Convert SEDS historical price data to constant `calculation_year` dollars
using the BEA GDP chain-type price index (FRED A191RG3A086NBEA).

SEDS prices are nominal dollars of the observation year, so the deflator
base year per row is the `period` column itself. The conversion is:
    value_in_Ystar = value_in_period * (deflator[Ystar] / deflator[period])

Handles both the US case (single-state row, multiple series stacked long)
and the multi-state case (weighted-average price already collapsed to one
series per year), matching the structure produced by the SEDS processing
script.
"""

import os
import pandas as pd
from config import fuel_seds, sector_seds, region_abbrv, calculation_year



# Paths
INPUT_PATH = f"data/interim/SEDS_{fuel_seds}_{sector_seds}_{region_abbrv}.csv"
FRED_PATH = "data/raw/FRED/A191RG3A086NBEA.csv"
OUT_DIR = "data/interim"


def load_deflator(path):
    """Load FRED GDP deflator into a {year: value} dict."""
    df = pd.read_csv(path)
    df["year"] = pd.to_datetime(df["observation_date"]).dt.year
    return dict(zip(df["year"], df["A191RG3A086NBEA"]))


def convert_to_constant(df, year_col, value_col, deflator, target_year):
    """
    Add `<value_col>_converted` column with values in `target_year` dollars.
    """
    years = df[year_col].astype(int)

    missing = set(years.unique()) - set(deflator.keys())
    if missing:
        raise ValueError(
            f"Years missing from FRED deflator: {sorted(missing)}"
        )
    if target_year not in deflator:
        raise ValueError(
            f"calculation_year {target_year} missing from FRED deflator"
        )

    target_def = deflator[target_year]
    factors = years.map(lambda y: target_def / deflator[y])

    df = df.copy()
    df[f"{value_col}_converted"] = df[value_col] * factors
    return df


def main():
    deflator = load_deflator(FRED_PATH)
    print(f"Loaded FRED deflator: {min(deflator)}-{max(deflator)}")

    df = pd.read_csv(INPUT_PATH)
    print(f"Loaded {INPUT_PATH}: {len(df)} rows")

    if region_abbrv == "US":
        # Long-format file with consumption, price, and conversion-factor
        # series stacked. Filter to just the price series before converting.
        price_code = fuel_seds + sector_seds + "D"
        df_price = df[df["seriesId"] == price_code].copy()
        print(f"Filtered to price series ({price_code}): {len(df_price)} rows")

        if df_price.empty:
            raise RuntimeError(
                f"No rows matched price seriesId {price_code!r}. "
                "Check that the SEDS interim file contains the price series."
            )

        converted = convert_to_constant(
            df_price,
            year_col="period",
            value_col="value",
            deflator=deflator,
            target_year=calculation_year,
        )
        converted["unit_converted"] = f"{calculation_year} $/MMBtu"

    else:
        # Already collapsed to (period, ne_avg_price) by the SEDS script
        if "ne_avg_price" not in df.columns:
            raise RuntimeError(
                "Expected 'ne_avg_price' column in non-US SEDS interim file."
            )
        df = df.rename(columns={"ne_avg_price": "value"})
        converted = convert_to_constant(
            df,
            year_col="period",
            value_col="value",
            deflator=deflator,
            target_year=calculation_year,
        )
        converted["unit_converted"] = f"{calculation_year} $/MMBtu"

    os.makedirs(OUT_DIR, exist_ok=True)
    outpath = (
        f"{OUT_DIR}/SEDS_{fuel_seds}_{sector_seds}_{region_abbrv}"
        f"_constant_{calculation_year}.csv"
    )
    converted.to_csv(outpath, index=False)
    print(f"Wrote {outpath}")

    print("\nSample of converted rows:")
    print(converted.head())


if __name__ == "__main__":
    main()