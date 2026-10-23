"""How the send queue is cut into Labelbox batches.

A batch is one push to a botanist session, so its size is the thing the
labelling lead asked about on 2026-08-27: batches of about a hundred pictures, with lookalike
photos sitting together. Cutting per species gave neither -- 170 of 357 batches
held a single photo -- so the groups are now packed. The invariant that matters
is unchanged: the batches are a repartition of the queue, nothing lost, nothing
duplicated, priority order kept.

The packing tests below pass ``control_fraction=0``. They are about how species
groups are packed, and the random control is a separate decision that would
otherwise move every expected batch size by fifteen. The control has its own tests
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
                        k + 1, "", ""])
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


# ---------------- the random control ----------------
#
# Fifteen of every batch are drawn at random from the photos not sent yet instead
# of from the head of the queue. Nothing here measures whether the queue fills
# gaps faster than random, and a later pool has been reshaped by the queue, so
# the comparison has to ride in every batch. These tests hold the control to
# being a comparison rather than a corruption of the send order.


def controls_by_batch(batches):
    out: dict = {}
    for bid, group, key, _, picked in batches:
        if picked == "control":
            assert group == "control"
            out.setdefault(bid, []).append(key)
    return out


def test_every_batch_carries_its_own_control(queues):
    batches = queues.chunk_send_batches(rows(500), batch_size=100)
    control = controls_by_batch(batches)
    assert set(control) == set(range(1, len(sizes(batches)) + 1))
    assert all(len(v) == 15 for v in list(control.values())[:-1])
    assert max(sizes(batches)) <= 100, "the control takes room from a batch, it does not add to it"


def test_the_control_is_one_block_at_the_end_of_its_batch(queues):
    batches = queues.chunk_send_batches(rows(500), batch_size=100)
    for bid in controls_by_batch(batches):
        seen = groups_of(batches, bid)
        assert seen[-1] == queues.CONTROL_GROUP
        assert seen.count(queues.CONTROL_GROUP) == 1


def test_the_control_moves_frames_forward_and_never_adds_one(queues):
    """The whole invariant verify_snapshot rests on: same rows, no frame twice."""
    queue = rows(120, 90, 300)
    batches = queues.chunk_send_batches(queue, batch_size=100)
    keys = [b[2] for b in batches]
    assert len(keys) == len(set(keys)) == len(queue)
    assert set(keys) == {r[1] for r in queue}


def test_the_same_queue_draws_the_same_control(queues):
    """A fixed seed, so two runs of measure.py write the same file. A different
    draw is a different comparison, not a correction."""
    a = queues.chunk_send_batches(rows(500), batch_size=100)
    b = queues.chunk_send_batches(rows(500), batch_size=100)
    assert a == b
    assert a != queues.chunk_send_batches(rows(500), batch_size=100, seed=1)


def test_the_draw_reaches_past_the_head_of_the_queue(queues):
    """A control taken from the frames the queue would have sent anyway measures
    nothing. It is drawn from the whole pool left, so most of it sits behind the head."""
    queue = rows(1000)
    batches = queues.chunk_send_batches(queue, batch_size=100)
    key_at = {r[1]: i for i, r in enumerate(queue)}
    first = controls_by_batch(batches)[1]
    assert len(first) == 15
    assert max(key_at[k] for k in first) > 100, "the draw never left the first batch"


def test_a_later_batch_draws_from_what_is_left(queues):
    """Without replacement across batches, and not confined to the next hundred."""
    queue = rows(1000)
    batches = queues.chunk_send_batches(queue, batch_size=100)
    key_at = {r[1]: i for i, r in enumerate(queue)}
    second = controls_by_batch(batches)[2]
    assert len(second) == 15
    assert max(key_at[k] for k in second) > 300


def test_a_short_pool_gives_each_batch_fewer_control_but_keeps_queue_work(queues):
    """20 photos, batch of 100: the lone batch takes 15% of its own size, 3."""
    batches = queues.chunk_send_batches(rows(20), batch_size=100)
    assert sizes(batches) == [20]
    assert len(controls_by_batch(batches)[1]) == 3
    batches = queues.chunk_send_batches(rows(1), batch_size=100)
    assert [b[4] for b in batches] == ["queue"]


def test_the_tail_never_opens_a_batch_of_only_control(queues):
    for n in range(1, 260):
        batches = queues.chunk_send_batches(rows(n), batch_size=20)
        assert len({b[2] for b in batches}) == n
        by_batch: dict = {}
        for b in batches:
            by_batch.setdefault(b[0], set()).add(b[4])
        assert all("queue" in kinds for kinds in by_batch.values()), n


def test_the_control_turns_off(queues):
    """`control_fraction=0` is the way back to the order before this existed."""
    batches = queues.chunk_send_batches(rows(500), batch_size=100, control_fraction=0)
    assert all(b[4] == "queue" for b in batches)
    assert sizes(batches) == [100, 100, 100, 100, 100]


def old_packing(queue, batch_size):
    """The packer before the control: species pre-split to batch_size, whole
    groups until the next would overflow. Kept here as the reference."""
    order, by = [], {}
    for r in queue:
        if r[3] not in by:
            order.append(r[3])
        by.setdefault(r[3], []).append(r)
    out, bid, held = [], 0, batch_size
    for sp in order:
        for i in range(0, len(by[sp]), batch_size):
            chunk = by[sp][i:i + batch_size]
            if held + len(chunk) > batch_size:
                bid, held = bid + 1, 0
            held += len(chunk)
            out += [[bid, sp, r[1], r[0], "queue"] for r in chunk]
    return out


@pytest.mark.parametrize("batch_size", [1, 3, 7, 25, 100])
def test_with_no_control_the_packing_is_the_pre_control_packing(queues, batch_size):
    import random
    rng = random.Random(batch_size)
    for _ in range(40):
        counts = [rng.choice([1, 1, 2, 5, 30, 120]) for _ in range(rng.randint(1, 8))]
        queue = rows(*counts)
        rng.shuffle(queue)
        assert queues.chunk_send_batches(
            queue, batch_size=batch_size, control_fraction=0) == old_packing(queue, batch_size)


def test_a_species_that_fills_a_batch_is_cut_at_the_room_the_control_leaves(queues):
    """A batch has 85 rows of room, not a hundred. A species that fills a whole
    batch is cut at 85 rather than leaving the batch nearly empty, and the
    remainder opens the next one."""
    batches = queues.chunk_send_batches(rows(500), batch_size=100)
    assert sizes(batches)[0] == 100, "85 queue rows plus the 15-row control"
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


def test_the_control_keeps_its_batch_id_on_the_queue_row(queues):
    """The control rides in its batch and moves forward out of queue order, so its
    rows are the ones a positional join would get wrong."""
    queue = rows(500)
    batches = queues.chunk_send_batches(queue, batch_size=100)
    joined = queues.with_batch_ids(queue, batches)
    control = controls_by_batch(batches)
    key_at = queues.SEND_FIRST_COLUMNS.index("global_key")
    assert len(control) > 1
    for bid, keys in control.items():
        assert {r[-1] for r in joined if r[key_at] in keys} == {bid}


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


# --- The cap itself is the labelling team's number ---
def test_the_cap_defaults_to_a_hundred_when_nothing_is_set(queues):
    """The labelling lead's number. An unset or empty variable is not a choice."""
    assert queues._batch_size_from_env(None) == 100
    assert queues._batch_size_from_env("") == 100
    assert queues._batch_size_from_env("   ") == 100


def test_the_cap_can_be_set_without_editing_source(queues):
    """The reviewer wanted many small batches over few large ones. Trying 50 or 200
    should not be a code change, because it is not our call to make."""
    assert queues._batch_size_from_env("50") == 50
    assert queues._batch_size_from_env(" 200 ") == 200


@pytest.mark.parametrize("raw", ["one hundred", "100.5", "1e2", "100 photos"])
def test_a_cap_that_is_not_a_number_stops_the_run(queues, raw):
    """Falling back to 100 on a typo would repartition the queue against a
    number nobody chose, and the page would then describe it as intended."""
    with pytest.raises(ValueError, match="whole number"):
        queues._batch_size_from_env(raw)


@pytest.mark.parametrize("raw", ["0", "-1"])
def test_a_cap_below_one_stops_the_run(queues, raw):
    with pytest.raises(ValueError, match="at least 1"):
        queues._batch_size_from_env(raw)


# --- group_by -----------------------------------------------------------------

def golden_rows(queues):
    """30 interleaved rows over five species; the golden below came from the
    packer before `group_by` existed."""
    cols = queues.SEND_FIRST_COLUMNS
    out = []
    for i in range(30):
        r = [""] * len(cols)
        r[cols.index("queue")] = "long_tail" if i < 20 else "normal"
        r[cols.index("global_key")] = f"k{i:02d}"
        r[cols.index("predicted_species")] = "abcde"[(i * 3 + i // 4) % 5]
        out.append(r)
    return out


GOLDEN_SPECIES = [
    (1, "a", "k00", "queue"), (1, "a", "k11", "queue"), (1, "a", "k14", "queue"),
    (1, "a", "k17", "queue"), (1, "a", "k20", "queue"), (1, "control", "k25", "control"),
    (2, "d", "k01", "queue"), (2, "d", "k04", "queue"), (2, "d", "k15", "queue"),
    (2, "d", "k18", "queue"), (2, "d", "k21", "queue"), (2, "d", "k24", "queue"),
    (2, "control", "k08", "control"),
    (3, "b", "k02", "queue"), (3, "b", "k05", "queue"), (3, "b", "k19", "queue"),
    (3, "b", "k22", "queue"), (3, "b", "k28", "queue"), (3, "control", "k07", "control"),
    (4, "e", "k03", "queue"), (4, "e", "k06", "queue"), (4, "e", "k09", "queue"),
    (4, "e", "k12", "queue"), (4, "e", "k23", "queue"), (4, "e", "k26", "queue"),
    (4, "control", "k10", "control"),
    (5, "e", "k29", "queue"), (5, "c", "k13", "queue"), (5, "c", "k27", "queue"),
    (5, "control", "k16", "control")]


def test_species_mode_is_unchanged_and_the_default(queues):
    for kwargs in ({}, {"group_by": "species"}):
        got = queues.chunk_send_batches(golden_rows(queues), batch_size=7, **kwargs)
        assert [(b[0], b[1], b[2], b[4]) for b in got] == GOLDEN_SPECIES


def test_rank_mode_keeps_global_rank_order_in_fixed_chunks(queues):
    got = queues.chunk_send_batches(golden_rows(queues), batch_size=7, group_by="rank")
    queue_part = [b for b in got if b[4] == "queue"]
    control = [(b[0], b[2]) for b in got if b[4] == "control"]
    assert sizes(got) == [7, 7, 7, 7, 2]       # each batch: 6 queue rows + 1 control
    assert control == [(1, "k25"), (2, "k14"), (3, "k20"), (4, "k28"), (5, "k29")]
    assert [b[2] for b in queue_part] == [
        f"k{i:02d}" for i in range(30) if f"k{i:02d}" not in {k for _, k in control}]
    assert {b[1] for b in queue_part} <= set("abcde")


def test_rank_mode_with_no_control_fills_every_batch(queues):
    got = queues.chunk_send_batches(golden_rows(queues), batch_size=7, control_fraction=0,
                                    group_by="rank")
    assert sizes(got) == [7, 7, 7, 7, 2]
    assert [b[2] for b in got] == [f"k{i:02d}" for i in range(30)]


@pytest.mark.parametrize("mode", ["species", "rank", None])
def test_the_build_check_follows_the_group_by_column(queues, history, tmp_path, mode):
    """None is a file written before the column existed: read as species."""
    import csv
    rows = golden_rows(queues)
    for i, r in enumerate(rows):
        r[queues.SEND_FIRST_COLUMNS.index("how_new_it_looks")] = "0.5"
    batches = queues.chunk_send_batches(rows, batch_size=queues.BATCH_SIZE,
                                        group_by=mode or "species")
    with open(tmp_path / "q.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(queues.SEND_FIRST_COLUMNS)
        w.writerows(rows)
    header = queues.SEND_BATCH_COLUMNS + ["how_new_it_looks"] + (["group_by"] if mode else [])
    with open(tmp_path / "send_batches.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(b + ["0.5"] + ([mode] if mode else []) for b in batches)
    assert "30 rows" in history.check_send_batches(str(tmp_path), str(tmp_path / "q.csv"), 30)
    if mode == "rank":
        # Same file claiming the other mode no longer matches the recomputation.
        text = (tmp_path / "send_batches.csv").read_text().replace(",rank", ",species")
        (tmp_path / "send_batches.csv").write_text(text)
        with pytest.raises(SystemExit):
            history.check_send_batches(str(tmp_path), str(tmp_path / "q.csv"), 30)


def test_the_build_fails_when_the_file_and_the_page_setting_disagree(queues, history, tmp_path):
    import csv
    rows = golden_rows(queues)
    for r in rows:
        r[queues.SEND_FIRST_COLUMNS.index("how_new_it_looks")] = "0.5"
    batches = queues.chunk_send_batches(rows, batch_size=queues.BATCH_SIZE, group_by="rank")
    with open(tmp_path / "q.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(queues.SEND_FIRST_COLUMNS)
        w.writerows(rows)
    with open(tmp_path / "send_batches.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(queues.SEND_BATCH_COLUMNS + ["how_new_it_looks", "group_by"])
        w.writerows(b + ["0.5", "rank"] for b in batches)
    args = (str(tmp_path), str(tmp_path / "q.csv"), 30)
    assert "30 rows" in history.check_send_batches(*args, page_group_by="rank")
    with pytest.raises(SystemExit, match="VERIFY FAIL: send_batches.csv was packed by rank but BCI_GROUP_BY is species"):
        history.check_send_batches(*args, page_group_by="species")


def test_group_by_is_validated(queues):
    with pytest.raises(ValueError, match="group_by"):
        queues.chunk_send_batches(golden_rows(queues), group_by="confusion")
    assert queues._group_by_from_env(None) == "species"
    assert queues._group_by_from_env("  ") == "species"
    assert queues._group_by_from_env("rank") == "rank"
    with pytest.raises(ValueError, match="BCI_GROUP_BY"):
        queues._group_by_from_env("Rank")


# --- the control is a share of each batch, not a fixed count -------------------


def shares(batches):
    """(batch size, control count) per batch, in batch_id order."""
    ctl = {b: len(v) for b, v in controls_by_batch(batches).items()}
    return [(n, ctl.get(i + 1, 0)) for i, n in enumerate(sizes(batches))]


@pytest.mark.parametrize("counts", [(9, 80, 70, 55), (1, 200, 3, 3, 40), (5,), (30, 30, 30, 30, 30, 7)])
def test_every_batch_controls_within_one_photo_of_its_share(queues, counts):
    """Uneven species and a tiny first group: species stay whole, so batches come out
    uneven, and each one, the last included, holds 15% control to within one photo."""
    batches = queues.chunk_send_batches(rows(*counts), batch_size=100)
    assert len({b[2] for b in batches}) == sum(counts)
    for size, ctl in shares(batches):
        assert abs(ctl - 0.15 * size) <= 1, (size, ctl)
        assert ctl < size
