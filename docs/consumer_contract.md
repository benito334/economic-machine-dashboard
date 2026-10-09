# Consumer Contract — reading `signals.duckdb` from another project

For anyone building on this database from outside the repo. Written 2026-10-07
after the CreovaOne beta work had to reverse-engineer the weighting from a live
`weight_audit` row.

Open the DB **read-only**. It is single-writer: the pipeline needs exclusive
access, and a second writer will block it.

```python
con = duckdb.connect("/mnt/data/db/finance/indicators_machine/signals.duckdb",
                     read_only=True)
```

---

## The one thing to get right

**`composites` is not point-in-time. `composites_pit` is.**

| | `composites` | `composites_pit` |
| :--- | :--- | :--- |
| Z-score window | each series' **full history** | **expanding, shift(1)** — only data strictly before each month |
| A row dated 2010 is scored against | data through **today** | data through **2010** |
| Rewritten under the current rule each run | yes, deliberately | yes |
| Use it for | reading the machine; current state; charts | **anything fitted across time** |

`composites` is recomputed in full on every run so that all of history is read
through one consistent lens. That is intentional and is not changing — when a
threshold or weight changes, you want the whole history re-read, not a patchwork
of retired rules.

What it cannot also be is as-known-at-the-time. A 2010 `growth_score` is
measured against a mean and standard deviation computed over 1968–2026; that
reading could not have existed in 2010. Harmless for a dashboard. **Look-ahead
bias for any model where month *t*'s regressor explains month *t*'s return.**

How far apart they are, measured on US data 2026-10-07:

| | correlation | sign disagreement |
| :--- | ---: | ---: |
| growth level | 0.942 | 14.6% of months |
| inflation level | **0.654** | **24.5% of months** |
| growth, first-differenced | 0.887 | 16.2% |
| inflation, first-differenced | 0.840 | 14.4% |

**If you are fitting betas, regressions, or any rolling refit, read
`composites_pit`.** If you want the dashboard's own numbers, read `composites`.

Neither is vintage-corrected: both score **final-revised** observations. Data
revisions (BEA restating GDP, BLS restating payrolls) are a third, separate
effect. `indicators/backtest_g3.py` replays true ALFRED vintages for the 16/19
US growth and 6/9 inflation signals that have them, and `history.duckdb`
(`indicators/vintage_store.py`) accumulates real vintages going forward.

---

## Knowing when the methodology moved

Both tables carry two stamps:

| column | what it is |
| :--- | :--- |
| `methodology_version` | manual, bumped when a formula or rule changes. Keyed to the Methodology page's §15 revision log. |
| `config_hash` | automatic digest of the weight/policy config. Catches a weight edited through the importance editor or a GDP-regression recalibration — neither touches a version string. |

If your refit moves and **both stamps are unchanged**, the world changed. If a
stamp changed, we did. `weight_change_log` holds the per-signal detail of every
importance change, with reason and source.

---

## Column notes that have already caught someone out

**`*_momentum` was renamed to `*_breadth` (2026-10-07) — migrate when you can.**
These columns are the *fraction of contributing signals moving in the force's
positive direction*, never a rate of change. The old name read as a first
difference, which is a genuinely different quantity this project also publishes
(the MoM delta of the score, shown on the regime card as "Momentum (Δ MoM)").

```sql
-- canonical
growth_breadth, inflation_breadth, rate_breadth,
credit_breadth, volatility_breadth, productivity_breadth

-- DEPRECATED mirror, identical values, still written every run
growth_momentum, inflation_momentum, rate_momentum,
credit_momentum, volatility_momentum, productivity_momentum
```

Both names are populated for **all history** — the new columns were backfilled
from the old at migration, so there is no transition gap and nothing breaks on
the next pipeline run. The mirror will be dropped only once consumers confirm
they have migrated; it is not on a timer.

If you want "how much did the composite move", difference the score yourself —
or better, read `composites_pit` and difference that.

**`confidence` was REDEFINED on 2026-10-07 — not renamed, redefined.** It now
carries **Chip Direction Agreement**: the share of the basket moving with the
chip's heading (the sign of the composite's MoM delta), invert-aware, over the
signals that actually build the composite. Two new columns expose it per force:

```sql
growth_dir_agreement, inflation_dir_agreement   -- confidence = mean of these
```

It previously measured agreement with the four-season **quadrant**, derived from
a raw `score >= 0` sign split that ignored thresholds entirely — a rule this
project retired in July 2026 when the seasons became display-only. Historical
values therefore CHANGED; `methodology_version` moved to `2026.10.07` to say so.
If you were reading `confidence`, re-read it.

**The inflation CHIP changed on 2026-10-08 — but the composite columns did not.**
The displayed Inflation / Transition / Disinflation chip is now gated on
**distance from the central bank's target** (`indicators.inflation_anchor.gap_series`,
beyond ±`bands.tolerance_pp`, sustained), not on `inflation_score`'s relative
Z. The momentum gate is retired. `growth_score` / `inflation_score` in both
composite tables are **unchanged in value** — if you fit betas to those
columns, nothing moves. What changes is any consumer that was reproducing the
chip, and `validator_verdicts`, which grades the chip.

Growth is deliberately NOT symmetric: it stays relative-Z, because growth has
no natural "right" level and inflation has a target (Ray, 2026-10-03). See
`docs/Guidance/regime_state_vs_environment_2026-10-08.md`.

⚠ **Still pending and NOT in this change:** re-anchoring has no effect on the
composite series today because the anchor runs alongside, not inside, the
composite. If the inflation *composite* is ever rebuilt around the target, the
continuous series moves and **every fitted beta moves with it** — that change
must land before any beta recalibration, not after.

**Four countries' inflation composite is too flat to fit a beta to.** Measured
over the last 10 years of `composites_pit`, `inflation_score` standard deviation:

| country | sd | |
| :--- | ---: | :--- |
| BR | **0.016** | unusable |
| MX | **0.050** | unusable |
| ID | **0.101** | unusable |
| CN | **0.177** | unusable |
| everyone else | 0.36 – 1.63 | fine |

Those four run on an annual IMF bridge that is forward-filled into a near-flat
line, so the series has months but almost no information. A regression will
still return a coefficient; it will be meaningless. **Skip the inflation leg
for BR / MX / ID / CN, or mark those assets unclassified on that axis.** Growth
is fine for all 14. `indicators.backtest.composite_variance_flags()` computes
this, and the Regime Validator page shows it next to the episode counts.

The regime CHIP for those countries is *not* affected — it is gated on distance
from target, not on this Z — so do not infer from a healthy chip that the
composite behind it is fittable.

**`signals.surprise` is now POPULATED (2026-10-08) — read the naming caveat.**
It was 0 non-null of 368,225 rows until this date. It now carries
`(realized − expectation) / sigma`, per signal, with sigma an expanding
standard deviation shifted one period so a month is never scaled by a spread
that had not happened yet. Null for the first 24 observations of a series by
design, rather than scaled off three data points.

⚠ **The expectation is a random walk for almost every signal, so on those this
is a standardised CHANGE, not a surprise against what the market discounted.**
Ray conceded the point directly when pressed (2026-10-07 Ruling 4): *"In the
absence of true forecasts, the label is technically a misnomer. It is still a
change measure."* What it genuinely buys over differencing the composite
yourself is per-signal standardisation — one high-volatility component cannot
dominate — and explicit missing-data renormalisation. A published forecast
drops into the same slot per signal when one exists; SPF covers US GDP growth
and CPI and is not yet wired.

It was built only after Ray's own decision test passed, on **non-overlapping
monthly returns**: incremental R² over ΔComposite was 0.019 for long bonds
(F = 5.05, p = 0.007) and 0.082 for equity (F = 5.35, p = 0.006), against his
≥ 0.01 bar. Gold did not clear it (0.005, p = 0.34), so do not expect it to
help on every asset.

**`low_coverage`** marks months with too few active signals. For the US these
are a contiguous block, 1980-01 to 1990-11 — dropping them leaves **no interior
gaps**, so first-differencing across the survivors is safe. That is a property of
today's data, not a guarantee; assert on it if you difference.

**Rolling windows.** `growth_score_48m` and `inflation_score_90m` are the
canonical ones (Ray audit ruling 2026-07-06) and are what the dashboard shows by
default. They are **trailing** windows, so they already carry far less
look-ahead than the base columns — a cheap partial fix if you cannot move to
`composites_pit` immediately. They are still revised-data and still recomputed
on a methodology change.

**Joining the two composite tables.** `composites` stamps the in-progress month
with today's date (e.g. `2026-10-07`); `composites_pit` only emits completed
month-ends (`2026-09-30`). Join on year-month, not on the raw date, and expect
`composites_pit` to lag by the current partial month.

**Early months are legitimately absent from `composites_pit`.** The expanding
window needs 36 observations before it produces anything, so every country's
first few years are empty rather than null-filled.

---

## How a score is built

For each signal: transform (YoY / level / spread) → Z-score → weight. The weight
is `base_share × importance × quality_factor`, tilted by a momentum-agreement
multiplier and decayed by a per-signal `half_life_months` once the observation is
overdue relative to its own release schedule. Weights renormalize over whichever
signals are active that month.

Every composite row carries the full per-signal audit for that month as JSON in
`weight_audit` — nominal weight, momentum multiplier, decay fraction, effective
weight. Read that rather than inferring the weighting.

Full methodology: the dashboard's Methodology page, or `docs/project_plan.md`.

---

## Stability

| | |
| :--- | :--- |
| Stable | table names, column names, `(country, as_of)` keys, the `Signal` contract |
| Recomputed every run | every value in `composites` and `composites_pit` |
| Deprecated | `*_momentum` (use `*_breadth`), `signals.surprise` |
| Redefined 2026-10-07 | `confidence` — now Chip Direction Agreement, see above |

Column removals get a deprecation cycle. Value changes do not — that is what the
stamps are for.
