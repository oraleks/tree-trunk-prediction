"""
Batch tree trunk point generation from predicted shapefiles.

Usage:
    python batch_generate_points.py path/to/folder/
    python batch_generate_points.py file1_predicted.shp file2_predicted.shp ...

For each *_predicted.shp file (output of batch_predict_trees.py),
generates a point shapefile of estimated tree trunk locations.

Input:  XXX_tree_canopies_YYYY_predicted.shp
Output: XXX_tree_trunks_YYYY.shp

Each point carries:
  - poly_id:   ID of the source polygon
  - tree_idx:  tree index within the polygon (1..N)
  - pred_trees: total predicted trees in the source polygon
  - crown_area: estimated crown area per tree (polygon area / N)
  - crown_diam: estimated crown diameter (2 * sqrt(crown_area / pi))

Tree placement uses constrained k-means (CVT approximation) to
distribute points evenly inside each polygon.
"""

import sys
import os
import glob
import time
import math
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
from sklearn.cluster import KMeans
import warnings

warnings.filterwarnings('ignore')


# =====================================================================
# Tree point generation (from tree_point_generator.py, streamlined)
# =====================================================================

def _sample_points_in_polygon(polygon, n_samples, rng):
    """Sample points uniformly inside a polygon via vectorized rejection sampling."""
    from shapely.vectorized import contains
    minx, miny, maxx, maxy = polygon.bounds
    points = []
    while len(points) < n_samples:
        batch_size = (n_samples - len(points)) * 3
        xs = rng.uniform(minx, maxx, batch_size)
        ys = rng.uniform(miny, maxy, batch_size)
        mask = contains(polygon, xs, ys)
        inside = np.column_stack((xs[mask], ys[mask]))
        points.extend(inside.tolist())
    return np.array(points[:n_samples])


def _snap_to_polygon(cx, cy, polygon):
    """Snap a point inside the polygon if it fell outside."""
    p = Point(cx, cy)
    if polygon.contains(p):
        return cx, cy
    nearest = polygon.boundary.interpolate(polygon.boundary.project(p))
    pcx, pcy = polygon.centroid.x, polygon.centroid.y
    return nearest.x + 0.1 * (pcx - nearest.x), nearest.y + 0.1 * (pcy - nearest.y)


def generate_points(polygon, n_trees, n_samples=1000, rng=None):
    """Generate N evenly-distributed points inside a polygon."""
    if polygon is None or polygon.is_empty:
        return []

    n_trees = max(1, int(n_trees))

    if n_trees == 1:
        centroid = polygon.centroid
        if polygon.contains(centroid):
            return [(centroid.x, centroid.y)]
        rp = polygon.representative_point()
        return [(rp.x, rp.y)]

    if rng is None:
        rng = np.random.default_rng(42)

    n_actual = max(n_samples, n_trees * 20)
    try:
        candidates = _sample_points_in_polygon(polygon, n_actual, rng)
    except Exception:
        rp = polygon.representative_point()
        return [(rp.x, rp.y)] * n_trees

    if len(candidates) < n_trees:
        rp = polygon.representative_point()
        return [(rp.x, rp.y)] * n_trees

    kmeans = KMeans(n_clusters=n_trees, random_state=42, n_init=3, max_iter=100)
    kmeans.fit(candidates)

    points = []
    for c in kmeans.cluster_centers_:
        sx, sy = _snap_to_polygon(c[0], c[1], polygon)
        points.append((sx, sy))

    return points


# =====================================================================
# Process one file
# =====================================================================

def process_file(shp_path, n_samples=500):
    """Generate tree trunk points for all polygons in a predicted shapefile."""
    basename = os.path.splitext(os.path.basename(shp_path))[0]
    # Transform: XXX_tree_canopies_YYYY_predicted -> XXX_tree_trunks_YYYY
    out_name = basename.replace('_tree_canopies_', '_tree_trunks_').replace('_predicted', '')
    out_dir = os.path.dirname(shp_path) or '.'
    out_path = os.path.join(out_dir, f"{out_name}.shp")

    print(f"\nProcessing: {shp_path}")
    t0 = time.time()

    gdf = gpd.read_file(shp_path)
    original_crs = gdf.crs
    n_polygons = len(gdf)

    # Reproject to metric CRS if needed (for correct area computation and point placement)
    TARGET_CRS = 2039
    if gdf.crs is not None and not gdf.crs.is_projected:
        print(f"  Reprojecting from {gdf.crs} to EPSG:{TARGET_CRS} (metric)")
        gdf = gdf.to_crs(epsg=TARGET_CRS)

    # Determine the prediction column name
    if 'pred_trees' in gdf.columns:
        count_col = 'pred_trees'
    elif 'pred_trunk' in gdf.columns:
        count_col = 'pred_trunk'
    else:
        print(f"  ERROR: No prediction column found. Skipping.")
        return None

    total_trees = int(gdf[count_col].sum())
    print(f"  Polygons: {n_polygons:,}, Total predicted trees: {total_trees:,}")

    rng = np.random.default_rng(42)

    # Build point records
    records = []
    n_done = 0
    t_report = time.time()

    for idx, row in gdf.iterrows():
        n_trees = int(row[count_col])
        if n_trees < 1:
            continue

        polygon = row.geometry
        poly_area = polygon.area
        crown_area = poly_area / n_trees
        crown_diam = 2 * math.sqrt(crown_area / math.pi) if crown_area > 0 else 0.0

        points = generate_points(polygon, n_trees, n_samples=n_samples, rng=rng)

        for i, (px, py) in enumerate(points):
            records.append({
                'geometry': Point(px, py),
                'poly_id': idx,
                'tree_idx': i + 1,
                'pred_tree': n_trees,
                'crown_area': round(crown_area, 1),
                'crown_diam': round(crown_diam, 1),
            })

        n_done += 1
        if time.time() - t_report > 30:
            print(f"    Progress: {n_done:,}/{n_polygons:,} polygons, "
                  f"{len(records):,} points ({time.time()-t0:.0f}s)")
            t_report = time.time()

    # Create output GeoDataFrame
    points_gdf = gpd.GeoDataFrame(records, crs=gdf.crs)

    # Reproject back to original CRS if we reprojected
    if original_crs is not None and original_crs != gdf.crs:
        points_gdf = points_gdf.to_crs(original_crs)

    # Save
    points_gdf.to_file(out_path)
    elapsed = time.time() - t0

    print(f"  Generated {len(points_gdf):,} tree points from {n_done:,} polygons")
    print(f"  Crown area: mean={points_gdf['crown_area'].mean():.1f} m², "
          f"median={points_gdf['crown_area'].median():.1f} m²")
    print(f"  Crown diameter: mean={points_gdf['crown_diam'].mean():.1f} m, "
          f"median={points_gdf['crown_diam'].median():.1f} m")
    print(f"  Saved: {out_path} ({elapsed:.1f}s)")
    return out_path


# =====================================================================
# Main
# =====================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python batch_generate_points.py <folder/> [file1_predicted.shp ...]")
        print("  Generates tree trunk point layers from *_predicted.shp files.")
        print("  Input:  XXX_tree_canopies_YYYY_predicted.shp")
        print("  Output: XXX_tree_trunks_YYYY.shp")
        sys.exit(1)

    # Collect input files
    shp_files = []
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            found = glob.glob(os.path.join(arg, '*_predicted.shp'))
            shp_files.extend(sorted(found))
        elif os.path.isfile(arg) and arg.lower().endswith('.shp'):
            shp_files.append(arg)
        else:
            print(f"WARNING: Skipping '{arg}'")

    if not shp_files:
        print("No *_predicted.shp files found.")
        sys.exit(1)

    print(f"Found {len(shp_files)} file(s) to process")

    t_total = time.time()
    results = []
    for shp in shp_files:
        out = process_file(shp)
        if out:
            results.append(out)

    elapsed_total = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"Done. Generated points for {len(results)}/{len(shp_files)} files in {elapsed_total:.1f}s")
    for r in results:
        print(f"  -> {r}")


if __name__ == '__main__':
    main()
