# DengueWatch LK web dashboard

React + TypeScript (Vite), Tailwind CSS, Radix UI, Apache ECharts, MapLibre GL and TanStack Query.
All data comes from the FastAPI service (`src/api/main.py`), or, in the hosted build, from static JSON
exports of the same endpoints.

```powershell
# Docker, from the project root
docker compose up -d                      # http://localhost:3000

# Development with hot reload (Node 22+)
uvicorn src.api.main:app --port 8000      # terminal 1, project root
cd web; npm install; npm run dev          # terminal 2 -> http://localhost:3000
npm run build                             # type check + production build (as in CI)
npm run build:static                      # hosted build: reads public/data/ instead of the API
```

Requests to `/api/*` are proxied to the API by Vite in development (`vite.config.ts`) and by nginx in Docker (`nginx.conf`).

| Path | Contents |
|---|---|
| `src/api.ts` | typed API client and data hooks, one per endpoint |
| `src/components/` | page sections: `Hero` (map, headline, national curve), `ForecastSection`, `WhereSection`, `DistrictSection`, `ModelSection`; shared parts in `ui.tsx` |
| `src/styles.css` | design tokens (light and dark colours, fonts) |

## Hosted build (Vercel)

The hosted dashboard is a static site: `npm run build:static` (mode `static`, `.env.static`) makes `src/api.ts`
read `public/data/*.json` instead of calling `/api`. Those files are written by `python -m src.export_static`
from the project root and are committed. The root `vercel.json` builds this folder in that mode and sets the
cache headers.
