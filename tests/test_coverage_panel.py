"""The crop-coverage sweep, on the page rather than only in the file.

`measure.py` swept the coverage bars on every build and `coverage_gate.csv`
carried the answer, while the page published the ungated rate alone. The house
rule is that a gated number travels beside its ungated twin, so the sweep is now
a panel.

    .venv/bin/pytest tests/test_coverage_panel.py
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def sweep(core):
    """One row a bar, rising, shaped like `core.coverage_gate_stats` returns.

    The bars come from `core.CROP_COVERAGE_SWEEP` rather than being typed, so a
    changed sweep fails on the panel and not on this fixture's arithmetic.
    """
    rates = (0.80, 0.84, 0.85, 0.86)
    counts = (3190, 2515, 2065, 1315)
    species = (184, 170, 158, 135)
    return [{"min_coverage": t, "n_admitted": n, "n_rejected": 0,
             "n_correct_top1": int(n * r), "micro_top1": r,
             "macro_top1": r - 0.28, "n_species": s}
            for t, n, r, s in zip(core.CROP_COVERAGE_SWEEP, counts, rates, species)]


def _ctx(sweep, dropped=None):
    return SimpleNamespace(
        n=3277, coverage_sweep=sweep,
        coverage_dropped=dropped or {"n": 49, "max": 6, "median": 1})


def test_the_panel_draws_one_row_per_bar(panels, sweep):
    out = panels.p_coverage(_ctx(sweep))
    assert out.count("<tr") == len(sweep) + 1


def test_the_lowest_bar_is_worded_as_a_presence_test(panels, sweep):
    """0% reads like a bar nothing can clear. The row admits any recorded
    overlap at all, which is a condition a reader can check a frame against."""
    out = panels.p_coverage(_ctx(sweep))
    assert "any of the crop" in out
    assert "<td>0% of the crop</td>" not in out


def test_every_rate_carries_the_frames_it_was_counted_off(panels, sweep):
    out = panels.p_coverage(_ctx(sweep))
    for row in sweep:
        assert f'{row["n_admitted"]:,}' in out


def test_the_summary_states_the_cost_beside_the_gain(panels, sweep):
    """A sweep that reports only the rising rate is the gated half on its own."""
    out = panels.p_coverage(_ctx(sweep))
    assert "1,875" in out  # 3,190 admitted at the lowest bar, 1,315 at the highest


def test_the_frames_in_no_row_at_all_are_counted(panels, sweep):
    """87 frames clear no bar: no crown geometry, or the largest crown inside
    the crop carries a different species. A denominator that appears in no row
    is the one a reader cannot reconstruct."""
    out = panels.p_coverage(_ctx(sweep))
    assert "87 of the 3,277" in out


def test_the_species_climb_is_attributed_to_the_species_leaving(panels, sweep):
    """The per-species column rises fastest because small species drop out. The
    panel renders how small they are rather than asserting the conclusion."""
    out = panels.p_coverage(_ctx(sweep))
    assert "49" in out and "at most 6" in out


def test_the_panel_links_the_file_the_bars_were_swept_into(panels, sweep):
    out = panels.p_coverage(_ctx(sweep))
    assert 'href="coverage_gate.csv"' in out


def test_the_panel_reaches_the_public_page(pagemod):
    """It was measured on every build and reached no page, which is the state
    this panel exists to end."""
    assert "coverage" in pagemod.EXTERNAL_PANELS
    assert pagemod.PANELS["coverage"][0] == "explanations"


def test_the_figure_sweeps_every_bar_and_sizes_what_the_top_bar_loses(figures, core):
    """A panel reads a figure, it never computes one, so the arithmetic behind
    the caveat is tested here. `b` clears every bar and `a` clears only the
    lowest, so `a` is what the top bar costs and its two labelled frames are the
    number the caveat renders."""
    recs = ([{"gt": "a", "ranked": [("a", 1.0)], "crop_coverage": 0.1,
              "crop_dominant": "a"}] * 2
            + [{"gt": "b", "ranked": [("b", 1.0)], "crop_coverage": 1.0,
                "crop_dominant": "b"}] * 40)
    per_species = [{"species": "a", "n_labelled_frames": 2},
                   {"species": "b", "n_labelled_frames": 40}]
    fig = figures._coverage_sweep(recs, per_species)
    assert [r["min_coverage"] for r in fig["coverage_sweep"]] == list(core.CROP_COVERAGE_SWEEP)
    assert fig["coverage_dropped"] == {"n": 1, "max": 2, "median": 2}


def test_the_figure_describes_no_dropped_species_without_inventing_a_median(figures):
    """Every species clearing the highest bar is a real state, and a median over
    an empty list raises rather than returning zero."""
    recs = [{"gt": "b", "ranked": [("b", 1.0)], "crop_coverage": 1.0,
             "crop_dominant": "b"}]
    fig = figures._coverage_sweep(recs, [{"species": "b", "n_labelled_frames": 1}])
    assert fig["coverage_dropped"] == {"n": 0, "max": None, "median": None}
