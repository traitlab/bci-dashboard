"""Every figure a page shows, computed once off one ``Health``.

One entry point: ``prepare``. Panels read what it returns and do no
arithmetic of their own, so two panels cannot drift by recomputing the same
figure differently.
"""

from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict
from types import SimpleNamespace

import core as hc
from history import model_tag_of, snapshot_date_of

# A species is "rarely labelled" below this many frames, and a frame can be
# deprioritised only at or above it. Both read hc.WELL_SAMPLED_MIN_N, the
# threshold hc.diagnose uses, so a page cannot render a status or a sentence
# that disagrees with the rule the data layer applied.
RARE_MAX_SUPPORT = hc.WELL_SAMPLED_MIN_N
WAIT_SUPPORT_MIN = hc.WELL_SAMPLED_MIN_N
# The confidence the page recommends is the one the queue applies. Written as
# 0.8 twice, the page could recommend a rule the queue does not implement.
RECOMMENDED_CONF = hc.WAIT_CONF

# The frozen confirmatory read, written by dashboard/score_confirmatory.py. The
# page reads the file rather than re-running the scorer, because the stopping
# rule in bci-dashboard-docs/hypothesis.md says that read happens once, on the
# complete set: a number that moved because a page was rebuilt would not be a
# confirmatory number. Tracked for the same reason the frozen frame list is.
CONFIRMATORY_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "input", "confirmatory_result_2026-08.csv")


def is_family(n: str) -> bool:
    """A one-word label ending in -aceae is a family, not a genus (exact:
    every family name carries that suffix). It can never match a predicted
    genus, so scoring it in a genus rate counts a guaranteed miss as
    measured.
    """
    return n.strip().lower().endswith("aceae")


def top1(r):
    return r["ranked"][0][0]


def conf(r):
    return r["ranked"][0][1]


def camera_of(key):
    """Which drone camera shot a frame, read off its key: ``zoom``
    (wide-angle) or ``tele`` (long-lens) in the file name. Counted, not
    assumed: the two populations are not the same one.
    """
    low = key.lower()
    for c in ("zoom", "tele"):
        if c in low:
            return c
    raise SystemExit(f"frame key names no camera: {key!r}. The camera split "
                     f"below reads the key, so a third camera has to be handled "
                     f"here rather than counted as neither.")


def load_confirmatory(path=CONFIRMATORY_CSV):
    """The frozen confirmatory read as a dict, or None if absent. Numeric
    values come back as floats, the rest as strings. Absent is not an error:
    a fresh clone that has not run the scorer still builds its other page.
    """
    if not os.path.exists(path):
        return None
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                out[row["key"]] = float(row["value"])
            except ValueError:
                out[row["key"]] = row["value"]
    return out


# Both pages state the list length in prose, and prose that disagrees with the
# metric is the defect this file exists to prevent. Aliased from core rather than
# restated, like RARE_MAX_SUPPORT above. prepare() checks the cache against it.
N_CANDIDATES = hc.N_CANDIDATES


def prepare(h, *, verify_dir, fallback_tag) -> SimpleNamespace:
    """Every figure both pages draw from, computed once off one ``Health``.
    Read-only for builders except ``checks``, filled in by the page after
    its own slice of ``history.verify_snapshot`` runs.
    """
    sp_recs, per_species = h.sp_recs, h.per_species
    longest = max(len(r["ranked"]) for r in sp_recs + h.genus_recs)
    if longest > N_CANDIDATES:
        raise SystemExit(
            f"cached predictions carry up to {longest} names per photo, but every rate\n"
            f"and every sentence on both pages is written for {N_CANDIDATES}. Re-ingest\n"
            f"changed the request setting: update N_CANDIDATES in dashboard/core.py.")
    n, n_sp = len(sp_recs), len(per_species)

    c1 = sum(1 for r in sp_recs if top1(r) == r["gt"])
    _c5 = sum(1 for r in sp_recs if r["gt"] in [b for b, _ in r["ranked"][:N_CANDIDATES]])
    now = dict(macro_top1=sum(d["top1_accuracy"] for d in per_species) / n_sp,
               macro_top5=sum(d["top5_accuracy"] for d in per_species) / n_sp,
               micro_top1=c1 / n, micro_top5=_c5 / n)

    support = {d["species"]: d["n_labelled_crowns"] for d in per_species}
    status = {d["species"]: hc.diagnose(d) for d in per_species}
    counts = defaultdict(int)
    for s in status.values():
        counts[s] += 1

    # --- frames grouped by how many labels their species has ---
    buckets = {}
    for d in per_species:
        buckets.setdefault(d["support_bucket"],
                           dict(n_species=0, n_crowns=0, c1=0))["n_species"] += 1
    for r in sp_recs:
        b = buckets[hc.bucket_label(support[r["gt"]])]
        b["n_crowns"] += 1
        b["c1"] += top1(r) == r["gt"]

    # --- confidence bands over the whole species-level set ---
    bins_all = [(f"[{lo:.1f},{min(hi, 1.0):.1f})", len(sub),
                 sum(1 for r in sub if top1(r) == r["gt"]))
                for lo, hi in hc.CONF_BINS
                for sub in ([r for r in sp_recs if lo <= conf(r) < hi],)]

    # --- what this evaluation cannot score, and what name matching is worth ---
    # "Never named": in no cached candidate list, so no threshold scores it. Counted
    # over the evaluated set and over every label; the run log uses the second.
    never = sorted((d for d in per_species if not d["in_corpus_vocabulary"]),
                   key=lambda d: -d["n_labelled_crowns"])
    never_sp = {d["species"] for d in never}
    never_crowns = sum(d["n_labelled_crowns"] for d in never)
    never_all = h.tier_crowns["e_absent_from_corpus"] + h.tier_crowns["c_genus_only_in_corpus"]
    reach = [r for r in sp_recs if r["gt"] not in never_sp]
    reach1 = sum(1 for r in reach if top1(r) == r["gt"]) / len(reach)
    # Labels and predictions are canonicalised the same way before matching. Scoring the raw
    # names instead says what that is worth, and it is a gain, never a source of error.
    strict1 = sum(1 for r in sp_recs
                  if r["ranked_strict"] and r["ranked_strict"][0][0] == r["gt_strict"])
    short5 = sum(1 for r in sp_recs + h.genus_recs if len(r["ranked"]) < N_CANDIDATES)
    n_pred = len(sp_recs) + len(h.genus_recs)

    tag = model_tag_of(verify_dir, fallback_tag)
    snap_date = snapshot_date_of(verify_dir)

    # --- send-first queue over the unlabelled pool, and labels worth a second look.
    # The logic lives in core so this page and measure.py cannot drift apart.
    acc_of = {d["species"]: d["top1_accuracy"] for d in per_species}
    joined_stems = {stem for _, stem, _ in h.joined}
    queue_counts = {}
    lt_species = defaultdict(int)
    queue_rows = []
    n_no_answer = 0
    for stem in sorted(h.predictions):
        if stem in joined_stems:
            continue
        ranked = [(h.canon(b), s) for b, s in h.predictions[stem]]
        if not ranked:
            n_no_answer += 1
            continue
        pred, cf = ranked[0]
        q = hc.queue_of_prediction(pred, cf, support, acc_of)
        queue_counts[q] = queue_counts.get(q, 0) + 1
        queue_rows.append((q, stem, pred, cf))
        if q == "long_tail":
            lt_species[pred] += 1
    n_unlab = sum(queue_counts.values())
    # send_first_queue.csv's own order. The page prints the head of that file and
    # tells the reader to open the rest, so two sorts would be two lists.
    queue_rows.sort(key=lambda r: (hc.QUEUE_ORDER.index(r[0]), r[3], r[1]))
    # The same order in the form send_first_queue.csv writes it, so
    # verify_snapshot can compare the two lists row for row.
    queue_keys = [hc.GT_KEY_PREFIX + stem for _, stem, _, _ in queue_rows]

    # How many scored frames the centre crop mostly misses. Read under the species
    # table and again under the four corpus rates, so it is computed here once.
    crop_half = sum(1 for r in sp_recs if (r.get("crop_coverage") or 0) < 0.5)
    crop_none = sum(1 for r in sp_recs if (r.get("crop_coverage") or 0) == 0)

    scored_cams = Counter(camera_of(r["global_key"]) for r in sp_recs)
    queue_cams = Counter(camera_of(stem) for _, stem, _, _ in queue_rows)

    confident = [r for r in sp_recs if conf(r) >= hc.REVIEW_CONF]
    # Same filter as measure.py's label_review_queue.csv, or verify_snapshot
    # aborts the build on the count mismatch. That check is the guard.
    adjudicated = hc.adjudicated_keys()
    raised = [r for r in confident if top1(r) != r["gt"]]
    review = [r for r in raised if r["global_key"] not in adjudicated]
    n_adjudicated = len(raised) - len(review)
    # The claim the review panel rests on. Measured, not asserted: it moves with
    # every batch, and stale it argues for spending expert time on the wrong list.
    # Counted over every disagreement, adjudicated or not: a botanist confirming
    # the label makes the model's guess wrong, not right.
    confident_hits = len(confident) - len(raised)
    confident_ok = confident_hits / len(confident)
    review_pairs = defaultdict(list)
    for r in review:
        review_pairs[(r["gt"], top1(r))].append(conf(r))
    review_counts = (len(review), len(review_pairs))

    # --- why confidence alone is unsafe: error by labelled frames, at the
    # lowest band core.CONF_THRESHOLDS names. The queue page writes this number
    # into its own column header, so it reads it from here rather than typing it.
    flat_thr = hc.CONF_THRESHOLDS[0]
    flat = {}
    for r in sp_recs:
        if conf(r) >= flat_thr:
            b = flat.setdefault(hc.bucket_label(support[r["gt"]]), [0, 0])
            b[0] += 1
            b[1] += top1(r) != r["gt"]

    # --- queue-ordering rules. Which species clear the gate is decided from train frames
    # only, then scored on test only, so no rule is graded on the frames that defined it.
    train_support = defaultdict(int)
    for r in sp_recs:
        if r["split"] == "train":
            train_support[r["gt"]] += 1
    eligible = {s for s, k in train_support.items() if k >= WAIT_SUPPORT_MIN}
    test_recs = [r for r in sp_recs if r["split"] == "test"]
    rare = {s for s, k in support.items() if k < RARE_MAX_SUPPORT}
    n_rare_test = sum(1 for r in test_recs if r["gt"] in rare)

    rules = [(f"{t} or more sure, any species", t, False)
             for t in hc.CONF_THRESHOLDS[:-1]]
    rules += [(f"{t} or more sure, and the species has at least {WAIT_SUPPORT_MIN} "
               f"labelled frames", t, True) for t in hc.CONF_THRESHOLDS]
    ops = []
    for label, thr, gate in rules:
        wait = [r for r in test_recs if conf(r) >= thr and (not gate or r["gt"] in eligible)]
        ids = {id(r) for r in wait}
        rest = [r for r in test_recs if id(r) not in ids]
        ops.append(dict(label=label, thr=thr, gate=gate, n=len(wait),
                        share=len(wait) / len(test_recs) if test_recs else None,
                        err=sum(1 for r in wait if top1(r) != r["gt"]) / len(wait)
                        if wait else None,
                        rare=sum(1 for r in wait if r["gt"] in rare),
                        rare_rest=sum(1 for r in rest if r["gt"] in rare) / len(rest)
                        if rest else None))
    best = next(o for o in ops if o["gate"] and abs(o["thr"] - RECOMMENDED_CONF) < 1e-9)

    # Kept apart from family-only labels: a family name can never equal a predicted
    # genus, so mixing them scores guaranteed misses as measured ones.
    fam_recs = [r for r in h.genus_recs if is_family(r["gt"])]
    gen_recs = [r for r in h.genus_recs if not is_family(r["gt"])]
    gn, fam_n = len(gen_recs), len(fam_recs)
    gg1 = sum(1 for r in gen_recs if hc.genus_of(r["ranked"][0][0]) == r["gt"])
    fam_names = len({r["gt"] for r in fam_recs})
    # Genus-only frames whose right answer is narrowed to one in-genus candidate:
    # the cheapest confirmation on the page, a yes/no rather than an identification.
    in_gen = [sum(1 for b, _ in r["ranked"][:N_CANDIDATES] if hc.genus_of(b) == r["gt"]) for r in gen_recs]
    gen_any = sum(1 for k in in_gen if k)
    gen_one = sum(1 for k in in_gen if k == 1)
    gen_none = len(in_gen) - gen_any

    return SimpleNamespace(
        h=h, sp_recs=sp_recs, per_species=per_species, n=n, n_sp=n_sp,
        c1=c1, now=now, support=support, status=status, counts=counts,
        buckets=buckets, bins_all=bins_all, never=never, never_crowns=never_crowns,
        never_all=never_all, reach=reach, reach1=reach1, unscoreable=n - len(reach),
        strict1=strict1, short5=short5, n_pred=n_pred, tag=tag, snap_date=snap_date,
        queue_counts=queue_counts, lt_species=lt_species, queue_rows=queue_rows,
        queue_keys=queue_keys,
        n_no_answer=n_no_answer, n_unlab=n_unlab, scored_cams=scored_cams,
        queue_cams=queue_cams, confident=confident, review=review,
        confident_ok=confident_ok, confident_hits=confident_hits,
        n_adjudicated=n_adjudicated,
        review_pairs=review_pairs, review_counts=review_counts,
        flat=flat, flat_thr=flat_thr, eligible=eligible, test_recs=test_recs, rare=rare,
        n_rare_test=n_rare_test, ops=ops, best=best, gn=gn, fam_n=fam_n, gg1=gg1,
        fam_names=fam_names, gen_any=gen_any, gen_one=gen_one, gen_none=gen_none,
        n_cand=N_CANDIDATES, cf=load_confirmatory(), checks=None,
        crop_half=crop_half, crop_none=crop_none,
        # Every frame a botanist has labelled at all, whatever rank the name
        # stops at and whether or not a Pl@ntNet answer was cached for it. The
        # widest of the three frame counts the page reconciles.
        n_gt=len(h.gt_rows))
