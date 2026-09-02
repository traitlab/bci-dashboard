"""Direct tests for dashboard/history.py's verify_snapshot.

verify_snapshot is the single gate that aborts every page build when the
freshly computed numbers disagree with the committed model-health snapshot,
and it had no tests at all before this file (tests/test_snapshot_gate.py only
covers latest_snapshot_dir). These tests build a synthetic snapshot directory
under tmp_path from a small in-memory description and call verify_snapshot
directly. No real snapshots/ folder is read and no page is built.

    .venv/bin/pytest tests/test_verify_snapshot.py
"""

from __future__ import annotations

import copy
import csv
import inspect
import re

import pytest

# ---- a small, self-consistent snapshot description ----
# Two species, two support buckets (one per species), two confidence bands,
# a two-queue send-first pool and a two-pair review queue. Every helper below
# derives its file rows or its verify_snapshot kwargs from these constants, so
# a test that wants "everything but one thing" just calls write_snapshot() and
# overrides that one thing.

PER_SPECIES = [
    {"species": "Hura crepitans", "n_labelled_crowns": 10,
     "top1_accuracy": 0.8, "top5_accuracy": 0.9},
    {"species": "Ceiba pentandra", "n_labelled_crowns": 5,
     "top1_accuracy": 0.6, "top5_accuracy": 1.0},
]

BUCKETS = {
    "well_sampled": {"n_species": 1, "n_crowns": 10, "c1": 8},
    "rare": {"n_species": 1, "n_crowns": 5, "c1": 3},
}

BINS_ALL = [
    ("[0.0,0.2)", 2, 1),
    ("[0.2,0.4)", 3, 2),
]

NEVER_ALL = 4
UNSCOREABLE = 6
STRICT_HITS = 82
N_NO_ANSWER = 7

QUEUE_COUNTS = {"long_tail": 3, "normal": 2}
REVIEW_COUNTS = (2, 2)


def _tol(history):
    """close()'s own default tolerance, read out of verify_snapshot's source
    rather than restated as a literal here, so a change to the constant
    changes this test too."""
    src = inspect.getsource(history.verify_snapshot)
    m = re.search(r"def close\(a, b, tol=([0-9.eE+-]+)\)", src)
    assert m, "close()'s signature changed shape; update _tol()"
    return float(m.group(1))


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _species_csv_rows():
    return [{"species": d["species"], "n_labelled_crowns": d["n_labelled_crowns"],
             "top1_accuracy": d["top1_accuracy"], "top5_accuracy": d["top5_accuracy"]}
            for d in PER_SPECIES]


def _bucket_csv_rows():
    return [{"support_bucket": label, "n_species": b["n_species"], "n_crowns": b["n_crowns"],
             "top1_accuracy": b["c1"] / b["n_crowns"]}
            for label, b in BUCKETS.items()]


def _bin_csv_rows():
    rows = [{"row_type": "bin", "scope": "all_species_level_gt", "band": band,
             "n_crowns": n, "n_correct": k}
            for band, n, k in BINS_ALL]
    # A threshold row and an off-scope bin row alongside, so the row_type ==
    # "bin" and scope == "all_species_level_gt" filter is actually exercised.
    rows.append({"row_type": "threshold", "scope": "all_species_level_gt",
                 "band": ">=0.9", "n_crowns": 1, "n_correct": 1})
    rows.append({"row_type": "bin", "scope": "species_with_n_ge_5",
                 "band": "[0.0,0.2)", "n_crowns": 99, "n_correct": 99})
    return rows


def _log_lines(never_all=NEVER_ALL, unscoreable=UNSCOREABLE, strict_hits=STRICT_HITS,
               n_no_answer=N_NO_ANSWER):
    """The four run_log.txt prose lines verify_snapshot regexes out, keyed so
    a test can drop or edit exactly one."""
    return {
        "never": f"      {never_all} GT crowns across 3 species can NEVER be scored "
                 "correct from this cache.",
        "unscoreable": f"  (n=100; excludes the {unscoreable} frames that are unscoreable "
                       "by construction):",
        "strict": f"    strict top-1                      : 82.00%   ({strict_hits}/100)   "
                  "[+1.00 pp from tier d]",
        "no_answer": f"  unlabelled frames with NO answer    : {n_no_answer}  (empty "
                     "candidate list;",
    }


def _queue_rows(counts=QUEUE_COUNTS):
    """send_first_queue.csv rows: one contiguous species group per queue."""
    rows = []
    for q, n in counts.items():
        for i in range(n):
            rows.append({"queue": q, "global_key": f"{q}_{i}.JPG", "split": "unlabelled",
                         "predicted_species": f"species_{q}", "confidence": "0.500000",
                         "species_labelled_crowns": "0", "species_top1_accuracy": ""})
    return rows


def _batch_rows(queue_rows, batch_id=0):
    """A trivial single-batch repartition of queue_rows: valid, but not
    necessarily what core.chunk_send_batches would produce (see the test
    documenting that gap below)."""
    return [{"batch_id": batch_id, "species_group": r["predicted_species"],
             "global_key": r["global_key"], "queue": r["queue"]} for r in queue_rows]


def _review_rows(review_counts=REVIEW_COUNTS):
    n_crowns, n_pairs = review_counts
    pairs = [(f"gt_{i}", f"pred_{i}") for i in range(n_pairs)]
    rows = []
    for i in range(n_crowns):
        gt, pred = pairs[i % len(pairs)]
        rows.append({"global_key": f"review_{i}.JPG", "split": "test", "gt_species": gt,
                     "predicted_species": pred, "confidence": "0.900000", "labelbox_url": ""})
    return rows


def write_snapshot(tmp_path, *, per_species_rows=None, bucket_rows=None, bin_rows=None,
                    log_lines=None, queue_rows=None, batch_rows=None, review_rows=None,
                    queue_keys=None,
                    with_queue_counts=True, with_no_answer=True, with_review_counts=True):
    """Write a consistent, passing snapshot directory under tmp_path and
    return the matching verify_snapshot kwargs.

    Each *_rows / log_lines keyword substitutes perturbed content for one
    file's rows while every other file stays at its default, consistent
    content; the with_* flags control whether an optional argument (and the
    file(s) it gates) is present at all. Returns (kwargs, files) where files
    is a dict of the row lists actually written, for tests that want to
    perturb the "here" kwargs against an unperturbed file, or vice versa.
    """
    d = tmp_path
    files = {
        "per_species": per_species_rows if per_species_rows is not None else _species_csv_rows(),
        "buckets": bucket_rows if bucket_rows is not None else _bucket_csv_rows(),
        "bins": bin_rows if bin_rows is not None else _bin_csv_rows(),
    }
    _write_csv(d / "per_species_health.csv", files["per_species"],
               ["species", "n_labelled_crowns", "top1_accuracy", "top5_accuracy"])
    _write_csv(d / "support_buckets.csv", files["buckets"],
               ["support_bucket", "n_species", "n_crowns", "top1_accuracy"])
    _write_csv(d / "confidence_calibration.csv", files["bins"],
               ["row_type", "scope", "band", "n_crowns", "n_correct"])

    lines = log_lines if log_lines is not None else _log_lines()
    (d / "run_log.txt").write_text("\n".join(lines.values()) + "\n", encoding="utf-8")

    kwargs = {
        "per_species": copy.deepcopy(PER_SPECIES), "buckets": copy.deepcopy(BUCKETS),
        "bins_all": list(BINS_ALL), "never_all": NEVER_ALL, "unscoreable": UNSCOREABLE,
        "strict_hits": STRICT_HITS,
    }

    if with_no_answer:
        kwargs["n_no_answer"] = N_NO_ANSWER

    if with_queue_counts:
        qrows = queue_rows if queue_rows is not None else _queue_rows()
        brows = batch_rows if batch_rows is not None else _batch_rows(qrows)
        _write_csv(d / "send_first_queue.csv", qrows,
                   ["queue", "global_key", "split", "predicted_species", "confidence",
                    "species_labelled_crowns", "species_top1_accuracy"])
        _write_csv(d / "send_batches.csv", brows,
                   ["batch_id", "species_group", "global_key", "queue"])
        files["queue"], files["batches"] = qrows, brows
        kwargs["queue_counts"] = dict(QUEUE_COUNTS)
        if queue_keys is not None:
            kwargs["queue_keys"] = queue_keys

    if with_review_counts:
        rrows = review_rows if review_rows is not None else _review_rows()
        _write_csv(d / "label_review_queue.csv", rrows,
                   ["global_key", "split", "gt_species", "predicted_species",
                    "confidence", "labelbox_url"])
        files["review"] = rrows
        kwargs["review_counts"] = REVIEW_COUNTS

    return kwargs, files


def run(history, directory, kwargs):
    return history.verify_snapshot(str(directory), **kwargs)


def assert_aborts(history, directory, kwargs):
    """Call verify_snapshot expecting SystemExit; return its message, which
    must start with the gate's own prefix."""
    with pytest.raises(SystemExit) as exc:
        run(history, directory, kwargs)
    msg = str(exc.value)
    assert msg.startswith("VERIFY FAIL")
    return msg


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
    rows = _species_csv_rows()[:1]  # drop one species from the file
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "species here" in msg


def test_species_present_here_but_absent_from_csv_aborts(history, tmp_path):
    rows = _species_csv_rows()
    rows[1] = dict(rows[1], species="Bertholletia excelsa")  # same count, different name
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "Ceiba pentandra" in msg and "absent from" in msg


def test_labelled_crown_count_mismatch_aborts(history, tmp_path):
    rows = _species_csv_rows()
    rows[0]["n_labelled_crowns"] = rows[0]["n_labelled_crowns"] + 1
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "labelled frames for" in msg and "Hura crepitans" in msg


def test_top1_accuracy_mismatch_aborts(history, tmp_path):
    rows = _species_csv_rows()
    rows[0]["top1_accuracy"] = rows[0]["top1_accuracy"] + 0.1
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "top1_accuracy for" in msg and "Hura crepitans" in msg


def test_top5_accuracy_mismatch_aborts(history, tmp_path):
    rows = _species_csv_rows()
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
    rows = _bucket_csv_rows()
    rows[0]["n_crowns"] = rows[0]["n_crowns"] + 1
    kwargs, _ = write_snapshot(tmp_path, bucket_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "counts" in msg and "well_sampled" in msg


def test_support_bucket_first_guess_rate_mismatch_aborts(history, tmp_path):
    rows = _bucket_csv_rows()
    rows[0]["top1_accuracy"] = 0.0
    kwargs, _ = write_snapshot(tmp_path, bucket_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "first-guess rate" in msg and "well_sampled" in msg


# ---------------- confidence_calibration.csv ----------------

def test_confidence_band_absent_from_csv_aborts(history, tmp_path):
    rows = [r for r in _bin_csv_rows() if r["band"] != "[0.2,0.4)"]
    kwargs, _ = write_snapshot(tmp_path, bin_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "[0.2,0.4)" in msg and "absent from" in msg


def test_confidence_band_counts_mismatch_aborts(history, tmp_path):
    rows = _bin_csv_rows()
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
    lines = _log_lines()
    del lines["never"]
    kwargs, _ = write_snapshot(tmp_path, log_lines=lines)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "no line for" in msg


def test_unscoreable_line_missing_aborts(history, tmp_path):
    lines = _log_lines()
    del lines["unscoreable"]
    kwargs, _ = write_snapshot(tmp_path, log_lines=lines)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "no line for" in msg and "unscoreable" in msg


def test_strict_hits_line_missing_aborts(history, tmp_path):
    lines = _log_lines()
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
    lines = _log_lines()
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
    qrows = _queue_rows(counts)
    brows = _batch_rows(qrows)  # a single batch holding all `over` rows
    kwargs, _ = write_snapshot(tmp_path, queue_rows=qrows, batch_rows=brows)
    kwargs["queue_counts"] = counts
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "exceeds" in msg and "BATCH_SIZE" in msg


def test_batch_with_noncontiguous_species_group_aborts(history, tmp_path):
    qrows = _queue_rows()
    brows = _batch_rows(qrows)
    # Split the long_tail group's rows around one normal row so the same
    # species_group value reappears later in the same batch.
    long_tail = [r for r in brows if r["queue"] == "long_tail"]
    normal = [r for r in brows if r["queue"] == "normal"]
    brows = [long_tail[0], normal[0], long_tail[1], long_tail[2], normal[1]]
    kwargs, _ = write_snapshot(tmp_path, queue_rows=qrows, batch_rows=brows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "not" in msg and "contiguous" in msg


def test_send_batches_row_count_disagreeing_with_queue_aborts(history, tmp_path):
    qrows = _queue_rows()
    brows = _batch_rows(qrows)[:-1]  # one row short
    kwargs, _ = write_snapshot(tmp_path, queue_rows=qrows, batch_rows=brows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "send_batches.csv" in msg and "rows vs" in msg


def test_send_batches_global_key_set_disagreeing_aborts(history, tmp_path):
    qrows = _queue_rows()
    brows = _batch_rows(qrows)
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
    qrows = _queue_rows()
    long_tail = [r for r in qrows if r["queue"] == "long_tail"]
    normal = [r for r in qrows if r["queue"] == "normal"]
    brows = _batch_rows(long_tail, batch_id=0) + _batch_rows(normal, batch_id=1)
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
    tol = _tol(history)
    rows = _species_csv_rows()
    rows[0]["top1_accuracy"] = rows[0]["top1_accuracy"] + tol * 0.5
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    run(history, tmp_path, kwargs)  # must not raise


def test_a_difference_just_outside_the_tolerance_aborts(history, tmp_path):
    tol = _tol(history)
    rows = _species_csv_rows()
    rows[0]["top1_accuracy"] = rows[0]["top1_accuracy"] + tol * 2
    kwargs, _ = write_snapshot(tmp_path, per_species_rows=rows)
    msg = assert_aborts(history, tmp_path, kwargs)
    assert "top1_accuracy for" in msg
