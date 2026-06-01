"""
Calculate the AEO forecast error as
stdev_H(log(y_projected)-log(y_observed)) for all y_projected and y_observed in that H

H is year/time horizon. H=0 is the first year of the projection, H=1 is the second year of the proejction, etc..

Observed values default to SEDS. Where SEDS is missing a year (e.g. residential
propane, where SEDS only goes back to 2010), fall back to the HISTORIC rows
carried in the AEO vintages, which are already converted to constant dollars by
the compilation step. SEDS remains the default because it generally has spatial coverage
than the AEO historic
"""

import pandas as pd
import math
from config import region_abbrv, sector_aeo, sector_seds, fuel_aeo, fuel_seds, value, sector,fuel, region, calculation_year

# data paths
aeo_data_path = f"data/interim/AEO_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_constant_{calculation_year}.csv"
seds_data_path = f"data/interim/SEDS_{fuel_seds}_{sector_seds}_{region_abbrv}_constant_{calculation_year}.csv"

# importing data
aeo_df = pd.read_csv(aeo_data_path)
seds_df = pd.read_csv(seds_data_path)


#######################################################################################################
# Build the observed-values lookup (default to SEDS, pull in AEO HISTORIC when SEDS has gaps)
#######################################################################################################

seds_observed = (
    seds_df[['period', 'value_converted']]
    .dropna(subset=['value_converted'])
    .drop_duplicates(subset='period')
)

# Collapse multiple vintages reporting the same historic year, keeping the
# most recent vintage's value (EIA revises historic figures across AEOs).
aeo_historic = (
    aeo_df[aeo_df['history'] == 'HISTORIC']
    .dropna(subset=['value_converted'])
    .sort_values('aeo_vintage')
    .drop_duplicates(subset='period', keep='last')[['period', 'value_converted']]
)

# find the years that exist in AEO but not in SEDS
missing_years = set(aeo_historic['period']) - set(seds_observed['period'])

# filter the AEO dataframe to just pull the yers not available in SEDS
aeo_fallback = aeo_historic[aeo_historic['period'].isin(missing_years)]

# combine SEDS and fallback AEO data, use concat to stack vertically
observed = pd.concat([seds_observed, aeo_fallback], ignore_index=True)

# sort chronologically
observed = observed.sort_values('period').reset_index(drop=True)

# save to data/interim to use as complete historical data for plotting
observed.to_csv(f'data/interim/complete_historical_{fuel_seds}_{sector_seds}_{region_abbrv}_constant_{calculation_year}.csv')

if not aeo_fallback.empty:
    print(
        f"SEDS missing years {sorted(missing_years)}; "
        f"filled from AEO historic data."
    )

# convenient year -> observed value map
observed_lookup = dict(zip(observed['period'], observed['value_converted']))

# filter AEO to only include projections
aeo_df = aeo_df[aeo_df['history'] == 'PROJECTION']

# filter AEO to only include years that there are observed data for
max_observed_year = max(observed_lookup)
aeo_df = aeo_df[aeo_df['period'] <= max_observed_year]

# get list of unique AEO projections included in the dataset
aeo_unique = aeo_df['scenario'].unique()

#######################################################################################################
# Calculate the log forecast errors
#######################################################################################################

forecast_errors = []

for scenario in aeo_unique:
    aeo_subset = aeo_df[aeo_df['scenario'] == scenario]

    # sort by year and reset index
    aeo_subset = aeo_subset.sort_values('period').reset_index(drop=True)

    for H, t in enumerate(aeo_subset['period']):
        # skip any projection year we have no observed value for
        if t not in observed_lookup:
            continue

        aeo_val = aeo_subset.loc[aeo_subset['period'] == t, 'value_converted'].iloc[0]
        seds_val = observed_lookup[t]

        log_diff = math.log(aeo_val) - math.log(seds_val)

        # append a row as a dictionary
        forecast_errors.append({
            'scenario': scenario,
            'H': H,
            'log_diff': log_diff
        })

# convert list of dicts to DataFrame
forecast_errors_df = pd.DataFrame(forecast_errors)

# save to data/interim to be able to plot
forecast_errors_df.to_csv(f'data/interim/forecast_errors_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_constant_{calculation_year}.csv')

#######################################################################################################
# Calculate the standard deviation of the errors grouped by time horizon (H)
#######################################################################################################
std_by_H = (
    forecast_errors_df
    .groupby('H')['log_diff']
    .std(ddof=1)
    .reset_index(name='std_log_diff')
)

print(std_by_H)

# get the count of samples for each H
count_by_H = (
    forecast_errors_df
    .groupby('H')['log_diff']
    .count()
    .reset_index(name='count')
)

print(count_by_H)

# save the standard deviations to data/outputs
std_by_H.to_csv(f'data/outputs/std_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_constant_{calculation_year}.csv')
