"""
Street Tree Quality Analysis: 17 Israeli Cities

Identical analysis to urban_forest_analysis.py but on street-tree-only
trunk files (*_streets.shp). Adds a correlation plot comparing all-tree
vs street-tree median crown diameter across cities.

Usage:
    python street_tree_analysis.py

Reads XXX_tree_trunks_YYYY_streets.shp (output of extract_street_trees.py).
Produces: plots_street_trees/ (11 plots) + street_trees_report.md
"""

import os
import sys
import glob

# Reuse the core analysis from urban_forest_analysis.py
from urban_forest_analysis import (
    compute_city_stats, save_plot, DIAM_BINS, SIZE_CLASSES, CITY_NAMES,
    plot_01_national_histogram,
    plot_02_city_grid,
    plot_03_city_boxplots,
    plot_04_ranking_median,
    plot_05_ranking_large_trees,
    plot_06_size_classes_stacked,
    plot_07_count_vs_quality,
    plot_08_quality_heatmap,
    plot_09_cdf_comparison,
    plot_10_single_vs_all,
)

import time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import pearsonr, spearmanr
import warnings

warnings.filterwarnings('ignore')

DATA_DIR = r"d:\OneDrive - Technion\Research\Shade Maps\Israel trees"
PLOT_DIR = 'plots_street_trees'
REPORT_FILE = 'street_trees_report.md'


def compute_all_street_cities(data_dir):
    """Compute statistics for all cities with street tree data."""
    trunk_files = sorted(glob.glob(os.path.join(data_dir, '*_tree_trunks_*_streets.shp')))

    if not trunk_files:
        print(f"No *_streets.shp files found in {data_dir}")
        sys.exit(1)

    print(f"Found {len(trunk_files)} street tree files")

    all_stats = []
    national_hist = np.zeros(len(DIAM_BINS) - 1, dtype=np.int64)

    for f in trunk_files:
        city_code = os.path.basename(f).split('_tree_trunks_')[0]
        print(f"  {city_code}...", end=" ", flush=True)
        t0 = time.time()
        stats = compute_city_stats(f)
        national_hist += stats['hist_counts']
        all_stats.append(stats)
        print(f"{stats['n_trees']:,} street trees ({time.time()-t0:.1f}s)")

    hist_array = np.array([s['hist_counts'] for s in all_stats])
    for s in all_stats:
        del s['hist_counts']
    df = pd.DataFrame(all_stats)

    total_trees = df['n_trees'].sum()
    national_mean = np.average(df['diam_mean'], weights=df['n_trees'])

    # National median from cumulative histogram
    cum = np.cumsum(national_hist)
    half = total_trees / 2
    national_median = national_mean  # fallback
    for i, c in enumerate(cum):
        if c >= half:
            prev_cum = cum[i - 1] if i > 0 else 0
            frac = (half - prev_cum) / (c - prev_cum) if (c - prev_cum) > 0 else 0
            national_median = DIAM_BINS[i] + frac * (DIAM_BINS[i + 1] - DIAM_BINS[i])
            break

    national_stats = {
        'total_trees': total_trees,
        'total_polygons': df['n_polygons'].sum(),
        'n_cities': len(df),
        'national_mean': national_mean,
        'national_median': national_median,
        'national_hist': national_hist,
        'national_large_pct': np.average(df['large_tree_pct'], weights=df['n_trees']),
        'national_small_pct': np.average(df['small_tree_pct'], weights=df['n_trees']),
    }

    # Composite quality score
    df['rank_median'] = df['diam_median'].rank(pct=True)
    df['rank_large'] = df['large_tree_pct'].rank(pct=True)
    df['rank_cv'] = df['diam_cv'].rank(pct=True)
    df['rank_count'] = df['n_trees'].rank(pct=True)
    df['quality_score'] = (0.4 * df['rank_median'] + 0.3 * df['rank_large'] +
                           0.15 * df['rank_cv'] + 0.15 * df['rank_count'])
    df['quality_rank'] = df['quality_score'].rank(ascending=False).astype(int)

    return df, national_stats, hist_array


def plot_11_all_vs_street_correlation(street_df, data_dir, out_dir):
    """Correlation: all-tree vs street-tree median crown diameter."""
    # Load all-tree stats for the same cities
    all_tree_stats = []
    for _, row in street_df.iterrows():
        city = row['city']
        trunk_pattern = os.path.join(data_dir, f"{city}_tree_trunks_*.shp")
        trunk_files = [f for f in glob.glob(trunk_pattern) if '_streets' not in f]
        if trunk_files:
            stats = compute_city_stats(trunk_files[0])
            del stats['hist_counts']
            all_tree_stats.append(stats)

    all_df = pd.DataFrame(all_tree_stats)

    # Merge on city code
    merged = street_df[['city', 'city_name', 'diam_median', 'diam_mean']].rename(
        columns={'diam_median': 'street_median', 'diam_mean': 'street_mean'})
    all_cols = all_df[['city', 'diam_median', 'diam_mean']].rename(
        columns={'diam_median': 'all_median', 'diam_mean': 'all_mean'})
    merged = merged.merge(all_cols, on='city')

    # Correlation stats
    r_pear, p_pear = pearsonr(merged['all_median'], merged['street_median'])
    r_spear, p_spear = spearmanr(merged['all_median'], merged['street_median'])

    fig, ax = plt.subplots(figsize=(9, 9))

    ax.scatter(merged['all_median'], merged['street_median'], s=80,
               c='forestgreen', edgecolors='black', linewidth=0.5, alpha=0.8, zorder=5)

    # 1:1 line
    lims = [min(merged['all_median'].min(), merged['street_median'].min()) - 0.5,
            max(merged['all_median'].max(), merged['street_median'].max()) + 0.5]
    ax.plot(lims, lims, 'r--', linewidth=2, label='1:1 line', zorder=3)

    # Regression line
    z = np.polyfit(merged['all_median'], merged['street_median'], 1)
    xline = np.linspace(lims[0], lims[1], 100)
    ax.plot(xline, np.polyval(z, xline), 'b-', linewidth=1.5, alpha=0.7,
            label=f'Fit: y={z[0]:.2f}x{z[1]:+.2f}', zorder=4)

    # Labels
    for _, row in merged.iterrows():
        ax.annotate(row['city'], (row['all_median'], row['street_median']),
                    textcoords='offset points', xytext=(5, 5), fontsize=9)

    ax.set_xlabel('Median Crown Diameter -- All Trees (m)', fontsize=13)
    ax.set_ylabel('Median Crown Diameter -- Street Trees (m)', fontsize=13)
    ax.set_title(f'All Trees vs Street Trees: Crown Diameter Correlation\n'
                 f'Pearson r={r_pear:.3f} (p={p_pear:.4f}), '
                 f'Spearman rho={r_spear:.3f} (p={p_spear:.4f})',
                 fontsize=12)
    ax.legend(fontsize=11)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    save_plot(fig, '11_all_vs_street_correlation.png')

    return merged, r_pear, r_spear


def generate_street_report(df, national_stats, corr_data, r_pear, r_spear):
    """Generate the street trees markdown report."""
    sorted_by_quality = df.sort_values('quality_score', ascending=False)
    sorted_by_median = df.sort_values('diam_median', ascending=False)

    report = f"""# Street Tree Quality Analysis: {national_stats['n_cities']} Israeli Cities

## Summary

- **Total street trees analyzed**: {national_stats['total_trees']:,}
- **National mean crown diameter (street trees)**: {national_stats['national_mean']:.1f} m
- **National median crown diameter (street trees)**: {national_stats['national_median']:.1f} m
- **Large street trees (>= 10m crown)**: {national_stats['national_large_pct']:.1f}%
- **Small street trees (< 4m crown)**: {national_stats['national_small_pct']:.1f}%

### Definition

A tree is classified as a "street tree" if its estimated trunk location falls inside the city's street network polygon or within **2 meters** of a street edge. This captures both trees planted in street medians/sidewalks and front-yard trees that contribute to the streetscape canopy.

### Key Findings

1. **Top 3 cities by street tree quality**: {', '.join(f"{r['city']} ({r['city_name']})" for _, r in sorted_by_quality.head(3).iterrows())}
2. **Bottom 3 cities**: {', '.join(f"{r['city']} ({r['city_name']})" for _, r in sorted_by_quality.tail(3).iterrows())}
3. **Largest median crown**: {sorted_by_median.iloc[0]['city']} ({sorted_by_median.iloc[0]['city_name']}) at {sorted_by_median.iloc[0]['diam_median']:.1f} m
4. **Smallest median crown**: {sorted_by_median.iloc[-1]['city']} ({sorted_by_median.iloc[-1]['city_name']}) at {sorted_by_median.iloc[-1]['diam_median']:.1f} m
5. **All-trees vs street-trees correlation**: Pearson r={r_pear:.3f}, Spearman rho={r_spear:.3f}

## Methodology

Street tree trunks were identified by spatial intersection of estimated trunk point locations with the dissolved street network polygon (buffered by 2m). The street network polygons were derived from parcel-level street segment data, dissolved into unified polygons with thin sliver gaps closed and small holes filled.

Crown diameter for each tree is derived from the predicted trunk count per canopy polygon: `crown_area = polygon_area / N_trees`, `crown_diameter = 2 * sqrt(crown_area / pi)`.

## National Street Tree Crown Distribution

![National Distribution](plots_street_trees/01_national_crown_diameter_hist.png)

## City Rankings

### By Median Crown Diameter

![Median Ranking](plots_street_trees/04_city_ranking_median_diam.png)

"""
    report += "| Rank | City | Name | Median (m) | Mean (m) | IQR (m) | Street Trees |\n"
    report += "|------|------|------|-----------|---------|---------|-------------|\n"
    for rank, (_, row) in enumerate(sorted_by_median.iterrows(), 1):
        report += (f"| {rank} | {row['city']} | {row['city_name']} | "
                   f"{row['diam_median']:.1f} | {row['diam_mean']:.1f} | "
                   f"{row['diam_iqr']:.1f} | {row['n_trees']:,} |\n")

    report += f"""
### By Large Tree Fraction (crown >= 10m)

![Large Tree Ranking](plots_street_trees/05_city_ranking_large_trees.png)

### Composite Quality Score

![Quality Heatmap](plots_street_trees/08_quality_index_heatmap.png)

"""
    report += "| Rank | City | Name | Quality Score | Median Diam | Large Tree % | Street Trees |\n"
    report += "|------|------|------|--------------|------------|-------------|-------------|\n"
    for _, row in sorted_by_quality.iterrows():
        report += (f"| {row['quality_rank']} | {row['city']} | {row['city_name']} | "
                   f"{row['quality_score']:.3f} | {row['diam_median']:.1f} m | "
                   f"{row['large_tree_pct']:.1f}% | {row['n_trees']:,} |\n")

    report += f"""
## Detailed Comparisons

### Crown Diameter Distributions

![City Grid](plots_street_trees/02_city_distributions_grid.png)

### Box Plot Comparison

![Box Plots](plots_street_trees/03_city_boxplots.png)

### Crown Size Class Distribution

![Size Classes](plots_street_trees/06_crown_size_classes_stacked.png)

## All Trees vs Street Trees Correlation

![Correlation](plots_street_trees/11_all_vs_street_correlation.png)

"""
    if corr_data is not None:
        report += "| City | All Trees Median (m) | Street Trees Median (m) | Difference (m) |\n"
        report += "|------|---------------------|------------------------|----------------|\n"
        for _, row in corr_data.sort_values('all_median', ascending=False).iterrows():
            diff = row['street_median'] - row['all_median']
            report += (f"| {row['city']} ({row['city_name']}) | {row['all_median']:.1f} | "
                       f"{row['street_median']:.1f} | {diff:+.1f} |\n")

        above = (corr_data['street_median'] > corr_data['all_median']).sum()
        below = (corr_data['street_median'] < corr_data['all_median']).sum()
        equal = (corr_data['street_median'] == corr_data['all_median']).sum()
        report += f"""
**Pattern**: In {above} of {len(corr_data)} cities, street trees have a larger median crown diameter than the city-wide average, while in {below} cities they are smaller. This {"suggests street trees tend to be larger/more mature than the overall urban forest" if above > below else "suggests street trees tend to be smaller than the overall urban forest" if below > above else "shows no clear pattern"}.

## Additional Plots

### Tree Count vs Quality

![Count vs Quality](plots_street_trees/07_tree_count_vs_quality.png)

### CDF: Top vs Bottom Cities

![CDF](plots_street_trees/09_national_vs_city_cdf.png)

### Single-Tree vs All-Trees Estimates

![Single vs All](plots_street_trees/10_single_vs_all_trees.png)

"""

    report += f"""
## Appendix: Full Per-City Statistics

"""
    report += ("| City | Name | Street Trees | Median Diam | Mean Diam | Std | Q25 | Q75 | "
               "Large % | Small % | CV | Quality Score |\n")
    report += ("|----|------|-------------|------------|----------|-----|-----|-----|----|-----|--|--|\n")
    for _, row in sorted_by_quality.iterrows():
        report += (f"| {row['city']} | {row['city_name']} | {row['n_trees']:,} | "
                   f"{row['diam_median']:.1f} | {row['diam_mean']:.1f} | {row['diam_std']:.1f} | "
                   f"{row['diam_q25']:.1f} | {row['diam_q75']:.1f} | "
                   f"{row['large_tree_pct']:.1f} | {row['small_tree_pct']:.1f} | "
                   f"{row['diam_cv']:.2f} | {row['quality_score']:.3f} |\n")

    report += """
## Diagnostic Plots

All plots saved to `plots_street_trees/`:

1. `01_national_crown_diameter_hist.png` -- National street tree crown diameter histogram
2. `02_city_distributions_grid.png` -- Per-city distributions (small multiples)
3. `03_city_boxplots.png` -- Box plots (Q10-Q90)
4. `04_city_ranking_median_diam.png` -- City ranking by median crown diameter
5. `05_city_ranking_large_trees.png` -- City ranking by large tree fraction
6. `06_crown_size_classes_stacked.png` -- Size class proportions
7. `07_tree_count_vs_quality.png` -- Tree count vs crown quality
8. `08_quality_index_heatmap.png` -- Multi-metric quality heatmap
9. `09_national_vs_city_cdf.png` -- CDF: top 5 vs bottom 5
10. `10_single_vs_all_trees.png` -- Single-tree vs all-trees crown diameter
11. `11_all_vs_street_correlation.png` -- All trees vs street trees correlation
"""
    return report


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else DATA_DIR
    os.makedirs(PLOT_DIR, exist_ok=True)

    # Temporarily override the plot dir for reused functions
    import urban_forest_analysis
    urban_forest_analysis.PLOT_DIR = PLOT_DIR

    print("=" * 60)
    print("Street Tree Quality Analysis")
    print("=" * 60)

    # Phase 1: Compute statistics
    print("\nPhase 1: Computing per-city street tree statistics...")
    t0 = time.time()
    df, national_stats, hist_array = compute_all_street_cities(data_dir)
    print(f"\nStatistics computed in {time.time()-t0:.1f}s")
    print(f"Total street trees: {national_stats['total_trees']:,}")
    print(f"National mean crown diameter: {national_stats['national_mean']:.1f} m")
    print(f"National median crown diameter: {national_stats['national_median']:.1f} m")

    # Phase 2: Generate standard plots
    print("\nPhase 2: Generating plots...")
    plot_01_national_histogram(national_stats, PLOT_DIR)
    plot_02_city_grid(df, national_stats, hist_array, PLOT_DIR)
    plot_03_city_boxplots(df, national_stats, PLOT_DIR)
    plot_04_ranking_median(df, national_stats, PLOT_DIR)
    plot_05_ranking_large_trees(df, PLOT_DIR)
    plot_06_size_classes_stacked(df, PLOT_DIR)
    plot_07_count_vs_quality(df, PLOT_DIR)
    plot_08_quality_heatmap(df, PLOT_DIR)
    plot_09_cdf_comparison(df, national_stats, hist_array, PLOT_DIR)
    plot_10_single_vs_all(df, PLOT_DIR)

    # Phase 3: All-trees vs street-trees correlation
    print("\n  Computing all-trees vs street-trees correlation...")
    corr_data, r_pear, r_spear = plot_11_all_vs_street_correlation(df, data_dir, PLOT_DIR)

    # Phase 4: Generate report
    print("\nPhase 3: Generating report...")
    report = generate_street_report(df, national_stats, corr_data, r_pear, r_spear)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  Saved {REPORT_FILE}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Analysis complete!")
    print(f"  Report: {REPORT_FILE}")
    print(f"  Plots:  {PLOT_DIR}/ (11 files)")
    print(f"\nTop 5 cities by street tree quality:")
    top5 = df.sort_values('quality_score', ascending=False).head(5)
    for _, row in top5.iterrows():
        print(f"  {row['quality_rank']:>2d}. {row['city']} ({row['city_name']}) "
              f"-- Median={row['diam_median']:.1f}m, Large={row['large_tree_pct']:.1f}%, "
              f"Score={row['quality_score']:.3f}")
    print(f"\nAll-trees vs street-trees: Pearson r={r_pear:.3f}, Spearman rho={r_spear:.3f}")


if __name__ == '__main__':
    main()
