"""
Batch Process Districts
=======================

Process each district separately for faster, more reliable results.
Includes progress tracking with tqdm.
"""

import subprocess
import sys
from pathlib import Path
from tqdm import tqdm
import yaml
import json
from datetime import datetime

# Read districts configuration
config_path = Path("data/districts.yml")
config = yaml.safe_load(config_path.read_text())

# Get confirmed districts from all states
all_districts = []
for state in ['haryana', 'rajasthan', 'gujarat', 'delhi']:
    if state in config:
        all_districts.extend(config[state])

# Filter to confirmed districts only
districts = [d for d in all_districts if d.get('confirmed', False)]
district_names = [d['name'] for d in districts]

print(f"\n{'='*60}")
print(f"ARAVALLI BATCH PROCESSING")
print(f"{'='*60}")
print(f"Total districts to process: {len(district_names)}")
print(f"Districts: {', '.join(district_names[:5])}...")
print(f"{'='*60}\n")

# Results tracking
results = {
    'start_time': datetime.now().isoformat(),
    'districts': {},
    'summary': {}
}

# Process each district with progress bar
for district in tqdm(district_names, desc="Overall progress", unit="district"):
    print(f"\n{'─'*60}")
    print(f"Processing: {district}")
    print(f"{'─'*60}")
    
    district_start = datetime.now()
    
    # Build command
    cmd = [
        sys.executable, "-m", "aravalli", "run",
        "--districts", "data/districts.yml",
        "--filter-districts", district,
        "--dem", "SRTM",
        "--method", "relief",
        "--output-dir", f"outputs/districts/{district}"
    ]
    
    try:
        # Run with real-time output
        result = subprocess.run(
            cmd,
            capture_output=False,
            text=True,
            check=True,
            env={**dict(subprocess.os.environ), 'PYTHONIOENCODING': 'utf-8'}
        )
        
        district_end = datetime.now()
        duration = (district_end - district_start).total_seconds()
        
        results['districts'][district] = {
            'status': 'success',
            'duration_seconds': duration,
            'output_dir': f"outputs/districts/{district}"
        }
        
        print(f"✓ {district} completed in {duration:.1f}s")
        
    except subprocess.CalledProcessError as e:
        district_end = datetime.now()
        duration = (district_end - district_start).total_seconds()
        
        results['districts'][district] = {
            'status': 'failed',
            'duration_seconds': duration,
            'error': str(e)
        }
        
        print(f"✗ {district} failed after {duration:.1f}s")
        print(f"  Error: {e}")
        
        # Continue with next district
        continue

# Save results
results['end_time'] = datetime.now().isoformat()
results['summary'] = {
    'total': len(district_names),
    'successful': sum(1 for d in results['districts'].values() if d['status'] == 'success'),
    'failed': sum(1 for d in results['districts'].values() if d['status'] == 'failed'),
    'total_duration_seconds': sum(d['duration_seconds'] for d in results['districts'].values())
}

output_dir = Path("outputs/batch_processing")
output_dir.mkdir(parents=True, exist_ok=True)

results_file = output_dir / f"batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
results_file.write_text(json.dumps(results, indent=2))

# Print summary
print(f"\n{'='*60}")
print(f"BATCH PROCESSING COMPLETE")
print(f"{'='*60}")
print(f"Total districts: {results['summary']['total']}")
print(f"Successful: {results['summary']['successful']}")
print(f"Failed: {results['summary']['failed']}")
print(f"Total time: {results['summary']['total_duration_seconds']/60:.1f} minutes")
print(f"\nResults saved to: {results_file}")
print(f"{'='*60}\n")

# Show failed districts if any
if results['summary']['failed'] > 0:
    print("\nFailed districts:")
    for district, info in results['districts'].items():
        if info['status'] == 'failed':
            print(f"  - {district}: {info.get('error', 'Unknown error')}")
