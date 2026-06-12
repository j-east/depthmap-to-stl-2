#!/usr/bin/env python3
"""Build the physical board terrain: 255 mm board, 10x exaggerated relief on a
10 mm slab with flat sea-level water (the playing surface). Exports a binary
STL plus 3D preview renders with the lanes/holes draped on top.

Run with: PYTHONPATH=.pydeps python3 scripts/make_terrain_stl.py
"""
import json, math
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

SRC = "data/foxisles_cudem.tif"
LANES = "data/route_lanes.json"
OUT_STL = "data/board_terrain.stl"

BASE_MM = 10.0          # sea level; land rises above, seafloor dips below
EXAG = 5.0              # vertical exaggeration
Z_FLOOR = 3.0           # deepest the seafloor may cut into the slab (mm)
M_PER_PX = 8.46         # source grid resolution (meters per px)

d = json.load(open(LANES))
MM_PER_PX = d["mm_per_px"]
cx0, cy0, cx1, cy1 = d.get("crop_px", [0, 0, d["grid"][0], d["grid"][1]])
SRC = d.get("src_file", SRC)
M_PER_PX = d.get("src_m_per_px", M_PER_PX)
DATUM_M = d.get("datum_m", 0.0)
EXAG = float(d.get("exag", EXAG))
DECIM = max(1, round(0.4 / MM_PER_PX))          # ~0.4 mm mesh resolution
Z_PER_M = MM_PER_PX / M_PER_PX * EXAG           # mm of height per meter of elevation

a = np.array(Image.open(SRC), dtype=np.float64)
a = np.where(a < -1e30, DATUM_M, a) - DATUM_M
H, W = a.shape
el = a[cy0:cy1:DECIM, cx0:cx1:DECIM]            # the crop IS the board
ny, nx = el.shape
z = np.maximum(BASE_MM + el * Z_PER_M, Z_FLOOR)  # real bathymetry below sea level
xs = np.arange(nx) * DECIM * MM_PER_PX
ys = ((cy1 - cy0) - 1 - np.arange(ny) * DECIM) * MM_PER_PX  # row 0 = north = +y
X, Y = np.meshgrid(xs, ys)
BOARD_H_MM = (cy1 - cy0) * MM_PER_PX
print(f"mesh {nx}x{ny}, board {xs[-1]:.0f} x {BOARD_H_MM:.0f} mm, "
      f"relief {z.max()-BASE_MM:.1f} mm above {BASE_MM:.0f} mm slab")

P = np.stack([X, Y, z], axis=-1).astype(np.float32)

def quads_to_tris(p00, p10, p01, p11):
    return np.concatenate([np.stack([p00, p10, p11], 1), np.stack([p00, p11, p01], 1)])

tris = [quads_to_tris(P[:-1, :-1].reshape(-1, 3), P[:-1, 1:].reshape(-1, 3),
                      P[1:, :-1].reshape(-1, 3), P[1:, 1:].reshape(-1, 3))]
# perimeter walls down to z=0, then a bottom plate
for edge, flip in [(P[0, :], False), (P[-1, :], True), (P[:, 0], True), (P[:, -1], False)]:
    top = edge.copy(); bot = edge.copy(); bot[:, 2] = 0
    a0, a1 = top[:-1], top[1:]
    b0, b1 = bot[:-1], bot[1:]
    t = np.concatenate([np.stack([a0, b0, b1], 1), np.stack([a0, b1, a1], 1)])
    if flip:
        t = t[:, ::-1]
    tris.append(t.astype(np.float32))
c = [[xs[0], ys[-1], 0], [xs[-1], ys[-1], 0], [xs[-1], ys[0], 0], [xs[0], ys[0], 0]]
tris.append(np.array([[c[0], c[2], c[1]], [c[0], c[3], c[2]]], dtype=np.float32))
T = np.concatenate(tris)

e1 = T[:, 1] - T[:, 0]; e2 = T[:, 2] - T[:, 0]
N = np.cross(e1, e2)
N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
rec = np.zeros(len(T), dtype=np.dtype([('n', '<3f4'), ('v', '<(3,3)f4'), ('a', '<u2')]))
rec['n'] = N; rec['v'] = T
with open(OUT_STL, 'wb') as f:
    f.write(b'deer isle cribbage terrain'.ljust(80, b'\0'))
    f.write(np.uint32(len(T)).tobytes())
    rec.tofile(f)
print(f"wrote {OUT_STL}: {len(T):,} triangles, {(84+50*len(T))/1e6:.0f} MB")

# ---------- 3D preview renders ----------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = 2  # extra decimation for the renderer
zr = z[::R, ::R]; Xr = X[::R, ::R]; Yr = Y[::R, ::R]; er = el[::R, ::R]
land = er > 0
gy, gx = np.gradient(zr, ys[R] - ys[0] if False else 1.0, 1.0)
gy, gx = np.gradient(zr)
slope = np.arctan(np.hypot(gx, gy) / (DECIM * R * MM_PER_PX))
aspect = np.arctan2(-gx, gy)
az, alt = math.radians(315), math.radians(45)
hs = np.clip(math.sin(alt) * np.cos(slope) + math.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
col = np.zeros(zr.shape + (4,))
emax = max(er.max(), 1.0)
e = np.clip(er, 0, emax) / emax
col[..., 0] = np.where(land, (0.32 + 0.55 * e), 0.13)
col[..., 1] = np.where(land, (0.52 - 0.10 * e), 0.36)
col[..., 2] = np.where(land, (0.28 - 0.08 * e), 0.55)
col[..., :3] *= np.where(land, 0.5 + 0.7 * hs, 1.0)[..., None]
# topographic contours: land every 20 m, depth every 15 m (engraved look)
gmagr = np.hypot(*np.gradient(er))
tolr = np.maximum(gmagr * 0.6, 0.05)
for L in np.arange(20, max(er.max(), 21), 20):
    m = land & (np.abs(er - L) < tolr)
    col[m, :3] *= 0.5
for L in np.arange(-15, min(er.min(), -16), -15):
    m = (~land) & (np.abs(er - L) < tolr)
    col[m, :3] = col[m, :3] * 0.5 + np.array([0.3, 0.55, 0.65]) * 0.5
col[..., 3] = 1.0
col = np.clip(col, 0, 1)

lane_colors = ['#e03232', '#f5d746', '#fafafa']

for name, (elev_deg, azim, xlim, ylim) in {
    "board_3d_overview": (55, -90, None, None),
    "board_3d_south": (28, -120, (20, 130), (0, 110)),
}.items():
    fig = plt.figure(figsize=(13, 13), dpi=110)
    ax = fig.add_subplot(projection='3d')
    ax.plot_surface(Xr, Yr, zr, facecolors=col, rstride=1, cstride=1,
                    antialiased=False, shade=False, linewidth=0)
    for (lxs, lys), lc in zip(d["lanes"], lane_colors):
        lx = (np.array(lxs) - cx0) * MM_PER_PX
        ly = (cy1 - np.array(lys)) * MM_PER_PX
        ax.plot(lx, ly, BASE_MM + 0.25, color=lc, linewidth=1.1, zorder=10)
    for hl, lc in zip(d["holes"], lane_colors):
        hx = (np.array([p[0] for p in hl]) - cx0) * MM_PER_PX
        hy = (cy1 - np.array([p[1] for p in hl])) * MM_PER_PX
        ax.scatter(hx, hy, BASE_MM + 0.3, color='k', edgecolors=lc, s=4, zorder=11, linewidths=0.4)
    for lb in d.get("labels", []):
        ax.text((lb["x"] - cx0) * MM_PER_PX, (cy1 - lb["y"]) * MM_PER_PX, BASE_MM + 1.2,
                lb["text"], color='white', fontsize=6 if len(lb["text"]) > 3 else 5,
                ha='center', va='center', zorder=12,
                path_effects=None)
    ax.set_box_aspect((xs[-1], BOARD_H_MM, (z.max()) * 1.0))
    ax.view_init(elev=elev_deg, azim=azim)
    if xlim: ax.set_xlim(*xlim)
    if ylim: ax.set_ylim(*ylim)
    ax.set_axis_off()
    ax.set_facecolor('#1a1a22'); fig.patch.set_facecolor('#1a1a22')
    plt.tight_layout(pad=0)
    out = f"data/{name}.png"
    plt.savefig(out, bbox_inches='tight', pad_inches=0.05)
    plt.close(fig)
    print("wrote", out)
