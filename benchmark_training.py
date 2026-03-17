"""
Benchmark training time: old 5-feature model vs new 20-feature models.
Measures single-fit time and full GridSearchCV time for each configuration.
"""

import numpy as np
import pandas as pd
import geopandas as gpd
import math
import time
import warnings
from sklearn.model_selection import train_test_split, KFold, GridSearchCV
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
import xgboost as xgb
from catboost import CatBoostRegressor
from feature_utils import extract_features

warnings.filterwarnings('ignore')

RANDOM_STATE = 42
TARGET = 'Point_Coun'

# =====================================================================
# Prepare both feature sets
# =====================================================================
print("Loading data...")
gdf = gpd.read_file('train_set_validated.shp').to_crs(epsg=2039)
gdf = gdf.explode(index_parts=False).reset_index(drop=True)
gdf = gdf[gdf.geometry.type == 'Polygon'].copy()

# 20-feature set (new model)
feat20 = extract_features(gdf)
FEATURES_20 = [
    'area', 'perimeter', 'perimeter_to_area', 'compactness', 'convexity',
    'eccentricity', 'major_axis', 'minor_axis', 'aspect_ratio', 'mrr_area_ratio',
    'n_vertices', 'boundary_sinuosity', 'n_concavities', 'mean_radius',
    'radius_std', 'radius_cv', 'radius_ratio', 'equivalent_diameter',
    'convex_hull_deficit', 'l_ratio',
]

# 5-feature set (old model, with old buggy MRR)
gdf['perimeter'] = gdf.geometry.length
gdf['area'] = gdf.geometry.area
gdf['compactness'] = (4 * math.pi * gdf['area']) / (gdf['perimeter'] ** 2)
gdf['perimeter_to_area'] = gdf['perimeter'] / gdf['area']

def old_mrr_axes(geom):
    mrr = geom.minimum_rotated_rectangle
    xs = list(mrr.exterior.xy[0])
    ys = list(mrr.exterior.xy[1])
    return max(xs) - min(xs), max(ys) - min(ys)

gdf[['major_axis_length', 'minor_axis_length']] = gdf.geometry.apply(
    lambda g: pd.Series(old_mrr_axes(g))
)

def old_eccentricity(row):
    major, minor = row['major_axis_length'], row['minor_axis_length']
    if major == minor:
        return 0
    if minor > major:
        major, minor = minor, major
    return math.sqrt(np.clip(1 - (minor ** 2 / max(major ** 2, 1)), 0, 1))

gdf['eccentricity'] = gdf.apply(old_eccentricity, axis=1)
FEATURES_5 = ['perimeter', 'area', 'compactness', 'perimeter_to_area', 'eccentricity']

data5 = gdf[FEATURES_5 + [TARGET]].dropna()
# extract_features returns a DataFrame with feature columns; merge target back in
feat20[TARGET] = gdf[TARGET].values
data20 = feat20[FEATURES_20 + [TARGET]].dropna()

# Same split for both
bins = [0, 3, 5, 8, 15, 100]
y5 = data5[TARGET]
yb5 = pd.cut(y5, bins=bins, labels=False)
X5_tr, X5_te, y5_tr, y5_te = train_test_split(
    data5[FEATURES_5], y5, test_size=0.2, random_state=RANDOM_STATE, stratify=yb5
)

y20 = data20[TARGET]
yb20 = pd.cut(y20, bins=bins, labels=False)
X20_tr, X20_te, y20_tr, y20_te = train_test_split(
    data20[FEATURES_20], y20, test_size=0.2, random_state=RANDOM_STATE, stratify=yb20
)

cv = KFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

# =====================================================================
# Benchmark function
# =====================================================================
def benchmark_single_fit(name, model, X_tr, y_tr, X_te, y_te, n_runs=5):
    """Time a single model.fit() averaged over n_runs."""
    times = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        model.fit(X_tr, y_tr)
        t1 = time.perf_counter()
        times.append(t1 - t0)
    pred = np.clip(np.round(model.predict(X_te)), 1, None)
    mae = mean_absolute_error(y_te, pred)
    return {
        'name': name,
        'mean_time': np.mean(times),
        'std_time': np.std(times),
        'min_time': np.min(times),
        'mae': mae,
        'n_runs': n_runs,
    }


def benchmark_gridsearch(name, model, params, X_tr, y_tr, n_jobs=1):
    """Time a full GridSearchCV."""
    n_combos = 1
    for v in params.values():
        n_combos *= len(v)
    total_fits = n_combos * cv.n_splits

    t0 = time.perf_counter()
    grid = GridSearchCV(model, params, cv=cv, scoring='neg_mean_absolute_error',
                        refit=True, n_jobs=n_jobs)
    grid.fit(X_tr, y_tr)
    t1 = time.perf_counter()

    return {
        'name': name,
        'total_time': t1 - t0,
        'n_combos': n_combos,
        'total_fits': total_fits,
        'time_per_fit': (t1 - t0) / total_fits,
        'best_params': grid.best_params_,
    }

# =====================================================================
# Run benchmarks
# =====================================================================
print("\n" + "=" * 70)
print("SINGLE FIT BENCHMARKS (averaged over 5 runs)")
print("=" * 70)

single_results = []

# --- 5-feature models ---
print("\n--- 5-Feature Models ---")

r = benchmark_single_fit("Ridge (5feat)", Ridge(alpha=1.0), X5_tr, y5_tr, X5_te, y5_te)
single_results.append(r)
print(f"  {r['name']:<35s} {r['mean_time']*1000:>8.1f} ms  (MAE={r['mae']:.2f})")

r = benchmark_single_fit("CatBoost old config (5feat)",
    CatBoostRegressor(task_type='GPU', od_type='IncToDec', od_pval=0.001,
                      od_wait=100, verbose=0, random_seed=RANDOM_STATE),
    X5_tr, y5_tr, X5_te, y5_te)
single_results.append(r)
print(f"  {r['name']:<35s} {r['mean_time']*1000:>8.1f} ms  (MAE={r['mae']:.2f})")

r = benchmark_single_fit("CatBoost tuned (5feat)",
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE,
                      iterations=300, depth=5, learning_rate=0.1),
    X5_tr, y5_tr, X5_te, y5_te)
single_results.append(r)
print(f"  {r['name']:<35s} {r['mean_time']*1000:>8.1f} ms  (MAE={r['mae']:.2f})")

# --- 20-feature models ---
print("\n--- 20-Feature Models ---")

r = benchmark_single_fit("Ridge (20feat)", Ridge(alpha=1.0), X20_tr, y20_tr, X20_te, y20_te)
single_results.append(r)
print(f"  {r['name']:<35s} {r['mean_time']*1000:>8.1f} ms  (MAE={r['mae']:.2f})")

r = benchmark_single_fit("RandomForest (20feat)",
    RandomForestRegressor(n_estimators=300, max_depth=5, random_state=RANDOM_STATE, n_jobs=-1),
    X20_tr, y20_tr, X20_te, y20_te)
single_results.append(r)
print(f"  {r['name']:<35s} {r['mean_time']*1000:>8.1f} ms  (MAE={r['mae']:.2f})")

r = benchmark_single_fit("XGBoost (20feat)",
    xgb.XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.1,
                      random_state=RANDOM_STATE, device='cuda', verbosity=0),
    X20_tr, y20_tr, X20_te, y20_te)
single_results.append(r)
print(f"  {r['name']:<35s} {r['mean_time']*1000:>8.1f} ms  (MAE={r['mae']:.2f})")

r = benchmark_single_fit("CatBoost RMSE (20feat)",
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE,
                      iterations=300, depth=5, learning_rate=0.1),
    X20_tr, y20_tr, X20_te, y20_te)
single_results.append(r)
print(f"  {r['name']:<35s} {r['mean_time']*1000:>8.1f} ms  (MAE={r['mae']:.2f})")

r = benchmark_single_fit("CatBoost Poisson (20feat)",
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE,
                      iterations=300, depth=5, learning_rate=0.1, loss_function='Poisson'),
    X20_tr, y20_tr, X20_te, y20_te)
single_results.append(r)
print(f"  {r['name']:<35s} {r['mean_time']*1000:>8.1f} ms  (MAE={r['mae']:.2f})")

# =====================================================================
# GridSearchCV benchmarks
# =====================================================================
print("\n" + "=" * 70)
print("GRIDSEARCHCV BENCHMARKS (full hyperparameter tuning)")
print("=" * 70)

grid_results = []

print("\n--- 5-Feature Models ---")

g = benchmark_gridsearch("Ridge GridCV (5feat)",
    Ridge(), {'alpha': [0.01, 0.1, 1, 10, 100]},
    X5_tr, y5_tr, n_jobs=-1)
grid_results.append(g)
print(f"  {g['name']:<35s} {g['total_time']:>7.1f}s  ({g['total_fits']} fits, {g['time_per_fit']*1000:.1f} ms/fit)")

g = benchmark_gridsearch("CatBoost GridCV (5feat)",
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE, loss_function='RMSE'),
    {'iterations': [100, 300, 500, 1000], 'depth': [3, 5, 7], 'learning_rate': [0.01, 0.05, 0.1]},
    X5_tr, y5_tr, n_jobs=1)
grid_results.append(g)
print(f"  {g['name']:<35s} {g['total_time']:>7.1f}s  ({g['total_fits']} fits, {g['time_per_fit']*1000:.1f} ms/fit)")

print("\n--- 20-Feature Models ---")

g = benchmark_gridsearch("Ridge GridCV (20feat)",
    Ridge(), {'alpha': [0.1, 1, 10, 100]},
    X20_tr, y20_tr, n_jobs=-1)
grid_results.append(g)
print(f"  {g['name']:<35s} {g['total_time']:>7.1f}s  ({g['total_fits']} fits, {g['time_per_fit']*1000:.1f} ms/fit)")

g = benchmark_gridsearch("RandomForest GridCV (20feat)",
    RandomForestRegressor(random_state=RANDOM_STATE, n_jobs=-1),
    {'n_estimators': [100, 300, 500], 'max_depth': [3, 5, 7]},
    X20_tr, y20_tr, n_jobs=-1)
grid_results.append(g)
print(f"  {g['name']:<35s} {g['total_time']:>7.1f}s  ({g['total_fits']} fits, {g['time_per_fit']*1000:.1f} ms/fit)")

g = benchmark_gridsearch("XGBoost GridCV (20feat)",
    xgb.XGBRegressor(random_state=RANDOM_STATE, device='cuda', verbosity=0),
    {'n_estimators': [100, 300, 500], 'max_depth': [3, 5, 7], 'learning_rate': [0.01, 0.05, 0.1]},
    X20_tr, y20_tr, n_jobs=-1)
grid_results.append(g)
print(f"  {g['name']:<35s} {g['total_time']:>7.1f}s  ({g['total_fits']} fits, {g['time_per_fit']*1000:.1f} ms/fit)")

g = benchmark_gridsearch("CatBoost RMSE GridCV (20feat)",
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE, loss_function='RMSE'),
    {'iterations': [100, 300, 500], 'depth': [3, 5, 7], 'learning_rate': [0.01, 0.05, 0.1]},
    X20_tr, y20_tr, n_jobs=1)
grid_results.append(g)
print(f"  {g['name']:<35s} {g['total_time']:>7.1f}s  ({g['total_fits']} fits, {g['time_per_fit']*1000:.1f} ms/fit)")

g = benchmark_gridsearch("CatBoost Poisson GridCV (20feat)",
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE, loss_function='Poisson'),
    {'iterations': [100, 300, 500], 'depth': [3, 5, 7], 'learning_rate': [0.01, 0.05, 0.1]},
    X20_tr, y20_tr, n_jobs=1)
grid_results.append(g)
print(f"  {g['name']:<35s} {g['total_time']:>7.1f}s  ({g['total_fits']} fits, {g['time_per_fit']*1000:.1f} ms/fit)")

# =====================================================================
# Feature extraction benchmark
# =====================================================================
print("\n" + "=" * 70)
print("FEATURE EXTRACTION BENCHMARKS")
print("=" * 70)

gdf_bench = gpd.read_file('train_set_validated.shp').to_crs(epsg=2039)
gdf_bench = gdf_bench.explode(index_parts=False).reset_index(drop=True)
gdf_bench = gdf_bench[gdf_bench.geometry.type == 'Polygon'].copy()

# 5-feature extraction
times_5 = []
for _ in range(5):
    t0 = time.perf_counter()
    g = gdf_bench.copy()
    g['perimeter'] = g.geometry.length
    g['area'] = g.geometry.area
    g['compactness'] = (4 * math.pi * g['area']) / (g['perimeter'] ** 2)
    g['perimeter_to_area'] = g['perimeter'] / g['area']
    g[['major_axis_length', 'minor_axis_length']] = g.geometry.apply(lambda geom: pd.Series(old_mrr_axes(geom)))
    g['eccentricity'] = g.apply(old_eccentricity, axis=1)
    t1 = time.perf_counter()
    times_5.append(t1 - t0)

# 20-feature extraction
times_20 = []
for _ in range(5):
    t0 = time.perf_counter()
    _ = extract_features(gdf_bench)
    t1 = time.perf_counter()
    times_20.append(t1 - t0)

print(f"  5-feature extraction:  {np.mean(times_5)*1000:>8.1f} ms  (std: {np.std(times_5)*1000:.1f} ms)")
print(f"  20-feature extraction: {np.mean(times_20)*1000:>8.1f} ms  (std: {np.std(times_20)*1000:.1f} ms)")
print(f"  Ratio: {np.mean(times_20)/np.mean(times_5):.1f}x slower")

# =====================================================================
# Summary
# =====================================================================
print("\n" + "=" * 70)
print("SUMMARY: COMPUTATIONAL COST COMPARISON")
print("=" * 70)

# Total pipeline time estimate
old_total = np.mean(times_5) + grid_results[1]['total_time']  # 5feat extraction + CatBoost GridCV
new_total = np.mean(times_20) + sum(g['total_time'] for g in grid_results[2:])  # 20feat + all new grids

print(f"\n  Old pipeline (5feat + CatBoost GridCV):")
print(f"    Feature extraction:  {np.mean(times_5):.1f}s")
print(f"    CatBoost GridCV:     {grid_results[1]['total_time']:.1f}s")
print(f"    TOTAL:               {old_total:.1f}s")

print(f"\n  New pipeline (20feat + all 5 model GridCVs):")
print(f"    Feature extraction:  {np.mean(times_20):.1f}s")
for g in grid_results[2:]:
    print(f"    {g['name']:<30s} {g['total_time']:.1f}s")
print(f"    TOTAL:               {new_total:.1f}s")

print(f"\n  New pipeline is {new_total/old_total:.1f}x the computational cost of the old pipeline")
print(f"  But Ridge alone (20feat): {np.mean(times_20) + grid_results[2]['total_time']:.1f}s "
      f"({(np.mean(times_20) + grid_results[2]['total_time'])/old_total:.2f}x old)")
