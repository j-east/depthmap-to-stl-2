#!/usr/bin/env python3
"""Shared helpers for golf regions: a similarity transform (translate / scale /
rotate) that registers the OSM vector features onto the terrain, since the two
data sources often have a few metres of horizontal offset."""
import math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


def _rasterize(polys, to_px, ny, nx):
    out = []
    for f in polys:
        pts = [to_px(p[0], p[1]) for p in f["pts"]]
        if len(pts) >= 3:
            im = Image.new("1", (nx, ny), 0)
            ImageDraw.Draw(im).polygon(pts, fill=1)
            out.append(np.array(im, bool))
    return out


def hole_outline_mask(holes, turf_polys, to_px, ny, nx, corridor_half_px, stroke_px,
                      exclude_polys=None):
    """Boolean outline of each hole's footprint = union of its tee/fairway/green
    polygons + a minimum-width corridor along the tee->green routing (so the
    pieces connect). Returns the perimeter band of every hole's footprint.
    Pixels under exclude_polys (bunkers/greens/tees/water) are cut so the
    outline yields to those features instead of printing over them."""
    tmasks = _rasterize(turf_polys, to_px, ny, nx)
    outline = np.zeros((ny, nx), bool)
    for h in holes:
        pts = [to_px(p[0], p[1]) for p in h["pts"]]
        if len(pts) < 2:
            continue
        lim = Image.new("1", (nx, ny), 0)
        ImageDraw.Draw(lim).line(pts, fill=1, width=2, joint="curve")
        corridor = ndimage.distance_transform_edt(~np.array(lim, bool)) <= corridor_half_px
        foot = corridor.copy()
        for tm in tmasks:               # add turf this hole's corridor touches
            if (tm & corridor).any():
                foot |= tm
        din = ndimage.distance_transform_edt(foot)
        dout = ndimage.distance_transform_edt(~foot)
        outline |= (foot & (din <= stroke_px)) | (~foot & (dout <= stroke_px))
    if exclude_polys:
        ex = np.zeros((ny, nx), bool)
        for m in _rasterize(exclude_polys, to_px, ny, nx):
            ex |= m
        ex = ndimage.binary_dilation(ex, iterations=max(1, int(stroke_px * 0.5)))
        outline &= ~ex                  # leave a small gap around features
    return outline


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
