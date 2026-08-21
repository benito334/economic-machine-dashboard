"""Tests for the productivity-vs-cyclical-growth divergence read
(Ray Dalio consult, 2026-08-19 session)."""
import os

os.environ.setdefault("INDICATORS_TESTING", "1")

import math

from dashboard.force_detail import _productivity_divergence


def test_rising_productivity_soft_growth_is_early_advantage():
    note = _productivity_divergence(prod_z=0.6, growth_z=0.1, thresh_gz=0.5)
    assert note is not None
    assert note["label"] == "Early-stage competitive advantage"


def test_falling_productivity_strong_growth_is_unsustainable_watch():
    note = _productivity_divergence(prod_z=-0.6, growth_z=0.8, thresh_gz=0.5)
    assert note is not None
    assert note["label"] == "Unsustainable-expansion watch"


def test_aligned_productivity_and_growth_has_no_note():
    # both positive and both above threshold — no divergence
    assert _productivity_divergence(prod_z=0.7, growth_z=0.7, thresh_gz=0.5) is None
    # both negative / below threshold — no divergence
    assert _productivity_divergence(prod_z=-0.2, growth_z=-0.2, thresh_gz=0.5) is None


def test_missing_inputs_return_none():
    assert _productivity_divergence(None, 0.5, 0.5) is None
    assert _productivity_divergence(0.5, None, 0.5) is None
    assert _productivity_divergence(float("nan"), 0.5, 0.5) is None
    assert _productivity_divergence(0.5, float("nan"), 0.5) is None


def test_threshold_is_reused_from_gz_not_hardcoded():
    """A growth_z that clears a looser threshold shouldn't trigger 'soft
    growth' — the same gz threshold the Growth chip itself uses."""
    assert _productivity_divergence(prod_z=0.4, growth_z=0.6, thresh_gz=0.5) is None
    assert _productivity_divergence(prod_z=0.4, growth_z=0.4, thresh_gz=0.5) is not None
