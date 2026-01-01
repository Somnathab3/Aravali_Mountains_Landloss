
import osmnx as ox
import geopandas as gpd
from shapely.ops import unary_union
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)

tehsils = [
    "Badnor Tehsil, Rajasthan",
    "Beawar Tehsil, Rajasthan",
    "Jaitaran Tehsil, Rajasthan",
    "Masuda Tehsil, Rajasthan",
    "Raipur Tehsil, Rajasthan",
    "Todgarh Tehsil, Rajasthan",
    "Vijaynagar Tehsil, Rajasthan"
]

# Relation IDs provided (optional usage if names fail)
# 10414058, 9641933, 9639201, 9641932, 9639200, 14911144

output_dir = Path("data/boundaries")
output_dir.mkdir(parents=True, exist_ok=True)
output_file = output_dir / "Beawar_merged.geojson"

geoms = []

print("Fetching constituent Tehsils for Beawar...")

for t in tehsils:
    try:
        print(f"  Fetching '{t}'...", end=" ")
        gdf = ox.geocode_to_gdf(t)
        if not gdf.empty:
            geom = gdf.geometry.iloc[0]
            if geom.geom_type in ['Polygon', 'MultiPolygon']:
                geoms.append(geom)
                print(f"Success ({geom.geom_type})")
            else:
                 print(f"Skipped (Wrong type: {geom.geom_type})")
        else:
            print("Failed (Not found)")
            
            # Fallback for Beawar Tehsil specifically if ambiguous? (User provided ID 9641933)
            # if t == "Beawar Tehsil, Rajasthan": ...
            
    except Exception as e:
        print(f"Error: {e}")

if geoms:
    print(f"\nMerging {len(geoms)} geometries...")
    merged_geom = unary_union(geoms)
    
    gdf_final = gpd.GeoDataFrame({'district': ['Beawar'], 'geometry': [merged_geom]}, crs="EPSG:4326")
    gdf_final.to_file(output_file, driver='GeoJSON')
    print(f"Saved merged boundary to: {output_file}")
else:
    print("No geometries found!")
