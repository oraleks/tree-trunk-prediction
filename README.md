# Tree Trunk Prediction from Crown Polygon Morphology

Predicting the number of tree trunks within overlapping urban tree crown elevation polygons using morphological features -- an alternative to machine vision crown delineation from orthophotos.

## Approach

When tree crowns overlap, standard image segmentation methods struggle to delineate individual crowns. This project tests a different hypothesis: **the shape of a merged crown polygon encodes information about how many trees it contains**. Larger, more elongated, more complex polygons tend to represent more trees.

We extract 20 morphological features from each polygon (area, perimeter, compactness, eccentricity, boundary complexity, radial statistics, etc.) and train regression models to predict trunk count.

## Results

| Metric | Best Model (Ridge Regression) |
|--------|-------------------------------|
| R-squared | **0.731** |
| MAE | 1.52 trees |
| Within +/-2 trees | 88.5% |
| Spearman rho | 0.859 |

The approach is **viable** -- morphological features explain 73% of the variance in trunk count. The model is most accurate for clusters of 2-10 trees (MAE ~0.6-1.6), which covers the vast majority of urban crown clusters.

**Top predictive features**: perimeter, major axis length, equivalent diameter, area.

See [results.MD](results.MD) for the full analysis.

## Dataset

- 479 manually validated polygons of merged tree crown elevations (EPSG:2039, Israel)
- Trunk counts (2-44) verified from street-level photography
- Stored as `train_set_validated.shp`

## Usage

### Install dependencies

```bash
pip install geopandas shapely scikit-learn xgboost catboost matplotlib seaborn shap
```

### Run the training and evaluation pipeline

```bash
python train_evaluate_model.py
```

This will:
1. Load the shapefile and extract 20 morphological features
2. Train and compare 5 model types with 3 target transforms (13 configurations)
3. Evaluate on a held-out 20% test set
4. Generate diagnostic plots in `plots/`
5. Save the best model to `best_model.joblib`
6. Write a full evaluation report to `evaluation_report.txt`

### Use features on new data

```python
import geopandas as gpd
from feature_utils import extract_features

gdf = gpd.read_file('your_crowns.shp').to_crs(epsg=2039)
features = extract_features(gdf)
```

## Jupyter Notebooks

The full workflow is available as interactive notebooks:

| Notebook | Description |
|----------|-------------|
| [01_feature_extraction.ipynb](01_feature_extraction.ipynb) | Load shapefile, extract 5- and 20-feature sets, EDA, correlation analysis |
| [02_model_training.ipynb](02_model_training.ipynb) | Train Ridge/RF/XGBoost/CatBoost, cross-validation, diagnostic plots, save models |
| [03_predict_new_data.ipynb](03_predict_new_data.ipynb) | Apply trained model to a new unseen shapefile, visualize and save predictions |
| [04_old_model_evaluation.ipynb](04_old_model_evaluation.ipynb) | Evaluate the original 5-feature CatBoost model with rigorous methodology |

## Project Structure

```
01_feature_extraction.ipynb   # Notebook: feature extraction and EDA
02_model_training.ipynb       # Notebook: model training and evaluation
03_predict_new_data.ipynb     # Notebook: predict on new data
04_old_model_evaluation.ipynb # Notebook: old model evaluation
train_evaluate_model.py       # Standalone pipeline script (20-feature model)
plot_old_model.py             # Old model evaluation + plot generation
feature_utils.py              # Morphological feature extraction module
eval_old_model.py             # Old model evaluation script
dataset_size_analysis.py      # Learning curve extrapolation analysis
train_set_validated.shp       # Training dataset (+ .dbf, .shx, .prj, .cpg)
results.MD                    # Detailed results analysis
evaluation_report.txt         # Model comparison metrics
model_features.json           # Feature list and model config
plots/                        # Diagnostic plots (20-feature model)
plots_old_model/              # Diagnostic plots (old 5-feature model)
old_model/                    # Previous CatBoost-based implementation
```

## Key Findings

1. **Ridge regression outperformed** all tree-based ensembles (Random Forest, XGBoost, CatBoost) on the full range, indicating the relationship is largely linear.
2. **5 features match 20 features** in performance -- the simpler model is recommended for deployment.
3. **Perimeter is the single most important predictor** for the full range; **compactness** overtakes it for the ≤8 subset.
4. **CatBoost outperforms Ridge on ≤8 trees** -- nonlinear shape relationships matter more for small clusters.
5. **Current dataset (479) is sufficient** -- models have captured 94-98.5% of their potential; the bottleneck is feature expressiveness, not data quantity.
6. **Error scales with cluster size** -- reliable for 2-10 trees (MAE ~0.6-1.6), less so for 20+.
