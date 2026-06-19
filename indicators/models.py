from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel


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
    direction: Optional[str] = None  # rising | falling | flat
    equilibrium_estimate: Optional[float] = None
    distance_from_equilibrium: Optional[float] = None
    surprise: Optional[float] = None  # actual − consensus (if wired)
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
