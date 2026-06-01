"""
Compile AEO projection data from three vintage ranges into a single dataframe,
with all prices converted to a common constant-dollar year set by
`calculation_year` in config.py.

Conversion uses the BEA GDP chain-type price index (FRED series
A191RG3A086NBEA), which is the deflator EIA uses to construct real prices
in the AEO. Since every dollar-year we convert between is in the past
(projections use base years prior to vintage release, and we only compute
forecast errors against historical observations), a single economy-wide
historical deflator is sufficient -- no vintage-specific inflation
assumptions are needed.

Conversion formula:
    value_in_Ystar = value_in_Y * (deflator[Ystar] / deflator[Y])
where Y is parsed from the row's `unit` column (e.g. "2012 $/mill Btu")
and Ystar is `calculation_year`.
"""

import os
import re
import pandas as pd
from config import region_abbrv, sector_aeo, fuel_aeo, value, calculation_year



# Paths
AEO_DIR = "data/raw/AEO"
FRED_PATH = "data/raw/FRED/A191RG3A086NBEA.csv"
OUT_DIR = "data/interim"

INPUT_FILES = [
    f"{AEO_DIR}/AEO_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_1998_2010.csv",
    f"{AEO_DIR}/AEO_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_2011_2013.csv",
    f"{AEO_DIR}/AEO_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_2014_current.csv"
]

# Canonical unit string for the output
CANONICAL_ENERGY_UNIT = "$/MMBtu"


def load_deflator(path):
    """
    Load the FRED GDP deflator and return a {year: deflator_value} dict.
    The base year of the index is arbitrary -- it divides out in conversion.
    """
    df = pd.read_csv(path)
    df["year"] = pd.to_datetime(df["observation_date"]).dt.year
    return dict(zip(df["year"], df["A191RG3A086NBEA"]))


def parse_base_year(unit_str):
    """
    Pull the four-digit base year out of strings like '2012 $/mill Btu'
    or '1996 $/MMBtu'. Returns int.
    """
    match = re.search(r"\b(19|20)\d{2}\b", str(unit_str))
    if match is None:
        raise ValueError(f"Could not parse base year from unit: {unit_str!r}")
    return int(match.group(0))


def normalize_energy_unit(unit_str):
    """
    Confirm the energy-denominator portion is one of the expected variants
    ('MMBtu' or 'mill Btu', case-insensitive). Returns the canonical form.
    Raises if it's something unexpected -- better to fail loudly than
    silently mishandle a new unit.
    """
    s = str(unit_str).lower()
    if "mmbtu" in s or "mill btu" in s or "million btu" in s:
        return CANONICAL_ENERGY_UNIT
    raise ValueError(f"Unexpected energy unit in: {unit_str!r}")


def convert_prices(df, deflator, target_year):
    """
    Add `value_converted` and `unit_converted` columns to df, with all
    prices expressed in `target_year` dollars.
    """
    # Parse base year per row (vectorized via map for speed on large frames)
    base_years = df["unit"].map(parse_base_year)

    # Validate the energy denominator is something we recognize
    df["unit"].map(normalize_energy_unit)  # raises if not

    # Validate every base year and the target year are in the deflator
    missing = set(base_years.unique()) - set(deflator.keys())
    if missing:
        raise ValueError(
            f"Base years missing from FRED deflator: {sorted(missing)}"
        )
    if target_year not in deflator:
        raise ValueError(
            f"calculation_year {target_year} missing from FRED deflator"
        )

    # Conversion factor per row
    target_def = deflator[target_year]
    factors = base_years.map(lambda y: target_def / deflator[y])

    df = df.copy()
    df["value_converted"] = df["value"] * factors
    df["unit_converted"] = f"{target_year} {CANONICAL_ENERGY_UNIT}"
    df["base_year_original"] = base_years
    return df


def main():
    # Sanity check: real projections only -- the unit-parsing logic
    # assumes a dollar year is present in `unit`, which isn't true for nominal.
    if value != "real":
        raise ValueError(
            f"This script expects value='real' in config; got {value!r}. "
            "Nominal series do not carry a base year in their unit string."
        )

    deflator = load_deflator(FRED_PATH)
    print(f"Loaded FRED deflator: {min(deflator)}-{max(deflator)}")

    frames = []
    for path in INPUT_FILES:
        if not os.path.exists(path):
            print(f"WARNING: missing input file, skipping: {path}")
            continue
        df = pd.read_csv(path)
        print(f"Loaded {path}: {len(df)} rows")
        frames.append(df)

    if not frames:
        raise RuntimeError("No input files found.")

    combined = pd.concat(frames, ignore_index=True)
    print(f"Combined: {len(combined)} rows")

    converted = convert_prices(combined, deflator, calculation_year)

    os.makedirs(OUT_DIR, exist_ok=True)
    outpath = (
        f"{OUT_DIR}/AEO_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}"
        f"_constant_{calculation_year}.csv"
    )
    converted.to_csv(outpath, index=False)
    print(f"Wrote {outpath}")

    # Quick sanity peek
    print("\nSample of converted rows:")
    print(
        converted[
            ["aeo_vintage", "period", "value", "unit",
             "value_converted", "unit_converted", "base_year_original"]
        ].head()
    )


if __name__ == "__main__":
    main()