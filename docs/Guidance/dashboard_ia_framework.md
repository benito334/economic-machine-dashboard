# Dashboard Information Architecture & Visual System

> Standing reference for where a new dashboard page or chart belongs, and how
> it should be styled. Written 2026-10 off the back of a UI/IA audit (nav had
> drifted into a grab-bag, chart polish was inconsistent, colors had drifted
> across files). Read this before adding a new page — it should remove the
> guesswork, not add process.

---

## Nav groups and what each one is for

| Group | Role | Current pages |
| :--- | :--- | :--- |
| **Overviews** | Entry points; the first thing someone looks at | Command Center, Overview, Relative Cycles |
| **Regime & Cycles** | The regime engine's own output — feeds or reads the Growth/Inflation chips or the debt-cycle stage classifier | Regime Map, Regime History, Debt Stress |
| **Monitors** | Curated, single-topic narratives that deliberately feed **no** composite (the `fed.*`/`market.*`/`order.*` "isolated force" convention) | Fed Monitor, Debt Cycle Monitor, Market Expectations, Regime Validator, Valuations & Bubbles, AI Capex Cycle |
| **Signals** | Per-force signal drill-down — the raw inputs, one page per force | All Signals index + Growth/Inflation/Rate/Credit/Volatility/Productivity |
| **Tools** | Power-user exploration or model-calibration surfaces, not glanceable reads | Workbench, Weight Audit, Weight History |
| **Reference / Admin** | Documentation, plus operator-only/admin tooling | User Guide, Methodology, Assets by Environment, Data Dashboard, Traffic |

Every group is a click-to-roll `<details>` (`_group()` in `dashboard/charting.py`).
There is no second kind of nav section — if you are adding a group, it rolls up
like the rest, and its rows are `_nl()` rows with an icon. Routes for pages
that have been merged away are kept in `_PAGE_MAP` as aliases pointing at
their new home, so old links don't 404: `/yield-curve` and `/central-bank`
→ Fed Monitor, `/valuations` → the Bubble Gauge page. When you rename a page,
rename the **label** and leave the module, route and `navlnk-*` id alone.

**Regime & Cycles vs. Monitors is the one distinction worth protecting.** Both
render charts and both sit in the main nav, but they answer opposite
questions: Regime & Cycles pages are what the engine concluded; Monitors
pages are a curated read that never touches the engine. A page that mixes
the two (e.g. a chart that's mostly narrative but also quietly feeds a
composite) is a sign the signal itself needs a decision, not that the nav
needs a seventh group.

## Where does the next thing go?

Walk this top to bottom; stop at the first "yes."

1. **Is it a new signal for a force that already has a composite?**
   → `Signals / {force}`, and the composite if it should feed one.

2. **Is it a cross-country comparative read (same metric, many countries)?**
   → Relative Cycles.

3. **Is it regime-engine or stage-classifier output** (feeds the
   Growth/Inflation chips, or the debt-cycle stage)?
   → Regime & Cycles.

4. **Is it a curated, single-topic narrative that deliberately feeds no
   composite** — the isolated-force convention (`fed.*`, `market.*`,
   `order.*`)?
   → Monitors, built from day one on the shared chart-card component (see
   below) — don't let a new Monitors page start out "plain" and get
   retrofitted later.

5. **Is it a power-user exploration surface, not a glanceable read?**
   → Tools.

6. **Is it documentation, or operator/admin-only?**
   → Reference / Admin, gated the same way Traffic and Weight
   Audit/History already are (`PUBLIC_MODE` / `_traffic.nav_visible()`
   patterns in `dashboard/charting.py`).

If nothing above fits cleanly, that's a sign the page is actually two
pages, or the taxonomy itself needs revisiting — don't force it into the
nearest group just to ship it.

## Chart styling — one component, used everywhere

`_chart_card()` (in `dashboard/shared_components.py`, promoted there from
`fed_monitor.py` in the 2026-10 rollout's Phase 3 — every Monitors/Signals
page imports it from there now) is the standard: fixed compact height, muted
grid, optional `fill="tozeroy"`, clean hover, rounded card border, plus
`hline`/`hline2` (horizontal reference lines) and `vline_x` (a single
vertical reference line, e.g. a "you are here" step marker) for the common
threshold/selection overlays. Every new chart-bearing page should use it
rather than hand-building a `go.Figure` — this is what Phase 4 (Signals
force-detail pages) and Phase 5 (Regime History) each retrofitted an old
stacked `make_subplots` mega-chart into.

Pass `columns=2` for a Monitor page's card grid — that is the house default
since 2026-10-06, and it is what the `mon-grid` class (theme.css) is sized
around: it zeroes each card's inline `min-width: 280px` so a column can take
its share, and collapses to one column under 900px. A fixed-column grid
WITHOUT that class forces sideways scroll on a phone. `_section()` also takes
`lead=` for content that belongs to the section but isn't one of its cards
(a chip row, an embedded panel).

Exception: **Tools** pages (Workbench, Weight Audit) are built for dense
interactive exploration — multi-series overlays, draggable zoom, correlation
heatmaps — and are reasonably exempt from the card treatment. The same
exemption applies to any page's chart that is **not genuinely single-series**
— a 2D scatter (Regime Map), a categorical/discrete display (a regime-label
strip), or a deliberate multi-line overlay meant for at-a-glance comparison
(Debt Stress's 7-component chart) all stay hand-built; forcing them into
individual cards would lose the comparison the chart exists to show, not
just restyle it. The 2026-10 Phase 5 scoping pass is the worked example —
read `docs/worklog.md` 2026-10-04 for the full per-page reasoning before
assuming a page's charts "should" convert. Everything
else should converge on it.

## Color — one palette, imported, not retyped

Canonical semantic set, named once in `dashboard/shared_components.py`:

| Name | Hex | Meaning |
| :--- | :--- | :--- |
| `BLUE` | `#4C9BE8` | rate / neutral-primary |
| `AMBER` | `#E8A317` | watch / flagged |
| `GREEN` | `#2e9e5b` | good / built / positive |
| `RED` | `#d9534f` | critical / negative |
| `GREY` | `#8a97a8` | muted / inactive |

Plus `FORCE_COLOR` (also in `shared_components.py`) for the six per-force
accent colors (growth/inflation/rate/credit/volatility/productivity) — these
are a distinct axis from the semantic set above (a force's identity color
isn't a good/bad judgment) but should still be imported from one place
rather than redefined per page.

**Rule:** if you're about to type a hex literal for "success/positive" or
"error/critical" in a new page, import `GREEN`/`RED` (or `AMBER`/`BLUE`/
`GREY`) from `shared_components` instead. If you need a new per-force
accent, add it to `FORCE_COLOR` rather than inventing a local constant.

---

A follow-up UI pass on 2026-10-06 consolidated the nav further (every group
a rollup; Yield Curve folded into Fed Monitor §①, Central Bank Monitor into
its §⑦, Valuations into the Bubble Gauge page; Case Study → Debt Cycle
Monitor, Validator Audit → Regime Validator) and made 2-wide the default
card grid. See `docs/worklog.md` 2026-10-06 (3) for the per-decision
reasoning, including why the term-structure chart is not a `_chart_card`.

*Full audit and rollout plan: see the 2026-10 "Dashboard IA Blueprint"
session — all 5 phases complete as of 2026-10-04 (nav regroup, color
consolidation, `_chart_card` promotion, the Signals force-detail retrofit,
and the Regime History retrofit + a color-consistency pass on
`relative_view.py`/`global_overview.py`). See `docs/worklog.md` 2026-10-04
for the Phase 5 scoping reasoning — not every chart-bearing page converts to
the card pattern, and that doc explains why each one did or didn't.*
