"""
Batch tree count prediction for processed shapefiles.

Usage:
    python batch_predict_trees.py path/to/folder/
    python batch_predict_trees.py file1_processed.shp file2_processed.shp ...

For each *_processed.shp file (output of batch_extract_features.py),
predicts the number of trees per polygon and saves the result as
XXX_tree_canopies_YYYY_predicted.shp with a 'pred_trees' field.

Prediction logic:
  1. Single-tree filter: polygons with area < 150 m^2 AND compactness > 0.6
     are assumed to contain 1 tree (compact small crowns = individual trees).
  2. All other polygons: Ridge regression (5 features) trained on the
     validated training set predicts the trunk count.

Model choice: Ridge regression was selected over CatBoost because it has
higher R2 (0.736 vs 0.728) on the full range AND is ~100x faster at
prediction time -- critical for files with 100K-300K polygons.
"""

import sys
import os
import glob
import time
import math
import numpy as np
import pandas as pd
import geopandas as gpd
from sklearn.linear_model import Ridge
import warnings

warnings.filterwarnings('ignore')

TARGET_CRS = 2039
SINGLE_TREE_AREA = 150.0      # m^2
SINGLE_TREE_COMPACTNESS = 0.6  # minimum compactness for single-tree filter

# Feature columns as they appear in *_processed.shp files
# (abbreviated to 10 chars for shapefile compatibility)
FEATURE_COLS = ['perimeter', 'area', 'compact', 'p_to_a', 'eccentric']

# Corresponding full names as used in training
FEATURE_NAMES_TRAIN = ['perimeter', 'area', 'compactness', 'perimeter_to_area', 'eccentricity']


def train_model(training_shp='train_set_validated.shp'):
    """Train Ridge regression on the validated training set.

    Returns the fitted model. Training takes <1 second on 479 samples.
    """
    print("Training Ridge model on validated dataset...")
    t0 = time.time()

    gdf = gpd.read_file(training_shp).to_crs(epsg=TARGET_CRS)
    gdf = gdf.explode(index_parts=False).reset_index(drop=True)
    gdf = gdf[gdf.geometry.type == 'Polygon'].copy()

    # Compute the 5 training features
    gdf['perimeter'] = gdf.geometry.length
    gdf['area'] = gdf.geometry.area
    gdf['compactness'] = (4 * math.pi * gdf['area']) / (gdf['perimeter'] ** 2)
    gdf['perimeter_to_area'] = gdf['perimeter'] / gdf['area']

    # MRR axes for eccentricity (using old convention for consistency)
    def mrr_axes(geom):
        mrr = geom.minimum_rotated_rectangle
        coords = list(mrr.exterior.coords)
        s1 = math.hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
        s2 = math.hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
        return max(s1, s2), min(s1, s2)

    axes = gdf.geometry.apply(lambda g: pd.Series(mrr_axes(g), index=['major', 'minor']))
    gdf['major'] = axes['major']
    gdf['minor'] = axes['minor']

    def eccentricity(row):
        major, minor = row['major'], row['minor']
        if major == 0 or major == minor:
            return 0.0
        if minor > major:
            major, minor = minor, major
        return math.sqrt(np.clip(1 - (minor ** 2 / major ** 2), 0, 1))

    gdf['eccentricity'] = gdf.apply(eccentricity, axis=1)

    X = gdf[FEATURE_NAMES_TRAIN]
    y = gdf['Point_Coun']

    model = Ridge(alpha=100.0)
    model.fit(X, y)

    elapsed = time.time() - t0
    print(f"  Trained on {len(X)} samples in {elapsed:.2f}s")
    print(f"  Coefficients: {dict(zip(FEATURE_NAMES_TRAIN, [f'{c:.4f}' for c in model.coef_]))}")
    print(f"  Intercept: {model.intercept_:.4f}")
    return model


def predict_file(shp_path, model):
    """Predict tree counts for a single processed shapefile."""
    basename = os.path.splitext(os.path.basename(shp_path))[0]
    # Replace _processed with _predicted
    out_name = basename.replace('_processed', '_predicted')
    out_dir = os.path.dirname(shp_path) or '.'
    out_path = os.path.join(out_dir, f"{out_name}.shp")

    print(f"\nPredicting: {shp_path}")
    t0 = time.time()

    gdf = gpd.read_file(shp_path)
    original_crs = gdf.crs
    n_total = len(gdf)

    # Ensure we're in metric CRS for the area/compactness filter
    if gdf.crs is not None and gdf.crs.to_epsg() != TARGET_CRS:
        gdf_metric = gdf.to_crs(epsg=TARGET_CRS)
        area_col = gdf_metric.geometry.area
        compact_col = (4 * math.pi * area_col) / (gdf_metric.geometry.length ** 2)
    else:
        area_col = gdf['area']
        compact_col = gdf['compact']

    # Step 1: Single-tree filter
    single_tree_mask = (area_col < SINGLE_TREE_AREA) & (compact_col > SINGLE_TREE_COMPACTNESS)
    n_single = single_tree_mask.sum()

    # Step 2: Model prediction on remaining polygons
    multi_mask = ~single_tree_mask

    # Check all feature columns exist
    missing = [c for c in FEATURE_COLS if c not in gdf.columns]
    if missing:
        print(f"  ERROR: Missing columns {missing}. Skipping.")
        return None

    # Predict
    gdf['pred_trees'] = 0

    # Single trees
    gdf.loc[single_tree_mask, 'pred_trees'] = 1

    # Model predictions for multi-tree polygons
    if multi_mask.sum() > 0:
        X_pred = gdf.loc[multi_mask, FEATURE_COLS].copy()
        X_pred.columns = FEATURE_NAMES_TRAIN  # rename to match training column names
        raw_pred = model.predict(X_pred)
        gdf.loc[multi_mask, 'pred_trees'] = np.clip(np.round(raw_pred), 1, None).astype(int)

    # Summary stats
    predictions = gdf['pred_trees']
    elapsed = time.time() - t0

    print(f"  Polygons: {n_total:,}")
    print(f"  Single-tree (area<{SINGLE_TREE_AREA}, compact>{SINGLE_TREE_COMPACTNESS}): "
          f"{n_single:,} ({n_single/n_total*100:.1f}%)")
    print(f"  Model-predicted: {multi_mask.sum():,} ({multi_mask.sum()/n_total*100:.1f}%)")
    print(f"  Predicted range: {predictions.min()} - {predictions.max()}")
    print(f"  Mean: {predictions.mean():.2f}, Median: {predictions.median():.0f}")
    print(f"  Distribution: " + ", ".join(
        f"{k}={v}" for k, v in predictions.value_counts().sort_index().head(10).items()
    ) + (" ..." if predictions.nunique() > 10 else ""))

    # Save
    gdf.to_file(out_path)
    print(f"  Saved: {out_path} ({elapsed:.1f}s)")
    return out_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python batch_predict_trees.py <folder/> [file1_processed.shp ...]")
        print("  Predicts tree count per polygon in *_processed.shp files.")
        print("  Output: *_predicted.shp with 'pred_trees' field.")
        sys.exit(1)

    # Collect input files
    shp_files = []
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            found = glob.glob(os.path.join(arg, '*_processed.shp'))
            shp_files.extend(sorted(found))
        elif os.path.isfile(arg) and arg.lower().endswith('.shp'):
            shp_files.append(arg)
        else:
            print(f"WARNING: Skipping '{arg}' (not a .shp file or directory)")

    if not shp_files:
        print("No *_processed.shp files found.")
        sys.exit(1)

    print(f"Found {len(shp_files)} file(s) to predict")
    print(f"Single-tree filter: area < {SINGLE_TREE_AREA} m^2 AND compactness > {SINGLE_TREE_COMPACTNESS}")
    print(f"Model: Ridge regression (5 features, alpha=100)")

    # Train model
    model = train_model()

    # Process files
    t_total = time.time()
    results = []
    for shp in shp_files:
        out = predict_file(shp, model)
        if out:
            results.append(out)

    elapsed_total = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"Done. Predicted {len(results)}/{len(shp_files)} files in {elapsed_total:.1f}s")
    for r in results:
        print(f"  -> {r}")


if __name__ == '__main__':
    main()
