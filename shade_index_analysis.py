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

        # SI per pixel, then mean
        si_per_pixel = 1.0 - (valid / max_exposure)
        mean_si = float(np.mean(si_per_pixel))
        median_si = float(np.median(si_per_pixel))
        min_si = float(np.min(si_per_pixel))
        max_si = float(np.max(si_per_pixel))

        # Street area in m2 (0.25 m^2 per pixel at 0.5m resolution)
        px_area = abs(src.res[0] * src.res[1])
        street_area_m2 = n_pixels * px_area

    elapsed = time.time() - t0
    print(f"  max_exposure={max_exposure:.1f}, mean_SI={mean_si:.4f}, "
          f"pixels={n_pixels:,}, area={street_area_m2/1e6:.2f} km2 ({elapsed:.1f}s)")

    return {
        'city': city_code,
        'city_name': CITY_NAMES.get(city_code, city_code),
        'max_exposure': max_exposure,
        'mean_exposure': mean_exposure,
        'median_exposure': median_exposure,
        'min_exposure': min_exposure,
        'mean_SI': mean_si,
        'median_SI': median_si,
        'min_SI': min_si,
        'max_SI': max_si,
        'n_pixels': n_pixels,
        'street_area_m2': street_area_m2,
    }


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


def export_excel(df, filename):
    """Export shade index data to Excel."""
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        cols = ['city', 'city_name', 'mean_SI', 'median_SI', 'min_SI', 'max_SI',
                'max_exposure', 'mean_exposure', 'median_exposure', 'min_exposure',
                'n_pixels', 'street_area_m2']
        df_sorted = df.sort_values('mean_SI', ascending=False)
        df_sorted[cols].to_excel(writer, sheet_name='Shade Index', index=False)

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


def generate_report(df, corr_data, r_pear, r_spear):
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

| Rank | City | Name | Mean SI | Median SI | Street Area (km2) | Pixels |
|------|------|------|--------:|----------:|------------------:|-------:|
"""
    for rank, (_, row) in enumerate(sorted_df.iterrows(), 1):
        report += (f"| {rank} | {row['city']} | {row['city_name']} | "
                   f"{row['mean_SI']:.4f} | {row['median_SI']:.4f} | "
                   f"{row['street_area_m2']/1e6:.2f} | {row['n_pixels']:,} |\n")

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

    report += """
## Limitations

1. **Raster max as reference**: The global max per city may not be a perfectly unshaded point (e.g., if the entire city is partially shaded, the max is biased downward). Using absolute solar constants would change values but not the relative ranking.
2. **Building shade vs tree shade**: SI conflates shade from buildings, trees, and topography. Cities with tall buildings (TLV) may score high for reasons unrelated to tree cover.
3. **Single date**: Analysis is for 6 August only (~peak summer). Winter or morning/afternoon patterns may differ.
4. **Street polygon accuracy**: Depends on the quality of the dissolved street network polygon (see `batch_process_streets.py`).

## Files

- `shade_index_data.xlsx` -- per-city SI data (for custom plotting)
- `plots_shade_index/01_si_per_city.png` -- ranked bar chart
- `plots_shade_index/02_si_vs_crown_diameter.png` -- correlation scatter
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

    # Excel export
    print("\nExporting Excel...")
    export_excel(df, EXCEL_FILE)

    # Report
    print("\nGenerating report...")
    if corr is not None:
        corr_data, r_pear, r_spear = corr
    else:
        corr_data, r_pear, r_spear = None, None, None
    report = generate_report(df, corr_data, r_pear, r_spear)
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


if __name__ == '__main__':
    main()
