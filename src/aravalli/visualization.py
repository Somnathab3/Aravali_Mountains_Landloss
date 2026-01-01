"""
Visualization Module
====================

Generates maps and plots for Aravalli delineation outputs.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import contextily as ctx
import osmnx as ox

logger = logging.getLogger(__name__)

COLORS = {
    'old': '#3498db',
    'new': '#e74c3c',
    'district': '#2c3e50',
}


def generate_maps(
    old_gdf: gpd.GeoDataFrame,
    new_gdf: gpd.GeoDataFrame,
    aoi_gdf: gpd.GeoDataFrame,
    districts_gdf: gpd.GeoDataFrame,
    dem_data: Dict[str, Any],
    hill_distances: Optional[pd.DataFrame],
    output_dir: Path,
    crs: str
) -> None:
    """Generate all visualization outputs."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    plt.style.use('seaborn-v0_8-whitegrid')
    plt.rcParams['figure.dpi'] = 150
    
    _generate_comparison_overlay(old_gdf, new_gdf, districts_gdf, output_dir, crs)
    _generate_elevation_histogram(dem_data, output_dir)
    
    if hill_distances is not None and not hill_distances.empty:
        _generate_distance_histogram(hill_distances, output_dir)
    
    logger.info(f"  Maps saved to: {output_dir}")


def _generate_comparison_overlay(old_gdf, new_gdf, districts_gdf, output_dir, crs):
    """Generate overlay comparison map with stats box."""
    fig, ax = plt.subplots(figsize=(12, 12))
    
    # 1. Plot Districts
    districts_gdf.boundary.plot(ax=ax, color=COLORS['district'], linewidth=1.5, linestyle='--', zorder=5)
    
    # Add district labels
    for idx, row in districts_gdf.iterrows():
        # Heuristic for label placement
        centroid = row.geometry.centroid
        ax.annotate(text=row['name'].upper(), xy=(centroid.x, centroid.y),
                   ha='center', va='center', fontsize=10, fontweight='bold', color='gray', alpha=0.6)
    
    # 1.5 Add OSM Context (Translucent Roads/Water)
    try:
        _add_osm_context(ax, districts_gdf, crs)
    except Exception as e:
        logger.warning(f"Could not add OSM context: {e}")
    
    # 2. Plot OLD Layer
    if not old_gdf.empty:
        old_gdf.plot(ax=ax, color=COLORS['old'], alpha=0.3, edgecolor=COLORS['old'], linewidth=0.5, zorder=3)
    
    # 3. Plot NEW Layer (Make it pop!)
    if not new_gdf.empty:
        # Fill
        new_gdf.plot(ax=ax, color=COLORS['new'], alpha=0.6, zorder=4)
        # Stroke (Thick)
        new_gdf.boundary.plot(ax=ax, color='red', linewidth=1.5, zorder=6)
    
    # 4. Basemap
    try:
        ctx.add_basemap(ax, crs=crs, source=ctx.providers.CartoDB.Positron, alpha=0.8)
    except Exception as e:
        logger.warning(f"Could not add basemap: {e}")
    
    # 5. Comparison Stats Box
    old_area = old_gdf.area.sum() / 1e6 if not old_gdf.empty else 0
    new_area = new_gdf.area.sum() / 1e6 if not new_gdf.empty else 0
    diff = old_area - new_area
    
    stats_text = (
        f"COMPARISON STATISTICS\n"
        f"-----------------------\n"
        f"OLD (Slope>3°): {old_area:,.1f} km²\n"
        f"NEW (Relief>100m): {new_area:,.2f} km²\n"
        f"-----------------------\n"
        f"Difference: -{diff:,.1f} km²\n"
        f"Reduced by: {100 * (1 - new_area/old_area) if old_area > 0 else 0:.1f}%"
    )
    
    # Place text box in top-left or top-right
    props = dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='gray')
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=11,
            verticalalignment='top', bbox=props, zorder=10, family='monospace')

    # 6. Custom Legend
    legend_elements = [
        mpatches.Patch(facecolor=COLORS['old'], alpha=0.3, edgecolor=COLORS['old'], label=f'OLD Definition (FSI-like)'),
        mpatches.Patch(facecolor=COLORS['new'], alpha=0.6, edgecolor='red', linewidth=1.5, label=f'NEW Definition (Local Relief > 100m)'),
        mpatches.Patch(facecolor='none', edgecolor=COLORS['district'], linestyle='--', linewidth=1.5, label='District Boundary')
    ]
    ax.legend(handles=legend_elements, loc='lower right', frameon=True, fancybox=True, framealpha=0.9)
    
    ax.set_title('Aravalli Delineation Comparison: OLD vs NEW', fontweight='bold', fontsize=14)
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(output_dir / 'comparison_overview.png', dpi=200, bbox_inches='tight')
    plt.close(fig)


def _generate_elevation_histogram(dem_data, output_dir):
    """Generate elevation distribution histogram."""
    if 'elevation' not in dem_data:
        return
    
    Z = dem_data['elevation']
    Z_valid = Z[np.isfinite(Z)].flatten()
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(Z_valid, bins=50, color='#27ae60', alpha=0.7, edgecolor='white')
    ax.axvline(np.mean(Z_valid), color='red', linestyle='--', label=f'Mean: {np.mean(Z_valid):.0f}m')
    ax.set_xlabel('Elevation (m)')
    ax.set_ylabel('Pixel Count')
    ax.set_title('Elevation Distribution in Study Area', fontweight='bold')
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_dir / 'elevation_distribution.png', bbox_inches='tight')
    plt.close(fig)


def _generate_distance_histogram(distances_df, output_dir):
    """Generate inter-hill distance histogram."""
    fig, ax = plt.subplots(figsize=(10, 6))
    distances = distances_df['distance_m']
    ax.hist(distances, bins=30, color='#9b59b6', alpha=0.7, edgecolor='white')
    ax.axvline(500, color='red', linestyle='--', label='500m threshold')
    ax.set_xlabel('Nearest Neighbor Distance (m)')
    ax.set_ylabel('Count')
    ax.set_title('Inter-Hill Distance Distribution', fontweight='bold')
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_dir / 'hill_distances_histogram.png', bbox_inches='tight')
    plt.savefig(output_dir / 'hill_distances_histogram.png', bbox_inches='tight')
    plt.close(fig)


def _add_osm_context(ax, aoi_gdf: gpd.GeoDataFrame, crs: str):
    """Fetch and plot translucent OSM context (roads, water)."""
    # Project AOI to 4326 for OSM query
    if aoi_gdf.crs != "EPSG:4326":
        aoi_4326 = aoi_gdf.to_crs("EPSG:4326")
    else:
        aoi_4326 = aoi_gdf
        
    # Get total bounds
    polygon = aoi_4326.geometry.unary_union
    
    # 1. Fetch Water bodies
    try:
        water = ox.features_from_polygon(polygon, tags={'natural': 'water', 'waterway': 'riverbank'})
        if not water.empty:
            if water.crs != crs:
                water = water.to_crs(crs)
            water.plot(ax=ax, color='#3498db', alpha=0.2, zorder=1)
    except Exception as e:
        logger.debug(f"No water features found: {e}")

    # 2. Fetch Major Roads
    try:
        roads = ox.features_from_polygon(polygon, tags={'highway': ['motorway', 'trunk', 'primary']})
        if not roads.empty:
            if roads.crs != crs:
                roads = roads.to_crs(crs)
            roads.plot(ax=ax, color='gray', alpha=0.3, linewidth=0.5, zorder=2)
    except Exception as e:
        logger.debug(f"No road features found: {e}")

