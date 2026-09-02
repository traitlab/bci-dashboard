"""The model-health snapshot on disk: verify the build against it.

Everything reading measure.py's output lives here, so the renderer only
renders.

Pages report the latest state only; a trend over dated folders was
dropped 2026-08-27, since it cut points on cached-response mtime while
predictions were bulk-fetched months before labelling finished. Recover
from git history if a real label date exists.
"""

from __future__ import annotations

import glob
import os
import re
from collections import Counter

import core as hc
import queues

SNAPSHOT_DIR = re.compile(r"model-health-(\d{4}-\d{2}-\d{2})$")
SNAPSHOT_GLOB = "model-health-*"


def latest_snapshot_dir() -> str:
    """Newest model-health-<date>/ folder in the snapshot store.

    A gate on a fixed date would silently check today's numbers against an
    old measurement; the date in the folder name keeps sorting unambiguous.
    """
    found = sorted(d for d in glob.glob(os.path.join(hc.SNAPSHOT_DIR, SNAPSHOT_GLOB))
                   if SNAPSHOT_DIR.search(d))
    if not found:
        raise SystemExit(
            f"VERIFY FAIL: no {SNAPSHOT_GLOB} folder under {hc.SNAPSHOT_DIR}")
    return found[-1]


def snapshot_date_of(snap_dir: str) -> str:
    m = SNAPSHOT_DIR.search(snap_dir.rstrip("/"))
    return m.group(1) if m else "unknown"


def fail(msg):
    """One way out of every check below, worded for whoever has to fix it."""
    raise SystemExit(f"VERIFY FAIL: {msg}")


def close(a, b, tol=5e-5):
    """Rates are written to the CSV rounded, so compare them, do not equate them."""
    return abs(float(a) - float(b)) <= tol


def check_per_species(directory, per_species):
    """The species table: same species, same labelled-frame counts, same rates."""
    path = os.path.join(directory, "per_species_health.csv")
    ref = {r["species"]: r for r in hc.read_csv_rows(path)}
    if len(ref) != len(per_species):
        fail(f"{len(per_species)} species here vs {len(ref)} in {path}")
    for row in per_species:
        r = ref.get(row["species"])
        if r is None:
            fail(f"species {row['species']!r} absent from {path}")
        if int(r["n_labelled_crowns"]) != row["n_labelled_crowns"]:
            fail(f"labelled frames for {row['species']!r}")
        for col in ("top1_accuracy", "top5_accuracy"):
            if not close(r[col], row[col]):
                fail(f"{col} for {row['species']!r}")
    return (f"per_species_health.csv: {len(ref)} species, labelled frames and "
            f"both rates match")


def check_support_buckets(directory, buckets):
    """Species grouped by labelled-frame count: counts and the first-guess rate."""
    for r in hc.read_csv_rows(os.path.join(directory, "support_buckets.csv")):
        b = buckets.get(r["support_bucket"])
        if b is None:
            fail(f"labelled-frame group {r['support_bucket']!r} missing here")
        if int(r["n_crowns"]) != b["n_crowns"] or int(r["n_species"]) != b["n_species"]:
            fail(f"labelled-frame group {r['support_bucket']!r} counts")
        if not close(r["top1_accuracy"], b["c1"] / b["n_crowns"]):
            fail(f"labelled-frame group {r['support_bucket']!r} first-guess rate")
    return f"support_buckets.csv: {len(buckets)} labelled-frame groups match"


def check_confidence_bands(directory, bins_all):
    """Each confidence band, over the whole species-level set."""
    path = os.path.join(directory, "confidence_calibration.csv")
    ref = {r["band"]: r for r in hc.read_csv_rows(path)
           if r["row_type"] == "bin" and r["scope"] == "all_species_level_gt"}
    for band, n, k in bins_all:
        r = ref.get(band)
        if r is None:
            fail(f"confidence band {band!r} absent from {path}")
        if int(r["n_crowns"]) != n or int(r["n_correct"]) != k:
            fail(f"confidence band {band!r} counts")
    return f"confidence_calibration.csv: {len(bins_all)} confidence bands match"


def check_run_log(log, path, never_all, unscoreable, strict_hits):
    """Three figures that live in the run log's prose, on denominators no CSV
    uses, so they need their own check."""
    for pat, here, what in (
            (r"^\s*(\d+) GT (?:crowns|frames) across \d+ species can NEVER", never_all,
             "frames the model can never name, over every label"),
            (r"excludes the (\d+) (?:crowns|frames) that are unscoreable", unscoreable,
             "unscoreable frames inside the evaluated set"),
            (r"strict top-1\s*:\s*[\d.]+%\s*\((\d+)/", strict_hits,
             "first guesses right without name reconciliation")):
        m = re.search(pat, log, re.MULTILINE)
        if m is None:
            fail(f"no line for {what} in {path}")
        if int(m.group(1)) != here:
            fail(f"{what}: {here} here vs {m.group(1)} in {path}")
    # Named the way the headline names them, not "cannot be scored", so the check
    # message and the page prose describe the same group.
    return (f"run_log.txt: the {never_all:,}-frame ceiling, the {unscoreable:,} frames "
            f"whose species the model never names, and the {strict_hits:,} right "
            f"without name reconciliation, all match")


def check_no_answer(log, path, n_no_answer):
    """Unlabelled frames whose candidate list came back empty. The one figure no
    CSV carries, so it is read back out of the run log."""
    m = re.search(r"unlabelled (?:crowns|frames) with NO answer\s*:\s*(\d+)", log)
    if m is None:
        fail(f"no no-answer line in {path}")
    if int(m.group(1)) != n_no_answer:
        fail(f"no-answer unlabelled frames: {n_no_answer} here vs {m.group(1)} in {path}")


def check_send_first(directory, queue_counts, queue_keys):
    """The send-first queue, by queue and then row for row.

    The page prints the head of this file and tells the reader to open the rest,
    so the two orders have to be one order. Counts alone would not notice:
    measure.py and figures.py sort the same rows separately, and a changed
    tie-break moves rows without moving any count.
    """
    path = os.path.join(directory, "send_first_queue.csv")
    ref = Counter(r["queue"] for r in hc.read_csv_rows(path))
    for q, k in queue_counts.items():
        if ref.get(q, 0) != k:
            fail(f"send-first queue {q!r}: {k} here vs {ref.get(q, 0)} in {path}")
    if set(ref) - set(queue_counts):
        fail(f"send-first queues {sorted(set(ref) - set(queue_counts))} only in {path}")
    n_unlab = sum(ref.values())
    checks = []
    checks.append(f"send_first_queue.csv: {n_unlab:,} unlabelled photos across "
                  f"{len(ref)} queues match")

    if queue_keys is not None:
        csv_keys = [r["global_key"] for r in hc.read_csv_rows(path)]
        want = list(queue_keys)
        if csv_keys != want:
            i = next(i for i, (a, b) in enumerate(zip(csv_keys + [None],
                                                      want + [None])) if a != b)
            fail(f"send-first order diverges at row {i + 1}: {path} has "
                 f"{csv_keys[i] if i < len(csv_keys) else 'nothing'}, the page "
                 f"has {want[i] if i < len(want) else 'nothing'}")
        checks.append(f"send_first_queue.csv: all {len(want):,} rows in the same "
                      f"order as the page")
    return checks, n_unlab


def check_send_batches(directory, queue_path, n_unlab):
    """The batches must be a repartition of the queue and nothing else: same
    rows, every batch at most BATCH_SIZE with its species groups contiguous, no
    global_key skipped or duplicated."""
    path = os.path.join(directory, "send_batches.csv")
    brows = hc.read_csv_rows(path)
    by_batch: dict = {}
    for r in brows:
        by_batch.setdefault(r["batch_id"], []).append(r)
    for bid, rows in by_batch.items():
        if len(rows) > queues.BATCH_SIZE:
            fail(f"send_batches.csv batch {bid}: {len(rows)} rows exceeds "
                 f"BATCH_SIZE={queues.BATCH_SIZE}")
        runs = [r["species_group"] for i, r in enumerate(rows)
                if i == 0 or r["species_group"] != rows[i - 1]["species_group"]]
        if len(runs) != len(set(runs)):
            fail(f"send_batches.csv batch {bid}: species group is not "
                 f"contiguous, {runs}")
    if len(brows) != n_unlab:
        fail(f"send_batches.csv: {len(brows)} rows vs {n_unlab} in {queue_path}")
    if {r["global_key"] for r in brows} != {r["global_key"]
                                            for r in hc.read_csv_rows(queue_path)}:
        fail(f"send_batches.csv: global_key set does not match {queue_path}")
    return (f"send_batches.csv: {len(brows):,} rows in {len(by_batch)} batches, "
            f"contiguous species groups and at most {queues.BATCH_SIZE} rows each")


def check_review_queue(directory, review_counts):
    """Confident model/label disagreements: how many frames, how many pairs."""
    path = os.path.join(directory, "label_review_queue.csv")
    ref = hc.read_csv_rows(path)
    pairs = {(r["gt_species"], r["predicted_species"]) for r in ref}
    if len(ref) != review_counts[0]:
        fail(f"label review queue: {review_counts[0]} here vs {len(ref)} in {path}")
    if len(pairs) != review_counts[1]:
        fail(f"label review pairs: {review_counts[1]} here vs {len(pairs)} in {path}")
    return (f"label_review_queue.csv: {len(ref)} frames, {len(pairs)} confusion "
            f"pairs match")


def verify_snapshot(directory, *, per_species, buckets, bins_all, never_all,
                    unscoreable, strict_hits,
                    queue_counts=None, n_no_answer=None, review_counts=None,
                    queue_keys=None):
    """Abort the build if the page disagrees with measure.py's snapshot.

    One check per file the snapshot holds, each returning the line the page
    prints when it passes. ``queue_counts`` maps queue to frame count,
    ``review_counts`` is (frames, distinct confusion pairs) and ``queue_keys``
    is the page's send-first order: those three are checked against the queue
    CSVs. ``n_no_answer`` counts unlabelled frames with an empty candidate list,
    and is the one figure no CSV carries, so it is read back out of run_log.txt.
    """
    checks = [check_per_species(directory, per_species),
              check_support_buckets(directory, buckets),
              check_confidence_bands(directory, bins_all)]

    log_path = os.path.join(directory, "run_log.txt")
    with open(log_path, encoding="utf-8") as f:
        log = f.read()
    checks.append(check_run_log(log, log_path, never_all, unscoreable, strict_hits))
    if n_no_answer is not None:
        check_no_answer(log, log_path, n_no_answer)

    if queue_counts is not None:
        queue_checks, n_unlab = check_send_first(directory, queue_counts, queue_keys)
        checks += queue_checks
        checks.append(check_send_batches(
            directory, os.path.join(directory, "send_first_queue.csv"), n_unlab))

    if review_counts is not None:
        checks.append(check_review_queue(directory, review_counts))

    return checks


def model_tag_of(snap_dir: str, fallback: str) -> str:
    """Which Pl@ntNet model iteration produced a snapshot.

    Reads the endpoint and config.yaml's ``single_model_run_name`` from
    run_log.txt -- the only things on disk distinguishing iterations. Tag
    is ``<endpoint-slug>@<run-name>``; falls back to ``--model-tag`` if
    neither is found.
    """
    try:
        with open(os.path.join(snap_dir, "run_log.txt"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return fallback
    run = re.search(r"single_model_run_name '([^']+)'", text)
    if not run:
        return fallback
    region = re.search(r"identify/([A-Za-z0-9-]+)", text)
    return f"{region.group(1)}@{run.group(1)}" if region else run.group(1)
