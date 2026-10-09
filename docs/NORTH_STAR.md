# North Star — what this project is for, and how we decide

Agreed with the owner on 2026-10-09. **This is the document every other decision
gets justified against.** If something in this repo conflicts with this file,
this file wins and the other thing is a bug.

---

## 1. The goal, in one sentence

> **Accurately understand the world through the lens of Ray Dalio's macro
> investing — the market's forces, stressors and fundamentals — in an
> academically validated way, using mechanistic and documented methodologies
> that survive scrutiny. That understanding is then used to make macro-level
> investment decisions.**

Read the order of that sentence carefully, because it settles most arguments:

- **Understanding is the goal.** Not the dashboard, not a signal count, not a
  pretty chart. The dashboard is an instrument for understanding.
- **Investment decisions are the downstream use.** They matter — real money —
  but they are what the understanding is *for*, not what it is *measured by*.
- **The standard is academic.** "It looks right" is not a reason. "It survives
  outside scrutiny" is.

### What this rules out

Three things that would otherwise look like progress:

1. **Being actionable at the cost of being right.** If the honest answer is "we
   can't tell", that is the answer. We say it and we say why.
2. **Accepting a number because it is ours.** Every method has to be defensible
   to someone who did not build it and would enjoy finding a hole in it.
3. **Confidence that the evidence does not support.** A reading that *sounds*
   decisive but rests on one episode is worse than no reading, because someone
   will act on it.

---

## 2. The decision test

Before any change that affects what a number means, answer these five. If any
answer is weak, say so out loud rather than proceeding quietly.

| # | Question | Why it is on the list |
| :-- | :--- | :--- |
| 1 | **Does it measure what we claim?** Right units, right frequency, no circularity. | The most common silent failure. We have shipped a forecast in the wrong units' worth of near-misses. |
| 2 | **Can we state the mechanism?** Not "it correlates" — *why* it moves. | A correlation without a mechanism is a coin flip waiting to disappoint. |
| 3 | **What is the evidence?** A paper, an established convention, or our own measurement with numbers attached. | The owner's explicit standard: decide, but show the evidence. |
| 4 | **Would an outsider agree?** Given our data, would a reviewer reach the same conclusion? | This is what "survives scrutiny" means operationally. |
| 5 | **What can it NOT support?** State the limit in the same breath as the claim. | Every claim has a boundary. Unstated boundaries are how people get hurt. |

### The tie-break

**When being honest and being useful conflict, honest wins.** Then we say
plainly what the honest answer costs in usefulness, so the owner can decide
what to do about it.

---

## 3. Methodology guardrails

Hard-won on 2026-10-08/09. Each one caused a real wrong answer before it became
a rule. Check these specifically — they are the traps this project actually
falls into.

**Re-measure before implementing anything written in a previous session.** A
stale to-do is a hypothesis, not an instruction. Three items in one day turned
out to be aimed at the wrong target once re-measured.

**Overlapping windows inflate significance.** Rolling a 12-month forward return
monthly means each observation shares 11 months with its neighbour. It makes
p-values look wonderful and they are not real. Sample independently.

**Correlated units are not independent observations.** Eleven countries that
co-move are worth about two. Use the design-effect correction, never a raw count.

**Check for shared construction before quoting a fit.** If two series are built
from an overlapping ingredient, a high R² is arithmetic, not discovery. Prefer
whichever test case has no overlap.

**Separate "our measurement is broken" from "the world is like this."** These
feel identical from the inside. The question that splits them: *if I change
only our method, does the finding move?*

**A displayed control that no longer governs anything is a lie.** Remove it, do
not leave it inert.

**One definition, read everywhere.** Never recompute a stored quantity in a
second place. It will drift, silently, and both numbers will look plausible.

---

## 4. What the owner gets from me

The owner is not a specialist in these methodologies and should not have to be.
If an explanation cannot be followed, it cannot be checked, and an unchecked
method is exactly what this project exists to avoid.

**Every significant piece of work comes back with:**

1. **A plain-language summary first.** What changed and what it means, in
   ordinary words, before any numbers or code.
2. **A clear recommendation.** Not a survey of options with a shrug. If there
   is a real fork, I say which way I would go and what it costs if I am wrong.
3. **The link to this goal.** Which part of "understand the world accurately"
   this serves, stated explicitly.
4. **The evidence.** A citation, a convention, or a measurement with numbers.
   Never "this seemed reasonable."
5. **The limits.** What it still cannot tell us.

**Jargon rule:** a term gets defined the first time it appears in a reply, in a
clause, or it does not get used. "Effective sample size" becomes "how many
genuinely independent observations we really have, which is fewer than the row
count when the data points are related."

---

## 5. How decisions are recorded

Significant decisions become an **ADR** in `docs/decisions/` — the existing
format, with three sections added. Template:
`docs/decisions/ADR-TEMPLATE.md`.

Significant means: it changes what a published number means, changes a
threshold or weight, adds or retires a signal, or changes what the system
claims it can do. Routine implementation does not need one.

Every ADR must answer **"how does this serve the North Star?"** in plain
language. If that section is hard to write, that is information: the change may
not be serving the goal.

---

## 6. Where this lives

- This file is the source of truth.
- `CLAUDE.md` carries the goal verbatim at the top so it is loaded into context
  at the start of every session and cannot be lost.
- Every ADR links back here.
- When the goal itself changes, it changes **here first**, and the owner says so
  explicitly. I do not quietly reinterpret it.
