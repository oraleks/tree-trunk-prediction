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

## Evaluation Methodology

### Data Preparation

1. **Loading**: The shapefile is read with GeoPandas and reprojected to EPSG:2039 (Israel Transverse Mercator, units in meters). Multi-part geometries are exploded into individual polygons. Polygons fully contained within other polygons are removed using a spatial index to avoid double-counting.

2. **Feature extraction**: 20 morphological features are computed from each polygon's geometry (see table above). All features are derived purely from polygon shape -- no spatial location features are used, to avoid data leakage from spatial autocorrelation. A key fix over the old model: minimum rotated rectangle (MRR) axis lengths are computed from actual Euclidean distances between consecutive MRR vertices, rather than the axis-aligned bounding box of the MRR (which gives incorrect values for rotated rectangles).

### Train/Test Split

The 479 polygons are split 80/20 into training (383) and test (96) sets. Because the target is heavily right-skewed (median 5, max 44), a **stratified split** is used: `Point_Coun` is binned into 5 groups (2-3, 4-5, 6-8, 9-15, 16+), and `sklearn.model_selection.train_test_split` samples proportionally from each bin. This ensures the test set contains representative samples across the full count range. A fixed `random_state=42` ensures reproducibility.

The test set is held out throughout the entire model selection process and used only for final evaluation -- it is never seen during training or hyperparameter tuning.

### Cross-Validation and Hyperparameter Tuning

Each model is tuned using **5-fold cross-validation** on the training set only (`sklearn.model_selection.KFold`, `shuffle=True`, `random_state=42`). The training set (383 samples) is split into 5 folds of ~77 samples each. For each hyperparameter combination, the model is trained on 4 folds and evaluated on the held-out fold, repeated 5 times. The combination with the best mean negative MAE across folds is selected.

Hyperparameter tuning is performed via `sklearn.model_selection.GridSearchCV` with the following grids:

| Model | Hyperparameters Searched |
|-------|-------------------------|
| Ridge | alpha: [0.1, 1.0, 10.0, 100.0] |
| RandomForest | n_estimators: [100, 300, 500], max_depth: [3, 5, 7] |
| XGBoost | n_estimators: [100, 300, 500], max_depth: [3, 5, 7], learning_rate: [0.01, 0.05, 0.1] |
| CatBoost RMSE | iterations: [100, 300, 500], depth: [3, 5, 7], learning_rate: [0.01, 0.05, 0.1] |
| CatBoost Poisson | iterations: [100, 300, 500], depth: [3, 5, 7], learning_rate: [0.01, 0.05, 0.1] |

After the best hyperparameters are selected via CV, the model is refit on the entire training set with those parameters (`refit=True` in GridSearchCV).

### Target Transforms

Each model (except CatBoost Poisson, which inherently models log-rate) is tested with three target transforms:

- **raw**: predict `Point_Coun` directly
- **log1p**: train on `log(1 + Point_Coun)`, inverse-transform predictions with `exp(pred) - 1`
- **sqrt**: train on `sqrt(Point_Coun)`, inverse-transform with `pred^2`

This yields 13 total configurations (5 models x 3 transforms - 2 Poisson transforms).

### Final Evaluation

Each tuned model predicts on the held-out test set (96 samples). Predictions are rounded to the nearest integer and clipped to a minimum of 1 (trunk count cannot be zero). The following metrics are computed by comparing predictions to actual `Point_Coun` values:

| Metric | Formula | Interpretation |
|--------|---------|----------------|
| **MAE** | mean(\|actual - predicted\|) | Average absolute error in tree count |
| **RMSE** | sqrt(mean((actual - predicted)^2)) | Penalizes large errors more than MAE |
| **R-squared** | 1 - SS_res / SS_tot | Proportion of variance explained (0-1) |
| **Spearman rho** | Rank correlation between actual and predicted | Does the model rank polygons correctly? |
| **Within +/-1** | % of \|actual - predicted\| <= 1 | Practical accuracy: how often is the prediction exact or off by 1 |
| **Within +/-2** | % of \|actual - predicted\| <= 2 | Practical accuracy with wider tolerance |

### <=8 Subset Evaluation

For the focused 2-8 tree analysis, two approaches were tested:

1. **Full-range model, subset evaluation**: The model trained on all 383 training samples is evaluated only on the test polygons with `Point_Coun <= 8` (77 of 96 test samples). This tests how a general model performs on the operational range.

2. **Dedicated <=8 model**: Only polygons with `Point_Coun <= 8` (381 total) are used. These are split 80/20 (304 train / 77 test) with stratification by bins [2-3, 4-5, 6-8]. Models are tuned and evaluated independently on this subset. This tests whether a specialized model outperforms the general one.

### Feature Importance

Two methods are used:

1. **Model-native importance** (CatBoost/tree models): Built-in feature importance scores based on how frequently and effectively each feature is used in splits.

2. **Permutation importance** (`sklearn.inspection.permutation_importance`): For each feature, its values in the test set are randomly shuffled 20 times, and the increase in MAE is measured. This is model-agnostic and measures each feature's true contribution to test-set performance.

### Learning Curve

`sklearn.model_selection.learning_curve` is used to train the best model on progressively larger subsets of the training data (20%, 30%, ... 100%) and measure 5-fold CV performance at each size. This reveals whether performance is plateauing (more data won't help) or still improving (collect more samples).

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

## Focus Analysis: Polygons with 2-8 Trees

Polygons with up to 8 trees represent 80% of the dataset (381 of 479 polygons) and are the most operationally relevant range for urban tree inventory. This section evaluates model performance specifically for this subset.

### Dataset Composition

| Subset | Count | Percentage | Mean Trunk Count |
|--------|-------|------------|------------------|
| 2-8 trees | 381 | 79.5% | 4.27 |
| 9+ trees | 98 | 20.5% | 14.42 |

### Full-Range Models Evaluated on <=8 Subset

How do models trained on the full 2-44 range perform when evaluated only on the <=8 test polygons?

| Model | MAE | R2 | Within +/-1 | Within +/-2 |
|-------|-----|----|-------------|-------------|
| Ridge | 0.90 | 0.495 | 80.5% | 98.7% |
| CatBoost RMSE | 0.99 | 0.396 | 81.8% | 96.1% |
| CatBoost Poisson | 0.99 | 0.404 | 79.2% | 94.8% |

### Dedicated <=8 Models (trained and tested only on 2-8 trees)

| Model | MAE | RMSE | R2 | Spearman | Within +/-1 | Within +/-2 |
|-------|-----|------|----|----------|-------------|-------------|
| **CatBoost RMSE** | **0.79** | **1.13** | **0.573** | **0.811** | **85.7%** | 94.8% |
| Ridge | 0.86 | 1.16 | 0.551 | 0.791 | 83.1% | 96.1% |
| CatBoost Poisson | 0.86 | 1.28 | 0.456 | 0.751 | 84.4% | 92.2% |

**CatBoost RMSE is the best model for the <=8 range** (MAE=0.79, 85.7% within +/-1 tree), overtaking Ridge which wins on the full range. Best hyperparameters: depth=5, iterations=100, learning_rate=0.05.

### Error Breakdown within 2-8 Range (CatBoost RMSE)

| Trunk Count | n (test) | Mean Error |
|-------------|----------|------------|
| 2-3 | 33 | 0.48 |
| 4-5 | 25 | 0.80 |
| 6-8 | 19 | 1.32 |

### Why R2 Drops but Practical Performance Improves

The R2 drops from 0.731 (full range) to 0.573 (<=8 subset) despite better absolute accuracy. This is not a contradiction -- R2 measures proportion of variance explained. When restricting to 2-8 trees, the target variance shrinks dramatically (std ~1.8 vs ~5.2 for the full range). The model explains less of this narrower variance, even though its absolute errors are much smaller. **For practical purposes, MAE and within-N accuracy are the right metrics here.**

### Feature Importance Shifts for <=8 Models

CatBoost's feature importance reveals a significant shift when focusing on the <=8 range:

| Rank | Full Range (2-44) | <=8 Dedicated Model |
|------|-------------------|---------------------|
| 1 | perimeter (22.0) | **compactness (14.2)** |
| 2 | compactness (19.1) | **convex_hull_deficit (13.0)** |
| 3 | convex_hull_deficit (16.1) | radius_std (8.6) |
| 4 | radius_std (10.8) | perimeter (7.9) |
| 5 | n_vertices (8.2) | mean_radius (7.8) |

**On the full range, perimeter dominates** -- more trees simply means a bigger polygon. But **for 2-8 trees, shape complexity features (compactness, convex hull deficit) surpass pure size**. This makes physical sense: a 2-tree polygon and a 6-tree polygon of similar overall size will differ more in shape irregularity (lobing, concavities, deviation from circular) than in raw perimeter. The model learns to "read" the shape's complexity as a signal for how many crowns are merged together.

## Conclusions

### Applicability: STRONG

The morphological approach is **viable** for predicting tree trunk count from crown elevation polygons.

### Full Range (2-44 trees): Ridge Regression (R2 = 0.731)

1. **The relationship is predominantly linear** -- Ridge regression outperformed all tree-based ensemble methods (RandomForest, XGBoost, CatBoost). Larger/longer polygons contain more trees in a largely proportional relationship.

2. **Perimeter is the single most important predictor**, far exceeding all other features. This makes physical sense: merged crowns of multiple trees create elongated, irregular boundaries with greater perimeter relative to simple single-tree crowns.

3. **The model is most reliable for 2-10 trees** (MAE ~0.6-1.6), which covers the vast majority of urban crown clusters. For very large clusters (20+), predictions are unreliable.

4. **More data would help** -- the learning curve has not plateaued, and the 21+ category has very few training samples (limiting performance there).

5. **Target transforms (log, sqrt) did not improve results**, suggesting the raw count is already well-suited for regression.

### Operational Range (2-8 trees): CatBoost RMSE (R2 = 0.573, MAE = 0.79)

1. **CatBoost outperforms Ridge** on the <=8 subset, indicating nonlinear shape-trunk relationships that a linear model cannot fully capture at this scale.

2. **Shape complexity matters more than size** for distinguishing small clusters. Compactness and convex hull deficit become the top predictors, replacing perimeter.

3. **Predictions are off by less than 1 tree on average** (MAE = 0.79), with 85.7% of predictions exact or within +/-1 tree.

4. **Sub-tree accuracy for the smallest clusters**: polygons with 2-3 trees have a mean error of only 0.48.

### Recommendations

- **For general use (2-44 trees)**: Deploy Ridge regression. Simple, fast, and best overall R2.
- **For operational use (2-8 trees)**: Deploy CatBoost RMSE for better accuracy on the most common cluster sizes.
- **Confidence thresholds**: High confidence for 2-5 trees (error <1), moderate for 6-8 (error ~1.3), low confidence for 9+.
- **Data collection**: Prioritize collecting more samples of large clusters (15+ trees) to improve tail performance.
- **Feature simplification**: For the full-range model, perimeter + area + major axis is nearly sufficient. For the <=8 model, retain shape complexity features (compactness, convex hull deficit).
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
