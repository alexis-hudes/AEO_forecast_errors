import csv
import re
import os

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------
import importlib.util, sys

config_path = os.path.join(os.path.dirname(__file__), "config.py")
spec = importlib.util.spec_from_file_location("config", config_path)
cfg  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)

# ---------------------------------------------------------------------------
# Mappings: config shorthand -> CSV label used in the files
# ---------------------------------------------------------------------------

# sector shorthand -> the header label that appears in column 0 of the CSV
SECTOR_LABEL = {
    "elep": "Electric Power",
    "res":  "Residential",
    "com":  "Commercial",
    "ind":  "Industrial",
    "trn":  "Transportation",
}

# fuel shorthand -> the fuel label that appears in column 0 of the CSV
# Note: some fuels only exist under certain sectors
FUEL_LABEL = {
    "ng":   "Natural Gas",
    "dist": "Distillate Fuel Oil",
    "res":  "Residual Fuel Oil",
    "prop": "Propane",
    "elec": "Electricity",
    "coal": "Steam Coal",        # Electric Power only
}

# All top-level sector labels — used to detect when we've left a sector block
ALL_SECTOR_LABELS = set(SECTOR_LABEL.values()) | {
    "Average Price to All Users",
    "Non-Renewable Energy Expenditures by Sector",
    "Prices in Nominal Dollars",
}

# ---------------------------------------------------------------------------
# Region lookup
# ---------------------------------------------------------------------------
REGION_NAMES = {
    "1-0": "United States",
    "1-1": "New England",
    "1-2": "Middle Atlantic",
    "1-3": "East North Central",
    "1-4": "West North Central",
    "1-5": "South Atlantic",
    "1-6": "East South Central",
    "1-7": "West South Central",
    "1-8": "Mountain",
    "1-9": "Pacific",
}

# ---------------------------------------------------------------------------
# Dollar-year suffix for reconstructing seriesId in older files (no API key)
# ---------------------------------------------------------------------------
DOLLAR_YEAR_SUFFIX = {
    2010: "y08dlrpmmbtu",
    2011: "y09dlrpmmbtu",
    2012: "y10dlrpmmbtu",
    2013: "y11dlrpmmbtu",
    2014: "y12dlrpmmbtu",
}

# ---------------------------------------------------------------------------
# Input files  (no vintage or region hard-coded — all extracted from each file)
# ---------------------------------------------------------------------------
files = [
    "Energy_Prices_by_Sector_and_Source_2013.csv",
    "Energy_Prices_by_Sector_and_Source_2012.csv",
    "Energy_Prices_by_Sector_and_Source_2011.csv",
    "Energy_Prices_by_Sector_and_Source_2010.csv",
    "Energy_Prices_by_Sector_and_Source_2014.csv",
]

OUTPUT_FIELDS = [
    "period", "history", "scenario", "scenarioDescription",
    "tableId", "tableName", "seriesId", "seriesName",
    "regionId", "regionName", "value", "unit", "aeo_vintage",
]

# ---------------------------------------------------------------------------
# Resolve config settings -> labels and seriesId fragment
# ---------------------------------------------------------------------------
target_sector = SECTOR_LABEL.get(cfg.sector)
target_fuel   = FUEL_LABEL.get(cfg.fuel)

if target_sector is None:
    raise ValueError(f"Unknown sector '{cfg.sector}'. Choose from: {list(SECTOR_LABEL)}")
if target_fuel is None:
    raise ValueError(f"Unknown fuel '{cfg.fuel}'. Choose from: {list(FUEL_LABEL)}")

print(f"Extracting: sector='{target_sector}' | fuel='{target_fuel}' | value='{cfg.value}'")
print(f"Region: {cfg.region} ({cfg.region_code})\n")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_url_metadata(url):
    """
    Extract tableId, aeo_vintage, pub_year, scenario, regionId from the
    EIA data browser URL in row 1 of each CSV.

    Full URL example:
      https://.../#/?id=3-AEO2014&region=1-0&cases=ref2014&...
    Minimal URL example:
      https://.../#/?id=3-AEO2011&sourcekey=0
    """
    meta = {}
    m = re.search(r"[?&]id=(\d+)-AEO(\d{4})", url)
    if m:
        meta["tableId"]     = int(m.group(1))
        meta["aeo_vintage"] = int(m.group(2))
        meta["pub_year"]    = int(m.group(2))

    m = re.search(r"[?&]cases=(ref\d{4})", url, re.IGNORECASE)
    meta["scenario"] = m.group(1).lower() if m else f"ref{meta.get('aeo_vintage', '')}"

    m = re.search(r"[?&]region=([\d-]+)", url)
    meta["regionId"] = m.group(1) if m else cfg.region_code   # fall back to config

    return meta


def parse_series_id(raw_api_key, pub_year, sector_code, fuel_code, value_type):
    """
    Return a normalised lowercase seriesId.
    - If the file contains an API key, parse it directly.
    - Otherwise reconstruct from config values and the dollar-year suffix.

    Reconstructed pattern:
      prce_<value>_<sector>_<region>_<fuel>_NA_NA_<dollar-year-suffix>
    e.g.:
      prce_ene_elep_NA_ng_NA_NA_y12dlrpmmbtu   (real, AEO2014 convention)
      prce_real_elep_NA_ng_NA_NA_y13dlrpmmbtu  (real, AEO2015+ convention)
    """
    if raw_api_key:
        m = re.search(r"REF\d{4}\.(PRCE[^.]+)(?:\.A)?$", raw_api_key, re.IGNORECASE)
        return m.group(1).lower() if m else raw_api_key.lower()

    # Reconstruct
    # value segment: 'ene' was used in early vintages for real prices;
    # later vintages switched to 'real' / 'nom'
    value_seg = "real" if value_type == "real" else "nom"
    suffix    = DOLLAR_YEAR_SUFFIX.get(pub_year, "dlrpmmbtu")
    region_seg = cfg.region_shorthand  # 'NA' for US, 'neengl' for New England

    return f"prce_{value_seg}_{sector_code}_{region_seg}_{fuel_code}_NA_NA_{suffix}"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
rows = []

for filepath in files:

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        content = f.read()

    all_rows = list(csv.reader(content.splitlines()))

    # Row 0: table name
    table_name = all_rows[0][0].strip() if all_rows else ""

    # Row 1: URL -> metadata
    url  = all_rows[1][0].strip() if len(all_rows) > 1 else ""
    meta = parse_url_metadata(url)

    if "pub_year" not in meta:
        print(f"WARNING: Could not parse vintage from URL in {filepath} — skipping")
        continue

    pub_year    = int(meta["pub_year"])
    aeo_vintage = int(meta["aeo_vintage"])
    table_id    = meta["tableId"]
    scenario    = meta["scenario"]
    region_id   = meta["regionId"]
    region_name = REGION_NAMES.get(region_id, region_id)

    # Skip file if its region doesn't match the config
    if region_id != cfg.region_code:
        print(f"  Skipping {filepath}: region {region_id} != config {cfg.region_code}")
        continue

    # Find header row (column 3 == "units")
    header_row_idx = None
    for i, row in enumerate(all_rows):
        if len(row) > 3 and row[3].strip().lower() == "units":
            header_row_idx = i
            break

    if header_row_idx is None:
        print(f"WARNING: Could not find header row in {filepath}")
        continue

    headers = all_rows[header_row_idx]

    # Extract year columns
    year_cols = {}
    for idx, h in enumerate(headers):
        h_clean = h.strip().strip('"')
        if re.match(r"^\d{4}$", h_clean):
            year_cols[int(h_clean)] = idx

    # --- Navigate to target sector > target fuel ---
    # Some older files (AEO2011) use a two-row format per fuel:
    #   row 1: fuel label  — label only, values blank
    #   row 2: "Reference case" — actual numeric values
    # Other files carry values directly on the fuel label row.
    #
    # Also: the "real" and "nominal" price blocks share the same sector/fuel
    # labels, so we stop at the "Prices in Nominal Dollars" header if
    # value='real', or skip to it if value='nom'.

    in_target_sector  = False
    fuel_label_found  = False
    in_nominal_block  = False
    target_row        = None

    for row in all_rows[header_row_idx + 1:]:
        if not row:
            continue
        label = row[0].strip()

        # Track nominal block boundary
        if label == "Prices in Nominal Dollars":
            in_nominal_block = True
            in_target_sector = False
            fuel_label_found = False
            continue

        # If we only want real prices, stop before the nominal block
        if cfg.value == "real" and in_nominal_block:
            break

        # If we only want nominal prices, skip until we're in that block
        if cfg.value == "nom" and not in_nominal_block:
            if label == target_sector:
                pass  # let it fall through but we'll ignore it below
            continue

        # Detect entering the target sector
        if label == target_sector:
            in_target_sector = True
            fuel_label_found = False
            continue

        if not in_target_sector:
            continue

        # Leaving the sector block
        if label in ALL_SECTOR_LABELS:
            if in_target_sector and fuel_label_found is False:
                # moved past sector without finding the fuel
                break
            in_target_sector = False
            break

        # Match the target fuel label
        if label == target_fuel:
            fuel_label_found = True
            has_data = any(
                row[idx].strip()
                for idx in year_cols.values()
                if idx < len(row)
            )
            if has_data:
                target_row = row   # standard single-row format
                break

        # AEO2011 two-row fallback: data is on "Reference case" sub-row
        if fuel_label_found and label == "Reference case":
            target_row = row
            break

    if target_row is None:
        print(f"WARNING: Could not find {target_sector} > {target_fuel} in {filepath}")
        continue

    # Extract series metadata from the matched row
    series_name_raw = target_row[1].strip() if len(target_row) > 1 else ""
    raw_api_key     = target_row[2].strip() if len(target_row) > 2 else ""
    unit            = target_row[3].strip() if len(target_row) > 3 else ""

    series_name = re.sub(r":\s*Reference case$", "", series_name_raw).strip()
    series_id   = parse_series_id(
        raw_api_key, pub_year, cfg.sector, cfg.fuel, cfg.value
    )

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

        history = "HISTORIC" if int(year)+1 < pub_year else "PROJECTION"

        rows.append({
            "period":              year,
            "history":             history,
            "scenario":            scenario,
            "scenarioDescription": "Reference case",
            "tableId":             table_id,
            "tableName":           table_name,
            "seriesId":            series_id,
            "seriesName":          series_name,
            "regionId":            region_id,
            "regionName":          region_name,
            "value":               round(value_num, 6),
            "unit":                unit,
            "aeo_vintage":         aeo_vintage,
        })

# Sort by vintage (asc), then period (desc)
rows.sort(key=lambda r: (r["aeo_vintage"], -r["period"]))

# Build output filename from config
out_name = f"aeo_{cfg.value}_{cfg.sector}_{cfg.fuel}_{cfg.region_abbrv}.csv"
with open(out_name, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
    writer.writeheader()
    writer.writerows(rows)

print(f"Done. {len(rows)} rows written to {out_name}\n")

from collections import defaultdict
summary = defaultdict(lambda: {"HISTORIC": 0, "PROJECTION": 0, "unit": ""})
for r in rows:
    summary[r["aeo_vintage"]][r["history"]] += 1
    summary[r["aeo_vintage"]]["unit"] = r["unit"]

for yr in sorted(summary):
    d = summary[yr]
    print(f"  AEO{yr} ({d['unit']}): {d['HISTORIC']} historic, {d['PROJECTION']} projection years")