#!/usr/bin/env python3
"""Build the multicolor cribbage board as a single 3MF for Bambu Studio (H2D).

Objects (assign a filament to each part after import):
  base    — terrain slab: 10x relief, engraved depth contours, counterbore
            pads + 369 bored peg holes
  lane_red / lane_gold / lane_white — raised track ribbons (0.5 mm proud),
            interrupted at each peg hole
  labels  — raised START/END + every-5 counts

Everything is rasterized column geometry on regular grids — no CSG.
Run: python3 scripts/make_board_3mf.py
"""
import json, math, zipfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None

SRC = "data/foxisles_cudem.tif"
LANES = "data/route_lanes.json"
OUT = "data/deer_isle_board.3mf"

BASE_MM = 10.0       # sea-level height (land rises above, seafloor dips below)
EXAG = 5.0           # vertical exaggeration
Z_FLOOR = 3.0        # deepest the seafloor may cut into the slab (mm)
M_PER_PX = 8.46      # source grid meters per px
PITCH_B = 0.35       # base mesh pitch (mm)
PITCH_F = 0.15       # ribbon/label mesh pitch (mm)
RIB_W = 1.2          # ribbon width (mm)
RIB_H = 0.5          # ribbon height above terrain (mm)
RIB_EMBED = 0.15     # ribbon embedment into the base (mm)
HOLE_R = 1.6         # peg hole radius (mm)
HOLE_DEPTH = 8.0     # peg hole depth below its pad (mm)
PAD_R = 2.4          # counterbore pad radius (mm)
GROOVE = 0.25        # contour engraving depth (mm)
TEXT_MM = 3.2        # label text height (mm)

d = json.load(open(LANES))
MMPP = d["mm_per_px"]
cx0, cy0, cx1, cy1 = d["crop_px"]
BW = (cx1 - cx0) * MMPP   # board width (mm)
BH = (cy1 - cy0) * MMPP   # board height (mm)
ZPM = MMPP / M_PER_PX * EXAG

el_src = np.array(Image.open(SRC), dtype=np.float64)[cy0:cy1, cx0:cx1]
el_src = np.where(el_src < -1e30, 0.0, el_src)

def px_to_mm(px, py):
    return (np.asarray(px) - cx0) * MMPP, (cy1 - np.asarray(py)) * MMPP

def sample_el(x_mm, y_mm):
    """Nearest-neighbor elevation (m) at board mm coords."""
    sx = np.clip((x_mm / MMPP).astype(int), 0, el_src.shape[1] - 1)
    sy = np.clip(((BH - y_mm) / MMPP).astype(int), 0, el_src.shape[0] - 1)
    return el_src[sy, sx]

def surface_z(x_mm, y_mm):
    # real bathymetry: negative elevation carves below the waterline
    return np.maximum(BASE_MM + sample_el(x_mm, y_mm) * ZPM, Z_FLOOR)

# ---------------- generic masked column mesher ----------------
def block_mesh(mask, ztop, zbot, pitch):
    """mask: (ny,nx) cells; ztop/zbot: (ny+1,nx+1) corner z. Returns V,F.
    Corner (r,c) -> x = c*pitch, y = BH - r*pitch (row 0 = north)."""
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
    F = [np.c_[A, D, C], np.c_[A, C, B],          # top (+z)
         np.c_[Ab, Cb, Db], np.c_[Ab, Bb, Cb]]    # bottom (-z)
    pad = np.zeros((ny + 2, nx + 2), bool); pad[1:-1, 1:-1] = mask
    edges = [  # (neighbor row off, col off, corner1(r,c), corner2(r,c))
        (-1, 0, (0, 0), (0, 1)),   # north: corners (r,c)-(r,c+1)
        (1, 0, (1, 1), (1, 0)),    # south
        (0, -1, (1, 0), (0, 0)),   # west
        (0, 1, (0, 1), (1, 1)),    # east
    ]
    for dr, dc, (o1r, o1c), (o2r, o2c) in edges:
        e = mask & ~pad[1 + dr:ny + 1 + dr, 1 + dc:nx + 1 + dc]
        r, c = np.where(e)
        T1, T2 = tid[r + o1r, c + o1c], tid[r + o2r, c + o2c]
        B1, B2 = bid[r + o1r, c + o1c], bid[r + o2r, c + o2c]
        F += [np.c_[T1, T2, B2], np.c_[T1, B2, B1]]
    return V.astype(np.float32), np.concatenate(F)

# ---------------- base ----------------
nyb, nxb = int(round(BH / PITCH_B)), int(round(BW / PITCH_B))
crow = np.arange(nyb + 1); ccol = np.arange(nxb + 1)
CX, CY = np.meshgrid(ccol * PITCH_B, BH - crow * PITCH_B)
el_c = sample_el(CX, CY)
ztop = np.maximum(BASE_MM + el_c * ZPM, Z_FLOOR)

# engrave depth contours along the seafloor surface (every 15 m)
gmag = np.hypot(*np.gradient(el_c))
tol = np.maximum(gmag * 0.6, 0.02)
for L in np.arange(-15, el_c.min(), -15):
    ztop[(el_c <= 0) & (np.abs(el_c - L) < tol)] -= GROOVE

# counterbore pads + bored peg holes
holes_mm = [px_to_mm(x, y) for hl in d["holes"] for x, y in hl]
ir, ic = np.meshgrid(np.arange(nyb + 1), np.arange(ncol := nxb + 1), indexing="ij")
for hx, hy in holes_mm:
    c0 = int(hx / PITCH_B); r0 = int((BH - hy) / PITCH_B)
    w = int(PAD_R / PITCH_B) + 2
    rs, re = max(0, r0 - w), min(nyb + 1, r0 + w + 1)
    cs, ce = max(0, c0 - w), min(nxb + 1, c0 + w + 1)
    lx = ccol[cs:ce] * PITCH_B; ly = BH - crow[rs:re] * PITCH_B
    DX, DY = np.meshgrid(lx - hx, ly - hy)
    dist = np.hypot(DX, DY)
    pad = dist <= PAD_R
    if not pad.any():
        continue
    zpad = float(ztop[rs:re, cs:ce][pad].min())
    ztop[rs:re, cs:ce][pad] = zpad
    bore = dist <= HOLE_R
    ztop[rs:re, cs:ce][bore] = max(zpad - HOLE_DEPTH, 1.2)

# ---- split the slab at the datum: everything below sea level is OCEAN
# (its own object -> its own filament), land columns rise above it ----
zsea = np.minimum(ztop, BASE_MM)
V_sea, F_sea = block_mesh(np.ones((nyb, nxb), bool), zsea,
                          np.zeros_like(ztop), PITCH_B)
cmin = np.minimum(np.minimum(ztop[:-1, :-1], ztop[:-1, 1:]),
                  np.minimum(ztop[1:, :-1], ztop[1:, 1:]))
land_mask = cmin > BASE_MM + 0.02
V_land, F_land = block_mesh(land_mask, np.maximum(ztop, BASE_MM),
                            np.full_like(ztop, BASE_MM), PITCH_B)
print(f"ocean: {len(V_sea):,} verts, {len(F_sea):,} tris "
      f"({BW:.0f} x {BH:.0f} mm, seafloor down to {zsea.min():.1f} mm)")
print(f"land:  {len(V_land):,} verts, {len(F_land):,} tris "
      f"(relief to {ztop.max():.1f} mm)")

# ---------------- ribbons + labels (fine grid) ----------------
nyf, nxf = int(round(BH / PITCH_F)), int(round(BW / PITCH_F))

def fine_corner_surface():
    fc = np.meshgrid(np.arange(nxf + 1) * PITCH_F, BH - np.arange(nyf + 1) * PITCH_F)
    return surface_z(fc[0], fc[1])

zsurf_f = fine_corner_surface()

def mask_mesh(img, proud=RIB_H, embed=RIB_EMBED):
    m = np.array(img, bool)[:nyf, :nxf]
    if not m.any():
        return None
    return block_mesh(m, zsurf_f + proud, zsurf_f - embed, PITCH_F)

def lane_mask(k):
    img = Image.new("1", (nxf, nyf), 0)
    dr = ImageDraw.Draw(img)
    lx, ly = d["lanes"][k]
    xm, ym = px_to_mm(np.array(lx), np.array(ly))
    pts = list(zip(xm / PITCH_F, (BH - ym) / PITCH_F))
    dr.line(pts, fill=1, width=max(2, int(RIB_W / PITCH_F)), joint="curve")
    rcut = int((HOLE_R + 0.3) / PITCH_F)
    for hx, hy in holes_mm:  # part the ribbon around every hole
        px_, py_ = hx / PITCH_F, (BH - hy) / PITCH_F
        dr.ellipse([px_ - rcut, py_ - rcut, px_ + rcut, py_ + rcut], fill=0)
    return img

def labels_mask():
    img = Image.new("1", (nxf, nyf), 0)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc",
                                  int(TEXT_MM / PITCH_F))
    except Exception:
        font = ImageFont.load_default()
    for lb in d.get("labels", []):
        ang = ((lb["angle"] + 90) % 180) - 90  # keep text upright-ish
        stamp = Image.new("1", (300, 120), 0)
        sd = ImageDraw.Draw(stamp)
        sd.text((150, 60), lb["text"], fill=1, font=font, anchor="mm")
        stamp = stamp.rotate(ang, expand=True, fillcolor=0)
        x_mm, y_mm = px_to_mm(lb["x"], lb["y"])
        px_, py_ = int(x_mm / PITCH_F - stamp.width / 2), int((BH - y_mm) / PITCH_F - stamp.height / 2)
        img.paste(1, (px_, py_), stamp)
    return img

objects = [("ocean", "#2E6FA3", V_sea, F_sea),
           ("land", "#6B7F5E", V_land, F_land)]
for k, (name, color) in enumerate([("lane_red", "#E03232"),
                                   ("lane_gold", "#F0C832"),
                                   ("lane_white", "#F5F5F0")]):
    mm_ = mask_mesh(lane_mask(k))
    if mm_:
        objects.append((name, color, *mm_))
        print(f"{name}: {len(mm_[0]):,} verts, {len(mm_[1]):,} tris")
lm = mask_mesh(labels_mask())
if lm:
    objects.append(("labels", "#F5F5F0", *lm))
    print(f"labels: {len(lm[0]):,} verts, {len(lm[1]):,} tris")

# ---------------- write 3MF ----------------
def obj_xml(oid, name, color, V, F):
    mat = (f'<basematerials id="{oid * 10}">'
           f'<base name="{name}" displaycolor="{color}"/></basematerials>')
    vs = "".join(f'<vertex x="{v[0]:.3f}" y="{v[1]:.3f}" z="{v[2]:.3f}"/>' for v in V)
    ts = "".join(f'<triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>' for f in F)
    return (mat + f'<object id="{oid}" name="{name}" type="model" pid="{oid * 10}" pindex="0">'
            f'<mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object>')

parts, items = [], []
for n, (name, color, V, F) in enumerate(objects):
    oid = n + 2
    parts.append(obj_xml(oid, name, color, V, F))
    items.append(f'<item objectid="{oid}"/>')

model = ('<?xml version="1.0" encoding="UTF-8"?>'
         '<model unit="millimeter" xml:lang="en-US" '
         'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
         '<resources>' + "".join(parts) + '</resources>'
         '<build>' + "".join(items) + '</build></model>')

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

import os
print(f"wrote {OUT}: {os.path.getsize(OUT)/1e6:.1f} MB, {len(objects)} objects")
