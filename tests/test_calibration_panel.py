"""The corpus-wide calibration chart, and the per-species spread beside it.

The reviewer, 2026-09-03, on the confidence column: they wanted the distribution and
not one number. That is two halves. The chart here is the corpus half, measured
already and until now drawn only on the internal page; the species table's
middle-half column is the per-species half.

    .venv/bin/pytest tests/test_calibration_panel.py
"""

from __future__ import annotations

import pytest

# The plausible-name sweep the panel prints under the chart, in the shape
# `labelling/assess_species.py` writes it.
SWEEP = {"population": {"n_frames": 500, "n_species": 20},
         "method": {"n_folds": 5, "alpha": 0.1},
         "rows": [{"max_set_size": 1, "n_accepted": 400, "accept_rate": 0.8,
                   "accepted_accuracy": 0.95},
                  {"max_set_size": 3, "n_accepted": 500, "accept_rate": 1.0,
                   "accepted_accuracy": 0.9}],
         "grouped_rows": [{"max_set_size": 1, "n_accepted": 330, "accept_rate": 0.66,
                           "accepted_accuracy": 0.97},
                          {"max_set_size": 3, "n_accepted": 420, "accept_rate": 0.84,
                           "accepted_accuracy": 0.92}]}


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
        reject_sweep = SWEEP
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
    """Every block opened is closed, and the panel is the outermost one.

    The count used to be one apiece. The panel now carries a `more()` block, so
    the gate is balance and nesting rather than a single pair: an unclosed inner
    block swallows the rest of the page, which is the defect this catches.
    """
    out = panels.p_calibration(_ctx(panels, bins))
    assert out.count("<details") == out.count("</details") >= 1
    assert out.startswith("<details class=\"panel\"") and out.endswith("</details>")


def test_the_plausible_name_method_avoids_the_crop_coverage_word(panels, bins):
    """"coverage" is the crop-coverage panel's word elsewhere on this page, so
    the plausible-name method states its own rate in words instead: alpha 0.1
    reads as holding the right name 9 times in 10, split not fold."""
    out = panels.p_calibration(_ctx(panels, bins))
    assert "% coverage" not in out
    assert "in 5 splits of the frames" in out
    assert "holds the right one 9 times in 10" in out


def test_the_panel_links_the_file_its_bars_were_drawn_from(panels, bins):
    """A bar carries one rounded figure a band. The counts behind it are already
    on disk and already cross-checked against this panel's own build, so the
    file travels with the page rather than being named in a handover note."""
    out = panels.p_calibration(_ctx(panels, bins))
    assert 'href="confidence_calibration.csv"' in out


def test_the_external_page_draws_the_chart_it_already_measured(pagemod):
    """The measurement was verified against confidence_calibration.csv on this
    page's own build and then drawn only on the other page."""
    assert "calibration" in pagemod.EXTERNAL_PANELS
    assert pagemod.PANELS["calibration"][0] == "explanations"


def test_the_internal_page_does_not_draw_it_twice(pagemod):
    """The queue page has its own calibration block, with the rare-species
    breakdown this one does not carry."""
    assert "calibration" not in pagemod.INTERNAL_PANELS


def test_the_sweep_prints_the_new_flight_rate_beside_every_row(panels, bins):
    """The frame-by-frame rate leans on near-copies from the same flight, and
    the frames a queue orders are on new flights, so the two sit side by side."""
    out = panels.p_calibration(_ctx(panels, bins))
    assert "Frames kept, new flight" in out
    assert "66.0% (330)" in out and "97.0%" in out
    assert "84.0% (420)" in out and "92.0%" in out
