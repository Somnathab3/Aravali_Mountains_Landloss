
import osmnx as ox
import geopandas as gpd
from shapely.ops import unary_union
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)

tehsils = [
    "Bayana Tehsil, Rajasthan",
    "Bharatpur Tehsil, Rajasthan",
    "Bhusawar Tehsil, Rajasthan",
    "Nadbai Tehsil, Rajasthan",
    "Rudawal Tehsil, Rajasthan",
    "Rupbas Tehsil, Rajasthan",
    "Uchhain Tehsil, Rajasthan",
    "Weir Tehsil, Rajasthan"
]

output_dir = Path("data/boundaries")
output_dir.mkdir(parents=True, exist_ok=True)
output_file = output_dir / "Bharatpur_merged.geojson"

geoms = []

print("Fetching constituent Tehsils for Bharatpur...")

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
            
            # Try variations if Rudawal fails
            if "Rudawal" in t:
                print("    Trying 'Rudawal' (no Tehsil suffix)...", end=" ")
                try: 
                    g2 = ox.geocode_to_gdf("Rudawal, Rajasthan")
                    if not g2.empty:
                        geoms.append(g2.geometry.iloc[0])
                        print("Success")
                except: pass

    except Exception as e:
        print(f"Error: {e}")

if geoms:
    print(f"\nMerging {len(geoms)} geometries...")
    merged_geom = unary_union(geoms)
    
    gdf_final = gpd.GeoDataFrame({'district': ['Bharatpur'], 'geometry': [merged_geom]}, crs="EPSG:4326")
    gdf_final.to_file(output_file, driver='GeoJSON')
    print(f"Saved merged boundary to: {output_file}")
else:
    print("No geometries found!")
