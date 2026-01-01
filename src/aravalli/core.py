"""
Core Analysis Module for Aravalli Delineation
==============================================

Implements the main analysis pipelines for OLD (FSI-like) and NEW (20-Nov-2025)
Aravalli delineation methods.

**IMPORTANT LEGAL STATUS:**
The NEW definition was kept in abeyance on 29-Dec-2025 by Supreme Court order.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json

import numpy as np
import geopandas as gpd
from shapely.ops import unary_union
from shapely.geometry import shape, mapping

from . import LEGAL_STATUS, DEFAULT_PARAMS
from .dem import DEMAdapter, SRTMAdapter, CustomDEMAdapter
from .boundaries import load_district_boundaries
from .old_method import compute_old_delineation
from .new_method import compute_new_delineation
from .stats import compute_statistics, compute_hill_distances
from .visualization import generate_maps

logger = logging.getLogger(__name__)


def run_analysis(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the complete Aravalli delineation comparison analysis.
    
    Args:
        config: Configuration dictionary with analysis parameters
        
    Returns:
        Dictionary containing analysis results and statistics
    """
    logger.info("=" * 60)
    logger.info("ARAVALLI DELINEATION COMPARISON ANALYSIS")
    logger.info("=" * 60)
    logger.info(f"Legal Status: NEW definition is {LEGAL_STATUS['new_definition_status']}")
    logger.info(f"Abeyance Date: {LEGAL_STATUS['abeyance_date']}")
    logger.info("=" * 60)
    
    output_dir = Path(config['output_dir'])
    cache_dir = Path(config['cache_dir'])
    
    # 1. Load district boundaries
    logger.info("\n[Step 1/6] Loading district boundaries...")
    districts_gdf = load_district_boundaries(
        config_file=config['districts_file'],
        filter_districts=config.get('district_filter'),
        confirmed_only=config.get('confirmed_only', False),
        cache_dir=cache_dir
    )
    
    if districts_gdf.empty:
        raise ValueError("No districts loaded. Check districts.yml configuration.")
    
    logger.info(f"  Loaded {len(districts_gdf)} districts")
    for idx, row in districts_gdf.iterrows():
        logger.info(f"    - {row['name']}, {row['state']}")
    
    # 2. Get combined AOI
    aoi = gpd.GeoDataFrame(
        geometry=[unary_union(districts_gdf.geometry)],
        crs=districts_gdf.crs
    )
    
    # Estimate UTM CRS
    centroid = aoi.geometry.iloc[0].centroid
    utm_crs = estimate_utm_crs(centroid.y, centroid.x)
    logger.info(f"  Using projected CRS: {utm_crs}")
    
    aoi_utm = aoi.to_crs(utm_crs)
    districts_utm = districts_gdf.to_crs(utm_crs)
    
    # 3. Load DEM
    logger.info("\n[Step 2/6] Loading DEM data...")
    if config['dem_source'] == 'SRTM':
        dem_adapter = SRTMAdapter(cache_dir=cache_dir)
    else:
        dem_adapter = CustomDEMAdapter(dem_path=config['dem_path'])
    
    dem_data = dem_adapter.load_for_aoi(
        aoi_bounds=aoi.total_bounds,  # lon/lat bounds
        target_crs=utm_crs,
        buffer_m=5000  # 5km buffer for edge effects
    )
    
    logger.info(f"  DEM shape: {dem_data['elevation'].shape}")
    logger.info(f"  Pixel size: {dem_data['pixel_size_m']:.1f} m")
    logger.info(f"  Elevation range: {np.nanmin(dem_data['elevation']):.0f} - {np.nanmax(dem_data['elevation']):.0f} m")
    
    # 4. Compute OLD (FSI-like) delineation
    logger.info("\n[Step 3/6] Computing OLD (FSI-like) delineation...")
    old_params = {
        'slope_threshold_deg': config.get('slope_threshold_deg', DEFAULT_PARAMS['slope_threshold_deg']),
        'foothill_buffer_m': config.get('foothill_buffer_m', DEFAULT_PARAMS['foothill_buffer_m']),
        'gap_bridge_m': config.get('gap_bridge_m', DEFAULT_PARAMS['gap_bridge_m']),
    }
    logger.info(f"  Parameters: slope > {old_params['slope_threshold_deg']}°, "
                f"buffer {old_params['foothill_buffer_m']}m, gap {old_params['gap_bridge_m']}m")
    
    old_gdf = compute_old_delineation(
        dem_data=dem_data,
        aoi_gdf=aoi_utm,
        params=old_params
    )
    
    # 5. Compute NEW (20-Nov-2025) delineation
    logger.info("\n[Step 4/6] Computing NEW (20-Nov-2025) delineation...")
    logger.info(f"  ⚠️  NOTE: This definition is IN ABEYANCE per SC order 29-Dec-2025")
    
    new_params = {
        'relief_threshold_m': config.get('relief_threshold_m', DEFAULT_PARAMS['relief_threshold_m']),
        'range_proximity_m': config.get('range_proximity_m', DEFAULT_PARAMS['range_proximity_m']),
        'method': config.get('method', 'relief'),
        'relief_radius_m': config.get('relief_radius_m', DEFAULT_PARAMS['local_relief_radius_m']),
        'contour_interval_m': config.get('contour_interval_m', DEFAULT_PARAMS['contour_interval_m']),
        'enable_tiling': config.get('enable_tiling', False),
        'tile_size_m': config.get('tile_size_m', 10000),
    }
    logger.info(f"  Method: {new_params['method']}")
    logger.info(f"  Parameters: relief ≥ {new_params['relief_threshold_m']}m, "
                f"proximity {new_params['range_proximity_m']}m")
    
    new_gdf = compute_new_delineation(
        dem_data=dem_data,
        aoi_gdf=aoi_utm,
        params=new_params,
        cache_dir=cache_dir
    )
    
    # 6. Clip to AOI and per-district
    logger.info("\n[Step 5/6] Computing statistics...")
    
    old_clipped = gpd.overlay(old_gdf, aoi_utm, how='intersection') if not old_gdf.empty else old_gdf
    new_clipped = gpd.overlay(new_gdf, aoi_utm, how='intersection') if not new_gdf.empty else new_gdf
    
    # Compute statistics
    stats = compute_statistics(
        old_gdf=old_clipped,
        new_gdf=new_clipped,
        districts_gdf=districts_utm,
        dem_data=dem_data
    )
    
    # Compute hill distances
    hill_distances = compute_hill_distances(new_gdf)
    stats['hill_distances'] = hill_distances
    
    # 7. Generate outputs
    logger.info("\n[Step 6/6] Generating outputs...")
    
    # Save GeoJSON files
    old_output = output_dir / "old_aravalli.geojson"
    new_output = output_dir / "new_aravalli.geojson"
    
    if not old_clipped.empty:
        old_clipped.to_crs("EPSG:4326").to_file(str(old_output), driver="GeoJSON")
        logger.info(f"  Saved: {old_output}")
    
    if not new_clipped.empty:
        new_clipped.to_crs("EPSG:4326").to_file(str(new_output), driver="GeoJSON")
        logger.info(f"  Saved: {new_output}")
    
    # Save statistics
    stats_df = stats['per_district']
    stats_df.to_csv(output_dir / "tables" / "summary.csv", index=False)
    logger.info(f"  Saved: {output_dir / 'tables' / 'summary.csv'}")
    
    if hill_distances is not None:
        hill_distances.to_csv(output_dir / "tables" / "hill_distances.csv", index=False)
        logger.info(f"  Saved: {output_dir / 'tables' / 'hill_distances.csv'}")
    
    # Save metadata
    metadata = {
        "run_timestamp": datetime.utcnow().isoformat() + "Z",
        "parameters": {
            "method": config.get('method', 'relief'),
            "contour_interval": config.get('contour_interval_m', 10),
            "relief_radius": config.get('relief_radius_m', 2000),
            "slope_threshold": config.get('slope_threshold_deg', 3.0),
            "foothill_buffer": config.get('foothill_buffer_m', 100),
            "gap_bridge": config.get('gap_bridge_m', 500),
            "relief_threshold": DEFAULT_PARAMS['relief_threshold_m'],
            "range_proximity": DEFAULT_PARAMS['range_proximity_m'],
        },
        "dem_source": config.get('dem_source', 'SRTM'),
        "dem_resolution_m": dem_data['pixel_size_m'],
        "crs": str(utm_crs),
        "districts_processed": list(districts_gdf['name']),
        "legal_status": LEGAL_STATUS,
    }
    
    with open(output_dir / "tables" / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"  Saved: {output_dir / 'tables' / 'metadata.json'}")
    
    # Generate maps
    generate_maps(
        old_gdf=old_clipped,
        new_gdf=new_clipped,
        aoi_gdf=aoi_utm,
        districts_gdf=districts_utm,
        dem_data=dem_data,
        hill_distances=hill_distances,
        output_dir=output_dir / "maps",
        crs=utm_crs
    )
    
    # Summary statistics
    old_area_km2 = stats['old_total_area_km2']
    new_area_km2 = stats['new_total_area_km2']
    
    logger.info("\n" + "=" * 60)
    logger.info("ANALYSIS COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  OLD (FSI-like) total area:  {old_area_km2:,.2f} km²")
    logger.info(f"  NEW (20-Nov-2025) total area: {new_area_km2:,.2f} km²")
    if old_area_km2 > 0:
        change_pct = ((new_area_km2 - old_area_km2) / old_area_km2) * 100
        logger.info(f"  Change: {change_pct:+.1f}%")
    logger.info(f"\n⚠️  REMINDER: NEW definition is {LEGAL_STATUS['new_definition_status']}")
    logger.info("=" * 60)
    
    return {
        'old_area_km2': old_area_km2,
        'new_area_km2': new_area_km2,
        'per_district_stats': stats_df,
        'metadata': metadata,
    }


def estimate_utm_crs(lat: float, lon: float) -> str:
    """
    Estimate the appropriate UTM CRS for a given lat/lon.
    
    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        
    Returns:
        EPSG code string for the UTM zone
    """
    # Calculate UTM zone
    zone = int((lon + 180) / 6) + 1
    
    # Northern or Southern hemisphere
    if lat >= 0:
        epsg = 32600 + zone  # Northern hemisphere
    else:
        epsg = 32700 + zone  # Southern hemisphere
    
    return f"EPSG:{epsg}"
