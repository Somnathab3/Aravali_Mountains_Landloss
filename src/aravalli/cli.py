"""
Command Line Interface for Aravalli Delineation Tool
=====================================================

Provides CLI commands for running analysis and generating outputs.

Usage:
    python -m aravalli run --districts data/districts.yml --dem SRTM
    python -m aravalli profile --start "28.45,77.02" --end "28.30,77.10"
"""

import click
from pathlib import Path
from typing import Optional
import logging
from rich.console import Console
from rich.logging import RichHandler

from . import __version__, LEGAL_STATUS

console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger(__name__)


def print_legal_notice():
    """Print legal status notice."""
    console.print("\n[bold yellow]⚠️  LEGAL STATUS NOTICE[/bold yellow]")
    console.print(f"[yellow]The NEW definition (SC 20-Nov-2025) is: [bold]{LEGAL_STATUS['new_definition_status']}[/bold][/yellow]")
    console.print(f"[yellow]Abeyance Order: {LEGAL_STATUS['abeyance_order']}[/yellow]")
    console.print(f"[yellow]Operative Definition: {LEGAL_STATUS['operative_definition']}[/yellow]\n")


@click.group()
@click.version_option(version=__version__)
def main():
    """
    Aravalli Range Delineation Comparison Tool
    
    Compares OLD (FSI-like) and NEW (20-Nov-2025) Aravalli definitions
    and produces maps + quantitative summaries.
    
    IMPORTANT: The NEW definition is IN ABEYANCE per SC order 29-Dec-2025.
    """
    pass


@main.command()
@click.option(
    "--districts", "-d",
    type=click.Path(exists=True),
    default="data/districts.yml",
    help="Path to districts YAML configuration file"
)
@click.option(
    "--dem",
    type=click.Choice(["SRTM", "custom"]),
    default="SRTM",
    help="DEM source: SRTM (auto-download) or custom (provide path)"
)
@click.option(
    "--dem-path",
    type=click.Path(exists=True),
    default=None,
    help="Path to custom DEM GeoTIFF (required if --dem=custom)"
)
@click.option(
    "--method", "-m",
    type=click.Choice(["relief", "contour"]),
    default="relief",
    help="Method for NEW definition: relief (quick) or contour (accurate)"
)
@click.option(
    "--relief-radius",
    type=int,
    default=2000,
    help="Radius in meters for local relief filter (default: 2000)"
)
@click.option(
    "--contour-interval",
    type=int,
    default=10,
    help="Contour interval in meters for contour method (default: 10)"
)
@click.option(
    "--slope-threshold",
    type=float,
    default=3.0,
    help="Slope threshold in degrees for OLD method (default: 3.0)"
)
@click.option(
    "--foothill-buffer",
    type=int,
    default=100,
    help="Foothill buffer in meters for OLD method (default: 100)"
)
@click.option(
    "--gap-bridge",
    type=int,
    default=500,
    help="Gap bridging distance in meters (default: 500)"
)
@click.option(
    "--enable-tiling",
    is_flag=True,
    default=False,
    help="Enable tiled processing for large AOIs"
)
@click.option(
    "--tile-size",
    type=int,
    default=10000,
    help="Tile size in meters when tiling is enabled (default: 10000)"
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(),
    default="outputs",
    help="Output directory (default: outputs/)"
)
@click.option(
    "--cache-dir",
    type=click.Path(),
    default="data/cache",
    help="Cache directory for DEM clips (default: data/cache/)"
)
@click.option(
    "--filter-districts",
    type=str,
    default=None,
    help="Comma-separated list of districts to process (default: all)"
)
@click.option(
    "--confirmed-only",
    is_flag=True,
    default=False,
    help="Process only confirmed districts (Haryana 7)"
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Enable verbose output"
)
def run(
    districts: str,
    dem: str,
    dem_path: Optional[str],
    method: str,
    relief_radius: int,
    contour_interval: int,
    slope_threshold: float,
    foothill_buffer: int,
    gap_bridge: int,
    enable_tiling: bool,
    tile_size: int,
    output_dir: str,
    cache_dir: str,
    filter_districts: Optional[str],
    confirmed_only: bool,
    verbose: bool
):
    """
    Run the Aravalli delineation comparison analysis.
    
    Generates OLD (FSI-like) and NEW (20-Nov-2025) delineation layers,
    comparison maps, and statistical summaries.
    
    Example:
    
        python -m aravalli run --districts data/districts.yml --dem SRTM
        
        python -m aravalli run --method contour --contour-interval 10
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Print legal notice
    print_legal_notice()
    
    # Validate options
    if dem == "custom" and dem_path is None:
        raise click.UsageError("--dem-path is required when --dem=custom")
    
    # Parse filter districts
    district_filter = None
    if filter_districts:
        district_filter = [d.strip() for d in filter_districts.split(",")]
    
    # Create output directories
    output_path = Path(output_dir)
    cache_path = Path(cache_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "maps").mkdir(exist_ok=True)
    (output_path / "tables").mkdir(exist_ok=True)
    cache_path.mkdir(parents=True, exist_ok=True)
    
    console.print("[bold green]Starting Aravalli Delineation Analysis[/bold green]")
    console.print(f"  Districts config: {districts}")
    console.print(f"  DEM source: {dem}")
    console.print(f"  Method: {method}")
    console.print(f"  Output directory: {output_dir}")
    
    # Build configuration
    config = {
        "districts_file": districts,
        "dem_source": dem,
        "dem_path": dem_path,
        "method": method,
        "relief_radius_m": relief_radius,
        "contour_interval_m": contour_interval,
        "slope_threshold_deg": slope_threshold,
        "foothill_buffer_m": foothill_buffer,
        "gap_bridge_m": gap_bridge,
        "enable_tiling": enable_tiling,
        "tile_size_m": tile_size,
        "output_dir": str(output_path),
        "cache_dir": str(cache_path),
        "district_filter": district_filter,
        "confirmed_only": confirmed_only,
    }
    
    # Run analysis
    try:
        from .core import run_analysis
        results = run_analysis(config)
        
        console.print("\n[bold green]✓ Analysis complete![/bold green]")
        console.print(f"  OLD layer area: {results.get('old_area_km2', 'N/A'):.2f} km²")
        console.print(f"  NEW layer area: {results.get('new_area_km2', 'N/A'):.2f} km²")
        console.print(f"  Outputs saved to: {output_dir}/")
        
    except Exception as e:
        console.print(f"\n[bold red]✗ Analysis failed: {e}[/bold red]")
        if verbose:
            import traceback
            traceback.print_exc()
        raise click.Abort()


@main.command()
@click.option(
    "--start",
    type=str,
    required=True,
    help="Start point as 'lat,lon' (e.g., '28.45,77.02')"
)
@click.option(
    "--end",
    type=str,
    required=True,
    help="End point as 'lat,lon' (e.g., '28.30,77.10')"
)
@click.option(
    "--dem",
    type=click.Choice(["SRTM", "custom"]),
    default="SRTM",
    help="DEM source"
)
@click.option(
    "--dem-path",
    type=click.Path(exists=True),
    default=None,
    help="Path to custom DEM GeoTIFF"
)
@click.option(
    "--step",
    type=int,
    default=100,
    help="Sampling step in meters (default: 100)"
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    default="outputs/maps/elevation_profile.png",
    help="Output file path for profile plot"
)
def profile(
    start: str,
    end: str,
    dem: str,
    dem_path: Optional[str],
    step: int,
    output: str
):
    """
    Generate an elevation profile along a transect.
    
    Example:
    
        python -m aravalli profile --start "28.45,77.02" --end "28.30,77.10"
    """
    try:
        start_lat, start_lon = map(float, start.split(","))
        end_lat, end_lon = map(float, end.split(","))
    except ValueError:
        raise click.UsageError("Coordinates must be in 'lat,lon' format")
    
    console.print(f"[bold]Generating elevation profile[/bold]")
    console.print(f"  Start: ({start_lat}, {start_lon})")
    console.print(f"  End: ({end_lat}, {end_lon})")
    console.print(f"  Step: {step} m")
    
    try:
        from .elevation import generate_elevation_profile
        
        profile_data = generate_elevation_profile(
            start_point=(start_lat, start_lon),
            end_point=(end_lat, end_lon),
            dem_source=dem,
            dem_path=dem_path,
            step_m=step,
            output_path=output
        )
        
        console.print(f"\n[bold green]✓ Profile saved to: {output}[/bold green]")
        console.print(f"  Distance: {profile_data['distance_km']:.2f} km")
        console.print(f"  Elevation range: {profile_data['min_elev']:.0f} - {profile_data['max_elev']:.0f} m")
        
    except Exception as e:
        console.print(f"\n[bold red]✗ Profile generation failed: {e}[/bold red]")
        raise click.Abort()


@main.command()
@click.option(
    "--districts", "-d",
    type=click.Path(exists=True),
    default="data/districts.yml",
    help="Path to districts YAML file"
)
def list_districts(districts: str):
    """
    List all configured districts and their status.
    """
    import yaml
    
    with open(districts, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    console.print("\n[bold]Configured Aravalli Districts[/bold]\n")
    
    confirmed_count = 0
    pending_count = 0
    
    for state, district_list in config.items():
        if state in ('metadata', 'config', 'summary'):
            continue
        
        # Skip if not a list
        if not isinstance(district_list, list):
            continue
            
        console.print(f"[bold cyan]{state.upper()}[/bold cyan]")
        
        for d in district_list:
            # Ensure d is a dictionary
            if not isinstance(d, dict):
                continue
                
            status = "✓" if d.get('confirmed', False) else "○"
            color = "green" if d.get('confirmed', False) else "yellow"
            console.print(f"  [{color}]{status}[/{color}] {d['name']}")
            
            if d.get('confirmed', False):
                confirmed_count += 1
            else:
                pending_count += 1
        
        console.print()
    
    console.print(f"[bold]Summary:[/bold] {confirmed_count} confirmed, {pending_count} pending verification")


@main.command()
def legal_status():
    """
    Display current legal status of Aravalli definitions.
    """
    console.print("\n[bold]Aravalli Delineation Legal Status[/bold]")
    console.print("=" * 50)
    
    console.print(f"\n[bold]NEW Definition (SC 20-Nov-2025):[/bold]")
    console.print(f"  Status: [bold yellow]{LEGAL_STATUS['new_definition_status']}[/bold yellow]")
    console.print(f"  Source: {LEGAL_STATUS['new_definition_source']}")
    console.print(f"  Abeyance Date: {LEGAL_STATUS['abeyance_date']}")
    console.print(f"  Abeyance Order: {LEGAL_STATUS['abeyance_order']}")
    
    console.print(f"\n[bold]Operative Definition:[/bold]")
    console.print(f"  {LEGAL_STATUS['operative_definition']}")
    console.print(f"  (Continues to apply for mining activities)")
    
    console.print("\n[bold]Definition Parameters:[/bold]")
    console.print("  [cyan]OLD (FSI-like):[/cyan]")
    console.print("    - Slope threshold: > 3°")
    console.print("    - Foothill buffer: 100 m")
    console.print("    - Gap bridging: 500 m")
    
    console.print("  [cyan]NEW (20-Nov-2025, IN ABEYANCE):[/cyan]")
    console.print("    - Relief threshold: ≥ 100 m from local relief")
    console.print("    - Local relief: lowest contour encircling landform")
    console.print("    - Range proximity: 500 m")
    
    console.print("\n[dim]For full legal context, see README.md[/dim]\n")


if __name__ == "__main__":
    main()
