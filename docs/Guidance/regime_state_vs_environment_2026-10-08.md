# One series, three readings — why the chip and the box disagree, and why that is correct

**Date:** 2026-10-08
**Read this before** changing the regime chip, the beta inputs, or anything that calls either
of them a "regime". It exists to stop one specific argument being re-litigated.

---

## The argument it settles

The Indicators Machine says the economy is in **Transition** most of the time — 58% of months
on the growth axis, 82% on inflation, and the joint four-season state holds only 8%. All of
that is measured, reproducible, and correct.

CreovaOne assigns every asset to one of four All-Weather boxes and finds that **Transition
never occurs** — the four boxes cover 100% of months, 26.4 / 22.7 / 25.6 / 25.4. That is also
measured, reproducible, and correct.

Both numbers are right. They are not two answers to one question.

---

## The two objects

| | Indicators Machine chip | CreovaOne box |
| :--- | :--- | :--- |
| Question it answers | *Where is the economy now, vs its own history?* | *Did growth/inflation come in above or below what was priced?* |
| What it measures | a **level** | a **deviation** |
| Does it have a middle? | **Yes — legitimately** | **No — structurally** |
| Consumer | humans reading the dashboard | the beta regression |

**A level has a real middle.** "Growth is neither strong nor weak" is a true description of
the world, not a measurement failure. The Transition band is the honest answer to a level
question, and the fact that it is the modal answer is a fact about economies, not a defect.

**A deviation has no middle.** The sign of a continuous variable is positive or negative with
probability 1. There is no band to draw, so no transition can appear — not because the
measurement is better, but because the question does not admit one.

---

## For the box assignment there IS a right answer, and it is the deviation

This is not a matter of taste. It follows from asset pricing: **prices already embed the
expected state.** A bond does not care that inflation is 3%; it cares that inflation came in
above the 3% that was already discounted. The thing that moves an asset is inherently a
deviation — so the regressor has to be one, and deviations have no neutral category.

Ray ruled exactly this on 2026-10-07 (`ray_dalio_review_log.md`):

> Condition on the **SURPRISE**; the level is the discounted part, not the deviation.

The data agrees. Gold is the clean test — it is not mechanically tied to any of these
regressors. Full history, standardized OLS:

| basis | gold R² | LT bond R² |
| :--- | ---: | ---: |
| **Level** (the state) | 0.011 | 0.016 |
| **Change** (Δ state) | **0.022** | 0.034 |
| Discounted (Δ breakeven) | 0.018 | 0.261 ⚠ see caveat |

**The level is the weakest regressor for both assets**, which is what "the level is the
discounted part" predicts. So CreovaOne is right not to consume the chip, and right to use
changes.

> ⚠ **The LT-bond 0.261 is substantially mechanical — do not act on it.** The bond return
> proxy is `−7.5·Δ(nominal 10y)`, and breakeven = nominal − TIPS, so the two share the
> `Δ(nominal 10y)` term. `corr(Δ nominal 10y, Δ breakeven) = 0.507`. An earlier draft of
> `beta_classification_audit_2026-10-08.md` suggested promoting the `discounted_surprise`
> basis on the strength of this number; that suggestion is **withdrawn**.

---

## The unification

There is **one object** — the continuous (growth, inflation) composite pair. Three readings of
it, each with exactly one correct job:

| reading | question | middle? | correct job | status |
| :--- | :--- | :---: | :--- | :--- |
| **level** | where are we | **yes** | reading the machine — the chip | built; inflation leg miscalibrated |
| **first difference** | what just changed | no | beta input today | built, in production |
| **deviation from expected** | what was the *news* | no | **the right beta input** | **not built** |

Transition is a property of asking a level question. It was never missing from the other two
readings, and it cannot be added to them.

So nothing needs reconciling. A level reading and a derivative reading of the same series,
correctly used for different things. The only real error available here is using one for the
other's job — and neither project is doing that.

---

## Standing rules that follow

1. **Do not call both of them "regime."** The chip reports a **state**. The box reports an
   **environment**. One word doing two jobs generated this entire confusion and will generate
   it again. Use the two words in code, docs and UI.
2. **The chip must never become a beta input**, and the box must never be displayed as "what
   regime are we in." They are not substitutes at any threshold setting.
3. **"Transition is most of the time" is not an argument for a fifth All-Weather box.**
   Tested directly: betas keep the same sign across quiet and loud months and are simply 2–3×
   larger in the large-move tercile (`beta_classification_audit_2026-10-08.md` §2). Quiet
   months are the same relationship at lower signal-to-noise, not a distinct environment.
   The one real consequence is that an all-months OLS estimates roughly **half** the beta that
   applies in the months the box exists to hedge.
4. **`change` is a proxy for surprise, not surprise.** It conflates anticipated with
   unanticipated movement: if the market saw the change coming, there was no news. The genuine
   upgrade is realized-minus-consensus. `signals.surprise` is still 0 non-null of 368,225 rows;
   Philadelphia Fed SPF is already ingested for the validator badges and is the obvious input.
5. **Re-anchoring inflation to target moves the continuous series**, and therefore every
   fitted beta. Sequence that change *before* any beta recalibration, never after.
