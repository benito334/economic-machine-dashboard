# ADR-009: Extend the US composite history to 1959, and stop there

**Date:** 2026-10-09
**Status:** Proposed 2026-10-09 — measurements complete, build not started, awaiting owner sign-off
**Serves:** `docs/NORTH_STAR.md`

---

## In plain language

Our growth and inflation composites start in 1980. That was never a data limit —
it is a single default date in the code that fetches from FRED. The underlying
statistics go back much further: industrial production to 1919, producer prices
to 1913, unemployment to 1948.

This matters because of the honesty problem we have been stuck on. Every claim we
make about whether the regime chips predict anything is limited by how many
*independent* economic downturns we can test against, and from 1983 onward there
are only four. Worse, all four were low-inflation downturns — so **how the
inflation chip behaves in a high-inflation recession is currently untestable on
our own data.**

**What we are deciding: pull history back to 1959, which doubles the number of
testable recessions from four to eight and adds the 1970s stagflation era — and
deliberately do NOT go back further, because at 1948 the inflation basket
collapses to two series and stops being the same measurement.** The 1920s, which
prompted this, would be a genuinely different instrument and needs its own
decision, not this one.

One warning that must travel with this: extending the sample **changes every
number already published**, including historical ones, because each reading is
scored against the full history and the full history just got longer.

---

## How this serves the North Star

The North Star asks for understanding that is "academically validated" and
"survives scrutiny". The single largest obstacle to that in this project is not
methodology — it is **sample size**, and it is documented: a regime→return
relationship cannot be shown at conventional significance on this data, and
ADR-008's recession validation had to be stated with the limit "five recessions
is five observations."

Adding countries was tried and does not fix it: eleven countries co-move at
ρ̄ +0.42 and are worth about 2.1 independent observations. **Adding decades does
fix it**, because a 1970 recession and a 2008 recession genuinely do not
co-move. This is the one available lever on the power problem.

It also closes a specific blind spot rather than a general one. Our current test
sample contains no recession that began with inflation above 6%. Dalio's
framework is substantially *about* inflationary contractions. We have been
unable to test the instrument on the episodes the framework was built to
describe.

---

## Context

**The prompt.** A downstream consumer (CreovaOne) reported that the composite it
regresses against "only appears to go back to 2003." Investigated 2026-10-09: that
limit is not ours. `composites_pit` starts **1983-01** for the US. The 2003 wall is
their own default beta basis, which is built from FRED `T10YIE` and `DFII10` —
both TIPS-market series that begin **2003-01-02** because TIPS did not trade
before then. Their other two bases read `composites_pit` and already reach 1983.
That is passed to them separately in `docs/creovaone_note_2026-10-09-history.md`;
it is not what this ADR decides.

**Our actual floor.** [`indicators/loader.py:51`](../../indicators/loader.py) —
`_FRED_START = "1980-01-01"`. A default constant with no recorded justification.
Every US growth and inflation signal in the DB starts 1980-01 or later as a direct
consequence.

**What the sources actually support**, from the FRED `series` endpoint, queried
2026-10-09:

| series | signal | true start |
| :--- | :--- | :--- |
| `PPIACO` | `inflation.ppi_broad` | 1913-01 |
| `INDPRO` | `growth.industrial_prod` | 1919-01 |
| `PAYEMS` | `growth.payrolls` | 1939-01 |
| `CPIAUCSL` / `OPHNFB` | `inflation.cpi_headline`, `growth.productivity` | 1947-01 |
| `UNRATE` / `CIVPART` / `MFPNFBS` | unemployment, participation, TFP | 1948-01 |
| `CPILFESL` | `inflation.cpi_core` | 1957-01 |
| `PCEPILFE` | `inflation.pce_core` | 1959-01 |
| `TCU` | `growth.capacity_util` | 1967-01 |
| `GACDFSA066MSFRBPHI` | `growth.pmi_proxy` | 1968-05 |

**The size of the prize.** NBER recession onsets, counted against the
point-in-time scoreable era (data start + the 36-month `PIT_MIN_PERIODS`
warm-up):

| data start | PIT era begins | recessions testable |
| :--- | :--- | ---: |
| 1980 (today) | 1983 | **4** |
| 1968 | 1971 | 7 |
| **1959** | **1962** | **8** |
| 1948 | 1951 | 11 |
| 1919 | 1922 | 17 |

## Decision

**Make the FRED history start a per-binding setting, default it to 1959-01-01 for
the US, and re-pull. Do not extend past 1948 inside the existing composite at
all; do not extend past 1959 without publishing a per-month basket-coverage
column first.**

Anything earlier than 1948 is a separate instrument under a separate name and a
separate ADR. It is not this composite with more rows.

## Evidence

**That 1959 is nearly free, and that 1948 is not.** The decisive test is whether a
basket restricted to the signals available in a given era still measures the same
thing as the full basket. Measured 2026-10-09 on the US monthly panel in
`signals.duckdb` (n = 548–561 months, 1980–2026), each era-restricted basket
rebuilt with its own weights and compared against the full basket:

| era-available basket | growth: corr | growth: sign disagree | inflation: corr | inflation: sign disagree |
| :--- | ---: | ---: | ---: | ---: |
| 1992 (9 / 5 signals) | 0.993 | 3.6% | 0.998 | 1.6% |
| 1980 (8 / 4 signals) | 0.978 | 4.8% | 0.999 | 1.6% |
| 1968 (8 / 4 signals) | 0.978 | 4.8% | 0.999 | 1.6% |
| **1959 (6 / 4 signals)** | **0.936** | **12.5%** | **0.999** | **1.6%** |
| 1948 (6 / 2 signals) | 0.936 | 12.5% | **0.660** | **37.4%** |

The inflation basket is the binding constraint, and it fails abruptly rather than
gradually: `pce_core` (1959) and `cpi_core` (1957) carry 75% of its nominal weight
between them, so 1959 costs essentially nothing (0.999) while 1948 — PPI and
headline CPI only — collapses to 0.660 and disagrees on sign in **37.4% of
months**. A series that disagrees with itself in more than a third of months is
not the same instrument.

**Calibrating the 1959 growth penalty against one we already ship and consumers
already accept.** `docs/consumer_contract.md` publishes the `composites` vs
`composites_pit` gap as growth corr **0.942** / 14.6% sign disagreement. The
1959 era-restriction penalty is **0.936 / 12.5%** — the same order, slightly
*better* on sign agreement. We already ask consumers to live with a difference
of this size and we document it rather than hiding it. This is not a new class
of compromise.

**Weighted coverage, for the record** (nominal weight = base_share × importance ×
quality_factor, as a share of the basket total):

| as of | growth signals | growth weight | inflation signals | inflation weight |
| :--- | ---: | ---: | ---: | ---: |
| 1920 | 1/12 | 14.2% | 1/7 | 6.3% |
| 1948 | 6/12 | 42.6% | 2/7 | 10.6% |
| **1959** | **6/12** | **42.6%** | **4/7** | **85.7%** |
| 1968 | 7/12 | 51.7% | 4/7 | 85.7% |
| 1980 | 8/12 | 62.2% | 4/7 | 85.7% |

Note the growth basket at 1959 is 42.6% of weight but correlates 0.936 — thin is
not the same as wrong. What it loses is the *consumption* leg (`real_pce` 2007,
`retail_sales` 1992); 1959–1992 growth is a labour-and-output read. That is a
composition shift and is stated, not buried.

**That the current sample is biased toward one kind of recession.** CPI YoY at
each NBER onset, measured 2026-10-09:

| onset | CPI YoY | in today's 1983+ sample? |
| :--- | ---: | :--- |
| 1970-01 | 6.2% | no — gained |
| 1973-12 | 8.9% | no — gained |
| 1980-02 | **14.2%** | no — gained |
| 1981-08 | **10.8%** | no — gained |
| 1990-08 | 5.7% | yes |
| 2001-04 | 3.2% | yes |
| 2008-01 | 4.3% | yes |
| 2020-03 | 1.5% | yes |

**Today's sample contains no recession that began with inflation above 6%.**
Extending to 1959 adds two that began above 10%. This is the specific,
nameable gap, and it is the one most relevant to a Dalio-framework instrument.

**That the 1920s are a different problem, not a bigger version of this one.**
FRED has retired most of the NBER Macrohistory Database: release 15 now holds
**31 series, none starting before 1930** (queried 2026-10-09). What survives for
the 1920s–30s at monthly frequency is `INDPRO` (1919), `PPIACO`/`CPIAUCNS`
(1913), `AAA`/`BAA` corporate yields (1919), NY commercial paper rates
(1857–1971) and the Dow (1914–1968) — **one** growth series and no core
inflation measure at all. The academic datasets that do cover the era well
(Jordà–Schularick–Taylor Macrohistory 1870–2020, Barro–Ursúa, Balke–Gordon GNP,
Officer/Williamson) are predominantly **annual**; Shiller's monthly series from
1871 are prices, CPI and long rates, not real activity. A monthly chip cannot be
built from annual data, so the honest 1920s product is annual or quarterly and
is a different thing.

## The five checks

| # | Check | Answer |
| :-- | :--- | :--- |
| 1 | Measures what we claim? | **At 1959, yes** — inflation corr 0.999, growth 0.936 against the full basket. **At 1948, no**: inflation corr 0.660, sign disagreement 37.4%. This is exactly why the line is drawn at 1959. |
| 2 | Mechanism? | No new mechanism is asserted. The same signals measured over a longer window. The one real change is composition: 1959–1992 growth has no consumption leg, and that is published rather than inferred. |
| 3 | Evidence? | Era-restricted basket correlations (table above, n = 548–561); FRED `observation_start` for every basket series; NBER onset counts and onset inflation; the FRED release-15 enumeration for the 1920s claim. All measured 2026-10-09. |
| 4 | Outside reviewer? | A reviewer would accept extending a sample to 1959 given corr 0.999 / 0.936, and would require the coverage column and the composition note. They would reject 1948 inflation on the 0.660, and would reject a 1-signal 1920s "growth composite" outright. We agree with them on both. |
| 5 | What it cannot support? | See Limits. It does not make the chips predictive, and it does not extend the *inflation anchor* backward. |

## Alternatives considered

**(a) Leave it at 1980.** Rejected. The floor is an undocumented default, and the
cost is concrete: four testable recessions instead of eight, and zero
high-inflation recessions, which is the case the framework most cares about.

**(b) Extend to 1948.** Rejected **on evidence**, and this is the most useful
entry here because 1948 is the intuitive target (it is where unemployment and
the modern CPI both begin). The inflation basket at 1948 is PPI plus headline
CPI only: corr 0.660 against the full basket, **sign disagreement in 37.4% of
months**. It would silently publish a series named `inflation_score` that
disagrees with `inflation_score` a third of the time. `min_signals_required: 1`
in `composites_policy.yaml` means nothing currently stops this.

**(c) Extend to 1968 instead, the conservative option.** Growth 0.978 and
inflation 0.999 — genuinely the cleanest numbers. Rejected as the *target*
because it buys 7 recessions where 1959 buys 8, and the extra one is **1970-01
at 6.2% CPI** — a high-inflation recession, the exact observation the sample is
missing. The 1959 growth penalty (0.936 vs 0.978) is the price of that episode
and is smaller than the PIT penalty we already ship. **If the owner prefers
strictness over the extra episode, 1968 is a defensible fallback and nothing
else in this ADR changes.**

**(d) Go to 1919 inside the same composite.** Rejected outright: one growth
signal (`INDPRO`) and no core inflation series. A Z-score of industrial
production alone is not "the growth chip, earlier" — it is a different
instrument wearing a trusted name, which is the specific failure mode this
project exists to prevent.

**(e) A separate pre-1948 instrument, distinctly named.** **Not rejected —
deferred to its own ADR.** The plausible build is `INDPRO` + `PPIACO` + the
Baa–Aaa credit spread (all 1919), validated against `USREC`, which is monthly
from 1854 and genuinely out of sample. It must not be called the growth chip and
must not be published into `composites`.

**(f) Add more countries instead.** Already tried and already measured:
eleven countries are worth ~2.1 independent observations (`indicators/panel.py`).
Settled; not reopened here.

## Consequences

**This changes every published number, including historical ones. Say so loudly.**

- `composites` scores each reading against the series' **full history**. Adding
  1959–1980 changes the full-history mean and standard deviation of every signal,
  so **every `growth_score` and `inflation_score` in the table moves**, 1980 rows
  included. This is the documented and intended behaviour of that table — one
  consistent lens over all history — but it has never before been triggered by a
  *sample* change rather than a methodology change.
- `composites_pit` uses an **expanding** window, so a 1990 row's window becomes
  1959→1990 instead of 1980→1990. Those values move too.
- Therefore: **`METHODOLOGY_VERSION` must bump**, and `docs/consumer_contract.md`
  gains a note. Per that contract, a consumer whose refit moves while both stamps
  are unchanged should conclude the world changed — so the stamp has to move here,
  or we break the one guarantee that document makes.
- **Consumers must re-pull.** Named consumer: CreovaOne (`composites_pit` via
  `macro_beta_service`). Notified in `docs/creovaone_note_2026-10-09-history.md`.

**Required alongside the change, not after it:**

1. **Publish per-month basket coverage** — a `growth_n` / `inflation_n` count and
   weight-share column on both composite tables. Without it, a consumer cannot
   tell a 4-signal 1962 reading from a 12-signal 2020 one, and the composition
   shift becomes an invisible error of exactly the kind ADR-008 was written about.
2. **Raise the minimum-signal floor.** `min_signals_required: 1` would emit a
   one-signal composite without complaint. `PIT_MIN_SIGNALS` is already 3 and the
   two are documented as needing to agree; this is the moment to reconcile them.
3. **Re-run ADR-008's recession validation on the longer sample.** Its headline
   limit — "five recessions is five observations" — becomes eight, and the sign
   test gains real power. This is the payoff and it should be collected
   immediately rather than assumed.

**Makes easier:** every statistical claim in the project, by roughly doubling the
independent-episode count; and the first genuine test of the inflation chip in a
high-inflation contraction.

**Makes harder:** per-month coverage now varies across a 67-year span, so any
analysis that pools months has to decide whether to weight by coverage. Backtests
in `docs/backtests/*.md` carry numbers computed on the 1980-start sample and
become non-comparable — they must be re-run or explicitly date-stamped, not
silently left.

**Needs watching:** `growth.tfp` (annual, `MFPNFBS`) and `growth.productivity`
(quarterly) carry long forward-fill limits (A = 15 months, Q = 9). Over a longer
and thinner early sample those fills are a larger share of the panel. Check the
`is_stale` and ffill behaviour on 1959–1970 before trusting those two legs.

## Limits

**This does not make the chips predictive.** The statistical bound stands: a
regime→asset-return relationship cannot be demonstrated at conventional
significance on this data. Eight recessions is better than four and is still
eight. If the longer sample produces a significant result, that result will need
the same scrutiny applied on 2026-10-08/09 — overlapping windows and co-movement
inflate significance, and this extension does nothing about either.

**It does not extend the inflation anchor.** The inflation chip was re-anchored
to the central bank's target on 2026-10-08, and `config/inflation_anchor.yaml`
carries one fixed US figure, `target_pct: 2.0`. The Fed had no inflation target
before roughly 1996 implicitly and 2012 explicitly, and the US was on a gold
standard for most of the pre-1933 period. **Applying 2% to 1962 is anachronistic
and would not survive review.** The extension therefore delivers the continuous
`inflation_score` over 1959–2026 but **not** the anchored chip, which must either
stay 1996+ or acquire a documented time-varying target in a separate decision.
Any chart or test that shows the anchored read before 1996 is wrong until that
decision is made.

**It says nothing about the other thirteen countries.** The non-US baskets are
built on different providers with their own start dates, and the inflation
collapse seen at US-1948 is the kind of failure that will appear at different
dates elsewhere. Each country needs the same era-restriction test run before its
own floor is lowered. Do not generalise this ADR's 1959 to anything but the US.
