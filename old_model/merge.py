import geopandas as gpd
import pandas as pd
import sys

def merge_shapefiles(shapefile_paths, output_path):
    # Read the shapefiles
    shapefiles = [gpd.read_file(path) for path in shapefile_paths]
    
    # Merge the shapefiles into one
    merged_shapefile = gpd.GeoDataFrame(pd.concat(shapefiles, ignore_index=True), crs=shapefiles[0].crs)
    
    # Write the merged shapefile to the output path
    merged_shapefile.to_file(output_path)
    
    print(f"Shapefiles merged successfully. Merged file saved at: {output_path}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python merge_shapefiles.py <path_to_shapefile1> <path_to_shapefile2> <output_path>")
        sys.exit(1)
    
    # Get the paths to the shapefiles and the output path from command-line arguments
    shapefile_paths = sys.argv[1:3]
    output_path = sys.argv[3]
    
    # Call the merge function
    merge_shapefiles(shapefile_paths, output_path)