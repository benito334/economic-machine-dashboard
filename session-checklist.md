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
- Global Overview table (`/overview`): TE-style cross-country macro table, 9 columns, color-coded
- 4 new series: `master.gdp_level_bn`, `policy.fed_funds_target`, `fiscal.budget_balance_gdp`, `demo.population_total_mn` (63 signals total)
- Data Dashboard (`/data-dashboard`): 63 signals, grouped by force, sticky header, status badges
- Sort + filter: sortable columns, filter bar (search / force / status / freq), flat vs grouped view
- Status column sortable (0=stale…5=OK) + ↺ Reset Sort button
- 349 tests pass; Docker rebuilt

## Up next (next session)
| Priority | Item |
|---|---|
| 1 | Phase 2 — Eurozone rollout: `config/countries/eu_bindings.yaml`; verify all series IDs; `vintage_available: false` for all |
| 2 | BEA refresh (after 2026-06-26): `python3 -m indicators.pipeline --latest` clears 3 stale signals |

## Notes for next session
- 63 signals total (was 59); tests updated accordingly
- `/overview` nav link is live; `/data-dashboard` is under Data nav group
- Dash 4.x uses Radix UI for Slider — class names are `dash-slider-*`, not `rc-slider-*`
- `_RQ_MAP` is module-level in `charting.py`; stores use `storage_type="local"`
- :8501 (Streamlit) still running as reference; :8502 is the primary dashboard
