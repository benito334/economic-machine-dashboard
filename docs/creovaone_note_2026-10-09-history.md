# Note for CreovaOne — your 2003 limit isn't in our data

2026-10-09. **Two findings and one heads-up about a change coming on our side.
All decisions are yours.**

---

## 1. The 2003 wall is in your basis, not our composite

`composites_pit` starts **1983-01** for the US. Also 1952 for GB, 1974 for JP.
Nothing about our feed stops at 2003.

The 2003 cutoff comes from `macro_beta_service`'s live default basis,
`discounted_surprise`, which is built from two FRED series:

| series | role | starts |
| :--- | :--- | :--- |
| `T10YIE` (10y breakeven) | inflation axis | **2003-01-02** |
| `DFII10` (10y TIPS real yield) | growth axis | **2003-01-02** |

TIPS did not trade before 2003, so that basis can never reach earlier. It is a
hard floor in the instrument, not a gap in anyone's data.

**Your `level` and `change` bases read `composites_pit` directly and would reach
1983 today** — twenty extra years, no new data, no new code. Whether that trade
is worth it is your call; the previous note (`creovaone_note_2026-10-09.md`)
carries the separate evidence that the real-yield growth axis measured **p = 0.93
against NBER recessions — no detectable relationship**. The series capping you at
2003 is also the one that did not validate. Those are two independent reasons
pointing the same way, which is worth knowing, but it is still your decision and
the independence you gain from a market-priced basis is a real thing to give up.

---

## 2. Why the extra years are worth more than they look

Our own constraint has been the number of **independent** downturns available to
test against. Counted against the point-in-time scoreable era:

| macro data start | recessions testable |
| :--- | ---: |
| 2003 (your current basis) | 2 |
| 1983 (`composites_pit` today) | **4** |
| 1959 (where we are going — see below) | **8** |

More consequential than the count: CPI YoY at each recession onset.

| onset | CPI YoY at onset |
| :--- | ---: |
| 1990-08 | 5.7% |
| 2001-04 | 3.2% |
| 2008-01 | 4.3% |
| 2020-03 | 1.5% |
| — gained by extending — | |
| 1970-01 | 6.2% |
| 1973-12 | 8.9% |
| 1980-02 | **14.2%** |
| 1981-08 | **10.8%** |

**No recession in the 1983+ sample began with inflation above 6%.** If you are
fitting inflation betas, every observation you have comes from the
low-inflation era. That is a real limit on the four-box assignment, and it is
not something either of us can fix with a better estimator.

---

## 3. Heads-up: we are extending history to 1959, and it will move your numbers

Recorded in `docs/decisions/ADR-009-history-extension.md`. Our 1980 floor turned
out to be an undocumented default constant, not a data limit. We are pulling it
back to **1959-01** for the US, and deliberately no further — at 1948 the
inflation basket drops to PPI plus headline CPI and correlates only **0.660**
with the full basket, disagreeing on sign in 37.4% of months. At 1959 it is
**0.999**. Growth at 1959 is **0.936** — for scale, that is the same order as
the `composites` vs `composites_pit` gap of 0.942 already documented in
`docs/consumer_contract.md`.

**What this does to rows you have already pulled:**

- `composites` scores against **full history**, so a longer sample changes every
  signal's mean and standard deviation. **Every historical `growth_score` and
  `inflation_score` moves**, 1983–2026 rows included.
- `composites_pit` uses an **expanding** window, so a 1990 row's window becomes
  1959→1990 instead of 1980→1990. Those move too, though less.
- **`METHODOLOGY_VERSION` will bump**, so the consumer-contract rule still holds:
  if your refit moves and both stamps are unchanged, the world changed; if a
  stamp changed, we did. This one is us.
- **You will need to re-pull after we ship it.** We will tell you when.

**Two new columns will land with it:** a per-month signal count and weight-share
for each basket. You will want to filter on these. A 1962 reading is built from 6
growth signals and a 2020 reading from 12, and between 1959 and 1992 the growth
basket has **no consumption leg** at all (`real_pce` starts 2007, `retail_sales`
1992) — it is a labour-and-output read. That is a composition shift across your
fitting window, not just a thinner one, and it is the kind of thing that is
invisible unless you look for it.

---

## 4. On the 1920s

If the goal is backtesting to the 1920s, that is not reachable by extending this
composite, and we would rather say so now than hand you something that looks
like it.

For the 1920s–30s at monthly frequency the free sources support **one** growth
series (`INDPRO`, 1919) and **no core inflation measure**. FRED has retired most
of the NBER Macrohistory Database — release 15 now holds 31 series, none starting
before 1930 (we checked 2026-10-09). The academic datasets that do cover the era
properly — Jordà–Schularick–Taylor Macrohistory, Barro–Ursúa, Balke–Gordon — are
predominantly **annual**, so a monthly chip cannot be built from them.

A pre-1948 instrument is buildable — plausibly `INDPRO` + `PPIACO` + the Baa–Aaa
credit spread, all available from 1919, validated against `USREC` which is
monthly back to 1854. But it would be **a different instrument under a different
name**, not `growth_score` with more rows, and it would be annual-or-quarterly
for anything beyond those three series. We have deferred it to its own decision
rather than quietly widening this one.

If 1920s coverage is a real requirement on your side rather than an aspiration,
tell us and we will scope it properly — it is a project, not a config change.

---

## One thing we are NOT telling you to do

Switching your basis, and whether to refit on a longer sample, are both yours.
The test we would run first is the same one that caught the last problem: refit
your 55 holdings and compare box assignments against the current result.
**If it produces another one-directional mass flip, that is a signal to stop,
not a result.**
