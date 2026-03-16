"""
Morphological feature extraction from polygon geometries.
Used for predicting tree trunk count from crown elevation polygons.
"""

import numpy as np
import pandas as pd
import math
from shapely.geometry import Polygon


def compute_mrr_axes(geom):
    """Compute major and minor axis lengths from the minimum rotated rectangle.

    Unlike the old code which used axis-aligned bounding box of the MRR,
    this computes actual side lengths from consecutive MRR vertices.
    """
    mrr = geom.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)
    # MRR has 5 coords (closed ring), 4 unique vertices
    side1 = math.hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
    side2 = math.hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
    major = max(side1, side2)
    minor = min(side1, side2)
    return major, minor


def compute_eccentricity(major, minor):
    """Eccentricity of the ellipse fitted to major/minor axes. 0 = circle, ~1 = elongated."""
    if major == 0:
        return 0.0
    if minor > major:
        major, minor = minor, major
    arg = np.clip(1 - (minor ** 2 / major ** 2), 0, 1)
    return math.sqrt(arg)


def compute_radial_stats(geom):
    """Compute statistics of distances from centroid to boundary vertices."""
    centroid = geom.centroid
    coords = list(geom.exterior.coords)[:-1]  # exclude closing vertex
    distances = [math.hypot(c[0] - centroid.x, c[1] - centroid.y) for c in coords]
    distances = np.array(distances)
    if len(distances) == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    mean_r = distances.mean()
    std_r = distances.std()
    cv_r = std_r / mean_r if mean_r > 0 else 0.0
    return mean_r, std_r, cv_r, distances.min(), distances.max()


def count_concavities(geom):
    """Count distinct concave indentations (components of convex_hull - polygon)."""
    hull = geom.convex_hull
    diff = hull.difference(geom)
    if diff.is_empty:
        return 0
    if diff.geom_type == 'Polygon':
        return 1
    if diff.geom_type in ('MultiPolygon', 'GeometryCollection'):
        return sum(1 for g in diff.geoms if g.geom_type == 'Polygon' and g.area > 0.01)
    return 0


def compute_l_ratio(major, minor, compactness):
    """L-ratio from old model: min(axes)/max(axes) / compactness^2."""
    if minor == 0 or compactness == 0:
        return 0.0
    return (min(major, minor) / max(major, minor)) / (compactness ** 2)


def extract_features(gdf):
    """Extract morphological features from a GeoDataFrame of polygons.

    Parameters
    ----------
    gdf : GeoDataFrame
        Must contain a 'geometry' column with Polygon geometries in a projected CRS (meters).

    Returns
    -------
    pd.DataFrame
        DataFrame with one row per polygon and ~20 morphological feature columns.
    """
    records = []

    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty or geom.geom_type != 'Polygon':
            continue

        # Basic metrics
        area = geom.area
        perimeter = geom.length
        perimeter_to_area = perimeter / area if area > 0 else 0.0

        # Shape indices
        compactness = (4 * math.pi * area) / (perimeter ** 2) if perimeter > 0 else 0.0
        hull = geom.convex_hull
        hull_area = hull.area
        convexity = area / hull_area if hull_area > 0 else 1.0

        # Bounding geometry (MRR)
        major, minor = compute_mrr_axes(geom)
        eccentricity = compute_eccentricity(major, minor)
        aspect_ratio = major / minor if minor > 0 else 0.0
        mrr_area = major * minor
        mrr_area_ratio = area / mrr_area if mrr_area > 0 else 0.0

        # Complexity
        n_vertices = len(geom.exterior.coords) - 1
        hull_perimeter = hull.length
        boundary_sinuosity = perimeter / hull_perimeter if hull_perimeter > 0 else 1.0
        n_concavities = count_concavities(geom)

        # Radial stats
        mean_radius, radius_std, radius_cv, min_radius, max_radius = compute_radial_stats(geom)
        radius_ratio = min_radius / max_radius if max_radius > 0 else 1.0

        # Derived
        equivalent_diameter = 2 * math.sqrt(area / math.pi) if area > 0 else 0.0
        convex_hull_deficit = hull_area - area
        l_ratio = compute_l_ratio(major, minor, compactness)

        records.append({
            'area': area,
            'perimeter': perimeter,
            'perimeter_to_area': perimeter_to_area,
            'compactness': compactness,
            'convexity': convexity,
            'eccentricity': eccentricity,
            'major_axis': major,
            'minor_axis': minor,
            'aspect_ratio': aspect_ratio,
            'mrr_area_ratio': mrr_area_ratio,
            'n_vertices': n_vertices,
            'boundary_sinuosity': boundary_sinuosity,
            'n_concavities': n_concavities,
            'mean_radius': mean_radius,
            'radius_std': radius_std,
            'radius_cv': radius_cv,
            'radius_ratio': radius_ratio,
            'equivalent_diameter': equivalent_diameter,
            'convex_hull_deficit': convex_hull_deficit,
            'l_ratio': l_ratio,
        })

    return pd.DataFrame(records, index=gdf.index[:len(records)])


FEATURE_COLUMNS = [
    'area', 'perimeter', 'perimeter_to_area', 'compactness', 'convexity',
    'eccentricity', 'major_axis', 'minor_axis', 'aspect_ratio', 'mrr_area_ratio',
    'n_vertices', 'boundary_sinuosity', 'n_concavities', 'mean_radius',
    'radius_std', 'radius_cv', 'radius_ratio', 'equivalent_diameter',
    'convex_hull_deficit', 'l_ratio',
]
