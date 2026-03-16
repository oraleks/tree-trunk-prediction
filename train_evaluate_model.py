"""
Tree Trunk Count Prediction Model - Training & Evaluation Pipeline

Predicts the number of tree trunks within overlapping crown elevation polygons
based on morphological features. Evaluates model applicability with proper
train/test splits, cross-validation, and diagnostic plots.
"""

import os
import json
import warnings
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')  # Non-blocking backend; switch to 'TkAgg' for interactive use
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import spearmanr
from sklearn.model_selection import (
    train_test_split, KFold, GridSearchCV, learning_curve
)
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.inspection import permutation_importance
from sklearn.preprocessing import FunctionTransformer
from sklearn.pipeline import Pipeline
import xgboost as xgb
from catboost import CatBoostRegressor, Pool
import joblib
import shap

from feature_utils import extract_features, FEATURE_COLUMNS

warnings.filterwarnings('ignore', category=FutureWarning)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SHAPEFILE_PATH = os.path.join(os.path.dirname(__file__), 'train_set_validated.shp')
PLOTS_DIR = os.path.join(os.path.dirname(__file__), 'plots')
RANDOM_STATE = 42
TEST_SIZE = 0.2
N_FOLDS = 5
TARGET_COL = 'Point_Coun'

os.makedirs(PLOTS_DIR, exist_ok=True)


def save_and_show(fig, filename):
    """Save figure to plots/ directory and display interactively."""
    fig.savefig(os.path.join(PLOTS_DIR, filename), dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: plots/{filename}")


# ===========================================================================
# STEP 1: Data Loading & Preprocessing
# ===========================================================================
print("=" * 60)
print("STEP 1: Loading and preprocessing data")
print("=" * 60)

gdf = gpd.read_file(SHAPEFILE_PATH)
gdf = gdf.to_crs(epsg=2039)
gdf = gdf.explode(index_parts=False).reset_index(drop=True)

# Remove non-polygon geometries
gdf = gdf[gdf.geometry.type == 'Polygon'].copy()

# Remove polygons contained within other polygons (using spatial index)
sindex = gdf.sindex
to_drop = set()
for idx, row in gdf.iterrows():
    if idx in to_drop:
        continue
    candidates = list(sindex.query(row.geometry, predicate='contains'))
    for c in candidates:
        if c != idx and c not in to_drop:
            # Check if idx contains c
            if row.geometry.contains(gdf.iloc[c].geometry):
                to_drop.add(c)
gdf = gdf.drop(index=list(to_drop)).reset_index(drop=True)

print(f"Dataset: {len(gdf)} polygons after cleaning")
print(f"Target '{TARGET_COL}' stats:")
print(gdf[TARGET_COL].describe())
print()

# ===========================================================================
# STEP 2: Feature Engineering
# ===========================================================================
print("=" * 60)
print("STEP 2: Extracting morphological features")
print("=" * 60)

features_df = extract_features(gdf)
data = pd.concat([features_df, gdf[[TARGET_COL]].iloc[:len(features_df)]], axis=1)
data = data.dropna()

print(f"Features extracted: {len(FEATURE_COLUMNS)}")
print(f"Samples with valid features: {len(data)}")
print()

X = data[FEATURE_COLUMNS]
y = data[TARGET_COL]

# ===========================================================================
# STEP 3: Exploratory Data Analysis
# ===========================================================================
print("=" * 60)
print("STEP 3: Exploratory Data Analysis")
print("=" * 60)

# Target distribution
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
axes[0].hist(y, bins=25, edgecolor='black', alpha=0.7)
axes[0].set_xlabel('Tree Trunk Count')
axes[0].set_ylabel('Frequency')
axes[0].set_title('Target Distribution')
axes[0].axvline(y.mean(), color='red', linestyle='--', label=f'Mean={y.mean():.1f}')
axes[0].axvline(y.median(), color='orange', linestyle='--', label=f'Median={y.median():.1f}')
axes[0].legend()

axes[1].hist(np.log1p(y), bins=25, edgecolor='black', alpha=0.7, color='green')
axes[1].set_xlabel('log(1 + Tree Trunk Count)')
axes[1].set_ylabel('Frequency')
axes[1].set_title('Log-Transformed Target')
fig.suptitle('Target Variable Analysis', fontsize=14)
fig.tight_layout()
save_and_show(fig, '01_target_distribution.png')

# Correlation heatmap
corr = data[FEATURE_COLUMNS + [TARGET_COL]].corr()
fig, ax = plt.subplots(figsize=(14, 12))
sns.heatmap(corr, annot=True, fmt='.2f', cmap='RdBu_r', center=0,
            square=True, ax=ax, annot_kws={'size': 7})
ax.set_title('Feature Correlation Matrix')
fig.tight_layout()
save_and_show(fig, '02_correlation_heatmap.png')

# Feature-target correlations
target_corr = corr[TARGET_COL].drop(TARGET_COL).sort_values(key=abs, ascending=False)
print("Feature correlations with target:")
print(target_corr.to_string())
print()

# Top feature scatter plots
top_features = target_corr.head(6).index.tolist()
fig, axes = plt.subplots(2, 3, figsize=(15, 10))
for ax, feat in zip(axes.flat, top_features):
    ax.scatter(X[feat], y, alpha=0.4, s=15)
    ax.set_xlabel(feat)
    ax.set_ylabel('Trunk Count')
    # Add correlation text
    r = target_corr[feat]
    ax.set_title(f'{feat} (r={r:.3f})')
fig.suptitle('Top Features vs Target', fontsize=14)
fig.tight_layout()
save_and_show(fig, '03_feature_target_scatter.png')

# Highly correlated feature pairs
print("Highly correlated feature pairs (|r| > 0.9):")
for i in range(len(FEATURE_COLUMNS)):
    for j in range(i + 1, len(FEATURE_COLUMNS)):
        r = corr.iloc[i, j]
        if abs(r) > 0.9:
            print(f"  {FEATURE_COLUMNS[i]} <-> {FEATURE_COLUMNS[j]}: r={r:.3f}")
print()

# ===========================================================================
# STEP 4: Train/Test Split
# ===========================================================================
print("=" * 60)
print("STEP 4: Train/Test Split")
print("=" * 60)

# Stratified split using binned target
bins = [0, 3, 5, 8, 15, 100]
y_binned = pd.cut(y, bins=bins, labels=False)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y_binned
)
print(f"Train: {len(X_train)}, Test: {len(X_test)}")
print(f"Train target mean: {y_train.mean():.2f}, Test target mean: {y_test.mean():.2f}")
print()

# ===========================================================================
# STEP 5: Model Training & Comparison
# ===========================================================================
print("=" * 60)
print("STEP 5: Model Training & Comparison")
print("=" * 60)


def evaluate_model(y_true, y_pred, label=""):
    """Compute evaluation metrics."""
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    rho, _ = spearmanr(y_true, y_pred)
    within_1 = np.mean(np.abs(y_true - y_pred) <= 1) * 100
    within_2 = np.mean(np.abs(y_true - y_pred) <= 2) * 100
    return {
        'Model': label,
        'MAE': mae,
        'RMSE': rmse,
        'R2': r2,
        'Spearman': rho,
        'Within_1(%)': within_1,
        'Within_2(%)': within_2,
    }


# Target transforms to try
transforms = {
    'raw': (lambda y: y, lambda y: y),
    'log1p': (np.log1p, np.expm1),
    'sqrt': (np.sqrt, lambda y: y ** 2),
}

# Models
def get_models():
    return {
        'Ridge': Ridge(alpha=1.0),
        'RandomForest': RandomForestRegressor(random_state=RANDOM_STATE, n_jobs=-1),
        'XGBoost': xgb.XGBRegressor(
            random_state=RANDOM_STATE, device='cuda',
            verbosity=0, n_jobs=-1
        ),
        'CatBoost_RMSE': CatBoostRegressor(
            task_type='GPU', verbose=0, random_seed=RANDOM_STATE,
            loss_function='RMSE'
        ),
        'CatBoost_Poisson': CatBoostRegressor(
            task_type='GPU', verbose=0, random_seed=RANDOM_STATE,
            loss_function='Poisson'
        ),
    }


# Hyperparameter grids
param_grids = {
    'Ridge': {'alpha': [0.1, 1.0, 10.0, 100.0]},
    'RandomForest': {
        'n_estimators': [100, 300, 500],
        'max_depth': [3, 5, 7],
    },
    'XGBoost': {
        'n_estimators': [100, 300, 500],
        'max_depth': [3, 5, 7],
        'learning_rate': [0.01, 0.05, 0.1],
    },
    'CatBoost_RMSE': {
        'iterations': [100, 300, 500],
        'depth': [3, 5, 7],
        'learning_rate': [0.01, 0.05, 0.1],
    },
    'CatBoost_Poisson': {
        'iterations': [100, 300, 500],
        'depth': [3, 5, 7],
        'learning_rate': [0.01, 0.05, 0.1],
    },
}

cv = KFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)

results = []
best_overall_score = -np.inf
best_overall_model = None
best_overall_name = ""
best_overall_transform = ""
trained_models = {}

for transform_name, (fwd, inv) in transforms.items():
    y_train_t = fwd(y_train)

    for model_name, model in get_models().items():
        # Poisson loss doesn't work well with log/sqrt transforms (already models log-rate)
        if model_name == 'CatBoost_Poisson' and transform_name != 'raw':
            continue

        print(f"  Training {model_name} (target: {transform_name})...", end=" ", flush=True)

        try:
            grid = GridSearchCV(
                model, param_grids[model_name],
                cv=cv, scoring='neg_mean_absolute_error',
                n_jobs=1 if 'CatBoost' in model_name else -1,
                refit=True
            )
            grid.fit(X_train, y_train_t)

            y_pred_t = grid.predict(X_test)
            y_pred = inv(y_pred_t)
            y_pred = np.clip(np.round(y_pred), 1, None)  # trunk count >= 1

            metrics = evaluate_model(y_test.values, y_pred,
                                     label=f"{model_name}_{transform_name}")
            results.append(metrics)

            key = f"{model_name}_{transform_name}"
            trained_models[key] = grid.best_estimator_

            # Track overall best by R2
            if metrics['R2'] > best_overall_score:
                best_overall_score = metrics['R2']
                best_overall_model = grid.best_estimator_
                best_overall_name = key
                best_overall_transform = transform_name

            print(f"MAE={metrics['MAE']:.2f}, R2={metrics['R2']:.3f}, "
                  f"best_params={grid.best_params_}")

        except Exception as e:
            print(f"FAILED: {e}")

print()

# ===========================================================================
# STEP 6: Results Comparison
# ===========================================================================
print("=" * 60)
print("STEP 6: Results Comparison")
print("=" * 60)

results_df = pd.DataFrame(results).sort_values('R2', ascending=False)
results_df = results_df.reset_index(drop=True)
print(results_df.to_string(index=False, float_format='%.3f'))
print(f"\nBest model: {best_overall_name} (R2={best_overall_score:.3f})")
print()

# ===========================================================================
# STEP 7: Diagnostic Plots
# ===========================================================================
print("=" * 60)
print("STEP 7: Diagnostic Plots")
print("=" * 60)

# Get predictions from best model
fwd, inv = transforms[best_overall_transform]
y_pred_best = inv(best_overall_model.predict(X_test))
y_pred_best = np.clip(np.round(y_pred_best), 1, None)

# 7a. Predicted vs Actual
fig, ax = plt.subplots(figsize=(8, 8))
ax.scatter(y_test, y_pred_best, alpha=0.5, s=30)
lims = [min(y_test.min(), y_pred_best.min()) - 1,
        max(y_test.max(), y_pred_best.max()) + 1]
ax.plot(lims, lims, 'r--', linewidth=2, label='1:1 line')
ax.set_xlabel('Actual Trunk Count')
ax.set_ylabel('Predicted Trunk Count')
ax.set_title(f'Predicted vs Actual - {best_overall_name}\n'
             f'R2={best_overall_score:.3f}')
ax.legend()
ax.set_xlim(lims)
ax.set_ylim(lims)
ax.set_aspect('equal')
fig.tight_layout()
save_and_show(fig, '04_predicted_vs_actual.png')

# 7b. Residual plot
residuals = y_test.values - y_pred_best
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
axes[0].scatter(y_pred_best, residuals, alpha=0.5, s=30)
axes[0].axhline(0, color='red', linestyle='--')
axes[0].set_xlabel('Predicted')
axes[0].set_ylabel('Residual (Actual - Predicted)')
axes[0].set_title('Residuals vs Predicted')

axes[1].hist(residuals, bins=20, edgecolor='black', alpha=0.7)
axes[1].axvline(0, color='red', linestyle='--')
axes[1].set_xlabel('Residual')
axes[1].set_ylabel('Frequency')
axes[1].set_title(f'Residual Distribution (mean={residuals.mean():.2f})')
fig.suptitle(f'Residual Analysis - {best_overall_name}', fontsize=14)
fig.tight_layout()
save_and_show(fig, '05_residual_analysis.png')

# 7c. Error by trunk count range
error_df = pd.DataFrame({
    'actual': y_test.values,
    'abs_error': np.abs(residuals),
})
bin_labels = ['2-3', '4-6', '7-10', '11-20', '21+']
error_df['count_range'] = pd.cut(
    error_df['actual'], bins=[0, 3, 6, 10, 20, 100], labels=bin_labels
)

fig, ax = plt.subplots(figsize=(10, 6))
error_df.boxplot(column='abs_error', by='count_range', ax=ax)
ax.set_xlabel('Actual Trunk Count Range')
ax.set_ylabel('Absolute Error')
ax.set_title('Prediction Error by Trunk Count Range')
fig.suptitle('')
fig.tight_layout()
save_and_show(fig, '06_error_by_range.png')

# 7d. Feature importance
fig, ax = plt.subplots(figsize=(10, 8))
if hasattr(best_overall_model, 'feature_importances_'):
    importances = best_overall_model.feature_importances_
elif hasattr(best_overall_model, 'get_feature_importance'):
    importances = best_overall_model.get_feature_importance()
else:
    importances = np.zeros(len(FEATURE_COLUMNS))

feat_imp = pd.Series(importances, index=FEATURE_COLUMNS).sort_values(ascending=True)
feat_imp.plot.barh(ax=ax)
ax.set_xlabel('Importance')
ax.set_title(f'Feature Importance - {best_overall_name}')
fig.tight_layout()
save_and_show(fig, '07_feature_importance.png')

# 7e. Learning curve
print("  Computing learning curve...")
train_sizes_abs, train_scores, val_scores = learning_curve(
    best_overall_model, X_train, fwd(y_train),
    cv=cv, scoring='neg_mean_absolute_error',
    train_sizes=np.linspace(0.2, 1.0, 8),
    n_jobs=1
)
fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(train_sizes_abs, -train_scores.mean(axis=1), 'o-', label='Train MAE')
ax.fill_between(train_sizes_abs,
                -train_scores.mean(axis=1) - train_scores.std(axis=1),
                -train_scores.mean(axis=1) + train_scores.std(axis=1), alpha=0.1)
ax.plot(train_sizes_abs, -val_scores.mean(axis=1), 'o-', label='Validation MAE')
ax.fill_between(train_sizes_abs,
                -val_scores.mean(axis=1) - val_scores.std(axis=1),
                -val_scores.mean(axis=1) + val_scores.std(axis=1), alpha=0.1)
ax.set_xlabel('Training Set Size')
ax.set_ylabel('MAE')
ax.set_title('Learning Curve')
ax.legend()
ax.grid(True, alpha=0.3)
fig.tight_layout()
save_and_show(fig, '08_learning_curve.png')

# 7f. SHAP summary
print("  Computing SHAP values...")
try:
    explainer = shap.TreeExplainer(best_overall_model)
    shap_values = explainer.shap_values(X_test)
    fig, ax = plt.subplots(figsize=(10, 8))
    shap.summary_plot(shap_values, X_test, show=False)
    plt.title(f'SHAP Feature Impact - {best_overall_name}')
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, '09_shap_summary.png'), dpi=150, bbox_inches='tight')
    plt.close('all')
    print("  Saved: plots/09_shap_summary.png")
except Exception as e:
    print(f"  SHAP analysis failed: {e}")

# ===========================================================================
# STEP 8: Feature Selection Validation
# ===========================================================================
print("=" * 60)
print("STEP 8: Feature Selection Validation")
print("=" * 60)

# Permutation importance
print("  Computing permutation importance...")
perm_imp = permutation_importance(
    best_overall_model, X_test, fwd(y_test),
    n_repeats=20, random_state=RANDOM_STATE, scoring='neg_mean_absolute_error'
)
perm_df = pd.DataFrame({
    'feature': FEATURE_COLUMNS,
    'importance_mean': perm_imp.importances_mean,
    'importance_std': perm_imp.importances_std,
}).sort_values('importance_mean', ascending=False)
print("Permutation importance (test set):")
print(perm_df.to_string(index=False, float_format='%.4f'))
print()

# Compare full vs reduced feature set
top_n = 8
top_features_list = feat_imp.tail(top_n).index.tolist()
print(f"  Comparing full ({len(FEATURE_COLUMNS)} features) vs top-{top_n} features...")

reduced_model = type(best_overall_model)(**best_overall_model.get_params()) \
    if hasattr(best_overall_model, 'get_params') else Ridge()

try:
    reduced_model.fit(X_train[top_features_list], fwd(y_train))
    y_pred_reduced = inv(reduced_model.predict(X_test[top_features_list]))
    y_pred_reduced = np.clip(np.round(y_pred_reduced), 1, None)
    reduced_metrics = evaluate_model(y_test.values, y_pred_reduced, f"Reduced_top{top_n}")
    print(f"  Full model    - MAE: {results_df.iloc[0]['MAE']:.3f}, R2: {results_df.iloc[0]['R2']:.3f}")
    print(f"  Reduced model - MAE: {reduced_metrics['MAE']:.3f}, R2: {reduced_metrics['R2']:.3f}")
    print(f"  Top-{top_n} features: {top_features_list}")
except Exception as e:
    print(f"  Reduced model comparison failed: {e}")
print()

# ===========================================================================
# STEP 9: Applicability Assessment
# ===========================================================================
print("=" * 60)
print("STEP 9: Applicability Assessment")
print("=" * 60)

r2 = best_overall_score
assessment_lines = []
assessment_lines.append(f"Best Model: {best_overall_name}")
assessment_lines.append(f"R-squared: {r2:.3f}")
assessment_lines.append(f"MAE: {results_df.iloc[0]['MAE']:.2f} trees")
assessment_lines.append(f"RMSE: {results_df.iloc[0]['RMSE']:.2f} trees")
assessment_lines.append(f"Within +/-1 tree: {results_df.iloc[0]['Within_1(%)']:.1f}%")
assessment_lines.append(f"Within +/-2 trees: {results_df.iloc[0]['Within_2(%)']:.1f}%")
assessment_lines.append(f"Spearman rho: {results_df.iloc[0]['Spearman']:.3f}")
assessment_lines.append("")

if r2 < 0.3:
    assessment_lines.append("CONCLUSION: WEAK predictive power (R2 < 0.3)")
    assessment_lines.append("Morphological features alone are likely insufficient to predict trunk count.")
    assessment_lines.append("Consider adding additional data sources (e.g., spectral, LiDAR height variation).")
elif r2 < 0.6:
    assessment_lines.append("CONCLUSION: MODERATE predictive power (0.3 <= R2 < 0.6)")
    assessment_lines.append("The model provides useful rough estimates but should not be relied upon")
    assessment_lines.append("for precise individual predictions. Best suited as a screening tool.")
else:
    assessment_lines.append("CONCLUSION: STRONG predictive power (R2 >= 0.6)")
    assessment_lines.append("The morphological approach is viable for predicting trunk count.")
    assessment_lines.append("Model can be used operationally with appropriate uncertainty margins.")

assessment_lines.append("")
assessment_lines.append("Top 5 most important features:")
for i, (_, row) in enumerate(perm_df.head(5).iterrows()):
    assessment_lines.append(f"  {i+1}. {row['feature']} (importance: {row['importance_mean']:.4f})")

assessment_lines.append("")

# Learning curve interpretation
val_mae_start = -val_scores.mean(axis=1)[0]
val_mae_end = -val_scores.mean(axis=1)[-1]
train_mae_end = -train_scores.mean(axis=1)[-1]
gap = val_mae_end - train_mae_end

assessment_lines.append("Learning curve analysis:")
assessment_lines.append(f"  Validation MAE at 20% data: {val_mae_start:.2f}")
assessment_lines.append(f"  Validation MAE at 100% data: {val_mae_end:.2f}")
assessment_lines.append(f"  Train-validation gap: {gap:.2f}")
if gap > 1.0:
    assessment_lines.append("  -> Large gap suggests overfitting. More data would likely help.")
elif val_mae_end > val_mae_start * 0.9:
    assessment_lines.append("  -> Validation curve is plateauing. More data may help marginally.")
else:
    assessment_lines.append("  -> Performance is still improving with more data. Collecting more samples is recommended.")

assessment_lines.append("")
assessment_lines.append("Error breakdown by trunk count range:")
for label in bin_labels:
    subset = error_df[error_df['count_range'] == label]
    if len(subset) > 0:
        assessment_lines.append(
            f"  {label}: n={len(subset)}, mean_error={subset['abs_error'].mean():.2f}, "
            f"median_error={subset['abs_error'].median():.2f}"
        )

assessment_text = '\n'.join(assessment_lines)
print(assessment_text)
print()

# ===========================================================================
# STEP 10: Save Outputs
# ===========================================================================
print("=" * 60)
print("STEP 10: Saving outputs")
print("=" * 60)

# Save best model
model_path = os.path.join(os.path.dirname(__file__), 'best_model.joblib')
joblib.dump(best_overall_model, model_path)
print(f"  Model saved: {model_path}")

# Save feature list
features_path = os.path.join(os.path.dirname(__file__), 'model_features.json')
with open(features_path, 'w') as f:
    json.dump({
        'features': FEATURE_COLUMNS,
        'target_transform': best_overall_transform,
        'model_type': type(best_overall_model).__name__,
    }, f, indent=2)
print(f"  Feature config saved: {features_path}")

# Save evaluation report
report_path = os.path.join(os.path.dirname(__file__), 'evaluation_report.txt')
with open(report_path, 'w') as f:
    f.write("TREE TRUNK COUNT PREDICTION - EVALUATION REPORT\n")
    f.write("=" * 60 + "\n\n")
    f.write("MODEL COMPARISON\n")
    f.write("-" * 60 + "\n")
    f.write(results_df.to_string(index=False, float_format='%.3f'))
    f.write("\n\n")
    f.write("APPLICABILITY ASSESSMENT\n")
    f.write("-" * 60 + "\n")
    f.write(assessment_text)
    f.write("\n\n")
    f.write("PERMUTATION IMPORTANCE\n")
    f.write("-" * 60 + "\n")
    f.write(perm_df.to_string(index=False, float_format='%.4f'))
    f.write("\n")
print(f"  Report saved: {report_path}")
print()
print("Done! Check the plots/ directory for diagnostic visualizations.")
