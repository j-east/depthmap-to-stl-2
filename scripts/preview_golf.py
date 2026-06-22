#!/usr/bin/env python3
"""Colored preview of a golf region: turf features draped over a hillshade of
the real terrain. Writes data/board_preview.png (+ route_prototype.png for the
editor)."""
import json, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

Image.MAX_IMAGE_PIXELS = None

cfg = json.load(open("data/regions.json"))
ACTIVE = cfg["active"]
reg = cfg["regions"][ACTIVE]
MINLON, MINLAT, MAXLON, MAXLAT = reg["bbox"]
M_SRC = reg["src_m_per_px"]
from golf_common import transform_golf, hole_outline_mask, board_frame, merge_extra
g = transform_golf(merge_extra(json.load(open(f"data/golf_{ACTIVE}.json")), ACTIVE), reg)

dem = np.array(Image.open(reg["src_file"]), dtype=np.float64)
dem = np.where(dem < -1e30, np.nan, dem)
dem = np.where(np.isnan(dem), np.nanmedian(dem), dem)
DH, DW = dem.shape

# rotated board frame, resampled to a board-aligned hillshade
FR = board_frame(reg, g)
BW, BH = FR["BW"], FR["BH"]
PR = 0.2  # preview pitch (mm)
W, H = int(BW / PR), int(BH / PR)
gx_mm, gy_mm = np.meshgrid(np.arange(W) * PR, np.arange(H) * PR)
glon, glat = FR["mm_to_ll"](gx_mm, BH - gy_mm)
dc = np.clip(((glon - MINLON) / (MAXLON - MINLON) * (DW - 1)).astype(int), 0, DW - 1)
dr = np.clip(((MAXLAT - glat) / (MAXLAT - MINLAT) * (DH - 1)).astype(int), 0, DH - 1)
a = dem[dr, dc]

# layer paint order (back to front) and colors
COLORS = {
    "fairway": (150, 200, 104),
    "tee":     (150, 200, 104),
    "water":   (64, 132, 196),
    "bunker":  (238, 222, 170),
    "green":   (198, 226, 128),
}
ORDER = ["fairway", "tee", "water", "bunker", "green"]

# base = rough, hillshaded (gradient in board mm)
gy, gx = np.gradient(a)
slope = np.arctan(np.hypot(gx, gy) / (PR / FR["mm_per_m"]))
aspect = np.arctan2(-gx, gy)
az, alt = math.radians(315), math.radians(45)
hs = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
base = np.array([74, 116, 64])  # rough green (darker so mown turf pops)
img = (base[None, None, :] * (0.6 + 0.5 * hs)[..., None]).clip(0, 255).astype(np.uint8)
pim = Image.fromarray(img)
draw = ImageDraw.Draw(pim, "RGBA")

def to_px(lon, lat):
    x_mm, y_mm = FR["to_mm"](lon, lat)
    return float(x_mm) / PR, (BH - float(y_mm)) / PR

# satellite-detected fairway, painted under the OSM polygons
import os as _os
_fwp = f"data/fwmask_{ACTIVE}.png"
if _os.path.exists(_fwp):
    fwm = np.array(Image.open(_fwp).resize((W, H), Image.NEAREST)) > 127
    fimg = np.array(pim); fimg[fwm] = COLORS["fairway"]; pim = Image.fromarray(fimg)
    draw = ImageDraw.Draw(pim, "RGBA")

# semi-transparent turf so the hillshade (rail embankment, brook channel,
# leveled green pads) reads through it for alignment
TURF_A = 205
for layer in ORDER:
    for f in g["features"].get(layer, []):
        pts = [to_px(lon, lat) for lon, lat in f["pts"]]
        if len(pts) >= 3:
            draw.polygon(pts, fill=COLORS[layer] + (TURF_A,))

# paths, roads, railway
PATHCOL = {"cartpath": (224, 214, 188, 255), "road": (96, 96, 100, 255),
           "footway": (210, 196, 170, 200), "rail": (132, 86, 60, 255)}
PATHW = {"cartpath": 0.9, "road": 1.0, "footway": 0.7, "rail": 1.5}
for name, items in g.get("paths", {}).items():
    wpx = max(1, int(PATHW.get(name, 1.0) / PR))
    for p in items:
        pts = [to_px(lon, lat) for lon, lat in p["pts"]]
        if len(pts) >= 2:
            draw.line(pts, fill=PATHCOL.get(name, (120, 120, 120, 255)), width=wpx)

# per-hole footprint outlines (tee+fairway+green) + hole numbers at center
mm_per_px = PR
turf_polys = (g["features"].get("tee", []) + g["features"].get("fairway", [])
              + g["features"].get("green", []))
exclude = (g["features"].get("bunker", []) + g["features"].get("green", [])
           + g["features"].get("tee", []) + g["features"].get("water", []))
omask = hole_outline_mask(g["holes"], turf_polys, to_px, H, W,
                          corridor_half_px=3.5 / mm_per_px, stroke_px=0.7 / mm_per_px,
                          exclude_polys=exclude)
pim.paste((58, 92, 50), mask=Image.fromarray((omask * 255).astype("uint8")))
draw = ImageDraw.Draw(pim, "RGBA")
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(20, W // 70))
except Exception:
    font = None
for h in g["holes"]:
    if not h["ref"]:
        continue
    pts = h["pts"]
    d = [0.0]
    for (a, b), (c, e) in zip(pts, pts[1:]):
        d.append(d[-1] + math.hypot(c - a, e - b))
    half = d[-1] / 2
    mid = next((k for k in range(1, len(d)) if d[k] >= half), len(pts) // 2)
    t = (half - d[mid - 1]) / (d[mid] - d[mid - 1] or 1)
    lon = pts[mid - 1][0] + t * (pts[mid][0] - pts[mid - 1][0])
    lat = pts[mid - 1][1] + t * (pts[mid][1] - pts[mid - 1][1])
    mx, my = to_px(lon, lat)
    draw.text((mx, my), str(h["ref"]), fill=(255, 255, 255), font=font,
              anchor="mm", stroke_width=3, stroke_fill=(20, 40, 20))

scale = 1500 / W
out = pim.resize((int(W * scale), int(H * scale)), Image.LANCZOS)
out.save("data/board_preview.png")
out.save("data/route_prototype.png")
print(f"wrote data/board_preview.png {out.size}  ({ACTIVE})")
