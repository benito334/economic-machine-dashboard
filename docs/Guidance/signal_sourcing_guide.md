# Signal Sourcing Guide — Gold-Standard Signals + Known Country Gaps

> **Purpose.** A self-contained brief for a future agent session (or a fresh
> pair of eyes) tasked with **deep-searching for better/more signals**,
> especially for the sparse-data countries. Part 1 is the reference: what the
> *ideal* signal set looks like for ANY economy, in this project's Dalio
> "Economic Machine" framing, assuming zero prior knowledge of the codebase.
> Part 2 is the living punch-list: exactly what each live country is missing
> or running on a proxy today, and what a deep search should try to find.
>
> **Keep Part 2 current.** Every time a country is rolled out or a gap is
> closed, update its row here. This file and
> [data_source_wishlist.md](data_source_wishlist.md) are siblings — the
> wishlist tracks *feed-level* research notes; this file tracks the
> *per-country signal-completeness* view and the gold standard to aim at.

---

## Non-negotiable rules (read first)

These come from [CLAUDE.md](../../CLAUDE.md) and are not optional:

1. **Free public APIs only.** FRED, World Bank, IMF (Datamapper + SDMX/COFER),
   BIS (via FRED mirror), Eurostat, ECB SDW. No paid tiers, no scraping, no
   national-source automation that needs registration/keys we don't have
   (NBS China, Rosstat, BoK ECOS, e-Stat JP are all out of scope unless a
   free unregistered endpoint is found).
2. **Never invent or assume a series ID.** Every candidate ID must be
   confirmed against the provider's own metadata/search endpoint *before*
   binding it, and must return non-null data. An empty/all-null result is a
   FAILURE, not a success. (Use the FRED `/series` + `/series/observations`
   endpoints, or the project loaders `fetch_wb_series` / `fetch_imf_series`
   with `force_refresh=True`, exactly as the `verify_*` scratchpad scripts do.)
3. **Preserve native frequency; never forward-fill past a release cycle
   without `is_stale=true`.** A monthly series that dies gets bridged by a
   lower-frequency proxy flagged `is_proxy: true`, not silently carried.
4. **`vintage_available: true` only for US** (FRED/ALFRED). Everyone else is
   latest-revised → `false`.

The data-source **priority ladder** when sourcing any concept (best first):

1. **FRED-mirrored OECD / BIS / IMF-IFS** monthly or quarterly series — these
   are the backbone; one API, consistent IDs, long history.
2. **Eurostat JSON / ECB SDW** — for euro-area members where OECD-on-FRED is
   thin (e.g. live HICP, industrial production `geo=XX`).
3. **World Bank** annual (structural: demographics, Gini, R&D, external debt,
   trade/GDP, gov revenue).
4. **IMF Datamapper** annual (fiscal: gross debt, primary/structural balance,
   real growth, CPI %) + **IMF SDMX/COFER** (reserve-currency shares).
5. **Manual-load drop folder** (roadmap D4) for no-API bulk sources
   (V-Dem governance, GPR geopolitical risk) — see
   [manual_data.md](../manual_data.md).

---

# PART 1 — Gold-standard signal set for any economy

Organised by the project's **force taxonomy**. For each force: the concept,
the *ideal* signal, its *ideal update interval*, why it matters in the
machine, and the **fallback ladder** (what to accept when the ideal is
unavailable — the common real-world case). The US binding set (73 signals) is
the fullest reference implementation; a rich new country should approach it,
a sparse one should hit at least the **⭐ minimum-viable** signals.

Convention: signals are stored in a common space — flows/prices as
year-over-year %, rates/ratios/indices as levels. Update-interval targets
below are the *native release cadence* to aim for.

## Master / Growth clock (the short-term growth read)

| Concept | Ideal signal | Ideal interval | Why it matters | Fallback ladder |
|---|---|---|---|---|
| ⭐ **Real GDP** | Real GDP, SA, chained | Quarterly | The anchor growth rate; feeds r−g and the stage classifier | SA quarterly → NSA quarterly (YoY transform) → IMF annual real-growth % |
| ⭐ **Industrial production** | IP ex-construction, YoY | Monthly | Fastest broad output read; the cyclical workhorse | OECD `…PRINTO01GYSAM` YoY form (survives after the index form dies) → Eurostat `sts_inpr_m?geo=XX` → *drop it* (use trade+labour) |
| **Retail sales** | Retail volume, YoY | Monthly | Domestic-demand read | OECD `…SLRTTO01GYSAM` → national stats (usually no free API) |
| ⭐ **Unemployment** | Harmonised rate, SA | Monthly | Labour-market slack; lagging but reliable | OECD/ILO `LRHUTTTT…M156S` (monthly) → `LRUNTTTT…` → **WB `SL.UEM.TOTL.ZS` annual (is_proxy)** |
| **Merchandise trade** | Exports & imports value, YoY | Monthly | For commodity/trade economies this is the LIVE growth engine when IP is dead | OECD `XTEXVA01…M667S` / `XTIMVA01…M667S` (very widely available) |
| **Capacity / sentiment** | Capacity utilisation, PMI, business confidence | Monthly | Leading turn signals | Country-specific; often no free API |

**Minimum-viable growth basket:** real GDP (quarterly) + at least ONE live
monthly read (IP *or* exports+imports) + unemployment (monthly ideal, WB
annual acceptable).

## Inflation clock (the short-term price read)

| Concept | Ideal signal | Ideal interval | Why | Fallback ladder |
|---|---|---|---|---|
| ⭐ **Headline CPI/HICP** | All-items YoY | Monthly | The inflation anchor; central-bank target | Eurostat HICP (live, euro members) → OECD `CPALTT01…M659N` YoY → **IMF WEO annual `PCPIPCH` bridge (is_proxy)** → quarterly CPI (e.g. Australia) |
| **Core CPI** | Ex food & energy YoY | Monthly | Underlying persistence; what policy targets | OECD `CPGRLE01…M659N` → *often unavailable* (no free core for DE/CN/most EMs) |
| **Upstream / expectations** | PPI YoY; TIPS/linker breakevens | Monthly/Daily | Pipeline pressure + market-implied path | PPI `…PIEATI01GYM`; breakevens are US-rich, rare elsewhere |
| **Wages** | Avg hourly earnings / labour-cost index YoY | Monthly/Quarterly | Wage-price spiral input | Eurostat `lc_lci_r2_q` (EA); rare elsewhere |

**Minimum-viable inflation basket:** headline CPI (monthly ideal) + the IMF
annual bridge as a backstop for when the monthly feed ages out (it always
eventually does — OECD-on-FRED monthly CPI feeds have died for KR/GB/JP/CN/IN
on a rolling basis).

## Interest-Rate / Policy clock (the primary lever)

| Concept | Ideal signal | Ideal interval | Why | Fallback ladder |
|---|---|---|---|---|
| ⭐ **Policy rate** | Central-bank target/effective rate | Daily/Monthly | The main short-term lever | National policy rate → OECD immediate/call-money `IRSTCI01…` → discount rate `INTDSR…` (watch for dead series) → 3m interbank |
| ⭐ **Long yield** | 10-year govt bond yield | Monthly/Daily | Risk-free discount rate; feeds ngdp−yield & the stage spreads | OECD `IRLTLT01…M156N` → *NONE free for some EMs (CN, BR, ID)* → then a short rate proxies "the yield" (documented is_proxy) |
| **Short rate** | 3m interbank / T-bill | Monthly | Curve slope; policy pass-through | OECD `IR3TIB01…M156N` |
| **Real policy rate** | Policy rate − core CPI | Derived | Ray's "is money easy/tight" | Compute in-pipeline (`policy.real_*`) |
| **Forward expectations** | 2y−policy, futures-implied path | Daily | "Money is made on change" | Derived `yield_2y − policy` (US has it; the dot-plot is NOT usable — future-dated) |

**Minimum-viable rate basket:** at least ONE live market/policy rate. Two
(long + short) enables a slope read and a 2-signal rate composite (CA/AU/MX/DE
have this; CN/BR/ID/KR run on a single rate).

## Credit clock (the mechanism linking growth & inflation)

| Concept | Ideal signal | Ideal interval | Why | Fallback ladder |
|---|---|---|---|---|
| ⭐ **Private debt / GDP** | BIS total private non-financial credit | Quarterly | Core leverage; the stage classifier's anchor | BIS `Q..PAM770A` (mirrored on FRED — broadly available) |
| ⭐ **Household debt / GDP** | BIS household credit | Quarterly | Private-side cash-flow burden; enables the **private vote** | BIS `Q..HAM770A` (from ~2007 for EMs) |
| ⭐ **Corporate debt / GDP** | BIS non-financial corp credit | Quarterly | Enables the private/sovereign two-vote split | BIS `Q..NAM770A` |
| **Debt-service ratio (DSR)** | BIS DSR (household + total) | Quarterly | The EARLIEST squeeze signal | **BIS DSR is a bulk download, NOT an API → missing for every non-US country.** Highest-value cross-country gap. |
| **Lending standards / demand** | SLOOS-style survey, both sides | Quarterly | Supply AND demand of credit | US `DRTSCILM`/`DRSDCILM`; ECB BLS for EA; rare elsewhere |
| **Sovereign debt / interest** | Gov gross debt %; interest/GDP | Annual | The sovereign vote + SOVEREIGN SQUEEZE flag | IMF `GGXWDG_NGDP` (debt, everywhere); **gov-interest series is US-only (FYOINT) → the squeeze flag can't fire elsewhere** |

**Minimum-viable credit basket:** private debt/GDP (BIS) + gov debt/GDP (IMF).
The full 3-sector BIS set unlocks the two-vote stage split — aim for it (10 of
14 countries now have it).

## External / Capital / Currency

| Concept | Ideal signal | Interval | Fallback |
|---|---|---|---|
| Current account / GDP | WB `BN.CAB.XOKA.GD.ZS` | Annual | (EZ aggregate is a known hole — no free source) |
| Exports & imports / GDP | WB `NE.EXP/IMP.GNFS.ZS` | Annual | — |
| External debt stock | WB `DT.DOD.DECT.CD` | Annual | **Fills for EMs (debtor-reporting), NULL for high-income** — don't bind it for advanced economies |
| FDI net inflows / GDP | WB `BX.KLT.DINV.WD.GD.ZS` | Annual | (financial centres distort it — LU ±100%+) |
| FX reserves | IMF-IFS `TRESEG..M052N` | Monthly | Bind for reserve-managing EMs; skip for free-floaters (CA/AU) |
| Real effective exchange rate | BIS `RB..BIS` | Monthly | Broadly available |

## Volatility (environment risk — NOT a machine force)

| Concept | Ideal signal | Interval | Fallback ladder |
|---|---|---|---|
| ⭐ **Realized equity vol** | Rolling std of DAILY equity-index log returns | Daily→ann. | **US (S&P) + JP (Nikkei) have free daily indices.** Everyone else: monthly OECD share-price index `SPASTT01..M661N` → monthly-return proxy (`is_proxy`, quality ~0.70). Finding a free daily index for any other country is a standing upgrade. |
| Bond-market vol | MOVE-equivalent | Daily | Not yet sourced free; a rolling std of `DGS10` is a buildable fallback |
| Credit-spread vol | Rolling std of HY spread | Daily | Buildable from existing `BAMLH0A0HYM2` |

## Productivity (the third big force / trend)

| Concept | Ideal signal | Interval | Fallback |
|---|---|---|---|
| ⭐ **TFP** | Penn World Table TFP YoY | Annual (2–3y lag) | FRED `RTFPNA..A632NRUG` — available for most countries |
| R&D intensity | WB `GB.XPD.RSDV.GD.ZS` | Annual | Lags badly for some (IN → 2020) |

## Fiscal / Demographics / Order (structural — slow reads)

- **Fiscal:** IMF structural balance `GGCB_G01_PGDP_PT`, primary balance `pb`,
  WB gov revenue `GC.REV.XGRT.GD.ZS` — all annual, broadly available.
- **Demographics:** WB `SP.POP.TOTL / GROW / DPND`, `SL.TLF.CACT.ZS` — annual,
  universal.
- **Order (big-cycle):** WB Gini `SI.POV.GINI` (annual, multi-year lag);
  IMF COFER reserve-currency share (only for reserve issuers — USD/EUR/JPY/
  GBP/CNY; others sit in "Other currencies"); V-Dem governance + GPR
  geopolitical risk via the **manual-load drop folder** (no API).

## The "gold-standard new-country" checklist

When adding an economy, aim for this. Tiered by how much it unlocks:

**Tier A — must-have (the country is viable):** real GDP (Q), headline CPI
(M + IMF annual bridge), one live policy/market rate, BIS private debt/GDP,
IMF gov debt/GDP, WB demographics + Gini, IMF fiscal balances, TFP.

**Tier B — unlocks core features:** a live monthly growth read (IP or trade),
monthly unemployment, BIS household + corporate debt (→ two-vote stage split),
a second rate (→ curve slope + 2-signal rate composite), REER, current
account/trade GDP ratios.

**Tier C — the hard/rare wins (deep-search targets):** BIS DSR (the earliest
squeeze signal — missing everywhere non-US), a free DAILY equity index (true
realized vol), core CPI, gov-interest series (→ enables the SOVEREIGN SQUEEZE
flag), lending-standards survey, a live monthly CPI that doesn't age out.

---

# PART 2 — Known country-specific shortcomings (living list)

What each live country is **missing or running on a proxy** today, and what a
deep search should try to find. Ordered roughly fullest → sparsest. Update
this whenever a country is added or a gap is closed. "Cross-country gaps"
below apply to (nearly) everyone and are the highest-leverage finds.

### Cross-country gaps (apply to most/all non-US countries)

- **BIS Debt-Service Ratio (DSR).** The single earliest squeeze signal, and
  it's missing for EVERY non-US country because BIS publishes it as a bulk
  download, not an API. Finding a free programmatic DSR source (or a
  manual-load pipeline for the BIS DSR file, like the D4 V-Dem/GPR pattern)
  would upgrade the stage classifier everywhere. **Highest-value target.**
- **Free daily equity index.** Only US (S&P) and JP (Nikkei) have one free.
  Everyone else runs monthly-return realized-vol proxies (`is_proxy`,
  quality 0.70). A free daily index (Stooq/exchange open-data, licensing
  permitting) would give true realized vol.
- **OECD-on-FRED monthly CPI feeds keep dying** (KR 2025-04, GB 2025-03,
  JP 2021-06, CN 2025-04, BR 2025-04, IN 2025-03, MX 2024-07). Each is bridged
  by the IMF annual `PCPIPCH`. The live-monthly replacement is usually a
  national-stats API needing registration (ONS, e-Stat, BoK ECOS, INEGI).
- **Gov-interest series is US-only** (`FYOINT`) → the SOVEREIGN SQUEEZE
  early-warning flag can only fire for the US. A free gov-interest-outlay or
  effective-interest series per country would light it up elsewhere.

### Per-country

| Country | Live richness | Known gaps / proxies | Deep-search targets |
|---|---|---|---|
| **US** | Fullest (73 signals) | Bond-market vol (MOVE) not sourced; credit-spread vol not built; debt-service-to-consumption/-investment denominators open; forward-rate expectations only via `yield_2y−funds` | Free MOVE-equivalent; build the two buildable vol signals; PCE/GPDI denominators for DSR variants |
| **Canada** | Richest of the non-US (live IP + 10y + 3m + monthly unemployment + BIS 3-sector) | Monthly CPI dead 2025-03 → IMF bridge; monthly-proxy vol; no DSR | StatCan CPI API (free?); a daily TSX index |
| **Germany** | Very rich (live HICP, Eurostat IP `geo=DE`, 10y+3m, BIS from 1970) | **No free core CPI** (headline HICP only); monthly-proxy vol (no daily DAX); no DSR | Eurostat HICP special-aggregates for a core series; daily DAX |
| **Eurozone (agg)** | Rich (Eurostat + ECB SDW) | **Current account: unresolvable from any free API** (documented); monthly-proxy vol; governance/GPR awkward at aggregate level | ECB Data License (not free); a daily EuroStoxx |
| **UK** | Rich — ✅ **upgraded C→B 2026-07-09** | Moved to live ONS (`fetch_ons_series`): CPI `d7g7/mm23`, retail `j5ek/drsi`, IP `k222/diop`, unemployment `mgsx/lms`. Growth C→B, inflation C→B, **overall B (73)**. Remaining drags: single rate signal (10y yield only — no free UK policy-rate feed) and single credit signal keep policy/credit forces at C; no daily FTSE (monthly-proxy vol); no DSR | A free UK Bank-Rate series (BoE IUMABEDR? verify) to add a policy-rate signal; a second credit signal; daily FTSE |
| **Japan** | Rich — ✅ **upgraded C→B 2026-07-10** | ✅ **CPI CLOSED** — live monthly via e-Stat (`fetch_estat_series`, provider `eStat`, series_id `0003427113/1/0001/00000` = CPI 2020-base index, all-items, national; needs `ESTAT_APP_ID`), to 2026-05, linked to 1970; inflation C→B, **overall B (71)**. Remaining: growth 4/4 stale (IP/retail/unemployment on aging FRED mirrors — e-Stat has these too); single rate + single credit signal; no DSR | e-Stat IP/retail/unemployment tables to de-stale growth; a JGB policy-rate signal |
| **South Korea** | Moderate | Monthly CPI dead 2025-04 → IMF bridge; single rate signal; monthly-proxy vol; no DSR | BoK ECOS API — https://ecos.bok.or.kr/api/ (registration → `BOK_API_KEY`); a daily KOSPI |
| **India** | Rich (live IP + 10y + live Q GDP) | Monthly CPI dead 2025-03 → IMF bridge; R&D lags to 2020; **Gini is consumption-based (~25, NOT comparable to income Ginis)**; annual unemployment proxy; monthly-proxy vol; no DSR | MOSPI CPI API; an income-based inequality series; CMIE unemployment (paywalled) |
| **China** | Sparse-rich (BIS star, but…) | **No bond yield at ANY maturity** (3m interbank proxies everywhere incl. both stage spreads); ALL OECD monthly activity feeds dead → growth on trade only; monthly CPI dead 2025-04 → bridge; annual-only unemployment; monthly-proxy vol; no DSR; no gov-interest | ChinaBond/CFETS 10y CGB yield (no free API found); NBS is out of scope |
| **Brazil** | Rich — ✅ **strengthened 2026-07-10** | Moved to the open **BCB SGS API** (`fetch_bcb_series`, provider `BCB`, no key): IPCA 12m `13522` (inflation C→B), PNAD unemployment `24369` (de-proxied), Selic `4189` (real policy rate, was a discount-rate proxy). **Overall B (77)**. Remaining: still no free 10y yield → policy is a single rate signal (C); monthly-proxy vol; no DSR | A free Brazilian 10y (NTN-B/DI on BCB?); daily Bovespa |
| **Mexico** | Moderate | **No monthly IP AND no live monthly unemployment** (`LRUNTTTTMXM156S` dead 2009) → growth = merchandise trade ONLY; monthly CPI dead 2024-07 → bridge; monthly-proxy vol; no DSR | INEGI API for IP + unemployment; Banxico SIE for extra rates |
| **Australia** | Moderate | **CPI is QUARTERLY natively** (no monthly exists); **no monthly IP** → growth on unemployment + trade; monthly-proxy vol; no DSR | ABS API for a monthly CPI indicator (the new monthly CPI indicator series); a daily ASX index |
| **Indonesia** | Sparse | **No bond yield AND discount rate dead 2013 → call-money rate proxies**; no monthly IP → trade-only growth; monthly CPI dead 2025-04 → bridge; **WB gov revenue stale (2009) — omitted**; annual unemployment proxy; monthly-proxy vol; no DSR | BI/IDX APIs for a bond yield + equity index; BPS for IP + a current gov-revenue series |
| **Luxembourg** | Financial-centre (distorted) | **Credit 420% GDP = intra-group vehicles** (a global-flows gauge, not domestic leverage — reduced quality factors); **growth composite under-reads** (no free monthly financial-sector gauge); monthly-proxy vol; no DSR | A financial-sector activity gauge (fund AUM?); otherwise inherently a benchmark, not a driver |

### How to use this in a deep-search session

1. Pick a country + a Tier-C gap from its row (or a cross-country gap).
2. Search the provider's metadata endpoint for candidates (mirror the
   `scratchpad/verify_*.py` pattern — FRED `/series` + `/series/observations`,
   or the project loaders). **Confirm non-null data before proposing.**
3. If it's a no-API bulk source, evaluate the **manual-load pattern**
   (D4 / [manual_data.md](../manual_data.md)) rather than discarding it.
4. When a gap closes: add/retune the binding, re-run the pipeline, and
   **update this file's Part 2 row** + the [wishlist](data_source_wishlist.md).
