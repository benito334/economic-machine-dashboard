# Post Signals / Regime Classifier Code Review — 2026-06-25

Scope: commits after `4ffbfbe` (`Fix pipeline failure propagation`) through `cd0a320`, covering the new Signals page, Weight Audit/History pages, Regime Classifier, expanded rolling Z-score windows, ECB/EZ data additions, and recent Regime History navigation changes.

Review type: code, dashboard callback, persistence, configuration, and test review. Findings remediated on 2026-06-25.

## Findings

### 1. High — Current test suite is red after Regime History callback signature drift

`pytest -q` currently fails three Regime History stepper tests because `dashboard.charting.update_regime_step()` now expects seven positional arguments, while the tests still call it with six.

Locations:

- `dashboard/charting.py:2597-2614`
- `tests/test_charting.py:822-848`

Failure:

```text
TypeError: update_regime_step() missing 1 required positional argument: 'current_step'
```

Why this matters: the repo no longer has a green baseline. Even if the live Dash callback wiring is correct, CI/local validation will fail until the tests are updated. This also masks future failures because the suite stops being a reliable release gate.

Recommended fix: update the unit test invocation to include the new `page_trigger` argument in the correct position, and add a regression case for the new page-visit reset behavior.

Resolution: updated the stepper unit test calls for the current callback signature; the routed stepper test group now passes.

### 2. Medium — Regime History stepper still bounds navigation using US composite history

`update_regime_step()` does not accept `country-store` and calls `load_composite_history(start_date=start, end_date=end)` without a `country` argument in both the nav-event path and the button path. The rest of the Regime History/Map callbacks were made country-aware, but this shared step-index callback still computes `n` from the default US history.

Locations:

- `dashboard/charting.py:2597-2605`
- `dashboard/charting.py:2639`
- `dashboard/charting.py:2648`

Why this matters: when the user is viewing EZ or KR, prev/next bounds can be computed from US rows. If country histories differ in length or date coverage, navigation can clamp incorrectly, skip valid country-specific points, or allow stale indices that downstream country-aware panels then reinterpret.

Recommended fix: add `Input("country-store", "data")` or `State("country-store", "data")` to the callback, pass `country=country` into both `load_composite_history()` calls, and update tests to cover a non-US country with a different history length.

Resolution: `update_regime_step()` now receives the active `country-store`, resets the step index when the country changes, and passes `country=country` into both history lookups. Added a KR-specific bounds regression test.

## Verification

- `pytest -q`: passed after remediation — 354 passed, 6 warnings
- `python3 -m compileall -q indicators dashboard tests`: passed
- `git diff --check`: passed

## Notes

- The working tree was clean at review start.
