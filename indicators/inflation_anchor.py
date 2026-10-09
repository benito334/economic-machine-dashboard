"""Inflation anchored to the central-bank target, plus impulse/persistence split.

Implements two Ray Dalio rulings from 2026-10-03 (see
docs/Guidance/ray_dalio_review_log.md, session 2026-10-03):

  1. ANCHOR. "Growth is a force that doesn't have a natural 'right' level...
     Inflation is different. Inflation has a target... The main chip should be
     the distance from target. That's the number that matters for policy and
     markets. But you can also show a relative Z-score as a secondary read...
     you want to make it clear which is the anchor."

  2. SPLIT. "Inflation is a two-part machine: an impulse that shows up in
     flexible prices -- especially commodities and expectations -- and a
     persistence that shows up in core PCE, core CPI, wages and other sticky
     components." Combine at roughly 30% impulse / 70% persistence and publish
     both side by side.

Why this exists: the 2026-10-03 chip audit found the inflation composite read
+0.04 on full history, -0.31 at 90m and -0.90 at 60m for the SAME month. A
relative-only frame said "below its own norm" in the week the Fed hiked to
3.75-4.00% with headline CPI at 3.4%. The target gap has no such ambiguity.

This module is READ-ONLY against the signals DB and derives everything from
signals already ingested — it needs no new series, no new DB columns and no
pipeline re-run. Every parameter lives in config/inflation_anchor.yaml.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
import yaml

from store.store import DB_PATH

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parents[1] / "config" / "inflation_anchor.yaml"

# Labels for the anchored read. Deliberately NOT the legacy
# Inflation/Transition/Disinflation vocabulary: those describe movement relative
# to a country's own history, while these describe position against the target.
# Keeping them distinct stops the two reads being silently conflated.
ABOVE, AT, BELOW = "Above Target", "At Target", "Below Target"


@lru_cache(maxsize=1)
def load_config(path: Optional[str] = None) -> dict:
    with open(path or _CONFIG_PATH) as fh:
        return yaml.safe_load(fh)


@dataclass(frozen=True)
class AnchorRead:
    """The anchored inflation read for one country at one date.

    gap_pp is the headline number: inflation minus target, in percentage points.
    Everything else is secondary by design — Ray: "If you just show two numbers,
    people will get confused. If you make one the anchor and the other a
    secondary signal, you help people see what matters most."
    """

    country: str
    as_of: Optional[str]
    label: str
    gap_pp: Optional[float]
    inflation_pct: Optional[float]
    target_pct: Optional[float]
    gap_series: Optional[str]
    gap_change_3m_pp: Optional[float]
    far_from_target: bool
    official_band_pp: Optional[float]
    is_stale: bool = False
    age_months: Optional[int] = None
    note: str = ""

    @property
    def direction(self) -> str:
        """Is the gap closing or widening? Secondary read, never the anchor.

        Compares |gap| now against |gap| three months ago. Comparing SIGNS
        instead gets a zero-crossing backwards: AU went from +1.31pp to -0.10pp,
        which is clearly closing, but both gap and change are negative so a
        sign test calls it widening.
        """
        if self.gap_pp is None or self.gap_change_3m_pp is None:
            return "unknown"
        if abs(self.gap_change_3m_pp) < 0.05:
            return "flat"
        prev = self.gap_pp - self.gap_change_3m_pp
        return "widening" if abs(self.gap_pp) > abs(prev) else "closing"


def _connect():
    return duckdb.connect(str(DB_PATH), read_only=True)


def load_inflation_signals(country: str, conn=None) -> pd.DataFrame:
    """Every inflation-force signal for a country: id, as_of, value, zscore."""
    own = conn is None
    conn = conn or _connect()
    try:
        df = conn.execute(
            "SELECT id, as_of, value, zscore, is_stale FROM signals "
            "WHERE country = ? AND id LIKE ? AND value IS NOT NULL "
            "ORDER BY as_of",
            [country, f"%.inflation.%"],
        ).df()
    finally:
        if own:
            conn.close()
    if not df.empty:
        df["as_of"] = pd.to_datetime(df["as_of"])
        df["concept"] = df["id"].str.rsplit(".", n=1).str[-1]
    return df


def _series_for(df: pd.DataFrame, concept: str, col: str = "value") -> pd.Series:
    hit = df[df["concept"] == concept]
    if hit.empty:
        return pd.Series(dtype=float)
    s = hit.set_index("as_of")[col].dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def _rank_candidates(df: pd.DataFrame, spec: dict) -> list:
    """Configured gap series that have data, FRESHEST first, config order as tie-break.

    Several countries' monthly CPI mirrors are dead (GB, KR, CN, IN, MX, AU —
    docs/Guidance/data_source_wishlist.md) and strict config order would anchor
    the read to a print over a year old when a live IMF annual bridge exists.

    Factored out of anchor_read so `gap_series` applies the IDENTICAL rule. Two
    copies of a selection rule is how the chip and its own display card drift
    apart, which is the defect this whole module exists to fix.
    """
    cands = []
    for rank, concept in enumerate(spec["gap_series"]):
        cand = _series_for(df, concept)
        if not cand.empty:
            cands.append((cand.index[-1], -rank, concept, cand))
    cands.sort(reverse=True)
    return cands


def gap_series(
    country: str = "US",
    *,
    config: Optional[dict] = None,
    signals: Optional[pd.DataFrame] = None,
    conn=None,
) -> pd.Series:
    """Month-end PeriodIndex -> distance from target in percentage points.

    The series form of `anchor_read().gap_pp`, for callers that need the whole
    history cheaply — the regime classifier runs this over 500+ months per
    country and cannot afford a per-month DB read.

    Same selection rule as `anchor_read` (`_rank_candidates`), evaluated as of
    each month so a historical read never sees a print published later.

    A month whose freshest candidate is older than `bands.max_age_months`
    yields NaN rather than a stale number: a chip should not claim a state
    from a year-old observation. Countries on an annual IMF bridge legitimately
    sit near that bound, which is why the default is generous rather than tight.
    """
    cfg = config or load_config()
    cc = country.upper()
    spec = cfg["countries"].get(cc)
    if spec is None:
        return pd.Series(dtype=float)
    df = signals if signals is not None else load_inflation_signals(cc, conn)
    if df.empty:
        return pd.Series(dtype=float)

    target = float(spec["target_pct"])
    max_age = int(cfg["bands"].get("max_age_months", 12))

    ranked = _rank_candidates(df, spec)
    if not ranked:
        return pd.Series(dtype=float)

    # Per concept: month-end value and the date that value was actually observed,
    # both forward-filled, so "freshest as of month m" is answerable per row.
    vals, obs, order = {}, {}, {}
    for _last, neg_rank, concept, s in ranked:
        m = s.copy()
        m.index = pd.PeriodIndex(m.index, freq="M")
        m = m[~m.index.duplicated(keep="last")]
        d = pd.Series(m.index, index=m.index)
        vals[concept] = m
        obs[concept] = d
        order[concept] = -neg_rank          # back to config rank, lower = preferred

    # Carry forward to the CURRENT month, not just to the last observation.
    # A print from three months ago is still the live read — that is exactly
    # what anchor_read does when `as_of` is None — and it is `max_age_months`,
    # not the end of the data, that decides when carrying stops.
    last_obs = max(v.index.max() for v in vals.values())
    end = max(last_obs, pd.Timestamp.today().to_period("M"))
    idx = pd.period_range(min(v.index.min() for v in vals.values()), end, freq="M")
    V = pd.DataFrame({c: v.reindex(idx).ffill() for c, v in vals.items()})
    O = pd.DataFrame({c: o.reindex(idx).ffill() for c, o in obs.items()})

    out = {}
    for m in idx:
        best, best_key = None, None
        for c in V.columns:
            v, o = V.at[m, c], O.at[m, c]
            if pd.isna(v) or pd.isna(o):
                continue
            key = (o, -order[c])            # freshest wins; config order breaks ties
            if best_key is None or key > best_key:
                best_key, best = key, (v, o)
        if best is None:
            continue
        v, o = best
        if (m - o).n > max_age:
            continue                        # too stale to claim a state
        out[m] = float(v) * 100.0 - target  # signals are decimal fractions
    return pd.Series(out, dtype=float).sort_index()


def anchor_read(
    country: str = "US",
    as_of: Optional[str] = None,
    config: Optional[dict] = None,
    signals: Optional[pd.DataFrame] = None,
) -> AnchorRead:
    """Distance from the central-bank target — the anchor read.

    Picks the first configured `gap_series` that actually has data, so a country
    missing core CPI falls back to headline rather than returning nothing.
    """
    cfg = config or load_config()
    cc = country.upper()
    spec = cfg["countries"].get(cc)
    if spec is None:
        return AnchorRead(cc, None, AT, None, None, None, None, None, False, None,
                          note=f"No inflation target configured for {cc}.")

    df = signals if signals is not None else load_inflation_signals(cc)
    if as_of is not None and not df.empty:
        df = df[df["as_of"] <= pd.Timestamp(as_of)]

    target = float(spec["target_pct"])
    tol = float(cfg["bands"]["tolerance_pp"])
    far = float(cfg["bands"]["far_pp"])

    # Pick the FRESHEST configured candidate, with config order as the
    # tie-break. Several countries' monthly CPI mirrors are dead (GB, KR, CN,
    # IN, MX, AU — documented in docs/Guidance/data_source_wishlist.md) and
    # strict config order would anchor the read to a print over a year old when
    # a live IMF annual bridge exists.
    candidates = _rank_candidates(df, spec)

    for _, _, concept, s in candidates[:1]:
        # Signals are stored as decimal fractions (0.0301 == 3.01%).
        infl_pct = float(s.iloc[-1]) * 100.0
        gap = infl_pct - target
        chg3 = None
        if len(s) >= 4:
            prev_gap = float(s.iloc[-4]) * 100.0 - target
            chg3 = gap - prev_gap
        label = ABOVE if gap > tol else (BELOW if gap < -tol else AT)
        stale_rows = df[(df["concept"] == concept) & (df["as_of"] == s.index[-1])]
        is_stale = bool(stale_rows["is_stale"].iloc[0]) if not stale_rows.empty else False
        ref = pd.Timestamp(as_of) if as_of else pd.Timestamp.today()
        age = int(round((ref - s.index[-1]).days / 30.44))
        return AnchorRead(
            country=cc,
            as_of=str(s.index[-1].date()),
            label=label,
            gap_pp=round(gap, 3),
            inflation_pct=round(infl_pct, 3),
            target_pct=target,
            gap_series=concept,
            gap_change_3m_pp=None if chg3 is None else round(chg3, 3),
            far_from_target=abs(gap) >= far,
            official_band_pp=spec.get("official_band_pp"),
            is_stale=is_stale,
            age_months=age,
            note=spec.get("note", ""),
        )

    return AnchorRead(cc, None, AT, None, None, target, None, None, False,
                      spec.get("official_band_pp"),
                      note=f"No usable inflation series for {cc} "
                           f"(tried {spec['gap_series']}).")


def basket_split_composition(country: str = "US", config: "dict | None" = None) -> dict:
    """How a country's inflation basket divides into impulse vs persistence.

    Ray 2026-10-03 Ruling 2: "inflation is a two-part machine" — a flexible-
    price impulse and a sticky persistence — to be combined ~30/70 and
    published side by side. This reports what the configured basket WEIGHTS
    actually imply, as opposed to what the two sub-indices read today, so a
    weight edit that breaks the ruling is visible.

    `has_both` is the one that matters. Ten of fourteen countries have **no
    persistence member at all** — their whole inflation basket is headline or
    annual CPI, which is flexible-price. For those the composite is, in Ray's
    own framing, a leading impulse index and not a current-state gauge, and it
    must not be presented as if it were the US's core-PCE-weighted read.
    """
    import yaml
    cfg = config or load_config()
    split = cfg["split"]
    imp_set, per_set = set(split["impulse_members"]), set(split["persistence_members"])
    path = (_CONFIG_PATH.parents[1] / "config" / "countries"
            / f"{country.lower()}_composites.yaml")
    if not path.exists():
        return {"country": country.upper(), "has_both": False, "members": {}}
    doc = yaml.safe_load(path.read_text()) or {}
    inds = (doc.get("inflation_score") or {}).get("indicators") or []
    imp_w = per_w = unc_w = 0.0
    members = {"impulse": [], "persistence": [], "unclassified": []}
    for ind in inds:
        w = float(ind.get("importance", 0.0)) * float(ind.get("base_share", 1.0))
        concept = str(ind["id"]).rsplit(".", 1)[-1]
        if concept in per_set:
            per_w += w; members["persistence"].append(concept)
        elif concept in imp_set:
            imp_w += w; members["impulse"].append(concept)
        else:
            unc_w += w; members["unclassified"].append(concept)
    total = imp_w + per_w
    return {
        "country": country.upper(),
        "impulse_weight": round(imp_w, 4),
        "persistence_weight": round(per_w, 4),
        "unclassified_weight": round(unc_w, 4),
        "persistence_share": round(per_w / total, 4) if total else None,
        "has_both": bool(imp_w > 0 and per_w > 0),
        "members": members,
    }


def impulse_persistence(
    country: str = "US",
    as_of: Optional[str] = None,
    config: Optional[dict] = None,
    signals: Optional[pd.DataFrame] = None,
) -> dict:
    """Ray's two-part machine: flexible-price impulse vs sticky persistence.

    Each sub-index is the equal-weighted mean of its members' Z-scores — the
    members already carry per-signal importance in the main composite, and
    re-applying it here would double-count. Returns None for a sub-index with
    fewer than `min_members` contributors rather than a misleading partial.
    """
    cfg = config or load_config()
    split = cfg["split"]
    cc = country.upper()
    df = signals if signals is not None else load_inflation_signals(cc)
    if as_of is not None and not df.empty:
        df = df[df["as_of"] <= pd.Timestamp(as_of)]

    def _subindex(members: list[str]) -> tuple[Optional[float], list[str]]:
        vals, used = [], []
        for concept in members:
            s = _series_for(df, concept, col="zscore")
            if s.empty or pd.isna(s.iloc[-1]):
                continue
            vals.append(float(s.iloc[-1]))
            used.append(concept)
        if len(vals) < int(split["min_members"]):
            return None, used
        return round(sum(vals) / len(vals), 4), used

    imp, imp_used = _subindex(split["impulse_members"])
    per, per_used = _subindex(split["persistence_members"])

    iw, pw = float(split["impulse_weight"]), float(split["persistence_weight"])
    if imp is not None and per is not None:
        blended = round(iw * imp + pw * per, 4)
    elif per is not None:
        blended = per
    elif imp is not None:
        blended = imp
    else:
        blended = None

    divergence = None
    if imp is not None and per is not None:
        divergence = round(imp - per, 4)

    return {
        "country": cc,
        "impulse": imp,
        "impulse_members": imp_used,
        "persistence": per,
        "persistence_members": per_used,
        "blended": blended,
        "weights": {"impulse": iw, "persistence": pw},
        "divergence": divergence,
        "reading": _divergence_reading(imp, per, divergence),
    }


def _divergence_reading(imp, per, divergence) -> str:
    """Plain-language read of impulse vs persistence.

    This is the question Ray says the split exists to answer: is this a passing
    relative-price shock, or is inflation becoming embedded?
    """
    if imp is None or per is None or divergence is None:
        return "insufficient data for an impulse-vs-persistence read"
    if divergence > 0.75:
        return ("Impulse running well ahead of persistence — consistent with a "
                "supply-side or commodity shock that has NOT yet embedded. "
                "Watch whether persistence follows.")
    if divergence < -0.75:
        return ("Persistence running ahead of impulse — the sticky component is "
                "hot while the flexible-price impulse has faded. This is the "
                "embedded-inflation shape.")
    return "Impulse and persistence broadly aligned — no divergence signal."


# ── Growth-side safeguards (Ray ruling 3) ────────────────────────────────────

def apply_threshold_floor(threshold: float, config: Optional[dict] = None) -> float:
    """Floor the dynamic growth threshold.

    Ray: "consider a modest cap (e.g., never let the effective threshold fall
    below 0.15 sigma) so you don't become overly sensitive during unusually calm
    periods." Without this, a long quiet stretch shrinks the volatility-scaled
    threshold until noise trips the chip.
    """
    cfg = config or load_config()
    floor = float(cfg["growth_safeguards"]["min_dynamic_threshold"])
    try:
        t = float(threshold)
    except (TypeError, ValueError):
        return floor
    if pd.isna(t):
        return floor
    return max(abs(t), floor)


def sustained(
    series: "pd.Series",
    threshold: float,
    direction: str = "above",
    config: Optional[dict] = None,
) -> bool:
    """Has the Z condition held for N consecutive months?

    Ray: "Require the Z-score to be above the threshold for at least two
    consecutive months... This reduces noise without sacrificing much lead
    time." Returns False when there is not yet enough history to judge — a
    condition that cannot be shown to have held is not treated as held.
    """
    cfg = config or load_config()
    n = int(cfg["growth_safeguards"]["sustained_months"])
    if n <= 1:
        s = series.dropna()
        if s.empty:
            return False
        last = float(s.iloc[-1])
        return last > threshold if direction == "above" else last < -abs(threshold)
    s = series.dropna()
    if len(s) < n:
        return False
    tail = s.iloc[-n:]
    if direction == "above":
        return bool((tail > threshold).all())
    return bool((tail < -abs(threshold)).all())


def full_read(country: str = "US", as_of: Optional[str] = None) -> dict:
    """Anchor + split in one call, for dashboards and the audit skill."""
    cfg = load_config()
    sig = load_inflation_signals(country.upper())
    anchor = anchor_read(country, as_of=as_of, config=cfg, signals=sig)
    split = impulse_persistence(country, as_of=as_of, config=cfg, signals=sig)
    return {
        "anchor": anchor,
        "split": split,
        "primary": f"{anchor.label} ({anchor.gap_pp:+.2f}pp)" if anchor.gap_pp is not None
                   else f"{anchor.label} (no data)",
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Anchored inflation read")
    ap.add_argument("--country", default="US")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--all", action="store_true", help="every configured country")
    a = ap.parse_args()

    ccs = list(load_config()["countries"]) if a.all else [a.country.upper()]
    for cc in ccs:
        r = full_read(cc, as_of=a.as_of)
        an, sp = r["anchor"], r["split"]
        print(f"\n=== {cc} @ {an.as_of} ===")
        print(f"  ANCHOR  {an.label:>13}  gap {an.gap_pp:+.2f}pp "
              f"({an.inflation_pct}% vs {an.target_pct}% target, via {an.gap_series})"
              if an.gap_pp is not None else f"  ANCHOR  {an.label} — {an.note}")
        print(f"  trend   gap 3m change {an.gap_change_3m_pp} pp -> {an.direction}")
        print(f"  split   impulse {sp['impulse']}  persistence {sp['persistence']}  "
              f"blended {sp['blended']}")
        print(f"  read    {sp['reading']}")
