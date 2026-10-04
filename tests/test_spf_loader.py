"""Philadelphia Fed SPF loader (docs/external_validators_plan.md item 2,
2026-10-03) — pure-logic tests, no live network access."""
import pandas as pd
import pytest

from indicators import spf_loader as spf


def test_survey_date_is_quarter_end():
    assert spf._survey_date(2026, 3) == pd.Timestamp("2026-09-30")
    assert spf._survey_date(2026, 1) == pd.Timestamp("2026-03-31")
    assert spf._survey_date(2025, 4) == pd.Timestamp("2025-12-31")


# ── _realized_cpi_qoq_annualized: incomplete-quarter guard ────────────────────

def test_incomplete_quarter_excluded_from_realized_cpi(monkeypatch):
    # Sep missing (a real gap CPIAUCSL actually has around 2025-10) — Q3
    # only has Jul+Aug, must NOT be treated as a full quarterly average.
    idx = pd.date_range("2026-01-01", periods=9, freq="MS")
    vals = [300, 301, 302, 303, 304, 305, 306, 307, None]  # Sep missing
    s = pd.Series(vals, index=idx, dtype=float).dropna()

    monkeypatch.setattr(
        "indicators.loader.fetch_series",
        lambda series_id, freq, force_refresh=False: s,
    )
    out = spf._realized_cpi_qoq_annualized()
    assert pd.isna(out.loc["2026-09-30"])
    # Q2 (Apr-Jun, complete, with a complete Q1 base to compare against)
    # should compute a real rate rather than being swept up in the gap.
    assert pd.notna(out.loc["2026-06-30"])


def test_complete_quarters_compute_a_real_rate(monkeypatch):
    idx = pd.date_range("2025-01-01", periods=6, freq="MS")
    # flat 100 for Q1, flat 102 for Q2 -> +2% QoQ non-annualized -> annualized > 0
    vals = [100, 100, 100, 102, 102, 102]
    s = pd.Series(vals, index=idx, dtype=float)
    monkeypatch.setattr(
        "indicators.loader.fetch_series",
        lambda series_id, freq, force_refresh=False: s,
    )
    out = spf._realized_cpi_qoq_annualized()
    assert out.loc["2025-06-30"] == pytest.approx(((1.02) ** 4 - 1) * 100.0, abs=1e-6)


def test_realized_cpi_empty_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(
        "indicators.loader.fetch_series",
        lambda series_id, freq, force_refresh=False: None,
    )
    assert spf._realized_cpi_qoq_annualized().empty


# ── compute_spf_surprise ───────────────────────────────────────────────────────

def _fake_panel(growth_rows=None, cpi_rows=None):
    growth_df = pd.DataFrame(growth_rows or {}).T
    cpi_df = pd.DataFrame(cpi_rows or {}).T
    return {"rgdp_growth": growth_df, "cpi": cpi_df}


def test_surprise_matches_prior_survey_h3_to_realized_target_quarter(monkeypatch):
    # Q1 2026 survey's h3 ("one quarter ahead") targets Q2 2026.
    growth_rows = {
        pd.Timestamp("2026-03-31"): {"h2": 2.5, "h3": 2.0, "h4": 2.1, "h5": 2.2, "h6": 2.1},
        pd.Timestamp("2026-06-30"): {"h2": 2.3, "h3": 2.2, "h4": 2.0, "h5": 2.1, "h6": 2.0},
    }
    monkeypatch.setattr(spf, "fetch_spf_panel",
                        lambda force_refresh=False: _fake_panel(growth_rows=growth_rows))
    monkeypatch.setattr(spf, "_realized_growth",
                        lambda force_refresh=False: pd.Series(
                            {pd.Timestamp("2026-06-30"): 2.4}))
    monkeypatch.setattr(spf, "_realized_cpi_qoq_annualized",
                        lambda force_refresh=False: pd.Series(dtype=float))

    out = spf.compute_spf_surprise()
    g = out["variables"]["rgdp_growth"]
    assert g["nowcast"] == pytest.approx(2.3)       # latest survey's own h2
    assert g["next_q"] == pytest.approx(2.2)         # latest survey's own h3
    assert g["surprise"] == pytest.approx(2.4 - 2.0)  # realized(Q2) - h3 from Q1 survey
    assert g["surprise_target_quarter"] == "2026-06-30"
    assert g["surprise_forecast_date"] == "2026-03-31"


def test_surprise_is_none_when_target_quarter_not_yet_realized(monkeypatch):
    growth_rows = {
        pd.Timestamp("2026-06-30"): {"h2": 2.3, "h3": 2.2, "h4": 2.0, "h5": 2.1, "h6": 2.0},
    }
    monkeypatch.setattr(spf, "fetch_spf_panel",
                        lambda force_refresh=False: _fake_panel(growth_rows=growth_rows))
    monkeypatch.setattr(spf, "_realized_growth", lambda force_refresh=False: pd.Series(dtype=float))
    monkeypatch.setattr(spf, "_realized_cpi_qoq_annualized", lambda force_refresh=False: pd.Series(dtype=float))

    out = spf.compute_spf_surprise()
    g = out["variables"]["rgdp_growth"]
    assert g["surprise"] is None
    assert g["nowcast"] == pytest.approx(2.3)


def test_empty_panel_returns_none_fields_not_a_crash(monkeypatch):
    monkeypatch.setattr(spf, "fetch_spf_panel", lambda force_refresh=False: _fake_panel())
    monkeypatch.setattr(spf, "_realized_growth", lambda force_refresh=False: pd.Series(dtype=float))
    monkeypatch.setattr(spf, "_realized_cpi_qoq_annualized", lambda force_refresh=False: pd.Series(dtype=float))

    out = spf.compute_spf_surprise()
    assert out["as_of"] is None
    for v in out["variables"].values():
        assert v["nowcast"] is None and v["surprise"] is None
