"""Sidebar data-freshness stamp (last DB write time)."""
from dashboard import charting as c


def test_freshness_helper_returns_string():
    s = c._data_freshness_str()
    assert isinstance(s, str) and s               # a formatted date-time, or "—"


def test_freshness_helper_degrades_gracefully(monkeypatch):
    # Point at a missing DB path → helper must not raise.
    import dashboard.charting_data as cd
    from pathlib import Path
    monkeypatch.setattr(cd, "DB_PATH", Path("/nonexistent/nope.duckdb"))
    assert c._data_freshness_str() == "—"


def test_freshness_callback_registered():
    # The stamp refreshes on navigation.
    assert callable(c._refresh_data_stamp)
    assert c._refresh_data_stamp({"page": "/"})
