# Note for CreovaOne — one test result on the growth axis

2026-10-09. **One finding, passed along because we have data you don't. The
decision is entirely yours** — you have already diagnosed the confound yourself
and paused the backfill, which is the right call.

---

## The finding

We tested both candidate growth measures against **NBER recession dating** —
the official US recession calendar, which is independent of every series either
project builds. If something claims to measure growth, it should drop in
recessions.

| | your current growth axis (Δ 10y TIPS real yield) | our growth-surprise composite |
| :--- | ---: | ---: |
| mean in recession | −0.005 | **−1.96** |
| mean in expansion | +0.003 | **+0.13** |
| gap | −0.008 | **−2.09** |
| p (monthly) | **0.93** | <0.0001 |

**The real yield shows no detectable relationship with recessions.** Not a weak
one — none.

Per recession episode, which is the honest unit (47 recession months are 5
recessions):

| | growth surprise |
| :--- | ---: |
| 1982 | −1.50 |
| 1990–91 | −0.90 |
| 2001 | −1.25 |
| 2008–09 | −2.43 |
| 2020 | −7.39 |

**5 of 5 negative.**

**The honest limit:** five recessions is five observations. Sign test across
episodes p = 0.031 one-sided; t-test on the five episode means p = 0.079 —
outside conventional significance. Consistent in direction, underpowered in
magnitude. We are not claiming the replacement is validated; we are saying the
incumbent demonstrably tracks nothing recession-related and this one tracks
something in every episode.

---

## What the alternative is, if you want it

`signals.surprise` in `signals.duckdb` — populated 2026-10-08, 345k of 368k
rows. For three US growth signals it is a **real** surprise: realized minus the
Philadelphia Fed SPF consensus forecast. Those three are
`growth.unemployment`, `growth.payrolls`, `growth.industrial_prod` — **33% of
the US growth basket** by weight, including its two highest-weighted members.

To build the axis: weight those three by their basket importance
(0.125 / 0.320 / 0.330) and **flip the sign on unemployment** — it carries
`invert: true`, because a rising-unemployment surprise is a negative growth
surprise. Missing that inverts the whole axis.

For every other signal the expectation is still a random walk, so on those the
column is a standardised *change*, not a surprise. Documented in
`docs/consumer_contract.md`.

### One bug worth knowing about, since it was ours

We shipped that column on 2026-10-08 with the industrial-production forecast on
the wrong index base — SPF publishes a level on the base current when the survey
ran; `INDPRO` is now on 2017=100, and the ratio between them runs 2.08 in
1985-95 down to 1.05 today. Fixed 2026-10-09 by chaining growth rates, which are
base-invariant. **If you pulled that column before 2026-10-09, re-pull it.**
Payrolls and unemployment were never affected.

---

## The trade-off, stated plainly

Switching gives up something real: your current axis is market-priced and
independent of our feed, which you chose deliberately. Ours depends on a
published external forecast plus official statistics — better than depending on
our own weighting choices, but not the same as independence.

So it is a genuine trade: **independence versus measuring the thing the box is
named after.**

## What we would check before you switch

Refit the 55 holdings on the alternative axis and compare box assignments
against both your current result and the pre-change baseline. **If it produces
another one-directional mass flip, that is a signal to stop, not a result** —
the same test that caught the current problem.

We have not run that; it needs your returns and your estimator.
