'''
Plot the log forecast error and standard deviations for each H
'''
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
from config import value, sector_aeo, fuel_aeo, region_abbrv, calculation_year

fig_dir = Path(f'plots/_{region_abbrv}_{fuel_aeo}_{sector_aeo}_{value}_{calculation_year}')
fig_dir.mkdir(exist_ok = True) # make the figure directory if it doesn't already exist

forecast_errors_df = pd.read_csv(f'data/interim/forecast_errors_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_constant_{calculation_year}.csv')
std_df = pd.read_csv(f'data/outputs/std_{value}_{sector_aeo}_{fuel_aeo}_{region_abbrv}_constant_{calculation_year}.csv')

fig, axs = plt.subplots(2,1, sharex = True, sharey = False, figsize = (8,6))
axs[0].scatter(forecast_errors_df['H'],forecast_errors_df['log_diff'])
axs[0].set_ylabel(r'$\epsilon_{log}$ = ln(projected) - ln(observed)')

axs[1].scatter(std_df['H'], std_df['std_log_diff'])
axs[1].set_xlabel('H (yr)')
axs[1].set_ylabel(r'std dev($\epsilon_{log}$)')

plt.tight_layout()
plt.savefig(fig_dir / f'error_and_std_dev_vs_H.png', dpi=300)

plt.show()