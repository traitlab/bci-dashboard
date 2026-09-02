"""Loading and joining: labels, splits and cached predictions into one ``Health``.

Deterministic, no network. Reads the three inputs, reconciles every label name
against the prediction vocabulary (optionally through a WCVP crosswalk), and
builds the per-frame records and per-species aggregates every page counts from.

The vocabulary this works in, the paths, the thresholds and the name rules, is
in ``core.py``. Nothing here decides what a number means; it decides which rows
there are to measure.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace

from core import (
    CACHE_DIR,
    GT_CSV,
    GT_KEY_PREFIX,
    MIN_CROP_COVERAGE,
    N_CANDIDATES,
    SPLITS_CSV,
    WCVP_CACHE_JSON,
    bucket_label,
    coverage_split,
    genus_of,
    is_species_level,
    load_cache_entry,
    load_wcvp_crosswalk,
    normalize,
    read_csv_rows,
)

@dataclass
class Health:
    gt_rows: list
    split_rows: list
    split_of: dict
    predictions: dict
    maxk: int
    joined: list
    missing_cache: list
    crosswalk: dict
    corpus_norm: set
    corpus_canon: set
    gt_names: Counter
    tier_of_name: dict
    tier_crowns: Counter
    records: list
    sp_recs: list
    genus_recs: list
    per_species: list
    canon: Callable[[str], str]


def scan_cache(cache_dir):
    """Every cached Pl@ntNet response, read once.

    Returns the ranked list per photo stem, plus counts for the run log:
    parse status, list-length histogram, and two invariants pages assume,
    score fields match and lists descend.
    """
    files = sorted(f for f in os.listdir(cache_dir) if f.endswith(".json"))
    # SystemExit for the same reason load_health uses it below: every count
    # here is over the files found, so with none `maxk` has no largest list and
    # max() raises a bare ValueError four call sites from the empty directory.
    if not files:
        raise SystemExit(
            f"No cached Pl@ntNet answers in\n  {cache_dir}\nThe directory exists "
            f"but holds no .json file. Run bin/refresh.sh to fetch them, or point "
            f"at an existing copy with the flags --help lists.")
    predictions, status_count, length_hist = {}, Counter(), Counter()
    corpus_vocab = Counter()
    n_entries = n_cov_ne_score = n_unsorted = 0

    for fn in files:
        sp, status = load_cache_entry(os.path.join(cache_dir, fn))
        status_count[status] += 1
        ranked = []
        prev = None
        for e in sp:
            n_entries += 1
            if e.get("coverage") != e.get("max_score"):
                n_cov_ne_score += 1
            s = float(e.get("max_score") or 0.0)
            if prev is not None and s > prev + 1e-12:
                n_unsorted += 1
            prev = s
            b = (e.get("binomial") or "").strip()
            if b:
                ranked.append((b, s))
        predictions[fn[:-5]] = ranked
        length_hist[len(ranked)] += 1
        for b, _ in ranked:
            corpus_vocab[normalize(b)] += 1

    return SimpleNamespace(
        files=files, predictions=predictions, status_count=status_count,
        length_hist=length_hist, corpus_vocab=corpus_vocab, n_entries=n_entries,
        n_cov_ne_score=n_cov_ne_score, n_unsorted=n_unsorted, maxk=max(length_hist))


def reconcile_names(gt_rows, predictions, corpus_vocab, crosswalk):
    """Sort every botanist label into a tier against names the cache
    returned: byte-exact, normalized match, WCVP synonym, genus-only, or
    absent from every list. The last two are the ceiling pages report.
    """
    corpus_norm = set(corpus_vocab)
    corpus_genera = {genus_of(b) for b in corpus_norm if b}
    # raw (un-normalized) predicted binomials, for the byte-exact tier (a)
    corpus_raw = {b for ranked in predictions.values() for b, _ in ranked}

    gt_names = Counter(r["wcvp_canonical_name"] for r in gt_rows)
    tier_of_name, tier_names, tier_crowns = {}, Counter(), Counter()
    applied_synonyms, absent_names, genus_in_corpus_only = [], [], []

    for name, cnt in gt_names.items():
        nn = normalize(name)
        mapped = crosswalk.get(nn)
        if not is_species_level(nn):
            t = "c_gt_label_is_genus_only"
        elif name in corpus_raw:
            t = "a_exact_binomial"
        elif nn in corpus_norm:
            t = "b_normalized"
        elif mapped and mapped in corpus_norm:
            t = "d_wcvp_synonym"
            applied_synonyms.append((name, mapped, cnt))
        elif genus_of(mapped or nn) in corpus_genera:
            t = "c_genus_only_in_corpus"
            genus_in_corpus_only.append((name, mapped, cnt))
        else:
            t = "e_absent_from_corpus"
            absent_names.append((name, mapped, cnt))
        tier_of_name[name] = t
        tier_names[t] += 1
        tier_crowns[t] += cnt

    return SimpleNamespace(
        corpus_norm=corpus_norm, corpus_raw=corpus_raw, gt_names=gt_names,
        tier_of_name=tier_of_name, tier_names=tier_names, tier_crowns=tier_crowns,
        applied_synonyms=applied_synonyms, absent_names=absent_names,
        genus_in_corpus_only=genus_in_corpus_only)


def aggregate_per_species(sp_recs, corpus_norm, corpus_canon):
    """One row per species, commonest first. The keys are the dict below.

    Two of them are not counts. ``in_corpus_vocabulary`` is true when the name
    came back on any BCI photo, not only on this species’ own frames, so a
    row can be 0.0% in the list column and still be in the vocabulary.
    ``support_bucket`` is the labelled-frames band the species falls in.

    ``top5_accuracy`` counts ``core.N_CANDIDATES`` names, the same constant
    ``figures.prepare`` aborts a build against when the cache carries more.
    """
    def top1(r):
        return r["ranked"][0][0]

    by_sp = defaultdict(list)
    for r in sp_recs:
        by_sp[r["gt"]].append(r)

    per_species = []
    for sp, rs in by_sp.items():
        m = len(rs)
        k1 = sum(1 for r in rs if top1(r) == sp)
        k5 = sum(1 for r in rs if sp in [b for b, _ in r["ranked"][:N_CANDIDATES]])
        confs_ok = [r["ranked"][0][1] for r in rs if top1(r) == sp]
        per_species.append({
            "species": sp,
            "gt_raw_labels": "|".join(sorted({r["gt_raw"] for r in rs})),
            "n_labelled_crowns": m,
            "n_correct_top1": k1,
            "top1_accuracy": k1 / m,
            "n_correct_top5": k5,
            "top5_accuracy": k5 / m,
            "mean_top1_confidence": sum(r["ranked"][0][1] for r in rs) / m,
            "mean_top1_confidence_when_correct": (sum(confs_ok) / len(confs_ok)) if confs_ok else None,
            "in_corpus_vocabulary": sp in corpus_norm or sp in corpus_canon,
            "support_bucket": bucket_label(m),
        })
    per_species.sort(key=lambda d: (-d["n_labelled_crowns"], d["species"]))
    return per_species


def load_health(*, gt_csv=GT_CSV, splits_csv=SPLITS_CSV, cache_dir=CACHE_DIR,
                wcvp_cache=WCVP_CACHE_JSON,
                log: Callable[[str], None] | None = None) -> Health:
    def _log(msg: str = "") -> None:
        if log is not None:
            log(msg)

    # SystemExit, not an exception: the three builders and measure.py all call
    # this, and a first run on a fresh clone hits it. One line a reader can act
    # on beats a ten-frame traceback in four places.
    for p, what in ((gt_csv, "the botanist labels"), (splits_csv, "the grading split"),
                    (cache_dir, "the cached Pl@ntNet answers")):
        if not os.path.exists(p):
            raise SystemExit(
                f"Cannot find {what}, which this command reads from\n  {p}\n"
                f"Nothing here is generated by this command. Run bin/refresh.sh to "
                f"fetch and build the inputs, or point at an existing copy with the "
                f"flags --help lists.")
        _log(f"  input ok : {p}")
    _log(f"  wcvp cache: {wcvp_cache if wcvp_cache and os.path.exists(wcvp_cache) else 'ABSENT (tier d disabled)'}")
    _log("")

    # Local, like ``crop_overlap`` below: run_log reads pct and GT_KEY_PREFIX from
    # this module, so importing it at the top would be a cycle.
    import run_log as rl

    # ---------------- 1. the two input CSVs ----------------
    gt_rows = read_csv_rows(gt_csv)
    split_rows = read_csv_rows(splits_csv)
    split_of = {r["global_key"]: r["split"] for r in split_rows}

    rl.log_inputs(_log, gt_rows, split_rows, split_of)

    # ---------------- 2. every cached Pl@ntNet answer ----------------
    scan = scan_cache(cache_dir)
    predictions, maxk = scan.predictions, scan.maxk
    corpus_vocab = scan.corpus_vocab
    rl.log_cache(_log, scan)

    # ---------------- 3. match each label row to its cached answer ----------
    joined, missing_cache = [], []
    for r in gt_rows:
        gk = r["global_key"]
        stem = gk.removeprefix(GT_KEY_PREFIX)
        if stem in predictions:
            joined.append((gk, stem, r["wcvp_canonical_name"]))
        else:
            missing_cache.append(gk)

    rl.log_join(_log, gt_rows, joined, missing_cache, predictions)

    # ---------------- 4. sort each label into a name-matching tier ----------
    crosswalk, wcvp_raw = load_wcvp_crosswalk(wcvp_cache)
    names = reconcile_names(gt_rows, predictions, corpus_vocab, crosswalk)
    corpus_norm, corpus_raw = names.corpus_norm, names.corpus_raw
    gt_names, tier_of_name = names.gt_names, names.tier_of_name
    tier_crowns = names.tier_crowns
    rl.log_reconciliation(_log, names, scan, gt_rows, crosswalk, wcvp_raw)

    # ---------------- 5. one record per frame we can score ----------------
    def canon(name: str) -> str:
        """Normalize + apply the local WCVP crosswalk (tiers a-d)."""
        nn = normalize(name)
        return crosswalk.get(nn, nn)

    # Joined on base_image: GT keys carry GT_KEY_PREFIX and the box CSV does not, so
    # the stem used for the cache join is the join key here too.
    #
    # Imported here because crop_overlap imports ``normalize`` from this module.
    import crop_overlap
    crop_frames, crop_suspect = crop_overlap.build()

    records = []
    for gk, stem, gt_name in joined:
        gt_c = canon(gt_name)
        cov = crop_frames.get(stem)
        records.append({
            "global_key": gk,
            "split": split_of.get(gk, ""),
            "gt_raw": gt_name,
            "gt": gt_c,
            "gt_strict": normalize(gt_name),
            "species_level": is_species_level(gt_c),
            "ranked": [(canon(b), s) for b, s in predictions[stem]],
            "ranked_strict": [(normalize(b), s) for b, s in predictions[stem]],
            # None means no box row at all, so coverage is unknown rather than
            # zero. The dominant name is canonicalised like the GT label.
            "crop_coverage": cov["coverage"] if cov else None,
            "crop_dominant": (canon(cov["dominant"])
                              if cov and cov["dominant"] else None),
        })

    sp_recs = [r for r in records if r["species_level"] and r["ranked"]]
    genus_recs = [r for r in records if not r["species_level"] and r["ranked"]]

    n_crop_joined = sum(1 for r in records if r["crop_coverage"] is not None)
    crop_admitted, crop_rejected = coverage_split(sp_recs, MIN_CROP_COVERAGE)
    rl.log_crop_gate(_log, records, sp_recs, crop_frames, crop_suspect,
                   n_crop_joined, crop_admitted, crop_rejected, MIN_CROP_COVERAGE)

    # ---------------- 6. one row per species ----------------
    corpus_canon = {canon(b) for b in corpus_raw}
    per_species = aggregate_per_species(sp_recs, corpus_norm, corpus_canon)

    return Health(
        gt_rows=gt_rows, split_rows=split_rows, split_of=split_of, predictions=predictions,
        maxk=maxk, joined=joined, missing_cache=missing_cache, crosswalk=crosswalk,
        corpus_norm=corpus_norm, corpus_canon=corpus_canon, gt_names=gt_names,
        tier_of_name=tier_of_name, tier_crowns=tier_crowns, records=records,
        sp_recs=sp_recs, genus_recs=genus_recs, per_species=per_species, canon=canon,
    )
