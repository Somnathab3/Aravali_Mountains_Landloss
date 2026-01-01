"""
DEM Data Providers
==================

Provides elevation data from multiple sources with automatic fallback:
1. Copernicus DEM GLO-30 (AWS Open Data) - Primary, no auth required
2. SRTM GL1 (OpenTopography API) - Fallback
3. SRTM (USGS LPDAAC) - Last resort (may require Earthdata credentials)

Key Features:
- No authentication required for primary source
- Automatic fallback when tiles unavailable
- Cloud Optimized GeoTIFF support
- Proper tile naming and key construction
"""

import logging
import math
from pathlib import Path
from typing import Tuple, List, Optional
import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)


# Copernicus DEM GLO-30 from AWS Open Data
COP30_HTTP = "https://copernicus-dem-30m.s3.amazonaws.com"
COP90_HTTP = "https://copernicus-dem-90m.s3.amazonaws.com"


def _cop_tile_id(lat: int, lon: int) -> str:
    """
    Generate Copernicus DEM tile ID from lat/lon.
    
    Format: N42_00_E029_00 or S12_00_W073_00
    """
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00"


def get_tile_names_for_bounds(bounds: Tuple[float, float, float, float]) -> List[Tuple[int, int, str]]:
    """
    Get tile names covering the bounding box.
    
    Args:
        bounds: (minx, miny, maxx, maxy) in degrees
        
    Returns:
        List of (lat, lon, tile_name) tuples
    """
    minx, miny, maxx, maxy = bounds
    
    lat_min = math.floor(miny)
    lat_max = math.floor(maxy)
    lon_min = math.floor(minx)
    lon_max = math.floor(maxx)
    
    tiles = []
    for lat in range(lat_min, lat_max + 1):
        for lon in range(lon_min, lon_max + 1):
            # Copernicus tile ID
            tile_id = _cop_tile_id(lat, lon)
            tiles.append((lat, lon, tile_id))
    
    return tiles


def download_copernicus_tile(lat: int, lon: int, tile_id: str, output_dir: Path, 
                             resolution: str = "30m") -> Optional[Path]:
    """
    Download a single Copernicus DEM tile from AWS.
    
    Args:
        lat: Latitude (integer degree)
        lon: Longitude (integer degree)
        tile_id: Tile ID (e.g., 'N28_00_E077_00')
        output_dir: Output directory
        resolution: '30m' or '90m'
        
    Returns:
        Path to downloaded file, or None if unavailable
    """
    output_path = output_dir / f"COP_{tile_id}.tif"
    
    if output_path.exists():
        logger.info(f"    {tile_id} already exists")
        return output_path
    
    # Construct AWS S3 URL
    # GLO-30 uses "10" (arc-seconds) in naming (10" ≈ 30m)
    # GLO-90 uses "30" (arc-seconds) in naming (30" ≈ 90m)
    arc_sec = "10" if resolution == "30m" else "30"
    base_url = COP30_HTTP if resolution == "30m" else COP90_HTTP
    
    folder = f"Copernicus_DSM_COG_{arc_sec}_{tile_id}_DEM"
    fname = f"Copernicus_DSM_COG_{arc_sec}_{tile_id}_DEM.tif"
    url = f"{base_url}/{folder}/{fname}"
    
    try:
        logger.info(f"    Downloading {tile_id} from Copernicus DEM (AWS)...")
        response = requests.get(url, stream=True, timeout=120)
        
        if response.status_code == 404:
            logger.warning(f"    Copernicus tile {tile_id} not available (404)")
            return None
            
        response.raise_for_status()
        
        # Get file size
        total_size = int(response.headers.get('content-length', 0))
        
        # Download with progress bar
        with open(output_path, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=tile_id) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))
        
        logger.info(f"    ✓ Downloaded {tile_id}")
        return output_path
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"    Copernicus download failed for {tile_id}: {e}")
        return None


def download_srtm_tile_opentopo(lat: int, lon: int, tile_id: str, output_dir: Path) -> Optional[Path]:
    """
    Download SRTM tile via OpenTopography API (fallback).
    
    Args:
        lat: Latitude (integer degree)
        lon: Longitude (integer degree)
        tile_id: Tile ID (e.g., 'N28E077')
        output_dir: Output directory
        
    Returns:
        Path to downloaded file, or None if unavailable
    """
    output_path = output_dir / f"SRTM_{tile_id}.tif"
    
    if output_path.exists():
        logger.info(f"    {tile_id} already exists (SRTM)")
        return output_path
    
    # OpenTopography API endpoint
    api_url = "https://portal.opentopography.org/API/globaldem"
    
    # SRTM tiles are 1x1 degree
    south = lat
    north = lat + 1
    west = lon
    east = lon + 1
    
    # API parameters
    params = {
        'demtype': 'SRTMGL1',  # SRTM GL1 (Global 30m)
        'south': south,
        'north': north,
        'west': west,
        'east': east,
        'outputFormat': 'GTiff',
        'API_Key': 'demoapikeyot2022'  # Demo API key
    }
    
    try:
        logger.info(f"    Downloading {tile_id} via OpenTopography API (fallback)...")
        response = requests.get(api_url, params=params, stream=True, timeout=120)
        response.raise_for_status()
        
        # Get file size
        total_size = int(response.headers.get('content-length', 0))
        
        # Download with progress bar
        with open(output_path, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=tile_id) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))
        
        logger.info(f"    ✓ Downloaded {tile_id} (SRTM)")
        return output_path
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"    OpenTopography download failed for {tile_id}: {e}")
        return None


def download_dem_for_bounds(
    bounds: Tuple[float, float, float, float],
    output_path: Path,
    cache_dir: Path,
    provider: str = "copernicus"
) -> Path:
    """
    Download and merge DEM tiles for the given bounds.
    
    Uses Copernicus DEM by default with automatic fallback to SRTM.
    
    Args:
        bounds: (minx, miny, maxx, maxy) in degrees
        output_path: Output merged GeoTIFF path
        cache_dir: Directory for caching individual tiles
        provider: 'copernicus' or 'srtm'
        
    Returns:
        Path to merged GeoTIFF
    """
    # Create cache directory
    tiles_dir = cache_dir / "dem_tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    
    # Get required tiles
    tiles = get_tile_names_for_bounds(bounds)
    logger.info(f"  Required DEM tiles: {len(tiles)} tiles")
    
    # Download tiles with automatic fallback
    tile_paths = []
    failed_tiles = []
    
    for lat, lon, tile_id in tiles:
        tile_path = None
        
        # Try Copernicus first (if selected)
        if provider == "copernicus":
            tile_path = download_copernicus_tile(lat, lon, tile_id, tiles_dir)
        
        # Fallback to SRTM if Copernicus failed or not selected
        if tile_path is None:
            # Convert to SRTM tile naming
            ns = "N" if lat >= 0 else "S"
            ew = "E" if lon >= 0 else "W"
            srtm_tile_id = f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}"
            tile_path = download_srtm_tile_opentopo(lat, lon, srtm_tile_id, tiles_dir)
        
        if tile_path is not None:
            tile_paths.append(tile_path)
        else:
            failed_tiles.append(tile_id)
    
    # Log summary
    if failed_tiles:
        logger.warning(f"  Successfully downloaded {len(tile_paths)}/{len(tiles)} tiles")
        logger.warning(f"  Failed tiles: {', '.join(failed_tiles[:5])}{'...' if len(failed_tiles) > 5 else ''}")
        logger.warning(f"  Proceeding with partial coverage")
    else:
        logger.info(f"  ✓ Downloaded all {len(tile_paths)} tiles")
    
    if not tile_paths:
        raise RuntimeError("Failed to download any DEM tiles")
    
    # Merge tiles
    from .srtm_download import merge_srtm_tiles  # Reuse merge function
    merge_srtm_tiles(tile_paths, output_path)
    
    return output_path
