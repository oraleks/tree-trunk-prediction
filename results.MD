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

## Old Model Evaluation (5 Features)

The original model (`old_model/app.py`) uses CatBoost with only 5 features: perimeter, area, compactness, perimeter_to_area, and eccentricity. Eccentricity is derived from the minimum rotated rectangle (MRR) axis lengths, but the old code computes these incorrectly -- it takes the axis-aligned bounding box of the MRR rather than the actual side lengths, which gives wrong values for rotated rectangles. This evaluation replicates the old feature computation exactly to assess performance with those original 5 features and the buggy eccentricity.

The same evaluation methodology is used: 80/20 stratified train/test split (random_state=42), 5-fold cross-validation for hyperparameter tuning.

### Full Range (2-44 trees) -- Old Features

| Model | MAE | RMSE | R2 | Spearman | W+/-1 | W+/-2 |
|-------|-----|------|----|----------|-------|-------|
| Old CatBoost (no tuning, 5feat) | 1.50 | 3.29 | 0.709 | 0.862 | 70.8% | 86.5% |
| Old CatBoost (tuned, 5feat) | 1.49 | 3.19 | 0.728 | 0.860 | 75.0% | 86.5% |
| Old Ridge (5feat) | 1.52 | 3.14 | **0.736** | 0.865 | 72.9% | 86.5% |
| *New Ridge (20feat)* | *1.52* | *3.17* | *0.731* | *0.859* | *69.8%* | *88.5%* |
| *New CatBoost RMSE (20feat)* | *1.64* | *3.46* | *0.680* | *0.847* | *71.9%* | *87.5%* |

The old model's untuned CatBoost configuration uses default parameters with early stopping (`od_type="IncToDec"`, `od_pval=0.001`, `od_wait=100`). The tuned version searches over iterations [100, 300, 500, 1000], depth [3, 5, 7], and learning_rate [0.01, 0.05, 0.1]. Best tuned params: depth=3, iterations=100, learning_rate=0.1.

**Feature importance (CatBoost tuned, full range):**

| Feature | Importance (%) |
|---------|---------------|
| perimeter | 52.2 |
| compactness | 36.1 |
| area | 7.0 |
| eccentricity | 2.7 |
| perimeter_to_area | 1.9 |

Perimeter and compactness together account for 88% of the model's decision-making.

### Full Range on <=8 Subset -- Old Features

Performance of the full-range old models when evaluated only on test polygons with <=8 trees (n=77):

| Model | MAE | R2 | W+/-1 | W+/-2 |
|-------|-----|----|-------|-------|
| Old CatBoost (no tuning) | 0.87 | 0.478 | 81.8% | 96.1% |
| Old CatBoost (tuned) | 0.86 | 0.473 | 83.1% | 94.8% |
| Old Ridge | 0.91 | 0.508 | 83.1% | 96.1% |
| *New Ridge (20feat)* | *0.90* | *0.495* | *80.5%* | *98.7%* |

### Dedicated <=8 Models -- Old Features

Models trained and tested exclusively on polygons with 2-8 trees (304 train / 77 test):

| Model | MAE | RMSE | R2 | Spearman | W+/-1 | W+/-2 |
|-------|-----|------|----|----------|-------|-------|
| Old CatBoost (no tuning, 5feat) | 0.88 | 1.21 | 0.517 | 0.795 | 79.2% | 96.1% |
| **Old CatBoost (tuned, 5feat)** | **0.81** | **1.10** | **0.594** | **0.817** | 81.8% | 98.7% |
| Old Ridge (5feat) | 0.88 | 1.16 | 0.551 | 0.760 | 76.6% | 100% |
| *New CatBoost RMSE (20feat)* | *0.79* | *1.13* | *0.573* | *0.811* | *85.7%* | *94.8%* |
| *New Ridge (20feat)* | *0.86* | *1.16* | *0.551* | *0.791* | *83.1%* | *96.1%* |

Best tuned params for old CatBoost on <=8: depth=3, iterations=1000, learning_rate=0.01.

**Feature importance (CatBoost tuned, <=8 dedicated):**

| Feature | Importance (%) |
|---------|---------------|
| compactness | 45.8 |
| perimeter | 31.6 |
| area | 14.3 |
| eccentricity | 4.3 |
| perimeter_to_area | 4.0 |

As with the 20-feature model, compactness overtakes perimeter as the dominant feature when focusing on the <=8 range.

### Error Breakdown within 2-8 Range -- Old Features

| Model | 2-3 trees | 4-5 trees | 6-8 trees |
|-------|-----------|-----------|-----------|
| Old CatBoost (no tuning) | 0.58 | 0.96 | 1.32 |
| Old CatBoost (tuned) | 0.42 | 1.04 | 1.16 |
| Old Ridge | 0.61 | 0.96 | 1.26 |
| *New CatBoost (20feat)* | *0.48* | *0.80* | *1.32* |

### Key Findings: Old vs New Model

1. **The 15 additional features provide minimal improvement.** Ridge with 5 old features (R2=0.736) slightly *outperforms* Ridge with 20 new features (R2=0.731) on the full range. The core predictive signal is captured by perimeter, area, and compactness alone.

2. **On the <=8 range, old and new models are nearly equivalent.** Old CatBoost tuned (MAE=0.81, R2=0.594) vs new CatBoost (MAE=0.79, R2=0.573). The old model actually achieves a higher R2, while the new model has a marginally lower MAE.

3. **Hyperparameter tuning matters more than feature count.** The untuned old CatBoost (R2=0.709) improves to 0.728 with tuning -- a larger gain than adding 15 features to the tuned model.

4. **Compactness is the critical feature** that the old model gets right. It accounts for 36-46% of importance and is the only shape-complexity feature in the 5-feature set. The 15 additional features in the new model (convexity, boundary sinuosity, radial stats, etc.) largely duplicate or dilute the signal that compactness already captures.

5. **The buggy eccentricity has minimal impact.** Eccentricity accounts for only 2.7-4.3% of feature importance, so the incorrect MRR axis computation does not meaningfully affect predictions.

6. **For deployment, the 5-feature model is preferable** -- it is simpler, faster, requires no additional geometric computations beyond what GIS software provides natively (area, perimeter), and performs equivalently to the 20-feature version.

## Dataset Size Analysis: Can More Data Improve Accuracy?

To estimate whether expanding the training set would meaningfully improve predictions, learning curves were generated with 15 progressively larger training subsets (10%-100%) and extrapolated using an inverse-square-root model: `MAE = a / sqrt(n) + c`, where `c` represents the asymptotic MAE floor -- the best performance achievable with these features regardless of dataset size.

### Full Range (2-44 trees)

| Model | Current n | Current MAE | Asymptotic Floor | Gap to Floor | At n=1000 | At n=5000 |
|-------|-----------|-------------|-----------------|--------------|-----------|-----------|
| Ridge (5feat) | 306 | 1.308 | 1.289 | 1.5% | 1.302 (+0.5%) | 1.295 (+1.1%) |
| CatBoost (5feat) | 306 | 1.366 | 1.315 | 3.7% | 1.350 (+1.1%) | 1.331 (+2.6%) |

**The full-range model is near its ceiling.** Ridge is only 1.5% above its asymptotic floor -- essentially at the limit of what 5 morphological features can predict. Even multiplying the dataset 16x (to ~5000) would improve MAE by just 1.1%. CatBoost has slightly more room (3.7% gap) but the gains are still marginal: tripling the dataset to ~1000 yields only 1.1% improvement.

### Dedicated <=8 Trees

| Model | Current n | Current MAE | Asymptotic Floor | Gap to Floor | At n=1000 | At n=3000 |
|-------|-----------|-------------|-----------------|--------------|-----------|-----------|
| Ridge (5feat) | 243 | 0.852 | 0.820 | 3.8% | 0.833 (+2.3%) | 0.827 (+2.9%) |
| CatBoost (5feat) | 243 | 0.877 | 0.824 | 6.0% | 0.855 (+2.5%) | 0.842 (+4.0%) |

The <=8 model has slightly more room for improvement than the full-range model. CatBoost in particular has a 6% gap to its floor, and quadrupling to ~1000 samples would yield a 2.5% improvement. However, this translates to an absolute improvement of only ~0.02 trees in MAE -- from 0.877 to 0.855.

### Bootstrap Stability (Ridge, full range)

How much does performance vary across different random train/test splits?

| Training samples | MAE (mean +/- std) | Range |
|-----------------|---------------------|-------|
| 114 (30%) | 1.552 +/- 0.089 | 1.417 - 1.833 |
| 191 (50%) | 1.536 +/- 0.080 | 1.375 - 1.708 |
| 268 (70%) | 1.527 +/- 0.063 | 1.417 - 1.646 |
| 344 (90%) | 1.526 +/- 0.056 | 1.406 - 1.677 |
| 383 (100%) | 1.521 +/- 0.056 | 1.396 - 1.656 |

Prediction stability improves modestly with more data (std drops from 0.089 to 0.056), but the mean MAE plateaus quickly. Even using only 50% of the training data yields MAE within 1% of the full result.

### Diminishing Returns Thresholds

At what dataset size has each model captured most of its learnable signal?

| Model | 90% of potential at | 95% of potential at | Current n |
|-------|---------------------|---------------------|-----------|
| Ridge full range | ~10 | ~43 | 306 |
| CatBoost full range | ~73 | ~295 | 306 |
| Ridge <=8 | ~24 | ~98 | 243 |
| CatBoost <=8 | ~142 | ~569 | 243 |

Ridge models converge very quickly (95% of potential with <100 samples), reflecting the simplicity of the linear relationship. CatBoost requires more data to tune its nonlinear splits, but even so, the current dataset of ~300 training samples puts it at or past the 95% threshold.

### Conclusion on Dataset Size

**The current dataset of 479 polygons is essentially sufficient.** The models have captured 94-98.5% of the learnable signal from these 5 morphological features. Expanding the training set would produce marginal improvements:

- **Doubling to ~1000 polygons**: ~1-2.5% MAE improvement (practically negligible)
- **10x to ~5000 polygons**: ~1-4% MAE improvement (not worth the manual labeling effort)

**The bottleneck is not data quantity but feature expressiveness.** The asymptotic MAE floors (1.29 for full range, 0.82 for <=8) represent the inherent limit of predicting trunk count from polygon shape alone. To meaningfully improve beyond current accuracy, the path forward is not more polygons but **richer features** -- e.g., spectral information from the orthophoto, LiDAR-derived height variance within the polygon, or texture metrics.

The one exception is **rare high-count clusters (15+ trees)**, which are underrepresented in the current dataset (n=56). Targeted collection of these cases could reduce the large errors seen in the 21+ range, though this is a data *distribution* issue rather than a data *quantity* issue.

## Conclusions

### Applicability: STRONG

The morphological approach is **viable** for predicting tree trunk count from crown elevation polygons. Even a simple 5-feature model achieves R2 > 0.7 on the full range and sub-1-tree MAE on the operationally important 2-8 tree range.

### Full Range (2-44 trees)

Best models: Ridge (5feat, R2=0.736) and Ridge (20feat, R2=0.731) -- effectively equivalent.

1. **The relationship is predominantly linear** -- Ridge regression outperformed all tree-based ensemble methods across both feature sets. Larger/longer polygons contain more trees in a largely proportional relationship.

2. **Perimeter and compactness are the two critical predictors**, together accounting for 88% of CatBoost's feature importance. The remaining features contribute marginally.

3. **The model is most reliable for 2-10 trees** (MAE ~0.6-1.6), which covers the vast majority of urban crown clusters. For very large clusters (20+), predictions are unreliable.

4. **More data would help** -- the learning curve has not plateaued, and the 21+ category has very few training samples (limiting performance there).

5. **Target transforms (log, sqrt) did not improve results**, suggesting the raw count is already well-suited for regression.

### Operational Range (2-8 trees)

Best models: Old CatBoost tuned (5feat, MAE=0.81, R2=0.594) and New CatBoost (20feat, MAE=0.79, R2=0.573) -- effectively equivalent.

1. **CatBoost outperforms Ridge** on the <=8 subset with both feature sets, indicating nonlinear shape-trunk relationships that a linear model cannot fully capture at this scale.

2. **Compactness becomes the dominant feature** for small clusters (36-46% importance), replacing perimeter. This makes physical sense: polygons covering 2-8 trees of similar overall size differ more in shape irregularity than in raw perimeter.

3. **Predictions are off by less than 1 tree on average** (MAE ~0.8), with ~82-86% of predictions exact or within +/-1 tree.

4. **Sub-tree accuracy for the smallest clusters**: polygons with 2-3 trees have a mean error of only 0.42-0.58.

### Recommendations

- **Use the 5-feature model.** It matches the 20-feature version in performance while being simpler and faster. The features (perimeter, area, compactness, perimeter_to_area, eccentricity) are straightforward to compute in any GIS environment.
- **For general use (2-44 trees)**: Deploy Ridge regression. Simple, fast, and best overall R2.
- **For operational use (2-8 trees)**: Deploy CatBoost RMSE with tuned hyperparameters for better accuracy on the most common cluster sizes.
- **Confidence thresholds**: High confidence for 2-5 trees (error <1), moderate for 6-8 (error ~1.3), low confidence for 9+.
- **Data collection**: Prioritize collecting more samples of large clusters (15+ trees) to improve tail performance.
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
