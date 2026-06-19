# Data Release Calendar — US Signals

> As of 2026-06-19. "Period start/end" uses the FRED convention: quarterly obs_date = first day of the quarter (2026-01-01 = Q1 2026). Latest obs = last row in our DuckDB signals table.

---

## Why Trading Economics shows Q1 2026 GDP — and we do too

**Short answer: we also have Q1 2026 GDP.** Our `us.master.gdp_real` latest observation is `2026-01-01`, which _is_ Q1 2026 in FRED's convention — FRED dates quarterly series to the **first day of the quarter**, not the last. Jan 1 = Q1 Jan–Mar. The signal is correctly marked `is_stale=False`.

Trading Economics may also show **Q2 2026 nowcasts** (e.g., the Atlanta Fed GDPNow model, which updates in real-time with each data release). Those are model estimates, not BEA official releases. Q2 2026 official advance GDP won't be published until ~July 30, 2026.

For the legitimately stale signals (household debt, current account, NIIP, debt service), Trading Economics may display their own model-based estimates or blended figures — not the same official series we ingest.

---

## Release Lag Reference by Provider

| Provider | Typical lag after period end |
|:---------|:-----------------------------|
| FRED daily (Fed/market) | T+0 to T+1 |
| BLS: payrolls, wages, unemployment, LFPR | ~4 days (first Friday of following month) |
| BLS: CPI, PPI | ~12–14 days |
| BLS: JOLTS job openings | ~35–40 days (5–6 weeks) |
| Fed: industrial production, capacity utilisation | ~16 days |
| BEA: advance retail sales | ~13 days |
| BEA: PCE (real & core) | ~28 days (last Friday of following month) |
| BLS: quarterly productivity (preliminary) | ~35 days after quarter end |
| BEA: GDP advance estimate | ~30 days after quarter end |
| BEA: GDP second estimate | ~60 days after quarter end |
| BEA: GDP third (final) estimate | ~90 days after quarter end |
| Fed: Senior Loan Officer Survey | ~3 weeks after quarter end |
| Fed/OMB: government debt % GDP | ~30–45 days after quarter end |
| BEA: current account, NIIP | ~90 days after quarter end |
| FRB: household debt service ratio | ~120 days after quarter end |
| BIS: household debt / GDP | ~3–4 quarters after quarter end |
| Philly Fed PMI proxy | Mid-month (same month, 3rd Thursday) |
| BIS: REER (monthly) | ~6 weeks after month end |
| Treasury/OMB: federal deficit, interest payments | ~2–3 months after fiscal year end (FY = Oct–Sep) |
| World Bank (most annual indicators) | 12–18 months after calendar year end |
| IMF WEO (primary balance, structural balance) | April/October of following year |
| Penn World Tables (TFP via FRED) | 2–3 year lag |

---

## Signal Table

Columns: `Signal ID` · `FRED/Provider ID` · `Freq` · `Period` · `Period start → end` · `Release lag` · `Latest in DB` · `Stale?`

`⚠` = legitimately stale due to structural provider lag  
`✅` = current (latest available from provider)

### Daily — Market & Fed

| Signal | Series ID | Period | Period dates | Release lag | Latest obs | Status |
|:-------|:----------|:-------|:-------------|:------------|:-----------|:-------|
| policy.fed_funds | DFF | Daily | Previous business day | T+0 (same day) | 2026-06-17 | ✅ |
| policy.yield_2y | DGS2 | Daily | Previous business day | T+0 | 2026-06-17 | ✅ |
| policy.yield_10y | DGS10 | Daily | Previous business day | T+0 | 2026-06-17 | ✅ |
| policy.real_yield_10y | DFII10 | Daily | Previous business day | T+0 | 2026-06-17 | ✅ |
| inflation.breakeven_5y | T5YIE | Daily | Previous business day | T+0 | 2026-06-18 | ✅ |
| inflation.breakeven_10y | T10YIE | Daily | Previous business day | T+0 | 2026-06-18 | ✅ |
| inflation.crude_oil | DCOILWTICO | Daily | Previous business day | T+0 | 2026-06-15 | ✅ |
| premium.yield_curve_10y2y | T10Y2Y | Daily | Previous business day | T+0 | 2026-06-18 | ✅ |
| premium.yield_curve_10y3m | T10Y3M | Daily | Previous business day | T+0 | 2026-06-18 | ✅ |
| premium.credit_spread_corp | BAA10Y | Daily | Previous business day | T+0 | 2026-06-17 | ✅ |
| premium.high_yield_spread | BAMLH0A0HYM2 | Daily | Previous business day | T+0 | 2026-06-17 | ✅ |
| policy.real_fed_funds | derived | Daily | Previous business day | T+0 (derived) | 2026-06-17 | ✅ |

### Weekly — Federal Reserve

| Signal | Series ID | Period | Period dates | Release lag | Latest obs | Status |
|:-------|:----------|:-------|:-------------|:------------|:-----------|:-------|
| policy.fed_balance_sheet | WALCL | Weekly | Wed–Tue (covers week ending Wed) | T+1 (Thursday release) | 2026-06-17 | ✅ |
| credit.bank_loans | TOTBKCR | Weekly | Wed–Tue | ~10–14 days (Fed H.8, Friday) | 2026-06-10 | ✅ |

### Monthly — BLS (Labour)

| Signal | Series ID | Period | Period dates | Release lag | Latest obs | Status |
|:-------|:----------|:-------|:-------------|:------------|:-----------|:-------|
| growth.payrolls | PAYEMS | Monthly | 1st–last of month | ~4 days (1st Friday of following month) | 2026-05-01 | ✅ |
| growth.unemployment | UNRATE | Monthly | 1st–last of month | ~4 days (same BLS release) | 2026-05-01 | ✅ |
| growth.labor_force_part | CIVPART | Monthly | 1st–last of month | ~4 days (same BLS release) | 2026-05-01 | ✅ |
| inflation.wages | CES0500000003 | Monthly | 1st–last of month | ~4 days (same BLS release) | 2026-05-01 | ✅ |
| growth.job_openings | JTSJOL | Monthly | 1st–last of month | ~35–40 days (JOLTS, ~6 weeks lag) | 2026-04-01 | ✅ |
| inflation.cpi_headline | CPIAUCSL | Monthly | 1st–last of month | ~12–14 days | 2026-05-01 | ✅ |
| inflation.cpi_core | CPILFESL | Monthly | 1st–last of month | ~12–14 days (same BLS CPI release) | 2026-05-01 | ✅ |
| inflation.ppi_broad | PPIACO | Monthly | 1st–last of month | ~12 days | 2026-05-01 | ✅ |

### Monthly — BEA / Fed / BIS

| Signal | Series ID | Period | Period dates | Release lag | Latest obs | Status |
|:-------|:----------|:-------|:-------------|:------------|:-----------|:-------|
| growth.real_pce | PCEC96 | Monthly | 1st–last of month | ~28 days (BEA PCE release) | 2026-04-01 | ✅ |
| inflation.pce_core | PCEPILFE | Monthly | 1st–last of month | ~28 days (same BEA PCE release) | 2026-04-01 | ✅ |
| growth.industrial_prod | INDPRO | Monthly | 1st–last of month | ~16 days (Fed G.17) | 2026-05-01 | ✅ |
| growth.capacity_util | TCU | Monthly | 1st–last of month | ~16 days (same Fed G.17 release) | 2026-05-01 | ✅ |
| growth.retail_sales | RSAFS | Monthly | 1st–last of month | ~13 days (Census advance retail) | 2026-05-01 | ✅ |
| growth.pmi_proxy | GACDFSA066MSFRBPHI | Monthly | 1st–last of month | Mid-month (Philly Fed, 3rd Thursday) | 2026-06-01 | ✅ |
| currency.reer | RBUSBIS | Monthly | 1st–last of month | ~6 weeks (BIS narrow REER) | 2026-05-01 | ✅ |

### Quarterly — BEA (GDP & National Accounts)

| Signal | Series ID | Period | Period dates | Release lag | Latest obs | Status |
|:-------|:----------|:-------|:-------------|:------------|:-----------|:-------|
| master.gdp_real | GDPC1 | Quarterly | **Q1: Jan 1 – Mar 31** | Advance: ~30d; 2nd: ~60d; Final: ~90d | **2026-01-01 (= Q1 2026)** | ✅ |
| master.gdp_nominal | GDP | Quarterly | Q1: Jan 1 – Mar 31 | Same as GDPC1 | 2026-01-01 (= Q1 2026) | ✅ |
| master.gdp_deflator | GDPDEF | Quarterly | Q1: Jan 1 – Mar 31 | Same as GDPC1 | 2026-01-01 (= Q1 2026) | ✅ |
| master.spending_vs_labor | derived | Quarterly | Q1: Jan 1 – Mar 31 | Derived from GDP+payrolls+productivity | 2026-03-31 | ✅ |
| master.ngdp_minus_yield | derived | Quarterly | Q1: Jan 1 – Mar 31 | Derived from GDP+10Y yield | 2026-03-31 | ✅ |
| policy.monetary_base_gdp | derived | Quarterly | Q1: Jan 1 – Mar 31 | Derived (Fed balance sheet ÷ GDP) | 2026-03-31 | ✅ |
| external.current_account | IEABC | Quarterly | Q4 2025: Oct 1 – Dec 31 | ~90 days after quarter end (BEA ITA) | 2025-10-01 (= Q4 2025) | ⚠ Q1 2026 expected ~June 26 |
| external.niip | IIPUSNETIQ | Quarterly | Q4 2025: Oct 1 – Dec 31 | ~90 days after quarter end (BEA IIP) | 2025-10-01 (= Q4 2025) | ⚠ Q1 2026 expected ~June 26 |

### Quarterly — BLS, Fed, BIS

| Signal | Series ID | Period | Period dates | Release lag | Latest obs | Status |
|:-------|:----------|:-------|:-------------|:------------|:-----------|:-------|
| growth.productivity | OPHNFB | Quarterly | Q1: Jan 1 – Mar 31 | ~35 days preliminary; ~65 days revised | 2026-01-01 (= Q1 2026) | ✅ |
| credit.lending_standards | DRTSCILM | Quarterly | Q2 2026: Apr 1 – Jun 30 | ~3 weeks after quarter end (SLOOS) | 2026-04-01 (= Q2 2026) | ✅ |
| credit.gov_debt_gdp | GFDEGDQ188S | Quarterly | Q1: Jan 1 – Mar 31 | ~30–45 days after quarter end | 2026-01-01 (= Q1 2026) | ✅ |
| credit.corporate_debt | BCNSDODNS | Quarterly | Q1: Jan 1 – Mar 31 | ~90 days (Fed Z.1 release) | 2026-01-01 (= Q1 2026) | ✅ |
| credit.debt_service_ratio | TDSP | Quarterly | Q4 2025: Oct 1 – Dec 31 | ~120 days after quarter end (FRB) | 2025-10-01 (= Q4 2025) | ⚠ Q1 2026 expected ~July 2026 |
| credit.household_debt_gdp | HDTGPDUSQ163N | Quarterly | Q2 2025: Apr 1 – Jun 30 | ~3–4 quarters (BIS structural lag) | 2025-04-01 (= Q2 2025) | ⚠ BIS lag; Q3 2025 expected ~late 2026 |

### Annual — US Treasury / OMB (Fiscal Year: Oct–Sep)

| Signal | Series ID | Period | Period dates | Release lag | Latest obs | Status |
|:-------|:----------|:-------|:-------------|:------------|:-----------|:-------|
| fiscal.federal_deficit | FYFSD | Annual | FY2025: Oct 2024 – Sep 2025 | ~2–3 months after FY end (OMB/Treasury) | 2025-09-30 | ✅ |
| fiscal.interest_payments | FYOINT | Annual | FY2025: Oct 2024 – Sep 2025 | ~2–3 months after FY end | 2025-09-30 | ✅ |

### Annual — World Bank (Calendar Year)

| Signal | Series ID | Period | Period dates | Release lag | Latest obs | Status |
|:-------|:----------|:-------|:-------------|:------------|:-----------|:-------|
| demo.labor_force_part_wb | SL.TLF.CACT.ZS | Annual | 2025: Jan–Dec | ~12 months (ILO modeled estimates) | 2025-12-31 | ✅ |
| external.current_account_gdp | BN.CAB.XOKA.GD.ZS | Annual | 2024: Jan–Dec | ~12–18 months after year end | 2024-12-31 | ✅ |
| external.exports_gdp | NE.EXP.GNFS.ZS | Annual | 2024: Jan–Dec | ~12–18 months | 2024-12-31 | ✅ |
| external.imports_gdp | NE.IMP.GNFS.ZS | Annual | 2024: Jan–Dec | ~12–18 months | 2024-12-31 | ✅ |
| capital.fdi_net_inflows_gdp | BX.KLT.DINV.WD.GD.ZS | Annual | 2024: Jan–Dec | ~12–18 months | 2024-12-31 | ✅ |
| currency.reer_xcountry | PX.REX.REER | Annual | 2024: Jan–Dec | ~12–18 months | 2024-12-31 | ✅ |
| demo.population_growth | SP.POP.GROW | Annual | 2024: Jan–Dec | ~12–18 months | 2024-12-31 | ✅ |
| demo.age_dependency | SP.POP.DPND | Annual | 2024: Jan–Dec | ~12–18 months | 2024-12-31 | ✅ |
| demo.urbanization | SP.URB.TOTL.IN.ZS | Annual | 2024: Jan–Dec | ~12–18 months | 2024-12-31 | ✅ |
| fiscal.govt_revenue_gdp | GC.REV.XGRT.GD.ZS | Annual | 2024: Jan–Dec | ~12–18 months | 2024-12-31 | ✅ |
| growth.rnd_intensity | GB.XPD.RSDV.GD.ZS | Annual | 2023: Jan–Dec | ~2–3 year structural lag (UNESCO survey data) | 2023-12-31 | ⚠ Structural — normal |

### Annual — IMF WEO

| Signal | Series ID | Period | Period dates | Release lag | Latest obs | Status |
|:-------|:----------|:-------|:-------------|:------------|:-----------|:-------|
| fiscal.primary_balance_gdp | pb | Annual | 2024: Jan–Dec | ~6–12 months (IMF WEO April/October) | 2024-12-31 | ✅ |
| fiscal.structural_balance | GGCB_G01_PGDP_PT | Annual | 2025: Jan–Dec | ~6 months (IMF WEO; may include current-year estimates) | 2025-12-31 | ✅ |

### Annual — Penn World Tables (via FRED)

| Signal | Series ID | Period | Period dates | Release lag | Latest obs | Status |
|:-------|:----------|:-------|:-------------|:------------|:-----------|:-------|
| growth.tfp | RTFPNAUSA632NRUG | Annual | 2023: Jan–Dec | 2–3 year structural lag (PWT dataset compile cycle) | 2023-01-01 | ⚠ Structural — normal |

---

## Signals Flagged Stale (6 of 59)

| Signal | Latest obs | Next expected release | Root cause |
|:-------|:-----------|:----------------------|:-----------|
| growth.tfp | 2023-01-01 | 2026 or 2027 | Penn World Tables published on ~3yr lag |
| growth.rnd_intensity | 2023-12-31 | 2026 | World Bank R&D surveys: ~2yr lag |
| credit.household_debt_gdp | 2025-04-01 (Q2 2025) | ~late 2026 | BIS household debt released ~3–4 quarters late |
| credit.debt_service_ratio | 2025-10-01 (Q4 2025) | ~July 2026 | FRB DSR: ~120-day lag; Q1 2026 due ~July |
| external.current_account | 2025-10-01 (Q4 2025) | ~June 26, 2026 | BEA ITA: ~90-day lag; Q1 2026 imminent |
| external.niip | 2025-10-01 (Q4 2025) | ~June 26, 2026 | BEA IIP: ~90-day lag; Q1 2026 imminent |

> **Note on current_account and niip:** These may already have been released by BEA on or around June 26, 2026. Re-running `python3 -m indicators.pipeline --latest` will refresh them.

---

## Can We Get More Current Data?

### For the 3 BEA quarterly signals (current account, NIIP, debt service ratio):

These are already the **fastest publicly available sources**. FRED receives BEA data within 24 hours of release. No free data vendor has this faster. Q1 2026 release from BEA is expected ~June 26, 2026 — running the pipeline after that date will clear the stale flag.

Trading Economics may show a model estimate for these series, but it is not the official BEA figure.

### For household_debt_gdp (BIS):

The BIS compiles debt statistics by surveying national central banks globally, which creates the 3–4 quarter lag. **Faster alternatives:**
- `FRED:CMDEBT` — Household credit market debt outstanding from the Fed's Z.1 Financial Accounts (quarterly, released ~90 days after quarter end). We could replace `HDTGPDUSQ163N` with a derived ratio using CMDEBT ÷ GDP. Trade-off: the BIS measure is cross-country comparable (important for Phase 2); CMDEBT is US-specific.
- **Recommendation:** Add `CMDEBT/GDP` as a second binding at faster cadence for US-specific monitoring; keep BIS for cross-country consistency.

### For GDP (currently fine, but if you want real-time Q2 2026):

- **Atlanta Fed GDPNow** (`https://www.atlantafed.org/cgi-bin/was/man/public/gdpnow`) — updates with every major data release; gives a real-time Q2 2026 estimate. Not an official stat, but widely used.
- We could add a GDPNow fetcher as a `is_proxy=True`, `is_constructed=True` signal.

### For productivity, corporate_debt, and other quarterly FRED signals:

All already at their fastest available cadence from their official source. No improvement possible without a paid data terminal.

### Summary table

| Signal | Current source | Faster free alternative? |
|:-------|:---------------|:-------------------------|
| current_account, niip | BEA/FRED (90d lag) | None — already fastest public source; re-run after June 26 |
| debt_service_ratio | FRB/FRED (120d lag) | None — FRB compiles from household surveys |
| household_debt_gdp | BIS/FRED (3-4q lag) | FRED:CMDEBT ÷ GDP (90d lag) — faster but not cross-country comparable |
| gdp_real | BEA/FRED (advance ~30d) | GDPNow (Atlanta Fed) for real-time nowcast of current quarter |
| tfp | Penn World Tables (3yr lag) | No free alternative for true multi-factor TFP |
| rnd_intensity | World Bank/UNESCO (2yr lag) | NSF Science & Engineering Indicators (US-only, annual, similar lag) |
