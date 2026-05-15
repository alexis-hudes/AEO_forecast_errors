"""
Parse AEO 2004-2010 archive .xls files and convert them to long-format CSV
matching the schema of AEO_real_elep_ng_US.csv.

Driven by config.py (sector, fuel, region, value).
"""
import os
import re
import sys
import glob
import pandas as pd

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
sys.path.insert(0, PROJECT_ROOT)
from config import (
    region_abbrv, sector, fuel, value, region_code, region
)

RAW_DIR = f"data/raw/aeo_2004_to_2010_{region_abbrv}"
OUT_PATH = f"data/raw/AEO_{value}_{sector}_{fuel}_{region_abbrv}_2004_2010.csv"

COLUMNS = [
    "period", "history", "scenario", "scenarioDescription",
    "tableId", "tableName", "seriesId", "seriesName",
    "regionId", "regionName", "value", "unit", "aeo_vintage",
]

# Section + fuel labels keyed by config strings. These mirror the API series ID
# fragments. Extend as needed.
SECTION_PATTERNS = {
    "elep": ["electric power", "electric generator"],
    "resd": ["residential"],
    "comm": ["commercial"],
    "indu": ["industrial"],
    "trn":  ["transportation"],
}
FUEL_LABELS = {
    "ng":   ["natural gas"],
    "petr": ["petroleum", "distillate fuel oil"],
    "coal": ["steam coal", "coal"],
    "elc":  ["electricity"],
}

# Region label inside the file -- needed to disambiguate multi-region files
REGION_HEADER_LABELS = {
    "United States": ["united states"],
    "New England":   ["new england"],
}

# Mapping from config to the API metadata fields, so the CSV output is
# byte-compatible with the 2014+ pipeline.
TABLE_ID = 3
TABLE_NAME = "Energy Prices by Sector and Source"
SCENARIO_DESC = "Reference case"

SECTOR_DESC = {"elep": "Electric Power", "resd": "Residential",
               "comm": "Commercial", "indu": "Industrial",
               "trn": "Transportation"}
FUEL_DESC = {"ng": "Natural Gas", "coal": "Coal",
             "petr": "Petroleum", "elc": "Electricity"}


def _norm(s):
    if not isinstance(s, str):
        return ""
    return s.strip().lower()


def detect_label_col(df):
    """Pick the leftmost column whose cells are mostly strings. AEO 2004-style
    files have labels in col 0; AEO 2008-2010 have a blank col 0 and labels in
    col 1."""
    best_col, best_count = 0, -1
    for c in range(min(3, df.shape[1])):
        count = sum(1 for v in df.iloc[:, c] if isinstance(v, str) and v.strip())
        if count > best_count:
            best_count = count
            best_col = c
    return best_col


def find_base_year(df):
    """Find the base year from header text like '(2002 Dollars per Million Btu)'
    or '(2008 dollars per million Btu, unless otherwise noted)'. This is the
    real-dollars base year; the nominal sub-table (when present) reports actual
    nominal $ for each forecast year."""
    pat = re.compile(r"\(\s*(\d{4})\s*dollars", re.IGNORECASE)
    for v in df.values.flatten():
        if isinstance(v, str):
            m = pat.search(v)
            if m:
                yr = int(m.group(1))
                if 1990 <= yr <= 2030:
                    return yr
    return None


def find_year_row(df, label_col, start_row=0):
    """First row with >=10 year-like ints in columns AFTER label_col."""
    for i in range(start_row, len(df)):
        years = []
        for c in range(label_col + 1, df.shape[1]):
            v = df.iloc[i, c]
            if (isinstance(v, (int, float)) and not pd.isna(v)
                    and 1995 <= v <= 2050 and float(v).is_integer()):
                years.append((c, int(v)))
        if len(years) >= 10:
            return i, years
    return None, None


def find_nominal_header(df, label_col, start_row=0):
    """For AEO 2008+, the same file holds a 'Prices in Nominal Dollars' section
    below the real-$ section. Return the row of that banner, or None."""
    for i in range(start_row, len(df)):
        v = df.iloc[i, label_col]
        if isinstance(v, str) and "nominal dollars" in _norm(v):
            return i
    return None


def is_section_header(df, row_idx, label_col):
    """A section header has a string label and no numeric values in the row."""
    label = df.iloc[row_idx, label_col]
    if not isinstance(label, str) or not label.strip():
        return False
    for c in range(label_col + 1, df.shape[1]):
        v = df.iloc[row_idx, c]
        if isinstance(v, (int, float)) and not pd.isna(v):
            return False
    return True


def find_target_row(df, search_start, label_col, search_end,
                    section_patterns, fuel_labels):
    """Find the fuel row inside the target section. Section start is detected
    by a section-header row matching one of `section_patterns`. We stop the
    section at the next section-header row, so we don't accidentally pick a
    fuel row from a later section (e.g. 'Average Price to All Users')."""
    in_section = False
    for i in range(search_start, search_end):
        label = df.iloc[i, label_col]
        if not isinstance(label, str):
            continue
        low = _norm(label)
        if not low:
            continue

        if is_section_header(df, i, label_col):
            if any(p in low for p in section_patterns):
                in_section = True
                continue
            elif in_section:
                # left the target section without finding the fuel
                break
            else:
                continue

        if in_section:
            # Match fuel; first match wins. Strip footnote markers like '2/'.
            stem = re.sub(r"\s*\d+/\s*$", "", low).strip()
            if any(fl == stem or fl in stem for fl in fuel_labels):
                return i
    return None


def parse_file(path, vintage):
    df = pd.read_excel(path, engine="xlrd", header=None)

    label_col = detect_label_col(df)
    base_year = find_base_year(df)
    if base_year is None:
        raise ValueError(f"{path}: could not find base year")


    # The year header is at (or near) the top of the file; the same year
    # columns apply to both the real-$ and the nominal-$ sub-tables.
    year_row, years = find_year_row(df, label_col, start_row=0)
    if year_row is None:
        raise ValueError(f"{path}: could not find year header row")

    nominal_row = find_nominal_header(df, label_col, start_row=year_row + 1)
    if value == "real":
        # Search the real-$ sub-table only -- bail before the nominal banner
        # so we don't pick its 'Electric Power -> Natural Gas' row by mistake.
        section_start = year_row + 1
        section_end = nominal_row if nominal_row else len(df)
        unit_str = f"{base_year} $/MMBtu"
    elif value == "nom":
        if nominal_row is None:
            raise ValueError(
                f"{path}: no 'Prices in Nominal Dollars' section "
                f"(AEO {vintage} only reports real $)"
            )
        section_start = nominal_row + 1
        section_end = len(df)
        unit_str = "nominal $/MMBtu"
    else:
        raise ValueError(f"unknown value type: {value!r}")

    section_patterns = SECTION_PATTERNS[sector]
    fuel_labels = FUEL_LABELS[fuel]
    target_row = find_target_row(
        df, section_start, label_col, section_end,
        section_patterns, fuel_labels,
    )
    if target_row is None:
        raise ValueError(
            f"{path}: could not find {SECTOR_DESC[sector]} -> "
            f"{FUEL_DESC[fuel]} row"
        )

    # Match the AEO 2015+ API series ID convention. (AEO 2014 used 'ene'/'y12'
    # but the rest of the timeseries through 2023+ uses 'real'/'y13'. We don't
    # try to reproduce the 2014 quirk.)
    if value == "real":
        series_id = (
            f"prce_real_{sector}_NA_{fuel}_NA_NA_"
            f"y{str(base_year)[-2:]}dlrpmmbtu"
        )
    else:
        series_id = f"prce_nom_{sector}_NA_{fuel}_NA_NA_ndlrpmbtu"
    series_name = f"Energy Prices : {SECTOR_DESC[sector]} : {FUEL_DESC[fuel]}"

    records = []
    for col_idx, yr in years:
        v = df.iloc[target_row, col_idx]
        if not isinstance(v, (int, float)) or pd.isna(v):
            continue
        # AEOs are released in the spring of the named year, but H=0 (the
        # year before release) is still an estimate, not a final historic
        # value. The API marks years <= vintage - 2 as HISTORIC.
        history = "HISTORIC" if yr < vintage - 1 else "PROJECTION"
        records.append({
            "period": yr,
            "history": history,
            "scenario": f"ref{vintage}",
            "scenarioDescription": SCENARIO_DESC,
            "tableId": TABLE_ID,
            "tableName": TABLE_NAME,
            "seriesId": series_id,
            "seriesName": series_name,
            "regionId": region_code,
            "regionName": region,
            "value": float(v),
            "unit": unit_str,
            "aeo_vintage": vintage,
        })
    return records


def main():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "aeo*_aeotab_*.xls")))
    if not files:
        print(f"No files found in {RAW_DIR}")
        return

    all_records = []
    for path in files:
        m = re.search(r"aeo(\d{4})_", os.path.basename(path))
        if not m:
            print(f"Skipping (no vintage in name): {path}")
            continue
        vintage = int(m.group(1))
        print(f"Parsing AEO{vintage}: {path}")
        try:
            records = parse_file(path, vintage)
            print(f"  -> {len(records)} rows, "
                  f"unit {records[0]['unit'] if records else 'n/a'}")
            all_records.extend(records)
        except Exception as e:
            print(f"  FAILED: {e}")

    out_df = pd.DataFrame(all_records, columns=COLUMNS)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    out_df.to_csv(OUT_PATH, index=False)
    print(f"\nWrote {len(out_df)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()