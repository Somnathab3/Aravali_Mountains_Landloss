"""
Statistics Module
=================

Computes summary statistics for Aravalli delineation outputs:
- Per-district area calculations
- Elevation distribution statistics
- Inter-hill distance calculations
"""

import logging
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.strtree import STRtree
from shapely.geometry import MultiPolygon, Polygon

logger = logging.getLogger(__name__)


def compute_statistics(
    old_gdf: gpd.GeoDataFrame,
    new_gdf: gpd.GeoDataFrame,
    districts_gdf: gpd.GeoDataFrame,
    dem_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compute comprehensive statistics for the delineation layers.
    
    Args:
        old_gdf: OLD (FSI-like) delineation GeoDataFrame
        new_gdf: NEW (20-Nov-2025) delineation GeoDataFrame
        districts_gdf: District boundaries GeoDataFrame
        dem_data: DEM data dictionary
        
    Returns:
        Dictionary containing:
            - old_total_area_km2: Total OLD layer area
            - new_total_area_km2: Total NEW layer area
            - per_district: DataFrame with per-district statistics
            - elevation_stats: Elevation distribution statistics
    """
    stats = {}
    
    # Total areas
    old_area = old_gdf.area.sum() / 1e6 if not old_gdf.empty else 0
    new_area = new_gdf.area.sum() / 1e6 if not new_gdf.empty else 0
    
    stats['old_total_area_km2'] = old_area
    stats['new_total_area_km2'] = new_area
    
    # Per-district statistics
    district_stats = []
    
    for idx, district in districts_gdf.iterrows():
        district_geom = district.geometry
        district_name = district['name']
        district_state = district['state']
        
        # Clip layers to district
        old_in_district = _clip_to_geometry(old_gdf, district_geom)
        new_in_district = _clip_to_geometry(new_gdf, district_geom)
        
        old_district_area = old_in_district.area.sum() / 1e6 if not old_in_district.empty else 0
        new_district_area = new_in_district.area.sum() / 1e6 if not new_in_district.empty else 0
        
        change_km2 = new_district_area - old_district_area
        change_pct = (change_km2 / old_district_area * 100) if old_district_area > 0 else 0
        
        # District total area
        district_area = district_geom.area / 1e6
        old_pct_of_district = (old_district_area / district_area * 100) if district_area > 0 else 0
        new_pct_of_district = (new_district_area / district_area * 100) if district_area > 0 else 0
        
        district_stats.append({
            'District': district_name,
            'State': district_state,
            'District_Area_km2': round(district_area, 2),
            'OLD_Area_km2': round(old_district_area, 2),
            'NEW_Area_km2': round(new_district_area, 2),
            'Change_km2': round(change_km2, 2),
            'Change_pct': round(change_pct, 1),
            'OLD_pct_of_District': round(old_pct_of_district, 1),
            'NEW_pct_of_District': round(new_pct_of_district, 1),
        })
    
    stats['per_district'] = pd.DataFrame(district_stats)
    
    # Elevation statistics (if DEM data available)
    if dem_data and 'elevation' in dem_data:
        Z = dem_data['elevation']
        Z_valid = Z[np.isfinite(Z)]
        
        stats['elevation_stats'] = {
            'min': float(np.min(Z_valid)),
            'max': float(np.max(Z_valid)),
            'mean': float(np.mean(Z_valid)),
            'std': float(np.std(Z_valid)),
            'median': float(np.median(Z_valid)),
        }
    
    return stats


def _clip_to_geometry(gdf: gpd.GeoDataFrame, geometry) -> gpd.GeoDataFrame:
    """Clip a GeoDataFrame to a single geometry."""
    if gdf.empty:
        return gdf
    
    try:
        clipped = gpd.clip(gdf, gpd.GeoDataFrame(geometry=[geometry], crs=gdf.crs))
        return clipped
    except Exception as e:
        logger.warning(f"Clipping failed: {e}")
        return gpd.GeoDataFrame(geometry=[], crs=gdf.crs)


def compute_hill_distances(
    hills_gdf: gpd.GeoDataFrame,
    max_distance_m: float = 10000
) -> Optional[pd.DataFrame]:
    """
    Compute nearest-neighbor distances between hill polygons.
    
    Args:
        hills_gdf: GeoDataFrame containing individual hill polygons
        max_distance_m: Maximum distance to consider (meters)
        
    Returns:
        DataFrame with distance statistics, or None if no hills
    """
    if hills_gdf.empty:
        return None
    
    # Explode multipolygons to individual polygons
    try:
        hills = hills_gdf.explode(index_parts=False).reset_index(drop=True)
    except Exception:
        hills = hills_gdf.copy()
    
    if len(hills) < 2:
        return None
    
    logger.info(f"  Computing distances between {len(hills)} hill polygons...")
    
    # Build spatial index
    geoms = hills.geometry.tolist()
    tree = STRtree(geoms)
    
    distances = []
    
    for i, geom in enumerate(geoms):
        # Find nearby candidates
        candidates = tree.query(geom.buffer(max_distance_m))
        
        min_dist = float('inf')
        nearest_idx = -1
        
        for j in candidates:
            if i == j:
                continue
            
            dist = geom.distance(geoms[j])
            if dist < min_dist:
                min_dist = dist
                nearest_idx = j
        
        if np.isfinite(min_dist) and min_dist < max_distance_m:
            distances.append({
                'hill_id': i,
                'nearest_id': nearest_idx,
                'distance_m': round(min_dist, 1)
            })
    
    if not distances:
        return None
    
    df = pd.DataFrame(distances)
    
    # Summary statistics
    logger.info(f"  Distance statistics:")
    logger.info(f"    Min: {df['distance_m'].min():.0f}m")
    logger.info(f"    Max: {df['distance_m'].max():.0f}m")
    logger.info(f"    Mean: {df['distance_m'].mean():.0f}m")
    logger.info(f"    Median: {df['distance_m'].median():.0f}m")
    
    return df


def compute_elevation_within_polygon(
    geometry,
    dem_data: Dict[str, Any]
) -> Dict[str, float]:
    """
    Compute elevation statistics for pixels within a polygon.
    
    Args:
        geometry: Shapely geometry (Polygon/MultiPolygon)
        dem_data: DEM data dictionary
        
    Returns:
        Dictionary with elevation statistics
    """
    from rasterio.features import geometry_mask
    
    Z = dem_data['elevation']
    transform = dem_data['transform']
    
    if geometry is None or geometry.is_empty:
        return {'min': np.nan, 'max': np.nan, 'mean': np.nan, 'std': np.nan}
    
    try:
        mask = geometry_mask(
            [geometry],
            out_shape=Z.shape,
            transform=transform,
            invert=True
        )
        
        masked_elev = np.where(mask & np.isfinite(Z), Z, np.nan)
        valid = masked_elev[np.isfinite(masked_elev)]
        
        if len(valid) == 0:
            return {'min': np.nan, 'max': np.nan, 'mean': np.nan, 'std': np.nan}
        
        return {
            'min': float(np.min(valid)),
            'max': float(np.max(valid)),
            'mean': float(np.mean(valid)),
            'std': float(np.std(valid)),
        }
    
    except Exception as e:
        logger.warning(f"Elevation extraction failed: {e}")
        return {'min': np.nan, 'max': np.nan, 'mean': np.nan, 'std': np.nan}
