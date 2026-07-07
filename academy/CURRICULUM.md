# The Academy — Course Charter & Curriculum

> **This is the charter for a side-project inside this repo.** It is to the
> Academy what [CLAUDE.md](../CLAUDE.md) is to the dashboard: read it first,
> and when in conflict with instinct, this file wins. A Claude session working
> on the course should operate in **course-builder mode** (pedagogy, writing,
> lesson design) — not dashboard-engineer mode — and stay inside `academy/`
> plus a new `/academy` route, touching the rest of the dashboard only to add
> a feature that a lesson genuinely needs (and only after logging it in
> [feature_backlog.md](feature_backlog.md)).

---

## What this is

An interactive **training course** — a real class, not a help page — that
takes someone with **zero finance or economics background** and teaches them
to read this dashboard the way Ray Dalio reads the world economy. By the end
they can look at any country and confidently read all three clocks (the
short-term regime, the long-term debt-cycle stage, the big-cycle order) and
explain what each is saying and why it matters.

It is the natural expansion of the existing in-app User Guide (`/guide`,
`dashboard/user_guide.py`) — but where the guide is a 9-lesson quick tour, the
Academy is a **structured curriculum with progression**: modules that build on
each other, a running glossary, understanding-checks, and a capstone. It draws
its authority from Ray's own published frameworks (mapped in
[ray_sources.md](ray_sources.md)).

## Who it's for

The **absolute beginner**. Assume the student:
- has never taken an economics or finance class;
- doesn't know what GDP, inflation, a bond, or a central bank *is*;
- is smart and curious but allergic to jargon and hand-waving;
- is looking at OUR dashboard and wants to understand what it's telling them.

If a lesson would lose a bright 15-year-old, it's too hard. If it would bore a
curious adult, it's too slow. Aim between.

## The one big promise

> "Economies aren't mysterious. They're **machines** — they work by simple
> rules of cause and effect, repeating over and over. Once you can see the
> machine, the news stops being noise and starts being a story you can read.
> You do not need a finance degree. You need the machine."

Everything serves that promise. (It's Ray's own framing — the *Economic
Machine* — and it's why a beginner course is even possible.)

## Pedagogy — the non-negotiable rules

1. **Teach on live data, always.** Every concept is anchored to a real number
   the student can see in the dashboard *right now*, for a real country. This
   is the Academy's superpower and the reason it lives in this repo, not a
   separate one. (Reuse the `user_guide.py` "live box" pattern.)
2. **Intuition before vocabulary.** Introduce the *idea* with a plain-language
   analogy first; name the technical term only after the student already feels
   what it means. Never lead with a definition.
3. **Household analogy, then scale up.** Almost every macro idea has a
   kitchen-table version (credit = spending more than you earn; a debt cycle =
   a family that borrows to spend, then has to cut back). Start there, then
   scale the *same* mechanism to a country. Ray does this; it works.
4. **Cause and effect, not memorization.** Always answer "and then what
   happens?" The student should be able to *predict*, not recite.
5. **Zero jargon debt.** Every term is defined in plain words on first use and
   added to the glossary. No term is ever used before it's introduced.
6. **Front-load the traps.** The three beginner traps the User Guide already
   identifies go in Module 0 and get reinforced: (a) a Z-score is a *distance
   from normal*, not a grade; (b) magnitude ≠ direction; (c) never read one
   dial alone. Add Ray's own: don't trust a single indicator; the machine can
   fool you at turning points.
7. **Check understanding, gently.** End each module with a light "what would
   you expect?" prompt or a one-question check on live data — never a graded
   exam. The goal is a click of understanding, not a score.
8. **Short lessons, clear arc.** Each lesson = one idea, ~5–10 minutes. A
   module = 2–4 lessons around a theme. Momentum matters more than coverage.
9. **Our words, our data.** Teach Ray's *frameworks and concepts* (which are
   freely teachable ideas) in original prose on our own numbers. **Never
   reproduce passages from his books** (copyright). Where we lean on the
   digitalray.ai "AI Ray," keep the "not vetted by the real Ray" disclaimer.

## Lesson anatomy (every lesson follows this shape)

1. **Hook** — a question or scene the student already cares about ("Why did
   everything cost more in 2022?").
2. **Intuition** — the household-scale version, in plain words.
3. **The mechanism** — cause → effect, scaled to a country. A diagram where it
   helps.
4. **In the dashboard** — the exact tool/number this maps to, shown on live
   data for a real country, with "here's how to read it."
5. **Try it** — a one-step exercise on live data ("open Brazil; is its debt
   clock in squeeze? why?").
6. **Check** — one "what would you expect?" question.
7. **New words** — the 1–3 glossary terms this lesson earned.

## The module arc (the curriculum)

The journey from zero to reading a country cold. Each module maps to real
dashboard surfaces (in **bold**) so the course and the tool stay in lockstep.

- **M0 — Orientation: the economy is a machine.** The promise, what you'll be
  able to do, the beginner traps. No numbers yet — just the mindset. → the
  **Command Center** as the destination they're working toward.
- **M1 — How the machine works (Ray's foundation).** Transactions → the whole
  economy is just people buying and selling. Add credit and you get cycles.
  The three forces: productivity (slow), the short-term debt cycle (5–8 yrs),
  the long-term debt cycle (50–75 yrs). → frames the whole dashboard.
- **M2 — Money, credit, and debt (the true basics).** What money is, what
  credit is (the most important and least understood idea), why borrowing
  creates cycles, what "deleveraging" means. Kitchen-table first. → sets up
  every debt tool.
- **M3 — The short-term clock: the two dials.** Growth and inflation as the
  two questions you ask about any economy right now. Reading the two chips.
  The four "seasons" as map geography, not a verdict. → **Regime Map**,
  **Command Center** regime strip.
- **M4 — The levers: interest rates and credit.** How central banks steer with
  the price of money; why rates + credit are the *mechanism* that links growth
  and inflation. Easy vs tight money. → **policy/rate + credit** cards.
- **M5 — The big wave: the long-term debt cycle.** Leveraging → squeeze →
  deleveraging → reflation. Why debt feels great on the way up and breaks on
  the way down. The "beautiful deleveraging." → **stage classifier**,
  **/debt-stress** timeline.
- **M6 — Debt stress and the sovereign squeeze.** Reading the stress gauge;
  private vs government debt (the two votes); the SOVEREIGN SQUEEZE early
  warning and why a headline can say "reflation" while pressure builds
  underneath. → the 2026-07 two-vote rework.
- **M7 — The biggest cycle: the changing world order.** Wealth gaps inside a
  country (internal order) and the rise/decline of great powers + reserve
  currencies (external order). Why an empire's money is the last privilege it
  loses. → **order layer** (Gini, COFER, the D4 governance/GPR slots).
- **M8 — The slow force: productivity.** Why productivity is the only thing
  that raises living standards over the long run, and how to tell "real"
  growth from "borrowed" growth. → **productivity vs cycle** card.
- **M9 — Reading a country on all three clocks at once.** Synthesis: put the
  short-term, long-term, and big-cycle reads together. Then: which countries
  are at *different* points (the diversification payoff). → **Command Center**
  + **Relative Cycles**.
- **M10 — Thinking like Ray.** How to actually use all this without fooling
  yourself: believability (weight track records, not volume); don't trust one
  signal; be radically open to being wrong; pain + reflection = progress.
  → the mindset that makes the tools safe to use.
- **Capstone — Read a country cold.** The student picks a country and narrates
  all three clocks in their own words. The course "final."

## Delivery

- **Content source of truth** = markdown in `academy/lessons/NN-title.md`
  (reviewable, diffable, and exportable to a site/PDF later).
- **In-app** = a new `/academy` route (`dashboard/academy.py`) that renders the
  lessons as a progressive class on live data, with module navigation, a
  glossary, and understanding-checks. Build on `user_guide.py`'s live-data
  pattern. `/guide` becomes the quick-reference (or is absorbed once the
  Academy covers it).
- **Feature feedback** = anything a lesson needs that the dashboard lacks goes
  in [feature_backlog.md](feature_backlog.md) for the main project to pull —
  the Academy does not silently grow the dashboard.

## Done-criteria (what "good" looks like)

- A true beginner can finish M0–M9 and then, at the capstone, open a country
  they've never looked at and correctly narrate its three clocks.
- Every lesson shows live data and defines every term it uses.
- No book text is reproduced; every Ray concept is taught in original prose
  and cross-referenced in [ray_sources.md](ray_sources.md).
- The `/academy` route works end-to-end for at least one country, then all.

## How to work on this (for a future session)

1. Read this charter + [ray_sources.md](ray_sources.md).
2. Pick a module. Draft its lessons as markdown in `lessons/` following the
   lesson anatomy above.
3. If a lesson needs a dashboard number/tool that doesn't exist, log it in
   [feature_backlog.md](feature_backlog.md) — don't build it inline.
4. Wire drafted lessons into `/academy` on live data.
5. Keep [ray_sources.md](ray_sources.md) and the feature backlog current.
