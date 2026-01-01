#!/usr/bin/env python3
"""
Generate district-by-district analysis cards for README.md

Reads outputs/all_districts_summary.csv and generates an HTML table grid
with scientific formatting (units, proper precision) for each district.

Output: docs/district_cards.md (to be copy-pasted into README)

Usage:
    python scripts/generate_district_cards.py
"""

import os
import csv
from pathlib import Path


def main():
    # Paths
    repo_root = Path(__file__).parent.parent
    csv_path = repo_root / "outputs" / "all_districts_summary.csv"
    output_path = repo_root / "docs" / "district_cards.md"
    
    # Create docs directory if needed
    output_path.parent.mkdir(exist_ok=True)
    
    # Read CSV
    print(f"Reading: {csv_path}")
    districts = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            districts.append(row)
    
    print(f"Found {len(districts)} districts")
    
    # Sort by absolute area lost (most significant first)
    districts.sort(key=lambda d: float(d['Change_km2']), reverse=False)  # Most negative first
    
    # Validate map files exist and determine which filename to use
    missing_maps = []
    district_map_files = {}  # Store actual filename for each district
    
    for district in districts:
        district_name = district['District']
        overview_path = repo_root / "outputs" / "districts" / district_name / "maps" / "comparison_overview.png"
        overlay_path = repo_root / "outputs" / "districts" / district_name / "maps" / "comparison_overlay.png"
        
        if overview_path.exists():
            district_map_files[district_name] = "comparison_overview.png"
        elif overlay_path.exists():
            district_map_files[district_name] = "comparison_overlay.png"
        else:
            missing_maps.append(district_name)
    
    if missing_maps:
        print(f"⚠️  Warning: Missing maps for {len(missing_maps)} districts:")
        for name in missing_maps:
            print(f"   - {name}")
    
    # Generate markdown content
    lines = []
    lines.append("## District-by-District Analysis\n")
    lines.append("**Sorted by area lost** (most significant changes first). All areas in km², computed in UTM projected CRS.\n")
    lines.append("Click on any map thumbnail to view full-resolution comparison.\n")
    
    # Generate cards in rows of 3
    lines.append("<table>")
    
    for i, district in enumerate(districts):
        # Start new row every 3 districts
        if i % 3 == 0:
            if i > 0:
                lines.append("  </tr>")
            lines.append("  <tr>")
        
        # Extract data
        name = district['District']
        state = district['State']
        district_area = float(district['District_Area_km2'])
        old_area = float(district['OLD_Area_km2'])
        new_area = float(district['NEW_Area_km2'])
        change = float(district['Change_km2'])
        change_pct = float(district['Change_pct'])
        old_pct = float(district['OLD_pct_of_District'])
        new_pct = float(district['NEW_pct_of_District'])
        
        # Generate relative path for image (use determined filename or fallback)
        map_filename = district_map_files.get(name, "comparison_overview.png")
        img_path = f"outputs/districts/{name}/maps/{map_filename}"
        
        # Card content
        card = f"""    <td width="33%" valign="top">
      <b>{name}</b> ({state})<br/>
      <small>District area: {district_area:.1f} km²</small><br/>
      <br/>
      <b>OLD:</b> {old_area:.1f} km² ({old_pct:.1f}%)<br/>
      <b>NEW:</b> {new_area:.1f} km² ({new_pct:.1f}%)<br/>
      <b>Δ:</b> {change:.1f} km² ({change_pct:+.1f}%)<br/>
      <br/>
      <a href="{img_path}">
        <img src="{img_path}" width="300" alt="{name} comparison"/>
      </a>
    </td>"""
        
        lines.append(card)
    
    # Close final row and table
    lines.append("  </tr>")
    lines.append("</table>")
    
    # Add explanation
    lines.append("\n### Legend\n")
    lines.append("- **District area**: Total administrative area\n")
    lines.append("- **OLD**: FSI-2010-like delineation (slope > 3° + buffers)\n")
    lines.append("- **NEW**: SC 20-Nov-2025 definition (≥100 m local relief)\n")
    lines.append("- **Δ**: Change from OLD to NEW (negative = area lost)\n")
    lines.append("- **Percentages**: Share of total district area classified as Aravalli\n")
    
    # Write output
    content = "\n".join(lines)
    output_path.write_text(content, encoding='utf-8')
    
    print(f"\n✓ Generated: {output_path}")
    print(f"  - {len(districts)} districts in {(len(districts) + 2) // 3} rows")
    print(f"  - {len(missing_maps)} missing maps")
    print("\nNext step: Copy content from docs/district_cards.md into README.md Section 8.2")


if __name__ == "__main__":
    main()
