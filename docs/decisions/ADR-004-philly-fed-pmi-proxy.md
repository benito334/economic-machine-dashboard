# ADR-004: Philly Fed Manufacturing Survey as US PMI Proxy

**Date:** 2026-06-18
**Status:** Accepted

## Context

The spec lists `growth.pmi_proxy` as `GACDISA066MSFRBPHI` (Philadelphia Fed Manufacturing Business Outlook Survey, General Activity Diffusion Index). This is a **regional** US survey, not a national PMI.

National PMI options:
- **ISM Manufacturing PMI** (`NAPM` on FRED — verify): published by the Institute for Supply Management; the gold standard US national manufacturing PMI.
- **S&P Global / Markit US Manufacturing PMI:** available via FRED (`MSPMI` — verify); monthly; free with lag.
- **Philly Fed:** available same-day as release; well-correlated with ISM; longer free FRED history.

## Decision

Use **Philly Fed (`GACDISA066MSFRBPHI`)** as the primary binding for `growth.pmi_proxy`, with `is_proxy=true` flagged at the `CountryBinding` level.

Additionally, add **ISM Manufacturing (`NAPM`)** as a secondary series in the same lens for cross-validation, also with verification.

## Rationale

- Philly Fed is on FRED with a long, clean history and no additional keys needed.
- The high correlation with ISM (~0.85 historically) makes it a valid proxy for leading-indicator purposes.
- `is_proxy=true` is set so the dashboard signals to users that this is not a national composite.
- ISM (`NAPM`) should be verified and added as a cross-check indicator — if they diverge significantly, the Conflict Panel should flag it.

## Consequences

- `us_bindings.yaml` must set `is_proxy=true` for `growth.pmi_proxy`.
- Dashboard tooltip (`linkage`) must note: "Philly Fed Manufacturing Outlook; regional proxy for US manufacturing sentiment; correlated ~0.85 with ISM."
- ISM (`NAPM`) series ID must be verified against FRED before adding as secondary.
- For Phase 2 (non-US countries), national PMIs (S&P Global/Caixin/Tankan) will be used where available via FRED or direct source; `is_proxy` set per binding.
