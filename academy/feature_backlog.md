# Academy → Dashboard Feature Backlog

> Dashboard features the **course wants** that don't exist (or only partly
> exist) today. The Academy does not silently grow the dashboard — a lesson
> that needs a new number or view logs it here, and the main project pulls
> from this list on its own schedule. Keep it current; move items to "Shipped"
> when the dashboard delivers them.
>
> Priority: **P1** = a planned lesson is blocked / badly served without it ·
> **P2** = would materially improve a lesson · **P3** = nice-to-have polish.

## Open

| # | Feature | Why the course wants it | Lesson | Priority | Notes |
|---|---|---|---|---|---|
| 1 | **Canonical debt-cycle overlay** — plot a country's stage timeline against Ray's archetypal debt-cycle shape | Lets M5 show how a real country "rhymes" with the template — the single most powerful visual for the long-term cycle | M5 | P2 | Archetype shape is a teaching construct (drawn in our own words from *Big Debt Crises*), not reproduced art. Could live on /debt-stress or a lesson-embedded chart. |
| 2 | **"8 measures of power" order composite** — big-cycle index from education / competitiveness / innovation / output / trade share / military / financial-center / reserve status | M7's changing-world-order lesson currently has only Gini + reserve share to point at; the fuller index is what makes "rise and decline" legible | M7 | P2 | Several measures need new WB/IMF signals (education, trade share) + the D4 governance slot. Big feature; scope carefully. Extends the existing order layer. |
| 3 | **Fill the D4 order slots (V-Dem governance + GPR)** | M7's internal-order (governance/wealth-gap) and external-order (geopolitical risk) lessons should run on live data, not "pending manual load" placeholders | M7 | P1 | Infrastructure already built — just needs the operator to drop the files (see `docs/manual_data.md`). Not a code task; a data-load task. |
| 4 | **Believability / confidence treatment** — surface how much to trust a read (signal agreement + data freshness + track record) as a first-class element | M10 teaches "don't trust one signal / weight by believability"; the dashboard should *show* trust, not just values | M10 | P3 | Partly exists (Chip Direction Agreement, is_stale flags). Could be consolidated into one "confidence" read per clock. |
| 5 | **Glossary surface** — a lesson-fed running glossary the /academy route can render and link terms to | Every lesson earns terms; students need one place to look them up | all | P2 | Course-side feature (lives in /academy), not a dashboard-data feature. Listed here so it isn't forgotten. |

## Shipped

_(none yet — move items here with the commit/date that delivered them)_
