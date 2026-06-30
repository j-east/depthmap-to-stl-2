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
