'''
Plot the AEO projections and historic data as overlaid time series
'''

import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
from config import region_abbrv, sector_aeo, sector_seds, fuel_aeo, fuel_seds, value, calculation_year

#figure directory to save plots
fig_dir = Path(f'plots/_{region_abbrv}_{fuel_aeo}_{sector_aeo}_{value}_{calculation_year}')
fig_dir.mkdir(exist_ok = True) # make the figure directory if it doesn't already exist

# data paths
aeo_data_path = f"data/interim/AEO_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_constant_{calculation_year}.csv"
historical_data_path = f"data/interim/complete_historical_{fuel_seds}_{sector_seds}_{region_abbrv}_constant_{calculation_year}.csv"

# importing data
aeo_df = pd.read_csv(aeo_data_path)
historical_df = pd.read_csv(historical_data_path)

for i, scenario in enumerate(aeo_df['scenario'].unique()):
    subset = aeo_df[aeo_df['scenario'] == scenario]

    plt.plot(
        subset['period'],
        subset['value_converted'],
        color = 'lightgrey',
        label='AEO Projections' if i == 0 else None
    )

plt.scatter(
    historical_df['period'],
    historical_df['value_converted'],
    label='Historical'
)

plt.legend()

plt.savefig(fig_dir / 'time_series.png', dpi = 300)

plt.show()