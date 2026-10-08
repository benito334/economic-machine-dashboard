"""Methodology stamp for composite rows — what rule produced this number.

Why this exists
---------------
`composites` is deliberately rewritten in full on every pipeline run: when a
threshold, weight or formula changes, we want ALL of history re-read under the
current rule, so every month is comparable to every other month. That is the
right behaviour for a diagnostic dashboard and nothing here changes it.

What it cost us was traceability. A downstream consumer that refits a model
each month (CreovaOne's macro betas, 2026-10-07) sees the inputs move and
cannot tell "the world changed" from "the Indicators Machine changed its mind".
Two stamps make that distinguishable without freezing anything:

  methodology_version — manual, bumped when a FORMULA or rule changes. Reads
                        like the Methodology page's revision log, because it is
                        keyed to the same events.
  config_hash         — automatic, a digest of the config that actually feeds
                        the numbers. Catches what a manual version never will:
                        a weight edited through the Weight Audit importance
                        editor, or a GDP-regression recalibration, neither of
                        which touches a version string. `weight_change_log`
                        already holds 10 such US changes since 2026-07-05.

Rule: bump METHODOLOGY_VERSION whenever a change would alter a historical
composite value for reasons OTHER than new data. The config hash moves on its
own; you do not maintain it.
"""
from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# ── The manual version ───────────────────────────────────────────────────────
# Date-keyed to the Methodology page's Section 15 revision log, so a stamp can
# be traced to the entry that explains it. Bump on formula/rule changes only.
#
#   2026.10.07  `confidence` REDEFINED: was agreement with the retired
#               four-season quadrant (off a raw `score >= 0` sign split that
#               ignored thresholds); now Chip Direction Agreement — share of
#               the basket moving with the chip's heading, invert-aware, over
#               the contributing signals only. New per-force
#               growth/inflation_dir_agreement columns.
#   2026.10.06  Growth chip made level-gated; momentum demoted to an
#               annotation. gm 0.05 -> 0.04. Inflation chip unchanged.
#   2026.10.03  gm/im momentum gates raised 0.0 -> 0.05; sustained-months
#               filter and dynamic-threshold floor added.
#   2026.07.10  Composite age-decay made release-schedule-aware.
#   2026.07.06  Canonical rolling windows (48m growth / 90m inflation);
#               confidence redefined as Chip Direction Agreement.
METHODOLOGY_VERSION = "2026.10.07"


# ── The automatic fingerprint ────────────────────────────────────────────────
# Only files whose CONTENT changes a composite value belong here. Bindings are
# deliberately excluded: they decide which series is fetched, not how it is
# scored, and they churn for reasons (a corrected FRED id, a new comment) that
# do not move a single number.
def _fingerprint_paths(country: str) -> list[Path]:
    cc = (country or "US").lower()
    # Every country, US included, lives under config/countries/ — matching
    # composites.load_composites_config. There is no config/us_composites.yaml.
    return [
        _CONFIG_DIR / "composites_policy.yaml",
        _CONFIG_DIR / "countries" / f"{cc}_composites.yaml",
    ]


@lru_cache(maxsize=32)
def config_hash(country: str = "US") -> str:
    """12-hex digest of the config driving this country's composites.

    Missing files hash as empty rather than raising: a stamp must never be the
    reason a pipeline run fails. A country with no composites file does not
    reach this code anyway (the pass is skipped upstream).
    """
    h = hashlib.sha256()
    for path in _fingerprint_paths(country):
        try:
            h.update(path.read_bytes())
        except OSError as exc:
            logger.warning("[methodology] could not read %s for fingerprint: %s", path, exc)
            h.update(b"")
    return h.hexdigest()[:12]


def methodology_stamp(country: str = "US") -> dict:
    """{'methodology_version': ..., 'config_hash': ...} for one country."""
    return {
        "methodology_version": METHODOLOGY_VERSION,
        "config_hash": config_hash(country),
    }
