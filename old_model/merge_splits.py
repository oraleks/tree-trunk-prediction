import geopandas as gpd
import os
import pandas as pd  # Import pandas to use concat
import argparse

def merge_shapefiles(input_folder, output_shapefile):
    print("Starting to merge shapefiles...")
    
    # List to hold all the GeoDataFrames
    gdfs = []
    
    # Loop through the files in the input folder
    for file in os.listdir(input_folder):
        if file.endswith(".shp"):
            # Read each shapefile
            file_path = os.path.join(input_folder, file)
            gdf = gpd.read_file(file_path)
            gdfs.append(gdf)
    
    # Concatenate all GeoDataFrames into a single GeoDataFrame
    merged_gdf = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs=gdfs[0].crs)
    
    # Save the merged GeoDataFrame to a new shapefile
    merged_gdf.to_file(output_shapefile)
    print(f"Merged {len(gdfs)} shapefiles into {output_shapefile}")
    print("Merge process completed.")

if __name__ == "__main__":
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description="Merge shapefiles in a folder into one layer.")
    parser.add_argument("input_folder", help="Path to the folder containing shapefiles")
    parser.add_argument("output_shapefile", help="Path for the output merged shapefile")

    # Parse the arguments
    args = parser.parse_args()

    # Call the merge_shapefiles function with command-line arguments
    merge_shapefiles(args.input_folder, args.output_shapefile)
