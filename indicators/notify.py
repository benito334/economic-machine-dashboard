"""Operator alerts: Telegram push + Healthchecks.io dead-man's-switch.

Both are optional — unset env vars mean "not configured," which logs a
warning and returns False rather than raising. A notification failure must
never crash the pipeline/scheduler it's reporting on.

Env vars (all optional, read from .env):
  TELEGRAM_BOT_TOKEN   — bot token from @BotFather
  TELEGRAM_CHAT_ID     — target chat id (a DM, group, or channel)
  HEALTHCHECK_PING_URL — a healthchecks.io (or compatible) check URL; pinged
                         on success, pinged at "{url}/fail" on failure
"""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger("notify")

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT = 10


def send_telegram(message: str) -> bool:
    """POST a message to the configured Telegram chat. Returns True on success."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.warning("Telegram not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID unset) — skipping alert")
        return False
    try:
        resp = requests.post(
            _TELEGRAM_API.format(token=token),
            json={"chat_id": chat_id, "text": message},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Telegram alert failed to send: %s", exc)
        return False


def ping_healthcheck(success: bool = True) -> bool:
    """Ping the configured healthchecks.io URL. Returns True if the ping went out."""
    url = os.environ.get("HEALTHCHECK_PING_URL", "").strip()
    if not url:
        return False
    try:
        target = url if success else f"{url.rstrip('/')}/fail"
        resp = requests.get(target, timeout=_TIMEOUT)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Healthcheck ping failed: %s", exc)
        return False
