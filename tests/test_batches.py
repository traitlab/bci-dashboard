"""How the send queue is cut into Labelbox batches.

A batch is one push to a botanist session, so its size is the thing Antoine
asked about on 2026-08-27: batches of about a hundred pictures, with lookalike
photos sitting together. Cutting per species gave neither -- 170 of 357 batches
held a single photo -- so the groups are now packed. The invariant that matters
is unchanged: the batches are a repartition of the queue, nothing lost, nothing
duplicated, priority order kept.

The packing tests below pass ``control_fraction=0``. They are about how species
groups are packed, and the control slice is a separate decision that would
otherwise move every expected batch size by fifteen. The slice has its own tests
at the end of this file.

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
            out.append(["long_tail", f"s{i}_{k}.JPG", "train", f"species {i}", 0.5, 0, 0.0,
                        k + 1, ""])
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


def test_small_species_share_a_batch(queues):
    batches = queues.chunk_send_batches(rows(40, 30, 20), batch_size=100, control_fraction=0)
    assert sizes(batches) == [90]
    assert groups_of(batches, 1) == ["species 0", "species 1", "species 2"]


def test_a_group_that_would_overflow_opens_the_next_batch(queues):
    # 60 + 50 is 110, so the second species starts a batch rather than straddle.
    batches = queues.chunk_send_batches(rows(60, 50), batch_size=100, control_fraction=0)
    assert sizes(batches) == [60, 50]


def test_a_species_larger_than_a_batch_splits_into_its_own(queues):
    batches = queues.chunk_send_batches(rows(250), batch_size=100, control_fraction=0)
    assert sizes(batches) == [100, 100, 50]
    assert groups_of(batches, 3) == ["species 0"]


def test_the_remainder_of_a_split_species_packs_with_the_next(queues):
    # 250 leaves 50 trailing, which has room for the following 30.
    batches = queues.chunk_send_batches(rows(250, 30), batch_size=100, control_fraction=0)
    assert sizes(batches) == [100, 100, 80]
    assert groups_of(batches, 3) == ["species 0", "species 1"]


def test_every_batch_holds_contiguous_species_groups(queues):
    batches = queues.chunk_send_batches(rows(7, 1, 1, 120, 3, 1), batch_size=100, control_fraction=0)
    for bid in {b[0] for b in batches}:
        seen = groups_of(batches, bid)
        assert len(seen) == len(set(seen)), f"batch {bid} interleaves species"


def test_no_batch_exceeds_the_cap(queues):
    batches = queues.chunk_send_batches(rows(7, 1, 1, 120, 3, 1, 99), batch_size=100, control_fraction=0)
    assert max(sizes(batches)) <= 100


def test_the_batches_are_a_repartition_of_the_queue(queues):
    queue = rows(7, 1, 1, 120, 3, 1, 99)
    batches = queues.chunk_send_batches(queue, batch_size=100, control_fraction=0)
    keys = [b[2] for b in batches]
    assert len(keys) == len(queue)
    assert keys == [r[1] for r in queue], "priority order or a row was lost"


def test_a_species_keeps_the_place_its_first_row_earned(queues):
    # Species 1 reappears after species 2. It must not open a third group: the
    # queue's priority order is between species, and a species is visited once.
    queue = rows(2, 2) + [["normal", "late.JPG", "train", "species 0", 0.9, 0, 0.0, 9]]
    batches = queues.chunk_send_batches(queue, batch_size=100, control_fraction=0)
    assert groups_of(batches, 1) == ["species 0", "species 1"]
    assert [b[2] for b in batches][:3] == ["s0_0.JPG", "s0_1.JPG", "late.JPG"]


def test_an_empty_queue_makes_no_batches(queues):
    assert queues.chunk_send_batches([], batch_size=100, control_fraction=0) == []


def test_a_batch_size_below_one_is_refused(queues):
    with pytest.raises(ValueError):
        queues.chunk_send_batches(rows(3), batch_size=0, control_fraction=0)


def test_a_test_row_is_as_wide_as_the_file_the_chunker_reads(queues):
    """The helper indexes by position, which is why it carries every column and
    not just the three that are read. A column added to the file and not here
    would shift the species out from under the chunker with nothing failing."""
    assert len(rows(1)[0]) == len(queues.SEND_FIRST_COLUMNS)


def test_the_order_a_photo_looks_new_in_does_not_reach_the_batches(queues):
    """`send_first_rows` has already applied it. The batcher takes the queue in
    the order it is given, so the new column is carried, never read."""
    plain = queues.chunk_send_batches(rows(3, 2), batch_size=100, control_fraction=0)
    at = queues.SEND_FIRST_COLUMNS.index("novelty_rank")
    shuffled = []
    for r in rows(3, 2):
        r[at] = 100 - r[at]
        shuffled.append(r)
    assert queues.chunk_send_batches(shuffled, batch_size=100, control_fraction=0) == plain


# ---------------- the control slice ----------------
#
# Fifteen of the first batch are drawn at random from the whole pool instead of
# from the head of the queue. Nothing here measures whether the queue fills gaps
# faster than random, and after the first batch is labelled nothing can: every
# later pool has been reshaped by the queue. These tests hold the slice to being
# a comparison rather than a corruption of the send order.


def test_the_first_batch_carries_a_control_slice(queues):
    batches = queues.chunk_send_batches(rows(500), batch_size=100)
    first = [b for b in batches if b[0] == 1]
    control = [b for b in first if b[4] == "control"]
    assert len(control) == 15
    assert len(first) == 100, "the slice takes room from the batch, it does not add to it"


def test_no_later_batch_carries_a_control_row(queues):
    batches = queues.chunk_send_batches(rows(500), batch_size=100)
    assert {b[0] for b in batches if b[4] == "control"} == {1}


def test_the_slice_is_contiguous_and_named_so_it_cannot_be_a_species(queues):
    batches = queues.chunk_send_batches(rows(500), batch_size=100)
    seen = groups_of(batches, 1)
    assert seen[-1] == queues.CONTROL_GROUP
    assert seen.count(queues.CONTROL_GROUP) == 1


def test_the_slice_moves_frames_forward_and_never_adds_one(queues):
    """The whole invariant verify_snapshot rests on: same rows, no frame twice."""
    queue = rows(120, 90, 300)
    batches = queues.chunk_send_batches(queue, batch_size=100)
    keys = [b[2] for b in batches]
    assert len(keys) == len(set(keys)) == len(queue)
    assert set(keys) == {r[1] for r in queue}


def test_the_same_queue_draws_the_same_slice(queues):
    """A fixed seed, so two runs of measure.py write the same file. A different
    draw is a different comparison, not a correction."""
    a = queues.chunk_send_batches(rows(500), batch_size=100)
    b = queues.chunk_send_batches(rows(500), batch_size=100)
    assert a == b


def test_the_draw_reaches_past_the_head_of_the_queue(queues):
    """A slice taken from the frames the queue would have sent anyway measures
    nothing. It is drawn from the whole pool, so most of it sits behind the head."""
    queue = rows(1000)
    control = queues.draw_control_slice(queue, batch_size=100)
    assert len(control) == 15
    assert max(control) > 100, "the draw never left the first batch"


def test_a_frame_the_queue_would_send_anyway_may_be_drawn(queues):
    """Dropping the overlap is what would bias the sample, so it is kept. The
    draw is uniform over the pool, head included."""
    queue = rows(20)
    control = queues.draw_control_slice(queue, batch_size=100)
    assert len(control) == 15 and len(set(control)) == 15


def test_the_slice_turns_off(queues):
    """`control_fraction=0` is the way back to the order before this existed."""
    batches = queues.chunk_send_batches(rows(500), batch_size=100, control_fraction=0)
    assert all(b[4] == "queue" for b in batches)
    assert sizes(batches) == [100, 100, 100, 100, 100]


def test_a_group_too_big_for_the_shortened_first_batch_is_chopped_to_fit(queues):
    """The first batch has 85 rows of room, not a hundred. A species that fills
    a whole batch is cut at 85 rather than leaving the first batch nearly empty,
    and the remainder opens the next one."""
    batches = queues.chunk_send_batches(rows(500), batch_size=100)
    assert sizes(batches)[0] == 100, "85 queue rows plus the 15-row slice"
    assert max(sizes(batches)) <= 100
    assert sum(sizes(batches)) == 500


# --- the batch a queued frame landed in, written on the frame ------------------
#
# send_first_queue.csv and send_batches.csv describe the same frames, and until
# now the only way to ask "which batch is this frame in" was to open both files
# and match on global_key, or to re-run the packing, which is the second
# implementation verify_snapshot exists to forbid. The queue row carries the
# answer now.


def test_every_queued_frame_carries_the_batch_it_was_packed_into(queues):
    queue = rows(30, 40)
    batches = queues.chunk_send_batches(queue, batch_size=25)
    joined = queues.with_batch_ids(queue, batches)
    key_at = queues.SEND_FIRST_COLUMNS.index("global_key")
    of_key = {b[2]: b[0] for b in batches}
    assert [r[-1] for r in joined] == [of_key[r[key_at]] for r in queue]
    assert all(len(r) == len(queues.SEND_FIRST_COLUMNS) for r in joined)


def test_the_control_slice_keeps_its_batch_id_on_the_queue_row(queues):
    """The slice rides in batch 1 and moves forward out of queue order, so its
    rows are the ones a positional join would get wrong."""
    queue = rows(500)
    batches = queues.chunk_send_batches(queue, batch_size=100)
    joined = queues.with_batch_ids(queue, batches)
    control = {b[2] for b in batches if b[4] == "control"}
    key_at = queues.SEND_FIRST_COLUMNS.index("global_key")
    assert len(control) == 15
    assert {r[-1] for r in joined if r[key_at] in control} == {1}


def test_the_added_column_does_not_move_the_packing(queues):
    """verify_snapshot re-packs the queue file it reads, batch_id column and
    all. A column that shifted the result would abort every build."""
    queue = rows(30, 40)
    batches = queues.chunk_send_batches(queue, batch_size=25)
    assert queues.chunk_send_batches(
        queues.with_batch_ids(queue, batches), batch_size=25) == batches


def test_a_frame_no_batch_claims_is_a_build_failure(queues):
    """A blank cell would read as "not scheduled yet", which is a different
    fact from "the queue and the packing disagree"."""
    queue = rows(4)
    batches = queues.chunk_send_batches(queue, batch_size=25)
    with pytest.raises(ValueError, match="never packed"):
        queues.with_batch_ids(queue, batches[:-1])


def test_a_frame_two_batches_claim_is_a_build_failure(queues):
    queue = rows(4)
    batches = queues.chunk_send_batches(queue, batch_size=25)
    with pytest.raises(ValueError, match="more than one send batch"):
        queues.with_batch_ids(queue, batches + [list(batches[0])])
