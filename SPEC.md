# TerrainMaps — Designer & Platform Spec (SOURCE OF TRUTH)

This file is the contract. **Every element, behavior, and parameter listed here must
survive refactors.** If something is intentionally removed or changed, this file must be
updated in the same commit — a diff that changes behavior without touching SPEC.md is a
regression by definition.

Last major revision: 2026-07-13.

---

## 1. The parameter pipeline (where regressions happen)

Every generation parameter must be wired through **all six stops**. Params get "lost"
when a refactor misses one:

```
UI control  →  generate msg  →  worker.js  →  golf_board() kwarg  →  recipe params
(golf.html)    (msg.xyz)         (pass-through)  (board_lib.py)        (publish prms.xyz)
                                                                            │
             remix restore  ←──────────  viewer regeneration  ←────────────┘
             (?design= load)             (viewer.html download msg)
```

**Checklist for any new parameter:**
1. UI control in golf.html (+ display span, default value)
2. `msg.<key>` in `regenerate()`
3. worker.js: read from `m.<key>`, pass into the Python call string (mind positional order!)
4. `golf_board(...)` kwarg in board_lib.py (and `route_layer` if it affects the ribbon)
5. `prms.<key>` in `publish()`
6. Restore on `?design=` load in golf.html AND pass-through in viewer.html `download()`
7. If it can change after a build: include it in `currentParams()` (dirty tracking)
8. Add a row to the parameter table below.

## 2. Parameter table (canonical)

| Param | UI control | msg key | golf_board kwarg | recipe key | live (no rebake)? | default |
|---|---|---|---|---|---|---|
| vertical exaggeration | slider `#ex` (1–8, .5) | `exag` | `exag` | `exag` | yes — GPU uniform `uK` | 4.0 |
| resolution / pitch | slider `#res` (draft .7 / std .5 / high .35 / ultra .25) | `pitch` | `pitch` | `pitch` | no | high (0.35) |
| hidden features | checkboxes `#featchecks` | `hide[]` | `hide_json` | `hide` | visibility yes; 3MF no | all on |
| route thickness | slider `#rw` (1.2–5 mm) | `routeW` | `route_w` | `routeW` | yes — ribbon-only remesh | 2.4 |
| route height | slider `#rh` (0.4–3 mm) | `routeH` | `route_h` | `routeH` | yes — uniform `ROUTE_H_UNI` | 1.0 |
| board title | input `#btitle` | `title` | `title` | `title` | no | course/ride name |
| subtitle | auto (ride km / golf locality) | `subtitle` | `subtitle` | `subtitle` | no | auto |
| plaque corner | picker `#ppos` (↙↘↖↗) | `plaquePos` | `plaque_pos` | `plaquePos` | no | `bl` |
| hole labels (edited) | edit-step drag/✕ + course checkboxes | `holes[]` | `holes_json` | `holes` | no | OSM ∩ course bbox |
| route polyline | GPX / drawn waypoints | `route[]` | `route_json` | `route` | n/a | — |
| ride kind | chips (bike/moto/drive) | `kind` | `route_kind` | `kind` + design `type` | no | bike |
| waypoints (drawn) | map clicks | — | — | `wpts` | n/a | — |
| crop bbox | crop box in edit step | `bbox` | `bbox` | design `bbox` | no | golf 1.5× guess / ride 1.25× track |

### 2a. Advanced section (IMPLEMENTED 2026-07-12)

All of the following live in a collapsed **"advanced"** `<details>` section of the
layerbox. All are recipe params and follow the §1 checklist. All bake on
regenerate/download/publish (none are live unless stated).

| Param | Control | msg / kwarg / recipe key | Range | Default | Notes |
|---|---|---|---|---|---|
| element heights | per-group sliders | `heights` / `heights_json` / `heights` | 0.1–2.5 mm (turf: 0.25–2.5×) | road .4 · trail .5 · rail .7 · water .15 · turf 1.0× | LIVE via per-layer GPU uniforms (uH); turf is a MULTIPLIER on the four turf defaults (fairway .5/tee .6/green .8/bunker .6) |
| outline blobbiness | slider | `outlineBlob` / `outline_blob` / `outlineBlob` | 0–1 | 0.45 | gaussian radius = corridor_width × (0.08 + 0.32×blob); LIVE via marks remesh |
| corridor width | slider | `corridorW` / `corridor_w` / `corridorW` | 30–120 m | 60 | corridor stroke width; LIVE via marks remesh |
| hole number size | slider | `numSize` / `num_size` / `numSize` | 5–16 mm | 9 | LIVE via marks remesh |
| hole number height | slider | `numH` / `num_h` / `numH` | 0.4–2.5 mm | 1.1 | LIVE via uniform (except when flattened) |
| number flatten | toggle | `numFlat` / `num_flat` / `numFlat` | on/off | off | digits sit on per-label flattened discs (`numplate` mesh, local-max level +0.5) |
| outline height | slider | `outlineH` / `outline_h` / `outlineH` | 0.3–2 mm | 0.9 | LIVE via uniform |
| plaque size | slider | `plaqueSize` / `plaque_size` / `plaqueSize` | 0.6–1.8× | 1.0 | scales plaque font sizes + padding together |
| crop shape | toggle rect/organic | `cropShape` + `organicPad` / `crop_shape`,`organic_pad_mm` / same | rect·organic; pad 2–20 mm | rect | see §6 |
| outline style | toggle joined/per-hole | `outlineMode` / `outline_mode` / `outlineMode` | union·holes | union | 'holes' rings each hole separately (no turf wrap) — crossings read as OB lines; LIVE via marks remesh |

### 2b. Feature-group split (IMPLEMENTED)

`marks` (outline + numbers together) splits into **two independent groups**:
- `outline` — hole corridor rings (objs: `outline`)
- `numbers` — hole digits (objs: `numbers`, `numplate`)

Both toggleable independently, both in `hide`, both instant-visibility + baked exclusion.
Recipes with legacy `hide:["marks"]` must be interpreted as hiding both.

## 3. UI inventory — `/designer` (web/golf.html)

Anything here that disappears without a SPEC.md edit is a bug.

**Sidebar, top to bottom:**
- `#h1` title (mode emoji + name), `← gallery` link
- Mode tabs: `⛳ Golf course` / `🚵 Ride loop` — switching carries the search text across
  and auto-searches in the target mode
- Golf panel: search input (Enter + 1 s debounced autosearch, ≥3 chars, dedup),
  results list, `advanced: bbox` disclosure with manual W,S,E,N entry
- Ride panel: kind chips (🚴 bike / 🏍 moto / 🚗 drive — re-routes drawn routes on switch),
  waypoint search (same debounce), draw tools (↩ Undo, ✕ Clear,
  `⟲ Close the loop` button when route is open), "— or —" divider, GPX upload
  (`trkpt`/`rtept`, Douglas-Peucker simplify capped ~800 pts), `#gpxinfo` line
- Edit panel: course checkboxes `#coursebox` (multi-course separation, §5.4),
  `✓ Generate board` / `↻ Regenerate board` (spinner + "Generating…" while running),
  `✕ Cancel — keep the current board` (re-edit only; restores snapshot), mode tips
- Layerbox (visible once editing, stays after done): board title input, plaque corner
  picker, feature checkboxes (turf / outline / numbers [golf-only rows hidden in ride
  mode] / roads / trails & paths / railways / water / title plaque), ride-only ribbon
  thickness + route height sliders, vertical exaggeration slider, resolution slider
  (+ ultra warning), bake hint, advanced `<details>` with the §2a params
- Done panel: `↻ Regenerate board` (only when dirty), `✎ Edit crop / labels`,
  `⬇ download 3MF` (account-gated, auto-bakes when dirty, place-named file),
  `↑ Publish to gallery` (account-gated, auto-bakes, stores full recipe)
- Bake hint + auto-rotate toggle (default ON) sit directly below the Generate button
  (between the done panel and the layerbox); status line, progress bar (worker
  milestones + creep), monospace log
- Generate/Regenerate buttons narrate the phase while running: "Loading map data…"
  during the OSM/DEM fetch (<30%), then "Generating…"

**Map editor (plan canvas):**
- OSM raster tile basemap, Web-Mercator projection, "© OpenStreetMap" attribution
- Golf overlays on top of tiles: turf polys, water, roads/rail/cartpaths (print preview)
- Gestures: body drag = pan; two-finger scroll = pan; pinch (ctrl+wheel) = **gentle**
  zoom (exp(deltaY×0.004)) anchored at cursor; crop moves via its 8 edge/corner handles
  only; zoom buttons (+/−/⌖ fit) top-right, pinned left of the split divider
- Crop box: cyan, dim outside, never auto-resizes after user contact (no auto-fit)
- Golf: hole-number markers drag to move, ✕ to delete; refetch on pan/zoom never
  clobbers user label edits
- Ride: waypoint letters (A green start), ✕ delete, drag to move (reroute on release);
  route ribbon drag = Google-style via-insert with dashed elastic ghost; click map to
  append waypoint; click A (or button) closes the loop; OSRM bike/car profiles with
  fallback mirror

**3D view:**
- Left-drag orbit, two-finger scroll pan, pinch zoom (same math as map), right-drag pan
- Split-screen re-edit: plan left / live rotating render right; window resize safe
- Live uniforms: exaggeration (terrain scales, decal proud heights constant), route
  height; route thickness = debounced ribbon-only remesh (`route_layer`)
- Feature checkbox toggles = instant mesh visibility

## 4. UI inventory — other pages

- **`/` (gallery.html):** header (brand, search, + Create), tagline hero, cinematic hero
  (3 eased camera shots cycling top-3 meshed boards, crossfade + preload, "n / 3" tag;
  CTA row: ✎ Remix · ⬇ Download 3MF · 🖨 Order prints · Open board), browse tabs
  (Trending/Top/New), type chips (All/Golf/Bike/Moto/Drive), cards (thumb zoom, badge,
  vote pill, place shortened), skeletons, search-or-create card, footer. Contour-line
  page texture. No user camera takeover on the hero (buttons only).
- **`/view` (viewer.html):** instant precomputed-mesh render, vote, ✎ Remix,
  ⬇ Download 3MF (account gate; `?dl=1` auto-triggers; lazily boots Pyodide and rebuilds
  at recipe settings), Order print → `/order?design=`, pan/pinch/orbit.
- **`/order` (order.html):** stub — resin/human-review/hi-fi pitch, shows the linked
  design, notify-me email capture into accounts. Real commerce awaits a PRD.
- **Account modal (viewer + designer):** Sign in with Google (when `GOOGLE_CLIENT_ID`
  set — GIS button, server verifies token audience + email_verified) or name+email
  form; stored in `accounts` table, dedup by email; localStorage `tmAccount`; gates
  download AND publish; publish handle prefills from account.

## 5. Engine invariants (web/board_lib.py, web/worker.js)

Hard-won behaviors. **Do not undo these.**

1. **Elevation = 3DEP + NOAA merge.** USGS 3DEP for land (the NOAA mosaic has
   resolution seams inland — verified at Merion), NOAA topobathy where below sea level,
   NOAA fills where 3DEP has no coverage (non-US). Either service may fail; one is enough.
2. **Water split:** ocean (DEM < SEA_LEVEL) follows real bathymetry at the SAME
   mm-per-metre scale as land (no separate amplification), floored at the base recess.
   Inland water bodies are FLAT, each at its own level (numpy min-propagation flood).
3. **Supersampled rasterization (SS=3)** with majority downsample for ALL masks; line
   widths floored at `SS+1` px — thinner lines are erased by the downsample (this is
   how roads vanished from large ride boards).
4. **Hole outlines:** corridor stroke + round end caps + turf union (never slices
   tees/greens), gaussian blur + threshold rounding, dilated outward so the ring clears
   turf edges, `& lbl==0`.
5. **3MF is streamed** into the zip in 250k-row chunks — never build the whole XML
   string (WASM OOM at ultra).
6. **Live exaggeration shader:** `z' = uBase + (z−uBase−uC)·uK + uH` for z>0; uC = baked
   proud height per mesh (PROUD table), so decals keep true printed height while terrain
   scales. Route mesh uses `ROUTE_H_UNI` as uH.
7. **Overpass:** 5 mirrors × 3 backoff rounds. **Nominatim:** 1 req/s (debounce ≥1 s).
8. **Course separation:** holes assigned to `leisure=golf_course` polygons
   (point-in-polygon, ways + relation members), sub-grouped by hole-name prefix
   ("Stadium 1"); default-checked groups = holes inside the searched bbox; fall back to
   keep-all when the filter empties. Published recipes store the curated `holes`.
9. **route_layer** must rasterize the ribbon identically to golf_board (same SS, caps,
   width floor) — it hot-swaps the mesh live.
10. Worker boot failures post an error (never silent); `worker.onerror` surfaces crashes.
11. Retina: any Three.js canvas needs explicit CSS `width/height` (setSize's style gets
    wiped by cssText assignment).
12. Preview/gallery mesh is packed at 0.5 mm pitch regardless of the print pitch.
13. **Regenerate never refetches**: the worker caches the merged DEM (pyodide global)
    and the raw OSM features per bbox — same crop = pure remesh, no network. The cached
    feature JSON is snapshotted BEFORE hide-deletion so toggles can't corrupt the cache.
14. **Live-height uniforms**: every layer's shader gets uC (baked proud) + uH (live
    slider) — heights, outline height, and number height move in realtime; the 3MF
    catches up via the dirty auto-bake.
15. **Live marks remesh** (`marks_layer`): blobbiness, corridor width, outline style,
    number size, and flatten rebuild ONLY the outline/numbers/numplate meshes from
    cached data (debounced 350 ms) and hot-swap them. golf_board and marks_layer share
    `_outline_mask` / `_number_objs` — never fork their logic. Organic-crop clipping of
    these layers happens only at the real bake (live swap may slightly overhang).
16. Advanced UI is grouped: "heights · live" / "outline & numbers" (golf) / "board".

## 6. Organic crops (IMPLEMENTED 2026-07-12)

**Goal:** the board doesn't have to be rectangular. `crop_shape: "organic"` derives the
base plate outline from the content:

- **Golf:** union of hole corridors + turf polygons (the same mask as the outline
  algorithm, pre-ring), dilated by `organic_pad_mm` (default ~8 mm on-board), gaussian
  smoothed (reuse the blobbiness machinery), holes filled (no donuts).
- **Ride:** the route ribbon dilated by `organic_pad_mm`, smoothed. Out-and-backs give a
  thick organic band; loops give a ring with the interior filled.
- **Plaque (organic mode) AUTO-PLACES:** it slides inward from the user's preferred
  corner along the line toward the shape until ≥60% of it sits INSIDE the organic
  boundary, then a small (~2 mm) pad is unioned under it. The corner picker becomes a
  side preference in organic mode; exact corners apply only to rect crops. The plate is
  always one connected piece.
- **Outline hierarchy:** the hole-outline ring yields to turf polygons but OVERWRITES
  line layers (roads/rail/cartpaths) — `(lbl == 0) | (lbl > N_POLY)`.
- Implementation: a `base_mask` (bool, cell grid) replaces the implicit full-rect mask.
  `_mesh(base_mask, Zt, 0, …)` produces the plate + perimeter walls for free. Every
  other layer mask is `&`-ed with `base_mask`. Water/ocean clipped the same way.
  The plaque anchors to the mask's bounding corner with the same inset logic.
- `bbox` stays rectangular in the recipe (it's the fetch window); the mask is derived,
  not stored.
- UI: rect/organic toggle + pad slider in the advanced section; the edit-step canvas
  previews the footprint as a translucent white overlay (strokes/fills at padded widths).
- 3MF: nothing special — the mesher already handles arbitrary masks.

**Non-goals (v1):** custom drawn crop shapes; multiple disjoint islands are ALLOWED if
the content is disjoint (mesher handles it; print slicers are fine with it).

## 7. Server (scripts/path_editor.py)

- Public routes: `/`, `/designer` (301 from `/play`, `/golf`), `/view`, `/order`,
  `/board_lib.py`, `/worker.js`, `/font.ttf`, `/featured-demo.mesh`, `/proto`,
  `/health`, `/api/config`
- Public API: designs list/get/create/vote, thumb/mesh GET, mesh upload, `/api/signup`
- Auth-gated: `/studio` and all legacy editor endpoints (APP_PASSWORD)
- Rate limits (per IP, per hour, in-memory): signup 12 · publish 20 · vote 120 ·
  mesh upload 30 → HTTP 429
- DB: Postgres when `DATABASE_URL` set (self-provisions the named database), SQLite
  fallback for dev. Tables: designs, votes, accounts.
- `GOOGLE_CLIENT_ID` env → `/api/config` → GIS button; server verifies ID tokens via
  Google tokeninfo (audience + email_verified).
- Thumbs/meshes live on the container filesystem (`data/`) — **known gap:** needs a
  Coolify volume for persistence across deploys.

## 8. Refactor checklist (run before any commit touching web/ or the server)

- [ ] SPEC.md updated if any behavior/param changed
- [ ] `python3 -c "import ast; ast.parse(open('web/board_lib.py').read())"`
- [ ] `node --check web/worker.js` + extract & `node --check` each page's inline script
- [ ] New/changed params wired through all six stops (§1) + `currentParams()`
- [ ] Grep for the param's msg key across golf.html, worker.js, viewer.html
- [ ] Positional args in the worker's Python call strings match golf_board's signature
- [ ] Smoke-test board_lib with a synthetic DEM if the mesh path changed

**Implementation note:** advanced params are passed to Python as **keyword args** in the
worker's call string (the positional list is frozen at `plaque_pos`). The plaque plate is
unioned into an organic base so it always has material under it.
