import os
import numpy as np
import sys
import geopandas as gpd
import numpy as np
import pandas as pd
from tqdm import tqdm
import math
import matplotlib.pyplot as plt
from skimage.morphology import medial_axis
from shapely.geometry import Polygon, Point
from catboost import CatBoostRegressor, Pool
from funcs import calculate_compactness,find_overlapping_polygons,is_convex,calculate_eccentricity,calculate_l_shape_ratio,polygon_centerline,calculate_l_shape,get_ratio
current_dir = os.path.dirname(os.path.realpath(__file__))

# Add the current directory to the Python path
sys.path.append(current_dir)


tqdm.pandas()

if len(sys.argv) < 2:
    print("Usage: python app.py <path_to_shapefile>")
    sys.exit(1)

shapefile_path = sys.argv[1]
shapefile_path = shapefile_path.replace('\\','/')

out_path = shapefile_path.replace('.shp','_prediction.shp')

canopies = gpd.read_file(shapefile_path)

canopies = canopies.to_crs('2039')
canopies = canopies.explode(index_parts=True)
canopies = canopies.droplevel(1)
duplicate_columns = canopies.columns.duplicated()
canopies = canopies.loc[:, ~duplicate_columns]
canopies = find_overlapping_polygons(canopies)
canopies['perimter'] = canopies.length
canopies['area'] = canopies.area
canopies['mrr'] = canopies.progress_apply(lambda row:row.geometry.minimum_rotated_rectangle,axis=1)
canopies['major_axis_length'] = canopies.progress_apply(lambda row:max(row.mrr.exterior.xy[0]) - min(row.mrr.exterior.xy[0]),axis=1)
canopies['minor_axis_length'] = canopies.progress_apply(lambda row:max(row.mrr.exterior.xy[1]) - min(row.mrr.exterior.xy[1]),axis=1)
canopies['eccentricity'] = canopies.apply(calculate_eccentricity, axis=1)
canopies['perimeter_to_area'] = canopies.length / canopies.area
canopies['compactness'] =  (4 * 3.14159265359 * canopies['area']) / (canopies['perimter']**2)
canopies['L_ratio'] = canopies.progress_apply(lambda row:get_ratio(row), axis=1)

thresh = 0
col_names = canopies.columns
target_col_name = [col for col in col_names if "point" in col.lower()][0]
filtered = canopies[canopies[target_col_name] > thresh]
no_vals = canopies[canopies[target_col_name] <= thresh]

cols = ['perimter', 'area', 'compactness','perimeter_to_area','eccentricity']
X = filtered[cols]
y = filtered[target_col_name] 
target = no_vals[cols]

train_pool = Pool(X, label=y)
print('\n Running prediction... \n')
model = CatBoostRegressor(task_type="GPU", od_type = "IncToDec",od_pval=0.001, od_wait = 100,verbose=100) 
model.fit(train_pool)

predictions_regressor = model.predict(target).astype(int)
predictions_regressor[predictions_regressor < 1] = 1

no_vals[target_col_name] = predictions_regressor
#merged_with_pred = pd.concat([filtered, no_vals])
merged_with_pred = no_vals
merged_with_pred = merged_with_pred.drop(columns=['mrr'])
merged_with_pred = merged_with_pred[['area', 'perimter', 'minor_axis_length', 'minor_axis_length', 'eccentricity', 'perimeter_to_area', 'compactness', 'L_ratio', target_col_name, 'geometry']]
merged_with_pred = merged_with_pred.loc[:, ~merged_with_pred.columns.duplicated()]
merged_with_pred = merged_with_pred.set_geometry('geometry')
merged_with_pred.drop_duplicates('geometry').to_file(out_path)

feature_importance = model.get_feature_importance(prettified=True)

print("Feature Importance Report:")
print(feature_importance)
print("\n")

hist, bins = np.histogram(merged_with_pred[target_col_name], bins=20)

max_freq = max(hist)

print(f"Histogram of Target Variable {target_col_name}")
for i in range(len(hist)):
    bar_length = max(int(hist[i] / max_freq * 100), 1)  
    bar = '#' * bar_length
    print(f"{bins[i]:<10.2f} - {bins[i+1]:<10.2f} | {bar}")