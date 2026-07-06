# Ray-Framework Country Dashboard — Build Roadmap

Concrete, phased plan to evolve the current dashboard into the layered, Ray-Dalio-framework structure worked out during the 2026-07-05 review (see [ray_dalio_review_log.md](ray_dalio_review_log.md)). This is the "what to build and in what order" document; the *why* lives in the review log and CLAUDE.md.

**Scope boundary (unchanged):** this repo stays a *diagnostic* tool. The investment bridge / allocation logic (regime → asset-class returns, factor tilts, risk parity) is explicitly the separate Allocation Layer project and is **out of scope here** — it appears at the bottom of the roadmap only as a hand-off marker.

**Data rule (unchanged, from CLAUDE.md):** never invent series IDs. Any feed marked `⚠ VERIFY` must be confirmed against the provider's search/metadata endpoint before a binding is written. Effort tags: **S** = hours→1 day · **M** = a few days · **L** = a week+ · **R** = research spike (unknown until data is confirmed).

---

## The five-layer target architecture

```
L5  Investment bridge          regime → asset-class returns   (SEPARATE Allocation Layer — out of scope)
L4  Country position           two-dial regime · long-term-cycle stage · internal & external order
L3  Cycle positioning          productivity trend · short-term debt cycle · long-term debt cycle
L2  Force composites           growth · inflation · rate · credit · volatility   (basket → one weighted-Z each)
L1  Data & signal contract     free APIs · staleness/vintage discipline · minimum-viable set per country
```

The reframe vs. today: the 5 forces (L2) stop being the top-level story and become the raw material that tells you where a country sits on Ray's three clocks (L3), which synthesize into its overall position (L4).

## Current state (what's already built, by layer)

| Layer | Component | Status |
|---|---|---|
| L1 | Free-API ingestion, `Signal` contract, staleness/vintage, per-country minimum-viable sets | ✅ Built |
| L2 | Growth · Inflation · Rate · Credit · Volatility basket composites | ✅ Built (Volatility added 2026-07-05) |
| L3 | Short-term debt cycle = the two-dial regime engine | ✅ Built |
| L3 | Long-term debt cycle = Debt Stress composite | ✅ Built — but no explicit *stage* label |
| L3 | Productivity trend | ⚠ Partial — signals exist but folded into the Growth basket, not a first-class read |
| L4 | Two-dial regime + dynamic thresholds | ✅ Built (2026-07-05) |
| L4 | Big-cycle / "order" dimension (internal + external order, reserve-currency status) | ❌ Not built — the main new frontier |
| — | Cross-country / relative-cycle view for diversification | ⚠ Partial — Global Overview table exists; no cycle-stage or correlation lens |
| L5 | Investment bridge | ⛔ Out of scope (separate project) |

---

## Build phases

### Phase A — Finish the force layer (close the open review items)  ·  Effort: S
- **A2 — Credit force demand side.** ✅ **Done 2026-07-05.** Added `credit.loan_demand` (`DRSDCILM`, SLOOS "Net % of Banks Reporting Stronger Demand for C&I Loans") to the US `credit_score` basket (STRONG, importance 0.65, not inverted), pairing with the existing supply-side `credit.lending_standards` (punch item #9). Ingests cleanly (139 quarterly obs 1991→2026); documented in Methodology §7.
- **A1 — Rate force forward guidance.** ✅ **Done 2026-07-05.** The assumed feed (`FEDTARMD` FOMC dot-plot) was found non-viable — it's a future-dated forecast snapshot with no Z-scoreable history. Put the three options (display-only readout / derived `yield_2y − fed_funds` / defer) back to Ray; he chose the **derived expected-policy-change signal** on his principle "money is made by identifying *change* rather than forecasting it" — the 2Y *level* tells you where rates are, the 2Y-minus-funds *spread* tells you where they're heading, a distinct forward-looking dimension. Built `policy.rate_expectations` (`yield_2y − fed_funds`, derived, 11,625 daily obs) into the US `rate_score` basket at CONTEXT tier (importance 0.45, inverted). Ray's caveat, honored: kept modest pending **Phase G backtest** validation of its incremental value over the 2Y level (if the backtest shows no lift, drop it — his fallback to option "defer").
- **DoD:** ✅ both done. Note the standing dependency: A1's weight/keep decision is revisited after Phase G.

### Phase B — Promote the productivity trend to a first-class read (L3)  ·  Effort: S–M
Ray treats productivity growth as one of the three big forces, distinct from the cyclical business cycle.
- **B1** — Build a `productivity_trend` read from the existing `growth.productivity` / `growth.tfp` / `growth.rnd_intensity` signals (they already feed the Growth basket after 2026-07-05; here they also get their own composite/panel).
- **B2** — New dashboard element: the long-run potential-growth trend line shown *against* cyclical growth, so "cyclically strong but trend-decelerating" is visible at a glance.
- **Data:** already ingested. **Deps:** none. **DoD:** a productivity-trend panel exists on the regime/overview page; documented in Methodology.

### Phase C — Long-term debt-cycle STAGE classifier (L3/L4)  ·  Effort: M
Debt Stress gives a *level*; Ray's framework wants a *stage* — where in the ~50–75yr cycle the country sits.
- **C1** — `indicators/debt_cycle_stage.py`: classify into stages (e.g. *early / mid — leveraging*, *top — debt-service squeeze*, *deleveraging*, *reflation*) from a small feature set: debt/GDP level + trajectory (rising/falling), debt-service ratio trend, real policy rate vs. real growth (the "is debt growing faster than income" test), and nominal-growth-minus-yield.
- **C2** — Dashboard "Long-term cycle" panel: current stage, the features driving it, and a historical stage timeline.
- **Data:** mostly already have (debt/GDP, debt-service ratio, real rate, real growth). **Deps:** benefits from Phase G backtesting to calibrate stage thresholds. **DoD:** stage label + timeline render; thresholds are config-driven and documented.

### Phase D — Big-cycle / "order" dimension (L4)  ·  Effort: L + R
The genuinely new capability Ray stresses for choosing *which* countries to diversify into: internal order (wealth/political stress) and external order (geopolitics, reserve-currency status). **Start with a research spike** — several of these have no clean free API.
- **D1 — Research spike (R):** confirm free feeds for each candidate before building. Known/likely:
  - Internal order — wealth gap: World Bank Gini `SI.POV.GINI` (annual, sparse) `⚠ VERIFY cadence/coverage`.
  - Internal order — political polarization / governance: WB WGI is deleted (see deferred items); alternatives V-Dem / Polity5 are academic annual datasets, not simple APIs `⚠ RESEARCH` (may need a manual bulk-load slot, like the EA current-account gap).
  - External order — external debt: WB `DT.DOD.DECT.CD` `⚠ VERIFY`.
  - External order — reserve-currency status: IMF COFER (currency composition of global reserves) — only meaningful for reserve-issuer countries (US/EZ/JP/GB); would be a *constructed* "share of global reserves in this currency" indicator `⚠ RESEARCH`.
  - External order — geopolitical risk: GPR index (Caldara–Iacoviello) is downloadable but not a clean free API `⚠ RESEARCH` (candidate manual-load slot).
- **D2 — Build the confirmed subset** as new lens(es) with the same basket → weighted-Z pattern; honestly flag deferred/empty slots (as done for WGI/Lens H).
- **D3 — Dashboard "Big-cycle position" panel.**
- **Deps:** research spike gates everything. **DoD:** whatever has a confirmed free feed is live; everything else is a documented deferred slot in the data-source wishlist.

### Phase E — Cross-country / relative-cycle view for diversification (L4 payoff)  ·  Effort: M
The point of the whole exercise for global investing: see which countries are at *different* cycle stages and are least correlated.
- **E1** — A relative view: each rolled-out country's short-term regime + long-term-cycle stage + big-cycle position side by side.
- **E2** — A cross-country regime-correlation matrix (are these economies actually uncorrelated?).
- **Data:** derived from existing per-country composites. **Deps:** more valuable after C and D exist; works with just the regime engine too. **DoD:** a cross-country page that answers "where can I diversify to that isn't moving with the US?"

### Phase F — Japan rollout (Phase 2 continuation)  ·  Effort: M
Validates the sparse-country patterns end to end.
- Create `config/countries/jp_bindings.yaml` + `jp_composites.yaml`; apply the documented minimum-viable Debt Stress subset; use the monthly-proxy Volatility pattern; honest `vintage_available` and human sign-off.
- **Deps:** none (can slot in anytime). **DoD:** JP appears across all pages with the same honesty flags as EZ/KR.

### Phase G — Backtesting engine (Phase 3)  ·  Effort: L
Highest-leverage validation. Ray's own emphasis: systematically test every change.
- Replay FRED vintages against named scenarios (1970s stagflation, 2008 GFC, 2020 COVID); confirm the regime classifier lands in the expected regime with no look-ahead bias.
- Crucially: **use this to validate whether the opt-in dynamic-threshold algorithm actually beats the fixed one** — right now that's unproven, and this decides whether dynamic becomes the default.
- Also calibrates Phase C's stage thresholds against history.
- **Deps:** none technically, but its output feeds C's calibration and the dynamic-vs-fixed decision. **DoD:** a reproducible backtest report per scenario + a dynamic-vs-fixed comparison.

### Phase H — Investment bridge  ·  ⛔ OUT OF SCOPE
Regime-conditional return models, factor-tilt overlays, dynamic risk budgeting, scenario stress-testing (Ray's 5-step roadmap, review-log #12). Belongs to the separate Allocation Layer project. Listed here only so the hand-off point is explicit.

---

## Recommended sequence

1. **Phase A** (quick wins, closes open review loops)
2. **Phase G — backtesting** (validate what we already have, incl. dynamic thresholds, before building more speculative layers)
3. **Phase B** (small, data already exists)
4. **Phase C** (long-term-cycle stage — calibrated against G's output)
5. **Phase D research spike** in parallel from here (it gates the biggest new capability; start the data hunt early)
6. **Phase E** (the diversification payoff view)
7. **Phase F — Japan** can slot in wherever there's a natural break (it's independent)
8. **Phase H** — separate project, whenever the diagnostic layer is trusted

Rationale for putting backtesting (G) second: we just shipped a dynamic-threshold algorithm that is entirely unvalidated against history. Building more layers on top of an unvalidated classifier compounds risk. Validate the core, then extend.

## Consolidated open data-research (feeds into Phase D and the wishlist)
Tracked in [data_source_wishlist.md](data_source_wishlist.md). The order layer is the most data-uncertain part of the whole roadmap — treat D1 as a genuine spike, not a formality.
- Wealth-gap (Gini), political-polarization/governance (post-WGI alternative), external debt, reserve-currency share (COFER), geopolitical-risk index.
- Plus the still-open force-layer wishlist items: MOVE-style bond vol, credit-spread vol, ECB/BoK loan-demand, daily EA/KR equity index, debt-service-to-consumption/investment denominators.

---

*Companion docs: [ray_dalio_review_log.md](ray_dalio_review_log.md) (the review + punch list this roadmap operationalizes), [data_source_wishlist.md](data_source_wishlist.md) (the data hunt), CLAUDE.md (locked paths, build rules, phase map).*
