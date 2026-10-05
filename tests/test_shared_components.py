"""Tests for dashboard.shared_components pure-logic helpers."""
from dashboard.shared_components import VERDICT_COLOR, summarize_validator_axis


def test_all_agree_rolls_up_to_agree():
    rows = [{"verdict": "AGREE"}, {"verdict": "AGREE"}]
    out = summarize_validator_axis(rows)
    assert out == {"verdict": "AGREE", "n_agree": 2, "n_partial": 0,
                   "n_contradict": 0, "n_unknown": 0}


def test_any_contradict_wins_over_everything():
    rows = [{"verdict": "AGREE"}, {"verdict": "AGREE"}, {"verdict": "CONTRADICT"},
            {"verdict": "PARTIAL"}]
    out = summarize_validator_axis(rows)
    assert out["verdict"] == "CONTRADICT"
    assert out["n_agree"] == 2 and out["n_partial"] == 1 and out["n_contradict"] == 1


def test_any_partial_wins_when_no_contradict():
    rows = [{"verdict": "AGREE"}, {"verdict": "PARTIAL"}]
    assert summarize_validator_axis(rows)["verdict"] == "PARTIAL"


def test_unknown_rows_are_ignored_not_counted_toward_verdict():
    rows = [{"verdict": "UNKNOWN"}, {"verdict": "UNKNOWN"}, {"verdict": "AGREE"}]
    out = summarize_validator_axis(rows)
    assert out["verdict"] == "AGREE"
    assert out["n_unknown"] == 2


def test_all_unknown_or_empty_has_no_verdict():
    assert summarize_validator_axis([{"verdict": "UNKNOWN"}])["verdict"] is None
    assert summarize_validator_axis([])["verdict"] is None


def test_verdict_color_covers_every_verdict_and_unknown_fallback():
    for v in ("AGREE", "PARTIAL", "CONTRADICT", "UNKNOWN"):
        assert v in VERDICT_COLOR


# ── info-icon ids ────────────────────────────────────────────────────────────
# Content-addressed (2026-10-05): the ids used to come from a module counter
# that never reset, so each render minted fresh ones and left every prior
# dbc.Tooltip target dangling. Two things have to hold: stable across renders,
# and unique within one page's layout.

def test_monitor_page_layouts_have_no_duplicate_info_icon_ids():
    import pytest
    from dash.development.base_component import Component

    def _info_ids(node, out):
        cid = getattr(node, "id", None)
        if isinstance(cid, str) and cid.startswith("mon-info-"):
            out.append(cid)
        for child in getattr(node, "children", None) or []:
            if isinstance(child, Component):
                _info_ids(child, out)
            elif isinstance(child, list):
                for c in child:
                    if isinstance(c, Component):
                        _info_ids(c, out)
        return out

    builders = []
    for mod, fn, args in (
        ("dashboard.fed_monitor", "get_layout", ()),
        ("dashboard.case_study_monitor", "get_layout", ()),
        ("dashboard.market_expectations", "get_layout", ()),
        ("dashboard.bubble_gauge_monitor", "get_layout", ()),
        ("dashboard.ai_capex_monitor", "get_layout", ()),
        ("dashboard.validator_monitor", "get_layout", ()),
        ("dashboard.central_bank_monitor", "_country_block", ("US",)),
        ("dashboard.force_detail", "get_layout", ("growth",)),
        ("dashboard.force_detail", "get_layout", ("inflation",)),
    ):
        import importlib
        builders.append((f"{mod}.{fn}{args}", getattr(importlib.import_module(mod), fn), args))

    checked = 0
    for label, build, args in builders:
        try:                      # DB-guarded, same convention as the layout tests
            layout = build(*args)
        except Exception:
            continue
        # the dbc.Tooltip's `target` is a prop, not an id, so only the ⓘ spans
        # are collected here — every one of them must be unique in the layout
        ids = _info_ids(layout, [])
        dupes = {i for i in ids if ids.count(i) > 1}
        assert not dupes, f"{label} reuses info-icon id(s): {sorted(dupes)}"
        checked += 1
    if checked == 0:
        pytest.skip("no page layout could be built (signals DB absent)")
