#!/usr/bin/env python3
"""Peg options for the board: lathe-revolved profiles sized to the as-built
holes (Ø3.2 x ~7 mm usable) and the 4.14 mm adjacent-hole pitch, which caps
head diameter at ~3.9 mm so neighboring pegs can't clash.

Outputs data/pegs.3mf with three styles side by side; print 3 of your pick
per player color (plus a spare). Print standing up with a brim.
"""
import zipfile, math, os
import numpy as np

SHAFT_R = 1.425   # Ø2.85 shaft for a Ø3.2 printed hole
HEAD_R = 1.95     # Ø3.9 max head (adjacent holes are 4.14 mm apart)

# profiles: (radius, z) from the tip up; r=0 at both ends closes the solid
SHAFT = [(0.0, 0.0), (0.9, 0.0), (SHAFT_R, 0.6), (SHAFT_R, 7.0)]
STYLES = {
    "peg_classic": SHAFT + [
        (HEAD_R, 7.7), (1.80, 9.0), (1.80, 13.2),         # collar + grip
        (HEAD_R, 14.0), (1.55, 15.4), (0.9, 16.0), (0.0, 16.3)],   # dome
    "peg_ball": SHAFT + [
        (HEAD_R, 7.7), (1.25, 9.6), (1.10, 12.0),         # waisted neck
        (1.62, 12.6), (HEAD_R, 13.9), (1.62, 15.2), (0.9, 15.8), (0.0, 16.0)],
    "peg_buoy": SHAFT + [
        (HEAD_R, 7.7), (HEAD_R, 8.6),                     # base band
        (1.0, 13.8), (1.0, 14.4),                         # cone + waist
        (1.45, 15.0), (1.45, 15.9), (0.8, 16.6), (0.0, 16.9)],  # buoy top
}
COLORS = {"peg_classic": "#E03232", "peg_ball": "#F0C832", "peg_buoy": "#F5F5F0"}
SEGS = 40

def lathe(profile, x_off):
    pts = [(r, z) for r, z in profile]
    rings, V = [], []
    for r, z in pts:
        if r <= 1e-9:
            rings.append(("apex", len(V))); V.append([x_off, 0.0, z])
        else:
            idx = len(V)
            for s in range(SEGS):
                a = 2 * math.pi * s / SEGS
                V.append([x_off + r * math.cos(a), r * math.sin(a), z])
            rings.append(("ring", idx))
    F = []
    for i in range(len(rings) - 1):
        (ka, ia), (kb, ib) = rings[i], rings[i + 1]
        if ka == "ring" and kb == "ring":
            for s in range(SEGS):
                s2 = (s + 1) % SEGS
                F += [[ia + s, ia + s2, ib + s2], [ia + s, ib + s2, ib + s]]
        elif ka == "apex" and kb == "ring":      # bottom fan (faces down)
            for s in range(SEGS):
                F.append([ia, ib + (s + 1) % SEGS, ib + s])
        elif ka == "ring" and kb == "apex":      # top fan (faces up)
            for s in range(SEGS):
                F.append([ib, ia + s, ia + (s + 1) % SEGS])
    return np.array(V, np.float32), np.array(F, np.int64)

objects = []
for n, (name, prof) in enumerate(STYLES.items()):
    V, F = lathe(prof, x_off=n * 8.0)
    objects.append((name, COLORS[name], V, F))
    print(f"{name}: {len(V)} verts, {len(F)} tris, height {max(z for _, z in prof):.1f} mm")

def obj_xml(oid, name, color, V, F):
    mat = (f'<basematerials id="{oid * 10}">'
           f'<base name="{name}" displaycolor="{color}"/></basematerials>')
    vs = "".join(f'<vertex x="{v[0]:.3f}" y="{v[1]:.3f}" z="{v[2]:.3f}"/>' for v in V)
    ts = "".join(f'<triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>' for f in F)
    return (mat + f'<object id="{oid}" name="{name}" type="model" pid="{oid * 10}" pindex="0">'
            f'<mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh></object>')

parts = [obj_xml(n + 2, *o) for n, o in enumerate(objects)]
items = "".join(f'<item objectid="{n + 2}"/>' for n in range(len(objects)))
model = ('<?xml version="1.0" encoding="UTF-8"?>'
         '<model unit="millimeter" xml:lang="en-US" '
         'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
         '<resources>' + "".join(parts) + '</resources>'
         f'<build>{items}</build></model>')

with zipfile.ZipFile("data/pegs.3mf", "w", zipfile.ZIP_DEFLATED) as z:
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
print(f"wrote data/pegs.3mf ({os.path.getsize('data/pegs.3mf')/1e3:.0f} KB)")
