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

- **Forward-looking policy-rate expectations** — needs to reflect market-implied path, ideally daily/weekly — **Not viable as a standard signal (found 2026-07-05).** True market-based Fed funds futures (CME FedWatch) are not free/not on FRED. The apparent substitute `FEDTARMD` (FOMC dot-plot median) *exists free* but is a forecast snapshot, NOT a historical series: it serves only the latest FOMC's projections for future year-ends (rows dated 2026/2027/2028), all future-dated (deleted by the no-future-observations guard) with no history to Z-score. It cannot feed a Z-scored basket. Viable paths instead: (a) display-only dot-plot readout on the Rate page; (b) derived `yield_2y − fed_funds` expected-change signal (has history, but overlaps the existing `policy.yield_2y` which already represents market forward-pricing); (c) treat `policy.yield_2y` as sufficient. Awaiting a design decision (roadmap Phase A1).
- **EA/KR equivalent forward guidance** — not yet researched. ECB SDW may carry policy-rate-expectation series; BOK equivalent unconfirmed.

## Credit force

- **Loan-demand (not just tightening-standards) for EZ/KR** — quarterly — **Partial.** Confirmed the US-side gap is resolved: `DRSDCILM` (SLOOS "Net % of Domestic Banks Reporting Stronger Demand for C&I Loans") exists free via FRED, pairing with the existing `DRTSCILM` (lending standards). No equivalent confirmed yet for EZ (ECB Bank Lending Survey — BLS — publishes both a credit-standards and a demand net-percentage series; check ECB SDW for a matching series key) or KR (Bank of Korea Loan Officer Survey — likely requires the same BOK ECOS registration as the KR CPI bridge).

## Long-Term Debt Stress

- **Debt-service-to-consumption denominator** — quarterly, US — **Not yet sourced.** Needs household/government debt-service payments over a consumption base — likely FRED PCE (`PCE` or `PCEC`) as the denominator; numerator could reuse the existing debt-service-ratio construction. Confirm via FRED series-search before binding (punch item #18).
- **Debt-service-to-investment denominator** — quarterly, US — **Not yet sourced.** Needs a gross private investment series (FRED `GPDI` or similar) as the denominator. Ray prioritized this one over the consumption version for a "universal" model since it ties to the productivity-growth force (punch item #18).
- **Sparse-country component set** — see `config/longterm_stress.yaml` header for the documented minimum-viable 3-component fallback (debt/GDP, debt-service ratio, primary balance) — use this checklist to look for those 3 series specifically first when standing up a new country's Debt Stress composite, rather than attempting all 7 components at once.

## General — next country rollout (Japan)

When building `jp_bindings.yaml` / `jp_composites.yaml`, work through this file's entries country-by-country rather than assuming US-parity data exists. Specifically check early:
1. Daily equity index (Nikkei 225 / TOPIX) — likely similar gap to EZ/KR (FRED probably only carries a lower-frequency OECD share-price series for Japan too — confirm, don't assume).
2. SLOOS-equivalent loan-demand survey (Bank of Japan Tankan survey may have an analog).
3. Forward-guidance / policy-rate-expectation series (BoJ has had negative/ZIRP policy for years — confirm whether a meaningful "expectations" series exists at all before allocating a binding slot to it).
4. Debt Stress minimum-viable 3-component set (Japan's public debt/GDP is a headline global figure — likely has strong free coverage; household/primary-balance data quality unconfirmed).

---

*Maintained alongside [ray_dalio_review_log.md](ray_dalio_review_log.md) — update this file whenever a data-feed check surfaces a gap or resolves one, so the search doesn't have to be redone from scratch next time.*
