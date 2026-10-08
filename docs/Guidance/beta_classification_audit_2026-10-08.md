# Is the regime classification good enough to fit asset betas on?

**Date:** 2026-10-08
**Question from the user:** two parts. (1) CreovaOne fits asset betas to our regime composites
to decide which All-Weather box each asset belongs in — gold looks like it is not responding to
inflation, long bonds look like they are not responding to falling growth. Is the classification
accurate enough to trust those betas? (2) If most months are "Transition" and beta has no
Transition bin, should All Weather allocate risk to transition?

**Short answer.** Q2 dissolves: the beta engine never sees the chip, and in the space it does
work in the four boxes are 100% exhaustive. Q1 does not dissolve: the betas are currently not
trustworthy, but **the cause is the estimator's 12-month half-life, not the regime
classification.**

---

## 1. What CreovaOne actually does

Traced through the code rather than assumed
(`backend/app/services/macro_beta_service.py`, `backend/app/plugins/beta_estimators/`):

- Reads **`composites_pit`** — the point-in-time table. Correct per `consumer_contract.md`.
- Default basis **`"change"`**: the month-over-month difference of the continuous growth and
  inflation composites. Also supports `"level"` and `"discounted_surprise"`.
- `fit_betas()` is a **standardized OLS of monthly excess return on the two continuous
  series**. Every overlapping month enters. There are no bins, no conditioning, no subsetting.
- Box assignment compares `|β_growth|` against `|β_inflation|`; the larger picks the axis, the
  sign picks the side.
- Production estimator is **`ewma_shrinkage`** (`DEFAULT_ESTIMATOR_SLUG`), **12-month
  half-life**, shrunk toward a peer-class average with `λ = 24`.

**The discrete chip is never read by any of this.** It is a display object.

---

## 2. Q2 — there is no "Transition" in the space the boxes partition

Our 8%-of-months figure comes from putting threshold bands on a **level** measure. The
All-Weather boxes partition the **sign of a change**, which has no band and therefore no middle.

Sign quadrants of (Δgrowth, Δinflation) on `composites_pit`, US, 512 months:

| box | months | share |
| :--- | ---: | ---: |
| Rising growth / Rising inflation | 135 | 26.4% |
| Rising growth / Falling inflation | 116 | 22.7% |
| Falling growth / Rising inflation | 131 | 25.6% |
| Falling growth / Falling inflation | 130 | 25.4% |
| **total** | **512** | **100%** |

Exhaustive, mutually exclusive, near-evenly populated. **Every month is already in a box.**
So "the regimes rarely happen" is not a fact about the allocation framework — it is a fact
about a threshold band we drew on a different object for display purposes.

### The legitimate version of the question

The real content of the intuition is about **magnitude**, not category: if most months are
quiet, is an all-months beta telling you what happens when it is not quiet? Tested by splitting
on the size of the monthly move:

| asset | \|Δinflation\| tercile | n | β_inflation | t |
| :--- | :--- | ---: | ---: | ---: |
| GOLD | small (quiet) | 143 | +0.0041 | 1.24 |
| GOLD | middle | 142 | +0.0027 | 0.82 |
| GOLD | **large (real moves)** | 143 | **+0.0090** | **2.28** |
| LT BOND | small (quiet) | 171 | −0.0018 | −1.13 |
| LT BOND | middle | 170 | −0.0026 | −1.49 |
| LT BOND | **large (real moves)** | 171 | **−0.0059** | **−3.41** |

**The sign is stable across move sizes; the magnitude is 2–3× larger in the large-move
tercile, and only there is it significant.** The same holds on the growth axis for LT bonds
(+0.0007 → −0.0023 → −0.0039, t = −2.35 in the large tercile).

So quiet months are not a different environment. They are the same relationship at a lower
signal-to-noise ratio. **Do not add a fifth bin — there is nothing distinct to allocate to.**
But note the practical consequence: an all-months OLS estimates roughly **half** the beta that
applies in the months the box exists to hedge.

---

## 3. Q1 — the betas are not trustworthy, and it is the half-life

A 12-month half-life gives a Kish effective sample size of **34.6 months** against 428 months
of available history — it discards ~92% of the information. Against a relationship whose R² is
about 0.02, that leaves no power. Reproducing the production estimator:

| asset | half-life | n obs | **n_eff** | β_growth | t | β_inflation | t | box |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| GOLD | **12m (production)** | 428 | **34.6** | −0.0112 | −0.86 | **+0.0000** | **0.00** | **FallingGrowth** |
| GOLD | 60m | 428 | 170.3 | −0.0040 | −0.81 | +0.0016 | 0.32 | FallingGrowth |
| GOLD | none (full OLS) | 428 | 428.0 | −0.0027 | −1.28 | **+0.0063** | **3.03** | **RisingInfl** |
| LT BOND | **12m (production)** | 512 | **34.6** | +0.0007 | 0.15 | −0.0046 | −0.98 | FallingInfl |
| LT BOND | 60m | 512 | 172.2 | −0.0002 | −0.12 | −0.0034 | −1.58 | FallingInfl |
| LT BOND | none (full OLS) | 512 | 512.0 | −0.0016 | −1.58 | **−0.0033** | **−3.33** | FallingInfl |

**This reproduces the reported anomaly exactly.** At the production half-life gold's inflation
beta is `+0.0000` with `t = 0.00` — literally no signal — and the box is then assigned off a
growth beta of `t = −0.86`, also noise. Over full history the same asset reads `+0.0063`,
`t = 3.03`, and lands in Rising Inflation, which is the textbook answer.

**Gold is not failing to respond to inflation. The estimator cannot see whether it does.**

### Does the box assignment survive the other methodology choices?

| variant | GOLD box | β_i | t | LT BOND box | β_i | t |
| :--- | :--- | ---: | ---: | :--- | ---: | ---: |
| basis=change, full, 1m | RisingInfl | +0.0064 | 3.03 | FallingInfl | −0.0033 | −3.33 |
| basis=level, full, 1m | **FallingGrowth** | +0.0023 | 1.11 | FallingInfl | −0.0028 | −2.82 |
| basis=discounted (Δbreakeven) | RisingInfl | +0.0055 | 2.16 | FallingInfl | −0.0100 | −9.82 |
| basis=actual CPI change | RisingInfl | +0.0043 | 2.07 | FallingInfl | −0.0042 | −4.18 |
| basis=change, last 10y | **FallingGrowth** | −0.0004 | −0.10 | FallingInfl | −0.0028 | −1.55 |
| basis=change, last 20y | RisingInfl | +0.0054 | 1.86 | FallingInfl | −0.0041 | −3.21 |
| basis=change, 3m horizon | RisingInfl | +0.0091 | 2.41 | FallingInfl | −0.0064 | −3.45 |
| basis=change, 12m horizon | **FallingInfl** | −0.0123 | −1.35 | FallingInfl | −0.0052 | −1.16 |

- **LT bonds: Falling Inflation in all eight variants.** Stable and robust. The user's
  observation that long bonds are not responding to *falling growth* is correct and is a real
  finding, not an artifact: the growth beta is weak everywhere and the discount-rate (inflation)
  leg dominates. Caveat: at the production half-life even this is `t = −0.98`, so production
  gets the right answer by stability, not by evidence.
- **Gold: the box flips three ways** across basis, window and horizon. It is not a stable
  classification under any reading.

### Independent check on gold

The published literature says a weak monthly gold-inflation relationship is the *expected*
result: correlations at horizons of **2–32 months are largely insignificant**, and gold's
hedge becomes reliable only at horizons beyond roughly ten years, conditional on regime. So a
near-zero monthly beta should not have been surprising — the error was expecting the textbook
box assignment to fall out of a monthly regression at all.

Our full-history monthly `+0.0064 / t = 3.03` is, if anything, *stronger* than that literature
would predict. One candidate explanation to rule out: **the inflation composite contains
market-priced components** — `inflation.breakeven_avg` (importance 0.30) and
`inflation.crude_oil` (0.10) out of 2.80 total, so roughly **14% of the basket is market
prices** moving contemporaneously with gold. For a macro-beta use case that is partly
regressing one asset on other asset prices.

---

## 4. What I would change

1. **Lengthen the half-life, or stop binning on insignificant coefficients.** 12 months
   (n_eff ≈ 35) cannot support a classification. 60 months gives n_eff ≈ 170. Either way,
   report the confidence interval and **refuse to assign a box when it spans zero** — today
   both gold and LT bonds are binned on coefficients that are not significant at the production
   setting.
2. **Decide the box on evidence, not just on `|β_g|` vs `|β_i|`.** That comparison is
   meaningful only once both coefficients are estimated with some precision; at n_eff = 35 it
   is comparing two noise draws.
3. **Consider fitting box betas on the large-move months**, which is the state the box exists
   to hedge — or at minimum record that the all-months beta understates the stress response
   by about half.
4. **Watch the market-priced content of the inflation composite** for this specific use. It is
   fine for reading the machine; it is partly circular for regressing asset returns.
5. **The basis question is still open.** Ray's 2026-10-07 ruling was "condition on the
   surprise"; `signals.surprise` remains 0 non-null of 368,225 rows, and the three available
   bases are all proxies for it.

   > **Corrected 2026-10-08, same day.** An earlier version of this line proposed promoting
   > `discounted_surprise` over `change` because it gave by far the strongest LT-bond fit
   > (`t = −9.82`, R² 0.261). **Withdrawn — that number is substantially mechanical.** The
   > bond return proxy is `−7.5·Δ(nominal 10y)` and breakeven = nominal − TIPS, so the two
   > share the `Δ(nominal 10y)` term; `corr(Δ nominal 10y, Δ breakeven) = 0.507`. On gold,
   > which has no such overlap, `discounted` (R² 0.018) does **not** beat `change`
   > (R² 0.022). There is no evidence here for changing the basis. The real upgrade is
   > building genuine realized-minus-consensus surprise — see
   > `regime_state_vs_environment_2026-10-08.md`.

**None of these are regime-classification problems.** The classification feeding the betas is
the continuous PIT composite, and it is doing its job; the chip and its Transition band are not
involved. The separate inflation-chip defects documented in
`ray_consult_regime_frequency_2026-10-08.md` affect the *displayed chip*, not the beta inputs —
with one exception worth tracking: if the inflation composite is re-anchored to target (Ray's
2026-10-03 Ruling 1), the **continuous series changes**, and every fitted beta moves with it.
Sequence that change before any beta recalibration, not after.

---

## Appendix — reproduction

Scripts in the session scratchpad: `beta1.py` (box population, baseline betas), `beta2.py`
(methodology sensitivity), `beta3.py` (production EWMA reproduction, n_eff), `beta4.py`
(move-size terciles). Gold is FRED `IQ12260` (monthly, 1984-12 → 2026-08). Long bond is the
10y duration-approximation total return from `indicators/backtest_g3.bond_monthly_returns`
(−D·Δy + y/12, D = 7.5) — a proxy, not an index. US only. Betas are standardized, so they read
as excess return per 1 SD of surprise.
