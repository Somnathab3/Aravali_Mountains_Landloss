
import pandas as pd
import geopandas as gpd
from pathlib import Path
import logging
import glob
import sys
import yaml

# Add src to path
sys.path.append('src')
from aravalli import visualization

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting result aggregation...")
    
    output_base = Path("outputs/districts")
    summary_files = list(output_base.rglob("tables/summary.csv"))
    
    if not summary_files:
        logger.error("No summary.csv files found within outputs/districts")
        return

    logger.info(f"Found {len(summary_files)} summary files.")
    
    # 1. Aggregate Tables
    dfs = []
    for f in summary_files:
        try:
            df = pd.read_csv(f)
            dfs.append(df)
        except Exception as e:
            logger.warning(f"Could not read {f}: {e}")
            
    if dfs:
        master_df = pd.concat(dfs, ignore_index=True)
        master_output = Path("outputs/all_districts_summary.csv")
        master_df.to_csv(master_output, index=False)
        logger.info(f"Master summary saved to: {master_output}")
        
        # Calculate totals
        total_old = master_df['OLD_Area_km2'].sum()
        total_new = master_df['NEW_Area_km2'].sum()
        logger.info(f"TOTAL OLD AREA: {total_old:.2f} km^2")
        logger.info(f"TOTAL NEW AREA: {total_new:.2f} km^2")
        
    # 2. Trigger Map Regeneration (if needed) for specific districts
    # Or valid verification of current Mahendragarh run which had issues?
    # Actually, let's just create a combined GeoJSON if possible
    
    logger.info("Merging GeoJSONs...")
    old_gdfs = []
    new_gdfs = []
    
    district_dirs = [d for d in output_base.iterdir() if d.is_dir()]
    
    for d_dir in district_dirs:
        old_path = d_dir / "old_aravalli.geojson"
        new_path = d_dir / "new_aravalli.geojson"
        
        if old_path.exists():
            try:
                gdf = gpd.read_file(old_path)
                if not gdf.empty:
                    gdf['district'] = d_dir.name
                    old_gdfs.append(gdf)
            except Exception as e:
                logger.warning(f"Error reading {old_path}: {e}")

        if new_path.exists():
            try:
                gdf = gpd.read_file(new_path)
                if not gdf.empty:
                    gdf['district'] = d_dir.name
                    new_gdfs.append(gdf)
            except Exception as e:
                 logger.warning(f"Error reading {new_path}: {e}")

    if old_gdfs:
        full_old = pd.concat(old_gdfs, ignore_index=True)
        full_old.to_file("outputs/all_districts_old.geojson", driver="GeoJSON")
        logger.info("Saved outputs/all_districts_old.geojson")
        
    if new_gdfs:
        full_new = pd.concat(new_gdfs, ignore_index=True)
        full_new.to_file("outputs/all_districts_new.geojson", driver="GeoJSON")
        logger.info("Saved outputs/all_districts_new.geojson")

    logger.info("Aggregation complete.")

if __name__ == "__main__":
    main()
