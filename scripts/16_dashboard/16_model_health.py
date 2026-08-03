#!/usr/bin/env python3
"""
Pl@ntNet-on-BCI model health, computed entirely offline from cached API responses.

Run:  python3 16_model_health.py
Writes per_species_health.csv, support_buckets.csv, filter_gain.csv,
confidence_calibration.csv, name_reconciliation.csv and run_log.txt to
--out-dir (default: this directory), and prints headline numbers to stdout.

Stdlib only (no pandas/numpy). Deterministic. No network calls.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict

from health_core import (
    load_health,
    pct, ratio, fmt, genus_of, normalize,
    CONF_BINS, CONF_THRESHOLDS, BUCKET_ORDER, WELL_SAMPLED_MIN_N,
    GT_CSV, SPLITS_CSV, CACHE_DIR, WCVP_CACHE_JSON,
)

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_LINES: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    LOG_LINES.append(msg)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gt", default=GT_CSV, help="path to gt_dominant_taxon.csv")
    p.add_argument("--splits", default=SPLITS_CSV, help="path to splits.csv")
    p.add_argument("--cache-dir", default=CACHE_DIR, help="path to the Pl@ntNet response cache dir")
    p.add_argument("--wcvp-cache", default=WCVP_CACHE_JSON, help="path to the local WCVP crosswalk cache")
    p.add_argument("--out-dir", default=OUT_DIR, help="directory to write the six output files to")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir

    log("=" * 84)
    log("Pl@ntNet on BCI -- offline per-species model health")
    log("=" * 84)

    try:
        h = load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                         wcvp_cache=args.wcvp_cache, log=log)
    except FileNotFoundError as e:
        sys.exit(str(e))

    with open(os.path.join(out_dir, "name_reconciliation.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["gt_raw_name", "normalized", "wcvp_accepted_binomial",
                    "match_tier", "n_gt_crowns", "in_corpus_vocabulary"])
        for name, cnt in sorted(h.gt_names.items(), key=lambda x: (-x[1], x[0])):
            nn = normalize(name)
            m = h.crosswalk.get(nn, "")
            w.writerow([name, nn, m, h.tier_of_name[name], cnt,
                        (m or nn) in h.corpus_norm])

    log("--- EVALUABLE SETS ---")
    log(f"  GT crowns joined to a cache file    : {len(h.records)}")
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

    with open(os.path.join(out_dir, "per_species_health.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(per_species[0].keys()))
        w.writeheader()
        for d in per_species:
            w.writerow({k: (fmt(v) if isinstance(v, float) else v) for k, v in d.items()})

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

    # How binding is the nb-results=5 cap on the filter simulation? Re-ranking can
    # only ever promote a species that is already somewhere in the returned list.
    still_wrong = [r for r in sp_recs if filt[r["global_key"]] != r["gt"]]
    sw_full = sum(1 for r in still_wrong if len(r["ranked"]) == h.maxk)
    sw_short = len(still_wrong) - sw_full
    sw_full_unreachable = sum(1 for r in still_wrong
                              if len(r["ranked"]) == h.maxk and r["gt"] not in h.corpus_norm)

    # Attainable ceiling: crowns whose GT name exists somewhere in the corpus at all.
    reachable = [r for r in sp_recs if r["gt"] in h.corpus_norm]
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

    with open(os.path.join(out_dir, "support_buckets.csv"), "w", newline="", encoding="utf-8") as f:
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

    with open(os.path.join(out_dir, "filter_gain.csv"), "w", newline="", encoding="utf-8") as f:
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

    # ---------------- 10. confidence calibration ----------------
    well = {d["species"] for d in per_species if d["n_labelled_crowns"] >= WELL_SAMPLED_MIN_N}
    well_recs = [r for r in sp_recs if r["gt"] in well]
    # The species the proposed triage rule would actually whitelist: measured
    # well AND measured accurate. NOTE this whitelist is chosen on the same
    # crowns it is then scored on -- see the README caveat on selection bias.
    good = {d["species"] for d in per_species
            if d["n_labelled_crowns"] >= WELL_SAMPLED_MIN_N and d["top1_accuracy"] >= 0.90}
    good_recs = [r for r in sp_recs if r["gt"] in good]
    scopes = [("all_species_level_gt", sp_recs),
              (f"species_with_n_ge_{WELL_SAMPLED_MIN_N}", well_recs),
              (f"species_n_ge_{WELL_SAMPLED_MIN_N}_and_top1_ge_0.90", good_recs)]

    with open(os.path.join(out_dir, "confidence_calibration.csv"), "w", newline="", encoding="utf-8") as f:
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

    # ---------------- 11. report ----------------
    log("=" * 84)
    log(f"HEADLINE  (species-level GT, joined, >=1 cached prediction: n={n} crowns, {n_sp} species)")
    log("=" * 84)
    log(f"  top-1 accuracy                      : {pct(c1, n)}   ({c1}/{n})")
    log(f"  top-5 accuracy  (= full list)       : {pct(c5, n)}   ({c5}/{n})")
    log(f"  macro-avg per-species recall @1     : {macro1 * 100:.2f}%   (unweighted over {n_sp} species)")
    log(f"  macro-avg per-species recall @5     : {macro5 * 100:.2f}%")
    log(f"  genus-level top-1                   : {pct(g1, n)}   ({g1}/{n})")
    log(f"  genus-level top-5                   : {pct(g5, n)}   ({g5}/{n})")
    log("")
    log(f"  restricted to crowns whose GT species appears somewhere in the corpus at all")
    log(f"  (n={len(reachable)}; excludes the {n - len(reachable)} crowns that are unscoreable by construction):")
    log(f"    top-1                             : {pct(r1, len(reachable))}   ({r1}/{len(reachable)})")
    log(f"    top-5                             : {pct(r5, len(reachable))}   ({r5}/{len(reachable)})")
    log("")
    log("  sensitivity to name reconciliation (same crowns, no WCVP synonym tier):")
    log(f"    strict top-1                      : {pct(s1, n)}   ({s1}/{n})   [{100.0 * (c1 - s1) / n:+.2f} pp from tier d]")
    log(f"    strict top-5                      : {pct(s5, n)}   ({s5}/{n})   [{100.0 * (c5 - s5) / n:+.2f} pp from tier d]")
    log("")
    log(f"  genus-only GT crowns (n={gn}), scored at genus level:")
    log(f"    genus top-1                       : {pct(gg1, gn)}   ({gg1}/{gn})")
    log(f"    genus top-5                       : {pct(gg5, gn)}   ({gg5}/{gn})")
    log("")
    log("--- SUPPORT BUCKETS (species-level GT) ---")
    log(f"  {'bucket':<8} {'species':>8} {'crowns':>8} {'top-1':>9} {'top-5':>9}")
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
    log(f"  crowns with no surviving candidate  : {f_abstain} ({pct(f_abstain, n)})")
    log(f"  {'bucket':<8} {'crowns':>8} {'before':>9} {'after':>9} {'delta':>10} {'no-cand':>8}")
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
    log(f"    crowns still wrong after filtering  : {len(still_wrong)}")
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
        f"(n>={WELL_SAMPLED_MIN_N} labelled crowns AND")
    log(f"  measured top-1 >= 90%), covering {len(good_recs)} of the {n} primary crowns "
        f"({pct(len(good_recs), n)}).")
    log("  Its accuracy is OPTIMISTIC: the whitelist is selected on the very crowns it is")
    log("  then scored on. Treat it as an upper bound until validated on held-out crowns.")
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

    log("--- FILES WRITTEN ---")
    for fn in ("per_species_health.csv", "support_buckets.csv", "filter_gain.csv",
               "confidence_calibration.csv", "name_reconciliation.csv", "run_log.txt"):
        log(f"  {os.path.join(out_dir, fn)}")

    with open(os.path.join(out_dir, "run_log.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(LOG_LINES) + "\n")


if __name__ == "__main__":
    main()
