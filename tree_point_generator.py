"""
Generate estimated tree trunk locations within crown polygons.

Given a polygon and the number of trees it contains, places N points
evenly distributed inside the polygon using constrained k-means
(Lloyd's algorithm approximation).

Algorithm:
1. Sample dense candidate points uniformly inside the polygon
2. Run k-means with N clusters on those interior points
3. The N cluster centroids are the estimated tree locations
4. Verify all centroids fall inside the polygon; snap any exterior ones

This produces a centroidal Voronoi tessellation approximation that
naturally handles concave and irregular polygon shapes.
"""

import numpy as np
import geopandas as gpd
from shapely.geometry import Point, MultiPoint
from sklearn.cluster import KMeans


def _sample_points_in_polygon(polygon, n_samples=1000, rng=None):
    """Sample n_samples points uniformly inside a polygon via rejection sampling."""
    if rng is None:
        rng = np.random.default_rng(42)

    minx, miny, maxx, maxy = polygon.bounds
    points = []

    while len(points) < n_samples:
        batch_size = (n_samples - len(points)) * 3  # oversample to account for rejections
        xs = rng.uniform(minx, maxx, batch_size)
        ys = rng.uniform(miny, maxy, batch_size)
        for x, y in zip(xs, ys):
            if polygon.contains(Point(x, y)):
                points.append((x, y))
                if len(points) >= n_samples:
                    break

    return np.array(points)


def _snap_to_polygon(point, polygon):
    """If a point is outside the polygon, snap it to the nearest interior location."""
    p = Point(point[0], point[1])
    if polygon.contains(p):
        return point
    # Project onto polygon boundary, then nudge slightly inward
    nearest = polygon.boundary.interpolate(polygon.boundary.project(p))
    # Move 10% toward centroid to ensure it's inside
    cx, cy = polygon.centroid.x, polygon.centroid.y
    nx = nearest.x + 0.1 * (cx - nearest.x)
    ny = nearest.y + 0.1 * (cy - nearest.y)
    return np.array([nx, ny])


def generate_tree_points(polygon, n_trees, n_samples=2000, random_state=42):
    """Generate evenly-distributed tree point locations inside a polygon.

    Parameters
    ----------
    polygon : shapely.geometry.Polygon
        The crown polygon to place trees in.
    n_trees : int
        Number of tree points to generate.
    n_samples : int
        Number of candidate points to sample inside polygon for k-means.
        Higher = more precise placement but slower. 2000 is good for most cases.
    random_state : int
        Random seed for reproducibility.

    Returns
    -------
    list of shapely.geometry.Point
        N tree point locations inside the polygon.
    """
    if polygon is None or polygon.is_empty:
        return []

    n_trees = max(1, int(n_trees))

    # Special case: 1 tree = centroid (or representative point if centroid is outside)
    if n_trees == 1:
        centroid = polygon.centroid
        if polygon.contains(centroid):
            return [centroid]
        return [polygon.representative_point()]

    rng = np.random.default_rng(random_state)

    # Sample dense candidate points inside the polygon
    n_actual = max(n_samples, n_trees * 50)
    candidates = _sample_points_in_polygon(polygon, n_actual, rng)

    if len(candidates) < n_trees:
        # Fallback for very small/thin polygons: use representative point
        rep = polygon.representative_point()
        return [rep] * n_trees

    # Run k-means to find N evenly-spaced centroids
    kmeans = KMeans(n_clusters=n_trees, random_state=random_state, n_init=10, max_iter=300)
    kmeans.fit(candidates)
    centroids = kmeans.cluster_centers_

    # Snap any centroids that fell outside the polygon
    points = []
    for c in centroids:
        c = _snap_to_polygon(c, polygon)
        points.append(Point(c[0], c[1]))

    return points


def generate_tree_points_gdf(gdf, count_column='Point_Coun', n_samples=2000, random_state=42):
    """Generate tree points for all polygons in a GeoDataFrame.

    Parameters
    ----------
    gdf : GeoDataFrame
        Polygon GeoDataFrame with a column indicating tree count.
    count_column : str
        Name of column containing the tree count per polygon.
    n_samples : int
        Candidate points per polygon for k-means.
    random_state : int
        Random seed.

    Returns
    -------
    GeoDataFrame
        Point GeoDataFrame with columns: geometry, polygon_id, tree_count, tree_index.
    """
    records = []

    for idx, row in gdf.iterrows():
        n_trees = int(row[count_column])
        if n_trees < 1:
            continue

        points = generate_tree_points(row.geometry, n_trees, n_samples, random_state)

        for i, pt in enumerate(points):
            records.append({
                'geometry': pt,
                'polygon_id': idx,
                'tree_count': n_trees,
                'tree_index': i + 1,
            })

    points_gdf = gpd.GeoDataFrame(records, crs=gdf.crs)
    return points_gdf


def compute_placement_quality(polygon, points):
    """Compute quality metrics for a set of points placed inside a polygon.

    Returns
    -------
    dict with:
        - mean_nn_dist: mean nearest-neighbor distance between points
        - cv_voronoi_area: coefficient of variation of approximate Voronoi cell areas
          (lower = more even distribution; 0 = perfectly even)
        - min_edge_dist: minimum distance from any point to polygon boundary
    """
    if len(points) <= 1:
        return {'mean_nn_dist': 0, 'cv_voronoi_area': 0, 'min_edge_dist': 0}

    coords = np.array([(p.x, p.y) for p in points])

    # Nearest-neighbor distances
    from scipy.spatial import distance_matrix
    dmat = distance_matrix(coords, coords)
    np.fill_diagonal(dmat, np.inf)
    nn_dists = dmat.min(axis=1)
    mean_nn = nn_dists.mean()

    # CV of nearest-neighbor distances (proxy for evenness)
    cv_nn = nn_dists.std() / mean_nn if mean_nn > 0 else 0

    # Minimum distance to boundary
    min_edge = min(polygon.boundary.distance(Point(c)) for c in coords)

    return {
        'mean_nn_dist': round(mean_nn, 2),
        'cv_nn_dist': round(cv_nn, 4),
        'min_edge_dist': round(min_edge, 2),
    }
