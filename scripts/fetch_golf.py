#!/usr/bin/env python3
"""Fetch golf-course features for the ACTIVE region from OpenStreetMap.

Each turf feature (fairway, green, tee, bunker, water, rough) becomes a
filled polygon; each hole becomes a tee->green routing line with ref/par.
Writes data/golf_<region>.json.
"""
import json, urllib.parse, urllib.request

cfg = json.load(open("data/regions.json"))
ACTIVE = cfg["active"]
MINLON, MINLAT, MAXLON, MAXLAT = cfg["regions"][ACTIVE]["bbox"]

def overpass(q):
    for ep in ("https://overpass-api.de/api/interpreter",
               "https://overpass.private.coffee/api/interpreter",
               "https://overpass.kumi.systems/api/interpreter"):
        try:
            req = urllib.request.Request(
                ep, data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": "terrain-cribbage/1.0 (jakepevans@gmail.com)"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:
            print(f"  overpass {ep.split('/')[2]}: {type(e).__name__}")
    return {"elements": []}

q = (f'[out:json][timeout:80];'
     f'('
     f'way["golf"]({MINLAT},{MINLON},{MAXLAT},{MAXLON});'
     f'way["highway"]({MINLAT},{MINLON},{MAXLAT},{MAXLON});'
     f'way["railway"]({MINLAT},{MINLON},{MAXLAT},{MAXLON});'
     f');'
     f'out tags geom 2500;')

# normalize the zoo of golf tags into a few paint layers
LAYER = {
    "rough": "rough", "fairway": "fairway", "green": "green",
    "tee": "tee", "bunker": "bunker", "driving_range": "fairway",
    "water_hazard": "water", "lateral_water_hazard": "water",
}
feats = {k: [] for k in ("rough", "fairway", "tee", "green", "bunker", "water")}
paths = {"cartpath": [], "road": [], "footway": [], "rail": []}
holes = []
RAIL = {"rail", "light_rail", "subway", "tram", "narrow_gauge", "preserved"}

ROADS = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
         "residential", "living_street", "service", "road"}

for e in overpass(q).get("elements", []):
    t = e.get("tags", {})
    g = t.get("golf")
    hw = t.get("highway")
    rw = t.get("railway")
    geom = [[p["lon"], p["lat"]] for p in e.get("geometry", [])]
    if len(geom) < 2:
        continue
    if rw in RAIL:
        paths["rail"].append({"pts": geom})
    elif g == "hole":
        ref = t.get("ref", "")
        holes.append({"ref": int(ref) if ref.isdigit() else None,
                      "par": t.get("par"), "pts": geom})
    elif g == "cartpath" or t.get("highway") == "cartpath":
        paths["cartpath"].append({"pts": geom})
    elif g in LAYER:
        feats[LAYER[g]].append({"pts": geom})
    elif hw in ROADS:
        paths["road"].append({"pts": geom})
    elif hw in ("path", "footway", "track", "cycleway", "steps", "pedestrian"):
        paths["footway"].append({"pts": geom})

out = f"data/golf_{ACTIVE}.json"
json.dump({"features": feats, "paths": paths, "holes": holes,
           "bbox": [MINLON, MINLAT, MAXLON, MAXLAT]},
          open(out, "w"))
print(f"{out}:", {k: len(v) for k, v in feats.items()},
      "| paths", {k: len(v) for k, v in paths.items()},
      f"| {len([h for h in holes if h['ref']])} routed holes")
