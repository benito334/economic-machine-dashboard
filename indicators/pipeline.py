"""
Phase 1A-i pipeline: fetch FRED series, transform, normalize, store to DuckDB.

Usage:
    python -m indicators.pipeline              # normal run (uses cache)
    python -m indicators.pipeline --refresh    # force re-fetch from FRED
    python -m indicators.pipeline --latest     # print latest signals only
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from indicators.loader import fetch_series
from indicators.models import CountryBinding, Signal
from indicators.normalize import build_signals, sanity_check
from indicators.transform import apply_transformation
from store.store import get_connection, init_schema, upsert_signals, query_latest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")

_PROJECT_ROOT = Path(__file__).parents[1]
_CONFIG_DIR = _PROJECT_ROOT / "config"
DATA_DIR = Path(os.environ.get("DATA_DIR", "/mnt/data/project_data/all_weather/indicators_machine"))


# ─── Config loading ─────────────────────────────────────────────────────────

def load_bindings(path: Path) -> list[CountryBinding]:
    with open(path) as f:
        raw = yaml.safe_load(f)
    bindings = []
    for entry in raw.get("bindings", []):
        b = CountryBinding(**entry)
        bindings.append(b)
    return bindings


# ─── Derived series computation ──────────────────────────────────────────────

def compute_derived(
    binding: CountryBinding,
    raw_store: dict[str, pd.Series],
    transformed_store: dict[str, pd.Series],
) -> Optional[pd.Series]:
    """
    Compute a derived series from already-fetched raw and transformed data.

    raw_store keys:       FRED series IDs (e.g. "DFF", "GDP")
    transformed_store keys: binding IDs   (e.g. "master.gdp_nominal")
    """
    bid = binding.id

    if bid == "master.spending_vs_labor":
        # YoY(GDP) − (YoY(PAYEMS) + YoY(OPHNFB))
        # All three are quarterly (PAYEMS is monthly — resample to Q)
        ngdp = transformed_store.get("master.gdp_nominal")      # Q yoy_pct decimal
        payrolls = transformed_store.get("growth.payrolls")     # M yoy_pct decimal
        prod = transformed_store.get("growth.productivity")     # Q yoy_pct decimal
        if any(x is None for x in [ngdp, payrolls, prod]):
            logger.warning("[derived] Missing inputs for %s", bid)
            return None
        payrolls_q = payrolls.resample("QE").last()
        prod_q = prod.resample("QE").last()
        ngdp_q = ngdp.resample("QE").last()
        result = ngdp_q - (payrolls_q + prod_q)
        return result.dropna()

    if bid == "master.ngdp_minus_yield":
        # YoY(GDP) − (DGS10 / 100)  → both in decimal form
        ngdp = transformed_store.get("master.gdp_nominal")      # Q yoy_pct decimal
        dgs10_raw = raw_store.get("DGS10")                      # D level in % (e.g. 4.5)
        if ngdp is None or dgs10_raw is None:
            logger.warning("[derived] Missing inputs for %s", bid)
            return None
        # Convert yield to decimal, then resample to quarterly
        yield_q = (dgs10_raw / 100.0).resample("QE").last()
        ngdp_q = ngdp.resample("QE").last()
        result = ngdp_q - yield_q
        return result.dropna()

    if bid == "policy.real_fed_funds":
        # DFF (% level) − YoY(Core CPI) × 100  → result in % level
        dff_raw = raw_store.get("DFF")                          # D level in % (e.g. 5.33)
        cpi_yoy = transformed_store.get("inflation.cpi_core")  # M yoy_pct decimal
        if dff_raw is None or cpi_yoy is None:
            logger.warning("[derived] Missing inputs for %s", bid)
            return None
        # Forward-fill monthly CPI to daily
        cpi_daily = cpi_yoy.reindex(dff_raw.index, method="ffill") * 100.0
        result = dff_raw - cpi_daily
        return result.dropna()

    if bid == "policy.monetary_base_gdp":
        # WALCL (millions $) ÷ GDP (billions $ × 1000 = millions $)
        walcl_raw = raw_store.get("WALCL")                      # W level in M$
        gdp_raw = raw_store.get("GDP")                          # Q level in B$
        if walcl_raw is None or gdp_raw is None:
            logger.warning("[derived] Missing inputs for %s", bid)
            return None
        # Align GDP (quarterly) to WALCL (weekly) via forward-fill, then resample to Q
        gdp_weekly = gdp_raw.reindex(walcl_raw.index, method="ffill")
        ratio = walcl_raw / (gdp_weekly * 1000.0)
        result = ratio.resample("QE").last()
        return result.dropna()

    logger.warning("[derived] Unknown derived binding id: %s", bid)
    return None


# ─── Sanity + reporting ──────────────────────────────────────────────────────

def _print_signal(s: Signal) -> None:
    val_str = f"{s.value:.4f}" if s.value is not None else "None"
    z_str = f"Z={s.zscore:+.2f}" if s.zscore is not None else "Z=?"
    p_str = f"P={s.level_percentile:.0%}" if s.level_percentile is not None else "P=?"
    flags = " ".join(f for f in ["PROXY" if s.is_proxy else "",
                                  "STALE" if s.is_stale else "",
                                  "LOW_HIST" if s.low_history else ""] if f)
    print(f"  → {s.id:45s}  {val_str:>10} {s.units:12}  {z_str}  {p_str}  {s.direction or '?':8}  {flags}")


# ─── Main pipeline ───────────────────────────────────────────────────────────

def run(force_refresh: bool = False, print_latest: bool = False) -> None:
    print("=" * 70)
    print("  Indicators Machine — Phase 1A-i Pipeline (US / FRED)")
    print("=" * 70)

    # Ensure data dirs exist
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    init_schema(conn)

    bindings = load_bindings(_CONFIG_DIR / "us_bindings.yaml")
    raw_bindings = [b for b in bindings if b.provider == "FRED" and b.verified]
    derived_bindings = [b for b in bindings if b.provider == "derived" and b.verified]
    skipped = [b for b in bindings if not b.verified]

    print(f"\n  FRED series : {len(raw_bindings)}")
    print(f"  Derived     : {len(derived_bindings)}")
    print(f"  Skipped (⚠ VERIFY) : {len(skipped)}")
    if skipped:
        print(f"    {', '.join(b.id for b in skipped)}")
    print()

    results = {"ok": 0, "empty": 0, "error": 0, "sanity_warn": 0}
    raw_store: dict[str, pd.Series] = {}        # FRED series_id → raw pd.Series
    transformed_store: dict[str, pd.Series] = {}  # binding.id    → transformed pd.Series

    # ── Pass 1: FRED series ───────────────────────────────────────────────
    print("─── Pass 1: FRED series ───────────────────────────────────────────")
    for binding in raw_bindings:
        try:
            raw = fetch_series(
                binding.series_id,
                binding.frequency,
                force_refresh=force_refresh,
            )
            if raw is None or raw.empty:
                print(f"  [EMPTY] {binding.id} ({binding.series_id})")
                results["empty"] += 1
                continue

            raw_store[binding.series_id] = raw

            transformed = apply_transformation(raw, binding.transformation, binding.frequency)
            transformed = transformed.dropna()

            if transformed.empty:
                print(f"  [EMPTY after transform] {binding.id}")
                results["empty"] += 1
                continue

            transformed_store[binding.id] = transformed

            signals = build_signals(transformed, binding, raw)
            latest = signals[-1] if signals else None

            if latest:
                warns = sanity_check(latest, binding)
                for w in warns:
                    print(f"  [SANITY WARN] {w}")
                    results["sanity_warn"] += 1

            n = upsert_signals(conn, signals)
            status = "PROXY" if binding.is_proxy else "OK"
            freq_label = binding.frequency
            latest_val = f"{transformed.iloc[-1]:.4f}" if not transformed.empty else "?"
            latest_dt = str(transformed.index[-1].date()) if not transformed.empty else "?"
            print(f"  [{status:5}] {binding.id:40s}  {binding.series_id:20s}  {freq_label}  {latest_dt}  {latest_val}  ({n} rows)")
            results["ok"] += 1

        except Exception as exc:
            logger.exception("[ERROR] %s: %s", binding.id, exc)
            results["error"] += 1

    # ── Pass 2: Derived series ─────────────────────────────────────────────
    print("\n─── Pass 2: Derived series ────────────────────────────────────────")
    for binding in derived_bindings:
        try:
            series = compute_derived(binding, raw_store, transformed_store)
            if series is None or series.empty:
                print(f"  [EMPTY] {binding.id} (derived)")
                results["empty"] += 1
                continue

            transformed_store[binding.id] = series
            signals = build_signals(series, binding)
            latest = signals[-1] if signals else None

            if latest:
                warns = sanity_check(latest, binding)
                for w in warns:
                    print(f"  [SANITY WARN] {w}")
                    results["sanity_warn"] += 1

            n = upsert_signals(conn, signals)
            latest_val = f"{series.iloc[-1]:.4f}"
            latest_dt = str(series.index[-1].date())
            print(f"  [DERIVED] {binding.id:40s}  {latest_dt}  {latest_val}  ({n} rows)")
            results["ok"] += 1

        except Exception as exc:
            logger.exception("[ERROR] %s (derived): %s", binding.id, exc)
            results["error"] += 1

    # ── Summary ────────────────────────────────────────────────────────────
    print()
    print("─── Summary ───────────────────────────────────────────────────────")
    print(f"  OK: {results['ok']}  |  Empty: {results['empty']}  |  Errors: {results['error']}  |  Sanity warnings: {results['sanity_warn']}")

    if print_latest:
        print("\n─── Latest signals ────────────────────────────────────────────────")
        df = query_latest(conn)
        if not df.empty:
            for _, row in df.iterrows():
                s = Signal(**row.to_dict())
                _print_signal(s)

    conn.close()

    if results["error"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    force = "--refresh" in sys.argv
    latest = "--latest" in sys.argv
    run(force_refresh=force, print_latest=latest)
