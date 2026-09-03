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
    for n in [x for x in edges if 1 <= x <= core.NO_UPPER_BOUND]:
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


# ---------------------------------------------------------------------------
# send_first_rows: the order inside a queue, and the file that sets it
# ---------------------------------------------------------------------------

def _rows(queues, frames, novelty=None, prefix="comb_"):
    """`frames` is `{stem: (species, confidence)}`. Every species is unlabelled,
    so every frame lands in the long tail and the queue is held constant while
    the order inside it is what varies."""
    predictions = {stem: [(sp, conf)] for stem, (sp, conf) in frames.items()}
    return queues.send_first_rows(predictions, set(), lambda n: n, {}, {},
                                  novelty=novelty, key_prefix=prefix)[0]


def test_a_photo_unlike_the_labelled_ones_is_sent_before_a_less_confident_one(queues):
    """The change this ordering exists for. `b` is the least confident frame, so
    it led before; `a` is the one least like everything already labelled, so it
    leads now."""
    frames = {"a": ("Sp x", 0.9), "b": ("Sp y", 0.1)}
    novelty = {"comb_a": 1, "comb_b": 2}
    assert [r[1] for r in _rows(queues, frames, novelty)] == ["a", "b"]


def test_a_photo_with_no_vector_waits_behind_every_ranked_photo_of_its_queue(queues):
    """A frame the fetch has not reached yet is not treated as new. It keeps its
    place by confidence, at the back."""
    frames = {"a": ("Sp x", 0.9), "b": ("Sp y", 0.1), "c": ("Sp z", 0.5)}
    novelty = {"comb_a": 7}
    order = [r[1] for r in _rows(queues, frames, novelty)]
    assert order == ["a", "b", "c"]
    assert [r[4] for r in _rows(queues, frames, novelty)][1:] == [queues.NO_NOVELTY] * 2


def test_with_no_ordering_file_the_order_is_the_one_confidence_alone_gives(queues):
    """The rollback, proved rather than asserted: delete the file and every rank
    ties, so the queue is byte-for-byte what it was before the file existed."""
    frames = {"a": ("Sp x", 0.9), "b": ("Sp y", 0.1), "c": ("Sp z", 0.5)}
    baseline = [(r[1], r[3]) for r in _rows(queues, frames, None)]
    assert baseline == [("b", 0.1), ("c", 0.5), ("a", 0.9)]
    assert baseline == [(r[1], r[3]) for r in _rows(queues, frames, {})]


def test_how_a_photo_looks_never_moves_it_into_another_queue(queues, core):
    """Queue membership is decided by `queue_of_prediction`, which never sees a
    rank. Ranking first would send a photo of a solved species ahead of the long
    tail, which is the one thing this ordering must not do."""
    predictions = {"a": [("Rare sp", 0.9)], "b": [("Known sp", 0.9)]}
    support = {"Known sp": 500}
    top1 = {"Known sp": 1.0}
    rows, _ = queues.send_first_rows(predictions, set(), lambda n: n, support, top1,
                                     novelty={"comb_b": 1}, key_prefix="comb_")
    assert [(r[0], r[1]) for r in rows] == [("long_tail", "a"), ("can_wait", "b")]


def test_a_frame_with_no_answer_is_counted_and_not_ranked(queues):
    predictions = {"a": [], "b": [("Sp y", 0.4)]}
    rows, n_no_answer = queues.send_first_rows(predictions, set(), lambda n: n, {}, {},
                                               novelty={"comb_a": 1}, key_prefix="comb_")
    assert n_no_answer == 1
    assert [r[1] for r in rows] == ["b"]


def test_load_novelty_reads_the_file_and_survives_it_being_absent(queues, tmp_path):
    """A missing file is the normal state of a fresh clone, not an error. A rank
    that is not a whole number is dropped, since the alternative is inventing a
    place in the queue for it."""
    assert queues.load_novelty(str(tmp_path / "nothing.csv")) == {}
    path = tmp_path / "queue_novelty.csv"
    path.write_text("global_key,novelty_rank,distance_to_nearest_labelled,camera\n"
                    "comb_a,1,0.42,zoom\n"
                    "comb_b,,0.10,tele\n"
                    "comb_c,not a number,0.10,tele\n"
                    ",4,0.10,tele\n", encoding="utf-8")
    assert queues.load_novelty(str(path)) == {"comb_a": 1}
