#!/usr/bin/env python3
"""Build a multicolor relief display model of a golf region.

Objects (one filament each): rough (base slab), fairway, green, bunker,
water, cartpath, road, labels (hole numbers). Turf is drawn as proud
decals on the real terrain; paths/roads as raised lines. Also emits a 3D
colored render so the exaggerated elevation is visible.

Run: PYTHONPATH=.pydeps python3 scripts/make_golf_3mf.py
"""
import json, math, zipfile, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None

cfg = json.load(open("data/regions.json"))
ACTIVE = cfg["active"]
reg = cfg["regions"][ACTIVE]
MINLON, MINLAT, MAXLON, MAXLAT = reg["bbox"]
M_SRC = reg["src_m_per_px"]
DATUM_M = reg.get("datum_m", 0.0)
EXAG = float(reg.get("exag", 6.0))
BASE_MM = float(reg.get("base_mm", 8.0))
OUT = f"data/board_{ACTIVE}.3mf"

PITCH_B = 0.4      # base terrain mesh pitch (mm)
PITCH_F = 0.18     # decal / line mesh pitch (mm)

g = json.load(open(f"data/golf_{ACTIVE}.json"))
dem = np.array(Image.open(reg["src_file"]), dtype=np.float64)
dem = np.where(dem < -1e30, np.nan, dem)
dem = np.where(np.isnan(dem), np.nanmedian(dem), dem) - DATUM_M
H, W = dem.shape

BH = 255.0
BW = BH * W / H
MMPP = BH / H
ZPM = MMPP / M_SRC * EXAG
print(f"{ACTIVE}: board {BW:.0f} x {BH:.0f} mm, relief {dem.max()*ZPM:.1f} mm over {BASE_MM} mm base "
      f"(exag {EXAG}x)")

# turf paint layers, low->high precedence; (color, proud mm)
TURF = [
    ("fairway", (150, 200, 104), 0.5),
    ("tee",     (150, 200, 104), 0.5),
    ("water",   (64, 132, 196), 0.3),
    ("bunker",  (238, 222, 170), 0.6),
    ("green",   (198, 226, 128), 0.8),
]
PATHS = [("cartpath", (224, 214, 188), 0.45, 0.9),   # (name, color, proud, width mm)
         ("road",     (96, 96, 100), 0.5, 1.6),
         ("rail",     (132, 86, 60), 0.6, 1.4)]       # railroad: warm brown, distinct from road
ROUGH = (78, 120, 66)


def ll_fine(lon, lat):
    x_mm = (lon - MINLON) / (MAXLON - MINLON) * BW
    y_mm = (lat - MINLAT) / (MAXLAT - MINLAT) * BH
    return x_mm / PITCH_F, (BH - y_mm) / PITCH_F


nyf, nxf = int(BH / PITCH_F), int(BW / PITCH_F)

# exclusive turf label grid: 0 = rough, 1..len(TURF) = layers (later wins)
turf_img = Image.new("L", (nxf, nyf), 0)
td = ImageDraw.Draw(turf_img)
for i, (name, _, _) in enumerate(TURF):
    if name == "tee":   # tees share the fairway layer index
        idx = 1
    else:
        idx = i + 1
    for f in g["features"].get(name, []):
        pts = [ll_fine(lo, la) for lo, la in f["pts"]]
        if len(pts) >= 3:
            td.polygon(pts, fill=idx)
turf_lbl = np.array(turf_img)

# path masks (lines)
def path_mask(name, width_mm):
    im = Image.new("1", (nxf, nyf), 0)
    dr = ImageDraw.Draw(im)
    wpx = max(2, int(width_mm / PITCH_F))
    for p in g.get("paths", {}).get(name, []):
        pts = [ll_fine(lo, la) for lo, la in p["pts"]]
        if len(pts) >= 2:
            dr.line(pts, fill=1, width=wpx, joint="curve")
    return np.array(im, bool)

# ---------------- terrain sampling on the mesh grids ----------------
def elev_at_corner(rows, cols, pitch, ny, nx):
    x_mm = cols * pitch
    y_mm = BH - rows * pitch
    dc = np.clip((x_mm / BW * (W - 1)).astype(int), 0, W - 1)
    dr = np.clip(((BH - y_mm) / BH * (H - 1)).astype(int), 0, H - 1)
    return dem[dr, dc]

# ---------------- generic masked column mesher ----------------
def block_mesh(mask, ztop, zbot, pitch):
    ny, nx = mask.shape
    need = np.zeros((ny + 1, nx + 1), bool)
    need[:-1, :-1] |= mask; need[:-1, 1:] |= mask
    need[1:, :-1] |= mask;  need[1:, 1:] |= mask
    rr, cc = np.where(need)
    tid = np.full((ny + 1, nx + 1), -1, np.int64)
    bid = np.full((ny + 1, nx + 1), -1, np.int64)
    tid[rr, cc] = np.arange(len(rr))
    bid[rr, cc] = np.arange(len(rr)) + len(rr)
    xs = cc * pitch; ys = BH - rr * pitch
    V = np.concatenate([np.c_[xs, ys, ztop[rr, cc]], np.c_[xs, ys, zbot[rr, cc]]])
    r, c = np.where(mask)
    A, B = tid[r, c], tid[r, c + 1]
    C, D = tid[r + 1, c + 1], tid[r + 1, c]
    Ab, Bb, Cb, Db = bid[r, c], bid[r, c + 1], bid[r + 1, c + 1], bid[r + 1, c]
    F = [np.c_[A, D, C], np.c_[A, C, B], np.c_[Ab, Cb, Db], np.c_[Ab, Bb, Cb]]
    pad = np.zeros((ny + 2, nx + 2), bool); pad[1:-1, 1:-1] = mask
    for dr_, dc_, (o1r, o1c), (o2r, o2c) in [(-1, 0, (0, 0), (0, 1)), (1, 0, (1, 1), (1, 0)),
                                             (0, -1, (1, 0), (0, 0)), (0, 1, (0, 1), (1, 1))]:
        e = mask & ~pad[1 + dr_:ny + 1 + dr_, 1 + dc_:nx + 1 + dc_]
        r, c = np.where(e)
        T1, T2 = tid[r + o1r, c + o1c], tid[r + o2r, c + o2c]
        B1, B2 = bid[r + o1r, c + o1c], bid[r + o2r, c + o2c]
        F += [np.c_[T1, T2, B2], np.c_[T1, B2, B1]]
    return V.astype(np.float32), np.concatenate(F)


def surf_grid(pitch):
    ny, nx = int(BH / pitch), int(BW / pitch)
    rr, cc = np.meshgrid(np.arange(ny + 1), np.arange(nx + 1), indexing="ij")
    zt = BASE_MM + np.maximum(elev_at_corner(rr, cc, pitch, ny, nx), 0.0) * ZPM
    return ny, nx, zt


# fine surface, needed before carving the base for water
nyb, nxb, ztb = surf_grid(PITCH_B)
_, _, ztf = surf_grid(PITCH_F)

def decal(mask, proud):
    if not mask.any():
        return None
    return block_mesh(mask, ztf + proud, ztf - 0.15, PITCH_F)

# ---- water: a flat, level pond recessed into a carved basin (real water is
# level, not draped on the hillside like the turf decals) ----
WATER_IDX = 3
wmask_f = turf_lbl == WATER_IDX
water_mesh = None
if wmask_f.any():
    wz = float(np.percentile(ztf[:-1, :-1][wmask_f], 25))  # level near the low edge
    wtop = np.full_like(ztf, wz)
    water_mesh = block_mesh(wmask_f, wtop, np.full_like(ztf, wz - 1.2), PITCH_F)
    # carve the rough so terrain doesn't poke through the flat pond
    cb = Image.new("1", (nxb + 1, nyb + 1), 0)
    cd = ImageDraw.Draw(cb)
    for f in g["features"].get("water", []):
        pts = [( (lo - MINLON) / (MAXLON - MINLON) * BW / PITCH_B,
                 (BH - (la - MINLAT) / (MAXLAT - MINLAT) * BH) / PITCH_B) for lo, la in f["pts"]]
        if len(pts) >= 3:
            cd.polygon(pts, fill=1)
    carve = np.array(cb, bool)
    ztb[carve] = np.minimum(ztb[carve], wz - 0.25)

# base slab (rough), built after the basin is carved
V_base, F_base = block_mesh(np.ones((nyb, nxb), bool), ztb, np.zeros_like(ztb), PITCH_B)
objects = [("rough", "#4E7842", V_base, F_base)]
print(f"rough: {len(F_base):,} tris")

# turf decals (water handled separately above)
for i, (name, color, proud) in enumerate(TURF):
    if name in ("tee", "water"):
        continue  # tee merged into fairway idx 1; water is the flat pond
    idx = i + 1
    mesh = decal(turf_lbl == idx, proud)
    if mesh:
        objects.append((name, "#%02X%02X%02X" % color, *mesh))
        print(f"{name}: {len(mesh[1]):,} tris")
if water_mesh:
    objects.append(("water", "#%02X%02X%02X" % dict(((n, c) for n, c, _ in TURF))["water"],
                    *water_mesh))
    print(f"water: {len(water_mesh[1]):,} tris (flat pond at z {wz:.1f})")

for name, color, proud, wmm in PATHS:
    mesh = decal(path_mask(name, wmm), proud)
    if mesh:
        hexc = "#%02X%02X%02X" % color
        objects.append((name, hexc, *mesh))
        print(f"{name}: {len(mesh[1]):,} tris")

# hole-number labels at each green end
lbl_img = Image.new("1", (nxf, nyf), 0)
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", int(5.5 / PITCH_F))
except Exception:
    font = ImageFont.load_default()
for h in g["holes"]:
    if not h["ref"]:
        continue
    lo, la = h["pts"][-1]
    fx, fy = ll_fine(lo, la)
    stamp = Image.new("1", (120, 90), 0)
    ImageDraw.Draw(stamp).text((60, 45), str(h["ref"]), fill=1, font=font, anchor="mm")
    lbl_img.paste(1, (int(fx - stamp.width / 2), int(fy - stamp.height / 2)), stamp)
lmesh = decal(np.array(lbl_img, bool), 1.0)
if lmesh:
    objects.append(("labels", "#FFFFFF", *lmesh))
    print(f"labels: {len(lmesh[1]):,} tris")

# ---------------- write 3MF ----------------
def obj_xml(oid, name, color, V, F):
    mat = (f'<basematerials id="{oid * 10}"><base name="{name}" displaycolor="{color}"/>'
           f'</basematerials>')
    vs = "".join(f'<vertex x="{v[0]:.3f}" y="{v[1]:.3f}" z="{v[2]:.3f}"/>' for v in V)
    ts = "".join(f'<triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>' for f in F)
    return (mat + f'<object id="{oid}" name="{name}" type="model" pid="{oid*10}" pindex="0">'
            f'<mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object>')

parts = [obj_xml(n + 2, *o) for n, o in enumerate(objects)]
items = "".join(f'<item objectid="{n + 2}"/>' for n in range(len(objects)))
model = ('<?xml version="1.0" encoding="UTF-8"?>'
         '<model unit="millimeter" xml:lang="en-US" '
         'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
         '<resources>' + "".join(parts) + '</resources>'
         f'<build>{items}</build></model>')
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml",
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    z.writestr("_rels/.rels",
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel-1" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    z.writestr("3D/3dmodel.model", model)
print(f"wrote {OUT}: {os.path.getsize(OUT)/1e6:.1f} MB, {len(objects)} objects")

# ---------------- 3D colored render ----------------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = 4
rr, cc = np.meshgrid(np.arange(0, H, R), np.arange(0, W, R), indexing="ij")
Z = BASE_MM + np.maximum(dem[::R, ::R], 0.0) * ZPM
Xr = cc * MMPP; Yr = BH - rr * MMPP
# color grid: rasterize turf+paths at render resolution
ry, rx = Z.shape
col_im = Image.new("RGB", (rx, ry), ROUGH)
cd = ImageDraw.Draw(col_im)
def ll_rend(lon, lat):
    return ((lon - MINLON) / (MAXLON - MINLON) * rx,
            (MAXLAT - lat) / (MAXLAT - MINLAT) * ry)
for i, (name, color, _) in enumerate(TURF):
    for f in g["features"].get(name, []):
        pts = [ll_rend(lo, la) for lo, la in f["pts"]]
        if len(pts) >= 3:
            cd.polygon(pts, fill=color)
for name, color, _, wmm in PATHS:
    wpx = max(1, int(wmm / (BW / rx)))
    for p in g.get("paths", {}).get(name, []):
        pts = [ll_rend(lo, la) for lo, la in p["pts"]]
        if len(pts) >= 2:
            cd.line(pts, fill=color, width=wpx)
facec = np.asarray(col_im, np.float64)[:, :, :3] / 255
# hillshade modulation
gy, gx = np.gradient(Z)
sl = np.arctan(np.hypot(gx, gy) / (R * MMPP)); asp = np.arctan2(-gx, gy)
hsd = np.clip(math.sin(math.radians(45)) * np.cos(sl) +
              math.cos(math.radians(45)) * np.sin(sl) * np.cos(math.radians(315) - asp), 0, 1)
facec = np.clip(facec * (0.55 + 0.6 * hsd)[..., None], 0, 1)
facec = np.dstack([facec, np.ones(facec.shape[:2])])

fig = plt.figure(figsize=(11, 13), dpi=110)
ax = fig.add_subplot(projection="3d")
ax.plot_surface(Xr, Yr, Z, facecolors=facec, rstride=1, cstride=1,
                antialiased=False, shade=False, linewidth=0)
ax.set_box_aspect((BW, BH, Z.max() * 1.4))
ax.view_init(elev=42, azim=-118)
ax.set_axis_off(); ax.set_facecolor("#11151a"); fig.patch.set_facecolor("#11151a")
plt.tight_layout(pad=0)
plt.savefig("data/golf_3d.png", facecolor="#11151a", bbox_inches="tight", pad_inches=0.1)
print("wrote data/golf_3d.png")
