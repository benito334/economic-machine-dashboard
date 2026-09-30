"""Telegram + healthchecks.io alerting — graceful no-op when unconfigured."""
from __future__ import annotations

from unittest.mock import patch

from indicators import notify


# ── Telegram ────────────────────────────────────────────────────────────────

def test_send_telegram_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with patch("indicators.notify.requests.post") as mock_post:
        assert notify.send_telegram("hello") is False
        mock_post.assert_not_called()


def test_send_telegram_posts_when_configured(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    with patch("indicators.notify.requests.post") as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        assert notify.send_telegram("hello") is True
        url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
        assert "abc123" in url
        assert kwargs["json"] == {"chat_id": "999", "text": "hello"}


def test_send_telegram_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    with patch("indicators.notify.requests.post", side_effect=RuntimeError("network down")):
        assert notify.send_telegram("hello") is False


# ── healthchecks.io ─────────────────────────────────────────────────────────

def test_ping_healthcheck_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv("HEALTHCHECK_PING_URL", raising=False)
    with patch("indicators.notify.requests.get") as mock_get:
        assert notify.ping_healthcheck(success=True) is False
        mock_get.assert_not_called()


def test_ping_healthcheck_success_hits_base_url(monkeypatch):
    monkeypatch.setenv("HEALTHCHECK_PING_URL", "https://hc-ping.com/xyz")
    with patch("indicators.notify.requests.get") as mock_get:
        mock_get.return_value.raise_for_status.return_value = None
        assert notify.ping_healthcheck(success=True) is True
        mock_get.assert_called_once_with("https://hc-ping.com/xyz", timeout=notify._TIMEOUT)


def test_ping_healthcheck_failure_hits_fail_suffix(monkeypatch):
    monkeypatch.setenv("HEALTHCHECK_PING_URL", "https://hc-ping.com/xyz")
    with patch("indicators.notify.requests.get") as mock_get:
        mock_get.return_value.raise_for_status.return_value = None
        assert notify.ping_healthcheck(success=False) is True
        mock_get.assert_called_once_with("https://hc-ping.com/xyz/fail", timeout=notify._TIMEOUT)


def test_ping_healthcheck_network_error_does_not_raise(monkeypatch):
    monkeypatch.setenv("HEALTHCHECK_PING_URL", "https://hc-ping.com/xyz")
    with patch("indicators.notify.requests.get", side_effect=RuntimeError("network down")):
        assert notify.ping_healthcheck(success=True) is False
