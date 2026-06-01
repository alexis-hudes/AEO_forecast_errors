'''
Clear out fuel/sector/region specific files from the raw data folder

DO NOT delete generic files that can be reused across analyses (full AEO archive files and FRED data)
'''

import os

# delete the files in data/raw/AEO which are specific to each analysis
# DO NOT delete files in the subfolders aeo_1998_to_2010 and aeo_2011_2013_manueal_download
# these subfolders contain full sets of AEO projections, which get parsed/extracted from
# for each analysis
aeo_dir = "data/raw/AEO"

for filename in os.listdir(aeo_dir):
    file_path =os.path.join(aeo_dir, filename)

    #skip directories
    if os.path.isdir(file_path):
        continue

    os.remove(file_path)

print("AEO directory was cleared out, archive subfolders were preserved")

# raw SEDS data gets downloaded into the data/raw/seds folder for each specific analysis using the API
seds_dir = "data/raw/SEDS"

for filename in os.listdir(seds_dir):
    file_path =os.path.join(seds_dir, filename)
    os.remove(file_path)

print("SEDS directory was cleared out")
