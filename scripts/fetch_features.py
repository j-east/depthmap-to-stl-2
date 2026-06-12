#!/usr/bin/env python3
"""Fetch map garnish for the ACTIVE region -> data/features_<region>.json

Rivers and buoys from OpenStreetMap (Overpass, with mirror fallback).
Place names are hand-added in the editor (Labels mode), not fetched.
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
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print(f"  overpass {ep.split('/')[2]}: {type(e).__name__}")
    return {"elements": []}

features = {"rivers": [], "buoys": []}

q = (f'[out:json][timeout:45];way["waterway"~"^(river|canal)$"]'
     f'({MINLAT},{MINLON},{MAXLAT},{MAXLON});out geom 400;')
for e in overpass(q).get("elements", []):
    geom = e.get("geometry") or []
    if len(geom) > 1:
        features["rivers"].append({"name": e.get("tags", {}).get("name"),
                                   "pts": [[p["lon"], p["lat"]] for p in geom]})

q = (f'[out:json][timeout:30];node["seamark:type"~"buoy"]'
     f'({MINLAT},{MINLON},{MAXLAT},{MAXLON});out 300;')
for e in overpass(q).get("elements", []):
    if "lon" in e:
        features["buoys"].append({"lon": e["lon"], "lat": e["lat"]})

out = f"data/features_{ACTIVE}.json"
json.dump(features, open(out, "w"), indent=1)
names = sorted({r["name"] for r in features["rivers"] if r["name"]})
print(f"{out}: {len(features['rivers'])} river ways ({', '.join(names[:6])}), "
      f"{len(features['buoys'])} buoys")
