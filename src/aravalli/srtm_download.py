"""
Windows-compatible SRTM Download Utility
=========================================

Direct download of SRTM tiles from OpenTopography or USGS servers.
This works on Windows without requiring make/Unix tools.
"""

import logging
import math
from pathlib import Path
from typing import Tuple, List
import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)


def get_srtm_tile_names(bounds: Tuple[float, float, float, float]) -> List[str]:
    """
    Get SRTM tile names for the given bounds.
    
    Args:
        bounds: (minx, miny, maxx, maxy) in degrees
        
    Returns:
        List of SRTM tile names (e.g., ['N28E077', 'N28E078'])
    """
    minx, miny, maxx, maxy = bounds
    
    # Round to tile boundaries
    lat_min = math.floor(miny)
    lat_max = math.floor(maxy)
    lon_min = math.floor(minx)
    lon_max = math.floor(maxx)
    
    tiles = []
    for lat in range(lat_min, lat_max + 1):
        for lon in range(lon_min, lon_max + 1):
            # Format: N28E077 or S28W077
            lat_hem = 'N' if lat >= 0 else 'S'
            lon_hem = 'E' if lon >= 0 else 'W'
            tile_name = f"{lat_hem}{abs(lat):02d}{lon_hem}{abs(lon):03d}"
            tiles.append(tile_name)
    
    return tiles


def download_srtm_tile_opentopography(tile_name: str, output_dir: Path) -> Path:
    """
    Download a single SRTM tile from OpenTopography using the API.
    
    Args:
        tile_name: Tile name (e.g., 'N28E077')
        output_dir: Output directory
        
    Returns:
        Path to downloaded file
    """
    output_path = output_dir / f"{tile_name}.tif"
    
    if output_path.exists():
        logger.info(f"    {tile_name}.tif already exists")
        return output_path
    
    # Parse tile name to get bounding box
    # Format: N28E077 or S28W077
    lat_hem = tile_name[0]
    lat = int(tile_name[1:3])
    lon_hem = tile_name[3]
    lon = int(tile_name[4:7])
    
    # Convert to signed coordinates
    lat_val = lat if lat_hem == 'N' else -lat
    lon_val = lon if lon_hem == 'E' else -lon
    
    # SRTM tiles are 1x1 degree
    south = lat_val
    north = lat_val + 1
    west = lon_val
    east = lon_val + 1
    
    # OpenTopography API endpoint
    api_url = "https://portal.opentopography.org/API/globaldem"
    
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
        logger.info(f"    Downloading {tile_name} via OpenTopography API...")
        response = requests.get(api_url, params=params, stream=True, timeout=120)
        response.raise_for_status()
        
        # Get file size
        total_size = int(response.headers.get('content-length', 0))
        
        # Download with progress bar
        with open(output_path, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=tile_name) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))
        
        logger.info(f"    ✓ Downloaded {tile_name} (as GeoTIFF)")
        return output_path
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"    OpenTopography API download failed for {tile_name}: {e}")
        # Try alternative source
        return download_srtm_tile_usgs(tile_name, output_dir)


def download_srtm_tile_usgs(tile_name: str, output_dir: Path) -> Path:
    """
    Download a single SRTM tile from USGS EarthExplorer mirror.
    
    Args:
        tile_name: Tile name (e.g., 'N28E077')
        output_dir: Output directory
        
    Returns:
        Path to downloaded file
    """
    output_path = output_dir / f"{tile_name}.hgt"
    
    if output_path.exists():
        return output_path
    
    # USGS SRTM URL (alternative mirror)
    # Extract lat/lon from tile name
    lat_hem = tile_name[0]
    lat = int(tile_name[1:3])
    lon_hem = tile_name[3]
    lon = int(tile_name[4:7])
    
    # Construct directory path
    lat_dir = f"{lat_hem}{lat:02d}"
    
    url = f"https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/{lat_dir}.SRTMGL1.hgt.zip"
    
    try:
        logger.info(f"    Trying USGS mirror for {tile_name}...")
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        import zipfile
        import io
        
        # Extract .hgt from zip
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            # Find the .hgt file
            hgt_files = [f for f in zf.namelist() if f.endswith('.hgt')]
            if hgt_files:
                with zf.open(hgt_files[0]) as hgt:
                    with open(output_path, 'wb') as f:
                        f.write(hgt.read())
        
        logger.info(f"    ✓ Downloaded {tile_name}.hgt from USGS")
        return output_path
        
    except Exception as e:
        logger.warning(f"    USGS download failed for {tile_name}: {e}")
        logger.warning(f"    Skipping {tile_name} - proceeding with available tiles")
        # Return None to skip this tile instead of aborting
        return None


def merge_srtm_tiles(tile_paths: List[Path], output_path: Path):
    """
    Merge multiple SRTM .hgt tiles into a single GeoTIFF.
    
    Args:
        tile_paths: List of paths to .hgt files
        output_path: Output GeoTIFF path
    """
    logger.info(f"  Merging {len(tile_paths)} SRTM tiles...")
    
    import rasterio
    from rasterio.merge import merge
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    
    # Open all tiles
    src_files = []
    for tile_path in tile_paths:
        try:
            src = rasterio.open(tile_path)
            src_files.append(src)
        except Exception as e:
            logger.warning(f"  Could not open {tile_path}: {e}")
    
    if not src_files:
        raise RuntimeError("No valid SRTM tiles to merge")
    
    # Merge tiles
    mosaic, out_transform = merge(src_files)
    
    # Get metadata from first file
    out_meta = src_files[0].meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_transform,
        "compress": "lzw"
    })
    
    # Write merged file
    with rasterio.open(output_path, "w", **out_meta) as dest:
        dest.write(mosaic)
    
    # Close source files
    for src in src_files:
        src.close()
    
    logger.info(f"  ✓ Merged tiles saved to: {output_path}")


def download_srtm_for_bounds(
    bounds: Tuple[float, float, float, float],
    output_path: Path,
    cache_dir: Path
) -> Path:
    """
    Download and merge SRTM tiles for the given bounds.
    
    Args:
        bounds: (minx, miny, maxx, maxy) in degrees
        output_path: Output merged GeoTIFF path
        cache_dir: Directory for caching individual tiles
        
    Returns:
        Path to merged GeoTIFF
    """
    # Create cache directory
    tiles_dir = cache_dir / "srtm_tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    
    # Get required tiles
    tile_names = get_srtm_tile_names(bounds)
    logger.info(f"  Required SRTM tiles: {', '.join(tile_names)}")
    
    # Download tiles
    tile_paths = []
    failed_tiles = []
    for tile_name in tile_names:
        try:
            tile_path = download_srtm_tile_opentopography(tile_name, tiles_dir)
            if tile_path is not None:
                tile_paths.append(tile_path)
            else:
                failed_tiles.append(tile_name)
        except Exception as e:
            logger.error(f"  Failed to download {tile_name}: {e}")
            failed_tiles.append(tile_name)
            # Continue with other tiles
    
    # Log summary
    if failed_tiles:
        logger.warning(f"  Successfully downloaded {len(tile_paths)}/{len(tile_names)} tiles")
        logger.warning(f"  Failed tiles: {', '.join(failed_tiles)}")
        logger.warning(f"  Proceeding with partial coverage")
    
    if not tile_paths:
        raise RuntimeError("Failed to download any SRTM tiles")
    
    # Merge tiles
    merge_srtm_tiles(tile_paths, output_path)
    
    return output_path
