"""
Generate evaluation plots for the old model (5-feature CatBoost).
Saves all plots to plots_old_model/ directory.
"""

import numpy as np
import pandas as pd
import geopandas as gpd
import math
import os
import warnings
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import spearmanr
from sklearn.model_selection import train_test_split, KFold, GridSearchCV
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from catboost import CatBoostRegressor

warnings.filterwarnings('ignore')

RANDOM_STATE = 42
TARGET = 'Point_Coun'
OLD_FEATURES = ['perimeter', 'area', 'compactness', 'perimeter_to_area', 'eccentricity']
PLOT_DIR = 'plots_old_model'
os.makedirs(PLOT_DIR, exist_ok=True)

def save_plot(fig, name):
    path = os.path.join(PLOT_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {path}")

def evaluate(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    rho, _ = spearmanr(y_true, y_pred)
    w1 = np.mean(np.abs(y_true - y_pred) <= 1) * 100
    w2 = np.mean(np.abs(y_true - y_pred) <= 2) * 100
    return {'MAE': mae, 'RMSE': rmse, 'R2': r2, 'Spearman': rho, 'Within_1': w1, 'Within_2': w2}

# =====================================================================
# Load data and extract OLD features
# =====================================================================
print("Loading data and extracting features...")
gdf = gpd.read_file('train_set_validated.shp').to_crs(epsg=2039)
gdf = gdf.explode(index_parts=False).reset_index(drop=True)
gdf = gdf[gdf.geometry.type == 'Polygon'].copy()

gdf['perimeter'] = gdf.geometry.length
gdf['area'] = gdf.geometry.area
gdf['compactness'] = (4 * math.pi * gdf['area']) / (gdf['perimeter'] ** 2)
gdf['perimeter_to_area'] = gdf['perimeter'] / gdf['area']

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
    if major == minor:
        return 0
    if minor > major:
        major, minor = minor, major
    return math.sqrt(np.clip(1 - (minor ** 2 / max(major ** 2, 1)), 0, 1))

gdf['eccentricity'] = gdf.apply(old_eccentricity, axis=1)

# Correct MRR axes for comparison
def correct_mrr_axes(geom):
    mrr = geom.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)
    side1 = math.hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
    side2 = math.hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
    return max(side1, side2), min(side1, side2)

gdf[['correct_major', 'correct_minor']] = gdf.geometry.apply(
    lambda g: pd.Series(correct_mrr_axes(g))
)

data = gdf[OLD_FEATURES + [TARGET, 'major_axis_length', 'minor_axis_length',
                            'correct_major', 'correct_minor']].dropna()
X = data[OLD_FEATURES]
y = data[TARGET]

# Splits
bins = [0, 3, 5, 8, 15, 100]
y_binned = pd.cut(y, bins=bins, labels=False)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y_binned
)

data8 = data[data[TARGET] <= 8]
X8, y8 = data8[OLD_FEATURES], data8[TARGET]
y8_binned = pd.cut(y8, bins=[0, 3, 5, 9], labels=False)
X8_train, X8_test, y8_train, y8_test = train_test_split(
    X8, y8, test_size=0.2, random_state=RANDOM_STATE, stratify=y8_binned
)

cv = KFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

# =====================================================================
# Train models
# =====================================================================
print("Training models...")

# Full range
old_cb = CatBoostRegressor(
    task_type='GPU', od_type='IncToDec', od_pval=0.001,
    od_wait=100, verbose=0, random_seed=RANDOM_STATE
)
old_cb.fit(X_train, y_train)
pred_old = np.clip(np.round(old_cb.predict(X_test)), 1, None)

grid_cb = GridSearchCV(
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE, loss_function='RMSE'),
    {'iterations': [100, 300, 500, 1000], 'depth': [3, 5, 7],
     'learning_rate': [0.01, 0.05, 0.1]},
    cv=cv, scoring='neg_mean_absolute_error', refit=True, n_jobs=1
)
grid_cb.fit(X_train, y_train)
pred_tuned = np.clip(np.round(grid_cb.predict(X_test)), 1, None)

grid_ridge = GridSearchCV(
    Ridge(), {'alpha': [0.01, 0.1, 1.0, 10.0, 100.0]},
    cv=cv, scoring='neg_mean_absolute_error', refit=True, n_jobs=-1
)
grid_ridge.fit(X_train, y_train)
pred_ridge = np.clip(np.round(grid_ridge.predict(X_test)), 1, None)

# <=8 models
old_cb8 = CatBoostRegressor(
    task_type='GPU', od_type='IncToDec', od_pval=0.001,
    od_wait=100, verbose=0, random_seed=RANDOM_STATE
)
old_cb8.fit(X8_train, y8_train)
pred8_old = np.clip(np.round(old_cb8.predict(X8_test)), 1, None)

grid8_cb = GridSearchCV(
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE, loss_function='RMSE'),
    {'iterations': [100, 300, 500, 1000], 'depth': [3, 5, 7],
     'learning_rate': [0.01, 0.05, 0.1]},
    cv=cv, scoring='neg_mean_absolute_error', refit=True, n_jobs=1
)
grid8_cb.fit(X8_train, y8_train)
pred8_tuned = np.clip(np.round(grid8_cb.predict(X8_test)), 1, None)

grid8_ridge = GridSearchCV(
    Ridge(), {'alpha': [0.01, 0.1, 1.0, 10.0, 100.0]},
    cv=cv, scoring='neg_mean_absolute_error', refit=True, n_jobs=-1
)
grid8_ridge.fit(X8_train, y8_train)
pred8_ridge = np.clip(np.round(grid8_ridge.predict(X8_test)), 1, None)

print("All models trained.\n")

# =====================================================================
# PLOT 1: MRR Axis Bug Visualization
# =====================================================================
print("Generating plots...")

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
axes[0].scatter(data['correct_major'], data['major_axis_length'], alpha=0.5, s=20)
lims = [0, max(data['correct_major'].max(), data['major_axis_length'].max()) * 1.05]
axes[0].plot(lims, lims, 'r--', linewidth=2)
axes[0].set_xlabel('Correct Major Axis (m)')
axes[0].set_ylabel('Old (Buggy) Major Axis (m)')
axes[0].set_title('Major Axis: Old vs Correct')

axes[1].scatter(data['correct_minor'], data['minor_axis_length'], alpha=0.5, s=20, color='green')
lims = [0, max(data['correct_minor'].max(), data['minor_axis_length'].max()) * 1.05]
axes[1].plot(lims, lims, 'r--', linewidth=2)
axes[1].set_xlabel('Correct Minor Axis (m)')
axes[1].set_ylabel('Old (Buggy) Minor Axis (m)')
axes[1].set_title('Minor Axis: Old vs Correct')

fig.suptitle('MRR Axis Bug: Axis-Aligned BBox vs Actual Side Lengths', fontsize=13)
fig.tight_layout()
save_plot(fig, '01_mrr_axis_bug.png')

# =====================================================================
# PLOT 2: Feature Correlation Heatmap (5 features)
# =====================================================================
fig, ax = plt.subplots(figsize=(8, 6))
corr = X.corr()
sns.heatmap(corr, annot=True, fmt='.2f', cmap='coolwarm', center=0, ax=ax,
            square=True, linewidths=0.5)
ax.set_title('Feature Correlation Matrix (Old 5-Feature Set)')
fig.tight_layout()
save_plot(fig, '02_feature_correlation.png')

# =====================================================================
# PLOT 3: Feature-Target Scatter (5 features)
# =====================================================================
fig, axes = plt.subplots(1, 5, figsize=(22, 4))
for i, feat in enumerate(OLD_FEATURES):
    axes[i].scatter(data[feat], data[TARGET], alpha=0.4, s=15)
    axes[i].set_xlabel(feat)
    axes[i].set_ylabel('Trunk Count' if i == 0 else '')
    rho, _ = spearmanr(data[feat], data[TARGET])
    axes[i].set_title(f'rho={rho:.3f}')
fig.suptitle('Feature vs Trunk Count', fontsize=13)
fig.tight_layout()
save_plot(fig, '03_feature_target_scatter.png')

# =====================================================================
# PLOT 4: Predicted vs Actual -- All 3 models, full range
# =====================================================================
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
for ax, pred, name in zip(axes,
    [pred_old, pred_tuned, pred_ridge],
    ['CatBoost (old config)', 'CatBoost (tuned)', 'Ridge']):
    ax.scatter(y_test, pred, alpha=0.5, s=30)
    lims = [min(y_test.min(), pred.min()) - 1, max(y_test.max(), pred.max()) + 1]
    ax.plot(lims, lims, 'r--', linewidth=2)
    m = evaluate(y_test.values, pred)
    ax.set_xlabel('Actual')
    ax.set_ylabel('Predicted')
    ax.set_title(f'{name}\nR2={m["R2"]:.3f}, MAE={m["MAE"]:.2f}')
    ax.set_aspect('equal')
fig.suptitle('Predicted vs Actual -- Full Range (2-44)', fontsize=13)
fig.tight_layout()
save_plot(fig, '04_predicted_vs_actual_full.png')

# =====================================================================
# PLOT 5: Residual Analysis -- best full-range model (tuned CatBoost)
# =====================================================================
m_old = evaluate(y_test.values, pred_old)
m_tuned = evaluate(y_test.values, pred_tuned)
m_ridge = evaluate(y_test.values, pred_ridge)
best_pred_full = pred_tuned if m_tuned['R2'] >= m_old['R2'] and m_tuned['R2'] >= m_ridge['R2'] \
    else (pred_old if m_old['R2'] >= m_ridge['R2'] else pred_ridge)
best_name_full = 'CatBoost (tuned)' if best_pred_full is pred_tuned \
    else ('CatBoost (old config)' if best_pred_full is pred_old else 'Ridge')
residuals_full = y_test.values - best_pred_full

fig, axes = plt.subplots(1, 3, figsize=(18, 5))

ax = axes[0]
ax.scatter(best_pred_full, residuals_full, alpha=0.5, s=30)
ax.axhline(0, color='red', linestyle='--')
ax.set_xlabel('Predicted')
ax.set_ylabel('Residual (Actual - Predicted)')
ax.set_title(f'Residuals vs Predicted ({best_name_full})')

ax = axes[1]
ax.hist(residuals_full, bins=25, edgecolor='black', alpha=0.7)
ax.axvline(0, color='red', linestyle='--')
ax.set_xlabel('Residual')
ax.set_ylabel('Frequency')
ax.set_title(f'Residual Distribution (mean={residuals_full.mean():.2f})')

ax = axes[2]
ax.scatter(y_test, np.abs(residuals_full), alpha=0.5, s=30, color='orange')
ax.set_xlabel('Actual Trunk Count')
ax.set_ylabel('Absolute Error')
ax.set_title('Absolute Error vs Actual Count')

fig.suptitle('Residual Analysis -- Full Range', fontsize=13)
fig.tight_layout()
save_plot(fig, '05_residual_analysis_full.png')

# =====================================================================
# PLOT 6: Error by Trunk Count Range -- full range
# =====================================================================
fig, ax = plt.subplots(figsize=(8, 5))
error_df = pd.DataFrame({'actual': y_test.values, 'abs_error': np.abs(residuals_full)})
bin_labels = ['2-3', '4-6', '7-10', '11-20', '21+']
error_df['range'] = pd.cut(error_df['actual'], bins=[0, 3, 6, 10, 20, 100], labels=bin_labels)
error_df.boxplot(column='abs_error', by='range', ax=ax)
ax.set_xlabel('Actual Trunk Count Range')
ax.set_ylabel('Absolute Error')
plt.sca(ax)
plt.title(f'Error by Trunk Count Range ({best_name_full})')
fig.suptitle('')
fig.tight_layout()
save_plot(fig, '06_error_by_range_full.png')

# =====================================================================
# PLOT 7: Feature Importance -- Full Range (CatBoost old + tuned)
# =====================================================================
imp_old_cfg = old_cb.get_feature_importance()
imp_tuned_cfg = grid_cb.best_estimator_.get_feature_importance()

fig, ax = plt.subplots(figsize=(9, 5))
x = np.arange(len(OLD_FEATURES))
width = 0.35
bars1 = ax.barh(x - width/2, imp_old_cfg, width, label='CatBoost (old config)', color='steelblue')
bars2 = ax.barh(x + width/2, imp_tuned_cfg, width, label='CatBoost (tuned)', color='darkorange')
ax.set_yticks(x)
ax.set_yticklabels(OLD_FEATURES)
ax.set_xlabel('Feature Importance (%)')
ax.set_title('Feature Importance -- Full Range')
ax.legend()
for bar in bars1:
    ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
            f'{bar.get_width():.1f}', va='center', fontsize=9)
for bar in bars2:
    ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
            f'{bar.get_width():.1f}', va='center', fontsize=9)
fig.tight_layout()
save_plot(fig, '07_feature_importance_full.png')

# =====================================================================
# PLOT 8: Predicted vs Actual -- All 3 models, <=8 dedicated
# =====================================================================
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
for ax, pred, name in zip(axes,
    [pred8_old, pred8_tuned, pred8_ridge],
    ['CatBoost (old config)', 'CatBoost (tuned)', 'Ridge']):
    ax.scatter(y8_test, pred, alpha=0.6, s=40)
    ax.plot([1, 9], [1, 9], 'r--', linewidth=2)
    m = evaluate(y8_test.values, pred)
    ax.set_xlabel('Actual')
    ax.set_ylabel('Predicted')
    ax.set_title(f'{name}\nR2={m["R2"]:.3f}, MAE={m["MAE"]:.2f}')
    ax.set_xlim(1, 9)
    ax.set_ylim(1, 9)
    ax.set_aspect('equal')
fig.suptitle('Predicted vs Actual -- Dedicated <=8 Models', fontsize=13)
fig.tight_layout()
save_plot(fig, '08_predicted_vs_actual_le8.png')

# =====================================================================
# PLOT 9: Residual Analysis -- <=8
# =====================================================================
m8_old = evaluate(y8_test.values, pred8_old)
m8_tuned = evaluate(y8_test.values, pred8_tuned)
m8_ridge = evaluate(y8_test.values, pred8_ridge)
best_pred8 = pred8_tuned if m8_tuned['R2'] >= m8_old['R2'] and m8_tuned['R2'] >= m8_ridge['R2'] \
    else (pred8_old if m8_old['R2'] >= m8_ridge['R2'] else pred8_ridge)
best_name8 = 'CatBoost (tuned)' if best_pred8 is pred8_tuned \
    else ('CatBoost (old config)' if best_pred8 is pred8_old else 'Ridge')
residuals8 = y8_test.values - best_pred8

fig, axes = plt.subplots(1, 3, figsize=(18, 5))

ax = axes[0]
ax.scatter(best_pred8, residuals8, alpha=0.6, s=40)
ax.axhline(0, color='red', linestyle='--')
ax.set_xlabel('Predicted')
ax.set_ylabel('Residual')
ax.set_title(f'Residuals vs Predicted ({best_name8})')

ax = axes[1]
ax.hist(residuals8, bins=15, edgecolor='black', alpha=0.7)
ax.axvline(0, color='red', linestyle='--')
ax.set_xlabel('Residual')
ax.set_ylabel('Frequency')
ax.set_title(f'Residual Distribution (mean={residuals8.mean():.2f})')

ax = axes[2]
err8_df = pd.DataFrame({'actual': y8_test.values, 'abs_error': np.abs(residuals8)})
sub_labels = ['2-3', '4-5', '6-8']
err8_df['range'] = pd.cut(err8_df['actual'], bins=[1, 3, 5, 9], labels=sub_labels)
err8_df.boxplot(column='abs_error', by='range', ax=ax)
ax.set_xlabel('Actual Trunk Count Range')
ax.set_ylabel('Absolute Error')
plt.sca(ax)
plt.title(f'Error by Sub-Range ({best_name8})')

fig.suptitle('Residual Analysis -- <=8 Subset', fontsize=13)
fig.tight_layout()
save_plot(fig, '09_residual_analysis_le8.png')

# =====================================================================
# PLOT 10: Feature Importance Shift -- Full Range vs <=8
# =====================================================================
imp_full = old_cb.get_feature_importance()
imp_sub8 = old_cb8.get_feature_importance()

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

x = np.arange(len(OLD_FEATURES))
width = 0.35
axes[0].barh(x - width/2, imp_full, width, label='Full Range (2-44)', color='steelblue')
axes[0].barh(x + width/2, imp_sub8, width, label='<=8 Subset', color='teal')
axes[0].set_yticks(x)
axes[0].set_yticklabels(OLD_FEATURES)
axes[0].set_xlabel('Importance (%)')
axes[0].set_title('Feature Importance: Full Range vs <=8')
axes[0].legend()

shift = imp_sub8 - imp_full
colors = ['green' if s > 0 else 'red' for s in shift]
axes[1].barh(OLD_FEATURES, shift, color=colors)
axes[1].axvline(0, color='black', linewidth=0.5)
axes[1].set_xlabel('Importance Shift (<=8 minus Full)')
axes[1].set_title('Feature Importance Shift')
for i, (v, f) in enumerate(zip(shift, OLD_FEATURES)):
    axes[1].text(v + (0.5 if v >= 0 else -0.5), i, f'{v:+.1f}',
                 va='center', ha='left' if v >= 0 else 'right', fontsize=10)

fig.tight_layout()
save_plot(fig, '10_feature_importance_shift.png')

# =====================================================================
# PLOT 11: Model Comparison Bar Chart
# =====================================================================
models_full = ['CatBoost\n(old config)', 'CatBoost\n(tuned)', 'Ridge']
metrics_full = [m_old, m_tuned, m_ridge]
models_8 = models_full.copy()
metrics_8 = [m8_old, m8_tuned, m8_ridge]

fig, axes = plt.subplots(2, 3, figsize=(16, 10))

for col, metric, label in [(0, 'MAE', 'MAE (lower is better)'),
                            (1, 'R2', 'R-squared (higher is better)'),
                            (2, 'Within_2', 'Within +/-2 % (higher is better)')]:
    # Full range
    ax = axes[0, col]
    vals = [m[metric] for m in metrics_full]
    bars = ax.bar(models_full, vals, color=['steelblue', 'darkorange', 'green'], alpha=0.8)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f'{v:.2f}' if metric != 'Within_2' else f'{v:.1f}%',
                ha='center', va='bottom', fontsize=10)
    ax.set_title(f'Full Range -- {label}')
    ax.set_ylabel(metric)

    # <=8
    ax = axes[1, col]
    vals = [m[metric] for m in metrics_8]
    bars = ax.bar(models_8, vals, color=['steelblue', 'darkorange', 'green'], alpha=0.8)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f'{v:.2f}' if metric != 'Within_2' else f'{v:.1f}%',
                ha='center', va='bottom', fontsize=10)
    ax.set_title(f'<=8 Subset -- {label}')
    ax.set_ylabel(metric)

fig.suptitle('Old Model (5 Features) -- Model Comparison', fontsize=14)
fig.tight_layout()
save_plot(fig, '11_model_comparison.png')

# =====================================================================
# Print summary
# =====================================================================
print(f"\n{'='*60}")
print(f"All plots saved to {PLOT_DIR}/")
print(f"{'='*60}")
print(f"\nFull Range (2-44):")
print(f"  {'Model':<25s} {'MAE':>5s} {'RMSE':>6s} {'R2':>6s} {'W+/-2':>6s}")
for name, m in zip(['CB old config', 'CB tuned', 'Ridge'], [m_old, m_tuned, m_ridge]):
    print(f"  {name:<25s} {m['MAE']:>5.2f} {m['RMSE']:>6.2f} {m['R2']:>6.3f} {m['Within_2']:>5.1f}%")

print(f"\nDedicated <=8:")
print(f"  {'Model':<25s} {'MAE':>5s} {'RMSE':>6s} {'R2':>6s} {'W+/-2':>6s}")
for name, m in zip(['CB old config', 'CB tuned', 'Ridge'], [m8_old, m8_tuned, m8_ridge]):
    print(f"  {name:<25s} {m['MAE']:>5.2f} {m['RMSE']:>6.2f} {m['R2']:>6.3f} {m['Within_2']:>5.1f}%")
