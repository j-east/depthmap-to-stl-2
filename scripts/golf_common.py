#!/usr/bin/env python3
"""Shared helpers for golf regions: a similarity transform (translate / scale /
rotate) that registers the OSM vector features onto the terrain, since the two
data sources often have a few metres of horizontal offset."""
import math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


def board_frame(reg, g, long_mm=255.0, margin_m=35.0):
    """Map lon/lat <-> board millimetres in a frame that may be rotated to fit
    the course. board_rotation_deg in the region picks the angle; if unset, the
    minimum-area bounding rectangle of all features is used (tightest fit).
    Returns dict: BW, BH (mm), mm_per_m, theta_deg, to_mm(lon,lat),
    mm_to_ll(xmm,ymm) (both vectorised)."""
    pts = []
    for layer in g.get("features", {}).values():
        for f in layer:
            pts += f["pts"]
    for h in g.get("holes", []):
        pts += h["pts"]
    P = np.array(pts, float)
    clon, clat = P[:, 0].mean(), P[:, 1].mean()
    mlon = 111320 * math.cos(math.radians(clat)); mlat = 111320
    E = (P[:, 0] - clon) * mlon; N = (P[:, 1] - clat) * mlat
    th = reg.get("board_rotation_deg")
    if th is None:
        best = None
        for a in range(0, 90):
            r = math.radians(a); c, s = math.cos(r), math.sin(r)
            u = E * c + N * s; v = -E * s + N * c
            area = np.ptp(u) * np.ptp(v)
            if best is None or area < best[0]:
                best = (area, a)
        th = float(best[1])
    r = math.radians(th); c, s = math.cos(r), math.sin(r)
    u = E * c + N * s; v = -E * s + N * c
    umin, umax = u.min() - margin_m, u.max() + margin_m
    vmin, vmax = v.min() - margin_m, v.max() + margin_m
    mmpm = long_mm / max(umax - umin, vmax - vmin)
    BW, BH = (umax - umin) * mmpm, (vmax - vmin) * mmpm

    def to_mm(lon, lat):
        e = (np.asarray(lon) - clon) * mlon; n = (np.asarray(lat) - clat) * mlat
        uu = e * c + n * s; vv = -e * s + n * c
        return (uu - umin) * mmpm, (vv - vmin) * mmpm

    def mm_to_ll(xmm, ymm):
        uu = umin + np.asarray(xmm) / mmpm; vv = vmin + np.asarray(ymm) / mmpm
        e = uu * c - vv * s; n = uu * s + vv * c
        return clon + e / mlon, clat + n / mlat

    return dict(BW=BW, BH=BH, mm_per_m=mmpm, theta_deg=th, to_mm=to_mm, mm_to_ll=mm_to_ll)


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
