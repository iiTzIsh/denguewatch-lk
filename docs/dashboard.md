# Dashboard

React + TypeScript single-page app (`web/`), served by nginx on port 3000. It has no data of its own: every
number comes from the FastAPI service, which nginx proxies under `/api/`. Charts use ECharts, the map uses
MapLibre GL with the geoBoundaries district outlines, and controls are Radix UI components (keyboard accessible).
Light and dark themes have their own chart palettes, checked for colour-vision deficiency and contrast.

## Sections

| Section | Shows | API |
|---|---|---|
| Header | week picker, data freshness | `/weeks`, `/health` |
| Overview | district map (cases or cases per 100,000), headline for the selected week, national weekly curve, summary of forecast risk, model skill and drift | `/hotspots`, `/geo/districts`, `/national/trend` |
| The next 4 weeks | per health region: forecast at 2 and 4 weeks against the region's outbreak level, with the watch zone (80-100% of the level) and a risk label | `/forecast` |
| Where the cases are | districts ranked by cases or rate, and the high-risk MOH areas NDCU listed that week | `/hotspots`, `/moh/hotspots` |
| District close-up | weekly cases next to weekly rainfall on the same dates (rain starts 6 weeks earlier) | `/districts/{d}/trend`, `/districts/{d}/rain` |
| Model | national actual vs model vs naive forecast (2 or 4 weeks ahead), error and skill, outbreak weeks caught, latest drift check | `/model/health`, `/model/forecast-vs-actual` |

## Reading it

- **Risk** compares a region's forecast with its usual level for that time of year, not with other regions:
  high is at or above the outbreak level, watch is at or above 80% of it. A large region can be normal while a
  small one is on watch.
- **Map colours** use five classes computed from the selected week, so compare numbers rather than colours
  across weeks.
- **Gaps** in the curves are weeks without a report, not zero cases. A week with no reported neighbour is drawn
  as a dot.
- **MOH areas**: NDCU lists only high-risk areas; an area missing from the list was not high-risk that week.
  Parent areas ("split from") come from an unofficial mapping and are marked unverified.
- **Model section** uses the live champion's forecasts once it has at least 50 scored forecasts, and the as-of
  replay before that.
- **Counts vs rates**: forecasts are in cases per health region because Census 2024 population is published per
  district, not per RDHS region.

## Development

```bash
uvicorn src.api.main:app --port 8000      # terminal 1, project root
cd web && npm install && npm run dev      # terminal 2, http://localhost:3000
npm run build                             # type check and production build (run in CI)
```
