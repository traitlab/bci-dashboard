"""Every line measure.py writes into run_log.txt, and nothing else.

These blocks are the provenance record: which Pl@ntNet endpoint filled the
cache, which names could never be scored right and why, what the crop-coverage
sweep saw. A page quotes two numbers from here.

They print and return nothing, and compute nothing a CSV also reports: every
number arrives as an argument. Only measure.py calls them, so no page builder
reaches this file.
"""

from __future__ import annotations

import os
from collections import Counter

from core import (
    BUCKET_ORDER,
    CONF_BINS,
    CONF_THRESHOLDS,
    GT_KEY_PREFIX,
    IDENTIFY_URL,
    MIN_CROP_COVERAGE,
    N_CANDIDATES,
    RELIABLE_MIN_TOP1,
    REVIEW_CONF,
    WELL_SAMPLED_MIN_N,
    flora_name,
    pct,
)
from crop_overlap import CROP_SIZE
from queues import BATCH_SIZE, QUEUE_ORDER

# The rule that opens and closes a block of run_log.txt. measure.py writes the
# file's banner at this width too, or the log comes out ragged.
RULE = "=" * 84


def log_cache(_log, s):
    """Run-log block on the cache. Text only; every number is in ``s``."""
    _log("--- CACHED PREDICTIONS: PROVENANCE ---")
    _log("  Read from predict/ingest_photos.py + config.yaml")
    _log("  + bin/sbatch_ingest.sh (the run that filled this cache):")
    # Both lines derive from config.yaml. history.model_tag_of regexes the flora
    # back out of the first one, so a literal here is how the page comes to name
    # a flora nothing was predicted through.
    _log(f"    endpoint : {IDENTIFY_URL}")
    _log(f"               -> the {flora_name().upper()} model, "
         f"NOT the global Pl@ntNet model.")
    _log("               The sbatch job passes no --survey-endpoint, so the 2-call")
    _log("               identify+embeddings fallback ran, not /v2/survey/.")
    _log("    model    : the endpoint reports '2026-03-20 (7.5)'.")
    _log("               config.yaml's single_model_run_name says 'v7.4-2026-03-27',")
    _log("               a later date on an earlier version: that string dates the")
    _log("               fetch run, not the model, so it is not the model identity.")
    _log("               Checked 2026-09-03 by re-asking the live endpoint for 28")
    _log("               cached frames: identical species sets, scores equal to")
    _log("               within 1e-5. The cache is this model, not an older one.")
    _log(f"    params   : nb-results={N_CANDIDATES}, no-reject=true, organs=auto, "
         f"include-related-images=false")
    _log(f"    input    : {CROP_SIZE} px CENTRE CROP of each crown photo "
         f"(CROP_SIZE={CROP_SIZE}), not the full frame")
    _log("    'coverage'/'max_score' in the cached JSON are BOTH the identify confidence")
    _log("    score, copied twice by identify_to_survey_json(); there is no real coverage")
    _log("    signal here. Pl@ntNet identify scores are normalised across returned results.")
    _log(f"    No client-side score threshold is applied, so a list shorter than "
         f"{N_CANDIDATES} came back")
    _log("    short from the API itself.")
    _log("")
    _log("--- CACHED PREDICTIONS: PARSE ---")
    _log(f"cache .json files                     : {len(s.files)}")
    for k in ("ok", "salvaged", "unreadable"):
        _log(f"  parsed {k:<30}: {s.status_count.get(k, 0)}")
    _log("  ('salvaged' = payload truncated inside per_tiles_embeddings; the ranked")
    _log("   species array precedes it and was recovered by bracket-matching.)")
    _log("  prediction-list length histogram    : " +
         ", ".join(f"len={k}:{v}" for k, v in sorted(s.length_hist.items())))
    _log(f"  MAX list length observed            : {s.maxk}")
    _log(f"  => 'top-{N_CANDIDATES}' IS the full returned list. The cap is the client-side request")
    _log(f"     parameter nb-results={N_CANDIDATES} (config.yaml plantnet.identify_nb_results), not a")
    _log("     model limit: a re-ingest with a larger nb-results would return more. No")
    _log("     deeper candidate exists in this cache and none can be recovered offline.")
    _log(f"  total candidate entries             : {s.n_entries}")
    _log(f"  entries where coverage != max_score : {s.n_cov_ne_score}  "
         f"(0 confirms both fields hold the same identify score)")
    _log(f"  entries breaking descending order   : {s.n_unsorted}  "
         f"(0 confirms the list is ranked; index 0 is top-1)")
    _log(f"  distinct predicted binomials        : {len(s.corpus_vocab)}")
    _log("")


def log_reconciliation(_log, n, scan, gt_rows, crosswalk, wcvp_raw):
    """Run-log block on name matching, including the ceiling line pages quote."""
    _log("--- NAME RECONCILIATION ---")
    _log("  GT column is called 'wcvp_canonical_name' but IS NOT WCVP-resolved: it is a")
    _log("  string-strip of the Labelbox field label (see labelling/")
    _log("  gt_from_export.py). Hence trailing collection codes ('-QUARAS')")
    _log("  and pre-revision synonyms ('Arrabidaea candicans') survive in it.")
    _log("")
    _log("  'corpus vocabulary' = every distinct binomial appearing anywhere in the")
    _log(f"  {len(scan.files)} cached top-{scan.maxk} lists ({len(scan.corpus_vocab)} names). It is NOT Pl@ntNet's full")
    _log(f"  label set: a species the model knows but never ranked top-{N_CANDIDATES} on any BCI photo")
    _log("  is indistinguishable here from a species the model does not know at all.")
    _log("")
    _log(f"  {'tier':<28} {'distinct GT names':>18} {'GT crowns':>10}")
    for t in ("a_exact_binomial", "b_normalized", "d_wcvp_synonym",
              "c_gt_label_is_genus_only", "c_genus_only_in_corpus", "e_absent_from_corpus"):
        _log(f"  {t:<28} {n.tier_names.get(t, 0):>18} {n.tier_crowns.get(t, 0):>10}")
    _log(f"  crosswalk entries loaded            : {len(crosswalk)} name changes from "
         f"{len(wcvp_raw)} WCVP cache records")
    _log("")
    _log("  (d) WCVP synonym mappings actually APPLIED (audit these):")
    for name, mapped, cnt in sorted(n.applied_synonyms, key=lambda x: -x[2]):
        _log(f"      {cnt:>4} crowns  {name}  ->  {mapped}")
    _log("")
    _log("  CEILING ON ACHIEVABLE SPECIES-LEVEL ACCURACY")
    ceil_names = n.tier_names["e_absent_from_corpus"] + n.tier_names["c_genus_only_in_corpus"]
    ceil_crowns = n.tier_crowns["e_absent_from_corpus"] + n.tier_crowns["c_genus_only_in_corpus"]
    _log(f"      {ceil_crowns} GT crowns across {ceil_names} species can NEVER be scored correct from")
    _log("      this cache: after normalization and WCVP synonym resolution their name")
    _log(f"      still appears in no cached prediction list. ({ceil_crowns} is out of all {len(gt_rows)} GT")
    _log("      rows; the subset falling inside the primary evaluation set is reported")
    _log("      under HEADLINE as the 'restricted to reachable crowns' line.)")
    _log("")
    _log("  GT species whose genus IS in the corpus but the exact epithet is not:")
    for name, mapped, cnt in sorted(n.genus_in_corpus_only, key=lambda x: -x[2]):
        _log(f"      {cnt:>4} crowns  {name}" + (f"  (wcvp-> {mapped})" if mapped else ""))
    _log("")
    _log("  GT species absent from the corpus entirely (genus not seen either):")
    for name, mapped, cnt in sorted(n.absent_names, key=lambda x: -x[2]):
        _log(f"      {cnt:>4} crowns  {name}" + (f"  (wcvp-> {mapped})" if mapped else ""))
    _log("")
    _log(f"  GT labels the botanist left at genus level: {n.tier_names['c_gt_label_is_genus_only']} genera, "
         f"{n.tier_crowns['c_gt_label_is_genus_only']} crowns.")
    _log("      EXCLUDED from the species-level headline; scored separately at genus level.")
    _log("")


def log_inputs(_log, gt_rows, split_rows, split_of):
    """Run-log block on the two input CSVs: the labelled subset is a record."""
    _log("--- INPUTS ---")
    _log(f"gt_dominant_taxon.csv rows            : {len(gt_rows)}")
    _log(f"  distinct global_key                 : {len(set(r['global_key'] for r in gt_rows))}")
    _log(f"  distinct wcvp_canonical_name        : {len(set(r['wcvp_canonical_name'] for r in gt_rows))}")
    _log(f"splits.csv rows                       : {len(split_rows)}")
    sc = Counter(r["split"] for r in split_rows)
    for k in sorted(sc, key=lambda x: (-sc[x], x)):
        _log(f"  split '{k}'{'':<{max(0, 16 - len(k))}}: {sc[k]}")
    gt_split = Counter(split_of.get(r["global_key"], "<not in splits>") for r in gt_rows)
    _log("  split values among GT crowns        : " +
         ", ".join(f"{k or '<empty>'}={v}" for k, v in sorted(gt_split.items())))
    _log(f"  GT coverage of the photo corpus     : {len(gt_rows)} / {len(split_rows)} "
         f"= {pct(len(gt_rows), len(split_rows))} of photos carry a GT label.")
    _log("  That labelled subset is the historical botanist labelling record, not a")
    _log("  random draw, so per-species rates transfer to the unlabelled remainder only")
    _log("  under an assumption that cannot be tested offline.")
    _log("  NOTE: all evaluation below pools train+valid+test. The cached predictions")
    _log("  come from a frozen third-party API that never saw these splits, so there is")
    _log("  no train/test leakage to control for; splits are reported for traceability only.")
    _log("")


def log_join(_log, gt_rows, joined, missing_cache, predictions):
    """Run-log block on matching a label row to its cached answer."""
    _log("--- JOIN (global_key -> cache file) ---")
    _log(f"  convention                          : GT '{GT_KEY_PREFIX}<stem>.JPG'  ->  cache '<stem>.JPG.json'")
    _log(f"  byte-exact key join                 : 0 / {len(gt_rows)}   (GT keys carry the '{GT_KEY_PREFIX}' prefix; cache names do not)")
    _log(f"  after stripping '{GT_KEY_PREFIX}'            : {len(joined)} / {len(gt_rows)}   ({pct(len(joined), len(gt_rows))})")
    _log(f"  GT crowns with no cached response   : {len(missing_cache)}")
    for gk in sorted(missing_cache):
        _log(f"      {gk}")
    _log(f"  joined but empty prediction list    : {sum(1 for _, s, _ in joined if not predictions[s])}")
    _log("")


def log_crop_gate(_log, records, sp_recs, crop_frames, crop_suspect,
                   n_crop_joined, crop_admitted, crop_rejected, min_coverage):
    """Run-log block on the crop-coverage gate, a sweep and never a filter."""
    _log("--- CROP COVERAGE GATE ---")
    _log("  Predictions were made from a fixed centre crop of each frame; ground truth")
    _log("  boxes are drawn anywhere in the frame. A frame is admitted only when the")
    _log("  species it is labelled with is the one filling the crop, and fills at least")
    _log("  the threshold share of it.")
    _log(f"  box geometry available for          : {len(crop_frames)} base frames "
         f"({len(crop_suspect)} frames not trusted and excluded)")
    _log(f"  joined to a GT record               : {n_crop_joined} / {len(records)} "
         f"({pct(n_crop_joined, len(records))})")
    n_sp_cov = sum(1 for r in sp_recs if r["crop_coverage"] is not None)
    _log(f"  joined within the primary set       : {n_sp_cov} / {len(sp_recs)} "
         f"({pct(n_sp_cov, len(sp_recs))})")
    _log(f"  admitted at coverage >= {min_coverage:.2f}        : {len(crop_admitted)} "
         f"(rejected {len(crop_rejected)}, of which "
         f"{len(sp_recs) - n_sp_cov} for unknown geometry)")
    _log("")


def log_evaluable_sets(_log, h):
    """Which frames the headline is computed over, and which were set aside."""
    _log("--- EVALUABLE SETS ---")
    _log(f"  GT frames joined to a cache file    : {len(h.records)}")
    _log(f"  ... with >=1 prediction             : {sum(1 for r in h.records if r['ranked'])}")
    _log(f"  species-level GT + >=1 prediction   : {len(h.sp_recs)}   <-- PRIMARY EVALUATION SET")
    _log(f"  genus-only GT + >=1 prediction      : {len(h.genus_recs)}   (scored separately, genus level)")
    short = sum(1 for r in h.sp_recs if len(r["ranked"]) < N_CANDIDATES)
    _log(f"  primary set with <{N_CANDIDATES} candidates      : {short} ({pct(short, len(h.sp_recs))})")
    _log("")


def _macro(x, width: int) -> str:
    """A macro average as a right-aligned percentage, or ``n/a``.

    Both producers report absent over an empty population: ``headline_counts``
    when no species is scored, ``core.coverage_gate_stats`` when the gate admits
    nothing. Column width is passed in so the "n/a" lands under the same heading
    the number would have, the trailing "%" included.
    """
    return f"{'n/a':>{width + 1}}" if x is None else f"{x * 100:>{width}.2f}%"


def log_headline(_log, n, n_sp, c1, c5, macro1, macro5, g1, g5, reachable, r1, r5, s1, s5, gn, gg1, gg5):
    """The headline block: every rate, each with the frames it was measured on."""
    _log(RULE)
    _log(f"HEADLINE  (species-level GT, joined, >=1 cached prediction: n={n} frames, {n_sp} species)")
    _log(RULE)
    _log(f"  top-1 accuracy                      : {pct(c1, n)}   ({c1}/{n})")
    _log(f"  top-{N_CANDIDATES} accuracy  (= full list)       : {pct(c5, n)}   ({c5}/{n})")
    _log(f"  macro-avg per-species recall @1     : {_macro(macro1, 0)}   (unweighted over {n_sp} species)")
    _log(f"  macro-avg per-species recall @{N_CANDIDATES}     : {_macro(macro5, 0)}")
    _log(f"  genus-level top-1                   : {pct(g1, n)}   ({g1}/{n})")
    _log(f"  genus-level top-{N_CANDIDATES}                   : {pct(g5, n)}   ({g5}/{n})")
    _log("")
    _log("  restricted to frames whose GT species appears somewhere in the corpus at all")
    _log(f"  (n={len(reachable)}; excludes the {n - len(reachable)} frames that are unscoreable by construction):")
    _log(f"    top-1                             : {pct(r1, len(reachable))}   ({r1}/{len(reachable)})")
    _log(f"    top-{N_CANDIDATES}                             : {pct(r5, len(reachable))}   ({r5}/{len(reachable)})")
    _log("")
    _log("  sensitivity to name reconciliation (same frames, no WCVP synonym tier):")
    _log(f"    strict top-1                      : {pct(s1, n)}   ({s1}/{n})   [{100.0 * (c1 - s1) / n:+.2f} pp from tier d]")
    _log(f"    strict top-{N_CANDIDATES}                      : {pct(s5, n)}   ({s5}/{n})   [{100.0 * (c5 - s5) / n:+.2f} pp from tier d]")
    _log("")
    _log(f"  genus-only GT frames (n={gn}), scored at genus level:")
    _log(f"    genus top-1                       : {pct(gg1, gn)}   ({gg1}/{gn})")
    _log(f"    genus top-{N_CANDIDATES}                       : {pct(gg5, gn)}   ({gg5}/{gn})")
    _log("")


def log_checklist_scope(_log, scope, n, c1, n_sp, macro1):
    """Which species are proven out of scope, and the headline recomputed
    without their frames. The published numbers above this block do not move;
    this is a second, adjusted view sitting next to them, not a replacement.
    """
    _log("--- CHECKLIST SCOPE (predict/fetch_checklist.py) ---")
    ck = scope.checklist
    if ck is None:
        _log("  no checklist on disk. Run predict/fetch_checklist.py to download")
        _log("  core.EVAL_PROJECT's species list before this block can say more than")
        _log("  that: every species still carries in_project_checklist=None, and")
        _log("  'unreachable' is the most specific status diagnose() can give it.")
        _log("")
        return
    _log(f"  checklist read                      : data/checklist_{ck.project}.json")
    _log(f"  project                              : {ck.project}")
    _log(f"  species on the list                  : {ck.n_returned}")
    mismatch = "" if ck.declared_species_count == ck.n_returned else "  MISMATCH"
    _log(f"  declared species count               : {ck.declared_species_count}{mismatch}")
    _log("")
    _log(f"  out-of-scope species (proven absent from the checklist) : {len(scope.out)}")
    _log(f"  out-of-scope frames                                     : {scope.frames}")
    for d in scope.out:
        _log(f"      {d['n_labelled_frames']:>4} frames  {d['species']}")
    _log("")
    _log("  published headline (above) does not change. Side by side with the")
    _log("  out-of-scope frames and species removed:")
    _log(f"  {'':<28} {'published':>12} {'out-of-scope removed':>22}")
    _log(f"  {'frames (N)':<28} {n:>12} {scope.n_adj:>22}")
    _log(f"  {'frame top-1':<28} {pct(c1, n):>12} {pct(scope.c1_adj, scope.n_adj):>22}")
    _log(f"  {'species (N)':<28} {n_sp:>12} {scope.n_sp_adj:>22}")
    _log(f"  {'macro per-species top-1':<28} {_macro(macro1, 11)} "
        f"{_macro(scope.macro1_adj, 21)}")
    _log("")


def log_gate_comparison(_log, sp_recs, sweep, gate, n, n_sp, c1, macro1):
    """Gated and ungated side by side, then the sweep behind the threshold."""
    _log("--- CROP-COVERAGE GATE: GATED AND UNGATED, SIDE BY SIDE ---")
    _log("  Ungated scores every evaluated frame. Gated scores only the frames whose")
    _log("  own label fills at least the threshold share of the centre crop the model was")
    _log("  actually sent, so the label was inside the model's view.")
    _log("  The two are different populations. Neither replaces the other.")
    _log(f"  {'quantity':<34} {'ungated':>12} {'gated':>12}")
    _log(f"  {'frames (N)':<34} {n:>12} {gate['n_admitted']:>12}")
    _log(f"  {'frame top-1':<34} {pct(c1, n):>12} {pct(gate['n_correct_top1'], gate['n_admitted']):>12}"
        f"   (N_admitted={gate['n_admitted']})")
    _log(f"  {'macro per-species top-1':<34} {_macro(macro1, 11)} "
        f"{_macro(gate['macro_top1'], 11)}   (N_admitted={gate['n_admitted']}, "
        f"{gate['n_species']} species)")
    _log(f"  {'species':<34} {n_sp:>12} {gate['n_species']:>12}")
    _log(f"  threshold in force                  : {MIN_CROP_COVERAGE:.2f} "
        f"(core.MIN_CROP_COVERAGE)")
    _log(f"  {'min_coverage':>12} {'N_admitted':>12} {'frame top-1':>13} "
        f"{'macro top-1':>13} {'species':>9}")
    for g in sweep:
        _log(f"  {g['min_coverage']:>12.2f} {g['n_admitted']:>12} "
            f"{pct(g['n_correct_top1'], g['n_admitted']):>13} "
            f"{_macro(g['macro_top1'], 12)} {g['n_species']:>9}")
    n_unknown = sum(1 for r in sp_recs if r["crop_coverage"] is None)
    _log(f"  frames with no box geometry, rejected at every threshold : {n_unknown} "
        f"({pct(n_unknown, n)})")
    # Three unrelated reasons shrink the gated N and only one is the gate
    # measuring the label, so neither of the other two can read as evidence
    # about how much of the crop the labelled species fills.
    n_other = sum(1 for r in sp_recs
                  if r["crop_coverage"] is not None
                  and r["crop_dominant"] is not None
                  and r["crop_dominant"] != r["gt"])
    n_low = n - n_unknown - n_other - gate["n_admitted"]
    _log(f"  so the {n - gate['n_admitted']} frames not admitted are {n_unknown} with no box "
        f"geometry to measure,")
    _log(f"  {n_other} whose crop is filled by a species other than the frame's label,")
    _log(f"  and {n_low} where the label fills the crop but stays below the "
        f"{MIN_CROP_COVERAGE:.2f} threshold.")
    _log("  The middle group is measured, but what was measured is another tree, so it")
    _log("  says nothing about whether the label was inside what the model saw.")
    _log("")


def log_support_buckets(_log, B):
    """Accuracy by how many labelled frames a species has."""
    _log("--- SUPPORT BUCKETS (species-level GT) ---")
    _log(f"  {'bucket':<8} {'species':>8} {'frames':>8} {'top-1':>9} {f'top-{N_CANDIDATES}':>9}")
    for lab in BUCKET_ORDER:
        b = B[lab]
        if not b["n_crowns"]:
            continue
        _log(f"  {lab:<8} {b['n_species']:>8} {b['n_crowns']:>8} "
            f"{pct(b['c1'], b['n_crowns']):>9} {pct(b['c5'], b['n_crowns']):>9}")
    _log("")


def log_filter_gain(_log, B, bci_list, n, c1, f1, f_abstain, still_wrong, maxk, sw_full, sw_short, sw_full_unreachable):
    """What restricting candidates to the BCI list is worth, and why it is a lower bound."""
    _log(f"--- BCI SPECIES-LIST FILTER (proxy list = {len(bci_list)} distinct GT species) ---")
    _log(f"  top-1 before filter                 : {pct(c1, n)}   ({c1}/{n})")
    _log(f"  top-1 after  filter                 : {pct(f1, n)}   ({f1}/{n})")
    _log(f"  delta                               : {100.0 * (f1 - c1) / n:+.2f} pp")
    _log(f"  frames with no surviving candidate  : {f_abstain} ({pct(f_abstain, n)})")
    _log(f"  {'bucket':<8} {'frames':>8} {'before':>9} {'after':>9} {'delta':>10} {'no-cand':>8}")
    for lab in BUCKET_ORDER:
        b = B[lab]
        if not b["n_crowns"]:
            continue
        _log(f"  {lab:<8} {b['n_crowns']:>8} {pct(b['c1'], b['n_crowns']):>9} "
            f"{pct(b['f1'], b['n_crowns']):>9} "
            f"{100.0 * (b['f1'] - b['c1']) / b['n_crowns']:>+9.2f}p {b['fab']:>8}")
    _log("")
    _log("  THIS DELTA IS A LOWER BOUND. Re-ranking can only promote a species already")
    _log(f"  present in the returned list, and the list was capped at nb-results={N_CANDIDATES}.")
    _log(f"    frames still wrong after filtering  : {len(still_wrong)}")
    _log(f"      ... whose list was full (len={maxk})     : {sw_full}  <- cap could be binding;")
    _log(f"            a correct candidate may exist at rank {N_CANDIDATES + 1}+ and was never returned")
    _log(f"      ... whose list was short (len<{maxk})    : {sw_short}  <- cap NOT binding; the API")
    _log("            returned everything it had, so no re-ranking could have helped")
    _log(f"      ... full list AND GT name absent from the whole corpus : {sw_full_unreachable}")
    _log("  Sizing the real gain requires a re-ingest with a larger nb-results, or the")
    _log("  actual curated Pl@ntNet BCI micro-project. It cannot be estimated offline.")
    _log("")
    _log("  The proxy list is also OPTIMISTIC in the opposite direction: it is built from")
    _log("  the GT labels themselves, so by construction it contains every species that")
    _log("  can be correct and no distractor the real curated list might carry.")
    _log("")


def log_calibration(_log, scopes, top1, n, good, good_recs):
    """Accuracy by confidence band and threshold, per scope."""
    _log("--- CONFIDENCE CALIBRATION / TRIAGE FEASIBILITY ---")
    _log(f"  third scope = the {len(good)} species the proposed rule would whitelist "
        f"(n>={WELL_SAMPLED_MIN_N} labelled frames AND")
    _log(f"  measured top-1 >= {RELIABLE_MIN_TOP1:.0%}), covering {len(good_recs)} of the {n} primary "
        f"frames ({pct(len(good_recs), n)}).")
    _log("  Its accuracy is OPTIMISTIC: the whitelist is selected on the very frames it is")
    _log("  then scored on. Treat it as an upper bound until validated on held-out frames.")
    _log("")
    for scope, rs in scopes:
        _log(f"  scope: {scope}   (n={len(rs)})")
        _log(f"    {'conf band':<12} {'n':>7} {'top-1 acc':>11}")
        for lo, hi in CONF_BINS:
            sub = [r for r in rs if lo <= r["ranked"][0][1] < hi]
            k = sum(1 for r in sub if top1(r) == r["gt"])
            _log(f"    {f'[{lo:.1f},{min(hi, 1.0):.1f})':<12} {len(sub):>7} {pct(k, len(sub)):>11}")
        _log(f"    {'threshold':<12} {'n auto':>7} {'% of scope':>11} {'error rate':>11}")
        for t in CONF_THRESHOLDS:
            sub = [r for r in rs if r["ranked"][0][1] >= t]
            k = sum(1 for r in sub if top1(r) == r["gt"])
            _log(f"    {'>=' + str(t):<12} {len(sub):>7} {pct(len(sub), len(rs)):>11} "
                f"{pct(len(sub) - k, len(sub)):>11}")
        _log("")


def log_send_queue(_log, q_counts, batch_rows, n_no_answer, n_ranked=0,
                   novelty=None, held_out=None):
    """The unlabelled pool, by queue, and how it was batched.

    ``novelty`` is what ``queues.novelty_provenance`` read off the sidecar
    beside the ordering file: when the ranking was last rebuilt, how many
    labelled frames anchored it, how many photos it ranked. It is printed
    because ``labelling/rank_queue.py`` is not in ``bin/refresh.sh`` and needs a
    virtualenv this one is not: the ordering file can therefore be months older
    than every other number in this log, and nothing else here would say so.

    ``held_out`` is the split-tagged frames the queue refused, by split. Printed
    even at zero, like every other exclusion in this file: a queue that quietly
    shrank is the one nobody can account for later.
    """
    n_unlab = sum(q_counts.values())
    n_batches = batch_rows[-1][0] if batch_rows else 0
    _log("--- SEND-FIRST QUEUE (cached predictions with no GT label) ---")
    _log(f"  unlabelled frames with a prediction : {n_unlab}")
    for q in QUEUE_ORDER:
        _log(f"    {q:<16}: {q_counts[q]}")
    # Printed even at zero: the ordering inside a queue falls back to confidence
    # for every frame this number does not cover, and a reader has to know how
    # much of the queue that is.
    _log(f"  frames ordered by how they look     : {n_ranked} of {n_unlab}")
    # Immediately under the count it qualifies. "unknown" is printed rather than
    # skipped: a reader who cannot see the date cannot tell a fresh ranking from
    # one built before the last three batches went out.
    p = novelty or {}
    _log(f"    ordering file written            : {p.get('written') or 'unknown'}")
    _log(f"    labelled frames anchoring it     : {p.get('anchors') or 'unknown'}")
    _log(f"    photos ranked against them       : {p.get('pool') or 'unknown'}")
    _log("    (labelling/rank_queue.py writes these, outside bin/refresh.sh)")
    held = held_out or Counter()
    by_split = ", ".join(f"{k} {held[k]}" for k in sorted(held)) or "none"
    _log(f"  held out, already in an eval split  : {sum(held.values())}  ({by_split})")
    _log("    Sending an evaluation frame back for labelling would put a new")
    _log("    answer into the set the per-species statuses are measured on.")
    _log(f"  send_batches.csv                    : {len(batch_rows)} rows in {n_batches} "
        f"batches, max {BATCH_SIZE}/batch, species groups packed whole")
    _log(f"  unlabelled frames with NO answer    : {n_no_answer}  (empty candidate list;")
    _log("    possible junk or non-plant photos; check a sample")
    _log("    by eye before queueing, no automatic rule)")
    _log("")


def log_review_queue(_log, review_rows, n, n_adjudicated):
    """Confident disagreements between the model and a label."""
    pairs = Counter((r[2], r[3]) for r in review_rows)
    _log("--- LABELS WORTH A SECOND LOOK ---")
    _log(f"  first guess wrong at confidence >= {REVIEW_CONF} : {len(review_rows)} "
        f"of {n} evaluated frames ({pct(len(review_rows), n)})")
    _log(f"  distinct species-to-species confusions  : {len(pairs)}")
    # Printed even at zero: a queue that silently shrank is worse than a long one.
    _log(f"  suppressed, botanist confirmed the label : {n_adjudicated}")
    _log("")


def log_files_written(_log, out_dir, outputs):
    """Where the run put everything, in the order OUTPUTS names them."""
    _log("--- FILES WRITTEN ---")
    for fn in outputs:
        _log(f"  {os.path.join(out_dir, fn)}")
