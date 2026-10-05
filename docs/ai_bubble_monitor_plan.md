# AI Capex Cycle Monitor — research findings and build plan

> Produced 2026-10-04 by a six-expert panel: a Digital Ray consult (digitalray.ai thread
> `88cc245d-a4ad-45e4-960b-c0ddabd91045`, logged in `Guidance/ray_dalio_review_log.md`) plus five
> specialist research agents — credit/structured finance, hyperscaler & semis equity, power &
> infrastructure, forensic accounting, macro transmission. **Every data source named below was
> verified live against its endpoint during that session**, per CLAUDE.md rule 4. Values are as
> returned, with the date. Sources that failed verification are in §7 and must not be retried
> without new information.

---

## 1. What this is, mechanically

In the Economic Machine frame this is **a short-term, credit-financed, sector-specific
investment boom sitting on top of the long-term debt cycle**. Ray's own placement. The
distinguishing question is not "are prices high" — the existing `/bubble-gauge` page already
answers that for the market as a whole — but **whether the cash flows being borrowed against
actually arrive**.

**Debtors:** the five hyperscale cloud/AI firms (investment grade, funding increasingly via
bonds *and finance leases*), the neocloud tier (CoreWeave, IREN, Nebius — sub-IG, genuinely
leveraged), and AI-related vendors extending credit to their own customers.
**Creditors:** banks and bond investors, data-centre ABS/CMBS holders, and — the fastest-growing
and least visible leg — private credit funds backed by insurance and pension money. BIS Bulletin
120 (7 Jan 2026): private-credit lending to AI-related firms went from near zero to **>$200bn**,
~8% of all direct-loan volume, with AI loan spreads at **6.2pp vs 6.1pp for non-AI** and secured
share *lower* (46% vs 48%). **Credit is pricing AI as average risk while equity prices it as
exceptional. One of those markets is wrong, and credit has the thinner cushion.**

**The self-reinforcing loop:** capex → supplier revenue → supplier earnings beat → supplier
equity re-rates → cheaper capital for the complex → vendor financing and equity stakes into
customers → those customers order more → capex. The new leg this cycle, absent in 2000 at this
scale, is that **the supplier is capitalising its own customers**.

**Where it breaks — the panel's split, worth preserving rather than resolving:**
- *Credit desk:* the funding of the warehouse, not the collateral. Collateral impairment is slow
  and arguable; funding withdrawal is instant. The 2007 analogue is conduit rollover, not
  foreclosure.
- *Equity desk:* input-cost inflation colliding with a contracted depreciation wave. The
  quantity leg is fine; the price-and-return leg is already breaking.
- *Power desk:* not the constraint binding (that is benign and self-limiting) but the constraint
  **clearing** — into 15-year PPAs and leases signed at scarcity prices. The 2002 merchant-power
  and dark-fibre outcome.
These are sequential, not competing, and the monitor is built to see all three.

---

## 2. Architecture decision — a stage classifier, not a score

Ray, asked directly: *"You should build a stage classifier. I don't like blended scores for
bubbles because they hide the real mechanics and create false confidence. Stages show you where
you are and what comes next."*

This independently confirms the call already made in `indicators/bubble_gauge.py`, which refused
to average three partial dimensions into one number. **No "AI Bubble Score" will be built.**

**A real dissent inside the panel, and its resolution.** The macro desk argued that no stage
classifier is responsibly buildable here at all: `debt_cycle_stage.py` works because each of its
five feature families has decades of cross-cycle history (it enforces `percentile_min_periods:
20` quarters), whereas the AI sector has no observable debt stock, no sector DSR, and a Census
construction series with **12.7 years and zero prior downturns in it**. A four-way argmax over
features with no cross-cycle variance is, in their words, "a random number generator with a
Dalio vocabulary." That critique is correct and it kills the obvious implementation.

It does not kill Ray's. **Ray's cascade is a threshold ladder, not a percentile argmax** — every
entry condition below is an absolute level (OCF/Capex < 1.5; spread ≥ +30bp; capex growth < 0)
with a confirmation counter, and absolute thresholds need no cross-cycle percentile history to
be meaningful. So: build the *shape* of `debt_cycle_stage.py` — named stages, explicit entry
conditions, confirmation requirement, un-advance — and **explicitly do not port its percentile /
Z-score / weighted-argmax machinery.** The macro desk's three-state BUILD/STRETCH/STALL read is
folded in as the coarse summary chip at the top of the page; Ray's five stages are the detail
beneath it.

**Corollary that must be enforced in code: suppress Z-scores on the Census series.** The house
`_full_history_z()` is right for the Buffett Indicator and margin debt (decades, multiple
cycles). On a 12.7-year series containing one regime, "+2σ" means "higher than the only regime
we have observed," which is not information. Report level, YoY and share — never a Z.

### 2.1 The cascade and its lead times

Ray's stated chain, which is what the stages encode:

| Transition | Lead time |
|---|---|
| Cash-flow coverage breach → credit-spread widening | **3-6 months** |
| Spread widening → capex slowdown | **6-12 months** |
| Capex slowdown → broad market impact | **12-24 months** |

Compressed for this cycle: past tech bubbles ran 12-18 months from first cash-flow warning to a
visible capex slowdown; Ray expects **9-12 months** now, given faster infrastructure cycles and
tighter financing markets. **That is the realistic ceiling on how much warning this page can
give.** It is not a trading signal; it is an early-warning system with roughly three quarters of
usable lead, and the page should say so on its face.

### 2.2 Stage definitions as built

Ray's entry conditions, with two legs re-sourced because his originals were paid feeds (noted
inline). **Two consecutive quarters to confirm at every stage. Stages can un-advance** if entry
conditions reverse for two quarters.

| Stage | Entry condition (as implemented) | Un-advance |
|---|---|---|
| **1 Expansion** | AI capex growth positive YoY **and** median OCF/Capex > 1.5 for ≥2 quarters | — |
| **2 Cash-Flow Squeeze** | Median OCF/Capex < 1.5 for 2 quarters **and** (debt + finance leases)/trailing-4Q OCF rising | both reverse for 2 quarters |
| **3 Credit Stress** | *Re-sourced.* ABCP−nonfinancial CP spread ≥ +30bp for 5 consecutive days, **or** bank NDFI loan growth stalling below +5% annualized after a >15% year, **or** CCC−BB OAS dispersion ≥ 8.0pp | conditions clear for 2 quarters |
| **4 Capex Slowdown** | Census data-centre construction 6m-annualized < 0 for 3 consecutive months **and** *(panel addition)* DOM/AEP trough-load excess over control < +2pp | capex growth positive 2 quarters |
| **5 Broad Market Impact** | BEA computers-and-peripherals contribution to real GDP growth < 0 for 2 quarters **and** tech payrolls / IP inflecting down | broad indicators recover 2 quarters |

**Two legs of Ray's Stage 3 were dropped on his own instruction** — see §7.

---

## 3. The metric roster

Tiered by what each is *for*. The discipline that matters: **Tier 1 can trigger a stage; Tier 2
can only confirm one; Tier 3 sizes the consequence and must never trigger anything.**

### Tier 1 — can trigger (daily-to-monthly, genuine lead)

| # | Metric | Detects | Verified source | Lag | Warning | Critical |
|---|---|---|---|---|---|---|
| 0 | **Data-centre vs chip-fab construction divergence** | The only metric with a genuine structural lead (facility decisions precede use by 2-3 yrs) | Census C30 `privsatime.xlsx` / `privsa.xlsx`, rows `Data center` and `Computer/ electronic/ electrical` | ~1 month | chip-fab 12m-ann < −20% while data centre > +20%, 6 months | data centre 6m-ann < 0 **while** chip-fab still < −20% |
| 1 | **Data-centre-zone overnight trough load, net of adjacent control** | Realized, un-gameable AI compute throughput | EIA-930 `eia.gov/electricity/gridmonitor/sixMonthFiles/EIA930_SUBREGION_{YYYY}_{Jan_Jun\|Jul_Dec}.csv`; daily min of `Demand (MW)` by `Sub-Region`; DOM & AEP vs PEP+BC control | **~1 day** | excess < +5pp | excess < +2pp |
| 2 | **ABCP − nonfinancial CP 30d spread** | Warehouse/conduit rollover — the 2007 seizure point | FRED `RIFSPPAAAD30NB` − `RIFSPPNAAD30NB` | daily | ≥ +30bp, 5 days | ≥ +75bp |
| 3 | **Bank loans to nondepository financial institutions** | Bank→private-credit warehouse capacity withdrawal | FRED `LNFACBW027SBOG`, 13-week annualized | weekly | < +5% after a >15% year | < 0% |
| 4 | **Census data-centre construction, 6m-annualized + YoY** | Second derivative of the physical capex cycle | `census.gov/construction/c30/xlsx/privsa.xlsx`, sheet `Priv SA`, row `Data center` (leading whitespace) | ~1 month | 6m-ann < +20%, 3 months | < 0%, 3 months |
| 5 | **CCC − BB OAS dispersion** | Tail-issuer repricing ahead of the index | FRED `BAMLH0A3HYC` − `BAMLH0A1HYBB` | daily | ≥ 8.0pp | ≥ 10.0pp |
| 6 | **IT investment share of all GDP growth, 4q rolling** | Concentration — how much of the growth read is one sector's capex schedule | FRED `Y034RY2Q224SBEA` + `B985RY2Q224SBEA` ÷ `A191RL1Q225SBEA`. **Always display the pp level beside the share** | quarterly | > 25% | 4q contribution in pp turns negative |
| 7 | **Computers & electronics new orders, 3m-avg YoY** | The one clean mechanical trigger the 2000 analogue actually delivered | FRED `A34SNO` | ~1 month | 3 consecutive months decelerating from a local peak | **crosses zero** |

### Tier 2 — confirm only (quarterly filings, ~25-30 day lag)

| # | Metric | Detects | Verified source |
|---|---|---|---|
| 6 | **Capex ÷ OCF**, per filer and median | Self-funding collapse → external-finance dependence | SEC XBRL `PaymentsToAcquirePropertyPlantAndEquipment` ∥ `PaymentsToAcquireProductiveAssets` ÷ `NetCashProvidedByUsedInOperatingActivities` |
| 7 | **Debt + finance leases**, per filer | On- *and* off-balance-sheet leverage | `LongTermDebtNoncurrent` ∥ `LongTermDebt` ∥ `DebtLongtermAndShorttermCombinedAmount`, **plus** `FinanceLeaseLiability` ∥ `…Noncurrent`+`…Current` |
| 8 | **Nvidia DSO + AR-vs-revenue gap + DIO** | Vendor financing — the Lucent/Nortel signature | `AccountsReceivableNetCurrent`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `InventoryNet` (CIK 1045810) |
| 9 | **Supplier/hyperscaler equity stakes in customers** | Circular financing — the loop's closing leg | `EquitySecuritiesWithoutReadilyDeterminableFairValueAmount`; `EquitySecuritiesFvNi`, `PaymentsToAcquireEquitySecuritiesFvNi` |
| 10 | **Cumulative mark-up ÷ carrying amount** | Mark-to-model on illiquid cross-holdings — the Enron shape | `EquitySecuritiesWithoutReadilyDeterminableFairValueUpwardPriceAdjustmentCumulativeAmount` ÷ carrying amount. **Only GOOGL, NVDA, META file it** |
| 11 | **Depreciation rate + cross-operator dispersion** | Useful-life stretching | `Depreciation` ÷ avg(gross PP&E, t-1 and t), **not** the naive gross/dep ratio — see §5 |

### Tier 3 — context and consequence-sizing only (never a trigger)

Real-vs-nominal AI-equipment wedge (FRED `B935RC1Q027SBEA` / `B935RX1Q020SBEA` /
`B935RG3Q086SBEA` / `B935RY2Q224SBEA`); semiconductor input-price inflation (`IZ3344`,
`PCU33443344`) vs server PPI (`PCU3341113341115`); SOX/SPX ratio (`NASDAQSOX` ÷ `SP500`);
fixed-panel utility CWIP (SEC XBRL
`PublicUtilitiesPropertyPlantAndEquipmentConstructionWorkInProgress`); VA/OH excess retail
electricity price and commercial sales vs US (EIA-861M
`eia.gov/electricity/data/eia861m/xls/sales_revenue.xlsx`); BIS net issues
(`WS_DEBT_SEC2_PUB/Q.US.3P.J.1.C.A.A.TO1.A.A.A.A.A.G`).

---

## 4. Today's reading (2026-10-04)

**Stage 1 — Expansion, at the Stage-2 boundary.** Median OCF/Capex across the big five is
**~1.59**, marginally above Ray's 1.5 trigger — but **Oracle (0.57), Amazon (1.06) and CoreWeave
(0.30) are already through it**. The stage has not advanced; three of six names have.
*(Fiscal-year misalignment makes a clean median imprecise; the per-filer reads are the honest
ones.)*

| Leg | Reading | State |
|---|---|---|
| Realized demand validation | DOM trough **+12.7% YoY** vs PEP+BC control **+3.6%** → **+9.1pp excess** | **Load is genuinely arriving.** Verified independently. |
| Warehouse funding | ABCP−CP spread **+0.09pp** (median +0.10 over 4,524 days; 2007-08-10 was +0.39) | **Benign.** Warehouse open. |
| Bank plumbing | NDFI loans **$2,066.8bn**, +20.1% YoY | Still expanding |
| Capex second derivative | Census data centre **$84,950M SAAR, +73.2% YoY**, 3m-ann +179.7% | **Re-accelerating.** No rollover. |
| **Chip-fab leg** | Private computer/electronic/electrical **facility** construction **$52,298M, −45.2% YoY, −59% from its $126,353M Jun-2024 peak** | **Already rolled over — and firing** |
| Concentration | IT equipment + software = **34.2% of all real GDP growth** (4q rolling), 96th pctile vs a 9.3% full-history mean; dot-com peak was 23.4% | Structurally elevated |
| Wealth exposure | Household corporate equities **160% of GDP, Z +4.03**; 2000 peak 87%, 2007 peak 74% | Exposure gauge, not a trigger |
| Credit tail | CCC−BB **10.11pp**, 100th pctile of available window | **Warning — but see §5** |
| Circularity | Hyperscaler non-marketable stakes **~$67bn → ~$427bn** in 15 months; Nvidia AR **$40.7bn → $63.1bn in one quarter**, DSO ~59 days | **Firing** |
| Unit economics | Computers/peripherals deflator **+11.4% YoY** after two decades of declines; real GDP contribution **+0.62pp → −0.09pp** | **Firing** |

**The honest summary: the financing channel is calm, the demand channel is validated, and the
tells that are firing are on the revenue-quality, unit-economics and upstream-capacity side.**
Nothing here says a bust is underway. It says the *quality* of the boom is deteriorating while
its *quantity* still accelerates — the configuration that precedes Ray's Stage 2.

**The one genuinely forward-looking thing on this list is the chip-fab divergence**, and it is
the only item with a structural lead rather than a coincident or lagging read. The two legs of
BIS's own AI-investment measure are moving violently apart: the capacity to *make* the chips is
−59% from peak while the capacity to *house* them is +73% YoY. Either the upstream
capacity-build decision has already turned while the downstream committed build runs on — the
exact sequencing of telecom 1999-2000, where equipment orders rolled over before fibre
deployment did — **or** it is CHIPS-Act expiry with no AI content whatsoever. **The data cannot
distinguish these, and that is the reason it belongs on a monitored page rather than in a
conclusion.** The falsifiable test is whether data-centre construction follows chip-fab down on
the structural 18-24 month lag.

---

## 5. Two traps the build must not fall into

**(a) The naive implied-useful-life ratio will broadcast a false positive at the biggest names.**
Gross PP&E ÷ depreciation rises *mechanically* during a capex boom, because gross PP&E includes
construction-in-progress that is not depreciating. Oracle reads a spurious **+6.1 years** of
"stretching" on the naive ratio; strip CIP ($40.0bn of its $122.7bn gross PP&E) and average the
base, and the entire extension **evaporates**. `ConstructionInProgressGross` is filed by only
4 of 12 relevant filers — **not** by MSFT, AMZN, META, NVDA or CRWV.

The fix is a two-variable discriminant: implied life **and** accumulated-depreciation ÷ gross
PP&E (fleet age). Life ↑ with fleet age ↓ = innocent capex boom. Life ↑ with fleet age flat or ↑
= genuine stretching. **On verified data today, no major filer is in the red-flag quadrant** —
the widely-asserted depreciation-stretching thesis is *not* corroborated by structured filings
once CIP and fleet age are controlled.

The genuinely informative version is **dispersion, not level**: in the same quarter (Jan-2025),
**Meta extended** server lives to 5.5 years (+$2.92bn depreciation benefit, +$1.00/share) while
**Amazon shortened** 6→5 years, explicitly blaming AI obsolescence, taking a $1.0bn net-income
hit. The operator with the largest fleet and the best private information voted against its own
earnings. Monitor the divergence and who is the outlier.

**(b) `LongTermDebtNoncurrent` alone reads Microsoft as deleveraging. It is not.** Microsoft's
finance-lease liabilities grew **5.3x to $66.6bn** while reported long-term debt *fell* from
$50.1bn to $31.1bn. Finance leases are now **2.14x** its bonded debt. Any debt monitor that
misses the lease leg will score the single largest AI capex programme in the world as
deleveraging while it levers up.

---

**(c) Productivity does not discriminate between the two cases, and our existing read would have
said the opposite.** The standard test — "if output per hour accelerates, the boom validates
itself" — fails against the closest analogue. Verified on `OPHNFB`: nonfarm output per hour grew
**+3.05%/yr during the 1996-2000 boom and +3.65%/yr during 2001-2004, after the bust.** The
technology was real; the capital structure that financed it was not. Productivity acceleration
is evidence the *technology* works — it is not evidence the *capital deployed to build it* will
be serviced, and only the second causes a deleveraging.

Direct consequence for this repo: `force_detail._productivity_divergence()` would have printed
"Early-stage competitive advantage" throughout 2001-2004, the four years the capex was being
written off. That is not a bug in its construction — it answers a different question — but it
means **`productivity_score` must not be used as the AI-bust discriminator.** The separation
that does work is Ray's own impulse/persistence inflation split (his 2026-10-03 Ruling 2,
already triaged "ready to implement"): an AI capex bust is the only one of the three candidate
scenarios that pairs *IT contribution to growth collapsing* with *a persistence index that
stays put*. Neither a productivity boom nor an ordinary demand disinflation produces that pair.

---

## 6. Integration — where this goes

Per `Guidance/dashboard_ia_framework.md`, walking the placement list: this is a **curated,
single-topic narrative that deliberately feeds no composite** → **Monitors** group, built on the
shared `_chart_card` from day one (rule 4 in that doc: don't let a new Monitors page start
"plain" and get retrofitted).

- **New page `/ai-capex-cycle`**, Monitors nav group. Operator-gated initially, same pattern as
  `/bubble-gauge` and `/valuations`.
- **Relationship to `/bubble-gauge`:** complementary, not overlapping. That page answers "is the
  *market* late-stage" (valuation, leverage, positioning — aggregate, Dalio's 6 dimensions).
  This one answers "is the *AI capex cycle* breaking" (mechanism-specific, staged). Cross-link
  both ways; do not merge.
- **Signal namespace `ai.*`** — the isolated-force convention alongside `fed.*`/`market.*`/
  `order.*`. Feeds no composite.
- **New module `indicators/ai_capex_cycle.py`** — stage classifier plus metric computation,
  modelled on `debt_cycle_stage.py`.
- **New DB table `ai_capex_stage_snapshots`** — same shape as `debt_cycle_stage_snapshots`
  (stage, confidence, per-feature values, confirmation counters).

### One engine touch — threshold-side only

The "feeds no composite" convention is right, but it is being used to mean "touches nothing,"
and that conflates two different hooks. The repo already has a **threshold-side** hook that is
not a composite input: `compute_dynamic_thresholds()` takes `credit_adj` and `vol_adj`
*multipliers* that widen the chip thresholds without moving the score.

**Recommendation: add a third multiplier, a concentration term**, growth chip only, **off by
default** exactly as dynamic thresholds originally were:

    conc_adj = 1.0 + max(0, (it_growth_share_4q - 0.25) / 0.25) * 0.20

The rationale is statistical, not narrative: when a single investment category supplies more
than a quarter of all GDP growth, a growth composite built from broad-economy signals is partly
reading one sector's capex schedule, and that is a *lower-confidence* read — precisely what
`vol_adj` already encodes for a different reason. At today's 34.2% this widens the growth
threshold ~7%; at the 41.3% cycle peak, ~13%. Bounded, mechanically identical in shape to the
two multipliers that already ship, and it leaves the score untouched.

**This is the highest-value integration in the whole plan, because it changes a reading today
rather than waiting for an event.**

### New providers required

1. **SEC EDGAR XBRL** — the first genuinely new provider. Keyless; a descriptive `User-Agent`
   is mandatory and sufficient; ~10 req/s. **Verified working from this machine.** Three
   non-negotiable implementation details: (i) use `companyconcept`/`companyfacts` per CIK — the
   `frames` API silently omits Alphabet and Oracle and is unusable for a curated watchlist;
   (ii) key on the `end` date, never `fy`/`fp`, which are unreliable (Alphabet tags two different
   periods as `fy=2026, fp=Q2`); (iii) dedupe — duplicate facts per period are visible in the
   raw response and will double-count.
2. **Census C30 direct xlsx** and **EIA-930 direct CSV** — both key-free, both the same
   download-and-cache-with-TTL pattern `bubble_gauge.py` already uses for the FINRA xlsx. No new
   infrastructure.

---

## 7. Confirmed dead ends — do not retry without new information

- **Data-centre ABS tranche spreads / issuance volumes.** Deals are 144A; pricing is dealer-run
  and paid. BIS `WS_DEBT_SEC2_PUB` with `ISSUER_BUS=F` (securitisation vehicles, US) returns
  **empty**. **Ray's own ruling: drop it rather than ship a misleading proxy.**
- **Real-time productivity / unit-cost proxy.** Ray: *"There is no real-time free proxy... If
  you can't get it, drop it."* Dropped — with the §3 Tier-1 metric 1 (realized load) adopted as
  a *utilization* validator, which is a different and weaker claim than productivity.
- **US sector-level corporate OAS (tech/AI).** Does not exist on FRED. Sector splits exist only
  inside the EM aggregates. Not a sourcing failure to work around — it is not there.
- **DRAM/HBM spot and contract prices; token/inference pricing; GPU rental rates.** No free
  time series for any. Use `IZ3344`/`PCU33443344` as the official-statistics substitute.
- **S&P 500 index weights / market-cap concentration.** Paywalled; Stooq's free CSV is now
  bot-gated. Use SOX/SPX for reflexivity and XBRL `NetIncomeLoss` ÷ FRED `CPATAX` for earnings
  concentration instead.
- **Private-credit marks and fund-level AI exposure.** BIS's own figures come from PitchBook
  (licensed). Listed-BDC XBRL is a partial, quarterly, ~10%-coverage workaround at best.
- **Disclosed useful-life ranges, segment-level PP&E, related-party revenue, unconsolidated
  JV/SPV exposure.** None are XBRL-tagged by any relevant filer. Prose only. **This is the
  structural ceiling of the whole accounting channel: the circular relationships are disclosed
  in narrative; only their balance-sheet residue is tagged.**
- **EDGAR full-text-search *frequency* time series.** Saturated (`"useful life"` appears in
  essentially every 10-K) or single-digit noise, and no denominator is obtainable (unbounded
  counts cap at `10000 gte`). **Event-flag on a curated CIK list works and is worth building;
  a frequency index does not.**
- **LBNL interconnection queue** (17 months stale — calibration only); **electricity futures**
  (paid); **turbine/transformer lead times** (no free structured source); **PJM Data Miner API**
  (free key, but redistribution needs Associate Membership — blocks `PUBLIC_MODE`); **SIFMA ABS
  statistics** (404); **FINRA TRACE aggregates** (401/405); **Census `api.census.gov` JSON**
  (key required — the xlsx makes it moot).

---

## 8. Two findings that are NOT about AI and need their own decision

**(a) FRED cut every ICE BofA OAS series to a rolling 3-year window in April 2026.**
Independently reconfirmed this session: `BAMLH0A0HYM2` returns `observation_start: 2023-10-03`,
**794 observations**, and requesting 1997 onward changes nothing. This project already carries
`premium.high_yield_spread` as a live signal in the `premium` force feeding the Disequilibrium
score — and it is **already truncated in our own DB to 863 observations starting 2023-06-19**.
Both the FRED and ALFRED raw-cache parquets are truncated too, so the history is **already lost
locally**. That signal is currently being Z-scored against a three-year window containing no
crisis, which materially understates its own tail.
→ **Recommend: start a daily archive of these series into `raw_cache`/DuckDB immediately** (every
day not captured is permanently lost), and in the interim substitute `BAA10Y` (1986→) or `BAA`
(1919→) for any long-history credit-stress Z-score. **This is a pre-existing defect surfaced by
this research, not a consequence of it.**

**(b) `EIA_API_KEY` in `.env` is the literal placeholder `your_eia_key_here`.** The EIA v2 API
returns `API_KEY_INVALID`. It happens not to matter for this plan — every EIA source used here
(EIA-930, EIA-861M, EIA-860M) is a key-free static download — but any future work assuming a
working EIA key will fail. Registration is free at eia.gov/opendata/register.php.

---

## 8b. How much warning this can actually give — put this on the page

The panel's most uncomfortable conclusion, and it should be visible to anyone reading the page
rather than buried here.

**Three things would give real warning, and free data cannot see any of them:** the *debtor
identity* (the borrowers are SPVs, JVs and neoclouds, invisible in Z.1 — the nonfinancial
corporate financing gap sits at the **3rd percentile of its 80-year history** while BIS
documents a $200bn+ and growing private-credit book); the *creditor concentration* (BIS's own
figures are PitchBook, licensed — no free substitute exists); and the *contract structure*
(take-or-pay commitments, residual-value guarantees and circular vendor financing live in 10-K
prose, not in any time series).

**And the two channels that dominate the damage arithmetic are the two least forecastable.** The
wealth channel is the larger of the two and has read "unprecedented" for five years. The GDP
channel is immediate by construction — by the time the contribution turns negative, the print
has already happened.

**Lead times the closest analogue actually delivered** (reconstructed from FRED this session):
equity peak → recession **12 months**; new-orders YoY zero-cross → recession **~2 months**;
capex level peak → recession **2 quarters**; the financing gap peaked **3 quarters after** the
equity top, i.e. it confirmed and never warned. AI's collateral depreciates faster than
dot-com's (3-5yr GPUs vs 20-30yr fibre), so **expect lead time at or below the dot-com two
quarters.** BIS's own calibration sentence is the one to keep: *the largest contraction was
after the US dot-com boom, even though that boom was small relative to GDP.* Size does not
predict damage — concentration and financing structure do, and on both this cycle is worse.

**So: most of this page is confirmation infrastructure.** That has real value — it is how you
avoid misreading an investment bust as a benign disinflation (§5c) — but it is not foresight.
The two genuine exceptions are the chip-fab divergence (§4, a structural 18-24 month lead) and
the concentration multiplier (§6, actionable today without any forecast). **The page should
carry its own lead-time table on its face. A monitor that documents its blindness is worth more
than one that implies foresight it does not have.**

---

## 9. Build sequence

**Phase 1 — the trigger layer. ✅ SHIPPED 2026-10-04** (`docs/worklog.md` same date).
`indicators/ai_capex.py` (all 8 Tier-1 metrics), `dashboard/ai_capex_monitor.py` +
`/ai-capex-cycle` (Monitors nav, operator-gated), `loader.fetch_url_cached()`, the `conc_adj`
growth-threshold multiplier (off by default), and the ICE BofA spread archive. 24 new tests;
suite 701 passing, zero failures. Three real bugs were caught by RUNNING it rather than
inspecting it — a two-digit-year pivot, a partial-month contamination, and a silent
date-alignment failure in conc_adj. See the worklog entry.
**Phase 2 — SEC XBRL provider + the filings layer.** New `fetch_sec_xbrl_concept()` in
`loader.py` with the dedup/end-date/tag-ladder discipline from §6; Tier 2 metrics 6-11.
**Phase 3 — the stage classifier.** `ai_capex_cycle.py` + `ai_capex_stage_snapshots` table +
pipeline pass, once Phases 1-2 supply every feature its entry conditions need.
**Phase 4 — context layer and cross-links.** Tier 3 charts; `/bubble-gauge` cross-link.

**Start the daily spread archive (§8a) in Phase 1 regardless** — it is two lines of work and the
cost of delay is permanent.

---

## 10. Open decisions for the owner

1. **Should an AI-capex term feed the Growth composite?** Ray says there is a real case — AI
   capex is ~44% of recent GDP growth, so a stall is a growth event the current basket catches
   late — but only *"if you can track it cleanly... Don't average it in with everything else;
   keep it explicit."* **Recommendation: not initially.** The Census series is US-only and
   revision-heavy (one month revised +22%; 18 of 18 historical rollover fires were false
   positives). The BEA GDP-contribution series `B935RY2Q224SBEA` is the cleaner candidate if we
   ever do. Logged as open, not closed.
2. ✅ **DECIDED — operator-gated** (shipped; `/ai-capex-cycle` added to
   `OPERATOR_ONLY_ROUTES`). Split panel. `/bubble-gauge` is gated because it reuses
   `/valuations` data; **none of the sources in this plan carries a licensing constraint**, so
   the macro desk argued for public. Recommend **operator-only initially** anyway, on the
   narrower ground that a page whose own header says "this is mostly confirmation
   infrastructure" needs its caveats read, and flip it to public once the copy is settled.
3. **How many filers in the XBRL watchlist?** Recommend the six that carry the signal
   (MSFT, GOOGL, AMZN, META, ORCL, NVDA) plus CoreWeave as the leveraged-tier canary — not a
   broad panel, which multiplies tag-ladder maintenance for little gain.
4. ✅ **DECIDED AND SHIPPED — `conc_adj` adopted.** Off by default, growth chip only, toggled
   from the Regime Thresholds modal next to the dynamic-thresholds switch. Verified live: at
   today's 34.2% share it widens the US growth threshold **+7.4%**, the inflation chip is
   untouched, and 23 of 562 historical months are affected. US-only — returns None for every
   other country, so conc_adj falls back to 1.0 there.
5. **Take the impulse/persistence split (§5c) to the next Ray consult?** His own Ruling 2 is
   already triaged "ready to implement"; this work gives it a second, independent reason to be
   built — it is the key to separating an AI capex bust from a benign disinflation.
