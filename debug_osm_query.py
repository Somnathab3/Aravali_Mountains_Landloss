
import osmnx as ox
import logging

logging.basicConfig(level=logging.INFO)

queries = [
    "Beawar, Rajasthan, India",
    "Beawar District, Rajasthan",
    "Beawar Tehsil, Rajasthan",
    "Beawar, Ajmer, Rajasthan",
    "Salumber, Rajasthan, India",
    "Salumber District, Rajasthan",
    "Salumber Tehsil, Rajasthan",
    "Salumber, Udaipur, Rajasthan",
    "Salumbar, Rajasthan",
    "Salumbar Tehsil, Rajasthan",
    "Salumber Subdistrict, Rajasthan",
    "Salumber Block, Rajasthan"
]

print("Testing OSM queries...")

for q in queries:
    try:
        print(f"Querying: '{q}'...", end=" ")
        gdf = ox.geocode_to_gdf(q)
        if not gdf.empty:
            geom = gdf.geometry.iloc[0]
            # quick approx area in deg^2 (valid for relative checking)
            area = geom.area
            print(f"SUCCESS! Found {geom.geom_type}. Area: {area:.6f} (deg^2)")
        else:
            print("FAILED (Empty result)")
    except Exception as e:
        print(f"ERROR: {e}")
