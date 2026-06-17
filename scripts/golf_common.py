#!/usr/bin/env python3
"""Shared helpers for golf regions: a similarity transform (translate / scale /
rotate) that registers the OSM vector features onto the terrain, since the two
data sources often have a few metres of horizontal offset."""
import math


def transform_golf(g, reg):
    """Apply reg['feature_transform'] to every feature coordinate, in place.
    Transform = scale + rotation about the bbox centre, then a metre offset."""
    tf = reg.get("feature_transform") or {}
    dx = float(tf.get("dx_m", 0.0)); dy = float(tf.get("dy_m", 0.0))
    # independent lon (x) / lat (y) stretch; legacy uniform "scale" is the default
    sx = float(tf.get("scale_x", tf.get("scale", 1.0)))
    sy = float(tf.get("scale_y", tf.get("scale", 1.0)))
    rot = math.radians(float(tf.get("rot_deg", 0.0)))
    if dx == 0 and dy == 0 and sx == 1.0 and sy == 1.0 and rot == 0:
        return g
    lon0, lat0, lon1, lat1 = reg["bbox"]
    clon, clat = (lon0 + lon1) / 2, (lat0 + lat1) / 2
    mlon = 111320 * math.cos(math.radians(clat))
    mlat = 111320
    cosr, sinr = math.cos(rot), math.sin(rot)

    def f(lon, lat):
        x = (lon - clon) * mlon * sx     # stretch about the bbox centre
        y = (lat - clat) * mlat * sy
        xr = (x * cosr - y * sinr) + dx
        yr = (x * sinr + y * cosr) + dy
        return [clon + xr / mlon, clat + yr / mlat]

    for layer in g.get("features", {}).values():
        for ft in layer:
            ft["pts"] = [f(lo, la) for lo, la in ft["pts"]]
    for layer in g.get("paths", {}).values():
        for ft in layer:
            ft["pts"] = [f(lo, la) for lo, la in ft["pts"]]
    for h in g.get("holes", []):
        h["pts"] = [f(lo, la) for lo, la in h["pts"]]
    return g
