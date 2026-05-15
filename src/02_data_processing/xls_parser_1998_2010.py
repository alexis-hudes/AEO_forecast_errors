"""
Parse AEO 1998-2010 archive .xls supplement workbooks and convert them to
long-format CSV matching the schema of AEO_real_elep_ng_US.csv.

Selections are imported from config.py:
    sector, fuel, value      -- what series to pull
    region, region_abbrv,
    region_code, table_num   -- which region table to read

Each archive workbook holds multiple tables (Table 1, Table 2, ...) stacked
vertically in a single sheet. `table_num` says which one carries the wanted
region; we look for a row whose first column starts with 'Table N.' and only
parse between that and the next table header.
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
    region_abbrv, sector, fuel, value, region_code, region, table_num
)

RAW_DIR = f"data/raw/aeo_1998_to_2010"
OUT_PATH = f"data/raw/AEO_{value}_{sector}_{fuel}_{region_abbrv}_1998_2010.csv"

COLUMNS = [
    "period", "history", "scenario", "scenarioDescription",
    "tableId", "tableName", "seriesId", "seriesName",
    "regionId", "regionName", "value", "unit", "aeo_vintage",
]

# Section + fuel labels keyed by config strings
SECTION_PATTERNS = {
    "elep": ["electric power", "electric generator"],
    "resd": ["residential"],
    "comm": ["commercial"],
    "indu": ["industrial"],
    "trn":  ["transportation"],
}
FUEL_LABELS = {
    "ng":   ["natural gas"],
    "coal": ["steam coal"],   
    "petr": ["petroleum products"],
    "elc":  ["electricity"],
}

# Mapping from config to API metadata fields so the CSV is byte-compatible
# with the 2014+ pipeline.
TABLE_ID = 3
TABLE_NAME = "Energy Prices by Sector and Source"
SCENARIO_DESC = "Reference case"
SECTOR_DESC = {"elep": "Electric Power", "resd": "Residential",
               "comm": "Commercial", "indu": "Industrial",
               "trn": "Transportation"}
FUEL_DESC = {"ng": "Natural Gas", "coal": "Coal",
             "petr": "Petroleum", "elc": "Electricity"}


def _norm(s):
    """Lowercase + strip whitespace + strip trailing dots (1998-2004 labels
    end with long runs of dots like 'Natural Gas..............')."""
    if not isinstance(s, str):
        return ""
    return s.strip().rstrip(".").strip().lower()


def _strip_footnote(s):
    """Strip trailing footnote markers like '2/' or '11/' from a normalized
    label. 'natural gas 2/' -> 'natural gas'."""
    return re.sub(r"\s*\d+/\s*$", "", s).strip()


def _to_year(v):
    """Coerce a cell to a year int in [1995, 2050], or None.
    AEO 2009 stores years as strings; older AEOs store them as floats."""
    if isinstance(v, (int, float)) and not pd.isna(v):
        if 1995 <= v <= 2050 and float(v).is_integer():
            return int(v)
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit() and 1995 <= int(s) <= 2050:
            return int(s)
    return None


def detect_label_col(df, start_row, end_row):
    """Pick the leftmost column whose cells are mostly strings inside the
    given row range. AEO 1998-2009 supplement files have labels in col 0;
    the single-table 2010-style files have a blank col 0 and labels in col 1.
    Auto-detection keeps the parser working across both layouts."""
    best_col, best_count = 0, -1
    for c in range(min(3, df.shape[1])):
        count = sum(
            1 for v in df.iloc[start_row:end_row, c]
            if isinstance(v, str) and v.strip()
        )
        if count > best_count:
            best_count = count
            best_col = c
    return best_col


def find_tables(df):
    """Return list of (table_number, start_row) for every 'Table N.' header
    found in column 0 (or col 1, if col 0 is empty). Sorted by start_row."""
    pat = re.compile(r"^\s*Table\s+(\d+)[A-Za-z]?\s*\.", re.IGNORECASE)
    out = []
    for i in range(len(df)):
        for c in range(min(2, df.shape[1])):
            v = df.iloc[i, c]
            if isinstance(v, str):
                m = pat.search(v)
                if m:
                    out.append((int(m.group(1)), i))
                    break
    out.sort(key=lambda x: x[1])
    return out


def table_range(df, want_table):
    """Find rows [start, end) covering Table `want_table`. If only one table
    is found in the file (older single-table layout), the whole sheet is the
    range."""
    tabs = find_tables(df)
    if not tabs:
        return 0, len(df)
    # Locate the target
    for idx, (num, start) in enumerate(tabs):
        if num == want_table:
            end = tabs[idx + 1][1] if idx + 1 < len(tabs) else len(df)
            return start, end
    raise ValueError(
        f"Table {want_table} not found in workbook "
        f"(found tables: {[n for n, _ in tabs]})"
    )


REGION_ALIASES = {
    "United States": ["united states", "us average"],
    "New England":   ["new england"],
}


def verify_region(df, start_row, label_col, expected_region):
    """The first few rows of a table list the title, dollar-year footnote,
    and region. Sanity-check that the expected region appears."""
    aliases = REGION_ALIASES.get(expected_region, [_norm(expected_region)])
    for i in range(start_row, min(start_row + 5, len(df))):
        v = df.iloc[i, label_col]
        if isinstance(v, str):
            low = _norm(v)
            if any(a in low for a in aliases):
                return True
    return False


def find_base_year(df, start_row, end_row):
    """Find the base year from header text like '(2002 Dollars per Million
    Btu)' or '(2008 dollars per million Btu, unless otherwise noted)'. This
    is the real-dollars base year; the nominal sub-table (when present)
    reports actual nominal $ for each forecast year."""
    pat = re.compile(r"\(\s*(\d{4})\s*dollars", re.IGNORECASE)
    for i in range(start_row, end_row):
        for c in range(min(3, df.shape[1])):
            v = df.iloc[i, c]
            if isinstance(v, str):
                m = pat.search(v)
                if m:
                    yr = int(m.group(1))
                    if 1990 <= yr <= 2030:
                        return yr
    return None


def find_year_row(df, label_col, start_row, end_row):
    """First row in [start, end) with >=10 year-like cells in columns AFTER
    label_col. Accepts both numeric and string year encodings.

    Excludes growth-rate columns. In older AEOs (1998/2004) the rightmost
    column is a multi-year growth rate, labeled with a two-row header like
    '1996-' / '2020' or '2002-' / '2025'. The second row would otherwise be
    picked up as a year; we drop any year column whose row-above cell is a
    string ending in '-'."""
    for i in range(start_row, end_row):
        years = []
        for c in range(label_col + 1, df.shape[1]):
            y = _to_year(df.iloc[i, c])
            if y is None:
                continue
            # Check the cell above for a 'YYYY-' growth-range marker
            if i > 0:
                above = df.iloc[i - 1, c]
                if isinstance(above, str) and above.strip().endswith("-"):
                    continue
            years.append((c, y))
        if len(years) >= 10:
            return i, years
    return None, None


def find_nominal_header(df, label_col, start_row, end_row):
    """In AEO 2008+, the same table holds a 'Prices in Nominal Dollars'
    sub-section below the real-$ data. Return its row, or None."""
    for i in range(start_row, end_row):
        v = df.iloc[i, label_col]
        if isinstance(v, str) and "nominal dollars" in _norm(v):
            return i
    return None


# All section names we might transition through, used to detect section
# boundaries in older AEOs where the section row carries the sector total
# (e.g., 'Residential.....  12.9364  12.8258 ...').
ALL_SECTION_NAMES = [
    "residential", "commercial", "industrial", "transportation",
    "electric power", "electric generator",
    "average end-use energy", "average price to all users",
    "non-renewable energy expenditures",
]


def is_section_header(df, row_idx, label_col):
    """A section header has a string label. Two patterns:

    1. Pure header: a label cell with no numerics in the row (post-2008
       AEO format, where the section name sits alone above its fuels).
    2. Totals header: the label matches one of our known section names
       even though the row carries the sector total (1998-2007 format,
       where 'Residential..........' has both the label and totals).
    """
    label = df.iloc[row_idx, label_col]
    if not isinstance(label, str) or not label.strip():
        return False

    low = _strip_footnote(_norm(label))
    if any(low == s or low.startswith(s) for s in ALL_SECTION_NAMES):
        return True

    # Fallback: a label-only row with no numerics
    for c in range(label_col + 1, df.shape[1]):
        v = df.iloc[row_idx, c]
        if isinstance(v, (int, float)) and not pd.isna(v):
            return False
    return True


def find_target_row(df, search_start, search_end, label_col,
                    section_patterns, fuel_labels):
    """Find the fuel row inside the target section. Section start is detected
    by a section-header row matching one of `section_patterns`; we exit at the
    next section header, so a missing fuel doesn't drop us into the wrong
    section."""
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
                # Left the target section without finding the fuel
                break
            else:
                continue

        if in_section:
            stem = _strip_footnote(low)
            # Prefer exact match, fall back to substring
            for fl in fuel_labels:
                if fl == stem:
                    return i
            for fl in fuel_labels:
                if fl in stem:
                    return i
    return None


def parse_file(path, vintage):
    df = pd.read_excel(path, engine="xlrd", header=None)

    # Slice to the table the user wants. For older multi-table supplement
    # workbooks (1998-2009) `table_num` selects the region. Single-table
    # files (aeotab_20-style) only contain one table and we use the whole
    # sheet.
    t_start, t_end = table_range(df, table_num)
    label_col = detect_label_col(df, t_start, t_end)

    if not verify_region(df, t_start, label_col, region):
        # Not fatal -- just warn -- because some older files spell the region
        # differently or omit it.
        print(f"    WARNING: region {region!r} not confirmed in table header")

    base_year = find_base_year(df, t_start, t_end)
    if base_year is None:
        raise ValueError(f"{path}: could not find base year in table {table_num}")

    year_row, years = find_year_row(df, label_col, t_start, t_end)
    if year_row is None:
        raise ValueError(
            f"{path}: could not find year header row in table {table_num}"
        )

    nominal_row = find_nominal_header(df, label_col, year_row + 1, t_end)
    if value == "real":
        section_start = year_row + 1
        section_end = nominal_row if nominal_row else t_end
        unit_str = f"{base_year} $/MMBtu"
    elif value == "nom":
        if nominal_row is None:
            raise ValueError(
                f"{path}: no 'Prices in Nominal Dollars' section "
                f"(AEO {vintage} only reports real $)"
            )
        section_start = nominal_row + 1
        section_end = t_end
        unit_str = "nominal $/MMBtu"
    else:
        raise ValueError(f"unknown value type: {value!r}")

    section_patterns = SECTION_PATTERNS[sector]
    fuel_labels = FUEL_LABELS[fuel]
    target_row = find_target_row(
        df, section_start, section_end, label_col,
        section_patterns, fuel_labels,
    )
    if target_row is None:
        raise ValueError(
            f"{path}: could not find {SECTOR_DESC[sector]} -> "
            f"{FUEL_DESC[fuel]} row"
        )

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
        # AEOs are released in the spring of the named year, but the year before the release
        # are marked as PROJECTION. year <= vintage - 2 are marked as HISTORIC
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
    files = sorted(glob.glob(os.path.join(RAW_DIR, "aeo*.xls")))
    if not files:
        print(f"No files found in {RAW_DIR}")
        return

    all_records = []
    for path in files:
        m = re.search(r"aeo(\d{4})", os.path.basename(path))
        if not m:
            print(f"Skipping (no vintage in name): {path}")
            continue
        vintage = int(m.group(1))
        print(f"Parsing AEO{vintage}: {path}")
        try:
            records = parse_file(path, vintage)
            unit = records[0]["unit"] if records else "n/a"
            print(f"  -> {len(records)} rows, unit {unit}")
            all_records.extend(records)
        except Exception as e:
            print(f"  FAILED: {e}")

    out_df = pd.DataFrame(all_records, columns=COLUMNS)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    out_df.to_csv(OUT_PATH, index=False)
    print(f"\nWrote {len(out_df)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()