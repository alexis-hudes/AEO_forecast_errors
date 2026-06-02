# AEO Forecast Errors

A pipeline for calculating historical forecast errors in the U.S. Energy Information Administration's Annual Energy Outlook (AEO) reference scenario price projections, following the empirical prediction interval approach of [Kaack et al. (2017)](https://www.pnas.org/doi/10.1073/pnas.1619938114).

For each combination of fuel, sector, and region, the pipeline downloads every AEO vintage from 1998 to the present as well as historical observations from the State Energy Data System (SEDS), converts everything to constant dollars, and computes the standard deviation of log forecast errors as a function of forecast horizon (H). Those standard deviations can parameterize Gaussian density intervals to characterize uncertainty around future AEO projections.

## What you get

For a single configuration (e.g. natural gas / electric power / United States / 2021 dollars), one run produces:

- A CSV of forecast error standard deviations by horizon H (saved in `data/outputs`)
- A scatter plot of forecast errors and their standard deviations vs. horizon (saved in `plots/`)
- A plot of every AEO vintage's projections with historical observations overlaid (saved in `plots/`)
- A plot of the AEO 2025 projection with its Gaussian prediction-interval bands and historical data (saved in `plots/`)

## Repository layout

```
AEO_forecast_errors/
├── config.py                        # all user-editable settings
├── main.py                          # runs the full pipeline
├── README.md
├── data/
│   ├── raw/                         # downloaded and compiled raw data
│   ├── interim/                     # intermediate processed files
│   └── outputs/                     # final forecast-error CSVs
├── plots/                           # generated figures
└── src/
    ├── _01_data_downloading/        # AEO + SEDS downloaders
    ├── _02_data_processing/         # reformat archive XLS, aggregate SEDS
    ├── _03_data_transformation/     # convert to constant dollars
    ├── _04_forecast_error_calculation/
    ├── _05_visualizations/          # generate figures into plots/
    └── _06_clean_up_repository/     # clears data/interim/ and analysis-specific raw files
```

## Setup

### 1. Install Python dependencies

Code was developed using Python 3.12, should work reliably with Python 3.10+

Use pip or conda to install any of the following packages that you don't already have

```
pandas
requests
matplotlib
xlrd
openpyxl
```

### 2. Get an EIA API key

Register at https://www.eia.gov/opendata/ and copy your key into `config.py`:

```python
API_KEY = "your-key-here"
```

### 3. Manual downloads required

Two sources aren't fetched automatically and must be placed in the repo before running. These files are preloaded to GitHub for ease of use, but
if you find that you need to redownload them:

**a. FRED GDP deflator** (used to convert between dollar years)

Download `A191RG3A086NBEA` from https://fred.stlouisfed.org/series/A191RG3A086NBEA as CSV and save to:

```
data/raw/FRED/A191RG3A086NBEA.csv
```

**b. AEO 2011–2013 supplementary tables** (the API doesn't go back this far, and these years aren't in the archive XLS series)
1. Go to https://www.eia.gov/outlooks/aeo/data/browser
2. Under PUBLICATIONS & TABLES select Annual Energy Outlook 2011 and Energy Prices by Sector and Source
3. Under CASES & SCENARIOS select Reference Scenario
4. Under REGIONS select your desired region. The workflow is currently set-up to work with United States and New England, but could easily be extended to any census division.
5. Click on the blue square buttons to 'Add this series to the chart' for all of the displayed fuel + sector combos
6. Click Download, Table(CSV)
7. Move to this folder: data/raw/AEO/aeo_2011_2013_manual_download
7. Repeat for 2012 and 2013
8. Rename to follow this convention:

```
Energy_Prices_by_Sector_and_Source_{AEOyear}_{region_abbrv}.csv
```
For example:

```
Energy_Prices_by_Sector_and_Source_2011_US.csv
```

## Usage

### Run the full pipeline

From the project root:

```bash
python main.py
```

This runs the full workflow in order: downloading, reformatting, regional aggregation, dollar-year translation, forecast error calculation, plotting, and cleanup.


### Change what's analyzed

Edit the top of `config.py`:

```python
fuel    = "Natural Gas"      # Natural Gas | Electricity | Propane | Distillate Fuel
sector  = "Electric Power"   # Electric Power | Commercial | Residential | Industrial
region  = "United States"    # United States | New England
value   = "real"             # real | nom
calculation_year = 2021      # any year from 1929 to present
```

Re-run `python main.py` after editing

### Run a single stage

Use Python's `-m` flag from the project root. For example:

```bash
python -m src._01_data_downloading.aeo_2014_to_current_API
```

Note: Scripts must be invoked in this way from the project root so that `config` gets imported properly

## Caching behavior

The downloaders (`aeo_2014_to_current_API`, `seds_1998_to_current_API`, `aeo_1998_2010_web_scrape`) skip if their output file already exists. Reformatting and translation always re-run. To force a fresh download, delete the cached file.

The final pipeline step deletes all intermediate files. Comment out the last two entries in `main.py`'s `scripts` list if you want to inspect or call intermediate files.

## How the dollar-year conversion works

Every AEO vintage reports real prices in a different base year (e.g. AEO 2015 uses 2013 dollars, AEO 2020 uses 2019 dollars). SEDS reports nominal prices in the observation year. To compare them, everything is converted to a single year via the BEA GDP chain-type price index (FRED series `A191RG3A086NBEA`):

```
value_in_calculation_year = value_in_base_year × (deflator[calculation_year] / deflator[base])
```

The `calculation_year` variable is set in `config.py`.

## Reference

Kaack, L. H., Apt, J., Morgan, M. G., & McSharry, P. (2017). Empirical prediction intervals improve energy forecasting. *PNAS*, 114(33), 8752–8757. https://doi.org/10.1073/pnas.1619938114