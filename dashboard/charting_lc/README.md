# Option B — TradingView Lightweight Charts (Deferred)

This directory is the skeleton for ADR-007 Option B.

## Architecture

```
dashboard/charting_lc/
├── README.md          ← this file
├── main.py            ← FastAPI app (data API, port :8000)
└── index.html         ← Lightweight Charts v4 frontend (served by nginx, port :8503)
```

## Status

**Deferred.** Option A (Plotly Dash, `dashboard/charting.py`) is active for Phase 1D.
Activate Option B when TradingView UX polish justifies frontend JavaScript work.

## Activation steps

1. `pip install fastapi uvicorn`
2. `docker compose up api frontend` (add services to docker-compose.yml)
3. Wire series endpoints in `main.py` using `charting_data.py` helpers
4. Replace `createChart()` placeholder in `index.html` with real data fetch

## Why this exists

Committing the skeleton now prevents re-researching the integration pattern later.
The Lightweight Charts v4 API is stable; `index.html` documents the import and
`createChart` call signature so the frontend can be wired up without reading docs.
