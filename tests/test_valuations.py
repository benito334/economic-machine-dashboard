"""Buffett valuation feed + operator-only /valuations page wiring.

The standalone /valuations page was merged into the Bubble Gauge page on
2026-10-06 (valuations iframe on top, the three bubble dimensions below).
/valuations is kept as a gated alias, and the gated Flask routes that serve
the embedded app are unchanged — which is what most of this file covers.
"""
import json

from dashboard import charting as c
from dashboard.app_mode import OPERATOR_ONLY_ROUTES
from indicators import valuations as val


def _walk(node):
    """Recursively yield every Dash component in a layout tree."""
    from dash.development.base_component import Component

    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item)
        return
    if not isinstance(node, Component):
        return
    yield node
    yield from _walk(getattr(node, "children", None))


def test_operator_route_is_gated():
    assert "/valuations" in OPERATOR_ONLY_ROUTES
    assert "/valuations" in c._PAGE_MAP


def test_valuations_route_resolves_to_the_merged_page():
    assert c._PAGE_MAP["/valuations"] is c._page_bubble_gauge
    assert c._PAGE_MAP["/bubble-gauge"] is c._page_bubble_gauge


def test_merged_page_still_embeds_the_valuations_iframe():
    """The iframe moved from charting._page_valuations into
    bubble_gauge_monitor._valuations_section. Its `valuations-frame` id is
    load-bearing: the theme-sync clientside callback targets it by id."""
    from dashboard.bubble_gauge_monitor import _valuations_section

    frames = [n for n in _walk(_valuations_section())
              if type(n).__name__ == "Iframe"]
    assert len(frames) == 1
    assert frames[0].id == "valuations-frame"
    assert frames[0].src.startswith("/valuations/app")


def test_theme_sync_callback_still_targets_the_iframe():
    """Guards the one coupling the merge could silently break."""
    targets = [
        o.component_id
        for cb in c.app.callback_map.values()
        for o in (cb["output"] if isinstance(cb["output"], list) else [cb["output"]])
    ]
    assert "valuations-frame" in targets


def test_flask_routes_serve_for_operator():
    client = c.server.test_client()
    r = client.get("/valuations/app")
    assert r.status_code == 200
    assert b"Valuations" in r.data or b"Buffett" in r.data
    d = client.get("/valuations/buffett_data.json")
    assert d.status_code == 200
    payload = json.loads(d.data)
    assert "numerators" in payload


def test_flask_routes_404_in_public_mode(monkeypatch):
    monkeypatch.setattr(c, "PUBLIC_MODE", True)
    client = c.server.test_client()
    assert client.get("/valuations/app").status_code == 404
    assert client.get("/valuations/buffett_data.json").status_code == 404


def test_data_path_falls_back_to_bundled(monkeypatch, tmp_path):
    # When no live DATA_DIR copy exists, serve the repo-bundled JSON.
    monkeypatch.setattr(val, "DATA_DIR", tmp_path)
    assert val.data_path() == val.BUNDLED_JSON
    assert val.BUNDLED_JSON.exists()


def test_bundled_feed_shape():
    payload = json.loads(val.BUNDLED_JSON.read_text())
    assert payload["default"] in payload["numerators"]
    for n in payload["numerators"].values():
        assert n["series"] and "ratio" in n["series"][0]
        assert "current" in n and "mean" in n and "label" in n
