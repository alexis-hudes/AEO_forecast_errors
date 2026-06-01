import subprocess
import sys

from config import sector, fuel, region, calculation_year

print(
    f"Running the full forecast errors workflow for price projections of "
    f"fuel: {fuel}, sector: {sector}, region: {region} "
    f"in constant {calculation_year}$"
)

# list of modules to run in order
modules = [
    "src._01_data_downloading.aeo_1998_2010_web_scrape",
    "src._01_data_downloading.aeo_2014_to_current_API",
    "src._01_data_downloading.seds_1998_to_current_API",
    "src._02_data_processing.aeo_1998_2010_reformat",
    "src._02_data_processing.aeo_2011_2013_reformat",
    "src._02_data_processing.seds_regional_aggregation",
    "src._03_data_translation.aeo_translation_and_compilation",
    "src._03_data_translation.seds_translation",
    "src._04_forecast_error_calculation.forecast_error_calculation",
    "src._05_visualizations.forecast_errors_vs_H",
    "src._05_visualizations.projections_historic_time_series",
    "src._05_visualizations.projection_with_uncertainty_example",
    "src._06_clean_up_repository.delete_processed_data",
    "src._06_clean_up_repository.delete_specific_raw_data"
]

for module in modules:
    print(f"Running {module}...")
    # execute each module as a separate process using the same Python
    # interpreter that's running main.py
    subprocess.run([sys.executable, "-m", module], check=True)

print("All scripts finished! See outputs in the data/outputs and plots folders.")