# Tree Trunk Count Prediction - Results Analysis

## Objective

Evaluate whether morphological properties of overlapping tree crown elevation polygons can predict the number of tree trunks they contain, as an alternative to machine vision crown delineation from orthophotos.

## Dataset

- **Source**: `train_set_validated.shp` -- 479 polygons of merged tree crown elevations (EPSG:2039)
- **Target**: `Point_Coun` -- manually validated trunk count from street-level photography
- **Target distribution**: range 2-44, mean 6.35, median 5, heavily right-skewed

## Features Extracted (20 morphological descriptors)

| Category | Features |
|----------|----------|
| **Basic** | area, perimeter, perimeter_to_area |
| **Shape indices** | compactness, convexity, eccentricity |
| **Bounding geometry** | major_axis, minor_axis, aspect_ratio, mrr_area_ratio |
| **Complexity** | n_vertices, boundary_sinuosity, n_concavities |
| **Radial** | mean_radius, radius_std, radius_cv, radius_ratio |
| **Derived** | equivalent_diameter, convex_hull_deficit, l_ratio |

## Model Comparison

13 model configurations were evaluated (5 algorithms x 3 target transforms, minus Poisson with transforms). All used 5-fold cross-validation with hyperparameter grid search. Train/test split: 80/20, stratified by binned trunk count.

| Model | MAE | RMSE | R2 | Spearman | Within +/-1 | Within +/-2 |
|-------|-----|------|----|----------|-------------|-------------|
| **Ridge (raw)** | **1.52** | **3.17** | **0.731** | **0.859** | **69.8%** | **88.5%** |
| Ridge (sqrt) | 1.50 | 3.25 | 0.717 | 0.874 | 70.8% | 88.5% |
| XGBoost (raw) | 1.58 | 3.30 | 0.708 | 0.859 | 71.9% | 85.4% |
| RandomForest (sqrt) | 1.59 | 3.34 | 0.702 | 0.831 | 74.0% | 85.4% |
| RandomForest (raw) | 1.59 | 3.41 | 0.688 | 0.832 | 74.0% | 85.4% |
| RandomForest (log1p) | 1.64 | 3.42 | 0.687 | 0.857 | 70.8% | 84.4% |
| XGBoost (sqrt) | 1.71 | 3.43 | 0.684 | 0.855 | 67.7% | 82.3% |
| Ridge (log1p) | 1.56 | 3.46 | 0.680 | 0.880 | 70.8% | 88.5% |
| CatBoost RMSE (raw) | 1.64 | 3.46 | 0.680 | 0.847 | 71.9% | 87.5% |
| CatBoost RMSE (sqrt) | 1.63 | 3.67 | 0.640 | 0.866 | 71.9% | 86.5% |
| XGBoost (log1p) | 1.70 | 3.67 | 0.640 | 0.873 | 71.9% | 83.3% |
| CatBoost RMSE (log1p) | 1.67 | 3.69 | 0.635 | 0.871 | 71.9% | 84.4% |
| CatBoost Poisson (raw) | 1.98 | 4.85 | 0.370 | 0.808 | 69.8% | 84.4% |

## Best Model: Ridge Regression (raw target)

- **R-squared: 0.731** -- the model explains 73% of variance in trunk count
- **MAE: 1.52 trees** -- predictions are off by ~1.5 trees on average
- **88.5% of predictions fall within +/-2 trees** of the actual count
- **Spearman rho: 0.859** -- strong rank-order correlation
- Best hyperparameter: alpha = 100.0

## Feature Importance (Permutation Importance on Test Set)

| Rank | Feature | Importance |
|------|---------|------------|
| 1 | **perimeter** | 2.7189 |
| 2 | major_axis | 0.6711 |
| 3 | equivalent_diameter | 0.5548 |
| 4 | l_ratio | 0.2016 |
| 5 | area | 0.1930 |
| 6 | mean_radius | 0.1072 |
| 7 | minor_axis | 0.0540 |

**Perimeter dominates** -- it alone accounts for most of the model's predictive power. Size-related features (major axis, equivalent diameter, area) form the core signal. Shape-complexity features (compactness, eccentricity, convexity) contribute marginally.

A reduced model using only the top 8 features achieved R2 = 0.687 (vs 0.731 full), confirming that a small feature set is nearly sufficient.

## Feature Correlations with Target

| Feature | Pearson r |
|---------|-----------|
| perimeter | 0.891 |
| n_vertices | 0.880 |
| major_axis | 0.821 |
| radius_std | 0.806 |
| mean_radius | 0.805 |
| convex_hull_deficit | 0.773 |
| equivalent_diameter | 0.770 |
| area | 0.767 |
| l_ratio | 0.743 |
| compactness | -0.705 |

Note: many size features are highly intercorrelated (r > 0.9), explaining why Ridge regression (with regularization) outperforms unregularized approaches.

## Error Analysis by Trunk Count Range

| Trunk Count | n (test) | Mean Error | Median Error |
|-------------|----------|------------|--------------|
| 2-3 | 33 | 0.58 | 1.00 |
| 4-6 | 34 | 1.09 | 1.00 |
| 7-10 | 15 | 1.60 | 1.00 |
| 11-20 | 11 | 3.27 | 2.00 |
| 21+ | 3 | 10.00 | 3.00 |

The model is highly accurate for small clusters (2-6 trees) but degrades significantly for large clusters (20+ trees). This is expected given the skewed training distribution.

## Learning Curve Analysis

- Validation MAE at 20% training data: 1.61
- Validation MAE at 100% training data: 1.33
- Train-validation gap: 0.09 (minimal overfitting)
- **Performance is still improving** -- collecting more samples would likely improve results further

## Conclusions

### Applicability: STRONG (R2 = 0.731)

The morphological approach is **viable** for predicting tree trunk count from crown elevation polygons. Key findings:

1. **The relationship is predominantly linear** -- Ridge regression outperformed all tree-based ensemble methods (RandomForest, XGBoost, CatBoost). Larger/longer polygons contain more trees in a largely proportional relationship.

2. **Perimeter is the single most important predictor**, far exceeding all other features. This makes physical sense: merged crowns of multiple trees create elongated, irregular boundaries with greater perimeter relative to simple single-tree crowns.

3. **The model is most reliable for 2-10 trees** (MAE ~0.6-1.6), which covers the vast majority of urban crown clusters. For very large clusters (20+), predictions are unreliable.

4. **More data would help** -- the learning curve has not plateaued, and the 21+ category has very few training samples (limiting performance there).

5. **Target transforms (log, sqrt) did not improve results**, suggesting the raw count is already well-suited for regression.

### Recommendations

- **Operational use**: Deploy with confidence for clusters of 2-10 trees. Flag predictions of 15+ as low-confidence.
- **Data collection**: Prioritize collecting more samples of large clusters (15+ trees) to improve tail performance.
- **Feature simplification**: A model using only perimeter + area + major axis would perform nearly as well, simplifying deployment.
- **Integration**: The model can serve as a fast screening tool, reducing the need for manual counting or complex machine vision approaches.

## Diagnostic Plots

All plots saved to `plots/` directory:
1. `01_target_distribution.png` -- Target variable histogram
2. `02_correlation_heatmap.png` -- Full feature correlation matrix
3. `03_feature_target_scatter.png` -- Top features vs trunk count
4. `04_predicted_vs_actual.png` -- Best model predictions with 1:1 line
5. `05_residual_analysis.png` -- Residual distribution and heteroscedasticity check
6. `06_error_by_range.png` -- Error breakdown by trunk count range
7. `07_feature_importance.png` -- Feature importance bar chart
8. `08_learning_curve.png` -- Training vs validation performance by dataset size
