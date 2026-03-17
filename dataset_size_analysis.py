"""
Analyze the relationship between training set size and model performance.
Estimate optimal dataset size by fitting power-law decay to learning curves.
"""

import numpy as np
import pandas as pd
import geopandas as gpd
import math
import warnings
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split, learning_curve, KFold
from sklearn.linear_model import Ridge
from catboost import CatBoostRegressor
from scipy.optimize import curve_fit

warnings.filterwarnings('ignore')

# =====================================================================
# Load data and compute old 5-feature set
# =====================================================================
gdf = gpd.read_file('train_set_validated.shp').to_crs(epsg=2039)
gdf = gdf.explode(index_parts=False).reset_index(drop=True)
gdf = gdf[gdf.geometry.type == 'Polygon'].copy()

gdf['perimter'] = gdf.length
gdf['area'] = gdf.area
gdf['compactness'] = (4 * 3.14159265359 * gdf['area']) / (gdf['perimter'] ** 2)
gdf['perimeter_to_area'] = gdf.length / gdf.area

def old_mrr_axes(geom):
    mrr = geom.minimum_rotated_rectangle
    xs = list(mrr.exterior.xy[0])
    ys = list(mrr.exterior.xy[1])
    return max(xs) - min(xs), max(ys) - min(ys)

gdf[['major_axis_length', 'minor_axis_length']] = gdf.geometry.apply(
    lambda g: pd.Series(old_mrr_axes(g))
)

def old_eccentricity(row):
    major, minor = row['major_axis_length'], row['minor_axis_length']
    if major == minor: return 0
    if minor > major: major, minor = minor, major
    return math.sqrt(np.clip(1 - (minor**2 / max(major**2, 1)), 0, 1))

gdf['eccentricity'] = gdf.apply(old_eccentricity, axis=1)

FEATURES = ['perimter', 'area', 'compactness', 'perimeter_to_area', 'eccentricity']
TARGET = 'Point_Coun'
data = gdf[FEATURES + [TARGET]].dropna()

cv = KFold(n_splits=5, shuffle=True, random_state=42)

# Power law: MAE = a * n^(-b) + c  (c = asymptotic floor)
def power_law(n, a, b, c):
    return a * np.power(n, -b) + c

def fit_and_extrapolate(train_sizes, val_scores, label):
    """Fit power law to learning curve and extrapolate."""
    val_mae = -val_scores.mean(axis=1)
    val_std = val_scores.std(axis=1)

    # Fit power law
    try:
        popt, pcov = curve_fit(
            power_law, train_sizes, val_mae,
            p0=[10, 0.5, 1.0], maxfev=10000,
            bounds=([0, 0, 0], [100, 3, np.max(val_mae)])
        )
        a, b, c = popt

        # Extrapolate to larger sizes
        extrap_sizes = np.array([500, 750, 1000, 1500, 2000, 3000, 5000])
        extrap_mae = power_law(extrap_sizes, a, b, c)

        # Find where improvement becomes < threshold per doubling
        current_mae = val_mae[-1]
        current_n = train_sizes[-1]

        print(f"\n  {label}:")
        print(f"    Power law fit: MAE = {a:.2f} * n^(-{b:.3f}) + {c:.2f}")
        print(f"    Asymptotic floor (theoretical minimum MAE): {c:.2f}")
        print(f"    Current: n={int(current_n)}, MAE={current_mae:.3f}")
        print(f"    Extrapolated MAE by dataset size:")
        print(f"      {'n':>6s}  {'MAE':>6s}  {'Improvement vs current':>22s}  {'% improvement':>14s}")
        for n, m in zip(extrap_sizes, extrap_mae):
            imp = current_mae - m
            pct = imp / current_mae * 100
            marker = " <-- diminishing" if pct < 3 else ""
            print(f"      {n:>6d}  {m:>6.3f}  {imp:>+22.3f}  {pct:>13.1f}%{marker}")

        # Estimate "ideal" size: where doubling n improves MAE by <5%
        test_sizes = np.arange(100, 10001, 50)
        test_mae = power_law(test_sizes, a, b, c)
        for i in range(len(test_sizes) - 1):
            n1, n2 = test_sizes[i], test_sizes[i] * 2
            if n2 > 10000: break
            m1 = power_law(n1, a, b, c)
            m2 = power_law(n2, a, b, c)
            relative_gain = (m1 - m2) / m1 * 100
            if relative_gain < 2:
                print(f"    Suggested practical ceiling: ~{int(n1)} samples "
                      f"(doubling beyond this yields <2% MAE improvement)")
                break
        else:
            print(f"    Model still improving significantly at n=10000")

        return popt, extrap_sizes, extrap_mae, val_mae, val_std

    except Exception as e:
        print(f"\n  {label}: Power law fit failed: {e}")
        return None, None, None, val_mae, val_std


# =====================================================================
# FULL RANGE ANALYSIS
# =====================================================================
print("=" * 70)
print("DATASET SIZE ANALYSIS - FULL RANGE (2-44)")
print("=" * 70)

X_full = data[FEATURES]
y_full = data[TARGET]
bins = [0, 3, 5, 8, 15, 100]
yb = pd.cut(y_full, bins=bins, labels=False)
Xtr, Xte, ytr, yte = train_test_split(
    X_full, y_full, test_size=0.2, random_state=42, stratify=yb
)

# Fine-grained learning curve sizes
sizes = np.linspace(0.1, 1.0, 15)

print("\nRidge (5 features):")
train_sizes_r, train_scores_r, val_scores_r = learning_curve(
    Ridge(alpha=10), Xtr, ytr, cv=cv, scoring='neg_mean_absolute_error',
    train_sizes=sizes, n_jobs=-1
)
popt_r, ext_n_r, ext_mae_r, val_mae_r, val_std_r = fit_and_extrapolate(
    train_sizes_r, val_scores_r, "Ridge full range"
)

print("\nCatBoost tuned (5 features):")
train_sizes_c, train_scores_c, val_scores_c = learning_curve(
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=42,
                      depth=3, iterations=100, learning_rate=0.1),
    Xtr, ytr, cv=cv, scoring='neg_mean_absolute_error',
    train_sizes=sizes, n_jobs=1
)
popt_c, ext_n_c, ext_mae_c, val_mae_c, val_std_c = fit_and_extrapolate(
    train_sizes_c, val_scores_c, "CatBoost full range"
)

# =====================================================================
# <=8 RANGE ANALYSIS
# =====================================================================
print("\n")
print("=" * 70)
print("DATASET SIZE ANALYSIS - DEDICATED <=8 TREES")
print("=" * 70)

d8 = data[data[TARGET] <= 8]
X8, y8 = d8[FEATURES], d8[TARGET]
yb8 = pd.cut(y8, bins=[0, 3, 5, 9], labels=False)
X8tr, X8te, y8tr, y8te = train_test_split(
    X8, y8, test_size=0.2, random_state=42, stratify=yb8
)

print("\nRidge (5 features, <=8):")
train_sizes_r8, train_scores_r8, val_scores_r8 = learning_curve(
    Ridge(alpha=0.1), X8tr, y8tr, cv=cv, scoring='neg_mean_absolute_error',
    train_sizes=sizes, n_jobs=-1
)
popt_r8, ext_n_r8, ext_mae_r8, val_mae_r8, val_std_r8 = fit_and_extrapolate(
    train_sizes_r8, val_scores_r8, "Ridge <=8"
)

print("\nCatBoost tuned (5 features, <=8):")
train_sizes_c8, train_scores_c8, val_scores_c8 = learning_curve(
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=42,
                      depth=3, iterations=1000, learning_rate=0.01),
    X8tr, y8tr, cv=cv, scoring='neg_mean_absolute_error',
    train_sizes=sizes, n_jobs=1
)
popt_c8, ext_n_c8, ext_mae_c8, val_mae_c8, val_std_c8 = fit_and_extrapolate(
    train_sizes_c8, val_scores_c8, "CatBoost <=8"
)

# =====================================================================
# BOOTSTRAP STABILITY ANALYSIS
# =====================================================================
print("\n")
print("=" * 70)
print("BOOTSTRAP STABILITY ANALYSIS")
print("=" * 70)
print("\nHow stable are predictions across different train/test splits?")

from sklearn.utils import resample

n_bootstrap = 50
results_by_size = {}

for frac in [0.3, 0.5, 0.7, 0.9, 1.0]:
    maes = []
    for i in range(n_bootstrap):
        # Resample training data
        n_sample = int(len(Xtr) * frac)
        idx = resample(range(len(Xtr)), n_samples=n_sample, random_state=i)
        Xb, yb_s = Xtr.iloc[idx], ytr.iloc[idx]

        model = Ridge(alpha=10)
        model.fit(Xb, yb_s)
        pred = np.clip(np.round(model.predict(Xte)), 1, None)
        maes.append(mean_absolute_error(yte.values, pred))

    results_by_size[n_sample] = (np.mean(maes), np.std(maes))
    print(f"  n={n_sample:>4d} ({frac*100:>4.0f}% of train): "
          f"MAE={np.mean(maes):.3f} +/- {np.std(maes):.3f}  "
          f"(range: {np.min(maes):.3f} - {np.max(maes):.3f})")

# =====================================================================
# PLOTS
# =====================================================================
fig, axes = plt.subplots(2, 2, figsize=(16, 12))

configs = [
    (axes[0, 0], "Ridge - Full Range (2-44)", train_sizes_r, val_mae_r, val_std_r, popt_r),
    (axes[0, 1], "CatBoost - Full Range (2-44)", train_sizes_c, val_mae_c, val_std_c, popt_c),
    (axes[1, 0], "Ridge - Dedicated <=8", train_sizes_r8, val_mae_r8, val_std_r8, popt_r8),
    (axes[1, 1], "CatBoost - Dedicated <=8", train_sizes_c8, val_mae_c8, val_std_c8, popt_c8),
]

for ax, title, tsizes, vmae, vstd, popt in configs:
    ax.errorbar(tsizes, vmae, yerr=vstd, fmt='o-', capsize=3, label='Observed CV MAE')

    if popt is not None:
        # Plot fitted curve and extrapolation
        x_fit = np.linspace(tsizes[0], tsizes[-1], 100)
        ax.plot(x_fit, power_law(x_fit, *popt), 'r-', linewidth=2, label='Power law fit')

        x_ext = np.linspace(tsizes[-1], 5000, 100)
        ax.plot(x_ext, power_law(x_ext, *popt), 'r--', linewidth=2, alpha=0.5,
                label='Extrapolation')

        ax.axhline(popt[2], color='green', linestyle=':', alpha=0.7,
                    label=f'Asymptotic floor: {popt[2]:.2f}')

    ax.set_xlabel('Training Set Size')
    ax.set_ylabel('Validation MAE (trees)')
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

fig.suptitle('Learning Curves with Power-Law Extrapolation', fontsize=14)
fig.tight_layout()
fig.savefig('plots/10_dataset_size_analysis.png', dpi=150, bbox_inches='tight')
plt.close(fig)
print("\nSaved: plots/10_dataset_size_analysis.png")

# =====================================================================
# SUMMARY
# =====================================================================
print("\n")
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print("""
The power-law model MAE = a * n^(-b) + c captures how validation error
decreases with more training data:
  - 'a' and 'b' control the rate of improvement
  - 'c' is the asymptotic floor -- the minimum achievable MAE given these
    features, regardless of how much data is collected

Key question: Is the current dataset (479 total, ~383 train) on the steep
part of the curve (more data helps a lot) or the flat part (diminishing
returns)?
""")
