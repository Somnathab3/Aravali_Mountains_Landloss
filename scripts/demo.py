#!/usr/bin/env python
"""
Quick Demo Script
=================

Runs a quick demo of the Aravalli delineation tool on a small area.

Usage:
    python scripts/demo.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main():
    """Run quick demo."""
    print("=" * 60)
    print("ARAVALLI DELINEATION DEMO")
    print("=" * 60)
    print()
    print("⚠️  LEGAL STATUS: NEW definition is IN ABEYANCE")
    print("   (SC order 29-Dec-2025)")
    print()
    
    # Run with a subset of districts
    from aravalli import run_analysis
    
    config = {
        'districts_file': 'data/districts.yml',
        'dem_source': 'SRTM',
        'dem_path': None,
        'method': 'relief',
        'relief_radius_m': 2000,
        'contour_interval_m': 10,
        'slope_threshold_deg': 3.0,
        'foothill_buffer_m': 100,
        'gap_bridge_m': 500,
        'enable_tiling': False,
        'tile_size_m': 10000,
        'output_dir': 'outputs',
        'cache_dir': 'data/cache',
        'district_filter': ['Gurugram', 'Faridabad', 'Nuh'],  # Subset
        'confirmed_only': False,
    }
    
    print("Running demo with districts: Gurugram, Faridabad, Nuh")
    print()
    
    try:
        results = run_analysis(config)
        
        print()
        print("=" * 60)
        print("DEMO COMPLETE")
        print("=" * 60)
        print(f"OLD area: {results['old_area_km2']:.2f} km²")
        print(f"NEW area: {results['new_area_km2']:.2f} km²")
        print()
        print("Outputs saved to: outputs/")
        
    except Exception as e:
        print(f"Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
