#!/usr/bin/env python3
"""Fetch the elevation grid for a region config.

  source "noaa" — NCEI DEM_all mosaic (CUDEM coastal topobathy, ~3 m)
  source "usgs" — USGS 3DEP (all CONUS land; lakes appear as flat plates)

Usage: python3 scripts/fetch_dem.py [data/region.json] [max_px]
Updates src_m_per_px in the region file after download.
"""
import json, math, sys, urllib.request, urllib.parse

path = sys.argv[1] if len(sys.argv) > 1 else "data/region.json"
max_px = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
reg = json.load(open(path))
minlon, minlat, maxlon, maxlat = reg["bbox"]

w_m = (maxlon - minlon) * 111320 * math.cos(math.radians((minlat + maxlat) / 2))
h_m = (maxlat - minlat) * 111320
s = max_px / max(w_m, h_m)
W, H = round(w_m * s), round(h_m * s)
m_per_px = h_m / H

HOSTS = {
    "noaa": "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_all/ImageServer/exportImage",
    "usgs": "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage",
}
params = urllib.parse.urlencode({
    "bbox": f"{minlon},{minlat},{maxlon},{maxlat}", "bboxSR": "4326", "imageSR": "4326",
    "size": f"{W},{H}", "format": "tiff", "pixelType": "F32",
    "interpolation": "RSP_BilinearInterpolation", "f": "image"})
url = HOSTS[reg["source"]] + "?" + params
print(f"{reg['name']}: {w_m/1000:.1f} x {h_m/1000:.1f} km -> {W}x{H} ({m_per_px:.1f} m/px) from {reg['source']}")
urllib.request.urlretrieve(url, reg["src_file"])
reg["src_m_per_px"] = round(m_per_px, 3)
json.dump(reg, open(path, "w"), indent=1)
import os
print(f"wrote {reg['src_file']} ({os.path.getsize(reg['src_file'])/1e6:.0f} MB)")
