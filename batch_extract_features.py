"""
Batch morphological feature extraction for multiple shapefiles.

Usage:
    python batch_extract_features.py path/to/file1.shp path/to/file2.shp ...
    python batch_extract_features.py path/to/folder/   (processes all .shp in folder)

For each input file, outputs a new shapefile with 20 morphological features
appended as columns.

Expected naming convention: XXX_tree_canopies_YYYY.shp
  -> output: XXX_tree_canopies_YYYY_processed.shp

Before feature extraction, all polygon geometries are repaired:
  - Invalid geometries fixed via buffer(0) and make_valid
  - Z coordinates stripped (2D only)
  - MultiPolygons exploded to individual Polygons
  - Empty and non-polygon geometries removed
  - Contained (nested) polygons removed
"""

import sys
import os
import glob
import time
import numpy as np
import pandas as pd
import geopandas as gpd
import math
import warnings
from shapely.geometry import Polygon, MultiPolygon
from shapely.validation import make_valid

warnings.filterwarnings('ignore')

TARGET_CRS = 2039  # EPSG:2039 Israel Transverse Mercator (meters)

# =====================================================================
# Geometry repair
# =====================================================================

def strip_z(geom):
    """Remove Z dimension from a geometry."""
    if geom is None or geom.is_empty:
        return geom
    if geom.has_z:
        if geom.geom_type == 'Polygon':
            exterior = [(x, y) for x, y, *_ in geom.exterior.coords]
            interiors = [[(x, y) for x, y, *_ in ring.coords] for ring in geom.interiors]
            return Polygon(exterior, interiors)
        elif geom.geom_type == 'MultiPolygon':
            return MultiPolygon([strip_z(p) for p in geom.geoms])
    return geom


def repair_geometry(geom):
    """Repair a single geometry: fix invalidity, strip Z, ensure Polygon."""
    if geom is None or geom.is_empty:
        return None

    # Strip Z coordinates
    geom = strip_z(geom)

    # Fix invalid geometries
    if not geom.is_valid:
        geom = make_valid(geom)
        if geom is None or geom.is_empty:
            return None

    # buffer(0) as a fallback for remaining issues
    if not geom.is_valid:
        geom = geom.buffer(0)
        if geom is None or geom.is_empty:
            return None

    return geom


def prepare_geodataframe(gdf, target_crs=TARGET_CRS):
    """Clean and prepare a GeoDataFrame for feature extraction.

    Steps:
    1. Reproject to target CRS (metric units)
    2. Repair all geometries
    3. Explode MultiPolygons
    4. Remove non-polygon and empty geometries
    5. Remove contained (nested) polygons
    """
    n_original = len(gdf)
    print(f"  Original: {n_original} features, CRS={gdf.crs}")

    # Reproject
    if gdf.crs is None:
        print(f"  WARNING: No CRS defined, assuming EPSG:{target_crs}")
        gdf = gdf.set_crs(epsg=target_crs)
    else:
        gdf = gdf.to_crs(epsg=target_crs)

    # Repair geometries
    n_invalid = (~gdf.geometry.is_valid).sum()
    gdf['geometry'] = gdf.geometry.apply(repair_geometry)
    n_after_repair = gdf.geometry.notna().sum()
    if n_invalid > 0:
        print(f"  Repaired {n_invalid} invalid geometries ({n_original - n_after_repair} could not be fixed)")

    # Drop rows with None geometry
    gdf = gdf[gdf.geometry.notna()].copy()

    # Explode MultiPolygons
    n_before_explode = len(gdf)
    gdf = gdf.explode(index_parts=False).reset_index(drop=True)
    if len(gdf) > n_before_explode:
        print(f"  Exploded MultiPolygons: {n_before_explode} -> {len(gdf)}")

    # Keep only Polygons
    gdf = gdf[gdf.geometry.type == 'Polygon'].copy()

    # Remove very small polygons (likely artifacts)
    min_area = 1.0  # 1 m^2
    n_tiny = (gdf.geometry.area < min_area).sum()
    if n_tiny > 0:
        gdf = gdf[gdf.geometry.area >= min_area].copy()
        print(f"  Removed {n_tiny} tiny polygons (< {min_area} m^2)")

    # Remove contained polygons
    gdf = gdf.reset_index(drop=True)
    sindex = gdf.sindex
    to_drop = set()
    for idx, row in gdf.iterrows():
        if idx in to_drop:
            continue
        candidates = list(sindex.query(row.geometry, predicate='contains'))
        for c in candidates:
            if c != idx and c not in to_drop:
                if row.geometry.contains(gdf.iloc[c].geometry):
                    to_drop.add(c)
    if to_drop:
        gdf = gdf.drop(index=list(to_drop)).reset_index(drop=True)
        print(f"  Removed {len(to_drop)} contained polygons")

    print(f"  Final: {len(gdf)} polygons")
    return gdf


# =====================================================================
# Feature extraction (from feature_utils.py)
# =====================================================================

def compute_mrr_axes(geom):
    mrr = geom.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)
    side1 = math.hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
    side2 = math.hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
    return max(side1, side2), min(side1, side2)


def extract_features_row(geom):
    """Extract all 20 features from a single polygon geometry."""
    area = geom.area
    perimeter = geom.length
    perimeter_to_area = perimeter / area if area > 0 else 0.0
    compactness = (4 * math.pi * area) / (perimeter ** 2) if perimeter > 0 else 0.0

    hull = geom.convex_hull
    hull_area = hull.area
    convexity = area / hull_area if hull_area > 0 else 1.0

    major, minor = compute_mrr_axes(geom)
    eccentricity = math.sqrt(np.clip(1 - (minor**2 / major**2), 0, 1)) if major > 0 else 0.0
    aspect_ratio = major / minor if minor > 0 else 0.0
    mrr_area = major * minor
    mrr_area_ratio = area / mrr_area if mrr_area > 0 else 0.0

    n_vertices = len(geom.exterior.coords) - 1
    hull_perimeter = hull.length
    boundary_sinuosity = perimeter / hull_perimeter if hull_perimeter > 0 else 1.0

    # Concavities
    diff = hull.difference(geom)
    if diff.is_empty:
        n_concavities = 0
    elif diff.geom_type == 'Polygon':
        n_concavities = 1
    elif diff.geom_type in ('MultiPolygon', 'GeometryCollection'):
        n_concavities = sum(1 for g in diff.geoms if g.geom_type == 'Polygon' and g.area > 0.01)
    else:
        n_concavities = 0

    # Radial stats
    centroid = geom.centroid
    coords = list(geom.exterior.coords)[:-1]
    dists = np.array([math.hypot(c[0] - centroid.x, c[1] - centroid.y) for c in coords])
    if len(dists) > 0:
        mean_radius = dists.mean()
        radius_std = dists.std()
        radius_cv = radius_std / mean_radius if mean_radius > 0 else 0.0
        radius_ratio = dists.min() / dists.max() if dists.max() > 0 else 1.0
    else:
        mean_radius = radius_std = radius_cv = 0.0
        radius_ratio = 1.0

    equivalent_diameter = 2 * math.sqrt(area / math.pi) if area > 0 else 0.0
    convex_hull_deficit = hull_area - area
    l_ratio = ((min(major, minor) / max(major, minor)) / (compactness ** 2)
               if minor > 0 and compactness > 0 else 0.0)

    return {
        'area': area,
        'perimeter': perimeter,
        'p_to_a': perimeter_to_area,
        'compact': compactness,
        'convexity': convexity,
        'eccentric': eccentricity,
        'major_ax': major,
        'minor_ax': minor,
        'asp_ratio': aspect_ratio,
        'mrr_a_rat': mrr_area_ratio,
        'n_vert': n_vertices,
        'sinuosity': boundary_sinuosity,
        'n_concav': n_concavities,
        'mean_rad': mean_radius,
        'rad_std': radius_std,
        'rad_cv': radius_cv,
        'rad_ratio': radius_ratio,
        'eq_diam': equivalent_diameter,
        'hull_def': convex_hull_deficit,
        'l_ratio': l_ratio,
    }


def extract_features_gdf(gdf):
    """Extract features for all polygons in a GeoDataFrame."""
    records = []
    errors = 0
    for idx, row in gdf.iterrows():
        try:
            feat = extract_features_row(row.geometry)
            records.append(feat)
        except Exception:
            errors += 1
            records.append({k: np.nan for k in [
                'area', 'perimeter', 'p_to_a', 'compact', 'convexity',
                'eccentric', 'major_ax', 'minor_ax', 'asp_ratio', 'mrr_a_rat',
                'n_vert', 'sinuosity', 'n_concav', 'mean_rad', 'rad_std',
                'rad_cv', 'rad_ratio', 'eq_diam', 'hull_def', 'l_ratio',
            ]})
    if errors > 0:
        print(f"  WARNING: {errors} polygons failed feature extraction (NaN filled)")
    feat_df = pd.DataFrame(records, index=gdf.index)
    return feat_df


# =====================================================================
# Main
# =====================================================================

def make_output_path(shp_path):
    """Generate output path following naming convention.

    Input:  XXX_tree_canopies_YYYY.shp
    Output: XXX_tree_canopies_YYYY_processed.shp
    """
    directory = os.path.dirname(shp_path) or '.'
    basename = os.path.splitext(os.path.basename(shp_path))[0]
    return os.path.join(directory, f"{basename}_processed.shp")


def process_shapefile(shp_path, target_crs=TARGET_CRS):
    """Process a single shapefile: repair, extract features, save output."""
    out_path = make_output_path(shp_path)

    print(f"\nProcessing: {shp_path}")
    t0 = time.time()

    # Load
    gdf = gpd.read_file(shp_path)
    original_crs = gdf.crs

    # Prepare
    gdf = prepare_geodataframe(gdf, target_crs=target_crs)

    if len(gdf) == 0:
        print(f"  No valid polygons remaining. Skipping.")
        return None

    # Extract features
    print(f"  Extracting 20 morphological features...")
    feat_df = extract_features_gdf(gdf)

    # Merge features into GeoDataFrame
    for col in feat_df.columns:
        gdf[col] = feat_df[col].values

    # Reproject back to original CRS for output
    if original_crs is not None:
        gdf = gdf.to_crs(original_crs)

    # Save
    gdf.to_file(out_path)
    elapsed = time.time() - t0
    print(f"  Saved: {out_path} ({len(gdf)} polygons, {elapsed:.1f}s)")
    return out_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python batch_extract_features.py <file1.shp> [file2.shp ...] [folder/]")
        print("  Input naming:  XXX_tree_canopies_YYYY.shp")
        print("  Output naming: XXX_tree_canopies_YYYY_processed.shp")
        sys.exit(1)

    # Collect input files
    shp_files = []
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            # Match naming convention XXX_tree_canopies_YYYY.shp, exclude *_processed.shp
            found = glob.glob(os.path.join(arg, '*_tree_canopies_*.shp'))
            found = [f for f in found if not f.endswith('_processed.shp')]
            if not found:
                # Fallback: all .shp except *_processed.shp
                found = glob.glob(os.path.join(arg, '*.shp'))
                found = [f for f in found if not f.endswith('_processed.shp')]
            shp_files.extend(sorted(found))
        elif os.path.isfile(arg) and arg.lower().endswith('.shp'):
            shp_files.append(arg)
        else:
            print(f"WARNING: Skipping '{arg}' (not a .shp file or directory)")

    if not shp_files:
        print("No .shp files found.")
        sys.exit(1)

    print(f"Found {len(shp_files)} shapefile(s) to process")
    print(f"Target CRS: EPSG:{TARGET_CRS}")

    t_total = time.time()
    results = []
    for shp in shp_files:
        out = process_shapefile(shp)
        if out:
            results.append(out)

    elapsed_total = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"Done. Processed {len(results)}/{len(shp_files)} files in {elapsed_total:.1f}s")
    for r in results:
        print(f"  -> {r}")


if __name__ == '__main__':
    main()
