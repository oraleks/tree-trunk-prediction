import os
import numpy as np
import sys
import geopandas as gpd
import pandas as pd
from tqdm import tqdm
import math
from funcs import calculate_compactness,find_overlapping_polygons
current_dir = os.path.dirname(os.path.realpath(__file__))

# Add the current directory to the Python path
sys.path.append(current_dir)


tqdm.pandas()

if len(sys.argv) < 2:
    print("Usage: python app.py <path_to_shapefile>")
    sys.exit(1)

shapefile_path = sys.argv[1]
shapefile_path = shapefile_path.replace('\\','/')

out_path = shapefile_path.replace('.shp','_prameters.shp')

canopies = gpd.read_file(shapefile_path)

canopies = canopies.to_crs('2039')
canopies = canopies.explode(index_parts=True)
canopies = canopies.droplevel(1)
duplicate_columns = canopies.columns.duplicated()
canopies = canopies.loc[:, ~duplicate_columns]
canopies = find_overlapping_polygons(canopies)
canopies['perimter'] = canopies.length
canopies['area'] = canopies.area
canopies['compactness'] =  (4 * 3.14159265359 * canopies['area']) / (canopies['perimter']**2)

thresh = 0
col_names = canopies.columns
target_col_name = [col for col in col_names if "point" in col.lower()][0]
filtered = canopies[canopies[target_col_name] > thresh]

cols = ['perimter', 'area', 'compactness']
X = filtered[cols]
y = filtered[target_col_name] 

canopies.to_file(out_path)