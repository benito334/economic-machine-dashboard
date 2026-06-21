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

## Completed this session (2026-06-21)
- :8502 Dash UI restructuring: left-sidebar nav, browser back button, page routing via `dcc.Location`
- Regime Map scatter: data-driven auto-zoom with 15% buffer; ±100 quadrant backgrounds
- Below-map panels ported from :8501: What Changed, Conflicts, Signal Drill-Downs (all 10 lenses), Data-Quality Log
- Fixed chart height clipping (responsive=True + calc(100vh) CSS heights; removed hardcoded height= from figure layouts)
- Fixed lens accordion: replaced dcc.Markdown HTML rendering with proper html.Table Dash components
- Fixed `update_layout` duplicate `margin=` keyword argument error

## Up next (next session — continue :8502 UI)
| Priority | Item |
|---|---|
| 1 | Continue :8502 UI work — further refinements per user direction |
| 2 | Phase 2 — Eurozone rollout: `config/countries/eu_bindings.yaml`; verify all series IDs; `vintage_available: false` for all |
| 3 | BEA refresh (after 2026-06-26): `python3 -m indicators.pipeline --latest` |

## Notes for next session
- :8501 (Streamlit) and :8502 (Dash) are still both running; user intends :8502 as the sole dashboard going forward
- The `dashboard/app.py` (Streamlit) changes from Phase 1H are committed; :8501 remains functional as a reference
- Methodology Guide expander and data footnotes from :8501 not yet ported to :8502
