# Course Guide / Yardage Book Generator — Design (v0, 2026-07-19)

Goal: from a published golf design, generate a tour-style **yardage book** like the
2019 PLAYERS book — accurate hole diagrams with real yardages, green details, and
caddie notes — as a printable booklet (HTML → print PDF) and a new paid artifact.

Reference anatomy (from the Rory/PLAYERS book):
- Front matter: cover, course intro blurb, champions/history, tee table (rating/slope)
- Routing pages: front-nine / back-nine overview maps, compass, clubhouse label
- Per hole, a 2-page spread:
  1. **Hole diagram** (top-down, painterly but geometrically accurate): tee boxes,
     fairway, bunkers, water, trees; per-tee yardages to landmarks (`1-348 / 2-313 /
     3-278 / 4-211`), carry distances over hazards, distances to scoring-zone center,
     par + tee-yardage legend, a factoid bullet
  2. **Green page**: green close-up with depth (`Depth = 40`), line of play, landing
     /target zone box with edge distances, hole stats table, 2–3 caddie-note bullets

## Architecture: facts are computed, AI decorates

**Layer 1 — Facts engine (deterministic, client-side, free).** We already have every
input: OSM (hole lines, tee/green/fairway/bunker/water polygons, trees) + merged DEM.
Compute per hole into a `HoleFacts` JSON:
- par (OSM tag), lengths per tee polygon (tee centroid → green center along hole line)
- doglegs: max deviation point of hole line, turn angle, distance to turn
- hazards: each bunker/water body near the corridor → distance from each tee to its
  near/far edge along the line of play (= carry numbers), side (L/R)
- green: depth/width along final-approach direction, front/center/back distances,
  DEM slope over the green polygon (grid of arrows / fall lines), false-front detection
- elevation: tee→green Δ, landing-zone Δ ("plays +8 yd"), profile polyline
- landing zone: 250–300 yd band off the championship tee (the book's target box)
Also `CourseFacts`: routing geometry, total yardage per tee, par sequence.

**Layer 2 — Diagram renderer (deterministic, client-side, free).** Reuse the board
rasterizer's data on a 2D canvas per hole: rotate so line-of-play points up (book
convention), draw layers in book palette, yardage callouts from HoleFacts, arcs at
100/150/200, green page with slope arrows. This alone is a usable plain yardage book
— **the AI layers are optional garnish on top of it.**

**Layer 3 — Intelligence (Kimi K3 via OpenRouter).** Input: HoleFacts JSON + course
name/place. Output (strict JSON): caddie bullets per hole ("favor the left edge —
carry the right bunker at 227 from the whites"), course intro blurb, hole factoids.
Optionally enrich with web lore the model already knows (famous holes, history) —
flagged as `lore` so it renders in a distinct style (facts vs flavor).

**Layer 4 — Art (Gemini 3.1 Flash Image via OpenRouter).** Image-to-image ONLY:
input = our accurate Layer-2 diagram, prompt = restyle into hand-painted yardage-book
aesthetic (watercolor turf stripes, soft tree masses) **preserving all geometry and
text exactly**; plus a text-in-image cover. Never text-to-image for diagrams —
geometry must stay ours. Toggle per page: plain (free) vs painted (uses credits).

## OpenRouter: user-owned AI (BYO credits)

One-click connect via OpenRouter's **PKCE flow** (no server secrets, fits our
client-side model):
1. Generate `code_verifier`, SHA-256 → `code_challenge` (crypto.subtle)
2. Open `https://openrouter.ai/auth?callback_url=<our /guide URL>&code_challenge=...
   &code_challenge_method=S256`
3. Callback returns `?code=` → `POST https://openrouter.ai/api/v1/auth/keys`
   `{code, code_verifier, code_challenge_method:"S256"}` → `{key}`
4. Store key in localStorage (`orKey`); all Kimi/Gemini calls go browser →
   openrouter.ai directly. Our server never sees or spends anything.
Model IDs resolved at runtime from `GET /api/v1/models` (match `kimi-k3` and
`gemini-3.1-flash-image`); pin exact IDs once verified. Show per-generation cost
estimate before running (OpenRouter returns usage).

## Product shape

- `/guide?design=<id>`: booklet viewer — paginated pages at book aspect (~2:3.2),
  print stylesheet for PDF export. Free: plain diagrams + computed yardages. With
  OpenRouter connected: “✦ write caddie notes” (Kimi) and “🎨 paint this book”
  (Gemini) buttons. Guide JSON cached in the recipe (`params.guide`) once generated
  so viewers don't re-pay.
- Entry points: viewer/designer button "📖 Course guide" on golf designs.
- Funnel: printed + bound physical yardage books join the resin boards as a paid
  artifact (premium: painted edition).

## Data honesty rules

- Yardages only from geometry we have; never let a model invent numbers. Kimi
  receives facts and may only reference them.
- OSM gaps: guide marks holes with missing tees/greens as "approximate" and links to
  the OSM editor (same `#osmedit` deep link as the designer) instead of guessing.
  Auto-labelling from satellite stays opt-in for the BOARD only (fairway/rough and
  cartpath/bunker confusion make it unreliable for a book that prints numbers).

## Phases

1. **Facts engine + plain book** (no AI): HoleFacts, hole/green/routing renderers,
   /guide page with print CSS. Fully free, offline, correct.
2. **OpenRouter connect + Kimi notes**: PKCE, notes/intro/factoids JSON, render.
3. **Gemini painted edition** + cover; per-page regenerate.
4. Physical printing funnel (with the Shopify PRD).
