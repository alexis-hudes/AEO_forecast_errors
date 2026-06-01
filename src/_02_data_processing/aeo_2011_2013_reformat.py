"""
Parse AEO 2011-2013 Energy Prices by Sector and Source CSVs and convert them
to long-format CSV matching the format of more recent (2014+) AEO data.

These are the vintages between the .xls archive era (handled by the
1998-2010 script) and the EIA API era (2014+). They were downloaded from
the EIA data browser as CSVs and are parsed directly here rather than
re-downloaded.

Pulls settings directly from config.py:
  - sector      (e.g. 'Electric Power')      -> matched against col 0 of CSV
  - sector_aeo  (e.g. 'elep')                -> used in reconstructed seriesId
  - fuel        (e.g. 'Natural Gas')         -> matched against col 0 of CSV
  - fuel_aeo    (e.g. 'ng')                  -> used in reconstructed seriesId
  - value       ('real' or 'nom')
  - region      (e.g. 'United States')       -> for output regionName
  - region_code (e.g. '1-0')                 -> filter against URL in CSV
  - region_shorthand, region_abbrv

The CSV labels follow the AEO 2010+ vocabulary -- 'Liquefied Petroleum Gases',
'Distillate Fuel Oil', 'Steam Coal', etc. -- which doesn't exactly match the
config.py `fuel` strings. FUEL_LABEL_OVERRIDES translates the config value to
the label that appears in the file.
"""

import csv
import os
import re
from collections import defaultdict
from config import (
    sector, sector_aeo, fuel, fuel_aeo, value,
    region, region_code, region_shorthand, region_abbrv,
)

# ---------------------------------------------------------------------------
# Translate config `fuel` to the label the CSV actually uses. Add an entry
# here whenever the config name differs from the CSV's spelling.
#
# A value can be a plain string (apply to every vintage) or a dict keyed by
# AEO vintage with a "default" fallback (lets the override change at a known
# vintage boundary). Propane is vintage-dependent: AEO 2011-2012 reported it
# as 'Liquefied Petroleum Gases'; AEO 2013 onward labels the row 'Propane'
# directly, matching the 2014+ API.
# ---------------------------------------------------------------------------
FUEL_LABEL_OVERRIDES = {
    "Distillate Fuel": "Distillate Fuel Oil",
    "Coal":            "Steam Coal",          # only under Electric Power
    "Propane": {
        2011:      "Liquefied Petroleum Gases",
        2012:      "Liquefied Petroleum Gases",
        "default": "Propane",
    },
}


def resolve_fuel_label(fuel, vintage):
    """Return the CSV label to match for this config `fuel` at this AEO
    `vintage`. Falls through to `fuel` itself if no override exists."""
    override = FUEL_LABEL_OVERRIDES.get(fuel)
    if override is None:
        return fuel
    if isinstance(override, str):
        return override
    return override.get(vintage, override.get("default", fuel))

# ---------------------------------------------------------------------------
# Sector labels we need to recognise as "block boundaries" while parsing.
# These are CSV-structure artifacts (not user-configurable), so they stay here.
# ---------------------------------------------------------------------------
SECTOR_BLOCK_LABELS = {
    "Residential", "Commercial", "Industrial",
    "Transportation", "Electric Power",
    "Average Price to All Users",
    "Non-Renewable Energy Expenditures by Sector",
    "Prices in Nominal Dollars",
}

# ---------------------------------------------------------------------------
# Input files
# ---------------------------------------------------------------------------
files = [
    f"data/raw/AEO/aeo_2011_2013_manual_download/Energy_Prices_by_Sector_and_Source_2011_{region_abbrv}.csv",
    f"data/raw/AEO/aeo_2011_2013_manual_download/Energy_Prices_by_Sector_and_Source_2012_{region_abbrv}.csv",
    f"data/raw/AEO/aeo_2011_2013_manual_download/Energy_Prices_by_Sector_and_Source_2013_{region_abbrv}.csv",
]

OUTPUT_FIELDS = [
    "period", "history", "scenario", "scenarioDescription",
    "tableId", "tableName", "seriesId", "seriesName",
    "regionId", "regionName", "value", "unit", "aeo_vintage",
]

print(f"Extracting: sector='{sector}' | fuel='{fuel}' | value='{value}'")
print(f"Region: {region} ({region_code})\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_url_metadata(url):
    """Extract tableId, aeo_vintage, scenario, regionId from the EIA URL."""
    meta = {}
    m = re.search(r"[?&]id=(\d+)-AEO(\d{4})", url)
    if m:
        meta["tableId"]     = int(m.group(1))
        meta["aeo_vintage"] = int(m.group(2))

    m = re.search(r"[?&]cases=(ref\d{4})", url, re.IGNORECASE)
    meta["scenario"] = m.group(1).lower() if m else f"ref{meta.get('aeo_vintage', '')}"

    m = re.search(r"[?&]region=([\d-]+)", url)
    meta["regionId"] = m.group(1) if m else region_code

    return meta


def build_series_id(raw_api_key, pub_year):
    """
    Return a normalised lowercase seriesId.
    If the CSV row contains an API key, parse it; otherwise reconstruct from config.

    Reconstructed dollar-year suffix follows AEO convention: y{pub_year - 2}dlrpmmbtu
      AEO2011 -> y09, AEO2012 -> y10, AEO2013 -> y11
    """
    if raw_api_key:
        m = re.search(r"REF\d{4}\.(PRCE[^.]+)(?:\.A)?$", raw_api_key, re.IGNORECASE)
        return m.group(1).lower() if m else raw_api_key.lower()

    value_seg = "real" if value == "real" else "nom"
    suffix    = f"y{(pub_year - 2) % 100:02d}dlrpmmbtu"
    return (
        f"prce_{value_seg}_{sector_aeo}_{region_shorthand}_"
        f"{fuel_aeo}_NA_NA_{suffix}"
    )


def find_target_row(all_rows, header_idx, year_cols, fuel_label):
    """Walk the CSV rows looking for `sector` > `fuel_label` in the correct
    price block.

    Some older files (AEO2011) use a two-row format per fuel:
      row 1: fuel label  -- label only, values blank
      row 2: "Reference case" -- actual numeric values
    Other files carry values directly on the fuel label row.

    Also: the "real" and "nominal" price blocks share the same sector/fuel
    labels, so we stop at the "Prices in Nominal Dollars" header if
    value == "real", or skip to it if value == "nom".
    """
    in_target_sector = False
    fuel_label_found = False
    in_nominal_block = False

    for row in all_rows[header_idx + 1:]:
        if not row:
            continue
        label = row[0].strip()

        # Track nominal block boundary
        if label == "Prices in Nominal Dollars":
            in_nominal_block = True
            in_target_sector = False
            fuel_label_found = False
            continue

        # If we only want real prices, stop before the nominal block.
        # If we only want nominal prices, skip until we're inside it.
        if value == "real" and in_nominal_block:
            return None
        if value == "nom" and not in_nominal_block:
            continue

        # Detect entering the target sector
        if label == sector:
            in_target_sector = True
            fuel_label_found = False
            continue

        if not in_target_sector:
            continue

        # Hit a different sector header -> we've left the target block
        # without finding the fuel
        if label in SECTOR_BLOCK_LABELS:
            return None

        # Match the target fuel label
        if label == fuel_label:
            fuel_label_found = True
            has_data = any(
                row[idx].strip()
                for idx in year_cols.values()
                if idx < len(row)
            )
            if has_data:
                return row  # standard single-row format

        # AEO2011-style two-row fallback: data lives on a "Reference case" sub-row
        if fuel_label_found and label == "Reference case":
            return row

    return None


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
rows = []

for filepath in files:
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        all_rows = list(csv.reader(f))

    if not all_rows:
        print(f"WARNING: {filepath} is empty -- skipping")
        continue

    table_name = all_rows[0][0].strip()
    url        = all_rows[1][0].strip() if len(all_rows) > 1 else ""
    meta       = parse_url_metadata(url)

    if "aeo_vintage" not in meta:
        print(f"WARNING: Could not parse vintage from URL in {filepath} -- skipping")
        continue

    if meta["regionId"] != region_code:
        print(f"  Skipping {filepath}: region {meta['regionId']} != config {region_code}")
        continue

    aeo_vintage = meta["aeo_vintage"]
    fuel_label  = resolve_fuel_label(fuel, aeo_vintage)
    print(f"  AEO{aeo_vintage}: matching CSV label '{fuel_label}' for fuel '{fuel}'")

    # Find header row (column 3 == "units")
    header_idx = next(
        (i for i, r in enumerate(all_rows)
         if len(r) > 3 and r[3].strip().lower() == "units"),
        None
    )
    if header_idx is None:
        print(f"WARNING: Could not find header row in {filepath}")
        continue

    # Extract year columns
    year_cols = {
        int(h.strip().strip('"')): idx
        for idx, h in enumerate(all_rows[header_idx])
        if re.match(r"^\d{4}$", h.strip().strip('"'))
    }

    target_row = find_target_row(all_rows, header_idx, year_cols, fuel_label)
    if target_row is None:
        print(f"WARNING: Could not find {sector} > {fuel_label} in {filepath}")
        continue

    # Extract series metadata from the matched row
    series_name_raw = target_row[1].strip() if len(target_row) > 1 else ""
    raw_api_key     = target_row[2].strip() if len(target_row) > 2 else ""
    unit            = target_row[3].strip() if len(target_row) > 3 else ""

    series_name = re.sub(r":\s*Reference case$", "", series_name_raw).strip()
    series_id   = build_series_id(raw_api_key, aeo_vintage)

    # Reshape wide -> long
    for year, col_idx in year_cols.items():
        if col_idx >= len(target_row):
            continue
        raw = target_row[col_idx].strip()
        if not raw:
            continue
        try:
            value_num = float(raw)
        except ValueError:
            continue

        rows.append({
            "period":              year,
            "history":             "HISTORIC" if year + 1 < aeo_vintage else "PROJECTION",
            "scenario":            meta["scenario"],
            "scenarioDescription": "Reference case",
            "tableId":             meta["tableId"],
            "tableName":           table_name,
            "seriesId":            series_id,
            "seriesName":          series_name,
            "regionId":            meta["regionId"],
            "regionName":          region,         # straight from config
            "value":               round(value_num, 6),
            "unit":                unit,
            "aeo_vintage":         aeo_vintage,
        })

# Sort by vintage (asc), then period (desc)
rows.sort(key=lambda r: (r["aeo_vintage"], -r["period"]))

OUT_DIR = "data/raw/AEO"
out_name = os.path.join(
    OUT_DIR,
    f"AEO_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_2011_2013.csv",
)
os.makedirs(OUT_DIR, exist_ok=True)
with open(out_name, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
    writer.writeheader()
    writer.writerows(rows)

print(f"Done. {len(rows)} rows written to {out_name}\n")

# Summary
summary = defaultdict(lambda: {"HISTORIC": 0, "PROJECTION": 0, "unit": ""})
for r in rows:
    summary[r["aeo_vintage"]][r["history"]] += 1
    summary[r["aeo_vintage"]]["unit"] = r["unit"]

for yr in sorted(summary):
    d = summary[yr]
    print(f"  AEO{yr} ({d['unit']}): {d['HISTORIC']} historic, {d['PROJECTION']} projection years")