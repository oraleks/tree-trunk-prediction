"""
Evaluate the old model's feature set and configuration using the same
rigorous methodology as the new model evaluation.
"""

import numpy as np
import pandas as pd
import geopandas as gpd
import math
import warnings
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from scipy.stats import spearmanr
from sklearn.model_selection import train_test_split, KFold, GridSearchCV
from sklearn.linear_model import Ridge
from catboost import CatBoostRegressor

warnings.filterwarnings('ignore')

# =====================================================================
# Replicate OLD MODEL feature computation exactly
# (lines 39-46 of old_model/app.py, eccentricity from old_model/funcs.py)
# =====================================================================
gdf = gpd.read_file('train_set_validated.shp').to_crs(epsg=2039)
gdf = gdf.explode(index_parts=False).reset_index(drop=True)
gdf = gdf[gdf.geometry.type == 'Polygon'].copy()

# Old model features
gdf['perimter'] = gdf.length
gdf['area'] = gdf.area
gdf['compactness'] = (4 * 3.14159265359 * gdf['area']) / (gdf['perimter'] ** 2)
gdf['perimeter_to_area'] = gdf.length / gdf.area

# Old MRR axis computation (BUGGY - uses axis-aligned bbox of MRR)
def old_mrr_axes(geom):
    mrr = geom.minimum_rotated_rectangle
    xs = list(mrr.exterior.xy[0])
    ys = list(mrr.exterior.xy[1])
    major = max(xs) - min(xs)
    minor = max(ys) - min(ys)
    return major, minor

gdf[['major_axis_length', 'minor_axis_length']] = gdf.geometry.apply(
    lambda g: pd.Series(old_mrr_axes(g))
)

# Old eccentricity
def old_eccentricity(row):
    major = row['major_axis_length']
    minor = row['minor_axis_length']
    if major == minor:
        return 0
    if minor > major:
        major, minor = minor, major
    arg = np.clip(1 - (minor ** 2 / max(major ** 2, 1)), 0, 1)
    return math.sqrt(arg)

gdf['eccentricity'] = gdf.apply(old_eccentricity, axis=1)

OLD_FEATURES = ['perimter', 'area', 'compactness', 'perimeter_to_area', 'eccentricity']
TARGET = 'Point_Coun'

data = gdf[OLD_FEATURES + [TARGET]].dropna()
X, y = data[OLD_FEATURES], data[TARGET]


def ev(yt, yp):
    mae = mean_absolute_error(yt, yp)
    rmse = np.sqrt(mean_squared_error(yt, yp))
    r2 = r2_score(yt, yp)
    rho, _ = spearmanr(yt, yp)
    w1 = np.mean(np.abs(yt - yp) <= 1) * 100
    w2 = np.mean(np.abs(yt - yp) <= 2) * 100
    return mae, rmse, r2, rho, w1, w2


def print_metrics(label, yt, yp):
    mae, rmse, r2, rho, w1, w2 = ev(yt, yp)
    print(f"  {label}")
    print(f"    MAE={mae:.2f}  RMSE={rmse:.2f}  R2={r2:.3f}  "
          f"Spearman={rho:.3f}  W+/-1={w1:.1f}%  W+/-2={w2:.1f}%")
    return mae, rmse, r2, rho, w1, w2


cv = KFold(n_splits=5, shuffle=True, random_state=42)

# =====================================================================
# FULL RANGE (2-44)
# =====================================================================
print("=" * 70)
print("OLD MODEL EVALUATION - FULL RANGE (2-44)")
print(f"Features: {OLD_FEATURES}")
print(f"Dataset: {len(data)} polygons")
print("=" * 70)

bins = [0, 3, 5, 8, 15, 100]
yb = pd.cut(y, bins=bins, labels=False)
Xtr, Xte, ytr, yte = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=yb
)
print(f"Train: {len(Xtr)}, Test: {len(Xte)}")
print()

# 1. Old model EXACT config (no tuning, default CatBoost + early stopping)
print("--- CatBoost with OLD exact config (no tuning) ---")
old_cb = CatBoostRegressor(
    task_type='GPU', od_type='IncToDec', od_pval=0.001,
    od_wait=100, verbose=0, random_seed=42
)
old_cb.fit(Xtr, ytr)
pred = np.clip(np.round(old_cb.predict(Xte)), 1, None)
print_metrics("Full range", yte.values, pred)
imp = old_cb.get_feature_importance()
print(f"    Feature importance: {dict(zip(OLD_FEATURES, [round(v, 1) for v in imp]))}")
m8 = yte <= 8
print_metrics(f"<=8 subset (n={m8.sum()})", yte[m8].values, pred[m8])
print()

# 2. CatBoost with grid search (same features, tuned)
print("--- CatBoost with grid search (old features, tuned) ---")
grid = GridSearchCV(
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=42, loss_function='RMSE'),
    {'iterations': [100, 300, 500, 1000], 'depth': [3, 5, 7],
     'learning_rate': [0.01, 0.05, 0.1]},
    cv=cv, scoring='neg_mean_absolute_error', refit=True, n_jobs=1
)
grid.fit(Xtr, ytr)
pred_tuned = np.clip(np.round(grid.predict(Xte)), 1, None)
print(f"  Best params: {grid.best_params_}")
print_metrics("Full range", yte.values, pred_tuned)
imp = grid.best_estimator_.get_feature_importance()
print(f"    Feature importance: {dict(zip(OLD_FEATURES, [round(v, 1) for v in imp]))}")
print_metrics(f"<=8 subset (n={m8.sum()})", yte[m8].values, pred_tuned[m8])
print()

# 3. Ridge with old features
print("--- Ridge with old features ---")
rg = GridSearchCV(
    Ridge(), {'alpha': [0.1, 1, 10, 100]},
    cv=cv, scoring='neg_mean_absolute_error', refit=True
)
rg.fit(Xtr, ytr)
pred_r = np.clip(np.round(rg.predict(Xte)), 1, None)
print(f"  Best alpha: {rg.best_params_['alpha']}")
print_metrics("Full range", yte.values, pred_r)
print_metrics(f"<=8 subset (n={m8.sum()})", yte[m8].values, pred_r[m8])
print()

# =====================================================================
# DEDICATED <=8 MODELS
# =====================================================================
print("=" * 70)
print("OLD MODEL EVALUATION - DEDICATED <=8 MODELS")
print("=" * 70)

d8 = data[data[TARGET] <= 8]
X8, y8 = d8[OLD_FEATURES], d8[TARGET]
yb8 = pd.cut(y8, bins=[0, 3, 5, 9], labels=False)
X8tr, X8te, y8tr, y8te = train_test_split(
    X8, y8, test_size=0.2, random_state=42, stratify=yb8
)
print(f"Train: {len(X8tr)}, Test: {len(X8te)}")
print()

# 1. Old exact config on <=8
print("--- CatBoost OLD config (no tuning) on <=8 ---")
old_cb8 = CatBoostRegressor(
    task_type='GPU', od_type='IncToDec', od_pval=0.001,
    od_wait=100, verbose=0, random_seed=42
)
old_cb8.fit(X8tr, y8tr)
pred8 = np.clip(np.round(old_cb8.predict(X8te)), 1, None)
print_metrics("<=8 dedicated", y8te.values, pred8)
imp8 = old_cb8.get_feature_importance()
print(f"    Feature importance: {dict(zip(OLD_FEATURES, [round(v, 1) for v in imp8]))}")
err = np.abs(y8te.values - pred8)
for lo, hi, lb in [(2, 3, '2-3'), (4, 5, '4-5'), (6, 8, '6-8')]:
    mk = (y8te.values >= lo) & (y8te.values <= hi)
    if mk.sum() > 0:
        print(f"    {lb}: n={mk.sum()}, mean_err={err[mk].mean():.2f}")
print()

# 2. CatBoost tuned on <=8
print("--- CatBoost tuned on <=8 ---")
grid8 = GridSearchCV(
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=42, loss_function='RMSE'),
    {'iterations': [100, 300, 500, 1000], 'depth': [3, 5, 7],
     'learning_rate': [0.01, 0.05, 0.1]},
    cv=cv, scoring='neg_mean_absolute_error', refit=True, n_jobs=1
)
grid8.fit(X8tr, y8tr)
pred8t = np.clip(np.round(grid8.predict(X8te)), 1, None)
print(f"  Best params: {grid8.best_params_}")
print_metrics("<=8 dedicated", y8te.values, pred8t)
imp8t = grid8.best_estimator_.get_feature_importance()
print(f"    Feature importance: {dict(zip(OLD_FEATURES, [round(v, 1) for v in imp8t]))}")
err = np.abs(y8te.values - pred8t)
for lo, hi, lb in [(2, 3, '2-3'), (4, 5, '4-5'), (6, 8, '6-8')]:
    mk = (y8te.values >= lo) & (y8te.values <= hi)
    if mk.sum() > 0:
        print(f"    {lb}: n={mk.sum()}, mean_err={err[mk].mean():.2f}")
print()

# 3. Ridge on <=8
print("--- Ridge on <=8 ---")
rg8 = GridSearchCV(
    Ridge(), {'alpha': [0.01, 0.1, 1, 10, 100]},
    cv=cv, scoring='neg_mean_absolute_error', refit=True
)
rg8.fit(X8tr, y8tr)
pred8r = np.clip(np.round(rg8.predict(X8te)), 1, None)
print(f"  Best alpha: {rg8.best_params_['alpha']}")
print_metrics("<=8 dedicated", y8te.values, pred8r)
err = np.abs(y8te.values - pred8r)
for lo, hi, lb in [(2, 3, '2-3'), (4, 5, '4-5'), (6, 8, '6-8')]:
    mk = (y8te.values >= lo) & (y8te.values <= hi)
    if mk.sum() > 0:
        print(f"    {lb}: n={mk.sum()}, mean_err={err[mk].mean():.2f}")
print()

# =====================================================================
# COMPARISON SUMMARY
# =====================================================================
print("=" * 70)
print("COMPARISON: OLD (5 features) vs NEW (20 features)")
print("=" * 70)
print()
print("Full range (2-44):")
header = f"  {'Model':<40s} {'MAE':>5s} {'RMSE':>6s} {'R2':>6s} {'W+/-1':>6s} {'W+/-2':>6s}"
print(header)
print("  " + "-" * (len(header) - 2))
for label, yt, yp in [
    ("Old CatBoost (no tuning, 5feat)", yte.values, np.clip(np.round(old_cb.predict(Xte)), 1, None)),
    ("Old CatBoost (tuned, 5feat)", yte.values, pred_tuned),
    ("Old Ridge (5feat)", yte.values, pred_r),
    ("NEW Ridge (20feat)", None, None),
    ("NEW CatBoost RMSE (20feat)", None, None),
]:
    if yt is not None:
        m, rm, r2, rho, w1, w2 = ev(yt, yp)
        print(f"  {label:<40s} {m:>5.2f} {rm:>6.2f} {r2:>6.3f} {w1:>5.1f}% {w2:>5.1f}%")
    else:
        print(f"  {label:<40s}   (see results.MD: 1.52/3.17/.731 and 1.64/3.46/.680)")

print()
print("Dedicated <=8:")
print(header)
print("  " + "-" * (len(header) - 2))
for label, yt, yp in [
    ("Old CatBoost (no tuning, 5feat)", y8te.values, np.clip(np.round(old_cb8.predict(X8te)), 1, None)),
    ("Old CatBoost (tuned, 5feat)", y8te.values, pred8t),
    ("Old Ridge (5feat)", y8te.values, pred8r),
    ("NEW CatBoost RMSE (20feat)", None, None),
    ("NEW Ridge (20feat)", None, None),
]:
    if yt is not None:
        m, rm, r2, rho, w1, w2 = ev(yt, yp)
        print(f"  {label:<40s} {m:>5.2f} {rm:>6.2f} {r2:>6.3f} {w1:>5.1f}% {w2:>5.1f}%")
    else:
        print(f"  {label:<40s}   (see results.MD: 0.79/1.13/.573 and 0.86/1.16/.551)")
