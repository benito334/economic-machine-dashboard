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
Unblocked. Start with `config/countries/eu_bindings.yaml`. Verify all series IDs before ingesting. Set `vintage_available: false` for all Eurozone series.

---

## Completed this session (2026-06-19)
- H1, H2, G1, C1, E1, F1/L1, L2, L3, L4 from methodology feedback tracker
- 280/280 tests pass

## Up next
| Priority | ID | Item |
|---|---|---|
| 1 | A2/I2 | Correlation matrix + PCA analysis on composite signals |
| 2 | D1 | Percentile-rank momentum value in normalize.py |
| 3 | B1 | Audit calendar-adjusted N in apply_transformation() |
| 4 | Phase 2 | Eurozone rollout |
