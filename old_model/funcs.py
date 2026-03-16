import numpy as np
import math
from skimage.morphology import medial_axis
from shapely.geometry import Polygon, Point
from tqdm import tqdm

def calculate_compactness(polygon):
    polygon_area = polygon.area
    polygon_perimeter = polygon.length
    enclosing_circle_radius = polygon_perimeter / (2 * 3.14159265359)
    enclosing_circle_area = 3.14159265359 * enclosing_circle_radius**2
    compactness = polygon_area / enclosing_circle_area
    return compactness

def find_overlapping_polygons(df):
    polygons_to_keep = []

    for index, row in tqdm(df.iterrows(), total=len(df.index)):
        polygon = row['geometry']
        is_contained = False
        for inner_index, inner_row in df.iterrows():
            if inner_index != index:
                inner_polygon = inner_row['geometry']
                if inner_polygon.contains(polygon):
                    is_contained = True
                    break
        if not is_contained:
            polygons_to_keep.append(index)
    
    return df.loc[polygons_to_keep]

def is_convex(row):
    polygon = row['geometry']
    if row.geometry.geom_type == 'Polygon':
        coords = list(polygon.exterior.coords)
    else:
        coords = [coord for polygon_coords in row.geometry.geoms for coord in polygon_coords.exterior.coords]

    n = len(coords)
    sign = None
    
    for i in range(n):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % n]
        x3, y3 = coords[(i + 2) % n]
        
        cross_product = (x2 - x1) * (y3 - y2) - (y2 - y1) * (x3 - x2)
        
        if cross_product == 0:
            continue
        if sign is None:
            sign = cross_product > 0
        elif sign != (cross_product > 0):
            return False
    
    return True

def calculate_eccentricity(row):
    major_axis_length = row['major_axis_length']
    minor_axis_length = row['minor_axis_length']

    if major_axis_length == minor_axis_length:
        return 0  
    if minor_axis_length > major_axis_length:
        major_axis_length, minor_axis_length = minor_axis_length, major_axis_length
    _arg = 1 - (minor_axis_length**2 / max(major_axis_length**2, 1))
    arg = np.clip(_arg, 0, 1)
    result = math.sqrt(arg)
    return math.sqrt(arg)

def calculate_l_shape_ratio(line_coords):
    if len(line_coords) != 2:
        raise ValueError("Input line should have exactly two points")

    x1, y1 = line_coords[0]
    x2, y2 = line_coords[1]

    horizontal_length = abs(x2 - x1)
    vertical_length = abs(y2 - y1)

    if vertical_length == 0:
        return float('inf')

    return horizontal_length / vertical_length

def polygon_centerline(polygon, resolution=0.1):
    if not isinstance(polygon, Polygon):
        raise ValueError("Input must be a Shapely Polygon")

    xmin, ymin, xmax, ymax = polygon.bounds

    x_range = np.arange(xmin, xmax, resolution)
    y_range = np.arange(ymin, ymax, resolution)
    xx, yy = np.meshgrid(x_range, y_range)

    flat_coords = np.column_stack((xx.ravel(), yy.ravel()))

    binary_image = np.array([Point(coord).within(polygon) for coord in flat_coords], dtype=np.uint8)
    binary_image = binary_image.reshape(xx.shape)

    skel, distance = medial_axis(binary_image, return_distance=True)
    return skel

def calculate_l_shape(line):
    coords = list(line.coords)

    if len(coords) < 3:
        return 0  

    angle1 = np.arctan2(coords[-1][1] - coords[-2][1], coords[-1][0] - coords[-2][0])
    angle2 = np.arctan2(coords[-2][1] - coords[-3][1], coords[-2][0] - coords[-3][0])

    angle_diff = np.abs(angle1 - angle2)

    if np.abs(angle_diff - np.pi / 2) < 0.1:
        return 1  
    else:
        return 0  

def get_ratio(row):
    if not row['geometry'].geom_type == 'Polygon':
        return 0
    variable_1 = row['major_axis_length']
    variable_2 = row['minor_axis_length']
    variable_3 = row['compactness']
    if variable_2 == 0:
        print("Error: Division by zero. Variable_2 cannot be zero.")
        return None
    
    ratio = ((min(variable_1, variable_2) / max(variable_1, variable_2))/(variable_3**2))

    return ratio