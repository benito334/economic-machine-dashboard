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
python3 -m indicators.pipeline
```
Will clear 3 stale US signals: current account, NIIP, debt service ratio.

### EA current account — accepted gap
All free API sources exhausted (WB, ECB, FRED, Eurostat, IMF). See `docs/Guidance/EU_singals_guidance.md` for full investigation table. Resolution requires ECB Data License or manual Eurostat bulk download. Accept gap for now — Global Overview shows dash for EZ current account column.

---

## Completed this session (2026-06-23) — session 2
- **Weight Audit blank graphs fixed**: split `update_layout()` calls to avoid duplicate `margin` kwarg; `_hex_alpha()` helper converts 8-digit hex to `rgba()` for Plotly compatibility
- **Re-run button**: `wa-run-store` dcc.Store; clicking ↺ Re-run re-triggers all three audit panels on demand
- **Importance Editor (Weight Audit Section 4)**: inline editable DataTable for all signals; live G/I ratio preview; reason field; saves to YAML + `weight_change_log` DuckDB table
- **GDP-Regression Calibration (Weight Audit Section 5)**: `indicators/calibrate.py`; OLS each growth signal against `{cc}.master.gdp_real`; positive betas scaled to [0.10, 0.95]; β≤0 → no recommendation; "Apply Selected" populates editor
- **weight_change_log table**: DDL + `log_weight_changes()` / `query_weight_change_log()` / `update_weight_change_reason()` in `store/store.py`
- **Weight History page** (`/weight-history`): `dashboard/weight_history.py`; table + editable Reason column + Save Notes; wired into charting.py nav + `_PAGE_MAP`
- **Methodology Section 12 expanded**: importance tier table, GDP regression methodology, importance editor docs, weight history docs; deferred table updated (OLS calibration now live)
- **CLAUDE.md + worklog.md + session-checklist.md updated**

## Completed this session (2026-06-23) — session 1
- **Data Explorer country-awareness**: all 6 callbacks wired to `country-store`; signal table resets on country switch
- **ECB SDW fetcher**: `fetch_ecb_series()` in `loader.py`; Pass 1.6 in `pipeline.py`; `"FLOW/KEY"` series_id format
- **7 new EZ bindings**: employment growth, construction prod, capacity util (Eurostat); BTP-Bund spread via ECB IRS; fiscal budget balance (Eurostat quarterly); HICP energy + food sources corrected to FRED index series (monthly through current)
- **EZ composites**: growth 3→6, inflation 4→6; latest Inflationary Boom 58% conf
- **EZ Global Overview**: `ez.master.gdp_level_bn` (WB `NY.GDP.MKTP.CD`, 16,485B USD 2024) + `ez.credit.gov_debt_gdp` (Eurostat `gov_10dd_edpt1`, 87.8% 2025) now live
- **Regime History + Global Overview signal counts fixed**: dynamic from composites engine
- **Guidance doc updated**: `docs/Guidance/EU_singals_guidance.md` — all signals reviewed; CA investigation table added; HICP energy/food source correction noted
- **EZ: 34 signals live** (was 19); **353 tests pass**; Docker rebuilt

## Up next (next session)
| Priority | Item |
|---|---|
| 1 | Phase 2 — Japan (JP): `config/countries/jp_bindings.yaml` + `jp_composites.yaml` |
| 2 | BEA refresh (after 2026-06-26): `python3 -m indicators.pipeline` clears 3 stale US signals |
| 3 | KR monthly CPI: BoK ECOS API (requires registration) is the only remaining free source; OECD FRED discontinued Apr 2025 |

## Notes for next session
- **119 signals total** (63 US + 34 EZ + 22 KR)
- EZ now 34 signals: 3 FRED growth (stale/historical), 9 Eurostat, 2 ECB IRS, 3 derived, 1 WB GDP, 1 Eurostat debt, 10 WB structural, 5 FRED monetary/currency
- Per-country composites split: `config/composites_policy.yaml` (global) + `config/countries/{cc}_composites.yaml` (per-country)
- Adding Japan: create `jp_bindings.yaml` + `jp_composites.yaml` in `config/countries/`; pipeline auto-discovers
- EZ: `gov_10dd_edpt1` (annual debt) requires NO `s_adj` dim; `gov_10q_ggnfa` (quarterly fiscal balance) uses `s_adj=NSA`
- Eurostat `bop_c6_q` always 413 even with all dims — too large for JSON API; not usable for EA current account
- ECB SDW IRS flow key format: `FREQ.COUNTRY.MATURITY.RATE_TYPE.ISSUANCE.RATING.CURRENCY.IND.COUNTERPARTY`
- :8502 is primary dashboard (Dash); :8501 is Streamlit reference only
