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

### Phase B — Promote the productivity trend to a first-class read (L3)  ·  Effort: S–M  ·  ✅ **Done 2026-07-05**
Ray treats productivity growth as one of the three big forces, distinct from the cyclical business cycle.
- **B1 ✅** — `productivity_score`/`productivity_momentum` composite added to the engine (same basket→weighted-Z pattern as every force; new DB columns + migration). US = 3 signals (labor productivity 0.80 / TFP 0.45 / R&D 0.30); EZ/KR = single-signal R&D-only (low-coverage, quality 0.70 — honestly ages out when the annual source lags).
- **B2 ✅** — "Productivity Trend" is now a sixth section on /signals plus a full force-detail page at /signals/productivity whose composite panel overlays the cyclical Growth Z (dotted) — "cyclically strong but trend-decelerating" visible at a glance. Documented in Methodology §7 + revision log.
- **DoD:** ✅ met (panel lives on the Signals pages rather than the regime page — the command-center card in Phase CC is the eventual front-door surface).

### Phase C — Long-term debt-cycle STAGE classifier (L3/L4)  ·  Effort: M  ·  ✅ **done 2026-07-05**
Debt Stress gives a *level*; Ray's framework wants a *stage* — where in the ~50–75yr cycle the country sits.
- **C1 ✅** — `indicators/debt_cycle_stage.py` + `config/debt_cycle_stage.yaml` (all thresholds/weights TUNABLE-annotated): stages *leveraging / squeeze / deleveraging / reflation / neutral* from a 5-feature vote — debt/GDP expanding percentile (shift-1, no look-ahead) + 3y trajectory, DSR 2y trend, real-rate-minus-real-growth, nominal-growth-minus-yield. Weighted-condition argmax with per-quarter renormalization over available features (EZ/KR run honestly on 4/5 — no free DSR), min-3-families gate, 3-quarter rolling-mode smoothing that never carries a label across a data gap. `debt_cycle_stage_snapshots` DuckDB table; pipeline Pass 7 (all configured countries); `DebtCycleStageSnapshot` model; 17 unit tests. US timeline sanity anchors hit: 1989–91 squeeze, 1992–95 reflation, 2007 pre-GFC squeeze, 2012–2020 reflation, 2020–23 COVID leveraging. Current: US=reflation, EZ=reflation, KR=leveraging.
- **C2 ✅** — Command Center Cycle Stage card is live (stage + confidence + n/5 features, stage-colored); Debt Stress page gained a Long-Term Cycle Stage section: current-stage chip + driving-feature readout + colored quarterly stage band + per-stage score chart. Methodology §9 subsection + revision-log row.
- **Data:** mostly already have (debt/GDP, debt-service ratio, real rate, real growth). **Deps:** threshold calibration against the PIT backtest is an explicit **G3 task**. **DoD:** ✅ met — stage label + timeline render for US/EZ/KR; thresholds config-driven and documented.

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

### Phase CC — Country command center (the front door)  ·  Effort: M  ·  ✅ **done 2026-07-05**
One synthesis page per country that answers "where is this country, on all three clocks, and what's changing" — with the existing detail pages demoted to drill-downs. Built around the handful of things Ray said actually matter: the two dials + the credit/rate *levers* (supply AND demand side, policy stance + expected path), the debt-service ratio as the earliest long-cycle signal, the productivity trend as the baseline, the growth/inflation divergence flag as the cycle-shift alarm, and change-over-level throughout.
- **CC1 ✅ — v1 from existing data (no new modeling):** `dashboard/command_center.py`, routes `/` (default landing) + `/country`, nav entry at the top of Overviews. Regime strip (chips + confidence + diseq + DYNAMIC badge when dynamic thresholds are on — honors the store's dynamic mode when classifying), short-cycle lever cards (Growth/Inflation dials with Δ + momentum, Credit supply `lending_standards` + demand `loan_demand`, Policy stance `rate_score` + `rate_expectations` hikes/hold/cuts read), Debt Stress card (score + n/7 components), DSR card (Z + % of income + direction), productivity-vs-cyclical-growth card (trend above/below cycle read), what-changed watch list (top-8 Z movers, reuses `load_change_feed` + `_what_changed_children`). Every card links to its detail page. The divergence flag is surfaced as an amber DIVERGENCE badge with an explanatory tooltip — **closes the open #23 follow-up**.
- **CC2 ✅ — placeholder cards** for the two unbuilt layers (long-term-cycle *stage* from Phase C, big-cycle *order* from Phase D), dashed-border + "planned"; they light up when those phases land.
- **Data:** all computed today (composites, regime, debt stress, divergence flag, what-changed). **Deps:** none for v1; C and D upgrade their cards later. **DoD:** ✅ met — `/` and `/country` render the command center for US/EZ/KR; every card drills down; divergence badge live; 8 unit tests (`tests/test_command_center.py`); Methodology §15 revision-log entry added.

### Phase E — Cross-country / relative-cycle view for diversification (L4 payoff)  ·  Effort: M
The point of the whole exercise for global investing: see which countries are at *different* cycle stages and are least correlated.
- **E1** — A relative view: each rolled-out country's short-term regime + long-term-cycle stage + big-cycle position side by side.
- **E2** — A cross-country regime-correlation matrix (are these economies actually uncorrelated?).
- **Data:** derived from existing per-country composites. **Deps:** more valuable after C and D exist; works with just the regime engine too. **DoD:** a cross-country page that answers "where can I diversify to that isn't moving with the US?"

### Phase F — Japan rollout (Phase 2 continuation)  ·  Effort: M
Validates the sparse-country patterns end to end.
- Create `config/countries/jp_bindings.yaml` + `jp_composites.yaml`; apply the documented minimum-viable Debt Stress subset; use the monthly-proxy Volatility pattern; honest `vintage_available` and human sign-off.
- **Deps:** none (can slot in anytime). **DoD:** JP appears across all pages with the same honesty flags as EZ/KR.

### Phase G — Backtesting engine (Phase 3)  ·  Effort: L  ·  **G1+G2 done 2026-07-05, G3 open**
Highest-leverage validation. Ray's own emphasis: systematically test every change. Staged:
- **G1 ✅ — point-in-time engine** (`indicators/backtest.py`): expanding-window shift(1) Z-scores so the classifier at month t uses only data available before t — eliminates *statistical* look-ahead. 36-month warm-up; scored era 1983→2026 (559 months). Data starts 1980-81, so no 1970s scenario is possible; 8 named scenarios from the 1990-91 recession through the 2023 disinflation. Run via `python -m indicators.backtest`; reproducible report at `docs/backtests/pit_regime_backtest_us.md`; 9 unit tests.
- **G2 ✅ — scenario scoring + fixed-vs-dynamic comparison.** Findings:
  1. **Direction validation passed.** With zero look-ahead, wrong-direction labels ≈ 0% in every scenario (single exception: 1 month of "Inflation" during the gradual 2023 cooling). The classifier lands on the correct side of every bust, boom, and inflation episode since 1983.
  2. **Dynamic ≥ fixed.** Dynamic won 2 scenarios outright (1990-91 recession strict 50%→88%; late-90s boom 33%→54%) and tied the other 6, at the cost of one mislabeled month in 48 during the boom (+2% wrong). Mechanism: the country-vol-scaled baseline sets thresholds well below the flat 0.5 in low-volatility eras, giving more decisive labels. **Verdict: supportive of dynamic, not yet conclusive — keep it opt-in; revisit the default after G3** (only 8 scenarios, final-revised data).
  3. **Design insight — the momentum gate dominates strict scores.** In fast V-shaped episodes (COVID: 33% strict) the ΔMoM gate flips positive during the rebound while Z is still deeply negative, parking months in Transition. If "still-in-recession persistence" is ever wanted, the *exit* condition needs asymmetry (e.g. require Z to recross, not just delta to flip) — logged as a future refinement candidate, possibly one to put to Ray.
  4. 2023 disinflation scoring 0% strict is *correct* semantics: cooling from a high level ≠ below-average inflation, so Transition is the right chip.
- **G3 ⬜ — remaining:** ALFRED vintage replay (data as known at the time — eliminates data-*revision* look-ahead); asset-outcome predictive tests (incl. Ray's suggested validation of `rate_expectations` against bond/credit outcomes, which decides whether that signal keeps its slot); Phase C stage-threshold calibration.
- **DoD:** ✅ reproducible per-scenario report + dynamic-vs-fixed comparison exist. G3 items tracked above.

### Phase H — Investment bridge  ·  ⛔ OUT OF SCOPE
Regime-conditional return models, factor-tilt overlays, dynamic risk budgeting, scenario stress-testing (Ray's 5-step roadmap, review-log #12). Belongs to the separate Allocation Layer project. Listed here only so the hand-off point is explicit.

---

## Recommended sequence

1. **Phase A** ✅ done (quick wins, closed the open review loops)
2. **Phase G — backtesting** (validate what we already have, incl. dynamic thresholds, before building more speculative layers)
3. **Phase B** (small, data already exists; feeds the command center's productivity card)
4. **Phase CC — command center v1** ✅ done 2026-07-05 (assembly-only; placeholder cards for C/D)
5. **Phase C** ✅ done 2026-07-05 (long-term-cycle stage classifier; upgraded its CC card; threshold calibration deferred to G3)
6. **Phase D research spike** in parallel from here (it gates the biggest new capability; start the data hunt early)
7. **Phase E** (the diversification payoff view)
8. **Phase F — Japan** can slot in wherever there's a natural break (it's independent)
9. **Phase H** — separate project, whenever the diagnostic layer is trusted

Note: CC v1 is presentation-layer only (no new modeling risk), so it can be pulled forward ahead of G at any time without violating the validate-before-extend rationale.

Rationale for putting backtesting (G) second: we just shipped a dynamic-threshold algorithm that is entirely unvalidated against history. Building more layers on top of an unvalidated classifier compounds risk. Validate the core, then extend.

## Consolidated open data-research (feeds into Phase D and the wishlist)
Tracked in [data_source_wishlist.md](data_source_wishlist.md). The order layer is the most data-uncertain part of the whole roadmap — treat D1 as a genuine spike, not a formality.
- Wealth-gap (Gini), political-polarization/governance (post-WGI alternative), external debt, reserve-currency share (COFER), geopolitical-risk index.
- Plus the still-open force-layer wishlist items: MOVE-style bond vol, credit-spread vol, ECB/BoK loan-demand, daily EA/KR equity index, debt-service-to-consumption/investment denominators.

---

*Companion docs: [ray_dalio_review_log.md](ray_dalio_review_log.md) (the review + punch list this roadmap operationalizes), [data_source_wishlist.md](data_source_wishlist.md) (the data hunt), CLAUDE.md (locked paths, build rules, phase map).*
