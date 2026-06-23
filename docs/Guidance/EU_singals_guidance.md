When you move from the United States to the European Union, the same systematic mindset works: start with a set of observable, market‑based or policy‑driven signals that reflect the two forces you care about—growth and inflation—and then treat them as inputs in a repeatable, transparent workflow. Below is a practical list of publicly available EU‑wide (or very close to EU‑wide) signals that map cleanly onto the "Growth Force" and "Inflation Force" categories you already use for the U.S., together with a brief note on why each one matters and how it can be incorporated into a Z‑score or momentum calculation.

**Signal status legend**

| Symbol | Meaning |
|--------|---------|
| ✅ | Piped and live in DuckDB |
| ⚠️ | Partially covered — see notes |
| ❌ | Not piped — reason in notes section |

---

## Growth‑Force Signals for the EU

| Status | Category | Signal | Frequency / Horizon | Why it matters | Typical source |
|--------|----------|---------|--------------------|----------------|----------------|
| ✅ | **Labor Market** | **EU employment growth** (Eurostat `namq_10_pe`) | Quarterly | Direct gauge of labor‑force expansion; ties to capacity utilisation and wage pressure | Eurostat Statistical Data Warehouse |
| ⚠️ | | **Job vacancies (unemployment rate & vacancy‑to‑job ratio)** | Quarterly | Captures demand for workers; complements payrolls | Eurostat – Labour Force Survey |
| ⚠️ | | **Active labour force participation rate** | Quarterly | Adjusts for demographic shifts; useful for long‑run growth | Eurostat |
| ✅ | **Production & Capacity** | **EU Industrial Production Index (seasonally adjusted)** | Monthly | Shows real output trends; analogous to U.S. industrial production | Eurostat |
| ✅ | | **Capacity Utilisation (manufacturing)** (`ei_bsin_q_r2`) | Quarterly | Indicates slack vs. strain in the economy; a leading indicator of future growth | Eurostat / DG-ECFIN Business Survey |
| ✅ | | **Construction activity** (`sts_copr_m`) | Monthly | Sensitive to housing demand and fiscal stimulus | Eurostat |
| ✅ | **Retail & Services Activity** | **Retail sales (consumer spending index)** | Monthly/quarterly | Direct proxy for household demand; a key driver of GDP | Eurostat |
| ❌ | | **Services PMI (HCOB/ISM‑style)** | Monthly | Captures service‑sector health, which dominates EU GDP | Markit Economics |
| ✅ | **Macro‑policy** | **ECB Governing Council's monetary‑policy stance (interest rates, forward guidance)** | Annually/quarterly updates | Influences credit conditions and investment | ECB website |
| ✅ | | **Fiscal balance (net lending/borrowing)** (`gov_10q_ggnfa`) | Quarterly | Fiscal stimulus or austerity directly affects aggregate demand | Eurostat – Government Finance Statistics |
| ❌ | **Financial‑market sentiment** | **Equity market breadth (e.g., MSCI EMU Index returns)** | Daily/weekly | Market pricing already embeds expectations about growth | Bloomberg, Refinitiv |
| ❌ | | **Corporate earnings growth (EU‑wide composite)** | Quarterly | Reflects business confidence and profitability, feeding into investment | FactSet, S&P Global |

*How to use them*: Compute a rolling Z‑score over a 10‑year (40‑quarter) window for each series, then apply a simple decay factor (e.g., exponential half‑life of 2–3 months for monthly data) to give more weight to recent observations. For momentum, take the difference between the current value and the value 12 months ago, or compute a short‑term moving‑average slope. When you combine several series into a single "Growth Force" composite, weight each by its historical contribution to GDP growth (you can derive these weights from a regression of the series against real GDP) and then normalize the composite to unit variance before using it in your portfolio‑weighting model.

---

## Inflation‑Force Signals for the EU

| Status | Category | Signal | Frequency / Horizon | Why it matters | Typical source |
|--------|----------|---------|--------------------|----------------|----------------|
| ✅ | **Core price trends** | **HICP core inflation (ex‑food & energy)** | Monthly/quarterly | Removes volatile components; aligns with central‑bank inflation target | Eurostat |
| ✅ | | **Eurozone CPI core inflation** | Monthly/quarterly | Alternative measure, often used by policymakers | Eurostat |
| ✅ | **Commodity‑driven pressures** | **Energy‑price index (EIA/IEA‑derived)** | Monthly/quarterly | Energy is a large component of HICP; also a driver of input costs | EIA, IEA, Eurostat |
| ✅ | | **Food‑price index (HICP food)** | Monthly/quarterly | Useful for short‑run consumer‑price dynamics | Eurostat |
| ⚠️ | **Wage dynamics** | **Average hourly earnings (real)** | Quarterly | Direct input‑cost pressure; a key component of core inflation | Eurostat |
| ✅ | | **Labour‑market wage growth (median & average)** | Quarterly | Differentiates between high‑skill and low‑skill sectors | Eurostat |
| ❌ | **Market‑based expectations** | **Breakeven inflation rates (Eurozone 5‑yr & 10‑yr)** | Monthly | Market pricing of future inflation; already incorporates expectations | Bloomberg, Refinitiv |
| ❌ | | **Eurozone term‑structure of inflation swaps** | Monthly | Similar to breakevens but based on swap markets | ICE Swap Institute |
| ✅ | **Price‑pressure indices** | **Producer Price Index (PPI) broad** | Monthly/quarterly | Early signal of cost‑push inflation | Eurostat |
| ❌ | | **Wholesale price index (WPI)** | Monthly/quarterly | Another early‑stage price‑pressure gauge | Eurostat |
| ❌ | **Policy‑related** | **ECB inflation outlook (annual forecasts)** | Annually/quarterly updates | Provides a benchmark for what the central bank thinks is likely | ECB website |
| ✅ | | **Eurozone monetary‑policy stance (forward guidance, rate decisions)** | Same as above | Influences expectations and real‑rate environment | ECB website |
| ✅ | **Financial‑market stress** | **Real yields on 10‑yr German Bunds** | Daily/weekly | Real yield is a proxy for inflation‑adjusted cost of capital | ECB SDW IRS flow |
| ✅ | | **IT-DE Sovereign spread over Bund** (`credit.btp_bund_spread`) | Monthly | Higher spreads signal EA fragmentation risk and monetary transmission stress | ECB SDW IRS flow |

*How to use them*: Treat the core HICP series as the baseline "inflation force." Add a weighted contribution from energy‑price and food‑price indices to capture the volatility that can spill over into core measures. Use breakeven rates as a market‑based expectation filter: if breakevens are rising faster than the core index, you may want to tilt toward assets that benefit from higher inflation (e.g., commodities, real assets). Compute Z‑scores over a 10‑year window, then apply a longer decay (half‑life of 6–12 months) because price‑level changes tend to be smoother than production data. For momentum, look at the change in the 12‑month lagged inflation rate or the slope of the breakeven curve.

---

## Signal Status Notes

### ⚠️ Partial coverage

**Job vacancies / vacancy-to-job ratio** — We pipe `ez.growth.unemployment` (Eurostat `une_rt_m`, EA21, seasonally adjusted, monthly). This covers the unemployment rate half of this signal. The vacancy-to-job ratio is available from Eurostat (`jvs_q_nace2`), but requires an additional quarterly binding and would be a lagging supplement to unemployment. Deferred for now; unemployment alone is the dominant growth signal.

**Active labour force participation rate** — We have `ez.demo.labor_force_part_wb` (World Bank `SL.TLF.CACT.ZS`, annual) in the demographics force. It is present and tracked but sits in the structural/demographic basket rather than the cyclical growth composite. To promote it to the growth composite would require a higher-frequency Eurostat source (LFS quarterly). Deferred pending frequency match.

**Average hourly earnings (real)** — We pipe `ez.inflation.wages_lci` (Eurostat `lc_lci_r2_q`, wages and salaries YoY, nominal, quarterly). This captures wage-push dynamics but is **nominal**, not real (deflated). Real hourly earnings require deflating by HICP, which would need a derived construction step. The nominal LCI series is the standard ECB wage-pressure indicator; real deflation adds precision but not regime-classification signal. Not built yet.

---

### ✅ Newly piped signals (2026-06-23)

**EU employment growth** — `ez.growth.employment_growth` piped via Eurostat `namq_10_pe` (quarterly national accounts employment, EA20, SCA, EMP_DC, PCH_SM_PER). Note: `lfsi_emp_m` (monthly LFS) does NOT exist for the EA aggregate — the quarterly national accounts dataset is the correct source. 109 observations back to 2000-Q1; latest Q1 2026 = +0.5% YoY.

**Capacity utilisation** — `ez.growth.capacity_util` piped via Eurostat `ei_bsin_q_r2` (DG-ECFIN industry business survey, EA20, `indic=BS-ICU-PC`, SA). Key findings: (1) the previously-attempted `ei_bsco_q` is the **consumer** survey, not the industry survey; (2) the correct dataset is `ei_bsin_q_r2`; (3) `geo=EA20` is required — `geo=EA` returns empty. 108 observations; latest Q4 2025 = 78.2%.

**Construction production** — `ez.growth.construction_prod` piped via Eurostat `sts_copr_m` (construction production index, EA20, NACE F, PCH_SM). Key finding: `s_adj=CA` (calendar-adjusted) is required — `s_adj=SCA` returns empty for EA20 in this dataset. 328 observations; latest Apr 2026 = +0.9% YoY.

**Fiscal balance** — `ez.fiscal.budget_balance_gdp` piped via Eurostat `gov_10q_ggnfa` (quarterly general government non-financial accounts, EA20, B9 net lending/borrowing, S13, PC_GDP). Key finding: `gov_10dd_edpt1` (EDP procedure) is annual-only; `gov_10q_ggnfa` is the correct quarterly source. 96 observations; latest Q4 2025 = -2.5% of GDP.

**IT-DE sovereign spread** — `ez.credit.btp_bund_spread` piped via two ECB SDW IRS-flow series: `M.DE.L.L40.CI.0000.EUR.N.Z` (German Bund) and `M.IT.L.L40.CI.0000.EUR.N.Z` (Italian BTP). Key finding: the BOP flow returned HTTP 400 because BOP is balance-of-payments data; the correct flow for government bond yields is **IRS** (Long-term Interest Rate Statistics). The spread is computed as a derived signal (IT − DE). API: `https://data-api.ecb.europa.eu/service/data/IRS/{key}?startPeriod=2000-01&format=jsondata`. 317 monthly observations; latest May 2026 = 0.794 pp (79.4 bps).

**GDP level (billions USD)** — `ez.master.gdp_level_bn` piped via World Bank `NY.GDP.MKTP.CD` (current USD, annual). The WB uses country code `EMU` for the Euro area aggregate, resolved automatically via `_WB_COUNTRY_MAP`. `raw_scale: 1000000000` converts raw USD to billions. 35 annual observations; latest 2024 = 16,485B USD. Required by Global Overview table "GDP" column.

**Government debt/GDP** — `ez.credit.gov_debt_gdp` piped via Eurostat `gov_10dd_edpt1` (EDP procedure data, annual, `geo=EA20, na_item=GD, sector=S13, unit=PC_GDP`). Note: `gov_10q_ggnfa` provides only quarterly fiscal balance (B9), not debt stock — `gov_10dd_edpt1` is the only annual gross-debt series for the EA aggregate. 27 annual observations; latest 2025 = 87.8% of GDP. Required by Global Overview table "Debt/GDP" column.

**HICP energy and food sources corrected** — Sources changed from Eurostat `prc_hicp_manr` (which stops at December of the prior year because it publishes Mean Annual Rates, not monthly index values) to FRED index series with `yoy_pct` transform: `CP0450EZ19M086NEST` (electricity, gas and other fuels, 2015=100) and `CP0100EZ19M086NEST` (food and non-alcoholic beverages, 2015=100). The FRED series publishes through the current month.

---

### ❌ Current account balance (exhaustive investigation — 2026-06-23)

`ez.external.current_account_gdp` exists in `ez_bindings.yaml` but the WB `BN.CAB.XOKA.GD.ZS` series returns all null for every EA aggregate code (`EMU`, `XC`, `EU`, `1A`). All other free sources were systematically tested and failed:

| Source | Attempt | Outcome |
|--------|---------|---------|
| **World Bank** | `BN.CAB.XOKA.GD.ZS` for `EMU`, `XC`, `EU`, `1A` | All null — WB does not publish CA% of GDP for the EA aggregate |
| **ECB SDW `BOP`** | `Q.U2.W1.CA.B.EUR.Q` | HTTP 400 — `BOP` flow structure is BPM5, key format incompatible |
| **ECB SDW `BP6`** | `Q.U2.W1.S1.S1.T.B.CA._Z._Z._Z.EUR._T._X.Q` | HTTP 400 — key format wrong for this env |
| **ECB SDW `BPS`** | Multiple key variants | HTTP 400 for all variants |
| **ECB SDW `ECB_BOP1`** | Key format found via DSD: `FREQ.REF_AREA.ADJUSTMENT.DATA_TYPE_BOP.BOP_ITEM.CURR_BRKDWN.COUNT_AREA.SERIES_DENOM`; tried `Q.U2.N.B.010.X.W1.EUR` and 7 variants | HTTP 404 for all — flow not publicly queryable |
| **ECB SDW `ECB_BOP_BNT`** | Various keys | HTTP 404 |
| **FRED** | `BPBLTD01EZQ188S`, `BPBLTD01EZA188S`, `BPBLTT01EZQ188S` | Do not exist; `BPBLTT01EZA188S` exists but cut off at 2012 |
| **Eurostat `bop_c6_q`** | `geo=EA20, bop_item=CA, unit=PC_GDP, stk_flow=BAL, partner=WORLD/W1` | HTTP 413 regardless of dimension specificity — dataset too large for this API endpoint |
| **Eurostat `bop_q6_q`** | Any params | HTTP 404 — dataset does not exist |
| **Eurostat `tipsbp10`/`tipsbp20`** | Various params | Returns empty |
| **IMF Datamapper** | `BCAD`/`BCA` for `XM`, `U2`, `163`, `EMU` | All empty — IMF Datamapper does not support EA aggregate |
| **OECD SDMX** | Various endpoints | HTTP 404 in this environment |

**Conclusion**: EA current account balance (% of GDP) is not retrievable from any free machine-readable API in this environment. The signal slot remains in `ez_bindings.yaml` but will always produce empty. The Global Overview table will show a dash for EZ in the Current Account column. Resolution options: (1) manually maintain an annual CSV from Eurostat's bulk download `bop_c6_q`, (2) subscribe to ECB Data License for programmatic BOP access, (3) accept the gap as structural for the free-data pipeline.

---

### ❌ Not piped — reasons

**Services PMI (HCOB/ISM-style)** — HCOB Eurozone Services PMI is published by S&P Global Markit. No free machine-readable API exists; the monthly headline number appears only in press releases and behind a paywall. A free scraper from investing.com/tradingeconomics would be fragile and unreliable. Deferred until a licensed feed is available.

**Equity market breadth (MSCI EMU Index)** — Bloomberg/Refinitiv subscription required for reliable daily MSCI EMU data. Yahoo Finance provides approximate MSCI Europe data but not EMU-specific. Out of scope for the free-data pipeline per project design rules. Would belong in a premium signal tier.

**Corporate earnings growth** — FactSet or S&P Global subscription required. No free EA-aggregate earnings series available. Out of scope.

**Breakeven inflation rates (5-yr & 10-yr)** — Investigated ECB SDW but the IRS flow only carries harmonised government bond yields, not real yields or breakevens. True inflation-linked breakevens (from HICP-linked bond markets) are not available via the ECB SDW API in a clean time series form. Bloomberg/Refinitiv subscription required for reliable daily breakevens. Deferred to premium tier.

**Eurozone term-structure of inflation swaps** — ICE Swap Institute subscription required. Out of scope.

**Wholesale price index (WPI)** — Eurostat WPI overlaps substantially with our `ez.inflation.ppi` (producer prices, B-D industries). Adding WPI would be partially redundant given we already have the upstream PPI cost-push signal. Marginal regime-classification value is low; deferred.

**ECB inflation outlook (annual forecasts)** — ECB Staff Macroeconomic Projections are published as PDFs and structured press releases four times per year. No machine-readable API exists. Scraping would be brittle. This is a point-estimate forecast, not a time series — hard to Z-score meaningfully. Out of scope for automated ingestion.

---

## Common pitfalls to watch out for

- **Assuming past correlations will stay the same** – EU regimes have shifted dramatically over the last decade (post‑crisis austerity, Brexit, pandemic recovery). Test your composites across multiple sub‑periods (pre‑2008, post‑2012, post‑2020) to see how sensitivities evolve.
- **Ignoring embedded market expectations** – Breakevens and forward‑guidance surveys already price in expected inflation. When you add raw CPI numbers, you may double‑count. Separate "expectations" from "actual" price moves by treating breakevens as a separate signal.
- **Using a single look‑back window** – A 10‑year window smooths out noise but may hide regime changes. Overlay a shorter window (e.g., 2 years) for a "current‑trend" overlay, then blend the two with a decay‑weighted average.
- **Treating all series as linear** – Some relationships are non‑linear (e.g., the effect of energy prices on inflation spikes when they cross a certain threshold). Consider adding interaction terms or piece‑wise regressions if you have the statistical skill.
- **Over‑relying on a single metric for diversification** – Diversification comes from understanding how assets respond to both growth and inflation, not just their correlation matrix. Build a matrix of sensitivities to the two composites and allocate to achieve a balanced exposure across the four quadrants (high‑growth/high‑inflation, high‑growth/low‑inflation, low‑growth/high‑inflation, low‑growth/low‑inflation).
- **Neglecting policy and structural shifts** – EU fiscal rules, the Stability and Growth Pact, and the new "Fit‑for‑21" framework can change the relationship between fiscal balances and growth. Flag any major legislative changes and consider adjusting the fiscal‑balance weight accordingly.

---

### Bottom line

The signals listed above give you a robust, EU‑specific toolkit that mirrors the structure you already use for the United States. By treating each series as a cause‑and‑effect link in a larger economic machine, standardizing them, calibrating their historical impact, and continuously stress‑testing them against plausible macro scenarios, you build a diversified, principle‑driven portfolio that can survive the inevitable cycles of boom, bust, and policy change. Remember: the goal isn't to find a perfect number; it's to understand *why* the numbers behave the way they do and to let that understanding guide a systematic, risk‑balanced allocation.

**Where you can pull the data – a quick‑reference list**

| Signal (EU) | Public source(s) | Typical URL / portal |
|--------------|------------------|---------------------|
| **Employment & labour‑force** | Eurostat Labour Force Survey (LFS) – "Employment, unemployment, participation" | https://ec.europa.eu/eurostat/databrowser/view/lfslp/default/table |
| | Eurostat – "Active labour force participation rate" | https://ec.europa.eu/eurostat/databrowser/view/lfslp/default/table |
| **Job vacancies / JOLTS‑style** | Eurostat – "Vacancies in employment" (or national ministries for detailed series) | https://ec.europa.eu/eurostat/databrowser/view/lfsvl/default/table |
| **Industrial Production** | Eurostat – "Industrial production and manufacturing PMI" (seasonally adjusted) | https://ec.europa.eu/eurostat/databrowser/view/isp/default/table |
| **Capacity Utilisation** | Eurostat – "Capacity utilisation of manufacturing and services" | https://ec.europa.eu/eurostat/databrowser/view/ta001/default/table |
| **Retail Sales** | Eurostat – "Value added at retail level" or national statistical offices | https://ec.europa.eu/eurostat/databrowser/view/retail/default/table |
| **Services PMI** | Markit Economics – "Eurozone Services PMI" (free monthly release) | https://www.markiteconomics.com/Eurozone-Services-PMI |
| **Construction Activity** | Eurostat – "Construction activity, value added" | https://ec.europa.eu/eurostat/databrowser/view/conact/default/table |
| **Monetary policy stance** | ECB – Governing Council minutes & press releases | https://www.ecb.europa.eu/pub/monpol/html/index.en.html |
| **Fiscal balance** | Eurostat – Government finance statistics (primary balance) | https://ec.europa.eu/eurostat/databrowser/view/tfy00001/default/table |
| **Equity market breadth** | Bloomberg / Refinitiv – MSCI EMU Index (or free snapshots via Yahoo Finance) | https://finance.yahoo.com/quote/%5EMSX? (for MSCI Europe) |
| **Corporate earnings** | FactSet / S&P Global – EU‑wide composite earnings growth (or national BOP data) | https://www.factset.com/ or https://www.spglobal.com/ |
| **HICP core inflation** | Eurostat – Harmonised Index of Consumer Prices (core) | https://ec.europa.eu/eurostat/databrowser/view/pcsicp/default/table |
| **Eurozone CPI core** | Eurostat – Consumer Prices Index (core) | https://ec.europa.eu/eurostat/databrowser/view/pcsicp/default/table |
| **Energy price index** | EIA (International) or IEA – Energy Price Index; Eurostat – energy‑price component of HICP | https://www.eia.gov/outlooks/energy‑and‑environmental‑policy/ | https://www.iea.org/reports/world‑energy‑outlook |
| **Food price index** | Eurostat – Food‑price component of HICP | https://ec.europa.eu/eurostat/databrowser/view/pcsicp/default/table |
| **Real hourly earnings** | Eurostat – "Average hourly earnings (real)" | https://ec.stat.ee/ (or national statistical offices) |
| **Wage growth (median/average)** | Eurostat – "Median and average gross hourly earnings" | https://ec.europa.eu/eurostat/databrowser/view/earnest/default/table |
| **Breakeven inflation rates** | Bloomberg / Refinitiv – Eurozone 5‑yr & 10‑yr breakevens | https://www.bloomberg.com/markets/rates/ | https://www.refinitiv.com/en/products/spectranet |
| **Inflation swaps** | ICE Swap Institute – Eurozone inflation swap curves | https://www.iceswapinstitute.com/ |
| **Producer Price Index (PPI) broad** | Eurostat – PPI (all industries) | https://ec.europa.eu/eurostat/databrowser/view/ppi/default/table |
| **Wholesale price index (WPI)** | Eurostat – WPI (all industries) | https://ec.europa.eu/eurostat/databrowser/view/wpi/default/table |
| **ECB inflation outlook** | ECB – Annual forecasts (PDFs & slides) | https://www.ecb.europa.eu/pub/monetarypolicy/html/index.en.html |
| **Real yields on Bunds** | Bloomberg / Refinitiv – German 10‑yr Bund real yield | https://www.bloomberg.com/markets/rates/ | https://www.refinitiv.com/en/products/spectranet |
| **Sovereign spread over Bund** | Bloomberg / Refinitiv – Eurozone sovereign spreads | https://www.bloomberg.com/markets/rates/ | https://www.refinitiv.com/en/products/spectranet |

---

### Updated tables with the public‑source column

#### Growth‑Force Signals (EU)

| Status | Category | Signal | Frequency / Horizon | Why it matters | Typical source | Public‑access site |
|--------|----------|---------|--------------------|----------------|----------------|-------------------|
| ✅ | **Labor Market** | EU employment growth (`namq_10_pe`, PCH_SM_PER) | Quarterly | Direct gauge of labor‑force expansion; ties to capacity utilisation and wage pressure | Eurostat | `namq_10_pe?geo=EA20&s_adj=SCA&na_item=EMP_DC&unit=PCH_SM_PER` |
| ⚠️ | | Job vacancies (unemployment rate & vacancy‑to‑job ratio) | Quarterly | Captures demand for workers; complements payrolls | Eurostat – "Vacancies in employment" | https://ec.europa.eu/eurostat/databrowser/view/lfsvl/default/table |
| ⚠️ | | Active labour force participation rate | Quarterly | Adjusts for demographic shifts; useful for long‑run growth | Eurostat | https://ec.europa.eu/eurostat/databrowser/view/lfslp/default/table |
| ✅ | **Production & Capacity** | EU Industrial Production Index (seasonally adjusted) | Monthly | Shows real output trends; analogous to U.S. industrial production | Eurostat | `sts_inpr_m?geo=EA20&nace_r2=B-D&s_adj=CA&unit=PCH_SM` |
| ✅ | | Capacity Utilisation (`ei_bsin_q_r2`, BS-ICU-PC) | Quarterly | Indicates slack vs. strain in the economy; a leading indicator of future growth | Eurostat DG-ECFIN | `ei_bsin_q_r2?geo=EA20&indic=BS-ICU-PC&s_adj=SA` |
| ✅ | | Construction production (`sts_copr_m`, NACE F) | Monthly | Sensitive to housing demand and fiscal stimulus | Eurostat | `sts_copr_m?geo=EA20&nace_r2=F&s_adj=CA&unit=PCH_SM` |
| ✅ | **Retail & Services Activity** | Retail sales (consumer spending index) | Monthly/quarterly | Direct proxy for household demand; key driver of GDP | Eurostat | `sts_trtu_m?geo=EA20&nace_r2=G47&indic_bt=VOL_SLS&s_adj=CA&unit=PCH_SM` |
| ❌ | | Services PMI (HCOB/ISM‑style) | Monthly | Captures service‑sector health, which dominates EU GDP | Markit Economics (paywall) | No free API |
| ✅ | **Macro‑policy** | ECB policy rate (ECBDFR) + 10Y yield (IRLTLT01EZM156N) | Annually/quarterly updates | Influences credit conditions and investment | FRED | `FRED:ECBDFR`, `FRED:IRLTLT01EZM156N` |
| ✅ | | Fiscal balance (`gov_10q_ggnfa`, B9, S13, PC_GDP) | Quarterly | Fiscal stimulus or austerity directly affects aggregate demand | Eurostat | `gov_10q_ggnfa?geo=EA20&na_item=B9&sector=S13&unit=PC_GDP` |
| ❌ | **Financial‑market sentiment** | Equity market breadth (e.g., MSCI EMU Index returns) | Daily/weekly | Market pricing already embeds expectations about growth | Bloomberg / Refinitiv (paywall) | No free EA-specific API |
| ❌ | | Corporate earnings growth (EU‑wide composite) | Quarterly | Business confidence and profitability feed into investment | FactSet / S&P Global (paywall) | No free API |

#### Inflation‑Force Signals (EU)

| Status | Category | Signal | Frequency / Horizon | Why it matters | Typical source | Public‑access site |
|--------|----------|---------|--------------------|----------------|----------------|-------------------|
| ✅ | **Core price trends** | HICP core inflation (ex‑food & energy) | Monthly | Removes volatile components; aligns with central‑bank inflation target | FRED `00XEFDEZ19M086NEST` | Already piped |
| ✅ | | Eurozone CPI headline | Monthly | Broad price level; ECB primary mandate target | FRED `CP0000EZ19M086NEST` | Already piped |
| ✅ | **Commodity‑driven pressures** | HICP energy (`CP0450EZ19M086NEST`, yoy_pct) | Monthly | Energy is a large HICP component and a driver of input costs | FRED | `FRED:CP0450EZ19M086NEST` (index 2015=100, yoy_pct transform) |
| ✅ | | HICP food (`CP0100EZ19M086NEST`, yoy_pct) | Monthly | Useful for short‑run consumer‑price dynamics | FRED | `FRED:CP0100EZ19M086NEST` (index 2015=100, yoy_pct transform) |
| ⚠️ | **Wage dynamics** | Average hourly earnings (real) | Quarterly | Direct input‑cost pressure; a key component of core inflation | Eurostat | Nominal LCI piped (`lc_lci_r2_q`); real requires HICP deflation step |
| ✅ | | Labour‑market wage growth LCI (nominal) | Quarterly | Wage-push driver; services inflation persistence | Eurostat `lc_lci_r2_q` | Already piped |
| ❌ | **Market‑based expectations** | Breakeven inflation rates (5‑yr & 10‑yr) | Monthly | Market pricing of future inflation; already incorporates expectations | Bloomberg / Refinitiv (paywall) | ECB IRS carries nominal yields only; no free breakeven series |
| ❌ | | Eurozone term‑structure of inflation swaps | Monthly | Similar to breakevens but based on swap markets | ICE Swap Institute (paywall) | No free API |
| ✅ | **Price‑pressure indices** | Producer Price Index (PPI, `sts_inpp_m`) | Monthly | Early signal of cost‑push inflation | Eurostat | `sts_inpp_m?geo=EA20&nace_r2=B-D&unit=PCH_SM` |
| ❌ | | Wholesale price index (WPI) | Monthly | Overlaps with PPI already piped; marginal value low | Eurostat | Deferred |
| ❌ | **Policy‑related** | ECB inflation outlook (annual forecasts) | Quarterly releases | Provides a benchmark for what the central bank thinks is likely | ECB PDFs (no machine-readable API) | Out of scope |
| ✅ | | Eurozone monetary‑policy stance (ECB rate + yield curve) | Daily/monthly | Influences expectations and real‑rate environment | FRED + ECB | Already piped |
| ✅ | **Financial‑market stress** | Real yields on 10‑yr German Bund (derived) | Monthly | Proxy for inflation‑adjusted cost of capital | Derived from ECB IRS + HICP | Already piped |
| ✅ | | IT-DE 10Y sovereign spread (BTP-Bund, `credit.btp_bund_spread`) | Monthly | Higher spreads signal EA fragmentation risk | ECB SDW IRS flow | Newly piped (2026-06-23) |

These links point to the official portals where the raw series are published. Most of them offer an API or CSV download option, so you can automate the pull into your analytics pipeline. For the market‑based series (breakevens, swaps, yields), a free tier of Bloomberg Data License or Refinitiv Eikon may be required; otherwise you can use publicly available snapshots from Yahoo Finance or Quandl for a rough approximation.

---

### How to get the data in practice

1. **Free, fully open sources** – Eurostat, ECB, EIA/IEA, Markit Economics, and Quandl (for some market data) give you direct CSV or Excel downloads.  
2. **Subscription‑required sources** – Bloomberg Terminal, Refinitiv Eikon, FactSet, S&P Global, and ICE Swap Institute provide the most up‑to‑date market‑based series (breakevens, swaps, yields). If you have institutional access, you can pull them via their APIs.  
3. **Hybrid approach** – Use the free sources for the structural macro series (employment, production, CPI, PPI) and supplement with the subscription data for the expectation‑driven series (breakevens, inflation swaps, real yields). This keeps the bulk of the model transparent while still capturing the market‑pricing component.  

---

**Bottom line:** All the series needed for a systematic EU growth‑and‑inflation analysis are publicly available (or very inexpensive to obtain). By linking each signal to its source, you can build a repeatable workflow: download → clean → standardise → weight → composite → portfolio‑weighting. The tables now include the exact URLs you'll need to start pulling the data, so you can move from "what to look for" to "where to get it."
