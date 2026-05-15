import csv
import re
import os

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

files = {
    "Energy_Prices_by_Sector_and_Source_2013.csv": "AEO2013",
    "Energy_Prices_by_Sector_and_Source_2012.csv": "AEO2012",
    "Energy_Prices_by_Sector_and_Source_2011.csv": "AEO2011",
    "Energy_Prices_by_Sector_and_Source_2010.csv": "AEO2010",
    "Energy_Prices_by_Sector_and_Source_2014.csv": "AEO2014"}

OUTPUT_FIELDS = [
    "period", "history", "scenario", "scenarioDescription",
    "tableId", "tableName", "seriesId", "seriesName",
    "regionId", "regionName", "value", "unit", "aeo_vintage",
]


# ---------------------------------------------------------------------------
# Helper: parse all metadata from the URL embedded in row 1
# ---------------------------------------------------------------------------
def parse_url_metadata(url):
    """
    Extract tableId, aeo_vintage, pub_year, scenario, regionId from the
    EIA data browser URL in row 1 of each CSV.
    """
    meta = {}

    # tableId and vintage from "id=<tableId>-AEO<year>"
    m = re.search(r"[?&]id=(\d+)-AEO(\d{4})", url)
    if m:
        meta["tableId"] = int(m.group(1))
        meta["aeo_vintage"] = int(m.group(2))
        meta["pub_year"] = int(m.group(2))

    # scenario from "cases=ref<year>" — fall back to "ref<vintage>"
    m = re.search(r"[?&]cases=(ref\d{4})", url, re.IGNORECASE)
    meta["scenario"] = m.group(1).lower() if m else f"ref{meta.get('aeo_vintage', '')}"

    # regionId from "region=<id>" — fall back to "1-0" (United States)
    m = re.search(r"[?&]region=([\d-]+)", url)
    meta["regionId"] = m.group(1) if m else "1-0"

    return meta

DOLLAR_YEAR_SUFFIX = {
    2010: "y08dlrpmmbtu",
    2011: "y09dlrpmmbtu",
    2012: "y10dlrpmmbtu",
    2013: "y11dlrpmmbtu",
    2014: "y12dlrpmmbtu",
}


def parse_series_id(raw_api_key, pub_year):
    """
    Normalise the API key to a short lowercase seriesId.
    If the file has no API key, reconstruct from the known naming pattern.
    """
    if raw_api_key:
        # e.g. "AEO.2014.REF2014.PRCE_ENE_ELEP_NA_NG_NA_NA_Y12DLRPMMBTU.A"
        m = re.search(r"REF\d{4}\.(PRCE[^.]+)(?:\.A)?$", raw_api_key, re.IGNORECASE)
        return m.group(1).lower() if m else raw_api_key.lower()
    else:
        suffix = DOLLAR_YEAR_SUFFIX.get(pub_year, "dlrpmmbtu")
        return f"prce_ene_elep_NA_ng_NA_NA_{suffix}"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
rows = []

for filepath in files:

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        content = f.read()

    all_rows = list(csv.reader(content.splitlines()))

    # --- Row 0: table name ---
    table_name = all_rows[0][0].strip() if all_rows else ""

    # --- Row 1: URL → extract all metadata ---
    url = all_rows[1][0].strip() if len(all_rows) > 1 else ""
    meta = parse_url_metadata(url)

    if "pub_year" not in meta:
        print(f"WARNING: Could not parse vintage from URL in {filepath} — skipping")
        continue

    pub_year = meta["pub_year"]
    aeo_vintage = meta["aeo_vintage"]
    table_id = meta["tableId"]
    scenario = meta["scenario"]
    region_id = meta["regionId"]
    region_name = REGION_NAMES.get(region_id, region_id)

    # --- Find the header row (column 3 == "units") ---
    header_row_idx = None
    for i, row in enumerate(all_rows):
        if len(row) > 3 and row[3].strip().lower() == "units":
            header_row_idx = i
            break

    if header_row_idx is None:
        print(f"WARNING: Could not find header row in {filepath}")
        continue

    headers = all_rows[header_row_idx]

    # Extract year columns (4-digit integers)
    year_cols = {}
    for idx, h in enumerate(headers):
        h_clean = h.strip().strip('"')
        if re.match(r"^\d{4}$", h_clean):
            year_cols[int(h_clean)] = idx

    # --- Navigate to Electric Power > Natural Gas ---
    # AEO2011 uses a two-row format:
    #   "Natural Gas"    row — label only, values blank
    #   "Reference case" row — actual numeric values
    # All other vintages carry values directly on the "Natural Gas" row.
    sector_headers = {
        "Residential", "Commercial", "Industrial",
        "Transportation", "Average Price to All Users",
    }

    in_electric_power = False
    ng_label_found = False
    ng_row = None

    for row in all_rows[header_row_idx + 1:]:
        if not row:
            continue
        label = row[0].strip()

        if label == "Electric Power":
            in_electric_power = True
            continue

        if not in_electric_power:
            continue

        if label in sector_headers:
            break

        if label == "Natural Gas":
            ng_label_found = True
            has_data = any(
                row[idx].strip()
                for idx in year_cols.values()
                if idx < len(row)
            )
            if has_data:
                ng_row = row  # standard single-row format
                break

        if ng_label_found and label == "Reference case":
            ng_row = row  # AEO2011 two-row fallback
            break

    if ng_row is None:
        print(f"WARNING: Could not find Electric Power Natural Gas row in {filepath}")
        continue

    # --- Extract series metadata from the matched row ---
    series_name_raw = ng_row[1].strip() if len(ng_row) > 1 else ""
    raw_api_key = ng_row[2].strip() if len(ng_row) > 2 else ""
    unit = ng_row[3].strip() if len(ng_row) > 3 else ""

    series_name = re.sub(r":\s*Reference case$", "", series_name_raw).strip()
    series_id = parse_series_id(raw_api_key, pub_year)

    # --- Reshape wide -> long, stamp HISTORIC / PROJECTION ---
    for year, col_idx in year_cols.items():
        if col_idx >= len(ng_row):
            continue
        raw = ng_row[col_idx].strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue

        history = "HISTORIC" if int(year) < int(pub_year) else "PROJECTION"

        rows.append({
            "period": year,
            "history": history,
            "scenario": scenario,
            "scenarioDescription": "Reference case",
            "tableId": table_id,
            "tableName": table_name,
            "seriesId": series_id,
            "seriesName": series_name,
            "regionId": region_id,
            "regionName": region_name,
            "value": round(value, 6),
            "unit": unit,
            "aeo_vintage": aeo_vintage,
        })

# Sort by vintage (asc), then period (desc)
rows.sort(key=lambda r: (r["aeo_vintage"], -r["period"]))

out_path = "electric_power_ng_prices.csv"
with open(out_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
    writer.writeheader()
    writer.writerows(rows)

print(f"Done. {len(rows)} rows written to {out_path}\n")

from collections import defaultdict

summary = defaultdict(lambda: {"HISTORIC": 0, "PROJECTION": 0, "unit": ""})
for r in rows:
    summary[r["aeo_vintage"]][r["history"]] += 1
    summary[r["aeo_vintage"]]["unit"] = r["unit"]

for yr in sorted(summary):
    d = summary[yr]
    print(f"  AEO{yr} ({d['unit']}): {d['HISTORIC']} historic, {d['PROJECTION']} projection years")
