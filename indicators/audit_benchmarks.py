"""External benchmark panel for the independent chip audit (Dalio audit skill).

Purpose
-------
The Growth / Inflation chips on this dashboard are *relative* reads: "the force
composite sits more than `gz`/`iz` sigma above its own rolling norm AND is
rising". To audit them honestly we need outside measures that are
(a) constructed independently of our weighting scheme, and (b) comparable
either directly (standardised, mean-zero composites) or on the level axis
(growth/inflation rates, nowcasts, regime flags).

NON-NEGOTIABLE — VALIDATION ONLY
--------------------------------
No series in this module may EVER be added to `config/us_bindings.yaml` or any
`config/countries/{cc}_composites.yaml` basket. The moment a benchmark feeds the
composite it is auditing, the audit becomes circular and worthless. This module
only ever READS the signals DB (read_only=True); it never writes to it.

Honest caveat on "independence"
-------------------------------
These benchmarks are *independently constructed*, not *input-independent*.
CFNAI is built from 85 series that include payrolls, industrial production,
retail sales and capacity utilisation — four of our own growth basket members.
Median/trimmed/sticky CPI are alternative aggregations of the same BLS price
quotes behind our CPI signals. So a high correlation is partly mechanical and
proves little. What the comparison genuinely tests is our *aggregation,
normalisation and threshold* choices, and the informative output is therefore
DISAGREEMENT and LEAD/LAG, not the headline correlation. Every consumer of this
module must say so.

All FRED IDs below were endpoint-verified live on 2026-10-03 (project rule #4:
never invent or assume a series ID). Two candidates were rejected as dead:
`USALOLITONOSTSAM` (OECD US CLI, ends 2024-01) and `USSLIND` (ends 2020-02).
`ADSBCI` (Philly Fed ADS) does not exist on FRED at all.

Usage
-----
    python -m indicators.audit_benchmarks --country US
    python -m indicators.audit_benchmarks --country US --as-of 2022-06-30
    python -m indicators.audit_benchmarks --country US --json pack.json --refresh
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import duckdb
import numpy as np
import pandas as pd

from indicators.loader import fetch_series
from store.store import DB_PATH

logger = logging.getLogger(__name__)

# Canonical display windows (Ray audit ruling 2026-07-06, Q1a).
CANONICAL_GROWTH_WINDOW = 48
CANONICAL_INFLATION_WINDOW = 90

# Lead/lag search range, in months, for the cross-correlation scan.
MAX_LAG_MONTHS = 6

# A benchmark is called Above/Below its own norm beyond this many sigma when it
# publishes no thresholds of its own. Mirrors the chip's own default gz/iz so
# the two sides of the comparison are graded on the same yardstick.
DEFAULT_STATE_SIGMA = 0.5

# Minimum consecutive months of opposite-signed, materially-sized readings
# before a stretch counts as a disagreement episode worth investigating.
EPISODE_MIN_MONTHS = 3


@dataclass(frozen=True)
class Benchmark:
    """One external measure used to cross-examine a chip.

    kind:
      relative  — already standardised / mean-zero; directly comparable to our Z
      rate      — a growth or inflation RATE (level axis, not relative)
      flag      — a recession/regime marker (binary or probability)
      expect    — a measure of expectations rather than realised outcomes
    orientation: +1 if higher means more growth / more inflation, -1 if inverted.
    thresholds: published cut-offs, if the publisher defines any, as
      {"above": x, "below": y} in the series' own units.
    smooth_months: rolling mean applied before comparison (monthly annualised
      rates are far too noisy to compare against a smoothed composite raw).
    units: human-readable units. REQUIRED in practice — a blinded reviewer spent
      real effort trying to work out whether RECPROUSM156N's 0.62 was 0.62% or a
      62% probability, which would have inverted its entire growth read. State the
      scale explicitly rather than making the reader infer it.
    """

    key: str
    fred_id: str
    title: str
    axis: str
    kind: str
    frequency: str
    independence: str
    orientation: int = 1
    thresholds: Optional[dict] = None
    smooth_months: int = 0
    units: str = ""
    note: str = ""


# ── The panel ────────────────────────────────────────────────────────────────
# Growth. CFNAI-MA3 is the primary benchmark: it is the closest external analogue
# to our growth chip — a standardised, mean-zero composite WITH publisher-defined
# thresholds, so it tests our threshold calibration directly.
GROWTH_BENCHMARKS: list[Benchmark] = [
    Benchmark(
        "cfnai_ma3", "CFNAIMA3", "Chicago Fed National Activity Index, 3-mo MA",
        "growth", "relative", "m",
        "85 input series; OVERLAPS our payrolls / industrial_prod / retail_sales / "
        "capacity_util. Independent weighting (principal component), not independent data.",
        thresholds={"below": -0.70, "above": 0.70},
        note="Publisher reads MA3 < -0.70 as recession onset and > +0.70 as "
             "above-trend growth with building inflation pressure. The single "
             "best external test of our gz threshold.",
        units="index, 0 = trend growth"
    ),
    Benchmark(
        "cfnai", "CFNAI", "Chicago Fed National Activity Index (monthly)",
        "growth", "relative", "m",
        "Same inputs as CFNAI-MA3, unsmoothed.",
        note="Noisier than MA3; useful only for turning-point timing.",
        units="index, 0 = trend growth"
    ),
    Benchmark(
        "cfnai_diffusion", "CFNAIDIFF", "CFNAI Diffusion Index",
        "growth", "relative", "m",
        "Breadth of the same 85 inputs.",
        note="Breadth, not magnitude — the external analogue of our Chip "
             "Direction Agreement metric rather than of the score itself.",
        units="index, -1 to +1 (share of inputs improving)"
    ),
    Benchmark(
        "wei", "WEI", "Weekly Economic Index (Lewis-Mertens-Stock)",
        "growth", "rate", "w",
        "Retail sales, claims, steel output, fuel sales, electricity — only "
        "partially overlapping our basket; the most input-independent growth measure here.",
        smooth_months=0,
        note="Scaled to 4-quarter GDP growth. Weekly, so it leads monthly data.",
        units="percent, scaled to 4-quarter GDP growth"
    ),
    Benchmark(
        "gdpnow", "GDPNOW", "Atlanta Fed GDPNow (current-quarter real GDP)",
        "growth", "rate", "q",
        "Nowcast of the GDP target itself; shares source data, independent model.",
        note="LEVEL axis. Answers 'is the economy growing?', NOT 'is it above "
             "its own norm?'. Do not grade the chip against this alone.",
        units="percent, annualised quarterly rate"
    ),
    Benchmark(
        "stl_nowcast", "STLENI", "St. Louis Fed Economic News Index: Real GDP Nowcast",
        "growth", "rate", "q",
        "Second independent nowcasting model on overlapping source data.",
        note="LEVEL axis. Cross-check on GDPNow.",
        units="percent, annualised quarterly rate"
    ),
    Benchmark(
        "real_gdp_growth", "A191RL1Q225SBEA", "Real GDP, % change at annual rate",
        "growth", "rate", "q",
        "The realised outcome our growth force is a proxy for.",
        note="LEVEL axis, and revised. The ground truth for 'was it growing', "
             "published with a long lag.",
        units="percent, annualised quarterly rate"
    ),
    Benchmark(
        "sahm", "SAHMREALTIME", "Real-time Sahm Rule Recession Indicator",
        "growth", "flag", "m",
        "Derived from the unemployment rate — OVERLAPS growth.unemployment.",
        orientation=-1,
        thresholds={"above": 0.50},
        note="Rule fires at >= 0.50. Inverted: higher = weaker growth.",
        units="percentage points (unemployment gap); fires at >= 0.50"
    ),
    Benchmark(
        "recession_prob", "RECPROUSM156N", "Smoothed US Recession Probabilities",
        "growth", "flag", "m",
        "Chauvet dynamic-factor model on 4 coincident series; overlapping inputs.",
        orientation=-1,
        thresholds={"above": 50.0},
        note="Percent. Inverted. Conventionally read as a recession call above 50%.",
        units="PERCENT, 0-100 (so 0.62 means 0.62%, not 62%)"
    ),
    Benchmark(
        "nber_recession", "USREC", "NBER-based Recession Indicator",
        "growth", "flag", "m",
        "NBER committee judgement — genuinely independent of any of our data, "
        "but announced with a lag of many months.",
        orientation=-1,
        thresholds={"above": 0.5},
        note="THE historical arbiter for growth turning points. Use for "
             "lead/lag scoring in historical mode; useless for the current month "
             "because the dating is retrospective.",
        units="binary, 1 = NBER recession month"
    ),
]

# Inflation. No external measure here is standardised, so all are graded on the
# level axis plus a rolling-Z of their own history.
INFLATION_BENCHMARKS: list[Benchmark] = [
    Benchmark(
        "median_cpi", "MEDCPIM158SFRBCLE", "Median CPI (Cleveland Fed)",
        "inflation", "rate", "m",
        "Alternative aggregation of the same BLS price quotes as inflation.cpi_core.",
        smooth_months=12,
        note="Monthly annualised rate — smoothed 12m here to be comparable with "
             "our YoY-based signals. Robust central-tendency measure.",
        units="percent, monthly annualised rate (smoothed 12m here)"
    ),
    Benchmark(
        "trimmed_cpi", "TRMMEANCPIM158SFRBCLE", "16% Trimmed-Mean CPI (Cleveland Fed)",
        "inflation", "rate", "m",
        "Alternative aggregation of the same BLS price quotes.",
        smooth_months=12,
        units="percent, monthly annualised rate (smoothed 12m here)"
    ),
    Benchmark(
        "trimmed_pce", "PCETRIM12M159SFRBDAL", "Trimmed Mean PCE Inflation Rate (Dallas Fed)",
        "inflation", "rate", "m",
        "Alternative aggregation of the same BEA PCE basket as inflation.pce_core.",
        note="Already a 12-month rate. The Fed's own preferred underlying-trend measure.",
        units="percent, 12-month rate"
    ),
    Benchmark(
        "sticky_core_cpi", "CORESTICKM159SFRBATL", "Sticky Price Core CPI (Atlanta Fed)",
        "inflation", "rate", "m",
        "Same price quotes, partitioned by price-change frequency.",
        smooth_months=12,
        note="Sticky component proxies inflation PERSISTENCE — the thing the "
             "Disinflation chip is really claiming to detect.",
        units="percent, monthly annualised rate (smoothed 12m here)"
    ),
    # REJECTED — Cleveland Fed EXPINF1YR is already ingested as the bound signal
    # `market.exp_infl_1y` in config/us_bindings.yaml. Even though it does not sit
    # in the inflation_score basket, a series already inside our own system cannot
    # be presented as independent corroboration of it. Caught by
    # tests/test_audit_benchmarks.py::test_no_benchmark_is_also_an_input_signal.
    Benchmark(
        "mich_1y", "MICH", "U. Michigan 1-Year Inflation Expectation",
        "inflation", "expect", "m",
        "Household survey — genuinely independent data, but a poor forecaster "
        "and heavily level-biased.",
        units="percent, expected 12-month inflation"
    ),
]

ALL_BENCHMARKS: list[Benchmark] = GROWTH_BENCHMARKS + INFLATION_BENCHMARKS


def benchmarks_for(axis: str) -> list[Benchmark]:
    if axis == "growth":
        return GROWTH_BENCHMARKS
    if axis == "inflation":
        return INFLATION_BENCHMARKS
    raise ValueError(f"axis must be 'growth' or 'inflation', got {axis!r}")


# ── Panel assembly ───────────────────────────────────────────────────────────

def _to_monthly(series: pd.Series, frequency: str) -> pd.Series:
    """Month-end resample. Weekly/daily are averaged (noise reduction);
    monthly take the last print; quarterly are held forward within the quarter."""
    s = series.dropna()
    s.index = pd.to_datetime(s.index)
    if frequency in ("w", "d"):
        out = s.resample("ME").mean()
    else:
        out = s.resample("ME").last()
    if frequency == "q":
        out = out.ffill(limit=2)
    return out


def load_benchmark_panel(axis: str, force_refresh: bool = False) -> pd.DataFrame:
    """Month-end panel of every benchmark on `axis`, smoothing applied.

    Missing/failed fetches are logged and dropped — a benchmark that cannot be
    retrieved must never silently become a zero.
    """
    cols: dict[str, pd.Series] = {}
    for b in benchmarks_for(axis):
        raw = fetch_series(b.fred_id, b.frequency, force_refresh=force_refresh)
        if raw is None or raw.empty:
            logger.warning("[audit] benchmark unavailable: %s (%s)", b.key, b.fred_id)
            continue
        s = _to_monthly(raw, b.frequency)
        if b.smooth_months > 1:
            s = s.rolling(b.smooth_months, min_periods=max(2, b.smooth_months // 2)).mean()
        cols[b.key] = s
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).sort_index()


# ── Our side of the comparison ───────────────────────────────────────────────

def load_composite_history(country: str = "US") -> pd.DataFrame:
    """Read-only pull of the composites table. Never writes — the DB is
    single-writer and the dashboard may hold it."""
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = conn.execute(
            "SELECT * FROM composites WHERE country = ? ORDER BY as_of", [country]
        ).df()
    finally:
        conn.close()
    if not df.empty:
        df["as_of"] = pd.to_datetime(df["as_of"])
    return df


def _window_column(hist: pd.DataFrame, axis: str, window: Optional[int]) -> str:
    """Resolve the score column the dashboard would display, with the same
    fallback-to-full-history rule as command_center."""
    base = "growth_score" if axis == "growth" else "inflation_score"
    if not window:
        return base
    col = f"{base}_{window}m"
    if col in hist.columns and hist[col].notna().any():
        return col
    return base


def chip_state(
    country: str = "US",
    as_of: Optional[str] = None,
    growth_window: int = CANONICAL_GROWTH_WINDOW,
    inflation_window: int = CANONICAL_INFLATION_WINDOW,
    thresholds: Optional[dict] = None,
) -> dict:
    """Reproduce the dashboard's live chips EXACTLY, using production code.

    Imports `_classify_regime` / `compute_dynamic_thresholds` from
    dashboard.charting rather than reimplementing them, so this can never drift
    from what a user actually sees. Mirrors command_center's window resolution,
    latest/delta semantics and dynamic-threshold wiring.
    """
    from dashboard.charting import (  # lazy: charting is a heavy Dash module
        _DEFAULT_THRESHOLDS, _classify_regime, compute_dynamic_thresholds,
    )

    hist = load_composite_history(country)
    if hist.empty:
        raise RuntimeError(f"No composite rows for {country} — run the pipeline.")
    if as_of:
        hist = hist[hist["as_of"] <= pd.Timestamp(as_of)]
        if hist.empty:
            raise RuntimeError(f"No composite rows for {country} at or before {as_of}.")

    g_col = _window_column(hist, "growth", growth_window)
    i_col = _window_column(hist, "inflation", inflation_window)

    def _latest(col: str) -> Optional[float]:
        s = hist[col].dropna()
        return float(s.iloc[-1]) if not s.empty else None

    def _delta(col: str) -> Optional[float]:
        s = hist[col].dropna()
        return float(s.iloc[-1] - s.iloc[-2]) if len(s) >= 2 else None

    g, i = _latest(g_col), _latest(i_col)
    g_d, i_d = _delta(g_col), _delta(i_col)

    t = dict(thresholds or _DEFAULT_THRESHOLDS)
    dyn_cols = ["as_of", g_col, i_col] + (["credit_score"] if "credit_score" in hist.columns else [])
    dyn_input = hist[dyn_cols].rename(columns={g_col: "growth_score", i_col: "inflation_score"})
    dyn_df = compute_dynamic_thresholds(
        dyn_input, base_gz=float(t.get("gz", 0.5)), base_iz=float(t.get("iz", 0.5))
    )
    dynamic_on = bool(t.get("dynamic", False))
    if dynamic_on and not dyn_df.empty:
        t["gz"] = float(dyn_df["dyn_gz"].iloc[-1])
        t["iz"] = float(dyn_df["dyn_iz"].iloc[-1])
    g_chip, i_chip = _classify_regime(g, i, g_d, i_d, t)

    return {
        "country": country,
        "as_of": str(pd.Timestamp(hist["as_of"].iloc[-1]).date()),
        "growth_chip": g_chip,
        "inflation_chip": i_chip,
        "growth_score": g,
        "inflation_score": i,
        "growth_delta": g_d,
        "inflation_delta": i_d,
        "growth_momentum": _latest("growth_momentum") if "growth_momentum" in hist.columns else None,
        "inflation_momentum": _latest("inflation_momentum") if "inflation_momentum" in hist.columns else None,
        "score_columns": {"growth": g_col, "inflation": i_col},
        "windows": {"growth": growth_window, "inflation": inflation_window},
        "thresholds_in_force": {"gz": t.get("gz"), "iz": t.get("iz"),
                                "gm": t.get("gm"), "im": t.get("im"),
                                "dynamic": dynamic_on},
        "divergence_flag": bool(dyn_df["divergence_flag"].iloc[-1]) if not dyn_df.empty else False,
        "history": hist[["as_of", g_col, i_col]].rename(
            columns={g_col: "growth", i_col: "inflation"}
        ),
    }


# ── Comparison engine ────────────────────────────────────────────────────────

def rolling_z(series: pd.Series, window: int) -> pd.Series:
    """Rolling-window Z-score, matching how the composite's own windowed score
    is framed. min_periods is half the window so early history is not dropped
    wholesale."""
    mu = series.rolling(window, min_periods=max(12, window // 2)).mean()
    sd = series.rolling(window, min_periods=max(12, window // 2)).std()
    return (series - mu) / sd.replace(0, np.nan)


def best_lag(ours: pd.Series, theirs: pd.Series, max_lag: int = MAX_LAG_MONTHS) -> dict:
    """Scan lead/lag alignments and return the best Spearman fit.

    Convention: `ours.shift(k)` moves our readings LATER in time, so a positive
    best_lag means our composite LEADS the benchmark by that many months
    (shifting us later improved the match, i.e. we moved first).
    """
    joined = pd.concat([ours.rename("o"), theirs.rename("t")], axis=1).dropna()
    if len(joined) < 24:
        return {"best_lag": None, "corr_at_best": None, "n": int(len(joined))}
    scores = {}
    for k in range(-max_lag, max_lag + 1):
        pair = pd.concat([joined["o"].shift(k), joined["t"]], axis=1).dropna()
        if len(pair) < 24:
            continue
        c = pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman")
        if pd.notna(c):
            scores[k] = float(c)
    if not scores:
        return {"best_lag": None, "corr_at_best": None, "n": int(len(joined))}
    k_best = max(scores, key=lambda k: abs(scores[k]))
    return {"best_lag": int(k_best), "corr_at_best": round(scores[k_best], 3),
            "corr_at_zero": round(scores.get(0, float("nan")), 3) if 0 in scores else None,
            "n": int(len(joined))}


def _benchmark_state(b: Benchmark, raw: Optional[float], z: Optional[float]) -> tuple[str, str]:
    """Classify a benchmark as Above / Neutral / Below its own norm.

    Publisher thresholds win where they exist (that is the whole point of
    including CFNAI-MA3 and the recession flags); otherwise fall back to the
    same +/-0.5 sigma yardstick the chip uses.
    """
    if b.thresholds and raw is not None:
        hi = b.thresholds.get("above")
        lo = b.thresholds.get("below")
        basis = f"publisher thresholds {b.thresholds}"
        if hi is not None and raw >= hi:
            return ("Below" if b.orientation < 0 else "Above"), basis
        if lo is not None and raw <= lo:
            return ("Above" if b.orientation < 0 else "Below"), basis
        if hi is not None and lo is None:
            return "Neutral", basis
        if hi is not None and lo is not None:
            return "Neutral", basis
    if z is None or pd.isna(z):
        return "Unknown", "insufficient history for a rolling Z"
    basis = f"rolling Z vs +/-{DEFAULT_STATE_SIGMA} sigma"
    zz = z * b.orientation
    if zz >= DEFAULT_STATE_SIGMA:
        return "Above", basis
    if zz <= -DEFAULT_STATE_SIGMA:
        return "Below", basis
    return "Neutral", basis


_CHIP_TO_STATE = {
    "Growth": "Above", "Retraction": "Below", "Transition": "Neutral",
    "Inflation": "Above", "Disinflation": "Below",
}


def _verdict(chip: str, bench_state: str) -> str:
    """AGREE / PARTIAL / CONTRADICT / UNKNOWN on a fixed grid — no judgement calls."""
    if bench_state == "Unknown":
        return "UNKNOWN"
    ours = _CHIP_TO_STATE.get(chip, "Neutral")
    if ours == bench_state:
        return "AGREE"
    if "Neutral" in (ours, bench_state):
        return "PARTIAL"
    return "CONTRADICT"


def disagreement_episodes(
    ours_z: pd.Series, theirs_z: pd.Series, orientation: int = 1,
    min_months: int = EPISODE_MIN_MONTHS, sigma: float = DEFAULT_STATE_SIGMA,
) -> list[dict]:
    """Runs of >= min_months where both sides are materially sized and point
    opposite ways. These are the months worth a human explanation."""
    joined = pd.concat([ours_z.rename("o"), (theirs_z * orientation).rename("t")],
                       axis=1).dropna()
    if joined.empty:
        return []
    clash = ((joined["o"].abs() >= sigma) & (joined["t"].abs() >= sigma)
             & (np.sign(joined["o"]) != np.sign(joined["t"])))
    episodes, run = [], []
    for ts, flag in clash.items():
        if flag:
            run.append(ts)
            continue
        if len(run) >= min_months:
            episodes.append(run)
        run = []
    if len(run) >= min_months:
        episodes.append(run)
    return [
        {"start": str(r[0].date()), "end": str(r[-1].date()), "months": len(r),
         "our_z_mean": round(float(joined.loc[r, "o"].mean()), 2),
         "benchmark_z_mean": round(float(joined.loc[r, "t"].mean()), 2)}
        for r in episodes
    ]


def compare_axis(
    axis: str,
    chip: dict,
    panel: pd.DataFrame,
    window: Optional[int] = None,
    as_of: Optional[str] = None,
) -> dict:
    """Full numeric cross-examination of one chip against its benchmark panel."""
    window = window or (CANONICAL_GROWTH_WINDOW if axis == "growth"
                        else CANONICAL_INFLATION_WINDOW)
    ours = chip["history"].set_index("as_of")[axis].dropna()
    ours.index = pd.to_datetime(ours.index)
    ours = ours.resample("ME").last()
    if as_of:
        cutoff = pd.Timestamp(as_of)
        ours = ours[ours.index <= cutoff]
        panel = panel[panel.index <= cutoff]

    chip_label = chip["growth_chip"] if axis == "growth" else chip["inflation_chip"]
    rows = []
    for b in benchmarks_for(axis):
        if b.key not in panel.columns:
            rows.append({"benchmark": b.key, "title": b.title, "kind": b.kind,
                         "status": "UNAVAILABLE", "verdict": "UNKNOWN",
                         "independence": b.independence})
            continue
        s = panel[b.key].dropna()
        z = rolling_z(s, window)
        raw_latest = float(s.iloc[-1]) if not s.empty else None
        z_latest = float(z.dropna().iloc[-1]) if z.notna().any() else None
        state, basis = _benchmark_state(b, raw_latest, z_latest)
        lag = best_lag(ours, s)
        rows.append({
            "benchmark": b.key,
            "title": b.title,
            "kind": b.kind,
            "units": b.units,
            "axis_tested": "relative" if b.kind == "relative" else "level",
            "latest_date": str(s.index[-1].date()) if not s.empty else None,
            "latest_value": None if raw_latest is None else round(raw_latest, 3),
            "latest_rolling_z": None if z_latest is None else round(z_latest, 2),
            "state": state,
            "state_basis": basis,
            "verdict": _verdict(chip_label, state),
            "spearman_full": lag.get("corr_at_zero"),
            "best_lag_months": lag.get("best_lag"),
            "corr_at_best_lag": lag.get("corr_at_best"),
            "n_months": lag.get("n"),
            "episodes": disagreement_episodes(rolling_z(ours, window), z, b.orientation),
            "independence": b.independence,
            "note": b.note,
        })

    graded = [r for r in rows if r["verdict"] != "UNKNOWN"]
    tally = {v: sum(1 for r in graded if r["verdict"] == v)
             for v in ("AGREE", "PARTIAL", "CONTRADICT")}
    return {
        "axis": axis,
        "chip": chip_label,
        "window_months": window,
        "n_benchmarks_graded": len(graded),
        "tally": tally,
        "benchmarks": rows,
    }


def build_evidence_pack(
    country: str = "US",
    as_of: Optional[str] = None,
    force_refresh: bool = False,
    thresholds: Optional[dict] = None,
) -> dict:
    """Everything the reviewing agent needs on the numeric side, in one dict."""
    chip = chip_state(country=country, as_of=as_of, thresholds=thresholds)
    out = {
        "country": country,
        "as_of": chip["as_of"],
        "requested_as_of": as_of,
        "chip": {k: v for k, v in chip.items() if k != "history"},
        "axes": {},
        "caveat": (
            "Benchmarks are INDEPENDENTLY CONSTRUCTED, not input-independent. "
            "High correlation is partly mechanical and proves little; the "
            "informative outputs are CONTRADICT verdicts, disagreement episodes "
            "and lead/lag. Benchmarks marked kind='rate' test the LEVEL axis "
            "('is it growing / is inflation high?'), which is a different "
            "question from what the chip claims ('is it above its own norm and "
            "moving?'). Never score a relative chip against a level benchmark "
            "without saying which axis you are grading."
        ),
    }
    for axis in ("growth", "inflation"):
        panel = load_benchmark_panel(axis, force_refresh=force_refresh)
        out["axes"][axis] = compare_axis(axis, chip, panel, as_of=as_of)
    return out


def build_blind_pack(
    country: str = "US",
    as_of: Optional[str] = None,
    force_refresh: bool = False,
    trajectory_months: int = 24,
) -> dict:
    """Benchmark panel ONLY — no dashboard chip, no verdicts, no correlations.

    This is what a Stage-1 reviewer sees. Withholding our own read is what makes
    the review independent rather than a rationalisation of whatever the chip
    already says: an agent told the answer first will find reasons for it.
    `country` is accepted and echoed for provenance, but the panel is US-only
    (every benchmark here is a US series).
    """
    out = {
        "country": country,
        "as_of_requested": as_of,
        "blind": True,
        "instructions": (
            "Form your OWN read of US growth and inflation from these measures "
            "alone. Report each axis on BOTH axes of judgement: (1) LEVEL — is "
            "growth/inflation high or low in absolute terms; (2) RELATIVE — is it "
            "above or below its own recent norm, and accelerating or decelerating. "
            "These can disagree, and saying so is a finding, not a failure. "
            "Regime flags are reported Neutral unless they have actually fired."
        ),
        "axes": {},
    }
    for axis in ("growth", "inflation"):
        panel = load_benchmark_panel(axis, force_refresh=force_refresh)
        window = (CANONICAL_GROWTH_WINDOW if axis == "growth"
                  else CANONICAL_INFLATION_WINDOW)
        rows = []
        for b in benchmarks_for(axis):
            if b.key not in panel.columns:
                rows.append({"benchmark": b.key, "title": b.title, "status": "UNAVAILABLE"})
                continue
            s = panel[b.key].dropna()
            if as_of:
                s = s[s.index <= pd.Timestamp(as_of)]
            if s.empty:
                rows.append({"benchmark": b.key, "title": b.title, "status": "NO DATA AT DATE"})
                continue
            z = rolling_z(s, window)
            raw_latest = float(s.iloc[-1])
            z_latest = float(z.dropna().iloc[-1]) if z.notna().any() else None
            state, basis = _benchmark_state(b, raw_latest, z_latest)
            traj = s.tail(trajectory_months)
            rows.append({
                "benchmark": b.key,
                "title": b.title,
                "kind": b.kind,
                "units": b.units,
                "orientation": b.orientation,
                "latest_date": str(s.index[-1].date()),
                "latest_value": round(raw_latest, 3),
                "rolling_z": None if z_latest is None else round(z_latest, 2),
                "state": state,
                "state_basis": basis,
                "change_3m": (round(float(s.iloc[-1] - s.iloc[-4]), 3)
                              if len(s) >= 4 else None),
                "change_12m": (round(float(s.iloc[-1] - s.iloc[-13]), 3)
                               if len(s) >= 13 else None),
                "trajectory": {str(d.date()): round(float(v), 3)
                               for d, v in traj.items()},
            })
        out["axes"][axis] = {"axis": axis, "window_months": window, "benchmarks": rows}
    return out


# ── Rendering ────────────────────────────────────────────────────────────────

def render_markdown(pack: dict) -> str:
    c = pack["chip"]
    t = c["thresholds_in_force"]
    L = [
        f"# Benchmark evidence pack — {pack['country']} @ {pack['as_of']}",
        "",
        "## Dashboard read (reproduced with production code)",
        "",
        f"- Growth chip: **{c['growth_chip']}**  (score {c['growth_score']}, "
        f"delta {c['growth_delta']}, momentum {c['growth_momentum']})",
        f"- Inflation chip: **{c['inflation_chip']}**  (score {c['inflation_score']}, "
        f"delta {c['inflation_delta']}, momentum {c['inflation_momentum']})",
        f"- Score columns: {c['score_columns']}  (windows {c['windows']})",
        f"- Thresholds in force: gz={t['gz']}, iz={t['iz']}, gm={t['gm']}, "
        f"im={t['im']}, dynamic={t['dynamic']}",
        f"- Divergence flag: {c['divergence_flag']}",
        "",
        "## Caveat",
        "",
        pack["caveat"],
        "",
    ]
    for axis, res in pack["axes"].items():
        L += [f"## {axis.title()} axis — chip = {res['chip']}", "",
              f"Graded {res['n_benchmarks_graded']} benchmarks: {res['tally']}", "",
              "| benchmark | kind | units | axis | latest | z | state | verdict | r(0) | best lag | r(lag) |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in res["benchmarks"]:
            if r.get("status") == "UNAVAILABLE":
                L.append(f"| {r['benchmark']} | — | — | — | UNAVAILABLE | | | UNKNOWN | | | |")
                continue
            L.append(
                f"| {r['benchmark']} | {r['kind']} | {r.get('units','')} | {r['axis_tested']} | "
                f"{r['latest_value']} ({r['latest_date']}) | {r['latest_rolling_z']} | "
                f"{r['state']} | **{r['verdict']}** | {r['spearman_full']} | "
                f"{r['best_lag_months']} | {r['corr_at_best_lag']} |"
            )
        L.append("")
        eps = [(r["benchmark"], e) for r in res["benchmarks"] for e in r.get("episodes", [])]
        if eps:
            L += ["### Historical disagreement episodes", ""]
            for key, e in eps:
                L.append(f"- `{key}` {e['start']} → {e['end']} ({e['months']}mo): "
                         f"our Z {e['our_z_mean']} vs benchmark Z {e['benchmark_z_mean']}")
            L.append("")
    return "\n".join(L)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="External benchmark evidence pack for the chip audit")
    ap.add_argument("--country", default="US")
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD; audit the read as of this month")
    ap.add_argument("--json", default=None, help="also write the raw pack to this path")
    ap.add_argument("--refresh", action="store_true", help="force-refresh benchmark fetches")
    ap.add_argument("--blind", action="store_true",
                    help="benchmark panel only — withholds our chip, verdicts and "
                         "correlations, for Stage-1 independent review")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.blind:
        pack = build_blind_pack(country=args.country.upper(), as_of=args.as_of,
                                force_refresh=args.refresh)
        print(json.dumps(pack, indent=2, default=str))
    else:
        pack = build_evidence_pack(country=args.country.upper(), as_of=args.as_of,
                                   force_refresh=args.refresh)
        print(render_markdown(pack))
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(pack, fh, indent=2, default=str)
        logger.info("wrote %s", args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
