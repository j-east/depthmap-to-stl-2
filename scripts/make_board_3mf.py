#!/usr/bin/env python3
"""Build the multicolor cribbage board as a single 3MF for Bambu Studio (H2D).

Objects (assign a filament to each part after import):
  ocean/shoreline/land — terrain slab split at the datum: engraved depth
            contours, one-layer shoreline ring, 369 bored peg holes
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
OUT = None  # default: data/board_<region>.3mf

BASE_MM = 10.0       # datum height (land rises above, water floor dips below)
EXAG = 5.0           # vertical exaggeration
Z_FLOOR = 3.0        # deepest the seafloor may cut into the slab (mm)
SHORE_MM = 0.16      # one-layer shoreline accent ring at the waterline
M_PER_PX = 8.46      # source grid meters per px
PITCH_B = 0.35       # base mesh pitch (mm)
PITCH_F = 0.15       # ribbon/label mesh pitch (mm)
RIB_W = 1.2          # ribbon width (mm)
RIB_H = 0.5          # ribbon height above terrain (mm)
RIB_EMBED = 0.15     # ribbon embedment into the base (mm)
HOLE_R = 1.6         # peg hole radius (mm)
HOLE_DEPTH = 8.0     # peg hole depth below the surface at its center (mm)
GROOVE = 0.25        # contour engraving depth (mm)
TEXT_MM = 9.6        # label text height (mm) — big enough to print legibly

d = json.load(open(LANES))
MMPP = d["mm_per_px"]
cx0, cy0, cx1, cy1 = d["crop_px"]
SRC = d.get("src_file", SRC)
M_PER_PX = d.get("src_m_per_px", M_PER_PX)
DATUM_M = d.get("datum_m", 0.0)
EXAG = float(d.get("exag", EXAG))
OUT = OUT or f"data/board_{d.get('region', 'board')}.3mf"
BW = (cx1 - cx0) * MMPP   # board width (mm)
BH = (cy1 - cy0) * MMPP   # board height (mm)
ZPM = MMPP / M_PER_PX * EXAG

el_src = np.array(Image.open(SRC), dtype=np.float64)[cy0:cy1, cx0:cx1]
el_src = np.where(el_src < -1e30, DATUM_M, el_src) - DATUM_M  # datum-relative

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

# engrave contour grooves: depth lines on the seafloor, topo lines on land,
# both at intervals adapted to the region's relief
gmag = np.hypot(*np.gradient(el_c))
tol = np.maximum(gmag * 0.9, 0.02)
if el_c.min() < 0:
    wi = next(c for c in (15, 25, 50, 100, 200, 500) if -el_c.min() / c <= 10)
    for L in np.arange(-wi, el_c.min(), -wi):
        ztop[(el_c <= 0) & (np.abs(el_c - L) < tol)] -= GROOVE
if el_c.max() > 0:
    ci = next(c for c in (20, 25, 50, 100, 200, 250, 500, 1000) if el_c.max() / c <= 16)
    for L in np.arange(ci, el_c.max(), ci):
        ztop[(el_c > 0) & (np.abs(el_c - L) < tol)] -= GROOVE
    print(f"topo lines every {ci} m")

# bored peg holes: a plain vertical bore into the local surface (no pad —
# on slopes the rim is slightly slanted, which pegs don't mind)
holes_mm = [px_to_mm(x, y) for hl in d["holes"] for x, y in hl]
for hx, hy in holes_mm:
    c0 = int(hx / PITCH_B); r0 = int((BH - hy) / PITCH_B)
    w = int(HOLE_R / PITCH_B) + 2
    rs, re = max(0, r0 - w), min(nyb + 1, r0 + w + 1)
    cs, ce = max(0, c0 - w), min(nxb + 1, c0 + w + 1)
    lx = ccol[cs:ce] * PITCH_B; ly = BH - crow[rs:re] * PITCH_B
    DX, DY = np.meshgrid(lx - hx, ly - hy)
    bore = np.hypot(DX, DY) <= HOLE_R
    if not bore.any():
        continue
    zc = float(ztop[min(r0, nyb), min(c0, nxb)])
    floor = max(zc - HOLE_DEPTH, 1.2)
    ztop[rs:re, cs:ce][bore] = np.minimum(ztop[rs:re, cs:ce][bore], floor)

# ---- split the slab at the datum: ocean below, a one-layer shoreline ring
# at the waterline, land above — three parts, three filaments ----
zsea = np.minimum(ztop, BASE_MM)
V_sea, F_sea = block_mesh(np.ones((nyb, nxb), bool), zsea,
                          np.zeros_like(ztop), PITCH_B)
cmax = np.maximum(np.maximum(ztop[:-1, :-1], ztop[:-1, 1:]),
                  np.maximum(ztop[1:, :-1], ztop[1:, 1:]))
cmin = np.minimum(np.minimum(ztop[:-1, :-1], ztop[:-1, 1:]),
                  np.minimum(ztop[1:, :-1], ztop[1:, 1:]))
shore_mask = cmax > BASE_MM + 0.001
V_sh, F_sh = block_mesh(shore_mask, np.clip(ztop, BASE_MM, BASE_MM + SHORE_MM),
                        np.full_like(ztop, BASE_MM), PITCH_B)

# optional alpine band: land above the region's snowline gets its own color
try:
    _reg = json.load(open("data/regions.json"))["regions"][d.get("region", "")]
    SNOWLINE_M = _reg.get("snowline_m")
except Exception:
    SNOWLINE_M = None
SNOW_Z = BASE_MM + (SNOWLINE_M - DATUM_M) * ZPM if SNOWLINE_M else None

land_top = np.clip(ztop, BASE_MM, SNOW_Z) if SNOW_Z else ztop
land_mask = cmin > BASE_MM + SHORE_MM + 0.02
V_land, F_land = block_mesh(land_mask, np.maximum(land_top, BASE_MM + SHORE_MM),
                            np.full_like(ztop, BASE_MM + SHORE_MM), PITCH_B)
alpine = None
if SNOW_Z:
    alp_mask = cmin > SNOW_Z + 0.02
    if alp_mask.any():
        alpine = block_mesh(alp_mask, np.maximum(ztop, SNOW_Z),
                            np.full_like(ztop, SNOW_Z), PITCH_B)
print(f"ocean: {len(V_sea):,} verts, {len(F_sea):,} tris "
      f"({BW:.0f} x {BH:.0f} mm, floor down to {zsea.min():.1f} mm)")
print(f"shore: {len(V_sh):,} verts, {len(F_sh):,} tris (one {SHORE_MM} mm layer at the waterline)")
print(f"land:  {len(V_land):,} verts, {len(F_land):,} tris "
      f"(up to {land_top.max():.1f} mm)")
if alpine:
    print(f"alpine: {len(alpine[0]):,} verts, {len(alpine[1]):,} tris "
          f"(above {SNOWLINE_M} m -> z {SNOW_Z:.1f}..{ztop.max():.1f} mm)")

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

HOLE_COLLARS = True   # each lane rims its OWN holes in its color

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
    if HOLE_COLLARS:
        # ring this lane's own hole mouths in the lane color
        own = [px_to_mm(x, y) for x, y in d["holes"][k]]
        rco = (HOLE_R + 0.6) / PITCH_F
        rbo = (HOLE_R + 0.05) / PITCH_F
        for hx, hy in own:
            px_, py_ = hx / PITCH_F, (BH - hy) / PITCH_F
            dr.ellipse([px_ - rco, py_ - rco, px_ + rco, py_ + rco], fill=1)
        for hx, hy in own:
            px_, py_ = hx / PITCH_F, (BH - hy) / PITCH_F
            dr.ellipse([px_ - rbo, py_ - rbo, px_ + rbo, py_ + rbo], fill=0)
    return img

FEATS = {}
import os as _os
_fp = f"data/features_{d.get('region', '')}.json"
if _os.path.exists(_fp):
    FEATS = json.load(open(_fp))

def punch_holes(arr):
    """No raised garnish may ever print over a peg hole."""
    punch = Image.new("1", (nxf, nyf), 0)
    dp = ImageDraw.Draw(punch)
    rp = (HOLE_R + 0.5) / PITCH_F
    for hx, hy in holes_mm:
        px_, py_ = hx / PITCH_F, (BH - hy) / PITCH_F
        dp.ellipse([px_ - rp, py_ - rp, px_ + rp, py_ + rp], fill=1)
    return arr & ~np.array(punch, bool)

def ll_to_mm(lon, lat):
    bx = d["bbox"]; GW, GH = d["grid"]
    px_ = (lon - bx[0]) / (bx[2] - bx[0]) * GW
    py_ = (bx[3] - lat) / (bx[3] - bx[1]) * GH
    return px_to_mm(px_, py_)

def _font(size_mm):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc",
                                  int(size_mm / PITCH_F))
    except Exception:
        return ImageFont.load_default()

def stamp_text(img, text, x_mm, y_mm, size_mm, ang=0.0):
    font = _font(size_mm)
    w = int(len(text) * size_mm / PITCH_F) + 60
    stamp = Image.new("1", (w, int(2.2 * size_mm / PITCH_F)), 0)
    sd = ImageDraw.Draw(stamp)
    sd.text((stamp.width // 2, stamp.height // 2), text, fill=1, font=font, anchor="mm")
    if ang:
        stamp = stamp.rotate(ang, expand=True, fillcolor=0)
    img.paste(1, (int(x_mm / PITCH_F - stamp.width / 2),
                  int((BH - y_mm) / PITCH_F - stamp.height / 2)), stamp)

def labels_mask():
    img = Image.new("1", (nxf, nyf), 0)
    dr = ImageDraw.Draw(img)
    for lb in d.get("labels", []):
        ang = ((lb["angle"] + 90) % 180) - 90  # keep text upright-ish
        x_mm, y_mm = px_to_mm(lb["x"], lb["y"])
        stamp_text(img, lb["text"], x_mm, y_mm, lb.get("size", TEXT_MM), ang)
    # map garnish: place/island/water names + buoy dots
    for kind, size in [("places", 2.6), ("islands", 2.0), ("bays", 1.8)]:
        for p in FEATS.get(kind, []):
            x_mm, y_mm = ll_to_mm(p["lon"], p["lat"])
            if 2 < x_mm < BW - 2 and 2 < y_mm < BH - 2:
                stamp_text(img, p["name"], x_mm, y_mm, size)
    rb = int(0.8 / PITCH_F)
    for b in FEATS.get("buoys", []):
        x_mm, y_mm = ll_to_mm(b["lon"], b["lat"])
        px_, py_ = x_mm / PITCH_F, (BH - y_mm) / PITCH_F
        dr.ellipse([px_ - rb, py_ - rb, px_ + rb, py_ + rb], fill=1)
    # capsule outline around each group of 5
    arr = np.array(img, bool)
    rings = d.get("group_rings", [])
    if rings:
        outer = Image.new("L", (nxf, nyf), 0); inner = Image.new("L", (nxf, nyf), 0)
        dro, dri = ImageDraw.Draw(outer), ImageDraw.Draw(inner)
        for ring in rings:
            pts = []
            for gx, gy in ring["pts"]:
                x_mm, y_mm = px_to_mm(gx, gy)
                pts.append((x_mm / PITCH_F, (BH - y_mm) / PITCH_F))
            hw_f = ring["half_w"] * MMPP / PITCH_F
            for dr2, w in ((dro, 2 * hw_f + 0.8 / PITCH_F), (dri, 2 * hw_f - 0.8 / PITCH_F)):
                dr2.line(pts, fill=255, width=max(2, int(w)), joint="curve")
                for p in (pts[0], pts[-1]):
                    dr2.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=255)
        arr |= np.array(outer, bool) & ~np.array(inner, bool)
    return punch_holes(arr)

def roads_mask():
    img = Image.new("1", (nxf, nyf), 0)
    dr = ImageDraw.Draw(img)
    wpx = max(2, int(0.5 / PITCH_F))
    for path in FEATS.get("roads", []):
        pts = []
        for lon, lat in path:
            x_mm, y_mm = ll_to_mm(lon, lat)
            pts.append((x_mm / PITCH_F, (BH - y_mm) / PITCH_F))
        if len(pts) > 1:
            dr.line(pts, fill=1, width=wpx, joint="curve")
    return punch_holes(np.array(img, bool))

def rivers_mask():
    img = Image.new("1", (nxf, nyf), 0)
    dr = ImageDraw.Draw(img)
    wpx = max(2, int(0.7 / PITCH_F))
    for rv in FEATS.get("rivers", []):
        pts = []
        for lon, lat in rv["pts"]:
            x_mm, y_mm = ll_to_mm(lon, lat)
            pts.append((x_mm / PITCH_F, (BH - y_mm) / PITCH_F))
        if len(pts) > 1:
            dr.line(pts, fill=1, width=wpx, joint="curve")
    return punch_holes(np.array(img, bool))

objects = [("ocean", "#2E6FA3", V_sea, F_sea),
           ("shoreline", "#E2CF9C", V_sh, F_sh),
           ("land", "#6B7F5E", V_land, F_land)]
if alpine:
    objects.append(("alpine", "#F2F3F5", *alpine))

# starting block: filled colored pad under the 2x3 start rows
sb = d.get("start_block")
if sb:
    sbm = Image.new("L", (nxf, nyf), 0)
    sd = ImageDraw.Draw(sbm)
    spts = []
    for gx, gy in sb["pts"]:
        x_mm, y_mm = px_to_mm(gx, gy)
        spts.append((x_mm / PITCH_F, (BH - y_mm) / PITCH_F))
    w = 2 * sb["half_w"] * MMPP / PITCH_F
    sd.line(spts, fill=255, width=max(2, int(w)))
    for p in (spts[0], spts[-1]):
        sd.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=255)
    sbmesh = mask_mesh(punch_holes(np.array(sbm, bool)), proud=0.4, embed=0.12)
    if sbmesh:
        objects.append(("start_block", "#4CAF50", *sbmesh))
        print(f"start_block: {len(sbmesh[0]):,} verts, {len(sbmesh[1]):,} tris")
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
rm = mask_mesh(roads_mask(), proud=0.22, embed=0.10)
if rm:
    objects.append(("roads", "#4A4A4A", *rm))
    print(f"roads: {len(rm[0]):,} verts, {len(rm[1]):,} tris")
rv = mask_mesh(rivers_mask(), proud=0.18, embed=0.12)
if rv:
    objects.append(("rivers", "#4FA3D9", *rv))
    print(f"rivers: {len(rv[0]):,} verts, {len(rv[1]):,} tris")

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
