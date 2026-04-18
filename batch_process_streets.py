"""
Batch street network processing pipeline.

Takes raw street segment shapefiles and produces dissolved, cleaned street
network polygons ready for downstream analysis (e.g., street tree filtering).

Pipeline steps for each XXX_street_segments.shp:
1. Reproject to EPSG:2039 (metric, Israel TM Grid)
2. Strip Z coordinates (some files are PolygonZ)
3. Repair invalid geometries (make_valid + buffer(0))
4. Dissolve all segments via unary_union (merges adjacent segments)
5. Close thin sliver gaps: buffer(+0.5m) then buffer(-0.5m)
6. Remove small holes (<50 m^2) from inaccurate drawing
7. Save as XXX_street_network_polygon.shp

Usage:
    # Process all cities with street segment data
    python batch_process_streets.py

    # Process specific cities
    python batch_process_streets.py BTR TLV HAI

Input:  d:/OneDrive - Technion/Research/Shade Maps/Israel streets/XXX_street_segments.shp
Output: d:/OneDrive - Technion/Research/Shade Maps/Israel streets/XXX_street_network_polygon.shp
"""

import os
import sys
import glob
import time
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union
from shapely.validation import make_valid
import warnings

warnings.filterwarnings('ignore')

STREETS_DIR = r"d:\OneDrive - Technion\Research\Shade Maps\Israel streets"
TARGET_CRS = 2039

# Sliver gap closure buffer (meters)
SLIVER_BUFFER = 0.5
# Minimum hole area (m^2) below which interior rings are filled
MIN_HOLE_AREA = 50.0


# =====================================================================
# Geometry helpers
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
    """Repair a single geometry: strip Z, fix invalidity."""
    if geom is None or geom.is_empty:
        return None
    geom = strip_z(geom)
    if not geom.is_valid:
        geom = make_valid(geom)
        if geom is None or geom.is_empty:
            return None
    if not geom.is_valid:
        geom = geom.buffer(0)
        if geom is None or geom.is_empty:
            return None
    return geom


def extract_polygon_parts(geom):
    """Extract only Polygon/MultiPolygon parts from a GeometryCollection."""
    if geom is None or geom.is_empty:
        return geom
    if geom.geom_type == 'GeometryCollection':
        polys = [g for g in geom.geoms if g.geom_type in ('Polygon', 'MultiPolygon')]
        if not polys:
            return None
        return unary_union(polys)
    return geom


def remove_small_holes(geom, min_area):
    """Remove interior rings (holes) smaller than min_area."""
    if geom is None or geom.is_empty:
        return geom
    if geom.geom_type == 'Polygon':
        new_interiors = [ring for ring in geom.interiors if Polygon(ring).area >= min_area]
        return Polygon(geom.exterior, new_interiors)
    elif geom.geom_type == 'MultiPolygon':
        return MultiPolygon([remove_small_holes(p, min_area) for p in geom.geoms])
    return geom


# =====================================================================
# Main processing
# =====================================================================

def process_city(city_code, streets_dir=STREETS_DIR):
    """Process one city's street segments into a cleaned network polygon."""
    seg_file = os.path.join(streets_dir, f"{city_code}_street_segments.shp")
    out_file = os.path.join(streets_dir, f"{city_code}_street_network_polygon.shp")

    if not os.path.exists(seg_file):
        print(f"  ERROR: Street segments file not found: {os.path.basename(seg_file)}")
        return None

    t0 = time.time()

    # Step 1: Load
    gdf = gpd.read_file(seg_file)
    n_segments = len(gdf)

    # Step 2: Reproject to metric CRS
    if gdf.crs is None:
        print(f"  WARNING: No CRS defined, assuming EPSG:{TARGET_CRS}")
        gdf = gdf.set_crs(epsg=TARGET_CRS)
    elif gdf.crs.to_epsg() != TARGET_CRS:
        gdf = gdf.to_crs(epsg=TARGET_CRS)

    # Step 3: Strip Z and repair
    gdf['geometry'] = gdf.geometry.apply(strip_z).apply(repair_geometry)
    gdf = gdf[gdf.geometry.notna()].copy()

    # Step 4: Dissolve
    merged = unary_union(gdf.geometry.values)
    merged = repair_geometry(merged)
    if merged is None or merged.is_empty:
        print(f"  ERROR: Dissolve produced empty geometry")
        return None
    merged = extract_polygon_parts(merged)

    # Step 5: Close sliver gaps (buffer out then back in)
    merged = merged.buffer(SLIVER_BUFFER).buffer(-SLIVER_BUFFER)
    merged = repair_geometry(merged)
    if merged is None or merged.is_empty:
        print(f"  ERROR: Buffer cleanup produced empty geometry")
        return None
    merged = extract_polygon_parts(merged)

    # Step 6: Remove small holes
    merged = remove_small_holes(merged, MIN_HOLE_AREA)

    # Compute stats
    n_parts = len(merged.geoms) if merged.geom_type == 'MultiPolygon' else 1
    total_area_km2 = merged.area / 1e6
    elapsed = time.time() - t0

    # Step 7: Save
    out_gdf = gpd.GeoDataFrame(geometry=[merged], crs=f"EPSG:{TARGET_CRS}")
    out_gdf.to_file(out_file)

    print(f"  {n_segments:,} segments -> {n_parts:,} parts, {total_area_km2:.2f} km2 ({elapsed:.1f}s)")
    print(f"  Saved: {os.path.basename(out_file)}")

    return {
        'city': city_code,
        'n_segments': n_segments,
        'n_parts': n_parts,
        'area_km2': total_area_km2,
    }


def main():
    os.makedirs(STREETS_DIR, exist_ok=True)

    # Determine which cities to process
    if len(sys.argv) > 1:
        cities = sys.argv[1:]
        print(f"Processing specified cities: {', '.join(cities)}")
    else:
        # Find all cities with street segment data
        seg_files = sorted(glob.glob(os.path.join(STREETS_DIR, '*_street_segments.shp')))
        cities = [os.path.basename(f).replace('_street_segments.shp', '') for f in seg_files]
        print(f"Processing all {len(cities)} cities with street segment data")

    print(f"{'='*60}")
    print(f"Street Network Processing")
    print(f"Target CRS: EPSG:{TARGET_CRS}")
    print(f"Sliver gap buffer: {SLIVER_BUFFER} m")
    print(f"Minimum hole area: {MIN_HOLE_AREA} m2")
    print(f"{'='*60}")

    t_total = time.time()
    results = []
    failed = []

    for i, city in enumerate(cities):
        print(f"\n[{i+1}/{len(cities)}] {city}")
        result = process_city(city)
        if result:
            results.append(result)
        else:
            failed.append(city)

    elapsed = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"Done. Processed {len(results)}/{len(cities)} cities in {elapsed:.0f}s")

    if results:
        print(f"\n{'City':<6s} {'Segments':>10s} {'Parts':>8s} {'Area (km2)':>12s}")
        print(f"{'-'*6} {'-'*10} {'-'*8} {'-'*12}")
        for r in results:
            print(f"{r['city']:<6s} {r['n_segments']:>10,} {r['n_parts']:>8,} {r['area_km2']:>12.2f}")

    if failed:
        print(f"\nFailed: {', '.join(failed)}")


if __name__ == '__main__':
    main()
