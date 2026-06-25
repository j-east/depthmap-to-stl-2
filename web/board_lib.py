"""File-free golf-board core, runs in Pyodide (numpy + Pillow). Given a DEM grid
and OSM golf polygons for a bbox, builds a colored relief board: terrain base +
turf layers as proud colored decals -> per-object geometry (for WebGL) and a
multicolor 3MF. Axis-aligned v1 (no rotation/detection/labels yet)."""
import numpy as np, io, json, math, zipfile
from PIL import Image, ImageDraw

# layer -> (color, proud mm), low to high precedence
TURF = [("fairway", (150, 200, 104), 0.5),
        ("tee",     (118, 176, 120), 0.6),
        ("water",   (64, 132, 196), 0.3),
        ("bunker",  (238, 222, 170), 0.6),
        ("green",   (198, 226, 128), 0.8)]
ROUGH = (78, 120, 66)
PITCH = 0.6          # mesh pitch (mm)
EMBED = 0.2


def _mesh(mask, ztop, zbot, BH):
    """Masked column mesher: top + bottom + perimeter walls. mask (ny,nx) bool;
    ztop/zbot (ny+1,nx+1) corner heights. Returns (verts f32 Nx3, tris u32 Mx3)."""
    ny, nx = mask.shape
    need = np.zeros((ny + 1, nx + 1), bool)
    need[:-1, :-1] |= mask; need[:-1, 1:] |= mask; need[1:, :-1] |= mask; need[1:, 1:] |= mask
    rr, cc = np.where(need)
    tid = np.full((ny + 1, nx + 1), -1, np.int64); bid = np.full((ny + 1, nx + 1), -1, np.int64)
    tid[rr, cc] = np.arange(len(rr)); bid[rr, cc] = np.arange(len(rr)) + len(rr)
    xs = cc * PITCH; ys = BH - rr * PITCH
    V = np.concatenate([np.c_[xs, ys, ztop[rr, cc]], np.c_[xs, ys, zbot[rr, cc]]])
    r, c = np.where(mask)
    A, B, C, D = tid[r, c], tid[r, c + 1], tid[r + 1, c + 1], tid[r + 1, c]
    Ab, Bb, Cb, Db = bid[r, c], bid[r, c + 1], bid[r + 1, c + 1], bid[r + 1, c]
    F = [np.c_[A, D, C], np.c_[A, C, B], np.c_[Ab, Cb, Db], np.c_[Ab, Bb, Cb]]
    pad = np.zeros((ny + 2, nx + 2), bool); pad[1:-1, 1:-1] = mask
    for dr, dc, (o1r, o1c), (o2r, o2c) in [(-1, 0, (0, 0), (0, 1)), (1, 0, (1, 1), (1, 0)),
                                           (0, -1, (1, 0), (0, 0)), (0, 1, (0, 1), (1, 1))]:
        ed = mask & ~pad[1 + dr:ny + 1 + dr, 1 + dc:nx + 1 + dc]
        r2, c2 = np.where(ed)
        T1, T2 = tid[r2 + o1r, c2 + o1c], tid[r2 + o2r, c2 + o2c]
        B1, B2 = bid[r2 + o1r, c2 + o1c], bid[r2 + o2r, c2 + o2c]
        F += [np.c_[T1, T2, B2], np.c_[T1, B2, B1]]
    return V.astype(np.float32), np.concatenate(F).astype(np.uint32)


def golf_board(dem_in, nrows, ncols, bbox, features_json, exag=4.0, base_mm=8.0):
    raw = dem_in.to_py() if hasattr(dem_in, "to_py") else dem_in
    if not ncols:                       # raw is a float32 GeoTIFF (USGS 3DEP) -> decode
        dem = np.asarray(Image.open(io.BytesIO(bytes(raw))), dtype=np.float64)
        nrows, ncols = dem.shape
    else:                               # raw is a flat elevation array (local tests)
        dem = np.asarray(raw, dtype=np.float64).reshape(nrows, ncols)
    dem = np.where(dem < -1e10, np.nan, dem)        # 3DEP nodata sentinel
    if np.isnan(dem).any():
        dem = np.where(np.isnan(dem), np.nanmin(dem), dem)
    feats = json.loads(features_json)
    w, s, e, n = bbox
    clat = (s + n) / 2
    Wm = (e - w) * 111320 * math.cos(math.radians(clat))
    Hm = (n - s) * 111320
    if Wm >= Hm:
        BW, BH = 255.0, 255.0 * Hm / Wm
    else:
        BW, BH = 255.0 * Wm / Hm, 255.0
    ZPM = (255.0 / max(Wm, Hm)) * exag
    nyb, nxb = int(BH / PITCH), int(BW / PITCH)

    # corner heights sampled from the DEM (row0 = north for both)
    rr = np.clip((np.arange(nyb + 1) / nyb * (nrows - 1)).astype(int), 0, nrows - 1)
    cc = np.clip((np.arange(nxb + 1) / nxb * (ncols - 1)).astype(int), 0, ncols - 1)
    samp = dem[np.ix_(rr, cc)]
    datum = float(np.nanmin(dem))
    Zt = (base_mm + np.maximum(samp - datum, 0.0) * ZPM).astype(np.float64)

    def ll_px(lon, lat):
        return ((lon - w) / (e - w) * nxb, (n - lat) / (n - s) * nyb)

    # exclusive turf label grid (precedence by draw order)
    img = Image.new("L", (nxb, nyb), 0)
    dr = ImageDraw.Draw(img)
    for i, (name, _, _) in enumerate(TURF):
        for poly in feats.get(name, []):
            pts = [ll_px(lo, la) for lo, la in poly]
            if len(pts) >= 3:
                dr.polygon(pts, fill=i + 1)
    lbl = np.array(img)

    objects = []
    Vb, Fb = _mesh(np.ones((nyb, nxb), bool), Zt, np.zeros_like(Zt), BH)
    objects.append(("rough", ROUGH, Vb, Fb))
    for i, (name, color, proud) in enumerate(TURF):
        m = lbl == (i + 1)
        if m.any():
            V, F = _mesh(m, Zt + proud, Zt - EMBED, BH)
            objects.append((name, color, V, F))

    tmf = _make_3mf(objects)
    return {
        "objects": [{"name": nm, "color": "#%02X%02X%02X" % col,
                     "verts": V.tobytes(), "tris": F.tobytes(), "ntri": int(len(F))}
                    for nm, col, V, F in objects],
        "tmf": tmf, "board": [round(BW, 1), round(BH, 1)],
    }


def _xml_mesh(V, F):
    """Vectorized 3MF vertex/triangle serialization (np.char, C-level — fast at high tri counts)."""
    ca = np.char.add
    verts = ca(ca(ca('<vertex x="', np.char.mod('%.3f', V[:, 0])),
                  ca('" y="', np.char.mod('%.3f', V[:, 1]))),
               ca(ca('" z="', np.char.mod('%.3f', V[:, 2])), '"/>'))
    tris = ca(ca(ca('<triangle v1="', np.char.mod('%d', F[:, 0])),
                 ca('" v2="', np.char.mod('%d', F[:, 1]))),
              ca(ca('" v3="', np.char.mod('%d', F[:, 2])), '"/>'))
    return "".join(verts.tolist()), "".join(tris.tolist())


def _make_3mf(objects):
    parts, items = [], []
    for k, (name, color, V, F) in enumerate(objects):
        oid = k + 2
        mat = ('<basematerials id="%d"><base name="%s" displaycolor="#%02X%02X%02X"/></basematerials>'
               % (oid * 10, name, color[0], color[1], color[2]))
        vs, ts = _xml_mesh(V, F)
        parts.append(mat + '<object id="%d" name="%s" type="model" pid="%d" pindex="0"><mesh>'
                     '<vertices>%s</vertices><triangles>%s</triangles></mesh></object>'
                     % (oid, name, oid * 10, vs, ts))
        items.append('<item objectid="%d"/>' % oid)
    model = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             '<resources>' + "".join(parts) + '</resources><build>' + "".join(items) + '</build></model>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model", model)
    return buf.getvalue()
