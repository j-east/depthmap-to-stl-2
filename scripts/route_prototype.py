#!/usr/bin/env python3
"""Prototype the cribbage track: a 3-lane route that starts at the Deer Isle
bridge, circumnavigates the islands, and weaves through the Merchant Row
archipelago — staying mid-channel via a clearance-weighted Dijkstra.

Outputs a rendered preview (data/route_prototype.png) and the lane polylines
as JSON (data/route_lanes.json) for later mesh generation.
"""
import json, math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage, sparse
from scipy.sparse.csgraph import dijkstra
from scipy.ndimage import uniform_filter1d

Image.MAX_IMAGE_PIXELS = None

import os
REGION = {"bbox": [-68.95, 43.98, -68.44, 44.36], "src_file": "data/foxisles_cudem.tif",
          "src_m_per_px": 8.46, "datum_m": 0, "exag": 5.0, "landmarks": []}
ACTIVE = "deer-isle"
if os.path.exists("data/regions.json"):
    _rj = json.load(open("data/regions.json"))
    ACTIVE = _rj.get("active", ACTIVE)
    REGION.update(_rj["regions"][ACTIVE])
SRC = REGION["src_file"]
MINLON, MINLAT, MAXLON, MAXLAT = REGION["bbox"]
M_SRC = REGION["src_m_per_px"]
DATUM_M = REGION["datum_m"]
EXAG_R = REGION.get("exag", 5.0)
WAYPOINTS_FILE = f"data/waypoints_{ACTIVE}.json"

# circumnavigation waypoints (lon, lat) — Dijkstra fills in the weave
WAYPOINTS = [
    (-68.621, 44.272),  # Deer Isle bridge (start)
    (-68.755, 44.300),  # Eggemoggin Reach west exit
    (-68.770, 44.215),  # down the west shore of Deer Isle
    (-68.720, 44.125),  # approach Stonington from the west
    (-68.663, 44.150),  # Stonington harbor / Deer Island Thorofare
    (-68.617, 44.128),  # weave: between the Merchant Row islands
    (-68.660, 44.075),  # into Isle au Haut Bay
    (-68.685, 44.025),  # down the west side of Isle au Haut
    (-68.640, 44.000),  # around the south tip
    (-68.585, 44.020),  # up the east side
    (-68.560, 44.080),  # back north past York Island
    (-68.535, 44.155),  # weave: up through the eastern archipelago
    (-68.505, 44.230),  # Jericho Bay, off Stinson Neck
    (-68.560, 44.295),  # Eggemoggin Reach NE
    (-68.621, 44.272),  # back to the bridge (finish)
]

# hand-drawn waypoints (from the path editor) override the defaults
import os
PATH_MODE = "waypoints"     # "waypoints" = Dijkstra between points; "drawn" = the points ARE the path
MIN_RADIUS_MM = 8.0         # minimum bend radius of the rendered course
CROP = None                 # [minlon, minlat, maxlon, maxlat] -> the physical board
LABEL_OVERRIDES = {}        # text -> [lon, lat], hand-placed in the editor
if os.path.exists(WAYPOINTS_FILE):
    _wj = json.load(open(WAYPOINTS_FILE))
    WAYPOINTS = [tuple(p) for p in _wj["waypoints"]]
    PATH_MODE = _wj.get("mode", "waypoints")
    MIN_RADIUS_MM = float(_wj.get("min_radius_mm", MIN_RADIUS_MM))
    CROP = _wj.get("crop")
    LABEL_OVERRIDES = _wj.get("label_overrides", {})
    CUSTOM_LABELS = _wj.get("custom_labels", [])
    print(f"{PATH_MODE} mode, {len(WAYPOINTS)} points, min radius {MIN_RADIUS_MM} mm, "
          f"crop {CROP}, {len(LABEL_OVERRIDES)} label overrides")
else:
    WAYPOINTS = []
    CUSTOM_LABELS = []
print(f"region: {ACTIVE}")

def render_base():
    """Hillshade + bathymetry + coastline + landmarks; also saves data/basemap.png."""
    land = ~water
    gy, gx = np.gradient(a, M_SRC, M_SRC)
    slope = np.arctan(np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
    azr, altr = math.radians(315), math.radians(45)
    hs = np.clip(np.sin(altr) * np.cos(slope) +
                 np.cos(altr) * np.sin(slope) * np.cos(azr - aspect), 0, 1)
    img = np.zeros((H, W, 3))
    depth = np.clip(-a, 0, 80) / 80
    img[water] = np.stack([0.04 + 0.10 * (1 - depth), 0.18 + 0.35 * (1 - depth),
                           0.35 + 0.45 * (1 - depth)], -1)[water]
    emax = a[land].max(); e = np.clip(a, 0, emax) / emax
    img[land] = np.stack([0.30 + 0.55 * e, 0.55 - 0.15 * e, 0.30 - 0.10 * e], -1)[land]
    # snowline tint on high terrain (only kicks in for big-relief regions)
    if emax > 1500:
        snow = (np.clip((e - 0.55) / 0.2, 0, 1) * 0.85)[..., None]
        img = np.where(land[..., None], img * (1 - snow) + np.array([0.93, 0.94, 0.97]) * snow, img)
    img[land] *= (0.45 + 0.75 * hs[land])[:, None]
    # topographic contours, interval adapted to the region's relief
    gmag = np.hypot(*np.gradient(a))
    tol = np.maximum(gmag * 0.9, 0.02)
    lmax = a[land].max() if land.any() else 1.0
    ci = next(c for c in (20, 25, 50, 100, 200, 250, 500, 1000) if lmax / c <= 16)
    for L in np.arange(ci, lmax, ci):
        m = land & (np.abs(a - L) < tol)
        img[m] *= 0.55
    wmin = a[water].min() if water.any() else 0.0
    if wmin < 0:
        wi = next(c for c in (15, 25, 50, 100, 200, 500) if -wmin / c <= 10)
        for L in np.arange(-wi, wmin, -wi):
            m = water & (np.abs(a - L) < tol)
            img[m] = img[m] * 0.55 + np.array([0.25, 0.45, 0.55]) * 0.45
    edge = land ^ ndimage.binary_erosion(land)
    img[edge] = [0.95, 0.9, 0.35]
    pim = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    dr = ImageDraw.Draw(pim)
    rr = max(8, W // 320)
    try:
        from PIL import ImageFont
        _lf = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(18, W // 130))
    except Exception:
        _lf = None
    for lon, lat, label in LANDMARKS:
        x, y = lonlat_to_px(lon, lat)
        dr.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(255, 60, 60), outline=(0, 0, 0), width=2)
        dr.text((x + rr + 6, y), label, fill=(255, 255, 255), font=_lf, anchor="lm",
                stroke_width=2, stroke_fill=(0, 0, 0))
    pim.resize((W // 2, H // 2), Image.LANCZOS).save("data/basemap.png")
    return pim

def enforce_min_radius(x, y, r_min_px):
    """Locally smooth the polyline until its bend radius is everywhere >= r_min."""
    for _ in range(300):
        dx, dy = np.gradient(x), np.gradient(y)
        ds = np.maximum(np.hypot(dx, dy), 1e-9)
        ang = np.unwrap(np.arctan2(dy, dx))
        curv = np.abs(np.gradient(ang)) / ds
        bad = curv > 1.0 / r_min_px
        if not bad.any():
            break
        widen = ndimage.binary_dilation(bad, iterations=12)
        xs = uniform_filter1d(x, 17, mode="nearest")
        ys = uniform_filter1d(y, 17, mode="nearest")
        x = np.where(widen, xs, x); y = np.where(widen, ys, y)
    return x, y

LANDMARKS = [tuple(l) for l in REGION.get("landmarks", [])]

DOWN = 4            # routing grid downsample factor
LANE_COLORS = [(225, 50, 50), (245, 215, 70), (245, 245, 245)]

# ---- physical units (mm); px equivalents are derived AFTER the crop is
# known, since the crop defines the 255 mm board scale ----
LANE_SP_MM = 4.75                 # lane-to-lane spacing
HOLE_SP_MM = 4.4                  # hole-to-hole along a lane
GROUP_GAP_MM = 5.5                # extra gap between groups of 5
HOLE_MARGIN_MM = 0.6              # water beyond the outer lane at hole sites
LINE_MARGIN_MM = 1.3              # min shore standoff for the engraved lines
SQUEEZE_MIN = 0.28                # lanes may compress to this fraction in pinches
N_GROUPS = 24                     # 24 x 5 = 120 holes, once around

a = np.array(Image.open(SRC), dtype=np.float64)
nodata = (a < -1e30) | np.isnan(a)
print(f"grid {a.shape[1]}x{a.shape[0]}, nodata {100*nodata.sum()/a.size:.2f}%")
a = np.where(nodata, 0.5, a - DATUM_M)  # datum-relative; nodata -> land (impassable)
H, W = a.shape
water = a <= 0

# ---- the crop IS the board: scale everything to 255 mm max dimension ----
if CROP:
    cx0 = max(0, int((CROP[0] - MINLON) / (MAXLON - MINLON) * W))
    cx1 = min(W, int((CROP[2] - MINLON) / (MAXLON - MINLON) * W))
    cy0 = max(0, int((MAXLAT - CROP[3]) / (MAXLAT - MINLAT) * H))
    cy1 = min(H, int((MAXLAT - CROP[1]) / (MAXLAT - MINLAT) * H))
else:
    cx0, cy0, cx1, cy1 = 0, 0, W, H
MM_PER_PX = 255.0 / max(cx1 - cx0, cy1 - cy0)
print(f"board: {(cx1-cx0)*MM_PER_PX:.0f} x {(cy1-cy0)*MM_PER_PX:.0f} mm")
LANE_OFFSET_PX = LANE_SP_MM / MM_PER_PX
HOLE_STEP_PX = HOLE_SP_MM / MM_PER_PX
GROUP_GAP_PX = GROUP_GAP_MM / MM_PER_PX
HOLE_CLEAR_PX = (LANE_SP_MM + HOLE_MARGIN_MM) / MM_PER_PX
LINE_MARGIN_PX = LINE_MARGIN_MM / MM_PER_PX

def lonlat_to_px(lon, lat):
    return ((lon - MINLON) / (MAXLON - MINLON) * W,
            (MAXLAT - lat) / (MAXLAT - MINLAT) * H)

if len(WAYPOINTS) < 2:
    # fresh region: render the chart so the editor has a map to draw on
    pim = render_base()
    dr = ImageDraw.Draw(pim)
    dr.rectangle([cx0, cy0, cx1, cy1], outline=(255, 255, 255), width=6)
    pim.resize((W // 2, H // 2), Image.LANCZOS).save("data/route_prototype.png")
    raise SystemExit(f"region '{ACTIVE}': no course yet — draw one and Save & Re-route")
CROP_MARG_PX = 2.5 / MM_PER_PX    # holes must sit this far inside the board edge

# ---- routing on downsampled grid ----
wd = water[::DOWN, ::DOWN]
h, w = wd.shape
clear_d = ndimage.distance_transform_edt(wd)          # px to nearest land (coarse)
# "scenic cruising" cost: cheapest in a band ~85-270 m off the rocks, expensive
# in open water (forces coast-hugging + island-weaving), impassable too close in
SWEET_LO, SWEET_HI = 2.5, 8.0
cost = np.ones_like(clear_d)
cost += np.where(clear_d > SWEET_HI, ((clear_d - SWEET_HI) / 4.0) ** 2, 0)
cost += np.where(clear_d < SWEET_LO, ((SWEET_LO - clear_d) * 3.0) ** 2, 0)
cost = np.minimum(cost, 400.0)
cost[wd & (clear_d < 1.8)] = 900.0   # hugging the rocks: discouraged, not banned
cost[~wd] = 2500.0  # land is crossable at a steep price (causeways, tiny spits)

idx = np.arange(h * w).reshape(h, w)
rows, cols, wts = [], [], []
for dy, dx in [(0, 1), (1, 0), (1, 1), (1, -1)]:
    s0 = (slice(0, h - dy), slice(max(0, -dx), w - max(0, dx)))
    s1 = (slice(dy, h), slice(max(0, dx), w - max(0, -dx)))
    step = math.hypot(dx, dy)
    cw = (cost[s0] + cost[s1]) / 2 * step
    rows.append(idx[s0].ravel()); cols.append(idx[s1].ravel()); wts.append(cw.ravel())
rows = np.concatenate(rows); cols = np.concatenate(cols); wts = np.concatenate(wts)
graph = sparse.csr_matrix(
    (np.concatenate([wts, wts]), (np.concatenate([rows, cols]), np.concatenate([cols, rows]))),
    shape=(h * w, h * w))

def snap(lon, lat):
    x, y = lonlat_to_px(lon, lat)
    cy, cx = int(y / DOWN), int(x / DOWN)
    best, bd = None, 1e18
    r = 40
    ys, xs = np.mgrid[max(0, cy - r):min(h, cy + r), max(0, cx - r):min(w, cx + r)]
    m = (clear_d[ys, xs] >= 2.5)
    if not m.any():
        raise SystemExit(f"waypoint ({lon},{lat}) has no nearby water")
    d2 = (ys - cy) ** 2 + (xs - cx) ** 2 + (clear_d[ys, xs] < 3.5) * 400
    k = np.argmin(np.where(m, d2, 1e18))
    return ys.ravel()[k] * w + xs.ravel()[k]

if PATH_MODE == "drawn":
    # the drawn polyline IS the course — no routing
    pts = np.array([lonlat_to_px(lon, lat) for lon, lat in WAYPOINTS])
    fx, fy = pts[:, 0].astype(float), pts[:, 1].astype(float)
    fx = uniform_filter1d(fx, 5, mode="nearest"); fy = uniform_filter1d(fy, 5, mode="nearest")
else:
    nodes = [snap(lon, lat) for lon, lat in WAYPOINTS]
    path = []
    for i in range(len(nodes) - 1):
        _, pred = dijkstra(graph, indices=nodes[i], return_predecessors=True)
        seg, n = [], nodes[i + 1]
        while n != nodes[i] and n >= 0:
            seg.append(n); n = pred[n]
        if n < 0:
            raise SystemExit(f"no water path for leg {i}")
        seg.append(nodes[i]); seg.reverse()
        path.extend(seg if not path else seg[1:])
        print(f"leg {i}: {len(seg)} px")

    py, px = np.array(path) // w, np.array(path) % w
    fx, fy = px.astype(float) * DOWN + DOWN / 2, py.astype(float) * DOWN + DOWN / 2
    _wm = "wrap" if nodes[0] == nodes[-1] else "nearest"
    fx = uniform_filter1d(fx, 21, mode=_wm); fy = uniform_filter1d(fy, 21, mode=_wm)

# resample to even arc length (full-res px)
d = np.hypot(np.diff(fx), np.diff(fy)); s = np.concatenate([[0], np.cumsum(d)])
u = np.arange(0, s[-1], 3.0)
rx, ry = np.interp(u, s, fx), np.interp(u, s, fy)

# enforce the minimum bend radius, then re-resample evenly
rx, ry = enforce_min_radius(rx, ry, MIN_RADIUS_MM / MM_PER_PX)
d = np.hypot(np.diff(rx), np.diff(ry)); s = np.concatenate([[0], np.cumsum(d)])
total = s[-1]; print(f"route length {total:.0f} px = {total*M_SRC/1000:.1f} km real "
                     f"= {total*MM_PER_PX:.0f} mm on board")
u = np.arange(0, total, 3.0)
rx, ry = np.interp(u, s, rx), np.interp(u, s, ry)

DS = u[1] - u[0]  # arc px per sample
hole_step, group_gap = HOLE_STEP_PX, GROUP_GAP_PX
STRIDE = 5

# ---- excise short self-intersection loops left by drawing/smoothing ----
N0 = len(u)
MAX_LOOP = 450  # samples (~70 mm of track)
changed = True
while changed:
    changed = False
    n = len(rx)
    i = 0
    while i < n - 4:
        jlo, jhi = i + 3, min(i + MAX_LOOP, n - 1)
        if jlo >= jhi:
            i += 1; continue
        rxv, ryv = rx[i + 1] - rx[i], ry[i + 1] - ry[i]
        qx, qy = rx[jlo:jhi], ry[jlo:jhi]
        sx, sy = rx[jlo + 1:jhi + 1] - qx, ry[jlo + 1:jhi + 1] - qy
        den = rxv * sy - ryv * sx
        qpx, qpy = qx - rx[i], qy - ry[i]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (qpx * sy - qpy * sx) / den
            v = (qpx * ryv - qpy * rxv) / den
        hit = np.where((den != 0) & (t > 0) & (t < 1) & (v > 0) & (v < 1))[0]
        if len(hit):
            j = jlo + int(hit[0])
            keep = np.r_[0:i + 1, j + 1:n]
            rx, ry = rx[keep], ry[keep]
            n = len(rx); changed = True
        else:
            i += 1
print(f"loop excision: removed {N0 - len(rx)} of {N0} samples")
d_ = np.hypot(np.diff(rx), np.diff(ry))
u = np.concatenate([[0], np.cumsum(d_)])
total = u[-1]

# ---- frame + lanes: squeeze only where curvature would cross the offsets ----
# open courses must NOT wrap-smooth (it folds the two ends toward each other)
CLOSED = math.hypot(rx[-1] - rx[0], ry[-1] - ry[0]) < 12.0 / MM_PER_PX
SMODE = "wrap" if CLOSED else "nearest"
print(f"course is {'a closed loop' if CLOSED else 'open (start and end apart)'}")
rx = uniform_filter1d(rx, 25, mode=SMODE); ry = uniform_filter1d(ry, 25, mode=SMODE)
tx = np.gradient(rx); ty = np.gradient(ry)
tl = np.hypot(tx, ty); tx /= tl; ty /= tl
nx, ny = -ty, tx
ang = np.unwrap(np.arctan2(ty, tx))
curv = uniform_filter1d(np.abs(np.gradient(ang)) / DS, 51, mode=SMODE)  # 1/px
radius = 1.0 / np.maximum(curv, 1e-9)
squeeze = np.clip(radius / (3.5 * LANE_OFFSET_PX), SQUEEZE_MIN, 1.0)
squeeze = uniform_filter1d(squeeze, 101, mode=SMODE)
lanes = []
for k in (-1, 0, 1):
    lx = uniform_filter1d(rx + k * LANE_OFFSET_PX * squeeze * nx, 25, mode=SMODE)
    ly = uniform_filter1d(ry + k * LANE_OFFSET_PX * squeeze * ny, 25, mode=SMODE)
    lanes.append((lx, ly))

# each lane spaces its holes along ITS OWN arc length, so spacing holds
# through curves (inner-lane holes would otherwise bunch up and collide)
lane_arcs = [np.concatenate([[0], np.cumsum(np.hypot(np.diff(lx), np.diff(ly)))])
             for lx, ly in lanes]

def lane_pt(k, ic, d_arc):
    sk = lane_arcs[k]
    s = min(max(sk[min(ic, len(sk) - 1)] + d_arc, 0.0), sk[-1])
    i = min(np.searchsorted(sk, s), len(sk) - 1)
    return float(lanes[k][0][i]), float(lanes[k][1][i])

# ---- hole sites: land or sea, anywhere on the board — the only rules:
# stay inside the board edge and never collide with another hole, whether
# from this group or from another track section passing nearby ----
from scipy.spatial import cKDTree
from scipy.spatial.distance import pdist
tree = cKDTree(np.c_[rx, ry])
PROX_PX = (LANE_SP_MM + 4.0) / MM_PER_PX  # standoff from other track sections
ARC_NEAR_PX = 25.0 / MM_PER_PX            # closer than this along the track = same section
HOLE_MIN_PX = 3.8 / MM_PER_PX             # min distance between any two hole centers

def group_pts(ic, hole_step, d0=0.0):
    """The 15 actual hole positions of a group centered at sample ic."""
    return [lane_pt(k, ic, d0 + (m - 2) * hole_step) for k in range(3) for m in range(5)]

def site_ok(i, hs_idx, hole_step):
    pts = group_pts(i, hole_step)
    for x, y in pts:
        if not (cx0 + CROP_MARG_PX <= x < cx1 - CROP_MARG_PX and
                cy0 + CROP_MARG_PX <= y < cy1 - CROP_MARG_PX):
            return False
        for nb in tree.query_ball_point([x, y], PROX_PX):
            da = abs(u[nb] - u[min(i, len(u) - 1)])
            if (min(da, total - da) if CLOSED else da) > ARC_NEAR_PX:
                return False
    return pdist(np.array(pts)).min() >= HOLE_MIN_PX

# adapt spacing toward printable minimums until 24 groups fit
HOLE_STEP_FLOOR = 4.1 / MM_PER_PX   # 0.9 mm wall between 3.2 mm holes
GAP_FLOOR = 4.5 / MM_PER_PX
for it in range(6):
    hs_idx = max(1, int(round(hole_step / DS)))
    cluster_len = 4 * hole_step
    min_sep = int((cluster_len + group_gap) / DS)
    # keep room at the track ends for the start pair / finish hole —
    # checked on every lane's own arc (inner lanes contract through curves)
    start_room = cluster_len / 2 + hole_step * 6
    finish_room = cluster_len / 2 + hole_step * 4
    sites = [i for i in range(0, len(u), STRIDE)
             if all(lane_arcs[k][i] >= start_room and
                    lane_arcs[k][-1] - lane_arcs[k][i] >= finish_room for k in range(3))
             and site_ok(i, hs_idx, hole_step)]
    # separation must hold on EVERY lane's own arc, not just the centerline
    # (the inner lane's arc contracts through curves)
    chain, last = [], None
    for i in sites:
        if last is None or (i - last >= min_sep and
                all(lane_arcs[k][i] - lane_arcs[k][last] >= cluster_len + group_gap * 0.7
                    for k in range(3))):
            chain.append(i); last = i
    print(f"  spacing {hole_step*MM_PER_PX:.2f} mm -> capacity {len(chain)} of "
          f"{N_GROUPS} groups ({len(sites)} sites)")
    if len(chain) >= N_GROUPS:
        break
    if hole_step <= HOLE_STEP_FLOOR + 1e-9 and group_gap <= GAP_FLOOR + 1e-9:
        break
    hole_step = max(hole_step * 0.94, HOLE_STEP_FLOOR)
    group_gap = max(group_gap * 0.92, GAP_FLOOR)

if len(chain) < N_GROUPS:
    # still render the course line so the editor shows what was drawn
    pim = render_base()
    dr = ImageDraw.Draw(pim)
    dr.line(list(zip(rx, ry)), fill=(255, 255, 255), width=10, joint="curve")
    dr.rectangle([cx0, cy0, cx1, cy1], outline=(255, 255, 255), width=6)
    pim.resize((W // 2, H // 2), Image.LANCZOS).save("data/route_prototype.png")
    short_mm = (N_GROUPS - len(chain)) * (4 * hole_step + group_gap) * MM_PER_PX
    raise SystemExit(
        f"COURSE TOO SHORT: only {len(chain)} of {N_GROUPS} hole groups fit, even at "
        f"minimum spacing.\nThe track needs roughly {short_mm:.0f} mm more length inside "
        f"the crop (or fewer close parallel passes). Draw more course and re-route.")
sel = np.round(np.linspace(0, len(chain) - 1, N_GROUPS)).astype(int)
centers = [float(u[chain[k]]) for k in sel]

holes = [[] for _ in range(3)]
ic0 = min(np.searchsorted(u, centers[0]), len(u) - 1)
icf = min(np.searchsorted(u, centers[-1]), len(u) - 1)

# start pair / finish hole: nudge outward until they don't collide with
# their neighboring group (or each other)
g0 = np.array(group_pts(ic0, hole_step))
for extra in np.arange(0.0, 3.1, 0.5):
    offs = [-cluster_len / 2 - hole_step * (2.5 + extra),
            -cluster_len / 2 - hole_step * (1.5 + extra)]
    spts = [lane_pt(k, ic0, o) for k in range(3) for o in offs]
    if pdist(np.vstack([spts, g0])).min() >= HOLE_MIN_PX:
        break
gf = np.array(group_pts(icf, hole_step))
for fextra in np.arange(0.0, 3.1, 0.5):
    foff = cluster_len / 2 + hole_step * (1.5 + fextra)
    fpts = [lane_pt(k, icf, foff) for k in range(3)]
    # the finish must also clear the start pair (closed-loop courses)
    if pdist(np.vstack([fpts, gf, spts, g0])).min() >= HOLE_MIN_PX:
        break

for k in range(3):
    for o in offs:                                     # 2 start holes
        holes[k].append(lane_pt(k, ic0, o))
    for c in centers:                                  # 24 groups of 5
        ic = min(np.searchsorted(u, c), len(u) - 1)
        for m in range(5):
            holes[k].append(lane_pt(k, ic, (m - 2) * hole_step))
    holes[k].append(lane_pt(k, icf, foff))             # finish hole
print("holes per lane:", len(holes[0]), "(2 start + 120 + finish)")

# verify no two holes anywhere on the board collide
allh = np.array([p for hl in holes for p in hl])
close = cKDTree(allh).query_pairs(3.6 / MM_PER_PX)
if close:
    print(f"WARNING: {len(close)} hole pairs closer than 3.6 mm")
else:
    print("hole collision check: clean")

# ---- labels: START / END and the count every 5 holes; all north-up,
# placed to avoid the track, holes, group rings, and each other ----
LABEL_MM = 9.6
hole_tree = cKDTree(allh)
placed_rects = []

def rect_penalty(x, y, hw, hh):
    """0 = clear; otherwise weighted badness (holes are near-forbidden)."""
    pen = 0
    # true lane envelope: lanes + line width + a hair; rings stick out 2.9mm
    margin = LANE_OFFSET_PX + 1.4 / MM_PER_PX
    r = math.hypot(hw + margin, hh + margin)
    hits = 0
    for nb in tree.query_ball_point([x, y], r):
        if abs(rx[nb] - x) < hw + margin and abs(ry[nb] - y) < hh + margin:
            hits += 1
    pen += min(hits, 6) * 10
    for nb in hole_tree.query_ball_point([x, y], r):
        if (abs(allh[nb][0] - x) < hw + 2.2 / MM_PER_PX and
                abs(allh[nb][1] - y) < hh + 2.2 / MM_PER_PX):
            pen += 1000
    for qx, qy, qw, qh in placed_rects:
        if (abs(qx - x) < hw + qw + 1.5 / MM_PER_PX and
                abs(qy - y) < hh + qh + 1.5 / MM_PER_PX):
            pen += 500
    return pen

def _attempt(ic, d_arc, text, size_mm, mults):
    hw = len(text) * size_mm * 0.36 / MM_PER_PX
    hh = size_mm * 0.62 / MM_PER_PX
    base_off = LANE_OFFSET_PX + (2.2 + size_mm * 0.55) / MM_PER_PX
    s0 = u[min(ic, len(u) - 1)] + d_arc
    best, best_pen = None, 1e18
    # prefer close: small lateral offsets first, sliding along the track too
    for mult in mults:
        for darc_mm in (0.0, 6.0, -6.0, 11.0, -11.0, 16.0, -16.0):
            i2 = min(np.searchsorted(u, min(max(s0 + darc_mm / MM_PER_PX, 0), u[-1])), len(u) - 1)
            for side in (1.0, -1.0):
                x = rx[i2] + side * base_off * mult * nx[i2]
                y = ry[i2] + side * base_off * mult * ny[i2]
                x = min(max(x, cx0 + hw + 20), cx1 - hw - 20)
                y = min(max(y, cy0 + hh + 20), cy1 - hh - 20)
                pen = rect_penalty(x, y, hw, hh)
                if pen == 0:
                    return x, y, 0, hw, hh
                if pen < best_pen:
                    best, best_pen = (x, y), pen
    # crowded corner: sweep rings around the anchor for the nearest clear spot
    if best_pen > 60:
        ia = min(np.searchsorted(u, min(max(s0, 0), u[-1])), len(u) - 1)
        ax, ay = rx[ia], ry[ia]
        for rad_mm in np.arange(13.0, 56.0, 3.5):
            for angd in range(0, 360, 24):
                x = ax + math.cos(math.radians(angd)) * rad_mm / MM_PER_PX
                y = ay + math.sin(math.radians(angd)) * rad_mm / MM_PER_PX
                x = min(max(x, cx0 + hw + 20), cx1 - hw - 20)
                y = min(max(y, cy0 + hh + 20), cy1 - hh - 20)
                pen = rect_penalty(x, y, hw, hh)
                if pen == 0:
                    return x, y, 0, hw, hh
                if pen < best_pen:
                    best, best_pen = (x, y), pen
    return best[0], best[1], best_pen, hw, hh

def label_pos(ic, d_arc, text, mults=(1.0, 1.2, 1.45, 1.7, 2.0, 2.4, 2.8), sizes=None):
    """Find a home for the label; crowded spots get progressively smaller text
    (or exactly the given sizes). Returns (x, y, size_mm, penalty)."""
    if text in LABEL_OVERRIDES:
        # hand-placed in the editor: position is law; a hand-set size is too,
        # otherwise shrink only if dropped onto another label or a hole
        ov = LABEL_OVERRIDES[text]
        if isinstance(ov, dict):
            lon, lat = ov["pos"]
            forced = ov.get("size")
        else:
            (lon, lat), forced = ov, None
        x, y = lonlat_to_px(lon, lat)
        sizes = (forced,) if forced else (sizes or (LABEL_MM, 7.4, 6.2))
        for size_mm in sizes:
            hw = len(text) * size_mm * 0.36 / MM_PER_PX
            hh = size_mm * 0.62 / MM_PER_PX
            if forced or rect_penalty(x, y, hw, hh) < 500:
                break
        placed_rects.append((x, y, hw, hh))
        return float(x), float(y), size_mm, 0.0
    overall, overall_score, overall_pen = None, 1e18, 1e18
    for size_mm in (sizes or (LABEL_MM, 7.4, 6.2)):
        x, y, pen, hw, hh = _attempt(ic, d_arc, text, size_mm, mults)
        if pen == 0:
            placed_rects.append((x, y, hw, hh))
            return float(x), float(y), size_mm, 0.0
        score = pen + (LABEL_MM - size_mm) * 6
        if score < overall_score:
            overall, overall_score, overall_pen = (x, y, size_mm, hw, hh), score, pen
    x, y, size_mm, hw, hh = overall
    placed_rects.append((x, y, hw, hh))
    return float(x), float(y), size_mm, float(overall_pen)

labels = []
# direction-of-play arrow just before the starting block (replaces START/END)
i_ar = min(np.searchsorted(u, max(u[ic0] + offs[0] - 7.0 / MM_PER_PX, 0)), len(u) - 1)
_dx, _dy = tx[i_ar], ty[i_ar]
_nx, _ny = -_dy, _dx
AL, AW = 7.0 / MM_PER_PX, 6.0 / MM_PER_PX
_px, _py = rx[i_ar], ry[i_ar]
arrow = {"pts": [[float(_px + _dx * AL * 0.6), float(_py + _dy * AL * 0.6)],
                 [float(_px - _dx * AL * 0.4 + _nx * AW / 2), float(_py - _dy * AL * 0.4 + _ny * AW / 2)],
                 [float(_px - _dx * AL * 0.4 - _nx * AW / 2), float(_py - _dy * AL * 0.4 - _ny * AW / 2)]]}

# all count labels share one size: the largest at which every one of the 24
# finds a clean home (crowded boards step the whole set down together)
for uni in (LABEL_MM, 8.4, 7.4, 6.6):
    snapshot = list(placed_rects)
    nlabels, worst = [], 0.0
    for g, c in enumerate(centers):
        ic = min(np.searchsorted(u, c), len(u) - 1)
        txt = str((g + 1) * 5)
        x_, y_, s_, pen = label_pos(ic, 0.0, txt, sizes=(uni,))
        nlabels.append({"text": txt, "x": x_, "y": y_, "angle": 0.0, "size": s_})
        worst = max(worst, pen)
    if worst < 300:
        break
    placed_rects[:] = snapshot
print(f"count labels: uniform {uni} mm (worst penalty {worst:.0f})")
labels.extend(nlabels)

# user-added place names from the editor: position and text are law
for cl in CUSTOM_LABELS:
    x_, y_ = lonlat_to_px(cl["lon"], cl["lat"])
    labels.append({"text": cl["text"], "x": float(x_), "y": float(y_),
                   "angle": 0.0, "size": float(cl.get("size", 6.5)), "custom": True})

# ---- small capsule across the track around each MILESTONE row: the three
# holes (one per lane) at every 5th position, which the count label names ----
group_rings = []
for c in centers:
    ic = min(np.searchsorted(u, c), len(u) - 1)
    # last hole of the group = the 5th/10th/15th... in travel direction
    pts = [list(lane_pt(k, ic, 2 * hole_step)) for k in range(3)]
    group_rings.append({"pts": pts, "half_w": float(2.5 / MM_PER_PX)})

# starting block: a FILLED colored pad under both 2x3 start rows
ia = min(np.searchsorted(u, max(u[ic0] + offs[0], 0)), len(u) - 1)
ib = min(np.searchsorted(u, max(u[ic0] + offs[1], 0)), len(u) - 1)
start_block = {"pts": [[float(rx[ia]), float(ry[ia])], [float(rx[ib]), float(ry[ib])]],
               "half_w": float(LANE_OFFSET_PX * squeeze[ic0] + 2.5 / MM_PER_PX)}

json.dump({"lanes": [[list(map(float, l[0])), list(map(float, l[1]))] for l in lanes],
           "holes": [[(float(x), float(y)) for x, y in hl] for hl in holes],
           "bbox": [MINLON, MINLAT, MAXLON, MAXLAT], "grid": [W, H],
           "mm_per_px": MM_PER_PX, "crop_px": [cx0, cy0, cx1, cy1],
           "labels": labels, "group_rings": group_rings, "start_block": start_block,
           "arrow": arrow,
           "datum_m": DATUM_M, "src_file": SRC, "region": ACTIVE,
           "exag": EXAG_R, "src_m_per_px": M_SRC,
           "spec": {"lane_sp_mm": LANE_SP_MM, "hole_step_mm": hole_step * MM_PER_PX,
                    "hole_dia_mm": 3.2,
                    "board_mm": [(cx1 - cx0) * MM_PER_PX, (cy1 - cy0) * MM_PER_PX]}},
          open("data/route_lanes.json", "w"))

# ---- render ----
pim = render_base()
draw = ImageDraw.Draw(pim)
# starting block pad, under everything
_sb = Image.new("L", pim.size, 0)
_sd = ImageDraw.Draw(_sb)
_sp = [tuple(p) for p in start_block["pts"]]
_w = 2 * start_block["half_w"]
_sd.line(_sp, fill=255, width=max(2, int(_w)))
for p in (_sp[0], _sp[-1]):
    _sd.ellipse([p[0] - _w / 2, p[1] - _w / 2, p[0] + _w / 2, p[1] + _w / 2], fill=255)
pim.paste((96, 178, 110), mask=_sb)
draw.polygon([tuple(p) for p in arrow["pts"]], fill=(255, 255, 255), outline=(0, 0, 0))

# draw at true physical scale: 1 mm lines, 3.2 mm peg holes
LINE_W = max(2, int(1.0 / MM_PER_PX))
HOLE_R = 1.6 / MM_PER_PX
for (lx, ly), col in zip(lanes, LANE_COLORS):
    draw.line(list(zip(lx, ly)), fill=col, width=LINE_W, joint="curve")
for hl, col in zip(holes, LANE_COLORS):
    for x, y in hl:
        draw.ellipse([x - HOLE_R, y - HOLE_R, x + HOLE_R, y + HOLE_R],
                     fill=(20, 20, 20), outline=col, width=4)
# group capsule outlines (under the text)
_outer = Image.new("L", pim.size, 0); _inner = Image.new("L", pim.size, 0)
_do, _di = ImageDraw.Draw(_outer), ImageDraw.Draw(_inner)
RING_W = 0.8 / MM_PER_PX
for ring in group_rings:
    rpts = [tuple(p) for p in ring["pts"]]
    for dr2, w in ((_do, 2 * ring["half_w"] + RING_W), (_di, 2 * ring["half_w"] - RING_W)):
        dr2.line(rpts, fill=255, width=max(2, int(w)), joint="curve")
        for p in (rpts[0], rpts[-1]):
            dr2.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=255)
_ringmask = np.array(_outer, bool) & ~np.array(_inner, bool)
pim.paste((250, 250, 250), mask=Image.fromarray((_ringmask * 255).astype(np.uint8)))

def _label_font(size_mm):
    try:
        from PIL import ImageFont
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc",
                                  max(12, int(size_mm / MM_PER_PX)))
    except Exception:
        return None
for lb in labels:
    draw.text((lb["x"], lb["y"]), lb["text"], fill=(255, 255, 255),
              font=_label_font(lb.get("size", LABEL_MM)),
              anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))

# map garnish from fetch_features.py, if present
if os.path.exists(f"data/features_{ACTIVE}.json"):
    feats = json.load(open(f"data/features_{ACTIVE}.json"))
    for rv in feats.get("rivers", []):
        rpts = [lonlat_to_px(lon, lat) for lon, lat in rv["pts"]]
        draw.line(rpts, fill=(80, 150, 215), width=max(2, int(0.7 / MM_PER_PX)), joint="curve")
    def _f(size_mm):
        try:
            from PIL import ImageFont as _IF
            return _IF.truetype("/System/Library/Fonts/Helvetica.ttc",
                                max(10, int(size_mm / MM_PER_PX)))
        except Exception:
            return None
    for path in feats.get("roads", []):
        pts = [lonlat_to_px(lon, lat) for lon, lat in path]
        draw.line(pts, fill=(75, 70, 65), width=max(2, int(0.5 / MM_PER_PX)), joint="curve")
    for b in feats.get("buoys", []):
        x, y = lonlat_to_px(b["lon"], b["lat"])
        r = 0.8 / MM_PER_PX
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(250, 250, 250), outline=(0, 0, 0))
    for kind, size, fill in [("places", 2.6, (255, 255, 255)),
                             ("islands", 2.0, (235, 235, 215)),
                             ("bays", 1.8, (170, 215, 240))]:
        fnt = _f(size)
        for p in feats.get(kind, []):
            x, y = lonlat_to_px(p["lon"], p["lat"])
            draw.text((x, y), p["name"], fill=fill, font=fnt, anchor="mm",
                      stroke_width=2, stroke_fill=(0, 0, 0))
board = pim.crop((cx0, cy0, cx1, cy1))
board.save("data/board_preview.png")
print("wrote data/board_preview.png", board.size)

draw.rectangle([cx0, cy0, cx1, cy1], outline=(255, 255, 255), width=6)
out = pim.resize((W // 2, H // 2), Image.LANCZOS)
out.save("data/route_prototype.png")
print("wrote data/route_prototype.png", out.size)
