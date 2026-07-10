"""
Phase 1A+ pipeline: fetch FRED + WorldBank + IMF series, transform, normalize, store to DuckDB.
Multi-country: runs US (primary) then any YAML files under config/countries/.

Usage:
    python -m indicators.pipeline              # normal run (uses cache)
    python -m indicators.pipeline --refresh    # force re-fetch from all providers
    python -m indicators.pipeline --latest     # print latest signals only
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv

from indicators.composites import (
    audit_signal_correlations,
    compute_composite_history,
    load_composites_config,
)
from indicators.loader import fetch_series, fetch_wb_series, fetch_imf_series, fetch_eurostat_series, fetch_ecb_series, fetch_imf_sdmx_series, fetch_manual_series, fetch_ons_series
from indicators.longterm_stress import compute_debt_stress_history, load_longterm_stress_config
from indicators.debt_cycle_stage import compute_stage_history, load_stage_config
from indicators.models import CountryBinding, Signal
from indicators.normalize import build_signals, sanity_check
from indicators.transform import apply_transformation
from store.store import (
    delete_future_signals, get_connection, init_schema,
    upsert_signals, upsert_composites, update_rolling_composites,
    update_inflation_rolling,
    upsert_debt_stress, upsert_debt_cycle_stage, query_latest,
)

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

    if bid == "policy.real_yield_10y":
        # Nominal 10Y yield (%) − HICP headline YoY (decimal → %) → real yield in %
        yield_10y = transformed_store.get("policy.yield_10y")        # M pct_level (%)
        cpi_hl = transformed_store.get("inflation.cpi_headline")     # M yoy_pct (decimal)
        if yield_10y is None or cpi_hl is None:
            logger.warning("[derived] Missing inputs for %s", bid)
            return None
        y_m = yield_10y.resample("ME").last()
        c_m = (cpi_hl * 100.0).resample("ME").last()
        combined = pd.concat([y_m, c_m], axis=1, join="inner")
        combined.columns = ["y", "c"]
        return (combined["y"] - combined["c"]).dropna()

    if bid == "policy.yield_spread":
        # 10Y government yield (%) − central bank policy rate (%) → term premium proxy
        yield_10y = transformed_store.get("policy.yield_10y")        # M pct_level (%)
        policy_rate = transformed_store.get("policy.fed_funds_target")  # D pct_level (%)
        if yield_10y is None or policy_rate is None:
            logger.warning("[derived] Missing inputs for %s", bid)
            return None
        r_m = policy_rate.resample("ME").last()
        y_m = yield_10y.resample("ME").last()
        combined = pd.concat([y_m, r_m], axis=1, join="inner")
        combined.columns = ["y", "r"]
        return (combined["y"] - combined["r"]).dropna()

    if bid == "inflation.breakeven_avg":
        # Simple average of 5Y and 10Y TIPS breakevens (both D, pct_level)
        be5 = raw_store.get("T5YIE")
        be10 = raw_store.get("T10YIE")
        if be5 is None or be10 is None:
            logger.warning("[derived] Missing inputs for %s", bid)
            return None
        combined = pd.concat([be5, be10], axis=1, join="inner")
        combined.columns = ["be5", "be10"]
        return ((combined["be5"] + combined["be10"]) / 2.0).dropna()

    if bid == "policy.rate_expectations":
        # 2Y Treasury yield − effective fed funds (both pct_level, daily).
        # Market-implied expected policy change over ~2 years (Ray review A1).
        y2 = transformed_store.get("policy.yield_2y")
        ff = transformed_store.get("policy.fed_funds")
        if y2 is None or ff is None:
            logger.warning("[derived] Missing inputs for %s", bid)
            return None
        combined = pd.concat([y2, ff], axis=1, join="inner")
        combined.columns = ["y2", "ff"]
        return (combined["y2"] - combined["ff"]).dropna()

    if bid == "volatility.realized_vol":
        # Ray Dalio review 2026-07-05 (#13): annualized rolling std of log returns
        # on the country's own equity-index level. Uses transformed_store (keyed by
        # binding id, not provider series_id) so this one branch works for every
        # country's volatility.equity_index regardless of which underlying FRED
        # series backs it (SP500 daily for US, monthly share-price index for EZ/KR).
        eq = transformed_store.get("volatility.equity_index")
        if eq is None or eq.empty:
            return None
        log_returns = np.log(eq).diff().dropna()
        if binding.frequency == "D":
            window, periods_per_year = 21, 252   # ~1 trading month, annualized daily
        else:
            window, periods_per_year = 12, 12     # 12-month window, annualized monthly (EZ/KR proxy)
        realized_vol = (
            log_returns.rolling(window, min_periods=max(3, window // 2)).std()
            * np.sqrt(periods_per_year)
        )
        return realized_vol.dropna()

    if bid == "credit.btp_bund_spread":
        # Italian BTP 10Y minus German Bund 10Y (both in % pct_level)
        it_yield = transformed_store.get("credit.yield_it_10y")
        de_yield = transformed_store.get("credit.yield_de_10y")
        if it_yield is None or de_yield is None:
            logger.warning("[derived] Missing inputs for %s", bid)
            return None
        combined = pd.concat([it_yield, de_yield], axis=1, join="inner")
        combined.columns = ["it", "de"]
        return (combined["it"] - combined["de"]).dropna()

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


# ─── Per-country ingestion passes (1–4) ─────────────────────────────────────

def run_country(
    conn,
    yaml_path: Path,
    force_refresh: bool = False,
    is_primary: bool = False,
) -> dict:
    """
    Run ingestion passes 1–4 for a single country binding YAML.

    is_primary: if True, errors cause sys.exit(1); otherwise they are logged and skipped.
    Returns a results dict with ok/empty/error/sanity_warn counts.
    """
    bindings = load_bindings(yaml_path)
    country_code = bindings[0].country if bindings else yaml_path.stem.split("_")[0].upper()

    fred_bindings     = [b for b in bindings if b.provider == "FRED"       and b.verified]
    estat_bindings    = [b for b in bindings if b.provider == "Eurostat"   and b.verified]
    ecb_bindings      = [b for b in bindings if b.provider == "ECB"        and b.verified]
    ons_bindings      = [b for b in bindings if b.provider == "ONS"        and b.verified]
    wb_bindings       = [b for b in bindings if b.provider == "WorldBank"  and b.verified]
    imf_bindings      = [b for b in bindings if b.provider == "IMF"        and b.verified]
    imf_sdmx_bindings = [b for b in bindings if b.provider == "IMF_SDMX"   and b.verified]
    manual_bindings   = [b for b in bindings if b.provider == "Manual"     and b.verified]
    derived_bindings  = [b for b in bindings if b.provider == "derived"    and b.verified]
    skipped           = [b for b in bindings if not b.verified]

    print(f"\n{'=' * 70}")
    print(f"  Country: {country_code}  ({yaml_path.name})")
    print(f"  FRED: {len(fred_bindings)}  |  Eurostat: {len(estat_bindings)}  |  ECB: {len(ecb_bindings)}  "
          f"|  WorldBank: {len(wb_bindings)}  "
          f"|  IMF: {len(imf_bindings)}  |  Manual: {len(manual_bindings)}  "
          f"|  Derived: {len(derived_bindings)}  |  Skipped: {len(skipped)}")
    if skipped:
        print(f"    Skipped: {', '.join(b.id for b in skipped)}")
    print('=' * 70)

    # "slot" = a Manual binding whose file hasn't been dropped yet — a
    # documented pending state, counted separately so it never fails a run.
    results = {"ok": 0, "empty": 0, "error": 0, "sanity_warn": 0, "slot": 0}
    raw_store: dict[str, pd.Series] = {}
    transformed_store: dict[str, pd.Series] = {}

    # ── Pass 1: FRED series ───────────────────────────────────────────────
    print(f"\n─── Pass 1: FRED series [{country_code}] ──────────────────────────────")
    for binding in fred_bindings:
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

            raw_for_transform = (
                raw.rolling(binding.pre_smooth_window, min_periods=1).mean()
                if binding.pre_smooth_window
                else raw
            )

            # Apply raw_scale before transformation (e.g. already-YoY% series like KR CPI)
            if binding.raw_scale:
                raw_for_transform = raw_for_transform / binding.raw_scale

            transformed = apply_transformation(raw_for_transform, binding.transformation, binding.frequency)
            transformed = transformed.dropna()

            if transformed.empty:
                print(f"  [EMPTY after transform] {binding.id}")
                results["empty"] += 1
                continue

            transformed_store[binding.id] = transformed
            signals = build_signals(transformed, binding, raw_for_transform)
            latest = signals[-1] if signals else None

            if latest:
                warns = sanity_check(latest, binding)
                for w in warns:
                    print(f"  [SANITY WARN] {w}")
                    results["sanity_warn"] += 1

            n = upsert_signals(conn, signals)
            status = "PROXY" if binding.is_proxy else "OK"
            latest_val = f"{transformed.iloc[-1]:.4f}" if not transformed.empty else "?"
            latest_dt  = str(transformed.index[-1].date()) if not transformed.empty else "?"
            print(f"  [{status:5}] {binding.id:40s}  {binding.series_id:22s}  {binding.frequency}  {latest_dt}  {latest_val}  ({n} rows)")
            results["ok"] += 1

        except Exception as exc:
            logger.exception("[ERROR] %s: %s", binding.id, exc)
            results["error"] += 1
            if is_primary:
                sys.exit(1)

    # ── Pass 1.5: Eurostat series ─────────────────────────────────────────
    if estat_bindings:
        print(f"\n─── Pass 1.5: Eurostat series [{country_code}] ──────────────────────────")
        for binding in estat_bindings:
            try:
                raw = fetch_eurostat_series(
                    binding.series_id,
                    binding.eurostat_params or {},
                    frequency=binding.frequency,
                    force_refresh=force_refresh,
                )
                if raw is None or raw.empty:
                    print(f"  [EMPTY] {binding.id} ({binding.series_id})")
                    results["empty"] += 1
                    continue

                raw_store[binding.series_id] = raw

                if binding.raw_scale:
                    raw = raw / binding.raw_scale

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
                latest_val = f"{transformed.iloc[-1]:.4f}" if not transformed.empty else "?"
                latest_dt  = str(transformed.index[-1].date()) if not transformed.empty else "?"
                params_str = ",".join(f"{k}={v}" for k, v in (binding.eurostat_params or {}).items())
                print(f"  [{status:5}] {binding.id:40s}  {binding.series_id}?{params_str}  {binding.frequency}  {latest_dt}  {latest_val}  ({n} rows)")
                results["ok"] += 1

            except Exception as exc:
                logger.exception("[ERROR] %s: %s", binding.id, exc)
                results["error"] += 1
                if is_primary:
                    sys.exit(1)

    # ── Pass 1.6: ECB SDW series ──────────────────────────────────────────
    if ecb_bindings:
        print(f"\n─── Pass 1.6: ECB SDW series [{country_code}] ──────────────────────────")
        for binding in ecb_bindings:
            try:
                # series_id encodes flow/key (e.g. "IRS/M.DE.L.L40.CI.0000.EUR.N.Z")
                if not binding.series_id or "/" not in binding.series_id:
                    raise ValueError(f"ECB binding {binding.id} series_id must be 'FLOW/KEY'")
                flow, key = binding.series_id.split("/", 1)
                raw = fetch_ecb_series(
                    flow,
                    key,
                    frequency=binding.frequency,
                    force_refresh=force_refresh,
                )
                if raw is None or raw.empty:
                    print(f"  [EMPTY] {binding.id} ({binding.series_id})")
                    results["empty"] += 1
                    continue

                raw_store[binding.series_id] = raw

                if binding.raw_scale:
                    raw = raw / binding.raw_scale

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
                latest_val = f"{transformed.iloc[-1]:.4f}" if not transformed.empty else "?"
                latest_dt  = str(transformed.index[-1].date()) if not transformed.empty else "?"
                print(f"  [OK   ] {binding.id:40s}  {binding.series_id}  {binding.frequency}  {latest_dt}  {latest_val}  ({n} rows)")
                results["ok"] += 1

            except Exception as exc:
                logger.exception("[ERROR] %s: %s", binding.id, exc)
                results["error"] += 1
                if is_primary:
                    sys.exit(1)

    # ── Pass 1.7: UK ONS series (append-/data JSON) ───────────────────────
    if ons_bindings:
        print(f"\n─── Pass 1.7: ONS series [{country_code}] ────────────────────────────")
        for binding in ons_bindings:
            try:
                # series_id encodes "CDID/DATASET" (e.g. "d7g7/mm23")
                if not binding.series_id or "/" not in binding.series_id:
                    raise ValueError(f"ONS binding {binding.id} series_id must be 'CDID/DATASET'")
                cdid, dataset = binding.series_id.split("/", 1)
                raw = fetch_ons_series(cdid, dataset, frequency=binding.frequency,
                                       force_refresh=force_refresh)
                if raw is None or raw.empty:
                    print(f"  [EMPTY] {binding.id} ({binding.series_id})")
                    results["empty"] += 1
                    continue

                raw_store[binding.series_id] = raw
                if binding.raw_scale:
                    raw = raw / binding.raw_scale

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
                    for w in sanity_check(latest, binding):
                        print(f"  [SANITY WARN] {w}")
                        results["sanity_warn"] += 1

                n = upsert_signals(conn, signals)
                latest_val = f"{transformed.iloc[-1]:.4f}" if not transformed.empty else "?"
                latest_dt  = str(transformed.index[-1].date()) if not transformed.empty else "?"
                print(f"  [OK   ] {binding.id:40s}  {binding.series_id}  {binding.frequency}  {latest_dt}  {latest_val}  ({n} rows)")
                results["ok"] += 1
            except Exception as exc:
                logger.exception("[ERROR] %s: %s", binding.id, exc)
                results["error"] += 1
                if is_primary:
                    sys.exit(1)

    # ── Pass 2: WorldBank series ───────────────────────────────────────────
    print(f"\n─── Pass 2: WorldBank series [{country_code}] ─────────────────────────")
    for binding in wb_bindings:
        try:
            raw = fetch_wb_series(
                binding.series_id,
                country_iso=binding.country,
                frequency=binding.frequency,
                force_refresh=force_refresh,
            )
            if raw is None or raw.empty:
                print(f"  [EMPTY] {binding.id} ({binding.series_id})")
                results["empty"] += 1
                continue

            if binding.raw_scale:
                raw = raw / binding.raw_scale

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
            latest_val = f"{transformed.iloc[-1]:.4f}" if not transformed.empty else "?"
            latest_dt  = str(transformed.index[-1].date()) if not transformed.empty else "?"
            print(f"  [{status:5}] {binding.id:40s}  {binding.series_id:30s}  A  {latest_dt}  {latest_val}  ({n} rows)")
            results["ok"] += 1

        except Exception as exc:
            logger.exception("[ERROR] %s: %s", binding.id, exc)
            results["error"] += 1
            if is_primary:
                sys.exit(1)

    # ── Pass 3: IMF series ────────────────────────────────────────────────
    print(f"\n─── Pass 3: IMF series [{country_code}] ────────────────────────────────")
    for binding in imf_bindings:
        try:
            raw = fetch_imf_series(
                binding.series_id,
                country_iso2=binding.country,
                frequency=binding.frequency,
                force_refresh=force_refresh,
            )
            if raw is None or raw.empty:
                print(f"  [EMPTY] {binding.id} ({binding.series_id})")
                results["empty"] += 1
                continue

            if binding.raw_scale:
                raw = raw / binding.raw_scale

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
            latest_val = f"{transformed.iloc[-1]:.4f}" if not transformed.empty else "?"
            latest_dt  = str(transformed.index[-1].date()) if not transformed.empty else "?"
            print(f"  [{status:5}] {binding.id:40s}  {binding.series_id:30s}  A  {latest_dt}  {latest_val}  ({n} rows)")
            results["ok"] += 1

        except Exception as exc:
            logger.exception("[ERROR] %s: %s", binding.id, exc)
            results["error"] += 1
            if is_primary:
                sys.exit(1)

    # ── Pass 3.5: IMF SDMX series (api.imf.org — COFER etc.) ───────────────
    if imf_sdmx_bindings:
        print(f"\n─── Pass 3.5: IMF SDMX series [{country_code}] ─────────────────────────")
    for binding in imf_sdmx_bindings:
        try:
            # series_id convention mirrors ECB: "DATAFLOW/KEY"
            dataset, _, sdmx_key = (binding.series_id or "").partition("/")
            if not dataset or not sdmx_key:
                print(f"  [SKIP] {binding.id}: series_id must be 'DATAFLOW/KEY', got '{binding.series_id}'")
                results["error"] += 1
                continue
            raw = fetch_imf_sdmx_series(
                dataset, sdmx_key,
                frequency=binding.frequency,
                force_refresh=force_refresh,
            )
            if raw is None or raw.empty:
                print(f"  [EMPTY] {binding.id} ({binding.series_id})")
                results["empty"] += 1
                continue

            if binding.raw_scale:
                raw = raw / binding.raw_scale

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
            latest_val = f"{transformed.iloc[-1]:.4f}" if not transformed.empty else "?"
            latest_dt  = str(transformed.index[-1].date()) if not transformed.empty else "?"
            print(f"  [{status:5}] {binding.id:40s}  {binding.series_id:30s}  {binding.frequency}  {latest_dt}  {latest_val}  ({n} rows)")
            results["ok"] += 1

        except Exception as exc:
            logger.exception("[ERROR] %s: %s", binding.id, exc)
            results["error"] += 1
            if is_primary:
                sys.exit(1)

    # ── Pass 3.8: Manual-load series (roadmap D4 — V-Dem / GPR / EM-DAT) ───
    # Sources with no free API. A binding names its CSV in series_id; the
    # file is hand-produced via scripts/prepare_*.py and dropped in
    # MANUAL_DATA_DIR. Missing file = PENDING SLOT (never fails the run);
    # present-but-malformed file = loud error.
    if manual_bindings:
        print(f"\n─── Pass 3.8: Manual-load series [{country_code}] ──────────────────────")
    for binding in manual_bindings:
        try:
            raw = fetch_manual_series(binding.series_id, frequency=binding.frequency)
            if raw is None:
                print(f"  [SLOT ] {binding.id:40s}  {binding.series_id:30s}  pending — "
                      f"drop the file in manual_data/ (see its README)")
                results["slot"] += 1
                continue

            if binding.raw_scale:
                raw = raw / binding.raw_scale

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
            latest_val = f"{transformed.iloc[-1]:.4f}" if not transformed.empty else "?"
            latest_dt  = str(transformed.index[-1].date()) if not transformed.empty else "?"
            print(f"  [{status:5}] {binding.id:40s}  {binding.series_id:30s}  {binding.frequency}  {latest_dt}  {latest_val}  ({n} rows)")
            results["ok"] += 1

        except Exception as exc:
            logger.exception("[ERROR] %s: %s", binding.id, exc)
            results["error"] += 1
            if is_primary:
                sys.exit(1)

    # ── Pass 4: Derived series ─────────────────────────────────────────────
    if derived_bindings:
        print(f"\n─── Pass 4: Derived series [{country_code}] ────────────────────────────")
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
                latest_val = f"{latest.value:.4f}" if latest and latest.value is not None else "?"
                latest_dt  = str(latest.as_of) if latest else "?"
                print(f"  [DERIVED] {binding.id:40s}  {latest_dt}  {latest_val}  ({n} rows)")
                results["ok"] += 1

            except Exception as exc:
                logger.exception("[ERROR] %s (derived): %s", binding.id, exc)
                results["error"] += 1
                if is_primary:
                    sys.exit(1)

    slot_txt = f"  |  Pending slots: {results['slot']}" if results.get("slot") else ""
    print(f"\n  [{country_code}] OK: {results['ok']}  |  Empty: {results['empty']}  "
          f"|  Errors: {results['error']}  |  Sanity warnings: {results['sanity_warn']}{slot_txt}")
    return results


# ─── Main pipeline ───────────────────────────────────────────────────────────

def run(force_refresh: bool = False, print_latest: bool = False) -> None:
    load_dotenv(_PROJECT_ROOT / ".env")

    print("=" * 70)
    print("  Indicators Machine — Pipeline (US primary + country rollout)")
    print("=" * 70)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    init_schema(conn)
    removed_future = delete_future_signals(conn)
    if removed_future:
        logger.warning("Removed %d future-dated signal rows", removed_future)

    post_ingestion_errors = 0
    country_summaries: list[tuple[str, dict]] = []

    us_comp_config = load_composites_config("US")

    # ── US (primary country) — passes 1–4 ────────────────────────────────
    us_bindings = load_bindings(_CONFIG_DIR / "us_bindings.yaml")
    us_results  = run_country(conn, _CONFIG_DIR / "us_bindings.yaml", force_refresh=force_refresh, is_primary=True)

    # ── Pass 5: US Composites ──────────────────────────────────────────────
    print("\n─── Pass 5: Composites engine [US] ────────────────────────────────")
    try:
        freq_map = {f"us.{b.id}": b.frequency for b in us_bindings if b.verified}
        snapshots = compute_composite_history(conn, "US", us_comp_config, freq_map=freq_map)
        n_comp      = upsert_composites(conn, snapshots)
        audit_signal_correlations(conn, "US", us_comp_config)
        latest_snap = snapshots[-1] if snapshots else None
        if latest_snap:
            q   = latest_snap.quadrant or "?"
            gs  = f"{latest_snap.growth_score:+.3f}" if latest_snap.growth_score is not None else "?"
            is_ = f"{latest_snap.inflation_score:+.3f}" if latest_snap.inflation_score is not None else "?"
            cf  = f"{latest_snap.confidence:.0%}" if latest_snap.confidence is not None else "?"
            ds  = f"{latest_snap.disequilibrium_score:.3f}" if latest_snap.disequilibrium_score is not None else "?"
            print(f"  Snapshots stored : {n_comp}")
            print(f"  Latest ({latest_snap.as_of}): {q}")
            print(f"    Growth={gs}  Inflation={is_}  Confidence={cf}  Diseq={ds}")
        else:
            print("  [WARN] No composite snapshots produced")
            post_ingestion_errors += 1
    except Exception as exc:
        logger.exception("[ERROR] Composites pass [US]: %s", exc)
        post_ingestion_errors += 1

    # ── Passes 5b-5d: Rolling composite variants [US] ─────────────────────
    print("\n─── Passes 5b-5d: Rolling composite variants [US] ─────────────────")
    _ROLLING_CONFIGS = [
        ("zscore_36m", 12, "36m", "12m"),
        ("zscore_48m", 18, "48m", "18m"),
        ("zscore_60m", 24, "60m", "24m"),
    ]
    try:
        freq_map = {f"us.{b.id}": b.frequency for b in us_bindings if b.verified}
        for zscore_col, diseq_w, force_sfx, diseq_sfx in _ROLLING_CONFIGS:
            roll_snaps = compute_composite_history(
                conn, "US", us_comp_config, freq_map=freq_map,
                zscore_col=zscore_col, diseq_window=diseq_w,
            )
            n_upd = update_rolling_composites(
                conn, roll_snaps, force_suffix=force_sfx, diseq_suffix=diseq_sfx,
            )
            print(f"  [{force_sfx} force / {diseq_sfx} diseq] Updated {n_upd} composite rows")
    except Exception as exc:
        logger.exception("[ERROR] Rolling composites pass: %s", exc)
        post_ingestion_errors += 1

    # ── Passes 5e-5f: Inflation-only rolling windows (90m / 120m) [US] ────
    print("\n─── Passes 5e-5f: Inflation-only rolling variants [US] ─────────────")
    _INFLATION_ROLLING_CONFIGS = [
        ("zscore_90m",  "90m"),
        ("zscore_120m", "120m"),
    ]
    try:
        freq_map = {f"us.{b.id}": b.frequency for b in us_bindings if b.verified}
        for zscore_col, force_sfx in _INFLATION_ROLLING_CONFIGS:
            roll_snaps = compute_composite_history(
                conn, "US", us_comp_config, freq_map=freq_map,
                zscore_col=zscore_col, diseq_window=0,
            )
            n_upd = update_inflation_rolling(
                conn, roll_snaps, force_suffix=force_sfx,
            )
            print(f"  [inflation {force_sfx}] Updated {n_upd} composite rows")
    except Exception as exc:
        logger.exception("[ERROR] Inflation rolling passes (90m/120m): %s", exc)
        post_ingestion_errors += 1

    # ── Pass 6: Long-Term Debt Stress Indicator [US only] ─────────────────
    print("\n─── Pass 6: Long-Term Debt Stress Indicator [US] ──────────────────")
    try:
        stress_config = load_longterm_stress_config(_CONFIG_DIR / "longterm_stress.yaml")
        stress_snaps  = compute_debt_stress_history(conn, "US", stress_config, DATA_DIR)
        n_stress      = upsert_debt_stress(conn, stress_snaps)
        latest_stress = stress_snaps[-1] if stress_snaps else None
        if latest_stress:
            sc = f"{latest_stress.stress_score:+.3f}" if latest_stress.stress_score is not None else "null"
            rw = f"{latest_stress.retained_weight:.0%}" if latest_stress.retained_weight is not None else "?"
            total_stress_components = len(stress_config.get("components", []))
            print(f"  Snapshots stored : {n_stress}")
            print(f"  Latest ({latest_stress.as_of}): stress={sc}  components={latest_stress.n_components}/{total_stress_components}"
                  f"  retained_weight={rw}  low_coverage={latest_stress.low_coverage}")
        else:
            print("  [WARN] No debt stress snapshots produced")
            post_ingestion_errors += 1
    except Exception as exc:
        logger.exception("[ERROR] Debt stress pass: %s", exc)
        post_ingestion_errors += 1

    # ── Additional countries from config/countries/ ───────────────────────
    country_dir = _CONFIG_DIR / "countries"
    country_yamls = sorted(country_dir.glob("*_bindings.yaml")) if country_dir.exists() else []

    for yaml_path in country_yamls:
        country_results = run_country(conn, yaml_path, force_refresh=force_refresh, is_primary=False)

        # Load bindings to build freq_map for composites
        country_bindings = load_bindings(yaml_path)
        country_code = country_bindings[0].country.lower() if country_bindings else yaml_path.stem.split("_")[0]
        country_results["country"] = country_code.upper()
        freq_map = {f"{country_code}.{b.id}": b.frequency for b in country_bindings if b.verified}

        # Composites for this country
        print(f"\n─── Pass 5: Composites engine [{country_code.upper()}] ──────────────────────")
        try:
            try:
                country_comp_config = load_composites_config(country_code.upper())
            except FileNotFoundError:
                logger.warning(
                    "[%s] No composites file found — skipping composite pass. "
                    "Create config/countries/%s_composites.yaml to enable.",
                    country_code.upper(), country_code.lower(),
                )
                country_results["error"] += 1
                country_summaries.append((country_code.upper(), country_results))
                continue
            snaps = compute_composite_history(conn, country_code.upper(), country_comp_config, freq_map=freq_map)
            n_comp = upsert_composites(conn, snaps)
            audit_signal_correlations(conn, country_code.upper(), country_comp_config)

            # Rolling composite variants (Ray audit ruling 2026-07-06, Q1b:
            # every country needs the same rolling windows as the US so the
            # cross-country views can normalize on one canonical window).
            for zscore_col, diseq_w, force_sfx, diseq_sfx in [
                ("zscore_36m", 12, "36m", "12m"),
                ("zscore_48m", 18, "48m", "18m"),
                ("zscore_60m", 24, "60m", "24m"),
            ]:
                roll_snaps = compute_composite_history(
                    conn, country_code.upper(), country_comp_config, freq_map=freq_map,
                    zscore_col=zscore_col, diseq_window=diseq_w,
                )
                update_rolling_composites(conn, roll_snaps, force_suffix=force_sfx, diseq_suffix=diseq_sfx)
            for zscore_col, force_sfx in [("zscore_90m", "90m"), ("zscore_120m", "120m")]:
                roll_snaps = compute_composite_history(
                    conn, country_code.upper(), country_comp_config, freq_map=freq_map,
                    zscore_col=zscore_col, diseq_window=0,
                )
                update_inflation_rolling(conn, roll_snaps, force_suffix=force_sfx)
            print(f"  Rolling variants (36/48/60m force, 90/120m inflation) updated")
            latest = snaps[-1] if snaps else None
            if latest:
                q   = latest.quadrant or "?"
                gs  = f"{latest.growth_score:+.3f}" if latest.growth_score is not None else "?"
                is_ = f"{latest.inflation_score:+.3f}" if latest.inflation_score is not None else "?"
                cf  = f"{latest.confidence:.0%}" if latest.confidence is not None else "?"
                ds  = f"{latest.disequilibrium_score:.3f}" if latest.disequilibrium_score is not None else "?"
                print(f"  Snapshots stored : {n_comp}")
                print(f"  Latest ({latest.as_of}): {q}")
                print(f"    Growth={gs}  Inflation={is_}  Confidence={cf}  Diseq={ds}")
                print(f"    G-signals={latest.n_growth_signals}  I-signals={latest.n_inflation_signals}  LowCov={latest.low_coverage}")
            else:
                print(f"  [WARN] No composite snapshots produced for {country_code.upper()}")
                country_results["error"] += 1
        except Exception as exc:
            logger.exception("[ERROR] Composites pass [%s]: %s", country_code.upper(), exc)
            country_results["error"] += 1
        country_summaries.append((country_code.upper(), country_results))

    # ── Pass 7: Long-Term Debt-Cycle Stage Classifier (all configured) ────
    # Runs AFTER the country loop so newly-ingested countries have their
    # signals in the DB before their stage features are built.
    print("\n─── Pass 7: Debt-Cycle Stage Classifier ───────────────────────────")
    try:
        stage_cfg = load_stage_config()
        for stage_country in stage_cfg.get("countries", {}):
            try:
                stage_snaps = compute_stage_history(conn, stage_country, stage_cfg)
                n_stage = upsert_debt_cycle_stage(conn, stage_snaps)
                latest_stage = stage_snaps[-1] if stage_snaps else None
                if latest_stage and latest_stage.stage:
                    cf = f"{latest_stage.confidence:.2f}" if latest_stage.confidence is not None else "?"
                    print(f"  [{stage_country}] {n_stage} snapshots — latest ({latest_stage.as_of}): "
                          f"stage={latest_stage.stage}  confidence={cf}  "
                          f"features={latest_stage.n_features}/5")
                else:
                    print(f"  [{stage_country}] {n_stage} snapshots — no current stage label "
                          f"(insufficient features)")
            except Exception as exc:
                logger.exception("[ERROR] Stage classifier [%s]: %s", stage_country, exc)
                post_ingestion_errors += 1
    except Exception as exc:
        logger.exception("[ERROR] Stage classifier pass: %s", exc)
        post_ingestion_errors += 1

    # ── Summary ────────────────────────────────────────────────────────────
    print()
    print("─── Summary ───────────────────────────────────────────────────────")
    total_ok    = us_results["ok"]
    total_empty = us_results["empty"]
    total_err   = us_results["error"]
    total_warn  = us_results["sanity_warn"]
    print(f"  [US]  OK: {total_ok}  |  Empty: {total_empty}  |  Errors: {total_err}  |  Sanity warnings: {total_warn}")
    if post_ingestion_errors:
        print(f"  [US]  Post-ingestion errors: {post_ingestion_errors}")
    for code, results in country_summaries:
        slot_txt = f"  |  Pending slots: {results['slot']}" if results.get("slot") else ""
        print(
            f"  [{code}] OK: {results['ok']}  |  Empty: {results['empty']}  "
            f"|  Errors: {results['error']}  |  Sanity warnings: {results['sanity_warn']}{slot_txt}"
        )
    print(f"  Country files processed: {len(country_yamls)}")

    if print_latest:
        print("\n─── Latest signals ────────────────────────────────────────────────")
        df = query_latest(conn)
        if not df.empty:
            for _, row in df.iterrows():
                s = Signal(**row.to_dict())
                _print_signal(s)

    conn.close()

    country_failures = sum(
        results["error"] + results["empty"]
        for _, results in country_summaries
    )
    if (
        us_results["error"] > 0
        or us_results["empty"] > 0
        or post_ingestion_errors > 0
        or country_failures > 0
    ):
        sys.exit(1)


if __name__ == "__main__":
    force = "--refresh" in sys.argv
    latest = "--latest" in sys.argv
    run(force_refresh=force, print_latest=latest)
