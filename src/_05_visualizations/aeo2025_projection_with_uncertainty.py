'''
Plot the AEO 2025 projection with the Gaussian density uncertainty bands and historical data

Use the calculated standard deviations out to H = 10 and then hold them constant

This mitigates the effect of sample size decreasing as H increases, 
which drives down the standard deviation even though uncertainty does not decrease
'''

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from pathlib import Path
from config import region_abbrv, sector_aeo, sector_seds, fuel_aeo, fuel_seds, value, calculation_year, fuel

#figure directory to save plots
fig_dir = Path(f'plots/_{region_abbrv}_{fuel_aeo}_{sector_aeo}_{value}_{calculation_year}')
fig_dir.mkdir(exist_ok = True) # make the figure directory if it doesn't already exist

# data paths
aeo_data_path = f"data/interim/AEO_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_constant_{calculation_year}.csv"
historical_data_path = f"data/interim/complete_historical_{fuel_seds}_{sector_seds}_{region_abbrv}_constant_{calculation_year}.csv"

# importing data
aeo_df = pd.read_csv(aeo_data_path)
historical_df = pd.read_csv(historical_data_path)
std_df = pd.read_csv(f'data/outputs/std_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_constant_{calculation_year}.csv')

# filter for aeo2025
aeo_2025 = aeo_df[aeo_df['scenario'] == 'ref2025']
aeo_2025 = aeo_2025.sort_values('period').reset_index(drop=True)

# H = 0 is the first projection year, H = 1 the second, etc.
aeo_2025_proj = aeo_2025[aeo_2025['history'] == 'PROJECTION']
aeo_2025_proj = aeo_2025_proj.sort_values('period').reset_index(drop=True)
aeo_2025_proj['H'] = range(len(aeo_2025_proj))

# assign each projection year its std:
#   - use the empirical std for H <= H_MAX
#   - hold the std flat at the H_MAX value for any horizon beyond that
std_lookup = dict(zip(std_df['H'], std_df['std_log_diff']))
H_MAX = 10
def std_for_H(H):
    return std_lookup[H] if H <= H_MAX else std_lookup[H_MAX]

aeo_2025_proj['std_log'] = aeo_2025_proj['H'].apply(std_for_H)

# 95% Gaussian interval in log-error space: y_proj * exp(-/+ 1.96 * std)
Z = 1.96
aeo_2025_proj['lower'] = aeo_2025_proj['value_converted'] * np.exp(-Z * aeo_2025_proj['std_log'])
aeo_2025_proj['upper'] = aeo_2025_proj['value_converted'] * np.exp(Z * aeo_2025_proj['std_log'])



# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 5.5))

# uncertainty band
ax.fill_between(
    aeo_2025_proj['period'],
    aeo_2025_proj['lower'],
    aeo_2025_proj['upper'],
    color='steelblue', alpha=0.25,
    label='95% empirical prediction interval',
)

#AEO 2025 reference case line
ax.plot(
    aeo_2025['period'], aeo_2025['value_converted'],
    color='steelblue', lw=2,
    label='AEO 2025 reference case',
)

# historical observations
ax.scatter(historical_df['period'], historical_df['value_converted'], color = 'black', label = 'Historical')


ax.set_xlabel('Year')
ax.set_ylabel(f'{fuel} price ({calculation_year} $/MMBtu)')
ax.legend(frameon=False)
ax.margins(x=0.01)
fig.tight_layout()

# save to fig_dir as projection_with_uncertainty_example.png
fig.savefig(fig_dir / 'projection_with_uncertainty_example.png', dpi=300)
plt.show()