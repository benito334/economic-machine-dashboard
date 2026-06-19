# Master Technical Specification (v2): Global Economic Machine Dashboard

> **Build target:** A diagnostic, cross-country macro-regime dashboard in the Ray Dalio "Economic Machine" tradition. This revision integrates the original technical spec with the structural variable families and country coverage from Ray's outline, and is written to be handed off to a VS Code coding agent (Claude).

---

## Section 0: Document Control, Scope & What Changed in v2

### 0.1 Purpose of this revision
v1 was an excellent **US-centric, high-frequency cyclical terminal** but only partially matched Ray's outline, which calls for a **lower-frequency, cross-country, structural** view. v2 closes the structural and geographic gaps while keeping v1's engineering strengths (the `Signal` contract, the normalization engine, point-in-time vintages, the quadrant UI).

### 0.2 Explicitly OUT of scope for this build (moved to a separate project)
The following are **deferred to a separate "Allocation Layer" project** and must **not** be built here:
- Risk-parity / risk-budgeting weighting, volatility estimation, cross-asset correlation matrices, and any portfolio-construction or allocation output.
- Re-weighting methodology for the global aggregate. **Decision:** the global aggregate view in Section 6 stays as a **descriptive GDP-weighted composite only** (no change to weighting scheme in this build). The choice of weighting methodology is owned by the Allocation Layer project.

This build delivers a **diagnostic** (where each economy sits across growth/inflation and the structural forces), not an **allocator**.

### 0.3 Summary of additions in v2
1. Six previously-absent structural variable families added to the US catalog (Section 4): **fiscal fundamentals, external/trade balances, capital flows, currency valuation, demographics, political/governance risk**, plus **NIIP**, **TFP**, **labor-force participation**, and **R&D intensity**.
2. The **Five Big Forces** are now actually instrumented end-to-end, fixing a v1 inconsistency where the Disequilibrium Score claimed to average across five lenses that were never built.
3. Country coverage expanded from 4 to **Ray's full 10** (US, Eurozone, Japan, China, UK, India, Brazil, Russia, South Korea, Saudi Arabia) via a **US-first phased rollout** with per-country human verification.
4. A **harmonized cross-country data-source catalog** (Section 8) with exact access methods, scoped into a free/buildable tier and a deferred/manual tier.
5. **Named back-test scenarios** (Section 7) leveraging the existing vintage infrastructure.
6. A **geopolitical-risk overlay** in the UI (Section 5), distinct from the existing data-conflict panel.
7. An **Agent Build Guardrails** section (Section 9) targeting the specific failure modes that could sink the build.

### 0.4 Critical infrastructure note — ALFRED / vintages
Effective **January 5, 2026**, FRED *web user accounts* can no longer save archival ("ALFRED") data lists and graphs. **This does NOT affect the FRED *API*.** Point-in-time vintages remain fully available programmatically via the API's real-time parameters (`realtime_start`, `realtime_end`) and the `fred/series/vintagedates` endpoint, and `fredapi` still exposes them (`get_series_vintage_dates`, `get_series_as_of_date`, etc.). **The build must obtain vintages through the API, not the website account feature.** A free registered FRED API key is required.

---

## Section 1: Theoretical Context & Macroeconomic Philosophy

*(Retained from v1, with the Five Forces now mapped to instrumented lenses — see §1.5.)*

### 1.1 The Economic Machine Framework
The dashboard is designed around Ray Dalio's thesis that the economy is a mechanical system driven by timeless cause-and-effect linkages that operate consistently across geographies and historical epochs. The machine is powered by three forces: productivity growth, the short-term debt cycle, and the long-term debt cycle.

Every transaction reflects money or credit exchanged for goods, services, or financial assets. The master synthesis variable is therefore **Nominal Spending** (≈ Nominal GDP): the total dollars chasing items, financed by money, credit, and baseline income. This spending split dictates real growth and price-inflation outcomes.

Asset prices move on **surprises** — shifts in growth or inflation relative to what the market has already discounted. Every indicator is therefore analyzed relative to its own history, its momentum, and its distance from a structural equilibrium, never as an isolated raw number.

### 1.2 The Two Core Structural Spreads
1. **Nominal Spending vs. Output Capacity of Labor:** `NGDP Growth − (Payroll Growth + Productivity Growth)`. Excess nominal spending over labor+productivity capacity manifests as structural inflation.
2. **Nominal GDP Growth vs. Bond Yields:** `NGDP Growth − 10Y Government Yield`. When nominal growth outpaces risk-free yields, real returns favor equities/commodities over fixed income; when yields exceed nominal growth, the incentive flips toward cash/fixed income.

### 1.3 The Four Macro Environments ("Seasons")
| Macro Environment | Growth | Inflation | Structural Asset Alignments (descriptive only) |
| :--- | :---: | :---: | :--- |
| **Expansion (Goldilocks)** | ↑ | ↓/stable | Equities, corporate credit, pro-cyclicals |
| **Inflationary Boom** | ↑ | ↑ | Commodities, gold, TIPS |
| **Disinflationary Slowdown** | ↓ | ↓ | Long-duration govt bonds, defensive equities |
| **Stagflation** | ↓ | ↑ | Gold, commodities, TIPS; cash-like shelter |
| **Debt Stress / Crisis** | ↓ sharply | volatile | Liquidity, cash, gold |

> Note: asset-class alignments are shown as **descriptive context** only. No allocation logic is computed in this build (see §0.2).

### 1.4 Systemic Excess & the Bubble Gauges
Dalio's six bubble dimensions, used as programmatic flags: (1) price levels vs. valuation norms; (2) discounting of unsustainable conditions; (3) influx of new/unsophisticated buyers; (4) uniformly bullish sentiment; (5) leverage-financed purchases; (6) extended forward/speculative purchases.

### 1.5 The Five Big Forces — now instrumented
Each force now maps to concrete indicators so the Disequilibrium Score (§3.1) can actually be computed across all five:

| Force | Instrumented by (Section 4 lens) |
| :--- | :--- |
| **Debt / Money Cycle** | Lens D (Credit & Debt) + Lens C (Policy/Money) |
| **Internal Order / Conflict** | Lens H (Governance & Political Risk) — *new* |
| **External Order / Conflict** | Lens F (External & Trade) + Lens G (Capital Flows & Currency) — *new* |
| **Climate / Nature** | Lens I (Climate/Disaster cost) — *new, deferred-tier data* |
| **Technology / Inventiveness** | Lens A additions: TFP & R&D intensity — *new* |

---

## Section 2: Architectural Design & Data Model

### 2.1 Object Class Models
- **`IndicatorConcept` (country-agnostic):** a universal macro relationship (e.g. `core_inflation`). Holds immutable system ID, assigned macro force, timing class (leading/coincident/lagging), transformation method, and an explicit timeless cause-effect `linkage` string.
- **`CountryBinding` (country-specific):** binds a concept to a concrete source. Maps the concept to a provider + series identifier, declares local frequency, regional equilibrium constants, **source tier** (`free` | `deferred`), and **vintage availability** (`vintage` | `latest_only`).

### 2.2 The Signal Interface Contract
Every data point emits a standardized `Signal` so a downstream rules engine can query fields without schema translation. v2 adds three fields (`source_tier`, `vintage_available`, `provider`) to make cross-country data-quality explicit.

```python
Signal = {
  "id": "us.inflation.core_pce",          # Namespace: country.force.concept
  "country": "US",                         # ISO identifier
  "force": "inflation",                    # growth|inflation|policy|credit|risk_premium|
                                           #   external|capital_flow|currency|demographics|
                                           #   governance|climate|master
  "lead_lag": "coincident",                # leading|coincident|lagging
  "as_of": "2026-05-31",                   # release date of the underlying point
  "value": 0.031,
  "units": "yoy_pct",
  "level_percentile": 0.78,
  "zscore": 0.9,
  "change_1m": 0.001,
  "change_3m": -0.002,
  "change_12m": -0.015,
  "direction": "falling",                  # rising|falling|flat
  "equilibrium_estimate": 0.02,
  "distance_from_equilibrium": 0.011,
  "surprise": null,                        # actual − consensus (if wired)
  "is_constructed": false,
  "is_proxy": false,
  "is_stale": false,
  "provider": "FRED",                      # NEW: FRED|WorldBank|IMF|OECD|ECB|Eurostat|BIS|manual
  "source_tier": "free",                   # NEW: free|deferred
  "vintage_available": true,               # NEW: true only where point-in-time data exists
  "linkage": "Core PCE persistence drives Fed reaction and the discount rate",
  "source": "FRED:PCEPILFE"
}
```

---

## Section 3: Computational Core & Normalization Engine

For every registered series the engine runs five steps before archiving:
1. **Frequency Harmonization:** preserve native frequency for statistics; index to a unified cadence for display. Never forward-fill past a release cycle without setting `is_stale=true`. Track the native `as_of`.
2. **Transformational Analysis:** index levels → YoY %; yields and spreads kept as absolute levels. (Annual cross-country series may also be held as levels with YoY where meaningful.)
3. **Momentum Tracking:** absolute changes over 1m / 3m / 12m (or 1q/4q for quarterly/annual series).
4. **Historical Normalization:** every transformed point → Z-Score and Percentile Rank against a long historical window, so heterogeneous concepts become comparable.
5. **Equilibrium Reference Engine:** read explicit neutral constants from config; map distance-from-equilibrium in standardized units.

> **Cross-country note:** annual structural series (debt, fiscal, demographics, governance) have short histories per country. Where the historical window is too short for a stable Z-score (< ~15 observations), the engine must emit the percentile/Z-score with a `low_history` flag rather than a falsely precise value.

### 3.1 Calculated Master Composites
- **Growth Score:** weighted index over real-economy signals (payrolls, real PCE, industrial production, PMIs).
- **Inflation Score:** weighted index over price signals (core PCE, CPI, wages, breakevens, the Nominal-Spending-vs-Capacity spread).
- **Regime Quadrant Mapping:** cross-references Growth and Inflation direction vectors into one of the four seasons, with a **Confidence Score (%)** = mathematical agreement among inputs; high variance returns low confidence rather than a forced label.
- **Disequilibrium Score:** averages absolute distance-from-equilibrium across **all five** structural lenses (now genuinely computable — see §1.5).

---

## Section 4: US Mapping Matrix (Phase 1 Target)

> **ID verification convention.** `✓` = verified against the live provider during spec authoring. `⚠ VERIFY` = candidate ID the agent **must** confirm before ingestion via the provider's search API (FRED: `fred/series/search`; World Bank: `/v2/indicator?format=json&search=`). **Never ingest a `⚠` ID without a successful metadata lookup first** (see §9.1).

### 4.1 Master Synthesis Constructs
| Concept ID | Source | Freq | Timing | Formula / Linkage |
| :--- | :--- | :---: | :---: | :--- |
| `master.gdp_nominal` | FRED:`GDP` ✓ | Q | Lagging | Total nominal dollar spending. |
| `master.gdp_real` | FRED:`GDPC1` ✓ | Q | Lagging | Physical production volume. |
| `master.gdp_deflator` | FRED:`GDPDEF` ✓ | Q | Lagging | Broadest domestic price index. |
| `master.spending_vs_labor` | *Derived* | Q | Leading | `YoY(GDP) − (YoY(PAYEMS) + YoY(OPHNFB))`. Structural demand-inflation pressure. |
| `master.ngdp_minus_yield` | *Derived* | Q/D | Coincident | `YoY(GDP) − DGS10`. >0 favors equities over bonds. |

### 4.2 Macro Lenses

#### Lens A — Growth Force (incl. new Technology/Productivity additions)
| Concept | FRED ID | Freq | Timing |
| :--- | :--- | :---: | :---: |
| `growth.payrolls` | `PAYEMS` ✓ | M | Coincident |
| `growth.unemployment` | `UNRATE` ✓ | M | Lagging |
| `growth.job_openings` | `JTSJOL` ✓ | M | Leading |
| `growth.industrial_prod` | `INDPRO` ✓ | M | Coincident |
| `growth.retail_sales` | `RSAFS` ✓ | M | Coincident |
| `growth.real_pce` | `PCEC96` ✓ | M | Coincident |
| `growth.capacity_util` | `TCU` ✓ | M | Coincident |
| `growth.productivity` | `OPHNFB` ✓ | Q | Lagging |
| `growth.pmi_proxy` | `GACDFSA066MSFRBPHI` ✓ *(corrected from spec; original ID was wrong)* | M | Leading |
| **`growth.labor_force_part`** *(new)* | `CIVPART` ✓ | M | Coincident |
| **`growth.tfp`** *(new)* | `RTFPNAUSA632NRUG` ⚠ VERIFY (Penn World Table TFP, annual) | A | Structural |
| **`growth.rnd_intensity`** *(new)* | WorldBank:`GB.XPD.RSDV.GD.ZS` ✓ (R&D % of GDP) | A | Structural |

> TFP note: the US has no clean high-frequency TFP series. Options: PWT annual (`RTFPNAUSA632NRUG`) or the SF Fed's quarterly utilization-adjusted TFP (CSV download, not on FRED). Prefer PWT for cross-country consistency; mark `is_proxy=true`.

#### Lens B — Inflation Force
| Concept | FRED ID | Freq | Timing |
| :--- | :--- | :---: | :---: |
| `inflation.cpi_headline` | `CPIAUCSL` ✓ | M | Coincident |
| `inflation.cpi_core` | `CPILFESL` ✓ | M | Coincident |
| `inflation.pce_core` | `PCEPILFE` ✓ | M | Coincident |
| `inflation.wages` | `CES0500000003` ✓ | M | Lagging |
| `inflation.breakeven_5y` | `T5YIE` ✓ | D | Leading |
| `inflation.breakeven_10y` | `T10YIE` ✓ | D | Leading |
| `inflation.crude_oil` | `DCOILWTICO` ✓ | D | Leading |
| **`inflation.commodity_index`** *(new)* | `PPIACO` ⚠ VERIFY (broad PPI all commodities) | M | Leading |

#### Lens C — Monetary Policy & Rates
| Concept | FRED ID | Freq | Timing |
| :--- | :--- | :---: | :---: |
| `policy.fed_funds` | `DFF` ✓ | D | Coincident |
| `policy.real_fed_funds` | *Derived* `DFF − YoY(CPILFESL)` | D | Coincident |
| `policy.yield_2y` | `DGS2` ✓ | D | Coincident |
| `policy.yield_10y` | `DGS10` ✓ | D | Coincident |
| `policy.real_yield_10y` | `DFII10` ✓ | D | Coincident |
| `policy.fed_balance_sheet` | `WALCL` ✓ | W | Coincident |
| **`policy.monetary_base_gdp`** *(new)* | *Derived* `WALCL / (GDP nominal)` | Q | Coincident |

#### Lens D — Credit & the Debt Cycle
| Concept | FRED ID | Freq | Timing |
| :--- | :--- | :---: | :---: |
| `credit.debt_service_ratio` | `TDSP` ✓ | Q | Leading |
| `credit.bank_loans` | `TOTBKCR` ✓ | W | Coincident |
| `credit.lending_standards` | `DRTSCILM` ✓ | Q | Leading |
| `credit.gov_debt_gdp` | `GFDEGDQ188S` ✓ | Q | Leading |
| **`credit.household_debt_gdp`** *(new)* | `HDTGPDUSQ163N` ⚠ VERIFY (BIS household debt/GDP) | Q | Leading |
| **`credit.corporate_debt`** *(new)* | `BCNSDODNS` ⚠ VERIFY (nonfin corp debt securities & loans) | Q | Leading |

#### Lens E — Risk Premiums
| Concept | FRED ID | Freq | Timing |
| :--- | :--- | :---: | :---: |
| `premium.yield_curve_10y2y` | `T10Y2Y` ✓ | D | Leading |
| `premium.yield_curve_10y3m` | `T10Y3M` ✓ | D | Leading |
| `premium.credit_spread_corp` | `BAA10Y` ✓ | D | Leading |
| `premium.high_yield_spread` | `BAMLH0A0HYM2` ✓ | D | Leading |

#### Lens F — External & Trade *(new)*
| Concept | Source | Freq | Timing |
| :--- | :--- | :---: | :---: |
| `external.current_account` | FRED:`IEABC` ✓ (quarterly, SA, $) | Q | Leading |
| `external.current_account_gdp` | WorldBank:`BN.CAB.XOKA.GD.ZS` ✓ (% GDP, annual) | A | Leading |
| `external.exports_gdp` | WorldBank:`NE.EXP.GNFS.ZS` ✓ | A | Coincident |
| `external.imports_gdp` | WorldBank:`NE.IMP.GNFS.ZS` ✓ | A | Coincident |
| `external.niip` | FRED:`IIPUSNETIQ` ✓ (Net Intl Investment Position, quarterly) | Q | Structural |

#### Lens G — Capital Flows & Currency *(new)*
| Concept | Source | Freq | Timing |
| :--- | :--- | :---: | :---: |
| `capital.fdi_net_inflows_gdp` | WorldBank:`BX.KLT.DINV.WD.GD.ZS` ✓ | A | Leading |
| `capital.portfolio_flows` | IMF BOP / Treasury TIC ⚠ VERIFY (US: TIC monthly) — **deferred to Phase 1A-iii** | M/Q | Leading |
| `currency.reer` | FRED:`RBUSBIS` ✓ (BIS Real Broad Effective Exch Rate, US) | M | Coincident |
| `currency.reer_xcountry` | WorldBank:`PX.REX.REER` ✓ (fallback for non-BIS countries; `is_proxy=true`) | A | Coincident |
| `currency.ppp_gap` | *Derived* from OECD/WB PPP conversion vs market FX ⚠ VERIFY — **deferred to Phase 1A-iii** | A | Structural |

> Prefer **BIS REER via FRED** (`RB<country>BIS` pattern — e.g. `RBUSBIS`, monthly, broad) for all countries BIS covers; fall back to World Bank `PX.REX.REER` only where BIS coverage is missing. SWF holdings (Ray's third capital-flow item) have no reliable free programmatic feed → **deferred tier** (§8.2).

#### Lens H — Governance & Political Risk *(new — deferred slots only)*
Free programmatic substitute for paywalled EIU/ICRG: **World Bank Worldwide Governance Indicators (WGI)**, annual, all countries.

> ⚠ **API finding (2026-06-18):** All five WGI `.EST` series are **deleted/archived from the WB v2 indicator API** — confirmed via direct REST calls. The `✓` marks in the original spec were incorrect. Deferred slots created in `us_bindings.yaml` with `verified: false`, `source_tier: deferred`. Resolution: WGI bulk CSV download from the WGI portal, or a future WB API endpoint. See session-checklist G-03.

| Concept | WorldBank ID | Freq | Timing | Status |
| :--- | :--- | :---: | :---: | :---: |
| `governance.political_stability` | `PV.EST` | A | Structural | ⛔ API unavailable |
| `governance.control_of_corruption` | `CC.EST` | A | Structural | ⛔ API unavailable |
| `governance.govt_effectiveness` | `GE.EST` | A | Structural | ⛔ API unavailable |
| `governance.rule_of_law` | `RL.EST` | A | Structural | ⛔ API unavailable |
| `governance.regulatory_quality` | `RQ.EST` | A | Structural | ⛔ API unavailable |

#### Lens I — Climate / Nature *(new, deferred-tier data)*
| Concept | Source | Freq | Timing |
| :--- | :--- | :---: | :---: |
| `climate.disaster_loss` | EM-DAT (license) / WRI Climate Knowledge Portal | A | Structural |

> EM-DAT requires a (free for non-commercial) registered account and is not a clean API → **deferred/manual tier** (§8.2). Build the lens slot and `IndicatorConcept` now; leave the binding as `manual` until data is provisioned.

#### Fiscal Fundamentals *(new — folds into Lens D / "Debt-Money" force)*
| Concept | Source | Freq | Timing |
| :--- | :--- | :---: | :---: |
| `fiscal.primary_balance` | *Derived* US: `FYFSD` (surplus/deficit) net of `FYOINT` (net interest), annual ⚠ VERIFY; cross-country: IMF WEO `GGXONLB` (primary net lending/borrowing % GDP) ⚠ VERIFY | A | Leading |
| `fiscal.revenue_gdp` | WorldBank:`GC.REV.XGRT.GD.ZS` ✓ (revenue excl. grants % GDP) | A | Coincident |
| `fiscal.structural_balance` | IMF WEO `GGSB` ⚠ VERIFY (structural balance % potential GDP) | A | Leading |

#### Demographics *(new)*
| Concept | WorldBank ID | Freq | Timing |
| :--- | :--- | :---: | :---: |
| `demo.population_growth` | `SP.POP.GROW` ✓ | A | Structural |
| `demo.age_dependency` | `SP.POP.DPND` ✓ | A | Structural |
| `demo.urbanization` | `SP.URB.TOTL.IN.ZS` ✓ | A | Structural |
| `demo.labor_force_part_wb` | `SL.TLF.CACT.ZS` ✓ (cross-country LFPR, modeled ILO) | A | Structural |

---

## Section 5: Full-Stack User Interface Spec

The frontend is a Streamlit diagnostic terminal, scannable multi-row layout.

### 5.1 Grid Layout
```
-----------------------------------------------------------------------------------------
[TOP HUD] Regime Quadrant | Confidence % | Momentum Vectors | Disequilibrium Speedometer
-----------------------------------------------------------------------------------------
[ROW 1] Interactive 4-Quadrant Macro Map (Growth × Inflation) + 12-month connected tail
-----------------------------------------------------------------------------------------
[ROW 2] "What Changed" Delta Feed | Cross-Signal Conflict Panel | Geopolitical-Risk Overlay
-----------------------------------------------------------------------------------------
[ROW 3] Composite Accordion Drill-Downs (Leading -> Coincident -> Lagging within each):
  [>] Nominal Spending Master Indicators
  [>] Growth Force (incl. productivity, TFP, R&D)
  [>] Inflation Force
  [>] Monetary Policy & Rates
  [>] Credit, Debt & Fiscal
  [>] External & Trade
  [>] Capital Flows & Currency
  [>] Governance & Political Risk
  [>] Risk Premiums
  [>] Demographics & Structural (low-frequency)
-----------------------------------------------------------------------------------------
[ROW 4] Economic Releases Calendar | Historical Revisions / Data-Quality Log
-----------------------------------------------------------------------------------------
```

### 5.2 Intelligent Panels
- **"What Changed This Week":** rolling 7-day delta thresholds across high-frequency metrics; show top 5 absolute moves as a labeled log, e.g. `[Jobless Claims Rose > 6-Month MA (Negative Shift)]`. Low-frequency structural lenses are excluded from the weekly feed (they update quarterly/annually) and instead surface in a separate **"What Changed This Quarter"** view.
- **Cross-Signal Conflict Panel:** flags divergence between leading and lagging data, e.g. `[System Disagreement: Moderate. Leading new orders + tighter bank standards weakening, BUT payrolls coincidentally strong]`. *(This is about data disagreement, not geopolitics.)*
- **Geopolitical-Risk Overlay** *(new — Ray's structure item #4):* renders Lens H (WGI governance scores) as a per-country risk band, color-coded by percentile, with a delta vs. prior reading. Distinct from the Conflict Panel above.

### 5.3 Standard Component Rules
- **Per-indicator row:** inline sparkline, current raw value, directional arrow, and a **Percentile-Color Badge**.
- **Dynamic heat coloring:** never by arbitrary raw levels — color by Z-Score / Percentile:
  - `Z > +1.0 / pct > 85`: elevated / expansionary (deep orange → dark red)
  - `Z < −1.0 / pct < 15`: depressed / restrictive / stressed (deep blue → navy)
  - Rows with `low_history=true` render with a muted/striped badge and a tooltip caveat.
- **Causal-Linkage Tooltips:** hovering an indicator name renders its hardcoded `linkage` text verbatim.
- **Data-quality badges:** rows display small markers for `is_proxy`, `is_stale`, and `vintage_available=false` so the user can see comparability limits at a glance.

---

## Section 6: Global & Multi-Country Expansion Architecture

### 6.1 Country Coverage (Ray's full 10)
Launch footprint: **US, Eurozone (Germany core), Japan, China, UK, India, Brazil, Russia, South Korea, Saudi Arabia** — ~80% of global GDP, the main reserve-currency issuers, and full coverage of the growth/inflation quadrants (incl. the commodity-exporter and high-growth tilts: Brazil, Russia, Saudi, India).

Rollout is **phased and verified per country** (see §7), not all-at-once.

### 6.2 Multi-Country UI Hierarchy
1. **Global Aggregate View:** a **descriptive GDP-weighted composite** of growth, inflation, and liquidity impulses. *(Weighting scheme unchanged in this build; methodology owned by the Allocation Layer project — §0.2.)*
2. **Country Dropdown Selector:** toggling swaps the active `CountryBinding` set, re-pointing calculations to that country's sources.

### 6.3 Harmonized Cross-Country Source Routing
**Comparability principle:** for the structural variable families (debt, fiscal, external, capital, currency, demographics, governance), prefer a **single harmonized provider across all countries** (World Bank WDI / IMF WEO/IFS / OECD) rather than stitching national bureaus, to avoid definition drift. Use national/central-bank sources only for the **high-frequency cyclical** lenses (rates, CPI, PMI) where harmonized feeds lag.

| Lens / Concept | Harmonized cross-country source | Per-country high-frequency source |
| :--- | :--- | :--- |
| Policy anchor / rates | — | Fed / ECB / BOJ / PBOC / BoE / RBI / BCB / CBR / BoK / SAMA |
| Benchmark 10Y bond | — | UST / Bund / JGB / CGB / Gilt / IGB / NTN-B / OFZ / KTB / (KSA sukuk) |
| Consumer inflation | — | US CPI/PCE, Eurostat HICP, BOJ/Stats Bureau, NBS, ONS, MOSPI, IBGE, Rosstat, Statistics Korea, GASTAT |
| Core growth / PMI | OECD GDP | ISM, S&P Global / Caixin / Tankan / national PMIs |
| Debt (govt/hh/corp) | BIS + World Bank `GC.DOD.TOTL.GD.ZS` | — |
| Fiscal (primary/structural/revenue) | IMF WEO (`GGXONLB`, `GGSB`), WB `GC.REV.XGRT.GD.ZS` | — |
| External (CA, exports, imports, NIIP) | World Bank `BN.CAB.XOKA.GD.ZS`, `NE.EXP/IMP.GNFS.ZS`; IMF IIP | — |
| Capital flows / currency | IMF BOP; BIS REER (`RB<ccy>BIS`) | — |
| Governance / political risk | World Bank WGI (`PV/CC/GE/RL/RQ.EST`) | — |
| Demographics | World Bank (`SP.POP.*`, `SP.URB.*`) | — |
| Commodities (EM drivers) | EIA / IEA / World Bank "Pink Sheet" | — |

### 6.4 Sovereign Debt-Cycle Risk Adjustments (EM profiles)
The Credit/Debt/Fiscal lens must bifurcate leverage for EM countries:
- **Domestic-currency debt burden** (risk: managed devaluation, monetization, inflation).
- **Foreign-currency (FX) debt burden** (risk: hard default, balance-of-payments crisis).
- **FX Reserve Runway** = FX reserves ÷ average monthly imports (import-coverage months).

### 6.5 Cross-Border Net Liquidity Impulse
`Global Liquidity = Fed BS + ECB BS + BOJ BS + PBOC injections (USD-equivalent)`, compiled from each central bank's balance-sheet series. *(This is a descriptive liquidity gauge, not an allocation input.)*

---

## Section 7: Implementation Sub-Phases & Code Milestones

> **Sequencing principle:** prove the full architecture **end-to-end on the US with the complete expanded indicator set first**. Only then add countries one at a time, each with a human verifying its bindings. Do **not** attempt to instantiate all 10 countries × all sources in one pass — that is the primary failure path (§9).

### ✅ Phase 1A-i — FRED lenses A–E + Master (COMPLETE 2026-06-18)
1. ✅ DuckDB schema (`store/store.py`), Pydantic `Signal` + `CountryBinding` models (`indicators/models.py`)
2. ✅ `fredapi` loader with parquet disk cache, tenacity retry (`indicators/loader.py`)
3. ✅ Transform (YoY%, level, spread), normalize (Z-score, percentile, momentum, equilibrium distance, staleness) — `indicators/transform.py`, `indicators/normalize.py`
4. ✅ Pipeline orchestrator with Pass 1 (FRED) + Pass 2 (derived) — `indicators/pipeline.py`
5. ✅ `config/us_bindings.yaml` — 29 FRED bindings (lenses A–E + Master) + 4 derived; all `verified: true`
6. ✅ 51 unit + integration tests passing (`tests/`)
7. ✅ **Acceptance gate passed:** 37/37 signals ingesting, 0 empty, 0 errors, 0 sanity warnings
   - Corrected series ID: Philly Fed PMI `GACDISA066MSFRBPHI` → `GACDFSA066MSFRBPHI`
   - Documented: ICE BofA HY spread (BAMLH0A0HYM2) truncated to 2023-06-19 on FRED (3yr window only); primary long-history credit premium is BAA10Y

### ✅ Phase 1A-ii — World Bank lenses F/G/H/demographics (COMPLETE 2026-06-18)
1. ✅ `fetch_wb_series()` added to `indicators/loader.py` — direct REST API (`/v2/country/{iso}/indicator/{code}?format=json`), parquet cache, tenacity retry. Note: `wbgapi` library has JSON-decoding issues in this environment; direct `requests` used instead.
2. ✅ WB + new FRED bindings added to `config/us_bindings.yaml`:
   - Lens F (External): `external.current_account` (FRED IEABC), `external.current_account_gdp`, `external.exports_gdp`, `external.imports_gdp` (WB), `external.niip` (FRED IIPUSNETIQ)
   - Lens A supplement: `growth.rnd_intensity` (WB GB.XPD.RSDV.GD.ZS)
   - Lens G (Capital/Currency): `capital.fdi_net_inflows_gdp` (WB), `currency.reer` (FRED RBUSBIS), `currency.reer_xcountry` (WB PX.REX.REER, `is_proxy=true`)
   - Lens H (Governance): 5 deferred slots — WGI `.EST` series confirmed deleted/archived from WB v2 API (2026-06-18); resolution requires WGI bulk CSV download (see session-checklist G-03)
   - Demographics: population growth, age dependency, urbanization, WB LFPR (all WB)
3. ✅ Pipeline updated with WorldBank Pass 2; derived promoted to Pass 3
4. ✅ 9 new WB fetcher tests; full suite 60/60 passing
5. ✅ **Acceptance gate passed:** 50/50 signals ingesting, 0 empty, 0 errors, 0 sanity warnings

### Phase 1A-iii — IMF/OECD fiscal lenses ✅ COMPLETE (2026-06-18)
1. ✅ `fetch_imf_series()` added to `loader.py` using IMF Datamapper REST API (`https://www.imf.org/external/datamapper/api/v1/{indicator}/{iso3}`). No auth required. ISO-3 country codes (USA). Current-year estimates and future forecasts are excluded. Parquet cache + tenacity retry.
2. ✅ FRED fiscal bindings verified and added: `FYFSD` ✓ (federal surplus/deficit, A), `FYOINT` ✓ (interest outlays, A), `PPIACO` ✓ (broad PPI, M), `HDTGPDUSQ163N` ✓ (household debt/GDP, Q), `BCNSDODNS` ✓ (corporate debt, Q), `RTFPNAUSA632NRUG` ✓ (TFP PWT, A — was last ⚠ VERIFY item)
3. ✅ IMF bindings: `pb` ✓ (primary balance % GDP), `GGCB_G01_PGDP_PT` ✓ (structural/cyclically-adjusted balance % potential GDP). Note: GGXONLB/GGSB are not the Datamapper IDs; actual IDs are `pb` and `GGCB_G01_PGDP_PT`.
4. ✅ WB: `GC.REV.XGRT.GD.ZS` ✓ bound (`fiscal.govt_revenue_gdp`)
5. ✅ Deferred `climate.disaster_loss` manual slot added for Lens I
6. ✅ Full suite 79/79 passing
7. ✅ **Acceptance gate passed:** 59/59 signals ingesting, 0 empty, 0 errors, 0 sanity warnings, 0 future-dated rows; full Docker Compose stack verified; no ⚠ VERIFY items remain in active config

### Phase 1B — Composites & Snapshot Engine ✅ COMPLETE (2026-06-18)
1. ✅ Compile current signal state via `compute_composite_history()` in `indicators/composites.py`.
2. ✅ Growth Score + Inflation Score (weighted Z-score composites), Regime Quadrant (4-season), Confidence (direction-agreement fraction), Disequilibrium Score (mean |Z-score| across 5 structural force groups).
3. ✅ 558 monthly composite snapshots stored in `composites` DuckDB table; idempotent upserts.
4. ✅ **Acceptance gate passed:** multi-year timeline in DB; historical narrative consistent with known regimes. Note: 2022 engine output is "Inflationary Boom" (not Stagflation) — employment Z-scores were strongly positive all year; Stagflation label correctly appears from Mar 2023 onward. Spec's spot-check assumption was imprecise.

### Phase 1C — US Streamlit Frontend (architecture proof)
1. Build the §5.1 grid; render the 4-quadrant Plotly scatter with a 12-month tail.
2. Build all accordions (A–I + demographics), percentile color badges, data-quality badges, causal tooltips, and the **Geopolitical-Risk Overlay**.
3. Dashboard note: add tooltip on `premium.high_yield_spread` flagging "Z-score vs 3yr window only (FRED data truncated 2023)".
4. **Acceptance:** UI launches, queries DuckDB, paints heat by percentile correctly, and runs a manual refresh smoothly.

### Phase 2 — Country Rollout (one at a time, in this order)
Recommended order (data-availability descending): **Eurozone → Japan → UK → South Korea → China → India → Brazil → Saudi Arabia → Russia.**
For each country: instantiate `CountryBinding`s using §6.3 harmonized routing → verify every series ID against the provider → spot-check 3–5 recent values against a public reference → set `vintage_available` honestly (`true` only for the US/where vintages exist; otherwise `latest_only`) → human sign-off before merging.

### Phase 3 — Back-Test / Regime-Replay
Using the US vintage data, replay named historical regimes and confirm the quadrant classifier lands each in the expected season:
- **1970s stagflation** (falling growth / rising inflation)
- **2008 GFC** (debt-stress / crisis)
- **2020 COVID shock** (sharp growth collapse → reflation)
- *(Optional)* late-1990s expansion (rising growth / stable inflation)
**Acceptance:** each scenario, fed only data available *as of* that time (no look-ahead), classifies into the expected quadrant with documented confidence.

---

## Section 8: Cross-Country Data Source Catalog

### 8.1 Free / Buildable Tier (use these now)
| Provider | Access method | Covers | Vintages? | Key needed |
| :--- | :--- | :--- | :--- | :--- |
| **FRED / ALFRED** | `fredapi` / REST `api.stlouisfed.org/fred` | US high-frequency + many global series + BIS REER/debt | **Yes (API)** | Free key |
| **World Bank WDI/WGI** | `wbgapi` / REST `/v2/...?format=json` | Debt, fiscal, external, capital, demographics, governance, R&D | No | None |
| **IMF** | IMF Data / SDMX (`sdmx` or `imfp`) | WEO (fiscal: `GGXONLB`,`GGSB`), IFS, BOP, IIP | No | None |
| **OECD** | OECD SDMX API | Govt debt, structural deficits, real rates, productivity, LFPR | Some | None |
| **ECB** | ECB Data Portal / SDMX | Eurozone rates, balance sheet, HICP | No | None |
| **Eurostat** | Eurostat REST/SDMX | Eurozone GDP, HICP, BoP | No | None |
| **BIS** | via FRED mirrors (`RB*BIS`, debt/GDP) | REER, credit-to-GDP, debt-service ratios | No | (FRED key) |
| **EIA / IEA / WB Pink Sheet** | EIA API (free key) / WB CSV | Oil, gas, broad commodity indices | No | EIA key |

> **Verification requirement:** for any provider with a search API, the agent resolves every `⚠ VERIFY` ID via search before first ingestion and writes the confirmed ID + metadata back to config (§9.1).

### 8.2 Deferred / Manual-Entry Tier (documented, NOT blocking)
Build the `IndicatorConcept` slots and leave bindings as `provider="manual"`, `source_tier="deferred"`. Do not let these block Phases 1–3.
| Item | Why deferred | Possible later path |
| :--- | :--- | :--- |
| EIU / ICRG political-risk scores | Paywalled, no free API | Use WB **WGI** as the live substitute (already in Lens H) |
| EM-DAT disaster losses (Lens I) | Registration + non-API | Manual annual CSV import; or WRI portal |
| SWF holdings (capital flows) | No reliable free feed | Manual / SWFI snapshots |
| CEIC / Bloomberg / Refinitiv | Subscription terminals | Only if a license is provided |
| NBS China automated pull | Hard to automate reliably | Use WB/IMF harmonized series for China structural data; national source manual |
| Russia (Rosstat/CBR) | Possible access restrictions | WB/IMF harmonized series; flag coverage gaps |

---

## Section 9: Agent Build Guardrails & Failure-Mode Mitigations

> These rules exist because the **data layer**, not the software, is where this project fails. Follow them strictly.

### 9.1 Series-ID discipline (the #1 risk)
- **Never invent or assume a series identifier.** Treat every `⚠ VERIFY` ID as unconfirmed.
- Before first ingestion of any series, call the provider's search/metadata endpoint, confirm the title matches the intended concept, and **write the confirmed ID + human-readable title back into the binding config.**
- A series that returns **empty or all-null** data is a **failure, not a success** — halt and re-resolve the ID. Do not let the dashboard render placeholder/empty series silently.
- After ingestion, run a **sanity range check** per concept (e.g. a current-account-to-GDP outside ±25%, or a debt/GDP outside 0–400%, triggers a flag for human review).

### 9.2 Secrets & registration
- Required keys: **FRED API key**, **EIA API key**. These must be provisioned by a human and read from environment variables / a `.env` file (never hardcoded). The agent must fail loudly with a clear message if a key is missing, not stub the data.

### 9.3 Cross-country comparability
- For each structural concept, pin the **exact definition** (e.g. *general government* gross debt vs *central government*; calendar vs fiscal year; SA vs NSA) in the `IndicatorConcept` and keep it identical across countries.
- Prefer one harmonized provider per structural family (§6.3). When a national source must be mixed in, set `is_proxy=true` and log the definitional difference.

### 9.4 Vintage honesty
- `vintage_available=true` only where point-in-time data genuinely exists (US via FRED API). All other countries use latest-revised data and must set `vintage_available=false`.
- The Phase 3 backtest acceptance criterion ("free of look-ahead bias") applies **only to series where vintages exist.** Do not claim look-ahead-free backtests for latest-only series; surface the caveat in the data-quality log.

### 9.5 Resilient ingestion & agent feedback loop
- Wrap every external call in retry-with-backoff; **distinguish rate-limit/transient errors from real failures** so the agent doesn't misread a 429 as "my code is wrong."
- **Cache raw API responses to local disk** (DuckDB or parquet) on first successful pull, and develop against the cache. This gives the agent fast, deterministic feedback and avoids hammering rate-limited APIs during iteration.
- Make ingestion **idempotent** (re-running doesn't duplicate rows; upsert on `id + as_of`).

### 9.6 Acceptance gates (must pass before advancing a phase)
1. Every active binding's ID is provider-confirmed (no `⚠` left in active config).
2. No active series is empty/all-null.
3. Every series passes its sanity range check or is human-reviewed.
4. `vintage_available` is set truthfully for every series.
5. Deferred-tier items are present as slots but clearly marked and non-blocking.

---

## Appendix A — Quick Reference: New v2 Series (verification status)

> Last updated: 2026-06-18 (after full Phase 1A acceptance)

**Verified and ingesting (`✓`):**
`CIVPART`, `GACDFSA066MSFRBPHI` *(corrected from original `GACDISA066MSFRBPHI`)*, `GB.XPD.RSDV.GD.ZS`, `IEABC`, `IIPUSNETIQ`, `RBUSBIS`, `BN.CAB.XOKA.GD.ZS`, `NE.EXP.GNFS.ZS`, `NE.IMP.GNFS.ZS`, `BX.KLT.DINV.WD.GD.ZS`, `PX.REX.REER`, `GC.DOD.TOTL.GD.ZS`, `SP.POP.DPND`, `SP.POP.GROW`, `SP.URB.TOTL.IN.ZS`, `SL.TLF.CACT.ZS`, `GC.REV.XGRT.GD.ZS` *(verified; bound in Phase 1A-iii fiscal section)*.

**Verified in Phase 1A-iii (2026-06-18):**
`RTFPNAUSA632NRUG` ✓, `PPIACO` ✓, `HDTGPDUSQ163N` ✓, `BCNSDODNS` ✓, `FYFSD` ✓, `FYOINT` ✓. IMF Datamapper IDs: `pb` ✓ (primary balance, replaces `GGXONLB`), `GGCB_G01_PGDP_PT` ✓ (structural balance, replaces `GGSB`).

**Must verify before ingestion (`⚠`) — Phase 2+ scope:**
All per-country bindings (Eurozone, Japan, UK, etc.).

**API unavailable — deferred (`⛔`):**
`PV.EST`, `CC.EST`, `GE.EST`, `RL.EST`, `RQ.EST` — WGI governance series deleted/archived from WB v2 indicator API (confirmed 2026-06-18). Deferred slots exist in `us_bindings.yaml`. Resolution: WGI bulk CSV download.

**Deferred / manual:** SWF holdings, EM-DAT disaster losses, EIU/ICRG, CEIC/Bloomberg, NBS-China automated, Russia automated, `capital.portfolio_flows` (IMF BOP/TIC), `currency.ppp_gap` (derived OECD/WB PPP).
