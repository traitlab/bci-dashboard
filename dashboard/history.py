"""The model-health snapshot on disk: verify the build against it.

Everything that reads measure.py's *output* lives here, so the renderer only
computes and renders. ``latest_snapshot_dir`` picks the folder to check
against and ``verify_snapshot`` aborts the build when the page disagrees with
that folder's CSVs or run log.

The page reports the latest state only. It carried a trend over the dated
snapshot folders until 2026-08-27; that was dropped because the series was not
what it claimed. Points were cut on the mtime of each cached Pl@ntNet
response, and predictions were bulk-fetched in May while labelling ran on for
months, so August labels were back-dated to May. Recover it from git history
if a real label date ever exists to cut on. Stdlib only, no network.
"""

from __future__ import annotations

import glob
import os
import re
from collections import Counter

import core as hc
from assets import weight_pair_ok

SNAPSHOT_DIR = re.compile(r"model-health-(\d{4}-\d{2}-\d{2})$")
SNAPSHOT_GLOB = "model-health-*"


def latest_snapshot_dir() -> str:
    """Newest model-health-<date>/ folder in the snapshot store.

    Both pages gate on a snapshot folder, and a gate aimed at a fixed date
    silently checks today's numbers against an old measurement and appends
    today's trend points to that old folder's history. The date is in the
    folder name, so sorting is unambiguous.
    """
    found = sorted(d for d in glob.glob(os.path.join(hc.SNAPSHOT_DIR, SNAPSHOT_GLOB))
                   if SNAPSHOT_DIR.search(d))
    if not found:
        raise SystemExit(
            f"VERIFY FAIL: no {SNAPSHOT_GLOB} folder under {hc.SNAPSHOT_DIR}")
    return found[-1]


def snapshot_date_of(snap_dir: str) -> str:
    """The date in a model-health-<date>/ folder name, which is the snapshot's date."""
    m = SNAPSHOT_DIR.search(snap_dir.rstrip("/"))
    return m.group(1) if m else "unknown"


def verify_snapshot(directory, *, per_species, buckets, bins_all, never_all,
                    unscoreable, strict_hits,
                    queue_counts=None, n_no_answer=None, review_counts=None):
    """Abort the build if the page disagrees with measure.py's snapshot.

    ``queue_counts`` maps queue name to crown count over the unlabelled pool,
    ``n_no_answer`` counts unlabelled crowns whose candidate list came back
    empty, and ``review_counts`` is (crowns, distinct confusion pairs) for the
    high-confidence label disagreements. All three are checked against the two
    queue CSVs when given.
    """
    def fail(msg):
        raise SystemExit(f"VERIFY FAIL: {msg}")

    def close(a, b, tol=5e-5):
        return abs(float(a) - float(b)) <= tol

    checks = []
    path = os.path.join(directory, "per_species_health.csv")
    ref = {r["species"]: r for r in hc.read_csv_rows(path)}
    if len(ref) != len(per_species):
        fail(f"{len(per_species)} species here vs {len(ref)} in {path}")
    for row in per_species:
        r = ref.get(row["species"])
        if r is None:
            fail(f"species {row['species']!r} absent from {path}")
        if int(r["n_labelled_crowns"]) != row["n_labelled_crowns"]:
            fail(f"labelled crowns for {row['species']!r}")
        for col in ("top1_accuracy", "top5_accuracy"):
            if not close(r[col], row[col]):
                fail(f"{col} for {row['species']!r}")
    checks.append(f"per_species_health.csv: {len(ref)} species, crowns and both rates match")

    for r in hc.read_csv_rows(os.path.join(directory, "support_buckets.csv")):
        b = buckets.get(r["support_bucket"])
        if b is None:
            fail(f"labelled-crown group {r['support_bucket']!r} missing here")
        if int(r["n_crowns"]) != b["n_crowns"] or int(r["n_species"]) != b["n_species"]:
            fail(f"labelled-crown group {r['support_bucket']!r} counts")
        if not close(r["top1_accuracy"], b["c1"] / b["n_crowns"]):
            fail(f"labelled-crown group {r['support_bucket']!r} first-guess rate")
    checks.append(f"support_buckets.csv: {len(buckets)} labelled-crown groups match")

    path = os.path.join(directory, "confidence_calibration.csv")
    ref_bins = {r["band"]: r for r in hc.read_csv_rows(path)
                if r["row_type"] == "bin" and r["scope"] == "all_species_level_gt"}
    for band, n, k in bins_all:
        r = ref_bins.get(band)
        if r is None:
            fail(f"confidence band {band!r} absent from {path}")
        if int(r["n_crowns"]) != n or int(r["n_correct"]) != k:
            fail(f"confidence band {band!r} counts")
    checks.append(f"confidence_calibration.csv: {len(bins_all)} confidence bands match")

    # These three live in the run log's prose, on denominators no CSV uses. Checking
    # them here once caught the report and the CSVs disagreeing by two crowns.
    path = os.path.join(directory, "run_log.txt")
    with open(path, encoding="utf-8") as f:
        log = f.read()
    for pat, here, what in (
            (r"^\s*(\d+) GT (?:crowns|frames) across \d+ species can NEVER", never_all,
             "crowns the model can never name, over every label"),
            (r"excludes the (\d+) (?:crowns|frames) that are unscoreable", unscoreable,
             "unscoreable crowns inside the evaluated set"),
            (r"strict top-1\s*:\s*[\d.]+%\s*\((\d+)/", strict_hits,
             "first guesses right without name reconciliation")):
        m = re.search(pat, log, re.M)
        if m is None:
            fail(f"no line for {what} in {path}")
        if int(m.group(1)) != here:
            fail(f"{what}: {here} here vs {m.group(1)} in {path}")
    checks.append(f"run_log.txt: the {never_all}-crown ceiling, the {unscoreable} unscoreable "
                  f"evaluated crowns and the {strict_hits}-hit unreconciled baseline match")

    if n_no_answer is not None:
        m = re.search(r"unlabelled (?:crowns|frames) with NO answer\s*:\s*(\d+)", log)
        if m is None:
            fail(f"no no-answer line in {path}")
        if int(m.group(1)) != n_no_answer:
            fail(f"no-answer unlabelled crowns: {n_no_answer} here vs {m.group(1)} in {path}")

    if queue_counts is not None:
        path = os.path.join(directory, "send_first_queue.csv")
        ref = Counter(r["queue"] for r in hc.read_csv_rows(path))
        for q, k in queue_counts.items():
            if ref.get(q, 0) != k:
                fail(f"send-first queue {q!r}: {k} here vs {ref.get(q, 0)} in {path}")
        if set(ref) - set(queue_counts):
            fail(f"send-first queues {sorted(set(ref) - set(queue_counts))} only in {path}")
        n_unlab = sum(ref.values())
        checks.append(f"send_first_queue.csv: {n_unlab:,} unlabelled crowns across "
                      f"{len(ref)} queues match")

        # send_batches.csv must be a capped-size repartition of the exact same
        # rows: same total, every batch at most BATCH_SIZE rows with its
        # species groups contiguous, no global_key skipped or duplicated.
        bpath = os.path.join(directory, "send_batches.csv")
        brows = hc.read_csv_rows(bpath)
        by_batch: dict = {}
        for r in brows:
            by_batch.setdefault(r["batch_id"], []).append(r)
        for bid, rows in by_batch.items():
            if len(rows) > hc.BATCH_SIZE:
                fail(f"send_batches.csv batch {bid}: {len(rows)} rows exceeds "
                     f"BATCH_SIZE={hc.BATCH_SIZE}")
            runs = [r["species_group"] for i, r in enumerate(rows)
                    if i == 0 or r["species_group"] != rows[i - 1]["species_group"]]
            if len(runs) != len(set(runs)):
                fail(f"send_batches.csv batch {bid}: species group is not "
                     f"contiguous, {runs}")
        if len(brows) != n_unlab:
            fail(f"send_batches.csv: {len(brows)} rows vs {n_unlab} in {path}")
        if {r["global_key"] for r in brows} != {r["global_key"]
                                                 for r in hc.read_csv_rows(path)}:
            fail(f"send_batches.csv: global_key set does not match {path}")
        checks.append(f"send_batches.csv: {len(brows):,} rows in {len(by_batch)} batches, "
                      f"contiguous species groups and at most {hc.BATCH_SIZE} rows each")

    if review_counts is not None:
        path = os.path.join(directory, "label_review_queue.csv")
        ref = hc.read_csv_rows(path)
        pairs = {(r["gt_species"], r["predicted_species"]) for r in ref}
        if len(ref) != review_counts[0]:
            fail(f"label review queue: {review_counts[0]} here vs {len(ref)} in {path}")
        if len(pairs) != review_counts[1]:
            fail(f"label review pairs: {review_counts[1]} here vs {len(pairs)} in {path}")
        checks.append(f"label_review_queue.csv: {len(ref)} crowns, {len(pairs)} confusion "
                      f"pairs match")

    if not weight_pair_ok():
        fail("the weighting bars are drawn wrong: a bigger share must be a wider band")
    checks.append("charts: a bigger share is drawn wider")
    return checks


def model_tag_of(snap_dir: str, fallback: str) -> str:
    """Which Pl@ntNet model iteration produced a snapshot.

    Read from that snapshot's own run_log.txt, which records the endpoint and
    config.yaml's ``single_model_run_name`` (currently ``v7.4-2026-03-27``).
    Those two strings are the only thing on disk that tells one Pl@ntNet
    iteration from the next, so the tag is ``<endpoint-slug>@<run-name>``. A
    log naming neither falls back to ``--model-tag``, never to an invented tag.
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
