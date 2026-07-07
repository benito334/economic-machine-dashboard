# Data Source Wishlist

Running checklist of data we *want* but don't have a good free source for yet, plus data we have via a lower-fidelity proxy than we'd like. Use this when rolling out a new country (Japan is next) or when revisiting an existing gap — check each candidate source against the provider's own search/metadata endpoint before adding a binding (per [CLAUDE.md](../../CLAUDE.md) rule: never invent series IDs).

Format per entry: **Concept** — desired frequency — current status — candidates to check.

---

## Volatility force

- **Daily equity index, Euro Area** — daily — **Gap.** FRED only has monthly/quarterly/annual OECD share-price indices for the Euro Area (`SPASTT01EZM661N` family) — no daily EuroStoxx/EuroStoxx50 feed. Currently using a monthly-return realized-vol proxy (`ez.volatility.realized_vol`, `quality_factor: 0.70`, flagged `is_proxy: true`). Candidates to check: ECB Statistical Data Warehouse (SDW) — may carry a daily EuroStoxx or broad EA equity index outside the IRS/BOP flows already probed (see `docs/Guidance/Used/EU_singals_guidance.md`); Stooq or Yahoo Finance (not "free API" tier per project rules — would need a licensing/ToS check first).
- **Daily equity index, Korea (true KOSPI)** — daily — **Gap.** Same issue: only monthly OECD share-price index (`SPASTT01KRM661N`) is free via FRED. World Bank has `DDSM01KRA066NWDB` ("Volatility of Stock Price Index for Republic of Korea") but it's **annual** — even lower resolution than our current monthly proxy, not an upgrade. Candidates to check: Bank of Korea ECOS API (requires registration — same blocker as the KR CPI bridge, see CLAUDE.md); KRX (Korea Exchange) open data.
- **Bond-market volatility (MOVE-index equivalent)** — daily, US — **Not yet sourced.** Ray recommended this for Volatility-force redundancy (punch item #15). No FRED series confirmed yet — search terms to try: "MOVE index", "ICE BofA MOVE", "Treasury option volatility". A rolling standard deviation of an existing yield series (e.g. `DGS10`) could serve as a fallback construction if no dedicated index exists free.
- **Credit-spread volatility** — daily, US — **Not yet sourced**, but likely buildable in-house: rolling std of `BAMLH0A0HYM2` (already bound as `premium.high_yield_spread`) or `BAA10Y` — no new data source needed, just a derived signal (punch item #15).

## Interest Rate force

- **Forward-looking policy-rate expectations** — needs to reflect market-implied path, ideally daily/weekly — **Not viable as a standard signal (found 2026-07-05).** True market-based Fed funds futures (CME FedWatch) are not free/not on FRED. The apparent substitute `FEDTARMD` (FOMC dot-plot median) *exists free* but is a forecast snapshot, NOT a historical series: it serves only the latest FOMC's projections for future year-ends (rows dated 2026/2027/2028), all future-dated (deleted by the no-future-observations guard) with no history to Z-score. It cannot feed a Z-scored basket. Viable paths instead: (a) display-only dot-plot readout on the Rate page; (b) derived `yield_2y − fed_funds` expected-change signal (has history, but overlaps the existing `policy.yield_2y` which already represents market forward-pricing); (c) treat `policy.yield_2y` as sufficient. **Resolved 2026-07-05 (Phase A1):** Ray chose option (b) — `policy.rate_expectations` = yield_2y − fed_funds is live at CONTEXT tier; its keep/weight decision is revisited after the Phase G3 asset-outcome backtest.
- **EA/KR equivalent forward guidance** — not yet researched. ECB SDW may carry policy-rate-expectation series; BOK equivalent unconfirmed.

## Credit force

- **Loan-demand (not just tightening-standards) for EZ/KR** — quarterly — **Partial.** Confirmed the US-side gap is resolved: `DRSDCILM` (SLOOS "Net % of Domestic Banks Reporting Stronger Demand for C&I Loans") exists free via FRED, pairing with the existing `DRTSCILM` (lending standards). No equivalent confirmed yet for EZ (ECB Bank Lending Survey — BLS — publishes both a credit-standards and a demand net-percentage series; check ECB SDW for a matching series key) or KR (Bank of Korea Loan Officer Survey — likely requires the same BOK ECOS registration as the KR CPI bridge).

## Long-Term Debt Stress

- **Debt-service-to-consumption denominator** — quarterly, US — **Not yet sourced.** Needs household/government debt-service payments over a consumption base — likely FRED PCE (`PCE` or `PCEC`) as the denominator; numerator could reuse the existing debt-service-ratio construction. Confirm via FRED series-search before binding (punch item #18).
- **Debt-service-to-investment denominator** — quarterly, US — **Not yet sourced.** Needs a gross private investment series (FRED `GPDI` or similar) as the denominator. Ray prioritized this one over the consumption version for a "universal" model since it ties to the productivity-growth force (punch item #18).
- **Sparse-country component set** — see `config/longterm_stress.yaml` header for the documented minimum-viable 3-component fallback (debt/GDP, debt-service ratio, primary balance) — use this checklist to look for those 3 series specifically first when standing up a new country's Debt Stress composite, rather than attempting all 7 components at once.

## Big-cycle ORDER layer (roadmap Phase D — research spike run 2026-07-05)

**Confirmed viable (built as Lens J `order.*` bindings):**
- **Wealth gap (Gini)** — annual — World Bank `SI.POV.GINI` verified: US through 2024 (41.8), KR through 2021 (32.9), JP through 2020 (32.3), FR/IT/ES through 2023. Multi-year publication lag is inherent — treat as a slow structural read, never gate on freshness. The WB v2 API intermittently returns HTTP 400 on some country codes (DEU was flaky across retries) — tenacity retries usually recover it.
- **Reserve-currency share (COFER)** — quarterly — the **new IMF SDMX 2.1 API** (`api.imf.org/external/sdmx/2.1/data/IMF.STA,COFER/{KEY}`, CSV via Accept header) serves pre-computed currency shares: key `G001.AFXRA.CI_{USD|EUR|JPY|GBP|CNY}.SHRO_PT.Q`, 109 obs 1999-Q1 → 2026-Q1 (USD 71.2% → 57.1%). Loader: `fetch_imf_sdmx_series()`. The legacy `dataservices.imf.org` SDMX host is dead. Only meaningful for reserve-issuer countries — KRW sits inside "Other currencies" (KR gets no slot, honest gap).

**Checked and NOT viable / deferred:**
- **External debt** — WB `DT.DOD.DECT.CD` returns NULL for US/EMU/KR/JP (verified 2026-07-05) — the debtor-reporting-system series only covers low/middle-income countries. **PARTIALLY RESOLVED 2026-07-07: fills for China** ($2.42T through 2024, 35 obs) — bound as `cn.external.external_debt_bn`. Expect it to fill for India/Brazil too.
- **EZ aggregate Gini** — WB `EMU` aggregate is empty. A constructed GDP-weighted big-4 average (DE/FR/IT/ES) is feasible but deferred — flaky member-code fetches plus a constructed-proxy design decision.
- **Governance / political polarization (post-WGI)** — V-Dem and Polity5 are annual academic bulk-CSV downloads, no REST API. **BUILT 2026-07-07 (D4)**: `order.governance` Manual bindings (v2x_libdem, 8 countries) + `scripts/prepare_vdem.py` converter — drop the V-Dem CY-Core CSV per `docs/manual_data.md`. WB WGI `.EST` series remain deleted from the v2 API.
- **Geopolitical risk (GPR, Caldara–Iacoviello)** — monthly xls from matteoiacoviello.com, no API. **BUILT 2026-07-07 (D4)**: `order.geopolitical_risk` Manual bindings (GPRC columns, 7 countries — Luxembourg is not in the GPR set) + `scripts/prepare_gpr.py` converter.

## Japan (rolled out 2026-07-05 — roadmap Phase F results)

The pre-rollout checklist below was worked through; results:
1. **Daily equity index — RESOLVED, better than expected**: `NIKKEI225` is a free DAILY FRED feed (1949→current). JP volatility is true daily realized vol, US-quality — the EZ/KR monthly-proxy gap does NOT apply to Japan.
2. **Monthly CPI — WORSE than expected**: every OECD FRED CPI series for Japan (JPNCPALTT01CTGYM, CPALTT01JPM659N, CPGRLE01JPM659N, JPNCPIALLMINMEI, CPALCY01JPM661N) ended 2021-06/2022-04. JP inflation rests entirely on the IMF WEO annual bridge (`jp.inflation.cpi_imf_annual`, is_proxy). **Open gap: e-Stat (www.e-stat.go.jp) has a free API but requires registration** — the highest-value JP follow-up.
3. **Industrial production**: the index form `JPNPRINTO01IXOBM` died 2024-03; the live feed is the YoY form `JPNPRINTO01GYSAM` (→2026-04, raw_scale 100).
4. Loan-demand survey (BoJ Tankan analog) and policy-rate expectations — not researched this pass; same registration-wall expectation as BoK ECOS.
5. Debt Stress minimum-viable 3-component set for JP — still open (needs a JP DSR source; BIS DSR is a bulk download, not an API).

## United Kingdom (rolled out 2026-07-06)

Results of the pre-rollout verification:
1. **Monthly CPI ages out 2025-03** — `CPALTT01GBM659N` / `CPGRLE01GBM659N` end Mar 2025 (the same OECD-feed cutoff as KR). The IMF WEO annual bridge covers the gap. **Open gap: the ONS API (api.beta.ons.gov.uk) is free and unregistered** — the highest-value UK follow-up for a live monthly CPI (and could replace the aging retail/IP feeds too if OECD feeds keep dying).
2. **No daily FTSE on FRED** — volatility uses the monthly share-price proxy (`SPASTT01GBM661N`), EZ/KR pattern, quality 0.70.
3. Unemployment: the ILO **monthly** form is `LRHUTTTTGBM156S` (→2026-01); the `LRUNTTTT` monthly variant 400s for GB.
4. Industrial production: index form `GBRPROINDMISMEI` died 2024-03 (same as JP) — the live feed is the GYSAM YoY form.
5. GBP COFER share confirmed (4.40%, quarterly 1999→2026); Gini through 2021 (32.4).
6. Debt Stress minimum-viable set for GB — still open (needs a UK DSR source; BoE/BIS candidates are bulk downloads).

## China (rolled out 2026-07-07)

Results of the pre-rollout verification (32 signals bound, all endpoint-verified):
1. **BIS credit is the star dataset** — `QCNPAM770A` (private 200.8% GDP), `QCNHAM770A` (household 58.0%), `QCNNAM770A` (corporate 142.8%), all quarterly and live via FRED. China is the second country (after the US) with a real private/sovereign two-vote split in the stage classifier.
2. **All OECD monthly activity feeds are dead**: industrial production (`CHNPRINTO01*` → 2023), CLI (→ 2024-01), M2 (→ 2019), quarterly nominal GDP (`CHNGDPNQDSMEI` → 2023-Q3), PPI (→ 2022). The LIVE monthly cyclical reads are merchandise **exports/imports** (`XTEXVA01CNM667S` / `XTIMVA01CNM667S`, USD, → 2026-04) — bound as the growth basket. **Open gap: NBS monthly IP/retail/PMI would be the upgrade, but the NBS pull is explicitly out of scope.**
3. **No free government bond yield at ANY maturity** (China isn't in the OECD IRLT family; FRED search returns nothing). The 3m interbank rate (`IR3TIB01CNM156N`, live) proxies the market rate everywhere a yield is needed — including both stage-classifier spreads. **Open gap: ChinaBond/CFETS 10y CGB yield has no free API.**
4. **Monthly CPI ages out 2025-04** (`CPALTT01CNM659N`, same OECD cutoff as KR/GB) → IMF WEO annual bridge. No core-CPI series exists at all.
5. **Unemployment is annual-only** (WB ILO-modeled `SL.UEM.TOTL.ZS`, is_proxy) — the NBS monthly surveyed rate is not freely automatable.
6. **CNY COFER share confirmed** (`G001.AFXRA.CI_CNY.SHRO_PT.Q`, 38 obs 2016-Q4 → 2026-Q1 at 1.99%) — China gets the same external-order read as the US.
7. **WB external debt fills** (see the ORDER-layer entry above) — first country in the system.
8. No daily equity index (monthly `SPASTT01CNM661N` proxy, EZ/KR volatility pattern); no gov-interest series (the stage classifier's SOVEREIGN SQUEEZE flag degrades honestly to never firing for CN); Debt Stress composite not attempted (model stays US-only).

## India (rolled out 2026-07-07)

Richer than China via free APIs (31 signals):
1. **LIVE monthly industrial production** (`INDPRINTO01GYSAM` → 2026-04 — the GYSAM YoY form survives while the index form died 2024-03, the recurring pattern) and **LIVE 10y government bond yield** (`INDIRLTLT01STM` → 2026-05, from 2011) — both things China lacks.
2. LIVE quarterly real GDP (`NGDPRNSAXDCINQ`, NSA → YoY transform), monthly trade, REER, FX reserves, share prices; BIS 3-sector credit from 2007 (private 102.3% / household 47.8% / corporate 54.5%) → two-vote stage split.
3. `DT.DOD.DECT.CD` external debt fills ($716B) — as predicted from the CN result.
4. Monthly CPI dead 2025-03 → IMF annual bridge. **Open gaps:** MOSPI CPI has no free API; CMIE unemployment is paywalled; WB R&D intensity lags to 2020; INR sits in COFER's "Other currencies" (no reserve-share slot); WB Gini is consumption-based (25.5) and NOT comparable to income Ginis — treat as trend-only.

## Germany + Luxembourg (rolled out 2026-07-07, user-requested standalone euro members)

Both are ALSO inside the EZ aggregate — standalone codes for core-vs-aggregate divergence reads.
1. **Germany (29 signals) is the richest non-US dataset**: live monthly HICP via Eurostat-on-FRED (`CP0000DEM086NEST` — NO IMF bridge needed, first bridge-free non-US country), live IP via the Eurostat JSON API (`sts_inpr_m?geo=DE` — the OECD FRED IP feeds died 2023/24), live retail/unemployment/10y Bund/3m interbank (first non-US 2-signal rate basket); BIS 3-sector credit from 1970. OECD core CPI (`CPGRLE01DEM659N`) died 2025-03 — **open gap: no free German core-CPI series** (Eurostat special aggregates via FRED is the candidate to check).
2. **Luxembourg (26 signals) works but is structurally weird**: live HICP/unemployment/IP/10y yield; BIS private credit **420% of GDP** (358.8% corporate — intra-group financing vehicles, documented as a financial-center flow gauge, not domestic leverage); FDI swings past ±100% GDP (sanity range set to ±500/800); exports 190% GDP (entrepôt). The growth composite under-reads LU because the financial sector (the real economy) has no free monthly gauge.
3. The WB v2 API is intermittently flaky on DEU (HTTP 400s) — tenacity retries recover it.

## Commodity/trade hubs — Brazil + Canada/Australia/Mexico/Indonesia (rolled out 2026-07-07)

Added on Digital-Ray's country-coverage advice (he flagged the set as heavy on debt-cycle pillars and light on the commodity-exporter/trade-hub axis; these were his top-4 missing economies + the committed Brazil). ~154 signals; all 5 have full BIS 3-sector credit → they run the private/sovereign two-vote stage split. Per-country data notes (all endpoint-verified 2026-07-07):
- **Brazil (32)** — live IP (`BRAPRINTO01GYSAM`), live discount rate (`INTDSRBRM193N`, Selic-linked ~21%; no OECD bond yield exists → this proxies the rate), BIS credit, WB external debt fills ($605B), Gini 50.3 (highest tracked). Monthly CPI dead 2025-04 → IMF bridge.
- **Canada (31)** — the richest of the five: live IP, live **10y + 3m** rates (2-signal rate basket), live monthly unemployment, BIS credit. External debt null (high-income). CPI dead 2025-03 → IMF bridge.
- **Australia (30)** — live 10y+3m, live monthly unemployment, BIS credit. **QUIRKS:** CPI is **quarterly** natively (no monthly CPI exists for AU); **no monthly IP** on FRED → growth reads on unemployment + trade. External debt null.
- **Mexico (31)** — live 10y+3m, BIS credit, external debt fills ($591B). **QUIRKS:** no monthly IP, no live monthly unemployment (`LRUNTTTTMXM156S` dead 2009) → growth = merchandise trade only (thin, CN-like). CPI dead 2024-07 → IMF bridge.
- **Indonesia (30)** — BIS credit, external debt fills ($421B), FX reserves. **QUIRKS:** no monthly IP; **no bond yield and the discount rate died 2013** → rate = call-money/interbank (`IRSTCI01IDM156N`, live). WB gov-revenue stale (2009) → omitted. CPI dead 2025-04 → IMF bridge.
- **Common:** none is a reserve currency (no COFER slot); no gov-interest series for any → their SOVEREIGN SQUEEZE flags can't fire (CN pattern); monthly IP survives only for BR/CA (the GYSAM YoY form).

## General — next country rollout (Ray's next tier, or the original spec's Saudi/Russia)

Work through this file's entries country-by-country rather than assuming US-parity data exists — every rollout above shows surprises in both directions. Ray's ranked missing list continues past the top-4: **Vietnam, Turkey, South Africa, Saudi Arabia, Russia, Singapore** (he ranked Saudi/Russia BELOW the commodity exporters). Expect the IN/BR pattern: WB/IMF harmonized + FRED-mirrored BIS/OECD feeds; check `DT.DOD.DECT.CD` (external debt) early — it fills for debtor-reporting (EM) countries and is null for high-income. Russia hits the no-Rosstat constraint → WB/IMF harmonized only, expect gaps.

---

*Maintained alongside [ray_dalio_review_log.md](ray_dalio_review_log.md) — update this file whenever a data-feed check surfaces a gap or resolves one, so the search doesn't have to be redone from scratch next time.*
