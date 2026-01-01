"""
OLD (FSI-like) Delineation Method
=================================

Implements the OLD/FSI-like Aravalli delineation using:
- Slope threshold (> 3°)
- Foothill buffer (100 m)
- Gap/valley bridging (500 m via morphological closing)

This is a best-effort approximation of the FSI 2010 methodology.
"""

import logging
from typing import Dict, Any, Optional

import numpy as np
import geopandas as gpd
from shapely.ops import unary_union
from rasterio.features import shapes

logger = logging.getLogger(__name__)


def compute_old_delineation(
    dem_data: Dict[str, Any],
    aoi_gdf: gpd.GeoDataFrame,
    params: Dict[str, float]
) -> gpd.GeoDataFrame:
    """
    Compute OLD (FSI-like) Aravalli delineation.
    
    Pipeline:
    1. Compute slope in degrees from DEM
    2. Threshold: slope > slope_threshold_deg
    3. Polygonize slope mask
    4. Apply foothill buffer outward
    5. Apply morphological closing for gap bridging
    
    Args:
        dem_data: DEM data dictionary from DEMAdapter
        aoi_gdf: Area of interest GeoDataFrame (in projected CRS)
        params: Parameters dictionary with:
            - slope_threshold_deg: Slope threshold in degrees
            - foothill_buffer_m: Foothill buffer in meters
            - gap_bridge_m: Gap bridging distance in meters
            
    Returns:
        GeoDataFrame with the OLD delineation polygon(s)
    """
    Z = dem_data['elevation']
    transform = dem_data['transform']
    crs = dem_data['crs']
    pixel_size = dem_data['pixel_size_m']
    
    slope_threshold = params['slope_threshold_deg']
    foothill_buffer = params['foothill_buffer_m']
    gap_bridge = params['gap_bridge_m']
    
    # Step 1: Compute slope (degrees)
    logger.info("  Computing slope...")
    slope_deg = _compute_slope_degrees(Z, pixel_size)
    
    # Step 2: Threshold
    logger.info(f"  Thresholding slope > {slope_threshold}°...")
    slope_mask = (slope_deg > slope_threshold) & np.isfinite(Z)
    
    masked_pixels = np.sum(slope_mask)
    total_pixels = np.sum(np.isfinite(Z))
    logger.info(f"  {masked_pixels:,} pixels ({100*masked_pixels/total_pixels:.1f}%) above threshold")
    
    # Step 2a: Urban Masking (New Requirement)
    # Filter out residential/urban areas using OSM data
    logger.info("  Generating urban exclusion mask (residential, col, etc.)...")
    urban_mask = _generate_urban_mask(aoi_gdf, Z.shape, transform)
    
    if urban_mask is not None:
        urban_pixel_count = np.sum(urban_mask)
        if urban_pixel_count > 0:
            logger.info(f"  Excluding {urban_pixel_count:,} urban pixels...")
            slope_mask = slope_mask & (~urban_mask)
            
            masked_pixels = np.sum(slope_mask)
            logger.info(f"  Remaining pixels after urban filter: {masked_pixels:,}")
    
    if masked_pixels == 0:
        logger.warning("  No pixels above slope threshold (after filtering) - returning empty layer")
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    # Step 3: Raster-based Buffering & Gap Filling (Much Faster than Vector)
    from scipy import ndimage
    
    # Calculate pixel radius for buffer and gap bridging
    buffer_pixels = int(np.ceil(foothill_buffer / pixel_size))
    gap_pixels = int(np.ceil(gap_bridge / pixel_size / 2))  # Closing radius is half gap
    
    logger.info(f"  Processing raster mask (Buffer: {buffer_pixels}px, Gap: {gap_pixels}px)...")
    
    # 1. Apply Morphological Closing (Gap Bridging)
    if gap_pixels > 0:
        logger.info(f"  Bridging gaps ({gap_bridge}m)...")
        # Use circular structure element
        struct_gap = ndimage.generate_binary_structure(2, 1)
        slope_mask = ndimage.binary_closing(slope_mask, structure=struct_gap, iterations=gap_pixels)
        
    # 2. Apply Dilation (Foothill Buffer)
    if buffer_pixels > 0:
        logger.info(f"  Applying foothill buffer ({foothill_buffer}m)...")
        struct_buffer = ndimage.generate_binary_structure(2, 1)
        slope_mask = ndimage.binary_dilation(slope_mask, structure=struct_buffer, iterations=buffer_pixels)
        
    masked_pixels_final = np.sum(slope_mask)
    logger.info(f"  Final mask has {masked_pixels_final:,} pixels")

    # Step 4: Polygonize Final Result
    logger.info("  Polygonizing final mask...")
    polygons = _polygonize_mask(slope_mask, transform, crs, masked_pixels_final)
    
    if polygons.empty:
        logger.warning("  Polygonization failed - returning empty layer")
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    # Dissolve (should be fast now as there are fewer, larger polygons)
    logger.info("  Creating final geometry...")
    old_union = unary_union(polygons.geometry.buffer(0))
    
    # Return as GeoDataFrame
    result = gpd.GeoDataFrame(
        {'layer': ['OLD_FSI_like']},
        geometry=[old_union],
        crs=crs
    )
    
    area_km2 = result.area.sum() / 1e6
    logger.info(f"  OLD layer area: {area_km2:.2f} km²")
    
    return result


def _generate_urban_mask(
    aoi_gdf: gpd.GeoDataFrame,
    shape: tuple,
    transform
) -> Optional[np.ndarray]:
    """
    Generate a binary mask of urban/built-up areas using OSM data.
    
    Fetches landuse=residential, industrial, commercial, retail, construction.
    """
    import osmnx as ox
    from rasterio import features
    
    logger.info("    Fetching OSM landuse data...")
    
    tags = {
        'landuse': [
            'residential', 
            'industrial', 
            'commercial', 
            'retail', 
            'construction',
            'institutional',
            'education',
            'military', 
            'cemetery',
            'quarry'
        ],
        'highway': [
            'motorway', 'trunk', 'primary', 'secondary', 
            'tertiary', 'residential', 'unclassified', 'paved'
        ],
        'railway': True,
        'aeroway': True
    }
    
    try:
        # Use the first geometry of AOI (usually singular)
        polygon = aoi_gdf.geometry.iloc[0]
        
        # Project to 4326 for OSM query
        if aoi_gdf.crs.is_projected:
            area_km2 = aoi_gdf.area.sum() / 1e6
            if area_km2 > 3000:
                logger.warning(f"    Large AOI ({area_km2:.0f} km²). Skipping 'highway' and 'railway' tags to prevent timeout.")
                if 'highway' in tags:
                    del tags['highway']
                if 'railway' in tags:
                    del tags['railway']

            polygon_4326 = gpd.GeoSeries([polygon], crs=aoi_gdf.crs).to_crs("EPSG:4326").iloc[0]
        else:
            polygon_4326 = polygon
            
        # Fetch features
        logger.info(f"    Requesting tags: {list(tags.keys())}")
        gdf = ox.features_from_polygon(polygon_4326, tags)
        
        if gdf.empty:
            logger.info("    No urban features found in OSM.")
            return None
            
        logger.info(f"    Found {len(gdf)} urban/infrastructure features.")
        # detailed count
        counts = gdf['geometry'].apply(lambda x: x.geom_type).value_counts()
        logger.info(f"    Geometry types: {counts.to_dict()}")
        
        if gdf.empty:
            logger.info("    No urban features found in OSM.")
            return None
            
        logger.info(f"    Found {len(gdf)} urban features.")
        
        # Project back to DEM CRS for rasterization
        if gdf.crs != aoi_gdf.crs:
            gdf = gdf.to_crs(aoi_gdf.crs)
            
        # Rasterize
        shapes = ((geom, 1) for geom in gdf.geometry)
        urban_mask = features.rasterize(
            shapes=shapes,
            out_shape=shape,
            transform=transform,
            fill=0,
            dtype=np.uint8
        )
        
        return urban_mask.astype(bool)
        
    except Exception as e:
        logger.warning(f"    Failed to generate urban mask: {e}")
        return None



def _compute_slope_degrees(Z: np.ndarray, pixel_size: float) -> np.ndarray:
    """
    Compute slope in degrees from elevation array.
    
    Uses numpy gradient for efficient computation.
    
    Args:
        Z: 2D elevation array (meters)
        pixel_size: Pixel size in meters
        
    Returns:
        2D array of slope values in degrees
    """
    # Handle NaN values for gradient computation
    Z_filled = np.where(np.isfinite(Z), Z, np.nanmean(Z[np.isfinite(Z)]))
    
    # Compute gradients (rise/run for y and x directions)
    dz_dy, dz_dx = np.gradient(Z_filled, pixel_size, pixel_size)
    
    # Compute slope magnitude (radians)
    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    
    # Convert to degrees
    slope_deg = np.degrees(slope_rad)
    
    # Restore NaN where original was NaN
    slope_deg = np.where(np.isfinite(Z), slope_deg, np.nan)
    
    return slope_deg


def _polygonize_mask(
    mask: np.ndarray,
    transform,
    crs: str,
    total_pixels: int = None
) -> gpd.GeoDataFrame:
    """
    Convert a binary mask to vector polygons.
    
    Args:
        mask: 2D boolean mask
        transform: Rasterio Affine transform
        crs: Coordinate reference system
        total_pixels: Total number of pixels for progress tracking
        
    Returns:
        GeoDataFrame with polygons
    """
    from shapely.geometry import shape as shapely_shape
    from tqdm import tqdm
    
    geoms = []
    
    # Wrap shapes generator with tqdm for progress tracking
    shape_gen = shapes(
        mask.astype(np.uint8),
        mask=mask,
        transform=transform
    )
    
    # Estimate total features (rough estimate based on pixel count)
    # Typically ~1 polygon per 1000 pixels, but this varies
    est_features = max(total_pixels // 1000, 100) if total_pixels else None
    
    for geom_dict, val in tqdm(
        shape_gen,
        desc="    Extracting polygons",
        total=est_features,
        unit="features",
        disable=False
    ):
        if val == 1:
            geom = shapely_shape(geom_dict)
            if geom.is_valid and not geom.is_empty:
                geoms.append(geom)
    
    if not geoms:
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    
    return gpd.GeoDataFrame(geometry=geoms, crs=crs)
