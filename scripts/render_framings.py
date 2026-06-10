#!/usr/bin/env python3
"""Crop framing options from the full-res CUDEM grid and render hillshade
previews so we can choose the board extent visually."""
import math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

Image.MAX_IMAGE_PIXELS = None

SRC = "data/deerisle_cudem.tif"
# bbox the full grid covers (lon/lat)
FMINLON, FMAXLON, FMINLAT, FMAXLAT = -68.75, -68.55, 44.13, 44.32

LANDMARKS = [
    (-68.667, 44.157, "Stonington"),
    (-68.677, 44.224, "Deer Isle village"),
    (-68.621, 44.272, "Deer Isle Bridge"),
    (-68.640, 44.292, "Little Deer Isle"),
    (-68.612, 44.308, "Sedgwick"),
]

# framing -> (minlon, maxlon, minlat, maxlat)
FRAMINGS = {
    "A_full":            (-68.75,  -68.55,  44.13,  44.32),
    "B_islands_mainland":(-68.715, -68.585, 44.150, 44.318),
    "C_two_islands":     (-68.705, -68.595, 44.150, 44.293),
}

full = np.array(Image.open(SRC), dtype=np.float64)
full = np.where(full < -1e30, np.nan, full)
FH, FW = full.shape


def lonlat_to_full_px(lon, lat):
    x = (lon - FMINLON) / (FMAXLON - FMINLON) * FW
    y = (FMAXLAT - lat) / (FMAXLAT - FMINLAT) * FH
    return x, y


def render(name, bbox):
    minlon, maxlon, minlat, maxlat = bbox
    x0, y0 = lonlat_to_full_px(minlon, maxlat)   # top-left
    x1, y1 = lonlat_to_full_px(maxlon, minlat)   # bottom-right
    x0, x1 = int(round(x0)), int(round(x1))
    y0, y1 = int(round(y0)), int(round(y1))
    a = full[y0:y1, x0:x1].copy()
    a = np.where(np.isnan(a), -50.0, a)
    H, W = a.shape
    land = a > 0

    midlat = (minlat + maxlat) / 2
    mpp_lat = (maxlat - minlat) * 111320 / H
    mpp_lon = (maxlon - minlon) * 111320 * math.cos(math.radians(midlat)) / W
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
    emax = max(1.0, a[land].max()) if land.any() else 1.0
    e = np.clip(a, 0, emax) / emax
    lc = np.stack([0.30 + 0.55 * e, 0.55 - 0.15 * e, 0.30 - 0.10 * e], -1)
    img[land] = lc[land]
    img[land] *= (0.45 + 0.75 * hs[land])[:, None]
    edge = land ^ ndimage.binary_erosion(land)
    img[edge] = [1.0, 0.95, 0.2]

    pim = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    scale = max(1, 900 // W)
    if scale > 1:
        pim = pim.resize((W * scale, H * scale), Image.NEAREST)
    else:
        sc = 900 / W
        pim = pim.resize((int(W * sc), int(H * sc)), Image.LANCZOS)
        scale = sc
    draw = ImageDraw.Draw(pim)
    for lon, lat, label in LANDMARKS:
        if not (minlon <= lon <= maxlon and minlat <= lat <= maxlat):
            continue
        px = (lon - minlon) / (maxlon - minlon) * pim.size[0]
        py = (maxlat - lat) / (maxlat - minlat) * pim.size[1]
        r = 5
        draw.ellipse([px - r, py - r, px + r, py + r], fill=(255, 60, 60), outline=(0, 0, 0))
        draw.text((px + 8, py - 6), label, fill=(255, 255, 255))
    out = f"data/framing_{name}.png"
    pim.save(out)
    print(f"{name}: crop {W}x{H}px @ ~{mpp_lon:.1f} m/px  land {100*land.sum()/a.size:.0f}%  -> {out}")


for name, bbox in FRAMINGS.items():
    render(name, bbox)
