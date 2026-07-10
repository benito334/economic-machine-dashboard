"""Per-country Data Confidence scoring.

A diagnostic is only as trustworthy as the data under it. This module grades
how much to trust each country's reads from three properties we already track
on every signal:

  • Freshness  — is the data current, or stale (and how badly)?  (is_stale + age)
  • Directness — is it native data, or a proxy / constructed stand-in?
  • Depth      — how many signals feed the force? (a read on 2 is shakier than 8)

Each scored force gets a 0–100 score → A/B/C/D grade; the country's overall
grade is the weighted average across forces (growth + inflation weighted most,
since they drive the headline regime). Pure logic — no Dash imports — so it is
cheap to test and reuse. Rendering helpers live in the consuming pages.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb

_DB = Path(os.environ.get(
    "DB_PATH", "/mnt/data/db/all_weather/indicators_machine/signals.duckdb"))

# Forces that feed the regime reads, with their weight in the overall roll-up.
# The DB stores interest-rate signals under force "policy".
_SCORED_FORCES: dict[str, float] = {
    "growth": 0.30,
    "inflation": 0.30,
    "policy": 0.20,
    "credit": 0.20,
}
_FORCE_LABEL = {"growth": "Growth", "inflation": "Inflation",
                "policy": "Rate", "credit": "Credit"}

_DEPTH_TARGET = 5          # signals for full-depth credit
_W_FRESH, _W_DIRECT, _W_DEPTH = 0.45, 0.30, 0.25

# Grade bands (score ≥ threshold) → (grade, colour name, hex).
_BANDS = [
    (85, "A", "green", "#2e9e5b"),
    (70, "B", "blue", "#3b82f6"),
    (55, "C", "amber", "#E8A317"),
    (0, "D", "red", "#d9534f"),
]


def _as_date(v: Any) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def grade_of(score: float) -> dict[str, Any]:
    for thresh, letter, name, hexc in _BANDS:
        if score >= thresh:
            return {"score": round(score), "grade": letter,
                    "color": name, "hex": hexc}
    return {"score": round(score), "grade": "D", "color": "red", "hex": "#d9534f"}


def _force_score(sigs: list[tuple], ref: date) -> dict[str, Any]:
    """Score one (country, force) bucket of latest-per-signal rows."""
    n = len(sigs)
    fresh_sum = direct_sum = 0.0
    stale_n = proxy_n = 0
    for (as_of, is_stale, is_proxy, is_constructed, low_history) in sigs:
        months_old = (ref - _as_date(as_of)).days / 30.4
        if is_stale:
            stale_n += 1
        # Graded freshness: a signal just past its window is far better than one
        # years out of date (e.g. an abandoned annual feed).
        if not is_stale:
            f = 1.0
        elif months_old <= 12:
            f = 0.5
        elif months_old <= 24:
            f = 0.25
        else:
            f = 0.1
        fresh_sum += f
        if is_proxy or is_constructed:
            proxy_n += 1
            d = 0.5
        else:
            d = 1.0
        if low_history:
            d -= 0.1
        direct_sum += max(d, 0.0)

    freshness = fresh_sum / n
    directness = direct_sum / n
    depth = min(n / _DEPTH_TARGET, 1.0)
    score = 100 * (_W_FRESH * freshness + _W_DIRECT * directness + _W_DEPTH * depth)
    # A read on 1–2 signals can't be high-confidence no matter how fresh — cap it.
    if n == 1:
        score = min(score, 68)      # at most C
    elif n == 2:
        score = min(score, 82)      # at most B
    out = grade_of(score)
    out.update(n=n, stale=stale_n, proxy=proxy_n,
               freshness=round(freshness, 2), directness=round(directness, 2))
    return out


def compute_scores(ref: date | None = None) -> dict[str, dict[str, Any]]:
    """Return {country_code: {"overall": {...}, "forces": {force: {...}}}}."""
    ref = ref or date.today()
    forces_sql = ", ".join(f"'{f}'" for f in _SCORED_FORCES)
    try:
        con = duckdb.connect(str(_DB), read_only=True)
        rows = con.execute(f"""
            SELECT country, force, as_of, is_stale, is_proxy,
                   is_constructed, low_history
            FROM signals
            WHERE force IN ({forces_sql})
            QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY as_of DESC) = 1
        """).fetchall()
        con.close()
    except Exception:
        return {}

    buckets: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    for country, force, as_of, stale, proxy, constr, low in rows:
        buckets[(country.lower(), force)].append((as_of, stale, proxy, constr, low))

    per_country: dict[str, dict[str, Any]] = {}
    for (cc, force), sigs in buckets.items():
        per_country.setdefault(cc, {})[force] = _force_score(sigs, ref)

    result: dict[str, dict[str, Any]] = {}
    for cc, forces in per_country.items():
        num = den = 0.0
        for f, w in _SCORED_FORCES.items():
            if f in forces:
                num += w * forces[f]["score"]
                den += w
        overall = grade_of(num / den if den else 0.0)
        result[cc] = {"overall": overall, "forces": forces}
    return result


def country_score(country_code: str, ref: date | None = None) -> dict[str, Any] | None:
    """Convenience: scores for one country (or None if it has no scored data)."""
    return compute_scores(ref).get(country_code.lower())


def force_caveat(force_info: dict[str, Any] | None) -> str:
    """Short human caveat for a force, e.g. '5 signals · 4 stale, 2 proxy'."""
    if not force_info:
        return "no data"
    n = force_info["n"]
    lead = f"{n} signal{'s' if n != 1 else ''}"
    bits = []
    if force_info.get("stale"):
        bits.append(f"{force_info['stale']} stale")
    if force_info.get("proxy"):
        bits.append(f"{force_info['proxy']} proxy")
    return f"{lead} · {', '.join(bits)}" if bits else lead


def breakdown_text(scores: dict[str, Any]) -> str:
    """One-line tooltip breakdown across forces for a country."""
    parts = []
    for f in _SCORED_FORCES:
        fi = scores["forces"].get(f)
        if fi:
            parts.append(f"{_FORCE_LABEL[f]} {fi['grade']} ({force_caveat(fi)})")
    return "Data confidence — " + "; ".join(parts)
