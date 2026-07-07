# Ray Sources — Concepts → Lessons → Features

> The map from **Ray Dalio's published frameworks** to **which Academy lesson
> teaches each concept** to **what dashboard feature it relies on (or would
> need)**. This is both the course's intellectual backbone and its
> feature-discovery engine: concepts with no matching dashboard feature become
> candidates in [feature_backlog.md](feature_backlog.md).
>
> **Copyright discipline:** we teach Ray's *ideas and frameworks* — which are
> freely teachable — in our own words, on our own data. We do **not** reproduce
> passages, figures, or extended quotes from his books. Cite the source by
> title/idea; write original explanations. Where the course leans on the
> digitalray.ai "AI Ray," carry the standard "not vetted by the real Ray"
> disclaimer.

---

## The source works (what we draw on)

| Short name | Work | What it gives the course |
|---|---|---|
| **Economic Machine** | "How the Economic Machine Works" (Ray's ~30-min framework / booklet) | The beginner foundation: transactions, credit, the three forces, the two debt cycles. The backbone of M1–M4. |
| **Principles** | *Principles: Life and Work* | How to *think*: believability-weighting, radical open-mindedness, pain + reflection = progress, "the machine is knowable." Frames M0 and M10. |
| **Big Debt Crises** | *Principles for Navigating Big Debt Crises* | The archetypal long-term debt cycle, its stages, and the "beautiful deleveraging." The engine of M5–M6. |
| **Changing World Order** | *Principles for Dealing with the Changing World Order* | The biggest cycle: the rise/decline of empires, the measures of power, reserve-currency lifecycles, internal vs external order. The engine of M7. |
| **Review log** | `docs/Guidance/ray_dalio_review_log.md` (our digitalray.ai consults) | Where AI-Ray's rulings shaped THIS dashboard — useful "here's why the tool is built this way" asides. Disclaimer applies. |

## Concept map

Each row: a Ray concept → the lesson that teaches it → the dashboard feature it
uses. **Feature status:** ✅ exists · 🟡 partial · 🔦 candidate feature (logged
in the backlog).

| Ray concept | Source | Lesson | Dashboard feature | Status |
|---|---|---|---|---|
| The economy is a machine (knowable cause-effect) | Economic Machine; Principles | M0, M1 | The whole dashboard; Command Center as the "machine dashboard" | ✅ |
| Transactions are the building block (spending = money + credit) | Economic Machine | M1, M2 | — (teaching) | ✅ |
| Credit is the most important & least understood force | Economic Machine | M2 | Credit force cards | ✅ |
| The three forces: productivity, short-term & long-term debt cycles | Economic Machine | M1 | Regime + stage + productivity surfaces together | ✅ |
| Short-term debt cycle (~5–8 yrs), steered by the central bank | Economic Machine | M3, M4 | Regime chips, rate/credit levers | ✅ |
| Growth & inflation as the two questions | Economic Machine | M3 | Two-chip regime, Regime Map | ✅ |
| Interest rates as the price of money / the main lever | Economic Machine | M4 | policy.rate + real-rate signals | ✅ |
| Long-term debt cycle (~50–75 yrs): leveraging→squeeze→deleveraging→reflation | Big Debt Crises | M5 | Stage classifier, /debt-stress timeline | ✅ |
| The "beautiful deleveraging" (balanced mix that avoids collapse) | Big Debt Crises | M5 | stage = reflation read | ✅ |
| The **archetypal debt-cycle template** (a canonical shape crises rhyme with) | Big Debt Crises | M5 | 🔦 overlay our stage timeline on Ray's canonical arc | 🔦 |
| Debt-service burden as the earliest squeeze signal | Big Debt Crises | M6 | Debt-service-ratio card; BIS DSR gap (see signal guide) | 🟡 |
| Private vs government (sovereign) debt can diverge | Big Debt Crises; our 2026-07 rework | M6 | Two-vote stage split + SOVEREIGN SQUEEZE flag | ✅ |
| The big cycle: rise & decline of empires | Changing World Order | M7 | Order layer (partial) | 🟡 |
| Internal order — wealth/values gaps precede internal conflict | Changing World Order | M7 | order.gini; V-Dem governance (D4 slot) | 🟡 |
| External order — great-power conflict / geopolitical risk | Changing World Order | M7 | GPR (D4 manual-load slot) | 🟡 |
| Reserve-currency lifecycle ("last privilege an empire loses") | Changing World Order | M7 | order.reserve_currency_share (COFER) | ✅ |
| **The measures of a power's strength** (education, competitiveness, innovation/tech, output, trade share, military, financial-center, reserve status) | Changing World Order | M7 | 🔦 an "8-measures-of-power" composite for the order layer | 🔦 |
| Productivity as the only sustainable driver of living standards | Economic Machine; Changing World Order | M8 | Productivity trend vs cycle card | ✅ |
| "Borrowed" vs "earned" growth (debt-fuelled vs productivity-fuelled) | Economic Machine | M8 | productivity-vs-growth comparison | ✅ |
| Diversification: hold things at *different* points in their cycles | Big Debt Crises; Principles | M9 | Relative Cycles page + correlation heatmaps | ✅ |
| Believability-weighting (weight views by track record, not volume) | Principles | M10 | 🔦 a signal-confidence / track-record UI treatment | 🔦 |
| Don't trust a single indicator; watch the machine, not the number | Principles; Economic Machine | M0, M10 | Chip Direction Agreement; multi-signal composites | ✅ |
| Pain + reflection = progress; be radically open to being wrong | Principles | M10 | — (mindset) | ✅ |

## Candidate features this map surfaced (→ backlog)

These are Ray concepts the course wants to teach that the dashboard covers only
partially or not at all. Each is logged in [feature_backlog.md](feature_backlog.md):

1. **Canonical debt-cycle overlay** — plot our stage timeline against Ray's
   archetypal debt-cycle shape so students see how a real country "rhymes" with
   the template (teaches M5 viscerally).
2. **"8 measures of power" order composite** — a richer big-cycle index built
   from the measures in *Changing World Order* (education, innovation, output,
   trade share, military, financial-center, reserve status), extending today's
   Gini + reserve-share order layer (M7).
3. **Believability / confidence treatment** — surface how much to trust a read
   (signal agreement, data freshness, track record) as a first-class UI element
   (M10).
4. **Fill the D4 order slots** (V-Dem governance + GPR) so M7's internal/external
   order lessons run on live data rather than placeholders.

## Open questions for course design (resolve as we build)

- How deep to go on *Changing World Order*'s empire archetype for a pure
  beginner — probably a light, story-driven M7 with an optional "go deeper"
  appendix rather than the full 8-measures machinery up front.
- Whether M10 (thinking like Ray) is one module or threaded through as recurring
  "Ray's rule" callouts. Leaning: a short M10 *plus* callouts throughout.
- Glossary as a per-lesson accretion vs a standalone reference page (probably
  both: earn terms per lesson, collect them on a glossary page).
