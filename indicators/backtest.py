"""Phase G backtesting engine — point-in-time regime replay.

Stage G1: expanding-window ("point-in-time") Z-scores. The production display
pipeline Z-scores each signal against its FULL history, which means historical
Z-scores "know" future data (documented as deliberate for Phase 1 display).
Here every Z-score at month t uses only observations up to t-1 (expanding
window, shift(1)), eliminating statistical look-ahead.

Stage G2: named-scenario scoring + fixed-vs-dynamic threshold comparison.
Each scenario declares an expected regime chip for one dimension over a dated
window; we score what fraction of months the point-in-time classifier produced
the strict expected label, an acceptable label, or the wrong-direction label —
under BOTH the fixed default thresholds and the dynamic (Ray Dalio) algorithm.

Stage G3 (NOT implemented — future): ALFRED vintage replay (data as it was
known at the time, eliminating data-REVISION look-ahead) and asset-outcome
predictive tests (e.g. does rate_expectations improve prediction of bond/
credit outcomes — Ray's suggested validation for that signal).

Honest simplifications in G1 (documented, revisit if results look off):
  * The momentum weight tilt and observation-age decay used by the production
    composites engine are NOT applied — the PIT composite is a plain
    (renormalized) weighted mean of PIT Z-scores. Both modifiers are bounded
    multipliers on weights; they shift magnitudes, rarely signs.
  * Data is final-revised (G3 fixes this).

Usage:
    python -m indicators.backtest              # run US backtest, write report
    python -m indicators.backtest --country US
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from indicators.composites import load_composites_config, normalized_nominal_weights
from indicators.normalize import ZSCORE_CAP_SIGMA
from indicators.pipeline import load_bindings, _CONFIG_DIR
from store.store import DB_PATH

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[1]
_REPORT_DIR = _PROJECT_ROOT / "docs" / "backtests"

# Point-in-time warm-up: months of prior history required before a PIT Z-score
# is emitted. TUNABLE — 36 keeps early-1980s noise out of the scored era.
PIT_MIN_PERIODS = 36

# Minimum contributing signals for a PIT composite value (else NaN).
PIT_MIN_SIGNALS = 3

# Per-frequency forward-fill caps for the monthly panel — mirrors
# config/composites_policy.yaml per_frequency_ffill_limit.
_FREQ_FFILL_LIMIT = {"D": 1, "W": 2, "M": 3, "Q": 9, "A": 15}
_DEFAULT_FFILL_LIMIT = 13


# ── Scenarios ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Scenario:
    """A named historical window with an expected regime chip on one dimension.

    strict     — the single label the classifier "should" show.
    acceptable — labels that don't count as a miss (the momentum gate makes
                 chips flicker to Transition during plateaus by design).
    The wrong-direction label (the opposite pole) is derived automatically.
    """
    name: str
    start: str
    end: str
    dim: str                      # "growth" | "inflation"
    strict: str
    acceptable: frozenset = field(default_factory=frozenset)
    note: str = ""

    @property
    def wrong(self) -> str:
        opposites = {"Growth": "Retraction", "Retraction": "Growth",
                     "Inflation": "Disinflation", "Disinflation": "Inflation"}
        return opposites[self.strict]


# History starts 1980-81 + 36mo PIT warm-up → scoreable era ≈ 1984 onward,
# so no 1970s scenario (would need pre-1970 data for the warm-up anyway).
US_SCENARIOS: list[Scenario] = [
    Scenario("1990-91 recession", "1990-08-01", "1991-03-31", "growth",
             "Retraction", frozenset({"Retraction", "Transition"}),
             "Gulf-war oil shock recession"),
    Scenario("Late-90s boom", "1996-01-01", "1999-12-31", "growth",
             "Growth", frozenset({"Growth", "Transition"}),
             "Dot-com era expansion; plateaus flicker to Transition by design"),
    Scenario("2001 dot-com bust", "2001-04-01", "2001-11-30", "growth",
             "Retraction", frozenset({"Retraction", "Transition"}),
             "Shallow recession — hard test, labor held up"),
    Scenario("2008 GFC bust", "2008-10-01", "2009-06-30", "growth",
             "Retraction", frozenset({"Retraction", "Transition"}),
             "Textbook credit-driven bust"),
    Scenario("2009 disinflation", "2008-12-01", "2009-09-30", "inflation",
             "Disinflation", frozenset({"Disinflation", "Transition"}),
             "Post-GFC price collapse"),
    Scenario("2020 COVID crash", "2020-03-01", "2020-08-31", "growth",
             "Retraction", frozenset({"Retraction", "Transition"}),
             "Fastest contraction on record"),
    Scenario("2021-22 inflation surge", "2021-09-01", "2022-09-30", "inflation",
             "Inflation", frozenset({"Inflation", "Transition"}),
             "The defining recent inflation episode"),
    Scenario("2023 disinflation", "2023-03-01", "2024-03-31", "inflation",
             "Disinflation", frozenset({"Disinflation", "Transition"}),
             "Cooling from the 2022 peak — gradual, so Transition-heavy is fine"),
]


# ── Point-in-time computation ────────────────────────────────────────────────

def pit_zscore(series: pd.Series, min_periods: int = PIT_MIN_PERIODS) -> pd.Series:
    """Expanding-window Z-score using only PRIOR observations (shift(1)).

    The value at time t is scored against the mean/std of observations
    strictly before t — no look-ahead. Clipped to ±ZSCORE_CAP_SIGMA like the
    production normalizer.
    """
    prior = series.shift(1)
    mu = prior.expanding(min_periods=min_periods).mean()
    sd = prior.expanding(min_periods=min_periods).std()
    z = (series - mu) / sd.replace(0, np.nan)
    return z.clip(-ZSCORE_CAP_SIGMA, ZSCORE_CAP_SIGMA)


def load_monthly_values(
    conn, signal_ids: list[str], freq_map: dict[str, str]
) -> pd.DataFrame:
    """Month-end panel of raw signal VALUES with per-frequency ffill caps."""
    placeholders = ", ".join(["?"] * len(signal_ids))
    df = conn.execute(
        f"SELECT id, as_of, value FROM signals "
        f"WHERE id IN ({placeholders}) AND value IS NOT NULL ORDER BY as_of",
        signal_ids,
    ).df()
    if df.empty:
        return pd.DataFrame()
    df["as_of"] = pd.to_datetime(df["as_of"])
    wide = df.pivot_table(index="as_of", columns="id", values="value", aggfunc="last")
    wide = wide.resample("ME").last()
    for col in wide.columns:
        limit = _FREQ_FFILL_LIMIT.get(freq_map.get(col, ""), _DEFAULT_FFILL_LIMIT)
        wide[col] = wide[col].ffill(limit=limit)
    return wide


def pit_composite(
    z_wide: pd.DataFrame,
    indicators_cfg: list[dict],
    prefix: str,
    min_signals: int = PIT_MIN_SIGNALS,
) -> pd.Series:
    """Renormalized weighted mean of PIT Z-scores for one force basket."""
    weights = normalized_nominal_weights(indicators_cfg)
    cols, w, signs = [], [], []
    for ind in indicators_cfg:
        col = f"{prefix}.{ind['id']}"
        if col not in z_wide.columns:
            continue
        cols.append(col)
        w.append(weights[ind["id"]])
        signs.append(-1.0 if ind.get("invert", False) else 1.0)
    if not cols:
        return pd.Series(dtype=float)
    z = z_wide[cols]
    w_arr = np.array(w) * np.array(signs)
    mask = z.notna()
    weighted = (z.fillna(0.0) * w_arr).sum(axis=1)
    active_w = (mask * np.abs(np.array(w))).sum(axis=1)
    score = weighted / active_w.replace(0, np.nan)
    score[mask.sum(axis=1) < min_signals] = np.nan
    return score


def compute_pit_scores(conn, country: str = "US") -> pd.DataFrame:
    """Monthly point-in-time growth/inflation/credit composite scores."""
    cfg = load_composites_config(country)
    prefix = country.lower()
    baskets = {
        "growth_score": cfg["growth_score"]["indicators"],
        "inflation_score": cfg["inflation_score"]["indicators"],
        "credit_score": cfg.get("credit_score", {}).get("indicators", []),
    }
    all_ids = sorted({
        f"{prefix}.{ind['id']}"
        for inds in baskets.values() for ind in inds
    })
    bindings_path = (
        _CONFIG_DIR / "us_bindings.yaml" if country.upper() == "US"
        else _CONFIG_DIR / "countries" / f"{prefix}_bindings.yaml"
    )
    freq_map = {f"{prefix}.{b.id}": b.frequency for b in load_bindings(bindings_path)}

    values = load_monthly_values(conn, all_ids, freq_map)
    if values.empty:
        raise ValueError(f"No signal values found for {country} — run the pipeline first.")
    z_wide = values.apply(pit_zscore)

    out = pd.DataFrame(index=values.index)
    for name, inds in baskets.items():
        if inds:
            out[name] = pit_composite(z_wide, inds, prefix)
    return out


# ── Classification + scoring ─────────────────────────────────────────────────

def classify_history(scores: pd.DataFrame, dynamic: bool) -> pd.DataFrame:
    """Per-month Growth/Inflation chips under fixed or dynamic thresholds.

    Imports the production classifier so there is exactly one implementation
    of the classification rule and the threshold algorithm.
    """
    from dashboard.charting import (
        _DEFAULT_THRESHOLDS, _classify_regime, compute_dynamic_thresholds,
    )

    base = dict(_DEFAULT_THRESHOLDS)
    dyn_df = compute_dynamic_thresholds(
        scores, base_gz=base["gz"], base_iz=base["iz"]
    ) if dynamic else None

    g_delta = scores["growth_score"].diff()
    i_delta = scores["inflation_score"].diff()
    rows = []
    for pos, ts in enumerate(scores.index):
        t = dict(base)
        if dyn_df is not None:
            t["gz"] = float(dyn_df["dyn_gz"].iloc[pos])
            t["iz"] = float(dyn_df["dyn_iz"].iloc[pos])
        g_chip, i_chip = _classify_regime(
            scores["growth_score"].iloc[pos], scores["inflation_score"].iloc[pos],
            g_delta.iloc[pos], i_delta.iloc[pos], t,
        )
        rows.append({"as_of": ts, "growth_chip": g_chip, "inflation_chip": i_chip})
    return pd.DataFrame(rows).set_index("as_of")


def score_scenario(chips: pd.DataFrame, scenario: Scenario) -> dict:
    col = f"{scenario.dim}_chip"
    window = chips.loc[scenario.start: scenario.end, col].dropna()
    n = len(window)
    if n == 0:
        return {"scenario": scenario.name, "months": 0}
    counts = window.value_counts().to_dict()
    return {
        "scenario": scenario.name,
        "dim": scenario.dim,
        "months": n,
        "strict_hit": round(float((window == scenario.strict).mean()), 3),
        "acceptable_hit": round(float(window.isin(scenario.acceptable).mean()), 3),
        "wrong_direction": round(float((window == scenario.wrong).mean()), 3),
        "labels": counts,
    }


def run_backtest(country: str = "US", db_path: Path | None = None) -> dict:
    conn = duckdb.connect(str(db_path or DB_PATH), read_only=True)
    try:
        scores = compute_pit_scores(conn, country)
    finally:
        conn.close()

    results = {"country": country, "scores": scores, "modes": {}}
    for mode, dynamic in (("fixed", False), ("dynamic", True)):
        chips = classify_history(scores, dynamic=dynamic)
        results["modes"][mode] = {
            "chips": chips,
            "scenarios": [score_scenario(chips, s) for s in US_SCENARIOS],
        }
    return results


# ── Report ───────────────────────────────────────────────────────────────────

def render_report(results: dict) -> str:
    scores = results["scores"]
    lines = [
        f"# Point-in-time regime backtest — {results['country']}",
        "",
        "Phase G (stages G1+G2) of docs/Guidance/ray_framework_roadmap.md.",
        "All Z-scores are expanding-window, shift(1) — the classifier at month t",
        f"uses only data available before t (warm-up: {PIT_MIN_PERIODS} months).",
        "",
        "**Not covered here (stage G3, future):** data-revision look-ahead",
        "(this uses final-revised data, not ALFRED vintages) and asset-outcome",
        "predictive tests. The production momentum weight-tilt and age-decay",
        "modifiers are not applied to the PIT composite (bounded weight",
        "multipliers; they shift magnitudes, rarely signs).",
        "",
        f"Scored era: {scores.dropna(how='all').index.min():%Y-%m} → "
        f"{scores.index.max():%Y-%m} ({len(scores)} months).",
        "",
        "Reading the numbers: `strict` = months showing exactly the expected",
        "chip; `acceptable` also counts Transition (the momentum gate parks",
        "plateau months there by design); `wrong` = months showing the",
        "OPPOSITE pole — the number that must stay near zero.",
        "",
    ]
    for mode in ("fixed", "dynamic"):
        rows = results["modes"][mode]["scenarios"]
        lines += [f"## {mode.capitalize()} thresholds", "",
                  "| Scenario | Dim | Months | Strict | Acceptable | Wrong dir | Labels |",
                  "|---|---|---|---|---|---|---|"]
        for r in rows:
            if r.get("months", 0) == 0:
                lines.append(f"| {r['scenario']} | — | 0 | — | — | — | no data |")
                continue
            labels = ", ".join(f"{k} {v}" for k, v in sorted(r["labels"].items()))
            lines.append(
                f"| {r['scenario']} | {r['dim']} | {r['months']} "
                f"| {r['strict_hit']:.0%} | {r['acceptable_hit']:.0%} "
                f"| {r['wrong_direction']:.0%} | {labels} |")
        lines.append("")

    # Head-to-head deltas
    lines += ["## Dynamic vs. fixed — head to head", "",
              "| Scenario | Δ strict | Δ acceptable | Δ wrong (lower is better) |",
              "|---|---|---|---|"]
    fixed = {r["scenario"]: r for r in results["modes"]["fixed"]["scenarios"]}
    for r in results["modes"]["dynamic"]["scenarios"]:
        f = fixed.get(r["scenario"], {})
        if r.get("months", 0) == 0 or f.get("months", 0) == 0:
            continue
        lines.append(
            f"| {r['scenario']} "
            f"| {r['strict_hit'] - f['strict_hit']:+.0%} "
            f"| {r['acceptable_hit'] - f['acceptable_hit']:+.0%} "
            f"| {r['wrong_direction'] - f['wrong_direction']:+.0%} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", default="US")
    args = parser.parse_args()

    results = run_backtest(args.country)
    report = render_report(results)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = _REPORT_DIR / f"pit_regime_backtest_{args.country.lower()}.md"
    out.write_text(report)
    print(report)
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    main()
