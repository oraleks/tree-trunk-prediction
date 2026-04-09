# CatBoost 3-Feature Model Evaluation Report

## Model Configuration

- **Algorithm**: CatBoost (gradient boosting, RMSE loss)
- **Features**: area, compactness, perimeter
- **Best hyperparameters**: depth=3, iterations=300, learning_rate=0.05
- **GPU accelerated**: Yes (task_type='GPU')
- **Dataset**: 479 polygons (EPSG:2039), 80/20 stratified split

## Features

| Feature | Description | Spearman rho with target |
|---------|-------------|-------------------------|
| perimeter | Polygon boundary length (m) | 0.857 |
| area | Polygon area (m^2) | 0.730 |
| compactness | 4*pi*area/perimeter^2 (circularity) | -0.835 |

Feature inter-correlations:
- perimeter-area: r = 0.938
- perimeter-compactness: r = -0.699
- area-compactness: r = -0.516

## Full Range Results (2-44 trees)

| Metric | Value |
|--------|-------|
| MAE | 1.594 |
| RMSE | 3.283 |
| R-squared | 0.711 |
| Spearman rho | 0.835 |
| Within +/-1 | 69.8% |
| Within +/-2 | 83.3% |

### Feature Importance (Full Range)

| Feature | CatBoost Native (%) | Permutation Importance |
|---------|--------------------|-----------------------|
| compactness     | 41.6% | -1.079 |
| perimeter       | 37.5% | -0.926 |
| area            | 20.9% | -0.303 |

### Error by Trunk Count Range

| Range | n | MAE | Within +/-1 | Within +/-2 |
|-------|---|-----|-------------|-------------|
| 2-3 | 33 | 0.55 | 97% | 97% |
| 4-6 | 34 | 1.21 | 71% | 91% |
| 7-10 | 15 | 1.67 | 47% | 73% |
| 11-20 | 11 | 3.36 | 36% | 55% |
| 21+ | 3 | 10.67 | 0% | 0% |

## Full-Range Model on <=8 Subset

| Metric | Value |
|--------|-------|
| MAE | 0.948 |
| RMSE | 1.334 |
| R-squared | 0.409 |
| Within +/-1 | 80.5% |
| Within +/-2 | 93.5% |

## Dedicated <=8 Model

- **Best hyperparameters**: depth=3, iterations=100, learning_rate=0.1
- **Train/Test**: 304/77 (from 381 polygons with <=8 trees)

| Metric | Value |
|--------|-------|
| MAE | 0.909 |
| RMSE | 1.184 |
| R-squared | 0.534 |
| Within +/-1 | 80.5% |
| Within +/-2 | 97.4% |

### Feature Importance (<=8 Dedicated)

| Feature | Importance (%) |
|---------|---------------|
| compactness     | 48.6% |
| perimeter       | 29.4% |
| area            | 22.0% |

### Error by Sub-Range (<=8 Dedicated)

| Range | n | MAE | Within +/-1 |
|-------|---|-----|-------------|
| 2-3 | 33 | 0.58 | 97% |
| 4-5 | 25 | 1.04 | 84% |
| 6-8 | 19 | 1.32 | 47% |

## Model Stability

### 10-Fold Cross-Validation (full dataset)

- MAE: 1.409 +/- 0.189
- Range: [1.206, 1.834]

### Bootstrap Analysis (50 random 80/20 splits)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| MAE | 1.449 | 0.152 | 1.125 | 1.823 |
| R2 | 0.792 | 0.061 | 0.659 | 0.898 |

## Comparison with Previous Models

### Full Range (2-44)

| Model | MAE | RMSE | R2 | W+/-1 | W+/-2 |
|-------|-----|------|----|-------|-------|
| Ridge (20feat) | 1.52 | 3.17 | 0.731 | 69.8% | 88.5% |
| Ridge (5feat) | 1.52 | 3.14 | 0.736 | 72.9% | 86.5% |
| CatBoost tuned (5feat) | 1.49 | 3.19 | 0.728 | 75.0% | 86.5% |
| **CatBoost (3feat)** | **1.59** | **3.28** | **0.711** | **69.8%** | **83.3%** |

### Dedicated <=8

| Model | MAE | R2 | W+/-1 | W+/-2 |
|-------|-----|----|-------|-------|
| CatBoost tuned (5feat) | 0.81 | 0.594 | 81.8% | 98.7% |
| CatBoost (20feat) | 0.79 | 0.573 | 85.7% | 94.8% |
| **CatBoost (3feat)** | **0.91** | **0.534** | **80.5%** | **97.4%** |

## Diagnostic Plots

All plots saved to `plots_3feat_catboost/`:

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
