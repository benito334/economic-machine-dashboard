"""Feedback dialog — the browser posts straight to Apps Script, so the tests
that matter are about what the server does NOT do, and about the client
contract that is easy to break silently."""
import importlib
import re

import pytest

from dashboard import feedback


@pytest.fixture
def configured(monkeypatch):
    """Reload the module with an endpoint configured.

    ENDPOINT/TOKEN are read at import time from the environment, so a plain
    monkeypatch of os.environ would not reach them.
    """
    monkeypatch.setenv("FEEDBACK_ENDPOINT", "https://example.test/exec")
    monkeypatch.setenv("FEEDBACK_TOKEN", "tok123")
    mod = importlib.reload(feedback)
    yield mod
    monkeypatch.delenv("FEEDBACK_ENDPOINT", raising=False)
    monkeypatch.delenv("FEEDBACK_TOKEN", raising=False)
    importlib.reload(feedback)


@pytest.fixture
def unconfigured(monkeypatch):
    monkeypatch.delenv("FEEDBACK_ENDPOINT", raising=False)
    monkeypatch.delenv("FEEDBACK_TOKEN", raising=False)
    mod = importlib.reload(feedback)
    yield mod
    importlib.reload(feedback)


# ── enabled() gating ─────────────────────────────────────────────────────────

def test_enabled_requires_both_endpoint_and_token(configured):
    assert configured.enabled() is True


def test_disabled_without_configuration(unconfigured):
    assert unconfigured.enabled() is False


def test_nav_button_hidden_when_unconfigured(unconfigured):
    """A button that silently discards what someone typed is worse than no
    button, so nothing is rendered without an endpoint."""
    assert unconfigured.nav_button() is None


def test_nav_button_rendered_when_configured(configured):
    assert configured.nav_button() is not None


def test_endpoint_only_is_not_enough(monkeypatch):
    monkeypatch.setenv("FEEDBACK_ENDPOINT", "https://example.test/exec")
    monkeypatch.delenv("FEEDBACK_TOKEN", raising=False)
    mod = importlib.reload(feedback)
    assert mod.enabled() is False
    importlib.reload(feedback)


# ── the server must not become a write surface ───────────────────────────────

def test_module_never_performs_a_write():
    """The whole point of routing feedback to a Sheet is that the deployment
    writes nothing. If this module ever grows a file/DB write, the design has
    regressed into the shape PUBLIC_MODE exists to prevent."""
    src = open(feedback.__file__.replace(".pyc", ".py")).read()
    body = src.split('"""', 2)[2]        # skip the module docstring
    for forbidden in ("open(", "write_text", "requests.", "urllib",
                      "get_connection", "to_csv", "to_parquet"):
        assert forbidden not in body, f"{forbidden} appeared in feedback.py"


def test_submit_is_clientside_not_a_server_callback():
    """SUBMIT_JS must stay a JS string handed to app.clientside_callback. If it
    were ported to a Python callback the POST would originate from the server,
    which defeats the design."""
    src = open("dashboard/charting.py").read()
    assert "app.clientside_callback(\n        _feedback.SUBMIT_JS," in src


# ── the client contract ──────────────────────────────────────────────────────

def _js():
    src = open(feedback.__file__.replace(".pyc", ".py")).read()
    return re.search(r'SUBMIT_JS = """(.*?)"""', src, re.S).group(1)


def test_posts_as_text_plain_to_avoid_cors_preflight():
    """application/json triggers a preflight OPTIONS, which Apps Script web
    apps cannot answer — the POST then never happens. This is the single most
    common way this integration silently fails."""
    js = _js()
    assert "text/plain;charset=utf-8" in js
    assert "application/json" not in js


def test_sends_no_ip_or_location_fields():
    """Explicit product decision (2026-10-05): no IP, no geolocation."""
    js = _js().lower()
    for banned in ("geolocation", "getcurrentposition", "ipapi", "ipinfo",
                   "latitude", "longitude"):
        assert banned not in js, f"{banned} must not be collected"


def test_every_return_path_matches_the_three_outputs():
    """The callback declares three Outputs (status text, status style, sent
    flag). A return of the wrong arity makes Dash drop the update silently."""
    js = _js()
    returns = re.findall(r"return \[([^\]]*)\]", js)
    assert returns, "no array returns found"
    for r in returns:
        # commas inside the style objects don't count — those are braces
        depth, commas = 0, 0
        for ch in r:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == "," and depth == 0:
                commas += 1
        assert commas == 2, f"expected 3 values, got {commas + 1}: {r[:60]}"


def test_app_version_is_populated(configured):
    """Shipped blank the first time: the JS read a window global that was never
    set, so every row recorded an empty App version. It now comes from the
    config store (git SHA, or APP_VERSION for images with no .git)."""
    assert "__EMD_VERSION__" not in configured.SUBMIT_JS
    assert "cfg.version" in configured.SUBMIT_JS
    cfg = next(s for s in configured.stores() if s.id == "feedback-config")
    assert "version" in cfg.data


def test_app_version_prefers_env_for_images_without_git(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "deadbee")
    mod = importlib.reload(feedback)
    assert mod.APP_VERSION == "deadbee"
    monkeypatch.delenv("APP_VERSION", raising=False)
    importlib.reload(feedback)


def test_message_is_capped_client_side_too():
    js = _js()
    assert "slice(0, cfg.max" in js
    assert feedback.MAX_MESSAGE == 4000


def test_config_store_carries_endpoint_and_token(configured):
    stores = configured.stores()
    cfg = next(s for s in stores if s.id == "feedback-config")
    assert cfg.data["endpoint"] == "https://example.test/exec"
    assert cfg.data["token"] == "tok123"
    assert cfg.data["max"] == configured.MAX_MESSAGE


def test_sent_store_exists_and_starts_false(configured):
    stores = configured.stores()
    sent = next(s for s in stores if s.id == "feedback-sent")
    assert sent.data is False


def _render(component) -> str:
    """Flatten a Dash component tree to a string.

    `to_plotly_json()` is only shallow — nested dbc components come back as
    objects json.dumps cannot serialise — so walk it instead.
    """
    out = []

    def walk(node):
        out.append(str(getattr(node, "id", "")))
        for attr in ("children", "value", "placeholder", "title"):
            v = getattr(node, attr, None)
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, (list, tuple)):
                for c in v:
                    walk(c)
            elif v is not None and hasattr(v, "_prop_names"):
                walk(v)

    walk(component)
    return " ".join(out)


def test_modal_has_the_expected_controls(configured):
    """Guards against an id rename silently detaching a callback."""
    rendered = _render(configured.modal())
    for cid in ("feedback-message", "feedback-email", "feedback-send",
                "feedback-cancel", "feedback-status", "feedback-modal"):
        assert cid in rendered, f"missing control: {cid}"


def test_dialog_discloses_what_is_collected(configured):
    """The disclosure is the reason collecting context is acceptable at all;
    if someone trims the copy, this should fail rather than quietly ship."""
    rendered = _render(configured.modal())
    assert "No IP address and no location are collected" in rendered
