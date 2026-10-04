# External Validator Badges — Plan

> **Purpose:** promote the existing one-off `audit_benchmarks.py` comparison logic from a manual
> CLI audit into a live, always-on validation layer — a badge on the dashboard (AGREE/PARTIAL/
> CONTRADICT per axis) plus a detail page, refreshed on the same schedule as the chips themselves.
> Consumed downstream by CreovaOne's Beta Engine (Phase 6U), which depends on this project's
> growth/inflation surprise series for its own asset-beta regressions — a badge here is also a
> badge there.

**Origin.** The 2026-10-03 Dalio chip audit (`docs/audits/dalio_chip_audit_log.md`) found the
inflation score was window-dominated (a 0.94-point swing on window choice alone) and is mid-fix.
Separately, CreovaOne's own Phase 6U work (a growth/inflation beta regression consuming this
project's `growth_inflation_history()`) hit a parallel lookback-sensitivity problem one layer
downstream, and paused pending more confidence in the upstream regime read. Both problems are
instances of the same thing: nobody gets a continuous, live answer to "does an independent source
agree with our regime classification right now" — only a periodic, manually-triggered audit. This
plan fixes that.

**Non-negotiable, inherited from `audit_benchmarks.py`'s own header:** no validator series may ever
be added to `config/us_bindings.yaml` or any country composite basket. The moment a benchmark feeds
the thing it's validating, the badge becomes circular and worthless. This stays strictly read-only
against the chip.

---

## What already exists (do not rebuild)

`indicators/audit_benchmarks.py` (766 lines) already contains nearly all the hard part:

- `GROWTH_BENCHMARKS` / `INFLATION_BENCHMARKS` — FRED-ID-verified benchmark definitions, including
  **CFNAI-MA3** (`CFNAIMA3`) and **Trimmed Mean PCE** (`PCETRIM12M159SFRBDAL`, Dallas Fed), with
  publisher thresholds and orientation already encoded.
  (Note: 14-day-old thresholds — re-check at build time, `thresholds={"below": -0.70,
  "above": 0.70}` as last read for `cfnai_ma3`.)
- `_benchmark_state()` — classifies a benchmark as Above/Below/Neutral against its own publisher
  thresholds or a fallback ±0.5σ rolling Z.
- `_verdict(chip, bench_state)` — **the badge state itself**: AGREE / PARTIAL / CONTRADICT / UNKNOWN,
  "no judgement calls" by design (a fixed grid, see the function body).
- `compare_axis()` — full per-axis comparison: latest value, latest rolling Z, state, verdict,
  Spearman correlation, best lead/lag in months, disagreement episodes. **This is already the badge
  payload, one dict per benchmark.**
- `fetch_series()` (`indicators/loader.py`) — generic FRED pull via `fredapi`, needs only
  `FRED_API_KEY`. Works for any FRED series, not just the two already wired up.
- `scheduler.py` — a working daily APScheduler cron job (`run_import`), file-based config
  (`schedule.json` / `run_now.trigger` / `schedule_status.json`) written by the dashboard, read by
  the scheduler process. The new validator refresh job slots in here directly — no new scheduling
  infrastructure needed.

**What's missing is persistence, a schedule, and two UI surfaces** — not new comparison math.

---

## Scope: three candidate validators, assessed for actual build cost

### 1. CFNAI + Trimmed Mean PCE (eco3min-style) — build first

Already ~90% done per the section above. The only genuinely new work:
- Wrap `compare_axis()` (or a thin new `run_live_validation()`) as a scheduled job.
- Persist results (schema below) instead of printing a markdown report.
- Badge + detail page in the dashboard.

**Estimate: well under a day.**

### 2. Philadelphia Fed Survey of Professional Forecasters (SPF) — build second

Real, free, well-documented — but a genuinely different shape of work:
- **Not FRED-hosted.** Philly Fed publishes its own CSV/XLS files
  (philadelphiafed.org/surveys-and-data/real-time-data-research/spf-q*-2026 pattern, median/mean
  forecast datasets going back to Q4 1968). Needs its own small loader, not a reuse of
  `fetch_series`.
- **Quarterly, not monthly.** Doesn't refresh on the chip's own cadence — surface it as its own
  "last SPF read: Q3 2026" card rather than forcing it into the same AGREE/PARTIAL/CONTRADICT tally
  as the monthly validators. A genuinely different kind of badge (freshness-labeled, lower-frequency).
- Gives the project something CFNAI/Trimmed PCE can't: a true forecaster-**consensus** surprise
  measure (actual vs. what professional economists predicted), which is definitionally closer to
  what "surprise" means in the academic literature than our own Z-score-vs-own-history approach.

**Estimate: a few days — new loader + parser, new (lower-frequency) schema/UI treatment.**

### 3. Scotti Surprise Index (Dallas Fed) — investigate before scoping

Not on FRED (same class of gap `audit_benchmarks.py` already documented for `ADSBCI`). The only
lead found was "available from the author upon request, or chiarascotti.com" — **unverified for
2026**: no confirmed live, structured, currently-maintained download was found. **Do not scope a
build for this yet.** First task is a short spike: check whether chiarascotti.com (or a successor)
still actively publishes this, in what format, at what cadence, before committing any design time.
If it turns out to be dead or manual-request-only, drop it rather than design around it.

---

## Proposed schema (mirrors `store/store.py`'s existing `composites`/`debt_stress_snapshots` pattern)

One row per benchmark per axis per date — matches `compare_axis()`'s own natural output grain, so
persisting it is close to a direct `INSERT` of what that function already returns:

```sql
CREATE TABLE IF NOT EXISTS validator_verdicts (
    country          VARCHAR   NOT NULL,
    as_of            DATE      NOT NULL,
    axis             VARCHAR   NOT NULL,   -- 'growth' | 'inflation'
    validator_key    VARCHAR   NOT NULL,   -- 'cfnai_ma3' | 'trimmed_pce' | 'spf' | ...
    chip_label       VARCHAR,              -- our own chip state at this as_of (context for the row)
    benchmark_state  VARCHAR,              -- Above | Below | Neutral | Unknown
    verdict          VARCHAR   NOT NULL,   -- AGREE | PARTIAL | CONTRADICT | UNKNOWN
    spearman_full    DOUBLE,
    best_lag_months  INTEGER,
    latest_value     DOUBLE,
    latest_date      DATE,
    note             VARCHAR   DEFAULT '',
    created_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (country, as_of, axis, validator_key)
)
```

A per-axis rollup badge (overall AGREE/PARTIAL/CONTRADICT counts) is a `GROUP BY` on read, not a
second materialized table — avoids a second source of truth to keep in sync.

---

## UI: badge + detail page

- **Badge**: small pill per axis (Growth / Inflation) on the main dashboard, next to the existing
  chip — color-coded AGREE (green) / PARTIAL (amber) / CONTRADICT (red) / UNKNOWN (gray), reading
  from the rollup. Click-through to the detail page.
- **Validation detail page**: new sibling to `dashboard/methodology.py`, same styling helpers
  (`_p`, `_sub`, `_table`, `_note` already exist there — reuse, don't re-invent). One section per
  validator: current verdict, latest values both sides, Spearman/lag, and the disagreement-episode
  list `compare_axis()` already computes — this is the "many validation page... that shows the
  details" the owner asked for.

---

## Downstream consumer: CreovaOne

CreovaOne already reads this project's `growth_inflation_history()` read-only off `signals.duckdb`
via `MacroContextPlugin` / `IndicatorsMachineMacroAdapter` (no API layer exists or is needed — same
file-mount pattern works for `validator_verdicts`). Once this table exists and is populated,
CreovaOne's side is: one new adapter read method + a badge in its own macro/beta-engine UI. See
CreovaOne's own plan for that half of the work (`docs/PLAN_Beta_Engine.md`, this project referenced
from the "Validator Badge Pipeline" addendum).

---

## Suggested build order

1. **CFNAI + Trimmed Mean PCE** — schema, scheduled job (wraps existing `compare_axis()`),
   dashboard badge + detail page. This alone closes the loop CreovaOne is currently blocked on.
2. **Philadelphia Fed SPF** — new loader, lower-frequency card.
3. **Scotti Surprise Index** — spike first (confirm the source is actually alive and what shape it's
   in); only scope a build if that comes back positive.
