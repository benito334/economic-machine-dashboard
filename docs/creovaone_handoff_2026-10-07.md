# CreovaOne handoff — what changed in the feed, and what to do about it

2026-10-07. Written against CreovaOne's actual adapter
(`backend/app/plugins/macro/indicators_machine.py`) and `macro_beta_service.py`.

Everything below is live in `signals.duckdb` now. Nothing you currently read has
been removed, and nothing breaks if you deploy no changes today — but **one of
your reads is silently wrong, and one has changed meaning.**

---

## TL;DR — three changes, in priority order

| # | What | Your action | Urgency |
| :-- | :--- | :--- | :--- |
| 1 | `composites_pit` — a new point-in-time composite series | Switch `_COMPOSITE_HISTORY_SQL` to it | **High** — your backfilled betas have look-ahead bias today |
| 2 | `confidence` **redefined** (not renamed) | Re-read it, or stop reading it | Medium — values changed |
| 3 | `*_momentum` → `*_breadth` | Rename in 2 queries; old names still work | Low — mirror is written |

Plus: both composite tables now carry `methodology_version` + `config_hash`, so
you can finally tell "the world moved" from "the Indicators Machine moved".

---

## 1. Your beta fit has look-ahead bias. Use `composites_pit`.

### The problem

`composites.growth_score` / `inflation_score` are Z-scored against **each
series' full history** — a deliberate design choice, stated outright in
`indicators/normalize.py`:

> Z-scores and percentiles are computed against the *full* series history (not
> expanding). This is appropriate for Phase 1A display.

So the March 2010 `growth_score` is measured against a mean and standard
deviation computed over 1968–2026. **That reading could not have existed in
2010.** It needs 2015's and 2023's observations to compute the baseline it is
measured against.

Harmless for a dashboard. For `macro_beta_service.py`, where month *t*'s
regressor explains month *t*'s excess return, it is look-ahead bias — the
regressor contains information from the future of the fit window. Your
"no-lookahead rolling refits" are not currently no-lookahead.

### How big

Measured against the point-in-time engine, US:

| | correlation | sign disagreement |
| :--- | ---: | ---: |
| growth level | 0.942 | 14.6% of months |
| **inflation level** | **0.654** | **24.5% of months** |
| growth, first-differenced (your `basis="change"`) | 0.887 | 16.2% |
| inflation, first-differenced | 0.840 | 14.4% |

Inflation is the bad one. A quarter of your historical inflation observations
have the **wrong sign** relative to what was knowable at the time.

### What is NOT the problem

To be explicit, because this came up: **we recompute all of history under the
current rule on every pipeline run, and that is correct and is not changing.**
When a threshold or weight changes, you want the whole history re-read through
one consistent lens, not a patchwork of retired rules. That is a different thing
from the full-history Z-score, and only the latter is a defect.

There is a third, separate effect — **data revisions** (BEA restating GDP, BLS
restating payrolls). `composites_pit` does NOT fix that; it scores final-revised
observations point-in-time. True vintage replay exists for the 16/19 US growth
and 6/9 inflation signals with ALFRED coverage
(`indicators/backtest_g3.py`), and `history.duckdb` accumulates real vintages
going forward. Say the word if you want that surfaced as a third series.

### The fix — drop-in replacement for `_COMPOSITE_HISTORY_SQL`

`composites_pit` carries the same baskets and the same weights, with
expanding-window `shift(1)` Z-scores. It does not carry `low_coverage` /
`quadrant` (those are coverage and labelling facts, unaffected by the Z window),
so join back to `composites` for them:

```sql
SELECT p.as_of,
       p.growth_score, p.inflation_score,
       c.low_coverage, c.quadrant,
       c.growth_dir_agreement, c.inflation_dir_agreement,
       p.methodology_version, p.config_hash
FROM composites_pit p
JOIN composites c
  ON c.country = p.country
 AND date_trunc('month', c.as_of) = date_trunc('month', p.as_of)
WHERE p.country = ?
  AND p.growth_score IS NOT NULL
  AND p.inflation_score IS NOT NULL
ORDER BY p.as_of ASC
```

Verified against live US data: **513 rows, 1984-01 → 2026-09, 430 usable after
dropping `low_coverage`.** (Your current query returns more rows because
`composites` starts in 1980; the expanding window needs 36 observations before
it produces anything, so the first years are legitimately absent rather than
null-filled.)

Three things to know about that join:

- **Join on year-month, not raw date.** `composites` stamps the in-progress
  month with today's date (`2026-10-07`); `composites_pit` only emits completed
  month-ends (`2026-09-30`). A raw-date join silently drops the current month.
- You can drop your `QUALIFY row_number() … ORDER BY created_at DESC` dedup if
  you want — both tables are upserted in place on `(country, as_of)`, so there
  is exactly one row per key. Harmless to keep.
- `composites_pit` also carries `credit_score`, point-in-time, if useful.

### Cheaper interim, if you cannot move this week

Switch to `growth_score_48m` / `inflation_score_90m` on the existing table.
Those are **trailing** rolling windows (the canonical ones, and what the
dashboard shows by default), so the look-ahead is largely gone for a one-line
change. They are still revised-data and still recomputed on a methodology
change, so it is a mitigation, not the fix.

---

## 2. `confidence` was redefined. Re-read it or drop it.

You select `confidence` in `_COMPOSITE_SQL`, `_COMPOSITE_ALL_SQL` and
`_COMPOSITE_HISTORY_SQL`. You told us it does not feed the regression — good,
because its values changed today.

**It used to measure** agreement with the four-season **quadrant**, with each
signal's expected direction taken from a raw `growth_score >= 0` sign split that
ignored the regime thresholds entirely. That rule was retired in July 2026 when
the four seasons became display-only map geography. The column was computing a
classification this project no longer uses.

**It now carries Chip Direction Agreement**: the share of the basket moving with
the chip's heading (the sign of the composite's MoM delta), invert-aware, over
the signals that actually build the composite. Two new columns expose it per
force, and `confidence` is their mean:

```sql
growth_dir_agreement, inflation_dir_agreement
```

Live US moved from 50% / 50% to **29% / 33%** — because the old number was
computed over the wrong population (every signal tagged `force='growth'`, 19 for
the US, rather than the 12 that build the composite) and never flipped inverted
signals, so a *falling* unemployment rate counted as disagreeing with a *rising*
growth chip.

`methodology_version` moved to `2026.10.07` to mark it.

**On your open question of whether to weight the regression by it:** our
recommendation is still no. It is a breadth/agreement measure, not an estimate
of the score's variance, and weighted least squares wants the latter. If you
want to down-weight unreliable months, `low_coverage` (which you already drop)
and the signal counts are better-founded. Worth noting the worst-coverage era is
contiguous — US `low_coverage` runs 1980-01 to 1990-11 — and you already exclude
it, so the marginal gain is small either way.

---

## 3. `*_momentum` → `*_breadth`

These columns are the **share of contributing signals moving in the force's
positive direction**. They were never a rate of change. The old name collided
with a genuine momentum this project also publishes (the MoM delta of the score,
shown on the regime card as "Momentum (Δ MoM)") — which is exactly the confusion
that nearly had you fitting betas to it.

```sql
-- canonical
growth_breadth, inflation_breadth, rate_breadth,
credit_breadth, volatility_breadth, productivity_breadth

-- DEPRECATED mirror: identical values, still written every run
growth_momentum, inflation_momentum, …
```

Affects `_COMPOSITE_SQL` and `_COMPOSITE_ALL_SQL` in your adapter. **Both names
are populated for all history** (the new columns were backfilled from the old at
migration), so there is no transition gap and nothing breaks if you deploy
nothing. The mirror gets dropped only when you confirm you have migrated — it is
not on a timer. Tell us and we will schedule it.

---

## 4. Methodology stamps — the thing you actually asked for

Both composite tables now carry:

| column | what it is |
| :--- | :--- |
| `methodology_version` | manual, bumped when a formula or rule changes. Keyed to the dashboard's Methodology §15 revision log. |
| `config_hash` | automatic digest of the weight/policy config. Catches a weight edited through the importance editor or a GDP-regression recalibration — neither of which touches a version string. |

This is the answer to your point-in-time question that does **not** require us to
stop recomputing history. If your refit moves and **both stamps are unchanged**,
the world changed. If a stamp moved, we did. `weight_change_log` has the
per-signal detail of every importance change, with reason and source — there are
10 US entries since 2026-07-05, which is why the automatic hash exists rather
than just the manual version.

Suggested: store the stamp alongside each fitted beta. Then your Beta Drift chart
can distinguish genuine drift from a methodology step, which it currently cannot.

---

## 5. On level vs change vs surprise — we took this to Ray

Your open question got a Digital Ray consult today (three rounds; logged in
`docs/Guidance/ray_dalio_review_log.md`, session 2026-10-07). Summary, including
where it **contradicts** advice we gave you earlier:

**His ruling: condition on the SURPRISE, not the level.** The All-Weather boxes
are defined by growth/inflation landing above or below what is *already priced
in*. Our composite measures state-versus-own-history, so the level is largely the
discounted part — a beta fitted on it is **biased**, not merely noisy. We had
read our own IC evidence (2y yield level 0.245 vs a change-like measure 0.079
over 555 months) as favouring the level; his reading is that it is evidence the
level is persistent and already discounted. Same number, opposite conclusion.
**Treat our earlier "use the level" steer as withdrawn.**

**Classification and magnitude differ.** For box assignment, the *sign* of the
surprise coefficient is sufficient and robust. For magnitude, use the surprise
coefficient, optionally shrunk.

**Build the surprise at SIGNAL level, not composite level.** His first
implementation step was `Surprise = Composite − Expected`, which is undefined for
us (unitless Z-score minus a percent). Pushed back; he chose:

```
Surprise_i,t        = (Realized_i,t − Expectation_i,t) / sigma_i
CompositeSurprise_t = Σ w_i · Surprise_i,t
```

with the published forecast where one exists and **the previous month's value
where none does**.

**He conceded the label when pressed.** With 16 of 19 signals on a random-walk
expectation, that formula is a weighted sum of standardised per-signal changes:
*"In the absence of true forecasts, the label is technically a misnomer. It is
still a change measure."* The real gains are per-signal standardisation (one
volatile component cannot dominate) and explicit missing-data renormalisation.

**His decision test, and our partial result.** Regress returns on both `ΔComp`
and `SurpriseComp`; if `SurpriseComp`'s incremental R² is negligible (<0.01)
after controlling for `ΔComp`, the engineering is not paying for itself. We ran
the half that does not need asset returns:

| basket | n | corr(ΔComp, SurpriseComp) | shared R² | sign disagreement |
| :--- | ---: | ---: | ---: | ---: |
| growth | 429 | +0.836 | 0.698 | 16.3% |
| inflation | 430 | +0.832 | 0.692 | 14.2% |

~30% of the variance is genuinely unshared — not interchangeable, not obviously
worth a rebuild. **Run his test with your asset returns before building
anything.**

### What we suggest regardless of that test

- **Stop calling `basis="change"` a surprise.** It is a change measure. The β
  means sensitivity to realized news, not to a forecast miss. Costs nothing.
- **Drop the level/change toggle; put both in one regression.** `corr(level,
  change)` is only **+0.07 to +0.22** across both composites — near-orthogonal,
  so both are well-identified together, and you get a state β and a news β
  separately rather than choosing.
- **Your `|t| ≥ 1.0` gate needs HAC standard errors** on any persistent
  regressor. `AR(1)` is **0.981** for the inflation composite and 0.903 for
  growth — essentially a random walk against monthly returns, which inflates OLS
  t-stats badly (Stambaugh/spurious-regression bias). The effective sample is far
  smaller than your nominal n, so holdings will land in boxes on noise. Use
  Newey-West with ~6–12 lags and raise the gate. On the change basis this barely
  matters (AR(1) 0.03–0.29), which is itself an argument for change if you keep a
  single regressor.

### A dead end, so you do not re-walk it

The Scotti Surprise Index was investigated here on 2026-10-03 and **confirmed
unavailable** — no live 2026 feed. The surviving free surprise source is the
Philadelphia Fed SPF (`indicators/spf_loader.py::compute_spf_surprise()`), which
is a genuine forecaster-consensus surprise but **quarterly and US-only**. We have
no monthly expectations for any non-US country.

---

## Reference

- `docs/consumer_contract.md` — the standing contract: which table for which job,
  deprecated columns, join hazards. Read before relying on a column's meaning.
- `docs/Guidance/ray_dalio_review_log.md` session 2026-10-07 — the full consult.
- `docs/worklog.md` 2026-10-07 (2) — what shipped and why.

Open the DB **read-only**; it is single-writer and a second writer blocks the
pipeline.

Questions, or if you want the vintage-replay series surfaced as a third table —
ask.
