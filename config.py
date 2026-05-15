######################################################
# 1. API KEY
######################################################
# You need to register for the EIA API to get a key
# https://www.eia.gov/opendata/

# uncomment the next line and add your API key in quotes
# API_KEY = 

######################################################
# 2. Current year
######################################################
current_year = 2026

######################################################
# 3. Region
######################################################

region = 'United States' #currently setup to work with 'United States' or 'New England'

if region == 'United States':
    region_code = '1-0'
    region_shorthand = 'NA' #for API seriesID
    region_abbrv = 'US'
    table_num = 20
elif region == 'New England':
    region_code = '1-1'
    region_shorthand = 'neengl'
    region_abbrv = 'NE'
    table_num = 11

######################################################
# 3. series
######################################################
fuel = 'ng'

sector = 'elep'

# value can be 'real' or 'nom' for nominal
value = 'real'
