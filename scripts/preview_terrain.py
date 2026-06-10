#!/usr/bin/env python3
"""Render a colored hillshade preview of a GMRT topobathy GeoTIFF so we can
eyeball the bounding box / geography before building board geometry on it.

Usage: python3 scripts/preview_terrain.py [tif] [out.png]
"""
import sys, math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

Image.MAX_IMAGE_PIXELS = None

TIF = sys.argv[1] if len(sys.argv) > 1 else "data/deerisle_gmrt.tif"
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/deerisle_preview.png"

# bbox the GMRT grid was requested with (lon/lat)
MINLON, MAXLON, MINLAT, MAXLAT = -68.75, -68.55, 44.13, 44.32

# approximate landmarks to sanity-check geography (lon, lat, label)
LANDMARKS = [
    (-68.667, 44.157, "Stonington"),
    (-68.677, 44.224, "Deer Isle village"),
    (-68.621, 44.272, "Deer Isle Bridge"),
    (-68.640, 44.295, "Little Deer Isle"),
    (-68.620, 44.305, "Sedgwick (mainland)"),
]

a = np.array(Image.open(TIF), dtype=np.float64)
a = np.where(np.isnan(a), -50.0, a)        # nodata -> deep water for preview
H, W = a.shape
land = a > 0

# meters/px for hillshade gradient
midlat = (MINLAT + MAXLAT) / 2
mpp_lat = (MAXLAT - MINLAT) * 111320 / H
mpp_lon = (MAXLON - MINLON) * 111320 * math.cos(math.radians(midlat)) / W

az, alt = math.radians(315), math.radians(45)
gy, gx = np.gradient(a, mpp_lat, mpp_lon)
slope = np.arctan(np.hypot(gx, gy))
aspect = np.arctan2(-gx, gy)
hs = np.clip(np.sin(alt) * np.cos(slope) +
             np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)

img = np.zeros((H, W, 3), np.float64)
depth = np.clip(-a, 0, 80) / 80.0
img[~land] = np.stack([0.04 + 0.10 * (1 - depth),
                       0.18 + 0.35 * (1 - depth),
                       0.35 + 0.45 * (1 - depth)], -1)[~land]
e = np.clip(a, 0, 123) / 123.0
lc = np.stack([0.30 + 0.55 * e, 0.55 - 0.15 * e, 0.30 - 0.10 * e], -1)
img[land] = lc[land]
img[land] *= (0.45 + 0.75 * hs[land])[:, None]

# coastline = boundary of land mask
edge = land ^ ndimage.binary_erosion(land)
img[edge] = [1.0, 0.95, 0.2]

pim = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
scale = max(1, 1400 // W)
pim = pim.resize((W * scale, H * scale), Image.NEAREST)
draw = ImageDraw.Draw(pim)

def to_px(lon, lat):
    x = (lon - MINLON) / (MAXLON - MINLON) * W * scale
    y = (MAXLAT - lat) / (MAXLAT - MINLAT) * H * scale
    return x, y

for lon, lat, label in LANDMARKS:
    x, y = to_px(lon, lat)
    r = 5
    draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 60, 60), outline=(0, 0, 0))
    draw.text((x + 8, y - 6), label, fill=(255, 255, 255))

pim.save(OUT)
print("wrote", OUT, pim.size)
