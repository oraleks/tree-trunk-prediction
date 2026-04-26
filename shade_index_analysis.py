"""
Street Shade Index Analysis

Computes a Shade Index (SI) for each city's street network by analyzing
cumulative solar exposure rasters (kdown, 6 August 08:00-17:00, 0.5m/pixel).

For each city:
  - Find global max solar exposure from the entire raster
  - Extract pixels inside the street network polygon
  - Per-pixel SI = 1 - (exposure / max_exposure)
  - City SI = mean(SI) across all street pixels

Outputs:
  - shade_index_data.xlsx (per-city SI stats)
  - plots_shade_index/01_si_per_city.png (ranked bar chart)
  - plots_shade_index/02_si_vs_crown_diameter.png (correlation scatter)
  - shade_index_report.md

Usage:
    python shade_index_analysis.py
"""

import os
import sys
import glob
import time
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask as rio_mask
from rasterio.windows import Window
import geopandas as gpd
from shapely.geometry import mapping
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import pearsonr, spearmanr
import warnings

warnings.filterwarnings('ignore')

SOLAR_DIR = r"d:\OneDrive - Technion\Research\Shade Maps\Israel solar exposure"
STREETS_DIR = r"d:\OneDrive - Technion\Research\Shade Maps\Israel streets"
PLOT_DIR = 'plots_shade_index'
EXCEL_FILE = 'shade_index_data.xlsx'
REPORT_FILE = 'shade_index_report.md'
STREET_TREES_EXCEL = 'street_trees_data.xlsx'  # source of median crown diameters

# City name mapping (copied from urban_forest_analysis.py to avoid import dependency)
CITY_NAMES = {
    'AFL': 'Afula', 'AKO': 'Akko', 'ASD': 'Ashdod', 'ASK': 'Ashkelon',
    'BBK': 'Bnei Brak', 'BSM': 'Beit Shemesh', 'BSV': 'Beersheva',
    'BTR': 'Beitar Ilit', 'BTY': 'Bat Yam', 'ELT': 'Eilat', 'GTM': 'Givatayim',
    'HAI': 'Haifa', 'HDR': 'Hadera', 'HDS': 'Hod HaSharon',
    'HOL': 'Holon', 'HRZ': 'Herzliya', 'JER': 'Jerusalem',
    'KAT': 'Kiryat Ata', 'KFS': 'Kfar Saba', 'KGT': 'Kiryat Gat',
    'LOD': 'Lod', 'MDN': 'Modiin', 'NHR': 'Nahariya',
    'NSZ': 'Ness Ziona', 'NTN': 'Netanya', 'NTV': 'Netivot',
    'NZR': 'Nazareth', 'PHK': 'Pardes Hanna-Karkur', 'PTV': 'Petah Tikva',
    'RAN': 'Raanana', 'RHT': 'Rahat', 'RHV': 'Rehovot',
    'RLZ': 'Rishon LeZion', 'RMG': 'Ramat Gan', 'RML': 'Ramla',
    'RSN': 'Rosh HaAyin', 'SDR': 'Sderot', 'TLV': 'Tel Aviv',
    'UMF': 'Umm al-Fahm', 'YVN': 'Yavne',
}


def compute_global_max(src, window_size=2048):
    """Compute the maximum value across the entire raster using windowed reads."""
    nodata = src.nodata
    h, w = src.shape
    global_max = -np.inf

    for row_off in range(0, h, window_size):
        for col_off in range(0, w, window_size):
            win = Window(
                col_off, row_off,
                min(window_size, w - col_off),
                min(window_size, h - row_off)
            )
            data = src.read(1, window=win)
            # Exclude nodata
            if nodata is not None:
                valid = data[data != nodata]
            else:
                valid = data[np.isfinite(data)]
            if valid.size > 0:
                m = valid.max()
                if m > global_max:
                    global_max = m

    return global_max if global_max > -np.inf else np.nan


MIN_SEGMENT_AREA = 250.0  # m^2 -- segments smaller than this are excluded


def compute_segment_si_distribution(city_code, max_exposure):
    """Compute per-segment mean SI for each street segment polygon.

    Returns a dict with segment-level SI distribution stats, or None if
    the segments file is missing.
    """
    seg_file = os.path.join(STREETS_DIR, f"{city_code}_street_segments.shp")
    raster_file = os.path.join(SOLAR_DIR, f"{city_code}_all_kdown_1999_218_SUM.tif")

    if not os.path.exists(seg_file):
        return None
    if max_exposure is None or not np.isfinite(max_exposure):
        return None

    seg_gdf = gpd.read_file(seg_file)

    # Reproject to match raster CRS (EPSG:2039)
    if seg_gdf.crs is not None and seg_gdf.crs.to_epsg() != 2039:
        seg_gdf = seg_gdf.to_crs(epsg=2039)

    # Strip Z if any (some files like NTN are PolygonZ)
    def _strip_z(g):
        if g is None or g.is_empty or not g.has_z:
            return g
        from shapely.geometry import Polygon, MultiPolygon
        if g.geom_type == 'Polygon':
            ext = [(x, y) for x, y, *_ in g.exterior.coords]
            ints = [[(x, y) for x, y, *_ in r.coords] for r in g.interiors]
            return Polygon(ext, ints)
        if g.geom_type == 'MultiPolygon':
            return MultiPolygon([_strip_z(p) for p in g.geoms])
        return g
    seg_gdf['geometry'] = seg_gdf.geometry.apply(_strip_z)
    seg_gdf = seg_gdf[seg_gdf.geometry.notna() & ~seg_gdf.geometry.is_empty].copy()

    # Filter by minimum area
    seg_gdf['_area'] = seg_gdf.geometry.area
    n_total_segs = len(seg_gdf)
    seg_gdf = seg_gdf[seg_gdf['_area'] >= MIN_SEGMENT_AREA].copy()
    n_kept = len(seg_gdf)

    if n_kept == 0:
        return None

    segment_means = []
    with rasterio.open(raster_file) as src:
        for geom in seg_gdf.geometry:
            try:
                masked, _ = rio_mask(src, [mapping(geom)], crop=True,
                                      filled=False, nodata=src.nodata)
            except Exception:
                continue
            data = masked[0]
            if hasattr(data, 'mask'):
                valid = data.compressed()
            else:
                valid = data.ravel()
            if src.nodata is not None:
                valid = valid[valid != src.nodata]
            if valid.size == 0:
                continue
            seg_si = 1.0 - (valid / max_exposure)
            segment_means.append(float(seg_si.mean()))

    if not segment_means:
        return None

    arr = np.array(segment_means)
    p10, p25, p50, p75, p90 = np.percentile(arr, [10, 25, 50, 75, 90])

    return {
        'seg_n_total': n_total_segs,
        'seg_n_kept': n_kept,
        'seg_mean_SI': float(arr.mean()),
        'seg_std_SI': float(arr.std()),
        'seg_min_SI': float(arr.min()),
        'seg_P10_SI': float(p10),
        'seg_P25_SI': float(p25),
        'seg_median_SI': float(p50),
        'seg_P75_SI': float(p75),
        'seg_P90_SI': float(p90),
        'seg_max_SI': float(arr.max()),
        'seg_IQR_SI': float(p75 - p25),
    }


def compute_city_shade_index(city_code):
    """Compute Shade Index statistics for one city."""
    raster_file = os.path.join(SOLAR_DIR, f"{city_code}_all_kdown_1999_218_SUM.tif")
    polygon_file = os.path.join(STREETS_DIR, f"{city_code}_street_network_polygon.shp")

    if not os.path.exists(raster_file):
        print(f"  ERROR: Missing raster: {os.path.basename(raster_file)}")
        return None
    if not os.path.exists(polygon_file):
        print(f"  ERROR: Missing polygon: {os.path.basename(polygon_file)}")
        return None

    t0 = time.time()

    # Load street polygon
    poly_gdf = gpd.read_file(polygon_file)

    with rasterio.open(raster_file) as src:
        # Reproject polygon if CRS differs
        raster_epsg = 2039
        if poly_gdf.crs is not None and poly_gdf.crs.to_epsg() != raster_epsg:
            poly_gdf = poly_gdf.to_crs(epsg=raster_epsg)

        # Step 1: global max (windowed)
        max_exposure = compute_global_max(src)

        # Step 2: mask raster by polygon (crop=True keeps only the bbox)
        geometries = [mapping(g) for g in poly_gdf.geometry]
        masked, _ = rio_mask(src, geometries, crop=True, filled=False, nodata=src.nodata)
        # masked is a MaskedArray with shape (1, H, W)
        data = masked[0]

        # Valid pixels inside polygon
        if hasattr(data, 'mask'):
            valid = data.compressed()
        else:
            valid = data.ravel()

        # Also exclude raster nodata
        if src.nodata is not None:
            valid = valid[valid != src.nodata]

        n_pixels = valid.size
        if n_pixels == 0:
            print(f"  ERROR: No valid pixels within street polygon")
            return None

        mean_exposure = float(np.mean(valid))
        median_exposure = float(np.median(valid))
        min_exposure = float(np.min(valid))

        # SI per pixel, then aggregate
        si_per_pixel = 1.0 - (valid / max_exposure)
        mean_si = float(np.mean(si_per_pixel))
        std_si = float(np.std(si_per_pixel))
        # Percentiles for distribution shape
        p10, p25, p50, p75, p90 = np.percentile(si_per_pixel, [10, 25, 50, 75, 90])
        min_si = float(np.min(si_per_pixel))
        max_si = float(np.max(si_per_pixel))

        # Street area in m2 (0.25 m^2 per pixel at 0.5m resolution)
        px_area = abs(src.res[0] * src.res[1])
        street_area_m2 = n_pixels * px_area

    elapsed = time.time() - t0
    print(f"  max_exposure={max_exposure:.1f}, mean_SI={mean_si:.4f}, "
          f"P10={p10:.3f} P50={p50:.3f} P90={p90:.3f}, "
          f"pixels={n_pixels:,}, area={street_area_m2/1e6:.2f} km2 ({elapsed:.1f}s)")

    # Per-segment SI distribution (segments >= 250 m^2)
    seg_stats = compute_segment_si_distribution(city_code, max_exposure)
    if seg_stats:
        print(f"  Segments: {seg_stats['seg_n_kept']:,}/{seg_stats['seg_n_total']:,} "
              f"(>= {MIN_SEGMENT_AREA:.0f} m^2), seg_mean_SI={seg_stats['seg_mean_SI']:.4f}, "
              f"seg_P50={seg_stats['seg_median_SI']:.4f}")

    result = {
        'city': city_code,
        'city_name': CITY_NAMES.get(city_code, city_code),
        'max_exposure': max_exposure,
        'mean_exposure': mean_exposure,
        'median_exposure': median_exposure,
        'min_exposure': min_exposure,
        'mean_SI': mean_si,
        'std_SI': std_si,
        'min_SI': min_si,
        'P10_SI': float(p10),
        'P25_SI': float(p25),
        'median_SI': float(p50),
        'P75_SI': float(p75),
        'P90_SI': float(p90),
        'max_SI': max_si,
        'IQR_SI': float(p75 - p25),
        'n_pixels': n_pixels,
        'street_area_m2': street_area_m2,
    }
    if seg_stats:
        result.update(seg_stats)
    return result


def plot_01_si_per_city(df, out_dir):
    """Ranked bar chart of city SI values."""
    fig, ax = plt.subplots(figsize=(10, 8))

    sorted_df = df.sort_values('mean_SI')
    cmap = plt.cm.YlGn
    norm = plt.Normalize(vmin=sorted_df['mean_SI'].min(), vmax=sorted_df['mean_SI'].max())
    colors = [cmap(norm(v)) for v in sorted_df['mean_SI']]

    ax.barh(range(len(sorted_df)), sorted_df['mean_SI'], color=colors,
            edgecolor='black', linewidth=0.5)
    ax.set_yticks(range(len(sorted_df)))
    ax.set_yticklabels([f"{r['city']} ({r['city_name']})" for _, r in sorted_df.iterrows()],
                       fontsize=10)
    ax.set_xlabel('Mean Shade Index (0 = fully sunlit, 1 = fully shaded)', fontsize=12)
    ax.set_title(f'Average Street Shade Index by City (n={len(df)})',
                 fontsize=13)

    # National average line
    nat_avg = np.average(df['mean_SI'], weights=df['n_pixels'])
    ax.axvline(nat_avg, color='red', linestyle='--', linewidth=2,
               label=f'Weighted mean = {nat_avg:.3f}')
    ax.legend(fontsize=11)

    # Value labels
    for i, (_, row) in enumerate(sorted_df.iterrows()):
        ax.text(row['mean_SI'] + 0.002, i, f"{row['mean_SI']:.3f}",
                va='center', fontsize=9)

    ax.set_xlim(0, sorted_df['mean_SI'].max() * 1.15)
    fig.tight_layout()
    path = os.path.join(out_dir, '01_si_per_city.png')
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {path}")


def plot_02_si_vs_crown_diameter(df, out_dir):
    """Correlation scatter: median street tree crown diameter vs mean SI."""
    # Load median crown diameter from street_trees_data.xlsx
    if not os.path.exists(STREET_TREES_EXCEL):
        print(f"  SKIP: {STREET_TREES_EXCEL} not found -- run street_tree_analysis.py first")
        return None

    trees = pd.read_excel(STREET_TREES_EXCEL, sheet_name='City Statistics')
    merged = df.merge(trees[['city', 'diam_median']], on='city', how='inner')
    merged = merged.rename(columns={'diam_median': 'street_median_diam'})

    if len(merged) == 0:
        print("  SKIP: No cities match between shade and street trees data")
        return None

    r_pear, p_pear = pearsonr(merged['street_median_diam'], merged['mean_SI'])
    r_spear, p_spear = spearmanr(merged['street_median_diam'], merged['mean_SI'])

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.scatter(merged['street_median_diam'], merged['mean_SI'], s=80,
               c='forestgreen', edgecolors='black', linewidth=0.5, alpha=0.8, zorder=5)

    # Regression line
    z = np.polyfit(merged['street_median_diam'], merged['mean_SI'], 1)
    xline = np.linspace(merged['street_median_diam'].min() - 0.2,
                         merged['street_median_diam'].max() + 0.2, 100)
    ax.plot(xline, np.polyval(z, xline), 'b-', linewidth=1.5, alpha=0.7,
            label=f'Fit: y={z[0]:.4f}x{z[1]:+.3f}', zorder=4)

    # City labels
    for _, row in merged.iterrows():
        ax.annotate(row['city'], (row['street_median_diam'], row['mean_SI']),
                    textcoords='offset points', xytext=(5, 5), fontsize=9)

    ax.set_xlabel('Median Street Tree Crown Diameter (m)', fontsize=13)
    ax.set_ylabel('Mean Street Shade Index', fontsize=13)
    ax.set_title(f'Street Shade Index vs Street Tree Crown Diameter (n={len(merged)})\n'
                 f'Pearson r={r_pear:.3f} (p={p_pear:.4f}), '
                 f'Spearman rho={r_spear:.3f} (p={p_spear:.4f})',
                 fontsize=12)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = os.path.join(out_dir, '02_si_vs_crown_diameter.png')
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {path}")

    return merged, r_pear, r_spear


def plot_05_si_distribution_per_city(df, out_dir):
    """Box plot showing SI percentile distribution per city, sorted by median."""
    sorted_df = df.sort_values('median_SI').reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(12, 9))

    nat_avg = np.average(df['mean_SI'], weights=df['n_pixels'])

    for i, row in sorted_df.iterrows():
        color = ('forestgreen' if row['median_SI'] >= nat_avg
                 else 'coral')
        # Box: P25-P75
        ax.barh(i, row['P75_SI'] - row['P25_SI'], left=row['P25_SI'],
                height=0.6, color=color, alpha=0.7,
                edgecolor='black', linewidth=0.5)
        # Median line
        ax.plot([row['median_SI'], row['median_SI']], [i - 0.3, i + 0.3],
                color='black', linewidth=2)
        # Whiskers: P10-P90
        ax.plot([row['P10_SI'], row['P25_SI']], [i, i], color='black', linewidth=1)
        ax.plot([row['P75_SI'], row['P90_SI']], [i, i], color='black', linewidth=1)
        ax.plot([row['P10_SI'], row['P10_SI']], [i - 0.15, i + 0.15],
                color='black', linewidth=1)
        ax.plot([row['P90_SI'], row['P90_SI']], [i - 0.15, i + 0.15],
                color='black', linewidth=1)

    ax.set_yticks(range(len(sorted_df)))
    ax.set_yticklabels([f"{r['city']} ({r['city_name']})"
                        for _, r in sorted_df.iterrows()], fontsize=10)
    ax.axvline(nat_avg, color='blue', linestyle='--', linewidth=2,
               label=f'Weighted national mean = {nat_avg:.3f}')
    ax.set_xlabel('Shade Index', fontsize=12)
    ax.set_title('Per-City Shade Index Distribution\n'
                 '(box = P25-P75, whiskers = P10-P90, vertical line = median)',
                 fontsize=13)
    ax.legend(fontsize=11, loc='lower right')
    ax.set_xlim(left=0)
    ax.grid(True, axis='x', alpha=0.3)
    fig.tight_layout()
    path = os.path.join(out_dir, '05_si_distribution_per_city.png')
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {path}")


def plot_03_si_vs_tree_density(df, out_dir):
    """Correlation scatter: street tree density (trees/km^2) vs mean SI."""
    if not os.path.exists(STREET_TREES_EXCEL):
        print(f"  SKIP: {STREET_TREES_EXCEL} not found -- run street_tree_analysis.py first")
        return None

    trees = pd.read_excel(STREET_TREES_EXCEL, sheet_name='City Statistics')
    merged = df.merge(trees[['city', 'n_trees']], on='city', how='inner')
    merged = merged.rename(columns={'n_trees': 'n_street_trees'})
    merged['tree_density'] = merged['n_street_trees'] / (merged['street_area_m2'] / 1e6)

    if len(merged) == 0:
        return None

    r_pear, p_pear = pearsonr(merged['tree_density'], merged['mean_SI'])
    r_spear, p_spear = spearmanr(merged['tree_density'], merged['mean_SI'])

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.scatter(merged['tree_density'], merged['mean_SI'], s=80,
               c='forestgreen', edgecolors='black', linewidth=0.5, alpha=0.8, zorder=5)

    z = np.polyfit(merged['tree_density'], merged['mean_SI'], 1)
    xline = np.linspace(merged['tree_density'].min() * 0.95,
                         merged['tree_density'].max() * 1.05, 100)
    ax.plot(xline, np.polyval(z, xline), 'b-', linewidth=1.5, alpha=0.7,
            label=f'Fit: y={z[0]:.2e}x{z[1]:+.3f}', zorder=4)

    for _, row in merged.iterrows():
        ax.annotate(row['city'], (row['tree_density'], row['mean_SI']),
                    textcoords='offset points', xytext=(5, 5), fontsize=9)

    ax.set_xlabel('Street Tree Density (trees per km² of street area)', fontsize=13)
    ax.set_ylabel('Mean Street Shade Index', fontsize=13)
    ax.set_title(f'Shade Index vs Street Tree Density (n={len(merged)})\n'
                 f'Pearson r={r_pear:.3f} (p={p_pear:.4f}), '
                 f'Spearman rho={r_spear:.3f} (p={p_spear:.4f})',
                 fontsize=12)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = os.path.join(out_dir, '03_si_vs_tree_density.png')
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {path}")

    return merged, r_pear, r_spear


def export_excel(df, filename):
    """Export shade index data to Excel."""
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        cols = ['city', 'city_name',
                'mean_SI', 'std_SI', 'min_SI',
                'P10_SI', 'P25_SI', 'median_SI', 'P75_SI', 'P90_SI',
                'max_SI', 'IQR_SI',
                'max_exposure', 'mean_exposure', 'median_exposure', 'min_exposure',
                'n_pixels', 'street_area_m2']
        df_sorted = df.sort_values('mean_SI', ascending=False)
        df_sorted[cols].to_excel(writer, sheet_name='Shade Index', index=False)

        # Dedicated percentile sheet for easy plotting in Excel
        pct_cols = ['city', 'city_name', 'P10_SI', 'P25_SI', 'median_SI',
                    'P75_SI', 'P90_SI']
        df_sorted[pct_cols].to_excel(writer, sheet_name='SI Percentiles', index=False)

        # Per-segment SI distribution (segments >= 250 m^2)
        seg_cols = ['city', 'city_name', 'seg_n_kept', 'seg_n_total',
                    'seg_mean_SI', 'seg_std_SI', 'seg_min_SI',
                    'seg_P10_SI', 'seg_P25_SI', 'seg_median_SI',
                    'seg_P75_SI', 'seg_P90_SI', 'seg_max_SI', 'seg_IQR_SI']
        seg_available = [c for c in seg_cols if c in df_sorted.columns]
        seg_df = df_sorted[seg_available].dropna(subset=['seg_mean_SI']) \
            if 'seg_mean_SI' in df_sorted.columns else pd.DataFrame()
        if not seg_df.empty:
            seg_df.to_excel(writer, sheet_name='SI Per Street Segment', index=False)

        # Summary sheet
        summary = pd.DataFrame({
            'Metric': ['Cities analyzed',
                       'Weighted mean SI (by pixel count)',
                       'Max city SI', 'Min city SI',
                       'Total street pixels',
                       'Total street area (km2)'],
            'Value': [len(df),
                      round(np.average(df['mean_SI'], weights=df['n_pixels']), 4),
                      f"{df_sorted.iloc[0]['city']} ({df_sorted.iloc[0]['mean_SI']:.3f})",
                      f"{df_sorted.iloc[-1]['city']} ({df_sorted.iloc[-1]['mean_SI']:.3f})",
                      int(df['n_pixels'].sum()),
                      round(df['street_area_m2'].sum() / 1e6, 2)]
        })
        summary.to_excel(writer, sheet_name='Summary', index=False)

    print(f"  Saved {filename}")


def generate_report(df, corr_data, r_pear, r_spear,
                    corr_density=None, r_pear_d=None, r_spear_d=None):
    """Generate markdown report."""
    sorted_df = df.sort_values('mean_SI', ascending=False)
    nat_avg = np.average(df['mean_SI'], weights=df['n_pixels'])

    report = f"""# Street Shade Index Analysis: {len(df)} Israeli Cities

## Summary

- **Cities analyzed**: {len(df)}
- **Weighted mean Shade Index**: {nat_avg:.4f}
- **Most shaded streets**: {sorted_df.iloc[0]['city']} ({sorted_df.iloc[0]['city_name']}) at SI = {sorted_df.iloc[0]['mean_SI']:.3f}
- **Least shaded streets**: {sorted_df.iloc[-1]['city']} ({sorted_df.iloc[-1]['city_name']}) at SI = {sorted_df.iloc[-1]['mean_SI']:.3f}
- **Total street area analyzed**: {df['street_area_m2'].sum()/1e6:.2f} km2 across {df['n_pixels'].sum():,} pixels

## Methodology

### Shade Index Definition

For each raster pixel, the Shade Index is computed as:

```
SI = 1 - (pixel_kdown / city_max_kdown)
```

where `pixel_kdown` is the pixel's cumulative solar exposure (08:00-17:00 on 6 August), and `city_max_kdown` is the maximum pixel value across the entire city's raster (representing a fully unshaded reference location).

A city's **average SI** is the mean of per-pixel SI values across all raster cells that fall within the dissolved street network polygon.

- `SI = 0` means no shading (direct sunlight throughout the day)
- `SI = 1` means full shading (no direct solar exposure)
- Typical urban values: 0.1-0.5

### Data Sources

- **Solar exposure rasters**: 0.5 m/pixel cumulative kdown (6 Aug, 08:00-17:00), EPSG:2039
- **Street polygons**: dissolved street network polygons from `batch_process_streets.py`

## Per-City Shade Index

![SI per City](plots_shade_index/01_si_per_city.png)

### Distribution Shape

The mean alone hides the shape of each city's SI distribution. The box plot below shows the inter-quartile range (P25-P75) and 10th-90th percentile whiskers per city, so you can see how varied or uniform the shading is across each city's street network.

![SI Distribution per City](plots_shade_index/05_si_distribution_per_city.png)

### Per-City Statistics Table

| Rank | City | Name | Mean SI | P10 | P25 | Median | P75 | P90 | IQR | Street Area (km²) |
|------|------|------|--------:|----:|----:|-------:|----:|----:|----:|------------------:|
"""
    for rank, (_, row) in enumerate(sorted_df.iterrows(), 1):
        report += (f"| {rank} | {row['city']} | {row['city_name']} | "
                   f"{row['mean_SI']:.4f} | "
                   f"{row['P10_SI']:.3f} | {row['P25_SI']:.3f} | "
                   f"{row['median_SI']:.3f} | "
                   f"{row['P75_SI']:.3f} | {row['P90_SI']:.3f} | "
                   f"{row['IQR_SI']:.3f} | "
                   f"{row['street_area_m2']/1e6:.2f} |\n")

    report += f"""
## Correlation with Street Tree Crown Diameter

![SI vs Crown Diameter](plots_shade_index/02_si_vs_crown_diameter.png)

"""
    if corr_data is not None:
        direction = "positive" if r_pear > 0 else "negative"
        strength = ("strong" if abs(r_pear) >= 0.7 else
                    "moderate" if abs(r_pear) >= 0.4 else
                    "weak" if abs(r_pear) >= 0.2 else "very weak")
        report += f"""**Correlation**: Pearson r = {r_pear:.3f}, Spearman rho = {r_spear:.3f}

Interpretation: There is a **{strength} {direction} correlation** between median street tree crown diameter and street-average Shade Index. {"Cities with larger street trees tend to have more shaded streets, consistent with the hypothesis that tree canopy is a primary driver of street shading." if r_pear > 0.3 else "The relationship between tree size and street shading is weaker than expected; other factors (building geometry, street orientation, canyon width) likely dominate SI in many cities."}

### Detailed Data

| City | Name | Median Crown Diam (m) | Mean SI |
|------|------|----------------------:|--------:|
"""
        for _, row in corr_data.sort_values('mean_SI', ascending=False).iterrows():
            report += (f"| {row['city']} | {row['city_name']} | "
                       f"{row['street_median_diam']:.1f} | {row['mean_SI']:.4f} |\n")

    if corr_density is not None:
        direction_d = "positive" if r_pear_d > 0 else "negative"
        strength_d = ("strong" if abs(r_pear_d) >= 0.7 else
                      "moderate" if abs(r_pear_d) >= 0.4 else
                      "weak" if abs(r_pear_d) >= 0.2 else "very weak")
        report += f"""
## Correlation with Street Tree Density

![SI vs Tree Density](plots_shade_index/03_si_vs_tree_density.png)

Street tree density is computed as number of street trees divided by street network area (trees per km²). This normalizes for city size, giving a fair per-unit-area comparison.

**Correlation**: Pearson r = {r_pear_d:.3f}, Spearman rho = {r_spear_d:.3f}

Interpretation: There is a **{strength_d} {direction_d} correlation** between street tree density and street-average Shade Index.

### Detailed Data

| City | Name | Street Trees | Street Area (km²) | Density (trees/km²) | Mean SI |
|------|------|-------------:|------------------:|--------------------:|--------:|
"""
        for _, row in corr_density.sort_values('mean_SI', ascending=False).iterrows():
            report += (f"| {row['city']} | {row['city_name']} | "
                       f"{int(row['n_street_trees']):,} | "
                       f"{row['street_area_m2']/1e6:.2f} | "
                       f"{row['tree_density']:,.0f} | "
                       f"{row['mean_SI']:.4f} |\n")

    report += """
## Limitations

1. **Raster max as reference**: The global max per city may not be a perfectly unshaded point (e.g., if the entire city is partially shaded, the max is biased downward). Using absolute solar constants would change values but not the relative ranking.
2. **Building shade vs tree shade**: SI conflates shade from buildings, trees, and topography. Cities with tall buildings (TLV) may score high for reasons unrelated to tree cover.
3. **Single date**: Analysis is for 6 August only (~peak summer). Winter or morning/afternoon patterns may differ.
4. **Street polygon accuracy**: Depends on the quality of the dissolved street network polygon (see `batch_process_streets.py`).

## Files

- `shade_index_data.xlsx` -- per-city SI data (for custom plotting); now includes
  P10/P25/P50/P75/P90 percentiles and IQR plus a dedicated `SI Percentiles` sheet
- `plots_shade_index/01_si_per_city.png` -- ranked bar chart
- `plots_shade_index/02_si_vs_crown_diameter.png` -- SI vs crown diameter
- `plots_shade_index/03_si_vs_tree_density.png` -- SI vs tree density
- `plots_shade_index/05_si_distribution_per_city.png` -- per-city SI distribution
  (box = P25-P75, whiskers = P10-P90)
"""
    return report


def main():
    os.makedirs(PLOT_DIR, exist_ok=True)

    # Find cities with both raster and street polygon
    rasters = glob.glob(os.path.join(SOLAR_DIR, '*_all_kdown_1999_218_SUM.tif'))
    raster_cities = {os.path.basename(f).split('_all_kdown_')[0] for f in rasters}
    polys = glob.glob(os.path.join(STREETS_DIR, '*_street_network_polygon.shp'))
    poly_cities = {os.path.basename(f).replace('_street_network_polygon.shp', '') for f in polys}

    cities = sorted(raster_cities & poly_cities)

    print(f"{'='*60}")
    print(f"Street Shade Index Analysis")
    print(f"Cities with both raster and street polygon: {len(cities)}")
    print(f"{'='*60}")

    results = []
    for i, city in enumerate(cities):
        print(f"\n[{i+1}/{len(cities)}] {city}")
        r = compute_city_shade_index(city)
        if r:
            results.append(r)

    if not results:
        print("No results. Exiting.")
        return

    df = pd.DataFrame(results)

    # Plots
    print("\nGenerating plots...")
    plot_01_si_per_city(df, PLOT_DIR)
    corr = plot_02_si_vs_crown_diameter(df, PLOT_DIR)
    corr_density = plot_03_si_vs_tree_density(df, PLOT_DIR)
    plot_05_si_distribution_per_city(df, PLOT_DIR)

    # Excel export
    print("\nExporting Excel...")
    export_excel(df, EXCEL_FILE)

    # Report
    print("\nGenerating report...")
    if corr is not None:
        corr_data, r_pear, r_spear = corr
    else:
        corr_data, r_pear, r_spear = None, None, None
    if corr_density is not None:
        corr_dens_data, r_pear_d, r_spear_d = corr_density
    else:
        corr_dens_data, r_pear_d, r_spear_d = None, None, None
    report = generate_report(df, corr_data, r_pear, r_spear,
                              corr_dens_data, r_pear_d, r_spear_d)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  Saved {REPORT_FILE}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Done. Processed {len(results)} cities.")
    print(f"\nTop 5 most shaded streets:")
    for _, row in df.sort_values('mean_SI', ascending=False).head(5).iterrows():
        print(f"  {row['city']} ({row['city_name']}): SI = {row['mean_SI']:.3f}")
    if corr_data is not None:
        print(f"\nCorrelation with street tree crown diameter:")
        print(f"  Pearson r = {r_pear:.3f}, Spearman rho = {r_spear:.3f}")
    if corr_dens_data is not None:
        print(f"\nCorrelation with street tree density:")
        print(f"  Pearson r = {r_pear_d:.3f}, Spearman rho = {r_spear_d:.3f}")


if __name__ == '__main__':
    main()
