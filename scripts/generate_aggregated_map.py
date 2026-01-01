
import geopandas as gpd
from pathlib import Path
import matplotlib.pyplot as plt
import logging
import sys

# Add src to path
sys.path.append('src')

# Import generated visualization module (after import fix)
try:
    from aravalli import visualization
    from aravalli.boundaries import load_district_boundaries
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("Generating aggregated map...")
    
    output_dir = Path("outputs/aggregated_maps")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load Merged Layers
    try:
        old_gdf = gpd.read_file("outputs/all_districts_old.geojson")
        new_gdf = gpd.read_file("outputs/all_districts_new.geojson")
    except Exception as e:
        logger.error(f"Could not load merged GeoJSONs: {e}")
        return

    # Load All Districts Context
    districts_gdf = load_district_boundaries("data/districts.yml", confirmed_only=True)
    
    # Generate Map using existing function
    # Note: visualization.generate_maps expects specific args, but we can reuse internal 
    # _generate_comparison_overlay or mock the others if needed.
    # _generate_comparison_overlay(old_gdf, new_gdf, districts_gdf, output_dir, crs)
    
    # We need a CRS. Using Mahendragarh's as representative or projecting to a common UTM zone.
    # For large area (multiple states), EPSG:3857 (Web Mercator) is often better for visualization 
    # if we want OSM tiles, but visualization.py expects a specific projected CRS for analysis usually.
    # Let's use the CRS from the input GeoJSONs.
    
    # Use a metric CRS for correct area calculation and visualization
    # EPSG:32643 (UTM Zone 43N) covers NW India (Aravallis) well
    crs = "EPSG:32643"
        
    logger.info(f"Using Projected CRS: {crs}")
    
    # Ensure all align
    if districts_gdf.crs != crs:
        districts_gdf = districts_gdf.to_crs(crs)
    if new_gdf.crs != crs:
        new_gdf = new_gdf.to_crs(crs)
    if old_gdf.crs != crs:
        old_gdf = old_gdf.to_crs(crs)
        
    logger.info("Plotting comparison map...")
    
    # DISABLE OSM VECTOR OVERLAY for large aggregated map 
    # (Contextily basemap is sufficient and fetching vectors for 34 districts is too slow)
    original_add_context = visualization._add_osm_context
    visualization._add_osm_context = lambda ax, gdf, crs: logger.info("Skipping OSM vector overlay for large area.")
    
    visualization._generate_comparison_overlay(old_gdf, new_gdf, districts_gdf, output_dir, crs)
    
    # Restore (good practice)
    visualization._add_osm_context = original_add_context
    
    logger.info(f"Map saved to {output_dir}")

if __name__ == "__main__":
    main()
