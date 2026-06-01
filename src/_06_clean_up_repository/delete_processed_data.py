'''
Clear out the data/interim folder
'''

import os

interim_dir = "data/interim"

for filename in os.listdir(interim_dir):
    file_path =os.path.join(interim_dir, filename)
    os.remove(file_path)

print("Interim directory was cleared out")
