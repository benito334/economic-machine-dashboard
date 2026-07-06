# Archive — retired pre-Ray surfaces

Removed from the live stack in the 2026-07-06 UI cleanup (approved after the
Ray-era unification audit). Kept for reference; none of this is imported,
tested, or shipped in docker-compose.

| File / dir | What it was | Superseded by |
|---|---|---|
| `streamlit_app.py` | Phase 1C Streamlit proof (:8501) — 4-quadrant HUD, legacy confidence | The Dash dashboard on :8502 (Command Center + Regime Map/History) |
| `charting_lc/` | Phase 1H TradingView Lightweight Charts SPA (:8503 nginx + :8004 FastAPI) — 4-tab charts + 4-season regime step controls | Chart Overlay (`/charts`) + the two-chip regime pages |
| `regime_classifier_page.py` + `regime_classifier.py` | Experimental standalone threshold classifier (`/regime-classifier`) with its own 4-season/"Transitional" labels | The production dual-condition classifier (`_classify_regime`) + Ray's dynamic thresholds, configurable in the Regime Thresholds modal and validated by the G1–G3 backtests |
| `test_streamlit_dashboard.py` | 41 tests for the Streamlit app | Retired with it |

`config/composites.yaml` (deprecated since 2026-06-22, read by nothing) was
deleted outright — recover from git history if ever needed.
