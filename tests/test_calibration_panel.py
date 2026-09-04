"""The corpus-wide calibration chart, and the per-species spread beside it.

Etienne, 2026-09-03, on the confidence column: he wanted the distribution and
not one number. That is two halves. The chart here is the corpus half, measured
already and until now drawn only on the internal page; the species table's
middle-half column is the per-species half.

    .venv/bin/pytest tests/test_calibration_panel.py
"""

from __future__ import annotations

import pytest


@pytest.fixture
def bins(explain):
    """Three real bands, rising, with a band nobody landed in.

    The band keys come from `explain.CONF_BAND_WORDS` rather than being typed,
    because the panel looks each one up and a retyped band would fail here for
    the wrong reason. The empty band is the case that divides by zero if a
    share is taken without checking, and it is a real state: nothing forces a
    frame into every confidence band.
    """
    keys = list(explain.CONF_BAND_WORDS)
    return [(keys[0], 100, 20), (keys[1], 0, 0), (keys[-1], 400, 380)]


def _ctx(panels, bins):
    class C:
        bins_all = bins
    return C()


def test_the_panel_draws_one_bar_per_band(panels, bins):
    out = panels.p_calibration(_ctx(panels, bins))
    assert out.count("<rect") >= len(bins)


def test_an_empty_band_reads_n_a_rather_than_dividing_by_zero(panels, bins):
    out = panels.p_calibration(_ctx(panels, bins))
    assert "n/a" in out


def test_the_panel_counts_every_graded_frame(panels, bins):
    """The population, printed, because a rate without its denominator is the
    thing this repo refuses to publish."""
    out = panels.p_calibration(_ctx(panels, bins))
    assert "500" in out


def test_the_bar_labels_carry_their_own_frame_count(panels, bins):
    out = panels.p_calibration(_ctx(panels, bins))
    assert "of 400 frames" in out


def test_no_bar_label_smuggles_an_unrendered_entity(panels, bins):
    """`&middot;` inside an SVG text label came back escaped and printed
    literally on both pages. Plain words instead."""
    out = panels.p_calibration(_ctx(panels, bins))
    assert "&amp;" not in out


def test_the_panel_is_a_balanced_details_block(panels, bins):
    out = panels.p_calibration(_ctx(panels, bins))
    assert out.count("<details") == out.count("</details") == 1


def test_the_external_page_draws_the_chart_it_already_measured(pagemod):
    """The measurement was verified against confidence_calibration.csv on this
    page's own build and then drawn only on the other page."""
    assert "calibration" in pagemod.EXTERNAL_PANELS
    assert pagemod.PANELS["calibration"][0] == "explanations"


def test_the_internal_page_does_not_draw_it_twice(pagemod):
    """The queue page has its own calibration block, with the rare-species
    breakdown this one does not carry."""
    assert "calibration" not in pagemod.INTERNAL_PANELS
