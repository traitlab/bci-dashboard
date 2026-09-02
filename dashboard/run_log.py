"""Every line measure.py writes into run_log.txt, and nothing else.

These blocks are the provenance record: which Pl@ntNet endpoint filled the
cache, which names could never be scored right and why, what the crop-coverage
sweep saw. A page quotes two numbers from here; the rest is for whoever has to
answer "where did this come from" a year from now.

They print and return nothing. ``health.load_health`` calls them only when a
caller passes it a ``log``, which only measure.py does, so the three page
builders never reach this file.
"""

from __future__ import annotations

from collections import Counter

from core import GT_KEY_PREFIX, pct


def log_cache(_log, s):
    """Run-log block on the cache. Text only; every number is in ``s``."""
    _log("--- CACHED PREDICTIONS: PROVENANCE ---")
    _log("  Read from predict/ingest_photos.py + config.yaml")
    _log("  + bin/sbatch_ingest.sh (the run that filled this cache):")
    _log("    endpoint : https://my-api.plantnet.org/v2/identify/k-central-america")
    _log("               -> the CENTRAL AMERICA regional model, NOT the global Pl@ntNet model.")
    _log("               The sbatch job passes no --survey-endpoint, so the 2-call")
    _log("               identify+embeddings fallback ran, not /v2/survey/.")
    _log("    model    : config.yaml single_model_run_name 'v7.4-2026-03-27'")
    _log("    params   : nb-results=5, no-reject=true, organs=auto, include-related-images=false")
    _log("    input    : 1280 px CENTRE CROP of each crown photo (CROP_SIZE=1280), not the full frame")
    _log("    'coverage'/'max_score' in the cached JSON are BOTH the identify confidence")
    _log("    score, copied twice by identify_to_survey_json(); there is no real coverage")
    _log("    signal here. Pl@ntNet identify scores are normalised across returned results.")
    _log("    No client-side score threshold is applied, so a list shorter than 5 came back")
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
    _log("  => 'top-5' IS the full returned list. The cap is the client-side request")
    _log("     parameter nb-results=5 (config.yaml plantnet.identify_nb_results), not a")
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
    """Run-log block on name matching, including the ceiling line pages
    quote. Text only; every number is in ``n``."""
    _log("--- NAME RECONCILIATION ---")
    _log("  GT column is called 'wcvp_canonical_name' but IS NOT WCVP-resolved: it is a")
    _log("  string-strip of the Labelbox field label (see labelling/")
    _log("  gt_from_export.py). Hence trailing collection codes ('-QUARAS')")
    _log("  and pre-revision synonyms ('Arrabidaea candicans') survive in it.")
    _log("")
    _log("  'corpus vocabulary' = every distinct binomial appearing anywhere in the")
    _log(f"  {len(scan.files)} cached top-{scan.maxk} lists ({len(scan.corpus_vocab)} names). It is NOT Pl@ntNet's full")
    _log("  label set: a species the model knows but never ranked top-5 on any BCI photo")
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
    """Run-log block on the two input CSVs, including the line pages
    repeat: the labelled subset is a record, not a random draw."""
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
    """Run-log block on matching a label row to its cached answer,
    including every label with none."""
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
    """Run-log block on the crop-coverage gate. Pages report it as a
    diagnostic sweep, never a filter behind a headline."""
    _log("--- CROP COVERAGE GATE ---")
    _log("  Predictions were made from a fixed centre crop of each frame; ground truth")
    _log("  boxes are drawn anywhere in the frame. A frame is admitted only when its")
    _log("  dominant labelled species covers at least the threshold share of that crop.")
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
