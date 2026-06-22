#!/usr/bin/env python3
"""Fetch the elevation grid for a region in data/regions.json.

  source "noaa"      — NCEI DEM_all mosaic (CUDEM coastal topobathy, ~3 m, US)
  source "usgs"      — USGS 3DEP (all CONUS land; lakes appear as flat plates)
  source "terrarium" — AWS Terrain Tiles (GLOBAL, ~7 m/px at z14, no key)

Usage: python3 scripts/fetch_dem.py [region-name] [max_px]
Updates src_m_per_px in data/regions.json after download.
"""
import io, json, math, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image

REG_FILE = "data/regions.json"
cfg = json.load(open(REG_FILE))
name = sys.argv[1] if len(sys.argv) > 1 else cfg["active"]
max_px = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
reg = cfg["regions"][name]
minlon, minlat, maxlon, maxlat = reg["bbox"]
w_m = (maxlon - minlon) * 111320 * math.cos(math.radians((minlat + maxlat) / 2))
h_m = (maxlat - minlat) * 111320

if reg["source"] in ("noaa", "usgs"):
    import urllib.parse
    s = max_px / max(w_m, h_m)
    MIN_RES = 0.8   # m/px floor: finer than the source serves -> HTTP 500
    s = min(s, 1.0 / MIN_RES)
    W, H = max(1, round(w_m * s)), max(1, round(h_m * s))
    m_per_px = h_m / H
    HOSTS = {
        "noaa": "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_all/ImageServer/exportImage",
        "usgs": "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage",
    }
    # adjustAspectRatio is per-region so seeded boards reproduce the exact DEM
    # coverage they were calibrated against. Legacy boards default to true
    # (the server default they were built with); fresh golf courses use false
    # (exact bbox -> features align at identity).
    adj = "false" if reg.get("adjust_aspect") is False else "true"
    params = urllib.parse.urlencode({
        "bbox": f"{minlon},{minlat},{maxlon},{maxlat}", "bboxSR": "4326", "imageSR": "4326",
        "size": f"{W},{H}", "format": "tiff", "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation", "adjustAspectRatio": adj,
        "f": "image"})
    print(f"{name}: {w_m/1000:.1f} x {h_m/1000:.1f} km -> {W}x{H} ({m_per_px:.1f} m/px) from {reg['source']}")
    urllib.request.urlretrieve(HOSTS[reg["source"]] + "?" + params, reg["src_file"])

elif reg["source"] == "terrarium":
    lat_c = (minlat + maxlat) / 2
    for z in range(15, 8, -1):
        res = 40075016.686 * math.cos(math.radians(lat_c)) / (256 * 2 ** z)
        if max(w_m, h_m) / res <= max_px * 1.25:
            break
    n = 2 ** z * 256
    def merc(lon, lat):
        return ((lon + 180) / 360 * n,
                (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    x0, y0 = merc(minlon, maxlat); x1, y1 = merc(maxlon, minlat)
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    ntiles = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    print(f"{name}: terrarium z{z}, {ntiles} tiles, {res:.1f} m/px")
    mos = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), np.float64)
    def get(tile):
        tx, ty = tile
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{tx}/{ty}.png"
        a = np.array(Image.open(io.BytesIO(urllib.request.urlopen(url, timeout=90).read())), np.float64)
        mos[(ty - ty0) * 256:(ty - ty0 + 1) * 256,
            (tx - tx0) * 256:(tx - tx0 + 1) * 256] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(get, [(tx, ty) for tx in range(tx0, tx1 + 1) for ty in range(ty0, ty1 + 1)]))
    # resample web-mercator mosaic onto the pipeline's uniform lat/lon grid
    Wn, Hn = round(w_m / res), round(h_m / res)
    s = min(1.0, max_px / max(Wn, Hn))
    W, H = round(Wn * s), round(Hn * s)
    lons = np.linspace(minlon, maxlon, W)
    lats = np.linspace(maxlat, minlat, H)
    xs = (lons + 180) / 360 * n - tx0 * 256
    ys = (1 - np.arcsinh(np.tan(np.radians(lats))) / np.pi) / 2 * n - ty0 * 256
    from scipy.ndimage import map_coordinates
    XX, YY = np.meshgrid(xs, ys)
    a = map_coordinates(mos, [YY.ravel(), XX.ravel()], order=1).reshape(H, W)
    Image.fromarray(a.astype(np.float32)).save(reg["src_file"])
    m_per_px = h_m / H
    print(f"grid {W}x{H}, elev {a.min():.0f}..{a.max():.0f} m")
else:
    raise SystemExit(f"unknown source {reg['source']}")

reg["src_m_per_px"] = round(m_per_px, 3)
json.dump(cfg, open(REG_FILE, "w"), indent=1)
print(f"wrote {reg['src_file']} ({os.path.getsize(reg['src_file'])/1e6:.0f} MB), {m_per_px:.1f} m/px")
