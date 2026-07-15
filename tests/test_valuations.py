"""Buffett valuation feed + operator-only /valuations page wiring."""
import json

from dashboard import charting as c
from dashboard.app_mode import OPERATOR_ONLY_ROUTES
from indicators import valuations as val


def test_operator_route_is_gated():
    assert "/valuations" in OPERATOR_ONLY_ROUTES
    assert "/valuations" in c._PAGE_MAP


def test_page_is_an_embedded_iframe():
    lay = c._page_valuations()
    assert type(lay).__name__ == "Div"
    assert type(lay.children).__name__ == "Iframe"
    assert lay.children.src.startswith("/valuations/app")


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
