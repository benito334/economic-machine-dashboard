"""Traffic metrics — recording, aggregation, and access control."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def tr(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TRAFFIC_KEY", raising=False)
    monkeypatch.delenv("PUBLIC_MODE", raising=False)
    from dashboard import app_mode
    importlib.reload(app_mode)
    from dashboard import traffic
    importlib.reload(traffic)
    return traffic


def test_record_and_aggregate(tr):
    for p, s in [("/country", "a"), ("/overview", "a"), ("/country", "b"),
                 ("/relative", "b")]:
        tr.record_hit(p, s)
    m = tr.read_metrics()
    assert m["total_views"] == 4
    assert m["unique_visitors"] == 2
    assert m["top_paths"][0] == ("/country", 2)


def test_region_aggregation(tr):
    tr.record_hit("/country", "a", "Europe/London")
    tr.record_hit("/overview", "a", "Europe/London")
    tr.record_hit("/country", "b", "America/New_York")
    tr.record_hit("/relative", "c")                      # no tz → no region
    m = tr.read_metrics()
    regions = dict(m["top_regions"])
    assert regions == {"Europe/London": 2, "America/New_York": 1}
    assert m["top_regions"][0] == ("Europe/London", 2)


def test_assets_and_self_are_skipped(tr):
    tr.record_hit("/traffic", "a")
    tr.record_hit("/assets/app.js", "a")
    tr.record_hit("/_dash-update-component", "a")
    tr.record_hit("/country?x=1", "a")           # query stripped, counted once
    m = tr.read_metrics()
    assert m["total_views"] == 1
    assert m["top_paths"][0][0] == "/country"


def test_record_never_raises_on_bad_input(tr):
    tr.record_hit(None, None)                     # None path → "/", still counted
    tr.record_hit("/x", None)                     # no session → counted, not unique
    m = tr.read_metrics()
    assert m["total_views"] == 2
    assert m["unique_visitors"] == 0              # neither had a session id


def test_by_day_has_requested_span(tr):
    tr.record_hit("/country", "a")
    m = tr.read_metrics(days=7)
    assert len(m["by_day"]) == 7
    assert m["by_day"][-1][1] == 1                # today has the one view


def test_access_open_without_key(tr):
    assert tr.can_view("") is True
    assert tr.nav_visible() is True


def test_access_requires_key_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRAFFIC_KEY", "s3cret")
    from dashboard import app_mode
    importlib.reload(app_mode)
    from dashboard import traffic
    importlib.reload(traffic)
    assert traffic.can_view("") is False
    assert traffic.can_view("?key=s3cret") is True
    assert traffic.can_view("?key=nope") is False
    assert traffic.nav_visible() is False


def test_layout_renders_with_no_data(tr):
    assert tr.get_layout() is not None
