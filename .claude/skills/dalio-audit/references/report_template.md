# Dalio Chip Audit — {COUNTRY} {YYYY-MM}

**Run date:** {ISO date} · **Audited as-of:** {chip as_of} · **Mode:** current | historical
**Scope:** Growth + Inflation chips only.

## 1. Verdicts

| Chip | Dashboard says | Verdict | Falsifier |
| --- | --- | --- | --- |
| Growth | {chip} | {VERDICT} | {this would flip if ___} |
| Inflation | {chip} | {VERDICT} | {this would flip if ___} |

**One-line summary:** {the single thing the owner must hear}

## 2. The read under audit

| | Growth | Inflation |
| --- | --- | --- |
| Chip | | |
| Score | | |
| Delta (MoM) | | |
| Momentum | | |
| Score column / window | | |
| Threshold in force | gz = | iz = |

Dynamic thresholds: {on/off} · Divergence flag: {true/false}

## 3. Tier 1 — numeric benchmarks

> Benchmarks are independently *constructed*, not input-*independent*. CFNAI shares
> four inputs with our growth basket; the CPI measures re-aggregate the same price
> quotes. Correlation is partly mechanical. The informative content is below.

**Growth:** AGREE {n} / PARTIAL {n} / CONTRADICT {n}
**Inflation:** AGREE {n} / PARTIAL {n} / CONTRADICT {n}

CFNAI-MA3 (primary, publisher-thresholded): {value}, state {state}, verdict {v}.

{paste the pack tables}

### Lead/lag
{per benchmark; positive = we led. Flag anything lagging 3+ months.}

### Disagreement episodes
{largest per axis, with an explanation or an honest "cannot explain".}

## 4. Stage-1 blinded reads

### Agent A — quantitative (blind to our read)
- LEVEL: growth {…}, inflation {…}
- RELATIVE: growth {…}, inflation {…}
- Drivers: {…} · Confidence: {…} · Internal conflicts: {…}

### Agent B — narrative (Tier 2/3, blind to our read)
| Source | Date | Says | URL |
| --- | --- | --- | --- |

Thin or contradictory coverage: {…}

## 5. Comparison

| Axis | Our chip | Agent A | Agent B | Tier 1 | Reconciles? |
| --- | --- | --- | --- | --- | --- |
| Growth — level | | | | | |
| Growth — relative | | | | | |
| Inflation — level | | | | | |
| Inflation — relative | | | | | |

**Level-vs-relative divergences:** {these are findings, not errors}

**Strongest case against our own verdicts:** {required}

## 6. Punch list

Proposed changes only. Nothing is implemented without explicit approval.

| # | Finding | Proposed change | Triage |
| --- | --- | --- | --- |
| 1 | | | ready to implement / needs design pass / needs data-feed check / acknowledged, no build |

## 7. Digital Ray briefing block

{paste-ready summary the user can take to digitalray.ai — this skill cannot call it}

## 8. Reproduction

```bash
python -m indicators.audit_benchmarks --country {CC} {--as-of YYYY-MM-DD}
python -m indicators.audit_benchmarks --country {CC} --blind
```
