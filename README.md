# Tunnels

Small but really good colony sim. Agents have personalities (Big Five),
rank-bucketed talents (E–S), and survival strategies; the world is a
WorldBox-style top-down sandbox with pixel-art tiles.

- `backend/` — Flask + SQLAlchemy + Alembic + Postgres. Tick engine,
  REST API, pytest harness with real Postgres (no mocks).
- `frontend/` — React + Vite + TypeScript. Canvas2D renderer, Zustand
  view-state, React Query for server state.
- `nginx/` — reverse proxy.
- `docker-compose.yml` — one-command spin-up: `docker compose up`.

## Running

```bash
docker compose up
# frontend → http://localhost:5173
# backend  → http://localhost:8000
```

Tests:

```bash
cd backend  && pytest
cd frontend && npm ci && npx vitest run && npx tsc --noEmit
```

## Credits

Sprites: **Tiny Swords** by [Pixel Frog](https://pixelfrog-assets.itch.io/tiny-swords)
— free pack, commercial use permitted. Used here for terrain tiles,
decorations (bushes, rocks), the meat resource, and the pawn unit.
Atlas mapping lives in `frontend/src/render/spriteAtlas.ts`.
