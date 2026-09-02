"""The crop-coverage gate: what it admits, and what it refuses to assume.

`MIN_CROP_COVERAGE` asks a question none of the published rates ask -- does the
frame's own label fill at least half of the centre crop the model was sent --
and the pages only report its effect, in `coverage_gate.csv`.
`labelling/next_batch.py` is what actually filters on it.

Three properties matter. A frame whose crop is filled by some other species is
rejected however full that crop is: the coverage measured there belongs to a
tree the frame is not labelled with, so it answers a different question. That
is the same pair of tests `next_batch.crop_verdict` sends on, and the two have
to stay in step because they share the constant.

Two more properties had no test either. A frame with no measured geometry
is rejected, never assumed to pass: README says crop geometry comes from what
the fetch recorded, never a constant, and a gate that admitted unmeasured
frames would quietly break that. And the gated macro average is over a species
set that shrinks with the threshold, which is why `n_species` and `n_admitted`
travel with it.

    .venv/bin/pytest tests/test_coverage_gate.py
"""

from __future__ import annotations


def _rec(gt, guess, coverage, dominant=None):
    """One scored frame, in the shape `coverage_gate_stats` reads.

    `dominant` left None is the case `crop_overlap` records when no box touches
    the crop at all; such a frame carries 0.0 coverage and fails on that.
    """
    return {"gt": gt, "ranked": [(guess, 1.0)], "crop_coverage": coverage,
            "crop_dominant": dominant}


# ---------------------------------------------------------------------------
# coverage_split
# ---------------------------------------------------------------------------

def test_the_threshold_is_inclusive(core):
    at = _rec("a", "a", core.MIN_CROP_COVERAGE)
    under = _rec("a", "a", core.MIN_CROP_COVERAGE - 0.001)
    admitted, rejected = core.coverage_split([at, under])
    assert admitted == [at] and rejected == [under]


def test_a_frame_with_no_measured_coverage_is_rejected_not_assumed(core):
    """The whole point of the gate. None means the fetch recorded no geometry
    for that frame, and admitting it would publish a gated number over frames
    nobody measured."""
    admitted, rejected = core.coverage_split([_rec("a", "a", None)])
    assert admitted == [] and len(rejected) == 1


def test_zero_coverage_is_rejected_and_is_not_confused_with_no_measurement(core):
    """0.0 is a measurement: the labelled species covers none of the crop. It
    fails the gate like any other value under the line, and is not the same
    case as None, which is the absence of a measurement."""
    admitted, rejected = core.coverage_split([_rec("a", "a", 0.0)])
    assert admitted == [] and len(rejected) == 1


def test_a_crop_filled_by_another_species_is_rejected_however_full(core):
    """The coverage measured on such a frame is that other tree's share, not
    the label's. Admitting it would put a frame in the gated population on
    evidence about a species the frame is not labelled with."""
    other = _rec("a", "a", 0.9, dominant="b")
    own = _rec("a", "a", 0.9, dominant="a")
    admitted, rejected = core.coverage_split([other, own])
    assert admitted == [own] and rejected == [other]


def test_the_gate_asks_what_next_batch_sends_on(core):
    """`next_batch.crop_verdict` sends only rows whose crop dominant is the
    label and whose coverage clears the same constant. The two paths share the
    constant, so they have to share the question as well."""
    recs = [_rec("a", "a", 0.9, dominant="a"),    # send
            _rec("a", "a", 0.9, dominant="b"),    # other_crown
            _rec("a", "a", 0.1, dominant="a"),    # low_coverage
            _rec("a", "a", None, dominant=None)]  # unknown_geometry
    admitted, rejected = core.coverage_split(recs)
    assert [r["crop_dominant"] for r in admitted] == ["a"]
    assert len(rejected) == 3


def test_every_record_lands_on_exactly_one_side(core):
    recs = [_rec("a", "a", c) for c in (None, 0.0, 0.49, 0.5, 0.51, 1.0)]
    admitted, rejected = core.coverage_split(recs)
    assert len(admitted) + len(rejected) == len(recs)
    assert not ({id(r) for r in admitted} & {id(r) for r in rejected})


def test_the_threshold_can_be_swept(core):
    """Reported as a sweep, per the comment on MIN_CROP_COVERAGE, so the
    default must be an argument rather than baked into the comparison."""
    recs = [_rec("a", "a", c) for c in (0.2, 0.6, 0.9)]
    assert len(core.coverage_split(recs, 0.0)[0]) == 3
    assert len(core.coverage_split(recs, 0.5)[0]) == 2
    assert len(core.coverage_split(recs, 1.0)[0]) == 0


# ---------------------------------------------------------------------------
# coverage_gate_stats
# ---------------------------------------------------------------------------

def test_the_rates_are_measured_over_the_admitted_rows_only(core):
    """One species right on an admitted frame, another wrong on one, and a
    third right on a frame the gate rejects. The rejected frame must not reach
    either average."""
    stats = core.coverage_gate_stats([
        _rec("a", "a", 0.9),
        _rec("b", "wrong", 0.9),
        _rec("c", "c", 0.1),
    ])
    assert stats["n_admitted"] == 2 and stats["n_rejected"] == 1
    assert stats["n_correct_top1"] == 1
    assert stats["micro_top1"] == 0.5
    assert stats["macro_top1"] == 0.5
    assert stats["n_species"] == 2      # "c" is not in the gated population


def test_the_species_set_shrinks_with_the_threshold_and_says_so(core):
    """The docstring's warning, as a test: raising the gate drops species
    entirely, so macro_top1 is not comparable across thresholds without
    n_species beside it."""
    recs = [_rec("a", "a", 0.9), _rec("b", "b", 0.6)]
    assert core.coverage_gate_stats(recs, 0.5)["n_species"] == 2
    assert core.coverage_gate_stats(recs, 0.8)["n_species"] == 1


def test_the_two_averages_part_company_when_species_are_uneven(core):
    """Two frames of a species the model gets right and one of a species it
    gets wrong: two thirds of frames, half of species. The gap is the same one
    the weighting panel exists to explain."""
    stats = core.coverage_gate_stats([
        _rec("a", "a", 0.9), _rec("a", "a", 0.9), _rec("b", "wrong", 0.9)])
    assert stats["micro_top1"] == 2 / 3
    assert stats["macro_top1"] == 0.5


def test_an_empty_gate_reports_none_rather_than_zero(core):
    """A rate over no frames is not 0%. `ratio` returns None and the formatters
    print an empty cell, which is the repo's way of saying unmeasured."""
    stats = core.coverage_gate_stats([_rec("a", "a", 0.1)])
    assert stats["n_admitted"] == 0
    assert stats["micro_top1"] is None
    assert stats["macro_top1"] is None
    assert stats["n_species"] == 0


def test_the_threshold_travels_with_the_numbers(core):
    """A gated figure is meaningless without the line it was gated at, so the
    threshold is part of the result rather than something a caller remembers."""
    assert core.coverage_gate_stats([], 0.75)["min_coverage"] == 0.75
    assert core.coverage_gate_stats([])["min_coverage"] == core.MIN_CROP_COVERAGE
