"""Cross-country panel tests — and an honest count of what pooling buys.

Checklist item 9, from the Ray consult of 2026-10-08. Shown that the US
inflation chip had fired in essentially one macro episode in 43 years, he set
a bar of 10-15 independent occurrences "tested across different time periods
**and countries**". Pooling the 14-country panel was the obvious way to get
there.

The point of this module is that **pooling buys far less than it appears to**,
and saying so is the deliverable. Country-months are not independent
observations: macro cycles and bond markets co-move. Measured on live data
(2026-10-09):

    mean pairwise corr of monthly bond returns      +0.42  ->  2.1 of 11
    mean pairwise corr of d(growth composite)       +0.19  ->  3.8 of 11

So eleven countries are worth two to four, not eleven. Anyone quoting a
pooled t-statistic computed on ~5,000 country-months is overstating their
evidence by roughly the square root of five.

Nothing here conditions on overlapping forward windows. The 2026-10-08 audit
found that overlapping windows were inflating significance badly elsewhere in
this repo, so the panel tests use plain monthly returns.
"""
from __future__ import annotations

import logging

import duckdb
import numpy as np
import pandas as pd

from store.store import DB_PATH

logger = logging.getLogger(__name__)

# Duration approximation for a 10y government bond total return:
#   r_t ≈ −D·Δy_t + y_{t-1}/12
# The same D the G3 backtest uses, so the two are comparable. This is a proxy,
# not an index — fine for ranking specifications against each other, not a
# substitute for real instrument data.
BOND_DURATION = 7.5

# Countries carrying a usable 10y yield. BR, CN and ID are excluded: they have
# only short rates, so there is no long-bond return to build.
PANEL_COUNTRIES = ("US", "EZ", "GB", "JP", "KR", "IN", "DE", "LU", "CA", "AU", "MX")

MIN_MONTHS = 60


def _conn(conn=None):
    return conn or duckdb.connect(str(DB_PATH), read_only=True)


def country_bond_returns(country: str, conn=None) -> pd.Series:
    """Monthly 10y bond total-return proxy for one country, as a fraction."""
    own = conn is None
    c = _conn(conn)
    try:
        df = c.execute(
            "SELECT as_of, value FROM signals WHERE id = ? AND value IS NOT NULL "
            "ORDER BY as_of", [f"{country.lower()}.policy.yield_10y"],
        ).df()
    finally:
        if own:
            c.close()
    if df.empty:
        return pd.Series(dtype=float)
    y = pd.Series(df["value"].values, index=pd.to_datetime(df["as_of"]))
    y = y.resample("ME").last().dropna()
    if len(y) < MIN_MONTHS:
        return pd.Series(dtype=float)
    return ((-BOND_DURATION * y.diff() + y.shift(1) / 12.0) / 100.0).dropna()


def effective_independent_n(panel: pd.DataFrame) -> dict:
    """How many genuinely independent series a correlated panel is worth.

    The standard design-effect correction for equicorrelated units:

        N_eff = N / (1 + (N - 1) * rho_bar)

    `rho_bar` is the mean off-diagonal pairwise correlation. With N = 11 and
    rho_bar = 0.42 this returns 2.1 — which is the whole reason this function
    exists rather than a bare count of countries.
    """
    cols = [c for c in panel.columns if panel[c].notna().sum() >= MIN_MONTHS]
    if len(cols) < 2:
        return {"n": len(cols), "rho_bar": None, "n_eff": float(len(cols))}
    corr = panel[cols].corr()
    off = corr.values[np.triu_indices_from(corr.values, 1)]
    rho = float(np.nanmean(off))
    n = len(cols)
    denom = 1.0 + (n - 1) * rho
    n_eff = n / denom if denom > 0 else float(n)
    return {"n": n, "rho_bar": round(rho, 4), "n_eff": round(float(n_eff), 2)}


def build_panel(conn=None, countries: "tuple[str, ...]" = PANEL_COUNTRIES) -> dict:
    """{'returns': DataFrame, 'dgrowth': DataFrame, 'dinflation': DataFrame}.

    All month-end indexed, one column per country. Composite changes come from
    `composites_pit` — the point-in-time series, per docs/consumer_contract.md,
    because this is a fit across time.
    """
    own = conn is None
    c = _conn(conn)
    try:
        rets, dg, di = {}, {}, {}
        for cc in countries:
            r = country_bond_returns(cc, conn=c)
            if r.empty:
                continue
            rets[cc] = r
            df = c.execute(
                "SELECT as_of, growth_score, inflation_score FROM composites_pit "
                "WHERE country = ? ORDER BY as_of", [cc],
            ).df()
            if df.empty:
                continue
            idx = pd.to_datetime(df["as_of"])
            dg[cc] = pd.Series(df["growth_score"].values, index=idx).diff()
            di[cc] = pd.Series(df["inflation_score"].values, index=idx).diff()
    finally:
        if own:
            c.close()
    return {"returns": pd.DataFrame(rets),
            "dgrowth": pd.DataFrame(dg),
            "dinflation": pd.DataFrame(di)}


def pooled_regression(panel: dict) -> dict:
    """Pool the macro-change → bond-return regression across countries.

    Country fixed effects (demeaning per country), monthly returns so there is
    no window overlap, and **both** the naive t-statistic and one corrected for
    cross-sectional dependence. The naive one is what a reader would compute
    and is wrong; the corrected one divides the effective sample by the design
    effect measured on the same panel.
    """
    R, G, I = panel["returns"], panel["dgrowth"], panel["dinflation"]
    rows = []
    for cc in R.columns:
        if cc not in G.columns or cc not in I.columns:
            continue
        j = pd.concat([R[cc].rename("y"), G[cc].rename("g"), I[cc].rename("i")],
                      axis=1).dropna()
        if len(j) < MIN_MONTHS:
            continue
        # country fixed effects: demean each country's own columns
        for col in ("y", "g", "i"):
            j[col] = j[col] - j[col].mean()
        j["country"] = cc
        rows.append(j)
    if not rows:
        return {"error": "no country had enough overlap"}
    d = pd.concat(rows)
    n = len(d)
    X = np.column_stack([np.ones(n), d["g"].values, d["i"].values])
    b, _, _, _ = np.linalg.lstsq(X, d["y"].values, rcond=None)
    resid = d["y"].values - X @ b
    dof = n - X.shape[1]
    se = np.sqrt(np.diag(np.linalg.pinv(X.T @ X)) * (resid @ resid / dof))
    r2 = 1 - (resid @ resid) / float(((d["y"] - d["y"].mean()) ** 2).sum())

    eff = effective_independent_n(R)
    # Scale the standard errors by sqrt(design effect): the pooled sample is
    # worth n * (n_eff / n_countries) independent observations, not n.
    shrink = (eff["n"] / eff["n_eff"]) if eff["n_eff"] else 1.0
    se_adj = se * np.sqrt(shrink)
    return {
        "country_months": int(n),
        "countries": int(len(rows)),
        "effective_countries": eff["n_eff"],
        "rho_bar": eff["rho_bar"],
        "effective_country_months": int(round(n / shrink)),
        "r2": round(float(r2), 5),
        "beta_growth": round(float(b[1]), 5),
        "beta_inflation": round(float(b[2]), 5),
        "t_growth_naive": round(float(b[1] / se[1]), 2),
        "t_inflation_naive": round(float(b[2] / se[2]), 2),
        "t_growth_adjusted": round(float(b[1] / se_adj[1]), 2),
        "t_inflation_adjusted": round(float(b[2] / se_adj[2]), 2),
    }
