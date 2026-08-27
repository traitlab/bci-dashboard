"""How the send queue is cut into Labelbox batches.

A batch is one push to a botanist session, so its size is the thing Antoine
asked about on 2026-08-27: batches of about a hundred pictures, with lookalike
photos sitting together. Cutting per species gave neither -- 170 of 357 batches
held a single photo -- so the groups are now packed. The invariant that matters
is unchanged: the batches are a repartition of the queue, nothing lost, nothing
duplicated, priority order kept.

    .venv/bin/pytest tests/test_batches.py
"""

import pytest


def rows(*counts):
    """A send_first_queue row list: `counts` photos of species s0, s1, ...

    Only columns 0 (queue), 1 (global_key) and 3 (predicted_species) are read
    by the chunker; the rest carry their real shape so a column shift shows up
    here rather than in a rendered page.
    """
    out = []
    for i, n in enumerate(counts):
        for k in range(n):
            out.append(["long_tail", f"s{i}_{k}.JPG", "train", f"species {i}", 0.5, 0, 0.0])
    return out


def sizes(batches):
    """Row count per batch, in batch_id order."""
    counts: dict = {}
    for bid, *_ in batches:
        counts[bid] = counts.get(bid, 0) + 1
    return [counts[bid] for bid in sorted(counts)]


def groups_of(batches, batch_id):
    """The species groups of one batch, in the order they appear."""
    seen = [sp for bid, sp, *_ in batches if bid == batch_id]
    return [sp for i, sp in enumerate(seen) if i == 0 or sp != seen[i - 1]]


def test_small_species_share_a_batch(core):
    batches = core.chunk_send_batches(rows(40, 30, 20), batch_size=100)
    assert sizes(batches) == [90]
    assert groups_of(batches, 1) == ["species 0", "species 1", "species 2"]


def test_a_group_that_would_overflow_opens_the_next_batch(core):
    # 60 + 50 is 110, so the second species starts a batch rather than straddle.
    batches = core.chunk_send_batches(rows(60, 50), batch_size=100)
    assert sizes(batches) == [60, 50]


def test_a_species_larger_than_a_batch_splits_into_its_own(core):
    batches = core.chunk_send_batches(rows(250), batch_size=100)
    assert sizes(batches) == [100, 100, 50]
    assert groups_of(batches, 3) == ["species 0"]


def test_the_remainder_of_a_split_species_packs_with_the_next(core):
    # 250 leaves 50 trailing, which has room for the following 30.
    batches = core.chunk_send_batches(rows(250, 30), batch_size=100)
    assert sizes(batches) == [100, 100, 80]
    assert groups_of(batches, 3) == ["species 0", "species 1"]


def test_every_batch_holds_contiguous_species_groups(core):
    batches = core.chunk_send_batches(rows(7, 1, 1, 120, 3, 1), batch_size=100)
    for bid in {b[0] for b in batches}:
        seen = groups_of(batches, bid)
        assert len(seen) == len(set(seen)), f"batch {bid} interleaves species"


def test_no_batch_exceeds_the_cap(core):
    batches = core.chunk_send_batches(rows(7, 1, 1, 120, 3, 1, 99), batch_size=100)
    assert max(sizes(batches)) <= 100


def test_the_batches_are_a_repartition_of_the_queue(core):
    queue = rows(7, 1, 1, 120, 3, 1, 99)
    batches = core.chunk_send_batches(queue, batch_size=100)
    keys = [b[2] for b in batches]
    assert len(keys) == len(queue)
    assert keys == [r[1] for r in queue], "priority order or a row was lost"


def test_a_species_keeps_the_place_its_first_row_earned(core):
    # Species 1 reappears after species 2. It must not open a third group: the
    # queue's priority order is between species, and a species is visited once.
    queue = rows(2, 2) + [["normal", "late.JPG", "train", "species 0", 0.9, 0, 0.0]]
    batches = core.chunk_send_batches(queue, batch_size=100)
    assert groups_of(batches, 1) == ["species 0", "species 1"]
    assert [b[2] for b in batches][:3] == ["s0_0.JPG", "s0_1.JPG", "late.JPG"]


def test_an_empty_queue_makes_no_batches(core):
    assert core.chunk_send_batches([], batch_size=100) == []


def test_a_batch_size_below_one_is_refused(core):
    with pytest.raises(ValueError):
        core.chunk_send_batches(rows(3), batch_size=0)
