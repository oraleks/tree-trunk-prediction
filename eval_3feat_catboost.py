"""
Comprehensive evaluation of CatBoost with 3 features: area, compactness, perimeter.
Produces a full report with metrics, plots, and comparison to previous models.
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
from sklearn.model_selection import (
    train_test_split, KFold, GridSearchCV, learning_curve, cross_val_score
)
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.inspection import permutation_importance
from catboost import CatBoostRegressor

warnings.filterwarnings('ignore')

RANDOM_STATE = 42
TARGET = 'Point_Coun'
FEATURES = ['area', 'compactness', 'perimeter']
PLOT_DIR = 'plots_3feat_catboost'
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
# Load and prepare data
# =====================================================================
print("=" * 70)
print("CatBoost 3-Feature Model Evaluation")
print(f"Features: {FEATURES}")
print("=" * 70)

gdf = gpd.read_file('train_set_validated.shp').to_crs(epsg=2039)
gdf = gdf.explode(index_parts=False).reset_index(drop=True)
gdf = gdf[gdf.geometry.type == 'Polygon'].copy()

# Remove contained polygons
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
gdf = gdf.drop(index=list(to_drop)).reset_index(drop=True)

# Compute features
gdf['perimeter'] = gdf.geometry.length
gdf['area'] = gdf.geometry.area
gdf['compactness'] = (4 * math.pi * gdf['area']) / (gdf['perimeter'] ** 2)

data = gdf[FEATURES + [TARGET]].dropna()
X = data[FEATURES]
y = data[TARGET]

print(f"\nDataset: {len(data)} polygons")
print(f"Target range: {y.min()} - {y.max()}, mean: {y.mean():.2f}, median: {y.median():.0f}")
print(f"Target distribution:")
for lo, hi, lb in [(2, 3, '2-3'), (4, 6, '4-6'), (7, 10, '7-10'), (11, 20, '11-20'), (21, 100, '21+')]:
    n = ((y >= lo) & (y <= hi)).sum()
    print(f"  {lb}: {n} ({n/len(y)*100:.1f}%)")

# =====================================================================
# Feature overview
# =====================================================================
print(f"\nFeature statistics:")
print(X.describe().round(3).to_string())

print(f"\nFeature-target correlations:")
for feat in FEATURES:
    r_pear = X[feat].corr(y)
    r_spear, _ = spearmanr(X[feat], y)
    print(f"  {feat:<15s}  Pearson={r_pear:.3f}  Spearman={r_spear:.3f}")

# =====================================================================
# Train/Test Split
# =====================================================================
bins = [0, 3, 5, 8, 15, 100]
y_binned = pd.cut(y, bins=bins, labels=False)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y_binned
)
print(f"\nTrain: {len(X_train)}, Test: {len(X_test)}")
print(f"Train mean: {y_train.mean():.2f}, Test mean: {y_test.mean():.2f}")

cv = KFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

# =====================================================================
# Hyperparameter tuning
# =====================================================================
print("\n" + "=" * 70)
print("HYPERPARAMETER TUNING (5-fold CV)")
print("=" * 70)

param_grid = {
    'iterations': [100, 300, 500, 1000],
    'depth': [3, 5, 7],
    'learning_rate': [0.01, 0.05, 0.1],
}
n_combos = 4 * 3 * 3
print(f"Grid: {n_combos} combinations x 5 folds = {n_combos * 5} fits")

grid = GridSearchCV(
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE, loss_function='RMSE'),
    param_grid, cv=cv, scoring='neg_mean_absolute_error', refit=True, n_jobs=1,
    return_train_score=True
)
grid.fit(X_train, y_train)

print(f"\nBest parameters: {grid.best_params_}")
print(f"Best CV MAE: {-grid.best_score_:.3f}")

# Show top 10 configurations
cv_results = pd.DataFrame(grid.cv_results_)
cv_results['mean_test_MAE'] = -cv_results['mean_test_score']
cv_results['std_test_MAE'] = cv_results['std_test_score']
top10 = cv_results.nsmallest(10, 'mean_test_MAE')[
    ['param_depth', 'param_iterations', 'param_learning_rate', 'mean_test_MAE', 'std_test_MAE']
]
print(f"\nTop 10 hyperparameter configurations:")
print(top10.to_string(index=False))

best_model = grid.best_estimator_

# =====================================================================
# Test set evaluation -- FULL RANGE
# =====================================================================
print("\n" + "=" * 70)
print("TEST SET EVALUATION -- FULL RANGE (2-44)")
print("=" * 70)

y_pred = np.clip(np.round(best_model.predict(X_test)), 1, None)
m_full = evaluate(y_test.values, y_pred)
residuals = y_test.values - y_pred

print(f"\n  MAE:          {m_full['MAE']:.3f}")
print(f"  RMSE:         {m_full['RMSE']:.3f}")
print(f"  R-squared:    {m_full['R2']:.3f}")
print(f"  Spearman rho: {m_full['Spearman']:.3f}")
print(f"  Within +/-1:  {m_full['Within_1']:.1f}%")
print(f"  Within +/-2:  {m_full['Within_2']:.1f}%")

# Error by range
print(f"\n  Error by trunk count range:")
error_data = pd.DataFrame({'actual': y_test.values, 'predicted': y_pred, 'abs_error': np.abs(residuals)})
for lo, hi, lb in [(2, 3, '2-3'), (4, 6, '4-6'), (7, 10, '7-10'), (11, 20, '11-20'), (21, 100, '21+')]:
    mk = (error_data['actual'] >= lo) & (error_data['actual'] <= hi)
    if mk.sum() > 0:
        sub = error_data[mk]
        print(f"    {lb:<6s}: n={mk.sum():>2d}, MAE={sub['abs_error'].mean():.2f}, "
              f"median_err={sub['abs_error'].median():.1f}, "
              f"W+/-1={np.mean(sub['abs_error'] <= 1)*100:.0f}%, "
              f"W+/-2={np.mean(sub['abs_error'] <= 2)*100:.0f}%")

# Feature importance
feat_imp = best_model.get_feature_importance()
print(f"\n  Feature importance (CatBoost native):")
for feat, imp in sorted(zip(FEATURES, feat_imp), key=lambda x: -x[1]):
    print(f"    {feat:<15s}: {imp:.1f}%")

# Permutation importance
perm_imp = permutation_importance(best_model, X_test, y_test, n_repeats=20,
                                   random_state=RANDOM_STATE, scoring='neg_mean_absolute_error')
print(f"\n  Permutation importance (test set, 20 repeats):")
for feat, imp, std in sorted(zip(FEATURES, perm_imp.importances_mean, perm_imp.importances_std),
                              key=lambda x: -x[1]):
    print(f"    {feat:<15s}: {-imp:.3f} +/- {std:.3f}")

# =====================================================================
# Test set evaluation -- <=8 SUBSET (from full-range model)
# =====================================================================
print("\n" + "=" * 70)
print("FULL-RANGE MODEL ON <=8 TEST SUBSET")
print("=" * 70)

mask8 = y_test <= 8
y_test8 = y_test[mask8].values
y_pred8 = y_pred[mask8]
m_sub8 = evaluate(y_test8, y_pred8)

print(f"\n  Subset size: {mask8.sum()} of {len(y_test)} test samples")
print(f"  MAE:          {m_sub8['MAE']:.3f}")
print(f"  RMSE:         {m_sub8['RMSE']:.3f}")
print(f"  R-squared:    {m_sub8['R2']:.3f}")
print(f"  Spearman rho: {m_sub8['Spearman']:.3f}")
print(f"  Within +/-1:  {m_sub8['Within_1']:.1f}%")
print(f"  Within +/-2:  {m_sub8['Within_2']:.1f}%")

# =====================================================================
# Dedicated <=8 model
# =====================================================================
print("\n" + "=" * 70)
print("DEDICATED <=8 MODEL")
print("=" * 70)

data8 = data[data[TARGET] <= 8]
X8, y8 = data8[FEATURES], data8[TARGET]
y8_binned = pd.cut(y8, bins=[0, 3, 5, 9], labels=False)
X8_train, X8_test, y8_train, y8_test = train_test_split(
    X8, y8, test_size=0.2, random_state=RANDOM_STATE, stratify=y8_binned
)
print(f"  Train: {len(X8_train)}, Test: {len(X8_test)}")

grid8 = GridSearchCV(
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE, loss_function='RMSE'),
    param_grid, cv=cv, scoring='neg_mean_absolute_error', refit=True, n_jobs=1,
)
grid8.fit(X8_train, y8_train)
best_model8 = grid8.best_estimator_

y8_pred = np.clip(np.round(best_model8.predict(X8_test)), 1, None)
m_ded8 = evaluate(y8_test.values, y8_pred)
residuals8 = y8_test.values - y8_pred

print(f"  Best params: {grid8.best_params_}")
print(f"  Best CV MAE: {-grid8.best_score_:.3f}")
print(f"\n  MAE:          {m_ded8['MAE']:.3f}")
print(f"  RMSE:         {m_ded8['RMSE']:.3f}")
print(f"  R-squared:    {m_ded8['R2']:.3f}")
print(f"  Spearman rho: {m_ded8['Spearman']:.3f}")
print(f"  Within +/-1:  {m_ded8['Within_1']:.1f}%")
print(f"  Within +/-2:  {m_ded8['Within_2']:.1f}%")

print(f"\n  Error by sub-range (<=8 dedicated model):")
for lo, hi, lb in [(2, 3, '2-3'), (4, 5, '4-5'), (6, 8, '6-8')]:
    mk = (y8_test.values >= lo) & (y8_test.values <= hi)
    if mk.sum() > 0:
        err = np.abs(y8_test.values[mk] - y8_pred[mk])
        print(f"    {lb}: n={mk.sum()}, MAE={err.mean():.2f}, "
              f"W+/-1={np.mean(err <= 1)*100:.0f}%")

feat_imp8 = best_model8.get_feature_importance()
print(f"\n  Feature importance (<=8 dedicated):")
for feat, imp in sorted(zip(FEATURES, feat_imp8), key=lambda x: -x[1]):
    print(f"    {feat:<15s}: {imp:.1f}%")

# =====================================================================
# Cross-validation stability analysis
# =====================================================================
print("\n" + "=" * 70)
print("CROSS-VALIDATION STABILITY")
print("=" * 70)

# Run 10-fold CV with best params on full data
cv10 = KFold(n_splits=10, shuffle=True, random_state=RANDOM_STATE)
cv_scores = cross_val_score(
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE,
                      **grid.best_params_),
    X, y, cv=cv10, scoring='neg_mean_absolute_error'
)
cv_mae = -cv_scores
print(f"\n  10-fold CV MAE: {cv_mae.mean():.3f} +/- {cv_mae.std():.3f}")
print(f"  Range: [{cv_mae.min():.3f}, {cv_mae.max():.3f}]")
print(f"  Per-fold: {', '.join(f'{v:.3f}' for v in cv_mae)}")

# Bootstrap stability
print(f"\n  Bootstrap stability (50 random 80/20 splits):")
bootstrap_mae = []
bootstrap_r2 = []
for seed in range(50):
    Xb_tr, Xb_te, yb_tr, yb_te = train_test_split(X, y, test_size=0.2, random_state=seed)
    m = CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE,
                          **grid.best_params_)
    m.fit(Xb_tr, yb_tr)
    pred_b = np.clip(np.round(m.predict(Xb_te)), 1, None)
    bootstrap_mae.append(mean_absolute_error(yb_te.values, pred_b))
    bootstrap_r2.append(r2_score(yb_te.values, pred_b))
bootstrap_mae = np.array(bootstrap_mae)
bootstrap_r2 = np.array(bootstrap_r2)
print(f"  MAE: {bootstrap_mae.mean():.3f} +/- {bootstrap_mae.std():.3f} "
      f"[{bootstrap_mae.min():.3f}, {bootstrap_mae.max():.3f}]")
print(f"  R2:  {bootstrap_r2.mean():.3f} +/- {bootstrap_r2.std():.3f} "
      f"[{bootstrap_r2.min():.3f}, {bootstrap_r2.max():.3f}]")

# =====================================================================
# PLOTS
# =====================================================================
print("\n" + "=" * 70)
print("GENERATING PLOTS")
print("=" * 70)

# PLOT 1: Feature-target scatter with regression lines
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
for i, feat in enumerate(FEATURES):
    ax = axes[i]
    ax.scatter(data[feat], data[TARGET], alpha=0.4, s=15)
    # Add trend line
    z = np.polyfit(data[feat], data[TARGET], 1)
    xline = np.linspace(data[feat].min(), data[feat].max(), 100)
    ax.plot(xline, np.polyval(z, xline), 'r-', linewidth=2, alpha=0.7)
    r_spear, _ = spearmanr(data[feat], data[TARGET])
    ax.set_xlabel(feat, fontsize=12)
    ax.set_ylabel('Trunk Count' if i == 0 else '', fontsize=12)
    ax.set_title(f'Spearman rho = {r_spear:.3f}', fontsize=11)
fig.suptitle('Feature vs Trunk Count (3-Feature Set)', fontsize=14)
fig.tight_layout()
save_plot(fig, '01_feature_target_scatter.png')

# PLOT 2: Feature correlation heatmap (small but informative)
fig, ax = plt.subplots(figsize=(6, 5))
corr = data[FEATURES + [TARGET]].corr()
sns.heatmap(corr, annot=True, fmt='.3f', cmap='coolwarm', center=0, ax=ax,
            square=True, linewidths=0.5)
ax.set_title('Correlation Matrix (3 Features + Target)')
fig.tight_layout()
save_plot(fig, '02_correlation_heatmap.png')

# PLOT 3: Predicted vs Actual -- full range
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

ax = axes[0]
ax.scatter(y_test, y_pred, alpha=0.5, s=40)
lims = [min(y_test.min(), y_pred.min()) - 1, max(y_test.max(), y_pred.max()) + 1]
ax.plot(lims, lims, 'r--', linewidth=2, label='1:1 line')
ax.fill_between([lims[0], lims[1]], [lims[0]-2, lims[1]-2], [lims[0]+2, lims[1]+2],
                alpha=0.1, color='green', label='+/-2 band')
ax.set_xlabel('Actual Trunk Count', fontsize=12)
ax.set_ylabel('Predicted Trunk Count', fontsize=12)
ax.set_title(f'Full Range: R2={m_full["R2"]:.3f}, MAE={m_full["MAE"]:.2f}')
ax.legend()
ax.set_aspect('equal')

ax = axes[1]
# Zoomed view for <=8
mask = y_test <= 8
ax.scatter(y_test[mask], y_pred[mask], alpha=0.6, s=50)
ax.plot([1, 9], [1, 9], 'r--', linewidth=2, label='1:1 line')
ax.fill_between([1, 9], [-1, 7], [3, 11], alpha=0.1, color='green', label='+/-2 band')
ax.set_xlabel('Actual Trunk Count', fontsize=12)
ax.set_ylabel('Predicted Trunk Count', fontsize=12)
ax.set_title(f'<=8 Subset: R2={m_sub8["R2"]:.3f}, MAE={m_sub8["MAE"]:.2f}')
ax.set_xlim(1, 9)
ax.set_ylim(0, 10)
ax.legend()
ax.set_aspect('equal')

fig.suptitle('CatBoost 3-Feature: Predicted vs Actual', fontsize=14)
fig.tight_layout()
save_plot(fig, '03_predicted_vs_actual.png')

# PLOT 4: Residual analysis
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

ax = axes[0]
ax.scatter(y_pred, residuals, alpha=0.5, s=30)
ax.axhline(0, color='red', linestyle='--')
ax.set_xlabel('Predicted')
ax.set_ylabel('Residual (Actual - Predicted)')
ax.set_title('Residuals vs Predicted')

ax = axes[1]
ax.hist(residuals, bins=25, edgecolor='black', alpha=0.7)
ax.axvline(0, color='red', linestyle='--')
ax.axvline(residuals.mean(), color='blue', linestyle='--', label=f'Mean={residuals.mean():.2f}')
ax.set_xlabel('Residual')
ax.set_ylabel('Frequency')
ax.set_title('Residual Distribution')
ax.legend()

ax = axes[2]
ax.scatter(y_test, np.abs(residuals), alpha=0.5, s=30, color='orange')
z = np.polyfit(y_test, np.abs(residuals), 1)
xline = np.linspace(y_test.min(), y_test.max(), 100)
ax.plot(xline, np.polyval(z, xline), 'r-', linewidth=2, alpha=0.7)
ax.set_xlabel('Actual Trunk Count')
ax.set_ylabel('Absolute Error')
ax.set_title('Error Growth with Count')

fig.suptitle('Residual Analysis -- Full Range', fontsize=14)
fig.tight_layout()
save_plot(fig, '04_residual_analysis.png')

# PLOT 5: Error by trunk count range (boxplot)
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

ax = axes[0]
error_df = pd.DataFrame({'actual': y_test.values, 'abs_error': np.abs(residuals)})
bin_labels = ['2-3', '4-6', '7-10', '11-20', '21+']
error_df['range'] = pd.cut(error_df['actual'], bins=[0, 3, 6, 10, 20, 100], labels=bin_labels)
error_df.boxplot(column='abs_error', by='range', ax=ax)
ax.set_xlabel('Actual Trunk Count Range')
ax.set_ylabel('Absolute Error')
plt.sca(ax)
plt.title('Full Range')

ax = axes[1]
err8_df = pd.DataFrame({'actual': y8_test.values, 'abs_error': np.abs(residuals8)})
sub_labels = ['2-3', '4-5', '6-8']
err8_df['range'] = pd.cut(err8_df['actual'], bins=[1, 3, 5, 9], labels=sub_labels)
err8_df.boxplot(column='abs_error', by='range', ax=ax)
ax.set_xlabel('Actual Trunk Count Range')
ax.set_ylabel('Absolute Error')
plt.sca(ax)
plt.title('Dedicated <=8 Model')

fig.suptitle('Error by Trunk Count Range', fontsize=13)
fig.tight_layout()
save_plot(fig, '05_error_by_range.png')

# PLOT 6: Feature importance comparison (full range vs <=8)
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

ax = axes[0]
sorted_idx = np.argsort(feat_imp)
ax.barh(np.array(FEATURES)[sorted_idx], feat_imp[sorted_idx], color='steelblue')
for i, (v, f) in enumerate(zip(feat_imp[sorted_idx], np.array(FEATURES)[sorted_idx])):
    ax.text(v + 0.5, i, f'{v:.1f}%', va='center')
ax.set_xlabel('Importance (%)')
ax.set_title('Full Range (2-44)')

ax = axes[1]
sorted_idx8 = np.argsort(feat_imp8)
ax.barh(np.array(FEATURES)[sorted_idx8], feat_imp8[sorted_idx8], color='teal')
for i, (v, f) in enumerate(zip(feat_imp8[sorted_idx8], np.array(FEATURES)[sorted_idx8])):
    ax.text(v + 0.5, i, f'{v:.1f}%', va='center')
ax.set_xlabel('Importance (%)')
ax.set_title('Dedicated <=8')

fig.suptitle('Feature Importance: Full Range vs <=8', fontsize=14)
fig.tight_layout()
save_plot(fig, '06_feature_importance.png')

# PLOT 7: Learning curve
fig, ax = plt.subplots(figsize=(10, 6))
train_sizes, train_scores, val_scores = learning_curve(
    CatBoostRegressor(task_type='GPU', verbose=0, random_seed=RANDOM_STATE,
                      **grid.best_params_),
    X_train, y_train, cv=cv,
    train_sizes=np.linspace(0.2, 1.0, 10),
    scoring='neg_mean_absolute_error', n_jobs=1
)
train_mae = -train_scores.mean(axis=1)
val_mae = -val_scores.mean(axis=1)
train_std = train_scores.std(axis=1)
val_std = val_scores.std(axis=1)

ax.plot(train_sizes, train_mae, 'o-', color='blue', label='Training MAE')
ax.fill_between(train_sizes, train_mae - train_std, train_mae + train_std, alpha=0.1, color='blue')
ax.plot(train_sizes, val_mae, 'o-', color='red', label='Validation MAE')
ax.fill_between(train_sizes, val_mae - val_std, val_mae + val_std, alpha=0.1, color='red')
ax.set_xlabel('Training Set Size')
ax.set_ylabel('MAE')
ax.set_title('Learning Curve -- CatBoost 3-Feature')
ax.legend()
ax.grid(True, alpha=0.3)
fig.tight_layout()
save_plot(fig, '07_learning_curve.png')

# PLOT 8: Bootstrap stability distribution
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

ax = axes[0]
ax.hist(bootstrap_mae, bins=20, edgecolor='black', alpha=0.7)
ax.axvline(bootstrap_mae.mean(), color='red', linestyle='--',
           label=f'Mean={bootstrap_mae.mean():.3f}')
ax.axvline(m_full['MAE'], color='blue', linestyle='--',
           label=f'This split={m_full["MAE"]:.3f}')
ax.set_xlabel('MAE')
ax.set_ylabel('Count')
ax.set_title('Bootstrap MAE Distribution (50 splits)')
ax.legend()

ax = axes[1]
ax.hist(bootstrap_r2, bins=20, edgecolor='black', alpha=0.7, color='green')
ax.axvline(bootstrap_r2.mean(), color='red', linestyle='--',
           label=f'Mean={bootstrap_r2.mean():.3f}')
ax.axvline(m_full['R2'], color='blue', linestyle='--',
           label=f'This split={m_full["R2"]:.3f}')
ax.set_xlabel('R-squared')
ax.set_ylabel('Count')
ax.set_title('Bootstrap R2 Distribution (50 splits)')
ax.legend()

fig.suptitle('Model Stability Across Random Splits', fontsize=14)
fig.tight_layout()
save_plot(fig, '08_bootstrap_stability.png')

# PLOT 9: Predicted vs Actual for <=8 dedicated model
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

ax = axes[0]
ax.scatter(y8_test, y8_pred, alpha=0.6, s=50)
ax.plot([1, 9], [1, 9], 'r--', linewidth=2, label='1:1 line')
ax.set_xlabel('Actual')
ax.set_ylabel('Predicted')
ax.set_title(f'Dedicated <=8: R2={m_ded8["R2"]:.3f}, MAE={m_ded8["MAE"]:.2f}')
ax.set_xlim(1, 9)
ax.set_ylim(1, 9)
ax.set_aspect('equal')
ax.legend()

ax = axes[1]
ax.scatter(y8_pred, residuals8, alpha=0.6, s=50, color='green')
ax.axhline(0, color='red', linestyle='--')
ax.set_xlabel('Predicted')
ax.set_ylabel('Residual')
ax.set_title(f'Residuals (mean={residuals8.mean():.2f})')

fig.suptitle('Dedicated <=8 Model Performance', fontsize=14)
fig.tight_layout()
save_plot(fig, '09_dedicated_le8.png')

# PLOT 10: Comparison with previous models
fig, axes = plt.subplots(1, 3, figsize=(18, 6))

# Data for comparison (from results.MD)
models = ['Ridge\n20feat', 'Ridge\n5feat', 'CatBoost\n5feat', 'CatBoost\n3feat\n(this)']
mae_full = [1.52, 1.52, 1.49, m_full['MAE']]
r2_full = [0.731, 0.736, 0.728, m_full['R2']]
w2_full = [88.5, 86.5, 86.5, m_full['Within_2']]

colors = ['gray', 'gray', 'gray', 'steelblue']

ax = axes[0]
bars = ax.bar(models, mae_full, color=colors, edgecolor='black', alpha=0.8)
for bar, v in zip(bars, mae_full):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
            f'{v:.2f}', ha='center', va='bottom', fontsize=11, fontweight='bold')
ax.set_ylabel('MAE')
ax.set_title('MAE (lower = better)')
ax.set_ylim(0, max(mae_full) * 1.2)

ax = axes[1]
bars = ax.bar(models, r2_full, color=colors, edgecolor='black', alpha=0.8)
for bar, v in zip(bars, r2_full):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
            f'{v:.3f}', ha='center', va='bottom', fontsize=11, fontweight='bold')
ax.set_ylabel('R-squared')
ax.set_title('R-squared (higher = better)')
ax.set_ylim(0, 1)

ax = axes[2]
bars = ax.bar(models, w2_full, color=colors, edgecolor='black', alpha=0.8)
for bar, v in zip(bars, w2_full):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
            f'{v:.1f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')
ax.set_ylabel('Within +/-2 (%)')
ax.set_title('Within +/-2 (higher = better)')
ax.set_ylim(0, 105)

fig.suptitle('Full Range: CatBoost 3-Feature vs Previous Models', fontsize=14)
fig.tight_layout()
save_plot(fig, '10_model_comparison.png')

# =====================================================================
# Write report
# =====================================================================
print("\n" + "=" * 70)
print("WRITING EVALUATION REPORT")
print("=" * 70)

report = f"""# CatBoost 3-Feature Model Evaluation Report

## Model Configuration

- **Algorithm**: CatBoost (gradient boosting, RMSE loss)
- **Features**: area, compactness, perimeter
- **Best hyperparameters**: depth={grid.best_params_['depth']}, iterations={grid.best_params_['iterations']}, learning_rate={grid.best_params_['learning_rate']}
- **GPU accelerated**: Yes (task_type='GPU')
- **Dataset**: {len(data)} polygons (EPSG:2039), 80/20 stratified split

## Features

| Feature | Description | Spearman rho with target |
|---------|-------------|-------------------------|
| perimeter | Polygon boundary length (m) | {spearmanr(X['perimeter'], y)[0]:.3f} |
| area | Polygon area (m^2) | {spearmanr(X['area'], y)[0]:.3f} |
| compactness | 4*pi*area/perimeter^2 (circularity) | {spearmanr(X['compactness'], y)[0]:.3f} |

Feature inter-correlations:
- perimeter-area: r = {X['perimeter'].corr(X['area']):.3f}
- perimeter-compactness: r = {X['perimeter'].corr(X['compactness']):.3f}
- area-compactness: r = {X['area'].corr(X['compactness']):.3f}

## Full Range Results (2-44 trees)

| Metric | Value |
|--------|-------|
| MAE | {m_full['MAE']:.3f} |
| RMSE | {m_full['RMSE']:.3f} |
| R-squared | {m_full['R2']:.3f} |
| Spearman rho | {m_full['Spearman']:.3f} |
| Within +/-1 | {m_full['Within_1']:.1f}% |
| Within +/-2 | {m_full['Within_2']:.1f}% |

### Feature Importance (Full Range)

| Feature | CatBoost Native (%) | Permutation Importance |
|---------|--------------------|-----------------------|
| {FEATURES[np.argsort(feat_imp)[::-1][0]]:<15s} | {feat_imp[np.argsort(feat_imp)[::-1][0]]:.1f}% | {-perm_imp.importances_mean[np.argsort(feat_imp)[::-1][0]]:.3f} |
| {FEATURES[np.argsort(feat_imp)[::-1][1]]:<15s} | {feat_imp[np.argsort(feat_imp)[::-1][1]]:.1f}% | {-perm_imp.importances_mean[np.argsort(feat_imp)[::-1][1]]:.3f} |
| {FEATURES[np.argsort(feat_imp)[::-1][2]]:<15s} | {feat_imp[np.argsort(feat_imp)[::-1][2]]:.1f}% | {-perm_imp.importances_mean[np.argsort(feat_imp)[::-1][2]]:.3f} |

### Error by Trunk Count Range

| Range | n | MAE | Within +/-1 | Within +/-2 |
|-------|---|-----|-------------|-------------|"""

for lo, hi, lb in [(2, 3, '2-3'), (4, 6, '4-6'), (7, 10, '7-10'), (11, 20, '11-20'), (21, 100, '21+')]:
    mk = (error_data['actual'] >= lo) & (error_data['actual'] <= hi)
    if mk.sum() > 0:
        sub = error_data[mk]
        w1 = np.mean(sub['abs_error'] <= 1) * 100
        w2 = np.mean(sub['abs_error'] <= 2) * 100
        report += f"\n| {lb} | {mk.sum()} | {sub['abs_error'].mean():.2f} | {w1:.0f}% | {w2:.0f}% |"

report += f"""

## Full-Range Model on <=8 Subset

| Metric | Value |
|--------|-------|
| MAE | {m_sub8['MAE']:.3f} |
| RMSE | {m_sub8['RMSE']:.3f} |
| R-squared | {m_sub8['R2']:.3f} |
| Within +/-1 | {m_sub8['Within_1']:.1f}% |
| Within +/-2 | {m_sub8['Within_2']:.1f}% |

## Dedicated <=8 Model

- **Best hyperparameters**: depth={grid8.best_params_['depth']}, iterations={grid8.best_params_['iterations']}, learning_rate={grid8.best_params_['learning_rate']}
- **Train/Test**: {len(X8_train)}/{len(X8_test)} (from {len(data8)} polygons with <=8 trees)

| Metric | Value |
|--------|-------|
| MAE | {m_ded8['MAE']:.3f} |
| RMSE | {m_ded8['RMSE']:.3f} |
| R-squared | {m_ded8['R2']:.3f} |
| Within +/-1 | {m_ded8['Within_1']:.1f}% |
| Within +/-2 | {m_ded8['Within_2']:.1f}% |

### Feature Importance (<=8 Dedicated)

| Feature | Importance (%) |
|---------|---------------|
| {FEATURES[np.argsort(feat_imp8)[::-1][0]]:<15s} | {feat_imp8[np.argsort(feat_imp8)[::-1][0]]:.1f}% |
| {FEATURES[np.argsort(feat_imp8)[::-1][1]]:<15s} | {feat_imp8[np.argsort(feat_imp8)[::-1][1]]:.1f}% |
| {FEATURES[np.argsort(feat_imp8)[::-1][2]]:<15s} | {feat_imp8[np.argsort(feat_imp8)[::-1][2]]:.1f}% |

### Error by Sub-Range (<=8 Dedicated)

| Range | n | MAE | Within +/-1 |
|-------|---|-----|-------------|"""

for lo, hi, lb in [(2, 3, '2-3'), (4, 5, '4-5'), (6, 8, '6-8')]:
    mk = (y8_test.values >= lo) & (y8_test.values <= hi)
    if mk.sum() > 0:
        err = np.abs(y8_test.values[mk] - y8_pred[mk])
        w1 = np.mean(err <= 1) * 100
        report += f"\n| {lb} | {mk.sum()} | {err.mean():.2f} | {w1:.0f}% |"

report += f"""

## Model Stability

### 10-Fold Cross-Validation (full dataset)

- MAE: {cv_mae.mean():.3f} +/- {cv_mae.std():.3f}
- Range: [{cv_mae.min():.3f}, {cv_mae.max():.3f}]

### Bootstrap Analysis (50 random 80/20 splits)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| MAE | {bootstrap_mae.mean():.3f} | {bootstrap_mae.std():.3f} | {bootstrap_mae.min():.3f} | {bootstrap_mae.max():.3f} |
| R2 | {bootstrap_r2.mean():.3f} | {bootstrap_r2.std():.3f} | {bootstrap_r2.min():.3f} | {bootstrap_r2.max():.3f} |

## Comparison with Previous Models

### Full Range (2-44)

| Model | MAE | RMSE | R2 | W+/-1 | W+/-2 |
|-------|-----|------|----|-------|-------|
| Ridge (20feat) | 1.52 | 3.17 | 0.731 | 69.8% | 88.5% |
| Ridge (5feat) | 1.52 | 3.14 | 0.736 | 72.9% | 86.5% |
| CatBoost tuned (5feat) | 1.49 | 3.19 | 0.728 | 75.0% | 86.5% |
| **CatBoost (3feat)** | **{m_full['MAE']:.2f}** | **{m_full['RMSE']:.2f}** | **{m_full['R2']:.3f}** | **{m_full['Within_1']:.1f}%** | **{m_full['Within_2']:.1f}%** |

### Dedicated <=8

| Model | MAE | R2 | W+/-1 | W+/-2 |
|-------|-----|----|-------|-------|
| CatBoost tuned (5feat) | 0.81 | 0.594 | 81.8% | 98.7% |
| CatBoost (20feat) | 0.79 | 0.573 | 85.7% | 94.8% |
| **CatBoost (3feat)** | **{m_ded8['MAE']:.2f}** | **{m_ded8['R2']:.3f}** | **{m_ded8['Within_1']:.1f}%** | **{m_ded8['Within_2']:.1f}%** |

## Diagnostic Plots

All plots saved to `{PLOT_DIR}/`:

1. `01_feature_target_scatter.png` -- Each feature vs trunk count with trend lines
2. `02_correlation_heatmap.png` -- 3-feature + target correlation matrix
3. `03_predicted_vs_actual.png` -- Predictions with 1:1 line (full range + <=8 zoom)
4. `04_residual_analysis.png` -- Residuals, distribution, error growth
5. `05_error_by_range.png` -- Error boxplots by count range
6. `06_feature_importance.png` -- Feature importance: full range vs <=8
7. `07_learning_curve.png` -- Training vs validation MAE by dataset size
8. `08_bootstrap_stability.png` -- MAE and R2 distributions across 50 random splits
9. `09_dedicated_le8.png` -- Predicted vs actual and residuals for <=8 model
10. `10_model_comparison.png` -- Bar chart comparison with previous models
"""

report_path = 'evaluation_report_3feat_catboost.md'
with open(report_path, 'w') as f:
    f.write(report)
print(f"  Saved {report_path}")

print("\n" + "=" * 70)
print("EVALUATION COMPLETE")
print("=" * 70)
print(f"\nPlots: {PLOT_DIR}/")
print(f"Report: {report_path}")
