# Tree Trunk Count Prediction from Crown Polygon Morphology

## Context

Crown delineation from orthophotos struggles with overlapping canopies. The hypothesis is that morphological properties of merged crown elevation polygons (area, elongation, complexity, etc.) correlate with the number of tree trunks beneath them. We have 479 manually-validated polygons (`train_set_validated.shp`) with trunk counts (range 2-44, median 5). The existing code in `old_model/` uses CatBoost but has no proper evaluation -- it trains on all labeled data and predicts unlabeled polygons. We need a rigorous assessment of whether this approach works.

**Installed packages**: geopandas, shapely, scikit-learn, xgboost, catboost, matplotlib, seaborn, shap, numpy, pandas, joblib.

## Files

| File | Purpose |
|------|---------|
| `feature_utils.py` | Reusable 20-feature extraction from polygon geometries |
| `train_evaluate_model.py` | Main pipeline: load data, engineer features, train/evaluate models, produce plots |
| `eval_old_model.py` | Old model (5-feature) evaluation script |
| `plot_old_model.py` | Old model evaluation with diagnostic plots → `plots_old_model/` |
| `dataset_size_analysis.py` | Learning curve extrapolation and dataset size analysis |
| `01_feature_extraction.ipynb` | Notebook: feature extraction (5 and 20 features) + EDA |
| `02_model_training.ipynb` | Notebook: model training, CV, evaluation, save models |
| `03_predict_new_data.ipynb` | Notebook: apply trained model to new shapefile |
| `04_old_model_evaluation.ipynb` | Notebook: old 5-feature model training and evaluation |
| `05_generate_tree_points.ipynb` | Notebook: generate estimated tree trunk point locations |
| `tree_point_generator.py` | Tree point placement module (constrained k-means / CVT approximation) |

## Step 1 -- Feature Engineering (`feature_utils.py`)

Create `extract_features(gdf) -> pd.DataFrame` that computes ~20 morphological features:

**Basic**: area, perimeter, perimeter_to_area
**Shape indices**: compactness (`4*pi*area/perimeter^2`), convexity (`area/convex_hull_area`), eccentricity
**Bounding geometry**: major/minor axis from MRR (fix old code's bug -- compute actual side lengths from MRR vertices, not axis-aligned bbox of MRR), aspect_ratio, mrr_area_ratio
**Complexity**: n_vertices, boundary_sinuosity (`perimeter/convex_hull_perimeter`), n_concavities (components of `hull.difference(polygon)`)
**Radial**: mean_radius, radius_std, radius_cv (from centroid to boundary vertices)
**Derived**: equivalent_diameter, convex_hull_deficit, l_ratio (from old code)

Reuse logic from `old_model/funcs.py` for eccentricity and l_ratio, but fix MRR axis computation.

## Step 3 -- Data Loading and Preprocessing (`train_evaluate_model.py`)

- Read shapefile, ensure EPSG:2039, explode multiparts
- Remove contained polygons (use spatial index, not O(n^2) loop)
- Extract features using `feature_utils.extract_features()`
- Print dataset summary and target distribution

## Step 4 -- Exploratory Data Analysis

- Target distribution histogram (with log-scale overlay)
- Feature correlation heatmap
- Top feature-target scatter plots
- Identify highly correlated feature pairs (r > 0.9)

## Step 5 -- Model Training and Comparison

**Split**: 80/20 stratified by binned Point_Coun (quantile bins), `random_state=42`

**Models**:
1. Ridge Regression (linear baseline)
2. Random Forest
3. XGBoost
4. CatBoost (RMSE loss)
5. CatBoost (Poisson loss -- appropriate for count data)

**Cross-validation**: 5-fold on training set with light hyperparameter grid:
- `n_estimators/iterations`: [100, 300, 500]
- `max_depth`: [3, 5, 7]
- `learning_rate` (boosted): [0.01, 0.05, 0.1]

**Target transforms**: Compare raw vs log1p vs sqrt transforms (inverse-transform predictions for evaluation).

## Step 6 -- Evaluation Metrics

On held-out test set:
- MAE, RMSE, R-squared
- Within-1 and within-2 accuracy (% of predictions within +/-1 or +/-2 of actual)
- Spearman rank correlation

Print comparison table across all models.

## Step 7 -- Diagnostic Plots

1. Predicted vs Actual scatter (with 1:1 line) for best model
2. Residual plot (residuals vs predicted)
3. Error by trunk count range (boxplot, bins: 2-3, 4-6, 7-10, 11-20, 21+)
4. Feature importance bar chart (from best tree model)
5. Learning curve (training vs validation score vs dataset size)
6. SHAP summary plot for best model

## Step 8 -- Feature Selection Validation

- Compare full feature set vs top-8 features
- Permutation importance on test set
- Report if reduced set performs comparably (guards against overfitting with ~20 features on 479 samples)

## Step 9 -- Applicability Assessment

Print a synthesis:
- R^2 < 0.3: weak, morphology alone insufficient
- R^2 0.3-0.6: moderate, useful as rough estimate
- R^2 > 0.6: viable approach
- Learning curve interpretation (would more data help?)
- Error breakdown by count range
- Top features and their physical meaning

## Step 10 -- Save Outputs

- Best model to `best_model.joblib`
- Feature list to `model_features.json`
- New model plots to `plots/` directory
- Old model plots to `plots_old_model/` directory
- Summary report to `evaluation_report.txt`
- Use GPU acceleration for CatBoost/XGBoost (`task_type="GPU"` / `device="cuda"`)

## Step 11 -- Old Model Evaluation (`plot_old_model.py`, `04_old_model_evaluation.ipynb`)

Evaluate the original 5-feature CatBoost model from `old_model/app.py` using the same rigorous methodology:
- Replicate exact old feature computation (including buggy MRR axis-aligned bbox)
- Train CatBoost (old config), CatBoost (tuned), Ridge on full range and <=8 subset
- Generate 11 diagnostic plots in `plots_old_model/`
- Compare feature importance shift between full range and <=8 subset

## Verification

1. Run `python train_evaluate_model.py` -- should complete without errors
2. Check `plots/` directory for all diagnostic plots
3. Check `evaluation_report.txt` for metrics and applicability assessment
4. Verify model file `best_model.joblib` exists
5. Test that feature extraction works on the original shapefile

## Key Technical Notes

- **MRR axis bug fix**: Old code computes axis-aligned bbox of the rotated rectangle instead of actual MRR side lengths. Fix by computing Euclidean distances between consecutive MRR vertices.
- **No spatial features**: Location is excluded to avoid spatial leakage.
- **No deep learning**: 479 samples with ~20 features is ideal for tree-based ensembles.
- **Stratified split**: Essential due to heavily right-skewed target.
