"""
DEM Adapter Module
==================

Provides adapters for loading DEM data from different sources:
- SRTM (via elevation package)
- Custom user-provided GeoTIFF

All adapters return data in a standardized format for analysis.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import hashlib

import numpy as np
import rasterio
import rioxarray as rxr
import xarray as xr

logger = logging.getLogger(__name__)


class DEMAdapter(ABC):
    """Abstract base class for DEM data adapters."""
    
    @abstractmethod
    def load_for_aoi(
        self,
        aoi_bounds: Tuple[float, float, float, float],
        target_crs: str,
        buffer_m: float = 5000
    ) -> Dict[str, Any]:
        """
        Load DEM data for an area of interest.
        
        Args:
            aoi_bounds: (minx, miny, maxx, maxy) in EPSG:4326
            target_crs: Target CRS for reprojection (e.g., "EPSG:32643")
            buffer_m: Buffer in meters around AOI for edge effects
            
        Returns:
            Dictionary containing:
                - elevation: 2D numpy array of elevations (meters)
                - transform: rasterio Affine transform
                - crs: CRS of the data
                - pixel_size_m: Pixel size in meters
                - nodata: NoData value
        """
        pass


class SRTMAdapter(DEMAdapter):
    """
    Adapter for SRTM DEM data.
    
    Uses the `elevation` package to download and clip SRTM data.
    Data is cached for subsequent runs.
    """
    
    def __init__(self, cache_dir: Path, product: str = "SRTM1"):
        """
        Initialize SRTM adapter.
        
        Args:
            cache_dir: Directory for caching DEM clips
            product: SRTM product ("SRTM1" for 30m, "SRTM3" for 90m)
        """
        self.cache_dir = Path(cache_dir)
        self.product = product
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_path(self, bounds: Tuple[float, float, float, float]) -> Path:
        """Generate a unique cache path based on bounds."""
        bounds_str = f"{bounds[0]:.4f}_{bounds[1]:.4f}_{bounds[2]:.4f}_{bounds[3]:.4f}"
        hash_str = hashlib.md5(bounds_str.encode()).hexdigest()[:10]
        return self.cache_dir / f"srtm_{hash_str}.tif"
    
    def load_for_aoi(
        self,
        aoi_bounds: Tuple[float, float, float, float],
        target_crs: str,
        buffer_m: float = 5000
    ) -> Dict[str, Any]:
        """Load SRTM data for the AOI."""
        
        minx, miny, maxx, maxy = aoi_bounds
        cache_path = self._get_cache_path(aoi_bounds)
        
        # Check cache
        if cache_path.exists():
            logger.info(f"  Loading cached SRTM from: {cache_path}")
        else:
            logger.info(f"  Downloading SRTM data...")
            try:
                # Try elevation package first (works on Linux/Mac)
                import platform
                if platform.system() == 'Windows':
                    # Use Windows-compatible downloader with Copernicus DEM primary
                    from .dem_providers import download_dem_for_bounds
                    download_dem_for_bounds(
                        bounds=aoi_bounds,
                        output_path=cache_path,
                        cache_dir=self.cache_dir,
                        provider='copernicus'  # Copernicus DEM with SRTM fallback
                    )
                else:
                    # Use elevation package on Unix systems
                    import elevation
                    elevation.clip(
                        bounds=(minx, miny, maxx, maxy),
                        output=str(cache_path),
                        product=self.product
                    )
                logger.info(f"  Cached to: {cache_path}")
            except Exception as e:
                logger.error(f"  SRTM download failed: {e}")
                raise RuntimeError(
                    f"Failed to download SRTM data. Error: {e}\n"
                    "Consider using --dem custom with a user-provided DEM file."
                )
        
        # Load and reproject
        dem = rxr.open_rasterio(str(cache_path), masked=True).squeeze()
        
        # Reproject to target CRS (meters)
        logger.info(f"  Reprojecting to {target_crs}...")
        dem_utm = dem.rio.reproject(target_crs)
        
        # Extract metadata
        transform = dem_utm.rio.transform()
        pixel_x = abs(transform.a)
        pixel_y = abs(transform.e)
        pixel_size = (pixel_x + pixel_y) / 2  # Average for non-square pixels
        
        # Convert to numpy
        Z = dem_utm.values.astype(np.float32)
        
        return {
            'elevation': Z,
            'transform': transform,
            'crs': target_crs,
            'pixel_size_m': pixel_size,
            'nodata': dem_utm.rio.nodata,
            'bounds': dem_utm.rio.bounds(),
            'shape': Z.shape,
            'xarray': dem_utm,  # Keep for profile sampling
        }


class CustomDEMAdapter(DEMAdapter):
    """
    Adapter for user-provided DEM GeoTIFF files.
    """
    
    def __init__(self, dem_path: str):
        """
        Initialize custom DEM adapter.
        
        Args:
            dem_path: Path to the DEM GeoTIFF file
        """
        self.dem_path = Path(dem_path)
        if not self.dem_path.exists():
            raise FileNotFoundError(f"DEM file not found: {dem_path}")
    
    def load_for_aoi(
        self,
        aoi_bounds: Tuple[float, float, float, float],
        target_crs: str,
        buffer_m: float = 5000
    ) -> Dict[str, Any]:
        """Load custom DEM data for the AOI."""
        
        logger.info(f"  Loading custom DEM: {self.dem_path}")
        
        # Load DEM
        dem = rxr.open_rasterio(str(self.dem_path), masked=True).squeeze()
        
        # Clip to AOI bounds (with buffer) if needed
        # First reproject to get bounds in DEM's CRS for clipping
        try:
            from shapely.geometry import box
            import geopandas as gpd
            from pyproj import CRS as PyCRS, Transformer
            
            # Create bounding box in EPSG:4326
            aoi_box = box(*aoi_bounds)
            
            # Add buffer (approximate, in degrees)
            buffer_deg = buffer_m / 111000  # Rough approximation
            aoi_buffered = aoi_box.buffer(buffer_deg)
            
            # Clip DEM to buffered AOI
            dem = dem.rio.clip_box(*aoi_buffered.bounds, crs="EPSG:4326")
            
        except Exception as e:
            logger.warning(f"  Could not clip DEM to AOI: {e}")
            logger.warning("  Using full DEM extent")
        
        # Reproject to target CRS
        logger.info(f"  Reprojecting to {target_crs}...")
        dem_utm = dem.rio.reproject(target_crs)
        
        # Extract metadata
        transform = dem_utm.rio.transform()
        pixel_x = abs(transform.a)
        pixel_y = abs(transform.e)
        pixel_size = (pixel_x + pixel_y) / 2
        
        # Convert to numpy
        Z = dem_utm.values.astype(np.float32)
        
        return {
            'elevation': Z,
            'transform': transform,
            'crs': target_crs,
            'pixel_size_m': pixel_size,
            'nodata': dem_utm.rio.nodata,
            'bounds': dem_utm.rio.bounds(),
            'shape': Z.shape,
            'xarray': dem_utm,
        }
