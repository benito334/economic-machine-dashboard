"""AI capex cycle monitor, Phase 1 (docs/ai_bubble_monitor_plan.md) —
pure-logic and monkeypatched tests, no live network access."""
import io
from datetime import date

import pandas as pd
import pytest

from indicators import ai_capex as ac


# ── _parse_c30_date: the two-digit-year pivot ────────────────────────────────

def test_parse_c30_date_handles_suffixes_and_month_end():
    today = date(2026, 10, 4)
    assert ac._parse_c30_date("Aug-26p", today) == pd.Timestamp("2026-08-31")
    assert ac._parse_c30_date("Jul-26r", today) == pd.Timestamp("2026-07-31")
    assert ac._parse_c30_date("Feb-24", today) == pd.Timestamp("2024-02-29")


def test_parse_c30_date_pivots_twentieth_century_years():
    """The C30 file reaches back to 1993; a naive "20"+yy turns Jan-99 into
    2099. Regression test for a bug caught by actually running the parser."""
    today = date(2026, 10, 4)
    assert ac._parse_c30_date("Jan-99", today) == pd.Timestamp("1999-01-31")
    assert ac._parse_c30_date("Dec-93", today) == pd.Timestamp("1993-12-31")
    # ...while a legitimately near-future year is left alone.
    assert ac._parse_c30_date("Jan-27", today) == pd.Timestamp("2027-01-31")


def test_parse_c30_date_rejects_garbage():
    assert pd.isna(ac._parse_c30_date("Type of Construction"))
    assert pd.isna(ac._parse_c30_date(None))


# ── fetch_census_c30 ─────────────────────────────────────────────────────────

def _fake_c30_xlsx(dc_label="Data center",
                   fab_label="Computer/ electronic/ electrical") -> bytes:
    rows = [
        ["Value of Private Construction", None, None, None],
        ["(Millions of dollars.)", None, None, None],
        [None, None, None, None],
        ["Date", dc_label, fab_label, "Nonresidential"],
        ["Aug-26p", 84950, 52298, 773010],
        ["Jul-26r", 79007, 53000, 764979],
        ["Aug-25", 49052, 95374, 750000],
    ]
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, sheet_name="Private SA", index=False, header=False)
    return buf.getvalue()


def test_fetch_census_c30_parses_both_legs(monkeypatch):
    monkeypatch.setattr("indicators.loader.fetch_url_cached",
                        lambda *a, **k: _fake_c30_xlsx())
    df = ac.fetch_census_c30()
    assert list(df.columns) == ["as_of", "data_center", "chip_fab", "nonresidential"]
    assert len(df) == 3
    # sorted ASCENDING even though the source file descends
    assert df["as_of"].is_monotonic_increasing
    assert df["data_center"].iloc[-1] == 84950
    assert df["chip_fab"].iloc[-1] == 52298


def test_fetch_census_c30_missing_column_fails_loudly(monkeypatch):
    """A renamed/absent column must yield an EMPTY frame, never a silent zero
    column — CLAUDE.md rule 4: an empty result is a failure, not a success."""
    monkeypatch.setattr("indicators.loader.fetch_url_cached",
                        lambda *a, **k: _fake_c30_xlsx(dc_label="Datacentre"))
    assert ac.fetch_census_c30().empty


def test_fetch_census_c30_unreachable_returns_empty(monkeypatch):
    monkeypatch.setattr("indicators.loader.fetch_url_cached", lambda *a, **k: None)
    assert ac.fetch_census_c30().empty


# ── EIA-930: incomplete-month guard ──────────────────────────────────────────

def _fake_930_csv(year: int, month: int, days: int, zones=("DOM", "PEP")) -> bytes:
    rows = []
    for z in zones:
        for d in range(1, days + 1):
            for hour in (3, 15):   # a trough hour and a peak hour
                rows.append({
                    "Balancing Authority": "PJM",
                    "Data Date": f"{month:02d}/{d:02d}/{year}",
                    "Hour Number": hour,
                    "Sub-Region": z,
                    "Demand (MW)": 1000 if hour == 3 else 2000,
                })
    return pd.DataFrame(rows).to_csv(index=False).encode()


def test_fetch_eia930_drops_incomplete_months(monkeypatch):
    """The current month is always partial — these files update daily — and
    comparing four days of October against a full October a year earlier
    fabricates a year-over-year move. Regression test for a real bug."""
    def fake(url, cache_name, ttl, force_refresh=False, **k):
        if "2026_Jul_Dec" in url:
            # September complete (30 days), October only 4 days so far
            return (_fake_930_csv(2026, 9, 30).decode()
                    + "\n".join(_fake_930_csv(2026, 10, 4).decode().splitlines()[1:])
                    ).encode()
        return None
    monkeypatch.setattr("indicators.loader.fetch_url_cached", fake)

    out = ac.fetch_eia930_trough(years_back=0, today=date(2026, 10, 4))
    months = set(out["as_of"].dt.strftime("%Y-%m"))
    assert "2026-09" in months
    assert "2026-10" not in months, "partial month must be dropped"


def test_fetch_eia930_uses_daily_minimum(monkeypatch):
    monkeypatch.setattr(
        "indicators.loader.fetch_url_cached",
        lambda url, *a, **k: _fake_930_csv(2026, 9, 30) if "Jul_Dec" in url else None)
    out = ac.fetch_eia930_trough(years_back=0, today=date(2026, 10, 4))
    # trough is the 1000 MW hour, never the 2000 MW one
    assert out["trough_mw"].unique().tolist() == [1000.0]


# ── trough_excess ────────────────────────────────────────────────────────────

def _trough_frame(dc_vals, ctl_vals, start="2025-01-31") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(dc_vals), freq="ME")
    rows = []
    for zone, vals in (("DOM", dc_vals), ("AEP", dc_vals),
                       ("PEP", ctl_vals), ("BC", ctl_vals)):
        rows.append(pd.DataFrame({"as_of": idx, "zone": zone, "trough_mw": vals}))
    return pd.concat(rows, ignore_index=True)


def test_trough_excess_nets_out_a_common_shock():
    """The whole point of the control: a shock hitting both the data-centre
    zones and their weather-matched neighbours must NOT show up as excess."""
    base = [100.0] * 15
    shocked = [100.0] * 12 + [130.0] * 3   # +30% in both groups
    out = ac.trough_excess(_trough_frame(shocked, shocked, start="2024-01-31"))
    assert not out.empty
    assert abs(out["excess_pp"].iloc[-1]) < 1e-6


def test_trough_excess_detects_datacentre_only_growth():
    dc = [100.0] * 12 + [130.0] * 3        # data-centre zones grow
    ctl = [100.0] * 15                      # control flat
    out = ac.trough_excess(_trough_frame(dc, ctl, start="2024-01-31"))
    assert out["excess_pp"].iloc[-1] > 25.0
    assert out["control_yoy"].iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_trough_excess_requires_both_zone_groups():
    df = _trough_frame([100.0] * 15, [100.0] * 15)
    only_dc = df[df["zone"].isin(["DOM", "AEP"])]
    assert ac.trough_excess(only_dc).empty


def test_trough_excess_handles_empty():
    assert ac.trough_excess(pd.DataFrame(columns=["as_of", "zone", "trough_mw"])).empty


# ── _state ───────────────────────────────────────────────────────────────────

def test_state_higher_is_worse():
    assert ac._state(0.1, 0.3, 0.75) == "OK"
    assert ac._state(0.4, 0.3, 0.75) == "WARNING"
    assert ac._state(0.9, 0.3, 0.75) == "CRITICAL"


def test_state_lower_is_worse():
    assert ac._state(20.0, 5.0, 0.0, lower_is_worse=True) == "OK"
    assert ac._state(3.0, 5.0, 0.0, lower_is_worse=True) == "WARNING"
    assert ac._state(-1.0, 5.0, 0.0, lower_is_worse=True) == "CRITICAL"


def test_state_missing_value():
    assert ac._state(None, 1.0, 2.0) == "—"
    assert ac._state(float("nan"), 1.0, 2.0) == "—"


# ── it_growth_share ──────────────────────────────────────────────────────────

def test_it_growth_share_returns_both_share_and_contribution(monkeypatch):
    """The pp contribution must be returned alongside the share: when GDP
    growth collapses, the denominator shrinks and the share spikes while the
    contribution is actually FALLING. The share alone is misleading."""
    idx = pd.date_range("2024-01-01", periods=8, freq="QS")
    series = {
        ac._FRED["it_equip"]: pd.Series([0.2] * 8, index=idx),
        ac._FRED["it_soft"]: pd.Series([0.3] * 8, index=idx),
        ac._FRED["gdp_growth"]: pd.Series([2.0] * 8, index=idx),
    }
    monkeypatch.setattr(ac, "_series", lambda sid, freq, fr=False: series[sid])
    out = ac.it_growth_share()
    assert {"as_of", "value", "contribution_pp"} <= set(out.columns)
    # (0.2+0.3)*4 = 2.0pp of 8.0pp of 4q GDP growth = 25%
    assert out["value"].iloc[-1] == pytest.approx(25.0)
    assert out["contribution_pp"].iloc[-1] == pytest.approx(2.0)


def test_it_growth_share_missing_source_returns_empty(monkeypatch):
    monkeypatch.setattr(ac, "_series", lambda sid, freq, fr=False: None)
    assert ac.it_growth_share().empty


# ── no Z-scores on the Census series (a design rule, enforced) ───────────────

def test_module_does_not_zscore_census_construction():
    """12.7 years with zero prior downturns cannot support a Z-score; "+2σ"
    would mean "higher than the only regime we have observed". The plan makes
    this an explicit rule, so pin it."""
    src = (ac.__file__).replace(".pyc", ".py")
    text = open(src).read()
    body = text.split("def compute_ai_capex_metrics")[1]
    assert "zscore" not in body.lower()
    assert "_full_history_z" not in body


# ── operator gating (the public Cloud Run deploy runs PUBLIC_MODE=1) ─────────

def test_ai_capex_route_is_operator_only():
    """deploy/cloudrun/Dockerfile sets PUBLIC_MODE=1, and a push to main
    auto-deploys it. The page must therefore be gated two ways: hidden from
    the nav, AND blocked by direct URL in route_page via this frozenset."""
    from dashboard.app_mode import OPERATOR_ONLY_ROUTES
    assert "/ai-capex-cycle" in OPERATOR_ONLY_ROUTES


def test_ai_capex_nav_link_is_inside_the_public_mode_guard():
    """The nav entry must sit in charting.py's `[] if PUBLIC_MODE else [...]`
    block alongside Bubble Gauge — a route that is gated but still listed in
    the sidebar leaks its existence on the public deploy."""
    import pathlib
    src = pathlib.Path("dashboard/charting.py").read_text()
    guard = src.split("*([] if PUBLIC_MODE else [")[1].split("]),")[0]
    assert "/ai-capex-cycle" in guard
