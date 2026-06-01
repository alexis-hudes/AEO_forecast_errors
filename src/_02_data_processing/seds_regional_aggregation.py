'''
SEDS data is at a state level
'''

import pandas as pd
from config import fuel_seds, sector_seds, region_states, region_abbrv

df = pd.read_csv(f'data/raw/SEDS/{sector_seds}_{fuel_seds}.csv')

df_filtered = df[df['stateId'].isin(region_states)]

consumption_code = fuel_seds + sector_seds + 'B'
price_code = fuel_seds + sector_seds + 'D'
conversion_factor_code = fuel_seds + 'TCK'

if region_abbrv == 'US':
    df_weighted_avg = df_filtered
else:
    # Split into separate dataframes 
    df_price = df_filtered[df_filtered["seriesId"] == price_code][["stateId", "period", "value"]].rename(columns={"value": "price"})
    df_consumption = df_filtered[df_filtered["seriesId"] == consumption_code][["stateId", "period", "value"]].rename(columns={"value": "consumption"})

    # Merge price and consumption on state and year
    df_merged = pd.merge(df_price, df_consumption, on=["stateId", "period"])

    # Drop rows where either price or consumption is missing
    df_merged = df_merged.dropna(subset=["price", "consumption"])

    # Calculate weighted price for each state-year: price * consumption
    df_merged["weighted_price"] = df_merged["price"] * df_merged["consumption"]

    # Group by year and calculate the New England weighted average price
    df_weighted_avg = (
        df_merged
        .groupby("period")
        .apply(lambda x: x["weighted_price"].sum() / x["consumption"].sum())
        .reset_index()
        .rename(columns={0: "ne_avg_price"})
    )
    df_weighted_avg["period"] = df_weighted_avg["period"].astype(int)
    df_weighted_avg = df_weighted_avg.sort_values("period")

df_weighted_avg.to_csv(f'data/interim/SEDS_{fuel_seds}_{sector_seds}_{region_abbrv}.csv', index = False)