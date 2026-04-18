# Urban Tree Analysis Pipeline

End-to-end pipeline for extracting tree trunks and analyzing urban forest quality across Israeli cities, given raw tree crown polygon shapefiles as input. This document describes the production analysis pipeline — separate from the model training/evaluation work documented in [results.MD](results.MD).

## Pipeline Overview

```
Raw tree crown polygons (XXX_tree_canopies_YYYY.shp)
         |
         v
 [1] batch_extract_features.py
     Geometry repair + dissolve overlaps + 20 morphological features
         |
         v
 XXX_tree_canopies_YYYY_processed.shp
         |
         v
 [2] batch_predict_trees.py
     Single-tree filter + Ridge regression prediction
         |
         v
 XXX_tree_canopies_YYYY_predicted.shp  (has pred_trees column)
         |
         v
 [3] batch_generate_points.py
     Constrained k-means trunk placement + crown area/diameter
         |
         v
 XXX_tree_trunks_YYYY.shp  (point layer)
         |
         +-------- [4a] urban_forest_analysis.py
         |             -> plots_urban_forest/, urban_forest_report.md, urban_forest_data.xlsx
         |
         +-------- Optional street tree branch
                   |
                   v
            Raw street segments (XXX_street_segments.shp)
                   |
                   v
         [5] batch_process_streets.py
             Dissolve + sliver fix + hole fill
                   |
                   v
            XXX_street_network_polygon.shp
                   |
                   v
         [6] extract_street_trees.py
             Filter trunks inside buffered street polygon (2m buffer)
                   |
                   v
            XXX_tree_trunks_YYYY_streets.shp
                   |
                   v
         [7] street_tree_analysis.py
             -> plots_street_trees/, street_trees_report.md, street_trees_data.xlsx

Solar exposure raster + Street network polygon
         |
         v
 [8] shade_index_analysis.py
     Zonal statistics + per-pixel Shade Index (SI = 1 - kdown/city_max)
         |
         v
 shade_index_data.xlsx, plots_shade_index/, shade_index_report.md
```

## Data Locations

| Type | Path |
|------|------|
| Raw tree canopies | `d:\OneDrive - Technion\Research\Shade Maps\Israel trees\XXX_tree_canopies_YYYY.shp` |
| Raw street segments | `d:\OneDrive - Technion\Research\Shade Maps\Israel streets\XXX_street_segments.shp` |
| Pipeline outputs | same folders as inputs |

Naming convention:
- `XXX` = 3-letter city code (see [city_codes.csv](city_codes.csv))
- `YYYY` = year of the underlying orthophoto/DSM data (typically 2022)

---

## Step 1: Feature Extraction

**Script**: [batch_extract_features.py](batch_extract_features.py)

**What it does**:
1. Reproject to EPSG:2039 (Israel TM Grid, metric)
2. Repair invalid geometries (`make_valid` + `buffer(0)`)
3. Strip Z coordinates
4. **Dissolve overlapping polygons** into unified geometry, then explode into individual polygons (chunked for files >50K polygons to avoid memory spikes)
5. Remove tiny polygons (<1 m²)
6. Extract 20 morphological features per polygon (area, perimeter, compactness, eccentricity, convexity, MRR axes, radial stats, concavities, etc.)

**Usage**:
```bash
# Single file
python batch_extract_features.py path/to/XXX_tree_canopies_YYYY.shp

# Entire folder
python batch_extract_features.py "d:\OneDrive - Technion\Research\Shade Maps\Israel trees"
```

**Input**: `XXX_tree_canopies_YYYY.shp`
**Output**: `XXX_tree_canopies_YYYY_processed.shp` (with feature columns appended)

**Feature columns** (10-char abbreviated for shapefile compatibility):
`area, perimeter, p_to_a, compact, convexity, eccentric, major_ax, minor_ax, asp_ratio, mrr_a_rat, n_vert, sinuosity, n_concav, mean_rad, rad_std, rad_cv, rad_ratio, eq_diam, hull_def, l_ratio`

---

## Step 2: Tree Count Prediction

**Script**: [batch_predict_trees.py](batch_predict_trees.py)

**What it does** (two-step prediction):
1. **Single-tree filter**: polygons with `area < 150 m² AND compactness > 0.6` are assigned 1 tree (compact small crowns = individual trees)
2. **Ridge regression**: for remaining polygons, predict trunk count using a Ridge model (5 features: perimeter, area, compactness, perimeter_to_area, eccentricity, alpha=100) trained on `train_set_validated.shp` (R²=0.736, MAE=1.52)

The Ridge model is trained inline in ~0.2s at script startup; no saved model file required.

**Usage**:
```bash
# Single file
python batch_predict_trees.py path/to/XXX_tree_canopies_YYYY_processed.shp

# Entire folder
python batch_predict_trees.py "d:\OneDrive - Technion\Research\Shade Maps\Israel trees"
```

**Why Ridge, not CatBoost**:
- Ridge has higher R² on the full range (0.736 vs 0.728)
- Ridge prediction is ~100x faster — critical for 300K+ polygon files
- Full 39-city run: 98 seconds total

**Input**: `XXX_tree_canopies_YYYY_processed.shp`
**Output**: `XXX_tree_canopies_YYYY_predicted.shp` (adds `pred_trees` column)

---

## Step 3: Trunk Point Generation

**Script**: [batch_generate_points.py](batch_generate_points.py)

**What it does**:
For each polygon with N predicted trees, generates N evenly-distributed point locations via **constrained k-means** (Centroidal Voronoi Tessellation approximation):
1. Sample ~500 candidate points uniformly inside the polygon (vectorized rejection sampling)
2. Run k-means with N clusters on those interior points
3. Snap any centroids that fell outside the polygon back inside

Each output point carries:
- `poly_id` — source polygon ID
- `tree_idx` — tree index within the polygon (1..N)
- `pred_tree` — total predicted trees in that polygon
- `crown_area` — polygon area / N (m²)
- `crown_diam` — equivalent circular diameter: `2·√(crown_area/π)` (m)

**Usage**:
```bash
# Single file
python batch_generate_points.py path/to/XXX_tree_canopies_YYYY_predicted.shp

# Entire folder
python batch_generate_points.py "d:\OneDrive - Technion\Research\Shade Maps\Israel trees"
```

CRS handling: If the input is in a geographic CRS (e.g., EPSG:4326), it is automatically reprojected to EPSG:2039 for correct area computation, then reprojected back for output.

**Input**: `XXX_tree_canopies_YYYY_predicted.shp`
**Output**: `XXX_tree_trunks_YYYY.shp` (point layer)

---

## Step 4a: Urban Forest Quality Analysis (All Trees)

**Script**: [urban_forest_analysis.py](urban_forest_analysis.py)

**What it does**:
- Reads all `XXX_tree_trunks_YYYY.shp` files (attributes only, ignore_geometry=True)
- Computes per-city crown diameter statistics (mean, median, Q10-Q90, large/small tree %, CV, skewness, etc.)
- Computes national aggregates from summed histogram bin counts and tree-count-weighted averages
- Calculates a composite quality score: `0.4·rank(median_diam) + 0.3·rank(large_tree_%) + 0.15·rank(diam_CV) + 0.15·rank(n_trees)`
- Generates 10 diagnostic plots
- Writes a comprehensive markdown report
- Exports all data to a multi-sheet Excel file

**Usage**:
```bash
python urban_forest_analysis.py
```

**Outputs**:
- [urban_forest_report.md](urban_forest_report.md) — comprehensive report with tables
- [plots_urban_forest/](plots_urban_forest/) — 10 diagnostic plots
- [urban_forest_data.xlsx](urban_forest_data.xlsx) — 5 sheets for custom plotting

---

## Step 5: Street Network Processing (for cities with street data)

**Script**: [batch_process_streets.py](batch_process_streets.py)

**What it does**:
1. Load `XXX_street_segments.shp` (polygon segments from parcel data)
2. Reproject to EPSG:2039
3. Strip Z coordinates (NTN has PolygonZ)
4. Repair invalid geometries
5. Dissolve all segments via `unary_union`
6. Close thin sliver gaps: buffer(+0.5m) then buffer(-0.5m)
7. Remove small holes (<50 m², artifacts from inaccurate drawing)
8. Save as single-feature shapefile

**Usage**:
```bash
# Process all cities with street segment data
python batch_process_streets.py

# Process specific cities
python batch_process_streets.py BTR TLV HAI
```

**Input**: `XXX_street_segments.shp`
**Output**: `XXX_street_network_polygon.shp` (in same folder)

---

## Step 6: Street Tree Filtering

**Script**: [extract_street_trees.py](extract_street_trees.py)

**What it does**:
1. Load the dissolved street network polygon for each city
2. Buffer by **2 meters** beyond street edges (to capture front-yard trees adjacent to streets)
3. Filter `XXX_tree_trunks_YYYY.shp` points: keep only those inside the buffered street polygon
4. Save as `XXX_tree_trunks_YYYY_streets.shp`

The 2m buffer is an intentional inclusive criterion — it captures trees planted in sidewalks, medians, and front yards that contribute to the streetscape canopy, rather than restricting to narrowly street-planted trees only.

**Usage**:
```bash
python extract_street_trees.py
```

Automatically processes all cities that have both a `_street_network_polygon.shp` and a `_tree_trunks_*.shp` file.

**Input**: `XXX_street_network_polygon.shp` + `XXX_tree_trunks_YYYY.shp`
**Output**: `XXX_tree_trunks_YYYY_streets.shp`

**Typical result**: ~20-30% of total trees are classified as street trees.

---

## Step 7: Street Tree Quality Analysis

**Script**: [street_tree_analysis.py](street_tree_analysis.py)

**What it does**:
Runs the same analysis as Step 4a but filtered to street trees only. Additionally produces a correlation plot comparing all-trees vs street-trees median crown diameter across cities.

**Usage**:
```bash
python street_tree_analysis.py
```

**Outputs**:
- [street_trees_report.md](street_trees_report.md) — comprehensive report
- [plots_street_trees/](plots_street_trees/) — 11 plots (all 10 standard plots labeled "Street Trees:" + correlation plot)
- [street_trees_data.xlsx](street_trees_data.xlsx) — 5 sheets for custom plotting

---

## Step 8: Street Shade Index Analysis

**Script**: [shade_index_analysis.py](shade_index_analysis.py)

**What it does**:
For each city that has both a solar exposure raster and a street network polygon:
1. Compute the raster's global maximum cumulative kdown (via windowed reads — avoids loading 1+ GB into memory)
2. Mask the raster with the street network polygon (`rasterio.mask.mask(crop=True)`)
3. Compute per-pixel Shade Index: `SI = 1 - (pixel_kdown / city_max_kdown)`
4. Aggregate to a single city-average SI (mean across all street pixels)

**Shade Index interpretation**:
- `SI = 0` → no shading (direct sun throughout the day)
- `SI = 1` → fully shaded
- Typical urban values: 0.04-0.28

**Usage**:
```bash
python shade_index_analysis.py
```

**Input**:
- `d:\OneDrive - Technion\Research\Shade Maps\Israel solar exposure\XXX_all_kdown_1999_218_SUM.tif`
- `XXX_street_network_polygon.shp` (from Step 5)
- `street_trees_data.xlsx` (from Step 7) — for the correlation plot

**Outputs**:
- `shade_index_data.xlsx` — per-city SI data (Excel for custom plotting)
- `plots_shade_index/01_si_per_city.png` — ranked bar chart of SI by city
- `plots_shade_index/02_si_vs_crown_diameter.png` — SI vs median street tree crown diameter (correlation plot)
- `shade_index_report.md` — comprehensive report

**Typical result**: Pearson r ≈ 0.74 between median street tree crown diameter and street average SI — tree canopy is a major driver of street shading.

---

## Processing a Single New City

To add a new city to the full pipeline:

```bash
# Place raw data in the expected locations:
#   d:\OneDrive - Technion\Research\Shade Maps\Israel trees\XXX_tree_canopies_YYYY.shp
#   d:\OneDrive - Technion\Research\Shade Maps\Israel streets\XXX_street_segments.shp  (optional)

CITY="XXX"
TREES_DIR="d:/OneDrive - Technion/Research/Shade Maps/Israel trees"

# Tree pipeline
python batch_extract_features.py "${TREES_DIR}/${CITY}_tree_canopies_YYYY.shp"
python batch_predict_trees.py "${TREES_DIR}/${CITY}_tree_canopies_YYYY_processed.shp"
python batch_generate_points.py "${TREES_DIR}/${CITY}_tree_canopies_YYYY_predicted.shp"

# Optional street branch (only if street_segments file exists)
python batch_process_streets.py "${CITY}"

# Regenerate analyses to include the new city
python urban_forest_analysis.py
python street_tree_analysis.py  # if streets available

# Update CITY_NAMES in urban_forest_analysis.py to show the full city name in reports/plots
```

Then add a line to [city_codes.csv](city_codes.csv).

---

## Processing All Cities at Once

```bash
TREES_DIR="d:/OneDrive - Technion/Research/Shade Maps/Israel trees"

# Full tree pipeline for all cities
python batch_extract_features.py "${TREES_DIR}"
python batch_predict_trees.py "${TREES_DIR}"
python batch_generate_points.py "${TREES_DIR}"

# Street pipeline for all cities with street data
python batch_process_streets.py
python extract_street_trees.py

# Analyses
python urban_forest_analysis.py
python street_tree_analysis.py
```

Alternatively, [run_full_pipeline.py](run_full_pipeline.py) runs steps 1–3 as subprocess-per-city for memory safety on large files.

---

## Performance Notes

| Step | Typical time per city | Notes |
|------|----------------------|-------|
| 1. Feature extraction | 5–300s | Scales with polygon count; dissolve is the heavy step |
| 2. Prediction | <2s | Ridge is essentially instant on millions of rows |
| 3. Point generation | 1–20 min | k-means per polygon; most time-consuming step |
| 5. Street processing | 1–30s | Fast dissolve on 1K–8K segments per city |
| 6. Street filtering | 1–60s | Vectorized `contains` with prepared geometry |
| 4a/7. Analyses | 15–30s each | Mostly plotting; statistics computation is fast |

For the current dataset (40 cities, ~3M trees), the complete pipeline takes about **3 hours** end-to-end, dominated by Step 3 (point generation).

## Key Data Guardrails

- **CRS**: All metric computations assume EPSG:2039 (Israel TM Grid). Non-projected inputs are auto-reprojected.
- **Memory**: Large cities (JER 452K polygons, RLZ 416K) use chunked dissolve to stay within ~2GB RAM.
- **Geometry repair is idempotent**: rerunning steps is safe.
- **Naming convention strictly enforced**: `XXX_tree_canopies_YYYY.shp` → `_processed` → `_predicted` → `_tree_trunks_` → `_streets`. Scripts use glob patterns that depend on this.
