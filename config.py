# config.py
######################################################
# USER SETTINGS — edit these
######################################################
# You need to register for the EIA API to get a key
# https://www.eia.gov/opendata/
API_KEY = 'b4mZau2npFizQNxnHhTpsJy8zTq8njsMbDStWfod'

# What to analyze
fuel    = "Distillate Fuel"      # Natural Gas | Electricity | Propane | Distillate Fuel
sector  = "Residential"      # Electric Power | Commercial | Residential | Industrial
region  = "New England"    # United States | New England
value   = "real"             # real | nom

# Time settings
current_year     = 2026
calculation_year = 2020      # dollar-year for constant-$ analysis (1929-present)
# Note: Kaack, et al. uses 2013 as their calculation year


######################################################
# LOOKUPS — don't edit unless adding a new option
######################################################

FUEL_CODES = {
    "Natural Gas":     {"aeo": "ng",   "seds": "NG"},
    "Electricity":     {"aeo": "elc",  "seds": "ES"},
    "Propane":         {"aeo": "prop", "seds": "PQ"},
    "Distillate Fuel": {"aeo": "dfo",  "seds": "DF"},
}

SECTOR_CODES = {
    "Electric Power": {"aeo": "elep", "seds": "EI"},
    "Commercial":     {"aeo": "comm", "seds": "CC"},
    "Residential":    {"aeo": "resd", "seds": "RC"},
    "Industrial":     {"aeo": "idal", "seds": "IC"},
}

REGION_CODES = {
    "United States": {
        "code": "1-0", "shorthand": "NA", "abbrv": "US",
        "table_num": 20, "states": ["US"],
    },
    "New England": {
        "code": "1-1", "shorthand": "neengl", "abbrv": "NE",
        "table_num": 11, "states": ["MA", "NH", "CT", "VT", "ME", "RI"],
    },
}


######################################################
# DERIVED — exported for the rest of the pipeline
######################################################

_f = FUEL_CODES[fuel]
_s = SECTOR_CODES[sector]
_r = REGION_CODES[region]


fuel_aeo,   fuel_seds   = _f["aeo"], _f["seds"]
sector_aeo, sector_seds = _s["aeo"], _s["seds"]
region_code      = _r["code"]
region_shorthand = _r["shorthand"]
region_abbrv     = _r["abbrv"]
table_num        = _r["table_num"]
region_states    = _r["states"]