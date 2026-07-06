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
- **External debt** — WB `DT.DOD.DECT.CD` returns NULL for US/EMU/KR/JP (verified 2026-07-05) — the debtor-reporting-system series only covers low/middle-income countries. Revisit when rolling out China/India/Brazil.
- **EZ aggregate Gini** — WB `EMU` aggregate is empty. A constructed GDP-weighted big-4 average (DE/FR/IT/ES) is feasible but deferred — flaky member-code fetches plus a constructed-proxy design decision.
- **Governance / political polarization (post-WGI)** — V-Dem and Polity5 are annual academic bulk-CSV downloads, no REST API → **manual-load slot** (same pattern as EM-DAT). WB WGI `.EST` series remain deleted from the v2 API.
- **Geopolitical risk (GPR, Caldara–Iacoviello)** — monthly xls from matteoiacoviello.com, no API → **manual-load slot**.

## Japan (rolled out 2026-07-05 — roadmap Phase F results)

The pre-rollout checklist below was worked through; results:
1. **Daily equity index — RESOLVED, better than expected**: `NIKKEI225` is a free DAILY FRED feed (1949→current). JP volatility is true daily realized vol, US-quality — the EZ/KR monthly-proxy gap does NOT apply to Japan.
2. **Monthly CPI — WORSE than expected**: every OECD FRED CPI series for Japan (JPNCPALTT01CTGYM, CPALTT01JPM659N, CPGRLE01JPM659N, JPNCPIALLMINMEI, CPALCY01JPM661N) ended 2021-06/2022-04. JP inflation rests entirely on the IMF WEO annual bridge (`jp.inflation.cpi_imf_annual`, is_proxy). **Open gap: e-Stat (www.e-stat.go.jp) has a free API but requires registration** — the highest-value JP follow-up.
3. **Industrial production**: the index form `JPNPRINTO01IXOBM` died 2024-03; the live feed is the YoY form `JPNPRINTO01GYSAM` (→2026-04, raw_scale 100).
4. Loan-demand survey (BoJ Tankan analog) and policy-rate expectations — not researched this pass; same registration-wall expectation as BoK ECOS.
5. Debt Stress minimum-viable 3-component set for JP — still open (needs a JP DSR source; BIS DSR is a bulk download, not an API).

## General — next country rollout (UK is next in the Phase 2 order)

Work through this file's entries country-by-country rather than assuming US-parity data exists — the JP section above shows both directions of surprise (daily Nikkei better, dead CPI worse).

---

*Maintained alongside [ray_dalio_review_log.md](ray_dalio_review_log.md) — update this file whenever a data-feed check surfaces a gap or resolves one, so the search doesn't have to be redone from scratch next time.*
