# Street Shade Index Analysis: 18 Israeli Cities

## Summary

- **Cities analyzed**: 18
- **Weighted mean Shade Index**: 0.1561
- **Most shaded streets**: KFS (Kfar Saba) at SI = 0.274
- **Least shaded streets**: NTV (Netivot) at SI = 0.041
- **Total street area analyzed**: 63.00 km2 across 252,020,274 pixels

## Methodology

### Shade Index Definition

For each raster pixel, the Shade Index is computed as:

```
SI = 1 - (pixel_kdown / city_max_kdown)
```

where `pixel_kdown` is the pixel's cumulative solar exposure (08:00-17:00 on 6 August), and `city_max_kdown` is the maximum pixel value across the entire city's raster (representing a fully unshaded reference location).

A city's **average SI** is the mean of per-pixel SI values across all raster cells that fall within the dissolved street network polygon.

- `SI = 0` means no shading (direct sunlight throughout the day)
- `SI = 1` means full shading (no direct solar exposure)
- Typical urban values: 0.1-0.5

### Data Sources

- **Solar exposure rasters**: 0.5 m/pixel cumulative kdown (6 Aug, 08:00-17:00), EPSG:2039
- **Street polygons**: dissolved street network polygons from `batch_process_streets.py`

## Per-City Shade Index

![SI per City](plots_shade_index/01_si_per_city.png)

| Rank | City | Name | Mean SI | Median SI | Street Area (km2) | Pixels |
|------|------|------|--------:|----------:|------------------:|-------:|
| 1 | KFS | Kfar Saba | 0.2742 | 0.1538 | 2.44 | 9,767,015 |
| 2 | TLV | Tel Aviv | 0.2520 | 0.1437 | 10.68 | 42,732,450 |
| 3 | HRZ | Herzliya | 0.2298 | 0.1008 | 2.99 | 11,950,193 |
| 4 | RAN | Raanana | 0.2274 | 0.1066 | 2.08 | 8,336,044 |
| 5 | HDS | Hod HaSharon | 0.2097 | 0.0829 | 1.91 | 7,654,857 |
| 6 | PTV | Petah Tikva | 0.1933 | 0.0853 | 4.54 | 18,177,185 |
| 7 | BTY | Bat Yam | 0.1836 | 0.0969 | 1.57 | 6,293,530 |
| 8 | HOL | Holon | 0.1756 | 0.0801 | 3.27 | 13,071,733 |
| 9 | NSZ | Ness Ziona | 0.1709 | 0.0619 | 1.54 | 6,149,053 |
| 10 | NTN | Netanya | 0.1365 | 0.0479 | 5.33 | 21,310,342 |
| 11 | PHK | Pardes Hanna-Karkur | 0.1215 | 0.0220 | 1.71 | 6,853,617 |
| 12 | HAI | Haifa | 0.1009 | 0.0344 | 7.92 | 31,698,477 |
| 13 | BTR | Beitar Ilit | 0.0952 | 0.0309 | 0.68 | 2,718,725 |
| 14 | AKO | Akko | 0.0830 | 0.0239 | 2.04 | 8,152,715 |
| 15 | ELT | Eilat | 0.0754 | 0.0266 | 2.48 | 9,906,380 |
| 16 | SDR | Sderot | 0.0707 | 0.0179 | 1.59 | 6,373,119 |
| 17 | BSV | Beersheva | 0.0666 | 0.0170 | 8.59 | 34,372,573 |
| 18 | NTV | Netivot | 0.0409 | 0.0128 | 1.63 | 6,502,266 |

## Correlation with Street Tree Crown Diameter

![SI vs Crown Diameter](plots_shade_index/02_si_vs_crown_diameter.png)

**Correlation**: Pearson r = 0.744, Spearman rho = 0.781

Interpretation: There is a **strong positive correlation** between median street tree crown diameter and street-average Shade Index. Cities with larger street trees tend to have more shaded streets, consistent with the hypothesis that tree canopy is a primary driver of street shading.

### Detailed Data

| City | Name | Median Crown Diam (m) | Mean SI |
|------|------|----------------------:|--------:|
| KFS | Kfar Saba | 6.4 | 0.2742 |
| TLV | Tel Aviv | 6.5 | 0.2520 |
| HRZ | Herzliya | 6.4 | 0.2298 |
| RAN | Raanana | 6.3 | 0.2274 |
| HDS | Hod HaSharon | 6.5 | 0.2097 |
| PTV | Petah Tikva | 6.4 | 0.1933 |
| BTY | Bat Yam | 5.5 | 0.1836 |
| HOL | Holon | 5.9 | 0.1756 |
| NSZ | Ness Ziona | 5.9 | 0.1709 |
| NTN | Netanya | 6.0 | 0.1365 |
| PHK | Pardes Hanna-Karkur | 6.5 | 0.1215 |
| HAI | Haifa | 6.3 | 0.1009 |
| BTR | Beitar Ilit | 5.0 | 0.0952 |
| AKO | Akko | 5.7 | 0.0830 |
| ELT | Eilat | 5.5 | 0.0754 |
| SDR | Sderot | 4.2 | 0.0707 |
| BSV | Beersheva | 4.9 | 0.0666 |
| NTV | Netivot | 4.7 | 0.0409 |

## Limitations

1. **Raster max as reference**: The global max per city may not be a perfectly unshaded point (e.g., if the entire city is partially shaded, the max is biased downward). Using absolute solar constants would change values but not the relative ranking.
2. **Building shade vs tree shade**: SI conflates shade from buildings, trees, and topography. Cities with tall buildings (TLV) may score high for reasons unrelated to tree cover.
3. **Single date**: Analysis is for 6 August only (~peak summer). Winter or morning/afternoon patterns may differ.
4. **Street polygon accuracy**: Depends on the quality of the dissolved street network polygon (see `batch_process_streets.py`).

## Files

- `shade_index_data.xlsx` -- per-city SI data (for custom plotting)
- `plots_shade_index/01_si_per_city.png` -- ranked bar chart
- `plots_shade_index/02_si_vs_crown_diameter.png` -- correlation scatter
