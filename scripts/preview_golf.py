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
g = json.load(open(f"data/golf_{ACTIVE}.json"))

a = np.array(Image.open(reg["src_file"]), dtype=np.float64)
a = np.where(a < -1e30, np.nan, a)
a = np.where(np.isnan(a), np.nanmedian(a), a)
H, W = a.shape

# layer paint order (back to front) and colors
COLORS = {
    "fairway": (150, 200, 104),
    "tee":     (150, 200, 104),
    "water":   (64, 132, 196),
    "bunker":  (238, 222, 170),
    "green":   (198, 226, 128),
}
ORDER = ["fairway", "tee", "water", "bunker", "green"]

# base = rough, hillshaded
gy, gx = np.gradient(a, M_SRC, M_SRC)
slope = np.arctan(np.hypot(gx, gy))
aspect = np.arctan2(-gx, gy)
az, alt = math.radians(315), math.radians(45)
hs = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
base = np.array([74, 116, 64])  # rough green (darker so mown turf pops)
img = (base[None, None, :] * (0.6 + 0.5 * hs)[..., None]).clip(0, 255).astype(np.uint8)
pim = Image.fromarray(img)
draw = ImageDraw.Draw(pim, "RGBA")

def to_px(lon, lat):
    return ((lon - MINLON) / (MAXLON - MINLON) * W,
            (MAXLAT - lat) / (MAXLAT - MINLAT) * H)

for layer in ORDER:
    for f in g["features"].get(layer, []):
        pts = [to_px(lon, lat) for lon, lat in f["pts"]]
        if len(pts) >= 3:
            draw.polygon(pts, fill=COLORS[layer] + (255,))

# paths, roads, railway
PATHCOL = {"cartpath": (224, 214, 188, 255), "road": (96, 96, 100, 255),
           "footway": (210, 196, 170, 200), "rail": (132, 86, 60, 255)}
PATHW = {"cartpath": 0.9, "road": 1.6, "footway": 0.7, "rail": 1.5}
for name, items in g.get("paths", {}).items():
    wpx = max(1, int(PATHW.get(name, 1.0) / M_SRC / (255 / H)))
    for p in items:
        pts = [to_px(lon, lat) for lon, lat in p["pts"]]
        if len(pts) >= 2:
            draw.line(pts, fill=PATHCOL.get(name, (120, 120, 120, 255)), width=wpx)

# routing lines (thin) + hole numbers
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(20, W // 70))
except Exception:
    font = None
for h in g["holes"]:
    pts = [to_px(lon, lat) for lon, lat in h["pts"]]
    if len(pts) >= 2:
        draw.line(pts, fill=(245, 245, 245, 220), width=max(2, W // 700))
    if h["ref"]:
        mx, my = pts[len(pts) // 2]
        draw.text((mx, my), str(h["ref"]), fill=(255, 255, 255), font=font,
                  anchor="mm", stroke_width=3, stroke_fill=(20, 40, 20))

scale = 1500 / W
out = pim.resize((int(W * scale), int(H * scale)), Image.LANCZOS)
out.save("data/board_preview.png")
out.save("data/route_prototype.png")
print(f"wrote data/board_preview.png {out.size}  ({ACTIVE})")
