"""Late-stage-bubble gauge (coverage-audit Phase C build-out, 2026-10-04) —
pure-logic and monkeypatched tests, no live network access."""
import io
import json

import pandas as pd
import pytest

from indicators import bubble_gauge as bg


# ── _full_history_z / _z_label ─────────────────────────────────────────────────

def test_full_history_z_is_centered_on_zero():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    z = bg._full_history_z(s)
    assert z.mean() == pytest.approx(0.0, abs=1e-9)
    assert z.iloc[-1] > 0  # the max value is above its own mean


def test_full_history_z_handles_zero_variance():
    s = pd.Series([5.0, 5.0, 5.0])
    z = bg._full_history_z(s)
    assert z.isna().all()


def test_z_label_is_magnitude_only_direction_agnostic():
    assert bg._z_label(2.0) == "Extreme"
    assert bg._z_label(-2.0) == "Extreme"  # crowded short is as noteworthy as crowded long
    assert bg._z_label(1.0) == "Elevated"
    assert bg._z_label(-1.0) == "Elevated"
    assert bg._z_label(0.1) == "Normal"
    assert bg._z_label(None) == "—"
    assert bg._z_label(float("nan")) == "—"


# ── fetch_margin_debt ────────────────────────────────────────────────────────

def _fake_margin_xlsx() -> bytes:
    df = pd.DataFrame({
        "Year-Month": ["2026-08", "2026-07", "2026-06"],
        bg._FINRA_DEBIT_COL: [1453832, 1417225, 1502072],
        "Free Credit Balances in Customers' Cash Accounts": [207641, 205132, 217441],
        "Free Credit Balances in Customers' Securities Margin Accounts": [217499, 217305, 223412],
    })
    buf = io.BytesIO()
    df.to_excel(buf, sheet_name="Customer Margin Balances", index=False)
    return buf.getvalue()


def test_fetch_margin_debt_parses_and_sorts_ascending(monkeypatch):
    monkeypatch.setattr(bg, "_download_bytes", lambda *a, **k: _fake_margin_xlsx())
    df = bg.fetch_margin_debt()
    assert list(df["as_of"]) == sorted(df["as_of"])
    assert df["value"].iloc[-1] == 1453832
    assert df["as_of"].iloc[-1] == pd.Timestamp("2026-08-31")


def test_fetch_margin_debt_empty_on_download_failure(monkeypatch):
    monkeypatch.setattr(bg, "_download_bytes", lambda *a, **k: None)
    df = bg.fetch_margin_debt()
    assert df.empty


# ── fetch_leveraged_fund_positioning ────────────────────────────────────────────

def _fake_cftc_json() -> bytes:
    rows = [
        {"report_date_as_yyyy_mm_dd": "2026-09-22T00:00:00.000",
         "open_interest_all": "1890653",
         "lev_money_positions_long": "120133", "lev_money_positions_short": "495707"},
        {"report_date_as_yyyy_mm_dd": "2026-09-29T00:00:00.000",
         "open_interest_all": "1895922",
         "lev_money_positions_long": "125453", "lev_money_positions_short": "497942"},
    ]
    return json.dumps(rows).encode()


def test_fetch_positioning_computes_net_pct_of_oi(monkeypatch):
    monkeypatch.setattr(bg, "_download_bytes", lambda *a, **k: _fake_cftc_json())
    df = bg.fetch_leveraged_fund_positioning()
    assert len(df) == 2
    expected = (125453 - 497942) / 1895922 * 100.0
    assert df["value"].iloc[-1] == pytest.approx(expected)
    assert df["as_of"].iloc[-1] == pd.Timestamp("2026-09-29")


def test_fetch_positioning_skips_malformed_rows(monkeypatch):
    rows = [
        {"report_date_as_yyyy_mm_dd": "2026-09-29T00:00:00.000",
         "open_interest_all": "0",  # zero OI -> must be skipped, not div-by-zero
         "lev_money_positions_long": "1", "lev_money_positions_short": "1"},
        {"report_date_as_yyyy_mm_dd": "2026-09-22T00:00:00.000"},  # missing fields
    ]
    monkeypatch.setattr(bg, "_download_bytes", lambda *a, **k: json.dumps(rows).encode())
    df = bg.fetch_leveraged_fund_positioning()
    assert df.empty


# ── _margin_debt_pct_gdp ─────────────────────────────────────────────────────

def test_margin_debt_pct_gdp_unit_conversion(monkeypatch):
    # debt in $ millions, GDP in $ billions -> ratio must convert, not conflate units
    monkeypatch.setattr(bg, "fetch_margin_debt", lambda force_refresh=False: pd.DataFrame({
        "as_of": [pd.Timestamp("2026-06-30"), pd.Timestamp("2026-07-31")],
        "value": [1_000_000.0, 1_100_000.0],  # $M -> $1.0T, $1.1T
    }))
    gdp_series = pd.Series(
        [30_000.0, 30_100.0],  # $B
        index=pd.to_datetime(["2026-04-30", "2026-07-31"]),
    )
    monkeypatch.setattr(
        "indicators.loader.fetch_series",
        lambda series_id, freq, force_refresh=False: gdp_series,
    )
    df = bg._margin_debt_pct_gdp()
    assert not df.empty
    # 1.1T / 30.1T * 100 ~= 3.65%
    last = df.set_index("as_of")["value"].sort_index().iloc[-1]
    assert last == pytest.approx(1_100_000.0 / 1000.0 / 30_100.0 * 100.0, rel=1e-6)


# ── compute_bubble_gauge ─────────────────────────────────────────────────────

def test_compute_bubble_gauge_assembles_all_three_dimensions(monkeypatch, tmp_path):
    buffett_payload = {
        "default": "z1",
        "numerators": {
            "z1": {
                "label": "FRED Z.1 (nonfinancial)",
                "series": [
                    {"date": "2026-01-01", "ratio": 180.0},
                    {"date": "2026-04-01", "ratio": 190.0},
                ],
            },
        },
    }
    buffett_path = tmp_path / "buffett_data.json"
    buffett_path.write_text(json.dumps(buffett_payload))
    monkeypatch.setattr("indicators.valuations.data_path", lambda: buffett_path)

    monkeypatch.setattr(bg, "_margin_debt_pct_gdp", lambda force_refresh=False: pd.DataFrame({
        "as_of": pd.to_datetime(["2026-06-30", "2026-07-31"]),
        "value": [3.5, 3.6],
    }))
    monkeypatch.setattr(bg, "fetch_leveraged_fund_positioning", lambda force_refresh=False: pd.DataFrame({
        "as_of": pd.to_datetime(["2026-09-22", "2026-09-29"]),
        "value": [-15.5, -19.6],
    }))

    dims = bg.compute_bubble_gauge()
    assert set(dims) == {"valuation", "leverage", "positioning"}
    for d in dims.values():
        assert d is not None
        assert d["z_label"] in ("Extreme", "Elevated", "Normal", "—")
    assert dims["valuation"]["current"] == pytest.approx(190.0)
    assert dims["leverage"]["current"] == pytest.approx(3.6)
    assert dims["positioning"]["current"] == pytest.approx(-19.6)


def test_compute_bubble_gauge_one_dimension_failing_does_not_break_others(monkeypatch, tmp_path):
    monkeypatch.setattr("indicators.valuations.data_path",
                        lambda: tmp_path / "does_not_exist.json")
    monkeypatch.setattr(bg, "_margin_debt_pct_gdp", lambda force_refresh=False: pd.DataFrame({
        "as_of": pd.to_datetime(["2026-06-30", "2026-07-31"]),
        "value": [3.5, 3.6],
    }))
    monkeypatch.setattr(bg, "fetch_leveraged_fund_positioning",
                        lambda force_refresh=False: pd.DataFrame(columns=["as_of", "value"]))

    dims = bg.compute_bubble_gauge()
    assert dims["valuation"] is None       # bad file path -> fails closed, not a crash
    assert dims["leverage"] is not None    # other dimensions unaffected
    assert dims["positioning"] is None     # empty frame -> None, not a fabricated reading
