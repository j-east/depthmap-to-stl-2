#!/usr/bin/env python3
"""Detect fairway turf from the satellite overlay. Within each hole's corridor
(buffered tee->green routing) it classifies mown fairway by greenness +
brightness thresholds (tunable), writing a board-frame mask
data/fwmask_<region>.png that the renderers fold into the fairway layer.

Thresholds come from region["fairway_detect"] = {gmin, vmin, vmax, corridor_m}
or CLI: detect_fairways.py [gmin] [vmin] [corridor_m]."""
import json, sys
import numpy as np
from PIL import Image
from scipy import ndimage
from golf_common import transform_golf, merge_extra, board_frame

Image.MAX_IMAGE_PIXELS = None
cfg = json.load(open("data/regions.json"))
ACTIVE = cfg["active"]
reg = cfg["regions"][ACTIVE]
fd = reg.get("fairway_detect", {})
GMIN = float(sys.argv[1]) if len(sys.argv) > 1 else fd.get("gmin", 12)
VMIN = float(sys.argv[2]) if len(sys.argv) > 2 else fd.get("vmin", 70)
VMAX = fd.get("vmax", 230)
CORRIDOR_M = float(sys.argv[3]) if len(sys.argv) > 3 else fd.get("corridor_m", 45)

sat = np.array(Image.open(f"data/sat_{ACTIVE}.png").convert("RGB"), float)
H, W, _ = sat.shape
g = transform_golf(merge_extra(json.load(open(f"data/golf_{ACTIVE}.json")), ACTIVE), reg)
FR = board_frame(reg, g)
BW, BH = FR["BW"], FR["BH"]
PR = BW / W   # board mm per sat pixel

def to_px(lon, lat):
    x, y = FR["to_mm"](lon, lat)
    return float(x) / PR, (BH - float(y)) / PR

# corridor mask along all routings
from PIL import ImageDraw
cim = Image.new("1", (W, H), 0)
cd = ImageDraw.Draw(cim)
for h in g.get("holes", []):
    pts = [to_px(lo, la) for lo, la in h["pts"]]
    if len(pts) >= 2:
        cd.line(pts, fill=1, width=2, joint="curve")
corridor = ndimage.distance_transform_edt(~np.array(cim, bool)) <= (CORRIDOR_M / PR)

R, G, B = sat[..., 0], sat[..., 1], sat[..., 2]
greenness = G - np.maximum(R, B)
value = sat.mean(axis=2)
fw = corridor & (greenness >= GMIN) & (value >= VMIN) & (value <= VMAX)
# clean up speckle and fill small gaps
fw = ndimage.binary_opening(fw, iterations=2)
fw = ndimage.binary_closing(fw, iterations=3)
fw = ndimage.binary_dilation(fw, iterations=1)

Image.fromarray((fw * 255).astype(np.uint8)).save(f"data/fwmask_{ACTIVE}.png")
reg["fairway_detect"] = {"gmin": GMIN, "vmin": VMIN, "vmax": VMAX, "corridor_m": CORRIDOR_M}
json.dump(cfg, open("data/regions.json", "w"), indent=1)
print(f"detect: {100*fw.mean():.1f}% of board is fairway "
      f"(gmin {GMIN}, vmin {VMIN}, corridor {CORRIDOR_M}m)")
