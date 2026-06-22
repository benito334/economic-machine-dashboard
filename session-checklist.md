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

## Completed this session (2026-06-22)
- Rolling Z-score pipeline: 6 rolling Z columns on signals, 9 rolling composite columns; Passes 5b-5d
- Sidebar sliders for Z-Score and Disequilibrium windows; slider state persists via localStorage
- Scatter map blank bug fixed (invalid f-string in hovertemplate)
- Rolling confidence (quadrant-consistency % over 12m rolling scores) replaces baseline when window active
- Dash 4.x slider CSS: all class names updated from rc-slider-* to dash-slider-* (Radix UI); tooltip hidden, vertical bar thumb, visible track on all palettes
- Country selector in sidebar (Phase 2 hooks); Settings modal with Disequilibrium window radio

## Up next (next session)
| Priority | Item |
|---|---|
| 1 | Phase 2 — Eurozone rollout: `config/countries/eu_bindings.yaml`; verify all series IDs; `vintage_available: false` for all |
| 2 | BEA refresh (after 2026-06-26): `python3 -m indicators.pipeline --latest` clears 3 stale signals |
| 3 | :8502 UI remaining polish per user direction |

## Notes for next session
- Dash 4.x uses Radix UI for Slider — class names are `dash-slider-*`, not `rc-slider-*`
- `_RQ_MAP` is now module-level in `charting.py` (used by both scatter and regime-info callbacks)
- `zscore-window-store` and `diseq-window-store` use `storage_type="local"` — survived across refreshes
- :8501 (Streamlit) still running as reference; :8502 is the primary dashboard
