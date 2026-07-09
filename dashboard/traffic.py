"""Lightweight, self-contained web-traffic metrics — no third-party tracker.

Every page view is appended (one JSON line) to ``DATA_DIR/traffic.log``; the
``/traffic`` page reads and aggregates it. Append-only + short lines keeps it
concurrency-safe across many viewers without touching the single-writer DB.

Access: if ``TRAFFIC_KEY`` is set, the page requires ``?key=<TRAFFIC_KEY>``
(so it works on a public deploy — the operator bookmarks the keyed URL). With
no key set on a non-public instance, it's open and gets a sidebar link.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dash import dcc, html

from dashboard.app_mode import PUBLIC_MODE

DATA_DIR = Path(os.environ.get(
    "DATA_DIR", "/mnt/data/project_data/all_weather/indicators_machine"))
TRAFFIC_LOG = DATA_DIR / "traffic.log"
TRAFFIC_KEY = os.environ.get("TRAFFIC_KEY", "").strip()

# Don't count the metrics page itself, asset/framework requests, or noise.
_SKIP_PREFIXES = ("/traffic", "/_dash", "/assets", "/favicon")
_MAX_READ_BYTES = 8_000_000        # tail-read cap so the page stays fast


def record_hit(path: str, session: Optional[str], tz: Optional[str] = None) -> None:
    """Append one page-view record. Never raises (must not break routing).

    ``tz`` is the visitor's IANA browser timezone (e.g. "Europe/London") — a
    coarse region hint only; no IP or geolocation is ever recorded.
    """
    path = (path or "/").split("?")[0]
    if any(path.startswith(p) for p in _SKIP_PREFIXES):
        return
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"t": int(time.time()), "p": path,
                           "s": (session or "")[:40], "z": (tz or "")[:48]},
                          separators=(",", ":"))
        with open(TRAFFIC_LOG, "a") as fh:      # append is atomic for short lines
            fh.write(line + "\n")
    except Exception:
        pass


def _read_records() -> list[dict]:
    try:
        size = TRAFFIC_LOG.stat().st_size
        with open(TRAFFIC_LOG, "rb") as fh:
            if size > _MAX_READ_BYTES:
                fh.seek(size - _MAX_READ_BYTES)
                fh.readline()                    # discard partial first line
            raw = fh.read().decode("utf-8", "ignore")
    except Exception:
        return []
    out = []
    for ln in raw.splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def read_metrics(days: int = 30) -> dict:
    recs = _read_records()
    now = datetime.now(timezone.utc)
    today = now.date()
    since_7d = (now - timedelta(days=7)).timestamp()
    by_day: Counter = Counter()
    top_paths: Counter = Counter()
    top_regions: Counter = Counter()
    sessions: set = set()
    total = views_today = views_7d = 0
    day_keys = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    for r in recs:
        t = r.get("t")
        if not isinstance(t, (int, float)):
            continue
        total += 1
        top_paths[r.get("p", "/")] += 1
        if r.get("z"):
            top_regions[r["z"]] += 1
        if r.get("s"):
            sessions.add(r["s"])
        d = datetime.fromtimestamp(t, timezone.utc).date()
        by_day[d.isoformat()] += 1
        if d == today:
            views_today += 1
        if t >= since_7d:
            views_7d += 1
    return {
        "total_views": total,
        "unique_visitors": len(sessions),
        "views_today": views_today,
        "views_7d": views_7d,
        "by_day": [(k, by_day.get(k, 0)) for k in day_keys],
        "top_paths": top_paths.most_common(12),
        "top_regions": top_regions.most_common(12),
    }


# ── access control ────────────────────────────────────────────────────────────

def can_view(search: str) -> bool:
    """True if this request may see /traffic."""
    if TRAFFIC_KEY:
        qs = urllib.parse.parse_qs((search or "").lstrip("?"))
        return qs.get("key", [""])[0] == TRAFFIC_KEY
    return not PUBLIC_MODE          # open on a local/private instance


def nav_visible() -> bool:
    """Show the sidebar 'Traffic' link only where the page is openly viewable."""
    return not PUBLIC_MODE and not TRAFFIC_KEY


# ── page ──────────────────────────────────────────────────────────────────────

_CARD = {"background": "var(--card-bg)", "border": "1px solid var(--border-color)",
         "borderRadius": "8px", "padding": "12px 16px", "flex": "1 1 150px"}
_LABEL = {"fontSize": "0.66rem", "textTransform": "uppercase", "letterSpacing": "0.08em",
          "color": "var(--muted-color)", "marginBottom": "4px"}
_BIG = {"fontSize": "1.6rem", "fontWeight": "700", "fontFamily": "monospace",
        "color": "var(--font-color)"}


def _stat(label: str, value) -> html.Div:
    return html.Div([html.Div(label, style=_LABEL),
                     html.Div(f"{value:,}", style=_BIG)], style=_CARD)


def _day_bars(by_day: list[tuple]) -> html.Div:
    peak = max((c for _, c in by_day), default=0) or 1
    bars = []
    for d, c in by_day:
        h = 4 + int(96 * c / peak)          # px, min 4
        bars.append(html.Div([
            html.Div(str(c) if c else "", style={
                "fontSize": "0.6rem", "color": "var(--muted-color)",
                "textAlign": "center", "height": "12px"}),
            html.Div(title=f"{d}: {c} views", style={
                "height": f"{h}px", "background": "var(--slider-accent, #E8A317)",
                "borderRadius": "2px 2px 0 0", "opacity": "0.85"}),
            html.Div(d[5:], style={"fontSize": "0.55rem", "color": "var(--muted-color)",
                                   "textAlign": "center", "marginTop": "3px",
                                   "transform": "rotate(-60deg)", "height": "26px",
                                   "whiteSpace": "nowrap"}),
        ], style={"flex": "1 1 0", "display": "flex", "flexDirection": "column",
                  "justifyContent": "flex-end", "minWidth": "0"}))
    return html.Div(bars, style={"display": "flex", "gap": "3px",
                                 "alignItems": "flex-end", "height": "150px",
                                 "marginTop": "8px", "overflow": "hidden"})


def _count_table(pairs: list[tuple], empty: str) -> html.Table:
    rows = [html.Tr([html.Td(k, style={"padding": "3px 10px"}),
                     html.Td(f"{c:,}", style={"padding": "3px 10px", "textAlign": "right",
                                              "fontFamily": "monospace"})])
            for k, c in pairs]
    return html.Table(html.Tbody(rows or [html.Tr([html.Td(empty)])]),
                      style={"fontSize": "0.82rem", "borderCollapse": "collapse",
                             "marginTop": "6px"})


def get_layout() -> html.Div:
    m = read_metrics(30)
    return html.Div([
        html.H3("Traffic", style={"marginBottom": "2px"}),
        html.Div("Page views recorded on this dashboard. A visitor is one browser "
                 "session; counts exclude assets and this page.",
                 style={"fontSize": "0.8rem", "color": "var(--muted-color)",
                        "marginBottom": "14px"}),
        html.Div([
            _stat("Total page views", m["total_views"]),
            _stat("Unique visitors", m["unique_visitors"]),
            _stat("Views today", m["views_today"]),
            _stat("Views · last 7 days", m["views_7d"]),
        ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"}),
        html.Div("Views per day — last 30 days", style={**_LABEL, "marginTop": "18px"}),
        _day_bars(m["by_day"]),
        html.Div([
            html.Div([
                html.Div("Most-viewed pages", style={**_LABEL, "marginTop": "22px"}),
                _count_table(m["top_paths"], "No traffic recorded yet."),
            ], style={"flex": "1 1 300px"}),
            html.Div([
                html.Div("Top regions · browser timezone",
                         style={**_LABEL, "marginTop": "22px"}),
                _count_table(m["top_regions"], "No region data yet."),
            ], style={"flex": "1 1 300px"}),
        ], style={"display": "flex", "gap": "24px", "flexWrap": "wrap"}),
        html.Div("Region = the visitor's browser timezone (e.g. Europe/London). "
                 "No IP address or precise location is collected.",
                 style={"fontSize": "0.72rem", "color": "var(--muted-color)",
                        "marginTop": "12px"}),
    ], className="p-3", style={"maxWidth": "1000px"})
