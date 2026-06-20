#!/usr/bin/env python3
"""Synthesize fairways for holes that OSM left without one. For each routed
hole whose corridor has no nearby fairway polygon, build a capsule fairway
along the tee->green line. Writes data/golf_auto_<region>.json (regenerated
each run). Manual additions live separately in golf_manual_<region>.json."""
import json, math
from golf_common import fairway_capsule

cfg = json.load(open("data/regions.json"))
ACTIVE = cfg["active"]
clat = sum(cfg["regions"][ACTIVE]["bbox"][1::2]) / 2
g = json.load(open(f"data/golf_{ACTIVE}.json"))
HALF_W_M = 16.0   # synthesized fairway half-width (~32 m wide)
NEAR_M = 55.0     # a hole "has" a fairway if one's centroid is within this

def cen(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

def dist_m(a, b):
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(math.radians(clat)),
                      (a[1] - b[1]) * 111320)

fw_cen = [cen(f["pts"]) for f in g["features"].get("fairway", [])]
auto = []
for h in g.get("holes", []):
    if len(h["pts"]) < 2:
        continue
    # does any fairway sit near this hole's routing?
    near = any(min(dist_m(v, fc) for v in h["pts"]) < NEAR_M for fc in fw_cen)
    if not near:
        auto.append({"pts": fairway_capsule(h["pts"], HALF_W_M, clat)})

json.dump({"features": {"fairway": auto}},
          open(f"data/golf_auto_{ACTIVE}.json", "w"))
print(f"autofill: {len(auto)} fairways synthesized for "
      f"{len(g.get('holes', []))} holes ({len(fw_cen)} already mapped)")
