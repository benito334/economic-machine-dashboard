"""Tests for pipeline orchestration and failure propagation."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from indicators.models import CompositeSnapshot, DebtStressSnapshot


class _FakeConn:
    def close(self) -> None:
        pass


def _binding(country: str = "US") -> SimpleNamespace:
    return SimpleNamespace(
        id="growth.payrolls",
        country=country,
        frequency="M",
        verified=True,
    )


def _prepare_run(monkeypatch, tmp_path, country_files: list[str] | None = None):
    import indicators.pipeline as pipeline

    config_dir = tmp_path / "config"
    countries_dir = config_dir / "countries"
    countries_dir.mkdir(parents=True)
    (config_dir / "us_bindings.yaml").write_text("bindings: []\n")
    for name in country_files or []:
        (countries_dir / name).write_text("bindings: []\n")

    monkeypatch.setattr(pipeline, "_CONFIG_DIR", config_dir)
    monkeypatch.setattr(pipeline, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(pipeline, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(pipeline, "init_schema", lambda _conn: None)
    monkeypatch.setattr(pipeline, "delete_future_signals", lambda _conn: 0)
    monkeypatch.setattr(pipeline, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pipeline, "load_composites_config", lambda _country="US": {})
    monkeypatch.setattr(pipeline, "load_longterm_stress_config", lambda _path: {"components": [{}]})
    monkeypatch.setattr(pipeline, "upsert_composites", lambda _conn, snaps: len(snaps))
    monkeypatch.setattr(pipeline, "update_rolling_composites", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(pipeline, "upsert_debt_stress", lambda _conn, snaps: len(snaps))
    monkeypatch.setattr(
        pipeline,
        "compute_composite_history",
        lambda *_args, **_kwargs: [CompositeSnapshot(country="US", as_of=date(2024, 1, 31))],
    )
    monkeypatch.setattr(
        pipeline,
        "compute_debt_stress_history",
        lambda *_args, **_kwargs: [DebtStressSnapshot(country="US", as_of=date(2024, 3, 31))],
    )

    def _load_bindings(path):
        stem = path.stem
        country = stem.split("_")[0].upper() if stem.endswith("_bindings") else "US"
        return [_binding(country)]

    monkeypatch.setattr(pipeline, "load_bindings", _load_bindings)
    monkeypatch.setattr(
        pipeline,
        "run_country",
        lambda *_args, **_kwargs: {"ok": 1, "empty": 0, "error": 0, "sanity_warn": 0},
    )
    return pipeline


def test_run_exits_nonzero_when_us_composites_fail(monkeypatch, tmp_path):
    pipeline = _prepare_run(monkeypatch, tmp_path)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("composite failed")

    monkeypatch.setattr(pipeline, "compute_composite_history", _boom)

    with pytest.raises(SystemExit) as exc:
        pipeline.run()

    assert exc.value.code == 1


def test_run_exits_nonzero_when_us_debt_stress_has_no_snapshots(monkeypatch, tmp_path):
    pipeline = _prepare_run(monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, "compute_debt_stress_history", lambda *_args, **_kwargs: [])

    with pytest.raises(SystemExit) as exc:
        pipeline.run()

    assert exc.value.code == 1


def test_run_exits_nonzero_when_enabled_country_ingestion_fails(monkeypatch, tmp_path):
    pipeline = _prepare_run(monkeypatch, tmp_path, ["ez_bindings.yaml"])

    def _run_country(_conn, yaml_path, **_kwargs):
        if yaml_path.name == "ez_bindings.yaml":
            return {"ok": 0, "empty": 1, "error": 0, "sanity_warn": 0}
        return {"ok": 1, "empty": 0, "error": 0, "sanity_warn": 0}

    monkeypatch.setattr(pipeline, "run_country", _run_country)

    with pytest.raises(SystemExit) as exc:
        pipeline.run()

    assert exc.value.code == 1


def test_run_exits_nonzero_when_enabled_country_composites_empty(monkeypatch, tmp_path):
    pipeline = _prepare_run(monkeypatch, tmp_path, ["kr_bindings.yaml"])

    def _compute(_conn, country, *_args, **_kwargs):
        if country == "KR":
            return []
        return [CompositeSnapshot(country=country, as_of=date(2024, 1, 31))]

    monkeypatch.setattr(pipeline, "compute_composite_history", _compute)

    with pytest.raises(SystemExit) as exc:
        pipeline.run()

    assert exc.value.code == 1
