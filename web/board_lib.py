"""File-free golf-board core, runs in Pyodide (numpy + Pillow). Given a DEM grid
and OSM golf polygons for a bbox, builds a colored relief board: terrain base +
turf layers as proud colored decals -> per-object geometry (for WebGL) and a
multicolor 3MF. Axis-aligned v1 (no rotation/detection/labels yet)."""
import numpy as np, io, json, math, zipfile
from PIL import Image, ImageDraw, ImageFont

ROUGH = (78, 120, 66)
# (name, color, proud_mm, kind, width_m) — drawn in order; later overwrites on overlap.
# "poly" fills closed ways (turf); "line" strokes open ways (roads/paths/rail) to width_m.
LAYERS = [("fairway",  (150, 200, 104), 0.5, "poly", 0),
          ("tee",      (118, 176, 120), 0.6, "poly", 0),
          ("green",    (198, 226, 128), 0.8, "poly", 0),
          ("bunker",   (238, 222, 170), 0.6, "poly", 0),
          ("road",     (96, 96, 104),  0.4, "line", 7.0),
          ("rail",     (70, 70, 78),   0.7, "line", 3.5),
          ("cartpath", (212, 200, 180), 0.5, "line", 2.4)]
WATER_COLOR = (58, 124, 190)
# ride-loop ribbon colors by kind (bike / motorcycle / scenic drive)
ROUTE_COLORS = {"bike": (240, 118, 44), "moto": (222, 62, 62), "drive": (245, 196, 66)}
SEA_LEVEL = 0.3          # m: cells below this are water (real bathymetry from NOAA topobathy)
PITCH = 0.5          # mesh pitch (mm) — finer = more resolution
EMBED = 0.2


def _point_at(pts, frac):
    """Point at `frac` of the arc length along a polyline of (x, y) tuples."""
    if len(pts) < 2:
        return pts[0]
    seg = [math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1)]
    tot = sum(seg)
    if tot == 0:
        return pts[0]
    target, acc = tot * frac, 0.0
    for i, d in enumerate(seg):
        if acc + d >= target:
            f = (target - acc) / d if d else 0
            return (pts[i][0] + f * (pts[i + 1][0] - pts[i][0]), pts[i][1] + f * (pts[i + 1][1] - pts[i][1]))
        acc += d
    return pts[-1]


def _declutter(labels, min_d, nx, ny, iters=80):
    """Nudge labels [num, x, y, fixed] apart so none sit closer than min_d. Fixed
    (user-placed) labels are not moved; only auto labels relax around them."""
    for _ in range(iters):
        moved = False
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                dx = labels[j][1] - labels[i][1]; dy = labels[j][2] - labels[i][2]
                d = math.hypot(dx, dy)
                if d < min_d:
                    if d < 1e-6:
                        dx, dy, d = 1.0, 0.0, 1.0          # exact overlap -> arbitrary push
                    fi, fj = labels[i][3], labels[j][3]
                    if fi and fj:
                        continue
                    ux, uy, g = dx / d, dy / d, min_d - d
                    if fi:
                        labels[j][1] += ux * g; labels[j][2] += uy * g
                    elif fj:
                        labels[i][1] -= ux * g; labels[i][2] -= uy * g
                    else:
                        labels[i][1] -= ux * g / 2; labels[i][2] -= uy * g / 2
                        labels[j][1] += ux * g / 2; labels[j][2] += uy * g / 2
                    moved = True
        if not moved:
            break
    for L in labels:                                       # keep on the board
        L[1] = min(max(L[1], 4), nx - 4); L[2] = min(max(L[2], 4), ny - 4)


def _erode(m, k):
    """k iterations of 4-neighbour binary erosion (numpy; no scipy needed)."""
    for _ in range(k):
        e = m.copy()
        e[1:, :] &= m[:-1, :]; e[:-1, :] &= m[1:, :]; e[:, 1:] &= m[:, :-1]; e[:, :-1] &= m[:, 1:]
        m = e
    return m


def _mesh(mask, ztop, zbot, BH, pitch):
    """Masked column mesher: top + bottom + perimeter walls. mask (ny,nx) bool;
    ztop/zbot (ny+1,nx+1) corner heights. Returns (verts f32 Nx3, tris u32 Mx3)."""
    ny, nx = mask.shape
    need = np.zeros((ny + 1, nx + 1), bool)
    need[:-1, :-1] |= mask; need[:-1, 1:] |= mask; need[1:, :-1] |= mask; need[1:, 1:] |= mask
    rr, cc = np.where(need)
    tid = np.full((ny + 1, nx + 1), -1, np.int64); bid = np.full((ny + 1, nx + 1), -1, np.int64)
    tid[rr, cc] = np.arange(len(rr)); bid[rr, cc] = np.arange(len(rr)) + len(rr)
    xs = cc * pitch; ys = BH - rr * pitch
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


def golf_board(dem_in, nrows, ncols, bbox, features_json, exag=4.0, base_mm=8.0,
               holes_json="[]", font_bytes=None, pitch=None, route_json="[]", route_kind="bike",
               hide_json="[]", route_w=2.4):
    P = float(pitch) if pitch else PITCH       # mesh pitch (mm); coarse for fast previews
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
    hide = set(json.loads(hide_json)) if hide_json else set()
    w, s, e, n = bbox
    clat = (s + n) / 2
    Wm = (e - w) * 111320 * math.cos(math.radians(clat))
    Hm = (n - s) * 111320
    if Wm >= Hm:
        BW, BH = 255.0, 255.0 * Hm / Wm
    else:
        BW, BH = 255.0 * Wm / Hm, 255.0
    ZPM = (255.0 / max(Wm, Hm)) * exag
    nyb, nxb = int(BH / P), int(BW / P)

    # corner heights sampled from the DEM (row0 = north for both)
    rr = np.clip((np.arange(nyb + 1) / nyb * (nrows - 1)).astype(int), 0, nrows - 1)
    cc = np.clip((np.arange(nxb + 1) / nxb * (ncols - 1)).astype(int), 0, ncols - 1)
    samp = dem[np.ix_(rr, cc)]
    # heights relative to the lowest LAND (so inland boards aren't lifted by absolute elevation);
    # ocean recesses at the SAME vertical scale as land (true bathymetry, incl. exaggeration),
    # floored at `recess` below base so deep water can't punch through the plate.
    land = samp >= 0.0
    datum = float(samp[land].min()) if land.any() else float(samp.min())
    recess = min(base_mm - 2.0, 6.0)
    land_z = base_mm + np.maximum(samp - datum, 0.0) * ZPM
    ocean_z = base_mm - np.minimum(np.maximum(-samp, 0.0) * ZPM, recess)
    Zt = np.where(samp >= 0.0, land_z, ocean_z).astype(np.float64)

    def ll_px(lon, lat):
        return ((lon - w) / (e - w) * nxb, (n - lat) / (n - s) * nyb)
    px_per_m = (255.0 / max(Wm, Hm)) / P            # board-grid pixels per ground metre

    # exclusive label grid (precedence by draw order; lines stroked over turf)
    img = Image.new("L", (nxb, nyb), 0)
    dr = ImageDraw.Draw(img)
    for i, (name, color, proud, kind, width_m) in enumerate(LAYERS):
        if name in hide:
            continue
        for way in feats.get(name, []):
            pts = [ll_px(lo, la) for lo, la in way]
            if kind == "poly" and len(pts) >= 3:
                dr.polygon(pts, fill=i + 1)
            elif kind == "line" and len(pts) >= 2:
                dr.line(pts, fill=i + 1, width=max(1, int(round(width_m * px_per_m))), joint="curve")
    lbl = np.array(img)

    objects = []
    Vb, Fb = _mesh(np.ones((nyb, nxb), bool), Zt, np.zeros_like(Zt), BH, P)
    objects.append(("rough", ROUGH, Vb, Fb))
    for i, (name, color, proud, kind, width_m) in enumerate(LAYERS):
        m = lbl == (i + 1)
        if m.any():
            V, F = _mesh(m, Zt + proud, Zt - EMBED, BH, P)
            objects.append((name, color, V, F))

    # water: OSM water polygons + ocean (DEM at/below sea level), flat blue, where no turf
    water = np.zeros((nyb, nxb), bool)
    if "water" not in hide:
        crr = np.clip(((np.arange(nyb) + 0.5) / nyb * (nrows - 1)).astype(int), 0, nrows - 1)
        ccc = np.clip(((np.arange(nxb) + 0.5) / nxb * (ncols - 1)).astype(int), 0, ncols - 1)
        cell = dem[np.ix_(crr, ccc)]
        wimg = Image.new("L", (nxb, nyb), 0); wd = ImageDraw.Draw(wimg)
        for way in feats.get("water", []):
            pts = [ll_px(lo, la) for lo, la in way]
            if len(pts) >= 3:
                wd.polygon(pts, fill=1)
        # water = below sea level (ocean, with real depth) + OSM lakes/ponds; blue, following Zt
        water = ((np.array(wimg) > 0) | (cell < SEA_LEVEL)) & (lbl == 0)
        if water.any():
            V, F = _mesh(water, Zt + 0.15, Zt - EMBED, BH, P)
            objects.append(("water", WATER_COLOR, V, F))

    # ride route: bold ribbon following the terrain, proud of everything else,
    # with a raised start-marker disc at the first track point
    route = json.loads(route_json) if route_json else []
    if len(route) >= 2:
        rimg = Image.new("L", (nxb, nyb), 0)
        rd2 = ImageDraw.Draw(rimg)
        rpts = [ll_px(lo, la) for lo, la in route]
        rw = max(2, int(round(float(route_w) / P)))      # ribbon width in mm on the board
        rd2.line(rpts, fill=1, width=rw, joint="curve")
        rmask = np.array(rimg) > 0
        if rmask.any():
            V, F = _mesh(rmask, Zt + 1.0, Zt - EMBED, BH, P)
            objects.append(("route", ROUTE_COLORS.get(route_kind, ROUTE_COLORS["bike"]), V, F))
        simg = Image.new("L", (nxb, nyb), 0)
        sd = ImageDraw.Draw(simg)
        sx, sy = rpts[0]
        sr = 2.6 / P
        sd.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=1)
        smask = np.array(simg) > 0
        if smask.any():
            V, F = _mesh(smask, Zt + 1.4, Zt - EMBED, BH, P)
            objects.append(("start", (245, 245, 245), V, F))

    # hole outlines (corridor boundary, kept on rough) + raised hole numbers
    holes = json.loads(holes_json) if (holes_json and "marks" not in hide) else []
    if holes:
        corr = Image.new("L", (nxb, nyb), 0); cd = ImageDraw.Draw(corr)
        cw = max(1, int(round(60.0 * px_per_m)))            # ~60 m playing corridor
        for h in holes:
            pts = [ll_px(lo, la) for lo, la in h["pts"]]
            if len(pts) >= 2:
                cd.line(pts, fill=1, width=cw, joint="curve")
        corr = np.array(corr) > 0
        outline = (corr & ~_erode(corr, max(1, int(round(1.4 / P))))) & (lbl == 0)
        if outline.any():
            V, F = _mesh(outline, Zt + 0.9, Zt - EMBED, BH, P)
            objects.append(("outline", (28, 64, 38), V, F))      # dark green

        raw_font = font_bytes.to_py() if hasattr(font_bytes, "to_py") else font_bytes
        if raw_font is not None:
            fpx = max(8, int(round(9.0 / P)))
            font = ImageFont.truetype(io.BytesIO(bytes(raw_font)), fpx)
            def place(pts_px):                       # prefer hole midpoint, but keep off water
                for t in (0.5, 0.45, 0.55, 0.4, 0.6, 0.35, 0.65, 0.3, 0.7):
                    x, y = _point_at(pts_px, t); xi, yi = int(x), int(y)
                    if 0 <= xi < nxb and 0 <= yi < nyb and not water[yi, xi]:
                        return (x, y)
                return _point_at(pts_px, 0.5)
            labels = []
            for h in holes:
                num = str(h.get("num") or "").strip()
                if not num:
                    continue
                if h.get("lx") is not None and h.get("ly") is not None:   # user-placed
                    x, y = ll_px(h["lx"], h["ly"]); labels.append([num, x, y, True])
                else:
                    mx, my = place([ll_px(lo, la) for lo, la in h["pts"]]); labels.append([num, mx, my, False])
            _declutter(labels, fpx * 1.5, nxb, nyb)        # push apart if too close
            nimg = Image.new("L", (nxb, nyb), 0); nd = ImageDraw.Draw(nimg)
            for L in labels:
                nd.text((L[1], L[2]), L[0], font=font, fill=1, anchor="mm")
            nmask = np.array(nimg) > 0
            if nmask.any():
                V, F = _mesh(nmask, Zt + 1.1, Zt - EMBED, BH, P)
                objects.append(("numbers", (245, 245, 245), V, F))

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
