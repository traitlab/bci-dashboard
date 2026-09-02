#!/usr/bin/env python3
"""
Pl@ntNet-on-BCI model health, computed entirely offline from cached API responses.

Run:  python3 dashboard/measure.py
Writes the files named in OUTPUTS below to --out-dir (default: this directory),
and prints headline numbers to stdout.

Stdlib only (no pandas/numpy). Deterministic. No network calls.
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import Counter, defaultdict

import run_log as rl
from health import load_health
from core import (
    add_input_flags, summarise,
    ratio, fmt, genus_of, normalize,
    coverage_gate_stats, labelbox_urls, adjudicated_keys,
    CONF_BINS, CONF_THRESHOLDS, BUCKET_ORDER, WELL_SAMPLED_MIN_N,
    RELIABLE_MIN_TOP1,
    REVIEW_CONF, MIN_CROP_COVERAGE, CROP_COVERAGE_SWEEP,
    GT_KEY_PREFIX, N_CANDIDATES,
)
from queues import (
    BATCH_SIZE, SEND_BATCH_COLUMNS, SEND_FIRST_COLUMNS,
    chunk_send_batches, send_first_rows,
)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Every file a run produces, in the order it reports them. Named once, so
# nothing else can drift out of sync.
OUTPUTS = ("per_species_health.csv", "support_buckets.csv", "filter_gain.csv",
           "confidence_calibration.csv", "name_reconciliation.csv",
           "send_first_queue.csv", "send_batches.csv", "label_review_queue.csv",
           "coverage_gate.csv", "run_log.txt")

LOG_LINES: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    LOG_LINES.append(msg)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=summarise(__doc__))
    add_input_flags(p)
    p.add_argument("--out-dir", default=OUT_DIR,
                   help=f"directory to write the {len(OUTPUTS)} output files to")
    return p.parse_args()


def _csv(out_dir: str, name: str):
    """Open one output CSV; keep ``newline=""`` like the others."""
    return open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8")


def write_name_reconciliation(out_dir, h):
    """Every distinct label name, its normalized form, and match tier."""
    with _csv(out_dir, "name_reconciliation.csv") as f:
        w = csv.writer(f)
        w.writerow(["gt_raw_name", "normalized", "wcvp_accepted_binomial",
                    "match_tier", "n_gt_crowns", "in_corpus_vocabulary"])
        for name, cnt in sorted(h.gt_names.items(), key=lambda x: (-x[1], x[0])):
            nn = normalize(name)
            m = h.crosswalk.get(nn, "")
            w.writerow([name, nn, m, h.tier_of_name[name], cnt,
                        (m or nn) in h.corpus_norm])


def write_per_species_health(out_dir, per_species):
    """The page's table: one row per species from the aggregation."""
    with _csv(out_dir, "per_species_health.csv") as f:
        w = csv.DictWriter(f, fieldnames=list(per_species[0].keys()))
        w.writeheader()
        for d in per_species:
            w.writerow({k: (fmt(v) if isinstance(v, float) else v) for k, v in d.items()})


def write_support_buckets(out_dir, B):
    """Species grouped by labelled-frame count."""
    with _csv(out_dir, "support_buckets.csv") as f:
        w = csv.writer(f)
        w.writerow(["support_bucket", "n_species", "n_crowns", "top1_accuracy",
                    "top5_accuracy", "n_correct_top1", "n_correct_top5"])
        for lab in BUCKET_ORDER:
            b = B[lab]
            if not b["n_crowns"]:
                continue
            w.writerow([lab, b["n_species"], b["n_crowns"],
                        fmt(ratio(b["c1"], b["n_crowns"])),
                        fmt(ratio(b["c5"], b["n_crowns"])), b["c1"], b["c5"]])


def write_filter_gain(out_dir, B, *, n, c1, f1, f_abstain):
    """What restricting candidates to the BCI list is worth, overall and
    per group."""
    with _csv(out_dir, "filter_gain.csv") as f:
        w = csv.writer(f)
        w.writerow(["scope", "n_crowns", "top1_global", "top1_bci_list_filtered",
                    "delta_pp", "n_correct_global", "n_correct_filtered",
                    "n_no_candidate_after_filter"])
        w.writerow(["ALL", n, fmt(ratio(c1, n)), fmt(ratio(f1, n)),
                    fmt(100.0 * (f1 - c1) / n, 2), c1, f1, f_abstain])
        for lab in BUCKET_ORDER:
            b = B[lab]
            if not b["n_crowns"]:
                continue
            w.writerow([f"support_{lab}", b["n_crowns"],
                        fmt(ratio(b["c1"], b["n_crowns"])),
                        fmt(ratio(b["f1"], b["n_crowns"])),
                        fmt(100.0 * (b["f1"] - b["c1"]) / b["n_crowns"], 2),
                        b["c1"], b["f1"], b["fab"]])


def write_confidence_calibration(out_dir, scopes, top1):
    """Accuracy by confidence band, and at each threshold, per scope."""
    with _csv(out_dir, "confidence_calibration.csv") as f:
        w = csv.writer(f)
        w.writerow(["row_type", "scope", "band", "n_crowns", "top1_accuracy",
                    "fraction_of_scope", "n_correct", "n_wrong",
                    "error_rate_if_auto_accepted"])
        for scope, rs in scopes:
            for lo, hi in CONF_BINS:
                sub = [r for r in rs if lo <= r["ranked"][0][1] < hi]
                k = sum(1 for r in sub if top1(r) == r["gt"])
                w.writerow(["bin", scope, f"[{lo:.1f},{min(hi, 1.0):.1f})", len(sub),
                            fmt(ratio(k, len(sub))), fmt(ratio(len(sub), len(rs))),
                            k, len(sub) - k, ""])
            for t in CONF_THRESHOLDS:
                sub = [r for r in rs if r["ranked"][0][1] >= t]
                k = sum(1 for r in sub if top1(r) == r["gt"])
                w.writerow(["threshold", scope, f">={t}", len(sub),
                            fmt(ratio(k, len(sub))), fmt(ratio(len(sub), len(rs))),
                            k, len(sub) - k, fmt(ratio(len(sub) - k, len(sub)))])


def write_coverage_gate(out_dir, sweep):
    """The headline at every crop-coverage threshold."""
    with _csv(out_dir, "coverage_gate.csv") as f:
        w = csv.writer(f)
        w.writerow(["min_coverage", "n_frames_admitted", "crown_top1",
                    "macro_per_species_top1", "n_species"])
        for g in sweep:
            w.writerow([f"{g['min_coverage']:.2f}", g["n_admitted"],
                        fmt(g["micro_top1"]), fmt(g["macro_top1"]), g["n_species"]])


def write_send_first_queue(out_dir, queue_rows):
    """The unlabelled pool in send order; send_batches must match it."""
    with _csv(out_dir, "send_first_queue.csv") as f:
        w = csv.writer(f)
        w.writerow(SEND_FIRST_COLUMNS)
        w.writerows(queue_rows)


def write_send_batches(out_dir, batch_rows):
    """The send-first queue, batched to one botanist sitting."""
    with _csv(out_dir, "send_batches.csv") as f:
        w = csv.writer(f)
        w.writerow(SEND_BATCH_COLUMNS)
        w.writerows(batch_rows)


def write_label_review_queue(out_dir, review_rows):
    """Confident model/label disagreements, most confident first."""
    with _csv(out_dir, "label_review_queue.csv") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "split", "gt_species", "predicted_species",
                    "confidence", "labelbox_url"])
        w.writerows(review_rows)


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir
    # Up front, not at the first open(): a missing directory would otherwise
    # surface only after the whole load_health pass had run.
    os.makedirs(out_dir, exist_ok=True)

    log(rl.RULE)
    log("Pl@ntNet on BCI -- offline per-species model health")
    log(rl.RULE)

    h = load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                    wcvp_cache=args.wcvp_cache, log=log)

    write_name_reconciliation(out_dir, h)

    rl.log_evaluable_sets(log, h)

    # ---------------- 6. headline ----------------
    def top1(r, key="ranked"):
        return r[key][0][0]

    def hit(r, k, key="ranked", gtkey="gt"):
        return r[gtkey] in [b for b, _ in r[key][:k]]

    sp_recs = h.sp_recs
    genus_recs = h.genus_recs

    n = len(sp_recs)
    c1 = sum(1 for r in sp_recs if top1(r) == r["gt"])
    c5 = sum(1 for r in sp_recs if hit(r, N_CANDIDATES))
    s1 = sum(1 for r in sp_recs if top1(r, "ranked_strict") == r["gt_strict"])
    s5 = sum(1 for r in sp_recs if hit(r, N_CANDIDATES, "ranked_strict", "gt_strict"))
    g1 = sum(1 for r in sp_recs if genus_of(top1(r)) == genus_of(r["gt"]))
    g5 = sum(1 for r in sp_recs
             if genus_of(r["gt"]) in [genus_of(b) for b, _ in r["ranked"][:N_CANDIDATES]])
    gn = len(genus_recs)
    gg1 = sum(1 for r in genus_recs if genus_of(top1(r)) == r["gt"])
    gg5 = sum(1 for r in genus_recs
              if r["gt"] in [genus_of(b) for b, _ in r["ranked"][:N_CANDIDATES]])

    per_species = h.per_species
    n_sp = len(per_species)
    macro1 = sum(d["top1_accuracy"] for d in per_species) / n_sp
    macro5 = sum(d["top5_accuracy"] for d in per_species) / n_sp

    write_per_species_health(out_dir, per_species)

    # ---------------- 8. BCI species-list filter ----------------
    bci_list = {d["species"] for d in per_species}
    f1 = f_abstain = 0
    filt = {}
    for r in sp_recs:
        keep = [(b, s) for b, s in r["ranked"] if b in bci_list]
        if keep:
            filt[r["global_key"]] = keep[0][0]
            f1 += keep[0][0] == r["gt"]
        else:
            filt[r["global_key"]] = None
            f_abstain += 1

    # Re-ranking can only promote a species already in the returned list, so
    # reachability is tested on the canonicalized names the accuracy is scored on.
    # corpus_norm alone understates it and disagrees with per_species_health.csv.
    def reachable_gt(name: str) -> bool:
        return name in h.corpus_norm or name in h.corpus_canon

    still_wrong = [r for r in sp_recs if filt[r["global_key"]] != r["gt"]]
    sw_full = sum(1 for r in still_wrong if len(r["ranked"]) == h.maxk)
    sw_short = len(still_wrong) - sw_full
    sw_full_unreachable = sum(1 for r in still_wrong
                              if len(r["ranked"]) == h.maxk and not reachable_gt(r["gt"]))

    # Attainable ceiling: frames whose GT name exists somewhere in the corpus at all.
    reachable = [r for r in sp_recs if reachable_gt(r["gt"])]
    r1 = sum(1 for r in reachable if top1(r) == r["gt"])
    r5 = sum(1 for r in reachable if hit(r, N_CANDIDATES))

    # ---------------- 9. support buckets ----------------
    b_of = {d["species"]: d["support_bucket"] for d in per_species}
    B = defaultdict(lambda: dict(n_species=0, n_crowns=0, c1=0, c5=0, f1=0, fab=0))
    for d in per_species:
        B[d["support_bucket"]]["n_species"] += 1
    for r in sp_recs:
        b = B[b_of[r["gt"]]]
        b["n_crowns"] += 1
        b["c1"] += top1(r) == r["gt"]
        b["c5"] += hit(r, N_CANDIDATES)
        ft = filt[r["global_key"]]
        if ft is None:
            b["fab"] += 1
        else:
            b["f1"] += ft == r["gt"]

    write_support_buckets(out_dir, B)

    write_filter_gain(out_dir, B, n=n, c1=c1, f1=f1, f_abstain=f_abstain)

    # ---------------- 10. confidence calibration ----------------
    well = {d["species"] for d in per_species if d["n_labelled_crowns"] >= WELL_SAMPLED_MIN_N}
    well_recs = [r for r in sp_recs if r["gt"] in well]
    # The species the proposed triage rule would actually whitelist: measured
    # well AND measured accurate. NOTE this whitelist is chosen on the same
    # frames it is then scored on: an optimistic, selection-biased number
    # rather than an out-of-sample estimate.
    good = {d["species"] for d in per_species
            if d["n_labelled_crowns"] >= WELL_SAMPLED_MIN_N
            and d["top1_accuracy"] >= RELIABLE_MIN_TOP1}
    good_recs = [r for r in sp_recs if r["gt"] in good]
    scopes = [("all_species_level_gt", sp_recs),
              (f"species_with_n_ge_{WELL_SAMPLED_MIN_N}", well_recs),
              (f"species_n_ge_{WELL_SAMPLED_MIN_N}_and_top1_ge_{RELIABLE_MIN_TOP1:.2f}",
               good_recs)]

    write_confidence_calibration(out_dir, scopes, top1)

    # ---------------- 10b. crop-coverage gate ----------------
    # How the headline moves once only frames whose dominant labelled species fills
    # the crop are scored. Both rates are kept, so neither replaces the other.
    sweep = [coverage_gate_stats(sp_recs, t) for t in CROP_COVERAGE_SWEEP]
    gate = coverage_gate_stats(sp_recs, MIN_CROP_COVERAGE)
    write_coverage_gate(out_dir, sweep)

    rl.log_headline(log, n, n_sp, c1, c5, macro1, macro5, g1, g5, reachable, r1, r5, s1, s5, gn, gg1, gg5)

    rl.log_gate_comparison(log, sp_recs, sweep, gate, n, n_sp, c1, macro1)

    rl.log_support_buckets(log, B)

    rl.log_filter_gain(log, B, bci_list, n, c1, f1, f_abstain, still_wrong,
                       h.maxk, sw_full, sw_short, sw_full_unreachable)

    rl.log_calibration(log, scopes, top1, n, good, good_recs)

    # ---------------- 12. send-first queue over the unlabelled pool ----------------
    # Which unlabelled frames reach the botanist first. Every cached response whose
    # stem no GT row joined to is an unlabelled photo with a prediction.
    joined_stems = {stem for _, stem, _ in h.joined}
    support = {d["species"]: d["n_labelled_crowns"] for d in per_species}
    top1_of = {d["species"]: d["top1_accuracy"] for d in per_species}
    # The queue decision and its order live in core, because figures.py builds
    # the same list for the page. The CSV columns are this file's own.
    decided, n_no_answer = send_first_rows(h.predictions, joined_stems, h.canon,
                                           support, top1_of)
    q_counts = Counter(q for q, _, _, _ in decided)
    queue_rows = [[q, GT_KEY_PREFIX + stem, h.split_of.get(GT_KEY_PREFIX + stem, ""),
                   pred, f"{conf:.6f}", support.get(pred, 0),
                   fmt(top1_of.get(pred)) if pred in top1_of else ""]
                  for q, stem, pred, conf in decided]
    write_send_first_queue(out_dir, queue_rows)

    # Species-grouped Labelbox send batches over the same priority order, capped
    # at BATCH_SIZE rows each: the CSV policy is priority-first globally, then
    # one species per batch so a send is never a mixed bag.
    batch_rows = chunk_send_batches(queue_rows, batch_size=BATCH_SIZE)
    write_send_batches(out_dir, batch_rows)

    rl.log_send_queue(log, q_counts, batch_rows, n_no_answer)

    # ---------------- 13. labels worth a second look ----------------
    # First guess wrong at high confidence: either the label or the model is wrong.
    # Worked after the cheap queues. Sorted most confident first.
    urls = labelbox_urls()
    adjudicated = adjudicated_keys()
    raised = [r for r in sp_recs
              if top1(r) != r["gt"] and r["ranked"][0][1] >= REVIEW_CONF]
    review_rows = [[r["global_key"], r["split"], r["gt"], top1(r),
                    f"{r['ranked'][0][1]:.6f}", urls.get(r["global_key"], "")]
                   for r in raised if r["global_key"] not in adjudicated]
    n_adjudicated = len(raised) - len(review_rows)
    review_rows.sort(key=lambda r: (-float(r[4]), r[1], r[0]))
    write_label_review_queue(out_dir, review_rows)

    rl.log_review_queue(log, review_rows, n, n_adjudicated)

    rl.log_files_written(log, out_dir, OUTPUTS)

    with open(os.path.join(out_dir, "run_log.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(LOG_LINES) + "\n")


if __name__ == "__main__":
    main()
