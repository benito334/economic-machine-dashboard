"""D4 manual-load infrastructure — fetch_manual_series + Manual bindings."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import indicators.loader as loader
from indicators.loader import fetch_manual_series
from indicators.pipeline import load_bindings

_CONFIG = Path(__file__).parents[1] / "config"


@pytest.fixture
def manual_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "MANUAL_DATA_DIR", tmp_path)
    return tmp_path


# ── fetch_manual_series ───────────────────────────────────────────────────────

def test_missing_file_is_pending_slot_not_error(manual_dir):
    assert fetch_manual_series("vdem_us.csv") is None


def test_bare_years_parse_to_year_end(manual_dir):
    (manual_dir / "vdem_us.csv").write_text("date,value\n1990,0.796\n1991,0.801\n")
    s = fetch_manual_series("vdem_us.csv")
    assert list(s.index) == [pd.Timestamp("1990-12-31"), pd.Timestamp("1991-12-31")]
    assert s.iloc[-1] == pytest.approx(0.801)


def test_iso_dates_parse(manual_dir):
    (manual_dir / "gpr_us.csv").write_text(
        "date,value\n2024-01-01,1.42\n2024-02-01,1.57\n"
    )
    s = fetch_manual_series("gpr_us.csv", frequency="M")
    assert len(s) == 2
    assert s.index[0] == pd.Timestamp("2024-01-01")


def test_unsorted_rows_and_blank_values_are_cleaned(manual_dir):
    (manual_dir / "x.csv").write_text(
        "date,value\n2001,0.5\n2000,0.4\n2002,\n"
    )
    s = fetch_manual_series("x.csv")
    assert len(s) == 2                       # blank value dropped
    assert s.index.is_monotonic_increasing   # sorted


def test_case_insensitive_headers(manual_dir):
    (manual_dir / "x.csv").write_text("Date,Value\n2020,1.0\n")
    s = fetch_manual_series("x.csv")
    assert len(s) == 1


def test_malformed_columns_fail_loudly(manual_dir):
    (manual_dir / "bad.csv").write_text("year,score\n2020,1.0\n")
    with pytest.raises(ValueError, match="must have 'date' and 'value'"):
        fetch_manual_series("bad.csv")


def test_all_null_values_fail_loudly(manual_dir):
    (manual_dir / "empty.csv").write_text("date,value\n2020,\n2021,\n")
    with pytest.raises(ValueError, match="zero usable rows"):
        fetch_manual_series("empty.csv")


# ── Manual bindings config integrity ──────────────────────────────────────────

def _manual_bindings():
    out = []
    for p in [_CONFIG / "us_bindings.yaml", *sorted((_CONFIG / "countries").glob("*_bindings.yaml"))]:
        out += [(p.name, b) for b in load_bindings(p) if b.provider == "Manual"]
    return out


def test_manual_bindings_exist_and_are_well_formed():
    bindings = _manual_bindings()
    ids = {b.id for _, b in bindings}
    assert "order.governance" in ids
    assert "order.geopolitical_risk" in ids
    for fname, b in bindings:
        assert b.verified, f"{fname}:{b.id} — Manual slots must be verified:true"
        assert b.series_id and b.series_id.endswith(".csv"), f"{fname}:{b.id}"
        assert b.force == "order"
        assert b.lead_lag == "structural"


def test_governance_covers_all_countries_gpr_skips_lu():
    bindings = _manual_bindings()
    gov = {b.country for _, b in bindings if b.id == "order.governance"}
    gpr = {b.country for _, b in bindings if b.id == "order.geopolitical_risk"}
    assert gov == {"US", "CN", "IN", "DE", "GB", "JP", "KR", "LU"}
    # Luxembourg is not in the GPR country set — deliberately no binding.
    assert gpr == {"US", "CN", "IN", "DE", "GB", "JP", "KR"}
