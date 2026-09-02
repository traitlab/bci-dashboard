"""The two functions that decide what a reader is shown, at their boundaries.

`queue_of_prediction` sorts every unlabelled photo into the queue the send-first
page prints, and `bucket_label` sorts every species into the support band the
weighting panel charts. Both are pure, both are all thresholds, and neither had
a test: a boundary written `>` instead of `>=` moves photos between queues and
species between bands with nothing failing.

The thresholds are read from `core`, never restated here, so tuning one changes
what these tests assert rather than breaking them.

    .venv/bin/pytest tests/test_queueing.py
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# queue_of_prediction: four queues, first rule wins
# ---------------------------------------------------------------------------

def _q(queues, *, pred="Sp x", conf=0.9, n=None, acc=None):
    """One call, with support and accuracy given only when the case needs them.

    `n=None` means the species is absent from `support`, which is what a
    species nobody has ever labelled looks like; `acc=None` means absent from
    `top1`, which is what an unmeasured one looks like.
    """
    support = {} if n is None else {pred: n}
    top1 = {} if acc is None else {pred: acc}
    return queues.queue_of_prediction(pred, conf, support, top1)


def test_a_species_nobody_has_labelled_goes_to_the_long_tail(queues):
    """Absent from support reads as zero, not as unknown, which is the whole
    point of the queue: the photos worth sending are the ones about species we
    have nothing on."""
    assert _q(queues) == "long_tail"


def test_the_support_boundary_is_inclusive_at_well_sampled_min_n(queues, core):
    n = core.WELL_SAMPLED_MIN_N
    # One short of the line is still the long tail; on the line is not.
    assert _q(queues, n=n - 1, acc=1.0) == "long_tail"
    assert _q(queues, n=n, acc=1.0) != "long_tail"


def test_a_species_we_get_wrong_stays_in_the_long_tail_however_many_labels(queues, core):
    """The second half of the rule. A species with 500 labels and a measured
    accuracy under the hard line is not solved, so more labels still buy the
    most."""
    assert _q(queues, n=500, acc=core.HARD_MAX_TOP1 - 0.01) == "long_tail"
    assert _q(queues, n=500, acc=core.HARD_MAX_TOP1) != "long_tail"


def test_a_confident_guess_on_a_species_we_barely_have_is_still_long_tail(queues):
    """First rule wins, as the docstring says. Confidence cannot buy a photo
    out of the long tail, which is the property the confidence panel's evidence
    is about."""
    assert _q(queues, conf=0.999, n=1, acc=1.0) == "long_tail"


def test_an_unsure_guess_on_a_usually_right_species_is_worth_confirming(queues, core):
    n, acc = core.WELL_SAMPLED_MIN_N, core.RELIABLE_MIN_TOP1
    assert _q(queues, conf=core.LOW_CONF - 0.01, n=n, acc=acc) == "low_conf_known"
    # On the confidence line it is no longer low, so it falls through.
    assert _q(queues, conf=core.LOW_CONF, n=n, acc=acc) != "low_conf_known"


def test_reliable_is_inclusive_and_a_shade_below_it_is_not_low_conf_known(queues, core):
    """`low_conf_known` says "usually right species the model is unsure of
    here". A species just under the reliable line is not one of those, and the
    page would be claiming more than it measured if it said so."""
    n, conf = core.WELL_SAMPLED_MIN_N, core.LOW_CONF - 0.01
    assert _q(queues, conf=conf, n=n, acc=core.RELIABLE_MIN_TOP1) == "low_conf_known"
    assert _q(queues, conf=conf, n=n, acc=core.RELIABLE_MIN_TOP1 - 0.01) == "normal"


def test_a_confident_guess_on_a_well_sampled_species_can_wait(queues, core):
    n = core.WELL_SAMPLED_MIN_N
    assert _q(queues, conf=core.WAIT_CONF, n=n, acc=0.8) == "can_wait"
    assert _q(queues, conf=core.WAIT_CONF - 0.01, n=n, acc=0.8) == "normal"


def test_a_measured_species_with_no_rule_matching_is_normal(queues, core):
    """The residual queue exists, and nothing should silently land in it that
    another rule was meant to catch."""
    assert _q(queues, conf=0.6, n=core.WELL_SAMPLED_MIN_N, acc=0.8) == "normal"


def test_every_queue_the_function_can_return_is_one_the_pages_name(queues, core):
    """QUEUE_ORDER is what the send panel prints and what QL is checked
    against. A fifth queue returned here would render as a missing row."""
    seen = set()
    for n in (None, 0, core.WELL_SAMPLED_MIN_N - 1, core.WELL_SAMPLED_MIN_N, 500):
        for acc in (None, 0.0, core.HARD_MAX_TOP1, core.RELIABLE_MIN_TOP1, 1.0):
            for conf in (0.0, core.LOW_CONF, core.WAIT_CONF, 1.0):
                seen.add(_q(queues, conf=conf, n=n, acc=acc))
    assert seen <= set(queues.QUEUE_ORDER)


# ---------------------------------------------------------------------------
# bucket_label: the support bands, which have to tile the integers
# ---------------------------------------------------------------------------

def test_the_bands_tile_every_count_with_no_gap_and_no_overlap(core):
    """A gap prints "?" in a chart axis; an overlap counts a species twice.
    Checked across every boundary rather than a sample, since the bands are
    written as literal pairs."""
    edges = sorted({e for lo, hi, _ in core.SUPPORT_BUCKETS for e in (lo - 1, lo, hi, hi + 1)})
    for n in [x for x in edges if 1 <= x <= 10 ** 9]:
        hits = [lab for lo, hi, lab in core.SUPPORT_BUCKETS if lo <= n <= hi]
        assert len(hits) == 1, f"{n} labelled frames falls in {hits}"
        assert core.bucket_label(n) == hits[0]


def test_a_count_below_the_first_band_is_marked_not_guessed(core):
    """Zero is not a band: a species with no labelled frames is not in
    per_species at all, so reaching here means a caller passed something the
    bands were not built for, and "?" says so rather than silently landing in
    the smallest band."""
    assert core.bucket_label(0) == "?"


def test_bucket_order_is_the_bands_in_the_order_they_are_defined(core):
    """The charts read BUCKET_ORDER; the lookup reads SUPPORT_BUCKETS. Derived,
    not restated, so this is a guard on the derivation staying derived."""
    assert core.BUCKET_ORDER == [lab for _, _, lab in core.SUPPORT_BUCKETS]
    assert len(set(core.BUCKET_ORDER)) == len(core.BUCKET_ORDER)


@pytest.mark.parametrize("n", [1, 2, 4, 5, 9, 10, 24, 25, 1_000])
def test_bucket_label_agrees_with_the_bands_at_every_named_edge(core, n):
    assert core.bucket_label(n) in core.BUCKET_ORDER
