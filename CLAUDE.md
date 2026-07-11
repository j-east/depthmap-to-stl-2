# TerrainMaps (terrainmaps.land)

**Before modifying anything in `web/` or `scripts/path_editor.py`, read `SPEC.md`.**
It is the source of truth for every UI element, parameter, and engine invariant.
Features have been silently lost in past refactors — SPEC.md exists to stop that.

Hard rules:
- Never remove or alter a UI element, parameter, or behavior listed in SPEC.md without
  updating SPEC.md in the same commit.
- Every generation parameter must be wired through ALL SIX stops listed in SPEC.md §1
  (UI → msg → worker → golf_board kwarg → recipe → viewer/remix restore) and included
  in `currentParams()` if it affects the bake.
- The worker calls Python with POSITIONAL args — keep call strings in worker.js in sync
  with `golf_board(...)`'s signature.
- Engine invariants in SPEC.md §5 (DEM merge, flat inland water, SS line-width floor,
  streamed 3MF, shader proud-height compensation, …) are load-bearing fixes for real
  bugs. Do not "simplify" them away.
- Run the refactor checklist in SPEC.md §8 before committing.

Dev:
- Local server: `PORT=8765 HOST=127.0.0.1 APP_PASSWORD= python3 scripts/path_editor.py`
  (serves web/ fresh from disk; SQLite locally, Postgres in prod via DATABASE_URL)
- Deploys: push to BOTH remotes (`git push && git push private master`) — Coolify
  watches `private` (j-east/deer-isle-cribbage) and auto-deploys terrainmaps.land.
- Syntax checks: ast.parse for board_lib.py, `node --check` for worker.js and each
  page's extracted inline `<script>`.
