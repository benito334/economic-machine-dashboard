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
- Global Overview + Data Dashboard + sort/filter/reset (see prior entry)
- **Phase 2 EZ + KR rollout**: 19 EZ signals + 22 KR signals live in DuckDB (104 total)
- `raw_scale` field on CountryBinding for already-YoY% FRED series (KR CPI, retail sales)
- `_WB_COUNTRY_MAP` in loader.py for WB API country code mapping (EZ→EMU, KR→KOR, etc.)
- Multi-country pipeline: `run_country()` helper + country loop over `config/countries/*.yaml`
- `_load_wide` composites bug fix: empty-input tuple unpacking crash fixed
- 349 tests pass; Docker rebuilt; EZ+KR visible in Global Overview table

## Up next (next session)
| Priority | Item |
|---|---|
| 1 | Phase 2 — Japan (JP): create `jp_bindings.yaml` + `jp_composites.yaml` |
| 2 | EZ current_account_gdp: WB EMU + Eurostat BOP both empty; investigate ECB SDW key format or accept gap |
| 3 | BEA refresh (after 2026-06-26): `python3 -m indicators.pipeline` clears 3 stale US signals |
| 4 | KR monthly CPI: OECD FRED discontinued Apr 2025; OECD direct API returns 404; explore BoK ECOS API (requires registration) |

## Notes for next session
- 107 signals total (63 US + 23 KR + 19 EZ + Eurostat feeds)
- **Per-country composites split complete**: `config/composites_policy.yaml` (global) + `config/countries/{cc}_composites.yaml` (per-country)
- `load_composites_config(country="US")` in composites.py — merges policy + country file; errors loudly if no country file
- Pipeline skips composites pass with warning if no `{cc}_composites.yaml` found — safe for Japan before file is created
- Adding Japan = create `jp_bindings.yaml` + `jp_composites.yaml` in `config/countries/`
- EZ uses `country: EZ` code (maps to WB `EMU`); signals stored as `ez.*.*`
- KR CPI/retail series have `raw_scale: 100` — already-YoY% OECD FRED series
- Dash 4.x uses Radix UI for Slider — class names are `dash-slider-*`, not `rc-slider-*`
- :8501 (Streamlit) still running as reference; :8502 is the primary dashboard
