# CreovaOne handoff — your box assignments are being made on noise

2026-10-08. Written against CreovaOne's actual code
(`backend/app/plugins/beta_estimators/ewma_shrinkage.py`,
`backend/app/services/macro_beta_service.py`).

Two items. **One is a live defect in your estimator that is affecting real box
assignments today. The other is a methodology change on our side that, after
checking your code, turns out not to affect you at all** — included so you don't
have to go and verify that yourself.

Prompted by your observation that gold does not look like it responds to
inflation and that long bonds do not look like they respond to falling growth.
The first of those is an artifact. The second is real.

---

## TL;DR

| # | What | Your action | Urgency |
| :-- | :--- | :--- | :--- |
| 1 | 12-month EWMA half-life leaves no statistical power; boxes are assigned off insignificant coefficients | Raise the half-life, or gate box assignment on significance | **High — affects allocation now** |
| 2 | Our `METHODOLOGY_VERSION` moved to `2026.10.08` | None. Verified against your code. | None |

---

## 1. The gold anomaly is your half-life, not gold

### What you are running

`DEFAULT_ESTIMATOR_SLUG = "ewma_shrinkage"`, `DEFAULT_HALF_LIFE_MONTHS = 12.0`.

A 12-month half-life over 428 months of overlap gives a **Kish effective sample
size of 34.6**. You are discarding about 92% of the information in the series,
against a relationship whose R² is roughly 0.02.

### What that does

Reproducing your estimator exactly (EWMA weights, standardized regressors, the
same `|β_growth|` vs `|β_inflation|` box rule), US, gold = FRED `IQ12260`, long
bond = 10y duration-approximation total return:

| half-life | n_eff | GOLD \|t\|growth | \|t\|infl | box axis | BOND \|t\|growth | \|t\|infl | box axis |
| ---: | ---: | ---: | ---: | :--- | ---: | ---: | :--- |
| **12m (yours)** | **35** | 0.86 | **0.00** | **growth** | 0.15 | 0.98 | inflation |
| 24m | 69 | 0.69 | 0.00 | growth | 0.09 | 1.12 | inflation |
| 36m | 104 | 0.71 | 0.06 | growth | 0.01 | 1.27 | inflation |
| 60m | 170 | 0.81 | 0.32 | growth | 0.12 | 1.58 | inflation |
| 120m | 291 | 0.97 | 1.01 | **inflation** | 0.38 | **2.09** | inflation |
| none (OLS) | 428 | 1.28 | **3.03** | **inflation** | 1.58 | **3.33** | inflation |

Three things to take from this.

**At your current setting, not one coefficient on either asset is
distinguishable from zero** — the largest |t| in that row is 0.98. Both assets
are nonetheless being assigned to boxes, by comparing two numbers that are both
statistically indistinguishable from zero against each other.

**Gold's inflation beta at a 12-month half-life is literally +0.0000 (t = 0.00).**
Over full history the same asset reads **+0.0063, t = 3.03** — significant, correctly
signed, and it lands in Rising Inflation, the textbook box. The "gold does not
hedge inflation" finding is the estimator failing to see, not gold failing to
respond.

**Gold's box flips axis between a 60m and a 120m half-life.** That is the
parameter deciding the answer, not the data.

By contrast **long bonds come out Falling Inflation at every half-life and in
all eight other methodology variants we tested** (basis level/change/breakeven/
actual-CPI, 10y/20y windows, 1m/3m/12m horizons). Your read that long bonds are
not responding to falling growth is a real, stable finding: their growth beta is
weak everywhere and the discount-rate leg dominates. It just happens to be
getting the right answer by stability rather than by evidence at the current
setting, since even its inflation |t| is 0.98 there.

### Worth knowing: a weak monthly gold beta is the expected result

The published literature reports gold's inflation correlation as largely
insignificant at **2–32 month horizons**, becoming reliable only beyond roughly
ten years and conditional on regime. So a near-zero *monthly* gold beta should
not have been a surprise — the thing to question was the expectation that a
textbook box assignment would fall out of a monthly regression at all.

### The specific flaw, and the fix we would pick

Your credibility weight is

```python
weight = 1.0 / (1.0 + shrinkage_lambda / max(n_eff, 1e-9))     # ewma_shrinkage.py
```

which keys off **sample size only**. Two assets with the same `n_eff` get the
same shrinkage whether their beta is sharply estimated or pure noise. At
`n_eff = 34.6` and `λ = 24` that is `weight = 0.59` — you are putting 59% of
the published number on an estimate with a t of 0.00.

Three options, in our order of preference:

1. **Shrink on precision, not on count.** Key the credibility weight off the
   estimate's standard error (or equivalently its t) rather than `n_eff`. This
   keeps the time-varying intent of a short half-life while refusing to act on
   a coefficient the data cannot support. Smallest change, best behaviour.
2. **Gate the box assignment on significance.** Assign a box only when the
   winning |β| is distinguishable from zero and from the other axis; otherwise
   fall back to the peer prior or mark the asset unclassified. Compare
   confidence intervals, not point estimates — `|β_g|` vs `|β_i|` is only
   meaningful once both are estimated with some precision.
3. **Raise the half-life.** 120m gets the bond over |t| = 2 and flips gold to
   the correct axis; no decay at all gets both clearly significant. Simplest,
   but it gives up the time-variation the short half-life was chosen for.

A fourth thing worth doing regardless: **`shrink_toward_peers` passes
`t_growth` / `t_inflation` through unchanged from `own`**, so the t-stats you
publish describe the *unshrunk* estimate, not the blended number you actually
use. Anyone reading a beta and its t together is reading two different fits.

### One more, from the same investigation

Betas are **2–3× larger, and only significant, in the large-move tercile**:

| asset | small \|Δinfl\| | middle | large |
| :--- | ---: | ---: | ---: |
| GOLD β_infl | +0.0041 (t 1.24) | +0.0027 (t 0.82) | **+0.0090 (t 2.28)** |
| LT BOND β_infl | −0.0018 (t −1.13) | −0.0026 (t −1.49) | **−0.0059 (t −3.41)** |

Signs are stable across move sizes, so there is no separate "quiet" regime and
no case for a fifth box. But an all-months OLS estimates roughly **half** the
beta that applies in the months the box exists to hedge. Worth knowing when you
size a hedge off one of these numbers.

---

## 2. Our methodology version moved. You are unaffected — we checked.

`METHODOLOGY_VERSION` went `2026.10.07` → `2026.10.08`. The regime **chip** is
now gated on distance from the central bank's target rather than on the
inflation composite's own Z-score, and the momentum gate is retired.

**`composites_pit.growth_score` and `inflation_score` are unchanged in value.**
The anchor runs alongside the composite, not inside it. Your
`macro_surprise_series()` differences those two columns, so nothing you fit
moves.

We also checked the two places a chip change could have reached you:

- You do not read `validator_verdicts` anywhere in `backend/app/`.
- `aw_regimes.derive_from_sensitivity()` builds `aw_regime` from the asset's
  own sensitivity vector, not from our chip.

So: no action. The version bump is doing its job — telling you we moved, so you
can confirm it was not the world.

### ⚠ The one that will matter later

If we ever re-anchor the inflation **composite** itself to target — as opposed
to running the anchor alongside it, which is what shipped — **the continuous
series moves and every beta you have fitted moves with it.** That change has to
land before any beta recalibration on your side, never after. It is flagged in
`session-checklist.md` and in `docs/consumer_contract.md`; we will send a
handoff before it happens rather than after.

---

## Reproduction

Everything above is US-only and reproducible from `signals.duckdb` plus FRED.
Gold is `IQ12260` (monthly, 1984-12 →). The long bond is a duration
approximation, `−D·Δy + y/12` with D = 7.5, not a total-return index — fine for
ranking methodology variants against each other, not a substitute for your own
instrument data. Full working:
`docs/Guidance/beta_classification_audit_2026-10-08.md`.

The conceptual companion, worth ten minutes before changing anything here:
`docs/Guidance/regime_state_vs_environment_2026-10-08.md` — why our dashboard
says the economy is mostly in "Transition" while your four boxes cover 100% of
months, and why both are correct.
