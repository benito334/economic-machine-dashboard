# ADR-008: What should measure "growth" when we sort assets into boxes

**Date:** 2026-10-09
**Status:** Accepted 2026-10-09 — evidence gathered, recommendation stands. CreovaOne-side refit still required before its backfill runs.
**Serves:** `docs/NORTH_STAR.md`

---

## In plain language

To sort each investment into one of Dalio's four boxes, CreovaOne has to measure
two things each month: did growth come in better or worse than expected, and did
inflation. For the growth half it currently uses the **10-year TIPS real yield** —
the interest rate on US government bonds after stripping out inflation.

The problem: when that rate rises, share prices usually fall. So the system sees
shares falling as the rate rises and concludes "these do badly when growth is
weak." But over the past year the rate rose because the **Federal Reserve was
tightening policy**, not because growth was weakening. The label says "falling
growth"; the actual cause is "higher interest rates."

That mislabelling just moved **21 of 55 holdings** — almost the whole equity
bucket — from one box to the opposite one. The backfill that would stamp this
across all stored history is correctly paused.

**My recommendation: measure growth with the growth surprise we started
publishing yesterday — what actually happened minus what professional
forecasters predicted — rather than with an interest rate.** It measures growth
rather than the price of money, and it is still expectation-relative, which is
what the four-box framework requires.

---

## How this serves the North Star

Directly, and on the first test: **does it measure what we claim?** Today it does
not. The axis is labelled "growth" and is substantially measuring monetary policy
stance. Anything built on it — box membership, risk budgets, the Balance Score —
inherits that error, and the error is invisible because the label looks right.

It also fails the mechanism test. We can state a mechanism for why rising real
yields depress share prices (higher discount rate on future cash flows), but it is
**not the mechanism the box name asserts**. A reviewer would catch this
immediately, so by our own standard it does not survive scrutiny.

---

## Context

CreovaOne promoted a `discounted_surprise` basis to production (its 2026-10-09
worklog entry, commit `e4656ad`). Growth is proxied by the 10-year TIPS real
yield (FRED `DFII10`), inflation by the breakeven rate. Both are market prices,
chosen deliberately so the basis does not depend on this repo's feed.

Measured there: `DFII10` rose **1.82% (Aug 2025) → 2.92% (Oct 2026)**, most of it
in the last six months. Refitting on the new basis reassigned **31 of 55
holdings'** dominant box, and **21+ flipped the same direction**,
`rising_growth → falling_growth`, across VTI, QQQ, NVDA, SCHD, SO, TSLA and more.
The fits are strong, not marginal (VTI t = −6.67, SCHD t = −7.28, GLD t = −3.06,
QQQ t = −3.26, ~34–35 observations).

A one-directional flip across an entire asset class is the signature of a
confounded regressor, not of 21 independent discoveries. CreovaOne's own author
reached the same conclusion and paused rather than backfilling.

## Decision

**Proposed:** replace the growth axis of the `discounted_surprise` basis with the
**growth-surprise composite** — the weighted average of per-signal surprises
(realized minus the Philadelphia Fed Survey of Professional Forecasters
consensus) for `growth.unemployment`, `growth.payrolls` and
`growth.industrial_prod`.

Keep the inflation axis as the breakeven rate. Breakeven is a genuine
market-implied inflation expectation and does not suffer the same confound.

## Evidence

**That the current proxy is confounded.** The real yield decomposes into expected
real growth *plus* a policy/term-premium component; this is standard in the
term-structure literature and is why central banks are described as moving real
rates. It is also the limitation CreovaOne itself flagged when the proxy was
built, now showing up live at scale.

**That the replacement measures growth and not the price of money.** The SPF
consensus is a published forecast of real activity. Realized-minus-forecast is
the standard construction for a macro surprise in the event-study literature,
and is what Ray's own 2026-10-07 Ruling 3 specified: *"the published forecast
where one exists."*

**That it is materially different from what we had.** Measured 2026-10-09 on live
data: correlation between the random-walk surprise and the SPF-based surprise is
**0.59** for unemployment, **0.62** for payrolls, **−0.01** for industrial
production. These are not the same series.

**That it covers enough to matter.** The three SPF-backed signals are **33% of the
US growth basket** by weight, including its two highest-weighted members.

### Measured 2026-10-09, after building the axis

**A bug was found and fixed in the process, in the very thing being proposed.**
The SPF industrial-production forecast is an index LEVEL on whatever base was
current when the survey ran; today's `INDPRO` is on 2017=100. Dividing one by
the other compares different rulers — the SPF-to-realized level ratio measures
**2.08** in 1985-95, 1.51 in 1995-2005, 1.10 in 2005-15, 1.05 since — and
produced a surprise averaging **−1.84σ** instead of ~0. Shipped in `da556a2`
(2026-10-08), caught here. Fixed by chaining growth RATES, which are
base-invariant: the quarterly growth implied within a single survey (h3/h2,
same base, so it cancels) compounded onto three realized quarterly rates. IP
surprise mean **−1.84 → −0.10**, sd 3.72 → 1.08. `PAYEMS` is a headcount and
never rebases (ratio 0.996–1.003 in every era), so it keeps the simple
conversion and now serves as the control in a regression test.

**Against NBER recession dating** — independent of every series we ingest, and
the strongest external check available:

| | proposed axis (growth surprise) | incumbent (Δ real yield) |
| :--- | ---: | ---: |
| mean in recession | **−1.96** | −0.005 |
| mean in expansion | **+0.13** | +0.003 |
| difference | **−2.09** | −0.008 |
| t (monthly) | **−7.35** | −0.09 |
| p (monthly) | **<0.0001** | 0.93 |

Treating each recession as ONE observation rather than counting months — the
honest unit, since 47 recession months are 5 recessions:

| recession | mean growth surprise |
| :--- | ---: |
| 1982-01 … 1982-11 | −1.50 |
| 1990-08 … 1991-03 | −0.90 |
| 2001-04 … 2001-11 | −1.25 |
| 2008-01 … 2009-06 | −2.43 |
| 2020-03 … 2020-04 | −7.39 |

**5 of 5 negative.** Sign test across episodes p = 0.031 one-sided; t-test on
the five episode means p = 0.079. Consistent in direction in every recession,
not driven by one, but **underpowered** — five episodes is five episodes.

**Correlation with the incumbent is +0.07**, confirming these are not two
measurements of the same thing.

**What the evidence does NOT include:** nobody has refit the 55 holdings on
this axis and compared box assignments. That remains a precondition on the
CreovaOne side before its backfill.

## The five checks

| # | Check | Answer |
| :-- | :--- | :--- |
| 1 | Measures what we claim? | **Yes, and this is the point.** It measures realized growth against expected growth. The current proxy measures the real discount rate. |
| 2 | Mechanism? | Yes: an asset that falls when growth disappoints is genuinely growth-sensitive. That is the mechanism the box name asserts. |
| 3 | Evidence? | Standard surprise construction; Ray's Ruling 3; three live correlations above; 33% basket coverage. |
| 4 | Outside reviewer? | A reviewer would accept realized-minus-consensus as a growth surprise. They would challenge a real yield labelled "growth" — which is why we are here. |
| 5 | What it cannot support? | See Limits. It is US-only, quarterly-sourced, and covers a third of the basket. |

## Alternatives considered

**(a) Keep the real yield, rename the box.** Cheapest. Rejected: it abandons the
four-box framework's meaning rather than fixing the measurement, and "rising
discount rate" is not one of Dalio's four environments.

**(b) Use this repo's growth composite (`composites_pit.growth_score`).** It
genuinely measures growth across 12 signals. Rejected as the primary: it is
scored against its own history, so it says nothing about whether the market had
already priced the move — which is precisely what the four boxes are about. Ray
ruled on this directly on 2026-10-07: *"the level is the discounted part, not the
deviation."*

**(c) The growth-surprise composite.** Recommended. Measures growth, and is
expectation-relative.

**(d) Do nothing and backfill anyway.** Rejected outright. It would write a
confounded label across all stored history and make the error much harder to
find later.

## Consequences

**Easier:** the growth axis starts meaning what its name says, so box membership
becomes defensible to an outsider.

**Harder:** it reintroduces a dependency on this repo's feed, which CreovaOne had
deliberately removed. That is a real cost and worth stating plainly — though the
dependency is now on a *published external forecast* plus official statistics,
not on our own weighting choices.

**Needs watching:** the SPF is quarterly and US-only. Non-US books cannot use
this axis today and must stay on the existing basis, with that stated rather than
silently inherited.

**Before adopting:** refit the 55 holdings on the proposed axis and compare box
assignments against both the current production result and the pre-change
baseline. If it produces another one-directional mass flip, that is a signal to
stop, not a result.

## Limits

This does not make the four-box assignment *reliable* — it makes it *honest*.
Separately established on 2026-10-08/09 and recorded in `CLAUDE.md`: a
regime→asset-return relationship **cannot be demonstrated at conventional
statistical significance** on this data, even pooling eleven countries, because
they co-move (eleven are worth about 2.1 independent observations).

So this ADR improves what the axis measures. It does not license more confidence
in the resulting boxes. Both things are true at once and both should be said
whenever these boxes are quoted.
