"""
Urban Forest Quality Analysis: 39 Israeli Cities

Analyzes crown diameter distributions from tree trunk point files to assess
and compare urban forest quality across cities. Higher crown diameter indicates
more mature, higher-quality urban forest.

Usage:
    python urban_forest_analysis.py [data_dir]

Reads XXX_tree_trunks_YYYY.shp files (output of batch_generate_points.py).
Produces: plots_urban_forest/ (10 plots) + urban_forest_report.md
"""

import os
import sys
import glob
import time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.colors import Normalize
import seaborn as sns
from scipy.stats import skew
import warnings

warnings.filterwarnings('ignore')

# =====================================================================
# Configuration
# =====================================================================

DATA_DIR = r"d:\OneDrive - Technion\Research\Shade Maps\Israel trees"
PLOT_DIR = 'plots_urban_forest'
REPORT_FILE = 'urban_forest_report.md'

# Crown diameter histogram bins (meters)
DIAM_BINS = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20, 30]
DIAM_BIN_LABELS = ['0-2', '2-3', '3-4', '4-5', '5-6', '6-7', '7-8', '7-9', '9-10',
                    '10-12', '12-15', '15-20', '20-30']

# Size classes for ecological analysis
SIZE_CLASSES = {
    '<4m': (0, 4),
    '4-6m': (4, 6),
    '6-8m': (6, 8),
    '8-10m': (8, 10),
    '10-15m': (10, 15),
    '15m+': (15, 999),
}

# Known city names (partial mapping)
CITY_NAMES = {
    'AFL': 'Afula', 'AKO': 'Akko', 'ASD': 'Ashdod', 'ASK': 'Ashkelon',
    'BBK': 'Bnei Brak', 'BSM': 'Beit Shemesh', 'BSV': 'Beersheva',
    'BTY': 'Bat Yam', 'ELT': 'Eilat', 'GTM': 'Givatayim',
    'HAI': 'Haifa', 'HDR': 'Hadera', 'HDS': 'Hod HaSharon',
    'HOL': 'Holon', 'HRZ': 'Herzliya', 'JER': 'Jerusalem',
    'KAT': 'Kfar Saba', 'KFS': 'Kfar Saba', 'KGT': 'Kiryat Gat',
    'LOD': 'Lod', 'MDN': 'Modiin', 'NHR': 'Nahariya',
    'NSZ': 'Ness Ziona', 'NTN': 'Netanya', 'NTV': 'Netivot',
    'NZR': 'Nazareth', 'PHK': 'Pardes Hanna-Karkur', 'PTV': 'Petah Tikva',
    'RAN': 'Raanana', 'RHT': 'Rahat', 'RHV': 'Rehovot',
    'RLZ': 'Rishon LeZion', 'RMG': 'Ramat Gan', 'RML': 'Ramla',
    'RSN': 'Rosh HaAyin', 'SDR': 'Sderot', 'TLV': 'Tel Aviv',
    'UMF': 'Umm al-Fahm', 'YVN': 'Yavne',
}


def save_plot(fig, name):
    path = os.path.join(PLOT_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {path}")


# =====================================================================
# Phase 1: Compute per-city statistics
# =====================================================================

def compute_city_stats(trunk_file):
    """Compute all statistics for one city from its trunk points file."""
    import geopandas as gpd

    # Read attributes only (no geometry) for speed
    df = gpd.read_file(trunk_file, ignore_geometry=True)

    city_code = os.path.basename(trunk_file).split('_tree_trunks_')[0]
    year = os.path.basename(trunk_file).split('_tree_trunks_')[1].replace('.shp', '')

    diam = df['crown_diam'].values.astype(float)
    area = df['crown_area'].values.astype(float)
    pred = df['pred_tree'].values.astype(int)

    # Basic counts
    n_trees = len(df)
    n_polygons = df['poly_id'].nunique()

    # Crown diameter statistics
    diam_mean = np.mean(diam)
    diam_median = np.median(diam)
    diam_std = np.std(diam)
    diam_q10 = np.percentile(diam, 10)
    diam_q25 = np.percentile(diam, 25)
    diam_q75 = np.percentile(diam, 75)
    diam_q90 = np.percentile(diam, 90)
    diam_p99 = np.percentile(diam, 99)
    diam_max = np.max(diam)
    diam_skew = skew(diam)
    diam_cv = diam_std / diam_mean if diam_mean > 0 else 0

    # Crown area statistics
    area_mean = np.mean(area)
    area_median = np.median(area)

    # Histogram bin counts
    hist_counts, _ = np.histogram(diam, bins=DIAM_BINS)

    # Single-tree analysis
    single_mask = pred == 1
    single_frac = single_mask.mean()
    if single_mask.sum() > 0:
        single_diam_mean = np.mean(diam[single_mask])
        single_diam_median = np.median(diam[single_mask])
    else:
        single_diam_mean = single_diam_median = np.nan

    # Size class fractions
    large_frac = np.mean(diam >= 10) * 100
    small_frac = np.mean(diam < 4) * 100

    # Size class counts
    size_class_fracs = {}
    for label, (lo, hi) in SIZE_CLASSES.items():
        size_class_fracs[f'class_{label}'] = np.mean((diam >= lo) & (diam < hi)) * 100

    stats = {
        'city': city_code,
        'city_name': CITY_NAMES.get(city_code, city_code),
        'year': year,
        'n_trees': n_trees,
        'n_polygons': n_polygons,
        'trees_per_polygon': n_trees / n_polygons if n_polygons > 0 else 0,
        'diam_mean': diam_mean,
        'diam_median': diam_median,
        'diam_std': diam_std,
        'diam_cv': diam_cv,
        'diam_q10': diam_q10,
        'diam_q25': diam_q25,
        'diam_q75': diam_q75,
        'diam_q90': diam_q90,
        'diam_p99': diam_p99,
        'diam_max': diam_max,
        'diam_skew': diam_skew,
        'diam_iqr': diam_q75 - diam_q25,
        'area_mean': area_mean,
        'area_median': area_median,
        'single_tree_frac': single_frac * 100,
        'single_diam_mean': single_diam_mean,
        'single_diam_median': single_diam_median,
        'large_tree_pct': large_frac,
        'small_tree_pct': small_frac,
        'hist_counts': hist_counts,
    }
    stats.update(size_class_fracs)

    return stats


def compute_all_cities(data_dir):
    """Compute statistics for all cities and national aggregates."""
    trunk_files = sorted(glob.glob(os.path.join(data_dir, '*_tree_trunks_*.shp')))

    if not trunk_files:
        print(f"No *_tree_trunks_*.shp files found in {data_dir}")
        sys.exit(1)

    print(f"Found {len(trunk_files)} city trunk files")

    all_stats = []
    national_hist = np.zeros(len(DIAM_BINS) - 1, dtype=np.int64)

    for f in trunk_files:
        city_code = os.path.basename(f).split('_tree_trunks_')[0]
        print(f"  {city_code}...", end=" ", flush=True)
        t0 = time.time()
        stats = compute_city_stats(f)
        national_hist += stats['hist_counts']
        all_stats.append(stats)
        print(f"{stats['n_trees']:,} trees ({time.time()-t0:.1f}s)")

    # Build DataFrame (hist_counts as separate array)
    hist_array = np.array([s['hist_counts'] for s in all_stats])
    for s in all_stats:
        del s['hist_counts']
    df = pd.DataFrame(all_stats)

    # National statistics (tree-count-weighted)
    total_trees = df['n_trees'].sum()
    national_mean = np.average(df['diam_mean'], weights=df['n_trees'])
    national_median_approx = np.average(df['diam_median'], weights=df['n_trees'])

    # Better national median from cumulative histogram
    cum = np.cumsum(national_hist)
    half = total_trees / 2
    for i, c in enumerate(cum):
        if c >= half:
            # Linear interpolation within the bin
            prev_cum = cum[i - 1] if i > 0 else 0
            frac = (half - prev_cum) / (c - prev_cum) if (c - prev_cum) > 0 else 0
            national_median = DIAM_BINS[i] + frac * (DIAM_BINS[i + 1] - DIAM_BINS[i])
            break
    else:
        national_median = national_median_approx

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

    # Composite quality score (rank-based)
    df['rank_median'] = df['diam_median'].rank(pct=True)
    df['rank_large'] = df['large_tree_pct'].rank(pct=True)
    df['rank_cv'] = df['diam_cv'].rank(pct=True)
    df['rank_count'] = df['n_trees'].rank(pct=True)
    df['quality_score'] = (0.4 * df['rank_median'] + 0.3 * df['rank_large'] +
                           0.15 * df['rank_cv'] + 0.15 * df['rank_count'])
    df['quality_rank'] = df['quality_score'].rank(ascending=False).astype(int)

    return df, national_stats, hist_array


# =====================================================================
# Phase 2: Plotting
# =====================================================================

def plot_01_national_histogram(national_stats, out_dir, label=""):
    """National crown diameter distribution."""
    fig, ax1 = plt.subplots(figsize=(12, 6))

    hist = national_stats['national_hist']
    bin_centers = [(DIAM_BINS[i] + DIAM_BINS[i + 1]) / 2 for i in range(len(hist))]
    bin_widths = [DIAM_BINS[i + 1] - DIAM_BINS[i] for i in range(len(hist))]

    # Normalize to density
    total = hist.sum()
    density = hist / (total * np.array(bin_widths))

    bars = ax1.bar(bin_centers, density, width=bin_widths, edgecolor='black',
                   alpha=0.7, color='forestgreen', align='center')
    ax1.set_xlabel('Crown Diameter (m)', fontsize=13)
    ax1.set_ylabel('Density', fontsize=13)
    tree_label = "Street Tree" if label else "Tree"
    ax1.set_title(f'{label}National {tree_label} Crown Diameter Distribution\n'
                  f'{national_stats["total_trees"]:,} {tree_label.lower()}s across {national_stats["n_cities"]} cities',
                  fontsize=14)

    # Mean and median lines
    ax1.axvline(national_stats['national_mean'], color='red', linestyle='--', linewidth=2,
                label=f'Mean = {national_stats["national_mean"]:.1f} m')
    ax1.axvline(national_stats['national_median'], color='blue', linestyle='--', linewidth=2,
                label=f'Median = {national_stats["national_median"]:.1f} m')

    # Cumulative distribution on secondary axis
    ax2 = ax1.twinx()
    cum_pct = np.cumsum(hist) / total * 100
    ax2.plot([DIAM_BINS[0]] + [DIAM_BINS[i + 1] for i in range(len(hist))],
             [0] + list(cum_pct), color='navy', linewidth=2, label='Cumulative %')
    ax2.set_ylabel('Cumulative %', fontsize=13, color='navy')
    ax2.set_ylim(0, 105)
    ax2.tick_params(axis='y', labelcolor='navy')

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='center right', fontsize=11)

    ax1.set_xlim(0, 25)
    fig.tight_layout()
    save_plot(fig, '01_national_crown_diameter_hist.png')


def plot_02_city_grid(df, national_stats, hist_array, out_dir, label=""):
    """Small multiples: crown diameter distribution per city."""
    sorted_idx = df['diam_median'].argsort().values
    n_cities = len(df)
    ncols = 7
    nrows = int(np.ceil(n_cities / ncols))

    fig, axes = plt.subplots(nrows, ncols, figsize=(24, nrows * 3), sharex=True)
    axes = axes.flatten()

    # National density for overlay
    nat_hist = national_stats['national_hist']
    nat_total = nat_hist.sum()
    bin_widths = np.array([DIAM_BINS[i + 1] - DIAM_BINS[i] for i in range(len(nat_hist))])
    bin_centers = [(DIAM_BINS[i] + DIAM_BINS[i + 1]) / 2 for i in range(len(nat_hist))]
    nat_density = nat_hist / (nat_total * bin_widths)

    for plot_idx, city_idx in enumerate(sorted_idx):
        ax = axes[plot_idx]
        row = df.iloc[city_idx]
        city_hist = hist_array[city_idx]
        city_total = city_hist.sum()

        if city_total > 0:
            city_density = city_hist / (city_total * bin_widths)
            ax.bar(bin_centers, city_density, width=bin_widths, alpha=0.7,
                   color='forestgreen', edgecolor='none')

        # National overlay
        ax.plot(bin_centers, nat_density, color='black', linewidth=1, alpha=0.5)

        ax.set_title(f"{row['city']} ({row['n_trees']:,})\nMd={row['diam_median']:.1f}m",
                     fontsize=8)
        ax.set_xlim(0, 22)
        ax.set_yticks([])

    # Hide unused axes
    for i in range(n_cities, len(axes)):
        axes[i].set_visible(False)

    fig.suptitle(f'{label}Crown Diameter Distribution by City (sorted by median, national overlay in black)',
                 fontsize=14, y=1.01)
    fig.tight_layout()
    save_plot(fig, '02_city_distributions_grid.png')


def plot_03_city_boxplots(df, national_stats, out_dir, label=""):
    """Box plots from stored quantiles."""
    fig, ax = plt.subplots(figsize=(14, 10))

    sorted_df = df.sort_values('diam_median')
    y_pos = range(len(sorted_df))

    for i, (_, row) in enumerate(sorted_df.iterrows()):
        color = 'forestgreen' if row['diam_median'] >= national_stats['national_median'] else 'coral'
        # Box: Q25-Q75
        ax.barh(i, row['diam_q75'] - row['diam_q25'], left=row['diam_q25'],
                height=0.6, color=color, alpha=0.7, edgecolor='black', linewidth=0.5)
        # Median line
        ax.plot([row['diam_median'], row['diam_median']], [i - 0.3, i + 0.3],
                color='black', linewidth=2)
        # Whiskers: Q10-Q90
        ax.plot([row['diam_q10'], row['diam_q25']], [i, i], color='black', linewidth=1)
        ax.plot([row['diam_q75'], row['diam_q90']], [i, i], color='black', linewidth=1)
        ax.plot([row['diam_q10'], row['diam_q10']], [i - 0.15, i + 0.15], color='black', linewidth=1)
        ax.plot([row['diam_q90'], row['diam_q90']], [i - 0.15, i + 0.15], color='black', linewidth=1)

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([f"{r['city']} ({r['city_name']})" for _, r in sorted_df.iterrows()], fontsize=9)
    ax.axvline(national_stats['national_median'], color='blue', linestyle='--', linewidth=2,
               label=f'National median = {national_stats["national_median"]:.1f} m')
    ax.set_xlabel('Crown Diameter (m)', fontsize=13)
    ax.set_title(f'{label}Crown Diameter Distribution by City\n(box=IQR, whiskers=10th-90th percentile)', fontsize=14)
    ax.legend(fontsize=11)
    ax.set_xlim(0, 22)
    fig.tight_layout()
    save_plot(fig, '03_city_boxplots.png')


def plot_04_ranking_median(df, national_stats, out_dir, label=""):
    """City ranking by median crown diameter."""
    fig, ax = plt.subplots(figsize=(12, 10))

    sorted_df = df.sort_values('diam_median')
    nat_med = national_stats['national_median']

    colors = ['forestgreen' if v >= nat_med * 1.1 else
              ('gold' if v >= nat_med * 0.9 else 'coral')
              for v in sorted_df['diam_median']]

    bars = ax.barh(range(len(sorted_df)), sorted_df['diam_median'], color=colors,
                   edgecolor='black', linewidth=0.5, alpha=0.8)

    # Error bars (IQR)
    for i, (_, row) in enumerate(sorted_df.iterrows()):
        ax.plot([row['diam_q25'], row['diam_q75']], [i, i],
                color='black', linewidth=1.5, alpha=0.5)

    ax.set_yticks(range(len(sorted_df)))
    ax.set_yticklabels([f"{r['city']} ({r['city_name']})" for _, r in sorted_df.iterrows()], fontsize=9)
    ax.axvline(nat_med, color='blue', linestyle='--', linewidth=2,
               label=f'National median = {nat_med:.1f} m')
    ax.set_xlabel('Median Crown Diameter (m)', fontsize=13)
    ax.set_title(f'{label}City Ranking by Median Crown Diameter\n(green=above, gold=near, coral=below national median)',
                 fontsize=13)
    ax.legend(fontsize=11)

    # Annotate values
    for i, (_, row) in enumerate(sorted_df.iterrows()):
        ax.text(row['diam_median'] + 0.1, i, f"{row['diam_median']:.1f}",
                va='center', fontsize=8)

    fig.tight_layout()
    save_plot(fig, '04_city_ranking_median_diam.png')


def plot_05_ranking_large_trees(df, out_dir, label=""):
    """City ranking by large tree fraction (>= 10m)."""
    fig, ax = plt.subplots(figsize=(12, 10))

    sorted_df = df.sort_values('large_tree_pct')
    nat_avg = np.average(df['large_tree_pct'], weights=df['n_trees'])

    cmap = cm.YlGn
    norm = Normalize(vmin=sorted_df['large_tree_pct'].min(),
                     vmax=sorted_df['large_tree_pct'].max())
    colors = [cmap(norm(v)) for v in sorted_df['large_tree_pct']]

    ax.barh(range(len(sorted_df)), sorted_df['large_tree_pct'], color=colors,
            edgecolor='black', linewidth=0.5)
    ax.set_yticks(range(len(sorted_df)))
    ax.set_yticklabels([f"{r['city']} ({r['city_name']})" for _, r in sorted_df.iterrows()], fontsize=9)
    ax.axvline(nat_avg, color='blue', linestyle='--', linewidth=2,
               label=f'National average = {nat_avg:.1f}%')
    ax.set_xlabel('Trees with Crown Diameter >= 10m (%)', fontsize=13)
    ax.set_title(f'{label}City Ranking by Large Tree Fraction\n(mature urban forest indicator)', fontsize=13)
    ax.legend(fontsize=11)

    for i, (_, row) in enumerate(sorted_df.iterrows()):
        ax.text(row['large_tree_pct'] + 0.2, i, f"{row['large_tree_pct']:.1f}%",
                va='center', fontsize=8)

    fig.tight_layout()
    save_plot(fig, '05_city_ranking_large_trees.png')


def plot_06_size_classes_stacked(df, out_dir, label=""):
    """Stacked bar chart of crown size classes per city."""
    fig, ax = plt.subplots(figsize=(14, 10))

    class_cols = [f'class_{k}' for k in SIZE_CLASSES.keys()]
    class_labels = list(SIZE_CLASSES.keys())

    # Sort by proportion of large trees (10m+)
    df_sorted = df.sort_values('large_tree_pct')

    colors = ['#d4e6b5', '#a8d08d', '#6bb04d', '#3a8b2e', '#1e6b1e', '#0d4a0d']

    bottom = np.zeros(len(df_sorted))
    for i, (col, label) in enumerate(zip(class_cols, class_labels)):
        vals = df_sorted[col].values
        ax.barh(range(len(df_sorted)), vals, left=bottom, color=colors[i],
                label=label, edgecolor='white', linewidth=0.3)
        bottom += vals

    ax.set_yticks(range(len(df_sorted)))
    ax.set_yticklabels([f"{r['city']}" for _, r in df_sorted.iterrows()], fontsize=9)
    ax.set_xlabel('Percentage of Trees (%)', fontsize=13)
    ax.set_title(f'{label}Crown Diameter Size Class Distribution by City', fontsize=14)
    ax.legend(title='Crown Diameter', bbox_to_anchor=(1.01, 1), loc='upper left', fontsize=10)
    ax.set_xlim(0, 100)
    fig.tight_layout()
    save_plot(fig, '06_crown_size_classes_stacked.png')


def plot_07_count_vs_quality(df, out_dir, label=""):
    """Scatter: tree count vs median crown diameter."""
    fig, ax = plt.subplots(figsize=(10, 8))

    ax.scatter(df['n_trees'], df['diam_median'], s=df['large_tree_pct'] * 10 + 20,
               c=df['quality_score'], cmap='RdYlGn', edgecolors='black', linewidth=0.5,
               alpha=0.8, vmin=0, vmax=1)

    # Label notable cities
    for _, row in df.iterrows():
        if row['city'] in ('TLV', 'JER', 'HAI', 'ELT', 'AFL', 'BSV', 'RLZ') or \
           row['quality_rank'] <= 3 or row['quality_rank'] >= len(df) - 2:
            ax.annotate(row['city'], (row['n_trees'], row['diam_median']),
                        textcoords='offset points', xytext=(5, 5), fontsize=9)

    ax.set_xscale('log')
    ax.set_xlabel('Total Tree Count (log scale)', fontsize=13)
    ax.set_ylabel('Median Crown Diameter (m)', fontsize=13)
    tree_label = "Street Tree" if label else "Tree"
    ax.set_title(f'{label}{tree_label} Count vs. Crown Quality\n(point size = large tree %, color = quality score)',
                 fontsize=13)
    ax.grid(True, alpha=0.3)

    sm = cm.ScalarMappable(cmap='RdYlGn', norm=Normalize(0, 1))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6)
    cbar.set_label('Composite Quality Score', fontsize=11)

    fig.tight_layout()
    save_plot(fig, '07_tree_count_vs_quality.png')


def plot_08_quality_heatmap(df, out_dir, label=""):
    """Multi-metric quality heatmap."""
    fig, ax = plt.subplots(figsize=(12, 12))

    metrics = ['diam_median', 'diam_mean', 'large_tree_pct', 'small_tree_pct',
               'diam_cv', 'n_trees', 'single_tree_frac', 'area_mean']
    metric_labels = ['Median\nDiam', 'Mean\nDiam', 'Large\nTree %', 'Small\nTree %',
                     'Diam\nCV', 'Tree\nCount', 'Single\nTree %', 'Mean\nArea']

    sorted_df = df.sort_values('quality_score', ascending=False)

    # Normalize each metric to 0-1 percentile rank
    heat_data = pd.DataFrame()
    for m in metrics:
        if m == 'small_tree_pct':
            heat_data[m] = 1 - sorted_df[m].rank(pct=True)  # lower is better
        else:
            heat_data[m] = sorted_df[m].rank(pct=True)

    sns.heatmap(heat_data.values, ax=ax, cmap='RdYlGn', vmin=0, vmax=1,
                xticklabels=metric_labels, linewidths=0.5, linecolor='white',
                yticklabels=[f"{r['city']} ({r['city_name']})" for _, r in sorted_df.iterrows()],
                cbar_kws={'label': 'Percentile Rank (higher = better)', 'shrink': 0.6})

    # Add quality score as text
    for i, (_, row) in enumerate(sorted_df.iterrows()):
        ax.text(len(metrics) + 0.3, i + 0.5, f"{row['quality_score']:.2f}",
                va='center', fontsize=8)

    quality_label = "Street Tree" if label else "Urban Forest"
    ax.set_title(f'{quality_label} Quality: Multi-Metric Comparison\n(sorted by composite quality score)',
                 fontsize=14, pad=20)
    fig.tight_layout()
    save_plot(fig, '08_quality_index_heatmap.png')


def plot_09_cdf_comparison(df, national_stats, hist_array, out_dir, label=""):
    """CDF comparison: top 5, bottom 5, national."""
    fig, ax = plt.subplots(figsize=(10, 7))

    sorted_df = df.sort_values('diam_median')
    bin_edges = np.array(DIAM_BINS)

    # National CDF
    nat_cum = np.cumsum(national_stats['national_hist'])
    nat_cdf = nat_cum / nat_cum[-1] * 100
    ax.plot([bin_edges[0]] + [bin_edges[i + 1] for i in range(len(nat_cdf))],
            [0] + list(nat_cdf), color='black', linewidth=3, label='National', zorder=10)

    # Bottom 5
    for idx in sorted_df.index[:5]:
        row = df.loc[idx]
        city_hist = hist_array[df.index.get_loc(idx)]
        city_cum = np.cumsum(city_hist) / city_hist.sum() * 100
        ax.plot([bin_edges[0]] + [bin_edges[i + 1] for i in range(len(city_cum))],
                [0] + list(city_cum), color='coral', linewidth=1.5, alpha=0.7,
                label=f"{row['city']} (Md={row['diam_median']:.1f}m)")

    # Top 5
    for idx in sorted_df.index[-5:]:
        row = df.loc[idx]
        city_hist = hist_array[df.index.get_loc(idx)]
        city_cum = np.cumsum(city_hist) / city_hist.sum() * 100
        ax.plot([bin_edges[0]] + [bin_edges[i + 1] for i in range(len(city_cum))],
                [0] + list(city_cum), color='forestgreen', linewidth=1.5, alpha=0.7,
                label=f"{row['city']} (Md={row['diam_median']:.1f}m)")

    ax.set_xlabel('Crown Diameter (m)', fontsize=13)
    ax.set_ylabel('Cumulative Percentage (%)', fontsize=13)
    ax.set_title(f'{label}Crown Diameter CDF: Top 5 vs Bottom 5 Cities\n(green = top, coral = bottom, black = national)',
                 fontsize=13)
    ax.legend(fontsize=9, loc='lower right')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 105)
    fig.tight_layout()
    save_plot(fig, '09_national_vs_city_cdf.png')


def plot_10_single_vs_all(df, out_dir, label=""):
    """Scatter: single-tree median vs all-trees median."""
    fig, ax = plt.subplots(figsize=(8, 8))

    valid = df.dropna(subset=['single_diam_median'])
    ax.scatter(valid['diam_median'], valid['single_diam_median'], s=60,
               c='forestgreen', edgecolors='black', linewidth=0.5, alpha=0.8)

    lims = [min(valid['diam_median'].min(), valid['single_diam_median'].min()) - 0.5,
            max(valid['diam_median'].max(), valid['single_diam_median'].max()) + 0.5]
    ax.plot(lims, lims, 'r--', linewidth=2, label='1:1 line')

    for _, row in valid.iterrows():
        if abs(row['single_diam_median'] - row['diam_median']) > 0.5 or \
           row['city'] in ('TLV', 'JER', 'HAI', 'ELT'):
            ax.annotate(row['city'], (row['diam_median'], row['single_diam_median']),
                        textcoords='offset points', xytext=(5, 5), fontsize=8)

    ax.set_xlabel('Median Crown Diameter — All Trees (m)', fontsize=12)
    ax.set_ylabel('Median Crown Diameter — Single-Tree Polygons Only (m)', fontsize=12)
    ax.set_title(f'{label}Single-Tree vs All-Trees Crown Diameter\n(above line = multi-tree polygons inflate estimates)',
                 fontsize=12)
    ax.legend(fontsize=11)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    save_plot(fig, '10_single_vs_all_trees.png')


# =====================================================================
# Phase 3: Report generation
# =====================================================================

def generate_report(df, national_stats):
    """Generate the markdown report."""
    sorted_by_quality = df.sort_values('quality_score', ascending=False)
    sorted_by_median = df.sort_values('diam_median', ascending=False)
    sorted_by_large = df.sort_values('large_tree_pct', ascending=False)

    report = f"""# Urban Forest Quality Analysis: {national_stats['n_cities']} Israeli Cities

## Summary

- **Total trees analyzed**: {national_stats['total_trees']:,}
- **Total crown polygons**: {national_stats['total_polygons']:,}
- **National mean crown diameter**: {national_stats['national_mean']:.1f} m
- **National median crown diameter**: {national_stats['national_median']:.1f} m
- **Large trees (>= 10m crown)**: {national_stats['national_large_pct']:.1f}% nationally
- **Small trees (< 4m crown)**: {national_stats['national_small_pct']:.1f}% nationally

### Key Findings

1. **Top 3 cities by crown quality**: {', '.join(f"{r['city']} ({r['city_name']})" for _, r in sorted_by_quality.head(3).iterrows())}
2. **Bottom 3 cities**: {', '.join(f"{r['city']} ({r['city_name']})" for _, r in sorted_by_quality.tail(3).iterrows())}
3. **Largest median crown**: {sorted_by_median.iloc[0]['city']} ({sorted_by_median.iloc[0]['city_name']}) at {sorted_by_median.iloc[0]['diam_median']:.1f} m
4. **Smallest median crown**: {sorted_by_median.iloc[-1]['city']} ({sorted_by_median.iloc[-1]['city_name']}) at {sorted_by_median.iloc[-1]['diam_median']:.1f} m
5. **Most large trees**: {sorted_by_large.iloc[0]['city']} ({sorted_by_large.iloc[0]['city_name']}) at {sorted_by_large.iloc[0]['large_tree_pct']:.1f}%

## Methodology

### Data Pipeline

Tree crown polygons were extracted from digital surface model (DSM) derived elevation data for each city. The analysis pipeline:

1. **Geometry repair**: Invalid polygons fixed, multi-parts exploded, contained polygons removed
2. **Feature extraction**: 20 morphological features computed per polygon
3. **Tree count prediction**: Polygons with area < 150 m^2 and compactness > 0.6 assigned 1 tree; remaining polygons predicted using Ridge regression (R2=0.736)
4. **Point generation**: Tree trunk locations placed via constrained k-means inside each polygon

### Crown Diameter Derivation

For each polygon with predicted N trees:
- Crown area per tree = polygon area / N
- Crown diameter = 2 * sqrt(crown_area / pi) (equivalent circular diameter)

### Quality Definition

Urban forest quality is assessed by crown diameter as a proxy for tree maturity and canopy development. Larger crown diameters indicate:
- More mature trees with greater ecosystem services
- Better growing conditions (soil, water, space)
- Higher canopy coverage and shade provision

A **composite quality score** combines: median crown diameter (40%), large tree fraction (30%), crown diameter diversity/CV (15%), and total tree count (15%).

## National Crown Diameter Distribution

![National Distribution](plots_urban_forest/01_national_crown_diameter_hist.png)

The national distribution is right-skewed, with most trees in the 4-8m crown diameter range. The median ({national_stats['national_median']:.1f} m) is slightly below the mean ({national_stats['national_mean']:.1f} m), reflecting the tail of very large crown polygons.

## City Rankings

### By Median Crown Diameter

![Median Ranking](plots_urban_forest/04_city_ranking_median_diam.png)

"""
    # Ranking table
    report += "| Rank | City | Name | Median (m) | Mean (m) | IQR (m) | Trees |\n"
    report += "|------|------|------|-----------|---------|---------|-------|\n"
    for rank, (_, row) in enumerate(sorted_by_median.iterrows(), 1):
        report += (f"| {rank} | {row['city']} | {row['city_name']} | "
                   f"{row['diam_median']:.1f} | {row['diam_mean']:.1f} | "
                   f"{row['diam_iqr']:.1f} | {row['n_trees']:,} |\n")

    report += f"""
### By Large Tree Fraction (crown >= 10m)

![Large Tree Ranking](plots_urban_forest/05_city_ranking_large_trees.png)

### Composite Urban Forest Quality Score

![Quality Heatmap](plots_urban_forest/08_quality_index_heatmap.png)

"""
    # Quality score table
    report += "| Rank | City | Name | Quality Score | Median Diam | Large Tree % | Trees |\n"
    report += "|------|------|------|--------------|------------|-------------|-------|\n"
    for _, row in sorted_by_quality.iterrows():
        report += (f"| {row['quality_rank']} | {row['city']} | {row['city_name']} | "
                   f"{row['quality_score']:.3f} | {row['diam_median']:.1f} m | "
                   f"{row['large_tree_pct']:.1f}% | {row['n_trees']:,} |\n")

    report += f"""
## Detailed City Comparisons

### Crown Diameter Distributions

![City Grid](plots_urban_forest/02_city_distributions_grid.png)

### Box Plot Comparison

![Box Plots](plots_urban_forest/03_city_boxplots.png)

### Crown Size Class Distribution

![Size Classes](plots_urban_forest/06_crown_size_classes_stacked.png)

## Correlations and Patterns

### Tree Count vs Quality

![Count vs Quality](plots_urban_forest/07_tree_count_vs_quality.png)

### CDF Comparison: Top and Bottom Cities

![CDF Comparison](plots_urban_forest/09_national_vs_city_cdf.png)

### Single-Tree vs All-Trees Estimates

![Single vs All](plots_urban_forest/10_single_vs_all_trees.png)

Points above the 1:1 line indicate cities where multi-tree polygon estimates inflate the median crown diameter. Points near or on the line suggest the multi-tree estimates are consistent with single-tree measurements.

## Data Quality Notes

### Single-Tree Polygon Fraction

The fraction of trees originating from single-tree polygons (pred_trees=1) varies by city. Higher single-tree fractions produce more reliable crown diameter estimates.

| City | Single-Tree Fraction | Note |
|------|---------------------|------|
"""
    for _, row in df.sort_values('single_tree_frac').iterrows():
        note = ""
        if row['single_tree_frac'] < 60:
            note = "Low -- many merged canopies"
        elif row['single_tree_frac'] > 85:
            note = "High -- mostly individual crowns"
        report += f"| {row['city']} | {row['single_tree_frac']:.1f}% | {note} |\n"

    report += f"""
### Outlier Detection

Cities with 99th percentile crown diameter > 25m may contain artifacts from large single-prediction polygons:

"""
    outlier_cities = df[df['diam_p99'] > 25].sort_values('diam_p99', ascending=False)
    if len(outlier_cities) > 0:
        report += "| City | 99th Percentile (m) | Max (m) |\n"
        report += "|------|--------------------|---------|\n"
        for _, row in outlier_cities.iterrows():
            report += f"| {row['city']} | {row['diam_p99']:.1f} | {row['diam_max']:.1f} |\n"
    else:
        report += "No cities have 99th percentile > 25m.\n"

    report += f"""
### Limitations

1. Crown diameter is derived from predicted tree counts -- prediction errors propagate to crown size estimates
2. Multi-tree polygons split crown area equally among predicted trees (assumes uniform crown sizes within a cluster)
3. The single-tree filter (area < 150m^2, compactness > 0.6) may misclassify some small multi-tree clusters as single trees
4. No species information is available -- crown size variation across species is not accounted for
5. Temporal variation: most data is from 2022 orthophotos; SDR uses 2025 data

## Appendix: Full Per-City Statistics

"""
    report += ("| City | Name | Trees | Polygons | Median Diam | Mean Diam | Std | Q25 | Q75 | "
               "Large % | Small % | CV | Single % | Quality Score |\n")
    report += ("|----|------|-------|----------|------------|----------|-----|-----|-----|----|-----|--|--|--|\n")
    for _, row in sorted_by_quality.iterrows():
        report += (f"| {row['city']} | {row['city_name']} | {row['n_trees']:,} | {row['n_polygons']:,} | "
                   f"{row['diam_median']:.1f} | {row['diam_mean']:.1f} | {row['diam_std']:.1f} | "
                   f"{row['diam_q25']:.1f} | {row['diam_q75']:.1f} | "
                   f"{row['large_tree_pct']:.1f} | {row['small_tree_pct']:.1f} | "
                   f"{row['diam_cv']:.2f} | {row['single_tree_frac']:.0f} | "
                   f"{row['quality_score']:.3f} |\n")

    report += """
## Diagnostic Plots

All plots saved to `plots_urban_forest/`:

1. `01_national_crown_diameter_hist.png` -- National crown diameter histogram with CDF
2. `02_city_distributions_grid.png` -- Small multiples: per-city distributions
3. `03_city_boxplots.png` -- Box plots (Q10-Q90) sorted by median
4. `04_city_ranking_median_diam.png` -- City ranking by median crown diameter
5. `05_city_ranking_large_trees.png` -- City ranking by large tree fraction
6. `06_crown_size_classes_stacked.png` -- Size class proportions per city
7. `07_tree_count_vs_quality.png` -- Tree count vs crown quality scatter
8. `08_quality_index_heatmap.png` -- Multi-metric quality heatmap
9. `09_national_vs_city_cdf.png` -- CDF: top 5 vs bottom 5 cities
10. `10_single_vs_all_trees.png` -- Single-tree vs all-trees crown diameter
"""
    return report


# =====================================================================
# Main
# =====================================================================

def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else DATA_DIR
    os.makedirs(PLOT_DIR, exist_ok=True)

    print("=" * 60)
    print("Urban Forest Quality Analysis")
    print("=" * 60)

    # Phase 1: Compute statistics
    print("\nPhase 1: Computing per-city statistics...")
    t0 = time.time()
    df, national_stats, hist_array = compute_all_cities(data_dir)
    print(f"\nStatistics computed in {time.time()-t0:.1f}s")
    print(f"Total trees: {national_stats['total_trees']:,}")
    print(f"National mean crown diameter: {national_stats['national_mean']:.1f} m")
    print(f"National median crown diameter: {national_stats['national_median']:.1f} m")

    # Phase 2: Generate plots
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

    # Phase 3: Generate report
    print("\nPhase 3: Generating report...")
    report = generate_report(df, national_stats)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  Saved {REPORT_FILE}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Analysis complete!")
    print(f"  Report: {REPORT_FILE}")
    print(f"  Plots:  {PLOT_DIR}/ (10 files)")
    print(f"\nTop 5 cities by quality score:")
    top5 = df.sort_values('quality_score', ascending=False).head(5)
    for _, row in top5.iterrows():
        print(f"  {row['quality_rank']:>2d}. {row['city']} ({row['city_name']}) "
              f"-- Median={row['diam_median']:.1f}m, Large={row['large_tree_pct']:.1f}%, "
              f"Score={row['quality_score']:.3f}")


if __name__ == '__main__':
    main()
