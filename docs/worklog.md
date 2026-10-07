# Worklog — Indicators Machine

Log entries are newest-first. Each entry: date, what was done, what is next, any blockers.

---

## 2026-10-03 (2) — Dashboard IA Phase 3 (shared chart-card promotion) + a scheduled-import rolling-composite gap found and fixed

**The ask.** Finish Phase 3-5 of the Dashboard IA Blueprint (dropped mid-stream in an earlier session) before returning to the remaining coverage-audit items. Phase 3: promote Fed Monitor's chart-card primitives into `dashboard/shared_components.py` so every Monitors-group page draws from one shared component, rather than each page importing from `fed_monitor.py` as a stand-in shared module.

**Shipped.** `_chart_card`, `_section`, `_chip`, `_info_icon`, `_fmt`, `_ICON_SEQ` moved from `dashboard/fed_monitor.py` into `dashboard/shared_components.py` (new imports: `dbc`, `pd`, `go`, `dcc`, `figure_layout`/`DEFAULT_THEME`). `fed_monitor.py` now imports them back; `case_study_monitor.py`, `market_expectations.py`, `central_bank_monitor.py` repointed their imports at `shared_components` (keeping only their genuinely fed_monitor-specific helpers — `_hist`/`_latest`/`_CC` etc. — imported from `fed_monitor`). Module docstrings on `case_study_monitor.py` and `central_bank_monitor.py` updated to stop describing the pattern as "reused verbatim from fed_monitor" now that it has one real home. `_info_icon`'s DOM id prefix changed `fed-info-` → `mon-info-` (it's a Monitor-group primitive now, not a Fed Monitor one); updated the one test that asserted the literal id string. Verified pixel-identical live on all four pages (Fed Monitor, Case Study Monitor, Market Expectations, Central Bank Monitor) via the Docker preview — no visual change, which was the point.

**Found and fixed in the process — today's 03:00 scheduled auto-import silently dropped all rolling-composite data.** Full-suite run surfaced two Command Center test failures unrelated to the Phase 3 files; tracing them found `growth_score_{36,48,60}m` / `inflation_score_{90,120}m` **NULL across the entire US composites history (all 562 rows)**, despite `growth_score`/`inflation_score` (the full-history base columns) being current through today. Root cause of the mechanism (not the trigger): `upsert_composites()` does a DELETE+INSERT keyed on `(country, month)` against the bare `CompositeSnapshot` the Pass-5 base pass produces, which carries no rolling-window fields — so it blanks every rolling column for the whole history on every run, and the pipeline immediately re-populates them in Passes 5b-5f *within the same run*. Manually reproducing each piece (`compute_composite_history(..., zscore_col="zscore_48m")` → `update_rolling_composites()`) worked cleanly in isolation, so the compute/write logic itself isn't broken — scheduler logs showed only `import success (exit 1)` for the 03:00 run, with no detail on which of the per-country try/except blocks silently absorbed the error. Treated as transient rather than chasing further: re-ran the full pipeline by hand (`docker compose stop charting && docker compose run --rm pipeline && docker compose up -d charting`, the project's standard manual-import workflow) and it completed cleanly — "Updated 562 composite rows" for every rolling variant, confirmed via direct query before moving on. **This is now a known failure mode worth a follow-up**: the scheduler reports `import success` on any pipeline exit code without distinguishing "known EZ current-account gap" (historically the only documented exit-1 cause) from a genuine mid-run data gap — there's no alerting on which per-country/per-pass try/except actually fired. Not fixed this session; flagged as an open item below.

**Stale-test cleanup found along the way.** `test_load_signal_overview_returns_all_signals` still asserted the US signal count at 91 (last updated 2026-08-19); live count is now 107 after this session's earlier coverage-audit sprint (FX debt share / reserve runway, military expenditure, debt service ratio, gov-interest-GDP, central bank balance sheet additions). Updated the assertion and its explanatory comment chain rather than leaving it red.

**Verification.** Full suite: 620 passed, zero exclusions (was 616 passed / 4 failed before the two fixes above — none of the 4 were caused by the Phase 3 file changes themselves, confirmed by checking which files each touched). Docker image rebuilt and redeployed twice (once for the Phase 3 code, once more after the test-file fixes, since the image bakes source and tests must be rebuilt in to run against). Live-verified all four Monitors-group pages in the browser.

**Open item — not pursued today.** Scheduler's exit-code-only success/failure reporting can't distinguish a benign known gap from a real data-pass failure; the specific exception swallowed by today's 03:00 run's rolling-composite step was never identified (transient — didn't reproduce on manual re-run). Worth adding pass-level error detail to the scheduler's log line if this recurs.

**Next.** Phase 4 (retrofit the Signals index + 6 force-detail pages to the shared `_chart_card` style — the actual "signal graphs look crude" fix originally requested), then Phase 5 (Regime Map/History, Debt Stress, Global Overview, Relative Cycles), then back to the remaining coverage-audit items (Phase B: "pushing on a string" QE-effectiveness flag + probabilistic regime confidence; Phase C: bubble-gauge scoping against the existing unconnected `indicators/valuations.py` Buffett Indicator).

---

## 2026-10-03 (3) — Dashboard IA Phase 4: Signals force-detail pages retrofitted to the shared chart-card style

**The ask.** Continue the Dashboard IA Blueprint in order: Phase 4 is the actual "signal graphs look crude" fix originally requested — retrofit the Signals index page and the 6 force-detail sub-pages (`/signals/{force}`) to the shared Monitor chart-card style from Phase 3.

**Scoping finding.** `dashboard/signals_page.py` (the `/signals` index) is a pure table page with no charts at all — nothing to retrofit there. The actual target is `dashboard/force_detail.py`'s chart section: previously one giant `plotly.subplots.make_subplots` figure per force (composite Z row, optional momentum row, then a raw-value + Z-score row pair per basket signal — up to 27 stacked rows on Growth), with a hand-rolled clientside JS crosshair synced across every subplot. Visually dense and inconsistent with every other chart surface on the dashboard.

**Shipped.** Replaced `_build_force_chart()` (one `go.Figure`) with `_build_force_cards()` (a list of `_section()`/`_chart_card()` divs) — a Composite Z card (fill, zero-line, symmetric ± threshold bands where the force has a chip threshold) plus a Momentum card where the force has one, then one raw-value card + one Z-score card per basket signal, all in the same responsive flex-wrap grid every Monitor page already uses. `get_layout()`'s `dcc.Graph` + hover-sync `dcc.Store` became a plain `html.Div` container; the callback's third `Output` changed `"figure"` → `"children"`.

**`_chart_card` gained two small, genuinely-needed extensions** (`dashboard/shared_components.py`): `hline2`/`hline2_txt` for a second dashed reference line (the composite Z cards need both +threshold and −threshold, not just one), and `fmt_override` — a pre-formatted header-value string that bypasses `_fmt()`'s small fixed unit vocabulary (%, $T, $B, idx) for callers whose values live in a different convention — a signal's own native `units` (yoy_pct, pct_gdp, millions_usd, …, formatted via the already-existing `_fmt_value()`) or a signed Z-score. Also fixed a pre-existing cosmetic bug while in this code: `_chart_card`'s filled-area color was hardcoded to a blue tint (`rgba(76,155,232,0.12)`) regardless of the line's own `color` — every force's composite card would have shown a blue-tinted fill under a green/orange/purple/teal line. Added `_hex_to_rgba()` and derive the fill from the actual line color instead. Verified this didn't visibly disturb the 4 already-shipped Monitor pages (Fed Monitor's own filled cards use `_BLUE`/`_GREEN` already, so the fix is a no-op or near-no-op for those).

**Productivity's dual-line overlay (cyclical growth vs. productivity trend) ported cleanly** onto `_chart_card`'s existing `df2`/`color2`/`label`/`label2` dual-line parameters — no new code needed for that part.

**Found and fixed in passing — a near-miss on an unrelated live consumer.** `dashboard/charting.py` wires the Workbench page's own stacked chart (`wb-chart`) through `_force_detail._hover_sync_js(...)` for its synced crosshair — a completely different use case (Workbench's multi-pane overlay, which still is one real `make_subplots` figure) that happens to reuse this module's JS helper. Deleting `_hover_sync_js` outright (it's no longer called by force_detail's own pages) would have silently broken Workbench at import time. Caught via a dangling-reference grep before rebuilding; the function stays defined and exported in `force_detail.py` with a comment explaining why, even though nothing in the file calls it anymore.

**Verification.** Full suite: 620 passed, zero exclusions, after two rebuild cycles. Live-verified all 6 force pages (growth/inflation/rate/credit/volatility/productivity) via DOM inspection, `get_page_text`, and (for the shorter pages) screenshots — Growth's page (12 signals → 28 cards, ~2360px tall) didn't capture in the browser-pane screenshot tool despite correct DOM geometry, correct SVG dimensions, and correct rendered text content confirmed three different ways; re-tested on Productivity (3 signals → 8 cards, much shorter), which screenshot perfectly with the composite dual-line overlay and all signal cards visible — concluded the blank capture is a tool-side limit on very tall pages, not an application bug, and moved on rather than chasing it further. Re-verified the 4 Phase-3 Monitor pages still render correctly after the `_chart_card` extensions (no regressions from the new `hline2`/`fmt_override` params or the fill-color fix).

**Next.** Phase 5 (retrofit Regime Map/History, Debt Stress, Global Overview, Relative Cycles charts to the same card style), then back to the remaining coverage-audit items (Phase B: "pushing on a string" QE-effectiveness flag + probabilistic regime confidence; Phase C: bubble-gauge scoping against `indicators/valuations.py`'s existing unconnected Buffett Indicator).

---

## 2026-10-03 (4) — Coverage Audit Phase B: "pushing on a string" flag + probabilistic regime confidence

**The ask.** With the Dashboard IA Blueprint's chart-card phases done (Phase 3, Phase 4; Phase 5 explicitly deferred — its targets are scatter plots, cross-country tables, and heatmaps, not single-series charts, so a uniform card conversion doesn't apply and the user chose to skip it for now), return to the remaining coverage-audit items. Phase B combines signals already live elsewhere with more design judgment than Phase A's mechanical items.

**Item 7 — "pushing on a string" QE-effectiveness flag.** `case_study_monitor.py` already showed the Fed balance-sheet-YoY chart beside the private-credit-creation chart with prose explaining the pattern, but computed no actual flag. Added `_pushing_on_a_string(bs_yoy_pct, priv_credit_pp)`: fires when balance-sheet YoY > +5% (reused verbatim — not reinvented — from `central_bank_monitor.py`'s own `_mp_read()` MP2 cutoff) AND private credit creation ≤ +0.5pp (reused from this page's own `priv_read` "not expanding" cutoff). Renders as a 5th header chip, same "separate badge, never conflate alarms" convention as Sovereign Squeeze / Debt-Income Spread. Checked the live number before calling it done: balance sheet is +2.4% YoY right now, well under the QE threshold, so the flag correctly stays dormant despite private credit actively deleveraging (-1.9pp) — confirmed via a standalone script, not just "didn't crash."

**Item 8 — probabilistic regime confidence.** New `compute_regime_confidence()` in `dashboard/charting.py`, placed beside `_classify_regime()`/`compute_dynamic_thresholds()` since it's a genuine regime-engine concern, not a page-local helper. Operationalized "historical-frequency confidence" as: of all past months carrying the SAME chip label as today, what fraction were followed (next month) by that label holding rather than reversing? Replays the production `_classify_regime()` call month-by-month — same function the live chip uses, so there is exactly one classification implementation — against whatever windowed composite history the caller already has loaded (no new DB connection, no point-in-time Z recompute; an empirical hold-rate-so-far doesn't need backtest-grade PIT discipline the way an accuracy claim would). Mirrors `indicators/backtest.py`'s own `classify_history()` replay loop, including its precedent of not passing the sustained-months history guard.

Wired into Command Center's header as `persistence G {x%} · I {x%}`, directly beside the existing Chip Direction Agreement stat — "(uncertain)" below the audit's suggested 70% cutoff, "—" when today's chip is Transition (no persistence claim makes sense on the neutral band). The underlying `g_chip`/`i_chip` values are completely unchanged by this — a complement, never a replacement, exactly as specified. Live right now: Growth reads 31% (uncertain) — today's Growth reading has a genuinely weak track record of holding — Inflation reads "—" (currently Transition).

**Not done — Regime Map.** The audit item named both Command Center and Regime Map as display targets; only Command Center shipped this session. Regime Map's own header/chip area would need the same treatment — flagged as a quick follow-up, not forgotten.

**Verification.** 5 new tests for `compute_regime_confidence` (`tests/test_charting.py::TestComputeRegimeConfidence` — persistent-growth→100% confidence, flip-flopping→0% confidence, Transition→no claim, too-short-history→None, inflation-column routing) + 7 new tests for `_pushing_on_a_string` (`tests/test_case_study_monitor.py`, new file — fires/doesn't-fire across the threshold boundary, missing-input guards, plus a basic layout smoke test matching the Fed Monitor/Market Expectations convention). Full suite: 632 passed, zero exclusions. Live-verified both features in the browser plus the live-data sanity check above; re-confirmed Fed Monitor and Case Study Monitor's existing chips/charts still render correctly (no regressions from the new import/helper additions).

**Next.** Phase C (bubble-gauge scoping): check `indicators/valuations.py`'s existing unconnected Buffett Indicator and FINRA's free margin-debt data before building anything, per the audit's own instruction to scope before committing to a build. Then the Regime Map follow-up noted above.

---

## 2026-10-03 (5) — Coverage Audit Phase C: bubble-gauge scoping (research only, per the audit's own instruction)

**The ask.** Phase C's own definition in the coverage audit is explicit: "needs a scoping pass before committing to a build" — scope all 6 of Dalio's late-stage-bubble dimensions for free-data buildability, don't build yet.

**Method.** Checked each dimension live rather than relying on the audit's own guesses (which were right on some, wrong on others):

- **Dimension 1, "prices high relative to traditional measures"** — already built. `indicators/valuations.py` computes a live Buffett Indicator (market-cap/GDP, two numerators: FRED Z.1 official + a Yahoo VTI proxy anchored to a published market-cap level), fully wired into the dashboard at `/valuations` (operator-only, hidden in PUBLIC_MODE, pipeline Pass 8 refreshes it). It was simply never labeled or connected as "part of a bubble gauge" — a framing gap, not a data gap.
- **Dimension 5, "leverage-financed buying"** — the audit's own suggestion (FINRA margin statistics) checked out. `curl -I` on `https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx` returned `200`, `last-modified: Mon, 14 Sep 2026` — genuinely live and actively maintained at a stable URL (the "2021-03" segment is a CMS upload-date artifact from whenever the file was first created at that path, not a staleness signal — confirmed by the live last-modified header, the same kind of trap the Shiller CAPE check caught the OTHER way around earlier this session). No login, no API — direct Excel download only, monthly since 1997. **Buildable, not yet built.**
- **Dimension 6, "extended forward purchases"** — not one of the audit's suggestions, found independently: CFTC Commitments of Traders reports are published free via an official Socrata REST API (`publicreporting.cftc.gov`), no auth, historical futures positioning back to 2006+. Speculative net-long positioning in equity-index futures is a reasonable proxy for this dimension. **Buildable, not yet built** — this contradicts the audit's own assumption that this dimension had no free data.
- **Dimension 4, "uniform bullish sentiment"** — the audit guessed right, confirmed why: AAII's current-week bull/bear/neutral % is public with no login, but fetching the page directly showed the full historical series explicitly gated behind a $198/yr AAII membership. A single current snapshot can't feed a Z-score composite the way this project's signals work. **Confirmed dead end.**
- **Dimensions 2 and 3** ("prices discounting unsustainable future conditions", "new/unsophisticated buyers") — searched for a free forward-earnings/analyst-consensus series and a free retail-participation series respectively; found only proprietary research products (FactSet Earnings Insight, bank outlook notes) and academic papers discussing the concept with no live public feed for either. **Confirmed dead ends.**

**Verdict.** 2 of 6 dimensions are genuinely free-buildable and not yet built (leverage via FINRA, positioning via CFTC); 1 already exists but was never connected to this framing; 3 are real dead ends, not oversights. A full 6-dimension "Bubble Gauge" the audit may have had in mind was never realistic on free data — at most a 3-dimension partial gauge (valuation + leverage + positioning) is honestly buildable. Documented per-dimension in `session-checklist.md` so the next session doesn't re-research any of this from scratch.

**Not done this session, deliberately** — per Phase C's own scope, this was research only. Building the FINRA/CFTC ingestion and wiring a 3-dimension gauge display is flagged as a real future-session task.

---

## 2026-10-03 (6) — External validator badges shipped (CFNAI + trimmed-mean CPI/PCE), independently validated plan first

**The ask.** A `docs/external_validators_plan.md` was dropped into the repo by a parallel session (the one running the Dalio chip-audit work) — a plan to promote `indicators/audit_benchmarks.py`'s one-off CLI audit into a live dashboard badge, with a downstream consumer (CreovaOne's Beta Engine) explicitly parked waiting on it. Asked to review the plan for independent validation before anyone built it.

**Validation pass (no code changes).** Traced every claim in the plan back to real code, in both this repo and CreovaOne's (`/mnt/data/projects/finance/CreovaOne`) — line counts, function names, thresholds, the proposed `validator_verdicts` schema. Found CreovaOne's `IndicatorsMachineMacroAdapter.validator_verdicts()` already has a hardcoded SQL query against that exact table, nearly column-for-column — the two sides were built in lockstep. CreovaOne's `PLAN_Beta_Engine.md` confirms their half-life decision is parked on this table existing; it's currently a silent no-op. One real nuance flagged: `compare_axis()`'s nested return needs a small flatten/rename step before insert, contrary to the plan's "close to a direct INSERT" framing — minor, not a blocker. Resolved the plan's one open question (Scotti Surprise Index spike) directly: no live 2026 feed found, confirmed dead end. Verdict: sound, build item 1 first.

**Shipped — CFNAI + trimmed-mean CPI/PCE validator badges.** New `ValidatorVerdict` Pydantic model (`indicators/models.py`) and `validator_verdicts` DuckDB table (`store/store.py`, schema locked to CreovaOne's existing query — do not change column names/order without updating that side too). `indicators/audit_benchmarks.py` gained `persist_validator_verdicts()`: flattens `build_evidence_pack()`'s per-axis nested result into one row per (axis, validator_key) and upserts. Wired into the pipeline as **Pass 10** (US-only, best-effort, same cadence as the chips themselves).

**Dashboard:** Command Center header gained a small "validated G ✓ · I ~" pill next to Chip Direction Agreement / persistence — reads the persisted table (cheap), rolls up via a new `summarize_validator_axis()` in `shared_components.py` that mirrors CreovaOne's own `app.core.validator_badges.summarize_axis()` rollup rule exactly (UNKNOWN ignored, any CONTRADICT wins, else any PARTIAL wins, else AGREE) so a badge here and a badge there never disagree. New **Validator Audit Monitor** page (`/validator-audit`, Monitors nav group — not Reference/Admin as the plan suggested, since this session's own Phase 3/4 work just established the shared `_chart_card` style as the Monitors-group standard and this page fits that mold better than methodology.py's document style) — one dual-line card per benchmark (our chip's windowed Z vs. the benchmark's own rolling Z, same comparison `compare_axis()` computes), AGREE/PARTIAL/CONTRADICT header per card, disagreement-episode notes. Recomputes live on each render (not from the snapshot table) so the detail page is always current. `_chart_card` needed no further changes — `fmt_override` (built in Phase 4) was enough to show the verdict word as the header value.

**Real bug caught before shipping.** Pass 10 first run inside the actual pipeline (not the standalone test) failed: `Connection Error: Can't open a connection to same database file with a different configuration than existing connections`. Root cause: `persist_validator_verdicts(conn=pipeline_conn)` correctly reused the pipeline's connection for the WRITE, but `build_evidence_pack()` → `chip_state()` → `load_composite_history()` always opened its OWN fresh read-only connection to the same file regardless — two connections, different configs, same file, while the pipeline's own was still open. Fixed by threading `conn` all the way down (`load_composite_history`, `chip_state`, `build_evidence_pack` all gained an optional `conn` param, defaulting to the old open-your-own behavior when None). Caught by actually running the full pipeline end-to-end rather than trusting the standalone test — the standalone test had been silently reading real production data through its OWN untouched connection the whole time, which is exactly why it didn't catch this.

**Also caught: the pipeline/charting/scheduler image-drift trap, again.** `docker compose build charting` does NOT rebuild the `pipeline` or `scheduler` images — three separate image tags from the same Dockerfile. This is a previously-documented hard lesson (memory `feedback-docker-rebuild`, incidents from 2026-07-06 and 2026-07-31) that got missed again this session: ran `docker compose build charting` repeatedly all session but never `pipeline` or `scheduler` until this feature's own pipeline-integration testing forced the issue. Rebuilt and restarted all three before finishing. Worth noting as a plausible (not confirmed) partial explanation for this session's earlier "03:00 scheduled run silently dropped rolling-composite columns" finding (worklog entry (2) above) — if `scheduler` was running stale code at that point too, that's a more mundane explanation than a genuine transient failure, though the exact trigger was never conclusively identified either way.

**Verification.** 647 tests pass, zero exclusions (24 new: persist round-trip + idempotency with a properly-seeded in-memory DB, the rollup rule's full truth table, episode-note formatting, the Command Center badge's color/symbol logic). Full pipeline re-run end-to-end confirmed Pass 10 writes 15 rows matching the original CLI audit's own documented tallies exactly (4 AGREE/6 PARTIAL/0 CONTRADICT growth, 2/3/0 inflation). Live-verified the Command Center badge and the new Validator Audit Monitor page in the browser.

**Next.** Philadelphia Fed SPF (item 2 of the plan — quarterly, needs its own loader, lower-frequency UI treatment) when there's appetite for it; otherwise back to Phase 5 of the Dashboard IA Blueprint or further coverage-audit tails.

---

## 2026-10-03 (7) — External validator badges item 2: Philadelphia Fed SPF, a true forecaster-surprise measure

**The ask.** Build item 2 of `docs/external_validators_plan.md` — the Survey of Professional Forecasters. The plan correctly flagged this as "a genuinely different shape of work" from item 1 (CFNAI/trimmed-mean CPI): not FRED-hosted, quarterly not monthly, and capable of a true forecaster-consensus SURPRISE measure (actual vs. what professional economists predicted) rather than the Z-score-vs-own-history approach every other validator on this dashboard uses.

**Research before writing any code** (per house rule — never invent a series or a file format). Verified live: `Median_RGDP_Growth.xlsx` and `Median_CPI_Level.xlsx` both resolve (200, correct xlsx content-type) at Philly Fed's own static CDN paths — no API, direct Excel downloads, the same pattern already used for FINRA margin stats in the Phase C scoping pass. Read the SPF's own 61-page documentation PDF (via the PDF-reading Read tool, since WebFetch couldn't parse it) to get the horizon convention right rather than guessing from column names: survey conducted in quarter Q, suffix "2" = Q itself (an in-quarter nowcast using partial data), "3" = Q+1 (the first genuinely ex-ante forecast), "4"/"5"/"6" = further out; CPI additionally carries "1" = Q-1 (backward estimate). Confirmed the filename "Median_CPI_Level.xlsx" is misleading — the variable itself is already rate-form, not an index level, per the doc's own text.

**Design decision — which forecast counts as "the prediction."** The in-quarter nowcast (h2) uses partial information collected mid-quarter, which is a weaker, more ambiguous basis for a "surprise" claim. Used the academically standard construction instead: survey Q-1's "one quarter ahead" (h3) forecast — made *before* quarter Q began — shifted forward to align with Q, then compared against Q's realized actual once FRED/BEA publish it. This is a `.to_period("Q") + 1` shift, not a guess.

**Shipped — `indicators/spf_loader.py`** (new, ~230 lines): its own small loader (urllib + openpyxl, not a `fetch_series` reuse, exactly as the plan anticipated), 7-day TTL raw-cache with stale-cache fallback mirroring `loader.py`'s own convention. `compute_spf_surprise()` and `forecast_vs_realized()` (point reading vs. full history for charting). Realized actuals: growth reuses `A191RL1Q225SBEA` — already a verified benchmark in `audit_benchmarks.py`'s own registry, zero new sourcing, exact same QoQ-annualized convention SPF uses. CPI has no ready-made FRED series in that convention, so it's derived from `CPIAUCSL` (already backing `inflation.cpi_headline`) via the standard quarterly-average-then-annualize transformation — a derived identity, not an invented series, same standard this project already applies to `debt_income_spread`/FX reserve runway/etc.

**Two real bugs caught before shipping, both found by actually running the code against live data, not by inspection.** (1) The realized-CPI derivation initially used whatever months were available in the latest quarter without checking completeness — with September not yet released, the Q3 average silently used only Jul+Aug, producing a wildly wrong (and wrong-direction) "surprise" purely from data incompleteness, not a real forecast error. Fixed by requiring all 3 months present (`resample(...).count() == 3`) before a quarter counts as realized — an incomplete quarter now correctly reads as unresolved (NaN) rather than a fabricated rate. The fix also correctly, automatically excluded Q4 2025 and (transitively, via the QoQ base) Q1 2026 once testing surfaced a genuine one-month gap in `CPIAUCSL` around October 2025 — exactly the kind of gap `is_stale`/completeness checks exist to catch, discovered incidentally while testing this feature. (2) `forecast_vs_realized()`'s charting path crashed in the live container with `ValueError: Invalid frequency: QE` — `Period.to_timestamp()` wants the old `"Q"` alias, not pandas 2.2's newer `"QE"` resample alias; I'd written it inconsistently with the (correct) single-point lookup in `compute_spf_surprise()` two functions away. A DB-guarded test (`try/except: return`, the same pattern every Monitor page's layout test uses) silently swallowed this exact crash — only caught by actually loading the page in the browser, which is why that step isn't optional.

**Dashboard.** New section on the existing `/validator-audit` Monitor page (not a separate page — same page, explicitly a different *kind* of card within it, per the plan): "Survey of Professional Forecasters (Philadelphia Fed)" with a "last SPF read: Qx 20xx" freshness chip and two dual-line `_chart_card`s (forecast-made-one-quarter-ahead vs. realized actual, full history) for growth and CPI — deliberately NOT part of the AGREE/PARTIAL/CONTRADICT tally above it on the same page, exactly as the plan specified. No pipeline DB write at all for this feature (unlike item 1's `validator_verdicts` table) — the loader's own TTL cache is the only persistence; **Pass 11** just proactively triggers that check daily so the first visitor after a gap isn't the one paying the fetch latency.

**Live reading, 2026-10-03:** Q2 2026 growth surprise +0.10pp (realized 2.2% vs. 2.10% forecast — close). Q2 2026 CPI surprise **+3.35pp** (realized 6.07% QoQ-annualized vs. 2.72% forecast — a large inflationary miss), thematically consistent with this session's other inflation signals (PPI +9.85%, crude oil +53% YoY, the chip audit's own window-sensitivity finding).

**Verification.** 11 new tests (`tests/test_spf_loader.py`: survey-date math, the incomplete-quarter guard with a synthetic gap reproducing the real `CPIAUCSL` gap, the surprise-matching logic, empty/missing-data guards — all via monkeypatch, no live network in CI). 654 tests pass, zero exclusions. Rebuilt and redeployed `charting`, `pipeline`, AND `scheduler` this time (see the "docker image drift" note below). Full pipeline re-run confirmed Pass 11 end-to-end (464 survey-quarter rows cached across 2 variables). Live-verified in the browser on a fresh tab after the QE/Q fix — confirmed a stale error in an older tab's console buffer was leftover from before the fix, not a live issue, by opening a brand-new tab and reloading clean.

**Repeated and reinforced an existing hard lesson.** Missed rebuilding `pipeline`/`scheduler` again for the first pass of this feature too (same gap as entry 6, just now) — caught it faster this time since I knew to check, but still worth noting the habit isn't fully internalized yet.

**Next.** Item 3 (Scotti Surprise Index) is a confirmed dead end per the Phase C scoping pass — nothing further to build there. `docs/external_validators_plan.md` is now fully worked through (items 1, 2 shipped; item 3 closed as not viable).

---

## 2026-10-04 — Dashboard IA Phase 5: Regime History retrofitted to shared chart-cards + color-consistency pass

**The ask.** Finish Phase 5 of the Dashboard IA Blueprint — previously deferred (user chose to skip it in favor of the coverage-audit work) since its five named targets (Regime Map, Regime History, Debt Stress, Global Overview, Relative Cycles) are mostly scatter plots, tables, and heatmaps rather than single-series charts, so a uniform "convert to `_chart_card`" doesn't apply the way it did for Phase 4. Resumed on explicit request.

**Scoping pass across all five pages before touching code.** Read each page's actual chart-building code (`dashboard/charting.py`'s `_page_regime_map`/`_page_regime_history`/`_page_debt_stress`, `dashboard/global_overview.py`, `dashboard/relative_view.py`) rather than assuming from the page name:
- **Regime Map** — a single interactive scatter (growth-vs-inflation quadrant + history trail). Not single-series; no retrofit candidate.
- **Regime History** — a 7-row `make_subplots` stacked mega-figure (regime dual-band, then Growth Z/Momentum, Inflation Z/Momentum, Direction Agreement, Disequilibrium). **The real match** — architecturally identical to the force_detail.py mega-chart Phase 4 already fixed; 6 of 7 rows are genuine single series, only the regime dual-band row is categorical.
- **Debt Stress** — a quadrant scatter, a 2-row stage timeline (categorical band + 4-way score overlay), and a composite-stress-vs-7-component-overlay chart. The multi-line overlays are *intentionally* comparison charts (seeing which components drive stress at a glance) — splitting them into individual cards would be a usability regression, not an improvement. No structural retrofit.
- **Global Overview** — a cross-country data table. Not charts at all.
- **Relative Cycles** — per-country summary cards (already card-shaped) + correlation heatmaps. Heatmaps aren't single-series by nature.

**Shipped — Regime History retrofit.** Replaced the single 7-row `make_subplots` figure with: a compact standalone band chart (`_build_regime_band_chart()`, new) for the categorical regime-label row, plus 6 `_chart_card`s (Growth Z, Growth Momentum, Inflation Z, Inflation Momentum, Direction Agreement, Disequilibrium) in a `_section()` grid — the callback (`update_regime_chart`) now returns `(band_fig, cards_children)` instead of one `go.Figure`. `_chart_card` gained a new `vline_x` parameter (a single vertical dashed reference line, distinct from the existing horizontal `hline`/`hline2`) specifically to carry over the page's "step through history" feature — every card now draws its own vline at the currently-selected date, verified live by stepping back with the Prev button and watching all 6 cards' markers move together with the header's date display.

**Deliberate, accepted tradeoffs** (same shape as Phase 4's): the old figure's cross-subplot shared-hover-line (a hand-rolled clientside callback, `rh-shared-hover-line`) is gone — each card now gets independent hover, consistent with every other chart-card page on the dashboard; removed the now-dead clientside callback and its `hover-sync-init` store entirely rather than leaving unreachable code. The "click anywhere on the old mega-chart to jump the selection there" callback (`select_regime_point`) is repointed at the band chart only — `_chart_card`'s internal `dcc.Graph` is intentionally anonymous (no stable id to wire click handlers onto per-card), so click-to-jump is now scoped to the band strip; the Prev/Now/Next buttons remain the way to step from anywhere on the page. Updated the Field Guide help panel's "Chart Rows" section to describe the new band-strip-plus-cards layout instead of the old numbered-rows language.

**Color-consistency pass** (the IA framework's other standing rule — "import a named color, don't retype a hex literal") — found genuine drift in the two pages that hadn't been touched by the earlier Phase 2 consolidation: `relative_view.py` had three `"#E8A317"` warning-chip colors and a notes-block border/background/text that should all have been `AMBER` (one of the three even used a *different* amber shade, `#F4C842`, for the text right next to a `#E8A317` border — drift within one component), plus a correlation-heatmap colorscale retyping `BLUE`/`FORCE_COLOR["inflation"]`'s exact hex values. `global_overview.py` had a chart line color that should have been `AMBER`, a legend swatch and a data-confidence badge background that were exact `BLUE`/`GREEN` duplicates sitting a few lines from an already-correctly-imported `GREEN`, and one judgment call: a "negative threshold" hline was hardcoded to `FORCE_COLOR["inflation"]`'s exact hex even though the chart has nothing to do with inflation specifically — paired with a `GREEN` "positive threshold" hline right above it, the semantically correct fix was `RED` (generic negative), not the inflation force color that happened to share the same hex by coincidence — exactly the distinction the framework's own docs call out ("a force's identity color isn't a good/bad judgment"). Left two colors unchanged (`#9AA4B2`, `#E8853A`) that are visually close to but not exact matches of any canonical value — no evidence they're accidental drift rather than deliberate distinct shades, so forcing them to the nearest named color would be an uninvited visual change, not a consolidation.

**Verification.** Found and fixed 5 now-obsolete tests in `tests/test_charting.py` that asserted the old single-figure architecture (trace counts, `xaxis.matches == "x7"`, the deleted hover-sync callback's exact wiring) — rewrote them to verify the new `(band_fig, cards)` return shape and the vline-tracks-the-step behavior, rather than leaving them silently passing against a return value that no longer existed or deleting coverage outright. 654 tests pass, zero exclusions. Live-verified: Regime History's band chart + all 6 cards render correctly; stepping back via Prev moved the header date, the band chart's highlight circles, and every card's vline together; Regime Map (which shares `regime-info-box`/`regime-step-button` with Regime History) unaffected; Relative Cycles' heatmaps and country-card amber note boxes render with identical colors post-refactor (confirmed via the rendered Plotly colorscale JSON, not just a visual glance); Global Overview's table and legend unaffected.

**Next.** Phase 5 is now complete per this session's scoping — the one genuine stacked-mega-chart target is fixed, the two pages with real color drift are consolidated, and the remaining three pages (Regime Map, Debt Stress's overlay charts, Global Overview's table) are documented as deliberately out of scope for the card pattern rather than silently skipped.

---

## 2026-10-04 (5) — Signals pages: shared crosshair + new card layout

Per-metric chart cards (Phase 4) had lost the old stacked-subplot synced hover. Added `dashboard/assets/hover_sync.js` + `_chart_card(sync_hover=True)`: hovering one card shows the same date (nearest observation at or before) on every other card; used on all six `/signals/{force}` pages and Regime History (not the Monitors pages — their cards are unrelated metrics). Observer is a throttle, not a debounce (Regime History mutates continuously and starved the debounce version). Layout: `_section(columns=N)` — composite Z-score/Momentum cards full-width one-per-row, basket signal cards (raw + Z pairs) two per row, on all force pages. Regime History's card grid is unchanged. Suite 678 passed.

---

## 2026-10-04 (4) — DuckDB bloat: root cause fixed (in-place upserts), not another compaction

**Why this was still an issue.** Commit `4c2026a` ("auto-compact after every import") had been made on a side branch (`claude/serene-clarke-3321dd`) and **never merged to `main`** — so the NAS scheduler image never contained it, and the file kept growing to 10.9 GB. It was also the wrong kind of fix: a nightly compaction treats the symptom and needs the dashboard down for it.

**Root cause (measured, not assumed).** Every `upsert_*` in `store/store.py` was DELETE-then-INSERT of the full history on a table with a PRIMARY KEY. DuckDB cannot physically reclaim DELETEd tuples on a PK table, so each pipeline run leaked a complete copy of the table: `signals` had 52,051,808 physical rows for 368,150 live. Replaying the same churn in isolation: current code +368k physical rows/run; same table with the PK dropped = flat; **`INSERT … ON CONFLICT (keys) DO UPDATE` with the PK kept = flat.** Dropping the PK would have traded away the idempotency guarantee (CLAUDE.md rule #6), so ON CONFLICT it is.

**Fix.** New `_upsert_in_place()` (one INSERT…ON CONFLICT DO UPDATE) is now the only upsert path for `signals`, `composites`, `debt_stress_snapshots`, `debt_cycle_stage_snapshots`, `validator_verdicts`. The old month/quarter *bucket* semantics (a new mid-month `as_of` replaces that month's earlier row) are preserved by `_delete_stale_bucket_rows()`, which only touches the handful of rows whose date moved. Side benefit: the SET list names only the base columns, so the rolling-window composite columns (`growth_score_48m`, `inflation_score_90m`, …) are no longer blanked by the baseline write — the likely mechanism behind the 2026-10-03 "scheduled import dropped rolling columns" incident. `vintage_store.py` (history.duckdb) was checked — it only deletes *changed* rows, so it doesn't leak materially.

**Verified.** Replayed the full pipeline twice on a scratch copy: physical rows == live rows for all 5 tables after both runs (was +368k/run); file 133 → 160 MB on the first run (WAL/free-block settle), **flat on the second**; rolling columns intact (539/562 US rows). 9 new tests in `tests/test_store.py` (no-growth per table via `pragma_storage_info`, bucket semantics, rolling-column preservation) — 5 of them fail on the old code. Suite **677 passed**.

**Deployed.** Rebuilt charting/pipeline/scheduler; one-time compaction of the live NAS file with new `scripts/compact_db.py` (`COPY FROM DATABASE` — keeps the PKs that a `CREATE TABLE AS` copy would silently drop): **10.9 GB → 132.9 MB**, original kept as `signals.duckdb.bak` (delete once happy). The per-import compaction hook from `4c2026a` is deliberately NOT adopted. **Still to do on the Oracle VM:** `git pull` + rebuild + `up -d charting scheduler` (its DB is already compact, but runs the old leaky code until updated).

---

## 2026-10-04 (3) — Oracle Cloud VM migration: parallel instance live (not cut over)

**What was done.** Stood up a full second copy of the dashboard on the Oracle Cloud ARM VM (Oracle Linux 9, aarch64, 10 GB RAM): installed Docker CE + compose plugin + git from the el9 repos, cloned the public repo, copied `.env` (secrets over scp only, never printed) with `HOST_DATA_DIR`/`HOST_DB_DIR`/`TZ` appended, rsynced the data dir (15 MB, excluding `traffic.log`/`schedule_status.json`), built all three images natively on ARM64, started `charting` + `scheduler` (never bare `up -d` — the one-shot `pipeline` service stays out of it). Both containers `restart: always`, Docker enabled at boot. Acceptance test = the project's own standard: the **full pipeline ran on the VM** (all 14 countries, Passes 1–12, same OK counts and the same known exit 1 as the NAS), then charting restarted; the dashboard's Command Center values matched the NAS exactly.

**Key finding — the NAS `signals.duckdb` is 10.9 GB of which ~133 MB is real data.** Row-checked before assuming: 368,150 rows, zero duplicate `(id, as_of)` keys, 556 signals. The rest is dead space — the idempotent delete-then-insert upserts (`upsert_signals`, `upsert_composites`, …) never return freed blocks to the file, so it grows every pipeline run. Migrated a **compacted copy** (`ATTACH … (READ_ONLY)` + `COPY FROM DATABASE` into a fresh file, per-table row counts verified equal for all 6 tables; source untouched) — 10.9 GB → 133 MB, which also turned a 20-minute-class transfer into a few minutes. **(Superseded by the 2026-10-04 (4) entry — root cause since fixed.) The bloat continued on the VM at first:** one pipeline run grew the compact file 133 → 247 MB (~114 MB/run); at the 17 GB free left, a daily schedule fills the disk in roughly five months. Not fixed here (out of the migration's scope, and it needs a careful compaction step in the pipeline/scheduler) — **open follow-up, and the same bloat is eating NAS disk right now.**

**Unrelated pre-existing finding.** Brazil's central-bank API (`api.bcb.gov.br`) does not resolve in DNS from the NAS either (9 errors in the NAS's own pipeline log), so the 3 BCB Brazil series fall back to stale cache on both machines — not a migration regression.

**Deliberately NOT done (decisions for the owner).** (1) No public exposure — no OCI security-list ingress, no firewalld port; reached via `ssh -L`. Going public needs the ingress rule **and** `PUBLIC_MODE=1` (the VM currently runs operator mode with the write-capable Settings/Weight-Audit surfaces). (2) No cutover — the NAS keeps running with its own DB; both instances run their own 03:00 CT auto-import against the same free APIs. Facts for the VM are in memory `reference-oracle-vm`; update procedure: `git pull && sudo docker compose build charting pipeline scheduler && sudo docker compose up -d charting scheduler`.

---

## 2026-10-04 (2) — Coverage Audit Phase C build-out: Late-Stage Bubble Gauge (3 of 6 dimensions)

**The ask.** Build out the 3 dimensions the 2026-10-03 Phase C scoping pass confirmed were genuinely free-buildable: valuation (already built — the Buffett Indicator), leverage (FINRA margin debt, new), and positioning (CFTC leveraged-fund futures positioning, new). Explicitly NOT a 6-dimension gauge — that scoping pass was clear a full Dalio bubble composite was never realistic on free data; the other 3 dimensions (sentiment, forward-earnings pricing, new-buyer participation) stay confirmed dead ends.

**Re-verified both new sources live before writing any code** (the scoping pass had only checked they existed, not their exact shape). FINRA's `margin-statistics.xlsx` — downloaded and parsed: one sheet ("Customer Margin Balances"), `Year-Month` + 3 dollar columns, 1997-01 through 2026-08, 356 rows. CFTC's Socrata API — the scoping pass's own search turned up a candidate dataset id (`gpe5-46if`, Traders in Financial Futures) and contract code; queried it live directly rather than trusting the search summary, confirmed real field names (`lev_money_positions_long/short`, `open_interest_all`, etc.) and genuine history back to 2006-06-13 (1060 weekly observations for E-mini S&P 500).

**Shipped — `indicators/bubble_gauge.py`** (new). `fetch_margin_debt()` and `fetch_leveraged_fund_positioning()` — both their own small loaders (FINRA: direct xlsx download, same raw_cache/TTL/stale-fallback convention as the SPF loader; CFTC: Socrata REST query, JSON parse). `_margin_debt_pct_gdp()` derives margin debt as % of nominal GDP (reusing `indicators.loader.fetch_series("GDP", "Q")` — no new FRED binding) — the same GDP-normalization the Buffett Indicator itself uses, for a directly comparable "is this elevated" read. `compute_bubble_gauge()` assembles all 3 dimensions as independent **full-history Z-scores** — deliberately not averaged into one score; the module's own docstring states why (3 partial dimensions averaged into one number would manufacture false precision this data doesn't support). Dimension 1 (valuation) reads the Buffett Indicator's own already-cached `buffett_data.json` rather than recomputing it — reused, not rebuilt, per the plan.

**A real design problem caught by actually computing the numbers, not just writing the code.** The first pass used a single signed-Z magnitude scale (`z >= 1.5 → Extreme`, etc.) for all 3 dimensions. Valuation and leverage are *trending* ratios where only the high side is bubble-relevant (low valuation isn't a bubble risk). Positioning is a *mean-reverting oscillator* where either tail matters — leveraged funds are currently net SHORT the E-mini (Z = -1.35), and the original signed scale labeled that "Low," which reads as "low risk" when it's actually a noteworthy crowded-short extreme, just in the other direction. Fixed by making the magnitude label `abs(Z)`-based (direction-agnostic) and adding a per-dimension directional note shown alongside it ("crowded long"/"crowded short" for positioning; "above/below its own history" for the trending pair) — caught and fixed before shipping, not after.

**Dashboard.** New `/bubble-gauge` Monitor page (`dashboard/bubble_gauge_monitor.py`) — three `_chart_card`s (one per dimension, each its own force-adjacent color), a header chip row showing each dimension's label at a glance, and prose stating plainly that this is 3 of 6 dimensions with no combined score. Gated operator-only (`OPERATOR_ONLY_ROUTES`, same convention as `/valuations`, whose data this page's valuation dimension reuses) — hidden in PUBLIC_MODE, consistent with the existing Buffett Indicator's own gating. Lives in the Monitors nav group (curated, feeds no composite — same convention as Validator Audit). Pipeline **Pass 12**: proactive cache-refresh only, no DB table (same shape as Pass 11's SPF pass) — the page recomputes live from the TTL-cached raw data.

**Live reading, 2026-10-04:** Buffett Indicator 243.9% of GDP (+2.66σ, Extreme) · Margin debt 4.46% of GDP (+3.05σ, Extreme) · Leveraged-fund E-mini positioning -19.65% of open interest (-1.35σ, Elevated/crowded short). Two of three dimensions reading at historical extremes simultaneously; the third reading an extreme in the opposite direction from "euphoric long" — a genuinely informative, not generic, first read.

**Verification.** 24 new tests (`tests/test_bubble_gauge.py`, `tests/test_bubble_gauge_monitor.py`) — Z-score math, the direction-agnostic label logic (explicitly testing that ±2.0 both read "Extreme"), FINRA/CFTC parsing against synthetic fixtures (including a div-by-zero guard on CFTC's open-interest field and a GDP-unit-conversion check, $ millions vs $ billions), and a test confirming one dimension's failure doesn't take down the other two. 668 tests pass, zero exclusions. Full pipeline re-run end-to-end confirmed Pass 12 (3/3 dimensions cached successfully). Rebuilt and redeployed all three Docker services (`charting`/`pipeline`/`scheduler`) this time without needing the reminder. Live-verified the page in the browser — all 3 cards, the header chips, and the directional positioning label all render correctly.

**Next.** Nothing further scoped for the bubble gauge — Phase C is now fully closed (scoped 2026-10-03, built 2026-10-04). The external-validator-badges plan is also fully closed (items 1 and 2 shipped, item 3 confirmed dead). Open threads: Philadelphia Fed SPF was the last item of that plan; no further coverage-audit or IA-blueprint work remains queued.

---

## 2026-10-03 — Independent chip-audit skill + first audit: the inflation score is a window artifact

**The ask.** Build a skill that acts as an independent agent trained in the Dalio framework and reviews the dashboard's indicator determinations for accuracy, using outside sources to ground-truth what we show — starting with Growth and Inflation only, with historical-episode scoring to follow.

**Design decision that reframed the task.** "Do experts agree?" is the *weakest* of three available ground truths, because the chip is not the claim "the economy is growing" — it is the claim "the composite sits more than `gz` sigma above **its own rolling norm** and is rising." An expert confirming the LEVEL does not confirm the RELATIVE claim, so naive comparison manufactures fake findings. Agreed hierarchy: **Tier 1 numeric benchmarks** (reproducible, the backbone) > **Tier 2 institutional narrative** (FOMC/IMF/OECD) > **Tier 3 commentary** (noisy, recency-biased; on Dalio's own terms consensus is to be tested, not deferred to). The decisive insight is that published composites exist which are *structurally the same kind of object* as our chips — standardised, mean-zero, publisher-thresholded — so the comparison can be **numeric over full history** rather than rhetorical.

**Built — `indicators/audit_benchmarks.py`, 15 validation-only FRED series, all endpoint-verified 2026-10-03.** Growth: `CFNAIMA3` (primary — the only external benchmark both standardised AND publisher-thresholded at ±0.70, so the sharpest test of our `gz` calibration), `CFNAI`, `CFNAIDIFF`, `WEI`, `GDPNOW`, `STLENI`, `A191RL1Q225SBEA`, `SAHMREALTIME`, `RECPROUSM156N`, `USREC` (the historical arbiter). Inflation: `MEDCPIM158SFRBCLE`, `TRMMEANCPIM158SFRBCLE`, `PCETRIM12M159SFRBDAL`, `CORESTICKM159SFRBATL`, `MICH`. Rejected as dead or unusable: `USALOLITONOSTSAM` (OECD US CLI, ends 2024-01 — the OECD die-off again), `USSLIND` (ends 2020-02), `ADSBCI` (does not exist on FRED), Conference Board LEI (proprietary).

**NON-NEGOTIABLE in the module and enforced by a test: validation-only.** No benchmark may ever be bound as a signal — the moment one feeds the composite it audits, the audit is circular. `test_no_benchmark_is_also_an_input_signal` scans `us_bindings.yaml` plus every `countries/*_bindings.yaml` on each run and **caught a real case on its first execution**: `EXPINF1YR` was already ingested as `market.exp_infl_1y`. Not in the inflation basket, but a series inside our own system cannot be offered as independent corroboration of it — dropped from the registry, rejection documented.

**Honest caveat written into the module, the skill and every report:** these benchmarks are independently *constructed*, not input-*independent*. CFNAI's 85 inputs include our payrolls/IP/retail sales/capacity utilisation; median/trimmed/sticky CPI re-aggregate the same BLS price quotes. High correlation is therefore partly mechanical and proves little — the informative outputs are **CONTRADICT verdicts, disagreement episodes and lead/lag**.

The module reproduces the live chips by importing `_classify_regime` / `compute_dynamic_thresholds` from `dashboard.charting` (never reimplementing them), mirroring `command_center`'s window resolution and latest/delta semantics, so the audit cannot drift from what a user sees. Read-only on the DB throughout. Deterministic verdict grid in `_verdict()` (AGREE/PARTIAL/CONTRADICT/UNKNOWN) so the tally is reproducible run to run; publisher thresholds beat the ±0.5σ fallback; **an unfired regime flag reads Neutral, not Above** (absence of a recession call is not a growth call); `best_lag()` scans ±6 months by Spearman with positive = our composite led. `--blind` emits the panel with our read, verdicts, correlations and all internal prose stripped — enforced by a test, because a reviewer who learns a chip exists reasons backwards from it.

**Built — the skill at `.claude/skills/dalio-audit/`** (SKILL.md + `references/benchmarks.md`, `grading.md`, `report_template.md`). Four-stage protocol: Stage 0 pins the read with production code; Stage 1 spawns **two mutually-blinded subagents** (quantitative on the blind JSON only; narrative on web Tier 2/3 only, each unaware of the other and of the dashboard); Stage 2 reveals and scores on a fixed verdict vocabulary (`CONFIRMED` / `CONFIRMED-WITH-CAVEAT` / `DISPUTED-TIMING` / `DISPUTED-LABEL` / `INSUFFICIENT-EVIDENCE`, each requiring a **falsifier line**); Stage 3 files a dated report plus an append-only log row and a punch list that changes nothing without approval. `grading.md` front-loads the things that look like bugs but are documented design (Transition on plateaus, dynamic thresholds, display-only full-history Z, the IMF annual CPI bridges) so the reviewer cannot "discover" them. Explicitly does NOT rebuild historical replay — `indicators/backtest.py` and `backtest_g3.py` already do PIT and ALFRED-vintage replay; the skill's job is the layer they lack (what the outside world said at the time, scored as lead/lag vs `USREC`).

**First audit run — `docs/audits/dalio_audit/US_2026-10.md`, logged in `docs/audits/dalio_chip_audit_log.md`.** Growth chip **Growth** and Inflation chip **Transition** both graded `CONFIRMED-WITH-CAVEAT`, with **zero CONTRADICT verdicts across 15 benchmarks** (G 4A/6P/0C, I 2A/3P/0C). Growth tracks `cfnai_ma3` at **Spearman 0.761 at lag 0** and `cfnai_diffusion` at **0.783 at lag 0** — no systematic lag, a clean pass. Input freshness verified rather than assumed, and it reconciles to externally retrieved prints: our `cpi_headline` 3.353% vs BLS 3.4%, `pce_core` 3.008% vs BEA 3.0%, `wages` 3.086% vs AHE 3.0%, no staleness flags.

**Headline finding — the inflation score is a window artifact.** Same month, by window: full history **+0.040**, 120m −0.070, **90m (canonical) −0.310**, 60m **−0.904**, 48m −0.622, 36m −0.509. A **0.94-point spread from window choice alone**, because every post-2019 window is dominated by the 2021–23 shock (60m reaches back only to Oct 2021, almost entirely inside it). So the chip reads "below its own norm" in the same week the FOMC **raised rates 25bp to 3.75–4.00% — its first hike since 2023** — with headline CPI 3.4%, core PCE 3.0%, the SEP projecting core PCE *rising* to 3.4% Q4/Q4, and the OECD noting "signs that inflation has begun to rise again". Against the 2% target inflation is above it on every gauge. **The blind quantitative reviewer identified the window contamination independently, with no knowledge that a dashboard existed** — the blinding paid for itself on the first run.

**Where the design earned credit.** The momentum gate blocked a Disinflation call (Δ +0.0153) in exact agreement with the Fed, OECD and Cleveland Fed nowcast on direction — the dual-condition rule caught a turn a Z-score alone would have missed. The divergence flag firing TRUE sits alongside BofA's "mild stagflation" base case.

**Second finding.** The inflation composite correlates only **0.17–0.22** coincidentally with median/trimmed/sticky CPI, best fit at **+5 to +6 months**. Largest historical divergence is `sticky_core_cpi` 2004-01 → 2006-03 (**27 months**, our Z +1.47 vs −1.10) — structurally identical to today's oil-led impulse (crude +53% YoY, PPI +9.85%, sticky core 2.96%), since our basket carries `crude_oil` and `breakeven_avg` directly while sticky-price gauges exclude exactly that. Open question: are we measuring the inflation *impulse* rather than inflation?

**Risk carried forward, deliberately not graded as a failure.** Audited on Aug-2026 vintage one day after a September jobs report (+29k, July revised to −10k, −60k net revisions, U3 4.2%, 12m avg +45k) the chip legitimately cannot yet see. Our growth basket is labour-heavy (payrolls 0.64 + unemployment 0.25 + job_openings 0.25 + participation 0.10) — the over-representation Ray flagged 2026-07-05, still open. Judging a chip against data it cannot have is the exact error this skill exists to prevent, but if the Growth label flips once September ingests, that is direct evidence for his re-weighting recommendation.

34 new tests (`tests/test_audit_benchmarks.py`); suite **588 passed**. One pre-existing unrelated failure: `tests/test_explorer.py::test_load_signal_overview_returns_all_signals` expects 91 US signals against 105 in the DB, from the in-flight uncommitted `us_bindings.yaml` work.

**Same-day follow-through — Ray consult + four fixes shipped.** Took the two design-pass items plus the threshold-calibration question to Digital Ray (full rulings in `docs/Guidance/ray_dalio_review_log.md` session 2026-10-03). His verdict on the headline finding: *"That's why your dashboard is out of sync with reality."*

**Ruling 1 — inflation must be anchored to the TARGET.** Growth has no natural "right" level, so relative Z-scoring is correct there; inflation has an explicit policy target and the main chip must be distance from it, with the relative Z demoted to a clearly-secondary read ("If you just show two numbers, people will get confused. If you make one the anchor and the other a secondary signal, you help people see what matters most"). Built `config/inflation_anchor.yaml` (14 country targets, each sourced + TUNABLE; uniform ±0.5pp tolerance chosen over per-country official bands so the read stays comparable across columns) and `indicators/inflation_anchor.py`. US now reads **Above Target +1.01pp** (core PCE 3.01% vs 2.0%) where the relative frame said "below its own norm". Two bugs caught while verifying across all 14: the gap-direction test broke on a zero crossing (AU went +1.31pp → −0.10pp, clearly closing, but a sign-based test called it widening — now compares |gap| magnitudes), and six countries were anchoring to dead monthly CPI mirrors, so series selection now picks the **freshest** configured candidate with config order as tie-break, falling through to the live IMF annual bridge and surfacing `is_stale`/`age_months` rather than quoting an 18-month-old print.

**Ruling 2 — inflation is a two-part machine.** Impulse (flexible prices: crude, breakevens, PPI, headline) vs persistence (sticky: core PCE, core CPI, wages), combined 30/70 and published side by side. The 5–6 month lead the audit found is *"a feature, not a bug"* — it means the composite is a leading impulse index, not a current-state gauge. US reads impulse +0.81 / persistence −0.10 → "supply-side shock that has NOT yet embedded", matching the audit's own Tier-2 finding of a 1.0pp headline-vs-core energy wedge. **Documented departure:** Ray listed trimmed-mean measures inside the persistence index; we exclude them, because those are precisely the audit's independent benchmarks and making them inputs would make the audit circular. Flagged back to him in-thread; enforced by `test_persistence_excludes_audit_benchmarks`.

**Ruling 3 — the 0.23σ growth threshold is right, with safeguards.** "A threshold around 0.2–0.3 sigma works well for a leading indicator… your 0.23-sigma is in that sweet spot" — a diagnostic's job is early warning, not recession dating, so it should be looser than CFNAI's ±0.70. Shipped two of his four safeguards: a **0.15σ floor** on the dynamic threshold (binding for **9 of 14 countries** — they had been running below it, i.e. over-sensitive in calm stretches; US `iz` 0.093 → 0.150) and a **two-consecutive-month sustained filter** on the Z leg, wired at every call site rather than one page (page-level chip inconsistency was a real bug on 2026-08-15). The filter is additive — callers passing no history keep the single-month rule — and short history never blocks a newly-added country. Measured impact: exactly **1 of 14** current chips changes (LU inflation, a one-month spike that did not hold).

**Ruling 4 — late-cycle, labour leads and output lags.** "In a late-cycle setting, labor is often the first to feel the pressure of a tightening short-term debt cycle, while output can still appear robust." So the labour-heavy basket is reading the right signal, but it needs smoothing, not down-weighting: he prescribes the same impulse/persistence split on growth (labour = impulse, output = persistence), a 2–3 month rolling labour average, leading demand signals (credit growth, corporate earnings, consumer confidence), and a credit-conditional weight tilt. Left open as design-pass items.

Also shipped punch item 4 (benchmark `units` field — a blind reviewer had burned real effort working out whether `recession_prob` 0.62 meant 0.62% or 62%). Command Center now renders the anchor as the primary inflation chip with the relative read beside it in dashed, smaller, subordinate styling; verified by invoking `render_command_center` directly for US/CN/LU/JP rather than assuming. One pre-existing test needed a fixture fix, not a code fix: `test_credit_tightness_widens_inflation_threshold_only` used a series so calm that both the loose and tight cases floored to 0.15, masking the credit multiplier — amplified the fixture and added `test_floor_masks_credit_multiplier_in_very_calm_regimes` to pin that interaction deliberately.

30 new tests (`tests/test_inflation_anchor.py`); suite **619 passed**, with the one pre-existing unrelated `test_explorer` count failure.

**Next:** Ray's remaining design-pass items — growth labour/output impulse-persistence split with a 2–3m rolling labour average, credit-conditional labour-vs-output tilt, and leading demand signals (needs a data-feed check). Then re-run the audit once September data ingests, to see whether the Growth label survives the labour stall.

**Superseded next-step note:** six punch-list items were open at audit time, nothing implemented — the two `needs design pass` items (inflation window frame; impulse-vs-inflation weighting) go to Digital Ray before any code changes, along with a `gz`-vs-CFNAI-±0.70 calibration comparison.

## 2026-08-16 (2) — Data Feed Monitor: two compounding bugs behind "89/90 OK but nothing shows OK"

**The report.** User: the top summary says "89/90 OK" for US, but almost every row shows a "release overdue" badge and none show "✓ OK" — asked for an audit.

**Bug A — the `+Nd overdue` badge used its own hardcoded, override-blind staleness math.** `dashboard/data_dashboard.py::_badges()` recomputed "overdue" from a flat `_NEXT_DAYS` table (D:2,W:10,M:45,Q:120,A:400 + 15d grace) instead of the real `is_stale` flag (which honors per-signal `stale_after_days` overrides from earlier audits this session). Empirically: **32/90 signals tripped "+Nd overdue"; only 1 was real** (31 false positives) — dominated by the Z.1/BEA quarterlies (`credit.household_debt`, `external.niip`, etc.) given a deliberate `stale_after_days: 260` override earlier this session because their true lag is ~250 days, while this table's generic 135-day quarterly buffer flagged them "+107d overdue" regardless.

**Bug B — informational metadata blocked the OK badge.** `_badges()` treated `vintage_available=false` / `is_proxy` / `is_constructed` as badge-worthy, so the "✓ OK" fallback only fired if *zero* badges of any kind applied. **79/90 US signals (88%) carried `vintage_available: false`**, including **63 plain FRED series** — so **88/90 rows carried some badge**, crowding out OK almost entirely, even though only 1 signal had an actual freshness problem.

**Fix — same principle as the Regime History badge fix earlier today: separate alarms from metadata.** `_badges()` now badges only `is_stale`/`low_history` as alarms (OK is the default otherwise); `PROXY`/`DERIVED`/`NO VINTAGE` render as non-blocking tags alongside OK. The `+Nd` detail is now computed from each signal's real threshold (`stale_after_days` override, else the same generic per-frequency default as `indicators/normalize.py::_STALE_THRESHOLDS`) and only ever shown as an annex inside the STALE badge — there is no longer a second, independent "overdue" trigger that can disagree with `is_stale`. New `tests/test_data_dashboard.py` (10 tests) locks in both the false-positive fix and the metadata/OK decoupling.

**`vintage_available` gap — investigated, confirmed as a real bug, fixed.** CLAUDE.md rule 8 says vintage_available should be true for US-via-FRED series, but only 2/98 US bindings had it set. Rather than flip categorically, ran an empirical ALFRED-availability check (`fetch_alfred_vintages()`, already built for Phase G3) against all 63 FRED-provider non-constructed bindings: **43 have genuine, retrievable ALFRED vintage history** (confirmed by successful non-empty fetch — 15 were already cached from G3, 28 fetched fresh this session) and **20 do not** (`HTTP 400` — all daily unrevised market/policy-rate series: Treasury yields, Fed funds, VIX, SP500, breakevens, credit spreads — ALFRED has no meaningful revision history for data that's published once and never restated). Flipped the 43 confirmed bindings to `vintage_available: true` in `config/us_bindings.yaml` (targeted text edit, comments/formatting preserved) and backfilled the same 43 signal IDs' existing DB rows (38,637 rows) via a direct `UPDATE` — equivalent to what a full pipeline re-run would produce for this metadata-only field, without an unnecessary live-API re-pull. The 20 daily market series correctly keep `vintage_available: false` — not a gap, a real data-availability limit.

Full suite **522 passed** (10 new). Rebuilt `charting` only.

## 2026-08-16 — Force Component status badges: STALE vs in-window carry, no longer conflated

**The report.** User asked why Growth Forces on Regime History showed everything "decayed," and whether that meant a signal was genuinely past its expected update window or just aging normally within one (e.g. a quarterly series a month or two after release). Asked for a way to make that distinction visible.

**Root cause.** The badge (`_status_cell()` in `dashboard/signals_page.py`, duplicated in the Regime History/Map info-card builder in `dashboard/charting.py`) fired its orange "DECAYED" label off `is_stale OR fill_months > 0` — i.e. off *any* carry-forward age at all, including a signal sitting at 100% weight, perfectly on schedule, inside its configured `release_grace_months` (`config/composites_policy.yaml`: M=1mo, Q=4mo, A=14mo grace before the composite engine's `decay_fraction` even starts falling). Growth Forces is dominated by quarterly/annual series, so nearly everything showed *some* fill age and got the same alarming badge as a signal genuinely months overdue. The `· time NN%` sub-text was the only thing distinguishing them, and it wasn't tied to the badge at all. The Debt Stress page already got this right (`lag_q` = excess beyond the expected gap, only badges "STALE" when truly overdue) — used as the reference pattern.

**Fix.** Collapsed to exactly two badges, both in `signals_page.py::_status_cell()` and its `charting.py` duplicate (LOW HISTORY / BLANK unchanged, they're unrelated states):
- **ACTIVE** (green) — fresh, or carried forward but still inside its expected release window.
- **STALE** (orange) — `is_stale` is true: genuinely past the per-signal cadence threshold (honors the `stale_after_days` overrides from the earlier US/non-US staleness passes).

Carry age is no longer badge-gated — whenever `fill_months > 0`, both badges now show `· time NN% (Nm)` in the detail text (the `(Nm)` is new), so a viewer can see *how much* carry contributed to any weight reduction regardless of whether it crossed into STALE. Row background tinting also dropped `fill_months > 0` from its alarm condition (only `is_stale`/`z_missing`/`low_history` redden a row now). Verified live: US `Tfp` (19m carry, 75% weight) and `Rnd Intensity` (32m carry, 35% weight) — the two signals from the original blanking bug — now correctly read `ACTIVE · time 75% (19m)` / `ACTIVE · CONFLICT · time 35% (32m)` instead of the old alarming `DECAYED` badge.

3 tests in `TestRegimeInfoStaleBadge` (`tests/test_charting.py`) rewritten for the new two-badge contract, incl. one that explicitly locks in "in-window carry ≠ STALE." Full suite **512 passed**. Rebuilt `charting` only (dashboard-only change, no `indicators/`/`config/`/`store/` touched — scheduler unaffected).

## 2026-08-15 — Command Center vs Regime Map "disagreement" — explained + fixed

**The report.** Command Center showed US Growth as "Transition"; the Regime Map dot sat clearly inside the Expansion quadrant, well past the threshold line — looked like the two pages disagreed.

**Root cause — not a data bug.** Both pages use the identical `_classify_regime()` call on the identical composite data (verified by reproducing the calculation directly: growth_score_48m = **+0.600**, dynamic gz threshold = **+0.200** → Z-condition passes). But the chip rule is dual-condition **Z beyond threshold AND momentum agreeing** (Field Guide: "Miss either → Transition, honesty not indecision") — and the MoM delta was **-0.000** (flat), failing the momentum leg. So "Transition" was the correct, honest chip. The Regime Map's dot position only encodes the Z-score half of that rule; it has no visual for momentum, so a Z-confirmed-but-momentum-flat month LOOKS like it should say "Growth" when read from the map alone — a real legibility gap, not a classification bug.

**Fix:** the Regime Map page now carries the same regime-info-box summary card Regime History uses (reused by component id, same `update_regime_info` callback — no duplicated logic) showing the chip, Force Z-Scores, and Δ MoM Momentum together, directly above the scatter. The map and the chip now tell the same story in the same glance: "Growth +0.600 (past threshold) · Momentum -0.000 (flat) → Transition." Caught a real bug while wiring this up: the reused card has two Outputs (`regime-info-box`, `regime-date-display`) and Dash refuses a multi-Output callback update if ANY target is missing from the current page — I'd only added one id to the Map page, so the card rendered silently empty. Fixed by adding the second id (kept the pre-existing `scatter-date-display` as a hidden-but-valid target so its own callback still resolves).

Also folds in the earlier same-day fix: Regime History's date display now prefixes the country name (`United States · Aug 2026 · current`) — a selector/store desync earlier in the session had rendered the EZ basket under a stale "US" impression with nothing on screen to reveal it; both the country-name label and a dropdown self-heal (syncs FROM the persisted store on load) ship together as the general fix for that class of confusion.

Verified in-browser (console clean bar the pre-existing unrelated `rh-threshold-open` warning); suite **512 passed**.

---

## 2026-08-02 (3) — Non-US staleness pass: 152 cadence-grounded overrides + EZ yield revival

**The pass** (follow-up to the relocation audit): applied the US-style `stale_after_days` treatment to all 13 other countries, grounded in each source's observed publication cadence (inter-obs gaps measured from the DB, not guessed).

**Overrides (152 across the country YAMLs):** BIS 3-sector credit 360d (FRED mirrors lag 2-3 quarters past the quarter-start stamp); OECD quarterly GDP mirrors 280d; monthly mirrors with 2-4mo lag (trade YoY 150d, IP 180d, retail 150d, unemployment 150d, FX reserves / CN interbank / IN+MX monthly yields 120d); slow structural annuals ≈1.5× their observed print gap (PWT TFP 1500d, WB R&D 1100d — AU/ID/IN 2200d for biennial/sparse reporters, gini 2200d, AU/IN govt revenue 1400d); EZ capacity survey 300d. Mid-pass correction: CN/ID/IN/MX unemployment are ANNUAL WB/ILO proxies (documented quirks) — blanket monthly rule mis-sized them, reset to 750d.

**Real breaks found (not papered over):**
- **`ez.policy.yield_10y` REBOUND** — the OECD FRED mirror (IRLTLT01EZM156N) died 2026-01 (die-off continues). Now the live **ECB Maastricht euro-area aggregate** (`IRS/M.I9.L.L40.CI.0000.EUR.N.Z`, monthly, 3.36% @ Jun-30) — also revives derived `real_yield_10y` + `yield_spread`.
- **Root-owned raw_cache collision**: 18 parquets written by container-root blocked host-side refresh (PermissionError killed the whole binding for BCB/ONS/eStat/BPS fetchers — BR unemployment + GB IP/unemployment stuck stale). Deleted the root-owned files (refetched clean) and added the FRED-style PermissionError guard to ALL 8 unguarded cache-write sites in loader.py.

**Dead mirrors documented in the wishlist (keep their honest stale badge until replaced):** AU/CA/CN/IN/KR/MX CPI mirrors (IMF bridges carry the read), GB+KR CPI core, `kr.growth.industrial_prod` (KOSIS/ECOS candidate), `ez.volatility.equity_index`+`realized_vol` (no free FRED replacement; EURO STOXX needs a non-FRED source), `jp.fiscal.govt_revenue_gdp` (WB ends 1993 — removal candidate).

**End state: 13/480 stale** (was ~120) — the remaining 13 = exactly the documented-dead set + `us.fed.foreign_holdings` (genuine Treasury Bulletin lag). All countries 0-3 stale. Both images rebuilt; scheduler nightly confirmed enabled (next 2026-08-03 03:00). Suite **512 passed**.

---

## 2026-08-02 (2) — Relocation audit: restored the feeds lost in the projects reorg

**The report.** After the all_weather → finance folder move (commit b1c0e98), "a number of data feeds" appeared lost. Full system audit:

**Found + fixed:**
1. **`.env` still pointed at the deleted all_weather paths** (DATA_DIR/DB_PATH/RAW_CACHE_DIR/SNAPSHOTS_DIR) — the relocate commit updated code defaults + compose, but `.env` is uncommitted. Containers were unaffected (compose `environment:` overrides win in-container) but every HOST-side pipeline run resolved to nonexistent dirs. → repointed to finance.
2. **Nightly auto-import silently disabled**: compose passes `AUTO_IMPORT_ENABLED: "${AUTO_IMPORT_ENABLED:-}"` → the container env var exists as `""` → `load_schedule` treated any set value as an operator override → parsed `""` as False → overrode schedule.json's `enabled: true`. → `schedule_config.py` now treats an EMPTY env value as not-configured (explicit 0/1 still override); regression test added. Scheduler now logs "auto-import enabled — daily at 03:00 (next 2026-08-03)".
3. **The Aug-2 18:44 ingest ran with pre-relocation OLD code** — stale flags contradicted the existing overrides (productivity/JOLTS/R&D flagged inside their windows). Fresh run with current code corrected all flags.
4. **11 more release-lag staleness overrides** (same period-start + publication-lag class as the Jul-18/31 fixes): 9 Z.1/BEA quarterlies (`gov_debt_gdp`, `corporate_debt(+_gdp)`, `household_debt(+_gdp)`, `debt_service_ratio`, `niip`, `current_account`, `govt_receipts_qtr`) at **260d** (Q1-start obs superseded ~254d later — generic 200d false-flagged them ~50 days/quarter), plus `fed.term_premium_10y` **14d** (ACM ~weekly) and `inflation.crude_oil` **10d** (EIA lag). 15 bindings now carry `stale_after_days`.
5. CLAUDE.md project-root line updated to finance.

**Verified intact (no data lost):** raw_cache (509 parquets, all readable), signals.duckdb (4.8G) + history.duckdb at the new locked paths, hypothesis_machine charter already on finance paths, zero all_weather references left in code/config.

**End state:** pipeline clean (US 90 OK / 0 errors; exit-1 = the documented EZ current-account only); **US stale 15 → 1** (`fed.foreign_holdings`, the genuinely ~2-quarter-lagged Treasury Bulletin series); vintage capture appending at the new path (69 rows today); both images rebuilt; scheduler nightly restored; suite **512 passed**. Non-US stale counts are the pre-existing per-country annual/quarterly-lag baseline (BIS/WB/IMF cadences) — a candidate for the same per-binding override sweep later, not a relocation casualty.

---

## 2026-08-01 — Fix: mass-blanked US growth/inflation signals (stale scheduler image + cache-TTL pinning)

**The report.** Seven US monthly signals (IP, retail, real PCE, capacity util, JOLTS, core PCE, PPI) plus productivity/TFP/R&D showed BLANK on the force pages; the US composite had swung to G −0.78 and flipped the chips (the Jul-31 "clock change" notes were partly this artifact).

**Two root causes:**
1. **The nightly `scheduler` container was running a 2-week-old image** — its baked pipeline code/config predated every fix since ~Jul 11, so each nightly run silently re-applied OLD staleness logic (re-breaking the Jul-18 tfp/rnd fix) and missed the estat/carry-cap/vintage passes entirely. → Rebuilt; standing rule added to memory: any `indicators/`/`config/`/`store/` change ⇒ rebuild **charting AND scheduler**.
2. **Cache TTLs pinned pre-release data**: M TTL was 25d; the many Jul-17/18 session runs stamped every cache just before the June releases (Jul 16–31), so nightly runs served May data from cache until the obs crossed the 90d staleness line on Jul 30 → mass stale → `exclude_unreliable` blanked them at once. → `_CACHE_TTL` now **D 20h / W 2d / M 3d / Q 7d / A 30d** (daily volumes are trivial vs provider rate limits; releases picked up within days).

**Also fixed (same period-start + release-lag class as the Jul-18 annual fix):** `growth.productivity` `stale_after_days: 240` (BLS publishes ~218d after the quarter-start stamp; generic Q=200d false-flagged it every early August) and `growth.job_openings` `stale_after_days: 100` (JOLTS publishes ~95d after the month-start stamp; generic M=90d false-flags it a few days every cycle).

**Recovery + verification:** force-refresh pulled all June prints (killed the WB-timeout-crawling force run after the US FRED pass — the WB annuals it was grinding through are unchanged; normal run completed the composite passes). Growth force now **11/12 active** (Retail +1.22, IP +0.87, PMI +2.85; composite G **+0.41** / I **+0.23** vs the −0.78 artifact); JOLTS legitimately awaits its ~Aug 4 June print and un-blanks tonight via the override. Both images rebuilt + containers restarted. Suite **511 passed**.

---

## 2026-07-31 — Relative Cycles: clock-change notes

**Done:** per user request, each country card on /relative now shows a small amber "clock changed" note when one of its three clocks flips — Growth chip, Inflation chip (30-day window), or debt-cycle Stage (45-day window — quarterly stages surface with a lag). Derived from history at render time (no stored state): classify the last 8 snapshots (per-row dynamic thresholds when enabled, so past rows are judged as the dashboard judged them), find the first snapshot carrying the current label, show "X clock → new (was old) · date" while that start is inside the window. Windows + lookback are TUNABLE constants in `relative_view.py`. Live on ship day: US (both short-term clocks → Transition, Jul 31), GB (stage → squeeze, Jun 30), BR (both → Transition). 4 new tests; suite **511 passed**.

---

## 2026-07-20 — Vintage store (Pass 9) + hypothesis_machine chartered

**Done:**
- **Three-project structure agreed with the user**: indicators_machine (perception) → **hypothesis_machine** (rules R&D — NEW sibling repo at `/mnt/data/projects/all_weather/hypothesis_machine/`, chartered H0) → CreovaOne (execution). Strategy hypothesis testing is explicitly OUT of this repo's scope (charter intact); this repo's role is data ownership.
- **Pass 9: vintage capture** (`indicators/vintage_store.py`) → `history.duckdb` (locked DB dir, beside signals.duckdb). Append-only point-in-time store of every RAW fetched series (all providers — scans raw_cache parquets, skips alfred_*): `raw_observations(series_key, obs_date, value, vintage_date)` + `latest_values` mirror for O(changes) dedupe. New/changed values stamped with the run's vintage date; unchanged runs append nothing; publication calendar = MIN(vintage_date) per obs. **Seeded: 494 series / 302,831 obs / 23 MB.** Downstream consumers open it READ-ONLY (single-writer preserved). 4 tests.
- ALFRED coverage verified for the future deep-US backfill (INDPRO vintages→1927, PAYEMS→1955, CPIAUCSL→1972, TCU→1996, CMDEBT→1999, BCNSDODNS→2010, MFPNFBS→2016).

**Next:** ALFRED full-vintage backfill script (this repo, feeds hypothesis_machine H5); hypothesis_machine H1 replay engine (its repo). Standing tails unchanged.

---

## 2026-07-18 — Fix: annual signals (TFP, R&D) showed BLANK despite current data

**The report.** After the audit swapped TFP to BLS (current through 2025), the productivity page still showed Tfp + Rnd Intensity as BLANK / eff-wt 0%. Data + z-scores were fine in the DB — three stacked display/engine caps were silently killing every annual signal for the back half of its natural cycle:

1. **Carry cap** `per_frequency_ffill_limit A: 15` — but annual obs are stamped at PERIOD START and the successor print only lands ~26mo later (12mo period + ~14mo release lag; WB-lagged series like R&D up to ~34mo). → **A: 36** (TUNABLE). The cap now only kills true zombies; grace + half-life decay do the honest down-weighting in between.
2. **Global zombie ceiling** `time_decay.hard_drop_months: 12` zeroed the decay fraction at >12mo — re-blanking what the carry cap allowed (TFP at 18mo → time 0%). → **36** (must sit above the largest per-frequency cap; D/M/Q still bind sooner).
3. **`exclude_unreliable` + is_stale**: the composite NaNs all months after a stale-flagged obs, and the generic A staleness window (600d ≈ 20mo) is shorter than these sources' real cadence → they were permanently stale-excluded. → new per-binding **`stale_after_days`** override on `CountryBinding` (normalize.py threads it): TFP **850d** (BLS successor ~26mo), R&D **1100d** (WB ~34mo).

**Result** (verified in-app + audit JSON): productivity force **3/3 ACTIVE** (was 1/3) — Productivity 76.9% eff wt, TFP 19.1% (time 79% — grace 14m + half-life 12m working as designed), R&D 2.1% (time 37%, Z +2.06). is_stale now False for both. Methodology §15 row added. Suite 503 passed (composites limit assertion updated).

---

## 2026-07-17 — US data-set audit: empty / very-old / overdue signals tracked down

**Audit of all 96 US bindings** (age vs frequency-aware release windows; every suspect verified at the provider via API).

**Fixed (5):**
- **`credit.household_debt_gdp`** — was BIS `HDTGPDUSQ163N`, stuck at 2025-Q1 (472d). BIS just repackages Z.1 with ~4-quarter extra lag (cross-checked identical: 67.90 vs 67.95 at 2025-Q1). Now **derived `CMDEBT ÷ GDP`** → current to 2026-Q1 (66.2%), history 1980→ (Z.1 goes to 1947 if GDP fetch extends). New base signal `credit.household_debt` (CMDEBT YoY) added alongside.
- **`credit.corporate_debt_gdp`** — was BIS `QUSNAM770A` (2025-Q4, 289d). Now **derived `BCNSDODNS ÷ GDP`** → 2026-Q1 (45.4%). ⚠ **Concept shift**: Z.1 securities+loans (~45% GDP) is narrower than BIS total credit (~75%, incl. cross-border/intercompany) — equilibrium reset 70→43 (new long-run mean), sanity 15–90, linkage documents the difference. Stage-classifier percentiles are self-relative so they adapt; next full pipeline run refreshes stage snapshots on the new inputs.
- **`growth.tfp`** — was Penn World Table `RTFPNAUSA632NRUG`, stuck at **2023** (PWT updates every ~3 years). Now **BLS `MFPNFBS`** (official TFP, private nonfarm) → current through **2025**. Old PWT rows cleared before re-ingest (no mixed-source history).
- **`fed.foreign_holdings`** — NOT broken: Treasury Bulletin source genuinely lags ~2 quarters (FDHBFIN end 2025-Q4, updated 2026-06). Kept, and added **`fed.custody_holdings` (`WMTSECL1`, weekly, live to Jul 15)** — Fed custody of Treasuries for foreign official accounts, the real-time "buyers stepping away" pulse; new card in Fed Monitor §5 next to Foreign share.
- **Weekly staleness threshold 12→18d** (`normalize.py`) — H.8 releases lag ~9 days, so fresh weekly series (TOTBKCR) false-flagged stale at 12d.

**Verified-correct, no action possible (documented):** WB annual batch at 2024 = WB's latest (563d, inside the 600d annual window; 2025 lands late 2026) — gini/demographics/trade/fiscal ratios + REER; `rnd_intensity` 2023 = WB's latest (R&D lags ~2yrs everywhere); IMF `primary_balance_gdp` 2024 = latest actual (forecast-exclusion working as designed); `FYFSD`/`FYOINT` FY2025 = latest fiscal year (next Oct 2026).

**Empty (8) — all known:** 5 WGI governance slots (WB killed the `.EST` API — deferred since 1A-ii), 1 climate manual slot (by design), **2 D4 manual slots (V-Dem + GPR): infra built, files never dropped** — operator runbook at docs/manual_data.md remains the standing to-do.

US signal count 88→**90**. Suite **503 passed, zero exclusions**.

**Bonus bug caught by the audit's full-pipeline run:** `indicators/loader.py` defined `_estat_cache_path`, `_fetch_estat_from_api`, AND `_ESTAT_BASE` **twice** — the JP e-Stat fetcher (Phase F) reused the Eurostat helper names, and Python's last-definition-wins silently pointed every Eurostat fetch at the Japanese API ("takes 1 positional argument" crashes / 404s to api.e-stat.go.jp). EZ/DE Eurostat signals had been living off stale parquet cache fallback since then. Renamed the JP trio to `_estat_jp_cache_path` / `_fetch_estat_jp_from_api` / `_ESTAT_JP_BASE`; swept loader.py for duplicate module-level names (none remain). EZ PPI immediately refreshed 2026-04→**2026-05**. Full pipeline now runs with ZERO fetch errors (exit 1 = the documented EZ current-account empty only).

**Next:** run the FULL pipeline (Passes 5-7) so composites/stage/debt-stress pick up the new debt-ratio inputs + longer histories; drop the D4 V-Dem/GPR files (operator); standing tails unchanged.

---

## 2026-07-15 (2) — Fix: regime walk features leaked a stale month between pages

**Done:**
- **Bug:** the Regime Map and Regime History share one `regime-step-index` store. On SPA navigation, `page-trigger` co-fires with a *phantom* step-button re-mount (the prev/next buttons re-mount with reset `n_clicks`), and that phantom "prev" won via `triggered_id` — so walking back on one page (or just navigating between them) leaked/incremented a stale month, and the pages opened on **June instead of the current reading**. Reproduced: History (Jul) → prev → Map showed Jun; Map → History incremented to May.
- **Fix** (`update_regime_step`): check the FULL `ctx.triggered` batch — if `page-trigger` is anywhere in it and the destination is `/regime-map` or `/regime-history`, snap to step 0 (most-current) and let that win over the phantom button. Uses `getattr(ctx, "triggered", …)` so the unit-test context mock (only `triggered_id`) still works. Walking within a page is unaffected (page-trigger doesn't fire on a button click). Verified in-browser: landing on either page now shows "Jul 2026 · current", and prev/next still walk correctly.
- New parametrized regression test (`test_landing_on_regime_page_snaps_to_current`); charting suite 88→89.
- Note (separate, not a bug): composites reached a mid-month 2026-07-10 snapshot while the quarterly stage/debt-stress tables sit at 2026-06-30 — so the Command Center stage card legitimately reads "Jun" (quarterly data lags). Getting everything fully current needs a **full** pipeline run (Pass 5/6/7); this session's quick `run_country` market.* ingest deliberately skipped those. The daily scheduler runs the full pipeline.

**Next:** commit/push this fix; standing tails (Wilshire-closer numerator; full-pipeline refresh so composites/stage advance together).

---

## 2026-07-15 — Market Expectations page (Ray consult: discount rate + inflation expectations)

**Done:**
- **Digital Ray consult** (logged in `ray_dalio_review_log.md`, Session 2026-07-15) on the market-implied formulas he uses routinely. Ray's core identity: **nominal yield = real (TIPS) yield + breakeven inflation** (i = r + E(π) + RP); breakeven = nominal − TIPS; E(π) ≈ breakeven − term premium; the real yield is his real-growth proxy. His routine gauges: 5y/10y breakevens, 1y expected inflation (Cleveland Fed), real yields, nominal yields, BEI-curve slope (10y−5y), real-growth proxy, policy-rate gap; plus a **Breakeven×Real-Yield 2×2** regime read. FRED-ID verification (house rule) caught that **DFII2 doesn't exist** (no 2y TIPS) — term-premium leg uses the ACM series we already ship.
- **7 new `market.*` FRED bindings** (isolated `market` force — page only, not composites/regime/stage/data-score): `DGS5 DGS10 DFII5 DFII10 T5YIE T10YIE EXPINF1YR`. Ingested via `run_country` (US, passes 1–4) — full history (nominal→1976, TIPS/breakevens→2003). US signal count 81→88.
- **New page** `dashboard/market_expectations.py` → `/market-expectations` ("📐 Market Expectations", Indicators nav, **not** operator-gated). Four sections: ① discount-rate decomposition (stacked real+breakeven bars = nominal, for 5y/10y) + 10y nominal history; ② inflation-expectations curve (1y/5y/10y) + 5y/10y breakeven histories with Ray's bands + BEI-curve slope; ③ real yields (DFII5/10) + 1y expected inflation, with restrictive/zero lines; ④ **Ray's 2×2** (3-month Δbreakeven vs Δreal-yield → regime label). Header chips (nominal/real/breakeven/slope + 2×2 read). Reuses fed_monitor card/section/chip/info-icon helpers. Live now: 10y 4.62% = 2.36 real + 2.25 breakeven; 2×2 = "disinflation with firmer real growth".
- Methodology §18 added; 4 new tests (`tests/test_market_expectations.py`) + explorer count 81→88. Suite green. Charting image rebuilt; verified in-app.

**Next:** could extend the real-growth proxy (GDP growth − BEI) and policy-rate gap as explicit cards; optional cross-country breakevens where TIPS-equivalents exist (mostly US-only on free data). Same standing tail: Wilshire-closer numerator research; commit of the recent standalone/valuations/UI/market work.

---

## 2026-07-14 (2) — Valuations palette match + collapsible sidebar groups

**Done:**
- **Valuations palette matches the site.** Reskinned the embedded Buffett app to the Economic Machine palette (Carbon charcoal `#1c1c1c` + amber accent `#E8A317`) — replaced its purple/navy `:root` and all hard-coded chart purples (`#7c6cff`, `rgba(124,108,255,…)`, `#a99bff`) with `var(--accent)`-driven JS colours (`ACC()`/`rgba()` helpers) + `color-mix` CSS tints. **Theme-following:** the app reads `?theme=carbon|slate|dawn` and applies matching CSS vars; `_page_valuations` iframe src is kept in sync with the site's `theme-store` via a clientside callback (`valuations-frame.src`). Verified: under `?theme=slate` the palette + chart line switch to gold `#F4C842`.
- **Sidebar sharpened — click-toggle collapsible groups.** Signals, Data, and Reference are now native `<details>` groups (helper `_group()` in `_left_nav`): click header to roll/unroll (no more hover-expand on Signals), **rolled up by default**, animated ▸→▾ chevron. Overviews + Indicators stay always-open. Icon-rail (collapsed sidebar) CSS force-shows every group's links + hides headers so pages stay reachable. Signals sub-list gained an "↳ All signals" link to `/signals`. Removed the old `.signals-subnav`/`.signals-nav-group` hover CSS; added `.nav-group*` rules to `theme.css`.
- Test assertion updated (iframe src now carries `?theme=`); suite still green (`test_charting` + `test_valuations` = 94). Charting image rebuilt; both changes verified in-app. Note: 14 pre-existing Dash `rh-threshold-open`/`regime-step-button` callback-timing warnings persist (unrelated).

**Next:** same as below — Wilshire-closer numerator research (deferred); optional commit of standalone/ + these UI changes.

---

## 2026-07-14 — Buffett Indicator valuation page (operator-only) + standalone build

**Done:**
- **Standalone Buffett Indicator dashboard** (`standalone/buffett_valuations_dashboard.html`) — a faithful, self-contained clone of a friend's Gemini-Canvas app (which was hard-coded, no feed), rebuilt on a **live** feed. Chart.js + gauge + mean-reversion projector + searchable/paginated history table + Macro FAQ + on-chart event markers/tooltip. Reverse-engineered the friend's `.tsx` (numerator = Wilshire 5000).
- **Two live numerators with a header toggle** (default VTI): **Wilshire proxy (VTI)** = VTI/CRSP US Total Market (Yahoo `query2` chart API, free) scaled to a $62.2T @ 2024-Q4 anchor → 231.5% today (matches the friend's Wilshire magnitude); **FRED Z.1** = `NCBEILQ027S` ÷ GDP → 218.1%. Producer: `standalone/fetch_buffett_data.py` writes `buffett_data.json` (both numerators). Stooq is now behind a JS PoW wall → used Yahoo for VTI. Anchor is a single documented, adjustable constant.
- **Integrated into the machine as an operator-only page** `/valuations` ("🫧 Valuations", Indicators nav). Reuses the exact operator-gating pattern: nav hidden in `PUBLIC_MODE`; `/valuations` added to `OPERATOR_ONLY_ROUTES` (route → operator notice); the two serving Flask routes (`/valuations/app`, `/valuations/buffett_data.json`) **404 in PUBLIC_MODE** — so it never appears on the public/cloud deploy. Page = `html.Iframe` embedding the self-contained app (no Dash-callback rewrite of its interactivity).
- **Data module** `indicators/valuations.py` (`compute_buffett_data`/`refresh_buffett_data`/`data_path`) + pipeline **Pass 8** (best-effort, never fails the run) refreshes `DATA_DIR/buffett_data.json`; dashboard falls back to the repo-bundled copy. Feeds no composite/regime/DB.
- 6 new tests (`tests/test_valuations.py`: routes serve for operator, 404 in public mode, gating, iframe page, bundled-fallback, feed shape); suite **488 passed, zero exclusions**. Charting image rebuilt; `/valuations` verified rendering in-app at VTI 231.5%.

**Next:** find a numerator closer to true Wilshire (VTI-scaling accuracy is anchor-dependent; options = total-market ETF anchored to a better print, or SIFMA/WFE dollar tables, or a paid FT-Wilshire/Nasdaq-Data-Link feed) — deferred by user until after current updates. Optional: commit standalone/ files to the repo (currently untracked → local Docker `COPY . .` picks them up, but they're absent from the git-based cloud build, which is fine since the page is gated off there).

---

## 2026-06-26 — Rolling Z fix, chart polish, signals subnav, repo made private

**Done:**
- **Rolling Z fix on force detail pages**: `load_signal_history` allowlist expanded to include all rolling Z columns (`zscore_36m/48m/60m/90m/120m`). Force detail callback now passes `g_zcol`/`i_zcol` to `load_multi_signal_history` so per-signal Z panels update when the lookback slider changes.
- **Composite Z chart styling**: `fill="tozeroy"` with per-force shading; line width 1.5; `y=0` dotted midline; amber dashed ±threshold hlines for growth/inflation pages — matches Regime History style.
- **Composite Momentum panel**: new Row 2 on growth/inflation/rate/credit force pages; amber `#E8A317` with fill, 50% dotted midline, % Y-axis. Volatility page skipped (no DB momentum column).
- **Signals subnav collapse**: sub-pages (Growth/Inflation/Rate/Credit/Volatility) now hidden by default and expand on hover or when any `/signals/*` page is active. Pure CSS: `max-height` transition on `.signals-subnav`, `:hover` + `:has(.active)` selectors. Signals NavLink changed to `active="partial"` so it stays highlighted on all sub-routes.
- **Repo made private**: `github.com/benito334/indicators-machine` set to PRIVATE via `gh repo edit`.

**Next:**
- Phase 3: Back-testing engine (FRED vintage replay — named scenarios: 1970s stagflation, 2008 GFC, 2020 COVID) + simulation engine (parameter sweep / sensitivity to weights, thresholds, lookback windows).

---

## 2026-06-26 — Force detail sub-pages + chart alignment fixes

**Done:**

- **Force detail sub-pages** (`dashboard/force_detail.py`, new ~290-line file): 5 pages at `/signals/{force}` (growth, inflation, rate, credit, volatility). Each page: banner strip (Force Z · Momentum · Active · In Agreement · Threshold · Lookback), collapsible 8-column signal table (same as `/signals` main page), stacked time-series chart (composite Z row 1, then raw-value + Z-score dual panels per signal). Shared hover spike via clientside JS mirrors Regime History tab. VIX page uses daily raw data (no composite row); composite forces use monthly-resampled data.
- **`load_signal_units()`** added to `dashboard/charting_data.py`: queries `signals` table for `units` per signal_id list; used by force detail chart builder.
- **`_comp_arrow()`** promoted to module-level in `dashboard/signals_page.py` (was a closure inside `render_signals()`); signature `_comp_arrow(comp_df, force)` — importable by `force_detail.py`.
- **Sidebar sub-nav**: 5 `.sidebar-subnav` links under Signals in `charting.py`; `.sidebar-subnav` CSS class in `theme.css` (0.78rem, 0.80 opacity, full opacity on hover/active).
- **Bug fixes (this session):**
  - *Z-score column mismatch*: `_build_force_chart()` was hardcoding base `growth_score`/`inflation_score` regardless of rolling-window store. Now `_render()` computes `chart_score_col` (e.g., `growth_score_36m`) matching the banner, and passes it explicitly.
  - *Date misalignment*: Composites store month-end dates (`2026-05-31`); signals store native observation dates (`2026-05-01` for monthly FRED, weekly dates for bank loans, etc.). Both are now normalized to first-of-month before plotting — composite via `dt.to_period("M").dt.to_timestamp()`, signals via index resample + `.groupby().last()`. VIX (no composite row) skips resampling and keeps daily granularity.
  - *Regime History divergence*: Same root cause as Z-score mismatch — force detail always plotted full-history `growth_score` while Regime History used the window-adjusted variant. Fixed by the same `chart_score_col` parameter.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- Run `python3 -m indicators.pipeline` after BEA Q1 2026 data release to clear 3 stale US signals.
- KR monthly CPI: BoK ECOS API registration needed.

---

## 2026-06-26 — Rate/Credit composites + per-signal age-decay half-lives

**Done:**

- **Rate/Credit composites engine** (`indicators/composites.py`, `indicators/models.py`, `store/store.py`): Extended `_score_force()` path (importance × momentum tilt × age decay) to all four forces. Added `rate_score`, `credit_score`, `rate_momentum`, `credit_momentum` DB columns and `CompositeSnapshot` fields. `weight_audit` JSON now includes `"rate"` and `"credit"` keys alongside growth/inflation.
- **Signals page rate/credit display** (`dashboard/signals_page.py`): Rate and Credit sections now use `_composite_rows()` (full 8-column table with importance, config wt, eff wt, Z-bar, momentum) instead of `_signal_rows()`. Fixed two generic bugs in `_composite_rows()`: `positive_dir` was hardcoded for growth (`invert` check now force-agnostic); momentum color flip only applies to `inflation` force now (not every non-growth force).
- **`charting_data.py`**: `load_composite_component_status()` extended to iterate `rate_score` and `credit_score` config sections; `_zscore_col_for` mapping covers `rate` and `credit`.
- **US Interest Rate basket redesign** (`config/countries/us_composites.yaml`): Replaced 9-signal basket (mixed policy + premium + balance-sheet) with 6 pure policy-rate / term-structure signals: `fed_funds_target` (PRIMARY 0.95), `real_yield_10y` (PRIMARY 0.90), `fed_funds` (PRIMARY 0.88), `real_fed_funds` (STRONG 0.75), `yield_2y` (STRONG 0.70), `yield_10y` (CONTEXT 0.45).
- **US Credit basket rebuilt** (`config/countries/us_composites.yaml`): Expanded from 5 to 7 signals — added `corporate_debt` (STRONG 0.65, Corporate Debt Outstanding Growth YoY%) and new `corporate_debt_gdp` (CONTEXT 0.40, BIS/FRED quarterly stock measure). Full basket: bank_loans → lending_standards → corporate_debt → debt_service_ratio → household_debt_gdp → corporate_debt_gdp → gov_debt_gdp.
- **New binding** (`config/us_bindings.yaml`): `credit.corporate_debt_gdp` → FRED `QUSNAM770A` ("Total Credit to Non-Financial Corporations as % of GDP", BIS quarterly). Equilibrium 70.0, sanity 30–130. Signal live (72.2% GDP at Oct 2025).
- **EZ/KR composites** (`config/countries/ez_composites.yaml`, `kr_composites.yaml`): Added `rate_score` and `credit_score` sections (EZ: 5+4 signals; KR: 1+1 minimal stubs pending data rollout).
- **Per-signal age-decay half-lives** — Interest Rate basket: `fed_funds_target`/`fed_funds`/`real_fed_funds` = 3m (short-end, discrete FOMC jumps); `yield_2y` = 4m (forward-pricing); `real_yield_10y`/`yield_10y` = 6m (long-end, structurally slow). Credit basket: `bank_loans` = 3m; `lending_standards`/`corporate_debt` = 4m (fast-moving quarterly flow); `debt_service_ratio` = 6m (stock-ish, quarterly); `household_debt_gdp`/`corporate_debt_gdp` = 9m (slow structural); `gov_debt_gdp` = 12m (annual). Engine reads `half_life_months` per-signal from composites YAML; falls back to global 3m; stored in `weight_audit` JSON.
- **Methodology Section 6** (`dashboard/methodology.py`): "Observation-age decay" subsection now has a 5-row half-life tier table (3m → 4m → 6m → 9m → 12m) with signal-type descriptions and rationale; carry-cap vs half-life distinction clarified.
- **Methodology Section 7**: Both basket tables extended with "Half-life" column. Interest Rate table row order changed to group short-end (3m) then long-end (6m). Credit table shows all 7 signals.
- **Methodology Section 8**: Rewritten to cover three distinct momentum roles — (1) weight tilt in pipeline, (2) dual-condition chip classification in dashboard, (3) stored quadrant (sign-only).
- **65 US signals** (was 64); **558 US composite snapshots** recomputed with updated baskets and half-lives. 354 tests still pass.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- Run `python3 -m indicators.pipeline` after BEA Q1 2026 data release to clear 3 stale US signals.
- KR monthly CPI: BoK ECOS API registration needed.

---

## 2026-06-25 — Regime UI polish + methodology audit

**Done:**
- **Slider styling fixes** (`dashboard/assets/theme.css`): tooltip boxes below sliders hidden (`dash-slider-tooltip { display: none }`); slider track/range/thumb styled with `--slider-accent` amber; value-display input box (`.dash-input-container`) given dark background (`var(--card-bg)`) with amber text and monospace font; mark labels forced amber via `.modal-body .dash-slider-mark`.
- **Modal dark-theme overrides**: `.modal-content`, `.modal-header`, `.modal-footer` wired to `--card-bg`/`--border-color`; all modal slider parts inherit the sidebar slider palette.
- **Auto-open bug fix** (`_toggle_threshold_modal` callback): Dash 4.x resolves `ctx.triggered_id` to the first Input even at n_clicks=0; fixed with `if ctx.triggered_id == "rh-threshold-open" and (n_open or 0) > 0` guard.
- **Header threshold display**: `html.Div(id="rh-threshold-display")` added to Regime History header; `_update_threshold_display` callback renders live G·Z / I·Z / G·Δ / I·Δ chips in amber monospace inline with Prev/Now/Next buttons.
- **Regime chart wired to threshold store**: `update_regime_chart` now takes `Input("regime-threshold-store", "data")`; Row 1 redesigned to dual-band scatter (Growth band at y=0.25, Inflation band at y=0.75); ±gz hlines added to Row 2 (Growth Z); ±iz hlines added to Row 4 (Inflation Z).
- **"Regime Thresholds" button**: replaced ⚙ gear icon with `dbc.Button("Regime Thresholds", color="warning")` for visibility.
- **Methodology page Section 1 updated**: description changed from "four macro seasons" to "two independent regime dimensions"; "Quadrant" concept row replaced with separate "Growth Regime" and "Inflation Regime" rows.
- **Methodology page Section 8 rewritten**: old 4-season quadrant table replaced with dual-condition classification table (Growth/Transition/Retraction + Inflation/Transition/Disinflation), threshold explanation, configurable defaults, and localStorage persistence note.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).

---

## 2026-06-25 — Configurable regime classification system

**Done:**
- **New two-label regime classification** (`dashboard/charting.py`): replaced single "Inflationary Boom / Stagflation / Expansion / Disinflationary Slowdown" badge with two independent chips — Growth chip (Growth · Transition · Retraction) and Inflation chip (Inflation · Transition · Disinflation).
- **`_classify_regime(g_score, i_score, g_delta, i_delta, thresholds)`** function: dual condition — Z threshold (±gz/±iz) AND MoM delta threshold (gm/im) must both be satisfied to enter a named regime; otherwise lands in Transition.
- **`regime-threshold-store`** (localStorage): default `{gz:0.5, iz:0.5, gm:0.0, im:0.0}`.
- **`_THRESHOLD_MODAL`**: ⚙ button in Regime History header opens modal with four sliders (Growth Z, Inflation Z, Growth Mom, Inflation Mom); "Apply" persists to store, "Reset Defaults" reverts; sliders populate from store on open.
- **Threshold-aware `_sem_z_color`** in `charting.py` and `_semantic_z_color` in `signals_page.py`: neutral zone = ±thresh (configurable); colour magnitude scales above it (floored at 35% intensity so never invisible).
- **Scatter chart threshold lines**: four dashed lines at ±gz (vertical) and ±iz (horizontal) update live with store.
- **`update_regime_info` callback** now accepts `regime-threshold-store` as Input; `_regime_info_children` passes `thresholds` through to classify and color.
- **Signals page** (`render_signals`) receives `regime-threshold-store`; passes `thresh` to `_composite_rows` → `_semantic_z_color`.
- **354/354 tests pass.** Container rebuilt and serving HTTP 200.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).

---

## 2026-06-25 — Composites stale-exclusion fix + signal QAQC

**Done:**
- **Fix: `_load_wide(exclude_unreliable=True)` now preserves the observation month for stale signals** (`indicators/composites.py`). Previously, a daily signal marked `is_stale=True` (e.g., crude oil last obs June 15) had its Z-score zeroed from the END of the observation month (June 30) onward — wiping it from the June composite. Fix: `stale_from = (period + 1).to_timestamp("M")`. A June 15 observation is now available at the June composite; zeroing starts from July onward.
- **Pipeline re-run** — fetched fresh crude oil data (June 22, `is_stale=False`); crude oil now contributing to June inflation composite (`eff_wt=0.0097`, `missing=False`).
- **US quadrant updated to Inflationary Boom** (growth=+0.015, inflation=+0.434). Was misclassified as Stagflation while crude oil was excluded.
- **Signal QAQC**: `us.credit.bank_loans` / `ez.policy.central_bank_assets` (weekly, ~15d) — display-only stale, not in composites. EZ yields (ECB IRS lag, 145-175d) — no free-API fix. KR CPI/IP — correctly excluded. All genuinely stale signals confirmed not affecting composite calculations.
- **US signal count corrected to 64** in tests (`test_load_signal_overview_returns_all_signals`, `test_explorer_signal_table_callback`).
- **354/354 tests pass.**

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).

---

## 2026-06-25 — Signal drill-down, info popup, color palette, composite momentum

**Done:**
- **Debt stress 5→7 components**: added FRED-derived `primary_balance_gdp` (FYFSD+FYOINT) and `govt_revenue_gdp` (FGRECPT quarterly) replacements; `us.fiscal.govt_receipts_qtr` binding in `us_bindings.yaml`; `longterm_stress.yaml` updated; both built by new `_build_primary_balance_gdp_fred()` + `_build_govt_receipts_gdp_fred()` in `longterm_stress.py`.
- **Signal drill-down modal**: pattern-matching `{"type": "signal-link"}` Dash callback; `_signal_link()` in `shared_components.py` wired into all tables (lens tables, Force Component Inputs, Debt Stress table, Signals page). Click → dual-panel chart (value + Z-score) with shared spike hover line.
- **3rd panel raw data**: `_load_signal_binding()` + `_load_raw_cache_series()` in `charting.py`; for FRED `yoy_pct` signals a 3rd subplot shows the raw level from parquet cache before YoY transformation.
- **Shared vertical hover spike across all drill panels**: clientside JS callback mirrors regime history page — draws SVG `<line>` spanning all subplot y-extents on `plotly_hover`; `hovermode="x"` + `showspikes=True` on all traces.
- **Signal info popup (ⓘ icon)**: `_signal_info_icon()` in `shared_components.py` added to all Signals page rows. Pattern-matching `{"type": "info-icon"}` callback opens `signal-info-modal` with signal description, transformed units, raw FRED units (when different), frequency, provider, series ID, last updated.
- **FRED metadata sidecar**: `get_fred_meta(series_id)` in `loader.py` reads/writes `fred_{id}_meta.json` (365-day TTL cache). 76 sidecars backfilled on first access.
- **Dark-theme color palette**: `_lerp_rgb()` + opaque anchors in `shared_components.py`. Replaces `rgba(color, low_alpha)` (invisible on dark bg) with lerp from light washed-out pastel (soft sage/salmon) → vivid saturated (emerald/red-orange). Applied to `_semantic_z_color`, `_momentum_score_color`, `_stress_z_color`, `_sem_z_color`.
- **Signals page composite momentum**: `growth_momentum` + `inflation_momentum` from composites table shown in section headers as `Mom XX%`, color-coded. Rate/Credit/Vol momentum computed on the fly as direction fraction.
- **`ALL`, `PreventUpdate`, `ctx` import fix**: added to top-level Dash import in `charting.py`; removed 3 redundant local `from dash import ctx` lines.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- Run `python3 -m indicators.pipeline` after 2026-06-26 (BEA Q1 2026 data clears 3 stale US signals).

---

## 2026-06-24 — Regime History step reset on navigation

**Done:**
- **Fix: Regime History now defaults to current date on every visit** — added `Input("page-trigger", "data")` to `update_regime_step` callback in `dashboard/charting.py`; when the triggered input is `page-trigger` and the page is `/regime-history`, the step is reset to 0 (most recent composite). Previously, the in-memory `regime-step-index` store retained whatever step the user last navigated to, so returning to the page could show data from a prior month.
- **Investigation: Growth momentum score discrepancy between Regime History and Signals tabs** — confirmed by design: Regime History summary strip shows three distinct momentum metrics (composite Z, MoM Δ, Momentum Z over 12mo) while Signals page section header shows a simple majority-vote direction arrow; the composite Z values (`growth_score`) are the same at step=0 but differ at any non-zero step since Regime History is date-sensitive and Signals always shows latest.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- Run `python3 -m indicators.pipeline` after 2026-06-26 (BEA Q1 2026 release clears 3 stale US signals).

---

## 2026-06-24 — Methodology page audit + per-signal Z-bar window fix

**Done:**
- **Fix: per-signal Z-bars now update with slider changes** — `load_composite_component_status()` gained `g_zscore_col`/`i_zscore_col` params; fetches the appropriate rolling column (e.g. `zscore_36m`) from the signals table and substitutes it into the returned `zscore` field. Both `update_regime_info` (Force Component Inputs table in Regime History) and `render_signals` (/signals page) pass the active col names derived from their window stores.
- **Methodology page audit** (`dashboard/methodology.py`) — updated five sections:
  - **Section 2** (Data Sources): Added Eurostat JSON stats API + ECB SDW SDMX-JSON rows; noted EA20/EA21 geo codes, IRS SDMX format, BOP 400 limitation.
  - **Section 4** (Force Z-Score): Documented independent Growth/Inflation windows (Growth Full/36/48/60m; Inflation Full/60/90/120m); added table of pre-computed DB columns per force; noted per-signal Z-bar live update behaviour.
  - **Section 6** (Dynamic Force Weighting): Replaced stale `config/composites.yaml` reference with `composites_policy.yaml` + `countries/{cc}_composites.yaml` split.
  - **Section 11** (Country Coverage): Replaced "US only (Phase 1)" with current live status (US 63 signals, EZ 34, KR 22); added country table with data sources and known gaps; documented file architecture and EZ current account gap.
  - **Section 13** (Deferred Items): Fixed visible table OLS calibration row from "Deferred" to "✅ Live".
- **353/353 tests pass.** Docker rebuilt; HTTP 200.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- Run `python3 -m indicators.pipeline` after 2026-06-26 (BEA Q1 2026 release clears 3 stale US signals).

---

## 2026-06-24 — Inflation Z-Score window separation + Signals page reformatting

**Done:**
- **Separate Growth / Inflation Z-score lookback windows** — Growth keeps Full/36m/48m/60m slider; Inflation gets a new independent slider: Full / 60m / 90m / 120m.
  - New `inflation-window-store` (`dcc.Store`, `storage_type="local"`) + sidebar "Inflation Z-Score Window" slider (`id=inflation-window-slider`) + Settings modal mirror.
  - New `_INFLATION_WINDOW_COL = {60:"60m", 90:"90m", 120:"120m"}` constant in `charting.py`.
  - Three sync callbacks wire sidebar ↔ modal ↔ store for inflation window (matches pattern used for growth window).
  - `update_regime_info`: added `Input("inflation-window-store")`, now resolves `g_sfx` and `i_sfx` independently; `rolling` dict carries separate `window` + `inflation_window` keys.
  - `update_regime_chart`: same input added; subplot title labels encode `G:Xmo / I:Ymo` for independent windows; quadrant re-derives from combined rolling g/i cols.
  - `update_scatter_chart`: same; axis titles show independent window suffixes.
  - `render_signals` (signals page): added `Input("zscore-window-store")` + `Input("inflation-window-store")`; resolves Growth/Inflation Z independently from rolling cols.
- **New DB columns** — `zscore_90m`, `zscore_120m` in signals table; `inflation_score_90m`, `inflation_score_120m` in composites table.
  - `indicators/models.py`: `zscore_90m`, `zscore_120m` Optional fields.
  - `indicators/normalize.py`: `_ROLLING_MONTHS = [12,18,24,36,48,60,90,120]` — computes new columns.
  - `store/store.py`: DDL + migration + `update_inflation_rolling()` function.
  - `dashboard/charting_data.py`: SELECT includes `inflation_score_90m`, `inflation_score_120m`.
  - `indicators/pipeline.py`: Passes 5e-5f write 90m/120m inflation composites (558 US rows).
- **Signals page reformatted** to Regime History "Force Component Inputs" table style (8 columns: Signal / Importance / Config Wt / Eff Wt / Last Data / Z-bar / Momentum / Status).
- **353/353 tests pass.** Docker rebuilt; HTTP 200 at `:8502`.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA refresh after 2026-06-26 (`python3 -m indicators.pipeline`) clears 3 stale US signals.

---

## 2026-06-24 — Signals page (/signals) — 5-force signal breakdown

**Done:**
- **New page** `dashboard/signals_page.py` at `/signals` (nav: Indicators → 📡 Signals).
  - Five collapsible sections: Growth · Inflation · Interest Rate · Credit · Volatility.
  - Each section header shows force name, composite Z-score, and majority-direction momentum arrow.
  - Growth/Inflation Z pulled from `composites` table; Rate/Credit/Volatility computed as unweighted mean of constituent signal Z-scores.
  - Section body: same Indicator/Value/Dir/Pct/Z/Quality table as Regime Map lens drill-downs.
  - Rate section: `force='policy'`, excludes balance-sheet/monetary-base signals (US) and wrongly-mapped fed_funds_target (EZ).
  - Credit section: `force IN ('credit','premium')` — covers spreads, debt ratios, lending standards, yield curves.
  - Volatility section: VIX (US only, 120-month rolling Z), loaded from raw cache; empty for EZ/KR.
- **New shared module** `dashboard/shared_components.py` — extracted force-table helpers (`build_force_table`, `_DIR_ARROW`, `_concept_label`, `_zscore_color`, `_fmt_value`) for reuse.
- `charting.py`: added import, nav entry under Indicators group, `_page_signals()`, `/signals` in `_PAGE_MAP`.
- **353/353 tests pass.** Docker rebuilt at `:8502`; `/signals` returns HTTP 200.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA refresh after 2026-06-26 (`python3 -m indicators.pipeline`) clears 3 stale US signals.

---

## 2026-06-23 — Weight Audit page (/weight-audit)

**Done:**
- **New Dash page** `dashboard/weight_audit.py` at `/weight-audit` (nav: Reference → 🔍 Weight Audit). Three panels:
  - **Force Balance**: clustered bar chart of G_mass vs I_mass for all countries (US/EZ/KR); ratio badge green (0.75–1.33) or red.
  - **Signal Correlations**: per-country Pearson r heatmaps for growth and inflation baskets separately; |r| ≥ 0.80 cells outlined in orange; flagged pairs table (|r| ≥ 0.70, same-basket "redundant" pairs in red).
  - **Monte Carlo**: 500-trial ±15% importance perturbation → scatter of (growth_score, inflation_score) outcomes + donut of regime distribution + caption showing % of trials confirming current reading.
- **New `composites.py` functions** (country-agnostic):
  - `compute_force_balance(config)` → `(g_mass, i_mass, ratio)`
  - `compute_signal_correlation_matrix(conn, country, config)` → `(corr_df, growth_ids, inflation_ids)`
  - `monte_carlo_regime_sensitivity(conn, country, config, n_trials, sigma)` → dict
- **353/353 tests pass.** Docker rebuilt and live.
- Committed `3a071c1` and pushed.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA refresh after 2026-06-26 (`python3 -m indicators.pipeline`) clears 3 stale US signals.
- Phase 3B `indicators/calibrate.py`: country-agnostic weight calibration via supervised regime scoring.

---

## 2026-06-23 — Signal weight calibration: tier system, force-balance audit, correlation audit

**Done:**
- **Weight tier system** (PRIMARY / STRONG / CONTEXT / VOLATILE) documented and applied across all three country composites (`us_composites.yaml`, `ez_composites.yaml`, `kr_composites.yaml`) as a country-agnostic template. Matches guidance in `docs/Guidance/signal_weight_guidance.md`.
- **Anti-redundancy rule** applied: secondary signal's importance reduced to ≤40% of primary when `[CORR AUDIT]` surfaces |r| > 0.80 same-basket pairs: US cpi_core 0.95→0.65 (vs pce_core), breakeven_10y 0.25→0.20 (vs 5y); EZ cpi_headline base_share 1.0→0.7 importance 0.65→0.45, hicp_energy importance 0.25→0.20; KR cpi_headline 0.60→0.45.
- **`_log_force_balance()`** private function added to `composites.py`: logs `[BALANCE]` INFO/WARNING per country per Pass 5 run. All three now within 0.75–1.33 (US: 1.32, EZ: 0.83, KR: 0.82). Previously US=1.52, EZ=0.63, KR=0.64.
- **`audit_signal_correlations()`** public function added to `composites.py`: queries Z-score history, builds correlation matrix, logs `[CORR AUDIT] WARN` for same-basket pairs above threshold. Called in pipeline after every country's composite upsert.
- **4 test assertions updated** to reflect calibrated values (`test_breakeven_guidance_defaults`, `test_growth_importance_guidance_defaults`, `test_inflation_importance_guidance_defaults`, `test_guidance_nominal_weights_are_normalized_after_quality`). **353/353 tests pass.**
- Committed and pushed: `b095880`.

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA refresh after 2026-06-26 (`python3 -m indicators.pipeline`) clears 3 stale US signals.
- Phase 3B `indicators/calibrate.py`: country-agnostic weight calibration via supervised regime scoring (see guidance doc Sections 5–9).

---

## 2026-06-23 — EZ signal expansion (cont.) — ECB fetcher, GDP, Debt/GDP, CA investigation

**Done:**
- **Data Explorer country-awareness** (`dashboard/explorer.py`): all 6 callbacks now accept `country-store` as `Input` or `State`. Signal table resets `selected_rows` on country switch. `load_signal_overview(country)` and `load_composite_zscore_matrix(country)` called with selected country throughout.
- **ECB SDW fetcher** (`indicators/loader.py` + `indicators/pipeline.py`): `fetch_ecb_series(flow, key)` added — SDMX-JSON 1.0, parquet cache, TTL-based refresh, same retry/error pattern as Eurostat. Pass 1.6 (ECB) added to `run_country()`: parses `series_id` as `"FLOW/KEY"`, e.g. `"IRS/M.DE.L.L40.CI.0000.EUR.N.Z"`.
- **7 new EZ bindings** (`config/countries/ez_bindings.yaml`):
  - `growth.employment_growth` — Eurostat `namq_10_pe` (EA20, SCA, EMP_DC, PCH_SM_PER, Q). `raw_scale: 100`.
  - `growth.construction_prod` — Eurostat `sts_copr_m` (EA20, F, s_adj=CA, PCH_SM, M). `raw_scale: 100`. Key finding: `SCA` returns empty; `CA` works.
  - `growth.capacity_util` — Eurostat `ei_bsin_q_r2` (EA20, BS-ICU-PC, SA, Q). Level in %, no raw_scale.
  - `fiscal.budget_balance_gdp` — Eurostat `gov_10q_ggnfa` (EA20, B9, S13, PC_GDP, Q). Annual `gov_10dd_edpt1` is EDP-procedure data only; quarterly net lending via `gov_10q_ggnfa`.
  - `credit.yield_de_10y` / `credit.yield_it_10y` — ECB SDW IRS flow (M). Correct flow for Maastricht-criterion 10Y yields; BOP flow returns 400.
  - `credit.btp_bund_spread` — derived (IT − DE); 317 monthly obs, latest May 2026 = 79.4 bps.
- **EZ HICP energy/food sources corrected**: `prc_hicp_manr` publishes Mean Annual Rate and stops at Dec of prior year — switched to FRED index series with `yoy_pct` transform: `CP0450EZ19M086NEST` (electricity/gas) and `CP0100EZ19M086NEST` (food). Both through May 2026.
- **EZ composites re-run**: growth 3→6 signals, inflation 4→6 signals. `ez_composites.yaml` updated. Latest (May 2026): Inflationary Boom, Growth=+0.242, Inflation=+0.666, Confidence=58%.
- **Regime History / Global Overview signal counts fixed**: `n_growth_signals` and `n_inflation_signals` now reflect live signal count from composites engine, not hardcoded values.
- **`ez.master.gdp_level_bn`** — WB `NY.GDP.MKTP.CD` (EMU, annual). `raw_scale: 1e9` converts USD → billions. 35 obs; 2024 = 16,485B USD. Global Overview "GDP" column now populated for EZ.
- **`ez.credit.gov_debt_gdp`** — Eurostat `gov_10dd_edpt1` (EA20, GD, S13, PC_GDP, annual). 27 obs; 2025 = 87.8% GDP. Global Overview "Debt/GDP" now populated for EZ.
- **EA current account — exhaustive investigation, no free source found**: WB EMU (`BN.CAB.XOKA.GD.ZS`) all null; ECB BOP/BP6/BPS/ECB_BOP1/BOP_BNT all HTTP 400 or 404; FRED series don't exist or cut off 2012; Eurostat `bop_c6_q` always 413 (dataset too large even with all dims specified); IMF Datamapper empty for all EA codes. Fully documented in `docs/Guidance/EU_singals_guidance.md` — slot stays in bindings, returns empty, Global Overview shows dash.
- **EZ now 34 signals live** (was 19). **353 tests pass.**

**Next:**
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA refresh after 2026-06-26 (`python3 -m indicators.pipeline`) clears 3 stale US signals.
- EZ current_account_gdp: only option left is a paid ECB Data License or manual Eurostat bulk download. Accept gap for now.

---

## 2026-06-23 — EZ signal expansion + country-aware Data Dashboard

**Done:**
- Added 4 new Eurostat bindings to `config/countries/ez_bindings.yaml`: `inflation.ppi` (PPI), `inflation.wages_lci` (LCI wages, quarterly), `inflation.hicp_energy`, `inflation.hicp_food`. Also 2 derived: `policy.real_yield_10y`, `policy.yield_spread`.
- Added derived dispatch cases for `policy.real_yield_10y` and `policy.yield_spread` in `indicators/pipeline.py`.
- Expanded `config/countries/ez_composites.yaml` inflation_score from 2 → 6 signals (cpi_core + cpi_headline + wages_lci + ppi + hicp_energy + hicp_food).
- Added EZ signal display labels to `_COMPOSITE_SIGNAL_LABELS` in `dashboard/charting_data.py` (ppi, wages_lci, hicp_energy, hicp_food) — fixes force component table for EZ.
- Added EZ + KR signal names to `_SIGNAL_NAMES` in `dashboard/data_dashboard.py`.
- Made Data Dashboard fully country-aware: `_load_binding_meta(country)` and `_load_signals(country)` parameterized; layout uses static force/freq options; callback reads `country-store` and passes it through; sort resets on country switch; description shows country name + signal count.
- `country-store` in `charting.py` changed to `storage_type="local"` — country selection persists over browser refresh.
- **353 tests pass** (4 new from EZ signal additions earlier in session).

**Next:**
- Run pipeline to ingest new EZ signals into DuckDB (`python3 -m indicators.pipeline` for EZ).
- Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`).
- BEA data refresh (after 2026-06-26) will clear 3 stale US signals.

---

## 2026-06-22 — Per-country composites config split

**Done:**
- Split monolithic `config/composites.yaml` into:
  - `config/composites_policy.yaml` — global methodology (dynamic_weighting, time_decay, per_frequency_ffill_limit, regime_confidence, disequilibrium_score, what_changed)
  - `config/countries/us_composites.yaml` — US indicator lists (9 growth + 8 inflation)
  - `config/countries/ez_composites.yaml` — EZ indicator lists (3 growth + 2 inflation)
  - `config/countries/kr_composites.yaml` — KR indicator lists (3 growth + 3 inflation incl. IMF bridge)
- Refactored `indicators/composites.py`: `load_composites_config(country="US")` merges policy + country file; `_load_country_composites()` errors loudly if `{cc}_composites.yaml` is missing
- Updated `indicators/pipeline.py`: US pass loads `load_composites_config("US")`; country loop tries `load_composites_config(country_code.upper())` and skips with warning if no file found
- Updated `dashboard/charting_data.py`, `dashboard/charting.py`, `dashboard/explorer_data.py`: all replaced direct `composites.yaml` reads with `load_composites_config(country)`
- `cpi_imf_annual` removed from US composites (it's a KR-only bridge); test updated 18→17 for `test_returns_17_columns`
- `config/composites.yaml` marked DEPRECATED; no code reads it anymore
- **349 tests pass**

**Next:**
- Phase 2 — Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`)
- EZ current_account_gdp: investigate ECB SDW
- BEA data refresh (after 2026-06-26)

---

## 2026-06-22 — Eurostat fetcher + data gap resolution (EZ growth signals, KR CPI bridge)

**Done:**
- **Eurostat JSON stats API fetcher** (`fetch_eurostat_series()`) added to `loader.py`. Fixed `geo=EA` → correct codes (`EA21` for unemployment, `EA20` for industrial prod/retail sales). Fixed `s_adj` filter: `CA` (calendar-adjusted) is the correct value for PCH_SM industrial production — `SCA` returns 0 values for EA20.
- **`eurostat_params: Optional[dict]`** field added to `CountryBinding` (models.py).
- **Pass 1.5 (Eurostat)** added to `run_country()` in pipeline.py — sits between FRED and WB passes; applies `raw_scale` before transformation.
- **IMF `raw_scale` fix** in pipeline Pass 3 — was missing the `raw_scale` division; now consistent with FRED/WB/Eurostat passes.
- **EZ bindings updated** — 3 stale FRED growth series replaced with live Eurostat bindings:
  - `growth.industrial_prod` → Eurostat `sts_inpr_m?geo=EA20,nace_r2=B-D,s_adj=CA,unit=PCH_SM` (through 2026-04)
  - `growth.retail_sales` → Eurostat `sts_trtu_m?geo=EA20,nace_r2=G47,indic_bt=VOL_SLS,s_adj=CA,unit=PCH_SM` (through 2026-04)
  - `growth.unemployment` → Eurostat `une_rt_m?geo=EA21,s_adj=SA,unit=PC_ACT,sex=T,age=TOTAL` (through 2026-04)
- **KR IMF CPI bridge** (`PCPIPCH`) added to `kr_bindings.yaml` as `inflation.cpi_imf_annual` (annual, `raw_scale: 100`, `is_proxy: true`). Provides 2025 annual CPI = 2.1% while monthly OECD FRED feed is stale (discontinued Apr 2025).
- **Composites config updates**:
  - `min_signals_required`: 4 → 1 (Phase 2 multi-country support; confidence metric captures uncertainty)
  - `inflation.cpi_imf_annual` added to inflation_score indicator list (weight=0.30, quality=0.70; silently excluded for US/EZ)
- **Final composite quadrants**: EZ = Inflationary Boom 67% conf (3G+2I); KR = Expansion 25% conf (2G+1I annual bridge); US = Stagflation 40% conf (unchanged).
- **349 tests pass** (1 count assertion updated for new indicator).

**Next:**
- Phase 2 country 3: Japan (JP).
- EZ current_account_gdp: WB EMU has no `BN.CAB.XOKA.GD.ZS` and Eurostat BOP EA aggregate also returns 0 values. Investigate ECB SDW or IMF BOP.
- BEA refresh (after 2026-06-26) to clear 3 stale US signals.

---

## 2026-06-22 — Phase 2: Euro Area (EZ) + South Korea (KR) rollout

**Done:**
- **`config/countries/ez_bindings.yaml`**: 20 bindings (10 FRED + 10 WB). FRED: `CLVMNACSCAB1GQEA19` (GDP real Q), `CP0000EZ19M086NEST` (HICP M), `00XEFDEZ19M086NEST` (HICP core M), `ECBDFR` (ECB rate D), `IRLTLT01EZM156N` (10Y M), `RBXMBIS` (REER M), `ECBASSETSW` (ECB assets W), `EA19PRINTO01IXOBSAM`/`EA19SLRTTO01IXOBSAM`/`LRHUTTTTEZM156S` (growth — stale). WB EMU: demographics, external, capital, fiscal, R&D.
- **`config/countries/kr_bindings.yaml`**: 22 bindings (8 FRED + 10 WB + 4 IMF). FRED: `NGDPRSAXDCKRQ` (GDP real Q), `KORCPALTT01CTGYM` / `CPGRLE01KRM659N` (CPI headline+core, `raw_scale: 100`), `LRUNTTTTKRM156S` (unemployment M), `KORSLRTTO01GYSAM` (retail sales, `raw_scale: 100`), `KORPRINTO01IXOBM` (industrial prod M), `IRLTLT01KRM156N` (10Y M), `RBKRBIS` (REER M). IMF KOR: GDP$ (`NGDPD`), govt debt, budget/primary balance. WB KOR: same structural set.
- **`indicators/models.py`**: added `raw_scale: Optional[float]` field to `CountryBinding` — divides raw FRED value by this factor before transformation (converts already-YoY% percent-form series to decimal).
- **`indicators/loader.py`**: `_WB_COUNTRY_MAP` maps internal 2-letter codes → WB API codes (`EZ→EMU`, `KR→KOR`, etc.); `fetch_wb_series()` now uses this map for URL and cache path. `_IMF_COUNTRY_MAP` updated with `EZ` key.
- **`indicators/pipeline.py`**: refactored to multi-country architecture. `run_country()` helper runs passes 1–4 for any binding YAML (with `raw_scale` applied and `is_primary` flag for error handling). `run()` now runs US first, then loops over `config/countries/*.yaml` for Phase 2+ countries and runs composites for each.
- **`indicators/composites.py`**: bug fix — `_load_wide()` returned plain DataFrame on empty input even when `return_fill_age=True`, causing "too many values to unpack" crash for countries with no signals; now returns proper tuple.
- **Pipeline results**: EZ 19/20 signals live (1 empty: `external.current_account_gdp` — WB EMU doesn't publish this); KR 22/22 signals live. EZ composites: 545 snapshots, latest Inflation=+0.886 (HICP 3.1%), LowCov growth (stale series excluded). KR composites: 436 snapshots, latest Growth=+0.093, LowCov inflation (CPI stale >12m).
- **Global Overview now shows EZ + KR rows**: EZ — HICP 3.14%, ECB 2.25%, GDP 0.3%, unemployment 6.7% (2023 stale). KR — CPI 2.09%, GDP 3.78%, unemployment 2.8%, CA +5.33%, debt 52.3%.
- **349 tests pass** (no test regressions).

**Next:**
- Add EZ current account slot via alternate source (Eurostat or IMF BOP); or remove from EZ row.
- Phase 2 country 3: Japan (JP).
- BEA refresh (after 2026-06-26) to clear 3 stale US signals.

---

## 2026-06-22 — Global Overview table, Data Dashboard, sort/filter/reset

**Done:**
- **Global Overview page** (`/overview`): TE-style cross-country macro summary table — 9 columns (GDP $B, GDP Growth %, Interest Rate, Inflation, Jobless Rate, Govt Budget, Debt/GDP, Current Account, Population). Color-coded: `ov-cell-warn` (orange) for stress signals, `ov-cell-pos` (green) for positives, `ov-cell-high` (blue) for scale highlights. Date shown below each value as `yyyy-mm`. Only US row live; architecture supports future Phase 2 countries via `id LIKE '%.{concept}'` DuckDB query.
- **4 new series added** (`config/us_bindings.yaml`): `master.gdp_level_bn` (FRED:GDP, billions), `policy.fed_funds_target` (FRED:DFEDTARU, daily), `fiscal.budget_balance_gdp` (FRED:FYFSGDA188S, annual), `demo.population_total_mn` (WB:SP.POP.TOTL, annual). Total signals: 63.
- **Data Dashboard page** (`/data-dashboard`): operational feed health monitor. 63 signals grouped by force. Columns: Signal, Series ID chip, Latest Value (formatted by units), As Of (+ X days ago), Frequency, Source, Next Release (estimated), Status badges.
- **Status badges**: `✓ OK` (green), `STALE` (orange), `+Nd overdue` (amber), `LOW HIST` (blue), `PROXY`/`DERIVED`/`NO VINTAGE` (grey).
- **Sticky header**: `position: sticky; top: 0` on `thead tr th`; `box-shadow: inset 0 -2px 0 var(--border-color)` replaces `border-bottom` (which disappears under sticky).
- **Sort + Filter**: sortable columns (Signal, As Of, Frequency, Source, Next Release, Status); filter bar (search text, force, status, frequency dropdowns). Sorting switches to flat view; no sort = grouped by force.
- **Status sort key**: 0=stale → 1=overdue → 2=low_hist → 3=proxy → 4=derived → 5=OK.
- **↺ Reset Sort button**: clears sort state back to default grouped view.
- **`/overview` nav link** enabled (removed `disabled=True`; Docker was running stale image — required `docker compose build + up -d`).
- Tests updated: 3 hardcoded `== 59` counts → `== 63`; formula-route test replaced with overview-route test. **349 tests pass.**

**Next:**
- Phase 2 Eurozone rollout (`config/countries/eu_bindings.yaml`) — unblocked
- Run `python3 -m indicators.pipeline --latest` after 2026-06-26 (BEA Q1 2026 data; clears 3 stale signals)

---

## 2026-06-22 — Methodology audit, UI polish, formula clipboard, confidence fix

**Done:**
- **Confidence score fix**: rolling quadrant-consistency override (last 12 months) trivially hit 100% in a 3-year Stagflation regime. Removed the override entirely — `_regime_info_children` now always uses the raw DB `confidence` value (directional signal agreement fraction from the composites engine).
- **Formula / Methodology audit**: cross-referenced `methodology.py` prose against `composites.yaml`, `longterm_stress.yaml`, and actual computation code. Found and corrected: base_share fabricated values (Section 6), completely wrong debt stress component table (Section 9), and 4 minor description errors.
- **Debt stress formula catalog**: added `build_debt_stress_formula_catalog()` to `indicators/longterm_stress.py` — reads live from `longterm_stress.yaml`, same pattern as composites. Returns 5 formula cards (rolling Z quarterly, rolling Z annual→quarterly, staleness weight decay, aggregate stress score, band labels).
- **Clipboard copy on formula cards**: added `dcc.Clipboard` button to each card in `formulas.py`; `_clipboard_text()` formats card as plain text with raw LaTeX.
- **Formulas embedded in Methodology**: rewrote `methodology.py` — each accordion section ends with relevant inline formulas and the entire section is copyable via `dcc.Clipboard`; helper `_section_text()` generates clipboard-ready plain text including formula LaTeX. Removed the separate "ƒ Formula Reference" sub-tab and route.
- **Slider accent color**: replaced blue slider color with theme-aware amber/gold (`--slider-accent` CSS var — `#E8A317` Carbon, `#F4C842` Slate, `#4C6EF5` Dawn). Added to `THEME_CSS_VARS` in `themes.py`. Slider track tint and hover glow use `color-mix()`.
- **Slider thumb centering**: removed `top: 50%` / `transform: translate(-50%, -50%)` overrides on `.dash-slider-thumb` — Radix UI centers the thumb naturally within the track area; overriding these fought the mark-label space and caused misalignment.
- **Debt Stress nav icon**: changed from 📉 to ⚖️ (was too similar to Regime History).
- **Force Components title bar**: `html.Summary` color changed from `var(--muted-color)` to `var(--slider-accent)` (amber) for the main rollup row only; sub-headings (Growth / Inflation) unchanged.
- **Date block under PAST DATA warning**: added `date_block` div to `_regime_info_children()` quadrant column — shows "Month Year" (large, bold) + "X months/years ago" (small) for both current and historical selected dates. Uses month difference calculation with year/remainder formatting ≥24 months.
- **Settings icon size fix**: `⚙` (text glyph, renders small) → `⚙️` (emoji variation selector); icon span `fontSize: "1.1em"`; button `fontSize` raised to `"0.875rem"`; added `className="sidebar-nav-link"` so tooltip wires to same class.
- **Sidebar nav tooltips (minimized)**: nav links got unique `id` props; `_nl()` helper appends `dbc.Tooltip` to `_tooltips` list; Settings button gets its own tooltip. Overdue sync banner: `⚠` icon always visible, `html.Span(text, className="sidebar-text")` hidden when collapsed.

**Next:**
- Phase 2 Eurozone rollout (`config/countries/eu_bindings.yaml`) — unblocked
- Run `python3 -m indicators.pipeline --latest` after 2026-06-26 (BEA Q1 2026 data; clears 3 stale signals)

---

## 2026-06-22 — Sidebar slider polish + scatter map fix + rolling confidence

**Done:**
- **Scatter map blank bug fixed**: `update_scatter_chart` hovertemplate had invalid f-string `{sel_g:.2f if sel_g is not None else '—'}` (format spec can't contain conditional logic); pre-computed `_g_str`/`_i_str` strings before the f-string
- **Sidebar Z-Score + Disequilibrium sliders**: added `dcc.Slider` widgets directly to `_left_nav()` for both windows; `step=None` snaps to pre-computed marks only; wired to existing `zscore-window-store` / `diseq-window-store` via `ctx.triggered_id` dispatch
- **Slider persistence across refreshes**: changed both stores to `storage_type="local"` (browser localStorage); added `sync_zscore_slider` / `sync_diseq_slider` callbacks (`prevent_initial_call=False`) to restore slider positions from store on page load
- **Rolling confidence**: when a Z-score window is active, confidence now shows quadrant-consistency % over the last 12 months of rolling g/i scores instead of baseline directional-agreement; updates visibly when slider moves; `_RQ_MAP` promoted to module level
- **Slider visual polish** (Dash 4.x / Radix UI class names — NOT rc-slider):
  - Tooltip hidden: `.dash-slider-tooltip { display: none }`
  - Track background: `rgba(76,155,232,0.28)` — reads on Carbon/Slate/Dawn
  - Filled range: `#4C9BE8` solid blue
  - Thumb: 5×18px vertical pill (`dash-slider-thumb`); hover glow
  - Mark text: `var(--font-color)` inline style in `marks` dict (overrides Radix default dark ink)
- **Country selector**: `dbc.Select` in sidebar; US enabled, EZ/JP/GB disabled (Phase 2 hooks)
- **Settings modal**: separate Disequilibrium window radio added alongside Force Z radio

**Next:**
- Phase 2 Eurozone rollout per user direction
- BEA refresh after 2026-06-26: `python3 -m indicators.pipeline --latest`

---

## 2026-06-22 — Full pipeline rolling Z implementation + dashboard panels update

**Done:**
- **`indicators/transform.py`**: added `months_to_periods(months, frequency)` — converts month-count windows to native observation counts per frequency (M→months, Q→months÷3, A→months÷12, min 4)
- **`indicators/models.py`**: added 6 rolling Z-score fields to `Signal`: `zscore_12m`, `zscore_18m`, `zscore_24m`, `zscore_36m`, `zscore_48m`, `zscore_60m`
- **`indicators/normalize.py`**: `build_signals()` now pre-computes all 6 rolling Z-scores for each signal using `zscore_rolling()` and `months_to_periods()` with frequency-adjusted windows
- **`store/store.py`**: added 6 rolling Z columns to signals table schema + 9 rolling composite columns (`growth_score_36m/48m/60m`, `inflation_score_36m/48m/60m`, `disequilibrium_12m/18m/24m`) to composites table; `init_schema()` migrations; `update_rolling_composites()` batch-UPDATE function
- **`indicators/composites.py`**: `compute_composite_history()` gains `zscore_col` and `diseq_window` parameters; supports rolling Z for force scoring and rolling std for disequilibrium normalization
- **`indicators/pipeline.py`**: added Passes 5b–5d — runs composites engine 3× more with (36m/12m), (48m/18m), (60m/24m) window pairs; stores results via `update_rolling_composites()`; 558 composite rows updated per pass
- **`dashboard/charting_data.py`**: `load_composite_history()` now includes all 9 rolling columns in SELECT + accepts `country` parameter
- **`dashboard/charting.py`**:
  - Settings modal: removed 24mo force option (below guidance range), added **Disequilibrium Window** section (Full History / 24mo / 18mo★ / 12mo) with `diseq-window-radio` wired to `diseq-window-store`
  - `app.layout`: added `diseq-window-store` and `country-store` dcc.Stores
  - `_left_nav()`: added country dropdown (`dbc.Select`, id=`country-selector`) above nav groups; shows US (enabled), EZ/JP/GB (disabled, "soon")
  - New callbacks: `update_diseq_window`, `update_country`
  - `_FORCE_WINDOW_COL`/`_DISEQ_WINDOW_COL` maps for column routing
  - `update_regime_info`: uses DB pre-computed rolling columns instead of on-the-fly computation; accepts `diseq-window-store`, `country-store` inputs
  - `_regime_info_children()`: uses `rolling["diseq_score"]` when diseq window active
  - `update_regime_chart`: uses `g_col`/`i_col`/`d_col` rolling columns for all 7 subplots (quadrant derived from rolling scores when window active)
  - `update_scatter_chart`: uses rolling columns for context dots, trail, selected point; axis labels show window when active
- **Pipeline re-run**: 558 baseline composites + 3×558 rolling variants stored; all signals refreshed with 6 rolling Z columns; 349 tests pass; `:8502` HTTP 200

**Pipeline note:** 11 FRED series still returning API-key errors (breakeven, yields, spreads, crude oil) — these hit rate limits without cached parquets. Those are pre-existing; rolling Z for those series is NaN. The composite passes use zscore_36m/48m/60m from the cached signals that do have data.

**Next:** Phase 2 Eurozone rollout; BEA refresh after 2026-06-26; further :8502 UI polish per user direction

---

## 2026-06-21 — Rolling Z-score window, Momentum Z, and Methodology page

**Done:**
- **`indicators/normalize.py`**: added `zscore_rolling(series, window)` — rolling mean/std Z-score capped at ±4σ with `min_periods = window // 2`
- **`dashboard/charting_data.py`**: added `load_composite_signal_values(country)` — bulk-loads all growth + inflation composite signal transformed values from DuckDB for rolling Z computation
- **`dashboard/charting.py`**:
  - Imported `numpy`, `Path`, `load_composite_signal_values`, `dashboard.methodology`
  - Added `_compute_rolling_history(country, window)` — recomputes full composite score history with rolling Z-scores; applies nominal weights from composites.yaml; aligns quarterly series to monthly index via ffill ≤ 95 days
  - Added `_momentum_z_at(comp, idx, window=12)` — Z-score of the current MoM force-score change against the preceding 12 monthly changes
  - **Settings modal** (`dbc.Modal`, id=`settings-modal`) with 5 window options: Full History / 60mo / 48mo (recommended) / 36mo / 24mo; wired to `zscore-window-store` dcc.Store
  - **⚙ Settings** button added at the bottom of the left sidebar (`id="settings-btn"`)
  - **`_page_methodology()`** + `/methodology` route added to `_PAGE_MAP`
  - **📖 Methodology** nav link added to the Data section in the left sidebar
  - `update_regime_info` callback: added `Input("zscore-window-store")` input; when window > 0, recomputes growth/inflation scores from rolling Z history, derives rolling quadrant label, and computes rolling MoM deltas; always computes Momentum Z from stored composite history
  - `_regime_info_children()`: added `rolling` dict parameter; Force Z-Score group header shows "rolling Nmo" when window active; new **Momentum Z (12mo)** group shows Z-score of recent MoM changes; quadrant label derived from rolling scores when active
- **`dashboard/methodology.py`** (new): comprehensive 12-section methodology page covering overview, data sources, signal transformation, force Z-score (both modes), momentum (both metrics), dynamic weighting, composite construction, regime classification, debt stress, data quality flags, country coverage, and deferred items
- 349 tests pass; `:8502` rebuilt and returns HTTP 200; `/methodology` and settings modal confirmed in Dash layout JSON

**Next:** Phase 2 Eurozone rollout; BEA refresh after 2026-06-26; further :8502 UI polish per user direction

---

## 2026-06-21 — Code-backed Formula Reference

- Added a Formula Reference page at `/formulas` under the Dash Data navigation
- The page renders live equations for component/force Z-scores, configured and effective weights, momentum tilt and breadth, confidence, structural disequilibrium, and observation-age decay
- Formula cards read active values directly from the composite calculation modules and `config/composites.yaml`, including momentum alpha/bounds, neutral-Z threshold, decay half-life/hard drop, frequency carry caps, and coverage minimums
- Each card identifies its authoritative calculation function so formulas and displayed settings remain traceable as the methodology evolves
- Rebuilt :8502, verified `/formulas` in headless Chromium, and passed all 349 tests in Docker

---

## 2026-06-21 — Dynamic Growth/Inflation force weighting

- Replaced legacy fixed force weights with the documented `base_share × importance × quality_factor` model; all 17 importance defaults match `docs/feedback/force-momentum weighting guidance.md` and remain editable in `config/composites.yaml`
- Added point-in-time momentum agreement tilts (1.5× agreement, 0.5× conflict by default) and exponential observation-age decay with a configurable three-month half-life
- Preserved frequency-specific carry caps and provider-stale/low-history exclusions; each monthly snapshot now stores a JSON audit of config weight, momentum multiplier, age, decay, effective weight, and normalized contribution for every component
- Rebuilt Force Component Inputs to mirror Debt Stress: Importance, Config Wt, Eff Wt, Last Data, Z-score, Momentum, and explicit ACTIVE/BOOSTED/CONFLICT/DECAYED/BLANK tags; disclosure state remains persistent across dates
- Migrated and regenerated 558 US composite snapshots; latest remains Stagflation (Growth −0.079, Inflation +0.399, Confidence 36%)
- Updated methodology/help text and both dashboard component tables; 347 tests pass on host and Docker, :8501/:8502 rebuilt, and the live :8502 table passed Chromium interaction/content checks

---

## 2026-06-21 — Regime History synchronized hover and disclosure state

- Synchronized hover across all seven Regime History subplots by mirroring the hovered date through Plotly's client-side hover API
- Added a full-height dashed vertical guide and placed each value label on its respective graph with consistent black styling
- Preserved the Force Component Inputs disclosure state while stepping through dates; an opened table now remains open as the snapshot changes
- Raised the minimum Plotly version to 5.21 for cross-subplot hover support and added callback/layout/state regressions
- Verified the rendered interactions in headless Chromium; 339 repository tests pass and rebuilt :8502 returns HTTP 200

---

## 2026-06-21 — Regime History graph point selection

- Wired all five Regime History subplots through Dash's native graph click event; clicking a past point now selects the corresponding composite snapshot
- The shared step index updates the sticky summary/component data and every graph's selected-point marker together
- Date-based selection works across traces with different point counts and resolves sparse series to the nearest available composite date
- Added exact-date, nearest-date/timezone, and invalid-click regressions; 335 tests pass on host and Docker
- Rebuilt :8502; Regime History returns HTTP 200 and the click callback is registered without server errors

---

## 2026-06-21 — Routed Regime History step controls

- Replaced page-specific Prev/Now/Next callback inputs with shared structured button IDs, so the callback remains active when only the routed Regime History page is mounted
- Prev now selects the immediately older data point; Next moves one point toward the present; Now returns to the latest point
- The shared `regime-step-index` continues to drive the sticky summary/component table and all five graph rows together
- Added routed-layout and step-transition regressions; 329 tests pass on host and Docker
- Rebuilt :8502; Regime History rendered all controls in a headless-browser smoke test with HTTP 200 and no callback errors

---

## 2026-06-21 — Post-UI-restructure code review remediation

- Fixed the Data Explorer initial-load callback error caused by passing Plotly's `title` layout argument twice
- Made Regime Map panels point-in-time in both Dash and Streamlit: historical stepping now controls What Changed, Conflicts, lens drill-downs, quality flags, and sparkline windows
- Made the Streamlit Debt Stress tab honor the selected regime date instead of always showing the latest snapshot
- Corrected change-feed ranking so the latest reading must be recent but its comparison reading may fall outside the 120-day display window, preserving quarterly-series deltas
- Updated the Regime History callback tests to the routed-page signature and added as-of/change-feed regressions
- 324 tests pass; rebuilt :8501/:8502 containers return HTTP 200; all six :8502 routes completed headless-browser smoke tests with no callback errors
- Next: continue Phase 1I UI consolidation, then Phase 2 Eurozone rollout
- Blockers: BEA refresh remains pending until after 2026-06-26

---

## 2026-06-21 — :8502 Dash UI restructuring + Regime Map panels

**Done:**
- **Left-sidebar navigation**: replaced tabbed layout with persistent vertical pill nav. Two groups — *Data* (Chart Overlay, Data Explorer) and *Indicators* (Yield Curve, Regime Map, Regime History, Debt Stress). Series selector moved inside Chart Overlay.
- **Browser back button**: `dcc.Location(id="url", refresh=False)` + `dbc.NavLink` hrefs push to browser history; `page-trigger` store guarantees downstream callbacks fire after DOM is updated.
- **Regime Map scatter zoom**: quadrant backgrounds widened to ±100 (always fill viewport); initial axis range now computed from actual data with 15% buffer; `uirevision="scatter-map"` preserves user zoom across step changes.
- **Below-map panels on :8502 Regime Map page** (ported from :8501):
  - *What Changed* — top-8 Z-score movers (leading/coincident only), Δ vs prior reading
  - *Cross-Signal Conflicts* — leading vs lagging/coincident direction gap > 40%; PMI vs Payrolls check
  - *Geopolitical-Risk Overlay* — static deferred placeholder (WGI G-03)
  - *Signal Drill-Downs* — collapsible `dbc.Accordion` for all 10 lens groups (A–I + Master); each panel shows indicator table with value, direction, percentile badge, Z-score, quality flags, causal-linkage tooltip
  - *Data-Quality Log* — collapsed by default; `dash_table.DataTable` of stale/proxy/low-history/no-vintage signals
- **Fixed chart height clipping bug**: removed hardcoded `height=` from regime history and debt stress figures; set `responsive=True` on `dcc.Graph` components with `calc(100vh - Xpx)` CSS heights; fixed double `margin=` keyword argument error in `update_layout` calls.
- **Lens table rendering fix**: replaced `dcc.Markdown(dangerously_allow_html=True)` (unreliable for complex HTML in Dash 4.2) with proper `html.Table` / `html.Tr` / `html.Td` Dash components; accordion `title` props changed to plain strings.
- `dashboard/charting_data.py`: added `load_latest_signals`, `load_change_feed`, `load_all_signal_histories`.
- All services rebuild cleanly; :8502 HTTP 200; no callback errors in logs.

**Next session:** Continue :8502 UI improvements. Consider migrating remaining :8501 content (methodology guide, footnotes). Phase 2 Eurozone rollout remains queued.

**Blockers:** BEA refresh still pending (run `python3 -m indicators.pipeline --latest` after 2026-06-26).

---

## 2026-06-20 — Post-Phase-1H code review remediation

- Fixed Regime History carry-age badges: `stale_signals` point-in-time metadata now marks forward-filled components as `STALE · Nm` even when the source observation's ingestion-time stale flag is false
- Made the Lightweight Charts frontend runtime self-contained: the pinned v4.1.3 asset is vendored into the nginx image at build time and protected by a SHA-256 check
- Hardened composite PCA against wholly missing columns, non-finite inputs, undersized matrices, and zero-variance datasets; the dashboard now renders a controlled unavailable state instead of raising
- Added regression tests; 321 host tests pass and rebuilt charting/API/frontend services return HTTP 200
- Next: Phase 2 Eurozone rollout; refresh BEA data after 2026-06-26
- Blockers: `FRED_API_KEY` is not available in the host shell, so no live ingestion refresh was run

---

## 2026-06-20 — TradingView Lightweight Charts system (ADR-007 Option B)

Built the full TradingView system. All 319 tests pass; both Docker services healthy.

**Backend** (`dashboard/charting_lc/main.py`): FastAPI on :8004 (Docker: :8000 internal). Five endpoints: `/catalog`, `/series/{signal_id}`, `/composite-history`, `/signals/snapshot`, `/yield-curve/{date}`. CORS enabled; nginx at :8503 reverse-proxies `/api/` so the browser uses one port.

**Frontend** (`dashboard/charting_lc/frontend/index.html`): Single-page app with four tabs:
- 📈 Charts: TradingView Lightweight Charts multi-pane chart; 50-series sidebar grouped by force; 1Y/3Y/5Y/10Y/MAX horizon; Value/Z-Score toggle; panes time-synchronized; default series: GDP / Core PCE / Fed Funds
- 📊 Macro Table: all 59 signals; sortable columns (Z-score bar, direction, 1m/3m/12m deltas, momentum percentile); force filter pills; search box
- 🔄 Regime: 4-pane chart (Growth Score / Growth Momentum / Inflation Score / Inflation Momentum); ⏮ ‹ › ⏭ step controls + Play/Pause + arrow-key navigation; live info strip showing quadrant/scores/confidence per step
- 📉 Yield Curve: bar chart + table for any selected date

**Docker**: `lc_api` (Python/uvicorn, port 8004→8000) + `lc_frontend` (nginx:alpine, port 8503→80) in docker-compose.yml.

Next: Phase 2 Eurozone rollout (unblocked; see session-checklist.md). BEA refresh after 2026-06-26.

---

## 2026-06-19 — Session close: TradingView system spec reviewed; docs and memory updated

All 319 tests pass. Reviewed ADR-007 Option B (FastAPI :8000 + TradingView Lightweight Charts :8503) and confirmed the skeleton at `dashboard/charting_lc/main.py`. Next session will implement the full TradingView system per the ADR.

Next: Build TradingView Lightweight Charts system (Option B, ADR-007). Backend: `api/main.py` FastAPI with DuckDB endpoints. Frontend: nginx-served HTML/JS with Lightweight Charts v4 at :8503. Docker: two new services in docker-compose.yml.

---

## 2026-06-19 — D1, B1, A2/I2 (momentum percentile, period audit, composite PCA)

**D1** (momentum percentile): `momentum_percentile DOUBLE` added to `Signal` model and DB. In `build_signals()`, `_percentile_series()` is applied to the valid `change_3m` slice — rank of current 3-month change within its own full history. Aligns momentum comparisons across high/low-volatility series. 5 new tests.

**B1** (calendar-adjusted N audit): All 5 frequencies audited. `_YOY_PERIODS` and `_MOMENTUM_PERIODS` constants are correct: D=252/21/63/252, W=52/4/13/52, M=12/1/3/12, Q=4/1/1/4, A=1/1/1/1. 14 new explicit tests covering all frequency × period combinations including weekly and annual YoY.

**A2/I2** (composite correlation + PCA): New "📊 Composite Analysis" subtab added to the Data Explorer right panel. `load_composite_zscore_matrix()` + `compute_pca()` added to `explorer_data.py`. Shows: (1) 17×17 Pearson correlation heatmap of composite signal Z-scores with a growth/inflation divider line; (2) Scree plot + PC1/PC2 loadings heatmap. 10 new tests. Container rebuilt.

Pipeline re-run: 59 signals updated with `momentum_percentile`. 319/319 tests pass.
Next: Phase 2 Eurozone rollout (user sign-off after BEA refresh on 2026-06-26).

## 2026-06-19 — Regime History tab UX improvements (momentum display, table rollup, chart subplots)

Three improvements to the Dash :8502 Regime History tab:

1. **Momentum in summary box**: Dedicated `_mom_block` components for Growth Momentum and Inflation Momentum now appear as separate stat blocks (e.g. "4/9") after the force scores, separated by a vertical divider. Force score subtitles simplified to "N/N signals active" only.

2. **Momentum charts**: `update_regime_chart` now uses 5 subplot rows (was 3). New layout: Growth Score → Growth Momentum (%) → Inflation Score → Inflation Momentum (%) → Quadrant. Momentum rows are 15% height; force rows 25%; quadrant 20%. Both momentum rows use 0–100% Y-axis with 50% dotted reference line. Step-selection markers added for all 5 rows. Chart container height raised to 85vh.

3. **Signal table rollup**: Each force section now wrapped in `html.Details`/`html.Summary` for independent collapse/expand (open by default). Each summary shows "GROWTH/INFLATION FORCE INPUTS · N/M active" — same information as before but now clickable headers.

   DB change: `growth_momentum DOUBLE` + `inflation_momentum DOUBLE` columns added to composites table (schema migration + pipeline re-run). 558 snapshots re-generated. 287 tests pass (7 new tests).

Next: A2/I2 correlation matrix + PCA analysis, or D1 momentum percentile-rank.

## 2026-06-19 — Feedback tracker remediation: L4 (regime composite stale-lag badges)

L4 (dashboard stale-lag badges): `load_composite_history()` in `charting_data.py` now includes `stale_signals` in the SELECT. `_regime_info_children()` gains a `stale_dict: dict[str, int]` parameter. `update_regime_info` callback parses the `stale_signals` string (reusing `_parse_stress_components()`) and passes the dict through. In the component table, STALE badges now render as "STALE · Nm" (e.g. "STALE · 2m") for signals with known fill-months — matching the J5 debt stress pattern.

5 new tests (3 unit, 2 integration); 280/280 pass. All L1–L4 staleness items for regime composite are now done. L5 deferred.
Next: A2/I2 correlation + PCA analysis in Data Explorer, or D1 (percentile-rank momentum).

## 2026-06-19 — Feedback tracker remediation: L2, L3 (regime composite staleness)

L2 (per-frequency carry cap): `per_frequency_ffill_limit` added to composites.yaml (M:3, Q:9, A:15, D:1); `_load_wide()` accepts `per_signal_limits: dict[str, int]` for per-column ffill; pipeline Pass 5 builds freq_map from verified bindings and passes it to `compute_composite_history()`. Monthly signals are now capped at 3 months fill (was 13 uniformly).

L3 (stale signal tracking): `CompositeSnapshot.stale_signals: Optional[str]` field added; DB schema updated with migration; snapshot loop populates `"signal_id:months,..."` string from fill_age data. Verified: 2026-06-19 shows 13 signals with 1-2 months fill — correct for mid-month before all releases land.

6 new tests; 275/275 pass. Pipeline re-run: 558 composite snapshots, 59/59 signals.
Next: L4 (dashboard stale-lag badges in Regime History), then A2/I2 PCA analysis.

---

## 2026-06-19 — Feedback tracker remediation: C1, E1, F1/L1, G1, H1, H2

Implemented six items from `docs/feedback_tracker.md` — all 269 tests pass:

- **H1**: Both TIPS breakeven weights halved to 0.5 in `composites.yaml`; combined contribution stays 1.0
- **G1**: Labour-market signals (payrolls, unemployment, job_openings, labor_force_part) → 0.75 weight; capacity_util → 1.05; output/demand stays 1.00
- **C1**: `_zscore_series()` now caps Z-scores at ±4σ; prevents COVID/GFC spikes from distorting all other historical Z-scores
- **E1**: `_direction(change_3m, series_std)` uses `series_std × 10%` as the significance threshold; `series_std` computed in `build_signals()` and passed through; eliminates false directional calls on low-volatility flat series
- **F1/L1**: `_compute_fill_age()` tracks months since last observation; in `compute_composite_history()` each signal's effective weight is `base_weight × decay_factor^fill_age`; config-gated via `staleness_decay.enabled/decay_factor` in `composites.yaml` (default: enabled, factor=0.9)
- **H2**: `CountryBinding.pre_smooth_window` optional field; `pre_smooth_window: 7` in crude_oil binding; Pass 1 of pipeline applies 7-day rolling mean to raw prices before YoY transformation

20 new tests added across `test_normalize.py` and `test_composites.py`.
Tracker updated: H1, H2, G1, C1, E1, F1, L1 all marked ✅ Done.
Next: pipeline re-run to regenerate signals/composites with new weights + decay; Phase 2 Eurozone rollout; L2 per-frequency carry cap.

---

## 2026-06-19 — Post-Phase-1F code review remediation

- Reviewed all changes from the Long-Term Debt Stress implementation, staleness work, Debt Stress UI, Regime History component table, and methodology-feedback documentation
- Corrected `BCNSDODNS` from millions to billions before dividing by GDP; latest corporate debt/GDP raw value is now 0.454 rather than 454.2
- Made staleness point-in-time: historical snapshots now use only source dates available at that quarter, and forward-filled synthetic dates no longer masquerade as observations
- Replaced the misleading linear “halflife” with true exponential half-life decay; repaired corporate carry-forward and the extrapolation trigger at the carry boundary
- Fixed both historical UIs: Regime History loads component values as of the selected month, and the Streamlit HUD loads Debt Stress as of the selected regime date
- Added derived-source dates and consistent effective-weight calculations to the Debt Stress table
- Hardened storage against future rows and duplicate provisional quarters; added config validation, country-scope guards, safe list defaults, and explicit schema migrations
- Removed the empty misspelled `docs/macro_methodoloy.md`; retained the correctly named feedback document
- Full suite: 249 passed; live pipeline: 59/59 signals, 185 debt-stress snapshots, latest stress +0.488 with 5/7 components and 72.7% retained weight; no future rows
- Next: Phase 2 Eurozone rollout; debt-stress configuration must be country-specific before enabling it outside the US
- Blockers: real-time publication/vintage metadata remains Phase 3 work; historical stress output is latest-revised, not a real-time backtest

---

## 2026-06-19 — Session 17: Debt Stress tab — full-width component detail table

- `dashboard/charting_data.py`: added `_COMPONENT_SIGNAL_MAP` + `load_debt_stress_component_dates()` — queries signals table for last `as_of` per underlying signal (min of sub-components for derived series)
- `dashboard/charting.py`: Debt Stress tab layout changed from 3/9 split to stacked (full-width info card → full-width chart); `_build_debt_stress_info` rewritten with score summary strip + 7-column component table; new helpers `_fmt_period`, `_carry_expires`; callback now passes `component_dates` dict; old narrow bar list replaced
- Component table columns: Component · Freq · Config Wt · Eff Wt (post-decay, coloured amber/red when reduced/zero) · Last Data (YYYY-Qn or YYYY) · Z-Score (mini bar) · Status/Detail
- `BLANK` status rows explain carry expiry in full: "carry expired · last data: 2024 · carry cap 4q → covered to 2025-Q4 · extrapolation disabled · last known value: −4.08"
- 239/239 tests pass; committed + pushed
- Next: Phase 2 Eurozone rollout; pipeline re-run after June 26 BEA release
- Blockers: None

---

## 2026-06-19 — Session 16: Long-Term Debt Stress — Staleness Handling (Gaps 1–3)

- **Gap 1 (weight decay)**: Components with excess staleness lag decay linearly toward zero weight; drops below `stale_min_weight_fraction` are excluded from the score. Parameters in `config/longterm_stress.yaml` under `staleness:`.
- **Gap 2 (carry limit + extrapolation)**: All builder functions and `_rolling_z_annual_then_ffill` now take `ffill_limit=max_carry_q` from config; `_extrapolate_z_score` adds `rolling_mean` / `linear_trend` extrapolation behind `extrapolation.enabled: false` config gate.
- **Gap 3 (structured stale strings)**: `stale_components` and new `extrapolated_components` fields store `"cid:lag_q"` strings; dashboards parse and display amber (stale Nq) and blue (extrap Nq) badges; backward-compatible parser handles old plain-`"cid"` format.
- `indicators/models.py`, `store/store.py`: `extrapolated_components` column added with migration guard.
- 14 new tests; bug fix in `test_extrapolated_components_populated_when_enabled` — dsr used `periods=80` (ends 2019), which meant q_index never reached recent stale quarters; fixed to `pd.Timestamp.today()`.
- 239/239 tests pass; committed `2f0a97f`; pushed.
- Next: rebuild containers to pick up staleness changes; pipeline re-run after June 26 BEA release; Phase 2 Eurozone rollout.
- Blockers: None

---

## 2026-06-19 — Session 15: Long-Term Debt Stress Indicator (UI layer)

- Fixed invalid Z-scores in prior session's pipeline output: root causes were `ffill(limit=1)` not covering BIS publication lag + `resample("QE").last()` not extending past last data point; added `_extend_to_current_quarter()` helper; all 7/7 components now active at 2026-Q1 (stress=+0.447, retained_weight=100%); stale component tracking introduced (`stale_components` field)
- `dashboard/charting_data.py`: added `load_debt_stress_history(country, start_date, end_date)` query helper
- `dashboard/app.py`: added `load_debt_stress_latest()` cached loader; added `_render_hud_debt_stress()` HTML helper; added `debt_stress` parameter to `render_hud()`; HUD now shows Debt Stress gauge after Disequilibrium with score, band label (color-coded), component count (N/7), and stale badge
- `dashboard/charting.py`: added "📉 Debt Stress" tab with 2-row layout (left info card + right chart); info card shows score, band, per-component Z-score bars with stale badges; chart shows composite score time series (row 1, band shading) + all 7 component Z-scores as lines (row 2, shown as stress-direction contribution i.e. negative-direction components are negated); `load_debt_stress_history` imported; two callbacks wired
- 225/225 tests pass; both dashboards unchanged for existing tabs
- Next: Phase 2 Eurozone rollout (pending user sign-off on US data); pipeline re-run after June 26 BEA release to clear 3 stale signals; consider adding band-change alerts to change feed
- Blockers: None

---

## 2026-06-19 — Session 14: Long-Term Debt Stress Indicator (computation layer)

- Implemented the Long-Term Debt Stress Indicator per `docs/longterm_stress_indicator.md`
- `config/longterm_stress.yaml`: all tunable parameters (weights, rolling windows, coverage threshold, interpretation bands) explicitly annotated with `# TUNABLE` comments and rationale; no tunable values buried in code
- `indicators/models.py`: added `DebtStressSnapshot` Pydantic model with per-component Z-scores and raw values for full auditability
- `indicators/longterm_stress.py`: computation module; load_longterm_stress_config, rolling Z-score with shift(1) look-ahead protection at quarterly (window=40) and annual (window=10) frequency, weight renormalisation under missing components, low_coverage flag when retained_weight < 0.60
- `store/store.py`: `debt_stress_snapshots` table + `upsert_debt_stress` + `query_debt_stress_history`; wired into `init_schema`
- `indicators/pipeline.py` Pass 6: runs stress computation, upserts, prints latest reading
- `tests/test_longterm_stress.py`: 19 tests covering unit conversion (FYOINT millions→billions), look-ahead prevention (shift=1 vs shift=0), sign convention (negative-direction components lower score), missing-component renormalisation, coverage threshold, no future-dated snapshots, band labels, config-driven weight change, model defaults, and config structural integrity
- Pipeline verified: 222/222 tests pass; 185 debt stress snapshots stored; latest (2026-03-31): stress=null, 5/7 components active, retained_weight=55% (< 60% threshold) → low_coverage=True (correct — TDSP and one other stale at current date)
- Key design: all tunable parameters in YAML with rationale; no hardcoded values; component Z-scores + raw values stored for dashboard decomposition later
- Next: Phase 2 Eurozone rollout; pipeline re-run after June 26 BEA release; dashboard panel for debt stress (after historical output review)
- Blockers: None

---

## 2026-06-19 — Repository-wide code review remediation

- Fixed all nine findings from the review of changes since the prior repository audit
- Prevented future-dated composite snapshots and made current-month upserts replace the provisional row atomically
- Activated the bound PPI inflation input; excluded stale and low-history signals from composite scoring; aligned disequilibrium with standardized declared-equilibrium distances
- Removed the duplicate Dash callback for the Explorer Latest card; corrected weekly bank-loan gap detection and the swapped BIS/World Bank REER catalog entries
- Converted `chart_series.yaml` to valid YAML and replaced the regex/duplicate catalog parsers with one canonical loader
- Rewrote the Long-Term Debt Stress Indicator specification to correct units, frequencies, component signs, debt-service definitions, and weights
- Added regression coverage and registered the integration marker; full suite passes: 203 tests, with only Dash's upstream DataTable deprecation warnings
- Live pipeline verified: 59/59 signals, 558 snapshots, latest date 2026-06-19, 8/8 inflation inputs, no future composite rows; Growth=−0.048, Inflation=+0.428, Confidence=48%, Disequilibrium=0.702
- Next: implement the corrected Long-Term Debt Stress Indicator specification
- Blockers: None

---

## 2026-06-19 — Session 13: Regime stepper (:8501) + Sync banner (:8502)

- Added `← Prev` / `Next →` stepper to Streamlit :8501 — controls both the Macro Regime HUD and the 4-quadrant scatter map; when stepping back, the HUD shows a gold `⚠ Jun 2024` warning in the bottom-right of the regime box; scatter trail and selected marker shift to the chosen date; step clamped to available history and persisted via `st.session_state["regime_step"]`
- Added sync banner to Dash :8502 header (inline with title): shows "Next sync: Jun 26, 2026 · BEA Q1 2026 current account / NIIP (7d)" today; auto-flips to gold "⚠ Update data now" after the release date passes; `_UPCOMING_RELEASES` list at top of `charting.py` should be updated each session
- Rebuilt Docker containers (`docker compose build && up -d`) to pick up code changes; 195/195 tests passing
- User added `docs/longterm_stress_indicator.md` — spec for a new Long-Term Debt Stress Gauge feature (two-layer framework: Short-Term Health + Long-Term Stress Index as complementary composites); to be implemented in next session
- Next: implement Long-Term Stress Indicator per `docs/longterm_stress_indicator.md`; also re-run `python3 -m indicators.pipeline --latest` after June 26 (BEA release) to clear 3 stale signals

---

## 2026-06-19 — Session 12: Data docs + Regime History navigation

- Added `docs/data_release_calendar.md` — full table of all 59 signals with period type, period start/end, release lag by provider, latest obs in DB, and staleness status; explains FRED period-start date convention (2026-01-01 = Q1 2026) and why Trading Economics can show Q1 2026 data that we also have
- Added `docs/methodology.md` — comprehensive methodology document covering signal pipeline (transform → Z-score → percentile → momentum → direction → ffill), Growth Score, Inflation Score, Regime Quadrant, Confidence, Disequilibrium; includes formulas, code references, indicator rationale table, and known-limitations section aimed at reviewer feedback
- Ran pipeline to check for BEA Q1 2026 data (current account, NIIP, debt service); still at Q4 2025 — BEA release expected June 26; re-run after that date
- Added ← / → nav buttons to Regime History tab: step through monthly composite snapshots; Macro Regime info box (quadrant badge + Growth/Inflation/Confidence/Disequilibrium scores) updates on each step; `⚠ Past Data` warning appears bottom-right for any non-current selection; chart gets dashed vline + highlighted circle marker at selected date
- Fixed remaining `themes['midnight']` fallback in clientside callback (was dead code but incorrect)
- 195/195 tests passing (+8 new tests for nav feature and composite query columns)
- Next: Phase 2 Eurozone rollout; BEA re-run on June 26

---

## 2026-06-19 — Session 11: Theme switcher + staleness fix

- Added multi-theme support to Dash app (:8502): Carbon (dark, default), Slate (dark), Dawn (light) — `dashboard/themes.py` is single source of truth; CSS custom properties + clientside callback drive all styling changes without page reloads
- Created `dashboard/assets/theme.css` for static CSS defaults and fixed `dcc.Checklist` label colour inheritance bug (labels need explicit `#series-selector-body label { color: var(--series-label-color) !important; }`)
- Fixed staleness false-positive bug in `indicators/normalize.py`: `_is_stale()` was comparing `today - period_start_date` against thresholds that assumed release dates, not period starts; raised M: 50→90d, Q: 120→200d, A: 400→600d
- After threshold fix and pipeline re-run: 53/59 signals correctly not-stale; 6 remain legitimately stale (TFP/R&D: 2-3yr structural lag; household debt BIS + BEA current account/NIIP/debt-service: 1-3 quarter structural lag)
- 191/191 tests passing; Midnight theme removed; Carbon is now default
- Next: Phase 2 — Eurozone rollout (user data quality sign-off satisfied)

---

## 2026-06-19 — Session 10: Phase 1E — Data Explorer + session close

- Shipped Phase 1E end-to-end: Data Explorer tab in the Dash app (:8502) with signal browser (59 signals, filterable by force/flags), Time Series tab (dual raw+Z-score chart, equilibrium reference, stale markers, ±2/3σ bands, stat cards, reference spot-check vs provider), Observations tab (full paginated table, outlier/stale row highlighting, CSV download), Quality & Gaps tab (metadata, flag badges, gap detection), Raw vs Processed tab (parquet cache vs DB delta to verify transforms)
- Decided: Data Explorer lives as a new tab in the existing Dash app (not a separate page) — lowest friction, data helpers already built
- 31 new tests; total suite 187/187 passing; Docker :8502 HTTP 200 confirmed
- User will use Explorer to verify data accuracy before committing to Phase 2 country rollout
- Next: Phase 2 — Eurozone rollout (once user is satisfied with US data quality)

---

## 2026-06-19 — Session 9: Phase 1D — Dash charting view + session close

- Shipped Phase 1D end-to-end: Plotly Dash app (`dashboard/charting.py`) on `:8502` with series selector sidebar (50 series, 9 lens groups), Chart Overlay tab (multi-pane, shared X-axis, independent Y-axes, `hovermode="x unified"`), Yield Curve tab (full term structure 3M→30Y + historical 10Y-2Y spread bar), Regime History tab (growth/inflation scores + quadrant colour bands)
- Created `config/chart_series.yaml` (series catalog), `dashboard/charting_data.py` (DuckDB query helpers + FRED parquet cache reads), `dashboard/charting_lc/` (Option B TradingView skeleton, deferred per ADR-007)
- Pre-fetched DGS3MO, DGS1, DGS5, DGS30 into raw_cache for complete yield curve term structure
- Added `charting` service to `docker-compose.yml`; Docker acceptance gate passed: `:8502` returns HTTP 200
- 25 new tests; total suite 156/156 passing
- Next: Data explorer — verify raw signal data accuracy before Phase 2 country rollout

---

## 2026-06-18 — Session 8: Dashboard rendering fix + session close

- Fixed critical rendering bug: Streamlit 1.39+ silently ignores `unsafe_allow_html=True` in `st.markdown()`; replaced all 10 affected call sites with `st.html()` — HUD, What Changed rows, conflict panel, GPR overlay, lens "About" boxes, signal tables, page header, and footer now render correctly
- Confirmed Docker dashboard healthy after rebuild on port :8501
- All project docs, CLAUDE.md, session-checklist, ADR-007, and memory updated
- 131/131 tests passing throughout
- Next: Phase 1D — Plotly Dash charting view (`:8502`)

---

## 2026-06-18 — Session 7: Dashboard tweaks + Phase 1D planning

- Fixed HUD "Momentum Vectors" mislabeling: renamed to **Force Scores** (current composite Z-score level that determines the regime quadrant) + added separate **Momentum** metric (month-over-month Δ in composite score — true rate of change)
- Added **📚 Methodology Guide** to sidebar: collapsible reference covering Z-score, percentile, Growth/Inflation Score composition (with signal tables and weights), Confidence, Disequilibrium, lead/lag classification, quality badges, and Dalio's four seasons
- Added **"About this lens"** description line inside each accordion — explains what each lens measures, which signals feed the composites, and weighting rationale
- Created **ADR-007** (`docs/decisions/ADR-007-charting-architecture.md`): documents decision to build Phase 1D as Plotly Dash on :8502; Option B (FastAPI + TradingView Lightweight Charts) deferred with skeleton committed
- Updated CLAUDE.md, session-checklist, project docs with Phase 1D plan
- 131/131 tests still passing; dashboard container confirmed healthy
- Next: Phase 1D — Plotly Dash charting view

---

## 2026-06-18 — Session 6: Phase 1C — Streamlit Dashboard

- Wired Telegram `Stop` hook into `~/.claude/settings.json` (bot already authorized; Telegram was the existing notification mechanism, not Signal)
- Shipped Phase 1C end-to-end: full `dashboard/app.py` rewrite (~380 lines) with HUD, 4-quadrant Plotly scatter + 12-month trail, What Changed feed, Cross-Signal Conflict panel, Geopolitical-Risk Overlay placeholder (WGI deferred per G-03), accordion drill-downs for all 10 lens groups, per-signal sparklines (SVG), percentile color badges, quality badges (proxy/stale/no-vintage/low-hist), causal linkage tooltips (via HTML `title` attribute), data-quality log
- Added `tests/test_dashboard.py`: 39 tests (35 unit + 4 integration) — all passing; total suite 131 tests
- Docker acceptance gate passed: `docker compose up dashboard` serves on :8501; health endpoint returns HTML
- Current regime: Stagflation — Growth=−0.05 / Inflation=+0.31 / Confidence=45%
- Next: Phase 2 — Eurozone rollout (first non-US country binding)

---

## 2026-06-18 — Session 5: Phase 1B — Composites Engine

- Merged `codex/code-review-fixes` → `main`; all 8 code review findings closed, 79 tests passing
- Shipped Phase 1B end-to-end: `indicators/composites.py` (Growth Score, Inflation Score, Regime Quadrant + Confidence, Disequilibrium Score); `CompositeSnapshot` Pydantic model; `composites` DuckDB table with idempotent upserts; Pass 5 in `pipeline.py`; 13 new tests (91 total passing)
- Pipeline verified: 59/59 signals OK, 558 monthly composite snapshots stored (full US history)
- Key finding: 2022 engine labels are "Inflationary Boom" (not "Stagflation" as spec assumed) — employment Z-scores stayed strongly positive all year; Stagflation label correctly emerges from Mar 2023 when growth Z-scores turn negative. Spec acceptance gate updated to reflect this.
- Current regime (Jun 2026): Stagflation — Growth=−0.05 / Inflation=+0.31 / Confidence=45% / Diseq=0.82
- Next: Phase 1C — Streamlit dashboard (4-quadrant scatter, HUD, accordion lenses A–I)

---

## 2026-06-18 — Repository-wide code review remediation

- Resolved all eight findings in `code_review/2026-06-18-repository-code-review.md`
- Fixed ingestion failure exit status, country/provider metadata, PMI equilibrium, non-finite values, IMF forecast handling, future-date cleanup, and atomic DuckDB upserts
- Added the deferred Lens I climate slot and a read-only Streamlit status entry point
- Expanded regression suite from 73 to 79 tests; all pass
- Live pipeline verified: 59/59 OK, 0 empty, 0 errors, 0 sanity warnings, 0 future-dated rows
- Full `docker compose up --build -d` acceptance run passed: pipeline exited 0 and dashboard served on port 8501
- Next: Phase 1B composites engine (Growth Score, Inflation Score, Regime Quadrant, Disequilibrium Score)
- Blockers: None

---

## 2026-06-18 — Session 4: Phase 1A-iii Fiscal / IMF lenses

- Shipped Phase 1A-iii end-to-end: 9 new bindings (FRED: TFP, PPI broad, household debt/GDP, corporate debt, federal deficit, interest payments; WB: govt revenue % GDP; IMF: primary balance, structural balance); 13 new tests; suite 73/73 passing
- Added `fetch_imf_series()` to `loader.py` using IMF Datamapper REST API (no auth, ISO-3 country codes, forecast-year filter, parquet cache, tenacity retry)
- Added Pass 3 (IMF) and renumbered Derived as Pass 4 in `pipeline.py`; header updated to reflect all four providers
- Pipeline verified: 59/59 OK, 0 empty, 0 errors, 0 sanity warnings; `growth.tfp` (RTFPNAUSA632NRUG) was last unresolved ⚠ VERIFY — now confirmed and ingesting
- Key finding: IMF Datamapper uses ISO-3 codes (USA not US); `fiscal.structural_balance` last obs is 2026-12-31 (in-year WEO projection) — flagged in `notes`
- Next: Phase 1B — composites engine (Growth Score, Inflation Score, Regime Quadrant, Disequilibrium Score)

---

## 2026-06-18 — Session 3: Phase 1A-ii World Bank lenses

- Shipped Phase 1A-ii end-to-end: `fetch_wb_series()` (direct REST, parquet cache, tenacity retry) in `loader.py`; WorldBank Pass 2 in `pipeline.py`; 13 new bindings in `us_bindings.yaml`; 9 new tests; suite 60/60 passing
- Pipeline verified live: 50/50 OK, 0 empty, 0 errors, 0 sanity warnings — Lens F (external/trade), Lens G (capital/currency), Lens A supplement (R&D), Demographics all ingesting cleanly
- Key finding: WGI `.EST` governance series confirmed deleted/archived from WB v2 API — 5 deferred slots created; resolution requires WGI bulk CSV download from WGI portal
- Decided: use direct `requests` for World Bank API (not `wbgapi`, which produces JSON-decoding errors in this environment)
- Updated `docs/project_plan.md`: Phase 1A-i/ii marked ✅ complete, all verified series IDs updated ✓/⛔, Appendix A reorganized; added project_plan update step to session-close checklist
- Next: Phase 1A-iii (IMF/OECD fiscal lenses) — verify FYFSD/FYOINT, GGXONLB/GGSB, bind GC.REV.XGRT.GD.ZS, PPIACO, HDTGPDUSQ163N, BCNSDODNS

---

## 2026-06-18 — Session close
- Shipped Phase 1A-i end-to-end: FRED loader, transform, normalize, DuckDB store, pipeline orchestrator, 51 tests (all pass)
- Pipeline verified live against FRED: 37/37 signals OK, 0 errors, 0 sanity warnings; ~85k rows in DuckDB
- Fixed spec error: Philly Fed PMI series ID `GACDISA066MSFRBPHI` → `GACDFSA066MSFRBPHI`; documented ICE BofA FRED truncation (HY spread 3yr history only, G-10)
- ADRs 001–005 decided and written; G-01 through G-10 tracked in session-checklist.md
- Next: Phase 1A-ii (World Bank lenses) or Phase 1B (composites engine) — user's choice at next session open

---

## 2026-06-18 — Session 2: Phase 1A-i Code Complete

**Done:**
- Scaffolded full project structure: `indicators/`, `store/`, `config/`, `tests/`, `dashboard/`
- `requirements.txt`, `Dockerfile`, `docker-compose.yml`
- `indicators/models.py`: Pydantic `CountryBinding` + `Signal` contract
- `indicators/loader.py`: FRED fetcher with parquet disk cache, tenacity retry, TTL-based freshness
- `indicators/transform.py`: YoY%, level/spread pass-through, momentum period maps
- `indicators/normalize.py`: Z-score, percentile, direction, staleness, `build_signals`, `sanity_check`
- `indicators/pipeline.py`: full orchestrator (Pass 1 FRED, Pass 2 derived series, sanity gates, `--refresh`/`--latest` flags)
- `store/store.py`: DuckDB schema init, idempotent upsert, `query_latest`, `query_series`
- `config/us_bindings.yaml`: 29 FRED bindings (lenses A–E + Master, all `verified: true`) + 4 derived
- `config/composites.yaml`: Growth/Inflation Score weights (ADR-005), disequilibrium forces
- **51 tests written and passing** (test_transform, test_normalize, test_store)
- Pushed to https://github.com/benito334/indicators-machine

**Pipeline run results (2026-06-18):**
- 36/37 FRED OK, 1 empty (GACDISA066MSFRBPHI — bad ID in spec), 0 errors, 0 sanity warnings
- Fixed PMI proxy ID: `GACDISA066MSFRBPHI` → `GACDFSA066MSFRBPHI` (one char off)
- After fix: **37/37 signals OK, 0 empty, 0 errors, 0 sanity warnings**
- Discovered: all ICE BofA series on FRED truncated to 2023-06-19 (licensing change). HY spread has only 787 obs. Documented as G-10. BAA10Y (since 1986) is the primary long-history credit spread.
- DuckDB now has signals across: lenses A–E + Master, 33 FRED series + 4 derived
- Total rows: ~85,000+ time-series observations stored

**Current signal state (as of 2026-06-17/18):**
- Growth: cooling (payrolls +0.3% YoY P=22%, capacity util 76% P=23%)
- Inflation: above target (core PCE 3.3% YoY P=72%, core CPI 2.8% P=58%)
- Policy: mild restriction (real fed funds +0.81%, real 10Y yield +2.14% at P=88%)
- Credit: very loose (Baa spread 1.55% at P=9%, HY spread 2.63%)
- Regime: Disinflationary Slowdown / mild Stagflation border

**Next session:**
- Phase 1A-ii: add World Bank lenses (F external, G capital/currency, H governance, demographics)
- OR begin Phase 1B composites engine if user prefers to see the regime quadrant first

**Blockers:** None — pipeline is fully operational.

---

## 2026-06-18 — Session 1: Project Bootstrap

**Done:**
- Read and analyzed `docs/project_plan.md` (Master Technical Specification v2).
- Identified key weaknesses and gaps in the plan (see session-checklist.md).
- Created all project documentation:
  - `CLAUDE.md` — authoritative session guide with locked-in paths, rules, stack, phase map
  - `worklog.md` — this file
  - `session-checklist.md` — per-session pre/post checklist + open items
  - `docs/decisions/ADR-001-duckdb-signal-store.md`
  - `docs/decisions/ADR-002-apscheduler-orchestration.md`
  - `docs/decisions/ADR-003-alfred-vintages-deferred.md`
  - `docs/decisions/ADR-004-philly-fed-pmi-proxy.md`
  - `docs/decisions/ADR-005-composite-weights.md`

**Locked in (confirmed by user):**
- Data path: `/mnt/data/project_data/finance/indicators_machine/`
- DB path: `/mnt/data/db/finance/indicators_machine/`
- Rule: Dockerize everything
- Rule: Use existing tools/packages before building from scratch

**Next session should start with:**
- Phase 1A: scaffold directory structure, `requirements.txt`, `docker-compose.yml`, `.env.example`
- Define Pydantic models for `IndicatorConcept`, `CountryBinding`, `Signal` in `indicators/models.py`
- Write DuckDB schema in `store/store.py`
- Write FRED fetcher with cache in `indicators/loader.py`

**Blockers:**
- `FRED_API_KEY` must be provisioned before ingestion can run. Check with `echo $FRED_API_KEY`.
- `EIA_API_KEY` required for commodity data (Lens B / crude oil) — lower priority, Phase 1A can proceed without it if crude oil is fetched via FRED `DCOILWTICO` (no key needed via FRED).

---

---

## 2026-06-23 — Session: Weight Audit enhancements + Weight History page

**Done:**

### Bug fixes
- Fixed blank graphs on Weight Audit page (`/weight-audit`): two separate Plotly bugs:
  1. `figure_layout()` returns `margin`/`xaxis`/`yaxis` keys — callers were passing duplicates → split into two sequential `update_layout()` calls across all four chart functions
  2. Plotly rejects 8-digit hex colors (`#RRGGBBAA`) — added `_hex_alpha()` helper to convert to `rgba(r,g,b,a)` format

### New features shipped
1. **Re-run button** on Weight Audit page — triggers force balance, correlation heatmaps, and Monte Carlo on demand without a page reload
2. **Importance Editor (Section 4)** — editable DataTable showing all signals for the selected country with importance, tier, base_share, quality_factor; live G/I ratio preview recalculates as values are edited; Reset and Save buttons; Reason text input before save
3. **GDP-Regression Calibration (Section 5)** — `indicators/calibrate.py`: OLS of each growth signal's quarterly Z-score against `{cc}.master.gdp_real`; positive betas normalized to contribution shares then scaled to [0.10, 0.95]; β ≤ 0 signals get no recommendation (Option B — user decides); results table shown in UI with recommended importance and Δ from current; "Apply Selected to Editor" button populates editor for review before save
4. **Weight Change Log** — `weight_change_log` table added to DuckDB (log_id, changed_at, country, signal_id, basket, old/new importance, delta, reason, source); every save from the editor writes a row; `log_weight_changes()`, `query_weight_change_log()`, `update_weight_change_reason()` in `store/store.py`
5. **Weight History page** (`/weight-history`) — new `dashboard/weight_history.py`; table of all importance changes, editable Reason column, Save Notes button, country filter; wired into charting.py nav and `_PAGE_MAP`
6. **Methodology page** — Section 12 expanded with importance tier table, GDP regression calibration subsection; row in deferred table updated (OLS calibration now live)

**Files changed:**
- `indicators/calibrate.py` — NEW
- `store/store.py` — `weight_change_log` DDL + 3 new functions
- `dashboard/weight_audit.py` — Re-run store, editor section, calibration section, `_hex_alpha()`, split `update_layout()` calls
- `dashboard/weight_history.py` — NEW
- `dashboard/methodology.py` — expanded Section 12, updated Section 13 deferred table
- `dashboard/charting.py` — import + nav link + page function + `_PAGE_MAP` entry for weight-history

**Current state:** 353 tests pass. 119 signals (63 US + 34 EZ + 22 KR). Docker rebuilt clean, :8502 HTTP 200.

**Next session:** Phase 2 Japan rollout (`config/countries/jp_bindings.yaml` + `jp_composites.yaml`). BEA refresh available after 2026-06-26.

---

## 2026-06-24 — Bug fixes: Monte Carlo graphs + Importance Editor copy button

**Done:**
- **Monte Carlo blank graphs fixed**: `titlefont` is a deprecated Plotly v4 property — removed in v5. Two axes in `_mc_scatter` (Growth Score, Inflation Score) and the Y-axis in the force balance bar chart used it, causing a silent `ValueError` that killed the callback. Fixed to `title={"text": ..., "font": {...}}` in all three places.
- **Importance Editor copy button**: `dcc.Clipboard` added to Section 4 header (top-right). Content callback converts table rows to TSV (Signal, Basket, base_share, importance, Tier, quality_factor, Raw Weight) on every table update — paste directly into a spreadsheet. Content updates automatically on country switch, reset, or applied calibration.

**Files changed:** `dashboard/weight_audit.py`

---

## 2026-06-24 — Threshold-Based Regime Classifier (Phase 3 analysis tool)

**Done:**
- `indicators/regime_classifier.py` (new): standalone `classify_regimes_threshold()` function — 5-dimension hard Z-score threshold classifier (Growth · Inflation · Rate · Credit · Volatility). Signal map per country (US/EZ/KR) with inversion flags for spread-based credit signals. Independent rolling Z-score (not from pipeline's pre-computed column). GDP quarterly fill: forward-fill or decay-weighted (Z-score decays toward 0 between releases with configurable half-life). VIX loaded from raw parquet cache or FRED fetch (US only, gracefully skipped if unavailable).
- `dashboard/regime_classifier_page.py` (new): full Dash page at `/regime-classifier`. Config panel: lookback dropdown (5/10/20yr), upper/lower threshold inputs, GDP fill toggle (ffill/decay) with conditional halflife slider, credit signal dropdown (BAA Spread / Gov Debt-GDP), Run button. Three result sections: (1) dimension flag heatmap, (2) threshold quadrant step chart, (3) comparison vs composites engine with agreement rate metric.
- `dashboard/charting.py`: new "Analysis" nav group + import + page function + `_PAGE_MAP` entry.

**Signal map:**
- US: growth=`us.master.gdp_real`, inflation=`us.inflation.cpi_headline`, rate=`us.policy.real_fed_funds`, credit=[`us.premium.credit_spread_corp`|`us.credit.gov_debt_gdp`], volatility=VIXCLS
- EZ: growth=`ez.master.gdp_real`, inflation=`ez.inflation.cpi_headline`, rate=`ez.policy.real_yield_10y`, credit=[`ez.credit.btp_bund_spread`|`ez.credit.gov_debt_gdp`]
- KR: growth=`kr.master.gdp_real`, inflation=`kr.inflation.cpi_headline`, rate=`kr.policy.yield_10y`, credit=`kr.credit.gov_debt_gdp`

**Smoke test (US, 10yr lookback):** 517 months 1983–2026. 2020-04 → Disinflationary Slowdown ✅, 2021-06 → Inflationary Boom ✅. EZ: 336 months.

**Next session:** Phase 2 Japan rollout. BEA refresh after 2026-06-26.

---

## 2026-06-24 — Regime Classifier: placeholder fix + guidance doc reorganisation

**Done:**
- Fixed blank graphs on `/regime-classifier` page: `dcc.Graph` components initialise with `_placeholder_fig()` ("Click ▶ Run Classifier to generate results") instead of empty white boxes. Chart callbacks also return placeholder instead of `PreventUpdate` when store is empty.
- Reorganised `docs/Guidance/`: consumed guidance docs moved to `docs/Guidance/Used/`; `Backtesting_Indicator_imporvements.md` is the active working document for Phase 3.

**Files changed:** `dashboard/regime_classifier_page.py`, `docs/Guidance/` structure.

---

## 2026-06-28 — Global Overview Cycle Health Index

**Done:**
- Added Cycle Health columns to `/overview`: raw index, debt-adjusted weighted index, and interpreted cycle stage.
- Implemented browser-local Cycle Health config modal for weights, debt target, and stage thresholds.
- Direct nominal GDP growth is used when available; otherwise the Overview uses `real GDP growth + headline inflation` as a display proxy so EZ/KR can participate.
- Added focused tests for the Cycle Health math and Overview route rendering.
- Follow-up: added Methodology documentation for the Cycle Health formulas/defaults and a config-modal clipboard button that copies the current settings.
- Follow-up: Overview table values are now clickable and open a time-series modal. Standard cells plot their underlying DB signal history; CHI cells plot dynamically computed raw/debt-adjusted history using the active browser config.
- Follow-up: CHI v2 implemented from feedback — raw formula now uses real GDP growth; debt-adjusted CHI separates public/private debt gaps with public-only fallback; thresholds default to adaptive `k × σ`; component contributions support age-based freshness decay.

**Validation:** `python3 -m pytest` → 360 passed; follow-up `python3 -m pytest tests/test_charting.py` → 77 passed.

**Next:** Review the default weights/thresholds against Phase 3 back-test scenarios, then decide whether to persist country-specific defaults in YAML.

---

## 2026-07-05 — Ray Dalio AI review process (systematic, all 5 forces + Debt Stress + CHI)

**Done:**
- Started a new process reviewing the project against a "Ray Dalio" AI persona (digitalray.ai, browser-driven) to sanity-check the methodology from a genuine macro-cycle framework perspective. New tracking doc: `docs/Guidance/ray_dalio_review_log.md` — coverage matrix, session log, and a 23-item triaged punch list (ready-to-implement / needs-design-pass / needs-data-feed-check / acknowledged-no-build).
- Discovered and mined a large amount of pre-existing informal review history in the same tool (growth/inflation composite critique, historical ground-truth validation against 1990s/2008/QE episodes).
- Systematically reviewed all 5 forces, the Long-Term Debt Stress composite, and the Cycle Health Index, each landing on a concrete, implementable plan (see log for full detail per area).
- Biggest structural output: a complete, ordered 7-step regime-classifier threshold algorithm (country-vol-scaled baseline → credit multiplier → volatility multiplier → multiplicative combination → classify → correlation-divergence overlay), with worked Python pseudocode and a numerical example — supersedes 4 previously-open punch items.
- Confirmed two free data feeds via direct FRED series-search (not guessed): `DRSDCILM` (SLOOS loan-demand, pairs with existing `DRTSCILM` lending-standards signal) and `FEDTARMD` (FOMC dot-plot median, a forward-guidance proxy since true Fed-funds-futures data isn't free).
- Nothing implemented yet — this was the review/planning pass only.

**Next:** Work through the 23-item punch list; start with the ready-to-implement items (#1, #2, #3, #7, #13, #16, #17, #19, #21, #22, #23), then resolve remaining data-feed checks (#15, #18).

---

## 2026-07-05 — Ray Dalio review punch-list implementation (part 1: 8 of 11 items)

**Done:**
- **#1 Growth weights**: ran `indicators/calibrate.py` GDP-regression, applied recommended importances to all 9 cyclical growth signals (e.g. job_openings 0.85→0.25, real_pce 0.65→0.95), logged to `weight_change_log` (source="regression").
- **#2 Inflation breakevens**: new derived signal `inflation.breakeven_avg` (mean of T5YIE/T10YIE) replacing the two separate breakeven slots in the composite; both raw signals still exist individually.
- **#3 Crude oil rolling avg**: found already implemented from an earlier session (`pre_smooth_window: 7`) — no work needed.
- **#7 Growth productivity trend**: added `growth.productivity`/`growth.tfp`/`growth.rnd_intensity` to the growth composite at modest weights (previously excluded as "structural frequency" even though the signals already existed).
- **#16/#17/#19 Debt Stress**: documented a sparse-country minimum-viable 3-component fallback in `longterm_stress.yaml`; implemented Ray's dynamic stock/flow weighting formula (`_dynamic_group_weights()`); added linear interpolation for single missing annual observations (`_fill_missing_annual_via_interpolation()`).
- **#21/#22 Cycle Health Index**: conditional growth/rate/inflation weight rule (`_conditional_chi_weights()`) and a nominal/real policy-rate toggle (`use_real_policy_rate`, defaults nominal).
- **Data-feed checks resolved but not yet coded**: #8 (`FEDTARMD` FOMC dot-plot as forward-guidance proxy — no free futures feed exists) and #9 (`DRSDCILM` SLOOS loan-demand series confirmed free, pairs with existing `DRTSCILM`).
- **#13 Volatility restructure — data constraint found**: FRED only has daily `SP500` for the US (from 2016-07), and just *monthly* share-price indices for EZ (`SPASTT01EZM661N`) / KR (`SPASTT01KRM661N`) — no daily equity feed for EZ/KR, so true realized vol isn't feasible there without a lower-resolution monthly-return proxy. Architecture work still pending.

**Validation:** `python3 -m pytest` → 370 passed, 1 pre-existing unrelated failure (`test_compare_raw_vs_processed_level_signal`, a pandas dtype bug, reproduces on main without any of these changes — spawned as a separate task). Pipeline re-run clean after each change.

**Remaining:** #13 (Volatility restructure, needs a data-feed decision given the constraint above) and #23 (the full regime-classifier threshold algorithm — the biggest, most invasive remaining change).

---

## 2026-07-05 — Ray Dalio review punch-list implementation (part 2: Volatility restructure, #13)

**Done:**
- **New signals**: `volatility.equity_index` (US: `SP500` daily; EZ: `SPASTT01EZM661N` monthly; KR: `SPASTT01KRM661N` monthly) and `volatility.vix` (US only, `VIXCLS`). All confirmed via direct FRED series-search, not guessed.
- **New derived signal**: `volatility.realized_vol` — annualized rolling std of log returns on the equity index (21-day/√252 window for US daily data, 12-month/√12 window for the EZ/KR monthly proxy). `indicators/pipeline.py::compute_derived`.
- **Volatility is now a real basket composite** (`volatility_score`/`volatility_momentum`), matching the same architecture as Growth/Inflation/Rate/Credit: added to `models.py`, `store.py` (schema + migration), `composites.py` (validation, scoring, momentum, weight_audit), `charting_data.py::load_composite_component_status` and `load_composite_history`. US basket = realized_vol (importance 0.70) + VIX (importance 0.90, bonus weight); EZ/KR = realized_vol only (single-signal, `quality_factor: 0.70`, low-coverage/directional-only, documented in each composites.yaml).
- **Removed the old ad-hoc raw-VIX path**: deleted `_vix_df()`/`_signal_rows()`/`_dash_td()` (dead code) from `signals_page.py`; `force_detail.py`'s `/signals/volatility` page dropped its special-case branch and now uses the same generic composite-driven banner/table/chart path as every other force.
- **Bug found + fixed along the way**: `load_composite_history()` in `charting_data.py` had an explicit column SELECT list that omitted the (pre-existing) `rate_score`/`credit_score` columns from ever showing up correctly if they'd been missing too — added `volatility_score`/`volatility_momentum` to that list. Also fixed a `PermissionError` in `loader.py`'s cache-write step (pre-existing root-owned cache file blocking a legitimate new-binding fetch) by logging a warning and proceeding without caching instead of crashing the pipeline.
- **New doc**: `docs/Guidance/data_source_wishlist.md` — running checklist of data we want but don't have a free source for yet (daily EA/KR equity index, MOVE-equivalent, credit-spread vol, ECB/BOK loan-demand series, debt-service-to-consumption/investment denominators), with guidance for the next country rollout (Japan).
- **Verified live in the dashboard** (rebuilt `docker compose build/up charting`): `/signals/volatility` and `/signals` overview both render the new composite correctly (Force Z, momentum, weight columns, 4-panel stacked chart with composite Z + momentum + per-signal dual panels) for US; confirmed EZ/KR ingest correctly too (EZ currently shows `NaN` for the latest few months because the OECD source lags beyond the monthly forward-fill window — same expected staleness behavior as other known-lagging EZ signals, not a bug).

**Validation:** `python3 -m pytest` → 377 passed, 1 pre-existing unrelated failure (dtype bug, already tracked separately). Full pipeline re-run clean across US/EZ/KR.

**Next:** #23 — the full regime-classifier threshold algorithm (the last, most invasive punch-list item).

---

## 2026-07-05 — Ray Dalio review punch-list implementation (part 3: regime-classifier algorithm, #23 — punch list complete)

**Done:**
- Implemented `compute_dynamic_thresholds()` in `dashboard/charting.py` — Ray's full 7-step algorithm: country-vol-scaled baseline (24-mo rolling σ of growth_score/inflation_score, look-ahead safe), credit-tightness multiplier (inflation threshold only), volatility multiplier ("vol of the vol" — 12-mo rolling σ of the composite's own Z-score history, both chips), multiplicative combination, and a correlation-divergence overlay (diagnostic only, N=3-month lookback).
- Opt-in, not a silent behavior change: added a "Use dynamic thresholds (Ray Dalio algorithm)" checkbox to the existing Regime Thresholds modal (`regime-threshold-store`). Off by default — every existing user sees identical behavior unless they explicitly turn it on. Wired into both the Regime History full-history chart loop and the single-row regime-info card (`update_regime_info` callback), so switching modes changes the actual classification, not just a display label.
- Verified live: enabling the toggle visibly changes the Growth/Inflation regime band pattern on `/regime-history`, and the header threshold display now shows a "DYNAMIC" badge. Confirmed via direct query that the computed thresholds are real and time-varying (US: dyn_gz ranges ~0.06–0.95, dyn_iz ~0.03–0.64 over history; credit_adj 1.0–1.07; vol_adj 1.0–1.12; divergence_flag fires ~33% of months) — no degenerate/constant values.
- Added 5 focused unit tests for `compute_dynamic_thresholds` (fallback on short history, credit-tightness affecting inflation only, volatility widening both chips, divergence-flag timing, graceful handling of a missing credit_score column).
- **Punch-list item #23 was the last one of the original 23** (plus #24, the wishlist doc) — all are now either implemented or explicitly deferred with a documented reason (data-feed gaps for #10/#15/#18, out-of-scope for #12).

**Validation:** `python3 -m pytest` → 382 passed, 1 pre-existing unrelated failure (dtype bug, tracked separately). Verified live in the rebuilt dashboard.

**Next:** Punch list is done. Remaining open items are all explicitly deferred (data-feed research per `docs/Guidance/data_source_wishlist.md`, or out-of-scope per the Allocation Layer boundary). Divergence-flag UI badge is a small nice-to-have follow-up, not blocking. BEA Q1 2026 refresh still pending per `session-checklist.md`.

---

## 2026-07-05 — Roadmap Phase A complete + Phase G backtest (G1+G2)

**Done:**
- **Roadmap created + Phase CC added**: `docs/Guidance/ray_framework_roadmap.md` — phased plan (A–H) for the 5-layer Ray-framework dashboard; Phase CC = country command center (single synthesis front-door page per country; v1 is assembly-only from existing data, closes the divergence-badge follow-up).
- **Phase A2**: `credit.loan_demand` (FRED `DRSDCILM`, SLOOS demand side) added to the US credit basket — pairs with supply-side lending standards (Ray #9). 139 quarterly obs, verified live.
- **Phase A1**: the assumed forward-guidance feed (`FEDTARMD` dot-plot) proved non-viable (future-dated forecast snapshot, no Z-scoreable history). Asked Ray; he chose a derived `policy.rate_expectations` = `yield_2y − fed_funds` ("money is made by identifying change rather than forecasting it"). Built at CONTEXT tier (0.45, inverted), 11,625 daily obs; keep/weight decision deferred to Phase G3 per his caveat.
- **Phase G1 — point-in-time backtest engine** (`indicators/backtest.py`): expanding-window shift(1) Z-scores (no statistical look-ahead), PIT composites (momentum tilt/age decay deliberately omitted — documented), classification via the production `_classify_regime`/`compute_dynamic_thresholds` (single source of truth). 9 unit tests.
- **Phase G2 — scenario scoring**: 8 named scenarios 1990→2024 (history starts 1980-81, so no 1970s replay). Results: wrong-direction ≈ 0% everywhere (direction validation PASSED with zero look-ahead); dynamic thresholds ≥ fixed (won 1990-91 recession 50→88% strict and late-90s boom 33→54%, tied the rest, cost 1 mislabeled month in 48). Verdict: supportive of dynamic, keep opt-in until G3. Design insight: the ΔMoM gate parks fast V-shaped episodes (COVID 33% strict) in Transition during the rebound — exit-condition asymmetry is a future refinement candidate.
- Report: `docs/backtests/pit_regime_backtest_us.md` (regenerate with `python -m indicators.backtest`).

**Validation:** `python3 -m pytest` → 397 passed, 1 pre-existing unrelated failure (dtype bug).

**Next (per roadmap sequence):** Phase B (promote productivity trend) → Phase CC (command center v1) → Phase C (debt-cycle stage classifier). G3 (ALFRED vintage replay + asset-outcome tests incl. rate_expectations validation) stays open.

---

## 2026-07-05 — Roadmap Phase B: productivity trend as a first-class read

**Done:**
- `productivity_score`/`productivity_momentum` composite (Ray's third big force) added end-to-end: models/store (columns+migration), composites engine, per-country configs (US 3-signal basket: labor productivity 0.80 / TFP 0.45 / R&D 0.30; EZ+KR single-signal R&D-only low-coverage), charting_data SELECT + component-status loop.
- UI: sixth "Productivity Trend" section on /signals (teal #3FBFB0) + full force-detail page /signals/productivity with the cyclical Growth Z overlaid (dotted) on the trend composite panel — the "cyclically strong but trend-decelerating" glance. Subnav link added.
- Methodology §7 basket table + revision-log entries (Phase A + B). 2 new composite tests.

**Validation:** 399 passed, 1 pre-existing failure. Pipeline populates all three countries (EZ/KR trend read ends 2023 — annual R&D source aging out honestly). Verified live.

**Next:** Phase CC — country command center v1 (assembly-only front-door page; closes the divergence-badge follow-up).

---

## 2026-07-05 — Roadmap Phase CC: country command center v1 (new default landing page)

**Done:**
- `dashboard/command_center.py` (new): one synthesis page per country answering "where is this country, on all three clocks, and what's changing." Routes `/` (now the default landing page — was Chart Overlay) + `/country`; "🎛 Command Center" nav entry at the top of Overviews.
- Cards (each links to its detail page): regime strip (Growth/Inflation chips via the production `_classify_regime`, honoring the threshold store *including dynamic mode* — computes `compute_dynamic_thresholds` and uses the latest dyn_gz/dyn_iz when dynamic is on; confidence, diseq, DYNAMIC badge); short-cycle levers (Growth/Inflation dials with Δ + momentum %, Credit conditions = composite + SLOOS supply-tightening/easing + loan-demand reads, Policy stance = rate_score accommodative/restrictive + 2y−funds hikes/hold/cuts read); long-term debt cycle (Debt Stress score + n/7 components, DSR Z + % of income + direction — "the earliest stress signal"); trend & big cycle (productivity trend with above/below-cycle read); what-changed top-8 Z movers (reuses `load_change_feed` + `_what_changed_children`).
- **Divergence badge live** — amber DIVERGENCE chip with tooltip when growth/inflation Z-scores have opposed signs for 3+ consecutive months (closes the open review-log #23 follow-up; the flag was computed but never surfaced).
- CC2 placeholder cards (dashed border, "planned") for Phase C cycle *stage* and Phase D big-cycle *order*.
- Lazy imports from `dashboard.charting` inside the callback (avoids circular import); module-level `@callback` pattern matching signals_page.
- `tests/test_command_center.py` (8 tests: layout, all cards present, drill-down hrefs, no_update on other pages, dynamic badge, EZ/KR no-crash, route registration). Methodology §15 revision-log row (also fixed a duplicated-row bug in the §15 copy-text table). Roadmap Phase CC marked ✅.

**Validation:** 407 passed, 1 pre-existing failure (dtype). Docker rebuilt; verified live in browser at `/` and `/country` — US renders all cards, card click navigates to `/signals/credit`, nav highlights Command Center; EZ/KR verified via direct callback tests.

**Next (per roadmap sequence):** Phase C — long-term debt-cycle *stage* classifier (calibrated against Phase G output; upgrades its CC placeholder card). Then Phase D research spike in parallel.

---

## 2026-07-05 — Roadmap Phase C: long-term debt-cycle stage classifier

**Done:**
- `indicators/debt_cycle_stage.py` + `config/debt_cycle_stage.yaml` (every threshold/weight TUNABLE-annotated): classifies leveraging / squeeze / deleveraging / reflation / neutral from 5 feature families — debt/GDP expanding percentile (ranked vs PRIOR history only, no look-ahead) + 3y trajectory (pp/yr), DSR 2y trend, real-rate−real-growth, nominal-growth−yield. Transparent weighted-condition argmax; per-quarter renormalization over available features (EZ/KR honestly run on 4/5 — no free debt-service series); <3 families → no label; 3-quarter rolling-mode smoothing that never carries a label across a data gap.
- Storage/pipeline: `DebtCycleStageSnapshot` model, `debt_cycle_stage_snapshots` DuckDB table (+ upsert/query in store.py), pipeline Pass 7 looping all configured countries.
- Dashboard: Command Center Cycle Stage card now LIVE (stage-colored, confidence + n/5 features, links to /debt-stress); Debt Stress page gained a Long-Term Cycle Stage section (current-stage chip + driving-features readout + colored quarterly stage band + per-stage score chart). Works for US/EZ/KR (stage section renders even where the US-only stress model shows its placeholder).
- Bugs fixed during build: empty pd.Series RangeIndex corrupting the feature-frame index union (EZ/KR produced zero features); resample().last() not reaching the current quarter (annual ratios went NaN at the newest quarters — added extend-to-current-quarter within ffill limit); smoothing carrying a stale label across raw=None gaps; in-progress future quarter emitted as "latest"; Python strftime %q (only plotly supports %q).
- US timeline sanity anchors hit: 1989–91 squeeze (S&L), 1992–95 reflation, 2007 pre-GFC squeeze, 2012–2020 reflation ("beautiful deleveraging"), 2020–23 COVID leveraging. Current reads: US=reflation, EZ=reflation, KR=leveraging.
- 17 new tests (`tests/test_debt_cycle_stage.py`); CC test updated (stage card live, Phase D placeholder remains). Methodology §9 subsection + §15 revision-log row; roadmap Phase C ✅.

**Deferred to G3 (explicit):** stage-threshold calibration against the PIT backtest.

**Next:** Phase D research spike (order-layer data hunt), then E (cross-country view), F (Japan), G3.

---

## 2026-07-05 — Roadmap Phase D: big-cycle ORDER layer (research spike + confirmed subset)

**Done:**
- **D1 research spike** (all feeds verified against provider endpoints, results in data_source_wishlist.md): WB Gini `SI.POV.GINI` ✔ (US 2024 / KR 2021 / JP 2020; EMU aggregate empty; WB v2 API intermittently 400s — retries recover); IMF COFER reserve-currency shares ✔ via the NEW IMF SDMX 2.1 API (`api.imf.org`, legacy dataservices host is dead) — pre-computed quarterly shares `G001.AFXRA.CI_{CUR}.SHRO_PT.Q`, 109 obs 1999→2026, USD 71.2%→57.1%; WB external debt `DT.DOD.DECT.CD` ✘ NULL for all high-income countries; V-Dem/Polity governance + GPR index ✘ no API → manual-load slots.
- **D2 build**: `fetch_imf_sdmx_series()` in loader.py (CSV Accept header, parquet cache, tenacity retry, stale-cache fallback); pipeline Pass 3.5 for `provider: IMF_SDMX` (series_id `"DATAFLOW/KEY"`, ECB convention); Lens J `order.*` bindings — us.order.gini (41.8), us.order.reserve_currency_share (57.1%), ez.order.reserve_currency_share (20.0%), kr.order.gini (32.9). KR reserve share honestly N/A (KRW inside "Other"); EZ Gini deferred (constructed big-4 proxy). 136 signals total. All `lead_lag: structural`, feed no composite.
- **D3**: Command Center Big-cycle position card live-partial — reserve share (level + 12m Δ) + Gini (level + year) + "governance/GPR deferred" note; placeholder retained for countries with neither.
- Wishlist: new ORDER section + A1 rate-expectations entry marked resolved. Roadmap Phase D ✅ (D4 = manual-load governance/GPR remains open). Methodology §15 revision row.

**Next:** Phase E — cross-country / relative-cycle view. Then F (Japan), G3.

---

## 2026-07-05 — Roadmap Phase E: cross-country relative-cycle view

**Done:**
- `dashboard/relative_view.py` (route `/relative`, "🌍 Relative Cycles" nav under Overviews): per-country cards showing all three clocks side by side — regime chips (threshold-store aware incl. dynamic mode, computed per country), debt-cycle stage chip, Growth/Inflation Z + Δ, debt stress, productivity Z, order reads (reserve share / Gini); each card links to the command center.
- Correlation section: 4 heatmaps — growth-score + inflation-score pairwise Pearson correlation over full common history AND last 10y. Month-period alignment (US composites land on the 5th, KR on month-end); <24 common months → NaN, never spurious.
- **The diversification answer as of today**: US–EZ growth correlation 0.86 over the last decade (same cycle in disguise; 0.60 full-history), US–KR 0.53. Inflation correlations 0.84–0.90 everywhere in the last 10y — the 2021–23 global inflation wave dominates; there is currently no inflation-cycle diversification among US/EZ/KR.
- 9 tests (`tests/test_relative_view.py`): correlation identities (±1), NaN on short overlap, start-window filter, day-of-month alignment, full-page render, route registration. Verified live in browser. Methodology §15 revision rows (script-inserted into both tables to avoid the duplicate-row bug pattern). Roadmap Phase E ✅.

**Next:** Phase F — Japan rollout (jp_bindings.yaml + jp_composites.yaml, sparse-country patterns end to end). Then G3, D4.

---

## 2026-07-05 — Roadmap Phase F: Japan rollout (25 signals, 6 composites, stage classifier)

**Done:**
- `config/countries/jp_bindings.yaml` (25 bindings, every FRED series verified via the metadata endpoint with observation ranges recorded per binding) + `jp_composites.yaml` (all 6 forces). Pipeline: **25/25 OK, 0 errors, 0 sanity warnings**; 161 signals total (73 US + 37 EZ + 25 JP + 26 KR).
- **JP data findings** (documented in the wishlist): NO live monthly CPI free — all OECD FRED CPI feeds ended 2021-06, so inflation = IMF WEO annual bridge only (is_proxy, quality 0.70; e-Stat API needs registration = highest-value follow-up). NIKKEI225 is a free DAILY feed → JP volatility is TRUE daily realized vol, US-quality (unlike EZ/KR proxies). Industrial production: index form died 2024-03, live feed is the GYSAM YoY form.
- JP added to `debt_cycle_stage.yaml` (4/5 features) — current stage **reflation** (textbook: r engineered below g at a 206%-of-GDP debt stock). Pipeline Pass 7 moved AFTER the country loop (was staging before new countries ingested).
- Dashboard: country selector enabled (was "soon"), Relative Cycles + Command Center + stage section all render JP; currency label map extended (JPY).
- **The payoff read**: JP inflation correlates +0.03 with US over the last 10y — the only real inflation diversifier among the four economies. JP growth correlates 0.74 with US/EZ.
- Spot-check passed: unemployment 2.5%, 10y JGB 2.65% (post-normalization), gov debt 206.5% (IMF), CA +4.9%, JPY reserve share 5.44%, REER 65.9 (weak-yen era). All vintage_available=false, honest flags.
- 433 tests pass. Roadmap Phase F ✅; wishlist JP section rewritten with results; UK noted as next rollout.

**Not built (honest):** JP Debt Stress composite — model stays US-only pending a JP DSR source.

**Next:** Phase G3 (ALFRED vintage replay + asset-outcome tests) — the last major open roadmap item; then D4 (manual-load governance/GPR).

---

## 2026-07-06 — Roadmap Phase G3: ALFRED vintage replay + asset-outcome tests (Phase G complete)

**Done:**
- `indicators/backtest_g3.py` (run: `python -m indicators.backtest_g3`; report: `docs/backtests/pit_regime_backtest_g3_us.md`): ALFRED full-vintage fetch (`fetch_alfred_vintages`, one call per series via realtime_start=1980/realtime_end=9999, cached `raw_cache/alfred_{id}.parquet`), `VintageSeries.as_known(t)` bisect lookup, `pit_vintage_zscores` (value AND its expanding reference history both from data-as-known-at-t), vintage PIT composites → production classifier → all 8 scenarios × fixed/dynamic vs the G1 final-data baseline. 15/19 basket signals fully replayed (crude oil, breakevens, Philly Fed, WB R&D use final values — market-priced/non-FRED, flagged in report).
- Chip-conditioned forward returns (no information overlap): 558-month bond test (DGS10 duration proxy) — Inflation chip → −10%/yr fwd bond returns vs +5% under Disinflation, the chip carries real information; equity test honest-flagged as tiny (free SP500 ≈ 10y).
- `rate_expectations` IC test: raw IC 0.079, 2Y-level IC 0.245, incremental IC (residualized on 2Y) **+0.153** over 555 months.
- Stage-episode calibration: post-GFC reflation 100%, COVID leveraging 100%, 2007-08 squeeze 50% (modal leveraging — engages late; logged as the one tweak candidate, not tuned on a single episode).
- **Verdicts** (in the report + roadmap): (1) direction validation survives vintage replay — G1/G2 was not revision-look-ahead; (2) **A1 closed: rate_expectations keeps its slot** at CONTEXT 0.45; (3) dynamic thresholds stay opt-in; (4) stage thresholds confirmed except the late squeeze.
- 6 new tests (`tests/test_backtest_g3.py`: as-known semantics incl. future-vintage invisibility, no-overlap forward windows, bond-return sign); backtest.py header updated. **Phase G fully complete.**

**Remaining open (small):** D4 (manual-load governance/GPR), UK rollout, e-Stat JP CPI registration, pre-existing dtype test failure, 2007-squeeze threshold tweak candidate.

---

## 2026-07-06 — UK rollout (Phase 2 continuation): 27 signals, 6 composites, stage classifier

**Done:**
- `config/countries/gb_bindings.yaml` (27 bindings, every FRED/WB/IMF ID verified against provider endpoints with ranges noted) + `gb_composites.yaml` (all 6 forces, KR structure). Pipeline: **27/27 OK, 0 errors, 0 sanity warnings**; 188 signals total (73 US + 37 EZ + 27 GB + 25 JP + 26 KR).
- **GB data findings** (wishlist updated): monthly CPI (headline + core) ends 2025-03 — same OECD cutoff as KR; IMF annual bridge covers; **ONS API (free, unregistered) is the highest-value follow-up**. No daily FTSE on FRED → monthly-proxy volatility (quality 0.70). ILO monthly unemployment is the LRHUTTTT form (LRUNTTTT 400s). Industrial-production index form died 2024-03 (same as JP) — GYSAM YoY form is live.
- GB added to `debt_cycle_stage.yaml` (4/5 features) — **current stage: squeeze, confidence 0.53, the strongest stage read of any country** (gov debt 102% GDP, gilts 4.94% vs real growth +0.9% → r > g, credit composite −1.76). A coherent Ray read for the UK.
- Dashboard: country selector enabled (GB was the last "soon" entry — dropdown is now fully live), Relative Cycles 5-country grid + 5×5 correlation matrices, Command Center + stage section render GB, GBP currency labels.
- Cross-country reads with 5 countries: GB inflation correlates 0.94 with EZ (last 10y) — no diversification there; GB growth 0.51 vs US. JP inflation (+0.03 vs US) remains the only real diversifier.
- Spot-check passed: CPI 3.4% (Mar-25), unemployment 4.9%, gilt 4.94%, gov debt 102.3%, CA −2.4% (the UK's structural deficit), GBP reserve share 4.40%, REER 111. All vintage_available=false, honest flags.
- 440 tests pass. Methodology §15 revision row.

**Next:** China is next in the Phase 2 order (WB/IMF harmonized only — NBS out of scope). Other open tails: D4 manual-load slots, ONS/e-Stat registrations, dtype test failure, 2007-squeeze threshold tweak.

---

## 2026-07-06 — Unification audit (Ray session): windows, taxonomy, confidence

**Ray session** (rulings logged in full in ray_dalio_review_log.md): Q1 lookback windows → rolling everywhere, canonical defaults 48m growth / 96m inflation / 36m policy, user-overridable, cross-country views on ONE uniform window; Q2 taxonomy → four seasons demoted to background shading beyond the ±threshold lines only, explicit "Transition — no clear season" inside the band; Q3 → confidence renamed **Chip Direction Agreement**, split G/I, measured against the chips' headings.

**Done:**
- **Root fix — rolling composite columns were US-only.** The sidebar window sliders silently fell back to full-history for every non-US country. Rolling passes (36/48/60m force + 90/120m inflation) now run inside the pipeline country loop; backfilled for EZ/GB/JP/KR (all 5 countries populated).
- Canonical defaults wired: sliders + localStorage stores default to 48m/90m (Ray ruled 96m — 90m is the existing DB grid point, Δ documented; policy 36m deferred: rate composite has no rolling variants yet, logged).
- **Command Center** now honors both window stores (dials, Δs, chips, dynamic-threshold inputs on windowed columns; "window 48m / 90m" header annotation) and displays **chip agreement G x% · I y%** instead of the legacy confidence.
- **Relative Cycles**: cards + correlation matrices normalized on canonical 48m/90m for every country (Q1b), annotated in the heatmap titles.
- **Regime Map/History**: season shading only beyond ±gz/±iz with a central "Transition — no clear season" label; new threshold-aware `_season_label()` replaces every sign-based quadrant re-derivation (scatter hovers, info card accent, history step row); `_hex_to_rgba` hardened for 3-digit hex.
- **Chip Direction Agreement** on the Regime Map info card: per-force agreement vs the chip heading (inverted signals flipped), G/I sub-line under the headline number; stored legacy `confidence` kept as fallback only.
- 5 new tests (season-label semantics, agreement math, CC window honoring incl. full-history mode, relative canonical windows); 445 total pass.

**Still open:** rate-basket rolling variants (36m policy default), stored `quadrant` column retirement (kept for legacy/backtest compat).

---

## 2026-07-06 — Dynamic thresholds re-paired with the window unification

**Trigger:** user asked how the Ray dynamic-threshold algorithm composes with the audit's rolling windows — the trace found a real seam.

**The bug:** the Regime History chart + regime info card fed FULL-HISTORY `growth_score`/`inflation_score` into `compute_dynamic_thresholds` while classifying the WINDOWED columns. Ray's step 1 scales by the σ of "the composite's own Z-score" — post-audit that is the windowed series, so thresholds were scaled to the wrong distribution. Material: at 48m/90m the correct US values are gz=0.205/iz=0.082 vs the mismatched 0.093/0.116 (growth threshold more than doubles). The CC and Relative pages were already correct (wired during the audit).

**Done:**
- `_dyn_threshold_input(comp, g_col, i_col)` shared helper — every dynamic call site now builds the input from the ACTIVE (windowed or full) columns: regime info card, Regime History chart, scatter, CC, Relative.
- Regime Map in dynamic mode: corner shading, threshold lines, and hover season labels all positioned by the latest dynamic gz/iz on the windowed series (latest-row convention, same as the Regime History hlines) — geometry and labels always agree.
- Regression test: windowed-vs-full dynamic thresholds genuinely differ AND the scatter geometry matches the windowed-input values. 445 tests pass.

---

## 2026-07-06 — Regime Map: dynamic band follows the time step

**Trigger:** user asked whether walking back in time moves the dynamic threshold bounds on the map. It didn't (geometry was pinned to the latest month, inconsistent with the info card's per-row values).

**Done:** selected-index resolution moved above the shading block; in dynamic mode the corner shading + threshold lines are positioned by the SELECTED month's dyn_gz/dyn_iz (on the active windowed columns), so Prev/Next steps move the band to what the classifier used that month. Hover labels are per-row — each history dot judged against its own month's thresholds. Verified: US step 0 → gz 0.205 (calm era, tight); step 60 (COVID-vol era) → gz 1.02/iz 1.13 (wide); fixed mode static at 0.5. 445 tests pass.

---

## 2026-07-06 — User Guide tab: a training course on the Dalio machine

**Done:**
- `dashboard/user_guide.py` (route `/guide`, "🎓 User Guide" nav in Reference): 9-lesson sequential course for someone who knows Dalio's concepts but hasn't operated a live diagnostic — L0 machine-in-one-picture, L1 debt-cycle hook, L2 dials/Z-scores, L3 chips/thresholds/windows/agreement/divergence, L4 Regime Map, L5 stress-vs-stage, L6 productivity/order, L7 diversification, L8 reading routine (daily/weekly/monthly + when-a-chip-flips playbook + scope boundary).
- **Ray pedagogy pass first** (logged in review log): 3 newcomer traps front-loaded as amber callouts (Z≠grade; magnitude≠direction; never the two dials alone); debt-cycle hook moved BEFORE the dial mechanics per his ordering ruling; L0 diagram upgraded with data-source labels, credit feedback loop, adaptive "normal" band (previews dynamic thresholds), order as background shading.
- Live data in every lesson ("On your dashboard right now" green boxes) — country/theme/window/threshold aware, same code paths as the Command Center; Methodology §N links wherever formulas live.
- 3 plotly diagrams: three-lines-and-band machine chart, stage-colored debt-cycle arc with a "you are here" marker, regime-map geography miniature with the live dot.
- 10 tests (Ray's teaching order asserted, traps present, live boxes ≥5, all countries render, page guard, route). Suite 455 passing. Verified live in browser.

---

## 2026-07-06 — UI cleanup: retired pre-Ray surfaces, fixed stale content

**Audit-driven cleanup (user-approved, full A+B scope):**
- **Retired to `archive/`** (with README): the standalone Regime Classifier page + engine (`/regime-classifier` — a second, sign-based 4-season classifier that could contradict the chips; nothing else imported it), the Streamlit :8501 proof (`dashboard/app.py` + its 41 tests — 4-quadrant HUD, legacy confidence), and the TradingView :8503/:8004 SPA (`charting_lc/` — quadrant history, duplicated Chart Overlay). docker-compose is now 2 services (pipeline + charting). The "Analysis" nav group is gone (was only the classifier).
- **Deleted outright:** `config/composites.yaml` (deprecated since 2026-06-22, read by nothing) and the dead `_RQ_MAP` constant.
- **Stale content fixed:** Regime History help panel rewritten to chips/thresholds/windows language (+ User Guide link; the old panel taught sign-based seasons, referenced a step-function chart removed in June, and pointed at the deleted composites.yaml); chart Row 6 relabeled "Direction Agreement (legacy)" with honest hover; footer "Confidence" definition → Chip Agreement; Weight Audit Monte Carlo now classifies trials by the threshold-aware season zones (`_season_label`, static ±0.5) with band-aware shading instead of sign quadrants; CLAUDE.md "What This Project Is" rewritten (three clocks, chips as the rule, seasons as map geography).

**Incident during rollout (resolved):** `docker compose up -d --remove-orphans` started the pipeline service, whose image was stale (June code — 63 US signals, 2 countries, no rate/credit/vol/productivity or rolling columns). Its Pass 5/6 overwrote composites + debt-stress for US/EZ/KR with old-schema output (signals + stage tables unharmed — upsert-only / not in old image). Recovery: stopped charting, re-ran the current pipeline from the host (188 signals, all 5 stages correct, all columns verified restored to exact pre-clobber counts), rebuilt BOTH images so the pipeline image can't lag the code again. **Lesson (worth remembering): `docker compose build` must build all services, not just charting — a stale pipeline image silently rewrites the DB with old formulas.**

**Validation:** 414 tests pass (455 − 41 archived Streamlit tests); MC smoke-tested; Command Center/Regime Map/Guide verified live post-rebuild.

---

## 2026-07-06 — Workbench: TV-style chart studio (replaces Chart Overlay + Data Explorer)

**Done (user-approved design: Plotly-in-Dash, JSON saved views, clean replacement):**
- `dashboard/workbench.py` + `dashboard/workbench_data.py` (route `/workbench`, "📈 Workbench" nav; `/charts` + `/explorer` are legacy routes landing there).
- **Search**: TV-style omnibox ("/" hotkey) over a unified index of all 321 plottable series — 188 signals, 35 composite scores, debt stress, 97 raw FRED cache series (titles from meta sidecars); all-token fuzzy match + country/force facet dropdowns; result rows show flag, label, force chip, span.
- **Charting**: overlay mode (one pane, right-side scale, minimap range slider) and stacked mode (pane-number per pill groups series into shared-X panes; the force-detail crosshair-sync JS reused). Per-series transform pills: Raw · Rebase=100 · % from start · YoY % · Z (stored) — window-anchored rebasing = TV "compare". Pan default, scroll zoom.
- **Inspector drawer** per series (🔍 on the pill): metadata + stats + Observations table with CSV export + Quality/Gaps + Raw-vs-Processed — the whole Data Explorer, docked. Reuses `explorer_data.py` (kept; UI archived as `archive/explorer_page.py`).
- **Saved views**: named layouts in `DATA_DIR/saved_views.json` (deliberately NOT signals.duckdb — dashboard readers + a writer would recreate the DuckDB lock conflict), 4 built-in ★ presets (US Inflation Stack, Policy Rates ×5, US Credit Conditions, The Two Dials), URL deep links `/workbench?view=name` verified live.
- **Retired**: chart-overlay layout + 4 callbacks + series-selector helpers excised from charting.py; `selected-series` store dropped; `date-range` store kept (many readers; None = full history as before). 8 old-UI tests removed; 14 new workbench tests.
- **Bonus fix**: the long-standing `test_compare_raw_vs_processed_level_signal` dtype failure (merge_asof `datetime64[us]` vs `[ns]`) — fixed in explorer_data; **the suite now runs 421 passed with ZERO exclusions** (first time since 2026-06).

**Verified live**: search → add US+JP 10Y, overlay + stacked with pane grouping, save "us vs jp 10y", deep-link reload restores the view.

---

## 2026-07-06 — Workbench: independent-axis overlay (TV multiple price scales)

**Ask:** overlaying series with very different magnitudes (US interest payments vs productivity) flattened the small one against zero on the shared axis.

**Done:** added an `axis: Shared | Independent` toggle to overlay mode (hidden in stacked). Independent puts each series on its own overlaying, auto-scaled y-axis (`yaxis`, `yaxis2`, …), hides tick labels (N scales can't share one label column), switches to `hovermode="x unified"` so the crosshair carries every value, and is a no-op with a single series. Persisted in `wb-config` and saved-view specs; the toggle hides itself in stacked mode via `wb_axis_sync`. 1 new test (`test_overlay_independent_axes`); suite 422 passed. Verified live: interest-payments vs productivity — productivity's COVID spike/collapse/recovery, invisible on the shared axis, is fully legible on independent.

---

## 2026-07-07 — Sovereign-aware debt-cycle stage classifier (Ray Dalio ruling)

**Trigger:** the interest-payments-vs-productivity chart made the sovereign squeeze visually obvious (interest at z=+4.00, pinned to the system Z-cap) — which surfaced a user challenge: the stage classifier reads the US as "reflation" while Ray's public position calls for a major deleveraging. The classifier's mean-of-3-sectors debt-stock feature was diluting a record government debt stock (122.8% GDP, z +1.78) against a genuinely deleveraged private sector (household debt/GDP 68.5%, z −1.54 — a multi-decade low). Same failure mode the G3 backtest flagged (2007 squeeze engaging late): squeeze conditions keyed to gauges that lag the real pressure.

**Consulted Ray** (full session in `ray_dalio_review_log.md`, Session 2026-07-06 (3)) — rulings: (1) two independent stage votes, PRIVATE and SOVEREIGN, headline = worse of the two by severity; (2) debt stock = size-weighted mean of sector percentiles, each sector capped at the 90th percentile ("worst-of without total dilution"); (3) debt-service blend = 70% household DSR / 30% government interest-to-GDP; (4) a refinancing-gap feature (marginal rate − effective rate on the government stock) triggers the sovereign vote's debt-service condition one quarter early once it exceeds +0.75pp; (5) keep the headline as "the mechanism currently operating" — do NOT force-flip it — and add a SEPARATE independent "Sovereign Squeeze" warning flag instead.

**Done:**
- `config/debt_cycle_stage.yaml`: new `sector_model` (cap, service weights, refi threshold, flag conditions, severity ranking) and `sovereign_inputs` (per-country gov debt/interest/revenue/marginal-yield signal bindings) sections, all TUNABLE.
- `indicators/debt_cycle_stage.py`: `_expanding_z_lagged()` (shift-1 expanding Z, no look-ahead), `_sector_stock()` (capped size-weighted percentile + trajectory), `build_sovereign_features()` (gov interest/GDP + Z + trend, gov DSR = interest/revenue + Z, refinancing gap), `_vote()` (shared scoring helper for either vote), reworked `compute_stage_history()`: builds private + sovereign feature frames, scores both, headline = worst-of by severity `{squeeze:3, deleveraging:2, reflation:1, leveraging:0}`, independent squeeze flag.
- `indicators/models.py` + `store/store.py`: `DebtCycleStageSnapshot` and the `debt_cycle_stage_snapshots` table gained `stage_private`, `stage_sovereign`, `sovereign_squeeze`, `feat_gov_interest_z`, `feat_refi_gap` (migration via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, safe on existing DBs).
- Re-ran the classifier for all 5 countries. **US: headline stays reflation (r−g −1.56pp, ngdp−yield +1.62pp are genuinely reflation-shaped — fiscal dominance operating right now) but SOVEREIGN SQUEEZE fires** (refinancing gap +1.81pp, gov-interest Z +1.43, both past threshold) — **and has been continuously True since 2022-Q2**, a multi-year early warning matching Ray's own public timeline, running underneath a headline that correctly still describes the current mechanism. Historical anchors preserved (2006/2009 squeeze episodes, etc). GB/EZ/JP/KR have no private-debt inputs, so headline = sovereign vote unchanged from before (GB stays squeeze) — no regression.
- Dashboard: Command Center Cycle Stage card gets an amber "SOVEREIGN SQUEEZE" badge (tooltip cites the ruling) + a private/sovereign sub-line when the two votes diverge; Debt Stress page info strip shows the same plus 2 new feature readouts (gov-interest Z, refinancing gap); Relative Cycles country cards append a ⚠ to the stage chip.
- 5 new tests (capped/size-weighted percentile via monkeypatched signal loader, expanding-Z no-lookahead, severity ordering, live US flag regression, live GB no-regression) — suite **427 passed, zero exclusions** (up from 422).
- Rebuilt the charting image only (NOT the pipeline — running the pipeline container while charting holds read-only connections was the incident two sessions ago; this session only ran the classifier from the host against the live DB with charting's connections already read-only, no conflict). Verified all three UI surfaces live for US and non-US countries.

**Design note carried forward:** the sovereign VOTE itself can read differently from the SQUEEZE FLAG (e.g. sovereign vote = "leveraging" this quarter while the flag is True) — this is intentional per Ray's Q5 ruling, not a bug: the vote scoring shares the country's macro conditions (r−g, ngdp−yield) across both votes by design, while the flag is built directly from independent thresholds specifically so it can fire ahead of the vote catching up.

---

## 2026-07-07 — China rollout (Phase 2 continuation — 6th economy live)

**Done:**
- `config/countries/cn_bindings.yaml` (32 signals, all endpoint-verified against FRED/WB/IMF/COFER before binding) + `config/countries/cn_composites.yaml` (6 force composites). **220 signals total** (73 US + 37 EZ + 27 GB + 25 JP + 26 KR + 32 CN). All 32 ingested clean: 0 empty, 0 errors, 0 sanity warnings.
- **The data-availability surprises (both directions), all logged in `data_source_wishlist.md`:**
  - **BIS credit is the star**: private (200.8% GDP), household (58.0%), corporate (142.8%) — quarterly, live. CN is the **second country after the US with a real private/sovereign two-vote split** in the stage classifier.
  - **WB external debt fills for China** ($2.42T) — first country in the system where `DT.DOD.DECT.CD` works (wishlist item partially closed).
  - **CNY COFER share confirmed** (1.99%, 2016-Q4→2026-Q1) — CN gets the same external-order read as the US.
  - **All OECD monthly activity feeds are dead** (IP → 2023, CLI → 2024-01, M2 → 2019, quarterly GDP → 2023-Q3, PPI → 2022). The live monthly growth reads are **merchandise exports/imports** (USD, → 2026-04), bound as the growth basket with LNY-noise caveats documented.
  - **No free bond yield at any maturity** — the 3m interbank rate (live) proxies the market rate everywhere, including both stage-classifier spreads (documented is_proxy).
  - Monthly CPI ages out 2025-04 (same OECD cutoff as KR/GB) → IMF annual bridge; no core CPI exists; unemployment is WB/ILO annual-only.
- Stage classifier: CN added to `debt_cycle_stage.yaml` (3 debt components + interbank-rate proxies) and `sovereign_inputs` (household+corporate private vote; no gov-interest series → SOVEREIGN SQUEEZE flag degrades honestly to never firing). **CN = leveraging on BOTH votes** (confidence 0.28, 4/5 features) — textbook: debt/GDP still rising, r−g deeply negative, ngdp above the short rate.
- Composites: 545 monthly snapshots. Latest (2026-05): Disinflationary Slowdown — Growth −0.68 / Inflation −0.77 (the 0.0% CPI deflation read pins inflation Z deeply negative — plausible and the defining China story right now). Growth flips month-to-month on trade YoY noise (documented; the Transition band + momentum gate absorb most of it). Force balance 0.78 OK; no CORR AUDIT flags.
- Spot-checks vs public references: BIS credit ratios, IMF gov debt 99.2%, FX reserves ~$3.4T, GDP $19.6T, FDI collapse to 0.23% GDP, population decline −0.17%, Gini 36.0, COFER 1.99% — all match.
- Dashboard: CN added to the country selector, Command Center/User Guide name maps, Relative Cycles `COUNTRIES`, Workbench facet + flags, Data Dashboard label map. Methodology §11 rollout table rewritten (was stale — still said "Japan next"); §15 revision-log row added (anchor-split pattern, verified 2 occurrences).
- 2 new tests (CN config integrity: 3-sector debt + interbank proxies + private-vote inputs; live CN two-vote regression pinned to leveraging) — suite **429 passed, zero exclusions**.
- Full pipeline run on host (charting stopped first, restarted after); docker images rebuilt; all 8 routes verified 200; CC/Relative/Guide render CN with live data.

**Next:** India is next in the Phase 2 order (expect the CN pattern: WB/IMF + FRED-mirrored feeds; check `DT.DOD.DECT.CD` early). Other open tails: D4 manual-load slots, ONS/e-Stat CPI registrations, the 2007-squeeze threshold tweak candidate.

---

## 2026-07-07 — India + Germany + Luxembourg rollouts (9 economies live)

**Ask:** India next per the Phase 2 order, plus Germany and Luxembourg by user request (both euro members — standalone codes alongside the EZ aggregate for core-vs-aggregate divergence reads).

**Done:**
- Three binding + composites file pairs, every series endpoint-verified first: **IN 32 signals / DE 29 / LU 27 — 308 signals total across 9 economies**. All clean (0 empty / 0 errors / 0 sanity warnings). Loader maps gained DE→DEU, LU→LUX (WB + IMF).
- **India is data-richer than China**: LIVE monthly IP (GYSAM form) + LIVE 10y gov yield (from 2011) + live quarterly real GDP + BIS 3-sector credit (2007→) + WB external debt fills ($716B, as predicted from CN). CPI dead 2025-03 → IMF bridge. INR not in COFER. Latest read: Expansion (G +2.76 / I −1.72); stage = reflation 0.38 (private vote leveraging, sovereign reflation — worst-of picks reflation correctly since leveraging is lower severity).
- **Germany is the richest non-US dataset in the system**: live monthly HICP (first bridge-free non-US country), live IP via the Eurostat JSON API (`geo=DE` — OECD FRED IP feeds died 2023/24), live retail/unemployment/Bund/3m interbank (first non-US 2-signal rate basket), BIS credit from 1970. Latest read: Stagflation (G −0.30 / I +0.39); **stage = deleveraging on BOTH votes at 0.44 — diverging sharply from the EZ aggregate's reflation, exactly the core-vs-aggregate contrast the standalone build was for.**
- **Luxembourg works but is structurally weird** (documented prominently in `lu_bindings.yaml` header + wishlist): BIS private credit 420% GDP (358.8% corporate = intra-group financing vehicles — read as a global credit-conditions gauge, quality_factor reduced), FDI ±100%+ GDP (sanity ±500/800), exports 190% GDP. Live HICP/unemployment/IP/10y. The growth composite under-reads LU because the financial sector (the real economy) has no free monthly gauge — LowCov flags honestly. Stage = reflation.
- **All three carry BIS household+corporate credit → all three run the private/sovereign two-vote stage split** (5 of 9 countries now: US/CN/IN/DE/LU). None has a gov-interest series → their SOVEREIGN SQUEEZE flags degrade honestly to never firing (CN pattern).
- Stage config: 3 new `countries` + `sovereign_inputs` entries (IN/DE/LU use real 10y yields in the spreads, unlike CN's interbank proxy).
- Dashboards: country selector (9 entries), CC/User Guide/Relative Cycles/Workbench/Data Dashboard maps all extended; Methodology §11 table updated (Brazil marked next) + §15 revision rows (anchor-split, verified 2 occurrences).
- Force balance: DE 1.20 / IN 1.03 OK; no CORR AUDIT flags on any new country. 4 new tests (config integrity for IN/DE/LU two-vote entries + live three-country two-vote regression); suite **431 passed, zero exclusions**.
- Spot-checks vs public references: DE Bund 3.05% / HICP ~2.2% / unemployment 3.8% / gov debt 62.9%; IN 10y 7.02% / growth 7.6% / gov debt 84.1%; LU credit 420% / gov debt 27% — all match.
- Docker rebuilt, all 8 routes 200, CC renders all three countries with live stage chips.

**Next:** Brazil is next in the original Phase 2 order (expect the IN pattern; check DT.DOD external debt early). Standing tails: D4 manual-loads, ONS/e-Stat CPI registrations, no free German core CPI (wishlist), 2007-squeeze threshold tweak.

---

## 2026-07-07 — D4: manual-load infrastructure (V-Dem governance + GPR)

**Ask:** build D4 — the last unbuilt piece of the big-cycle ORDER layer. V-Dem/Polity governance and the Caldara–Iacoviello GPR index publish no free API (bulk CSV/xls downloads only).

**Done:**
- **Drop-folder pattern**: `MANUAL_DATA_DIR` (default `DATA_DIR/manual_data/`, env-overridable, added to both docker-compose service blocks). `fetch_manual_series()` in `loader.py` reads per-signal `date,value` CSVs (bare years → year-end timestamps, ISO dates passthrough; case-insensitive headers). **Missing file = pending [SLOT]** (one INFO line, never an error); **present-but-malformed = loud ValueError**.
- **Pipeline Pass 3.8 (Manual-load series)**: new `provider: Manual` binding filter; `results["slot"]` counted separately — pending slots never fail a run; per-country and final summaries show "Pending slots: N" only when nonzero.
- **15 Manual bindings**: `order.governance` (V-Dem `v2x_libdem`, 0–1, annual) for US/CN/IN/DE/GB/JP/KR/LU; `order.geopolitical_risk` (GPR `GPRC_{ISO3}` share-of-articles, monthly since 1985) for the same set minus LU — **Luxembourg is not in the GPR country set** (honest gap, no binding). No EZ aggregate exists for either source.
- **Converter scripts**: `scripts/prepare_vdem.py` (V-Dem-CY-Core CSV → `vdem_{cc}.csv` × 8; 1900 start to keep expanding Z-scores sane) and `scripts/prepare_gpr.py` (`data_gpr_export.xls` → `gpr_{cc}.csv` × 7; needs `xlrd` for the legacy .xls — documented, not added to requirements since it's operator-side only).
- **Docs**: `docs/manual_data.md` (sources, download links, format spec, freshness expectations) — mirrored into the drop folder as its `README.md`. `us_bindings.yaml` deferred-comment block updated; the pre-existing `climate.disaster_loss` slot noted as the next candidate for the same pattern once EM-DAT access is sorted.
- **Command Center**: big-cycle card now shows V-Dem + GPR readouts when the files land, and names the *specific* pending slots ("governance/GPR pending manual load") until then — replaces the blanket "deferred" suffix. Also added CNY to the reserve-share currency label map.
- **Tests**: new `tests/test_manual_load.py` (9 tests — slot vs loud-failure semantics, year/ISO parsing, header case, config integrity incl. the LU-has-no-GPR rule).
- Roadmap D4 marked ✅; wishlist governance/GPR entries flipped to BUILT.

**Design note:** the "order score" composite stays deliberately unbuilt — premature until the manual drops are loaded and have survived a couple of refresh cycles (per the roadmap's validate-before-extend rationale).

**Next:** drop the two files (download V-Dem CY-Core + data_gpr_export.xls, run the converters, re-run the pipeline) — then the slots fill with no further code changes. Brazil remains next in the country order.

---

## 2026-07-07 — Digital Ray country-coverage consult + Brazil & commodity-hub rollouts (14 economies)

**Ask:** "Do Brazil and Switzerland. Also give Digital Ray our country list and see what input he has — too many, missing key players, etc."

**Ray consult** (digitalray.ai; full log in ray_dalio_review_log.md Session 2026-07-07): endorsed Brazil, flagged **Switzerland as marginal** for the order read, and flagged **Germany + Luxembourg as "borderline redundant"** with the EZ aggregate. His top missing economies, ranked: **1 Canada, 2 Australia, 3 Mexico, 4 Indonesia**, 5 Vietnam, 6 Turkey, 7 South Africa, 8 Saudi Arabia, 9 Russia, 10 Singapore — the signal being that the set was heavy on debt-cycle *pillars* and light on the *commodity-exporter / trade-hub* axis (he ranked the original spec's Saudi/Russia BELOW the commodity exporters). User chose "do the ones Ray suggested" → built Brazil + his top-4 commodity/trade hubs; dropped standalone Switzerland.

**Done — 5 rollouts (BR + CA/AU/MX/ID), 154 signals → 14 economies, 462 total:**
- 10 config files (5 bindings + 5 composites), every series endpoint-verified 2026-07-07; loader WB+IMF maps gained CA/AU/MX/ID. All clean (0 empty / 0 errors / 0 sanity warnings).
- **All 5 carry BIS 3-sector credit → all run the private/sovereign two-vote stage split** (9 of 14 countries now: US/CN/IN/DE/LU/BR/CA/AU/MX/ID... actually 10). Stage reads: **BR squeeze (0.62 — Selic ~21% real rates), CA squeeze (0.53 — 100% household debt), MX squeeze, AU leveraging, ID reflation.** None has a gov-interest series → SOVEREIGN SQUEEZE flags honestly never fire.
- Per-country data quirks (all in data_source_wishlist.md): BR uses the discount rate (Selic-linked) as the rate — no OECD bond yield exists; CA is the richest (live IP + 10y+3m + monthly unemployment); AU has **quarterly CPI** and no monthly IP (growth on unemployment+trade); MX has no IP and no live unemployment (trade-only growth); ID uses call-money rate (bond yield + discount rate both dead) and no IP. WB external debt fills for BR/MX/ID (EMs), null for CA/AU (high-income).
- Dashboards: all 14 countries in the selector, CC/Relative/Workbench/User Guide/Data Dashboard maps. Methodology §11 table + §15 revision row. 3 new tests (config integrity for the 5 + live two-vote regression); suite **442 passed, zero exclusions**.
- **Bug caught + fixed mid-build:** the YAML generator first emitted `transformation: yoy` (invalid) for master.gdp_real → all 5 GDP signals errored and starved the stage classifier ("insufficient features"). Fixed to `yoy_pct`, re-ran clean.

**Design note:** Germany/Luxembourg redundancy acknowledged by Ray but NOT reverted — they were an explicit user request for core-vs-aggregate divergence, and DE already diverged (deleveraging vs the aggregate's reflation). Switzerland dropped in favor of Ray's higher-value commodity picks.

**Next:** Ray's next tier (Vietnam, Turkey, South Africa, Saudi Arabia, Singapore; Russia hits the no-Rosstat constraint), or the standing tails (D4 manual drops, ONS/e-Stat CPI, no free German core CPI).

---

## 2026-07-09 — Daily auto-import scheduler + Settings menu audit/cleanup

**Ask:** run the data import daily at a time set in the dashboard Settings; also audit the (stale) Settings menu.

**Settings audit finding:** the three window sliders (Growth Z / Inflation Z / Disequilibrium) were DUPLICATED — present in both the always-visible left sidebar AND the Settings modal, kept mirrored by six sync callbacks. Classic organic-growth cruft. Per user's call: keep them in the sidebar, remove the duplicates from Settings. Also dropped the stale "re-run the pipeline to refresh" footer note.

**Scheduler (simple — automates the manual workflow):** the user rightly pushed back on my over-engineering (graceful-notice / staging-swap). The manual process already stops the dashboard during an import, so the auto-version just fires those same steps on a timer.
- `indicators/schedule_config.py` — file-based coordination (schedule.json / schedule_status.json / run_now.trigger in DATA_DIR); the dashboard and scheduler talk through files, never the single-writer DB. Atomic writes, validation, graceful fallbacks.
- `indicators/scheduler.py` — APScheduler daemon: reads schedule.json, fires a daily cron job at the set time (+ polls a run_now trigger), and the job = **stop the charting container → run the pipeline → start it** (the manual workflow). Uses the docker SDK via the mounted socket to bounce charting; degrades gracefully (skips the bounce, still imports) if docker is unavailable. Pipeline exit code isn't used for pass/fail (it exits 1 on the documented EZ current-account empty) — completion is "done".
- `docker-compose.yml` — new `scheduler` service (same image, `/var/run/docker.sock` mounted, `restart: unless-stopped`, `TZ` from .env). Starts with `docker compose up`. `requirements.txt` += `docker`; `.env.example` += TZ.
- **Settings → Data updates** section: enable toggle, time picker, timezone label, last-run/next-run status, "Save schedule", and "Update now" (writes the trigger). Opt-in (disabled by default) so the user sets their own time.

**Verified live:** built all images; scheduler service comes up, finds the running `indicators_machine-charting-1` container via the socket, detects a schedule.json change on its poll, schedules the daily job, and computed next run = 2026-07-10 03:00 America/Chicago; status file written; reset to disabled (opt-in). Settings modal renders the new controls; the duplicate sliders + stale note are gone. 9 new tests (`tests/test_scheduler.py`); suite **451 passed, zero exclusions**.

**To use:** Settings → Data updates → toggle on, pick a time, Save. (Timezone via TZ in .env, default America/Chicago.)

---

## 2026-07-09 — Public/read-only mode for untrusted multi-viewer deploys + rebrand

**Rebrand:** repo renamed on GitHub to `economic-machine-dashboard` (auto-redirect keeps old links working); app tab title → "Economic Machine Dashboard", sidebar brand → "Economic Machine". Package + locked `indicators_machine` paths unchanged. Repo is now PUBLIC.

**Public mode (`PUBLIC_MODE=1`):** hardens the dashboard for an untrusted public/cloud audience. The concern: most settings are per-browser (localStorage — theme, country, windows, thresholds → each viewer independent, no collision), but three surfaces write SHARED server-side state and would let any visitor affect everyone: (1) the Data-updates scheduler (esp. "Update now" → restarts the app for all), (2) Weight Audit/History (importance editor writes YAML + the DB), (3) Workbench save/delete views (shared saved_views.json).
- `dashboard/app_mode.py`: `PUBLIC_MODE` flag + `OPERATOR_ONLY_ROUTES`.
- In public mode: Settings Data-updates section replaced by a read-only "refreshes automatically" note (scheduler callbacks not registered); Weight Audit/History nav links hidden + routes return an "operator tool" notice (blocks direct-URL access); Workbench save/delete/name controls hidden (load dropdown kept) + the save callback no-ops.
- No defaults needed — hidden controls keep their existing config-driven values. For the scheduler specifically, added env-var config so a headless/cloud operator can set the daily import without the UI: `AUTO_IMPORT_ENABLED` / `AUTO_IMPORT_TIME` override schedule.json in `load_schedule()`.
- docker-compose: `PUBLIC_MODE` on charting, `AUTO_IMPORT_*` on scheduler (all default off/empty → local single-operator experience unchanged).
- 5 new tests (env overrides, invalid-time ignore, flag parsing); suite **454 passed, zero exclusions**. Verified both modes render correctly; normal mode still serves all routes with write controls present.

---

## 2026-07-09 — Dynamic thresholds ON by default + self-contained traffic metrics

**Dynamic thresholds default-on:** Ray's dynamic regime thresholds (his 7-step algorithm) now default ON — `_DEFAULT_THRESHOLDS["dynamic"]=True`, the `regime-threshold-store` initial data carries `dynamic:True`, and all 6 `.get("dynamic", …)` read-sites default True (so keyless/older stored dicts flip on too). An explicit user "off" (stored dynamic:False) is still respected; the Regime Thresholds modal checkbox syncs from the store. Backtest G2 found dynamic ≥ fixed, so this is defensible.

**Traffic metrics (`dashboard/traffic.py`, `/traffic`):** no third-party tracker. Every real page view (the route_page callback) is appended one JSON line to `DATA_DIR/traffic.log` (append-only, concurrency-safe, never the DB); the /traffic page aggregates total views, unique visitors (per-tab sessionStorage id), views today/7d, a 30-day per-day bar chart (HTML bars, theme-adaptive), and top pages. Assets/framework/self requests are skipped. Access: if `TRAFFIC_KEY` is set, `/traffic` requires `?key=…` (works on a public deploy — operator bookmarks the keyed URL, no nav link); with no key on a non-public instance it's open + sidebar-linked. docker-compose exposes `TRAFFIC_KEY`. 7 new tests. Verified end-to-end with a real browser (recorded views, unique visitors, top paths). Suite **461 passed, zero exclusions**.

---

## 2026-07-09 (2) — Traffic: region breakdown + mobile-friendly layout

**Region breakdown (privacy-preserving):** `/traffic` now shows a **Top regions** table derived from the visitor's browser IANA timezone (e.g. `Europe/London`) — captured client-side into a `tz-region` localStorage store and passed to `record_hit(path, session, tz)` (new `z` field on each log line). **No IP address, no geolocation** — a coarse region hint only, with an in-page note saying so. We chose this over a third-party tracker (e.g. Google Analytics) deliberately: GA would give city-level location but sends visitor data to Google and needs a cookie-consent banner in the EU, which cuts against the "no black box" framing. `read_metrics()` gains `top_regions`; layout renders pages + regions side-by-side. 1 new test (`test_region_aggregation`).

**Mobile-friendly:** the app was desktop-only — **no viewport meta tag** (so phones fake-rendered at ~980px and shrank everything) and **zero `@media` queries**. Added (1) the viewport meta tag to the Dash constructor, and (2) a `@media (max-width: 768px)` block in `theme.css` that forces the 195px sidebar down to its 46px icon rail, tightens page gutters, lets over-wide tables/flex-rows scroll/wrap instead of bursting the layout. Verified with a 390px headless render: Command Center cards stack full-width and readable, sidebar is a clean icon rail, /traffic cards + bar chart + tables all fit. A full off-canvas drawer nav is a possible future polish, but the rail is usable now. Suite **462 passed**.

---

## 2026-07-09 (3) — Public cloud deploy (Hugging Face Spaces, free)

Prepared a free, no-credit-card public deploy on Hugging Face Spaces (Docker
SDK). Key findings + artifacts:

- **DB was 2.3 GB of DuckDB bloat** (only 285K rows across 5 tables). A fresh
  copy-into-new-file compaction drops it to **67 MB** — makes baking data into
  an image trivial. `scripts/build_public_bundle.py` reproduces this: compacts
  the DB + tars it with raw_cache/snapshots into `emd_data.tar.gz` (~27 MB).
- **`deploy/hf/`**: `Dockerfile` (clones the public GitHub repo at build,
  installs deps, extracts the data bundle, runs gunicorn on 7860, `PUBLIC_MODE=1`),
  `README.md` (HF Space metadata — `sdk: docker`, `app_port: 7860`), and
  `DEPLOY.md` (5-min click-path: create Space → upload 3 files → optional
  `TRAFFIC_KEY` secret → live). The Space holds only Dockerfile + README + data
  bundle; code comes from GitHub so rebuilds auto-pick-up main.
- **gunicorn** added to requirements. Verified end-to-end: built the exact
  image, ran it on :7860 under gunicorn, headless-rendered the Command Center
  off the baked-in compacted DB — full live data, DYNAMIC badge, SOVEREIGN
  SQUEEZE flag, and operator-only nav (Weight Audit/History) correctly hidden
  in public mode. Data bundle is not committed (binary — uploaded to the Space).

---

## 2026-07-09 (4) — UI cleanup: nav tooltips, Overview names + Rate coverage

Three requested tweaks:
- **Removed the hover popup labels on the left nav** (all `dbc.Tooltip`s on the
  nav links + Settings). The icon rail no longer shows tooltips.
- **Overview spells out every country** — added Luxembourg/Australia/Mexico/
  Indonesia to `_COUNTRY_NAMES` (they were rendering as LU/AU/MX/ID codes) and
  refreshed `_COUNTRY_ORDER` to the real 14-country rollout order.
- **Overview Rate column now fills for all 14 countries.** It was hardcoded to
  `policy.fed_funds_target` (US-only). Added a per-country fallback —
  policy rate → 3-month interbank → 10-year gov-bond yield — so each country
  shows its best-available rate, with the actual instrument named on hover
  (`_RATE_CONCEPT_LABELS`). e.g. US/EZ policy rate, CN/DE/CA/AU/MX interbank,
  GB/JP/KR/IN/LU 10y yield, BR Selic 21.3%.

88 charting tests pass.

- **CHI now computes for all 14 countries** (follow-up to the Rate fix). The
  Cycle Health Index read the policy rate ONLY from `policy.fed_funds_target`
  and inflation ONLY from `inflation.cpi_headline`, so it returned None for
  every country lacking the US-shaped signals — the Overview CHI/Stage columns
  were blank for all but US/EZ. Applied the same per-country fallbacks
  (`_RATE_CONCEPTS`, `_INFLATION_CONCEPTS`) to `_cycle_health` and
  `_cycle_health_history`; Japan's inflation now bridges to the annual IMF
  estimate. Result: CHI raw / debt-adjusted / Stage fill for all 14. Instrument
  named on hover for both Rate and Inflation fallback cells.

---

## 2026-07-09 (5) — Data Confidence score/badge (per-country + per-force)

New `dashboard/data_score.py`: grades how trustworthy each country's reads are
from three signal properties we already track — freshness (`is_stale` + age,
graded so a normal lag ≠ an abandoned feed), directness (`is_proxy` /
`is_constructed`), and depth (# signals in the basket, with thin baskets capped:
1 signal ≤ C, 2 ≤ B). Per scored force (growth/inflation/rate/credit) → 0–100 →
A/B/C/D; overall = weighted avg (growth+inflation heaviest). Live spread: US/EZ
A, most others C, richer EMs B — honest.

Surfaced:
- **Overview**: colored A–D chip after each country name + legend note (hover =
  per-force breakdown).
- **Command Center**: a "Data <grade>" header chip, and — the key ask — a
  per-force caveat on the Growth/Inflation cards (e.g. Indonesia growth reads
  "C · data · 5 signals · 4 stale, 2 proxy", so the stale-growth story is
  visible right next to the number). 6 new tests; suite 468 passed.

---

## 2026-07-09 (6) — Data-quality drive: UK CPI live via ONS (C-country push)

Started the concerted C-country data-improvement effort (UK/JP/KR/CN/IN/LU/ID)
from the punch-list in `docs/Guidance/signal_sourcing_guide.md`. First win: UK.

- **New `fetch_ons_series()`** in `loader.py` — the UK ONS "append-/data" JSON
  API (free, unregistered). Topic-agnostic: series_id is `CDID/DATASET` and the
  fetcher walks the ONS economic topic paths until one resolves (or takes an
  explicit `topic/CDID/DATASET`). Pipeline **Pass 1.7** (provider `ONS`).
- **UK CPI repointed** from the dead OECD-on-FRED mirror (`CPALTT01GBM659N`,
  ended 2025-03) to ONS `d7g7/mm23` — **live to 2026-05 = 2.8%**, exact match to
  the published rate. GB **inflation force C→B**; overall 66→70.
- Verified end-to-end (rebuilt the pipeline image — it bakes code, so it needed
  rebuilding too; ran the full pipeline). 2 new ONS tests.

**Roadmap (rest of the C countries):** free/unregistered next → UK retail+IP+
unemployment via the same ONS fetcher (de-stale GB growth → likely B); India
MOSPI, Indonesia BPS/BI, Brazil BCB (verify). Registration-gated (operator key
needed) → Japan e-Stat (worst CPI staleness), Korea BoK ECOS. Hard/none → China
bond yield, Luxembourg (structural).

- **UK growth also moved to ONS** (retail `j5ek/drsi`, IP `k222/diop`,
  unemployment `mgsx/lms`; index series → yoy_pct, rate → level). Retail flipped
  fresh, IP/unemployment fresher. **GB growth C→B; GB overall C→B (73).** First
  C-country fully upgraded on free/unregistered data. `_fetch_ons_from_api` made
  topic-agnostic (walks ONS economic topic paths).

---

## 2026-07-10 — Japan CPI live via e-Stat (C-country push, key-gated win)

Operator supplied a free e-Stat appId (stored in git-ignored `.env` as
`ESTAT_APP_ID`). Wired Japan's live monthly CPI in — the worst-staleness gap in
the dashboard (JP inflation had been an IMF *annual* bridge since 2021).

- **New `fetch_estat_series()`** (loader) — Japan e-Stat getStatsData REST API.
  series_id = `statsDataId/cdTab/cdCat01/cdArea`. Reads `ESTAT_APP_ID`; returns
  None (graceful skip → IMF bridge) if the key is absent. Pipeline **Pass 1.8**
  (provider `eStat`).
- **JP `inflation.cpi_headline`** = e-Stat `0003427113/1/0001/00000` (CPI
  2020-base index, all-items 総合, national 全国) → yoy_pct. **Live to 2026-05,
  linked to 1970**, YoY 1.52%. Added as PRIMARY in `jp_composites.yaml`; the IMF
  annual bridge demoted to keyless backup.
- **Result: JP inflation C→B, JP overall C→B (71).** Second C-country upgraded.
  4 new tests (ONS+e-Stat parse + guarded live). Note: the appId lives only in
  `.env` (gitignored) and the baked DB snapshot — never committed.

Discovered + documented the e-Stat login-loop fix: the appId is issued from
**My Page → API function** (`/en/mypage/view/api`), NOT the `/api/` portal
(separate auth realm that loops).

**C-country scorecard:** UK ✅ B, Japan ✅ B. Remaining C: Korea (BoK key
pending), China (no free bond yield), India/Indonesia (free national sources
to verify), Luxembourg (structural).

---

## 2026-07-10 (2) — Brazil on the open BCB API (C-country drive continues)

Fully autonomous win (no key). New `fetch_bcb_series()` (loader) — the Banco
Central do Brasil SGS time-series API, open/unauthenticated. series_id = numeric
SGS code. Pipeline **Pass 1.9** (provider `BCB`). Repointed 3 BR signals off
dead/proxy feeds to live BCB:
- `inflation.cpi_headline` → IPCA 12m (`13522`), live to 2026-06 = 4.64% —
  replaces the dead OECD-on-FRED mirror. **BR inflation C→B.**
- `growth.unemployment` → PNAD monthly (`24369`), live to 2026-05 — replaces
  the WB annual ILO proxy (de-proxied).
- `policy.rate_policy` → Selic annualized (`4189`) — the real COPOM lever,
  replacing the FRED discount-rate proxy.

**BR overall B 71 → B 77.** 2 new tests. Brazil still can't reach the top tier
on policy (no free BR 10y yield → single rate signal) but the underlying data is
now live/native across inflation, labour and the policy rate.

**C-drive tally:** UK ✅B, Japan ✅B, Brazil ✅B(77, strengthened). Korea ⛔
(Korean ID-verification wall). Next free-but-keyed: India (data.gov.in — easy
email key, no ID check), Indonesia (BPS — key). China/Luxembourg structural.

---

## 2026-07-10 (3) — Indonesia CPI live via BPS WebAPI (4th C-country upgraded)

Operator supplied a free BPS key (git-ignored `.env` as `BPS_KEY`; the BPS
"login loop" was a false alarm — the app/key ARE created, the portal just
redirects to the account page after Generate Key). New `fetch_bps_series()`
(loader) — Indonesia BPS WebAPI. Non-trivial: the data endpoint needs internal
th_ids (year-1900), the national row is vervar label "INDONESIA", and the
datacontent key = vervar+var+turvar+th_id+turtahun. CPI is fragmented by
COICOP group and rebased (2012→2018→2022); the live general index is var **2245**
(CPI 150-regency, 2022=100). Pipeline **Pass 1.10** (provider `BPS`).

`inflation.cpi_headline` → BPS 2245 (yoy_pct), live to 2026-06 = 3.3% (short
history from 2024). **ID inflation C→B, overall C 68 → B 73.** 2 new tests.

**Final C-drive scorecard:** UK ✅B, Japan ✅B, Brazil ✅B(77), Indonesia ✅B(73).
Blocked by national-ID SSO (resident-only): Korea (본인인증), India (JanParichay).
Structural (no free source): China (no bond yield), Luxembourg (financial-centre).

---

## 2026-07-10 (4) — Schedule-aware composite decay (Digital Ray consult)

Consulted Digital Ray on the age-decay methodology (logged in
`ray_dalio_review_log.md`). Finding: the dashboard had THREE decay mechanisms
with inconsistent philosophies — `is_stale` (release-aware, 200d/Q) and the
debt-stress module (excess-lag-aware) both matched "release-schedule-aware",
but the growth/inflation composite decayed on RAW fill-age (pure recency),
silently down-weighting a quarterly reading (e.g. GDP) mid-quarter even though
it was the freshest data available.

Ray's ruling: "recency PLUS schedule awareness" — the schedule-aware hold
belongs to LOW-frequency signals (a monthly series' natural cadence already
does the job), and high-frequency "bridges" carry the gap while the coarse
quarterly signal stays the reliable anchor. We already satisfy the bridge point
(growth basket ≈9 signals; GDP is one input the monthlies outnumber).

Implemented: `time_decay.release_grace_months` (TUNABLE D0/M1/Q4/A14) in
`composites_policy.yaml`; `compute_composite_history` now decays on
`max(0, fill_age − grace[freq])` (via the already-threaded `freq_map`). A
quarterly signal keeps full weight through its release window and only decays
once genuinely overdue — aligning the composite with the other two mechanisms.
US/EZ regime reads unchanged/sane; recomputed all 8,264 composite snapshots.

Related observation (NOT changed here): JP growth reads None in recent months
because ALL its growth signals are `is_stale`-EXCLUDED (real data ends ~April,
now July). That's the is_stale *hard exclusion* — a stronger form of the same
recency-vs-schedule tension. Extending the grace concept to the exclusion is a
candidate follow-up, but JP's ~3-month lag is genuine, so left as-is.

---

## 2026-07-10 (5) — Fed Monitor dashboard (/fed) — Digital Ray consult

New US Federal Reserve monitoring page built from a two-part Digital Ray consult
(logged in ray_dalio_review_log.md). Five sections in Ray's framing: short-term
cycle, rates-vs-inflation, balance-sheet/liquidity, turning points, and — the
*How Countries Go Broke* heart — late-cycle monetization (MP1→MP2→MP3).

- **7 new `fed.*` FRED series** in us_bindings (TOTRESNS reserves, RRPONTSYD ON
  RRP, T5YIFR 5y5y fwd, TREAST Fed Tsy holdings, MVMTD marketable debt,
  RESPPLLOPNWW remittances, FDHBFIN foreign holdings) — isolated `force: fed`
  so they feed the page only, NOT the composites or data-score. Verified 4 of
  Ray's AI-supplied FRED IDs were WRONG and corrected them before binding.
- **`dashboard/fed_monitor.py`** — 5 sections of mini time-series charts +
  current value + Ray's thresholds; header strip (easy/tight, behind/ahead,
  Fed-share-of-debt, MP-phase). Computes Fed share, foreign share, reserves/GDP,
  federal interest÷revenue inline. Route `/fed`, nav "🏛 Fed Monitor".
- Live reads confirm the thesis: ON RRP ~$0.5B, remittances −$235B, Fed share
  15.5%, foreign share 55%→32%, interest÷revenue 16.5% (danger zone). 3 tests.

- **Fed Monitor follow-ups** (both of Ray's flagged additions): (1) **10y term
  premium** — `fed.term_premium_10y` = FRED `THREEFYTP10` (the ACM/Kim-Wright
  10y term premium, live; no NY-Fed xls fetcher needed), card added to §4
  turning points (0.73%, risen from negative = fiscal-dominance worry). (2)
  **Fed % of net new issuance** — inline `_fed_net_issuance_share()` (ΔFed Tsy
  holdings ÷ Δmarketable debt, 1yr), card added to §5 monetization with a 30%
  red line. US signal count 80→81.

## 2026-08-11 — Weekly feed audit + automated weekly public-deploy refresh

**Weekly feed audit** (`scripts/weekly_feed_audit.py`, scheduled task
`weekly-feed-audit`, Sundays 02:07): read-only DuckDB + `schedule_status.json`
check, appends a dated report to `docs/audits/weekly_feed_audit.md`. First
live run (2026-08-11): 13/14 countries OK, KR WARN at 12% stale
(`kr.growth.industrial_prod`, `kr.inflation.cpi_core`,
`kr.inflation.cpi_headline` — the known OECD-feed-dead CPI gap, bridged via
IMF annual elsewhere but the live monthly slot itself reads stale), scheduler
OK. Noted a script bug worth a follow-up: no same-day dedup guard, so a second
run on the same date appends a duplicate section instead of overwriting.

**Automated weekly public-deploy refresh** (user request): the public demo
lives on **Google Cloud Run**
(`https://economic-machine-dashboard-987443237004.us-south1.run.app`), deployed
via the Cloud Build "Connect repository" console flow (Option A in
`deploy/cloudrun/DEPLOY-cloudrun.md`) — confirmed live-tested this session,
NOT assumed: pushing a commit to `main` triggers an automatic rebuild+redeploy
within ~3-4 min. New `scripts/refresh_public_deploy.py` chains the existing
`build_public_bundle.py` compaction with `gh release upload data-latest
--clobber` (replaces the public GitHub Release asset the Cloud Run Dockerfile
fetches at build time) and a marker-file (`deploy/cloudrun/.last_refresh`)
commit+push to `main` — since the Dockerfile also `git clone`s `main` fresh on
every build, one push refreshes both the deployed data AND any merged code
changes. Live-verified end-to-end: ran it once, live site's "data through"
banner (`_static_banner()` in `charting.py`, visible via `/_dash-layout` JSON
since Dash server-renders an empty shell) flipped Jul→Aug 2026 at the ~210s
mark. Scheduled task `weekly-public-deploy-refresh` created (Sundays 04:01,
after the 03:00 daily auto-import) to run this automatically; it deliberately
pushes to the public repo's main branch every run — already authorized by the
user, task prompt says not to re-ask. `gh` CLI is pre-authenticated in this
environment with repo+release write access — no new secrets needed.

## 2026-08-19 — Digital Ray consult: debt-growth-vs-income spread, productivity divergence, relative ULC

User is taking a Dalio course and asked two tactical questions live against
Digital Ray (logged in `ray_dalio_review_log.md`), then approved building all
three resulting punch-list items same-day.

**Q1 — debt growth vs. income growth equilibrium.** Ray's answer: `Spread_t =
DebtGrowthRate_t − IncomeGrowthRate_t`, both annualized %, a distinct metric
from the debt/GDP stock percentiles already tracked. Implemented as
`build_debt_income_spread()` / `_spread_flag()` in
`indicators/debt_cycle_stage.py`: per-sector (household/corporate/government)
spread computed as the YoY %-change of the EXISTING debt/GDP ratio signals —
a first-order identity (`%Δr ≈ %ΔDebt − %ΔGDP` for ratio `r = Debt/GDP`) that
needed no new data sourcing. Thresholds in `config/debt_cycle_stage.yaml`
`debt_income_spread` block: reserve-currency tier (US/EZ/JP, Ray's named set)
tolerates 1.5pp for 2 consecutive quarters; everyone else 0.75pp for a single
quarter; critical at 3+ consecutive quarters or a single YoY reading past
4.0pp (fixed a double-counting bug in an early draft that summed 4
already-annualized quarters instead of checking the single YoY reading).
`DebtCycleStageSnapshot` + `debt_cycle_stage_snapshots` table gained
`feat_spread_household/corporate/government` + `debt_income_spread_flag`.
Backfilled live for all 14 countries (no pipeline API calls needed — pure
recompute from existing `signals` table data). Surfaced in the same 3 places
Sovereign Squeeze uses — Command Center `stage_card`, Debt Stress page's
`update_debt_stage_section` (badge + per-sector values in the feature-bits
line), Relative Cycles `_country_card` — as a **separate** badge/chip, not
folded into the Sovereign Squeeze ⚠ (this repo has a history of badges
conflating unrelated signals into one alarm, e.g. the 2026-08 Data Feed
Monitor and Force Component fixes). Live US read: government spread +3.2pp
→ WARNING; several other countries (DE/GB/KR/CN/BR/CA/AU/MX/ID) read CRITICAL
on government-sector drift. 6 new tests in `test_debt_cycle_stage.py`.

**Q2 — productivity tactics.** Ray's answer largely *validated* the existing
`productivity_score` composite (labor productivity + TFP + R&D, same
0.6/0.3/0.1-ish weighting). Two genuinely new pieces: (1) a **divergence
read** — `_productivity_divergence()` in `dashboard/force_detail.py`, reusing
the same `gz` threshold the Growth chip uses: ProdScore rising + Growth Z
soft/neutral → "Early-stage competitive advantage"; ProdScore falling +
Growth Z strong → "Unsustainable-expansion watch". Rendered as an amber/teal
callout on the `/signals/productivity` banner and reused (imported directly)
in Command Center's Productivity Trend card so both surfaces read the same
way. (2) a **cross-country competitiveness ranking** — new `growth.relative_ulc`
signal bound to 10/14 countries (US/EZ/DE/GB/JP/KR/MX/CA/AU/LU), series
`CCRETT02{cc}Q661N` (FRED-mirrored OECD/IMF "Real Effective Exchange Rate,
Unit-Labor-Cost Based" — verified live via the FRED search API before
binding, per house rule; confirmed absent for CN/IN/BR/ID). This index is
already trade-weighted and FX-adjusted, so its YoY %-change is directly
comparable in DIRECTION across countries without inventing a cross-country
normalization scheme — simpler and more robust than the raw wages÷productivity
formula Ray proposed, which would have needed a PPP/FX comparability layer
built from scratch. New `_competitiveness_table()` section on `/relative`
(`dashboard/relative_view.py`), ranked most-improving to most-eroding, with
the CN/IN/BR/ID gap called out explicitly in the footer rather than silently
omitted. Live spot-check: Korea/Japan −11.4% YoY (gaining sharply), Australia
+10.9% (losing). Ingested via a standalone one-off script (not a full
pipeline run) since only one new signal needed fetching across 10 countries.
9 new tests (`test_force_detail.py` new file + `test_relative_view.py`).

**Verification.** Rebuilt + restarted the local `charting` Docker container
(image bakes source, no bind mount — confirmed all three features render
correctly via live browser check on `/relative`, `/country`, `/debt-stress`
before/after: badges, ranking table, and divergence card all showed correct
live values). Full suite **534 passed, zero exclusions** (one pre-existing
hardcoded US-signal-count assertion bumped 90→91 for the new binding — not a
regression). Methodology §15 Revision Log updated (both the copy-button and
visible table copies). Disclaimer as always: digitalray.ai output is an AI
approximation of Dalio's framework, not vetted by Ray Dalio.

## 2026-10-03 — Dashboard IA/color audit, Phase 1+2 (nav regroup + palette consolidation)

User asked for a UI/IA audit as the dashboard grew noisy (23 pages by this
point), presented as a pitch-deck artifact ("Dashboard IA Blueprint"):
nav had drifted into a grab-bag ("Indicators" mixed the regime engine's own
output with curated isolated-force monitors), only 3 of ~15 chart-bearing
pages used the polished Fed-Monitor card style, and the color palette had
been hand-retyped across ~15 files until it drifted (3 different reds, 3
different greens, two duplicate Z-score coloring systems). Full 5-phase plan
in the artifact; user approved starting Phase 1 (nav regroup) + Phase 2
(color consolidation) — Phase 3 (promote `_chart_card` into
`shared_components.py`) and Phases 4–5 (retrofit Signals, then Regime &
Cycles/Overview charts) remain open.

**Phase 1 — nav regroup** (`dashboard/charting.py::_left_nav()`). Split
"Indicators" into **Regime & Cycles** (Yield Curve, Regime Map, Regime
History, Debt Stress — the engine's own output) and **Monitors** (Fed
Monitor, Case Study Monitor, Market Expectations — curated, feed no
composite). Renamed "Data" → **Tools** (Workbench + Weight Audit/History,
moved in from the old "Reference" group). Renamed "Reference" →
**Reference / Admin** (gained Data Dashboard and Valuations, moved in from
the old "Data"/"Indicators" groups). Every link's existing `PUBLIC_MODE`/
`_traffic.nav_visible()` gating was preserved exactly — this was a pure
relocation, no visibility-behavior change. New standing placement framework
written to `docs/Guidance/dashboard_ia_framework.md` — a "where does the
next page go" decision tree plus the chart/color rules below, so future
features get placed by rule instead of guesswork.

**Phase 2 — color consolidation** (`dashboard/shared_components.py`). Named
the canonical semantic set (`BLUE`/`AMBER`/`GREEN`/`RED`/`GREY`, Fed
Monitor's own five, since they were already the most-reused values) plus a
`FORCE_COLOR` dict for the six per-force accents, both as public module-level
constants. `fed_monitor.py` now imports the semantic five instead of
redefining them (same hex values — zero visual change; kept the short
`_BLUE`/`_AMBER`/etc. names since `case_study_monitor.py` and
`market_expectations.py` import them directly). Deleted a verbatim-duplicated
`_zscore_color()`/`_concept_label()` pair (`charting.py` had its own copy of
both — now imports from `shared_components.py`). Reconciled the drifted
reds/greens to the canonical hex across `command_center.py`,
`relative_view.py` (×2), `global_overview.py` (×2), `data_dashboard.py`
(×5), `weight_audit.py` (`_BALANCE_OK_COLOR`), and `weight_history.py`
(`_DELTA_POS`) — each now imports `GREEN`/`RED` rather than retyping hex.
Left force-accent and 4-way categorical colors alone (e.g. weight_audit's
season-color map, data_score's A–D grade scale) since those are a different
axis from the good/bad semantic drift that was actually in scope.

**Verification.** All 9 edited files AST-parsed clean. Rebuilt the `charting`
Docker image and ran the full suite inside it: **619 passed**, 1 pre-existing
failure (`test_load_signal_overview_returns_all_signals`, a hardcoded
signal-count assertion stale from this session's earlier `growth.output_gap`/
`credit.*` additions — unrelated to this change, not a regression). Restarted
the live container and confirmed via browser: all four new/renamed nav
groups render with the right labels and links; Command Center, Data
Dashboard, Relative Cycles, and Fed Monitor all render correctly post-change
(Fed Monitor pixel-identical, as expected — same hex values, different
import path).

## 2026-10-03 (2) — Coverage-audit High item #1: Short-Term Health × Long-Term Stress combined view

First of the audit's four open **High**-priority items (the other three —
Debt-Stress rollout beyond the US, foreign/domestic-currency debt split,
MP1→MP2→MP3 for EZ/JP/GB — are real multi-day builds, scoped separately).
This one was "zero new data, pure visualization" per the audit, reusing two
composites that already existed: CHI (`global_overview._cycle_health_history`,
self-normalized to its own history's σ — same pattern the page already uses
for its adaptive-threshold banding) and the Debt-Stress composite's
`stress_score` (already a Z-score). New section at the top of `/debt-stress`
(`dashboard/charting.py::_page_debt_stress`): a scatter + 36-month trail,
quadrant lines at x=0/y=0/y=0.5, and a text readout from `_chi_stress_quadrant()`
— the real 4-cell interpretation table transcribed from the source note
(`600 Finance/.../Digital-Ray_Research/02 — The Indicators Machine —
Regime Detection System.md` §6), not invented from the audit's one-line
summary of it. Honest "no sharp read" fallback for the cells the note's
table leaves undefined, rather than forcing those into the nearest labeled
quadrant.

Debt-Stress is still US-only (unchanged), so this view is too for now — same
"not yet available" placeholder the existing page already shows for other
countries. It will automatically go multi-country once the Debt-Stress
rollout (High item #3) lands, since both pull from the same
`load_debt_stress_history()` call.

**Bug caught during verification**: `_cycle_health_history()` expects a
*lowercase* country code (it rebuilds `signals` table IDs as
`f"{country_code}.{concept}"`, and those are stored `us.master.gdp_real`
etc.) — every existing caller already lowercases before calling it
(`dashboard/global_overview.py:1364`), but `charting.py`'s country store
holds uppercase `"US"`. First pass silently returned an empty CHI history
(`len 0`, no exception — `_component_series` just returns an empty Series on
a miss). Caught by checking the rendered figure said "Not enough history
yet" instead of actually erroring, then confirming the row count directly
via `docker compose exec` before touching the fix. One-line fix:
`.lower()` the country code before the call.

**Verification.** Rebuilt + full suite in Docker twice (once per fix): both
times **619 passed**, same single pre-existing failure. Confirmed live:
US renders a real read (currently "Entering late-deleveraging" — CHI Z
≈ −1.4, Stress Z ≈ +0.17); switching to EZ correctly falls back to the
US-only placeholder, consistent with the page's existing per-country
convention.

## 2026-10-03 (3) — Coverage-audit High item #3: Debt-Stress composite rollout to 12 more countries

Second of the audit's four open High-priority items. The audit assumed "no
new sourcing" — Ray's own 3-component minimum-viable guidance was already
written into `config/longterm_stress.yaml`. That assumption turned out to
be wrong for one piece: `credit.debt_service_ratio` ("the earliest stress
signal") had zero non-US coverage anywhere in the codebase, and was
separately tracked in the SAME audit's "already tracked gaps" table as
"the single highest-value cross-country gap; no free API found yet."

**New data source found and verified.** BIS publishes a "Debt service
ratios" dataflow (`WS_DSR`) for the private non-financial sector, covering
12 of our 14 countries (missing only EZ and LU — not BIS reporting
entities in this dataflow). Discovered via the same `detail=serieskeysonly`
live-probing technique from the 2026-08-21 dollar-dominance session (the
documented dimension structure wasn't trustworthy on its own — had to read
the actual populated series keys). Key format `Q.{CC}.P` (P = private
non-financial sector, household+corporate combined — broader than the
US's household-only FRED TDSP, used uniformly across non-US countries for
comparability, documented in each binding's `linkage`). Verified live via
the existing `fetch_bis_sdmx_series()` infra (US 13.9%, GB 13.0% on first
fetch — plausible). New `credit.debt_service_ratio` binding added to
`config/countries/{au,br,ca,cn,de,gb,id,in,jp,kr,mx}_bindings.yaml`.

**Three real bugs caught and fixed before any country ran through them**
(all in `indicators/longterm_stress.py`):
1. `_build_primary_balance_gdp_fred()` reads raw FRED cache files with no
   country parameter — calling it for a non-US country would have silently
   returned the **US's own** primary balance mislabeled as that country's.
   Fixed with a `country_prefix == "us"` guard; every other country now
   goes straight to its own IMF/WB-sourced `fiscal.primary_balance_gdp`.
2. `_build_gov_household_debt_gdp()` summed gov + household debt/GDP with
   plain `pandas.add()` — NaN-propagating, so a country with no
   `household_debt_gdp` binding (EZ/GB/JP/KR) got an entirely empty
   component instead of falling back to government debt alone. First fix
   attempt introduced a second bug (checked `hh.empty` *after* calling
   `.resample()` on it — an empty Series from the loader has a default
   RangeIndex, and `.resample()` raises on that regardless of emptiness,
   independent of whether the check downstream would have caught it).
   Fixed by moving the emptiness check before any resampling.
3. The dynamic stock/flow weighting step indexed `hds_median_series` (built
   from the `household_debt_service` raw series) by a Timestamp comparison
   unconditionally — for a country with no debt-service source at all
   (LU), that series is empty with the same RangeIndex problem, and the
   comparison raised instead of the existing "fall back to static weights
   when inputs are unavailable" path ever being reached. This one was
   latent in the original US-only code too; just never triggered since the
   US always has debt-service data. Fixed with an explicit emptiness guard.

**Per-country configs** (`config/countries/{cc}_longterm_stress.yaml`, 11
new 3-component files + 1 new 2-component LU file): weights renormalized
from the US config's own 0.25/0.20/0.10 (or 0.25/0.10 for LU) to sum to
1.0, same z-score/staleness/band methodology as the US config verbatim.
One real methodology adjustment, not a bug: `max_carry_quarters` raised
from the US config's 4 to 8 for all 12 — the US's primary-balance leg is a
fast FRED fiscal-year proxy, but every other country's primary_balance_gdp
is IMF/WB *annual* data running ~7 quarters behind in practice (confirmed:
latest available vintage is 2024-12, current date 2026-10). At 4Q, that
component was being dropped almost permanently for every single rolled-out
country; verified immediately before/after on AU (2/3 components → 3/3,
stress score only producible after the fix).

**Pipeline**: new Pass 6b in `indicators/pipeline.py`, positioned after the
country-ingestion loop (same reasoning Pass 7 already documented — a
country's signals must be in the DB before its stage/stress features are
built), not immediately after the original US-only Pass 6. Auto-discovers
`config/countries/*_longterm_stress.yaml`.

**Dashboard**: removed the `if country != "US"` hard gates in
`update_debt_stress_info`, `update_debt_stress_chart`, and the new
CHI-stress callback (`dashboard/charting.py`) — `load_debt_stress_history()`
was already called generically in all three; the gates were the only
thing stopping other countries' data from showing. `_build_debt_stress_info`
now loads the calling country's own config (was unconditionally loading
the US's 7-component file, which would have shown the wrong weights for
every other country's table). Command Center's debt-stress card had a
hardcoded "/7 components" label — fixed to show the actual count, since
"3/7" would have read as 4 broken components rather than a different,
intentionally-scoped model. Relative Cycles' stale "(US-only model)"
fallback text and comment updated to reflect the real per-country state.

**Verification.** Full suite in Docker after each round of fixes: 619
passed throughout (same single pre-existing failure). Recomputed the
debt-stress layer directly against the already-ingested signal data
(no need to re-run the full 14-country pipeline a second time) to iterate
the three bug fixes quickly; confirmed via direct DB query after each fix.
Final state: AU/BR/CA/CN/DE/GB/ID/IN/JP/KR/MX all 3/3 components,
~74% retained weight, real non-null stress scores; LU 2/2, ~67% retained
weight; EZ still has no model (genuinely out of scope — not BIS-covered
AND missing `fiscal.primary_balance_gdp`, so even the 2-component fallback
isn't meaningful). Confirmed live in-browser across AU (3/3, combined
CHI-stress view producing a real quadrant read), LU (2/2), EZ (clean "no
model yet" fallback everywhere, no crashes), Command Center (AU's card now
reads "3 components active" instead of a misleading fixed denominator),
and Relative Cycles (all 12 rolled-out countries now show a real Debt
Stress value in the per-country card grid, where every one previously
showed nothing).

## 2026-10-03 (4) — Coverage-audit High item #5: Central Bank Monitor (MP1->MP2->MP3 for EZ/JP)

Third of the audit's four High-priority items, and the one that turned out
to be a design decision rather than a quick extension: `dashboard/fed_monitor.py`
is architecturally single-country (`_CC = "us"` is a hardcoded module
constant, nothing threads the country selector in at all), and its own MP1->
MP2->MP3 read leans on signals with no cross-country equivalent (foreign-
holder share of marketable debt, Fed remittances/losses). Rather than
retrofitting that page, built a new, deliberately simpler, genuinely
country-reactive page — `dashboard/central_bank_monitor.py`, route
`/central-bank`, "Monitors" nav group — with its own cross-country-comparable
read: the central bank's own balance sheet, level and YoY growth.

**Coverage, verified live before any binding** (per house rule — the
audit's own assumption that "ECB/BOJ/BOE balance sheets are well-covered on
FRED" turned out half wrong): ECB (`ECBASSETSW`, weekly, current — the
*monthly* `ECBASSETS` is discontinued, easy to pick by mistake) and BOJ
(`JPNASSETS`, monthly, current) are genuinely well-covered. **GB is not** —
every Bank of England balance-sheet series on FRED is either discontinued
or stopped updating years ago (`BOEBSTAUKA`: annual, last real observation
2016, last updated 2018; `UKASSETS`: discontinued 2014). Documented as a
confirmed gap on the page itself (plain "no live source" message for GB)
rather than silently dropped from the country list.

**A near-duplicate caught before it shipped**: EZ already had
`policy.central_bank_assets` bound to the exact same `ECBASSETSW` series
from an earlier project phase — and it already feeds EZ's `rate_score`
composite at CONTEXT weight (0.50 importance). First draft of this page
added a second EZ binding (`policy.central_bank_balance_sheet`) pointing at
the identical series under a different concept id, discovered only because
the ingestion log printed both lines side by side. Removed the duplicate
binding and its 1,448 already-ingested DB rows; the page reuses the
existing concept instead. JP had no prior binding, so its
`policy.central_bank_balance_sheet` is genuinely new.

**A real unit bug caught via a visibly broken chart**: the obvious US
analogue, `policy.fed_balance_sheet`, turned out to be bound as `transformation:
yoy_pct` — its stored value is already a YoY % change, not a dollar level.
Treating it as a level (dividing by 1e6 for a trillions display) produced
"$0.00T" and a "YoY -135.5%" readout with micro-scale y-axis ticks — caught
immediately from the rendered page, not a quiet silent error. Added a new
`fed.balance_sheet` binding (same `WALCL` series, `transformation: level`,
reuses the already-cached raw fetch) so the US has a genuine level signal
to pair against EZ/JP's.

**No GDP normalization attempted**: all three countries' `master.gdp_level_bn`
is USD-converted (World Bank/IMF), which would need an FX leg to pair
cleanly against a locally-denominated balance sheet (EUR/JPY) — skipped
rather than risk a unit-mismatched ratio. YoY growth needs no currency
conversion at all and is the read actually used for cross-country
comparison; it's resampled to monthly first so a weekly (US/EZ) and monthly
(JP) native series both produce a literal "vs ~12 months ago" figure.

**MP-phase read**: deliberately simpler than Fed Monitor's own US-specific
heuristic (which needs the foreign-holder-share + remittance-loss signals
this page doesn't have for EZ/JP) — the same YoY-growth-only threshold
(>+5% = MP2/QE underway, <-5% = MP1/QT, else roughly stable) is applied
uniformly to all three countries, so the comparison is honest rather than
mixing a richer US read against two thinner ones.

**Verification.** Full suite in Docker: 619 passed (same pre-existing
failure). Confirmed live across all four cases: US ($6.74T, +2.0% YoY,
"MP1 roughly stable"), EZ (€5.90T, -2.9% YoY), JP (¥644.66T, -11.0% YoY,
"MP1/QT contracting" — consistent with the BOJ's actual gradual JGB-purchase
unwind), GB (clean "no live source" message, no crash), and a genuinely
uncovered country CN (clean "not one of the three covered banks yet"
message). No console errors beyond the pre-existing benign Dash
wildcard-callback warning pattern already present on every other page.

## 2026-10-03 (5) — Coverage-audit High item #4: foreign-vs-domestic-currency government debt split (all 4 High items now shipped)

Last of the audit's four High-priority items, and the one the audit itself
flagged as highest-risk ("genuine new data-source research, not a derived
ratio... real risk it needs the coarser external-debt/reserves fallback
instead of a true currency breakdown"). Found a real source — no fallback
needed, though coverage came out narrower than the spec's target list.

**project_plan.md §6.4** names this as the requirement: "The Credit/Debt/
Fiscal lens must bifurcate leverage for EM countries" into domestic-currency
debt (risk: devaluation/monetization/inflation) and foreign-currency debt
(risk: hard default/BoP crisis) — Dalio's "single sharpest distinction" in
*Big Debt Crises*. Never built; every EM country ran the same stage
mechanics as the US, implicitly assuming the US's own-currency privilege.

**Source found and verified**: IMF's `IIPCC` dataflow ("Currency
Composition of the International Investment Position") carries exactly
this — government-sector external debt liabilities broken into domestic
(`XDC`) and foreign (`FC`) currency, in USD, quarterly. Discovered by
listing IMF's full dataflow catalog (`api.imf.org/.../dataflow/IMF.STA/all`)
and grep-ing for "debt"/"currency" in the names — not a guess. Verified
with real fetched numbers before writing a single binding: Brazil 64%
domestic / 36% foreign, Mexico 42% / 58%, Indonesia 24% / 76% — all three
match the well-known real-world EM debt-FX-exposure ordering (Brazil has
spent two decades de-dollarizing its debt; Mexico and Indonesia have not).
**India and China have zero coverage in this dataflow** — confirmed via
the same catalog probe, not assumed; documented as a real gap, same as
GB's missing central-bank balance sheet in item #5. project_plan.md's
original target list (BR/MX/ID/IN/CN) is now 3 of 5, not a fallback metric
on all 5.

**Two bugs caught during verification, both before any bad data shipped**:
1. The first live data probe used a dimension order with `FREQUENCY` first
   (`Q.BRA.L_P...`) because that's the convention `fetch_bis_sdmx_series()`
   uses for the *different* BIS API — got a clean empty result (zero
   series, not an error) that looked like "no data for Brazil" until the
   actual SDMX attribute order in the keys-only listing (`COUNTRY` first,
   `FREQUENCY` last) was checked directly instead of assumed from a
   different provider's convention.
2. The bindings were first written with `units: usd_millions` (copying the
   BIS/FRED convention from items #3/#5), producing sanity-check warnings
   ("value 166042178571 above sanity_max 10000000") — IIPCC's `OBS_VALUE`
   is already plain USD, not millions. Caught from the pipeline's own
   sanity-warning output, not a silent pass; fixed `units` and `sanity_max`
   for both legs across all three countries, force-refreshed to confirm
   clean (0 warnings).

**New signals** (BR/MX/ID only): `credit.govt_debt_domestic_usd`,
`credit.govt_debt_fc_usd` (both `provider: IMF_SDMX`, dataflow `IIPCC`).
**New flag**: `fx_debt_share_flag` (+ `feat_fx_debt_share`, the raw %) added
to `DebtCycleStageSnapshot`/`debt_cycle_stage_snapshots`, computed in
`indicators/debt_cycle_stage.py::build_fx_debt_share()`/`_fx_debt_share_flag()`
— share = FC ÷ (FC + domestic) × 100, flagged at fixed thresholds (warning
≥50%, critical ≥65%, `config/debt_cycle_stage.yaml` `fx_debt_share` block).
Deliberately a **fixed** threshold rather than `debt_income_spread`'s
country-relative percentile system: that system exists specifically
because a %Δ growth-rate spread is scale-dependent across countries (the
2026-09-27 audit finding); a currency-composition share is already bounded
0-100% and directly comparable, so a plain round-number bar (Dalio's own
"majority FX-denominated = risky" framing) is the methodologically correct
choice here, not a shortcut.

**Dashboard**: new badge on Command Center's Cycle Stage card
("FX DEBT SHARE: WARNING (58%)"), same separate-badge convention as
Sovereign Squeeze and Debt-Income Spread (never conflate independent
alarms into one). New chip on Relative Cycles' per-country card
("FX debt 76% · critical").

**Verification.** Full suite in Docker: 619 passed (same pre-existing
failure). Confirmed live: Indonesia (Command Center shows "FX DEBT SHARE:
CRITICAL (76%)"), Mexico ("WARNING (58%)"), Brazil (correctly shows no
badge — 36% is below the 50% warning floor), India (correctly shows no
badge — no data, not a crash). Relative Cycles: Mexico and Indonesia show
the new chip inline with their stage chip; every other country (including
Brazil) shows nothing, as expected.

**All four of the coverage audit's High-priority items are now shipped**:
#1 (combined CHI × Debt-Stress view), #3 (Debt-Stress rollout to 12
countries), #4 (this entry), #5 (Central Bank Monitor). Medium/Low items
from the same audit remain open for a future session.

## 2026-10-03 (6) — Remaining coverage-audit items, Phase A #1: government interest payments for 11 countries (unblocks Sovereign Squeeze)

User asked to implement everything left from the audit that doesn't need a
paid source, sequenced sensibly. Full triage + plan written to
`session-checklist.md`. This entry: the single highest-value item found
during that triage — not on the audit's own ranked list at all, surfaced
while re-checking "gov-interest series outside the US," a gap tracked
since the 2026-07-06 Sovereign Squeeze ruling with "no source found yet."

**Found**: IMF's `GFS_SOO` (Government Finance Statistics, Statement of
Operations) carries general-government interest expense (`G24_T`, the
GFSM2014 economic-classification code for interest) as a direct %-of-GDP
transformation (`POGDP_PT`) — sidestepping a currency-mismatch risk the
raw-currency figure would have created against `master.gdp_level_bn`
(USD-converted). Verified real, sane values before binding anything (GB
2.97% of GDP, consistent with 2022's gilt-market inflation-linked spike
story already known from this project's other work).

**Real coverage, properly re-verified**: 11 of the 12 target countries
(GB/JP/KR/CN/DE/LU/BR/CA/AU/MX/ID) have real observations; **India does
not** — its `<Obs>` rows exist but every one lacks an `OBS_VALUE` entirely
(`STATUS="NA"`). First-pass verification counted raw `<Obs>` tags via grep
and wrongly concluded India was covered; the pipeline's own ingestion
(which filters on `OBS_VALUE` presence, same as every other provider) got
it right immediately — correctly reported `[EMPTY]` for India without
any code change needed. The false "it's covered" belief was corrected by
rechecking every country with the same OBS_VALUE-presence filter the
pipeline itself uses, not by trusting a faster but wrong manual count.
EZ still has no entry either (checked both `U2` and `EMU` aggregate codes
— same gap pattern as `fiscal.primary_balance_gdp`).

**Code change**: `build_sovereign_features()` in `indicators/debt_cycle_stage.py`
now accepts an optional `gov_interest_gdp` config key (a pre-computed
%GDP signal) checked *before* falling back to the existing raw-$-level
path (`gov_interest` ÷ `gdp_level`) that only the US uses. Necessary
because the raw IMF figure is in LOCAL currency while `gdp_level_bn` is
USD-converted (World Bank/IMF) — dividing one against the other would
have silently produced a currency-mismatched ratio with no error. The
refinancing-gap feature stays US-only (needs a currency-matched debt
stock the new countries don't have) but Sovereign Squeeze is an OR across
three conditions, so `gov_interest_z`/`gov_dsr_z` alone can still fire it.

**A second bug, same class as the Debt-Stress rollout's**: after wiring
and ingesting, every country but Canada still showed `gov_interest_z=None`
at the latest quarter despite having real recent data. Root cause:
`ffill_limit_quarters: 5` (1.25 years) — tight enough for the US's own
fast-landing FRED fiscal-year data, but IMF GFS's real-world lag (GB/JP/
KR/DE/LU/BR all had genuine 2024 data that was still *more* than 5
quarters behind "today") exceeded it for everyone except Canada (2025
data, the one country whose lag happened to fit). Raised to 10 quarters
(2.5 years) — a global change, not a US-only carve-out this time, since
a longer ceiling can only help genuinely-stale cases catch up and can
never make fresh data look more stale, so it's safe for the quarterly
signals sharing the same config value. Full test suite re-run after the
global change specifically to check for stage-label drift on unrelated
countries — none found.

**Still doesn't reach**: AU (2022 data, ~16Q stale), MX/ID (2023, ~11-12Q),
CN (2021, ~20Q) — all still beyond the new 10Q cap. Left as an honest gap
rather than chasing the cap further; carrying a 4+-year-old interest
figure as "current" would stop being a meaningfully live reading.

**Verification.** Full suite: 619 passed (same pre-existing failure).
Recomputed debt-cycle-stage directly for all 14 countries after the
fix (no full pipeline re-run needed — same already-ingested-signal-data
pattern used for the earlier Debt-Stress fixes). Confirmed live:
**South Korea's Sovereign Squeeze flag fired for the first time ever**
(Command Center now shows the SOVEREIGN SQUEEZE badge, features 4/5 → 5/5);
GB/JP/DE/LU/BR/CA all now carry a real `gov_interest_z` where none of
them had one before this session.

## 2026-10-03 (7) — Remaining coverage-audit items, Phase A #2: FX reserve runway (CN/IN/ID/BR)

Second item from the free-source build plan. `project_plan.md` §6.4's other
named EM balance-of-payments gauge, alongside the currency-debt split:
"FX Reserve Runway = FX reserves ÷ average monthly imports." Audit's own
assessment ("no new source — a derived ratio from signals already in the
system") was half right: the YoY-form reserves signal already existed, but
a genuine LEVEL was needed for a ratio, same pattern as `fed.balance_sheet`
earlier this session — added `capital.fx_reserves_usd` (same FRED series as
the existing `capital.fx_reserves_yoy`, `transformation: level` instead,
reuses the cached fetch) + `external.imports_usd` (new World Bank binding,
`NE.IMP.GNFS.CD`, current US$) for CN/IN/ID/BR.

Built as a `DebtCycleStageSnapshot` feature+flag, same architecture as
`fx_debt_share` from entry (5): `build_fx_reserve_runway()` /
`_fx_reserve_runway_flag()` in `indicators/debt_cycle_stage.py`. Thresholds
are the standard IMF/market reserve-adequacy convention (3 months = classic
floor, 6 = wider caution band) — not invented for this project, unlike
`fx_debt_share`'s exploratory bars.

**Bug caught from an implausible result, not a silent pass**: first
computation gave `runway=0.0` for all four countries — China holding $3.48T
in reserves against $3.29T in annual imports reading as "0 months of
cover" was obviously wrong on inspection. Root cause: `fx_reserves_usd` is
in FRED's native millions, while the new `imports_usd` is in World Bank's
plain current-US$ — dividing mismatched-by-1,000,000 units rounds to ~0 at
4 decimal places. Fixed by converting reserves to plain dollars before the
ratio. Re-verified against known reserve-adequacy reality before trusting
the fix: China 12.7mo (famously the largest reserve holder), India 7.4mo,
Brazil 10.5mo — all comfortable — and **Indonesia 5.4mo → warning**,
consistent with Indonesia's well-known thinner reserve coverage relative
to the other three.

Same Command Center badge + Relative Cycles chip convention as
`fx_debt_share` (separate badge, never conflated with another alarm).

**Verification.** Full suite: 619 passed (same pre-existing failure).
Confirmed live: Indonesia now shows both EM-risk badges stacked on Command
Center (`FX DEBT SHARE: CRITICAL (76%)` and `FX RESERVE RUNWAY: WARNING
(5.4mo)`) — the compounding-risk read Dalio's framework is meant to
surface. China/India/Brazil correctly show no runway badge (comfortable
coverage, below the warning threshold).

## 2026-10-03 (8) — Remaining coverage-audit items, Phase A #3: room-to-ease gauge

Third item from the free-source build plan — "a simple, Dalio-specific
diagnostic... how much conventional ammunition a central bank has left
before it's forced into QE/MP2." Zero new sourcing: distance of the
existing `policy.fed_funds_target` from a 0% floor (ELB), US/EZ only — no
free BOJ policy-rate series exists on FRED either (checked live), same
gap pattern as JP's missing Fed-Monitor-style signals elsewhere. Added as
a chip on `dashboard/central_bank_monitor.py` (the page built for item #5
earlier this session) rather than a new chart — purely a derived display
stat, no new signal or DB schema. Verified live: US +4.00pp (plenty of
room), EZ +2.50pp (right at the amber/green boundary), JP correctly shows
no chip at all rather than a fake or crashed value. Full suite: 619
passed (same pre-existing failure).

## 2026-10-03 (9) — Remaining coverage-audit items, Phase A #4: military expenditure % GDP (all 14 countries)

Fourth item — one of Dalio's eight named great-power determinants
(`Principles for Dealing with the Changing World Order`), flagged by the
audit as "genuinely buildable... zero mentions in any prior session."
World Bank `MS.MIL.XPND.GD.ZS`, same provider pattern as the existing
`order.gini`/demographics bindings — verified live for all 14 countries
before binding anything (US 3.42%, GB 2.28%, JP 1.37% — all consistent
with known real-world defense-spending ordering). New
`order.military_expenditure_gdp` binding added everywhere, including
**EZ**, which has no `order.gini` at all (Gini has no sensible EZ-aggregate
reading; military spending does) — so this is the first order-layer
datapoint EZ has ever had beyond reserve share.

Wired into Command Center's Big-cycle position card and Relative Cycles'
Order line, same convention as Gini/COFER (append to `order_bits`, no new
UI surface). Zero sanity warnings across all 14 ingestions.

**Verification.** Full suite: 619 passed (same pre-existing failure).
Confirmed live on Relative Cycles: every one of the 14 countries' Order
line now ends with "military X.X% GDP" — including EZ, where the Order
line previously showed only reserve share.

## 2026-10-03 (10) — Remaining coverage-audit items, Phase A #5: momentum-gate magnitude backtest

Fifth item — a validation task, not a build. User's Obsidian notes flagged
that the classifier's `gm`/`im` momentum gates default to `0.0` (a pure
sign test), "exactly the false-positive mode" a single noisy one-month
wiggle can exploit to flip a Growth/Retraction or Inflation/Disinflation
label. Note suggested testing `>0.05`.

**Backtested before changing anything** (`indicators/backtest.py`'s
existing PIT-score + `US_SCENARIOS` machinery, reused as-is — classified
the full US history three times with `gm=im` at 0.0/0.05/0.1):
- Direction-validation accuracy on the known historical scenarios was
  **identical** across all three — 0.9% wrong-direction (1/115 months) —
  raising the gate costs nothing against ground truth.
- Label-flip frequency over the full PIT history dropped meaningfully:
  inflation flips 37.9%→22.6% (at 0.05)→9.4% (at 0.1); growth flips were
  unaffected at 0.05 (37.0%→37.0%) and only moved at 0.1 (→28.6%).

Shipped **0.05** — the value actually cited in the source note, not the
better-performing-but-unvalidated-by-the-note 0.1 (flagged as a future
candidate if 0.05 proves too weak in practice, not adopted speculatively).
Changed `_DEFAULT_THRESHOLDS` in `dashboard/charting.py` plus the matching
`regime-threshold-store` dcc.Store initial data (same default-sync pattern
already fixed once before for the "dynamic" flag) and 5 `.get("gm"/"im",
0.0)` fallback read-sites. Left one `(gm or 0.0)` null-guard at the Apply-
button handler deliberately untouched — `0.0 or 0.05` would silently
override a user's deliberate zero choice with 0.05, a real bug the
`.get(key, default)` pattern elsewhere doesn't share (only triggers when
the key is absent, not when the value is falsy).

**Verification.** Full suite: 619 passed (same pre-existing failure — no
test pinned the old 0.0 default). Confirmed live: with a stale cached
`regime-threshold-store` localStorage value (this session's own browser,
set hours earlier), the header correctly still showed the OLD 0.0 —
expected and already documented (existing per-browser values aren't
retroactively migrated, same as every prior default change here). After
clearing that one key, a fresh load correctly showed the new 0.05 default
in the Regime History header's live threshold display.

## 2026-10-03 (11) — Remaining coverage-audit items, Phase A #6: rate-basket correlation check (last Phase A item)

Last of the mechanical Phase A items — a due-diligence check, not a build.
User's Obsidian notes named a PRIMARY/STRONG/CONTEXT tiering rule and
specifically flagged nominal 10Y yield as a likely >0.95 correlation with
real 10Y yield, recommending nominal stay at CONTEXT tier so the
inflation-premium component isn't double-counted against the dedicated
inflation signals.

**Checked directly against the live DB** (not the project's own automated
`[CORR AUDIT]` tool, which runs on a different window/pairing and didn't
happen to surface this particular pair when re-run — the direct check is
the authoritative one here, computed straight from the same `signals`
table values the composite actually uses): `us.policy.yield_10y` vs
`us.policy.real_yield_10y`, r=0.94 (full history, n=5942), r=0.96 (last
10y), r=0.99 (last 5y) — confirms the note's suspicion and clears the
project's own documented |r|>0.80 anti-redundancy trigger by a wide margin.

**Found a real violation, not just confirmation**: `policy.yield_10y` was
already correctly tiered CONTEXT in `config/countries/us_composites.yaml`
(importance 0.45) below `policy.real_yield_10y`'s PRIMARY (0.90) — the
basic judgment call was already right. But 0.45 is 50% of 0.90, above the
project's own stated "secondary ≤ 40% of primary" anti-redundancy rule.
Lowered to 0.36 (exactly 40% of 0.90 — the rule's own ceiling, not an
arbitrary extra cut). Logged via `log_weight_changes()` (the same
mechanism the Weight Audit UI's Importance Editor uses) rather than
silently hand-editing the YAML, so it shows up correctly in Weight History
alongside the project's existing manual/regression weight-change trail.

**Verification.** Full suite: 619 passed (same pre-existing failure).
Recomputed US composites directly (`compute_composite_history` +
`upsert_composites`, same pattern as other direct recomputes this
session) to apply the new weight; `rate_score` updated to -0.868, a sane
value. Confirmed live on `/weight-history`: the new log entry (log_id 10)
renders correctly with its full reasoning, alongside the pre-existing
2026-07-05 regression-calibration entries.

**All six Phase A items are now shipped** (gov-interest payments, FX
reserve runway, room-to-ease gauge, military expenditure, momentum-gate
magnitude, rate-basket correlation check). Phase B ("pushing on a string"
QE-effectiveness flag, probabilistic regime confidence) and Phase C
(bubble-gauge scoping) remain open.

## 2026-10-04 (5) — AI capex bubble: six-expert research panel, monitor designed (not built)

Research + design session, no code shipped. User asked how to monitor the AI bubble from a
data perspective, "think like a hedge fund, think like Ray Dalio," using a mixture of experts
including Digital Ray, with a dashboard addition as the end goal.

**Panel.** Digital Ray consult (digitalray.ai thread `88cc245d-…`, logged in
`docs/Guidance/ray_dalio_review_log.md`) plus five specialist research agents run in parallel:
credit/structured finance, hyperscaler & semis equity, power & infrastructure, forensic
accounting, macro transmission. Each was given the free-data-only constraint and the
never-invent-a-series-ID rule, and required to paste live verification evidence. Outputs
synthesized into **`docs/ai_bubble_monitor_plan.md`** (the build plan) and a published artifact.

**Ray's ruling — stage classifier, not a score.** Verbatim: *"I don't like blended scores for
bubbles because they hide the real mechanics and create false confidence."* Independently
confirms the judgment already made in `bubble_gauge.py`. He specified a full 5-stage cascade
with entry conditions, 2-quarter confirmation and un-advance rules, plus the lead-time chain
(coverage breach → spreads 3-6m → capex slowdown 6-12m → market 12-24m; ~9-12m total for this
cycle). He also ruled "drop it" on two legs whose only sources were paid (data-centre ABS
issuance; real-time productivity proxy) — both dropped as instructed rather than proxied.

**A real panel disagreement, resolved rather than averaged.** The macro desk argued no stage
classifier is buildable at all — the AI sector has no observable debt stock, no sector DSR, and
12.7 years of Census data with zero prior downturns, so a `debt_cycle_stage.py`-style
percentile argmax would be "a random number generator with a Dalio vocabulary." Correct, and it
kills the obvious implementation. But Ray's cascade is a **threshold ladder**, not a percentile
argmax — absolute levels with confirmation counters need no cross-cycle history. Resolution
recorded in the plan: build the *shape* of the debt-cycle classifier, explicitly do not port its
percentile machinery, and suppress Z-scores on the Census series entirely.

**Verified independently by me, not just reported by agents** (the load-bearing claims):
- EIA-930 subregion hourly feed parses and the metric computes: Dominion-zone (Data Center
  Alley) overnight trough load **+12.7% YoY** against an adjacent same-weather control (PEP+BC)
  at **+3.6%** — a **+9.1pp excess**. This is the panel's best idea and it closes most of the
  gap Ray declared unclosable: realized electricity draw is the one number in the complex that
  cannot be booked, prepaid or round-tripped, at ~1-day lag. The 2001 "lit traffic vs reported
  revenue" lesson.
- ABCP − nonfinancial CP 30d spread reproduces the 2007 path exactly (2007-08-01 +0.09 →
  08-10 +0.39 → 08-20 +0.68 → 09-10 +1.24) and reads **+0.09pp today** against a 4,524-day
  median of +0.10. Best free tripwire available, with its calibration event in-sample.
- SEC EDGAR XBRL works from this machine (MSFT FY26 capex $115.9B; NVDA receivables
  $40.7B → $63.1B in one quarter). The duplicate-facts trap the forensic desk warned about is
  visible in the raw response — dedup is mandatory.

**Two non-AI defects surfaced, both logged in `session-checklist.md`:**
1. **FRED truncated every ICE BofA OAS series to a rolling 3-year window in April 2026.**
   `BAMLH0A0HYM2` now starts 2023-10-03 (794 obs). **`us.premium.high_yield_spread` is already
   truncated in our own DB to 863 obs from 2023-06-19**, and both raw-cache parquets
   (`fred_` and `alfred_`) are truncated too — the long history is already gone locally. A live
   signal in the premium force is being Z-scored against a window with no crisis in it. Needs a
   daily archive started (every uncaptured day is permanently lost) and `BAA10Y`/`BAA` as the
   long-history substitute meanwhile.
2. **`EIA_API_KEY` in `.env` is the literal placeholder `your_eia_key_here`** — CLAUDE.md lists
   EIA as an available provider and it is not. Didn't block this plan (every EIA source used is
   a key-free static download) but will silently break any future work assuming it.

**Most interesting finding, which nobody appears to be watching.** The two legs of BIS's own
AI-investment measure are moving violently apart: private **chip-fab** facility construction is
**−45.2% YoY and −59% from its Jun-2024 peak ($126.4bn → $52.3bn SAAR)** while **data-centre**
construction runs **+73.2% YoY ($84.95bn SAAR)**. Facility decisions are committed 2-3 years
ahead, so this is the only metric in the whole roster with a genuine structural lead. It is
either the telecom-1999 sequencing (upstream orders roll over before downstream deployment) or
CHIPS-Act expiry with no AI content — **the data cannot distinguish these**, which is exactly
why it belongs on a monitored page rather than in a conclusion.

**Also corrected a standing assumption.** Measured productivity does *not* discriminate a
self-validating boom from a debt-financed one: nonfarm output per hour grew +3.05%/yr during
1996-2000 and **+3.65%/yr during 2001-04, after the bust**. Our existing
`force_detail._productivity_divergence()` would have printed "Early-stage competitive advantage"
through the four years the capex was being written off. Not a bug — it answers a different
question — but it means `productivity_score` must not be used as the AI-bust discriminator. The
separation that works is Ray's own impulse/persistence inflation split (his 2026-10-03 Ruling 2,
already triaged ready-to-implement), which now has a second independent reason to be built.

**Status: nothing built.** Four open decisions are the owner's (plan doc §10), the most
consequential being whether to adopt a `conc_adj` threshold multiplier — the only proposed item
that touches the regime engine, and the only one that changes a reading today rather than
waiting for an event. Next session starts at plan §9 Phase 1. Test suite untouched at 677.

## 2026-10-04 (6) — AI Capex Cycle Monitor, Phase 1 shipped

Owner approved three of the four open decisions from `docs/ai_bubble_monitor_plan.md` §10
(adopt `conc_adj`, keep the page operator-gated, start Phase 1); the growth-composite question
stays open and deliberately unbuilt. Phase 1 is the **trigger layer** — the Tier-1 metrics that
can advance a stage. Tier 2 (SEC XBRL filings forensics) and the stage classifier itself remain
Phases 2 and 3.

**Shipped.**
- **`indicators/ai_capex.py`** (new) — all 8 Tier-1 metrics. Census C30 both legs (data centre
  AND chip-fab), EIA-930 subregion trough-load with its weather control, ABCP−CP spread,
  bank NDFI loans, CCC−BB dispersion, IT share of GDP growth, computers/electronics new orders.
- **`indicators/loader.py`** — new `fetch_url_cached()`, the documented home for providers that
  publish a plain file rather than an API (Census xlsx, EIA csv). Cache-first with an explicit
  TTL, falls back to a stale cache on a failed fetch, returns None only when there is no cache
  at all. `bubble_gauge.py` still has its own near-identical `_download_bytes` — consolidating
  the two is a small follow-up, deliberately not done here to avoid touching that module's 24
  passing tests mid-session.
- **`dashboard/ai_capex_monitor.py`** + route `/ai-capex-cycle`, Monitors nav group,
  operator-gated (added to `OPERATOR_ONLY_ROUTES`), built on the shared `_chart_card` from day
  one per `dashboard_ia_framework.md`'s rule 4. The page carries its own lead-time table and a
  "what free data cannot see" panel — the plan's instruction that a monitor documenting its
  blindness is worth more than one implying foresight.
- **`conc_adj`** — the one approved engine touch. A third multiplier in
  `compute_dynamic_thresholds()` beside the shipped `credit_adj`/`vol_adj`, **growth chip only,
  off by default**, toggled from the Regime Thresholds modal. `1 + max(0, (share-0.25)/0.25)*0.20`.
  Verified live: at today's 34.2% IT share it widens the US growth threshold **+7.4%**, leaves
  the inflation threshold bit-identical, and affects 23 of 562 historical months. The composite
  score is never touched, which is what keeps it consistent with "curated narratives feed no
  composite." Deliberately NOT applied in `compute_regime_confidence()` — that stat is an
  explicitly simplified historical hold-rate replay, and threading a US-only multiplier through
  it would change the metric's meaning for one country only.
- **ICE BofA spread archive** — `archive_spreads()`, append-only, union-merged on
  (series_id, as_of) so it is idempotent and can never shrink. 3,929 rows seeded. This is the
  mitigation for the FRED 3-year-truncation finding: every day not captured is permanently lost.

**Three real bugs, every one caught by RUNNING the code, not by reading it.**
1. **Two-digit-year pivot.** The C30 file reaches back to 1993, so a naive `"20" + yy` turned
   `Jan-99` into 2099 — which silently poisoned the chip-fab series (it reported `-96.6% from
   peak` against a 2099 "latest"). Caught because the number disagreed with the panel's
   independently-derived −58.6%.
2. **Partial-month contamination in EIA-930.** These files update daily, so the current month
   is always partial. October 2026 was being built from four days and compared against a full
   October 2025, producing a fabricated +2.4pp excess against a true ~+9pp. Same failure mode as
   the SPF loader's incomplete-quarter CPI average (2026-10-03 entry 7); fixed the same way,
   with an explicit completeness guard, and pinned by a regression test. A follow-on pass also
   added 3-month smoothing before the YoY — the raw monthly excess swung between +2.9pp and
   +13.8pp on an underlying trend that is steady.
3. **`conc_adj` silently died on date alignment.** `_dyn_threshold_input()` keeps `as_of` as a
   COLUMN and leaves a RangeIndex behind, so reindexing a date-indexed share series by
   `comp.index` yielded all-NaN and `fillna(1.0)` turned the multiplier into a no-op. It
   *looked* like it worked (conc_adj reported 1.0736 in a hand-built test where I had set a
   DatetimeIndex myself) and only failed against the real call path. Now aligns on `as_of` when
   present, with a regression test that reproduces the RangeIndex shape specifically.

A fourth issue was investigated and correctly *not* "fixed": a large blank band when scrolling
the page looked like a layout bug, but measuring the DOM showed all 8 cards at a uniform 260px
in a 788px three-row flex section. It was a Browser-pane scroll artifact, not a real defect.

**One display change driven by actually looking at the render.** The IT-concentration card
originally charted the share, whose y-axis ran ±200% — when 4-quarter GDP growth approaches
zero the denominator collapses and the share swings wildly, compressing today's 34% into an
invisible line. The card now charts the **pp contribution** (a stable series) with the share in
the header and read line. Both numbers are still shown, because the share alone is misleading in
exactly the situation the metric exists to catch.

**Pre-existing issue found, not fixed here.** Every Monitors page logs a Dash console error
(`A nonexistent object was used in an 'Input'`, naming stale `mon-info-N` tooltip targets) —
`shared_components._ICON_SEQ` is a never-resetting module counter. Reproduced on `/fed` as well
as the new page, so it is shared-component behaviour and not introduced here. Cosmetic, but it
fills the console; spun off as its own task rather than touching machinery 8 pages depend on
mid-session.

**Live reading at ship time.** Three Tier-1 metrics in warning: the data-centre/chip-fab
divergence (WARNING — data centre +73.2% YoY against chip fab −45.2% YoY, −59% from its
Jun-2024 peak), CCC−BB dispersion (CRITICAL at 10.11pp, 100th percentile — but with the caveat
on the card itself that FRED has no sector OAS, so its AI attribution cannot be verified), and
IT concentration (WARNING, 34.2% of all real GDP growth, 98th percentile). The two fast credit
tripwires are benign: ABCP−CP at +0.09pp against a +0.08pp median over 5,990 days, and bank NDFI
lending still expanding at +15.8% 13-week annualized. Realized demand is validated — Dominion
and AEP overnight trough load +11.9% YoY against a +3.7% weather control, a +8.3pp excess.

**Verification.** Full suite **701 passed, zero failures** (was 677; +24 new — 18 in
`tests/test_ai_capex.py`, 5 for `conc_adj`, plus one). Rebuilt and restarted the `charting`
container (a restart alone does NOT pick up code changes — memory `feedback-docker-rebuild`),
then confirmed in the browser: all 8 cards render with correct live values, both panels render,
the nav entry appears in Monitors, and the `conc_adj` checkbox is present, defaults to OFF, and
writes `conc_adj: true` to the threshold store the moment it is ticked.

**Next:** Phase 2 (SEC EDGAR XBRL provider + the Tier-2 filings metrics), then Phase 3 (the
stage classifier). The growth-composite decision (§10 item 1) is still the owner's.

## 2026-10-05 — PUBLIC_MODE gating audit: two unguarded shared-state writers found and fixed

Prompted by the owner's question while planning the Oracle VM public cutover:
"I want to make sure nothing that is configurable that affects things for all viewers is
exposed." Audited rather than assumed — and the assumption would have been wrong.

**The finding.** Hiding a page is not the same as disabling it. Three facts compose into a
real gap:
1. `dashboard/charting.py:80` sets `suppress_callback_exceptions=True`, so Dash does **not**
   verify that a callback's components are present in the rendered layout.
2. `weight_audit` and `weight_history` are imported unconditionally by `charting.py`, so all
   their callbacks register in both modes.
3. `/_dash-dependencies` — a public endpoint Dash serves by design — advertises every
   registered callback's full signature.

Verified live against the **public Cloud Run deploy** by READING that endpoint (no exploit
attempted): 93 callbacks advertised, including

    output : ..wa-editor-save-msg.children...wa-run-store.data..
    inputs : ['wa-editor-save-btn']
    state  : ['wa-editor-table','wa-editor-original','wa-editor-reason','country-store','wa-run-store']

That is `save_importance`, which writes `config/countries/{cc}_composites.yaml` **and** the
`weight_change_log` table — i.e. the weights behind every viewer's regime read. `OPERATOR_ONLY_
ROUTES` blocked the page and the nav link was hidden, but the callback stayed reachable.

**Severity, honestly stated.** On Cloud Run this is survivable: the container filesystem is
ephemeral and the DB is a frozen snapshot rebuilt from the GitHub release each deploy, so a
write is wiped on the next build. On the **Oracle VM it is not** — that is the live writable
system, and it is the machine being prepared for public exposure. This was a prerequisite to
fix before cutover, not a nice-to-have.

**Complete inventory of shared-state writes reachable from a callback** (grep for the write
primitives, every hit triaged):

| Write | Gating before | After |
|---|---|---|
| `charting.py:1910` `save_schedule` | ✅ registration skipped (`if not PUBLIC_MODE:`) | unchanged |
| `charting.py:1922` `request_run_now` | ✅ same block | unchanged |
| `workbench_data.py:328/337` saved_views.json | ✅ `if PUBLIC_MODE: raise PreventUpdate` in `wb_views` | unchanged |
| `weight_audit.py:141` YAML + `:999` `log_weight_changes` | ❌ **none** | ✅ guard added |
| `weight_history.py:249` `update_weight_change_reason` | ❌ **none** | ✅ guard added |

**The fix** follows the pattern already in the repo rather than inventing one: `workbench.py`'s
`wb_views` guards inside the callback body with `if PUBLIC_MODE: raise PreventUpdate`. Same
guard added as the FIRST statement of `save_importance` and `save_notes`, before any other
validation, so a crafted invocation carrying well-formed arguments is still refused. The
callbacks remain *listed* in `/_dash-dependencies` but are now inert — the listing is
information disclosure, the guard is the actual control.

**Verification.** New `tests/test_public_mode_gating.py`, 9 tests. Critically, the tests were
confirmed to FAIL when the guard is removed (2 failures) and pass when restored — a gating test
that cannot fail is worse than none. Also confirmed by executing both callbacks under a real
`PUBLIC_MODE=1` import: both raise `PreventUpdate` before touching anything. The file includes
a tripwire test that greps `dashboard/*.py` for write primitives and fails if a new one appears
in a module with no corresponding guard test, plus a test pinning that the scheduler keeps its
registration-skip strategy.

**Per-viewer settings confirmed safe, not assumed:** 11 `localStorage` stores (country, the
Z-score / inflation / disequilibrium windows, regime thresholds, theme, sidebar, session id,
timezone region). None touch the server.

**An own-goal worth recording.** Proving the new tests can fail required removing the guard and
re-running them — and with the guard gone, the test's own arguments (`[{"yaml_id":
"growth.payrolls", "importance": 0.9}]`) travelled all the way down the real write path and
wrote `importance: 0.90` into `config/countries/us_composites.yaml`. It surfaced as an
unrelated-looking failure in `test_composites.py::test_growth_importance_guidance_defaults`
(expected 0.64, found 0.90) on the next full-suite run. Restored with `git checkout`; the
`weight_change_log` table was NOT affected (latest row is still log_id 10 from 2026-10-03 —
`log_weight_changes` never fired because the empty `original_rows` yielded no delta).

The fix is a `no_real_writes` fixture that stubs every reachable write primitive to raise, so
the tests prove the guard without the *capacity* to perform a real write. Re-verified after
hardening: removing the guard still produces 2 failures, and the YAML's md5 is unchanged. The
general lesson — a test that calls a real callback with arguments chosen to reach a write path
is itself a hazard the moment the thing it is testing is absent; neutralise the primitive, not
just the path.

**Also worth knowing for future sessions:** two pytest processes against this repo will produce
convincing phantom failures — DuckDB is single-writer, and a concurrent run made 24 unrelated
`test_charting.py` tests fail. Run alone, that file is 103 passed. Check `ps aux | grep pytest`
before believing a surprising suite result.

## 2026-10-05 (2) — Feedback dialog: browser → Apps Script → Google Sheet

Owner's spec: no writes to the VM, populate a Google Sheet instead, optional email,
one button in the side menu opening a simple dialog, no IP and no location.

**Architecture.** The dialog is the one thing on a public dashboard that genuinely wants to
be a write surface — exactly what `PUBLIC_MODE` exists to eliminate (see the gating audit
earlier today). So the server is cut out entirely: `dashboard/feedback.py` renders the UI, and
a **clientside** callback POSTs from the visitor's browser straight to a Google Apps Script web
app, which appends a row to the Sheet. The deployment stores nothing. Receiver and deployment
notes live in `deploy/feedback/` (`Code.gs`, plus `probe.sh` for one-line endpoint testing).

Captured: message, optional email, and the context a bug report otherwise needs a back-and-forth
to establish — page, country, the three look-back windows, theme, viewport, app version (git
SHA), user agent. **Not** captured: IP, geolocation. The dialog discloses all of this in a
"What gets sent with this" disclosure, and a test asserts that copy still exists.

**Three non-obvious things this had to get right.**
1. `Content-Type: text/plain;charset=utf-8`, not `application/json`. JSON triggers a CORS
   preflight `OPTIONS`, which Apps Script web apps cannot answer, and the POST silently never
   happens. Pinned by a test.
2. `mode: 'no-cors'` — the response is opaque and unreadable. Accepted deliberately: reading it
   needs CORS headers Apps Script doesn't reliably set, and showing an error when the write
   actually succeeded is worse than optimistic confirmation.
3. Apps Script answers a POST with a 302 to a result URL, which must be followed as a GET (the
   `doPost` already ran). Browsers do this correctly on their own — but `curl -X POST` forces
   POST through the redirect and fails with a Drive "Page Not Found". That cost a debugging
   round against a deployment that was already working; `probe.sh` now carries the fix and a
   comment.

**Google-side deployment traps, all three hit, all now documented in `Code.gs`:**
"Anyone with a Google account" sends anonymous visitors to a sign-in page (GET redirects to
accounts.google.com, POST 401); clicking Deploy with the Version dropdown left on its current
number re-ships the same snapshot while reporting "successfully updated"; and functions pasted
*inside* the default `myFunction()` become nested, which Apps Script does not expose — the
endpoint answers "Script function not found: doPost" even though the code is visibly there.
A new deployment (rather than editing the existing one) also issues a NEW `/exec` URL.

**A bug caught only by the live end-to-end run.** The first real submission landed a row with
an empty App version column: the JS read `window.__EMD_VERSION__`, a global nothing ever set.
Now resolved at import from the git SHA, with an `APP_VERSION` env fallback because the Docker
image carries no `.git`, and threaded through the config store. Re-verified live: the second
submission recorded `a1a50e3` and `page: /ai-capex-cycle` correctly.

**Safety.** The Apps Script side prefixes any field starting with `= + - @` with an apostrophe —
formula injection is the real attack on a write-to-a-spreadsheet design, and a message of
`=HYPERLINK("http://evil.test","click me")` was verified to store as literal text rather than a
live formula. Plus a 4000-char cap (both sides), a 12/hour per-session throttle, and a shared
token that is abuse friction rather than access control — the `/exec` URL is necessarily public
for a browser-side POST, so the token can't be secret and the code says so.

**Gating.** The Feedback button is not rendered at all unless both `FEEDBACK_ENDPOINT` and
`FEEDBACK_TOKEN` are set — a button that silently discards what someone typed is worse than no
button. Both live in `.env` (gitignored); `.env.example` and `docker-compose.yml` carry empty
placeholders.

**Verification.** 17 new tests in `tests/test_feedback.py`, including one asserting the module
never performs a write and one asserting the submit stays clientside. Confirmed live in a
browser against the real endpoint: dialog opens from the sidebar, sends, closes on success, and
the row lands in the Sheet with every field correct. Test rows cleaned up.

Note: port 8502 was held by `imwt-charting-1` (the spun-off tooltip-fix task running in its own
worktree), so verification ran on :8504 rather than disturbing it.

## 2026-10-06 — Public cutover: dashboard.creovalabs.com live on the Oracle VM

The VM is now the public site, behind Caddy with automatic TLS. Cloud Run is retired (see
below). Full walkthrough and per-step verification in this session's transcript; the short
version:

**Architecture.** Caddy is the only public listener. The dashboard binds to `127.0.0.1:8502`
via the new `CHARTING_BIND` variable (defaults to `0.0.0.0`, so the NAS is untouched), meaning
a firewall misconfiguration still cannot expose the app directly. `PUBLIC_MODE=1`,
`TRAFFIC_KEY` and `DEPLOY_KIND=live` set on the VM.

**The operator/public split, forced by a real constraint.** The original plan — a public
container and an operator container side by side on the VM — does not work. DuckDB takes an
exclusive file lock; tested all three combinations on a copy of the live DB: rw+rw conflicts,
**rw+ro also conflicts**, only ro+ro coexists. So the NAS stays the operator/dev instance and
the VM serves only. That is also why the nightly import needs a maintenance page at all: the
pipeline must take the write lock, so charting has to step aside.

**Three bugs found by looking at the running system rather than the config:**
1. **Full IPs were being logged.** `ip_mask` was applied to `request>remote_ip`, but Caddy
   logs `client_ip` too and *that* carries the real address — the log held
   `remote_ip: 99.40.36.0` next to `client_ip: 99.40.36.158`. The Caddyfile looked correct.
   Both fields masked now; the log was truncated since it held unmasked addresses.
2. **The provenance banner lied on this deploy.** It hardcoded "Static demo snapshot —
   read-only, not live", which is true of Cloud Run's frozen release and false of a VM that
   imports nightly. Now driven by `DEPLOY_KIND`, defaulting to `snapshot`.
3. **Compose interpolates `$` in `env_file` as well as `environment`.** A bcrypt hash passed
   either way arrived as `$2a$14` and /stats 401'd with correct credentials. My first fix
   assumed `env_file` was passed through literally — it isn't, on this version. Caddy now
   imports the auth block from a mounted file it reads itself, which is version-independent
   unlike `$$` escaping.

**Certificate note for next time.** After the ports opened, Caddy did not pick up the cert —
it had already backed off to a 20-minute retry while they were shut, so the ACME log showed a
stale "likely firewall problem" that looked current. Restarting Caddy forced an immediate
retry and it issued in seconds from production Let's Encrypt (not staging), validated from
three perspectives. **Check the log timestamp before believing an ACME error.**

**Traffic metrics.** GoAccess reads Caddy's own access log, so unlike a JS beacon it isn't
defeated by ad blockers and sees every request — assets, bots, 404s — not just the page views
the in-app `/traffic` page records. The two complement rather than duplicate. Country geo uses
DB-IP's free IP-to-Country Lite (MaxMind GeoLite2 needs an account and licence key — verified
401 without one); country still resolves from the masked /24, which is the whole trade.
Report served at `/stats` behind basic auth, since request paths, user agents and referrers
are not public information.

**Verified live:** production Let's Encrypt cert valid to 2027-01-04; HTTP→HTTPS 308;
`/ai-capex-cycle` returns the operator-tool notice; Bubble Gauge / AI Capex / Weight Audit /
Traffic all absent from the public nav; feedback button present; maintenance page renders
"Updating — back in a few minutes" on a simulated outage; both log IP fields masked; `/stats`
401 without credentials and 200 with.
---

## 2026-10-06 — Dash console errors, Regime History layout + crosshair, threshold-display bug, and a Ray consult on the growth-chip momentum gate

**The ask (four things, in order).** (1) Fix the `ReferenceError: A nonexistent object was used in an 'Input' of a Dash callback` that every Monitors-group page logs on load — reported as being caused by `shared_components._ICON_SEQ`, the never-resetting info-icon counter. (2) Regime History: every chart on its own full-width row, with the shared crosshair the Signals force pages have. (3) Then, from a question the user raised reading the live page: the US growth charts and Regime Map both show growth above its threshold while the Growth chip still reads Transition — is that correct? (4) Take the answer to Digital Ray and decide it.

### 1. The console errors were NOT the info-icon ids

Captured the full error text (the browser console truncates it) by hooking `console.error` before an SPA navigation. The actual messages name **`rh-threshold-open`** and **`{"type":"regime-step-button","action":"prev"}`**. The `mon-info-N` ids that appear alongside them are the tail of the *"The string ids in the current layout are: [...]"* list Dash prints as context after the failing id — i.e. they were listed as PRESENT, not missing. Confirmed independently from the other direction: `dbc.Tooltip` in dash-bootstrap-components 2.0.4 is a pure React component with no Dash callback at all, so a tooltip target could never produce this error.

**Real cause.** Two callbacks take exact `Input`s on components that exist only on `/regime-history` and `/regime-map`, while also taking the global `page-trigger` Input — so they resolve on every page and the renderer errors on the missing ids everywhere else. Fixed by making both ids pattern-matching (`{"type": "regime-step-button", "action": ALL}` and `{"type": "rh-threshold-open", "idx": ALL}`); a wildcard Input matching zero components is legal and silent, and `ctx.triggered_id` still carries the concrete dict so the action dispatch is unchanged. Scoped deliberately: `rh-threshold-apply`/`rh-threshold-reset` live in the global modal and were left as exact ids.

**The info-icon ids were genuinely unstable anyway**, so they were fixed too — they were the reason the real error was unreadable. `_ICON_SEQ` was a module counter that never reset (only `fed_monitor.get_layout()` reset it), so every render minted fresh ids and left prior tooltip targets dangling. Now content-addressed: `mon-info-{sha1(scope + text)[:10]}`. Chose a content hash over the obvious per-`get_layout()` counter reset because `central_bank_monitor` builds its cards in a *callback* (`cbm-content`), not in `get_layout()` — a reset at the top of `get_layout()` could never have covered it. `_info_icon(text)` keeps its signature; `scope` is an optional second arg and `_chart_card` passes the card title, so two cards sharing info prose still get distinct ids. New test builds 8 real page layouts and asserts no duplicate `mon-info-*` ids (fed 25, validator 17, case-study 13, market-exp 10, ai-capex 8, bubble-gauge 3, central-bank 2 — all unique).

**Verification.** Swept all 22 nav routes with a `console.error` hook installed: **zero** "nonexistent object" errors, where before there were two on nearly every page. Regression-checked what was rewired: the Regime Thresholds modal opens on click and closes on Apply, and Prev/Now/Next step Oct → Sep → Oct on both `/regime-history` and `/regime-map`.

### 2. Regime History — one chart per row, crosshair across the whole stack

`_section(..., columns=1)` so every chart is its own full-width row (the shape the Signals force pages already use for their composite cards) instead of a flex-wrap grid putting three narrow charts side by side. The six cards already carried `sync_hover=True`, but the regime band chart on top sat outside the group, so the crosshair stopped at the cards; it is now dressed as a chart card (same chrome, same header) and tagged `sync-hover-card`.

**The part that actually made the crosshair readable was the gutter.** `_chart_card` let Plotly auto-size the left margin to each figure's own y tick labels, so `0.5`, `-2` and `Inflation` each started their plot area at a different pixel and the seven spike lines did not line up. New optional `_chart_card(margin_l=...)` pins it; Regime History passes `_RH_MARGIN_L = 55` (wide enough for the band chart's row labels) to all seven. Measured live: plot-area left **and** right edges identical to the pixel across all seven charts, and a real mouse hover puts a label + spike line on every one.

Also found in the process: `_chart_card`'s `dcc.Graph` had no `responsive=True`, so a figure kept whatever width it was first drawn at and sat narrow inside a wide card once the column resized. Added; re-checked Fed Monitor live to confirm the multi-column pages are unaffected.

### 3. The threshold readout was showing a number the classifier was not using

Answering the user's question surfaced a real bug. With dynamic mode on (the default), the Regime History header read **"G·Z +0.50"** while the classifier was using **0.226** — the readout was wired to `regime-threshold-store` alone, which only ever holds the sliders' base values, sitting next to a lit DYNAMIC badge. Misleading in exactly the case that prompted the question: a reading of +0.374 looks nowhere near the band when it has in fact cleared it.

Now takes the same selection inputs the regime info card does (step / windows / country / date range) and shows the selected month's effective values with the base in parentheses: **"G·Z +0.23 (0.50)"**. Parenthetical omitted when dynamic is off or when scaling did not move the value; tooltip on the DYNAMIC badge explains the two numbers. The per-row dynamic resolution was extracted out of `update_regime_info` into `_resolve_row_thresholds()` so the card that classifies and the header that reports read from one implementation — these two disagreeing *was* the bug. Momentum gates pass through unscaled (Ray's step 6), now pinned by a test. Kept the readout on its own callback rather than adding an output to `update_regime_info`: `regime-info-box` also lives on `/regime-map` where `rh-threshold-display` does not, and a multi-output callback with a missing output does not fire.

### 4. The answer to the user's question, and the seam it exposed

**The chip was correct.** `_classify_regime` requires three conditions for "Growth": Z > threshold, ΔZ > `gm` (0.05), and the Z leg sustained 2 months. On 2026-10 the US reads Z **+0.374** against a dynamic threshold of **0.226** (clears), sustained 2m (clears), ΔZ **+0.008** (fails). The Regime Map's "Expansion" backdrop uses `_season_label`, which checks only the two Z legs — so the two surfaces disagreeing is by design (Ray audit 2026-07-06, Q2: season names are map geography, chips are the decision rule).

**But the chip means something narrower than it reads.** Since 2010 the ΔZ leg alone blocked the Growth label in **45 of the 76 months** where the Z leg passed. The composite has sat between +0.30 and +0.48 for six months — it arrived and plateaued, and the rule demands it still be *accelerating* at 0.05 Z/month every month. In practice the Growth chip has been reading "growth is accelerating", not "growth is strong".

**Backtest of the alternatives** (US, 562 months 1980-01..2026-10, dynamic thresholds, scored against mean realized real GDP YoY over the FOLLOWING 12 months; unconditional +2.71%):

| rule | Growth months | flip rate | fwd-12m GDP G / T / R | G−R spread |
|---|---|---|---|---|
| current, ΔZ > +0.05 | 78 (14%) | 33% | +3.74 / +2.77 / +0.73 | 3.01pp |
| no momentum gate | 185 (33%) | 14% | +3.56 / +2.80 / +1.09 | 2.47pp |
| ΔZ > −0.05 (not falling) | 123 (22%) | 32% | +3.65 / +2.75 / +0.94 | 2.71pp |
| hysteresis (ΔZ to enter, level to hold) | 175 (31%) | 13% | +3.59 / +2.78 / +1.04 | 2.55pp |

Two findings worth recording. The gate makes the label flicker **more**, not less (33% vs 13-14%). And the 2026-10-03 (10) calibration that set `gm`=0.05 only compared 0.0 / 0.05 / 0.1 — **removing the gate was never tested**. That same entry already recorded that the gate did nothing for growth (37.0%→37.0% flips) and only helped inflation; it was adopted globally anyway.

### Ray consult + external validation

Full detail in `docs/Guidance/ray_dalio_review_log.md`, session 2026-10-06 (thread `b9c48725-1c73-441b-abec-74e4b355548a`). Ray's ruling: **the level is the primary gate** (*"if the level is below the threshold, the regime is not Growth, regardless of momentum"*), a high-but-flat reading **is** a transition, but it deserves its own label rather than being collapsed into the same bucket as a weak reading. He also endorsed per-force momentum gates and committed to a concrete three-label rule.

Operational note: digitalray.ai errors out on long prompts — the ~2,000-character brief failed repeatedly with "Something went wrong", including on Regenerate, while a ~450-character message worked first time. Run these consults as several short turns, which the documented process wanted anyway. Newlines in the input box submit the form, so compose without them.

**Then validated the proposal against outside sources before touching code**, because the backtest above scored our composite against forward GDP — the quantity that composite is built to proxy, so both sides lean on our own basket. Used the two benchmarks `indicators/audit_benchmarks.py` already wires: **NBER recession dating** (genuinely independent of every series we ingest) and **CFNAI-MA3** (Chicago Fed — independent *weighting*, overlapping *data*: it also contains payrolls, IP, retail sales, capacity utilisation).

| proposed label | n | median months to next NBER onset | within 12m | in recession |
|---|---|---|---|---|
| Growth (accelerating) | 105 | 51 | 2% | **0%** |
| Growth (flat) | 39 | **77** | 3% | **0%** |
| Growth (fading) | 65 | 41 | 0% | **0%** |
| Transition | 208 | 52 | **23%** | 5% |
| Retraction | 145 | 70 | 21% | 33% |

**Survives:** the level gate (all three high sub-states contain **zero** NBER recession months against 33% for Retraction), and the core claim that collapsing high-but-flat into Transition is wrong — a flat month sits a median **77 months** from the next recession onset while the Transition bucket we dump it in is 23%-within-a-year of one.

**Does not survive:** Ray's *causal story*. He justified the flat category as "the tail end of an unsustainable expansion"; in US data flat readings are the **furthest** of any growth state from the next recession and fading readings are **0%** within a year. Structure adopted, rationale rejected, wording kept out of the UI. And the three-way split only half-reproduces out of sample — rebuilding the identical rule on the Chicago Fed's composite gives **54%** sub-state agreement (3-way chance is 33%) and the accelerating−flat separation nearly halves, **+0.39pp → +0.21pp**.

Also rejected on evidence: Ray's `level_thresh = 0.7` (he appears to have forgotten his own 2026-07-05 dynamic-threshold algorithm; our vol-scaled 0.226 is the equivalent), his volatility-scaled momentum gate `0.5 × σ(ΔZ)` (collapses the separation to **+0.01pp**), and a defect in his literal code snippet (the `else` inside the `z > level_thresh` branch labels high-but-*falling* months as `"Low/Retraction"` — those months average **+3.43%** forward GDP at a 69% hit-rate).

**Separate calibration finding, logged not actioned.** Our growth level threshold is far less demanding than the Chicago Fed's published one: our growth family covers 37% of months, CFNAI-MA3 above +0.70 covers 3%, and below −0.70 is 93% in-recession. Different concepts — theirs is calibrated as a recession call, ours as a regime boundary — so CFNAI's thresholds cannot validate our `gz` directly.

**Verification across the session.** Suite 714 → 720 passed, zero exclusions. Browser-verified each change on a worktree-built container on :8502 (the main-repo container was swapped out and restored; note the scheduler finds the charting container by compose *service label*, not name, so a differently-named container is still bounced correctly by the 03:00 import).

**Next.** Implement the narrowed recommendation (below).

---

## 2026-10-06 (2) — Growth chip made level-gated; momentum demoted to a sub-state

**The ask.** Implement the narrowed recommendation from the consult + external validation above (same session, entry 2026-10-06).

**What shipped — three changes, one of which is a deliberate asymmetry.**

**1. `_classify_regime`'s growth leg is now level-only.** Was `gv > gz AND gd > gm AND sustained`; is now `gv > gz AND sustained`. The inflation leg is untouched and still dual-condition. The asymmetry is the point and is documented in the function's own docstring: the momentum gate measurably helps the inflation chip (flip rate 33% with it vs 9% without) and did nothing for growth (37.0% → 37.0% in the 2026-10-03 (10) calibration, which only compared gm 0.0/0.05/0.1 and never tested removing it), and NBER dating puts **zero of the 209 months above the growth level gate inside a recession** regardless of momentum. Ray's own ruling matched: "if the level is below the threshold, the regime is not Growth, regardless of momentum."

**2. New `_growth_momentum_state()` — momentum moved, not discarded.** Returns `accelerating` / `flat` / `fading` for a Growth chip and `None` otherwise, with `_GROWTH_MOMENTUM_STATE` giving a plain-English gloss (building / holding / easing off). Deliberately **not** promoted into the chip vocabulary — the three-way split reproduces only weakly on the Chicago Fed's independently-weighted CFNAI-MA3 (54% sub-state agreement, separation +0.39pp → +0.21pp), so it annotates rather than labels. Deliberately **growth-only**: the equivalent split on the Retraction side does not separate at all on forward GDP (+1.42 / +1.01 / +1.43), so there was no evidence to carry it across, and the code comment says so rather than leaving the asymmetry looking like an oversight.

**3. `gm` default 0.05 → 0.04, and its meaning changed.** `gm` no longer gates anything; it is the accelerating/flat boundary of the sub-state. 0.04 is Ray's value and the one that clears his own acceptance test on our data (+0.39pp accelerating-vs-flat separation on forward realized GDP, inside his stated 0.3–0.5pp band). `im` stays 0.05 and still gates the inflation chip. The Regime Thresholds modal copy was rewritten for both sliders — the growth one is now labelled "Growth Momentum **band**" and says in as many words that it does not gate the chip, because a slider that silently changed job would be worse than no slider.

**Surfaces.** The annotation appears in exactly two places: under the chips on the Regime History / Regime Map info card ("growth flat (holding)") and beside the Growth chip on Command Center ("flat", with a hover explaining what sets the chip vs. what sets the annotation). Not sprayed across every surface — it is secondary information and the evidence for it is weaker than the evidence for the level gate.

**Live effect across the 14 countries.** US +0.374 → **Growth [flat]** (was Transition — the reading that started all of this). Also flipped out of a wrong-looking Transition: **CN +2.133 → Growth [flat]** and **IN +1.044 → Growth [flat]** — a growth Z of +2.13 being labelled "Transition" because the month-over-month change was −0.03 was the clearest illustration of the defect. GB +0.835 → Growth [accelerating], JP +1.892 → Growth [accelerating]. EZ / BR stay Transition, DE stays Retraction — all correctly, on the level.

**Two test-coverage gaps found and closed.** The whole suite passed *before* any test was updated, which meant **nothing pinned the old growth momentum-gate behaviour at all** — a rule that had been in place since 2026-06-25 was entirely unprotected. Added 8 tests covering the new growth rule, the preserved inflation gate, the sub-state's three-way split and its boundary, its None cases, and the defaults. Separately pinned the `regime-threshold-store` initial data against `_DEFAULT_THRESHOLDS`: that pair has silently drifted **twice** (the `dynamic` default-ON change, then gm/im 0.0→0.05) and each time every new browser got different thresholds from the ones the code documented. Now a test failure instead of a silent divergence.

**Docs.** Methodology §8 rewritten — the narrative, both rule tables, and the defaults line (it was still documenting `gm = im = 0.0`, stale since 2026-10-03). New §15 Revision Log entry recording the change, the NBER/CFNAI evidence, and the three things from the consult that were **rejected** on evidence (Ray's fixed `level_thresh = 0.7`, his volatility-scaled momentum gate, and his "tail end of an unsustainable expansion" rationale). Ray review log and `docs/worklog.md` entry above carry the full derivation.

**Verification.** Full suite **729 passed**, zero exclusions (720 → 729: +8 classifier tests, +1 store-sync test). Rebuilt the charting image and verified live: Regime History shows `G · Growth` + "growth flat (holding)", Command Center shows `Growth · Growth` + "flat", and the threshold readout shows `G·Δ +0.040` **after clearing stale localStorage** — before clearing it still showed the old 0.050, which is the documented non-migration behaviour and worth knowing when sanity-checking a default change in a browser that has used the dashboard before. Swept /relative, /guide, /regime-map, /signals/growth, /overview, /regime-history: all render, zero console errors.

**Flagged, not fixed (out of scope).** The Signals force pages (`/signals/{force}`) show the BASE threshold in their banner ("THRESHOLD ±0.50") and draw their composite chart bands there, while the classifier uses the dynamic 0.226 — the same bug class just fixed on the Regime History header. `_resolve_row_thresholds()` and `_threshold_display_chips()` are the ready-made fix. Spawned as a separate task rather than widening this change.

**Next.** The Signals-page threshold display above. The calibration question logged in the review log is also still open and genuinely separate: our growth level threshold is far less demanding than the Chicago Fed's published one (our growth family covers 37% of months; CFNAI-MA3 above +0.70 covers 3%), which is a question about `gz` itself, not about momentum.

---

## 2026-10-06 (3) — Methodology + User Guide brought in line with the new chip rule (and two older staleness bugs found)

**The ask.** Make sure the Methodology page and the User Guide are up to date after the growth-chip change.

**User Guide — the chip lesson taught the old rule.** L3 ("Chips, thresholds, and windows — the decision rule") opened with "the chip system requires two conditions at once... AND the momentum must agree", and L2 ended with "the regime chips require BOTH". Both rewritten to teach the asymmetry — growth on the level, inflation on both — with the NBER evidence given in one sentence so a learner knows it is an evidence-based asymmetry rather than an inconsistency. Added a paragraph on the accelerating/flat/fading note and what weight to give it ("texture, not the call").

The **2×2 table** in L3 encoded the old rule directly (level beyond threshold × momentum opposes → Transition) and could not be patched, since the whole point is that the answer now depends on which chip. Replaced with `_chip_rule_table()`, a module-level helper rendering the two chips as separate rows across three columns (inside the band / beyond with momentum agreeing / beyond with momentum opposing) — the asymmetry is now the first thing the table shows.

The **newcomer trap** ("magnitude is not direction") was one of the three Ray front-loaded, and its claim — "a big Z-score with opposing momentum is NOT a regime call" — is now true for inflation and false for growth. Rewritten as "the two chips do not read momentum the same way", keeping the inflation example intact and naming the new opposite-direction mistake: waiting for acceleration before calling a Growth regime. Added the line that actually explains why this matters — *expansions spend most of their life not accelerating*.

Also in the guide: L8's "the chips flip to Transition early and often" now qualified per chip (inflation still does by design, growth is steadier since it went level-only, so a growth flip is a bigger event than it was); L3's live box now shows the sub-state inline ("Growth · Growth (flat)"); and the canonical inflation window was documented as **96** when the implemented default is **90** — Ray called for 96 and 90 is the nearest slider option, which is now what it says.

**Methodology — §8 plus two older bugs found while sweeping.** §8's narrative, both rule tables and the defaults line had already been updated in the implementation commit; this pass added the sub-state rows to the second (rendered) table, which only the copy-to-clipboard table had, and replaced the inflation "Neither threshold crossed" cell with the explicit condition now that the growth rows state theirs explicitly.

Two **pre-existing** staleness bugs surfaced that have nothing to do with this change:

1. **The glossary still described both chips as dual-condition** — "Inflation Regime ... classified independently using *the same* dual-condition logic" — in two separate copies (§1 and the duplicated glossary block). Both fixed.
2. **The page claimed dynamic thresholds are "opt-in and off by default"** in three places. They have been ON by default since **2026-07-09** (backtest G2 found dynamic >= fixed), so the page has been wrong about the dashboard's actual default for three months. Fixed, and the note now also spells out the consequence a reader needs: the gz/iz values on the sliders are a BASE that gets scaled per month, so the threshold actually classifying a given month is usually not the slider value — which is exactly the confusion that started this whole session. The historical Revision Log entries that say "dynamic thresholds stay opt-in" were left alone: they are a record of what was true in July, not a claim about now.

**In-app help text swept too** (not just the two docs pages): the Regime Thresholds modal intro, the Regime History help-panel chip row, and the stale code comment on the Regime Map info card explaining a 2026-08 symptom that the level-gated growth chip has since made impossible.

**Verification.** Full suite **729 passed**, zero exclusions. Rebuilt and checked live: User Guide L3 renders the new two-chip table with the per-chip pills and the live box reads "Growth · Growth (flat)"; Methodology §8 renders the sub-state rows, "ON by default since 2026-07-09", and the effective-vs-base note; the Regime Thresholds modal reads correctly for both sliders ("Growth Momentum **band** … does NOT gate the Growth chip" / "Unlike the growth band above, this still GATES the Inflation chip").

**Next.** Unchanged from the previous entry: the Signals-page threshold display (spawned as its own task) and the `gz` calibration question.
