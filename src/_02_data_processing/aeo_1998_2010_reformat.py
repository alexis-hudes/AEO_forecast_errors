"""
Parse AEO 1998-2010 archive .xls supplement workbooks and convert them to
long-format CSV matching the format of more recent (2014+) AEO data.

Selections are imported from config.py:
    sector, sector_aeo,
    fuel, fuel_aeo, value         -- what series to pull
    region, region_abbrv,         -- used for labelling
    region_code, table_num        -- which region table to read

Each archive workbook holds multiple tables (Table 1, Table 2, ...) stacked
vertically in a single sheet. `table_num` says which one carries the wanted
region; we locate every 'Table N.' header and parse only between the chosen
header and the next one.

Most files (1998-2009) put labels in column 0. AEO 2010 leaves column 0
empty and puts labels in column 1. detect_label_col handles the difference.
"""
import os
import re
import sys
import glob
import pandas as pd
from config import region_abbrv, sector, sector_aeo, fuel, fuel_aeo, value, region_code, region, table_num


RAW_DIR = "data/raw/AEO/aeo_1998_to_2010"
OUT_PATH = (
    f"data/raw/AEO/AEO_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_1998_2010.csv"
)

COLUMNS = [
    "period", "history", "scenario", "scenarioDescription",
    "tableId", "tableName", "seriesId", "seriesName",
    "regionId", "regionName", "value", "unit", "aeo_vintage",
]

# Substring patterns used to recognize section header rows. Keys must match
# `sector_aeo` values produced by config.py.
SECTION_PATTERNS = {
    "elep": ["electric power", "electric generator"],
    "resd": ["residential"],
    "comm": ["commercial"],
    "idal": ["industrial"],
    "trn":  ["transportation"],
}

# Substring patterns used to recognize fuel rows. Keys must match `fuel_aeo`
# values produced by config.py. Substrings are chosen to match across the
# 1998-2010 vocabulary drift (e.g. 'Distillate Fuel' in 1998 vs 'Distillate
# Fuel Oil' in 2010).
FUEL_LABELS = {
    "ng":   ["natural gas"],
    "coal": ["steam coal"],          # under Electric Power; industrial uses other coal names
    "dfo":  ["distillate fuel"],
    "prop": ["liquefied petroleum"],  # 'Liquefied Petroleum Gas' (1998) / 'Gases' (2010+)
    "elc":  ["electricity"],
}

# Section names we might transition through. Used to detect section
# boundaries in older AEOs (1998-2007) where the section row carries the
# sector total -- e.g. 'Residential.....  12.94  12.83 ...' -- rather than
# sitting alone above its fuels.
ALL_SECTION_NAMES = [
    "residential", "commercial", "industrial", "transportation",
    "electric power", "electric generator",
    "average end-use energy", "average price to all users",
    "non-renewable energy expenditures",
]

# Constants for byte-compatibility with the 2014+ API pipeline.
TABLE_ID = 3
TABLE_NAME = "Energy Prices by Sector and Source"
SCENARIO_DESC = "Reference case"


def _norm(s):
    """Lowercase + strip whitespace + strip trailing dots. 1998-2004 labels
    end with leader dots like 'Natural Gas..............'."""
    if not isinstance(s, str):
        return ""
    return s.strip().rstrip(".").strip().lower()


def _strip_footnote(s):
    """Strip trailing footnote markers like '2/' or '11/' from a normalized
    label. 'natural gas 2/' -> 'natural gas'."""
    return re.sub(r"\s*\d+/\s*$", "", s).strip()


def _to_year(v):
    """Coerce a cell to a year int in [1995, 2050], or None. AEO 2009 stores
    years as strings; older AEOs store them as floats."""
    if isinstance(v, (int, float)) and not pd.isna(v):
        if 1995 <= v <= 2050 and float(v).is_integer():
            return int(v)
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit() and 1995 <= int(s) <= 2050:
            return int(s)
    return None


def detect_label_col(df):
    """Pick the leftmost column whose cells are mostly strings. AEO 1998-2009
    use column 0; AEO 2010 leaves column 0 empty and uses column 1."""
    best_col, best_count = 0, -1
    for c in range(min(3, df.shape[1])):
        count = sum(
            1 for v in df.iloc[:, c]
            if isinstance(v, str) and v.strip()
        )
        if count > best_count:
            best_count = count
            best_col = c
    return best_col


def table_range(df, label_col, want_table):
    """Find rows [start, end) covering Table `want_table`. Returns the full
    sheet if only one table is present (older single-table layout)."""
    pat = re.compile(r"^\s*Table\s+(\d+)[A-Za-z]?\s*\.", re.IGNORECASE)
    tabs = []
    for i in range(len(df)):
        v = df.iloc[i, label_col]
        if isinstance(v, str):
            m = pat.search(v)
            if m:
                tabs.append((int(m.group(1)), i))
    if not tabs:
        return 0, len(df)
    for idx, (num, start) in enumerate(tabs):
        if num == want_table:
            end = tabs[idx + 1][1] if idx + 1 < len(tabs) else len(df)
            return start, end
    raise ValueError(
        f"Table {want_table} not found "
        f"(available: {[n for n, _ in tabs]})"
    )


def find_base_year(df, label_col, start_row, end_row):
    """Find the real-dollars base year from text like '(2002 Dollars per
    Million Btu)' or '(2008 dollars per million Btu, unless otherwise
    noted)'."""
    pat = re.compile(r"\(\s*(\d{4})\s*dollars", re.IGNORECASE)
    for i in range(start_row, end_row):
        v = df.iloc[i, label_col]
        if isinstance(v, str):
            m = pat.search(v)
            if m and 1990 <= int(m.group(1)) <= 2030:
                return int(m.group(1))
    return None


def find_year_row(df, label_col, start_row, end_row):
    """First row with >=10 year-like cells in columns AFTER label_col,
    accepting both numeric and string year encodings.

    The rightmost column in older AEOs (1998/2004) is a growth rate with a
    two-row header like '1996-' / '2020' or '2002-' / '2025'. The second
    row would otherwise be picked up as a year; we drop any column whose
    row-above cell ends in '-'."""
    for i in range(start_row, end_row):
        years = []
        for c in range(label_col + 1, df.shape[1]):
            y = _to_year(df.iloc[i, c])
            if y is None:
                continue
            if i > 0:
                above = df.iloc[i - 1, c]
                if isinstance(above, str) and above.strip().endswith("-"):
                    continue
            years.append((c, y))
        if len(years) >= 10:
            return i, years
    return None, None


def find_nominal_header(df, label_col, start_row, end_row):
    """In AEO 2008+, the table holds a 'Prices in Nominal Dollars' sub-
    section below the real-$ data. Return its row, or None."""
    for i in range(start_row, end_row):
        v = df.iloc[i, label_col]
        if isinstance(v, str) and "nominal dollars" in _norm(v):
            return i
    return None


def is_section_header(df, label_col, row_idx):
    """A section header has a string label. Two patterns:
    1. Pure header: a label cell with no numerics in the row (post-2008 AEO
       format, where the section name sits alone above its fuels).
    2. Totals header: the label matches one of our known section names even
       though the row carries the sector total (1998-2007 format, where
       'Residential..........' has both the label and totals).
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


def find_target_row(df, label_col, search_start, search_end,
                    section_patterns, fuel_labels):
    """Find the fuel row inside the target section. Section start is detected
    by a section-header row matching one of `section_patterns`; we exit at
    the next section header, so a missing fuel doesn't drop us into the
    wrong section."""
    in_section = False
    for i in range(search_start, search_end):
        label = df.iloc[i, label_col]
        if not isinstance(label, str):
            continue
        low = _norm(label)
        if not low:
            continue
        if is_section_header(df, label_col, i):
            if any(p in low for p in section_patterns):
                in_section = True
            elif in_section:
                break  # left the target section without finding the fuel
            continue
        if in_section:
            stem = _strip_footnote(low)
            if any(fl in stem for fl in fuel_labels):
                return i
    return None


def parse_file(path, vintage):
    df = pd.read_excel(path, engine="xlrd", header=None)

    label_col = detect_label_col(df)
    t_start, t_end = table_range(df, label_col, table_num)

    base_year = find_base_year(df, label_col, t_start, t_end)
    if base_year is None:
        raise ValueError(f"{path}: could not find base year")

    year_row, years = find_year_row(df, label_col, t_start, t_end)
    if year_row is None:
        raise ValueError(f"{path}: could not find year header row")

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

    target_row = find_target_row(
        df, label_col, section_start, section_end,
        SECTION_PATTERNS[sector_aeo], FUEL_LABELS[fuel_aeo],
    )
    if target_row is None:
        raise ValueError(
            f"{path}: could not find {sector} -> {fuel} row"
        )

    if value == "real":
        series_id = (
            f"prce_real_{sector_aeo}_NA_{fuel_aeo}_NA_NA_"
            f"y{str(base_year)[-2:]}dlrpmmbtu"
        )
    else:
        series_id = f"prce_nom_{sector_aeo}_NA_{fuel_aeo}_NA_NA_ndlrpmbtu"
    series_name = f"Energy Prices : {sector} : {fuel}"

    records = []
    for col_idx, yr in years:
        v = df.iloc[target_row, col_idx]
        if not isinstance(v, (int, float)) or pd.isna(v):
            continue
        # AEOs are released in spring of the named year; the year before
        # release (H=0) is listed as PROJECTION, before that is HISTORIC
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


files = sorted(glob.glob(os.path.join(RAW_DIR, "aeo*.xls")))

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
