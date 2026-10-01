# DengueWatch LK web dashboard

React + TypeScript (Vite), Tailwind CSS, Radix UI, Apache ECharts, MapLibre GL, TanStack Query.
It reads everything from the FastAPI service (`src/api/main.py`); it has no data of its own.

```powershell
# with Docker (normal way): from the project root
docker compose up -d            # http://localhost:3000

# for development (hot reload), needs Node 22+:
uvicorn src.api.main:app --port 8000      # terminal 1, project root
cd web; npm install; npm run dev          # terminal 2 -> http://localhost:3000
npm run build                             # type check + production build (what CI runs)
```

`/api/*` is forwarded to the API: by Vite in development (`vite.config.ts`), by nginx in Docker (`nginx.conf`).

| Folder | What |
|---|---|
| `src/api.ts` | typed API client + data hooks (one per endpoint) |
| `src/components/` | page sections: `Hero` (map + headline + national curve), `ForecastSection`, `WhereSection`, `DistrictSection`, `ModelSection`; `ui.tsx` shared parts |
| `src/styles.css` | design tokens (colours for light + dark mode, fonts) |
