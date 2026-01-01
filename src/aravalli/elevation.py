"""
Elevation Profile Module
========================

Generates elevation profiles along user-defined transects.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Point

logger = logging.getLogger(__name__)


def generate_elevation_profile(
    start_point: Tuple[float, float],
    end_point: Tuple[float, float],
    dem_source: str = "SRTM",
    dem_path: Optional[str] = None,
    step_m: int = 100,
    output_path: str = "outputs/maps/elevation_profile.png"
) -> Dict[str, Any]:
    """
    Generate an elevation profile along a transect.
    
    Args:
        start_point: (lat, lon) of start point
        end_point: (lat, lon) of end point
        dem_source: "SRTM" or "custom"
        dem_path: Path to custom DEM (if dem_source is "custom")
        step_m: Sampling step in meters
        output_path: Output path for the plot
        
    Returns:
        Dictionary with profile data
    """
    from shapely.geometry import box
    from .dem import SRTMAdapter, CustomDEMAdapter
    from .core import estimate_utm_crs
    
    # Calculate bounds for DEM download
    lats = [start_point[0], end_point[0]]
    lons = [start_point[1], end_point[1]]
    bounds = (min(lons) - 0.1, min(lats) - 0.1, max(lons) + 0.1, max(lats) + 0.1)
    
    # Estimate UTM CRS
    center_lat = (start_point[0] + end_point[0]) / 2
    center_lon = (start_point[1] + end_point[1]) / 2
    utm_crs = estimate_utm_crs(center_lat, center_lon)
    
    # Load DEM
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    if dem_source == "SRTM":
        adapter = SRTMAdapter(cache_dir=cache_dir)
    else:
        adapter = CustomDEMAdapter(dem_path=dem_path)
    
    dem_data = adapter.load_for_aoi(bounds, utm_crs)
    dem_xr = dem_data['xarray']
    
    # Convert points to UTM
    from pyproj import Transformer
    transformer = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
    
    start_utm = transformer.transform(start_point[1], start_point[0])
    end_utm = transformer.transform(end_point[1], end_point[0])
    
    # Sample profile
    line = LineString([start_utm, end_utm])
    n_points = int(line.length // step_m) + 1
    distances = np.linspace(0, line.length, n_points)
    
    points = [line.interpolate(d) for d in distances]
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    
    # Sample DEM at points
    elevations = []
    for x, y in zip(xs, ys):
        try:
            elev = float(dem_xr.sel(x=x, y=y, method="nearest").values)
            elevations.append(elev)
        except:
            elevations.append(np.nan)
    
    elevations = np.array(elevations)
    
    # Generate plot
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.fill_between(distances / 1000, elevations, alpha=0.3, color='brown')
    ax.plot(distances / 1000, elevations, color='brown', linewidth=2)
    ax.set_xlabel('Distance (km)')
    ax.set_ylabel('Elevation (m)')
    ax.set_title(f'Elevation Profile: ({start_point[0]:.3f}, {start_point[1]:.3f}) → '
                f'({end_point[0]:.3f}, {end_point[1]:.3f})', fontweight='bold')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight', dpi=150)
    plt.close(fig)
    
    return {
        'distance_km': line.length / 1000,
        'min_elev': float(np.nanmin(elevations)),
        'max_elev': float(np.nanmax(elevations)),
        'mean_elev': float(np.nanmean(elevations)),
        'output_path': str(output_path),
    }
