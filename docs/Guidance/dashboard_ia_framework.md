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
| **Regime & Cycles** | The regime engine's own output — feeds or reads the Growth/Inflation chips or the debt-cycle stage classifier | Yield Curve, Regime Map, Regime History, Debt Stress |
| **Monitors** | Curated, single-topic narratives that deliberately feed **no** composite (the `fed.*`/`market.*`/`order.*` "isolated force" convention) | Fed Monitor, Case Study Monitor, Market Expectations |
| **Signals** | Per-force signal drill-down — the raw inputs, one page per force | All Signals index + Growth/Inflation/Rate/Credit/Volatility/Productivity |
| **Tools** | Power-user exploration or model-calibration surfaces, not glanceable reads | Workbench, Weight Audit, Weight History |
| **Reference / Admin** | Documentation, plus operator-only/admin tooling | User Guide, Methodology, Assets by Environment, Data Dashboard, Valuations, Traffic |

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

Fed Monitor's `_chart_card()` (in `dashboard/fed_monitor.py`, reused directly
by `case_study_monitor.py` and `market_expectations.py`) is the standard:
fixed compact height, muted grid, optional `fill="tozeroy"`, clean hover,
rounded card border. Every new chart-bearing page should use it (or the
promoted shared version once Phase 3 of the 2026-10 rollout lands it in
`shared_components.py`) rather than hand-building a `go.Figure`.

Exception: **Tools** pages (Workbench, Weight Audit) are built for dense
interactive exploration — multi-series overlays, draggable zoom, correlation
heatmaps — and are reasonably exempt from the card treatment. Everything
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

*Full audit and rollout plan: see the 2026-10 "Dashboard IA Blueprint"
session. Phases 1–2 (nav regroup + color consolidation) are complete as of
this writing; Phase 3 (promote `_chart_card` into `shared_components.py`)
and Phases 4–5 (retrofit Signals, then Regime & Cycles/Overview pages) are
still open.*
