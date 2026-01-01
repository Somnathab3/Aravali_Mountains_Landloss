"""
NEW (20-Nov-2025) Delineation Method
=====================================

Implements the NEW Aravalli delineation based on SC judgment 20-Nov-2025:
- Relief threshold: ≥100m from local relief
- Local relief: lowest contour encircling landform
- Range proximity: 500m between hills

**IMPORTANT:** This definition is IN ABEYANCE per SC order 29-Dec-2025.

Two methods are provided:
1. Quick (relief): Local minimum filter approximation
2. Accurate (contour): Contour-based hill detection
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np
import geopandas as gpd
from shapely.ops import unary_union
from shapely.geometry import shape as shapely_shape
from scipy.ndimage import minimum_filter, maximum_filter, label
from rasterio.features import shapes
from skimage.morphology import local_maxima

logger = logging.getLogger(__name__)


def compute_new_delineation(
    dem_data: Dict[str, Any],
    aoi_gdf: gpd.GeoDataFrame,
    params: Dict[str, Any],
    cache_dir: Optional[Path] = None
) -> gpd.GeoDataFrame:
    """
    Compute NEW (20-Nov-2025) Aravalli delineation.
    
    Args:
        dem_data: DEM data dictionary from DEMAdapter
        aoi_gdf: Area of interest GeoDataFrame (in projected CRS)
        params: Parameters dictionary with:
            - method: 'relief' or 'contour'
            - relief_threshold_m: Relief threshold (default 100)
            - range_proximity_m: Range proximity distance (default 500)
            - relief_radius_m: Radius for local minimum filter
            - contour_interval_m: Contour interval for contour method
            
    Returns:
        GeoDataFrame with the NEW delineation polygon(s)
    """
    method = params.get('method', 'relief')
    
    logger.info(f"  ⚠️  NEW definition status: IN ABEYANCE (SC order 29-Dec-2025)")
    
    if method == 'relief':
        return _compute_relief_method(dem_data, aoi_gdf, params)
    elif method == 'contour':
        return _compute_contour_method(dem_data, aoi_gdf, params, cache_dir)
    else:
        raise ValueError(f"Unknown method: {method}")


def _compute_relief_method(
    dem_data: Dict[str, Any],
    aoi_gdf: gpd.GeoDataFrame,
    params: Dict[str, Any]
) -> gpd.GeoDataFrame:
    """
    Quick approximation using local minimum filter.
    
    This approximates "lowest contour encircling landform" by computing
    the minimum elevation within a configurable radius around each pixel.
    
    Pipeline:
    1. Apply minimum filter with configurable radius
    2. Compute local relief (elevation - local_minimum)
    3. Threshold: relief >= 100m
    4. Polygonize
    5. Apply range proximity clustering (500m)
    """
    Z = dem_data['elevation']
    transform = dem_data['transform']
    crs = dem_data['crs']
    pixel_size = dem_data['pixel_size_m']
    
    relief_threshold = params.get('relief_threshold_m', 100)
    range_proximity = params.get('range_proximity_m', 500)
    relief_radius = params.get('relief_radius_m', 2000)
    
    # Step 1: Compute local minimum filter
    logger.info(f"  Computing local minimum (radius: {relief_radius}m)...")
    
    # Convert radius to pixels
    window_size = max(3, int(relief_radius / pixel_size))
    if window_size % 2 == 0:
        window_size += 1  # Ensure odd window size
    
    logger.info(f"  Window size: {window_size} pixels")
    
    # Fill NaN values for filter operation
    Z_finite = np.isfinite(Z)
    Z_filled = np.where(Z_finite, Z, np.nanmin(Z[Z_finite]) if np.any(Z_finite) else 0)
    
    local_min = minimum_filter(Z_filled, size=window_size)
    
    # Step 2: Compute local relief
    relief = Z_filled - local_min
    
    # Step 3: Threshold
    logger.info(f"  Thresholding relief >= {relief_threshold}m...")
    relief_mask = (relief >= relief_threshold) & Z_finite
    
    masked_pixels = np.sum(relief_mask)
    total_pixels = np.sum(Z_finite)
    logger.info(f"  {masked_pixels:,} pixels ({100*masked_pixels/total_pixels:.1f}%) above threshold")
    
    if masked_pixels == 0:
        logger.warning("  No pixels above relief threshold - returning empty layer")
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    # Step 4: Polygonize
    logger.info("  Polygonizing...")
    polygons = _polygonize_mask(relief_mask, transform, crs)
    
    if polygons.empty:
        logger.warning("  Polygonization failed - returning empty layer")
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    # Dissolve into single geometry
    new_union = unary_union(polygons.geometry.buffer(0))
    
    # Step 5: Range proximity clustering (500m)
    # Merge hills within 500m using morphological closing
    half_proximity = range_proximity / 2
    logger.info(f"  Clustering hills within {range_proximity}m proximity...")
    
    new_clustered = gpd.GeoSeries([new_union], crs=crs).buffer(half_proximity)
    new_clustered = new_clustered.unary_union
    new_clustered = gpd.GeoSeries([new_clustered], crs=crs).buffer(-half_proximity).iloc[0]
    
    # Return as GeoDataFrame
    result = gpd.GeoDataFrame(
        {'layer': ['NEW_2025_relief']},
        geometry=[new_clustered],
        crs=crs
    )
    
    area_km2 = result.area.sum() / 1e6
    logger.info(f"  NEW layer area: {area_km2:.2f} km²")
    
    return result


def _compute_contour_method(
    dem_data: Dict[str, Any],
    aoi_gdf: gpd.GeoDataFrame,
    params: Dict[str, Any],
    cache_dir: Optional[Path] = None
) -> gpd.GeoDataFrame:
    """
    Contour-based approximation of "lowest contour encircling landform".
    
    This is more accurate but computationally intensive.
    
    Pipeline:
    1. Generate elevation contours at fixed interval
    2. Identify closed contours (polygons)
    3. Identify local maxima (hill peaks)
    4. For each peak, find lowest enclosing closed contour
    5. Calculate relief = peak_elev - contour_elev
    6. Filter hills where relief >= 100m
    7. Apply range proximity clustering
    """
    Z = dem_data['elevation']
    transform = dem_data['transform']
    crs = dem_data['crs']
    pixel_size = dem_data['pixel_size_m']
    
    relief_threshold = params.get('relief_threshold_m', 100)
    range_proximity = params.get('range_proximity_m', 500)
    contour_interval = params.get('contour_interval_m', 10)
    
    logger.info(f"  Generating contours at {contour_interval}m interval...")
    
    # Handle NaN values
    Z_finite = np.isfinite(Z)
    if not np.any(Z_finite):
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    Z_filled = np.where(Z_finite, Z, np.nanmin(Z[Z_finite]))
    
    # Generate contours
    min_elev = np.floor(np.nanmin(Z_filled) / contour_interval) * contour_interval
    max_elev = np.ceil(np.nanmax(Z_filled) / contour_interval) * contour_interval
    contour_levels = np.arange(min_elev, max_elev + contour_interval, contour_interval)
    
    logger.info(f"  Contour range: {min_elev:.0f} - {max_elev:.0f}m ({len(contour_levels)} levels)")
    
    # Generate closed contour polygons for each level
    closed_contours = []
    
    try:
        import matplotlib.pyplot as plt
        from matplotlib.path import Path as MplPath
        from shapely.geometry import Polygon, MultiPolygon
        
        # Use matplotlib's contour generation
        fig, ax = plt.subplots()
        
        # Create coordinate grids
        ny, nx = Z_filled.shape
        x_coords = transform.c + np.arange(nx) * transform.a
        y_coords = transform.f + np.arange(ny) * transform.e
        X, Y = np.meshgrid(x_coords, y_coords)
        
        for level in contour_levels:
            contour_set = ax.contour(X, Y, Z_filled, levels=[level])
            
            for path_collection in contour_set.collections:
                for path in path_collection.get_paths():
                    if path.codes is not None and len(path.vertices) > 3:
                        # Check if closed
                        if np.allclose(path.vertices[0], path.vertices[-1], atol=pixel_size):
                            try:
                                poly = Polygon(path.vertices)
                                if poly.is_valid and poly.area > 0:
                                    closed_contours.append({
                                        'elevation': level,
                                        'geometry': poly
                                    })
                            except:
                                pass
        
        plt.close(fig)
        
    except Exception as e:
        logger.warning(f"  Contour generation failed: {e}")
        logger.warning("  Falling back to relief method")
        return _compute_relief_method(dem_data, aoi_gdf, params)
    
    logger.info(f"  Found {len(closed_contours)} closed contours")
    
    if not closed_contours:
        logger.warning("  No closed contours found - falling back to relief method")
        return _compute_relief_method(dem_data, aoi_gdf, params)
    
    # Find local maxima (hill peaks)
    logger.info("  Identifying hill peaks (local maxima)...")
    
    # Use a larger neighborhood for peak detection
    peak_window = max(5, int(500 / pixel_size))  # ~500m minimum separation
    if peak_window % 2 == 0:
        peak_window += 1
    
    local_max = maximum_filter(Z_filled, size=peak_window)
    peaks_mask = (Z_filled == local_max) & Z_finite
    
    # Get peak coordinates and elevations
    peak_coords = np.argwhere(peaks_mask)
    logger.info(f"  Found {len(peak_coords)} potential peaks")
    
    # For each peak, find lowest enclosing contour
    hill_footprints = []
    
    # Sort contours by elevation (ascending)
    closed_contours.sort(key=lambda x: x['elevation'])
    
    for peak_idx, (py, px) in enumerate(peak_coords):
        peak_elev = Z_filled[py, px]
        peak_x = transform.c + px * transform.a
        peak_y = transform.f + py * transform.e
        
        from shapely.geometry import Point
        peak_point = Point(peak_x, peak_y)
        
        # Find lowest contour containing this peak
        for contour in closed_contours:
            if contour['geometry'].contains(peak_point):
                local_relief = peak_elev - contour['elevation']
                
                if local_relief >= relief_threshold:
                    hill_footprints.append({
                        'peak_elev': peak_elev,
                        'base_elev': contour['elevation'],
                        'relief': local_relief,
                        'geometry': contour['geometry']
                    })
                break  # Found the lowest enclosing contour
        
        # Progress logging for large datasets
        if (peak_idx + 1) % 1000 == 0:
            logger.info(f"    Processed {peak_idx + 1}/{len(peak_coords)} peaks...")
    
    logger.info(f"  Identified {len(hill_footprints)} hills with relief >= {relief_threshold}m")
    
    if not hill_footprints:
        logger.warning("  No hills meeting relief threshold - returning empty layer")
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    # Merge overlapping hill footprints
    all_hills = unary_union([h['geometry'] for h in hill_footprints])
    
    # Apply range proximity clustering (500m)
    half_proximity = range_proximity / 2
    logger.info(f"  Clustering hills within {range_proximity}m proximity...")
    
    new_clustered = gpd.GeoSeries([all_hills], crs=crs).buffer(half_proximity)
    new_clustered = new_clustered.unary_union
    new_clustered = gpd.GeoSeries([new_clustered], crs=crs).buffer(-half_proximity).iloc[0]
    
    # Return as GeoDataFrame
    result = gpd.GeoDataFrame(
        {'layer': ['NEW_2025_contour']},
        geometry=[new_clustered],
        crs=crs
    )
    
    area_km2 = result.area.sum() / 1e6
    logger.info(f"  NEW layer area: {area_km2:.2f} km²")
    
    return result


def _polygonize_mask(
    mask: np.ndarray,
    transform,
    crs: str
) -> gpd.GeoDataFrame:
    """Convert a binary mask to vector polygons."""
    geoms = []
    
    for geom_dict, val in shapes(
        mask.astype(np.uint8),
        mask=mask,
        transform=transform
    ):
        if val == 1:
            geom = shapely_shape(geom_dict)
            if geom.is_valid and not geom.is_empty:
                geoms.append(geom)
    
    if not geoms:
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    return gpd.GeoDataFrame(geometry=geoms, crs=crs)
