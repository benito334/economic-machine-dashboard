# Session Checklist

## At session start
1. Read `CLAUDE.md`
2. Read last 3 entries of `docs/worklog.md`
3. Check this file for pending items

## At session end
1. Add worklog entry
2. Update this file
3. Update memory if key facts changed

---

## Pending / Blockers

### BEA data refresh — due 2026-06-26
Run after June 26 to pick up BEA Q1 2026 data:
```
python3 -m indicators.pipeline --latest
```
Will clear 3 stale signals: current account, NIIP, debt service ratio.

### Phase 2 — Eurozone rollout
Unblocked but deferred until after TradingView system is shipped. Start with `config/countries/eu_bindings.yaml`. Verify all series IDs before ingesting. Set `vintage_available: false` for all Eurozone series.

---

## Completed this session (2026-06-19)
- H1, H2, G1, C1, E1, F1/L1, L2, L3, L4 from methodology feedback tracker
- Regime History UX: momentum blocks in summary strip, 5-subplot chart, html.Details table rollup
- D1: momentum percentile-rank in normalize.py + DB + models
- B1: calendar-adjusted period constants audit (all 5 frequencies confirmed correct; 14 tests)
- A2/I2: Composite Analysis subtab in Data Explorer (correlation heatmap + PCA scree + loadings)
- 319/319 tests pass

## Up next (next session)
| Priority | ID | Item |
|---|---|---|
| 1 | TradingView | Build Option B: FastAPI :8000 + TradingView Lightweight Charts :8503 (see ADR-007) |
| 2 | Phase 2 | Eurozone rollout (after TradingView shipped) |

### TradingView (Option B, ADR-007) — next session checklist
- [ ] `api/main.py`: FastAPI app; endpoints: `/series/{signal_id}`, `/yield-curve/{date}`, `/composite-history`, `/regime-history`
- [ ] `frontend/index.html`: TradingView Lightweight Charts v4 with multi-pane layout
- [ ] `frontend/` static assets served by nginx
- [ ] `docker-compose.yml`: add `api` (FastAPI :8000) and `frontend` (nginx :8503) services
- [ ] User todo items: GDP/Inflation/rate chart, trading-economics-style table, momentum overlay, step controls
- [ ] Skeleton at `dashboard/charting_lc/main.py` is the starting point
