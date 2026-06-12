#!/usr/bin/env python3
"""Auto-populate place names for the ACTIVE region as editable custom labels.

Settlements and named peaks from OSM, centered on their true locations with
no regard for the track or holes — curate them in the editor (drag, resize,
right-click to delete). Existing custom labels are never overwritten.
"""
import json, math, os, urllib.parse, urllib.request

cfg = json.load(open("data/regions.json"))
ACTIVE = cfg["active"]
MINLON, MINLAT, MAXLON, MAXLAT = cfg["regions"][ACTIVE]["bbox"]
WP = f"data/waypoints_{ACTIVE}.json"
wj = json.load(open(WP)) if os.path.exists(WP) else {"waypoints": []}
existing = wj.get("custom_labels", [])
have = {c["text"] for c in existing}
crop = wj.get("crop") or [MINLON, MINLAT, MAXLON, MAXLAT]

# board mm per degree, for spacing among the added names
crop_w_m = (crop[2] - crop[0]) * 111320 * math.cos(math.radians((crop[1] + crop[3]) / 2))
crop_h_m = (crop[3] - crop[1]) * 111320
mm_per_deg_lat = 255 / max(crop_w_m, crop_h_m) * 111320
MIN_SPACING_MM = 7.0

def overpass(q):
    for ep in ("https://overpass-api.de/api/interpreter",
               "https://overpass.private.coffee/api/interpreter"):
        try:
            req = urllib.request.Request(
                ep, data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": "terrain-cribbage/1.0 (jakepevans@gmail.com)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print(f"  overpass {ep.split('/')[2]}: {type(e).__name__}")
    return {"elements": []}

q = (f'[out:json][timeout:45];('
     f'node["place"~"^(city|town|village|hamlet)$"]["name"]({MINLAT},{MINLON},{MAXLAT},{MAXLON});'
     f'node["natural"="peak"]["name"]({MINLAT},{MINLON},{MAXLAT},{MAXLON});'
     f'node["place"="island"]["name"]({MINLAT},{MINLON},{MAXLAT},{MAXLON});'
     f');out 1000;')

RANK = {"city": 0, "town": 1, "village": 2, "island": 3, "hamlet": 4, "peak": 5}
SIZE = {"city": 8.0, "town": 7.5, "village": 6.5, "island": 5.5, "hamlet": 5.0, "peak": 5.5}
CAPS = {"city": 99, "town": 99, "village": 20, "island": 14, "hamlet": 8, "peak": 14}

cands = []
for e in overpass(q).get("elements", []):
    t = e.get("tags", {})
    name = t.get("name")
    lon, lat = e.get("lon"), e.get("lat")
    if not name or lon is None:
        continue
    if not (crop[0] <= lon <= crop[2] and crop[1] <= lat <= crop[3]):
        continue
    kind = "peak" if t.get("natural") == "peak" else t["place"]
    try:
        ele = float(str(t.get("ele", "0")).split(";")[0])
    except ValueError:
        ele = 0.0
    cands.append((RANK.get(kind, 9), -ele, kind, name, lon, lat))

cands.sort()
placed = [(c["lon"], c["lat"]) for c in existing]
counts = dict.fromkeys(CAPS, 0)
added = []
for _, negele, kind, name, lon, lat in cands:
    if name in have or counts[kind] >= CAPS[kind]:
        continue
    too_close = any(
        math.hypot((lon - plon) * math.cos(math.radians(lat)), lat - plat)
        * mm_per_deg_lat < MIN_SPACING_MM
        for plon, plat in placed)
    if too_close:
        continue
    existing.append({"text": name, "lon": lon, "lat": lat, "size": SIZE[kind]})
    placed.append((lon, lat))
    counts[kind] += 1
    added.append(name)

wj["custom_labels"] = existing
json.dump(wj, open(WP, "w"), indent=1)
print(f"added {len(added)} names ({counts}); total custom labels: {len(existing)}")
print("added:", ", ".join(added[:24]) + ("…" if len(added) > 24 else ""))
