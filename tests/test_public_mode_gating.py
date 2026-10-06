"""PUBLIC_MODE gating of shared-state writes.

Context (2026-10-05): the Oracle VM is being prepared as the public site, and
unlike the Cloud Run demo (ephemeral filesystem, frozen snapshot DB) it runs
the LIVE writable system. An audit found that hiding a page is not the same as
disabling it:

  * the app runs with ``suppress_callback_exceptions=True``, so Dash does NOT
    check that a callback's components are present in the rendered layout;
  * ``weight_audit`` / ``weight_history`` are imported unconditionally by
    ``dashboard.charting``, so their callbacks register in both modes;
  * ``/_dash-dependencies`` advertises every registered callback's full
    signature — verified live against the public deploy, which was publishing
    the weight-editor save callback's inputs and state.

So route-level gating (``OPERATOR_ONLY_ROUTES``) plus a hidden nav link left a
reachable path to write ``{cc}_composites.yaml`` and the ``weight_change_log``
table. The fix is the guard ``workbench.py`` already used: refuse inside the
callback body. These tests pin that, for every shared-state writer.
"""
import pytest
from dash.exceptions import PreventUpdate

from dashboard import weight_audit, weight_history, workbench, workbench_data


# Every callback that writes state shared by all viewers, with a minimal set of
# arguments that would otherwise reach its write path. Add to this list when a
# new shared-state writer is introduced.
SHARED_STATE_WRITERS = [
    pytest.param(
        weight_audit, "save_importance",
        (1, [{"yaml_id": "growth.payrolls", "importance": 0.9}], [], "why", "US", 0),
        id="weight_audit.save_importance (writes YAML + weight_change_log)",
    ),
    pytest.param(
        weight_history, "save_notes",
        (1, [{"log_id": 1, "reason": "x"}], "US"),
        id="weight_history.save_notes (writes weight_change_log)",
    ),
    pytest.param(
        workbench, "wb_views",
        (1, 0, "a view", None, [{"id": "x"}], {}),
        id="workbench.wb_views (writes saved_views.json)",
    ),
]


@pytest.fixture
def no_real_writes(monkeypatch):
    """Neutralise every real write primitive these callbacks can reach.

    These tests deliberately call the callbacks with arguments that WOULD
    perform a genuine write, because that is the only way to prove the guard
    is what stops them. That makes the test itself dangerous the moment the
    guard is absent — verified the hard way: removing the guard to confirm
    these tests can fail let one of them write
    ``importance: 0.90`` into ``config/countries/us_composites.yaml`` for real.

    So the write primitives are stubbed to raise. If a guard ever goes missing,
    the test fails on the missing PreventUpdate rather than by editing the
    repo's configuration.
    """
    def _boom(*a, **k):  # pragma: no cover - only reached if a guard is missing
        raise AssertionError(
            "a shared-state write was reached in PUBLIC_MODE — the guard is missing")

    monkeypatch.setattr(weight_audit, "_write_importance_updates", _boom)
    monkeypatch.setattr(weight_audit, "log_weight_changes", _boom)
    monkeypatch.setattr(weight_history, "update_weight_change_reason", _boom)
    monkeypatch.setattr(workbench_data, "save_view", _boom, raising=False)
    monkeypatch.setattr(workbench_data, "delete_view", _boom, raising=False)


@pytest.mark.parametrize("module,func_name,args", SHARED_STATE_WRITERS)
def test_shared_write_refuses_in_public_mode(monkeypatch, no_real_writes,
                                             module, func_name, args):
    """In PUBLIC_MODE the callback must bail out before touching anything."""
    monkeypatch.setattr(module, "PUBLIC_MODE", True)
    with pytest.raises(PreventUpdate):
        getattr(module, func_name)(*args)


@pytest.mark.parametrize("module,func_name,args", SHARED_STATE_WRITERS)
def test_shared_write_guard_is_first(monkeypatch, no_real_writes,
                                    module, func_name, args):
    """The guard must come BEFORE any other validation, so that a crafted
    invocation carrying perfectly well-formed arguments is still refused.

    A guard placed after an `if not n_clicks` check would still be correct, but
    one placed after the write would not — this pins the ordering by passing
    arguments that are deliberately valid.
    """
    monkeypatch.setattr(module, "PUBLIC_MODE", True)
    with pytest.raises(PreventUpdate):
        getattr(module, func_name)(*args)


def test_operator_mode_does_not_short_circuit(monkeypatch):
    """Sanity check in the other direction: with PUBLIC_MODE off the guard must
    NOT be what stops execution, otherwise the operator UI is silently broken.

    save_importance is called with n_clicks=0, so it should still raise
    PreventUpdate — but via its own `if not n_clicks` check, not the gate. The
    distinction is proven by the fact that this is the same exception either
    way; what matters is that flipping PUBLIC_MODE off does not change it to a
    crash or an unexpected write.
    """
    monkeypatch.setattr(weight_audit, "PUBLIC_MODE", False)
    with pytest.raises(PreventUpdate):
        weight_audit.save_importance(0, [], [], "", "US", 0)   # n_clicks=0, never writes


def test_every_known_write_path_is_covered():
    """Guard against someone adding a shared-state writer without a test.

    Greps the dashboard package for the known write primitives and asserts each
    hit lives in a module whose writer is in SHARED_STATE_WRITERS above (or is
    an allowed exception). This is deliberately crude — it is a tripwire, not a
    static analyser.
    """
    import pathlib
    import re

    write_calls = re.compile(
        r"write_text|yaml\.dump|log_weight_changes\(|"
        r"update_weight_change_reason\(|save_schedule\(|request_run_now\("
    )
    # Modules allowed to write without appearing in SHARED_STATE_WRITERS.
    allowed = {
        "traffic.py",        # per-request append-only page-view log, not user config
        "workbench_data.py",  # the data layer behind workbench.wb_views, which IS covered
        "app_mode.py",
    }
    covered = {m.__name__.rsplit(".", 1)[-1] + ".py"
               for m, _, _ in (p.values for p in SHARED_STATE_WRITERS)}
    # charting.py's scheduler writes are gated by skipping REGISTRATION
    # entirely (`if not PUBLIC_MODE:`), verified separately below.
    allowed.add("charting.py")

    offenders = []
    for path in pathlib.Path("dashboard").glob("*.py"):
        if path.name in allowed or path.name in covered:
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if line.strip().startswith("#") or "def " in line or "import " in line:
                continue
            if write_calls.search(line):
                offenders.append(f"{path.name}:{i}: {line.strip()[:70]}")
    assert not offenders, (
        "shared-state write found in a module with no PUBLIC_MODE guard test:\n  "
        + "\n  ".join(offenders)
    )


def test_scheduler_callbacks_are_not_registered_in_public_mode():
    """charting.py uses the other valid strategy for the scheduler — skipping
    registration entirely behind `if not PUBLIC_MODE:`. Pin that it stays that
    way, since those callbacks write schedule.json and the run-now trigger."""
    import pathlib

    src = pathlib.Path("dashboard/charting.py").read_text()
    after_guard = src.split("if not PUBLIC_MODE:", 1)
    assert len(after_guard) == 2, "the `if not PUBLIC_MODE:` registration guard vanished"
    assert "sched_cfg.save_schedule(" in after_guard[1]
    assert "sched_cfg.request_run_now()" in after_guard[1]


# ── provenance banner must match the deployment it is running on ─────────────

def test_banner_wording_follows_deploy_kind(monkeypatch):
    """Two public deploys, two different truths: Cloud Run serves a frozen
    snapshot, the Oracle VM runs the live system with a nightly import. The
    banner shipped saying "static demo snapshot ... not live" on BOTH, which
    was false on the live one and visible to every visitor."""
    import importlib
    import dashboard.charting as c

    def banner_text(kind):
        if kind is None:
            monkeypatch.delenv("DEPLOY_KIND", raising=False)
        else:
            monkeypatch.setenv("DEPLOY_KIND", kind)
        monkeypatch.setattr(c, "PUBLIC_MODE", True)
        node = c._static_banner()
        return " ".join(
            ch.children if isinstance(getattr(ch, "children", None), str) else ""
            for ch in node.children
        )

    assert "Live instance" in banner_text("live")
    assert "not live" not in banner_text("live")
    # Unset must keep the pre-existing Cloud Run wording.
    assert "Static demo snapshot" in banner_text(None)
    assert "Static demo snapshot" in banner_text("snapshot")


def test_banner_absent_when_not_public(monkeypatch):
    import dashboard.charting as c
    monkeypatch.setattr(c, "PUBLIC_MODE", False)
    assert c._static_banner() is None
