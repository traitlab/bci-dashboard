"""A synthetic snapshot directory, built row by row from one description.

`tests/test_verify_snapshot.py` reads it. It lives here rather than in that
file because it is a builder, not a test: the file was over the workspace's
500-line rule, and the half a reader wants is the half that says what the gate
must catch.

Two species, two support buckets (one per species), two confidence bands, a
two-queue send-first pool and a two-pair review queue. Every helper derives its
file rows or its verify_snapshot kwargs from the constants at the top, so a
test that wants "everything but one thing" calls `write_snapshot()` and
overrides that one thing.
"""

from __future__ import annotations

import copy
import csv
import inspect

import pytest

import queues


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


def tolerance(history):
    """``close``'s own default tolerance, taken off the function rather than
    restated as a literal here, so a change to it changes this test too."""
    default = inspect.signature(history.close).parameters["tol"].default
    assert isinstance(default, float), (
        f"close()'s tol is no longer a plain float default: {default!r}")
    return default


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def species_csv_rows():
    return [{"species": d["species"], "n_labelled_crowns": d["n_labelled_crowns"],
             "top1_accuracy": d["top1_accuracy"], "top5_accuracy": d["top5_accuracy"]}
            for d in PER_SPECIES]


def bucket_csv_rows():
    return [{"support_bucket": label, "n_species": b["n_species"], "n_crowns": b["n_crowns"],
             "top1_accuracy": b["c1"] / b["n_crowns"]}
            for label, b in BUCKETS.items()]


def bin_csv_rows():
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


def log_lines_default(never_all=NEVER_ALL, unscoreable=UNSCOREABLE, strict_hits=STRICT_HITS,
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


def queue_rows_for(counts=QUEUE_COUNTS):
    """send_first_queue.csv rows: one contiguous species group per queue."""
    rows = []
    for q, n in counts.items():
        for i in range(n):
            rows.append({"queue": q, "global_key": f"{q}_{i}.JPG", "split": "unlabelled",
                         "predicted_species": f"species_{q}", "confidence": "0.500000",
                         "species_labelled_crowns": "0", "species_top1_accuracy": "",
                         "novelty_rank": ""})
    return rows


def batch_rows_for(queue_rows, batch_id=None):
    """The repartition queues.chunk_send_batches makes from queue_rows.

    verify_snapshot requires that exact assignment, so a fixture that invents
    its own batch_id is a fixture the check rejects. Pass ``batch_id`` to force
    a flat single-batch repartition instead: structurally valid, and the
    wrong assignment, which is what the test for that abort needs.
    """
    if batch_id is not None:
        return [{"batch_id": batch_id, "species_group": r["predicted_species"],
                 "global_key": r["global_key"], "queue": r["queue"]}
                for r in queue_rows]
    rows = [[r[c] for c in queues.SEND_FIRST_COLUMNS] for r in queue_rows]
    return [dict(zip(queues.SEND_BATCH_COLUMNS, b))
            for b in queues.chunk_send_batches(rows)]


def review_rows_for(review_counts=REVIEW_COUNTS):
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
        "per_species": per_species_rows if per_species_rows is not None else species_csv_rows(),
        "buckets": bucket_rows if bucket_rows is not None else bucket_csv_rows(),
        "bins": bin_rows if bin_rows is not None else bin_csv_rows(),
    }
    write_csv(d / "per_species_health.csv", files["per_species"],
               ["species", "n_labelled_crowns", "top1_accuracy", "top5_accuracy"])
    write_csv(d / "support_buckets.csv", files["buckets"],
               ["support_bucket", "n_species", "n_crowns", "top1_accuracy"])
    write_csv(d / "confidence_calibration.csv", files["bins"],
               ["row_type", "scope", "band", "n_crowns", "n_correct"])

    lines = log_lines if log_lines is not None else log_lines_default()
    (d / "run_log.txt").write_text("\n".join(lines.values()) + "\n", encoding="utf-8")

    kwargs = {
        "per_species": copy.deepcopy(PER_SPECIES), "buckets": copy.deepcopy(BUCKETS),
        "bins_all": list(BINS_ALL), "never_all": NEVER_ALL, "unscoreable": UNSCOREABLE,
        "strict_hits": STRICT_HITS,
    }

    if with_no_answer:
        kwargs["n_no_answer"] = N_NO_ANSWER

    if with_queue_counts:
        qrows = queue_rows if queue_rows is not None else queue_rows_for()
        brows = batch_rows if batch_rows is not None else batch_rows_for(qrows)
        write_csv(d / "send_first_queue.csv", qrows,
                   ["queue", "global_key", "split", "predicted_species", "confidence",
                    "species_labelled_crowns", "species_top1_accuracy", "novelty_rank"])
        write_csv(d / "send_batches.csv", brows,
                   ["batch_id", "species_group", "global_key", "queue"])
        files["queue"], files["batches"] = qrows, brows
        kwargs["queue_counts"] = dict(QUEUE_COUNTS)
        if queue_keys is not None:
            kwargs["queue_keys"] = queue_keys

    if with_review_counts:
        rrows = review_rows if review_rows is not None else review_rows_for()
        write_csv(d / "label_review_queue.csv", rrows,
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
