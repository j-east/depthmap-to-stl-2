#!/usr/bin/env python3
"""Fetch map garnish for the board: place names (USGS GNIS), roads (USGS
National Map), buoys (OSM Overpass, skipped gracefully when unreachable).

Curates against the current course (data/route_lanes.json): islands are
chosen near the track, everything is spaced so labels don't pile up, and
nothing lands on a peg hole.  Writes data/features.json.
"""
import json, math, os, urllib.request, urllib.parse
import numpy as np
from scipy.spatial import cKDTree

REG = json.load(open("data/region.json"))
MINLON, MINLAT, MAXLON, MAXLAT = REG["bbox"]
RL = json.load(open("data/route_lanes.json"))
W, H = RL["grid"]
MMPP = RL["mm_per_px"]
cx0, cy0, cx1, cy1 = RL["crop_px"]

def ll_to_px(lon, lat):
    return ((lon - MINLON) / (MAXLON - MINLON) * W,
            (MAXLAT - lat) / (MAXLAT - MINLAT) * H)

def get(url, params, timeout=60):
    u = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(u, headers={"User-Agent": "deer-isle-cribbage/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

GNIS = "https://carto.nationalmap.gov/arcgis/rest/services/geonames/MapServer"
TNM_ROADS = "https://carto.nationalmap.gov/arcgis/rest/services/transportation/MapServer"
QBASE = dict(geometry=f"{MINLON},{MINLAT},{MAXLON},{MAXLAT}",
             geometryType="esriGeometryEnvelope", inSR="4326", outSR="4326",
             spatialRel="esriSpatialRelIntersects", where="1=1",
             outFields="gaz_name,gaz_featureclass", f="json",
             resultRecordCount="1000")

track = np.array(list(zip(*RL["lanes"][1])))      # middle lane, px
track_tree = cKDTree(track)
holes = np.array([p for hl in RL["holes"] for p in hl])
hole_tree = cKDTree(holes)
placed = [np.array([lb["x"], lb["y"]]) for lb in RL.get("labels", [])]

def mm(v): return v / MMPP

def in_crop(x, y, margin_mm=4.0):
    m = mm(margin_mm)
    return cx0 + m <= x <= cx1 - m and cy0 + m <= y <= cy1 - m

def try_place(x, y, min_label_mm=11.0, min_hole_mm=4.5):
    p = np.array([x, y])
    if placed and min(np.hypot(*(p - q)) for q in placed) < mm(min_label_mm):
        return False
    if len(hole_tree.query_ball_point(p, mm(min_hole_mm))):
        return False
    placed.append(p)
    return True

def gnis(layer, classes=None):
    feats = get(f"{GNIS}/{layer}/query", QBASE).get("features", [])
    out = []
    for f in feats:
        name = f["attributes"].get("gaz_name")
        cls = f["attributes"].get("gaz_featureclass")
        g = f.get("geometry") or {}
        if "x" in g:                       # point geometry
            lon, lat = g["x"], g["y"]
        elif g.get("points"):              # multipoint geometry
            lon, lat = g["points"][0]
        else:
            continue
        if not name or (classes and cls not in classes):
            continue
        out.append((name, lon, lat))
    return out

features = {"places": [], "islands": [], "bays": [], "roads": [], "buoys": []}

for name, lon, lat in gnis(3):                              # populated places
    x, y = ll_to_px(lon, lat)
    if in_crop(x, y) and len(features["places"]) < 12 and try_place(x, y, 8, 3.8):
        features["places"].append({"name": name, "lon": lon, "lat": lat})

isl = []
for name, lon, lat in gnis(5, {"Island"}):                  # islands near the track
    x, y = ll_to_px(lon, lat)
    if in_crop(x, y):
        d, _ = track_tree.query([x, y])
        isl.append((d, name, lon, lat, x, y))
for d, name, lon, lat, x, y in sorted(isl):
    if len(features["islands"]) >= 12:
        break
    if d < mm(22.0) and try_place(x, y, 7, 3.8):
        features["islands"].append({"name": name, "lon": lon, "lat": lat})

for name, lon, lat in gnis(7, {"Bay", "Channel"}):          # water names
    x, y = ll_to_px(lon, lat)
    if in_crop(x, y) and len(features["bays"]) < 6:
        d, _ = track_tree.query([x, y])
        if d > mm(7.0) and try_place(x, y, 20):
            features["bays"].append({"name": name, "lon": lon, "lat": lat})

# roads: secondary highways + local connecting (TNM layers 30, 31)
try:
    for lyr in (29, 30, 31):
        q = dict(QBASE); q["outFields"] = "*"
        for f in get(f"{TNM_ROADS}/{lyr}/query", q).get("features", []):
            for path in (f.get("geometry") or {}).get("paths", []):
                features["roads"].append([[p[0], p[1]] for p in path])
except Exception as e:
    print("roads fetch failed:", e)

# buoys: OSM Overpass (best-effort; mirrors are often busy)
try:
    qq = (f'[out:json][timeout:25];node["seamark:type"~"buoy"]'
          f'({MINLAT},{MINLON},{MAXLAT},{MAXLON});out 200;')
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                 data=urllib.parse.urlencode({"data": qq}).encode(),
                                 headers={"User-Agent": "deer-isle-cribbage/1.0 (jakepevans@gmail.com)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        for e in json.load(r).get("elements", []):
            x, y = ll_to_px(e["lon"], e["lat"])
            if in_crop(x, y) and len(hole_tree.query_ball_point([x, y], mm(3.5))) == 0:
                features["buoys"].append({"lon": e["lon"], "lat": e["lat"]})
except Exception as e:
    print("buoys skipped (Overpass unreachable):", type(e).__name__)

json.dump(features, open("data/features.json", "w"), indent=1)
print({k: len(v) for k, v in features.items()})
print("places:", [p["name"] for p in features["places"]])
print("islands:", [p["name"] for p in features["islands"]])
print("bays:", [p["name"] for p in features["bays"]])
