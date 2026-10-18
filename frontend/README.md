# MeterZero frontend

React 19 + TypeScript + Vite, Tailwind v4, react-three-fiber (Three.js) and Recharts.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to the backend on :8000
npm run build    # dist/, served by the backend (or copied into the container as static/)
```

* `src/pages/` one file per page
* `src/twin/` the 3D scenes: the plant twin (`PlantScene`, `TwinCanvas`) and the energy flow (`FlowScene`)
* `src/components/` layout, sidebar, the floating assistant (`AssistantDock`), shared UI
* `src/lib/` API client, formatting, shared hooks
