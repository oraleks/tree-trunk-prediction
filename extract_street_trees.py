"""
Extract street tree trunks for 17 cities.

For each city with street segment data:
1. Load the street network polygon (already dissolved and cleaned)
2. Buffer it by 2m to capture front-yard trees near street edges
3. Filter tree trunk points: keep those inside the buffered street polygon
4. Save as XXX_tree_trunks_YYYY_streets.shp

Usage:
    python extract_street_trees.py

Input:
    d:/OneDrive - Technion/Research/Shade Maps/Israel streets/XXX_street_network_polygon.shp
    d:/OneDrive - Technion/Research/Shade Maps/Israel trees/XXX_tree_trunks_YYYY.shp

Output:
    d:/OneDrive - Technion/Research/Shade Maps/Israel trees/XXX_tree_trunks_YYYY_streets.shp
"""

import os
import glob
import time
import geopandas as gpd
from shapely.prepared import prep
import warnings

warnings.filterwarnings('ignore')

STREETS_DIR = r"d:\OneDrive - Technion\Research\Shade Maps\Israel streets"
TREES_DIR = r"d:\OneDrive - Technion\Research\Shade Maps\Israel trees"
TARGET_CRS = 2039
BUFFER_DIST = 2.0  # meters -- captures front-yard trees near street edges


def filter_street_trunks(city_code, streets_dir=STREETS_DIR, trees_dir=TREES_DIR):
    """Filter tree trunk points to those inside the buffered street polygon."""

    # Load street network polygon
    street_file = os.path.join(streets_dir, f"{city_code}_street_network_polygon.shp")
    if not os.path.exists(street_file):
        print(f"  ERROR: Street polygon not found: {os.path.basename(street_file)}")
        return None

    street_gdf = gpd.read_file(street_file)
    street_polygon = street_gdf.geometry.iloc[0]

    # Buffer by 2m to capture front-yard trees
    buffered = street_polygon.buffer(BUFFER_DIST)
    buffered_prep = prep(buffered)

    # Find trunk file
    trunk_pattern = os.path.join(trees_dir, f"{city_code}_tree_trunks_*.shp")
    trunk_files = [f for f in glob.glob(trunk_pattern) if '_streets' not in f]
    if not trunk_files:
        print(f"  ERROR: No trunk file found for {city_code}")
        return None

    trunk_file = trunk_files[0]
    year = os.path.basename(trunk_file).split('_tree_trunks_')[1].replace('.shp', '')
    out_file = os.path.join(trees_dir, f"{city_code}_tree_trunks_{year}_streets.shp")

    # Load trunk points
    gdf = gpd.read_file(trunk_file)
    n_total = len(gdf)

    # Ensure matching CRS
    if gdf.crs is not None and gdf.crs.to_epsg() != TARGET_CRS:
        gdf = gdf.to_crs(epsg=TARGET_CRS)

    # Filter: keep points inside buffered street polygon
    mask = gdf.geometry.apply(lambda pt: buffered_prep.contains(pt))
    street_trees = gdf[mask].copy()
    n_street = len(street_trees)
    pct = n_street / n_total * 100 if n_total > 0 else 0

    # Save
    street_trees.to_file(out_file)
    print(f"  Street trees: {n_street:,} / {n_total:,} ({pct:.1f}%)")
    print(f"  Saved: {os.path.basename(out_file)}")

    return {
        'city': city_code,
        'year': year,
        'n_total': n_total,
        'n_street': n_street,
        'pct_street': pct,
    }


def main():
    # Find cities with street network polygons
    poly_files = sorted(glob.glob(os.path.join(STREETS_DIR, '*_street_network_polygon.shp')))
    cities = [os.path.basename(f).replace('_street_network_polygon.shp', '') for f in poly_files]

    print(f"{'='*60}")
    print(f"Street Tree Trunk Extraction")
    print(f"Cities with street data: {len(cities)}")
    print(f"Buffer: {BUFFER_DIST}m beyond street edges")
    print(f"{'='*60}")

    t_total = time.time()
    results = []

    for i, city in enumerate(cities):
        print(f"\n[{i+1}/{len(cities)}] {city}")
        t0 = time.time()
        result = filter_street_trunks(city)
        if result:
            results.append(result)
        print(f"  ({time.time()-t0:.1f}s)")

    # Summary
    elapsed = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"Done. Processed {len(results)}/{len(cities)} cities in {elapsed:.0f}s")
    print(f"\n{'City':<6s} {'Total':>10s} {'Street':>10s} {'%':>7s}")
    print(f"{'-'*6} {'-'*10} {'-'*10} {'-'*7}")
    total_all = 0
    total_street = 0
    for r in results:
        print(f"{r['city']:<6s} {r['n_total']:>10,} {r['n_street']:>10,} {r['pct_street']:>6.1f}%")
        total_all += r['n_total']
        total_street += r['n_street']
    print(f"{'-'*6} {'-'*10} {'-'*10} {'-'*7}")
    pct = total_street / total_all * 100 if total_all > 0 else 0
    print(f"{'TOTAL':<6s} {total_all:>10,} {total_street:>10,} {pct:>6.1f}%")


if __name__ == '__main__':
    main()
