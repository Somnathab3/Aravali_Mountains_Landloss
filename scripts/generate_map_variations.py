#!/usr/bin/env python3
"""
Generate aggregated map variations with improved visualization and label handling.

Outputs:
1. comparison_overview_v2.png: Standard overlay with decluttered labels (Delhi inset logic or shifted).
2. comparison_side_by_side.png: Two distinct panels for clear comparison.
3. comparison_loss_map.png: Highlighting areas lost (Red) vs Retained (Green).
"""

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
import logging
import sys
import contextily as ctx

# Add src to path
sys.path.append('src')

try:
    from aravalli.boundaries import load_district_boundaries
except ImportError:
    # Quick fallback if src not in pythonpath properly
    def load_district_boundaries(path, confirmed_only=False):
        # This assumes we might load from the geojson if the function fails
        # but better to rely on path fix
        pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_basemap(ax, crs, zoom='auto'):
    try:
        ctx.add_basemap(ax, crs=crs, source=ctx.providers.CartoDB.PositronNoLabels, zoom=zoom)
    except Exception as e:
        logger.warning(f"Basemap fetch failed: {e}")

def fix_labels(ax, gdf):
    """
    Manually adjust labels for Delhi NCR cluster to avoid overlap.
    """
    offsets = {
        "Central Delhi": (0, 15),       # Shift Up
        "New Delhi": (-20, 10),         # Shift NW
        "South Delhi": (10, -10),       # Shift SE
        "South West Delhi": (-30, -10), # Shift SW
        "Faridabad": (30, -5),          # Shift East
        "Gurugram": (-20, -20),         # Shift SW
        "Nuh": (-10, -20),
        "Mahendragarh": (-10, -10),
    }

    for idx, row in gdf.iterrows():
        # Handle different column names (load_district_boundaries returns 'name', aggregated might have 'district')
        name = row.get('name', row.get('district'))
        if not name: continue
        
        # Calculate centroid in projected CRS
        centroid = row.geometry.centroid
        x, y = centroid.x, centroid.y
        
        # Apply offset if defined
        dx, dy = offsets.get(name, (0, 0))
        
        ha = 'center'
        if dx > 0: ha = 'left'
        if dx < 0: ha = 'right'
        
        ax.annotate(text=name, xy=(x, y), xytext=(dx, dy), 
                    textcoords='offset points',    # Points are small (1/72 inch). 10-30 is reasonable.
                    ha=ha, va='center',
                    fontsize=8, fontweight='bold', # Increased font slightly for readability
                    color='black',
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.6),
                    arrowprops=dict(arrowstyle="-", color="gray", lw=0.5, alpha=0.5) if (dx!=0 or dy!=0) else None)

def generate_side_by_side(old_gdf, new_gdf, districts_gdf, output_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))
    
    # OLD Map
    districts_gdf.boundary.plot(ax=ax1, color='black', linewidth=0.3, alpha=0.5)
    old_gdf.plot(ax=ax1, color='#1f77b4', alpha=0.6, label='OLD (FSI-like)')
    add_basemap(ax1, crs=old_gdf.crs)
    ax1.set_title("OLD Definition (FSI-like)", fontsize=16)
    ax1.axis('off')
    
    # NEW Map
    districts_gdf.boundary.plot(ax=ax2, color='black', linewidth=0.3, alpha=0.5)
    new_gdf.plot(ax=ax2, color='#ff7f0e', alpha=0.6, label='NEW (SC 2025)')
    add_basemap(ax2, crs=new_gdf.crs)
    ax2.set_title("NEW Definition (SC 2025)", fontsize=16)
    ax2.axis('off')
    
    # Stats
    old_area = old_gdf.area.sum() / 1e6
    new_area = new_gdf.area.sum() / 1e6
    
    plt.suptitle(f"Aravalli Delineation Comparison\nOLD: {old_area:,.0f} km²  vs  NEW: {new_area:,.0f} km²", fontsize=20)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    logger.info(f"Saved {output_path}")
    plt.close()

def generate_loss_map(old_gdf, new_gdf, districts_gdf, output_path):
    fig, ax = plt.subplots(figsize=(15, 15))
    
    # Difference (OLD - NEW) = Loss
    # Visualization trick: Plot OLD in Red, then Plot NEW on top in Green. 
    # Red areas visible are "Lost", Green are "Retained".
    
    districts_gdf.boundary.plot(ax=ax, color='black', linewidth=0.5, alpha=0.3)
    
    # Plot OLD as "Lost" (Base layer)
    old_gdf.plot(ax=ax, color='#d62728', alpha=0.7, label='Area Lost') # Red
    
    # Plot NEW as "Retained" (Top layer)
    new_gdf.plot(ax=ax, color='#2ca02c', alpha=0.9, label='Area Retained') # Green
    
    add_basemap(ax, crs=old_gdf.crs)
    
    # Labels
    fix_labels(ax, districts_gdf)
    
    # Legend
    red_patch = mpatches.Patch(color='#d62728', alpha=0.7, label='De-protected Area (Lost)')
    green_patch = mpatches.Patch(color='#2ca02c', alpha=0.9, label='Retained Area')
    ax.legend(handles=[red_patch, green_patch], loc='lower right', fontsize=12)
    
    ax.set_title("Aravalli Protection Loss Analysis\n(Red areas lose protection under NEW definition)", fontsize=18)
    ax.axis('off')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    logger.info(f"Saved {output_path}")
    plt.close()

def main():
    logger.info("Generating map variations...")
    output_dir = Path("outputs/aggregated_maps")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        old_gdf = gpd.read_file("outputs/all_districts_old.geojson")
        new_gdf = gpd.read_file("outputs/all_districts_new.geojson")
        
        # Load districts using our helper to get metadata names, but handle if script path differs
        # Manual load of dists for visualization names
        # We need a dataframe with 'district' column
        from aravalli.boundaries import load_district_boundaries
        districts_gdf = load_district_boundaries("data/districts.yml", confirmed_only=False) # Load ALL including additional
        
    except Exception as e:
        logger.error(f"Failed to load data: {e}")
        return

    # Projection
    crs = "EPSG:32643"
    if old_gdf.crs != crs: old_gdf = old_gdf.to_crs(crs)
    if new_gdf.crs != crs: new_gdf = new_gdf.to_crs(crs)
    if districts_gdf.crs != crs: districts_gdf = districts_gdf.to_crs(crs)

    # 1. Side by Side
    generate_side_by_side(old_gdf, new_gdf, districts_gdf, output_dir / "comparison_side_by_side.png")
    
    # 2. Loss Map (Difference)
    generate_loss_map(old_gdf, new_gdf, districts_gdf, output_dir / "comparison_loss_map.png")
    
    # 3. Overview V2 (Cleaned up Standard)
    fig, ax = plt.subplots(figsize=(20, 20)) # Larger figure for better resolution
    
    # Base districts
    districts_gdf.boundary.plot(ax=ax, color='#444444', linewidth=0.8, alpha=0.3, zorder=2)
    
    # Data Layers
    # OLD: Blue (classic/water storage metaphor)
    old_gdf.plot(ax=ax, color='#1f77b4', alpha=0.5, zorder=3, label='OLD (FSI-like)')
    # NEW: Orange (alert/change metaphor)
    new_gdf.plot(ax=ax, color='#ff7f0e', alpha=0.7, zorder=4, label='NEW (SC 2025)')
    
    # Basemap (Light gray for focus)
    add_basemap(ax, crs=crs, zoom=8)
    
    # Labels with leader lines
    fix_labels(ax, districts_gdf)
    
    # Legend
    blue_patch = mpatches.Patch(color='#1f77b4', alpha=0.5, label='OLD: Broader Definition (FSI-like)')
    orange_patch = mpatches.Patch(color='#ff7f0e', alpha=0.7, label='NEW: Restricted Definition (SC 2025)')
    
    # Custom Legend
    ax.legend(handles=[blue_patch, orange_patch], loc='upper right', fontsize=14, 
              frameon=True, fancybox=True, framealpha=0.9, title="Aravalli Delineation")
    
    # Scale Bar (Manual approximation for visual reference)
    # 1 degree approx 111km, but projected CRS is in meters. 
    # Let's add a simple annotation if ctx.add_scalebar isn't available
    
    ax.set_title("Aravalli Delineation: Aggregate Overview", fontsize=24, pad=20)
    ax.axis('off')
    
    plt.tight_layout()
    output_path = output_dir / "comparison_overview_v2.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    logger.info(f"Saved {output_path}")
    plt.close()
    
    # 4. Delhi Inset Map (Zoomed In)
    # Filter for Delhi and immediate neighbors
    delhi_ncr = ['New Delhi', 'South Delhi', 'South West Delhi', 'Central Delhi', 
                 'Gurugram', 'Faridabad', 'Nuh', 'Jhajjar', 'Rohtak', 'Sonipat', 'Ghaziabad', 'Gautam Buddha Nagar']
    
    col_name = 'name' if 'name' in districts_gdf.columns else 'district'
    delhi_gdf = districts_gdf[districts_gdf[col_name].isin(delhi_ncr)]
    
    if not delhi_gdf.empty:
        fig_d, ax_d = plt.subplots(figsize=(10, 10))
        
        # Clip to Delhi NCR bounding box
        minx, miny, maxx, maxy = delhi_gdf.total_bounds
        ax_d.set_xlim(minx - 5000, maxx + 5000)
        ax_d.set_ylim(miny - 5000, maxy + 5000)
        
        delhi_gdf.boundary.plot(ax=ax_d, color='black', linewidth=1, zorder=2)
        
        # Clip data to view
        old_clip = gpd.clip(old_gdf, delhi_gdf.envelope)
        new_clip = gpd.clip(new_gdf, delhi_gdf.envelope)
        
        old_clip.plot(ax=ax_d, color='#1f77b4', alpha=0.5, zorder=3)
        new_clip.plot(ax=ax_d, color='#ff7f0e', alpha=0.7, zorder=4)
        
        add_basemap(ax_d, crs=crs, zoom=10)
        
        # Simple Labels for Inset
        for idx, row in delhi_gdf.iterrows():
            lbl = row.get(col_name, '')
            ax_d.annotate(text=lbl, xy=(row.geometry.centroid.x, row.geometry.centroid.y),
                          ha='center', fontsize=8, fontweight='bold',
                          bbox=dict(boxstyle="round,pad=0.1", fc="white", alpha=0.6))
                          
        ax_d.set_title("Delhi NCR Detail", fontsize=16)
        ax_d.axis('off')
        
        plt.savefig(output_dir / "inset_delhi_ncr.png", dpi=300, bbox_inches='tight')
        logger.info(f"Saved {output_dir / 'inset_delhi_ncr.png'}")
        plt.close()


if __name__ == "__main__":
    main()
