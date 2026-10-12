"""Loading and joining: labels, splits and cached predictions into one ``Health``.

Deterministic. Reads the three inputs, reconciles every label name
against the prediction vocabulary (optionally through a WCVP crosswalk), and
builds the per-frame records and per-species aggregates every page counts from.

Paths, thresholds and name rules live in ``core.py``. Nothing here decides what
a number means; it decides which rows there are to measure.
"""

from __future__ import annotations

import os
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace

import reference
import run_log as rl
from checklist import load_checklist, membership
from core import (
    CACHE_DIR,
    EVAL_PROJECT,
    GT_CSV,
    GT_KEY_PREFIX,
    HOLDOUT_CSV,
    HOLDOUT_HELD_ROLE,
    HOLDOUT_SPLIT,
    LABEL_SOURCE_ALL,
    LABEL_SOURCE_COLUMN,
    LABEL_SOURCE_REVIEWED,
    LABELBOX_NAME_COLUMN,
    MIN_CROP_COVERAGE,
    N_CANDIDATES,
    SPLITS_CSV,
    WCVP_CACHE_JSON,
    bucket_label,
    canonicaliser,
    coverage_split,
    entry_project,
    entry_project_source,
    entry_species,
    genus_of,
    is_species_level,
    load_wcvp_crosswalk,
    normalize,
    read_cache_json,
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
    checklist: object | None
    # Every frame with any label, whichever population is scored: the send
    # queue holds all of them back, so an unreviewed label is never re-sent.
    labelled_stems: set
    # label_source -> the species-level scored records of that population,
    # the headline's included. Empty for a GT without the column.
    by_source: dict
    # What the headline is scored against, a ``reference`` constant.
    reference: str


def scan_cache(cache_dir):
    """Every cached Pl@ntNet response, read once.

    Returns the ranked list per photo stem, plus run-log counts: parse status,
    list-length histogram, the two invariants pages assume, score fields match
    and lists descend, and which Pl@ntNet project each answer records.

    The project counts are here rather than in a separate pass because this is
    the only walk of the directory. An answer whose project is not the one
    config.yaml names today was fetched through a different flora, and every
    per-species number pools it with the rest. That is the one failure mode a
    flora switch introduces and the only place it can be seen.
    """
    files = sorted(f for f in os.listdir(cache_dir) if f.endswith(".json"))
    # SystemExit like require_inputs below: with no files `maxk` has no largest
    # list and max() raises a bare ValueError four call sites away.
    if not files:
        raise SystemExit(
            f"No cached Pl@ntNet answers in\n  {cache_dir}\nThe directory exists "
            f"but holds no .json file. Run bin/refresh.sh to fetch them, or point "
            f"at an existing copy with the flags --help lists.")
    predictions, status_count, length_hist = {}, Counter(), Counter()
    corpus_vocab, project_count, project_source_count = Counter(), Counter(), Counter()
    n_entries = n_cov_ne_score = n_unsorted = 0

    for fn in files:
        entry, status = read_cache_json(os.path.join(cache_dir, fn))
        sp = entry_species(entry)
        status_count[status] += 1
        project_count[entry_project(entry)] += 1
        project_source_count[entry_project_source(entry)] += 1
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
        n_cov_ne_score=n_cov_ne_score, n_unsorted=n_unsorted, maxk=max(length_hist),
        project_count=project_count, project_source_count=project_source_count,
        n_no_project=project_count[""],
        n_foreign_project=sum(n for p, n in project_count.items()
                              if p and p != EVAL_PROJECT))


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


def confusion_counts(sp_recs):
    """Per species: right first guesses, frames guessed, frames labelled.

    The three counts precision, recall and F1 are all built from, in one pass.
    Recall's denominator is the frames a species was *labelled* on, which is
    the same denominator the first-guess rate already uses. Precision's is the
    frames it was *guessed* on, and no per-species row holds that: a wrong
    first guess lands in the guessed count of a species whose own row it never
    touches, so it cannot be recovered from the rows afterwards.

    Counted here rather than folded into ``aggregate_per_species``'s own tally,
    so the two arrive at the frames-labelled count by different routes and a
    test can check them against each other instead of watching them agree by
    construction.
    """
    tp, guessed, labelled = Counter(), Counter(), Counter()
    for r in sp_recs:
        guess = r["ranked"][0][0]
        guessed[guess] += 1
        labelled[r["gt"]] += 1
        if guess == r["gt"]:
            tp[guess] += 1
    return tp, guessed, labelled


def f_measure(precision, recall):
    """The harmonic mean of a precision and a recall, and 0.0 when both are 0.

    A species the model never guesses has no right guesses either, so both
    rates are 0 and the harmonic mean is 0/0. Reporting it as 0.0 is the same
    reading every confusion-matrix report gives it: nothing was found, so
    nothing was found well. Written once because per-species F1 and the
    per-species average of it must not be two different formulas.
    """
    total = precision + recall
    return 0.0 if not total else 2 * precision * recall / total


def confidence_spread(values):
    """Mean, median and the middle half of a list of confidences.

    The mean alone hides the shape. Pl@ntNet spreads its score over every
    species it knows, so the distribution is skewed and the median says more
    about a typical frame than the average does. The quartile pair says how
    wide the middle of it is.

    A single value has no spread to report, and a single-frame species is the
    commonest row in the table, so that case returns the value itself rather
    than letting ``statistics.quantiles`` raise on one data point. Empty is
    ``None`` throughout, never 0.0: no frames means no confidence, not a
    confidence of zero.
    """
    if not values:
        return {"mean": None, "median": None, "p25": None, "p75": None, "iqr": None}
    if len(values) == 1:
        only = values[0]
        return {"mean": only, "median": only, "p25": only, "p75": only, "iqr": 0.0}
    q1, _q2, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return {"mean": statistics.fmean(values), "median": statistics.median(values),
            "p25": q1, "p75": q3, "iqr": q3 - q1}


def aggregate_per_species(sp_recs, corpus_norm, corpus_canon, in_checklist=None):
    """One row per species, commonest first. The keys are the dict below.

    Three of them are not counts. ``in_corpus_vocabulary`` is true when the
    name came back on any BCI photo, not only on this species' own frames, so
    a row can be 0.0% in the list column and still be in the vocabulary.
    ``top5_accuracy`` counts ``core.N_CANDIDATES`` names, the constant
    ``figures.prepare`` aborts a build against when the cache carries more.
    ``in_project_checklist`` is ``None`` when ``in_checklist`` is, which is
    when no checklist is on disk (``predict/fetch_checklist.py`` has not been
    run), otherwise True or False against ``core.EVAL_PROJECT``'s own species
    list, the one source that can prove a species absent rather than merely
    never ranked in an ``N_CANDIDATES``-name sample. ``checklist.membership``
    builds the test; it is handed the row's raw labels as well as its
    canonical name because the GBIF key that survives a rename hangs off the
    label, not off the name.

    Three more are the confusion-matrix rates, built from ``confusion_counts``.
    ``recall`` asks how many of a species' own labelled frames the model named
    right, which is the question ``top1_accuracy`` already answers, here under
    the name the metric grid uses. ``precision`` asks the opposite question
    over a different population: of the frames the model *guessed* this species
    on, how many really were it. ``n_guessed_frames`` is that population and
    travels beside the rate, because 100% over one guess and 100% over four
    hundred are not the same claim. A species the model never guesses gets
    ``precision`` 0.0 rather than ``None``, so the per-species average has a
    number to average, and ``n_guessed_frames`` is 0 there to say what the 0.0
    rests on.

    ``f1`` is the harmonic mean of that row's own precision and recall.
    Averaging that column across species is macro F1. The F1 of the two
    averaged rates is a different number, and nothing here computes it.

    The confidence columns are a distribution rather than one figure.
    ``mean_top1_confidence`` is the arithmetic mean it has always been; the
    median and the quartile pair beside it say what a mean hides on a skewed
    score. ``mean_top1_confidence_when_correct`` is the same mean over only the
    frames the first guess got right, so the gap between the two is what being
    confident is worth on this species.
    """
    def top1(r):
        return r["ranked"][0][0]

    by_sp = defaultdict(list)
    for r in sp_recs:
        by_sp[r["gt"]].append(r)

    tp, guessed, _labelled = confusion_counts(sp_recs)

    per_species = []
    for sp, rs in by_sp.items():
        m = len(rs)
        k1 = sum(1 for r in rs if top1(r) == sp)
        k5 = sum(1 for r in rs if sp in [b for b, _ in r["ranked"][:N_CANDIDATES]])
        confs = [r["ranked"][0][1] for r in rs]
        confs_ok = [r["ranked"][0][1] for r in rs if top1(r) == sp]
        spread = confidence_spread(confs)
        n_guessed = guessed[sp]
        precision = (tp[sp] / n_guessed) if n_guessed else 0.0
        recall = tp[sp] / m
        raw_labels = sorted({r["gt_raw"] for r in rs})
        per_species.append({
            "species": sp,
            "gt_raw_labels": "|".join(raw_labels),
            "n_labelled_frames": m,
            "n_correct_top1": k1,
            "top1_accuracy": k1 / m,
            "n_correct_top5": k5,
            "top5_accuracy": k5 / m,
            "n_guessed_frames": n_guessed,
            "precision": precision,
            "recall": recall,
            "f1": f_measure(precision, recall),
            "mean_top1_confidence": sum(confs) / m,
            "median_top1_confidence": spread["median"],
            "p25_top1_confidence": spread["p25"],
            "p75_top1_confidence": spread["p75"],
            "iqr_top1_confidence": spread["iqr"],
            "mean_top1_confidence_when_correct": (sum(confs_ok) / len(confs_ok)) if confs_ok else None,
            "in_corpus_vocabulary": sp in corpus_norm or sp in corpus_canon,
            "in_project_checklist": (None if in_checklist is None
                                      else in_checklist(sp, raw_labels)),
            "support_bucket": bucket_label(m),
        })
    per_species.sort(key=lambda d: (-d["n_labelled_frames"], d["species"]))
    return per_species


def require_inputs(paths_and_names, log):
    """Fail on a missing input with one line a reader can act on.

    SystemExit, not an exception: a first run on a fresh clone hits this from
    any of the four callers, and one line beats a ten-frame traceback.
    """
    for path, what in paths_and_names:
        if not os.path.exists(path):
            raise SystemExit(
                f"Cannot find {what}, which this command reads from\n  {path}\n"
                f"Nothing here is generated by this command. Run bin/refresh.sh to "
                f"fetch and build the inputs, or point at an existing copy with the "
                f"flags --help lists.")
        log(f"  input ok : {path}")


def frame_records(joined, split_of, predictions, canon, crop_frames, box_name_of=None):
    """One record per frame that has both a label and a cached answer.

    Raw name forms are kept alongside the canonicalised ones so the run can say
    what canonicalising was worth. Crop coverage rides along: whether the
    labelled crown is inside the square the model saw decides scorability.

    ``box_name_of`` maps a reviewed frame to the Labelbox name its crown boxes
    carry. A box records a species name and no crown id, so the labelled crown
    is recognised by name: a dominant species equal to the frame's Labelbox
    name is taken to be that crown, renamed by the review, and compared as the
    reviewed label. An approximation: another crown of that same Labelbox
    species filling the crop would pass too, as it always has under Labelbox.
    Neither the Labelbox export nor the workbook links a box to a crown, so
    this cannot be matched by id; ``crop_by_name`` marks the frames the rename
    let through and ``crop_crowns`` how many crowns of the filling species reach
    into the crop, which together count how exposed the gate is to it.
    """
    box_name_of = box_name_of or {}
    records = []
    for gk, stem, gt_name in joined:
        gt_c = canon(gt_name)
        cov = crop_frames.get(stem)
        dominant = canon(cov["dominant"]) if cov and cov["dominant"] else None
        by_name = (dominant is not None and dominant != gt_c and gk in box_name_of
                   and dominant == canon(box_name_of[gk]))
        if by_name:
            dominant = gt_c
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
            "crop_dominant": dominant,
            "crop_by_name": by_name,
            "crop_crowns": cov.get("crowns") if cov else None,
        })
    return records


def load_holdout(path: str = HOLDOUT_CSV) -> set:
    """The global keys the flight holdout holds, read off its role column.

    Only the held rows: a train or buffered row keeps whatever splits.csv says
    about it. An absent file holds nothing, which is what a checkout without a
    drawn holdout gets, and the run log says so.
    """
    if not os.path.exists(path):
        return set()
    return {r["global_key"] for r in read_csv_rows(path)
            if r.get("global_key") and r.get("role") == HOLDOUT_HELD_ROLE}


def merge_holdout(split_of: dict, held: set) -> dict:
    """Tag every held frame ``HOLDOUT_SPLIT`` in ``split_of``, in place of its
    splits.csv value, and return a count of the values that displaced.

    The tag is never ``test``: the held frames are graded on their own, beside
    the test score, and a held frame that also counted as test would put the
    same frame in both numbers. Any non-empty split holds a frame out of the
    queue, so the tag is enough to keep these frames from ever being sent.
    """
    displaced = Counter(split_of.get(k, "") for k in held)
    split_of.update(dict.fromkeys(held, HOLDOUT_SPLIT))
    return displaced


def only_label_source(gt_rows: list, label_source: str, gt_csv: str) -> list:
    """The GT rows whose ``label_source`` is ``label_source``.

    SystemExit when the file has no such column or no such row: asked for one
    population, a run that scored the whole file, or nothing, would publish a
    number under the wrong name.
    """
    if not gt_rows or LABEL_SOURCE_COLUMN not in gt_rows[0]:
        raise SystemExit(f"--label-source {label_source}: {gt_csv} has no "
                         f"{LABEL_SOURCE_COLUMN} column. labelling/gt_from_publication.py "
                         f"writes one.")
    kept = [r for r in gt_rows if r[LABEL_SOURCE_COLUMN] == label_source]
    if not kept:
        found = sorted({r[LABEL_SOURCE_COLUMN] for r in gt_rows})
        raise SystemExit(f"--label-source {label_source}: no row of {gt_csv} carries it "
                         f"(found: {', '.join(found)})")
    return kept


def other_populations(gt_all, gt_rows, sp_recs, predictions, records_of):
    """Every labelled stem with a cached answer, and the scored species-level
    records per ``label_source``, the headline's (``sp_recs``) included.

    The headline is one population; the rows it leaves out are still labelled,
    so they are scored beside it and held out of the send queue.
    """
    labelled_stems = {r["global_key"].removeprefix(GT_KEY_PREFIX) for r in gt_all}
    labelled_stems &= set(predictions)
    if not gt_all or LABEL_SOURCE_COLUMN not in gt_all[0]:
        return labelled_stems, {}
    scored = {id(r) for r in gt_rows}
    by_source = {}
    for source in sorted({r[LABEL_SOURCE_COLUMN] for r in gt_all}):
        rows = [r for r in gt_all if r[LABEL_SOURCE_COLUMN] == source]
        if all(id(r) in scored for r in rows):
            keys = {r["global_key"] for r in rows}
            by_source[source] = [r for r in sp_recs if r["global_key"] in keys]
            continue
        joined = [(r["global_key"], r["global_key"].removeprefix(GT_KEY_PREFIX),
                   r["wcvp_canonical_name"]) for r in rows]
        joined = [j for j in joined if j[1] in predictions]
        by_source[source] = [r for r in records_of(joined)
                             if r["species_level"] and r["ranked"]]
    return labelled_stems, by_source


def load_health(*, gt_csv=GT_CSV, splits_csv=SPLITS_CSV, cache_dir=CACHE_DIR,
                wcvp_cache=WCVP_CACHE_JSON, holdout_csv=HOLDOUT_CSV,
                label_source: str | None = None,
                log: Callable[[str], None] | None = None) -> Health:
    """Read the labels, the split and the cached answers into one ``Health``.

    Everything downstream reads what this returns rather than the files, so the
    pages and measure.py cannot disagree about what the corpus is. ``log`` is
    optional; only measure.py passes one. ``label_source`` keeps only the GT
    rows of that population, so every number downstream is measured on it alone;
    the other rows are scored beside it in ``by_source`` and never pooled in.
    ``all`` or None keeps every row.
    """
    def _log(msg: str = "") -> None:
        if log is not None:
            log(msg)

    labels = "the botanist labels"
    if label_source and label_source != LABEL_SOURCE_ALL:
        labels = ("the reviewed-label ground truth labelling/gt_from_publication.py "
                  "builds from the publication workbook (no fallback to the Labelbox "
                  "labels)")
    require_inputs(((gt_csv, labels),
                    (splits_csv, "the grading split"),
                    (cache_dir, "the cached Pl@ntNet answers")), _log)
    _log(f"  wcvp cache: {wcvp_cache if wcvp_cache and os.path.exists(wcvp_cache) else 'ABSENT (tier d disabled)'}")
    _log("")

    # ---------------- 1. the two input CSVs ----------------
    gt_all = read_csv_rows(gt_csv)
    gt_rows = gt_all
    if label_source and label_source != LABEL_SOURCE_ALL:
        gt_rows = only_label_source(gt_all, label_source, gt_csv)
        _log(f"  {LABEL_SOURCE_COLUMN} filter    : {label_source}, {len(gt_rows)} of {len(gt_all)} GT rows")
    split_rows = read_csv_rows(splits_csv)
    split_of = {r["global_key"]: r["split"] for r in split_rows}
    # The flight holdout on top of the frame-by-frame split. Merged before the
    # log and before any record is built, so every count downstream, the run
    # log's included, sees a held frame as held and not as train or test.
    held = load_holdout(holdout_csv)
    displaced = merge_holdout(split_of, held)

    rl.log_inputs(_log, gt_rows, split_rows, split_of)
    rl.log_holdout(_log, holdout_csv, held, displaced)

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
    canon = canonicaliser(crosswalk)

    # Joined on base_image: GT keys carry GT_KEY_PREFIX and the box CSV does not,
    # so the stem used for the cache join is the join key here too. Local import
    # for the same cycle reason as run_log above.
    import crop_overlap
    crop_frames, crop_suspect = crop_overlap.build()

    box_name_of = {r["global_key"]: r[LABELBOX_NAME_COLUMN] for r in gt_all
                   if r.get(LABEL_SOURCE_COLUMN) == LABEL_SOURCE_REVIEWED
                   and r.get(LABELBOX_NAME_COLUMN)}
    records = frame_records(joined, split_of, predictions, canon, crop_frames, box_name_of)

    sp_recs = [r for r in records if r["species_level"] and r["ranked"]]
    genus_recs = [r for r in records if not r["species_level"] and r["ranked"]]
    labelled_stems, by_source = other_populations(
        gt_all, gt_rows, sp_recs, predictions,
        lambda joined_: frame_records(joined_, split_of, predictions, canon, crop_frames,
                                      box_name_of))

    n_crop_joined = sum(1 for r in records if r["crop_coverage"] is not None)
    crop_admitted, crop_rejected = coverage_split(sp_recs, MIN_CROP_COVERAGE)
    rl.log_crop_gate(_log, records, sp_recs, crop_frames, crop_suspect,
                   n_crop_joined, crop_admitted, crop_rejected, MIN_CROP_COVERAGE)

    # ---------------- 6. one row per species ----------------
    corpus_canon = {canon(b) for b in corpus_raw}
    checklist = load_checklist()
    per_species = aggregate_per_species(sp_recs, corpus_norm, corpus_canon,
                                        membership(checklist, canon))

    return Health(
        gt_rows=gt_rows, split_rows=split_rows, split_of=split_of, predictions=predictions,
        maxk=maxk, joined=joined, missing_cache=missing_cache, crosswalk=crosswalk,
        corpus_norm=corpus_norm, corpus_canon=corpus_canon, gt_names=gt_names,
        tier_of_name=tier_of_name, tier_crowns=tier_crowns, records=records,
        sp_recs=sp_recs, genus_recs=genus_recs, per_species=per_species, canon=canon,
        checklist=checklist, labelled_stems=labelled_stems, by_source=by_source,
        reference=reference.reference_of(gt_all, label_source),
    )
