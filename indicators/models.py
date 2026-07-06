from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CountryBinding(BaseModel):
    """One-to-one mapping of a concept to a concrete data source for one country."""

    id: str  # concept identifier, e.g. "growth.payrolls"
    series_id: Optional[str] = None  # provider series ID; None for derived
    provider: str  # FRED | WorldBank | IMF | OECD | derived | manual
    frequency: str  # D | W | M | Q | A
    force: str  # growth | inflation | policy | credit | premium | external | capital | currency | governance | demographics | climate | master
    lead_lag: str  # leading | coincident | lagging | structural
    transformation: str  # yoy_pct | level | spread | derived
    units: str  # human-readable unit label
    country: str = "US"
    source_tier: Literal["free", "deferred"] = "free"
    vintage_available: bool = False
    is_proxy: bool = False
    is_constructed: bool = False  # True for derived/computed series
    verified: bool = False  # True when series_id confirmed via provider search
    equilibrium: Optional[float] = None  # neutral value in transformed units
    linkage: str = ""  # causal explanation shown as tooltip
    sanity_min: Optional[float] = None
    sanity_max: Optional[float] = None
    notes: str = ""
    pre_smooth_window: Optional[int] = None  # H2: rolling-mean window applied to raw series before transformation
    raw_scale: Optional[float] = None  # divide raw fetched values by this factor before transformation (e.g. 100 to convert % → decimal, 1e9 to convert USD → billions)
    eurostat_params: Optional[dict] = None  # dimension filter dict for Eurostat JSON stats API (provider=Eurostat only)


class Signal(BaseModel):
    """Standardized output record — one per (concept, observation date)."""

    id: str  # country.force.concept, e.g. "us.growth.payrolls"
    country: str
    force: str
    lead_lag: str
    as_of: date
    value: Optional[float] = None
    units: str = ""
    level_percentile: Optional[float] = None  # 0–1 rank within full history
    zscore: Optional[float] = None  # vs full-series mean/std
    change_1m: Optional[float] = None  # absolute change over ~1 month
    change_3m: Optional[float] = None
    change_12m: Optional[float] = None
    momentum_percentile: Optional[float] = None  # D1: rank of change_3m within full change_3m history (0–1)
    direction: Optional[str] = None  # rising | falling | flat
    equilibrium_estimate: Optional[float] = None
    distance_from_equilibrium: Optional[float] = None
    surprise: Optional[float] = None  # actual − consensus (if wired)
    # Rolling Z-scores for configurable look-back windows (pre-computed at pipeline time)
    zscore_12m: Optional[float] = None
    zscore_18m: Optional[float] = None
    zscore_24m: Optional[float] = None
    zscore_36m: Optional[float] = None
    zscore_48m: Optional[float] = None
    zscore_60m: Optional[float] = None
    zscore_90m: Optional[float] = None
    zscore_120m: Optional[float] = None
    is_constructed: bool = False
    is_proxy: bool = False
    is_stale: bool = False
    low_history: bool = False  # True when < 15 observations for normalization
    provider: str = ""
    source_tier: str = "free"
    vintage_available: bool = False
    linkage: str = ""
    source: str = ""  # e.g. "FRED:PAYEMS"


class CompositeSnapshot(BaseModel):
    """One composite reading for a country at a given month-end date."""

    country: str
    as_of: date
    growth_score: Optional[float] = None
    inflation_score: Optional[float] = None
    quadrant: Optional[str] = None        # Expansion | Inflationary Boom | Stagflation | Disinflationary Slowdown
    confidence: Optional[float] = None   # 0–1: fraction of signals whose direction agrees with quadrant
    disequilibrium_score: Optional[float] = None
    n_growth_signals: int = 0
    n_inflation_signals: int = 0
    n_forces: int = 0
    low_coverage: bool = False
    stale_signals: Optional[str] = None  # L3: "signal_id:fill_months,..." for signals with fill_age > 0
    growth_momentum: Optional[float] = None    # fraction of growth-positive direction signals (0–1)
    inflation_momentum: Optional[float] = None # fraction of inflation-positive direction signals (0–1)
    rate_score: Optional[float] = None        # financial accommodation composite (positive = loose)
    credit_score: Optional[float] = None      # credit health composite (positive = healthy)
    rate_momentum: Optional[float] = None     # fraction of accommodation-positive direction signals (0–1)
    credit_momentum: Optional[float] = None   # fraction of credit-health-positive direction signals (0–1)
    volatility_score: Optional[float] = None     # market volatility composite (positive = higher vol / risk-off)
    volatility_momentum: Optional[float] = None  # fraction of vol-rising direction signals (0–1)
    productivity_score: Optional[float] = None    # long-run productivity trend composite (Ray's third big force)
    productivity_momentum: Optional[float] = None # fraction of productivity-rising direction signals (0–1)
    weight_audit: Optional[str] = None  # JSON: point-in-time nominal/dynamic/decay weights by signal


class DebtStressSnapshot(BaseModel):
    """One Long-Term Debt Stress reading for a country at a quarter-end date."""

    country: str
    as_of: date                           # quarter-end date
    stress_score: Optional[float] = None  # weighted Z-score composite (tunable weights in longterm_stress.yaml)
    n_components: int = 0                 # number of active (non-missing, non-stale) components
    retained_weight: Optional[float] = None  # fraction of total weight that is active (0–1)
    low_coverage: bool = False            # True when retained_weight < config coverage.min_retained_weight

    # Per-component Z-scores (stored for auditability and dashboard decomposition)
    z_gov_household_debt_gdp: Optional[float] = None
    z_corporate_debt_gdp: Optional[float] = None
    z_household_debt_service: Optional[float] = None
    z_federal_interest_gdp: Optional[float] = None
    z_primary_balance_gdp: Optional[float] = None
    z_structural_balance: Optional[float] = None
    z_govt_revenue_gdp: Optional[float] = None

    # Per-component raw level values (stored for auditability)
    val_gov_household_debt_gdp: Optional[float] = None
    val_corporate_debt_gdp: Optional[float] = None
    val_household_debt_service: Optional[float] = None
    val_federal_interest_gdp: Optional[float] = None
    val_primary_balance_gdp: Optional[float] = None
    val_structural_balance: Optional[float] = None
    val_govt_revenue_gdp: Optional[float] = None

    # Components whose last raw observation predates the snapshot quarter.
    # Stored as "cid:excess_lag_q" (e.g. "gov_household_debt_gdp:2") so the
    # display layer can show both the component name and the lag in quarters.
    # These are included in the score (with decayed weight) but flagged in UI.
    stale_components: list[str] = Field(default_factory=list)

    # Components whose Z-score was model-estimated (rolling mean or linear trend)
    # because the raw value was older than max_carry_quarters.
    # Stored as "cid:excess_lag_q". Only populated when extrapolation is enabled.
    extrapolated_components: list[str] = Field(default_factory=list)
