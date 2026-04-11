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
pip install geopandas shapely scikit-learn xgboost catboost matplotlib seaborn shap scipy
```

Each notebook also includes a `%pip install` cell at the top for its specific dependencies.

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

### Batch feature extraction for multiple shapefiles

```bash
# Single file
python batch_extract_features.py TLV_tree_canopies_2022.shp

# Entire folder
python batch_extract_features.py path/to/shapefiles/
```

Input naming: `XXX_tree_canopies_YYYY.shp` -> Output: `XXX_tree_canopies_YYYY_processed.shp`

Automatically repairs invalid geometries (via `make_valid` + `buffer(0)`), strips Z coordinates, explodes MultiPolygons, removes tiny/contained polygons, then extracts 20 morphological features.

### Batch prediction pipeline

The full end-to-end pipeline for processing city-wide tree crown data:

```bash
# Step 1: Extract features and repair geometries
python batch_extract_features.py path/to/shapefiles/
# XXX_tree_canopies_YYYY.shp -> XXX_tree_canopies_YYYY_processed.shp

# Step 2: Predict tree count per polygon
python batch_predict_trees.py path/to/shapefiles/
# XXX_tree_canopies_YYYY_processed.shp -> XXX_tree_canopies_YYYY_predicted.shp

# Step 3: Generate tree trunk point locations
python batch_generate_points.py path/to/shapefiles/
# XXX_tree_canopies_YYYY_predicted.shp -> XXX_tree_trunks_YYYY.shp
```

Prediction uses a two-step approach:
1. **Single-tree filter**: polygons with area < 150 m² and compactness > 0.6 are assigned 1 tree
2. **Ridge regression** (5 features) predicts trunk count for remaining polygons

Each tree point carries `crown_area` (polygon area / N trees) and `crown_diam` (equivalent diameter).

### Urban forest quality analysis

```bash
python urban_forest_analysis.py [data_dir]
```

Analyzes crown diameter distributions across all cities, produces 10 diagnostic plots in `plots_urban_forest/` and a comprehensive report (`urban_forest_report.md`). Computes a composite quality score ranking cities by median crown diameter, large tree fraction, crown diversity, and tree count.

### Generate estimated tree locations (programmatic)

```python
from tree_point_generator import generate_tree_points_gdf

# gdf must have a column with trunk counts (known or predicted)
points_gdf = generate_tree_points_gdf(gdf, count_column='Point_Coun')
points_gdf.to_file('tree_locations.shp')
```

## Jupyter Notebooks

The full workflow is available as interactive notebooks:

| Notebook | Description |
|----------|-------------|
| [01_feature_extraction.ipynb](01_feature_extraction.ipynb) | Load shapefile, extract 5- and 20-feature sets, EDA, correlation analysis |
| [02_model_training.ipynb](02_model_training.ipynb) | Train Ridge/RF/XGBoost/CatBoost, cross-validation, diagnostic plots, save models |
| [03_predict_new_data.ipynb](03_predict_new_data.ipynb) | Apply trained model to a new unseen shapefile, visualize and save predictions |
| [04_old_model_evaluation.ipynb](04_old_model_evaluation.ipynb) | Evaluate the original 5-feature CatBoost model with rigorous methodology |
| [05_generate_tree_points.ipynb](05_generate_tree_points.ipynb) | Generate estimated tree trunk locations within crown polygons |

## Project Structure

```
01_feature_extraction.ipynb   # Notebook: feature extraction and EDA
02_model_training.ipynb       # Notebook: model training and evaluation
03_predict_new_data.ipynb     # Notebook: predict on new data
04_old_model_evaluation.ipynb # Notebook: old model evaluation
05_generate_tree_points.ipynb # Notebook: generate tree trunk point locations
train_evaluate_model.py       # Standalone pipeline script (20-feature model)
plot_old_model.py             # Old model evaluation + plot generation
eval_3feat_catboost.py        # CatBoost 3-feature evaluation + report + plots
batch_extract_features.py     # Batch feature extraction with geometry repair
batch_predict_trees.py        # Batch tree count prediction (Ridge + single-tree filter)
batch_generate_points.py      # Batch tree trunk point generation with crown metrics
urban_forest_analysis.py      # Urban forest quality analysis (39 cities, 10 plots)
feature_utils.py              # Morphological feature extraction module
tree_point_generator.py       # Tree point placement using constrained k-means
eval_old_model.py             # Old model evaluation script
dataset_size_analysis.py      # Learning curve extrapolation analysis
benchmark_training.py         # Computational cost comparison
train_set_validated.shp       # Training dataset (+ .dbf, .shx, .prj, .cpg)
results.MD                    # Detailed results analysis (also results.docx)
evaluation_report.txt         # Model comparison metrics
evaluation_report_3feat_catboost.md  # 3-feature CatBoost report (also .docx)
model_features.json           # Feature list and model config
plots/                        # Diagnostic plots (20-feature model)
plots_old_model/              # Diagnostic plots (old 5-feature model)
plots_3feat_catboost/         # Diagnostic plots (3-feature CatBoost)
plots_urban_forest/           # Urban forest quality analysis plots (10)
urban_forest_report.md        # Urban forest quality report
old_model/                    # Previous CatBoost-based implementation
```

## Key Findings

1. **Ridge regression outperformed** all tree-based ensembles (Random Forest, XGBoost, CatBoost) on the full range, indicating the relationship is largely linear.
2. **5 features match 20 features** in performance -- the simpler model is recommended for deployment.
3. **Perimeter is the single most important predictor** for the full range; **compactness** overtakes it for the ≤8 subset.
4. **CatBoost outperforms Ridge on ≤8 trees** -- nonlinear shape relationships matter more for small clusters.
5. **Current dataset (479) is sufficient** -- models have captured 94-98.5% of their potential; the bottleneck is feature expressiveness, not data quantity.
6. **Error scales with cluster size** -- reliable for 2-10 trees (MAE ~0.6-1.6), less so for 20+.
7. **Tree point generation** -- constrained k-means places estimated trunk locations evenly inside each polygon, producing a point layer for GIS use.
8. **Urban forest quality** -- Haifa leads with 7.1m median crown diameter (14.1% large trees), followed by Tel Aviv (6.7m) and Ramat Gan (6.7m). National median: 6.2m across 3.9M trees in 39 cities.
