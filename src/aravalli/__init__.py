"""
Aravalli Range Delineation Comparison Tool
==========================================

A reproducible Python toolkit for comparing:
- OLD (FSI-like) Aravalli delineation
- NEW (20-Nov-2025 SC judgment) operational definition

**IMPORTANT LEGAL STATUS:**
The NEW definition was kept in abeyance on 29-Dec-2025 by Supreme Court order.
A high-powered committee has been constituted for reassessment.

Author: [Your Name/Organization]
License: MIT
Version: 0.1.0
"""

__version__ = "0.1.0"
__author__ = "Aravalli Research Team"

# Legal status constants
LEGAL_STATUS = {
    "new_definition_status": "IN_ABEYANCE",
    "abeyance_date": "2025-12-29",
    "abeyance_order": "SC Order dated 29-Dec-2025",
    "operative_definition": "FSI-2010",
    "new_definition_source": "SC Judgment dated 20-Nov-2025",
}

# Default parameters
DEFAULT_PARAMS = {
    # OLD (FSI-like) definition parameters
    "slope_threshold_deg": 3.0,
    "foothill_buffer_m": 100,
    "gap_bridge_m": 500,
    
    # NEW (2025) definition parameters
    "relief_threshold_m": 100,
    "range_proximity_m": 500,
    "local_relief_radius_m": 2000,
    "contour_interval_m": 10,
}

from .core import run_analysis
from .cli import main

__all__ = [
    "run_analysis",
    "main",
    "__version__",
    "LEGAL_STATUS",
    "DEFAULT_PARAMS",
]
