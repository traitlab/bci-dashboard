"""Direct tests for dashboard/history.py's verify_snapshot.

verify_snapshot is the single gate that aborts every page build when the
freshly computed numbers disagree with the committed model-health snapshot,
and it had no tests at all before this file (tests/test_snapshot_gate.py only
covers latest_snapshot_dir). These tests build a synthetic snapshot directory
directly, against the synthetic snapshot directory `snapshot_harness.py`
writes. No real snapshots/ folder is read and no page is built.

    .venv/bin/pytest tests/test_verify_snapshot.py
"""

from __future__ import annotations

from snapshot_harness import (
    NEVER_ALL,
    N_NO_ANSWER,
    QUEUE_COUNTS,
    REVIEW_COUNTS,
    STRICT_HITS,
    UNSCOREABLE,
    assert_aborts,
    batch_rows_for,
    bin_csv_rows,
    bucket_csv_rows,
    log_lines_default,
    queue_rows_for,
    run,
    species_csv_rows,
    tolerance,
    write_snapshot,
)


# ---------------- happy path and the optional-argument matrix ----------------

def test_a_consistent_snapshot_returns_a_check_string_per_file(history, tmp_path):
    kwargs, _ = write_snapshot(tmp_path)
    checks = run(history, tmp_path, kwargs)
    assert len(checks) == 7  # 4 unconditional + send_first_queue + send_batches + review


def test_each_returned_check_names_the_file_it_came_from(history, tmp_path):
    kwargs, _ = write_snapshot(tmp_path)
    checks = run(history, tmp_path, kwargs)
    named = {"per_species_health.csv", "support_buckets.csv", "confidence_calibration.csv",
             "run_log.txt", "send_first_queue.csv", "send_batches.csv",
             "label_review_queue.csv"}
    for fname in named:
        assert any(fname in c for c in checks), f"no check string names {fname}"


def test_with_all_three_optional_arguments_omitted_only_the_four_unconditional_checks_return(
        history, tmp_path):
    kwargs, _ = write_snapshot(
        tmp_path, with_queue_counts=False, with_no_answer=False, with_review_counts=False)
    checks = run(history, tmp_path, kwargs)
    assert len(checks) == 4
    assert not any("queue" in c or "batch" in c or "review" in c for c in checks)


def test_the_send_first_order_is_checked_row_for_row_not_only_counted(history, tmp_path):
    """measure.py and figures.py sort the same rows separately. A changed
    tie-break moves rows without moving any count, and the page prints the head
    of the file, so the two orders have to be one order."""
    kwargs, files = write_snapshot(tmp_path)
    keys = [r["global_key"] for r in files["queue"]]
    kwargs["queue_keys"] = keys
    assert any("same order as the page" in c for c in run(history, tmp_path, kwargs))

    kwargs["queue_keys"] = keys[:1] + [keys[2], keys[1]] + keys[3:]
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "order diverges at row 2" in msg


def test_a_send_first_queue_missing_rows_is_an_order_failure_not_a_crash(history, tmp_path):
    kwargs, files = write_snapshot(tmp_path)
    kwargs["queue_keys"] = [r["global_key"] for r in files["queue"]][:-1]
    assert "order diverges" in assert_aborts(history, tmp_path, kwargs)


def test_queue_counts_alone_adds_the_two_queue_csv_checks(history, tmp_path):
    kwargs, _ = write_snapshot(
        tmp_path, with_queue_counts=True, with_no_answer=False, with_review_counts=False)
    checks = run(history, tmp_path, kwargs)
    assert len(checks) == 6


def test_review_counts_alone_adds_one_check(history, tmp_path):
    kwargs, _ = write_snapshot(
        tmp_path, with_queue_counts=False, with_no_answer=False, with_review_counts=True)
    checks = run(history, tmp_path, kwargs)
    assert len(checks) == 5


def test_n_no_answer_alone_adds_no_check_string_even_though_it_is_verified(history, tmp_path):
    # Documents a gap in verify_snapshot rather than endorsing it: n_no_answer
    # is checked against run_log.txt (a wrong value still aborts the build,
    # see test_no_answer_count_disagreeing_with_run_log_aborts below) but,
    # unlike the other two optional arguments, nothing appends a check string
    # for it, so its own pass is invisible in the returned checks list.
    kwargs, _ = write_snapshot(
        tmp_path, with_queue_counts=False, with_no_answer=True, with_review_counts=False)
    checks = run(history, tmp_path, kwargs)
    assert len(checks) == 4


# ---------------- per_species_health.csv ----------------

def test_species_count_mismatch_aborts(history, tmp_path):
    rows = species_csv_rows()[:1]  # drop one species from the file
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "species here" in msg


def test_species_present_here_but_absent_from_csv_aborts(history, tmp_path):
    rows = species_csv_rows()
    rows[1] = dict(rows[1], species="Bertholletia excelsa")  # same count, different name
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "Ceiba pentandra" in msg and "absent from" in msg


def test_labelled_crown_count_mismatch_aborts(history, tmp_path):
    rows = species_csv_rows()
    rows[0]["n_labelled_crowns"] = rows[0]["n_labelled_crowns"] + 1
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "labelled frames for" in msg and "Hura crepitans" in msg


def test_top1_accuracy_mismatch_aborts(history, tmp_path):
    rows = species_csv_rows()
    rows[0]["top1_accuracy"] = rows[0]["top1_accuracy"] + 0.1
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "top1_accuracy for" in msg and "Hura crepitans" in msg


def test_top5_accuracy_mismatch_aborts(history, tmp_path):
    rows = species_csv_rows()
    rows[0]["top5_accuracy"] = rows[0]["top5_accuracy"] - 0.1
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "top5_accuracy for" in msg and "Hura crepitans" in msg


# ---------------- support_buckets.csv ----------------

def test_support_bucket_missing_here_aborts(history, tmp_path):
    kwargs, _ = write_snapshot(tmp_path)
    kwargs["buckets"] = {k: v for k, v in kwargs["buckets"].items() if k != "rare"}
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "rare" in msg and "missing here" in msg


def test_support_bucket_counts_mismatch_aborts(history, tmp_path):
    rows = bucket_csv_rows()
    rows[0]["n_crowns"] = rows[0]["n_crowns"] + 1
    kwargs, _ = write_snapshot(tmp_path, bucket_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "counts" in msg and "well_sampled" in msg


def test_support_bucket_first_guess_rate_mismatch_aborts(history, tmp_path):
    rows = bucket_csv_rows()
    rows[0]["top1_accuracy"] = 0.0
    kwargs, _ = write_snapshot(tmp_path, bucket_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "first-guess rate" in msg and "well_sampled" in msg


# ---------------- confidence_calibration.csv ----------------

def test_confidence_band_absent_from_csv_aborts(history, tmp_path):
    rows = [r for r in bin_csv_rows() if r["band"] != "[0.2,0.4)"]
    kwargs, _ = write_snapshot(tmp_path, bin_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "[0.2,0.4)" in msg and "absent from" in msg


def test_confidence_band_counts_mismatch_aborts(history, tmp_path):
    rows = bin_csv_rows()
    rows[0]["n_correct"] = rows[0]["n_correct"] + 1
    kwargs, _ = write_snapshot(tmp_path, bin_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "confidence band" in msg and "counts" in msg


# ---------------- run_log.txt prose ----------------

def test_never_ceiling_number_mismatch_aborts(history, tmp_path):
    kwargs, _ = write_snapshot(tmp_path)
    kwargs["never_all"] = NEVER_ALL + 1
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "never name" in msg.lower() or "never" in msg.lower()


def test_unscoreable_number_mismatch_aborts(history, tmp_path):
    kwargs, _ = write_snapshot(tmp_path)
    kwargs["unscoreable"] = UNSCOREABLE + 1
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "unscoreable" in msg


def test_strict_hits_number_mismatch_aborts(history, tmp_path):
    kwargs, _ = write_snapshot(tmp_path)
    kwargs["strict_hits"] = STRICT_HITS + 1
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "reconciliation" in msg


def test_never_ceiling_line_missing_aborts(history, tmp_path):
    lines = log_lines_default()
    del lines["never"]
    kwargs, _ = write_snapshot(tmp_path, log_lines=lines)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "no line for" in msg


def test_unscoreable_line_missing_aborts(history, tmp_path):
    lines = log_lines_default()
    del lines["unscoreable"]
    kwargs, _ = write_snapshot(tmp_path, log_lines=lines)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "no line for" in msg and "unscoreable" in msg


def test_strict_hits_line_missing_aborts(history, tmp_path):
    lines = log_lines_default()
    del lines["strict"]
    kwargs, _ = write_snapshot(tmp_path, log_lines=lines)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "no line for" in msg


def test_no_answer_count_disagreeing_with_run_log_aborts(history, tmp_path):
    kwargs, _ = write_snapshot(tmp_path)
    kwargs["n_no_answer"] = N_NO_ANSWER + 1
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "no-answer" in msg


def test_no_answer_line_missing_aborts(history, tmp_path):
    lines = log_lines_default()
    del lines["no_answer"]
    kwargs, _ = write_snapshot(tmp_path, log_lines=lines)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "no no-answer line" in msg


# ---------------- send_first_queue.csv / send_batches.csv ----------------

def test_send_first_queue_count_mismatch_aborts(history, tmp_path):
    kwargs, _ = write_snapshot(tmp_path)
    kwargs["queue_counts"] = dict(QUEUE_COUNTS, long_tail=QUEUE_COUNTS["long_tail"] + 1)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "send-first queue" in msg and "long_tail" in msg


def test_queue_present_in_csv_but_not_in_queue_counts_aborts(history, tmp_path):
    kwargs, _ = write_snapshot(tmp_path)
    del kwargs["queue_counts"]["normal"]
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "only in" in msg and "normal" in msg


def test_batch_exceeding_batch_size_aborts(history, tmp_path):
    over = history.hc.BATCH_SIZE + 1
    counts = {"long_tail": over}
    qrows = queue_rows_for(counts)
    brows = batch_rows_for(qrows)  # a single batch holding all `over` rows
    kwargs, _ = write_snapshot(tmp_path, queue_rows=qrows, batch_rows=brows)
    kwargs["queue_counts"] = counts
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "exceeds" in msg and "BATCH_SIZE" in msg


def test_batch_with_noncontiguous_species_group_aborts(history, tmp_path):
    qrows = queue_rows_for()
    brows = batch_rows_for(qrows)
    # Split the long_tail group's rows around one normal row so the same
    # species_group value reappears later in the same batch.
    long_tail = [r for r in brows if r["queue"] == "long_tail"]
    normal = [r for r in brows if r["queue"] == "normal"]
    brows = [long_tail[0], normal[0], long_tail[1], long_tail[2], normal[1]]
    kwargs, _ = write_snapshot(tmp_path, queue_rows=qrows, batch_rows=brows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "not" in msg and "contiguous" in msg


def test_send_batches_row_count_disagreeing_with_queue_aborts(history, tmp_path):
    qrows = queue_rows_for()
    brows = batch_rows_for(qrows)[:-1]  # one row short
    kwargs, _ = write_snapshot(tmp_path, queue_rows=qrows, batch_rows=brows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "send_batches.csv" in msg and "rows vs" in msg


def test_send_batches_global_key_set_disagreeing_aborts(history, tmp_path):
    qrows = queue_rows_for()
    brows = batch_rows_for(qrows)
    brows[0] = dict(brows[0], global_key="not_a_real_key.JPG")
    kwargs, _ = write_snapshot(tmp_path, queue_rows=qrows, batch_rows=brows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "global_key set does not match" in msg


def test_batch_ids_need_not_match_chunk_send_batches_current_output(history, tmp_path):
    """Documents an open gap, not an endorsement of it: verify_snapshot checks
    that send_batches.csv is *a* valid repartition of send_first_queue.csv
    (capped size, contiguous species groups, same rows), but never checks
    that the batch_id assignment is the one core.chunk_send_batches would
    actually produce from those same rows. Splitting the two queues into two
    batches here is still structurally valid and still passes, even though
    chunk_send_batches, given the same 5 rows, would pack them into a single
    batch (see core.BATCH_SIZE=100)."""
    qrows = queue_rows_for()
    long_tail = [r for r in qrows if r["queue"] == "long_tail"]
    normal = [r for r in qrows if r["queue"] == "normal"]
    brows = batch_rows_for(long_tail, batch_id=0) + batch_rows_for(normal, batch_id=1)
    kwargs, _ = write_snapshot(tmp_path, queue_rows=qrows, batch_rows=brows)
    checks = run(history, tmp_path, kwargs)
    assert any("send_batches.csv" in c for c in checks)


# ---------------- label_review_queue.csv ----------------

def test_review_crown_count_mismatch_aborts(history, tmp_path):
    kwargs, _ = write_snapshot(tmp_path)
    kwargs["review_counts"] = (REVIEW_COUNTS[0] + 1, REVIEW_COUNTS[1])
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "label review queue" in msg


def test_review_pair_count_mismatch_aborts(history, tmp_path):
    kwargs, _ = write_snapshot(tmp_path)
    kwargs["review_counts"] = (REVIEW_COUNTS[0], REVIEW_COUNTS[1] + 1)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "label review pairs" in msg


# ---------------- float tolerance ----------------

def test_a_difference_just_inside_the_tolerance_passes(history, tmp_path):
    tol = tolerance(history)
    rows = species_csv_rows()
    rows[0]["top1_accuracy"] = rows[0]["top1_accuracy"] + tol * 0.5
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    run(history, tmp_path, kwargs)  # must not raise


def test_a_difference_just_outside_the_tolerance_aborts(history, tmp_path):
    tol = tolerance(history)
    rows = species_csv_rows()
    rows[0]["top1_accuracy"] = rows[0]["top1_accuracy"] + tol * 2
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "top1_accuracy for" in msg
