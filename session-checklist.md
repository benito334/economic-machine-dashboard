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

---

## Completed this session (2026-06-20)
- TradingView Lightweight Charts system (ADR-007 Option B) — full build
  - FastAPI backend :8004, nginx frontend :8503
  - 4-tab SPA: Charts, Macro Table, Regime (with step controls), Yield Curve
  - 319/319 tests pass; both Docker services healthy

## Up next
| Priority | Item |
|---|---|
| 1 | Phase 2 — Eurozone rollout: `config/countries/eu_bindings.yaml`; verify all series IDs; `vintage_available: false` for all |
| 2 | BEA refresh (after 2026-06-26): `python3 -m indicators.pipeline --latest` |
