# SRTM Download Guide for Windows

Due to limitations with SRTM download tools on Windows, you have two options:

## Option 1: Use Pre-downloaded DEM (Recommended for Windows)

1. **Download SRTM tiles manually** from:
   - OpenTopography: https://portal.opentopography.org/raster?opentopoID=OTSRTM.082015.4326.1
   - USGS EarthExplorer: https://earthexplorer.usgs.gov/

2. **For Aravalli region**, you need tiles covering:
   - Haryana: N28E076, N28E077
   - Rajasthan: N25-N28, E073-E077 (depending on districts)
   - Gujarat: N23-N24, E072-E074

3. **Save tiles** to `data/cache/srtm_tiles/`

4. **Use custom DEM option**:
   ```bash
   python -m aravalli run --dem custom --dem-path path/to/your/dem.tif
   ```

## Option 2: Use WSL (Windows Subsystem for Linux)

If you have WSL installed:

```bash
# In WSL terminal
conda activate aravalli
python -m aravalli profile --start "28.45,77.02" --end "28.30,77.10"
```

## Option 3: Download Merged SRTM for India

1. Download pre-merged SRTM for India from:
   - https://dwtkns.com/srtm30m/
   - Select tiles covering 23°-30°N, 72°-78°E

2. Merge tiles using GDAL:
   ```bash
   gdal_merge.py -o india_srtm.tif N*.hgt
   ```

3. Use the merged file:
   ```bash
   python -m aravalli run --dem custom --dem-path india_srtm.tif
   ```

## Temporary Workaround

For testing, you can:

1. Run only the district listing:
   ```bash
   python -m aravalli list-districts
   python -m aravalli legal-status
   ```

2. Prepare a small DEM for your area of interest manually

3. Once you have a DEM file, the full pipeline will work

## Why This Happens

The `elevation` package uses Unix tools (`make`, `gdal`) that aren't available by default on Windows. Our Windows-compatible downloader attempts direct HTTP downloads, but SRTM servers sometimes have connectivity issues or require authentication.

## Future Fix

We're working on:
- Better Windows support with alternative download methods
- Integration with Google Earth Engine or other cloud DEM sources
- Pre-packaged DEM tiles for common regions
