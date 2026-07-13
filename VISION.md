# Terrain Boards — Vision

## What it is
Turn a real place into a 3D‑printable, multi‑color relief object. Search a place,
preview it in 3D in the browser, download a print‑ready multicolor 3MF (free), or
order a printed board.

## The core insight
The whole pipeline runs **client‑side in the browser** (Pyodide + numpy/Pillow,
Three.js for preview). Public data is fetched directly from the user's browser —
**USGS 3DEP** (1 m terrain) and **OSM Overpass / Nominatim** (features + search),
all CORS‑open. That means:
- The server does **no compute** and can't be overloaded — it scales per‑visitor.
- The same engine generalizes: anything that's "geographic data → a colored,
  layered, raised relief on a board" is the same machine with different inputs.

## Shipping now
- **Golf relief boards** — terrain + turf (fairway/green/tee/bunker/water) + roads,
  cart paths, rail, per‑hole outlines, and hole numbers. Course search auto‑fits
  the board to the course boundary. Live client‑side at `/play`.
- **Cribbage boards** — hand‑routed 121‑hole track over real topo/bathymetry
  (server‑side for now; Dijkstra routing to be ported to the browser).

## Where this goes — more "place as an object" products
The same fetch → layer → color → emboss → 3MF engine can make many things. Ideas:

- **City / town maps** — streets, water, parks, rail, building footprints as raised
  colored layers (OSM has all of it). "Your town as a board."
- **Skylines** — extrude building footprints by height (OSM `building:height` /
  `building:levels`) into a 3D skyline relief of a downtown / neighborhood.
- **Coastlines & lakes** — bathymetry + shoreline as art pieces (we already do
  topobathy for cribbage).
- **Trail / ski / national‑park maps** — terrain + trails + runs + huts, labeled.
- **Stadiums / campuses / racetracks** — a specific landmark rendered in relief.
- **Watershed / river systems**, **wine regions**, **harbor charts**, etc.

Each is a new "model type" plugged into the existing client‑side core: pick the
data layers, colors, heights, and labels; the engine + board frame + 3MF export
are shared. Town maps and skylines are the most natural next expansions.

## Product / business
Free 3MF download + paid printed boards (Shopify checkout/fulfillment). Domain:
**terrainmaps.land**. Names are user‑set with disclaimers (trademark posture);
imagery uses public‑domain NAIP. See the project notes for the legal posture.

## Sales funnel (drafted 2026-07)

Principle: **the free tier is the marketing.** Unrestricted in-browser generation +
free 3MF download costs us ~nothing (all compute is client-side) and every board
someone prints at home or shares in the gallery is an ad. The exit ramp is quality,
not access:

1. **Create (free, unlimited)** — search/draw → live 3D → download 3MF. No account,
   no watermark, no limits. Publish-to-gallery is the viral loop (every shared board
   links back to "Order this print").
2. **The ramp** — an "Order this board" CTA on /play (after generate), /view, and the
   gallery hero. The pitch is what home printers can't do:
   - **Resin / multi-material prints** — museum-grade detail, true color layers,
     finishes most people have no access to.
   - **Human review** — we check label placement, crop, water/coast artifacts, and
     hand-tune before printing (turn the manual review into a stated feature).
   - **Print-grade resolution** — we re-generate server/offline at finer pitch than
     the browser build, plus post-processing.
   - Framing/mounting options later.
3. **Checkout** — Shopify product per size/material tier; the design id rides along
   as a line-item property so fulfillment pulls the exact recipe. Price anchored to
   materials + review time (e.g. $79/$149/$249 tiers by size/tech).
4. **Follow-through** — order status page; photo of the finished board before ship
   (also great gallery/social content, with permission).

Funnel metrics to wire early: generates → publishes → order-clicks → checkouts.
The "resolution" slider in the free tool intentionally tops out below what the paid
print uses — free hi-fi exists (slow, in-browser), paid is *finer + reviewed + resin*.


## Status (2026-07-13)

The designer is feature-complete for golf + rides: client-side Pyodide engine
(3DEP+NOAA merged DEM, Overpass, tile-basemap editor), live parameter system
(exaggeration, base thickness, all element heights via GPU uniforms; route
ribbon + outline/numbers via targeted remesh), organic crops with auto-placed
plaques, per-course hole separation, accounts gating downloads/publish (Google
sign-in ready behind GOOGLE_CLIENT_ID), rate-limited public API, Postgres
gallery, cinematic homepage. SPEC.md is the behavioral contract. Next fronts:
Shopify ordering (PRD pending), data/ volume persistence, more model types.
