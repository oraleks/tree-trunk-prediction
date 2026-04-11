# Urban Forest Quality Analysis: 39 Israeli Cities

## Summary

- **Total trees analyzed**: 3,890,249
- **Total crown polygons**: 2,096,017
- **National mean crown diameter**: 6.1 m
- **National median crown diameter**: 6.2 m
- **Large trees (>= 10m crown)**: 7.7% nationally
- **Small trees (< 4m crown)**: 22.5% nationally

### Key Findings

1. **Top 3 cities by crown quality**: HAI (Haifa), TLV (Tel Aviv), RMG (Ramat Gan)
2. **Bottom 3 cities**: NSZ (Ness Ziona), UMF (Umm al-Fahm), RHT (Rahat)
3. **Largest median crown**: HAI (Haifa) at 7.1 m
4. **Smallest median crown**: RHT (Rahat) at 4.9 m
5. **Most large trees**: HAI (Haifa) at 14.1%

## Methodology

### Data Pipeline

Tree crown polygons were extracted from digital surface model (DSM) derived elevation data for each city. The analysis pipeline:

1. **Geometry repair**: Invalid polygons fixed, multi-parts exploded, contained polygons removed
2. **Feature extraction**: 20 morphological features computed per polygon
3. **Tree count prediction**: Polygons with area < 150 m^2 and compactness > 0.6 assigned 1 tree; remaining polygons predicted using Ridge regression (R2=0.736)
4. **Point generation**: Tree trunk locations placed via constrained k-means inside each polygon

### Crown Diameter Derivation

For each polygon with predicted N trees:
- Crown area per tree = polygon area / N
- Crown diameter = 2 * sqrt(crown_area / pi) (equivalent circular diameter)

### Quality Definition

Urban forest quality is assessed by crown diameter as a proxy for tree maturity and canopy development. Larger crown diameters indicate:
- More mature trees with greater ecosystem services
- Better growing conditions (soil, water, space)
- Higher canopy coverage and shade provision

A **composite quality score** combines: median crown diameter (40%), large tree fraction (30%), crown diameter diversity/CV (15%), and total tree count (15%).

## National Crown Diameter Distribution

![National Distribution](plots_urban_forest/01_national_crown_diameter_hist.png)

The national distribution is right-skewed, with most trees in the 4-8m crown diameter range. The median (6.2 m) is slightly below the mean (6.1 m), reflecting the tail of very large crown polygons.

## City Rankings

### By Median Crown Diameter

![Median Ranking](plots_urban_forest/04_city_ranking_median_diam.png)

| Rank | City | Name | Median (m) | Mean (m) | IQR (m) | Trees |
|------|------|------|-----------|---------|---------|-------|
| 1 | HAI | Haifa | 7.1 | 7.0 | 3.7 | 460,131 |
| 2 | TLV | Tel Aviv | 6.7 | 6.7 | 3.8 | 377,882 |
| 3 | RMG | Ramat Gan | 6.7 | 6.7 | 3.4 | 176,827 |
| 4 | HDS | Hod HaSharon | 6.6 | 6.7 | 2.6 | 44,197 |
| 5 | HRZ | Herzliya | 6.6 | 6.4 | 3.3 | 84,991 |
| 6 | PHK | Petah Tikva | 6.6 | 6.8 | 3.0 | 44,384 |
| 7 | KFS | Kfar Saba | 6.5 | 6.3 | 3.4 | 58,502 |
| 8 | PTV | Petah Tikva | 6.5 | 6.7 | 3.2 | 65,846 |
| 9 | GTM | Givatayim | 6.5 | 6.5 | 3.4 | 39,738 |
| 10 | RAN | Raanana | 6.4 | 6.3 | 2.9 | 55,346 |
| 11 | HDR | Hadera | 6.4 | 6.6 | 3.8 | 120,440 |
| 12 | AFL | Afula | 6.4 | 6.5 | 3.1 | 25,461 |
| 13 | BBK | Bnei Brak | 6.3 | 6.2 | 3.7 | 35,615 |
| 14 | NHR | Nahariya | 6.3 | 6.5 | 3.2 | 22,226 |
| 15 | KAT | Kfar Saba | 6.3 | 6.4 | 3.4 | 56,946 |
| 16 | NTN | Netanya | 6.2 | 6.5 | 3.0 | 74,475 |
| 17 | AKO | Akko | 6.1 | 6.4 | 2.9 | 25,055 |
| 18 | BSM | Beit Shemesh | 6.1 | 6.2 | 3.1 | 55,224 |
| 19 | HOL | Holon | 6.0 | 5.9 | 4.3 | 61,569 |
| 20 | RHV | Rehovot | 6.0 | 6.3 | 2.6 | 81,221 |
| 21 | RLZ | Rishon LeZion | 6.0 | 5.9 | 3.6 | 443,138 |
| 22 | MDN | Modiin | 6.0 | 6.1 | 2.6 | 72,134 |
| 23 | UMF | Umm al-Fahm | 5.8 | 5.8 | 2.4 | 65,140 |
| 24 | ELT | Eilat | 5.8 | 6.0 | 2.9 | 13,422 |
| 25 | NSZ | Ness Ziona | 5.8 | 6.0 | 2.5 | 39,729 |
| 26 | NZR | Nazareth | 5.8 | 5.8 | 2.6 | 46,878 |
| 27 | RSN | Rosh HaAyin | 5.8 | 5.7 | 3.7 | 54,542 |
| 28 | RML | Ramla | 5.7 | 5.7 | 4.0 | 43,198 |
| 29 | BTY | Bat Yam | 5.7 | 5.6 | 4.6 | 34,950 |
| 30 | ASK | Ashkelon | 5.7 | 5.5 | 3.6 | 141,322 |
| 31 | YVN | Yavne | 5.6 | 5.6 | 4.2 | 54,092 |
| 32 | LOD | Lod | 5.6 | 5.5 | 3.8 | 46,526 |
| 33 | KGT | Kiryat Gat | 5.5 | 5.6 | 4.1 | 31,601 |
| 34 | JER | Jerusalem | 5.5 | 5.4 | 3.9 | 508,736 |
| 35 | ASD | Ashdod | 5.4 | 5.4 | 4.2 | 127,851 |
| 36 | SDR | Sderot | 5.3 | 6.0 | 4.9 | 24,094 |
| 37 | BSV | Beersheva | 5.2 | 5.3 | 3.9 | 142,349 |
| 38 | NTV | Netivot | 5.2 | 5.4 | 4.3 | 16,127 |
| 39 | RHT | Rahat | 4.9 | 4.9 | 3.4 | 18,344 |

### By Large Tree Fraction (crown >= 10m)

![Large Tree Ranking](plots_urban_forest/05_city_ranking_large_trees.png)

### Composite Urban Forest Quality Score

![Quality Heatmap](plots_urban_forest/08_quality_index_heatmap.png)

| Rank | City | Name | Quality Score | Median Diam | Large Tree % | Trees |
|------|------|------|--------------|------------|-------------|-------|
| 1 | HAI | Haifa | 0.908 | 7.1 m | 14.1% | 460,131 |
| 2 | TLV | Tel Aviv | 0.888 | 6.7 m | 12.1% | 377,882 |
| 3 | RMG | Ramat Gan | 0.858 | 6.7 m | 11.4% | 176,827 |
| 4 | HDR | Hadera | 0.813 | 6.4 m | 13.5% | 120,440 |
| 5 | HRZ | Herzliya | 0.778 | 6.6 m | 8.4% | 84,991 |
| 6 | GTM | Givatayim | 0.721 | 6.5 m | 9.6% | 39,738 |
| 7 | KFS | Kfar Saba | 0.694 | 6.5 m | 7.8% | 58,502 |
| 8 | PTV | Petah Tikva | 0.690 | 6.5 m | 8.7% | 65,846 |
| 9 | PHK | Petah Tikva | 0.647 | 6.6 m | 7.5% | 44,384 |
| 10 | KAT | Kfar Saba | 0.640 | 6.3 m | 8.2% | 56,946 |
| 11 | BBK | Bnei Brak | 0.640 | 6.3 m | 8.8% | 35,615 |
| 12 | NTN | Netanya | 0.619 | 6.2 m | 8.0% | 74,475 |
| 13 | HOL | Holon | 0.588 | 6.0 m | 7.1% | 61,569 |
| 14 | NHR | Nahariya | 0.571 | 6.3 m | 8.8% | 22,226 |
| 15 | HDS | Hod HaSharon | 0.567 | 6.6 m | 6.7% | 44,197 |
| 16 | RLZ | Rishon LeZion | 0.565 | 6.0 m | 6.2% | 443,138 |
| 17 | RAN | Raanana | 0.544 | 6.4 m | 5.5% | 55,346 |
| 18 | AFL | Afula | 0.521 | 6.4 m | 7.1% | 25,461 |
| 19 | AKO | Akko | 0.515 | 6.1 m | 8.0% | 25,055 |
| 20 | SDR | Sderot | 0.495 | 5.3 m | 13.2% | 24,094 |
| 21 | RHV | Rehovot | 0.462 | 6.0 m | 6.0% | 81,221 |
| 22 | BSM | Beit Shemesh | 0.454 | 6.1 m | 5.5% | 55,224 |
| 23 | RML | Ramla | 0.451 | 5.7 m | 6.9% | 43,198 |
| 24 | BTY | Bat Yam | 0.440 | 5.7 m | 6.8% | 34,950 |
| 25 | ASD | Ashdod | 0.432 | 5.4 m | 5.8% | 127,851 |
| 26 | RSN | Rosh HaAyin | 0.396 | 5.8 m | 4.8% | 54,542 |
| 27 | KGT | Kiryat Gat | 0.390 | 5.5 m | 6.8% | 31,601 |
| 28 | MDN | Modiin | 0.381 | 6.0 m | 4.3% | 72,134 |
| 29 | YVN | Yavne | 0.376 | 5.6 m | 5.2% | 54,092 |
| 30 | ASK | Ashkelon | 0.374 | 5.7 m | 3.6% | 141,322 |
| 31 | JER | Jerusalem | 0.347 | 5.5 m | 3.0% | 508,736 |
| 32 | LOD | Lod | 0.341 | 5.6 m | 5.2% | 46,526 |
| 33 | BSV | Beersheva | 0.329 | 5.2 m | 4.1% | 142,349 |
| 34 | NTV | Netivot | 0.318 | 5.2 m | 6.5% | 16,127 |
| 35 | NZR | Nazareth | 0.285 | 5.8 m | 3.0% | 46,878 |
| 36 | ELT | Eilat | 0.281 | 5.8 m | 5.2% | 13,422 |
| 37 | NSZ | Ness Ziona | 0.262 | 5.8 m | 4.3% | 39,729 |
| 37 | UMF | Umm al-Fahm | 0.262 | 5.8 m | 2.3% | 65,140 |
| 39 | RHT | Rahat | 0.160 | 4.9 m | 2.5% | 18,344 |

## Detailed City Comparisons

### Crown Diameter Distributions

![City Grid](plots_urban_forest/02_city_distributions_grid.png)

### Box Plot Comparison

![Box Plots](plots_urban_forest/03_city_boxplots.png)

### Crown Size Class Distribution

![Size Classes](plots_urban_forest/06_crown_size_classes_stacked.png)

## Correlations and Patterns

### Tree Count vs Quality

![Count vs Quality](plots_urban_forest/07_tree_count_vs_quality.png)

### CDF Comparison: Top and Bottom Cities

![CDF Comparison](plots_urban_forest/09_national_vs_city_cdf.png)

### Single-Tree vs All-Trees Estimates

![Single vs All](plots_urban_forest/10_single_vs_all_trees.png)

Points above the 1:1 line indicate cities where multi-tree polygon estimates inflate the median crown diameter. Points near or on the line suggest the multi-tree estimates are consistent with single-tree measurements.

## Data Quality Notes

### Single-Tree Polygon Fraction

The fraction of trees originating from single-tree polygons (pred_trees=1) varies by city. Higher single-tree fractions produce more reliable crown diameter estimates.

| City | Single-Tree Fraction | Note |
|------|---------------------|------|
| HAI | 29.9% | Low -- many merged canopies |
| HDS | 30.7% | Low -- many merged canopies |
| RAN | 34.1% | Low -- many merged canopies |
| PHK | 34.3% | Low -- many merged canopies |
| HDR | 35.7% | Low -- many merged canopies |
| TLV | 36.3% | Low -- many merged canopies |
| RHV | 36.5% | Low -- many merged canopies |
| HRZ | 36.5% | Low -- many merged canopies |
| RMG | 36.6% | Low -- many merged canopies |
| GTM | 38.3% | Low -- many merged canopies |
| NSZ | 38.4% | Low -- many merged canopies |
| KFS | 39.3% | Low -- many merged canopies |
| PTV | 39.7% | Low -- many merged canopies |
| NHR | 41.2% | Low -- many merged canopies |
| AFL | 41.6% | Low -- many merged canopies |
| AKO | 41.7% | Low -- many merged canopies |
| UMF | 42.1% | Low -- many merged canopies |
| MDN | 42.3% | Low -- many merged canopies |
| NTN | 42.8% | Low -- many merged canopies |
| KAT | 43.9% | Low -- many merged canopies |
| ASK | 44.9% | Low -- many merged canopies |
| NZR | 45.3% | Low -- many merged canopies |
| BBK | 45.9% | Low -- many merged canopies |
| RLZ | 46.7% | Low -- many merged canopies |
| BSM | 47.3% | Low -- many merged canopies |
| RSN | 48.7% | Low -- many merged canopies |
| HOL | 50.1% | Low -- many merged canopies |
| YVN | 51.3% | Low -- many merged canopies |
| SDR | 51.7% | Low -- many merged canopies |
| KGT | 52.7% | Low -- many merged canopies |
| BTY | 53.9% | Low -- many merged canopies |
| RML | 54.2% | Low -- many merged canopies |
| ELT | 54.3% | Low -- many merged canopies |
| LOD | 55.1% | Low -- many merged canopies |
| JER | 55.3% | Low -- many merged canopies |
| ASD | 56.0% | Low -- many merged canopies |
| BSV | 59.1% | Low -- many merged canopies |
| NTV | 62.7% |  |
| RHT | 66.9% |  |

### Outlier Detection

Cities with 99th percentile crown diameter > 25m may contain artifacts from large single-prediction polygons:

No cities have 99th percentile > 25m.

### Limitations

1. Crown diameter is derived from predicted tree counts -- prediction errors propagate to crown size estimates
2. Multi-tree polygons split crown area equally among predicted trees (assumes uniform crown sizes within a cluster)
3. The single-tree filter (area < 150m^2, compactness > 0.6) may misclassify some small multi-tree clusters as single trees
4. No species information is available -- crown size variation across species is not accounted for
5. Temporal variation: most data is from 2022 orthophotos; SDR uses 2025 data

## Appendix: Full Per-City Statistics

| City | Name | Trees | Polygons | Median Diam | Mean Diam | Std | Q25 | Q75 | Large % | Small % | CV | Single % | Quality Score |
|----|------|-------|----------|------------|----------|-----|-----|-----|----|-----|--|--|--|
| HAI | Haifa | 460,131 | 175,047 | 7.1 | 7.0 | 2.9 | 5.2 | 8.9 | 14.1 | 16.2 | 0.41 | 30 | 0.908 |
| TLV | Tel Aviv | 377,882 | 176,846 | 6.7 | 6.7 | 3.0 | 4.8 | 8.6 | 12.1 | 18.5 | 0.44 | 36 | 0.888 |
| RMG | Ramat Gan | 176,827 | 85,248 | 6.7 | 6.7 | 2.8 | 5.0 | 8.4 | 11.4 | 16.3 | 0.41 | 37 | 0.858 |
| HDR | Hadera | 120,440 | 54,683 | 6.4 | 6.6 | 3.0 | 4.6 | 8.4 | 13.5 | 19.0 | 0.46 | 36 | 0.813 |
| HRZ | Herzliya | 84,991 | 40,487 | 6.6 | 6.4 | 2.7 | 4.8 | 8.1 | 8.4 | 19.1 | 0.42 | 37 | 0.778 |
| GTM | Givatayim | 39,738 | 20,018 | 6.5 | 6.5 | 2.8 | 4.7 | 8.1 | 9.6 | 18.4 | 0.43 | 38 | 0.721 |
| KFS | Kfar Saba | 58,502 | 29,473 | 6.5 | 6.3 | 2.7 | 4.6 | 8.0 | 7.8 | 20.2 | 0.43 | 39 | 0.694 |
| PTV | Petah Tikva | 65,846 | 34,681 | 6.5 | 6.7 | 2.4 | 5.0 | 8.2 | 8.7 | 12.9 | 0.35 | 40 | 0.690 |
| PHK | Petah Tikva | 44,384 | 20,866 | 6.6 | 6.8 | 2.4 | 5.2 | 8.2 | 7.5 | 11.2 | 0.36 | 34 | 0.647 |
| KAT | Kfar Saba | 56,946 | 31,354 | 6.3 | 6.4 | 2.7 | 4.6 | 8.0 | 8.2 | 18.2 | 0.41 | 44 | 0.640 |
| BBK | Bnei Brak | 35,615 | 20,321 | 6.3 | 6.2 | 2.7 | 4.3 | 8.0 | 8.8 | 22.4 | 0.43 | 46 | 0.640 |
| NTN | Netanya | 74,475 | 41,134 | 6.2 | 6.5 | 2.4 | 4.8 | 7.8 | 8.0 | 15.3 | 0.37 | 43 | 0.619 |
| HOL | Holon | 61,569 | 36,982 | 6.0 | 5.9 | 2.8 | 3.7 | 8.0 | 7.1 | 27.2 | 0.47 | 50 | 0.588 |
| NHR | Nahariya | 22,226 | 11,726 | 6.3 | 6.5 | 2.4 | 4.7 | 7.9 | 8.8 | 15.3 | 0.37 | 41 | 0.571 |
| HDS | Hod HaSharon | 44,197 | 19,039 | 6.6 | 6.7 | 2.1 | 5.4 | 8.0 | 6.7 | 10.7 | 0.32 | 31 | 0.567 |
| RLZ | Rishon LeZion | 443,138 | 254,112 | 6.0 | 5.9 | 2.6 | 4.0 | 7.6 | 6.2 | 24.3 | 0.44 | 47 | 0.565 |
| RAN | Raanana | 55,346 | 25,504 | 6.4 | 6.3 | 2.4 | 4.9 | 7.8 | 5.5 | 17.0 | 0.38 | 34 | 0.544 |
| AFL | Afula | 25,461 | 13,686 | 6.4 | 6.5 | 2.2 | 4.9 | 8.0 | 7.1 | 14.5 | 0.34 | 42 | 0.521 |
| AKO | Akko | 25,055 | 13,046 | 6.1 | 6.4 | 2.4 | 4.8 | 7.7 | 8.0 | 14.5 | 0.38 | 42 | 0.515 |
| SDR | Sderot | 24,094 | 14,832 | 5.3 | 6.0 | 4.7 | 3.1 | 8.0 | 13.2 | 34.2 | 0.78 | 52 | 0.495 |
| RHV | Rehovot | 81,221 | 39,195 | 6.0 | 6.3 | 2.2 | 4.8 | 7.4 | 6.0 | 13.8 | 0.35 | 37 | 0.462 |
| BSM | Beit Shemesh | 55,224 | 32,188 | 6.1 | 6.2 | 2.3 | 4.5 | 7.6 | 5.5 | 18.2 | 0.37 | 47 | 0.454 |
| RML | Ramla | 43,198 | 28,043 | 5.7 | 5.7 | 2.7 | 3.6 | 7.6 | 6.9 | 28.5 | 0.47 | 54 | 0.451 |
| BTY | Bat Yam | 34,950 | 22,000 | 5.7 | 5.6 | 2.9 | 3.1 | 7.7 | 6.8 | 32.8 | 0.51 | 54 | 0.440 |
| ASD | Ashdod | 127,851 | 83,503 | 5.4 | 5.4 | 2.8 | 3.1 | 7.3 | 5.8 | 33.6 | 0.52 | 56 | 0.432 |
| RSN | Rosh HaAyin | 54,542 | 32,133 | 5.8 | 5.7 | 2.6 | 3.7 | 7.4 | 4.8 | 27.3 | 0.46 | 49 | 0.396 |
| KGT | Kiryat Gat | 31,601 | 19,570 | 5.5 | 5.6 | 2.7 | 3.4 | 7.5 | 6.8 | 30.4 | 0.49 | 53 | 0.390 |
| MDN | Modiin | 72,134 | 38,774 | 6.0 | 6.1 | 2.0 | 4.7 | 7.3 | 4.3 | 15.8 | 0.33 | 42 | 0.381 |
| YVN | Yavne | 54,092 | 32,791 | 5.6 | 5.6 | 2.8 | 3.3 | 7.5 | 5.2 | 30.5 | 0.50 | 51 | 0.376 |
| ASK | Ashkelon | 141,322 | 75,711 | 5.7 | 5.5 | 2.5 | 3.6 | 7.2 | 3.6 | 28.4 | 0.45 | 45 | 0.374 |
| JER | Jerusalem | 508,736 | 329,067 | 5.5 | 5.4 | 2.5 | 3.3 | 7.2 | 3.0 | 31.9 | 0.46 | 55 | 0.347 |
| LOD | Lod | 46,526 | 30,648 | 5.6 | 5.5 | 2.6 | 3.5 | 7.3 | 5.2 | 29.6 | 0.47 | 55 | 0.341 |
| BSV | Beersheva | 142,349 | 97,695 | 5.2 | 5.3 | 2.6 | 3.2 | 7.1 | 4.1 | 33.5 | 0.48 | 59 | 0.329 |
| NTV | Netivot | 16,127 | 11,489 | 5.2 | 5.4 | 2.8 | 3.0 | 7.3 | 6.5 | 35.4 | 0.52 | 63 | 0.318 |
| NZR | Nazareth | 46,878 | 26,721 | 5.8 | 5.8 | 2.1 | 4.4 | 7.0 | 3.0 | 19.3 | 0.36 | 45 | 0.285 |
| ELT | Eilat | 13,422 | 8,861 | 5.8 | 6.0 | 2.1 | 4.4 | 7.3 | 5.2 | 19.0 | 0.36 | 54 | 0.281 |
| NSZ | Ness Ziona | 39,729 | 20,001 | 5.8 | 6.0 | 2.0 | 4.7 | 7.2 | 4.3 | 15.3 | 0.33 | 38 | 0.262 |
| UMF | Umm al-Fahm | 65,140 | 34,587 | 5.8 | 5.8 | 1.9 | 4.6 | 7.0 | 2.3 | 16.5 | 0.32 | 42 | 0.262 |
| RHT | Rahat | 18,344 | 13,955 | 4.9 | 4.9 | 2.4 | 3.0 | 6.4 | 2.5 | 36.5 | 0.48 | 67 | 0.160 |

## Diagnostic Plots

All plots saved to `plots_urban_forest/`:

1. `01_national_crown_diameter_hist.png` -- National crown diameter histogram with CDF
2. `02_city_distributions_grid.png` -- Small multiples: per-city distributions
3. `03_city_boxplots.png` -- Box plots (Q10-Q90) sorted by median
4. `04_city_ranking_median_diam.png` -- City ranking by median crown diameter
5. `05_city_ranking_large_trees.png` -- City ranking by large tree fraction
6. `06_crown_size_classes_stacked.png` -- Size class proportions per city
7. `07_tree_count_vs_quality.png` -- Tree count vs crown quality scatter
8. `08_quality_index_heatmap.png` -- Multi-metric quality heatmap
9. `09_national_vs_city_cdf.png` -- CDF: top 5 vs bottom 5 cities
10. `10_single_vs_all_trees.png` -- Single-tree vs all-trees crown diameter
