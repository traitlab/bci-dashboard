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

from health import load_health
from core import (
    add_input_flags, summarise,
    pct, ratio, fmt, genus_of, normalize, queue_of_prediction, chunk_send_batches,
    coverage_gate_stats, coverage_split, labelbox_urls, adjudicated_keys,
    CONF_BINS, CONF_THRESHOLDS, BUCKET_ORDER, WELL_SAMPLED_MIN_N,
    RELIABLE_MIN_TOP1,
    QUEUE_ORDER, REVIEW_CONF, BATCH_SIZE, MIN_CROP_COVERAGE, CROP_COVERAGE_SWEEP,
    GT_KEY_PREFIX,
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
        w.writerow(["queue", "global_key", "split", "predicted_species", "confidence",
                    "species_labelled_crowns", "species_top1_accuracy"])
        w.writerows(queue_rows)


def write_send_batches(out_dir, batch_rows):
    """The send-first queue, batched to one botanist sitting."""
    with _csv(out_dir, "send_batches.csv") as f:
        w = csv.writer(f)
        w.writerow(["batch_id", "species_group", "global_key", "queue"])
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

    log("=" * 84)
    log("Pl@ntNet on BCI -- offline per-species model health")
    log("=" * 84)

    h = load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                    wcvp_cache=args.wcvp_cache, log=log)

    write_name_reconciliation(out_dir, h)

    log("--- EVALUABLE SETS ---")
    log(f"  GT frames joined to a cache file    : {len(h.records)}")
    log(f"  ... with >=1 prediction             : {sum(1 for r in h.records if r['ranked'])}")
    log(f"  species-level GT + >=1 prediction   : {len(h.sp_recs)}   <-- PRIMARY EVALUATION SET")
    log(f"  genus-only GT + >=1 prediction      : {len(h.genus_recs)}   (scored separately, genus level)")
    short = sum(1 for r in h.sp_recs if len(r["ranked"]) < 5)
    log(f"  primary set with <5 candidates      : {short} ({pct(short, len(h.sp_recs))})")
    log("")

    # ---------------- 6. headline ----------------
    def top1(r, key="ranked"):
        return r[key][0][0]

    def hit(r, k, key="ranked", gtkey="gt"):
        return r[gtkey] in [b for b, _ in r[key][:k]]

    sp_recs = h.sp_recs
    genus_recs = h.genus_recs

    n = len(sp_recs)
    c1 = sum(1 for r in sp_recs if top1(r) == r["gt"])
    c5 = sum(1 for r in sp_recs if hit(r, 5))
    s1 = sum(1 for r in sp_recs if top1(r, "ranked_strict") == r["gt_strict"])
    s5 = sum(1 for r in sp_recs if hit(r, 5, "ranked_strict", "gt_strict"))
    g1 = sum(1 for r in sp_recs if genus_of(top1(r)) == genus_of(r["gt"]))
    g5 = sum(1 for r in sp_recs
             if genus_of(r["gt"]) in [genus_of(b) for b, _ in r["ranked"][:5]])
    gn = len(genus_recs)
    gg1 = sum(1 for r in genus_recs if genus_of(top1(r)) == r["gt"])
    gg5 = sum(1 for r in genus_recs
              if r["gt"] in [genus_of(b) for b, _ in r["ranked"][:5]])

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
    r5 = sum(1 for r in reachable if hit(r, 5))

    # ---------------- 9. support buckets ----------------
    b_of = {d["species"]: d["support_bucket"] for d in per_species}
    B = defaultdict(lambda: dict(n_species=0, n_crowns=0, c1=0, c5=0, f1=0, fab=0))
    for d in per_species:
        B[d["support_bucket"]]["n_species"] += 1
    for r in sp_recs:
        b = B[b_of[r["gt"]]]
        b["n_crowns"] += 1
        b["c1"] += top1(r) == r["gt"]
        b["c5"] += hit(r, 5)
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

    # ---------------- 11. report ----------------
    log("=" * 84)
    log(f"HEADLINE  (species-level GT, joined, >=1 cached prediction: n={n} frames, {n_sp} species)")
    log("=" * 84)
    log(f"  top-1 accuracy                      : {pct(c1, n)}   ({c1}/{n})")
    log(f"  top-5 accuracy  (= full list)       : {pct(c5, n)}   ({c5}/{n})")
    log(f"  macro-avg per-species recall @1     : {macro1 * 100:.2f}%   (unweighted over {n_sp} species)")
    log(f"  macro-avg per-species recall @5     : {macro5 * 100:.2f}%")
    log(f"  genus-level top-1                   : {pct(g1, n)}   ({g1}/{n})")
    log(f"  genus-level top-5                   : {pct(g5, n)}   ({g5}/{n})")
    log("")
    log("  restricted to frames whose GT species appears somewhere in the corpus at all")
    log(f"  (n={len(reachable)}; excludes the {n - len(reachable)} frames that are unscoreable by construction):")
    log(f"    top-1                             : {pct(r1, len(reachable))}   ({r1}/{len(reachable)})")
    log(f"    top-5                             : {pct(r5, len(reachable))}   ({r5}/{len(reachable)})")
    log("")
    log("  sensitivity to name reconciliation (same frames, no WCVP synonym tier):")
    log(f"    strict top-1                      : {pct(s1, n)}   ({s1}/{n})   [{100.0 * (c1 - s1) / n:+.2f} pp from tier d]")
    log(f"    strict top-5                      : {pct(s5, n)}   ({s5}/{n})   [{100.0 * (c5 - s5) / n:+.2f} pp from tier d]")
    log("")
    log(f"  genus-only GT frames (n={gn}), scored at genus level:")
    log(f"    genus top-1                       : {pct(gg1, gn)}   ({gg1}/{gn})")
    log(f"    genus top-5                       : {pct(gg5, gn)}   ({gg5}/{gn})")
    log("")
    log("--- CROP-COVERAGE GATE: GATED AND UNGATED, SIDE BY SIDE ---")
    log("  Ungated scores every evaluated frame. Gated scores only the frames whose")
    log("  dominant labelled species covers at least the threshold share of the centre")
    log("  crop the model was actually sent, so the label was inside the model's view.")
    log("  The two are different populations. Neither replaces the other.")
    log(f"  {'quantity':<34} {'ungated':>12} {'gated':>12}")
    log(f"  {'frames (N)':<34} {n:>12} {gate['n_admitted']:>12}")
    log(f"  {'frame top-1':<34} {pct(c1, n):>12} {pct(gate['n_correct_top1'], gate['n_admitted']):>12}"
        f"   (N_admitted={gate['n_admitted']})")
    log(f"  {'macro per-species top-1':<34} {macro1 * 100:>11.2f}% "
        f"{gate['macro_top1'] * 100:>11.2f}%   (N_admitted={gate['n_admitted']}, "
        f"{gate['n_species']} species)")
    log(f"  {'species':<34} {n_sp:>12} {gate['n_species']:>12}")
    log(f"  threshold in force                  : {MIN_CROP_COVERAGE:.2f} "
        f"(core.MIN_CROP_COVERAGE)")
    log(f"  {'min_coverage':>12} {'N_admitted':>12} {'frame top-1':>13} "
        f"{'macro top-1':>13} {'species':>9}")
    for g in sweep:
        log(f"  {g['min_coverage']:>12.2f} {g['n_admitted']:>12} "
            f"{pct(g['n_correct_top1'], g['n_admitted']):>13} "
            f"{(g['macro_top1'] * 100):>12.2f}% {g['n_species']:>9}")
    n_unknown = sum(1 for r in sp_recs if r["crop_coverage"] is None)
    log(f"  frames with no box geometry, rejected at every threshold : {n_unknown} "
        f"({pct(n_unknown, n)})")
    # The gated N is smaller than the ungated N for two unrelated reasons, and only
    # one of them is the gate doing its job. Splitting them keeps a missing-data
    # count from reading as evidence about crop coverage.
    n_low = n - n_unknown - gate["n_admitted"]
    log(f"  so the {n - gate['n_admitted']} frames not admitted are {n_unknown} with no box "
        f"geometry to measure")
    log(f"  and {n_low} measured below the {MIN_CROP_COVERAGE:.2f} threshold.")
    admitted, _ = coverage_split(sp_recs, MIN_CROP_COVERAGE)
    mism = sum(1 for r in admitted if r["crop_dominant"] != r["gt"])
    log(f"  admitted frames whose crop-dominant species differs from the GT label : "
        f"{mism}")
    log("  A difference there means the crop is filled by a species other than the one")
    log("  the frame is labelled with, so admission alone does not make the label the")
    log("  right answer for what the model saw.")
    log("")
    log("--- SUPPORT BUCKETS (species-level GT) ---")
    log(f"  {'bucket':<8} {'species':>8} {'frames':>8} {'top-1':>9} {'top-5':>9}")
    for lab in BUCKET_ORDER:
        b = B[lab]
        if not b["n_crowns"]:
            continue
        log(f"  {lab:<8} {b['n_species']:>8} {b['n_crowns']:>8} "
            f"{pct(b['c1'], b['n_crowns']):>9} {pct(b['c5'], b['n_crowns']):>9}")
    log("")
    log(f"--- BCI SPECIES-LIST FILTER (proxy list = {len(bci_list)} distinct GT species) ---")
    log(f"  top-1 before filter                 : {pct(c1, n)}   ({c1}/{n})")
    log(f"  top-1 after  filter                 : {pct(f1, n)}   ({f1}/{n})")
    log(f"  delta                               : {100.0 * (f1 - c1) / n:+.2f} pp")
    log(f"  frames with no surviving candidate  : {f_abstain} ({pct(f_abstain, n)})")
    log(f"  {'bucket':<8} {'frames':>8} {'before':>9} {'after':>9} {'delta':>10} {'no-cand':>8}")
    for lab in BUCKET_ORDER:
        b = B[lab]
        if not b["n_crowns"]:
            continue
        log(f"  {lab:<8} {b['n_crowns']:>8} {pct(b['c1'], b['n_crowns']):>9} "
            f"{pct(b['f1'], b['n_crowns']):>9} "
            f"{100.0 * (b['f1'] - b['c1']) / b['n_crowns']:>+9.2f}p {b['fab']:>8}")
    log("")
    log("  THIS DELTA IS A LOWER BOUND. Re-ranking can only promote a species already")
    log("  present in the returned list, and the list was capped at nb-results=5.")
    log(f"    frames still wrong after filtering  : {len(still_wrong)}")
    log(f"      ... whose list was full (len={h.maxk})     : {sw_full}  <- cap could be binding;")
    log("            a correct candidate may exist at rank 6+ and was never returned")
    log(f"      ... whose list was short (len<{h.maxk})    : {sw_short}  <- cap NOT binding; the API")
    log("            returned everything it had, so no re-ranking could have helped")
    log(f"      ... full list AND GT name absent from the whole corpus : {sw_full_unreachable}")
    log("  Sizing the real gain requires a re-ingest with a larger nb-results, or the")
    log("  actual curated Pl@ntNet BCI micro-project. It cannot be estimated offline.")
    log("")
    log("  The proxy list is also OPTIMISTIC in the opposite direction: it is built from")
    log("  the GT labels themselves, so by construction it contains every species that")
    log("  can be correct and no distractor the real curated list might carry.")
    log("")
    log("--- CONFIDENCE CALIBRATION / TRIAGE FEASIBILITY ---")
    log(f"  third scope = the {len(good)} species the proposed rule would whitelist "
        f"(n>={WELL_SAMPLED_MIN_N} labelled frames AND")
    log(f"  measured top-1 >= 90%), covering {len(good_recs)} of the {n} primary frames "
        f"({pct(len(good_recs), n)}).")
    log("  Its accuracy is OPTIMISTIC: the whitelist is selected on the very frames it is")
    log("  then scored on. Treat it as an upper bound until validated on held-out frames.")
    log("")
    for scope, rs in scopes:
        log(f"  scope: {scope}   (n={len(rs)})")
        log(f"    {'conf band':<12} {'n':>7} {'top-1 acc':>11}")
        for lo, hi in CONF_BINS:
            sub = [r for r in rs if lo <= r["ranked"][0][1] < hi]
            k = sum(1 for r in sub if top1(r) == r["gt"])
            log(f"    {f'[{lo:.1f},{min(hi, 1.0):.1f})':<12} {len(sub):>7} {pct(k, len(sub)):>11}")
        log(f"    {'threshold':<12} {'n auto':>7} {'% of scope':>11} {'error rate':>11}")
        for t in CONF_THRESHOLDS:
            sub = [r for r in rs if r["ranked"][0][1] >= t]
            k = sum(1 for r in sub if top1(r) == r["gt"])
            log(f"    {'>=' + str(t):<12} {len(sub):>7} {pct(len(sub), len(rs)):>11} "
                f"{pct(len(sub) - k, len(sub)):>11}")
        log("")

    # ---------------- 12. send-first queue over the unlabelled pool ----------------
    # Which unlabelled frames reach the botanist first. Every cached response whose
    # stem no GT row joined to is an unlabelled photo with a prediction.
    joined_stems = {stem for _, stem, _ in h.joined}
    support = {d["species"]: d["n_labelled_crowns"] for d in per_species}
    top1_of = {d["species"]: d["top1_accuracy"] for d in per_species}
    queue_rows = []
    q_counts = Counter()
    n_no_answer = 0
    for stem in sorted(h.predictions):
        if stem in joined_stems:
            continue
        ranked = [(h.canon(b), s) for b, s in h.predictions[stem]]
        gk = GT_KEY_PREFIX + stem
        if not ranked:
            n_no_answer += 1
            continue
        pred, conf = ranked[0]
        q = queue_of_prediction(pred, conf, support, top1_of)
        q_counts[q] += 1
        queue_rows.append([q, gk, h.split_of.get(gk, ""), pred, f"{conf:.6f}",
                           support.get(pred, 0),
                           fmt(top1_of.get(pred)) if pred in top1_of else ""])

    # Queue order first, then weakest confidence first inside a queue: the most
    # uncertain frame of a group is the one most worth an expert look. Sorted here
    # rather than inside the writer because the batch file below is built from the
    # same list and must carry the same order.
    queue_rows.sort(key=lambda r: (QUEUE_ORDER.index(r[0]), float(r[4]), r[1]))
    write_send_first_queue(out_dir, queue_rows)

    # Species-grouped Labelbox send batches over the same priority order, capped
    # at BATCH_SIZE rows each: the CSV policy is priority-first globally, then
    # one species per batch so a send is never a mixed bag.
    batch_rows = chunk_send_batches(queue_rows, batch_size=BATCH_SIZE)
    write_send_batches(out_dir, batch_rows)

    n_unlab = sum(q_counts.values())
    n_batches = batch_rows[-1][0] if batch_rows else 0
    log("--- SEND-FIRST QUEUE (cached predictions with no GT label) ---")
    log(f"  unlabelled frames with a prediction : {n_unlab}")
    for q in QUEUE_ORDER:
        log(f"    {q:<16}: {q_counts[q]}")
    log(f"  send_batches.csv                    : {len(batch_rows)} rows in {n_batches} "
        f"batches, max {BATCH_SIZE}/batch, species groups packed whole")
    log(f"  unlabelled frames with NO answer    : {n_no_answer}  (empty candidate list;")
    log("    possible junk or non-plant photos; check a sample")
    log("    by eye before queueing, no automatic rule)")
    log("")

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

    pairs = Counter((r[2], r[3]) for r in review_rows)
    log("--- LABELS WORTH A SECOND LOOK ---")
    log(f"  first guess wrong at confidence >= {REVIEW_CONF} : {len(review_rows)} "
        f"of {n} evaluated frames ({pct(len(review_rows), n)})")
    log(f"  distinct species-to-species confusions  : {len(pairs)}")
    # Printed even at zero: a queue that silently shrank is worse than a long one.
    log(f"  suppressed, botanist confirmed the label : {n_adjudicated}")
    log("")

    log("--- FILES WRITTEN ---")
    for fn in OUTPUTS:
        log(f"  {os.path.join(out_dir, fn)}")

    with open(os.path.join(out_dir, "run_log.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(LOG_LINES) + "\n")


if __name__ == "__main__":
    main()
