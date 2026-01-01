"""
District Boundaries Module
==========================

Loads and manages district boundary data from:
- Official shapefiles (preferred)
- OSM Nominatim (fallback via osmnx)
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml
import geopandas as gpd
import osmnx as ox
from shapely.ops import unary_union
from shapely.geometry import shape

logger = logging.getLogger(__name__)


def load_district_boundaries(
    config_file: str,
    filter_districts: Optional[List[str]] = None,
    confirmed_only: bool = False,
    cache_dir: Optional[Path] = None
) -> gpd.GeoDataFrame:
    """
    Load district boundaries from configuration file.
    
    Args:
        config_file: Path to districts.yml configuration
        filter_districts: Optional list of district names to include
        confirmed_only: If True, only load confirmed districts
        cache_dir: Optional cache directory for downloaded boundaries
        
    Returns:
        GeoDataFrame with district polygons
    """
    # Load configuration
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    districts = []
    
    # Iterate through states
    for state_key, district_list in config.items():
        if state_key in ('metadata', 'config'):
            continue
        
        if not isinstance(district_list, list):
            continue
        
        for d in district_list:
            # Filter by confirmed status
            if confirmed_only and not d.get('confirmed', False):
                continue
            
            # Filter by name if specified
            if filter_districts and d['name'] not in filter_districts:
                continue
            
            districts.append({
                'name': d['name'],
                'state': d['state'],
                'confirmed': d.get('confirmed', False),
                'source': d.get('source', 'Unknown'),
                'osm_query': d.get('osm_query'),
                'boundary_file': d.get('boundary_file'),
            })
    
    if not districts:
        logger.warning("No districts matched the filter criteria")
        return gpd.GeoDataFrame()
    
    # Load geometries
    geometries = []
    records = []
    
    for d in districts:
        geom = None
        
        # Try official boundary file first
        if d['boundary_file']:
            try:
                geom = _load_from_shapefile(d['boundary_file'])
                logger.info(f"  Loaded official boundary for {d['name']}")
            except Exception as e:
                logger.warning(f"  Could not load shapefile for {d['name']}: {e}")
        
        # Fallback to OSM
        if geom is None and d['osm_query']:
            try:
                geom = _load_from_osm(d['osm_query'], cache_dir)
                logger.info(f"  Loaded OSM boundary for {d['name']}")
            except Exception as e:
                logger.warning(f"  Could not load OSM boundary for {d['name']}: {e}")
        
        if geom is not None:
            geometries.append(geom)
            records.append({
                'name': d['name'],
                'state': d['state'],
                'confirmed': d['confirmed'],
                'source': d['source'],
            })
        else:
            logger.error(f"  Failed to load boundary for {d['name']} - skipping")
    
    if not geometries:
        return gpd.GeoDataFrame()
    
    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")
    
    return gdf


def _load_from_shapefile(filepath: str) -> Optional[Any]:
    """Load geometry from a shapefile."""
    gdf = gpd.read_file(filepath)
    if gdf.empty:
        return None
    # Dissolve if multiple features
    return unary_union(gdf.geometry)


def _load_from_osm(query: str, cache_dir: Optional[Path] = None) -> Optional[Any]:
    """
    Load boundary geometry from OSM via Nominatim.
    
    Uses osmnx to geocode the place name.
    """
    try:
        gdf = ox.geocode_to_gdf(query)
        if gdf.empty:
            return None
        return gdf.geometry.iloc[0]
    except Exception as e:
        logger.debug(f"OSM geocoding failed for '{query}': {e}")
        return None


def get_district_list(config_file: str) -> List[Dict[str, Any]]:
    """
    Get a list of all configured districts.
    
    Args:
        config_file: Path to districts.yml
        
    Returns:
        List of district dictionaries
    """
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    districts = []
    
    for state_key, district_list in config.items():
        if state_key in ('metadata', 'config'):
            continue
        
        if not isinstance(district_list, list):
            continue
        
        for d in district_list:
            districts.append({
                'name': d['name'],
                'state': d['state'],
                'confirmed': d.get('confirmed', False),
                'source': d.get('source', 'Unknown'),
            })
    
    return districts
