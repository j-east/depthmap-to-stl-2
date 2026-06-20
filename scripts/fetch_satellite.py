#!/usr/bin/env python3
"""Fetch Esri World Imagery for the ACTIVE golf region and resample it into the
board frame, so it overlays the rendered preview exactly (for tracing missing
features). Writes data/sat_<region>.png."""
import json, urllib.request
import numpy as np
from PIL import Image
from golf_common import transform_golf, board_frame

Image.MAX_IMAGE_PIXELS = None
cfg = json.load(open("data/regions.json"))
ACTIVE = cfg["active"]
reg = cfg["regions"][ACTIVE]
g = transform_golf(json.load(open(f"data/golf_{ACTIVE}.json")), reg)
FR = board_frame(reg, g)
BW, BH = FR["BW"], FR["BH"]

# lon/lat bbox that bounds the (rotated) board, padded
corners = [FR["mm_to_ll"](x, y) for x in (0, BW) for y in (0, BH)]
los = [c[0] for c in corners]; las = [c[1] for c in corners]
pad = 0.06
w = max(los) - min(los); h = max(las) - min(las)
lo0, lo1 = min(los) - w * pad, max(los) + w * pad
la0, la1 = min(las) - h * pad, max(las) + h * pad

# fetch Esri imagery for that axis-aligned bbox
ew = int(min(2200, max(800, (lo1 - lo0) / (la1 - la0) * 1800)))
eh = int(ew * (la1 - la0) / (lo1 - lo0))
url = ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
       f"?bbox={lo0},{la0},{lo1},{la1}&bboxSR=4326&imageSR=4326&size={ew},{eh}"
       f"&format=png&f=image")
sat = np.array(Image.open(__import__("io").BytesIO(
    urllib.request.urlopen(url, timeout=90).read())).convert("RGB"))
print(f"{ACTIVE}: esri {ew}x{eh} over {lo1-lo0:.4f}x{la1-la0:.4f} deg")

# resample into the board frame
PR = max(BW, BH) / 1500.0
W, H = int(BW / PR), int(BH / PR)
gx_mm, gy_mm = np.meshgrid(np.arange(W) * PR, np.arange(H) * PR)
glon, glat = FR["mm_to_ll"](gx_mm, BH - gy_mm)
ec = np.clip(((glon - lo0) / (lo1 - lo0) * (ew - 1)).astype(int), 0, ew - 1)
er = np.clip(((la1 - glat) / (la1 - la0) * (eh - 1)).astype(int), 0, eh - 1)
out = sat[er, ec]
Image.fromarray(out).save(f"data/sat_{ACTIVE}.png")
print(f"wrote data/sat_{ACTIVE}.png {W}x{H} (board frame)")
