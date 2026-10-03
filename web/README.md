# DengueWatch LK web dashboard

React + TypeScript (Vite), Tailwind CSS, Radix UI, Apache ECharts, MapLibre GL and TanStack Query.
All data comes from the FastAPI service (`src/api/main.py`).

```powershell
# Docker, from the project root
docker compose up -d                      # http://localhost:3000

# Development with hot reload (Node 22+)
uvicorn src.api.main:app --port 8000      # terminal 1, project root
cd web; npm install; npm run dev          # terminal 2 -> http://localhost:3000
npm run build                             # type check + production build (as in CI)
```

Requests to `/api/*` are proxied to the API by Vite in development (`vite.config.ts`) and by nginx in Docker (`nginx.conf`).

| Path | Contents |
|---|---|
| `src/api.ts` | typed API client and data hooks, one per endpoint |
| `src/components/` | page sections: `Hero` (map, headline, national curve), `ForecastSection`, `WhereSection`, `DistrictSection`, `ModelSection`; shared parts in `ui.tsx` |
| `src/styles.css` | design tokens (light and dark colours, fonts) |
